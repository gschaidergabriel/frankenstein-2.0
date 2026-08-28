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
from state.execution_completion import (
    AdmitExecution,
    ExecutionLineage,
    ExecutionOutcome,
    ExecutionStage,
    ReplayDisposition,
    apply_execution_transition,
)


CHILD_SHA = "a" * 64
RESULT_SHA = "b" * 64


def admitted() -> ExecutionLineage:
    lineage = ExecutionLineage.requested(
        causal_id="causal-A",
        generation=7,
        request_id="request-A",
    )
    return apply_execution_transition(
        lineage,
        AdmitExecution(
            transition_id="admit-A",
            causal_id=lineage.causal_id,
            generation=lineage.generation,
            request_id=lineage.request_id,
            admission_id="admission-A",
        ),
    )


def semantic_request(target: str = "target-A") -> EffectRequestIdentity:
    return EffectRequestIdentity(
        user_id="user-A",
        session_id="session-A",
        capability="entityos.exec",
        target=target,
        argv=("run", target),
        expected_generation=7,
    )


def prepared(*, semantic: bool = False) -> EffectCallBinding:
    return EffectCallBinding(
        effect_id="canonical-effect-A",
        return_id=None,
        binding_id="binding-A",
        invocation_id="invocation-A",
        tool_use_id="tool-A",
        delegation_id="delegation-A",
        child_identity_sha256=CHILD_SHA,
        stage=EffectCorrelationStage.PREPARED,
        request=semantic_request() if semantic else None,
    )


def receipt(
    *,
    raw_status: str = "SUCCEEDED",
    request_sha256: str | None = None,
) -> StructuredExecutionReceipt:
    return StructuredExecutionReceipt(
        receipt_id="executor-receipt-A",
        effect_id="canonical-effect-A",
        binding_id="binding-A",
        invocation_id="invocation-A",
        tool_use_id="tool-A",
        delegation_id="delegation-A",
        child_identity_sha256=CHILD_SHA,
        causal_id="causal-A",
        generation=7,
        request_id="request-A",
        admission_id="admission-A",
        execution_attempt_id="attempt-A",
        raw_status=raw_status,
        result_id="result-A",
        result_sha256=RESULT_SHA,
        request_sha256=request_sha256,
    )


