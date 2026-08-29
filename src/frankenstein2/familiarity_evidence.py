"""Deterministic soft-familiarity evidence boundary for F2-WP-706.

This module does not inspect images or identify people. It only evaluates
caller-supplied, content-bound evidence about scene/object-state familiarity.
Fresh external observations, cheap/self-derived matches and retrieved priors
remain mechanically distinct so cheap matches cannot promote their own
prototype or masquerade as current observation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

EVIDENCE_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_EVIDENCE/v1"
DECISION_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_DECISION/v1"
_KINDS = frozenset({"FRESH_EXPENSIVE_CONFIRMATION", "CHEAP_MATCH", "RETRIEVED_PRIOR"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_SCOPE_TOKENS = frozenset({"person", "face", "identity", "biometric", "biometrics"})


class FamiliarityEvidenceError(ValueError):
    """Fail-closed validation error for F2-WP-706."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FamiliarityEvidenceError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise FamiliarityEvidenceError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FamiliarityEvidenceError(f"{name} must be an integer >= 0")
    return value


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FamiliarityEvidenceError(f"{name} must be an integer > 0")
    return value


def _confidence(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise FamiliarityEvidenceError("confidence_micros must be an integer in [0, 1000000]")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise FamiliarityEvidenceError(f"{name} must be lowercase sha256 hex")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise FamiliarityEvidenceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _scene_object_scope(semantic_key: Any) -> str:
    semantic_key = _text("semantic_key", semantic_key)
    tokens = {token for token in re.split(r"[^a-z0-9]+", semantic_key.lower()) if token}
    if tokens & _FORBIDDEN_SCOPE_TOKENS:
        raise FamiliarityEvidenceError("familiarity scope must not target person/face/identity/biometrics")
    return semantic_key


@dataclass(frozen=True, slots=True, kw_only=True)
class FamiliarityEvidence:
    evidence_id: str
    prototype_id: str
    prototype_generation: int
    semantic_key: str
    evidence_kind: str
    evidence_time_ns: int
    confidence_micros: int
    provenance_refs: tuple[str, ...]
    observed_claim_sha256: str | None = None
    independence_key: str | None = None

    schema: ClassVar[str] = EVIDENCE_SCHEMA
    classification: ClassVar[str] = "FAMILIARITY_CANDIDATE_EVIDENCE_NOT_WORLD_TRUTH_IDENTITY_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text("evidence_id", self.evidence_id))
        object.__setattr__(self, "prototype_id", _text("prototype_id", self.prototype_id))
        _nonnegative_int("prototype_generation", self.prototype_generation)
        object.__setattr__(self, "semantic_key", _scene_object_scope(self.semantic_key))
        if self.evidence_kind not in _KINDS:
            raise FamiliarityEvidenceError("unsupported evidence_kind")
        _nonnegative_int("evidence_time_ns", self.evidence_time_ns)
        _confidence(self.confidence_micros)
        if not isinstance(self.provenance_refs, tuple) or not self.provenance_refs:
            raise FamiliarityEvidenceError("provenance_refs must be a non-empty immutable tuple")
        refs = tuple(sorted(_text("provenance_ref", ref) for ref in self.provenance_refs))
        if len(refs) != len(set(refs)):
            raise FamiliarityEvidenceError("provenance_refs must not contain duplicates")
        object.__setattr__(self, "provenance_refs", refs)

        if self.evidence_kind == "FRESH_EXPENSIVE_CONFIRMATION":
            if self.observed_claim_sha256 is None:
                raise FamiliarityEvidenceError("fresh confirmation requires observed_claim_sha256")
            _sha256("observed_claim_sha256", self.observed_claim_sha256)
            if self.independence_key is None:
                raise FamiliarityEvidenceError("fresh confirmation requires independence_key")
            object.__setattr__(self, "independence_key", _text("independence_key", self.independence_key))
        else:
            if self.observed_claim_sha256 is not None:
                raise FamiliarityEvidenceError("cheap/retrieved evidence cannot masquerade as current observation")
            if self.independence_key is not None:
                raise FamiliarityEvidenceError("cheap/retrieved evidence cannot claim independent fresh-confirmation identity")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "evidence_id": self.evidence_id,
            "prototype_id": self.prototype_id,
            "prototype_generation": self.prototype_generation,
            "semantic_key": self.semantic_key,
            "evidence_kind": self.evidence_kind,
            "evidence_time_ns": self.evidence_time_ns,
            "confidence_micros": self.confidence_micros,
            "provenance_refs": list(self.provenance_refs),
            "observed_claim_sha256": self.observed_claim_sha256,
            "independence_key": self.independence_key,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class FamiliarityPromotionPolicy:
    min_independent_fresh_confirmations: int = 3
    min_fresh_span_ns: int = 30_000_000_000
    max_independent_fresh_confirmations: int = 16

    def __post_init__(self) -> None:
        _positive_int("min_independent_fresh_confirmations", self.min_independent_fresh_confirmations)
        _positive_int("min_fresh_span_ns", self.min_fresh_span_ns)
        _positive_int("max_independent_fresh_confirmations", self.max_independent_fresh_confirmations)
        if self.min_independent_fresh_confirmations > self.max_independent_fresh_confirmations:
            raise FamiliarityEvidenceError("minimum confirmations cannot exceed bounded maximum")
        if self.max_independent_fresh_confirmations > 64:
            raise FamiliarityEvidenceError("confirmation bound exceeds hard safety cap")


@dataclass(frozen=True, slots=True, kw_only=True)
class FamiliarityDecision:
    prototype_id: str
    prototype_generation: int
    semantic_key: str
    status: str
    evidence_sha256s: tuple[str, ...]
    fresh_confirmation_sha256s: tuple[str, ...]
    cheap_match_sha256s: tuple[str, ...]
    retrieved_prior_sha256s: tuple[str, ...]
    independent_fresh_confirmation_count: int
    fresh_confirmation_span_ns: int
    latest_fresh_confirmation_time_ns: int | None
    promotion_eligible: bool
    current_observation_present: bool

    schema: ClassVar[str] = DECISION_SCHEMA
    classification: ClassVar[str] = "SOFT_FAMILIARITY_READOUT_NOT_CANONICAL_WORLD_TRUTH_IDENTITY_GWT_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "prototype_id", _text("prototype_id", self.prototype_id))
        _nonnegative_int("prototype_generation", self.prototype_generation)
        object.__setattr__(self, "semantic_key", _scene_object_scope(self.semantic_key))
        if self.status not in {"FAMILIAR_CURRENT_CONFIRMED", "FAMILIAR_CANDIDATE_CHEAP", "UNKNOWN_OPEN_SET"}:
            raise FamiliarityEvidenceError("unsupported familiarity status")
        for name in ("evidence_sha256s", "fresh_confirmation_sha256s", "cheap_match_sha256s", "retrieved_prior_sha256s"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise FamiliarityEvidenceError(f"{name} must be an immutable tuple")
            for digest in value:
                _sha256(name, digest)
            if len(value) != len(set(value)):
                raise FamiliarityEvidenceError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, tuple(sorted(value)))
        _nonnegative_int("independent_fresh_confirmation_count", self.independent_fresh_confirmation_count)
        _nonnegative_int("fresh_confirmation_span_ns", self.fresh_confirmation_span_ns)
        if self.latest_fresh_confirmation_time_ns is not None:
            _nonnegative_int("latest_fresh_confirmation_time_ns", self.latest_fresh_confirmation_time_ns)
        if type(self.promotion_eligible) is not bool or type(self.current_observation_present) is not bool:
            raise FamiliarityEvidenceError("promotion/current-observation flags must be booleans")
        if self.promotion_eligible and not self.current_observation_present:
            raise FamiliarityEvidenceError("promotion cannot be eligible without fresh current-observation evidence")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "prototype_id": self.prototype_id,
            "prototype_generation": self.prototype_generation,
            "semantic_key": self.semantic_key,
            "status": self.status,
            "evidence_sha256s": list(self.evidence_sha256s),
            "fresh_confirmation_sha256s": list(self.fresh_confirmation_sha256s),
            "cheap_match_sha256s": list(self.cheap_match_sha256s),
            "retrieved_prior_sha256s": list(self.retrieved_prior_sha256s),
            "independent_fresh_confirmation_count": self.independent_fresh_confirmation_count,
            "fresh_confirmation_span_ns": self.fresh_confirmation_span_ns,
            "latest_fresh_confirmation_time_ns": self.latest_fresh_confirmation_time_ns,
            "promotion_eligible": self.promotion_eligible,
            "current_observation_present": self.current_observation_present,
            "cheap_match_can_promote": False,
            "retrieval_can_become_current_observation": False,
            "person_identity_scope_allowed": False,
            "world_truth_authority": "NONE",
            "identity_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def evaluate_familiarity(*, prototype_id: str, prototype_generation: int, semantic_key: str,
    evidence: tuple[tuple[FamiliarityEvidence, str], ...],
    policy: FamiliarityPromotionPolicy = FamiliarityPromotionPolicy()) -> FamiliarityDecision:
    """Evaluate one prototype without allowing self-reinforcing cheap evidence."""
    prototype_id = _text("prototype_id", prototype_id)
    _nonnegative_int("prototype_generation", prototype_generation)
    semantic_key = _scene_object_scope(semantic_key)
    if not isinstance(evidence, tuple):
        raise FamiliarityEvidenceError("evidence must be an immutable tuple")
    if type(policy) is not FamiliarityPromotionPolicy:
        raise FamiliarityEvidenceError("policy must be FamiliarityPromotionPolicy")

    seen_ids: set[str] = set()
    all_digests: list[str] = []
    fresh: list[tuple[FamiliarityEvidence, str]] = []
    cheap: list[tuple[FamiliarityEvidence, str]] = []
    retrieved: list[tuple[FamiliarityEvidence, str]] = []

    for item in evidence:
        if not isinstance(item, tuple) or len(item) != 2:
            raise FamiliarityEvidenceError("evidence items must be (evidence, expected_sha256)")
        event, expected = item
        if type(event) is not FamiliarityEvidence:
            raise FamiliarityEvidenceError("evidence items must contain concrete FamiliarityEvidence")
        _sha256("expected evidence sha256", expected)
        if event.sha256() != expected:
            raise FamiliarityEvidenceError("evidence digest mismatch")
        if event.evidence_id in seen_ids:
            raise FamiliarityEvidenceError("evidence_id must be unique")
        seen_ids.add(event.evidence_id)
        if event.prototype_id != prototype_id or event.prototype_generation != prototype_generation or event.semantic_key != semantic_key:
            raise FamiliarityEvidenceError("prototype/generation/semantic scope mismatch")
        all_digests.append(expected)
        if event.evidence_kind == "FRESH_EXPENSIVE_CONFIRMATION":
            fresh.append((event, expected))
        elif event.evidence_kind == "CHEAP_MATCH":
            cheap.append((event, expected))
        else:
            retrieved.append((event, expected))

    independent: dict[str, FamiliarityEvidence] = {}
    for event, _ in sorted(fresh, key=lambda item: (item[0].evidence_time_ns, item[0].evidence_id)):
        assert event.independence_key is not None
        prior = independent.get(event.independence_key)
        if prior is None or event.evidence_time_ns < prior.evidence_time_ns:
            independent[event.independence_key] = event

    independent_events = sorted(independent.values(), key=lambda event: (event.evidence_time_ns, event.evidence_id))
    independent_count = len(independent_events)
    if independent_count:
        times = [event.evidence_time_ns for event in independent_events]
        fresh_span = max(times) - min(times)
        latest_fresh = max(event.evidence_time_ns for event, _ in fresh)
    else:
        fresh_span = 0
        latest_fresh = None

    bounded_count = min(independent_count, policy.max_independent_fresh_confirmations)
    promotion_eligible = bounded_count >= policy.min_independent_fresh_confirmations and fresh_span >= policy.min_fresh_span_ns

    if fresh:
        status = "FAMILIAR_CURRENT_CONFIRMED"
        current_observation_present = True
    elif cheap:
        status = "FAMILIAR_CANDIDATE_CHEAP"
        current_observation_present = False
        promotion_eligible = False
    else:
        status = "UNKNOWN_OPEN_SET"
        current_observation_present = False
        promotion_eligible = False

    return FamiliarityDecision(
        prototype_id=prototype_id,
        prototype_generation=prototype_generation,
        semantic_key=semantic_key,
        status=status,
        evidence_sha256s=tuple(all_digests),
        fresh_confirmation_sha256s=tuple(digest for _, digest in fresh),
        cheap_match_sha256s=tuple(digest for _, digest in cheap),
        retrieved_prior_sha256s=tuple(digest for _, digest in retrieved),
        independent_fresh_confirmation_count=independent_count,
        fresh_confirmation_span_ns=fresh_span,
        latest_fresh_confirmation_time_ns=latest_fresh,
        promotion_eligible=promotion_eligible,
        current_observation_present=current_observation_present,
    )
