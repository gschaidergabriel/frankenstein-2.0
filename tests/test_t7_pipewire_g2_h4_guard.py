#!/usr/bin/env python3
"""Regression tests for Trigger-7 G2 H4 discriminative post-bound guard."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import wave

try:
    import numpy  # noqa: F401
except Exception:  # pragma: no cover
    numpy = None

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "research" / "local_voice" / "tools" / "t7_pipewire_g2_h4_guard.py"
MODULE_NAME = "t7_pipewire_g2_h4_guard_test"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, TOOL)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = GUARD
SPEC.loader.exec_module(GUARD)

RATE = 16_000
LEAD = RATE // 10
SOURCE_FRAMES = RATE * 2
CANCEL_MS = 600.0
MAX_INFLIGHT_MS = 80.0
BOUND_MS = CANCEL_MS + MAX_INFLIGHT_MS


def _noise_source() -> list[int]:
    rng = random.Random(0x4847)
    return [rng.randint(-12_000, 12_000) for _ in range(SOURCE_FRAMES)]


def _write(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def _capture(source: list[int], retained_until_ms: float | None) -> list[int]:
    if retained_until_ms is None:
        body = list(source)
    else:
        cutoff = int(round(retained_until_ms * RATE / 1000.0))
        body = list(source[:cutoff]) + [0] * max(0, len(source) - cutoff)
    return [0] * LEAD + body + [0] * (RATE // 2)


def _argv(source: Path, control: Path, cancel: Path, output: Path) -> list[str]:
    return [
        "--source", str(source),
        "--control", str(control),
        "--cancel", str(cancel),
        "--output", str(output),
        "--cancel-offset-ms", str(CANCEL_MS),
        "--max-inflight-ms", str(MAX_INFLIGHT_MS),
        "--required-postroll-ms", "500",
        "--min-post-bound-observation-ms", "500",
        "--min-post-bound-active-ratio", "0.40",
        "--window-ms", "20",
        "--correlation-threshold", "0.80",
        "--capture-rms-ratio-floor", "0.10",
        "--voice-output-packet-id", "output-old-g2-h4",
        "--f2-subject-sha", "b" * 40,
    ]


@unittest.skipIf(numpy is None, "numpy is required for the H4 guard regression suite")
class H4GuardTests(unittest.TestCase):
    def test_active_post_bound_control_allows_delegate(self) -> None:
        source = _noise_source()
        with tempfile.TemporaryDirectory(prefix="t7-h4-positive-") as tmp:
            root = Path(tmp)
            s, c, x, o = root / "source.wav", root / "control.wav", root / "cancel.wav", root / "out.json"
            _write(s, source)
            _write(c, _capture(source, None))
            _write(x, _capture(source, CANCEL_MS + 50.0))
            rc = GUARD.main(_argv(s, c, x, o))
            receipt = json.loads(o.read_text(encoding="utf-8"))
            self.assertEqual(rc, 0, receipt)
            self.assertTrue(receipt["pass"])
            h4 = receipt["h4_discriminative_guard"]
            self.assertTrue(h4["pass"])
            self.assertGreaterEqual(
                h4["control_correlated_active_ms"],
                h4["required_correlated_active_ms"],
            )
            self.assertEqual(receipt["explicit_zero_credit"]["runtime_credit_from_h4_guard"], 0)

    def test_silent_source_after_bound_is_evidence_invalid_not_false_green(self) -> None:
        source = _noise_source()
        silence_at = int(round(BOUND_MS * RATE / 1000.0))
        source[silence_at:] = [0] * (len(source) - silence_at)
        with tempfile.TemporaryDirectory(prefix="t7-h4-silent-") as tmp:
            root = Path(tmp)
            s, c, x, o = root / "source.wav", root / "control.wav", root / "cancel.wav", root / "out.json"
            _write(s, source)
            _write(c, _capture(source, None))
            _write(x, _capture(source, CANCEL_MS + 50.0))
            rc = GUARD.main(_argv(s, c, x, o))
            receipt = json.loads(o.read_text(encoding="utf-8"))
            self.assertEqual(rc, 2, receipt)
            self.assertFalse(receipt["pass"])
            self.assertEqual(
                receipt["classification"],
                "EVIDENCE_INVALID_H4_INSUFFICIENT_POST_BOUND_DISCRIMINATIVE_AUDIO",
            )
            self.assertEqual(receipt["h4_guard"]["control_correlated_active_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
