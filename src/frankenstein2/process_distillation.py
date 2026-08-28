"""Deterministic cognitive-process distillation primitive for Frankenstein 2.0.

F2-WP-304 generation 1.

This module does not inspect payload contents and does not infer facts, semantic
correctness, causality, success, method validity, transfer applicability, authority,
effects, or completion. It freezes only explicit caller-supplied process evidence into
a deterministic candidate descriptor suitable for later Method Memory evaluation.

Recursive composition is bounded and acyclic by construction: a new candidate can only
reference already-materialized immutable parent candidates, stores their exact digests,
and has a strictly greater bounded depth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Sequence

PROCESS_EVIDENCE_SCHEMA = "FRANKENSTEIN2_PROCESS_EVIDENCE/v1"
PROCESS_PATTERN_SCHEMA = "FRANKENSTEIN2_PROCESS_PATTERN_CANDIDATE/v1"

OUTCOME_REPORTED_SUCCESS = "REPORTED_SUCCESS"
OUTCOME_REPORTED_FAILURE = "REPORTED_FAILURE"
OUTCOME_UNKNOWN = "UNKNOWN"

_ALLOWED_OUTCOMES = frozenset(
    {OUTCOME_REPORTED_SUCCESS, OUTCOME_REPORTED_FAILURE, OUTCOME_UNKNOWN}
)
_PATTERN_CLASSIFICATION = (
    "PROCESS_PATTERN_CANDIDATE_NOT_FACT_METHOD_VALIDATION_TRANSFER_OR_AUTHORITY"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_DEPTH = 8
_PATTERN_TOKEN = object()


class ProcessDistillationError(ValueError):
    """Fail-closed process-distillation contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ProcessDistillationError(f"{name} must be a string")
    if not value or value != value.strip():
        raise ProcessDistillationError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise ProcessDistillationError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ProcessDistillationError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ProcessDistillationError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ProcessDistillationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _ordered_refs(name: str, values: Iterable[str], *, required: bool) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ProcessDistillationError(f"{name} must be an iterable of reference strings")
    refs = tuple(_identifier(name, value) for value in values)
    if required and not refs:
        raise ProcessDistillationError(f"{name} must contain at least one explicit reference")
    return refs


