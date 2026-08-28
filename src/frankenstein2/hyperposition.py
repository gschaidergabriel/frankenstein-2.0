"""Deterministic Hyperposition primitives for Frankenstein 2.0 Stage 5.

Hyperposition preserves explicit unresolved alternatives and emits typed discriminator
candidates. It is candidate/evidence structure only. Recurrence, peer support, ranking
scores, model output, or internal agreement never mint world truth, decision authority,
effect authority, completion authority, or GRID/GWT runtime credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, ClassVar


HYPERPOSITION_SCHEMA = "FRANKENSTEIN2_HYPERPOSITION/v1"
ALTERNATIVE_SCHEMA = "FRANKENSTEIN2_HYPERPOSITION_ALTERNATIVE/v1"
DISCRIMINATOR_SCHEMA = "FRANKENSTEIN2_HYPERPOSITION_DISCRIMINATOR/v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HyperpositionError(ValueError):
    """Fail-closed validation error for Hyperposition structures."""


class EpistemicStatus(str, Enum):
    OBSERVED_EVIDENCE = "OBSERVED_EVIDENCE"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    NOT_COMPUTED = "NOT_COMPUTED"


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HyperpositionError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise HyperpositionError(f"{name} must not contain leading or trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise HyperpositionError(f"{name} must not contain control characters")
    return value


def _require_generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HyperpositionError("generation must be an integer >= 0")
    return value


def _require_nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HyperpositionError(f"{name} must be an integer >= 0")
    return value


def _require_micros(name: str, value: Any, *, allow_none: bool) -> int | None:
    if value is None:
        if allow_none:
            return None
        raise HyperpositionError(f"{name} is required")
    if isinstance(value, bool) or not isinstance(value, int):
        raise HyperpositionError(f"{name} must be an integer in [0, 1000000]")
    if not 0 <= value <= 1_000_000:
        raise HyperpositionError(f"{name} must be in [0, 1000000]")
    return value


def _require_sha256(name: str, value: Any) -> str:
    value = _require_text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise HyperpositionError(f"{name} must be a lowercase sha256 hex digest")
    return value


def _require_refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise HyperpositionError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise HyperpositionError(f"{name} must not be empty")
    refs = tuple(_require_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise HyperpositionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _require_text(name, value)


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
        raise HyperpositionError("value must be canonical-JSON encodable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class Alternative:
    alternative_id: str
    proposition_ref: str
    generation: int
    epistemic_status: EpistemicStatus
    provenance_refs: tuple[str, ...]
    support_refs: tuple[str, ...] = ()
    counterevidence_refs: tuple[str, ...] = ()
    score_micros: int | None = None
    uncertainty_micros: int | None = None
    recurrence_count: int = 0
    peer_support_count: int = 0

    schema: ClassVar[str] = ALTERNATIVE_SCHEMA
    classification: ClassVar[str] = (
        "CANDIDATE_ALTERNATIVE_NOT_WORLD_TRUTH_OR_DECISION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "alternative_id", _require_text("alternative_id", self.alternative_id))
        object.__setattr__(self, "proposition_ref", _require_text("proposition_ref", self.proposition_ref))
        _require_generation(self.generation)
        if not isinstance(self.epistemic_status, EpistemicStatus):
            raise HyperpositionError("epistemic_status must be an EpistemicStatus")
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        object.__setattr__(
            self,
            "support_refs",
            _require_refs("support_refs", self.support_refs, allow_empty=True),
        )
        object.__setattr__(
            self,
            "counterevidence_refs",
            _require_refs("counterevidence_refs", self.counterevidence_refs, allow_empty=True),
        )
        _require_micros("score_micros", self.score_micros, allow_none=True)
        _require_micros("uncertainty_micros", self.uncertainty_micros, allow_none=True)
        _require_nonnegative_int("recurrence_count", self.recurrence_count)
        _require_nonnegative_int("peer_support_count", self.peer_support_count)

        overlap = set(self.support_refs).intersection(self.counterevidence_refs)
        if overlap:
            raise HyperpositionError("support_refs and counterevidence_refs must not overlap")

        if self.epistemic_status is EpistemicStatus.NOT_COMPUTED:
            if (
                self.support_refs
                or self.counterevidence_refs
                or self.score_micros is not None
                or self.uncertainty_micros is not None
                or self.recurrence_count
                or self.peer_support_count
            ):
                raise HyperpositionError(
                    "NOT_COMPUTED alternative must not carry computed evidence, scores, "
                    "uncertainty, recurrence, or peer support"
                )

        if self.epistemic_status is EpistemicStatus.UNKNOWN and self.score_micros is not None:
            raise HyperpositionError("UNKNOWN alternative must not carry a ranking score")

        if self.epistemic_status is EpistemicStatus.CONFLICT:
            if not self.support_refs or not self.counterevidence_refs:
                raise HyperpositionError(
                    "CONFLICT alternative requires support_refs and counterevidence_refs"
                )

        if self.epistemic_status in (
            EpistemicStatus.OBSERVED_EVIDENCE,
            EpistemicStatus.INFERRED,
        ) and not self.support_refs:
            raise HyperpositionError(
                f"{self.epistemic_status.value} alternative requires support_refs"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "alternative_id": self.alternative_id,
            "proposition_ref": self.proposition_ref,
            "generation": self.generation,
            "epistemic_status": self.epistemic_status.value,
            "provenance_refs": list(self.provenance_refs),
            "support_refs": list(self.support_refs),
            "counterevidence_refs": list(self.counterevidence_refs),
            "score_micros": self.score_micros,
            "uncertainty_micros": self.uncertainty_micros,
            "recurrence_count": self.recurrence_count,
            "peer_support_count": self.peer_support_count,
            "authority_boundary": (
                "RECURRENCE_PEER_SUPPORT_SCORE_AND_MODEL_AGREEMENT_DO_NOT_MINT_TRUTH"
            ),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class Hyperposition:
    hyperposition_id: str
    generation: int
    alternatives: tuple[Alternative, ...]
    provenance_refs: tuple[str, ...]
    situation_frame_ref: str | None = None
    policy_ref: str | None = None

    schema: ClassVar[str] = HYPERPOSITION_SCHEMA
    classification: ClassVar[str] = (
        "HYPERPOSITION_CANDIDATE_SET_NOT_WORLD_TRUTH_OR_DECISION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "hyperposition_id", _require_text("hyperposition_id", self.hyperposition_id)
        )
        _require_generation(self.generation)
        if not isinstance(self.alternatives, tuple):
            raise HyperpositionError("alternatives must be an immutable tuple")
        if len(self.alternatives) < 2:
            raise HyperpositionError("Hyperposition requires at least two alternatives")
        if not all(isinstance(item, Alternative) for item in self.alternatives):
            raise HyperpositionError("alternatives must contain only Alternative values")
        for item in self.alternatives:
            if item.generation != self.generation:
                raise HyperpositionError("alternative generation mismatch")
        alternative_ids = [item.alternative_id for item in self.alternatives]
        if len(set(alternative_ids)) != len(alternative_ids):
            raise HyperpositionError("duplicate alternative_id")
        proposition_refs = [item.proposition_ref for item in self.alternatives]
        if len(set(proposition_refs)) != len(proposition_refs):
            raise HyperpositionError("duplicate proposition_ref")
        object.__setattr__(
            self,
            "alternatives",
            tuple(sorted(self.alternatives, key=lambda item: item.alternative_id)),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        object.__setattr__(
            self,
            "situation_frame_ref",
            _optional_text("situation_frame_ref", self.situation_frame_ref),
        )
        object.__setattr__(self, "policy_ref", _optional_text("policy_ref", self.policy_ref))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "hyperposition_id": self.hyperposition_id,
            "generation": self.generation,
            "alternatives": [item.as_dict() for item in self.alternatives],
            "provenance_refs": list(self.provenance_refs),
            "situation_frame_ref": self.situation_frame_ref,
            "policy_ref": self.policy_ref,
            "selection_authority": "NONE",
            "authority_boundary": (
                "MULTIPLE_ALTERNATIVES_REMAIN_UNRESOLVED_UNTIL_EVIDENCE_BEARING_DISCRIMINATION"
            ),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())

    def alternative(self, alternative_id: str) -> Alternative:
        alternative_id = _require_text("alternative_id", alternative_id)
        for item in self.alternatives:
            if item.alternative_id == alternative_id:
                return item
        raise HyperpositionError(f"unknown alternative_id: {alternative_id}")


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscriminatorCandidate:
    discriminator_id: str
    hyperposition_id: str
    hyperposition_generation: int
    hyperposition_sha256: str
    target_alternative_ids: tuple[str, ...]
    evidence_need_ref: str
    expected_information_gain_micros: int
    estimated_cost_micros: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = DISCRIMINATOR_SCHEMA
    classification: ClassVar[str] = (
        "DISCRIMINATOR_CANDIDATE_NOT_ACTION_OR_EFFECT_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "discriminator_id", _require_text("discriminator_id", self.discriminator_id)
        )
        object.__setattr__(
            self, "hyperposition_id", _require_text("hyperposition_id", self.hyperposition_id)
        )
        _require_generation(self.hyperposition_generation)
        _require_sha256("hyperposition_sha256", self.hyperposition_sha256)
        object.__setattr__(
            self,
            "target_alternative_ids",
            _require_refs(
                "target_alternative_ids",
                self.target_alternative_ids,
                allow_empty=False,
            ),
        )
        if len(self.target_alternative_ids) < 2:
            raise HyperpositionError(
                "discriminator must target at least two alternatives"
            )
        object.__setattr__(
            self, "evidence_need_ref", _require_text("evidence_need_ref", self.evidence_need_ref)
        )
        _require_micros(
            "expected_information_gain_micros",
            self.expected_information_gain_micros,
            allow_none=False,
        )
        _require_micros(
            "estimated_cost_micros", self.estimated_cost_micros, allow_none=False
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "discriminator_id": self.discriminator_id,
            "hyperposition_id": self.hyperposition_id,
            "hyperposition_generation": self.hyperposition_generation,
            "hyperposition_sha256": self.hyperposition_sha256,
            "target_alternative_ids": list(self.target_alternative_ids),
            "evidence_need_ref": self.evidence_need_ref,
            "expected_information_gain_micros": self.expected_information_gain_micros,
            "estimated_cost_micros": self.estimated_cost_micros,
            "provenance_refs": list(self.provenance_refs),
            "effect_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


def create_hyperposition(
    *,
    hyperposition_id: str,
    generation: int,
    alternatives: tuple[Alternative, ...],
    provenance_refs: tuple[str, ...],
    situation_frame_ref: str | None = None,
    policy_ref: str | None = None,
) -> Hyperposition:
    return Hyperposition(
        hyperposition_id=hyperposition_id,
        generation=generation,
        alternatives=alternatives,
        provenance_refs=provenance_refs,
        situation_frame_ref=situation_frame_ref,
        policy_ref=policy_ref,
    )


def verify_hyperposition_binding(
    state: Hyperposition,
    *,
    expected_generation: int,
    expected_state_sha256: str,
) -> None:
    if not isinstance(state, Hyperposition):
        raise HyperpositionError("state must be a Hyperposition")
    _require_generation(expected_generation)
    _require_sha256("expected_state_sha256", expected_state_sha256)
    if state.generation != expected_generation:
        raise HyperpositionError("hyperposition generation mismatch")
    if state.sha256() != expected_state_sha256:
        raise HyperpositionError("hyperposition digest mismatch")


def create_discriminator_candidate(
    *,
    state: Hyperposition,
    expected_generation: int,
    expected_state_sha256: str,
    discriminator_id: str,
    target_alternative_ids: tuple[str, ...],
    evidence_need_ref: str,
    expected_information_gain_micros: int,
    estimated_cost_micros: int,
    provenance_refs: tuple[str, ...],
) -> DiscriminatorCandidate:
    verify_hyperposition_binding(
        state,
        expected_generation=expected_generation,
        expected_state_sha256=expected_state_sha256,
    )
    normalized_targets = _require_refs(
        "target_alternative_ids", target_alternative_ids, allow_empty=False
    )
    known_ids = {item.alternative_id for item in state.alternatives}
    unknown = sorted(set(normalized_targets) - known_ids)
    if unknown:
        raise HyperpositionError(
            "discriminator targets unknown alternatives: " + ", ".join(unknown)
        )
    return DiscriminatorCandidate(
        discriminator_id=discriminator_id,
        hyperposition_id=state.hyperposition_id,
        hyperposition_generation=state.generation,
        hyperposition_sha256=state.sha256(),
        target_alternative_ids=normalized_targets,
        evidence_need_ref=evidence_need_ref,
        expected_information_gain_micros=expected_information_gain_micros,
        estimated_cost_micros=estimated_cost_micros,
        provenance_refs=provenance_refs,
    )


__all__ = [
    "ALTERNATIVE_SCHEMA",
    "DISCRIMINATOR_SCHEMA",
    "HYPERPOSITION_SCHEMA",
    "Alternative",
    "DiscriminatorCandidate",
    "EpistemicStatus",
    "Hyperposition",
    "HyperpositionError",
    "create_discriminator_candidate",
    "create_hyperposition",
    "verify_hyperposition_binding",
]
