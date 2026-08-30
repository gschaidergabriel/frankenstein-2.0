import copy
import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone

from tools.coordination.architect_packet import (
    PacketError,
    compute_payload_digest,
    compute_route_id,
    main,
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
            reason="matched exact worker and claim context",
            authority_head="deadbeef",
            observed_at=NOW,
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

    def test_public_ack_derives_all_fail_closed_dispositions(self):
        payload_tamper = copy.deepcopy(BASE_PACKET)
        payload_tamper["objective"] = "tampered after sealing"
        route_tamper = copy.deepcopy(BASE_PACKET)
        route_tamper["route_id"] = "0" * 64
        stale = sealed_packet(expires_at="2026-08-31T00:30:00Z")
        cases = [
            ("payload_tamper", payload_tamper, CONTEXT, {}, "REJECT_SCHEMA_INVALID"),
            ("route_tamper", route_tamper, CONTEXT, {}, "REJECT_SCHEMA_INVALID"),
            ("stale", stale, CONTEXT, {}, "REJECT_STALE"),
            ("misaddressed", BASE_PACKET, dict(CONTEXT, worker_id="worker-B"), {}, "REJECT_MISADDRESSED"),
            ("duplicate", BASE_PACKET, CONTEXT, {"seen_nonces": {"nonce-0001"}}, "ACK_ONLY_DUPLICATE"),
            ("authority", BASE_PACKET, CONTEXT, {"authority_conflict": True}, "REJECT_AUTHORITY_CONFLICT"),
        ]
        for label, packet, context, kwargs, expected in cases:
            with self.subTest(label=label):
                ack = make_ack(
                    packet,
                    context,
                    reason=label,
                    authority_head="deadbeef",
                    observed_at=NOW,
                    **kwargs,
                )
                self.assertEqual(ack["disposition"], expected)
                self.assertEqual(ack["context_bytes_injected"], 0)
                self.assertEqual(ack["estimated_context_tokens_injected"], 0)
                self.assertEqual(ack["credit_delta"], 0)

    def test_cli_ack_classifies_instead_of_accepting_caller_disposition(self):
        packet = copy.deepcopy(BASE_PACKET)
        packet["route_id"] = "0" * 64
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
                    "--now",
                    "2026-08-31T01:00:00Z",
                    "--reason",
                    "CLI classification regression",
                    "--authority-head",
                    "deadbeef",
                ]
            )
            self.assertEqual(rc, 0)
            ack = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(ack["disposition"], "REJECT_SCHEMA_INVALID")
            self.assertEqual(ack["context_bytes_injected"], 0)

    def test_cli_ack_supports_duplicate_and_authority_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            packet_path = root / "packet.json"
            context_path = root / "context.json"
            seen_path = root / "seen.json"
            duplicate_output = root / "duplicate.json"
            conflict_output = root / "conflict.json"
            packet_path.write_text(json.dumps(BASE_PACKET), encoding="utf-8")
            context_path.write_text(json.dumps(CONTEXT), encoding="utf-8")
            seen_path.write_text(json.dumps(["nonce-0001"]), encoding="utf-8")
            common = [
                str(packet_path),
                str(context_path),
                "--now",
                "2026-08-31T01:00:00Z",
                "--reason",
                "CLI deterministic classification",
                "--authority-head",
                "deadbeef",
            ]
            self.assertEqual(
                main(["ack", common[0], common[1], str(duplicate_output), *common[2:], "--seen-nonces", str(seen_path)]),
                0,
            )
            self.assertEqual(
                json.loads(duplicate_output.read_text(encoding="utf-8"))["disposition"],
                "ACK_ONLY_DUPLICATE",
            )
            self.assertEqual(
                main(["ack", common[0], common[1], str(conflict_output), *common[2:], "--authority-conflict"]),
                0,
            )
            self.assertEqual(
                json.loads(conflict_output.read_text(encoding="utf-8"))["disposition"],
                "REJECT_AUTHORITY_CONFLICT",
            )


if __name__ == "__main__":
    unittest.main()
