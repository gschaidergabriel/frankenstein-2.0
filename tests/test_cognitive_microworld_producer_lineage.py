from dataclasses import replace
import hashlib
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionSpec,
    CognitiveMicroWorldError,
    MatchedRunPair,
    MicroWorldFixture,
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
        fixture_id="producer-lineage.001",
        generation=1,
        holdout_set_id="producer-lineage.v1",
        initial_node_id="n0",
        max_steps=1,
        actions=(ActionSpec("act", "action:act", h("act")),),
        nodes=(
            WorldNode("n0", "obs:0", h("obs0"), "hidden:0", h("hidden0"), False, 0),
            WorldNode("n1", "obs:1", h("obs1"), "hidden:1", h("hidden1"), True, 1),
        ),
        transitions=(TransitionRule("n0", "act", "n1", "transition:0", h("transition0")),),
        evidence_source_family="synthetic-heldout",
        primary_source_ids=("wp800-producer-lineage-regression",),
        donor_path_family="none-synthetic",
        method_family="producer-lineage-falsifier",
    )


class ProducerLineageRegressionTests(unittest.TestCase):
    def test_reconstructed_run_descriptor_loses_producer_credit(self) -> None:
        f = fixture()
        baseline = RunDescriptor.for_fixture(
            f,
            run_id="baseline",
            condition=BASELINE,
            episode_family_id="family",
            system_under_test_ref="baseline-v1",
            communication_before_result=False,
            independent_reproduction=True,
        )
        intervention = RunDescriptor.for_fixture(
            f,
            run_id="intervention",
            condition=INTERVENTION,
            episode_family_id="family",
            system_under_test_ref="candidate-v1",
            communication_before_result=False,
            independent_reproduction=True,
        )
        reconstructed = replace(baseline)
        with self.assertRaisesRegex(CognitiveMicroWorldError, "must originate from RunDescriptor.for_fixture"):
            MatchedRunPair.create(baseline=reconstructed, intervention=intervention)

    def test_reconstructed_episode_state_loses_evaluator_credit(self) -> None:
        f = fixture()
        state, _ = begin_episode(f, episode_id="episode", episode_generation=0)
        with self.assertRaisesRegex(CognitiveMicroWorldError, "EpisodeState must be created"):
            replace(state)


if __name__ == "__main__":
    unittest.main()
