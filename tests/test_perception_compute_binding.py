import unittest

from src.frankenstein2.adaptive_compute import (
    AdaptiveComputePolicy,
    AllocationRule,
    CellWorkCap,
    build_allocation_candidate,
)
from src.frankenstein2.cognitive_envelope import (
    CognitiveEnvelopePolicy,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
    DISPOSITION_WITHIN,
    EnvelopeBand,
    SignalReadout,
    evaluate_control_snapshot,
)
from src.frankenstein2.grid10_interface import CellBudget, GRID10_CELL_IDS, Grid10Plan
from src.frankenstein2.perception_compute_binding import (
    PerceptionComputeBindingError,
    PerceptionComputeBindingPolicy,
    PerceptionEnvelopeRule,
    derive_perception_worker_policy,
)


HASH_A = "a" * 64
P = ("test:perception-compute-binding",)


def envelope_policy():
    band = EnvelopeBand.create(
        signal_id="load",
        expected_generation=1,
        hard_min=0,
        soft_min=10,
        soft_max=20,
        hard_max=30,
        required=True,
        evidence_refs=P,
    )
    return CognitiveEnvelopePolicy.create(
        policy_id="envelope:perception-test",
        generation=1,
        bands=(band,),
        evidence_refs=P,
    )


def snapshot(disposition):
    policy = envelope_policy()
    if disposition == DISPOSITION_UNKNOWN:
        readouts = ()
    else:
        value = {
            DISPOSITION_WITHIN: 15,
            DISPOSITION_DEGRADED: 25,
            DISPOSITION_HARD_LIMIT: 31,
        }[disposition]
        readouts = (
            SignalReadout.create(
                signal_id="load",
                generation=1,
                value=value,
                evidence_refs=P,
                provenance_refs=P,
            ),
        )
    result = evaluate_control_snapshot(policy, readouts)
    assert result.disposition == disposition
    return result


def plan():
    env = envelope_policy()
    cells = tuple(
        CellBudget(
            cell_id=cell,
            role_label=f"role:{cell}",
            max_input_refs=2,
            max_output_refs=2,
            max_work_units=10,
            max_reentry_depth=1,
        )
        for cell in GRID10_CELL_IDS
    )
    return Grid10Plan.create(
        plan_id="grid-plan:perception-test",
        cycle_id="cycle:1",
        generation=1,
        frame_id="frame:1",
        frame_generation=1,
        frame_sha256=HASH_A,
        policy_id=env.policy_id,
        policy_generation=env.generation,
        policy_sha256=env.sha256(),
        cells=cells,
        max_total_work_units=100,
        provenance_refs=P,
    )


def adaptive_policy():
    def caps(value):
        return tuple(CellWorkCap(cell, value) for cell in GRID10_CELL_IDS)

    def rule(disposition, active, total, cap):
        return AllocationRule.create(
            disposition=disposition,
            max_active_cells=active,
            max_total_work_units=total,
            cell_priority=GRID10_CELL_IDS,
            cell_work_caps=caps(cap),
        )

    return AdaptiveComputePolicy.create(
        policy_id="adaptive:perception-test",
        generation=1,
        rules=(
            rule(DISPOSITION_WITHIN, 10, 100, 10),
            rule(DISPOSITION_DEGRADED, 5, 50, 10),
            rule(DISPOSITION_HARD_LIMIT, 2, 20, 10),
            rule(DISPOSITION_UNKNOWN, 1, 10, 10),
        ),
        provenance_refs=P,
    )


def binding_policy():
    return PerceptionComputeBindingPolicy(
        policy_id="perception-share:test",
        generation=1,
        rules=(
            PerceptionEnvelopeRule(
                disposition=DISPOSITION_WITHIN,
                max_active_workers=4,
                max_perception_work_units=40,
                max_share_micros=400_000,
            ),
            PerceptionEnvelopeRule(
                disposition=DISPOSITION_DEGRADED,
                max_active_workers=2,
                max_perception_work_units=10,
                max_share_micros=200_000,
            ),
            PerceptionEnvelopeRule(
                disposition=DISPOSITION_HARD_LIMIT,
                max_active_workers=1,
                max_perception_work_units=2,
                max_share_micros=100_000,
            ),
            PerceptionEnvelopeRule(
                disposition=DISPOSITION_UNKNOWN,
                max_active_workers=0,
                max_perception_work_units=0,
                max_share_micros=0,
            ),
        ),
        provenance_refs=P,
    )


