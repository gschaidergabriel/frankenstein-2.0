#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "trigger4/tools/local_voice/g2_causal_playback_delivery.py"
HARNESS = ROOT / "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"

spec = importlib.util.spec_from_file_location("g2_causal_playback_delivery", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeEvent:
    def __init__(self, event_id: str, event_kind: str, packet_refs: tuple[str, ...]):
        self.event_id = event_id
        self.event_kind = event_kind
        self.packet_refs = packet_refs


class FakeCortex:
    def __init__(self, *, packet_id: str = "packet-old", wrong_event: bool = False):
        self.packet_id = packet_id
        self.wrong_event = wrong_event
        self.events = (FakeEvent("event:0", "OUTPUT_STARTED", (packet_id,)),)

    def cancel_for_barge_in(self, *, turn_id: str, monotonic_ms: int) -> tuple[str, ...]:
        kind = "WRONG_EVENT" if self.wrong_event else "BARGE_IN_CANCEL_PROPAGATED"
        self.events = self.events + (FakeEvent("event:1", kind, (self.packet_id,)),)
        return (self.packet_id,)


class FakeProc:
    def __init__(self, *, live: bool = True, timeout: bool = False):
        self.pid = 4242
        self._rc = None if live else 0
        self.timeout = timeout
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminate_calls += 1

    def wait(self, timeout=None):
        if self.timeout and self._rc is None:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        self._rc = 0
        return 0

    def kill(self):
        self.kill_calls += 1
        self._rc = -9


class Trigger4G2CausalPlaybackDeliveryTests(unittest.TestCase):
    def test_exact_cortex_cancel_event_causes_bound_playback_termination(self) -> None:
        cortex = FakeCortex()
        proc = FakeProc()
        changed, evidence = module.propagate_barge_in_cancel_to_bound_playback(
            cortex,
            packet_id="packet-old",
            turn_id="turn-b",
            monotonic_ms=123,
            playback_proc=proc,
        )
        self.assertEqual(("packet-old",), changed)
        self.assertEqual(1, proc.terminate_calls)
        self.assertEqual(0, proc.kill_calls)
        self.assertEqual("event:1", evidence["authority_event_id"])
        self.assertEqual("BARGE_IN_CANCEL_PROPAGATED", evidence["authority_event_kind"])
        self.assertEqual("packet-old", evidence["bound_packet_id"])
        self.assertEqual(4242, evidence["bound_playback_pid"])
        self.assertTrue(evidence["pass"])
        self.assertFalse(evidence["independent_test_kill_before_terminalization"])

    def test_wrong_authority_event_fails_before_process_termination(self) -> None:
        cortex = FakeCortex(wrong_event=True)
        proc = FakeProc()
        with self.assertRaisesRegex(RuntimeError, "WRONG_AUTHORITY_EVENT_KIND"):
            module.propagate_barge_in_cancel_to_bound_playback(
                cortex,
                packet_id="packet-old",
                turn_id="turn-b",
                monotonic_ms=123,
                playback_proc=proc,
            )
        self.assertEqual(0, proc.terminate_calls)
        self.assertEqual(0, proc.kill_calls)

    def test_already_terminal_playback_fails_before_product_cancel(self) -> None:
        cortex = FakeCortex()
        proc = FakeProc(live=False)
        before = cortex.events
        with self.assertRaisesRegex(RuntimeError, "PLAYBACK_NOT_LIVE_BEFORE_CANCEL"):
            module.propagate_barge_in_cancel_to_bound_playback(
                cortex,
                packet_id="packet-old",
                turn_id="turn-b",
                monotonic_ms=123,
                playback_proc=proc,
            )
        self.assertEqual(before, cortex.events)
        self.assertEqual(0, proc.terminate_calls)

    def test_sigkill_cleanup_cannot_return_promotion_evidence(self) -> None:
        cortex = FakeCortex()
        proc = FakeProc(timeout=True)
        with self.assertRaisesRegex(AssertionError, "SIGTERM_DID_NOT_TERMINATE"):
            module.propagate_barge_in_cancel_to_bound_playback(
                cortex,
                packet_id="packet-old",
                turn_id="turn-b",
                monotonic_ms=123,
                playback_proc=proc,
            )
        self.assertEqual(1, proc.terminate_calls)
        self.assertEqual(1, proc.kill_calls)

    def test_promotion_window_does_not_directly_call_cleanup_stop(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        causal = text.split('stage = "CAUSAL_CANCEL"', 1)[1].split('stage = "PCM_ANALYSIS"', 1)[0]
        self.assertIn("propagate_barge_in_cancel_to_bound_playback", causal)
        self.assertNotIn("stop_playback(cancel_play)", causal)


if __name__ == "__main__":
    unittest.main()