class StructuredExecutionReceiptTests(unittest.TestCase):
    def test_only_exact_succeeded_maps_to_reported_success(self) -> None:
        observed = apply_structured_execution_receipt(
            prepared(), admitted(), receipt(raw_status="SUCCEEDED")
        )
        self.assertEqual(observed.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertEqual(
            observed.lineage.execution_outcome,
            ExecutionOutcome.REPORTED_SUCCESS,
        )
        self.assertFalse(observed.lineage.is_verified_complete)
        self.assertEqual(
            observed.lineage.replay_disposition,
            ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )
        self.assertEqual(
            observed.observed_call.stage,
            EffectCorrelationStage.RESULT_OBSERVED,
        )

    def test_semantic_request_digest_survives_structured_receipt(self) -> None:
        call = prepared(semantic=True)
        observed = apply_structured_execution_receipt(
            call,
            admitted(),
            receipt(request_sha256=call.request_sha256),
        )
        self.assertEqual(observed.observed_call.request_sha256, call.request_sha256)
        self.assertEqual(observed.receipt.request_sha256, call.request_sha256)

    def test_missing_semantic_request_digest_is_rejected_before_lineage_replacement(self) -> None:
        call = prepared(semantic=True)
        line = admitted()
        with self.assertRaisesRegex(
            StructuredExecutionReceiptError, "REQUEST_SHA256_REQUIRED"
        ):
            apply_structured_execution_receipt(call, line, receipt())
        self.assertEqual(line.stage, ExecutionStage.ADMITTED)
        self.assertIsNone(line.execution_attempt_id)

    def test_substituted_semantic_request_digest_is_rejected_before_lineage_replacement(self) -> None:
        call = prepared(semantic=True)
        line = admitted()
        wrong = semantic_request("target-B").sha256()
        with self.assertRaisesRegex(
            StructuredExecutionReceiptError, "REQUEST_SHA256_MISMATCH"
        ):
            apply_structured_execution_receipt(
                call,
                line,
                receipt(request_sha256=wrong),
            )
        self.assertEqual(line.stage, ExecutionStage.ADMITTED)
        self.assertIsNone(line.execution_attempt_id)

    def test_success_like_strings_are_not_success(self) -> None:
        for status in (
            "SUCCESS",
            "PASS",
            "OK",
            "COMPLETED",
            "DONE",
            "0",
            "FAILED",
            "TIMEOUT",
            "CANCELLED",
        ):
            with self.subTest(status=status):
                observed = apply_structured_execution_receipt(
                    prepared(), admitted(), receipt(raw_status=status)
                )
                self.assertEqual(
                    observed.lineage.execution_outcome,
                    ExecutionOutcome.UNKNOWN,
                )
                self.assertFalse(observed.lineage.is_verified_complete)

    def test_canonical_unknown_outcome_stays_unverified_and_nonreplayable(self) -> None:
        """Consume EntityOS UNKNOWN_OUTCOME without upgrading it to failure or success."""
        observed = apply_structured_execution_receipt(
            prepared(), admitted(), receipt(raw_status="UNKNOWN_OUTCOME")
        )
        self.assertEqual(observed.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertEqual(observed.lineage.execution_outcome, ExecutionOutcome.UNKNOWN)
        self.assertFalse(observed.lineage.is_verified_complete)
        self.assertEqual(
            observed.lineage.replay_disposition,
            ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )

    def test_only_explicit_pre_effect_failure_maps_to_reported_failure(self) -> None:
        observed = apply_structured_execution_receipt(
            prepared(), admitted(), receipt(raw_status="FAILED_BEFORE_EFFECT")
        )
        self.assertEqual(
            observed.lineage.execution_outcome,
            ExecutionOutcome.REPORTED_FAILURE,
        )
        self.assertFalse(observed.lineage.is_verified_complete)

    def test_result_digest_is_bound_to_observed_call(self) -> None:
        observed = apply_structured_execution_receipt(
            prepared(), admitted(), receipt()
        )
        self.assertEqual(observed.observed_call.result_id, "result-A")
        self.assertEqual(observed.observed_call.result_sha256, RESULT_SHA)
        self.assertEqual(observed.receipt.fingerprint().__len__(), 64)
        self.assertTrue(
            observed.receipt.transition_id().startswith(
                "structured-execution-receipt:"
            )
        )

    def test_cross_call_receipt_is_rejected_before_lineage_replacement(self) -> None:
        line = admitted()
        wrong = replace(receipt(), tool_use_id="tool-B")
        with self.assertRaisesRegex(
            StructuredExecutionReceiptError, "TOOL_USE_ID_MISMATCH"
        ):
            apply_structured_execution_receipt(prepared(), line, wrong)
        self.assertEqual(line.stage, ExecutionStage.ADMITTED)
        self.assertIsNone(line.execution_attempt_id)

    def test_wrong_admission_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            StructuredExecutionReceiptError, "ADMISSION_ID_MISMATCH"
        ):
            apply_structured_execution_receipt(
                prepared(),
                admitted(),
                replace(receipt(), admission_id="admission-B"),
            )

    def test_receipt_payload_fingerprint_changes_with_result_status_or_semantic_request(self) -> None:
        base = receipt()
        changed_result = replace(base, result_sha256="c" * 64)
        changed_status = replace(base, raw_status="SUCCESS")
        changed_request = replace(base, request_sha256="d" * 64)
        self.assertNotEqual(base.fingerprint(), changed_result.fingerprint())
        self.assertNotEqual(base.fingerprint(), changed_status.fingerprint())
        self.assertNotEqual(base.fingerprint(), changed_request.fingerprint())
        self.assertNotEqual(base.transition_id(), changed_result.transition_id())
        self.assertNotEqual(base.transition_id(), changed_status.transition_id())
        self.assertNotEqual(base.transition_id(), changed_request.transition_id())

    def test_exact_receipt_replay_is_idempotent_at_lineage_layer(self) -> None:
        call = prepared()
        first = apply_structured_execution_receipt(call, admitted(), receipt())
        second = apply_structured_execution_receipt(call, first.lineage, receipt())
        self.assertEqual(first.lineage, second.lineage)
        self.assertEqual(first.observed_call, second.observed_call)


if __name__ == "__main__":
    unittest.main(verbosity=2)
