from __future__ import annotations

import copy
import unittest

from frankenstein2.canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityEvidence,
    EffectCallIntent,
)
from frankenstein2.current_entityos_effect_authority_binding import (
    CurrentEntityOSEffectAuthorityBindingError,
    dispatch_with_current_entityos_authority,
    load_current_entityos_effect_authority_binding,
)
from frankenstein2.effect_executor_interlock import ExecutorObservation, ExternalGateDecision
from frankenstein2.effect_request_identity import EffectRequestIdentity
from frankenstein2.structured_execution_receipt import (
    StructuredExecutionReceipt,
    apply_structured_execution_receipt,
)
from state.execution_completion import (
    AdmitExecution,
    ExecutionLineage,
    ExecutionOutcome,
    ExecutionStage,
    ReplayDisposition,
    VerificationOutcome,
    VerifyExecution,
    apply_execution_transition,
)


BINDING_PATH = "research_entity/continuity/ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING_V1.json"
BINDING_BLOB = "b4d91a0dd233c9dc15ff8218feea9248ac1c13c5"
BINDING_COMMIT = "5638204026468b631de5e774e8403d7a6334021e"
ATTESTATION_PATH = (
    "research_entity/continuity/"
    "ENTITYOS_EFFECT_AUTHORITY_BINDING_9_13_CURRENT_EPOCH_ATTESTATION_2026-08-29.json"
)
ATTESTATION_COMMIT = "60f3e77900721ffa1dea1211e8b035a0e42b7c2f"
CHILD_SHA = "a" * 64
RESULT_SHA = "b" * 64

BINDING = {
    "schema": "ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING/v1",
    "implementation_identity": {
        "repository": "gschaidergabriel/clay-global-research-entity",
        "bound_commit": "2b68aad14bf7824d513b52898904909256e3522d",
        "effect_gate": {
            "path": "the artefact/clayverse/effects.py",
            "blob_sha": "4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
        },
        "effect_journal": {
            "path": "the artefact/clayverse/effect_journal.py",
            "blob_sha": "cda63471f1467481f2ff79032d3931730a334a20",
        },
        "canonical_state_schema": {
            "path": "the artefact/clayverse/store.py",
            "blob_sha": "a88d923ea3d0eab5847f304f35463e5a2b2c4acd",
            "schema_version": "6",
        },
    },
    "api_contract": {
        "version": "ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
    },
}

ATTESTATION = {
    "schema": "ENTITYOS_EFFECT_AUTHORITY_CURRENT_EPOCH_ATTESTATION/v1",
    "status": "CURRENT_EPOCH_COMPATIBILITY_ATTESTED_NO_AUTHORITY_CHANGE",
    "canonical_repository": "gschaidergabriel/clay-global-research-entity",
    "attested_binding": {
        "path": BINDING_PATH,
        "blob_sha": BINDING_BLOB,
        "binding_commit": BINDING_COMMIT,
        "implementation_bound_commit": "2b68aad14bf7824d513b52898904909256e3522d",
        "effect_gate_path": "the artefact/clayverse/effects.py",
        "effect_gate_blob_sha": "4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
        "effect_journal_path": "the artefact/clayverse/effect_journal.py",
        "effect_journal_blob_sha": "cda63471f1467481f2ff79032d3931730a334a20",
        "unifieddb_path": "the artefact/clayverse/store.py",
        "unifieddb_blob_sha": "a88d923ea3d0eab5847f304f35463e5a2b2c4acd",
        "unifieddb_schema_version": "6",
        "api_version": "ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
    },
    "current_epoch_basis": {
        "schema_version": "9.13",
        "selected_delta": "9.13AJ_NON_AUTHORITY",
        "authority_change": False,
    },
    "resolution": {
        "current_epoch_authority_binding_verified": True,
        "implementation_tuple_changed": False,
        "new_effect_authority_created": False,
        "authority_broadened": False,
    },
}


