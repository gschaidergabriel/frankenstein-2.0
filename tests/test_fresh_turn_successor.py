from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.fresh_turn_successor import (
    FreshTurnSuccessorError,
    memory_evidence_sha256,
    project_fresh_turn,
)
from frankenstein2.gwt_reentry_uptake_binding import GwtReentryUptakeBinding
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.typed_memory import KIND_FACT, create_typed_memory
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import bind_completed_reentry, build_heard_result
from frankenstein2.voice_packet_cortex import VoicePacketCortex


class FreshTurnSuccessorTests(unittest.TestCase):
    """F2-WP-719 bounded FRESH1-FRESH10 repository discriminator.

    F15/F16/F17 remain an upstream prerequisite and are intentionally not
    duplicated here.  These tests exercise only the successor-composition
    boundary after one exact validated reentry receipt exists.
    """

    def predecessor(
        self,
        *,
        include_gwt: bool = True,
        include_memory: bool = True,
        output_text: str = "heard predecessor output",
        tool_ref_disposition: str = "REFERENCE_ONLY_NO_TOOL_OR_EFFECT_REPLAY",
    ):
        root = CausalIdentity(
            session_id="session-wp719",
            agent_id="frankenstein-2",
            task_id="task-wp719",
            turn_id="turn-input",
            causal_id="causal-input-wp719",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="fixture:wp719-predecessor",
            input_sha256="1" * 64,
            provenance_refs=("test:wp719-intent",),
        )
        session = VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp719", generation=4, turn_id="turn-session"
            ),
            provenance_refs=("test:wp719-session",),
        )
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-voice",
            packet_id="output-0",
            monotonic_ms=10,
            text_segment=output_text,
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

        memory_event = None
        memory_bindings = ()
        if include_memory:
            state = create_memory(
                memory_id="memory:wp719-heard-result",
                payload_ref=heard.payload_ref,
                payload_sha256=heard.payload_sha256,
                provenance_refs=("test:wp719-memory-source",),
            )
            record = create_typed_memory(
                state=state,
                memory_kind=KIND_FACT,
                refs={"evidence": ("voice:heard-result",)},
            )
            memory_event = cortex.emit_intent(
                turn_id="turn-memory",
                monotonic_ms=120,
                voice_intent="WAIT",
                memory_refs=(state.memory_id,),
            )
            memory_bindings = ((state, record),)

        gwt_event = None
        gwt_binding = None
        if include_gwt:
            gwt_binding = GwtReentryUptakeBinding(
                binding_id="gwt-binding:wp719",
                canonical_reentry_key="2" * 64,
                reentry_witness_sha256="3" * 64,
                uptake_receipt_id="uptake-receipt:wp719",
                uptake_receipt_sha256="4" * 64,
                broadcast_id="broadcast:wp719",
                broadcast_generation=1,
                broadcast_sha256="5" * 64,
                recipient_cell_id="cell:wp719",
                delivery_status="DELIVERED",
                uptake_status="NOT_UPTAKEN",
                downstream_ref=None,
                downstream_sha256=None,
                binding_status="WP507_NOT_UPTAKEN_BOUND",
                provenance_refs=("test:gwt-binding",),
            )
            gwt_event = cortex.emit_intent(
                turn_id="turn-gwt",
                monotonic_ms=130,
                voice_intent="WAIT",
                gwt_ref=gwt_binding.binding_id,
            )

        outcome = cortex.close_session(
            turn_id="turn-voice",
            monotonic_ms=200,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-wp719", generation=5, turn_id="turn-outcome"
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
            provenance_refs=("test:wp719-outcome",),
        )
        close_event = cortex.events[-1]
        receipt = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            memory_event=memory_event,
            memory_bindings=memory_bindings,
            gwt_event=gwt_event,
            gwt_binding=gwt_binding,
            tool_ref_disposition=tool_ref_disposition,
            provenance_refs=("test:wp719-reentry",),
        )
        return session, receipt

    def project(self, session, receipt, *, existing=None, input_sha256="8" * 64):
        fresh_intent_causal = session.session_causal_identity.derive(
            causal_id="causal-fresh-intent-wp719",
            generation=session.session_causal_identity.generation + 1,
            turn_id="turn-fresh",
        )
        fresh_session_causal = fresh_intent_causal.derive(
            causal_id="causal-fresh-session-wp719",
            generation=fresh_intent_causal.generation + 1,
            turn_id="turn-fresh",
        )
        return project_fresh_turn(
            predecessor_session=session,
            predecessor_reentry=receipt,
            predecessor_reentry_sha256=receipt.sha256(),
            fresh_intent_causal_identity=fresh_intent_causal,
            fresh_session_causal_identity=fresh_session_causal,
            input_ref="fixture:wp719-fresh-input",
            input_sha256=input_sha256,
            expected_gwt_binding_id=receipt.gwt_binding_id,
            expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
            expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            provenance_refs=("test:wp719-fresh",),
            existing=existing,
        )

    def test_fresh1_valid_exact_gwt_memory_reentry_creates_distinct_bounded_successor(self) -> None:
        session, receipt = self.predecessor()
        intent, successor, projection = self.project(session, receipt)
        self.assertNotEqual(successor.voice_session_id, session.voice_session_id)
        self.assertNotEqual(intent.causal_identity.turn_id, session.session_causal_identity.turn_id)
        self.assertEqual(projection.predecessor_reentry_receipt_id, receipt.receipt_id)
        self.assertEqual(projection.gwt_binding_id, receipt.gwt_binding_id)
        self.assertEqual(projection.memory_evidence_sha256, memory_evidence_sha256(receipt))
        evidence = projection.identity_payload()
        for field in (
            "canonical_memory_write_credit",
            "gwt_runtime_credit",
            "jspace_runtime_credit",
            "effect_credit",
            "asr_runtime_credit",
            "tts_runtime_credit",
            "physical_audio_credit",
            "whole_voice_e2e_credit",
            "training_credit",
        ):
            self.assertEqual(evidence[field], 0)
        self.assertFalse(evidence["whole_system_acceptance"])

    def test_fresh2_stale_or_foreign_gwt_lineage_fails_closed(self) -> None:
        session, receipt = self.predecessor()
        fresh = session.session_causal_identity.derive(
            causal_id="causal-fresh-intent-wp719", generation=6, turn_id="turn-fresh"
        )
        with self.assertRaisesRegex(FreshTurnSuccessorError, "stale/foreign GWT"):
            project_fresh_turn(
                predecessor_session=session,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=fresh,
                fresh_session_causal_identity=fresh.derive(
                    causal_id="causal-fresh-session-wp719", generation=7
                ),
                input_ref="fixture:wp719-fresh-input",
                input_sha256="8" * 64,
                expected_gwt_binding_id="gwt-binding:foreign",
                expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
                expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            )

    def test_fresh3_mismatched_memory_relation_fails_closed(self) -> None:
        session, receipt = self.predecessor()
        fresh = session.session_causal_identity.derive(
            causal_id="causal-fresh-intent-wp719", generation=6, turn_id="turn-fresh"
        )
        with self.assertRaisesRegex(FreshTurnSuccessorError, "memory relation evidence digest mismatch"):
            project_fresh_turn(
                predecessor_session=session,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=fresh,
                fresh_session_causal_identity=fresh.derive(
                    causal_id="causal-fresh-session-wp719", generation=7
                ),
                input_ref="fixture:wp719-fresh-input",
                input_sha256="8" * 64,
                expected_gwt_binding_id=receipt.gwt_binding_id,
                expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
                expected_memory_evidence_sha256="f" * 64,
            )

    def test_fresh4_exact_replay_is_idempotent_and_semantic_drift_is_rejected(self) -> None:
        session, receipt = self.predecessor()
        _intent, _successor, first = self.project(session, receipt)
        _intent2, _successor2, replay = self.project(session, receipt, existing=first)
        self.assertIs(replay, first)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "conflicts with exact deterministic replay"):
            self.project(session, receipt, existing=first, input_sha256="9" * 64)

    def test_fresh5_only_validated_receipt_identity_crosses_cancel_unheard_boundary(self) -> None:
        # F15/F16/F17 own interrupted/unheard accounting. WP719 must not copy prior
        # packet text/inventory into the successor, so unheard material cannot be
        # inflated into spoken history at this boundary.
        session, receipt = self.predecessor(output_text="heard-only-material")
        _intent, _successor, projection = self.project(session, receipt)
        serialized = projection.as_dict()
        self.assertNotIn("text_segments", serialized)
        self.assertNotIn("ordered_output_packet_ids", serialized)
        self.assertNotIn("heard_result_ref", serialized)
        self.assertEqual(serialized["predecessor_reentry_receipt_id"], receipt.receipt_id)

    def test_fresh6_backchannel_like_predecessor_does_not_invent_full_assistant_utterance(self) -> None:
        session, receipt = self.predecessor(output_text="mhm")
        _intent, _successor, projection = self.project(session, receipt)
        material = projection.as_dict()
        self.assertNotIn("assistant_text", material)
        self.assertNotIn("speech_act", material)
        self.assertNotIn("output_packet", material)
        self.assertEqual(material["effect_credit"], 0)

    def test_fresh7_restart_before_successor_creation_preserves_exactly_once_projection(self) -> None:
        session, receipt = self.predecessor()
        rebuilt_session = VoiceSessionCapsule.from_mapping(session.as_dict())
        rebuilt_receipt = copy.deepcopy(receipt)
        _intent, _successor, first = self.project(session, receipt)
        _intent2, _successor2, after_restart = self.project(
            rebuilt_session, rebuilt_receipt, existing=first
        )
        self.assertEqual(after_restart.projection_id, first.projection_id)
        self.assertEqual(after_restart.sha256(), first.sha256())

    def test_fresh8_tool_and_memory_refs_remain_reference_only_without_effect_replay(self) -> None:
        session, receipt = self.predecessor(
            tool_ref_disposition="BOUND_REFERENCE_ONLY_NO_TOOL_EFFECT_REPLAY"
        )
        _intent, _successor, projection = self.project(session, receipt)
        material = projection.as_dict()
        self.assertEqual(projection.tool_ref_disposition, receipt.tool_ref_disposition)
        self.assertEqual(material["canonical_memory_write_credit"], 0)
        self.assertEqual(material["effect_credit"], 0)
        self.assertEqual(material["memory_evidence_sha256"], memory_evidence_sha256(receipt))

    def test_fresh9_packet_successor_composition_requires_no_network_or_external_model(self) -> None:
        session, receipt = self.predecessor()
        with patch("socket.socket", side_effect=AssertionError("network access forbidden in FRESH9")):
            _intent, _successor, projection = self.project(session, receipt)
        self.assertEqual(projection.identity_payload()["asr_runtime_credit"], 0)
        self.assertEqual(projection.identity_payload()["tts_runtime_credit"], 0)

    def test_fresh10_missing_or_corrupt_prior_receipt_fails_closed(self) -> None:
        session, receipt = self.predecessor()
        fresh = session.session_causal_identity.derive(
            causal_id="causal-fresh-intent-wp719", generation=6, turn_id="turn-fresh"
        )
        kwargs = dict(
            predecessor_session=session,
            fresh_intent_causal_identity=fresh,
            fresh_session_causal_identity=fresh.derive(
                causal_id="causal-fresh-session-wp719", generation=7
            ),
            input_ref="fixture:wp719-fresh-input",
            input_sha256="8" * 64,
            expected_gwt_binding_id=receipt.gwt_binding_id,
            expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
            expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
        )
        with self.assertRaisesRegex(FreshTurnSuccessorError, "exact VoiceHeardResultReentryReceipt"):
            project_fresh_turn(
                predecessor_reentry=None,  # type: ignore[arg-type]
                predecessor_reentry_sha256=receipt.sha256(),
                **kwargs,
            )
        with self.assertRaisesRegex(FreshTurnSuccessorError, "predecessor reentry digest mismatch"):
            project_fresh_turn(
                predecessor_reentry=receipt,
                predecessor_reentry_sha256="0" * 64,
                **kwargs,
            )


if __name__ == "__main__":
    unittest.main()
