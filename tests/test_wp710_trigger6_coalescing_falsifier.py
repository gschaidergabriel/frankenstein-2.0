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


PROV = ("trigger6:wp710-coalescing-falsifier",)


def snapshot(source_id: str) -> PerceptionCapabilitySnapshot:
    return PerceptionCapabilitySnapshot(
        snapshot_id=f"permission:{source_id}:g1",
        generation=1,
        source_id=source_id,
        capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
        valid_from_monotonic_ns=0,
        expires_monotonic_ns=None,
        provenance_refs=PROV,
    )


def make_intent(
    intent_id: str,
    permission: PerceptionCapabilitySnapshot,
    *,
    freshness_ns: int,
    expires_ns: int,
) -> ObserveIntent:
    return ObserveIntent(
        intent_id=intent_id,
        cycle_id="cycle:trigger6",
        generation=1,
        source_id=permission.source_id,
        permission_snapshot_sha256=permission.sha256(),
        requested_head_ids=("motion",),
        target_atom_ids=(),
        roi_ref=None,
        required_freshness_ns=freshness_ns,
        expires_monotonic_ns=expires_ns,
        priority_micros=700_000,
        max_work_units=1,
        allow_remote_frame=False,
        allow_external_vlm=False,
        provenance_refs=PROV,
    )


def policy() -> PerceptionSchedulerPolicy:
    return PerceptionSchedulerPolicy(
        policy_id="policy:trigger6",
        generation=1,
        max_active_workers=1,
        max_queue_items=4,
        max_perception_work_units=4,
        pressure_drop_below_priority_micros=100_000,
        provenance_refs=PROV,
    )


class WP710CoalescingConstraintDominanceFalsifier(unittest.TestCase):
    def test_same_target_coalescing_must_not_discard_stricter_freshness_and_deadline(self):
        permission = snapshot("camera:front")
        strict = make_intent(
            "intent:strict",
            permission,
            freshness_ns=100,
            expires_ns=5_000,
        )
        loose = make_intent(
            "intent:loose",
            permission,
            freshness_ns=5_000,
            expires_ns=50_000,
        )

        state = create_scheduler(scheduler_id="scheduler:trigger6", provenance_refs=PROV)
        state = enqueue_intents(state=state, policy=policy(), intents=(strict, loose))

        self.assertEqual(len(state.queued_intents), 1)
        survivor = state.queued_intents[0]
        self.assertLessEqual(
            survivor.required_freshness_ns,
            strict.required_freshness_ns,
            "coalescing discarded the stricter freshness obligation",
        )
        self.assertLessEqual(
            survivor.expires_monotonic_ns,
            strict.expires_monotonic_ns,
            "coalescing discarded the earlier deadline obligation",
        )


if __name__ == "__main__":
    unittest.main()
