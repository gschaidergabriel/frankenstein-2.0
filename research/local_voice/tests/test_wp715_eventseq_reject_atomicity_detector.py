from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import export_packet_cortex_checkpoint, resume_packet_cortex


class WP715RejectAtomicityDetector(unittest.TestCase):
    def _session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp715-eventseq-detector",
            agent_id="frankenstein-2",
            task_id="wp715-eventseq-detector",
            turn_id="turn-root",
            causal_id="causal-root-wp715-eventseq-detector",
            generation=1,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="wp715:eventseq-detector",
            input_sha256="e" * 64,
            provenance_refs=("trigger4:wp715-eventseq-detector",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp715-eventseq-detector",
                generation=2,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger4:wp715-eventseq-detector-session",),
        )

    def test_detector_reports_exact_current_reject_atomicity_state(self) -> None:
        session = self._session()
        cortex = VoicePacketCortex(session)
        before_seq = cortex._event_seq
        before_events = tuple(event.as_dict() for event in cortex.events)

        rejected = False
        try:
            cortex.emit_system_event(
                turn_id="turn-invalid",
                monotonic_ms=10,
                event_kind="ERROR",
                detail=1,  # CortexEventPacket rejects non-string detail.
            )
        except VoicePacketCortexError:
            rejected = True

        after_seq = cortex._event_seq
        after_events = tuple(event.as_dict() for event in cortex.events)
        state_mutated_on_reject = (after_seq != before_seq) or (after_events != before_events)

        checkpoint = export_packet_cortex_checkpoint(cortex)
        resume_rejected = False
        try:
            resume_packet_cortex(session, checkpoint, monotonic_ms=20)
        except VoicePacketCortexError:
            resume_rejected = True

        product_negative = rejected and state_mutated_on_reject and resume_rejected
        classification = "PRODUCT_NEGATIVE" if product_negative else "PASS_OR_DIFFERENT_BEHAVIOR"
        report = {
            "schema": "F2_WP715_EVENTSEQ_REJECT_ATOMICITY_DETECTOR/v1",
            "classification": classification,
            "invalid_call_rejected": rejected,
            "event_seq_before": before_seq,
            "event_seq_after": after_seq,
            "events_before": len(before_events),
            "events_after": len(after_events),
            "state_mutated_on_reject": state_mutated_on_reject,
            "checkpoint_resume_rejected": resume_rejected,
            "credit": {
                "repository_acceptance": 0,
                "vps_runtime": 0,
                "acoustic": 0,
                "whole_product": 0,
            },
        }
        print("WP715_EVENTSEQ_DETECTOR=" + json.dumps(report, sort_keys=True, separators=(",", ":")))

        # Detector CI remains green whether the product is vulnerable or repaired; the printed
        # classification is evidence. Canonical acceptance must come from the WP715 regression lane.
        self.assertTrue(rejected)
        self.assertIn(classification, {"PRODUCT_NEGATIVE", "PASS_OR_DIFFERENT_BEHAVIOR"})


if __name__ == "__main__":
    unittest.main()
