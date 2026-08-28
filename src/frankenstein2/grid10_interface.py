"""Deterministic GRID10 logical-cell interface and budget ABI.

F2-WP-503 generation 1.

This module defines exactly ten logical cell slots (G1..G10), caller-supplied opaque
role labels, bounded input/output/work budgets, exact SituationFrame/policy bindings,
and deterministic accounting. It does not assign cognitive semantics to cells, call
models/tools/providers, mutate state, authorize effects/completion, or imply any physical
model/decode concurrency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

GRID10_PLAN_SCHEMA = "FRANKENSTEIN2_GRID10_INTERFACE_PLAN/v1"
GRID10_INPUT_SCHEMA = "FRANKENSTEIN2_GRID10_CELL_INPUT/v1"
GRID10_OUTPUT_SCHEMA = "FRANKENSTEIN2_GRID10_CELL_OUTPUT/v1"
GRID10_USAGE_SCHEMA = "FRANKENSTEIN2_GRID10_USAGE_RECEIPT/v1"
GRID10_CELL_IDS = tuple(f"G{i}" for i in range(1, 11))
_GRID10_CELL_SET = frozenset(GRID10_CELL_IDS)
_OUTPUT_STATUSES = frozenset(
    {"COMPLETE", "PARTIAL", "ABSTAIN", "UNKNOWN", "NOT_COMPUTED", "ERROR"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_MAX_BUDGET = 2**31 - 1


class Grid10InterfaceError(ValueError):
    """Fail-closed GRID10 ABI validation error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise Grid10InterfaceError(f"{name} must be a string")
    if not value or value != value.strip():
        raise Grid10InterfaceError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise Grid10InterfaceError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise Grid10InterfaceError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise Grid10InterfaceError(f"{name} must be a non-negative integer")
    return value


