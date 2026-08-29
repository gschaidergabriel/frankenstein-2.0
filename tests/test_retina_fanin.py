from __future__ import annotations

import dataclasses
import unittest

from frankenstein2.retina_fanin import (
    RetinaFanInError,
    RetinaFanInPolicy,
    RetinaPermissionSnapshot,
    RetinaSourcePermission,
    build_retina_fanin_plan,
)

D64_A = "a" * 64
D64_B = "b" * 64


class ForgedSnapshot(RetinaPermissionSnapshot):
    pass


class RetinaFanInTests(unittest.TestCase):
    def permission(
        self,
        source_id: str,
        source_kind: str,
        *,
        capture: bool = True,
        cognition: bool = True,
        persistence: bool = False,
    ) -> RetinaSourcePermission:
        return RetinaSourcePermission(
            source_id=source_id,
            source_kind=source_kind,
            locator_ref=f"source-ref:{source_id}",
            capture_allowed=capture,
            cognition_allowed=cognition,
            persistence_allowed=persistence,
            provenance_refs=(f"permission:{source_id}",),
        )

    def snapshot(self, *permissions: RetinaSourcePermission) -> RetinaPermissionSnapshot:
        return RetinaPermissionSnapshot(
            snapshot_id="dashboard-permissions-7",
            generation=7,
            permission_epoch="owner-epoch-7",
            permission_authority_ref="canonical:user-permission-writer",
            permissions=tuple(permissions),
            provenance_refs=("dashboard:receipt-7",),
        )

    def policy(self, priority: tuple[str, ...], *, max_workers: int = 4) -> RetinaFanInPolicy:
        return RetinaFanInPolicy(
            policy_id="fanin-policy-1",
            generation=1,
            max_parallel_workers=max_workers,
            priority_source_ids=priority,
            provenance_refs=("policy:retina-fanin",),
        )

    def plan(
        self,
        snapshot: RetinaPermissionSnapshot,
        policy: RetinaFanInPolicy,
        requested: tuple[str, ...],
    ):
        return build_retina_fanin_plan(
            plan_id="fanin-plan-1",
            permission_snapshot=snapshot,
            expected_permission_snapshot_sha256=snapshot.sha256(),
            policy=policy,
            expected_policy_sha256=policy.sha256(),
            requested_source_ids=requested,
            provenance_refs=("cycle:7",),
        )

    def test_four_parallel_permitted_sources_map_to_r1_through_r4(self) -> None:
        permissions = (
            self.permission("cam-front", "CAMERA", persistence=True),
            self.permission("screen-main", "SCREEN"),
            self.permission("page-work", "PAGE"),
            self.permission("activity-local", "USER_ACTIVITY"),
        )
        snapshot = self.snapshot(*permissions)
        policy = self.policy(("cam-front", "screen-main", "page-work", "activity-local"))
        plan = self.plan(snapshot, policy, ("activity-local", "page-work", "cam-front", "screen-main"))
        self.assertEqual(tuple(slot.slot_id for slot in plan.worker_slots), ("R1", "R2", "R3", "R4"))
        self.assertEqual(
            tuple(slot.source_id for slot in plan.worker_slots),
            ("cam-front", "screen-main", "page-work", "activity-local"),
        )
        self.assertEqual(plan.deferred_source_ids, ())
        self.assertEqual(plan.denied_source_ids, ())
        self.assertEqual(plan.as_dict()["workers_spawned"], 0)
        self.assertEqual(plan.as_dict()["sensors_opened"], 0)

    def test_fifth_eligible_source_is_deferred_not_silently_dropped(self) -> None:
        permissions = tuple(
            self.permission(f"cam-{i}", "CAMERA") for i in range(1, 6)
        )
        snapshot = self.snapshot(*permissions)
        priority = tuple(f"cam-{i}" for i in range(1, 6))
        plan = self.plan(snapshot, self.policy(priority), priority)
        self.assertEqual(len(plan.worker_slots), 4)
        self.assertEqual(plan.deferred_source_ids, ("cam-5",))
        self.assertEqual(plan.denied_source_ids, ())

    def test_capture_false_cannot_be_broadened_by_cognition_or_persistence(self) -> None:
        denied = self.permission(
            "screen-private",
            "SCREEN",
            capture=False,
            cognition=True,
            persistence=True,
        )
        allowed = self.permission("cam-front", "CAMERA")
        snapshot = self.snapshot(denied, allowed)
        policy = self.policy(("screen-private", "cam-front"))
        plan = self.plan(snapshot, policy, ("screen-private", "cam-front"))
        self.assertEqual(tuple(slot.source_id for slot in plan.worker_slots), ("cam-front",))
        self.assertEqual(plan.denied_source_ids, ("screen-private",))
        self.assertFalse(plan.as_dict()["permission_broadening"])

    def test_cognition_false_denies_retina_slot_even_when_capture_is_allowed(self) -> None:
        capture_only = self.permission("cam-record-only", "CAMERA", capture=True, cognition=False, persistence=True)
        snapshot = self.snapshot(capture_only)
        plan = self.plan(snapshot, self.policy(("cam-record-only",)), ("cam-record-only",))
        self.assertEqual(plan.worker_slots, ())
        self.assertEqual(plan.denied_source_ids, ("cam-record-only",))

    def test_persistence_flag_only_narrows_selected_slot(self) -> None:
        volatile = self.permission("cam-volatile", "CAMERA", persistence=False)
        persistent = self.permission("cam-persist", "CAMERA", persistence=True)
        snapshot = self.snapshot(volatile, persistent)
        policy = self.policy(("cam-volatile", "cam-persist"))
        plan = self.plan(snapshot, policy, ("cam-persist", "cam-volatile"))
        by_source = {slot.source_id: slot for slot in plan.worker_slots}
        self.assertFalse(by_source["cam-volatile"].persistence_allowed)
        self.assertTrue(by_source["cam-persist"].persistence_allowed)

    def test_priority_not_request_tuple_order_controls_deterministic_slot_assignment(self) -> None:
        a = self.permission("a", "CAMERA")
        b = self.permission("b", "SCREEN")
        c = self.permission("c", "PAGE")
        snapshot = self.snapshot(c, b, a)
        policy = self.policy(("c", "a", "b"), max_workers=2)
        first = self.plan(snapshot, policy, ("a", "b", "c"))
        second = self.plan(snapshot, policy, ("c", "b", "a"))
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(tuple(slot.source_id for slot in first.worker_slots), ("c", "a"))
        self.assertEqual(first.deferred_source_ids, ("b",))

    def test_unknown_requested_source_fails_closed(self) -> None:
        snapshot = self.snapshot(self.permission("cam", "CAMERA"))
        policy = self.policy(("cam",))
        with self.assertRaisesRegex(RetinaFanInError, "absent from exact permission snapshot"):
            self.plan(snapshot, policy, ("cam", "unknown"))

    def test_requested_source_missing_from_priority_fails_closed(self) -> None:
        snapshot = self.snapshot(self.permission("cam", "CAMERA"), self.permission("screen", "SCREEN"))
        policy = self.policy(("cam",))
        with self.assertRaisesRegex(RetinaFanInError, "priority order"):
            self.plan(snapshot, policy, ("cam", "screen"))

    def test_priority_source_absent_from_snapshot_fails_closed(self) -> None:
        snapshot = self.snapshot(self.permission("cam", "CAMERA"))
        policy = self.policy(("cam", "ghost"))
        with self.assertRaisesRegex(RetinaFanInError, "policy priority contains"):
            self.plan(snapshot, policy, ("cam",))

    def test_snapshot_and_policy_digest_binding_is_exact(self) -> None:
        snapshot = self.snapshot(self.permission("cam", "CAMERA"))
        policy = self.policy(("cam",))
        with self.assertRaisesRegex(RetinaFanInError, "permission snapshot digest mismatch"):
            build_retina_fanin_plan(
                plan_id="fanin-plan-1",
                permission_snapshot=snapshot,
                expected_permission_snapshot_sha256=D64_B,
                policy=policy,
                expected_policy_sha256=policy.sha256(),
                requested_source_ids=("cam",),
                provenance_refs=("cycle:7",),
            )
        with self.assertRaisesRegex(RetinaFanInError, "policy digest mismatch"):
            build_retina_fanin_plan(
                plan_id="fanin-plan-1",
                permission_snapshot=snapshot,
                expected_permission_snapshot_sha256=snapshot.sha256(),
                policy=policy,
                expected_policy_sha256=D64_A,
                requested_source_ids=("cam",),
                provenance_refs=("cycle:7",),
            )

    def test_duplicate_source_and_locator_are_rejected(self) -> None:
        one = self.permission("cam", "CAMERA")
        duplicate_id = RetinaSourcePermission(
            source_id="cam",
            source_kind="SCREEN",
            locator_ref="source-ref:other",
            capture_allowed=True,
            cognition_allowed=True,
            persistence_allowed=False,
            provenance_refs=("permission:dup",),
        )
        with self.assertRaisesRegex(RetinaFanInError, "source_id must be unique"):
            self.snapshot(one, duplicate_id)
        duplicate_locator = RetinaSourcePermission(
            source_id="other",
            source_kind="SCREEN",
            locator_ref=one.locator_ref,
            capture_allowed=True,
            cognition_allowed=True,
            persistence_allowed=False,
            provenance_refs=("permission:dup-locator",),
        )
        with self.assertRaisesRegex(RetinaFanInError, "locator_ref must be unique"):
            self.snapshot(one, duplicate_locator)

    def test_max_parallel_worker_ceiling_is_one_through_four(self) -> None:
        with self.assertRaisesRegex(RetinaFanInError, "\[1, 4\]"):
            self.policy(("cam",), max_workers=0)
        with self.assertRaisesRegex(RetinaFanInError, "\[1, 4\]"):
            self.policy(("cam",), max_workers=5)

    def test_exact_concrete_snapshot_type_is_required(self) -> None:
        forged = ForgedSnapshot(
            snapshot_id="forged",
            generation=1,
            permission_epoch="epoch",
            permission_authority_ref="authority",
            permissions=(self.permission("cam", "CAMERA"),),
            provenance_refs=("forge",),
        )
        policy = self.policy(("cam",))
        with self.assertRaisesRegex(RetinaFanInError, "concrete RetinaPermissionSnapshot"):
            build_retina_fanin_plan(
                plan_id="fanin-plan-1",
                permission_snapshot=forged,
                expected_permission_snapshot_sha256=forged.sha256(),
                policy=policy,
                expected_policy_sha256=policy.sha256(),
                requested_source_ids=("cam",),
                provenance_refs=("cycle:7",),
            )

    def test_snapshot_normalization_makes_permission_input_order_irrelevant(self) -> None:
        a = self.permission("a", "CAMERA")
        b = self.permission("b", "SCREEN")
        left = self.snapshot(a, b)
        right = self.snapshot(b, a)
        self.assertEqual(left.sha256(), right.sha256())


if __name__ == "__main__":
    unittest.main()
