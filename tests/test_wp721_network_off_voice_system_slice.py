from __future__ import annotations

import hashlib
import json
import unittest
from unittest import mock

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.fresh_turn_successor import memory_evidence_sha256, project_fresh_turn
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    REENTRY_RECEIPT_SCHEMA,
    VoiceHeardResultReentryReceipt,
)
from frankenstein2.voice_packet_cortex import PacketTurnPolicy, VoiceInputPacket, VoicePacketCortex
from frankenstein2.voice_packet_cortex_recovery import export_packet_cortex_checkpoint, resume_packet_cortex


_REENTRY_CLASSIFICATION = VoiceHeardResultReentryReceipt.__dataclass_fields__["classification"].default
_RESTART_REF = "runtime:trigger4/wp715-g3/33534630240"
_RESTART_SHA256 = "8" * 64


def _digest(value) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class WP721NetworkOffExistingPartsVoiceSystemSlice(unittest.TestCase):
    def predecessor(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp721-predecessor",
            agent_id="frankenstein-2",
            task_id="task-wp721-existing-parts-slice",
            turn_id="turn-wp721-predecessor-input",
            causal_id="causal-wp721-predecessor-input",
            generation=10,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="fixture:wp721:predecessor",
            input_sha256="1" * 64,
            provenance_refs=("trigger4:F2-WP-721:predecessor",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-wp721-predecessor-session",
                generation=11,
                turn_id="turn-wp721-predecessor-session",
            ),
            provenance_refs=("trigger4:F2-WP-721:predecessor-session",),
        )

    def predecessor_reentry(self, predecessor: VoiceSessionCapsule) -> VoiceHeardResultReentryReceipt:
        provenance = ("trigger4:F2-WP-721:accepted-reentry-reference",)
        payload = {
            "schema": REENTRY_RECEIPT_SCHEMA,
            "heard_result_ref": "voice-heard-result:wp721-predecessor",
            "heard_result_sha256": "2" * 64,
            "voiceoutcome_id": "voice-outcome:wp721-predecessor",
            "voiceoutcome_sha256": "3" * 64,
            "voice_session_id": predecessor.voice_session_id,
            "voice_session_sha256": predecessor.sha256(),
            "close_event_id": "voice-close:wp721-predecessor",
            "ordered_output_packet_ids": ["output-wp721-predecessor"],
            "context_view_sha256": None,
            "context_item_id": None,
            "context_cost_witness_sha256": None,
            "memory_evidence": [],
            "gwt_binding_id": None,
            "gwt_binding_sha256": None,
            "tool_ref_disposition": "REFERENCE_ONLY_NO_TOOL_OR_EFFECT_REPLAY",
            "provenance_refs": list(provenance),
            "classification": _REENTRY_CLASSIFICATION,
            "canonical_memory_write_credit": 0,
            "gwt_runtime_credit": 0,
            "effect_credit": 0,
            "physical_audio_credit": 0,
            "whole_system_acceptance": False,
        }
        return VoiceHeardResultReentryReceipt(
            receipt_id="voice-reentry-receipt:" + _digest(payload),
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
            memory_evidence=(),
            gwt_binding_id=None,
            gwt_binding_sha256=None,
            tool_ref_disposition=payload["tool_ref_disposition"],
            provenance_refs=provenance,
        )

    @staticmethod
    def input_packet(
        cortex: VoicePacketCortex,
        *,
        turn_id: str,
        packet_id: str,
        monotonic_ms: int,
        sequence: int,
        final: bool,
    ) -> VoiceInputPacket:
        return VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id=turn_id,
            packet_id=packet_id,
            monotonic_ms=monotonic_ms,
            source_modality="asr_final" if final else "asr_partial",
            text="Jetzt bin ich fertig" if final else "Ich spreche noch",
            language="de-DE",
            is_final=final,
            confidence=0.99,
            speech_start=not final,
            speech_end=final,
            vad_state="SPEECH",
            endpoint_decision="END" if final else "HOLD",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=320 if final else 160,
            sequence=sequence,
        )

    def test_wp719_to_wp720_to_wp715_slice_survives_restart_without_network(self) -> None:
        predecessor = self.predecessor()
        reentry = self.predecessor_reentry(predecessor)
        fresh_intent_causal = predecessor.session_causal_identity.derive(
            causal_id="causal-wp721-fresh-intent",
            generation=12,
            turn_id="turn-wp721-fresh",
        )
        fresh_session_causal = fresh_intent_causal.derive(
            causal_id="causal-wp721-fresh-session",
            generation=13,
            turn_id="turn-wp721-fresh-session",
        )

        with (
            mock.patch("socket.socket", side_effect=AssertionError("WP721 discriminator must remain network-off")),
            mock.patch("socket.create_connection", side_effect=AssertionError("WP721 discriminator must remain network-off")),
        ):
            fresh_intent, fresh_session, projection = project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=reentry,
                predecessor_reentry_sha256=reentry.sha256(),
                fresh_intent_causal_identity=fresh_intent_causal,
                fresh_session_causal_identity=fresh_session_causal,
                input_ref="voice-input:wp721:fresh",
                input_sha256="4" * 64,
                expected_gwt_binding_id=None,
                expected_gwt_binding_sha256=None,
                expected_memory_evidence_sha256=memory_evidence_sha256(reentry),
                prerequisite_restart_receipt_ref=_RESTART_REF,
                prerequisite_restart_receipt_sha256=_RESTART_SHA256,
                provenance_refs=("trigger4:F2-WP-721:system-slice",),
            )

            self.assertEqual(projection.fresh_intent_id, fresh_intent.intent_id)
            self.assertEqual(projection.fresh_conversation_id, fresh_session.voice_session_id)
            self.assertNotEqual(fresh_session.voice_session_id, predecessor.voice_session_id)
            self.assertEqual(projection.as_dict()["gwt_runtime_credit"], 0)
            self.assertEqual(projection.as_dict()["effect_credit"], 0)
            self.assertFalse(projection.as_dict()["whole_system_acceptance"])

            cortex = VoicePacketCortex(fresh_session)
            turn_id = projection.fresh_turn_id
            hold = self.input_packet(
                cortex,
                turn_id=turn_id,
                packet_id="wp721-input-hold-0",
                monotonic_ms=100,
                sequence=0,
                final=False,
            )
            cortex.accept_input(hold)
            policy = PacketTurnPolicy(
                policy_id="wp721-existing-authoritative-policy",
                hold_intent="WAIT",
                provenance_refs=("trigger4:F2-WP-721:reuse-WP720-policy",),
            )
            decision = cortex.apply_turn_policy(hold, policy)
            replay = cortex.apply_turn_policy(hold, policy)
            self.assertEqual(replay, decision)

            final = self.input_packet(
                cortex,
                turn_id=turn_id,
                packet_id="wp721-input-final-1",
                monotonic_ms=120,
                sequence=1,
                final=True,
            )
            cortex.accept_input(final)
            cortex.emit_intent(turn_id=turn_id, monotonic_ms=130, voice_intent="ANSWER")
            cortex.queue_output(
                turn_id=turn_id,
                packet_id="wp721-output-answer-0",
                monotonic_ms=140,
                text_segment="Ja.",
                expression_intent="neutral",
                speech_act="ANSWER",
                planned_audio_duration_ms=300,
                sequence=0,
            )
            cortex.advance_output(
                "wp721-output-answer-0",
                playback_state="started",
                monotonic_ms=150,
                heard_fraction=0.0,
            )

            checkpoint = export_packet_cortex_checkpoint(cortex)
            resumed = resume_packet_cortex(fresh_session, checkpoint, monotonic_ms=200)

        policy_events = [
            event
            for event in resumed.events
            if event.event_kind == "TURN_POLICY_DECISION"
            and event.packet_refs == (hold.packet_id,)
        ]
        self.assertEqual(len(policy_events), 1)
        self.assertEqual(policy_events[0].voice_intent, "WAIT")
        self.assertEqual(resumed.events[-1].event_kind, "RESTART_REENTRY")
        self.assertEqual(resumed.outputs[0].packet_id, "wp721-output-answer-0")
        self.assertEqual(resumed.outputs[0].playback_state, "interrupted")
        self.assertFalse(resumed.outputs[0].commit_eligible)
        self.assertEqual(resumed.outputs[0].interruption_ms, 200)


if __name__ == "__main__":
    unittest.main()
