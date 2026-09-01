"""Fail-closed WP900 G4 causal intervention/runtime readback binder.

This module composes already-accepted WP900 runtime-observation evidence with the
WP507 matched causal-probe ABI and WP508 re-entry/uptake lineage.  It creates a
bounded evidence candidate only.  Repository construction or CI must not mint
runtime, semantic GWT/J-Space, physical, effect, training, completion or whole-
system credit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import CellInput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import (
    GwtReentryProvenanceWitness,
    validate_reentry_witness,
)
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBinding,
    assert_reentry_uptake_binding_factory_origin,
    validate_reentry_uptake_binding,
)
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessError,
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    RuntimeObservationIdentity,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    CellUptakeReceipt,
    GWTUptakeError,
    UptakeSummary,
    evaluate_causal_influence,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope, WorkspaceSelection

GWT_CAUSAL_RUNTIME_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_RUNTIME_READBACK/v1"
GWT_CAUSAL_ARM_RUNTIME_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_ARM_RUNTIME_READBACK/v1"
CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE = "CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE"
INTERVENTION_ACTIVE_OBSERVED = "INTERVENTION_ACTIVE_OBSERVED"
INTERVENTION_ABSENT_OBSERVED = "INTERVENTION_ABSENT_OBSERVED"
_READBACK_FACTORY = object()
_BINDER_FACTORY = object()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512


class GwtCausalRuntimeReadbackError(ValueError):
    """Fail-closed WP900 G4 causal/runtime integration error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtCausalRuntimeReadbackError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise GwtCausalRuntimeReadbackError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtCausalRuntimeReadbackError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise GwtCausalRuntimeReadbackError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtCausalRuntimeReadbackError(f"{name} must be a positive integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtCausalRuntimeReadbackError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", item) for item in values)
    if not refs:
        raise GwtCausalRuntimeReadbackError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise GwtCausalRuntimeReadbackError("provenance_refs must not contain duplicates")
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
        raise GwtCausalRuntimeReadbackError("readback is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identity_tuple(identity: RuntimeObservationIdentity) -> tuple[str, str, str, str]:
    return (
        identity.runtime_instance_id,
        identity.process_identity,
        identity.boot_id_sha256,
        identity.exact_source_sha256,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CausalArmRuntimeReadback:
    """One runtime-observed matched-probe arm output candidate.

    The runtime harness must supply the observed downstream digest and activation
    state.  Factory construction is not runtime authority; external execution and
    reconciliation remain required.
    """

    identity: RuntimeObservationIdentity
    arm_id: str
    arm_sha256: str
    probe_id: str
    condition: str
    nonbroadcast_input_sha256: str
    downstream_output_sha256: str
    observed_monotonic_ns: int
    intervention_activation: str
    broadcast_id: str | None
    broadcast_sha256: str | None
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = GWT_CAUSAL_ARM_RUNTIME_READBACK_SCHEMA
    evidence_scope = "RUNTIME_ARM_READBACK_CANDIDATE_REQUIRES_EXTERNAL_EXECUTION_ADMISSION"
    runtime_credit = 0

    def __post_init__(self) -> None:
        if type(self.identity) is not RuntimeObservationIdentity:
            raise GwtCausalRuntimeReadbackError("identity must be exact RuntimeObservationIdentity")
        for name in ("arm_id", "probe_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in ("arm_sha256", "nonbroadcast_input_sha256", "downstream_output_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        if self.condition not in {"INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"}:
            raise GwtCausalRuntimeReadbackError("unsupported causal arm condition")
        if self.intervention_activation not in {
            INTERVENTION_ACTIVE_OBSERVED,
            INTERVENTION_ABSENT_OBSERVED,
        }:
            raise GwtCausalRuntimeReadbackError("unsupported intervention activation state")
        if self.condition == "INTERVENTION_BROADCAST":
            if self.intervention_activation != INTERVENTION_ACTIVE_OBSERVED:
                raise GwtCausalRuntimeReadbackError("intervention arm lacks observed activation")
            if self.broadcast_id is None or self.broadcast_sha256 is None:
                raise GwtCausalRuntimeReadbackError("intervention arm readback lacks broadcast identity")
            object.__setattr__(self, "broadcast_id", _text("broadcast_id", self.broadcast_id))
            object.__setattr__(self, "broadcast_sha256", _sha256("broadcast_sha256", self.broadcast_sha256))
        else:
            if self.intervention_activation != INTERVENTION_ABSENT_OBSERVED:
                raise GwtCausalRuntimeReadbackError("control arm did not observe broadcast absence")
            if self.broadcast_id is not None or self.broadcast_sha256 is not None:
                raise GwtCausalRuntimeReadbackError("control arm readback must not carry broadcast identity")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.as_dict(),
            "arm_id": self.arm_id,
            "arm_sha256": self.arm_sha256,
            "probe_id": self.probe_id,
            "condition": self.condition,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "downstream_output_sha256": self.downstream_output_sha256,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "intervention_activation": self.intervention_activation,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def observe_causal_arm_runtime_readback(
    *,
    identity: RuntimeObservationIdentity,
    arm: CausalProbeArm,
    observed_downstream_output_sha256: str,
    observed_monotonic_ns: int,
    intervention_activation: str,
) -> CausalArmRuntimeReadback:
    """Bind one actually-observed arm readback to an existing WP507 arm."""
    if type(identity) is not RuntimeObservationIdentity:
        raise GwtCausalRuntimeReadbackError("identity must be exact RuntimeObservationIdentity")
    if type(arm) is not CausalProbeArm:
        raise GwtCausalRuntimeReadbackError("arm must be exact CausalProbeArm")
    observed_digest = _sha256("observed_downstream_output_sha256", observed_downstream_output_sha256)
    if observed_digest != arm.downstream_output_sha256:
        raise GwtCausalRuntimeReadbackError("observed downstream digest does not match declared causal arm")
    readback = CausalArmRuntimeReadback(
        identity=identity,
        arm_id=arm.arm_id,
        arm_sha256=arm.sha256(),
        probe_id=arm.probe_id,
        condition=arm.condition,
        nonbroadcast_input_sha256=arm.nonbroadcast_input_sha256,
        downstream_output_sha256=observed_digest,
        observed_monotonic_ns=_positive_int("observed_monotonic_ns", observed_monotonic_ns),
        intervention_activation=intervention_activation,
        broadcast_id=arm.broadcast_id,
        broadcast_sha256=arm.broadcast_sha256,
        _factory_seal=_READBACK_FACTORY,
    )
    object.__setattr__(readback, "_factory_payload_sha256", _digest(readback.as_dict()))
    return readback


def validate_causal_arm_runtime_readback(readback: CausalArmRuntimeReadback) -> None:
    if type(readback) is not CausalArmRuntimeReadback or readback._factory_seal is not _READBACK_FACTORY:
        raise GwtCausalRuntimeReadbackError("causal arm runtime readback lacks factory origin")
    if readback._factory_payload_sha256 != _digest(readback.as_dict()):
        raise GwtCausalRuntimeReadbackError("causal arm runtime readback payload changed after observation")


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalRuntimeReadback:
    readback_id: str
    identity: RuntimeObservationIdentity
    broadcast_id: str
    broadcast_sha256: str
    runtime_witness_sha256: str
    uptake_receipt_id: str
    uptake_receipt_sha256: str
    reentry_witness_sha256: str
    binding_id: str
    binding_sha256: str
    causal_result_id: str
    causal_result_sha256: str
    causal_status: str
    nonbroadcast_input_sha256: str
    intervention_readback_sha256: str
    control_readback_sha256: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = GWT_CAUSAL_RUNTIME_READBACK_SCHEMA
    evidence_scope = "TARGET_ENVIRONMENT_CAUSAL_RUNTIME_READBACK_CANDIDATE_REQUIRES_EXTERNAL_RECONCILIATION"
    runtime_credit = 0
    target_environment_component_runtime_credit = 0
    gwt_contract_causal_runtime_candidate_credit = 0
    gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "readback_id", _text("readback_id", self.readback_id))
        if type(self.identity) is not RuntimeObservationIdentity:
            raise GwtCausalRuntimeReadbackError("identity must be exact RuntimeObservationIdentity")
        for name in ("broadcast_id", "uptake_receipt_id", "binding_id", "causal_result_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "broadcast_sha256",
            "runtime_witness_sha256",
            "uptake_receipt_sha256",
            "reentry_witness_sha256",
            "binding_sha256",
            "causal_result_sha256",
            "nonbroadcast_input_sha256",
            "intervention_readback_sha256",
            "control_readback_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.causal_status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
            raise GwtCausalRuntimeReadbackError("causal runtime readback requires positive matched causal status")
        if self.classification != CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE:
            raise GwtCausalRuntimeReadbackError("causal runtime readback classification mismatch")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "readback_id": self.readback_id,
            "identity": self.identity.as_dict(),
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "uptake_receipt_id": self.uptake_receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "reentry_witness_sha256": self.reentry_witness_sha256,
            "binding_id": self.binding_id,
            "binding_sha256": self.binding_sha256,
            "causal_result_id": self.causal_result_id,
            "causal_result_sha256": self.causal_result_sha256,
            "causal_status": self.causal_status,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "intervention_readback_sha256": self.intervention_readback_sha256,
            "control_readback_sha256": self.control_readback_sha256,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "gwt_contract_causal_runtime_candidate_credit": self.gwt_contract_causal_runtime_candidate_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_gwt_causal_runtime_readback(
    *,
    readback_id: str,
    runtime_witness: GwtRuntimeWitnessReceipt,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
    reentry_witness: GwtReentryProvenanceWitness,
    binding: GwtReentryUptakeBinding,
    uptake_receipt: CellUptakeReceipt,
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    causal_result: CausalInfluenceResult,
    intervention_readback: CausalArmRuntimeReadback,
    control_readback: CausalArmRuntimeReadback,
    provenance_refs: Iterable[str],
) -> GwtCausalRuntimeReadback:
    """Bind one live WP900 witness to one matched WP507 intervention/control readback."""
    _text("readback_id", readback_id)
    if type(runtime_witness) is not GwtRuntimeWitnessReceipt:
        raise GwtCausalRuntimeReadbackError("runtime_witness must be exact GwtRuntimeWitnessReceipt")
    if type(plan) is not Grid10Plan or type(selection) is not WorkspaceSelection:
        raise GwtCausalRuntimeReadbackError("plan/selection must be exact accepted types")
    if type(broadcast) is not BroadcastEnvelope or type(cell_input) is not CellInput:
        raise GwtCausalRuntimeReadbackError("broadcast/cell_input must be exact accepted types")
    if type(reentry_witness) is not GwtReentryProvenanceWitness:
        raise GwtCausalRuntimeReadbackError("reentry_witness must be exact GwtReentryProvenanceWitness")
    if type(binding) is not GwtReentryUptakeBinding:
        raise GwtCausalRuntimeReadbackError("binding must be exact GwtReentryUptakeBinding")
    if type(uptake_receipt) is not CellUptakeReceipt or type(uptake_summary) is not UptakeSummary:
        raise GwtCausalRuntimeReadbackError("uptake receipt/summary must be exact WP507 types")
    if type(intervention) is not CausalProbeArm or type(control) is not CausalProbeArm:
        raise GwtCausalRuntimeReadbackError("intervention/control must be exact CausalProbeArm values")
    if type(causal_result) is not CausalInfluenceResult:
        raise GwtCausalRuntimeReadbackError("causal_result must be exact CausalInfluenceResult")

    try:
        validate_gwt_runtime_witness_receipt(runtime_witness)
    except GwtRuntimeWitnessError as exc:
        raise GwtCausalRuntimeReadbackError(f"invalid runtime witness: {exc}") from exc
    if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
        raise GwtCausalRuntimeReadbackError("runtime witness lacks live delivery+uptake+reentry observation")
    if (runtime_witness.broadcast_id, runtime_witness.broadcast_sha256) != (
        broadcast.broadcast_id,
        broadcast.sha256(),
    ):
        raise GwtCausalRuntimeReadbackError("runtime witness broadcast identity mismatch")
    if (runtime_witness.uptake_receipt_id, runtime_witness.uptake_receipt_sha256) != (
        uptake_receipt.receipt_id,
        uptake_receipt.sha256(),
    ):
        raise GwtCausalRuntimeReadbackError("runtime witness uptake receipt identity mismatch")
    if runtime_witness.recipient_cell_id != uptake_receipt.cell_id:
        raise GwtCausalRuntimeReadbackError("runtime witness uptake recipient mismatch")

    try:
        uptake_receipt.assert_broadcast_binding(broadcast)
        validate_reentry_witness(
            reentry_witness,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )
        assert_reentry_uptake_binding_factory_origin(binding)
        validate_reentry_uptake_binding(
            binding,
            witness=reentry_witness,
            uptake_receipt=uptake_receipt,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )
    except (ValueError, GWTUptakeError) as exc:
        raise GwtCausalRuntimeReadbackError(f"invalid WP507/WP508 source lineage: {exc}") from exc

    if runtime_witness.canonical_reentry_key != reentry_witness.canonical_reentry_key():
        raise GwtCausalRuntimeReadbackError("runtime witness re-entry key mismatch")
    if runtime_witness.reentry_witness_sha256 != reentry_witness.sha256():
        raise GwtCausalRuntimeReadbackError("runtime witness re-entry digest mismatch")
    if (runtime_witness.binding_id, runtime_witness.binding_sha256) != (
        binding.binding_id,
        binding.sha256(),
    ):
        raise GwtCausalRuntimeReadbackError("runtime witness WP508 binding identity mismatch")

    try:
        rebuilt_causal = evaluate_causal_influence(
            result_id=causal_result.result_id,
            broadcast=broadcast,
            uptake_summary=uptake_summary,
            intervention=intervention,
            control=control,
            provenance_refs=causal_result.provenance_refs,
        )
    except GWTUptakeError as exc:
        raise GwtCausalRuntimeReadbackError(f"invalid matched causal source lineage: {exc}") from exc
    if rebuilt_causal.as_dict() != causal_result.as_dict():
        raise GwtCausalRuntimeReadbackError("causal result does not match deterministic WP507 rebuild")
    if rebuilt_causal.status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
        raise GwtCausalRuntimeReadbackError("causal influence was not observed at matched contract scope")

    matching_receipts = tuple(
        item
        for item in uptake_summary.source_receipts
        if item.receipt_id == uptake_receipt.receipt_id and item.sha256() == uptake_receipt.sha256()
    )
    if len(matching_receipts) != 1:
        raise GwtCausalRuntimeReadbackError("runtime uptake receipt is not uniquely present in causal summary")
    if uptake_receipt.uptake_status != "UPTAKEN" or uptake_receipt.downstream_sha256 is None:
        raise GwtCausalRuntimeReadbackError("runtime-bound uptake is not positive with downstream readback")
    if intervention.probe_id != control.probe_id:
        raise GwtCausalRuntimeReadbackError("causal arms do not share probe identity")
    if intervention.nonbroadcast_input_sha256 != control.nonbroadcast_input_sha256:
        raise GwtCausalRuntimeReadbackError("causal arms do not share nonbroadcast input identity")
    if (intervention.broadcast_id, intervention.broadcast_sha256) != (
        broadcast.broadcast_id,
        broadcast.sha256(),
    ):
        raise GwtCausalRuntimeReadbackError("intervention arm broadcast identity mismatch")
    if intervention.downstream_output_sha256 != uptake_receipt.downstream_sha256:
        raise GwtCausalRuntimeReadbackError("intervention output does not match live uptake downstream readback")

    validate_causal_arm_runtime_readback(intervention_readback)
    validate_causal_arm_runtime_readback(control_readback)
    expected_identity = _identity_tuple(runtime_witness.identity)
    if _identity_tuple(intervention_readback.identity) != expected_identity:
        raise GwtCausalRuntimeReadbackError("intervention readback runtime identity mismatch")
    if _identity_tuple(control_readback.identity) != expected_identity:
        raise GwtCausalRuntimeReadbackError("control readback runtime identity mismatch")
    if intervention_readback.observed_monotonic_ns == control_readback.observed_monotonic_ns:
        raise GwtCausalRuntimeReadbackError("matched causal arm readbacks require distinct monotonic observations")

    for label, arm, observed in (
        ("intervention", intervention, intervention_readback),
        ("control", control, control_readback),
    ):
        if observed.arm_id != arm.arm_id or observed.arm_sha256 != arm.sha256():
            raise GwtCausalRuntimeReadbackError(f"{label} runtime readback arm identity mismatch")
        if observed.probe_id != arm.probe_id or observed.condition != arm.condition:
            raise GwtCausalRuntimeReadbackError(f"{label} runtime readback probe/condition mismatch")
        if observed.nonbroadcast_input_sha256 != arm.nonbroadcast_input_sha256:
            raise GwtCausalRuntimeReadbackError(f"{label} runtime readback nonbroadcast input mismatch")
        if observed.downstream_output_sha256 != arm.downstream_output_sha256:
            raise GwtCausalRuntimeReadbackError(f"{label} runtime readback downstream digest mismatch")

    result = GwtCausalRuntimeReadback(
        readback_id=readback_id,
        identity=runtime_witness.identity,
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        runtime_witness_sha256=runtime_witness.sha256(),
        uptake_receipt_id=uptake_receipt.receipt_id,
        uptake_receipt_sha256=uptake_receipt.sha256(),
        reentry_witness_sha256=reentry_witness.sha256(),
        binding_id=binding.binding_id,
        binding_sha256=binding.sha256(),
        causal_result_id=rebuilt_causal.result_id,
        causal_result_sha256=rebuilt_causal.sha256(),
        causal_status=rebuilt_causal.status,
        nonbroadcast_input_sha256=intervention.nonbroadcast_input_sha256,
        intervention_readback_sha256=intervention_readback.sha256(),
        control_readback_sha256=control_readback.sha256(),
        classification=CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE,
        provenance_refs=_refs(provenance_refs),
        _factory_seal=_BINDER_FACTORY,
    )
    object.__setattr__(result, "_factory_payload_sha256", _digest(result.as_dict()))
    return result


def validate_gwt_causal_runtime_readback(readback: GwtCausalRuntimeReadback) -> None:
    if type(readback) is not GwtCausalRuntimeReadback or readback._factory_seal is not _BINDER_FACTORY:
        raise GwtCausalRuntimeReadbackError("causal runtime readback lacks binder factory origin")
    if readback._factory_payload_sha256 != _digest(readback.as_dict()):
        raise GwtCausalRuntimeReadbackError("causal runtime readback payload changed after seal")


__all__ = [
    "CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE",
    "CausalArmRuntimeReadback",
    "GWT_CAUSAL_ARM_RUNTIME_READBACK_SCHEMA",
    "GWT_CAUSAL_RUNTIME_READBACK_SCHEMA",
    "GwtCausalRuntimeReadback",
    "GwtCausalRuntimeReadbackError",
    "INTERVENTION_ABSENT_OBSERVED",
    "INTERVENTION_ACTIVE_OBSERVED",
    "bind_gwt_causal_runtime_readback",
    "observe_causal_arm_runtime_readback",
    "validate_causal_arm_runtime_readback",
    "validate_gwt_causal_runtime_readback",
]
