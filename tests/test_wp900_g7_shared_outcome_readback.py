import runpy
from pathlib import Path

import pytest

from frankenstein2.gwt_semantic_runtime_readback import (
    GwtSemanticRuntimeReadbackError,
    MATCHED_TASK_OUTCOME_SCHEMA,
    SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE,
    SEMANTIC_COMPARISON_UNKNOWN,
    SEMANTIC_DIFFERENCE_OBSERVED,
    SEMANTIC_UNKNOWN_FAIL_CLOSED,
    MatchedTaskOutcomeReadback,
    WP900_CONTROL_RAW_OUTCOME_SCHEMA,
    WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
    WP900_MATCHED_TASK_SCHEMA,
    bind_semantic_causal_readback,
    validate_matched_task_outcome_readback,
)

_G6 = runpy.run_path(str(Path(__file__).with_name("test_wp900_g6_semantic_runtime_readback.py")))
make_contract = _G6["make_contract"]
sha256_bytes = _G6["sha256_bytes"]
arm = _G6["arm"]
D = _G6["D"]
E = _G6["E"]


def _observe_pair(*, intervention_payload: bytes, control_payload: bytes):
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(control_payload))
    intervention = MatchedTaskOutcomeReadback.observe_from_g4(
        contract_candidate=contract,
        condition="INTERVENTION_BROADCAST",
        task_id="task:wp900:g7:matched-reentry",
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        raw_outcome_schema=WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
        raw_payload=intervention_payload,
        producer_identity="producer:wp900:g7:intervention",
        runtime_instance_id="runtime:wp900:g7:intervention",
        observed_monotonic_ns=70,
        provenance_refs=("prov:wp900:g7:intervention",),
    )
    control = MatchedTaskOutcomeReadback.observe_from_g4(
        contract_candidate=contract,
        condition="CONTROL_NO_BROADCAST",
        task_id="task:wp900:g7:matched-reentry",
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        raw_outcome_schema=WP900_CONTROL_RAW_OUTCOME_SCHEMA,
        raw_payload=control_payload,
        producer_identity="producer:wp900:g7:control",
        runtime_instance_id="runtime:wp900:g7:control",
        observed_monotonic_ns=80,
        provenance_refs=("prov:wp900:g7:control",),
    )
    return contract, intervention, control


def test_g7_shared_outcome_preserves_distinct_raw_schemas_and_exact_g4_lineage():
    intervention_payload = b'{"cell_id":"G1","status":"COMPLETE","output_refs":["readback:intervention"]}'
    control_payload = b'{"probe_id":"probe:wp900-g7","reentry_observed":false}'
    contract, intervention, control = _observe_pair(
        intervention_payload=intervention_payload,
        control_payload=control_payload,
    )

    validate_matched_task_outcome_readback(intervention)
    validate_matched_task_outcome_readback(control)

    assert intervention.raw_outcome_schema == WP900_INTERVENTION_RAW_OUTCOME_SCHEMA
    assert control.raw_outcome_schema == WP900_CONTROL_RAW_OUTCOME_SCHEMA
    assert intervention.raw_outcome_schema != control.raw_outcome_schema
    assert intervention.outcome_schema == MATCHED_TASK_OUTCOME_SCHEMA
    assert control.outcome_schema == MATCHED_TASK_OUTCOME_SCHEMA
    assert intervention.downstream_sha256 == contract.intervention_downstream_sha256
    assert control.downstream_sha256 == contract.control_downstream_sha256
    assert intervention.exact_source_sha256 == contract.exact_source_sha256 == E
    assert control.exact_source_sha256 == contract.exact_source_sha256 == E
    assert intervention.boot_id_sha256 == contract.boot_id_sha256 == D
    assert control.boot_id_sha256 == contract.boot_id_sha256 == D
    assert intervention.execution_context_sha256 == contract.execution_context_sha256
    assert control.execution_context_sha256 == contract.execution_context_sha256
    assert intervention.reentry_observed is True
    assert control.reentry_observed is False
    assert intervention.semantic_gwt_runtime_credit == 0
    assert control.jspace_runtime_credit == 0
    assert intervention.whole_system_acceptance is False


def test_g7_shared_outcome_becomes_only_zero_credit_semantic_difference_candidate():
    intervention_payload = b'{"cell_id":"G1","status":"COMPLETE"}'
    control_payload = b'{"probe_id":"probe:wp900-g7","reentry_observed":false}'
    contract, intervention, control = _observe_pair(
        intervention_payload=intervention_payload,
        control_payload=control_payload,
    )

    intervention_arm = intervention.to_semantic_arm()
    control_arm = control.to_semantic_arm()
    result = bind_semantic_causal_readback(
        contract_candidate=contract,
        intervention=intervention_arm,
        control=control_arm,
        provenance_refs=("prov:wp900:g7:semantic-bind",),
    )

    assert intervention_arm.task_schema == control_arm.task_schema == WP900_MATCHED_TASK_SCHEMA
    assert intervention_arm.outcome_schema == control_arm.outcome_schema == MATCHED_TASK_OUTCOME_SCHEMA
    assert intervention_arm.semantic_sha256 != control_arm.semantic_sha256
    assert result.comparison_status == SEMANTIC_DIFFERENCE_OBSERVED
    assert result.classification == SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE
    assert result.target_environment_component_runtime_credit == 0
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
    assert result.effect_credit == 0
    assert result.training_credit == 0
    assert result.completion_credit == 0
    assert result.whole_system_acceptance is False


