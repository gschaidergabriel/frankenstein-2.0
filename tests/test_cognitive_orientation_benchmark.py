from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionSpec,
    MicroWorldFixture,
    TransitionRule,
    WorldNode,
)
from frankenstein2.cognitive_orientation_benchmark import (
    BOUNDED_PUBLIC_EXPLORATION,
    MEMORYLESS_CANONICAL_FIRST,
    OrientationBenchmarkError,
    OrientationPolicy,
    compare_orientation_runs,
    run_orientation_policy,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def ambiguous_orientation_fixture(*, max_steps: int = 4) -> MicroWorldFixture:
    """Two evaluator states look identical publicly; action history is useful, hidden node ID is not exposed."""

    return MicroWorldFixture(
        schema=FIXTURE_SCHEMA,
        fixture_id="heldout.orientation.ambiguous-junction.001",
        generation=1,
        holdout_set_id="orientation-heldout.v1",
        initial_node_id="hidden-junction-a",
        max_steps=max_steps,
        actions=(
            ActionSpec("a-left", "action:left", h("left")),
            ActionSpec("b-right", "action:right", h("right")),
        ),
        nodes=(
            WorldNode(
                "hidden-goal",
                "obs:goal",
                h("goal"),
                "ground-truth:goal",
                h("gt-goal"),
                True,
                10,
            ),
            WorldNode(
                "hidden-junction-a",
                "obs:ambiguous-junction",
                h("ambiguous-junction"),
                "ground-truth:junction-a",
                h("gt-a"),
                False,
                0,
            ),
            WorldNode(
                "hidden-junction-b",
                "obs:ambiguous-junction",
                h("ambiguous-junction"),
                "ground-truth:junction-b",
                h("gt-b"),
                False,
                0,
            ),
        ),
        transitions=(
            TransitionRule(
                "hidden-junction-a",
                "a-left",
                "hidden-junction-b",
                "transition:a:left",
                h("a-left"),
            ),
            TransitionRule(
                "hidden-junction-a",
                "b-right",
                "hidden-goal",
                "transition:a:right",
                h("a-right"),
            ),
            TransitionRule(
                "hidden-junction-b",
                "a-left",
                "hidden-junction-a",
                "transition:b:left",
                h("b-left"),
            ),
            TransitionRule(
                "hidden-junction-b",
                "b-right",
                "hidden-goal",
                "transition:b:right",
                h("b-right"),
            ),
        ),
        evidence_source_family="synthetic-heldout",
        primary_source_ids=("wp801-ambiguous-orientation-fixture-v1",),
        donor_path_family="none-synthetic",
        method_family="heldout-orientation-policy-discriminator",
    )


def run_pair():
    f = ambiguous_orientation_fixture()
    baseline = run_orientation_policy(
        f,
        policy=OrientationPolicy.memoryless(),
        run_id="orientation-baseline-run",
        condition=BASELINE,
        episode_family_id="orientation-family-001",
        episode_id="orientation-episode-001",
        episode_generation=0,
        system_under_test_ref="builtin-memoryless-public-baseline-v1",
        independent_reproduction=True,
    )
    intervention = run_orientation_policy(
        f,
        policy=OrientationPolicy.bounded_exploration(max_public_history_entries=4),
        run_id="orientation-exploration-run",
        condition=INTERVENTION,
        episode_family_id="orientation-family-001",
        episode_id="orientation-episode-001",
        episode_generation=0,
        system_under_test_ref="builtin-bounded-public-exploration-v1",
        independent_reproduction=True,
    )
    return f, baseline, intervention


class OrientationBenchmarkTests(unittest.TestCase):
    def test_memoryless_baseline_exhausts_on_publicly_ambiguous_loop(self) -> None:
        _, baseline, _ = run_pair()
        self.assertFalse(baseline.terminal_reached)
        self.assertTrue(baseline.step_budget_exhausted)
        self.assertEqual(baseline.evaluator_score, 0)
        self.assertEqual(baseline.steps_used, 4)
        self.assertEqual({entry.action_id for entry in baseline.public_trace}, {"a-left"})

    def test_bounded_public_exploration_reaches_goal_without_hidden_state(self) -> None:
        _, _, exploration = run_pair()
        self.assertTrue(exploration.terminal_reached)
        self.assertFalse(exploration.step_budget_exhausted)
        self.assertEqual(exploration.evaluator_score, 10)
        self.assertEqual(exploration.steps_used, 2)
        self.assertEqual(
            [entry.action_id for entry in exploration.public_trace],
            ["a-left", "b-right"],
        )

    def test_public_trace_contains_no_evaluator_node_score_or_ground_truth(self) -> None:
        _, baseline, intervention = run_pair()
        forbidden = {
            "current_node_id",
            "from_node_id",
            "to_node_id",
            "evaluator_score",
            "hidden_ground_truth_ref",
            "hidden_ground_truth_sha256",
            "fixture_sha256",
            "transition_ref",
        }
        for result in (baseline, intervention):
            for entry in result.public_trace:
                self.assertTrue(forbidden.isdisjoint(entry.as_dict()))
                self.assertEqual(entry.observation_ref, "obs:ambiguous-junction")

    def test_comparison_is_matched_and_descriptive_not_superiority_credit(self) -> None:
        f, baseline, intervention = run_pair()
        comparison = compare_orientation_runs(
            f,
            baseline=baseline,
            intervention=intervention,
        )
        self.assertEqual(comparison.evaluator_score_delta, 10)
        self.assertEqual(comparison.steps_used_delta, -2)
        self.assertEqual(comparison.terminal_delta, "INTERVENTION_ONLY")
        self.assertIn("NOT_CAUSAL_OR_WHOLE_SYSTEM_CREDIT", comparison.classification)
        self.assertEqual(
            comparison.matched_pair.baseline.fixture_sha256,
            comparison.matched_pair.intervention.fixture_sha256,
        )

    def test_hidden_fixture_change_breaks_matched_comparison(self) -> None:
        f, baseline, intervention = run_pair()
        nodes = list(f.nodes)
        nodes[0] = replace(nodes[0], hidden_ground_truth_sha256=h("changed-hidden-goal"))
        changed = replace(f, nodes=tuple(nodes))
        with self.assertRaisesRegex(Exception, "exact fixture|fixture/provenance|does not match"):
            compare_orientation_runs(changed, baseline=baseline, intervention=intervention)

    def test_result_reconstruction_loses_runner_origin(self) -> None:
        _, baseline, _ = run_pair()
        with self.assertRaisesRegex(OrientationBenchmarkError, "must be created by run_orientation_policy"):
            replace(baseline, evaluator_score=999)

    def test_policy_modes_and_history_bounds_fail_closed(self) -> None:
        with self.assertRaisesRegex(OrientationBenchmarkError, "mode must be one of"):
            OrientationPolicy(
                schema="FRANKENSTEIN2_ORIENTATION_POLICY/v1",
                policy_id="bad",
                mode="USES_HIDDEN_GROUND_TRUTH",
                max_public_history_entries=1,
            )
        with self.assertRaisesRegex(OrientationBenchmarkError, "integer in \[1"):
            OrientationPolicy.bounded_exploration(max_public_history_entries=0)

    def test_conditions_are_explicit_and_not_inferred_from_policy_name(self) -> None:
        f = ambiguous_orientation_fixture()
        result = run_orientation_policy(
            f,
            policy=OrientationPolicy.bounded_exploration(),
            run_id="explicit-baseline-condition",
            condition=BASELINE,
            episode_family_id="family",
            episode_id="episode",
            episode_generation=0,
            system_under_test_ref="bounded-exploration-used-as-baseline",
        )
        self.assertEqual(result.run_descriptor.condition, BASELINE)
        self.assertEqual(result.policy_id, "baseline.bounded-public-exploration.v1")

    def test_comparison_rejects_different_episode_identity(self) -> None:
        f, baseline, _ = run_pair()
        other = run_orientation_policy(
            f,
            policy=OrientationPolicy.bounded_exploration(),
            run_id="other",
            condition=INTERVENTION,
            episode_family_id="orientation-family-001",
            episode_id="different-episode",
            episode_generation=0,
            system_under_test_ref="builtin-bounded-public-exploration-v1",
        )
        with self.assertRaisesRegex(OrientationBenchmarkError, "same episode identity"):
            compare_orientation_runs(f, baseline=baseline, intervention=other)

    def test_fixture_is_hidden_from_policy_selector_signature_by_contract(self) -> None:
        import inspect
        from frankenstein2 import cognitive_orientation_benchmark as module

        parameters = tuple(inspect.signature(module._select_public_action).parameters)
        self.assertEqual(parameters, ("policy", "observation", "public_history"))
        self.assertNotIn("fixture", parameters)
        self.assertNotIn("state", parameters)

    def test_baseline_and_intervention_use_same_full_hidden_fixture_digest(self) -> None:
        f, baseline, intervention = run_pair()
        self.assertEqual(baseline.run_descriptor.fixture_sha256, f.sha256())
        self.assertEqual(intervention.run_descriptor.fixture_sha256, f.sha256())
        self.assertEqual(
            baseline.run_descriptor.primary_source_ids,
            intervention.run_descriptor.primary_source_ids,
        )


if __name__ == "__main__":
    unittest.main()
