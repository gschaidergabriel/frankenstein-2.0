from __future__ import annotations

import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"
WORKFLOW = ROOT / ".github/workflows/t4-g2-pipewire-monitor-cancel.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_g2_harness_is_valid_python_and_v2_receipt():
    text = _text(HARNESS)
    ast.parse(text)
    assert 'SCHEMA = "T4_G2_PIPEWIRE_S2_PLAYBACK_CANCEL_MONITOR/v2"' in text
    assert 'SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"' in text


def test_h2_inflight_bound_is_required_and_preflight_bound():
    harness = _text(HARNESS)
    launcher = _text(LAUNCHER)
    assert 'ap.add_argument("--max-inflight-ms", type=float, required=True)' in harness
    assert 'default=250.0' not in harness
    assert '"T4_G2_PIPEWIRE_PREFLIGHT_BOUND/v1"' in harness
    assert '"clock.rate"' in launcher
    assert '"clock.quantum"' in launcher
    assert '"max_inflight_quanta": max_inflight_quanta' in launcher
    assert '--preflight-receipt "$G2_PREFLIGHT_RECEIPT"' in launcher
    assert '--max-inflight-ms "$G2_MAX_INFLIGHT_MS"' in launcher
    assert launcher.index('pw-metadata -n settings') < launcher.index('"$G2_VENV/bin/python" "$G2_HARNESS"')


def test_h3_packet_audio_tts_binding_is_explicit_and_exact_byte_bound():
    harness = _text(HARNESS)
    launcher = _text(LAUNCHER)
    assert '"T4_G2_PACKET_AUDIO_BINDING/v1"' in harness
    for token in (
        '"packet_id": packet_id',
        '"output_generation": output_generation',
        '"source_wav_sha256": sha256_file(source)',
        '"source_text_sha256"',
        '"tts_receipt_sha256"',
        '"piper_tts_version"',
        '"tts_model_sha256"',
        '"tts_config_sha256"',
        '"python_version"',
        '"f2_subject_sha"',
    ):
        assert token in harness
    assert '"T4_G2_LOCAL_TTS_BINDING_RECEIPT/v1"' in launcher
    assert "'source_wav_sha256': source_sha" in launcher
    assert "'replacement_wav_sha256': replacement_sha" in launcher


def test_h5_pipewire_sink_and_monitor_are_bound_by_object_serial_to_pw_dump():
    harness = _text(HARNESS)
    assert 'pactl", "-f", "json", "list", "sinks"' in harness
    assert 'pactl", "-f", "json", "list", "sources"' in harness
    assert '"object.serial"' in harness
    assert 'def _pw_dump_by_serial' in harness
    assert 'PIPEWIRE_SINK_MONITOR_SERIAL_COLLISION' in harness
    assert 'def assert_bound_objects_absent' in harness
    assert '"bound_object_serials_absent"' in harness


def test_h1_replacement_generation_uses_distinct_packet_and_positive_monitor_readback():
    harness = _text(HARNESS)
    launcher = _text(LAUNCHER)
    assert 'output-replacement-g2-pipewire' in harness
    assert 'output_generation=2' in harness
    assert 'output_generation=1' in harness
    assert 'positive_replacement_readback' in harness
    assert 'REPLACEMENT_GENERATION_POSITIVE_READBACK_FAILED' in harness
    assert 'playback_state="completed"' in harness
    assert 'heard_fraction=1.0' in harness
    assert 'REPLACEMENT_WAV="$WORK/replacement.wav"' in launcher
    assert "replacement_text =" in launcher


def test_singleton_manual_dispatch_fence_is_preserved():
    workflow = _text(WORKFLOW)
    assert re.search(r"(?m)^on:\n  workflow_dispatch:\s*$", workflow)
    assert "push:" not in workflow.split("permissions:", 1)[0]
    assert "Promotion-bearing runtime is a singleton" in workflow
