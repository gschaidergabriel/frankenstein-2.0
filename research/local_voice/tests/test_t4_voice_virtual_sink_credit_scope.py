import importlib.util
import pathlib
import sys
import unittest


MODULE = pathlib.Path(__file__).resolve().parents[1] / "tools" / "t4_voice_virtual_sink_cancel_readback.py"
spec = importlib.util.spec_from_file_location("t4_voice_virtual_sink_credit_scope_ci", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


class Trigger4VirtualSinkCreditScopeTests(unittest.TestCase):
    def test_software_reference_cannot_mint_virtual_sink_runtime_credit(self):
        result = probe.run("software")
        self.assertTrue(result["pass"])
        self.assertEqual(result["classification"], "CANDIDATE_FALSIFIER_VIRTUAL_SINK_ONLY")
        self.assertEqual(result["execution_scope"], "REPOSITORY_SIMULATION_ONLY")
        self.assertEqual(result["measured_credit"]["repository_software_reference_credit"], 1)
        self.assertEqual(result["measured_credit"]["candidate_pulse_null_output_consumption_observed"], 0)
        self.assertEqual(result["measured_credit"]["virtual_sink_output_consumption_control"], 0)
        self.assertEqual(result["measured_credit"]["target_vps_virtual_sink_runtime_credit"], 0)

    def test_raw_pulse_path_remains_candidate_until_external_identity_binding(self):
        original = probe.PulseNullSink

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

        probe.PulseNullSink = FakePulseNullSink
        try:
            result = probe.run("pulse-null")
        finally:
            probe.PulseNullSink = original

        self.assertTrue(result["pass"])
        self.assertEqual(result["execution_scope"], "VPS_VIRTUAL_SINK_IF_EXECUTED_ON_ADMITTED_TARGET")
        self.assertEqual(result["measured_credit"]["repository_software_reference_credit"], 0)
        self.assertEqual(result["measured_credit"]["candidate_pulse_null_output_consumption_observed"], 1)
        self.assertEqual(result["measured_credit"]["virtual_sink_output_consumption_control"], 0)
        self.assertEqual(result["measured_credit"]["target_vps_virtual_sink_runtime_credit"], 0)

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
            self.assertEqual(result["measured_credit"][key], 0)


if __name__ == "__main__":
    unittest.main()
