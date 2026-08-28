from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.deferred_causal_return import (
    DeferredCausalReturn,
    DeferredCausalReturnError,
)
from frankenstein2.native_child_binding import NativeChildBinding


class DeferredCausalReturnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = CausalIdentity(
            session_id="session-1",
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-1",
            causal_id="causal-parent",
            generation=4,
        )
        child = self.parent.derive(
            causal_id="causal-child",
            generation=5,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
        )
        pending = NativeChildBinding(
            workpackage_id="F2-WP-102",
            workpackage_generation=1,
            claim_id="claim-wp102-g1",
            parent=self.parent,
            invocation_id="invocation-7",
            tool_use_id="tool-use-7",
            delegation_id="delegation-7",
            child=child,
        )
        self.bound = pending.bind_result(
            invocation_id="invocation-7",
            delegation_id="delegation-7",
            child_causal_id="causal-child",
            result_id="result-7",
            result_sha256="a" * 64,
        )
        self.resume = child.derive(
            causal_id="causal-resume",
            generation=6,
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-3",
        )
        self.return_envelope = DeferredCausalReturn(
            return_id="return-7",
            binding=self.bound,
            resume=self.resume,
        )

    def test_valid_bound_result_returns_to_parent_causally(self) -> None:
        self.assertEqual(
            self.return_envelope.resume.parent_causal_id,
            self.return_envelope.binding.child.causal_id,
        )
        self.assertEqual(
            self.return_envelope.resume.agent_id,
            self.return_envelope.binding.parent.agent_id,
        )

    def test_unbound_child_result_cannot_form_return(self) -> None:
        pending = NativeChildBinding(
            workpackage_id="F2-WP-102",
            workpackage_generation=1,
            claim_id="claim-wp102-g1",
            parent=self.parent,
            invocation_id="invocation-7",
            tool_use_id="tool-use-7",
            delegation_id="delegation-7",
            child=self.bound.child,
        )
        with self.assertRaises(DeferredCausalReturnError):
            DeferredCausalReturn(
                return_id="return-7",
                binding=pending,
                resume=self.resume,
            )

    def test_resume_must_be_caused_by_child_and_advance_generation(self) -> None:
        wrong_parent = CausalIdentity(
            session_id="session-1",
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-3",
            causal_id="causal-resume",
            generation=6,
            parent_causal_id="causal-parent",
        )
        with self.assertRaises(DeferredCausalReturnError):
            DeferredCausalReturn("return-7", self.bound, wrong_parent)
        stale = self.bound.child.derive(
            causal_id="causal-resume",
            generation=5,
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-3",
        )
        with self.assertRaises(DeferredCausalReturnError):
            DeferredCausalReturn("return-7", self.bound, stale)

    def test_resume_must_target_semantic_parent_agent_task_and_session(self) -> None:
        cases = (
            self.bound.child.derive(
                causal_id="resume-agent",
                generation=6,
                agent_id="other-agent",
                task_id="parent-task",
                turn_id="turn-3",
            ),
            self.bound.child.derive(
                causal_id="resume-task",
                generation=6,
                agent_id="parent-agent",
                task_id="other-task",
                turn_id="turn-3",
            ),
            self.bound.child.derive(
                causal_id="resume-session",
                generation=6,
                session_id="other-session",
                agent_id="parent-agent",
                task_id="parent-task",
                turn_id="turn-3",
            ),
        )
        for resume in cases:
            with self.subTest(resume=resume.causal_id):
                with self.assertRaises(DeferredCausalReturnError):
                    DeferredCausalReturn("return-7", self.bound, resume)

    def test_mapping_is_strict_and_serialization_is_deterministic(self) -> None:
        raw = self.return_envelope.as_dict()
        reconstructed = DeferredCausalReturn.from_mapping(
            {
                "resume": raw["resume"],
                "return_id": raw["return_id"],
                "binding": raw["binding"],
            }
        )
        self.assertEqual(
            self.return_envelope.canonical_json(), reconstructed.canonical_json()
        )
        self.assertEqual(self.return_envelope.sha256(), reconstructed.sha256())
        bad = raw | {"recipient_id": "belongs-to-wp103"}
        with self.assertRaises(DeferredCausalReturnError):
            DeferredCausalReturn.from_mapping(bad)


if __name__ == "__main__":
    unittest.main()
