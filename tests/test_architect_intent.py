import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.coordination.architect_intent import (
    IntentError,
    intent_key,
    load_intent_chain,
    mark_terminal,
    reserve_intent,
)
from tools.coordination.architect_packet import compute_payload_digest, compute_route_id


NOW = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)


def packet(*, packet_id="AWP-1", nonce="nonce-1", objective="one objective", expires_at="2026-08-31T06:00:00Z"):
    value = {
        "schema": "F2_ARCHITECT_WORKER_PACKET/v1",
        "packet_id": packet_id,
        "route_id": "PENDING",
        "nonce": nonce,
        "payload_digest": "PENDING",
        "issued_at": "2026-08-31T00:00:00Z",
        "expires_at": expires_at,
        "architect_id": "persistent-architect",
        "project": "frankenstein-2.0",
        "priority": 96,
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


class ArchitectIntentTests(unittest.TestCase):
    def test_same_explicit_intent_reuses_active_owner_despite_different_wording_and_nonce(self):
        first = packet(packet_id="AWP-1", nonce="nonce-1", objective="repair ACK classifier")
        second = packet(packet_id="AWP-2", nonce="nonce-2", objective="fix deterministic ACK integrity")
        with tempfile.TemporaryDirectory() as root:
            one = reserve_intent(root, "ACK-CLASSIFIER-INTEGRITY", first, now=NOW)
            two = reserve_intent(root, "ACK-CLASSIFIER-INTEGRITY", second, now=NOW)
            self.assertEqual(one["disposition"], "RESERVED")
            self.assertEqual(two["disposition"], "REUSE_ACTIVE")
            self.assertEqual(two["existing_event"]["packet_id"], "AWP-1")
            self.assertNotEqual(first["route_id"], second["route_id"])
            self.assertEqual(len(load_intent_chain(root, "ACK-CLASSIFIER-INTEGRITY")), 1)

    def test_different_intent_ids_are_independently_routable(self):
        with tempfile.TemporaryDirectory() as root:
            one = reserve_intent(root, "INTENT-A", packet(packet_id="A", nonce="A"), now=NOW)
            two = reserve_intent(root, "INTENT-B", packet(packet_id="B", nonce="B"), now=NOW)
            self.assertEqual(one["disposition"], "RESERVED")
            self.assertEqual(two["disposition"], "RESERVED")
            self.assertNotEqual(intent_key("INTENT-A"), intent_key("INTENT-B"))

    def test_expired_active_intent_allows_append_only_successor(self):
        first = packet(packet_id="OLD", nonce="old", expires_at="2026-08-31T00:30:00Z")
        successor = packet(packet_id="NEW", nonce="new", expires_at="2026-08-31T06:00:00Z")
        with tempfile.TemporaryDirectory() as root:
            reserve_intent(root, "INTENT-EXPIRY", first, now=datetime(2026, 8, 31, 0, 15, tzinfo=timezone.utc))
            result = reserve_intent(root, "INTENT-EXPIRY", successor, now=NOW)
            self.assertEqual(result["disposition"], "RESERVED")
            chain = load_intent_chain(root, "INTENT-EXPIRY")
            self.assertEqual([event["sequence"] for _, event in chain], [1, 2])
            self.assertEqual(chain[1][1]["parent_event_digest"], chain[0][1]["event_digest"])
            self.assertEqual(chain[0][1]["packet_id"], "OLD")
            self.assertEqual(chain[1][1]["packet_id"], "NEW")

    def test_terminal_intent_allows_successor_without_rewriting_history(self):
        first = packet(packet_id="P1", nonce="N1")
        successor = packet(packet_id="P2", nonce="N2")
        with tempfile.TemporaryDirectory() as root:
            reserve_intent(root, "INTENT-TERMINAL", first, now=NOW)
            terminal = mark_terminal(
                root,
                "INTENT-TERMINAL",
                packet=first,
                evidence_ref="research/result.json",
                now=datetime(2026, 8, 31, 1, 5, tzinfo=timezone.utc),
            )
            self.assertEqual(terminal["disposition"], "TERMINAL_RECORDED")
            next_result = reserve_intent(
                root,
                "INTENT-TERMINAL",
                successor,
                now=datetime(2026, 8, 31, 1, 6, tzinfo=timezone.utc),
            )
            self.assertEqual(next_result["disposition"], "RESERVED")
            chain = load_intent_chain(root, "INTENT-TERMINAL")
            self.assertEqual([event["state"] for _, event in chain], ["ACTIVE", "TERMINAL", "ACTIVE"])
            self.assertEqual(len(chain), 3)

    def test_stale_candidate_packet_cannot_reserve_intent(self):
        stale = packet(expires_at="2026-08-31T00:30:00Z")
        with tempfile.TemporaryDirectory() as root:
            result = reserve_intent(root, "INTENT-STALE", stale, now=NOW)
            self.assertEqual(result["disposition"], "REJECT_STALE_PACKET")
            self.assertEqual(load_intent_chain(root, "INTENT-STALE"), [])

    def test_event_tamper_fails_closed(self):
        first = packet()
        with tempfile.TemporaryDirectory() as root:
            result = reserve_intent(root, "INTENT-TAMPER", first, now=NOW)
            path = Path(result["event_path"])
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["packet_id"] = "TAMPERED"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(IntentError, "digest mismatch"):
                load_intent_chain(root, "INTENT-TAMPER")

    def test_intent_events_never_grant_authority_or_credit(self):
        with tempfile.TemporaryDirectory() as root:
            result = reserve_intent(root, "INTENT-ZERO-CREDIT", packet(), now=NOW)
            event = result["event"]
            self.assertFalse(event["new_mutation_authority"])
            self.assertFalse(event["new_runtime_dispatch"])
            self.assertFalse(event["new_effect_authority"])
            self.assertEqual(event["credit_delta"], 0)
            self.assertFalse(result["new_mutation_authority"])
            self.assertFalse(result["new_runtime_dispatch"])
            self.assertFalse(result["new_effect_authority"])
            self.assertEqual(result["credit_delta"], 0)

    def test_concurrent_same_checkout_creators_yield_one_active_reservation(self):
        candidate_a = packet(packet_id="A", nonce="A", objective="wording A")
        candidate_b = packet(packet_id="B", nonce="B", objective="wording B")
        with tempfile.TemporaryDirectory() as root:
            barrier = threading.Barrier(2)
            results = []
            errors = []

            def worker(candidate):
                try:
                    barrier.wait()
                    results.append(reserve_intent(root, "INTENT-RACE", candidate, now=NOW))
                except Exception as exc:  # pragma: no cover - diagnostic preservation
                    errors.append(exc)

            a = threading.Thread(target=worker, args=(candidate_a,))
            b = threading.Thread(target=worker, args=(candidate_b,))
            a.start()
            b.start()
            a.join()
            b.join()

            self.assertEqual(errors, [])
            dispositions = sorted(result["disposition"] for result in results)
            self.assertEqual(dispositions, ["RESERVED", "REUSE_ACTIVE"])
            chain = load_intent_chain(root, "INTENT-RACE")
            self.assertEqual(len(chain), 1)
            self.assertEqual(chain[0][1]["state"], "ACTIVE")

    def test_terminal_requires_exact_reserved_packet_identity(self):
        reserved = packet(packet_id="P1", nonce="N1")
        wrong = packet(packet_id="P2", nonce="N2")
        with tempfile.TemporaryDirectory() as root:
            reserve_intent(root, "INTENT-BINDING", reserved, now=NOW)
            with self.assertRaisesRegex(IntentError, "does not match active reservation"):
                mark_terminal(
                    root,
                    "INTENT-BINDING",
                    packet=wrong,
                    evidence_ref="wrong.json",
                    now=NOW,
                )


if __name__ == "__main__":
    unittest.main()
