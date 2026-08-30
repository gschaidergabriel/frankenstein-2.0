"""Deterministic resource/latency/quality characterization evidence contract.

F2-WP-902 generation 1 repository-component scope only.

This module does *not* measure a machine and does not attest that caller-supplied
numbers were really observed.  It validates an explicit cohort of measurement records,
keeps their exact source/environment/workload/evidence identity, and computes only
integer nearest-rank summaries.  Runtime, effect, completion and whole-system authority
remain outside this contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar, Iterable, Sequence


OBSERVATION_SCHEMA = "FRANKENSTEIN2_CHARACTERIZATION_OBSERVATION/v1"
SUMMARY_SCHEMA = "FRANKENSTEIN2_CHARACTERIZATION_SUMMARY/v1"
OBSERVATION_CLASSIFICATION = (
    "CALLER_SUPPLIED_MEASUREMENT_RECORD_NOT_RUNTIME_ATTESTATION_OR_WORLD_TRUTH"
)
SUMMARY_CLASSIFICATION = (
    "DETERMINISTIC_MATCHED_COHORT_SUMMARY_NOT_RUNTIME_EFFECT_COMPLETION_OR_WHOLE_SYSTEM_AUTHORITY"
)

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_REFS = 256
_MAX_SAMPLES = 10000
_MAX_INT = (1 << 63) - 1


class CharacterizationError(ValueError):
    """Fail-closed F2-WP-902 characterization-contract error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str:
        raise CharacterizationError(f"{name} must be exact concrete string")
    if not value or value != value.strip():
        raise CharacterizationError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_TEXT:
        raise CharacterizationError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CharacterizationError(f"{name} contains control characters")
    return value


def _git_sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA1_RE.fullmatch(value) is None:
        raise CharacterizationError(f"{name} must be lowercase 40-hex Git SHA")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CharacterizationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0 or value > _MAX_INT:
        raise CharacterizationError(f"{name} must be exact positive signed-63-bit int")
    return value


