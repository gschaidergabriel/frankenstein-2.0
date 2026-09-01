"""WP900 G5 repository discriminator for G4 runtime -> whole-loop identity binding."""
from dataclasses import replace

import pytest

from test_whole_persistent_loop import fixture_components

from frankenstein2.gwt_causal_runtime_readback import (
    ControlNoBroadcastReadback,
    ProbeExecutionContext,
    bind_causal_runtime_readback,
)
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.runtime_bound_whole_loop import (
    RUNTIME_BOUND_WHOLE_LOOP_CLASSIFICATION,
    RuntimeBoundWholeLoopError,
    bind_runtime_bound_whole_loop,
    validate_runtime_bound_whole_loop,
)
from frankenstein2.whole_persistent_loop import seal_whole_persistent_loop

SOURCE_A = "1" * 64
SOURCE_B = "2" * 64
BOOT = "3" * 64
ENGINE = "4" * 64
ENVIRONMENT = "5" * 64
DEPENDENCIES = "6" * 64
CONTROL_DOWNSTREAM = "f" * 64


def _whole_fixture():
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
        seal_id="whole-loop-seal-wp900-g5",
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
        provenance_refs=("test:wp900:g5:whole-loop",),
    )
    return plan, gwt, gwt_evidence, whole


def _runtime_readback(*, plan, gwt_evidence, exact_source_sha256: str):
    bundle = gwt_evidence.reentry_bundles[0]
    ticks = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:wp900:g5:intervention",
            process_identity="pid:9005:start:10",
            boot_id_sha256=BOOT,
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
    witness = recorder.seal()

    context = ProbeExecutionContext(
        runner_identity="runner:vps-clay-host",
        execution_surface="S1:ubuntu-24.04-oci",
        runtime_engine_identity="python:cpython-3.11",
        runtime_engine_config_sha256=ENGINE,
        environment_sha256=ENVIRONMENT,
        dependency_set_sha256=DEPENDENCIES,
        boot_id_sha256=BOOT,
        exact_source_sha256=exact_source_sha256,
        provenance_refs=("test:wp900:g5:execution-context",),
    )
    control = ControlNoBroadcastReadback.observe(
        execution_context=context,
        runtime_instance_id="runtime:wp900:g5:control",
        process_identity="pid:9006:start:20",
        boot_id_sha256=BOOT,
        exact_source_sha256=exact_source_sha256,
        probe_id="probe:wp900:g5",
        nonbroadcast_input_sha256=gwt_evidence.intervention.nonbroadcast_input_sha256,
        downstream_ref="readback:wp900:g5:control",
        downstream_sha256=CONTROL_DOWNSTREAM,
        observed_monotonic_ns=40,
        reentry_observed=False,
        provenance_refs=("test:wp900:g5:control",),
    )
    return bind_causal_runtime_readback(
        probe_id="probe:wp900:g5",
        nonbroadcast_input_sha256=gwt_evidence.intervention.nonbroadcast_input_sha256,
        execution_context=context,
        broadcast=gwt_evidence.broadcast,
        runtime_witness=witness,
        uptake_receipt=bundle.uptake_receipt,
        uptake_summary=gwt_evidence.uptake_summary,
        control_readback=control,
        provenance_refs=("test:wp900:g5:g4-readback",),
    )


def _bind(*, exact_source_sha256=SOURCE_A):
    plan, gwt, gwt_evidence, whole = _whole_fixture()
    runtime = _runtime_readback(
        plan=plan,
        gwt_evidence=gwt_evidence,
        exact_source_sha256=exact_source_sha256,
    )
    candidate = bind_runtime_bound_whole_loop(
        whole_loop_seal=whole,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        causal_runtime_readback=runtime,
        provenance_refs=("test:wp900:g5:runtime-bound-whole-loop",),
    )
    return plan, gwt, gwt_evidence, whole, runtime, candidate


def test_g4_runtime_identity_is_bound_to_exact_whole_loop_but_mints_zero_credit():
    _, _, _, whole, runtime, candidate = _bind()
    validate_runtime_bound_whole_loop(candidate)

    assert candidate.classification == RUNTIME_BOUND_WHOLE_LOOP_CLASSIFICATION
    assert candidate.whole_loop_seal_sha256 == whole.sha256()
    assert candidate.causal_runtime_readback_sha256 == runtime.sha256()
    assert candidate.exact_source_sha256 == SOURCE_A
    assert candidate.boot_id_sha256 == BOOT
    assert candidate.execution_context_sha256 == runtime.execution_context_sha256
    assert candidate.repository_component_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.runtime_bound_whole_loop_candidate_credit == 0
    assert candidate.runtime_credit == 0
    assert candidate.gwt_runtime_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.physical_grid10_credit == 0
    assert candidate.effect_credit == 0
    assert candidate.training_credit == 0
    assert candidate.completion_credit == 0
    assert candidate.whole_system_acceptance is False


def test_source_identity_substitution_changes_bound_subject_digest():
    *_, first = _bind(exact_source_sha256=SOURCE_A)
    *_, second = _bind(exact_source_sha256=SOURCE_B)

    assert first.whole_loop_seal_sha256 == second.whole_loop_seal_sha256
    assert first.exact_source_sha256 != second.exact_source_sha256
    assert first.causal_runtime_readback_sha256 != second.causal_runtime_readback_sha256
    assert first.sha256() != second.sha256()


def test_tampered_g4_runtime_candidate_is_rejected_before_binding():
    plan, gwt, gwt_evidence, whole, runtime, _ = _bind()
    forged = replace(runtime, exact_source_sha256=SOURCE_B)

    with pytest.raises(RuntimeBoundWholeLoopError, match="invalid causal runtime readback"):
        bind_runtime_bound_whole_loop(
            whole_loop_seal=whole,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            causal_runtime_readback=forged,
            provenance_refs=("test:wp900:g5:forged-runtime",),
        )


def test_whole_loop_must_bind_the_same_gwt_seal():
    plan, gwt, gwt_evidence, whole, runtime, _ = _bind()
    forged_whole = replace(whole, gwt_seal_sha256=CONTROL_DOWNSTREAM)

    with pytest.raises(RuntimeBoundWholeLoopError, match="whole-loop GWT seal identity mismatch"):
        bind_runtime_bound_whole_loop(
            whole_loop_seal=forged_whole,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            causal_runtime_readback=runtime,
            provenance_refs=("test:wp900:g5:forged-whole",),
        )


def test_runtime_broadcast_must_be_the_whole_loop_gwt_broadcast():
    plan, gwt, gwt_evidence, whole, runtime, _ = _bind()
    forged = replace(runtime, broadcast_sha256=CONTROL_DOWNSTREAM)

    with pytest.raises(RuntimeBoundWholeLoopError, match="invalid causal runtime readback"):
        bind_runtime_bound_whole_loop(
            whole_loop_seal=whole,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            causal_runtime_readback=forged,
            provenance_refs=("test:wp900:g5:forged-broadcast",),
        )


def test_bound_candidate_tamper_is_rejected():
    *_, candidate = _bind()
    forged = replace(candidate, exact_source_sha256=SOURCE_B)

    with pytest.raises(RuntimeBoundWholeLoopError, match="payload changed after bind"):
        validate_runtime_bound_whole_loop(forged)
