import concurrent.futures
import tempfile
import unittest
from datetime import datetime, timezone

from tools.coordination.architect_intent import active_marker_path, claim_intent, intent_key
from tools.coordination.architect_packet import compute_payload_digest, compute_route_id


def packet(packet_id: str, expires_at: str = "2026-08-31T06:00:00Z", objective: str = "repair"):
    value = {
        "schema": "F2_ARCHITECT_WORKER_PACKET/v1",
        "packet_id": packet_id,
        "route_id": "PENDING",
        "nonce": f"nonce-{packet_id}",
        "payload_digest": "PENDING",
        "issued_at": "2026-08-31T00:00:00Z",
        "expires_at": expires_at,
        "architect_id": "persistent-architect",
        "project": "frankenstein-2.0",
        "priority": 90,
        "action_class": "CONTEXT_DELTA",
        "target": {"trigger": "4"},
        "objective": objective,
        "constraints": [],
        "expected_output": {"ack_required": True},
        "evidence_refs": [],
        "supersedes_packet_ids": [],
        "credit_authority": False,
        "mutation_authority": False,
        "runtime_dispatch_authority": False,
        "effect_authority": False,
    }
    value["payload_digest"] = compute_payload_digest(value)
    value["route_id"] = compute_route_id(value)
    return value


NOW = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)


class CoordinationIntentTests(unittest.TestCase):
    def test_same_explicit_intent_reuses_active_owner_despite_different_wording(self):
        with tempfile.TemporaryDirectory() as td:
            first = claim_intent(
                td,
                intent_id="ACK_CLASSIFICATION_REPAIR_V1",
                packet=packet("P1", objective="wording A"),
                authority_head="h1",
                now=NOW,
            )
            second = claim_intent(
                td,
                intent_id="ACK_CLASSIFICATION_REPAIR_V1",
                packet=packet("P2", objective="totally different wording"),
                authority_head="h1",
                now=NOW,
            )
            self.assertEqual(first["result"], "CLAIMED")
            self.assertEqual(second["result"], "REUSE_ACTIVE")
            self.assertEqual(second["active_packet_id"], "P1")

    def test_concurrent_same_intent_yields_one_owner_and_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            candidates = [packet("P-A"), packet("P-B")]

            def run(candidate):
                return claim_intent(td, intent_id="INTENT-X", packet=candidate, authority_head="h1", now=NOW)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(run, candidates))

            self.assertEqual(sorted(result["result"] for result in results), ["CLAIMED", "REUSE_ACTIVE"])
            owners = {result["active_packet_id"] for result in results}
            self.assertEqual(len(owners), 1)

    def test_different_intents_are_independently_routable(self):
        with tempfile.TemporaryDirectory() as td:
            a = claim_intent(td, intent_id="INTENT-A", packet=packet("P-A"), authority_head="h1", now=NOW)
            b = claim_intent(td, intent_id="INTENT-B", packet=packet("P-B"), authority_head="h1", now=NOW)
            self.assertEqual(a["result"], "CLAIMED")
            self.assertEqual(b["result"], "CLAIMED")
            self.assertNotEqual(intent_key("INTENT-A"), intent_key("INTENT-B"))

    def test_expired_intent_can_be_superseded_without_rewriting_history(self):
        with tempfile.TemporaryDirectory() as td:
            early = datetime(2026, 8, 31, 0, 10, tzinfo=timezone.utc)
            first = claim_intent(
                td,
                intent_id="INTENT-X",
                packet=packet("P1", expires_at="2026-08-31T00:30:00Z"),
                authority_head="h1",
                now=early,
            )
            history1 = first["history_marker"]
            second = claim_intent(td, intent_id="INTENT-X", packet=packet("P2"), authority_head="h2", now=NOW)
            self.assertEqual(second["result"], "SUPERSEDED_EXPIRED")
            self.assertEqual(second["supersedes_packet_id"], "P1")
            self.assertNotEqual(history1, second["history_marker"])
            self.assertTrue(active_marker_path(td, "INTENT-X").exists())

    def test_terminal_intent_can_be_superseded(self):
        with tempfile.TemporaryDirectory() as td:
            first = claim_intent(td, intent_id="INTENT-X", packet=packet("P1"), authority_head="h1", now=NOW)
            second = claim_intent(
                td,
                intent_id="INTENT-X",
                packet=packet("P2"),
                authority_head="h2",
                now=NOW,
                terminal_packet_ids={"P1"},
            )
            self.assertEqual(first["result"], "CLAIMED")
            self.assertEqual(second["result"], "SUPERSEDED_TERMINAL")
            self.assertEqual(second["supersedes_packet_id"], "P1")

    def test_creation_fence_never_mints_authority_or_credit(self):
        with tempfile.TemporaryDirectory() as td:
            result = claim_intent(td, intent_id="INTENT-X", packet=packet("P1"), authority_head="h1", now=NOW)
            self.assertFalse(result["new_mutation_authority"])
            self.assertFalse(result["new_runtime_dispatch"])
            self.assertFalse(result["new_effect_authority"])
            self.assertEqual(result["credit_delta"], 0)


if __name__ == "__main__":
    unittest.main()
