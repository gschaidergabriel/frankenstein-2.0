from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.deferred_return import DeferredReturnEnvelope, DeferredReturnError
from frankenstein2.native_child_binding import NativeChildBinding


class DeferredReturnEnvelopeTests(unittest.TestCase):
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
        pending = NativeChildBinding(
            workpackage_id="F2-WP-102",
            parent=self.parent,
            tool_use_id="tool-use-7",
            delegation_id="delegation-7",
            child=self.child,
        )
        self.binding = pending.bind_result(
            delegation_id="delegation-7",
            child_causal_id="causal-child",
            result_id="result-7",
            result_sha256="a" * 64,
        )
        self.resume = self.child.derive(
            causal_id="causal-parent-resume",
            generation=6,
            agent_id=self.parent.agent_id,
            task_id=self.parent.task_id,
            turn_id="turn-3",
        )

    def make(self) -> DeferredReturnEnvelope:
        return DeferredReturnEnvelope(
            return_id="return-7",
            binding=self.binding,
            resume=self.resume,
        )

    def test_valid_return_binds_result_to_parent_reentry(self) -> None:
        envelope = self.make()
        self.assertEqual(envelope.result_id, "result-7")
        self.assertEqual(envelope.result_sha256, "a" * 64)
        self.assertEqual(envelope.resume.parent_causal_id, self.child.causal_id)
        self.assertEqual(envelope.resume.agent_id, self.parent.agent_id)

    def test_unbound_child_result_is_rejected(self) -> None:
        pending = NativeChildBinding(
            workpackage_id="F2-WP-102",
            parent=self.parent,
            tool_use_id="tool-use-7",
            delegation_id="delegation-7",
            child=self.child,
        )
        with self.assertRaises(DeferredReturnError):
            DeferredReturnEnvelope(
                return_id="return-7",
                binding=pending,
                resume=self.resume,
            )

    def test_resume_must_descend_from_child(self) -> None:
        wrong = self.parent.derive(
            causal_id="causal-parent-resume",
            generation=6,
            turn_id="turn-3",
        )
        with self.assertRaises(DeferredReturnError):
            DeferredReturnEnvelope(
                return_id="return-7",
                binding=self.binding,
                resume=wrong,
            )

    def test_resume_generation_must_advance(self) -> None:
        stale = self.child.derive(
            causal_id="causal-parent-resume",
            generation=5,
            agent_id=self.parent.agent_id,
            task_id=self.parent.task_id,
            turn_id="turn-3",
        )
        with self.assertRaises(DeferredReturnError):
            DeferredReturnEnvelope(
                return_id="return-7",
                binding=self.binding,
                resume=stale,
            )

    def test_resume_returns_to_same_parent_session_agent_and_task(self) -> None:
        variants = (
            self.child.derive(
                causal_id="resume-session",
                generation=6,
                session_id="other-session",
                agent_id=self.parent.agent_id,
                task_id=self.parent.task_id,
                turn_id="turn-3",
            ),
            self.child.derive(
                causal_id="resume-agent",
                generation=6,
                agent_id="other-agent",
                task_id=self.parent.task_id,
                turn_id="turn-3",
            ),
            self.child.derive(
                causal_id="resume-task",
                generation=6,
                agent_id=self.parent.agent_id,
                task_id="other-task",
                turn_id="turn-3",
            ),
        )
        for resume in variants:
            with self.subTest(resume=resume.causal_id), self.assertRaises(DeferredReturnError):
                DeferredReturnEnvelope(
                    return_id="return-7",
                    binding=self.binding,
                    resume=resume,
                )

    def test_resume_causal_id_must_be_fresh(self) -> None:
        reused = self.child.derive(
            causal_id=self.parent.causal_id,
            generation=6,
            agent_id=self.parent.agent_id,
            task_id=self.parent.task_id,
            turn_id="turn-3",
        )
        with self.assertRaises(DeferredReturnError):
            DeferredReturnEnvelope(
                return_id="return-7",
                binding=self.binding,
                resume=reused,
            )

    def test_canonical_serialization_is_stable(self) -> None:
        envelope = self.make()
        raw = envelope.as_dict()
        reconstructed = DeferredReturnEnvelope.from_mapping(
            {
                "resume": raw["resume"],
                "return_id": raw["return_id"],
                "binding": raw["binding"],
            }
        )
        self.assertEqual(envelope.canonical_json(), reconstructed.canonical_json())
        self.assertEqual(envelope.sha256(), reconstructed.sha256())

    def test_completion_effect_or_delivery_claims_fail_closed(self) -> None:
        raw = self.make().as_dict()
        for forbidden in ("completion", "effect_id", "delivery_state", "transport_attempt_id"):
            mutated = dict(raw)
            mutated[forbidden] = "claimed"
            with self.subTest(forbidden=forbidden), self.assertRaises(DeferredReturnError):
                DeferredReturnEnvelope.from_mapping(mutated)


if __name__ == "__main__":
    unittest.main()
