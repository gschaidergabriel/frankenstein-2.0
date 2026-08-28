"""Bounded deterministic ContextView compiler for Frankenstein 2.0 Stage 3.

F2-WP-208 generation 1.

The compiler consumes already-typed F2-WP-207 epistemic records plus explicit caller-
supplied relevance evidence.  It emits references and immutable identity/provenance only;
it never copies or decodes record payloads while selecting context.

Authority invariants::

    CONTEXT_SELECTION != TRUTH
    RELEVANCE_SCORE != SEMANTIC_INFERENCE
    RETRIEVAL_PRIOR != OBSERVATION
    UNKNOWN_EVIDENCE != MISSING_VALUE_TO_FILL
    NEGATIVE_RESULT != PROOF_OF_ALL_ALTERNATIVES_FALSE

No durable-state I/O, provider/model/tool invocation, effect authority or completion
authority exists in this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .epistemic_records import (
    InferredHypothesis,
    NegativeResult,
    ObservedEvidence,
    RetrievalPrior,
    UnknownEvidence,
)

CANDIDATE_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_CONTEXT_CANDIDATE/v1"
REQUEST_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_CONTEXT_REQUEST/v1"
RECORD_REF_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_CONTEXT_RECORD_REF/v1"
VIEW_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_CONTEXT_VIEW/v1"

SELECTED_EXPLICIT_RELEVANCE = "SELECTED_BY_EXPLICIT_RELEVANCE"
NOT_SELECTED_LIMIT = "VALID_CANDIDATE_BELOW_CONTEXT_LIMIT"
NOT_SELECTED_SCHEMA = "RECORD_SCHEMA_NOT_REQUESTED"
VIEW_CLASSIFICATION = "BOUNDED_CONTEXT_REFERENCE_VIEW_NOT_WORLD_TRUTH_OR_AUTHORITY"

MAX_BASIS_POINTS = 10_000
MAX_RECORDS = 1_024
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_KNOWN_RECORD_TYPES = (
    ObservedEvidence,
    InferredHypothesis,
    RetrievalPrior,
    NegativeResult,
    UnknownEvidence,
)
KNOWN_RECORD_SCHEMAS = tuple(sorted(record_type.schema for record_type in _KNOWN_RECORD_TYPES))
_KNOWN_SCHEMA_SET = frozenset(KNOWN_RECORD_SCHEMAS)


class EpistemicContextViewError(ValueError):
    """Fail-closed F2-WP-208 contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise EpistemicContextViewError(f"{name} must be a string")
    if not value or value != value.strip():
        raise EpistemicContextViewError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise EpistemicContextViewError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise EpistemicContextViewError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EpistemicContextViewError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _basis_points(value: Any) -> int:
    if type(value) is not int or value < 0 or value > MAX_BASIS_POINTS:
        raise EpistemicContextViewError("relevance_bp must be an integer in [0, 10000]")
    return value


def _positive_int(name: str, value: Any, *, maximum: int) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        raise EpistemicContextViewError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EpistemicContextViewError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not allow_empty and not refs:
        raise EpistemicContextViewError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise EpistemicContextViewError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _record_type(record: Any):
    if type(record) not in _KNOWN_RECORD_TYPES:
        raise EpistemicContextViewError(
            "record must be a concrete F2-WP-207 epistemic record type"
        )
    return type(record)


@dataclass(frozen=True, slots=True, init=False)
class EpistemicContextCandidate:
    schema: str
    record: Any
    expected_record_sha256: str
    relevance_bp: int
    relevance_evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        record: Any,
        expected_record_sha256: str,
        relevance_bp: int,
        relevance_evidence_refs: Iterable[str],
    ) -> None:
        if schema != CANDIDATE_SCHEMA:
            raise EpistemicContextViewError("candidate schema mismatch")
        _record_type(record)
        expected_record_sha256 = _sha256(
            "expected_record_sha256", expected_record_sha256
        )
        if record.identity_sha256 != expected_record_sha256:
            raise EpistemicContextViewError("record identity digest mismatch")
        relevance_bp = _basis_points(relevance_bp)
        refs = _refs("relevance evidence_ref", relevance_evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "record", record)
        object.__setattr__(self, "expected_record_sha256", expected_record_sha256)
        object.__setattr__(self, "relevance_bp", relevance_bp)
        object.__setattr__(self, "relevance_evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        record: Any,
        expected_record_sha256: str,
        relevance_bp: int,
        relevance_evidence_refs: Iterable[str],
    ) -> "EpistemicContextCandidate":
        return cls(
            schema=CANDIDATE_SCHEMA,
            record=record,
            expected_record_sha256=expected_record_sha256,
            relevance_bp=relevance_bp,
            relevance_evidence_refs=relevance_evidence_refs,
        )


