"""Deterministic whole-persistent-loop causal binding for Frankenstein 2.0.

F2-WP-900 generation 1, repository-component scope only.

This module does not execute providers, tools, external effects, or schedulers.  It
revalidates an exact persistent-checkpoint -> GRID10/GWT -> typed effect-outcome
re-entry -> successor-checkpoint chain from already bounded components.

It mints no world truth, completion authority, target-runtime credit, physical GRID10
credit, provider/model credit, training credit, or whole-system acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from frankenstein2.effect_executor_interlock import InterlockResult
from frankenstein2.effect_invocation_correlation import EffectCorrelationStage
from frankenstein2.grid10_interface import Grid10Plan
from frankenstein2.gwt_causal_path import (
    GwtCausalPathSeal,
    ReentryEvidenceBundle,
    seal_gwt_causal_path,
)
from frankenstein2.gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    CellUptakeReceipt,
    UptakeSummary,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope, WorkspaceSelection

WHOLE_LOOP_SCHEMA = "FRANKENSTEIN2_WHOLE_PERSISTENT_LOOP_SEAL/v1"
EFFECT_REENTRY_SCHEMA = "FRANKENSTEIN2_EFFECT_OUTCOME_REENTRY/v1"

EFFECT_VERIFIED = "VERIFIED_EFFECT_OUTCOME"
EFFECT_NO_EFFECT = "NO_EFFECT_DISPATCHED"
EFFECT_UNKNOWN = "UNKNOWN_EFFECT_OUTCOME"

_ALLOWED_EFFECT_STATUSES = frozenset({EFFECT_VERIFIED, EFFECT_NO_EFFECT, EFFECT_UNKNOWN})
_KNOWN_GWT_PATHS = frozenset(
    {
        "CONTRACT_SCOPE_CAUSAL_PATH_SEALED",
        "NO_CAUSAL_INFLUENCE_PATH_SEALED",
    }
)
_MAX_REFS = 4096


class WholePersistentLoopError(ValueError):
    """Fail-closed WP900 integration error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise WholePersistentLoopError(f"{name} must be a non-empty trimmed string")
    if len(value) > 1024:
        raise WholePersistentLoopError(f"{name} exceeds 1024 characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise WholePersistentLoopError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise WholePersistentLoopError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise WholePersistentLoopError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WholePersistentLoopError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise WholePersistentLoopError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS:
        raise WholePersistentLoopError(f"provenance_refs exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise WholePersistentLoopError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_projection(name: str, checkpoint: Any) -> dict[str, Any]:
    if type(checkpoint).__module__ != "frankenstein2.persistent_agency_kernel":
        raise WholePersistentLoopError(
            f"{name} must be a concrete persistent_agency_kernel checkpoint"
        )
    for attr in ("checkpoint_id", "previous_checkpoint_id", "generation", "sha256", "as_dict"):
        if not hasattr(checkpoint, attr):
            raise WholePersistentLoopError(f"{name} lacks {attr}")
    checkpoint_id = _text(f"{name}.checkpoint_id", checkpoint.checkpoint_id)
    generation = _generation(f"{name}.generation", checkpoint.generation)
    digest = _sha256(f"{name}.sha256", checkpoint.sha256())
    payload = checkpoint.as_dict()
    if not isinstance(payload, dict):
        raise WholePersistentLoopError(f"{name}.as_dict() must return a JSON object")
    if payload.get("checkpoint_id") != checkpoint_id:
        raise WholePersistentLoopError(f"{name} checkpoint identity payload mismatch")
    if payload.get("generation") != generation:
        raise WholePersistentLoopError(f"{name} generation payload mismatch")
    provenance = payload.get("provenance_refs")
    if not isinstance(provenance, list) or any(not isinstance(item, str) for item in provenance):
        raise WholePersistentLoopError(f"{name} provenance_refs payload invalid")
    return {
        "checkpoint_id": checkpoint_id,
        "previous_checkpoint_id": checkpoint.previous_checkpoint_id,
        "generation": generation,
        "sha256": digest,
        "provenance_refs": tuple(provenance),
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectOutcomeReentry:
    """Typed derived re-entry evidence; never an effect authority or journal."""

    cycle_id: str
    generation: int
    status: str
    outcome_ref: str
    effect_id: str | None
    result_id: str | None
    result_sha256: str | None
    gate_decision_id: str | None
    authority_ref: str | None
    provenance_refs: tuple[str, ...]

    schema = EFFECT_REENTRY_SCHEMA
    classification = "DERIVED_EFFECT_OUTCOME_REENTRY_NOT_EFFECT_AUTHORITY_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        if self.status not in _ALLOWED_EFFECT_STATUSES:
            raise WholePersistentLoopError("unsupported effect outcome re-entry status")
        object.__setattr__(self, "outcome_ref", _text("outcome_ref", self.outcome_ref))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))
        if self.status == EFFECT_VERIFIED:
            object.__setattr__(self, "effect_id", _text("effect_id", self.effect_id))
            object.__setattr__(self, "result_id", _text("result_id", self.result_id))
            object.__setattr__(
                self, "result_sha256", _sha256("result_sha256", self.result_sha256)
            )
            object.__setattr__(
                self, "gate_decision_id", _text("gate_decision_id", self.gate_decision_id)
            )
            object.__setattr__(self, "authority_ref", _text("authority_ref", self.authority_ref))
        elif self.status == EFFECT_NO_EFFECT:
            if self.effect_id is not None or self.result_id is not None or self.result_sha256 is not None:
                raise WholePersistentLoopError("NO_EFFECT outcome must not claim effect result")
            object.__setattr__(
                self, "gate_decision_id", _text("gate_decision_id", self.gate_decision_id)
            )
            object.__setattr__(self, "authority_ref", _text("authority_ref", self.authority_ref))
        else:
            if self.result_id is not None or self.result_sha256 is not None:
                raise WholePersistentLoopError("UNKNOWN outcome must not claim a result")

    @classmethod
    def from_interlock(
        cls,
        interlock: InterlockResult,
        *,
        cycle_id: str,
        generation: int,
        provenance_refs: Iterable[str],
    ) -> "EffectOutcomeReentry":
        if type(interlock) is not InterlockResult:
            raise WholePersistentLoopError("interlock must be concrete InterlockResult")
        refs = tuple(provenance_refs) + (
            f"effect-authority:{interlock.authority_ref}",
            f"effect-decision:{interlock.gate_decision_id}",
        )
        if not interlock.dispatched:
            if interlock.observed is not None:
                raise WholePersistentLoopError("blocked interlock must not carry POST observation")
            return cls(
                cycle_id=cycle_id,
                generation=generation,
                status=EFFECT_NO_EFFECT,
                outcome_ref=f"effect-decision:{interlock.gate_decision_id}:NO_EFFECT",
                effect_id=None,
                result_id=None,
                result_sha256=None,
                gate_decision_id=interlock.gate_decision_id,
                authority_ref=interlock.authority_ref,
                provenance_refs=refs,
            )

        observed = interlock.observed
        if observed is None or observed.stage is not EffectCorrelationStage.RESULT_OBSERVED:
            raise WholePersistentLoopError(
                "dispatched interlock requires exact RESULT_OBSERVED binding"
            )
        if observed.result_id is None or observed.result_sha256 is None:
            raise WholePersistentLoopError("observed effect lacks result identity")
        return cls(
            cycle_id=cycle_id,
            generation=generation,
            status=EFFECT_VERIFIED,
            outcome_ref=f"effect-result:{observed.result_id}:{observed.result_sha256}",
            effect_id=observed.effect_id,
            result_id=observed.result_id,
            result_sha256=observed.result_sha256,
            gate_decision_id=interlock.gate_decision_id,
            authority_ref=interlock.authority_ref,
            provenance_refs=refs,
        )

    @classmethod
    def unknown(
        cls,
        *,
        cycle_id: str,
        generation: int,
        outcome_ref: str,
        effect_id: str | None,
        provenance_refs: Iterable[str],
    ) -> "EffectOutcomeReentry":
        return cls(
            cycle_id=cycle_id,
            generation=generation,
            status=EFFECT_UNKNOWN,
            outcome_ref=outcome_ref,
            effect_id=effect_id,
            result_id=None,
            result_sha256=None,
            gate_decision_id=None,
            authority_ref=None,
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "status": self.status,
            "outcome_ref": self.outcome_ref,
            "effect_id": self.effect_id,
            "result_id": self.result_id,
            "result_sha256": self.result_sha256,
            "gate_decision_id": self.gate_decision_id,
            "authority_ref": self.authority_ref,
            "provenance_refs": list(self.provenance_refs),
            "effect_authority": "NONE",
            "replay_authority": "NONE",
            "world_truth_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class WholePersistentLoopSeal:
    seal_id: str
    cycle_id: str
    start_checkpoint_id: str
    start_checkpoint_generation: int
    start_checkpoint_sha256: str
    grid_plan_id: str
    grid_plan_generation: int
    grid_plan_sha256: str
    gwt_seal_id: str
    gwt_seal_sha256: str
    gwt_path_status: str
    effect_outcome_ref: str
    effect_outcome_sha256: str
    effect_outcome_status: str
    next_checkpoint_id: str
    next_checkpoint_generation: int
    next_checkpoint_sha256: str
    provenance_refs: tuple[str, ...]

    schema = WHOLE_LOOP_SCHEMA
    classification = "DERIVED_WHOLE_LOOP_COMPONENT_SEAL_NOT_RUNTIME_OR_WHOLE_SYSTEM_ACCEPTANCE"

    def __post_init__(self) -> None:
        for name in (
            "seal_id",
            "cycle_id",
            "start_checkpoint_id",
            "grid_plan_id",
            "gwt_seal_id",
            "effect_outcome_ref",
            "next_checkpoint_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "start_checkpoint_generation",
            "grid_plan_generation",
            "next_checkpoint_generation",
        ):
            object.__setattr__(self, name, _generation(name, getattr(self, name)))
        for name in (
            "start_checkpoint_sha256",
            "grid_plan_sha256",
            "gwt_seal_sha256",
            "effect_outcome_sha256",
            "next_checkpoint_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.gwt_path_status not in _KNOWN_GWT_PATHS:
            raise WholePersistentLoopError("whole-loop seal requires known non-UNKNOWN GWT path")
        if self.effect_outcome_status not in {EFFECT_VERIFIED, EFFECT_NO_EFFECT}:
            raise WholePersistentLoopError("whole-loop seal cannot close on UNKNOWN effect outcome")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "seal_id": self.seal_id,
            "cycle_id": self.cycle_id,
            "start_checkpoint_id": self.start_checkpoint_id,
            "start_checkpoint_generation": self.start_checkpoint_generation,
            "start_checkpoint_sha256": self.start_checkpoint_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_generation": self.grid_plan_generation,
            "grid_plan_sha256": self.grid_plan_sha256,
            "gwt_seal_id": self.gwt_seal_id,
            "gwt_seal_sha256": self.gwt_seal_sha256,
            "gwt_path_status": self.gwt_path_status,
            "effect_outcome_ref": self.effect_outcome_ref,
            "effect_outcome_sha256": self.effect_outcome_sha256,
            "effect_outcome_status": self.effect_outcome_status,
            "next_checkpoint_id": self.next_checkpoint_id,
            "next_checkpoint_generation": self.next_checkpoint_generation,
            "next_checkpoint_sha256": self.next_checkpoint_sha256,
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "target_runtime_credit": 0,
            "physical_grid10_credit": 0,
            "provider_model_credit": 0,
            "training_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def seal_whole_persistent_loop(
    *,
    seal_id: str,
    start_checkpoint: Any,
    next_checkpoint: Any,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    receipts: tuple[CellUptakeReceipt, ...],
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    causal_result: CausalInfluenceResult,
    reentry_bundles: tuple[ReentryEvidenceBundle, ...],
    gwt_seal_id: str,
    gwt_provenance_refs: Iterable[str],
    effect_outcome: EffectOutcomeReentry,
    provenance_refs: Iterable[str],
) -> WholePersistentLoopSeal:
    """Seal one exact deterministic repository-component loop.

    The factory rebuilds the GWT causal seal itself.  A caller-supplied prose claim or
    detached GWT digest cannot satisfy this boundary.
    """
    start = _checkpoint_projection("start_checkpoint", start_checkpoint)
    nxt = _checkpoint_projection("next_checkpoint", next_checkpoint)

    if type(plan) is not Grid10Plan:
        raise WholePersistentLoopError("plan must be concrete Grid10Plan")
    if plan.cycle_id != effect_outcome.cycle_id:
        raise WholePersistentLoopError("cycle lineage mismatch between GRID10 and effect re-entry")
    if nxt["previous_checkpoint_id"] != start["checkpoint_id"]:
        raise WholePersistentLoopError("SUCCESSOR_CHECKPOINT_LINEAGE_MISMATCH")
    if nxt["generation"] != start["generation"] + 1:
        raise WholePersistentLoopError("SUCCESSOR_CHECKPOINT_GENERATION_MISMATCH")

    start_ref = f"checkpoint:{start['checkpoint_id']}:{start['sha256']}"
    if start_ref not in plan.provenance_refs:
        raise WholePersistentLoopError("GRID10_PLAN_MISSING_START_CHECKPOINT_LINEAGE")

    gwt_seal = seal_gwt_causal_path(
        seal_id=gwt_seal_id,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        receipts=receipts,
        uptake_summary=uptake_summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
        reentry_bundles=reentry_bundles,
        provenance_refs=gwt_provenance_refs,
    )
    if type(gwt_seal) is not GwtCausalPathSeal:
        raise WholePersistentLoopError("GWT causal factory returned invalid seal")
    if gwt_seal.path_status not in _KNOWN_GWT_PATHS:
        raise WholePersistentLoopError("GWT_CAUSAL_PATH_UNKNOWN_CANNOT_CLOSE_LOOP")

    if type(effect_outcome) is not EffectOutcomeReentry:
        raise WholePersistentLoopError("effect_outcome must be concrete EffectOutcomeReentry")
    if effect_outcome.status == EFFECT_UNKNOWN:
        raise WholePersistentLoopError("EFFECT_OUTCOME_UNKNOWN_CANNOT_CLOSE_LOOP")
    if effect_outcome.generation != nxt["generation"]:
        raise WholePersistentLoopError("EFFECT_OUTCOME_REENTRY_GENERATION_MISMATCH")

    gwt_ref = f"gwt-seal:{gwt_seal.seal_id}:{gwt_seal.sha256()}"
    next_refs = set(nxt["provenance_refs"])
    if gwt_ref not in next_refs:
        raise WholePersistentLoopError("SUCCESSOR_CHECKPOINT_MISSING_GWT_REENTRY_LINEAGE")
    if effect_outcome.outcome_ref not in next_refs:
        raise WholePersistentLoopError("SUCCESSOR_CHECKPOINT_MISSING_EFFECT_OUTCOME_REENTRY")

    combined_refs = tuple(provenance_refs) + (
        start_ref,
        gwt_ref,
        effect_outcome.outcome_ref,
        f"next-checkpoint:{nxt['checkpoint_id']}:{nxt['sha256']}",
    )
    return WholePersistentLoopSeal(
        seal_id=seal_id,
        cycle_id=plan.cycle_id,
        start_checkpoint_id=start["checkpoint_id"],
        start_checkpoint_generation=start["generation"],
        start_checkpoint_sha256=start["sha256"],
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        gwt_seal_id=gwt_seal.seal_id,
        gwt_seal_sha256=gwt_seal.sha256(),
        gwt_path_status=gwt_seal.path_status,
        effect_outcome_ref=effect_outcome.outcome_ref,
        effect_outcome_sha256=effect_outcome.sha256(),
        effect_outcome_status=effect_outcome.status,
        next_checkpoint_id=nxt["checkpoint_id"],
        next_checkpoint_generation=nxt["generation"],
        next_checkpoint_sha256=nxt["sha256"],
        provenance_refs=combined_refs,
    )


__all__ = [
    "EFFECT_NO_EFFECT",
    "EFFECT_UNKNOWN",
    "EFFECT_VERIFIED",
    "EffectOutcomeReentry",
    "WholePersistentLoopError",
    "WholePersistentLoopSeal",
    "seal_whole_persistent_loop",
]
