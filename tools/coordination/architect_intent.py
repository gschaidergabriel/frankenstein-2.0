#!/usr/bin/env python3
"""Create-only coordination-intent fence for Architect packet creation.

This module is deliberately separate from packet delivery idempotency.  Packet
nonce/route identity still belongs to ``architect_packet``; this helper only
ensures that one explicit coordination intent revision maps to one deterministic
pending-packet path.  Repository create-only/CAS semantics then make concurrent
creators converge on one winner instead of producing parallel semantic work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
from typing import Any, Mapping

from tools.coordination.architect_packet import (
    ACTION_CLASSES,
    PacketError,
    compute_route_id,
    new_packet,
    validate_packet,
)

INTENT_REF_PREFIX = "coordination-intent:"
DEFAULT_PENDING_ROOT = pathlib.Path("coordination/architect_packets/pending")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,127}$")
_REV_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def validate_intent_identity(intent_id: str, revision: str) -> None:
    if not isinstance(intent_id, str) or not _ID_RE.fullmatch(intent_id):
        raise PacketError("coordination_intent_id must match [A-Za-z0-9][A-Za-z0-9._:/-]{1,127}")
    if not isinstance(revision, str) or not _REV_RE.fullmatch(revision):
        raise PacketError("intent_revision must match [A-Za-z0-9][A-Za-z0-9._-]{0,31}")


def intent_evidence_ref(intent_id: str, revision: str) -> str:
    validate_intent_identity(intent_id, revision)
    return f"{INTENT_REF_PREFIX}{intent_id}@{revision}"


def intent_key(*, project: str, target: Mapping[str, Any], intent_id: str, revision: str) -> str:
    """Deterministic creation identity, independent of objective wording."""
    validate_intent_identity(intent_id, revision)
    material = {
        "project": project,
        "target": target,
        "coordination_intent_id": intent_id,
        "intent_revision": revision,
    }
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def intent_packet_id(*, project: str, target: Mapping[str, Any], intent_id: str, revision: str) -> str:
    return "AWP-INTENT-" + intent_key(
        project=project,
        target=target,
        intent_id=intent_id,
        revision=revision,
    )[:24]


def new_intent_packet(
    *,
    target: dict[str, Any],
    objective: str,
    intent_id: str,
    intent_revision: str,
    action_class: str,
    ttl_minutes: int,
    priority: int,
    architect_id: str,
    project: str,
    constraints: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    """Build a normal packet whose create path is stable for one explicit intent revision."""
    ref = intent_evidence_ref(intent_id, intent_revision)
    refs = list(evidence_refs)
    if ref not in refs:
        refs.append(ref)
    packet = new_packet(
        target=target,
        objective=objective,
        action_class=action_class,
        ttl_minutes=ttl_minutes,
        priority=priority,
        architect_id=architect_id,
        project=project,
        constraints=constraints,
        evidence_refs=refs,
    )
    packet["packet_id"] = intent_packet_id(
        project=project,
        target=target,
        intent_id=intent_id,
        revision=intent_revision,
    )
    # payload_digest already binds evidence_refs, including the explicit intent
    # identity. route_id must be recomputed because packet_id changed.
    packet["route_id"] = compute_route_id(packet)
    validate_packet(packet)
    return packet


def pending_path(packet: Mapping[str, Any], *, root: pathlib.Path = DEFAULT_PENDING_ROOT) -> pathlib.Path:
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not packet_id.startswith("AWP-INTENT-"):
        raise PacketError("intent packet_id missing deterministic AWP-INTENT prefix")
    return root / f"{packet_id}.json"


def _intent_refs(packet: Mapping[str, Any]) -> set[str]:
    refs = packet.get("evidence_refs")
    if not isinstance(refs, list):
        return set()
    return {str(ref) for ref in refs if str(ref).startswith(INTENT_REF_PREFIX)}


def create_only_write(packet: dict[str, Any], path: pathlib.Path) -> tuple[str, dict[str, Any]]:
    """Atomically create one local/repository checkout owner for the intent path.

    ``O_EXCL`` gives same-checkout process atomicity.  When this deterministic
    path is committed with GitHub's create-file/CAS flow, concurrent branches
    race on the same repository path; the loser must refresh and reuse/defer.
    """
    validate_packet(packet)
    expected = pending_path(packet, root=path.parent)
    if expected != path:
        raise PacketError(f"output path must be deterministic intent path {expected}")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _dump(packet).encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        validate_packet(existing)
        if existing.get("packet_id") != packet.get("packet_id"):
            raise PacketError("deterministic intent path collision with different packet_id")
        wanted_refs = _intent_refs(packet)
        existing_refs = _intent_refs(existing)
        if len(wanted_refs) != 1 or wanted_refs != existing_refs:
            raise PacketError("deterministic intent path collision with different intent identity")
        return "REUSE_EXISTING", existing
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return "CREATED", packet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-json", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--coordination-intent-id", required=True)
    parser.add_argument("--intent-revision", default="v1")
    parser.add_argument("--action-class", choices=sorted(ACTION_CLASSES), default="COORDINATION_ONLY")
    parser.add_argument("--ttl-minutes", type=int, default=120)
    parser.add_argument("--priority", type=int, default=50)
    parser.add_argument("--architect-id", default="persistent-architect")
    parser.add_argument("--project", default="frankenstein-2.0")
    parser.add_argument("--constraint", action="append")
    parser.add_argument("--evidence-ref", action="append")
    parser.add_argument(
        "--checkout-root",
        default=".",
        help="repository checkout root; deterministic pending path is created below it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ttl_minutes <= 0:
        raise PacketError("--ttl-minutes must be > 0")
    target = json.loads(args.target_json)
    packet = new_intent_packet(
        target=target,
        objective=args.objective,
        intent_id=args.coordination_intent_id,
        intent_revision=args.intent_revision,
        action_class=args.action_class,
        ttl_minutes=args.ttl_minutes,
        priority=args.priority,
        architect_id=args.architect_id,
        project=args.project,
        constraints=args.constraint or [],
        evidence_refs=args.evidence_ref or [],
    )
    root = pathlib.Path(args.checkout_root) / DEFAULT_PENDING_ROOT
    path = pending_path(packet, root=root)
    status, winner = create_only_write(packet, path)
    print(_dump({
        "status": status,
        "path": str(path),
        "packet_id": winner["packet_id"],
        "route_id": winner["route_id"],
        "nonce": winner["nonce"],
        "credit_delta": 0,
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
    }), end="")
    return 0 if status == "CREATED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
