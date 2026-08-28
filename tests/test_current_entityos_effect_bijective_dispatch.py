from __future__ import annotations

import sqlite3
import tempfile
import unittest

from frankenstein2.canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityEvidence,
    EffectCallIntent,
)
from frankenstein2.current_entityos_effect_authority_binding import (
    CurrentEntityOSEffectAuthorityBinding,
    dispatch_with_current_entityos_authority_bijective,
)
from frankenstein2.effect_executor_interlock import ExecutorObservation, ExternalGateDecision
from frankenstein2.effect_invocation_bijection import (
    EffectInvocationBijectionError,
    initialize_effect_invocation_bijection,
    verify_effect_invocation,
)
from frankenstein2.effect_request_identity import EffectRequestIdentity


RESULT_SHA = "c" * 64


def current_binding() -> CurrentEntityOSEffectAuthorityBinding:
    return CurrentEntityOSEffectAuthorityBinding(
        binding_repository="gschaidergabriel/clay-global-research-entity",
        binding_record_path="research_entity/continuity/binding.json",
        binding_record_blob_sha="1" * 40,
        binding_record_commit_sha="2" * 40,
        current_epoch_attestation_path="research_entity/continuity/attestation.json",
        current_epoch_attestation_commit_sha="3" * 40,
        implementation_commit_sha="4" * 40,
        effect_gate_path="the artefact/clayverse/effects.py",
        effect_gate_blob_sha="5" * 40,
        effect_journal_path="the artefact/clayverse/effect_journal.py",
        effect_journal_blob_sha="6" * 40,
        unifieddb_path="the artefact/clayverse/store.py",
        unifieddb_blob_sha="7" * 40,
        unifieddb_schema_version="6",
        api_version="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
        supervisor_epoch="9.13",
        supervisor_delta="9.13AL_NON_AUTHORITY",
    )


def request(suffix: str) -> EffectRequestIdentity:
    return EffectRequestIdentity(
        user_id="user-1",
        session_id="shared-session",
        capability="entityos.exec",
        target=f"target-{suffix}",
        argv=("run", f"payload-{suffix}"),
        expected_generation=7,
    )


def intent(suffix: str) -> EffectCallIntent:
    return EffectCallIntent(
        return_id=None,
        binding_id=f"binding-{suffix}",
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child_identity_sha256=("a" if suffix == "A" else "b") * 64,
        request=request(suffix),
    )


def evidence_for(
    call: EffectCallIntent,
    binding: CurrentEntityOSEffectAuthorityBinding,
    *,
    effect_id: str | None,
    decision: ExternalGateDecision = ExternalGateDecision.ALLOW,
) -> CanonicalEffectAuthorityEvidence:
    return CanonicalEffectAuthorityEvidence(
        authority=binding.bridge_identity(),
        decision_id=f"decision-{call.invocation_id}-{decision.value}",
        decision=decision,
        journal_state="PENDING" if decision is ExternalGateDecision.ALLOW else "NO_EFFECT",
        effect_id=effect_id,
        return_id=call.return_id,
        binding_id=call.binding_id,
        invocation_id=call.invocation_id,
        tool_use_id=call.tool_use_id,
        delegation_id=call.delegation_id,
        child_identity_sha256=call.child_identity_sha256,
        request_sha256=call.request_sha256,
    )


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, prepared):
        self.calls.append(prepared)
        return ExecutorObservation(
            effect_id=prepared.effect_id,
            binding_id=prepared.binding_id,
            invocation_id=prepared.invocation_id,
            tool_use_id=prepared.tool_use_id,
            delegation_id=prepared.delegation_id,
            child_identity_sha256=prepared.child_identity_sha256,
            result_id=f"result-{prepared.invocation_id}",
            result_sha256=RESULT_SHA,
            request_sha256=prepared.request_sha256,
        )


