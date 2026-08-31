from dataclasses import replace
import hashlib
import json

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import (
    assert_reentry_uptake_binding_factory_origin,
    bind_reentry_to_uptake,
)
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessError,
    GwtRuntimeWitnessRecorder,
    LIVE_GWT_PATH_OBSERVED,
    RuntimeObservationIdentity,
    UPTAKE_NOT_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def canonical_digest(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp900-g2",
        cycle_id="cycle-wp900-g2",
        generation=4,
        frame_id="frame-wp900-g2",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp900-g2",
        policy_generation=1,
        policy_sha256=B,
        cells=tuple(
            CellBudget(
                cell_id=f"G{i}",
                role_label=f"role-{i}",
                max_input_refs=8,
                max_output_refs=8,
                max_work_units=8,
                max_reentry_depth=2,
            )
            for i in range(1, 11)
        ),
        max_total_work_units=80,
        provenance_refs=("prov:grid-plan-wp900-g2",),
    )


def make_selection(plan):
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:producer",),
        provenance_refs=("prov:producer-input",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp900-g2",
        payload_ref="payload:candidate",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=100_000,
        information_gain_micros=500_000,
        estimated_cost_units=1,
        producer_admission=CandidateProducerAdmission(
            plan=plan,
            cell_input=producer_input,
            cell_output=producer_output,
        ),
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy-wp900-g2",
        generation=1,
        max_selected_candidates=1,
        max_total_cost_units=4,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    return build_workspace_selection(
        selection_id="selection:wp900-g2",
        cycle_id=plan.cycle_id,
        generation=8,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )


def make_fixture(*, delivery="DELIVERED", uptake="UPTAKEN"):
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp900-g2",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1", "G2"),
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:candidate",),
        provenance_refs=("prov:reentry-input",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:wp900-g2:G1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status=delivery,
        uptake_status=uptake,
        downstream_ref="downstream:observed" if uptake == "UPTAKEN" else None,
        downstream_sha256=C if uptake == "UPTAKEN" else None,
        provenance_refs=("prov:wp507-receipt",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp900-g2",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp900-g2-binding",),
    )
    return plan, selection, broadcast, cell_input, witness, receipt, binding


def identity():
    return RuntimeObservationIdentity(
        runtime_instance_id="runtime:wp900-g2:test",
        process_identity="pid:4242:start:100",
        boot_id_sha256=D,
        exact_source_sha256=A,
    )


def clock(*values):
    sequence = iter(values)
    return lambda: next(sequence)


def record_all(*, delivery="DELIVERED", uptake="UPTAKEN"):
    plan, selection, broadcast, cell_input, witness, receipt, binding = make_fixture(
        delivery=delivery,
        uptake=uptake,
    )
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20, 30))
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(receipt)
    recorder.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    return recorder, (plan, selection, broadcast, cell_input, witness, receipt, binding)


def test_positive_path_binds_delivery_uptake_and_reentry_but_mints_zero_credit():
    recorder, fixture = record_all()
    _, _, broadcast, _, witness, receipt, binding = fixture
    observed = recorder.seal()
    validate_gwt_runtime_witness_receipt(observed)

    payload = observed.as_dict()
    assert observed.classification == LIVE_GWT_PATH_OBSERVED
    assert observed.broadcast_id == broadcast.broadcast_id
    assert observed.broadcast_sha256 == broadcast.sha256()
    assert observed.uptake_receipt_id == receipt.receipt_id
    assert observed.uptake_receipt_sha256 == receipt.sha256()
    assert observed.canonical_reentry_key == witness.canonical_reentry_key()
    assert observed.reentry_witness_sha256 == witness.sha256()
    assert observed.binding_id == binding.binding_id
    assert observed.binding_sha256 == binding.sha256()
    assert [event["phase"] for event in payload["events"]] == ["DELIVERY", "UPTAKE", "REENTRY"]
    assert payload["runtime_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["effect_credit"] == 0
    assert payload["completion_credit"] == 0
    assert payload["training_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_delivery_must_precede_uptake():
    _, _, broadcast, _, _, receipt, _ = make_fixture()
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20))
    with pytest.raises(GwtRuntimeWitnessError, match="delivery must be observed before uptake"):
        recorder.observe_uptake(receipt)
    recorder.observe_delivery(broadcast)


