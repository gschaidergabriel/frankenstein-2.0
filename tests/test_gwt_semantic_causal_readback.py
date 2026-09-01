from dataclasses import replace

import pytest

import frankenstein2.gwt_causal_runtime_readback as g4
from frankenstein2.gwt_causal_runtime_readback import ProbeExecutionContext
from frankenstein2.gwt_semantic_causal_readback import (
    CONTROL_NO_BROADCAST,
    INTERVENTION_BROADCAST,
    SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE,
    GwtSemanticCausalReadbackError,
    SemanticDownstreamReadback,
    SemanticExecutionContext,
    SemanticTaskSpec,
    bind_semantic_causal_readback,
    validate_semantic_causal_readback,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64
G = "1" * 64
H = "2" * 64
I = "3" * 64


def base_context(**overrides):
    values = {
        "runner_identity": "runner:vps-clay-host",
        "execution_surface": "S1:ubuntu-24.04-oci",
        "runtime_engine_identity": "python:cpython-3.11",
        "runtime_engine_config_sha256": A,
        "environment_sha256": B,
        "dependency_set_sha256": C,
        "boot_id_sha256": D,
        "exact_source_sha256": E,
        "provenance_refs": ("prov:g5-base-context",),
    }
    values.update(overrides)
    return ProbeExecutionContext(**values)


def accepted_g4_candidate():
    """Unit-scope dependency fixture with the exact G4 validator seal.

    G4's own test suite exercises construction from WP506/WP507/WP508 runtime
    evidence. G5 tests need only one already-valid dependency object and should
    not duplicate the entire G4 fixture.
    """
    candidate = g4.GwtCausalRuntimeReadbackCandidate(
        schema=g4.GWT_CAUSAL_RUNTIME_READBACK_SCHEMA,
        probe_id="probe:wp900-g5",
        exact_source_sha256=E,
        boot_id_sha256=D,
        execution_context_sha256=base_context().sha256(),
        broadcast_id="broadcast:wp900-g5",
        broadcast_sha256=F,
        recipient_cell_id="G1",
        nonbroadcast_input_sha256=A,
        intervention_downstream_ref="readback:g4:intervention",
        intervention_downstream_sha256=B,
        control_downstream_ref="readback:g4:control",
        control_downstream_sha256=C,
        runtime_witness_sha256=G,
        uptake_receipt_sha256=H,
        uptake_summary_sha256=I,
        control_readback_sha256="4" * 64,
        causal_result_sha256="5" * 64,
        causal_result_status="CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE",
        classification=g4.CAUSAL_RUNTIME_READBACK_OBSERVED,
        provenance_refs=("prov:accepted-g4-dependency",),
        _factory_seal=g4._BOUND,
    )
    object.__setattr__(candidate, "_factory_payload_sha256", g4._digest(candidate.as_dict()))
    g4.validate_causal_runtime_readback(candidate)
    return candidate


def task(**overrides):
    values = {
        "task_id": "semantic-task:wp900-g5",
        "task_family": "held-out-discrete-semantic-choice",
        "nonbroadcast_input_sha256": A,
        "oracle_ref": "oracle:held-out:wp900-g5",
        "oracle_sha256": B,
        "expected_label": "ALPHA",
        "provenance_refs": ("prov:evaluator-only-oracle",),
    }
    values.update(overrides)
    return SemanticTaskSpec.define(**values)


def semantic_context(*, execution_context=None, **overrides):
    ctx = execution_context or base_context()
    values = {
        "execution_context": ctx,
        "model_runtime_identity": "model-runtime:test-double-boundary",
        "model_artifact_sha256": G,
        "decoder_config_sha256": H,
        "model_input_context_sha256": I,
        "evaluator_oracle_context_sha256": "6" * 64,
        "provenance_refs": ("prov:model-specific-context",),
    }
    values.update(overrides)
    return SemanticExecutionContext.bind(**values)


def readback(condition, *, semantic_label, task_value=None, semantic_context_value=None, **overrides):
    task_value = task_value or task()
    semantic_context_value = semantic_context_value or semantic_context()
    values = {
        "condition": condition,
        "task": task_value,
        "semantic_execution_context": semantic_context_value,
        "runtime_instance_id": f"runtime:{condition.lower()}",
        "process_identity": f"process:{condition.lower()}",
        "nonbroadcast_input_sha256": A,
        "output_ref": f"output:{condition.lower()}",
        "output_sha256": B if condition == INTERVENTION_BROADCAST else C,
        "semantic_label": semantic_label,
        "observed_monotonic_ns": 10 if condition == INTERVENTION_BROADCAST else 20,
        "provenance_refs": (f"prov:{condition.lower()}",),
        "broadcast_id": "broadcast:wp900-g5" if condition == INTERVENTION_BROADCAST else None,
        "broadcast_sha256": F if condition == INTERVENTION_BROADCAST else None,
    }
    values.update(overrides)
    return SemanticDownstreamReadback.observe(**values)


def bind(**overrides):
    ctx = overrides.pop("execution_context", base_context())
    semantic_ctx = overrides.pop(
        "semantic_execution_context",
        semantic_context(execution_context=ctx),
    )
    task_value = overrides.pop("task", task())
    intervention = overrides.pop(
        "intervention_readback",
        readback(
            INTERVENTION_BROADCAST,
            semantic_label="ALPHA",
            task_value=task_value,
            semantic_context_value=semantic_ctx,
        ),
    )
    control = overrides.pop(
        "control_readback",
        readback(
            CONTROL_NO_BROADCAST,
            semantic_label="BETA",
            task_value=task_value,
            semantic_context_value=semantic_ctx,
        ),
    )
    return bind_semantic_causal_readback(
        g4_candidate=overrides.pop("g4_candidate", accepted_g4_candidate()),
        execution_context=ctx,
        semantic_execution_context=semantic_ctx,
        task=task_value,
        intervention_readback=intervention,
        control_readback=control,
        provenance_refs=("prov:g5-semantic-binder",),
        **overrides,
    )


def test_positive_semantic_matched_pair_binds_but_mints_zero_runtime_credit():
    candidate = bind()
    validate_semantic_causal_readback(candidate)

    assert candidate.classification == SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE
    assert candidate.intervention_semantic_label == "ALPHA"
    assert candidate.control_semantic_label == "BETA"
    assert candidate.expected_semantic_label == "ALPHA"
    assert candidate.repository_ci_credit == 0
    assert candidate.runtime_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.gwt_contract_causal_runtime_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.physical_grid10_credit == 0
    assert candidate.effect_credit == 0
    assert candidate.training_credit == 0
    assert candidate.completion_credit == 0
    assert candidate.whole_system_acceptance is False


def test_control_that_also_gets_oracle_label_fails_semantic_causality():
    task_value = task()
    semantic_ctx = semantic_context()
    with pytest.raises(GwtSemanticCausalReadbackError, match="control also produced expected label"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            control_readback=readback(
                CONTROL_NO_BROADCAST,
                semantic_label="ALPHA",
                task_value=task_value,
                semantic_context_value=semantic_ctx,
            ),
        )


def test_intervention_must_get_evaluator_expected_label():
    task_value = task()
    semantic_ctx = semantic_context()
    with pytest.raises(GwtSemanticCausalReadbackError, match="intervention did not produce expected"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            intervention_readback=readback(
                INTERVENTION_BROADCAST,
                semantic_label="BETA",
                task_value=task_value,
                semantic_context_value=semantic_ctx,
            ),
        )


def test_control_may_not_smuggle_broadcast_identity():
    task_value = task()
    semantic_ctx = semantic_context()
    with pytest.raises(GwtSemanticCausalReadbackError, match="control readback must not carry broadcast identity"):
        readback(
            CONTROL_NO_BROADCAST,
            semantic_label="BETA",
            task_value=task_value,
            semantic_context_value=semantic_ctx,
            broadcast_id="forged:broadcast",
            broadcast_sha256=F,
        )


def test_intervention_must_bind_exact_g4_broadcast():
    task_value = task()
    semantic_ctx = semantic_context()
    bad = readback(
        INTERVENTION_BROADCAST,
        semantic_label="ALPHA",
        task_value=task_value,
        semantic_context_value=semantic_ctx,
        broadcast_id="broadcast:wrong",
    )
    with pytest.raises(GwtSemanticCausalReadbackError, match="broadcast id mismatch"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            intervention_readback=bad,
        )


def test_model_and_oracle_contexts_must_be_separated_at_contract_boundary():
    with pytest.raises(GwtSemanticCausalReadbackError, match="must be distinct"):
        semantic_context(
            model_input_context_sha256=I,
            evaluator_oracle_context_sha256=I,
        )


def test_semantic_context_must_bind_exact_g4_source_and_boot():
    mismatched_base = base_context(exact_source_sha256=F)
    semantic_ctx = semantic_context(execution_context=mismatched_base)
    task_value = task()
    with pytest.raises(GwtSemanticCausalReadbackError, match="G4/base exact-source mismatch"):
        bind(
            execution_context=mismatched_base,
            semantic_execution_context=semantic_ctx,
            task=task_value,
            intervention_readback=readback(
                INTERVENTION_BROADCAST,
                semantic_label="ALPHA",
                task_value=task_value,
                semantic_context_value=semantic_ctx,
            ),
            control_readback=readback(
                CONTROL_NO_BROADCAST,
                semantic_label="BETA",
                task_value=task_value,
                semantic_context_value=semantic_ctx,
            ),
        )


def test_semantic_task_input_must_match_g4_matched_nonbroadcast_input():
    task_value = task(nonbroadcast_input_sha256=F)
    semantic_ctx = semantic_context()
    with pytest.raises(GwtSemanticCausalReadbackError, match="task input does not match G4"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            intervention_readback=readback(
                INTERVENTION_BROADCAST,
                semantic_label="ALPHA",
                task_value=task_value,
                semantic_context_value=semantic_ctx,
                nonbroadcast_input_sha256=F,
            ),
            control_readback=readback(
                CONTROL_NO_BROADCAST,
                semantic_label="BETA",
                task_value=task_value,
                semantic_context_value=semantic_ctx,
                nonbroadcast_input_sha256=F,
            ),
        )


def test_readback_from_different_semantic_context_is_rejected():
    task_value = task()
    semantic_ctx = semantic_context()
    other_ctx = semantic_context(decoder_config_sha256="7" * 64)
    bad_control = readback(
        CONTROL_NO_BROADCAST,
        semantic_label="BETA",
        task_value=task_value,
        semantic_context_value=other_ctx,
    )
    with pytest.raises(GwtSemanticCausalReadbackError, match="control semantic execution-context mismatch"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            control_readback=bad_control,
        )


def test_identical_downstream_output_digest_fails_even_when_labels_differ():
    task_value = task()
    semantic_ctx = semantic_context()
    intervention = readback(
        INTERVENTION_BROADCAST,
        semantic_label="ALPHA",
        task_value=task_value,
        semantic_context_value=semantic_ctx,
        output_sha256=C,
    )
    control = readback(
        CONTROL_NO_BROADCAST,
        semantic_label="BETA",
        task_value=task_value,
        semantic_context_value=semantic_ctx,
        output_sha256=C,
    )
    with pytest.raises(GwtSemanticCausalReadbackError, match="identical downstream output digest"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            intervention_readback=intervention,
            control_readback=control,
        )


def test_direct_semantic_readback_constructor_is_not_admitted():
    task_value = task()
    semantic_ctx = semantic_context()
    direct = SemanticDownstreamReadback(
        condition=CONTROL_NO_BROADCAST,
        task_sha256=task_value.sha256(),
        semantic_execution_context_sha256=semantic_ctx.sha256(),
        runtime_instance_id="runtime:direct",
        process_identity="process:direct",
        model_artifact_sha256=G,
        decoder_config_sha256=H,
        nonbroadcast_input_sha256=A,
        broadcast_id=None,
        broadcast_sha256=None,
        output_ref="output:direct",
        output_sha256=C,
        semantic_label="BETA",
        semantic_label_sha256=__import__("hashlib").sha256(b"BETA").hexdigest(),
        observed_monotonic_ns=20,
        provenance_refs=("prov:direct",),
    )
    with pytest.raises(GwtSemanticCausalReadbackError, match="observation factory origin"):
        bind(
            task=task_value,
            semantic_execution_context=semantic_ctx,
            control_readback=direct,
        )


def test_bound_candidate_tamper_is_rejected():
    candidate = bind()
    forged = replace(candidate, control_semantic_label="GAMMA")
    with pytest.raises(GwtSemanticCausalReadbackError, match="changed after bind"):
        validate_semantic_causal_readback(forged)
