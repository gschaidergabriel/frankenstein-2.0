"""Deterministic GWT selection/broadcast primitives for Frankenstein 2.0 Stage 5.

F2-WP-506 generation 1.

This module selects an explicitly bounded candidate set for one workspace cycle and
constructs a broadcast envelope addressed to logical GRID10 cells. Selection and
broadcast are candidate-coordination artifacts only: they do not establish recipient
uptake, causal influence, world truth, action/effect authority, completion, or runtime
credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

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
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GwtWorkspaceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        object.__setattr__(self, "candidate_sha256", _sha256("candidate_sha256", self.candidate_sha256))
        object.__setattr__(self, "payload_ref", _text("payload_ref", self.payload_ref))
        if self.epistemic_class not in _EPISTEMIC_CLASSES:
            raise GwtWorkspaceError("unsupported selected epistemic_class")
        object.__setattr__(self, "provenance_refs", _unique_sorted_refs("provenance_refs", self.provenance_refs, allow_empty=False))
        object.__setattr__(self, "alternative_refs", _unique_sorted_refs("alternative_refs", self.alternative_refs, allow_empty=True))
        if type(self.score) is not int:
            raise GwtWorkspaceError("score must be an integer")
        _cost("estimated_cost_units", self.estimated_cost_units)

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
        }


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
        object.__setattr__(self, "deferred_candidate_ids", _unique_sorted_refs("deferred_candidate_ids", self.deferred_candidate_ids, allow_empty=True))
        if set(selected_ids).intersection(self.deferred_candidate_ids):
            raise GwtWorkspaceError("selected and deferred candidates must be disjoint")
        hyper_fields = (self.hyperposition_id, self.hyperposition_generation, self.hyperposition_sha256)
        if any(value is not None for value in hyper_fields) and not all(value is not None for value in hyper_fields):
            raise GwtWorkspaceError("hyperposition binding must be all-present or all-absent")
        if self.hyperposition_id is not None:
            object.__setattr__(self, "hyperposition_id", _text("hyperposition_id", self.hyperposition_id))
            _generation("hyperposition_generation", self.hyperposition_generation)
            object.__setattr__(self, "hyperposition_sha256", _sha256("hyperposition_sha256", self.hyperposition_sha256))

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
            "selected": [item.as_dict() for item in self.selected],
            "deferred_candidate_ids": list(self.deferred_candidate_ids),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "uptake_claim": "NOT_OBSERVED_BY_SELECTION",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class BroadcastEnvelope:
    broadcast_id: str
    cycle_id: str
    generation: int
    selection_id: str
    selection_generation: int
    selection_sha256: str
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
        if not isinstance(self.recipient_cell_ids, tuple) or not self.recipient_cell_ids:
            raise GwtWorkspaceError("recipient_cell_ids must be a non-empty immutable tuple")
        if len(set(self.recipient_cell_ids)) != len(self.recipient_cell_ids):
            raise GwtWorkspaceError("recipient_cell_ids must not contain duplicates")
        if any(cell_id not in _GRID10_CELL_SET for cell_id in self.recipient_cell_ids):
            raise GwtWorkspaceError("recipient_cell_ids must contain only logical G1..G10 ids")
        object.__setattr__(self, "recipient_cell_ids", tuple(sorted(self.recipient_cell_ids, key=GRID10_CELL_IDS.index)))
        object.__setattr__(self, "candidate_ids", _unique_sorted_refs("candidate_ids", self.candidate_ids, allow_empty=False))
        object.__setattr__(self, "candidate_payload_refs", _unique_sorted_refs("candidate_payload_refs", self.candidate_payload_refs, allow_empty=False))
        if len(self.candidate_ids) != len(self.candidate_payload_refs):
            raise GwtWorkspaceError("candidate_ids and candidate_payload_refs must have equal length")

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
    hyperposition_id: str | None = None,
    hyperposition_generation: int | None = None,
    hyperposition_sha256: str | None = None,
) -> WorkspaceSelection:
    if not isinstance(policy, SelectionPolicy):
        raise GwtWorkspaceError("policy must be SelectionPolicy")
    if not isinstance(candidates, tuple) or not candidates:
        raise GwtWorkspaceError("candidates must be a non-empty immutable tuple")
    if len(candidates) > _MAX_ITEMS or not all(isinstance(item, WorkspaceCandidate) for item in candidates):
        raise GwtWorkspaceError("candidates contain invalid values or exceed limit")
    ids = tuple(item.candidate_id for item in candidates)
    if len(set(ids)) != len(ids):
        raise GwtWorkspaceError("duplicate candidate_id")
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
            )
        )
        total_cost += item.estimated_cost_units
    if not selected:
        raise GwtWorkspaceError("selection policy admitted no candidate within budget")

    return WorkspaceSelection(
        selection_id=selection_id,
        cycle_id=cycle_id,
        generation=generation,
        frame_id=frame_id,
        frame_generation=frame_generation,
        frame_sha256=frame_sha256,
        grid_plan_id=grid_plan_id,
        grid_plan_generation=grid_plan_generation,
        grid_plan_sha256=grid_plan_sha256,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        selected=tuple(selected),
        deferred_candidate_ids=tuple(deferred),
        hyperposition_id=hyperposition_id,
        hyperposition_generation=hyperposition_generation,
        hyperposition_sha256=hyperposition_sha256,
    )


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
        recipient_cell_ids=recipient_cell_ids,
        candidate_ids=candidate_ids,
        candidate_payload_refs=payload_refs,
    )
