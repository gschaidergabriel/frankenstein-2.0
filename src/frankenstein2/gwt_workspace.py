"""Deterministic GWT selection/broadcast primitives for Frankenstein 2.0 Stage 5.

F2-WP-506 generation 1.

This module selects an explicitly bounded candidate set for one workspace cycle and
constructs a broadcast envelope addressed to logical GRID10 cells. Candidate admission
is bound to an exact, structurally validated WP503 Grid10Plan/CellInput/CellOutput triple,
and downstream broadcast re-validates the exact policy + source-candidate lineage carried
by the WorkspaceSelection.

Selection and broadcast remain candidate-coordination artifacts only: they do not establish
recipient uptake, causal influence, world truth, action/effect authority, completion, target
runtime, physical GRID10 concurrency, or training credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import CellInput, CellOutput, Grid10InterfaceError, Grid10Plan
from frankenstein2.hyperposition import Hyperposition

GWT_PRODUCER_ADMISSION_SCHEMA = "FRANKENSTEIN2_GWT_CANDIDATE_PRODUCER_ADMISSION/v1"
GWT_CANDIDATE_SCHEMA = "FRANKENSTEIN2_GWT_CANDIDATE/v1"
GWT_SELECTION_POLICY_SCHEMA = "FRANKENSTEIN2_GWT_SELECTION_POLICY/v1"
GWT_SELECTION_SCHEMA = "FRANKENSTEIN2_GWT_WORKSPACE_SELECTION/v1"
GWT_BROADCAST_SCHEMA = "FRANKENSTEIN2_GWT_BROADCAST_ENVELOPE/v1"
GRID10_CELL_IDS = tuple(f"G{i}" for i in range(1, 11))
_GRID10_CELL_SET = frozenset(GRID10_CELL_IDS)
_EPISTEMIC_CLASSES = frozenset(
    {
        "OBSERVED_EVIDENCE",
        "INFERRED",
        "UNKNOWN",
        "CONFLICT",
        "NOT_COMPUTED",
        "SIMULATED",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_ITEMS = 4096
_MAX_MICROS = 1_000_000
_MAX_COST = 2**31 - 1


class GwtWorkspaceError(ValueError):
    """Fail-closed validation error for GWT selection/broadcast structures."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GwtWorkspaceError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise GwtWorkspaceError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtWorkspaceError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise GwtWorkspaceError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GwtWorkspaceError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_MICROS:
        raise GwtWorkspaceError(f"{name} must be an integer in [0, {_MAX_MICROS}]")
    return value


