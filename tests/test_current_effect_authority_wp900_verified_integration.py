"""Cross-component regression: current EntityOS effect authority -> WP105 -> WP900.

This test exercises only existing authorities and typed adapters. It proves that an
EffectJournal-verified APPLIED result for the exact current-authority-dispatched call
can enter WP900 as VERIFIED_APPLIED and participate in the deterministic persistence
seal without minting effect/completion/runtime authority.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_current_entityos_effect_authority_binding import RESULT_SHA, evidence_for, load_binding  # noqa: E402
from test_deferred_execution_verification import execution_record, make_return  # noqa: E402
from test_whole_persistent_loop import fixture_components  # noqa: E402

from frankenstein2.canonical_effect_authority_bridge import EffectCallIntent  # noqa: E402
from frankenstein2.current_entityos_effect_authority_binding import dispatch_with_current_entityos_authority  # noqa: E402
from frankenstein2.deferred_execution_verification import DeferredExecutionVerificationTarget  # noqa: E402
from frankenstein2.effect_executor_interlock import ExecutorObservation, ExternalGateDecision  # noqa: E402
from frankenstein2.effect_request_identity import EffectRequestIdentity  # noqa: E402
from frankenstein2.persistent_agency_kernel import advance_checkpoint  # noqa: E402
from frankenstein2.whole_persistent_loop import (  # noqa: E402
    EFFECT_VERIFIED_APPLIED,
    LoopOutcomeEvidence,
    required_reentry_refs,
    seal_whole_persistent_loop,
)
from state.execution_completion import (  # noqa: E402
    VERIFICATION_RECEIPT_SCHEMA,
    ExecutionStage,
    VerificationEvidenceKind,
    VerificationOutcome,
    VerificationReceipt,
    VerifyExecution,
    apply_execution_transition,
)


class ExactResultExecutor:
    def __init__(self, *, result_id: str, result_sha256: str) -> None:
        self.result_id = result_id
        self.result_sha256 = result_sha256
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
            result_id=self.result_id,
            result_sha256=self.result_sha256,
            request_sha256=prepared.request_sha256,
        )


def test_current_effect_authority_verified_applied_reaches_wp900_seal_without_credit_inflation():
    returned = make_return(suffix="WP900", task_id="task-wp900-effect", turn_id="turn-wp900-effect")
    child = returned.binding.child
    request = EffectRequestIdentity(
        user_id="user-wp900-effect",
        session_id=child.session_id,
        capability="entityos.exec",
        target="target-wp900-effect",
        argv=("run", "payload-wp900-effect"),
        expected_generation=child.generation,
    )
    intent = EffectCallIntent(
        return_id=returned.return_id,
        binding_id=returned.binding.binding_id(),
        invocation_id=returned.binding.invocation_id,
        tool_use_id=returned.binding.tool_use_id,
        delegation_id=returned.binding.delegation_id,
        child_identity_sha256=child.sha256(),
        request=request,
    )

    binding = load_binding()
    executor = ExactResultExecutor(
        result_id=returned.binding.result_id,
        result_sha256=returned.binding.result_sha256,
    )
    dispatched = dispatch_with_current_entityos_authority(
        intent,
        binding=binding,
        authorize=lambda item: evidence_for(
            item,
            binding,
            ExternalGateDecision.ALLOW,
            effect_id="canonical-effect-wp900-verified",
        ),
        executor=executor,
    )
    assert dispatched.dispatched
    assert dispatched.interlock is not None
    observed = dispatched.interlock.observed
    assert observed is not None
    assert observed.binding_id == returned.binding.binding_id()
    assert observed.result_id == returned.binding.result_id
    assert observed.result_sha256 == returned.binding.result_sha256

    recorded = execution_record(returned)
    verification_attempt_id = "verification-wp900-effect"
    verified = apply_execution_transition(
        recorded,
        VerifyExecution(
            transition_id="transition-verify-wp900-effect",
            causal_id=recorded.causal_id,
            generation=recorded.generation,
            request_id=recorded.request_id,
            admission_id=recorded.admission_id,
            execution_attempt_id=recorded.execution_attempt_id,
            verification_attempt_id=verification_attempt_id,
            outcome=VerificationOutcome.APPLIED,
            receipt=VerificationReceipt(
                schema=VERIFICATION_RECEIPT_SCHEMA,
                receipt_id="verification-receipt-wp900-effect",
                verification_attempt_id=verification_attempt_id,
                execution_attempt_id=recorded.execution_attempt_id,
                execution_outcome=recorded.execution_outcome,
                outcome=VerificationOutcome.APPLIED,
                evidence_kind=VerificationEvidenceKind.EFFECT_JOURNAL_VERIFIED,
                evidence_ref="canonical-effect-wp900-verified:VERIFIED",
                evidence_sha256=RESULT_SHA,
            ),
        ),
    )
    assert verified.stage is ExecutionStage.VERIFIED_APPLIED
    target = DeferredExecutionVerificationTarget(returned=returned, lineage=verified)

    outcome = LoopOutcomeEvidence(
        outcome_id="outcome-wp900-effect-verified",
        status=EFFECT_VERIFIED_APPLIED,
        effect_call=observed,
        verification_target=target,
        provenance_refs=(binding.current_epoch_attestation_path, "integration:current-effect-authority-wp105-wp900"),
    )

    checkpoint, frame, contract, plan, gwt, gwt_evidence, decision, _, _ = fixture_components()
    refs = required_reentry_refs(
        current_checkpoint=checkpoint,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt,
        decision=decision,
        outcome=outcome,
    )
    next_checkpoint = advance_checkpoint(
        checkpoint,
        checkpoint_id="checkpoint-wp900-verified-effect",
        pulse_id="pulse-wp900-verified-effect",
        observation_id="observation-wp900-verified-effect",
        provenance_refs=refs,
    )
    seal = seal_whole_persistent_loop(
        seal_id="whole-loop-seal-wp900-verified-effect",
        generation=0,
        current_checkpoint=checkpoint,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        decision=decision,
        outcome=outcome,
        next_checkpoint=next_checkpoint,
        provenance_refs=("integration:wp105-verified-effect-wp900",),
    )

    payload = seal.as_dict()
    assert outcome.as_dict()["status"] == EFFECT_VERIFIED_APPLIED
    assert outcome.as_dict()["effect_authority"] == "NONE"
    assert outcome.as_dict()["completion_authority"] == "NONE"
    assert payload["runtime_credit"] == 0
    assert payload["effect_authority"] == "NONE"
    assert payload["completion_authority"] == "NONE"
    assert payload["whole_system_acceptance"] is False
