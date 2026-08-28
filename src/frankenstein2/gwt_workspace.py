"""Deterministic GWT workspace selection and logical GRID10 broadcast contract.

F2-WP-506 generation 1.

This module coordinates explicit caller-supplied cognition candidates only.  It binds every
selection to one exact SituationFrame and GRID10 plan, optionally binds one exact
Hyperposition, applies one explicit deterministic integer policy, and creates a broadcast
envelope for logical G1..G10 recipients.

It does not infer world facts/goals/causality/completion, call models/providers/tools,
read/write UnifiedDB, mutate GRID state, claim broadcast uptake, authorize effects, imply
physical decoder concurrency, or mint GRID10/GWT/runtime/training/whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import GRID10_CELL_IDS, Grid10Plan
from frankenstein2.hyperposition import Hyperposition
from frankenstein2.situation_frame import SituationFrame

WORKSPACE_CANDIDATE_SCHEMA = "FRANKENSTEIN2_GWT_WORKSPACE_CANDIDATE/v1"
SELECTION_POLICY_SCHEMA = "FRANKENSTEIN2_GWT_SELECTION_POLICY/v1"
WORKSPACE_SELECTION_SCHEMA = "FRANKENSTEIN2_GWT_WORKSPACE_SELECTION/v1"
BROADCAST_ENVELOPE_SCHEMA = "FRANKENSTEIN2_GWT_BROADCAST_ENVELOPE/v1"

_EPISTEMIC_CLASSES = frozenset(
    {"OBSERVATION", "MEMORY", "HYPOTHESIS", "SIMULATION", "CONFLICT", "UNKNOWN"}
)
_UNRESOLVED_CLASSES = frozenset({"CONFLICT", "UNKNOWN"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_CANDIDATES = 4096
_MAX_PROVENANCE_REFS = 4096
_MAX_MICROS = 1_000_000
_MAX_BUDGET = 2**31 - 1


class GWTWorkspaceError(ValueError):
    """Fail-closed GWT selection/broadcast contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise GWTWorkspaceError(f"{name} must be a string")
    if not value or value != value.strip():
        raise GWTWorkspaceError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise GWTWorkspaceError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GWTWorkspaceError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise GWTWorkspaceError(f"{name} must be a non-negative integer")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_MICROS:
        raise GWTWorkspaceError(f"{name} must be an integer in [0, {_MAX_MICROS}]")
    return value


