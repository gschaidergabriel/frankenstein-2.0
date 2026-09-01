"""REVIEW_ONLY discriminator: current EntityOS effect authority -> WP105 -> WP900.

This exercises only existing authorities and typed contracts. It demonstrates the
currently unsatisfied cross-component type boundary: a valid WP105
DeferredExecutionVerificationTarget is necessarily EXECUTION_RECORDED, while WP900
requires that same concrete target type to carry VERIFIED_APPLIED before it can admit
EFFECT_VERIFIED_APPLIED. No authority or adapter is invented to bridge the mismatch.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_current_entityos_effect_authority_binding import evidence_for, load_binding  # noqa: E402
from test_deferred_execution_verification import execution_record, make_return  # noqa: E402

from frankenstein2.canonical_effect_authority_bridge import EffectCallIntent  # noqa: E402
from frankenstein2.current_entityos_effect_authority_binding import dispatch_with_current_entityos_authority  # noqa: E402
from frankenstein2.deferred_execution_verification import DeferredExecutionVerificationTarget  # noqa: E402
from frankenstein2.effect_executor_interlock import ExecutorObservation, ExternalGateDecision  # noqa: E402
from frankenstein2.effect_request_identity import EffectRequestIdentity  # noqa: E402
from frankenstein2.whole_persistent_loop import (  # noqa: E402
    EFFECT_VERIFIED_APPLIED,
    LoopOutcomeEvidence,
    WholePersistentLoopError,
)
from state.execution_completion import ExecutionStage  # noqa: E402


class ExactResultExecutor:
    def __init__(self, *, result_id: str, result_sha256: str) -> None:
        self.result_id = result_id
        self.result_sha256 = result_sha256

    def __call__(self, prepared):
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


class CurrentEffectAuthorityWp900VerifiedIntegrationTests(unittest.TestCase):
    def test_valid_wp105_target_cannot_enter_wp900_as_verified_applied(self) -> None:
        returned = make_return(
            suffix="WP900",
            task_id="task-wp900-effect",
            turn_id="turn-wp900-effect",
        )
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
        dispatched = dispatch_with_current_entityos_authority(
            intent,
            binding=binding,
            authorize=lambda item: evidence_for(
                item,
                binding,
                ExternalGateDecision.ALLOW,
                effect_id="canonical-effect-wp900-verified",
            ),
            executor=ExactResultExecutor(
                result_id=returned.binding.result_id,
                result_sha256=returned.binding.result_sha256,
            ),
        )
        self.assertTrue(dispatched.dispatched)
        self.assertIsNotNone(dispatched.interlock)
        observed = dispatched.interlock.observed
        self.assertIsNotNone(observed)
        assert observed is not None
        self.assertEqual(observed.binding_id, returned.binding.binding_id())
        self.assertEqual(observed.result_id, returned.binding.result_id)
        self.assertEqual(observed.result_sha256, returned.binding.result_sha256)

        target = DeferredExecutionVerificationTarget(
            returned=returned,
            lineage=execution_record(returned),
        )
        self.assertIs(target.lineage.stage, ExecutionStage.EXECUTION_RECORDED)

        with self.assertRaisesRegex(
            WholePersistentLoopError,
            "verified outcome status does not match WP-105 lineage stage",
        ):
            LoopOutcomeEvidence(
                outcome_id="outcome-wp900-effect-verified",
                status=EFFECT_VERIFIED_APPLIED,
                effect_call=observed,
                verification_target=target,
                provenance_refs=(
                    binding.current_epoch_attestation_path,
                    "review:current-effect-authority-wp105-wp900",
                ),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
