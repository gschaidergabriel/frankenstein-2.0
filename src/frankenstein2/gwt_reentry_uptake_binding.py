"""Deterministic binding between accepted WP508 re-entry provenance and WP507 uptake evidence.

F2-WP-508 generation 4 component scope only.

This module does not observe or infer uptake. It verifies that one already-valid WP508
re-entry witness and one already-valid WP507 CellUptakeReceipt refer to the same exact
broadcast and recipient, revalidates accepted WP506 selection and broadcast builder lineage,
then preserves the WP507 delivery/uptake state verbatim.
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
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import (
    BroadcastEnvelope,
    GwtWorkspaceError,
    WorkspaceSelection,
    verify_selection_binding,
)

GWT_REENTRY_UPTAKE_BINDING_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_UPTAKE_BINDING/v1"
_CLASSIFICATION = "DERIVED_BINDING_WP507_UPTAKE_AUTHORITY_ONLY_NOT_NEW_UPTAKE_OR_RUNTIME_EVIDENCE"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_BINDING_SEAL = object()


class GwtReentryUptakeBindingError(ValueError):
    """Fail-closed WP508 generation-4 integration error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GwtReentryUptakeBindingError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise GwtReentryUptakeBindingError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtReentryUptakeBindingError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GwtReentryUptakeBindingError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtReentryUptakeBindingError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtReentryUptakeBindingError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS:
        raise GwtReentryUptakeBindingError(f"provenance_refs exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise GwtReentryUptakeBindingError("provenance_refs must not contain duplicates")
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


def _binding_status(uptake_status: str) -> str:
    if uptake_status == "UPTAKEN":
        return "WP507_UPTAKEN_BOUND"
    if uptake_status == "NOT_UPTAKEN":
        return "WP507_NOT_UPTAKEN_BOUND"
    if uptake_status == "UNKNOWN":
        return "WP507_UNKNOWN_BOUND"
    raise GwtReentryUptakeBindingError("unsupported WP507 uptake status")


def _validate_wp506_reentry_lineage(
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
) -> None:
    """Revalidate exact WP506 selection/broadcast lineage and material payload re-entry."""
    try:
        verify_selection_binding(
            selection,
            expected_generation=broadcast.selection_generation,
            expected_selection_sha256=broadcast.selection_sha256,
            frame_id=plan.frame_id,
            frame_generation=plan.frame_generation,
            frame_sha256=plan.frame_sha256,
            grid_plan_id=plan.plan_id,
            grid_plan_generation=plan.generation,
            grid_plan_sha256=plan.sha256(),
        )
    except GwtWorkspaceError as exc:
        raise GwtReentryUptakeBindingError(
            f"invalid WP506 selection builder lineage: {exc}"
        ) from exc

    expected_candidate_ids = tuple(candidate.candidate_id for candidate in selection.selected)
    expected_payload_refs = tuple(candidate.payload_ref for candidate in selection.selected)
    if broadcast.candidate_ids != expected_candidate_ids:
        raise GwtReentryUptakeBindingError(
            "broadcast candidate-id lineage does not match exact WorkspaceSelection.selected"
        )
    if broadcast.candidate_payload_refs != expected_payload_refs:
        raise GwtReentryUptakeBindingError(
            "broadcast payload lineage does not match exact WorkspaceSelection.selected"
        )

    broadcast_payload_refs = set(expected_payload_refs)
    if not broadcast_payload_refs.intersection(cell_input.input_refs):
        raise GwtReentryUptakeBindingError(
            "re-entry CellInput lacks bound broadcast candidate payload reference"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtReentryUptakeBinding:
    binding_id: str
    canonical_reentry_key: str
    reentry_witness_sha256: str
    uptake_receipt_id: str
    uptake_receipt_sha256: str
    broadcast_id: str
    broadcast_generation: int
    broadcast_sha256: str
    recipient_cell_id: str
    delivery_status: str
    uptake_status: str
    downstream_ref: str | None
    downstream_sha256: str | None
    binding_status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    schema = GWT_REENTRY_UPTAKE_BINDING_SCHEMA
    classification = _CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", _text("binding_id", self.binding_id))
        object.__setattr__(
            self,
            "canonical_reentry_key",
            _sha256("canonical_reentry_key", self.canonical_reentry_key),
        )
        object.__setattr__(
            self,
            "reentry_witness_sha256",
            _sha256("reentry_witness_sha256", self.reentry_witness_sha256),
        )
        object.__setattr__(
            self,
            "uptake_receipt_sha256",
            _sha256("uptake_receipt_sha256", self.uptake_receipt_sha256),
        )
        object.__setattr__(self, "uptake_receipt_id", _text("uptake_receipt_id", self.uptake_receipt_id))
        object.__setattr__(self, "broadcast_id", _text("broadcast_id", self.broadcast_id))
        if type(self.broadcast_generation) is not int or self.broadcast_generation < 0:
            raise GwtReentryUptakeBindingError("broadcast_generation must be a non-negative integer")
        object.__setattr__(
            self,
            "broadcast_sha256",
            _sha256("broadcast_sha256", self.broadcast_sha256),
        )
        object.__setattr__(self, "recipient_cell_id", _text("recipient_cell_id", self.recipient_cell_id))
        expected_status = _binding_status(self.uptake_status)
        if self.binding_status != expected_status:
            raise GwtReentryUptakeBindingError("binding_status must preserve WP507 uptake_status exactly")
        if self.uptake_status == "UPTAKEN":
            if self.delivery_status != "DELIVERED":
                raise GwtReentryUptakeBindingError("UPTAKEN binding requires WP507 DELIVERED evidence")
            if self.downstream_ref is None or self.downstream_sha256 is None:
                raise GwtReentryUptakeBindingError("UPTAKEN binding requires WP507 downstream evidence")
        elif self.downstream_ref is not None or self.downstream_sha256 is not None:
            raise GwtReentryUptakeBindingError("non-UPTAKEN binding must not mint downstream evidence")
        if self.downstream_ref is not None:
            object.__setattr__(self, "downstream_ref", _text("downstream_ref", self.downstream_ref))
            object.__setattr__(
                self,
                "downstream_sha256",
                _sha256("downstream_sha256", self.downstream_sha256),
            )
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "binding_id": self.binding_id,
            "canonical_reentry_key": self.canonical_reentry_key,
            "reentry_witness_sha256": self.reentry_witness_sha256,
            "uptake_receipt_id": self.uptake_receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_generation": self.broadcast_generation,
            "broadcast_sha256": self.broadcast_sha256,
            "recipient_cell_id": self.recipient_cell_id,
            "delivery_status": self.delivery_status,
            "uptake_status": self.uptake_status,
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "binding_status": self.binding_status,
            "provenance_refs": list(self.provenance_refs),
            "uptake_authority": "WP507_CELL_UPTAKE_RECEIPT_ONLY",
            "reentry_authority": "WP508_G1_CANONICAL_REENTRY_WITNESS_ONLY",
            "causal_influence_claim": "NOT_ESTABLISHED_BY_BINDING",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "training_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_reentry_to_uptake(
    *,
    binding_id: str,
    witness: GwtReentryProvenanceWitness,
    uptake_receipt: CellUptakeReceipt,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
    known_lineage_refs: Iterable[str] = (),
    provenance_refs: Iterable[str],
) -> GwtReentryUptakeBinding:
    """Bind exact existing evidence without creating a new uptake observation."""
    if type(witness) is not GwtReentryProvenanceWitness:
        raise GwtReentryUptakeBindingError("witness must be concrete GwtReentryProvenanceWitness")
    if type(uptake_receipt) is not CellUptakeReceipt:
        raise GwtReentryUptakeBindingError("uptake_receipt must be concrete CellUptakeReceipt")

    _validate_wp506_reentry_lineage(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    validate_reentry_witness(
        witness,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        known_lineage_refs=known_lineage_refs,
    )
    try:
        uptake_receipt.assert_broadcast_binding(broadcast)
    except GWTUptakeError as exc:
        raise GwtReentryUptakeBindingError(f"invalid WP507 uptake receipt lineage: {exc}") from exc

    if uptake_receipt.cell_id != witness.recipient_cell_id:
        raise GwtReentryUptakeBindingError("uptake receipt recipient does not match re-entry recipient")
    if uptake_receipt.cell_id != cell_input.cell_id:
        raise GwtReentryUptakeBindingError("uptake receipt recipient does not match re-entry CellInput")
    if uptake_receipt.broadcast_id != witness.broadcast_id:
        raise GwtReentryUptakeBindingError("uptake receipt broadcast id does not match re-entry witness")
    if uptake_receipt.broadcast_sha256 != witness.broadcast_sha256:
        raise GwtReentryUptakeBindingError("uptake receipt broadcast digest does not match re-entry witness")
    if uptake_receipt.broadcast_generation != witness.broadcast_generation:
        raise GwtReentryUptakeBindingError("uptake receipt broadcast generation does not match re-entry witness")

    return GwtReentryUptakeBinding(
        binding_id=binding_id,
        canonical_reentry_key=witness.canonical_reentry_key(),
        reentry_witness_sha256=witness.sha256(),
        uptake_receipt_id=uptake_receipt.receipt_id,
        uptake_receipt_sha256=uptake_receipt.sha256(),
        broadcast_id=witness.broadcast_id,
        broadcast_generation=witness.broadcast_generation,
        broadcast_sha256=witness.broadcast_sha256,
        recipient_cell_id=witness.recipient_cell_id,
        delivery_status=uptake_receipt.delivery_status,
        uptake_status=uptake_receipt.uptake_status,
        downstream_ref=uptake_receipt.downstream_ref,
        downstream_sha256=uptake_receipt.downstream_sha256,
        binding_status=_binding_status(uptake_receipt.uptake_status),
        provenance_refs=tuple(provenance_refs),
        _factory_seal=_BINDING_SEAL,
    )


def validate_reentry_uptake_binding(
    binding: GwtReentryUptakeBinding,
    *,
    witness: GwtReentryProvenanceWitness,
    uptake_receipt: CellUptakeReceipt,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    cell_input: CellInput,
    known_lineage_refs: Iterable[str] = (),
) -> None:
    if type(binding) is not GwtReentryUptakeBinding or binding._factory_seal is not _BINDING_SEAL:
        raise GwtReentryUptakeBindingError("binding was not produced by deterministic binding factory")
    rebuilt = bind_reentry_to_uptake(
        binding_id=binding.binding_id,
        witness=witness,
        uptake_receipt=uptake_receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        known_lineage_refs=known_lineage_refs,
        provenance_refs=binding.provenance_refs,
    )
    if rebuilt.as_dict() != binding.as_dict():
        raise GwtReentryUptakeBindingError("binding source-evidence lineage mismatch")


__all__ = [
    "GWT_REENTRY_UPTAKE_BINDING_SCHEMA",
    "GwtReentryUptakeBinding",
    "GwtReentryUptakeBindingError",
    "bind_reentry_to_uptake",
    "validate_reentry_uptake_binding",
]
