#!/usr/bin/env python3
"""Deterministic noncanonical Architect worker-packet validator/matcher/ACK helper.

This tool does not grant mutation, runtime-dispatch, effect, provider, or credit authority.
It only evaluates coordination packets after canonical worker authority has been resolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

PACKET_SCHEMA = "F2_ARCHITECT_WORKER_PACKET/v1"
ACK_SCHEMA = "F2_ARCHITECT_WORKER_PACKET_ACK/v1"
ACTION_CLASSES = {
    "COORDINATION_ONLY",
    "CONTEXT_DELTA",
    "REVIEW_ONLY",
    "CANDIDATE_FALSIFIER",
    "RESEARCH_REQUEST",
    "STOP_DEFER",
}
TARGET_FIELDS = {
    "worker_id",
    "worker_lane",
    "trigger",
    "workpackage_id",
    "generation",
    "claim_id",
    "runtime_subject_id",
    "organ",
}
DISPOSITIONS = {
    "APPLIED",
    "ACK_ONLY_DUPLICATE",
    "REJECT_STALE",
    "REJECT_MISADDRESSED",
    "REJECT_SUPERSEDED",
    "REJECT_AUTHORITY_CONFLICT",
    "REJECT_SCHEMA_INVALID",
}
REQUIRED_PACKET_FIELDS = {
    "schema",
    "packet_id",
    "nonce",
    "issued_at",
    "expires_at",
    "architect_id",
    "project",
    "priority",
    "action_class",
    "target",
    "objective",
    "constraints",
    "expected_output",
    "evidence_refs",
    "supersedes_packet_ids",
    "credit_authority",
    "mutation_authority",
    "runtime_dispatch_authority",
}


class PacketError(ValueError):
    pass


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PacketError("timestamp must be a non-empty RFC3339 string")
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PacketError(f"invalid RFC3339 timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        raise PacketError("timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def _load(path: str | pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def validate_packet(packet: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_PACKET_FIELDS - set(packet))
    if missing:
        raise PacketError(f"missing required fields: {', '.join(missing)}")
    if packet.get("schema") != PACKET_SCHEMA:
        raise PacketError(f"schema must be {PACKET_SCHEMA}")
    for field in ("packet_id", "nonce", "architect_id", "project", "objective"):
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            raise PacketError(f"{field} must be a non-empty string")
    if packet.get("action_class") not in ACTION_CLASSES:
        raise PacketError("unsupported action_class")
    if not isinstance(packet.get("priority"), int) or not 0 <= packet["priority"] <= 100:
        raise PacketError("priority must be integer 0..100")
    target = packet.get("target")
    if not isinstance(target, dict) or not target:
        raise PacketError("target must contain at least one selector; implicit global broadcast is forbidden")
    unknown = sorted(set(target) - TARGET_FIELDS)
    if unknown:
        raise PacketError(f"unknown target selectors: {', '.join(unknown)}")
    for key, value in target.items():
        values = value if isinstance(value, list) else [value]
        if not values or any(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            raise PacketError(f"target selector {key} contains empty value")
    if not isinstance(packet.get("constraints"), list):
        raise PacketError("constraints must be a list")
    if not isinstance(packet.get("expected_output"), dict):
        raise PacketError("expected_output must be an object")
    if not isinstance(packet.get("evidence_refs"), list):
        raise PacketError("evidence_refs must be a list")
    if not isinstance(packet.get("supersedes_packet_ids"), list):
        raise PacketError("supersedes_packet_ids must be a list")
    issued = _parse_time(packet["issued_at"])
    expires = _parse_time(packet["expires_at"])
    if expires <= issued:
        raise PacketError("expires_at must be after issued_at")
    for field in ("credit_authority", "mutation_authority", "runtime_dispatch_authority"):
        if packet.get(field) is not False:
            raise PacketError(f"{field} must be false in Architect coordination packets")


def _selector_matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list):
        return any(_selector_matches(item, actual) for item in expected)
    if isinstance(actual, list):
        return any(_selector_matches(expected, item) for item in actual)
    return expected == actual


def target_matches(target: dict[str, Any], worker_context: dict[str, Any]) -> bool:
    if not target:
        return False
    return all(key in worker_context and _selector_matches(value, worker_context[key]) for key, value in target.items())


def packet_disposition(
    packet: dict[str, Any],
    worker_context: dict[str, Any],
    *,
    now: datetime | None = None,
    seen_nonces: Iterable[str] = (),
    superseded_packet_ids: Iterable[str] = (),
    authority_conflict: bool = False,
) -> str:
    try:
        validate_packet(packet)
    except PacketError:
        return "REJECT_SCHEMA_INVALID"
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now >= _parse_time(packet["expires_at"]):
        return "REJECT_STALE"
    if not target_matches(packet["target"], worker_context):
        return "REJECT_MISADDRESSED"
    if packet["packet_id"] in set(superseded_packet_ids):
        return "REJECT_SUPERSEDED"
    if packet["nonce"] in set(seen_nonces):
        return "ACK_ONLY_DUPLICATE"
    if authority_conflict:
        return "REJECT_AUTHORITY_CONFLICT"
    return "APPLIED"


def make_ack(
    packet: dict[str, Any],
    worker_context: dict[str, Any],
    disposition: str,
    *,
    reason: str,
    authority_head: str,
    observed_at: datetime | None = None,
    event_head_ref: str | None = None,
    active_pointer_ref: str | None = None,
) -> dict[str, Any]:
    if disposition not in DISPOSITIONS:
        raise PacketError("invalid disposition")
    observed = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    packet_bytes = len(_dump(packet).encode("utf-8"))
    stable = "|".join(
        str(x or "")
        for x in (
            packet.get("packet_id"),
            worker_context.get("worker_id"),
            worker_context.get("claim_id"),
            disposition,
            observed.isoformat(),
        )
    )
    ack_id = "AWA-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]
    return {
        "schema": ACK_SCHEMA,
        "ack_id": ack_id,
        "packet_id": packet.get("packet_id"),
        "nonce": packet.get("nonce"),
        "worker_id": worker_context.get("worker_id"),
        "worker_lane": worker_context.get("worker_lane"),
        "workpackage_id": worker_context.get("workpackage_id"),
        "generation": worker_context.get("generation"),
        "claim_id": worker_context.get("claim_id"),
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "disposition": disposition,
        "authority_head": authority_head,
        "event_head_ref": event_head_ref,
        "active_pointer_ref": active_pointer_ref,
        "reason": reason,
        "context_bytes_injected": packet_bytes if disposition == "APPLIED" else 0,
        "estimated_context_tokens_injected": (packet_bytes + 3) // 4 if disposition == "APPLIED" else 0,
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "credit_delta": 0,
    }


def new_packet(
    *,
    target: dict[str, Any],
    objective: str,
    action_class: str,
    ttl_minutes: int,
    priority: int,
    architect_id: str,
    project: str,
    constraints: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    issued = datetime.now(timezone.utc)
    packet_uuid = uuid.uuid4().hex
    packet = {
        "schema": PACKET_SCHEMA,
        "packet_id": f"AWP-{issued.strftime('%Y%m%dT%H%M%SZ')}-{packet_uuid[:12]}",
        "nonce": packet_uuid,
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued + timedelta(minutes=ttl_minutes)).isoformat().replace("+00:00", "Z"),
        "architect_id": architect_id,
        "project": project,
        "priority": priority,
        "action_class": action_class,
        "target": target,
        "objective": objective,
        "constraints": constraints,
        "expected_output": {
            "ack_required": True,
            "result_summary_required": True,
            "telemetry_required": True,
        },
        "evidence_refs": evidence_refs,
        "supersedes_packet_ids": [],
        "credit_authority": False,
        "mutation_authority": False,
        "runtime_dispatch_authority": False,
    }
    validate_packet(packet)
    return packet


def _read_string_set(path: str | None) -> set[str]:
    if not path:
        return set()
    data = _load(path)
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        return {str(x) for x, enabled in data.items() if enabled}
    raise PacketError("set file must be JSON list or object")


def cmd_validate(args: argparse.Namespace) -> int:
    packet = _load(args.packet)
    try:
        validate_packet(packet)
    except PacketError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print("VALID")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    packet = _load(args.packet)
    context = _load(args.context)
    now = _parse_time(args.now) if args.now else None
    disposition = packet_disposition(
        packet,
        context,
        now=now,
        seen_nonces=_read_string_set(args.seen_nonces),
        superseded_packet_ids=_read_string_set(args.superseded_packet_ids),
        authority_conflict=args.authority_conflict,
    )
    print(disposition)
    return 0 if disposition == "APPLIED" else 3


def cmd_ack(args: argparse.Namespace) -> int:
    packet = _load(args.packet)
    context = _load(args.context)
    disposition = args.disposition
    ack = make_ack(
        packet,
        context,
        disposition,
        reason=args.reason,
        authority_head=args.authority_head,
        event_head_ref=args.event_head_ref,
        active_pointer_ref=args.active_pointer_ref,
    )
    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.output).write_text(_dump(ack), encoding="utf-8")
    print(args.output)
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    target = json.loads(args.target_json)
    packet = new_packet(
        target=target,
        objective=args.objective,
        action_class=args.action_class,
        ttl_minutes=args.ttl_minutes,
        priority=args.priority,
        architect_id=args.architect_id,
        project=args.project,
        constraints=args.constraint or [],
        evidence_refs=args.evidence_ref or [],
    )
    text = _dump(packet)
    if args.output:
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.output).write_text(text, encoding="utf-8")
        print(args.output)
    else:
        print(text, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate")
    p.add_argument("packet")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("match")
    p.add_argument("packet")
    p.add_argument("context")
    p.add_argument("--now")
    p.add_argument("--seen-nonces")
    p.add_argument("--superseded-packet-ids")
    p.add_argument("--authority-conflict", action="store_true")
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("ack")
    p.add_argument("packet")
    p.add_argument("context")
    p.add_argument("output")
    p.add_argument("--disposition", choices=sorted(DISPOSITIONS), required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--authority-head", required=True)
    p.add_argument("--event-head-ref")
    p.add_argument("--active-pointer-ref")
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("new")
    p.add_argument("--target-json", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--action-class", choices=sorted(ACTION_CLASSES), default="COORDINATION_ONLY")
    p.add_argument("--ttl-minutes", type=int, default=120)
    p.add_argument("--priority", type=int, default=50)
    p.add_argument("--architect-id", default="persistent-architect")
    p.add_argument("--project", default="frankenstein-2.0")
    p.add_argument("--constraint", action="append")
    p.add_argument("--evidence-ref", action="append")
    p.add_argument("--output")
    p.set_defaults(func=cmd_new)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "ttl_minutes", 1) <= 0:
        parser.error("--ttl-minutes must be > 0")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
