from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeObservation,
    GwtRuntimeObservationWindow,
    GwtRuntimeWitnessError,
    create_runtime_witness_from_observations,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)


def _fixture(suffix: str):
    payload_ref = f"payload:wp900-g2:{suffix}"
    plan = Grid10Plan.create(
        plan_id=f"grid-plan-wp900-{suffix}",
        cycle_id=f"cycle-wp900-{suffix}",
        generation=1,
        frame_id=f"frame-wp900-{suffix}",
        frame_generation=1,
        frame_sha256="a" * 64,
        policy_id=f"grid-policy-wp900-{suffix}",
        policy_generation=1,
        policy_sha256="b" * 64,
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
        provenance_refs=(f"test:wp900-plan:{suffix}",),
    )
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=(payload_ref,),
        provenance_refs=(f"test:wp900-producer-input:{suffix}",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=(payload_ref,),
        evidence_refs=(payload_ref,),
        provenance_refs=(f"test:wp900-producer-output:{suffix}",),
    )
    candidate = WorkspaceCandidate(
        candidate_id=f"candidate:wp900:{suffix}",
        payload_ref=payload_ref,
        epistemic_class="INFERRED",
        provenance_refs=(f"test:wp900-candidate:{suffix}",),
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
        policy_id=f"gwt-policy-wp900-{suffix}",
        generation=1,
        max_selected_candidates=1,
        max_total_cost_units=4,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    selection = build_workspace_selection(
        selection_id=f"selection:wp900:{suffix}",
        cycle_id=plan.cycle_id,
        generation=1,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )
    broadcast = create_broadcast(
        broadcast_id=f"broadcast:wp900:{suffix}",
        generation=1,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    reentry_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(payload_ref,),
        provenance_refs=(f"test:wp900-reentry-input:{suffix}",),
    )
    reentry_witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=reentry_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id=f"uptake:wp900:{suffix}",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=payload_ref,
        downstream_sha256="c" * 64,
        provenance_refs=(f"test:wp900-uptake:{suffix}",),
    )
    binding = bind_reentry_to_uptake(
        binding_id=f"binding:wp900:{suffix}",
        witness=reentry_witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=reentry_input,
        provenance_refs=(f"test:wp900-binding:{suffix}",),
    )
    return {
        "plan": plan,
        "selection": selection,
        "broadcast": broadcast,
        "cell_input": reentry_input,
        "reentry_witness": reentry_witness,
        "uptake": uptake,
        "binding": binding,
    }


def _capture(window: GwtRuntimeObservationWindow, fixture: dict):
    window.observe_delivery(
        broadcast=fixture["broadcast"],
        uptake_receipt=fixture["uptake"],
        provenance_refs=("test:delivery",),
    )
    window.observe_uptake(
        broadcast=fixture["broadcast"],
        uptake_receipt=fixture["uptake"],
        provenance_refs=("test:uptake",),
    )
    window.observe_reentry(
        binding=fixture["binding"],
        witness=fixture["reentry_witness"],
        uptake_receipt=fixture["uptake"],
        plan=fixture["plan"],
        selection=fixture["selection"],
        broadcast=fixture["broadcast"],
        cell_input=fixture["cell_input"],
        provenance_refs=("test:reentry",),
    )


