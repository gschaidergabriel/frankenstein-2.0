"""Deterministic multi-source PresenceKernel for F2-WP-703.

The kernel consumes exact, caller-supplied OBSERVED perception claims from the
F2-WP-701 epistemic boundary.  It does not acquire sensors, inspect payload text,
infer identity/activity, call a model/provider/tool, write UnifiedDB, or authorize
GWT/effects/completion.  Its only job is to determine whether bounded current
presence evidence is fresh, stale, insufficient, agreeing, conflicting, or absent.

One through four independent source slots are supported so multiple Retina workers
can contribute current observations without becoming separate truth authorities.
Repeated aliases of the same observation are rejected rather than counted twice.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

from .epistemic_perception import EpistemicPerceptClaim

PRESENCE_POLICY_SCHEMA = "FRANKENSTEIN2_PRESENCE_FRESHNESS_POLICY/v1"
PRESENCE_SOURCE_EVIDENCE_SCHEMA = "FRANKENSTEIN2_PRESENCE_SOURCE_EVIDENCE/v1"
FRESH_PRESENCE_SNAPSHOT_SCHEMA = "FRANKENSTEIN2_FRESH_PRESENCE_SNAPSHOT/v1"

PRESENT = "PRESENT"
ABSENT = "ABSENT"
UNKNOWN = "UNKNOWN"
CONFLICT = "CONFLICT"

FRESH = "FRESH"
STALE = "STALE"
INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"

_MAX_SOURCE_SLOTS = 4
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PresenceKernelError(ValueError):
    """Fail-closed validation error for the F2-WP-703 PresenceKernel."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PresenceKernelError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PresenceKernelError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PresenceKernelError(f"{name} must be an integer >= 0")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise PresenceKernelError(f"{name} must be an integer > 0")
    return value


