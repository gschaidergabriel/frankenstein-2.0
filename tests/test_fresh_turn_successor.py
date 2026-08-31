from __future__ import annotations

import hashlib
import inspect
import json
import socket
import unittest
from unittest import mock

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.fresh_turn_successor import (
    FreshTurnSuccessorError,
    memory_evidence_sha256,
    project_fresh_turn,
)
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    MemoryReferenceEvidence,
    REENTRY_RECEIPT_SCHEMA,
    VoiceHeardResultReentryReceipt,
)


_REENTRY_CLASSIFICATION = VoiceHeardResultReentryReceipt.__dataclass_fields__["classification"].default
_RESTART_REF = "runtime:trigger4/restart_reentry_composition/run-33422253285"
_RESTART_SHA256 = "8" * 64


def _canonical_digest(value) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class FreshTurnSuccessorTests(unittest.TestCase):
    def predecessor(self, suffix: str = "a") -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id=f"session-wp719-{suffix}",
            agent_id="frankenstein-2",
            task_id="task-wp719",
            turn_id=f"turn-input-{suffix}",
            causal_id=f"causal-input-wp719-{suffix}",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref=f"fixture:wp719:{suffix}",
            input_sha256="1" * 64,
            provenance_refs=(f"test:wp719:{suffix}",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id=f"causal-session-wp719-{suffix}",
                generation=4,
                turn_id=f"turn-session-{suffix}",
            ),
            provenance_refs=(f"test:wp719-session:{suffix}",),
        )

    def receipt(
        self,
        predecessor: VoiceSessionCapsule,
        *,
        suffix: str = "a",
        with_gwt: bool = True,
        with_memory: bool = True,
        tool_ref_disposition: str = "REFERENCE_ONLY_NO_TOOL_OR_EFFECT_REPLAY",
    ) -> VoiceHeardResultReentryReceipt:
        memory = (
            (
                MemoryReferenceEvidence(
                    memory_id=f"memory:heard:{suffix}",
                    lifecycle_generation=7,
                    lifecycle_state_sha256="2" * 64,
                    typed_memory_sha256="3" * 64,
                ),
            )
            if with_memory
            else ()
        )
        gwt_id = f"gwt-binding:heard:{suffix}" if with_gwt else None
        gwt_sha = "4" * 64 if with_gwt else None
        provenance = (f"test:wp719-reentry:{suffix}",)
        payload = {
            "schema": REENTRY_RECEIPT_SCHEMA,
            "heard_result_ref": f"voice-heard-result:heard-only:{suffix}",
            "heard_result_sha256": "5" * 64,
            "voiceoutcome_id": f"voice-outcome:heard-only:{suffix}",
            "voiceoutcome_sha256": "6" * 64,
            "voice_session_id": predecessor.voice_session_id,
            "voice_session_sha256": predecessor.sha256(),
            "close_event_id": f"voice-close:heard-only:{suffix}",
            "ordered_output_packet_ids": [f"output-heard-{suffix}"],
            "context_view_sha256": None,
            "context_item_id": None,
            "context_cost_witness_sha256": None,
            "memory_evidence": [item.as_dict() for item in memory],
            "gwt_binding_id": gwt_id,
            "gwt_binding_sha256": gwt_sha,
            "tool_ref_disposition": tool_ref_disposition,
            "provenance_refs": list(provenance),
            "classification": _REENTRY_CLASSIFICATION,
            "canonical_memory_write_credit": 0,
            "gwt_runtime_credit": 0,
            "effect_credit": 0,
            "physical_audio_credit": 0,
            "whole_system_acceptance": False,
        }
        return VoiceHeardResultReentryReceipt(
            receipt_id="voice-reentry-receipt:" + _canonical_digest(payload),
            heard_result_ref=payload["heard_result_ref"],
            heard_result_sha256=payload["heard_result_sha256"],
            voiceoutcome_id=payload["voiceoutcome_id"],
            voiceoutcome_sha256=payload["voiceoutcome_sha256"],
            voice_session_id=payload["voice_session_id"],
            voice_session_sha256=payload["voice_session_sha256"],
            close_event_id=payload["close_event_id"],
            ordered_output_packet_ids=tuple(payload["ordered_output_packet_ids"]),
            context_view_sha256=None,
            context_item_id=None,
            context_cost_witness_sha256=None,
            memory_evidence=memory,
            gwt_binding_id=gwt_id,
            gwt_binding_sha256=gwt_sha,
            tool_ref_disposition=tool_ref_disposition,
            provenance_refs=provenance,
        )

    def restore_receipt(self, receipt: VoiceHeardResultReentryReceipt) -> VoiceHeardResultReentryReceipt:
        value = receipt.as_dict()
        return VoiceHeardResultReentryReceipt(
            receipt_id=value["receipt_id"],
            heard_result_ref=value["heard_result_ref"],
            heard_result_sha256=value["heard_result_sha256"],
            voiceoutcome_id=value["voiceoutcome_id"],
            voiceoutcome_sha256=value["voiceoutcome_sha256"],
            voice_session_id=value["voice_session_id"],
            voice_session_sha256=value["voice_session_sha256"],
            close_event_id=value["close_event_id"],
            ordered_output_packet_ids=tuple(value["ordered_output_packet_ids"]),
            context_view_sha256=value["context_view_sha256"],
            context_item_id=value["context_item_id"],
            context_cost_witness_sha256=value["context_cost_witness_sha256"],
            memory_evidence=tuple(MemoryReferenceEvidence(**item) for item in value["memory_evidence"]),
            gwt_binding_id=value["gwt_binding_id"],
            gwt_binding_sha256=value["gwt_binding_sha256"],
            tool_ref_disposition=value["tool_ref_disposition"],
            provenance_refs=tuple(value["provenance_refs"]),
            schema=value["schema"],
            classification=value["classification"],
        )

    def fresh_causals(self, predecessor: VoiceSessionCapsule, suffix: str = "1"):
        fresh_intent = predecessor.session_causal_identity.derive(
            causal_id=f"causal-fresh-intent-{suffix}",
            generation=predecessor.session_causal_identity.generation + 1,
            turn_id=f"turn-fresh-{suffix}",
        )
        fresh_session = fresh_intent.derive(
            causal_id=f"causal-fresh-session-{suffix}",
            generation=fresh_intent.generation + 1,
            turn_id=f"turn-fresh-session-{suffix}",
        )
        return fresh_intent, fresh_session

    def project(
        self,
        predecessor: VoiceSessionCapsule,
        receipt: VoiceHeardResultReentryReceipt,
        *,
        suffix: str = "1",
        input_sha256: str = "7" * 64,
        existing=None,
    ):
        fresh_intent, fresh_session = self.fresh_causals(predecessor, suffix)
        kwargs = {
            "predecessor_session": predecessor,
            "predecessor_reentry": receipt,
            "predecessor_reentry_sha256": receipt.sha256(),
            "fresh_intent_causal_identity": fresh_intent,
            "fresh_session_causal_identity": fresh_session,
            "input_ref": f"voice-input:fresh:{suffix}",
            "input_sha256": input_sha256,
            "expected_gwt_binding_id": receipt.gwt_binding_id,
            "expected_gwt_binding_sha256": receipt.gwt_binding_sha256,
            "expected_memory_evidence_sha256": memory_evidence_sha256(receipt),
            "provenance_refs": ("test:F2-WP-719",),
            "existing": existing,
        }
        parameters = inspect.signature(project_fresh_turn).parameters
        if "prerequisite_restart_receipt_ref" in parameters:
            kwargs["prerequisite_restart_receipt_ref"] = _RESTART_REF
            kwargs["prerequisite_restart_receipt_sha256"] = _RESTART_SHA256
        return project_fresh_turn(**kwargs)

    def test_fresh1_valid_prior_reentry_projects_one_distinct_fresh_turn(self) -> None:
        predecessor = self.predecessor()
        receipt = self.receipt(predecessor)
        intent, session, projection = self.project(predecessor, receipt)
        self.assertNotEqual(session.voice_session_id, predecessor.voice_session_id)
        self.assertNotEqual(intent.causal_identity.turn_id, predecessor.session_causal_identity.turn_id)
        self.assertEqual(projection.predecessor_reentry_receipt_id, receipt.receipt_id)
        self.assertEqual(projection.gwt_binding_id, receipt.gwt_binding_id)
        self.assertEqual(projection.gwt_binding_sha256, receipt.gwt_binding_sha256)
        self.assertEqual(projection.memory_evidence_sha256, memory_evidence_sha256(receipt))
        self.assertEqual(projection.tool_ref_disposition, receipt.tool_ref_disposition)

    def test_fresh2_stale_or_foreign_gwt_lineage_fails_closed(self) -> None:
        predecessor = self.predecessor()
        receipt = self.receipt(predecessor, with_gwt=True)
        fresh_intent, fresh_session = self.fresh_causals(predecessor)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "stale/foreign GWT binding id"):
            project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=fresh_intent,
                fresh_session_causal_identity=fresh_session,
                input_ref="voice-input:fresh:gwt-foreign",
                input_sha256="7" * 64,
                expected_gwt_binding_id="gwt-binding:foreign",
                expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
                expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            )

    def test_fresh3_mismatched_memory_relation_fails_closed(self) -> None:
        predecessor = self.predecessor()
        receipt = self.receipt(predecessor, with_memory=True)
        fresh_intent, fresh_session = self.fresh_causals(predecessor)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "memory relation evidence digest mismatch"):
            project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=fresh_intent,
                fresh_session_causal_identity=fresh_session,
                input_ref="voice-input:fresh:memory-mismatch",
                input_sha256="7" * 64,
                expected_gwt_binding_id=receipt.gwt_binding_id,
                expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
                expected_memory_evidence_sha256="9" * 64,
            )

    def test_fresh4_same_valid_reentry_is_exactly_once_and_semantic_drift_rejected(self) -> None:
        predecessor = self.predecessor()
        receipt = self.receipt(predecessor)
        first = self.project(predecessor, receipt)
        second = self.project(predecessor, receipt, existing=first[2])
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        self.assertIs(second[2], first[2])
        with self.assertRaisesRegex(FreshTurnSuccessorError, "conflicts"):
            self.project(predecessor, receipt, input_sha256="a" * 64, existing=first[2])

    def test_fresh5_unheard_cancelled_fragment_has_no_projection_channel(self) -> None:
        predecessor = self.predecessor()
        receipt = self.receipt(predecessor)
        unheard_secret = "UNHEARD_CANCELLED_FRAGMENT_MUST_NOT_BECOME_HISTORY"
        intent, session, projection = self.project(predecessor, receipt)
        material = json.dumps(
            {
                "intent": intent.as_dict(),
                "session": session.as_dict(),
                "projection": projection.as_dict(),
            },
            sort_keys=True,
        )
        self.assertNotIn(unheard_secret, material)
        self.assertEqual(receipt.ordered_output_packet_ids, ("output-heard-a",))
        self.assertNotIn("text_segments", projection.as_dict())

    def test_fresh6_wait_backchannel_only_does_not_invent_full_assistant_speech(self) -> None:
        predecessor = self.predecessor("wait")
        receipt = self.receipt(
            predecessor,
            suffix="wait",
            tool_ref_disposition="WAIT_BACKCHANNEL_REFERENCE_ONLY_NO_FULL_SPEECH",
        )
        _intent, _session, projection = self.project(predecessor, receipt, suffix="wait")
        payload = projection.as_dict()
        self.assertEqual(projection.tool_ref_disposition, "WAIT_BACKCHANNEL_REFERENCE_ONLY_NO_FULL_SPEECH")
        self.assertNotIn("assistant_text", payload)
        self.assertNotIn("utterance", payload)
        self.assertEqual(payload["whole_voice_e2e_credit"], 0)

    def test_fresh7_restart_roundtrip_before_successor_preserves_exact_once_projection(self) -> None:
        predecessor = self.predecessor("restart")
        receipt = self.receipt(predecessor, suffix="restart")
        before = self.project(predecessor, receipt, suffix="restart")
        restored_predecessor = VoiceSessionCapsule.from_mapping(
            json.loads(json.dumps(predecessor.as_dict(), sort_keys=True))
        )
        restored_receipt = self.restore_receipt(receipt)
        after = self.project(restored_predecessor, restored_receipt, suffix="restart")
        self.assertEqual(before, after)
        self.assertEqual(before[2].projection_id, after[2].projection_id)

    def test_fresh8_tool_and_memory_refs_remain_reference_only_with_zero_replay_authority(self) -> None:
        predecessor = self.predecessor("refs")
        receipt = self.receipt(
            predecessor,
            suffix="refs",
            with_memory=True,
            tool_ref_disposition="TOOL_AND_MEMORY_REFS_REFERENCE_ONLY_NO_REPLAY",
        )
        _intent, _session, projection = self.project(predecessor, receipt, suffix="refs")
        payload = projection.as_dict()
        self.assertEqual(payload["canonical_memory_write_credit"], 0)
        self.assertEqual(payload["effect_credit"], 0)
        self.assertEqual(projection.memory_evidence_sha256, memory_evidence_sha256(receipt))
        self.assertNotIn(receipt.memory_evidence[0].memory_id, json.dumps(payload, sort_keys=True))
        self.assertEqual(projection.tool_ref_disposition, receipt.tool_ref_disposition)

    def test_fresh9_packet_successor_executes_with_network_blocked(self) -> None:
        predecessor = self.predecessor("offline")
        receipt = self.receipt(predecessor, suffix="offline")
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("network forbidden")
        ):
            _intent, _session, projection = self.project(predecessor, receipt, suffix="offline")
        self.assertEqual(projection.as_dict()["asr_runtime_credit"], 0)
        self.assertEqual(projection.as_dict()["tts_runtime_credit"], 0)

    def test_fresh10_missing_or_corrupt_prior_or_restart_prerequisite_fails_closed(self) -> None:
        predecessor = self.predecessor("missing")
        receipt = self.receipt(predecessor, suffix="missing")
        fresh_intent, fresh_session = self.fresh_causals(predecessor, "missing")
        common = {
            "predecessor_session": predecessor,
            "fresh_intent_causal_identity": fresh_intent,
            "fresh_session_causal_identity": fresh_session,
            "input_ref": "voice-input:fresh:missing",
            "input_sha256": "7" * 64,
            "expected_gwt_binding_id": receipt.gwt_binding_id,
            "expected_gwt_binding_sha256": receipt.gwt_binding_sha256,
            "expected_memory_evidence_sha256": memory_evidence_sha256(receipt),
        }
        with self.assertRaises(FreshTurnSuccessorError):
            project_fresh_turn(
                predecessor_reentry=None,
                predecessor_reentry_sha256=receipt.sha256(),
                **common,
            )
        with self.assertRaisesRegex(FreshTurnSuccessorError, "digest mismatch"):
            project_fresh_turn(
                predecessor_reentry=receipt,
                predecessor_reentry_sha256="f" * 64,
                **common,
            )

        # The routed FRESH10 contract requires the already-executed F15/F16/F17 restart
        # result to be an explicit prerequisite. A projector that succeeds without any
        # prerequisite binding is a product-negative gap, not an accepted fresh-turn closure.
        with self.assertRaises(FreshTurnSuccessorError):
            project_fresh_turn(
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                **common,
            )


if __name__ == "__main__":
    unittest.main()
