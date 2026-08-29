"""Fail-closed target-relative completion epistemics for Frankenstein 2.0.

F2-WP-1200 generation 1.

Completion is evaluated against an explicit, generation-bound obligation manifest. Caller
omission of a mandatory obligation therefore remains UNKNOWN instead of shrinking the
completion universe. Repository/source/installer assertions never mint target or physical
host credit in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

TARGET_OBLIGATION_SCHEMA = "FRANKENSTEIN2_TARGET_OBLIGATION/v1"
TARGET_OBLIGATION_REQUIREMENT_SCHEMA = "FRANKENSTEIN2_TARGET_OBLIGATION_REQUIREMENT/v1"
TARGET_OBLIGATION_MANIFEST_SCHEMA = "FRANKENSTEIN2_TARGET_OBLIGATION_MANIFEST/v1"
TARGET_COMPLETION_REPORT_SCHEMA = "FRANKENSTEIN2_TARGET_COMPLETION_REPORT/v1"


class CompletionEpistemicsError(ValueError):
    """Fail-closed target-completion contract error."""


class FidelityLevel(str, Enum):
    T0_CONTRACT = "T0_CONTRACT"
    T1_UBUNTU_USERSPACE = "T1_UBUNTU_USERSPACE"
    T2_DEVICE_SESSION_FAULT_TWIN = "T2_DEVICE_SESSION_FAULT_TWIN"
    T3_TARGET_TRACE_REPLAY = "T3_TARGET_TRACE_REPLAY"
    T4_PHYSICAL = "T4_PHYSICAL"


_FIDELITY_RANK = {level: rank for rank, level in enumerate(FidelityLevel)}


class PositiveReadback(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CounterevidenceProbe(str, Enum):
    CLEAR = "CLEAR"
    FOUND = "FOUND"
    UNKNOWN = "UNKNOWN"


class ObligationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CompletionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


def _clean_identifier(name: str, value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CompletionEpistemicsError(f"{name} must be a non-empty trimmed string")
    if len(value) > 512:
        raise CompletionEpistemicsError(f"{name} is too long")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CompletionEpistemicsError(f"{name} contains control characters")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise CompletionEpistemicsError(f"{name} must be an iterable of refs, not a string")
    output = tuple(_clean_identifier(name, value) for value in values)
    if len(set(output)) != len(output):
        raise CompletionEpistemicsError(f"{name} contains duplicate refs")
    return output


@dataclass(frozen=True, slots=True)
class TargetObligationRequirement:
    """One mandatory member of the declared target-completion universe."""

    obligation_id: str
    required_fidelity: FidelityLevel
    schema: str = TARGET_OBLIGATION_REQUIREMENT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TARGET_OBLIGATION_REQUIREMENT_SCHEMA:
            raise CompletionEpistemicsError("target obligation requirement schema mismatch")
        _clean_identifier("obligation_id", self.obligation_id)
        if not isinstance(self.required_fidelity, FidelityLevel):
            raise CompletionEpistemicsError("required_fidelity must be FidelityLevel")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "obligation_id": self.obligation_id,
            "required_fidelity": self.required_fidelity.value,
        }


@dataclass(frozen=True, slots=True)
class TargetObligationManifest:
    """Closed-world mandatory obligation set for one target and generation."""

    target_id: str
    generation: int
    mandatory_obligations: tuple[TargetObligationRequirement, ...]
    schema: str = TARGET_OBLIGATION_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TARGET_OBLIGATION_MANIFEST_SCHEMA:
            raise CompletionEpistemicsError("target obligation manifest schema mismatch")
        _clean_identifier("target_id", self.target_id)
        if type(self.generation) is not int or self.generation < 1:
            raise CompletionEpistemicsError("generation must be a positive integer")
        requirements = tuple(self.mandatory_obligations)
        if not requirements:
            raise CompletionEpistemicsError("manifest must declare at least one mandatory obligation")
        for item in requirements:
            if type(item) is not TargetObligationRequirement:
                raise CompletionEpistemicsError(
                    "mandatory_obligations must contain exact TargetObligationRequirement"
                )
        if len({item.obligation_id for item in requirements}) != len(requirements):
            raise CompletionEpistemicsError("manifest contains duplicate obligation_id")
        object.__setattr__(self, "mandatory_obligations", requirements)

    def required_at(self, fidelity: FidelityLevel) -> tuple[TargetObligationRequirement, ...]:
        if not isinstance(fidelity, FidelityLevel):
            raise CompletionEpistemicsError("fidelity must be FidelityLevel")
        rank = _FIDELITY_RANK[fidelity]
        return tuple(
            item for item in self.mandatory_obligations
            if _FIDELITY_RANK[item.required_fidelity] <= rank
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "target_id": self.target_id,
            "generation": self.generation,
            "mandatory_obligations": [item.as_dict() for item in self.mandatory_obligations],
        }

    def canonical_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TargetObligation:
    obligation_id: str
    target_id: str
    required_fidelity: FidelityLevel
    mandatory: bool
    positive_readback: PositiveReadback = PositiveReadback.UNKNOWN
    positive_evidence_refs: tuple[str, ...] = ()
    counterevidence_probe: CounterevidenceProbe = CounterevidenceProbe.UNKNOWN
    counterevidence_refs: tuple[str, ...] = ()
    schema: str = TARGET_OBLIGATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TARGET_OBLIGATION_SCHEMA:
            raise CompletionEpistemicsError("target obligation schema mismatch")
        _clean_identifier("obligation_id", self.obligation_id)
        _clean_identifier("target_id", self.target_id)
        if type(self.mandatory) is not bool:
            raise CompletionEpistemicsError("mandatory must be bool")
        if not isinstance(self.required_fidelity, FidelityLevel):
            raise CompletionEpistemicsError("required_fidelity must be FidelityLevel")
        if not isinstance(self.positive_readback, PositiveReadback):
            raise CompletionEpistemicsError("positive_readback must be PositiveReadback")
        if not isinstance(self.counterevidence_probe, CounterevidenceProbe):
            raise CompletionEpistemicsError("counterevidence_probe must be CounterevidenceProbe")
        object.__setattr__(self, "positive_evidence_refs", _refs("positive_evidence_ref", self.positive_evidence_refs))
        object.__setattr__(self, "counterevidence_refs", _refs("counterevidence_ref", self.counterevidence_refs))
        if self.positive_readback in (PositiveReadback.PASS, PositiveReadback.FAIL) and not self.positive_evidence_refs:
            raise CompletionEpistemicsError("non-UNKNOWN positive readback requires evidence refs")
        if self.counterevidence_probe in (CounterevidenceProbe.CLEAR, CounterevidenceProbe.FOUND) and not self.counterevidence_refs:
            raise CompletionEpistemicsError("non-UNKNOWN counterevidence probe requires probe refs")

    @property
    def status(self) -> ObligationStatus:
        if self.positive_readback is PositiveReadback.FAIL:
            return ObligationStatus.FAIL
        if self.counterevidence_probe is CounterevidenceProbe.FOUND:
            return ObligationStatus.FAIL
        if self.positive_readback is PositiveReadback.PASS and self.counterevidence_probe is CounterevidenceProbe.CLEAR:
            return ObligationStatus.PASS
        return ObligationStatus.UNKNOWN

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "obligation_id": self.obligation_id,
            "target_id": self.target_id,
            "required_fidelity": self.required_fidelity.value,
            "mandatory": self.mandatory,
            "positive_readback": self.positive_readback.value,
            "positive_evidence_refs": list(self.positive_evidence_refs),
            "counterevidence_probe": self.counterevidence_probe.value,
            "counterevidence_refs": list(self.counterevidence_refs),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class TargetCompletionReport:
    target_id: str
    evaluated_fidelity: FidelityLevel
    manifest: TargetObligationManifest
    obligations: tuple[TargetObligation, ...]
    schema: str = TARGET_COMPLETION_REPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TARGET_COMPLETION_REPORT_SCHEMA:
            raise CompletionEpistemicsError("target completion report schema mismatch")
        _clean_identifier("target_id", self.target_id)
        if not isinstance(self.evaluated_fidelity, FidelityLevel):
            raise CompletionEpistemicsError("evaluated_fidelity must be FidelityLevel")
        if type(self.manifest) is not TargetObligationManifest:
            raise CompletionEpistemicsError("manifest must be exact TargetObligationManifest")
        if self.manifest.target_id != self.target_id:
            raise CompletionEpistemicsError("manifest target_id mismatch")

        obligations = tuple(self.obligations)
        for item in obligations:
            if type(item) is not TargetObligation:
                raise CompletionEpistemicsError("obligations must contain exact TargetObligation")
        if len({item.obligation_id for item in obligations}) != len(obligations):
            raise CompletionEpistemicsError("duplicate obligation_id")

        declared = {item.obligation_id: item for item in self.manifest.mandatory_obligations}
        for item in obligations:
            if item.target_id != self.target_id:
                raise CompletionEpistemicsError("obligation target_id mismatch")
            requirement = declared.get(item.obligation_id)
            if requirement is None:
                if item.mandatory:
                    raise CompletionEpistemicsError(
                        "mandatory obligation is not declared by the bound manifest"
                    )
                continue
            if not item.mandatory:
                raise CompletionEpistemicsError(
                    "manifest-declared mandatory obligation cannot be supplied as optional"
                )
            if item.required_fidelity is not requirement.required_fidelity:
                raise CompletionEpistemicsError(
                    "obligation required_fidelity does not match bound manifest"
                )
        object.__setattr__(self, "obligations", obligations)

    @property
    def in_scope(self) -> tuple[TargetObligation, ...]:
        rank = _FIDELITY_RANK[self.evaluated_fidelity]
        return tuple(item for item in self.obligations if _FIDELITY_RANK[item.required_fidelity] <= rank)

    @property
    def required_manifest_in_scope(self) -> tuple[TargetObligationRequirement, ...]:
        return self.manifest.required_at(self.evaluated_fidelity)

    @property
    def mandatory_in_scope(self) -> tuple[TargetObligation, ...]:
        required_ids = {item.obligation_id for item in self.required_manifest_in_scope}
        return tuple(item for item in self.in_scope if item.obligation_id in required_ids)

    @property
    def missing_mandatory_obligation_ids(self) -> tuple[str, ...]:
        supplied_ids = {item.obligation_id for item in self.obligations}
        return tuple(
            item.obligation_id
            for item in self.required_manifest_in_scope
            if item.obligation_id not in supplied_ids
        )

    @property
    def status(self) -> CompletionStatus:
        required = self.required_manifest_in_scope
        if not required:
            return CompletionStatus.UNKNOWN
        mandatory = self.mandatory_in_scope
        if any(item.status is ObligationStatus.FAIL for item in mandatory):
            return CompletionStatus.FAILED
        if self.missing_mandatory_obligation_ids:
            return CompletionStatus.UNKNOWN
        if any(item.status is ObligationStatus.UNKNOWN for item in mandatory):
            return CompletionStatus.UNKNOWN
        if len(mandatory) != len(required):
            return CompletionStatus.UNKNOWN
        return CompletionStatus.COMPLETE

    @property
    def unknown_obligation_ids(self) -> tuple[str, ...]:
        supplied_unknown = [
            item.obligation_id for item in self.in_scope if item.status is ObligationStatus.UNKNOWN
        ]
        seen = set(supplied_unknown)
        for obligation_id in self.missing_mandatory_obligation_ids:
            if obligation_id not in seen:
                supplied_unknown.append(obligation_id)
                seen.add(obligation_id)
        return tuple(supplied_unknown)

    @property
    def failed_obligation_ids(self) -> tuple[str, ...]:
        return tuple(item.obligation_id for item in self.mandatory_in_scope if item.status is ObligationStatus.FAIL)

    @property
    def physical_completion_candidate(self) -> bool:
        """Evidence-shaped T4 candidate only; never physical execution credit."""
        required_t4 = tuple(
            item for item in self.required_manifest_in_scope
            if item.required_fidelity is FidelityLevel.T4_PHYSICAL
        )
        return (
            self.evaluated_fidelity is FidelityLevel.T4_PHYSICAL
            and bool(required_t4)
            and self.status is CompletionStatus.COMPLETE
        )

    @property
    def physical_credit(self) -> bool:
        """Never mint physical-host credit from caller-supplied refs."""
        return False

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "target_id": self.target_id,
            "evaluated_fidelity": self.evaluated_fidelity.value,
            "manifest_generation": self.manifest.generation,
            "manifest_sha256": self.manifest.sha256(),
            "manifest": self.manifest.as_dict(),
            "status": self.status.value,
            "physical_completion_candidate": self.physical_completion_candidate,
            "physical_credit": False,
            "missing_mandatory_obligation_ids": list(self.missing_mandatory_obligation_ids),
            "unknown_obligation_ids": list(self.unknown_obligation_ids),
            "failed_obligation_ids": list(self.failed_obligation_ids),
            "obligations": [item.as_dict() for item in self.obligations],
        }

    def canonical_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


__all__ = [
    "CompletionEpistemicsError",
    "CompletionStatus",
    "CounterevidenceProbe",
    "FidelityLevel",
    "ObligationStatus",
    "PositiveReadback",
    "TargetCompletionReport",
    "TargetObligation",
    "TargetObligationManifest",
    "TargetObligationRequirement",
    "TARGET_COMPLETION_REPORT_SCHEMA",
    "TARGET_OBLIGATION_MANIFEST_SCHEMA",
    "TARGET_OBLIGATION_REQUIREMENT_SCHEMA",
    "TARGET_OBLIGATION_SCHEMA",
]
