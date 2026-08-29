from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.cognitive_lesion_rescue_benchmark import (
    CAPABILITY_SCHEMA,
    LESION,
    NORMAL,
    RESCUE,
    REDUNDANCY_OR_INTERACTION_UNKNOWN,
    TARGET_SPECIFIC_RESTORATION_AT_SCOPE,
    CognitiveCondition,
    CognitiveLesionRescueError,
    PublicCapability,
    choose_action_public,
    run_condition,
    run_matched_lesion_rescue,
)
from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionSpec,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    TransitionRule,
    WorldNode,
    begin_episode,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        schema=FIXTURE_SCHEMA,
        fixture_id="heldout.lesion-rescue.001",
        generation=3,
        holdout_set_id="lesion-rescue.v1",
        initial_node_id="evaluator-node-a",
        max_steps=1,
        actions=(
            ActionSpec("left", "action:left", h("left")),
            ActionSpec("right", "action:right", h("right")),
        ),
        nodes=(
            WorldNode(
                "evaluator-node-a",
                "obs:fork",
                h("fork"),
                "ground-truth:start",
                h("gt-start"),
                False,
                0,
            ),
            WorldNode(
                "evaluator-node-b",
                "obs:failure",
                h("failure"),
                "ground-truth:trap",
                h("gt-trap"),
                True,
                -1,
            ),
            WorldNode(
                "evaluator-node-c",
                "obs:success",
                h("success"),
                "ground-truth:goal",
                h("gt-goal"),
                True,
                10,
            ),
        ),
        transitions=(
            TransitionRule(
                "evaluator-node-a",
                "left",
                "evaluator-node-b",
                "transition:a:left",
                h("a-left"),
            ),
            TransitionRule(
                "evaluator-node-a",
                "right",
                "evaluator-node-c",
                "transition:a:right",
                h("a-right"),
            ),
        ),
        evidence_source_family="synthetic-heldout",
        primary_source_ids=("wp806-fixture-design-v1",),
        donor_path_family="wp800-cognitive-microworld",
        method_family="matched-cognitive-lesion-rescue",
    )


def capabilities() -> tuple[PublicCapability, ...]:
    return (
        PublicCapability(CAPABILITY_SCHEMA, "cap.goal-path", "right", 0),
        PublicCapability(CAPABILITY_SCHEMA, "cap.fallback", "left", 1),
    )


def runs(f: MicroWorldFixture) -> tuple[RunDescriptor, RunDescriptor, RunDescriptor]:
    common = dict(
        fixture=f,
        episode_family_id="family.wp806.001",
        communication_before_result=False,
        independent_reproduction=False,
    )
    normal = RunDescriptor.for_fixture(
        **common,
        run_id="run.wp806.normal",
        condition=BASELINE,
        system_under_test_ref="wp806-public-policy-normal",
    )
    lesion = RunDescriptor.for_fixture(
        **common,
        run_id="run.wp806.lesion",
        condition=INTERVENTION,
        system_under_test_ref="wp806-public-policy-lesion",
    )
    rescue = RunDescriptor.for_fixture(
        **common,
        run_id="run.wp806.rescue",
        condition=INTERVENTION,
        system_under_test_ref="wp806-public-policy-rescue",
    )
    return normal, lesion, rescue


def conditions(f: MicroWorldFixture) -> tuple[CognitiveCondition, CognitiveCondition, CognitiveCondition]:
    _, obs = begin_episode(f, episode_id="condition-seed", episode_generation=5)
    normal = CognitiveCondition.for_observation(obs, condition_kind=NORMAL)
    lesion = CognitiveCondition.for_observation(
        obs,
        condition_kind=LESION,
        disabled_capability_ids=("cap.goal-path",),
    )
    rescue = CognitiveCondition.for_observation(
        obs,
        condition_kind=RESCUE,
        disabled_capability_ids=("cap.goal-path",),
        rescued_capability_ids=("cap.goal-path",),
    )
    return normal, lesion, rescue


