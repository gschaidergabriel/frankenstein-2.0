from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.agency_state import (
    AGENCY_PATCH_SCHEMA,
    AgencyState,
    AgencyStateError,
    AgencyStatePatch,
    DeferredIntent,
    Interest,
    OpenLoop,
)


class AgencyStateTests(unittest.TestCase):
    def interest(self, item_id="interest-1", label="understand anomaly", salience=700000):
        return Interest(
            interest_id=item_id,
            label=label,
            salience_ppm=salience,
            provenance_refs=("event:interest-source",),
        )

    def loop(self, item_id="loop-1", state="OPEN", blocked=()):
        return OpenLoop(
            loop_id=item_id,
            summary="resolve runtime evidence gap",
            state=state,
            priority_ppm=800000,
            provenance_refs=("event:loop-source",),
            blocked_on_refs=blocked,
        )

    def intent(self, item_id="intent-1"):
        return DeferredIntent(
            intent_id=item_id,
            summary="re-check after explicit signal",
            priority_ppm=500000,
            revisit_condition_ref="signal:runtime-reentry",
            provenance_refs=("event:intent-source",),
        )

    def state(self):
        return AgencyState.create(
            state_id="agency-main",
            generation=3,
            interests=(self.interest(),),
            open_loops=(self.loop(),),
            deferred_intents=(self.intent(),),
        )

    def patch(self, state, **changes):
        params = dict(
            schema=AGENCY_PATCH_SCHEMA,
            transition_id="transition-1",
            expected_state_id=state.state_id,
            expected_generation=state.generation,
            expected_state_sha256=state.sha256(),
            next_generation=state.generation + 1,
            transition_refs=("event:explicit-transition",),
        )
        params.update(changes)
        return AgencyStatePatch(**params)

    def test_state_is_order_canonical_by_stable_item_id(self):
        a = AgencyState.create(
            state_id="agency-main",
            generation=0,
            interests=(self.interest("interest-b"), self.interest("interest-a")),
            open_loops=(self.loop("loop-b"), self.loop("loop-a")),
            deferred_intents=(self.intent("intent-b"), self.intent("intent-a")),
        )
        b = AgencyState.create(
            state_id="agency-main",
            generation=0,
            interests=(self.interest("interest-a"), self.interest("interest-b")),
            open_loops=(self.loop("loop-a"), self.loop("loop-b")),
            deferred_intents=(self.intent("intent-a"), self.intent("intent-b")),
        )
        self.assertEqual(a.canonical_json(), b.canonical_json())
        self.assertEqual(a.sha256(), b.sha256())
        self.assertEqual([i.interest_id for i in a.interests], ["interest-a", "interest-b"])

    def test_state_classification_does_not_claim_world_truth(self):
        state = self.state()
        self.assertEqual(state.classification, "EXPLICIT_AGENCY_PROJECTION_NOT_WORLD_TRUTH")

    def test_duplicate_ids_within_category_fail_closed(self):
        with self.assertRaisesRegex(AgencyStateError, "duplicate interest"):
            AgencyState.create(
                state_id="agency-main",
                interests=(self.interest("same"), self.interest("same")),
            )

    def test_cross_category_id_ambiguity_fails_closed(self):
        with self.assertRaisesRegex(AgencyStateError, "ambiguous"):
            AgencyState.create(
                state_id="agency-main",
                interests=(self.interest("same"),),
                open_loops=(self.loop("same"),),
            )

    def test_provenance_is_required_for_all_agency_items(self):
        with self.assertRaisesRegex(AgencyStateError, "at least one"):
            Interest("i", "x", 1, ())
        with self.assertRaisesRegex(AgencyStateError, "at least one"):
            OpenLoop("l", "x", "OPEN", 1, ())
        with self.assertRaisesRegex(AgencyStateError, "at least one"):
            DeferredIntent("d", "x", 1, "signal:x", ())

    def test_salience_and_priority_are_integer_ppm_not_unbounded_float(self):
        with self.assertRaises(AgencyStateError):
            self.interest(salience=1.0)
        with self.assertRaises(AgencyStateError):
            self.interest(salience=1_000_001)
        with self.assertRaises(AgencyStateError):
            OpenLoop("l", "x", "OPEN", -1, ("event:x",))

    def test_blocked_loop_requires_explicit_blocker_and_only_blocked_loop_may_have_one(self):
        with self.assertRaisesRegex(AgencyStateError, "requires blocked_on_refs"):
            self.loop(state="BLOCKED")
        blocked = self.loop(state="BLOCKED", blocked=("dependency:123",))
        self.assertEqual(blocked.blocked_on_refs, ("dependency:123",))
        with self.assertRaisesRegex(AgencyStateError, "only valid"):
            self.loop(state="OPEN", blocked=("dependency:123",))

    def test_patch_adds_all_three_item_classes_with_one_generation_step(self):
        state = AgencyState.create(state_id="agency-main", generation=0)
        patch = self.patch(
            state,
            upsert_interests=(self.interest(),),
            upsert_open_loops=(self.loop(),),
            upsert_deferred_intents=(self.intent(),),
        )
        new_state, receipt = state.apply(patch)
        self.assertEqual(new_state.generation, 1)
        self.assertEqual(len(new_state.interests), 1)
        self.assertEqual(len(new_state.open_loops), 1)
        self.assertEqual(len(new_state.deferred_intents), 1)
        self.assertEqual(receipt.before_state_sha256, state.sha256())
        self.assertEqual(receipt.after_state_sha256, new_state.sha256())
        self.assertEqual(receipt.classification, "PURE_AGENCY_STATE_TRANSITION_NOT_WORLD_EFFECT")

    def test_patch_can_update_existing_item_without_changing_identity(self):
        state = self.state()
        changed = self.interest(label="investigate stronger falsifier", salience=900000)
        new_state, _ = state.apply(self.patch(state, upsert_interests=(changed,)))
        self.assertEqual(new_state.interests[0].interest_id, "interest-1")
        self.assertEqual(new_state.interests[0].label, "investigate stronger falsifier")
        self.assertEqual(new_state.interests[0].salience_ppm, 900000)

    def test_patch_retire_operations_are_explicit_and_receipted(self):
        state = self.state()
        patch = self.patch(
            state,
            remove_interest_ids=("interest-1",),
            close_loop_ids=("loop-1",),
            cancel_intent_ids=("intent-1",),
        )
        new_state, receipt = state.apply(patch)
        self.assertEqual(new_state.interests, ())
        self.assertEqual(new_state.open_loops, ())
        self.assertEqual(new_state.deferred_intents, ())
        self.assertEqual(receipt.removed_interest_ids, ("interest-1",))
        self.assertEqual(receipt.closed_loop_ids, ("loop-1",))
        self.assertEqual(receipt.cancelled_intent_ids, ("intent-1",))

    def test_unknown_retirement_fails_closed(self):
        state = self.state()
        with self.assertRaisesRegex(AgencyStateError, "unknown interest"):
            state.apply(self.patch(state, remove_interest_ids=("not-present",)))
        with self.assertRaisesRegex(AgencyStateError, "unknown open loop"):
            state.apply(self.patch(state, close_loop_ids=("not-present",)))
        with self.assertRaisesRegex(AgencyStateError, "unknown deferred intent"):
            state.apply(self.patch(state, cancel_intent_ids=("not-present",)))

    def test_patch_requires_exact_state_id_generation_and_digest(self):
        state = self.state()
        with self.assertRaisesRegex(AgencyStateError, "state_id mismatch"):
            state.apply(
                AgencyStatePatch(
                    schema=AGENCY_PATCH_SCHEMA,
                    transition_id="t",
                    expected_state_id="other-state",
                    expected_generation=state.generation,
                    expected_state_sha256=state.sha256(),
                    next_generation=state.generation + 1,
                    transition_refs=("event:t",),
                    upsert_interests=(self.interest(label="changed"),),
                )
            )
        with self.assertRaisesRegex(AgencyStateError, "stale agency-state generation"):
            state.apply(
                AgencyStatePatch(
                    schema=AGENCY_PATCH_SCHEMA,
                    transition_id="t",
                    expected_state_id=state.state_id,
                    expected_generation=state.generation - 1,
                    expected_state_sha256=state.sha256(),
                    next_generation=state.generation,
                    transition_refs=("event:t",),
                    upsert_interests=(self.interest(label="changed"),),
                )
            )
        with self.assertRaisesRegex(AgencyStateError, "digest"):
            bad = self.patch(state, upsert_interests=(self.interest(label="changed"),))
            state.apply(replace(bad, expected_state_sha256="0" * 64))

    def test_patch_generation_must_advance_exactly_one(self):
        state = self.state()
        with self.assertRaisesRegex(AgencyStateError, "next_generation"):
            AgencyStatePatch(
                schema=AGENCY_PATCH_SCHEMA,
                transition_id="t",
                expected_state_id=state.state_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                next_generation=state.generation + 2,
                transition_refs=("event:t",),
                upsert_interests=(self.interest(label="changed"),),
            )

    def test_patch_rejects_self_conflicting_operations(self):
        state = self.state()
        with self.assertRaisesRegex(AgencyStateError, "upserted and removed"):
            self.patch(
                state,
                upsert_interests=(self.interest(),),
                remove_interest_ids=("interest-1",),
            )
        with self.assertRaisesRegex(AgencyStateError, "upserted and closed"):
            self.patch(
                state,
                upsert_open_loops=(self.loop(),),
                close_loop_ids=("loop-1",),
            )
        with self.assertRaisesRegex(AgencyStateError, "upserted and cancelled"):
            self.patch(
                state,
                upsert_deferred_intents=(self.intent(),),
                cancel_intent_ids=("intent-1",),
            )

    def test_empty_patch_is_rejected(self):
        state = self.state()
        with self.assertRaisesRegex(AgencyStateError, "at least one explicit change"):
            self.patch(state)

    def test_cross_category_collision_created_by_patch_fails_closed(self):
        state = self.state()
        collision = self.interest(item_id="loop-1", label="collision")
        with self.assertRaisesRegex(AgencyStateError, "ambiguous"):
            state.apply(self.patch(state, upsert_interests=(collision,)))

    def test_transition_receipt_is_deterministic_for_same_explicit_input(self):
        state = self.state()
        patch = self.patch(state, upsert_interests=(self.interest(label="changed"),))
        next_a, receipt_a = state.apply(patch)
        next_b, receipt_b = state.apply(patch)
        self.assertEqual(next_a.canonical_json(), next_b.canonical_json())
        self.assertEqual(receipt_a.canonical_json(), receipt_b.canonical_json())
        self.assertEqual(receipt_a.sha256(), receipt_b.sha256())


if __name__ == "__main__":
    unittest.main(verbosity=2)
