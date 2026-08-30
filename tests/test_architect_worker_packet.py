import copy
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

from tools.coordination.architect_packet import (
    PacketError,
    cmd_ack,
    compute_payload_digest,
    compute_route_id,
    make_ack,
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


class ArchitectWorkerPacketTests(unittest.TestCase):
    def ack(self, packet=None, context=None, **kwargs):
        return make_ack(
            packet or BASE_PACKET,
            context or CONTEXT,
            reason="classified from deterministic packet state",
            authority_head="deadbeef",
            observed_at=NOW,
            **kwargs,
        )

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
        ack = self.ack(
            event_head_ref="workpackages/state_events/F2-WP-715/000001.json",
            active_pointer_ref="workpackages/active/F2-WP-715.json",
        )
        self.assertEqual(ack["disposition"], "APPLIED")
        self.assertFalse(ack["new_mutation_authority"])
        self.assertFalse(ack["new_runtime_dispatch"])
        self.assertFalse(ack["new_effect_authority"])
        self.assertEqual(ack["credit_delta"], 0)
        self.assertGreater(ack["context_bytes_injected"], 0)
        self.assertEqual(ack["route_id"], BASE_PACKET["route_id"])
        self.assertEqual(ack["payload_digest"], BASE_PACKET["payload_digest"])
        self.assertEqual(ack["worker_id"], CONTEXT["worker_id"])

    def test_ack_tampered_payload_derives_schema_rejection(self):
        packet = copy.deepcopy(BASE_PACKET)
        packet["objective"] = "tampered after sealing"
        ack = self.ack(packet=packet)
        self.assertEqual(ack["disposition"], "REJECT_SCHEMA_INVALID")
        self.assertEqual(ack["context_bytes_injected"], 0)

    def test_ack_tampered_route_derives_schema_rejection(self):
        packet = copy.deepcopy(BASE_PACKET)
        packet["route_id"] = "0" * 64
        ack = self.ack(packet=packet)
        self.assertEqual(ack["disposition"], "REJECT_SCHEMA_INVALID")

    def test_ack_expired_packet_derives_stale_rejection(self):
        packet = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        ack = self.ack(packet=packet)
        self.assertEqual(ack["disposition"], "REJECT_STALE")

    def test_ack_misaddressed_packet_derives_rejection(self):
        ack = self.ack(context=dict(CONTEXT, worker_id="worker-B"))
        self.assertEqual(ack["disposition"], "REJECT_MISADDRESSED")

    def test_ack_duplicate_nonce_derives_ack_only(self):
        ack = self.ack(seen_nonces={"nonce-0001"})
        self.assertEqual(ack["disposition"], "ACK_ONLY_DUPLICATE")

    def test_ack_authority_conflict_derives_rejection(self):
        ack = self.ack(authority_conflict=True)
        self.assertEqual(ack["disposition"], "REJECT_AUTHORITY_CONFLICT")

    def test_caller_supplied_applied_cannot_override_classifier(self):
        packet = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        with self.assertRaisesRegex(PacketError, "disagrees with deterministic disposition"):
            make_ack(
                packet,
                CONTEXT,
                "APPLIED",
                reason="attempted stale override",
                authority_head="deadbeef",
                observed_at=NOW,
            )

    def test_cli_ack_derives_disposition_without_caller_override(self):
        packet = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        with tempfile.TemporaryDirectory() as tmpdir:
            packet_path = Path(tmpdir) / "packet.json"
            context_path = Path(tmpdir) / "context.json"
            output_path = Path(tmpdir) / "ack.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            context_path.write_text(json.dumps(CONTEXT), encoding="utf-8")
            args = Namespace(
                packet=str(packet_path),
                context=str(context_path),
                output=str(output_path),
                disposition=None,
                reason="deterministic CLI classification",
                authority_head="deadbeef",
                now=NOW.isoformat(),
                seen_nonces=None,
                superseded_packet_ids=None,
                authority_conflict=False,
                event_head_ref=None,
                active_pointer_ref=None,
            )
            self.assertEqual(cmd_ack(args), 3)
            ack = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(ack["disposition"], "REJECT_STALE")

    def test_cli_caller_applied_assertion_cannot_override_stale(self):
        packet = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        with tempfile.TemporaryDirectory() as tmpdir:
            packet_path = Path(tmpdir) / "packet.json"
            context_path = Path(tmpdir) / "context.json"
            output_path = Path(tmpdir) / "ack.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            context_path.write_text(json.dumps(CONTEXT), encoding="utf-8")
            args = Namespace(
                packet=str(packet_path),
                context=str(context_path),
                output=str(output_path),
                disposition="APPLIED",
                reason="attempted override",
                authority_head="deadbeef",
                now=NOW.isoformat(),
                seen_nonces=None,
                superseded_packet_ids=None,
                authority_conflict=False,
                event_head_ref=None,
                active_pointer_ref=None,
            )
            self.assertEqual(cmd_ack(args), 4)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
