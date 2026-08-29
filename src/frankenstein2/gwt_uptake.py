"""Deterministic GWT uptake and matched causal-influence evidence contract.

F2-WP-507 generation 1.

This module never infers hidden model state, world truth, completion, or effect authority.
It only validates explicit caller-supplied delivery/uptake observations against one exact
WP506 BroadcastEnvelope and evaluates a narrow matched intervention/control probe.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import GRID10_CELL_IDS
from frankenstein2.gwt_workspace import BroadcastEnvelope

CELL_UPTAKE_RECEIPT_SCHEMA = "FRANKENSTEIN2_GWT_CELL_UPTAKE_RECEIPT/v1"
UPTAKE_SUMMARY_SCHEMA = "FRANKENSTEIN2_GWT_UPTAKE_SUMMARY/v1"
CAUSAL_PROBE_ARM_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_PROBE_ARM/v1"
CAUSAL_INFLUENCE_RESULT_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_INFLUENCE_RESULT/v1"

_DELIVERY = frozenset({"DELIVERED", "NOT_OBSERVED"})
_UPTAKE = frozenset({"UPTAKEN", "NOT_UPTAKEN", "UNKNOWN"})
_CONDITIONS = frozenset({"INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096


class GWTUptakeError(ValueError):
    """Fail-closed WP507 contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise GWTUptakeError(f"{name} must be a string")
    if not value or value != value.strip():
        raise GWTUptakeError(f"{name} must be non-empty and already trimmed")
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
        raise GWTUptakeError(f"{name} must be an iterable of reference strings")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs:
        raise GWTUptakeError(f"{name} must contain at least one reference")
    if len(refs) > _MAX_REFS:
        raise GWTUptakeError(f"{name} exceeds {_MAX_REFS} references")
    if len(set(refs)) != len(refs):
        raise GWTUptakeError(f"{name} contains duplicate references")
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
        raise GWTUptakeError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _grid_order(values: Iterable[str]) -> tuple[str, ...]:
    """Return logical cell identities in the canonical G1..G10 ABI order."""
    value_set = set(values)
    if not value_set.issubset(set(GRID10_CELL_IDS)):
        raise GWTUptakeError("cell collection contains non-GRID10 identity")
    return tuple(cell_id for cell_id in GRID10_CELL_IDS if cell_id in value_set)


