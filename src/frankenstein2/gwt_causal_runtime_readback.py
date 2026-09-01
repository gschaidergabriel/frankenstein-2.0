"""Fail-closed binder for WP900 G4 causal runtime intervention/readback evidence.

This module composes three already accepted contracts without creating a second
GWT/J-Space, state, effect, release, or evidence authority:

* a sealed WP900 live DELIVERY -> UPTAKE -> REENTRY runtime witness;
* the exact WP507 uptake summary/causal-probe ABI for that broadcast; and
* one separately observed matched no-broadcast downstream readback.

The intervention arm is not caller-declared from arbitrary data: its downstream
output must equal the downstream digest carried by the exact uptake receipt that
WP900 observed live.  The control arm is separately observed under the same
non-broadcast input identity.  Sealing delegates the causal decision to the
accepted WP507 ``evaluate_causal_influence`` implementation.

A receipt from this module is still only a runtime evidence candidate.  It never
mints target-runtime, semantic GWT/J-Space, physical, effect, training,
completion, or whole-system credit.  Those promotions remain external
execution/reconciliation decisions over an exact frozen source subject.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Iterable

from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    GWTUptakeError,
    UptakeSummary,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

GWT_CAUSAL_RUNTIME_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_RUNTIME_READBACK/v1"
_RECORDED = object()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_REFS = 4096


class GwtCausalRuntimeReadbackError(ValueError):
    """Fail-closed validation error for the bounded WP900 G4 binder."""


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


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtCausalRuntimeReadbackError(f"{name} must be an iterable of refs")
    refs = tuple(_text(f"{name} item", value) for value in values)
    if not refs:
        raise GwtCausalRuntimeReadbackError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise GwtCausalRuntimeReadbackError(f"{name} exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise GwtCausalRuntimeReadbackError(f"{name} must not contain duplicates")
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
class CausalRuntimeReadbackObservation:
    """One recorder-origin downstream readback observation."""

    condition: str
    observed_monotonic_ns: int
    arm_id: str
    probe_id: str
    nonbroadcast_input_sha256: str
    downstream_output_sha256: str
    arm_sha256: str
    _recorder_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        if self.condition not in {"INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"}:
            raise GwtCausalRuntimeReadbackError("unsupported causal runtime condition")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "arm_id", _text("arm_id", self.arm_id))
        object.__setattr__(self, "probe_id", _text("probe_id", self.probe_id))
        for name in ("nonbroadcast_input_sha256", "downstream_output_sha256", "arm_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "arm_id": self.arm_id,
            "probe_id": self.probe_id,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "downstream_output_sha256": self.downstream_output_sha256,
            "arm_sha256": self.arm_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalRuntimeReadbackReceipt:
    schema: str
    runtime_witness_sha256: str
    runtime_instance_id: str
    process_identity: str
    boot_id_sha256: str
    exact_source_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    uptake_summary_id: str
    uptake_summary_sha256: str
    recipient_cell_id: str
    uptake_receipt_id: str
    uptake_receipt_sha256: str
    probe_id: str
    nonbroadcast_input_sha256: str
    intervention_arm_id: str
    intervention_arm_sha256: str
    control_arm_id: str
    control_arm_sha256: str
    intervention_output_sha256: str
    control_output_sha256: str
    causal_result_id: str
    causal_result_sha256: str
    causal_status: str
    observations: tuple[CausalRuntimeReadbackObservation, CausalRuntimeReadbackObservation]
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    evidence_scope = "RUNTIME_CAUSAL_READBACK_CANDIDATE_REQUIRES_EXTERNAL_EXECUTION_ADMISSION"
    repository_ci_credit = 0
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
        if self.schema != GWT_CAUSAL_RUNTIME_READBACK_SCHEMA:
            raise GwtCausalRuntimeReadbackError("causal runtime readback schema mismatch")
        for name in (
            "runtime_instance_id",
            "process_identity",
            "broadcast_id",
            "uptake_summary_id",
            "recipient_cell_id",
            "uptake_receipt_id",
            "probe_id",
            "intervention_arm_id",
            "control_arm_id",
            "causal_result_id",
            "causal_status",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "runtime_witness_sha256",
            "boot_id_sha256",
            "exact_source_sha256",
            "broadcast_sha256",
            "uptake_summary_sha256",
            "uptake_receipt_sha256",
            "nonbroadcast_input_sha256",
            "intervention_arm_sha256",
            "control_arm_sha256",
            "intervention_output_sha256",
            "control_output_sha256",
            "causal_result_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if type(self.observations) is not tuple or len(self.observations) != 2:
            raise GwtCausalRuntimeReadbackError("observations must contain intervention and control")
        if tuple(item.condition for item in self.observations) != (
            "INTERVENTION_BROADCAST",
            "CONTROL_NO_BROADCAST",
        ):
            raise GwtCausalRuntimeReadbackError("readback order must be intervention then matched control")
        if any(
            type(item) is not CausalRuntimeReadbackObservation or item._recorder_seal is not _RECORDED
            for item in self.observations
        ):
            raise GwtCausalRuntimeReadbackError("readback observation lacks recorder origin")
        if self.observations[0].observed_monotonic_ns >= self.observations[1].observed_monotonic_ns:
            raise GwtCausalRuntimeReadbackError("readback observations must be strictly increasing")
        if any(item.probe_id != self.probe_id for item in self.observations):
            raise GwtCausalRuntimeReadbackError("observation probe identity mismatch")
        if any(item.nonbroadcast_input_sha256 != self.nonbroadcast_input_sha256 for item in self.observations):
            raise GwtCausalRuntimeReadbackError("observation nonbroadcast input mismatch")
        if self.observations[0].arm_id != self.intervention_arm_id or self.observations[0].arm_sha256 != self.intervention_arm_sha256:
            raise GwtCausalRuntimeReadbackError("intervention observation/arm mismatch")
        if self.observations[1].arm_id != self.control_arm_id or self.observations[1].arm_sha256 != self.control_arm_sha256:
            raise GwtCausalRuntimeReadbackError("control observation/arm mismatch")
        if self.observations[0].downstream_output_sha256 != self.intervention_output_sha256:
            raise GwtCausalRuntimeReadbackError("intervention output mismatch")
        if self.observations[1].downstream_output_sha256 != self.control_output_sha256:
            raise GwtCausalRuntimeReadbackError("control output mismatch")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "boot_id_sha256": self.boot_id_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "uptake_summary_id": self.uptake_summary_id,
            "uptake_summary_sha256": self.uptake_summary_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "uptake_receipt_id": self.uptake_receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "probe_id": self.probe_id,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "intervention_arm_id": self.intervention_arm_id,
            "intervention_arm_sha256": self.intervention_arm_sha256,
            "control_arm_id": self.control_arm_id,
            "control_arm_sha256": self.control_arm_sha256,
            "intervention_output_sha256": self.intervention_output_sha256,
            "control_output_sha256": self.control_output_sha256,
            "causal_result_id": self.causal_result_id,
            "causal_result_sha256": self.causal_result_sha256,
            "causal_status": self.causal_status,
            "observations": [item.as_dict() for item in self.observations],
            "provenance_refs": list(self.provenance_refs),
            "evidence_scope": self.evidence_scope,
            "repository_ci_credit": self.repository_ci_credit,
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


MonotonicNs = Callable[[], int]


class GwtCausalRuntimeReadbackRecorder:
    """Bind a live WP900 intervention arm to a matched observed control arm."""

    def __init__(
        self,
        *,
        runtime_witness: GwtRuntimeWitnessReceipt,
        broadcast: BroadcastEnvelope,
        uptake_summary: UptakeSummary,
        monotonic_ns: MonotonicNs,
    ) -> None:
        if type(runtime_witness) is not GwtRuntimeWitnessReceipt:
            raise GwtCausalRuntimeReadbackError("runtime_witness must be exact GwtRuntimeWitnessReceipt")
        try:
            validate_gwt_runtime_witness_receipt(runtime_witness)
        except ValueError as exc:
            raise GwtCausalRuntimeReadbackError(f"invalid runtime witness: {exc}") from exc
        if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
            raise GwtCausalRuntimeReadbackError("G4 requires a LIVE_GWT_PATH_OBSERVED intervention witness")
        if type(broadcast) is not BroadcastEnvelope:
            raise GwtCausalRuntimeReadbackError("broadcast must be exact BroadcastEnvelope")
        if type(uptake_summary) is not UptakeSummary:
            raise GwtCausalRuntimeReadbackError("uptake_summary must be exact UptakeSummary")
        if not callable(monotonic_ns):
            raise GwtCausalRuntimeReadbackError("monotonic_ns must be callable")
        if runtime_witness.broadcast_id != broadcast.broadcast_id or runtime_witness.broadcast_sha256 != broadcast.sha256():
            raise GwtCausalRuntimeReadbackError("runtime witness/broadcast identity mismatch")
        if uptake_summary.broadcast_id != broadcast.broadcast_id or uptake_summary.broadcast_sha256 != broadcast.sha256():
            raise GwtCausalRuntimeReadbackError("uptake summary/broadcast identity mismatch")
        try:
            rebuilt = summarize_uptake(
                summary_id=uptake_summary.summary_id,
                broadcast=broadcast,
                receipts=uptake_summary.source_receipts,
                provenance_refs=uptake_summary.provenance_refs,
            )
        except GWTUptakeError as exc:
            raise GwtCausalRuntimeReadbackError(f"invalid uptake summary lineage: {exc}") from exc
        if rebuilt.as_dict() != uptake_summary.as_dict():
            raise GwtCausalRuntimeReadbackError("uptake summary source-receipt lineage mismatch")
        if uptake_summary.status != "UPTAKE_OBSERVED":
            raise GwtCausalRuntimeReadbackError("G4 requires an UPTAKE_OBSERVED summary")

        matches = tuple(
            receipt
            for receipt in uptake_summary.source_receipts
            if receipt.receipt_id == runtime_witness.uptake_receipt_id
            and receipt.sha256() == runtime_witness.uptake_receipt_sha256
            and receipt.cell_id == runtime_witness.recipient_cell_id
        )
        if len(matches) != 1:
            raise GwtCausalRuntimeReadbackError("uptake summary does not contain the exact live WP900 uptake receipt")
        live_receipt = matches[0]
        if live_receipt.delivery_status != "DELIVERED" or live_receipt.uptake_status != "UPTAKEN":
            raise GwtCausalRuntimeReadbackError("live WP900 uptake receipt is not a delivered/uptaken intervention")
        if live_receipt.downstream_sha256 is None:
            raise GwtCausalRuntimeReadbackError("live WP900 uptake receipt has no downstream readback digest")

        self._runtime_witness = runtime_witness
        self._broadcast = broadcast
        self._uptake_summary = uptake_summary
        self._clock = monotonic_ns
        self._live_intervention_output_sha256 = live_receipt.downstream_sha256
        self._intervention: CausalProbeArm | None = None
        self._control: CausalProbeArm | None = None
        self._observations: list[CausalRuntimeReadbackObservation] = []
        self._sealed = False

    def _observation(self, arm: CausalProbeArm) -> CausalRuntimeReadbackObservation:
        if self._sealed:
            raise GwtCausalRuntimeReadbackError("causal runtime recorder is already sealed")
        observed = CausalRuntimeReadbackObservation(
            condition=arm.condition,
            observed_monotonic_ns=_positive_int("monotonic_ns", self._clock()),
            arm_id=arm.arm_id,
            probe_id=arm.probe_id,
            nonbroadcast_input_sha256=arm.nonbroadcast_input_sha256,
            downstream_output_sha256=arm.downstream_output_sha256,
            arm_sha256=arm.sha256(),
            _recorder_seal=_RECORDED,
        )
        if self._observations and observed.observed_monotonic_ns <= self._observations[-1].observed_monotonic_ns:
            raise GwtCausalRuntimeReadbackError("runtime clock did not advance monotonically")
        self._observations.append(observed)
        return observed

    def observe_intervention_readback(
        self,
        *,
        arm_id: str,
        probe_id: str,
        nonbroadcast_input_sha256: str,
        observed_downstream_output_sha256: str,
        provenance_refs: Iterable[str],
    ) -> CausalProbeArm:
        if self._intervention is not None:
            raise GwtCausalRuntimeReadbackError("intervention readback already recorded")
        if self._control is not None:
            raise GwtCausalRuntimeReadbackError("intervention must be recorded before control")
        observed_output = _sha256("observed_downstream_output_sha256", observed_downstream_output_sha256)
        if observed_output != self._live_intervention_output_sha256:
            raise GwtCausalRuntimeReadbackError("intervention output does not match the exact live WP900 uptake receipt")
        try:
            arm = CausalProbeArm.intervention(
                arm_id=arm_id,
                probe_id=probe_id,
                broadcast=self._broadcast,
                nonbroadcast_input_sha256=nonbroadcast_input_sha256,
                downstream_output_sha256=observed_output,
                provenance_refs=provenance_refs,
            )
        except GWTUptakeError as exc:
            raise GwtCausalRuntimeReadbackError(f"invalid intervention readback: {exc}") from exc
        self._intervention = arm
        self._observation(arm)
        return arm

    def observe_control_readback(
        self,
        *,
        arm_id: str,
        probe_id: str,
        nonbroadcast_input_sha256: str,
        observed_downstream_output_sha256: str,
        provenance_refs: Iterable[str],
    ) -> CausalProbeArm:
        if self._intervention is None:
            raise GwtCausalRuntimeReadbackError("intervention must be recorded before control")
        if self._control is not None:
            raise GwtCausalRuntimeReadbackError("control readback already recorded")
        if probe_id != self._intervention.probe_id:
            raise GwtCausalRuntimeReadbackError("control probe_id must match intervention probe_id")
        nonbroadcast = _sha256("nonbroadcast_input_sha256", nonbroadcast_input_sha256)
        if nonbroadcast != self._intervention.nonbroadcast_input_sha256:
            raise GwtCausalRuntimeReadbackError("control nonbroadcast input must match intervention")
        try:
            arm = CausalProbeArm.control(
                arm_id=arm_id,
                probe_id=probe_id,
                nonbroadcast_input_sha256=nonbroadcast,
                downstream_output_sha256=observed_downstream_output_sha256,
                provenance_refs=provenance_refs,
            )
        except GWTUptakeError as exc:
            raise GwtCausalRuntimeReadbackError(f"invalid control readback: {exc}") from exc
        self._control = arm
        self._observation(arm)
        return arm

    def seal(
        self,
        *,
        result_id: str,
        provenance_refs: Iterable[str],
    ) -> GwtCausalRuntimeReadbackReceipt:
        if self._sealed:
            raise GwtCausalRuntimeReadbackError("causal runtime recorder is already sealed")
        if self._intervention is None or self._control is None:
            raise GwtCausalRuntimeReadbackError("intervention and control readbacks are required before seal")
        try:
            result: CausalInfluenceResult = evaluate_causal_influence(
                result_id=result_id,
                broadcast=self._broadcast,
                uptake_summary=self._uptake_summary,
                intervention=self._intervention,
                control=self._control,
                provenance_refs=provenance_refs,
            )
        except GWTUptakeError as exc:
            raise GwtCausalRuntimeReadbackError(f"causal evaluation rejected readbacks: {exc}") from exc
        refs = _refs("provenance_refs", provenance_refs)
        identity = self._runtime_witness.identity
        receipt = GwtCausalRuntimeReadbackReceipt(
            schema=GWT_CAUSAL_RUNTIME_READBACK_SCHEMA,
            runtime_witness_sha256=self._runtime_witness.sha256(),
            runtime_instance_id=identity.runtime_instance_id,
            process_identity=identity.process_identity,
            boot_id_sha256=identity.boot_id_sha256,
            exact_source_sha256=identity.exact_source_sha256,
            broadcast_id=self._broadcast.broadcast_id,
            broadcast_sha256=self._broadcast.sha256(),
            uptake_summary_id=self._uptake_summary.summary_id,
            uptake_summary_sha256=self._uptake_summary.sha256(),
            recipient_cell_id=self._runtime_witness.recipient_cell_id,
            uptake_receipt_id=self._runtime_witness.uptake_receipt_id,
            uptake_receipt_sha256=self._runtime_witness.uptake_receipt_sha256,
            probe_id=self._intervention.probe_id,
            nonbroadcast_input_sha256=self._intervention.nonbroadcast_input_sha256,
            intervention_arm_id=self._intervention.arm_id,
            intervention_arm_sha256=self._intervention.sha256(),
            control_arm_id=self._control.arm_id,
            control_arm_sha256=self._control.sha256(),
            intervention_output_sha256=self._intervention.downstream_output_sha256,
            control_output_sha256=self._control.downstream_output_sha256,
            causal_result_id=result.result_id,
            causal_result_sha256=result.sha256(),
            causal_status=result.status,
            observations=tuple(self._observations),
            provenance_refs=refs,
            _factory_seal=_RECORDED,
        )
        object.__setattr__(receipt, "_factory_payload_sha256", _digest(receipt.as_dict()))
        self._sealed = True
        return receipt


def validate_gwt_causal_runtime_readback_receipt(receipt: GwtCausalRuntimeReadbackReceipt) -> None:
    """Validate recorder origin and sealed payload without promoting its scope."""
    if type(receipt) is not GwtCausalRuntimeReadbackReceipt or receipt._factory_seal is not _RECORDED:
        raise GwtCausalRuntimeReadbackError("causal runtime readback receipt lacks recorder factory origin")
    if receipt._factory_payload_sha256 != _digest(receipt.as_dict()):
        raise GwtCausalRuntimeReadbackError("causal runtime readback receipt changed after seal")


__all__ = [
    "CausalRuntimeReadbackObservation",
    "GWT_CAUSAL_RUNTIME_READBACK_SCHEMA",
    "GwtCausalRuntimeReadbackError",
    "GwtCausalRuntimeReadbackReceipt",
    "GwtCausalRuntimeReadbackRecorder",
    "validate_gwt_causal_runtime_readback_receipt",
]
