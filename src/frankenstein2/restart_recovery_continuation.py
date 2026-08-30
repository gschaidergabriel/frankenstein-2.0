"""Fail-closed restart/recovery continuation contract for Frankenstein 2.0.

F2-WP-901 generation 2 repository-component scope only.

Generation 2 closes the executed generation-1 mixed-causal-lineage/self-attestation
counterexample. Recovery admission now consumes the existing canonical ``CausalIdentity``
primitive plus concrete ``PersistentAgencyCheckpoint``, ``WholePersistentLoopSeal`` and
``LoopOutcomeEvidence`` objects. The WP900 seal must identify the exact restart checkpoint
as its direct successor and the exact outcome object, and one causal-identity reference must
be present in the persisted provenance of the checkpoint, outcome and whole-loop seal.

This module still does not persist a second recovery ledger, schedule work, call
models/providers/tools, execute effects, or mint completion. It produces only a deterministic
continuation *candidate*.

Restart safety remains conservative:

* UNKNOWN or merely RESULT_OBSERVED external-effect outcomes hold the entire unfinished
  set until outcome verification closes the causal ambiguity;
* VERIFIED_NOT_APPLIED may continue unrelated non-effect work, but the effect attempt
  remains held for explicit re-authorization rather than blind replay;
* VERIFIED_APPLIED requires the attempted-effect refs to be explicitly completed;
* NO_EFFECT cannot carry effect-attempt refs.

Canonical durable state remains UnifiedDB. This object is a typed recovery/control
projection only and cannot become a competing truth/effect/completion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar, Iterable

from .causal_identity import CausalIdentity
from .persistent_agency_kernel import PersistentAgencyCheckpoint
from .whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    EFFECT_RESULT_OBSERVED,
    EFFECT_VERIFIED_APPLIED,
    EFFECT_VERIFIED_NOT_APPLIED,
    NO_EFFECT,
    LoopOutcomeEvidence,
    WholePersistentLoopSeal,
)


RECOVERY_EVIDENCE_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_EVIDENCE/v2"
RECOVERY_PLAN_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_CONTINUATION_PLAN/v2"
EVIDENCE_CLASSIFICATION = (
    "PERSISTED_CAUSAL_OBJECT_BOUND_RECOVERY_INPUT_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
)
PLAN_CLASSIFICATION = (
    "DETERMINISTIC_CAUSAL_BOUND_RESTART_CONTINUATION_CANDIDATE_NOT_SCHEDULER_EFFECT_OR_COMPLETION_AUTHORITY"
)

CONTINUE_UNFINISHED = "CONTINUE_UNFINISHED_AS_CANDIDATE"
HOLD_EFFECT_VERIFICATION = "HOLD_FOR_EFFECT_VERIFICATION"
CONTINUE_WITH_EFFECT_REAUTH_HOLD = "CONTINUE_NON_EFFECT_WITH_EFFECT_REAUTH_HOLD"
NO_CONTINUATION = "NO_UNFINISHED_WORK"

_REASON_CONTINUE = "EXPLICIT_UNFINISHED_EVIDENCE"
_REASON_VERIFY = "UNRESOLVED_EFFECT_OUTCOME_REQUIRES_VERIFICATION"
_REASON_REAUTHORIZE = "VERIFIED_NOT_APPLIED_EFFECT_REQUIRES_EXPLICIT_REAUTHORIZATION"
_REASON_NONE = "NO_EXPLICIT_UNFINISHED_WORK"

_OUTCOME_STATUSES = frozenset(
    {
        NO_EFFECT,
        EFFECT_RESULT_OBSERVED,
        EFFECT_VERIFIED_APPLIED,
        EFFECT_VERIFIED_NOT_APPLIED,
        EFFECT_OUTCOME_UNKNOWN,
    }
)
_UNRESOLVED_EFFECT_STATUSES = frozenset(
    {EFFECT_RESULT_OBSERVED, EFFECT_OUTCOME_UNKNOWN}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_REFS = 4096


class RestartRecoveryError(ValueError):
    """Fail-closed WP901 recovery-contract error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str:
        raise RestartRecoveryError(f"{name} must be exact concrete string")
    if not value or value != value.strip():
        raise RestartRecoveryError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_TEXT:
        raise RestartRecoveryError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RestartRecoveryError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RestartRecoveryError(
            f"{name} must be exact concrete lowercase 64-hex SHA-256"
        )
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise RestartRecoveryError(f"{name} must be non-negative exact int")
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RestartRecoveryError(f"{name} must be iterable of reference strings")
    refs = tuple(_text(f"{name} item", item) for item in values)
    if not allow_empty and not refs:
        raise RestartRecoveryError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise RestartRecoveryError(f"{name} exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise RestartRecoveryError(f"{name} must not contain duplicates")
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
        raise RestartRecoveryError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def causal_identity_ref(identity: CausalIdentity) -> str:
    """Return the exact reusable provenance reference for one canonical causal identity."""
    if type(identity) is not CausalIdentity:
        raise RestartRecoveryError("causal_identity must be concrete CausalIdentity")
    return f"f2:causal-identity:{identity.causal_id}:{identity.sha256()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedRestartEvidence:
    """Explicit, causally bound evidence required to plan one restart continuation.

    Direct construction remains validation-only. Canonical recovery admission should use
    :func:`bind_persisted_restart_evidence`, which derives checkpoint/seal/outcome identities
    from concrete typed source objects rather than accepting mutually self-consistent hashes.
    """

    evidence_id: str
    causal_identity: CausalIdentity
    source_checkpoint_id: str
    source_checkpoint_generation: int
    source_checkpoint_sha256: str
    whole_loop_seal_id: str
    whole_loop_seal_sha256: str
    outcome_status: str
    outcome_id: str
    outcome_sha256: str
    unfinished_work_refs: tuple[str, ...] = ()
    completed_work_refs: tuple[str, ...] = ()
    effect_attempt_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    schema: ClassVar[str] = RECOVERY_EVIDENCE_SCHEMA
    classification: ClassVar[str] = EVIDENCE_CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text("evidence_id", self.evidence_id))
        if type(self.causal_identity) is not CausalIdentity:
            raise RestartRecoveryError("causal_identity must be concrete CausalIdentity")
        object.__setattr__(
            self,
            "source_checkpoint_id",
            _text("source_checkpoint_id", self.source_checkpoint_id),
        )
        object.__setattr__(
            self,
            "source_checkpoint_generation",
            _generation("source_checkpoint_generation", self.source_checkpoint_generation),
        )
        object.__setattr__(
            self,
            "source_checkpoint_sha256",
            _sha256("source_checkpoint_sha256", self.source_checkpoint_sha256),
        )
        object.__setattr__(
            self,
            "whole_loop_seal_id",
            _text("whole_loop_seal_id", self.whole_loop_seal_id),
        )
        object.__setattr__(
            self,
            "whole_loop_seal_sha256",
            _sha256("whole_loop_seal_sha256", self.whole_loop_seal_sha256),
        )
        if type(self.outcome_status) is not str or self.outcome_status not in _OUTCOME_STATUSES:
            raise RestartRecoveryError("unsupported whole-loop outcome status")
        object.__setattr__(self, "outcome_id", _text("outcome_id", self.outcome_id))
        object.__setattr__(
            self, "outcome_sha256", _sha256("outcome_sha256", self.outcome_sha256)
        )
        object.__setattr__(
            self,
            "unfinished_work_refs",
            _refs("unfinished_work_refs", self.unfinished_work_refs),
        )
        object.__setattr__(
            self,
            "completed_work_refs",
            _refs("completed_work_refs", self.completed_work_refs),
        )
        object.__setattr__(
            self,
            "effect_attempt_refs",
            _refs("effect_attempt_refs", self.effect_attempt_refs),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

        if self.causal_identity.generation != self.source_checkpoint_generation:
            raise RestartRecoveryError(
                "causal identity generation must equal restart checkpoint generation"
            )
        if causal_identity_ref(self.causal_identity) not in self.provenance_refs:
            raise RestartRecoveryError(
                "persisted recovery evidence lacks exact causal identity provenance ref"
            )

        unfinished = set(self.unfinished_work_refs)
        completed = set(self.completed_work_refs)
        effects = set(self.effect_attempt_refs)
        if unfinished & completed:
            raise RestartRecoveryError(
                "unfinished_work_refs and completed_work_refs must be disjoint"
            )

        if self.outcome_status == NO_EFFECT:
            if effects:
                raise RestartRecoveryError("NO_EFFECT cannot carry effect_attempt_refs")
            return

        if not effects:
            raise RestartRecoveryError(
                "effect outcome status requires explicit effect_attempt_refs"
            )

        if self.outcome_status == EFFECT_VERIFIED_APPLIED:
            if not effects.issubset(completed):
                raise RestartRecoveryError(
                    "VERIFIED_APPLIED effect_attempt_refs must be completed, not unfinished"
                )
            return

        if not effects.issubset(unfinished):
            raise RestartRecoveryError(
                "unresolved/NOT_APPLIED effect_attempt_refs must remain explicit unfinished work"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "evidence_id": self.evidence_id,
            "causal_identity": self.causal_identity.as_dict(),
            "causal_identity_sha256": self.causal_identity.sha256(),
            "source_checkpoint_id": self.source_checkpoint_id,
            "source_checkpoint_generation": self.source_checkpoint_generation,
            "source_checkpoint_sha256": self.source_checkpoint_sha256,
            "whole_loop_seal_id": self.whole_loop_seal_id,
            "whole_loop_seal_sha256": self.whole_loop_seal_sha256,
            "outcome_status": self.outcome_status,
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "unfinished_work_refs": list(self.unfinished_work_refs),
            "completed_work_refs": list(self.completed_work_refs),
            "effect_attempt_refs": list(self.effect_attempt_refs),
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_persisted_restart_evidence(
    *,
    evidence_id: str,
    causal_identity: CausalIdentity,
    source_checkpoint: PersistentAgencyCheckpoint,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
    unfinished_work_refs: Iterable[str] = (),
    completed_work_refs: Iterable[str] = (),
    effect_attempt_refs: Iterable[str] = (),
    provenance_refs: Iterable[str] = (),
) -> PersistedRestartEvidence:
    """Bind recovery evidence to concrete WP206/WP900/outcome objects and causal lineage."""
    if type(causal_identity) is not CausalIdentity:
        raise RestartRecoveryError("causal_identity must be concrete CausalIdentity")
    if type(source_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartRecoveryError(
            "source_checkpoint must be concrete PersistentAgencyCheckpoint"
        )
    if type(whole_loop_seal) is not WholePersistentLoopSeal:
        raise RestartRecoveryError(
            "whole_loop_seal must be concrete WholePersistentLoopSeal"
        )
    if type(outcome) is not LoopOutcomeEvidence:
        raise RestartRecoveryError("outcome must be concrete LoopOutcomeEvidence")

    checkpoint_sha = source_checkpoint.sha256()
    seal_sha = whole_loop_seal.sha256()
    outcome_sha = outcome.sha256()
    causal_ref = causal_identity_ref(causal_identity)

    if source_checkpoint.generation != causal_identity.generation:
        raise RestartRecoveryError("RECOVERY_CAUSAL_GENERATION_MISMATCH")
    if source_checkpoint.generation != whole_loop_seal.generation + 1:
        raise RestartRecoveryError("RECOVERY_SEAL_CHECKPOINT_GENERATION_MISMATCH")
    if whole_loop_seal.next_checkpoint_id != source_checkpoint.checkpoint_id:
        raise RestartRecoveryError("RECOVERY_SEAL_CHECKPOINT_ID_MISMATCH")
    if whole_loop_seal.next_checkpoint_sha256 != checkpoint_sha:
        raise RestartRecoveryError("RECOVERY_SEAL_CHECKPOINT_DIGEST_MISMATCH")
    if whole_loop_seal.outcome_id != outcome.outcome_id:
        raise RestartRecoveryError("RECOVERY_SEAL_OUTCOME_ID_MISMATCH")
    if whole_loop_seal.outcome_sha256 != outcome_sha:
        raise RestartRecoveryError("RECOVERY_SEAL_OUTCOME_DIGEST_MISMATCH")

    for label, refs in (
        ("checkpoint", source_checkpoint.provenance_refs),
        ("whole-loop seal", whole_loop_seal.provenance_refs),
        ("outcome", outcome.provenance_refs),
    ):
        if causal_ref not in refs:
            raise RestartRecoveryError(
                f"RECOVERY_CAUSAL_LINEAGE_REF_MISSING:{label}"
            )

    provenance = tuple(
        sorted(
            set(_refs("provenance_refs", provenance_refs))
            | {
                causal_ref,
                f"wp206:checkpoint:{source_checkpoint.checkpoint_id}:{checkpoint_sha}",
                f"wp900:whole-loop:{whole_loop_seal.seal_id}:{seal_sha}",
                f"wp900:outcome:{outcome.outcome_id}:{outcome_sha}",
            }
        )
    )

    return PersistedRestartEvidence(
        evidence_id=evidence_id,
        causal_identity=causal_identity,
        source_checkpoint_id=source_checkpoint.checkpoint_id,
        source_checkpoint_generation=source_checkpoint.generation,
        source_checkpoint_sha256=checkpoint_sha,
        whole_loop_seal_id=whole_loop_seal.seal_id,
        whole_loop_seal_sha256=seal_sha,
        outcome_status=outcome.status,
        outcome_id=outcome.outcome_id,
        outcome_sha256=outcome_sha,
        unfinished_work_refs=tuple(unfinished_work_refs),
        completed_work_refs=tuple(completed_work_refs),
        effect_attempt_refs=tuple(effect_attempt_refs),
        provenance_refs=provenance,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class RestartContinuationPlan:
    plan_id: str
    source_evidence_id: str
    source_evidence_sha256: str
    causal_identity: CausalIdentity
    source_checkpoint_id: str
    source_checkpoint_generation: int
    source_checkpoint_sha256: str
    whole_loop_seal_id: str
    whole_loop_seal_sha256: str
    outcome_id: str
    outcome_sha256: str
    candidate_generation: int
    disposition: str
    reason_code: str
    continuation_refs: tuple[str, ...]
    held_refs: tuple[str, ...]
    requires_effect_verification: bool
    requires_effect_reauthorization: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = RECOVERY_PLAN_SCHEMA
    classification: ClassVar[str] = PLAN_CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text("plan_id", self.plan_id))
        object.__setattr__(
            self, "source_evidence_id", _text("source_evidence_id", self.source_evidence_id)
        )
        object.__setattr__(
            self,
            "source_evidence_sha256",
            _sha256("source_evidence_sha256", self.source_evidence_sha256),
        )
        if type(self.causal_identity) is not CausalIdentity:
            raise RestartRecoveryError("causal_identity must be concrete CausalIdentity")
        object.__setattr__(
            self,
            "source_checkpoint_id",
            _text("source_checkpoint_id", self.source_checkpoint_id),
        )
        object.__setattr__(
            self,
            "source_checkpoint_generation",
            _generation("source_checkpoint_generation", self.source_checkpoint_generation),
        )
        object.__setattr__(
            self,
            "source_checkpoint_sha256",
            _sha256("source_checkpoint_sha256", self.source_checkpoint_sha256),
        )
        object.__setattr__(
            self,
            "whole_loop_seal_id",
            _text("whole_loop_seal_id", self.whole_loop_seal_id),
        )
        object.__setattr__(
            self,
            "whole_loop_seal_sha256",
            _sha256("whole_loop_seal_sha256", self.whole_loop_seal_sha256),
        )
        object.__setattr__(self, "outcome_id", _text("outcome_id", self.outcome_id))
        object.__setattr__(
            self, "outcome_sha256", _sha256("outcome_sha256", self.outcome_sha256)
        )
        object.__setattr__(
            self,
            "candidate_generation",
            _generation("candidate_generation", self.candidate_generation),
        )
        allowed_dispositions = {
            CONTINUE_UNFINISHED,
            HOLD_EFFECT_VERIFICATION,
            CONTINUE_WITH_EFFECT_REAUTH_HOLD,
            NO_CONTINUATION,
        }
        if self.disposition not in allowed_dispositions:
            raise RestartRecoveryError("unsupported recovery disposition")
        object.__setattr__(self, "reason_code", _text("reason_code", self.reason_code))
        object.__setattr__(
            self,
            "continuation_refs",
            _refs("continuation_refs", self.continuation_refs),
        )
        object.__setattr__(self, "held_refs", _refs("held_refs", self.held_refs))
        if type(self.requires_effect_verification) is not bool:
            raise RestartRecoveryError("requires_effect_verification must be exact bool")
        if type(self.requires_effect_reauthorization) is not bool:
            raise RestartRecoveryError("requires_effect_reauthorization must be exact bool")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        if set(self.continuation_refs) & set(self.held_refs):
            raise RestartRecoveryError("continuation_refs and held_refs must be disjoint")
        if self.causal_identity.generation != self.source_checkpoint_generation:
            raise RestartRecoveryError(
                "plan causal identity generation must equal source checkpoint generation"
            )
        if causal_identity_ref(self.causal_identity) not in self.provenance_refs:
            raise RestartRecoveryError("plan lacks exact causal identity provenance ref")
        if self.candidate_generation != self.source_checkpoint_generation + 1:
            raise RestartRecoveryError(
                "candidate_generation must be direct successor of source checkpoint generation"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "plan_id": self.plan_id,
            "source_evidence_id": self.source_evidence_id,
            "source_evidence_sha256": self.source_evidence_sha256,
            "causal_identity": self.causal_identity.as_dict(),
            "causal_identity_sha256": self.causal_identity.sha256(),
            "source_checkpoint_id": self.source_checkpoint_id,
            "source_checkpoint_generation": self.source_checkpoint_generation,
            "source_checkpoint_sha256": self.source_checkpoint_sha256,
            "whole_loop_seal_id": self.whole_loop_seal_id,
            "whole_loop_seal_sha256": self.whole_loop_seal_sha256,
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "candidate_generation": self.candidate_generation,
            "disposition": self.disposition,
            "reason_code": self.reason_code,
            "continuation_refs": list(self.continuation_refs),
            "held_refs": list(self.held_refs),
            "requires_effect_verification": self.requires_effect_verification,
            "requires_effect_reauthorization": self.requires_effect_reauthorization,
            "provenance_refs": list(self.provenance_refs),
            "scheduler_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "persistence_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def plan_restart_continuation(
    evidence: PersistedRestartEvidence,
    *,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    source_checkpoint: PersistentAgencyCheckpoint,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> RestartContinuationPlan:
    """Create one deterministic restart candidate from independently bound typed sources.

    Unlike generation 1, checkpoint/seal/outcome principal identities are not accepted as a
    second set of caller-supplied strings. They are re-derived from concrete validated source
    objects and compared to the persisted evidence before any continuation disposition exists.
    """
    if type(evidence) is not PersistedRestartEvidence:
        raise RestartRecoveryError("evidence must be concrete PersistedRestartEvidence")
    plan_id = _text("plan_id", plan_id)
    expected_evidence_sha256 = _sha256(
        "expected_evidence_sha256", expected_evidence_sha256
    )
    if type(causal_identity) is not CausalIdentity:
        raise RestartRecoveryError("causal_identity must be concrete CausalIdentity")

    if evidence.sha256() != expected_evidence_sha256:
        raise RestartRecoveryError("RECOVERY_EVIDENCE_DIGEST_MISMATCH")
    if evidence.causal_identity.as_dict() != causal_identity.as_dict():
        raise RestartRecoveryError("RECOVERY_CAUSAL_IDENTITY_MISMATCH")

    rebound = bind_persisted_restart_evidence(
        evidence_id=evidence.evidence_id,
        causal_identity=causal_identity,
        source_checkpoint=source_checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
        unfinished_work_refs=evidence.unfinished_work_refs,
        completed_work_refs=evidence.completed_work_refs,
        effect_attempt_refs=evidence.effect_attempt_refs,
        provenance_refs=evidence.provenance_refs,
    )
    if rebound.as_dict() != evidence.as_dict():
        raise RestartRecoveryError("RECOVERY_BOUND_SOURCE_OBJECT_MISMATCH")

    unfinished = set(evidence.unfinished_work_refs)
    effects = set(evidence.effect_attempt_refs)

    requires_verification = evidence.outcome_status in _UNRESOLVED_EFFECT_STATUSES
    requires_reauthorization = evidence.outcome_status == EFFECT_VERIFIED_NOT_APPLIED

    if requires_verification:
        disposition = HOLD_EFFECT_VERIFICATION
        reason = _REASON_VERIFY
        continuation: tuple[str, ...] = ()
        held = evidence.unfinished_work_refs
    elif not unfinished:
        disposition = NO_CONTINUATION
        reason = _REASON_NONE
        continuation = ()
        held = ()
    elif requires_reauthorization:
        disposition = CONTINUE_WITH_EFFECT_REAUTH_HOLD
        reason = _REASON_REAUTHORIZE
        continuation = tuple(sorted(unfinished - effects))
        held = tuple(sorted(effects))
    else:
        disposition = CONTINUE_UNFINISHED
        reason = _REASON_CONTINUE
        continuation = evidence.unfinished_work_refs
        held = ()

    provenance = tuple(
        sorted(
            set(evidence.provenance_refs)
            | {
                causal_identity_ref(causal_identity),
                f"wp901:evidence:{evidence.evidence_id}:{evidence.sha256()}",
                f"wp901:checkpoint:{evidence.source_checkpoint_id}:{evidence.source_checkpoint_sha256}",
                f"wp901:whole-loop:{evidence.whole_loop_seal_id}:{evidence.whole_loop_seal_sha256}",
                f"wp901:outcome:{evidence.outcome_id}:{evidence.outcome_sha256}",
            }
        )
    )

    return RestartContinuationPlan(
        plan_id=plan_id,
        source_evidence_id=evidence.evidence_id,
        source_evidence_sha256=evidence.sha256(),
        causal_identity=causal_identity,
        source_checkpoint_id=evidence.source_checkpoint_id,
        source_checkpoint_generation=evidence.source_checkpoint_generation,
        source_checkpoint_sha256=evidence.source_checkpoint_sha256,
        whole_loop_seal_id=evidence.whole_loop_seal_id,
        whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
        outcome_id=evidence.outcome_id,
        outcome_sha256=evidence.outcome_sha256,
        candidate_generation=evidence.source_checkpoint_generation + 1,
        disposition=disposition,
        reason_code=reason,
        continuation_refs=continuation,
        held_refs=held,
        requires_effect_verification=requires_verification,
        requires_effect_reauthorization=requires_reauthorization,
        provenance_refs=provenance,
    )


__all__ = [
    "CONTINUE_UNFINISHED",
    "CONTINUE_WITH_EFFECT_REAUTH_HOLD",
    "HOLD_EFFECT_VERIFICATION",
    "NO_CONTINUATION",
    "PersistedRestartEvidence",
    "RECOVERY_EVIDENCE_SCHEMA",
    "RECOVERY_PLAN_SCHEMA",
    "RestartContinuationPlan",
    "RestartRecoveryError",
    "bind_persisted_restart_evidence",
    "causal_identity_ref",
    "plan_restart_continuation",
]
