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


class Trigger7RecoveryImportBoundsFalsifier(unittest.TestCase):
    """RBOUND1: rehashed checkpoint import must preserve live input cardinality law."""

    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-t7-rbound1",
            agent_id="frankenstein-2",
            task_id="task-t7-rbound1",
            turn_id="turn-root",
            causal_id="causal-root-t7-rbound1",
            generation=1,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="trigger7:rbound1:fixture",
            input_sha256="a" * 64,
            provenance_refs=("trigger7:rbound1",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-t7-rbound1",
                generation=2,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger7:rbound1:session",),
        )

    @staticmethod
    def rehash(checkpoint: dict) -> None:
        canonical = json.dumps(
            checkpoint["payload"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        checkpoint["payload_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def test_rbound1_rehashed_oversized_input_seen_fails_at_resume_boundary(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        checkpoint = deepcopy(export_packet_cortex_checkpoint(cortex))

        checkpoint["payload"]["input_seen"] = [
            [f"forged-input-{index:04d}", "f" * 64]
            for index in range(VoicePacketCortex.MAX_INPUT_PACKETS + 1)
        ]
        self.rehash(checkpoint)

        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, checkpoint, monotonic_ms=100)


if __name__ == "__main__":
    unittest.main()
