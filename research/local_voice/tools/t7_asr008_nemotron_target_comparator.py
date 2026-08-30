#!/usr/bin/env python3
"""T7-ASR-008 bounded Nemotron 3.5 target-runtime comparator.

Exercises the exact source-pinned Nemotron 3.5 ASR Streaming Q8 artifact through
NVIDIA NeMo-Speech.cpp on the target execution surface. Records exact artifact
and runtime identity, matched FLEURS fixture identity, de-DE vs auto, all five
published RNNT right-context operating points, realtime partial/final behavior,
latency, RTF, process RSS, and deterministic digital-silence false activations.

This is evidence-scoped: it does not mint German quality, production turn
admission, E2E voice, effect, training, whole-system or product-completion credit.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import re
import signal
import statistics
import subprocess
import tempfile
import threading
import time
import unicodedata
import wave
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "T7_ASR008_NEMOTRON_TARGET_COMPARATOR_RECEIPT/v1"
SEMANTIC_KEY = "93d61d9b893d411c8085cd5d257968c23448bc426430e603f6e33add1db5e4e3"
MODEL_ID = "nvidia/nemotron-3.5-asr-streaming-0.6b"
MODEL_REVISION = "1c8deaecc64b91f034d73e08dd8b64625eb3395d"
MODEL_FILE = "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"
MODEL_SHA256 = "a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae"
NEMO_SPEECH_VERSION = "0.1.0"
NEMO_SPEECH_SOURCE_REVISION = "4f9676226f667d14608487df744f375db87127f8"
NEMO_SPEECH_LINUX_X86_64_CPU_ARCHIVE_SHA256 = "0f74131d631ad2c694cf0ec53490866bb6461147959589a69fb6fc231944065b"
FLEURS_REPO = "google/fleurs"
FLEURS_CONFIG = "de_de"
FLEURS_REVISION = "bc0636bc121b131df69ed727a4ddafc5afc8afe4"
RIGHT_CONTEXT_TO_MS = {0: 80, 1: 160, 3: 320, 6: 560, 13: 1120}
LANGUAGES = ("de-DE", "auto")
TRANSPORT_CHUNK_MS = 160
NORMALIZER = "NFKC_CASEFOLD_PUNCT_SYMBOL_TO_SPACE_COLLAPSE_WS"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        out.append(" " if cat.startswith("P") or cat.startswith("S") else ch)
    return " ".join("".join(out).split())


def edit_distance(a: list[str], b: list[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def score_pair(reference: str, hypothesis: str) -> dict[str, Any]:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    rw, hw = ref.split(), hyp.split()
    rc, hc = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
    we = edit_distance(rw, hw)
    ce = edit_distance(rc, hc)
    return {
        "normalizer": NORMALIZER,
        "reference_normalized": ref,
        "hypothesis_normalized": hyp,
        "word_errors": we,
        "reference_words": len(rw),
        "wer": we / max(1, len(rw)),
        "char_errors": ce,
        "reference_chars": len(rc),
        "cer": ce / max(1, len(rc)),
    }


def percentile(values: Iterable[float], p: float) -> float | None:
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * p
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (rank - lo)


def aggregate_latencies(records: list[dict[str, Any]]) -> dict[str, Any]:
    def vals(key: str) -> list[float]:
        return [float(r[key]) for r in records if r.get(key) is not None]
    return {
        key: {
            "p50": percentile(vals(key), 0.50),
            "p95": percentile(vals(key), 0.95),
            "p99": percentile(vals(key), 0.99),
            "mean": statistics.fmean(vals(key)) if vals(key) else None,
        }
        for key in ("first_partial_latency_ms", "final_latency_ms", "rtf")
    }


def partial_stability(partials: list[str], final_text: str) -> dict[str, Any]:
    normalized = [normalize_text(p) for p in partials if normalize_text(p)]
    final_norm = normalize_text(final_text)
    revisions = 0
    revision_edits = 0
    previous: list[str] = []
    for item in normalized:
        current = item.split()
        if previous:
            d = edit_distance(previous, current)
            revision_edits += d
            revisions += int(d > 0)
        previous = current
    tail_distance = edit_distance(previous, final_norm.split()) if previous or final_norm else 0
    return {
        "partial_count": len(normalized),
        "revision_events": revisions,
        "revision_edit_distance_sum": revision_edits,
        "last_partial_to_final_word_distance": tail_distance,
        "last_partial_matches_final": bool(normalized) and normalized[-1] == final_norm,
    }


def proc_rss_bytes(pid: int) -> int | None:
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        m = re.search(r"^VmRSS:\s+(\d+)\s+kB$", text, re.M)
        return int(m.group(1)) * 1024 if m else None
    except Exception:
        return None


class RssSampler:
    def __init__(self, pid: int, interval: float = 0.05) -> None:
        self.pid = pid
        self.interval = interval
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            rss = proc_rss_bytes(self.pid)
            if rss is not None:
                self.peak = max(self.peak, rss)
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


def parse_rows(spec: str) -> tuple[int, ...]:
    spec = spec.strip()
    if ":" in spec:
        a, b = spec.split(":", 1)
        rows = tuple(range(int(a), int(b)))
    else:
        rows = tuple(int(x) for x in spec.split(",") if x.strip())
    if not rows or any(x < 0 for x in rows) or len(set(rows)) != len(rows):
        raise ValueError("rows must be a non-empty unique non-negative range/list")
    return rows


def wav_pcm16(path: Path) -> tuple[bytes, int, float]:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
        if channels != 1 or width != 2 or rate != 16000:
            raise RuntimeError(f"expected mono PCM16 16k WAV, got channels={channels} width={width} rate={rate}")
        raw = wav.readframes(frames)
    return raw, rate, frames / rate


def write_silence(path: Path, seconds: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000 * seconds)


def prepare_fixtures(root: Path, rows: tuple[int, ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import importlib.metadata
    import numpy as np
    import soundfile as sf
    from datasets import Audio, load_dataset

    t0 = time.perf_counter()
    ds = load_dataset(FLEURS_REPO, FLEURS_CONFIG, revision=FLEURS_REVISION, split="test", trust_remote_code=True)
    ds = ds.cast_column("audio", Audio(decode=False))
    speech_dir = root / "speech"
    speech_dir.mkdir(parents=True, exist_ok=True)
    speech: list[dict[str, Any]] = []
    for row in rows:
        item = ds[row]
        audio = item["audio"]
        data = audio.get("bytes") if isinstance(audio, dict) else None
        source_path = audio.get("path") if isinstance(audio, dict) else None
        if data is None:
            if not source_path:
                raise RuntimeError(f"FLEURS row {row}: no bytes/path")
            data = Path(source_path).read_bytes()
        source_sha = hashlib.sha256(data).hexdigest()
        suffix = Path(str(source_path or "audio.flac")).suffix or ".flac"
        src = speech_dir / f"row_{row:02d}{suffix}"
        src.write_bytes(data)
        decoded, rate = sf.read(str(src), dtype="float32", always_2d=False)
        decoded = np.asarray(decoded, dtype=np.float32)
        if decoded.ndim == 2:
            decoded = decoded.mean(axis=1)
        if int(rate) != 16000:
            raise RuntimeError(f"FLEURS row {row}: expected 16k source, got {rate}")
        wav_path = speech_dir / f"row_{row:02d}.wav"
        sf.write(str(wav_path), decoded, 16000, subtype="PCM_16", format="WAV")
        _, _, duration = wav_pcm16(wav_path)
        speech.append({
            "fixture_kind": "speech",
            "row": row,
            "path": str(wav_path),
            "source_audio_sha256": source_sha,
            "normalized_wav_sha256": sha256_file(wav_path),
            "duration_seconds": duration,
            "reference": str(item.get("transcription", "")),
            "raw_transcription": str(item.get("raw_transcription", item.get("transcription", ""))),
            "dataset_id": item.get("id"),
        })
    ns_dir = root / "non_speech"
    ns_dir.mkdir(parents=True, exist_ok=True)
    non_speech: list[dict[str, Any]] = []
    for seconds in (1, 2, 5):
        path = ns_dir / f"digital_silence_{seconds}s.wav"
        write_silence(path, seconds)
        non_speech.append({
            "fixture_kind": "non_speech",
            "fixture_id": f"digital_silence_{seconds}s",
            "path": str(path),
            "normalized_wav_sha256": sha256_file(path),
            "duration_seconds": float(seconds),
            "reference": "",
        })
    return speech, non_speech, {
        "repo": FLEURS_REPO,
        "config": FLEURS_CONFIG,
        "revision": FLEURS_REVISION,
        "rows": list(rows),
        "datasets_version": importlib.metadata.version("datasets"),
        "soundfile_version": importlib.metadata.version("soundfile"),
        "numpy_version": importlib.metadata.version("numpy"),
        "preparation_seconds": time.perf_counter() - t0,
        "normalized_transport": "MONO_PCM16_16000_WAV",
    }


async def transcribe_realtime(url: str, fixture: dict[str, Any], language: str) -> dict[str, Any]:
    import websockets

    raw, rate, duration = wav_pcm16(Path(fixture["path"]))
    bytes_per_chunk = int(rate * (TRANSPORT_CHUNK_MS / 1000.0)) * 2
    t0 = time.perf_counter()
    partials: list[str] = []
    final_text = ""
    first_partial_ms: float | None = None
    events_seen: list[str] = []
    async with websockets.connect(url, open_timeout=20, close_timeout=10, max_size=16 * 1024 * 1024) as ws:
        created = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
        events_seen.append(str(created.get("type")))
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {"sample_rate": rate, "language": language, "automatic_punctuation": True,
                        "verbatim": False, "word_timestamps": False},
        }))
        for off in range(0, len(raw), bytes_per_chunk):
            await ws.send(raw[off : off + bytes_per_chunk])
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        deadline = time.perf_counter() + max(30.0, duration * 10.0)
        while time.perf_counter() < deadline:
            msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.perf_counter()))
            if isinstance(msg, bytes):
                continue
            event = json.loads(msg)
            kind = str(event.get("type", ""))
            events_seen.append(kind)
            if kind == "conversation.item.input_audio_transcription.delta":
                text = str(event.get("delta") or event.get("text") or "").strip()
                if text:
                    partials.append(text)
                    if first_partial_ms is None:
                        first_partial_ms = (time.perf_counter() - t0) * 1000.0
            elif kind == "conversation.item.input_audio_transcription.completed":
                final_text = str(event.get("transcript") or event.get("text") or "").strip()
                break
            elif kind == "error":
                raise RuntimeError(f"realtime server error: {event}")
        else:
            raise TimeoutError("realtime final transcript timeout")
    final_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "hypothesis": final_text,
        "partials": partials,
        "events_seen": events_seen,
        "first_partial_latency_ms": first_partial_ms,
        "final_latency_ms": final_ms,
        "rtf": (final_ms / 1000.0) / max(duration, 1e-9),
        "transport_chunk_ms": TRANSPORT_CHUNK_MS,
        "transport_pacing": "UNPACED_COMPUTE_LATENCY",
        "partial_stability": partial_stability(partials, final_text),
    }


def wait_ready(port: int, proc: subprocess.Popen[str], timeout: float = 180.0) -> dict[str, Any]:
    import urllib.request
    url = f"http://127.0.0.1:{port}/ready"
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"nemo-speech server exited before readiness rc={proc.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("ready") is True:
                return data
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(0.25)
    raise TimeoutError(f"server readiness timeout: {last_error}")


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        proc.wait(timeout=5)


def condition_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    speech = [r for r in records if r["fixture_kind"] == "speech"]
    ns = [r for r in records if r["fixture_kind"] == "non_speech"]
    word_errors = sum(int(r["score"]["word_errors"]) for r in speech)
    ref_words = sum(int(r["score"]["reference_words"]) for r in speech)
    char_errors = sum(int(r["score"]["char_errors"]) for r in speech)
    ref_chars = sum(int(r["score"]["reference_chars"]) for r in speech)
    false_activations = sum(1 for r in ns if normalize_text(r["hypothesis"]))
    partials = [r["partial_stability"] for r in speech]
    return {
        "speech_rows": len(speech), "non_speech_rows": len(ns),
        "micro_wer": word_errors / max(1, ref_words), "micro_cer": char_errors / max(1, ref_chars),
        "word_errors": word_errors, "reference_words": ref_words,
        "char_errors": char_errors, "reference_chars": ref_chars,
        "non_speech_false_activations": false_activations,
        "non_speech_false_activation_rate": false_activations / max(1, len(ns)),
        "latency_and_rtf": aggregate_latencies(records),
        "partial_stability": {
            "mean_partial_count": statistics.fmean([p["partial_count"] for p in partials]) if partials else None,
            "mean_revision_edit_distance_sum": statistics.fmean([p["revision_edit_distance_sum"] for p in partials]) if partials else None,
            "last_partial_matches_final_rate": sum(bool(p["last_partial_matches_final"]) for p in partials) / len(partials) if partials else None,
        },
    }


def runtime_version(binary: Path) -> dict[str, Any]:
    for command in ([str(binary), "--version"], [str(binary), "version"], [str(binary), "--json", "doctor"]):
        try:
            p = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            if p.returncode == 0:
                return {"command": command[1:], "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
        except Exception:
            pass
    return {"command": [], "stdout": "", "stderr": "VERSION_QUERY_FAILED"}


def execute(args: argparse.Namespace) -> dict[str, Any]:
    binary, model = Path(args.nemo_binary).resolve(), Path(args.model).resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"nemo binary missing/not executable: {binary}")
    if not model.is_file():
        raise RuntimeError(f"model missing: {model}")
    model_sha = sha256_file(model)
    if model_sha != MODEL_SHA256:
        raise RuntimeError(f"model hash mismatch expected={MODEL_SHA256} observed={model_sha}")
    archive_sha = sha256_file(Path(args.runtime_archive)) if args.runtime_archive else None
    if archive_sha and archive_sha != NEMO_SPEECH_LINUX_X86_64_CPU_ARCHIVE_SHA256:
        raise RuntimeError("NeMo-Speech.cpp release archive hash mismatch")

    rows = parse_rows(args.rows)
    root = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="t7-asr008-"))
    root.mkdir(parents=True, exist_ok=True)
    speech, non_speech, fixture_identity = prepare_fixtures(root / "fixtures", rows)
    all_conditions: list[dict[str, Any]] = []
    started = time.perf_counter()
    runtime_id = runtime_version(binary)
    for right_context, context_ms in RIGHT_CONTEXT_TO_MS.items():
        port = args.base_port + right_context
        log_path = root / f"server_rc{right_context}.log"
        with log_path.open("w", encoding="utf-8") as log:
            command = [str(binary), "serve", "--asr.model.path", str(model), "--asr.backend.gpu", "-1",
                       "--asr.streaming.rnnt_right_context", str(right_context), "--host", "127.0.0.1",
                       "--port", str(port), "--threads", "1", "--no-ui"]
            proc = subprocess.Popen(command, text=True, stdout=log, stderr=subprocess.STDOUT,
                                    env=os.environ.copy(), start_new_session=True)
            sampler = RssSampler(proc.pid)
            sampler.start()
            ready: dict[str, Any] = {}
            records: list[dict[str, Any]] = []
            try:
                ready = wait_ready(port, proc)
                for language in LANGUAGES:
                    for fixture in [*speech, *non_speech]:
                        result = asyncio.run(transcribe_realtime(f"ws://127.0.0.1:{port}/v1/realtime", fixture, language))
                        record = {
                            "language": language, "right_context": right_context, "operating_point_ms": context_ms,
                            "fixture_kind": fixture["fixture_kind"], "fixture_row": fixture.get("row"),
                            "fixture_id": fixture.get("fixture_id"), "audio_sha256": fixture["normalized_wav_sha256"],
                            "source_audio_sha256": fixture.get("source_audio_sha256"), "duration_seconds": fixture["duration_seconds"],
                            "reference": fixture["reference"], **result,
                        }
                        record["score"] = score_pair(record["reference"], record["hypothesis"])
                        records.append(record)
            finally:
                sampler.stop()
                terminate_process(proc)
        all_conditions.append({
            "right_context": right_context, "operating_point_ms": context_ms,
            "server_command": command[1:], "ready": ready,
            "server_peak_rss_bytes": sampler.peak, "server_log_sha256": sha256_file(log_path),
            "language_summaries": [
                {"language": language, "summary": condition_summary([r for r in records if r["language"] == language])}
                for language in LANGUAGES
            ],
            "records": records,
        })

    return {
        "schema": SCHEMA, "semantic_key": SEMANTIC_KEY, "research_id": "T7-ASR-008", "created_at": utc_now(),
        "classification": "TARGET_RUNTIME_COMPONENT_PILOT_EXECUTED_REQUIRES_TRIGGER4_RECONCILIATION",
        "execution_observed": True, "evidence_scope": "NEMOTRON_35_ASR_TARGET_RUNTIME_MATCHED_PILOT",
        "source_identity": {
            "f2_source_commit": os.environ.get("F2_SOURCE_COMMIT", ""), "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION, "model_file": MODEL_FILE,
            "model_sha256_expected": MODEL_SHA256, "model_sha256_observed": model_sha,
            "nemo_speech_version": NEMO_SPEECH_VERSION, "nemo_speech_source_revision": NEMO_SPEECH_SOURCE_REVISION,
            "nemo_binary_sha256": sha256_file(binary),
            "nemo_release_archive_sha256_expected": NEMO_SPEECH_LINUX_X86_64_CPU_ARCHIVE_SHA256,
            "nemo_release_archive_sha256_observed": archive_sha, "nemo_runtime_version_query": runtime_id,
        },
        "fixture_identity": fixture_identity,
        "execution_identity": {
            "hostname": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
            "cpu_count": os.cpu_count(), "device": "CPU_EXPLICIT_ASR_BACKEND_GPU_MINUS_1",
            "target_sandbox": os.environ.get("TARGET_SANDBOX", ""), "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            "transport": "NEMO_SPEECH_CPP_WEBSOCKET_V1_REALTIME", "transport_chunk_ms": TRANSPORT_CHUNK_MS,
            "transport_pacing": "UNPACED_COMPUTE_LATENCY",
        },
        "operating_points": all_conditions, "elapsed_seconds": time.perf_counter() - started,
        "scope_fences": {
            "target_runtime_component_execution_observed": 1, "nemotron_target_runtime_credit_candidate": 1,
            "german_asr_quality_credit": 0, "production_turn_admission_credit": 0,
            "paced_live_voice_latency_credit": 0, "physical_local_device_credit": 0, "gwt_jspace_credit": 0,
            "effect_credit": 0, "training_credit": 0, "trigger4_acceptance_credit": 0,
            "whole_system_credit": 0, "whole_product_credit": 0,
        },
        "limitations": [
            "Pilot uses 8 FLEURS de_de rows by default, not the full 32-row matched quality comparator.",
            "Realtime PCM is sent in unpaced 160 ms chunks; latency/RTF is target compute+transport latency, not paced live E2E latency.",
            "CPU backend is forced for comparability with the established target CPU lane; GPU performance is not measured.",
            "Digital silence measures raw decoder false text activation; deterministic production VAD/turn admission is intentionally not applied.",
        ],
    }


def validate_receipt(doc: dict[str, Any], expected_rows: tuple[int, ...]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema") != SCHEMA: errors.append("schema")
    if doc.get("semantic_key") != SEMANTIC_KEY: errors.append("semantic_key")
    if doc.get("execution_observed") is not True: errors.append("execution_observed")
    src = doc.get("source_identity") or {}
    if src.get("model_sha256_observed") != MODEL_SHA256: errors.append("model_sha256")
    if src.get("nemo_release_archive_sha256_observed") not in (None, NEMO_SPEECH_LINUX_X86_64_CPU_ARCHIVE_SHA256):
        errors.append("runtime_archive_sha256")
    if tuple((doc.get("fixture_identity") or {}).get("rows") or []) != expected_rows: errors.append("fixture_rows")
    ops = doc.get("operating_points") or []
    if {(op.get("right_context"), op.get("operating_point_ms")) for op in ops} != set(RIGHT_CONTEXT_TO_MS.items()):
        errors.append("operating_points")
    for op in ops:
        records = op.get("records") or []
        expected_count = (len(expected_rows) + 3) * len(LANGUAGES)
        if len(records) != expected_count: errors.append(f"record_count_rc{op.get('right_context')}")
        if {r.get("language") for r in records} != set(LANGUAGES): errors.append(f"languages_rc{op.get('right_context')}")
        if any(r.get("final_latency_ms") is None for r in records): errors.append(f"final_latency_rc{op.get('right_context')}")
    fences = doc.get("scope_fences") or {}
    for field in ("german_asr_quality_credit", "production_turn_admission_credit", "paced_live_voice_latency_credit",
                  "physical_local_device_credit", "gwt_jspace_credit", "effect_credit", "training_credit",
                  "trigger4_acceptance_credit", "whole_system_credit", "whole_product_credit"):
        if fences.get(field) != 0: errors.append(f"scope_fence_{field}")
    return errors


def self_test() -> None:
    assert normalize_text("Hallo, WELT!") == "hallo welt"
    assert score_pair("a b", "a c")["word_errors"] == 1
    assert parse_rows("0:3") == (0, 1, 2)
    assert parse_rows("0,2,4") == (0, 2, 4)
    assert percentile([1, 2, 3], 0.5) == 2
    p = partial_stability(["Hallo", "Hallo Welt"], "Hallo Welt")
    assert p["partial_count"] == 2 and p["last_partial_matches_final"] is True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nemo-binary"); parser.add_argument("--model"); parser.add_argument("--runtime-archive")
    parser.add_argument("--rows", default="0:8"); parser.add_argument("--base-port", type=int, default=18800)
    parser.add_argument("--work-dir"); parser.add_argument("--output"); parser.add_argument("--validate-receipt")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test(); print("SELF_TEST_PASS"); return 0
    if args.validate_receipt:
        doc = json.loads(Path(args.validate_receipt).read_text(encoding="utf-8"))
        errors = validate_receipt(doc, parse_rows(args.rows))
        print(json.dumps({"schema": "T7_ASR008_NEMOTRON_RECEIPT_VALIDATION/v1", "pass": not errors, "errors": errors}, indent=2, sort_keys=True))
        return 0 if not errors else 2
    if not args.nemo_binary or not args.model or not args.output:
        parser.error("execution requires --nemo-binary --model --output")
    try:
        receipt = execute(args)
        errors = validate_receipt(receipt, parse_rows(args.rows))
        receipt["self_validation"] = {"pass": not errors, "errors": errors}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(args.output)
        return 0 if not errors else 2
    except Exception as exc:
        failure = {
            "schema": SCHEMA, "semantic_key": SEMANTIC_KEY, "research_id": "T7-ASR-008", "created_at": utc_now(),
            "classification": "TARGET_RUNTIME_EXECUTION_FAILED_REQUIRES_FAILURE_CLASSIFICATION",
            "execution_observed": False, "error_type": type(exc).__name__, "error": str(exc),
            "scope_fences": {"target_runtime_component_execution_observed": 0, "nemotron_target_runtime_credit_candidate": 0,
                             "german_asr_quality_credit": 0, "trigger4_acceptance_credit": 0,
                             "whole_system_credit": 0, "whole_product_credit": 0},
        }
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
