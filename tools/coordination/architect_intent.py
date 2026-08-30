#!/usr/bin/env python3
"""Deterministic creation-dedup fence for Architect coordination packets.

This module is coordination support only. It does not mint project mutation,
runtime, effect, provider, product, or training authority. Packet delivery
idempotency remains with the existing packet route/nonce and Clay delivery
atomicity mechanisms.

Repository concurrency law: every creator for the same explicit
``coordination_intent_id`` targets the same deterministic active-marker path.
A creator that loses the repository fast-forward/CAS race MUST refresh main and
re-run this decision; it must not force-push or commit a second active packet.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable

from tools.coordination.architect_packet import PacketError, validate_packet

INTENT_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT/v1"
INTENT_RESULT_SCHEMA = "F2_ARCHITECT_COORDINATION_INTENT_RESULT/v1"
ACTIVE_DIR = "active"
HISTORY_DIR = "history"
LOCK_DIR = ".locks"
TERMINAL_STATES = {"APPLIED", "REJECTED", "EXPIRED", "SUPERSEDED", "CLOSED"}


class IntentError(ValueError):
    pass


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IntentError("timestamp must be a non-empty RFC3339 string")
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise IntentError(f"invalid RFC3339 timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        raise IntentError("timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_intent_id(intent_id: str) -> str:
    if not isinstance(intent_id, str) or not intent_id.strip():
        raise IntentError("coordination_intent_id must be a non-empty explicit string")
    value = intent_id.strip()
    if len(value.encode("utf-8")) > 512:
        raise IntentError("coordination_intent_id exceeds 512 UTF-8 bytes")
    return value


def intent_key(intent_id: str) -> str:
    value = validate_intent_id(intent_id)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def active_marker_path(root: str | pathlib.Path, intent_id: str) -> pathlib.Path:
    return pathlib.Path(root) / ACTIVE_DIR / f"{intent_key(intent_id)}.json"


def history_marker_path(root: str | pathlib.Path, intent_id: str, packet_id: str) -> pathlib.Path:
    safe_packet = hashlib.sha256(str(packet_id).encode("utf-8")).hexdigest()
    return pathlib.Path(root) / HISTORY_DIR / intent_key(intent_id) / f"{safe_packet}.json"


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise IntentError(f"intent record must be object: {path}")
    return data


def _write_create_only(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_dump(data))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_replace(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        tmp = pathlib.Path(handle.name)
        handle.write(_dump(data))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _record_state(record: dict[str, Any], *, now: datetime, terminal_packet_ids: set[str]) -> str:
    if str(record.get("active_packet_id")) in terminal_packet_ids:
        return "TERMINAL"
    state = str(record.get("state") or "ACTIVE")
    if state in TERMINAL_STATES:
        return "TERMINAL"
    expires_at = _parse_time(str(record.get("expires_at") or ""))
    if now >= expires_at:
        return "EXPIRED"
    return "ACTIVE"


def _new_record(
    *,
    intent_id: str,
    packet: dict[str, Any],
    authority_head: str,
    claimed_at: datetime,
    supersedes_packet_id: str | None,
) -> dict[str, Any]:
    return {
        "schema": INTENT_SCHEMA,
        "coordination_intent_id": intent_id,
        "intent_key": intent_key(intent_id),
        "active_packet_id": packet["packet_id"],
        "packet_route_id": packet["route_id"],
        "packet_payload_digest": packet["payload_digest"],
        "claimed_at": _rfc3339(claimed_at),
        "expires_at": packet["expires_at"],
        "authority_head": authority_head,
        "state": "ACTIVE",
        "supersedes_packet_id": supersedes_packet_id,
        "new_mutation_authority": False,
        "new_runtime_dispatch": False,
        "new_effect_authority": False,
        "credit_delta": 0,
    }


def claim_intent(
    root: str | pathlib.Path,
    *,
    intent_id: str,
    packet: dict[str, Any],
    authority_head: str,
    now: datetime | None = None,
    terminal_packet_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Claim one active coordination intent or return the existing active owner.

    Local contenders are serialized with ``flock``. Cross-checkout contenders
    produce the same deterministic active-marker path and therefore rely on the
    repository's normal non-force fast-forward/CAS law: after a CAS loss the loser
    refreshes and calls this function again, which returns ``REUSE_ACTIVE``.
    """
    try:
        validate_packet(packet)
    except PacketError as exc:
        raise IntentError(f"packet invalid: {exc}") from exc

    intent_id = validate_intent_id(intent_id)
    observed = _now(now)
    expires = _parse_time(packet["expires_at"])
    if observed >= expires:
        raise IntentError("cannot claim intent for already-expired packet")

    root = pathlib.Path(root)
    key = intent_key(intent_id)
    lock_path = root / LOCK_DIR / f"{key}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    terminal_set = {str(x) for x in terminal_packet_ids}

    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        active_path = active_marker_path(root, intent_id)
        previous: dict[str, Any] | None = None
        previous_state: str | None = None

        if active_path.exists():
            previous = _load_json(active_path)
            previous_state = _record_state(previous, now=observed, terminal_packet_ids=terminal_set)
            if previous_state == "ACTIVE":
                return {
                    "schema": INTENT_RESULT_SCHEMA,
                    "result": "REUSE_ACTIVE",
                    "coordination_intent_id": intent_id,
                    "intent_key": key,
                    "active_packet_id": previous.get("active_packet_id"),
                    "active_marker": str(active_path),
                    "history_marker": None,
                    "authority_head": authority_head,
                    "new_mutation_authority": False,
                    "new_runtime_dispatch": False,
                    "new_effect_authority": False,
                    "credit_delta": 0,
                }

        supersedes = str(previous.get("active_packet_id")) if previous else None
        record = _new_record(
            intent_id=intent_id,
            packet=packet,
            authority_head=authority_head,
            claimed_at=observed,
            supersedes_packet_id=supersedes,
        )
        history_path = history_marker_path(root, intent_id, packet["packet_id"])
        _write_create_only(history_path, record)

        if previous is None:
            try:
                _write_create_only(active_path, record)
            except FileExistsError:
                current = _load_json(active_path)
                return {
                    "schema": INTENT_RESULT_SCHEMA,
                    "result": "CONCURRENCY_RETRY",
                    "coordination_intent_id": intent_id,
                    "intent_key": key,
                    "active_packet_id": current.get("active_packet_id"),
                    "active_marker": str(active_path),
                    "history_marker": str(history_path),
                    "authority_head": authority_head,
                    "new_mutation_authority": False,
                    "new_runtime_dispatch": False,
                    "new_effect_authority": False,
                    "credit_delta": 0,
                }
            result = "CLAIMED"
        else:
            _atomic_replace(active_path, record)
            result = "SUPERSEDED_EXPIRED" if previous_state == "EXPIRED" else "SUPERSEDED_TERMINAL"

        return {
            "schema": INTENT_RESULT_SCHEMA,
            "result": result,
            "coordination_intent_id": intent_id,
            "intent_key": key,
            "active_packet_id": packet["packet_id"],
            "active_marker": str(active_path),
            "history_marker": str(history_path),
            "authority_head": authority_head,
            "supersedes_packet_id": supersedes,
            "new_mutation_authority": False,
            "new_runtime_dispatch": False,
            "new_effect_authority": False,
            "credit_delta": 0,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="coordination/architect_packets/intents root")
    parser.add_argument("packet", help="candidate immutable packet JSON")
    parser.add_argument("--intent-id", required=True, help="explicit stable coordination boundary identity")
    parser.add_argument("--authority-head", required=True)
    parser.add_argument("--now")
    parser.add_argument("--terminal-packet-id", action="append")
    parser.add_argument("--result-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    packet = json.loads(pathlib.Path(args.packet).read_text(encoding="utf-8"))
    observed = _parse_time(args.now) if args.now else None
    result = claim_intent(
        args.root,
        intent_id=args.intent_id,
        packet=packet,
        authority_head=args.authority_head,
        now=observed,
        terminal_packet_ids=args.terminal_packet_id or (),
    )
    text = _dump(result)
    if args.result_output:
        pathlib.Path(args.result_output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.result_output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["result"] in {"CLAIMED", "SUPERSEDED_EXPIRED", "SUPERSEDED_TERMINAL"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
