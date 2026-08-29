"""Fail-closed target-relative completion epistemics for Frankenstein 2.0.

F2-WP-1200 generation 1.

This module evaluates explicit target obligations from independently supplied positive
readback and counterevidence-probe results. Missing mandatory evidence stays UNKNOWN.
Repository/source/installer assertions are never promoted into target or physical-host
completion by this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

TARGET_OBLIGATION_SCHEMA = "FRANKENSTEIN2_TARGET_OBLIGATION/v1"
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
        object.__setattr__(
            self,
            "positive_evidence_refs",
            _refs("positive_evidence_ref", self.positive_evidence_refs),
        )
        object.__setattr__(
            self,
            "counterevidence_refs",
            _refs("counterevidence_ref", self.counterevidence_refs),
        )
        if self.positive_readback is PositiveReadback.PASS and not self.positive_evidence_refs:
            raise CompletionEpistemicsError("PASS positive readback requires evidence refs")
        if self.positive_readback is PositiveReadback.FAIL and not self.positive_evidence_refs:
            raise CompletionEpistemicsError("FAIL positive readback requires evidence refs")
        if self.counterevidence_probe is CounterevidenceProbe.CLEAR and not self.counterevidence_refs:
            raise CompletionEpistemicsError("CLEAR counterevidence probe requires probe refs")
        if self.counterevidence_probe is CounterevidenceProbe.FOUND and not self.counterevidence_refs:
            raise CompletionEpistemicsError("FOUND counterevidence requires evidence refs")

    @property
    def status(self) -> ObligationStatus:
        if self.positive_readback is PositiveReadback.FAIL:
            return ObligationStatus.FAIL
        if self.counterevidence_probe is CounterevidenceProbe.FOUND:
            return ObligationStatus.FAIL
        if (
            self.positive_readback is PositiveReadback.PASS
            and self.counterevidence_probe is CounterevidenceProbe.CLEAR
        ):
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
    obligations: tuple[TargetObligation, ...]
    schema: str = TARGET_COMPLETION_REPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TARGET_COMPLETION_REPORT_SCHEMA:
            raise CompletionEpistemicsError("target completion report schema mismatch")
        _clean_identifier("target_id", self.target_id)
        if not isinstance(self.evaluated_fidelity, FidelityLevel):
            raise CompletionEpistemicsError("evaluated_fidelity must be FidelityLevel")
        obligations = tuple(self.obligations)
        if not obligations:
            raise CompletionEpistemicsError("at least one target obligation is required")
        if len({item.obligation_id for item in obligations}) != len(obligations):
            raise CompletionEpistemicsError("duplicate obligation_id")
        for item in obligations:
            if not isinstance(item, TargetObligation):
                raise CompletionEpistemicsError("obligations must contain TargetObligation")
            if item.target_id != self.target_id:
                raise CompletionEpistemicsError("obligation target_id mismatch")
        object.__setattr__(self, "obligations", obligations)

    @property
    def in_scope(self) -> tuple[TargetObligation, ...]:
        rank = _FIDELITY_RANK[self.evaluated_fidelity]
        return tuple(
            item for item in self.obligations if _FIDELITY_RANK[item.required_fidelity] <= rank
        )

    @property
    def mandatory_in_scope(self) -> tuple[TargetObligation, ...]:
        return tuple(item for item in self.in_scope if item.mandatory)

    @property
    def status(self) -> CompletionStatus:
        mandatory = self.mandatory_in_scope
        if not mandatory:
            return CompletionStatus.UNKNOWN
        if any(item.status is ObligationStatus.FAIL for item in mandatory):
            return CompletionStatus.FAILED
        if any(item.status is ObligationStatus.UNKNOWN for item in mandatory):
            return CompletionStatus.UNKNOWN
        return CompletionStatus.COMPLETE

    @property
    def unknown_obligation_ids(self) -> tuple[str, ...]:
        return tuple(item.obligation_id for item in self.in_scope if item.status is ObligationStatus.UNKNOWN)

    @property
    def failed_obligation_ids(self) -> tuple[str, ...]:
        return tuple(item.obligation_id for item in self.in_scope if item.status is ObligationStatus.FAIL)

    @property
    def physical_credit(self) -> bool:
        """Physical credit is impossible below T4 and still requires all mandatory T4 evidence."""
        return self.evaluated_fidelity is FidelityLevel.T4_PHYSICAL and self.status is CompletionStatus.COMPLETE

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "target_id": self.target_id,
            "evaluated_fidelity": self.evaluated_fidelity.value,
            "status": self.status.value,
            "physical_credit": self.physical_credit,
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
    "TARGET_COMPLETION_REPORT_SCHEMA",
    "TARGET_OBLIGATION_SCHEMA",
]
