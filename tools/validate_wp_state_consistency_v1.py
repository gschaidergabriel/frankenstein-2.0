#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 workpackage state/claim generations.

This is the dedicated generation-consistency view used by F2-WP-002 CI. Pointer
terminality is authoritative for claim-generation closure; broad STATE status may
remain IN_PROGRESS for a narrower accepted generation when a matching reconciliation
explicitly records that broader status.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ACTIVE_RE = re.compile(r"^F2-WP-(\d+)$")
CLAIM_FILE_RE = re.compile(r"^(F2-WP-\d+)_G(\d+)_([^/]+)\.json$")
ALLOWED_STATES = {"NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}
CONTRACT_REL = Path("workpackages/WORKPACKAGE_STATE_CONSISTENCY_CONTRACT_V1.json")
CONTRACT_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE_CONSISTENCY_CONTRACT/v1"
RECON_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1"


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"expected object: {path}")
    return value


def require(obj: dict, key: str, path: Path):
    if key not in obj:
        raise ValidationError(f"missing {key!r}: {path}")
    return obj[key]


def _load_contract(root: Path) -> tuple[str, set[str]]:
    path = root / CONTRACT_REL
    contract = load_json(path)
    if contract.get("schema") != CONTRACT_SCHEMA:
        raise ValidationError(f"contract schema mismatch: {contract.get('schema')!r}")
    active_state = require(contract, "active_state", path)
    terminal_states = require(contract, "terminal_states", path)
    if not isinstance(active_state, str) or not active_state:
        raise ValidationError("contract active_state must be a non-empty string")
    if not isinstance(terminal_states, list) or not terminal_states or not all(
        isinstance(item, str) and item for item in terminal_states
    ):
        raise ValidationError("contract terminal_states must be a non-empty string list")
    return active_state, set(terminal_states)


def _bind_terminal_reconciliation(
    root: Path,
    *,
    active: dict,
    claim: dict,
    workpackage: str,
    generation: int,
    claim_id: str,
    pointer_state: str,
    state_status: str,
) -> str:
    reconciliation = active.get("reconciliation_ref") or claim.get("reconciliation_ref")
    if not isinstance(reconciliation, str) or not reconciliation:
        raise ValidationError("terminal pointer requires reconciliation_ref")
    recon_path = root / reconciliation
    if not recon_path.is_file():
        raise ValidationError(f"terminal reconciliation file missing: {reconciliation}")
    recon = load_json(recon_path)
    if recon.get("schema") != RECON_SCHEMA:
        raise ValidationError("terminal reconciliation schema mismatch")
    expected = {
        "workpackage_id": workpackage,
        "generation": generation,
        "claim_id": claim_id,
        "terminal_state": pointer_state,
    }
    for field, value in expected.items():
        if recon.get(field) != value:
            raise ValidationError(f"terminal reconciliation mismatch: {field}")

    if "whole_system_acceptance" in recon:
        if recon.get("whole_system_acceptance") is not False:
            raise ValidationError("terminal reconciliation must not assert whole-system acceptance")
    elif recon.get("whole_system_credit") != 0:
        raise ValidationError("terminal reconciliation requires explicit zero whole-system credit")

    if pointer_state == "ACCEPTED":
        broader = recon.get("broader_workpackage_status")
        if broader not in {"IN_PROGRESS", "ACCEPTED_AT_SCOPE"}:
            raise ValidationError("ACCEPTED reconciliation requires explicit broader_workpackage_status")
        if state_status != broader:
            raise ValidationError(
                f"ACCEPTED reconciliation/state mismatch: reconciliation={broader} STATE={state_status}"
            )
    return reconciliation


