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
            continue
        _require(claim_id not in claims, f"duplicate claim_id: {claim_id}")
        claims[claim_id] = claim
    return claims


def _bind_claim(pointer: dict[str, Any], claim: dict[str, Any]) -> None:
    _require(claim.get("schema") == CLAIM_SCHEMA, "claim schema mismatch")
    for field in ("workpackage_id", "generation", "claim_id"):
        _require(claim.get(field) == pointer.get(field), f"claim/pointer identity mismatch: {field}")
    if "worker_id" in claim and "worker_id" in pointer:
        _require(claim.get("worker_id") == pointer.get("worker_id"), "claim/pointer identity mismatch: worker_id")
    if "trigger" in claim:
        _require(claim.get("trigger") == "4", "claim trigger must be '4' when present")


def _reconciliation_terminal_state(reconciliation: dict[str, Any]) -> str:
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


def _same_reconciliation_identity(lhs: dict[str, Any], rhs: dict[str, Any]) -> bool:
    return (
        lhs.get("schema") == RECON_SCHEMA
        and rhs.get("schema") == RECON_SCHEMA
        and lhs.get("workpackage_id") == rhs.get("workpackage_id")
        and lhs.get("generation") == rhs.get("generation")
        and lhs.get("claim_id") == rhs.get("claim_id")
        and _reconciliation_terminal_state(lhs) == _reconciliation_terminal_state(rhs)
    )


def _select_terminal_reconciliation(
    root: Path,
    matches: list[tuple[Path, dict[str, Any]]],
    *,
    context: str,
) -> dict[str, Any]:
    """Select one append-only terminal reconciliation without accepting parallel authorities.

    A single matching reconciliation keeps historical behavior. Multiple same-identity
    reconciliations are admitted only when explicit parent_reconciliation_ref links form one
    acyclic chain with exactly one leaf. A parent outside the same-identity match set may be
    an older-generation lineage predecessor, but it must exist and must not secretly be an
    omitted same-identity reconciliation.
    """
    _require(bool(matches), f"{context}: terminal pointer requires a matching reconciliation")
    if len(matches) == 1:
        return matches[0][1]

    by_ref: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path, reconciliation in matches:
        try:
            ref = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValidationError(f"{context}: reconciliation path escapes repository root: {path}") from exc
        _require(ref not in by_ref, f"{context}: duplicate reconciliation path in match set: {ref}")
        by_ref[ref] = (path, reconciliation)

    sample = matches[0][1]
    parent_of: dict[str, str] = {}
    for ref, (_, reconciliation) in by_ref.items():
        parent_ref = reconciliation.get("parent_reconciliation_ref")
        _require(isinstance(parent_ref, str) and bool(parent_ref.strip()),
                 f"{context}: multiple matching reconciliations require explicit parent_reconciliation_ref: {ref}")
        parent_ref = parent_ref.strip()
        if parent_ref in by_ref:
            parent_of[ref] = parent_ref
            continue

        external_parent_path = root / parent_ref
        _require(external_parent_path.is_file(),
                 f"{context}: reconciliation chain references unknown parent: {parent_ref}")
        external_parent = load_json(external_parent_path)
        _require(not _same_reconciliation_identity(sample, external_parent),
                 f"{context}: same-identity parent omitted from reconciliation match set: {parent_ref}")

    for start in by_ref:
        seen: set[str] = set()
        current = start
        while current in parent_of:
            _require(current not in seen, f"{context}: reconciliation parent cycle detected")
            seen.add(current)
            current = parent_of[current]

    internal_parents = set(parent_of.values())
    leaves = [ref for ref in by_ref if ref not in internal_parents]
    _require(len(leaves) == 1,
             f"{context}: multiple matching reconciliations do not form one unique append-only chain leaf; found {len(leaves)}")
    return by_ref[leaves[0]][1]


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
            reconciliation = _select_terminal_reconciliation(root, matches, context=str(path))
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
