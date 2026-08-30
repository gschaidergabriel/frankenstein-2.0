import copy
import unittest
from datetime import datetime, timedelta

from tools.coordination.architect_intent import (
    IntentError,
    compile_intent_bundle,
    intent_key,
    normalize_intent_id,
    reservation_decision,
    reservation_path,
    validate_reservation,
)


def compile_kwargs(intent_id="VOICE/INTERRUPTION-POLICY", objective="first wording"):
    return {
        "intent_id": intent_id,
        "target": {"trigger": "4"},
        "objective": objective,
        "action_class": "CONTEXT_DELTA",
        "ttl_minutes": 120,
        "priority": 90,
        "architect_id": "persistent-architect",
        "project": "frankenstein-2.0",
        "constraints": ["no authority changes"],
        "evidence_refs": ["commit:abc"],
    }


def bundle(
    intent_id="VOICE/INTERRUPTION-POLICY",
    objective="first wording",
    *,
    existing_reservation=None,
    now=None,
    terminal_packet_ids=(),
):
    return compile_intent_bundle(
        **compile_kwargs(intent_id=intent_id, objective=objective),
        existing_reservation=existing_reservation,
        now=now,
        terminal_packet_ids=terminal_packet_ids,
    )


def expiry_of(reservation):
    return datetime.fromisoformat(reservation["packet_expires_at"].replace("Z", "+00:00"))


class ArchitectIntentTests(unittest.TestCase):
    def test_explicit_identity_is_normalized_without_prose_inference(self):
        self.assertEqual(
            normalize_intent_id(" Voice/Interruption-Policy "),
            "voice/interruption-policy",
        )
        with self.assertRaises(IntentError):
            normalize_intent_id("infer this from a prose sentence")

    def test_same_intent_different_wording_collides_on_same_create_only_path(self):
        first = bundle(objective="first wording")
        second = bundle(objective="completely different words")
        self.assertEqual(first["intent_key"], second["intent_key"])
        self.assertEqual(first["reservation_path"], second["reservation_path"])
        self.assertEqual(first["reservation"]["generation"], 1)
        self.assertEqual(second["reservation"]["generation"], 1)
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

    def test_generation_paths_are_append_only_but_not_public_creation_input(self):
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
        with self.assertRaises(TypeError):
            compile_intent_bundle(**compile_kwargs(), generation=2)

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

    def test_active_existing_reservation_is_reused_and_cannot_be_bypassed_by_successor(self):
        first = bundle()
        before_expiry = expiry_of(first["reservation"]) - timedelta(seconds=1)
        self.assertEqual(
            reservation_decision(first["reservation"], now=before_expiry),
            "REUSE_EXISTING_PACKET",
        )
        attempted_successor = bundle(
            objective="different wording tries to bypass active generation",
            existing_reservation=first["reservation"],
            now=before_expiry,
        )
        self.assertEqual(attempted_successor["decision"], "REUSE_EXISTING_PACKET")
        self.assertIsNone(attempted_successor["packet"])
        self.assertEqual(
            attempted_successor["reservation_path"], first["reservation_path"]
        )
        self.assertEqual(attempted_successor["reservation"]["generation"], 1)
        self.assertEqual(
            attempted_successor["atomic_repository_contract"]["write_mode"],
            "NO_WRITE_REUSE_EXISTING_PACKET",
        )

    def test_omitting_observed_state_can_only_recompile_generation_one_collision_path(self):
        first = bundle()
        second = bundle(objective="caller ignores observed state")
        self.assertEqual(first["reservation"]["generation"], 1)
        self.assertEqual(second["reservation"]["generation"], 1)
        self.assertEqual(first["reservation_path"], second["reservation_path"])

    def test_expired_reservation_derives_exactly_next_generation(self):
        first = bundle()
        after_expiry = expiry_of(first["reservation"]) + timedelta(seconds=1)
        successor = bundle(
            objective="successor after expiry",
            existing_reservation=first["reservation"],
            now=after_expiry,
        )
        self.assertEqual(successor["decision"], "CREATE_CANDIDATE")
        self.assertEqual(successor["reservation"]["generation"], 2)
        self.assertTrue(successor["reservation_path"].endswith("/000002.json"))

    def test_terminal_reservation_derives_exactly_next_generation(self):
        first = bundle()
        before_expiry = expiry_of(first["reservation"]) - timedelta(seconds=1)
        successor = bundle(
            objective="successor after exact terminal evidence",
            existing_reservation=first["reservation"],
            now=before_expiry,
            terminal_packet_ids={first["packet"]["packet_id"]},
        )
        self.assertEqual(successor["decision"], "CREATE_CANDIDATE")
        self.assertEqual(successor["reservation"]["generation"], 2)

    def test_existing_reservation_for_other_intent_fails_closed(self):
        first = bundle(intent_id="voice/interrupt")
        with self.assertRaisesRegex(IntentError, "different coordination intent"):
            bundle(
                intent_id="voice/tts",
                existing_reservation=first["reservation"],
                now=expiry_of(first["reservation"]) + timedelta(seconds=1),
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

        reused = bundle(
            existing_reservation=reservation,
            now=expiry_of(reservation) - timedelta(seconds=1),
        )
        self.assertEqual(reused["decision"], "REUSE_EXISTING_PACKET")
        self.assertFalse(reused["reservation"]["mutation_authority"])
        self.assertFalse(reused["reservation"]["runtime_dispatch_authority"])
        self.assertFalse(reused["reservation"]["effect_authority"])
        self.assertEqual(reused["reservation"]["credit_delta"], 0)


if __name__ == "__main__":
    unittest.main()
