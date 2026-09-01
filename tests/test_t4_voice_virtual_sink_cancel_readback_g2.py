import importlib.util
from pathlib import Path
import sys

MODULE = (
    Path(__file__).parents[1]
    / "research" / "local_voice" / "tools"
    / "t4_voice_virtual_sink_cancel_readback_g2.py"
)
spec = importlib.util.spec_from_file_location("t4_voice_virtual_sink_cancel_readback_g2", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def test_reference_queues_old_sentinel_before_cancel_then_proves_it_absent():
    result = probe.run("software")
    assert result["pass"] is True
    assert result["execution_scope"] == "REPOSITORY_REFERENCE_ONLY"
    assert result["old_sentinel_queued_before_cancel"] is True
    assert result["generation_advanced_before_sink_cancel"] is True
    assert result["late_old_generation_accepted"] is False
    assert result["stale_chunks_rejected"] == 1
    assert result["old_sentinel_samples"] == 0
    assert result["new_sentinel_samples"] == result["expected_new_sentinel_samples"]
    assert result["software_discarded_pending_bytes"] > 0


def test_broken_cancel_that_keeps_pending_old_audio_is_product_negative():
    result = probe.run("software", software_cancel_discards_pending=False)
    assert result["pass"] is False
    assert result["failure_class"] == "PRODUCT_NEGATIVE"
    assert result["old_sentinel_queued_before_cancel"] is True
    assert result["old_sentinel_samples"] > 0


def test_generation_fence_is_session_bound_and_monotonic():
    fence = probe.GenerationFence("session-a")
    current = probe.Chunk("session-a", "p1", 1, 0, b"a")
    wrong_session = probe.Chunk("session-b", "p2", 1, 0, b"b")
    assert fence.admit(current) is True
    assert fence.admit(wrong_session) is False
    old, new, advanced_ns = fence.cancel_generation()
    assert (old, new) == (1, 2)
    assert advanced_ns > 0
    assert fence.admit(current) is False
    assert fence.admit(probe.Chunk("session-a", "p3", 2, 0, b"c")) is True
    assert fence.rejected == 2


def test_reference_pass_cannot_mint_runtime_or_adjacent_voice_credit():
    result = probe.run("software")
    assert result["evidence"]["repository_reference_pass"] == 1
    assert result["evidence"]["pulse_virtual_sink_promotion_candidate"] == 0
    for key in (
        "target_runtime_credit_from_probe_alone",
        "producer_generation_cancel",
        "true_streaming_partial_asr",
        "physical_speaker",
        "physical_microphone",
        "human_heard_output",
        "acoustic_playback_readback",
        "whole_voice_e2e",
        "gwt_jspace",
        "effect",
        "unifieddb_write",
        "training",
        "whole_product",
    ):
        assert result["evidence"][key] == 0


def test_pulse_path_is_virtual_sink_only_and_avoids_drain_semantics():
    source = MODULE.read_text(encoding="utf-8")
    assert "PIPEWIRE_PULSE_NULL_SINK" in source
    assert "module-null-sink" in source
    assert "SIGTERM closes" in source
    assert "snd_pcm_drain" not in source
    assert "producer-side TTS cancel" in source
    assert "reserve physical speaker/mic/human-heard for S4" in source
