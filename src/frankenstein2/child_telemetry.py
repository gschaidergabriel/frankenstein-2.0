"""F2-WP-605 deterministic Native Child telemetry evidence.

This component records explicit performance/resource measurements and opaque quality-
evidence references for one exact F2-WP-602 ChildReconcileEvidence.  It does not infer
semantic quality, success, completion, causal credit, capability authority or world facts.
It is persistence-agnostic and has no child-spawn, provider, tool, effect or UnifiedDB
side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .child_handoff_reconcile import ChildReconcileEvidence, verify_child_reconcile

TELEMETRY_SCHEMA = "FRANKENSTEIN2_CHILD_TELEMETRY/v1"
TELEMETRY_CLASSIFICATION = "MEASUREMENT_EVIDENCE_ONLY_NOT_SUCCESS_COMPLETION_OR_CAUSAL_CREDIT"
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ChildTelemetryError(ValueError):
    """Raised when WP605 telemetry is incomplete, contradictory or noncanonical."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise ChildTelemetryError(f"{name} must be a string")
    if not value or value != value.strip():
        raise ChildTelemetryError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise ChildTelemetryError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ChildTelemetryError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ChildTelemetryError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nonnegative_json_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ChildTelemetryError(f"{name} must be a non-negative integer")
    try:
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ChildTelemetryError(f"{name} is outside the canonical JSON integer domain") from exc
    return value


