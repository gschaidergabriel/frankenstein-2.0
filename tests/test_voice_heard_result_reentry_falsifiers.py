from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    VoiceHeardResultReentryError,
    build_heard_result,
    validate_completed_heard_result,
)
from frankenstein2.voice_packet_cortex import VoicePacketCortex


class VoiceHeardResultRepairFalsifiers(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp717-repair",
            agent_id="frankenstein-2",
            task_id="task-wp717-repair",
            turn_id="turn-input",
            causal_id="causal-input-wp717-repair",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="fixture:wp717-repair",
            input_sha256="7" * 64,
            provenance_refs=("test:wp717-repair",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp717-repair",
                generation=4,
                turn_id="turn-session",
            ),
            provenance_refs=("test:wp717-repair-session",),
        )

    def closed(self):
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-output",
            packet_id="output-0",
            monotonic_ms=10,
            text_segment="Exakt gehört.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            sequence=0,
        )
        cortex.advance_output(
            "output-0", playback_state="started", monotonic_ms=20, heard_fraction=0.0
        )
        cortex.advance_output(
            "output-0", playback_state="completed", monotonic_ms=120, heard_fraction=1.0
        )
        pre_close = cortex.outputs[0]
        heard = build_heard_result(session=session, output_packets=(pre_close,))
        outcome = cortex.close_session(
            turn_id="turn-close",
            monotonic_ms=130,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-wp717-repair",
                generation=5,
                turn_id="turn-outcome",
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
            provenance_refs=("test:wp717-repair-outcome",),
        )
        return session, cortex, pre_close, heard, outcome, cortex.events[-1]

    def test_single_pass_iterable_cannot_bypass_voiceoutcome_backlink(self) -> None:
        session, cortex, _pre, _heard, outcome, close_event = self.closed()
        wrong_backlink = replace(cortex.outputs[0], voiceoutcome_ref="voice-outcome:wrong")
        with self.assertRaisesRegex(VoiceHeardResultReentryError, "bound back"):
            validate_completed_heard_result(
                session=session,
                outcome=outcome,
                output_packets=iter((wrong_backlink,)),
                close_event=close_event,
            )

    def test_dedicated_wp715_close_turn_is_valid(self) -> None:
        session, cortex, _pre, heard, outcome, close_event = self.closed()
        self.assertEqual(close_event.turn_id, "turn-close")
        self.assertEqual(heard.turn_id, "turn-output")
        validated = validate_completed_heard_result(
            session=session,
            outcome=outcome,
            output_packets=iter(cortex.outputs),
            close_event=close_event,
        )
        self.assertEqual(validated.payload_sha256, heard.payload_sha256)

    def test_pre_close_full_packet_identity_changes_on_timing_metadata_change(self) -> None:
        session, _cortex, pre_close, heard, _outcome, _close_event = self.closed()
        changed = replace(
            pre_close,
            planned_audio_duration_ms=pre_close.planned_audio_duration_ms + 1,
        )
        changed_heard = build_heard_result(session=session, output_packets=(changed,))
        self.assertNotEqual(changed.sha256(), pre_close.sha256())
        self.assertNotEqual(
            changed_heard.ordered_output_material_sha256s,
            heard.ordered_output_material_sha256s,
        )
        self.assertNotEqual(changed_heard.payload_sha256, heard.payload_sha256)

    def test_outcome_backlink_is_only_normalized_field_in_heard_identity(self) -> None:
        session, cortex, pre_close, heard, outcome, _close_event = self.closed()
        post_close = cortex.outputs[0]
        self.assertIsNone(pre_close.voiceoutcome_ref)
        self.assertEqual(post_close.voiceoutcome_ref, outcome.outcome_id)
        self.assertNotEqual(pre_close.sha256(), post_close.sha256())
        rebuilt = build_heard_result(session=session, output_packets=(post_close,))
        self.assertEqual(rebuilt.payload_sha256, heard.payload_sha256)
        self.assertEqual(
            rebuilt.ordered_output_material_sha256s,
            heard.ordered_output_material_sha256s,
        )

    def test_close_event_wrong_session_still_fails_closed(self) -> None:
        session, cortex, _pre, _heard, outcome, close_event = self.closed()
        wrong = replace(close_event, session_id="session-wrong")
        with self.assertRaisesRegex(VoiceHeardResultReentryError, "exact voice session"):
            validate_completed_heard_result(
                session=session,
                outcome=outcome,
                output_packets=cortex.outputs,
                close_event=wrong,
            )


if __name__ == "__main__":
    unittest.main()
