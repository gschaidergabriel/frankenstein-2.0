"""Deterministic Goal lifecycle primitive for Frankenstein 2.0.

F2-WP-204 generation 2 fail-closed hardening.

Public GoalState construction admits explicit caller-supplied CANDIDATE records only.
Non-CANDIDATE lifecycle state can only be materialized by a validated GoalState.apply()
transition. No generic persistence rehydration shortcut is admitted in this generation.

Promotion into TRIAL/ACTIVE requires typed caller:/control-plane:/external: adoption
authority evidence. Each mutation patch and transition receipt binds exactly one goal.
Duplicate provenance/evidence/transition references fail closed before canonical sorting.

This component does not infer goals, auto-adopt model output, evaluate wake conditions,
choose Persistent Pulse actions, authorize or execute effects, read/write UnifiedDB,
infer world facts, or mint verified completion.

GOAL_GENERATION != GOAL_ADOPTION != EFFECT_AUTHORIZATION != COMPLETION_VERIFICATION.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
from typing import Any, Iterable

GOAL_STATE_SCHEMA = "FRANKENSTEIN2_GOAL_STATE/v1"
GOAL_PATCH_SCHEMA = "FRANKENSTEIN2_GOAL_STATE_PATCH/v1"
GOAL_TRANSITION_SCHEMA = "FRANKENSTEIN2_GOAL_STATE_TRANSITION/v1"

GOAL_CANDIDATE = "CANDIDATE"
GOAL_TRIAL = "TRIAL"
GOAL_ACTIVE = "ACTIVE"
GOAL_HOLD = "HOLD"
GOAL_DROPPED = "DROPPED"
_ALLOWED_STATUSES = frozenset(
    {GOAL_CANDIDATE, GOAL_TRIAL, GOAL_ACTIVE, GOAL_HOLD, GOAL_DROPPED}
)
_ALLOWED_TRANSITIONS = {
    GOAL_CANDIDATE: frozenset({GOAL_TRIAL, GOAL_ACTIVE, GOAL_HOLD, GOAL_DROPPED}),
    GOAL_TRIAL: frozenset({GOAL_ACTIVE, GOAL_HOLD, GOAL_DROPPED}),
    GOAL_ACTIVE: frozenset({GOAL_HOLD, GOAL_DROPPED}),
    GOAL_HOLD: frozenset({GOAL_TRIAL, GOAL_ACTIVE, GOAL_DROPPED}),
    GOAL_DROPPED: frozenset(),
}
_ADOPTION_REF_PREFIXES = ("caller:", "control-plane:", "external:")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_TEXT_LEN = 4096
_STATE_CLASSIFICATION = "EXPLICIT_GOAL_LIFECYCLE_STATE_NOT_WORLD_TRUTH_OR_COMPLETION"
_TRANSITION_CLASSIFICATION = "PURE_GOAL_LIFECYCLE_TRANSITION_NOT_EFFECT_OR_COMPLETION"


class GoalLifecycleError(ValueError):
    """Fail-closed Goal lifecycle contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise GoalLifecycleError(f"{name} must be a string")
    if not value or value != value.strip():
        raise GoalLifecycleError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise GoalLifecycleError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GoalLifecycleError(f"{name} contains control characters")
    return value


def _text(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) > _MAX_TEXT_LEN:
        raise GoalLifecycleError(f"{name} exceeds {_MAX_TEXT_LEN} characters")
    return value


