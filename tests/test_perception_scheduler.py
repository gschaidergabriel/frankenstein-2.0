import unittest

from src.frankenstein2.perception_fabric import (
    ObserveIntent,
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
)
from src.frankenstein2.perception_scheduler import (
    PerceptionSchedulerPolicy,
    create_scheduler,
    enqueue_intents,
    plan_perception_cycle,
)


PROV = ("test:wp710",)


def snapshot(source_id, *, generation=1, analyze=True, expires=None):
    capabilities = [PerceptionCapability.SEE]
    if analyze:
        capabilities.append(PerceptionCapability.ANALYZE)
    return PerceptionCapabilitySnapshot(
        snapshot_id=f"permission:{source_id}:g{generation}",
        generation=generation,
        source_id=source_id,
        capabilities=tuple(capabilities),
        valid_from_monotonic_ns=0,
        expires_monotonic_ns=expires,
        provenance_refs=PROV,
    )


def intent(intent_id, source_id, permission, *, generation=1, priority=500_000, work=1, expires=10_000, head="motion", target=None):
    targets = () if target is None else (target,)
    return ObserveIntent(
        intent_id=intent_id,
        cycle_id="cycle:test",
        generation=generation,
        source_id=source_id,
        permission_snapshot_sha256=permission.sha256(),
        requested_head_ids=(head,),
        target_atom_ids=targets,
        roi_ref=None,
        required_freshness_ns=1_000,
        expires_monotonic_ns=expires,
        priority_micros=priority,
        max_work_units=work,
        allow_remote_frame=False,
        allow_external_vlm=False,
        provenance_refs=PROV,
    )


def policy(*, workers=4, queue=16, budget=16, pressure_drop=100_000):
    return PerceptionSchedulerPolicy(
        policy_id="policy:test",
        generation=1,
        max_active_workers=workers,
        max_queue_items=queue,
        max_perception_work_units=budget,
        pressure_drop_below_priority_micros=pressure_drop,
        provenance_refs=PROV,
    )


