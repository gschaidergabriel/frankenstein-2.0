"""Fail-closed measurement admission and deterministic summary ABI for F2-WP-902.

Repository-component scope only. This module does not perform target-host benchmarking,
call models/providers/tools, execute effects, or mint runtime/whole-system acceptance.
It admits already-measured samples only when exact source, whole-loop seal, environment,
metric-schema and provenance identities agree, then produces an order-independent summary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

SAMPLE_SCHEMA = "FRANKENSTEIN2_WHOLE_SYSTEM_CHARACTERIZATION_SAMPLE/v1"
REPORT_SCHEMA = "FRANKENSTEIN2_WHOLE_SYSTEM_CHARACTERIZATION_REPORT/v1"
DEFAULT_METRIC_SCHEMA = "FRANKENSTEIN2_WHOLE_SYSTEM_CHARACTERIZATION_METRICS/v1"
SAMPLE_CLASSIFICATION = "MEASURED_SAMPLE_CANDIDATE_NOT_RUNTIME_OR_WHOLE_SYSTEM_AUTHORITY"
REPORT_CLASSIFICATION = "DETERMINISTIC_CHARACTERIZATION_SUMMARY_NOT_RUNTIME_OR_WHOLE_SYSTEM_AUTHORITY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_REFS = 4096
_MAX_INT = (1 << 63) - 1
_QUALITY_MAX = 1_000_000


class WholeSystemCharacterizationError(ValueError):
    """Reject malformed, stale, mixed-lineage or authority-inflating characterization data."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise WholeSystemCharacterizationError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_TEXT or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise WholeSystemCharacterizationError(f"{name} is outside the text domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WholeSystemCharacterizationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _bounded_int(name: str, value: Any, *, minimum: int = 0, maximum: int = _MAX_INT) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise WholeSystemCharacterizationError(
            f"{name} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WholeSystemCharacterizationError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise WholeSystemCharacterizationError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS or len(set(refs)) != len(refs):
        raise WholeSystemCharacterizationError("provenance_refs exceed bounds or contain duplicates")
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
        raise WholeSystemCharacterizationError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _nearest_rank(values: tuple[int, ...], percentile: int) -> int:
    if not values:
        raise WholeSystemCharacterizationError("cannot summarize an empty measurement family")
    if type(percentile) is not int or not 1 <= percentile <= 100:
        raise WholeSystemCharacterizationError("percentile must be an integer in [1, 100]")
    ordered = tuple(sorted(values))
    rank = (len(ordered) * percentile + 99) // 100
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationSample:
    sample_id: str
    source_bundle_sha256: str
    whole_loop_seal_sha256: str
    environment_fingerprint_sha256: str
    metric_schema_id: str
    latency_ns: int
    peak_rss_bytes: int
    quality_micros: int
    provenance_refs: tuple[str, ...]
    schema: str = SAMPLE_SCHEMA
    classification: str = SAMPLE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != SAMPLE_SCHEMA or self.classification != SAMPLE_CLASSIFICATION:
            raise WholeSystemCharacterizationError("sample schema/classification mismatch")
        object.__setattr__(self, "sample_id", _text("sample_id", self.sample_id))
        object.__setattr__(self, "source_bundle_sha256", _sha("source_bundle_sha256", self.source_bundle_sha256))
        object.__setattr__(self, "whole_loop_seal_sha256", _sha("whole_loop_seal_sha256", self.whole_loop_seal_sha256))
        object.__setattr__(self, "environment_fingerprint_sha256", _sha("environment_fingerprint_sha256", self.environment_fingerprint_sha256))
        object.__setattr__(self, "metric_schema_id", _text("metric_schema_id", self.metric_schema_id))
        object.__setattr__(self, "latency_ns", _bounded_int("latency_ns", self.latency_ns))
        object.__setattr__(self, "peak_rss_bytes", _bounded_int("peak_rss_bytes", self.peak_rss_bytes))
        object.__setattr__(self, "quality_micros", _bounded_int("quality_micros", self.quality_micros, maximum=_QUALITY_MAX))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationReport:
    source_bundle_sha256: str
    whole_loop_seal_sha256: str
    environment_fingerprint_sha256: str
    metric_schema_id: str
    sample_count: int
    sample_set_sha256: str
    latency_ns_min: int
    latency_ns_p50: int
    latency_ns_p95: int
    latency_ns_max: int
    peak_rss_bytes_min: int
    peak_rss_bytes_p50: int
    peak_rss_bytes_p95: int
    peak_rss_bytes_max: int
    quality_micros_min: int
    quality_micros_p50: int
    quality_micros_p95: int
    quality_micros_max: int
    schema: str = REPORT_SCHEMA
    classification: str = REPORT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != REPORT_SCHEMA or self.classification != REPORT_CLASSIFICATION:
            raise WholeSystemCharacterizationError("report schema/classification mismatch")
        _sha("source_bundle_sha256", self.source_bundle_sha256)
        _sha("whole_loop_seal_sha256", self.whole_loop_seal_sha256)
        _sha("environment_fingerprint_sha256", self.environment_fingerprint_sha256)
        _text("metric_schema_id", self.metric_schema_id)
        _bounded_int("sample_count", self.sample_count, minimum=1)
        _sha("sample_set_sha256", self.sample_set_sha256)
        for name in (
            "latency_ns_min", "latency_ns_p50", "latency_ns_p95", "latency_ns_max",
            "peak_rss_bytes_min", "peak_rss_bytes_p50", "peak_rss_bytes_p95", "peak_rss_bytes_max",
        ):
            _bounded_int(name, getattr(self, name))
        for name in ("quality_micros_min", "quality_micros_p50", "quality_micros_p95", "quality_micros_max"):
            _bounded_int(name, getattr(self, name), maximum=_QUALITY_MAX)
        if not self.latency_ns_min <= self.latency_ns_p50 <= self.latency_ns_p95 <= self.latency_ns_max:
            raise WholeSystemCharacterizationError("latency summary is not monotonic")
        if not self.peak_rss_bytes_min <= self.peak_rss_bytes_p50 <= self.peak_rss_bytes_p95 <= self.peak_rss_bytes_max:
            raise WholeSystemCharacterizationError("memory summary is not monotonic")
        if not self.quality_micros_min <= self.quality_micros_p50 <= self.quality_micros_p95 <= self.quality_micros_max:
            raise WholeSystemCharacterizationError("quality summary is not monotonic")

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
                "runtime_authority": "NONE",
                "truth_authority": "NONE",
                "effect_authority": "NONE",
                "completion_authority": "NONE",
                "whole_system_acceptance": False,
            }
        )
        return data

    def sha256(self) -> str:
        return _digest(self.as_dict())


