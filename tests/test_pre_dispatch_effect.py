from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.pre_dispatch_effect import (
    EffectExecutionReceipt,
    PreDispatchEffectError,
    prepare_pre_dispatch_effect,
    record_effect_execution,
)
from state.execution_completion import (
    AdmitExecution,
    ExecutionLineage,
    ExecutionOutcome,
    ExecutionStage,
    ReplayDisposition,
    apply_execution_transition,
)


RESULT_SHA256 = "a" * 64


def make_admitted(*, suffix: str) -> tuple[NativeChildBinding, ExecutionLineage]:
    parent = CausalIdentity(
        session_id="shared-session",
        agent_id="parent-agent",
        task_id=f"task-{suffix}",
        turn_id=f"turn-{suffix}",
        causal_id=f"parent-causal-{suffix}",
        generation=4,
    )
    child = parent.derive(
        causal_id=f"child-causal-{suffix}",
        generation=5,
        agent_id=f"child-agent-{suffix}",
        task_id=f"child-task-{suffix}",
        turn_id=f"child-turn-{suffix}",
    )
    binding = NativeChildBinding(
        workpackage_id="F2-WP-102",
        workpackage_generation=1,
        claim_id="claim-wp102-g1",
        parent=parent,
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-use-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child=child,
    )
    lineage = ExecutionLineage.requested(
        causal_id=child.causal_id,
        generation=child.generation,
        request_id=f"request-{suffix}",
    )
    lineage = apply_execution_transition(
        lineage,
        AdmitExecution(
            transition_id=f"admit-transition-{suffix}",
            causal_id=lineage.causal_id,
            generation=lineage.generation,
            request_id=lineage.request_id,
            admission_id=f"admission-{suffix}",
        ),
    )
    return binding, lineage


def make_receipt(envelope, *, suffix: str, outcome: ExecutionOutcome) -> EffectExecutionReceipt:
    return EffectExecutionReceipt(
        transition_id=f"record-transition-{suffix}",
        effect_id=envelope.effect_id,
        binding_id=envelope.binding_id,
        invocation_id=envelope.invocation_id,
        tool_use_id=envelope.tool_use_id,
        delegation_id=envelope.delegation_id,
        child_identity_sha256=envelope.child_identity_sha256,
        causal_id=envelope.causal_id,
        generation=envelope.generation,
        request_id=envelope.request_id,
        admission_id=envelope.admission_id,
        execution_attempt_id=f"execution-attempt-{suffix}",
        outcome=outcome,
        result_id=f"result-{suffix}",
        result_sha256=RESULT_SHA256,
    )


class PreDispatchEffectTests(unittest.TestCase):
    def test_true_pre_dispatch_envelope_requires_no_result_or_execution_record(self) -> None:
        binding, lineage = make_admitted(suffix="A")
        self.assertFalse(binding.has_result)
        self.assertEqual(lineage.stage, ExecutionStage.ADMITTED)
        self.assertIsNone(lineage.execution_attempt_id)

        envelope = prepare_pre_dispatch_effect(binding, lineage, effect_id="effect-A")

        self.assertEqual(envelope.effect_id, "effect-A")
        self.assertEqual(envelope.binding_id, binding.binding_id())
        self.assertEqual(envelope.admission_id, lineage.admission_id)
        self.assertEqual(envelope.causal_id, binding.child.causal_id)

    def test_pre_dispatch_rejects_already_result_bound_binding(self) -> None:
        binding, lineage = make_admitted(suffix="A")
        bound = binding.bind_result(
            invocation_id=binding.invocation_id,
            delegation_id=binding.delegation_id,
            child_causal_id=binding.child.causal_id,
            result_id="result-A",
            result_sha256=RESULT_SHA256,
        )
        with self.assertRaisesRegex(
            PreDispatchEffectError, "PRE_DISPATCH_REQUIRES_RESULT_FREE_BINDING"
        ):
            prepare_pre_dispatch_effect(bound, lineage, effect_id="effect-A")

    def test_unknown_execution_receipt_stays_unverified_and_forbids_replay(self) -> None:
        binding, lineage = make_admitted(suffix="A")
        envelope = prepare_pre_dispatch_effect(binding, lineage, effect_id="effect-A")
        receipt = make_receipt(envelope, suffix="A", outcome=ExecutionOutcome.UNKNOWN)

        observed = record_effect_execution(envelope, binding, lineage, receipt)

        self.assertTrue(observed.binding.has_result)
        self.assertEqual(observed.binding.result_id, receipt.result_id)
        self.assertEqual(observed.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertEqual(observed.lineage.execution_outcome, ExecutionOutcome.UNKNOWN)
        self.assertFalse(observed.lineage.is_verified_complete)
        self.assertEqual(
            observed.lineage.replay_disposition,
            ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )

    def test_executor_reported_success_does_not_mint_verified_completion(self) -> None:
        binding, lineage = make_admitted(suffix="A")
        envelope = prepare_pre_dispatch_effect(binding, lineage, effect_id="effect-A")
        receipt = make_receipt(
            envelope,
            suffix="A",
            outcome=ExecutionOutcome.REPORTED_SUCCESS,
        )

        observed = record_effect_execution(envelope, binding, lineage, receipt)

        self.assertEqual(observed.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(observed.lineage.is_verified_complete)
        self.assertEqual(
            observed.lineage.replay_disposition,
            ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )

    def test_effect_id_mismatch_rejected_before_any_replacement(self) -> None:
        binding, lineage = make_admitted(suffix="A")
        envelope = prepare_pre_dispatch_effect(binding, lineage, effect_id="effect-A")
        receipt = make_receipt(envelope, suffix="A", outcome=ExecutionOutcome.UNKNOWN)
        wrong = replace(receipt, effect_id="effect-B")

        with self.assertRaisesRegex(PreDispatchEffectError, "EFFECT_ID_MISMATCH"):
            record_effect_execution(envelope, binding, lineage, wrong)

        self.assertFalse(binding.has_result)
        self.assertEqual(lineage.stage, ExecutionStage.ADMITTED)

    def test_cross_call_receipt_cannot_close_other_envelope(self) -> None:
        binding_a, lineage_a = make_admitted(suffix="A")
        binding_b, lineage_b = make_admitted(suffix="B")
        envelope_a = prepare_pre_dispatch_effect(binding_a, lineage_a, effect_id="effect-A")
        envelope_b = prepare_pre_dispatch_effect(binding_b, lineage_b, effect_id="effect-B")
        receipt_b = make_receipt(envelope_b, suffix="B", outcome=ExecutionOutcome.UNKNOWN)

        with self.assertRaises(PreDispatchEffectError):
            record_effect_execution(envelope_a, binding_a, lineage_a, receipt_b)

        self.assertFalse(binding_a.has_result)
        self.assertEqual(lineage_a.stage, ExecutionStage.ADMITTED)

    def test_pre_dispatch_rejects_wrong_causal_lineage_before_dispatch(self) -> None:
        binding_a, _ = make_admitted(suffix="A")
        _, lineage_b = make_admitted(suffix="B")
        with self.assertRaisesRegex(PreDispatchEffectError, "CAUSAL_ID_MISMATCH"):
            prepare_pre_dispatch_effect(binding_a, lineage_b, effect_id="effect-A")


if __name__ == "__main__":
    unittest.main(verbosity=2)
