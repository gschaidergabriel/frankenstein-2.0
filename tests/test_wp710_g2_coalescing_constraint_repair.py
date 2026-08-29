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
)


PROV = ("test:wp710:g2-coalescing-constraint-repair",)


def snapshot(source_id: str, *, generation: int) -> PerceptionCapabilitySnapshot:
    return PerceptionCapabilitySnapshot(
        snapshot_id=f"permission:{source_id}:g{generation}",
        generation=generation,
        source_id=source_id,
        capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
        valid_from_monotonic_ns=0,
        expires_monotonic_ns=None,
        provenance_refs=PROV,
    )


def intent(
    intent_id: str,
    permission: PerceptionCapabilitySnapshot,
    *,
    generation: int = 1,
    freshness_ns: int = 1_000,
    expires_ns: int = 10_000,
    priority: int = 700_000,
) -> ObserveIntent:
    return ObserveIntent(
        intent_id=intent_id,
        cycle_id="cycle:wp710:g2",
        generation=generation,
        source_id=permission.source_id,
        permission_snapshot_sha256=permission.sha256(),
        requested_head_ids=("motion",),
        target_atom_ids=(),
        roi_ref=None,
        required_freshness_ns=freshness_ns,
        expires_monotonic_ns=expires_ns,
        priority_micros=priority,
        max_work_units=1,
        allow_remote_frame=False,
        allow_external_vlm=False,
        provenance_refs=PROV,
    )


def policy() -> PerceptionSchedulerPolicy:
    return PerceptionSchedulerPolicy(
        policy_id="policy:wp710:g2",
        generation=1,
        max_active_workers=1,
        max_queue_items=8,
        max_perception_work_units=8,
        pressure_drop_below_priority_micros=100_000,
        provenance_refs=PROV,
    )


class WP710G2CoalescingConstraintRepairTests(unittest.TestCase):
    def test_stricter_freshness_and_deadline_are_not_collapsed_into_looser_request(self) -> None:
        permission = snapshot("camera:front", generation=1)
        strict = intent(
            "intent:strict",
            permission,
            freshness_ns=100,
            expires_ns=5_000,
        )
        loose = intent(
            "intent:loose",
            permission,
            freshness_ns=5_000,
            expires_ns=50_000,
        )

        state = create_scheduler(scheduler_id="scheduler:wp710:g2", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(), intents=(strict, loose))

        self.assertEqual(
            {item.intent_id for item in state.queued_intents},
            {"intent:strict", "intent:loose"},
        )
        self.assertEqual(state.dropped_intent_count, 0)

    def test_distinct_permission_snapshot_identities_are_not_coalesced(self) -> None:
        permission_g1 = snapshot("camera:front", generation=1)
        permission_g2 = snapshot("camera:front", generation=2)
        old_authority = intent("intent:permission-g1", permission_g1)
        new_authority = intent("intent:permission-g2", permission_g2)

        state = create_scheduler(scheduler_id="scheduler:wp710:g2", provenance_refs=PROV)
        state = enqueue_intents(
            state=state,
            policy=policy(),
            intents=(old_authority, new_authority),
        )

        self.assertEqual(
            {item.intent_id for item in state.queued_intents},
            {"intent:permission-g1", "intent:permission-g2"},
        )
        self.assertEqual(state.dropped_intent_count, 0)

    def test_truly_equivalent_constraints_still_coalesce_deterministically(self) -> None:
        permission = snapshot("camera:front", generation=1)
        old = intent("intent:old", permission, generation=1, priority=700_000)
        new = intent("intent:new", permission, generation=2, priority=700_000)

        state = create_scheduler(scheduler_id="scheduler:wp710:g2", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(), intents=(old, new))

        self.assertEqual(tuple(item.intent_id for item in state.queued_intents), ("intent:new",))
        self.assertEqual(state.dropped_intent_count, 1)
        self.assertIn("intent:old", state.recent_dropped_intent_ids)


if __name__ == "__main__":
    unittest.main()
