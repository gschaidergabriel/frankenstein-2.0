from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.canonical_effect_authority_bridge import EffectCallIntent
from frankenstein2.effect_executor_interlock import (
    ExecutorObservation,
    ExecutorOutcomeUnknown,
    dispatch_through_external_gate,
)
from frankenstein2.entityos_effect_authority_binding import (
    CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING,
    EntityOSEffectAuthorityBindingError,
    validate_current_binding_document,
)
from frankenstein2.entityos_effect_gate_call_bridge import (
    EntityOSEffectCallContext,
    EntityOSEffectGateCallBridgeError,
    attach_entityos_request_identity,
    bind_unique_pending_entityos_effect,
)


CANONICAL_ROOT_RAW = os.environ.get("ENTITYOS_CANONICAL_ROOT")
CANONICAL_ROOT = Path(CANONICAL_ROOT_RAW).resolve() if CANONICAL_ROOT_RAW else None
if CANONICAL_ROOT is not None:
    sys.path.insert(0, str(CANONICAL_ROOT / "the artefact"))
    from clayverse.effects import EffectGate, EffectRequest  # type: ignore[import-not-found]
    from clayverse.store import UnifiedDB  # type: ignore[import-not-found]
else:  # pragma: no cover - dedicated CI always supplies the exact canonical checkout.
    EffectGate = EffectRequest = UnifiedDB = None  # type: ignore[assignment]


BINDING = CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING


def call_intent(*, suffix: str = "A") -> EffectCallIntent:
    return EffectCallIntent(
        return_id=None,
        binding_id=f"binding-{suffix}",
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child_identity_sha256=("a" if suffix == "A" else "b") * 64,
    )


def git_blob(path: str) -> str:
    assert CANONICAL_ROOT is not None
    return subprocess.check_output(
        ["git", "-C", str(CANONICAL_ROOT), "rev-parse", f"HEAD:{path}"],
        text=True,
    ).strip()