class WP900GwtRuntimeWitnessTests(unittest.TestCase):
    def test_exact_delivery_uptake_reentry_window_binds_zero_credit_witness(self) -> None:
        fixture = _fixture("exact")
        window = GwtRuntimeObservationWindow.open(
            window_id="window:wp900:exact",
            source_sha256="d" * 64,
        )
        with patch(
            "frankenstein2.gwt_runtime_witness.time.monotonic_ns",
            side_effect=(100, 200, 300),
        ):
            _capture(window, fixture)
        witness = window.finalize(provenance_refs=("test:wp900-final",))
        data = witness.as_dict()
        self.assertTrue(data["process_observation_bound"])
        self.assertEqual(data["delivery_receipt_id"], fixture["uptake"].receipt_id)
        self.assertEqual(data["uptake_receipt_id"], fixture["uptake"].receipt_id)
        self.assertEqual(data["reentry_binding_id"], fixture["binding"].binding_id)
        self.assertEqual(data["target_environment_component_runtime_credit"], 0)
        self.assertEqual(data["gwt_runtime_credit"], 0)
        self.assertEqual(data["jspace_runtime_credit"], 0)
        self.assertEqual(data["effect_credit"], 0)
        self.assertEqual(data["completion_credit"], 0)
        self.assertFalse(data["whole_system_acceptance"])

    def test_direct_instantiated_observations_are_not_runtime_authority(self) -> None:
        fake = GwtRuntimeObservation(
            stage="DELIVERY",
            ordinal=0,
            process_id="gwt-process:fake",
            window_id="window:fake",
            source_sha256="d" * 64,
            observed_monotonic_ns=100,
            broadcast_id="broadcast:fake",
            broadcast_sha256="e" * 64,
            recipient_cell_id="G1",
            evidence_ref="receipt:fake",
            evidence_sha256="f" * 64,
            provenance_refs=("test:fake",),
        )
        with self.assertRaisesRegex(GwtRuntimeWitnessError, "factory|process"):
            create_runtime_witness_from_observations(
                (fake, fake, fake),
                provenance_refs=("test:fake-final",),
            )

    def test_seal_preserving_observation_mutation_fails_digest_fence(self) -> None:
        fixture = _fixture("tamper")
        window = GwtRuntimeObservationWindow.open(
            window_id="window:wp900:tamper",
            source_sha256="d" * 64,
        )
        with patch(
            "frankenstein2.gwt_runtime_witness.time.monotonic_ns",
            side_effect=(100, 200, 300),
        ):
            _capture(window, fixture)
        values = list(window.observations)
        values[1] = replace(values[1], evidence_sha256="0" * 64)
        with self.assertRaisesRegex(GwtRuntimeWitnessError, "changed after capture"):
            create_runtime_witness_from_observations(
                values,
                provenance_refs=("test:tamper-final",),
            )

    def test_cross_process_identity_is_rejected_even_with_preserved_factory_fields(self) -> None:
        fixture = _fixture("process")
        window = GwtRuntimeObservationWindow.open(
            window_id="window:wp900:process",
            source_sha256="d" * 64,
        )
        with patch(
            "frankenstein2.gwt_runtime_witness.time.monotonic_ns",
            side_effect=(100, 200, 300),
        ):
            _capture(window, fixture)
        values = list(window.observations)
        values[1] = replace(values[1], process_id="gwt-process:foreign")
        with self.assertRaisesRegex(GwtRuntimeWitnessError, "cross-process|changed"):
            create_runtime_witness_from_observations(
                values,
                provenance_refs=("test:cross-process-final",),
            )

    def test_reordered_observations_fail_closed(self) -> None:
        fixture = _fixture("reordered")
        window = GwtRuntimeObservationWindow.open(
            window_id="window:wp900:reordered",
            source_sha256="d" * 64,
        )
        with patch(
            "frankenstein2.gwt_runtime_witness.time.monotonic_ns",
            side_effect=(100, 200, 300),
        ):
            _capture(window, fixture)
        values = window.observations
        with self.assertRaisesRegex(GwtRuntimeWitnessError, "reordered"):
            create_runtime_witness_from_observations(
                (values[1], values[0], values[2]),
                provenance_refs=("test:reordered-final",),
            )

    def test_cross_broadcast_observation_window_fails_at_finalize(self) -> None:
        first = _fixture("broadcast-a")
        second = _fixture("broadcast-b")
        window = GwtRuntimeObservationWindow.open(
            window_id="window:wp900:cross-broadcast",
            source_sha256="d" * 64,
        )
        with patch(
            "frankenstein2.gwt_runtime_witness.time.monotonic_ns",
            side_effect=(100, 200, 300),
        ):
            window.observe_delivery(
                broadcast=first["broadcast"],
                uptake_receipt=first["uptake"],
                provenance_refs=("test:a-delivery",),
            )
            window.observe_uptake(
                broadcast=first["broadcast"],
                uptake_receipt=first["uptake"],
                provenance_refs=("test:a-uptake",),
            )
            window.observe_reentry(
                binding=second["binding"],
                witness=second["reentry_witness"],
                uptake_receipt=second["uptake"],
                plan=second["plan"],
                selection=second["selection"],
                broadcast=second["broadcast"],
                cell_input=second["cell_input"],
                provenance_refs=("test:b-reentry",),
            )
        with self.assertRaisesRegex(GwtRuntimeWitnessError, "broadcast"):
            window.finalize(provenance_refs=("test:cross-broadcast-final",))

    def test_direct_or_replaced_gwt_binding_cannot_mint_reentry_observation(self) -> None:
        fixture = _fixture("binding-tamper")
        window = GwtRuntimeObservationWindow.open(
            window_id="window:wp900:binding-tamper",
            source_sha256="d" * 64,
        )
        with patch(
            "frankenstein2.gwt_runtime_witness.time.monotonic_ns",
            side_effect=(100, 200),
        ):
            window.observe_delivery(
                broadcast=fixture["broadcast"],
                uptake_receipt=fixture["uptake"],
                provenance_refs=("test:delivery",),
            )
            window.observe_uptake(
                broadcast=fixture["broadcast"],
                uptake_receipt=fixture["uptake"],
                provenance_refs=("test:uptake",),
            )
        tampered = replace(fixture["binding"], broadcast_sha256="0" * 64)
        with self.assertRaisesRegex(GwtRuntimeWitnessError, "re-entry binding validation failed"):
            window.observe_reentry(
                binding=tampered,
                witness=fixture["reentry_witness"],
                uptake_receipt=fixture["uptake"],
                plan=fixture["plan"],
                selection=fixture["selection"],
                broadcast=fixture["broadcast"],
                cell_input=fixture["cell_input"],
                provenance_refs=("test:tampered-reentry",),
            )


if __name__ == "__main__":
    unittest.main()
