from dataclasses import replace
import inspect
import runpy
from pathlib import Path

import pytest

from frankenstein2.gwt_causal_runtime_readback import (
    ControlNoBroadcastReadback,
    GwtCausalRuntimeReadbackError,
    bind_causal_runtime_readback,
)
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessError
from frankenstein2.gwt_semantic_runtime_readback import (
    GwtSemanticRuntimeReadbackError,
    MATCHED_TASK_OUTCOME_SCHEMA,
    SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE,
    SEMANTIC_DIFFERENCE_OBSERVED,
    WP900_MATCHED_TASK_SCHEMA,
    bind_independent_reentry_evidence,
    validate_semantic_causal_readback,
)

_G4 = runpy.run_path(str(Path(__file__).with_name("test_gwt_causal_runtime_readback.py")))
make_fixture = _G4["make_fixture"]
context = _G4["context"]
control = _G4["control"]
A = _G4["A"]
B = _G4["B"]
D = _G4["D"]
E = _G4["E"]


def make_g8_fixture():
    broadcast, runtime_witness, uptake_receipt, uptake_summary = make_fixture()
    execution_context = context()
    control_readback = control(execution_context=execution_context)
    contract = bind_causal_runtime_readback(
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=A,
        execution_context=execution_context,
        broadcast=broadcast,
        runtime_witness=runtime_witness,
        uptake_receipt=uptake_receipt,
        uptake_summary=uptake_summary,
        control_readback=control_readback,
        provenance_refs=("prov:wp900:g8:g4-contract",),
    )
    return contract, runtime_witness, control_readback


def bind_g8(*, contract=None, runtime_witness=None, control_readback=None):
    observed_contract, observed_witness, observed_control = make_g8_fixture()
    return bind_independent_reentry_evidence(
        contract_candidate=observed_contract if contract is None else contract,
        intervention_runtime_witness=observed_witness if runtime_witness is None else runtime_witness,
        control_readback=observed_control if control_readback is None else control_readback,
        task_id="task:wp900:g8:independent-reentry",
        provenance_refs=("prov:wp900:g8:independent-observation",),
    )


def test_g8_derives_non_circular_reentry_difference_from_exact_g4_bound_observations():
    contract, runtime_witness, control_readback = make_g8_fixture()
    result = bind_independent_reentry_evidence(
        contract_candidate=contract,
        intervention_runtime_witness=runtime_witness,
        control_readback=control_readback,
        task_id="task:wp900:g8:independent-reentry",
        provenance_refs=("prov:wp900:g8:positive",),
    )
    validate_semantic_causal_readback(result)

    assert runtime_witness.sha256() == contract.runtime_witness_sha256
    assert control_readback.sha256() == contract.control_readback_sha256
    assert result.task_id == "task:wp900:g8:independent-reentry"
    assert result.intervention_task_schema == result.control_task_schema == WP900_MATCHED_TASK_SCHEMA
    assert result.intervention_outcome_schema == result.control_outcome_schema == MATCHED_TASK_OUTCOME_SCHEMA
    assert result.comparison_status == SEMANTIC_DIFFERENCE_OBSERVED
    assert result.classification == SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE
    assert result.exact_source_sha256 == E
    assert result.boot_id_sha256 == D
    assert result.target_environment_component_runtime_credit == 0
    assert result.runtime_credit == 0
    assert result.gwt_runtime_credit == 0
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
    assert result.physical_grid10_credit == 0
    assert result.effect_credit == 0
    assert result.training_credit == 0
    assert result.completion_credit == 0
    assert result.whole_system_acceptance is False


def test_g8_surface_has_no_caller_selected_arm_condition_or_reentry_boolean():
    parameters = inspect.signature(bind_independent_reentry_evidence).parameters
    assert "condition" not in parameters
    assert "reentry_observed" not in parameters
    assert "intervention_observed" not in parameters
    assert "control_observed" not in parameters


