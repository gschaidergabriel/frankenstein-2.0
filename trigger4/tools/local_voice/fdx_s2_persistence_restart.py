#!/usr/bin/env python3
"""Bounded S2 VPS persistence/restart discriminator for FDX7 + FDX8.

This executable reuses the existing VoiceSessionCapsule, VoicePacketCortex and
voice_packet_cortex_recovery authorities.  It creates no second packet/state
machine and mints no physical-audio, whole-voice, effect, training or product
credit.

The orchestrator must run inside the admitted Ubuntu 24.04 systemd-nspawn S2
sandbox.  Each case is split across two distinct Python processes sharing only
persisted files, so in-process resume cannot satisfy the restart gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import export_packet_cortex_checkpoint, resume_packet_cortex

SCHEMA = "T4_T7_S2_FDX7_FDX8_PERSISTENCE_RESTART/v1"
CLASSIFICATION = "BOUNDED_S2_VPS_PROCESS_FILESYSTEM_RESTART_EVIDENCE"
SEMANTIC_KEY = "fdx7-fdx8-s2-persistence-restart-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, value: Any) -> str:
    raw = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return sha256_bytes(raw)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def s2_identity() -> dict[str, Any]:
    os_release: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            os_release[k] = v.strip().strip('"')
    marker = Path("/.f2-sandbox-base.json")
    marker_doc = load_json(marker) if marker.exists() else None
    detect = subprocess.run(
        ["systemd-detect-virt", "--container"], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    detected = detect.stdout.strip()
    env_container = os.environ.get("container", "")
    positively_identified = (
        os_release.get("ID") == "ubuntu"
        and os_release.get("VERSION_ID") == "24.04"
        and isinstance(marker_doc, dict)
        and marker_doc.get("schema") == "F2_VPS_SANDBOX_BASE/v1"
        and marker_doc.get("suite") == "noble"
        and (detected == "systemd-nspawn" or env_container == "systemd-nspawn")
    )
    if not positively_identified:
        raise RuntimeError(
            f"S2_IDENTITY_NOT_PROVEN:ubuntu={os_release.get('VERSION_ID')!r}:"
            f"detected={detected!r}:env_container={env_container!r}:marker={marker_doc!r}"
        )
    return {
        "tier": "S2_VPS",
        "ubuntu_version": os_release.get("VERSION_ID"),
        "virt_detected": detected,
        "container_env": env_container,
        "base_marker": marker_doc,
        "positively_identified": True,
    }


def make_session(case: str) -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id=f"session-t4-t7-{case}",
        agent_id="frankenstein-2",
        task_id=f"task-t4-t7-{case}",
        turn_id="turn-root",
        causal_id=f"causal-t4-t7-{case}-root",
        generation=1,
    )
    input_hash = hashlib.sha256(f"trigger4:{case}:s2".encode()).hexdigest()
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref=f"trigger4:{case}:s2",
        input_sha256=input_hash,
        provenance_refs=(f"trigger4:{case}:s2",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-t4-t7-{case}-session",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=(f"trigger4:{case}:s2:session",),
    )


def final_input(session: VoiceSessionCapsule, *, case: str, turn: str, monotonic_ms: int) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=session.voice_session_id,
        turn_id=turn,
        packet_id=f"input-{case}-0",
        monotonic_ms=monotonic_ms,
        source_modality="transcript_fixture",
        text=f"Persisted final input for {case}",
        language="de",
        is_final=True,
        confidence=1.0,
        speech_start=True,
        speech_end=True,
        vad_state="SILENCE",
        endpoint_decision="END",
        overlap_state="NONE",
        barge_in=False,
        source_duration_ms=monotonic_ms,
        sequence=0,
    )


def phase_prepare7(root: Path) -> None:
    case = "fdx7"
    session = make_session(case)
    cortex = VoicePacketCortex(session, opened_monotonic_ms=0)
    inp = final_input(session, case=case, turn="turn-7", monotonic_ms=10)
    cortex.accept_input(inp)
    cortex.queue_output(
        turn_id="turn-7", packet_id="output-fdx7-0", monotonic_ms=20,
        text_segment="Dieser Output ist beim Prozessneustart noch nicht abgeschlossen.",
        expression_intent="neutral", speech_act="ANSWER", planned_audio_duration_ms=5000,
        sequence=0,
    )
    cortex.advance_output("output-fdx7-0", playback_state="started", monotonic_ms=30, heard_fraction=0.0)
    cortex.advance_output("output-fdx7-0", playback_state="heard", monotonic_ms=40, heard_fraction=0.25)
    checkpoint = export_packet_cortex_checkpoint(cortex)
    session_path = root / case / "session.json"
    checkpoint_path = root / case / "checkpoint.json"
    session_file_sha = atomic_json(session_path, session.as_dict())
    checkpoint_file_sha = atomic_json(checkpoint_path, checkpoint)
    atomic_json(root / case / "phase_a.json", {
        "pid": os.getpid(),
        "session_id": session.voice_session_id,
        "session_sha256": session.sha256(),
        "turn_id": "turn-7",
        "input_packet_id": inp.packet_id,
        "input_packet_sha256": inp.sha256(),
        "output_packet_ids": [p.packet_id for p in cortex.outputs],
        "output_sequences": [p.sequence for p in cortex.outputs],
        "commit_eligible_output_ids": [p.packet_id for p in cortex.outputs if p.commit_eligible],
        "checkpoint_payload_sha256": checkpoint["payload_sha256"],
        "checkpoint_file_sha256": checkpoint_file_sha,
        "session_file_sha256": session_file_sha,
        "is_open": cortex.is_open,
    })


def phase_resume7(root: Path) -> None:
    case = "fdx7"
    phase_a = load_json(root / case / "phase_a.json")
    session = VoiceSessionCapsule.from_mapping(load_json(root / case / "session.json"))
    checkpoint_path = root / case / "checkpoint.json"
    checkpoint_file_sha_before = file_sha(checkpoint_path)
    checkpoint = load_json(checkpoint_path)
    if checkpoint_file_sha_before != phase_a["checkpoint_file_sha256"]:
        raise AssertionError("FDX7 persisted checkpoint bytes changed across process boundary")
    if session.sha256() != phase_a["session_sha256"] or session.voice_session_id != phase_a["session_id"]:
        raise AssertionError("FDX7 session identity changed across process boundary")

    cortex = resume_packet_cortex(session, checkpoint, monotonic_ms=50)
    restored = {p.packet_id: p for p in cortex.outputs}
    old = restored.get("output-fdx7-0")
    if old is None or old.playback_state != "interrupted" or old.commit_eligible or old.voiceoutcome_ref is not None:
        raise AssertionError("FDX7 nonterminal pre-restart output retained answer authority")
    restart_events = [e for e in cortex.events if e.event_kind == "RESTART_REENTRY"]
    if len(restart_events) != 1 or restart_events[0].packet_refs != ("output-fdx7-0",):
        raise AssertionError("FDX7 restart reentry did not bind exact pre-restart output")

    replay = final_input(session, case=case, turn="turn-7", monotonic_ms=10)
    cortex.accept_input(replay)
    checkpoint_after_replay = export_packet_cortex_checkpoint(cortex)
    if len(checkpoint_after_replay["payload"]["input_seen"]) != 1:
        raise AssertionError("FDX7 exact input replay duplicated admitted input authority")

    cortex.queue_output(
        turn_id="turn-7", packet_id="output-fdx7-1", monotonic_ms=60,
        text_segment="Nach dem Prozessneustart wird die bestehende Turn-Lineage fortgesetzt.",
        expression_intent="neutral", speech_act="ANSWER", planned_audio_duration_ms=1000,
        sequence=1,
    )
    cortex.advance_output("output-fdx7-1", playback_state="started", monotonic_ms=70, heard_fraction=0.0)
    cortex.advance_output("output-fdx7-1", playback_state="completed", monotonic_ms=80, heard_fraction=1.0)
    outputs = list(cortex.outputs)
    ids = [p.packet_id for p in outputs]
    sequences = [p.sequence for p in outputs if p.turn_id == "turn-7"]
    commit_ids = [p.packet_id for p in outputs if p.commit_eligible]
    if len(ids) != len(set(ids)) or sequences != [0, 1] or commit_ids != ["output-fdx7-1"]:
        raise AssertionError("FDX7 restart created duplicate sequence or second answer authority")
    final_checkpoint = export_packet_cortex_checkpoint(cortex)
    final_sha = atomic_json(root / case / "checkpoint_after_restart.json", final_checkpoint)
    atomic_json(root / case / "result.json", {
        "pass": True,
        "phase_a_pid": phase_a["pid"],
        "phase_b_pid": os.getpid(),
        "distinct_processes": phase_a["pid"] != os.getpid(),
        "session_id_preserved": session.voice_session_id == phase_a["session_id"],
        "session_sha256_preserved": session.sha256() == phase_a["session_sha256"],
        "pre_restart_checkpoint_file_sha256": checkpoint_file_sha_before,
        "pre_restart_checkpoint_payload_sha256": checkpoint["payload_sha256"],
        "post_restart_checkpoint_file_sha256": final_sha,
        "restart_reentry_event_count": len(restart_events),
        "restart_terminalized_packet_refs": list(restart_events[0].packet_refs),
        "old_output_terminal_state": old.playback_state,
        "old_output_commit_eligible": old.commit_eligible,
        "admitted_input_count_after_exact_replay": len(checkpoint_after_replay["payload"]["input_seen"]),
        "output_packet_ids": ids,
        "turn_output_sequences": sequences,
        "commit_eligible_output_ids": commit_ids,
        "duplicate_output_id_count": len(ids) - len(set(ids)),
        "second_answer_authority_count": max(0, len(commit_ids) - 1),
    })


def fdx8_close_args(session: VoiceSessionCapsule) -> dict[str, Any]:
    return {
        "turn_id": "turn-8",
        "monotonic_ms": 50,
        "outcome_causal_identity": session.session_causal_identity.derive(
            causal_id="causal-t4-t7-fdx8-outcome", generation=3, turn_id="turn-8"
        ),
        "outcome_kind": "RETURNED",
        "result_ref": "result:fdx8:s2",
        "result_sha256": hashlib.sha256(b"fdx8-s2-result").hexdigest(),
        "provenance_refs": ("trigger4:fdx8:s2",),
    }


def phase_prepare8(root: Path) -> None:
    case = "fdx8"
    session = make_session(case)
    cortex = VoicePacketCortex(session, opened_monotonic_ms=0)
    inp = final_input(session, case=case, turn="turn-8", monotonic_ms=10)
    cortex.accept_input(inp)
    cortex.queue_output(
        turn_id="turn-8", packet_id="output-fdx8-0", monotonic_ms=20,
        text_segment="Dieser vollständig gehörte Output besitzt genau eine terminale Outcome-Bindung.",
        expression_intent="neutral", speech_act="ANSWER", planned_audio_duration_ms=1000,
        sequence=0,
    )
    cortex.advance_output("output-fdx8-0", playback_state="started", monotonic_ms=30, heard_fraction=0.0)
    cortex.advance_output("output-fdx8-0", playback_state="completed", monotonic_ms=40, heard_fraction=1.0)
    outcome = cortex.close_session(**fdx8_close_args(session))
    checkpoint = export_packet_cortex_checkpoint(cortex)
    session_path = root / case / "session.json"
    checkpoint_path = root / case / "checkpoint.json"
    session_file_sha = atomic_json(session_path, session.as_dict())
    checkpoint_file_sha = atomic_json(checkpoint_path, checkpoint)
    close_events = [e for e in cortex.events if e.event_kind == "SESSION_CLOSE"]
    commit_ids = [p.packet_id for p in cortex.outputs if p.commit_eligible]
    atomic_json(root / case / "phase_a.json", {
        "pid": os.getpid(),
        "session_id": session.voice_session_id,
        "session_sha256": session.sha256(),
        "session_file_sha256": session_file_sha,
        "checkpoint_payload_sha256": checkpoint["payload_sha256"],
        "checkpoint_file_sha256": checkpoint_file_sha,
        "outcome": outcome.as_dict(),
        "outcome_sha256": outcome.sha256(),
        "commit_eligible_output_ids": commit_ids,
        "session_close_event_ids": [e.event_id for e in close_events],
        "session_close_event_count": len(close_events),
        "is_open": cortex.is_open,
    })


def phase_resume8(root: Path) -> None:
    case = "fdx8"
    phase_a = load_json(root / case / "phase_a.json")
    session = VoiceSessionCapsule.from_mapping(load_json(root / case / "session.json"))
    checkpoint_path = root / case / "checkpoint.json"
    before_file_sha = file_sha(checkpoint_path)
    checkpoint = load_json(checkpoint_path)
    if before_file_sha != phase_a["checkpoint_file_sha256"]:
        raise AssertionError("FDX8 persisted checkpoint bytes changed across process boundary")
    cortex = resume_packet_cortex(session, checkpoint, monotonic_ms=80)
    if cortex.is_open:
        raise AssertionError("FDX8 closed session reopened after restart")
    close_before = [e for e in cortex.events if e.event_kind == "SESSION_CLOSE"]
    if len(close_before) != 1 or [e.event_id for e in close_before] != phase_a["session_close_event_ids"]:
        raise AssertionError("FDX8 SESSION_CLOSE identity/count changed on restore")
    restored_checkpoint = export_packet_cortex_checkpoint(cortex)
    restored_file_sha = sha256_bytes(canonical_bytes(restored_checkpoint))
    if restored_checkpoint["payload_sha256"] != phase_a["checkpoint_payload_sha256"] or restored_file_sha != before_file_sha:
        raise AssertionError("FDX8 closed checkpoint is not identity-idempotent on readback")

    replay_outcome = cortex.close_session(**fdx8_close_args(session))
    after_replay = export_packet_cortex_checkpoint(cortex)
    close_after = [e for e in cortex.events if e.event_kind == "SESSION_CLOSE"]
    commit_ids = [p.packet_id for p in cortex.outputs if p.commit_eligible]
    if replay_outcome.as_dict() != phase_a["outcome"] or replay_outcome.sha256() != phase_a["outcome_sha256"]:
        raise AssertionError("FDX8 exact close replay minted a different VoiceOutcome")
    if len(close_after) != 1 or [e.event_id for e in close_after] != phase_a["session_close_event_ids"]:
        raise AssertionError("FDX8 exact close replay duplicated SESSION_CLOSE authority")
    if commit_ids != phase_a["commit_eligible_output_ids"]:
        raise AssertionError("FDX8 commit-eligible output identity changed after restart/replay")
    after_file_sha = sha256_bytes(canonical_bytes(after_replay))
    if after_file_sha != before_file_sha:
        raise AssertionError("FDX8 idempotent close replay changed durable checkpoint identity")
    closed_write_rejected = False
    try:
        cortex.queue_output(
            turn_id="turn-8", packet_id="output-fdx8-illegal", monotonic_ms=90,
            text_segment="must reject", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=1, sequence=1,
        )
    except VoicePacketCortexError:
        closed_write_rejected = True
    if not closed_write_rejected:
        raise AssertionError("FDX8 closed session accepted new output authority")
    atomic_json(root / case / "result.json", {
        "pass": True,
        "phase_a_pid": phase_a["pid"],
        "phase_b_pid": os.getpid(),
        "distinct_processes": phase_a["pid"] != os.getpid(),
        "session_id_preserved": session.voice_session_id == phase_a["session_id"],
        "session_sha256_preserved": session.sha256() == phase_a["session_sha256"],
        "pre_restart_checkpoint_file_sha256": before_file_sha,
        "post_restart_loaded_checkpoint_file_sha256": restored_file_sha,
        "post_replay_checkpoint_file_sha256": after_file_sha,
        "checkpoint_payload_sha256": after_replay["payload_sha256"],
        "outcome_id": replay_outcome.outcome_id,
        "outcome_sha256": replay_outcome.sha256(),
        "commit_eligible_output_ids": commit_ids,
        "session_close_event_ids": [e.event_id for e in close_after],
        "session_close_event_count": len(close_after),
        "duplicate_session_close_count": max(0, len(close_after) - 1),
        "duplicate_durable_result_output_count": 0,
        "closed_state_preserved": not cortex.is_open,
        "closed_write_rejected": closed_write_rejected,
    })


def child(phase: str, root: Path) -> int:
    s2_identity()
    dispatch = {
        "prepare7": phase_prepare7,
        "resume7": phase_resume7,
        "prepare8": phase_prepare8,
        "resume8": phase_resume8,
    }
    dispatch[phase](root)
    return 0


def run_orchestrator(root: Path) -> dict[str, Any]:
    identity = s2_identity()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=False)
    phases = []
    for phase in ("prepare7", "resume7", "prepare8", "resume8"):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--phase", phase, "--state-root", str(root)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        phases.append({
            "phase": phase,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        })
        if proc.returncode != 0:
            raise RuntimeError(f"PHASE_FAILED:{phase}:rc={proc.returncode}:stderr={proc.stderr[-2000:]}")
    fdx7 = load_json(root / "fdx7" / "result.json")
    fdx8 = load_json(root / "fdx8" / "result.json")
    if not fdx7.get("distinct_processes") or not fdx8.get("distinct_processes"):
        raise AssertionError("restart discriminator reused same process")
    return {
        "schema": SCHEMA,
        "semantic_key": SEMANTIC_KEY,
        "result": "NO_COUNTEREXAMPLE",
        "classification": CLASSIFICATION,
        "source": {
            "f2_subject_sha": os.environ.get("F2_SUBJECT_SHA", "UNBOUND"),
            "tool_path": "trigger4/tools/local_voice/fdx_s2_persistence_restart.py",
        },
        "sandbox": identity,
        "process_phases": phases,
        "cases": {
            "FDX7_RESTART_MID_OPEN_TURN": fdx7,
            "FDX8_CLOSED_RESTART_IDEMPOTENCE": fdx8,
        },
        "explicit_zero_credit": {
            "acoustic_asr": 0,
            "tts_synthesis": 0,
            "physical_microphone": 0,
            "physical_speaker": 0,
            "physical_presence": 0,
            "human_heard_output": 0,
            "physical_cancellation_to_silence": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
        "credit_boundary": {
            "fdx7_s2_process_filesystem_restart_candidate": 1,
            "fdx8_s2_closed_restart_idempotence_candidate": 1,
            "s3_kernel_reboot": 0,
            "s4_physical_local": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("orchestrate", "prepare7", "resume7", "prepare8", "resume8"), default="orchestrate")
    parser.add_argument("--state-root", type=Path, default=Path("/var/tmp/t4-fdx-s2-state"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.phase != "orchestrate":
        return child(args.phase, args.state_root)
    try:
        receipt = run_orchestrator(args.state_root)
        rc = 0
    except Exception as exc:
        receipt = {
            "schema": SCHEMA,
            "semantic_key": SEMANTIC_KEY,
            "result": "COUNTEREXAMPLE_OR_EXECUTION_DEFECT_REQUIRES_TRIAGE",
            "failure_class": "PRODUCT_NEGATIVE_OR_EVIDENCE_VALIDITY_REQUIRES_REVIEW",
            "error": f"{type(exc).__name__}:{exc}",
            "source": {"f2_subject_sha": os.environ.get("F2_SUBJECT_SHA", "UNBOUND")},
            "explicit_zero_credit": {
                "fdx7_s2_process_filesystem_restart": 0,
                "fdx8_s2_closed_restart_idempotence": 0,
                "whole_voice_e2e": 0,
                "whole_product": 0,
            },
        }
        rc = 2
    raw = canonical_bytes(receipt)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    print("T4_FDX_S2_RECEIPT_B64=" + __import__("base64").b64encode(raw).decode("ascii"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
