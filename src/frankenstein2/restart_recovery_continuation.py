"""Fail-closed restart/recovery continuation planner for Frankenstein 2.0.

F2-WP-901 generation 1 repository-component scope only.

The planner consumes only already-persisted WP-900 whole-loop evidence plus exact
WP-206 PersistentAgencyCheckpoint values. It never schedules work, writes state,
executes/replays an effect, infers world truth, infers completion, or grants effect,
completion, provider/model, GRID10/GWT/J-Space or whole-system authority.

Recovery law:

    exact previous checkpoint
      + exact WP900 loop seal/outcome
      + exact direct-successor persisted checkpoint
      -> bounded continuation candidate

UNKNOWN or merely observed external outcomes remain unverified and force an OBSERVE
continuation with effect replay forbidden. VERIFIED_APPLIED is never replayed.
VERIFIED_NOT_APPLIED may only surface that a *new explicit request* could be created by
some separately authorized caller; this module never creates that request itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar, Iterable

from .persistent_agency_kernel import (
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
    selected_fingerprint_change,
)
from .whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    EFFECT_RESULT_OBSERVED,
    EFFECT_VERIFIED_APPLIED,
    EFFECT_VERIFIED_NOT_APPLIED,
    NO_EFFECT,
    LoopOutcomeEvidence,
    WholePersistentLoopSeal,
    checkpoint_ref,
    outcome_ref,
)

RECOVERY_CANDIDATE_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_CONTINUATION/v1"
CLASSIFICATION = (
    "DERIVED_RESTART_CONTINUATION_CANDIDATE_NOT_SCHEDULER_EFFECT_COMPLETION_OR_TRUTH_AUTHORITY"
)

TRANSITION_RESUME = "RESUME"
TRANSITION_OBSERVE = "OBSERVE"
TRANSITION_HOLD = "HOLD"

REPLAY_NOT_APPLICABLE = "NOT_APPLICABLE"
REPLAY_FORBIDDEN_UNVERIFIED = "FORBIDDEN_UNVERIFIED_OUTCOME"
REPLAY_FORBIDDEN_APPLIED = "FORBIDDEN_ALREADY_APPLIED"
REPLAY_NEW_EXPLICIT_REQUEST_ONLY = "ELIGIBLE_NEW_EXPLICIT_REQUEST_ONLY"

_REASON_NO_UNFINISHED = "NO_UNFINISHED_WORK_IN_PERSISTED_AGENCY_STATE"
_REASON_EXPLICIT_UNFINISHED = "EXPLICIT_UNFINISHED_WORK_PRESENT_IN_PERSISTED_AGENCY_STATE"
_REASON_UNKNOWN_EFFECT = "UNKNOWN_EXTERNAL_EFFECT_OUTCOME_REQUIRES_VERIFICATION"
_REASON_UNVERIFIED_RESULT = "OBSERVED_EFFECT_RESULT_REQUIRES_VERIFICATION"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096


class RestartRecoveryError(ValueError):
    """Fail-closed WP-901 recovery planning error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RestartRecoveryError(f"{name} must be an exact non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise RestartRecoveryError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RestartRecoveryError(f"{name} contains control characters")
    return value


def _sha256_text(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RestartRecoveryError(f"{name} must be lowercase 64-hex SHA-256")
    return value


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
        raise RestartRecoveryError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RestartRecoveryError(f"{name} must be an iterable of references")
    refs = tuple(_text(f"{name} item", value) for value in values)
    if require_nonempty and not refs:
        raise RestartRecoveryError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise RestartRecoveryError(f"{name} exceeds {_MAX_REFS} references")
    if len(set(refs)) != len(refs):
        raise RestartRecoveryError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _item_ref(kind: str, item_id: str, payload: dict[str, Any]) -> str:
    return f"wp901:{kind}:{_text(kind + '_id', item_id)}:{_digest(payload)}"


def _unfinished_refs(checkpoint: PersistentAgencyCheckpoint) -> tuple[str, ...]:
    refs: list[str] = []
    for loop in checkpoint.agency_state.open_loops:
        refs.append(_item_ref("open-loop", loop.loop_id, loop.as_dict()))
    for intent in checkpoint.agency_state.deferred_intents:
        refs.append(_item_ref("deferred-intent", intent.intent_id, intent.as_dict()))
    return tuple(sorted(refs))


def _loop_seal_ref(seal: WholePersistentLoopSeal) -> str:
    return f"wp900:loop-seal:{seal.seal_id}:{seal.sha256()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryContinuationCandidate:
    candidate_id: str
    generation: int
    previous_checkpoint_id: str
    previous_checkpoint_sha256: str
    persisted_checkpoint_id: str
    persisted_checkpoint_sha256: str
    loop_seal_id: str
    loop_seal_sha256: str
    outcome_id: str
    outcome_sha256: str
    outcome_status: str
    transition: str
    replay_disposition: str
    reason: str
    unfinished_work_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = RECOVERY_CANDIDATE_SCHEMA
    classification: ClassVar[str] = CLASSIFICATION

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "previous_checkpoint_id",
            "persisted_checkpoint_id",
            "loop_seal_id",
            "outcome_id",
            "outcome_status",
            "transition",
            "replay_disposition",
            "reason",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if type(self.generation) is not int or self.generation < 0:
            raise RestartRecoveryError("generation must be a non-negative integer")
        for name in (
            "previous_checkpoint_sha256",
            "persisted_checkpoint_sha256",
            "loop_seal_sha256",
            "outcome_sha256",
        ):
            object.__setattr__(self, name, _sha256_text(name, getattr(self, name)))
        if self.transition not in {TRANSITION_RESUME, TRANSITION_OBSERVE, TRANSITION_HOLD}:
            raise RestartRecoveryError("unsupported recovery transition")
        if self.replay_disposition not in {
            REPLAY_NOT_APPLICABLE,
            REPLAY_FORBIDDEN_UNVERIFIED,
            REPLAY_FORBIDDEN_APPLIED,
            REPLAY_NEW_EXPLICIT_REQUEST_ONLY,
        }:
            raise RestartRecoveryError("unsupported replay disposition")
        object.__setattr__(
            self,
            "unfinished_work_refs",
            _refs("unfinished_work_refs", self.unfinished_work_refs, require_nonempty=False),
        )
        object.__setattr__(self, "evidence_refs", _refs("evidence_refs", self.evidence_refs))
        object.__setattr__(
            self, "provenance_refs", _refs("provenance_refs", self.provenance_refs)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "candidate_id": self.candidate_id,
            "generation": self.generation,
            "previous_checkpoint_id": self.previous_checkpoint_id,
            "previous_checkpoint_sha256": self.previous_checkpoint_sha256,
            "persisted_checkpoint_id": self.persisted_checkpoint_id,
            "persisted_checkpoint_sha256": self.persisted_checkpoint_sha256,
            "loop_seal_id": self.loop_seal_id,
            "loop_seal_sha256": self.loop_seal_sha256,
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "outcome_status": self.outcome_status,
            "transition": self.transition,
            "replay_disposition": self.replay_disposition,
            "reason": self.reason,
            "unfinished_work_refs": list(self.unfinished_work_refs),
            "evidence_refs": list(self.evidence_refs),
            "provenance_refs": list(self.provenance_refs),
            "scheduler_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "provider_model_credit": 0,
            "training_credit": 0,
            "whole_system_acceptance": False,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _validate_exact_persisted_lineage(
    *,
    previous_checkpoint: PersistentAgencyCheckpoint,
    persisted_checkpoint: PersistentAgencyCheckpoint,
    loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> None:
    if type(previous_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError(
            "previous_checkpoint must be concrete PersistentAgencyCheckpoint"
        )
    if type(persisted_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError(
            "persisted_checkpoint must be concrete PersistentAgencyCheckpoint"
        )
    if type(loop_seal) is not WholePersistentLoopSeal:
        raise RestartRecoveryError("loop_seal must be concrete WholePersistentLoopSeal")
    if type(outcome) is not LoopOutcomeEvidence:
        raise RestartRecoveryError("outcome must be concrete LoopOutcomeEvidence")

    try:
        selected_fingerprint_change(previous_checkpoint, persisted_checkpoint)
    except PersistentAgencyError as exc:
        raise RestartRecoveryError(
            f"persisted checkpoint is not an exact direct successor: {exc}"
        ) from exc

    if loop_seal.current_checkpoint_id != previous_checkpoint.checkpoint_id:
        raise RestartRecoveryError("loop seal previous checkpoint id mismatch")
    if loop_seal.current_checkpoint_sha256 != previous_checkpoint.sha256():
        raise RestartRecoveryError("loop seal previous checkpoint digest mismatch")
    if loop_seal.next_checkpoint_id != persisted_checkpoint.checkpoint_id:
        raise RestartRecoveryError("loop seal persisted checkpoint id mismatch")
    if loop_seal.next_checkpoint_sha256 != persisted_checkpoint.sha256():
        raise RestartRecoveryError("loop seal persisted checkpoint digest mismatch")
    if loop_seal.outcome_id != outcome.outcome_id:
        raise RestartRecoveryError("loop seal outcome id mismatch")
    if loop_seal.outcome_sha256 != outcome.sha256():
        raise RestartRecoveryError("loop seal outcome digest mismatch")

    required = {
        checkpoint_ref(previous_checkpoint),
        outcome_ref(outcome),
    }
    if not required.issubset(set(loop_seal.reentry_refs)):
        raise RestartRecoveryError("loop seal lacks exact checkpoint/outcome re-entry refs")
    if not set(loop_seal.reentry_refs).issubset(set(persisted_checkpoint.provenance_refs)):
        raise RestartRecoveryError(
            "persisted checkpoint lacks exact WP900 loop re-entry evidence"
        )


def _recovery_transition(
    *, outcome: LoopOutcomeEvidence, unfinished_work_refs: tuple[str, ...]
) -> tuple[str, str, str]:
    if outcome.status == EFFECT_OUTCOME_UNKNOWN:
        return TRANSITION_OBSERVE, REPLAY_FORBIDDEN_UNVERIFIED, _REASON_UNKNOWN_EFFECT
    if outcome.status == EFFECT_RESULT_OBSERVED:
        return TRANSITION_OBSERVE, REPLAY_FORBIDDEN_UNVERIFIED, _REASON_UNVERIFIED_RESULT

    if unfinished_work_refs:
        transition = TRANSITION_RESUME
        reason = _REASON_EXPLICIT_UNFINISHED
    else:
        transition = TRANSITION_HOLD
        reason = _REASON_NO_UNFINISHED

    if outcome.status == EFFECT_VERIFIED_APPLIED:
        return transition, REPLAY_FORBIDDEN_APPLIED, reason
    if outcome.status == EFFECT_VERIFIED_NOT_APPLIED:
        return transition, REPLAY_NEW_EXPLICIT_REQUEST_ONLY, reason
    if outcome.status == NO_EFFECT:
        return transition, REPLAY_NOT_APPLICABLE, reason
    raise RestartRecoveryError("unsupported loop outcome status")


def plan_restart_recovery(
    *,
    candidate_id: str,
    previous_checkpoint: PersistentAgencyCheckpoint,
    persisted_checkpoint: PersistentAgencyCheckpoint,
    loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
    provenance_refs: Iterable[str],
) -> RecoveryContinuationCandidate:
    """Build one bounded restart continuation candidate from exact persisted evidence.

    No state mutation, scheduling, effect replay, retry request, verification, completion,
    provider/model/tool call, or world-state inference occurs here.
    """
    _validate_exact_persisted_lineage(
        previous_checkpoint=previous_checkpoint,
        persisted_checkpoint=persisted_checkpoint,
        loop_seal=loop_seal,
        outcome=outcome,
    )
    unfinished = _unfinished_refs(persisted_checkpoint)
    transition, replay, reason = _recovery_transition(
        outcome=outcome,
        unfinished_work_refs=unfinished,
    )
    evidence_refs = tuple(
        sorted(
            {
                checkpoint_ref(previous_checkpoint),
                checkpoint_ref(persisted_checkpoint),
                outcome_ref(outcome),
                _loop_seal_ref(loop_seal),
                *loop_seal.reentry_refs,
            }
        )
    )
    return RecoveryContinuationCandidate(
        candidate_id=candidate_id,
        generation=persisted_checkpoint.generation,
        previous_checkpoint_id=previous_checkpoint.checkpoint_id,
        previous_checkpoint_sha256=previous_checkpoint.sha256(),
        persisted_checkpoint_id=persisted_checkpoint.checkpoint_id,
        persisted_checkpoint_sha256=persisted_checkpoint.sha256(),
        loop_seal_id=loop_seal.seal_id,
        loop_seal_sha256=loop_seal.sha256(),
        outcome_id=outcome.outcome_id,
        outcome_sha256=outcome.sha256(),
        outcome_status=outcome.status,
        transition=transition,
        replay_disposition=replay,
        reason=reason,
        unfinished_work_refs=unfinished,
        evidence_refs=evidence_refs,
        provenance_refs=tuple(provenance_refs),
    )


__all__ = [
    "CLASSIFICATION",
    "RECOVERY_CANDIDATE_SCHEMA",
    "REPLAY_FORBIDDEN_APPLIED",
    "REPLAY_FORBIDDEN_UNVERIFIED",
    "REPLAY_NEW_EXPLICIT_REQUEST_ONLY",
    "REPLAY_NOT_APPLICABLE",
    "RecoveryContinuationCandidate",
    "RestartRecoveryError",
    "TRANSITION_HOLD",
    "TRANSITION_OBSERVE",
    "TRANSITION_RESUME",
    "plan_restart_recovery",
]
