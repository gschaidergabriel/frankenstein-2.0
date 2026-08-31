from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    resume_packet_cortex,
)


def _payload_digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class F18ClosedCheckpointCausalFalsifier(unittest.TestCase):
    """T7-ARCH-003 F18: checksum-valid closed checkpoint must preserve causal close relation."""

    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-f18-recovery",
            agent_id="frankenstein-2",
            task_id="task-f18-recovery",
            turn_id="turn-root",
            causal_id="causal-root-f18-recovery",
            generation=8,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:f18-recovery",
            input_sha256="e" * 64,
            provenance_refs=("trigger7:t7-arch-003:f18",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-f18-recovery",
                generation=9,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger7:t7-arch-003:f18-session",),
        )

    def test_f18_checksum_valid_causally_mismatched_closed_checkpoint_is_rejected(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        outcome_causal_identity = session.session_causal_identity.derive(
            causal_id="causal-outcome-f18-recovery",
            generation=10,
            turn_id="turn-close",
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
            event
            for event in tampered["payload"]["events"]
            if event["event_kind"] == "SESSION_CLOSE"
        ]
        self.assertEqual(len(close_events), 1)

        # Keep the checkpoint structurally valid and recompute its envelope digest, but sever
        # the causal relation between the serialized SESSION_CLOSE event and VoiceOutcome.
        close_events[0]["turn_id"] = "turn-forged-close"
        tampered["payload_sha256"] = _payload_digest(tampered["payload"])

        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, tampered, monotonic_ms=250)


if __name__ == "__main__":
    unittest.main()
