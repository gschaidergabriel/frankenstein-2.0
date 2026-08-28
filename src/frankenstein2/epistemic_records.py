"""Immutable identity-bound epistemic records for Frankenstein 2.0.

F2-WP-207 generation 1.

This module only types explicit caller-supplied epistemic records. It never reads the
referenced payload, infers facts, changes canonical state, ranks retrieval, invokes a
model/provider/tool, authorizes effects, or mints completion.

Important authority boundary::

    EPISTEMIC_RECORD != CANONICAL_WORLD_TRUTH
    RETRIEVAL_PRIOR != OBSERVATION
    INFERRED_HYPOTHESIS != OBSERVED_EVIDENCE
    UNKNOWN != FALSE

Each record binds its classification, opaque payload identity, provenance/support refs,
lineage and fixed non-authority scope into a deterministic SHA-256 identity. Admission
re-validates the complete structure and identity digest so post-construction relabeling
or provenance mutation fails closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

EPISTEMIC_RECORD_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_RECORD/v1"

OBSERVED_EVIDENCE = "OBSERVED_EVIDENCE"
INFERRED_HYPOTHESIS = "INFERRED_HYPOTHESIS"
RETRIEVAL_PRIOR = "RETRIEVAL_PRIOR"
NEGATIVE_RESULT = "NEGATIVE_RESULT"
UNKNOWN = "UNKNOWN"

ALLOWED_CLASSIFICATIONS = (
    OBSERVED_EVIDENCE,
    INFERRED_HYPOTHESIS,
    RETRIEVAL_PRIOR,
    NEGATIVE_RESULT,
    UNKNOWN,
)
_ALLOWED_CLASSIFICATION_SET = frozenset(ALLOWED_CLASSIFICATIONS)

AUTHORITY_SCOPE = (
    "EPISTEMIC_RECORD_CANDIDATE_ONLY_NOT_CANONICAL_TRUTH_RETRIEVAL_EFFECT_OR_COMPLETION_AUTHORITY"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_RECORD_TOKEN = object()


class EpistemicRecordError(ValueError):
    """Fail-closed epistemic record contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise EpistemicRecordError(f"{name} must be a string")
    if not value or value != value.strip():
        raise EpistemicRecordError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise EpistemicRecordError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EpistemicRecordError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise EpistemicRecordError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EpistemicRecordError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(
    name: str,
    values: Iterable[str],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EpistemicRecordError(f"{name} must be an iterable of reference strings")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs and not allow_empty:
        raise EpistemicRecordError(f"{name} must contain at least one explicit reference")
    if len(set(refs)) != len(refs):
        raise EpistemicRecordError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identity_payload(
    *,
    schema: str,
    record_id: str,
    subject_ref: str,
    generation: int,
    payload_ref: str,
    payload_sha256: str,
    provenance_refs: tuple[str, ...],
    support_refs: tuple[str, ...],
    counterevidence_refs: tuple[str, ...],
    classification: str,
    parent_record_sha256: str | None,
    authority_scope: str,
) -> dict[str, Any]:
    return {
        "schema": schema,
        "record_id": record_id,
        "subject_ref": subject_ref,
        "generation": generation,
        "payload_ref": payload_ref,
        "payload_sha256": payload_sha256,
        "provenance_refs": provenance_refs,
        "support_refs": support_refs,
        "counterevidence_refs": counterevidence_refs,
        "classification": classification,
        "parent_record_sha256": parent_record_sha256,
        "authority_scope": authority_scope,
    }


def _normalize_fields(
    *,
    schema: str,
    record_id: str,
    subject_ref: str,
    generation: int,
    payload_ref: str,
    payload_sha256: str,
    provenance_refs: Iterable[str],
    support_refs: Iterable[str],
    counterevidence_refs: Iterable[str],
    classification: str,
    parent_record_sha256: str | None,
    authority_scope: str,
) -> dict[str, Any]:
    if schema != EPISTEMIC_RECORD_SCHEMA:
        raise EpistemicRecordError("epistemic record schema mismatch")
    record_id = _identifier("record_id", record_id)
    subject_ref = _identifier("subject_ref", subject_ref)
    generation = _generation(generation)
    payload_ref = _identifier("payload_ref", payload_ref)
    payload_sha256 = _sha256("payload_sha256", payload_sha256)
    provenance_refs = _refs("provenance_ref", provenance_refs)
    support_refs = _refs("support_ref", support_refs)
    counterevidence_refs = _refs(
        "counterevidence_ref", counterevidence_refs, allow_empty=True
    )
    if classification not in _ALLOWED_CLASSIFICATION_SET:
        raise EpistemicRecordError(
            f"unsupported epistemic classification: {classification!r}"
        )
    overlap = set(support_refs).intersection(counterevidence_refs)
    if overlap:
        raise EpistemicRecordError(
            "support_refs and counterevidence_refs must be disjoint"
        )
    if parent_record_sha256 is not None:
        parent_record_sha256 = _sha256(
            "parent_record_sha256", parent_record_sha256
        )
    if generation == 0 and parent_record_sha256 is not None:
        raise EpistemicRecordError(
            "generation 0 must not carry parent_record_sha256"
        )
    if generation > 0 and parent_record_sha256 is None:
        raise EpistemicRecordError(
            "nonzero generation requires parent_record_sha256"
        )
    if authority_scope != AUTHORITY_SCOPE:
        raise EpistemicRecordError("epistemic record authority scope mismatch")

    return _identity_payload(
        schema=schema,
        record_id=record_id,
        subject_ref=subject_ref,
        generation=generation,
        payload_ref=payload_ref,
        payload_sha256=payload_sha256,
        provenance_refs=provenance_refs,
        support_refs=support_refs,
        counterevidence_refs=counterevidence_refs,
        classification=classification,
        parent_record_sha256=parent_record_sha256,
        authority_scope=authority_scope,
    )


@dataclass(frozen=True, slots=True, init=False)
class EpistemicRecord:
    schema: str
    record_id: str
    subject_ref: str
    generation: int
    payload_ref: str
    payload_sha256: str
    provenance_refs: tuple[str, ...]
    support_refs: tuple[str, ...]
    counterevidence_refs: tuple[str, ...]
    classification: str
    parent_record_sha256: str | None
    authority_scope: str
    identity_sha256: str

    def __init__(
        self,
        *,
        schema: str,
        record_id: str,
        subject_ref: str,
        generation: int,
        payload_ref: str,
        payload_sha256: str,
        provenance_refs: Iterable[str],
        support_refs: Iterable[str],
        counterevidence_refs: Iterable[str],
        classification: str,
        parent_record_sha256: str | None,
        authority_scope: str,
        identity_sha256: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _RECORD_TOKEN:
            raise EpistemicRecordError(
                "EpistemicRecord must be created through create_epistemic_record"
            )
        normalized = _normalize_fields(
            schema=schema,
            record_id=record_id,
            subject_ref=subject_ref,
            generation=generation,
            payload_ref=payload_ref,
            payload_sha256=payload_sha256,
            provenance_refs=provenance_refs,
            support_refs=support_refs,
            counterevidence_refs=counterevidence_refs,
            classification=classification,
            parent_record_sha256=parent_record_sha256,
            authority_scope=authority_scope,
        )
        identity_sha256 = _sha256("identity_sha256", identity_sha256)
        expected = _digest(normalized)
        if identity_sha256 != expected:
            raise EpistemicRecordError("epistemic record identity digest mismatch")

        for field_name, value in normalized.items():
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "identity_sha256", identity_sha256)

    def as_dict(self) -> dict[str, Any]:
        validate_epistemic_record(self)
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        validate_epistemic_record(self)
        return self.identity_sha256


def create_epistemic_record(
    *,
    record_id: str,
    subject_ref: str,
    generation: int,
    payload_ref: str,
    payload_sha256: str,
    provenance_refs: Iterable[str],
    support_refs: Iterable[str],
    classification: str,
    counterevidence_refs: Iterable[str] = (),
    parent_record_sha256: str | None = None,
) -> EpistemicRecord:
    """Create one immutable epistemic record from explicit caller data only."""
    normalized = _normalize_fields(
        schema=EPISTEMIC_RECORD_SCHEMA,
        record_id=record_id,
        subject_ref=subject_ref,
        generation=generation,
        payload_ref=payload_ref,
        payload_sha256=payload_sha256,
        provenance_refs=provenance_refs,
        support_refs=support_refs,
        counterevidence_refs=counterevidence_refs,
        classification=classification,
        parent_record_sha256=parent_record_sha256,
        authority_scope=AUTHORITY_SCOPE,
    )
    return EpistemicRecord(
        **normalized,
        identity_sha256=_digest(normalized),
        _token=_RECORD_TOKEN,
    )


def validate_epistemic_record(record: EpistemicRecord) -> EpistemicRecord:
    """Re-admit a record and fail closed on structural or identity mutation."""
    if not isinstance(record, EpistemicRecord):
        raise EpistemicRecordError("record must be an EpistemicRecord")
    normalized = _normalize_fields(
        schema=record.schema,
        record_id=record.record_id,
        subject_ref=record.subject_ref,
        generation=record.generation,
        payload_ref=record.payload_ref,
        payload_sha256=record.payload_sha256,
        provenance_refs=record.provenance_refs,
        support_refs=record.support_refs,
        counterevidence_refs=record.counterevidence_refs,
        classification=record.classification,
        parent_record_sha256=record.parent_record_sha256,
        authority_scope=record.authority_scope,
    )
    identity_sha256 = _sha256("identity_sha256", record.identity_sha256)
    expected = _digest(normalized)
    if identity_sha256 != expected:
        raise EpistemicRecordError("epistemic record identity digest mismatch")
    return record


__all__ = [
    "ALLOWED_CLASSIFICATIONS",
    "AUTHORITY_SCOPE",
    "EPISTEMIC_RECORD_SCHEMA",
    "INFERRED_HYPOTHESIS",
    "NEGATIVE_RESULT",
    "OBSERVED_EVIDENCE",
    "RETRIEVAL_PRIOR",
    "UNKNOWN",
    "EpistemicRecord",
    "EpistemicRecordError",
    "create_epistemic_record",
    "validate_epistemic_record",
]
