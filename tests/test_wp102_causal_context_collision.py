from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.native_child_binding import NativeChildBinding


class WP102CausalContextCollisionTests(unittest.TestCase):
    """Regression for the explicit F2-WP-102 causal-context projection falsifier."""

    def make_binding(
        self,
        *,
        session_id: str = "session-A",
        task_id: str = "task-A",
        turn_id: str = "turn-A",
        causal_generation: int = 4,
    ) -> NativeChildBinding:
        parent = CausalIdentity(
            session_id=session_id,
            agent_id="parent-agent",
            task_id=task_id,
            turn_id=turn_id,
            causal_id="shared-parent-causal-id",
            generation=causal_generation,
        )
        child = parent.derive(
            causal_id="shared-child-causal-id",
            generation=causal_generation + 1,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="child-turn",
        )
        return NativeChildBinding(
            workpackage_id="F2-WP-102",
            workpackage_generation=1,
            claim_id="claim-wp102-g1",
            parent=parent,
            invocation_id="invocation-shared",
            tool_use_id="tool-use-shared",
            delegation_id="delegation-shared",
            child=child,
        )

    def test_full_causal_context_is_collision_separating(self) -> None:
        baseline = self.make_binding()
        variants = {
            "session": self.make_binding(session_id="session-B"),
            "task": self.make_binding(task_id="task-B"),
            "turn": self.make_binding(turn_id="turn-B"),
            "causal_generation": self.make_binding(causal_generation=9),
        }
        for dimension, candidate in variants.items():
            with self.subTest(dimension=dimension):
                self.assertEqual(candidate.parent.causal_id, baseline.parent.causal_id)
                self.assertEqual(candidate.invocation_id, baseline.invocation_id)
                self.assertEqual(candidate.tool_use_id, baseline.tool_use_id)
                self.assertEqual(candidate.delegation_id, baseline.delegation_id)
                self.assertNotEqual(candidate.binding_id(), baseline.binding_id())

    def test_workpackage_and_causal_generation_domains_are_distinct(self) -> None:
        binding = self.make_binding(causal_generation=7)
        payload = binding.as_dict()
        self.assertEqual(payload["workpackage_generation"], 1)
        self.assertEqual(payload["parent"]["generation"], 7)
        self.assertEqual(payload["child"]["generation"], 8)
        self.assertNotIn("generation", {k: v for k, v in payload.items() if k != "parent" and k != "child"})


if __name__ == "__main__":
    unittest.main()