def _confidence(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise PresenceKernelError("confidence_micros must be an integer in [0, 1000000]")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PresenceKernelError(f"{name} must be lowercase 64-hex sha256")
    return value


def _refs(name: str, values: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PresenceKernelError(f"{name} must be an immutable tuple")
    if not allow_empty and not values:
        raise PresenceKernelError(f"{name} must be non-empty")
    cleaned = tuple(_text(f"{name} item", item) for item in values)
    if len(cleaned) != len(set(cleaned)):
        raise PresenceKernelError(f"{name} must not contain duplicates")
    return tuple(sorted(cleaned))


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
        raise PresenceKernelError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PresenceFreshnessPolicy:
    """Explicit deterministic freshness/admission bounds; not sensing authority."""

    policy_id: str
    generation: int
    semantic_key: str
    allowed_modalities: tuple[str, ...]
    max_age_ns: int
    min_confidence_micros: int
    max_source_slots: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = PRESENCE_POLICY_SCHEMA
    classification: ClassVar[str] = (
        "PRESENCE_FRESHNESS_POLICY_NOT_SENSOR_WORLD_TRUTH_GWT_EFFECT_OR_COMPLETION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "semantic_key", _text("semantic_key", self.semantic_key))
        modalities = _refs("allowed_modalities", self.allowed_modalities)
        object.__setattr__(self, "allowed_modalities", modalities)
        _positive_int("max_age_ns", self.max_age_ns)
        _confidence(self.min_confidence_micros)
        if type(self.max_source_slots) is not int or not 1 <= self.max_source_slots <= _MAX_SOURCE_SLOTS:
            raise PresenceKernelError(
                f"max_source_slots must be an integer in [1, {_MAX_SOURCE_SLOTS}]"
            )
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "semantic_key": self.semantic_key,
            "allowed_modalities": list(self.allowed_modalities),
            "max_age_ns": self.max_age_ns,
            "min_confidence_micros": self.min_confidence_micros,
            "max_source_slots": self.max_source_slots,
            "hard_source_slot_ceiling": _MAX_SOURCE_SLOTS,
            "world_truth_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PresenceSourceBinding:
    """One explicit Retina/perception source bound to one exact observed claim."""

    source_id: str
    worker_id: str
    claim: EpistemicPerceptClaim
    expected_claim_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "worker_id", _text("worker_id", self.worker_id))
        if type(self.claim) is not EpistemicPerceptClaim:
            raise PresenceKernelError("claim must be a concrete EpistemicPerceptClaim")
        _sha256("expected_claim_sha256", self.expected_claim_sha256)
        if self.claim.sha256() != self.expected_claim_sha256:
            raise PresenceKernelError("claim digest mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class PresenceSourceEvidence:
    source_id: str
    worker_id: str
    claim_id: str
    claim_sha256: str
    modality: str
    source_generation: int
    source_time_ns: int
    confidence_micros: int
    freshness_status: str
    observed_user_present: bool
    upstream_retina_assessment_sha256: str | None
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = PRESENCE_SOURCE_EVIDENCE_SCHEMA
    classification: ClassVar[str] = (
        "PRESENCE_SOURCE_EVIDENCE_OBSERVED_REFERENCE_NOT_CANONICAL_WORLD_TRUTH_OR_EFFECT_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "worker_id", _text("worker_id", self.worker_id))
        object.__setattr__(self, "claim_id", _text("claim_id", self.claim_id))
        _sha256("claim_sha256", self.claim_sha256)
        object.__setattr__(self, "modality", _text("modality", self.modality))
        _nonnegative_int("source_generation", self.source_generation)
        _nonnegative_int("source_time_ns", self.source_time_ns)
        _confidence(self.confidence_micros)
        if self.freshness_status not in {FRESH, STALE, INSUFFICIENT_CONFIDENCE}:
            raise PresenceKernelError("unsupported freshness_status")
        if type(self.observed_user_present) is not bool:
            raise PresenceKernelError("observed_user_present must be bool")
        if self.upstream_retina_assessment_sha256 is not None:
            _sha256(
                "upstream_retina_assessment_sha256",
                self.upstream_retina_assessment_sha256,
            )
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_id": self.source_id,
            "worker_id": self.worker_id,
            "claim_id": self.claim_id,
            "claim_sha256": self.claim_sha256,
            "modality": self.modality,
            "source_generation": self.source_generation,
            "source_time_ns": self.source_time_ns,
            "confidence_micros": self.confidence_micros,
            "freshness_status": self.freshness_status,
            "observed_user_present": self.observed_user_present,
            "upstream_retina_assessment_sha256": self.upstream_retina_assessment_sha256,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class FreshPresenceSnapshot:
    snapshot_id: str
    evaluated_monotonic_ns: int
    policy_id: str
    policy_generation: int
    policy_sha256: str
    presence_status: str
    source_evidence: tuple[PresenceSourceEvidence, ...]
    fresh_present_claim_sha256s: tuple[str, ...]
    fresh_absent_claim_sha256s: tuple[str, ...]
    stale_source_ids: tuple[str, ...]
    insufficient_confidence_source_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = FRESH_PRESENCE_SNAPSHOT_SCHEMA
    classification: ClassVar[str] = (
        "FRESH_PRESENCE_READOUT_NOT_IDENTITY_ACTIVITY_WORLD_TRUTH_GWT_EFFECT_OR_COMPLETION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _text("snapshot_id", self.snapshot_id))
        _nonnegative_int("evaluated_monotonic_ns", self.evaluated_monotonic_ns)
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative_int("policy_generation", self.policy_generation)
        _sha256("policy_sha256", self.policy_sha256)
        if self.presence_status not in {PRESENT, ABSENT, UNKNOWN, CONFLICT}:
            raise PresenceKernelError("unsupported presence_status")
        if type(self.source_evidence) is not tuple or not self.source_evidence:
            raise PresenceKernelError("source_evidence must be a non-empty immutable tuple")
        if not 1 <= len(self.source_evidence) <= _MAX_SOURCE_SLOTS:
            raise PresenceKernelError("source_evidence count exceeds hard source-slot bounds")
        for evidence in self.source_evidence:
            if type(evidence) is not PresenceSourceEvidence:
                raise PresenceKernelError("source_evidence members must be concrete PresenceSourceEvidence")
        ordered = tuple(sorted(self.source_evidence, key=lambda item: item.source_id))
        if tuple(item.source_id for item in ordered) != tuple(item.source_id for item in self.source_evidence):
            raise PresenceKernelError("source_evidence must already be canonical source_id order")
        if len({item.source_id for item in ordered}) != len(ordered):
            raise PresenceKernelError("source_evidence source_id must be unique")
        if len({item.claim_sha256 for item in ordered}) != len(ordered):
            raise PresenceKernelError("the same observation claim cannot occupy multiple source slots")

        for name in (
            "fresh_present_claim_sha256s",
            "fresh_absent_claim_sha256s",
        ):
            digests = getattr(self, name)
            if type(digests) is not tuple:
                raise PresenceKernelError(f"{name} must be an immutable tuple")
            for digest in digests:
                _sha256(name, digest)
            if len(digests) != len(set(digests)):
                raise PresenceKernelError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, tuple(sorted(digests)))

        for name in ("stale_source_ids", "insufficient_confidence_source_ids"):
            ids = getattr(self, name)
            if type(ids) is not tuple:
                raise PresenceKernelError(f"{name} must be an immutable tuple")
            cleaned = tuple(_text(name, item) for item in ids)
            if len(cleaned) != len(set(cleaned)):
                raise PresenceKernelError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, tuple(sorted(cleaned)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

        has_present = bool(self.fresh_present_claim_sha256s)
        has_absent = bool(self.fresh_absent_claim_sha256s)
        expected = (
            CONFLICT if has_present and has_absent else
            PRESENT if has_present else
            ABSENT if has_absent else
            UNKNOWN
        )
        if self.presence_status != expected:
            raise PresenceKernelError("presence_status must equal exact fresh-evidence state")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "snapshot_id": self.snapshot_id,
            "evaluated_monotonic_ns": self.evaluated_monotonic_ns,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "presence_status": self.presence_status,
            "source_evidence": [item.as_dict() for item in self.source_evidence],
            "fresh_present_claim_sha256s": list(self.fresh_present_claim_sha256s),
            "fresh_absent_claim_sha256s": list(self.fresh_absent_claim_sha256s),
            "stale_source_ids": list(self.stale_source_ids),
            "insufficient_confidence_source_ids": list(self.insufficient_confidence_source_ids),
            "unknown_is_first_class": self.presence_status == UNKNOWN,
            "conflict_is_first_class": self.presence_status == CONFLICT,
            "source_slot_count": len(self.source_evidence),
            "max_supported_parallel_source_slots": _MAX_SOURCE_SLOTS,
            "raw_frame_present": False,
            "identity_inference": False,
            "activity_inference": False,
            "world_truth_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_policy(policy: PresenceFreshnessPolicy, expected_policy_sha256: str) -> None:
    if type(policy) is not PresenceFreshnessPolicy:
        raise PresenceKernelError("policy must be a concrete PresenceFreshnessPolicy")
    _sha256("expected_policy_sha256", expected_policy_sha256)
    if policy.sha256() != expected_policy_sha256:
        raise PresenceKernelError("policy digest mismatch")


def build_fresh_presence_snapshot(
    *,
    snapshot_id: str,
    evaluated_monotonic_ns: int,
    policy: PresenceFreshnessPolicy,
    expected_policy_sha256: str,
    sources: tuple[PresenceSourceBinding, ...],
    provenance_refs: tuple[str, ...],
) -> FreshPresenceSnapshot:
    """Aggregate exact current observations without creating a second truth authority."""

    snapshot_id = _text("snapshot_id", snapshot_id)
    now = _nonnegative_int("evaluated_monotonic_ns", evaluated_monotonic_ns)
    _verify_policy(policy, expected_policy_sha256)
    if type(sources) is not tuple or not sources:
        raise PresenceKernelError("sources must be a non-empty immutable tuple")
    if len(sources) > policy.max_source_slots or len(sources) > _MAX_SOURCE_SLOTS:
        raise PresenceKernelError("source count exceeds admitted policy/hard source-slot ceiling")

    seen_source_ids: set[str] = set()
    seen_claim_ids: set[str] = set()
    seen_claim_digests: set[str] = set()
    evidence_rows: list[PresenceSourceEvidence] = []
    present_digests: list[str] = []
    absent_digests: list[str] = []
    stale_source_ids: list[str] = []
    insufficient_source_ids: list[str] = []
    all_provenance = set(_refs("provenance_refs", provenance_refs)) | set(policy.provenance_refs)

    for binding in sources:
        if type(binding) is not PresenceSourceBinding:
            raise PresenceKernelError("sources must contain concrete PresenceSourceBinding instances")
        if binding.source_id in seen_source_ids:
            raise PresenceKernelError("source_id must be unique within one snapshot")
        seen_source_ids.add(binding.source_id)

        claim = binding.claim
        claim_digest = binding.expected_claim_sha256
        if claim.claim_id in seen_claim_ids or claim_digest in seen_claim_digests:
            raise PresenceKernelError("the same observation claim cannot be counted through multiple source slots")
        seen_claim_ids.add(claim.claim_id)
        seen_claim_digests.add(claim_digest)

        if claim.epistemic_type != "OBSERVED":
            raise PresenceKernelError("only OBSERVED claims may contribute to current presence")
        if claim.semantic_key != policy.semantic_key:
            raise PresenceKernelError("claim semantic_key does not match presence policy")
        if claim.modality not in policy.allowed_modalities:
            raise PresenceKernelError("claim modality is not admitted by presence policy")
        if type(claim.value) is not bool:
            raise PresenceKernelError("presence OBSERVED claim value must be an exact bool")
        if claim.source_time_ns > now:
            raise PresenceKernelError("claim source_time_ns is in the future relative to evaluation")

        age_ns = now - claim.source_time_ns
        if age_ns > policy.max_age_ns:
            freshness_status = STALE
            stale_source_ids.append(binding.source_id)
        elif claim.confidence_micros < policy.min_confidence_micros:
            freshness_status = INSUFFICIENT_CONFIDENCE
            insufficient_source_ids.append(binding.source_id)
        else:
            freshness_status = FRESH
            if claim.value:
                present_digests.append(claim_digest)
            else:
                absent_digests.append(claim_digest)

        all_provenance.update(claim.provenance_refs)
        evidence_rows.append(
            PresenceSourceEvidence(
                source_id=binding.source_id,
                worker_id=binding.worker_id,
                claim_id=claim.claim_id,
                claim_sha256=claim_digest,
                modality=claim.modality,
                source_generation=claim.source_generation,
                source_time_ns=claim.source_time_ns,
                confidence_micros=claim.confidence_micros,
                freshness_status=freshness_status,
                observed_user_present=claim.value,
                upstream_retina_assessment_sha256=claim.upstream_retina_assessment_sha256,
                provenance_refs=claim.provenance_refs,
            )
        )

    has_present = bool(present_digests)
    has_absent = bool(absent_digests)
    status = (
        CONFLICT if has_present and has_absent else
        PRESENT if has_present else
        ABSENT if has_absent else
        UNKNOWN
    )

    return FreshPresenceSnapshot(
        snapshot_id=snapshot_id,
        evaluated_monotonic_ns=now,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=expected_policy_sha256,
        presence_status=status,
        source_evidence=tuple(sorted(evidence_rows, key=lambda item: item.source_id)),
        fresh_present_claim_sha256s=tuple(sorted(present_digests)),
        fresh_absent_claim_sha256s=tuple(sorted(absent_digests)),
        stale_source_ids=tuple(sorted(stale_source_ids)),
        insufficient_confidence_source_ids=tuple(sorted(insufficient_source_ids)),
        provenance_refs=tuple(sorted(all_provenance)),
    )
