"""Deterministic candidate-only VisualNeed planning for Frankenstein 2.0.

A VisualNeed is a bounded request for later perception. This module does not capture,
observe, infer modality, invoke a model/tool/provider, or promote a projection to truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, ClassVar

from .sparse_world_basis import WorldSlice
from .world_multiview import MultiViewOverlay

VISUAL_NEED_SCHEMA = "FRANKENSTEIN2_VISUAL_NEED/v1"
VISUAL_TARGET_SCHEMA = "FRANKENSTEIN2_VISUAL_TARGET/v1"


class VisualNeedError(ValueError):
    """Fail-closed validation error for active-sensing planning."""


class VisualReason(str, Enum):
    UNRESOLVED_TARGET = "UNRESOLVED_TARGET"
    MULTIVIEW_DISAGREEMENT = "MULTIVIEW_DISAGREEMENT"


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualNeedError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise VisualNeedError(f"{name} must not contain leading or trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise VisualNeedError(f"{name} must not contain control characters")
    return value


def _require_refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise VisualNeedError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise VisualNeedError(f"{name} must not be empty")
    refs = tuple(_require_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise VisualNeedError(f"{name} must not contain duplicates")
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
        raise VisualNeedError("value must be canonical-JSON encodable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualTarget:
    atom_id: str
    reasons: tuple[VisualReason, ...]

    schema: ClassVar[str] = VISUAL_TARGET_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_TARGET_CANDIDATE_NOT_OBSERVATION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "atom_id", _require_text("atom_id", self.atom_id))
        if not isinstance(self.reasons, tuple) or not self.reasons:
            raise VisualNeedError("reasons must be a non-empty immutable tuple")
        if any(not isinstance(reason, VisualReason) for reason in self.reasons):
            raise VisualNeedError("reasons must contain VisualReason values")
        if len(set(self.reasons)) != len(self.reasons):
            raise VisualNeedError("reasons must not contain duplicates")
        object.__setattr__(
            self,
            "reasons",
            tuple(sorted(self.reasons, key=lambda item: item.value)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "atom_id": self.atom_id,
            "reasons": [reason.value for reason in self.reasons],
            "observation": None,
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualNeed:
    visual_need_id: str
    cycle_id: str
    generation: int
    vector_space_version: str
    source_slice_id: str
    source_slice_sha256: str
    source_slice_provenance_digest: str
    source_overlay_id: str | None
    source_overlay_sha256: str | None
    targets: tuple[VisualTarget, ...]
    visualizable_atom_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    provenance_digest: str

    schema: ClassVar[str] = VISUAL_NEED_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_PERCEPTION_REQUEST_CANDIDATE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "visual_need_id": self.visual_need_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "source_slice_id": self.source_slice_id,
            "source_slice_sha256": self.source_slice_sha256,
            "source_slice_provenance_digest": self.source_slice_provenance_digest,
            "source_overlay_id": self.source_overlay_id,
            "source_overlay_sha256": self.source_overlay_sha256,
            "targets": [target.as_dict() for target in self.targets],
            "visualizable_atom_ids": list(self.visualizable_atom_ids),
            "provenance_refs": list(self.provenance_refs),
            "provenance_digest": self.provenance_digest,
            "perception_execution_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


def _validate_slice_identity(world_slice: WorldSlice) -> None:
    digest = _require_text("world_slice.provenance_digest", world_slice.provenance_digest)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise VisualNeedError("world_slice provenance_digest must be lowercase sha256 hex")
    if world_slice.slice_id != "world-slice:" + digest[:24]:
        raise VisualNeedError("world_slice slice_id/provenance_digest binding mismatch")


def plan_visual_need(
    *,
    world_slice: WorldSlice,
    visualizable_atom_ids: tuple[str, ...],
    overlay: MultiViewOverlay | None = None,
    max_targets: int = 16,
    provenance_refs: tuple[str, ...],
) -> VisualNeed | None:
    """Plan a bounded re-look request from explicit uncertainty/disagreement signals.

    The caller, not this function, declares which atoms are visually inspectable.
    If no eligible uncertain/disagreed atom intersects that declaration, returns None.
    """
    if not isinstance(world_slice, WorldSlice):
        raise VisualNeedError("world_slice must be a WorldSlice")
    _validate_slice_identity(world_slice)
    visualizable = _require_refs(
        "visualizable_atom_ids", visualizable_atom_ids, allow_empty=True
    )
    provenance = set(_require_refs("provenance_refs", provenance_refs, allow_empty=False))
    if isinstance(max_targets, bool) or not isinstance(max_targets, int) or max_targets <= 0:
        raise VisualNeedError("max_targets must be an integer > 0")

    source_slice_sha256 = world_slice.sha256()
    provenance.update(world_slice.evidence_refs)
    provenance.add(f"world-slice-sha256:{source_slice_sha256}")
    provenance.add(f"world-slice-provenance:{world_slice.provenance_digest}")

    reasons_by_atom: dict[str, set[VisualReason]] = {}
    for atom_id in world_slice.unresolved_target_atom_ids:
        reasons_by_atom.setdefault(atom_id, set()).add(VisualReason.UNRESOLVED_TARGET)

    overlay_sha256: str | None = None
    overlay_id: str | None = None
    if overlay is not None:
        if not isinstance(overlay, MultiViewOverlay):
            raise VisualNeedError("overlay must be a MultiViewOverlay or None")
        if overlay.cycle_id != world_slice.cycle_id:
            raise VisualNeedError("overlay cycle_id mismatch")
        if overlay.generation != world_slice.generation:
            raise VisualNeedError("overlay generation mismatch")
        if overlay.vector_space_version != world_slice.vector_space_version:
            raise VisualNeedError("overlay vector_space_version mismatch")
        if not any(
            slice_id == world_slice.slice_id and slice_sha256 == source_slice_sha256
            for _, slice_id, slice_sha256 in overlay.view_refs
        ):
            raise VisualNeedError("overlay does not reference the exact source WorldSlice")
        expected_overlay_id = "world-multiview:" + overlay.provenance_digest[:24]
        if overlay.overlay_id != expected_overlay_id:
            raise VisualNeedError("overlay id/provenance_digest binding mismatch")
        overlay_sha256 = overlay.sha256()
        overlay_id = overlay.overlay_id
        provenance.update(overlay.provenance_refs)
        provenance.add(f"world-multiview-sha256:{overlay_sha256}")
        provenance.add(f"world-multiview-provenance:{overlay.provenance_digest}")
        for atom_id in overlay.disagreement_atom_ids:
            reasons_by_atom.setdefault(atom_id, set()).add(
                VisualReason.MULTIVIEW_DISAGREEMENT
            )

    eligible = sorted(set(reasons_by_atom).intersection(visualizable))[:max_targets]
    if not eligible:
        return None

    targets = tuple(
        VisualTarget(atom_id=atom_id, reasons=tuple(reasons_by_atom[atom_id]))
        for atom_id in eligible
    )
    payload = {
        "cycle_id": world_slice.cycle_id,
        "generation": world_slice.generation,
        "vector_space_version": world_slice.vector_space_version,
        "source_slice_id": world_slice.slice_id,
        "source_slice_sha256": source_slice_sha256,
        "source_slice_provenance_digest": world_slice.provenance_digest,
        "source_overlay_id": overlay_id,
        "source_overlay_sha256": overlay_sha256,
        "targets": [target.as_dict() for target in targets],
        "visualizable_atom_ids": list(visualizable),
        "provenance_refs": sorted(provenance),
        "max_targets": max_targets,
    }
    provenance_digest = _sha256_text(_canonical_json(payload))
    return VisualNeed(
        visual_need_id="visual-need:" + provenance_digest[:24],
        cycle_id=world_slice.cycle_id,
        generation=world_slice.generation,
        vector_space_version=world_slice.vector_space_version,
        source_slice_id=world_slice.slice_id,
        source_slice_sha256=source_slice_sha256,
        source_slice_provenance_digest=world_slice.provenance_digest,
        source_overlay_id=overlay_id,
        source_overlay_sha256=overlay_sha256,
        targets=targets,
        visualizable_atom_ids=visualizable,
        provenance_refs=tuple(sorted(provenance)),
        provenance_digest=provenance_digest,
    )
