from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.context_compiler import (
    CHANNEL_STATE,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    compile_context,
)
from frankenstein2.gwt_reentry_uptake_binding import GwtReentryUptakeBinding
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.typed_memory import KIND_FACT, create_typed_memory
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    VoiceHeardResultReentryError,
    bind_completed_reentry,
    build_heard_result,
    build_interrupted_heard_prefix,
    validate_completed_heard_result,
    validate_context_binding,
    validate_gwt_event_binding,
    validate_memory_event_bindings,
)
from frankenstein2.voice_packet_cortex import VoicePacketCortex, VoicePacketCortexError


class VoiceHeardResultReentryTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp717",
            agent_id="frankenstein-2",
            task_id="task-wp717",
            turn_id="turn-input",
            causal_id="causal-input-wp717",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="fixture:wp717",
            input_sha256="1" * 64,
            provenance_refs=("test:wp717",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp717", generation=4, turn_id="turn-session"
            ),
            provenance_refs=("test:wp717-session",),
        )

    def completed_cortex(self, texts=("Hallo",), *, result_override=None):
        session = self.session()
        cortex = VoicePacketCortex(session)
        now = 10
        for sequence, text in enumerate(texts):
            packet_id = f"output-{sequence}"
            cortex.queue_output(
                turn_id="turn-voice",
                packet_id=packet_id,
                monotonic_ms=now,
                text_segment=text,
                expression_intent="neutral",
                speech_act="ANSWER",
                planned_audio_duration_ms=100,
                sequence=sequence,
            )
            cortex.advance_output(
                packet_id, playback_state="started", monotonic_ms=now + 1, heard_fraction=0.0
            )
            cortex.advance_output(
                packet_id, playback_state="completed", monotonic_ms=now + 101, heard_fraction=1.0
            )
            now += 120
        prepared = build_heard_result(session=session, output_packets=cortex.outputs)
        result_ref, result_sha256 = (
            (prepared.payload_ref, prepared.payload_sha256)
            if result_override is None
            else result_override
        )
        outcome = cortex.close_session(
            turn_id="turn-voice",
            monotonic_ms=now + 10,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-wp717", generation=5, turn_id="turn-outcome"
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=result_ref,
            result_sha256=result_sha256,
            provenance_refs=("test:wp717-outcome",),
        )
        close_event = cortex.events[-1]
        self.assertEqual(close_event.event_kind, "SESSION_CLOSE")
        return session, cortex, prepared, outcome, close_event

    def context_for(self, *, payload_ref, payload_sha256, source_ref, source_sha256):
        item = ContextItem.create(
            item_id="context:voice-heard-result",
            channel=CHANNEL_STATE,
            payload_ref=payload_ref,
            payload_sha256=payload_sha256,
            source_ref=source_ref,
            source_sha256=source_sha256,
            source_generation=1,
            source_classification="VOICE_REENTRY_REFERENCE_ONLY",
            priority_bp=9000,
            cost_units=7,
            required=True,
            provenance_refs=("test:context",),
            evidence_refs=("test:heard-result",),
        )
        witness = ContextCostWitness.create(
            payload_sha256=payload_sha256,
            renderer_id="test-renderer",
            renderer_version="1",
            tokenizer_id="test-tokenizer",
            tokenizer_version="1",
            measured_cost_units=7,
            generation=1,
            measurement_ref="measurement:voice-context-cost",
            provenance_refs=("test:context-cost",),
        )
        need = ContextNeed.create(
            context_id="context-view:wp717",
            task_id="task-wp717",
            task_generation=1,
            allowed_channels=(CHANNEL_STATE,),
            required_channels=(CHANNEL_STATE,),
            max_items=1,
            max_cost_units=7,
            evidence_refs=("test:context-need",),
        )
        view = compile_context(need, (item,), cost_witnesses=(witness,))
        return item, witness, view

    def test_vsr01_exact_heard_result_matches_voiceoutcome_and_close_inventory(self) -> None:
        session, cortex, prepared, outcome, close_event = self.completed_cortex(("Hallo ", "Welt"))
        validated = validate_completed_heard_result(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
        )
        self.assertEqual(validated, prepared)
        self.assertEqual(validated.text_segments, ("Hallo ", "Welt"))
        self.assertEqual(validated.ordered_output_packet_ids, ("output-0", "output-1"))

    def test_vsr01_arbitrary_voiceoutcome_digest_is_rejected_by_consumer(self) -> None:
        session, cortex, _prepared, outcome, close_event = self.completed_cortex(
            ("Exakt gehört",), result_override=("voice-result:synthetic", "b" * 64)
        )
        # WP715 intentionally permits this evidence-only pair.  WP717 must not promote it.
        with self.assertRaisesRegex(VoiceHeardResultReentryError, "UNBOUND_VOICEOUTCOME_RESULT"):
            validate_completed_heard_result(
                session=session,
                outcome=outcome,
                output_packets=cortex.outputs,
                close_event=close_event,
            )

    def test_vsr01_multi_segment_order_and_omission_fail_closed(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        for sequence, text in enumerate(("A", "B")):
            packet_id = f"output-{sequence}"
            cortex.queue_output(
                turn_id="turn-voice", packet_id=packet_id, monotonic_ms=10 + sequence * 100,
                text_segment=text, expression_intent="neutral", speech_act="ANSWER",
                planned_audio_duration_ms=90, sequence=sequence,
            )
            cortex.advance_output(packet_id, playback_state="started", monotonic_ms=11 + sequence * 100, heard_fraction=0.0)
            cortex.advance_output(packet_id, playback_state="completed", monotonic_ms=90 + sequence * 100, heard_fraction=1.0)
        with self.assertRaises(VoiceHeardResultReentryError):
            build_heard_result(session=session, output_packets=tuple(reversed(cortex.outputs)))

        # Deliberately derive the VoiceOutcome from only segment 0.  The core may close because both
        # outputs are commit-eligible, but the SESSION_CLOSE inventory exposes the omitted segment.
        omitted_payload = build_heard_result(session=session, output_packets=(cortex.outputs[0],))
        outcome = cortex.close_session(
            turn_id="turn-voice", monotonic_ms=300,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-omission", generation=5, turn_id="turn-outcome"
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=omitted_payload.payload_ref,
            result_sha256=omitted_payload.payload_sha256,
            provenance_refs=("test:omission",),
        )
        with self.assertRaises(VoiceHeardResultReentryError):
            validate_completed_heard_result(
                session=session,
                outcome=outcome,
                output_packets=(cortex.outputs[0],),
                close_event=cortex.events[-1],
            )

    def test_vsr01_context_binding_requires_exact_payload_source_and_cost_witness(self) -> None:
        session, cortex, prepared, outcome, close_event = self.completed_cortex(("Kontext",))
        item, witness, view = self.context_for(
            payload_ref=prepared.payload_ref,
            payload_sha256=prepared.payload_sha256,
            source_ref=outcome.outcome_id,
            source_sha256=outcome.sha256(),
        )
        receipt = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            context_item=item,
            cost_witness=witness,
            context_view=view,
            provenance_refs=("test:wp717-receipt",),
        )
        self.assertEqual(receipt.context_view_sha256, view.sha256())
        self.assertEqual(receipt.context_cost_witness_sha256, witness.sha256())
        self.assertEqual(receipt.gwt_runtime_credit if hasattr(receipt, "gwt_runtime_credit") else 0, 0)

    def test_vsr02_interrupted_prefix_is_ephemeral_and_excludes_unheard_tail(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-voice", packet_id="output-interrupted", monotonic_ms=10,
            text_segment="gehört|NICHTGEHOERT", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=500, sequence=0,
        )
        cortex.advance_output("output-interrupted", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-interrupted", playback_state="heard", monotonic_ms=200, heard_fraction=0.35)
        cortex.cancel_for_barge_in(turn_id="turn-user", monotonic_ms=210)
        packet = cortex.outputs[0]
        prefix = build_interrupted_heard_prefix(
            packet=packet,
            heard_prefix_text="gehört|",
            measurement_ref="playout-ack:prefix-1",
            provenance_refs=("test:playout-ack",),
        )
        self.assertEqual(prefix.heard_prefix_text, "gehört|")
        self.assertEqual(prefix.unheard_tail_text, "NICHTGEHOERT")
        self.assertIn("EPHEMERAL_NEXT_TURN_CONTEXT_ONLY", prefix.classification)
        with self.assertRaises(VoiceHeardResultReentryError):
            build_heard_result(session=session, output_packets=(packet,))

        item, witness, view = self.context_for(
            payload_ref=prefix.payload_ref,
            payload_sha256=prefix.payload_sha256,
            source_ref=packet.packet_id,
            source_sha256=packet.sha256(),
        )
        validate_context_binding(
            payload_ref=prefix.payload_ref,
            payload_sha256=prefix.payload_sha256,
            source_ref=packet.packet_id,
            source_sha256=packet.sha256(),
            context_item=item,
            cost_witness=witness,
            context_view=view,
        )

    def test_vsr04_memory_ref_requires_exact_lifecycle_and_typed_record(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        state = create_memory(
            memory_id="memory:voice-fact-1",
            payload_ref="payload:voice-fact-1",
            payload_sha256="3" * 64,
            provenance_refs=("test:memory-source",),
        )
        record = create_typed_memory(
            state=state,
            memory_kind=KIND_FACT,
            refs={"evidence": ("voice:heard-result",)},
        )
        event = cortex.emit_intent(
            turn_id="turn-memory",
            monotonic_ms=100,
            voice_intent="WAIT",
            memory_refs=(state.memory_id,),
        )
        evidence = validate_memory_event_bindings(
            event=event,
            bindings=((state, record),),
        )
        self.assertEqual(evidence[0].lifecycle_state_sha256, state.sha256())
        self.assertEqual(evidence[0].typed_memory_sha256, record.sha256())

        changed = create_memory(
            memory_id=state.memory_id,
            payload_ref="payload:other",
            payload_sha256="4" * 64,
            provenance_refs=("test:memory-source",),
        )
        with self.assertRaises(VoiceHeardResultReentryError):
            validate_memory_event_bindings(
                event=event,
                bindings=((changed, record),),
                heard_result_ref=state.payload_ref,
                heard_result_sha256=state.payload_sha256,
            )

    def test_vsr03_gwt_ref_is_reference_only_and_fail_closed_on_wrong_ref(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        binding = GwtReentryUptakeBinding(
            binding_id="gwt-binding:wp717",
            canonical_reentry_key="1" * 64,
            reentry_witness_sha256="2" * 64,
            uptake_receipt_id="uptake-receipt:wp717",
            uptake_receipt_sha256="3" * 64,
            broadcast_id="broadcast:wp717",
            broadcast_generation=1,
            broadcast_sha256="4" * 64,
            recipient_cell_id="cell:wp717",
            delivery_status="DELIVERED",
            uptake_status="NOT_UPTAKEN",
            downstream_ref=None,
            downstream_sha256=None,
            binding_status="WP507_NOT_UPTAKEN_BOUND",
            provenance_refs=("test:gwt-binding",),
        )
        exact = cortex.emit_intent(
            turn_id="turn-gwt", monotonic_ms=100, voice_intent="WAIT", gwt_ref=binding.binding_id
        )
        validate_gwt_event_binding(event=exact, binding=binding)
        evidence = binding.as_dict()
        self.assertEqual(evidence["causal_influence_claim"], "NOT_ESTABLISHED_BY_BINDING")
        self.assertEqual(evidence["gwt_runtime_credit"], 0)
        self.assertEqual(evidence["jspace_runtime_credit"], 0)
        self.assertFalse(evidence["whole_system_acceptance"])
        opaque = cortex.emit_intent(
            turn_id="turn-gwt", monotonic_ms=101, voice_intent="WAIT", gwt_ref="gwt:opaque-broadcast"
        )
        with self.assertRaisesRegex(VoiceHeardResultReentryError, "opaque|stale|wrong"):
            validate_gwt_event_binding(event=opaque, binding=binding)

    def test_vsr05_cancelled_late_tool_result_never_reenters_adapter_surface(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-tool", packet_id="output-tool", monotonic_ms=10,
            text_segment="Ich prüfe.", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=300, sequence=0,
        )
        cortex.advance_output("output-tool", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.emit_intent(
            turn_id="turn-tool", monotonic_ms=30, voice_intent="TOOL_USE", tool_ref="tool:late"
        )
        cortex.cancel_for_barge_in(turn_id="turn-user", monotonic_ms=40)
        with self.assertRaises(VoicePacketCortexError):
            cortex.emit_system_event(
                turn_id="turn-tool", monotonic_ms=50, event_kind="TOOL_RESULT", tool_ref="tool:late"
            )

    def test_vsr06_exact_replay_is_idempotent_but_rebinding_fails(self) -> None:
        session, cortex, _prepared, outcome, close_event = self.completed_cortex(("Replay",))
        first = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            provenance_refs=("test:replay",),
        )
        second = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            provenance_refs=("test:replay",),
            existing=first,
        )
        self.assertEqual(first, second)
        with self.assertRaises(VoiceHeardResultReentryError):
            bind_completed_reentry(
                session=session,
                outcome=outcome,
                output_packets=cortex.outputs,
                close_event=close_event,
                tool_ref_disposition="DIFFERENT_REPLAY_BINDING",
                provenance_refs=("test:replay",),
                existing=first,
            )


if __name__ == "__main__":
    unittest.main()
