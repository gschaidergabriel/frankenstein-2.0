"""REVIEW_ONLY discriminator for WP900 runtime-witness -> whole-loop binding.

This does not define a new evidence adapter. It demonstrates that the accepted runtime
witness can observe the exact GWT objects consumed by the whole-loop seal while its
runtime/source identity remains outside that seal's input contract.
"""
from pathlib import Path
import sys

# Reuse the canonical WP900 whole-loop fixture rather than cloning another fixture.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_whole_persistent_loop import fixture_components  # noqa: E402

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
            runtime_instance_id="runtime:wp900:whole-loop-review",
            process_identity="pid:900:start:1",
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


def test_runtime_source_identity_is_not_yet_bound_into_whole_loop_seal():
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

    runtime_a = _runtime_receipt(
        plan=plan,
        gwt_evidence=gwt_evidence,
        exact_source_sha256="a" * 64,
    )
    runtime_b = _runtime_receipt(
        plan=plan,
        gwt_evidence=gwt_evidence,
        exact_source_sha256="b" * 64,
    )

    # Both receipts observe the exact same accepted GWT objects, but assert different
    # exact-source identities. This is permitted because runtime-source admission is
    # external to the deterministic GWT object lineage.
    assert runtime_a.broadcast_sha256 == runtime_b.broadcast_sha256 == gwt_evidence.broadcast.sha256()
    assert runtime_a.binding_sha256 == runtime_b.binding_sha256 == gwt_evidence.reentry_bundles[0].binding.sha256()
    assert runtime_a.identity.exact_source_sha256 != runtime_b.identity.exact_source_sha256

    whole = seal_whole_persistent_loop(
        seal_id="whole-loop-seal-runtime-binding-review",
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
        provenance_refs=("review:wp900:runtime-witness-whole-loop",),
    )

    payload = whole.as_dict()
    assert payload["runtime_credit"] == 0
    assert payload["whole_system_acceptance"] is False
    assert runtime_a.sha256() not in repr(payload)
    assert runtime_b.sha256() not in repr(payload)
