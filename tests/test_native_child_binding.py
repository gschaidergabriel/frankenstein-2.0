from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.native_child_binding import NativeChildBinding, NativeChildBindingError


class NativeChildBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = CausalIdentity(
            session_id="session-1", agent_id="parent-agent", task_id="parent-task",
            turn_id="turn-1", causal_id="causal-parent", generation=4,
        )
        self.child = self.parent.derive(
            causal_id="causal-child", generation=5, agent_id="child-agent",
            task_id="child-task", turn_id="turn-2",
        )
        self.binding = NativeChildBinding(
            workpackage_id="F2-WP-102",
            workpackage_generation=1,
            claim_id="claim-wp102-g1",
            parent=self.parent,
            invocation_id="invocation-7",
            tool_use_id="tool-use-7",
            delegation_id="delegation-7",
            child=self.child,
        )
        self.digest = "a" * 64

    def bind(self, **overrides):
        args = {
            "invocation_id": "invocation-7",
            "delegation_id": "delegation-7",
            "child_causal_id": "causal-child",
            "result_id": "result-7",
            "result_sha256": self.digest,
        }
        args.update(overrides)
        return self.binding.bind_result(**args)

    def test_valid_pending_and_result_binding(self) -> None:
        self.assertFalse(self.binding.has_result)
        before_id = self.binding.binding_id()
        bound = self.bind()
        self.assertTrue(bound.has_result)
        self.assertEqual(bound.result_id, "result-7")
        self.assertEqual(bound.result_sha256, self.digest)
        self.assertEqual(bound.binding_id(), before_id)
        self.assertNotEqual(bound.sha256(), self.binding.sha256())

    def test_exact_result_replay_is_idempotent(self) -> None:
        bound = self.bind()
        replayed = bound.bind_result(
            invocation_id="invocation-7", delegation_id="delegation-7",
            child_causal_id="causal-child", result_id="result-7", result_sha256=self.digest,
        )
        self.assertIs(bound, replayed)
        with self.assertRaises(NativeChildBindingError):
            bound.bind_result(
                invocation_id="invocation-7", delegation_id="delegation-7",
                child_causal_id="causal-child", result_id="result-other", result_sha256="b" * 64,
            )

    def test_wrong_invocation_delegation_or_child_cannot_receive_result(self) -> None:
        for field, value in (
            ("invocation_id", "invocation-other"),
            ("delegation_id", "delegation-other"),
            ("child_causal_id", "causal-other"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(NativeChildBindingError):
                    self.bind(**{field: value})

    def test_child_must_explicitly_descend_and_advance(self) -> None:
        unrelated = CausalIdentity(
            session_id="session-1", agent_id="child-agent", task_id="child-task",
            turn_id="turn-2", causal_id="causal-child", generation=5,
        )
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102", workpackage_generation=1, claim_id="claim-wp102-g1",
                parent=self.parent, invocation_id="invocation-7", tool_use_id="tool-use-7",
                delegation_id="delegation-7", child=unrelated,
            )
        same_generation = self.parent.derive(
            causal_id="causal-child", generation=4, agent_id="child-agent",
            task_id="child-task", turn_id="turn-2",
        )
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102", workpackage_generation=1, claim_id="claim-wp102-g1",
                parent=self.parent, invocation_id="invocation-7", tool_use_id="tool-use-7",
                delegation_id="delegation-7", child=same_generation,
            )

    def test_child_session_bridge_is_not_implicit(self) -> None:
        other_session = self.parent.derive(
            causal_id="causal-child", generation=5, session_id="session-other",
            agent_id="child-agent", task_id="child-task", turn_id="turn-2",
        )
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102", workpackage_generation=1, claim_id="claim-wp102-g1",
                parent=self.parent, invocation_id="invocation-7", tool_use_id="tool-use-7",
                delegation_id="delegation-7", child=other_session,
            )

    def test_workpackage_generation_and_claim_are_explicit_binding_identity(self) -> None:
        self.assertTrue(self.binding.binding_id().startswith("wex:"))
        other_generation = NativeChildBinding(
            workpackage_id="F2-WP-102", workpackage_generation=2, claim_id="claim-wp102-g2",
            parent=self.parent, invocation_id="invocation-7", tool_use_id="tool-use-7",
            delegation_id="delegation-7", child=self.child,
        )
        self.assertNotEqual(self.binding.binding_id(), other_generation.binding_id())
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(NativeChildBindingError):
                    NativeChildBinding(
                        workpackage_id="F2-WP-102", workpackage_generation=invalid, claim_id="claim-wp102-g1",
                        parent=self.parent, invocation_id="invocation-7", tool_use_id="tool-use-7",
                        delegation_id="delegation-7", child=self.child,
                    )

    def test_result_is_all_or_nothing_and_digest_is_strict(self) -> None:
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding(
                workpackage_id="F2-WP-102", workpackage_generation=1, claim_id="claim-wp102-g1",
                parent=self.parent, invocation_id="invocation-7", tool_use_id="tool-use-7",
                delegation_id="delegation-7", child=self.child, result_id="result-7",
            )
        with self.assertRaises(NativeChildBindingError):
            self.bind(result_sha256="A" * 64)

    def test_mapping_is_strict_and_canonical_serialization_is_stable(self) -> None:
        raw = self.binding.as_dict()
        reordered = {
            "child": raw["child"],
            "delegation_id": raw["delegation_id"],
            "tool_use_id": raw["tool_use_id"],
            "invocation_id": raw["invocation_id"],
            "parent": raw["parent"],
            "claim_id": raw["claim_id"],
            "workpackage_generation": raw["workpackage_generation"],
            "workpackage_id": raw["workpackage_id"],
            "result_sha256": None,
            "result_id": None,
        }
        reconstructed = NativeChildBinding.from_mapping(reordered)
        self.assertEqual(self.binding.canonical_json(), reconstructed.canonical_json())
        self.assertEqual(self.binding.binding_id(), reconstructed.binding_id())
        reordered["completion"] = True
        with self.assertRaises(NativeChildBindingError):
            NativeChildBinding.from_mapping(reordered)

    def test_completion_and_effect_authority_are_not_part_of_wp102(self) -> None:
        bound = self.bind()
        fields = bound.as_dict()
        self.assertNotIn("completion_id", fields)
        self.assertNotIn("effect", fields)
        self.assertNotIn("outcome", fields)


if __name__ == "__main__":
    unittest.main()
