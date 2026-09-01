from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

TOOL = Path(__file__).resolve().parents[1] / "trigger4" / "tools" / "local_voice" / "fdx_delivery_receipt.py"
SPEC = importlib.util.spec_from_file_location("fdx_delivery_receipt", TOOL)
assert SPEC is not None and SPEC.loader is not None
receipt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = receipt
SPEC.loader.exec_module(receipt)

SOURCE = "a" * 64


def binding(*, capability: bool = True):
    return receipt.DeliveryBinding(
        source_sha=SOURCE,
        engine_identity="kokoro@pin",
        voice_session_id="voice-session:abc",
        turn_id="turn-1",
        voice_output_packet_id="output-1",
        scenario="FDX3_BARGE_IN_PARTIAL_OUTPUT",
        request_admitted_monotonic_ms=100.0,
        producer_cancel_capability=capability,
    )


class Trigger4FDXDeliveryReceiptTests(unittest.TestCase):
    def test_sink_cancel_and_packet_fence_pass_without_producer_cancel_credit(self) -> None:
        bound = binding(capability=False)
        bound.admit_chunk(
            chunk_bytes=b"aaaa", sample_rate=24000, samples=2,
            generated_monotonic_ms=110, sink_admitted_monotonic_ms=111,
        )
        bound.request_cancel(monotonic_ms=120)
        bound.discard_generated_chunk(
            chunk_bytes=b"bbbb", sample_rate=24000, samples=2,
            generated_monotonic_ms=121,
        )
        doc = bound.build_receipt(
            packet_playback_state="interrupted", heard_fraction=0.1,
            commit_eligible=False, voiceoutcome_ref=None,
            producer_last_generated_chunk_monotonic_ms=121,
        )
        self.assertEqual(doc["credits"]["producer_generation_cancel"], 0)
        self.assertEqual(doc["credits"]["sink_delivery_cancel"], 1)
        self.assertEqual(doc["credits"]["packet_commit_fence"], 1)
        self.assertTrue(receipt.validate_receipt(doc)["valid"])

    def test_post_cancel_sink_admission_fails_closed(self) -> None:
        bound = binding()
        bound.admit_chunk(
            chunk_bytes=b"aaaa", sample_rate=24000, samples=2,
            generated_monotonic_ms=110, sink_admitted_monotonic_ms=111,
        )
        bound.request_cancel(monotonic_ms=120)
        with self.assertRaises(receipt.FDXReceiptError):
            bound.admit_chunk(
                chunk_bytes=b"bbbb", sample_rate=24000, samples=2,
                generated_monotonic_ms=121, sink_admitted_monotonic_ms=122,
            )

    def test_internal_producer_cancel_credit_requires_no_post_cancel_generation(self) -> None:
        bound = binding(capability=True)
        bound.admit_chunk(
            chunk_bytes=b"aaaa", sample_rate=24000, samples=2,
            generated_monotonic_ms=110, sink_admitted_monotonic_ms=111,
        )
        bound.request_cancel(monotonic_ms=120)
        doc = bound.build_receipt(
            packet_playback_state="interrupted", heard_fraction=0.1,
            commit_eligible=False, voiceoutcome_ref=None,
            producer_last_generated_chunk_monotonic_ms=120,
        )
        self.assertEqual(doc["credits"]["producer_generation_cancel"], 1)
        self.assertTrue(receipt.validate_receipt(doc)["valid"])

    def test_completed_output_cannot_inherit_cancel_packet_fence(self) -> None:
        bound = binding(capability=False)
        bound.admit_chunk(
            chunk_bytes=b"aaaa", sample_rate=24000, samples=2,
            generated_monotonic_ms=110, sink_admitted_monotonic_ms=111,
        )
        doc = bound.build_receipt(
            packet_playback_state="completed", heard_fraction=1.0,
            commit_eligible=True, voiceoutcome_ref="voice-outcome:abc",
        )
        self.assertEqual(doc["credits"]["sink_delivery_cancel"], 0)
        self.assertEqual(doc["credits"]["packet_commit_fence"], 0)
        self.assertTrue(receipt.validate_receipt(doc)["valid"])

    def test_scope_inflation_is_rejected(self) -> None:
        bound = binding(capability=False)
        bound.admit_chunk(
            chunk_bytes=b"aaaa", sample_rate=24000, samples=2,
            generated_monotonic_ms=110, sink_admitted_monotonic_ms=111,
        )
        doc = bound.build_receipt(
            packet_playback_state="completed", heard_fraction=1.0,
            commit_eligible=True, voiceoutcome_ref="voice-outcome:abc",
        )
        doc["credits"]["physical_speaker"] = 1
        with self.assertRaises(receipt.FDXReceiptError):
            receipt.validate_receipt(doc)

    def test_chunk_hashes_bind_exact_bytes(self) -> None:
        bound = binding(capability=False)
        chunk_a = bound.admit_chunk(
            chunk_bytes=b"aaaa", sample_rate=24000, samples=2,
            generated_monotonic_ms=110, sink_admitted_monotonic_ms=111,
        )
        chunk_b = bound.admit_chunk(
            chunk_bytes=b"aaab", sample_rate=24000, samples=2,
            generated_monotonic_ms=112, sink_admitted_monotonic_ms=113,
        )
        self.assertNotEqual(chunk_a.sha256, chunk_b.sha256)


if __name__ == "__main__":
    unittest.main()
