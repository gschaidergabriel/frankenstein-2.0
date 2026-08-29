"""Deterministic sparse generative world-basis primitives for Frankenstein 2.0.

This generation is a synthetic/local substrate only. Vectors are opaque caller-supplied
payloads. Explicit activation values may route bounded expansion, but similarity, model
output, recurrence, or reconstruction never mint world truth, effect authority, completion,
GWT uptake, or runtime credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, ClassVar


WORLD_ATOM_SCHEMA = "FRANKENSTEIN2_WORLD_ATOM/v1"
WORLD_OPERATOR_SCHEMA = "FRANKENSTEIN2_WORLD_OPERATOR/v1"
WORLD_NEED_SCHEMA = "FRANKENSTEIN2_WORLD_NEED/v1"
WORLD_SLICE_SCHEMA = "FRANKENSTEIN2_WORLD_SLICE/v1"
WORLD_ACTIVATION_SCHEMA = "FRANKENSTEIN2_WORLD_ACTIVATION/v1"


class SparseWorldError(ValueError):
    """Fail-closed validation error for the sparse world substrate."""


class EpistemicOrigin(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    SIMULATED = "SIMULATED"
    LEARNED_RULE = "LEARNED_RULE"


class KnowledgeState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    NOT_COMPUTED = "NOT_COMPUTED"


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SparseWorldError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise SparseWorldError(f"{name} must not contain leading or trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise SparseWorldError(f"{name} must not contain control characters")
    return value


def _require_generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SparseWorldError("generation must be an integer >= 0")
    return value


def _require_positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SparseWorldError(f"{name} must be an integer > 0")
    return value


def _require_nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SparseWorldError(f"{name} must be an integer >= 0")
    return value


def _require_micros(name: str, value: Any, *, allow_none: bool = False) -> int | None:
    if value is None:
        if allow_none:
            return None
        raise SparseWorldError(f"{name} is required")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise SparseWorldError(f"{name} must be an integer in [0, 1000000]")
    return value


def _require_refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise SparseWorldError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise SparseWorldError(f"{name} must not be empty")
    refs = tuple(_require_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise SparseWorldError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _require_vector(value: Any) -> tuple[int, ...]:
    if not isinstance(value, tuple) or not value:
        raise SparseWorldError("vector must be a non-empty immutable tuple")
    checked: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise SparseWorldError("vector components must be integers")
        if not -1_000_000_000 <= item <= 1_000_000_000:
            raise SparseWorldError("vector component out of bounded range")
        checked.append(item)
    return tuple(checked)


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
        raise SparseWorldError("value must be canonical-JSON encodable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldAtom:
    atom_id: str
    generation: int
    vector_space_version: str
    vector: tuple[int, ...]
    epistemic_origin: EpistemicOrigin
    knowledge_state: KnowledgeState
    provenance_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()
    confidence_micros: int | None = None

    schema: ClassVar[str] = WORLD_ATOM_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_WORLD_PROJECTION_ATOM"

    def __post_init__(self) -> None:
        object.__setattr__(self, "atom_id", _require_text("atom_id", self.atom_id))
        _require_generation(self.generation)
        object.__setattr__(
            self,
            "vector_space_version",
            _require_text("vector_space_version", self.vector_space_version),
        )
        object.__setattr__(self, "vector", _require_vector(self.vector))
        if not isinstance(self.epistemic_origin, EpistemicOrigin):
            raise SparseWorldError("epistemic_origin must be an EpistemicOrigin")
        if not isinstance(self.knowledge_state, KnowledgeState):
            raise SparseWorldError("knowledge_state must be a KnowledgeState")
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _require_refs("evidence_refs", self.evidence_refs, allow_empty=True),
        )
        _require_micros("confidence_micros", self.confidence_micros, allow_none=True)

        if self.knowledge_state is KnowledgeState.NOT_COMPUTED:
            if self.evidence_refs or self.confidence_micros is not None:
                raise SparseWorldError(
                    "NOT_COMPUTED atom must not carry computed evidence or confidence"
                )
        if self.knowledge_state is KnowledgeState.UNKNOWN and self.confidence_micros is not None:
            raise SparseWorldError("UNKNOWN atom must not carry confidence")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "atom_id": self.atom_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "vector": list(self.vector),
            "epistemic_origin": self.epistemic_origin.value,
            "knowledge_state": self.knowledge_state.value,
            "provenance_refs": list(self.provenance_refs),
            "evidence_refs": list(self.evidence_refs),
            "confidence_micros": self.confidence_micros,
            "truth_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldOperator:
    operator_id: str
    generation: int
    operator_version: str
    vector_space_version: str
    input_atom_ids: tuple[str, ...]
    output_atom_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    epistemic_origin: EpistemicOrigin = EpistemicOrigin.LEARNED_RULE

    schema: ClassVar[str] = WORLD_OPERATOR_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_TRANSFORM_OPERATOR"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _require_text("operator_id", self.operator_id))
        _require_generation(self.generation)
        object.__setattr__(
            self, "operator_version", _require_text("operator_version", self.operator_version)
        )
        object.__setattr__(
            self,
            "vector_space_version",
            _require_text("vector_space_version", self.vector_space_version),
        )
        object.__setattr__(
            self,
            "input_atom_ids",
            _require_refs("input_atom_ids", self.input_atom_ids, allow_empty=False),
        )
        object.__setattr__(
            self,
            "output_atom_ids",
            _require_refs("output_atom_ids", self.output_atom_ids, allow_empty=False),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        if not isinstance(self.epistemic_origin, EpistemicOrigin):
            raise SparseWorldError("epistemic_origin must be an EpistemicOrigin")
        if set(self.input_atom_ids).intersection(self.output_atom_ids):
            raise SparseWorldError("operator input_atom_ids and output_atom_ids must not overlap")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "operator_id": self.operator_id,
            "generation": self.generation,
            "operator_version": self.operator_version,
            "vector_space_version": self.vector_space_version,
            "input_atom_ids": list(self.input_atom_ids),
            "output_atom_ids": list(self.output_atom_ids),
            "provenance_refs": list(self.provenance_refs),
            "epistemic_origin": self.epistemic_origin.value,
            "truth_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class AtomActivation:
    atom_id: str
    activation_micros: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = WORLD_ACTIVATION_SCHEMA
    classification: ClassVar[str] = "CALLER_SUPPLIED_ROUTING_SIGNAL_NOT_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "atom_id", _require_text("atom_id", self.atom_id))
        _require_micros("activation_micros", self.activation_micros)
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "atom_id": self.atom_id,
            "activation_micros": self.activation_micros,
            "provenance_refs": list(self.provenance_refs),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldNeed:
    need_id: str
    cycle_id: str
    generation: int
    vector_space_version: str
    start_atom_ids: tuple[str, ...]
    target_atom_ids: tuple[str, ...]
    max_depth: int
    max_atoms: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = WORLD_NEED_SCHEMA
    classification: ClassVar[str] = "BOUNDED_WORLD_SLICE_REQUEST_NOT_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "need_id", _require_text("need_id", self.need_id))
        object.__setattr__(self, "cycle_id", _require_text("cycle_id", self.cycle_id))
        _require_generation(self.generation)
        object.__setattr__(
            self,
            "vector_space_version",
            _require_text("vector_space_version", self.vector_space_version),
        )
        object.__setattr__(
            self,
            "start_atom_ids",
            _require_refs("start_atom_ids", self.start_atom_ids, allow_empty=False),
        )
        object.__setattr__(
            self,
            "target_atom_ids",
            _require_refs("target_atom_ids", self.target_atom_ids, allow_empty=True),
        )
        _require_nonnegative_int("max_depth", self.max_depth)
        _require_positive_int("max_atoms", self.max_atoms)
        if len(self.start_atom_ids) > self.max_atoms:
            raise SparseWorldError("start_atom_ids exceed max_atoms")
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "need_id": self.need_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "start_atom_ids": list(self.start_atom_ids),
            "target_atom_ids": list(self.target_atom_ids),
            "max_depth": self.max_depth,
            "max_atoms": self.max_atoms,
            "provenance_refs": list(self.provenance_refs),
            "effect_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldSlice:
    slice_id: str
    need_id: str
    cycle_id: str
    generation: int
    vector_space_version: str
    selected_atom_ids: tuple[str, ...]
    selected_operator_ids: tuple[str, ...]
    unresolved_target_atom_ids: tuple[str, ...]
    tainted_atom_ids: tuple[str, ...]
    depth_reached: int
    stopped_reason: str
    evidence_refs: tuple[str, ...]
    provenance_digest: str

    schema: ClassVar[str] = WORLD_SLICE_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_EXPIRES_AFTER_COGNITIVE_USE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "slice_id", _require_text("slice_id", self.slice_id))
        object.__setattr__(self, "need_id", _require_text("need_id", self.need_id))
        object.__setattr__(self, "cycle_id", _require_text("cycle_id", self.cycle_id))
        _require_generation(self.generation)
        object.__setattr__(
            self,
            "vector_space_version",
            _require_text("vector_space_version", self.vector_space_version),
        )
        for field_name in (
            "selected_atom_ids",
            "selected_operator_ids",
            "unresolved_target_atom_ids",
            "tainted_atom_ids",
            "evidence_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_refs(field_name, getattr(self, field_name), allow_empty=True),
            )
        _require_nonnegative_int("depth_reached", self.depth_reached)
        object.__setattr__(
            self, "stopped_reason", _require_text("stopped_reason", self.stopped_reason)
        )
        digest = _require_text("provenance_digest", self.provenance_digest)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise SparseWorldError("provenance_digest must be lowercase sha256 hex")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "slice_id": self.slice_id,
            "need_id": self.need_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "selected_atom_ids": list(self.selected_atom_ids),
            "selected_operator_ids": list(self.selected_operator_ids),
            "unresolved_target_atom_ids": list(self.unresolved_target_atom_ids),
            "tainted_atom_ids": list(self.tainted_atom_ids),
            "depth_reached": self.depth_reached,
            "stopped_reason": self.stopped_reason,
            "evidence_refs": list(self.evidence_refs),
            "provenance_digest": self.provenance_digest,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


def _validate_substrate(
    *,
    atoms: tuple[WorldAtom, ...],
    operators: tuple[WorldOperator, ...],
    activations: tuple[AtomActivation, ...],
    need: WorldNeed,
) -> tuple[dict[str, WorldAtom], dict[str, WorldOperator], dict[str, AtomActivation]]:
    if not isinstance(atoms, tuple) or not atoms:
        raise SparseWorldError("atoms must be a non-empty immutable tuple")
    if not isinstance(operators, tuple):
        raise SparseWorldError("operators must be an immutable tuple")
    if not isinstance(activations, tuple):
        raise SparseWorldError("activations must be an immutable tuple")
    if not isinstance(need, WorldNeed):
        raise SparseWorldError("need must be a WorldNeed")

    atom_by_id: dict[str, WorldAtom] = {}
    for atom in atoms:
        if not isinstance(atom, WorldAtom):
            raise SparseWorldError("atoms must contain WorldAtom values")
        if atom.atom_id in atom_by_id:
            raise SparseWorldError(f"duplicate atom_id: {atom.atom_id}")
        if atom.vector_space_version != need.vector_space_version:
            raise SparseWorldError("atom vector_space_version mismatch")
        if atom.generation != need.generation:
            raise SparseWorldError("atom generation mismatch")
        atom_by_id[atom.atom_id] = atom

    operator_by_id: dict[str, WorldOperator] = {}
    for operator in operators:
        if not isinstance(operator, WorldOperator):
            raise SparseWorldError("operators must contain WorldOperator values")
        if operator.operator_id in operator_by_id:
            raise SparseWorldError(f"duplicate operator_id: {operator.operator_id}")
        if operator.vector_space_version != need.vector_space_version:
            raise SparseWorldError("operator vector_space_version mismatch")
        if operator.generation != need.generation:
            raise SparseWorldError("operator generation mismatch")
        unknown = (set(operator.input_atom_ids) | set(operator.output_atom_ids)) - set(atom_by_id)
        if unknown:
            raise SparseWorldError(
                "operator references unknown atoms: " + ",".join(sorted(unknown))
            )
        operator_by_id[operator.operator_id] = operator

    activation_by_id: dict[str, AtomActivation] = {}
    for activation in activations:
        if not isinstance(activation, AtomActivation):
            raise SparseWorldError("activations must contain AtomActivation values")
        if activation.atom_id in activation_by_id:
            raise SparseWorldError(f"duplicate activation atom_id: {activation.atom_id}")
        if activation.atom_id not in atom_by_id:
            raise SparseWorldError(f"activation references unknown atom: {activation.atom_id}")
        activation_by_id[activation.atom_id] = activation

    missing_boundary = set(need.start_atom_ids) - set(atom_by_id)
    if missing_boundary:
        raise SparseWorldError(
            "start_atom_ids reference unknown atoms: " + ",".join(sorted(missing_boundary))
        )
    missing_targets = set(need.target_atom_ids) - set(atom_by_id)
    if missing_targets:
        raise SparseWorldError(
            "target_atom_ids reference unknown atoms: " + ",".join(sorted(missing_targets))
        )
    return atom_by_id, operator_by_id, activation_by_id


def _taint_closure(
    atom_by_id: dict[str, WorldAtom],
    operators: tuple[WorldOperator, ...],
) -> set[str]:
    tainted = {
        atom_id
        for atom_id, atom in atom_by_id.items()
        if atom.knowledge_state is KnowledgeState.NOT_COMPUTED
    }
    changed = True
    while changed:
        changed = False
        for operator in operators:
            if set(operator.input_atom_ids).intersection(tainted):
                for output_id in operator.output_atom_ids:
                    if output_id not in tainted:
                        tainted.add(output_id)
                        changed = True
    return tainted


def materialize_world_slice(
    *,
    atoms: tuple[WorldAtom, ...],
    operators: tuple[WorldOperator, ...],
    activations: tuple[AtomActivation, ...],
    need: WorldNeed,
) -> WorldSlice:
    """Materialize one bounded, noncanonical local world slice.

    Expansion uses only exact graph reachability plus explicit caller-supplied activation.
    Omitted activation defaults to zero. Higher activation wins; ties use atom_id order.
    """
    atom_by_id, _, activation_by_id = _validate_substrate(
        atoms=atoms,
        operators=operators,
        activations=activations,
        need=need,
    )
    ordered_operators = tuple(sorted(operators, key=lambda item: item.operator_id))
    tainted = _taint_closure(atom_by_id, ordered_operators)

    selected = set(need.start_atom_ids)
    selected_operators: set[str] = set()
    evidence_refs = set(need.provenance_refs)
    for atom_id in selected:
        evidence_refs.update(atom_by_id[atom_id].provenance_refs)
        evidence_refs.update(atom_by_id[atom_id].evidence_refs)

    depth_reached = 0
    stopped_reason = "NO_EXPANSION_AVAILABLE"

    for depth in range(1, need.max_depth + 1):
        candidates: dict[str, set[str]] = {}
        for operator in ordered_operators:
            inputs = set(operator.input_atom_ids)
            if not inputs.issubset(selected):
                continue
            if inputs.intersection(tainted):
                continue
            for output_id in operator.output_atom_ids:
                if output_id in selected or output_id in tainted:
                    continue
                candidates.setdefault(output_id, set()).add(operator.operator_id)

        if not candidates:
            stopped_reason = "NO_EXPANSION_AVAILABLE"
            break

        slots = need.max_atoms - len(selected)
        if slots <= 0:
            stopped_reason = "MAX_ATOMS_REACHED"
            break

        ranked = sorted(
            candidates,
            key=lambda atom_id: (
                -(
                    activation_by_id[atom_id].activation_micros
                    if atom_id in activation_by_id
                    else 0
                ),
                atom_id,
            ),
        )
        chosen = ranked[:slots]
        for atom_id in chosen:
            selected.add(atom_id)
            atom = atom_by_id[atom_id]
            evidence_refs.update(atom.provenance_refs)
            evidence_refs.update(atom.evidence_refs)
            activation = activation_by_id.get(atom_id)
            if activation is not None:
                evidence_refs.update(activation.provenance_refs)
            selected_operators.update(candidates[atom_id])

        depth_reached = depth
        if set(need.target_atom_ids).issubset(selected):
            stopped_reason = "TARGETS_REACHED"
            break
        if len(selected) >= need.max_atoms:
            stopped_reason = "MAX_ATOMS_REACHED"
            break
    else:
        stopped_reason = "MAX_DEPTH_REACHED"

    unresolved = set(need.target_atom_ids) - selected
    provenance_payload = {
        "need": need.as_dict(),
        "atoms": [atom_by_id[atom_id].as_dict() for atom_id in sorted(selected)],
        "operators": [
            operator.as_dict()
            for operator in ordered_operators
            if operator.operator_id in selected_operators
        ],
        "activations": [
            activation_by_id[atom_id].as_dict()
            for atom_id in sorted(selected)
            if atom_id in activation_by_id
        ],
        "tainted_atom_ids": sorted(tainted),
    }
    provenance_digest = _sha256_text(_canonical_json(provenance_payload))
    slice_id = "world-slice:" + provenance_digest[:24]

    return WorldSlice(
        slice_id=slice_id,
        need_id=need.need_id,
        cycle_id=need.cycle_id,
        generation=need.generation,
        vector_space_version=need.vector_space_version,
        selected_atom_ids=tuple(selected),
        selected_operator_ids=tuple(selected_operators),
        unresolved_target_atom_ids=tuple(unresolved),
        tainted_atom_ids=tuple(tainted),
        depth_reached=depth_reached,
        stopped_reason=stopped_reason,
        evidence_refs=tuple(evidence_refs),
        provenance_digest=provenance_digest,
    )
