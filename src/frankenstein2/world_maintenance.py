"""Deterministic maintenance proposals for the Frankenstein 2.0 sparse world substrate.

F2-WP-401 generation 1. These functions classify candidate maintenance work only.
They do not mutate a database, delete evidence, promote world truth, authorize effects,
or claim runtime/GWT/GRID10 execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any

from .sparse_world_basis import WorldAtom, WorldOperator


MAINTENANCE_EVIDENCE_SCHEMA = "FRANKENSTEIN2_WORLD_MAINTENANCE_EVIDENCE/v1"
ATOM_ASSESSMENT_SCHEMA = "FRANKENSTEIN2_ATOM_ASSIMILATION_RESULT/v1"
OPERATOR_ASSESSMENT_SCHEMA = "FRANKENSTEIN2_OPERATOR_MAINTENANCE_RESULT/v1"


class WorldMaintenanceError(ValueError):
    """Fail-closed validation error for maintenance proposal construction."""


class MaintenanceEvidenceClass(str, Enum):
    VERIFIED_OBSERVATION = "VERIFIED_OBSERVATION"
    VERIFIED_OUTCOME_MATCH = "VERIFIED_OUTCOME_MATCH"
    VERIFIED_OUTCOME_FAILURE = "VERIFIED_OUTCOME_FAILURE"
    INFERRED = "INFERRED"
    SIMULATED = "SIMULATED"


class AtomMaintenanceAction(str, Enum):
    ADD_CANDIDATE = "ADD_CANDIDATE"
    NO_CHANGE = "NO_CHANGE"
    EXACT_DUPLICATE_CANDIDATE = "EXACT_DUPLICATE_CANDIDATE"
    CONFLICT_PRESERVED = "CONFLICT_PRESERVED"


class OperatorMaintenanceAction(str, Enum):
    HOLD_UNVERIFIED = "HOLD_UNVERIFIED"
    PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"
    DOWNGRADE_CANDIDATE = "DOWNGRADE_CANDIDATE"
    CONFLICT_PRESERVED = "CONFLICT_PRESERVED"


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise WorldMaintenanceError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise WorldMaintenanceError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise WorldMaintenanceError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise WorldMaintenanceError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise WorldMaintenanceError(f"{name} must be an immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if not allow_empty and not refs:
        raise WorldMaintenanceError(f"{name} must not be empty")
    if len(set(refs)) != len(refs):
        raise WorldMaintenanceError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorldMaintenanceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _atom_semantic_digest(atom: WorldAtom) -> str:
    """Identity/provenance-independent digest used only to propose duplicate compression.

    Provenance and evidence are intentionally excluded from the equivalence key: two
    independently sourced atoms may describe the same projected content. The proposal
    result retains the union of those refs and performs no deletion or canonical merge.
    """
    if not isinstance(atom, WorldAtom):
        raise WorldMaintenanceError("atom must be WorldAtom")
    payload = atom.as_dict().copy()
    for field_name in ("atom_id", "provenance_refs", "evidence_refs"):
        payload.pop(field_name, None)
    return _digest(payload)


@dataclass(frozen=True, slots=True, kw_only=True)
class MaintenanceEvidence:
    evidence_id: str
    generation: int
    target_id: str
    target_sha256: str
    evidence_class: MaintenanceEvidenceClass
    provenance_refs: tuple[str, ...]

    schema = MAINTENANCE_EVIDENCE_SCHEMA
    classification = "MAINTENANCE_EVIDENCE_NOT_WORLD_TRUTH_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text("evidence_id", self.evidence_id))
        _generation("generation", self.generation)
        object.__setattr__(self, "target_id", _text("target_id", self.target_id))
        object.__setattr__(self, "target_sha256", _sha256("target_sha256", self.target_sha256))
        if not isinstance(self.evidence_class, MaintenanceEvidenceClass):
            raise WorldMaintenanceError("evidence_class must be MaintenanceEvidenceClass")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "evidence_id": self.evidence_id,
            "generation": self.generation,
            "target_id": self.target_id,
            "target_sha256": self.target_sha256,
            "evidence_class": self.evidence_class.value,
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class AtomAssimilationResult:
    incoming_atom_id: str
    incoming_atom_sha256: str
    action: AtomMaintenanceAction
    canonical_candidate_atom_id: str
    conflicting_atom_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    schema = ATOM_ASSESSMENT_SCHEMA
    classification = "NONCANONICAL_MAINTENANCE_PROPOSAL"

    def __post_init__(self) -> None:
        object.__setattr__(self, "incoming_atom_id", _text("incoming_atom_id", self.incoming_atom_id))
        object.__setattr__(self, "incoming_atom_sha256", _sha256("incoming_atom_sha256", self.incoming_atom_sha256))
        if not isinstance(self.action, AtomMaintenanceAction):
            raise WorldMaintenanceError("action must be AtomMaintenanceAction")
        object.__setattr__(self, "canonical_candidate_atom_id", _text("canonical_candidate_atom_id", self.canonical_candidate_atom_id))
        object.__setattr__(self, "conflicting_atom_ids", _refs("conflicting_atom_ids", self.conflicting_atom_ids, allow_empty=True))
        object.__setattr__(self, "evidence_refs", _refs("evidence_refs", self.evidence_refs, allow_empty=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "incoming_atom_id": self.incoming_atom_id,
            "incoming_atom_sha256": self.incoming_atom_sha256,
            "action": self.action.value,
            "canonical_candidate_atom_id": self.canonical_candidate_atom_id,
            "conflicting_atom_ids": list(self.conflicting_atom_ids),
            "evidence_refs": list(self.evidence_refs),
            "mutation_performed": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorMaintenanceResult:
    operator_id: str
    operator_sha256: str
    action: OperatorMaintenanceAction
    verified_support_count: int
    verified_failure_count: int
    nonverified_count: int
    evidence_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema = OPERATOR_ASSESSMENT_SCHEMA
    classification = "NONCANONICAL_OPERATOR_MAINTENANCE_PROPOSAL"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _text("operator_id", self.operator_id))
        object.__setattr__(self, "operator_sha256", _sha256("operator_sha256", self.operator_sha256))
        if not isinstance(self.action, OperatorMaintenanceAction):
            raise WorldMaintenanceError("action must be OperatorMaintenanceAction")
        for name in ("verified_support_count", "verified_failure_count", "nonverified_count"):
            _generation(name, getattr(self, name))
        object.__setattr__(self, "evidence_ids", _refs("evidence_ids", self.evidence_ids, allow_empty=True))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs, allow_empty=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "operator_id": self.operator_id,
            "operator_sha256": self.operator_sha256,
            "action": self.action.value,
            "verified_support_count": self.verified_support_count,
            "verified_failure_count": self.verified_failure_count,
            "nonverified_count": self.nonverified_count,
            "evidence_ids": list(self.evidence_ids),
            "provenance_refs": list(self.provenance_refs),
            "mutation_performed": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def assimilate_atom(
    *,
    incoming: WorldAtom,
    existing_atoms: tuple[WorldAtom, ...],
    expected_generation: int,
    expected_vector_space_version: str,
) -> AtomAssimilationResult:
    """Classify one atom without mutating or deleting any substrate state."""
    if not isinstance(incoming, WorldAtom):
        raise WorldMaintenanceError("incoming must be WorldAtom")
    if not isinstance(existing_atoms, tuple) or not all(isinstance(item, WorldAtom) for item in existing_atoms):
        raise WorldMaintenanceError("existing_atoms must be an immutable tuple of WorldAtom")
    generation = _generation("expected_generation", expected_generation)
    vector_space = _text("expected_vector_space_version", expected_vector_space_version)
    all_atoms = existing_atoms + (incoming,)
    if any(atom.generation != generation for atom in all_atoms):
        raise WorldMaintenanceError("atom generation mismatch")
    if any(atom.vector_space_version != vector_space for atom in all_atoms):
        raise WorldMaintenanceError("atom vector_space_version mismatch")
    existing_ids = tuple(atom.atom_id for atom in existing_atoms)
    if len(set(existing_ids)) != len(existing_ids):
        raise WorldMaintenanceError("existing_atoms contain duplicate atom_id")

    same_id = next((atom for atom in existing_atoms if atom.atom_id == incoming.atom_id), None)
    evidence_refs = set(incoming.provenance_refs) | set(incoming.evidence_refs)
    if same_id is not None:
        evidence_refs.update(same_id.provenance_refs)
        evidence_refs.update(same_id.evidence_refs)
        if same_id.sha256() == incoming.sha256():
            action = AtomMaintenanceAction.NO_CHANGE
            conflicts: tuple[str, ...] = ()
        else:
            action = AtomMaintenanceAction.CONFLICT_PRESERVED
            conflicts = (same_id.atom_id,)
        canonical_id = same_id.atom_id
    else:
        incoming_content = _atom_semantic_digest(incoming)
        duplicates = tuple(
            atom for atom in existing_atoms if _atom_semantic_digest(atom) == incoming_content
        )
        if duplicates:
            action = AtomMaintenanceAction.EXACT_DUPLICATE_CANDIDATE
            canonical_id = min((incoming.atom_id,) + tuple(atom.atom_id for atom in duplicates))
            conflicts = ()
            for atom in duplicates:
                evidence_refs.update(atom.provenance_refs)
                evidence_refs.update(atom.evidence_refs)
        else:
            action = AtomMaintenanceAction.ADD_CANDIDATE
            canonical_id = incoming.atom_id
            conflicts = ()

    return AtomAssimilationResult(
        incoming_atom_id=incoming.atom_id,
        incoming_atom_sha256=incoming.sha256(),
        action=action,
        canonical_candidate_atom_id=canonical_id,
        conflicting_atom_ids=conflicts,
        evidence_refs=tuple(sorted(evidence_refs)),
    )


def assess_operator(
    *,
    operator: WorldOperator,
    evidence: tuple[MaintenanceEvidence, ...],
    expected_generation: int,
    min_verified_support: int = 2,
) -> OperatorMaintenanceResult:
    """Assess support/failure evidence and emit a noncanonical maintenance proposal."""
    if not isinstance(operator, WorldOperator):
        raise WorldMaintenanceError("operator must be WorldOperator")
    if not isinstance(evidence, tuple) or not all(isinstance(item, MaintenanceEvidence) for item in evidence):
        raise WorldMaintenanceError("evidence must be an immutable tuple of MaintenanceEvidence")
    generation = _generation("expected_generation", expected_generation)
    if operator.generation != generation:
        raise WorldMaintenanceError("operator generation mismatch")
    if type(min_verified_support) is not int or min_verified_support <= 0:
        raise WorldMaintenanceError("min_verified_support must be an integer > 0")
    evidence_ids = tuple(item.evidence_id for item in evidence)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise WorldMaintenanceError("duplicate evidence_id")

    operator_sha = operator.sha256()
    for item in evidence:
        if item.generation != generation:
            raise WorldMaintenanceError("evidence generation mismatch")
        if item.target_id != operator.operator_id:
            raise WorldMaintenanceError("evidence target_id mismatch")
        if item.target_sha256 != operator_sha:
            raise WorldMaintenanceError("evidence target digest mismatch")

    support_classes = {
        MaintenanceEvidenceClass.VERIFIED_OBSERVATION,
        MaintenanceEvidenceClass.VERIFIED_OUTCOME_MATCH,
    }
    support = sum(item.evidence_class in support_classes for item in evidence)
    failures = sum(item.evidence_class is MaintenanceEvidenceClass.VERIFIED_OUTCOME_FAILURE for item in evidence)
    nonverified = sum(item.evidence_class in {MaintenanceEvidenceClass.INFERRED, MaintenanceEvidenceClass.SIMULATED} for item in evidence)

    if failures and support:
        action = OperatorMaintenanceAction.CONFLICT_PRESERVED
    elif failures:
        action = OperatorMaintenanceAction.DOWNGRADE_CANDIDATE
    elif support >= min_verified_support:
        action = OperatorMaintenanceAction.PROMOTION_CANDIDATE
    else:
        action = OperatorMaintenanceAction.HOLD_UNVERIFIED

    provenance = set(operator.provenance_refs)
    for item in evidence:
        provenance.update(item.provenance_refs)

    return OperatorMaintenanceResult(
        operator_id=operator.operator_id,
        operator_sha256=operator_sha,
        action=action,
        verified_support_count=support,
        verified_failure_count=failures,
        nonverified_count=nonverified,
        evidence_ids=tuple(sorted(evidence_ids)),
        provenance_refs=tuple(sorted(provenance)),
    )