class PerceptionSchedulerTests(unittest.TestCase):
    def test_zero_sources_produces_no_work_or_observation(self):
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state, plan = plan_perception_cycle(state=state, policy=policy(), permission_snapshots=(), now_monotonic_ns=100, available_compute_units=16, control_reserve_units=4)
        self.assertEqual(plan.active_workers, 0)
        self.assertEqual(plan.selected_intent_ids, ())
        self.assertEqual(plan.deferred_intent_ids, ())
        self.assertEqual(plan.dropped_intent_ids, ())
        self.assertEqual(state.queued_intents, ())
        self.assertFalse(plan.as_dict()["raw_frame_persistence"])
        self.assertFalse(plan.as_dict()["provider_or_vlm_invocation"])

    def test_zero_worker_policy_is_valid_and_defers_admitted_work(self):
        permission = snapshot("camera:front")
        item = intent("intent:1", "camera:front", permission)
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(workers=0), intents=(item,))
        state, plan = plan_perception_cycle(state=state, policy=policy(workers=0), permission_snapshots=(permission,), now_monotonic_ns=100, available_compute_units=16, control_reserve_units=4)
        self.assertEqual(plan.active_workers, 0)
        self.assertEqual(plan.selected_intent_ids, ())
        self.assertEqual(plan.deferred_intent_ids, ("intent:1",))
        self.assertEqual(tuple(x.intent_id for x in state.queued_intents), ("intent:1",))

    def test_n_sources_greater_than_workers_is_bounded_and_deferred(self):
        permissions = tuple(snapshot(f"camera:{i}") for i in range(5))
        items = tuple(intent(f"intent:{i}", f"camera:{i}", permissions[i], priority=900_000 - (i * 10_000)) for i in range(5))
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(workers=2, queue=8), intents=items)
        state, plan = plan_perception_cycle(state=state, policy=policy(workers=2, queue=8), permission_snapshots=permissions, now_monotonic_ns=100, available_compute_units=20, control_reserve_units=4)
        self.assertEqual(plan.active_workers, 2)
        self.assertEqual(plan.selected_intent_ids, ("intent:0", "intent:1"))
        self.assertEqual(len(plan.deferred_intent_ids), 3)
        self.assertLessEqual(len(state.queued_intents), 8)

    def test_four_useful_sources_can_fill_all_four_analysis_slots(self):
        permissions = tuple(snapshot(f"source:{i}") for i in range(4))
        items = tuple(intent(f"intent:{i}", f"source:{i}", permissions[i], priority=800_000 - i) for i in range(4))
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(workers=4), intents=items)
        _, plan = plan_perception_cycle(state=state, policy=policy(workers=4), permission_snapshots=permissions, now_monotonic_ns=100, available_compute_units=20, control_reserve_units=4)
        self.assertEqual(plan.active_workers, 4)
        self.assertEqual(set(plan.selected_intent_ids), {f"intent:{i}" for i in range(4)})

    def test_equivalent_queued_need_coalesces_to_newer_generation(self):
        permission = snapshot("camera:front")
        old = intent("intent:old", "camera:front", permission, generation=1, priority=700_000)
        new = intent("intent:new", "camera:front", permission, generation=2, priority=700_000)
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(queue=4), intents=(old, new))
        self.assertEqual(tuple(x.intent_id for x in state.queued_intents), ("intent:new",))
        self.assertEqual(state.dropped_intent_count, 1)
        self.assertIn("intent:old", state.recent_dropped_intent_ids)

    def test_queue_overflow_drops_low_value_work_deterministically(self):
        permissions = tuple(snapshot(f"source:{i}") for i in range(5))
        items = tuple(intent(f"intent:{i}", f"source:{i}", permissions[i], priority=900_000 - i * 100_000) for i in range(5))
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(queue=3), intents=items)
        self.assertEqual(tuple(x.intent_id for x in state.queued_intents), ("intent:0", "intent:1", "intent:2"))
        self.assertEqual(state.dropped_intent_count, 2)
        self.assertEqual(set(state.recent_dropped_intent_ids), {"intent:3", "intent:4"})

    def test_control_reserve_is_never_consumed_and_low_value_work_drops_under_pressure(self):
        permission = snapshot("camera:front")
        low = intent("intent:low", "camera:front", permission, priority=50_000, head="motion")
        high = intent("intent:high", "camera:front", permission, priority=900_000, head="ocr")
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        p = policy(workers=4, queue=8, budget=20, pressure_drop=100_000)
        state = enqueue_intents(state=state, policy=p, intents=(low, high))
        state, plan = plan_perception_cycle(state=state, policy=p, permission_snapshots=(permission,), now_monotonic_ns=100, available_compute_units=4, control_reserve_units=4)
        self.assertTrue(plan.pressure_degraded)
        self.assertEqual(plan.effective_perception_budget_units, 0)
        self.assertEqual(plan.consumed_work_units, 0)
        self.assertEqual(plan.selected_intent_ids, ())
        self.assertEqual(plan.deferred_intent_ids, ("intent:high",))
        self.assertEqual(plan.dropped_intent_ids, ("intent:low",))
        self.assertEqual(tuple(x.intent_id for x in state.queued_intents), ("intent:high",))

    def test_permission_revocation_after_enqueue_fails_closed_at_dispatch(self):
        admitted = snapshot("camera:front", generation=1, analyze=True)
        revoked = snapshot("camera:front", generation=2, analyze=False)
        item = intent("intent:1", "camera:front", admitted)
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(), intents=(item,))
        state, plan = plan_perception_cycle(state=state, policy=policy(), permission_snapshots=(revoked,), now_monotonic_ns=100, available_compute_units=16, control_reserve_units=4)
        self.assertEqual(plan.selected_intent_ids, ())
        self.assertEqual(plan.deferred_intent_ids, ())
        self.assertEqual(plan.dropped_intent_ids, ("intent:1",))
        self.assertEqual(state.queued_intents, ())

    def test_compute_budget_limits_selected_work_even_with_free_worker_slots(self):
        permissions = tuple(snapshot(f"source:{i}") for i in range(3))
        items = tuple(intent(f"intent:{i}", f"source:{i}", permissions[i], priority=800_000 - i, work=3) for i in range(3))
        p = policy(workers=4, budget=4)
        state = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=p, intents=items)
        _, plan = plan_perception_cycle(state=state, policy=p, permission_snapshots=permissions, now_monotonic_ns=100, available_compute_units=20, control_reserve_units=4)
        self.assertEqual(plan.active_workers, 1)
        self.assertEqual(plan.consumed_work_units, 3)
        self.assertEqual(len(plan.deferred_intent_ids), 2)

    def test_input_order_does_not_change_schedule(self):
        permissions = tuple(snapshot(f"source:{i}") for i in range(4))
        items = tuple(intent(f"intent:{i}", f"source:{i}", permissions[i], priority=700_000 - i * 10_000) for i in range(4))
        p = policy(workers=2, queue=8, budget=8)
        a = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        b = create_scheduler(scheduler_id="scheduler:test", provenance_refs=PROV)
        a = enqueue_intents(state=a, policy=p, intents=items)
        b = enqueue_intents(state=b, policy=p, intents=tuple(reversed(items)))
        a, plan_a = plan_perception_cycle(state=a, policy=p, permission_snapshots=permissions, now_monotonic_ns=100, available_compute_units=20, control_reserve_units=4)
        b, plan_b = plan_perception_cycle(state=b, policy=p, permission_snapshots=tuple(reversed(permissions)), now_monotonic_ns=100, available_compute_units=20, control_reserve_units=4)
        self.assertEqual(plan_a.as_dict(), plan_b.as_dict())
        self.assertEqual(a.as_dict(), b.as_dict())


if __name__ == "__main__":
    unittest.main()
