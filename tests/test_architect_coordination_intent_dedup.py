import copy
import json
import pathlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from tools.coordination.architect_packet import (
    PacketError,
    compute_payload_digest,
    compute_route_id,
    coordination_intent_packet_id,
    main,
    new_packet,
    packet_disposition,
    validate_packet,
)


def generated_packet(
    intent_id: str,
    *,
    objective: str = "Route one exact coordination repair.",
    generation: int = 1,
    supersedes=(),
):
    return new_packet(
        target={"trigger": "4"},
        objective=objective,
        action_class="CONTEXT_DELTA",
        ttl_minutes=120,
        priority=96,
        architect_id="persistent-architect",
        project="frankenstein-2.0",
        constraints=["preserve authority boundaries"],
        evidence_refs=[],
        coordination_intent_id=intent_id,
        coordination_intent_generation=generation,
        supersedes_packet_ids=supersedes,
    )


class ArchitectCoordinationIntentDedupTests(unittest.TestCase):
    def test_same_explicit_intent_and_generation_share_create_only_packet_path(self):
        first = generated_packet("T7/ACK-INTEGRITY-REPAIR", objective="Repair ACK integrity.")
        second = generated_packet(
            "T7/ACK-INTEGRITY-REPAIR",
            objective="Different wording for the exact same explicit repair boundary.",
        )

        self.assertEqual(first["packet_id"], second["packet_id"])
        self.assertNotEqual(first["nonce"], second["nonce"])
        self.assertNotEqual(first["payload_digest"], second["payload_digest"])
        self.assertNotEqual(first["route_id"], second["route_id"])
        self.assertEqual(
            first["packet_id"],
            coordination_intent_packet_id("T7/ACK-INTEGRITY-REPAIR", 1),
        )

    def test_two_concurrent_creators_yield_one_create_only_owner(self):
        intent_id = "T7/COORDINATION-CREATION-DEDUP"
        packet_id = coordination_intent_packet_id(intent_id, 1)

        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / f"{packet_id}.json"

            def create(objective):
                return main(
                    [
                        "new",
                        "--target-json",
                        json.dumps({"trigger": "4"}),
                        "--objective",
                        objective,
                        "--action-class",
                        "CONTEXT_DELTA",
                        "--intent-id",
                        intent_id,
                        "--output",
                        str(output),
                    ]
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = sorted(pool.map(create, ["creator A wording", "creator B wording"]))

            self.assertEqual(results, [0, 4])
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted["packet_id"], packet_id)
            self.assertEqual(persisted["coordination_intent_id"], intent_id)
            self.assertEqual(persisted["coordination_intent_generation"], 1)
            self.assertFalse(persisted["mutation_authority"])
            self.assertFalse(persisted["runtime_dispatch_authority"])
            self.assertFalse(persisted["effect_authority"])
            self.assertFalse(persisted["credit_authority"])

    def test_different_intents_remain_independently_routable(self):
        first = generated_packet("T7/BOUNDARY-A")
        second = generated_packet("T7/BOUNDARY-B")
        self.assertNotEqual(first["packet_id"], second["packet_id"])
        validate_packet(first)
        validate_packet(second)

    def test_successor_generation_requires_explicit_supersession(self):
        first = generated_packet("T7/RETRYABLE-BOUNDARY")
        with self.assertRaisesRegex(PacketError, "must explicitly supersede"):
            generated_packet("T7/RETRYABLE-BOUNDARY", generation=2)

        second = generated_packet(
            "T7/RETRYABLE-BOUNDARY",
            generation=2,
            supersedes=[first["packet_id"]],
        )
        self.assertNotEqual(first["packet_id"], second["packet_id"])
        self.assertEqual(second["supersedes_packet_ids"], [first["packet_id"]])

    def test_intent_identity_tamper_fails_even_if_digest_and_route_are_resealed(self):
        packet = generated_packet("T7/ORIGINAL-BOUNDARY")
        tampered = copy.deepcopy(packet)
        tampered["coordination_intent_id"] = "T7/OTHER-BOUNDARY"
        tampered["payload_digest"] = compute_payload_digest(tampered)
        tampered["route_id"] = compute_route_id(tampered)

        with self.assertRaisesRegex(PacketError, "packet_id does not match coordination intent"):
            validate_packet(tampered)
        self.assertEqual(
            packet_disposition(
                tampered,
                {"trigger": "4"},
            ),
            "REJECT_SCHEMA_INVALID",
        )

    def test_legacy_v1_packet_without_intent_fields_remains_valid(self):
        packet = {
            "schema": "F2_ARCHITECT_WORKER_PACKET/v1",
            "packet_id": "AWP-LEGACY-0001",
            "route_id": "PENDING",
            "nonce": "legacy-nonce",
            "payload_digest": "PENDING",
            "issued_at": "2026-08-31T00:00:00Z",
            "expires_at": "2026-08-31T06:00:00Z",
            "architect_id": "persistent-architect",
            "project": "frankenstein-2.0",
            "priority": 50,
            "action_class": "REVIEW_ONLY",
            "target": {"trigger": "4"},
            "objective": "Legacy compatibility probe.",
            "constraints": [],
            "expected_output": {"ack_required": True},
            "evidence_refs": [],
            "supersedes_packet_ids": [],
            "credit_authority": False,
            "mutation_authority": False,
            "runtime_dispatch_authority": False,
            "effect_authority": False,
        }
        packet["payload_digest"] = compute_payload_digest(packet)
        packet["route_id"] = compute_route_id(packet)
        validate_packet(packet)


if __name__ == "__main__":
    unittest.main()