def load_binding(binding_doc=BINDING, attestation_doc=ATTESTATION):
    return load_current_entityos_effect_authority_binding(
        binding_document=binding_doc,
        binding_record_path=BINDING_PATH,
        binding_record_blob_sha=BINDING_BLOB,
        binding_record_commit_sha=BINDING_COMMIT,
        attestation_document=attestation_doc,
        attestation_path=ATTESTATION_PATH,
        attestation_commit_sha=ATTESTATION_COMMIT,
    )


def effect_request() -> EffectRequestIdentity:
    return EffectRequestIdentity(
        user_id="user-A",
        session_id="session-A",
        capability="entityos.exec",
        target="target-A",
        argv=("run", "payload-A"),
        expected_generation=7,
    )


def intent() -> EffectCallIntent:
    return EffectCallIntent(
        return_id=None,
        binding_id="binding-A",
        invocation_id="invocation-A",
        tool_use_id="tool-A",
        delegation_id="delegation-A",
        child_identity_sha256=CHILD_SHA,
        request=effect_request(),
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
            result_id="result-A",
            result_sha256=RESULT_SHA,
            request_sha256=prepared.request_sha256,
        )


def evidence_for(call, binding, decision, *, journal_state=None, effect_id=None):
    if journal_state is None:
        journal_state = "PENDING" if decision is ExternalGateDecision.ALLOW else "NO_EFFECT"
    if effect_id is None and decision is ExternalGateDecision.ALLOW:
        effect_id = "canonical-effect-A"
    return CanonicalEffectAuthorityEvidence(
        authority=binding.bridge_identity(),
        decision_id=f"decision-{decision.value}",
        decision=decision,
        journal_state=journal_state,
        effect_id=effect_id,
        return_id=call.return_id,
        binding_id=call.binding_id,
        invocation_id=call.invocation_id,
        tool_use_id=call.tool_use_id,
        delegation_id=call.delegation_id,
        child_identity_sha256=call.child_identity_sha256,
        request_sha256=call.request_sha256,
    )