class CognitiveLesionRescueTests(unittest.TestCase):
    def test_matched_lesion_degrades_and_rescue_restores_public_capability(self) -> None:
        f = fixture()
        normal_run, lesion_run, rescue_run = runs(f)
        normal, lesion, rescue = conditions(f)
        result = run_matched_lesion_rescue(
            f,
            normal_run=normal_run,
            lesion_run=lesion_run,
            rescue_run=rescue_run,
            normal_condition=normal,
            lesion_condition=lesion,
            rescue_condition=rescue,
            capabilities=capabilities(),
            episode_generation=9,
        )
        self.assertEqual(result.normal.final_score, 10)
        self.assertEqual(result.lesion.final_score, -1)
        self.assertEqual(result.rescue.final_score, 10)
        self.assertEqual(result.lesion_delta, -11)
        self.assertEqual(result.rescue_delta, 11)
        self.assertEqual(result.restoration_gap, 0)
        self.assertEqual(result.interpretation, TARGET_SPECIFIC_RESTORATION_AT_SCOPE)
        self.assertTrue(result.normal.terminal)
        self.assertTrue(result.lesion.terminal)
        self.assertTrue(result.rescue.terminal)
        self.assertFalse(result.normal.abstained)
        self.assertEqual(result.normal.step_count, 1)

    def test_policy_boundary_uses_only_public_observation_and_public_config(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        normal, _, _ = conditions(f)
        action = choose_action_public(obs, capabilities=capabilities(), condition=normal)
        self.assertEqual(action, "right")
        public_blob = {
            "observation": obs.as_dict(),
            "condition": normal.as_dict(),
            "capabilities": [c.as_dict() for c in capabilities()],
        }
        rendered = repr(public_blob)
        self.assertNotIn("current_node_id", rendered)
        self.assertNotIn("'fixture_sha256':", rendered)
        self.assertNotIn("evaluator_score", rendered)
        self.assertNotIn("hidden_ground_truth", rendered)
        self.assertNotIn("transition_ref", rendered)
        self.assertIn("public_fixture_sha256", rendered)

    def test_exact_concrete_observation_and_capability_types_are_required(self) -> None:
        class EvilObservation(ObservationView):
            pass

        class EvilCapability(PublicCapability):
            pass

        f = fixture()
        _, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        normal, _, _ = conditions(f)
        evil_obs = EvilObservation(**obs.as_dict())
        with self.assertRaisesRegex(CognitiveLesionRescueError, "exact concrete ObservationView"):
            choose_action_public(evil_obs, capabilities=capabilities(), condition=normal)

        evil_cap = EvilCapability(CAPABILITY_SCHEMA, "cap.goal-path", "right", 0)
        caps = (evil_cap, PublicCapability(CAPABILITY_SCHEMA, "cap.fallback", "left", 1))
        with self.assertRaisesRegex(CognitiveLesionRescueError, "exact concrete PublicCapability"):
            choose_action_public(obs, capabilities=caps, condition=normal)

    def test_condition_requires_builder_and_exact_public_fixture_identity(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        built, _, _ = conditions(f)
        forged = CognitiveCondition(
            built.schema,
            built.condition_id,
            built.condition_kind,
            built.fixture_id,
            built.fixture_generation,
            built.public_fixture_sha256,
            built.disabled_capability_ids,
            built.rescued_capability_ids,
        )
        with self.assertRaisesRegex(CognitiveLesionRescueError, "must originate"):
            choose_action_public(obs, capabilities=capabilities(), condition=forged)

        f2 = replace(f, generation=f.generation + 1)
        _, obs2 = begin_episode(f2, episode_id="ep2", episode_generation=0)
        with self.assertRaisesRegex(CognitiveLesionRescueError, "exact public fixture identity"):
            choose_action_public(obs2, capabilities=capabilities(), condition=built)

    def test_rescue_must_be_subset_of_explicit_lesion(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        with self.assertRaisesRegex(CognitiveLesionRescueError, "subset"):
            CognitiveCondition.for_observation(
                obs,
                condition_kind=RESCUE,
                disabled_capability_ids=("cap.goal-path",),
                rescued_capability_ids=("cap.fallback",),
            )

    def test_posthoc_condition_relabel_is_rejected(self) -> None:
        f = fixture()
        _, lesion, _ = conditions(f)
        with self.assertRaises(CognitiveLesionRescueError):
            replace(lesion, condition_kind=RESCUE)

    def test_unknown_capability_in_lesion_fails_closed(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        lesion = CognitiveCondition.for_observation(
            obs,
            condition_kind=LESION,
            disabled_capability_ids=("cap.unknown",),
        )
        with self.assertRaisesRegex(CognitiveLesionRescueError, "unknown public capability"):
            choose_action_public(obs, capabilities=capabilities(), condition=lesion)

    def test_total_lesion_abstains_instead_of_forcing_an_action(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="seed", episode_generation=0)
        total_lesion = CognitiveCondition.for_observation(
            obs,
            condition_kind=LESION,
            disabled_capability_ids=("cap.fallback", "cap.goal-path"),
        )
        _, lesion_run, _ = runs(f)
        result = run_condition(
            f,
            run=lesion_run,
            condition=total_lesion,
            capabilities=capabilities(),
            episode_id="family.wp806.total-lesion",
            episode_generation=2,
        )
        self.assertTrue(result.abstained)
        self.assertFalse(result.terminal)
        self.assertEqual(result.step_count, 0)
        self.assertEqual(result.final_score, 0)
        self.assertEqual(len(result.observation_sha256s), 1)
        self.assertEqual(result.action_request_sha256s, ())
        self.assertEqual(result.evaluator_step_sha256s, ())

    def test_hidden_fixture_mutation_breaks_full_run_binding_despite_same_public_digest(self) -> None:
        f1 = fixture()
        normal_run, _, _ = runs(f1)
        normal, _, _ = conditions(f1)
        nodes = list(f1.nodes)
        nodes[0] = replace(nodes[0], hidden_ground_truth_ref="ground-truth:changed")
        f2 = replace(f1, nodes=tuple(nodes))
        self.assertEqual(f1.public_sha256(), f2.public_sha256())
        self.assertNotEqual(f1.sha256(), f2.sha256())
        with self.assertRaisesRegex(
            CognitiveLesionRescueError,
            "does not match exact fixture/provenance binding",
        ):
            run_condition(
                f2,
                run=normal_run,
                condition=normal,
                capabilities=capabilities(),
                episode_id="ep",
                episode_generation=0,
            )

    def test_matched_runs_reject_different_episode_family(self) -> None:
        f = fixture()
        normal_run, lesion_run, _ = runs(f)
        rescue_run = RunDescriptor.for_fixture(
            f,
            run_id="run.wp806.rescue.other",
            condition=INTERVENTION,
            episode_family_id="different-family",
            system_under_test_ref="wp806-public-policy-rescue",
            communication_before_result=False,
            independent_reproduction=False,
        )
        normal, lesion, rescue = conditions(f)
        with self.assertRaisesRegex(CognitiveLesionRescueError, "episode_family_id"):
            run_matched_lesion_rescue(
                f,
                normal_run=normal_run,
                lesion_run=lesion_run,
                rescue_run=rescue_run,
                normal_condition=normal,
                lesion_condition=lesion,
                rescue_condition=rescue,
                capabilities=capabilities(),
                episode_generation=0,
            )

    def test_comparison_is_deterministic_at_exact_identity(self) -> None:
        f = fixture()
        r = runs(f)
        c = conditions(f)
        first = run_matched_lesion_rescue(
            f,
            normal_run=r[0],
            lesion_run=r[1],
            rescue_run=r[2],
            normal_condition=c[0],
            lesion_condition=c[1],
            rescue_condition=c[2],
            capabilities=capabilities(),
            episode_generation=7,
        )
        second = run_matched_lesion_rescue(
            f,
            normal_run=r[0],
            lesion_run=r[1],
            rescue_run=r[2],
            normal_condition=c[0],
            lesion_condition=c[1],
            rescue_condition=c[2],
            capabilities=capabilities(),
            episode_generation=7,
        )
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.comparison_id, second.comparison_id)

    def test_rescue_must_match_exact_lesion_disabled_universe_before_evaluation(self) -> None:
        f = fixture()
        r = runs(f)
        normal, lesion, _ = conditions(f)
        _, obs = begin_episode(f, episode_id="mismatch-seed", episode_generation=5)
        mismatched_rescue = CognitiveCondition.for_observation(
            obs,
            condition_kind=RESCUE,
            disabled_capability_ids=("cap.fallback", "cap.goal-path"),
            rescued_capability_ids=("cap.goal-path",),
        )
        with self.assertRaisesRegex(CognitiveLesionRescueError, "same disabled capability universe"):
            run_matched_lesion_rescue(
                f,
                normal_run=r[0],
                lesion_run=r[1],
                rescue_run=r[2],
                normal_condition=normal,
                lesion_condition=lesion,
                rescue_condition=mismatched_rescue,
                capabilities=capabilities(),
                episode_generation=7,
            )

    def test_metric_and_operator_identity_change_sealed_comparison_identity(self) -> None:
        f = fixture()
        r = runs(f)
        c = conditions(f)
        baseline = run_matched_lesion_rescue(
            f,
            normal_run=r[0], lesion_run=r[1], rescue_run=r[2],
            normal_condition=c[0], lesion_condition=c[1], rescue_condition=c[2],
            capabilities=capabilities(), episode_generation=7,
        )
        changed_metric = run_matched_lesion_rescue(
            f,
            normal_run=r[0], lesion_run=r[1], rescue_run=r[2],
            normal_condition=c[0], lesion_condition=c[1], rescue_condition=c[2],
            capabilities=capabilities(), episode_generation=7,
            score_metric_version="2",
        )
        changed_operator = run_matched_lesion_rescue(
            f,
            normal_run=r[0], lesion_run=r[1], rescue_run=r[2],
            normal_condition=c[0], lesion_condition=c[1], rescue_condition=c[2],
            capabilities=capabilities(), episode_generation=7,
            rescue_operator_id="public-capability-restore-subset/v2",
        )
        self.assertEqual(baseline.normal.sha256(), changed_metric.normal.sha256())
        self.assertEqual(baseline.lesion.sha256(), changed_metric.lesion.sha256())
        self.assertEqual(baseline.rescue.sha256(), changed_metric.rescue.sha256())
        self.assertNotEqual(baseline.comparison_id, changed_metric.comparison_id)
        self.assertNotEqual(baseline.comparison_id, changed_operator.comparison_id)
        self.assertNotEqual(baseline.sha256(), changed_metric.sha256())

    def test_condition_results_are_order_independent_from_fresh_episode_boundaries(self) -> None:
        f = fixture()
        r = runs(f)
        c = conditions(f)
        jobs = {
            "normal": (r[0], c[0], "family.wp806.001:normal"),
            "lesion": (r[1], c[1], "family.wp806.001:lesion"),
            "rescue": (r[2], c[2], "family.wp806.001:rescue"),
        }

        def execute(order: tuple[str, ...]) -> dict[str, str]:
            out: dict[str, str] = {}
            for name in order:
                run, condition, episode_id = jobs[name]
                out[name] = run_condition(
                    f,
                    run=run,
                    condition=condition,
                    capabilities=capabilities(),
                    episode_id=episode_id,
                    episode_generation=11,
                ).sha256()
            return out

        first = execute(("normal", "lesion", "rescue"))
        second = execute(("rescue", "normal", "lesion"))
        self.assertEqual(first, second)

    def test_zero_lesion_effect_stays_redundancy_or_interaction_unknown(self) -> None:
        f = fixture()
        r = runs(f)
        _, obs = begin_episode(f, episode_id="semantic-seed", episode_generation=5)
        normal = CognitiveCondition.for_observation(obs, condition_kind=NORMAL)
        lesion = CognitiveCondition.for_observation(
            obs,
            condition_kind=LESION,
            disabled_capability_ids=("cap.fallback",),
        )
        rescue = CognitiveCondition.for_observation(
            obs,
            condition_kind=RESCUE,
            disabled_capability_ids=("cap.fallback",),
            rescued_capability_ids=("cap.fallback",),
        )
        result = run_matched_lesion_rescue(
            f,
            normal_run=r[0], lesion_run=r[1], rescue_run=r[2],
            normal_condition=normal, lesion_condition=lesion, rescue_condition=rescue,
            capabilities=capabilities(), episode_generation=12,
        )
        self.assertEqual(result.lesion_delta, 0)
        self.assertEqual(result.interpretation, REDUNDANCY_OR_INTERACTION_UNKNOWN)
        self.assertNotIn("IRRELEVANT", result.as_dict().values())

    def test_semantic_identifiers_are_strict_trimmed_identity_inputs(self) -> None:
        f = fixture()
        r = runs(f)
        c = conditions(f)
        with self.assertRaisesRegex(CognitiveLesionRescueError, "score_metric_id"):
            run_matched_lesion_rescue(
                f,
                normal_run=r[0], lesion_run=r[1], rescue_run=r[2],
                normal_condition=c[0], lesion_condition=c[1], rescue_condition=c[2],
                capabilities=capabilities(), episode_generation=1,
                score_metric_id=" metric-with-whitespace ",
            )


if __name__ == "__main__":
    unittest.main()
