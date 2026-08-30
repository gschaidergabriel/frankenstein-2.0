#!/usr/bin/env python3
"""Stateless packet validation/ACK plus noncanonical coordination-intent creation fencing.

Delivery ownership/CAS/UNKNOWN_DELIVERY semantics remain with Clay's existing
`research_entity/coordination/live_reentry_delivery_atomicity.py` primitive.
This F2 helper validates packet identity, matches a resolved worker context,
emits non-authoritative ACK evidence, and provides a deterministic create-only
coordination-intent fence so concurrent Architect reentries cannot create
parallel active packets for one explicit intent identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

PACKET_SCHEMA = "F2_ARCHITECT_WORKER_PACKET/v1"
ACK_SCHEMA = "F2_ARCHITECT_WORKER_PACKET_ACK/v1"
INTENT_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT_EVENT/v1"
MESSAGE_KIND = "ARCHITECT_COORDINATION_PACKET"
ACTION_CLASSES = {
    "ACK_ONLY",
    "STATUS",
    "REVIEW_ONLY",
    "CANDIDATE_FALSIFIER",
    "COORDINATION_ONLY",
    "CONTEXT_DELTA",
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
INTENT_STATES = {"ACTIVE", "TERMINAL"}
INTENT_CREATION_DISPOSITIONS = {"CLAIMED", "REUSE_ACTIVE"}
REQUIRED_PACKET_FIELDS = {
    "schema",
    "packet_id",
    "route_id",
    "nonce",
    "payload_digest",
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
    "effect_authority",
}


class PacketError(ValueError):
    pass


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: str | pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _validate_coordination_intent_id(value: Any) -> str:
    if not isinstance(value, str):
        raise PacketError("coordination_intent_id must be a string")
    text = value.strip()
    if not text or text != value:
        raise PacketError("coordination_intent_id must be a non-empty trimmed string")
    if len(text) > 256:
        raise PacketError("coordination_intent_id must be <= 256 characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise PacketError("coordination_intent_id must not contain control characters")
    return text


def coordination_intent_key(coordination_intent_id: str) -> str:
    intent_id = _validate_coordination_intent_id(coordination_intent_id)
    return hashlib.sha256(intent_id.encode("utf-8")).hexdigest()


def payload_identity(packet: Mapping[str, Any]) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "objective": packet.get("objective"),
        "constraints": packet.get("constraints"),
        "expected_output": packet.get("expected_output"),
        "evidence_refs": packet.get("evidence_refs"),
        "supersedes_packet_ids": packet.get("supersedes_packet_ids"),
        "runtime_subject_fence": packet.get("runtime_subject_fence"),
        "owner_intent_epoch": packet.get("owner_intent_epoch"),
    }
    # Historical v1 packets did not carry this field. Add it to the sealed
    # payload only when present so old packet digests remain reproducible.
    if "coordination_intent_id" in packet:
        identity["coordination_intent_id"] = packet.get("coordination_intent_id")
    return identity


def compute_payload_digest(packet: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload_identity(packet))).hexdigest()


def receiver_identity(target: Mapping[str, Any]) -> str:
    return _canonical_json(target).decode("utf-8")


def compute_route_id(packet: Mapping[str, Any]) -> str:
    """Use the same canonical route identity shape as Clay live_reentry_delivery_atomicity.route_id."""
    route_packet = {
        "decision": str(packet.get("action_class") or ""),
        "message_kind": MESSAGE_KIND,
        "payload_digest": str(packet.get("payload_digest") or ""),
        "receiver": receiver_identity(packet.get("target") or {}),
        "run_id": str(packet.get("packet_id") or ""),
    }
    return hashlib.sha256(_canonical_json(route_packet)).hexdigest()


def validate_packet(packet: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_PACKET_FIELDS - set(packet))
    if missing:
        raise PacketError(f"missing required fields: {', '.join(missing)}")
    if packet.get("schema") != PACKET_SCHEMA:
        raise PacketError(f"schema must be {PACKET_SCHEMA}")
    for field in ("packet_id", "route_id", "nonce", "payload_digest", "architect_id", "project", "objective"):
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            raise PacketError(f"{field} must be a non-empty string")
    if "coordination_intent_id" in packet:
        _validate_coordination_intent_id(packet["coordination_intent_id"])
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
    for field in ("credit_authority", "mutation_authority", "runtime_dispatch_authority", "effect_authority"):
        if packet.get(field) is not False:
            raise PacketError(f"{field} must be false in Architect coordination packets")
    if packet["payload_digest"] != compute_payload_digest(packet):
        raise PacketError("payload_digest mismatch")
    if packet["route_id"] != compute_route_id(packet):
        raise PacketError("route_id mismatch")


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
    disposition: str | None = None,
    *,
    reason: str,
    authority_head: str,
    observed_at: datetime | None = None,
    event_head_ref: str | None = None,
    active_pointer_ref: str | None = None,
    now: datetime | None = None,
    seen_nonces: Iterable[str] = (),
    superseded_packet_ids: Iterable[str] = (),
    authority_conflict: bool = False,
) -> dict[str, Any]:
    """Create ACK evidence from the deterministic packet classifier.

    ``disposition`` is retained only as a backwards-compatible expected-value
    assertion. It never selects the emitted ACK disposition. If supplied and it
    disagrees with deterministic classification, ACK creation fails closed.
    """
    classification_time = (now or observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    derived_disposition = packet_disposition(
        packet,
        worker_context,
        now=classification_time,
        seen_nonces=seen_nonces,
        superseded_packet_ids=superseded_packet_ids,
        authority_conflict=authority_conflict,
    )
    if disposition is not None:
        if disposition not in DISPOSITIONS:
            raise PacketError("invalid expected disposition")
        if disposition != derived_disposition:
            raise PacketError(
                f"expected disposition {disposition} does not match deterministic disposition {derived_disposition}"
            )

    observed = (observed_at or classification_time).astimezone(timezone.utc)
    packet_bytes = len(_dump(packet).encode("utf-8"))
    stable = "|".join(
        str(x or "")
        for x in (
            packet.get("route_id"),
            worker_context.get("worker_id"),
            worker_context.get("claim_id"),
            derived_disposition,
            observed.isoformat(),
        )
    )
    ack_id = "AWA-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]
    return {
        "schema": ACK_SCHEMA,
        "ack_id": ack_id,
        "packet_id": packet.get("packet_id"),
        "route_id": packet.get("route_id"),
        "nonce": packet.get("nonce"),
        "payload_digest": packet.get("payload_digest"),
        "worker_id": worker_context.get("worker_id"),
        "worker_lane": worker_context.get("worker_lane"),
        "workpackage_id": worker_context.get("workpackage_id"),
        "generation": worker_context.get("generation"),
        "claim_id": worker_context.get("claim_id"),
        "observed_at": _format_time(observed),
        "disposition": derived_disposition,
        "authority_head": authority_head,
        "event_head_ref": event_head_ref,
        "active_pointer_ref": active_pointer_ref,
        "reason": reason,
        "context_bytes_injected": packet_bytes if derived_disposition == "APPLIED" else 0,
        "estimated_context_tokens_injected": (packet_bytes + 3) // 4 if derived_disposition == "APPLIED" else 0,
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
    }


def _intent_event_dir(root: str | pathlib.Path, coordination_intent_id: str) -> pathlib.Path:
    return pathlib.Path(root) / coordination_intent_key(coordination_intent_id)


def _validate_intent_event(event: dict[str, Any], expected_intent_id: str, expected_sequence: int) -> None:
    required = {
        "schema",
        "coordination_intent_id",
        "intent_key",
        "sequence",
        "parent_sequence",
        "state",
        "observed_at",
        "owner_packet_id",
        "owner_route_id",
        "owner_nonce",
        "owner_payload_digest",
        "new_mutation_authority",
        "new_runtime_dispatch",
        "new_effect_authority",
        "credit_delta",
    }
    missing = sorted(required - set(event))
    if missing:
        raise PacketError(f"intent event missing required fields: {', '.join(missing)}")
    if event.get("schema") != INTENT_SCHEMA:
        raise PacketError(f"intent event schema must be {INTENT_SCHEMA}")
    intent_id = _validate_coordination_intent_id(event.get("coordination_intent_id"))
    if intent_id != expected_intent_id:
        raise PacketError("intent event coordination_intent_id mismatch")
    if event.get("intent_key") != coordination_intent_key(intent_id):
        raise PacketError("intent event intent_key mismatch")
    if event.get("sequence") != expected_sequence:
        raise PacketError("intent event sequence mismatch")
    expected_parent = expected_sequence - 1 if expected_sequence > 1 else None
    if event.get("parent_sequence") != expected_parent:
        raise PacketError("intent event parent_sequence mismatch")
    if event.get("state") not in INTENT_STATES:
        raise PacketError("unsupported intent event state")
    _parse_time(event.get("observed_at"))
    for field in ("owner_packet_id", "owner_route_id", "owner_nonce", "owner_payload_digest"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise PacketError(f"intent event {field} must be non-empty string")
    for field in ("new_mutation_authority", "new_runtime_dispatch", "new_effect_authority"):
        if event.get(field) is not False:
            raise PacketError(f"intent event {field} must be false")
    if event.get("credit_delta") != 0:
        raise PacketError("intent event credit_delta must be zero")
    if event["state"] == "ACTIVE":
        opened = _parse_time(event.get("opened_at"))
        expires = _parse_time(event.get("expires_at"))
        if expires <= opened:
            raise PacketError("intent event expires_at must be after opened_at")
    else:
        _parse_time(event.get("terminal_at"))
        if not isinstance(event.get("terminal_reason"), str) or not event["terminal_reason"].strip():
            raise PacketError("terminal intent event requires terminal_reason")


def _read_intent_chain(
    root: str | pathlib.Path,
    coordination_intent_id: str,
) -> list[tuple[pathlib.Path, dict[str, Any]]]:
    intent_id = _validate_coordination_intent_id(coordination_intent_id)
    directory = _intent_event_dir(root, intent_id)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise PacketError("intent key path exists but is not a directory")
    paths = sorted(directory.glob("*.json"))
    chain: list[tuple[pathlib.Path, dict[str, Any]]] = []
    expected = 1
    for path in paths:
        if len(path.stem) != 6 or not path.stem.isdigit() or int(path.stem) != expected:
            raise PacketError("intent event chain has non-contiguous or malformed sequence path")
        event = _load(path)
        if not isinstance(event, dict):
            raise PacketError("intent event must be a JSON object")
        _validate_intent_event(event, intent_id, expected)
        chain.append((path, event))
        expected += 1
    return chain


def claim_coordination_intent(
    root: str | pathlib.Path,
    packet: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any], pathlib.Path]:
    """Create one append-only ACTIVE intent event or reuse the active owner.

    The next event path is deterministic (six-digit sequence under a SHA-256
    intent key) and is opened with create-only semantics. Concurrent creators
    for the same intent therefore contend on the same path. In separate Git
    checkouts the same deterministic path must additionally pass the normal
    repository fast-forward/CAS boundary before becoming canonical.
    """
    validate_packet(packet)
    if "coordination_intent_id" not in packet:
        raise PacketError("new coordination packet requires coordination_intent_id")
    intent_id = _validate_coordination_intent_id(packet["coordination_intent_id"])
    observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    chain = _read_intent_chain(root, intent_id)
    if chain:
        head_path, head = chain[-1]
        if head["state"] == "ACTIVE" and observed < _parse_time(head["expires_at"]):
            return "REUSE_ACTIVE", head, head_path

    sequence = len(chain) + 1
    directory = _intent_event_dir(root, intent_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sequence:06d}.json"
    event = {
        "schema": INTENT_SCHEMA,
        "coordination_intent_id": intent_id,
        "intent_key": coordination_intent_key(intent_id),
        "sequence": sequence,
        "parent_sequence": sequence - 1 if sequence > 1 else None,
        "state": "ACTIVE",
        "observed_at": _format_time(observed),
        "opened_at": _format_time(observed),
        "expires_at": packet["expires_at"],
        "owner_packet_id": packet["packet_id"],
        "owner_route_id": packet["route_id"],
        "owner_nonce": packet["nonce"],
        "owner_payload_digest": packet["payload_digest"],
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
    }
    _validate_intent_event(event, intent_id, sequence)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_dump(event))
    except FileExistsError:
        # A same-filesystem creator won the deterministic create-only race.
        # Re-read the complete chain and reuse only a still-active winner.
        refreshed = _read_intent_chain(root, intent_id)
        if refreshed:
            winner_path, winner = refreshed[-1]
            if winner["state"] == "ACTIVE" and observed < _parse_time(winner["expires_at"]):
                return "REUSE_ACTIVE", winner, winner_path
        raise PacketError("coordination intent create-only race requires authority refresh")
    return "CLAIMED", event, path


def close_coordination_intent(
    root: str | pathlib.Path,
    coordination_intent_id: str,
    *,
    reason: str,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any], pathlib.Path]:
    """Append a TERMINAL event without rewriting the active intent history."""
    intent_id = _validate_coordination_intent_id(coordination_intent_id)
    if not isinstance(reason, str) or not reason.strip():
        raise PacketError("terminal reason must be a non-empty string")
    observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    chain = _read_intent_chain(root, intent_id)
    if not chain:
        raise PacketError("cannot terminalize an intent with no event history")
    head_path, head = chain[-1]
    if head["state"] == "TERMINAL":
        return "ALREADY_TERMINAL", head, head_path
    sequence = len(chain) + 1
    path = _intent_event_dir(root, intent_id) / f"{sequence:06d}.json"
    event = {
        "schema": INTENT_SCHEMA,
        "coordination_intent_id": intent_id,
        "intent_key": coordination_intent_key(intent_id),
        "sequence": sequence,
        "parent_sequence": sequence - 1,
        "state": "TERMINAL",
        "observed_at": _format_time(observed),
        "terminal_at": _format_time(observed),
        "terminal_reason": reason.strip(),
        "owner_packet_id": head["owner_packet_id"],
        "owner_route_id": head["owner_route_id"],
        "owner_nonce": head["owner_nonce"],
        "owner_payload_digest": head["owner_payload_digest"],
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
    }
    _validate_intent_event(event, intent_id, sequence)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_dump(event))
    except FileExistsError:
        refreshed = _read_intent_chain(root, intent_id)
        if refreshed and refreshed[-1][1]["state"] == "TERMINAL":
            return "ALREADY_TERMINAL", refreshed[-1][1], refreshed[-1][0]
        raise PacketError("coordination intent terminal race requires authority refresh")
    return "TERMINALIZED", event, path


def new_packet(
    *,
    coordination_intent_id: str,
    target: dict[str, Any],
    objective: str,
    action_class: str,
    ttl_minutes: int,
    priority: int,
    architect_id: str,
    project: str,
    constraints: list[str],
    evidence_refs: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    if ttl_minutes <= 0:
        raise PacketError("ttl_minutes must be > 0")
    intent_id = _validate_coordination_intent_id(coordination_intent_id)
    issued = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    packet_uuid = uuid.uuid4().hex
    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "packet_id": f"AWP-{issued.strftime('%Y%m%dT%H%M%SZ')}-{packet_uuid[:12]}",
        "route_id": "PENDING",
        "nonce": packet_uuid,
        "payload_digest": "PENDING",
        "issued_at": _format_time(issued),
        "expires_at": _format_time(issued + timedelta(minutes=ttl_minutes)),
        "architect_id": architect_id,
        "project": project,
        "priority": priority,
        "action_class": action_class,
        "target": target,
        "objective": objective,
        "constraints": constraints,
        "expected_output": {
            "ack_required": True,
            "classification_required": True,
            "result_summary_required": True,
            "telemetry_required": True,
        },
        "evidence_refs": evidence_refs,
        "supersedes_packet_ids": [],
        "coordination_intent_id": intent_id,
        "credit_authority": False,
        "mutation_authority": False,
        "runtime_dispatch_authority": False,
        "effect_authority": False,
    }
    packet["payload_digest"] = compute_payload_digest(packet)
    packet["route_id"] = compute_route_id(packet)
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
    now = _parse_time(args.now) if args.now else None
    try:
        ack = make_ack(
            packet,
            context,
            args.disposition,
            reason=args.reason,
            authority_head=args.authority_head,
            event_head_ref=args.event_head_ref,
            active_pointer_ref=args.active_pointer_ref,
            now=now,
            seen_nonces=_read_string_set(args.seen_nonces),
            superseded_packet_ids=_read_string_set(args.superseded_packet_ids),
            authority_conflict=args.authority_conflict,
        )
    except PacketError as exc:
        print(f"ACK_REJECTED: {exc}", file=sys.stderr)
        return 2
    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.output).write_text(_dump(ack), encoding="utf-8")
    print(args.output)
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    target = json.loads(args.target_json)
    now = _parse_time(args.now) if args.now else None
    packet = new_packet(
        coordination_intent_id=args.coordination_intent_id,
        target=target,
        objective=args.objective,
        action_class=args.action_class,
        ttl_minutes=args.ttl_minutes,
        priority=args.priority,
        architect_id=args.architect_id,
        project=args.project,
        constraints=args.constraint or [],
        evidence_refs=args.evidence_ref or [],
        now=now,
    )
    disposition, event, _event_path = claim_coordination_intent(args.intent_root, packet, now=now)
    if disposition == "REUSE_ACTIVE":
        print(
            _dump(
                {
                    "creation_disposition": disposition,
                    "coordination_intent_id": packet["coordination_intent_id"],
                    "owner_packet_id": event["owner_packet_id"],
                    "owner_route_id": event["owner_route_id"],
                    "credit_delta": 0,
                }
            ),
            end="",
        )
        return 3

    text = _dump(packet)
    if args.output:
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except Exception:
            # Preserve the failed creation causally; do not leave a durable
            # active intent pointing at a packet file we failed to materialize.
            close_coordination_intent(
                args.intent_root,
                packet["coordination_intent_id"],
                reason="PACKET_OUTPUT_WRITE_FAILED",
                now=now,
            )
            raise
        print(args.output)
    else:
        print(text, end="")
    return 0


def cmd_close_intent(args: argparse.Namespace) -> int:
    now = _parse_time(args.now) if args.now else None
    disposition, event, path = close_coordination_intent(
        args.intent_root,
        args.coordination_intent_id,
        reason=args.reason,
        now=now,
    )
    print(
        _dump(
            {
                "disposition": disposition,
                "coordination_intent_id": event["coordination_intent_id"],
                "sequence": event["sequence"],
                "event_path": str(path),
                "credit_delta": 0,
            }
        ),
        end="",
    )
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
    p.add_argument(
        "--disposition",
        choices=sorted(DISPOSITIONS),
        help="optional expected disposition assertion; emitted disposition is always derived deterministically",
    )
    p.add_argument("--reason", required=True)
    p.add_argument("--authority-head", required=True)
    p.add_argument("--event-head-ref")
    p.add_argument("--active-pointer-ref")
    p.add_argument("--now")
    p.add_argument("--seen-nonces")
    p.add_argument("--superseded-packet-ids")
    p.add_argument("--authority-conflict", action="store_true")
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("new")
    p.add_argument("--coordination-intent-id", required=True)
    p.add_argument("--intent-root", default="coordination/architect_intents")
    p.add_argument("--target-json", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--action-class", choices=sorted(ACTION_CLASSES), default="COORDINATION_ONLY")
    p.add_argument("--ttl-minutes", type=int, default=120)
    p.add_argument("--priority", type=int, default=50)
    p.add_argument("--architect-id", default="persistent-architect")
    p.add_argument("--project", default="frankenstein-2.0")
    p.add_argument("--constraint", action="append")
    p.add_argument("--evidence-ref", action="append")
    p.add_argument("--now")
    p.add_argument("--output")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("close-intent")
    p.add_argument("--coordination-intent-id", required=True)
    p.add_argument("--intent-root", default="coordination/architect_intents")
    p.add_argument("--reason", required=True)
    p.add_argument("--now")
    p.set_defaults(func=cmd_close_intent)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "ttl_minutes", 1) <= 0:
        parser.error("--ttl-minutes must be > 0")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
