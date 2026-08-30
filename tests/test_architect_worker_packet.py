import copy
import json
import pathlib
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

from tools.coordination.architect_packet import (
    PacketError,
    claim_coordination_intent,
    close_coordination_intent,
    compute_payload_digest,
    compute_route_id,
    coordination_intent_key,
    main,
    make_ack,
    new_packet,
    packet_disposition,
    target_matches,
    validate_packet,
)


def sealed_packet(**changes):
    packet = {
        "schema": "F2_ARCHITECT_WORKER_PACKET/v1",
        "packet_id": "AWP-TEST-0001",
        "route_id": "PENDING",
        "nonce": "nonce-0001",
        "payload_digest": "PENDING",
        "issued_at": "2026-08-31T00:00:00Z",
        "expires_at": "2026-08-31T06:00:00Z",
        "architect_id": "persistent-architect",
        "project": "frankenstein-2.0",
        "priority": 50,
        "action_class": "REVIEW_ONLY",
        "target": {"worker_id": "worker-A", "workpackage_id": "F2-WP-715"},
        "objective": "Review one exact boundary without mutation.",
        "constraints": ["no mutation"],
        "expected_output": {"ack_required": True},
        "evidence_refs": [],
        "supersedes_packet_ids": [],
        "credit_authority": False,
        "mutation_authority": False,
        "runtime_dispatch_authority": False,
        "effect_authority": False,
    }
    packet.update(changes)
    packet["payload_digest"] = compute_payload_digest(packet)
    packet["route_id"] = compute_route_id(packet)
    return packet


BASE_PACKET = sealed_packet()
CONTEXT = {
    "worker_id": "worker-A",
    "worker_lane": "REVIEW_ONLY",
    "trigger": "7",
    "workpackage_id": "F2-WP-715",
    "generation": 1,
    "claim_id": "claim-1",
    "organ": "GPT-5.6-Sol",
}
NOW = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)


def intent_packet(intent_id, objective="Repair one coordination boundary.", *, now=NOW, ttl_minutes=60):
    return new_packet(
        coordination_intent_id=intent_id,
        target={"trigger": "4"},
        objective=objective,
        action_class="CONTEXT_DELTA",
        ttl_minutes=ttl_minutes,
        priority=90,
        architect_id="persistent-architect",
        project="frankenstein-2.0",
        constraints=["no authority inflation"],
        evidence_refs=[],
        now=now,
    )


