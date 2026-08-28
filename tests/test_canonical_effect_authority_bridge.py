from __future__ import annotations

import unittest

from frankenstein2.canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityBridgeError,
    CanonicalEffectAuthorityEvidence,
    CanonicalEffectAuthorityIdentity,
    CanonicalEffectAuthorityIdentityError,
    EffectCallIntent,
    bind_canonical_effect,
    dispatch_with_canonical_authority,
    intent_from_prepared_candidate,
)
from frankenstein2.effect_executor_interlock import (
    ExecutorObservation,
    ExecutorOutcomeUnknown,
    ExternalGateDecision,
)
from frankenstein2.effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage
from frankenstein2.effect_request_identity import EffectRequestIdentity


CHILD_A = "a" * 64
CHILD_B = "b" * 64
RESULT_SHA = "c" * 64
AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="example/canonical-authority",
    commit_sha="1" * 40,
    module_path="entityos/effects.py",
    source_blob_sha="2" * 40,
    state_schema="EffectJournal/v1",
    api_version="CANONICAL_EFFECT_AUTHORITY_PORT/v1",
)
OTHER_AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="example/other-authority",
    commit_sha="3" * 40,
    module_path="other/effects.py",
    source_blob_sha="4" * 40,
    state_schema="OtherJournal/v1",
    api_version="OTHER_EFFECT_AUTHORITY/v1",
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


def intent(
    suffix: str,
    *,
    return_bound: bool = False,
    semantic_request: EffectRequestIdentity | None = None,
) -> EffectCallIntent:
    return EffectCallIntent(
        return_id=f"return-{suffix}" if return_bound else None,
        binding_id=f"binding-{suffix}",
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child_identity_sha256=CHILD_A if suffix == "A" else CHILD_B,
        request=semantic_request if semantic_request is not None else request(suffix),
    )


def authority_for(
    call: EffectCallIntent,
    decision: ExternalGateDecision,
    *,
    authority: CanonicalEffectAuthorityIdentity = AUTHORITY,
    effect_id: str | None = None,
    journal_state: str | None = None,
    request_sha256: str | None = None,
) -> CanonicalEffectAuthorityEvidence:
    if journal_state is None:
        journal_state = "PENDING" if decision is ExternalGateDecision.ALLOW else "NO_EFFECT"
    if decision is ExternalGateDecision.ALLOW and effect_id is None:
        effect_id = f"canonical-{call.tool_use_id}"
    if request_sha256 is None:
        request_sha256 = call.request_sha256
    return CanonicalEffectAuthorityEvidence(
        authority=authority,
        decision_id=f"decision-{call.tool_use_id}-{decision.value}",
        decision=decision,
        journal_state=journal_state,
        effect_id=effect_id,
        return_id=call.return_id,
        binding_id=call.binding_id,
        invocation_id=call.invocation_id,
        tool_use_id=call.tool_use_id,
        delegation_id=call.delegation_id,
        child_identity_sha256=call.child_identity_sha256,
        request_sha256=request_sha256,
    )


class RecordingExecutor:
    def __init__(self, *, request_sha256_override: str | None = None) -> None:
        self.calls: list[EffectCallBinding] = []
        self.request_sha256_override = request_sha256_override

    def __call__(self, call: EffectCallBinding) -> ExecutorObservation:
        self.calls.append(call)
        request_sha256 = (
            self.request_sha256_override
            if self.request_sha256_override is not None
            else call.request_sha256
        )
        return ExecutorObservation(
            effect_id=call.effect_id,
            binding_id=call.binding_id,
            invocation_id=call.invocation_id,
            tool_use_id=call.tool_use_id,
            delegation_id=call.delegation_id,
            child_identity_sha256=call.child_identity_sha256,
            result_id=f"result-{call.tool_use_id}",
            result_sha256=RESULT_SHA,
            request_sha256=request_sha256,
        )


class CanonicalEffectAuthorityBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = intent("A")
        self.b = intent("B")

    def dispatch(self, call, authorize, executor):
        return dispatch_with_canonical_authority(
            call,
            expected_authority=AUTHORITY,
            authorize=authorize,
            executor=executor,
        )

    def test_true_pre_authority_intent_has_no_effect_or_return_but_has_semantic_request(self) -> None:
        self.assertFalse(hasattr(self.a, "effect_id"))
        self.assertIsNone(self.a.return_id)
        self.assertIsInstance(self.a.request, EffectRequestIdentity)
        self.assertEqual(len(self.a.request_sha256 or ""), 64)

    def test_canonical_allow_mints_effect_id_before_dispatch_and_preserves_request(self) -> None:
        executor = RecordingExecutor()
        calls = []

        def authorize(call: EffectCallIntent):
            calls.append(call)
            return authority_for(
                call,
                ExternalGateDecision.ALLOW,
                effect_id="journal-effect-A",
            )

        result = self.dispatch(self.a, authorize, executor)
        self.assertEqual(calls, [self.a])
        self.assertTrue(result.dispatched)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(executor.calls[0].effect_id, "journal-effect-A")
        self.assertIsNone(executor.calls[0].return_id)
        self.assertEqual(executor.calls[0].request, self.a.request)
        self.assertEqual(executor.calls[0].request_sha256, self.a.request_sha256)
        self.assertEqual(result.interlock.observed.effect_id, "journal-effect-A")
        self.assertEqual(result.interlock.observed.request_sha256, self.a.request_sha256)

    def test_missing_semantic_request_fails_before_authority_or_executor(self) -> None:
        unresolved = EffectCallIntent(
            return_id=None,
            binding_id="binding-unresolved",
            invocation_id="invocation-unresolved",
            tool_use_id="tool-unresolved",
            delegation_id="delegation-unresolved",
            child_identity_sha256=CHILD_A,
        )
        authority_calls = []
        executor = RecordingExecutor()
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "SEMANTIC_EFFECT_REQUEST_UNRESOLVED",
        ):
            self.dispatch(
                unresolved,
                lambda call: authority_calls.append(call),
                executor,
            )
        self.assertEqual(authority_calls, [])
        self.assertEqual(executor.calls, [])

    def test_authority_request_substitution_fails_before_executor(self) -> None:
        executor = RecordingExecutor()
        evidence_for_wrong_semantics = authority_for(
            self.a,
            ExternalGateDecision.ALLOW,
            effect_id="journal-effect-A",
            request_sha256=self.b.request_sha256,
        )
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "REQUEST_SHA256_MISMATCH",
        ):
            bind_canonical_effect(
                self.a,
                evidence_for_wrong_semantics,
                expected_authority=AUTHORITY,
            )
        self.assertEqual(executor.calls, [])

    def test_post_request_substitution_becomes_unknown_after_dispatch(self) -> None:
        executor = RecordingExecutor(request_sha256_override=self.b.request_sha256)
        with self.assertRaisesRegex(
            ExecutorOutcomeUnknown,
            "EXECUTOR_POST_CORRELATION_FAILED_OUTCOME_UNKNOWN_NO_AUTOMATIC_REPLAY",
        ):
            self.dispatch(
                self.a,
                lambda call: authority_for(
                    call,
                    ExternalGateDecision.ALLOW,
                    effect_id="journal-effect-A",
                ),
                executor,
            )
        self.assertEqual(len(executor.calls), 1)

    def test_every_non_allow_decision_stops_before_executor(self) -> None:
        for decision in (
            ExternalGateDecision.DENY,
            ExternalGateDecision.REQUIRE_CONFIRMATION,
            ExternalGateDecision.DEGRADE_TO_PROPOSAL,
            ExternalGateDecision.UNKNOWN,
        ):
            with self.subTest(decision=decision.value):
                executor = RecordingExecutor()
                result = self.dispatch(
                    self.a,
                    lambda call, d=decision: authority_for(call, d),
                    executor,
                )
                self.assertFalse(result.dispatched)
                self.assertIsNone(result.interlock)
                self.assertEqual(executor.calls, [])

    def test_restart_unknown_with_existing_effect_never_replays(self) -> None:
        executor = RecordingExecutor()
        result = self.dispatch(
            self.a,
            lambda call: authority_for(
                call,
                ExternalGateDecision.UNKNOWN,
                effect_id="journal-effect-prior",
                journal_state="UNKNOWN_AFTER_RESTART",
            ),
            executor,
        )
        self.assertFalse(result.dispatched)
        self.assertEqual(result.authority.effect_id, "journal-effect-prior")
        self.assertEqual(result.authority.journal_state, "UNKNOWN_AFTER_RESTART")
        self.assertEqual(executor.calls, [])

    def test_allow_without_pending_journal_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "CANONICAL_ALLOW_REQUIRES_PENDING_JOURNAL",
        ):
            authority_for(
                self.a,
                ExternalGateDecision.ALLOW,
                effect_id="effect-A",
                journal_state="VERIFIED",
            )

    def test_allow_without_canonical_effect_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "CANONICAL_ALLOW_REQUIRES_EFFECT_ID",
        ):
            CanonicalEffectAuthorityEvidence(
                authority=AUTHORITY,
                decision_id="decision-A",
                decision=ExternalGateDecision.ALLOW,
                journal_state="PENDING",
                effect_id=None,
                return_id=self.a.return_id,
                binding_id=self.a.binding_id,
                invocation_id=self.a.invocation_id,
                tool_use_id=self.a.tool_use_id,
                delegation_id=self.a.delegation_id,
                child_identity_sha256=self.a.child_identity_sha256,
                request_sha256=self.a.request_sha256,
            )

    def test_unresolved_or_different_authority_cannot_self_grant(self) -> None:
        executor = RecordingExecutor()
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "AUTHORITY_IDENTITY_MISMATCH",
        ):
            self.dispatch(
                self.a,
                lambda call: authority_for(
                    call,
                    ExternalGateDecision.ALLOW,
                    authority=OTHER_AUTHORITY,
                    effect_id="other-effect-A",
                ),
                executor,
            )
        self.assertEqual(executor.calls, [])

    def test_allow_for_call_b_cannot_bind_call_a(self) -> None:
        evidence_b = authority_for(
            self.b,
            ExternalGateDecision.ALLOW,
            effect_id="journal-effect-B",
        )
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "BINDING_ID_MISMATCH",
        ):
            bind_canonical_effect(
                self.a,
                evidence_b,
                expected_authority=AUTHORITY,
            )

    def test_same_session_overlapping_calls_keep_distinct_requests_and_effect_ids(self) -> None:
        executor = RecordingExecutor()
        minted = {
            self.a.tool_use_id: "journal-effect-A",
            self.b.tool_use_id: "journal-effect-B",
        }

        def authorize(call: EffectCallIntent):
            return authority_for(
                call,
                ExternalGateDecision.ALLOW,
                effect_id=minted[call.tool_use_id],
            )

        result_b = self.dispatch(self.b, authorize, executor)
        result_a = self.dispatch(self.a, authorize, executor)
        self.assertTrue(result_a.dispatched)
        self.assertTrue(result_b.dispatched)
        self.assertEqual(
            [call.effect_id for call in executor.calls],
            ["journal-effect-B", "journal-effect-A"],
        )
        self.assertNotEqual(self.a.request_sha256, self.b.request_sha256)
        self.assertEqual(result_a.interlock.observed.tool_use_id, self.a.tool_use_id)
        self.assertEqual(result_b.interlock.observed.tool_use_id, self.b.tool_use_id)

    def test_existing_candidate_effect_id_is_discarded_but_request_is_preserved(self) -> None:
        old = EffectCallBinding(
            effect_id="caller-authored-effect-id",
            return_id=None,
            binding_id=self.a.binding_id,
            invocation_id=self.a.invocation_id,
            tool_use_id=self.a.tool_use_id,
            delegation_id=self.a.delegation_id,
            child_identity_sha256=self.a.child_identity_sha256,
            stage=EffectCorrelationStage.PREPARED,
            request=self.a.request,
        )
        migrated = intent_from_prepared_candidate(old)
        self.assertFalse(hasattr(migrated, "effect_id"))
        self.assertIsNone(migrated.return_id)
        self.assertEqual(migrated.request, self.a.request)
        bound = bind_canonical_effect(
            migrated,
            authority_for(
                migrated,
                ExternalGateDecision.ALLOW,
                effect_id="journal-effect-A",
            ),
            expected_authority=AUTHORITY,
        )
        self.assertEqual(bound.prepared.effect_id, "journal-effect-A")
        self.assertEqual(bound.prepared.request_sha256, self.a.request_sha256)
        self.assertNotEqual(bound.prepared.effect_id, old.effect_id)

    def test_legacy_candidate_without_request_cannot_enter_canonical_path(self) -> None:
        old = EffectCallBinding(
            effect_id="caller-authored-effect-id",
            return_id=None,
            binding_id=self.a.binding_id,
            invocation_id=self.a.invocation_id,
            tool_use_id=self.a.tool_use_id,
            delegation_id=self.a.delegation_id,
            child_identity_sha256=self.a.child_identity_sha256,
            stage=EffectCorrelationStage.PREPARED,
        )
        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "SEMANTIC_EFFECT_REQUEST_UNRESOLVED",
        ):
            intent_from_prepared_candidate(old)

    def test_authority_failure_stops_before_executor(self) -> None:
        executor = RecordingExecutor()

        def broken(_intent):
            raise RuntimeError("canonical authority unavailable")

        with self.assertRaisesRegex(
            CanonicalEffectAuthorityBridgeError,
            "CANONICAL_EFFECT_AUTHORITY_FAILED",
        ):
            self.dispatch(self.a, broken, executor)
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