def _quality_bp(value: Any) -> int:
    if type(value) is not int or value < 0 or value > 10000:
        raise CharacterizationError("quality_bp must be exact int in [0, 10000]")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise CharacterizationError("evidence_refs must be an iterable of strings")
    refs = tuple(_text("evidence_refs item", item) for item in values)
    if not refs:
        raise CharacterizationError("evidence_refs must not be empty")
    if len(refs) > _MAX_REFS:
        raise CharacterizationError(f"evidence_refs exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise CharacterizationError("evidence_refs must not contain duplicates")
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
        raise CharacterizationError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _nearest_rank(values: Sequence[int], numerator: int, denominator: int) -> int:
    """Return an integer nearest-rank quantile, always selecting an observed sample.

    Rank is ceil(n * numerator / denominator), clamped to [1, n].
    No floating point enters the characterization surface.
    """

    if not values:
        raise CharacterizationError("quantile input must not be empty")
    ordered = sorted(values)
    rank = (len(ordered) * numerator + denominator - 1) // denominator
    rank = min(max(rank, 1), len(ordered))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationObservation:
    observation_id: str
    trial_id: str
    source_commit_sha: str
    environment_fingerprint_sha256: str
    workload_id: str
    peak_rss_bytes: int
    latency_ns: int
    quality_bp: int
    evidence_refs: tuple[str, ...]

    schema: ClassVar[str] = OBSERVATION_SCHEMA
    classification: ClassVar[str] = OBSERVATION_CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text("observation_id", self.observation_id))
        object.__setattr__(self, "trial_id", _text("trial_id", self.trial_id))
        object.__setattr__(
            self, "source_commit_sha", _git_sha("source_commit_sha", self.source_commit_sha)
        )
        object.__setattr__(
            self,
            "environment_fingerprint_sha256",
            _sha256("environment_fingerprint_sha256", self.environment_fingerprint_sha256),
        )
        object.__setattr__(self, "workload_id", _text("workload_id", self.workload_id))
        object.__setattr__(self, "peak_rss_bytes", _positive_int("peak_rss_bytes", self.peak_rss_bytes))
        object.__setattr__(self, "latency_ns", _positive_int("latency_ns", self.latency_ns))
        object.__setattr__(self, "quality_bp", _quality_bp(self.quality_bp))
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "observation_id": self.observation_id,
            "trial_id": self.trial_id,
            "source_commit_sha": self.source_commit_sha,
            "environment_fingerprint_sha256": self.environment_fingerprint_sha256,
            "workload_id": self.workload_id,
            "peak_rss_bytes": self.peak_rss_bytes,
            "latency_ns": self.latency_ns,
            "quality_bp": self.quality_bp,
            "evidence_refs": list(self.evidence_refs),
            "runtime_attestation": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "whole_system_credit": 0,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationSummary:
    cohort_id: str
    source_commit_sha: str
    environment_fingerprint_sha256: str
    workload_id: str
    sample_count: int
    observation_bindings: tuple[tuple[str, str, str], ...]
    peak_rss_p50_bytes: int
    peak_rss_p95_bytes: int
    latency_p50_ns: int
    latency_p95_ns: int
    quality_p05_bp: int
    quality_p50_bp: int
    evidence_refs: tuple[str, ...]

    schema: ClassVar[str] = SUMMARY_SCHEMA
    classification: ClassVar[str] = SUMMARY_CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "cohort_id", _text("cohort_id", self.cohort_id))
        object.__setattr__(
            self, "source_commit_sha", _git_sha("source_commit_sha", self.source_commit_sha)
        )
        object.__setattr__(
            self,
            "environment_fingerprint_sha256",
            _sha256("environment_fingerprint_sha256", self.environment_fingerprint_sha256),
        )
        object.__setattr__(self, "workload_id", _text("workload_id", self.workload_id))
        if type(self.sample_count) is not int or self.sample_count < 3 or self.sample_count > _MAX_SAMPLES:
            raise CharacterizationError("sample_count must be exact int in [3, 10000]")
        if len(self.observation_bindings) != self.sample_count:
            raise CharacterizationError("observation_bindings length must equal sample_count")
        if tuple(sorted(self.observation_bindings)) != self.observation_bindings:
            raise CharacterizationError("observation_bindings must be canonically sorted")
        for binding in self.observation_bindings:
            if type(binding) is not tuple or len(binding) != 3:
                raise CharacterizationError("each observation binding must be a 3-tuple")
            _text("binding observation_id", binding[0])
            _text("binding trial_id", binding[1])
            _sha256("binding observation_sha256", binding[2])
        for field_name in (
            "peak_rss_p50_bytes",
            "peak_rss_p95_bytes",
            "latency_p50_ns",
            "latency_p95_ns",
        ):
            _positive_int(field_name, getattr(self, field_name))
        _quality_bp(self.quality_p05_bp)
        _quality_bp(self.quality_p50_bp)
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "cohort_id": self.cohort_id,
            "source_commit_sha": self.source_commit_sha,
            "environment_fingerprint_sha256": self.environment_fingerprint_sha256,
            "workload_id": self.workload_id,
            "sample_count": self.sample_count,
            "observation_bindings": [
                {
                    "observation_id": observation_id,
                    "trial_id": trial_id,
                    "observation_sha256": observation_sha256,
                }
                for observation_id, trial_id, observation_sha256 in self.observation_bindings
            ],
            "statistics": {
                "method": "INTEGER_NEAREST_RANK",
                "peak_rss_p50_bytes": self.peak_rss_p50_bytes,
                "peak_rss_p95_bytes": self.peak_rss_p95_bytes,
                "latency_p50_ns": self.latency_p50_ns,
                "latency_p95_ns": self.latency_p95_ns,
                "quality_p05_bp": self.quality_p05_bp,
                "quality_p50_bp": self.quality_p50_bp,
            },
            "evidence_refs": list(self.evidence_refs),
            "runtime_attestation": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "training_credit": 0,
            "whole_system_credit": 0,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def summarize_characterization(
    observations: Sequence[CharacterizationObservation],
    *,
    cohort_id: str,
) -> CharacterizationSummary:
    """Validate one matched cohort and return a deterministic non-attesting summary."""

    cohort_id = _text("cohort_id", cohort_id)
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise CharacterizationError("observations must be a concrete sequence")
    if len(observations) < 3 or len(observations) > _MAX_SAMPLES:
        raise CharacterizationError("observations length must be in [3, 10000]")
    if any(type(item) is not CharacterizationObservation for item in observations):
        raise CharacterizationError("all observations must be concrete CharacterizationObservation")

    first = observations[0]
    observation_ids: set[str] = set()
    trial_ids: set[str] = set()
    bindings: list[tuple[str, str, str]] = []
    peak_rss: list[int] = []
    latency: list[int] = []
    quality: list[int] = []
    evidence: set[str] = set()

    for item in observations:
        if item.source_commit_sha != first.source_commit_sha:
            raise CharacterizationError("mixed source_commit_sha cohort")
        if item.environment_fingerprint_sha256 != first.environment_fingerprint_sha256:
            raise CharacterizationError("mixed environment_fingerprint_sha256 cohort")
        if item.workload_id != first.workload_id:
            raise CharacterizationError("mixed workload_id cohort")
        if item.observation_id in observation_ids:
            raise CharacterizationError("duplicate observation_id")
        if item.trial_id in trial_ids:
            raise CharacterizationError("duplicate trial_id")
        observation_ids.add(item.observation_id)
        trial_ids.add(item.trial_id)
        bindings.append((item.observation_id, item.trial_id, item.sha256()))
        peak_rss.append(item.peak_rss_bytes)
        latency.append(item.latency_ns)
        quality.append(item.quality_bp)
        evidence.update(item.evidence_refs)

    return CharacterizationSummary(
        cohort_id=cohort_id,
        source_commit_sha=first.source_commit_sha,
        environment_fingerprint_sha256=first.environment_fingerprint_sha256,
        workload_id=first.workload_id,
        sample_count=len(observations),
        observation_bindings=tuple(sorted(bindings)),
        peak_rss_p50_bytes=_nearest_rank(peak_rss, 50, 100),
        peak_rss_p95_bytes=_nearest_rank(peak_rss, 95, 100),
        latency_p50_ns=_nearest_rank(latency, 50, 100),
        latency_p95_ns=_nearest_rank(latency, 95, 100),
        quality_p05_bp=_nearest_rank(quality, 5, 100),
        quality_p50_bp=_nearest_rank(quality, 50, 100),
        evidence_refs=tuple(sorted(evidence)),
    )
