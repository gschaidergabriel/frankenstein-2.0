from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.deferred_return import DeferredReturnEnvelope
from frankenstein2.deferred_return_delivery import (
    ack_deferred_return,
    causal_recipient_id,
    enqueue_deferred_return,
    offer_deferred_returns,
)
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.recipient_delivery import DeliveryConflict
from frankenstein2.recipient_delivery_binding import bind_recipient_delivery_to_canonical_unifieddb


class DeferredReturnDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.root / "unified.db"
        con = sqlite3.connect(self.db)
        try:
            con.execute("CREATE TABLE canonical_seed(id INTEGER PRIMARY KEY)")
            con.commit()
        finally:
            con.close()
        bound = bind_recipient_delivery_to_canonical_unifieddb(
            env={
                "FRANKENSTEIN2_DB": str(self.db),
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "XDG_DATA_HOME": str(self.root / "data"),
            },
            home=self.home,
            pointer_path=self.root / "absent-pointer.txt",
        )
        self.store = bound.store

        self.parent = CausalIdentity(
            session_id="session-A",
            agent_id="parent-agent",
            task_id="task-1",
            turn_id="turn-parent",
            causal_id="cause-parent",
            generation=1,
        )
        self.child = self.parent.derive(
            causal_id="cause-child",
            generation=2,
            agent_id="child-agent",
            turn_id="turn-child",
        )
        result_digest = hashlib.sha256(b"child-result-v1").hexdigest()
        unbound = NativeChildBinding(
            workpackage_id="F2-WP-103",
            workpackage_generation=2,
            claim_id="claim-1",
            parent=self.parent,
            invocation_id="invoke-1",
            tool_use_id="tool-use-1",
            delegation_id="delegate-1",
            child=self.child,
        )
        self.binding = unbound.bind_result(
            invocation_id="invoke-1",
            delegation_id="delegate-1",
            child_causal_id="cause-child",
            result_id="result-1",
            result_sha256=result_digest,
        )
        self.resume = self.child.derive(
            causal_id="cause-parent-resume",
            generation=3,
            agent_id=self.parent.agent_id,
            task_id=self.parent.task_id,
            turn_id="turn-parent-resume",
        )
        self.envelope = DeferredReturnEnvelope(
            return_id="return-1",
            binding=self.binding,
            resume=self.resume,
        )

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_child_result_is_automatically_addressed_to_exact_parent_resume(self) -> None:
        pending = enqueue_deferred_return(self.store, self.envelope, created_at=1.0)
        self.assertEqual(pending.state, "PENDING")
        self.assertEqual(pending.recipient_id, causal_recipient_id(self.resume))
        self.assertEqual(pending.generation, self.resume.generation)

        offered = offer_deferred_returns(
            self.store,
            resume=self.resume,
            lease_seconds=10.0,
            now=2.0,
        )
        self.assertEqual(len(offered), 1)
        self.assertEqual(offered[0].envelope, self.envelope)
        self.assertEqual(offered[0].delivery.state, "OFFERED")

        acked = ack_deferred_return(self.store, offered[0], now=3.0)
        self.assertEqual(acked.state, "ACKED")

    def test_same_session_and_agent_but_different_causal_resume_cannot_steal_return(self) -> None:
        enqueue_deferred_return(self.store, self.envelope, created_at=1.0)
        wrong_resume = CausalIdentity(
            session_id=self.resume.session_id,
            agent_id=self.resume.agent_id,
            task_id="other-task",
            turn_id=self.resume.turn_id,
            causal_id="other-cause",
            generation=self.resume.generation,
            parent_causal_id=self.resume.parent_causal_id,
        )
        self.assertNotEqual(causal_recipient_id(wrong_resume), causal_recipient_id(self.resume))
        self.assertEqual(
            offer_deferred_returns(
                self.store,
                resume=wrong_resume,
                lease_seconds=10.0,
                now=2.0,
            ),
            [],
        )
        self.assertEqual(
            len(
                offer_deferred_returns(
                    self.store,
                    resume=self.resume,
                    lease_seconds=10.0,
                    now=2.0,
                )
            ),
            1,
        )

    def test_crash_before_ack_redelivers_and_stale_attempt_cannot_consume(self) -> None:
        enqueue_deferred_return(self.store, self.envelope, created_at=1.0)
        first = offer_deferred_returns(
            self.store,
            resume=self.resume,
            lease_seconds=5.0,
            now=10.0,
        )[0]
        # Simulated worker crash: no ACK. The exact resume is reconstructed later.
        rejoined_resume = CausalIdentity.from_mapping(self.resume.as_dict())
        second = offer_deferred_returns(
            self.store,
            resume=rejoined_resume,
            lease_seconds=5.0,
            now=15.0,
        )[0]

        self.assertEqual(second.envelope, self.envelope)
        self.assertEqual(second.delivery.attempt_count, 2)
        self.assertNotEqual(first.delivery.offer_token, second.delivery.offer_token)
        with self.assertRaisesRegex(Exception, "token mismatch|stale"):
            ack_deferred_return(self.store, first, now=16.0)
        self.assertEqual(ack_deferred_return(self.store, second, now=16.0).state, "ACKED")

    def test_late_recipient_rejoin_after_unoffered_pending_message_receives_it(self) -> None:
        enqueue_deferred_return(self.store, self.envelope, created_at=1.0)
        # No parent process is present at enqueue time. Later reconstruction from durable
        # causal identity is enough to address the same pending return.
        reconstructed = CausalIdentity.from_mapping(self.resume.as_dict())
        offered = offer_deferred_returns(
            self.store,
            resume=reconstructed,
            lease_seconds=5.0,
            now=1000.0,
        )
        self.assertEqual(len(offered), 1)
        self.assertEqual(offered[0].envelope.result_id, "result-1")

    def test_duplicate_same_return_is_idempotent_but_mutated_same_return_id_fails_closed(self) -> None:
        first = enqueue_deferred_return(self.store, self.envelope, created_at=1.0)
        replay = enqueue_deferred_return(self.store, self.envelope, created_at=999.0)
        self.assertEqual(first.payload_sha256, replay.payload_sha256)

        altered_digest = hashlib.sha256(b"different-result").hexdigest()
        altered_binding = NativeChildBinding(
            workpackage_id=self.binding.workpackage_id,
            workpackage_generation=self.binding.workpackage_generation,
            claim_id=self.binding.claim_id,
            parent=self.binding.parent,
            invocation_id=self.binding.invocation_id,
            tool_use_id=self.binding.tool_use_id,
            delegation_id=self.binding.delegation_id,
            child=self.binding.child,
            result_id="result-2",
            result_sha256=altered_digest,
        )
        altered = DeferredReturnEnvelope(
            return_id=self.envelope.return_id,
            binding=altered_binding,
            resume=self.resume,
        )
        with self.assertRaises(DeliveryConflict):
            enqueue_deferred_return(self.store, altered, created_at=2.0)

    def test_ack_of_one_return_does_not_consume_another_resume(self) -> None:
        enqueue_deferred_return(self.store, self.envelope, created_at=1.0)
        offered = offer_deferred_returns(
            self.store,
            resume=self.resume,
            lease_seconds=10.0,
            now=2.0,
        )[0]
        ack_deferred_return(self.store, offered, now=3.0)

        second_resume = self.child.derive(
            causal_id="cause-parent-resume-2",
            generation=4,
            agent_id=self.parent.agent_id,
            task_id=self.parent.task_id,
            turn_id="turn-parent-resume-2",
        )
        second = DeferredReturnEnvelope(
            return_id="return-2",
            binding=self.binding,
            resume=second_resume,
        )
        pending2 = enqueue_deferred_return(self.store, second, created_at=4.0)
        self.assertEqual(pending2.state, "PENDING")
        self.assertEqual(
            len(
                offer_deferred_returns(
                    self.store,
                    resume=second_resume,
                    lease_seconds=10.0,
                    now=5.0,
                )
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
