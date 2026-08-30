import pathlib
import tempfile
import threading
import unittest

from tools.coordination.architect_intent import (
    create_only_write,
    intent_evidence_ref,
    new_intent_packet,
    pending_path,
)
from tools.coordination.architect_packet import PacketError, validate_packet


def packet_for(*, intent_id="T7/ACK-INTEGRITY-REPAIR", revision="v1", objective="repair ACK integrity"):
    return new_intent_packet(
        target={"trigger": "4"},
        objective=objective,
        intent_id=intent_id,
        intent_revision=revision,
        action_class="CONTEXT_DELTA",
        ttl_minutes=120,
        priority=96,
        architect_id="persistent-architect",
        project="frankenstein-2.0",
        constraints=["no duplicate mutation", "no runtime credit"],
        evidence_refs=["commit:76c8943be674713f078df4de07badde5953f93f4"],
    )


class ArchitectCoordinationIntentTests(unittest.TestCase):
    def test_same_explicit_intent_different_wording_has_same_creation_path(self):
        first = packet_for(objective="close ACK classifier bypass")
        second = packet_for(objective="repair deterministic ACK classification")
        self.assertEqual(first["packet_id"], second["packet_id"])
        self.assertNotEqual(first["nonce"], second["nonce"])
        self.assertNotEqual(first["route_id"], second["route_id"])
        self.assertIn(intent_evidence_ref("T7/ACK-INTEGRITY-REPAIR", "v1"), first["evidence_refs"])
        validate_packet(first)
        validate_packet(second)

    def test_different_intents_remain_independently_routable(self):
        first = packet_for(intent_id="T7/ACK-INTEGRITY-REPAIR")
        second = packet_for(intent_id="T7/COORDINATION-CREATION-DEDUP")
        self.assertNotEqual(first["packet_id"], second["packet_id"])

    def test_explicit_revision_supersedes_without_rewriting_history(self):
        first = packet_for(revision="v1")
        successor = packet_for(revision="v2")
        self.assertNotEqual(first["packet_id"], successor["packet_id"])
        self.assertNotEqual(
            intent_evidence_ref("T7/ACK-INTEGRITY-REPAIR", "v1"),
            intent_evidence_ref("T7/ACK-INTEGRITY-REPAIR", "v2"),
        )

    def test_sequential_duplicate_reuses_existing_winner(self):
        first = packet_for(objective="first creator wording")
        second = packet_for(objective="second creator different wording")
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = pending_path(first, root=root)
            status1, winner1 = create_only_write(first, path)
            status2, winner2 = create_only_write(second, path)
        self.assertEqual(status1, "CREATED")
        self.assertEqual(status2, "REUSE_EXISTING")
        self.assertEqual(winner1["nonce"], winner2["nonce"])
        self.assertEqual(winner1["objective"], "first creator wording")
        self.assertEqual(winner2["objective"], "first creator wording")

    def test_concurrent_creators_yield_one_created_and_one_reuse(self):
        packets = [
            packet_for(objective="concurrent creator A"),
            packet_for(objective="concurrent creator B"),
        ]
        barrier = threading.Barrier(2)
        results = []
        errors = []
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = pending_path(packets[0], root=root)

            def worker(packet):
                try:
                    barrier.wait(timeout=2)
                    results.append(create_only_write(packet, path))
                except BaseException as exc:  # preserve thread failure for assertion
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(packet,)) for packet in packets]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

            self.assertFalse(errors)
            self.assertEqual(sorted(status for status, _ in results), ["CREATED", "REUSE_EXISTING"])
            nonces = {winner["nonce"] for _, winner in results}
            self.assertEqual(len(nonces), 1)
            persisted = path.read_text(encoding="utf-8")
            self.assertTrue(persisted.endswith("\n"))

    def test_creation_fence_cannot_mint_any_authority_or_credit(self):
        packet = packet_for()
        for field in (
            "credit_authority",
            "mutation_authority",
            "runtime_dispatch_authority",
            "effect_authority",
        ):
            self.assertIs(packet[field], False)
        validate_packet(packet)

    def test_intent_id_is_explicit_not_free_text_similarity(self):
        with self.assertRaises(PacketError):
            packet_for(intent_id="contains spaces and semantic prose")


if __name__ == "__main__":
    unittest.main()
