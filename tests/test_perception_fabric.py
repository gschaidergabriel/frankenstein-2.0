import unittest

from src.frankenstein2.perception_fabric import (
    ObserveIntent,
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
    PerceptionFabricError,
    PerceptionSource,
    PerceptionWorkerPolicy,
    SourceKind,
    allocate_perception_workers,
)


P = ("test:perception-fabric",)


def snapshot(
    source_id="screen:1",
    capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
    generation=1,
    valid_from=10,
    expires=1_000,
):
    return PerceptionCapabilitySnapshot(
        snapshot_id=f"permission:{source_id}:{generation}",
        generation=generation,
        source_id=source_id,
        capabilities=capabilities,
        valid_from_monotonic_ns=valid_from,
        expires_monotonic_ns=expires,
        provenance_refs=P,
    )


def intent(
    snap,
    intent_id="look:1",
    priority=500_000,
    work=10,
    expires=900,
    heads=("ocr",),
    targets=(),
    remote=False,
    vlm=False,
):
    return ObserveIntent(
        intent_id=intent_id,
        cycle_id="cycle:1",
        generation=1,
        source_id=snap.source_id,
        permission_snapshot_sha256=snap.sha256(),
        requested_head_ids=heads,
        target_atom_ids=targets,
        roi_ref=None,
        required_freshness_ns=100,
        expires_monotonic_ns=expires,
        priority_micros=priority,
        max_work_units=work,
        allow_remote_frame=remote,
        allow_external_vlm=vlm,
        provenance_refs=P,
    )


def policy(workers=4, total=100):
    return PerceptionWorkerPolicy(
        policy_id="workers:test",
        generation=1,
        max_active_workers=workers,
        max_total_work_units=total,
        provenance_refs=P,
    )


