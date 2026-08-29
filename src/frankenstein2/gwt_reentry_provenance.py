"""Deterministic GWT re-entry provenance witness for Frankenstein 2.0 Stage 5.

F2-WP-508 generation 1, E3 discriminator scope only.

The witness binds one concrete GRID10 re-entry input to exact canonical F2
frame/plan/selection/broadcast identities.  Optional external trace/span metadata is
correlation-only and is deliberately excluded from canonical re-entry identity.

This component does not observe semantic uptake or causal influence, does not mint a
new causal event from an external trace identifier, does not read/write UnifiedDB,
and has no truth, effect, completion, runtime, J-Space, or training authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import CellInput, Grid10InterfaceError, Grid10Plan
from frankenstein2.gwt_workspace import BroadcastEnvelope, WorkspaceSelection

GWT_REENTRY_PROVENANCE_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_PROVENANCE_WITNESS/v1"
_REENTRY_CLASSIFICATION = (
    "DERIVED_REENTRY_PROVENANCE_WITNESS_NOT_TRUTH_UPTAKE_CAUSAL_EFFECT_OR_COMPLETION_AUTHORITY"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096


class GwtReentryProvenanceError(ValueError):
    """Fail-closed WP508 re-entry/provenance validation error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GwtReentryProvenanceError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise GwtReentryProvenanceError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtReentryProvenanceError(f"{name} contains control characters")
    return value


def _optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _text(name, value)


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise GwtReentryProvenanceError(f"{name} must be a non-negative integer")
    return value


