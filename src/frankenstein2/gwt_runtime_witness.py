"""Fail-closed runtime observation binder for the accepted F2 GWT path.

F2-WP-900 generation 2 repository-component scope.

The accepted WP506/WP507/WP508 contracts deliberately distinguish constructed
selection/broadcast, uptake receipts and re-entry lineage from runtime execution.
This module supplies the missing observation boundary: a runtime integration can
call one recorder at the points where it actually delivers a broadcast, observes
its uptake result and observes the corresponding re-entry.

The recorder revalidates the exact accepted objects, binds all three observations
to one process/boot/source identity and a strictly increasing monotonic window,
and emits an immutable evidence *candidate*.  Neither constructing a recorder nor
sealing a receipt grants runtime, GWT/J-Space, effect, completion, training or
whole-system credit.  Such credit remains external evidence/reconciliation work
and requires an admitted target execution of the exact source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable

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
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import BroadcastEnvelope, WorkspaceSelection

GWT_RUNTIME_WITNESS_SCHEMA = "FRANKENSTEIN2_GWT_RUNTIME_WITNESS/v1"
LIVE_GWT_PATH_OBSERVED = "LIVE_GWT_PATH_OBSERVED"
DELIVERY_NOT_OBSERVED = "DELIVERY_NOT_OBSERVED"
UPTAKE_NOT_OBSERVED = "UPTAKE_NOT_OBSERVED"
_RECORDED = object()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512


class GwtRuntimeWitnessError(ValueError):
    """Fail-closed WP900 G2 runtime-witness validation error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtRuntimeWitnessError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise GwtRuntimeWitnessError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtRuntimeWitnessError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise GwtRuntimeWitnessError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtRuntimeWitnessError(f"{name} must be a positive integer")
    return value


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
        raise GwtRuntimeWitnessError("runtime witness is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeObservationIdentity:
    """Identity of one external execution context, supplied by the runtime harness."""

    runtime_instance_id: str
    process_identity: str
    boot_id_sha256: str
    exact_source_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_instance_id", _text("runtime_instance_id", self.runtime_instance_id))
        object.__setattr__(self, "process_identity", _text("process_identity", self.process_identity))
        object.__setattr__(self, "boot_id_sha256", _sha256("boot_id_sha256", self.boot_id_sha256))
        object.__setattr__(self, "exact_source_sha256", _sha256("exact_source_sha256", self.exact_source_sha256))

    def as_dict(self) -> dict[str, str]:
        return {
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "boot_id_sha256": self.boot_id_sha256,
            "exact_source_sha256": self.exact_source_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeObservationEvent:
    """One recorder-origin observation; never standalone runtime authority."""

    phase: str
    observed_monotonic_ns: int
    object_id: str
    object_sha256: str
    _recorder_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        if self.phase not in {"DELIVERY", "UPTAKE", "REENTRY"}:
            raise GwtRuntimeWitnessError("unsupported runtime observation phase")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "object_id", _text("object_id", self.object_id))
        object.__setattr__(self, "object_sha256", _sha256("object_sha256", self.object_sha256))

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "object_id": self.object_id,
            "object_sha256": self.object_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtRuntimeWitnessReceipt:
    schema: str
    identity: RuntimeObservationIdentity
    broadcast_id: str
    broadcast_sha256: str
    recipient_cell_id: str
    uptake_receipt_id: str
    uptake_receipt_sha256: str
    canonical_reentry_key: str
    reentry_witness_sha256: str
    binding_id: str
    binding_sha256: str
    delivery_status: str
    uptake_status: str
    events: tuple[RuntimeObservationEvent, RuntimeObservationEvent, RuntimeObservationEvent]
    classification: str
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    evidence_scope = "RUNTIME_OBSERVATION_CANDIDATE_REQUIRES_EXTERNAL_EXECUTION_ADMISSION"
    runtime_credit = 0
    physical_grid10_credit = 0
    gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    completion_credit = 0
    training_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if self.schema != GWT_RUNTIME_WITNESS_SCHEMA:
            raise GwtRuntimeWitnessError("runtime witness schema mismatch")
        if type(self.identity) is not RuntimeObservationIdentity:
            raise GwtRuntimeWitnessError("identity must be exact RuntimeObservationIdentity")
        for name in ("broadcast_id", "recipient_cell_id", "uptake_receipt_id", "binding_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "broadcast_sha256",
            "uptake_receipt_sha256",
            "canonical_reentry_key",
            "reentry_witness_sha256",
            "binding_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.delivery_status not in {"OFFERED", "DELIVERED", "NOT_OBSERVED"}:
            raise GwtRuntimeWitnessError("unsupported delivery_status")
        if self.uptake_status not in {"UPTAKEN", "NOT_UPTAKEN", "UNKNOWN"}:
            raise GwtRuntimeWitnessError("unsupported uptake_status")
        if type(self.events) is not tuple or len(self.events) != 3:
            raise GwtRuntimeWitnessError("events must contain exactly DELIVERY, UPTAKE and REENTRY")
        if tuple(event.phase for event in self.events) != ("DELIVERY", "UPTAKE", "REENTRY"):
            raise GwtRuntimeWitnessError("runtime observation phases must be DELIVERY -> UPTAKE -> REENTRY")
        if any(type(event) is not RuntimeObservationEvent or event._recorder_seal is not _RECORDED for event in self.events):
            raise GwtRuntimeWitnessError("runtime observation event lacks recorder origin")
        times = tuple(event.observed_monotonic_ns for event in self.events)
        if not (times[0] < times[1] < times[2]):
            raise GwtRuntimeWitnessError("runtime observation times must be strictly increasing")
        expected_classification = (
            LIVE_GWT_PATH_OBSERVED
            if self.delivery_status == "DELIVERED" and self.uptake_status == "UPTAKEN"
            else DELIVERY_NOT_OBSERVED
            if self.delivery_status != "DELIVERED"
            else UPTAKE_NOT_OBSERVED
        )
        if self.classification != expected_classification:
            raise GwtRuntimeWitnessError("runtime witness classification mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.as_dict(),
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "uptake_receipt_id": self.uptake_receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "canonical_reentry_key": self.canonical_reentry_key,
            "reentry_witness_sha256": self.reentry_witness_sha256,
            "binding_id": self.binding_id,
            "binding_sha256": self.binding_sha256,
            "delivery_status": self.delivery_status,
            "uptake_status": self.uptake_status,
            "events": [event.as_dict() for event in self.events],
            "classification": self.classification,
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "effect_credit": self.effect_credit,
            "completion_credit": self.completion_credit,
            "training_credit": self.training_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


MonotonicNs = Callable[[], int]


class GwtRuntimeWitnessRecorder:
    """Stateful hook target for one actually executing GWT path.

    Repository tests can exercise this recorder, but that only proves its fail-closed
    behavior.  Promotion requires an admitted external runtime to call these hooks at
    its real delivery/uptake/re-entry boundaries and preserve the resulting receipt.
    """

    def __init__(self, *, identity: RuntimeObservationIdentity, monotonic_ns: MonotonicNs) -> None:
        if type(identity) is not RuntimeObservationIdentity:
            raise GwtRuntimeWitnessError("identity must be exact RuntimeObservationIdentity")
        if not callable(monotonic_ns):
            raise GwtRuntimeWitnessError("monotonic_ns must be callable")
        self._identity = identity
        self._clock = monotonic_ns
        self._broadcast: BroadcastEnvelope | None = None
        self._receipt: CellUptakeReceipt | None = None
        self._witness: GwtReentryProvenanceWitness | None = None
        self._binding: GwtReentryUptakeBinding | None = None
        self._events: list[RuntimeObservationEvent] = []
        self._sealed = False

    def _event(self, phase: str, object_id: str, object_sha256: str) -> RuntimeObservationEvent:
        if self._sealed:
            raise GwtRuntimeWitnessError("runtime recorder is already sealed")
        event = RuntimeObservationEvent(
            phase=phase,
            observed_monotonic_ns=_positive_int("monotonic_ns", self._clock()),
            object_id=object_id,
            object_sha256=object_sha256,
            _recorder_seal=_RECORDED,
        )
        if self._events and event.observed_monotonic_ns <= self._events[-1].observed_monotonic_ns:
            raise GwtRuntimeWitnessError("runtime clock did not advance monotonically")
        self._events.append(event)
        return event

    def observe_delivery(self, broadcast: BroadcastEnvelope) -> None:
        if self._broadcast is not None:
            raise GwtRuntimeWitnessError("delivery observation already recorded")
        if type(broadcast) is not BroadcastEnvelope:
            raise GwtRuntimeWitnessError("broadcast must be exact BroadcastEnvelope")
        self._broadcast = broadcast
        self._event("DELIVERY", broadcast.broadcast_id, broadcast.sha256())

    def observe_uptake(self, receipt: CellUptakeReceipt) -> None:
        if self._broadcast is None:
            raise GwtRuntimeWitnessError("delivery must be observed before uptake")
        if self._receipt is not None:
            raise GwtRuntimeWitnessError("uptake observation already recorded")
        if type(receipt) is not CellUptakeReceipt:
            raise GwtRuntimeWitnessError("uptake receipt must be exact CellUptakeReceipt")
        try:
            receipt.assert_broadcast_binding(self._broadcast)
        except GWTUptakeError as exc:
            raise GwtRuntimeWitnessError(f"invalid uptake observation: {exc}") from exc
        self._receipt = receipt
        self._event("UPTAKE", receipt.receipt_id, receipt.sha256())

    def observe_reentry(
        self,
        *,
        witness: GwtReentryProvenanceWitness,
        binding: GwtReentryUptakeBinding,
        plan: Grid10Plan,
        selection: WorkspaceSelection,
        cell_input: CellInput,
    ) -> None:
        if self._broadcast is None or self._receipt is None:
            raise GwtRuntimeWitnessError("delivery and uptake must be observed before re-entry")
        if self._witness is not None:
            raise GwtRuntimeWitnessError("re-entry observation already recorded")
        if type(witness) is not GwtReentryProvenanceWitness:
            raise GwtRuntimeWitnessError("witness must be exact GwtReentryProvenanceWitness")
        if type(binding) is not GwtReentryUptakeBinding:
            raise GwtRuntimeWitnessError("binding must be exact GwtReentryUptakeBinding")
        try:
            validate_reentry_witness(
                witness,
                plan=plan,
                selection=selection,
                broadcast=self._broadcast,
                cell_input=cell_input,
            )
            assert_reentry_uptake_binding_factory_origin(binding)
            validate_reentry_uptake_binding(
                binding,
                witness=witness,
                uptake_receipt=self._receipt,
                plan=plan,
                selection=selection,
                broadcast=self._broadcast,
                cell_input=cell_input,
            )
        except ValueError as exc:
            raise GwtRuntimeWitnessError(f"invalid re-entry observation: {exc}") from exc
        self._witness = witness
        self._binding = binding
        self._event("REENTRY", witness.canonical_reentry_key(), witness.sha256())

    def seal(self) -> GwtRuntimeWitnessReceipt:
        if self._sealed:
            raise GwtRuntimeWitnessError("runtime recorder is already sealed")
        if self._broadcast is None or self._receipt is None or self._witness is None or self._binding is None:
            raise GwtRuntimeWitnessError("delivery, uptake and re-entry must all be observed before seal")
        if self._receipt.cell_id != self._witness.recipient_cell_id:
            raise GwtRuntimeWitnessError("uptake/re-entry recipient mismatch")
        if self._binding.broadcast_id != self._broadcast.broadcast_id or self._binding.broadcast_sha256 != self._broadcast.sha256():
            raise GwtRuntimeWitnessError("binding/broadcast identity mismatch")
        classification = (
            LIVE_GWT_PATH_OBSERVED
            if self._receipt.delivery_status == "DELIVERED" and self._receipt.uptake_status == "UPTAKEN"
            else DELIVERY_NOT_OBSERVED
            if self._receipt.delivery_status != "DELIVERED"
            else UPTAKE_NOT_OBSERVED
        )
        receipt = GwtRuntimeWitnessReceipt(
            schema=GWT_RUNTIME_WITNESS_SCHEMA,
            identity=self._identity,
            broadcast_id=self._broadcast.broadcast_id,
            broadcast_sha256=self._broadcast.sha256(),
            recipient_cell_id=self._receipt.cell_id,
            uptake_receipt_id=self._receipt.receipt_id,
            uptake_receipt_sha256=self._receipt.sha256(),
            canonical_reentry_key=self._witness.canonical_reentry_key(),
            reentry_witness_sha256=self._witness.sha256(),
            binding_id=self._binding.binding_id,
            binding_sha256=self._binding.sha256(),
            delivery_status=self._receipt.delivery_status,
            uptake_status=self._receipt.uptake_status,
            events=tuple(self._events),
            classification=classification,
            _factory_seal=_RECORDED,
        )
        object.__setattr__(receipt, "_factory_payload_sha256", _digest(receipt.as_dict()))
        self._sealed = True
        return receipt


def validate_gwt_runtime_witness_receipt(receipt: GwtRuntimeWitnessReceipt) -> None:
    """Verify recorder origin and immutability; never promote evidence scope."""
    if type(receipt) is not GwtRuntimeWitnessReceipt or receipt._factory_seal is not _RECORDED:
        raise GwtRuntimeWitnessError("runtime witness receipt lacks recorder factory origin")
    if receipt._factory_payload_sha256 != _digest(receipt.as_dict()):
        raise GwtRuntimeWitnessError("runtime witness receipt payload changed after seal")


__all__ = [
    "DELIVERY_NOT_OBSERVED",
    "GWT_RUNTIME_WITNESS_SCHEMA",
    "GwtRuntimeWitnessError",
    "GwtRuntimeWitnessReceipt",
    "GwtRuntimeWitnessRecorder",
    "LIVE_GWT_PATH_OBSERVED",
    "RuntimeObservationEvent",
    "RuntimeObservationIdentity",
    "UPTAKE_NOT_OBSERVED",
    "validate_gwt_runtime_witness_receipt",
]
