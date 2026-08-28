"""Persistent Agency Kernel integration for Frankenstein 2.0.

F2-WP-206 generation 1.

This module is a deterministic integration boundary over already-bounded components. It
stores WP-206-owned checkpoint rows inside the *existing* canonical UnifiedDB selected by
F2-WP-100. UnifiedDB file identity remains authority/provenance evidence and is deliberately
not reused as Agency checkpoint state identity.

Adopted goals are never reconstructed by directly constructing a non-CANDIDATE GoalState.
The public replay envelope starts from a candidate-only genesis and replays exact,
digest-fenced GoalStatePatch values through GoalState.apply().

Persistent Pulse decisions are never persisted or trusted across restart. Only immutable
PulseInput is checkpointed; eligibility is recomputed after restart. Wake evaluation remains
epistemic and never becomes scheduler/effect/completion authority.

No model/provider/tool invocation, world-fact inference, scheduler authority, effect execution,
or completion minting exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from frankenstein2.agency_state import (
    AGENCY_STATE_SCHEMA,
    AgencyState,
    DeferredIntent,
    Interest,
    OpenLoop,
)
from frankenstein2.goal_lifecycle import (
    GOAL_CANDIDATE,
    GOAL_PATCH_SCHEMA,
    GOAL_STATE_SCHEMA,
    GoalRecord,
    GoalState,
    GoalStatePatch,
    GoalStatusChange,
)
from frankenstein2.persistent_pulse import (
    PULSE_INPUT_SCHEMA,
    PulseDecision,
    PulseInput,
    classify_pulse_eligibility,
)
from frankenstein2.state_fingerprint import (
    CLASSIFICATION as FINGERPRINT_CLASSIFICATION,
    PROFILE as FINGERPRINT_PROFILE,
    StateFingerprint,
    fingerprint_state_projection,
    identity_changed,
    projection_changed,
)
from frankenstein2.wake_hold import (
    HOLD_CHECKPOINT_SCHEMA,
    HoldCheckpoint,
    WakeCondition,
    WakeEvaluation,
    WakeObservation,
    evaluate_wake,
)
from state.unifieddb_identity import (
    FINGERPRINT_SCHEMA as UNIFIEDDB_FINGERPRINT_SCHEMA,
    RESOLUTION_SCHEMA as UNIFIEDDB_RESOLUTION_SCHEMA,
    UnifiedDBFingerprint,
    UnifiedDBResolution,
)

CHECKPOINT_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_CHECKPOINT/v1"
GOAL_REPLAY_SCHEMA = "FRANKENSTEIN2_GOAL_LIFECYCLE_REPLAY/v1"
NEXT_TICK_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_NEXT_TICK/v1"
PROJECTION_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_PROJECTION/v1"
STORE_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_STORE/v1"
CHECKPOINT_TABLE = "f2_persistent_agency_checkpoints"

CHANGE_POLICY_PROJECTION = "PROJECTION_CHANGED"
CHANGE_POLICY_IDENTITY = "IDENTITY_CHANGED"
_ALLOWED_CHANGE_POLICIES = frozenset(
    {CHANGE_POLICY_PROJECTION, CHANGE_POLICY_IDENTITY}
)
_MAX_ID_LEN = 512


class PersistentAgencyError(RuntimeError):
    """Fail-closed Persistent Agency integration error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise PersistentAgencyError(f"{name} must be a string")
    if not value or value != value.strip():
        raise PersistentAgencyError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise PersistentAgencyError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PersistentAgencyError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PersistentAgencyError("generation must be a non-negative integer")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PersistentAgencyError("provenance_refs must be an iterable of strings")
    raw = tuple(_identifier("provenance_ref", value) for value in values)
    if not raw:
        raise PersistentAgencyError("provenance_refs must be non-empty")
    if len(set(raw)) != len(raw):
        raise PersistentAgencyError("provenance_refs contain duplicates")
    return tuple(sorted(raw))


def _mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PersistentAgencyError(f"{name} must be a JSON object")
    return value


def _expect_keys(name: str, value: Mapping[str, Any], expected: set[str]) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PersistentAgencyError(
            f"{name} field mismatch missing={missing} extra={extra}"
        )


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


def _decode_goal_record_candidate(raw: Any) -> GoalRecord:
    value = _mapping("goal candidate", raw)
    _expect_keys(
        "goal candidate",
        value,
        {"goal_id", "summary", "priority_ppm", "provenance_refs", "status"},
    )
    if value["status"] != GOAL_CANDIDATE:
        raise PersistentAgencyError(
            "goal replay genesis/add_candidates must contain CANDIDATE goals only"
        )
    return GoalRecord.candidate(
        goal_id=value["goal_id"],
        summary=value["summary"],
        priority_ppm=value["priority_ppm"],
        provenance_refs=tuple(value["provenance_refs"]),
    )