@unittest.skipUnless(CANONICAL_ROOT is not None, "exact canonical EntityOS checkout required")
class BoundEntityOSEffectAuthorityMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        assert CANONICAL_ROOT is not None
        self.tmp = tempfile.TemporaryDirectory()
        self.db = UnifiedDB(Path(self.tmp.name) / "unified.db")
        self.user_id = "user-A"
        self.db.ensure_user(self.user_id, "User A")
        self.session_id = self.db.ensure_session(self.user_id, "terminal-A")
        self.generation = self.db.session_generation(self.session_id)
        self.argv = ("deterministic-stub", "payload-A")
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

    def _request(self, *, capability: str | None = None):
        semantic = self.intent.request
        assert semantic is not None
        return EffectRequest(
            user_id=semantic.user_id,
            session_id=semantic.session_id,
            capability=capability or semantic.capability,
            target=semantic.target,
            argv=list(semantic.argv) if semantic.argv is not None else None,
            expected_generation=semantic.expected_generation,
        )

    def test_exact_external_binding_document_and_all_bound_blobs_match(self) -> None:
        assert CANONICAL_ROOT is not None
        binding_path = CANONICAL_ROOT / BINDING.binding_path
        document = json.loads(binding_path.read_text(encoding="utf-8"))
        self.assertEqual(validate_current_binding_document(document), BINDING)
        self.assertEqual(git_blob(BINDING.binding_path), BINDING.binding_blob_sha)
        self.assertEqual(git_blob(BINDING.effect_gate_path), BINDING.effect_gate_blob_sha)
        self.assertEqual(
            git_blob(BINDING.effect_journal_path), BINDING.effect_journal_blob_sha
        )
        self.assertEqual(git_blob(BINDING.unified_db_path), BINDING.unified_db_blob_sha)
        self.assertEqual(
            document["implementation_identity"]["bound_commit"],
            BINDING.implementation_commit,
        )

    def test_any_bound_source_identity_change_fails_closed(self) -> None:
        assert CANONICAL_ROOT is not None
        document = json.loads((CANONICAL_ROOT / BINDING.binding_path).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(document)
        mutated["implementation_identity"]["effect_journal"]["blob_sha"] = "0" * 40
        with self.assertRaisesRegex(
            EntityOSEffectAuthorityBindingError,
            "EFFECT_JOURNAL_BLOB_SHA_MISMATCH",
        ):
            validate_current_binding_document(mutated)

    def test_pending_row_binds_exact_call_and_semantic_request_before_stub_executor_runs(self) -> None:
        test_case = self

        class CorrelatingBridge:
            sha256 = "d" * 64

            def __init__(self):
                self.calls = 0
                self.pending = None
                self.interlock = None

            def run(self, argv):
                self.calls += 1
                test_case.assertEqual(tuple(argv), test_case.argv)
                self.pending = bind_unique_pending_entityos_effect(
                    test_case.intent,
                    test_case.context,
                    test_case._effect_rows(),
                )
                test_case.assertEqual(
                    self.pending.prepared.request_sha256,
                    test_case.intent.request_sha256,
                )
                test_case.assertEqual(
                    self.pending.gate.request_sha256,
                    test_case.intent.request_sha256,
                )

                def executor(prepared):
                    test_case.assertEqual(prepared.effect_id, self.pending.effect_id)
                    test_case.assertEqual(
                        prepared.request_sha256,
                        test_case.intent.request_sha256,
                    )
                    digest = hashlib.sha256(
                        json.dumps(list(argv), separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                    return ExecutorObservation(
                        effect_id=prepared.effect_id,
                        binding_id=prepared.binding_id,
                        invocation_id=prepared.invocation_id,
                        tool_use_id=prepared.tool_use_id,
                        delegation_id=prepared.delegation_id,
                        child_identity_sha256=prepared.child_identity_sha256,
                        result_id="stub-result-A",
                        result_sha256=digest,
                        request_sha256=prepared.request_sha256,
                    )

                self.interlock = dispatch_through_external_gate(
                    self.pending.prepared,
                    authorize=lambda _prepared: self.pending.gate,
                    executor=executor,
                )
                test_case.assertTrue(self.interlock.dispatched)
                test_case.assertEqual(
                    self.interlock.observed.request_sha256,
                    test_case.intent.request_sha256,
                )
                return {"ok": True, "exit": 0}

        bridge = CorrelatingBridge()
        effect_id, outcome = EffectGate(self.db, entityos_bridge=bridge).execute(self._request())
        self.assertEqual(bridge.calls, 1)
        self.assertIsNotNone(bridge.pending)
        self.assertEqual(bridge.pending.effect_id, effect_id)
        self.assertTrue(outcome["ok"])
        row = self.db.db.execute(
            "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertEqual(row["status"], "VERIFIED")

    def test_same_session_ab_pending_bijection_survives_reverse_binding_order(self) -> None:
        context_b = EntityOSEffectCallContext(
            user_id=self.user_id,
            session_id=self.session_id,
            generation=self.generation,
            argv=("deterministic-stub", "payload-B"),
        )
        intent_b = attach_entityos_request_identity(call_intent(suffix="B"), context_b)
        request_a = self.intent.request
        request_b = intent_b.request
        assert request_a is not None and request_b is not None
        gate = EffectGate(self.db)
        effect_a = gate.journal.begin(
            None,
            self.session_id,
            self.user_id,
            "entityos.exec",
            request_a.target,
            self.generation,
            list(request_a.argv or ()),
        )
        effect_b = gate.journal.begin(
            None,
            self.session_id,
            self.user_id,
            "entityos.exec",
            request_b.target,
            self.generation,
            list(request_b.argv or ()),
        )
        rows = self._effect_rows()

        # Bind B then A deliberately. No row order/timestamp heuristic is allowed.
        bound_b = bind_unique_pending_entityos_effect(intent_b, context_b, rows)
        bound_a = bind_unique_pending_entityos_effect(self.intent, self.context, rows)
        self.assertEqual(bound_b.effect_id, effect_b)
        self.assertEqual(bound_a.effect_id, effect_a)
        self.assertEqual(bound_b.prepared.request_sha256, intent_b.request_sha256)
        self.assertEqual(bound_a.prepared.request_sha256, self.intent.request_sha256)
        self.assertNotEqual(bound_a.prepared.request_sha256, bound_b.prepared.request_sha256)
        self.assertNotEqual(bound_a.effect_id, bound_b.effect_id)

    def test_semantic_request_substitution_fails_before_pending_binding(self) -> None:
        semantic = self.intent.request
        assert semantic is not None
        substituted = replace(
            self.intent,
            request=replace(semantic, argv=("deterministic-stub", "payload-B")),
        )
        gate = EffectGate(self.db)
        gate.journal.begin(
            None,
            self.session_id,
            self.user_id,
            "entityos.exec",
            semantic.target,
            self.generation,
            list(self.argv),
        )
        with self.assertRaisesRegex(
            EntityOSEffectGateCallBridgeError,
            "SEMANTIC_EFFECT_REQUEST_MISMATCH",
        ):
            bind_unique_pending_entityos_effect(
                substituted,
                self.context,
                self._effect_rows(),
            )

    def test_duplicate_identical_pending_rows_fail_closed_not_latest_row_wins(self) -> None:
        semantic = self.intent.request
        assert semantic is not None
        gate = EffectGate(self.db)
        for _ in range(2):
            gate.journal.begin(
                None,
                self.session_id,
                self.user_id,
                "entityos.exec",
                semantic.target,
                self.generation,
                list(self.argv),
            )
        with self.assertRaisesRegex(
            EntityOSEffectGateCallBridgeError,
            "AMBIGUOUS_EXACT_PENDING_EFFECT",
        ):
            bind_unique_pending_entityos_effect(
                self.intent,
                self.context,
                self._effect_rows(),
            )

    def test_direct_process_deny_has_zero_bridge_dispatch_and_zero_effect_rows(self) -> None:
        class NeverBridge:
            sha256 = "e" * 64
            calls = 0

            def run(self, argv):
                self.calls += 1
                raise AssertionError("must not dispatch")

        bridge = NeverBridge()
        with self.assertRaisesRegex(PermissionError, "direct host process execution forbidden"):
            EffectGate(self.db, entityos_bridge=bridge).execute(
                self._request(capability="process.exec")
            )
        self.assertEqual(bridge.calls, 0)
        self.assertEqual(
            self.db.db.execute("SELECT COUNT(*) FROM effects").fetchone()[0],
            0,
        )

    def test_restart_recovery_preserves_pending_as_unknown_without_replay(self) -> None:
        semantic = self.intent.request
        assert semantic is not None
        gate = EffectGate(self.db)
        effect_id = gate.journal.begin(
            None,
            self.session_id,
            self.user_id,
            "entityos.exec",
            semantic.target,
            self.generation,
            list(self.argv),
        )
        self.assertEqual(
            self.db.db.execute(
                "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
            ).fetchone()[0],
            "PENDING",
        )
        self.assertEqual(gate.journal.recover_pending(), 1)
        row = self.db.db.execute(
            "SELECT status,outcome FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertEqual(row["status"], "UNKNOWN_AFTER_RESTART")
        self.assertIn("restart_before_verified_outcome", row["outcome"])

    def test_live_ambiguous_executor_exception_is_currently_collapsed_to_failed(self) -> None:
        """NEGATIVE_RESULT: this is the remaining canonical integration blocker.

        F2 correctly reports a possibly-started executor exception as
        ExecutorOutcomeUnknown. The currently bound EffectGate catches every bridge
        exception and finalizes the journal as FAILED. This test intentionally freezes
        that observed mismatch until the canonical effect authority gains an explicit
        live-UNKNOWN finalization contract; a future fix must change this assertion.
        """
        test_case = self

        class AmbiguousBridge:
            sha256 = "f" * 64
            executor_calls = 0

            def run(self, argv):
                pending = bind_unique_pending_entityos_effect(
                    test_case.intent,
                    test_case.context,
                    test_case._effect_rows(),
                )

                def executor(_prepared):
                    self.executor_calls += 1
                    raise RuntimeError("transport lost after possible submission")

                return dispatch_through_external_gate(
                    pending.prepared,
                    authorize=lambda _prepared: pending.gate,
                    executor=executor,
                )

        bridge = AmbiguousBridge()
        with self.assertRaises(ExecutorOutcomeUnknown):
            EffectGate(self.db, entityos_bridge=bridge).execute(self._request())
        self.assertEqual(bridge.executor_calls, 1)
        row = self.db.db.execute(
            "SELECT status,outcome FROM effects ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertIn("ExecutorOutcomeUnknown", row["outcome"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