def _cost(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_COST:
        raise GwtWorkspaceError(f"{name} must be an integer in [0, {_MAX_COST}]")
    return value


def _positive_int(name: str, value: Any, *, maximum: int = _MAX_ITEMS) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise GwtWorkspaceError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _unique_sorted_refs(name: str, values: Iterable[str], *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtWorkspaceError(f"{name} must be an iterable of strings")
    items = tuple(_text(f"{name} item", item) for item in values)
    if len(items) > _MAX_ITEMS:
        raise GwtWorkspaceError(f"{name} exceeds {_MAX_ITEMS} items")
    if len(set(items)) != len(items):
        raise GwtWorkspaceError(f"{name} must not contain duplicates")
    if not allow_empty and not items:
        raise GwtWorkspaceError(f"{name} must not be empty")
    return tuple(sorted(items))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GwtWorkspaceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateProducerAdmission:
    """Exact source-level GRID10 producer binding for one workspace candidate.

    This is structural component evidence only. It proves that the supplied immutable
    Grid10Plan/CellInput/CellOutput triple is mutually consistent under the WP503 ABI; it
    does not prove that a physical model or target runtime actually produced the output.
    """

    plan: Grid10Plan
    cell_input: CellInput
    cell_output: CellOutput

    schema = GWT_PRODUCER_ADMISSION_SCHEMA
    classification = "SOURCE_LEVEL_GRID10_PRODUCER_BINDING_NOT_RUNTIME_ATTESTATION"

    def __post_init__(self) -> None:
        if type(self.plan) is not Grid10Plan:
            raise GwtWorkspaceError("producer plan must be concrete Grid10Plan")
        if type(self.cell_input) is not CellInput:
            raise GwtWorkspaceError("producer input must be concrete CellInput")
        if type(self.cell_output) is not CellOutput:
            raise GwtWorkspaceError("producer output must be concrete CellOutput")
        try:
            self.plan.validate_output(self.cell_output, cell_input=self.cell_input)
        except Grid10InterfaceError as exc:
            raise GwtWorkspaceError(f"invalid GRID10 producer binding: {exc}") from exc

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    @property
    def plan_generation(self) -> int:
        return self.plan.generation

    @property
    def plan_sha256(self) -> str:
        return self.plan.sha256()

    @property
    def cell_id(self) -> str:
        return self.cell_output.cell_id

    @property
    def input_sha256(self) -> str:
        return self.cell_input.sha256()

    @property
    def output_sha256(self) -> str:
        return self.cell_output.sha256()

    @property
    def output_refs(self) -> tuple[str, ...]:
        return self.cell_output.output_refs

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "plan_id": self.plan_id,
            "plan_generation": self.plan_generation,
            "plan_sha256": self.plan_sha256,
            "cell_id": self.cell_id,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "output_status": self.cell_output.status,
            "output_refs": list(self.cell_output.output_refs),
            "evidence_refs": list(self.cell_output.evidence_refs),
            "provenance_refs": list(self.cell_output.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceCandidate:
    candidate_id: str
    payload_ref: str
    epistemic_class: str
    provenance_refs: tuple[str, ...]
    salience_micros: int
    goal_relevance_micros: int
    uncertainty_micros: int
    information_gain_micros: int
    estimated_cost_units: int
    alternative_refs: tuple[str, ...] = ()
    producer_admission: CandidateProducerAdmission | None = None

    schema = GWT_CANDIDATE_SCHEMA
    classification = "WORKSPACE_CANDIDATE_NOT_WORLD_TRUTH_OR_ACTION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        object.__setattr__(self, "payload_ref", _text("payload_ref", self.payload_ref))
        if self.epistemic_class not in _EPISTEMIC_CLASSES:
            raise GwtWorkspaceError("unsupported epistemic_class")
        object.__setattr__(
            self,
            "provenance_refs",
            _unique_sorted_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        object.__setattr__(
            self,
            "alternative_refs",
            _unique_sorted_refs("alternative_refs", self.alternative_refs, allow_empty=True),
        )
        _micros("salience_micros", self.salience_micros)
        _micros("goal_relevance_micros", self.goal_relevance_micros)
        _micros("uncertainty_micros", self.uncertainty_micros)
        _micros("information_gain_micros", self.information_gain_micros)
        _cost("estimated_cost_units", self.estimated_cost_units)
        if self.producer_admission is not None and type(self.producer_admission) is not CandidateProducerAdmission:
            raise GwtWorkspaceError("producer_admission must be CandidateProducerAdmission or None")
        if self.epistemic_class == "NOT_COMPUTED" and any(
            (
                self.salience_micros,
                self.goal_relevance_micros,
                self.uncertainty_micros,
                self.information_gain_micros,
                self.estimated_cost_units,
                self.alternative_refs,
            )
        ):
            raise GwtWorkspaceError("NOT_COMPUTED candidate must not carry computed scores/cost/alternatives")
        if self.epistemic_class == "CONFLICT" and len(self.alternative_refs) < 2:
            raise GwtWorkspaceError("CONFLICT candidate requires at least two alternative_refs")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "candidate_id": self.candidate_id,
            "payload_ref": self.payload_ref,
            "epistemic_class": self.epistemic_class,
            "provenance_refs": list(self.provenance_refs),
            "salience_micros": self.salience_micros,
            "goal_relevance_micros": self.goal_relevance_micros,
            "uncertainty_micros": self.uncertainty_micros,
            "information_gain_micros": self.information_gain_micros,
            "estimated_cost_units": self.estimated_cost_units,
            "alternative_refs": list(self.alternative_refs),
            "producer_admission": (
                None if self.producer_admission is None else self.producer_admission.as_dict()
            ),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionPolicy:
    policy_id: str
    generation: int
    max_selected_candidates: int
    max_total_cost_units: int
    salience_weight: int
    goal_relevance_weight: int
    uncertainty_weight: int
    information_gain_weight: int
    cost_weight: int

    schema = GWT_SELECTION_POLICY_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _generation("generation", self.generation)
        _positive_int("max_selected_candidates", self.max_selected_candidates)
        _cost("max_total_cost_units", self.max_total_cost_units)
        for name in (
            "salience_weight",
            "goal_relevance_weight",
            "uncertainty_weight",
            "information_gain_weight",
            "cost_weight",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 1_000_000:
                raise GwtWorkspaceError(f"{name} must be an integer in [0, 1000000]")
        if not any(
            (
                self.salience_weight,
                self.goal_relevance_weight,
                self.uncertainty_weight,
                self.information_gain_weight,
                self.cost_weight,
            )
        ):
            raise GwtWorkspaceError("selection policy must contain at least one non-zero weight")

    def score(self, candidate: WorkspaceCandidate) -> int:
        if not isinstance(candidate, WorkspaceCandidate):
            raise GwtWorkspaceError("candidate must be WorkspaceCandidate")
        return (
            self.salience_weight * candidate.salience_micros
            + self.goal_relevance_weight * candidate.goal_relevance_micros
            + self.uncertainty_weight * candidate.uncertainty_micros
            + self.information_gain_weight * candidate.information_gain_micros
            - self.cost_weight * candidate.estimated_cost_units
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_selected_candidates": self.max_selected_candidates,
            "max_total_cost_units": self.max_total_cost_units,
            "salience_weight": self.salience_weight,
            "goal_relevance_weight": self.goal_relevance_weight,
            "uncertainty_weight": self.uncertainty_weight,
            "information_gain_weight": self.information_gain_weight,
            "cost_weight": self.cost_weight,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectedCandidate:
    candidate_id: str
    candidate_sha256: str
    payload_ref: str
    epistemic_class: str
    provenance_refs: tuple[str, ...]
    alternative_refs: tuple[str, ...]
    score: int
    estimated_cost_units: int
    producer_admission_sha256: str | None = None
    producer_cell_id: str | None = None
    producer_output_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        object.__setattr__(self, "candidate_sha256", _sha256("candidate_sha256", self.candidate_sha256))
        object.__setattr__(self, "payload_ref", _text("payload_ref", self.payload_ref))
        if self.epistemic_class not in _EPISTEMIC_CLASSES:
            raise GwtWorkspaceError("unsupported selected epistemic_class")
        object.__setattr__(
            self,
            "provenance_refs",
            _unique_sorted_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        object.__setattr__(
            self,
            "alternative_refs",
            _unique_sorted_refs("alternative_refs", self.alternative_refs, allow_empty=True),
        )
        if type(self.score) is not int:
            raise GwtWorkspaceError("score must be an integer")
        _cost("estimated_cost_units", self.estimated_cost_units)
        producer_fields = (
            self.producer_admission_sha256,
            self.producer_cell_id,
            self.producer_output_sha256,
        )
        if any(value is not None for value in producer_fields) and not all(value is not None for value in producer_fields):
            raise GwtWorkspaceError("selected producer binding must be all-present or all-absent")
        if self.producer_admission_sha256 is not None:
            object.__setattr__(
                self,
                "producer_admission_sha256",
                _sha256("producer_admission_sha256", self.producer_admission_sha256),
            )
            if self.producer_cell_id not in _GRID10_CELL_SET:
                raise GwtWorkspaceError("producer_cell_id must be one logical G1..G10 id")
            object.__setattr__(
                self,
                "producer_output_sha256",
                _sha256("producer_output_sha256", self.producer_output_sha256),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_sha256": self.candidate_sha256,
            "payload_ref": self.payload_ref,
            "epistemic_class": self.epistemic_class,
            "provenance_refs": list(self.provenance_refs),
            "alternative_refs": list(self.alternative_refs),
            "score": self.score,
            "estimated_cost_units": self.estimated_cost_units,
            "producer_admission_sha256": self.producer_admission_sha256,
            "producer_cell_id": self.producer_cell_id,
            "producer_output_sha256": self.producer_output_sha256,
        }


def _validate_candidate_origins(
    candidates: tuple[WorkspaceCandidate, ...],
    *,
    cycle_id: str,
    frame_id: str,
    frame_generation: int,
    frame_sha256: str,
    grid_plan_id: str,
    grid_plan_generation: int,
    grid_plan_sha256: str,
) -> None:
    ids = tuple(item.candidate_id for item in candidates)
    if len(set(ids)) != len(ids):
        raise GwtWorkspaceError("duplicate candidate_id")
    producer_payload_pairs: set[tuple[str, str]] = set()
    for item in candidates:
        admission = item.producer_admission
        if admission is None:
            raise GwtWorkspaceError("candidate requires exact GRID10 producer_admission")
        # Re-run the structural WP503 binding at the consuming boundary.
        try:
            admission.plan.validate_output(admission.cell_output, cell_input=admission.cell_input)
        except Grid10InterfaceError as exc:
            raise GwtWorkspaceError(f"invalid GRID10 producer binding: {exc}") from exc
        if (
            admission.plan_id != grid_plan_id
            or admission.plan_generation != grid_plan_generation
            or admission.plan_sha256 != grid_plan_sha256
        ):
            raise GwtWorkspaceError("candidate producer GRID10 plan binding mismatch")
        if admission.plan.cycle_id != cycle_id:
            raise GwtWorkspaceError("candidate producer cycle binding mismatch")
        if (
            admission.plan.frame_id != frame_id
            or admission.plan.frame_generation != frame_generation
            or admission.plan.frame_sha256 != frame_sha256
        ):
            raise GwtWorkspaceError("candidate producer SituationFrame binding mismatch")
        if item.payload_ref not in admission.output_refs:
            raise GwtWorkspaceError("candidate payload_ref is not present in producer output_refs")
        producer_payload = (admission.output_sha256, item.payload_ref)
        if producer_payload in producer_payload_pairs:
            raise GwtWorkspaceError("duplicate producer-output/payload alias amplification")
        producer_payload_pairs.add(producer_payload)


def _rank_candidates(
    policy: SelectionPolicy,
    candidates: tuple[WorkspaceCandidate, ...],
) -> tuple[tuple[SelectedCandidate, ...], tuple[str, ...]]:
    if any(item.estimated_cost_units > policy.max_total_cost_units for item in candidates):
        raise GwtWorkspaceError("candidate estimated cost exceeds selection total-cost budget")
    ranked = sorted(candidates, key=lambda item: (-policy.score(item), item.candidate_id))
    selected: list[SelectedCandidate] = []
    deferred: list[str] = []
    total_cost = 0
    for item in ranked:
        if len(selected) >= policy.max_selected_candidates:
            deferred.append(item.candidate_id)
            continue
        if total_cost + item.estimated_cost_units > policy.max_total_cost_units:
            deferred.append(item.candidate_id)
            continue
        admission = item.producer_admission
        if admission is None:  # guarded by _validate_candidate_origins; keep fail-closed locally.
            raise GwtWorkspaceError("candidate requires exact GRID10 producer_admission")
        selected.append(
            SelectedCandidate(
                candidate_id=item.candidate_id,
                candidate_sha256=item.sha256(),
                payload_ref=item.payload_ref,
                epistemic_class=item.epistemic_class,
                provenance_refs=item.provenance_refs,
                alternative_refs=item.alternative_refs,
                score=policy.score(item),
                estimated_cost_units=item.estimated_cost_units,
                producer_admission_sha256=admission.sha256(),
                producer_cell_id=admission.cell_id,
                producer_output_sha256=admission.output_sha256,
            )
        )
        total_cost += item.estimated_cost_units
    if not selected:
        raise GwtWorkspaceError("selection policy admitted no candidate within budget")
    return tuple(selected), tuple(sorted(deferred))


def _resolve_hyperposition_binding(
    *,
    frame_id: str,
    frame_generation: int,
    frame_sha256: str,
    hyperposition: Hyperposition | None,
    hyperposition_id: str | None,
    hyperposition_generation: int | None,
    hyperposition_sha256: str | None,
) -> tuple[str | None, int | None, str | None]:
    fields = (hyperposition_id, hyperposition_generation, hyperposition_sha256)
    if hyperposition is None:
        if any(value is not None for value in fields):
            raise GwtWorkspaceError(
                "hyperposition object required to verify situation frame binding"
            )
        return None, None, None
    if type(hyperposition) is not Hyperposition:
        raise GwtWorkspaceError("hyperposition must be concrete Hyperposition or None")
    normalized_frame_id = _text("frame_id", frame_id)
    normalized_frame_generation = _generation("frame_generation", frame_generation)
    normalized_frame_sha256 = _sha256("frame_sha256", frame_sha256)
    if (
        hyperposition.situation_frame_ref != normalized_frame_id
        or hyperposition.situation_frame_generation != normalized_frame_generation
        or hyperposition.situation_frame_sha256 != normalized_frame_sha256
    ):
        raise GwtWorkspaceError("hyperposition situation frame binding mismatch")
    expected = (
        hyperposition.hyperposition_id,
        hyperposition.generation,
        hyperposition.sha256(),
    )
    if any(value is not None for value in fields):
        if not all(value is not None for value in fields):
            raise GwtWorkspaceError("hyperposition binding must be all-present or all-absent")
        normalized = (
            _text("hyperposition_id", hyperposition_id),
            _generation("hyperposition_generation", hyperposition_generation),
            _sha256("hyperposition_sha256", hyperposition_sha256),
        )
        if normalized != expected:
            raise GwtWorkspaceError("hyperposition identity binding mismatch")
    return expected


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceSelection:
    selection_id: str
    cycle_id: str
    generation: int
    frame_id: str
    frame_generation: int
    frame_sha256: str
    grid_plan_id: str
    grid_plan_generation: int
    grid_plan_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    selected: tuple[SelectedCandidate, ...]
    deferred_candidate_ids: tuple[str, ...]
    hyperposition_id: str | None = None
    hyperposition_generation: int | None = None
    hyperposition_sha256: str | None = None
    hyperposition: Hyperposition | None = None
    selection_policy: SelectionPolicy | None = None
    source_candidates: tuple[WorkspaceCandidate, ...] = ()

    schema = GWT_SELECTION_SCHEMA
    classification = "GWT_SELECTION_CANDIDATE_COORDINATION_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "selection_id", _text("selection_id", self.selection_id))
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        _generation("generation", self.generation)
        object.__setattr__(self, "frame_id", _text("frame_id", self.frame_id))
        _generation("frame_generation", self.frame_generation)
        object.__setattr__(self, "frame_sha256", _sha256("frame_sha256", self.frame_sha256))
        object.__setattr__(self, "grid_plan_id", _text("grid_plan_id", self.grid_plan_id))
        _generation("grid_plan_generation", self.grid_plan_generation)
        object.__setattr__(self, "grid_plan_sha256", _sha256("grid_plan_sha256", self.grid_plan_sha256))
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _generation("policy_generation", self.policy_generation)
        object.__setattr__(self, "policy_sha256", _sha256("policy_sha256", self.policy_sha256))
        if not isinstance(self.selected, tuple) or not all(isinstance(item, SelectedCandidate) for item in self.selected):
            raise GwtWorkspaceError("selected must be an immutable tuple of SelectedCandidate")
        selected_ids = tuple(item.candidate_id for item in self.selected)
        if len(set(selected_ids)) != len(selected_ids):
            raise GwtWorkspaceError("selected contains duplicate candidate_id")
        object.__setattr__(
            self,
            "deferred_candidate_ids",
            _unique_sorted_refs("deferred_candidate_ids", self.deferred_candidate_ids, allow_empty=True),
        )
        if set(selected_ids).intersection(self.deferred_candidate_ids):
            raise GwtWorkspaceError("selected and deferred candidates must be disjoint")
        resolved_hyperposition_id, resolved_hyperposition_generation, resolved_hyperposition_sha256 = (
            _resolve_hyperposition_binding(
                frame_id=self.frame_id,
                frame_generation=self.frame_generation,
                frame_sha256=self.frame_sha256,
                hyperposition=self.hyperposition,
                hyperposition_id=self.hyperposition_id,
                hyperposition_generation=self.hyperposition_generation,
                hyperposition_sha256=self.hyperposition_sha256,
            )
        )
        object.__setattr__(self, "hyperposition_id", resolved_hyperposition_id)
        object.__setattr__(self, "hyperposition_generation", resolved_hyperposition_generation)
        object.__setattr__(self, "hyperposition_sha256", resolved_hyperposition_sha256)
        if self.selection_policy is not None and type(self.selection_policy) is not SelectionPolicy:
            raise GwtWorkspaceError("selection_policy must be SelectionPolicy or None")
        if not isinstance(self.source_candidates, tuple) or not all(type(item) is WorkspaceCandidate for item in self.source_candidates):
            raise GwtWorkspaceError("source_candidates must be an immutable tuple of WorkspaceCandidate")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "selection_id": self.selection_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "frame_id": self.frame_id,
            "frame_generation": self.frame_generation,
            "frame_sha256": self.frame_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_generation": self.grid_plan_generation,
            "grid_plan_sha256": self.grid_plan_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "hyperposition_id": self.hyperposition_id,
            "hyperposition_generation": self.hyperposition_generation,
            "hyperposition_sha256": self.hyperposition_sha256,
            "hyperposition": None if self.hyperposition is None else self.hyperposition.as_dict(),
            "selection_policy": None if self.selection_policy is None else self.selection_policy.as_dict(),
            "source_candidates": [item.as_dict() for item in self.source_candidates],
            "selected": [item.as_dict() for item in self.selected],
            "deferred_candidate_ids": list(self.deferred_candidate_ids),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "uptake_claim": "NOT_OBSERVED_BY_SELECTION",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_selection_build_lineage(selection: WorkspaceSelection) -> None:
    resolved_hyperposition = _resolve_hyperposition_binding(
        frame_id=selection.frame_id,
        frame_generation=selection.frame_generation,
        frame_sha256=selection.frame_sha256,
        hyperposition=selection.hyperposition,
        hyperposition_id=selection.hyperposition_id,
        hyperposition_generation=selection.hyperposition_generation,
        hyperposition_sha256=selection.hyperposition_sha256,
    )
    if resolved_hyperposition != (
        selection.hyperposition_id,
        selection.hyperposition_generation,
        selection.hyperposition_sha256,
    ):
        raise GwtWorkspaceError("selection hyperposition lineage mismatch")
    policy = selection.selection_policy
    candidates = selection.source_candidates
    if policy is None or not candidates:
        raise GwtWorkspaceError("selection lacks exact builder policy/candidate lineage")
    if (
        selection.policy_id != policy.policy_id
        or selection.policy_generation != policy.generation
        or selection.policy_sha256 != policy.sha256()
    ):
        raise GwtWorkspaceError("selection policy lineage mismatch")
    _validate_candidate_origins(
        candidates,
        cycle_id=selection.cycle_id,
        frame_id=selection.frame_id,
        frame_generation=selection.frame_generation,
        frame_sha256=selection.frame_sha256,
        grid_plan_id=selection.grid_plan_id,
        grid_plan_generation=selection.grid_plan_generation,
        grid_plan_sha256=selection.grid_plan_sha256,
    )
    expected_selected, expected_deferred = _rank_candidates(policy, candidates)
    if tuple(item.as_dict() for item in selection.selected) != tuple(item.as_dict() for item in expected_selected):
        raise GwtWorkspaceError("selection selected-candidate lineage mismatch")
    if selection.deferred_candidate_ids != expected_deferred:
        raise GwtWorkspaceError("selection deferred-candidate lineage mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class BroadcastEnvelope:
    broadcast_id: str
    cycle_id: str
    generation: int
    selection_id: str
    selection_generation: int
    selection_sha256: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    recipient_cell_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    candidate_payload_refs: tuple[str, ...]

    schema = GWT_BROADCAST_SCHEMA
    classification = "BROADCAST_OFFER_NOT_UPTAKE_OR_CAUSAL_INFLUENCE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "broadcast_id", _text("broadcast_id", self.broadcast_id))
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        _generation("generation", self.generation)
        object.__setattr__(self, "selection_id", _text("selection_id", self.selection_id))
        _generation("selection_generation", self.selection_generation)
        object.__setattr__(self, "selection_sha256", _sha256("selection_sha256", self.selection_sha256))
        object.__setattr__(self, "plan_id", _text("plan_id", self.plan_id))
        _generation("plan_generation", self.plan_generation)
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        if not isinstance(self.recipient_cell_ids, tuple) or not self.recipient_cell_ids:
            raise GwtWorkspaceError("recipient_cell_ids must be a non-empty immutable tuple")
        if len(set(self.recipient_cell_ids)) != len(self.recipient_cell_ids):
            raise GwtWorkspaceError("recipient_cell_ids must not contain duplicates")
        if any(cell_id not in _GRID10_CELL_SET for cell_id in self.recipient_cell_ids):
            raise GwtWorkspaceError("recipient_cell_ids must contain only logical G1..G10 ids")
        object.__setattr__(
            self,
            "recipient_cell_ids",
            tuple(sorted(self.recipient_cell_ids, key=GRID10_CELL_IDS.index)),
        )
        if not isinstance(self.candidate_ids, tuple) or not self.candidate_ids:
            raise GwtWorkspaceError("candidate_ids must be a non-empty immutable tuple")
        if not isinstance(self.candidate_payload_refs, tuple) or not self.candidate_payload_refs:
            raise GwtWorkspaceError("candidate_payload_refs must be a non-empty immutable tuple")
        candidate_ids = tuple(_text("candidate_ids item", item) for item in self.candidate_ids)
        payload_refs = tuple(_text("candidate_payload_refs item", item) for item in self.candidate_payload_refs)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise GwtWorkspaceError("candidate_ids must not contain duplicates")
        if len(candidate_ids) != len(payload_refs):
            raise GwtWorkspaceError("candidate_ids and candidate_payload_refs must have equal length")
        object.__setattr__(self, "candidate_ids", candidate_ids)
        object.__setattr__(self, "candidate_payload_refs", payload_refs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "broadcast_id": self.broadcast_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "selection_id": self.selection_id,
            "selection_generation": self.selection_generation,
            "selection_sha256": self.selection_sha256,
            "plan_id": self.plan_id,
            "plan_generation": self.plan_generation,
            "plan_sha256": self.plan_sha256,
            "recipient_cell_ids": list(self.recipient_cell_ids),
            "candidate_ids": list(self.candidate_ids),
            "candidate_payload_refs": list(self.candidate_payload_refs),
            "delivery_state": "OFFERED_NOT_ACKED",
            "uptake_observed": False,
            "causal_influence_observed": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_workspace_selection(
    *,
    selection_id: str,
    cycle_id: str,
    generation: int,
    frame_id: str,
    frame_generation: int,
    frame_sha256: str,
    grid_plan_id: str,
    grid_plan_generation: int,
    grid_plan_sha256: str,
    policy: SelectionPolicy,
    candidates: tuple[WorkspaceCandidate, ...],
    hyperposition: Hyperposition | None = None,
    hyperposition_id: str | None = None,
    hyperposition_generation: int | None = None,
    hyperposition_sha256: str | None = None,
) -> WorkspaceSelection:
    if not isinstance(policy, SelectionPolicy):
        raise GwtWorkspaceError("policy must be SelectionPolicy")
    if not isinstance(candidates, tuple) or not candidates:
        raise GwtWorkspaceError("candidates must be a non-empty immutable tuple")
    if len(candidates) > _MAX_ITEMS or not all(type(item) is WorkspaceCandidate for item in candidates):
        raise GwtWorkspaceError("candidates contain invalid values or exceed limit")
    normalized_cycle_id = _text("cycle_id", cycle_id)
    normalized_frame_id = _text("frame_id", frame_id)
    normalized_frame_generation = _generation("frame_generation", frame_generation)
    normalized_frame_sha256 = _sha256("frame_sha256", frame_sha256)
    normalized_grid_plan_id = _text("grid_plan_id", grid_plan_id)
    normalized_grid_plan_generation = _generation("grid_plan_generation", grid_plan_generation)
    normalized_grid_plan_sha256 = _sha256("grid_plan_sha256", grid_plan_sha256)
    canonical_candidates = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    _validate_candidate_origins(
        canonical_candidates,
        cycle_id=normalized_cycle_id,
        frame_id=normalized_frame_id,
        frame_generation=normalized_frame_generation,
        frame_sha256=normalized_frame_sha256,
        grid_plan_id=normalized_grid_plan_id,
        grid_plan_generation=normalized_grid_plan_generation,
        grid_plan_sha256=normalized_grid_plan_sha256,
    )
    selected, deferred = _rank_candidates(policy, canonical_candidates)
    value = WorkspaceSelection(
        selection_id=selection_id,
        cycle_id=normalized_cycle_id,
        generation=generation,
        frame_id=normalized_frame_id,
        frame_generation=normalized_frame_generation,
        frame_sha256=normalized_frame_sha256,
        grid_plan_id=normalized_grid_plan_id,
        grid_plan_generation=normalized_grid_plan_generation,
        grid_plan_sha256=normalized_grid_plan_sha256,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        selected=selected,
        deferred_candidate_ids=deferred,
        hyperposition_id=hyperposition_id,
        hyperposition_generation=hyperposition_generation,
        hyperposition_sha256=hyperposition_sha256,
        hyperposition=hyperposition,
        selection_policy=policy,
        source_candidates=canonical_candidates,
    )
    _assert_selection_build_lineage(value)
    return value


def verify_selection_binding(
    selection: WorkspaceSelection,
    *,
    expected_generation: int,
    expected_selection_sha256: str,
    frame_id: str,
    frame_generation: int,
    frame_sha256: str,
    grid_plan_id: str,
    grid_plan_generation: int,
    grid_plan_sha256: str,
) -> None:
    if not isinstance(selection, WorkspaceSelection):
        raise GwtWorkspaceError("selection must be WorkspaceSelection")
    _assert_selection_build_lineage(selection)
    if selection.generation != _generation("expected_generation", expected_generation):
        raise GwtWorkspaceError("selection generation mismatch")
    if selection.sha256() != _sha256("expected_selection_sha256", expected_selection_sha256):
        raise GwtWorkspaceError("selection digest mismatch")
    if selection.frame_id != _text("frame_id", frame_id):
        raise GwtWorkspaceError("frame_id mismatch")
    if selection.frame_generation != _generation("frame_generation", frame_generation):
        raise GwtWorkspaceError("frame generation mismatch")
    if selection.frame_sha256 != _sha256("frame_sha256", frame_sha256):
        raise GwtWorkspaceError("frame digest mismatch")
    if selection.grid_plan_id != _text("grid_plan_id", grid_plan_id):
        raise GwtWorkspaceError("grid plan id mismatch")
    if selection.grid_plan_generation != _generation("grid_plan_generation", grid_plan_generation):
        raise GwtWorkspaceError("grid plan generation mismatch")
    if selection.grid_plan_sha256 != _sha256("grid_plan_sha256", grid_plan_sha256):
        raise GwtWorkspaceError("grid plan digest mismatch")


def create_broadcast(
    *,
    broadcast_id: str,
    generation: int,
    selection: WorkspaceSelection,
    expected_selection_sha256: str,
    recipient_cell_ids: tuple[str, ...],
) -> BroadcastEnvelope:
    if not isinstance(selection, WorkspaceSelection):
        raise GwtWorkspaceError("selection must be WorkspaceSelection")
    _assert_selection_build_lineage(selection)
    if selection.sha256() != _sha256("expected_selection_sha256", expected_selection_sha256):
        raise GwtWorkspaceError("selection digest mismatch")
    candidate_ids = tuple(item.candidate_id for item in selection.selected)
    payload_refs = tuple(item.payload_ref for item in selection.selected)
    return BroadcastEnvelope(
        broadcast_id=broadcast_id,
        cycle_id=selection.cycle_id,
        generation=generation,
        selection_id=selection.selection_id,
        selection_generation=selection.generation,
        selection_sha256=selection.sha256(),
        plan_id=selection.grid_plan_id,
        plan_generation=selection.grid_plan_generation,
        plan_sha256=selection.grid_plan_sha256,
        recipient_cell_ids=recipient_cell_ids,
        candidate_ids=candidate_ids,
        candidate_payload_refs=payload_refs,
    )
