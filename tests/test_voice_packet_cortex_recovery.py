from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    packet_latency_report,
    resume_packet_cortex,
)


class VoicePacketCortexRecoveryTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-t7-recovery",
            agent_id="frankenstein-2",
            task_id="task-t7-recovery",
            turn_id="turn-root",
            causal_id="causal-root-t7-recovery",
            generation=8,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:recovery",
            input_sha256="c" * 64,
            provenance_refs=("trigger7:recovery-fixture",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-t7-recovery", generation=9, turn_id="turn-session"
            ),
            provenance_refs=("trigger7:recovery-session",),
        )

    def final_input(self, cortex: VoicePacketCortex, turn: str, packet: str, at: int, *, faults=()) -> VoiceInputPacket:
        return VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id=turn,
            packet_id=packet,
            monotonic_ms=at,
            source_modality="asr_final",
            text="Weiter bitte",
            language="de-DE",
            is_final=True,
            confidence=0.95,
            speech_start=True,
            speech_end=True,
            vad_state="SPEECH",
            endpoint_decision="END",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=160,
            sequence=0,
            fault_flags=faults,
        )

    def rehash(self, checkpoint: dict) -> dict:
        mutated = deepcopy(checkpoint)
        canonical = json.dumps(
            mutated["payload"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        mutated["payload_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return mutated

    def test_checkpoint_resume_preserves_exact_state_and_adds_reentry_event(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.accept_input(self.final_input(cortex, "turn-1", "input-1", 100))
        cortex.emit_intent(turn_id="turn-1", monotonic_ms=110, voice_intent="ANSWER")
        cortex.queue_output(
            turn_id="turn-1", packet_id="output-1", monotonic_ms=120,
            text_segment="Ja.", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=300, sequence=0,
        )
        cortex.advance_output("output-1", playback_state="started", monotonic_ms=130, heard_fraction=0.0)
        checkpoint = export_packet_cortex_checkpoint(cortex)
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=200)
        self.assertEqual(resumed.session_id, cortex.session_id)
        self.assertEqual(resumed.outputs[0].playback_state, "interrupted")
        self.assertFalse(resumed.outputs[0].commit_eligible)
        self.assertEqual(resumed.outputs[0].interruption_ms, 200)
        self.assertEqual(resumed.events[-1].event_kind, "RESTART_REENTRY")
        self.assertEqual(len(resumed.events), len(cortex.events) + 1)

    def test_restart_does_not_resurrect_active_tool_ownership(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.emit_intent(
            turn_id="turn-tool", monotonic_ms=100, voice_intent="TOOL_USE", tool_ref="tool:pre-restart"
        )
        checkpoint = export_packet_cortex_checkpoint(cortex)
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=200)
        with self.assertRaises(VoicePacketCortexError):
            resumed.emit_system_event(
                turn_id="turn-tool", monotonic_ms=210, event_kind="TOOL_RESULT", tool_ref="tool:pre-restart"
            )

    def test_checkpoint_digest_and_session_binding_fail_closed(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        checkpoint = export_packet_cortex_checkpoint(cortex)
        tampered = deepcopy(checkpoint)
        tampered["payload"]["event_seq"] = 999
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, tampered, monotonic_ms=10)

        other_root = CausalIdentity(
            session_id="other-session", agent_id="frankenstein-2", task_id="other-task",
            turn_id="other-turn", causal_id="other-causal", generation=1,
        )
        other_intent = VoiceIntent.create(
            causal_identity=other_root, input_ref="other:input", input_sha256="d" * 64,
            provenance_refs=("trigger7:other",),
        )
        other_session = VoiceSessionCapsule.create(
            intent=other_intent,
            session_causal_identity=other_root.derive(causal_id="other-session-causal", generation=2, turn_id="other-session-turn"),
            provenance_refs=("trigger7:other-session",),
        )
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(other_session, checkpoint, monotonic_ms=10)

    def test_rejected_event_is_atomic_and_checkpoint_remains_restartable(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        before_seq = cortex._event_seq
        before_events = cortex.events
        before_checkpoint = export_packet_cortex_checkpoint(cortex)

        with self.assertRaises(VoicePacketCortexError):
            cortex.emit_system_event(
                turn_id="turn-reject", monotonic_ms=10, event_kind="ERROR", detail=1  # type: ignore[arg-type]
            )

        self.assertEqual(cortex._event_seq, before_seq)
        self.assertEqual(cortex.events, before_events)
        after_checkpoint = export_packet_cortex_checkpoint(cortex)
        self.assertEqual(after_checkpoint, before_checkpoint)
        resumed = resume_packet_cortex(session, after_checkpoint, monotonic_ms=20)
        self.assertEqual(resumed.events[-1].event_kind, "RESTART_REENTRY")

    def test_closed_checkpoint_revalidates_session_close_packet_refs(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        outcome_causal_identity = session.session_causal_identity.derive(
            causal_id="causal-outcome-f18-recovery", generation=10, turn_id="turn-close"
        )
        cortex.close_session(
            turn_id="turn-close",
            monotonic_ms=200,
            outcome_causal_identity=outcome_causal_identity,
            outcome_kind="ENDED",
            provenance_refs=("trigger7:t7-arch-003:f18-close",),
        )
        checkpoint = export_packet_cortex_checkpoint(cortex)
        control = resume_packet_cortex(session, checkpoint, monotonic_ms=250)
        self.assertFalse(control.is_open)

        tampered = deepcopy(checkpoint)
        close_events = [
            event for event in tampered["payload"]["events"] if event["event_kind"] == "SESSION_CLOSE"
        ]
        self.assertEqual(len(close_events), 1)
        self.assertEqual(close_events[0]["packet_refs"], [])
        close_events[0]["packet_refs"] = ["output-forged-not-restored"]
        canonical = json.dumps(
            tampered["payload"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        tampered["payload_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, tampered, monotonic_ms=250)

    def test_event_derived_latency_accounting_is_explicit(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.accept_input(self.final_input(cortex, "turn-latency", "input-latency", 100))
        cortex.emit_intent(turn_id="turn-latency", monotonic_ms=115, voice_intent="ANSWER")
        cortex.queue_output(
            turn_id="turn-latency", packet_id="output-latency", monotonic_ms=125,
            text_segment="Antwort", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=400, sequence=0,
        )
        cortex.advance_output("output-latency", playback_state="started", monotonic_ms=140, heard_fraction=0.0)
        report = packet_latency_report(cortex, "turn-latency")
        self.assertEqual(report["asr_from_speech_start_ms"], 0)
        self.assertEqual(report["decision_after_asr_ms"], 15)
        self.assertEqual(report["first_output_after_decision_ms"], 10)
        self.assertEqual(report["playback_after_first_output_ms"], 15)
        self.assertEqual(report["speech_to_playback_ms"], 40)

    def test_long_conversation_keeps_turn_sequences_independent(self) -> None:
        cortex = VoicePacketCortex(self.session())
        for index in range(100):
            turn = f"turn-{index:03d}"
            packet = f"input-{index:03d}"
            event = cortex.accept_input(self.final_input(cortex, turn, packet, 1000 + index * 10))
            self.assertIn("ASR_FINAL", event.event_kind)
            cortex.emit_intent(turn_id=turn, monotonic_ms=1001 + index * 10, voice_intent="WAIT")
        self.assertEqual(len(cortex._last_input_sequence), 100)

    def test_transient_state_has_explicit_fail_closed_capacity(self) -> None:
        limits = {
            "MAX_EVENTS": getattr(VoicePacketCortex, "MAX_EVENTS", None),
            "MAX_INPUT_PACKETS": getattr(VoicePacketCortex, "MAX_INPUT_PACKETS", None),
            "MAX_OUTPUT_PACKETS": getattr(VoicePacketCortex, "MAX_OUTPUT_PACKETS", None),
            "MAX_TOOL_REFS": getattr(VoicePacketCortex, "MAX_TOOL_REFS", None),
        }
        for name, value in limits.items():
            self.assertIs(type(value), int, name)
            self.assertGreater(value, 0, name)

        cortex = VoicePacketCortex(self.session())
        for index in range(VoicePacketCortex.MAX_EVENTS - 1):
            cortex.emit_intent(
                turn_id="turn-capacity", monotonic_ms=index + 1, voice_intent="WAIT",
                detail=f"capacity-probe-{index}",
            )
        self.assertEqual(len(cortex.events), VoicePacketCortex.MAX_EVENTS)
        with self.assertRaises(VoicePacketCortexError):
            cortex.emit_intent(
                turn_id="turn-capacity", monotonic_ms=VoicePacketCortex.MAX_EVENTS + 1,
                voice_intent="WAIT", detail="must-fail-closed",
            )
        self.assertEqual(len(cortex.events), VoicePacketCortex.MAX_EVENTS)

    def test_transport_fault_is_preserved_and_retry_uses_new_causal_packet_id(self) -> None:
        cortex = VoicePacketCortex(self.session())
        dropped = self.final_input(cortex, "turn-fault", "input-fault-drop", 100, faults=("drop",))
        self.assertEqual(cortex.accept_input(dropped).event_kind, "INPUT_DROP_INJECTED")
        retry = self.final_input(cortex, "turn-fault", "input-fault-retry", 110)
        self.assertIn("ASR_FINAL", cortex.accept_input(retry).event_kind)
        transport = cortex.emit_system_event(
            turn_id="turn-fault", monotonic_ms=120, event_kind="TRANSPORT_FAILURE",
            packet_refs=("input-fault-drop",), detail="injected drop; retry admitted as new packet identity",
        )
        recovery = cortex.emit_system_event(
            turn_id="turn-fault", monotonic_ms=130, event_kind="RECOVERY",
            packet_refs=("input-fault-retry",), detail="replacement packet accepted",
        )
        self.assertEqual((transport.event_kind, recovery.event_kind), ("TRANSPORT_FAILURE", "RECOVERY"))

    def test_rbound1_imported_input_seen_over_cap_fails_closed(self) -> None:
        session = self.session()
        checkpoint = export_packet_cortex_checkpoint(VoicePacketCortex(session))
        checkpoint["payload"]["input_seen"] = [
            [f"input-{index}", f"{index:064x}"[-64:]]
            for index in range(VoicePacketCortex.MAX_INPUT_PACKETS + 1)
        ]
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=1000)

    def test_rbound2_imported_outputs_over_cap_fail_closed(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-template", packet_id="output-template", monotonic_ms=10,
            text_segment="x", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=1, sequence=0,
        )
        checkpoint = export_packet_cortex_checkpoint(cortex)
        template = checkpoint["payload"]["outputs"][0]
        outputs = []
        for index in range(VoicePacketCortex.MAX_OUTPUT_PACKETS + 1):
            raw = deepcopy(template)
            raw["packet_id"] = f"output-{index}"
            raw["turn_id"] = f"turn-{index}"
            raw["sequence"] = 0
            outputs.append(raw)
        checkpoint["payload"]["outputs"] = outputs
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=1000)

    def test_rbound3_imported_tool_refs_over_cap_fail_closed(self) -> None:
        session = self.session()
        checkpoint = export_packet_cortex_checkpoint(VoicePacketCortex(session))
        checkpoint["payload"]["active_tools"] = [
            [f"tool:{index}", f"turn-{index}"]
            for index in range(VoicePacketCortex.MAX_TOOL_REFS + 1)
        ]
        checkpoint["payload"]["cancelled_tools"] = []
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=1000)

    def test_rbound4_imported_events_over_cap_remain_fail_closed(self) -> None:
        session = self.session()
        checkpoint = export_packet_cortex_checkpoint(VoicePacketCortex(session))
        template = checkpoint["payload"]["events"][0]
        events = []
        for index in range(VoicePacketCortex.MAX_EVENTS + 1):
            raw = deepcopy(template)
            raw["event_id"] = f"event-{index}"
            raw["monotonic_ms"] = index
            events.append(raw)
        checkpoint["payload"]["events"] = events
        checkpoint["payload"]["event_seq"] = VoicePacketCortex.MAX_EVENTS + 1
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=1000)

    def test_rbound5_unbacked_input_sequence_projection_fails_closed(self) -> None:
        session = self.session()
        checkpoint = export_packet_cortex_checkpoint(VoicePacketCortex(session))
        checkpoint["payload"]["last_input_sequence"] = [["turn-ghost", 999]]
        checkpoint["payload"]["last_input_monotonic_ms"] = [["turn-ghost", 900]]
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=1000)

    def test_rbound6_unbacked_output_sequence_projection_fails_closed(self) -> None:
        session = self.session()
        checkpoint = export_packet_cortex_checkpoint(VoicePacketCortex(session))
        checkpoint["payload"]["last_output_sequence"] = [["turn-ghost", 999]]
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=1000)

    def test_rcomp1_completed_heard_commit_projection_fails_closed(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-output", packet_id="output-0", monotonic_ms=100,
            text_segment="vollstaendig gehoert", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=200, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
        cortex.advance_output("output-0", playback_state="completed", monotonic_ms=310, heard_fraction=1.0)
        checkpoint = export_packet_cortex_checkpoint(cortex)
        checkpoint["payload"]["outputs"][0]["commit_eligible"] = False
        with self.assertRaisesRegex(VoicePacketCortexError, "commit eligibility contradicts"):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=400)

    def test_rcomp2_tool_history_projection_drop_fails_closed(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.emit_intent(
            turn_id="turn-tool-a", monotonic_ms=100, voice_intent="TOOL_USE", tool_ref="tool:shared"
        )
        checkpoint = export_packet_cortex_checkpoint(cortex)
        checkpoint["payload"]["active_tools"] = []
        checkpoint["payload"]["cancelled_tools"] = []
        with self.assertRaisesRegex(VoicePacketCortexError, "tool ownership projection is not backed"):
            resume_packet_cortex(session, self.rehash(checkpoint), monotonic_ms=200)


if __name__ == "__main__":
    unittest.main()