#!/usr/bin/env python3
"""Deterministic create-only intent reservation for Architect coordination packets.

This module does not create canonical project state and does not own delivery.
It compiles one explicit coordination intent identity into a stable reservation
path and a normal Architect packet. The reservation and packet MUST be created
in one repository CAS commit. Competing creators for the same intent generation
therefore contend for the same create-only path; only one packet may become
active for that intent generation.

Generation is deliberately not caller-selectable. With no observed reservation
only generation 1 can be compiled. A successor generation can only be derived
from a validated previous reservation after that reservation is terminal or
expired. An active reservation is reused rather than bypassed with generation+1.

Packet nonce/route identity remains independent and is still handled by
``architect_packet.py`` plus the existing Clay delivery atomicity primitive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

from tools.coordination.architect_packet import new_packet

INTENT_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT/v1"
RESERVATION_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT_RESERVATION/v1"
INTENT_ROOT = "coordination/architect_packets/intents"
PENDING_ROOT = "coordination/architect_packets/pending"
DECISIONS = {
    "CREATE_CANDIDATE",
    "REUSE_EXISTING_PACKET",
    "NEXT_GENERATION_REQUIRED",
}


class IntentError(ValueError):
    pass


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def normalize_intent_id(value: str) -> str:
    """Normalize an explicit machine identity, never infer identity from prose."""
    if not isinstance(value, str) or not value.strip():
        raise IntentError("intent_id must be a non-empty explicit string")
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]{2,127}", normalized):
        raise IntentError(
            "intent_id must be 3..128 characters of [A-Za-z0-9._:/-] "
            "and start with an alphanumeric character"
        )
    return normalized


def canonical_intent(
    *, project: str, architect_id: str, intent_id: str
) -> dict[str, Any]:
    if not isinstance(project, str) or not project.strip():
        raise IntentError("project must be non-empty")
    if not isinstance(architect_id, str) or not architect_id.strip():
        raise IntentError("architect_id must be non-empty")
    return {
        "schema": INTENT_SCHEMA,
        "project": project.strip(),
        "architect_id": architect_id.strip(),
        "intent_id": normalize_intent_id(intent_id),
    }


def intent_key(*, project: str, architect_id: str, intent_id: str) -> str:
    return hashlib.sha256(
        _canonical_json(
            canonical_intent(
                project=project, architect_id=architect_id, intent_id=intent_id
            )
        )
    ).hexdigest()


def reservation_path(
    *, project: str, architect_id: str, intent_id: str, generation: int
) -> str:
    if not isinstance(generation, int) or generation < 1:
        raise IntentError("generation must be an integer >= 1")
    key = intent_key(project=project, architect_id=architect_id, intent_id=intent_id)
    return f"{INTENT_ROOT}/{key}/{generation:06d}.json"


def pending_packet_path(packet_id: str) -> str:
    if not isinstance(packet_id, str) or not packet_id.strip():
        raise IntentError("packet_id must be non-empty")
    return f"{PENDING_ROOT}/{packet_id}.json"


def validate_reservation(reservation: dict[str, Any]) -> None:
    if reservation.get("schema") != RESERVATION_SCHEMA:
        raise IntentError(f"schema must be {RESERVATION_SCHEMA}")
    generation = reservation.get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise IntentError("reservation generation must be integer >= 1")
    intent = reservation.get("intent")
    if not isinstance(intent, dict):
        raise IntentError("reservation intent must be an object")
    expected_intent = canonical_intent(
        project=intent.get("project"),
        architect_id=intent.get("architect_id"),
        intent_id=intent.get("intent_id"),
    )
    if intent != expected_intent:
        raise IntentError("reservation intent is not canonical")
    expected_key = hashlib.sha256(_canonical_json(expected_intent)).hexdigest()
    if reservation.get("intent_key") != expected_key:
        raise IntentError("intent_key mismatch")
    expected_path = f"{INTENT_ROOT}/{expected_key}/{generation:06d}.json"
    if reservation.get("reservation_path") != expected_path:
        raise IntentError("reservation_path mismatch")
    packet_id = reservation.get("packet_id")
    if not isinstance(packet_id, str) or not packet_id.strip():
        raise IntentError("packet_id must be non-empty")
    if reservation.get("packet_path") != pending_packet_path(packet_id):
        raise IntentError("packet_path mismatch")
    for field in ("packet_route_id", "packet_nonce", "packet_payload_digest"):
        if not isinstance(reservation.get(field), str) or not reservation[field].strip():
            raise IntentError(f"{field} must be non-empty")
    for field in (
        "credit_authority",
        "mutation_authority",
        "runtime_dispatch_authority",
        "effect_authority",
    ):
        if reservation.get(field) is not False:
            raise IntentError(f"{field} must be false")
    if reservation.get("credit_delta") != 0:
        raise IntentError("credit_delta must be zero")
    expires_at = reservation.get("packet_expires_at")
    if not isinstance(expires_at, str) or not expires_at.strip():
        raise IntentError("packet_expires_at must be non-empty")


def reservation_decision(
    existing: dict[str, Any],
    *,
    now: datetime | None = None,
    terminal_packet_ids: Iterable[str] = (),
) -> str:
    """Classify an already-created reservation without mutating it."""
    validate_reservation(existing)
    if existing["packet_id"] in set(terminal_packet_ids):
        return "NEXT_GENERATION_REQUIRED"
    text = existing["packet_expires_at"].replace("Z", "+00:00")
    try:
        expires = datetime.fromisoformat(text)
    except ValueError as exc:
        raise IntentError("invalid packet_expires_at") from exc
    if expires.tzinfo is None:
        raise IntentError("packet_expires_at must include timezone")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if current >= expires.astimezone(timezone.utc):
        return "NEXT_GENERATION_REQUIRED"
    return "REUSE_EXISTING_PACKET"


def _reuse_result(existing: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "REUSE_EXISTING_PACKET",
        "intent_key": existing["intent_key"],
        "reservation_path": existing["reservation_path"],
        "packet_path": existing["packet_path"],
        "reservation": existing,
        "packet": None,
        "atomic_repository_contract": {
            "required": False,
            "write_mode": "NO_WRITE_REUSE_EXISTING_PACKET",
            "same_intent_generation_collision": "REUSE_EXISTING_PACKET",
            "force_push_forbidden": True,
            "packet_created_without_reservation_credit": 0,
        },
    }


def _compile_generation_bundle(
    *,
    intent: dict[str, Any],
    generation: int,
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
    """Internal generation compiler; generation selection belongs to public state logic."""
    key = hashlib.sha256(_canonical_json(intent)).hexdigest()
    claim_path = f"{INTENT_ROOT}/{key}/{generation:06d}.json"
    claim_ref = f"coordination_intent_reservation:{claim_path}"
    packet_refs = list(evidence_refs)
    if claim_ref not in packet_refs:
        packet_refs.append(claim_ref)
    packet = new_packet(
        target=target,
        objective=objective,
        action_class=action_class,
        ttl_minutes=ttl_minutes,
        priority=priority,
        architect_id=architect_id,
        project=project,
        constraints=constraints,
        evidence_refs=packet_refs,
    )
    packet_path = pending_packet_path(packet["packet_id"])
    reservation = {
        "schema": RESERVATION_SCHEMA,
        "intent": intent,
        "intent_key": key,
        "generation": generation,
        "reservation_path": claim_path,
        "packet_id": packet["packet_id"],
        "packet_path": packet_path,
        "packet_route_id": packet["route_id"],
        "packet_nonce": packet["nonce"],
        "packet_payload_digest": packet["payload_digest"],
        "packet_issued_at": packet["issued_at"],
        "packet_expires_at": packet["expires_at"],
        "target": packet["target"],
        "action_class": packet["action_class"],
        "state": "RESERVED_CREATE_ONLY",
        "credit_authority": False,
        "mutation_authority": False,
        "runtime_dispatch_authority": False,
        "effect_authority": False,
        "credit_delta": 0,
    }
    validate_reservation(reservation)
    return {
        "decision": "CREATE_CANDIDATE",
        "intent_key": key,
        "reservation_path": claim_path,
        "packet_path": packet_path,
        "reservation": reservation,
        "packet": packet,
        "atomic_repository_contract": {
            "required": True,
            "write_mode": "CREATE_ONLY_BOTH_IN_ONE_GIT_CAS_COMMIT",
            "same_intent_generation_collision": "REFRESH_AND_REUSE_OR_DEFER",
            "force_push_forbidden": True,
            "packet_created_without_reservation_credit": 0,
        },
    }


def compile_intent_bundle(
    *,
    intent_id: str,
    target: dict[str, Any],
    objective: str,
    action_class: str,
    ttl_minutes: int,
    priority: int,
    architect_id: str,
    project: str,
    constraints: list[str],
    evidence_refs: list[str],
    existing_reservation: dict[str, Any] | None = None,
    now: datetime | None = None,
    terminal_packet_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Compile only the legally next candidate generation, or reuse the active one.

    There is intentionally no caller-selectable ``generation`` argument. If the
    caller has no observed reservation, only generation 1 can be proposed; an
    already-existing generation 1 will therefore collide at repository CAS. To
    reach generation N+1, the caller must provide the validated observed
    generation N and that reservation must be terminal or expired.
    """
    intent = canonical_intent(
        project=project, architect_id=architect_id, intent_id=intent_id
    )
    generation = 1
    if existing_reservation is not None:
        validate_reservation(existing_reservation)
        if existing_reservation["intent"] != intent:
            raise IntentError("existing reservation belongs to a different coordination intent")
        decision = reservation_decision(
            existing_reservation,
            now=now,
            terminal_packet_ids=terminal_packet_ids,
        )
        if decision == "REUSE_EXISTING_PACKET":
            return _reuse_result(existing_reservation)
        if decision != "NEXT_GENERATION_REQUIRED":
            raise IntentError(f"unsupported reservation decision: {decision}")
        generation = existing_reservation["generation"] + 1

    return _compile_generation_bundle(
        intent=intent,
        generation=generation,
        target=target,
        objective=objective,
        action_class=action_class,
        ttl_minutes=ttl_minutes,
        priority=priority,
        architect_id=architect_id,
        project=project,
        constraints=constraints,
        evidence_refs=evidence_refs,
    )


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise IntentError("invalid --now RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise IntentError("--now must include timezone")
    return parsed.astimezone(timezone.utc)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--intent-id", required=True)
    p.add_argument("--existing-reservation")
    p.add_argument("--terminal-packet-id", action="append")
    p.add_argument("--now")
    p.add_argument("--target-json", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--action-class", default="COORDINATION_ONLY")
    p.add_argument("--ttl-minutes", type=int, default=120)
    p.add_argument("--priority", type=int, default=50)
    p.add_argument("--architect-id", default="persistent-architect")
    p.add_argument("--project", default="frankenstein-2.0")
    p.add_argument("--constraint", action="append")
    p.add_argument("--evidence-ref", action="append")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.ttl_minutes <= 0:
        raise SystemExit("--ttl-minutes must be > 0")
    target = json.loads(args.target_json)
    existing = None
    if args.existing_reservation:
        existing = json.loads(
            pathlib.Path(args.existing_reservation).read_text(encoding="utf-8")
        )
    try:
        bundle = compile_intent_bundle(
            intent_id=args.intent_id,
            target=target,
            objective=args.objective,
            action_class=args.action_class,
            ttl_minutes=args.ttl_minutes,
            priority=args.priority,
            architect_id=args.architect_id,
            project=args.project,
            constraints=args.constraint or [],
            evidence_refs=args.evidence_ref or [],
            existing_reservation=existing,
            now=_parse_time(args.now),
            terminal_packet_ids=args.terminal_packet_id or [],
        )
    except IntentError as exc:
        print(f"INTENT_REJECTED: {exc}")
        return 2
    print(_dump(bundle), end="")
    return 0 if bundle["decision"] == "CREATE_CANDIDATE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
