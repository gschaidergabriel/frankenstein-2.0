#!/usr/bin/env python3
"""Bounded Trigger-7 target-runtime probe for Qwen3-ASR-0.6B.

This tool is intentionally component-scoped. It may download the pinned open model artifact
and Python package, verify the exact model hash, load the model locally, and run one local
silence inference. It never awards German quality, streaming, E2E, or Trigger-4 credit.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path

SCHEMA = "frankenstein.trigger7.qwen3_asr_target_probe.v2"
MODEL_ID = "Qwen/Qwen3-ASR-0.6B"
MODEL_REVISION = "9ba1d4a"
MODEL_FILE = "model.safetensors"
EXPECTED_MODEL_SHA256 = "79d6cbd4c98c7bbffe9db2edac07f56cd6637d0d5944b27f6c2b8353840323ea"
QWEN_ASR_VERSION = "0.0.6"
SOURCE_REPO_COMMIT = "7c6daf77a2421100f5fb066495372c00129d39ff"
SEMANTIC_KEY = "95bd53a469133dbfdf39da320f6daa049cec1361084e632dc915c4bc156e3715"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def mem_available_kib() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except Exception:
        return None
    return None


def base_receipt() -> dict:
    return {
        "schema": SCHEMA,
        "timestamp_utc": utc_now(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "semantic_key": SEMANTIC_KEY,
        "source_repo_commit": SOURCE_REPO_COMMIT,
        "model_id": MODEL_ID,
        "model_revision_requested": MODEL_REVISION,
        "model_file": MODEL_FILE,
        "model_sha256_expected": EXPECTED_MODEL_SHA256,
        "qwen_asr_version_expected": QWEN_ASR_VERSION,
        "platform": platform.platform(),
        "python": sys.version,
        "cpu_count_logical": os.cpu_count(),
        "mem_available_before_kib": mem_available_kib(),
        "execution_observed": True,
        "artifact_hash_verified": False,
        "model_load_observed": False,
        "inference_observed": False,
        "german_quality_credit": 0,
        "streaming_credit": 0,
        "german_e2e_credit": 0,
        "trigger4_acceptance_credit": 0,
        "whole_system_credit": 0,
        "network_model_inference_calls": 0,
        "network_asr_inference_calls": 0,
        "network_tts_inference_calls": 0,
        "official_streaming_backend_tested": False,
        "evidence_scope": "TARGET_RUNTIME_MODEL_BENCHMARK_PARTIAL",
    }


def emit(receipt: dict) -> None:
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_inside_venv() -> int:
    receipt = base_receipt()
    try:
        import psutil
        import torch
        from huggingface_hub import hf_hub_download, snapshot_download
        from qwen_asr import Qwen3ASRModel

        receipt["torch_version"] = torch.__version__
        try:
            receipt["qwen_asr_version_observed"] = importlib.metadata.version("qwen-asr")
        except Exception:
            receipt["qwen_asr_version_observed"] = None
        receipt["cuda_available"] = bool(torch.cuda.is_available())
        receipt["cuda_device_count"] = int(torch.cuda.device_count())

        t0 = time.perf_counter()
        weight = Path(
            hf_hub_download(
                repo_id=MODEL_ID,
                filename=MODEL_FILE,
                revision=MODEL_REVISION,
            )
        )
        receipt["weight_download_seconds"] = time.perf_counter() - t0
        receipt["model_bytes_observed"] = weight.stat().st_size
        receipt["model_sha256_observed"] = sha256_file(weight)
        receipt["artifact_hash_verified"] = (
            receipt["model_sha256_observed"] == EXPECTED_MODEL_SHA256
        )
        if not receipt["artifact_hash_verified"]:
            receipt["classification"] = "ARTIFACT_HASH_MISMATCH_FAIL_CLOSED"
            receipt["pass"] = False
            emit(receipt)
            return 0

        model_dir = snapshot_download(repo_id=MODEL_ID, revision=MODEL_REVISION)
        process = psutil.Process()
        receipt["rss_before_load_bytes"] = process.memory_info().rss
        t1 = time.perf_counter()
        model = Qwen3ASRModel.from_pretrained(
            model_dir,
            dtype=torch.float32,
            device_map="cpu",
            attn_implementation="sdpa",
            max_inference_batch_size=1,
            max_new_tokens=32,
        )
        receipt["model_load_seconds"] = time.perf_counter() - t1
        receipt["model_load_observed"] = True
        receipt["rss_after_load_bytes"] = process.memory_info().rss
        receipt["mem_available_after_load_kib"] = mem_available_kib()

        silence = Path(os.environ["HF_HOME"]) / "silence_1s_16k.wav"
        with wave.open(str(silence), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 16000)

        t2 = time.perf_counter()
        out = model.transcribe(audio=str(silence), language="German")
        receipt["silence_inference_seconds"] = time.perf_counter() - t2
        receipt["inference_observed"] = True
        receipt["silence_output_language"] = getattr(out[0], "language", None) if out else None
        receipt["silence_output_text"] = getattr(out[0], "text", None) if out else None
        receipt["rss_after_inference_bytes"] = process.memory_info().rss
        receipt["max_rss_kib"] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        receipt["mem_available_after_inference_kib"] = mem_available_kib()
        receipt["official_streaming_backend_reason"] = (
            "THIS_BOUND_PROBE_ESTABLISHES_EXACT_TRANSFORMERS_CPU_LOAD_AND_LOCAL_INFERENCE_ONLY; "
            "THE_OFFICIAL_VLLM_STREAMING_PATH_REMAINS_A_SEPARATE_GATE"
        )
        receipt["classification"] = (
            "TARGET_RUNTIME_MODEL_LOAD_AND_LOCAL_INFERENCE_OBSERVED_PARTIAL_SCOPE"
        )
        receipt["pass"] = True
    except Exception as exc:
        receipt["classification"] = "TARGET_RUNTIME_PROBE_EXCEPTION"
        receipt["exception_type"] = type(exc).__name__
        receipt["exception"] = str(exc)[:2000]
        receipt["traceback_tail"] = traceback.format_exc()[-4000:]
        receipt["mem_available_on_exception_kib"] = mem_available_kib()
        receipt["pass"] = False
    emit(receipt)
    return 0


def bootstrap_and_reexec() -> int:
    with tempfile.TemporaryDirectory(prefix="t7-qwen3-asr-") as tmp:
        root = Path(tmp)
        venv = root / "venv"
        env = os.environ.copy()
        env["HF_HOME"] = str(root / "hf")
        env["TRANSFORMERS_CACHE"] = str(root / "hf" / "transformers")
        env["PIP_CACHE_DIR"] = str(root / "pip-cache")
        env["TOKENIZERS_PARALLELISM"] = "false"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["T7_QWEN3_ASR_IN_VENV"] = "1"

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
        except Exception as exc:
            receipt = base_receipt()
            receipt.update(
                classification="BLOCKED_VENV_CREATION",
                bootstrap_exception=type(exc).__name__ + ": " + str(exc)[:1000],
                pass=False,
            )
            emit(receipt)
            return 0

        python = venv / "bin" / "python"
        install = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"qwen-asr=={QWEN_ASR_VERSION}",
                "psutil",
            ],
            env=env,
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
        if install.returncode != 0:
            receipt = base_receipt()
            receipt.update(
                classification="DEPENDENCY_INSTALL_FAILED",
                pip_returncode=install.returncode,
                pip_stderr_tail=install.stderr[-4000:],
                pass=False,
            )
            emit(receipt)
            return 0

        child = subprocess.run(
            [str(python), str(Path(__file__).resolve())],
            env=env,
            text=True,
            capture_output=True,
            timeout=1200,
            check=False,
        )
        if child.stdout.strip():
            print(child.stdout.strip())
            return 0
        receipt = base_receipt()
        receipt.update(
            classification="CHILD_PROBE_FAILED_BEFORE_JSON_RECEIPT",
            child_returncode=child.returncode,
            child_stderr_tail=child.stderr[-4000:],
            pass=False,
        )
        emit(receipt)
        return 0


def main() -> int:
    if os.environ.get("T7_QWEN3_ASR_IN_VENV") == "1":
        return run_inside_venv()
    return bootstrap_and_reexec()


if __name__ == "__main__":
    raise SystemExit(main())
