import dataclasses
import unittest

from frankenstein2.adaptive_compute import (
    AdaptiveComputeError,
    AdaptiveComputePolicy,
    AllocationRule,
    CellWorkCap,
    build_allocation_candidate,
)
from frankenstein2.cognitive_envelope import (
    CognitiveEnvelopePolicy,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
    DISPOSITION_WITHIN,
    EnvelopeBand,
    SignalReadout,
    evaluate_control_snapshot,
)
from frankenstein2.grid10_interface import CellBudget, GRID10_CELL_IDS, Grid10Plan

HASH_A = "a" * 64


def envelope_policy(
    *,
    policy_id="envelope-policy-1",
    generation=3,
    variant="standard",
):
    evidence_ref = (
        "policy:envelope"
        if variant == "standard"
        else f"policy:envelope:{variant}"
    )
    band = EnvelopeBand.create(
        signal_id="load",
        expected_generation=5,
        hard_min=0,
        soft_min=10,
        soft_max=20,
        hard_max=30,
        required=True,
        evidence_refs=("band:load",),
    )
    return CognitiveEnvelopePolicy.create(
        policy_id=policy_id,
        generation=generation,
        bands=(band,),
        evidence_refs=(evidence_ref,),
    )


def make_plan(*, cell_work=5, total=20):
    policy = envelope_policy()
    cells = tuple(
        CellBudget(
            cell_id=cell,
            role_label=f"role-{cell}",
            max_input_refs=3,
            max_output_refs=2,
            max_work_units=cell_work,
            max_reentry_depth=1,
        )
        for cell in GRID10_CELL_IDS
    )
    return Grid10Plan.create(
        plan_id="plan-1",
        cycle_id="cycle-1",
        generation=2,
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=HASH_A,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        cells=cells,
        max_total_work_units=total,
        provenance_refs=("receipt:grid",),
    )


def snapshot(
    disposition=DISPOSITION_WITHIN,
    *,
    policy_id="envelope-policy-1",
    policy_generation=3,
    policy_variant="standard",
):
    policy = envelope_policy(
        policy_id=policy_id,
        generation=policy_generation,
        variant=policy_variant,
    )
    if disposition == DISPOSITION_UNKNOWN:
        readouts = ()
    else:
        values = {
            DISPOSITION_WITHIN: 15,
            DISPOSITION_DEGRADED: 25,
            DISPOSITION_HARD_LIMIT: 31,
        }
        if disposition not in values:
            raise AssertionError(f"unsupported test disposition {disposition!r}")
        readouts = (
            SignalReadout.create(
                signal_id="load",
                generation=5,
                value=values[disposition],
                evidence_refs=("readout:load",),
                provenance_refs=("source:test",),
            ),
        )
    result = evaluate_control_snapshot(policy, readouts)
    if result.disposition != disposition:
        raise AssertionError(
            f"test fixture expected disposition {disposition!r}, got {result.disposition!r}"
        )
    return result


def caps(value=5):
    return tuple(CellWorkCap(cell, value) for cell in GRID10_CELL_IDS)


def rule(disposition, active, total, *, priority=GRID10_CELL_IDS, cap=5):
    return AllocationRule.create(
        disposition=disposition,
        max_active_cells=active,
        max_total_work_units=total,
        cell_priority=priority,
        cell_work_caps=caps(cap),
    )


def make_policy(
    *,
    within=(10, 20),
    degraded=(5, 10),
    hard=(2, 4),
    unknown=(1, 2),
    priority=GRID10_CELL_IDS,
    cap=5,
):
    return AdaptiveComputePolicy.create(
        policy_id="adaptive-policy-1",
        generation=7,
        rules=(
            rule(DISPOSITION_WITHIN, *within, priority=priority, cap=cap),
            rule(DISPOSITION_DEGRADED, *degraded, priority=priority, cap=cap),
            rule(DISPOSITION_HARD_LIMIT, *hard, priority=priority, cap=cap),
            rule(DISPOSITION_UNKNOWN, *unknown, priority=priority, cap=cap),
        ),
        provenance_refs=("policy:receipt",),
    )