def _decode_goal_patch(raw: Any) -> GoalStatePatch:
    value = _mapping("goal patch", raw)
    _expect_keys(
        "goal patch",
        value,
        {
            "schema",
            "transition_id",
            "expected_state_id",
            "expected_generation",
            "expected_state_sha256",
            "next_generation",
            "transition_refs",
            "add_candidates",
            "status_changes",
        },
    )
    if value["schema"] != GOAL_PATCH_SCHEMA:
        raise PersistentAgencyError("goal patch schema mismatch in replay envelope")
    add_candidates = tuple(
        _decode_goal_record_candidate(item) for item in value["add_candidates"]
    )
    changes: list[GoalStatusChange] = []
    for raw_change in value["status_changes"]:
        change = _mapping("goal status change", raw_change)
        _expect_keys(
            "goal status change",
            change,
            {
                "goal_id",
                "expected_status",
                "next_status",
                "evidence_refs",
                "adoption_authority_ref",
            },
        )
        changes.append(
            GoalStatusChange(
                goal_id=change["goal_id"],
                expected_status=change["expected_status"],
                next_status=change["next_status"],
                evidence_refs=tuple(change["evidence_refs"]),
                adoption_authority_ref=change["adoption_authority_ref"],
            )
        )
    return GoalStatePatch(
        schema=GOAL_PATCH_SCHEMA,
        transition_id=value["transition_id"],
        expected_state_id=value["expected_state_id"],
        expected_generation=value["expected_generation"],
        expected_state_sha256=value["expected_state_sha256"],
        next_generation=value["next_generation"],
        transition_refs=tuple(value["transition_refs"]),
        add_candidates=add_candidates,
        status_changes=tuple(changes),
    )


@dataclass(frozen=True, slots=True)
class GoalReplayEnvelope:
    """Public restart contract that replays only through GoalState.create/apply."""

    schema: str
    genesis: GoalState
    patches: tuple[GoalStatePatch, ...]
    final_generation: int
    final_state_sha256: str
    classification: str = (
        "PUBLIC_VALIDATED_LIFECYCLE_REPLAY_NOT_DIRECT_ADOPTED_STATE_REHYDRATION"
    )

    def __post_init__(self) -> None:
        if self.schema != GOAL_REPLAY_SCHEMA:
            raise PersistentAgencyError("goal replay schema mismatch")
        if not isinstance(self.genesis, GoalState):
            raise PersistentAgencyError("goal replay genesis must be GoalState")
        if self.genesis.generation != 0:
            raise PersistentAgencyError("goal replay genesis generation must be 0")
        if any(goal.status != GOAL_CANDIDATE for goal in self.genesis.goals):
            raise PersistentAgencyError("goal replay genesis must be candidate-only")
        if not isinstance(self.patches, tuple) or any(
            not isinstance(item, GoalStatePatch) for item in self.patches
        ):
            raise PersistentAgencyError("goal replay patches must be a tuple of GoalStatePatch")
        _generation(self.final_generation)
        _identifier("final_state_sha256", self.final_state_sha256)
        if len(self.final_state_sha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.final_state_sha256
        ):
            raise PersistentAgencyError(
                "final_state_sha256 must be lowercase 64-hex SHA-256"
            )
        state = self.replay()
        if state.generation != self.final_generation:
            raise PersistentAgencyError("goal replay final generation mismatch")
        if state.sha256() != self.final_state_sha256:
            raise PersistentAgencyError("goal replay final digest mismatch")

    @classmethod
    def create(
        cls, *, genesis: GoalState, patches: Iterable[GoalStatePatch]
    ) -> "GoalReplayEnvelope":
        if not isinstance(genesis, GoalState):
            raise PersistentAgencyError("goal replay genesis must be GoalState")
        patch_tuple = tuple(patches)
        state = genesis
        for patch in patch_tuple:
            state, _ = state.apply(patch)
        return cls(
            schema=GOAL_REPLAY_SCHEMA,
            genesis=genesis,
            patches=patch_tuple,
            final_generation=state.generation,
            final_state_sha256=state.sha256(),
        )

    def replay(self) -> GoalState:
        state = self.genesis
        for patch in self.patches:
            state, _ = state.apply(patch)
        return state

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "genesis": self.genesis.as_dict(),
            "patches": [patch.as_dict() for patch in self.patches],
            "final_generation": self.final_generation,
            "final_state_sha256": self.final_state_sha256,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())

    @classmethod
    def from_dict(cls, raw: Any) -> "GoalReplayEnvelope":
        value = _mapping("goal replay", raw)
        _expect_keys(
            "goal replay",
            value,
            {
                "schema",
                "genesis",
                "patches",
                "final_generation",
                "final_state_sha256",
                "classification",
            },
        )
        if value["schema"] != GOAL_REPLAY_SCHEMA:
            raise PersistentAgencyError("goal replay schema mismatch")
        if (
            value["classification"]
            != "PUBLIC_VALIDATED_LIFECYCLE_REPLAY_NOT_DIRECT_ADOPTED_STATE_REHYDRATION"
        ):
            raise PersistentAgencyError("goal replay classification mismatch")
        genesis_raw = _mapping("goal replay genesis", value["genesis"])
        _expect_keys(
            "goal replay genesis",
            genesis_raw,
            {"schema", "state_id", "generation", "goals", "classification"},
        )
        if genesis_raw["schema"] != GOAL_STATE_SCHEMA:
            raise PersistentAgencyError("goal replay genesis state schema mismatch")
        if (
            genesis_raw["classification"]
            != "EXPLICIT_GOAL_LIFECYCLE_STATE_NOT_WORLD_TRUTH_OR_COMPLETION"
        ):
            raise PersistentAgencyError("goal replay genesis classification mismatch")
        genesis = GoalState.create(
            state_id=genesis_raw["state_id"],
            generation=genesis_raw["generation"],
            goals=tuple(
                _decode_goal_record_candidate(item) for item in genesis_raw["goals"]
            ),
        )
        return cls(
            schema=GOAL_REPLAY_SCHEMA,
            genesis=genesis,
            patches=tuple(_decode_goal_patch(item) for item in value["patches"]),
            final_generation=value["final_generation"],
            final_state_sha256=value["final_state_sha256"],
            classification=value["classification"],
        )