def test_seal_requires_all_three_runtime_observations():
    _, _, broadcast, _, _, receipt, _ = make_fixture()
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20))
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(receipt)
    with pytest.raises(GwtRuntimeWitnessError, match="delivery, uptake and re-entry"):
        recorder.seal()


def test_non_uptake_is_preserved_as_negative_evidence_not_positive_runtime_claim():
    recorder, _ = record_all(delivery="DELIVERED", uptake="NOT_UPTAKEN")
    observed = recorder.seal()
    assert observed.classification == UPTAKE_NOT_OBSERVED
    assert observed.delivery_status == "DELIVERED"
    assert observed.uptake_status == "NOT_UPTAKEN"
    assert observed.gwt_runtime_credit == 0


def test_cross_broadcast_uptake_fails_closed():
    plan, selection, broadcast, _, _, _, _ = make_fixture()
    other = create_broadcast(
        broadcast_id="broadcast:wp900-g2:other",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    other_receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:other",
        broadcast=other,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:other",
        downstream_sha256=C,
        provenance_refs=("prov:other",),
    )
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20))
    recorder.observe_delivery(broadcast)
    with pytest.raises(GwtRuntimeWitnessError, match="invalid uptake observation"):
        recorder.observe_uptake(other_receipt)


def test_direct_constructed_wp507_receipt_cannot_cross_runtime_boundary():
    _, _, broadcast, _, _, receipt, _ = make_fixture()
    forged = replace(receipt, _factory_seal=None)
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20))
    recorder.observe_delivery(broadcast)
    with pytest.raises(GwtRuntimeWitnessError, match="observation factory"):
        recorder.observe_uptake(forged)


def test_direct_constructed_wp508_binding_cannot_cross_runtime_boundary():
    plan, selection, broadcast, cell_input, witness, receipt, binding = make_fixture()
    forged = replace(binding, _factory_seal=None)
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20, 30))
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(receipt)
    with pytest.raises(GwtRuntimeWitnessError, match="factory lineage"):
        recorder.observe_reentry(
            witness=witness,
            binding=forged,
            plan=plan,
            selection=selection,
            cell_input=cell_input,
        )


def test_adaptive_factory_metadata_replacement_is_rejected_by_deep_lineage_validator():
    plan, selection, broadcast, cell_input, witness, receipt, binding = make_fixture()
    forged_lineage = replace(binding, broadcast_sha256="e" * 64)
    forged = replace(
        forged_lineage,
        _factory_payload_sha256=canonical_digest(forged_lineage.as_dict()),
    )

    # GWTRW01 demonstrates that lightweight seal+digest metadata alone can be
    # adaptively copied.  The runtime boundary must therefore depend on the deep
    # WP508 source-evidence rebuild, not this lightweight check alone.
    assert_reentry_uptake_binding_factory_origin(forged)

    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(10, 20, 30))
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(receipt)
    with pytest.raises(GwtRuntimeWitnessError, match="source-evidence lineage mismatch"):
        recorder.observe_reentry(
            witness=witness,
            binding=forged,
            plan=plan,
            selection=selection,
            cell_input=cell_input,
        )


def test_non_monotonic_runtime_clock_is_rejected():
    _, _, broadcast, _, _, receipt, _ = make_fixture()
    recorder = GwtRuntimeWitnessRecorder(identity=identity(), monotonic_ns=clock(20, 20))
    recorder.observe_delivery(broadcast)
    with pytest.raises(GwtRuntimeWitnessError, match="clock did not advance"):
        recorder.observe_uptake(receipt)


def test_sealed_receipt_tamper_is_rejected():
    recorder, _ = record_all()
    observed = recorder.seal()
    forged = replace(observed, broadcast_sha256="f" * 64)
    with pytest.raises(GwtRuntimeWitnessError, match="payload changed after seal"):
        validate_gwt_runtime_witness_receipt(forged)


def test_recorder_cannot_be_reused_after_seal():
    recorder, fixture = record_all()
    _, _, broadcast, _, _, _, _ = fixture
    recorder.seal()
    with pytest.raises(GwtRuntimeWitnessError, match="delivery observation already recorded|already sealed"):
        recorder.observe_delivery(broadcast)
