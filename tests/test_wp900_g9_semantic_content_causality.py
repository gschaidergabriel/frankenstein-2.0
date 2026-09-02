import hashlib
import inspect
from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_semantic_content_causality import (
    CONTENT_CAUSALITY_READY,
    ConditionBlindTaskOutcomeReadback,
    GwtSemanticContentCausalityError,
    NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE,
    SEMANTIC_CONTENT_CAUSALITY_UNKNOWN,
    SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE,
    UNKNOWN_MECHANICS_MISMATCH,
    UNKNOWN_MECHANISM_PATH,
    UNKNOWN_ORDER,
    UNKNOWN_REPEAT_INSTABILITY,
    UNKNOWN_SEMANTIC_CONTENT,
    SemanticContentTrial,
    bind_semantic_content_crossover,
    validate_semantic_content_crossover,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)

SOURCE = "a" * 64
BOOT = "b" * 64
CONTEXT = "c" * 64
FRAME = "d" * 64
POLICY_SHA = "e" * 64
TASK_INPUT = "f" * 64
PRE_STATE = "1" * 64
EXECUTOR = "2" * 64
UPTAKE_DOWNSTREAM = "3" * 64

PAYLOAD_A = b'{"instruction":"ALLOW","reason":"sufficient-evidence"}'
PAYLOAD_B = b'{"instruction":"DENY","reason":"policy-block"}'
PAYLOAD_A_EQUIV_BYTES = b'{ "reason":"sufficient-evidence", "instruction":"ALLOW" }'
OUTCOME_A = b'{"decision":"ALLOW","reason":"sufficient-evidence"}'
OUTCOME_B = b'{"decision":"DENY","reason":"policy-block"}'
OUTCOME_SAME = b'{"decision":"ABSTAIN","reason":"insufficient-evidence"}'


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def plan() -> Grid10Plan:
    return Grid10Plan.create(
        plan_id="grid-plan-wp900-g9", cycle_id="cycle-wp900-g9", generation=9,
        frame_id="frame-wp900-g9", frame_generation=1, frame_sha256=FRAME,
        policy_id="grid-policy-wp900-g9", policy_generation=1, policy_sha256=POLICY_SHA,
        cells=tuple(CellBudget(cell_id=f"G{i}", role_label=f"role-{i}", max_input_refs=8,
            max_output_refs=8, max_work_units=8, max_reentry_depth=2) for i in range(1, 11)),
        max_total_work_units=80, provenance_refs=("prov:g9-plan",))


PLAN = plan()


def runtime_fixture(*, payload: bytes, position: int, delivery="DELIVERED", uptake="UPTAKEN", plan_value=PLAN):
    payload_ref = f"sha256:{sha256_bytes(payload)}"
    producer_input = CellInput.for_plan(plan_value, cell_id="G1", work_units_requested=2,
        input_refs=("input:g9",), provenance_refs=(f"prov:g9:producer-input:{position}",))
    producer_output = CellOutput.for_input(plan_value, producer_input, status="COMPLETE", work_units_used=1,
        output_refs=(payload_ref,), evidence_refs=(f"evidence:g9:{position}",),
        provenance_refs=(f"prov:g9:producer-output:{position}",))
    candidate = WorkspaceCandidate(candidate_id=f"candidate:g9:{position}", payload_ref=payload_ref,
        epistemic_class="INFERRED", provenance_refs=(f"prov:g9:candidate:{position}",),
        salience_micros=500_000, goal_relevance_micros=500_000, uncertainty_micros=100_000,
        information_gain_micros=500_000, estimated_cost_units=1,
        producer_admission=CandidateProducerAdmission(plan=plan_value, cell_input=producer_input, cell_output=producer_output))
    selection_policy = SelectionPolicy(policy_id="selection-policy:g9", generation=1,
        max_selected_candidates=1, max_total_cost_units=4, salience_weight=1, goal_relevance_weight=1,
        uncertainty_weight=1, information_gain_weight=1, cost_weight=1)
    selection = build_workspace_selection(selection_id=f"selection:g9:{position}", cycle_id=plan_value.cycle_id,
        generation=1, frame_id=plan_value.frame_id, frame_generation=plan_value.frame_generation,
        frame_sha256=plan_value.frame_sha256, grid_plan_id=plan_value.plan_id,
        grid_plan_generation=plan_value.generation, grid_plan_sha256=plan_value.sha256(),
        policy=selection_policy, candidates=(candidate,))
    broadcast = create_broadcast(broadcast_id=f"broadcast:g9:{position}", generation=1, selection=selection,
        expected_selection_sha256=selection.sha256(), recipient_cell_ids=("G1",))
    reentry_input = CellInput.for_plan(plan_value, cell_id="G1", work_units_requested=2, reentry_depth=1,
        input_refs=(payload_ref,), provenance_refs=(f"prov:g9:reentry-input:{position}",))
    reentry_witness = build_reentry_witness(plan=plan_value, selection=selection, broadcast=broadcast, cell_input=reentry_input)
    uptake_receipt = CellUptakeReceipt.observe(receipt_id=f"receipt:g9:{position}", broadcast=broadcast, cell_id="G1",
        delivery_status=delivery, uptake_status=uptake,
        downstream_ref=f"downstream:g9:{position}" if uptake == "UPTAKEN" else None,
        downstream_sha256=UPTAKE_DOWNSTREAM if uptake == "UPTAKEN" else None,
        provenance_refs=(f"prov:g9:uptake:{position}",))
    binding = bind_reentry_to_uptake(binding_id=f"binding:g9:{position}", witness=reentry_witness,
        uptake_receipt=uptake_receipt, plan=plan_value, selection=selection, broadcast=broadcast,
        cell_input=reentry_input, provenance_refs=(f"prov:g9:binding:{position}",))
    ticks = iter((position * 100 + 10, position * 100 + 20, position * 100 + 30))
    recorder = GwtRuntimeWitnessRecorder(identity=RuntimeObservationIdentity(runtime_instance_id=f"runtime:g9:{position}",
        process_identity=f"pid:{1000 + position}:start:1", boot_id_sha256=BOOT, exact_source_sha256=SOURCE),
        monotonic_ns=lambda: next(ticks))
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(uptake_receipt)
    recorder.observe_reentry(witness=reentry_witness, binding=binding, plan=plan_value,
        selection=selection, cell_input=reentry_input)
    return broadcast, recorder.seal()