def _decode_agency_state(raw: Any) -> AgencyState:
    value = _mapping("agency state", raw)
    _expect_keys(
        "agency state",
        value,
        {
            "schema",
            "state_id",
            "generation",
            "interests",
            "open_loops",
            "deferred_intents",
            "classification",
        },
    )
    if value["schema"] != AGENCY_STATE_SCHEMA:
        raise PersistentAgencyError("agency state schema mismatch")
    if value["classification"] != "EXPLICIT_AGENCY_PROJECTION_NOT_WORLD_TRUTH":
        raise PersistentAgencyError("agency state classification mismatch")
    interests = tuple(
        Interest(
            interest_id=item["interest_id"],
            label=item["label"],
            salience_ppm=item["salience_ppm"],
            provenance_refs=tuple(item["provenance_refs"]),
        )
        for item in value["interests"]
    )
    loops = tuple(
        OpenLoop(
            loop_id=item["loop_id"],
            summary=item["summary"],
            state=item["state"],
            priority_ppm=item["priority_ppm"],
            provenance_refs=tuple(item["provenance_refs"]),
            blocked_on_refs=tuple(item["blocked_on_refs"]),
        )
        for item in value["open_loops"]
    )
    intents = tuple(
        DeferredIntent(
            intent_id=item["intent_id"],
            summary=item["summary"],
            priority_ppm=item["priority_ppm"],
            revisit_condition_ref=item["revisit_condition_ref"],
            provenance_refs=tuple(item["provenance_refs"]),
        )
        for item in value["deferred_intents"]
    )
    return AgencyState.create(
        state_id=value["state_id"],
        generation=value["generation"],
        interests=interests,
        open_loops=loops,
        deferred_intents=intents,
    )


def _decode_fingerprint(raw: Any) -> StateFingerprint:
    value = _mapping("state fingerprint", raw)
    _expect_keys(
        "state fingerprint",
        value,
        {
            "profile",
            "projection_schema",
            "generation",
            "projection_sha256",
            "identity_sha256",
            "canonical_bytes",
            "classification",
        },
    )
    if value["profile"] != FINGERPRINT_PROFILE:
        raise PersistentAgencyError("state fingerprint profile mismatch")
    if value["classification"] != FINGERPRINT_CLASSIFICATION:
        raise PersistentAgencyError("state fingerprint classification mismatch")
    return StateFingerprint(**value)


def _decode_hold(raw: Any) -> HoldCheckpoint:
    value = _mapping("hold checkpoint", raw)
    _expect_keys(
        "hold checkpoint",
        value,
        {
            "schema",
            "hold_id",
            "state_id",
            "generation",
            "state_sha256",
            "wake_policy",
            "wake_conditions",
            "provenance_refs",
            "classification",
        },
    )
    if value["schema"] != HOLD_CHECKPOINT_SCHEMA:
        raise PersistentAgencyError("hold checkpoint schema mismatch")
    if value["classification"] != "EXPLICIT_HOLD_CHECKPOINT_NOT_SCHEDULER_AUTHORITY":
        raise PersistentAgencyError("hold checkpoint classification mismatch")
    conditions = tuple(
        WakeCondition(
            condition_id=item["condition_id"],
            observation_key=item["observation_key"],
            operator=item["operator"],
            expected_value=item["expected_value"],
            provenance_refs=tuple(item["provenance_refs"]),
        )
        for item in value["wake_conditions"]
    )
    return HoldCheckpoint.create(
        hold_id=value["hold_id"],
        state_id=value["state_id"],
        generation=value["generation"],
        state_sha256=value["state_sha256"],
        wake_policy=value["wake_policy"],
        wake_conditions=conditions,
        provenance_refs=tuple(value["provenance_refs"]),
    )


def _decode_pulse_input(raw: Any) -> PulseInput:
    value = _mapping("pulse input", raw)
    _expect_keys(
        "pulse input",
        value,
        {
            "schema",
            "pulse_id",
            "observation_id",
            "state_id",
            "generation",
            "state_digest_sha256",
            "act_candidate_ref",
            "ask_candidate_ref",
            "observe_candidate_ref",
            "wait_condition_ref",
            "hold_reason_ref",
            "delegate_candidate_ref",
            "classification",
        },
    )
    if value["schema"] != PULSE_INPUT_SCHEMA:
        raise PersistentAgencyError("pulse input schema mismatch")
    if value["classification"] != "EXPLICIT_ELIGIBILITY_INPUT_NOT_WORLD_FACT":
        raise PersistentAgencyError("pulse input classification mismatch")
    return PulseInput.create(
        pulse_id=value["pulse_id"],
        observation_id=value["observation_id"],
        state_id=value["state_id"],
        generation=value["generation"],
        state_digest_sha256=value["state_digest_sha256"],
        act_candidate_ref=value["act_candidate_ref"],
        ask_candidate_ref=value["ask_candidate_ref"],
        observe_candidate_ref=value["observe_candidate_ref"],
        wait_condition_ref=value["wait_condition_ref"],
        hold_reason_ref=value["hold_reason_ref"],
        delegate_candidate_ref=value["delegate_candidate_ref"],
    )


