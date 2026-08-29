"""Deterministic Stage-5 GWT causal-path integration seal.

F2-WP-510 generation 1.

The seal does not create observations. It revalidates and re-derives already-existing
WP506 selection/broadcast lineage, WP507 uptake and matched causal-probe evidence, and
WP508 re-entry/uptake bindings as one exact repository-component path.

No provider/model execution, target runtime, physical GRID10, hidden-state inference,
world truth, effect/completion authority, J-Space credit, training credit, or whole-system
acceptance is created by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.grid10_interface import CellInput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import GwtReentryProvenanceWitness
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBinding,
    GwtReentryUptakeBindingError,
    validate_reentry_uptake_binding,
)
from frankenstein2.gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    CellUptakeReceipt,
    GWTUptakeError,
    UptakeSummary,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import (
    BroadcastEnvelope,
    GwtWorkspaceError,
    WorkspaceSelection,
    create_broadcast,
    verify_selection_binding,
)

GWT_CAUSAL_PATH_REENTRY_EVIDENCE_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_PATH_REENTRY_EVIDENCE/v1"
GWT_CAUSAL_PATH_SEAL_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_PATH_SEAL/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_PATH_SEAL = object()


class GwtCausalPathError(ValueError):
    """Fail-closed WP510 causal-path integration error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GwtCausalPathError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise GwtCausalPathError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtCausalPathError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GwtCausalPathError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise GwtCausalPathError(f"{name} must be a non-negative integer")
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtCausalPathError(f"{name} must be an iterable of strings")
    refs = tuple(_text(f"{name} item", value) for value in values)
    if not allow_empty and not refs:
        raise GwtCausalPathError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise GwtCausalPathError(f"{name} exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise GwtCausalPathError(f"{name} must not contain duplicates")
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
        raise GwtCausalPathError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryBindingEvidence:
    """Exact objects needed to revalidate one WP508 binding.

    This carrier has no evidence authority by itself. WP510 validates every member against
    the canonical WP506/WP507/WP508 factories before the path can be sealed.
    """

    binding: GwtReentryUptakeBinding
    witness: GwtReentryProvenanceWitness
    uptake_receipt: CellUptakeReceipt
    cell_input: CellInput
    known_lineage_refs: tuple[str, ...] = ()

    schema = GWT_CAUSAL_PATH_REENTRY_EVIDENCE_SCHEMA
    classification = "REVALIDATION_INPUT_NOT_NEW_REENTRY_OR_UPTAKE_EVIDENCE"

    def __post_init__(self) -> None:
        if type(self.binding) is not GwtReentryUptakeBinding:
            raise GwtCausalPathError("binding must be concrete GwtReentryUptakeBinding")
        if type(self.witness) is not GwtReentryProvenanceWitness:
            raise GwtCausalPathError("witness must be concrete GwtReentryProvenanceWitness")
        if type(self.uptake_receipt) is not CellUptakeReceipt:
            raise GwtCausalPathError("uptake_receipt must be concrete CellUptakeReceipt")
        if type(self.cell_input) is not CellInput:
            raise GwtCausalPathError("cell_input must be concrete CellInput")
        object.__setattr__(
            self,
            "known_lineage_refs",
            _refs("known_lineage_refs", self.known_lineage_refs, allow_empty=True),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "binding_id": self.binding.binding_id,
            "binding_sha256": self.binding.sha256(),
            "witness_sha256": self.witness.sha256(),
            "uptake_receipt_id": self.uptake_receipt.receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt.sha256(),
            "cell_id": self.cell_input.cell_id,
            "cell_input_sha256": self.cell_input.sha256(),
            "known_lineage_refs": list(self.known_lineage_refs),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalPathSeal:
    seal_id: str
    cycle_id: str
    plan_id: str
    plan_generation: int
    plan_sha256: str
    selection_id: str
    selection_generation: int
    selection_sha256: str
    broadcast_id: str
    broadcast_generation: int
    broadcast_sha256: str
    uptake_summary_id: str
    uptake_summary_sha256: str
    causal_result_id: str
    causal_result_sha256: str
    uptake_status: str
    causal_status: str
    uptaken_cell_ids: tuple[str, ...]
    reentry_binding_sha256s: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    schema = GWT_CAUSAL_PATH_SEAL_SCHEMA
    classification = "REPOSITORY_COMPONENT_CAUSAL_PATH_SEAL_NOT_RUNTIME_OR_TRUTH_AUTHORITY"

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
        for name in ("plan_generation", "selection_generation", "broadcast_generation"):
            _generation(name, getattr(self, name))
        for name in (
            "plan_sha256",
            "selection_sha256",
            "broadcast_sha256",
            "uptake_summary_sha256",
            "causal_result_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.uptake_status not in {
            "UPTAKE_OBSERVED",
            "NO_UPTAKE_OBSERVED",
            "UNKNOWN_INCOMPLETE_RECEIPTS",
        }:
            raise GwtCausalPathError("unsupported uptake_status")
        if self.causal_status not in {
            "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE",
            "NO_CAUSAL_INFLUENCE_OBSERVED",
            "UNKNOWN_INSUFFICIENT_UPTAKE",
            "UNKNOWN_UNMATCHED_CONTROL",
        }:
            raise GwtCausalPathError("unsupported causal_status")
        if not isinstance(self.uptaken_cell_ids, tuple):
            raise GwtCausalPathError("uptaken_cell_ids must be an immutable tuple")
        if len(set(self.uptaken_cell_ids)) != len(self.uptaken_cell_ids):
            raise GwtCausalPathError("uptaken_cell_ids must not contain duplicates")
        if not isinstance(self.reentry_binding_sha256s, tuple):
            raise GwtCausalPathError("reentry_binding_sha256s must be an immutable tuple")
        if len(set(self.reentry_binding_sha256s)) != len(self.reentry_binding_sha256s):
            raise GwtCausalPathError("reentry_binding_sha256s must not contain duplicates")
        for digest in self.reentry_binding_sha256s:
            _sha256("reentry_binding_sha256", digest)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "seal_id": self.seal_id,
            "cycle_id": self.cycle_id,
            "plan_id": self.plan_id,
            "plan_generation": self.plan_generation,
            "plan_sha256": self.plan_sha256,
            "selection_id": self.selection_id,
            "selection_generation": self.selection_generation,
            "selection_sha256": self.selection_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_generation": self.broadcast_generation,
            "broadcast_sha256": self.broadcast_sha256,
            "uptake_summary_id": self.uptake_summary_id,
            "uptake_summary_sha256": self.uptake_summary_sha256,
            "causal_result_id": self.causal_result_id,
            "causal_result_sha256": self.causal_result_sha256,
            "uptake_status": self.uptake_status,
            "causal_status": self.causal_status,
            "uptaken_cell_ids": list(self.uptaken_cell_ids),
            "reentry_binding_sha256s": list(self.reentry_binding_sha256s),
            "provenance_refs": list(self.provenance_refs),
            "runtime_execution_observed": False,
            "runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "training_credit": 0,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _validate_wp506_path(
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
) -> None:
    if type(plan) is not Grid10Plan:
        raise GwtCausalPathError("plan must be concrete Grid10Plan")
    if type(selection) is not WorkspaceSelection:
        raise GwtCausalPathError("selection must be concrete WorkspaceSelection")
    if type(broadcast) is not BroadcastEnvelope:
        raise GwtCausalPathError("broadcast must be concrete BroadcastEnvelope")
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
        rebuilt_broadcast = create_broadcast(
            broadcast_id=broadcast.broadcast_id,
            generation=broadcast.generation,
            selection=selection,
            expected_selection_sha256=selection.sha256(),
            recipient_cell_ids=broadcast.recipient_cell_ids,
        )
    except GwtWorkspaceError as exc:
        raise GwtCausalPathError(f"invalid WP506 builder lineage: {exc}") from exc
    if rebuilt_broadcast.as_dict() != broadcast.as_dict():
        raise GwtCausalPathError("broadcast does not equal deterministic WP506 builder output")
    if broadcast.cycle_id != plan.cycle_id:
        raise GwtCausalPathError("broadcast cycle does not match exact GRID10 plan")


def _validate_wp507_summary(
    *,
    broadcast: BroadcastEnvelope,
    uptake_receipts: tuple[CellUptakeReceipt, ...],
    uptake_summary: UptakeSummary,
) -> dict[tuple[str, str], CellUptakeReceipt]:
    if type(uptake_summary) is not UptakeSummary:
        raise GwtCausalPathError("uptake_summary must be concrete UptakeSummary")
    if not isinstance(uptake_receipts, tuple) or not all(
        type(item) is CellUptakeReceipt for item in uptake_receipts
    ):
        raise GwtCausalPathError("uptake_receipts must be an immutable tuple of concrete CellUptakeReceipt")
    try:
        rebuilt = summarize_uptake(
            summary_id=uptake_summary.summary_id,
            broadcast=broadcast,
            receipts=uptake_receipts,
            provenance_refs=uptake_summary.provenance_refs,
        )
    except GWTUptakeError as exc:
        raise GwtCausalPathError(f"invalid WP507 uptake lineage: {exc}") from exc
    if rebuilt.as_dict() != uptake_summary.as_dict():
        raise GwtCausalPathError("uptake summary does not equal deterministic WP507 summarizer output")
    receipt_map: dict[tuple[str, str], CellUptakeReceipt] = {}
    for receipt in uptake_receipts:
        key = (receipt.receipt_id, receipt.sha256())
        if key in receipt_map:
            raise GwtCausalPathError("duplicate exact uptake receipt identity")
        receipt_map[key] = receipt
    return receipt_map


def _validate_wp507_causal_result(
    *,
    broadcast: BroadcastEnvelope,
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    causal_result: CausalInfluenceResult,
) -> None:
    if type(intervention) is not CausalProbeArm or type(control) is not CausalProbeArm:
        raise GwtCausalPathError("intervention and control must be concrete CausalProbeArm values")
    if type(causal_result) is not CausalInfluenceResult:
        raise GwtCausalPathError("causal_result must be concrete CausalInfluenceResult")
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
        raise GwtCausalPathError(f"invalid WP507 causal-probe lineage: {exc}") from exc
    if rebuilt.as_dict() != causal_result.as_dict():
        raise GwtCausalPathError("causal result does not equal deterministic WP507 evaluation")


def _validate_wp508_reentries(
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    uptake_summary: UptakeSummary,
    summary_receipts: dict[tuple[str, str], CellUptakeReceipt],
    reentry_evidence: tuple[ReentryBindingEvidence, ...],
) -> tuple[str, ...]:
    if not isinstance(reentry_evidence, tuple) or not all(
        type(item) is ReentryBindingEvidence for item in reentry_evidence
    ):
        raise GwtCausalPathError("reentry_evidence must be an immutable tuple of concrete ReentryBindingEvidence")
    recipient_ids: set[str] = set()
    binding_ids: set[str] = set()
    binding_digests: list[str] = []
    bound_uptaken: set[str] = set()
    for evidence in reentry_evidence:
        binding = evidence.binding
        recipient = binding.recipient_cell_id
        if recipient in recipient_ids:
            raise GwtCausalPathError("multiple re-entry bindings for one recipient are not allowed")
        recipient_ids.add(recipient)
        if binding.binding_id in binding_ids:
            raise GwtCausalPathError("duplicate re-entry binding identity")
        binding_ids.add(binding.binding_id)
        receipt_key = (evidence.uptake_receipt.receipt_id, evidence.uptake_receipt.sha256())
        if receipt_key not in summary_receipts:
            raise GwtCausalPathError("re-entry binding receipt is not an exact source receipt of the uptake summary")
        if summary_receipts[receipt_key].as_dict() != evidence.uptake_receipt.as_dict():
            raise GwtCausalPathError("re-entry binding receipt differs from exact uptake-summary source receipt")
        try:
            validate_reentry_uptake_binding(
                binding,
                witness=evidence.witness,
                uptake_receipt=evidence.uptake_receipt,
                plan=plan,
                selection=selection,
                broadcast=broadcast,
                cell_input=evidence.cell_input,
                known_lineage_refs=evidence.known_lineage_refs,
            )
        except (GwtReentryUptakeBindingError, ValueError) as exc:
            raise GwtCausalPathError(f"invalid WP508 re-entry/uptake binding: {exc}") from exc
        if binding.uptake_status == "UPTAKEN":
            bound_uptaken.add(recipient)
        binding_digests.append(binding.sha256())

    expected_uptaken = set(uptake_summary.uptaken_cell_ids)
    if bound_uptaken != expected_uptaken:
        missing = sorted(expected_uptaken - bound_uptaken)
        unexpected = sorted(bound_uptaken - expected_uptaken)
        parts: list[str] = []
        if missing:
            parts.append("missing UPTAKEN re-entry binding(s): " + ", ".join(missing))
        if unexpected:
            parts.append("unexpected UPTAKEN re-entry binding(s): " + ", ".join(unexpected))
        raise GwtCausalPathError("; ".join(parts) or "UPTAKEN re-entry binding coverage mismatch")
    return tuple(sorted(binding_digests))


def seal_gwt_causal_path(
    *,
    seal_id: str,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    uptake_receipts: tuple[CellUptakeReceipt, ...],
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    causal_result: CausalInfluenceResult,
    reentry_evidence: tuple[ReentryBindingEvidence, ...],
    provenance_refs: Iterable[str],
) -> GwtCausalPathSeal:
    """Revalidate one complete repository-component GWT causal path.

    Successful sealing means only that the supplied deterministic component artifacts are
    mutually and causally bound at their declared contract scope. It does not establish
    target runtime execution, hidden-state causality, world truth, or whole-system behavior.
    """
    _validate_wp506_path(plan=plan, selection=selection, broadcast=broadcast)
    receipt_map = _validate_wp507_summary(
        broadcast=broadcast,
        uptake_receipts=uptake_receipts,
        uptake_summary=uptake_summary,
    )
    _validate_wp507_causal_result(
        broadcast=broadcast,
        uptake_summary=uptake_summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
    )
    binding_digests = _validate_wp508_reentries(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        uptake_summary=uptake_summary,
        summary_receipts=receipt_map,
        reentry_evidence=reentry_evidence,
    )
    return GwtCausalPathSeal(
        seal_id=seal_id,
        cycle_id=plan.cycle_id,
        plan_id=plan.plan_id,
        plan_generation=plan.generation,
        plan_sha256=plan.sha256(),
        selection_id=selection.selection_id,
        selection_generation=selection.generation,
        selection_sha256=selection.sha256(),
        broadcast_id=broadcast.broadcast_id,
        broadcast_generation=broadcast.generation,
        broadcast_sha256=broadcast.sha256(),
        uptake_summary_id=uptake_summary.summary_id,
        uptake_summary_sha256=uptake_summary.sha256(),
        causal_result_id=causal_result.result_id,
        causal_result_sha256=causal_result.sha256(),
        uptake_status=uptake_summary.status,
        causal_status=causal_result.status,
        uptaken_cell_ids=uptake_summary.uptaken_cell_ids,
        reentry_binding_sha256s=binding_digests,
        provenance_refs=tuple(provenance_refs),
        _factory_seal=_PATH_SEAL,
    )


def validate_gwt_causal_path_seal(
    seal: GwtCausalPathSeal,
    *,
    plan: Grid10Plan,
    selection: WorkspaceSelection,
    broadcast: BroadcastEnvelope,
    uptake_receipts: tuple[CellUptakeReceipt, ...],
    uptake_summary: UptakeSummary,
    intervention: CausalProbeArm,
    control: CausalProbeArm,
    causal_result: CausalInfluenceResult,
    reentry_evidence: tuple[ReentryBindingEvidence, ...],
) -> None:
    if type(seal) is not GwtCausalPathSeal or seal._factory_seal is not _PATH_SEAL:
        raise GwtCausalPathError("seal was not produced by deterministic WP510 factory")
    rebuilt = seal_gwt_causal_path(
        seal_id=seal.seal_id,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        uptake_receipts=uptake_receipts,
        uptake_summary=uptake_summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
        reentry_evidence=reentry_evidence,
        provenance_refs=seal.provenance_refs,
    )
    if rebuilt.as_dict() != seal.as_dict():
        raise GwtCausalPathError("seal source-evidence lineage mismatch")


__all__ = [
    "GWT_CAUSAL_PATH_REENTRY_EVIDENCE_SCHEMA",
    "GWT_CAUSAL_PATH_SEAL_SCHEMA",
    "GwtCausalPathError",
    "GwtCausalPathSeal",
    "ReentryBindingEvidence",
    "seal_gwt_causal_path",
    "validate_gwt_causal_path_seal",
]
