#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import tempfile
import time
import types
import unittest
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
HARNESS = ROOT / "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"

for name in (
    "frankenstein2",
    "frankenstein2.causal_identity",
    "frankenstein2.voice_contract",
    "frankenstein2.voice_packet_cortex",
):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["frankenstein2.causal_identity"].CausalIdentity = object
sys.modules["frankenstein2.voice_contract"].VoiceIntent = object
sys.modules["frankenstein2.voice_contract"].VoiceSessionCapsule = object
sys.modules["frankenstein2.voice_packet_cortex"].VoicePacketCortex = object

spec = importlib.util.spec_from_file_location("g2_runtime", HARNESS)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class FakeEvent:
    def __init__(self, packet_id: str):
        self.event_kind = "BARGE_IN_CANCEL_PROPAGATED"
        self.packet_refs = (packet_id,)
        self.event_id = "cortex-event:test:00000004"


class FakeCortex:
    def __init__(self):
        self.events = []


class FakeProc:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class Trigger4G2TerminalRepairTests(unittest.TestCase):
    def test_preflight_bound_is_deterministic_and_graph_bound(self):
        settings = "update: id:0 key:'clock.rate' value:'48000'\nupdate: id:0 key:'clock.quantum' value:'1024'\n"
        bound, receipt = mod.derive_inflight_bound_ms(settings)
        self.assertEqual(bound, 250.0)
        self.assertTrue(receipt["observed_before_playback"])
        self.assertEqual(receipt["clock_rate_hz"], 48000.0)
        self.assertEqual(receipt["clock_quantum_frames"], 1024.0)
        self.assertRegex(receipt["sha256"], r"^[0-9a-f]{64}$")

    def test_preflight_bound_fails_closed_without_rate_or_quantum(self):
        with self.assertRaisesRegex(RuntimeError, "RATE_QUANTUM_NOT_BOUND"):
            mod.derive_inflight_bound_ms("clock.rate = 48000")

    def test_pw_dump_requires_unique_sink_and_monitor_serials(self):
        dump = '''[
          {"id": 41, "type": "PipeWire:Interface:Node", "info": {"props": {"node.name": "f2_voice_g2_sink", "object.serial": "410", "media.class": "Audio/Sink"}}},
          {"id": 42, "type": "PipeWire:Interface:Node", "info": {"props": {"node.name": "f2_voice_g2_sink.monitor", "object.serial": "420", "media.class": "Audio/Source"}}}
        ]'''
        ids = mod.parse_pw_objects(dump, "f2_voice_g2_sink", "f2_voice_g2_sink.monitor")
        self.assertEqual(ids["sink"]["object_serial"], "410")
        self.assertEqual(ids["monitor"]["object_serial"], "420")
        after = '[{"id":99,"info":{"props":{"node.name":"unrelated","object.serial":"999"}}}]'
        self.assertTrue(mod.identities_absent(after, ids))

    def test_pw_dump_missing_serial_is_evidence_invalid(self):
        dump = '''[
          {"id": 41, "info": {"props": {"node.name": "f2_voice_g2_sink"}}},
          {"id": 42, "info": {"props": {"node.name": "f2_voice_g2_sink.monitor", "object.serial": "420"}}}
        ]'''
        with self.assertRaisesRegex(RuntimeError, "OBJECT_SERIAL_MISSING"):
            mod.parse_pw_objects(dump, "f2_voice_g2_sink", "f2_voice_g2_sink.monitor")

    def test_playback_bridge_only_terminates_after_authority_event(self):
        cortex = FakeCortex()
        proc = FakeProc()
        bridge = mod.CancelPlaybackBridge(cortex, "old-packet", proc)
        bridge.start()
        time.sleep(0.03)
        self.assertFalse(proc.terminated)
        cortex.events.append(FakeEvent("old-packet"))
        bridge.wait()
        self.assertTrue(proc.terminated)
        self.assertEqual(bridge.event_id, "cortex-event:test:00000004")
        self.assertFalse(bridge.safety_teardown_used)

    def test_source_has_no_direct_credit_bearing_cancel_kill(self):
        source = HARNESS.read_text(encoding="utf-8")
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn("stop_playback(cancel_play)", source)
        self.assertNotIn("--max-inflight-ms 250", launcher)
        self.assertIn("CancelPlaybackBridge", source)
        self.assertIn("replacement_packet_audio_binding", source)
        self.assertIn("object_serial", source)

    def test_packet_audio_binding_binds_exact_wave_and_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            wav = root / "x.wav"
            txt = root / "x.txt"
            txt.write_text("gebundener text\n", encoding="utf-8")
            with wave.open(str(wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 1600)
            binding = mod.packet_audio_binding(
                packet_id="p1", output_generation=1, wav=wav, text_file=txt,
                tts_model_sha256="a" * 64, tts_config_sha256="b" * 64,
                tts_runtime_version="1.7.0", f2_subject_sha="c" * 40,
            )
            self.assertEqual(binding["packet_id"], "p1")
            self.assertTrue(binding["bound_before_playback"])
            self.assertRegex(binding["wav_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(binding["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
