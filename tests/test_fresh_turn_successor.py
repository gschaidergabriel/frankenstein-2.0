from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.fresh_turn_successor import (
    FreshTurnSuccessorError,
    memory_evidence_sha256,
    project_fresh_turn,
)
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import bind_completed_reentry, build_heard_result
from frankenstein2.voice_packet_cortex import VoicePacketCortex


class FreshTurnSuccessorTests(unittest.TestCase):
    def predecessor(self, suffix: str = "a"):
        root = CausalIdentity(
            session_id=f"session-wp719-{suffix}",
            agent_id="frankenstein-2",
            task_id="task-wp719",
            turn_id=f"turn-input-{suffix}",
            causal_id=f"causal-input-wp719-{suffix}",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref=f"fixture:wp719:{suffix}",
            input_sha256="1" * 64,
            provenance_refs=(f"test:wp719:{suffix}",),
        )
        session = VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id=f"causal-session-wp719-{suffix}",
                generation=4,
                turn_id=f"turn-session-{suffix}",
            ),
            provenance_refs=(f"test:wp719-session:{suffix}",),
        )
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id=f"turn-voice-{suffix}",
            packet_id=f"output-{suffix}",
            monotonic_ms=10,
            text_segment="vollstaendig gehoert",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            sequence=0,
        )
        cortex.advance_output(
            f"output-{suffix}", playback_state="started", monotonic_ms=11, heard_fraction=0.0
        )
        cortex.advance_output(
            f"output-{suffix}", playback_state="completed", monotonic_ms=111, heard_fraction=1.0
        )
        heard = build_heard_result(session=session, output_packets=cortex.outputs)
        outcome = cortex.close_session(
            turn_id=f"turn-voice-{suffix}",
            monotonic_ms=130,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id=f"causal-outcome-wp719-{suffix}",
                generation=5,
                turn_id=f"turn-outcome-{suffix}",
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
            provenance_refs=(f"test:wp719-outcome:{suffix}",),
        )
        receipt = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=cortex.events[-1],
            provenance_refs=(f"test:wp719-reentry:{suffix}",),
        )
        return session, receipt

    def fresh_causals(self, predecessor: VoiceSessionCapsule, suffix: str = "1"):
        fresh_intent = predecessor.session_causal_identity.derive(
            causal_id=f"causal-fresh-intent-{suffix}",
            generation=predecessor.session_causal_identity.generation + 1,
            turn_id=f"turn-fresh-{suffix}",
        )
        fresh_session = fresh_intent.derive(
            causal_id=f"causal-fresh-session-{suffix}",
            generation=fresh_intent.generation + 1,
            turn_id=f"turn-fresh-session-{suffix}",
        )
        return fresh_intent, fresh_session

    def project(self, predecessor, receipt, *, suffix: str = "1", input_sha256: str = "2" * 64, existing=None):
        fresh_intent, fresh_session = self.fresh_causals(predecessor, suffix)
        return project_fresh_turn(
            predecessor_session=predecessor,
            predecessor_reentry=receipt,
            predecessor_reentry_sha256=receipt.sha256(),
            fresh_intent_causal_identity=fresh_intent,
            fresh_session_causal_identity=fresh_session,
            input_ref=f"voice-input:fresh:{suffix}",
            input_sha256=input_sha256,
            expected_gwt_binding_id=receipt.gwt_binding_id,
            expected_gwt_binding_sha256=receipt.gwt_binding_sha256,
            expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            provenance_refs=("test:F2-WP-719",),
            existing=existing,
        )

    def test_fresh1_exact_predecessor_creates_distinct_successor(self) -> None:
        predecessor, receipt = self.predecessor()
        intent, session, projection = self.project(predecessor, receipt)
        self.assertNotEqual(session.voice_session_id, predecessor.voice_session_id)
        self.assertEqual(projection.predecessor_conversation_id, predecessor.voice_session_id)
        self.assertEqual(projection.fresh_conversation_id, session.voice_session_id)
        self.assertEqual(projection.fresh_intent_id, intent.intent_id)
        self.assertEqual(projection.predecessor_reentry_receipt_id, receipt.receipt_id)

    def test_fresh2_same_exact_request_is_deterministic(self) -> None:
        predecessor, receipt = self.predecessor()
        first = self.project(predecessor, receipt)
        second = self.project(predecessor, receipt)
        self.assertEqual(first, second)
        self.assertEqual(first[2].sha256(), second[2].sha256())

    def test_fresh3_existing_exact_projection_is_idempotent(self) -> None:
        predecessor, receipt = self.predecessor()
        intent1, session1, projection1 = self.project(predecessor, receipt)
        intent2, session2, projection2 = self.project(predecessor, receipt, existing=projection1)
        self.assertEqual(intent1, intent2)
        self.assertEqual(session1, session2)
        self.assertIs(projection2, projection1)

    def test_fresh4_existing_projection_rejects_semantic_drift(self) -> None:
        predecessor, receipt = self.predecessor()
        _intent, _session, projection = self.project(predecessor, receipt)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "conflicts"):
            self.project(predecessor, receipt, input_sha256="3" * 64, existing=projection)

    def test_fresh5_stale_or_wrong_reentry_digest_fails_closed(self) -> None:
        predecessor, receipt = self.predecessor()
        fresh_intent, fresh_session = self.fresh_causals(predecessor)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "digest mismatch"):
            project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256="f" * 64,
                fresh_intent_causal_identity=fresh_intent,
                fresh_session_causal_identity=fresh_session,
                input_ref="voice-input:fresh:wrong-digest",
                input_sha256="2" * 64,
                expected_gwt_binding_id=None,
                expected_gwt_binding_sha256=None,
                expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            )

    def test_fresh6_foreign_receipt_cannot_bind_predecessor_session(self) -> None:
        predecessor_a, _receipt_a = self.predecessor("a")
        _predecessor_b, receipt_b = self.predecessor("b")
        fresh_intent, fresh_session = self.fresh_causals(predecessor_a)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "not bound to exact predecessor"):
            project_fresh_turn(
                predecessor_session=predecessor_a,
                predecessor_reentry=receipt_b,
                predecessor_reentry_sha256=receipt_b.sha256(),
                fresh_intent_causal_identity=fresh_intent,
                fresh_session_causal_identity=fresh_session,
                input_ref="voice-input:fresh:foreign",
                input_sha256="2" * 64,
                expected_gwt_binding_id=None,
                expected_gwt_binding_sha256=None,
                expected_memory_evidence_sha256=memory_evidence_sha256(receipt_b),
            )

    def test_fresh7_cannot_invent_gwt_lineage_absent_from_predecessor(self) -> None:
        predecessor, receipt = self.predecessor()
        fresh_intent, fresh_session = self.fresh_causals(predecessor)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "invents GWT lineage"):
            project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=fresh_intent,
                fresh_session_causal_identity=fresh_session,
                input_ref="voice-input:fresh:gwt-invention",
                input_sha256="2" * 64,
                expected_gwt_binding_id="gwt:invented",
                expected_gwt_binding_sha256="a" * 64,
                expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            )

    def test_fresh8_memory_relation_digest_mismatch_fails_closed(self) -> None:
        predecessor, receipt = self.predecessor()
        fresh_intent, fresh_session = self.fresh_causals(predecessor)
        with self.assertRaisesRegex(FreshTurnSuccessorError, "memory relation evidence digest mismatch"):
            project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=fresh_intent,
                fresh_session_causal_identity=fresh_session,
                input_ref="voice-input:fresh:memory-mismatch",
                input_sha256="2" * 64,
                expected_gwt_binding_id=None,
                expected_gwt_binding_sha256=None,
                expected_memory_evidence_sha256="9" * 64,
            )

    def test_fresh9_fresh_intent_requires_exact_predecessor_causal_parent(self) -> None:
        predecessor, receipt = self.predecessor()
        parent = predecessor.session_causal_identity
        wrong_intent = CausalIdentity(
            session_id=parent.session_id,
            agent_id=parent.agent_id,
            task_id=parent.task_id,
            turn_id="turn-fresh-wrong-parent",
            causal_id="causal-fresh-wrong-parent",
            generation=parent.generation + 1,
            parent_causal_id="causal-not-the-predecessor",
        )
        wrong_session = wrong_intent.derive(
            causal_id="causal-fresh-session-wrong-parent",
            generation=wrong_intent.generation + 1,
            turn_id="turn-fresh-session-wrong-parent",
        )
        with self.assertRaisesRegex(FreshTurnSuccessorError, "causal parent"):
            project_fresh_turn(
                predecessor_session=predecessor,
                predecessor_reentry=receipt,
                predecessor_reentry_sha256=receipt.sha256(),
                fresh_intent_causal_identity=wrong_intent,
                fresh_session_causal_identity=wrong_session,
                input_ref="voice-input:fresh:wrong-parent",
                input_sha256="2" * 64,
                expected_gwt_binding_id=None,
                expected_gwt_binding_sha256=None,
                expected_memory_evidence_sha256=memory_evidence_sha256(receipt),
            )

    def test_fresh10_projection_mints_no_memory_gwt_effect_audio_or_completion_credit(self) -> None:
        predecessor, receipt = self.predecessor()
        _intent, _session, projection = self.project(predecessor, receipt)
        payload = projection.as_dict()
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
            self.assertEqual(payload[field], 0, field)
        self.assertFalse(payload["whole_system_acceptance"])
        self.assertEqual(projection.tool_ref_disposition, receipt.tool_ref_disposition)
        self.assertIn("predecessor-reentry:" + receipt.receipt_id, projection.provenance_refs)
        self.assertIn("predecessor-session:" + predecessor.voice_session_id, projection.provenance_refs)


if __name__ == "__main__":
    unittest.main()
