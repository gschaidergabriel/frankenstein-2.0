#!/usr/bin/env python3
"""T7-ASR-008 bounded Nemotron 3.5 target-runtime comparator.

Executes the already-routed Trigger-4 benchmark only. It reuses the exact
T7-ASR-004 FLEURS de_de rows 0..31 and deterministic external speech-presence
gate, runs the pinned Nemotron 3.5 Q8 artifact through pinned NeMo-Speech.cpp,
and emits exact-scope evidence. It does not grant global German quality,
production voice, physical-device, GWT/J-Space, effect, training, or whole-product credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from t7_asr004_matched_comparator import (
    FLEURS_CONFIG,
    FLEURS_REPO,
    FLEURS_REVISION,
    ROWS,
    gate_audio,
    prepare_fixtures,
)
from t7_asr004_comparator_receipt_validator import chars, edit_distance, tokens

SCHEMA = "T7_ASR008_NEMOTRON35_TARGET_COMPARATOR_RECEIPT/v1"
SEMANTIC_KEY = "93d61d9b893d411c8085cd5d257968c23448bc426430e603f6e33add1db5e4e3"
MODEL_ID = "nvidia/nemotron-3.5-asr-streaming-0.6b"
MODEL_REVISION = "1c8deaecc64b91f034d73e08dd8b64625eb3395d"
MODEL_SHA256 = "a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae"
RUNTIME_REPO = "NVIDIA/NeMo-Speech.cpp"
RUNTIME_COMMIT = "4f9676226f667d14608487df744f375db87127f8"
GATE_CONTRACT_FILE = "t7_asr004_external_gate_contract.json"
NORMALIZER = "NFKC_CASEFOLD_PUNCT_SYMBOL_TO_SPACE_COLLAPSE_WS"
GEOMETRIES = ((80, 0), (160, 1), (320, 3), (560, 6), (1120, 13))
LANGUAGES = ("de-DE", "auto")
BASELINES = {
    "qwen3_asr_0_6b": {
        "checkpoint": "research/local_voice/checkpoints/2026-08-31_T7_ASR004_EXECUTED_COMPARATOR_CONSUMED_NEMOTRON_UNBLOCKED_GPT56SOL.json",
        "micro_wer": 0.06388888888888888,
        "micro_cer": 0.02643486544415337,
    },
    "faster_whisper_large_v3": {
        "checkpoint": "research/local_voice/checkpoints/2026-08-31_T7_ASR004_EXECUTED_COMPARATOR_CONSUMED_NEMOTRON_UNBLOCKED_GPT56SOL.json",
        "micro_wer": 0.034722222222222224,
        "micro_cer": 0.012145748987854251,
    },
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, check=False,
    )


def ffmpeg_wav(src: Path, dst: Path) -> None:
    p = run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst),
    ], timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {src.name}: {p.stderr[-1000:]}")


def parse_time_v(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "max_rss_kib": r"Maximum resident set size \(kbytes\):\s*(\d+)",
        "user_seconds": r"User time \(seconds\):\s*([0-9.]+)",
        "system_seconds": r"System time \(seconds\):\s*([0-9.]+)",
        "cpu_percent": r"Percent of CPU this job got:\s*([0-9]+)%",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            result[key] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    return result


def read_transcript(outdir: Path, stem: str) -> str:
    candidates = [outdir / f"{stem}.txt", outdir / f"{stem}.wav.txt"]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace").strip()
    hits = sorted(
        p for p in outdir.rglob("*")
        if p.is_file() and (p.stem == stem or p.name.startswith(stem + "."))
    )
    for path in hits:
        if path.suffix.lower() in {".txt", ".json"}:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
            if path.suffix.lower() == ".txt":
                return raw
            try:
                doc = json.loads(raw)
            except Exception:
                continue
            if isinstance(doc, dict):
                for key in ("text", "transcript", "transcription"):
                    if isinstance(doc.get(key), str):
                        return doc[key].strip()
    raise RuntimeError(f"missing transcript output for {stem} under {outdir}")


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    we = rw = ce = rc = 0
    for r in records:
        refw, hypw = tokens(r["reference"]), tokens(r["hypothesis"])
        refc, hypc = chars(r["reference"]), chars(r["hypothesis"])
        rw += len(refw)
        we += edit_distance(refw, hypw)
        rc += len(refc)
        ce += edit_distance(refc, hypc)
    return {
        "utterance_count": len(records),
        "micro_wer": (we / rw) if rw else None,
        "micro_cer": (ce / rc) if rc else None,
        "word_edits": we,
        "reference_words": rw,
        "char_edits": ce,
        "reference_chars": rc,
    }


def load_gate_contract() -> tuple[dict[str, Any], str]:
    path = Path(__file__).resolve().with_name(GATE_CONTRACT_FILE)
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("schema") != "T7_ASR004_EXTERNAL_GATE_CONTRACT/v1":
        raise RuntimeError("shared gate contract schema mismatch")
    return doc, hashlib.sha256(raw).hexdigest()


def materialize_inputs(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    speech, non_speech, dataset_runtime = prepare_fixtures(root / "source")
    wavdir = root / "wav"
    wavdir.mkdir(parents=True)
    for item in speech:
        dst = wavdir / f"fleurs_de_de_test_{int(item['row']):02d}.wav"
        ffmpeg_wav(Path(item["path"]), dst)
        item["benchmark_wav"] = dst
        item["benchmark_wav_sha256"] = sha256_file(dst)
    for item in non_speech:
        dst = wavdir / f"{item['fixture_id']}.wav"
        ffmpeg_wav(Path(item["path"]), dst)
        item["benchmark_wav"] = dst
        item["benchmark_wav_sha256"] = sha256_file(dst)
    return speech, non_speech, dataset_runtime


def execute_config(
    binary: Path,
    model: Path,
    root: Path,
    speech: list[dict[str, Any]],
    non_speech: list[dict[str, Any]],
    gate_contract: dict[str, Any],
    gate_sha: str,
    language: str,
    chunk_ms: int,
    right_context: int,
) -> dict[str, Any]:
    outdir = root / f"out_{language.replace('-', '_')}_{chunk_ms}"
    outdir.mkdir(parents=True)
    timefile = root / f"time_{language.replace('-', '_')}_{chunk_ms}.txt"
    cmd = [
        "/usr/bin/time", "-v", "-o", str(timefile),
        str(binary), "transcribe", str(root / "wav"),
        "--recursive", "--output-dir", str(outdir), "--force", "--concurrency", "1",
        "--model", str(model), "--language", language, "--device", "cpu",
        "--stream", "--no-batching",
        "--asr.streaming.rnnt_right_context", str(right_context),
    ]
    t0 = time.perf_counter()
    p = run(cmd, timeout=7200)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    if p.returncode != 0:
        raise RuntimeError(
            f"nemo-speech failed language={language} chunk={chunk_ms} rc={p.returncode}: {p.stderr[-3000:]}"
        )

    speech_records: list[dict[str, Any]] = []
    false_rejects = 0
    for item in speech:
        stem = f"fleurs_de_de_test_{int(item['row']):02d}"
        hyp = read_transcript(outdir, stem)
        gate = gate_audio(Path(item["benchmark_wav"]), gate_contract)
        if gate["decision"] == "NON_SPEECH":
            false_rejects += 1
        speech_records.append({
            "fixture_row": int(item["row"]),
            "audio_sha256": item["audio_sha256"],
            "benchmark_wav_sha256": item["benchmark_wav_sha256"],
            "reference": item["reference"],
            "hypothesis": hyp,
            "gate_decision": gate["decision"],
            "gate_voiced_ratio": gate["voiced_ratio"],
            "external_gate_contract_sha256": gate_sha,
        })

    non_speech_records: list[dict[str, Any]] = []
    raw_false = gated_false = 0
    for item in non_speech:
        hyp = read_transcript(outdir, item["fixture_id"])
        gate = gate_audio(Path(item["benchmark_wav"]), gate_contract)
        raw_false += int(bool(hyp.strip()))
        gated_hyp = hyp if gate["decision"] == "SPEECH" else ""
        gated_false += int(bool(gated_hyp.strip()))
        non_speech_records.append({
            "fixture_id": item["fixture_id"],
            "audio_sha256": item["audio_sha256"],
            "benchmark_wav_sha256": item["benchmark_wav_sha256"],
            "raw_hypothesis": hyp,
            "gate_decision": gate["decision"],
            "gated_hypothesis": gated_hyp,
            "external_gate_contract_sha256": gate_sha,
        })
    metrics = aggregate(speech_records)
    metrics.update({
        "language": language,
        "chunk_ms": chunk_ms,
        "rnnt_right_context": right_context,
        "stream_mode": True,
        "batching": False,
        "batch_wall_ms": wall_ms,
        "time_v": parse_time_v(timefile),
        "speech_gate_false_rejects": false_rejects,
        "non_speech_false_text_activations_raw": raw_false,
        "non_speech_false_text_activations_gated": gated_false,
        "partial_stability": "NOT_EXPOSED_BY_CURRENT_DIRECTORY_CLI_SURFACE",
        "first_stable_token_latency": "NOT_EXPOSED_BY_CURRENT_DIRECTORY_CLI_SURFACE",
        "final_latency_scope": "BATCH_WALL_ONLY_NOT_PER_UTTERANCE",
    })
    return {
        "metrics": metrics,
        "speech_records": speech_records,
        "non_speech_records": non_speech_records,
        "stderr_tail": p.stderr[-4000:],
    }


def deterministic_rerun(binary: Path, model: Path, fixture: Path) -> dict[str, Any]:
    outputs = []
    for i in range(2):
        p = run([
            str(binary), "transcribe", str(fixture), "--model", str(model),
            "--language", "de-DE", "--device", "cpu", "--stream", "--no-batching",
            "--asr.streaming.rnnt_right_context", "3",
        ], timeout=1800)
        if p.returncode != 0:
            raise RuntimeError(f"determinism rerun failed iteration={i}: {p.stderr[-2000:]}")
        outputs.append(p.stdout.strip())
    return {
        "fixture": fixture.name,
        "language": "de-DE",
        "chunk_ms": 320,
        "rnnt_right_context": 3,
        "reruns": 2,
        "byte_equal_stdout": outputs[0] == outputs[1],
        "stdout_sha256": [hashlib.sha256(x.encode()).hexdigest() for x in outputs],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nemo-speech", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--runtime-commit", default=RUNTIME_COMMIT)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    output = Path(args.output)
    binary = Path(args.nemo_speech).resolve()
    model = Path(args.model).resolve()
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "semantic_key": SEMANTIC_KEY,
        "research_id": "T7-ASR-008",
        "timestamp_started_utc": utc_now(),
        "execution_observed": False,
        "pass": False,
        "credits": {
            "nemotron_target_runtime_credit": 0,
            "german_asr_quality_credit": 0,
            "production_streaming_credit": 0,
            "trigger4_acceptance_credit": 0,
            "physical_device_credit": 0,
            "gwt_jspace_credit": 0,
            "effect_credit": 0,
            "training_credit": 0,
            "whole_voice_e2e_credit": 0,
            "whole_product_credit": 0,
        },
    }
    try:
        if not binary.is_file():
            raise RuntimeError(f"nemo-speech binary missing: {binary}")
        if sha256_file(model) != MODEL_SHA256:
            raise RuntimeError("Nemotron Q8 SHA-256 mismatch")
        if args.runtime_commit != RUNTIME_COMMIT:
            raise RuntimeError(f"runtime commit mismatch: {args.runtime_commit} != {RUNTIME_COMMIT}")
        version = run([str(binary), "--version"], timeout=30)
        help_tx = run([str(binary), "help", "transcribe"], timeout=30)
        with tempfile.TemporaryDirectory(prefix="t7-asr008-") as td:
            root = Path(td)
            speech, non_speech, dataset_runtime = materialize_inputs(root)
            gate_contract, gate_sha = load_gate_contract()
            configs = []
            for language in LANGUAGES:
                for chunk_ms, right_context in GEOMETRIES:
                    configs.append(execute_config(
                        binary, model, root, speech, non_speech, gate_contract, gate_sha,
                        language, chunk_ms, right_context,
                    ))
            det = deterministic_rerun(binary, model, Path(speech[0]["benchmark_wav"]))
            if not det["byte_equal_stdout"]:
                raise RuntimeError("deterministic rerun mismatch at de-DE/320ms")
            receipt.update({
                "timestamp_completed_utc": utc_now(),
                "execution_observed": True,
                "classification": "EXECUTED_NO_HARNESS_COUNTEREXAMPLE",
                "target_surface": "clay-direct-dev",
                "source_repo_commit": os.environ.get("F2_PROBE_COMMIT", ""),
                "model": {
                    "id": MODEL_ID,
                    "revision": MODEL_REVISION,
                    "q8_sha256": MODEL_SHA256,
                    "bytes": model.stat().st_size,
                },
                "runtime": {
                    "repo": RUNTIME_REPO,
                    "commit": RUNTIME_COMMIT,
                    "binary_sha256": sha256_file(binary),
                    "version_stdout": version.stdout.strip(),
                    "version_stderr": version.stderr.strip(),
                    "transcribe_help_sha256": hashlib.sha256(help_tx.stdout.encode()).hexdigest(),
                    "device": "cpu",
                },
                "fixture": {
                    "dataset": FLEURS_REPO,
                    "config": FLEURS_CONFIG,
                    "revision": FLEURS_REVISION,
                    "split": "test",
                    "rows": list(ROWS),
                    "dataset_runtime": dataset_runtime,
                    "selected_rows": [{
                        "row": int(x["row"]),
                        "audio_sha256": x["audio_sha256"],
                        "benchmark_wav_sha256": x["benchmark_wav_sha256"],
                    } for x in speech],
                },
                "external_gate": {
                    "contract_path": GATE_CONTRACT_FILE,
                    "contract_sha256": gate_sha,
                    "deterministic": True,
                    "contract": gate_contract,
                },
                "normalizer": NORMALIZER,
                "streaming_geometry": [
                    {"chunk_ms": ms, "rnnt_right_context": rc} for ms, rc in GEOMETRIES
                ],
                "languages": list(LANGUAGES),
                "configs": configs,
                "deterministic_rerun": det,
                "baselines": BASELINES,
                "measurement_limitations": [
                    "Current NeMo-Speech.cpp directory CLI returns finalized transcripts, not per-token interim events.",
                    "First-stable-token latency and partial-stability therefore remain uncredited in this receipt.",
                    "Batch wall time is recorded; it is not relabeled as per-utterance final latency.",
                    "CPU target execution does not establish GPU, physical-device, room-audio, production endpointing, or whole-voice acceptance.",
                ],
                "pass": True,
            })
            receipt["credits"]["nemotron_target_runtime_credit"] = 1
    except Exception as exc:
        receipt.update({
            "timestamp_completed_utc": utc_now(),
            "classification": "HARNESS_OR_RUNTIME_FAILURE",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt.get("pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
