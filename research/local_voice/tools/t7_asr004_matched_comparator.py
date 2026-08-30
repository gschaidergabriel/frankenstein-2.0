#!/usr/bin/env python3
"""Execute the single routed T7-ASR-004 matched German/noise comparator.

Evidence scope is deliberately narrow:
- exact FLEURS de_de rows 0..31 at the pinned revision;
- Qwen3-ASR-0.6B raw and externally gated;
- faster-whisper 1.2.1 large-v3 raw and the SAME externally gated contract;
- deterministic digital-silence falsifiers.

The tool emits raw per-input results plus exact runtime/artifact identities. It does
not mint Trigger-4, streaming, E2E, whole-product, or training credit.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path
from typing import Any

SCHEMA = "T7_ASR004_COMPARATOR_RECEIPT/v1"
SEMANTIC_KEY = "95bd53a469133dbfdf39da320f6daa049cec1361084e632dc915c4bc156e3715"
FLEURS_REPO = "google/fleurs"
FLEURS_CONFIG = "de_de"
FLEURS_REVISION = "bc0636bc121b131df69ed727a4ddafc5afc8afe4"
ROWS = tuple(range(32))

QWEN_MODEL_ID = "Qwen/Qwen3-ASR-0.6B"
QWEN_MODEL_REVISION = "9ba1d4a"
QWEN_MODEL_FILE = "model.safetensors"
QWEN_MODEL_SHA256 = "79d6cbd4c98c7bbffe9db2edac07f56cd6637d0d5944b27f6c2b8353840323ea"
QWEN_ASR_VERSION = "0.0.6"

WHISPER_PACKAGE = "faster-whisper==1.2.1"
WHISPER_MODEL_REPO = "Systran/faster-whisper-large-v3"
WHISPER_BEAM_SIZE = 5
WHISPER_CPU_THREADS = 2

GATE_PACKAGE = "webrtcvad-wheels==2.0.14"
GATE_CONTRACT_FILE = "t7_asr004_external_gate_contract.json"
VALIDATOR_FILE = "t7_asr004_comparator_receipt_validator.py"

QWEN_RAW = "QWEN3_ASR_DIRECT_RAW_DECODER"
QWEN_GATED = "QWEN3_ASR_WITH_DETERMINISTIC_SPEECH_PRESENCE_VAD_TURN_ADMISSION"
WHISPER_RAW = "MATCHED_FASTER_WHISPER_RAW_DECODER"
WHISPER_GATED = "MATCHED_FASTER_WHISPER_WITH_DETERMINISTIC_SPEECH_PRESENCE_VAD_TURN_ADMISSION"

NORMALIZER = "NFKC_CASEFOLD_PUNCT_SYMBOL_TO_SPACE_COLLAPSE_WS"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def distribution_tree_sha256(distribution_name: str) -> str:
    dist = importlib.metadata.distribution(distribution_name)
    h = hashlib.sha256()
    files = sorted((str(p), p) for p in (dist.files or []))
    for logical, package_path in files:
        resolved = Path(dist.locate_file(package_path))
        if not resolved.is_file():
            continue
        h.update(logical.encode("utf-8"))
        h.update(b"\0")
        h.update(bytes.fromhex(sha256_file(resolved)))
        h.update(b"\n")
    return h.hexdigest()


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=10
        ).strip()
    except Exception:
        return os.environ.get("F2_SOURCE_COMMIT", "")


def max_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value * 1024 if sys.platform.startswith("linux") else value


def write_silence(path: Path, seconds: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * (16000 * seconds))


def load_gate_contract() -> tuple[dict[str, Any], str]:
    path = Path(__file__).resolve().with_name(GATE_CONTRACT_FILE)
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("schema") != "T7_ASR004_EXTERNAL_GATE_CONTRACT/v1":
        raise RuntimeError("external gate contract schema mismatch")
    if doc.get("semantic_key") != SEMANTIC_KEY:
        raise RuntimeError("external gate semantic_key mismatch")
    return doc, sha256_bytes(raw)


def gate_audio(path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf
    import webrtcvad

    t0 = time.perf_counter()
    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) == 2:
        audio = audio.mean(axis=1)
    if int(rate) != int(contract["sample_rate_hz"]):
        raise RuntimeError(f"gate requires {contract['sample_rate_hz']} Hz, observed {rate}")
    audio = np.asarray(audio, dtype=np.float32)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    frame_ms = int(contract["frame_ms"])
    frame_bytes = int(rate * frame_ms / 1000) * 2
    vad = webrtcvad.Vad(int(contract["webrtcvad_mode"]))
    voiced = total = 0
    for offset in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        frame = pcm[offset : offset + frame_bytes]
        total += 1
        voiced += int(bool(vad.is_speech(frame, int(rate))))
    ratio = voiced / total if total else 0.0
    decision = (
        "SPEECH"
        if voiced >= int(contract["minimum_voiced_frames"])
        and ratio >= float(contract["minimum_voiced_ratio"])
        else "NON_SPEECH"
    )
    return {
        "decision": decision,
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
        "voiced_frames": voiced,
        "total_frames": total,
        "voiced_ratio": ratio,
    }


def hypothesis_from_qwen(out: Any) -> str:
    if not out:
        return ""
    text = getattr(out[0], "text", "")
    return "" if text is None else str(text).strip()


def qwen_decode(model: Any, path: Path) -> tuple[str, float]:
    t0 = time.perf_counter()
    out = model.transcribe(audio=str(path), language="German")
    return hypothesis_from_qwen(out), (time.perf_counter() - t0) * 1000.0


def whisper_decode(model: Any, path: Path) -> tuple[str, float]:
    t0 = time.perf_counter()
    segments, _info = model.transcribe(
        str(path),
        language="de",
        beam_size=WHISPER_BEAM_SIZE,
        condition_on_previous_text=False,
        vad_filter=False,
        temperature=0.0,
    )
    text = " ".join(str(seg.text).strip() for seg in segments if str(seg.text).strip()).strip()
    return text, (time.perf_counter() - t0) * 1000.0


def prepare_fixtures(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    from datasets import Audio, load_dataset

    t0 = time.perf_counter()
    ds = load_dataset(
        FLEURS_REPO,
        FLEURS_CONFIG,
        revision=FLEURS_REVISION,
        split="test",
        trust_remote_code=True,
    )
    ds = ds.cast_column("audio", Audio(decode=False))
    speech: list[dict[str, Any]] = []
    speech_dir = root / "speech"
    speech_dir.mkdir(parents=True, exist_ok=True)

    for row in ROWS:
        item = ds[row]
        audio = item["audio"]
        data = audio.get("bytes") if isinstance(audio, dict) else None
        source_path = audio.get("path") if isinstance(audio, dict) else None
        if data is None:
            if not source_path:
                raise RuntimeError(f"FLEURS row {row}: loader exposed neither bytes nor path")
            data = Path(source_path).read_bytes()
        suffix = Path(str(source_path or "")).suffix or ".flac"
        local = speech_dir / f"fleurs_de_de_test_{row:02d}{suffix}"
        local.write_bytes(data)
        transcription = str(item.get("transcription", ""))
        raw_transcription = str(item.get("raw_transcription", transcription))
        stable = {
            key: item.get(key)
            for key in ("id", "path", "num_samples", "gender", "lang_id", "language")
            if key in item
        }
        speech.append(
            {
                "row": row,
                "path": local,
                "audio_sha256": sha256_bytes(data),
                "reference": transcription,
                "raw_transcription": raw_transcription,
                "stable_fields": stable,
            }
        )

    non_speech: list[dict[str, Any]] = []
    ns_dir = root / "non_speech"
    ns_dir.mkdir(parents=True, exist_ok=True)
    for seconds in (1, 2, 5):
        fixture_id = f"digital_silence_{seconds}s"
        path = ns_dir / f"{fixture_id}.wav"
        write_silence(path, seconds)
        non_speech.append(
            {
                "fixture_id": fixture_id,
                "path": path,
                "audio_sha256": sha256_file(path),
                "duration_seconds": seconds,
            }
        )

    return speech, non_speech, {
        "datasets_version": importlib.metadata.version("datasets"),
        "load_seconds": time.perf_counter() - t0,
        "resolved_revision_requested": FLEURS_REVISION,
        "trust_remote_code": True,
    }


def base_speech_record(item: dict[str, Any], variant: str, model_identity: str, runtime_identity: str) -> dict[str, Any]:
    return {
        "fixture_row": int(item["row"]),
        "variant": variant,
        "audio_sha256": item["audio_sha256"],
        "reference": item["reference"],
        "dataset_raw_transcription": item["raw_transcription"],
        "dataset_transcription": item["reference"],
        "hypothesis": "",
        "model_identity": model_identity,
        "runtime_identity": runtime_identity,
        "decoder_latency_ms": 0.0,
        "end_to_end_latency_ms": 0.0,
        "gate_decision": "NOT_APPLICABLE",
        "execution_state": "WARM_MODEL_AFTER_SINGLE_LOAD",
        "peak_rss_bytes_after_record": 0,
    }


def base_non_speech_record(item: dict[str, Any], variant: str) -> dict[str, Any]:
    return {
        "fixture_id": item["fixture_id"],
        "variant": variant,
        "audio_sha256": item["audio_sha256"],
        "hypothesis": "",
        "gate_decision": "NOT_APPLICABLE",
        "decoder_latency_ms": 0.0,
        "end_to_end_latency_ms": 0.0,
    }


def execute_qwen(
    speech: list[dict[str, Any]],
    non_speech: list[dict[str, Any]],
    gate_contract: dict[str, Any],
    gate_sha: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import psutil
    import torch
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    from qwen_asr import Qwen3ASRModel

    process = psutil.Process()
    info = HfApi().model_info(QWEN_MODEL_ID, revision=QWEN_MODEL_REVISION)
    resolved_revision = str(info.sha)
    weight = Path(
        hf_hub_download(
            repo_id=QWEN_MODEL_ID,
            filename=QWEN_MODEL_FILE,
            revision=resolved_revision,
        )
    )
    observed_sha = sha256_file(weight)
    if observed_sha != QWEN_MODEL_SHA256:
        raise RuntimeError(
            f"Qwen model hash mismatch: expected {QWEN_MODEL_SHA256}, got {observed_sha}"
        )
    model_dir = snapshot_download(repo_id=QWEN_MODEL_ID, revision=resolved_revision)
    rss_before = process.memory_info().rss
    t0 = time.perf_counter()
    model = Qwen3ASRModel.from_pretrained(
        model_dir,
        dtype=torch.float32,
        device_map="cpu",
        attn_implementation="sdpa",
        max_inference_batch_size=1,
        max_new_tokens=256,
    )
    model_load_ms = (time.perf_counter() - t0) * 1000.0
    identity = f"{QWEN_MODEL_ID}@{resolved_revision}|{QWEN_MODEL_FILE}:{observed_sha}"
    runtime_identity = (
        f"qwen-asr={importlib.metadata.version('qwen-asr')};"
        f"torch={torch.__version__};python={platform.python_version()};device=cpu;dtype=float32;sdpa"
    )

    speech_records: list[dict[str, Any]] = []
    ns_records: list[dict[str, Any]] = []
    for item in speech:
        raw = base_speech_record(item, QWEN_RAW, identity, runtime_identity)
        raw["hypothesis"], raw["decoder_latency_ms"] = qwen_decode(model, item["path"])
        raw["end_to_end_latency_ms"] = raw["decoder_latency_ms"]
        raw["peak_rss_bytes_after_record"] = max_rss_bytes()
        speech_records.append(raw)

        gated = base_speech_record(item, QWEN_GATED, identity, runtime_identity)
        gate = gate_audio(item["path"], gate_contract)
        gated["gate_decision"] = gate["decision"]
        gated["gate_latency_ms"] = gate["latency_ms"]
        gated["gate_voiced_frames"] = gate["voiced_frames"]
        gated["gate_total_frames"] = gate["total_frames"]
        gated["gate_voiced_ratio"] = gate["voiced_ratio"]
        gated["external_gate_contract_sha256"] = gate_sha
        if gate["decision"] == "SPEECH":
            gated["hypothesis"], gated["decoder_latency_ms"] = qwen_decode(model, item["path"])
        gated["end_to_end_latency_ms"] = gate["latency_ms"] + gated["decoder_latency_ms"]
        gated["peak_rss_bytes_after_record"] = max_rss_bytes()
        speech_records.append(gated)

    for item in non_speech:
        raw = base_non_speech_record(item, QWEN_RAW)
        raw["hypothesis"], raw["decoder_latency_ms"] = qwen_decode(model, item["path"])
        raw["end_to_end_latency_ms"] = raw["decoder_latency_ms"]
        raw["model_identity"] = identity
        raw["runtime_identity"] = runtime_identity
        ns_records.append(raw)

        gated = base_non_speech_record(item, QWEN_GATED)
        gate = gate_audio(item["path"], gate_contract)
        gated["gate_decision"] = gate["decision"]
        gated["gate_latency_ms"] = gate["latency_ms"]
        gated["gate_voiced_frames"] = gate["voiced_frames"]
        gated["gate_total_frames"] = gate["total_frames"]
        gated["gate_voiced_ratio"] = gate["voiced_ratio"]
        gated["external_gate_contract_sha256"] = gate_sha
        gated["model_identity"] = identity
        gated["runtime_identity"] = runtime_identity
        if gate["decision"] == "SPEECH":
            gated["hypothesis"], gated["decoder_latency_ms"] = qwen_decode(model, item["path"])
        gated["end_to_end_latency_ms"] = gate["latency_ms"] + gated["decoder_latency_ms"]
        ns_records.append(gated)

    metrics = {
        "model_id": QWEN_MODEL_ID,
        "requested_revision": QWEN_MODEL_REVISION,
        "resolved_revision": resolved_revision,
        "primary_artifact": QWEN_MODEL_FILE,
        "primary_artifact_sha256": observed_sha,
        "qwen_asr_version": importlib.metadata.version("qwen-asr"),
        "torch_version": torch.__version__,
        "device": "cpu",
        "dtype": "float32",
        "attn_implementation": "sdpa",
        "rss_before_load_bytes": rss_before,
        "rss_after_benchmark_bytes": process.memory_info().rss,
        "peak_rss_bytes": max_rss_bytes(),
        "model_load_ms": model_load_ms,
    }
    del model
    gc.collect()
    return speech_records, ns_records, metrics


def execute_whisper(
    speech: list[dict[str, Any]],
    non_speech: list[dict[str, Any]],
    gate_contract: dict[str, Any],
    gate_sha: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    import ctranslate2
    import psutil
    from faster_whisper import WhisperModel
    from huggingface_hub import HfApi, snapshot_download

    process = psutil.Process()
    info = HfApi().model_info(WHISPER_MODEL_REPO, revision="main")
    resolved_revision = str(info.sha)
    model_dir = Path(snapshot_download(repo_id=WHISPER_MODEL_REPO, revision=resolved_revision))
    artifact_files = []
    for path in sorted(p for p in model_dir.rglob("*") if p.is_file()):
        artifact_files.append(
            {
                "relative_path": str(path.relative_to(model_dir)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    if not artifact_files:
        raise RuntimeError("faster-whisper model snapshot contained no files")
    package_tree_sha = distribution_tree_sha256("faster-whisper")
    threads = min(WHISPER_CPU_THREADS, max(int(os.cpu_count() or 1), 1))
    rss_before = process.memory_info().rss
    t0 = time.perf_counter()
    model = WhisperModel(
        str(model_dir),
        device="cpu",
        compute_type="int8",
        cpu_threads=threads,
    )
    model_load_ms = (time.perf_counter() - t0) * 1000.0
    identity = f"{WHISPER_MODEL_REPO}@{resolved_revision}"
    runtime_identity = (
        f"faster-whisper={importlib.metadata.version('faster-whisper')};"
        f"ctranslate2={ctranslate2.__version__};python={platform.python_version()};"
        f"device=cpu;compute_type=int8;beam=5;threads={threads};language=de"
    )

    speech_records: list[dict[str, Any]] = []
    ns_records: list[dict[str, Any]] = []
    for item in speech:
        raw = base_speech_record(item, WHISPER_RAW, identity, runtime_identity)
        raw["hypothesis"], raw["decoder_latency_ms"] = whisper_decode(model, item["path"])
        raw["end_to_end_latency_ms"] = raw["decoder_latency_ms"]
        raw["peak_rss_bytes_after_record"] = max_rss_bytes()
        speech_records.append(raw)

        gated = base_speech_record(item, WHISPER_GATED, identity, runtime_identity)
        gate = gate_audio(item["path"], gate_contract)
        gated["gate_decision"] = gate["decision"]
        gated["gate_latency_ms"] = gate["latency_ms"]
        gated["gate_voiced_frames"] = gate["voiced_frames"]
        gated["gate_total_frames"] = gate["total_frames"]
        gated["gate_voiced_ratio"] = gate["voiced_ratio"]
        gated["external_gate_contract_sha256"] = gate_sha
        if gate["decision"] == "SPEECH":
            gated["hypothesis"], gated["decoder_latency_ms"] = whisper_decode(model, item["path"])
        gated["end_to_end_latency_ms"] = gate["latency_ms"] + gated["decoder_latency_ms"]
        gated["peak_rss_bytes_after_record"] = max_rss_bytes()
        speech_records.append(gated)

    for item in non_speech:
        raw = base_non_speech_record(item, WHISPER_RAW)
        raw["hypothesis"], raw["decoder_latency_ms"] = whisper_decode(model, item["path"])
        raw["end_to_end_latency_ms"] = raw["decoder_latency_ms"]
        raw["model_identity"] = identity
        raw["runtime_identity"] = runtime_identity
        ns_records.append(raw)

        gated = base_non_speech_record(item, WHISPER_GATED)
        gate = gate_audio(item["path"], gate_contract)
        gated["gate_decision"] = gate["decision"]
        gated["gate_latency_ms"] = gate["latency_ms"]
        gated["gate_voiced_frames"] = gate["voiced_frames"]
        gated["gate_total_frames"] = gate["total_frames"]
        gated["gate_voiced_ratio"] = gate["voiced_ratio"]
        gated["external_gate_contract_sha256"] = gate_sha
        gated["model_identity"] = identity
        gated["runtime_identity"] = runtime_identity
        if gate["decision"] == "SPEECH":
            gated["hypothesis"], gated["decoder_latency_ms"] = whisper_decode(model, item["path"])
        gated["end_to_end_latency_ms"] = gate["latency_ms"] + gated["decoder_latency_ms"]
        ns_records.append(gated)

    baseline = {
        "package": WHISPER_PACKAGE,
        "model_repo": WHISPER_MODEL_REPO,
        "model_revision": resolved_revision,
        "artifact_sha256": [x["sha256"] for x in artifact_files],
        "device": "cpu",
        "compute_type": "int8",
        "beam_size": WHISPER_BEAM_SIZE,
        "language": "de",
        "condition_on_previous_text": False,
        "raw_vad_filter": False,
        "effective_cpu_threads": threads,
        "ctranslate2_version": ctranslate2.__version__,
        "runtime_version": importlib.metadata.version("faster-whisper"),
        "package_source_sha256": package_tree_sha,
        "package_source_digest_kind": "INSTALLED_DISTRIBUTION_TREE_SHA256",
    }
    metrics = {
        "model_repo": WHISPER_MODEL_REPO,
        "resolved_revision": resolved_revision,
        "artifact_files": artifact_files,
        "rss_before_load_bytes": rss_before,
        "rss_after_benchmark_bytes": process.memory_info().rss,
        "peak_rss_bytes": max_rss_bytes(),
        "model_load_ms": model_load_ms,
        "temperature": 0.0,
    }
    del model
    gc.collect()
    return speech_records, ns_records, metrics, baseline


def run_inside_venv(output: Path) -> int:
    started = utc_now()
    try:
        gate_contract, gate_sha = load_gate_contract()
        validator_path = Path(__file__).resolve().with_name(VALIDATOR_FILE)
        evaluator_sha = sha256_file(validator_path)
        with tempfile.TemporaryDirectory(prefix="t7-asr004-comparator-data-") as tmp:
            root = Path(tmp)
            speech, non_speech, dataset_runtime = prepare_fixtures(root)
            q_speech, q_ns, q_runtime = execute_qwen(
                speech, non_speech, gate_contract, gate_sha
            )
            w_speech, w_ns, w_runtime, baseline = execute_whisper(
                speech, non_speech, gate_contract, gate_sha
            )
            receipt = {
                "schema": SCHEMA,
                "semantic_key": SEMANTIC_KEY,
                "timestamp_started_utc": started,
                "timestamp_completed_utc": utc_now(),
                "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                "source_repo_commit": git_head(),
                "evidence_scope": "TARGET_RUNTIME_COMPONENT_MATCHED_COMPARATOR",
                "target_surface": "clay-direct-dev",
                "execution_observed": True,
                "fixture": {
                    "dataset": FLEURS_REPO,
                    "config": FLEURS_CONFIG,
                    "revision": FLEURS_REVISION,
                    "split": "test",
                    "rows": list(ROWS),
                    "dataset_runtime": dataset_runtime,
                    "selected_rows": [
                        {
                            "row": x["row"],
                            "audio_sha256": x["audio_sha256"],
                            "stable_fields": x["stable_fields"],
                        }
                        for x in speech
                    ],
                },
                "evaluator": {
                    "normalizer": NORMALIZER,
                    "source_path": validator_path.name,
                    "source_sha256": evaluator_sha,
                },
                "external_gate": {
                    "contract_path": GATE_CONTRACT_FILE,
                    "contract_sha256": gate_sha,
                    "deterministic": True,
                    "contract": gate_contract,
                    "package": GATE_PACKAGE,
                    "package_runtime_version": importlib.metadata.version("webrtcvad-wheels"),
                },
                "faster_whisper_baseline": baseline,
                "qwen_runtime": q_runtime,
                "faster_whisper_runtime": w_runtime,
                "speech_records": sorted(
                    q_speech + w_speech,
                    key=lambda r: (int(r["fixture_row"]), str(r["variant"])),
                ),
                "non_speech_records": sorted(
                    q_ns + w_ns,
                    key=lambda r: (str(r["fixture_id"]), str(r["variant"])),
                ),
                "network_model_inference_calls": 0,
                "network_asr_inference_calls": 0,
                "network_tts_inference_calls": 0,
                "official_qwen_vllm_streaming_tested": False,
                "german_e2e_voice_credit": 0,
                "streaming_credit": 0,
                "trigger4_acceptance_credit": 0,
                "whole_system_credit": 0,
                "training_credit": 0,
                "release_policy": "KEEP_QUALITY_SCOPE_OPEN_UNTIL_COMPARATOR_RESULT_EXISTS",
                "classification": "MATCHED_COMPARATOR_EXECUTED_RECEIPT_REQUIRES_VALIDATION_AND_TRIGGER7_INTERPRETATION",
                "pass": True,
            }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        failure = {
            "schema": "T7_ASR004_COMPARATOR_EXECUTION_FAILURE/v1",
            "semantic_key": SEMANTIC_KEY,
            "timestamp_utc": utc_now(),
            "source_repo_commit": git_head(),
            "execution_observed": True,
            "classification": "COMPARATOR_EXECUTION_FAILED_NO_QUALITY_CREDIT",
            "exception_type": type(exc).__name__,
            "exception": str(exc)[:4000],
            "traceback_tail": traceback.format_exc()[-8000:],
            "runtime_credit_delta": 0,
            "german_asr_quality_credit": 0,
            "trigger4_acceptance_credit": 0,
            "whole_system_credit": 0,
            "pass": False,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 2


def bootstrap_and_reexec(output: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="t7-asr004-comparator-venv-") as tmp:
        venv = Path(tmp) / "venv"
        env = os.environ.copy()
        env["HF_HOME"] = str(Path(tmp) / "hf")
        env["HF_DATASETS_CACHE"] = str(Path(tmp) / "datasets")
        env["PIP_CACHE_DIR"] = str(Path(tmp) / "pip")
        env["TOKENIZERS_PARALLELISM"] = "false"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["OMP_NUM_THREADS"] = str(WHISPER_CPU_THREADS)
        env["T7_ASR004_IN_VENV"] = "1"
        create = subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if create.returncode != 0:
            raise RuntimeError(f"venv creation failed: {create.stderr[-2000:]}")
        python = venv / "bin" / "python"
        install = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"qwen-asr=={QWEN_ASR_VERSION}",
                "faster-whisper==1.2.1",
                "webrtcvad-wheels==2.0.14",
                "datasets==3.6.0",
                "soundfile",
                "psutil",
            ],
            env=env,
            text=True,
            capture_output=True,
            timeout=1800,
            check=False,
        )
        if install.returncode != 0:
            failure = {
                "schema": "T7_ASR004_COMPARATOR_EXECUTION_FAILURE/v1",
                "semantic_key": SEMANTIC_KEY,
                "timestamp_utc": utc_now(),
                "classification": "DEPENDENCY_INSTALL_FAILED_NO_QUALITY_CREDIT",
                "pip_returncode": install.returncode,
                "pip_stderr_tail": install.stderr[-8000:],
                "runtime_credit_delta": 0,
                "german_asr_quality_credit": 0,
                "trigger4_acceptance_credit": 0,
                "whole_system_credit": 0,
                "pass": False,
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
            return 2
        child = subprocess.run(
            [str(python), str(Path(__file__).resolve()), "--output", str(output.resolve())],
            env=env,
            text=True,
            timeout=7200,
            check=False,
        )
        return int(child.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("T7_ASR004_IN_VENV") == "1":
        return run_inside_venv(args.output)
    try:
        return bootstrap_and_reexec(args.output)
    except Exception as exc:
        failure = {
            "schema": "T7_ASR004_COMPARATOR_EXECUTION_FAILURE/v1",
            "semantic_key": SEMANTIC_KEY,
            "timestamp_utc": utc_now(),
            "classification": "BOOTSTRAP_FAILED_NO_QUALITY_CREDIT",
            "exception_type": type(exc).__name__,
            "exception": str(exc)[:4000],
            "traceback_tail": traceback.format_exc()[-8000:],
            "runtime_credit_delta": 0,
            "german_asr_quality_credit": 0,
            "trigger4_acceptance_credit": 0,
            "whole_system_credit": 0,
            "pass": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