def _positive_depth(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtReentryProvenanceError("reentry_depth must be a positive integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GwtReentryProvenanceError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtReentryProvenanceError(f"{name} must be an iterable of strings")
    items = tuple(_text(f"{name} item", item) for item in values)
    if len(items) > _MAX_REFS:
        raise GwtReentryProvenanceError(f"{name} exceeds {_MAX_REFS} items")
    if len(set(items)) != len(items):
        raise GwtReentryProvenanceError(f"{name} must not contain duplicates")
    return tuple(sorted(items))


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
        raise GwtReentryProvenanceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtReentryProvenanceWitness:
    cycle_id: str
    frame_id: str
    frame_generation: int
    frame_sha256: str
    grid_plan_id: str
    grid_plan_generation: int
    grid_plan_sha256: str
    selection_id: str
    selection_generation: int
    selection_sha256: str
    broadcast_id: str
    broadcast_generation: int
    broadcast_sha256: str
    recipient_cell_id: str
    reentry_depth: int
    reentry_input_sha256: str
    parent_ref: str | None = None
    root_ref: str | None = None
    link_refs: tuple[str, ...] = ()
    external_trace_id: str | None = None
    external_span_id: str | None = None

    schema = GWT_REENTRY_PROVENANCE_SCHEMA
    classification = _REENTRY_CLASSIFICATION

    def __post_init__(self) -> None:
        for name in (
            "cycle_id",
            "frame_id",
            "grid_plan_id",
            "selection_id",
            "broadcast_id",
            "recipient_cell_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "frame_generation",
            "grid_plan_generation",
            "selection_generation",
            "broadcast_generation",
        ):
            _generation(name, getattr(self, name))
        for name in (
            "frame_sha256",
            "grid_plan_sha256",
            "selection_sha256",
            "broadcast_sha256",
            "reentry_input_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        _positive_depth(self.reentry_depth)
        object.__setattr__(self, "parent_ref", _optional_text("parent_ref", self.parent_ref))
        object.__setattr__(self, "root_ref", _optional_text("root_ref", self.root_ref))
        object.__setattr__(self, "link_refs", _refs("link_refs", self.link_refs))
        if self.parent_ref is not None and self.parent_ref in self.link_refs:
            raise GwtReentryProvenanceError("parent_ref must not be duplicated in link_refs")
        if self.root_ref is not None and self.root_ref in self.link_refs:
            raise GwtReentryProvenanceError("root_ref must not be duplicated in link_refs")
        object.__setattr__(
            self,
            "external_trace_id",
            _optional_text("external_trace_id", self.external_trace_id),
        )
        object.__setattr__(
            self,
            "external_span_id",
            _optional_text("external_span_id", self.external_span_id),
        )
        external_fields = (self.external_trace_id, self.external_span_id)
        if any(value is not None for value in external_fields) and not all(
            value is not None for value in external_fields
        ):
            raise GwtReentryProvenanceError(
                "external trace witness must provide trace_id and span_id together"
            )

    def canonical_identity_dict(self) -> dict[str, Any]:
        """Canonical re-entry identity; external/projection lineage cannot mint a new event."""
        return {
            "schema": self.schema,
            "cycle_id": self.cycle_id,
            "frame_id": self.frame_id,
            "frame_generation": self.frame_generation,
            "frame_sha256": self.frame_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_generation": self.grid_plan_generation,
            "grid_plan_sha256": self.grid_plan_sha256,
            "selection_id": self.selection_id,
            "selection_generation": self.selection_generation,
            "selection_sha256": self.selection_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_generation": self.broadcast_generation,
            "broadcast_sha256": self.broadcast_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "reentry_depth": self.reentry_depth,
            "reentry_input_sha256": self.reentry_input_sha256,
        }

    def canonical_reentry_key(self) -> str:
        return _digest(self.canonical_identity_dict())

    def lineage_refs(self) -> tuple[str, ...]:
        refs = [ref for ref in (self.parent_ref, self.root_ref) if ref is not None]
        refs.extend(self.link_refs)
        return tuple(sorted(set(refs)))

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.canonical_identity_dict(),
            "classification": self.classification,
            "canonical_reentry_key": self.canonical_reentry_key(),
            "parent_ref": self.parent_ref,
            "root_ref": self.root_ref,
            "link_refs": list(self.link_refs),
            "external_trace_witness": (
                None
                if self.external_trace_id is None
                else {
                    "trace_id": self.external_trace_id,
                    "span_id": self.external_span_id,
                    "authority": "CORRELATION_ONLY_NONCANONICAL",
                }
            ),
            "truth_authority": "NONE",
            "uptake_claim": "NOT_OBSERVED_BY_WP508_E3_WITNESS",
            "causal_influence_claim": "NOT_OBSERVED_BY_WP508_E3_WITNESS",
            "effect_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_exact_object_lineage(
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
) -> None:
    if type(plan) is not Grid10Plan:
        raise GwtReentryProvenanceError("plan must be concrete Grid10Plan")
    if type(selection) is not WorkspaceSelection:
        raise GwtReentryProvenanceError("selection must be concrete WorkspaceSelection")
    if type(broadcast) is not BroadcastEnvelope:
        raise GwtReentryProvenanceError("broadcast must be concrete BroadcastEnvelope")
    if type(cell_input) is not CellInput:
        raise GwtReentryProvenanceError("cell_input must be concrete CellInput")
    try:
        plan.validate_input(cell_input)
    except Grid10InterfaceError as exc:
        raise GwtReentryProvenanceError(f"invalid GRID10 re-entry input: {exc}") from exc
    if cell_input.reentry_depth < 1:
        raise GwtReentryProvenanceError("cell_input is not a re-entry: reentry_depth must be positive")
    plan_sha256 = plan.sha256()
    if selection.cycle_id != plan.cycle_id:
        raise GwtReentryProvenanceError("selection cycle binding mismatch")
    if (
        selection.grid_plan_id != plan.plan_id
        or selection.grid_plan_generation != plan.generation
        or selection.grid_plan_sha256 != plan_sha256
    ):
        raise GwtReentryProvenanceError("selection GRID10 plan binding mismatch")
    if (
        selection.frame_id != plan.frame_id
        or selection.frame_generation != plan.frame_generation
        or selection.frame_sha256 != plan.frame_sha256
    ):
        raise GwtReentryProvenanceError("selection SituationFrame binding mismatch")
    if broadcast.cycle_id != selection.cycle_id:
        raise GwtReentryProvenanceError("broadcast cycle binding mismatch")
    if (
        broadcast.selection_id != selection.selection_id
        or broadcast.selection_generation != selection.generation
        or broadcast.selection_sha256 != selection.sha256()
    ):
        raise GwtReentryProvenanceError("broadcast selection binding mismatch")
    if (
        broadcast.plan_id != plan.plan_id
        or broadcast.plan_generation != plan.generation
        or broadcast.plan_sha256 != plan_sha256
    ):
        raise GwtReentryProvenanceError("broadcast GRID10 plan binding mismatch")
    if cell_input.cell_id not in broadcast.recipient_cell_ids:
        raise GwtReentryProvenanceError("cross-recipient re-entry is not addressed by broadcast")


def validate_reentry_witness(
    witness: GwtReentryProvenanceWitness,
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
    known_lineage_refs: Iterable[str] = (),
) -> None:
    """Validate one witness against exact current F2 objects, never external trace authority."""
    if type(witness) is not GwtReentryProvenanceWitness:
        raise GwtReentryProvenanceError(
            "witness must be concrete GwtReentryProvenanceWitness"
        )
    _assert_exact_object_lineage(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    expected = {
        "cycle_id": plan.cycle_id,
        "frame_id": plan.frame_id,
        "frame_generation": plan.frame_generation,
        "frame_sha256": plan.frame_sha256,
        "grid_plan_id": plan.plan_id,
        "grid_plan_generation": plan.generation,
        "grid_plan_sha256": plan.sha256(),
        "selection_id": selection.selection_id,
        "selection_generation": selection.generation,
        "selection_sha256": selection.sha256(),
        "broadcast_id": broadcast.broadcast_id,
        "broadcast_generation": broadcast.generation,
        "broadcast_sha256": broadcast.sha256(),
        "recipient_cell_id": cell_input.cell_id,
        "reentry_depth": cell_input.reentry_depth,
        "reentry_input_sha256": cell_input.sha256(),
    }
    for field, expected_value in expected.items():
        if getattr(witness, field) != expected_value:
            if field.endswith("sha256"):
                label = field.removesuffix("_sha256").replace("_", " ")
                raise GwtReentryProvenanceError(f"{label} digest mismatch")
            if field.endswith("generation"):
                label = field.removesuffix("_generation").replace("_", " ")
                raise GwtReentryProvenanceError(f"{label} generation mismatch")
            raise GwtReentryProvenanceError(f"{field.replace('_', ' ')} mismatch")
    known = set(_refs("known_lineage_refs", known_lineage_refs))
    unresolved = set(witness.lineage_refs()).difference(known)
    if unresolved:
        raise GwtReentryProvenanceError(
            "orphan lineage reference(s): " + ", ".join(sorted(unresolved))
        )


def build_reentry_witness(
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
    parent_ref: str | None = None,
    root_ref: str | None = None,
    link_refs: Iterable[str] = (),
    known_lineage_refs: Iterable[str] = (),
    external_trace_id: str | None = None,
    external_span_id: str | None = None,
) -> GwtReentryProvenanceWitness:
    _assert_exact_object_lineage(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    value = GwtReentryProvenanceWitness(
        cycle_id=plan.cycle_id,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        selection_id=selection.selection_id,
        selection_generation=selection.generation,
        selection_sha256=selection.sha256(),
        broadcast_id=broadcast.broadcast_id,
        broadcast_generation=broadcast.generation,
        broadcast_sha256=broadcast.sha256(),
        recipient_cell_id=cell_input.cell_id,
        reentry_depth=cell_input.reentry_depth,
        reentry_input_sha256=cell_input.sha256(),
        parent_ref=parent_ref,
        root_ref=root_ref,
        link_refs=tuple(link_refs),
        external_trace_id=external_trace_id,
        external_span_id=external_span_id,
    )
    validate_reentry_witness(
        value,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        known_lineage_refs=known_lineage_refs,
    )
    return value


def assert_unique_canonical_reentries(
    witnesses: Iterable[GwtReentryProvenanceWitness],
) -> tuple[str, ...]:
    """Reject replay aliases even when external trace/span metadata differs."""
    keys: list[str] = []
    seen: set[str] = set()
    for witness in witnesses:
        if type(witness) is not GwtReentryProvenanceWitness:
            raise GwtReentryProvenanceError(
                "all witnesses must be concrete GwtReentryProvenanceWitness objects"
            )
        key = witness.canonical_reentry_key()
        if key in seen:
            raise GwtReentryProvenanceError(
                "replay alias: duplicate canonical re-entry identity"
            )
        seen.add(key)
        keys.append(key)
    return tuple(keys)
