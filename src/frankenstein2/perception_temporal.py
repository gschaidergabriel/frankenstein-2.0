"""Temporal observation-window contracts for the Frankenstein 2.0 Perception Fabric.

Exact OBSERVED percepts are bound to source/clock identity and partitioned into CURRENT,
STALE, or UNALIGNED. Numeric offsets and raw witness digests never self-attest cross-clock
comparability. A raw ClockAlignmentWitness is evidence input only; distinct clock identities
are comparable only when the exact witness is selected by a separately produced
ClockAlignmentAdmissionRegistrySnapshot carrying upstream authority, generation, receipt,
and provenance identity.

This module consumes that registry result but does not mint admission authority, dereference
external receipts, read sensors, synchronize clocks, invoke providers, resolve semantic
disagreement, or mint world-truth/effect/completion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

from .epistemic_perception import EpistemicPerceptClaim
from .perception_clock_alignment_admission import (
    ClockAlignmentAdmissionRecord,
    ClockAlignmentAdmissionRegistrySnapshot,
)

TEMPORAL_REF_SCHEMA = "FRANKENSTEIN2_TEMPORAL_PERCEPT_REF/v2"
CLOCK_ALIGNMENT_WITNESS_SCHEMA = "FRANKENSTEIN2_CLOCK_ALIGNMENT_WITNESS/v1"
OBSERVATION_WINDOW_SCHEMA = "FRANKENSTEIN2_OBSERVATION_WINDOW/v5"
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


def _optional_sha256(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _sha256(name, value)


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise PerceptionTemporalError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionTemporalError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _sha_refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise PerceptionTemporalError(f"{name} must be an immutable tuple")
    refs = tuple(_sha256(f"{name} item", item) for item in value)
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
    source_generation: int = 1

    schema: ClassVar[str] = TEMPORAL_REF_SCHEMA
    classification: ClassVar[str] = "TEMPORALLY_BOUND_OBSERVATION_REFERENCE_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _text("ref_id", self.ref_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_sequence", self.source_sequence)
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        _positive("source_generation", self.source_generation)
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

    @property
    def clock_identity(self) -> tuple[str, int]:
        return (self.clock_domain, self.source_generation)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "ref_id": self.ref_id,
            "source_id": self.source_id,
            "source_sequence": self.source_sequence,
            "source_generation": self.source_generation,
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
class ClockAlignmentWitness:
    """Structural clock-relation evidence. Presence alone is never admission authority."""

    alignment_id: str
    alignment_generation: int
    left_clock_domain: str
    left_source_generation: int
    left_reference_offset_ns: int
    left_max_uncertainty_ns: int
    right_clock_domain: str
    right_source_generation: int
    right_reference_offset_ns: int
    right_max_uncertainty_ns: int
    valid_from_reference_ns: int
    valid_through_reference_ns: int
    evidence_sha256: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = CLOCK_ALIGNMENT_WITNESS_SCHEMA
    classification: ClassVar[str] = "CLOCK_RELATION_EVIDENCE_INPUT_NOT_ADMISSION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "alignment_id", _text("alignment_id", self.alignment_id))
        _positive("alignment_generation", self.alignment_generation)
        object.__setattr__(self, "left_clock_domain", _text("left_clock_domain", self.left_clock_domain))
        _positive("left_source_generation", self.left_source_generation)
        if type(self.left_reference_offset_ns) is not int:
            raise PerceptionTemporalError("left_reference_offset_ns must be an integer")
        _nonnegative("left_max_uncertainty_ns", self.left_max_uncertainty_ns)
        object.__setattr__(self, "right_clock_domain", _text("right_clock_domain", self.right_clock_domain))
        _positive("right_source_generation", self.right_source_generation)
        if type(self.right_reference_offset_ns) is not int:
            raise PerceptionTemporalError("right_reference_offset_ns must be an integer")
        _nonnegative("right_max_uncertainty_ns", self.right_max_uncertainty_ns)
        if (self.left_clock_domain, self.left_source_generation) == (
            self.right_clock_domain,
            self.right_source_generation,
        ):
            raise PerceptionTemporalError("clock alignment witness must relate two distinct clock identities")
        _nonnegative("valid_from_reference_ns", self.valid_from_reference_ns)
        _nonnegative("valid_through_reference_ns", self.valid_through_reference_ns)
        if self.valid_through_reference_ns < self.valid_from_reference_ns:
            raise PerceptionTemporalError("clock alignment witness validity interval is inverted")
        _sha256("evidence_sha256", self.evidence_sha256)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "alignment_id": self.alignment_id,
            "alignment_generation": self.alignment_generation,
            "left_clock_domain": self.left_clock_domain,
            "left_source_generation": self.left_source_generation,
            "left_reference_offset_ns": self.left_reference_offset_ns,
            "left_max_uncertainty_ns": self.left_max_uncertainty_ns,
            "right_clock_domain": self.right_clock_domain,
            "right_source_generation": self.right_source_generation,
            "right_reference_offset_ns": self.right_reference_offset_ns,
            "right_max_uncertainty_ns": self.right_max_uncertainty_ns,
            "valid_from_reference_ns": self.valid_from_reference_ns,
            "valid_through_reference_ns": self.valid_through_reference_ns,
            "evidence_sha256": self.evidence_sha256,
            "admission_authority": "NONE",
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def matches_pair(self, left: TemporalPerceptRef, right: TemporalPerceptRef) -> bool:
        orientations = (
            (
                self.left_clock_domain,
                self.left_source_generation,
                self.left_reference_offset_ns,
                self.left_max_uncertainty_ns,
                self.right_clock_domain,
                self.right_source_generation,
                self.right_reference_offset_ns,
                self.right_max_uncertainty_ns,
            ),
            (
                self.right_clock_domain,
                self.right_source_generation,
                self.right_reference_offset_ns,
                self.right_max_uncertainty_ns,
                self.left_clock_domain,
                self.left_source_generation,
                self.left_reference_offset_ns,
                self.left_max_uncertainty_ns,
            ),
        )
        for (
            left_domain,
            left_generation,
            left_offset,
            left_uncertainty,
            right_domain,
            right_generation,
            right_offset,
            right_uncertainty,
        ) in orientations:
            if (
                left.clock_domain == left_domain
                and left.source_generation == left_generation
                and left.reference_offset_ns == left_offset
                and left.clock_uncertainty_ns <= left_uncertainty
                and right.clock_domain == right_domain
                and right.source_generation == right_generation
                and right.reference_offset_ns == right_offset
                and right.clock_uncertainty_ns <= right_uncertainty
                and self.valid_from_reference_ns <= left.reference_time_ns <= self.valid_through_reference_ns
                and self.valid_from_reference_ns <= right.reference_time_ns <= self.valid_through_reference_ns
            ):
                return True
        return False


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
    alignment_witness_refs: tuple[tuple[str, str], ...] = ()
    alignment_admission_refs: tuple[tuple[str, str, str], ...] = ()
    alignment_admission_registry_sha256: str | None = None

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
        if groups[0] | groups[1] | groups[2] != {ref_id for _, ref_id, _ in checked}:
            raise PerceptionTemporalError("every source ref must have exactly one temporal disposition")
        object.__setattr__(self, "source_refs", tuple(sorted(checked)))

        if type(self.alignment_witness_refs) is not tuple:
            raise PerceptionTemporalError("alignment_witness_refs must be an immutable tuple")
        witness_refs: list[tuple[str, str]] = []
        for item in self.alignment_witness_refs:
            if type(item) is not tuple or len(item) != 2:
                raise PerceptionTemporalError("alignment_witness_refs items must be (alignment_id, witness_sha256)")
            alignment_id, witness_sha = item
            witness_refs.append((_text("alignment_id", alignment_id), _sha256("witness_sha256", witness_sha)))
        if len({alignment_id for alignment_id, _ in witness_refs}) != len(witness_refs):
            raise PerceptionTemporalError("alignment_witness_refs must not repeat alignment_id")
        object.__setattr__(self, "alignment_witness_refs", tuple(sorted(witness_refs)))

        if type(self.alignment_admission_refs) is not tuple:
            raise PerceptionTemporalError("alignment_admission_refs must be an immutable tuple")
        admission_refs: list[tuple[str, str, str]] = []
        for item in self.alignment_admission_refs:
            if type(item) is not tuple or len(item) != 3:
                raise PerceptionTemporalError(
                    "alignment_admission_refs items must be (admission_id, witness_sha256, admission_record_sha256)"
                )
            admission_id, witness_sha, admission_sha = item
            admission_refs.append(
                (
                    _text("admission_id", admission_id),
                    _sha256("admission witness_sha256", witness_sha),
                    _sha256("admission_record_sha256", admission_sha),
                )
            )
        if len({admission_id for admission_id, _, _ in admission_refs}) != len(admission_refs):
            raise PerceptionTemporalError("alignment_admission_refs must not repeat admission_id")
        witness_shas = {sha for _, sha in witness_refs}
        admitted_witness_shas = {sha for _, sha, _ in admission_refs}
        if witness_shas != admitted_witness_shas:
            raise PerceptionTemporalError("used admission records must exactly bind used witness digests")
        registry_sha = _optional_sha256(
            "alignment_admission_registry_sha256",
            self.alignment_admission_registry_sha256,
        )
        if admission_refs and registry_sha is None:
            raise PerceptionTemporalError("used alignment admissions require registry snapshot identity")
        if not admission_refs and registry_sha is not None:
            raise PerceptionTemporalError("unused registry snapshot must not appear in window causal identity")
        object.__setattr__(self, "alignment_admission_refs", tuple(sorted(admission_refs)))
        object.__setattr__(self, "alignment_admission_registry_sha256", registry_sha)
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
            "alignment_witness_refs": [
                {"alignment_id": alignment_id, "witness_sha256": witness_sha}
                for alignment_id, witness_sha in self.alignment_witness_refs
            ],
            "alignment_admission_refs": [
                {
                    "admission_id": admission_id,
                    "witness_sha256": witness_sha,
                    "admission_record_sha256": admission_sha,
                }
                for admission_id, witness_sha, admission_sha in self.alignment_admission_refs
            ],
            "alignment_admission_registry_sha256": self.alignment_admission_registry_sha256,
            "arrival_order_is_event_time": False,
            "same_grid_cycle_is_same_real_world_time": False,
            "unknown_or_unaligned_preserved": True,
            "unproven_cross_clock_is_unaligned": True,
            "numeric_reference_offset_self_attests_alignment": False,
            "raw_clock_alignment_witness_is_admission_authority": False,
            "bare_witness_digest_is_admission_authority": False,
            "requires_upstream_admission_registry": True,
            "registry_receipt_authenticated_here": False,
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
        source_generation=claim.source_generation,
        clock_domain=clock_domain,
        source_time_ns=claim.source_time_ns,
        reference_offset_ns=reference_offset_ns,
        clock_uncertainty_ns=clock_uncertainty_ns,
        max_freshness_ns=max_freshness_ns,
        observed_claim_sha256=expected_claim_sha256,
        provenance_refs=tuple(sorted(provenance)),
    )


def _matching_alignment_witness(
    a: TemporalPerceptRef,
    b: TemporalPerceptRef,
    *,
    alignment_witnesses: tuple[ClockAlignmentWitness, ...],
    alignment_admission_registry: ClockAlignmentAdmissionRegistrySnapshot | None,
) -> tuple[ClockAlignmentWitness, ClockAlignmentAdmissionRecord] | None:
    structural_matches = [witness for witness in alignment_witnesses if witness.matches_pair(a, b)]
    if len(structural_matches) != 1 or alignment_admission_registry is None:
        return None
    witness = structural_matches[0]
    admission = alignment_admission_registry.resolve_exact(
        alignment_id=witness.alignment_id,
        witness_sha256=witness.sha256(),
    )
    if admission is None:
        return None
    return (witness, admission)


def _pair_is_admissible(
    a: TemporalPerceptRef,
    b: TemporalPerceptRef,
    *,
    max_join_skew_ns: int,
    alignment_witnesses: tuple[ClockAlignmentWitness, ...],
    alignment_admission_registry: ClockAlignmentAdmissionRegistrySnapshot | None,
) -> tuple[bool, ClockAlignmentWitness | None, ClockAlignmentAdmissionRecord | None]:
    if a.source_id == b.source_id:
        same_clock = a.clock_identity == b.clock_identity
        same_transform = a.reference_offset_ns == b.reference_offset_ns
        return (same_clock and same_transform, None, None)

    witness: ClockAlignmentWitness | None = None
    admission: ClockAlignmentAdmissionRecord | None = None
    if a.clock_identity == b.clock_identity:
        if a.reference_offset_ns != b.reference_offset_ns:
            return (False, None, None)
    else:
        matched = _matching_alignment_witness(
            a,
            b,
            alignment_witnesses=alignment_witnesses,
            alignment_admission_registry=alignment_admission_registry,
        )
        if matched is None:
            return (False, None, None)
        witness, admission = matched

    worst_case_separation = (
        abs(a.reference_time_ns - b.reference_time_ns)
        + a.clock_uncertainty_ns
        + b.clock_uncertainty_ns
    )
    return (worst_case_separation <= max_join_skew_ns, witness, admission)


def build_observation_window(
    *,
    refs: tuple[TemporalPerceptRef, ...],
    reference_now_ns: int,
    max_join_skew_ns: int,
    max_clock_uncertainty_ns: int,
    provenance_refs: tuple[str, ...],
    alignment_witnesses: tuple[ClockAlignmentWitness, ...] = (),
    alignment_admission_registry: ClockAlignmentAdmissionRegistrySnapshot | None = None,
    admitted_alignment_witness_sha256s: tuple[str, ...] = (),
) -> ObservationWindow:
    """Partition refs without inventing simultaneity or locally minting witness admission.

    ``admitted_alignment_witness_sha256s`` is retained only as a fail-closed compatibility
    fence for the falsified G3 candidate API. Any non-empty value is rejected. Cross-clock
    admission must arrive through a typed upstream registry snapshot instead.
    """
    if type(refs) is not tuple or any(type(item) is not TemporalPerceptRef for item in refs):
        raise PerceptionTemporalError("refs must be an immutable tuple of concrete TemporalPerceptRef values")
    if type(alignment_witnesses) is not tuple or any(
        type(item) is not ClockAlignmentWitness for item in alignment_witnesses
    ):
        raise PerceptionTemporalError(
            "alignment_witnesses must be an immutable tuple of concrete ClockAlignmentWitness values"
        )
    witness_ids = [item.alignment_id for item in alignment_witnesses]
    if len(witness_ids) != len(set(witness_ids)):
        raise PerceptionTemporalError("alignment_witnesses must have unique alignment_id")

    legacy_digests = _sha_refs(
        "admitted_alignment_witness_sha256s",
        admitted_alignment_witness_sha256s,
    )
    if legacy_digests:
        raise PerceptionTemporalError(
            "bare caller-supplied witness digests are not independent admission authority"
        )
    if alignment_admission_registry is not None and type(alignment_admission_registry) is not ClockAlignmentAdmissionRegistrySnapshot:
        raise PerceptionTemporalError(
            "alignment_admission_registry must be None or a concrete ClockAlignmentAdmissionRegistrySnapshot"
        )

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
    used_witnesses: dict[str, ClockAlignmentWitness] = {}
    used_admissions: dict[str, ClockAlignmentAdmissionRecord] = {}
    for index, left in enumerate(current):
        for right in current[index + 1 :]:
            admissible, witness, admission = _pair_is_admissible(
                left,
                right,
                max_join_skew_ns=max_join_skew_ns,
                alignment_witnesses=alignment_witnesses,
                alignment_admission_registry=alignment_admission_registry,
            )
            if not admissible:
                incompatible_ids.add(left.ref_id)
                incompatible_ids.add(right.ref_id)
            elif witness is not None and admission is not None:
                used_witnesses[witness.alignment_id] = witness
                used_admissions[admission.admission_id] = admission
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

    witness_refs: list[tuple[str, str]] = []
    admission_refs: list[tuple[str, str, str]] = []
    registry_sha: str | None = None
    for witness in used_witnesses.values():
        witness_sha = witness.sha256()
        witness_refs.append((witness.alignment_id, witness_sha))
        provenance.update(witness.provenance_refs)
        provenance.add(f"clock-alignment-witness-sha256:{witness_sha}")

    if used_admissions:
        if alignment_admission_registry is None:
            raise PerceptionTemporalError("internal error: used admissions require registry snapshot")
        registry_sha = alignment_admission_registry.sha256()
        provenance.update(alignment_admission_registry.provenance_refs)
        provenance.add(f"clock-alignment-admission-registry-sha256:{registry_sha}")
        provenance.add(
            "clock-alignment-admission-authority:"
            f"{alignment_admission_registry.authority_id}:"
            f"{alignment_admission_registry.authority_generation}"
        )
        provenance.add(
            "clock-alignment-admission-authority-receipt-sha256:"
            f"{alignment_admission_registry.authority_receipt_sha256}"
        )
        for admission in used_admissions.values():
            admission_sha = admission.sha256()
            admission_refs.append((admission.admission_id, admission.witness_sha256, admission_sha))
            provenance.update(admission.provenance_refs)
            provenance.add(f"clock-alignment-admission-record-sha256:{admission_sha}")

    payload = {
        "reference_now_ns": reference_now_ns,
        "max_join_skew_ns": max_join_skew_ns,
        "max_clock_uncertainty_ns": max_clock_uncertainty_ns,
        "current_ref_ids": sorted(item.ref_id for item in current),
        "stale_ref_ids": sorted(item.ref_id for item in stale),
        "unaligned_ref_ids": sorted(item.ref_id for item in unaligned),
        "source_refs": sorted(source_refs),
        "alignment_witness_refs": sorted(witness_refs),
        "alignment_admission_refs": sorted(admission_refs),
        "alignment_admission_registry_sha256": registry_sha,
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
        alignment_witness_refs=tuple(witness_refs),
        alignment_admission_refs=tuple(admission_refs),
        alignment_admission_registry_sha256=registry_sha,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "CLOCK_ALIGNMENT_WITNESS_SCHEMA",
    "OBSERVATION_WINDOW_SCHEMA",
    "TEMPORAL_REF_SCHEMA",
    "ClockAlignmentWitness",
    "ObservationWindow",
    "PerceptionTemporalError",
    "TemporalPerceptRef",
    "bind_observed_claim",
    "build_observation_window",
]