def _agency_projection(
    agency_state: AgencyState, goal_replay: GoalReplayEnvelope
) -> dict[str, Any]:
    goal_state = goal_replay.replay()
    return {
        "agency_state": {
            "schema": agency_state.schema,
            "state_id": agency_state.state_id,
            "generation": agency_state.generation,
            "sha256": agency_state.sha256(),
        },
        "goal_state": {
            "schema": goal_state.schema,
            "state_id": goal_state.state_id,
            "generation": goal_state.generation,
            "sha256": goal_state.sha256(),
            "replay_sha256": goal_replay.sha256(),
        },
    }


@dataclass(frozen=True, slots=True)
class PersistentAgencyCheckpoint:
    schema: str
    checkpoint_id: str
    previous_checkpoint_id: str | None
    kernel_state_id: str
    generation: int
    change_policy: str
    agency_state: AgencyState
    goal_replay: GoalReplayEnvelope
    state_fingerprint: StateFingerprint
    hold_checkpoint: HoldCheckpoint
    pulse_input: PulseInput
    provenance_refs: tuple[str, ...]
    classification: str = (
        "PERSISTED_EXPLICIT_AGENCY_CHECKPOINT_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION"
    )

    def __post_init__(self) -> None:
        if self.schema != CHECKPOINT_SCHEMA:
            raise PersistentAgencyError("checkpoint schema mismatch")
        object.__setattr__(
            self, "checkpoint_id", _identifier("checkpoint_id", self.checkpoint_id)
        )
        if self.previous_checkpoint_id is not None:
            object.__setattr__(
                self,
                "previous_checkpoint_id",
                _identifier("previous_checkpoint_id", self.previous_checkpoint_id),
            )
        object.__setattr__(
            self, "kernel_state_id", _identifier("kernel_state_id", self.kernel_state_id)
        )
        object.__setattr__(self, "generation", _generation(self.generation))
        if self.change_policy not in _ALLOWED_CHANGE_POLICIES:
            raise PersistentAgencyError("unsupported fingerprint change policy")
        if not isinstance(self.agency_state, AgencyState):
            raise PersistentAgencyError("agency_state must be AgencyState")
        if not isinstance(self.goal_replay, GoalReplayEnvelope):
            raise PersistentAgencyError("goal_replay must be GoalReplayEnvelope")
        if not isinstance(self.state_fingerprint, StateFingerprint):
            raise PersistentAgencyError("state_fingerprint must be StateFingerprint")
        if not isinstance(self.hold_checkpoint, HoldCheckpoint):
            raise PersistentAgencyError("hold_checkpoint must be HoldCheckpoint")
        if not isinstance(self.pulse_input, PulseInput):
            raise PersistentAgencyError("pulse_input must be PulseInput")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))
        if (
            self.classification
            != "PERSISTED_EXPLICIT_AGENCY_CHECKPOINT_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION"
        ):
            raise PersistentAgencyError("checkpoint classification mismatch")

        expected_fingerprint = fingerprint_state_projection(
            projection_schema=PROJECTION_SCHEMA,
            generation=self.generation,
            projection=_agency_projection(self.agency_state, self.goal_replay),
        )
        if self.state_fingerprint.as_dict() != expected_fingerprint.as_dict():
            raise PersistentAgencyError(
                "checkpoint StateFingerprint does not match typed Agency/Goal projection"
            )

        for label, state_id, generation, digest in (
            (
                "hold checkpoint",
                self.hold_checkpoint.state_id,
                self.hold_checkpoint.generation,
                self.hold_checkpoint.state_sha256,
            ),
            (
                "pulse input",
                self.pulse_input.state_id,
                self.pulse_input.generation,
                self.pulse_input.state_digest_sha256,
            ),
        ):
            if state_id != self.kernel_state_id:
                raise PersistentAgencyError(f"{label} kernel state_id fence mismatch")
            if generation != self.generation:
                raise PersistentAgencyError(f"{label} generation fence mismatch")
            if digest != self.state_fingerprint.identity_sha256:
                raise PersistentAgencyError(f"{label} state digest fence mismatch")

    @property
    def live_goal_state(self) -> GoalState:
        """Reconstruct via public candidate genesis + validated lifecycle transitions."""
        return self.goal_replay.replay()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "checkpoint_id": self.checkpoint_id,
            "previous_checkpoint_id": self.previous_checkpoint_id,
            "kernel_state_id": self.kernel_state_id,
            "generation": self.generation,
            "change_policy": self.change_policy,
            "agency_state": self.agency_state.as_dict(),
            "goal_replay": self.goal_replay.as_dict(),
            "state_fingerprint": self.state_fingerprint.as_dict(),
            "hold_checkpoint": self.hold_checkpoint.as_dict(),
            "pulse_input": self.pulse_input.as_dict(),
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, raw: Any) -> "PersistentAgencyCheckpoint":
        value = _mapping("persistent agency checkpoint", raw)
        _expect_keys(
            "persistent agency checkpoint",
            value,
            {
                "schema",
                "checkpoint_id",
                "previous_checkpoint_id",
                "kernel_state_id",
                "generation",
                "change_policy",
                "agency_state",
                "goal_replay",
                "state_fingerprint",
                "hold_checkpoint",
                "pulse_input",
                "provenance_refs",
                "classification",
            },
        )
        return cls(
            schema=value["schema"],
            checkpoint_id=value["checkpoint_id"],
            previous_checkpoint_id=value["previous_checkpoint_id"],
            kernel_state_id=value["kernel_state_id"],
            generation=value["generation"],
            change_policy=value["change_policy"],
            agency_state=_decode_agency_state(value["agency_state"]),
            goal_replay=GoalReplayEnvelope.from_dict(value["goal_replay"]),
            state_fingerprint=_decode_fingerprint(value["state_fingerprint"]),
            hold_checkpoint=_decode_hold(value["hold_checkpoint"]),
            pulse_input=_decode_pulse_input(value["pulse_input"]),
            provenance_refs=tuple(value["provenance_refs"]),
            classification=value["classification"],
        )


