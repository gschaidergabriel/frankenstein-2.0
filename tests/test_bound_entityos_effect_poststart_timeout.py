from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.canonical_effect_authority_bridge import EffectCallIntent
from frankenstein2.effect_executor_interlock import (
    ExecutorOutcomeUnknown,
    dispatch_through_external_gate,
)
from frankenstein2.entityos_effect_gate_call_bridge import (
    EntityOSEffectCallContext,
    attach_entityos_request_identity,
    bind_unique_pending_entityos_effect,
)


CANONICAL_ROOT_RAW = os.environ.get("ENTITYOS_CANONICAL_ROOT")
CANONICAL_ROOT = Path(CANONICAL_ROOT_RAW).resolve() if CANONICAL_ROOT_RAW else None
if CANONICAL_ROOT is not None:
    sys.path.insert(0, str(CANONICAL_ROOT / "the artefact"))
    from clayverse.effects import EffectGate, EffectRequest  # type: ignore[import-not-found]
    from clayverse.store import UnifiedDB  # type: ignore[import-not-found]
else:  # pragma: no cover - dedicated CI supplies the exact-bound canonical fixture.
    EffectGate = EffectRequest = UnifiedDB = None  # type: ignore[assignment]


def call_intent() -> EffectCallIntent:
    return EffectCallIntent(
        return_id=None,
        binding_id="binding-timeout-A",
        invocation_id="invocation-timeout-A",
        tool_use_id="tool-timeout-A",
        delegation_id="delegation-timeout-A",
        child_identity_sha256="c" * 64,
    )


@unittest.skipUnless(CANONICAL_ROOT is not None, "exact canonical EntityOS checkout required")
class BoundEntityOSPostStartTimeoutTests(unittest.TestCase):
    """Freeze the current post-start timeout mismatch without executing a real effect."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = UnifiedDB(Path(self.tmp.name) / "unified.db")
        self.user_id = "user-timeout-A"
        self.db.ensure_user(self.user_id, "Timeout User")
        self.session_id = self.db.ensure_session(self.user_id, "terminal-timeout-A")
        self.generation = self.db.session_generation(self.session_id)
        self.argv = ("deterministic-timeout-stub", "payload-timeout-A")
        self.context = EntityOSEffectCallContext(
            user_id=self.user_id,
            session_id=self.session_id,
            generation=self.generation,
            argv=self.argv,
        )
        self.intent = attach_entityos_request_identity(call_intent(), self.context)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def _effect_rows(self):
        return [
            dict(row)
            for row in self.db.db.execute(
                "SELECT effect_id,user_id,capability,target,argv,requested_generation,status "
                "FROM effects ORDER BY ts,effect_id"
            ).fetchall()
        ]

    def _request(self):
        semantic = self.intent.request
        assert semantic is not None
        return EffectRequest(
            user_id=semantic.user_id,
            session_id=semantic.session_id,
            capability=semantic.capability,
            target=semantic.target,
            argv=list(semantic.argv) if semantic.argv is not None else None,
            expected_generation=semantic.expected_generation,
        )

    def test_post_start_timeout_is_unknown_at_interlock_but_failed_in_bound_journal(self) -> None:
        """NEGATIVE_RESULT: a timeout after executor entry must not become a negative world fact.

        The F2 interlock correctly promotes the timeout to ExecutorOutcomeUnknown. The
        exact-bound canonical EffectGate currently catches that bridge exception and writes
        FAILED. The marker proves executor entry occurred before TimeoutExpired; the test is
        therefore a deterministic falsifier for the missing live-UNKNOWN finalization path.
        """
        test_case = self
        marker = {"executor_entered": 0}

        class PostStartTimeoutBridge:
            sha256 = "9" * 64
            executor_calls = 0

            def run(self, argv):
                pending = bind_unique_pending_entityos_effect(
                    test_case.intent,
                    test_case.context,
                    test_case._effect_rows(),
                )

                def executor(_prepared):
                    self.executor_calls += 1
                    marker["executor_entered"] += 1
                    raise subprocess.TimeoutExpired(cmd=list(argv), timeout=0.25)

                return dispatch_through_external_gate(
                    pending.prepared,
                    authorize=lambda _prepared: pending.gate,
                    executor=executor,
                )

        bridge = PostStartTimeoutBridge()
        with self.assertRaises(ExecutorOutcomeUnknown) as caught:
            EffectGate(self.db, entityos_bridge=bridge).execute(self._request())

        self.assertEqual(bridge.executor_calls, 1)
        self.assertEqual(marker["executor_entered"], 1)
        self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)

        row = self.db.db.execute(
            "SELECT status,outcome FROM effects ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertIn("ExecutorOutcomeUnknown", row["outcome"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
