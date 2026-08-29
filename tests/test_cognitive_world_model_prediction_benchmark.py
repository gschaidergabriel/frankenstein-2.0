from __future__ import annotations

import hashlib
import unittest

from frankenstein2.cognitive_microworld import (
    ACTION_REQUEST_SCHEMA,
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    OBSERVATION_SCHEMA,
    ActionRequest,
    ActionSpec,
    CognitiveMicroWorldError,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    TransitionRule,
    WorldNode,
    begin_episode,
    step_episode,
)
from frankenstein2.cognitive_world_model_prediction_benchmark import (
    ABSTAIN,
    ABSTAINED,
    CORRECT,
    INCORRECT,
    POLICY_CONFIG_SCHEMA,
    PERSISTENCE,
    PREDICTED,
    PUBLIC_MEMORY,
    UNKNOWN,
    PolicyConfig,
    PublicTransitionMemory,
    PublicTransitionMemoryEntry,
    WorldModelPredictionError,
    bind_prediction_to_run,
    evaluate_prediction_after_step,
    learn_public_transition,
    predict_next_public_observation,
)


def h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fixture(*, generation: int = 1, hidden_suffix: str = "one", score: int = 1) -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture:wp803",
        generation,
        "holdout:wp803",
        "node:a",
        1,
        (ActionSpec("go", "action:go", h("action:go")),),
        (
            WorldNode(
                "node:a",
                "obs:a",
                h("public:a"),
                f"hidden:a:{hidden_suffix}",
                h(f"hidden:a:{hidden_suffix}"),
                False,
                0,
            ),
            WorldNode(
                "node:b",
                "obs:b",
                h("public:b"),
                f"hidden:b:{hidden_suffix}",
                h(f"hidden:b:{hidden_suffix}"),
                True,
                score,
            ),
        ),
        (TransitionRule("node:a", "go", "node:b", f"transition:{hidden_suffix}", h(f"transition:{hidden_suffix}")),),
        "evidence:wp803",
        ("source:wp800",),
        "donor:wp800",
        "method:heldout-world-model-prediction",
    )


def run_for(world: MicroWorldFixture, *, run_id: str, condition: str, sut: str) -> RunDescriptor:
    return RunDescriptor.for_fixture(
        world,
        run_id=run_id,
        condition=condition,
        episode_family_id="episode-family:wp803",
        system_under_test_ref=sut,
        communication_before_result=False,
        independent_reproduction=False,
    )


class ObservationSubtype(ObservationView):
    pass


class WorldModelPredictionBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = fixture()
        self.state, self.obs = begin_episode(self.world, episode_id="episode:1", episode_generation=1)
        self.request = ActionRequest.for_observation(self.obs, action_id="go")
        self.next_state, self.next_obs, self.evaluator_step = step_episode(
            self.world,
            state=self.state,
            request=self.request,
        )
        self.empty = PublicTransitionMemory.empty()
        self.memory_cfg = PolicyConfig(POLICY_CONFIG_SCHEMA, "policy:memory", 1, PUBLIC_MEMORY)
        self.persist_cfg = PolicyConfig(POLICY_CONFIG_SCHEMA, "policy:persistence", 1, PERSISTENCE)
        self.abstain_cfg = PolicyConfig(POLICY_CONFIG_SCHEMA, "policy:abstain", 1, ABSTAIN)

    def test_public_memory_preserves_unknown_when_evidence_is_insufficient(self) -> None:
        prediction = predict_next_public_observation(
            self.obs,
            action_id="go",
            config=self.memory_cfg,
            memory=self.empty,
        )
        self.assertEqual(prediction.status, UNKNOWN)
        self.assertIsNone(prediction.predicted_observation_ref)
        self.assertIsNone(prediction.predicted_observation_sha256)

    def test_explicit_abstain_baseline_never_fabricates_next_observation(self) -> None:
        prediction = predict_next_public_observation(
            self.obs,
            action_id="go",
            config=self.abstain_cfg,
            memory=self.empty,
        )
        self.assertEqual(prediction.status, UNKNOWN)
        run = run_for(self.world, run_id="run:abstain", condition=BASELINE, sut="sut:abstain")
        bound = bind_prediction_to_run(prediction, run=run, fixture=self.world)
        score = evaluate_prediction_after_step(
            bound,
            run=run,
            fixture=self.world,
            prior_observation=self.obs,
            request=self.request,
            next_state=self.next_state,
            next_observation=self.next_obs,
            evaluator_step=self.evaluator_step,
        )
        self.assertEqual((score.result, score.points), (ABSTAINED, 0))

    def test_persistence_is_an_explicit_public_information_baseline(self) -> None:
        prediction = predict_next_public_observation(
            self.obs,
            action_id="go",
            config=self.persist_cfg,
            memory=self.empty,
        )
        self.assertEqual(prediction.status, PREDICTED)
        self.assertEqual(prediction.predicted_observation_ref, self.obs.observation_ref)
        run = run_for(self.world, run_id="run:persistence", condition=BASELINE, sut="sut:persistence")
        score = evaluate_prediction_after_step(
            bind_prediction_to_run(prediction, run=run, fixture=self.world),
            run=run,
            fixture=self.world,
            prior_observation=self.obs,
            request=self.request,
            next_state=self.next_state,
            next_observation=self.next_obs,
            evaluator_step=self.evaluator_step,
        )
        self.assertEqual((score.result, score.points), (INCORRECT, 0))

    def test_public_transition_can_be_learned_only_from_attested_wp800_step_and_replayed(self) -> None:
        learned = learn_public_transition(
            self.empty,
            prior_observation=self.obs,
            request=self.request,
            next_state=self.next_state,
            next_observation=self.next_obs,
            evaluator_step=self.evaluator_step,
        )
        state2, obs2 = begin_episode(self.world, episode_id="episode:2", episode_generation=1)
        request2 = ActionRequest.for_observation(obs2, action_id="go")
        prediction = predict_next_public_observation(
            obs2,
            action_id="go",
            config=self.memory_cfg,
            memory=learned,
        )
        self.assertEqual(prediction.status, PREDICTED)
        self.assertEqual(
            (prediction.predicted_observation_ref, prediction.predicted_observation_sha256),
            (self.next_obs.observation_ref, self.next_obs.observation_sha256),
        )
        next_state2, next_obs2, step2 = step_episode(self.world, state=state2, request=request2)
        run = run_for(self.world, run_id="run:memory", condition=INTERVENTION, sut="sut:public-memory")
        score = evaluate_prediction_after_step(
            bind_prediction_to_run(prediction, run=run, fixture=self.world),
            run=run,
            fixture=self.world,
            prior_observation=obs2,
            request=request2,
            next_state=next_state2,
            next_observation=next_obs2,
            evaluator_step=step2,
        )
        self.assertEqual((score.result, score.points), (CORRECT, 1))

    def test_hidden_fixture_changes_do_not_change_raw_policy_output_when_public_view_is_identical(self) -> None:
        learned = learn_public_transition(
            self.empty,
            prior_observation=self.obs,
            request=self.request,
            next_state=self.next_state,
            next_observation=self.next_obs,
            evaluator_step=self.evaluator_step,
        )
        hidden_variant = fixture(hidden_suffix="two", score=99)
        _, variant_obs = begin_episode(hidden_variant, episode_id="episode:1", episode_generation=1)
        self.assertNotEqual(self.world.sha256(), hidden_variant.sha256())
        self.assertEqual(self.world.public_sha256(), hidden_variant.public_sha256())
        self.assertEqual(self.obs, variant_obs)
        p1 = predict_next_public_observation(self.obs, action_id="go", config=self.memory_cfg, memory=learned)
        p2 = predict_next_public_observation(variant_obs, action_id="go", config=self.memory_cfg, memory=learned)
        self.assertEqual(p1, p2)
        self.assertEqual(p1.sha256(), p2.sha256())

    def test_policy_boundary_rejects_hidden_fixture_object(self) -> None:
        with self.assertRaises(WorldModelPredictionError):
            predict_next_public_observation(  # type: ignore[arg-type]
                self.world,
                action_id="go",
                config=self.memory_cfg,
                memory=self.empty,
            )

    def test_policy_boundary_rejects_observation_subtype(self) -> None:
        subtype = ObservationSubtype(
            OBSERVATION_SCHEMA,
            self.obs.episode_id,
            self.obs.episode_generation,
            self.obs.fixture_id,
            self.obs.fixture_generation,
            self.obs.public_fixture_sha256,
            self.obs.step_index,
            self.obs.observation_ref,
            self.obs.observation_sha256,
            self.obs.available_action_ids,
            self.obs.terminal,
            self.obs.classification,
        )
        with self.assertRaises(WorldModelPredictionError):
            predict_next_public_observation(subtype, action_id="go", config=self.memory_cfg, memory=self.empty)

    def test_generation_change_invalidates_prediction_run_binding(self) -> None:
        prediction = predict_next_public_observation(
            self.obs,
            action_id="go",
            config=self.persist_cfg,
            memory=self.empty,
        )
        generation2 = fixture(generation=2)
        run2 = run_for(generation2, run_id="run:g2", condition=BASELINE, sut="sut:persistence")
        with self.assertRaises(WorldModelPredictionError):
            bind_prediction_to_run(prediction, run=run2, fixture=generation2)

    def test_run_binding_rejects_self_attested_or_wrong_fixture_provenance(self) -> None:
        prediction = predict_next_public_observation(self.obs, action_id="go", config=self.persist_cfg, memory=self.empty)
        run = run_for(self.world, run_id="run:wrong-fixture", condition=BASELINE, sut="sut:persistence")
        hidden_variant = fixture(hidden_suffix="other")
        with self.assertRaises(WorldModelPredictionError):
            bind_prediction_to_run(prediction, run=run, fixture=hidden_variant)

    def test_score_rejects_tampered_action_request(self) -> None:
        prediction = predict_next_public_observation(self.obs, action_id="go", config=self.persist_cfg, memory=self.empty)
        run = run_for(self.world, run_id="run:tamper", condition=BASELINE, sut="sut:persistence")
        bound = bind_prediction_to_run(prediction, run=run, fixture=self.world)
        tampered = ActionRequest(
            ACTION_REQUEST_SCHEMA,
            self.request.episode_id,
            self.request.episode_generation,
            self.request.fixture_id,
            self.request.fixture_generation,
            self.request.public_fixture_sha256,
            self.request.step_index,
            h("wrong-observation"),
            self.request.action_id,
        )
        with self.assertRaises(WorldModelPredictionError):
            evaluate_prediction_after_step(
                bound,
                run=run,
                fixture=self.world,
                prior_observation=self.obs,
                request=tampered,
                next_state=self.next_state,
                next_observation=self.next_obs,
                evaluator_step=self.evaluator_step,
            )

    def test_score_rejects_non_advanced_transition_values(self) -> None:
        prediction = predict_next_public_observation(self.obs, action_id="go", config=self.persist_cfg, memory=self.empty)
        run = run_for(self.world, run_id="run:prestep", condition=BASELINE, sut="sut:persistence")
        bound = bind_prediction_to_run(prediction, run=run, fixture=self.world)
        with self.assertRaises(WorldModelPredictionError):
            evaluate_prediction_after_step(
                bound,
                run=run,
                fixture=self.world,
                prior_observation=self.obs,
                request=self.request,
                next_state=self.state,
                next_observation=self.obs,
                evaluator_step=self.evaluator_step,
            )

    def test_conflicting_public_memory_fails_closed_instead_of_overwriting(self) -> None:
        conflicting = PublicTransitionMemoryEntry(
            self.obs.fixture_id,
            self.obs.fixture_generation,
            self.obs.public_fixture_sha256,
            self.obs.observation_ref,
            self.obs.observation_sha256,
            "go",
            "obs:conflict",
            h("public:conflict"),
        )
        memory = PublicTransitionMemory("FRANKENSTEIN2_WORLD_MODEL_PUBLIC_MEMORY/v1", 1, (conflicting,))
        with self.assertRaises(WorldModelPredictionError):
            learn_public_transition(
                memory,
                prior_observation=self.obs,
                request=self.request,
                next_state=self.next_state,
                next_observation=self.next_obs,
                evaluator_step=self.evaluator_step,
            )

    def test_raw_prediction_surface_contains_no_evaluator_hidden_fields(self) -> None:
        prediction = predict_next_public_observation(self.obs, action_id="go", config=self.persist_cfg, memory=self.empty)
        encoded = repr(prediction.as_dict()).lower()
        for forbidden in ("hidden_ground_truth", "transition_ref", "transition_sha256", "evaluator_score", "current_node_id", "score_delta"):
            self.assertNotIn(forbidden, encoded)

    def test_same_public_inputs_are_deterministic(self) -> None:
        p1 = predict_next_public_observation(self.obs, action_id="go", config=self.persist_cfg, memory=self.empty)
        p2 = predict_next_public_observation(self.obs, action_id="go", config=self.persist_cfg, memory=self.empty)
        self.assertEqual(p1, p2)
        self.assertEqual(p1.sha256(), p2.sha256())

    def test_wp800_manual_evaluator_state_fabrication_remains_rejected(self) -> None:
        # WP803 relies on WP800's evaluator-origin fence rather than minting a second state authority.
        from frankenstein2.cognitive_microworld import EPISODE_STATE_SCHEMA, EpisodeState

        with self.assertRaises(CognitiveMicroWorldError):
            EpisodeState(
                EPISODE_STATE_SCHEMA,
                "episode:forged",
                1,
                self.world.fixture_id,
                self.world.generation,
                self.world.sha256(),
                "node:b",
                1,
                999,
            )


if __name__ == "__main__":
    unittest.main()
