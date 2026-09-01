"""Fail-closed causal readback binder for the accepted F2 GWT runtime path.

F2-WP-900 generation 4.

WP900 G3 established one bounded target-component observation of the positive
DELIVERY -> UPTAKE -> REENTRY path. WP507 supplies a matched intervention /
no-broadcast causal-probe ABI. This module composes those accepted boundaries
without creating a second GWT, J-Space, state, effect or runtime authority.

The binder accepts an already sealed positive runtime witness, the exact uptake
receipt that witness observed, a complete uptake summary, an explicit shared
probe execution context, and an explicit no-broadcast control readback. It
requires:

* the positive arm really observed DELIVERY, UPTAKE and REENTRY;
* the uptake receipt is exactly the one bound by the runtime witness;
* intervention and control use the same non-broadcast input identity;
* the control run explicitly observed no GWT re-entry;
* both arms bind the same exact source and boot;
* both arms bind one hashed runner/engine/config/environment/dependency context;
* the control readback is factory-bound from that concrete typed context;
* WP507's matched causal evaluator reports a contract-scope influence.

Repository construction or CI produces only an evidence candidate. Runtime,
semantic GWT/J-Space, physical GRID10, effect, completion and training credit
remain zero until an external admitted execution/reconciliation promotes the
exact measured scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    CellUptakeReceipt,
    UptakeSummary,
    evaluate_causal_influence,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

GWT_CAUSAL_RUNTIME_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_RUNTIME_READBACK/v1"
CONTROL_NO_BROADCAST_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_CONTROL_NO_BROADCAST_READBACK/v1"
PROBE_EXECUTION_CONTEXT_SCHEMA = "FRANKENSTEIN2_GWT_PROBE_EXECUTION_CONTEXT/v1"
CAUSAL_RUNTIME_READBACK_OBSERVED = "CAUSAL_RUNTIME_READBACK_OBSERVED_AT_CONTRACT_SCOPE"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_CONTROL_FACTORY = object()
_BOUND = object()


class GwtCausalRuntimeReadbackError(ValueError):
    """Fail-closed WP900 G4 causal-runtime readback error."""


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
    refs = tuple(_text("provenance_ref", value) for value in values)
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
        raise GwtCausalRuntimeReadbackError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProbeExecutionContext:
    """Concrete shared execution context for intervention and control arms.

    This record closes the matched-control context confound at the binder ABI:
    runner/surface/runtime-engine/config/environment/dependencies cannot differ
    silently between arms. Broadcast identity is deliberately absent because it
    is the manipulated dimension. External runtime admission must still prove
    that the recorded values were actually observed on the executed subject.
    """

    runner_identity: str
    execution_surface: str
    runtime_engine_identity: str
    runtime_engine_config_sha256: str
    environment_sha256: str
    dependency_set_sha256: str
    boot_id_sha256: str
    exact_source_sha256: str
    provenance_refs: tuple[str, ...]

    schema = PROBE_EXECUTION_CONTEXT_SCHEMA

    def __post_init__(self) -> None:
        for name in ("runner_identity", "execution_surface", "runtime_engine_identity"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "runtime_engine_config_sha256",
            "environment_sha256",
            "dependency_set_sha256",
            "boot_id_sha256",
            "exact_source_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "runner_identity": self.runner_identity,
            "execution_surface": self.execution_surface,
            "runtime_engine_identity": self.runtime_engine_identity,
            "runtime_engine_config_sha256": self.runtime_engine_config_sha256,
            "environment_sha256": self.environment_sha256,
            "dependency_set_sha256": self.dependency_set_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ControlNoBroadcastReadback:
    """Explicit readback for the matched no-broadcast control arm.

    A nominal instance can be parsed directly for compatibility, but the causal
    binder only accepts instances produced by :meth:`observe`, which consumes
    the concrete ProbeExecutionContext and seals the immutable payload. This
    remains an observation record, not proof that execution happened.
    """

    runtime_instance_id: str
    process_identity: str
    boot_id_sha256: str
    exact_source_sha256: str
    execution_context_sha256: str
    probe_id: str
    nonbroadcast_input_sha256: str
    downstream_ref: str
    downstream_sha256: str
    observed_monotonic_ns: int
    reentry_observed: bool
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = CONTROL_NO_BROADCAST_READBACK_SCHEMA
    condition = "CONTROL_NO_BROADCAST"

    def __post_init__(self) -> None:
        for name in ("runtime_instance_id", "process_identity", "probe_id", "downstream_ref"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "boot_id_sha256",
            "exact_source_sha256",
            "execution_context_sha256",
            "nonbroadcast_input_sha256",
            "downstream_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        if type(self.reentry_observed) is not bool:
            raise GwtCausalRuntimeReadbackError("reentry_observed must be boolean")
        if self.reentry_observed:
            raise GwtCausalRuntimeReadbackError("no-broadcast control must not claim GWT re-entry")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe(
        cls,
        *,
        execution_context: ProbeExecutionContext,
        runtime_instance_id: str,
        process_identity: str,
        boot_id_sha256: str,
        exact_source_sha256: str,
        probe_id: str,
        nonbroadcast_input_sha256: str,
        downstream_ref: str,
        downstream_sha256: str,
        observed_monotonic_ns: int,
        reentry_observed: bool,
        provenance_refs: Iterable[str],
    ) -> "ControlNoBroadcastReadback":
        if type(execution_context) is not ProbeExecutionContext:
            raise GwtCausalRuntimeReadbackError("execution_context must be exact ProbeExecutionContext")
        if exact_source_sha256 != execution_context.exact_source_sha256:
            raise GwtCausalRuntimeReadbackError("control/context source identity mismatch")
        if boot_id_sha256 != execution_context.boot_id_sha256:
            raise GwtCausalRuntimeReadbackError("control/context boot identity mismatch")
        value = cls(
            runtime_instance_id=runtime_instance_id,
            process_identity=process_identity,
            boot_id_sha256=boot_id_sha256,
            exact_source_sha256=exact_source_sha256,
            execution_context_sha256=execution_context.sha256(),
            probe_id=probe_id,
            nonbroadcast_input_sha256=nonbroadcast_input_sha256,
            downstream_ref=downstream_ref,
            downstream_sha256=downstream_sha256,
            observed_monotonic_ns=observed_monotonic_ns,
            reentry_observed=reentry_observed,
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _CONTROL_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition": self.condition,
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "boot_id_sha256": self.boot_id_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "probe_id": self.probe_id,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "reentry_observed": self.reentry_observed,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_control_no_broadcast_readback(value: ControlNoBroadcastReadback) -> None:
    """Require factory origin and immutable payload for causal use."""

    if type(value) is not ControlNoBroadcastReadback or value._factory_seal is not _CONTROL_FACTORY:
        raise GwtCausalRuntimeReadbackError("control readback lacks typed observation factory origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise GwtCausalRuntimeReadbackError("control readback payload changed after observation")


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalRuntimeReadbackCandidate:
    schema: str
    probe_id: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    recipient_cell_id: str
    nonbroadcast_input_sha256: str
    intervention_downstream_ref: str
    intervention_downstream_sha256: str
    control_downstream_ref: str
    control_downstream_sha256: str
    runtime_witness_sha256: str
    uptake_receipt_sha256: str
    uptake_summary_sha256: str
    control_readback_sha256: str
    causal_result_sha256: str
    causal_result_status: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    evidence_scope = "RUNTIME_CAUSAL_READBACK_CANDIDATE_REQUIRES_EXTERNAL_EXECUTION_ADMISSION"
    runtime_credit = 0
    target_environment_component_runtime_credit = 0
    gwt_contract_causal_runtime_candidate_credit = 0
    physical_grid10_credit = 0
    gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if self.schema != GWT_CAUSAL_RUNTIME_READBACK_SCHEMA:
            raise GwtCausalRuntimeReadbackError("causal runtime readback schema mismatch")
        for name in (
            "probe_id",
            "broadcast_id",
            "recipient_cell_id",
            "intervention_downstream_ref",
            "control_downstream_ref",
            "causal_result_status",
            "classification",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "broadcast_sha256",
            "nonbroadcast_input_sha256",
            "intervention_downstream_sha256",
            "control_downstream_sha256",
            "runtime_witness_sha256",
            "uptake_receipt_sha256",
            "uptake_summary_sha256",
            "control_readback_sha256",
            "causal_result_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.classification != CAUSAL_RUNTIME_READBACK_OBSERVED:
            raise GwtCausalRuntimeReadbackError("unexpected causal runtime classification")
        if self.causal_result_status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
            raise GwtCausalRuntimeReadbackError("causal result is not positive at contract scope")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "probe_id": self.probe_id,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "intervention_downstream_ref": self.intervention_downstream_ref,
            "intervention_downstream_sha256": self.intervention_downstream_sha256,
            "control_downstream_ref": self.control_downstream_ref,
            "control_downstream_sha256": self.control_downstream_sha256,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "uptake_summary_sha256": self.uptake_summary_sha256,
            "control_readback_sha256": self.control_readback_sha256,
            "causal_result_sha256": self.causal_result_sha256,
            "causal_result_status": self.causal_result_status,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "gwt_contract_causal_runtime_candidate_credit": self.gwt_contract_causal_runtime_candidate_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_causal_runtime_readback(
    *,
    probe_id: str,
    nonbroadcast_input_sha256: str,
    execution_context: ProbeExecutionContext,
    broadcast: BroadcastEnvelope,
    runtime_witness: GwtRuntimeWitnessReceipt,
    uptake_receipt: CellUptakeReceipt,
    uptake_summary: UptakeSummary,
    control_readback: ControlNoBroadcastReadback,
    provenance_refs: Iterable[str],
) -> GwtCausalRuntimeReadbackCandidate:
    """Bind one positive live GWT path to one matched no-broadcast readback.

    The function deliberately consumes observations rather than executing a model
    or external effect. A target harness must supply observations from actual
    execution; external reconciliation then decides the exact credit scope.
    """

    probe_id = _text("probe_id", probe_id)
    nonbroadcast_input_sha256 = _sha256("nonbroadcast_input_sha256", nonbroadcast_input_sha256)
    if type(execution_context) is not ProbeExecutionContext:
        raise GwtCausalRuntimeReadbackError("execution_context must be exact ProbeExecutionContext")
    execution_context_sha256 = execution_context.sha256()
    if type(broadcast) is not BroadcastEnvelope:
        raise GwtCausalRuntimeReadbackError("broadcast must be exact BroadcastEnvelope")
    if type(runtime_witness) is not GwtRuntimeWitnessReceipt:
        raise GwtCausalRuntimeReadbackError("runtime_witness must be exact GwtRuntimeWitnessReceipt")
    try:
        validate_gwt_runtime_witness_receipt(runtime_witness)
    except ValueError as exc:
        raise GwtCausalRuntimeReadbackError(f"invalid runtime witness: {exc}") from exc
    if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
        raise GwtCausalRuntimeReadbackError("positive arm must be LIVE_GWT_PATH_OBSERVED")
    if runtime_witness.broadcast_id != broadcast.broadcast_id or runtime_witness.broadcast_sha256 != broadcast.sha256():
        raise GwtCausalRuntimeReadbackError("runtime witness/broadcast identity mismatch")
    if execution_context.exact_source_sha256 != runtime_witness.identity.exact_source_sha256:
        raise GwtCausalRuntimeReadbackError("execution context/source identity mismatch")
    if execution_context.boot_id_sha256 != runtime_witness.identity.boot_id_sha256:
        raise GwtCausalRuntimeReadbackError("execution context/boot identity mismatch")

    if type(uptake_receipt) is not CellUptakeReceipt:
        raise GwtCausalRuntimeReadbackError("uptake_receipt must be exact CellUptakeReceipt")
    try:
        uptake_receipt.assert_broadcast_binding(broadcast)
    except ValueError as exc:
        raise GwtCausalRuntimeReadbackError(f"invalid uptake receipt: {exc}") from exc
    if uptake_receipt.receipt_id != runtime_witness.uptake_receipt_id or uptake_receipt.sha256() != runtime_witness.uptake_receipt_sha256:
        raise GwtCausalRuntimeReadbackError("uptake receipt is not the runtime-witness receipt")
    if uptake_receipt.uptake_status != "UPTAKEN" or uptake_receipt.downstream_ref is None or uptake_receipt.downstream_sha256 is None:
        raise GwtCausalRuntimeReadbackError("positive arm requires observed downstream uptake readback")

    if type(uptake_summary) is not UptakeSummary:
        raise GwtCausalRuntimeReadbackError("uptake_summary must be exact UptakeSummary")
    if not any(
        item.receipt_id == uptake_receipt.receipt_id and item.sha256() == uptake_receipt.sha256()
        for item in uptake_summary.source_receipts
    ):
        raise GwtCausalRuntimeReadbackError("uptake summary does not contain runtime-witness receipt")

    validate_control_no_broadcast_readback(control_readback)
    if control_readback.probe_id != probe_id:
        raise GwtCausalRuntimeReadbackError("control probe identity mismatch")
    if control_readback.nonbroadcast_input_sha256 != nonbroadcast_input_sha256:
        raise GwtCausalRuntimeReadbackError("control non-broadcast input is not matched")
    if control_readback.exact_source_sha256 != runtime_witness.identity.exact_source_sha256:
        raise GwtCausalRuntimeReadbackError("control exact-source identity mismatch")
    if control_readback.boot_id_sha256 != runtime_witness.identity.boot_id_sha256:
        raise GwtCausalRuntimeReadbackError("control boot identity mismatch")
    if control_readback.execution_context_sha256 != execution_context_sha256:
        raise GwtCausalRuntimeReadbackError("control execution-context identity mismatch")
    if control_readback.reentry_observed:
        raise GwtCausalRuntimeReadbackError("control arm unexpectedly observed GWT re-entry")

    intervention = CausalProbeArm.intervention(
        arm_id=f"{probe_id}:intervention",
        probe_id=probe_id,
        broadcast=broadcast,
        nonbroadcast_input_sha256=nonbroadcast_input_sha256,
        downstream_output_sha256=uptake_receipt.downstream_sha256,
        provenance_refs=("wp900:g4:runtime-positive", runtime_witness.sha256(), execution_context_sha256),
    )
    control = CausalProbeArm.control(
        arm_id=f"{probe_id}:control",
        probe_id=probe_id,
        nonbroadcast_input_sha256=control_readback.nonbroadcast_input_sha256,
        downstream_output_sha256=control_readback.downstream_sha256,
        provenance_refs=("wp900:g4:runtime-control", control_readback.sha256(), execution_context_sha256),
    )
    try:
        causal_result: CausalInfluenceResult = evaluate_causal_influence(
            result_id=f"{probe_id}:causal-result",
            broadcast=broadcast,
            uptake_summary=uptake_summary,
            intervention=intervention,
            control=control,
            provenance_refs=("wp900:g4:matched-runtime-readback", execution_context_sha256),
        )
    except ValueError as exc:
        raise GwtCausalRuntimeReadbackError(f"causal evaluator rejected observations: {exc}") from exc
    if causal_result.status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
        raise GwtCausalRuntimeReadbackError(f"causal discriminator did not pass: {causal_result.status}")

    candidate = GwtCausalRuntimeReadbackCandidate(
        schema=GWT_CAUSAL_RUNTIME_READBACK_SCHEMA,
        probe_id=probe_id,
        exact_source_sha256=runtime_witness.identity.exact_source_sha256,
        boot_id_sha256=runtime_witness.identity.boot_id_sha256,
        execution_context_sha256=execution_context_sha256,
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        recipient_cell_id=runtime_witness.recipient_cell_id,
        nonbroadcast_input_sha256=nonbroadcast_input_sha256,
        intervention_downstream_ref=uptake_receipt.downstream_ref,
        intervention_downstream_sha256=uptake_receipt.downstream_sha256,
        control_downstream_ref=control_readback.downstream_ref,
        control_downstream_sha256=control_readback.downstream_sha256,
        runtime_witness_sha256=runtime_witness.sha256(),
        uptake_receipt_sha256=uptake_receipt.sha256(),
        uptake_summary_sha256=uptake_summary.sha256(),
        control_readback_sha256=control_readback.sha256(),
        causal_result_sha256=causal_result.sha256(),
        causal_result_status=causal_result.status,
        classification=CAUSAL_RUNTIME_READBACK_OBSERVED,
        provenance_refs=_refs(provenance_refs),
        _factory_seal=_BOUND,
    )
    object.__setattr__(candidate, "_factory_payload_sha256", _digest(candidate.as_dict()))
    return candidate


def validate_causal_runtime_readback(candidate: GwtCausalRuntimeReadbackCandidate) -> None:
    """Validate binder origin and immutable payload; never promote evidence scope."""

    if type(candidate) is not GwtCausalRuntimeReadbackCandidate or candidate._factory_seal is not _BOUND:
        raise GwtCausalRuntimeReadbackError("causal runtime candidate lacks binder factory origin")
    if candidate._factory_payload_sha256 != _digest(candidate.as_dict()):
        raise GwtCausalRuntimeReadbackError("causal runtime candidate payload changed after bind")


__all__ = [
    "CAUSAL_RUNTIME_READBACK_OBSERVED",
    "CONTROL_NO_BROADCAST_READBACK_SCHEMA",
    "GWT_CAUSAL_RUNTIME_READBACK_SCHEMA",
    "PROBE_EXECUTION_CONTEXT_SCHEMA",
    "ControlNoBroadcastReadback",
    "GwtCausalRuntimeReadbackCandidate",
    "GwtCausalRuntimeReadbackError",
    "ProbeExecutionContext",
    "bind_causal_runtime_readback",
    "validate_causal_runtime_readback",
    "validate_control_no_broadcast_readback",
]
