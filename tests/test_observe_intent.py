from __future__ import annotations

import dataclasses
import unittest

from frankenstein2.observe_intent import (
    ObserveIntentError,
    VisualNeed,
    build_observe_intent,
    validate_observe_intent_for_execution,
)
from frankenstein2.retina_fanin import RetinaPermissionSnapshot, RetinaSourcePermission

D64_B = "b" * 64


class ForgedSnapshot(RetinaPermissionSnapshot):
    pass


class ObserveIntentTests(unittest.TestCase):
    def permission(
        self,
        *,
        source_id: str = "screen-main",
        capture: bool = True,
        cognition: bool = True,
        persistence: bool = False,
    ) -> RetinaSourcePermission:
        return RetinaSourcePermission(
            source_id=source_id,
            source_kind="SCREEN",
            locator_ref=f"source-ref:{source_id}",
            capture_allowed=capture,
            cognition_allowed=cognition,
            persistence_allowed=persistence,
            provenance_refs=(f"permission:{source_id}",),
        )

    def snapshot(
        self,
        permission: RetinaSourcePermission,
        *,
        snapshot_id: str = "dashboard-permissions-12",
        generation: int = 12,
        epoch: str = "owner-epoch-12",
    ) -> RetinaPermissionSnapshot:
        return RetinaPermissionSnapshot(
            snapshot_id=snapshot_id,
            generation=generation,
            permission_epoch=epoch,
            permission_authority_ref="canonical:user-permission-writer",
            permissions=(permission,),
            provenance_refs=(f"dashboard:receipt-{generation}",),
        )

    def need(self, **overrides) -> VisualNeed:
        values = {
            "need_id": "visual-need-77",
            "cycle_id": "grid-cycle-77",
            "generation": 3,
            "source_id": "screen-main",
            "roi_ref": "roi:browser-primary",
            "requested_head_ids": ("ui-layout", "quality"),
            "target_world_atom_ids": ("atom:active-page",),
            "reason_refs": ("uncertainty:active-page",),
            "max_age_ms": 250,
            "deadline_monotonic_ns": 2_000_000,
            "priority": 80,
            "max_compute_ms": 40,
            "memory_write_requested": False,
            "raw_payload_requested": False,
            "remote_frame_requested": False,
            "external_vlm_requested": False,
            "provenance_refs": ("world-slice:77",),
        }
        values.update(overrides)
        return VisualNeed(**values)

    def build(
        self,
        need: VisualNeed,
        snapshot: RetinaPermissionSnapshot,
        *,
        admitted_ns: int = 1_000_000,
    ):
        return build_observe_intent(
            intent_id="observe-intent-77",
            visual_need=need,
            permission_snapshot=snapshot,
            expected_permission_snapshot_sha256=snapshot.sha256(),
            admitted_monotonic_ns=admitted_ns,
            provenance_refs=("compiler:wp708",),
        )

    def test_visual_need_compiles_without_capture_and_binds_exact_snapshot(self) -> None:
        snapshot = self.snapshot(self.permission())
        need = self.need()
        intent = self.build(need, snapshot)
        data = intent.as_dict()
        self.assertEqual(intent.need_sha256, need.sha256())
        self.assertEqual(intent.permission_snapshot_sha256, snapshot.sha256())
        self.assertEqual(intent.permission_snapshot_generation, snapshot.generation)
        self.assertEqual(intent.source_permission_sha256, snapshot.permissions[0].sha256())
        self.assertEqual(intent.requested_head_ids, ("quality", "ui-layout"))
        self.assertEqual(data["capture_performed"], False)
        self.assertEqual(data["analysis_performed"], False)
        self.assertEqual(data["truth_authority"], "NONE")
        self.assertEqual(data["effect_authority"], "NONE")
        self.assertEqual(data["completion_authority"], "NONE")

    def test_input_order_normalization_keeps_visual_need_digest_deterministic(self) -> None:
        left = self.need(
            requested_head_ids=("ui-layout", "quality"),
            target_world_atom_ids=("atom:z", "atom:a"),
            reason_refs=("reason:z", "reason:a"),
            provenance_refs=("prov:z", "prov:a"),
        )
        right = self.need(
            requested_head_ids=("quality", "ui-layout"),
            target_world_atom_ids=("atom:a", "atom:z"),
            reason_refs=("reason:a", "reason:z"),
            provenance_refs=("prov:a", "prov:z"),
        )
        self.assertEqual(left.sha256(), right.sha256())

    def test_permission_snapshot_digest_mismatch_fails_closed(self) -> None:
        snapshot = self.snapshot(self.permission())
        with self.assertRaisesRegex(ObserveIntentError, "permission snapshot digest mismatch"):
            build_observe_intent(
                intent_id="observe-intent-77",
                visual_need=self.need(),
                permission_snapshot=snapshot,
                expected_permission_snapshot_sha256=D64_B,
                admitted_monotonic_ns=1_000_000,
                provenance_refs=("compiler:wp708",),
            )

    def test_unknown_source_fails_closed(self) -> None:
        snapshot = self.snapshot(self.permission(source_id="camera-front"))
        with self.assertRaisesRegex(ObserveIntentError, "absent from exact permission snapshot"):
            self.build(self.need(), snapshot)

    def test_capture_or_cognition_denial_cannot_be_broadened(self) -> None:
        denied_capture = self.snapshot(self.permission(capture=False, cognition=True))
        with self.assertRaisesRegex(ObserveIntentError, "capture permission is denied"):
            self.build(self.need(), denied_capture)
        denied_cognition = self.snapshot(self.permission(capture=True, cognition=False))
        with self.assertRaisesRegex(ObserveIntentError, "cognition permission is denied"):
            self.build(self.need(), denied_cognition)

    def test_memory_request_requires_existing_persistence_permission(self) -> None:
        denied = self.snapshot(self.permission(persistence=False))
        with self.assertRaisesRegex(ObserveIntentError, "persistence permission is denied"):
            self.build(self.need(memory_write_requested=True), denied)
        allowed = self.snapshot(self.permission(persistence=True))
        intent = self.build(self.need(memory_write_requested=True), allowed)
        self.assertTrue(intent.memory_write_allowed)

    def test_unrepresented_high_sensitivity_capabilities_fail_closed(self) -> None:
        snapshot = self.snapshot(self.permission(persistence=True))
        cases = (
            ("raw_payload_requested", "RAW_RETENTION"),
            ("remote_frame_requested", "REMOTE_FRAME"),
            ("external_vlm_requested", "EXTERNAL_VLM"),
        )
        for field, capability in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(ObserveIntentError, capability):
                    self.build(self.need(**{field: True}), snapshot)

    def test_expired_need_cannot_be_compiled(self) -> None:
        snapshot = self.snapshot(self.permission())
        with self.assertRaisesRegex(ObserveIntentError, "expired at ObserveIntent admission"):
            self.build(self.need(deadline_monotonic_ns=1_000_000), snapshot, admitted_ns=1_000_000)

    def test_execution_revalidation_accepts_only_same_current_snapshot_before_deadline(self) -> None:
        snapshot = self.snapshot(self.permission(persistence=True))
        intent = self.build(self.need(memory_write_requested=True), snapshot)
        check = validate_observe_intent_for_execution(
            intent=intent,
            current_permission_snapshot=snapshot,
            expected_current_permission_snapshot_sha256=snapshot.sha256(),
            checked_monotonic_ns=1_500_000,
        )
        self.assertTrue(check.capture_allowed)
        self.assertTrue(check.cognition_allowed)
        self.assertTrue(check.memory_write_allowed)
        self.assertFalse(check.raw_payload_allowed)
        self.assertFalse(check.remote_frame_allowed)
        self.assertFalse(check.external_vlm_allowed)
        self.assertFalse(check.as_dict()["execution_performed"])

    def test_permission_revocation_or_generation_change_invalidates_queued_intent(self) -> None:
        original = self.snapshot(self.permission(persistence=True))
        intent = self.build(self.need(memory_write_requested=True), original)

        revoked = self.snapshot(
            self.permission(capture=False, cognition=False, persistence=False),
            snapshot_id="dashboard-permissions-13",
            generation=13,
            epoch="owner-epoch-13",
        )
        with self.assertRaisesRegex(ObserveIntentError, "snapshot identity changed|snapshot generation changed|snapshot changed"):
            validate_observe_intent_for_execution(
                intent=intent,
                current_permission_snapshot=revoked,
                expected_current_permission_snapshot_sha256=revoked.sha256(),
                checked_monotonic_ns=1_500_000,
            )

        equivalent_new_generation = self.snapshot(
            self.permission(persistence=True),
            snapshot_id="dashboard-permissions-13",
            generation=13,
            epoch="owner-epoch-13",
        )
        with self.assertRaisesRegex(ObserveIntentError, "snapshot identity changed|snapshot generation changed|snapshot changed"):
            validate_observe_intent_for_execution(
                intent=intent,
                current_permission_snapshot=equivalent_new_generation,
                expected_current_permission_snapshot_sha256=equivalent_new_generation.sha256(),
                checked_monotonic_ns=1_500_000,
            )

    def test_expired_intent_is_non_replayable_after_delay_or_reconnect(self) -> None:
        snapshot = self.snapshot(self.permission())
        intent = self.build(self.need(deadline_monotonic_ns=2_000_000), snapshot)
        with self.assertRaisesRegex(ObserveIntentError, "expired before execution"):
            validate_observe_intent_for_execution(
                intent=intent,
                current_permission_snapshot=snapshot,
                expected_current_permission_snapshot_sha256=snapshot.sha256(),
                checked_monotonic_ns=2_000_000,
            )

    def test_current_snapshot_expected_digest_is_separately_verified(self) -> None:
        snapshot = self.snapshot(self.permission())
        intent = self.build(self.need(), snapshot)
        with self.assertRaisesRegex(ObserveIntentError, "current permission snapshot digest mismatch"):
            validate_observe_intent_for_execution(
                intent=intent,
                current_permission_snapshot=snapshot,
                expected_current_permission_snapshot_sha256=D64_B,
                checked_monotonic_ns=1_500_000,
            )

    def test_forged_snapshot_subclass_is_rejected_at_both_boundaries(self) -> None:
        forged = ForgedSnapshot(
            snapshot_id="forged",
            generation=1,
            permission_epoch="forged-epoch",
            permission_authority_ref="forged-authority",
            permissions=(self.permission(),),
            provenance_refs=("forged",),
        )
        with self.assertRaisesRegex(ObserveIntentError, "concrete RetinaPermissionSnapshot"):
            self.build(self.need(), forged)

        real = self.snapshot(self.permission())
        intent = self.build(self.need(), real)
        with self.assertRaisesRegex(ObserveIntentError, "concrete RetinaPermissionSnapshot"):
            validate_observe_intent_for_execution(
                intent=intent,
                current_permission_snapshot=forged,
                expected_current_permission_snapshot_sha256=forged.sha256(),
                checked_monotonic_ns=1_500_000,
            )

    def test_forged_capability_on_intent_is_rejected_before_execution(self) -> None:
        snapshot = self.snapshot(self.permission())
        intent = self.build(self.need(), snapshot)
        forged = dataclasses.replace(intent, remote_frame_allowed=True)
        with self.assertRaisesRegex(ObserveIntentError, "capability not provable"):
            validate_observe_intent_for_execution(
                intent=forged,
                current_permission_snapshot=snapshot,
                expected_current_permission_snapshot_sha256=snapshot.sha256(),
                checked_monotonic_ns=1_500_000,
            )


if __name__ == "__main__":
    unittest.main()
