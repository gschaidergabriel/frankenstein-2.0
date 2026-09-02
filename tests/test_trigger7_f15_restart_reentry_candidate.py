from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import bind_completed_reentry, build_heard_result
from frankenstein2.voice_packet_cortex import VoicePacketCortex
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    resume_packet_cortex,
)


class Trigger7F15RestartReentryCandidateTests(unittest.TestCase):
    """Candidate falsifier for T7-ARCH-003 F15; test-only, no acceptance authority."""

    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-t7-f15",
            agent_id="frankenstein-2",
            task_id="task-t7-f15",
            turn_id="turn-input",
            causal_id="causal-input-t7-f15",
            generation=20,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="fixture:t7-f15",
            input_sha256="f" * 64,
            provenance_refs=("trigger7:t7-arch-003:f15",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-t7-f15", generation=21, turn_id="turn-session"
            ),
            provenance_refs=("trigger7:t7-arch-003:f15-session",),
        )

    def test_f15_closed_restart_reentry_is_exactly_once(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-answer",
            packet_id="output-f15",
            monotonic_ms=100,
            text_segment="Das wurde vollständig gehört.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=500,
            sequence=0,
        )
        cortex.advance_output(
            "output-f15", playback_state="started", monotonic_ms=110, heard_fraction=0.0
        )
        cortex.advance_output(
            "output-f15", playback_state="completed", monotonic_ms=610, heard_fraction=1.0
        )
        heard = build_heard_result(session=session, output_packets=cortex.outputs)
        outcome = cortex.close_session(
            turn_id="turn-answer",
            monotonic_ms=620,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-t7-f15", generation=22, turn_id="turn-outcome"
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
            provenance_refs=("trigger7:t7-arch-003:f15-outcome",),
        )
        close_event = cortex.events[-1]
        first = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            provenance_refs=("trigger7:t7-arch-003:f15-reentry",),
        )

        checkpoint = export_packet_cortex_checkpoint(cortex)
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=700)

        self.assertFalse(resumed.is_open)
        self.assertEqual(sum(event.event_kind == "SESSION_OPEN" for event in resumed.events), 1)
        self.assertEqual(sum(event.event_kind == "SESSION_CLOSE" for event in resumed.events), 1)
        self.assertEqual(len(resumed.events), len(cortex.events))
        self.assertEqual(resumed.outputs, cortex.outputs)
        self.assertIsNotNone(resumed._closed_outcome)
        restored_outcome = resumed._closed_outcome
        self.assertEqual(restored_outcome, outcome)
        self.assertEqual(restored_outcome.outcome_id, outcome.outcome_id)
        self.assertEqual(restored_outcome.sha256(), outcome.sha256())

        restored_close = next(event for event in resumed.events if event.event_kind == "SESSION_CLOSE")
        replay = bind_completed_reentry(
            session=session,
            outcome=restored_outcome,
            output_packets=resumed.outputs,
            close_event=restored_close,
            provenance_refs=("trigger7:t7-arch-003:f15-reentry",),
            existing=first,
        )
        self.assertEqual(replay, first)
        self.assertEqual(replay.receipt_id, first.receipt_id)
        self.assertEqual(replay.heard_result_ref, first.heard_result_ref)
        self.assertEqual(replay.voiceoutcome_id, first.voiceoutcome_id)
        self.assertEqual(replay.ordered_output_packet_ids, first.ordered_output_packet_ids)
        self.assertEqual(replay.canonical_memory_write_credit if hasattr(replay, "canonical_memory_write_credit") else 0, 0)
        self.assertEqual(replay.gwt_runtime_credit if hasattr(replay, "gwt_runtime_credit") else 0, 0)


if __name__ == "__main__":
    unittest.main()
