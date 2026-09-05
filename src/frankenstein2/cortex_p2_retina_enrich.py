"""cortex_p2_retina_enrich.py -- CORTEX-P2 retina-signal enrichment, part B: the
decoupled one-shot producer + cache (F2-WP-1207 self-integration, "cortex-p2-retina-
signal" round, 2026-09-06).

WHY THIS IS A SEPARATE, SLOW-CADENCE PRODUCER AND NOT PART OF `cortex_p2_capture.py`'s
per-turn path: `digital_retina_adapter.analyze_frame_bytes()` measured ~5.7s real
round-trip against the live service on this host. `cortex_p2_capture.py`'s own
subprocess is budgeted 2.5s by its caller (frankenstein-repo's
`f2wp1207_cortex_p2_percept_candidate.capture_candidate()`), and the OUTER P15 canary
live-hook bridge budgets the WHOLE turn (P7+P10+P11+P12+P2 combined) at 4s. Calling
digital-retina synchronously from inside that path would deterministically exceed both
budgets on every turn the new signal is active, killing the existing numeric P2
candidate too -- not an edge case, a certainty given the measured numbers. So this
module runs OUTSIDE that budget, on its own cadence (invoked manually or by whatever
external scheduler the operator chooses -- this round does not add a systemd timer or
any other autonomous scheduling; that is an infrastructure decision outside this task's
additive-only scope), and persists a small, cheap-to-read cache file. The per-turn path
(frankenstein-repo's GRID10 half) reads that cache with a plain file read -- no network
call, no camera contention, microseconds -- when computing whether to blend a retina
term into the competition signal.

Chain this module uses (all REUSED, nothing reimplemented):
  REAL CAMERA -> frankenstein2.cortex_p3_frame_file.capture_frame_to_file() (P3,
    UNCHANGED: same P1 chain, same retina.global quality/salience gate, temp-JPEG-only
    discipline, single-owner rule) -> ONE real JPEG on temp disk
    -> digital_retina_adapter.analyze_frame_bytes() (this round's new adapter, part A)
    -> THIS module: derive the cache record, write it, unlink the temp JPEG.

No cloud consent gate is touched (digital-retina is local-only, see
digital_retina_adapter.py's docstring) -- this module does not call
`vision.cloud_escalation` or any star code. It DOES go through the SAME retina.global
perception-head gate `cortex_p3_frame_file` already enforces (COMPUTE_OFF there = no
frame, no analyze call, no cache write -- fail-closed, unchanged upstream behaviour).

CACHE DISCIPLINE, matching the P1/P2/P3 "IDs/short text only, never full rows"
convention: the cache file NEVER contains the raw caption text, only a sha256 of it plus
small derived numeric/boolean fields. No pixel ever reaches the cache file or stdout
beyond what `cortex_p3_frame_file` already permits (a temp JPEG, unlinked by this
module's own `finally`, exactly like the P3 CLI does).

Exit codes: 0 = a JSON record was produced and (if `ok`) the cache was written, even
when digital-retina returned a non-notable/failed result (an honest "nothing new" is not
a failure). 3 = no frame could be captured (device/gate/quality -- same reasons
`cortex_p3_frame_file` already reports). 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from .cortex_p3_frame_file import REAL_CAMERA_DEVICE, capture_frame_to_file
from .digital_retina_adapter import (
    DEFAULT_TIMEOUT_S,
    DIGITAL_RETINA_URL_DEFAULT,
    analyze_frame_bytes,
)

CACHE_SCHEMA = "CORTEX_P2_RETINA_CACHE/v1"

DEFAULT_CACHE_PATH = str(
    Path.home() / ".local" / "share" / "frankenstein2" / "cortex_p2_retina_cache.json"
)
ENV_CACHE_PATH = "CORTEX_P2_RETINA_CACHE"
ENV_RETINA_URL = "CORTEX_P2_RETINA_URL"
ENV_RETINA_TIMEOUT = "CORTEX_P2_RETINA_TIMEOUT_S"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_FRAME = 3


def cache_path_from_env(env: Optional[dict[str, str]] = None) -> str:
    environ = env if env is not None else os.environ
    return environ.get(ENV_CACHE_PATH) or DEFAULT_CACHE_PATH


def write_cache(path: str, record: dict[str, Any]) -> None:
    """Atomic-ish write (tmp file + rename on the same filesystem) so a reader never
    observes a half-written cache file."""
    ziel = Path(path)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(ziel.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ziel)


def read_cache(path: str) -> Optional[dict[str, Any]]:
    """Plain, fast, read-only. Returns None on any absence/parse failure -- callers
    treat that exactly like "no retina data available", never an error."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def enrich_once(
    *,
    device: Optional[str] = None,
    cache_path: Optional[str] = None,
    retina_url: Optional[str] = None,
    retina_timeout_s: Optional[float] = None,
    f2wp1207_unified_db: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """One real camera frame -> one digital-retina analyze call -> one cache write.
    Never raises. `f2wp1207_unified_db` is a test-isolation override forwarded to
    `capture_frame_to_file` (default: real production DB, read-only, unchanged)."""
    environ = env if env is not None else os.environ
    geraet = device or REAL_CAMERA_DEVICE
    cache = cache_path or cache_path_from_env(environ)
    url = retina_url or environ.get(ENV_RETINA_URL) or DIGITAL_RETINA_URL_DEFAULT
    try:
        timeout = float(retina_timeout_s if retina_timeout_s is not None
                        else environ.get(ENV_RETINA_TIMEOUT, DEFAULT_TIMEOUT_S))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_S

    out: dict[str, Any] = {"schema": CACHE_SCHEMA, "ok": False, "cache_path": cache}
    tmp_dir = tempfile.mkdtemp(prefix="cortex-p2-retina-")
    bild = str(Path(tmp_dir) / "frame.jpg")
    try:
        t_capture0 = time.monotonic()
        frame, grund = capture_frame_to_file(
            out_path=bild, device=geraet, unified_db=f2wp1207_unified_db,
        )
        out["capture_ms"] = round((time.monotonic() - t_capture0) * 1000, 1)
        if frame is None:
            out["reason"] = f"frame_failed:{grund}"
            return out
        out["frame_sha256"] = frame.get("frame_sha256")
        out["quality_micros"] = frame.get("quality_micros")

        t0 = time.monotonic()
        jpeg_bytes = Path(bild).read_bytes()
        analyse = analyze_frame_bytes(jpeg_bytes, url=url, timeout_s=timeout)
        out["analyze_ms"] = round((time.monotonic() - t0) * 1000, 1)
        out.update({
            "ok": bool(analyse.get("ok")), "engine": analyse.get("engine"),
            "model": analyse.get("model"), "notable": analyse.get("notable", False),
            "retina_semantic_micros": analyse.get("retina_semantic_micros", 0),
            "caption_sha256": analyse.get("caption_sha256"),
        })
        if analyse.get("fehler"):
            out["fehler"] = analyse["fehler"]
        if not out["ok"]:
            return out

        record = {
            "schema": CACHE_SCHEMA,
            "ok": True,
            "ts_wall_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ts_monotonic_ns": time.monotonic_ns(),
            "engine": analyse["engine"], "model": analyse["model"],
            "caption_sha256": analyse["caption_sha256"],
            "notable": bool(analyse["notable"]),
            "retina_semantic_micros": int(analyse["retina_semantic_micros"]),
            "source_frame_sha256": frame.get("frame_sha256"),
            "source_quality_micros": frame.get("quality_micros"),
        }
        write_cache(cache, record)
        out["cache_written"] = True
        return out
    finally:
        try:
            os.unlink(bild)
        except OSError:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m frankenstein2.cortex_p2_retina_enrich",
        description=("CORTEX-P2 retina-signal: one real camera frame -> one "
                     "digital-retina analyze call -> one cache write. No loop, no "
                     "daemon -- caller decides the cadence."),
    )
    parser.add_argument("--device", default=None)
    parser.add_argument("--cache-path", default=None)
    parser.add_argument("--retina-url", default=None)
    parser.add_argument("--retina-timeout-s", type=float, default=None)
    parser.add_argument("--unified-db", default=None, help="test isolation only")
    args = parser.parse_args(argv)

    erg = enrich_once(
        device=args.device, cache_path=args.cache_path, retina_url=args.retina_url,
        retina_timeout_s=args.retina_timeout_s, f2wp1207_unified_db=args.unified_db,
    )
    print(_canonical(erg))
    if erg.get("ok"):
        return EXIT_OK
    return EXIT_NO_FRAME if str(erg.get("reason", "")).startswith("frame_failed") else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
