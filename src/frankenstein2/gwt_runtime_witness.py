"""Fail-closed live GWT delivery/uptake/re-entry observation binder.

F2-WP-900 generation 2 repository-component scope.

This module consumes the accepted WP506/WP507/WP508 semantic authorities and binds
three observations made by one executing Python process in strict monotonic order:

    delivery -> uptake -> re-entry

It does not create GWT semantics, infer hidden state, write UnifiedDB, authorize
effects, or mint target-runtime / GWT / J-Space / completion credit.  A later
external target/VPS run receipt must bind an exact source subject and execution
environment before any runtime promotion is possible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Iterable

from frankenstein2.grid10_interface import CellInput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import GwtReentryProvenanceWitness
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBinding,
    GwtReentryUptakeBindingError,
    validate_reentry_uptake_binding,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import BroadcastEnvelope, WorkspaceSelection

RUNTIME_OBSERVATION_SCHEMA = "FRANKENSTEIN2_GWT_RUNTIME_OBSERVATION/v1"
RUNTIME_WITNESS_SCHEMA = "FRANKENSTEIN2_GWT_RUNTIME_WITNESS/v1"
_OBSERVATION_CLASSIFICATION = (
    "PROCESS_LOCAL_GWT_OBSERVATION_NOT_TARGET_RUNTIME_OR_GWT_CREDIT_AUTHORITY"
)
_WITNESS_CLASSIFICATION = (
    "ORDERED_PROCESS_OBSERVATION_BINDING_NOT_TARGET_RUNTIME_GWT_JSPACE_EFFECT_OR_COMPLETION_AUTHORITY"
)
_STAGE_ORDER = ("DELIVERY", "UPTAKE", "REENTRY")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_OBSERVATION_SEAL = object()
_PROCESS_START_NS = time.monotonic_ns()


class GwtRuntimeWitnessError(ValueError):
    """Fail-closed F2-WP-900 generation-2 runtime-witness error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtRuntimeWitnessError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise GwtRuntimeWitnessError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtRuntimeWitnessError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise GwtRuntimeWitnessError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtRuntimeWitnessError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtRuntimeWitnessError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS:
        raise GwtRuntimeWitnessError(f"provenance_refs exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise GwtRuntimeWitnessError("provenance_refs must not contain duplicates")
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
        raise GwtRuntimeWitnessError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_PROCESS_ID = "gwt-process:" + _digest(
    {
        "pid": os.getpid(),
        "executable": sys.executable,
        "module_start_monotonic_ns": _PROCESS_START_NS,
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtRuntimeObservation:
    stage: str
    ordinal: int
    process_id: str
    window_id: str
    source_sha256: str
    observed_monotonic_ns: int
    broadcast_id: str
    broadcast_sha256: str
    recipient_cell_id: str
    evidence_ref: str
    evidence_sha256: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = RUNTIME_OBSERVATION_SCHEMA
    classification = _OBSERVATION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.stage not in _STAGE_ORDER:
            raise GwtRuntimeWitnessError("unsupported observation stage")
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise GwtRuntimeWitnessError("observation ordinal must be a non-negative integer")
        for name in (
            "process_id",
            "window_id",
            "broadcast_id",
            "recipient_cell_id",
            "evidence_ref",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in ("source_sha256", "broadcast_sha256", "evidence_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if type(self.observed_monotonic_ns) is not int or self.observed_monotonic_ns <= 0:
            raise GwtRuntimeWitnessError("observed_monotonic_ns must be a positive integer")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "stage": self.stage,
            "ordinal": self.ordinal,
            "process_id": self.process_id,
            "window_id": self.window_id,
            "source_sha256": self.source_sha256,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "evidence_ref": self.evidence_ref,
            "evidence_sha256": self.evidence_sha256,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _seal_observation(observation: GwtRuntimeObservation) -> GwtRuntimeObservation:
    object.__setattr__(observation, "_factory_payload_sha256", observation.sha256())
    return observation


def _assert_live_observation(observation: GwtRuntimeObservation) -> None:
    if type(observation) is not GwtRuntimeObservation:
        raise GwtRuntimeWitnessError("observation must be exact GwtRuntimeObservation")
    if observation._factory_seal is not _OBSERVATION_SEAL:
        raise GwtRuntimeWitnessError("observation lacks live process factory origin")
    if observation.process_id != _PROCESS_ID:
        raise GwtRuntimeWitnessError("cross-process observation is forbidden")
    if observation._factory_payload_sha256 != observation.sha256():
        raise GwtRuntimeWitnessError("observation payload changed after capture")


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtRuntimeWitness:
    witness_id: str
    process_id: str
    window_id: str
    source_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    recipient_cell_id: str
    observation_sha256s: tuple[str, str, str]
    delivery_receipt_id: str
    delivery_receipt_sha256: str
    uptake_receipt_id: str
    uptake_receipt_sha256: str
    reentry_binding_id: str
    reentry_binding_sha256: str
    first_monotonic_ns: int
    last_monotonic_ns: int
    provenance_refs: tuple[str, ...]

    schema = RUNTIME_WITNESS_SCHEMA
    classification = _WITNESS_CLASSIFICATION

    def __post_init__(self) -> None:
        for name in (
            "witness_id",
            "process_id",
            "window_id",
            "broadcast_id",
            "recipient_cell_id",
            "delivery_receipt_id",
            "uptake_receipt_id",
            "reentry_binding_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "source_sha256",
            "broadcast_sha256",
            "delivery_receipt_sha256",
            "uptake_receipt_sha256",
            "reentry_binding_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if type(self.observation_sha256s) is not tuple or len(self.observation_sha256s) != 3:
            raise GwtRuntimeWitnessError("witness requires exactly three observation digests")
        for value in self.observation_sha256s:
            _sha256("observation_sha256", value)
        if (
            type(self.first_monotonic_ns) is not int
            or type(self.last_monotonic_ns) is not int
            or self.first_monotonic_ns <= 0
            or self.last_monotonic_ns <= self.first_monotonic_ns
        ):
            raise GwtRuntimeWitnessError("witness monotonic window is invalid")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))
        expected = "gwt-runtime-witness:" + _digest(self.identity_payload())
        if self.witness_id != expected:
            raise GwtRuntimeWitnessError("witness_id does not bind exact runtime observation payload")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "process_id": self.process_id,
            "window_id": self.window_id,
            "source_sha256": self.source_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "observation_sha256s": list(self.observation_sha256s),
            "delivery_receipt_id": self.delivery_receipt_id,
            "delivery_receipt_sha256": self.delivery_receipt_sha256,
            "uptake_receipt_id": self.uptake_receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "reentry_binding_id": self.reentry_binding_id,
            "reentry_binding_sha256": self.reentry_binding_sha256,
            "first_monotonic_ns": self.first_monotonic_ns,
            "last_monotonic_ns": self.last_monotonic_ns,
            "provenance_refs": list(self.provenance_refs),
            "process_observation_bound": True,
            "target_environment_component_runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "effect_credit": 0,
            "training_credit": 0,
            "completion_credit": 0,
            "whole_system_acceptance": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {"witness_id": self.witness_id, **self.identity_payload()}

    def sha256(self) -> str:
        return _digest(self.as_dict())


class GwtRuntimeObservationWindow:
    """One process-local, single-broadcast, strict-order observation window."""

    __slots__ = (
        "window_id",
        "source_sha256",
        "process_id",
        "_observations",
        "_last_monotonic_ns",
        "_closed",
    )

    def __init__(self, *, window_id: str, source_sha256: str) -> None:
        self.window_id = _text("window_id", window_id)
        self.source_sha256 = _sha256("source_sha256", source_sha256)
        self.process_id = _PROCESS_ID
        self._observations: list[GwtRuntimeObservation] = []
        self._last_monotonic_ns = 0
        self._closed = False

    @classmethod
    def open(cls, *, window_id: str, source_sha256: str) -> "GwtRuntimeObservationWindow":
        return cls(window_id=window_id, source_sha256=source_sha256)

    @property
    def observations(self) -> tuple[GwtRuntimeObservation, ...]:
        return tuple(self._observations)

    def _capture(
        self,
        *,
        stage: str,
        broadcast: BroadcastEnvelope,
        recipient_cell_id: str,
        evidence_ref: str,
        evidence_sha256: str,
        provenance_refs: Iterable[str],
    ) -> GwtRuntimeObservation:
        if self._closed:
            raise GwtRuntimeWitnessError("observation window is already closed")
        expected_stage = _STAGE_ORDER[len(self._observations)] if len(self._observations) < 3 else None
        if stage != expected_stage:
            raise GwtRuntimeWitnessError(f"observation stage must be strict {_STAGE_ORDER!r} order")
        if type(broadcast) is not BroadcastEnvelope:
            raise GwtRuntimeWitnessError("broadcast must be exact BroadcastEnvelope")
        now = time.monotonic_ns()
        if now <= self._last_monotonic_ns:
            raise GwtRuntimeWitnessError("monotonic observation clock did not advance")
        self._last_monotonic_ns = now
        observation = GwtRuntimeObservation(
            stage=stage,
            ordinal=len(self._observations),
            process_id=self.process_id,
            window_id=self.window_id,
            source_sha256=self.source_sha256,
            observed_monotonic_ns=now,
            broadcast_id=broadcast.broadcast_id,
            broadcast_sha256=broadcast.sha256(),
            recipient_cell_id=_text("recipient_cell_id", recipient_cell_id),
            evidence_ref=_text("evidence_ref", evidence_ref),
            evidence_sha256=_sha256("evidence_sha256", evidence_sha256),
            provenance_refs=tuple(provenance_refs),
            _factory_seal=_OBSERVATION_SEAL,
        )
        _seal_observation(observation)
        self._observations.append(observation)
        return observation

    def observe_delivery(
        self,
        *,
        broadcast: BroadcastEnvelope,
        uptake_receipt: CellUptakeReceipt,
        provenance_refs: Iterable[str],
    ) -> GwtRuntimeObservation:
        if type(uptake_receipt) is not CellUptakeReceipt:
            raise GwtRuntimeWitnessError("uptake_receipt must be exact CellUptakeReceipt")
        try:
            uptake_receipt.assert_broadcast_binding(broadcast)
        except GWTUptakeError as exc:
            raise GwtRuntimeWitnessError(f"delivery receipt binding failed: {exc}") from exc
        if uptake_receipt.delivery_status != "DELIVERED":
            raise GwtRuntimeWitnessError("delivery observation requires DELIVERED receipt")
        return self._capture(
            stage="DELIVERY",
            broadcast=broadcast,
            recipient_cell_id=uptake_receipt.cell_id,
            evidence_ref=uptake_receipt.receipt_id,
            evidence_sha256=uptake_receipt.sha256(),
            provenance_refs=provenance_refs,
        )

    def observe_uptake(
        self,
        *,
        broadcast: BroadcastEnvelope,
        uptake_receipt: CellUptakeReceipt,
        provenance_refs: Iterable[str],
    ) -> GwtRuntimeObservation:
        if type(uptake_receipt) is not CellUptakeReceipt:
            raise GwtRuntimeWitnessError("uptake_receipt must be exact CellUptakeReceipt")
        try:
            uptake_receipt.assert_broadcast_binding(broadcast)
        except GWTUptakeError as exc:
            raise GwtRuntimeWitnessError(f"uptake receipt binding failed: {exc}") from exc
        if uptake_receipt.uptake_status != "UPTAKEN":
            raise GwtRuntimeWitnessError("uptake observation requires UPTAKEN receipt")
        return self._capture(
            stage="UPTAKE",
            broadcast=broadcast,
            recipient_cell_id=uptake_receipt.cell_id,
            evidence_ref=uptake_receipt.receipt_id,
            evidence_sha256=uptake_receipt.sha256(),
            provenance_refs=provenance_refs,
        )

    def observe_reentry(
        self,
        *,
        binding: GwtReentryUptakeBinding,
        witness: GwtReentryProvenanceWitness,
        uptake_receipt: CellUptakeReceipt,
        plan: Grid10Plan,
        selection: WorkspaceSelection,
        broadcast: BroadcastEnvelope,
        cell_input: CellInput,
        known_lineage_refs: Iterable[str] = (),
        provenance_refs: Iterable[str],
    ) -> GwtRuntimeObservation:
        try:
            validate_reentry_uptake_binding(
                binding,
                witness=witness,
                uptake_receipt=uptake_receipt,
                plan=plan,
                selection=selection,
                broadcast=broadcast,
                cell_input=cell_input,
                known_lineage_refs=known_lineage_refs,
            )
        except GwtReentryUptakeBindingError as exc:
            raise GwtRuntimeWitnessError(f"re-entry binding validation failed: {exc}") from exc
        if binding.uptake_status != "UPTAKEN":
            raise GwtRuntimeWitnessError("re-entry runtime witness requires UPTAKEN binding")
        return self._capture(
            stage="REENTRY",
            broadcast=broadcast,
            recipient_cell_id=binding.recipient_cell_id,
            evidence_ref=binding.binding_id,
            evidence_sha256=binding.sha256(),
            provenance_refs=provenance_refs,
        )

    def finalize(self, *, provenance_refs: Iterable[str]) -> GwtRuntimeWitness:
        if self._closed:
            raise GwtRuntimeWitnessError("observation window is already closed")
        observations = tuple(self._observations)
        if len(observations) != 3:
            raise GwtRuntimeWitnessError("runtime witness requires delivery, uptake and re-entry observations")
        for observation in observations:
            _assert_live_observation(observation)
        if tuple(item.stage for item in observations) != _STAGE_ORDER:
            raise GwtRuntimeWitnessError("runtime observations are reordered")
        if tuple(item.ordinal for item in observations) != (0, 1, 2):
            raise GwtRuntimeWitnessError("runtime observation ordinals are invalid")
        if len({item.process_id for item in observations}) != 1 or observations[0].process_id != self.process_id:
            raise GwtRuntimeWitnessError("runtime observations cross process identity")
        if len({item.window_id for item in observations}) != 1 or observations[0].window_id != self.window_id:
            raise GwtRuntimeWitnessError("runtime observations cross observation windows")
        if len({item.source_sha256 for item in observations}) != 1 or observations[0].source_sha256 != self.source_sha256:
            raise GwtRuntimeWitnessError("runtime observations cross source subjects")
        if len({item.broadcast_id for item in observations}) != 1 or len({item.broadcast_sha256 for item in observations}) != 1:
            raise GwtRuntimeWitnessError("runtime observations cross broadcast identity")
        if len({item.recipient_cell_id for item in observations}) != 1:
            raise GwtRuntimeWitnessError("runtime observations cross recipient identity")
        times = tuple(item.observed_monotonic_ns for item in observations)
        if not times[0] < times[1] < times[2]:
            raise GwtRuntimeWitnessError("runtime observation order is not strictly monotonic")

        refs = _refs(provenance_refs)
        payload = {
            "schema": RUNTIME_WITNESS_SCHEMA,
            "classification": _WITNESS_CLASSIFICATION,
            "process_id": self.process_id,
            "window_id": self.window_id,
            "source_sha256": self.source_sha256,
            "broadcast_id": observations[0].broadcast_id,
            "broadcast_sha256": observations[0].broadcast_sha256,
            "recipient_cell_id": observations[0].recipient_cell_id,
            "observation_sha256s": [item.sha256() for item in observations],
            "delivery_receipt_id": observations[0].evidence_ref,
            "delivery_receipt_sha256": observations[0].evidence_sha256,
            "uptake_receipt_id": observations[1].evidence_ref,
            "uptake_receipt_sha256": observations[1].evidence_sha256,
            "reentry_binding_id": observations[2].evidence_ref,
            "reentry_binding_sha256": observations[2].evidence_sha256,
            "first_monotonic_ns": times[0],
            "last_monotonic_ns": times[2],
            "provenance_refs": list(refs),
            "process_observation_bound": True,
            "target_environment_component_runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "effect_credit": 0,
            "training_credit": 0,
            "completion_credit": 0,
            "whole_system_acceptance": False,
        }
        result = GwtRuntimeWitness(
            witness_id="gwt-runtime-witness:" + _digest(payload),
            process_id=self.process_id,
            window_id=self.window_id,
            source_sha256=self.source_sha256,
            broadcast_id=observations[0].broadcast_id,
            broadcast_sha256=observations[0].broadcast_sha256,
            recipient_cell_id=observations[0].recipient_cell_id,
            observation_sha256s=tuple(item.sha256() for item in observations),
            delivery_receipt_id=observations[0].evidence_ref,
            delivery_receipt_sha256=observations[0].evidence_sha256,
            uptake_receipt_id=observations[1].evidence_ref,
            uptake_receipt_sha256=observations[1].evidence_sha256,
            reentry_binding_id=observations[2].evidence_ref,
            reentry_binding_sha256=observations[2].evidence_sha256,
            first_monotonic_ns=times[0],
            last_monotonic_ns=times[2],
            provenance_refs=refs,
        )
        self._closed = True
        return result


def create_runtime_witness_from_observations(
    observations: Iterable[GwtRuntimeObservation],
    *,
    provenance_refs: Iterable[str],
) -> GwtRuntimeWitness:
    """Validate a live observation tuple without allowing caller-supplied runtime strings.

    All observations must still carry their current process-local factory seals.
    Serialized observations are therefore evidence material, not runtime authority.
    """
    values = tuple(observations)
    if len(values) != 3:
        raise GwtRuntimeWitnessError("exactly three live observations are required")
    for item in values:
        _assert_live_observation(item)
    if tuple(item.stage for item in values) != _STAGE_ORDER:
        raise GwtRuntimeWitnessError("runtime observations are reordered")
    if len({item.process_id for item in values}) != 1 or values[0].process_id != _PROCESS_ID:
        raise GwtRuntimeWitnessError("runtime observations cross process identity")
    if len({item.window_id for item in values}) != 1:
        raise GwtRuntimeWitnessError("runtime observations cross observation windows")
    window = GwtRuntimeObservationWindow.open(
        window_id=values[0].window_id,
        source_sha256=values[0].source_sha256,
    )
    window._observations.extend(values)
    window._last_monotonic_ns = values[-1].observed_monotonic_ns
    return window.finalize(provenance_refs=provenance_refs)


__all__ = [
    "GwtRuntimeObservation",
    "GwtRuntimeObservationWindow",
    "GwtRuntimeWitness",
    "GwtRuntimeWitnessError",
    "RUNTIME_OBSERVATION_SCHEMA",
    "RUNTIME_WITNESS_SCHEMA",
    "create_runtime_witness_from_observations",
]
