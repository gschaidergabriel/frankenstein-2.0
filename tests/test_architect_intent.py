import copy
import unittest
from datetime import datetime, timezone

from tools.coordination.architect_intent import (
    IntentError,
    compile_intent_bundle,
    intent_key,
    normalize_intent_id,
    reservation_decision,
    reservation_path,
    validate_reservation,
)


def bundle(intent_id="VOICE/INTERRUPTION-POLICY", generation=1, objective="first wording"):
    return compile_intent_bundle(
        intent_id=intent_id,
        generation=generation,
        target={"trigger": "4"},
        objective=objective,
        action_class="CONTEXT_DELTA",
        ttl_minutes=120,
        priority=90,
        architect_id="persistent-architect",
        project="frankenstein-2.0",
        constraints=["no authority changes"],
        evidence_refs=["commit:abc"],
    )


class ArchitectIntentTests(unittest.TestCase):
    def test_explicit_identity_is_normalized_without_prose_inference(self):
        self.assertEqual(
            normalize_intent_id(" Voice/Interruption-Policy "),
            "voice/interruption-policy",
        )
        with self.assertRaises(IntentError):
            normalize_intent_id("infer this from a prose sentence")

    def test_same_intent_different_wording_collides_on_same_create_only_path(self):
        # Reservation identity is intentionally independent of packet wall-clock
        # time and nonce. Do not mock architect_packet.datetime here: that class is
        # also the RFC3339 parser used by validate_packet, so replacing it with a
        # MagicMock invalidates the test harness rather than exercising dedup.
        first = bundle(objective="first wording")
        second = bundle(objective="completely different words")
        self.assertEqual(first["intent_key"], second["intent_key"])
        self.assertEqual(first["reservation_path"], second["reservation_path"])
        self.assertNotEqual(first["packet"]["nonce"], second["packet"]["nonce"])
        self.assertNotEqual(first["packet"]["packet_id"], second["packet"]["packet_id"])
        self.assertNotEqual(first["packet"]["route_id"], second["packet"]["route_id"])

    def test_different_explicit_intents_remain_independently_routable(self):
        self.assertNotEqual(
            intent_key(
                project="frankenstein-2.0",
                architect_id="persistent-architect",
                intent_id="voice/interrupt",
            ),
            intent_key(
                project="frankenstein-2.0",
                architect_id="persistent-architect",
                intent_id="voice/tts",
            ),
        )

    def test_generation_changes_reservation_path_without_rewriting_history(self):
        p1 = reservation_path(
            project="frankenstein-2.0",
            architect_id="persistent-architect",
            intent_id="voice/interrupt",
            generation=1,
        )
        p2 = reservation_path(
            project="frankenstein-2.0",
            architect_id="persistent-architect",
            intent_id="voice/interrupt",
            generation=2,
        )
        self.assertNotEqual(p1, p2)
        self.assertTrue(p1.endswith("/000001.json"))
        self.assertTrue(p2.endswith("/000002.json"))

    def test_reservation_and_packet_are_bound_but_delivery_identity_remains_distinct(self):
        candidate = bundle()
        reservation = candidate["reservation"]
        packet = candidate["packet"]
        self.assertEqual(reservation["packet_id"], packet["packet_id"])
        self.assertEqual(reservation["packet_route_id"], packet["route_id"])
        self.assertEqual(reservation["packet_nonce"], packet["nonce"])
        self.assertIn(
            f"coordination_intent_reservation:{candidate['reservation_path']}",
            packet["evidence_refs"],
        )
        self.assertEqual(
            candidate["atomic_repository_contract"]["write_mode"],
            "CREATE_ONLY_BOTH_IN_ONE_GIT_CAS_COMMIT",
        )

    def test_active_existing_reservation_is_reused_not_duplicated(self):
        candidate = bundle()
        decision = reservation_decision(
            candidate["reservation"],
            now=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(decision, "REUSE_EXISTING_PACKET")

    def test_expired_or_terminal_reservation_requires_next_generation(self):
        candidate = bundle()
        self.assertEqual(
            reservation_decision(
                candidate["reservation"],
                now=datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc),
            ),
            "NEXT_GENERATION_REQUIRED",
        )
        self.assertEqual(
            reservation_decision(
                candidate["reservation"],
                now=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc),
                terminal_packet_ids={candidate["packet"]["packet_id"]},
            ),
            "NEXT_GENERATION_REQUIRED",
        )

    def test_reservation_tamper_fails_closed(self):
        candidate = bundle()
        tampered = copy.deepcopy(candidate["reservation"])
        tampered["intent_key"] = "0" * 64
        with self.assertRaisesRegex(IntentError, "intent_key mismatch"):
            validate_reservation(tampered)

    def test_reservation_cannot_mint_any_authority_or_credit(self):
        candidate = bundle()
        reservation = candidate["reservation"]
        self.assertFalse(reservation["credit_authority"])
        self.assertFalse(reservation["mutation_authority"])
        self.assertFalse(reservation["runtime_dispatch_authority"])
        self.assertFalse(reservation["effect_authority"])
        self.assertEqual(reservation["credit_delta"], 0)


if __name__ == "__main__":
    unittest.main()
