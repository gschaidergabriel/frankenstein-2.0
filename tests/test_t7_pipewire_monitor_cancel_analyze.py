#!/usr/bin/env python3
"""Regression tests for the Trigger-7 PipeWire monitor cancel analyzer.

These tests are synthetic measurement tests only. They do not mint runtime,
PipeWire, Voice, physical-audio, or product credit.
"""
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
    import numpy  # noqa: F401  # analyzer runtime dependency
except Exception:  # pragma: no cover - stdlib-only repo jobs may omit numpy
    numpy = None

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "research" / "local_voice" / "tools" / "t7_pipewire_monitor_cancel_analyze.py"
MODULE_NAME = "t7_pipewire_monitor_cancel_analyze"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, TOOL)
assert SPEC and SPEC.loader
ANALYZER = importlib.util.module_from_spec(SPEC)
# Python 3.12 dataclasses resolves string/type metadata through sys.modules
# while the module body executes. Register the dynamic test import exactly as
# the normal import machinery would before exec_module().
sys.modules[MODULE_NAME] = ANALYZER
SPEC.loader.exec_module(ANALYZER)

RATE = 16_000
LEAD_FRAMES = RATE // 10  # 100 ms capture lead-in
SOURCE_FRAMES = RATE * 2
CANCEL_MS = 600.0
MAX_INFLIGHT_MS = 80.0


def _source_pcm() -> list[int]:
    rng = random.Random(0x7A11CE)
    # Deterministic broadband probe avoids periodic alignment ambiguity.
    return [rng.randint(-11_000, 11_000) for _ in range(SOURCE_FRAMES)]


def _write_wav(path: Path, samples: list[int], *, rate: int = RATE) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def _capture(source: list[int], *, retained_until_ms: float | None) -> list[int]:
    if retained_until_ms is None:
        body = list(source)
    else:
        cutoff = int(round(retained_until_ms * RATE / 1000.0))
        body = list(source[:cutoff]) + [0] * max(0, len(source) - cutoff)
    return [0] * LEAD_FRAMES + body + [0] * (RATE // 5)


@unittest.skipIf(numpy is None, "numpy is required for the analyzer regression suite")
class PipeWireMonitorCancelAnalyzerTests(unittest.TestCase):
    def _run_case(self, *, retained_until_ms: float, output_name: str) -> tuple[int, dict]:
        source = _source_pcm()
        with tempfile.TemporaryDirectory(prefix="t7-pipewire-analyzer-test-") as tmp:
            root = Path(tmp)
            source_path = root / "source.wav"
            control_path = root / "control.wav"
            cancel_path = root / "cancel.wav"
            output_path = root / output_name
            _write_wav(source_path, source)
            _write_wav(control_path, _capture(source, retained_until_ms=None))
            _write_wav(cancel_path, _capture(source, retained_until_ms=retained_until_ms))
            rc = ANALYZER.main(
                [
                    "--source", str(source_path),
                    "--control", str(control_path),
                    "--cancel", str(cancel_path),
                    "--output", str(output_path),
                    "--cancel-offset-ms", str(CANCEL_MS),
                    "--max-inflight-ms", str(MAX_INFLIGHT_MS),
                    "--window-ms", "20",
                    "--correlation-threshold", "0.80",
                    "--capture-rms-ratio-floor", "0.10",
                    "--voice-output-packet-id", "output-old-g2",
                    "--f2-subject-sha", "a" * 40,
                ]
            )
            receipt = json.loads(output_path.read_text(encoding="utf-8"))
            return rc, receipt

    def test_bounded_50ms_tail_is_no_counterexample(self) -> None:
        rc, receipt = self._run_case(
            retained_until_ms=CANCEL_MS + 50.0,
            output_name="bounded.json",
        )
        self.assertEqual(rc, 0, receipt)
        self.assertTrue(receipt["pass"])
        self.assertEqual(receipt["classification"], "NO_COUNTEREXAMPLE_AT_AUDIO_CORRELATION_SCOPE")
        self.assertTrue(receipt["invariants"]["CONTROL_VALID"])
        self.assertTrue(receipt["invariants"]["BOUNDED_TAIL"])
        self.assertTrue(receipt["invariants"]["NO_POST_BOUND_OLD_AUDIO"])
        self.assertLessEqual(
            receipt["measurement"]["observed_cancel_to_last_old_audio_tail_ms"],
            MAX_INFLIGHT_MS + 20.0,
        )
        self.assertEqual(receipt["explicit_zero_credit"]["runtime_credit_from_analyzer"], 0)
        self.assertEqual(receipt["explicit_zero_credit"]["whole_product"], 0)

    def test_200ms_tail_is_product_negative_at_measurement_scope(self) -> None:
        rc, receipt = self._run_case(
            retained_until_ms=CANCEL_MS + 200.0,
            output_name="too-long.json",
        )
        self.assertEqual(rc, 1, receipt)
        self.assertFalse(receipt["pass"])
        self.assertEqual(
            receipt["classification"],
            "PRODUCT_NEGATIVE_OLD_PACKET_AUDIO_PERSISTS_BEYOND_DECLARED_BOUND",
        )
        self.assertGreater(receipt["measurement"]["post_bound_old_audio_window_count"], 0)

    def test_unalignable_control_is_evidence_invalid_not_product_negative(self) -> None:
        source = _source_pcm()
        with tempfile.TemporaryDirectory(prefix="t7-pipewire-analyzer-invalid-") as tmp:
            root = Path(tmp)
            source_path = root / "source.wav"
            control_path = root / "control.wav"
            cancel_path = root / "cancel.wav"
            output_path = root / "invalid.json"
            _write_wav(source_path, source)
            _write_wav(control_path, [0] * (LEAD_FRAMES + SOURCE_FRAMES + RATE // 5))
            _write_wav(cancel_path, _capture(source, retained_until_ms=CANCEL_MS + 50.0))
            rc = ANALYZER.main(
                [
                    "--source", str(source_path),
                    "--control", str(control_path),
                    "--cancel", str(cancel_path),
                    "--output", str(output_path),
                    "--cancel-offset-ms", str(CANCEL_MS),
                    "--max-inflight-ms", str(MAX_INFLIGHT_MS),
                ]
            )
            receipt = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(rc, 2, receipt)
            self.assertFalse(receipt["pass"])
            self.assertEqual(
                receipt["classification"],
                "EVIDENCE_INVALID_CONTROL_OR_PRECANCEL_ALIGNMENT",
            )


if __name__ == "__main__":
    unittest.main()
