#!/usr/bin/env python3
"""Resolve Frankenstein 2.0 workpackage state under concurrency protocol v2.

The global STATE.json is a compatibility snapshot. A validated per-workpackage
append-only event chain overrides the corresponding snapshot row. Events bind
current active-pointer/reconciliation Git blob identities so stale projections
fail closed without requiring every worker to rewrite the global snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVENT_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE_EVENT/v1"
CONTRACT_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE_VIEW_CONTRACT/v2"
CONTRACT_REL = Path("workpackages/STATE_VIEW_CONTRACT_V2.json")
STATE_REL = Path("workpackages/STATE.json")
EVENT_ROOT_REL = Path("workpackages/state_events")
ACTIVE_ROOT_REL = Path("workpackages/active")
TERMINAL_STATES = {"ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"}
BROAD_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}
WP_RE = re.compile(r"^F2-WP-\d+$")
SEQ_RE = re.compile(r"^(\d{6})\.json$")


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class EventHead:
    path: Path
    data: dict[str, Any]
    content_sha256: str


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_bytes(path))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(_read_bytes(path)).hexdigest()


def _git_blob_sha(root: Path, rel: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"HEAD:{rel.as_posix()}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValidationError(f"cannot resolve Git blob for {rel}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _require_str(obj: dict[str, Any], key: str, where: Path) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{where}: {key} must be a non-empty string")
    return value


def _require_int(obj: dict[str, Any], key: str, where: Path, *, minimum: int = 0) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValidationError(f"{where}: {key} must be integer >= {minimum}")
    return value


def _load_contract(root: Path) -> dict[str, Any]:
    path = root / CONTRACT_REL
    data = _load_json(path)
    if data.get("schema") != CONTRACT_SCHEMA:
        raise ValidationError(f"contract schema mismatch: {data.get('schema')!r}")
    return data


def load_event_chain(root: Path, workpackage_id: str) -> list[EventHead]:
    if not WP_RE.fullmatch(workpackage_id):
        raise ValidationError(f"invalid workpackage id: {workpackage_id}")
    event_dir = root / EVENT_ROOT_REL / workpackage_id
    if not event_dir.exists():
        return []
    if not event_dir.is_dir():
        raise ValidationError(f"event path is not directory: {event_dir}")

    candidates: list[tuple[int, Path]] = []
    for path in event_dir.iterdir():
        if path.name.startswith("."):
            continue
        match = SEQ_RE.fullmatch(path.name)
        if not match:
            raise ValidationError(f"non-canonical event filename: {path}")
        candidates.append((int(match.group(1)), path))
    candidates.sort()
    if not candidates:
        return []

    heads: list[EventHead] = []
    previous: EventHead | None = None
    for expected_seq, (actual_seq, path) in enumerate(candidates, start=1):
        if actual_seq != expected_seq:
            raise ValidationError(
                f"event sequence gap/branch for {workpackage_id}: expected {expected_seq:06d}, got {actual_seq:06d}"
            )
        data = _load_json(path)
        if data.get("schema") != EVENT_SCHEMA:
            raise ValidationError(f"event schema mismatch: {path}")
        if data.get("workpackage_id") != workpackage_id:
            raise ValidationError(f"event workpackage mismatch: {path}")
        if _require_int(data, "sequence", path, minimum=1) != actual_seq:
            raise ValidationError(f"event sequence field mismatch: {path}")

        content_sha = _sha256(path)
        if previous is None:
            if data.get("parent_event") is not None or data.get("parent_event_sha256") is not None:
                raise ValidationError(f"first event must have null parent: {path}")
        else:
            expected_parent = previous.path.relative_to(root).as_posix()
            if data.get("parent_event") != expected_parent:
                raise ValidationError(f"event parent path mismatch: {path}")
            if data.get("parent_event_sha256") != previous.content_sha256:
                raise ValidationError(f"event parent digest mismatch: {path}")

        broad_status = _require_str(data, "broad_status", path)
        if broad_status not in BROAD_STATUSES:
            raise ValidationError(f"unsupported broad_status {broad_status}: {path}")
        _require_int(data, "claim_generation", path, minimum=1)
        _require_str(data, "claim_id", path)
        _require_int(data, "phase", path, minimum=0)
        _require_str(data, "title", path)
        active_state = _require_str(data, "active_pointer_state", path)
        if active_state != "ACTIVE" and active_state not in TERMINAL_STATES:
            raise ValidationError(f"unsupported active_pointer_state {active_state}: {path}")
        evidence = data.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(x, str) and x for x in evidence):
            raise ValidationError(f"event evidence must be a string list: {path}")

        heads.append(EventHead(path=path, data=data, content_sha256=content_sha))
        previous = heads[-1]
    return heads


def _validate_head_bindings(root: Path, head: EventHead) -> None:
    data = head.data
    wp = data["workpackage_id"]
    active_rel = ACTIVE_ROOT_REL / f"{wp}.json"
    active_path = root / active_rel
    if not active_path.is_file():
        raise ValidationError(f"migrated workpackage missing active pointer: {active_rel}")
    active = _load_json(active_path)
    if active.get("workpackage_id") != wp:
        raise ValidationError(f"active pointer workpackage mismatch: {active_rel}")
    if active.get("generation") != data.get("claim_generation"):
        raise ValidationError(f"event/active generation mismatch: {wp}")
    if active.get("claim_id") != data.get("claim_id"):
        raise ValidationError(f"event/active claim mismatch: {wp}")
    if active.get("state") != data.get("active_pointer_state"):
        raise ValidationError(f"event/active state mismatch: {wp}")

    expected_active_blob = _require_str(data, "active_pointer_blob_sha", head.path)
    actual_active_blob = _git_blob_sha(root, active_rel)
    if actual_active_blob != expected_active_blob:
        raise ValidationError(
            f"event bound to stale active pointer blob for {wp}: expected {expected_active_blob}, got {actual_active_blob}"
        )

    if data["active_pointer_state"] in TERMINAL_STATES:
        reconciliation_ref = _require_str(data, "reconciliation_ref", head.path)
        reconciliation_rel = Path(reconciliation_ref)
        reconciliation_path = root / reconciliation_rel
        if not reconciliation_path.is_file():
            raise ValidationError(f"terminal event reconciliation missing: {reconciliation_ref}")
        expected_recon_blob = _require_str(data, "reconciliation_blob_sha", head.path)
        actual_recon_blob = _git_blob_sha(root, reconciliation_rel)
        if actual_recon_blob != expected_recon_blob:
            raise ValidationError(
                f"event bound to stale reconciliation blob for {wp}: expected {expected_recon_blob}, got {actual_recon_blob}"
            )
        recon = _load_json(reconciliation_path)
        if recon.get("workpackage_id") != wp:
            raise ValidationError(f"reconciliation workpackage mismatch: {wp}")
        if recon.get("generation") != data.get("claim_generation"):
            raise ValidationError(f"reconciliation generation mismatch: {wp}")
        if recon.get("claim_id") != data.get("claim_id"):
            raise ValidationError(f"reconciliation claim mismatch: {wp}")


def resolve_effective_state(root: Path, *, check_active: bool = False) -> dict[str, Any]:
    root = root.resolve()
    _load_contract(root)
    state = _load_json(root / STATE_REL)
    rows = state.get("workpackages")
    if not isinstance(rows, dict):
        raise ValidationError("STATE.json workpackages must be an object")

    effective_rows = dict(rows)
    migrated: dict[str, str] = {}
    event_root = root / EVENT_ROOT_REL
    if event_root.exists():
        for wp_dir in sorted(p for p in event_root.iterdir() if p.is_dir()):
            wp = wp_dir.name
            chain = load_event_chain(root, wp)
            if not chain:
                continue
            head = chain[-1]
            if check_active:
                _validate_head_bindings(root, head)
            data = head.data
            effective_rows[wp] = {
                "status": data["broad_status"],
                "phase": data["phase"],
                "title": data["title"],
                "evidence": list(data["evidence"]),
            }
            migrated[wp] = head.path.relative_to(root).as_posix()

    return {
        "schema": "FRANKENSTEIN2_EFFECTIVE_WORKPACKAGE_STATE/v2",
        "snapshot_schema": state.get("schema"),
        "snapshot_generation": state.get("generation"),
        "snapshot_path": STATE_REL.as_posix(),
        "migrated_event_heads": migrated,
        "workpackages": effective_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--workpackage")
    parser.add_argument("--check-active", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        resolved = resolve_effective_state(args.root, check_active=args.check_active)
        if args.workpackage:
            row = resolved["workpackages"].get(args.workpackage)
            if row is None:
                raise ValidationError(f"workpackage absent from effective state: {args.workpackage}")
            output: Any = {
                "workpackage_id": args.workpackage,
                "row": row,
                "event_head": resolved["migrated_event_heads"].get(args.workpackage),
            }
        else:
            output = resolved
        if args.json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            print("PASS effective workpackage state v2")
            print(f"snapshot_generation={resolved['snapshot_generation']}")
            print(f"migrated_workpackages={len(resolved['migrated_event_heads'])}")
            if args.workpackage:
                print(f"workpackage={args.workpackage}")
                print(f"status={output['row']['status']}")
                print(f"event_head={output['event_head'] or 'legacy-snapshot'}")
        return 0
    except ValidationError as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
