"""Deterministic restart/recovery continuation planning for Frankenstein 2.0.

F2-WP-901 generation 1 repository-component scope only.

This module consumes already-typed WP206 PersistentAgencyCheckpoint evidence and,
optionally, an exact WP900 WholePersistentLoopSeal + LoopOutcomeEvidence pair.  It
produces only a bounded continuation candidate projection.  It does not schedule,
execute, replay effects, infer missing work, mint completion, or persist a second
recovery ledger.

Core recovery law:

    explicit persisted unfinished work -> candidate projection only
    UNKNOWN external effect outcome     -> HOLD; never blind replay
    absent/closed/cancelled work         -> never reconstructed
    parent/generation/digest mismatch    -> fail closed
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar, Iterable

from .agency_state import DeferredIntent, OpenLoop
from .persistent_agency_kernel import (
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
    selected_fingerprint_change,
)
from .whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    LoopOutcomeEvidence,
    WholePersistentLoopSeal,
    checkpoint_ref,
    outcome_ref,
)


RECOVERY_CANDIDATE_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_CANDIDATE/v1"
RECOVERY_PLAN_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_PLAN/v1"
RECOVERY_CLASSIFICATION = (
    "CANDIDATE_CONTROL_EVIDENCE_ONLY_NO_SCHEDULER_EFFECT_COMPLETION_OR_TRUTH_AUTHORITY"
)

MODE_HOLD_UNKNOWN_EFFECT = "HOLD_UNKNOWN_EFFECT_OUTCOME"
MODE_CANDIDATES_PRESENT = "CONTINUATION_CANDIDATES_PRESENT"
MODE_NO_UNFINISHED_WORK = "NO_EXPLICIT_UNFINISHED_WORK"

SOURCE_OPEN_LOOP = "OPEN_LOOP"
SOURCE_DEFERRED_INTENT = "DEFERRED_INTENT"

DISPOSITION_ELIGIBLE = "ELIGIBLE_CANDIDATE"
DISPOSITION_BLOCKED = "BLOCKED"
DISPOSITION_WAITING = "WAITING"
DISPOSITION_DEFERRED = "DEFERRED"
DISPOSITION_HELD_UNKNOWN = "HELD_UNKNOWN_EFFECT_OUTCOME"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_TEXT_LEN = 4096


class RestartRecoveryError(ValueError):
    """Fail-closed WP901 recovery-planning error."""


def _token(name: str, value: Any, *, max_len: int = _MAX_ID_LEN) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RestartRecoveryError(f"{name} must be a non-empty trimmed string")
    if len(value) > max_len:
        raise RestartRecoveryError(f"{name} exceeds {max_len} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RestartRecoveryError(f"{name} contains control characters")
    return value


def _sha256_text(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RestartRecoveryError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RestartRecoveryError(f"{name} must be an iterable of strings")
    cleaned = tuple(sorted({_token(f"{name} item", value) for value in values}))
    if require_nonempty and not cleaned:
        raise RestartRecoveryError(f"{name} must not be empty")
    return cleaned


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


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryCandidate:
    candidate_id: str
    source_kind: str
    source_item_id: str
    summary: str
    priority_ppm: int
    source_state: str
    disposition: str
    source_refs: tuple[str, ...]
    blocked_on_refs: tuple[str, ...] = ()
    revisit_condition_ref: str | None = None

    schema: ClassVar[str] = RECOVERY_CANDIDATE_SCHEMA
    classification: ClassVar[str] = RECOVERY_CLASSIFICATION

    def __post_init__(self) -> None:
        for name in ("candidate_id", "source_item_id", "source_state", "disposition"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "summary", _token("summary", self.summary, max_len=_MAX_TEXT_LEN))
        if self.source_kind not in {SOURCE_OPEN_LOOP, SOURCE_DEFERRED_INTENT}:
            raise RestartRecoveryError("unsupported recovery candidate source_kind")
        if type(self.priority_ppm) is not int or not 0 <= self.priority_ppm <= 1_000_000:
            raise RestartRecoveryError("priority_ppm must be an integer in [0,1000000]")
        object.__setattr__(self, "source_refs", _refs("source_refs", self.source_refs, require_nonempty=True))
        object.__setattr__(self, "blocked_on_refs", _refs("blocked_on_refs", self.blocked_on_refs))
        if self.revisit_condition_ref is not None:
            object.__setattr__(
                self,
                "revisit_condition_ref",
                _token("revisit_condition_ref", self.revisit_condition_ref),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "candidate_id": self.candidate_id,
            "source_kind": self.source_kind,
            "source_item_id": self.source_item_id,
            "summary": self.summary,
            "priority_ppm": self.priority_ppm,
            "source_state": self.source_state,
            "disposition": self.disposition,
            "source_refs": list(self.source_refs),
            "blocked_on_refs": list(self.blocked_on_refs),
            "revisit_condition_ref": self.revisit_condition_ref,
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RestartRecoveryPlan:
    plan_id: str
    parent_checkpoint_id: str
    parent_checkpoint_sha256: str
    parent_generation: int
    next_generation: int
    previous_checkpoint_id: str | None
    previous_checkpoint_sha256: str | None
    loop_seal_id: str | None
    loop_seal_sha256: str | None
    outcome_id: str | None
    outcome_sha256: str | None
    outcome_status: str | None
    mode: str
    candidates: tuple[RecoveryCandidate, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = RECOVERY_PLAN_SCHEMA
    classification: ClassVar[str] = RECOVERY_CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _token("plan_id", self.plan_id))
        object.__setattr__(self, "parent_checkpoint_id", _token("parent_checkpoint_id", self.parent_checkpoint_id))
        object.__setattr__(self, "parent_checkpoint_sha256", _sha256_text("parent_checkpoint_sha256", self.parent_checkpoint_sha256))
        if type(self.parent_generation) is not int or self.parent_generation < 0:
            raise RestartRecoveryError("parent_generation must be non-negative integer")
        if type(self.next_generation) is not int or self.next_generation != self.parent_generation + 1:
            raise RestartRecoveryError("next_generation must be parent_generation + 1")
        optional_id_fields = ("previous_checkpoint_id", "loop_seal_id", "outcome_id", "outcome_status")
        for field in optional_id_fields:
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _token(field, value))
        for field in ("previous_checkpoint_sha256", "loop_seal_sha256", "outcome_sha256"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha256_text(field, value))
        if (self.previous_checkpoint_id is None) != (self.previous_checkpoint_sha256 is None):
            raise RestartRecoveryError("previous checkpoint identity must be complete or absent")
        if (self.loop_seal_id is None) != (self.loop_seal_sha256 is None):
            raise RestartRecoveryError("loop seal identity must be complete or absent")
        outcome_present = self.outcome_id is not None or self.outcome_sha256 is not None or self.outcome_status is not None
        if outcome_present and not all(
            value is not None for value in (self.outcome_id, self.outcome_sha256, self.outcome_status)
        ):
            raise RestartRecoveryError("outcome identity/status must be complete or absent")
        if (self.loop_seal_id is None) != (self.outcome_id is None):
            raise RestartRecoveryError("loop seal and outcome evidence must appear together")
        if self.mode not in {MODE_HOLD_UNKNOWN_EFFECT, MODE_CANDIDATES_PRESENT, MODE_NO_UNFINISHED_WORK}:
            raise RestartRecoveryError("unsupported recovery mode")
        if not isinstance(self.candidates, tuple) or any(type(item) is not RecoveryCandidate for item in self.candidates):
            raise RestartRecoveryError("candidates must be concrete RecoveryCandidate tuple")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs, require_nonempty=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "plan_id": self.plan_id,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "parent_checkpoint_sha256": self.parent_checkpoint_sha256,
            "parent_generation": self.parent_generation,
            "next_generation": self.next_generation,
            "previous_checkpoint_id": self.previous_checkpoint_id,
            "previous_checkpoint_sha256": self.previous_checkpoint_sha256,
            "loop_seal_id": self.loop_seal_id,
            "loop_seal_sha256": self.loop_seal_sha256,
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "outcome_status": self.outcome_status,
            "mode": self.mode,
            "candidates": [item.as_dict() for item in self.candidates],
            "provenance_refs": list(self.provenance_refs),
            "effect_replay_policy": "NEVER_AUTOMATIC",
            "unknown_effect_policy": "HOLD_UNTIL_EXPLICIT_VERIFICATION_OR_NEW_OBSERVATION",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "truth_authority": "NONE",
            "runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "training_credit": 0,
            "whole_system_acceptance": False,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _validate_checkpoint_lineage(
    *,
    checkpoint: PersistentAgencyCheckpoint,
    previous_checkpoint: PersistentAgencyCheckpoint | None,
) -> None:
    if checkpoint.generation == 0:
        if checkpoint.previous_checkpoint_id is not None or previous_checkpoint is not None:
            raise RestartRecoveryError("generation-0 checkpoint cannot claim previous checkpoint lineage")
        return
    if type(previous_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError("non-genesis recovery requires exact previous checkpoint evidence")
    try:
        selected_fingerprint_change(previous_checkpoint, checkpoint)
    except PersistentAgencyError as exc:
        raise RestartRecoveryError(f"checkpoint direct-successor lineage rejected: {exc}") from exc


def _validate_loop_evidence(
    *,
    checkpoint: PersistentAgencyCheckpoint,
    previous_checkpoint: PersistentAgencyCheckpoint | None,
    loop_seal: WholePersistentLoopSeal | None,
    outcome: LoopOutcomeEvidence | None,
) -> None:
    if (loop_seal is None) != (outcome is None):
        raise RestartRecoveryError("WP900 loop seal and outcome must be supplied together")
    if loop_seal is None:
        return
    if type(loop_seal) is not WholePersistentLoopSeal or type(outcome) is not LoopOutcomeEvidence:
        raise RestartRecoveryError("loop evidence must use concrete WP900 types")
    if type(previous_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError("WP900 loop evidence requires exact predecessor checkpoint")
    expected = {
        "seal current checkpoint id": (loop_seal.current_checkpoint_id, previous_checkpoint.checkpoint_id),
        "seal current checkpoint digest": (loop_seal.current_checkpoint_sha256, previous_checkpoint.sha256()),
        "seal next checkpoint id": (loop_seal.next_checkpoint_id, checkpoint.checkpoint_id),
        "seal next checkpoint digest": (loop_seal.next_checkpoint_sha256, checkpoint.sha256()),
        "seal outcome id": (loop_seal.outcome_id, outcome.outcome_id),
        "seal outcome digest": (loop_seal.outcome_sha256, outcome.sha256()),
    }
    for label, (observed, wanted) in expected.items():
        if observed != wanted:
            raise RestartRecoveryError(f"{label} mismatch")
    if loop_seal.generation != previous_checkpoint.generation:
        raise RestartRecoveryError("WP900 loop generation does not match predecessor checkpoint")
    if checkpoint.generation != loop_seal.generation + 1:
        raise RestartRecoveryError("WP900 loop does not terminate at direct-successor checkpoint generation")
    if outcome_ref(outcome) not in loop_seal.reentry_refs:
        raise RestartRecoveryError("WP900 loop seal lacks exact outcome re-entry reference")


def _candidate_from_open_loop(
    item: OpenLoop,
    *,
    checkpoint: PersistentAgencyCheckpoint,
    hold_unknown: bool,
) -> RecoveryCandidate:
    if type(item) is not OpenLoop:
        raise RestartRecoveryError("open-loop recovery source must be concrete OpenLoop")
    if hold_unknown:
        disposition = DISPOSITION_HELD_UNKNOWN
    elif item.state == "OPEN":
        disposition = DISPOSITION_ELIGIBLE
    elif item.state == "BLOCKED":
        disposition = DISPOSITION_BLOCKED
    else:
        disposition = DISPOSITION_WAITING
    exact_ref = (
        f"wp901:checkpoint-item:{checkpoint.checkpoint_id}:{checkpoint.sha256()}:"
        f"open-loop:{item.loop_id}"
    )
    return RecoveryCandidate(
        candidate_id=f"recover-open-loop:{item.loop_id}",
        source_kind=SOURCE_OPEN_LOOP,
        source_item_id=item.loop_id,
        summary=item.summary,
        priority_ppm=item.priority_ppm,
        source_state=item.state,
        disposition=disposition,
        source_refs=tuple(item.provenance_refs) + (exact_ref,),
        blocked_on_refs=item.blocked_on_refs,
    )


def _candidate_from_deferred_intent(
    item: DeferredIntent,
    *,
    checkpoint: PersistentAgencyCheckpoint,
    hold_unknown: bool,
) -> RecoveryCandidate:
    if type(item) is not DeferredIntent:
        raise RestartRecoveryError("deferred recovery source must be concrete DeferredIntent")
    exact_ref = (
        f"wp901:checkpoint-item:{checkpoint.checkpoint_id}:{checkpoint.sha256()}:"
        f"deferred-intent:{item.intent_id}"
    )
    return RecoveryCandidate(
        candidate_id=f"recover-deferred-intent:{item.intent_id}",
        source_kind=SOURCE_DEFERRED_INTENT,
        source_item_id=item.intent_id,
        summary=item.summary,
        priority_ppm=item.priority_ppm,
        source_state="DEFERRED",
        disposition=DISPOSITION_HELD_UNKNOWN if hold_unknown else DISPOSITION_DEFERRED,
        source_refs=tuple(item.provenance_refs) + (exact_ref,),
        revisit_condition_ref=item.revisit_condition_ref,
    )


def plan_restart_recovery(
    *,
    plan_id: str,
    checkpoint: PersistentAgencyCheckpoint,
    previous_checkpoint: PersistentAgencyCheckpoint | None = None,
    last_loop_seal: WholePersistentLoopSeal | None = None,
    last_outcome: LoopOutcomeEvidence | None = None,
    provenance_refs: Iterable[str] = (),
) -> RestartRecoveryPlan:
    """Derive a deterministic continuation candidate projection and execute nothing."""
    if type(checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError("checkpoint must be concrete PersistentAgencyCheckpoint")
    if previous_checkpoint is not None and type(previous_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError("previous_checkpoint must be concrete PersistentAgencyCheckpoint")

    _validate_checkpoint_lineage(checkpoint=checkpoint, previous_checkpoint=previous_checkpoint)
    _validate_loop_evidence(
        checkpoint=checkpoint,
        previous_checkpoint=previous_checkpoint,
        loop_seal=last_loop_seal,
        outcome=last_outcome,
    )

    hold_unknown = last_outcome is not None and last_outcome.status == EFFECT_OUTCOME_UNKNOWN
    candidates = [
        _candidate_from_open_loop(item, checkpoint=checkpoint, hold_unknown=hold_unknown)
        for item in checkpoint.agency_state.open_loops
    ]
    candidates.extend(
        _candidate_from_deferred_intent(item, checkpoint=checkpoint, hold_unknown=hold_unknown)
        for item in checkpoint.agency_state.deferred_intents
    )
    ordered_candidates = tuple(
        sorted(
            candidates,
            key=lambda item: (-item.priority_ppm, item.source_kind, item.source_item_id),
        )
    )

    if hold_unknown:
        mode = MODE_HOLD_UNKNOWN_EFFECT
    elif ordered_candidates:
        mode = MODE_CANDIDATES_PRESENT
    else:
        mode = MODE_NO_UNFINISHED_WORK

    refs = set(_refs("provenance_refs", provenance_refs))
    refs.add(checkpoint_ref(checkpoint))
    if previous_checkpoint is not None:
        refs.add(checkpoint_ref(previous_checkpoint))
    loop_seal_id = loop_seal_sha256 = outcome_id = outcome_sha256 = outcome_status = None
    if last_loop_seal is not None and last_outcome is not None:
        loop_seal_id = last_loop_seal.seal_id
        loop_seal_sha256 = last_loop_seal.sha256()
        outcome_id = last_outcome.outcome_id
        outcome_sha256 = last_outcome.sha256()
        outcome_status = last_outcome.status
        refs.add(f"wp901:whole-loop-seal:{loop_seal_id}:{loop_seal_sha256}")
        refs.add(outcome_ref(last_outcome))

    return RestartRecoveryPlan(
        plan_id=plan_id,
        parent_checkpoint_id=checkpoint.checkpoint_id,
        parent_checkpoint_sha256=checkpoint.sha256(),
        parent_generation=checkpoint.generation,
        next_generation=checkpoint.generation + 1,
        previous_checkpoint_id=(previous_checkpoint.checkpoint_id if previous_checkpoint is not None else None),
        previous_checkpoint_sha256=(previous_checkpoint.sha256() if previous_checkpoint is not None else None),
        loop_seal_id=loop_seal_id,
        loop_seal_sha256=loop_seal_sha256,
        outcome_id=outcome_id,
        outcome_sha256=outcome_sha256,
        outcome_status=outcome_status,
        mode=mode,
        candidates=ordered_candidates,
        provenance_refs=tuple(sorted(refs)),
    )


__all__ = [
    "DISPOSITION_BLOCKED",
    "DISPOSITION_DEFERRED",
    "DISPOSITION_ELIGIBLE",
    "DISPOSITION_HELD_UNKNOWN",
    "DISPOSITION_WAITING",
    "MODE_CANDIDATES_PRESENT",
    "MODE_HOLD_UNKNOWN_EFFECT",
    "MODE_NO_UNFINISHED_WORK",
    "RECOVERY_CANDIDATE_SCHEMA",
    "RECOVERY_PLAN_SCHEMA",
    "RecoveryCandidate",
    "RestartRecoveryError",
    "RestartRecoveryPlan",
    "plan_restart_recovery",
]