def _budget(name: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_BUDGET:
        raise GWTWorkspaceError(
            f"{name} must be an integer in [{minimum}, {_MAX_BUDGET}]"
        )
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GWTWorkspaceError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GWTWorkspaceError(f"{name} must be an iterable of reference strings")
    refs = tuple(_identifier(name, item) for item in values)
    if require_nonempty and not refs:
        raise GWTWorkspaceError(f"{name} must contain at least one reference")
    if len(refs) > _MAX_PROVENANCE_REFS:
        raise GWTWorkspaceError(f"{name} exceeds {_MAX_PROVENANCE_REFS} references")
    if len(set(refs)) != len(refs):
        raise GWTWorkspaceError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


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
        raise GWTWorkspaceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkspaceCandidate:
    """One explicit candidate for workspace competition; never a truth claim."""

    schema: str
    candidate_id: str
    payload_ref: str
    epistemic_class: str
    salience_micros: int
    goal_relevance_micros: int
    uncertainty_micros: int
    information_gain_micros: int
    cost_units: int
    provenance_refs: tuple[str, ...]
    classification: str = "COGNITION_CANDIDATE_NOT_WORLD_TRUTH_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != WORKSPACE_CANDIDATE_SCHEMA:
            raise GWTWorkspaceError("workspace candidate schema mismatch")
        object.__setattr__(self, "candidate_id", _identifier("candidate_id", self.candidate_id))
        object.__setattr__(self, "payload_ref", _identifier("payload_ref", self.payload_ref))
        if self.epistemic_class not in _EPISTEMIC_CLASSES:
            raise GWTWorkspaceError(
                f"epistemic_class must be one of {sorted(_EPISTEMIC_CLASSES)}"
            )
        _micros("salience_micros", self.salience_micros)
        _micros("goal_relevance_micros", self.goal_relevance_micros)
        _micros("uncertainty_micros", self.uncertainty_micros)
        _micros("information_gain_micros", self.information_gain_micros)
        _budget("cost_units", self.cost_units)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        payload_ref: str,
        epistemic_class: str,
        salience_micros: int,
        goal_relevance_micros: int,
        uncertainty_micros: int,
        information_gain_micros: int,
        cost_units: int,
        provenance_refs: Iterable[str],
    ) -> "WorkspaceCandidate":
        return cls(
            schema=WORKSPACE_CANDIDATE_SCHEMA,
            candidate_id=candidate_id,
            payload_ref=payload_ref,
            epistemic_class=epistemic_class,
            salience_micros=salience_micros,
            goal_relevance_micros=goal_relevance_micros,
            uncertainty_micros=uncertainty_micros,
            information_gain_micros=information_gain_micros,
            cost_units=cost_units,
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    """Explicit integer-only workspace competition policy."""

    schema: str
    policy_id: str
    generation: int
    salience_weight: int
    goal_relevance_weight: int
    uncertainty_weight: int
    information_gain_weight: int
    cost_weight: int
    max_selected: int
    max_total_cost_units: int
    provenance_refs: tuple[str, ...]
    classification: str = "EXPLICIT_SELECTION_POLICY_NOT_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != SELECTION_POLICY_SCHEMA:
            raise GWTWorkspaceError("selection policy schema mismatch")
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        for name in (
            "salience_weight",
            "goal_relevance_weight",
            "uncertainty_weight",
            "information_gain_weight",
            "cost_weight",
        ):
            _micros(name, getattr(self, name))
        _budget("max_selected", self.max_selected, minimum=1)
        if self.max_selected > _MAX_CANDIDATES:
            raise GWTWorkspaceError(f"max_selected exceeds {_MAX_CANDIDATES}")
        _budget("max_total_cost_units", self.max_total_cost_units)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        salience_weight: int,
        goal_relevance_weight: int,
        uncertainty_weight: int,
        information_gain_weight: int,
        cost_weight: int,
        max_selected: int,
        max_total_cost_units: int,
        provenance_refs: Iterable[str],
    ) -> "SelectionPolicy":
        return cls(
            schema=SELECTION_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            salience_weight=salience_weight,
            goal_relevance_weight=goal_relevance_weight,
            uncertainty_weight=uncertainty_weight,
            information_gain_weight=information_gain_weight,
            cost_weight=cost_weight,
            max_selected=max_selected,
            max_total_cost_units=max_total_cost_units,
            provenance_refs=tuple(provenance_refs),
        )

    def score(self, candidate: WorkspaceCandidate) -> int:
        if type(candidate) is not WorkspaceCandidate:
            raise GWTWorkspaceError("candidate must be concrete WorkspaceCandidate")
        return (
            self.salience_weight * candidate.salience_micros
            + self.goal_relevance_weight * candidate.goal_relevance_micros
            + self.uncertainty_weight * candidate.uncertainty_micros
            + self.information_gain_weight * candidate.information_gain_micros
            - self.cost_weight * candidate.cost_units
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class SelectedCandidate:
    candidate_id: str
    candidate_sha256: str
    payload_ref: str
    epistemic_class: str
    rank_score: int
    cost_units: int
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _identifier("candidate_id", self.candidate_id))
        object.__setattr__(
            self, "candidate_sha256", _sha256("candidate_sha256", self.candidate_sha256)
        )
        object.__setattr__(self, "payload_ref", _identifier("payload_ref", self.payload_ref))
        if self.epistemic_class not in _EPISTEMIC_CLASSES:
            raise GWTWorkspaceError("selected candidate epistemic class mismatch")
        if type(self.rank_score) is not int:
            raise GWTWorkspaceError("rank_score must be an integer")
        _budget("cost_units", self.cost_units)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkspaceSelection:
    schema: str
    selection_id: str
    frame_id: str
    frame_generation: int
    frame_sha256: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    hyperposition_id: str | None
    hyperposition_generation: int | None
    hyperposition_sha256: str | None
    selected: tuple[SelectedCandidate, ...]
    unresolved_candidate_ids: tuple[str, ...]
    total_cost_units: int
    provenance_refs: tuple[str, ...]
    classification: str = "WORKSPACE_SELECTION_CANDIDATE_COORDINATION_NOT_DECISION_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != WORKSPACE_SELECTION_SCHEMA:
            raise GWTWorkspaceError("workspace selection schema mismatch")
        object.__setattr__(self, "selection_id", _identifier("selection_id", self.selection_id))
        object.__setattr__(self, "frame_id", _identifier("frame_id", self.frame_id))
        object.__setattr__(self, "frame_generation", _generation("frame_generation", self.frame_generation))
        object.__setattr__(self, "frame_sha256", _sha256("frame_sha256", self.frame_sha256))
        object.__setattr__(self, "plan_id", _identifier("plan_id", self.plan_id))
        object.__setattr__(self, "plan_generation", _generation("plan_generation", self.plan_generation))
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(self, "policy_generation", _generation("policy_generation", self.policy_generation))
        object.__setattr__(self, "policy_sha256", _sha256("policy_sha256", self.policy_sha256))
        hp_values = (self.hyperposition_id, self.hyperposition_generation, self.hyperposition_sha256)
        if any(value is None for value in hp_values) and not all(value is None for value in hp_values):
            raise GWTWorkspaceError("hyperposition binding must be fully present or fully absent")
        if self.hyperposition_id is not None:
            object.__setattr__(
                self,
                "hyperposition_id",
                _identifier("hyperposition_id", self.hyperposition_id),
            )
            object.__setattr__(
                self,
                "hyperposition_generation",
                _generation("hyperposition_generation", self.hyperposition_generation),
            )
            object.__setattr__(
                self,
                "hyperposition_sha256",
                _sha256("hyperposition_sha256", self.hyperposition_sha256),
            )
        if not self.selected or not all(type(item) is SelectedCandidate for item in self.selected):
            raise GWTWorkspaceError("selected must contain SelectedCandidate values")
        ids = tuple(item.candidate_id for item in self.selected)
        if len(ids) != len(set(ids)):
            raise GWTWorkspaceError("selected contains duplicate candidate identities")
        unresolved = tuple(_identifier("unresolved_candidate_id", item) for item in self.unresolved_candidate_ids)
        if len(unresolved) != len(set(unresolved)):
            raise GWTWorkspaceError("unresolved_candidate_ids contains duplicates")
        object.__setattr__(self, "unresolved_candidate_ids", tuple(sorted(unresolved)))
        _budget("total_cost_units", self.total_cost_units)
        if self.total_cost_units != sum(item.cost_units for item in self.selected):
            raise GWTWorkspaceError("total_cost_units does not match selected candidates")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "selection_id": self.selection_id,
            "frame_id": self.frame_id,
            "frame_generation": self.frame_generation,
            "frame_sha256": self.frame_sha256,
            "plan_id": self.plan_id,
            "plan_generation": self.plan_generation,
            "plan_sha256": self.plan_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "hyperposition_id": self.hyperposition_id,
            "hyperposition_generation": self.hyperposition_generation,
            "hyperposition_sha256": self.hyperposition_sha256,
            "selected": [item.as_dict() for item in self.selected],
            "unresolved_candidate_ids": list(self.unresolved_candidate_ids),
            "total_cost_units": self.total_cost_units,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "broadcast_uptake_claimed": False,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class BroadcastEnvelope:
    schema: str
    broadcast_id: str
    selection_id: str
    selection_sha256: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    recipient_cell_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str = "LOGICAL_GWT_BROADCAST_NOT_DELIVERY_UPTAKE_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != BROADCAST_ENVELOPE_SCHEMA:
            raise GWTWorkspaceError("broadcast envelope schema mismatch")
        object.__setattr__(self, "broadcast_id", _identifier("broadcast_id", self.broadcast_id))
        object.__setattr__(self, "selection_id", _identifier("selection_id", self.selection_id))
        object.__setattr__(
            self, "selection_sha256", _sha256("selection_sha256", self.selection_sha256)
        )
        object.__setattr__(self, "plan_id", _identifier("plan_id", self.plan_id))
        object.__setattr__(self, "plan_generation", _generation("plan_generation", self.plan_generation))
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        recipients = tuple(self.recipient_cell_ids)
        if len(recipients) != len(set(recipients)):
            raise GWTWorkspaceError("recipient_cell_ids contains duplicate recipients")
        if set(recipients) != set(GRID10_CELL_IDS) or len(recipients) != len(GRID10_CELL_IDS):
            raise GWTWorkspaceError("broadcast must address each logical GRID10 cell G1..G10 exactly once")
        object.__setattr__(self, "recipient_cell_ids", GRID10_CELL_IDS)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "delivery_observed": False,
            "uptake_observed": False,
            "effect_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _normalize_candidates(values: Iterable[WorkspaceCandidate]) -> tuple[WorkspaceCandidate, ...]:
    if isinstance(values, (str, bytes)):
        raise GWTWorkspaceError("candidates must be an iterable of WorkspaceCandidate")
    candidates = tuple(values)
    if not candidates:
        raise GWTWorkspaceError("candidates must contain at least one candidate")
    if len(candidates) > _MAX_CANDIDATES:
        raise GWTWorkspaceError(f"candidate count exceeds {_MAX_CANDIDATES}")
    if any(type(item) is not WorkspaceCandidate for item in candidates):
        raise GWTWorkspaceError("candidates must contain concrete WorkspaceCandidate values")
    ids = [item.candidate_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise GWTWorkspaceError("duplicate candidate identity")
    return tuple(sorted(candidates, key=lambda item: item.candidate_id))


def select_workspace(
    *,
    selection_id: str,
    frame: SituationFrame,
    plan: Grid10Plan,
    policy: SelectionPolicy,
    candidates: Iterable[WorkspaceCandidate],
    hyperposition: Hyperposition | None = None,
    provenance_refs: Iterable[str],
) -> WorkspaceSelection:
    """Select a bounded deterministic workspace from explicit candidate metadata only."""
    if type(frame) is not SituationFrame:
        raise GWTWorkspaceError("frame must be concrete SituationFrame")
    if type(plan) is not Grid10Plan:
        raise GWTWorkspaceError("plan must be concrete Grid10Plan")
    if type(policy) is not SelectionPolicy:
        raise GWTWorkspaceError("policy must be concrete SelectionPolicy")

    plan.assert_frame_binding(
        frame_id=frame.frame_id,
        generation=frame.generation,
        sha256=frame.sha256(),
    )
    if policy.max_total_cost_units > plan.max_total_work_units:
        raise GWTWorkspaceError("selection policy cost budget exceeds GRID10 plan total-work budget")

    hp_id: str | None = None
    hp_generation: int | None = None
    hp_sha256: str | None = None
    if hyperposition is not None:
        if type(hyperposition) is not Hyperposition:
            raise GWTWorkspaceError("hyperposition must be concrete Hyperposition")
        if (
            hyperposition.situation_frame_ref is not None
            and hyperposition.situation_frame_ref != frame.frame_id
        ):
            raise GWTWorkspaceError("hyperposition SituationFrame binding mismatch")
        hp_id = hyperposition.hyperposition_id
        hp_generation = hyperposition.generation
        hp_sha256 = hyperposition.sha256()

    normalized = _normalize_candidates(candidates)
    ranked = tuple(sorted(normalized, key=lambda item: (-policy.score(item), item.candidate_id)))
    chosen = ranked[: min(policy.max_selected, len(ranked))]
    total_cost = sum(item.cost_units for item in chosen)
    if total_cost > policy.max_total_cost_units:
        raise GWTWorkspaceError("deterministic selected set exceeds explicit selection cost budget")
    if total_cost > plan.max_total_work_units:
        raise GWTWorkspaceError("deterministic selected set exceeds GRID10 plan total-work budget")

    selected = tuple(
        SelectedCandidate(
            candidate_id=item.candidate_id,
            candidate_sha256=item.sha256(),
            payload_ref=item.payload_ref,
            epistemic_class=item.epistemic_class,
            rank_score=policy.score(item),
            cost_units=item.cost_units,
            provenance_refs=item.provenance_refs,
        )
        for item in chosen
    )
    unresolved = tuple(
        item.candidate_id for item in normalized if item.epistemic_class in _UNRESOLVED_CLASSES
    )
    return WorkspaceSelection(
        schema=WORKSPACE_SELECTION_SCHEMA,
        selection_id=selection_id,
        frame_id=frame.frame_id,
        frame_generation=frame.generation,
        frame_sha256=frame.sha256(),
        plan_id=plan.plan_id,
        plan_generation=plan.generation,
        plan_sha256=plan.sha256(),
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        hyperposition_id=hp_id,
        hyperposition_generation=hp_generation,
        hyperposition_sha256=hp_sha256,
        selected=selected,
        unresolved_candidate_ids=unresolved,
        total_cost_units=total_cost,
        provenance_refs=tuple(provenance_refs),
    )


def create_broadcast(
    *,
    broadcast_id: str,
    selection: WorkspaceSelection,
    plan: Grid10Plan,
    recipient_cell_ids: Iterable[str] = GRID10_CELL_IDS,
    provenance_refs: Iterable[str],
) -> BroadcastEnvelope:
    """Create a logical broadcast envelope; this does not prove delivery or uptake."""
    if type(selection) is not WorkspaceSelection:
        raise GWTWorkspaceError("selection must be concrete WorkspaceSelection")
    if type(plan) is not Grid10Plan:
        raise GWTWorkspaceError("plan must be concrete Grid10Plan")
    if selection.plan_id != plan.plan_id:
        raise GWTWorkspaceError("broadcast GRID10 plan_id mismatch")
    if selection.plan_generation != plan.generation:
        raise GWTWorkspaceError("broadcast GRID10 plan generation mismatch")
    if selection.plan_sha256 != plan.sha256():
        raise GWTWorkspaceError("broadcast GRID10 plan digest mismatch")
    return BroadcastEnvelope(
        schema=BROADCAST_ENVELOPE_SCHEMA,
        broadcast_id=broadcast_id,
        selection_id=selection.selection_id,
        selection_sha256=selection.sha256(),
        plan_id=plan.plan_id,
        plan_generation=plan.generation,
        plan_sha256=plan.sha256(),
        recipient_cell_ids=tuple(recipient_cell_ids),
        provenance_refs=tuple(provenance_refs),
    )


__all__ = [
    "BROADCAST_ENVELOPE_SCHEMA",
    "SELECTION_POLICY_SCHEMA",
    "WORKSPACE_CANDIDATE_SCHEMA",
    "WORKSPACE_SELECTION_SCHEMA",
    "BroadcastEnvelope",
    "GWTWorkspaceError",
    "SelectedCandidate",
    "SelectionPolicy",
    "WorkspaceCandidate",
    "WorkspaceSelection",
    "create_broadcast",
    "select_workspace",
]