class AdaptiveComputeTests(unittest.TestCase):
    def test_policy_requires_exact_four_dispositions(self):
        with self.assertRaises(AdaptiveComputeError):
            AdaptiveComputePolicy.create(
                policy_id="p",
                generation=1,
                rules=(rule(DISPOSITION_WITHIN, 1, 1),) * 4,
                provenance_refs=("r",),
            )

    def test_rule_priority_requires_exact_g1_g10(self):
        with self.assertRaises(AdaptiveComputeError):
            rule(DISPOSITION_WITHIN, 2, 2, priority=GRID10_CELL_IDS[:-1])

    def test_unknown_and_hard_must_not_exceed_degraded(self):
        with self.assertRaisesRegex(
            AdaptiveComputeError, "HARD_LIMIT_BREACH max_active_cells"
        ):
            make_policy(degraded=(2, 10), hard=(3, 4))
        with self.assertRaisesRegex(
            AdaptiveComputeError, "UNKNOWN_REQUIRED_EVIDENCE max_total_work_units"
        ):
            make_policy(degraded=(5, 3), hard=(2, 3), unknown=(1, 4))

    def test_exact_plan_snapshot_policy_binding(self):
        plan = make_plan()
        policy = make_policy()
        with self.assertRaisesRegex(AdaptiveComputeError, "policy_id mismatch"):
            build_allocation_candidate(
                plan,
                snapshot(policy_id="other"),
                policy,
            )
        with self.assertRaisesRegex(AdaptiveComputeError, "generation mismatch"):
            build_allocation_candidate(
                plan,
                snapshot(policy_generation=4),
                policy,
            )
        with self.assertRaisesRegex(AdaptiveComputeError, "digest mismatch"):
            build_allocation_candidate(
                plan,
                snapshot(policy_variant="different-evidence"),
                policy,
            )

    def test_disposition_selects_only_explicit_rule(self):
        plan = make_plan()
        policy = make_policy(
            within=(4, 20), degraded=(2, 10), hard=(1, 3), unknown=(0, 0)
        )
        within = build_allocation_candidate(plan, snapshot(DISPOSITION_WITHIN), policy)
        degraded = build_allocation_candidate(
            plan, snapshot(DISPOSITION_DEGRADED), policy
        )
        hard = build_allocation_candidate(
            plan, snapshot(DISPOSITION_HARD_LIMIT), policy
        )
        unknown = build_allocation_candidate(
            plan, snapshot(DISPOSITION_UNKNOWN), policy
        )
        self.assertEqual(len(within.enabled_cells), 4)
        self.assertEqual(len(degraded.enabled_cells), 2)
        self.assertEqual(len(hard.enabled_cells), 1)
        self.assertEqual(len(unknown.enabled_cells), 0)

    def test_priority_is_caller_supplied_and_deterministic(self):
        priority = tuple(reversed(GRID10_CELL_IDS))
        candidate = build_allocation_candidate(
            make_plan(),
            snapshot(),
            make_policy(within=(2, 10), priority=priority),
        )
        self.assertEqual(
            tuple(cell.cell_id for cell in candidate.enabled_cells), ("G10", "G9")
        )
        self.assertEqual(candidate.deferred_cell_ids, GRID10_CELL_IDS[:-2])

    def test_allocation_clips_to_plan_cell_budget(self):
        candidate = build_allocation_candidate(
            make_plan(cell_work=2), snapshot(), make_policy(within=(1, 20), cap=5)
        )
        self.assertEqual(candidate.enabled_cells[0].work_units_ceiling, 2)
        self.assertEqual(candidate.enabled_cells[0].plan_cell_ceiling, 2)
        self.assertEqual(candidate.enabled_cells[0].allocation_policy_ceiling, 5)

    def test_allocation_clips_to_policy_cell_cap(self):
        candidate = build_allocation_candidate(
            make_plan(cell_work=9), snapshot(), make_policy(within=(1, 20), cap=3)
        )
        self.assertEqual(candidate.enabled_cells[0].work_units_ceiling, 3)

    def test_global_budget_is_never_exceeded(self):
        candidate = build_allocation_candidate(
            make_plan(cell_work=5, total=7),
            snapshot(),
            make_policy(within=(10, 20), cap=5),
        )
        self.assertEqual(candidate.total_work_units_ceiling, 7)
        self.assertEqual(
            [cell.work_units_ceiling for cell in candidate.enabled_cells], [5, 2]
        )

    def test_zero_caps_defer_without_minting_work(self):
        candidate = build_allocation_candidate(
            make_plan(), snapshot(), make_policy(within=(10, 20), cap=0)
        )
        self.assertEqual(candidate.enabled_cells, ())
        self.assertEqual(candidate.deferred_cell_ids, GRID10_CELL_IDS)
        self.assertEqual(candidate.total_work_units_ceiling, 0)

    def test_candidate_binds_exact_input_digests(self):
        plan = make_plan()
        snap = snapshot()
        policy = make_policy()
        candidate = build_allocation_candidate(plan, snap, policy)
        self.assertEqual(candidate.grid_plan_sha256, plan.sha256())
        self.assertEqual(candidate.control_snapshot_sha256, snap.sha256())
        self.assertEqual(candidate.adaptive_policy_sha256, policy.sha256())

    def test_policy_is_order_canonicalized_but_priority_semantics_preserved(self):
        p1 = make_policy()
        p2 = AdaptiveComputePolicy.create(
            policy_id="adaptive-policy-1",
            generation=7,
            rules=tuple(reversed(p1.rules)),
            provenance_refs=("policy:receipt",),
        )
        self.assertEqual(p1.as_dict(), p2.as_dict())
        self.assertEqual(p1.sha256(), p2.sha256())

    def test_candidate_is_immutable_and_non_authoritative(self):
        candidate = build_allocation_candidate(
            make_plan(), snapshot(), make_policy()
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.total_work_units_ceiling = 999
        self.assertIn("NOT_GRID_WRITER", candidate.classification)
        self.assertIn("PHYSICAL_CONCURRENCY", candidate.classification)
        self.assertIn("EFFECT_COMPLETION_AUTHORITY", candidate.classification)


if __name__ == "__main__":
    unittest.main()
