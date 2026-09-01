"""Fail-closed admission bridge for causal GWT runtime evidence.

This module does not create a new GWT or causal-probe authority. It composes the
accepted WP507 matched causal-influence primitive with the accepted WP900 runtime
witness and emits only a bounded evidence candidate. All semantic/runtime/product
credits remain zero until an external evidence reconciliation explicitly admits
an exact-source execution at the required scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable

from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessError,
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
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

GWT_CAUSAL_RUNTIME_ADMISSION_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_RUNTIME_ADMISSION/v1"
CAUSAL_GWT_RUNTIME_CANDIDATE_OBSERVED = "CAUSAL_GWT_RUNTIME_CANDIDATE_OBSERVED"
_ADMITTED = object()


class GwtCausalRuntimeAdmissionError(ValueError):
    """Fail-closed causal/runtime composition error."""


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
        raise GwtCausalRuntimeAdmissionError("admission is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtCausalRuntimeAdmissionError("provenance_refs must be an iterable of strings")
    refs = tuple(values)
    if not refs or any(type(item) is not str or not item or item != item.strip() for item in refs):
        raise GwtCausalRuntimeAdmissionError("provenance_refs must contain non-empty trimmed strings")
    if len(set(refs)) != len(refs):
        raise GwtCausalRuntimeAdmissionError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalRuntimeAdmission:
    admission_id: str
    exact_source_sha256: str
    runtime_instance_id: str
    broadcast_id: str
    broadcast_sha256: str
    runtime_witness_sha256: str
    causal_result_id: str
    causal_result_sha256: str
    uptake_summary_id: str
    uptake_summary_sha256: str
    intervention_arm_id: str
    intervention_arm_sha256: str
    control_arm_id: str
    control_arm_sha256: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = GWT_CAUSAL_RUNTIME_ADMISSION_SCHEMA
    evidence_scope = "CAUSAL_GWT_RUNTIME_EVIDENCE_CANDIDATE_REQUIRES_EXTERNAL_ADMISSION"
    runtime_credit = 0
    gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    completion_credit = 0
    training_credit = 0
    whole_system_acceptance = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "admission_id": self.admission_id,
            "exact_source_sha256": self.exact_source_sha256,
            "runtime_instance_id": self.runtime_instance_id,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "causal_result_id": self.causal_result_id,
            "causal_result_sha256": self.causal_result_sha256,
            "uptake_summary_id": self.uptake_summary_id,
            "uptake_summary_sha256": self.uptake_summary_sha256,
            "intervention_arm_id": self.intervention_arm_id,
            "intervention_arm_sha256": self.intervention_arm_sha256,
            "control_arm_id": self.control_arm_id,
            "control_arm_sha256": self.control_arm_sha256,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "completion_credit": self.completion_credit,
            "training_credit": self.training_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def admit_causal_runtime_candidate(
    *,
    admission_id: str,
    runtime_witness: GwtRuntimeWitnessReceipt,
    broadcast: BroadcastEnvelope,
    uptake_summary: UptakeSummary,
    causal_result: CausalInfluenceResult,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    provenance_refs: Iterable[str],
) -> GwtCausalRuntimeAdmission:
    """Compose existing causal and runtime evidence without minting credit.

    The supplied causal result is deterministically rebuilt from its source objects
    rather than trusted as an independently constructible dataclass. The concrete
    runtime uptake receipt must also occur inside the rebuilt uptake summary.
    """
    if type(admission_id) is not str or not admission_id or admission_id != admission_id.strip():
        raise GwtCausalRuntimeAdmissionError("admission_id must be non-empty trimmed text")
    if type(runtime_witness) is not GwtRuntimeWitnessReceipt:
        raise GwtCausalRuntimeAdmissionError("runtime_witness must be exact GwtRuntimeWitnessReceipt")
    if type(broadcast) is not BroadcastEnvelope:
        raise GwtCausalRuntimeAdmissionError("broadcast must be exact BroadcastEnvelope")
    if type(uptake_summary) is not UptakeSummary:
        raise GwtCausalRuntimeAdmissionError("uptake_summary must be exact UptakeSummary")
    if type(causal_result) is not CausalInfluenceResult:
        raise GwtCausalRuntimeAdmissionError("causal_result must be exact CausalInfluenceResult")
    if type(intervention) is not CausalProbeArm or type(control) is not CausalProbeArm:
        raise GwtCausalRuntimeAdmissionError("intervention/control must be exact CausalProbeArm values")

    try:
        validate_gwt_runtime_witness_receipt(runtime_witness)
    except GwtRuntimeWitnessError as exc:
        raise GwtCausalRuntimeAdmissionError(f"invalid runtime witness: {exc}") from exc

    if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
        raise GwtCausalRuntimeAdmissionError("runtime witness did not observe live delivery+uptake+reentry")
    if runtime_witness.broadcast_id != broadcast.broadcast_id or runtime_witness.broadcast_sha256 != broadcast.sha256():
        raise GwtCausalRuntimeAdmissionError("runtime witness and causal broadcast identity mismatch")

    try:
        rebuilt = evaluate_causal_influence(
            result_id=causal_result.result_id,
            broadcast=broadcast,
            uptake_summary=uptake_summary,
            intervention=intervention,
            control=control,
            provenance_refs=causal_result.provenance_refs,
        )
    except GWTUptakeError as exc:
        raise GwtCausalRuntimeAdmissionError(f"invalid causal source lineage: {exc}") from exc

    if rebuilt.as_dict() != causal_result.as_dict():
        raise GwtCausalRuntimeAdmissionError("causal result does not match deterministic source rebuild")
    if rebuilt.status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
        raise GwtCausalRuntimeAdmissionError("causal influence was not observed at matched contract scope")

    matching_runtime_receipts = tuple(
        item
        for item in uptake_summary.source_receipts
        if item.receipt_id == runtime_witness.uptake_receipt_id
        and item.sha256() == runtime_witness.uptake_receipt_sha256
    )
    if len(matching_runtime_receipts) != 1:
        raise GwtCausalRuntimeAdmissionError("runtime uptake receipt is not uniquely present in causal uptake summary")
    if matching_runtime_receipts[0].uptake_status != "UPTAKEN":
        raise GwtCausalRuntimeAdmissionError("runtime-bound causal uptake receipt is not UPTAKEN")

    admission = GwtCausalRuntimeAdmission(
        admission_id=admission_id,
        exact_source_sha256=runtime_witness.identity.exact_source_sha256,
        runtime_instance_id=runtime_witness.identity.runtime_instance_id,
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        runtime_witness_sha256=runtime_witness.sha256(),
        causal_result_id=rebuilt.result_id,
        causal_result_sha256=rebuilt.sha256(),
        uptake_summary_id=uptake_summary.summary_id,
        uptake_summary_sha256=uptake_summary.sha256(),
        intervention_arm_id=intervention.arm_id,
        intervention_arm_sha256=intervention.sha256(),
        control_arm_id=control.arm_id,
        control_arm_sha256=control.sha256(),
        classification=CAUSAL_GWT_RUNTIME_CANDIDATE_OBSERVED,
        provenance_refs=_refs(provenance_refs),
        _factory_seal=_ADMITTED,
    )
    object.__setattr__(admission, "_factory_payload_sha256", _digest(admission.as_dict()))
    return admission


def validate_gwt_causal_runtime_admission(admission: GwtCausalRuntimeAdmission) -> None:
    if type(admission) is not GwtCausalRuntimeAdmission or admission._factory_seal is not _ADMITTED:
        raise GwtCausalRuntimeAdmissionError("causal runtime admission lacks factory origin")
    if admission._factory_payload_sha256 != _digest(admission.as_dict()):
        raise GwtCausalRuntimeAdmissionError("causal runtime admission payload changed after seal")


__all__ = [
    "CAUSAL_GWT_RUNTIME_CANDIDATE_OBSERVED",
    "GWT_CAUSAL_RUNTIME_ADMISSION_SCHEMA",
    "GwtCausalRuntimeAdmission",
    "GwtCausalRuntimeAdmissionError",
    "admit_causal_runtime_candidate",
    "validate_gwt_causal_runtime_admission",
]
