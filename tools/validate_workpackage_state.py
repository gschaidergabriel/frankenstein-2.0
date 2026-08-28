#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 machine-readable workpackage state.

Scope is source/continuity metadata only. This validator never grants cognitive-runtime,
GRID10, provider, VPS, effect, training, or whole-system acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO = "gschaidergabriel/frankenstein-2.0"
CONTRACT_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE_CONSISTENCY_CONTRACT/v1"
STATE_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE/v1"
CLAIM_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_CLAIM/v1"
RECON_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1"
WP = re.compile(r"^F2-WP-[0-9]+$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
CONTRACT_REL = Path("workpackages/WORKPACKAGE_STATE_CONSISTENCY_CONTRACT_V1.json")


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _string(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field}: non-empty string required")
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: unreadable JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{path}: top-level object required")
    return value


def load_contract(root: Path) -> dict[str, Any]:
    contract = load_json(root / CONTRACT_REL)
    _require(contract.get("schema") == CONTRACT_SCHEMA, "contract schema mismatch")
    _require(contract.get("canonical_repository") == REPO, "contract canonical_repository mismatch")
    _require(contract.get("canonical_state_schema") == STATE_SCHEMA, "contract state schema mismatch")
    for field in ("compatible_active_pointer_schemas", "terminal_states", "state_values"):
        value = contract.get(field)
        _require(isinstance(value, list) and value and all(isinstance(x, str) and x for x in value),
                 f"contract {field} must be non-empty string list")
    _string(contract.get("active_state"), "contract.active_state")
    return contract


def validate_state(state: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    state_values = set((contract or {}).get("state_values") or [
        "NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"
    ])
    _require(state.get("schema") == STATE_SCHEMA, "state schema mismatch")
    _require(state.get("canonical_repository") == REPO, "state canonical_repository mismatch")
    generation = state.get("generation")
    _require(type(generation) is int and generation >= 1, "state generation must be integer >= 1")
    workpackages = state.get("workpackages")
    _require(isinstance(workpackages, dict), "state workpackages object required")
    for workpackage_id, entry in workpackages.items():
        _require(isinstance(workpackage_id, str) and bool(WP.fullmatch(workpackage_id)),
                 f"malformed state workpackage id: {workpackage_id}")
        _require(isinstance(entry, dict), f"state entry must be object: {workpackage_id}")
        status = entry.get("status")
        _require(status in state_values, f"invalid state status for {workpackage_id}: {status}")
        evidence = entry.get("evidence")
        _require(isinstance(evidence, list) and all(isinstance(x, str) and x.strip() for x in evidence),
                 f"state evidence must be string list: {workpackage_id}")
        if status == "ACCEPTED_AT_SCOPE":
            _require(bool(evidence), f"ACCEPTED_AT_SCOPE requires evidence: {workpackage_id}")
    return workpackages


def _claims_by_id(root: Path) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    directory = root / "workpackages" / "claims"
    _require(directory.is_dir(), "workpackages/claims directory missing")
    for path in sorted(directory.glob("*.json")):
        claim = load_json(path)
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            continue  # historical/noncanonical objects are not selectable by an active pointer
        _require(claim_id not in claims, f"duplicate claim_id: {claim_id}")
        claims[claim_id] = claim
    return claims


def _bind_claim(pointer: dict[str, Any], claim: dict[str, Any]) -> None:
    _require(claim.get("schema") == CLAIM_SCHEMA, "claim schema mismatch")
    for field in ("workpackage_id", "generation", "claim_id"):
        _require(claim.get(field) == pointer.get(field), f"claim/pointer identity mismatch: {field}")
    # Historical worker spellings are provenance; exact worker identity is required when present on both.
    if "worker_id" in claim and "worker_id" in pointer:
        _require(claim.get("worker_id") == pointer.get("worker_id"), "claim/pointer identity mismatch: worker_id")
    # CLAIM_PROTOCOL.md does not require a trigger field on every admitted v1 claim.
    # Preserve compatibility for claims that omit it, while fail-closing any explicit
    # trigger value that would bind this Triggerword-4 repository state to another trigger.
    if "trigger" in claim:
        _require(claim.get("trigger") == "4", "claim trigger must be '4' when present")


def _reconciliation_terminal_state(reconciliation: dict[str, Any]) -> str:
    # Newer reconciliations use terminal_state. One admitted legacy generation used state.
    # If terminal_state exists it remains authoritative even when a legacy descriptive state
    # (for example SUPERSEDED_DUPLICATE) is also present.
    if "terminal_state" in reconciliation:
        return _string(reconciliation.get("terminal_state"), "reconciliation.terminal_state")
    return _string(reconciliation.get("state"), "reconciliation.state")


def _matching_reconciliations(root: Path, pointer: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    wp_id = pointer["workpackage_id"]
    directory = root / "workpackages" / "reconciliations" / wp_id
    if not directory.is_dir():
        return []
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json")):
        reconciliation = load_json(path)
        if reconciliation.get("schema") != RECON_SCHEMA:
            continue
        try:
            terminal_state = _reconciliation_terminal_state(reconciliation)
        except ValidationError:
            continue
        if (
            reconciliation.get("workpackage_id") == wp_id
            and reconciliation.get("generation") == pointer.get("generation")
            and reconciliation.get("claim_id") == pointer.get("claim_id")
            and terminal_state == pointer.get("state")
        ):
            matches.append((path, reconciliation))
    return matches


def _bind_reconciliation(pointer: dict[str, Any], reconciliation: dict[str, Any]) -> None:
    _require(reconciliation.get("schema") == RECON_SCHEMA, "reconciliation schema mismatch")
    for field in ("workpackage_id", "generation", "claim_id"):
        _require(reconciliation.get(field) == pointer.get(field),
                 f"reconciliation/pointer identity mismatch: {field}")
    if "worker_id" in reconciliation and "worker_id" in pointer:
        _require(reconciliation.get("worker_id") == pointer.get("worker_id"),
                 "reconciliation/pointer identity mismatch: worker_id")
    _require(_reconciliation_terminal_state(reconciliation) == pointer.get("state"),
             "reconciliation terminal_state mismatch")

    # Current receipts use the explicit boolean guard. Older admitted reconciliations used
    # whole_system_credit: 0. Preserve fail-closed semantics: exactly one explicit zero/false
    # representation is required; absence, truthy acceptance, or nonzero credit is rejected.
    if "whole_system_acceptance" in reconciliation:
        _require(reconciliation.get("whole_system_acceptance") is False,
                 "component reconciliation must not assert whole-system acceptance")
    else:
        _require(reconciliation.get("whole_system_credit") == 0,
                 "component reconciliation requires explicit zero whole-system credit")


def validate_pointer(
    *,
    filename_stem: str,
    pointer: dict[str, Any],
    claim: dict[str, Any],
    state_entry: dict[str, Any] | None,
    contract: dict[str, Any] | None = None,
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compatible_schemas = set((contract or {}).get("compatible_active_pointer_schemas") or [
        "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1",
        "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1",
        "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_POINTER/v1",
    ])
    active_state = (contract or {}).get("active_state", "ACTIVE")
    terminal_values = set((contract or {}).get("terminal_states") or [
        "ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"
    ])
    state_values = set((contract or {}).get("state_values") or [
        "NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"
    ])

    _require(pointer.get("schema") in compatible_schemas,
             f"active pointer schema not contract-admitted: {pointer.get('schema')}")
    workpackage_id = _string(pointer.get("workpackage_id"), "pointer.workpackage_id")
    _require(bool(WP.fullmatch(workpackage_id)), "pointer workpackage_id malformed")
    _require(filename_stem == workpackage_id, "active filename/workpackage mismatch")
    _require(isinstance(state_entry, dict), "active pointer workpackage absent from STATE")

    generation = pointer.get("generation")
    _require(type(generation) is int and generation >= 1, "pointer generation must be integer >= 1")
    _string(pointer.get("claim_id"), "pointer.claim_id")
    _string(pointer.get("worker_id"), "pointer.worker_id")
    base_commit = pointer.get("base_commit")
    _require(isinstance(base_commit, str) and bool(SHA40.fullmatch(base_commit)),
             "pointer base_commit malformed")
    _bind_claim(pointer, claim)

    pointer_state = pointer.get("state")
    _require(pointer_state == active_state or pointer_state in terminal_values,
             f"invalid active pointer state: {pointer_state}")
    broad_status = state_entry.get("status")
    _require(broad_status in state_values, f"invalid broad workpackage status: {broad_status}")

    if pointer_state == active_state:
        _require(broad_status not in {"NOT_STARTED", "ACCEPTED_AT_SCOPE"},
                 f"ACTIVE pointer requires nonterminal broad state, got {broad_status}")
        _require(reconciliation is None, "ACTIVE pointer must not bind terminal reconciliation")
    else:
        _require(reconciliation is not None, "terminal active pointer requires reconciliation")
        _bind_reconciliation(pointer, reconciliation)
        if pointer_state == "ACCEPTED":
            broader = reconciliation.get("broader_workpackage_status")
            if broader == "IN_PROGRESS":
                _require(broad_status == "IN_PROGRESS",
                         "scoped ACCEPTED reconciliation requires broad IN_PROGRESS")
            elif broader == "ACCEPTED_AT_SCOPE":
                _require(broad_status == "ACCEPTED_AT_SCOPE",
                         "terminal ACCEPTED reconciliation requires broad ACCEPTED_AT_SCOPE")

    return {
        "workpackage_id": workpackage_id,
        "generation": generation,
        "claim_id": pointer["claim_id"],
        "pointer_schema": pointer["schema"],
        "pointer_state": pointer_state,
        "broad_status": broad_status,
        "reconciliation_bound": reconciliation is not None,
    }


def validate_repository(root: Path) -> dict[str, Any]:
    contract = load_contract(root)
    state = load_json(root / "workpackages" / "STATE.json")
    workpackages = validate_state(state, contract)
    active_dir = root / "workpackages" / "active"
    _require(active_dir.is_dir(), "workpackages/active directory missing")
    claims = _claims_by_id(root)

    # ACCEPTED_AT_SCOPE is only meaningful with repository-local evidence that actually exists.
    for workpackage_id, entry in workpackages.items():
        if entry.get("status") == "ACCEPTED_AT_SCOPE":
            evidence = entry["evidence"]
            _require(any((root / item).exists() for item in evidence),
                     f"ACCEPTED_AT_SCOPE has no existing repository-local evidence: {workpackage_id}")

    validated: list[dict[str, Any]] = []
    for path in sorted(active_dir.glob("*.json")):
        pointer = load_json(path)
        claim_id = _string(pointer.get("claim_id"), f"{path}.claim_id")
        claim = claims.get(claim_id)
        _require(claim is not None, f"{path}: no matching claim object for {claim_id}")
        reconciliation = None
        if pointer.get("state") in set(contract["terminal_states"]):
            matches = _matching_reconciliations(root, pointer)
            _require(len(matches) == 1,
                     f"{path}: terminal pointer requires exactly one matching reconciliation; found {len(matches)}")
            reconciliation = matches[0][1]
        validated.append(validate_pointer(
            filename_stem=path.stem,
            pointer=pointer,
            claim=claim,
            state_entry=workpackages.get(pointer.get("workpackage_id")),
            contract=contract,
            reconciliation=reconciliation,
        ))

    return {
        "pass": True,
        "scope": contract.get("scope"),
        "runtime_credit_granted": 0,
        "whole_system_acceptance": False,
        "state_generation": state["generation"],
        "active_pointers_validated": len(validated),
        "validated": validated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        result = validate_repository(args.root.resolve())
    except ValidationError as exc:
        print(json.dumps({"pass": False, "error": str(exc), "runtime_credit_granted": 0}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
