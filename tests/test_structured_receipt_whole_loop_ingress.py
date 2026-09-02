from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
)
from frankenstein2.effect_request_identity import EffectRequestIdentity
from frankenstein2.structured_execution_receipt import (
    StructuredExecutionReceipt,
    StructuredExecutionReceiptError,
    apply_structured_execution_receipt,
)
from frankenstein2.whole_persistent_loop import (
    EFFECT_RESULT_OBSERVED,
    LoopOutcomeEvidence,
    WholePersistentLoopError,
)
from state.execution_completion import (
    AdmitExecution,
    ExecutionLineage,
    apply_execution_transition,
)


CHILD_SHA = "a" * 64
RESULT_SHA = "b" * 64


def admitted() -> ExecutionLineage:
    lineage = ExecutionLineage.requested(
        causal_id="causal-wp105-wp900",
        generation=9,
        request_id="request-wp105-wp900",
    )
    return apply_execution_transition(
        lineage,
        AdmitExecution(
            transition_id="admit-wp105-wp900",
            causal_id=lineage.causal_id,
            generation=lineage.generation,
            request_id=lineage.request_id,
            admission_id="admission-wp105-wp900",
        ),
    )


def request() -> EffectRequestIdentity:
    return EffectRequestIdentity(
        user_id="user-wp105-wp900",
        session_id="session-wp105-wp900",
        capability="entityos.exec",
        target="target-wp105-wp900",
        argv=("run", "target-wp105-wp900"),
        expected_generation=9,
    )


def prepared() -> EffectCallBinding:
    return EffectCallBinding(
        effect_id="effect-wp105-wp900",
        return_id=None,
        binding_id="binding-wp105-wp900",
        invocation_id="invocation-wp105-wp900",
        tool_use_id="tool-wp105-wp900",
        delegation_id="delegation-wp105-wp900",
        child_identity_sha256=CHILD_SHA,
        stage=EffectCorrelationStage.PREPARED,
        request=request(),
    )


def receipt(call: EffectCallBinding) -> StructuredExecutionReceipt:
    return StructuredExecutionReceipt(
        receipt_id="receipt-wp105-wp900",
        effect_id=call.effect_id,
        binding_id=call.binding_id,
        invocation_id=call.invocation_id,
        tool_use_id=call.tool_use_id,
        delegation_id=call.delegation_id,
        child_identity_sha256=call.child_identity_sha256,
        causal_id="causal-wp105-wp900",
        generation=9,
        request_id="request-wp105-wp900",
        admission_id="admission-wp105-wp900",
        execution_attempt_id="attempt-wp105-wp900",
        raw_status="SUCCEEDED",
        result_id="result-wp105-wp900",
        result_sha256=RESULT_SHA,
        request_sha256=call.request_sha256,
    )


class StructuredReceiptWholeLoopIngressTests(unittest.TestCase):
    def test_wp105_observed_binding_is_admitted_by_wp900_without_authority_inflation(self) -> None:
        call = prepared()
        applied = apply_structured_execution_receipt(call, admitted(), receipt(call))

        outcome = LoopOutcomeEvidence(
            outcome_id="outcome-wp105-wp900",
            status=EFFECT_RESULT_OBSERVED,
            effect_call=applied.observed_call,
            provenance_refs=(f"wp105:receipt:{applied.receipt.fingerprint()}",),
        )

        self.assertIs(applied.observed_call.stage, EffectCorrelationStage.RESULT_OBSERVED)
        self.assertEqual(applied.observed_call.request_sha256, call.request_sha256)
        self.assertEqual(outcome.effect_call, applied.observed_call)
        payload = outcome.as_dict()
        self.assertEqual(payload["status"], EFFECT_RESULT_OBSERVED)
        self.assertEqual(payload["effect"]["result_sha256"], RESULT_SHA)
        self.assertEqual(payload["effect"]["request_sha256"], call.request_sha256)
        self.assertEqual(payload["truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")

    def test_wp105_request_substitution_fails_before_wp900_ingress(self) -> None:
        call = prepared()
        substituted = replace(receipt(call), request_sha256="c" * 64)
        with self.assertRaisesRegex(
            StructuredExecutionReceiptError, "REQUEST_SHA256_MISMATCH"
        ):
            apply_structured_execution_receipt(call, admitted(), substituted)
        self.assertIs(call.stage, EffectCorrelationStage.PREPARED)

    def test_wp900_rejects_prepared_binding_without_wp105_result_observation(self) -> None:
        with self.assertRaisesRegex(WholePersistentLoopError, "requires RESULT_OBSERVED"):
            LoopOutcomeEvidence(
                outcome_id="outcome-wp105-wp900-prepared",
                status=EFFECT_RESULT_OBSERVED,
                effect_call=prepared(),
                provenance_refs=("test:wp105-wp900:prepared",),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
