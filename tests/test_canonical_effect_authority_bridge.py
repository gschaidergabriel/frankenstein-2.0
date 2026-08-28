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
from frankenstein2.effect_executor_interlock import ExecutorObservation, ExternalGateDecision
from frankenstein2.effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage


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


def intent(suffix: str, *, return_bound: bool = False) -> EffectCallIntent:
    return EffectCallIntent(
        return_id=f"return-{suffix}" if return_bound else None,
        binding_id=f"binding-{suffix}",
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child_identity_sha256=CHILD_A if suffix == "A" else CHILD_B,
    )


def authority_for(
    call: EffectCallIntent,
    decision: ExternalGateDecision,
    *,
    authority: CanonicalEffectAuthorityIdentity = AUTHORITY,
    effect_id: str | None = None,
    journal_state: str | None = None,
) -> CanonicalEffectAuthorityEvidence:
    if journal_state is None:
        journal_state = "PENDING" if decision is ExternalGateDecision.ALLOW else "NO_EFFECT"
    if decision is ExternalGateDecision.ALLOW and effect_id is None:
        effect_id = f"canonical-{call.tool_use_id}"
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
    )


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[EffectCallBinding] = []

    def __call__(self, call: EffectCallBinding) -> ExecutorObservation:
        self.calls.append(call)
        return ExecutorObservation(
            effect_id=call.effect_id,
            binding_id=call.binding_id,
            invocation_id=call.invocation_id,
            tool_use_id=call.tool_use_id,
            delegation_id=call.delegation_id,
            child_identity_sha256=call.child_identity_sha256,
            result_id=f"result-{call.tool_use_id}",
            result_sha256=RESULT_SHA,
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

    def test_true_pre_authority_intent_has_neither_effect_nor_return_id(self) -> None:
        self.assertFalse(hasattr(self.a, "effect_id"))
        self.assertIsNone(self.a.return_id)

    def test_canonical_allow_mints_effect_id_before_dispatch(self) -> None:
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
        self.assertEqual(result.interlock.observed.effect_id, "journal-effect-A")

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

    def test_same_session_overlapping_calls_keep_distinct_canonical_effect_ids(self) -> None:
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
        self.assertEqual(result_a.interlock.observed.tool_use_id, self.a.tool_use_id)
        self.assertEqual(result_b.interlock.observed.tool_use_id, self.b.tool_use_id)

    def test_existing_candidate_effect_id_is_discarded_on_result_free_path(self) -> None:
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
        migrated = intent_from_prepared_candidate(old)
        self.assertFalse(hasattr(migrated, "effect_id"))
        self.assertIsNone(migrated.return_id)
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
        self.assertNotEqual(bound.prepared.effect_id, old.effect_id)

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