def validate(root: Path, workpackage: str) -> list[str]:
    m = ACTIVE_RE.fullmatch(workpackage)
    if not m:
        raise ValidationError(f"invalid workpackage id: {workpackage}")

    state_path = root / "workpackages" / "STATE.json"
    active_path = root / "workpackages" / "active" / f"{workpackage}.json"
    state = load_json(state_path)
    active = load_json(active_path)
    active_state, terminal_states = _load_contract(root)

    states = require(state, "workpackages", state_path)
    if not isinstance(states, dict) or workpackage not in states:
        raise ValidationError(f"workpackage absent from STATE.json: {workpackage}")
    state_row = states[workpackage]
    if not isinstance(state_row, dict):
        raise ValidationError(f"invalid STATE row: {workpackage}")

    if require(active, "workpackage_id", active_path) != workpackage:
        raise ValidationError("active filename/workpackage_id mismatch")
    generation = require(active, "generation", active_path)
    claim_id = require(active, "claim_id", active_path)
    pointer_state = require(active, "state", active_path)
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise ValidationError("generation must be a positive integer")
    if not isinstance(claim_id, str) or not claim_id:
        raise ValidationError("claim_id must be a non-empty string")
    if pointer_state != active_state and pointer_state not in terminal_states:
        raise ValidationError(f"unsupported pointer state: {pointer_state}")

    claim_dir = root / "workpackages" / "claims"
    candidates = []
    for path in claim_dir.glob(f"{workpackage}_G{generation}_*.json"):
        match = CLAIM_FILE_RE.fullmatch(path.name)
        if match:
            candidates.append(path)
    if not candidates:
        raise ValidationError(f"no claim file for {workpackage} generation {generation}")

    matching = None
    claim = None
    for path in sorted(candidates):
        candidate = load_json(path)
        if candidate.get("claim_id") == claim_id:
            matching = path
            claim = candidate
            break
    if matching is None or claim is None:
        raise ValidationError(f"active claim_id has no matching claim file: {claim_id}")

    filename_match = CLAIM_FILE_RE.fullmatch(matching.name)
    assert filename_match
    if filename_match.group(1) != workpackage:
        raise ValidationError("claim filename/workpackage mismatch")
    if int(filename_match.group(2)) != generation:
        raise ValidationError("claim filename/generation mismatch")

    for field in ("workpackage_id", "generation", "claim_id", "worker_id", "base_commit"):
        if require(active, field, active_path) != require(claim, field, matching):
            raise ValidationError(f"active/claim mismatch: {field}")

    state_status = require(state_row, "status", state_path)
    claim_status = require(claim, "status", matching)
    if state_status not in ALLOWED_STATES:
        raise ValidationError(f"unsupported STATE status: {state_status}")

    reconciliation = None
    if pointer_state == active_state:
        if state_status in {"NOT_STARTED", "ACCEPTED_AT_SCOPE"}:
            raise ValidationError(f"ACTIVE pointer incompatible with STATE status: {state_status}")
        if str(claim_status).startswith("ACCEPTED"):
            raise ValidationError("ACTIVE pointer cannot point at terminal claim")
        if active.get("reconciliation_ref"):
            raise ValidationError("ACTIVE pointer must not carry reconciliation_ref")
    else:
        reconciliation = _bind_terminal_reconciliation(
            root,
            active=active,
            claim=claim,
            workpackage=workpackage,
            generation=generation,
            claim_id=claim_id,
            pointer_state=pointer_state,
            state_status=state_status,
        )
        if state_status == "ACCEPTED_AT_SCOPE":
            evidence = state_row.get("evidence")
            if not isinstance(evidence, list) or not evidence or not all(
                isinstance(x, str) and x for x in evidence
            ):
                raise ValidationError("ACCEPTED_AT_SCOPE requires non-empty evidence list")

    lines = [
        f"PASS workpackage={workpackage}",
        f"generation={generation}",
        f"claim={claim_id}",
        f"state={state_status}",
        f"pointer_state={pointer_state}",
        f"claim_file={matching.relative_to(root)}",
    ]
    if reconciliation:
        lines.append(f"reconciliation={reconciliation}")
    lines.append("runtime_credit=0")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("workpackage")
    args = parser.parse_args()
    try:
        for line in validate(args.root.resolve(), args.workpackage):
            print(line)
        return 0
    except ValidationError as exc:
        print(f"FAIL_CLOSED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
