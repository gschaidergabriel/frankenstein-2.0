import unittest

from src.frankenstein2.perception_dashboard import (
    BASELINE_HIGH_SENSITIVITY_CAPTURE_EXCLUDED,
    DashboardAuditAction,
    ObservationExecutionResult,
    PerceptionAuditCursor,
    WorkerVisibility,
    apply_global_pause,
    apply_source_policy,
    build_visibility_snapshot,
    compile_permission_snapshot_with_audit,
    record_observation_execution,
    revoke_capabilities,
)
from src.frankenstein2.perception_dashboard_policy import (
    PerceptionDashboardError,
    create_dashboard_state,
)
from src.frankenstein2.perception_fabric import PerceptionCapability


P = ("test:wp713",)


class PerceptionDashboardAuditTests(unittest.TestCase):
    def _state_with_camera(self):
        state = create_dashboard_state(
            state_id="dashboard:wp713",
            max_active_cortex_workers=4,
            provenance_refs=P,
        )
        state, receipt, cursor = apply_source_policy(
            state=state,
            cursor=PerceptionAuditCursor(),
            source_id="camera:front",
            enabled=True,
            capabilities=(
                PerceptionCapability.SEE,
                PerceptionCapability.ANALYZE,
                PerceptionCapability.MEMORY,
                PerceptionCapability.REMOTE_FRAME,
                PerceptionCapability.EXTERNAL_VLM,
            ),
            actor_id="owner:test",
            reason="enable camera for bounded test",
            monotonic_ns=10,
            provenance_refs=P,
        )
        return state, receipt, cursor

    def test_policy_mutation_receipt_binds_exact_before_after_and_chain(self):
        state = create_dashboard_state(state_id="dashboard:wp713", provenance_refs=P)
        before_sha = state.sha256()
        state, first, cursor = apply_source_policy(
            state=state,
            cursor=PerceptionAuditCursor(),
            source_id="screen:main",
            enabled=True,
            capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
            actor_id="owner:test",
            reason="enable screen",
            monotonic_ns=100,
            provenance_refs=P,
        )
        self.assertEqual(first.action, DashboardAuditAction.SET_SOURCE_POLICY)
        self.assertEqual(first.sequence, 0)
        self.assertEqual(first.dashboard_state_sha256_before, before_sha)
        self.assertEqual(first.dashboard_state_sha256_after, state.sha256())
        self.assertIsNone(first.prior_receipt_sha256)

        state, second, cursor = apply_global_pause(
            state=state,
            cursor=cursor,
            paused=True,
            actor_id="owner:test",
            reason="privacy pause",
            monotonic_ns=101,
            provenance_refs=P,
        )
        self.assertEqual(second.sequence, 1)
        self.assertEqual(second.prior_receipt_sha256, first.sha256())
        self.assertEqual(cursor.next_sequence, 2)
        self.assertEqual(cursor.prior_receipt_sha256, second.sha256())

    def test_global_pause_uses_same_policy_authority_and_yields_zero_caps(self):
        state, _, cursor = self._state_with_camera()
        state, pause_receipt, cursor = apply_global_pause(
            state=state,
            cursor=cursor,
            paused=True,
            actor_id="owner:test",
            reason="pause all retina",
            monotonic_ns=20,
            provenance_refs=P,
        )
        snapshot, snap_receipt, _ = compile_permission_snapshot_with_audit(
            state=state,
            cursor=cursor,
            source_id="camera:front",
            valid_from_monotonic_ns=20,
            expires_monotonic_ns=100,
            actor_id="dashboard:test",
            reason="prove effective paused authority",
            monotonic_ns=20,
            provenance_refs=P,
        )
        self.assertTrue(state.global_pause)
        self.assertEqual(snapshot.capabilities, ())
        self.assertEqual(snap_receipt.permission_snapshot_sha256, snapshot.sha256())
        self.assertEqual(pause_receipt.dashboard_state_sha256_after, state.sha256())
        self.assertIn(f"dashboard-state-sha256:{state.sha256()}", snapshot.provenance_refs)

    def test_per_source_revocation_removes_remote_and_external_vlm(self):
        state, _, cursor = self._state_with_camera()
        state, receipt, cursor = revoke_capabilities(
            state=state,
            cursor=cursor,
            source_id="camera:front",
            capabilities=(PerceptionCapability.REMOTE_FRAME, PerceptionCapability.EXTERNAL_VLM),
            actor_id="owner:test",
            reason="local only",
            monotonic_ns=20,
            provenance_refs=P,
        )
        snapshot, _, _ = compile_permission_snapshot_with_audit(
            state=state,
            cursor=cursor,
            source_id="camera:front",
            valid_from_monotonic_ns=20,
            expires_monotonic_ns=100,
            actor_id="dashboard:test",
            reason="verify revocation",
            monotonic_ns=20,
            provenance_refs=P,
        )
        self.assertEqual(receipt.action, DashboardAuditAction.REVOKE_CAPABILITIES)
        self.assertTrue(snapshot.allows(PerceptionCapability.SEE))
        self.assertTrue(snapshot.allows(PerceptionCapability.ANALYZE))
        self.assertFalse(snapshot.allows(PerceptionCapability.REMOTE_FRAME))
        self.assertFalse(snapshot.allows(PerceptionCapability.EXTERNAL_VLM))

    def test_revoking_see_closes_capability_dependency_chain(self):
        state, _, cursor = self._state_with_camera()
        state, _, _ = revoke_capabilities(
            state=state,
            cursor=cursor,
            source_id="camera:front",
            capabilities=(PerceptionCapability.SEE,),
            actor_id="owner:test",
            reason="revoke sight",
            monotonic_ns=20,
            provenance_refs=P,
        )
        self.assertEqual(state.policy_for("camera:front").capabilities, ())

    def test_observation_execution_receipt_requires_current_dashboard_bound_snapshot(self):
        state, _, cursor = self._state_with_camera()
        snapshot, _, cursor = compile_permission_snapshot_with_audit(
            state=state,
            cursor=cursor,
            source_id="camera:front",
            valid_from_monotonic_ns=20,
            expires_monotonic_ns=100,
            actor_id="dashboard:test",
            reason="admit observation",
            monotonic_ns=20,
            provenance_refs=P,
        )
        receipt, cursor = record_observation_execution(
            state=state,
            cursor=cursor,
            snapshot=snapshot,
            worker_id="cortex:0",
            result=ObservationExecutionResult.EXECUTED,
            actor_id="scheduler:test",
            reason="targeted rel-look",
            monotonic_ns=21,
            provenance_refs=P,
        )
        self.assertEqual(receipt.action, DashboardAuditAction.OBSERVATION_EXECUTION)
        self.assertEqual(receipt.permission_snapshot_sha256, snapshot.sha256())
        self.assertEqual(receipt.worker_id, "cortex:0")

        newer_state, _, _ = apply_global_pause(
            state=state,
            cursor=cursor,
            paused=True,
            actor_id="owner:test",
            reason="revoke after queueing",
            monotonic_ns=22,
            provenance_refs=P,
        )
        with self.assertRaisesRegex(PerceptionDashboardError, "not bound to the current dashboard state"):
            record_observation_execution(
                state=newer_state,
                cursor=cursor,
                snapshot=snapshot,
                worker_id="cortex:0",
                result=ObservationExecutionResult.EXECUTED,
                actor_id="scheduler:test",
                reason="stale execution must fail",
                monotonic_ns=23,
                provenance_refs=P,
            )

    def test_visibility_is_headless_bounded_and_reason_visible(self):
        state, _, _ = self._state_with_camera()
        view = build_visibility_snapshot(
            state=state,
            workers=(
                WorkerVisibility(worker_id="cortex:0", source_id="camera:front", reason="motion delta"),
                WorkerVisibility(worker_id="cortex:1", source_id="camera:front", reason="uncertainty rel-look"),
            ),
            provenance_refs=P,
        )
        self.assertEqual(view.dashboard_state_sha256, state.sha256())
        self.assertEqual(len(view.workers), 2)
        source = view.sources[0]
        self.assertEqual(source.active_worker_ids, ("cortex:0", "cortex:1"))
        self.assertEqual(source.reasons, ("motion delta", "uncertainty rel-look"))
        self.assertEqual(view.as_dict()["world_truth_authority"], "NONE")
        self.assertEqual(view.as_dict()["effect_authority"], "NONE")

    def test_visibility_rejects_worker_over_ceiling_and_unknown_source(self):
        state, _, _ = self._state_with_camera()
        too_many = tuple(
            WorkerVisibility(worker_id=f"cortex:{i}", source_id="camera:front", reason="load")
            for i in range(5)
        )
        with self.assertRaisesRegex(PerceptionDashboardError, "exceed"):
            build_visibility_snapshot(state=state, workers=too_many, provenance_refs=P)
        with self.assertRaisesRegex(PerceptionDashboardError, "unknown source"):
            build_visibility_snapshot(
                state=state,
                workers=(WorkerVisibility(worker_id="cortex:0", source_id="camera:missing", reason="bad route"),),
                provenance_refs=P,
            )

    def test_global_pause_requires_zero_active_workers_in_visibility(self):
        state, _, cursor = self._state_with_camera()
        state, _, _ = apply_global_pause(
            state=state,
            cursor=cursor,
            paused=True,
            actor_id="owner:test",
            reason="privacy pause",
            monotonic_ns=20,
            provenance_refs=P,
        )
        with self.assertRaisesRegex(PerceptionDashboardError, "global pause"):
            build_visibility_snapshot(
                state=state,
                workers=(WorkerVisibility(worker_id="cortex:0", source_id="camera:front", reason="must stop"),),
                provenance_refs=P,
            )

    def test_baseline_excludes_keylogging_clipboard_and_password_capture(self):
        state, _, _ = self._state_with_camera()
        view = build_visibility_snapshot(state=state, workers=(), provenance_refs=P)
        self.assertEqual(
            view.baseline_high_sensitivity_capture_excluded,
            ("CLIPBOARD_CONTENT", "PASSWORD_FIELD_CONTENT", "RAW_KEYSTROKES"),
        )
        self.assertEqual(view.baseline_high_sensitivity_capture_excluded, BASELINE_HIGH_SENSITIVITY_CAPTURE_EXCLUDED)

    def test_unknown_source_cannot_be_revoked_or_snapshotted(self):
        state = create_dashboard_state(state_id="dashboard:wp713", provenance_refs=P)
        with self.assertRaisesRegex(PerceptionDashboardError, "no dashboard policy"):
            revoke_capabilities(
                state=state,
                cursor=PerceptionAuditCursor(),
                source_id="camera:missing",
                capabilities=(PerceptionCapability.SEE,),
                actor_id="owner:test",
                reason="fail closed",
                monotonic_ns=1,
                provenance_refs=P,
            )


if __name__ == "__main__":
    unittest.main()