def characterize_measurements(
    samples: Iterable[CharacterizationSample],
    *,
    expected_source_bundle_sha256: str,
    expected_whole_loop_seal_sha256: str,
    expected_environment_fingerprint_sha256: str,
    expected_metric_schema_id: str = DEFAULT_METRIC_SCHEMA,
) -> CharacterizationReport:
    """Admit one homogeneous measurement family and summarize it deterministically."""
    expected_source_bundle_sha256 = _sha("expected_source_bundle_sha256", expected_source_bundle_sha256)
    expected_whole_loop_seal_sha256 = _sha("expected_whole_loop_seal_sha256", expected_whole_loop_seal_sha256)
    expected_environment_fingerprint_sha256 = _sha(
        "expected_environment_fingerprint_sha256", expected_environment_fingerprint_sha256
    )
    expected_metric_schema_id = _text("expected_metric_schema_id", expected_metric_schema_id)
    if isinstance(samples, (str, bytes)):
        raise WholeSystemCharacterizationError("samples must be an iterable of CharacterizationSample")
    family = tuple(samples)
    if not family:
        raise WholeSystemCharacterizationError("measurement family must not be empty")
    if any(type(sample) is not CharacterizationSample for sample in family):
        raise WholeSystemCharacterizationError("measurement family must contain exact CharacterizationSample values")
    ids = tuple(sample.sample_id for sample in family)
    if len(set(ids)) != len(ids):
        raise WholeSystemCharacterizationError("duplicate sample_id in measurement family")

    expected = (
        expected_source_bundle_sha256,
        expected_whole_loop_seal_sha256,
        expected_environment_fingerprint_sha256,
        expected_metric_schema_id,
    )
    for sample in family:
        actual = (
            sample.source_bundle_sha256,
            sample.whole_loop_seal_sha256,
            sample.environment_fingerprint_sha256,
            sample.metric_schema_id,
        )
        if actual != expected:
            raise WholeSystemCharacterizationError(
                "measurement sample source/loop/environment/metric-schema identity mismatch"
            )

    canonical_samples = tuple(sorted(family, key=lambda sample: sample.sample_id))
    sample_set_sha256 = _digest(
        [{"sample_id": sample.sample_id, "sample_sha256": sample.sha256()} for sample in canonical_samples]
    )
    latency = tuple(sample.latency_ns for sample in canonical_samples)
    memory = tuple(sample.peak_rss_bytes for sample in canonical_samples)
    quality = tuple(sample.quality_micros for sample in canonical_samples)
    return CharacterizationReport(
        source_bundle_sha256=expected_source_bundle_sha256,
        whole_loop_seal_sha256=expected_whole_loop_seal_sha256,
        environment_fingerprint_sha256=expected_environment_fingerprint_sha256,
        metric_schema_id=expected_metric_schema_id,
        sample_count=len(canonical_samples),
        sample_set_sha256=sample_set_sha256,
        latency_ns_min=min(latency),
        latency_ns_p50=_nearest_rank(latency, 50),
        latency_ns_p95=_nearest_rank(latency, 95),
        latency_ns_max=max(latency),
        peak_rss_bytes_min=min(memory),
        peak_rss_bytes_p50=_nearest_rank(memory, 50),
        peak_rss_bytes_p95=_nearest_rank(memory, 95),
        peak_rss_bytes_max=max(memory),
        quality_micros_min=min(quality),
        quality_micros_p50=_nearest_rank(quality, 50),
        quality_micros_p95=_nearest_rank(quality, 95),
        quality_micros_max=max(quality),
    )
