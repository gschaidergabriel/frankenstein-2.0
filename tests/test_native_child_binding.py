from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.native_child_binding import NativeChildBinding, NativeChildBindingError


class NativeChildBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = CausalIdentity(
            session_id="session-1",
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-1",
            causal_id="causal-parent",
            generation=4,
        )
        self.child = self.parent.derive(
            causal_id="causal-child",
            generation=5,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
        )
        self.binding = NativeChildBinding(
            workpackage_id="F2-WP-102",
            parent=self.parent,
            tool_use_id="tool-use-7",
            delegation_id="delegation-7",
            child=self.child,
        )
        self.digest = "a" * 64

    def test_valid_pending_and_result_binding(self) -> None:
        self.assertFalse(self.binding.has_result)
        bound = self.binding.bind_result(
            delegation_id="delegation-7",
            child_causal_id="causal-child",
            result_id="result-7",
            result_sha256=self.digest,
        )
        self.assertTrue(bound.has_result)
        self.assertEqual(bound.result_id, "result-7")
        self.assertEqual(bound.result_sha256, self.digest)

    def test_exact_result_replay_is_idempotent(self) -> None:
        bound = self.binding.bind_result(
            delegation_id="delegation-7",
            child_causal_id="causal-child",
            result_id="result-7",
            result_sha256=self.digest,
        )
        replayed = bound.bind_result(
            delegation_id="delegation-7",
            child_causal_id="causal-child",
            result_id="result-7",
            result_sha256=self.digest,
        )
        self.assertIs(bound, replayed)
        with self.assertRaises(NativeChildBindingError):
            bound.bind_result(
                delegation_id="delegation-7",
                child_causal_id="causal-child",
                result_id="result-other",
                result_sha256="b" * 64,
            )

    def test_wrong_delegation_or_child_cannot_receive_result(self) -> None:
        with self.assertRaises(NativeChildBindingError):
            self.binding.bind_result(
                delegation_id="delegation-other",
                child_causal_id="causal-child",
                result_id="result-7",
                result_sha256=self.digest,
            )
        with self.assertRaises(NativeChildBindingError):
            self.binding.bind_result(
                delegation_id="delegation-7",
                child_causal_id="causal-other",
                result_id="result-7",
                result_sha256=self.digest,
            )

    def test_child_must_explicitly_descend_from_parent(self) -> None:
        unrelated = CausalIdentity(
            session_id="session-1",
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
            causal_id="causal-child",
            generation=5,
        )
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102",
                parent=self.parent,
                tool_use_id="tool-use-7",
                delegation_id="delegation-7",
                child=unrelated,
            )

    def test_child_generation_must_advance(self) -> None:
        same_generation = self.parent.derive(
            causal_id="causal-child",
            generation=4,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
        )
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102",
                parent=self.parent,
                tool_use_id="tool-use-7",
                delegation_id="delegation-7",
                child=same_generation,
            )

    def test_child_session_bridge_is_not_implicit(self) -> None:
        other_session = self.parent.derive(
            causal_id="causal-child",
            generation=5,
            session_id="session-other",
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
        )
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102",
                parent=self.parent,
                tool_use_id="tool-use-7",
                delegation_id="delegation-7",
                child=other_session,
            )

    def test_result_is_all_or_nothing_and_digest_is_strict(self) -> None:
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102",
                parent=self.parent,
                tool_use_id="tool-use-7",
                delegation_id="delegation-7",
                child=self.child,
                result_id="result-7",
            )
        with self.assertRaises(NativeChildBindingError):
            self.binding.bind_result(
                delegation_id="delegation-7",
                child_causal_id="causal-child",
                result_id="result-7",
                result_sha256="A" * 64,
            )

    def test_mapping_is_strict_and_canonical_serialization_is_stable(self) -> None:
        raw = self.binding.as_dict()
        reordered = {
            "child": raw["child"],
            "delegation_id": raw["delegation_id"],
            "tool_use_id": raw["tool_use_id"],
            "parent": raw["parent"],
            "workpackage_id": raw["workpackage_id"],
            "result_sha256": None,
            "result_id": None,
        }
        reconstructed = NativeChildBinding.from_mapping(reordered)
        self.assertEqual(self.binding.canonical_json(), reconstructed.canonical_json())
        self.assertEqual(self.binding.sha256(), reconstructed.sha256())
        reordered["unexpected"] = "no"
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding.from_mapping(reordered)


if __name__ == "__main__":
    unittest.main()
