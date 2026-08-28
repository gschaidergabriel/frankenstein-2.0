from __future__ import annotations

import unittest

from frankenstein2.canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityEvidence,
    CanonicalEffectAuthorityIdentity,
    EffectCallIntent,
)
from frankenstein2.effect_executor_interlock import (
    ExecutorObservation,
    ExecutorOutcomeUnknown,
    ExternalGateDecision,
)
from frankenstein2.semantic_effect_request import (
    SemanticCanonicalEffectAuthorityEvidence,
    SemanticEffectCallIntent,
    SemanticEffectRequest,
    SemanticEffectRequestError,
    SemanticExecutorRequest,
    dispatch_semantic_with_canonical_authority,
)


AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="example/canonical-authority",
    commit_sha="1" * 40,
    module_path="entityos/effects.py",
    source_blob_sha="2" * 40,
    state_schema="UnifiedDB/schema_version=6",
    api_version="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
)
CHILD_A = "a" * 64
CHILD_B = "b" * 64
RESULT_SHA = "c" * 64


def call(suffix: str) -> EffectCallIntent:
    return EffectCallIntent(
        return_id=None,
        binding_id=f"binding-{suffix}",
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child_identity_sha256=CHILD_A if suffix == "A" else CHILD_B,
    )


def request(*, target: str = "repo/file.txt", argv: tuple[str, ...] = ("write", "x")):
    return SemanticEffectRequest(
        user_id="user-1",
        session_id="session-1",
        capability="entityos.exec",
        target=target,
        argv=argv,
        expected_generation=7,
    )


def authority_for(
    intent: SemanticEffectCallIntent,
    decision: ExternalGateDecision,
    *,
    digest: str | None = None,
) -> SemanticCanonicalEffectAuthorityEvidence:
    effect_id = "effect-A" if decision is ExternalGateDecision.ALLOW else None
    journal_state = "PENDING" if decision is ExternalGateDecision.ALLOW else "NO_EFFECT"
    evidence = CanonicalEffectAuthorityEvidence(
        authority=AUTHORITY,
        decision_id=f"decision-{decision.value}",
        decision=decision,
        journal_state=journal_state,
        effect_id=effect_id,
        return_id=intent.call.return_id,
        binding_id=intent.call.binding_id,
        invocation_id=intent.call.invocation_id,
        tool_use_id=intent.call.tool_use_id,
        delegation_id=intent.call.delegation_id,
        child_identity_sha256=intent.call.child_identity_sha256,
    )
    return SemanticCanonicalEffectAuthorityEvidence(
        authority=evidence,
        effect_request_sha256=digest or intent.request_sha256,
    )


class RecordingSemanticExecutor:
    def __init__(self) -> None:
        self.calls: list[SemanticExecutorRequest] = []

    def __call__(self, semantic: SemanticExecutorRequest) -> ExecutorObservation:
        self.calls.append(semantic)
        prepared = semantic.prepared
        return ExecutorObservation(
            effect_id=prepared.effect_id,
            binding_id=prepared.binding_id,
            invocation_id=prepared.invocation_id,
            tool_use_id=prepared.tool_use_id,
            delegation_id=prepared.delegation_id,
            child_identity_sha256=prepared.child_identity_sha256,
            result_id=f"result-{prepared.tool_use_id}",
            result_sha256=RESULT_SHA,
        )


class SemanticEffectRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.intent = SemanticEffectCallIntent(call=call("A"), request=request())

    def dispatch(self, authorize, executor):
        return dispatch_semantic_with_canonical_authority(
            self.intent,
            expected_authority=AUTHORITY,
            authorize=authorize,
            executor=executor,
        )

    def test_digest_is_stable_and_semantic_field_sensitive(self) -> None:
        same = request()
        different_target = request(target="repo/other.txt")
        different_argv = request(argv=("write", "y"))
        self.assertEqual(self.intent.request_sha256, same.request_sha256())
        self.assertNotEqual(self.intent.request_sha256, different_target.request_sha256())
        self.assertNotEqual(self.intent.request_sha256, different_argv.request_sha256())

    def test_allow_dispatches_exact_semantic_request_once(self) -> None:
        executor = RecordingSemanticExecutor()
        result = self.dispatch(
            lambda intent: authority_for(intent, ExternalGateDecision.ALLOW),
            executor,
        )
        self.assertTrue(result.dispatched)
        self.assertEqual(len(executor.calls), 1)
        observed = executor.calls[0]
        self.assertEqual(observed.request, self.intent.request)
        self.assertEqual(observed.effect_request_sha256, self.intent.request_sha256)
        self.assertEqual(observed.prepared.effect_id, "effect-A")

    def test_authority_digest_mismatch_stops_before_executor(self) -> None:
        executor = RecordingSemanticExecutor()
        substituted = request(target="repo/substituted.txt").request_sha256()
        with self.assertRaisesRegex(
            SemanticEffectRequestError,
            "EFFECT_REQUEST_SHA256_MISMATCH",
        ):
            self.dispatch(
                lambda intent: authority_for(
                    intent,
                    ExternalGateDecision.ALLOW,
                    digest=substituted,
                ),
                executor,
            )
        self.assertEqual(executor.calls, [])

    def test_same_call_identity_cannot_authorize_different_semantics(self) -> None:
        executor = RecordingSemanticExecutor()
        authorized_request = request(target="repo/authorized.txt")
        authorized_digest = authorized_request.request_sha256()
        with self.assertRaisesRegex(
            SemanticEffectRequestError,
            "EFFECT_REQUEST_SHA256_MISMATCH",
        ):
            self.dispatch(
                lambda intent: authority_for(
                    intent,
                    ExternalGateDecision.ALLOW,
                    digest=authorized_digest,
                ),
                executor,
            )
        self.assertEqual(executor.calls, [])

    def test_every_non_allow_decision_dispatches_zero_times(self) -> None:
        for decision in (
            ExternalGateDecision.DENY,
            ExternalGateDecision.REQUIRE_CONFIRMATION,
            ExternalGateDecision.DEGRADE_TO_PROPOSAL,
            ExternalGateDecision.UNKNOWN,
        ):
            with self.subTest(decision=decision.value):
                executor = RecordingSemanticExecutor()
                result = self.dispatch(
                    lambda intent, d=decision: authority_for(intent, d),
                    executor,
                )
                self.assertFalse(result.dispatched)
                self.assertIsNone(result.interlock)
                self.assertEqual(executor.calls, [])

    def test_executor_input_rejects_digest_not_matching_payload(self) -> None:
        executor = RecordingSemanticExecutor()
        wrong_digest = request(target="repo/other.txt").request_sha256()

        def corrupting_executor(semantic: SemanticExecutorRequest):
            corrupted = SemanticExecutorRequest(
                prepared=semantic.prepared,
                request=semantic.request,
                effect_request_sha256=wrong_digest,
            )
            return executor(corrupted)

        with self.assertRaisesRegex(
            ExecutorOutcomeUnknown,
            "EXECUTOR_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY",
        ):
            self.dispatch(
                lambda intent: authority_for(intent, ExternalGateDecision.ALLOW),
                corrupting_executor,
            )
        self.assertEqual(executor.calls, [])

    def test_invalid_argv_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticEffectRequestError, "INVALID_ARGV"):
            SemanticEffectRequest(
                user_id="user-1",
                session_id="session-1",
                capability="entityos.exec",
                target="repo/file.txt",
                argv=["write", "x"],  # type: ignore[arg-type]
                expected_generation=7,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
