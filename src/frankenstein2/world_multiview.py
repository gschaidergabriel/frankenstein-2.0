"""Deterministic multi-view overlay/disagreement primitives for Frankenstein 2.0.

This module compares bounded noncanonical ``WorldSlice`` projections. It preserves
per-view epistemic states and provenance; it never selects a winner or promotes a
projection, agreement, confidence, or majority to world truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, ClassVar

from .sparse_world_basis import KnowledgeState, WorldSlice

VIEW_ATOM_STATE_SCHEMA = "FRANKENSTEIN2_VIEW_ATOM_STATE/v1"
WORLD_VIEW_SCHEMA = "FRANKENSTEIN2_WORLD_VIEW/v1"
ATOM_OVERLAY_SCHEMA = "FRANKENSTEIN2_ATOM_OVERLAY/v1"
MULTIVIEW_OVERLAY_SCHEMA = "FRANKENSTEIN2_MULTIVIEW_OVERLAY/v1"


class MultiViewError(ValueError):
    """Fail-closed validation error for multi-view comparison."""


class AtomOverlayStatus(str, Enum):
    VIEW_ONLY = "VIEW_ONLY"
    PARTIAL_AGREEMENT = "PARTIAL_AGREEMENT"
    PARTIAL_DISAGREEMENT = "PARTIAL_DISAGREEMENT"
    FULL_AGREEMENT = "FULL_AGREEMENT"
    FULL_DISAGREEMENT = "FULL_DISAGREEMENT"


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiViewError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise MultiViewError(f"{name} must not contain leading or trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise MultiViewError(f"{name} must not contain control characters")
    return value


def _require_refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise MultiViewError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise MultiViewError(f"{name} must not be empty")
    refs = tuple(_require_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise MultiViewError(f"{name} must not contain duplicates")
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
        raise MultiViewError("value must be canonical-JSON encodable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ViewAtomState:
    atom_id: str
    knowledge_state: KnowledgeState
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = VIEW_ATOM_STATE_SCHEMA
    classification: ClassVar[str] = "EXPLICIT_VIEW_STATE_NOT_TRUTH_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "atom_id", _require_text("atom_id", self.atom_id))
        if not isinstance(self.knowledge_state, KnowledgeState):
            raise MultiViewError("knowledge_state must be a KnowledgeState")
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
            "knowledge_state": self.knowledge_state.value,
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class WorldView:
    view_id: str
    world_slice: WorldSlice
    atom_states: tuple[ViewAtomState, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = WORLD_VIEW_SCHEMA
    classification: ClassVar[str] = "BOUND_NONCANONICAL_WORLD_VIEW"

    def __post_init__(self) -> None:
        object.__setattr__(self, "view_id", _require_text("view_id", self.view_id))
        if not isinstance(self.world_slice, WorldSlice):
            raise MultiViewError("world_slice must be a WorldSlice")
        if not isinstance(self.atom_states, tuple):
            raise MultiViewError("atom_states must be an immutable tuple")
        if not self.atom_states:
            raise MultiViewError("atom_states must not be empty")
        if any(not isinstance(item, ViewAtomState) for item in self.atom_states):
            raise MultiViewError("atom_states must contain ViewAtomState values")
        atom_ids = tuple(item.atom_id for item in self.atom_states)
        if len(set(atom_ids)) != len(atom_ids):
            raise MultiViewError("atom_states must not repeat atom_id")
        selected = set(self.world_slice.selected_atom_ids)
        observed = set(atom_ids)
        if observed != selected:
            missing = sorted(selected - observed)
            extra = sorted(observed - selected)
            raise MultiViewError(
                "atom_states must exactly cover selected_atom_ids; "
                f"missing={missing}; extra={extra}"
            )
        digest = _require_text("world_slice.provenance_digest", self.world_slice.provenance_digest)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise MultiViewError("world_slice provenance_digest must be lowercase sha256 hex")
        expected_slice_id = "world-slice:" + digest[:24]
        if self.world_slice.slice_id != expected_slice_id:
            raise MultiViewError("world_slice slice_id/provenance_digest binding mismatch")
        object.__setattr__(
            self,
            "atom_states",
            tuple(sorted(self.atom_states, key=lambda item: item.atom_id)),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    def slice_sha256(self) -> str:
        return self.world_slice.sha256()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "view_id": self.view_id,
            "slice_id": self.world_slice.slice_id,
            "slice_sha256": self.slice_sha256(),
            "slice_provenance_digest": self.world_slice.provenance_digest,
            "cycle_id": self.world_slice.cycle_id,
            "generation": self.world_slice.generation,
            "vector_space_version": self.world_slice.vector_space_version,
            "selected_atom_ids": list(self.world_slice.selected_atom_ids),
            "atom_states": [item.as_dict() for item in self.atom_states],
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AtomOverlay:
    atom_id: str
    status: AtomOverlayStatus
    states_by_view: tuple[tuple[str, KnowledgeState], ...]

    schema: ClassVar[str] = ATOM_OVERLAY_SCHEMA
    classification: ClassVar[str] = "DISAGREEMENT_PRESERVING_COMPARISON"

    def __post_init__(self) -> None:
        object.__setattr__(self, "atom_id", _require_text("atom_id", self.atom_id))
        if not isinstance(self.status, AtomOverlayStatus):
            raise MultiViewError("status must be an AtomOverlayStatus")
        if not isinstance(self.states_by_view, tuple) or not self.states_by_view:
            raise MultiViewError("states_by_view must be a non-empty immutable tuple")
        checked: list[tuple[str, KnowledgeState]] = []
        for item in self.states_by_view:
            if not isinstance(item, tuple) or len(item) != 2:
                raise MultiViewError("states_by_view items must be (view_id, KnowledgeState)")
            view_id, state = item
            checked_view_id = _require_text("states_by_view view_id", view_id)
            if not isinstance(state, KnowledgeState):
                raise MultiViewError("states_by_view state must be a KnowledgeState")
            checked.append((checked_view_id, state))
        if len({view_id for view_id, _ in checked}) != len(checked):
            raise MultiViewError("states_by_view must not repeat view_id")
        object.__setattr__(self, "states_by_view", tuple(sorted(checked)))

    @property
    def presence_count(self) -> int:
        return len(self.states_by_view)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "atom_id": self.atom_id,
            "status": self.status.value,
            "presence_count": self.presence_count,
            "states_by_view": [
                {"view_id": view_id, "knowledge_state": state.value}
                for view_id, state in self.states_by_view
            ],
            "winner": None,
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class MultiViewOverlay:
    overlay_id: str
    cycle_id: str
    generation: int
    vector_space_version: str
    view_refs: tuple[tuple[str, str, str], ...]
    atom_overlays: tuple[AtomOverlay, ...]
    disagreement_atom_ids: tuple[str, ...]
    view_only_atom_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    provenance_digest: str

    schema: ClassVar[str] = MULTIVIEW_OVERLAY_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_MULTIVIEW_COMPARISON"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "overlay_id": self.overlay_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "view_refs": [
                {
                    "view_id": view_id,
                    "slice_id": slice_id,
                    "slice_sha256": slice_sha256,
                }
                for view_id, slice_id, slice_sha256 in self.view_refs
            ],
            "atom_overlays": [item.as_dict() for item in self.atom_overlays],
            "disagreement_atom_ids": list(self.disagreement_atom_ids),
            "view_only_atom_ids": list(self.view_only_atom_ids),
            "provenance_refs": list(self.provenance_refs),
            "provenance_digest": self.provenance_digest,
            "winner_view_id": None,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


def compare_world_views(*, views: tuple[WorldView, ...]) -> MultiViewOverlay:
    """Compare bounded world views without resolving disagreement into truth."""
    if not isinstance(views, tuple) or len(views) < 2:
        raise MultiViewError("views must contain at least two WorldView values")
    if any(not isinstance(view, WorldView) for view in views):
        raise MultiViewError("views must contain WorldView values")

    ordered_views = tuple(sorted(views, key=lambda item: item.view_id))
    view_ids = tuple(view.view_id for view in ordered_views)
    if len(set(view_ids)) != len(view_ids):
        raise MultiViewError("views must not repeat view_id")

    first = ordered_views[0].world_slice
    for view in ordered_views[1:]:
        current = view.world_slice
        if current.cycle_id != first.cycle_id:
            raise MultiViewError("all views must bind the same cycle_id")
        if current.generation != first.generation:
            raise MultiViewError("all views must bind the same generation")
        if current.vector_space_version != first.vector_space_version:
            raise MultiViewError("all views must bind the same vector_space_version")

    slice_hashes = tuple(view.slice_sha256() for view in ordered_views)
    if len(set(slice_hashes)) != len(slice_hashes):
        raise MultiViewError("views must not duplicate the same exact WorldSlice")

    state_maps = {
        view.view_id: {item.atom_id: item for item in view.atom_states}
        for view in ordered_views
    }
    atom_ids = sorted({atom_id for state_map in state_maps.values() for atom_id in state_map})
    overlays: list[AtomOverlay] = []
    disagreement: list[str] = []
    view_only: list[str] = []

    for atom_id in atom_ids:
        states = tuple(
            (view_id, state_maps[view_id][atom_id].knowledge_state)
            for view_id in view_ids
            if atom_id in state_maps[view_id]
        )
        unique_states = {state for _, state in states}
        if len(states) == 1:
            status = AtomOverlayStatus.VIEW_ONLY
            view_only.append(atom_id)
        elif len(unique_states) == 1:
            status = (
                AtomOverlayStatus.FULL_AGREEMENT
                if len(states) == len(ordered_views)
                else AtomOverlayStatus.PARTIAL_AGREEMENT
            )
        else:
            status = (
                AtomOverlayStatus.FULL_DISAGREEMENT
                if len(states) == len(ordered_views)
                else AtomOverlayStatus.PARTIAL_DISAGREEMENT
            )
            disagreement.append(atom_id)
        overlays.append(AtomOverlay(atom_id=atom_id, status=status, states_by_view=states))

    provenance_refs: set[str] = set()
    for view in ordered_views:
        provenance_refs.update(view.provenance_refs)
        provenance_refs.update(view.world_slice.evidence_refs)
        provenance_refs.add(f"world-slice-sha256:{view.slice_sha256()}")
        provenance_refs.add(f"world-slice-provenance:{view.world_slice.provenance_digest}")
        for atom_state in view.atom_states:
            provenance_refs.update(atom_state.provenance_refs)

    view_refs = tuple(
        (view.view_id, view.world_slice.slice_id, view.slice_sha256()) for view in ordered_views
    )
    payload = {
        "cycle_id": first.cycle_id,
        "generation": first.generation,
        "vector_space_version": first.vector_space_version,
        "views": [view.as_dict() for view in ordered_views],
        "atom_overlays": [item.as_dict() for item in overlays],
        "provenance_refs": sorted(provenance_refs),
    }
    provenance_digest = _sha256_text(_canonical_json(payload))
    return MultiViewOverlay(
        overlay_id="world-multiview:" + provenance_digest[:24],
        cycle_id=first.cycle_id,
        generation=first.generation,
        vector_space_version=first.vector_space_version,
        view_refs=view_refs,
        atom_overlays=tuple(overlays),
        disagreement_atom_ids=tuple(sorted(disagreement)),
        view_only_atom_ids=tuple(sorted(view_only)),
        provenance_refs=tuple(sorted(provenance_refs)),
        provenance_digest=provenance_digest,
    )
