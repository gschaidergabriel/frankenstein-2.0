"""Temporal observation-window contracts for the Frankenstein 2.0 Perception Fabric.

This module binds exact OBSERVED percept claims to source/clock identity and constructs a
bounded, deterministic observation window. Temporal admissibility is explicit: CURRENT,
STALE, and UNALIGNED are distinct. The module never treats arrival order, a shared GRID
cycle, model agreement, or semantic agreement as evidence of real-world simultaneity.
It does not read sensors, persist raw frames, invoke providers, resolve semantic disagreement,
or mint world-truth/effect/completion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

from .epistemic_perception import EpistemicPerceptClaim

TEMPORAL_REF_SCHEMA = "FRANKENSTEIN2_TEMPORAL_PERCEPT_REF/v1"
OBSERVATION_WINDOW_SCHEMA = "FRANKENSTEIN2_OBSERVATION_WINDOW/v2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PerceptionTemporalError(ValueError):
    """Fail-closed validation error for temporal perception contracts."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionTemporalError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionTemporalError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionTemporalError(f"{name} must be an integer >= 0")
    return value


def _positive(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise PerceptionTemporalError(f"{name} must be an integer > 0")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise PerceptionTemporalError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise PerceptionTemporalError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionTemporalError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionTemporalError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class TemporalPerceptRef:
    ref_id: str
    source_id: str
    source_sequence: int
    clock_domain: str
    source_time_ns: int
    reference_offset_ns: int
    clock_uncertainty_ns: int
    max_freshness_ns: int
    observed_claim_sha256: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = TEMPORAL_REF_SCHEMA
    classification: ClassVar[str] = "TEMPORALLY_BOUND_OBSERVATION_REFERENCE_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _text("ref_id", self.ref_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_sequence", self.source_sequence)
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        _nonnegative("source_time_ns", self.source_time_ns)
        if type(self.reference_offset_ns) is not int:
            raise PerceptionTemporalError("reference_offset_ns must be an integer")
        _nonnegative("clock_uncertainty_ns", self.clock_uncertainty_ns)
        _positive("max_freshness_ns", self.max_freshness_ns)
        _sha256("observed_claim_sha256", self.observed_claim_sha256)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @property
    def reference_time_ns(self) -> int:
        value = self.source_time_ns + self.reference_offset_ns
        if value < 0:
            raise PerceptionTemporalError("normalized reference time cannot be negative")
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "ref_id": self.ref_id,
            "source_id": self.source_id,
            "source_sequence": self.source_sequence,
            "clock_domain": self.clock_domain,
            "source_time_ns": self.source_time_ns,
            "reference_offset_ns": self.reference_offset_ns,
            "reference_time_ns": self.reference_time_ns,
            "clock_uncertainty_ns": self.clock_uncertainty_ns,
            "max_freshness_ns": self.max_freshness_ns,
            "observed_claim_sha256": self.observed_claim_sha256,
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationWindow:
    window_id: str
    reference_now_ns: int
    max_join_skew_ns: int
    max_clock_uncertainty_ns: int
    current_ref_ids: tuple[str, ...]
    stale_ref_ids: tuple[str, ...]
    source_refs: tuple[tuple[str, str, str], ...]
    provenance_refs: tuple[str, ...]
    unaligned_ref_ids: tuple[str, ...] = ()

    schema: ClassVar[str] = OBSERVATION_WINDOW_SCHEMA
    classification: ClassVar[str] = "TEMPORAL_FUSION_WINDOW_NOT_WORLD_TRUTH_OR_DISAGREEMENT_RESOLUTION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _text("window_id", self.window_id))
        _nonnegative("reference_now_ns", self.reference_now_ns)
        _nonnegative("max_join_skew_ns", self.max_join_skew_ns)
        _nonnegative("max_clock_uncertainty_ns", self.max_clock_uncertainty_ns)
        object.__setattr__(self, "current_ref_ids", _refs("current_ref_ids", self.current_ref_ids, allow_empty=True))
        object.__setattr__(self, "stale_ref_ids", _refs("stale_ref_ids", self.stale_ref_ids, allow_empty=True))
        object.__setattr__(self, "unaligned_ref_ids", _refs("unaligned_ref_ids", self.unaligned_ref_ids, allow_empty=True))
        groups = (set(self.current_ref_ids), set(self.stale_ref_ids), set(self.unaligned_ref_ids))
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise PerceptionTemporalError("current, stale and unaligned refs must be disjoint")
        if type(self.source_refs) is not tuple:
            raise PerceptionTemporalError("source_refs must be an immutable tuple")
        checked: list[tuple[str, str, str]] = []
        for item in self.source_refs:
            if type(item) is not tuple or len(item) != 3:
                raise PerceptionTemporalError("source_refs items must be (source_id, ref_id, ref_sha256)")
            source_id, ref_id, ref_sha = item
            checked.append((_text("source_id", source_id), _text("ref_id", ref_id), _sha256("ref_sha256", ref_sha)))
        if len({ref_id for _, ref_id, _ in checked}) != len(checked):
            raise PerceptionTemporalError("source_refs must not repeat ref_id")
        all_ids = groups[0] | groups[1] | groups[2]
        if all_ids != {ref_id for _, ref_id, _ in checked}:
            raise PerceptionTemporalError("every source ref must have exactly one temporal disposition")
        object.__setattr__(self, "source_refs", tuple(sorted(checked)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @property
    def alignment_status(self) -> str:
        if not self.unaligned_ref_ids:
            return "ALIGNED"
        if self.current_ref_ids or self.stale_ref_ids:
            return "PARTIAL_UNALIGNED"
        return "UNALIGNED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "window_id": self.window_id,
            "reference_now_ns": self.reference_now_ns,
            "max_join_skew_ns": self.max_join_skew_ns,
            "max_clock_uncertainty_ns": self.max_clock_uncertainty_ns,
            "alignment_status": self.alignment_status,
            "current_ref_ids": list(self.current_ref_ids),
            "stale_ref_ids": list(self.stale_ref_ids),
            "unaligned_ref_ids": list(self.unaligned_ref_ids),
            "source_refs": [
                {"source_id": source_id, "ref_id": ref_id, "ref_sha256": ref_sha}
                for source_id, ref_id, ref_sha in self.source_refs
            ],
            "arrival_order_is_event_time": False,
            "same_grid_cycle_is_same_real_world_time": False,
            "unknown_or_unaligned_preserved": True,
            "resolves_semantic_disagreement": False,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_observed_claim(
    *,
    claim: EpistemicPerceptClaim,
    expected_claim_sha256: str,
    ref_id: str,
    source_id: str,
    source_sequence: int,
    clock_domain: str,
    reference_offset_ns: int,
    clock_uncertainty_ns: int,
    max_freshness_ns: int,
    provenance_refs: tuple[str, ...],
) -> TemporalPerceptRef:
    """Bind one exact OBSERVED claim to source-local and reference-clock metadata."""
    if type(claim) is not EpistemicPerceptClaim:
        raise PerceptionTemporalError("claim must be a concrete EpistemicPerceptClaim")
    _sha256("expected_claim_sha256", expected_claim_sha256)
    if claim.sha256() != expected_claim_sha256:
        raise PerceptionTemporalError("claim digest mismatch")
    if claim.epistemic_type != "OBSERVED":
        raise PerceptionTemporalError("only OBSERVED claims may enter a current observation window")
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.update(claim.provenance_refs)
    provenance.add(f"observed-claim-sha256:{expected_claim_sha256}")
    return TemporalPerceptRef(
        ref_id=ref_id,
        source_id=source_id,
        source_sequence=source_sequence,
        clock_domain=clock_domain,
        source_time_ns=claim.source_time_ns,
        reference_offset_ns=reference_offset_ns,
        clock_uncertainty_ns=clock_uncertainty_ns,
        max_freshness_ns=max_freshness_ns,
        observed_claim_sha256=expected_claim_sha256,
        provenance_refs=tuple(sorted(provenance)),
    )


def _pair_is_admissible(a: TemporalPerceptRef, b: TemporalPerceptRef, *, max_join_skew_ns: int) -> bool:
    if a.source_id == b.source_id:
        return True
    # Conservative bound: even the worst-case separation permitted by both clock-error
    # intervals must fit the declared join-skew budget.
    worst_case_separation = (
        abs(a.reference_time_ns - b.reference_time_ns)
        + a.clock_uncertainty_ns
        + b.clock_uncertainty_ns
    )
    return worst_case_separation <= max_join_skew_ns


def build_observation_window(
    *,
    refs: tuple[TemporalPerceptRef, ...],
    reference_now_ns: int,
    max_join_skew_ns: int,
    max_clock_uncertainty_ns: int,
    provenance_refs: tuple[str, ...],
) -> ObservationWindow:
    """Partition refs into CURRENT, STALE and UNALIGNED without inventing simultaneity."""
    if type(refs) is not tuple or any(type(item) is not TemporalPerceptRef for item in refs):
        raise PerceptionTemporalError("refs must be an immutable tuple of concrete TemporalPerceptRef values")
    _nonnegative("reference_now_ns", reference_now_ns)
    _nonnegative("max_join_skew_ns", max_join_skew_ns)
    _nonnegative("max_clock_uncertainty_ns", max_clock_uncertainty_ns)
    ids = [item.ref_id for item in refs]
    if len(ids) != len(set(ids)):
        raise PerceptionTemporalError("ref_id must be unique")

    by_source: dict[str, list[TemporalPerceptRef]] = {}
    for item in refs:
        by_source.setdefault(item.source_id, []).append(item)
    for source_id, source_items in by_source.items():
        ordered = sorted(source_items, key=lambda item: item.source_sequence)
        for previous, current_item in zip(ordered, ordered[1:]):
            if current_item.source_sequence <= previous.source_sequence:
                raise PerceptionTemporalError(f"source sequence must strictly increase for {source_id!r}")
            if current_item.source_time_ns < previous.source_time_ns:
                raise PerceptionTemporalError(f"source time regressed for {source_id!r}")

    current: list[TemporalPerceptRef] = []
    stale: list[TemporalPerceptRef] = []
    unaligned: list[TemporalPerceptRef] = []
    for item in refs:
        if item.clock_uncertainty_ns > max_clock_uncertainty_ns:
            unaligned.append(item)
            continue
        age = reference_now_ns - item.reference_time_ns
        if age < 0:
            unaligned.append(item)
        elif age > item.max_freshness_ns:
            stale.append(item)
        else:
            current.append(item)

    incompatible_ids: set[str] = set()
    for index, left in enumerate(current):
        for right in current[index + 1 :]:
            if not _pair_is_admissible(left, right, max_join_skew_ns=max_join_skew_ns):
                incompatible_ids.add(left.ref_id)
                incompatible_ids.add(right.ref_id)
    if incompatible_ids:
        retained: list[TemporalPerceptRef] = []
        for item in current:
            if item.ref_id in incompatible_ids:
                unaligned.append(item)
            else:
                retained.append(item)
        current = retained

    provenance = set(_refs("provenance_refs", provenance_refs))
    source_refs: list[tuple[str, str, str]] = []
    for item in refs:
        provenance.update(item.provenance_refs)
        provenance.add(f"temporal-ref-sha256:{item.sha256()}")
        source_refs.append((item.source_id, item.ref_id, item.sha256()))
    payload = {
        "reference_now_ns": reference_now_ns,
        "max_join_skew_ns": max_join_skew_ns,
        "max_clock_uncertainty_ns": max_clock_uncertainty_ns,
        "current_ref_ids": sorted(item.ref_id for item in current),
        "stale_ref_ids": sorted(item.ref_id for item in stale),
        "unaligned_ref_ids": sorted(item.ref_id for item in unaligned),
        "source_refs": sorted(source_refs),
    }
    window_id = "observation-window:" + _digest(payload)[:24]
    return ObservationWindow(
        window_id=window_id,
        reference_now_ns=reference_now_ns,
        max_join_skew_ns=max_join_skew_ns,
        max_clock_uncertainty_ns=max_clock_uncertainty_ns,
        current_ref_ids=tuple(item.ref_id for item in current),
        stale_ref_ids=tuple(item.ref_id for item in stale),
        unaligned_ref_ids=tuple(item.ref_id for item in unaligned),
        source_refs=tuple(source_refs),
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "OBSERVATION_WINDOW_SCHEMA",
    "TEMPORAL_REF_SCHEMA",
    "ObservationWindow",
    "PerceptionTemporalError",
    "TemporalPerceptRef",
    "bind_observed_claim",
    "build_observation_window",
]
