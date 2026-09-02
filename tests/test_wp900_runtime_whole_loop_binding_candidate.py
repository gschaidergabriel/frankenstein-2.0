"""CANDIDATE regression for WP900 runtime-witness -> whole-loop identity binding.

Absorbs the executable ambiguity characterized by REVIEW_ONLY PR #829 without
claiming canonical WP900 mutation authority or any runtime/semantic credit.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_whole_persistent_loop import fixture_components  # noqa: E402

from frankenstein2.gwt_runtime_whole_loop_binding import (  # noqa: E402
    GwtRuntimeWholeLoopBindingError,
    validate_runtime_witness_whole_loop_binding,
)
from frankenstein2.gwt_runtime_witness import (  # noqa: E402
    GwtRuntimeWitnessRecorder,
    RuntimeObservationIdentity,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.whole_persistent_loop import seal_whole_persistent_loop  # noqa: E402


def _runtime_receipt(*, plan, gwt_evidence, exact_source_sha256: str):
    bundle = gwt_evidence.reentry_bundles[0]
    ticks = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:wp900:g5-candidate",
            process_identity="pid:900:start:g5",
            boot_id_sha256="d" * 64,
            exact_source_sha256=exact_source_sha256,
        ),
        monotonic_ns=lambda: next(ticks),
    )
    recorder.observe_delivery(gwt_evidence.broadcast)
    recorder.observe_uptake(bundle.uptake_receipt)
    recorder.observe_reentry(
        witness=bundle.witness,
        binding=bundle.binding,
        plan=plan,
        selection=gwt_evidence.selection,
        cell_input=bundle.cell_input,
    )
    receipt = recorder.seal()
    validate_gwt_runtime_witness_receipt(receipt)
    return receipt


def _whole_subject():
    (
        checkpoint,
        frame,
        contract,
        plan,
        gwt,
        gwt_evidence,
        decision,
        outcome,
        next_checkpoint,
    ) = fixture_components()
    whole = seal_whole_persistent_loop(
        seal_id="whole-loop-seal-runtime-binding-candidate",
        generation=0,
        current_checkpoint=checkpoint,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        decision=decision,
        outcome=outcome,
        next_checkpoint=next_checkpoint,
        provenance_refs=("candidate:wp900:runtime-witness-whole-loop",),
    )
    return plan, gwt, gwt_evidence, whole


def test_exact_runtime_source_and_gwt_objects_bind_to_existing_whole_loop():
    plan, gwt, gwt_evidence, whole = _whole_subject()
    source = "a" * 64
    runtime = _runtime_receipt(
        plan=plan,
        gwt_evidence=gwt_evidence,
        exact_source_sha256=source,
    )

    validate_runtime_witness_whole_loop_binding(
        whole_seal=whole,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        runtime_witness=runtime,
        expected_exact_source_sha256=source,
    )

    assert whole.as_dict()["runtime_credit"] == 0
    assert whole.as_dict()["gwt_runtime_credit"] == 0
    assert whole.as_dict()["whole_system_acceptance"] is False


def test_pr829_two_source_ambiguity_fails_closed_at_binding_gate():
    plan, gwt, gwt_evidence, whole = _whole_subject()
    expected_source = "a" * 64
    wrong_source = "b" * 64
    runtime_expected = _runtime_receipt(
        plan=plan,
        gwt_evidence=gwt_evidence,
        exact_source_sha256=expected_source,
    )
    runtime_wrong = _runtime_receipt(
        plan=plan,
        gwt_evidence=gwt_evidence,
        exact_source_sha256=wrong_source,
    )

    # Reproduce the original observation: both recorder-valid receipts name exactly
    # the same accepted GWT objects and differ only in source identity.
    assert runtime_expected.broadcast_sha256 == runtime_wrong.broadcast_sha256
    assert runtime_expected.binding_sha256 == runtime_wrong.binding_sha256
    assert runtime_expected.identity.exact_source_sha256 != runtime_wrong.identity.exact_source_sha256

    validate_runtime_witness_whole_loop_binding(
        whole_seal=whole,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        runtime_witness=runtime_expected,
        expected_exact_source_sha256=expected_source,
    )

    with pytest.raises(
        GwtRuntimeWholeLoopBindingError,
        match="exact source identity mismatch",
    ):
        validate_runtime_witness_whole_loop_binding(
            whole_seal=whole,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            runtime_witness=runtime_wrong,
            expected_exact_source_sha256=expected_source,
        )