def create_checkpoint(
    *,
    checkpoint_id: str,
    previous_checkpoint_id: str | None,
    kernel_state_id: str,
    generation: int,
    change_policy: str,
    agency_state: AgencyState,
    goal_replay: GoalReplayEnvelope,
    hold_id: str,
    wake_policy: str,
    wake_conditions: Iterable[WakeCondition],
    hold_provenance_refs: Iterable[str],
    pulse_id: str,
    observation_id: str,
    act_candidate_ref: str | None = None,
    ask_candidate_ref: str | None = None,
    observe_candidate_ref: str | None = None,
    wait_condition_ref: str | None = None,
    hold_reason_ref: str | None = None,
    delegate_candidate_ref: str | None = None,
    provenance_refs: Iterable[str] = (),
) -> PersistentAgencyCheckpoint:
    gen = _generation(generation)
    if change_policy not in _ALLOWED_CHANGE_POLICIES:
        raise PersistentAgencyError("unsupported fingerprint change policy")
    fingerprint = fingerprint_state_projection(
        projection_schema=PROJECTION_SCHEMA,
        generation=gen,
        projection=_agency_projection(agency_state, goal_replay),
    )
    hold = HoldCheckpoint.create(
        hold_id=hold_id,
        state_id=kernel_state_id,
        generation=gen,
        state_sha256=fingerprint.identity_sha256,
        wake_policy=wake_policy,
        wake_conditions=tuple(wake_conditions),
        provenance_refs=tuple(hold_provenance_refs),
    )
    pulse = PulseInput.create(
        pulse_id=pulse_id,
        observation_id=observation_id,
        state_id=kernel_state_id,
        generation=gen,
        state_digest_sha256=fingerprint.identity_sha256,
        act_candidate_ref=act_candidate_ref,
        ask_candidate_ref=ask_candidate_ref,
        observe_candidate_ref=observe_candidate_ref,
        wait_condition_ref=wait_condition_ref,
        hold_reason_ref=hold_reason_ref,
        delegate_candidate_ref=delegate_candidate_ref,
    )
    return PersistentAgencyCheckpoint(
        schema=CHECKPOINT_SCHEMA,
        checkpoint_id=checkpoint_id,
        previous_checkpoint_id=previous_checkpoint_id,
        kernel_state_id=kernel_state_id,
        generation=gen,
        change_policy=change_policy,
        agency_state=agency_state,
        goal_replay=goal_replay,
        state_fingerprint=fingerprint,
        hold_checkpoint=hold,
        pulse_input=pulse,
        provenance_refs=tuple(provenance_refs),
    )


def advance_checkpoint(
    previous: PersistentAgencyCheckpoint,
    *,
    checkpoint_id: str,
    pulse_id: str,
    observation_id: str,
    provenance_refs: Iterable[str] | None = None,
) -> PersistentAgencyCheckpoint:
    """Pure caller-invoked next-tick checkpoint; this is not a scheduler."""
    if not isinstance(previous, PersistentAgencyCheckpoint):
        raise PersistentAgencyError("previous must be PersistentAgencyCheckpoint")
    return create_checkpoint(
        checkpoint_id=checkpoint_id,
        previous_checkpoint_id=previous.checkpoint_id,
        kernel_state_id=previous.kernel_state_id,
        generation=previous.generation + 1,
        change_policy=previous.change_policy,
        agency_state=previous.agency_state,
        goal_replay=previous.goal_replay,
        hold_id=previous.hold_checkpoint.hold_id,
        wake_policy=previous.hold_checkpoint.wake_policy,
        wake_conditions=previous.hold_checkpoint.wake_conditions,
        hold_provenance_refs=previous.hold_checkpoint.provenance_refs,
        pulse_id=pulse_id,
        observation_id=observation_id,
        act_candidate_ref=previous.pulse_input.act_candidate_ref,
        ask_candidate_ref=previous.pulse_input.ask_candidate_ref,
        observe_candidate_ref=previous.pulse_input.observe_candidate_ref,
        wait_condition_ref=previous.pulse_input.wait_condition_ref,
        hold_reason_ref=previous.pulse_input.hold_reason_ref,
        delegate_candidate_ref=previous.pulse_input.delegate_candidate_ref,
        provenance_refs=(
            previous.provenance_refs
            if provenance_refs is None
            else tuple(provenance_refs)
        ),
    )


