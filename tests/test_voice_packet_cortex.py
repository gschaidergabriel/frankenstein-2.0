from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import (
    PacketTurnPolicy,
    VoiceInputPacket,
    VoicePacketCortex,
    VoicePacketCortexError,
)
from frankenstein2.voice_packet_cortex_recovery import export_packet_cortex_checkpoint, resume_packet_cortex


class VoicePacketCortexTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-t7-packet",
            agent_id="frankenstein-2",
            task_id="task-t7-packet",
            turn_id="turn-input",
            causal_id="causal-input-t7-packet",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:de-turn",
            input_sha256="a" * 64,
            provenance_refs=("trigger7:packet-fixture",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-t7-packet", generation=4, turn_id="turn-session"
            ),
            provenance_refs=("trigger7:packet-session",),
        )

    def input_packet(self, cortex: VoicePacketCortex, **overrides) -> VoiceInputPacket:
        values = dict(
            session_id=cortex.session_id,
            turn_id="turn-1",
            packet_id="input-0",
            monotonic_ms=100,
            source_modality="asr_partial",
            text="Guten",
            language="de-DE",
            is_final=False,
            confidence=0.91,
            speech_start=True,
            speech_end=False,
            vad_state="SPEECH",
            endpoint_decision="HOLD",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=160,
            sequence=0,
        )
        values.update(overrides)
        return VoiceInputPacket(**values)

    def test_partial_then_final_preserves_turn_order_and_endpoint(self) -> None:
        cortex = VoicePacketCortex(self.session())
        partial = self.input_packet(cortex)
        final = self.input_packet(
            cortex,
            packet_id="input-1",
            monotonic_ms=260,
            source_modality="asr_final",
            text="Guten Morgen",
            is_final=True,
            confidence=0.96,
            speech_start=False,
            speech_end=True,
            endpoint_decision="END",
            sequence=1,
        )
        self.assertEqual(cortex.accept_input(partial).event_kind, "SPEECH_START_ASR_PARTIAL")
        self.assertEqual(cortex.accept_input(final).event_kind, "ASR_FINAL_SPEECH_END")
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(self.input_packet(cortex, packet_id="input-2", sequence=2))

    def test_barge_in_interrupts_started_output_and_revokes_commit(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=10,
            text_segment="Ich erkläre das gerade.", expression_intent="neutral",
            speech_act="ANSWER", planned_audio_duration_ms=1200, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-0", playback_state="heard", monotonic_ms=200, heard_fraction=0.2)
        event = cortex.accept_input(
            self.input_packet(cortex, monotonic_ms=201, barge_in=True, overlap_state="USER_OVER_OUTPUT")
        )
        self.assertEqual(event.event_kind, "SPEECH_START_ASR_PARTIAL")
        output = cortex.outputs[0]
        self.assertEqual(output.playback_state, "interrupted")
        self.assertEqual(output.heard_fraction, 0.2)
        self.assertFalse(output.commit_eligible)
        self.assertIn("BARGE_IN_CANCEL_PROPAGATED", [item.event_kind for item in cortex.events])

    def test_unheard_queued_output_is_cancelled_not_committed(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-queued", monotonic_ms=10,
            text_segment="Noch nicht abgespielt", expression_intent="neutral",
            speech_act="ANSWER", planned_audio_duration_ms=800, sequence=0,
        )
        self.assertEqual(cortex.cancel_for_barge_in(turn_id="turn-1", monotonic_ms=11), ("output-queued",))
        output = cortex.outputs[0]
        self.assertEqual(output.playback_state, "cancelled")
        self.assertEqual(output.heard_fraction, 0.0)
        self.assertFalse(output.commit_eligible)

    def test_completed_output_is_only_full_segment_commit_path(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=10,
            text_segment="Fertig.", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=300, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=15, heard_fraction=0.0)
        completed = cortex.advance_output("output-0", playback_state="completed", monotonic_ms=315, heard_fraction=1.0)
        self.assertTrue(completed.commit_eligible)
        with self.assertRaises(VoicePacketCortexError):
            cortex.advance_output("output-0", playback_state="heard", monotonic_ms=320, heard_fraction=1.0)

    def test_duplicate_is_idempotent_but_same_id_changed_content_fails(self) -> None:
        cortex = VoicePacketCortex(self.session())
        packet = self.input_packet(cortex)
        cortex.accept_input(packet)
        self.assertEqual(cortex.accept_input(packet).event_kind, "INPUT_DUPLICATE_IGNORED")
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(replace(packet, text="verändert"))

    def test_drop_reorder_and_corruption_faults_are_explicit(self) -> None:
        cortex = VoicePacketCortex(self.session())
        dropped = self.input_packet(cortex, packet_id="drop-0", fault_flags=("drop",))
        self.assertEqual(cortex.accept_input(dropped).event_kind, "INPUT_DROP_INJECTED")
        reordered = self.input_packet(cortex, packet_id="reorder-2", sequence=2, fault_flags=("reorder",))
        self.assertEqual(cortex.accept_input(reordered).event_kind, "INPUT_REORDER_REJECTED")
        corrupt = self.input_packet(cortex, packet_id="corrupt-0", fault_flags=("corrupt",))
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(corrupt)

    def test_input_monotonic_timestamp_cannot_regress_with_advancing_sequence(self) -> None:
        cortex = VoicePacketCortex(self.session(), opened_monotonic_ms=50)
        cortex.accept_input(self.input_packet(cortex, monotonic_ms=100, sequence=0))
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(self.input_packet(
                cortex,
                packet_id="input-1",
                monotonic_ms=99,
                speech_start=False,
                sequence=1,
            ))

    def test_output_playback_timestamp_cannot_regress_across_state_transition(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-clock", monotonic_ms=100,
            text_segment="Zeitfolge", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=200, sequence=0,
        )
        cortex.advance_output("output-clock", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
        with self.assertRaises(VoicePacketCortexError):
            cortex.advance_output("output-clock", playback_state="heard", monotonic_ms=109, heard_fraction=0.1)

    def test_barge_in_timestamp_cannot_precede_output_state_it_cancels(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-cancel-clock", monotonic_ms=100,
            text_segment="Unterbrechbar", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=200, sequence=0,
        )
        cortex.advance_output("output-cancel-clock", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
        with self.assertRaises(VoicePacketCortexError):
            cortex.cancel_for_barge_in(turn_id="turn-1", monotonic_ms=109)

    def test_duplicate_output_sequence_same_turn_fails_closed(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-z", monotonic_ms=100,
            text_segment="A", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=100, sequence=0,
        )
        with self.assertRaises(VoicePacketCortexError):
            cortex.queue_output(
                turn_id="turn-0", packet_id="output-a", monotonic_ms=101,
                text_segment="B", expression_intent="neutral", speech_act="ANSWER",
                planned_audio_duration_ms=100, sequence=0,
            )

    def test_output_chunks_are_exposed_in_declared_sequence_order(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-z", monotonic_ms=100,
            text_segment="A", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=100, sequence=0,
        )
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-a", monotonic_ms=101,
            text_segment="B", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=100, sequence=1,
        )
        self.assertEqual([packet.sequence for packet in cortex.outputs], [0, 1])

    def test_output_sequence_gap_is_rejected_explicitly(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=100,
            text_segment="A", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=100, sequence=0,
        )
        with self.assertRaises(VoicePacketCortexError):
            cortex.queue_output(
                turn_id="turn-0", packet_id="output-2", monotonic_ms=102,
                text_segment="C", expression_intent="neutral", speech_act="ANSWER",
                planned_audio_duration_ms=100, sequence=2,
            )

    def test_wait_backchannel_tool_gwt_and_memory_refs_share_one_event_fabric(self) -> None:
        cortex = VoicePacketCortex(self.session())
        wait = cortex.emit_intent(
            turn_id="turn-1", monotonic_ms=100, voice_intent="WAIT",
            gwt_ref="gwt:broadcast-1", memory_refs=("memory:fact-1",), detail="user still speaking",
        )
        backchannel = cortex.emit_intent(
            turn_id="turn-1", monotonic_ms=120, voice_intent="BACKCHANNEL", detail="mhm",
        )
        tool = cortex.emit_intent(
            turn_id="turn-1", monotonic_ms=140, voice_intent="TOOL_USE",
            tool_ref="tool:status-read", memory_refs=("memory:fact-1",),
        )
        self.assertEqual((wait.voice_intent, backchannel.voice_intent, tool.voice_intent),
                         ("WAIT", "BACKCHANNEL", "TOOL_USE"))
        self.assertEqual(tool.tool_ref, "tool:status-read")

    def test_cancelled_turn_rejects_late_tool_result(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-tool", monotonic_ms=100,
            text_segment="Ich prüfe das.", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=500, sequence=0,
        )
        cortex.advance_output("output-tool", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
        cortex.emit_intent(
            turn_id="turn-0", monotonic_ms=115, voice_intent="TOOL_USE", tool_ref="tool:late"
        )
        cortex.cancel_for_barge_in(turn_id="turn-1", monotonic_ms=120)
        with self.assertRaises(VoicePacketCortexError):
            cortex.emit_system_event(
                turn_id="turn-0", monotonic_ms=130, event_kind="TOOL_RESULT", tool_ref="tool:late"
            )

    def test_cancelled_unheard_output_cannot_mint_result_reference(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-cancelled", monotonic_ms=10,
            text_segment="Nicht gehört", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=500, sequence=0,
        )
        cortex.cancel_for_barge_in(turn_id="turn-1", monotonic_ms=20)
        with self.assertRaises(VoicePacketCortexError):
            cortex.close_session(
                turn_id="turn-close", monotonic_ms=30,
                outcome_causal_identity=session.session_causal_identity.derive(
                    causal_id="causal-outcome-cancelled", generation=5, turn_id="turn-outcome-cancelled"
                ),
                outcome_kind=OUTCOME_RETURNED,
                result_ref="voice-result:unheard",
                result_sha256="c" * 64,
            )

    def test_duplicate_close_same_identity_is_idempotent(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-close", monotonic_ms=10,
            text_segment="Fertig", expression_intent="neutral", speech_act="CLOSE",
            planned_audio_duration_ms=100, sequence=0,
        )
        cortex.advance_output("output-close", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-close", playback_state="completed", monotonic_ms=120, heard_fraction=1.0)
        identity = session.session_causal_identity.derive(
            causal_id="causal-outcome-idempotent", generation=5, turn_id="turn-outcome-idempotent"
        )
        first = cortex.close_session(
            turn_id="turn-close", monotonic_ms=130,
            outcome_causal_identity=identity, outcome_kind=OUTCOME_RETURNED,
            result_ref="voice-result:idempotent", result_sha256="d" * 64,
        )
        second = cortex.close_session(
            turn_id="turn-close", monotonic_ms=130,
            outcome_causal_identity=identity, outcome_kind=OUTCOME_RETURNED,
            result_ref="voice-result:idempotent", result_sha256="d" * 64,
        )
        self.assertEqual(second, first)

    def test_close_binds_existing_voice_outcome_contract(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=10,
            text_segment="Bis gleich.", expression_intent="warm", speech_act="CLOSE",
            planned_audio_duration_ms=500, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-0", playback_state="completed", monotonic_ms=520, heard_fraction=1.0)
        outcome = cortex.close_session(
            turn_id="turn-close", monotonic_ms=530,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-t7-packet", generation=5, turn_id="turn-outcome"
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref="voice-result:t7-packet",
            result_sha256="b" * 64,
        )
        self.assertEqual(outcome.voice_session_id, session.voice_session_id)
        self.assertFalse(cortex.is_open)
        self.assertEqual(cortex.events[-1].event_kind, "SESSION_CLOSE")

    def test_close_refuses_nonterminal_output(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-open", monotonic_ms=10,
            text_segment="läuft", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=900, sequence=0,
        )
        with self.assertRaises(VoicePacketCortexError):
            cortex.close_session(
                turn_id="turn-close", monotonic_ms=20,
                outcome_causal_identity=session.session_causal_identity.derive(
                    causal_id="causal-outcome-open", generation=5, turn_id="turn-outcome"
                ),
                outcome_kind=OUTCOME_RETURNED,
            )

    def test_session_close_cannot_silently_erase_active_tool_ownership(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        tool_ref = "tool:session-close-owned"
        cortex.emit_intent(
            turn_id="turn-tool", monotonic_ms=100, voice_intent="TOOL_USE", tool_ref=tool_ref
        )
        event_kinds_before = [event.event_kind for event in cortex.events]
        try:
            cortex.close_session(
                turn_id="turn-close", monotonic_ms=110,
                outcome_causal_identity=session.session_causal_identity.derive(
                    causal_id="causal-outcome-active-tool", generation=5, turn_id="turn-outcome-active-tool"
                ),
                outcome_kind=OUTCOME_RETURNED,
            )
        except VoicePacketCortexError:
            self.assertTrue(cortex.is_open)
            self.assertEqual(cortex._active_tools.get(tool_ref), "turn-tool")
            self.assertEqual([event.event_kind for event in cortex.events], event_kinds_before)
            return
        self.assertIn(
            tool_ref,
            cortex._cancelled_tools,
            "successful SESSION_CLOSE must preserve an explicit stale/cancelled tool tombstone",
        )
        self.assertTrue(
            any(event.event_kind in ("CANCELLATION", "TOOL_CANCELLED", "TOOL_FENCED") and event.tool_ref == tool_ref
                for event in cortex.events),
            "successful SESSION_CLOSE must emit an explicit causal tool terminalization event",
        )

    def test_rejected_session_close_is_checkpoint_atomic(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-atomic-close", monotonic_ms=10,
            text_segment="Atomar schließen.", expression_intent="neutral", speech_act="CLOSE",
            planned_audio_duration_ms=100, sequence=0,
        )
        cortex.advance_output("output-atomic-close", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-atomic-close", playback_state="completed", monotonic_ms=120, heard_fraction=1.0)
        before = export_packet_cortex_checkpoint(cortex)
        with self.assertRaises(VoicePacketCortexError):
            cortex.close_session(
                turn_id="", monotonic_ms=130,
                outcome_causal_identity=session.session_causal_identity.derive(
                    causal_id="causal-outcome-rejected-close", generation=5, turn_id="turn-outcome-rejected-close"
                ),
                outcome_kind=OUTCOME_RETURNED,
                result_ref="voice-result:rejected-close",
                result_sha256="e" * 64,
            )
        after = export_packet_cortex_checkpoint(cortex)
        self.assertEqual(
            after,
            before,
            "rejected SESSION_CLOSE must not mutate durable/recoverable packet-cortex state",
        )

    def test_pfd0_pfd5_matched_history_policy_only_intervention_is_deterministic(self) -> None:
        session = self.session()

        def trajectory_sha(cortex: VoicePacketCortex) -> str:
            raw = json.dumps(
                [event.as_dict() for event in cortex.events],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()

        def run(hold_intent: str):
            cortex = VoicePacketCortex(session)
            packet = self.input_packet(cortex)
            cortex.accept_input(packet)
            pre_events = [event.as_dict() for event in cortex.events]
            pre_sha = trajectory_sha(cortex)
            policy = PacketTurnPolicy(
                policy_id="packet-policy:pfd-hold-response",
                hold_intent=hold_intent,
                provenance_refs=("trigger7:pfd-matched-history-fixture",),
            )
            decision = cortex.apply_turn_policy(packet, policy)
            return cortex, packet, policy, decision, pre_events, pre_sha, trajectory_sha(cortex)

        wait_a = run("WAIT")
        backchannel = run("BACKCHANNEL")
        wait_b = run("WAIT")

        self.assertEqual(wait_a[4], backchannel[4], "PFD1: pre-intervention event history must match")
        self.assertEqual(wait_a[5], backchannel[5], "PFD1: pre-intervention history hash must match")
        self.assertEqual(wait_a[1].sha256(), backchannel[1].sha256(), "PFD3: exact input packet must match")
        self.assertEqual(wait_a[2].policy_id, backchannel[2].policy_id)
        self.assertEqual(wait_a[2].provenance_refs, backchannel[2].provenance_refs)
        self.assertNotEqual(wait_a[2].hold_intent, backchannel[2].hold_intent, "PFD2: vary one policy dimension")
        self.assertEqual(wait_a[3].event_kind, "TURN_POLICY_DECISION")
        self.assertEqual(backchannel[3].event_kind, "TURN_POLICY_DECISION")
        self.assertEqual(wait_a[3].voice_intent, "WAIT")
        self.assertEqual(backchannel[3].voice_intent, "BACKCHANNEL")

        wait_events = [event.as_dict() for event in wait_a[0].events]
        back_events = [event.as_dict() for event in backchannel[0].events]
        first_divergence = next(
            index for index, (left, right) in enumerate(zip(wait_events, back_events)) if left != right
        )
        self.assertEqual(first_divergence, len(wait_a[4]), "PFD4: first divergence must be policy decision")
        self.assertNotEqual(wait_a[6], backchannel[6], "PFD4: policy must change trajectory hash")
        self.assertEqual(wait_a[6], wait_b[6], "PFD5: repeated same-policy control must be stable")

        detail = json.loads(wait_a[3].detail)
        self.assertEqual(detail["input_packet_sha256"], wait_a[1].sha256())
        self.assertEqual(detail["policy_sha256"], wait_a[2].sha256())
        self.assertEqual(detail["policy_id"], wait_a[2].policy_id)
        self.assertEqual(detail["policy_provenance_refs"], list(wait_a[2].provenance_refs))

    def test_turn_policy_requires_exact_current_accepted_hold_and_conflicting_rebind_fails(self) -> None:
        cortex = VoicePacketCortex(self.session())
        packet = self.input_packet(cortex)
        wait = PacketTurnPolicy(
            policy_id="packet-policy:pfd-hold-response",
            hold_intent="WAIT",
            provenance_refs=("trigger7:pfd-matched-history-fixture",),
        )
        backchannel = replace(wait, hold_intent="BACKCHANNEL")
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(packet, wait)
        cortex.accept_input(packet)
        first = cortex.apply_turn_policy(packet, wait)
        self.assertIs(cortex.apply_turn_policy(packet, wait), first)
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(packet, backchannel)

        newer = self.input_packet(
            cortex,
            packet_id="input-1",
            monotonic_ms=120,
            speech_start=False,
            sequence=1,
        )
        cortex.accept_input(newer)
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(packet, wait)

    def test_turn_policy_cannot_override_mandatory_barge_in_cancellation(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-policy-barge", monotonic_ms=10,
            text_segment="Unterbrechbar", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=1000, sequence=0,
        )
        cortex.advance_output("output-policy-barge", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        packet = self.input_packet(
            cortex,
            monotonic_ms=30,
            barge_in=True,
            overlap_state="USER_OVER_OUTPUT",
        )
        cortex.accept_input(packet)
        self.assertEqual(cortex.outputs[0].playback_state, "interrupted")
        policy = PacketTurnPolicy(
            policy_id="packet-policy:malicious-barge-override",
            hold_intent="BACKCHANNEL",
            provenance_refs=("trigger4:wp720-barge-in-fence",),
        )
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(packet, policy)
        self.assertEqual(cortex.outputs[0].playback_state, "interrupted")
        self.assertIn("BARGE_IN_CANCEL_PROPAGATED", [event.event_kind for event in cortex.events])

    def test_turn_policy_binding_survives_checkpoint_reentry_without_second_authority(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        packet = self.input_packet(cortex)
        cortex.accept_input(packet)
        wait = PacketTurnPolicy(
            policy_id="packet-policy:pfd-reentry",
            hold_intent="WAIT",
            provenance_refs=("trigger4:wp720-reentry",),
        )
        decision = cortex.apply_turn_policy(packet, wait)
        checkpoint = export_packet_cortex_checkpoint(cortex)
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=200)
        replay = resumed.apply_turn_policy(packet, wait)
        self.assertEqual(replay.event_id, decision.event_id)
        self.assertEqual(replay.detail, decision.detail)
        with self.assertRaises(VoicePacketCortexError):
            resumed.apply_turn_policy(packet, replace(wait, hold_intent="BACKCHANNEL"))


if __name__ == "__main__":
    unittest.main()