def outcome(*, raw: bytes, position: int, pre_state=PRE_STATE, execution_context=CONTEXT, source=SOURCE):
    return ConditionBlindTaskOutcomeReadback.observe_json(
        task_id="task:wp900:g9:content-crossover", task_schema="F2_WP900_G9_MATCHED_CONTENT_TASK/v1",
        outcome_schema="F2_WP900_G9_TASK_OUTCOME/v1", raw_outcome=raw,
        exact_source_sha256=source, boot_id_sha256=BOOT, execution_context_sha256=execution_context,
        task_input_sha256=TASK_INPUT, pre_state_sha256=pre_state, task_executor_sha256=EXECUTOR,
        observer_identity="observer:wp900:g9:condition-blind", observed_monotonic_ns=position * 100 + 90,
        provenance_refs=(f"prov:g9:outcome:{position}",))


def trial(*, payload: bytes, outcome_raw: bytes, position: int, delivery="DELIVERED", uptake="UPTAKEN",
          pre_state=PRE_STATE, plan_value=PLAN):
    broadcast, witness = runtime_fixture(payload=payload, position=position, delivery=delivery,
        uptake=uptake, plan_value=plan_value)
    return SemanticContentTrial.observe(trial_id=f"trial:g9:{position}", order_position=position,
        semantic_payload=payload, broadcast=broadcast, runtime_witness=witness,
        outcome=outcome(raw=outcome_raw, position=position, pre_state=pre_state),
        provenance_refs=(f"prov:g9:trial:{position}",))


def crossover(outcomes=(OUTCOME_A, OUTCOME_B, OUTCOME_B, OUTCOME_A),
              payloads=(PAYLOAD_A, PAYLOAD_B, PAYLOAD_B, PAYLOAD_A)):
    trials = tuple(trial(payload=payload, outcome_raw=observed, position=index)
        for index, (payload, observed) in enumerate(zip(payloads, outcomes), start=1))
    return bind_semantic_content_crossover(trials=trials, provenance_refs=("prov:g9:crossover",))


def test_g9_counterbalanced_same_mechanism_distinct_semantics_is_zero_credit_candidate():
    candidate = crossover()
    validate_semantic_content_crossover(candidate)
    assert candidate.classification == SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE
    assert candidate.reason == CONTENT_CAUSALITY_READY
    assert len(set(candidate.payload_semantic_sha256s)) == 2
    assert len(set(candidate.outcome_semantic_sha256s)) == 2
    assert candidate.repository_ci_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.effect_credit == 0
    assert candidate.training_credit == 0
    assert candidate.completion_credit == 0
    assert candidate.whole_system_acceptance is False


def test_g9_condition_blind_observer_api_has_no_treatment_or_mechanism_labels():
    params = set(inspect.signature(ConditionBlindTaskOutcomeReadback.observe_json).parameters)
    forbidden = {"condition", "arm", "treatment", "expected_result", "broadcast", "broadcast_present",
        "delivery_status", "uptake_status", "reentry_observed", "semantic_payload", "semantic_payload_ref"}
    assert forbidden.isdisjoint(params)
    assert forbidden.isdisjoint(ConditionBlindTaskOutcomeReadback.__dataclass_fields__)


def test_g9_both_contents_reenter_but_equal_task_semantics_is_no_difference():
    candidate = crossover(outcomes=(OUTCOME_SAME, OUTCOME_SAME, OUTCOME_SAME, OUTCOME_SAME))
    assert candidate.classification == NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0


