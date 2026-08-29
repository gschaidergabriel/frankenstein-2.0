"""Typed upstream admission envelope for cross-clock alignment evidence.

The temporal fusion module must not treat a caller-declared witness digest as proof that an
independent authority admitted that witness. This module defines the *shape* of a separately
produced admission registry snapshot. It deliberately does not read UnifiedDB, host clocks,
receipts, files, devices, or networks and therefore does not authenticate external world facts.

The intended boundary is:

    upstream deterministic authority / registry
        -> ClockAlignmentAdmissionRegistrySnapshot
        -> temporal fusion consumes exact admission record

A registry snapshot is evidence input, not self-authenticating world truth. Final integration
must bind ``authority_receipt_sha256`` and provenance to the actual canonical admission source.
What this contract prevents is the weaker and already-falsified API in which the temporal
caller could pass only ``witness.sha256()`` and thereby declare its own witness admitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

CLOCK_ALIGNMENT_ADMISSION_RECORD_SCHEMA = "FRANKENSTEIN2_CLOCK_ALIGNMENT_ADMISSION_RECORD/v1"
CLOCK_ALIGNMENT_ADMISSION_REGISTRY_SCHEMA = "FRANKENSTEIN2_CLOCK_ALIGNMENT_ADMISSION_REGISTRY/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ClockAlignmentAdmissionError(ValueError):
    """Fail-closed validation error for upstream clock-alignment admission contracts."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ClockAlignmentAdmissionError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ClockAlignmentAdmissionError(f"{name} must not contain control characters")
    return value


def _positive(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ClockAlignmentAdmissionError(f"{name} must be an integer > 0")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise ClockAlignmentAdmissionError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise ClockAlignmentAdmissionError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise ClockAlignmentAdmissionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ClockAlignmentAdmissionError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ClockAlignmentAdmissionRecord:
    """One exact witness identity admitted by an upstream registry generation."""

    admission_id: str
    admission_generation: int
    alignment_id: str
    witness_sha256: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = CLOCK_ALIGNMENT_ADMISSION_RECORD_SCHEMA
    classification: ClassVar[str] = "UPSTREAM_ADMISSION_RECORD_NOT_LOCAL_MINT_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "admission_id", _text("admission_id", self.admission_id))
        _positive("admission_generation", self.admission_generation)
        object.__setattr__(self, "alignment_id", _text("alignment_id", self.alignment_id))
        _sha256("witness_sha256", self.witness_sha256)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "admission_id": self.admission_id,
            "admission_generation": self.admission_generation,
            "alignment_id": self.alignment_id,
            "witness_sha256": self.witness_sha256,
            "local_temporal_admission_authority": "NONE",
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ClockAlignmentAdmissionRegistrySnapshot:
    """Immutable result of a separately produced clock-alignment admission registry.

    This object carries the upstream authority/receipt/generation identity required for causal
    binding. The temporal module may consume it but must not create an admission from a raw
    witness or raw digest. Authenticating the referenced receipt remains an integration-layer
    responsibility and receives no runtime/world-truth credit here.
    """

    registry_id: str
    registry_generation: int
    authority_id: str
    authority_generation: int
    authority_receipt_sha256: str
    admissions: tuple[ClockAlignmentAdmissionRecord, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = CLOCK_ALIGNMENT_ADMISSION_REGISTRY_SCHEMA
    classification: ClassVar[str] = "UPSTREAM_ADMISSION_REGISTRY_SNAPSHOT_NOT_SELF_AUTHENTICATING_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_id", _text("registry_id", self.registry_id))
        _positive("registry_generation", self.registry_generation)
        object.__setattr__(self, "authority_id", _text("authority_id", self.authority_id))
        _positive("authority_generation", self.authority_generation)
        _sha256("authority_receipt_sha256", self.authority_receipt_sha256)
        if type(self.admissions) is not tuple or any(
            type(item) is not ClockAlignmentAdmissionRecord for item in self.admissions
        ):
            raise ClockAlignmentAdmissionError(
                "admissions must be an immutable tuple of concrete ClockAlignmentAdmissionRecord values"
            )
        admission_ids = [item.admission_id for item in self.admissions]
        if len(admission_ids) != len(set(admission_ids)):
            raise ClockAlignmentAdmissionError("admissions must have unique admission_id")
        object.__setattr__(
            self,
            "admissions",
            tuple(sorted(self.admissions, key=lambda item: (item.alignment_id, item.witness_sha256, item.admission_id))),
        )
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def resolve_exact(
        self,
        *,
        alignment_id: str,
        witness_sha256: str,
    ) -> ClockAlignmentAdmissionRecord | None:
        alignment_id = _text("alignment_id", alignment_id)
        witness_sha256 = _sha256("witness_sha256", witness_sha256)
        matches = [
            item
            for item in self.admissions
            if item.alignment_id == alignment_id and item.witness_sha256 == witness_sha256
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "registry_id": self.registry_id,
            "registry_generation": self.registry_generation,
            "authority_id": self.authority_id,
            "authority_generation": self.authority_generation,
            "authority_receipt_sha256": self.authority_receipt_sha256,
            "admissions": [item.as_dict() for item in self.admissions],
            "temporal_module_mints_admission": False,
            "receipt_authentication_performed_here": False,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


__all__ = [
    "CLOCK_ALIGNMENT_ADMISSION_RECORD_SCHEMA",
    "CLOCK_ALIGNMENT_ADMISSION_REGISTRY_SCHEMA",
    "ClockAlignmentAdmissionError",
    "ClockAlignmentAdmissionRecord",
    "ClockAlignmentAdmissionRegistrySnapshot",
]
