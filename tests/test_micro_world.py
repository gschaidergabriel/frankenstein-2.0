from __future__ import annotations

import unittest

from frankenstein2.micro_world import (
    ActionSpec,
    Condition,
    MicroWorldError,
    MicroWorldRunState,
    SPLIT_DEVELOPMENT,
    SPLIT_HELD_OUT,
    TRANSITION_APPLIED,
    TRANSITION_BLOCKED,
    create_partition,
    create_scenario,
    replay_micro_world,
    reset_micro_world,
    step_micro_world,
)


def scenario(*, scenario_id: str = "dev-switch-01", split: str = SPLIT_DEVELOPMENT, max_steps: int = 8, variant: str = "a"):
    initial = {
        "position": "entry",
        "clue": "none",
        "gate_open": False,
        "goal_reached": False,
        "variant": variant,
    }
    actions = (
        ActionSpec(
            action_id="inspect",
            preconditions=(),
            updates=(("clue", "switch-found"),),
        ),
        ActionSpec(
            action_id="open-gate",
            preconditions=(Condition("clue", "switch-found"),),
            updates=(("gate_open", True),),
        ),
        ActionSpec(
            action_id="finish",
            preconditions=(Condition("gate_open", True),),
            updates=(("goal_reached", True), ("position", "exit")),
        ),
    )
    return create_scenario(
        scenario_id=scenario_id,
        generation=1,
        split=split,
        initial_state=initial,
        visible_keys=("position", "clue"),
        actions=actions,
        terminal_conditions=(Condition("goal_reached", True),),
        max_steps=max_steps,
    )


