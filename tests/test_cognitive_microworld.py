from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.cognitive_microworld import (
    ACTION_REQUEST_SCHEMA,
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionRequest,
    ActionSpec,
    CognitiveMicroWorldError,
    MatchedRunPair,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    TransitionRule,
    WorldNode,
    begin_episode,
    observation_for_state,
    step_episode,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture(*, max_steps: int = 3) -> MicroWorldFixture:
    return MicroWorldFixture(
        schema=FIXTURE_SCHEMA,
        fixture_id="heldout.maze.001",
        generation=1,
        holdout_set_id="orientation.v1",
        initial_node_id="evaluator-node-a",
        max_steps=max_steps,
        actions=(
            ActionSpec("left", "action:left", h("left")),
            ActionSpec("right", "action:right", h("right")),
        ),
        nodes=(
            WorldNode(
                "evaluator-node-a",
                "obs:same-looking-room",
                h("same-looking-room"),
                "ground-truth:start",
                h("gt-start"),
                False,
                0,
            ),
            WorldNode(
                "evaluator-node-b",
                "obs:same-looking-room",
                h("same-looking-room"),
                "ground-truth:trap",
                h("gt-trap"),
                True,
                -1,
            ),
            WorldNode(
                "evaluator-node-c",
                "obs:goal",
                h("goal"),
                "ground-truth:goal",
                h("gt-goal"),
                True,
                10,
            ),
        ),
        transitions=(
            TransitionRule(
                "evaluator-node-a", "left", "evaluator-node-b", "t:a:left", h("a-left")
            ),
            TransitionRule(
                "evaluator-node-a", "right", "evaluator-node-c", "t:a:right", h("a-right")
            ),
        ),
        evidence_source_family="synthetic-heldout",
        primary_source_ids=("wp800-fixture-design-v1",),
        donor_path_family="none-synthetic",
        method_family="deterministic-interactive-microworld",
    )


class CognitiveMicroWorldTests(unittest.TestCase):
    def test_public_observation_excludes_hidden_evaluator_fields(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-1", episode_generation=0)
        public = obs.as_dict()
        self.assertNotIn("current_node_id", public)
        self.assertNotIn("fixture_sha256", public)
        self.assertNotIn("cumulative_score", public)
        self.assertNotIn("hidden_ground_truth_ref", public)
        self.assertNotIn("evaluator_score", public)
        self.assertEqual(obs.observation_ref, "obs:same-looking-room")
        self.assertNotEqual(f.sha256(), f.public_sha256())
        self.assertEqual(state.current_node_id, "evaluator-node-a")

    def test_hidden_fixture_change_does_not_change_public_interface_digest(self) -> None:
        f1 = fixture()
        nodes = list(f1.nodes)
        nodes[0] = replace(nodes[0], hidden_ground_truth_ref="ground-truth:changed")
        f2 = replace(f1, nodes=tuple(nodes))
        self.assertNotEqual(f1.sha256(), f2.sha256())
        self.assertEqual(f1.public_sha256(), f2.public_sha256())

    def test_deterministic_episode_replay(self) -> None:
        f = fixture()
        s1, o1 = begin_episode(f, episode_id="ep", episode_generation=4)
        s2, o2 = begin_episode(f, episode_id="ep", episode_generation=4)
        self.assertEqual(s1.sha256(), s2.sha256())
        self.assertEqual(o1.sha256(), o2.sha256())
        req1 = ActionRequest.for_observation(o1, action_id="right")
        req2 = ActionRequest.for_observation(o2, action_id="right")
        n1, p1, e1 = step_episode(f, state=s1, request=req1)
        n2, p2, e2 = step_episode(f, state=s2, request=req2)
        self.assertEqual(n1.sha256(), n2.sha256())
        self.assertEqual(p1.sha256(), p2.sha256())
        self.assertEqual(e1.sha256(), e2.sha256())
        self.assertTrue(p1.terminal)
        self.assertEqual(n1.cumulative_score, 10)

    def test_stale_observation_request_rejected(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep", episode_generation=1)
        request = ActionRequest.for_observation(obs, action_id="right")
        forged = replace(request, observation_sha256=h("wrong"))
        with self.assertRaisesRegex(CognitiveMicroWorldError, "observation digest mismatch"):
            step_episode(f, state=state, request=forged)

    def test_unknown_or_unroutable_action_rejected(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        forged = ActionRequest(
            schema=ACTION_REQUEST_SCHEMA,
            episode_id=obs.episode_id,
            episode_generation=obs.episode_generation,
            fixture_id=obs.fixture_id,
            fixture_generation=obs.fixture_generation,
            public_fixture_sha256=obs.public_fixture_sha256,
            step_index=obs.step_index,
            observation_sha256=obs.sha256(),
            action_id="wait",
        )
        with self.assertRaisesRegex(CognitiveMicroWorldError, "unknown action_id"):
            step_episode(f, state=state, request=forged)

        f2 = replace(
            f,
            transitions=(
                TransitionRule(
                    "evaluator-node-a", "right", "evaluator-node-c", "t:a:right", h("a-right")
                ),
            ),
        )
        state2, obs2 = begin_episode(f2, episode_id="ep2", episode_generation=0)
        left = ActionRequest.for_observation(obs2, action_id="left")
        with self.assertRaisesRegex(CognitiveMicroWorldError, "no deterministic transition"):
            step_episode(f2, state=state2, request=left)

    def test_terminal_state_cannot_be_stepped(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        state, obs, _ = step_episode(
            f,
            state=state,
            request=ActionRequest.for_observation(obs, action_id="right"),
        )
        with self.assertRaisesRegex(CognitiveMicroWorldError, "terminal episode"):
            step_episode(
                f,
                state=state,
                request=ActionRequest.for_observation(obs, action_id="left"),
            )

    def test_step_ceiling_enforced_before_transition(self) -> None:
        f = fixture(max_steps=1)
        nodes = tuple(
            replace(node, terminal=False) if node.node_id == "evaluator-node-b" else node
            for node in f.nodes
        )
        transitions = (
            TransitionRule(
                "evaluator-node-a", "left", "evaluator-node-b", "t:a:left", h("a-left")
            ),
            TransitionRule(
                "evaluator-node-a", "right", "evaluator-node-c", "t:a:right", h("a-right")
            ),
            TransitionRule(
                "evaluator-node-b", "left", "evaluator-node-a", "t:b:left", h("b-left")
            ),
        )
        f = replace(f, nodes=nodes, transitions=transitions)
        state, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        state, obs, _ = step_episode(
            f,
            state=state,
            request=ActionRequest.for_observation(obs, action_id="left"),
        )
        with self.assertRaisesRegex(CognitiveMicroWorldError, "step ceiling"):
            step_episode(
                f,
                state=state,
                request=ActionRequest.for_observation(obs, action_id="left"),
            )

    def test_fixture_rejects_duplicate_or_dangling_transition(self) -> None:
        f = fixture()
        duplicate = f.transitions + (
            TransitionRule("evaluator-node-a", "left", "evaluator-node-c", "t:dup", h("dup")),
        )
        duplicate = tuple(sorted(duplicate, key=lambda item: (item.from_node_id, item.action_id)))
        with self.assertRaisesRegex(CognitiveMicroWorldError, "at most one deterministic transition"):
            replace(f, transitions=duplicate)
        dangling = (
            TransitionRule("evaluator-node-a", "left", "missing", "t:x", h("x")),
        )
        with self.assertRaisesRegex(CognitiveMicroWorldError, "unknown node"):
            replace(f, transitions=dangling)

    def test_exact_concrete_nested_types_are_trust_boundary(self) -> None:
        class EvilNode(WorldNode):
            pass

        f = fixture()
        evil = EvilNode(
            "evaluator-node-a",
            "obs:same-looking-room",
            h("same-looking-room"),
            "ground-truth:start",
            h("gt-start"),
            False,
            0,
        )
        nodes = (evil,) + f.nodes[1:]
        with self.assertRaisesRegex(CognitiveMicroWorldError, "exact concrete WorldNode"):
            replace(f, nodes=nodes)

        class EvilObservation(ObservationView):
            pass

        _, obs = begin_episode(f, episode_id="ep", episode_generation=0)
        evil_obs = EvilObservation(**obs.as_dict())
        with self.assertRaisesRegex(CognitiveMicroWorldError, "exact concrete ObservationView"):
            ActionRequest.for_observation(evil_obs, action_id="right")

    def test_evaluator_state_is_bound_to_full_hidden_fixture_digest(self) -> None:
        f1 = fixture()
        state, _ = begin_episode(f1, episode_id="ep", episode_generation=0)
        nodes = list(f1.nodes)
        nodes[0] = replace(nodes[0], hidden_ground_truth_sha256=h("changed-hidden"))
        f2 = replace(f1, nodes=tuple(nodes))
        with self.assertRaisesRegex(CognitiveMicroWorldError, "state fixture digest mismatch"):
            observation_for_state(f2, state)

    def test_matched_pair_requires_exact_fixture_and_evidence_ancestry(self) -> None:
        f = fixture()
        baseline = RunDescriptor.for_fixture(
            f,
            run_id="run-base",
            condition=BASELINE,
            episode_family_id="family-1",
            system_under_test_ref="simple-baseline-v1",
            communication_before_result=False,
            independent_reproduction=True,
        )
        intervention = RunDescriptor.for_fixture(
            f,
            run_id="run-grid",
            condition=INTERVENTION,
            episode_family_id="family-1",
            system_under_test_ref="grid10-candidate-v1",
            communication_before_result=False,
            independent_reproduction=True,
        )
        pair = MatchedRunPair.create(baseline=baseline, intervention=intervention)
        self.assertTrue(pair.pair_id.startswith("pair:"))
        self.assertNotIn("worker_count", baseline.as_dict())
        self.assertNotIn("evidence_count", baseline.as_dict())
        self.assertEqual(pair.baseline.primary_source_ids, pair.intervention.primary_source_ids)

        mismatched = replace(intervention, method_family="different-method-family")
        with self.assertRaisesRegex(CognitiveMicroWorldError, "differs on method_family"):
            MatchedRunPair.create(baseline=baseline, intervention=mismatched)

    def test_matched_pair_rejects_wrong_conditions_and_self_attested_pair_id(self) -> None:
        f = fixture()
        a = RunDescriptor.for_fixture(
            f,
            run_id="a",
            condition=BASELINE,
            episode_family_id="family",
            system_under_test_ref="sut-a",
            communication_before_result=False,
            independent_reproduction=False,
        )
        b = RunDescriptor.for_fixture(
            f,
            run_id="b",
            condition=INTERVENTION,
            episode_family_id="family",
            system_under_test_ref="sut-b",
            communication_before_result=False,
            independent_reproduction=False,
        )
        pair = MatchedRunPair.create(baseline=a, intervention=b)
        with self.assertRaisesRegex(CognitiveMicroWorldError, "pair_id does not bind"):
            replace(pair, pair_id="pair:forged")
        with self.assertRaisesRegex(CognitiveMicroWorldError, "BASELINE then INTERVENTION"):
            MatchedRunPair.create(baseline=replace(a, condition=INTERVENTION), intervention=b)

    def test_nonpositive_step_ceiling_and_noncanonical_sources_rejected(self) -> None:
        with self.assertRaisesRegex(CognitiveMicroWorldError, "max_steps must be a positive"):
            fixture(max_steps=0)
        f = fixture()
        with self.assertRaisesRegex(CognitiveMicroWorldError, "canonical lexical order"):
            replace(f, primary_source_ids=("z", "a"))


if __name__ == "__main__":
    unittest.main()
