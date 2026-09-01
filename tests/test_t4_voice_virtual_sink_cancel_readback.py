import importlib.util
from pathlib import Path
import sys


MODULE = (
    Path(__file__).parents[1]
    / "research"
    / "local_voice"
    / "tools"
    / "t4_voice_virtual_sink_cancel_readback.py"
)
spec = importlib.util.spec_from_file_location("t4_voice_virtual_sink_cancel_readback", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def test_software_loopback_rejects_late_old_generation_and_never_commits_sentinel():
    result = probe.run("software")

    assert result["pass"] is True
    assert result["classification"] == "CANDIDATE_FALSIFIER_VIRTUAL_SINK_ONLY"
    assert result["execution_scope"] == "REPOSITORY_SIMULATION_ONLY"
    assert result["old_generation"] == 1
    assert result["new_generation"] == 2
    assert result["late_old_generation_accepted"] is False
    assert result["stale_chunks_rejected"] == 1
    assert result["old_sentinel_exact_occurrences"] == 0
    assert result["new_sentinel_exact_occurrences"] == 1
    assert result["measured_credit"]["repository_software_reference_credit"] == 1
    assert result["measured_credit"]["candidate_pulse_null_output_consumption_observed"] == 0
    assert result["measured_credit"]["virtual_sink_output_consumption_control"] == 0
    assert result["measured_credit"]["target_vps_virtual_sink_runtime_credit"] == 0

    for key in (
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
        assert result["measured_credit"][key] == 0


def test_pulse_null_pass_is_candidate_observation_not_runtime_credit(monkeypatch):
    class FakePulseNullSink:
        backend_name = "PIPEWIRE_PULSE_NULL_SINK"

        def __init__(self):
            self.played = bytearray()
            self.cancelled = False

        def start(self):
            return None

        def write(self, pcm):
            if self.cancelled:
                raise RuntimeError("write attempted after cancellation")
            self.played.extend(pcm)

        def cancel(self):
            self.cancelled = True

        def reset(self):
            self.cancelled = False

        def readback(self):
            return bytes(self.played)

        def close(self):
            return None

    monkeypatch.setattr(probe, "PulseNullSink", FakePulseNullSink)
    result = probe.run("pulse-null")

    assert result["pass"] is True
    assert result["execution_scope"] == "VPS_VIRTUAL_SINK_IF_EXECUTED_ON_ADMITTED_TARGET"
    assert result["measured_credit"]["repository_software_reference_credit"] == 0
    assert result["measured_credit"]["candidate_pulse_null_output_consumption_observed"] == 1
    assert result["measured_credit"]["virtual_sink_output_consumption_control"] == 0
    assert result["measured_credit"]["target_vps_virtual_sink_runtime_credit"] == 0


def test_generation_fence_is_session_bound_and_monotonic():
    fence = probe.GenerationFence("session-a")
    current = probe.Chunk("session-a", "p1", 1, 0, b"a")
    wrong_session = probe.Chunk("session-b", "p2", 1, 0, b"b")

    assert fence.admit(current) is True
    assert fence.admit(wrong_session) is False
    old, new = fence.cancel()
    assert (old, new) == (1, 2)
    assert fence.admit(current) is False
    assert fence.admit(probe.Chunk("session-a", "p3", 2, 0, b"c")) is True
    assert fence.rejected == 2


def test_pulse_mode_is_explicitly_virtual_not_physical_credit():
    source = MODULE.read_text(encoding="utf-8")
    assert "PIPEWIRE_PULSE_NULL_SINK" in source
    assert "module-null-sink" in source
    assert '"repository_software_reference_credit"' in source
    assert '"candidate_pulse_null_output_consumption_observed"' in source
    assert '"target_vps_virtual_sink_runtime_credit": 0' in source
    assert '"physical_speaker": 0' in source
    assert '"human_heard_output": 0' in source
    assert '"whole_product": 0' in source
    assert "promote virtual-sink runtime credit only in the external receipt/reconciliation" in source