class CurrentEntityOSEffectAuthorityMatrixTests(unittest.TestCase):
    def test_exact_current_epoch_binding_allows_only_pending_allow(self) -> None:
        binding = load_binding()
        call = intent()
        executor = RecordingExecutor()
        result = dispatch_with_current_entityos_authority(
            call,
            binding=binding,
            authorize=lambda item: evidence_for(
                item, binding, ExternalGateDecision.ALLOW
            ),
            executor=executor,
        )
        self.assertTrue(result.dispatched)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(executor.calls[0].effect_id, "canonical-effect-A")
        self.assertEqual(executor.calls[0].request_sha256, call.request_sha256)
        self.assertEqual(binding.supervisor_epoch, "9.13")
        self.assertEqual(binding.supervisor_delta, "9.13AJ_NON_AUTHORITY")
        self.assertEqual(
            binding.effect_journal_blob_sha,
            "cda63471f1467481f2ff79032d3931730a334a20",
        )

    def test_every_non_allow_and_restart_unknown_is_zero_dispatch(self) -> None:
        binding = load_binding()
        call = intent()
        for decision in (
            ExternalGateDecision.DENY,
            ExternalGateDecision.REQUIRE_CONFIRMATION,
            ExternalGateDecision.DEGRADE_TO_PROPOSAL,
            ExternalGateDecision.UNKNOWN,
        ):
            with self.subTest(decision=decision.value):
                executor = RecordingExecutor()
                result = dispatch_with_current_entityos_authority(
                    call,
                    binding=binding,
                    authorize=lambda item, d=decision: evidence_for(item, binding, d),
                    executor=executor,
                )
                self.assertFalse(result.dispatched)
                self.assertEqual(executor.calls, [])

        executor = RecordingExecutor()
        result = dispatch_with_current_entityos_authority(
            call,
            binding=binding,
            authorize=lambda item: evidence_for(
                item,
                binding,
                ExternalGateDecision.UNKNOWN,
                journal_state="UNKNOWN_AFTER_RESTART",
                effect_id="canonical-effect-prior",
            ),
            executor=executor,
        )
        self.assertFalse(result.dispatched)
        self.assertEqual(executor.calls, [])

    def test_binding_or_epoch_mismatch_fails_before_dispatch(self) -> None:
        bad_binding = copy.deepcopy(BINDING)
        bad_binding["implementation_identity"]["effect_journal"]["blob_sha"] = "9" * 40
        with self.assertRaisesRegex(
            CurrentEntityOSEffectAuthorityBindingError,
            "EFFECT_JOURNAL_BLOB_SHA_MISMATCH",
        ):
            load_binding(binding_doc=bad_binding)

        bad_attestation = copy.deepcopy(ATTESTATION)
        bad_attestation["current_epoch_basis"]["authority_change"] = True
        with self.assertRaisesRegex(
            CurrentEntityOSEffectAuthorityBindingError,
            "CURRENT_EPOCH_AUTHORITY_CHANGED",
        ):
            load_binding(attestation_doc=bad_attestation)

    def test_executor_success_still_requires_separate_world_verification(self) -> None:
        binding = load_binding()
        call = intent()
        executor = RecordingExecutor()
        result = dispatch_with_current_entityos_authority(
            call,
            binding=binding,
            authorize=lambda item: evidence_for(
                item, binding, ExternalGateDecision.ALLOW
            ),
            executor=executor,
        )
        self.assertTrue(result.dispatched)
        prepared = executor.calls[0]
        self.assertEqual(prepared.request_sha256, call.request_sha256)

        lineage = ExecutionLineage.requested(
            causal_id="causal-A",
            generation=7,
            request_id="request-A",
        )
        lineage = apply_execution_transition(
            lineage,
            AdmitExecution(
                transition_id="transition-admit-A",
                causal_id="causal-A",
                generation=7,
                request_id="request-A",
                admission_id="admission-A",
            ),
        )
        receipt = StructuredExecutionReceipt(
            receipt_id="receipt-A",
            effect_id=prepared.effect_id,
            binding_id=prepared.binding_id,
            invocation_id=prepared.invocation_id,
            tool_use_id=prepared.tool_use_id,
            delegation_id=prepared.delegation_id,
            child_identity_sha256=prepared.child_identity_sha256,
            causal_id="causal-A",
            generation=7,
            request_id="request-A",
            admission_id="admission-A",
            execution_attempt_id="execution-attempt-A",
            raw_status="SUCCEEDED",
            result_id="result-A",
            result_sha256=RESULT_SHA,
            request_sha256=prepared.request_sha256,
        )
        observed = apply_structured_execution_receipt(prepared, lineage, receipt)
        self.assertEqual(observed.observed_call.request_sha256, prepared.request_sha256)
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

        indeterminate = apply_execution_transition(
            observed.lineage,
            VerifyExecution(
                transition_id="transition-verify-A-1",
                causal_id="causal-A",
                generation=7,
                request_id="request-A",
                admission_id="admission-A",
                execution_attempt_id="execution-attempt-A",
                verification_attempt_id="verification-A-1",
                outcome=VerificationOutcome.INDETERMINATE,
            ),
        )
        self.assertEqual(indeterminate.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(indeterminate.is_verified_complete)

        verified = apply_execution_transition(
            indeterminate,
            VerifyExecution(
                transition_id="transition-verify-A-2",
                causal_id="causal-A",
                generation=7,
                request_id="request-A",
                admission_id="admission-A",
                execution_attempt_id="execution-attempt-A",
                verification_attempt_id="verification-A-2",
                outcome=VerificationOutcome.APPLIED,
            ),
        )
        self.assertEqual(verified.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertTrue(verified.is_verified_complete)


if __name__ == "__main__":
    unittest.main(verbosity=2)
