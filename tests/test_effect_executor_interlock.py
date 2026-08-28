from __future__ import annotations

import unittest

from frankenstein2.effect_executor_interlock import (
    ExecutorInterlockError,
    ExecutorObservation,
    ExecutorOutcomeUnknown,
    ExternalGateDecision,
    ExternalGateEvidence,
    dispatch_through_external_gate,
)
from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
)


RESULT_SHA = "a" * 64
CHILD_A = "b" * 64
CHILD_B = "c" * 64


def prepared(suffix: str) -> EffectCallBinding:
    return EffectCallBinding(
        effect_id=f"effect-{suffix}",
        return_id=f"return-{suffix}",
        binding_id=f"binding-{suffix}",
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child_identity_sha256=CHILD_A if suffix == "A" else CHILD_B,
        stage=EffectCorrelationStage.PREPARED,
    )


def gate_for(
    call: EffectCallBinding,
    decision: ExternalGateDecision,
    *,
    decision_id: str | None = None,
) -> ExternalGateEvidence:
    return ExternalGateEvidence(
        authority_ref="canonical-effectgate:external",
        decision_id=decision_id or f"decision-{call.effect_id}-{decision.value}",
        decision=decision,
        effect_id=call.effect_id,
        binding_id=call.binding_id,
        invocation_id=call.invocation_id,
        tool_use_id=call.tool_use_id,
        delegation_id=call.delegation_id,
        child_identity_sha256=call.child_identity_sha256,
    )


def observation_for(call: EffectCallBinding) -> ExecutorObservation:
    return ExecutorObservation(
        effect_id=call.effect_id,
        binding_id=call.binding_id,
        invocation_id=call.invocation_id,
        tool_use_id=call.tool_use_id,
        delegation_id=call.delegation_id,
        child_identity_sha256=call.child_identity_sha256,
        result_id=f"result-{call.effect_id}",
        result_sha256=RESULT_SHA,
    )


class RecordingExecutor:
    def __init__(self, *, fail: bool = False, return_other_call: EffectCallBinding | None = None):
        self.calls: list[EffectCallBinding] = []
        self.fail = fail
        self.return_other_call = return_other_call

    def __call__(self, call: EffectCallBinding) -> ExecutorObservation:
        self.calls.append(call)
        if self.fail:
            raise RuntimeError("transport failed after invocation boundary")
        return observation_for(self.return_other_call or call)


class EffectExecutorInterlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = prepared("A")
        self.b = prepared("B")

    def test_every_non_allow_decision_blocks_before_executor(self) -> None:
        for decision in (
            ExternalGateDecision.DENY,
            ExternalGateDecision.REQUIRE_CONFIRMATION,
            ExternalGateDecision.DEGRADE_TO_PROPOSAL,
            ExternalGateDecision.UNKNOWN,
        ):
            with self.subTest(decision=decision.value):
                executor = RecordingExecutor()
                result = dispatch_through_external_gate(
                    self.a,
                    authorize=lambda call, d=decision: gate_for(call, d),
                    executor=executor,
                )
                self.assertFalse(result.dispatched)
                self.assertEqual(result.gate_decision, decision)
                self.assertEqual(executor.calls, [])
                self.assertEqual(result.block_reason, f"EXTERNAL_GATE_{decision.value}")

    def test_allow_for_call_b_cannot_dispatch_call_a(self) -> None:
        executor = RecordingExecutor()
        with self.assertRaisesRegex(ExecutorInterlockError, "EFFECT_ID_MISMATCH"):
            dispatch_through_external_gate(
                self.a,
                authorize=lambda _call: gate_for(self.b, ExternalGateDecision.ALLOW),
                executor=executor,
            )
        self.assertEqual(executor.calls, [])

    def test_authority_failure_blocks_before_executor(self) -> None:
        executor = RecordingExecutor()

        def broken_authority(_call):
            raise RuntimeError("authority unavailable")

        with self.assertRaisesRegex(
            ExecutorInterlockError, "EXTERNAL_EFFECT_AUTHORITY_FAILED"
        ):
            dispatch_through_external_gate(
                self.a,
                authorize=broken_authority,
                executor=executor,
            )
        self.assertEqual(executor.calls, [])

    def test_exact_allow_dispatches_once_and_binds_post_observation(self) -> None:
        executor = RecordingExecutor()
        result = dispatch_through_external_gate(
            self.a,
            authorize=lambda call: gate_for(call, ExternalGateDecision.ALLOW),
            executor=executor,
        )
        self.assertTrue(result.dispatched)
        self.assertEqual(executor.calls, [self.a])
        self.assertIsNotNone(result.observed)
        assert result.observed is not None
        self.assertEqual(result.observed.stage, EffectCorrelationStage.RESULT_OBSERVED)
        self.assertEqual(result.observed.effect_id, self.a.effect_id)
        self.assertEqual(result.observed.binding_id, self.a.binding_id)

    def test_executor_exception_is_unknown_and_never_retried(self) -> None:
        executor = RecordingExecutor(fail=True)
        with self.assertRaisesRegex(
            ExecutorOutcomeUnknown, "UNKNOWN_NO_AUTOMATIC_REPLAY"
        ):
            dispatch_through_external_gate(
                self.a,
                authorize=lambda call: gate_for(call, ExternalGateDecision.ALLOW),
                executor=executor,
            )
        self.assertEqual(executor.calls, [self.a])

    def test_post_identity_mismatch_is_unknown_not_denied_or_retried(self) -> None:
        executor = RecordingExecutor(return_other_call=self.b)
        with self.assertRaisesRegex(
            ExecutorOutcomeUnknown, "POST_CORRELATION_FAILED.*UNKNOWN_NO_AUTOMATIC_REPLAY"
        ):
            dispatch_through_external_gate(
                self.a,
                authorize=lambda call: gate_for(call, ExternalGateDecision.ALLOW),
                executor=executor,
            )
        self.assertEqual(executor.calls, [self.a])

    def test_already_observed_effect_cannot_cross_dispatch_boundary_again(self) -> None:
        observed = EffectCallBinding(
            effect_id=self.a.effect_id,
            return_id=self.a.return_id,
            binding_id=self.a.binding_id,
            invocation_id=self.a.invocation_id,
            tool_use_id=self.a.tool_use_id,
            delegation_id=self.a.delegation_id,
            child_identity_sha256=self.a.child_identity_sha256,
            stage=EffectCorrelationStage.RESULT_OBSERVED,
            result_id="result-A",
            result_sha256=RESULT_SHA,
        )
        executor = RecordingExecutor()
        with self.assertRaisesRegex(
            ExecutorInterlockError, "DISPATCH_REQUIRES_PREPARED_EFFECT_CALL"
        ):
            dispatch_through_external_gate(
                observed,
                authorize=lambda call: gate_for(call, ExternalGateDecision.ALLOW),
                executor=executor,
            )
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
