from __future__ import annotations

import hashlib
import json
from pathlib import Path

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.fresh_turn_successor import memory_evidence_sha256, project_fresh_turn
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    REENTRY_RECEIPT_SCHEMA,
    VoiceHeardResultReentryReceipt,
)


WP901_G6_RECEIPT_REF = (
    "workpackages/receipts/"
    "F2-WP-901_G6_ROLLBACK_LINEAGE_HEAD_TARGET_RUNTIME_33539469356.json"
)


def _digest(value) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _predecessor_and_reentry() -> tuple[VoiceSessionCapsule, VoiceHeardResultReentryReceipt]:
    root = CausalIdentity(
        session_id="session-wp901-wp719-integration",
        agent_id="frankenstein-2",
        task_id="task-wp901-wp719-integration",
        turn_id="turn-predecessor",
        causal_id="causal-predecessor",
        generation=3,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="fixture:wp901-wp719:predecessor",
        input_sha256="1" * 64,
        provenance_refs=("test:wp901-wp719",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-predecessor-session",
            generation=4,
            turn_id="turn-predecessor-session",
        ),
        provenance_refs=("test:wp901-wp719-session",),
    )
    classification = VoiceHeardResultReentryReceipt.__dataclass_fields__["classification"].default
    payload = {
        "schema": REENTRY_RECEIPT_SCHEMA,
        "heard_result_ref": "voice-heard-result:wp901-wp719",
        "heard_result_sha256": "2" * 64,
        "voiceoutcome_id": "voice-outcome:wp901-wp719",
        "voiceoutcome_sha256": "3" * 64,
        "voice_session_id": session.voice_session_id,
        "voice_session_sha256": session.sha256(),
        "close_event_id": "voice-close:wp901-wp719",
        "ordered_output_packet_ids": ["output-wp901-wp719"],
        "context_view_sha256": None,
        "context_item_id": None,
        "context_cost_witness_sha256": None,
        "memory_evidence": [],
        "gwt_binding_id": None,
        "gwt_binding_sha256": None,
        "tool_ref_disposition": "REFERENCE_ONLY_NO_TOOL_OR_EFFECT_REPLAY",
        "provenance_refs": ["test:wp901-wp719-reentry"],
        "classification": classification,
        "canonical_memory_write_credit": 0,
        "gwt_runtime_credit": 0,
        "effect_credit": 0,
        "physical_audio_credit": 0,
        "whole_system_acceptance": False,
    }
    receipt = VoiceHeardResultReentryReceipt(
        receipt_id="voice-reentry-receipt:" + _digest(payload),
        heard_result_ref=payload["heard_result_ref"],
        heard_result_sha256=payload["heard_result_sha256"],
        voiceoutcome_id=payload["voiceoutcome_id"],
        voiceoutcome_sha256=payload["voiceoutcome_sha256"],
        voice_session_id=payload["voice_session_id"],
        voice_session_sha256=payload["voice_session_sha256"],
        close_event_id=payload["close_event_id"],
        ordered_output_packet_ids=tuple(payload["ordered_output_packet_ids"]),
        context_view_sha256=None,
        context_item_id=None,
        context_cost_witness_sha256=None,
        memory_evidence=(),
        gwt_binding_id=None,
        gwt_binding_sha256=None,
        tool_ref_disposition=payload["tool_ref_disposition"],
        provenance_refs=tuple(payload["provenance_refs"]),
    )
    return session, receipt


def test_accepted_wp901_g6_receipt_identity_is_preserved_by_wp719_prerequisite_binding() -> None:
    receipt_path = Path(__file__).resolve().parents[1] / WP901_G6_RECEIPT_REF
    receipt_bytes = receipt_path.read_bytes()
    restart_receipt = json.loads(receipt_bytes)
    restart_sha256 = hashlib.sha256(receipt_bytes).hexdigest()

    assert restart_receipt["workpackage_id"] == "F2-WP-901"
    assert restart_receipt["workpackage_generation"] == 6
    assert restart_receipt["workflow_run_id"] == 33539469356
    assert restart_receipt["workflow_job_id"] == 99961834959
    assert restart_receipt["execution_observed"] is True
    assert restart_receipt["source_identity_verified"] is True
    assert restart_receipt["g6_rollback_lineage_head_target_runtime_credit"] == 1
    assert restart_receipt["whole_system_acceptance"] is False

    predecessor, reentry = _predecessor_and_reentry()
    fresh_intent = predecessor.session_causal_identity.derive(
        causal_id="causal-fresh-intent-wp901-wp719",
        generation=predecessor.session_causal_identity.generation + 1,
        turn_id="turn-fresh-wp901-wp719",
    )
    fresh_session = fresh_intent.derive(
        causal_id="causal-fresh-session-wp901-wp719",
        generation=fresh_intent.generation + 1,
        turn_id="turn-fresh-session-wp901-wp719",
    )

    _intent, _session, projection = project_fresh_turn(
        predecessor_session=predecessor,
        predecessor_reentry=reentry,
        predecessor_reentry_sha256=reentry.sha256(),
        fresh_intent_causal_identity=fresh_intent,
        fresh_session_causal_identity=fresh_session,
        input_ref="voice-input:fresh:wp901-wp719",
        input_sha256="4" * 64,
        expected_gwt_binding_id=None,
        expected_gwt_binding_sha256=None,
        expected_memory_evidence_sha256=memory_evidence_sha256(reentry),
        prerequisite_restart_receipt_ref=WP901_G6_RECEIPT_REF,
        prerequisite_restart_receipt_sha256=restart_sha256,
        provenance_refs=("test:F2-WP-901->F2-WP-719",),
    )

    assert projection.prerequisite_restart_receipt_ref == WP901_G6_RECEIPT_REF
    assert projection.prerequisite_restart_receipt_sha256 == restart_sha256
    projected = projection.as_dict()
    assert projected["canonical_memory_write_credit"] == 0
    assert projected["gwt_runtime_credit"] == 0
    assert projected["jspace_runtime_credit"] == 0
    assert projected["effect_credit"] == 0
    assert projected["whole_system_acceptance"] is False
