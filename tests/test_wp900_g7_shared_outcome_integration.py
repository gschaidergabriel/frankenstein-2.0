import pytest

from frankenstein2.gwt_semantic_runtime_readback import (
    GwtSemanticRuntimeReadbackError,
    MatchedTaskOutcomeReadback,
    SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE,
    SEMANTIC_DIFFERENCE_OBSERVED,
    WP900_CONTROL_RAW_OUTCOME_SCHEMA,
    WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
    WP900_MATCHED_TASK_SCHEMA,
    bind_semantic_causal_readback,
    validate_matched_task_outcome_readback,
    validate_semantic_causal_readback,
)
from tests.test_wp900_g6_semantic_runtime_readback import make_contract, sha256_bytes


def _observe(contract, *, condition: str, raw_schema: str, payload: bytes, observed_ns: int):
    return MatchedTaskOutcomeReadback.observe_from_g4(
        contract_candidate=contract,
        condition=condition,
        task_id="task:wp900-g7-shared-outcome",
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        raw_outcome_schema=raw_schema,
        raw_payload=payload,
        producer_identity=f"producer:{condition.lower()}",
        runtime_instance_id=f"runtime:{condition.lower()}",
        observed_monotonic_ns=observed_ns,
        provenance_refs=(f"prov:{condition.lower()}",),
    )


def test_g7_factory_bridge_composes_exact_g4_bytes_into_g6_shared_semantic_comparison():
    intervention_payload = b'{"cell":"G1","status":"COMPLETE"}'
    control_payload = b'{"broadcast":false,"reentry":false}'
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(control_payload))

    intervention_readback = _observe(
        contract,
        condition="INTERVENTION_BROADCAST",
        raw_schema=WP900_INTERVENTION_RAW_OUTCOME_SCHEMA,
        payload=intervention_payload,
        observed_ns=70,
    )
    control_readback = _observe(
        contract,
        condition="CONTROL_NO_BROADCAST",
        raw_schema=WP900_CONTROL_RAW_OUTCOME_SCHEMA,
        payload=control_payload,
        observed_ns=80,
    )
    validate_matched_task_outcome_readback(intervention_readback)
    validate_matched_task_outcome_readback(control_readback)

    result = bind_semantic_causal_readback(
        contract_candidate=contract,
        intervention=intervention_readback.to_semantic_arm(),
        control=control_readback.to_semantic_arm(),
        provenance_refs=("prov:wp900-g7-shared-outcome",),
    )
    validate_semantic_causal_readback(result)

    assert result.comparison_status == SEMANTIC_DIFFERENCE_OBSERVED
    assert result.classification == SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
    assert result.target_environment_component_runtime_credit == 0
    assert result.effect_credit == 0
    assert result.completion_credit == 0
    assert result.whole_system_acceptance is False


def test_g7_rejects_condition_schema_relabel_before_shared_semantic_projection():
    payload = b'{"cell":"G1","status":"COMPLETE"}'
    contract = make_contract(sha256_bytes(payload), sha256_bytes(b'{"broadcast":false}'))

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="raw outcome schema does not match"):
        _observe(
            contract,
            condition="INTERVENTION_BROADCAST",
            raw_schema=WP900_CONTROL_RAW_OUTCOME_SCHEMA,
            payload=payload,
            observed_ns=70,
        )
