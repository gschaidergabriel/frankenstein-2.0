from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionSpec,
    MatchedRunPair,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    TransitionRule,
    WorldNode,
    begin_episode,
    step_episode,
)
from frankenstein2.cognitive_information_seeking_benchmark import (
    COMMIT_FIRST,
    POLICY_SCHEMA,
    PROBE_THEN_COMMIT,
    RULE_SCHEMA,
    InformationSeekingBenchmarkError,
    InformationSeekingPolicy,
    PolicyEpisodeResult,
    PublicDecisionRule,
    PublicPolicyState,
    choose_public_action,
    run_matched_information_seeking_benchmark,
    run_policy_episode,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture(*, hidden_start: str = "ground-truth:start") -> MicroWorldFixture:
    return MicroWorldFixture(
        schema=FIXTURE_SCHEMA,
        fixture_id="heldout.info.001",
        generation=1,
        holdout_set_id="information-seeking.v1",
        initial_node_id="evaluator-start",
        max_steps=2,
        actions=(
            ActionSpec("commit-a", "action:commit-a", h("commit-a")),
            ActionSpec("commit-b", "action:commit-b", h("commit-b")),
            ActionSpec("probe", "action:probe", h("probe")),
        ),
        nodes=(
            WorldNode("evaluator-bad", "obs:bad", h("bad"), "ground-truth:bad", h("gt-bad"), True, -5),
            WorldNode("evaluator-good", "obs:good", h("good"), "ground-truth:good", h("gt-good"), True, 10),
            WorldNode("evaluator-signal", "obs:signal-b", h("signal-b"), "ground-truth:signal-b", h("gt-signal-b"), False, 0),
            WorldNode("evaluator-start", "obs:ambiguous", h("ambiguous"), hidden_start, h(hidden_start), False, 0),
        ),
        transitions=(
            TransitionRule("evaluator-signal", "commit-a", "evaluator-bad", "t:signal:a", h("signal-a")),
            TransitionRule("evaluator-signal", "commit-b", "evaluator-good", "t:signal:b", h("signal-b")),
            TransitionRule("evaluator-start", "commit-a", "evaluator-bad", "t:start:a", h("start-a")),
            TransitionRule("evaluator-start", "commit-b", "evaluator-good", "t:start:b", h("start-b")),
            TransitionRule("evaluator-start", "probe", "evaluator-signal", "t:start:probe", h("start-probe")),
        ),
        evidence_source_family="synthetic-heldout",
        primary_source_ids=("wp802-fixture-v1",),
        donor_path_family="none-synthetic",
        method_family="matched-information-seeking",
    )


def policies() -> tuple[InformationSeekingPolicy, InformationSeekingPolicy]:
    rule = PublicDecisionRule(RULE_SCHEMA, "obs:signal-b", h("signal-b"), "commit-b")
    baseline = InformationSeekingPolicy(
        POLICY_SCHEMA,
        "wp802-baseline-commit-first-v1",
        COMMIT_FIRST,
        ("probe",),
        ("commit-a", "commit-b"),
        0,
        (rule,),
    )
    intervention = InformationSeekingPolicy(
        POLICY_SCHEMA,
        "wp802-probe-then-commit-v1",
        PROBE_THEN_COMMIT,
        ("probe",),
        ("commit-a", "commit-b"),
        1,
        (rule,),
    )
    return baseline, intervention


def pair_for(f: MicroWorldFixture) -> tuple[MatchedRunPair, InformationSeekingPolicy, InformationSeekingPolicy]:
    baseline_policy, intervention_policy = policies()
    baseline = RunDescriptor.for_fixture(
        f,
        run_id="wp802-run-baseline",
        condition=BASELINE,
        episode_family_id="wp802-family-1",
        system_under_test_ref=baseline_policy.policy_id,
        communication_before_result=False,
        independent_reproduction=True,
    )
    intervention = RunDescriptor.for_fixture(
        f,
        run_id="wp802-run-intervention",
        condition=INTERVENTION,
        episode_family_id="wp802-family-1",
        system_under_test_ref=intervention_policy.policy_id,
        communication_before_result=False,
        independent_reproduction=True,
    )
    return MatchedRunPair.create(baseline=baseline, intervention=intervention, fixture=f), baseline_policy, intervention_policy


class InformationSeekingBenchmarkTests(unittest.TestCase):
    def test_matched_probe_before_commit_discriminates_without_hidden_policy_input(self) -> None:
        f = fixture()
        pair, baseline_policy, intervention_policy = pair_for(f)
        result = run_matched_information_seeking_benchmark(
            f,
            pair=pair,
            baseline_policy=baseline_policy,
            intervention_policy=intervention_policy,
        )
        self.assertEqual(result.baseline.action_ids, ("commit-a",))
        self.assertEqual(result.intervention.action_ids, ("probe", "commit-b"))
        self.assertEqual(result.baseline.cumulative_score, -5)
        self.assertEqual(result.intervention.cumulative_score, 10)
        self.assertEqual(result.score_delta, 15)
        self.assertEqual(result.probe_delta, 1)
        self.assertEqual(result.public_payload_novelty_delta, 1)
        self.assertEqual(result.baseline.unique_public_payload_count, 2)
        self.assertEqual(result.intervention.unique_public_payload_count, 3)

    def test_hidden_fixture_change_cannot_change_initial_public_policy_action(self) -> None:
        f1 = fixture(hidden_start="ground-truth:start-a")
        f2 = fixture(hidden_start="ground-truth:start-b")
        self.assertNotEqual(f1.sha256(), f2.sha256())
        self.assertEqual(f1.public_sha256(), f2.public_sha256())
        _, policy = policies()
        _, o1 = begin_episode(f1, episode_id="same-episode", episode_generation=1)
        _, o2 = begin_episode(f2, episode_id="same-episode", episode_generation=1)
        self.assertEqual(o1, o2)
        s1 = PublicPolicyState.for_observation(policy, o1)
        s2 = PublicPolicyState.for_observation(policy, o2)
        self.assertEqual(choose_public_action(policy, s1, o1), choose_public_action(policy, s2, o2))
        self.assertEqual(choose_public_action(policy, s1, o1).action_id, "probe")

    def test_policy_boundary_signature_has_no_fixture_or_evaluator_state(self) -> None:
        params = tuple(inspect.signature(choose_public_action).parameters)
        self.assertEqual(params, ("policy", "state", "observation"))

    def test_exact_observation_type_is_policy_trust_boundary(self) -> None:
        class EvilObservation(ObservationView):
            pass

        f = fixture()
        _, policy = policies()
        _, obs = begin_episode(f, episode_id="ep", episode_generation=1)
        evil = EvilObservation(**obs.as_dict())
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "exact concrete ObservationView"):
            PublicPolicyState.for_observation(policy, evil)

    def test_stale_public_policy_state_rejected_after_probe(self) -> None:
        f = fixture()
        _, policy = policies()
        evaluator_state, obs = begin_episode(f, episode_id="ep", episode_generation=1)
        public_state = PublicPolicyState.for_observation(policy, obs)
        request = choose_public_action(policy, public_state, obs)
        _, next_obs, _ = step_episode(f, state=evaluator_state, request=request)
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "does not match current observation lineage"):
            choose_public_action(policy, public_state, next_obs)

    def test_public_state_advance_fails_closed_on_probe_budget_overrun(self) -> None:
        f = fixture()
        _, policy = policies()
        evaluator_state, obs = begin_episode(f, episode_id="ep", episode_generation=1)
        state = PublicPolicyState.for_observation(policy, obs)
        request = choose_public_action(policy, state, obs)
        _, signal, _ = step_episode(f, state=evaluator_state, request=request)
        state = state.advance(policy, prior_observation=obs, action_id="probe", next_observation=signal)
        forged_next = replace(signal, step_index=signal.step_index + 1)
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "probe action exceeds declared probe budget"):
            state.advance(policy, prior_observation=signal, action_id="probe", next_observation=forged_next)

    def test_decision_rule_for_unavailable_commit_fails_closed(self) -> None:
        f = fixture()
        _, policy = policies()
        evaluator_state, obs = begin_episode(f, episode_id="ep", episode_generation=1)
        state = PublicPolicyState.for_observation(policy, obs)
        request = choose_public_action(policy, state, obs)
        _, signal, _ = step_episode(f, state=evaluator_state, request=request)
        restricted = replace(signal, available_action_ids=("commit-a", "probe"))
        restricted_state = PublicPolicyState.for_observation(policy, restricted)
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "unavailable commit action"):
            choose_public_action(policy, restricted_state, restricted)

    def test_policy_contract_rejects_overlap_unsorted_and_noncommit_rule(self) -> None:
        rule = PublicDecisionRule(RULE_SCHEMA, "obs:x", h("x"), "probe")
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "disjoint"):
            InformationSeekingPolicy(POLICY_SCHEMA, "p", PROBE_THEN_COMMIT, ("probe",), ("probe",), 1, ())
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "canonical lexical order"):
            InformationSeekingPolicy(POLICY_SCHEMA, "p", COMMIT_FIRST, (), ("z", "a"), 0, ())
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "only declared commit"):
            InformationSeekingPolicy(POLICY_SCHEMA, "p", PROBE_THEN_COMMIT, ("probe",), ("commit",), 1, (rule,))

    def test_run_rejects_descriptor_bound_to_different_hidden_fixture(self) -> None:
        f1 = fixture(hidden_start="ground-truth:a")
        f2 = fixture(hidden_start="ground-truth:b")
        pair, baseline_policy, _ = pair_for(f1)
        with self.assertRaisesRegex(ValueError, "does not match exact fixture"):
            run_policy_episode(f2, run=pair.baseline, policy=baseline_policy, episode_id="ep", episode_generation=1)

    def test_episode_result_cannot_be_self_attested_with_dataclass_replace(self) -> None:
        f = fixture()
        pair, baseline_policy, _ = pair_for(f)
        result = run_policy_episode(f, run=pair.baseline, policy=baseline_policy, episode_id="ep", episode_generation=1)
        self.assertIsInstance(result, PolicyEpisodeResult)
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "must be created by run_policy_episode"):
            replace(result, cumulative_score=999)

    def test_replay_is_deterministic_at_result_digest(self) -> None:
        f = fixture()
        pair, baseline_policy, intervention_policy = pair_for(f)
        a = run_matched_information_seeking_benchmark(
            f,
            pair=pair,
            baseline_policy=baseline_policy,
            intervention_policy=intervention_policy,
            episode_generation=4,
        )
        b = run_matched_information_seeking_benchmark(
            f,
            pair=pair,
            baseline_policy=baseline_policy,
            intervention_policy=intervention_policy,
            episode_generation=4,
        )
        self.assertEqual(a.sha256(), b.sha256())

    def test_matched_policy_identity_mismatch_rejected(self) -> None:
        f = fixture()
        pair, baseline_policy, intervention_policy = pair_for(f)
        bad = replace(intervention_policy, policy_id="wrong-policy")
        with self.assertRaisesRegex(InformationSeekingBenchmarkError, "intervention run/policy identity mismatch"):
            run_matched_information_seeking_benchmark(
                f,
                pair=pair,
                baseline_policy=baseline_policy,
                intervention_policy=bad,
            )


if __name__ == "__main__":
    unittest.main()