def test_g9_missing_uptake_path_is_unknown_not_semantic_difference():
    values = [trial(payload=PAYLOAD_A, outcome_raw=OUTCOME_A, position=1),
        trial(payload=PAYLOAD_B, outcome_raw=OUTCOME_B, position=2, uptake="NOT_UPTAKEN"),
        trial(payload=PAYLOAD_B, outcome_raw=OUTCOME_B, position=3),
        trial(payload=PAYLOAD_A, outcome_raw=OUTCOME_A, position=4)]
    candidate = bind_semantic_content_crossover(trials=tuple(values), provenance_refs=("prov:g9:mechanism-negative",))
    assert candidate.classification == SEMANTIC_CONTENT_CAUSALITY_UNKNOWN
    assert candidate.reason == UNKNOWN_MECHANISM_PATH


def test_g9_same_content_repeat_instability_is_unknown_order_or_state_effect():
    candidate = crossover(outcomes=(OUTCOME_A, OUTCOME_B, OUTCOME_B, OUTCOME_SAME))
    assert candidate.classification == SEMANTIC_CONTENT_CAUSALITY_UNKNOWN
    assert candidate.reason == UNKNOWN_REPEAT_INSTABILITY


def test_g9_non_counterbalanced_aabb_order_is_unknown():
    candidate = crossover(payloads=(PAYLOAD_A, PAYLOAD_A, PAYLOAD_B, PAYLOAD_B),
        outcomes=(OUTCOME_A, OUTCOME_A, OUTCOME_B, OUTCOME_B))
    assert candidate.classification == SEMANTIC_CONTENT_CAUSALITY_UNKNOWN
    assert candidate.reason == UNKNOWN_ORDER


def test_g9_mechanics_mismatch_is_unknown_not_content_effect():
    values = [trial(payload=PAYLOAD_A, outcome_raw=OUTCOME_A, position=1),
        trial(payload=PAYLOAD_B, outcome_raw=OUTCOME_B, position=2),
        trial(payload=PAYLOAD_B, outcome_raw=OUTCOME_B, position=3, pre_state="9" * 64),
        trial(payload=PAYLOAD_A, outcome_raw=OUTCOME_A, position=4)]
    candidate = bind_semantic_content_crossover(trials=tuple(values), provenance_refs=("prov:g9:mechanics-mismatch",))
    assert candidate.classification == SEMANTIC_CONTENT_CAUSALITY_UNKNOWN
    assert candidate.reason == UNKNOWN_MECHANICS_MISMATCH


def test_g9_raw_distinct_but_semantically_equivalent_content_is_unknown():
    candidate = crossover(payloads=(PAYLOAD_A, PAYLOAD_A_EQUIV_BYTES, PAYLOAD_A_EQUIV_BYTES, PAYLOAD_A),
        outcomes=(OUTCOME_A, OUTCOME_B, OUTCOME_B, OUTCOME_A))
    assert candidate.classification == SEMANTIC_CONTENT_CAUSALITY_UNKNOWN
    assert candidate.reason == UNKNOWN_SEMANTIC_CONTENT


def test_g9_payload_ref_must_content_address_exact_payload_bytes():
    broadcast, witness = runtime_fixture(payload=PAYLOAD_A, position=1)
    with pytest.raises(GwtSemanticContentCausalityError, match="payload_ref is not exact"):
        SemanticContentTrial.observe(trial_id="trial:g9:bad-content-ref", order_position=1,
            semantic_payload=PAYLOAD_B, broadcast=broadcast, runtime_witness=witness,
            outcome=outcome(raw=OUTCOME_A, position=1), provenance_refs=("prov:g9:bad-content-ref",))


def test_g9_outcome_source_must_match_runtime_witness():
    broadcast, witness = runtime_fixture(payload=PAYLOAD_A, position=1)
    wrong_source = outcome(raw=OUTCOME_A, position=1, source="7" * 64)
    with pytest.raises(GwtSemanticContentCausalityError, match="source identity"):
        SemanticContentTrial.observe(trial_id="trial:g9:bad-source", order_position=1,
            semantic_payload=PAYLOAD_A, broadcast=broadcast, runtime_witness=witness,
            outcome=wrong_source, provenance_refs=("prov:g9:bad-source",))


def test_g9_direct_forged_outcome_or_trial_cannot_cross_factory_boundary():
    good_outcome = outcome(raw=OUTCOME_A, position=1)
    forged_outcome = replace(good_outcome)
    broadcast, witness = runtime_fixture(payload=PAYLOAD_A, position=1)
    with pytest.raises(GwtSemanticContentCausalityError, match="factory origin"):
        SemanticContentTrial.observe(trial_id="trial:g9:forged-outcome", order_position=1,
            semantic_payload=PAYLOAD_A, broadcast=broadcast, runtime_witness=witness,
            outcome=forged_outcome, provenance_refs=("prov:g9:forged-outcome",))
    good_trial = trial(payload=PAYLOAD_A, outcome_raw=OUTCOME_A, position=1)
    forged_trial = replace(good_trial)
    with pytest.raises(GwtSemanticContentCausalityError, match="factory origin"):
        bind_semantic_content_crossover(trials=(forged_trial,
            trial(payload=PAYLOAD_B, outcome_raw=OUTCOME_B, position=2),
            trial(payload=PAYLOAD_B, outcome_raw=OUTCOME_B, position=3),
            trial(payload=PAYLOAD_A, outcome_raw=OUTCOME_A, position=4)),
            provenance_refs=("prov:g9:forged-trial",))
