from __future__ import annotations

from dataclasses import replace
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.canonical_effect_authority_bridge import EffectCallIntent
from frankenstein2.effect_executor_interlock import (
    ExecutorInterlockError,
    ExecutorOutcomeUnknown,
    dispatch_through_external_gate,
)
from frankenstein2.effect_invocation_correlation import EffectCorrelationStage
from frankenstein2.entityos_effect_gate_call_bridge import (
    EntityOSEffectCallContext,
    attach_entityos_request_identity,
    bind_unique_pending_entityos_effect,
)
from frankenstein2.entityos_unknown_outcome_adapter import (
    translate_executor_unknown_to_canonical,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "entityos_effect_unknown_pr430_2f99"
    / "clayverse"
)
BOUND_STORE = (
    Path(__file__).parent
    / "fixtures"
    / "entityos_effect_authority_2b68"
    / "clayverse"
    / "store.py"
)


class PR430F2InterlockUnknownIntegrationTests(unittest.TestCase):
    """Source-bound, no-real-effect proof for the F2 -> PR430 UNKNOWN ABI seam."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        package = cls.root / "pr430_clayverse_integration"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        for name in ("effects.py", "effect_journal.py", "entityos_bridge.py"):
            shutil.copyfile(FIXTURE / name, package / name)
        shutil.copyfile(BOUND_STORE, package / "store.py")
        sys.path.insert(0, str(cls.root))
        cls.effects = importlib.import_module("pr430_clayverse_integration.effects")
        cls.bridge_module = importlib.import_module(
            "pr430_clayverse_integration.entityos_bridge"
        )
        cls.store_module = importlib.import_module("pr430_clayverse_integration.store")

    @classmethod
    def tearDownClass(cls) -> None:
        sys.path.remove(str(cls.root))
        for name in list(sys.modules):
            if name == "pr430_clayverse_integration" or name.startswith(
                "pr430_clayverse_integration."
            ):
                sys.modules.pop(name, None)
        cls.temp.cleanup()

    def setUp(self) -> None:
        self.db_temp = tempfile.TemporaryDirectory()
        self.db = self.store_module.UnifiedDB(Path(self.db_temp.name) / "unified.db")
        self.user_id = "pr430-f2-integration-user"
        self.db.ensure_user(self.user_id, "PR430 F2 Integration User")
        self.session_id = self.db.ensure_session(
            self.user_id, "pr430-f2-integration-session"
        )
        self.generation = self.db.session_generation(self.session_id)

    def tearDown(self) -> None:
        self.db.close()
        self.db_temp.cleanup()

    def _effect_rows(self):
        return [
            dict(row)
            for row in self.db.db.execute(
                "SELECT effect_id,user_id,capability,target,argv,requested_generation,status "
                "FROM effects ORDER BY ts,effect_id"
            ).fetchall()
        ]

    def _latest_effect(self):
        return self.db.db.execute(
            "SELECT effect_id,status,outcome FROM effects "
            "ORDER BY ts DESC,effect_id DESC LIMIT 1"
        ).fetchone()

    def _bound_request(self, suffix: str):
        context = EntityOSEffectCallContext(
            user_id=self.user_id,
            session_id=self.session_id,
            generation=self.generation,
            argv=("deterministic-no-real-effect-stub", f"payload-{suffix}"),
        )
        intent = attach_entityos_request_identity(
            EffectCallIntent(
                return_id=None,
                binding_id=f"binding-{suffix}",
                invocation_id=f"invocation-{suffix}",
                tool_use_id=f"tool-{suffix}",
                delegation_id=f"delegation-{suffix}",
                child_identity_sha256="d" * 64,
            ),
            context,
        )
        semantic = intent.request
        assert semantic is not None
        request = self.effects.EffectRequest(
            user_id=semantic.user_id,
            session_id=semantic.session_id,
            capability=semantic.capability,
            target=semantic.target,
            argv=list(semantic.argv) if semantic.argv is not None else None,
            expected_generation=semantic.expected_generation,
        )
        return intent, context, request

    def _assert_post_dispatch_error_becomes_unknown(
        self,
        suffix: str,
        executor_error: Exception,
    ) -> None:
        candidate_unknown = self.bridge_module.EntityOSOutcomeUnknown
        intent, context, request = self._bound_request(suffix)
        test_case = self
        marker: dict[str, object] = {"executor_calls": 0}

        class AdaptedF2Bridge:
            sha256 = "e" * 64
            pending_effect_id: str | None = None
            pending_request_sha256: str | None = None

            def run(self, argv):
                test_case.assertEqual(tuple(argv), context.argv)
                pending = bind_unique_pending_entityos_effect(
                    intent,
                    context,
                    test_case._effect_rows(),
                )
                self.pending_effect_id = pending.effect_id
                assert pending.prepared.request is not None
                self.pending_request_sha256 = pending.prepared.request.sha256()
                test_case.assertEqual(
                    self.pending_request_sha256,
                    intent.request_sha256,
                )
                test_case.assertEqual(
                    pending.gate.request_sha256,
                    intent.request_sha256,
                )

                def executor(prepared):
                    marker["executor_calls"] = int(marker["executor_calls"]) + 1
                    marker["effect_id"] = prepared.effect_id
                    marker["binding_id"] = prepared.binding_id
                    marker["request_sha256"] = prepared.request.sha256()
                    raise executor_error

                def dispatch():
                    return dispatch_through_external_gate(
                        pending.prepared,
                        authorize=lambda _prepared: pending.gate,
                        executor=executor,
                    )

                return translate_executor_unknown_to_canonical(
                    dispatch,
                    canonical_unknown_type=candidate_unknown,
                )

        bridge = AdaptedF2Bridge()
        gate = self.effects.EffectGate(self.db, entityos_bridge=bridge)
        with self.assertRaises(candidate_unknown) as caught:
            gate.execute(request)

        self.assertFalse(caught.exception.replay_permitted)
        self.assertIsInstance(caught.exception.__cause__, ExecutorOutcomeUnknown)
        self.assertIs(caught.exception.__cause__.__cause__, executor_error)
        self.assertEqual(marker["executor_calls"], 1)
        self.assertEqual(marker["effect_id"], bridge.pending_effect_id)
        self.assertEqual(marker["binding_id"], intent.binding_id)
        self.assertEqual(marker["request_sha256"], intent.request_sha256)

        row = self._latest_effect()
        self.assertEqual(row["effect_id"], bridge.pending_effect_id)
        self.assertEqual(row["status"], "UNKNOWN_OUTCOME")
        receipt = json.loads(row["outcome"])
        self.assertEqual(receipt["certainty"], "unknown")
        self.assertEqual(receipt["error"], "EntityOSOutcomeUnknown")
        self.assertEqual(receipt["reason"], "entityos_outcome_unknown")
        self.assertNotIn("ok", receipt)

        causal = self.db.db.execute(
            "SELECT credit,reentered FROM causal_episodes WHERE effect_id=?",
            (row["effect_id"],),
        ).fetchone()
        self.assertEqual(causal["credit"], 0.0)
        self.assertEqual(causal["reentered"], 1)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM effects").fetchone()[0], 1)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)

    def test_poststart_timeout_crosses_f2_interlock_then_terminalizes_unknown(self) -> None:
        self._assert_post_dispatch_error_becomes_unknown(
            "timeout",
            subprocess.TimeoutExpired(cmd=["deterministic-stub"], timeout=0.25),
        )

    def test_poststart_ordinary_error_crosses_f2_interlock_then_terminalizes_unknown(self) -> None:
        self._assert_post_dispatch_error_becomes_unknown(
            "ordinary-error",
            OSError("result channel lost after executor entry"),
        )

    def test_predispatch_interlock_failure_remains_failed_and_never_executes(self) -> None:
        candidate_unknown = self.bridge_module.EntityOSOutcomeUnknown
        intent, context, request = self._bound_request("predispatch")
        test_case = self
        marker = {"executor_calls": 0}

        class PredispatchFailureBridge:
            sha256 = "f" * 64

            def run(self, argv):
                test_case.assertEqual(tuple(argv), context.argv)
                pending = bind_unique_pending_entityos_effect(
                    intent,
                    context,
                    test_case._effect_rows(),
                )
                already_observed = replace(
                    pending.prepared,
                    stage=EffectCorrelationStage.RESULT_OBSERVED,
                    result_id="synthetic-result-never-dispatched",
                    result_sha256="a" * 64,
                )

                def executor(_prepared):
                    marker["executor_calls"] += 1
                    raise AssertionError("predispatch failure must not execute")

                def dispatch():
                    return dispatch_through_external_gate(
                        already_observed,
                        authorize=lambda _prepared: pending.gate,
                        executor=executor,
                    )

                return translate_executor_unknown_to_canonical(
                    dispatch,
                    canonical_unknown_type=candidate_unknown,
                )

        gate = self.effects.EffectGate(
            self.db,
            entityos_bridge=PredispatchFailureBridge(),
        )
        with self.assertRaises(ExecutorInterlockError):
            gate.execute(request)

        self.assertEqual(marker["executor_calls"], 0)
        row = self._latest_effect()
        self.assertEqual(row["status"], "FAILED")
        receipt = json.loads(row["outcome"])
        self.assertEqual(receipt["error"], "ExecutorInterlockError")
        self.assertEqual(receipt["reason"], "entityos_execution_failure")
        self.assertNotEqual(row["status"], "UNKNOWN_OUTCOME")
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM effects").fetchone()[0], 1)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
