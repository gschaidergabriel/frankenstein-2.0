"""Fail-closed Stage-5 GWT causal-path integration seal.

F2-WP-510 generation 2 repository-component scope only.

The seal does not create observations or causal evidence. It revalidates already
constructed WP506 selection/broadcast lineage, WP507 uptake/causal-probe evidence,
and WP508 re-entry/uptake bindings as one exact coherent component path. Positive
UPTAKEN admission additionally requires a concrete GRID10 CellOutput whose plan/input
lineage closes to the exact re-entry CellInput and whose ref/digest match the WP507/
WP508 downstream evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable

from frankenstein2.grid10_interface import (
    CellInput,
    CellOutput,
    Grid10InterfaceError,
    Grid10Plan,
)
from frankenstein2.gwt_reentry_provenance import GwtReentryProvenanceWitness
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBinding,
    validate_reentry_uptake_binding,
)
from frankenstein2.gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    CellUptakeReceipt,
    UptakeSummary,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import (
    BroadcastEnvelope,
    WorkspaceSelection,
    create_broadcast,
    verify_selection_binding,
)

GWT_CAUSAL_PATH_SEAL_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_PATH_SEAL/v1"
_CLASSIFICATION = "DERIVED_STAGE5_CAUSAL_PATH_INTEGRITY_NOT_RUNTIME_OR_WORLD_TRUTH"
_MAX_REFS = 4096
_SEAL_FACTORY = object()


class GwtCausalPathError(ValueError):
    """Fail-closed WP510 integration error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GwtCausalPathError(f"{name} must be a non-empty trimmed string")
    if len(value) > 512:
        raise GwtCausalPathError(f"{name} exceeds 512 characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtCausalPathError(f"{name} contains control characters")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtCausalPathError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtCausalPathError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS:
        raise GwtCausalPathError(f"provenance_refs exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise GwtCausalPathError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _sha256(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise GwtCausalPathError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryEvidenceBundle:
    """Exact source objects needed to revalidate one WP508 binding."""

    binding: GwtReentryUptakeBinding
    witness: GwtReentryProvenanceWitness
    uptake_receipt: CellUptakeReceipt
    cell_input: CellInput
    downstream_output: CellOutput | None = None
    known_lineage_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.binding) is not GwtReentryUptakeBinding:
            raise GwtCausalPathError("bundle binding must be concrete GwtReentryUptakeBinding")
        if type(self.witness) is not GwtReentryProvenanceWitness:
            raise GwtCausalPathError("bundle witness must be concrete GwtReentryProvenanceWitness")
        if type(self.uptake_receipt) is not CellUptakeReceipt:
            raise GwtCausalPathError("bundle uptake_receipt must be concrete CellUptakeReceipt")
        if type(self.cell_input) is not CellInput:
            raise GwtCausalPathError("bundle cell_input must be concrete CellInput")
        if self.downstream_output is not None and type(self.downstream_output) is not CellOutput:
            raise GwtCausalPathError("bundle downstream_output must be concrete CellOutput or None")
        if not isinstance(self.known_lineage_refs, tuple):
            raise GwtCausalPathError("known_lineage_refs must be an immutable tuple")
        refs = tuple(_text("known_lineage_ref", value) for value in self.known_lineage_refs)
        if len(set(refs)) != len(refs):
            raise GwtCausalPathError("known_lineage_refs must not contain duplicates")
        object.__setattr__(self, "known_lineage_refs", tuple(sorted(refs)))


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalPathSeal:
    seal_id: str
    cycle_id: str
    plan_id: str
    plan_sha256: str
    selection_id: str
    selection_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    uptake_summary_id: str
    uptake_summary_sha256: str
    causal_result_id: str
    causal_result_sha256: str
    causal_status: str
    uptaken_cell_ids: tuple[str, ...]
    reentry_binding_ids: tuple[str, ...]
    reentry_binding_sha256s: tuple[str, ...]
    path_status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    schema = GWT_CAUSAL_PATH_SEAL_SCHEMA
    classification = _CLASSIFICATION

    def __post_init__(self) -> None:
        for name in (
            "seal_id",
            "cycle_id",
            "plan_id",
            "selection_id",
            "broadcast_id",
            "uptake_summary_id",
            "causal_result_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "plan_sha256",
            "selection_sha256",
            "broadcast_sha256",
            "uptake_summary_sha256",
            "causal_result_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.path_status not in {
            "CONTRACT_SCOPE_CAUSAL_PATH_SEALED",
            "NO_CAUSAL_INFLUENCE_PATH_SEALED",
            "UNKNOWN_CAUSAL_PATH_SEALED",
        }:
            raise GwtCausalPathError("unsupported path_status")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "seal_id": self.seal_id,
            "cycle_id": self.cycle_id,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "selection_id": self.selection_id,
            "selection_sha256": self.selection_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "uptake_summary_id": self.uptake_summary_id,
            "uptake_summary_sha256": self.uptake_summary_sha256,
            "causal_result_id": self.causal_result_id,
            "causal_result_sha256": self.causal_result_sha256,
            "causal_status": self.causal_status,
            "uptaken_cell_ids": list(self.uptaken_cell_ids),
            "reentry_binding_ids": list(self.reentry_binding_ids),
            "reentry_binding_sha256s": list(self.reentry_binding_sha256s),
            "path_status": self.path_status,
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "training_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _path_status(causal_status: str) -> str:
    if causal_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
        return "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    if causal_status == "NO_CAUSAL_INFLUENCE_OBSERVED":
        return "NO_CAUSAL_INFLUENCE_PATH_SEALED"
    if causal_status.startswith("UNKNOWN_"):
        return "UNKNOWN_CAUSAL_PATH_SEALED"
    raise GwtCausalPathError("unsupported causal result status")


def seal_gwt_causal_path(
    *,
    seal_id: str,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    receipts: tuple[CellUptakeReceipt, ...],
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    causal_result: CausalInfluenceResult,
    reentry_bundles: tuple[ReentryEvidenceBundle, ...],
    provenance_refs: Iterable[str],
) -> GwtCausalPathSeal:
    """Revalidate the exact WP506 -> WP507 -> WP508 component chain."""
    if type(plan) is not Grid10Plan:
        raise GwtCausalPathError("plan must be concrete Grid10Plan")
    if type(selection) is not WorkspaceSelection:
        raise GwtCausalPathError("selection must be concrete WorkspaceSelection")
    if type(broadcast) is not BroadcastEnvelope:
        raise GwtCausalPathError("broadcast must be concrete BroadcastEnvelope")
    if (
        not isinstance(receipts, tuple)
        or not receipts
        or not all(type(item) is CellUptakeReceipt for item in receipts)
    ):
        raise GwtCausalPathError(
            "receipts must be a non-empty immutable CellUptakeReceipt tuple"
        )
    if type(uptake_summary) is not UptakeSummary:
        raise GwtCausalPathError("uptake_summary must be concrete UptakeSummary")
    if type(intervention) is not CausalProbeArm or type(control) is not CausalProbeArm:
        raise GwtCausalPathError("intervention/control must be concrete CausalProbeArm values")
    if type(causal_result) is not CausalInfluenceResult:
        raise GwtCausalPathError("causal_result must be concrete CausalInfluenceResult")
    if not isinstance(reentry_bundles, tuple) or not all(
        type(item) is ReentryEvidenceBundle for item in reentry_bundles
    ):
        raise GwtCausalPathError(
            "reentry_bundles must be an immutable ReentryEvidenceBundle tuple"
        )

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
    rebuilt_broadcast = create_broadcast(
        broadcast_id=broadcast.broadcast_id,
        generation=broadcast.generation,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=broadcast.recipient_cell_ids,
    )
    if rebuilt_broadcast.as_dict() != broadcast.as_dict():
        raise GwtCausalPathError(
            "broadcast does not match canonical WP506 builder lineage"
        )

    rebuilt_summary = summarize_uptake(
        summary_id=uptake_summary.summary_id,
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=uptake_summary.provenance_refs,
    )
    if rebuilt_summary.as_dict() != uptake_summary.as_dict():
        raise GwtCausalPathError(
            "uptake summary does not match exact WP507 receipt set"
        )

    rebuilt_causal = evaluate_causal_influence(
        result_id=causal_result.result_id,
        broadcast=broadcast,
        uptake_summary=uptake_summary,
        intervention=intervention,
        control=control,
        provenance_refs=causal_result.provenance_refs,
    )
    if rebuilt_causal.as_dict() != causal_result.as_dict():
        raise GwtCausalPathError(
            "causal result does not match exact WP507 matched probe"
        )

    receipt_by_identity = {
        (item.receipt_id, item.sha256()): item for item in receipts
    }
    if len(receipt_by_identity) != len(receipts):
        raise GwtCausalPathError("duplicate WP507 receipt identity/digest")

    seen_binding_ids: set[str] = set()
    seen_recipients: set[str] = set()
    bound_uptaken: set[str] = set()
    bound_uptaken_downstream: dict[str, str] = {}
    binding_ids: list[str] = []
    binding_sha256s: list[str] = []
    for bundle in reentry_bundles:
        binding = bundle.binding
        if binding.binding_id in seen_binding_ids:
            raise GwtCausalPathError("duplicate re-entry binding identity")
        if binding.recipient_cell_id in seen_recipients:
            raise GwtCausalPathError(
                "multiple re-entry bindings for one recipient"
            )
        seen_binding_ids.add(binding.binding_id)
        seen_recipients.add(binding.recipient_cell_id)
        receipt_key = (
            bundle.uptake_receipt.receipt_id,
            bundle.uptake_receipt.sha256(),
        )
        if receipt_key not in receipt_by_identity:
            raise GwtCausalPathError(
                "re-entry bundle uptake receipt is not in sealed WP507 receipt set"
            )
        validate_reentry_uptake_binding(
            binding,
            witness=bundle.witness,
            uptake_receipt=bundle.uptake_receipt,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=bundle.cell_input,
            known_lineage_refs=bundle.known_lineage_refs,
        )
        if binding.uptake_receipt_id != bundle.uptake_receipt.receipt_id:
            raise GwtCausalPathError("binding uptake receipt identity mismatch")
        if binding.uptake_receipt_sha256 != bundle.uptake_receipt.sha256():
            raise GwtCausalPathError("binding uptake receipt digest mismatch")
        if binding.uptake_status == "UPTAKEN":
            if binding.downstream_ref is None or binding.downstream_sha256 is None:
                raise GwtCausalPathError(
                    "UPTAKEN re-entry binding lacks downstream evidence"
                )
            downstream_output = bundle.downstream_output
            if type(downstream_output) is not CellOutput:
                raise GwtCausalPathError(
                    "UPTAKEN re-entry bundle lacks concrete downstream CellOutput"
                )
            try:
                plan.validate_output(downstream_output, cell_input=bundle.cell_input)
            except Grid10InterfaceError as exc:
                raise GwtCausalPathError(
                    "downstream CellOutput does not close to exact re-entry CellInput"
                ) from exc
            if bundle.uptake_receipt.downstream_ref not in downstream_output.output_refs:
                raise GwtCausalPathError(
                    "downstream reference does not resolve to typed CellOutput"
                )
            downstream_sha256 = downstream_output.sha256()
            if bundle.uptake_receipt.downstream_sha256 != downstream_sha256:
                raise GwtCausalPathError(
                    "downstream digest does not match typed CellOutput"
                )
            if binding.downstream_ref != bundle.uptake_receipt.downstream_ref:
                raise GwtCausalPathError(
                    "binding downstream reference does not match uptake receipt"
                )
            if binding.downstream_sha256 != downstream_sha256:
                raise GwtCausalPathError(
                    "binding downstream digest does not match typed CellOutput"
                )
            bound_uptaken.add(binding.recipient_cell_id)
            bound_uptaken_downstream[binding.recipient_cell_id] = downstream_sha256
        elif bundle.downstream_output is not None:
            raise GwtCausalPathError(
                "non-UPTAKEN re-entry bundle must not carry downstream CellOutput"
            )
        binding_ids.append(binding.binding_id)
        binding_sha256s.append(binding.sha256())

    expected_uptaken = set(uptake_summary.uptaken_cell_ids)
    if bound_uptaken != expected_uptaken:
        raise GwtCausalPathError(
            "every UPTAKEN recipient requires exactly one valid WP508 re-entry binding"
        )

    status = _path_status(causal_result.status)
    if status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED":
        if len(expected_uptaken) != 1:
            raise GwtCausalPathError(
                "positive causal path requires exactly one UPTAKEN recipient under the v1 probe ABI"
            )
        recipient = next(iter(expected_uptaken))
        if bound_uptaken_downstream[recipient] != intervention.downstream_output_sha256:
            raise GwtCausalPathError(
                "positive causal probe downstream digest does not match UPTAKEN re-entry evidence"
            )

    return GwtCausalPathSeal(
        seal_id=seal_id,
        cycle_id=plan.cycle_id,
        plan_id=plan.plan_id,
        plan_sha256=plan.sha256(),
        selection_id=selection.selection_id,
        selection_sha256=selection.sha256(),
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        uptake_summary_id=uptake_summary.summary_id,
        uptake_summary_sha256=uptake_summary.sha256(),
        causal_result_id=causal_result.result_id,
        causal_result_sha256=causal_result.sha256(),
        causal_status=causal_result.status,
        uptaken_cell_ids=tuple(uptake_summary.uptaken_cell_ids),
        reentry_binding_ids=tuple(binding_ids),
        reentry_binding_sha256s=tuple(binding_sha256s),
        path_status=status,
        provenance_refs=tuple(provenance_refs),
        _factory_seal=_SEAL_FACTORY,
    )


def validate_gwt_causal_path_seal(
    seal: GwtCausalPathSeal,
    **kwargs: Any,
) -> None:
    if type(seal) is not GwtCausalPathSeal or seal._factory_seal is not _SEAL_FACTORY:
        raise GwtCausalPathError(
            "seal was not produced by deterministic WP510 factory"
        )
    rebuilt = seal_gwt_causal_path(
        seal_id=seal.seal_id,
        provenance_refs=seal.provenance_refs,
        **kwargs,
    )
    if rebuilt.as_dict() != seal.as_dict():
        raise GwtCausalPathError("seal source-evidence lineage mismatch")


__all__ = [
    "GWT_CAUSAL_PATH_SEAL_SCHEMA",
    "GwtCausalPathError",
    "GwtCausalPathSeal",
    "ReentryEvidenceBundle",
    "seal_gwt_causal_path",
    "validate_gwt_causal_path_seal",
]
