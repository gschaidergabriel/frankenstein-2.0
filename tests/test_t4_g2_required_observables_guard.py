#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "trigger4/tools/local_voice/g2_required_observables_guard.py"
OBSERVER_PATH = ROOT / "trigger4/tools/local_voice/g2_pipewire_observer.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = load("g2_required_observables_guard_test", GUARD_PATH)
observer_mod = load("g2_pipewire_observer_test", OBSERVER_PATH)


def node(serial, binary, media_class, first, last):
    return {
        "object_id": int(serial),
        "object_serial": str(serial),
        "node_name": f"{binary}-{serial}",
        "media_class": media_class,
        "media_name": binary,
        "application_name": binary,
        "application_process_binary": binary,
        "application_process_id": str(int(serial) + 1000),
        "target_object": "99",
        "node_target": None,
        "latency_props": {"node.latency": "1024/48000"},
        "first_seen_monotonic_ns": first,
        "last_seen_monotonic_ns": last,
    }


def good_harness():
    return {
        "schema": guard.SCHEMA,
        "semantic_key": guard.SEMANTIC_KEY,
        "result": "NO_COUNTEREXAMPLE",
        "failure_class": None,
        "f2_subject_sha": "a" * 40,
        "source": {
            "wav_sha256": "b" * 64,
            "wav_meta": {"rate": 48000, "channels": 1, "frames": 480000},
            "tts_model_sha256": "c" * 64,
        },
        "pipewire": {
            "pipewire_version": "pipewire 1.0.5",
            "graph_preflight": {
                "pipewire_objects": {
                    "sink": {"object_id": 41, "object_serial": "1001", "node_name": "f2_voice_g2_sink"},
                    "monitor": {"object_id": 42, "object_serial": "1002", "node_name": "f2_voice_g2_sink.monitor"},
                }
            },
        },
        "control": {"playback_started_ns": 1_000_000_000, "playback_terminal_ns": 2_000_000_000},
        "cancel": {
            "voice_output_packet_id": "output-old-g2-pipewire",
            "playback_started_ns": 3_000_000_000,
            "cancel_request_ns": 3_400_000_000,
            "packet_terminal_ns": 3_410_000_000,
            "playback_terminal_ns": 3_500_000_000,
            "commit_eligible": False,
        },
        "replacement": {"playback_started_ns": 5_000_000_000, "playback_terminal_ns": 6_000_000_000},
        "analysis": {
            "files": {
                "control": {"rate": 48000, "channels": 1, "frames": 500000},
                "cancel": {"rate": 48000, "channels": 1, "frames": 300000},
            },
            "alignment": {"control_capture_offset_ms": 12.5},
            "measurement": {
                "last_old_audio_source_timeline_end_ms": 1280.0,
                "observed_cancel_to_last_old_audio_tail_ms": 80.0,
                "post_bound_old_audio_window_count": 0,
                "post_bound_observation_window_count": 25,
                "max_post_bound_correlation": 0.12,
            },
        },
        "cleanup": {
            "run_owned_sink_removed": True,
            "bound_pipewire_object_identities_absent_after": True,
        },
        "measured_credit": {
            "owner_vps_pipewire_virtual_sink_playback_readback": 1,
            "bounded_test_driver_cancel_translation_to_virtual_audio_monitor_silence": 1,
        },
        "explicit_zero_credit": {"whole_product": 0, "physical_speaker": 0},
    }


def good_observer():
    return {
        "nodes": [
            node(11, "parec", "Stream/Input/Audio", 800_000_000, 2_200_000_000),
            node(12, "paplay", "Stream/Output/Audio", 1_050_000_000, 1_950_000_000),
            node(21, "parec", "Stream/Input/Audio", 2_800_000_000, 4_200_000_000),
            node(22, "paplay", "Stream/Output/Audio", 3_050_000_000, 3_490_000_000),
            node(31, "parec", "Stream/Input/Audio", 4_800_000_000, 6_200_000_000),
            node(32, "paplay", "Stream/Output/Audio", 5_050_000_000, 5_950_000_000),
        ],
        "latency_samples": [
            {
                "monotonic_ns": 3_100_000_000,
                "sink": {"name": "f2_voice_g2_sink", "latency_usec": 21000, "configured_latency_usec": 21333},
                "monitor": {"name": "f2_voice_g2_sink.monitor", "latency_usec": 22000, "configured_latency_usec": 21333},
            }
        ],
    }


def good_bound():
    return {"clock_rate_hz": 48000, "clock_quantum_frames": 1024, "policy_quanta": 16, "derived_max_inflight_ms": 341.334}


class Trigger4G2RequiredObservablesGuardTests(unittest.TestCase):
    def test_complete_receipt_binds_every_canonical_required_observable(self):
        receipt = guard.guarded_receipt(good_harness(), good_observer(), good_bound())
        self.assertEqual(receipt["result"], "NO_COUNTEREXAMPLE")
        self.assertTrue(receipt["canonical_required_observables_guard"]["complete"])
        self.assertEqual(receipt["canonical_required_observables_guard"]["missing"], [])
        obs = receipt["required_observables"]
        for name in guard.REQUIRED_NAMES:
            self.assertIn(name, obs)
        self.assertRegex(obs["tts_runtime_binary_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(obs["playback_stream_identity"]["cancel"]["object_serial"], "22")
        self.assertEqual(obs["capture_stream_identity"]["cancel"]["object_serial"], "21")
        self.assertFalse(obs["commit_eligible_after_cancel"])

    def test_missing_reported_latency_fails_closed_and_zeroes_credit(self):
        obs = good_observer()
        obs["latency_samples"] = []
        for row in obs["nodes"]:
            row["latency_props"] = {}
        receipt = guard.guarded_receipt(good_harness(), obs, good_bound())
        self.assertEqual(receipt["result"], "BLOCKED")
        self.assertEqual(receipt["failure_class"], "EVIDENCE_INVALID")
        self.assertIn("guard_exception:ValueError:PIPEWIRE_REPORTED_LATENCY_NOT_OBSERVED", receipt["canonical_required_observables_guard"]["missing"])
        self.assertEqual(set(receipt["measured_credit"].values()), {0})

    def test_ambiguous_cancel_playback_stream_fails_closed(self):
        obs = good_observer()
        obs["nodes"].append(node(23, "paplay", "Stream/Output/Audio", 3_060_000_000, 3_480_000_000))
        receipt = guard.guarded_receipt(good_harness(), obs, good_bound())
        self.assertEqual(receipt["result"], "BLOCKED")
        self.assertIn("STREAM_IDENTITY_AMBIGUOUS:paplay", receipt["canonical_required_observables_guard"]["missing"][0])

    def test_packet_must_remain_non_commit_eligible(self):
        harness = good_harness()
        harness["cancel"]["commit_eligible"] = True
        receipt = guard.guarded_receipt(harness, good_observer(), good_bound())
        self.assertEqual(receipt["result"], "BLOCKED")
        self.assertIn("commit_eligible_after_cancel", receipt["canonical_required_observables_guard"]["missing"])

    def test_observer_parses_pactl_reported_latency(self):
        text = """Sink #41\n\tName: f2_voice_g2_sink\n\tLatency: 21000 usec, configured 21333 usec\n"""
        parsed = observer_mod.parse_pactl_latency(text, "f2_voice_g2_sink", "Sink")
        self.assertEqual(parsed["latency_usec"], 21000)
        self.assertEqual(parsed["configured_latency_usec"], 21333)


if __name__ == "__main__":
    unittest.main()
