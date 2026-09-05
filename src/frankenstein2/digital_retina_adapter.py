"""digital_retina_adapter.py -- CORTEX-P2 retina-signal enrichment, part A: the pure
HTTP adapter to the independent local `digital-retina` service (F2-WP-1207
self-integration, "cortex-p2-retina-signal" round, 2026-09-06).

Architecture boundary (unchanged from CORTEX-P1/P2/P3, verified against
`~/self-integration/log/2026-09-05-040-cortex-p1-real-retina-bridge.md` before writing
this file): `frankenstein-2.0`'s `perception_*`/`cortex_*` modules ("Codebase B") are the
canonical core; `~/.claude/star/` ("Codebase A", the "Frank" assistant) is design
reference only, NEVER imported. `digital-retina` is neither A nor B -- it is a THIRD,
independent local service (systemd --user `digital-retina.service`, CPU-only
CLIP-B32+DINOv2+YOLO+face pipeline, bound to 127.0.0.1:8000 only). Calling its HTTP API
directly is calling an independent service, not importing Codebase A -- Codebase A's own
`visual_cortex.vision_beschreibung_lokal_holen()` happens to call the SAME service, but
this module does not import or invoke that function; it re-implements the (small) HTTP
call and response parsing from scratch against B's own conventions. grep this file for
"claude/star" or "visual_cortex" import statements: there are none.

MEASURED LATENCY, real call against the live service on this host (2026-09-06):
~5.7s per `/v1/demo/analyze` call (CPU-only multi-model pipeline). This is why the
sibling module `cortex_p2_retina_enrich.py` does NOT call this adapter from inside
`cortex_p2_capture.py`'s per-turn hot path (that path's own subprocess timeout is 2.5s,
and the outer P15 canary live-hook bridge budgets the WHOLE turn incl. P7/P10/P11/P12 at
4s total -- a 5.7s call would deterministically blow both). Instead this adapter is
driven by a separate, slow-cadence, decoupled one-shot producer (see
`cortex_p2_retina_enrich.py`) that writes a small cache file the hot path reads with a
plain, fast file read -- no network call in the per-turn path at all.

PRIVACY NOTE: no cloud consent gate applies here (unlike CORTEX-P3's cloud-vision path)
because digital-retina makes zero external network calls -- it is a local process on
127.0.0.1 processing a frame that never leaves this host. Gabriel's `digital-retina`
service docstring frames this explicitly: it exists to REPLACE cloud vision precisely so
this per-call consent requirement does not apply. The retina.global perception-head
quality/salience gate (already enforced by whichever capture path produced the frame)
still applies upstream of this module; this module makes no persistence-gate decision of
its own.

DISCIPLINE, matching the P1/P2/P3 "IDs/short text only, never full rows" convention: the
raw caption STRING is returned to the caller (needed once, in RAM, to derive the bonus)
but this module never writes it to disk itself -- see `cortex_p2_retina_enrich.py`'s
cache writer, which persists a sha256 of the caption and small derived fields only, never
the caption text.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

DIGITAL_RETINA_URL_DEFAULT = "http://127.0.0.1:8000/v1/demo/analyze"
ENGINE_TAG = "digital_retina_local_b"  # "_b" = Codebase B's own adapter, distinct from
# Codebase A's engine tag "digital_retina_local" in visual_cortex.py -- same service,
# independently-implemented caller, deliberately distinguishable in any record/log.
MODEL_TAG = "retina-cpu-v0.1"

# Measured real round-trip on this host (2026-09-06): ~5.7s for one CPU-only
# CLIP+DINOv2+YOLO+face pass. Default timeout gives real margin above that -- this
# adapter is NEVER called from a tight per-turn budget (see module docstring), so a
# generous timeout costs nothing except this one-shot producer's own wall time.
DEFAULT_TIMEOUT_S = 20.0

# The one real, mechanical (not fabricated-sentiment) marker this v1 heuristic keys off:
# digital-retina's own caption template inserts "Notable detail: ..." when its
# object/face pipeline surfaces something worth flagging (observed directly in this
# session's real visual_event rows, e.g. "Notable detail: person with beard, a wall
# mirror"). Presence of this marker is a REAL signal already computed by digital-retina's
# own CV pipeline (YOLO/face detections), not a semantic judgement invented here.
NOTABLE_MARKER = "notable detail:"
NOTABLE_BONUS_MICROS = 500_000


def _canonical_caption_sha256(caption: str) -> str:
    return hashlib.sha256(caption.strip().encode("utf-8")).hexdigest()


def retina_semantic_micros_from_caption(caption: Optional[str]) -> int:
    """Real, deterministic, bounded [0, 1_000_000] bonus derived from ONE mechanical
    check against the caption text: does digital-retina's own pipeline flag a notable
    detail? v1 deliberately does not attempt free-text sentiment/semantic scoring (that
    would be fabricated, not measured) -- this is intentionally the smallest real signal
    available, documented as such, not the final word on "meaningful"."""
    if not caption:
        return 0
    return NOTABLE_BONUS_MICROS if NOTABLE_MARKER in caption.strip().lower() else 0


def analyze_frame_bytes(
    jpeg_bytes: bytes,
    *,
    url: str = DIGITAL_RETINA_URL_DEFAULT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    hint: Optional[str] = None,
) -> dict[str, Any]:
    """ONE real HTTP call to the independent digital-retina service. Fail-open: never
    raises, always returns a dict with at least {"ok": bool}. Never touches disk itself
    (the JPEG comes in as bytes already in RAM, e.g. from `cv2.imencode`); never imports
    anything under `~/.claude/star`."""
    import requests  # already a transitive dependency on this host (digital-retina's
    # own client code and Codebase A both use it); imported lazily so a host without it
    # only fails when this function is actually called, matching cv2's lazy-import
    # convention used elsewhere in this package.

    t0 = time.monotonic()
    out: dict[str, Any] = {
        "ok": False, "engine": None, "model": None, "caption": None,
        "caption_sha256": None, "retina_semantic_micros": 0, "notable": False,
        "elapsed_ms": None, "fehler": None,
    }
    data = {"hint": hint} if hint else None
    try:
        r = requests.post(
            url, files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
            data=data, timeout=timeout_s,
        )
    except Exception as exc:  # timeout, connection refused, DNS, etc. -- fail-open
        out["fehler"] = f"digital_retina_http: {type(exc).__name__}: {exc}"
        out["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)
        return out
    out["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)

    if r.status_code != 200:
        out["fehler"] = f"digital_retina_http: HTTP {r.status_code} {r.text[:200]!r}"
        return out
    try:
        payload = r.json()
    except Exception as exc:
        out["fehler"] = f"digital_retina_http: invalid JSON: {exc}"
        return out

    caption = (payload.get("description") or "").strip()
    if not caption:
        out["engine"], out["model"] = ENGINE_TAG, MODEL_TAG
        out["fehler"] = "digital_retina_http: empty description in response"
        return out

    bonus = retina_semantic_micros_from_caption(caption)
    out.update({
        "ok": True, "engine": ENGINE_TAG, "model": MODEL_TAG, "caption": caption,
        "caption_sha256": _canonical_caption_sha256(caption),
        "retina_semantic_micros": bonus, "notable": bonus > 0,
    })
    return out
