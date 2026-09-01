from __future__ import annotations

import hashlib
import unittest

from frankenstein2.voice_packet_cortex import VoiceOutputPacket
from trigger4.tools.local_voice.fdx_audio_delivery_evidence import (
    AudioDeliveryEvidenceError,
    RunLocalAudioDeliveryBinding,
)


def interrupted_packet() -> VoiceOutputPacket:
    return VoiceOutputPacket(
        session_id="session-fdx",
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


class RunLocalAudioDeliveryBindingTests(unittest.TestCase):
    def binding(self) -> RunLocalAudioDeliveryBinding:
        return RunLocalAudioDeliveryBinding(
            voice_session_id="session-fdx",
            turn_id="turn-output",
            voice_output_packet_id="output-old",
            request_admission_monotonic_ms=100,
            producer_cancel_capability=False,
        )

    def test_post_cancel_generated_chunk_is_discarded_without_sink_credit(self) -> None:
        binding = self.binding()
        first = b"\x00\x00\x80?" * 16
        binding.record_chunk(
            sequence=0,
            generated_monotonic_ms=110,
            sample_rate=24000,
            sample_count=16,
            canonical_audio_bytes=first,
            sink_admission_monotonic_ms=115,
        )
        binding.cancel_sink(monotonic_ms=140)
        second = b"\x00\x00\x00?" * 8
        observed = binding.record_chunk(
            sequence=1,
            generated_monotonic_ms=145,
            sample_rate=24000,
            sample_count=8,
            canonical_audio_bytes=second,
            sink_admission_monotonic_ms=None,
        )
        self.assertTrue(observed.generated_after_cancel_discarded)

        receipt = binding.receipt(packet=interrupted_packet())
        self.assertEqual(receipt["result"], "EXECUTED_NO_COUNTEREXAMPLE_AT_RUN_LOCAL_SINK_PACKET_SCOPE")
        self.assertEqual(receipt["sink_post_cancel_admission_count"], 0)
        self.assertEqual(receipt["generated_after_cancel_count"], 1)
        self.assertEqual(receipt["generated_after_cancel_discarded_count"], 1)
        self.assertTrue(receipt["sink_delivery_cancel_candidate"])
        self.assertTrue(receipt["packet_commit_fence_candidate"])
        self.assertFalse(receipt["producer_generation_cancel_candidate"])
        self.assertEqual(receipt["request_to_first_generated_chunk_ms"], 10)
        self.assertEqual(receipt["request_to_first_sink_admission_ms"], 15)
        self.assertEqual(receipt["chunks"][0]["sha256"], hashlib.sha256(first).hexdigest())
        self.assertEqual(receipt["credit_boundary"]["whole_voice_system"], 0)

    def test_post_cancel_sink_admission_is_product_negative(self) -> None:
        binding = self.binding()
        binding.record_chunk(
            sequence=0,
            generated_monotonic_ms=110,
            sample_rate=24000,
            sample_count=4,
            canonical_audio_bytes=b"\x00" * 16,
            sink_admission_monotonic_ms=115,
        )
        binding.cancel_sink(monotonic_ms=120)
        binding.record_chunk(
            sequence=1,
            generated_monotonic_ms=125,
            sample_rate=24000,
            sample_count=4,
            canonical_audio_bytes=b"\x01" * 16,
            sink_admission_monotonic_ms=130,
        )
        receipt = binding.receipt(packet=interrupted_packet())
        self.assertEqual(receipt["result"], "PRODUCT_NEGATIVE")
        self.assertEqual(receipt["sink_post_cancel_admission_count"], 1)
        self.assertIn("POST_CANCEL_CHUNK_ADMITTED_TO_OLD_PACKET", receipt["product_negative_reasons"])
        self.assertEqual(receipt["credit_boundary"]["run_local_sink_delivery_evidence_candidate"], 0)

    def test_packet_identity_mismatch_fails_closed(self) -> None:
        binding = self.binding()
        binding.record_chunk(
            sequence=0,
            generated_monotonic_ms=110,
            sample_rate=24000,
            sample_count=4,
            canonical_audio_bytes=b"\x00" * 16,
            sink_admission_monotonic_ms=115,
        )
        binding.cancel_sink(monotonic_ms=120)
        wrong = VoiceOutputPacket(
            session_id="session-fdx",
            turn_id="turn-output",
            packet_id="other-output",
            monotonic_ms=100,
            text_segment="x",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            first_output_ms=115,
            sequence=0,
            cancellable=True,
            playback_state="interrupted",
            heard_fraction=0.1,
            interruption_ms=120,
            commit_eligible=False,
        )
        with self.assertRaises(AudioDeliveryEvidenceError):
            binding.receipt(packet=wrong)

    def test_cannot_claim_internal_producer_cancel_when_capability_is_false(self) -> None:
        binding = self.binding()
        with self.assertRaises(AudioDeliveryEvidenceError):
            binding.request_producer_cancel(monotonic_ms=120, executed=True)


if __name__ == "__main__":
    unittest.main()