class MicroWorldTests(unittest.TestCase):
    def test_observation_does_not_expose_hidden_truth_or_split_metadata(self) -> None:
        world = scenario(split=SPLIT_HELD_OUT, scenario_id="heldout-switch-01")
        state, obs = reset_micro_world(world, episode_id="ep-1")

        self.assertEqual(dict(obs.visible_state), {"clue": "none", "position": "entry"})
        self.assertNotIn("gate_open", dict(obs.visible_state))
        self.assertNotIn("goal_reached", dict(obs.visible_state))
        rendered = obs.as_dict()
        self.assertNotIn("split", rendered)
        self.assertNotIn("scenario_sha256", rendered)
        self.assertNotIn("scenario_id", rendered)
        self.assertEqual(state.step_index, 0)

    def test_blocked_action_is_typed_and_does_not_mutate_world(self) -> None:
        world = scenario()
        state, _ = reset_micro_world(world, episode_id="ep-2")
        before_world = state.world_state
        state, obs = step_micro_world(world, state, episode_id="ep-2", action_id="finish")

        self.assertEqual(obs.transition_class, TRANSITION_BLOCKED)
        self.assertEqual(state.world_state, before_world)
        self.assertEqual(state.step_index, 1)
        self.assertFalse(state.terminal)

    def test_successful_path_reaches_hidden_terminal_condition(self) -> None:
        world = scenario()
        state, _ = reset_micro_world(world, episode_id="ep-3")
        for action_id in ("inspect", "open-gate", "finish"):
            state, obs = step_micro_world(world, state, episode_id="ep-3", action_id=action_id)
            self.assertEqual(obs.transition_class, TRANSITION_APPLIED)

        self.assertTrue(state.terminal)
        self.assertTrue(obs.terminal)
        self.assertEqual(dict(obs.visible_state), {"clue": "switch-found", "position": "exit"})
        self.assertNotIn("goal_reached", dict(obs.visible_state))

    def test_replay_is_exactly_deterministic(self) -> None:
        world = scenario()
        actions = ("inspect", "open-gate", "finish")
        state_a, obs_a = replay_micro_world(world, episode_id="ep-replay", actions=actions)
        state_b, obs_b = replay_micro_world(world, episode_id="ep-replay", actions=actions)

        self.assertEqual(state_a.sha256(), state_b.sha256())
        self.assertEqual(tuple(item.sha256() for item in obs_a), tuple(item.sha256() for item in obs_b))

    def test_max_steps_is_a_hard_terminal_bound(self) -> None:
        world = scenario(max_steps=1)
        state, _ = reset_micro_world(world, episode_id="ep-bound")
        state, obs = step_micro_world(world, state, episode_id="ep-bound", action_id="inspect")
        self.assertTrue(state.terminal)
        self.assertTrue(obs.terminal)
        with self.assertRaises(MicroWorldError):
            step_micro_world(world, state, episode_id="ep-bound", action_id="open-gate")

    def test_partition_rejects_same_semantic_world_under_renamed_heldout_id(self) -> None:
        dev = scenario(scenario_id="dev-a", split=SPLIT_DEVELOPMENT)
        held = scenario(scenario_id="held-a", split=SPLIT_HELD_OUT)
        self.assertNotEqual(dev.sha256(), held.sha256())
        self.assertEqual(dev.content_sha256(), held.content_sha256())
        with self.assertRaisesRegex(MicroWorldError, "semantic content"):
            create_partition(development=(dev,), held_out=(held,))

    def test_partition_accepts_disjoint_identity_and_content(self) -> None:
        dev = scenario(scenario_id="dev-a", split=SPLIT_DEVELOPMENT, variant="a")
        held = scenario(scenario_id="held-b", split=SPLIT_HELD_OUT, variant="b")
        partition = create_partition(development=(dev,), held_out=(held,))
        self.assertNotEqual(partition.development[0][0], partition.held_out[0][0])
        self.assertNotEqual(partition.development[0][2], partition.held_out[0][2])
        self.assertEqual(len(partition.sha256()), 64)

    def test_partition_rejects_same_identity_even_when_content_differs(self) -> None:
        dev = scenario(scenario_id="shared", split=SPLIT_DEVELOPMENT, variant="a")
        held = scenario(scenario_id="shared", split=SPLIT_HELD_OUT, variant="b")
        with self.assertRaisesRegex(MicroWorldError, "scenario_id"):
            create_partition(development=(dev,), held_out=(held,))

    def test_run_state_is_factory_only_and_consumer_revalidates_digest(self) -> None:
        world = scenario()
        with self.assertRaises(MicroWorldError):
            MicroWorldRunState(
                schema="FRANKENSTEIN2_MICRO_WORLD_RUN_STATE/v1",
                scenario_id=world.scenario_id,
                scenario_generation=1,
                scenario_sha256=world.sha256(),
                step_index=0,
                world_state=world.initial_state,
                terminal=False,
                authority_boundary="MICRO_WORLD_TEST_HARNESS_NOT_WORLD_TRUTH_EFFECT_COMPLETION_OR_RUNTIME_AUTHORITY",
            )

        state, _ = reset_micro_world(world, episode_id="ep-forge")
        object.__setattr__(state, "scenario_sha256", "0" * 64)
        with self.assertRaisesRegex(MicroWorldError, "scenario digest mismatch"):
            step_micro_world(world, state, episode_id="ep-forge", action_id="inspect")

    def test_unknown_action_and_unknown_state_key_fail_closed(self) -> None:
        world = scenario()
        state, _ = reset_micro_world(world, episode_id="ep-invalid")
        with self.assertRaisesRegex(MicroWorldError, "unknown action_id"):
            step_micro_world(world, state, episode_id="ep-invalid", action_id="teleport")

        bad_action = ActionSpec(action_id="bad", preconditions=(), updates=(("missing", 1),))
        with self.assertRaisesRegex(MicroWorldError, "unknown state key"):
            create_scenario(
                scenario_id="bad-world",
                generation=1,
                split=SPLIT_DEVELOPMENT,
                initial_state={"known": 0},
                visible_keys=("known",),
                actions=(bad_action,),
            )

    def test_bool_is_not_accepted_as_max_steps_integer(self) -> None:
        with self.assertRaises(MicroWorldError):
            scenario(max_steps=True)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
