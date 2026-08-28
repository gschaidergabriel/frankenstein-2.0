#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "state" / "execution_completion.py"
SPEC = importlib.util.spec_from_file_location("f2_execution_completion", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def requested(*, generation: int = 2):
    return mod.ExecutionLineage.requested(
        causal_id="cause-17",
        generation=generation,
        request_id="request-17",
    )


def admit(record=None):
    record = requested() if record is None else record
    return mod.apply_execution_transition(
        record,
        mod.AdmitExecution(
            transition_id="transition-admit",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id="admission-17",
        ),
    )


def executed(*, outcome=mod.ExecutionOutcome.UNKNOWN):
    record = admit()
    return mod.apply_execution_transition(
        record,
        mod.RecordExecution(
            transition_id="transition-exec",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id=record.admission_id,
            execution_attempt_id="exec-attempt-17",
            outcome=outcome,
        ),
    )


class ExecutionCompletionLineageTests(unittest.TestCase):
    def test_request_is_not_completion(self):
        record = requested()
        self.assertEqual(record.stage, mod.ExecutionStage.REQUESTED)
        self.assertFalse(record.is_verified_complete)
        self.assertEqual(
            record.replay_disposition,
            mod.ReplayDisposition.NOT_APPLICABLE_PRE_EXECUTION,
        )

    def test_reported_success_is_still_not_verified_completion(self):
        record = executed(outcome=mod.ExecutionOutcome.REPORTED_SUCCESS)
        self.assertEqual(record.stage, mod.ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(record.is_verified_complete)
        self.assertEqual(
            record.replay_disposition,
            mod.ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )

    def test_unknown_external_outcome_stays_unknown_and_blocks_blind_replay(self):
        record = executed(outcome=mod.ExecutionOutcome.UNKNOWN)
        self.assertEqual(record.execution_outcome, mod.ExecutionOutcome.UNKNOWN)
        self.assertFalse(record.is_verified_complete)
        self.assertEqual(
            record.replay_disposition,
            mod.ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )

    def test_indeterminate_verification_does_not_mint_completion(self):
        record = executed()
        checked = mod.apply_execution_transition(
            record,
            mod.VerifyExecution(
                transition_id="transition-verify-1",
                causal_id=record.causal_id,
                generation=record.generation,
                request_id=record.request_id,
                admission_id=record.admission_id,
                execution_attempt_id=record.execution_attempt_id,
                verification_attempt_id="verify-attempt-1",
                outcome=mod.VerificationOutcome.INDETERMINATE,
            ),
        )
        self.assertEqual(checked.stage, mod.ExecutionStage.EXECUTION_RECORDED)
        self.assertEqual(
            checked.verification_outcome,
            mod.VerificationOutcome.INDETERMINATE,
        )
        self.assertFalse(checked.is_verified_complete)
        self.assertEqual(
            checked.replay_disposition,
            mod.ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME,
        )

    def test_verified_applied_blocks_replay(self):
        record = executed(outcome=mod.ExecutionOutcome.REPORTED_SUCCESS)
        verified = mod.apply_execution_transition(
            record,
            mod.VerifyExecution(
                transition_id="transition-verify-applied",
                causal_id=record.causal_id,
                generation=record.generation,
                request_id=record.request_id,
                admission_id=record.admission_id,
                execution_attempt_id=record.execution_attempt_id,
                verification_attempt_id="verify-applied",
                outcome=mod.VerificationOutcome.APPLIED,
            ),
        )
        self.assertTrue(verified.is_verified_complete)
        self.assertEqual(verified.stage, mod.ExecutionStage.VERIFIED_APPLIED)
        self.assertEqual(
            verified.replay_disposition,
            mod.ReplayDisposition.FORBIDDEN_ALREADY_APPLIED,
        )

    def test_verified_not_applied_only_allows_new_explicit_request(self):
        record = executed(outcome=mod.ExecutionOutcome.REPORTED_FAILURE)
        verified = mod.apply_execution_transition(
            record,
            mod.VerifyExecution(
                transition_id="transition-verify-not-applied",
                causal_id=record.causal_id,
                generation=record.generation,
                request_id=record.request_id,
                admission_id=record.admission_id,
                execution_attempt_id=record.execution_attempt_id,
                verification_attempt_id="verify-not-applied",
                outcome=mod.VerificationOutcome.NOT_APPLIED,
            ),
        )
        self.assertTrue(verified.is_verified_complete)
        self.assertEqual(verified.stage, mod.ExecutionStage.VERIFIED_NOT_APPLIED)
        self.assertEqual(
            verified.replay_disposition,
            mod.ReplayDisposition.ELIGIBLE_NEW_EXPLICIT_REQUEST,
        )

    def test_exact_transition_replay_is_idempotent(self):
        record = requested()
        transition = mod.AdmitExecution(
            transition_id="same-transition",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id="admission-17",
        )
        once = mod.apply_execution_transition(record, transition)
        twice = mod.apply_execution_transition(once, transition)
        self.assertEqual(once, twice)

    def test_same_transition_id_with_changed_payload_fails_closed(self):
        record = requested()
        original = mod.AdmitExecution(
            transition_id="same-transition",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id="admission-17",
        )
        once = mod.apply_execution_transition(record, original)
        mutated = mod.AdmitExecution(
            transition_id="same-transition",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id="admission-18",
        )
        with self.assertRaisesRegex(
            mod.ExecutionLineageError, "TRANSITION_ID_PAYLOAD_MISMATCH"
        ):
            mod.apply_execution_transition(once, mutated)

    def test_stale_generation_fails_closed(self):
        record = requested(generation=4)
        with self.assertRaisesRegex(mod.ExecutionLineageError, "STALE_GENERATION"):
            mod.apply_execution_transition(
                record,
                mod.AdmitExecution(
                    transition_id="transition-stale",
                    causal_id=record.causal_id,
                    generation=3,
                    request_id=record.request_id,
                    admission_id="admission-17",
                ),
            )

    def test_causal_mismatch_fails_closed(self):
        record = requested()
        with self.assertRaisesRegex(mod.ExecutionLineageError, "CAUSAL_ID_MISMATCH"):
            mod.apply_execution_transition(
                record,
                mod.AdmitExecution(
                    transition_id="transition-wrong-cause",
                    causal_id="different-cause",
                    generation=record.generation,
                    request_id=record.request_id,
                    admission_id="admission-17",
                ),
            )

    def test_verification_must_bind_exact_execution_attempt(self):
        record = executed()
        with self.assertRaisesRegex(
            mod.ExecutionLineageError, "EXECUTION_ATTEMPT_ID_MISMATCH"
        ):
            mod.apply_execution_transition(
                record,
                mod.VerifyExecution(
                    transition_id="transition-wrong-exec",
                    causal_id=record.causal_id,
                    generation=record.generation,
                    request_id=record.request_id,
                    admission_id=record.admission_id,
                    execution_attempt_id="other-exec-attempt",
                    verification_attempt_id="verify-1",
                    outcome=mod.VerificationOutcome.APPLIED,
                ),
            )

    def test_identity_roles_cannot_collapse(self):
        with self.assertRaisesRegex(mod.ExecutionLineageError, "IDENTITY_ROLE_COLLISION"):
            mod.ExecutionLineage(
                schema=mod.EXECUTION_LINEAGE_SCHEMA,
                causal_id="same-id",
                generation=0,
                request_id="same-id",
                stage=mod.ExecutionStage.REQUESTED,
            )

    def test_boolean_generation_rejected(self):
        with self.assertRaisesRegex(mod.ExecutionLineageError, "INVALID_GENERATION"):
            mod.ExecutionLineage.requested(
                causal_id="cause",
                generation=True,
                request_id="request",
            )

    def test_execution_cannot_skip_admission(self):
        record = requested()
        with self.assertRaisesRegex(mod.ExecutionLineageError, "EXECUTION_OUT_OF_ORDER"):
            mod.apply_execution_transition(
                record,
                mod.RecordExecution(
                    transition_id="transition-exec",
                    causal_id=record.causal_id,
                    generation=record.generation,
                    request_id=record.request_id,
                    admission_id="admission-17",
                    execution_attempt_id="exec-attempt-17",
                    outcome=mod.ExecutionOutcome.UNKNOWN,
                ),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
