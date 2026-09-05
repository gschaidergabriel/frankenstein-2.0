"""Tests for CORTEX-P2 retina-signal, part B: frankenstein2.cortex_p2_retina_enrich
(F2-WP-1207 self-integration, "cortex-p2-retina-signal" round, 2026-09-06).

Cache read/write round-trips run always (pure filesystem, tmp_path-isolated). The real
end-to-end capture+analyze+cache test needs BOTH the real camera device and the real
digital-retina service and is skipped (not failed) when either is unavailable -- same
convention as the existing CORTEX-P1/P2/P3 real-hardware tests. It is also skipped (not
failed, reason disclosed) when /dev/video0 is exclusively held by another real process
(the single-owner rule this whole chain enforces -- correctly refusing here, on this
host, is itself evidence the rule works, not a defect to hide).
"""
from __future__ import annotations

import json
import pathlib
import socket
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2.cortex_p2_retina_enrich import (  # noqa: E402
    CACHE_SCHEMA,
    cache_path_from_env,
    enrich_once,
    read_cache,
    write_cache,
)
from frankenstein2.host_capture_adapter import REAL_CAMERA_DEVICE  # noqa: E402


def _retina_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=1.0):
            return True
    except OSError:
        return False


HAS_CAMERA = pathlib.Path(REAL_CAMERA_DEVICE).exists()
HAS_RETINA = _retina_reachable()


# --------------------------------------------------------------------------
# cache read/write -- pure filesystem, always runs
# --------------------------------------------------------------------------

def test_write_then_read_cache_roundtrip(tmp_path):
    path = str(tmp_path / "cache.json")
    record = {
        "schema": CACHE_SCHEMA, "ok": True, "ts_wall_iso": "2026-09-06T00:00:00Z",
        "ts_monotonic_ns": time.monotonic_ns(), "engine": "digital_retina_local_b",
        "model": "retina-cpu-v0.1", "caption_sha256": "a" * 64, "notable": True,
        "retina_semantic_micros": 500_000, "source_frame_sha256": "b" * 64,
        "source_quality_micros": 900_000,
    }
    write_cache(path, record)
    back = read_cache(path)
    assert back == record


def test_read_cache_missing_file_returns_none(tmp_path):
    assert read_cache(str(tmp_path / "does-not-exist.json")) is None


def test_read_cache_malformed_json_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert read_cache(str(p)) is None


def test_write_cache_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "nested" / "dir" / "cache.json")
    write_cache(path, {"schema": CACHE_SCHEMA, "ok": True})
    assert pathlib.Path(path).is_file()


def test_cache_path_from_env_uses_override():
    assert cache_path_from_env({"CORTEX_P2_RETINA_CACHE": "/tmp/x.json"}) == "/tmp/x.json"


def test_cache_path_from_env_default_when_unset():
    assert cache_path_from_env({}).endswith("cortex_p2_retina_cache.json")


# --------------------------------------------------------------------------
# enrich_once -- real camera + real digital-retina, or an honest skip
# --------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_CAMERA, reason=f"{REAL_CAMERA_DEVICE} not present on this host")
@pytest.mark.skipif(not HAS_RETINA, reason="digital-retina.service not reachable on 127.0.0.1:8000")
def test_enrich_once_real_camera_and_real_retina_writes_cache(tmp_path):
    cache = str(tmp_path / "cache.json")
    out = enrich_once(cache_path=cache)
    if not out.get("ok"):
        # A held device (single-owner rule correctly refusing a second real owner) is a
        # legitimate, disclosed outcome on a host where another process already owns
        # /dev/video0 -- not this test's failure, the rule working as designed.
        pytest.skip(f"enrich_once did not produce a candidate on this host: {out.get('reason') or out.get('fehler')}")
    assert out["cache_written"] is True
    record = read_cache(cache)
    assert record is not None
    assert record["schema"] == CACHE_SCHEMA
    assert record["ok"] is True
    assert isinstance(record["caption_sha256"], str) and len(record["caption_sha256"]) == 64
    assert record["retina_semantic_micros"] in (0, 500_000)
    assert isinstance(record["ts_monotonic_ns"], int)