@dataclass(frozen=True, slots=True, init=False)
class EpistemicContextRequest:
    schema: str
    view_id: str
    max_records: int
    allowed_record_schemas: tuple[str, ...]
    policy_evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        view_id: str,
        max_records: int,
        allowed_record_schemas: Iterable[str],
        policy_evidence_refs: Iterable[str],
    ) -> None:
        if schema != REQUEST_SCHEMA:
            raise EpistemicContextViewError("request schema mismatch")
        view_id = _identifier("view_id", view_id)
        max_records = _positive_int("max_records", max_records, maximum=MAX_RECORDS)
        if isinstance(allowed_record_schemas, (str, bytes)):
            raise EpistemicContextViewError(
                "allowed_record_schemas must be an iterable of schemas"
            )
        schemas = tuple(allowed_record_schemas)
        if not schemas:
            raise EpistemicContextViewError("allowed_record_schemas must not be empty")
        if any(schema_name not in _KNOWN_SCHEMA_SET for schema_name in schemas):
            raise EpistemicContextViewError("allowed_record_schemas contains unknown schema")
        if len(set(schemas)) != len(schemas):
            raise EpistemicContextViewError("allowed_record_schemas contains duplicates")
        schemas = tuple(sorted(schemas))
        refs = _refs("policy evidence_ref", policy_evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "view_id", view_id)
        object.__setattr__(self, "max_records", max_records)
        object.__setattr__(self, "allowed_record_schemas", schemas)
        object.__setattr__(self, "policy_evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        view_id: str,
        max_records: int,
        allowed_record_schemas: Iterable[str] = KNOWN_RECORD_SCHEMAS,
        policy_evidence_refs: Iterable[str],
    ) -> "EpistemicContextRequest":
        return cls(
            schema=REQUEST_SCHEMA,
            view_id=view_id,
            max_records=max_records,
            allowed_record_schemas=allowed_record_schemas,
            policy_evidence_refs=policy_evidence_refs,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EpistemicContextRecordRef:
    schema: str
    record_id: str
    generation: int
    record_schema: str
    record_classification: str
    record_identity_sha256: str
    provenance_sha256: str
    causal_refs: tuple[str, ...]
    relevance_bp: int
    relevance_evidence_refs: tuple[str, ...]
    selected: bool
    selection_reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EpistemicContextView:
    schema: str
    view_id: str
    request_sha256: str
    selected: tuple[EpistemicContextRecordRef, ...]
    not_selected: tuple[EpistemicContextRecordRef, ...]
    candidate_count: int
    classification: str = VIEW_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _record_ref(
    candidate: EpistemicContextCandidate,
    *,
    selected: bool,
    reason: str,
) -> EpistemicContextRecordRef:
    record = candidate.record
    record_type = _record_type(record)
    actual_digest = record.identity_sha256
    if actual_digest != candidate.expected_record_sha256:
        raise EpistemicContextViewError("record identity changed after candidate admission")
    return EpistemicContextRecordRef(
        schema=RECORD_REF_SCHEMA,
        record_id=record.record_id,
        generation=record.generation,
        record_schema=record_type.schema,
        record_classification=record_type.classification,
        record_identity_sha256=actual_digest,
        provenance_sha256=record.provenance_sha256,
        causal_refs=tuple(record.causal_refs),
        relevance_bp=candidate.relevance_bp,
        relevance_evidence_refs=candidate.relevance_evidence_refs,
        selected=selected,
        selection_reason=reason,
    )


def compile_epistemic_context_view(
    request: EpistemicContextRequest,
    candidates: Iterable[EpistemicContextCandidate],
) -> EpistemicContextView:
    """Compile one bounded reference-only view from explicit typed candidates."""
    if not isinstance(request, EpistemicContextRequest):
        raise EpistemicContextViewError("request must be an EpistemicContextRequest")
    raw_candidates = tuple(candidates)
    if any(not isinstance(candidate, EpistemicContextCandidate) for candidate in raw_candidates):
        raise EpistemicContextViewError(
            "candidates must contain EpistemicContextCandidate values"
        )

    seen_record_ids: set[str] = set()
    eligible: list[EpistemicContextCandidate] = []
    excluded: list[EpistemicContextCandidate] = []
    allowed = set(request.allowed_record_schemas)

    for candidate in raw_candidates:
        record = candidate.record
        _record_type(record)
        if record.identity_sha256 != candidate.expected_record_sha256:
            raise EpistemicContextViewError("record identity digest mismatch during compile")
        if record.record_id in seen_record_ids:
            raise EpistemicContextViewError(
                f"duplicate record_id in context candidates: {record.record_id!r}"
            )
        seen_record_ids.add(record.record_id)
        if type(record).schema in allowed:
            eligible.append(candidate)
        else:
            excluded.append(candidate)

    eligible.sort(
        key=lambda candidate: (
            -candidate.relevance_bp,
            candidate.record.record_id,
            candidate.record.generation,
            candidate.expected_record_sha256,
        )
    )
    excluded.sort(
        key=lambda candidate: (
            candidate.record.record_id,
            candidate.record.generation,
            candidate.expected_record_sha256,
        )
    )

    selected_candidates = eligible[: request.max_records]
    below_limit = eligible[request.max_records :]

    selected = tuple(
        _record_ref(
            candidate,
            selected=True,
            reason=SELECTED_EXPLICIT_RELEVANCE,
        )
        for candidate in selected_candidates
    )
    not_selected = tuple(
        [
            _record_ref(
                candidate,
                selected=False,
                reason=NOT_SELECTED_LIMIT,
            )
            for candidate in below_limit
        ]
        + [
            _record_ref(
                candidate,
                selected=False,
                reason=NOT_SELECTED_SCHEMA,
            )
            for candidate in excluded
        ]
    )

    return EpistemicContextView(
        schema=VIEW_SCHEMA,
        view_id=request.view_id,
        request_sha256=request.sha256(),
        selected=selected,
        not_selected=not_selected,
        candidate_count=len(raw_candidates),
    )


__all__ = [
    "CANDIDATE_SCHEMA",
    "REQUEST_SCHEMA",
    "RECORD_REF_SCHEMA",
    "VIEW_SCHEMA",
    "KNOWN_RECORD_SCHEMAS",
    "SELECTED_EXPLICIT_RELEVANCE",
    "NOT_SELECTED_LIMIT",
    "NOT_SELECTED_SCHEMA",
    "VIEW_CLASSIFICATION",
    "EpistemicContextCandidate",
    "EpistemicContextRequest",
    "EpistemicContextRecordRef",
    "EpistemicContextView",
    "EpistemicContextViewError",
    "compile_epistemic_context_view",
]