def test_g8_rejects_arm_type_swap_instead_of_relabeling_it():
    contract, runtime_witness, control_readback = make_g8_fixture()

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="intervention evidence must be exact GwtRuntimeWitnessReceipt"):
        bind_independent_reentry_evidence(
            contract_candidate=contract,
            intervention_runtime_witness=control_readback,
            control_readback=control_readback,
            task_id="task:wp900:g8:swap",
            provenance_refs=("prov:wp900:g8:swap-intervention",),
        )

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="control evidence must be exact ControlNoBroadcastReadback"):
        bind_independent_reentry_evidence(
            contract_candidate=contract,
            intervention_runtime_witness=runtime_witness,
            control_readback=runtime_witness,
            task_id="task:wp900:g8:swap",
            provenance_refs=("prov:wp900:g8:swap-control",),
        )


def test_g8_rejects_valid_but_wrong_control_observation_hash():
    _, _, observed_control = make_g8_fixture()
    wrong_control = control(downstream_sha256=B)

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="does not bind G4 control_readback_sha256"):
        bind_g8(control_readback=wrong_control)

    assert wrong_control.sha256() != observed_control.sha256()


def test_g8_rejects_tampered_runtime_witness_payload_before_semantic_projection():
    _, runtime_witness, _ = make_g8_fixture()
    tampered = replace(runtime_witness, broadcast_sha256=B)

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="invalid intervention runtime witness"):
        bind_g8(runtime_witness=tampered)


def test_g8_rejects_tampered_control_payload_before_semantic_projection():
    _, _, control_readback = make_g8_fixture()
    tampered = replace(control_readback, downstream_sha256=B)

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="invalid control readback"):
        bind_g8(control_readback=tampered)


def test_g8_missing_reentry_cannot_form_a_canonical_runtime_witness():
    _, runtime_witness, _ = make_g8_fixture()

    with pytest.raises(GwtRuntimeWitnessError, match="events must contain exactly DELIVERY, UPTAKE and REENTRY"):
        replace(runtime_witness, events=runtime_witness.events[:2])


def test_g8_malformed_event_order_cannot_form_a_canonical_runtime_witness():
    _, runtime_witness, _ = make_g8_fixture()
    delivery, uptake, reentry = runtime_witness.events

    with pytest.raises(GwtRuntimeWitnessError, match="runtime observation phases must be DELIVERY -> UPTAKE -> REENTRY"):
        replace(runtime_witness, events=(delivery, reentry, uptake))


def test_g8_control_direct_constructor_without_factory_origin_is_rejected():
    contract, runtime_witness, control_readback = make_g8_fixture()
    direct = ControlNoBroadcastReadback(
        runtime_instance_id=control_readback.runtime_instance_id,
        process_identity=control_readback.process_identity,
        boot_id_sha256=control_readback.boot_id_sha256,
        exact_source_sha256=control_readback.exact_source_sha256,
        execution_context_sha256=control_readback.execution_context_sha256,
        probe_id=control_readback.probe_id,
        nonbroadcast_input_sha256=control_readback.nonbroadcast_input_sha256,
        downstream_ref=control_readback.downstream_ref,
        downstream_sha256=control_readback.downstream_sha256,
        observed_monotonic_ns=control_readback.observed_monotonic_ns,
        reentry_observed=False,
        provenance_refs=("prov:wp900:g8:direct-control",),
    )

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="invalid control readback"):
        bind_independent_reentry_evidence(
            contract_candidate=contract,
            intervention_runtime_witness=runtime_witness,
            control_readback=direct,
            task_id="task:wp900:g8:direct-control",
            provenance_refs=("prov:wp900:g8:direct-control-bind",),
        )


def test_g8_identity_or_context_drift_cannot_be_composed_with_accepted_contract():
    contract, runtime_witness, _ = make_g8_fixture()
    drift_context = context(runtime_engine_config_sha256=B)
    drift_control = control(execution_context=drift_context)

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="does not bind G4 control_readback_sha256"):
        bind_independent_reentry_evidence(
            contract_candidate=contract,
            intervention_runtime_witness=runtime_witness,
            control_readback=drift_control,
            task_id="task:wp900:g8:context-drift",
            provenance_refs=("prov:wp900:g8:context-drift",),
        )


def test_g8_cannot_use_a_control_that_claims_reentry():
    with pytest.raises(GwtCausalRuntimeReadbackError, match="must not claim GWT re-entry"):
        control(reentry_observed=True)