def test_g7_rejects_wrong_condition_specific_raw_schema_before_projection():
    intervention_payload = b'{"cell_id":"G1","status":"COMPLETE"}'
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(b'{"reentry_observed":false}'))

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="raw outcome schema does not match"):
        MatchedTaskOutcomeReadback.observe_from_g4(
            contract_candidate=contract,
            condition="INTERVENTION_BROADCAST",
            task_id="task:wp900:g7:matched-reentry",
            task_schema=WP900_MATCHED_TASK_SCHEMA,
            raw_outcome_schema=WP900_CONTROL_RAW_OUTCOME_SCHEMA,
            raw_payload=intervention_payload,
            producer_identity="producer:wp900:g7:intervention",
            runtime_instance_id="runtime:wp900:g7:intervention",
            observed_monotonic_ns=70,
            provenance_refs=("prov:wp900:g7:bad-schema",),
        )


def test_g7_rejects_wrong_task_schema_and_wrong_exact_raw_digest():
    intervention_payload = b'{"cell_id":"G1","status":"COMPLETE"}'
    control_payload = b'{"reentry_observed":false}'
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(control_payload))

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="task schema does not bind"):
        MatchedTaskOutcomeReadback.observe_from_g4(
            contract_candidate=contract,
            condition="INTERVENTION_BROADCAST",
            task_id="task:wp900:g7:matched-reentry",
            task_schema="attacker-relabel/v1",
            raw_outcome_schema=WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
            raw_payload=intervention_payload,
            producer_identity="producer:wp900:g7:intervention",
            runtime_instance_id="runtime:wp900:g7:intervention",
            observed_monotonic_ns=70,
            provenance_refs=("prov:wp900:g7:bad-task",),
        )

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="raw payload does not match accepted G4 downstream SHA-256"):
        MatchedTaskOutcomeReadback.observe_from_g4(
            contract_candidate=contract,
            condition="INTERVENTION_BROADCAST",
            task_id="task:wp900:g7:matched-reentry",
            task_schema=WP900_MATCHED_TASK_SCHEMA,
            raw_outcome_schema=WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
            raw_payload=b'{"cell_id":"G1","status":"FAILED"}',
            producer_identity="producer:wp900:g7:intervention",
            runtime_instance_id="runtime:wp900:g7:intervention",
            observed_monotonic_ns=70,
            provenance_refs=("prov:wp900:g7:wrong-bytes",),
        )


def test_g7_direct_constructor_cannot_forge_factory_observation_or_lineage():
    forged = MatchedTaskOutcomeReadback(
        condition="CONTROL_NO_BROADCAST",
        task_id="task:wp900:g7:matched-reentry",
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        raw_outcome_schema=WP900_CONTROL_RAW_OUTCOME_SCHEMA,
        downstream_ref="readback:forged",
        downstream_sha256="a" * 64,
        reentry_observed=True,
        exact_source_sha256="9" * 64,
        boot_id_sha256="8" * 64,
        execution_context_sha256="7" * 64,
        producer_identity="producer:forged",
        runtime_instance_id="runtime:forged",
        observed_monotonic_ns=1,
        provenance_refs=("prov:forged",),
    )

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="lacks observation-factory origin"):
        validate_matched_task_outcome_readback(forged)
    with pytest.raises(GwtSemanticRuntimeReadbackError, match="lacks observation-factory origin"):
        forged.to_semantic_arm()


def test_historical_g6_distinct_raw_outcome_schemas_remain_unknown_without_g7_bridge():
    intervention_payload = b'{"cell_id":"G1","status":"COMPLETE"}'
    control_payload = b'{"probe_id":"probe:wp900-g7","reentry_observed":false}'
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(control_payload))
    intervention = arm(
        contract=contract,
        condition="INTERVENTION_BROADCAST",
        raw_payload=intervention_payload,
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        outcome_schema=WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
    )
    control = arm(
        contract=contract,
        condition="CONTROL_NO_BROADCAST",
        raw_payload=control_payload,
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        outcome_schema=WP900_CONTROL_RAW_OUTCOME_SCHEMA,
    )
    result = bind_semantic_causal_readback(
        contract_candidate=contract,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:wp900:g7:historical-g6",),
    )

    assert result.comparison_status == SEMANTIC_COMPARISON_UNKNOWN
    assert result.classification == SEMANTIC_UNKNOWN_FAIL_CLOSED
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
