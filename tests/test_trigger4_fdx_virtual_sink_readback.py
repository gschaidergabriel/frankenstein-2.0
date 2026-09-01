from __future__ import annotations

import unittest

from frankenstein2.voice_packet_cortex import VoiceOutputPacket
from trigger4.tools.local_voice.fdx_virtual_sink_readback import (
    VirtualSinkEvidenceError,
    exercise_interrupted_packet_virtual_sink,
)


def interrupted_packet() -> VoiceOutputPacket:
    return VoiceOutputPacket(
        session_id="session-fdx-virtual-sink",
        turn_id="turn-output",
        packet_id="output-old",
        monotonic_ms=100,
        text_segment="Ich erkläre das.",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=1000,
        first_output_ms=115,
        sequence=0,
        cancellable=True,
        playback_state="interrupted",
        heard_fraction=0.25,
        interruption_ms=140,
        commit_eligible=False,
    )


class KernelPipeVirtualSinkReadbackTests(unittest.TestCase):
    def test_byte_identical_readback_and_post_cancel_fence(self) -> None:
        before = b"\x00\x00\x80?" * 4096
        after = b"\x00\x00\x00?" * 1024
        receipt = exercise_interrupted_packet_virtual_sink(
            packet=interrupted_packet(),
            pre_cancel_audio_bytes=before,
            post_cancel_generated_audio_bytes=after,
            request_admission_monotonic_ms=100,
            generated_monotonic_ms=110,
            sink_admission_monotonic_ms=115,
            cancel_monotonic_ms=140,
            post_cancel_generated_monotonic_ms=145,
            sample_rate=24000,
            pre_cancel_sample_count=4096,
            post_cancel_sample_count=1024,
        )
        self.assertEqual(
            receipt["result"],
            "EXECUTED_NO_COUNTEREXAMPLE_AT_KERNEL_PIPE_VIRTUAL_SINK_SCOPE",
        )
        self.assertEqual(receipt["pre_cancel_sink_readback"]["byte_count"], len(before))
        self.assertTrue(receipt["pre_cancel_sink_readback"]["eof_observed"])
        self.assertTrue(receipt["post_cancel_write_rejected"])
        self.assertEqual(
            receipt["delivery_receipt"]["sink_post_cancel_admission_count"],
            0,
        )
        self.assertEqual(
            receipt["delivery_receipt"]["generated_after_cancel_discarded_count"],
            1,
        )
        self.assertTrue(receipt["delivery_receipt"]["packet_commit_fence_candidate"])
        self.assertEqual(receipt["credit_boundary"]["physical_audio"], 0)
        self.assertEqual(receipt["credit_boundary"]["human_heard_output"], 0)
        self.assertEqual(receipt["credit_boundary"]["whole_voice_system"], 0)

    def test_completed_packet_cannot_be_relabelled_as_interrupted_sink_cancel(self) -> None:
        packet = VoiceOutputPacket(
            session_id="session-fdx-virtual-sink",
            turn_id="turn-output",
            packet_id="output-complete",
            monotonic_ms=100,
            text_segment="Fertig.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            first_output_ms=110,
            sequence=0,
            cancellable=True,
            playback_state="completed",
            heard_fraction=1.0,
            interruption_ms=None,
            commit_eligible=True,
        )
        with self.assertRaises(VirtualSinkEvidenceError):
            exercise_interrupted_packet_virtual_sink(
                packet=packet,
                pre_cancel_audio_bytes=b"\x01" * 64,
                post_cancel_generated_audio_bytes=b"\x02" * 16,
                request_admission_monotonic_ms=100,
                generated_monotonic_ms=105,
                sink_admission_monotonic_ms=110,
                cancel_monotonic_ms=120,
                post_cancel_generated_monotonic_ms=125,
                sample_rate=24000,
                pre_cancel_sample_count=16,
                post_cancel_sample_count=4,
            )


if __name__ == "__main__":
    unittest.main()