def _bounded_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_BUDGET:
        raise Grid10InterfaceError(
            f"{name} must be an integer in [{minimum}, {_MAX_BUDGET}]"
        )
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise Grid10InterfaceError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise Grid10InterfaceError(f"{name} must be an iterable of reference strings")
    cleaned = tuple(sorted({_identifier(name, value) for value in values}))
    if len(cleaned) > _MAX_REFS:
        raise Grid10InterfaceError(f"{name} exceeds {_MAX_REFS} unique references")
    return cleaned


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CellBudget:
    """Caller-supplied logical-cell interface and resource ceiling."""

    cell_id: str
    role_label: str
    max_input_refs: int
    max_output_refs: int
    max_work_units: int
    max_reentry_depth: int

    def __post_init__(self) -> None:
        if self.cell_id not in _GRID10_CELL_SET:
            raise Grid10InterfaceError(f"cell_id must be one of {GRID10_CELL_IDS}")
        object.__setattr__(self, "role_label", _identifier("role_label", self.role_label))
        object.__setattr__(
            self, "max_input_refs", _bounded_int("max_input_refs", self.max_input_refs)
        )
        object.__setattr__(
            self, "max_output_refs", _bounded_int("max_output_refs", self.max_output_refs)
        )
        object.__setattr__(
            self, "max_work_units", _bounded_int("max_work_units", self.max_work_units)
        )
        object.__setattr__(
            self,
            "max_reentry_depth",
            _bounded_int("max_reentry_depth", self.max_reentry_depth),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Grid10Plan:
    """Exact-ten-cell logical GRID plan bound to one frame and one policy identity."""

    schema: str
    plan_id: str
    cycle_id: str
    generation: int
    frame_id: str
    frame_generation: int
    frame_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    cells: tuple[CellBudget, ...]
    max_total_work_units: int
    provenance_refs: tuple[str, ...]
    classification: str = (
        "TEN_LOGICAL_CELLS_ONLY_NOT_TEN_RESIDENT_MODELS_OR_PHYSICAL_DECODERS"
    )

    def __post_init__(self) -> None:
        if self.schema != GRID10_PLAN_SCHEMA:
            raise Grid10InterfaceError("GRID10 plan schema mismatch")
        object.__setattr__(self, "plan_id", _identifier("plan_id", self.plan_id))
        object.__setattr__(self, "cycle_id", _identifier("cycle_id", self.cycle_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        object.__setattr__(self, "frame_id", _identifier("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "frame_generation",
            _generation("frame_generation", self.frame_generation),
        )
        object.__setattr__(
            self, "frame_sha256", _sha256("frame_sha256", self.frame_sha256)
        )
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(
            self,
            "policy_generation",
            _generation("policy_generation", self.policy_generation),
        )
        object.__setattr__(
            self, "policy_sha256", _sha256("policy_sha256", self.policy_sha256)
        )
        cells = tuple(self.cells)
        if len(cells) != 10 or any(type(cell) is not CellBudget for cell in cells):
            raise Grid10InterfaceError("cells must contain exactly ten CellBudget objects")
        ids = [cell.cell_id for cell in cells]
        if len(set(ids)) != 10 or set(ids) != _GRID10_CELL_SET:
            raise Grid10InterfaceError("cells must contain each logical id G1..G10 exactly once")
        by_id = {cell.cell_id: cell for cell in cells}
        object.__setattr__(self, "cells", tuple(by_id[cell_id] for cell_id in GRID10_CELL_IDS))
        object.__setattr__(
            self,
            "max_total_work_units",
            _bounded_int("max_total_work_units", self.max_total_work_units),
        )
        provenance = _refs("provenance_refs", self.provenance_refs)
        if not provenance:
            raise Grid10InterfaceError("provenance_refs must contain at least one reference")
        object.__setattr__(self, "provenance_refs", provenance)

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        cycle_id: str,
        generation: int,
        frame_id: str,
        frame_generation: int,
        frame_sha256: str,
        policy_id: str,
        policy_generation: int,
        policy_sha256: str,
        cells: Iterable[CellBudget],
        max_total_work_units: int,
        provenance_refs: Iterable[str],
    ) -> "Grid10Plan":
        return cls(
            schema=GRID10_PLAN_SCHEMA,
            plan_id=plan_id,
            cycle_id=cycle_id,
            generation=generation,
            frame_id=frame_id,
            frame_generation=frame_generation,
            frame_sha256=frame_sha256,
            policy_id=policy_id,
            policy_generation=policy_generation,
            policy_sha256=policy_sha256,
            cells=tuple(cells),
            max_total_work_units=max_total_work_units,
            provenance_refs=tuple(provenance_refs),
        )

    def budget_for(self, cell_id: str) -> CellBudget:
        if cell_id not in _GRID10_CELL_SET:
            raise Grid10InterfaceError(f"unknown GRID10 cell {cell_id!r}")
        return self.cells[GRID10_CELL_IDS.index(cell_id)]

    def assert_frame_binding(self, *, frame_id: str, generation: int, sha256: str) -> None:
        if self.frame_id != _identifier("frame_id", frame_id):
            raise Grid10InterfaceError("frame_id mismatch")
        if self.frame_generation != _generation("frame_generation", generation):
            raise Grid10InterfaceError("frame generation mismatch")
        if self.frame_sha256 != _sha256("frame_sha256", sha256):
            raise Grid10InterfaceError("frame digest mismatch")

    def assert_policy_binding(self, *, policy_id: str, generation: int, sha256: str) -> None:
        if self.policy_id != _identifier("policy_id", policy_id):
            raise Grid10InterfaceError("policy_id mismatch")
        if self.policy_generation != _generation("policy_generation", generation):
            raise Grid10InterfaceError("policy generation mismatch")
        if self.policy_sha256 != _sha256("policy_sha256", sha256):
            raise Grid10InterfaceError("policy digest mismatch")

    def validate_input(self, value: "CellInput") -> None:
        if type(value) is not CellInput:
            raise Grid10InterfaceError("cell input must be concrete CellInput")
        _assert_plan_envelope(
            self,
            plan_id=value.plan_id,
            generation=value.plan_generation,
            sha256=value.plan_sha256,
        )
        budget = self.budget_for(value.cell_id)
        if len(value.input_refs) > budget.max_input_refs:
            raise Grid10InterfaceError("cell input reference budget exceeded")
        if value.work_units_requested > budget.max_work_units:
            raise Grid10InterfaceError("cell requested work budget exceeded")
        if value.reentry_depth > budget.max_reentry_depth:
            raise Grid10InterfaceError("cell reentry-depth budget exceeded")

    def validate_output(self, value: "CellOutput", *, cell_input: "CellInput") -> None:
        if type(value) is not CellOutput:
            raise Grid10InterfaceError("cell output must be concrete CellOutput")
        self.validate_input(cell_input)
        _assert_plan_envelope(
            self,
            plan_id=value.plan_id,
            generation=value.plan_generation,
            sha256=value.plan_sha256,
        )
        if value.cell_id != cell_input.cell_id:
            raise Grid10InterfaceError("cell output/input identity mismatch")
        if value.input_sha256 != cell_input.sha256():
            raise Grid10InterfaceError("cell input digest mismatch")
        budget = self.budget_for(value.cell_id)
        if len(value.output_refs) > budget.max_output_refs:
            raise Grid10InterfaceError("cell output reference budget exceeded")
        if value.work_units_used > budget.max_work_units:
            raise Grid10InterfaceError("cell used work budget exceeded")
        if value.work_units_used > cell_input.work_units_requested:
            raise Grid10InterfaceError("cell used more work than requested")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_id": self.plan_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "frame_id": self.frame_id,
            "frame_generation": self.frame_generation,
            "frame_sha256": self.frame_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "cells": [cell.as_dict() for cell in self.cells],
            "max_total_work_units": self.max_total_work_units,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CellInput:
    schema: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    cell_id: str
    work_units_requested: int
    reentry_depth: int
    input_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != GRID10_INPUT_SCHEMA:
            raise Grid10InterfaceError("cell input schema mismatch")
        object.__setattr__(self, "plan_id", _identifier("plan_id", self.plan_id))
        object.__setattr__(
            self, "plan_generation", _generation("plan_generation", self.plan_generation)
        )
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        if self.cell_id not in _GRID10_CELL_SET:
            raise Grid10InterfaceError(f"cell_id must be one of {GRID10_CELL_IDS}")
        object.__setattr__(
            self,
            "work_units_requested",
            _bounded_int("work_units_requested", self.work_units_requested),
        )
        object.__setattr__(
            self, "reentry_depth", _bounded_int("reentry_depth", self.reentry_depth)
        )
        object.__setattr__(self, "input_refs", _refs("input_refs", self.input_refs))
        provenance = _refs("provenance_refs", self.provenance_refs)
        if not provenance:
            raise Grid10InterfaceError("provenance_refs must contain at least one reference")
        object.__setattr__(self, "provenance_refs", provenance)

    @classmethod
    def for_plan(
        cls,
        plan: Grid10Plan,
        *,
        cell_id: str,
        work_units_requested: int,
        reentry_depth: int = 0,
        input_refs: Iterable[str] = (),
        provenance_refs: Iterable[str],
    ) -> "CellInput":
        if type(plan) is not Grid10Plan:
            raise Grid10InterfaceError("plan must be concrete Grid10Plan")
        value = cls(
            schema=GRID10_INPUT_SCHEMA,
            plan_id=plan.plan_id,
            plan_generation=plan.generation,
            plan_sha256=plan.sha256(),
            cell_id=cell_id,
            work_units_requested=work_units_requested,
            reentry_depth=reentry_depth,
            input_refs=tuple(input_refs),
            provenance_refs=tuple(provenance_refs),
        )
        plan.validate_input(value)
        return value

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CellOutput:
    schema: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    input_sha256: str
    cell_id: str
    status: str
    work_units_used: int
    output_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != GRID10_OUTPUT_SCHEMA:
            raise Grid10InterfaceError("cell output schema mismatch")
        object.__setattr__(self, "plan_id", _identifier("plan_id", self.plan_id))
        object.__setattr__(
            self, "plan_generation", _generation("plan_generation", self.plan_generation)
        )
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        object.__setattr__(self, "input_sha256", _sha256("input_sha256", self.input_sha256))
        if self.cell_id not in _GRID10_CELL_SET:
            raise Grid10InterfaceError(f"cell_id must be one of {GRID10_CELL_IDS}")
        if self.status not in _OUTPUT_STATUSES:
            raise Grid10InterfaceError(f"status must be one of {sorted(_OUTPUT_STATUSES)}")
        object.__setattr__(
            self, "work_units_used", _bounded_int("work_units_used", self.work_units_used)
        )
        object.__setattr__(self, "output_refs", _refs("output_refs", self.output_refs))
        object.__setattr__(self, "evidence_refs", _refs("evidence_refs", self.evidence_refs))
        provenance = _refs("provenance_refs", self.provenance_refs)
        if not provenance:
            raise Grid10InterfaceError("provenance_refs must contain at least one reference")
        object.__setattr__(self, "provenance_refs", provenance)

    @classmethod
    def for_input(
        cls,
        plan: Grid10Plan,
        cell_input: CellInput,
        *,
        status: str,
        work_units_used: int,
        output_refs: Iterable[str] = (),
        evidence_refs: Iterable[str] = (),
        provenance_refs: Iterable[str],
    ) -> "CellOutput":
        plan.validate_input(cell_input)
        value = cls(
            schema=GRID10_OUTPUT_SCHEMA,
            plan_id=plan.plan_id,
            plan_generation=plan.generation,
            plan_sha256=plan.sha256(),
            input_sha256=cell_input.sha256(),
            cell_id=cell_input.cell_id,
            status=status,
            work_units_used=work_units_used,
            output_refs=tuple(output_refs),
            evidence_refs=tuple(evidence_refs),
            provenance_refs=tuple(provenance_refs),
        )
        plan.validate_output(value, cell_input=cell_input)
        return value

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_plan_envelope(
    plan: Grid10Plan, *, plan_id: str, generation: int, sha256: str
) -> None:
    if plan.plan_id != plan_id:
        raise Grid10InterfaceError("plan_id mismatch")
    if plan.generation != generation:
        raise Grid10InterfaceError("plan generation mismatch")
    if plan.sha256() != sha256:
        raise Grid10InterfaceError("plan digest mismatch")


@dataclass(frozen=True, slots=True)
class Grid10UsageReceipt:
    schema: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    completed_cell_ids: tuple[str, ...]
    missing_cell_ids: tuple[str, ...]
    total_work_units_used: int
    remaining_work_units: int
    output_sha256s: tuple[str, ...]
    classification: str = "LOGICAL_GRID_ACCOUNTING_ONLY_NOT_PHYSICAL_CONCURRENCY_EVIDENCE"

    def __post_init__(self) -> None:
        if self.schema != GRID10_USAGE_SCHEMA:
            raise Grid10InterfaceError("usage receipt schema mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def account_outputs(
    plan: Grid10Plan,
    pairs: Iterable[tuple[CellInput, CellOutput]],
) -> Grid10UsageReceipt:
    if type(plan) is not Grid10Plan:
        raise Grid10InterfaceError("plan must be concrete Grid10Plan")
    seen: set[str] = set()
    total = 0
    output_hashes: list[str] = []
    for cell_input, cell_output in pairs:
        plan.validate_output(cell_output, cell_input=cell_input)
        if cell_output.cell_id in seen:
            raise Grid10InterfaceError("duplicate output for logical cell")
        seen.add(cell_output.cell_id)
        total += cell_output.work_units_used
        if total > plan.max_total_work_units:
            raise Grid10InterfaceError("GRID10 total work budget exceeded")
        output_hashes.append(cell_output.sha256())
    completed = tuple(cell_id for cell_id in GRID10_CELL_IDS if cell_id in seen)
    missing = tuple(cell_id for cell_id in GRID10_CELL_IDS if cell_id not in seen)
    return Grid10UsageReceipt(
        schema=GRID10_USAGE_SCHEMA,
        plan_id=plan.plan_id,
        plan_generation=plan.generation,
        plan_sha256=plan.sha256(),
        completed_cell_ids=completed,
        missing_cell_ids=missing,
        total_work_units_used=total,
        remaining_work_units=plan.max_total_work_units - total,
        output_sha256s=tuple(sorted(output_hashes)),
    )
