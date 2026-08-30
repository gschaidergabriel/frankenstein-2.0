#!/usr/bin/env python3
"""Append-only creation-dedup fence for noncanonical Architect coordination intents.

This module is deliberately separate from packet delivery idempotency. Packet
nonce/route identity still belongs to ``architect_packet.py`` and Clay delivery
atomicity. The intent chain only prevents concurrent Architect reentries from
creating multiple active coordination packets for one explicit stable intent.

Repository safety model:
- intent identity is caller-supplied and deterministic (never inferred by an LLM);
- each intent maps to a deterministic hash directory;
- reservation/terminal records are immutable, append-only sequence files;
- creation uses local O_EXCL semantics;
- the reservation event and packet are committed atomically by the caller;
- publication uses the repository's existing non-force Git CAS/fast-forward law;
- a CAS loser refreshes and resolves the now-current intent chain.

These records grant no mutation, runtime, effect, product, or training authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from tools.coordination.architect_packet import PacketError, validate_packet

EVENT_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT_EVENT/v1"
RESULT_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT_RESULT/v1"
EVENT_STATES = {"ACTIVE", "TERMINAL"}
RESERVATION_DISPOSITIONS = {
    "RESERVED",
    "REUSE_ACTIVE",
    "REJECT_STALE_PACKET",
    "CONCURRENCY_RETRY",
}
_SEQUENCE_RE = re.compile(r"^[0-9]{6}\.json$")


class IntentError(ValueError):
    pass


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IntentError("timestamp must be a non-empty RFC3339 string")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise IntentError(f"invalid RFC3339 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise IntentError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_intent_id(intent_id: str) -> None:
    if not isinstance(intent_id, str) or not intent_id.strip():
        raise IntentError("coordination_intent_id must be a non-empty string")
    if intent_id != intent_id.strip():
        raise IntentError("coordination_intent_id must not contain leading/trailing whitespace")
    if len(intent_id.encode("utf-8")) > 512:
        raise IntentError("coordination_intent_id exceeds 512 UTF-8 bytes")


def intent_key(intent_id: str) -> str:
    validate_intent_id(intent_id)
    return hashlib.sha256(intent_id.encode("utf-8")).hexdigest()


def intent_directory(events_root: str | pathlib.Path, intent_id: str) -> pathlib.Path:
    return pathlib.Path(events_root) / intent_key(intent_id)


def event_digest(event: Mapping[str, Any]) -> str:
    body = dict(event)
    body.pop("event_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def validate_event(event: dict[str, Any], *, expected_intent_id: str | None = None) -> None:
    required = {
        "schema",
        "coordination_intent_id",
        "intent_key",
        "sequence",
        "state",
        "packet_id",
        "payload_digest",
        "route_id",
        "created_at",
        "expires_at",
        "parent_event_digest",
        "terminal_evidence_ref",
        "new_mutation_authority",
        "new_runtime_dispatch",
        "new_effect_authority",
        "credit_delta",
        "event_digest",
    }
    missing = sorted(required - set(event))
    if missing:
        raise IntentError(f"intent event missing fields: {', '.join(missing)}")
    if event["schema"] != EVENT_SCHEMA:
        raise IntentError(f"intent event schema must be {EVENT_SCHEMA}")
    validate_intent_id(event["coordination_intent_id"])
    if expected_intent_id is not None and event["coordination_intent_id"] != expected_intent_id:
        raise IntentError("intent event identity mismatch")
    if event["intent_key"] != intent_key(event["coordination_intent_id"]):
        raise IntentError("intent event key mismatch")
    if not isinstance(event["sequence"], int) or event["sequence"] <= 0:
        raise IntentError("intent event sequence must be positive integer")
    if event["state"] not in EVENT_STATES:
        raise IntentError("unsupported intent event state")
    for field in ("packet_id", "payload_digest", "route_id", "created_at", "expires_at"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise IntentError(f"intent event {field} must be non-empty string")
    _parse_time(event["created_at"])
    _parse_time(event["expires_at"])
    if event["parent_event_digest"] is not None and (
        not isinstance(event["parent_event_digest"], str) or len(event["parent_event_digest"]) != 64
    ):
        raise IntentError("parent_event_digest must be null or sha256 hex")
    if event["state"] == "TERMINAL":
        if not isinstance(event["terminal_evidence_ref"], str) or not event["terminal_evidence_ref"].strip():
            raise IntentError("terminal event requires terminal_evidence_ref")
    elif event["terminal_evidence_ref"] is not None:
        raise IntentError("ACTIVE event terminal_evidence_ref must be null")
    if event["new_mutation_authority"] is not False:
        raise IntentError("intent event cannot grant mutation authority")
    if event["new_runtime_dispatch"] is not False:
        raise IntentError("intent event cannot grant runtime dispatch")
    if event["new_effect_authority"] is not False:
        raise IntentError("intent event cannot grant effect authority")
    if event["credit_delta"] != 0:
        raise IntentError("intent event credit_delta must be zero")
    if event["event_digest"] != event_digest(event):
        raise IntentError("intent event digest mismatch")


def load_intent_chain(events_root: str | pathlib.Path, intent_id: str) -> list[tuple[pathlib.Path, dict[str, Any]]]:
    directory = intent_directory(events_root, intent_id)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise IntentError("intent chain path is not a directory")
    candidates = sorted(path for path in directory.iterdir() if path.is_file() and _SEQUENCE_RE.match(path.name))
    chain: list[tuple[pathlib.Path, dict[str, Any]]] = []
    previous_digest: str | None = None
    for expected_sequence, path in enumerate(candidates, start=1):
        sequence = int(path.stem)
        if sequence != expected_sequence:
            raise IntentError("intent event chain sequence gap or duplicate")
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntentError(f"cannot read intent event {path}") from exc
        validate_event(event, expected_intent_id=intent_id)
        if event["sequence"] != expected_sequence:
            raise IntentError("intent event body sequence does not match path")
        if event["parent_event_digest"] != previous_digest:
            raise IntentError("intent event parent digest mismatch")
        previous_digest = event["event_digest"]
        chain.append((path, event))
    return chain


def _new_event(
    *,
    intent_id: str,
    sequence: int,
    state: str,
    packet: dict[str, Any],
    created_at: datetime,
    parent_event_digest: str | None,
    terminal_evidence_ref: str | None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "coordination_intent_id": intent_id,
        "intent_key": intent_key(intent_id),
        "sequence": sequence,
        "state": state,
        "packet_id": packet["packet_id"],
        "payload_digest": packet["payload_digest"],
        "route_id": packet["route_id"],
        "created_at": _utc_text(created_at),
        "expires_at": packet["expires_at"],
        "parent_event_digest": parent_event_digest,
        "terminal_evidence_ref": terminal_evidence_ref,
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
        "event_digest": "PENDING",
    }
    event["event_digest"] = event_digest(event)
    validate_event(event, expected_intent_id=intent_id)
    return event


def _create_exclusive(path: pathlib.Path, content: str) -> None:
    """Publish complete content at ``path`` with create-only atomic visibility."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temp, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def _result(
    *,
    disposition: str,
    intent_id: str,
    event_path: pathlib.Path | None,
    event: dict[str, Any] | None,
    existing_event_path: pathlib.Path | None = None,
    existing_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "disposition": disposition,
        "coordination_intent_id": intent_id,
        "intent_key": intent_key(intent_id),
        "event_path": str(event_path) if event_path else None,
        "event": event,
        "existing_event_path": str(existing_event_path) if existing_event_path else None,
        "existing_event": existing_event,
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
    }


