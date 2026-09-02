"""Bound an admitted GWT runtime witness to the existing WP900 whole-loop subject.

CANDIDATE integration repair for the post-G4 WP900 boundary exposed by REVIEW_ONLY
PR #829.  This module is not a scheduler, state/effect authority, runtime receipt
producer, semantic GWT/J-Space authority, or completion gate.  It only validates
that an existing recorder-origin runtime witness names the exact GWT objects already
consumed by an existing WholePersistentLoopSeal and the exact expected source subject.
"""
from __future__ import annotations

import re

from .grid10_interface import Grid10Plan
from .gwt_causal_path import GwtCausalPathSeal
from .gwt_runtime_witness import (
    GwtRuntimeWitnessError,
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from .whole_persistent_loop import GwtCausalValidationEvidence, WholePersistentLoopSeal

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GwtRuntimeWholeLoopBindingError(ValueError):
    """Fail-closed identity mismatch at the runtime-witness -> whole-loop seam."""


def _expected_sha256(value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise GwtRuntimeWholeLoopBindingError(
            "expected_exact_source_sha256 must be lowercase 64-hex SHA-256"
        )
    return value


def validate_runtime_witness_whole_loop_binding(
    *,
    whole_seal: WholePersistentLoopSeal,
    plan: Grid10Plan,
    gwt_seal: GwtCausalPathSeal,
    gwt_evidence: GwtCausalValidationEvidence,
    runtime_witness: GwtRuntimeWitnessReceipt,
    expected_exact_source_sha256: str,
) -> None:
    """Require one exact runtime/source identity for an already sealed GWT loop path.

    Success grants no credit.  It only removes ambiguity: a recorder-valid witness for
    another source subject, broadcast, uptake receipt, re-entry witness or binding is
    rejected before a caller can treat it as evidence for this whole-loop subject.
    """
    if type(whole_seal) is not WholePersistentLoopSeal:
        raise GwtRuntimeWholeLoopBindingError(
            "whole_seal must be concrete WholePersistentLoopSeal"
        )
    if type(plan) is not Grid10Plan:
        raise GwtRuntimeWholeLoopBindingError("plan must be concrete Grid10Plan")
    if type(gwt_seal) is not GwtCausalPathSeal:
        raise GwtRuntimeWholeLoopBindingError(
            "gwt_seal must be concrete GwtCausalPathSeal"
        )
    if type(gwt_evidence) is not GwtCausalValidationEvidence:
        raise GwtRuntimeWholeLoopBindingError(
            "gwt_evidence must be concrete GwtCausalValidationEvidence"
        )

    expected_source = _expected_sha256(expected_exact_source_sha256)
    try:
        validate_gwt_runtime_witness_receipt(runtime_witness)
    except (GwtRuntimeWitnessError, TypeError, ValueError) as exc:
        raise GwtRuntimeWholeLoopBindingError(
            f"runtime witness rejected: {exc}"
        ) from exc

    if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
        raise GwtRuntimeWholeLoopBindingError(
            "runtime witness is not positive DELIVERY -> UPTAKE -> REENTRY observation"
        )
    if runtime_witness.identity.exact_source_sha256 != expected_source:
        raise GwtRuntimeWholeLoopBindingError(
            "runtime witness exact source identity mismatch"
        )

    if (
        whole_seal.grid_plan_id != plan.plan_id
        or whole_seal.grid_plan_sha256 != plan.sha256()
    ):
        raise GwtRuntimeWholeLoopBindingError(
            "whole-loop seal GRID10 plan identity mismatch"
        )
    if (
        whole_seal.gwt_seal_id != gwt_seal.seal_id
        or whole_seal.gwt_seal_sha256 != gwt_seal.sha256()
    ):
        raise GwtRuntimeWholeLoopBindingError(
            "whole-loop seal GWT causal-path identity mismatch"
        )

    # Re-run the existing WP510 source-object validator at the consumer seam.  This
    # avoids trusting only the derived GWT seal digest.
    try:
        gwt_evidence.validate(seal=gwt_seal, plan=plan)
    except (TypeError, ValueError) as exc:
        raise GwtRuntimeWholeLoopBindingError(
            f"whole-loop GWT source evidence rejected: {exc}"
        ) from exc

    if (
        runtime_witness.broadcast_id != gwt_evidence.broadcast.broadcast_id
        or runtime_witness.broadcast_sha256 != gwt_evidence.broadcast.sha256()
    ):
        raise GwtRuntimeWholeLoopBindingError(
            "runtime witness broadcast identity mismatch"
        )

    uptake_matches = tuple(
        receipt
        for receipt in gwt_evidence.receipts
        if receipt.receipt_id == runtime_witness.uptake_receipt_id
        and receipt.sha256() == runtime_witness.uptake_receipt_sha256
        and receipt.cell_id == runtime_witness.recipient_cell_id
    )
    if len(uptake_matches) != 1:
        raise GwtRuntimeWholeLoopBindingError(
            "runtime witness uptake identity does not resolve uniquely in whole-loop evidence"
        )

    reentry_matches = tuple(
        bundle
        for bundle in gwt_evidence.reentry_bundles
        if bundle.witness.canonical_reentry_key()
        == runtime_witness.canonical_reentry_key
        and bundle.witness.sha256() == runtime_witness.reentry_witness_sha256
        and bundle.binding.binding_id == runtime_witness.binding_id
        and bundle.binding.sha256() == runtime_witness.binding_sha256
        and bundle.uptake_receipt.receipt_id == runtime_witness.uptake_receipt_id
        and bundle.uptake_receipt.sha256() == runtime_witness.uptake_receipt_sha256
    )
    if len(reentry_matches) != 1:
        raise GwtRuntimeWholeLoopBindingError(
            "runtime witness re-entry/binding identity does not resolve uniquely in whole-loop evidence"
        )


__all__ = [
    "GwtRuntimeWholeLoopBindingError",
    "validate_runtime_witness_whole_loop_binding",
]