def selected_fingerprint_change(
    previous: PersistentAgencyCheckpoint, current: PersistentAgencyCheckpoint
) -> bool:
    if not isinstance(previous, PersistentAgencyCheckpoint) or not isinstance(
        current, PersistentAgencyCheckpoint
    ):
        raise PersistentAgencyError(
            "selected_fingerprint_change requires PersistentAgencyCheckpoint values"
        )
    if previous.kernel_state_id != current.kernel_state_id:
        raise PersistentAgencyError("kernel state identity changed")
    if current.previous_checkpoint_id != previous.checkpoint_id:
        raise PersistentAgencyError("checkpoint parent identity mismatch")
    if current.generation != previous.generation + 1:
        raise PersistentAgencyError("checkpoint generation is not a direct successor")
    if current.change_policy != previous.change_policy:
        raise PersistentAgencyError("fingerprint change policy changed across replay")
    if current.change_policy == CHANGE_POLICY_PROJECTION:
        return projection_changed(
            previous.state_fingerprint, current.state_fingerprint
        )
    return identity_changed(previous.state_fingerprint, current.state_fingerprint)


@dataclass(frozen=True, slots=True)
class NextTickEvaluation:
    schema: str
    checkpoint_id: str
    checkpoint_sha256: str
    wake_evaluation: WakeEvaluation
    pulse_decision: PulseDecision
    classification: str = (
        "EVALUATION_ONLY_NO_SCHEDULER_ACTION_EFFECT_OR_COMPLETION_AUTHORITY"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "wake_evaluation": self.wake_evaluation.as_dict(),
            "pulse_decision": self.pulse_decision.as_dict(),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


def evaluate_checkpoint(
    checkpoint: PersistentAgencyCheckpoint,
    *,
    evaluation_id: str,
    observations: Iterable[WakeObservation] = (),
) -> NextTickEvaluation:
    """Re-evaluate Wake and Pulse from persisted typed inputs; execute nothing."""
    if not isinstance(checkpoint, PersistentAgencyCheckpoint):
        raise PersistentAgencyError("checkpoint must be PersistentAgencyCheckpoint")
    wake = evaluate_wake(
        checkpoint.hold_checkpoint,
        evaluation_id=evaluation_id,
        observed_state_id=checkpoint.kernel_state_id,
        observed_generation=checkpoint.generation,
        observed_state_sha256=checkpoint.state_fingerprint.identity_sha256,
        observations=tuple(observations),
    )
    pulse = classify_pulse_eligibility(checkpoint.pulse_input)
    return NextTickEvaluation(
        schema=NEXT_TICK_SCHEMA,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_sha256=checkpoint.sha256(),
        wake_evaluation=wake,
        pulse_decision=pulse,
    )


class CanonicalPersistentAgencyStore:
    """WP-206 writer inside one already-existing canonical UnifiedDB."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        resolution: UnifiedDBResolution,
        fingerprint: UnifiedDBFingerprint,
    ):
        if not isinstance(connection, sqlite3.Connection):
            raise PersistentAgencyError("SQLITE_CONNECTION_REQUIRED")
        if not isinstance(resolution, UnifiedDBResolution):
            raise PersistentAgencyError("UNIFIEDDB_RESOLUTION_REQUIRED")
        if not isinstance(fingerprint, UnifiedDBFingerprint):
            raise PersistentAgencyError("UNIFIEDDB_FINGERPRINT_REQUIRED")
        if resolution.schema != UNIFIEDDB_RESOLUTION_SCHEMA:
            raise PersistentAgencyError("UNIFIEDDB_RESOLUTION_SCHEMA_MISMATCH")
        if fingerprint.schema != UNIFIEDDB_FINGERPRINT_SCHEMA:
            raise PersistentAgencyError("UNIFIEDDB_FINGERPRINT_SCHEMA_MISMATCH")
        if not resolution.exists_at_resolution:
            raise PersistentAgencyError(
                "UNIFIEDDB_MUST_EXIST_BEFORE_PERSISTENT_AGENCY_WRITER_OPEN"
            )
        if not fingerprint.exists or fingerprint.status != "SQLITE3_REGULAR_FILE":
            raise PersistentAgencyError("UNIFIEDDB_FINGERPRINT_NOT_SQLITE_IDENTITY")
        if not _same_real_path(resolution.path, fingerprint.real_path):
            raise PersistentAgencyError(
                "UNIFIEDDB_RESOLUTION_FINGERPRINT_PATH_MISMATCH"
            )
        if fingerprint.device is None or fingerprint.inode is None:
            raise PersistentAgencyError("UNIFIEDDB_FINGERPRINT_FILE_IDENTITY_MISSING")
        expected = Path(fingerprint.real_path)
        try:
            current_stat = expected.stat()
        except OSError as exc:
            raise PersistentAgencyError("UNIFIEDDB_FILE_MISSING_AT_WRITER_OPEN") from exc
        if (current_stat.st_dev, current_stat.st_ino) != (
            fingerprint.device,
            fingerprint.inode,
        ):
            raise PersistentAgencyError("UNIFIEDDB_REPLACED_AFTER_FINGERPRINT")
        if connection.in_transaction:
            raise PersistentAgencyError("CALLER_TRANSACTION_ALREADY_OPEN")
        database_rows = connection.execute("PRAGMA database_list").fetchall()
        main_paths = [
            row[2] for row in database_rows if len(row) >= 3 and row[1] == "main"
        ]
        if len(main_paths) != 1 or not main_paths[0]:
            raise PersistentAgencyError("SQLITE_MAIN_DATABASE_PATH_UNAVAILABLE")
        if not _same_real_path(main_paths[0], fingerprint.real_path):
            raise PersistentAgencyError(
                "SQLITE_CONNECTION_NOT_BOUND_TO_FINGERPRINTED_UNIFIEDDB"
            )

        self.connection = connection
        self.resolution = resolution
        self.fingerprint = fingerprint
        self.canonical_db_path = os.path.realpath(fingerprint.real_path)
        self.db_device = int(fingerprint.device)
        self.db_inode = int(fingerprint.inode)
        self.authority_receipt_sha256 = fingerprint.receipt_sha256()
        self.connection.execute("PRAGMA foreign_keys=ON")

    @classmethod
    def open(
        cls,
        *,
        resolution: UnifiedDBResolution,
        fingerprint: UnifiedDBFingerprint,
        timeout: float = 5.0,
    ) -> "CanonicalPersistentAgencyStore":
        if not isinstance(fingerprint, UnifiedDBFingerprint) or not fingerprint.real_path:
            raise PersistentAgencyError("UNIFIEDDB_FINGERPRINT_REQUIRED")
        uri = Path(fingerprint.real_path).as_uri() + "?mode=rw"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=timeout)
        except sqlite3.Error as exc:
            raise PersistentAgencyError("UNIFIEDDB_READWRITE_OPEN_FAILED") from exc
        try:
            return cls(connection, resolution=resolution, fingerprint=fingerprint)
        except Exception:
            connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def initialize_schema(self) -> None:
        """Create only WP-206-owned tables inside the selected canonical DB."""
        if self.connection.in_transaction:
            raise PersistentAgencyError("CALLER_TRANSACTION_ALREADY_OPEN")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {CHECKPOINT_TABLE}(
                    checkpoint_id TEXT PRIMARY KEY,
                    previous_checkpoint_id TEXT,
                    kernel_state_id TEXT NOT NULL,
                    generation INTEGER NOT NULL CHECK(generation >= 0),
                    checkpoint_sha256 TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    canonical_db_path TEXT NOT NULL,
                    db_device INTEGER NOT NULL,
                    db_inode INTEGER NOT NULL,
                    unifieddb_authority_receipt_sha256 TEXT NOT NULL,
                    UNIQUE(kernel_state_id, generation),
                    FOREIGN KEY(previous_checkpoint_id)
                      REFERENCES {CHECKPOINT_TABLE}(checkpoint_id)
                )"""
            )
            self.connection.execute(
                f"""CREATE INDEX IF NOT EXISTS idx_f2_persistent_agency_lineage
                    ON {CHECKPOINT_TABLE}(kernel_state_id, generation)"""
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _assert_current_file_identity(self) -> None:
        try:
            st = Path(self.canonical_db_path).stat()
        except OSError as exc:
            raise PersistentAgencyError("UNIFIEDDB_FILE_MISSING_DURING_STORE_USE") from exc
        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):
            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")

    def write_checkpoint(self, checkpoint: PersistentAgencyCheckpoint) -> str:
        if not isinstance(checkpoint, PersistentAgencyCheckpoint):
            raise PersistentAgencyError(
                "checkpoint must be PersistentAgencyCheckpoint"
            )
        self._assert_current_file_identity()
        checkpoint_json = checkpoint.canonical_json()
        checkpoint_sha = checkpoint.sha256()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute(
                f"""SELECT checkpoint_sha256, checkpoint_json
                    FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
                (checkpoint.checkpoint_id,),
            ).fetchone()
            if existing is not None:
                if existing == (checkpoint_sha, checkpoint_json):
                    self.connection.commit()
                    return checkpoint_sha
                raise PersistentAgencyError(
                    "CHECKPOINT_ID_ALREADY_BOUND_TO_DIFFERENT_BYTES"
                )

            same_generation = self.connection.execute(
                f"""SELECT checkpoint_id FROM {CHECKPOINT_TABLE}
                    WHERE kernel_state_id=? AND generation=?""",
                (checkpoint.kernel_state_id, checkpoint.generation),
            ).fetchone()
            if same_generation is not None:
                raise PersistentAgencyError(
                    "KERNEL_GENERATION_ALREADY_BOUND_TO_CHECKPOINT"
                )

            if checkpoint.generation == 0:
                if checkpoint.previous_checkpoint_id is not None:
                    raise PersistentAgencyError(
                        "GENESIS_CHECKPOINT_MUST_NOT_HAVE_PARENT"
                    )
            else:
                if checkpoint.previous_checkpoint_id is None:
                    raise PersistentAgencyError(
                        "NON_GENESIS_CHECKPOINT_REQUIRES_PARENT"
                    )
                previous_row = self.connection.execute(
                    f"""SELECT checkpoint_json FROM {CHECKPOINT_TABLE}
                        WHERE checkpoint_id=?""",
                    (checkpoint.previous_checkpoint_id,),
                ).fetchone()
                if previous_row is None:
                    raise PersistentAgencyError("CHECKPOINT_PARENT_NOT_FOUND")
                previous = PersistentAgencyCheckpoint.from_dict(
                    json.loads(previous_row[0])
                )
                if previous.kernel_state_id != checkpoint.kernel_state_id:
                    raise PersistentAgencyError(
                        "CHECKPOINT_PARENT_KERNEL_STATE_ID_MISMATCH"
                    )
                if previous.generation + 1 != checkpoint.generation:
                    raise PersistentAgencyError(
                        "CHECKPOINT_PARENT_GENERATION_MISMATCH"
                    )
                if previous.change_policy != checkpoint.change_policy:
                    raise PersistentAgencyError(
                        "CHECKPOINT_CHANGE_POLICY_LINEAGE_MISMATCH"
                    )

            self.connection.execute(
                f"""INSERT INTO {CHECKPOINT_TABLE}(
                    checkpoint_id, previous_checkpoint_id, kernel_state_id,
                    generation, checkpoint_sha256, checkpoint_json,
                    canonical_db_path, db_device, db_inode,
                    unifieddb_authority_receipt_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    checkpoint.checkpoint_id,
                    checkpoint.previous_checkpoint_id,
                    checkpoint.kernel_state_id,
                    checkpoint.generation,
                    checkpoint_sha,
                    checkpoint_json,
                    self.canonical_db_path,
                    self.db_device,
                    self.db_inode,
                    self.authority_receipt_sha256,
                ),
            )
            self.connection.commit()
            return checkpoint_sha
        except Exception:
            self.connection.rollback()
            raise

    def load_checkpoint(self, checkpoint_id: str) -> PersistentAgencyCheckpoint:
        checkpoint_id = _identifier("checkpoint_id", checkpoint_id)
        self._assert_current_file_identity()
        row = self.connection.execute(
            f"""SELECT checkpoint_sha256, checkpoint_json, canonical_db_path,
                       db_device, db_inode
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise PersistentAgencyError("CHECKPOINT_NOT_FOUND")
        expected_sha, raw_json, stored_path, stored_device, stored_inode = row
        if not _same_real_path(stored_path, self.canonical_db_path):
            raise PersistentAgencyError("CHECKPOINT_DB_PATH_AUTHORITY_MISMATCH")
        if (stored_device, stored_inode) != (self.db_device, self.db_inode):
            raise PersistentAgencyError("CHECKPOINT_DB_FILE_IDENTITY_DRIFT")
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise PersistentAgencyError("CORRUPT_CHECKPOINT_JSON") from exc
        actual_sha = _sha256(raw)
        if actual_sha != expected_sha:
            raise PersistentAgencyError("CHECKPOINT_DIGEST_MISMATCH")
        checkpoint = PersistentAgencyCheckpoint.from_dict(raw)
        if checkpoint.sha256() != expected_sha:
            raise PersistentAgencyError("CHECKPOINT_TYPED_REPLAY_DIGEST_MISMATCH")
        return checkpoint

    def latest_checkpoint(
        self, kernel_state_id: str
    ) -> PersistentAgencyCheckpoint:
        kernel_state_id = _identifier("kernel_state_id", kernel_state_id)
        row = self.connection.execute(
            f"""SELECT checkpoint_id FROM {CHECKPOINT_TABLE}
                WHERE kernel_state_id=? ORDER BY generation DESC LIMIT 1""",
            (kernel_state_id,),
        ).fetchone()
        if row is None:
            raise PersistentAgencyError("CHECKPOINT_NOT_FOUND")
        return self.load_checkpoint(row[0])


__all__ = [
    "CHANGE_POLICY_IDENTITY",
    "CHANGE_POLICY_PROJECTION",
    "CHECKPOINT_SCHEMA",
    "CHECKPOINT_TABLE",
    "GOAL_REPLAY_SCHEMA",
    "NEXT_TICK_SCHEMA",
    "PROJECTION_SCHEMA",
    "STORE_SCHEMA",
    "CanonicalPersistentAgencyStore",
    "GoalReplayEnvelope",
    "NextTickEvaluation",
    "PersistentAgencyCheckpoint",
    "PersistentAgencyError",
    "advance_checkpoint",
    "create_checkpoint",
    "evaluate_checkpoint",
    "selected_fingerprint_change",
]