def _ppm(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise GoalLifecycleError(f"{name} must be an integer in [0, 1000000]")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise GoalLifecycleError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GoalLifecycleError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(
    name: str,
    values: Iterable[str],
    *,
    require_nonempty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GoalLifecycleError(f"{name} must be an iterable of reference strings")
    raw = tuple(_identifier(name, value) for value in values)
    if len(raw) != len(set(raw)):
        raise GoalLifecycleError(f"{name} contains duplicate references")
    cleaned = tuple(sorted(raw))
    if require_nonempty and not cleaned:
        raise GoalLifecycleError(f"{name} must contain at least one explicit reference")
    return cleaned


def _require_adoption_authority(next_status: str, evidence_refs: tuple[str, ...]) -> None:
    if next_status not in {GOAL_TRIAL, GOAL_ACTIVE}:
        return
    invalid = tuple(ref for ref in evidence_refs if not ref.startswith(_ADOPTION_REF_PREFIXES))
    if invalid:
        raise GoalLifecycleError(
            "promotion into TRIAL/ACTIVE requires typed "
            "caller:/control-plane:/external: adoption-authority evidence; "
            "self/model/untyped evidence is forbidden"
        )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GoalRecord:
    goal_id: str
    summary: str
    priority_ppm: int
    provenance_refs: tuple[str, ...]
    status: str = GOAL_CANDIDATE

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _identifier("goal_id", self.goal_id))
        object.__setattr__(self, "summary", _text("goal summary", self.summary))
        object.__setattr__(self, "priority_ppm", _ppm("priority_ppm", self.priority_ppm))
        object.__setattr__(self, "provenance_refs", _refs("goal provenance_ref", self.provenance_refs))
        if self.status not in _ALLOWED_STATUSES:
            raise GoalLifecycleError(f"unsupported goal status: {self.status!r}")

    @classmethod
    def candidate(cls, *, goal_id: str, summary: str, priority_ppm: int, provenance_refs: Iterable[str]) -> "GoalRecord":
        return cls(goal_id=goal_id, summary=summary, priority_ppm=priority_ppm, provenance_refs=tuple(provenance_refs), status=GOAL_CANDIDATE)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique_goals(goals: Iterable[GoalRecord], *, candidates_only: bool = False) -> tuple[GoalRecord, ...]:
    mapping: dict[str, GoalRecord] = {}
    for goal in goals:
        if not isinstance(goal, GoalRecord):
            raise GoalLifecycleError("goals must contain GoalRecord values")
        if candidates_only and goal.status != GOAL_CANDIDATE:
            raise GoalLifecycleError(
                "public GoalState construction accepts CANDIDATE goals only; "
                "non-candidate state requires admitted lifecycle evolution"
            )
        if goal.goal_id in mapping:
            raise GoalLifecycleError(f"duplicate goal_id: {goal.goal_id}")
        mapping[goal.goal_id] = goal
    return tuple(mapping[key] for key in sorted(mapping))


@dataclass(frozen=True, slots=True)
class GoalStatusChange:
    goal_id: str
    expected_status: str
    next_status: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _identifier("goal_id", self.goal_id))
        if self.expected_status not in _ALLOWED_STATUSES:
            raise GoalLifecycleError(f"unsupported expected_status: {self.expected_status!r}")
        if self.next_status not in _ALLOWED_STATUSES:
            raise GoalLifecycleError(f"unsupported next_status: {self.next_status!r}")
        if self.next_status == self.expected_status:
            raise GoalLifecycleError("goal status change must change status")
        if self.next_status not in _ALLOWED_TRANSITIONS[self.expected_status]:
            raise GoalLifecycleError(f"illegal goal transition: {self.expected_status} -> {self.next_status}")
        refs = _refs("goal transition evidence_ref", self.evidence_refs)
        _require_adoption_authority(self.next_status, refs)
        object.__setattr__(self, "evidence_refs", refs)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GoalStatePatch:
    schema: str
    transition_id: str
    expected_state_id: str
    expected_generation: int
    expected_state_sha256: str
    next_generation: int
    transition_refs: tuple[str, ...]
    add_candidates: tuple[GoalRecord, ...] = ()
    status_changes: tuple[GoalStatusChange, ...] = ()

    def __post_init__(self) -> None:
        if self.schema != GOAL_PATCH_SCHEMA:
            raise GoalLifecycleError("goal patch schema mismatch")
        object.__setattr__(self, "transition_id", _identifier("transition_id", self.transition_id))
        object.__setattr__(self, "expected_state_id", _identifier("expected_state_id", self.expected_state_id))
        object.__setattr__(self, "expected_generation", _generation(self.expected_generation))
        object.__setattr__(self, "expected_state_sha256", _sha256("expected_state_sha256", self.expected_state_sha256))
        object.__setattr__(self, "next_generation", _generation(self.next_generation))
        if self.next_generation != self.expected_generation + 1:
            raise GoalLifecycleError("next_generation must equal expected_generation + 1")
        object.__setattr__(self, "transition_refs", _refs("transition_ref", self.transition_refs))
        candidates = _unique_goals(self.add_candidates, candidates_only=True)
        object.__setattr__(self, "add_candidates", candidates)
        changes_by_goal: dict[str, GoalStatusChange] = {}
        for change in self.status_changes:
            if not isinstance(change, GoalStatusChange):
                raise GoalLifecycleError("status_changes must contain GoalStatusChange values")
            if change.goal_id in changes_by_goal:
                raise GoalLifecycleError(f"duplicate status change for goal_id: {change.goal_id}")
            changes_by_goal[change.goal_id] = change
        object.__setattr__(self, "status_changes", tuple(changes_by_goal[key] for key in sorted(changes_by_goal)))
        if {goal.goal_id for goal in candidates} & set(changes_by_goal):
            raise GoalLifecycleError("a goal cannot be added and lifecycle-transitioned in the same patch")
        affected_goal_count = len(candidates) + len(changes_by_goal)
        if affected_goal_count == 0:
            raise GoalLifecycleError("goal patch must contain at least one explicit change")
        if affected_goal_count != 1:
            raise GoalLifecycleError("each goal lifecycle patch/receipt must bind exactly one goal")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "transition_id": self.transition_id,
            "expected_state_id": self.expected_state_id,
            "expected_generation": self.expected_generation,
            "expected_state_sha256": self.expected_state_sha256,
            "next_generation": self.next_generation,
            "transition_refs": list(self.transition_refs),
            "add_candidates": [goal.as_dict() for goal in self.add_candidates],
            "status_changes": [change.as_dict() for change in self.status_changes],
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class GoalStateTransition:
    schema: str
    transition_id: str
    state_id: str
    before_generation: int
    after_generation: int
    before_state_sha256: str
    after_state_sha256: str
    patch_sha256: str
    transition_refs: tuple[str, ...]
    added_goal_ids: tuple[str, ...]
    changed_goal_ids: tuple[str, ...]
    classification: str = _TRANSITION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != GOAL_TRANSITION_SCHEMA:
            raise GoalLifecycleError("goal transition schema mismatch")
        object.__setattr__(self, "transition_id", _identifier("transition_id", self.transition_id))
        object.__setattr__(self, "state_id", _identifier("state_id", self.state_id))
        object.__setattr__(self, "before_generation", _generation(self.before_generation))
        object.__setattr__(self, "after_generation", _generation(self.after_generation))
        if self.after_generation != self.before_generation + 1:
            raise GoalLifecycleError("transition after_generation must equal before_generation + 1")
        object.__setattr__(self, "before_state_sha256", _sha256("before_state_sha256", self.before_state_sha256))
        object.__setattr__(self, "after_state_sha256", _sha256("after_state_sha256", self.after_state_sha256))
        object.__setattr__(self, "patch_sha256", _sha256("patch_sha256", self.patch_sha256))
        object.__setattr__(self, "transition_refs", _refs("transition_ref", self.transition_refs))
        added = _refs("added_goal_id", self.added_goal_ids, require_nonempty=False)
        changed = _refs("changed_goal_id", self.changed_goal_ids, require_nonempty=False)
        if set(added) & set(changed):
            raise GoalLifecycleError("goal receipt cannot both add and transition the same goal")
        if len(added) + len(changed) != 1:
            raise GoalLifecycleError("each goal lifecycle transition receipt must bind exactly one goal")
        if self.classification != _TRANSITION_CLASSIFICATION:
            raise GoalLifecycleError("goal transition classification is fixed")
        object.__setattr__(self, "added_goal_ids", added)
        object.__setattr__(self, "changed_goal_ids", changed)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class GoalState:
    schema: str
    state_id: str
    generation: int
    goals: tuple[GoalRecord, ...]
    classification: str

    def __init__(self, *, schema: str, state_id: str, generation: int, goals: Iterable[GoalRecord], classification: str = _STATE_CLASSIFICATION) -> None:
        if schema != GOAL_STATE_SCHEMA:
            raise GoalLifecycleError("goal state schema mismatch")
        state_id = _identifier("state_id", state_id)
        generation = _generation(generation)
        goals_tuple = _unique_goals(goals, candidates_only=True)
        if classification != _STATE_CLASSIFICATION:
            raise GoalLifecycleError("goal state classification is fixed")
        object.__setattr__(self, "schema", GOAL_STATE_SCHEMA)
        object.__setattr__(self, "state_id", state_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "goals", goals_tuple)
        object.__setattr__(self, "classification", _STATE_CLASSIFICATION)

    @classmethod
    def create(cls, *, state_id: str, generation: int = 0, goals: Iterable[GoalRecord] = ()) -> "GoalState":
        return cls(schema=GOAL_STATE_SCHEMA, state_id=state_id, generation=generation, goals=tuple(goals))

    @classmethod
    def _from_validated_evolution(cls, *, state_id: str, generation: int, goals: Iterable[GoalRecord]) -> "GoalState":
        state_id = _identifier("state_id", state_id)
        generation = _generation(generation)
        goals_tuple = _unique_goals(goals)
        instance = object.__new__(cls)
        object.__setattr__(instance, "schema", GOAL_STATE_SCHEMA)
        object.__setattr__(instance, "state_id", state_id)
        object.__setattr__(instance, "generation", generation)
        object.__setattr__(instance, "goals", goals_tuple)
        object.__setattr__(instance, "classification", _STATE_CLASSIFICATION)
        return instance

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "state_id": self.state_id, "generation": self.generation, "goals": [goal.as_dict() for goal in self.goals], "classification": self.classification}

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def apply(self, patch: GoalStatePatch) -> tuple["GoalState", GoalStateTransition]:
        if not isinstance(patch, GoalStatePatch):
            raise GoalLifecycleError("patch must be a GoalStatePatch")
        if patch.expected_state_id != self.state_id:
            raise GoalLifecycleError("goal state_id mismatch")
        if patch.expected_generation != self.generation:
            raise GoalLifecycleError("stale goal-state generation")
        before_sha = self.sha256()
        if patch.expected_state_sha256 != before_sha:
            raise GoalLifecycleError("stale or mismatched goal-state digest")
        goals = {goal.goal_id: goal for goal in self.goals}
        for candidate in patch.add_candidates:
            if candidate.goal_id in goals:
                raise GoalLifecycleError(f"cannot add existing goal candidate: {candidate.goal_id}")
            goals[candidate.goal_id] = candidate
        changed: list[str] = []
        for change in patch.status_changes:
            current = goals.get(change.goal_id)
            if current is None:
                raise GoalLifecycleError(f"cannot transition unknown goal: {change.goal_id}")
            if current.status != change.expected_status:
                raise GoalLifecycleError(f"goal {change.goal_id} status mismatch: expected {change.expected_status}, actual {current.status}")
            goals[change.goal_id] = replace(current, status=change.next_status)
            changed.append(change.goal_id)
        next_state = GoalState._from_validated_evolution(state_id=self.state_id, generation=patch.next_generation, goals=tuple(goals.values()))
        after_sha = next_state.sha256()
        if after_sha == before_sha:
            raise GoalLifecycleError("goal patch produced no state delta")
        receipt = GoalStateTransition(
            schema=GOAL_TRANSITION_SCHEMA,
            transition_id=patch.transition_id,
            state_id=self.state_id,
            before_generation=self.generation,
            after_generation=next_state.generation,
            before_state_sha256=before_sha,
            after_state_sha256=after_sha,
            patch_sha256=patch.sha256(),
            transition_refs=patch.transition_refs,
            added_goal_ids=tuple(goal.goal_id for goal in patch.add_candidates),
            changed_goal_ids=tuple(sorted(changed)),
        )
        return next_state, receipt


__all__ = [
    "GOAL_ACTIVE", "GOAL_CANDIDATE", "GOAL_DROPPED", "GOAL_HOLD", "GOAL_PATCH_SCHEMA",
    "GOAL_STATE_SCHEMA", "GOAL_TRANSITION_SCHEMA", "GOAL_TRIAL", "GoalLifecycleError",
    "GoalRecord", "GoalState", "GoalStatePatch", "GoalStateTransition", "GoalStatusChange",
]
