from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.gwt_reentry_uptake_binding import GwtReentryUptakeBinding
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.typed_memory import KIND_FACT, create_typed_memory
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    VoiceHeardResultReentryError,
    bind_completed_reentry,
    build_heard_result,
    validate_gwt_event_binding,
)
from frankenstein2.voice_packet_cortex import VoicePacketCortex


class WP717G3MemoryGwtLineageFalsifiers(unittest.TestCase):
    """Adversarial discriminators from the Trigger7 VSR07/VSR08 addendum.

    These tests intentionally describe the stronger higher-reentry semantics. They should fail
    against the pre-G3 consumer because that consumer validates memory and GWT references without
    proving the additional heard-payload/factory-lineage relations required for higher promotion.
    """

    def _session(self, suffix: str) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id=f"session-wp717-g3-{suffix}",
            agent_id="frankenstein-2",
            task_id=f"task-wp717-g3-{suffix}",
            turn_id="turn-input",
            causal_id=f"causal-input-wp717-g3-{suffix}",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref=f"fixture:wp717-g3:{suffix}",
            input_sha256="1" * 64,
            provenance_refs=(f"test:wp717-g3:{suffix}",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id=f"causal-session-wp717-g3-{suffix}",
                generation=4,
                turn_id="turn-session",
            ),
            provenance_refs=(f"test:wp717-g3-session:{suffix}",),
        )

    def test_vsr07_unrelated_valid_memory_payload_cannot_enter_heard_result_memory_receipt(self) -> None:
        session = self._session("vsr07")
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-voice",
            packet_id="output-0",
            monotonic_ms=10,
            text_segment="Das ist exakt gehoert.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            sequence=0,
        )
        cortex.advance_output(
            "output-0", playback_state="started", monotonic_ms=11, heard_fraction=0.0
        )
        cortex.advance_output(
            "output-0", playback_state="completed", monotonic_ms=111, heard_fraction=1.0
        )
        heard = build_heard_result(session=session, output_packets=cortex.outputs)

        unrelated_state = create_memory(
            memory_id="memory:wp717-g3-unrelated",
            payload_ref="payload:not-the-heard-result",
            payload_sha256="9" * 64,
            provenance_refs=("test:wp717-g3-vsr07-unrelated",),
        )
        unrelated_typed = create_typed_memory(
            state=unrelated_state,
            memory_kind=KIND_FACT,
            refs={"evidence": ("payload:not-the-heard-result",)},
        )
        memory_event = cortex.emit_intent(
            turn_id="turn-memory-bind",
            monotonic_ms=120,
            voice_intent="WAIT",
            memory_refs=(unrelated_state.memory_id,),
        )

        outcome = cortex.close_session(
            turn_id="turn-voice",
            monotonic_ms=130,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-wp717-g3-vsr07",
                generation=5,
                turn_id="turn-outcome",
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
            provenance_refs=("test:wp717-g3-vsr07-outcome",),
        )
        close_event = cortex.events[-1]

        with self.assertRaisesRegex(
            VoiceHeardResultReentryError,
            "heard-result memory payload",
        ):
            bind_completed_reentry(
                session=session,
                outcome=outcome,
                output_packets=cortex.outputs,
                close_event=close_event,
                memory_event=memory_event,
                memory_bindings=((unrelated_state, unrelated_typed),),
                provenance_refs=("test:wp717-g3-vsr07-receipt",),
            )

    def test_vsr08_direct_gwt_binding_without_factory_lineage_is_rejected(self) -> None:
        session = self._session("vsr08")
        cortex = VoicePacketCortex(session)
        direct = GwtReentryUptakeBinding(
            binding_id="gwt-binding:wp717-g3-direct",
            canonical_reentry_key="1" * 64,
            reentry_witness_sha256="2" * 64,
            uptake_receipt_id="uptake-receipt:wp717-g3-direct",
            uptake_receipt_sha256="3" * 64,
            broadcast_id="broadcast:wp717-g3-direct",
            broadcast_generation=1,
            broadcast_sha256="4" * 64,
            recipient_cell_id="G1",
            delivery_status="DELIVERED",
            uptake_status="NOT_UPTAKEN",
            downstream_ref=None,
            downstream_sha256=None,
            binding_status="WP507_NOT_UPTAKEN_BOUND",
            provenance_refs=("test:wp717-g3-vsr08-direct",),
        )
        event = cortex.emit_intent(
            turn_id="turn-gwt",
            monotonic_ms=100,
            voice_intent="WAIT",
            gwt_ref=direct.binding_id,
        )

        with self.assertRaisesRegex(
            VoiceHeardResultReentryError,
            "factory|lineage",
        ):
            validate_gwt_event_binding(event=event, binding=direct)


if __name__ == "__main__":
    unittest.main()