def _canonical_refs(name: str, value: Any, *, require_nonempty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ChildTelemetryError(f"{name} must be an immutable tuple")
    for item in value:
        _identifier(f"{name} item", item)
    if len(set(value)) != len(value):
        raise ChildTelemetryError(f"{name} must not contain duplicates")
    if value != tuple(sorted(value)):
        raise ChildTelemetryError(f"{name} must be in canonical lexical order")
    if require_nonempty and not value:
        raise ChildTelemetryError(f"{name} must not be empty")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identity_payload(
    *,
    reconcile_id: str,
    reconcile_sha256: str,
    started_monotonic_ns: int,
    finished_monotonic_ns: int,
    cpu_time_ns: int,
    peak_rss_bytes: int,
    input_tokens: int,
    output_tokens: int,
    tool_calls: int,
    work_units: int,
    quality_evidence_refs: tuple[str, ...],
    provenance_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "reconcile_id": reconcile_id,
        "reconcile_sha256": reconcile_sha256,
        "started_monotonic_ns": started_monotonic_ns,
        "finished_monotonic_ns": finished_monotonic_ns,
        "cpu_time_ns": cpu_time_ns,
        "peak_rss_bytes": peak_rss_bytes,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "work_units": work_units,
        "quality_evidence_refs": list(quality_evidence_refs),
        "provenance_refs": list(provenance_refs),
    }


def _telemetry_id(**fields: Any) -> str:
    return "child-telemetry:" + _digest(_identity_payload(**fields))


@dataclass(frozen=True, slots=True)
class ChildTelemetrySample:
    """Immutable measurement evidence bound to one exact child reconciliation.

    All counters are explicit measurements supplied by the caller.  ``quality_evidence_refs``
    are opaque references only; this component does not inspect or score their contents.
    """

    schema: str
    telemetry_id: str
    reconcile: ChildReconcileEvidence
    reconcile_sha256: str
    started_monotonic_ns: int
    finished_monotonic_ns: int
    cpu_time_ns: int
    peak_rss_bytes: int
    input_tokens: int
    output_tokens: int
    tool_calls: int
    work_units: int
    quality_evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str = TELEMETRY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != TELEMETRY_SCHEMA:
            raise ChildTelemetryError("telemetry schema mismatch")
        if self.classification != TELEMETRY_CLASSIFICATION:
            raise ChildTelemetryError("telemetry classification mismatch")
        _identifier("telemetry_id", self.telemetry_id)

        if type(self.reconcile) is not ChildReconcileEvidence:
            raise ChildTelemetryError("reconcile must be exact concrete ChildReconcileEvidence")
        _sha256("reconcile_sha256", self.reconcile_sha256)
        try:
            verify_child_reconcile(
                self.reconcile,
                expected_reconcile_id=self.reconcile.reconcile_id,
                expected_reconcile_sha256=self.reconcile_sha256,
            )
        except ValueError as exc:
            raise ChildTelemetryError(f"invalid reconcile evidence: {exc}") from exc

        start = _nonnegative_json_int("started_monotonic_ns", self.started_monotonic_ns)
        finish = _nonnegative_json_int("finished_monotonic_ns", self.finished_monotonic_ns)
        if finish < start:
            raise ChildTelemetryError("finished_monotonic_ns must be >= started_monotonic_ns")
        _nonnegative_json_int("cpu_time_ns", self.cpu_time_ns)
        _nonnegative_json_int("peak_rss_bytes", self.peak_rss_bytes)
        _nonnegative_json_int("input_tokens", self.input_tokens)
        _nonnegative_json_int("output_tokens", self.output_tokens)
        _nonnegative_json_int("tool_calls", self.tool_calls)
        _nonnegative_json_int("work_units", self.work_units)
        _canonical_refs("quality_evidence_refs", self.quality_evidence_refs)
        _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)

        expected_id = _telemetry_id(
            reconcile_id=self.reconcile.reconcile_id,
            reconcile_sha256=self.reconcile_sha256,
            started_monotonic_ns=self.started_monotonic_ns,
            finished_monotonic_ns=self.finished_monotonic_ns,
            cpu_time_ns=self.cpu_time_ns,
            peak_rss_bytes=self.peak_rss_bytes,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_calls=self.tool_calls,
            work_units=self.work_units,
            quality_evidence_refs=self.quality_evidence_refs,
            provenance_refs=self.provenance_refs,
        )
        if self.telemetry_id != expected_id:
            raise ChildTelemetryError("telemetry_id does not bind exact telemetry content")

    @classmethod
    def create(
        cls,
        *,
        reconcile: ChildReconcileEvidence,
        started_monotonic_ns: int,
        finished_monotonic_ns: int,
        cpu_time_ns: int = 0,
        peak_rss_bytes: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        tool_calls: int = 0,
        work_units: int = 0,
        quality_evidence_refs: tuple[str, ...] = (),
        provenance_refs: tuple[str, ...],
    ) -> "ChildTelemetrySample":
        if type(reconcile) is not ChildReconcileEvidence:
            raise ChildTelemetryError("reconcile must be exact concrete ChildReconcileEvidence")
        reconcile_sha = reconcile.sha256()
        # Constructor performs all validation before returning the candidate.
        fields = dict(
            reconcile_id=reconcile.reconcile_id,
            reconcile_sha256=reconcile_sha,
            started_monotonic_ns=started_monotonic_ns,
            finished_monotonic_ns=finished_monotonic_ns,
            cpu_time_ns=cpu_time_ns,
            peak_rss_bytes=peak_rss_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls,
            work_units=work_units,
            quality_evidence_refs=quality_evidence_refs,
            provenance_refs=provenance_refs,
        )
        return cls(
            schema=TELEMETRY_SCHEMA,
            telemetry_id=_telemetry_id(**fields),
            reconcile=reconcile,
            reconcile_sha256=reconcile_sha,
            started_monotonic_ns=started_monotonic_ns,
            finished_monotonic_ns=finished_monotonic_ns,
            cpu_time_ns=cpu_time_ns,
            peak_rss_bytes=peak_rss_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls,
            work_units=work_units,
            quality_evidence_refs=quality_evidence_refs,
            provenance_refs=provenance_refs,
            classification=TELEMETRY_CLASSIFICATION,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildTelemetrySample":
        if not isinstance(value, Mapping):
            raise ChildTelemetryError("telemetry input must be a mapping")
        expected = {
            "schema", "telemetry_id", "reconcile", "reconcile_sha256",
            "started_monotonic_ns", "finished_monotonic_ns", "cpu_time_ns",
            "peak_rss_bytes", "input_tokens", "output_tokens", "tool_calls",
            "work_units", "quality_evidence_refs", "provenance_refs", "classification",
        }
        if set(value.keys()) != expected:
            raise ChildTelemetryError("telemetry fields are not exact")
        try:
            reconcile = ChildReconcileEvidence.from_mapping(value["reconcile"])
        except (TypeError, ValueError) as exc:
            raise ChildTelemetryError(f"invalid nested reconcile evidence: {exc}") from exc
        quality_refs = tuple(value["quality_evidence_refs"]) if type(value["quality_evidence_refs"]) is list else value["quality_evidence_refs"]
        provenance_refs = tuple(value["provenance_refs"]) if type(value["provenance_refs"]) is list else value["provenance_refs"]
        return cls(
            schema=value["schema"],
            telemetry_id=value["telemetry_id"],
            reconcile=reconcile,
            reconcile_sha256=value["reconcile_sha256"],
            started_monotonic_ns=value["started_monotonic_ns"],
            finished_monotonic_ns=value["finished_monotonic_ns"],
            cpu_time_ns=value["cpu_time_ns"],
            peak_rss_bytes=value["peak_rss_bytes"],
            input_tokens=value["input_tokens"],
            output_tokens=value["output_tokens"],
            tool_calls=value["tool_calls"],
            work_units=value["work_units"],
            quality_evidence_refs=quality_refs,
            provenance_refs=provenance_refs,
            classification=value["classification"],
        )

    @property
    def duration_ns(self) -> int:
        return self.finished_monotonic_ns - self.started_monotonic_ns

    @property
    def result_id(self) -> str:
        return self.reconcile.result_id

    @property
    def result_sha256(self) -> str:
        return self.reconcile.result_sha256

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "telemetry_id": self.telemetry_id,
            "reconcile": self.reconcile.as_dict(),
            "reconcile_sha256": self.reconcile_sha256,
            "started_monotonic_ns": self.started_monotonic_ns,
            "finished_monotonic_ns": self.finished_monotonic_ns,
            "cpu_time_ns": self.cpu_time_ns,
            "peak_rss_bytes": self.peak_rss_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "tool_calls": self.tool_calls,
            "work_units": self.work_units,
            "quality_evidence_refs": list(self.quality_evidence_refs),
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def verify_child_telemetry(
    sample: ChildTelemetrySample,
    *,
    expected_telemetry_id: str,
    expected_telemetry_sha256: str,
    expected_reconcile_id: str,
    expected_reconcile_sha256: str,
) -> ChildTelemetrySample:
    """Revalidate one exact telemetry sample at a consumer boundary."""
    if type(sample) is not ChildTelemetrySample:
        raise ChildTelemetryError("sample must be exact concrete ChildTelemetrySample")
    _identifier("expected_telemetry_id", expected_telemetry_id)
    _sha256("expected_telemetry_sha256", expected_telemetry_sha256)
    _identifier("expected_reconcile_id", expected_reconcile_id)
    _sha256("expected_reconcile_sha256", expected_reconcile_sha256)
    rebuilt = ChildTelemetrySample.from_mapping(sample.as_dict())
    if rebuilt != sample:
        raise ChildTelemetryError("telemetry canonical reconstruction mismatch")
    if sample.telemetry_id != expected_telemetry_id:
        raise ChildTelemetryError("telemetry id mismatch at consumer boundary")
    if sample.sha256() != expected_telemetry_sha256:
        raise ChildTelemetryError("telemetry digest mismatch at consumer boundary")
    if sample.reconcile.reconcile_id != expected_reconcile_id:
        raise ChildTelemetryError("reconcile id mismatch at consumer boundary")
    if sample.reconcile_sha256 != expected_reconcile_sha256:
        raise ChildTelemetryError("reconcile digest mismatch at consumer boundary")
    return sample
