"""Epistemic perception typing boundary for F2-WP-701.

OBSERVED, INFERRED and RETRIEVED claims remain structurally distinct. A current
observation may be accompanied by hypotheses or memory, but neither can overwrite,
upgrade or silently replace the observation. Without a current observation the field
remains UNKNOWN, even when inference or retrieval is confident or repeated.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

CLAIM_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_PERCEPT_CLAIM/v1"
FIELD_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_PERCEPT_FIELD/v1"
_TYPES = frozenset({"OBSERVED", "INFERRED", "RETRIEVED"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EpistemicPerceptionError(ValueError):
    """Fail-closed validation error for F2-WP-701."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EpistemicPerceptionError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EpistemicPerceptionError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EpistemicPerceptionError(f"{name} must be an integer >= 0")
    return value


def _confidence(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise EpistemicPerceptionError("confidence_micros must be an integer in [0, 1000000]")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise EpistemicPerceptionError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise EpistemicPerceptionError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise EpistemicPerceptionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EpistemicPerceptionError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    # Canonical round-trip rejects non-JSON objects and normalizes dict ordering semantics.
    encoded = _canonical_json(value)
    return json.loads(encoded)


@dataclass(frozen=True, slots=True, kw_only=True)
class EpistemicPerceptClaim:
    claim_id: str
    semantic_key: str
    modality: str
    epistemic_type: str
    value: Any
    confidence_micros: int
    source_generation: int
    source_time_ns: int
    provenance_refs: tuple[str, ...]
    upstream_retina_assessment_sha256: str | None = None

    schema: ClassVar[str] = CLAIM_SCHEMA
    classification: ClassVar[str] = "PERCEPT_CLAIM_CANDIDATE_NOT_CANONICAL_WORLD_TRUTH_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text("claim_id", self.claim_id))
        object.__setattr__(self, "semantic_key", _text("semantic_key", self.semantic_key))
        object.__setattr__(self, "modality", _text("modality", self.modality))
        if self.epistemic_type not in _TYPES:
            raise EpistemicPerceptionError("epistemic_type must be OBSERVED, INFERRED or RETRIEVED")
        object.__setattr__(self, "value", _json_value(self.value))
        _confidence(self.confidence_micros)
        _nonnegative_int("source_generation", self.source_generation)
        _nonnegative_int("source_time_ns", self.source_time_ns)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if self.upstream_retina_assessment_sha256 is not None:
            _sha256("upstream_retina_assessment_sha256", self.upstream_retina_assessment_sha256)
        if self.epistemic_type == "RETRIEVED" and self.upstream_retina_assessment_sha256 is not None:
            raise EpistemicPerceptionError("RETRIEVED memory must not masquerade as a current Retina observation")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "claim_id": self.claim_id,
            "semantic_key": self.semantic_key,
            "modality": self.modality,
            "epistemic_type": self.epistemic_type,
            "value": self.value,
            "confidence_micros": self.confidence_micros,
            "source_generation": self.source_generation,
            "source_time_ns": self.source_time_ns,
            "provenance_refs": list(self.provenance_refs),
            "upstream_retina_assessment_sha256": self.upstream_retina_assessment_sha256,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class EpistemicPerceptField:
    field_id: str
    semantic_key: str
    modality: str
    current_status: str
    observed_claim_sha256: str | None
    effective_observed_value: Any | None
    effective_observed_confidence_micros: int | None
    inferred_claim_sha256s: tuple[str, ...]
    retrieved_claim_sha256s: tuple[str, ...]
    contradiction_claim_sha256s: tuple[str, ...]
    corroborating_claim_sha256s: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = FIELD_SCHEMA
    classification: ClassVar[str] = "EPISTEMIC_PERCEPT_FIELD_READOUT_NOT_CANONICAL_WORLD_TRUTH_GWT_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_id", _text("field_id", self.field_id))
        object.__setattr__(self, "semantic_key", _text("semantic_key", self.semantic_key))
        object.__setattr__(self, "modality", _text("modality", self.modality))
        if self.current_status not in {"OBSERVED_PRESENT", "UNKNOWN_NO_CURRENT_OBSERVATION"}:
            raise EpistemicPerceptionError("unsupported current_status")
        if self.current_status == "OBSERVED_PRESENT":
            if self.observed_claim_sha256 is None or self.effective_observed_confidence_micros is None:
                raise EpistemicPerceptionError("OBSERVED_PRESENT requires exact observed identity and confidence")
            _sha256("observed_claim_sha256", self.observed_claim_sha256)
            _confidence(self.effective_observed_confidence_micros)
            object.__setattr__(self, "effective_observed_value", _json_value(self.effective_observed_value))
        else:
            if self.observed_claim_sha256 is not None or self.effective_observed_value is not None or self.effective_observed_confidence_micros is not None:
                raise EpistemicPerceptionError("UNKNOWN field cannot expose an effective observation")
        for name in ("inferred_claim_sha256s", "retrieved_claim_sha256s", "contradiction_claim_sha256s", "corroborating_claim_sha256s"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise EpistemicPerceptionError(f"{name} must be an immutable tuple")
            for digest in value:
                _sha256(name, digest)
            if len(value) != len(set(value)):
                raise EpistemicPerceptionError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, tuple(sorted(value)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "field_id": self.field_id,
            "semantic_key": self.semantic_key,
            "modality": self.modality,
            "current_status": self.current_status,
            "observed_claim_sha256": self.observed_claim_sha256,
            "effective_observed_value": self.effective_observed_value,
            "effective_observed_confidence_micros": self.effective_observed_confidence_micros,
            "inferred_claim_sha256s": list(self.inferred_claim_sha256s),
            "retrieved_claim_sha256s": list(self.retrieved_claim_sha256s),
            "contradiction_claim_sha256s": list(self.contradiction_claim_sha256s),
            "corroborating_claim_sha256s": list(self.corroborating_claim_sha256s),
            "unknown_is_first_class": self.current_status == "UNKNOWN_NO_CURRENT_OBSERVATION",
            "memory_can_override_observation": False,
            "inference_can_upgrade_to_observation": False,
            "world_truth_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_claim(claim: EpistemicPerceptClaim, expected_sha256: str, *, expected_type: str) -> None:
    if type(claim) is not EpistemicPerceptClaim:
        raise EpistemicPerceptionError("claims must be concrete EpistemicPerceptClaim instances")
    _sha256("expected claim sha256", expected_sha256)
    if claim.sha256() != expected_sha256:
        raise EpistemicPerceptionError("claim digest mismatch")
    if claim.epistemic_type != expected_type:
        raise EpistemicPerceptionError(f"claim is not {expected_type}")


def build_epistemic_field(*, field_id: str, semantic_key: str, modality: str,
    observed: tuple[EpistemicPerceptClaim, str] | None = None,
    inferred: tuple[tuple[EpistemicPerceptClaim, str], ...] = (),
    retrieved: tuple[tuple[EpistemicPerceptClaim, str], ...] = (),
    provenance_refs: tuple[str, ...]) -> EpistemicPerceptField:
    """Fuse typed candidates while preserving the observation/memory authority boundary."""
    semantic_key = _text("semantic_key", semantic_key)
    modality = _text("modality", modality)
    if not isinstance(inferred, tuple) or not isinstance(retrieved, tuple):
        raise EpistemicPerceptionError("inferred and retrieved inputs must be immutable tuples")

    observed_claim = None
    observed_digest = None
    if observed is not None:
        if not isinstance(observed, tuple) or len(observed) != 2:
            raise EpistemicPerceptionError("observed must be (claim, expected_sha256)")
        observed_claim, observed_digest = observed
        _verify_claim(observed_claim, observed_digest, expected_type="OBSERVED")

    checked_inferred: list[tuple[EpistemicPerceptClaim, str]] = []
    checked_retrieved: list[tuple[EpistemicPerceptClaim, str]] = []
    seen_claim_ids: set[str] = set()

    def check_group(group: tuple[tuple[EpistemicPerceptClaim, str], ...], expected_type: str,
                    target: list[tuple[EpistemicPerceptClaim, str]]) -> None:
        for item in group:
            if not isinstance(item, tuple) or len(item) != 2:
                raise EpistemicPerceptionError("claim groups require (claim, expected_sha256) pairs")
            claim, expected = item
            _verify_claim(claim, expected, expected_type=expected_type)
            if claim.claim_id in seen_claim_ids:
                raise EpistemicPerceptionError("claim_id must be unique within a field build")
            seen_claim_ids.add(claim.claim_id)
            target.append((claim, expected))

    if observed_claim is not None:
        seen_claim_ids.add(observed_claim.claim_id)
    check_group(inferred, "INFERRED", checked_inferred)
    check_group(retrieved, "RETRIEVED", checked_retrieved)

    all_claims = ([observed_claim] if observed_claim is not None else []) + [c for c, _ in checked_inferred] + [c for c, _ in checked_retrieved]
    for claim in all_claims:
        if claim.semantic_key != semantic_key or claim.modality != modality:
            raise EpistemicPerceptionError("semantic_key/modality mismatch across percept field")

    inferred_digests = tuple(expected for _, expected in checked_inferred)
    retrieved_digests = tuple(expected for _, expected in checked_retrieved)
    contradictions: list[str] = []
    corroborating: list[str] = []

    if observed_claim is None:
        status = "UNKNOWN_NO_CURRENT_OBSERVATION"
        effective_value = None
        effective_confidence = None
        observed_digest = None
    else:
        status = "OBSERVED_PRESENT"
        effective_value = observed_claim.value
        # Critical invariant: inference/retrieval never raises or lowers the observed confidence.
        effective_confidence = observed_claim.confidence_micros
        observed_value_json = _canonical_json(observed_claim.value)
        for claim, digest in checked_inferred + checked_retrieved:
            if _canonical_json(claim.value) == observed_value_json:
                corroborating.append(digest)
            else:
                contradictions.append(digest)

    return EpistemicPerceptField(
        field_id=field_id,
        semantic_key=semantic_key,
        modality=modality,
        current_status=status,
        observed_claim_sha256=observed_digest,
        effective_observed_value=effective_value,
        effective_observed_confidence_micros=effective_confidence,
        inferred_claim_sha256s=inferred_digests,
        retrieved_claim_sha256s=retrieved_digests,
        contradiction_claim_sha256s=tuple(contradictions),
        corroborating_claim_sha256s=tuple(corroborating),
        provenance_refs=provenance_refs,
    )
