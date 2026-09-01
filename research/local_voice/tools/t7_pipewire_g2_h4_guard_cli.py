#!/usr/bin/env python3
"""CLI entrypoint for the Trigger-7 G2 H4 evidence-validity guard.

When imported by the Trigger-4 G2 runtime harness this module also exposes the
base PCM-analysis helpers used for positive replacement-generation readback.
This is evidence plumbing only; the H4 guard remains the promotion entrypoint.
"""
from __future__ import annotations

from pathlib import Path
import sys

# Dynamic loading from the Trigger-4 harness does not automatically put this
# tools directory on sys.path. Bind it explicitly so both the H4 guard and the
# base analyzer resolve identically whether this file is executed or imported.
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from t7_pipewire_g2_h4_guard import main
from t7_pipewire_monitor_cancel_analyze import (
    fft_alignment_offset,
    load_pcm16_wav,
    scan_correlated_windows,
)

__all__ = (
    "main",
    "fft_alignment_offset",
    "load_pcm16_wav",
    "scan_correlated_windows",
)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