def _set_refs(name: str, values: Iterable[str], *, required: bool) -> tuple[str, ...]:
    refs = _ordered_refs(name, values, required=required)
    if len(set(refs)) != len(refs):
        raise ProcessDistillationError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProcessEvidence:
    schema: str
    process_id: str
    generation: int
    step_refs: tuple[str, ...]
    outcome_classification: str
    outcome_refs: tuple[str, ...]
    falsifier_refs: tuple[str, ...]
    failure_signature_refs: tuple[str, ...]
    transfer_condition_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != PROCESS_EVIDENCE_SCHEMA:
            raise ProcessDistillationError("process evidence schema mismatch")
        object.__setattr__(self, "process_id", _identifier("process_id", self.process_id))
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(
            self,
            "step_refs",
            _ordered_refs("step_ref", self.step_refs, required=True),
        )
        if self.outcome_classification not in _ALLOWED_OUTCOMES:
            raise ProcessDistillationError(
                f"unsupported outcome classification: {self.outcome_classification!r}"
            )
        object.__setattr__(
            self,
            "outcome_refs",
            _set_refs("outcome_ref", self.outcome_refs, required=True),
        )
        object.__setattr__(
            self,
            "falsifier_refs",
            _set_refs("falsifier_ref", self.falsifier_refs, required=False),
        )
        object.__setattr__(
            self,
            "failure_signature_refs",
            _set_refs("failure_signature_ref", self.failure_signature_refs, required=False),
        )
        object.__setattr__(
            self,
            "transfer_condition_refs",
            _set_refs("transfer_condition_ref", self.transfer_condition_refs, required=False),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _set_refs("provenance_ref", self.provenance_refs, required=True),
        )

    @classmethod
    def create(
        cls,
        *,
        process_id: str,
        generation: int,
        step_refs: Iterable[str],
        outcome_classification: str,
        outcome_refs: Iterable[str],
        falsifier_refs: Iterable[str] = (),
        failure_signature_refs: Iterable[str] = (),
        transfer_condition_refs: Iterable[str] = (),
        provenance_refs: Iterable[str],
    ) -> "ProcessEvidence":
        return cls(
            schema=PROCESS_EVIDENCE_SCHEMA,
            process_id=process_id,
            generation=generation,
            step_refs=tuple(step_refs),
            outcome_classification=outcome_classification,
            outcome_refs=tuple(outcome_refs),
            falsifier_refs=tuple(falsifier_refs),
            failure_signature_refs=tuple(failure_signature_refs),
            transfer_condition_refs=tuple(transfer_condition_refs),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class ProcessPatternCandidate:
    schema: str
    candidate_id: str
    process_id: str
    generation: int
    process_evidence_sha256: str
    step_refs: tuple[str, ...]
    outcome_classification: str
    outcome_refs: tuple[str, ...]
    falsifier_refs: tuple[str, ...]
    failure_signature_refs: tuple[str, ...]
    transfer_condition_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    parent_candidate_sha256: tuple[str, ...]
    ancestry_sha256: tuple[str, ...]
    depth: int
    classification: str

    def __init__(
        self,
        *,
        schema: str,
        candidate_id: str,
        process_id: str,
        generation: int,
        process_evidence_sha256: str,
        step_refs: Iterable[str],
        outcome_classification: str,
        outcome_refs: Iterable[str],
        falsifier_refs: Iterable[str],
        failure_signature_refs: Iterable[str],
        transfer_condition_refs: Iterable[str],
        provenance_refs: Iterable[str],
        parent_candidate_sha256: Iterable[str],
        ancestry_sha256: Iterable[str],
        depth: int,
        classification: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _PATTERN_TOKEN:
            raise ProcessDistillationError(
                "ProcessPatternCandidate must be created through distill_process"
            )
        if schema != PROCESS_PATTERN_SCHEMA:
            raise ProcessDistillationError("process pattern schema mismatch")
        candidate_id = _identifier("candidate_id", candidate_id)
        process_id = _identifier("process_id", process_id)
        generation = _generation(generation)
        process_evidence_sha256 = _sha256(
            "process_evidence_sha256", process_evidence_sha256
        )
        step_refs = _ordered_refs("step_ref", step_refs, required=True)
        if outcome_classification not in _ALLOWED_OUTCOMES:
            raise ProcessDistillationError("process pattern outcome classification mismatch")
        outcome_refs = _set_refs("outcome_ref", outcome_refs, required=True)
        falsifier_refs = _set_refs("falsifier_ref", falsifier_refs, required=False)
        failure_signature_refs = _set_refs(
            "failure_signature_ref", failure_signature_refs, required=False
        )
        transfer_condition_refs = _set_refs(
            "transfer_condition_ref", transfer_condition_refs, required=False
        )
        provenance_refs = _set_refs("provenance_ref", provenance_refs, required=True)
        parent_candidate_sha256 = tuple(
            _sha256("parent_candidate_sha256", value)
            for value in parent_candidate_sha256
        )
        ancestry_sha256 = tuple(_sha256("ancestry_sha256", value) for value in ancestry_sha256)
        if len(set(parent_candidate_sha256)) != len(parent_candidate_sha256):
            raise ProcessDistillationError("duplicate parent candidate digest")
        if len(set(ancestry_sha256)) != len(ancestry_sha256):
            raise ProcessDistillationError("duplicate ancestry candidate digest")
        if type(depth) is not int or not 0 <= depth <= _MAX_DEPTH:
            raise ProcessDistillationError(f"depth must be in range 0..{_MAX_DEPTH}")
        if depth == 0 and parent_candidate_sha256:
            raise ProcessDistillationError("depth 0 candidate must not have parents")
        if depth > 0 and not parent_candidate_sha256:
            raise ProcessDistillationError("recursive candidate requires a parent")
        if classification != _PATTERN_CLASSIFICATION:
            raise ProcessDistillationError("process pattern classification mismatch")

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "process_id", process_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "process_evidence_sha256", process_evidence_sha256)
        object.__setattr__(self, "step_refs", step_refs)
        object.__setattr__(self, "outcome_classification", outcome_classification)
        object.__setattr__(self, "outcome_refs", outcome_refs)
        object.__setattr__(self, "falsifier_refs", falsifier_refs)
        object.__setattr__(self, "failure_signature_refs", failure_signature_refs)
        object.__setattr__(self, "transfer_condition_refs", transfer_condition_refs)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        object.__setattr__(self, "parent_candidate_sha256", parent_candidate_sha256)
        object.__setattr__(self, "ancestry_sha256", ancestry_sha256)
        object.__setattr__(self, "depth", depth)
        object.__setattr__(self, "classification", classification)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def distill_process(
    evidence: ProcessEvidence,
    *,
    candidate_id: str,
    parents: Sequence[ProcessPatternCandidate] = (),
) -> ProcessPatternCandidate:
    """Freeze explicit process evidence into a deterministic non-authoritative candidate."""
    if not isinstance(evidence, ProcessEvidence):
        raise ProcessDistillationError("evidence must be ProcessEvidence")
    candidate_id = _identifier("candidate_id", candidate_id)
    if isinstance(parents, (str, bytes)):
        raise ProcessDistillationError("parents must contain ProcessPatternCandidate objects")

    parent_list = tuple(parents)
    parent_digests: list[str] = []
    ancestry: set[str] = set()
    max_parent_depth = -1
    for parent in parent_list:
        if not isinstance(parent, ProcessPatternCandidate):
            raise ProcessDistillationError("parents must contain ProcessPatternCandidate objects")
        if parent.process_id != evidence.process_id:
            raise ProcessDistillationError("parent process_id mismatch")
        if parent.generation > evidence.generation:
            raise ProcessDistillationError("parent generation must not exceed evidence generation")
        if parent.candidate_id == candidate_id:
            raise ProcessDistillationError("candidate_id must not self-reference a parent")
        digest = parent.sha256()
        if digest in ancestry or digest in parent_digests:
            raise ProcessDistillationError("duplicate or cyclic parent candidate")
        if digest in parent.ancestry_sha256:
            raise ProcessDistillationError("parent candidate contains a cyclic ancestry chain")
        parent_digests.append(digest)
        ancestry.add(digest)
        ancestry.update(parent.ancestry_sha256)
        max_parent_depth = max(max_parent_depth, parent.depth)

    depth = 0 if not parent_list else max_parent_depth + 1
    if depth > _MAX_DEPTH:
        raise ProcessDistillationError(f"recursive process depth exceeds {_MAX_DEPTH}")

    return ProcessPatternCandidate(
        schema=PROCESS_PATTERN_SCHEMA,
        candidate_id=candidate_id,
        process_id=evidence.process_id,
        generation=evidence.generation,
        process_evidence_sha256=evidence.sha256(),
        step_refs=evidence.step_refs,
        outcome_classification=evidence.outcome_classification,
        outcome_refs=evidence.outcome_refs,
        falsifier_refs=evidence.falsifier_refs,
        failure_signature_refs=evidence.failure_signature_refs,
        transfer_condition_refs=evidence.transfer_condition_refs,
        provenance_refs=evidence.provenance_refs,
        parent_candidate_sha256=tuple(sorted(parent_digests)),
        ancestry_sha256=tuple(sorted(ancestry)),
        depth=depth,
        classification=_PATTERN_CLASSIFICATION,
        _token=_PATTERN_TOKEN,
    )


__all__ = [
    "OUTCOME_REPORTED_FAILURE",
    "OUTCOME_REPORTED_SUCCESS",
    "OUTCOME_UNKNOWN",
    "PROCESS_EVIDENCE_SCHEMA",
    "PROCESS_PATTERN_SCHEMA",
    "ProcessDistillationError",
    "ProcessEvidence",
    "ProcessPatternCandidate",
    "distill_process",
]