class PerceptionComputeBindingTests(unittest.TestCase):
    def test_within_envelope_can_allow_four_workers_but_only_bounded_share(self):
        snap = snapshot(DISPOSITION_WITHIN)
        allocation = build_allocation_candidate(plan(), snap, adaptive_policy())
        result = derive_perception_worker_policy(
            control_snapshot=snap,
            adaptive_allocation=allocation,
            binding_policy=binding_policy(),
        )
        self.assertEqual(result.max_active_workers, 4)
        self.assertEqual(result.max_total_work_units, 40)

    def test_degraded_shrinks_workers_and_work(self):
        snap = snapshot(DISPOSITION_DEGRADED)
        allocation = build_allocation_candidate(plan(), snap, adaptive_policy())
        result = derive_perception_worker_policy(
            control_snapshot=snap,
            adaptive_allocation=allocation,
            binding_policy=binding_policy(),
        )
        self.assertEqual(result.max_active_workers, 2)
        self.assertEqual(result.max_total_work_units, 10)

    def test_hard_limit_shrinks_perception_before_it_can_starve_cognition(self):
        snap = snapshot(DISPOSITION_HARD_LIMIT)
        allocation = build_allocation_candidate(plan(), snap, adaptive_policy())
        result = derive_perception_worker_policy(
            control_snapshot=snap,
            adaptive_allocation=allocation,
            binding_policy=binding_policy(),
        )
        self.assertEqual(result.max_active_workers, 1)
        self.assertEqual(result.max_total_work_units, 2)

    def test_unknown_required_evidence_fails_to_zero_perception_workers(self):
        snap = snapshot(DISPOSITION_UNKNOWN)
        allocation = build_allocation_candidate(plan(), snap, adaptive_policy())
        result = derive_perception_worker_policy(
            control_snapshot=snap,
            adaptive_allocation=allocation,
            binding_policy=binding_policy(),
        )
        self.assertEqual(result.max_active_workers, 0)
        self.assertEqual(result.max_total_work_units, 0)

    def test_exact_control_snapshot_binding_is_required(self):
        within = snapshot(DISPOSITION_WITHIN)
        degraded = snapshot(DISPOSITION_DEGRADED)
        allocation = build_allocation_candidate(plan(), within, adaptive_policy())
        with self.assertRaisesRegex(PerceptionComputeBindingError, "exact ControlSnapshot"):
            derive_perception_worker_policy(
                control_snapshot=degraded,
                adaptive_allocation=allocation,
                binding_policy=binding_policy(),
            )

    def test_hard_and_unknown_rules_cannot_exceed_degraded(self):
        with self.assertRaises(PerceptionComputeBindingError):
            PerceptionComputeBindingPolicy(
                policy_id="bad",
                generation=1,
                rules=(
                    PerceptionEnvelopeRule(disposition=DISPOSITION_WITHIN, max_active_workers=4, max_perception_work_units=40, max_share_micros=400_000),
                    PerceptionEnvelopeRule(disposition=DISPOSITION_DEGRADED, max_active_workers=1, max_perception_work_units=5, max_share_micros=100_000),
                    PerceptionEnvelopeRule(disposition=DISPOSITION_HARD_LIMIT, max_active_workers=2, max_perception_work_units=5, max_share_micros=100_000),
                    PerceptionEnvelopeRule(disposition=DISPOSITION_UNKNOWN, max_active_workers=0, max_perception_work_units=0, max_share_micros=0),
                ),
                provenance_refs=P,
            )


if __name__ == "__main__":
    unittest.main()
