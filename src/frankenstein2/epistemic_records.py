"""Deterministic epistemic record primitives for Frankenstein 2.0 Stage 3.

These records preserve the distinction between observation, inference, retrieval prior,
negative result and explicit unknown. They are evidence/candidate metadata only. They do
not grant canonical-state, world-truth, goal, scheduler, effect or completion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar


class EpistemicRecordError(ValueError):
    """Fail-closed validation error for typed epistemic records."""


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicRecordError(f"{name} must be a non-empty string")
    return value


def _require_sha256(name: str, value: Any) -> str:
    value = _require_text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise EpistemicRecordError(f"{name} must be a lowercase sha256 hex digest")
    return value


def _require_refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise EpistemicRecordError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise EpistemicRecordError(f"{name} must not be empty")
    normalized: list[str] = []
    for item in value:
        normalized.append(_require_text(f"{name} item", item))
    if len(set(normalized)) != len(normalized):
        raise EpistemicRecordError(f"{name} must not contain duplicates")
    return tuple(normalized)


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
        raise EpistemicRecordError("payload must be canonical-JSON encodable") from exc


def _canonical_payload_json(value: Any) -> str:
    return _canonical_json(value)


def _validate_canonical_payload_json(value: Any) -> str:
    value = _require_text("payload_json", value)
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise EpistemicRecordError("payload_json must contain valid JSON") from exc
    if _canonical_json(parsed) != value:
        raise EpistemicRecordError("payload_json must already be canonical JSON")
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class _EpistemicRecordBase:
    """Shared immutable identity surface; classification is fixed by concrete type."""

    record_id: str
    generation: int
    payload_json: str
    provenance_sha256: str
    causal_refs: tuple[str, ...] = ()

    schema: ClassVar[str]
    classification: ClassVar[str]

    def __post_init__(self) -> None:
        _require_text("record_id", self.record_id)
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise EpistemicRecordError("generation must be an integer")
        if self.generation < 0:
            raise EpistemicRecordError("generation must be >= 0")
        _validate_canonical_payload_json(self.payload_json)
        _require_sha256("provenance_sha256", self.provenance_sha256)
        _require_refs("causal_refs", self.causal_refs, allow_empty=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "record_id": self.record_id,
            "generation": self.generation,
            "payload_json": self.payload_json,
            "provenance_sha256": self.provenance_sha256,
            "causal_refs": list(self.causal_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    @property
    def identity_sha256(self) -> str:
        return _sha256_text(self.canonical_json())

    def payload(self) -> Any:
        """Return a fresh decoded payload; mutation cannot alter record identity."""
        return json.loads(self.payload_json)


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservedEvidence(_EpistemicRecordBase):
    observation_ref: str

    schema: ClassVar[str] = "FRANKENSTEIN2_OBSERVED_EVIDENCE/v1"
    classification: ClassVar[str] = "OBSERVED_EVIDENCE_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        _EpistemicRecordBase.__post_init__(self)
        _require_text("observation_ref", self.observation_ref)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        generation: int,
        payload: Any,
        provenance_sha256: str,
        observation_ref: str,
        causal_refs: tuple[str, ...] = (),
    ) -> "ObservedEvidence":
        return cls(
            record_id=record_id,
            generation=generation,
            payload_json=_canonical_payload_json(payload),
            provenance_sha256=provenance_sha256,
            causal_refs=causal_refs,
            observation_ref=observation_ref,
        )

    def as_dict(self) -> dict[str, Any]:
        value = _EpistemicRecordBase.as_dict(self)
        value["observation_ref"] = self.observation_ref
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class InferredHypothesis(_EpistemicRecordBase):
    support_refs: tuple[str, ...]

    schema: ClassVar[str] = "FRANKENSTEIN2_INFERRED_HYPOTHESIS/v1"
    classification: ClassVar[str] = "INFERRED_HYPOTHESIS_NOT_OBSERVATION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        _EpistemicRecordBase.__post_init__(self)
        _require_refs("support_refs", self.support_refs, allow_empty=False)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        generation: int,
        payload: Any,
        provenance_sha256: str,
        support_refs: tuple[str, ...],
        causal_refs: tuple[str, ...] = (),
    ) -> "InferredHypothesis":
        return cls(
            record_id=record_id,
            generation=generation,
            payload_json=_canonical_payload_json(payload),
            provenance_sha256=provenance_sha256,
            causal_refs=causal_refs,
            support_refs=support_refs,
        )

    def as_dict(self) -> dict[str, Any]:
        value = _EpistemicRecordBase.as_dict(self)
        value["support_refs"] = list(self.support_refs)
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalPrior(_EpistemicRecordBase):
    retrieval_ref: str
    query_sha256: str

    schema: ClassVar[str] = "FRANKENSTEIN2_RETRIEVAL_PRIOR/v1"
    classification: ClassVar[str] = "RETRIEVAL_PRIOR_NOT_OBSERVATION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        _EpistemicRecordBase.__post_init__(self)
        _require_text("retrieval_ref", self.retrieval_ref)
        _require_sha256("query_sha256", self.query_sha256)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        generation: int,
        payload: Any,
        provenance_sha256: str,
        retrieval_ref: str,
        query_sha256: str,
        causal_refs: tuple[str, ...] = (),
    ) -> "RetrievalPrior":
        return cls(
            record_id=record_id,
            generation=generation,
            payload_json=_canonical_payload_json(payload),
            provenance_sha256=provenance_sha256,
            causal_refs=causal_refs,
            retrieval_ref=retrieval_ref,
            query_sha256=query_sha256,
        )

    def as_dict(self) -> dict[str, Any]:
        value = _EpistemicRecordBase.as_dict(self)
        value.update(
            {
                "retrieval_ref": self.retrieval_ref,
                "query_sha256": self.query_sha256,
            }
        )
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class NegativeResult(_EpistemicRecordBase):
    attempt_ref: str
    falsifier_ref: str

    schema: ClassVar[str] = "FRANKENSTEIN2_NEGATIVE_RESULT/v1"
    classification: ClassVar[str] = "NEGATIVE_RESULT_NOT_ABSENCE_OF_ALL_ALTERNATIVES"

    def __post_init__(self) -> None:
        _EpistemicRecordBase.__post_init__(self)
        _require_text("attempt_ref", self.attempt_ref)
        _require_text("falsifier_ref", self.falsifier_ref)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        generation: int,
        payload: Any,
        provenance_sha256: str,
        attempt_ref: str,
        falsifier_ref: str,
        causal_refs: tuple[str, ...] = (),
    ) -> "NegativeResult":
        return cls(
            record_id=record_id,
            generation=generation,
            payload_json=_canonical_payload_json(payload),
            provenance_sha256=provenance_sha256,
            causal_refs=causal_refs,
            attempt_ref=attempt_ref,
            falsifier_ref=falsifier_ref,
        )

    def as_dict(self) -> dict[str, Any]:
        value = _EpistemicRecordBase.as_dict(self)
        value.update(
            {
                "attempt_ref": self.attempt_ref,
                "falsifier_ref": self.falsifier_ref,
            }
        )
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownEvidence(_EpistemicRecordBase):
    reason: str

    schema: ClassVar[str] = "FRANKENSTEIN2_UNKNOWN_EVIDENCE/v1"
    classification: ClassVar[str] = "UNKNOWN_NOT_FILLED_BY_INFERENCE_OR_RETRIEVAL"

    def __post_init__(self) -> None:
        _EpistemicRecordBase.__post_init__(self)
        _require_text("reason", self.reason)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        generation: int,
        payload: Any,
        provenance_sha256: str,
        reason: str,
        causal_refs: tuple[str, ...] = (),
    ) -> "UnknownEvidence":
        return cls(
            record_id=record_id,
            generation=generation,
            payload_json=_canonical_payload_json(payload),
            provenance_sha256=provenance_sha256,
            causal_refs=causal_refs,
            reason=reason,
        )

    def as_dict(self) -> dict[str, Any]:
        value = _EpistemicRecordBase.as_dict(self)
        value["reason"] = self.reason
        return value


EpistemicRecord = (
    ObservedEvidence
    | InferredHypothesis
    | RetrievalPrior
    | NegativeResult
    | UnknownEvidence
)


__all__ = [
    "EpistemicRecord",
    "EpistemicRecordError",
    "InferredHypothesis",
    "NegativeResult",
    "ObservedEvidence",
    "RetrievalPrior",
    "UnknownEvidence",
]