class PerceptionFabricTests(unittest.TestCase):
    def test_source_binds_single_capture_owner_identity(self):
        source = PerceptionSource(
            source_id="camera:front",
            kind=SourceKind.CAMERA,
            clock_domain="local-monotonic",
            capture_owner_id="capture-owner:camera:front",
            provenance_refs=P,
        )
        self.assertEqual(source.capture_owner_id, "capture-owner:camera:front")
        self.assertEqual(source.as_dict()["world_truth_authority"], "NONE")

    def test_analyze_requires_see(self):
        with self.assertRaisesRegex(PerceptionFabricError, "ANALYZE requires SEE"):
            snapshot(capabilities=(PerceptionCapability.ANALYZE,))

    def test_external_vlm_capability_requires_analyze(self):
        with self.assertRaisesRegex(PerceptionFabricError, "EXTERNAL_VLM requires ANALYZE"):
            snapshot(capabilities=(PerceptionCapability.SEE, PerceptionCapability.EXTERNAL_VLM))

    def test_stale_permission_digest_fails_closed(self):
        s1 = snapshot(generation=1)
        i = intent(s1)
        s2 = snapshot(generation=2)
        with self.assertRaisesRegex(PerceptionFabricError, "stale or mismatched"):
            i.validate_against(s2, now_monotonic_ns=100)

    def test_revoked_source_permission_fails_closed(self):
        allowed = snapshot()
        i = intent(allowed)
        revoked = snapshot(capabilities=(), generation=1)
        with self.assertRaises(PerceptionFabricError):
            i.validate_against(revoked, now_monotonic_ns=100)

    def test_expired_snapshot_and_expired_intent_fail_closed(self):
        s = snapshot(expires=200)
        i = intent(s, expires=150)
        with self.assertRaisesRegex(PerceptionFabricError, "permission snapshot"):
            i.validate_against(s, now_monotonic_ns=250)

        fresh = snapshot(expires=1_000)
        expired_intent = intent(fresh, expires=150)
        with self.assertRaisesRegex(PerceptionFabricError, "ObserveIntent is expired"):
            expired_intent.validate_against(fresh, now_monotonic_ns=150)

    def test_remote_frame_requires_explicit_capability(self):
        s = snapshot()
        i = intent(s, remote=True)
        with self.assertRaisesRegex(PerceptionFabricError, "REMOTE_FRAME"):
            i.validate_against(s, now_monotonic_ns=100)

    def test_external_vlm_requires_explicit_capability(self):
        s = snapshot(capabilities=(
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.REMOTE_FRAME,
        ))
        i = intent(s, remote=True, vlm=True)
        with self.assertRaisesRegex(PerceptionFabricError, "EXTERNAL_VLM"):
            i.validate_against(s, now_monotonic_ns=100)

    def test_zero_workers_is_valid_and_defers_all_work(self):
        s = snapshot()
        intents = (intent(s, intent_id="a"), intent(s, intent_id="b"))
        result = allocate_perception_workers(
            intents=intents,
            policy=policy(workers=0, total=100),
            permission_snapshots=(s,),
            now_monotonic_ns=100,
        )
        self.assertEqual(result.selected_intent_ids, ())
        self.assertEqual(set(result.deferred_intent_ids), {"a", "b"})
        self.assertEqual(result.total_work_units, 0)

    def test_scheduler_never_selects_more_than_four_and_prefers_priority(self):
        sources = [snapshot(source_id=f"screen:{n}") for n in range(6)]
        intents = tuple(
            intent(s, intent_id=f"i{n}", priority=n * 100_000, work=10)
            for n, s in enumerate(sources)
        )
        result = allocate_perception_workers(
            intents=intents,
            policy=policy(workers=4, total=100),
            permission_snapshots=tuple(sources),
            now_monotonic_ns=100,
        )
        self.assertEqual(len(result.selected_intent_ids), 4)
        self.assertEqual(set(result.selected_intent_ids), {"i2", "i3", "i4", "i5"})
        self.assertEqual(set(result.deferred_intent_ids), {"i0", "i1"})

    def test_worker_budget_is_hard_ceiling(self):
        s1 = snapshot(source_id="screen:1")
        s2 = snapshot(source_id="screen:2")
        a = intent(s1, intent_id="a", priority=900_000, work=7)
        b = intent(s2, intent_id="b", priority=800_000, work=7)
        result = allocate_perception_workers(
            intents=(a, b),
            policy=policy(workers=4, total=10),
            permission_snapshots=(s1, s2),
            now_monotonic_ns=100,
        )
        self.assertEqual(result.selected_intent_ids, ("a",))
        self.assertEqual(result.deferred_intent_ids, ("b",))
        self.assertEqual(result.total_work_units, 7)

    def test_duplicate_permission_snapshot_for_same_source_fails_closed(self):
        s1 = snapshot(generation=1)
        s2 = snapshot(generation=2)
        i = intent(s1)
        with self.assertRaisesRegex(PerceptionFabricError, "exactly one permission snapshot"):
            allocate_perception_workers(
                intents=(i,),
                policy=policy(),
                permission_snapshots=(s1, s2),
                now_monotonic_ns=100,
            )

    def test_source_count_is_independent_of_worker_count(self):
        sources = tuple(snapshot(source_id=f"source:{n}") for n in range(9))
        intents = tuple(intent(s, intent_id=f"look:{n}", priority=100_000 + n, work=1) for n, s in enumerate(sources))
        result = allocate_perception_workers(
            intents=intents,
            policy=policy(workers=3, total=3),
            permission_snapshots=sources,
            now_monotonic_ns=100,
        )
        self.assertEqual(len(result.selected_intent_ids), 3)
        self.assertEqual(len(result.deferred_intent_ids), 6)

    def test_baseline_intent_has_no_vlm_or_remote_payload_authority(self):
        s = snapshot()
        i = intent(s)
        i.validate_against(s, now_monotonic_ns=100)
        payload = i.as_dict()
        self.assertFalse(payload["allow_remote_frame"])
        self.assertFalse(payload["allow_external_vlm"])
        self.assertEqual(payload["perception_execution_authority"], "NONE")
        self.assertEqual(payload["world_truth_authority"], "NONE")


if __name__ == "__main__":
    unittest.main()