class ArchitectWorkerPacketTests(unittest.TestCase):
    def test_exact_worker_and_workpackage_match(self):
        validate_packet(BASE_PACKET)
        self.assertTrue(target_matches(BASE_PACKET["target"], CONTEXT))
        self.assertEqual(packet_disposition(BASE_PACKET, CONTEXT, now=NOW), "APPLIED")

    def test_exact_worker_packet_rejects_other_worker(self):
        other = dict(CONTEXT, worker_id="worker-B")
        self.assertEqual(packet_disposition(BASE_PACKET, other, now=NOW), "REJECT_MISADDRESSED")

    def test_list_selector_supports_bounded_cohort(self):
        packet = sealed_packet(target={"trigger": "7", "worker_lane": ["REVIEW_ONLY", "CANDIDATE_FALSIFIER"]})
        self.assertEqual(packet_disposition(packet, CONTEXT, now=NOW), "APPLIED")

    def test_empty_target_forbidden(self):
        packet = sealed_packet(target={})
        with self.assertRaises(PacketError):
            validate_packet(packet)
        self.assertEqual(packet_disposition(packet, CONTEXT, now=NOW), "REJECT_SCHEMA_INVALID")

    def test_expired_packet_fails_closed(self):
        packet = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        self.assertEqual(packet_disposition(packet, CONTEXT, now=NOW), "REJECT_STALE")

    def test_duplicate_nonce_is_ack_only(self):
        self.assertEqual(
            packet_disposition(BASE_PACKET, CONTEXT, now=NOW, seen_nonces={"nonce-0001"}),
            "ACK_ONLY_DUPLICATE",
        )

    def test_superseded_packet_fails_closed(self):
        self.assertEqual(
            packet_disposition(BASE_PACKET, CONTEXT, now=NOW, superseded_packet_ids={"AWP-TEST-0001"}),
            "REJECT_SUPERSEDED",
        )

    def test_authority_conflict_defeats_packet(self):
        self.assertEqual(
            packet_disposition(BASE_PACKET, CONTEXT, now=NOW, authority_conflict=True),
            "REJECT_AUTHORITY_CONFLICT",
        )

    def test_packet_cannot_claim_any_authority(self):
        for field in ("credit_authority", "mutation_authority", "runtime_dispatch_authority", "effect_authority"):
            packet = copy.deepcopy(BASE_PACKET)
            packet[field] = True
            with self.assertRaises(PacketError):
                validate_packet(packet)

    def test_payload_tamper_is_rejected(self):
        packet = copy.deepcopy(BASE_PACKET)
        packet["objective"] = "tampered after sealing"
        self.assertEqual(packet_disposition(packet, CONTEXT, now=NOW), "REJECT_SCHEMA_INVALID")

    def test_route_tamper_is_rejected(self):
        packet = copy.deepcopy(BASE_PACKET)
        packet["route_id"] = "0" * 64
        self.assertEqual(packet_disposition(packet, CONTEXT, now=NOW), "REJECT_SCHEMA_INVALID")

    def test_ack_is_non_authoritative_and_binds_route(self):
        ack = make_ack(
            BASE_PACKET,
            CONTEXT,
            "APPLIED",
            reason="matched exact worker and claim context",
            authority_head="deadbeef",
            observed_at=NOW,
            event_head_ref="workpackages/state_events/F2-WP-715/000001.json",
            active_pointer_ref="workpackages/active/F2-WP-715.json",
        )
        self.assertFalse(ack["new_mutation_authority"])
        self.assertFalse(ack["new_runtime_dispatch"])
        self.assertFalse(ack["new_effect_authority"])
        self.assertEqual(ack["credit_delta"], 0)
        self.assertGreater(ack["context_bytes_injected"], 0)
        self.assertEqual(ack["disposition"], "APPLIED")
        self.assertEqual(ack["route_id"], BASE_PACKET["route_id"])
        self.assertEqual(ack["payload_digest"], BASE_PACKET["payload_digest"])
        self.assertEqual(ack["worker_id"], CONTEXT["worker_id"])

    def test_ack_derives_fail_closed_dispositions(self):
        payload_tamper = copy.deepcopy(BASE_PACKET)
        payload_tamper["objective"] = "tampered after sealing"

        route_tamper = copy.deepcopy(BASE_PACKET)
        route_tamper["route_id"] = "0" * 64

        cases = [
            ("payload tamper", payload_tamper, CONTEXT, {}, "REJECT_SCHEMA_INVALID"),
            ("route tamper", route_tamper, CONTEXT, {}, "REJECT_SCHEMA_INVALID"),
            ("stale", sealed_packet(expires_at="2026-08-31T00:30:00Z"), CONTEXT, {}, "REJECT_STALE"),
            ("misaddressed", BASE_PACKET, dict(CONTEXT, worker_id="worker-B"), {}, "REJECT_MISADDRESSED"),
            ("duplicate nonce", BASE_PACKET, CONTEXT, {"seen_nonces": {"nonce-0001"}}, "ACK_ONLY_DUPLICATE"),
            ("authority conflict", BASE_PACKET, CONTEXT, {"authority_conflict": True}, "REJECT_AUTHORITY_CONFLICT"),
        ]

        for name, packet, context, kwargs, expected in cases:
            with self.subTest(name=name):
                ack = make_ack(
                    packet,
                    context,
                    reason=f"classification regression: {name}",
                    authority_head="deadbeef",
                    now=NOW,
                    **kwargs,
                )
                self.assertEqual(ack["disposition"], expected)
                self.assertEqual(ack["context_bytes_injected"], 0)
                self.assertEqual(ack["estimated_context_tokens_injected"], 0)
                self.assertFalse(ack["new_mutation_authority"])
                self.assertFalse(ack["new_runtime_dispatch"])
                self.assertFalse(ack["new_effect_authority"])
                self.assertEqual(ack["credit_delta"], 0)

    def test_caller_supplied_applied_cannot_override_rejection(self):
        stale = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        with self.assertRaisesRegex(PacketError, "does not match deterministic disposition REJECT_STALE"):
            make_ack(
                stale,
                CONTEXT,
                "APPLIED",
                reason="caller attempted to force apply",
                authority_head="deadbeef",
                now=NOW,
            )

    def test_cli_ack_cannot_force_applied_for_tampered_packet(self):
        packet = copy.deepcopy(BASE_PACKET)
        packet["objective"] = "tampered after sealing"

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            packet_path = root / "packet.json"
            context_path = root / "context.json"
            output_path = root / "ack.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            context_path.write_text(json.dumps(CONTEXT), encoding="utf-8")

            rc = main(
                [
                    "ack",
                    str(packet_path),
                    str(context_path),
                    str(output_path),
                    "--disposition",
                    "APPLIED",
                    "--reason",
                    "attempted forced disposition",
                    "--authority-head",
                    "deadbeef",
                    "--now",
                    "2026-08-31T01:00:00Z",
                ]
            )
            self.assertEqual(rc, 2)
            self.assertFalse(output_path.exists())

    def test_cli_ack_derives_rejection_without_disposition_argument(self):
        stale = sealed_packet(expires_at="2026-08-31T00:30:00Z")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            packet_path = root / "packet.json"
            context_path = root / "context.json"
            output_path = root / "ack.json"
            packet_path.write_text(json.dumps(stale), encoding="utf-8")
            context_path.write_text(json.dumps(CONTEXT), encoding="utf-8")

            rc = main(
                [
                    "ack",
                    str(packet_path),
                    str(context_path),
                    str(output_path),
                    "--reason",
                    "deterministic stale classification",
                    "--authority-head",
                    "deadbeef",
                    "--now",
                    "2026-08-31T01:00:00Z",
                ]
            )
            self.assertEqual(rc, 0)
            ack = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(ack["disposition"], "REJECT_STALE")
            self.assertEqual(ack["context_bytes_injected"], 0)

    def test_coordination_intent_field_is_sealed_without_breaking_historical_packets(self):
        validate_packet(BASE_PACKET)
        packet = intent_packet("T7/ACK-INTEGRITY")
        validate_packet(packet)
        self.assertEqual(packet_disposition(packet, {"trigger": "4"}, now=NOW), "APPLIED")
        tampered = copy.deepcopy(packet)
        tampered["coordination_intent_id"] = "T7/OTHER"
        self.assertEqual(packet_disposition(tampered, {"trigger": "4"}, now=NOW), "REJECT_SCHEMA_INVALID")

    def test_same_intent_different_wording_reuses_one_active_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = intent_packet("COORD/ACK-FIX", "Repair ACK classification bypass.")
            second = intent_packet("COORD/ACK-FIX", "Close the same ACK validation weakness using different wording.")
            d1, e1, _ = claim_coordination_intent(tmp, first, now=NOW)
            d2, e2, _ = claim_coordination_intent(tmp, second, now=NOW)
            self.assertEqual(d1, "CLAIMED")
            self.assertEqual(d2, "REUSE_ACTIVE")
            self.assertEqual(e2["owner_packet_id"], e1["owner_packet_id"])
            key_dir = pathlib.Path(tmp) / coordination_intent_key("COORD/ACK-FIX")
            self.assertEqual([p.name for p in key_dir.glob("*.json")], ["000001.json"])

    def test_concurrent_same_intent_creators_yield_claim_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            barrier = threading.Barrier(2)
            lock = threading.Lock()
            outcomes = []

            def creator(objective):
                packet = intent_packet("COORD/RACE-1", objective)
                barrier.wait()
                result = claim_coordination_intent(tmp, packet, now=NOW)
                with lock:
                    outcomes.append((result[0], result[1]["owner_packet_id"]))

            threads = [
                threading.Thread(target=creator, args=("wording A",)),
                threading.Thread(target=creator, args=("wording B",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(sorted(disposition for disposition, _ in outcomes), ["CLAIMED", "REUSE_ACTIVE"])
            self.assertEqual(len({owner for _, owner in outcomes}), 1)
            key_dir = pathlib.Path(tmp) / coordination_intent_key("COORD/RACE-1")
            self.assertEqual([p.name for p in key_dir.glob("*.json")], ["000001.json"])

    def test_different_intents_are_independently_routable(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1, e1, _ = claim_coordination_intent(tmp, intent_packet("COORD/A"), now=NOW)
            d2, e2, _ = claim_coordination_intent(tmp, intent_packet("COORD/B"), now=NOW)
            self.assertEqual((d1, d2), ("CLAIMED", "CLAIMED"))
            self.assertNotEqual(e1["intent_key"], e2["intent_key"])

    def test_expired_intent_can_be_superseded_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = intent_packet("COORD/EXPIRY", now=NOW, ttl_minutes=10)
            d1, e1, _ = claim_coordination_intent(tmp, first, now=NOW)
            later = NOW + timedelta(minutes=20)
            second = intent_packet("COORD/EXPIRY", "successor after expiry", now=later, ttl_minutes=10)
            d2, e2, _ = claim_coordination_intent(tmp, second, now=later)
            self.assertEqual((d1, d2), ("CLAIMED", "CLAIMED"))
            self.assertEqual((e1["sequence"], e2["sequence"]), (1, 2))
            key_dir = pathlib.Path(tmp) / coordination_intent_key("COORD/EXPIRY")
            self.assertEqual(sorted(p.name for p in key_dir.glob("*.json")), ["000001.json", "000002.json"])

    def test_terminal_intent_can_be_superseded_without_history_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = intent_packet("COORD/TERMINAL")
            d1, e1, first_path = claim_coordination_intent(tmp, first, now=NOW)
            first_bytes = first_path.read_bytes()
            close_disposition, terminal, _ = close_coordination_intent(
                tmp,
                "COORD/TERMINAL",
                reason="repair merged",
                now=NOW + timedelta(minutes=5),
            )
            second = intent_packet("COORD/TERMINAL", "new legal successor", now=NOW + timedelta(minutes=6))
            d2, e2, _ = claim_coordination_intent(tmp, second, now=NOW + timedelta(minutes=6))
            self.assertEqual(d1, "CLAIMED")
            self.assertEqual(close_disposition, "TERMINALIZED")
            self.assertEqual(terminal["sequence"], 2)
            self.assertEqual(d2, "CLAIMED")
            self.assertEqual(e2["sequence"], 3)
            self.assertEqual(first_path.read_bytes(), first_bytes)

    def test_intent_events_cannot_mint_authority_or_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, active, _ = claim_coordination_intent(tmp, intent_packet("COORD/ZERO-CREDIT"), now=NOW)
            _, terminal, _ = close_coordination_intent(
                tmp,
                "COORD/ZERO-CREDIT",
                reason="closed",
                now=NOW + timedelta(minutes=1),
            )
            for event in (active, terminal):
                self.assertFalse(event["new_mutation_authority"])
                self.assertFalse(event["new_runtime_dispatch"])
                self.assertFalse(event["new_effect_authority"])
                self.assertEqual(event["credit_delta"], 0)

    def test_cli_new_reuses_active_intent_and_does_not_write_second_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            intent_root = root / "intents"
            first_output = root / "first.json"
            second_output = root / "second.json"
            common = [
                "--coordination-intent-id",
                "COORD/CLI",
                "--intent-root",
                str(intent_root),
                "--target-json",
                '{"trigger":"4"}',
                "--action-class",
                "CONTEXT_DELTA",
                "--now",
                "2026-08-31T01:00:00Z",
            ]
            rc1 = main(["new", *common, "--objective", "first wording", "--output", str(first_output)])
            rc2 = main(["new", *common, "--objective", "different wording", "--output", str(second_output)])
            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 3)
            self.assertTrue(first_output.exists())
            self.assertFalse(second_output.exists())


if __name__ == "__main__":
    unittest.main()