@dataclass(frozen=True, slots=True)
class CellUptakeReceipt:
    schema: str
    receipt_id: str
    broadcast_id: str
    broadcast_sha256: str
    selection_id: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    cell_id: str
    delivery_status: str
    uptake_status: str
    downstream_ref: str | None
    downstream_sha256: str | None
    provenance_refs: tuple[str, ...]
    classification: str = "OBSERVED_UPTAKE_EVIDENCE_NOT_HIDDEN_STATE_OR_TRUTH_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != CELL_UPTAKE_RECEIPT_SCHEMA:
            raise GWTUptakeError("cell uptake receipt schema mismatch")
        for name in ("receipt_id", "broadcast_id", "selection_id", "plan_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        object.__setattr__(
            self,
            "broadcast_sha256",
            _sha256("broadcast_sha256", self.broadcast_sha256),
        )
        object.__setattr__(
            self,
            "plan_generation",
            _generation("plan_generation", self.plan_generation),
        )
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        if self.cell_id not in GRID10_CELL_IDS:
            raise GWTUptakeError("cell_id must be one logical GRID10 identity G1..G10")
        if self.delivery_status not in _DELIVERY:
            raise GWTUptakeError(f"delivery_status must be one of {sorted(_DELIVERY)}")
        if self.uptake_status not in _UPTAKE:
            raise GWTUptakeError(f"uptake_status must be one of {sorted(_UPTAKE)}")
        if self.delivery_status != "DELIVERED" and self.uptake_status != "UNKNOWN":
            raise GWTUptakeError("uptake must remain UNKNOWN when delivery is not observed")
        if self.uptake_status == "UPTAKEN":
            if self.downstream_ref is None or self.downstream_sha256 is None:
                raise GWTUptakeError("UPTAKEN requires explicit downstream evidence")
        if (self.downstream_ref is None) != (self.downstream_sha256 is None):
            raise GWTUptakeError(
                "downstream_ref and downstream_sha256 must be present together"
            )
        if self.downstream_ref is not None:
            object.__setattr__(
                self,
                "downstream_ref",
                _identifier("downstream_ref", self.downstream_ref),
            )
            object.__setattr__(
                self,
                "downstream_sha256",
                _sha256("downstream_sha256", self.downstream_sha256),
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

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
        if type(broadcast) is not BroadcastEnvelope:
            raise GWTUptakeError("broadcast must be concrete BroadcastEnvelope")
        if cell_id not in broadcast.recipient_cell_ids:
            raise GWTUptakeError("cell_id is not a recipient of this broadcast")
        return cls(
            schema=CELL_UPTAKE_RECEIPT_SCHEMA,
            receipt_id=receipt_id,
            broadcast_id=broadcast.broadcast_id,
            broadcast_sha256=broadcast.sha256(),
            selection_id=broadcast.selection_id,
            plan_id=broadcast.plan_id,
            plan_generation=broadcast.plan_generation,
            plan_sha256=broadcast.plan_sha256,
            cell_id=cell_id,
            delivery_status=delivery_status,
            uptake_status=uptake_status,
            downstream_ref=downstream_ref,
            downstream_sha256=downstream_sha256,
            provenance_refs=tuple(provenance_refs),
        )

    def assert_broadcast_binding(self, broadcast: BroadcastEnvelope) -> None:
        if type(broadcast) is not BroadcastEnvelope:
            raise GWTUptakeError("broadcast must be concrete BroadcastEnvelope")
        expected = (
            broadcast.broadcast_id,
            broadcast.sha256(),
            broadcast.selection_id,
            broadcast.plan_id,
            broadcast.plan_generation,
            broadcast.plan_sha256,
        )
        observed = (
            self.broadcast_id,
            self.broadcast_sha256,
            self.selection_id,
            self.plan_id,
            self.plan_generation,
            self.plan_sha256,
        )
        if observed != expected:
            raise GWTUptakeError(
                "cell receipt broadcast/selection/GRID10 binding mismatch"
            )
        if self.cell_id not in broadcast.recipient_cell_ids:
            raise GWTUptakeError("cell receipt recipient binding mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class UptakeSummary:
    schema: str
    summary_id: str
    broadcast_id: str
    broadcast_sha256: str
    selection_id: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    receipt_ids: tuple[str, ...]
    delivered_cell_ids: tuple[str, ...]
    uptaken_cell_ids: tuple[str, ...]
    unknown_cell_ids: tuple[str, ...]
    status: str
    provenance_refs: tuple[str, ...]
    classification: str = "GWT_UPTAKE_MEASUREMENT_NOT_CAUSAL_PROOF_OR_RUNTIME_ACCEPTANCE"

    def __post_init__(self) -> None:
        if self.schema != UPTAKE_SUMMARY_SCHEMA:
            raise GWTUptakeError("uptake summary schema mismatch")
        object.__setattr__(self, "summary_id", _identifier("summary_id", self.summary_id))
        object.__setattr__(
            self,
            "broadcast_id",
            _identifier("broadcast_id", self.broadcast_id),
        )
        object.__setattr__(
            self,
            "broadcast_sha256",
            _sha256("broadcast_sha256", self.broadcast_sha256),
        )
        object.__setattr__(
            self,
            "selection_id",
            _identifier("selection_id", self.selection_id),
        )
        object.__setattr__(self, "plan_id", _identifier("plan_id", self.plan_id))
        object.__setattr__(
            self,
            "plan_generation",
            _generation("plan_generation", self.plan_generation),
        )
        object.__setattr__(self, "plan_sha256", _sha256("plan_sha256", self.plan_sha256))
        if self.status not in {
            "UPTAKE_OBSERVED",
            "NO_UPTAKE_OBSERVED",
            "UNKNOWN_INCOMPLETE_RECEIPTS",
        }:
            raise GWTUptakeError("unsupported uptake summary status")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def summarize_uptake(
    *,
    summary_id: str,
    broadcast: BroadcastEnvelope,
    receipts: Iterable[CellUptakeReceipt],
    provenance_refs: Iterable[str],
) -> UptakeSummary:
    if type(broadcast) is not BroadcastEnvelope:
        raise GWTUptakeError("broadcast must be concrete BroadcastEnvelope")
    values = tuple(receipts)
    if any(type(item) is not CellUptakeReceipt for item in values):
        raise GWTUptakeError(
            "receipts must contain concrete CellUptakeReceipt values"
        )
    receipt_ids = tuple(item.receipt_id for item in values)
    cell_ids = tuple(item.cell_id for item in values)
    if len(receipt_ids) != len(set(receipt_ids)):
        raise GWTUptakeError("duplicate receipt identity")
    if len(cell_ids) != len(set(cell_ids)):
        raise GWTUptakeError("duplicate logical cell receipt")
    for item in values:
        item.assert_broadcast_binding(broadcast)

    delivered_set = {
        item.cell_id for item in values if item.delivery_status == "DELIVERED"
    }
    uptaken_set = {item.cell_id for item in values if item.uptake_status == "UPTAKEN"}
    observed_cells = set(cell_ids)
    unknown_set = (set(GRID10_CELL_IDS) - observed_cells) | {
        item.cell_id for item in values if item.uptake_status == "UNKNOWN"
    }
    delivered = _grid_order(delivered_set)
    uptaken = _grid_order(uptaken_set)
    unknown = _grid_order(unknown_set)
    if unknown:
        status = "UNKNOWN_INCOMPLETE_RECEIPTS"
    elif uptaken:
        status = "UPTAKE_OBSERVED"
    else:
        status = "NO_UPTAKE_OBSERVED"
    return UptakeSummary(
        schema=UPTAKE_SUMMARY_SCHEMA,
        summary_id=summary_id,
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        selection_id=broadcast.selection_id,
        plan_id=broadcast.plan_id,
        plan_generation=broadcast.plan_generation,
        plan_sha256=broadcast.plan_sha256,
        receipt_ids=tuple(sorted(receipt_ids)),
        delivered_cell_ids=delivered,
        uptaken_cell_ids=uptaken,
        unknown_cell_ids=unknown,
        status=status,
        provenance_refs=tuple(provenance_refs),
    )


@dataclass(frozen=True, slots=True)
class CausalProbeArm:
    schema: str
    arm_id: str
    condition: str
    nonbroadcast_input_sha256: str
    downstream_output_sha256: str
    broadcast_id: str | None
    broadcast_sha256: str | None
    provenance_refs: tuple[str, ...]
    classification: str = "DECLARED_MATCHED_PROBE_ARM_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        if self.schema != CAUSAL_PROBE_ARM_SCHEMA:
            raise GWTUptakeError("causal probe arm schema mismatch")
        object.__setattr__(self, "arm_id", _identifier("arm_id", self.arm_id))
        if self.condition not in _CONDITIONS:
            raise GWTUptakeError(f"condition must be one of {sorted(_CONDITIONS)}")
        object.__setattr__(
            self,
            "nonbroadcast_input_sha256",
            _sha256("nonbroadcast_input_sha256", self.nonbroadcast_input_sha256),
        )
        object.__setattr__(
            self,
            "downstream_output_sha256",
            _sha256("downstream_output_sha256", self.downstream_output_sha256),
        )
        if self.condition == "INTERVENTION_BROADCAST":
            if self.broadcast_id is None or self.broadcast_sha256 is None:
                raise GWTUptakeError(
                    "intervention arm requires exact broadcast binding"
                )
            object.__setattr__(
                self,
                "broadcast_id",
                _identifier("broadcast_id", self.broadcast_id),
            )
            object.__setattr__(
                self,
                "broadcast_sha256",
                _sha256("broadcast_sha256", self.broadcast_sha256),
            )
        elif self.broadcast_id is not None or self.broadcast_sha256 is not None:
            raise GWTUptakeError("control arm must not carry a broadcast binding")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    @classmethod
    def intervention(
        cls,
        *,
        arm_id: str,
        broadcast: BroadcastEnvelope,
        nonbroadcast_input_sha256: str,
        downstream_output_sha256: str,
        provenance_refs: Iterable[str],
    ) -> "CausalProbeArm":
        if type(broadcast) is not BroadcastEnvelope:
            raise GWTUptakeError("broadcast must be concrete BroadcastEnvelope")
        return cls(
            schema=CAUSAL_PROBE_ARM_SCHEMA,
            arm_id=arm_id,
            condition="INTERVENTION_BROADCAST",
            nonbroadcast_input_sha256=nonbroadcast_input_sha256,
            downstream_output_sha256=downstream_output_sha256,
            broadcast_id=broadcast.broadcast_id,
            broadcast_sha256=broadcast.sha256(),
            provenance_refs=tuple(provenance_refs),
        )

    @classmethod
    def control(
        cls,
        *,
        arm_id: str,
        nonbroadcast_input_sha256: str,
        downstream_output_sha256: str,
        provenance_refs: Iterable[str],
    ) -> "CausalProbeArm":
        return cls(
            schema=CAUSAL_PROBE_ARM_SCHEMA,
            arm_id=arm_id,
            condition="CONTROL_NO_BROADCAST",
            nonbroadcast_input_sha256=nonbroadcast_input_sha256,
            downstream_output_sha256=downstream_output_sha256,
            broadcast_id=None,
            broadcast_sha256=None,
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CausalInfluenceResult:
    schema: str
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
    classification: str = "MATCHED_CONTRACT_SCOPE_CAUSAL_EVIDENCE_NOT_HIDDEN_STATE_OR_WHOLE_SYSTEM_PROOF"

    def __post_init__(self) -> None:
        if self.schema != CAUSAL_INFLUENCE_RESULT_SCHEMA:
            raise GWTUptakeError("causal influence result schema mismatch")
        for name in (
            "result_id",
            "broadcast_id",
            "uptake_summary_id",
            "intervention_arm_id",
            "control_arm_id",
        ):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        for name in (
            "broadcast_sha256",
            "uptake_summary_sha256",
            "intervention_arm_sha256",
            "control_arm_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.status not in {
            "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE",
            "NO_CAUSAL_INFLUENCE_OBSERVED",
            "UNKNOWN_INSUFFICIENT_UPTAKE",
            "UNKNOWN_UNMATCHED_CONTROL",
        }:
            raise GWTUptakeError("unsupported causal influence result status")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def evaluate_causal_influence(
    *,
    result_id: str,
    broadcast: BroadcastEnvelope,
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    provenance_refs: Iterable[str],
) -> CausalInfluenceResult:
    if type(broadcast) is not BroadcastEnvelope:
        raise GWTUptakeError("broadcast must be concrete BroadcastEnvelope")
    if type(uptake_summary) is not UptakeSummary:
        raise GWTUptakeError("uptake_summary must be concrete UptakeSummary")
    if type(intervention) is not CausalProbeArm or type(control) is not CausalProbeArm:
        raise GWTUptakeError(
            "intervention and control must be concrete CausalProbeArm values"
        )
    if (
        intervention.condition != "INTERVENTION_BROADCAST"
        or control.condition != "CONTROL_NO_BROADCAST"
    ):
        raise GWTUptakeError("causal probe requires intervention and control conditions")
    if (
        uptake_summary.broadcast_id != broadcast.broadcast_id
        or uptake_summary.broadcast_sha256 != broadcast.sha256()
    ):
        raise GWTUptakeError("uptake summary broadcast binding mismatch")
    if (
        intervention.broadcast_id != broadcast.broadcast_id
        or intervention.broadcast_sha256 != broadcast.sha256()
    ):
        raise GWTUptakeError("intervention broadcast binding mismatch")

    if uptake_summary.status != "UPTAKE_OBSERVED":
        status = "UNKNOWN_INSUFFICIENT_UPTAKE"
    elif intervention.nonbroadcast_input_sha256 != control.nonbroadcast_input_sha256:
        status = "UNKNOWN_UNMATCHED_CONTROL"
    elif intervention.downstream_output_sha256 == control.downstream_output_sha256:
        status = "NO_CAUSAL_INFLUENCE_OBSERVED"
    else:
        status = "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"

    return CausalInfluenceResult(
        schema=CAUSAL_INFLUENCE_RESULT_SCHEMA,
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
    "CAUSAL_INFLUENCE_RESULT_SCHEMA",
    "CAUSAL_PROBE_ARM_SCHEMA",
    "CELL_UPTAKE_RECEIPT_SCHEMA",
    "UPTAKE_SUMMARY_SCHEMA",
    "CausalInfluenceResult",
    "CausalProbeArm",
    "CellUptakeReceipt",
    "GWTUptakeError",
    "UptakeSummary",
    "evaluate_causal_influence",
    "summarize_uptake",
]
