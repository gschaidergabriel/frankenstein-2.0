"""Tests for CORTEX-P2 retina-signal, part A: frankenstein2.digital_retina_adapter
(F2-WP-1207 self-integration, "cortex-p2-retina-signal" round, 2026-09-06).

Pure-function tests always run. The real-HTTP test talks to the actual, independent
`digital-retina.service` on 127.0.0.1:8000 -- skipped (not failed) when that service is
not reachable on this host, same convention as the camera tests skip on missing
hardware. No mocking of the HTTP layer: this is a real request against a real running
CPU-vision pipeline, matching this repo's "not mocked" testing culture for CORTEX-P*.
"""
from __future__ import annotations

import pathlib
import socket
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from frankenstein2.digital_retina_adapter import (  # noqa: E402
    DIGITAL_RETINA_URL_DEFAULT,
    ENGINE_TAG,
    MODEL_TAG,
    NOTABLE_BONUS_MICROS,
    NOTABLE_MARKER,
    analyze_frame_bytes,
    retina_semantic_micros_from_caption,
)


def _retina_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=1.0):
            return True
    except OSError:
        return False


HAS_RETINA = _retina_reachable()
skip_no_retina = pytest.mark.skipif(not HAS_RETINA, reason="digital-retina.service not reachable on 127.0.0.1:8000")


# --------------------------------------------------------------------------
# retina_semantic_micros_from_caption -- pure, deterministic, no I/O
# --------------------------------------------------------------------------

def test_notable_marker_present_yields_full_bonus():
    caption = "A wide-format image showing a person. Notable detail: person with beard."
    assert retina_semantic_micros_from_caption(caption) == NOTABLE_BONUS_MICROS


def test_notable_marker_absent_yields_zero():
    caption = "A wide-format image showing an empty room, in even lighting."
    assert retina_semantic_micros_from_caption(caption) == 0


def test_notable_marker_case_insensitive():
    caption = "A scene. NOTABLE DETAIL: a wall mirror."
    assert retina_semantic_micros_from_caption(caption) == NOTABLE_BONUS_MICROS


def test_empty_and_none_caption_yield_zero():
    assert retina_semantic_micros_from_caption("") == 0
    assert retina_semantic_micros_from_caption(None) == 0


def test_bonus_is_bounded_in_micros_range():
    assert 0 <= retina_semantic_micros_from_caption(NOTABLE_MARKER) <= 1_000_000


# --------------------------------------------------------------------------
# analyze_frame_bytes -- real HTTP, real service, or a real connection failure
# --------------------------------------------------------------------------

def _synthetic_jpeg_bytes() -> bytes:
    frame = (np.random.rand(240, 320, 3) * 255).astype("uint8")
    cv2.rectangle(frame, (40, 40), (120, 120), (0, 255, 0), -1)
    ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    assert ok
    return enc.tobytes()


@skip_no_retina
def test_analyze_frame_bytes_real_call_returns_real_caption():
    out = analyze_frame_bytes(_synthetic_jpeg_bytes(), timeout_s=20.0)
    assert out["ok"] is True, out
    assert out["engine"] == ENGINE_TAG
    assert out["model"] == MODEL_TAG
    assert isinstance(out["caption"], str) and out["caption"]
    assert isinstance(out["caption_sha256"], str) and len(out["caption_sha256"]) == 64
    assert out["retina_semantic_micros"] == retina_semantic_micros_from_caption(out["caption"])
    assert isinstance(out["notable"], bool)
    assert out["elapsed_ms"] is not None and out["elapsed_ms"] > 0


def test_analyze_frame_bytes_fails_open_on_connection_error():
    # Deliberately unroutable port on loopback -- a real connection failure, not mocked.
    out = analyze_frame_bytes(_synthetic_jpeg_bytes(), url="http://127.0.0.1:1/v1/demo/analyze", timeout_s=2.0)
    assert out["ok"] is False
    assert out["fehler"]
    assert out["retina_semantic_micros"] == 0


def test_analyze_frame_bytes_never_raises_on_bad_url():
    out = analyze_frame_bytes(_synthetic_jpeg_bytes(), url="not-a-url", timeout_s=1.0)
    assert out["ok"] is False
    assert out["fehler"]