class CurrentEntityOSBijectiveDispatchTests(unittest.TestCase):
    def new_connection(self):
        conn = sqlite3.connect(":memory:")
        initialize_effect_invocation_bijection(conn)
        conn.commit()
        return conn

    def test_overlapping_calls_cannot_share_one_canonical_effect(self) -> None:
        conn = self.new_connection()
        binding = current_binding()
        executor = RecordingExecutor()
        a = intent("A")
        b = intent("B")
        try:
            first = dispatch_with_current_entityos_authority_bijective(
                a,
                binding=binding,
                authorize=lambda call: evidence_for(
                    call, binding, effect_id="canonical-effect-shared"
                ),
                executor=executor,
                bijection_connection=conn,
            )
            self.assertTrue(first.dispatched)
            with self.assertRaisesRegex(
                EffectInvocationBijectionError,
                "EFFECT_ID_REBOUND_TO_DIFFERENT_CALL",
            ):
                dispatch_with_current_entityos_authority_bijective(
                    b,
                    binding=binding,
                    authorize=lambda call: evidence_for(
                        call, binding, effect_id="canonical-effect-shared"
                    ),
                    executor=executor,
                    bijection_connection=conn,
                )
            self.assertEqual(
                [call.invocation_id for call in executor.calls],
                ["invocation-A"],
            )
        finally:
            conn.close()

    def test_binding_is_committed_before_executor_entry(self) -> None:
        binding = current_binding()
        call = intent("A")
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as tmp:
            conn = sqlite3.connect(tmp.name)
            initialize_effect_invocation_bijection(conn)
            conn.commit()
            executor_calls = []

            def executor(prepared):
                observer = sqlite3.connect(tmp.name)
                try:
                    visible = verify_effect_invocation(
                        observer,
                        call_id=prepared.invocation_id,
                        effect_id=prepared.effect_id,
                        binding_id=prepared.binding_id,
                        generation=7,
                    )
                finally:
                    observer.close()
                executor_calls.append(visible)
                return ExecutorObservation(
                    effect_id=prepared.effect_id,
                    binding_id=prepared.binding_id,
                    invocation_id=prepared.invocation_id,
                    tool_use_id=prepared.tool_use_id,
                    delegation_id=prepared.delegation_id,
                    child_identity_sha256=prepared.child_identity_sha256,
                    result_id="result-A",
                    result_sha256=RESULT_SHA,
                    request_sha256=prepared.request_sha256,
                )

            try:
                result = dispatch_with_current_entityos_authority_bijective(
                    call,
                    binding=binding,
                    authorize=lambda item: evidence_for(
                        item, binding, effect_id="canonical-effect-A"
                    ),
                    executor=executor,
                    bijection_connection=conn,
                )
                self.assertTrue(result.dispatched)
                self.assertEqual(len(executor_calls), 1)
                self.assertEqual(executor_calls[0].call_id, "invocation-A")
                self.assertEqual(executor_calls[0].effect_id, "canonical-effect-A")
            finally:
                conn.close()

    def test_missing_bijection_schema_fails_before_authority_and_executor(self) -> None:
        conn = sqlite3.connect(":memory:")
        binding = current_binding()
        authority_calls = []
        executor = RecordingExecutor()
        try:
            with self.assertRaisesRegex(
                EffectInvocationBijectionError,
                "BIJECTION_SCHEMA_NOT_INITIALIZED",
            ):
                dispatch_with_current_entityos_authority_bijective(
                    intent("A"),
                    binding=binding,
                    authorize=lambda call: authority_calls.append(call),
                    executor=executor,
                    bijection_connection=conn,
                )
            self.assertEqual(authority_calls, [])
            self.assertEqual(executor.calls, [])
        finally:
            conn.close()

    def test_preexisting_transaction_fails_before_authority_and_executor(self) -> None:
        conn = self.new_connection()
        binding = current_binding()
        authority_calls = []
        executor = RecordingExecutor()
        try:
            conn.execute("BEGIN")
            with self.assertRaisesRegex(
                EffectInvocationBijectionError,
                "PREEXISTING_TRANSACTION_FORBIDDEN",
            ):
                dispatch_with_current_entityos_authority_bijective(
                    intent("A"),
                    binding=binding,
                    authorize=lambda call: authority_calls.append(call),
                    executor=executor,
                    bijection_connection=conn,
                )
            self.assertEqual(authority_calls, [])
            self.assertEqual(executor.calls, [])
        finally:
            conn.rollback()
            conn.close()

    def test_non_allow_never_creates_bijection_or_dispatches(self) -> None:
        conn = self.new_connection()
        binding = current_binding()
        executor = RecordingExecutor()
        try:
            result = dispatch_with_current_entityos_authority_bijective(
                intent("A"),
                binding=binding,
                authorize=lambda call: evidence_for(
                    call,
                    binding,
                    effect_id=None,
                    decision=ExternalGateDecision.DENY,
                ),
                executor=executor,
                bijection_connection=conn,
            )
            self.assertFalse(result.dispatched)
            self.assertEqual(executor.calls, [])
            count = conn.execute("SELECT COUNT(*) FROM effect_invocation_bijection").fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
