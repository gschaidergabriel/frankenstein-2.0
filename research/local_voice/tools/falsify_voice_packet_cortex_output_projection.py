#!/usr/bin/env python3
"""Trigger-7 discriminator for restored output-sequence projection consistency.

Research/falsifier scope only. No acoustic, target-runtime, physical-device,
semantic GWT/J-Space, effect, training, whole-voice, or whole-product credit.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from typing import Any

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    resume_packet_cortex,
)

SCHEMA = "F2_T7_RECOVERY_OUTPUT_PROJECTION_DIAGNOSTIC/v1"
PROBE_ID = "RBOUND6_OUTPUT_SEQUENCE_PROJECTION_CONSISTENCY"


def digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_session() -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id="session-t7-rbound-output-projection",
        agent_id="frankenstein-2",
        task_id="task-t7-recovery-output-projection",
        turn_id="turn-root",
        causal_id="causal-root-rbound-output-projection",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="trigger7:rbound6:output-sequence-projection",
        input_sha256="7" * 64,
        provenance_refs=("trigger7:rbound6-output-projection-diagnostic",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-session-rbound-output-projection",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger7:rbound6-output-projection-session",),
    )


def probe() -> tuple[bool, str]:
    session = make_session()
    checkpoint = export_packet_cortex_checkpoint(VoicePacketCortex(session))

    # No output packet for turn-ghost exists, therefore this projection has no backing state.
    checkpoint = copy.deepcopy(checkpoint)
    checkpoint["payload"]["last_output_sequence"] = [["turn-ghost", 999]]
    checkpoint["payload_sha256"] = digest(checkpoint["payload"])

    try:
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=1000)
    except VoicePacketCortexError as exc:
        return True, f"resume rejected inconsistent output projection: {type(exc).__name__}: {exc}"

    try:
        resumed.queue_output(
            turn_id="turn-ghost",
            packet_id="fresh-output",
            monotonic_ms=1100,
            text_segment="weiter",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            sequence=0,
        )
    except VoicePacketCortexError as exc:
        return (
            False,
            "resume admitted unbacked last_output_sequence projection and it changed "
            f"subsequent ordering authority: {type(exc).__name__}: {exc}",
        )

    return (
        False,
        "resume admitted unbacked last_output_sequence projection; fresh sequence=0 was accepted",
    )


def main() -> int:
    try:
        fail_closed, detail = probe()
    except Exception as exc:
        fail_closed = False
        detail = f"diagnostic exception {type(exc).__name__}: {exc}"

    report = {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "result": "NO_COUNTEREXAMPLE" if fail_closed else "PRODUCT_NEGATIVE_CANDIDATE",
        "case": {
            "probe_id": PROBE_ID,
            "fail_closed": fail_closed,
            "detail": detail,
        },
        "classification": (
            "Repository-executable deterministic counterexample candidate only; "
            "route reproduced case to Trigger4/current legal mutation owner."
        ),
        "explicit_zero_credit": {
            "acoustic": 0,
            "target_runtime": 0,
            "physical_audio": 0,
            "semantic_gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if fail_closed else 2


if __name__ == "__main__":
    raise SystemExit(main())
