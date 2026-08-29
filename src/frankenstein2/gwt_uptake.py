"""Deterministic GWT uptake and matched causal-influence evidence primitives.

F2-WP-507 generation 2.

This component consumes the accepted WP506 BroadcastEnvelope ABI and explicit
caller-supplied observations. It distinguishes broadcast offer, delivery, semantic
uptake, and a narrow matched intervention/control result. It does not infer hidden
model state, world truth, runtime execution, completion, or effect authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import GRID10_CELL_IDS
from frankenstein2.gwt_workspace import BroadcastEnvelope

CELL_UPTAKE_RECEIPT_SCHEMA = "FRANKENSTEIN2_GWT_CELL_UPTAKE_RECEIPT/v2"
UPTAKE_SUMMARY_SCHEMA = "FRANKENSTEIN2_GWT_UPTAKE_SUMMARY/v2"
CAUSAL_PROBE_ARM_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_PROBE_ARM/v2"
CAUSAL_INFLUENCE_RESULT_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_INFLUENCE_RESULT/v2"

_DELIVERY = frozenset({"DELIVERED", "NOT_OBSERVED"})
_UPTAKE = frozenset({"UPTAKEN", "NOT_UPTAKEN", "UNKNOWN"})
_CONDITIONS = frozenset({"INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_RECEIPT_SEAL = object()
_SUMMARY_SEAL = object()
_ARM_SEAL = object()


class GWTUptakeError(ValueError):
    """Fail-closed WP507 validation error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GWTUptakeError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise GWTUptakeError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GWTUptakeError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise GWTUptakeError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GWTUptakeError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GWTUptakeError(f"{name} must be an iterable of strings")
    refs = tuple(_identifier(f"{name} item", value) for value in values)
    if not refs:
        raise GWTUptakeError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise GWTUptakeError(f"{name} exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise GWTUptakeError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GWTUptakeError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _broadcast_binding(broadcast: BroadcastEnvelope) -> tuple[Any, ...]:
    if type(broadcast) is not BroadcastEnvelope:
        raise GWTUptakeError("broadcast must be concrete BroadcastEnvelope")
    return (
        broadcast.broadcast_id,
        broadcast.sha256(),
        broadcast.cycle_id,
        broadcast.generation,
        broadcast.selection_id,
        broadcast.selection_generation,
        broadcast.selection_sha256,
        broadcast.plan_id,
        broadcast.plan_generation,
        broadcast.plan_sha256,
    )


def _recipient_order(broadcast: BroadcastEnvelope, values: Iterable[str]) -> tuple[str, ...]:
    values_set = set(values)
    recipients = tuple(broadcast.recipient_cell_ids)
    if not values_set.issubset(set(recipients)):
        raise GWTUptakeError("cell collection contains non-recipient identity")
    return tuple(cell_id for cell_id in recipients if cell_id in values_set)


@dataclass(frozen=True, slots=True, kw_only=True)
class CellUptakeReceipt:
    receipt_id: str
    broadcast_id: str
    broadcast_sha256: str
    cycle_id: str
    broadcast_generation: int
    selection_id: str
    selection_generation: int
    selection_sha256: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    cell_id: str
    delivery_status: str
    uptake_status: str
    downstream_ref: str | None
    downstream_sha256: str | None
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    schema = CELL_UPTAKE_RECEIPT_SCHEMA
    classification = "OBSERVED_UPTAKE_EVIDENCE_NOT_HIDDEN_STATE_OR_TRUTH_AUTHORITY"

    def __post_init__(self) -> None:
        for name in ("receipt_id", "broadcast_id", "cycle_id", "selection_id", "plan_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        for name in ("broadcast_sha256", "selection_sha256", "plan_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        _generation("broadcast_generation", self.broadcast_generation)
        _generation("selection_generation", self.selection_generation)
        _generation("plan_generation", self.plan_generation)
        if self.cell_id not in GRID10_CELL_IDS:
            raise GWTUptakeError("cell_id must be one logical GRID10 identity G1..G10")
        if self.delivery_status not in _DELIVERY:
            raise GWTUptakeError("unsupported delivery_status")
        if self.uptake_status not in _UPTAKE:
            raise GWTUptakeError("unsupported uptake_status")
        if self.delivery_status != "DELIVERED" and self.uptake_status != "UNKNOWN":
            raise GWTUptakeError("uptake must remain UNKNOWN when delivery is not observed")
        if self.uptake_status == "UPTAKEN":
            if self.delivery_status != "DELIVERED":
                raise GWTUptakeError("UPTAKEN requires observed delivery")
            if self.downstream_ref is None or self.downstream_sha256 is None:
                raise GWTUptakeError("UPTAKEN requires explicit downstream evidence")
        elif self.downstream_ref is not None or self.downstream_sha256 is not None:
            raise GWTUptakeError("non-UPTAKEN receipt must not carry downstream evidence")
        if self.downstream_ref is not None:
            object.__setattr__(self, "downstream_ref", _identifier("downstream_ref", self.downstream_ref))
            object.__setattr__(self, "downstream_sha256", _sha256("downstream_sha256", self.downstream_sha256))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @classmethod
    def observe(
        cls,
        *,
        receipt_id: str,
        broadcast: BroadcastEnvelope,
        cell_id: str,
        delivery_status: str,
        uptake_status: str,
        downstream_ref: str | None = None,
        downstream_sha256: str | None = None,
        provenance_refs: Iterable[str],
    ) -> "CellUptakeReceipt":
        _broadcast_binding(broadcast)
        if cell_id not in broadcast.recipient_cell_ids:
            raise GWTUptakeError("cell_id is not a recipient of this broadcast")
        return cls(
            receipt_id=receipt_id,
            broadcast_id=broadcast.broadcast_id,
            broadcast_sha256=broadcast.sha256(),
            cycle_id=broadcast.cycle_id,
            broadcast_generation=broadcast.generation,
            selection_id=broadcast.selection_id,
            selection_generation=broadcast.selection_generation,
            selection_sha256=broadcast.selection_sha256,
            plan_id=broadcast.plan_id,
            plan_generation=broadcast.plan_generation,
            plan_sha256=broadcast.plan_sha256,
            cell_id=cell_id,
            delivery_status=delivery_status,
            uptake_status=uptake_status,
            downstream_ref=downstream_ref,
            downstream_sha256=downstream_sha256,
            provenance_refs=tuple(provenance_refs),
            _factory_seal=_RECEIPT_SEAL,
        )

    def assert_broadcast_binding(self, broadcast: BroadcastEnvelope) -> None:
        if self._factory_seal is not _RECEIPT_SEAL:
            raise GWTUptakeError("receipt was not produced by observation factory")
        expected = _broadcast_binding(broadcast)
        observed = (
            self.broadcast_id,
            self.broadcast_sha256,
            self.cycle_id,
            self.broadcast_generation,
            self.selection_id,
            self.selection_generation,
            self.selection_sha256,
            self.plan_id,
            self.plan_generation,
            self.plan_sha256,
        )
        if observed != expected:
            raise GWTUptakeError("cell receipt broadcast/selection/GRID10 binding mismatch")
        if self.cell_id not in broadcast.recipient_cell_ids:
            raise GWTUptakeError("cell receipt recipient binding mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "receipt_id": self.receipt_id,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "cycle_id": self.cycle_id,
            "broadcast_generation": self.broadcast_generation,
            "selection_id": self.selection_id,
            "selection_generation": self.selection_generation,
            "selection_sha256": self.selection_sha256,
            "plan_id": self.plan_id,
            "plan_generation": self.plan_generation,
            "plan_sha256": self.plan_sha256,
            "cell_id": self.cell_id,
            "delivery_status": self.delivery_status,
            "uptake_status": self.uptake_status,
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class UptakeSummary:
    summary_id: str
    broadcast_id: str
    broadcast_sha256: str
    cycle_id: str
    broadcast_generation: int
    selection_id: str
    selection_generation: int
    selection_sha256: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    receipt_ids: tuple[str, ...]
    delivered_cell_ids: tuple[str, ...]
    uptaken_cell_ids: tuple[str, ...]
    unknown_cell_ids: tuple[str, ...]
    status: str
    provenance_refs: tuple[str, ...]
    source_receipts: tuple[CellUptakeReceipt, ...] = field(repr=False, compare=False, hash=False)
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    schema = UPTAKE_SUMMARY_SCHEMA
    classification = "GWT_UPTAKE_MEASUREMENT_NOT_CAUSAL_PROOF_OR_RUNTIME_ACCEPTANCE"

    def __post_init__(self) -> None:
        for name in ("summary_id", "broadcast_id", "cycle_id", "selection_id", "plan_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        for name in ("broadcast_sha256", "selection_sha256", "plan_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        _generation("broadcast_generation", self.broadcast_generation)
        _generation("selection_generation", self.selection_generation)
        _generation("plan_generation", self.plan_generation)
        if self.status not in {"UPTAKE_OBSERVED", "NO_UPTAKE_OBSERVED", "UNKNOWN_INCOMPLETE_RECEIPTS"}:
            raise GWTUptakeError("unsupported uptake summary status")
        if not isinstance(self.source_receipts, tuple) or not all(type(item) is CellUptakeReceipt for item in self.source_receipts):
            raise GWTUptakeError("source_receipts must be immutable CellUptakeReceipt tuple")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "summary_id": self.summary_id,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "cycle_id": self.cycle_id,
            "broadcast_generation": self.broadcast_generation,
            "selection_id": self.selection_id,
            "selection_generation": self.selection_generation,
            "selection_sha256": self.selection_sha256,
            "plan_id": self.plan_id,
            "plan_generation": self.plan_generation,
            "plan_sha256": self.plan_sha256,
            "receipt_ids": list(self.receipt_ids),
            "delivered_cell_ids": list(self.delivered_cell_ids),
            "uptaken_cell_ids": list(self.uptaken_cell_ids),
            "unknown_cell_ids": list(self.unknown_cell_ids),
            "status": self.status,
            "provenance_refs": list(self.provenance_refs),
            "source_receipt_sha256s": [item.sha256() for item in self.source_receipts],
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def summarize_uptake(
    *,
    summary_id: str,
    broadcast: BroadcastEnvelope,
    receipts: Iterable[CellUptakeReceipt],
    provenance_refs: Iterable[str],
) -> UptakeSummary:
    _broadcast_binding(broadcast)
    values = tuple(receipts)
    if any(type(item) is not CellUptakeReceipt for item in values):
        raise GWTUptakeError("receipts must contain concrete CellUptakeReceipt values")
    receipt_ids = tuple(item.receipt_id for item in values)
    cell_ids = tuple(item.cell_id for item in values)
    if len(receipt_ids) != len(set(receipt_ids)):
        raise GWTUptakeError("duplicate receipt identity")
    if len(cell_ids) != len(set(cell_ids)):
        raise GWTUptakeError("duplicate logical cell receipt")
    for item in values:
        item.assert_broadcast_binding(broadcast)

    recipients = set(broadcast.recipient_cell_ids)
    observed = set(cell_ids)
    unknown_set = (recipients - observed) | {item.cell_id for item in values if item.uptake_status == "UNKNOWN"}
    delivered_set = {item.cell_id for item in values if item.delivery_status == "DELIVERED"}
    uptaken_set = {item.cell_id for item in values if item.uptake_status == "UPTAKEN"}
    delivered = _recipient_order(broadcast, delivered_set)
    uptaken = _recipient_order(broadcast, uptaken_set)
    unknown = _recipient_order(broadcast, unknown_set)
    if unknown:
        status = "UNKNOWN_INCOMPLETE_RECEIPTS"
    elif uptaken:
        status = "UPTAKE_OBSERVED"
    else:
        status = "NO_UPTAKE_OBSERVED"

    return UptakeSummary(
        summary_id=summary_id,
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        cycle_id=broadcast.cycle_id,
        broadcast_generation=broadcast.generation,
        selection_id=broadcast.selection_id,
        selection_generation=broadcast.selection_generation,
        selection_sha256=broadcast.selection_sha256,
        plan_id=broadcast.plan_id,
        plan_generation=broadcast.plan_generation,
        plan_sha256=broadcast.plan_sha256,
        receipt_ids=tuple(sorted(receipt_ids)),
        delivered_cell_ids=delivered,
        uptaken_cell_ids=uptaken,
        unknown_cell_ids=unknown,
        status=status,
        provenance_refs=tuple(provenance_refs),
        source_receipts=values,
        _factory_seal=_SUMMARY_SEAL,
    )


def _assert_summary_lineage(summary: UptakeSummary, broadcast: BroadcastEnvelope) -> None:
    if summary._factory_seal is not _SUMMARY_SEAL:
        raise GWTUptakeError("uptake summary was not produced by deterministic summarizer")
    expected_binding = _broadcast_binding(broadcast)
    observed_binding = (
        summary.broadcast_id,
        summary.broadcast_sha256,
        summary.cycle_id,
        summary.broadcast_generation,
        summary.selection_id,
        summary.selection_generation,
        summary.selection_sha256,
        summary.plan_id,
        summary.plan_generation,
        summary.plan_sha256,
    )
    if observed_binding != expected_binding:
        raise GWTUptakeError("uptake summary broadcast/selection/GRID10 binding mismatch")
    rebuilt = summarize_uptake(
        summary_id=summary.summary_id,
        broadcast=broadcast,
        receipts=summary.source_receipts,
        provenance_refs=summary.provenance_refs,
    )
    if rebuilt.as_dict() != summary.as_dict():
        raise GWTUptakeError("uptake summary source-receipt lineage mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class CausalProbeArm:
    arm_id: str
    probe_id: str
    condition: str
    nonbroadcast_input_sha256: str
    downstream_output_sha256: str
    broadcast_id: str | None
    broadcast_sha256: str | None
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    schema = CAUSAL_PROBE_ARM_SCHEMA
    classification = "DECLARED_MATCHED_PROBE_ARM_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "arm_id", _identifier("arm_id", self.arm_id))
        object.__setattr__(self, "probe_id", _identifier("probe_id", self.probe_id))
        if self.condition not in _CONDITIONS:
            raise GWTUptakeError("unsupported causal probe condition")
        object.__setattr__(self, "nonbroadcast_input_sha256", _sha256("nonbroadcast_input_sha256", self.nonbroadcast_input_sha256))
        object.__setattr__(self, "downstream_output_sha256", _sha256("downstream_output_sha256", self.downstream_output_sha256))
        if self.condition == "INTERVENTION_BROADCAST":
            if self.broadcast_id is None or self.broadcast_sha256 is None:
                raise GWTUptakeError("intervention arm requires exact broadcast binding")
            object.__setattr__(self, "broadcast_id", _identifier("broadcast_id", self.broadcast_id))
            object.__setattr__(self, "broadcast_sha256", _sha256("broadcast_sha256", self.broadcast_sha256))
        elif self.broadcast_id is not None or self.broadcast_sha256 is not None:
            raise GWTUptakeError("control arm must not carry broadcast binding")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @classmethod
    def intervention(cls, *, arm_id: str, probe_id: str, broadcast: BroadcastEnvelope, nonbroadcast_input_sha256: str, downstream_output_sha256: str, provenance_refs: Iterable[str]) -> "CausalProbeArm":
        _broadcast_binding(broadcast)
        return cls(arm_id=arm_id, probe_id=probe_id, condition="INTERVENTION_BROADCAST", nonbroadcast_input_sha256=nonbroadcast_input_sha256, downstream_output_sha256=downstream_output_sha256, broadcast_id=broadcast.broadcast_id, broadcast_sha256=broadcast.sha256(), provenance_refs=tuple(provenance_refs), _factory_seal=_ARM_SEAL)

    @classmethod
    def control(cls, *, arm_id: str, probe_id: str, nonbroadcast_input_sha256: str, downstream_output_sha256: str, provenance_refs: Iterable[str]) -> "CausalProbeArm":
        return cls(arm_id=arm_id, probe_id=probe_id, condition="CONTROL_NO_BROADCAST", nonbroadcast_input_sha256=nonbroadcast_input_sha256, downstream_output_sha256=downstream_output_sha256, broadcast_id=None, broadcast_sha256=None, provenance_refs=tuple(provenance_refs), _factory_seal=_ARM_SEAL)

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "classification": self.classification, "arm_id": self.arm_id, "probe_id": self.probe_id, "condition": self.condition, "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256, "downstream_output_sha256": self.downstream_output_sha256, "broadcast_id": self.broadcast_id, "broadcast_sha256": self.broadcast_sha256, "provenance_refs": list(self.provenance_refs)}

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CausalInfluenceResult:
    result_id: str
    broadcast_id: str
    broadcast_sha256: str
    uptake_summary_id: str
    uptake_summary_sha256: str
    intervention_arm_id: str
    intervention_arm_sha256: str
    control_arm_id: str
    control_arm_sha256: str
    status: str
    provenance_refs: tuple[str, ...]

    schema = CAUSAL_INFLUENCE_RESULT_SCHEMA
    classification = "MATCHED_CONTRACT_SCOPE_CAUSAL_EVIDENCE_NOT_HIDDEN_STATE_OR_WHOLE_SYSTEM_PROOF"

    def __post_init__(self) -> None:
        for name in ("result_id", "broadcast_id", "uptake_summary_id", "intervention_arm_id", "control_arm_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        for name in ("broadcast_sha256", "uptake_summary_sha256", "intervention_arm_sha256", "control_arm_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.status not in {"CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE", "NO_CAUSAL_INFLUENCE_OBSERVED", "UNKNOWN_INSUFFICIENT_UPTAKE", "UNKNOWN_UNMATCHED_CONTROL"}:
            raise GWTUptakeError("unsupported causal influence result status")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "classification": self.classification, "result_id": self.result_id, "broadcast_id": self.broadcast_id, "broadcast_sha256": self.broadcast_sha256, "uptake_summary_id": self.uptake_summary_id, "uptake_summary_sha256": self.uptake_summary_sha256, "intervention_arm_id": self.intervention_arm_id, "intervention_arm_sha256": self.intervention_arm_sha256, "control_arm_id": self.control_arm_id, "control_arm_sha256": self.control_arm_sha256, "status": self.status, "provenance_refs": list(self.provenance_refs), "runtime_credit": 0, "truth_authority": "NONE", "effect_authority": "NONE"}

    def sha256(self) -> str:
        return _digest(self.as_dict())


def evaluate_causal_influence(*, result_id: str, broadcast: BroadcastEnvelope, uptake_summary: UptakeSummary, intervention: CausalProbeArm, control: CausalProbeArm, provenance_refs: Iterable[str]) -> CausalInfluenceResult:
    _broadcast_binding(broadcast)
    if type(uptake_summary) is not UptakeSummary:
        raise GWTUptakeError("uptake_summary must be concrete UptakeSummary")
    _assert_summary_lineage(uptake_summary, broadcast)
    if type(intervention) is not CausalProbeArm or type(control) is not CausalProbeArm:
        raise GWTUptakeError("intervention and control must be concrete CausalProbeArm values")
    if intervention._factory_seal is not _ARM_SEAL or control._factory_seal is not _ARM_SEAL:
        raise GWTUptakeError("causal probe arm was not produced by declared arm factory")
    if intervention.condition != "INTERVENTION_BROADCAST" or control.condition != "CONTROL_NO_BROADCAST":
        raise GWTUptakeError("causal probe requires intervention and control conditions")
    if intervention.probe_id != control.probe_id:
        status = "UNKNOWN_UNMATCHED_CONTROL"
    elif intervention.broadcast_id != broadcast.broadcast_id or intervention.broadcast_sha256 != broadcast.sha256():
        raise GWTUptakeError("intervention broadcast binding mismatch")
    elif uptake_summary.status != "UPTAKE_OBSERVED":
        status = "UNKNOWN_INSUFFICIENT_UPTAKE"
    elif intervention.nonbroadcast_input_sha256 != control.nonbroadcast_input_sha256:
        status = "UNKNOWN_UNMATCHED_CONTROL"
    elif intervention.downstream_output_sha256 == control.downstream_output_sha256:
        status = "NO_CAUSAL_INFLUENCE_OBSERVED"
    else:
        status = "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"

    return CausalInfluenceResult(
        result_id=result_id,
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        uptake_summary_id=uptake_summary.summary_id,
        uptake_summary_sha256=uptake_summary.sha256(),
        intervention_arm_id=intervention.arm_id,
        intervention_arm_sha256=intervention.sha256(),
        control_arm_id=control.arm_id,
        control_arm_sha256=control.sha256(),
        status=status,
        provenance_refs=tuple(provenance_refs),
    )


__all__ = [
    "CAUSAL_INFLUENCE_RESULT_SCHEMA", "CAUSAL_PROBE_ARM_SCHEMA", "CELL_UPTAKE_RECEIPT_SCHEMA", "UPTAKE_SUMMARY_SCHEMA",
    "CausalInfluenceResult", "CausalProbeArm", "CellUptakeReceipt", "GWTUptakeError", "UptakeSummary", "evaluate_causal_influence", "summarize_uptake",
]