def reserve_intent(
    events_root: str | pathlib.Path,
    intent_id: str,
    packet: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reserve one active coordination intent with append-only create-only evidence."""
    validate_intent_id(intent_id)
    try:
        validate_packet(packet)
    except PacketError as exc:
        raise IntentError(f"packet invalid: {exc}") from exc
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    packet_expiry = _parse_time(packet["expires_at"])
    if current_time >= packet_expiry:
        return _result(disposition="REJECT_STALE_PACKET", intent_id=intent_id, event_path=None, event=None)

    chain = load_intent_chain(events_root, intent_id)
    latest_path, latest = chain[-1] if chain else (None, None)
    if latest is not None and latest["state"] == "ACTIVE" and current_time < _parse_time(latest["expires_at"]):
        return _result(
            disposition="REUSE_ACTIVE",
            intent_id=intent_id,
            event_path=None,
            event=None,
            existing_event_path=latest_path,
            existing_event=latest,
        )

    sequence = len(chain) + 1
    parent_digest = latest["event_digest"] if latest is not None else None
    event = _new_event(
        intent_id=intent_id,
        sequence=sequence,
        state="ACTIVE",
        packet=packet,
        created_at=current_time,
        parent_event_digest=parent_digest,
        terminal_evidence_ref=None,
    )
    path = intent_directory(events_root, intent_id) / f"{sequence:06d}.json"
    try:
        _create_exclusive(path, _dump(event))
    except FileExistsError:
        refreshed = load_intent_chain(events_root, intent_id)
        latest_path, latest = refreshed[-1] if refreshed else (None, None)
        if latest is not None and latest["state"] == "ACTIVE" and current_time < _parse_time(latest["expires_at"]):
            return _result(
                disposition="REUSE_ACTIVE",
                intent_id=intent_id,
                event_path=None,
                event=None,
                existing_event_path=latest_path,
                existing_event=latest,
            )
        return _result(
            disposition="CONCURRENCY_RETRY",
            intent_id=intent_id,
            event_path=None,
            event=None,
            existing_event_path=latest_path,
            existing_event=latest,
        )
    return _result(disposition="RESERVED", intent_id=intent_id, event_path=path, event=event)


def mark_terminal(
    events_root: str | pathlib.Path,
    intent_id: str,
    *,
    packet: dict[str, Any],
    evidence_ref: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append terminal evidence for the currently active intent reservation."""
    validate_intent_id(intent_id)
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise IntentError("terminal evidence_ref must be non-empty")
    try:
        validate_packet(packet)
    except PacketError as exc:
        raise IntentError(f"packet invalid: {exc}") from exc
    chain = load_intent_chain(events_root, intent_id)
    if not chain:
        raise IntentError("cannot terminate intent with no reservation")
    latest_path, latest = chain[-1]
    if latest["state"] != "ACTIVE":
        raise IntentError("latest intent event is already terminal")
    for field in ("packet_id", "payload_digest", "route_id"):
        if latest[field] != packet[field]:
            raise IntentError(f"terminal packet {field} does not match active reservation")

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    sequence = len(chain) + 1
    event = _new_event(
        intent_id=intent_id,
        sequence=sequence,
        state="TERMINAL",
        packet=packet,
        created_at=current_time,
        parent_event_digest=latest["event_digest"],
        terminal_evidence_ref=evidence_ref,
    )
    path = intent_directory(events_root, intent_id) / f"{sequence:06d}.json"
    try:
        _create_exclusive(path, _dump(event))
    except FileExistsError as exc:
        raise IntentError("terminal append lost create-only race; refresh and re-evaluate") from exc
    return _result(
        disposition="TERMINAL_RECORDED",
        intent_id=intent_id,
        event_path=path,
        event=event,
        existing_event_path=latest_path,
        existing_event=latest,
    )


def _load_json(path: str | pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def cmd_reserve(args: argparse.Namespace) -> int:
    packet = _load_json(args.packet)
    now = _parse_time(args.now) if args.now else None
    try:
        result = reserve_intent(args.events_root, args.intent_id, packet, now=now)
    except IntentError as exc:
        print(f"INTENT_REJECTED: {exc}", file=sys.stderr)
        return 2
    print(_dump(result), end="")
    return 0 if result["disposition"] == "RESERVED" else 3


def cmd_terminal(args: argparse.Namespace) -> int:
    packet = _load_json(args.packet)
    now = _parse_time(args.now) if args.now else None
    try:
        result = mark_terminal(
            args.events_root,
            args.intent_id,
            packet=packet,
            evidence_ref=args.evidence_ref,
            now=now,
        )
    except IntentError as exc:
        print(f"INTENT_REJECTED: {exc}", file=sys.stderr)
        return 2
    print(_dump(result), end="")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    try:
        chain = load_intent_chain(args.events_root, args.intent_id)
    except IntentError as exc:
        print(f"INTENT_REJECTED: {exc}", file=sys.stderr)
        return 2
    payload = {
        "schema": RESULT_SCHEMA,
        "coordination_intent_id": args.intent_id,
        "intent_key": intent_key(args.intent_id),
        "events": [{"path": str(path), "event": event} for path, event in chain],
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
    }
    print(_dump(payload), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    reserve = sub.add_parser("reserve")
    reserve.add_argument("--events-root", required=True)
    reserve.add_argument("--intent-id", required=True)
    reserve.add_argument("--packet", required=True)
    reserve.add_argument("--now")
    reserve.set_defaults(func=cmd_reserve)

    terminal = sub.add_parser("terminal")
    terminal.add_argument("--events-root", required=True)
    terminal.add_argument("--intent-id", required=True)
    terminal.add_argument("--packet", required=True)
    terminal.add_argument("--evidence-ref", required=True)
    terminal.add_argument("--now")
    terminal.set_defaults(func=cmd_terminal)

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--events-root", required=True)
    resolve.add_argument("--intent-id", required=True)
    resolve.set_defaults(func=cmd_resolve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
