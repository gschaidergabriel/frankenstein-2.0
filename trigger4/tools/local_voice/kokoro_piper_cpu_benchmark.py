#!/usr/bin/env python3
"""Bounded CPU/file-output benchmark for Trigger-4 Kokoro-vs-Piper routing."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import resource
import socket
import sys
import tempfile
import time
import traceback
from typing import Any

KOKORO_MODEL_REV = "734e593d320a3d876bede7020f773dfd481a0cc7"
KOKORO_MODEL_SHA256 = "36dde15c4a800cfd1ab540ccb4476dbab604fe03ff7c937d976ebbf3b49e59ce"
KOKORO_VOICE_SHA256 = "9d98b775ebce1cfc369e8f9a3ee8ee260cd612dffb477cba85749112362306d7"
KOKORO_RUNTIME_COMMIT = "b96fef95e6a746495f92443fac7c688f90fc57fc"
MISAKI_COMMIT = "6d252a2e02f3b030f22f56686f1a73786c16ffc8"
PIPER_MODEL_REV = "4c56824d7a76ee98b08a6e9046e640727397fac7"
PIPER_MODEL_SHA256 = "7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819"
PIPER_RUNTIME_VERSION = "1.7.0"
PIPER_RUNTIME_SOURCE_COMMIT = "7b8e8f7197a480047677715f00d3d78903b55a2a"

FIXTURES: list[tuple[str, list[str]]] = [
    ("conversation", ["Hallo, hier spricht Thorsten. Das ist ein lokaler CPU-Test."]),
    ("umlauts_short_ue", ["Zwei weiße Zwerge gehen über die Brücke und grüßen höflich."]),
    ("ich_ach", ["Ich mache mich auf den Weg nach Aachen und bleibe nachts wach."]),
    ("numbers_dates", ["Am 31. August 2026 verarbeitet das System 42 Aufgaben um 20 Uhr 15."]),
    ("technical", ["Die API liest JSON für EntityOS, HCU und Frankenstein vollständig lokal."]),
    ("hyphenated", ["Das atmosphärisch-optische Echtzeit-System prüft einen CPU-Datei-Ausgabe-Test."]),
    (
        "long_segmented",
        [
            "Dies ist der erste deterministisch getrennte Satz für eine lange Eingabe.",
            "Der zweite Satz enthält Umlaute, Zahlen wie 123 und technische Begriffe wie JSON.",
            "Der dritte Satz prüft Frankenstein, EntityOS und HCU ohne externe Inferenz.",
            "Der vierte Satz beendet die lange Eingabe kontrolliert und vollständig.",
        ],
    ),
]


def sha256_file(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require_hash(path: str, expected: str, label: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f"{label}_MISSING:{p}")
    actual = sha256_file(p)
    if actual != expected:
        raise RuntimeError(f"{label}_HASH_MISMATCH:{actual}!={expected}")
    return {"path": str(p), "sha256": actual, "bytes": p.stat().st_size}


def direct_url(dist_name: str) -> dict[str, Any] | None:
    dist = metadata.distribution(dist_name)
    raw = dist.read_text("direct_url.json")
    return json.loads(raw) if raw else None


def verify_vcs_pin(dist_name: str, expected_commit: str) -> dict[str, Any]:
    data = direct_url(dist_name)
    if not data:
        raise RuntimeError(f"{dist_name}_DIRECT_URL_MISSING")
    commit = (((data.get("vcs_info") or {}).get("commit_id")) or "").lower()
    if commit != expected_commit.lower():
        raise RuntimeError(f"{dist_name}_VCS_PIN_MISMATCH:{commit}!={expected_commit}")
    return data


def selected_versions() -> dict[str, str | None]:
    names = [
        "kokoro",
        "misaki",
        "torch",
        "transformers",
        "huggingface-hub",
        "numpy",
        "soundfile",
        "loguru",
        "piper-tts",
        "onnxruntime",
        "phonemizer-fork",
        "espeakng-loader",
    ]
    result: dict[str, str | None] = {}
    for name in names:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def install_network_guard(attempts: list[str]) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    real_socket = socket.socket

    class GuardedSocket(real_socket):
        def connect(self, address: Any) -> Any:
            attempts.append(repr(address))
            raise RuntimeError(f"NETWORK_BLOCKED_DURING_BENCHMARK:{address!r}")

        def connect_ex(self, address: Any) -> int:
            attempts.append(repr(address))
            return 111

    def blocked_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        attempts.append(repr(address))
        raise RuntimeError(f"NETWORK_BLOCKED_DURING_BENCHMARK:{address!r}")

    socket.socket = GuardedSocket
    socket.create_connection = blocked_create_connection


def max_rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def write_audio(path: Path, audio: Any, sample_rate: int) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf

    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 1:
        array = array.reshape(-1)
    if array.size <= 0:
        raise RuntimeError("EMPTY_AUDIO_ARRAY")
    if not np.isfinite(array).all():
        raise RuntimeError("NONFINITE_AUDIO_ARRAY")
    sf.write(path, array, sample_rate, subtype="PCM_16")
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError("LOCAL_WAV_NOT_CREATED")
    return {
        "sample_rate": int(sample_rate),
        "samples": int(array.size),
        "generated_audio_seconds": float(array.size / sample_rate),
        "output_file_bytes": int(path.stat().st_size),
        "output_sha256": sha256_file(path),
    }


def load_kokoro(paths: dict[str, str], short_ue_counter: dict[str, int]):
    import torch
    from kokoro import KModel, KPipeline

    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    model = KModel(
        repo_id="hexgrad/Kokoro-82M",
        config=paths["config"],
        model=paths["model"],
    ).to("cpu").eval()
    pipeline = KPipeline(
        lang_code="d",
        repo_id="hexgrad/Kokoro-82M",
        model=model,
        device="cpu",
    )
    original_g2p = pipeline.g2p

    def patched_g2p(text: str):
        phonemes, tokens = original_g2p(text)
        count = phonemes.count("ʏ")
        if count:
            short_ue_counter["substitutions"] += count
        return phonemes.replace("ʏ", "y"), tokens

    pipeline.g2p = patched_g2p
    voice = torch.load(paths["voice"], map_location="cpu", weights_only=True)
    return model, pipeline, voice


def load_piper(paths: dict[str, str]):
    from piper import PiperVoice

    return PiperVoice.load(
        paths["model"],
        config_path=paths["config"],
        use_cuda=False,
    )


def measure_load(loader):
    start = time.perf_counter()
    obj = loader()
    return obj, time.perf_counter() - start


def benchmark_kokoro(paths: dict[str, str], outdir: Path) -> tuple[dict[str, Any], dict[str, int]]:
    import numpy as np

    short_ue = {"substitutions": 0}
    loaded, cold = measure_load(lambda: load_kokoro(paths, short_ue))
    del loaded
    gc.collect()

    loaded, warm = measure_load(lambda: load_kokoro(paths, short_ue))
    model, pipeline, voice = loaded

    fixtures: list[dict[str, Any]] = []
    for name, segments in FIXTURES:
        audio_parts = []
        first_chunk_ms = None
        t0 = time.perf_counter()
        for segment in segments:
            iterator = pipeline(segment, voice=voice, speed=1.0)
            while True:
                chunk_start = time.perf_counter()
                try:
                    result = next(iterator)
                except StopIteration:
                    break
                if first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - chunk_start) * 1000.0
                if result.audio is not None:
                    audio_parts.append(result.audio.detach().cpu().numpy())
        wall = time.perf_counter() - t0
        if not audio_parts:
            raise RuntimeError(f"KOKORO_NO_AUDIO:{name}")
        audio = np.concatenate(audio_parts)
        wav = outdir / f"kokoro_{name}.wav"
        meta = write_audio(wav, audio, 24000)
        fixtures.append(
            {
                "fixture": name,
                "segments": len(segments),
                "synthesis_wall_seconds": wall,
                "time_to_first_generated_audio_chunk_ms": first_chunk_ms,
                "realtime_factor": wall / meta["generated_audio_seconds"],
                "failure_or_truncation_class": (
                    "DETERMINISTIC_SEGMENTATION_APPLIED"
                    if len(segments) > 1
                    else "NONE_OBSERVED_AT_FILE_OUTPUT_SCOPE"
                ),
                **meta,
            }
        )
    del model, pipeline, voice
    gc.collect()
    return {
        "cold_load_seconds": cold,
        "warm_load_seconds": warm,
        "fixtures": fixtures,
        "output_sample_rate": 24000,
    }, short_ue


def benchmark_piper(paths: dict[str, str], outdir: Path) -> dict[str, Any]:
    import numpy as np

    voice, cold = measure_load(lambda: load_piper(paths))
    del voice
    gc.collect()

    voice, warm = measure_load(lambda: load_piper(paths))
    fixtures: list[dict[str, Any]] = []
    for name, segments in FIXTURES:
        audio_parts = []
        sample_rate = None
        first_chunk_ms = None
        t0 = time.perf_counter()
        for segment in segments:
            iterator = iter(voice.synthesize(segment))
            while True:
                chunk_start = time.perf_counter()
                try:
                    chunk = next(iterator)
                except StopIteration:
                    break
                if first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - chunk_start) * 1000.0
                sample_rate = int(chunk.sample_rate)
                audio_parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
        wall = time.perf_counter() - t0
        if not audio_parts or not sample_rate:
            raise RuntimeError(f"PIPER_NO_AUDIO:{name}")
        audio = np.concatenate(audio_parts)
        wav = outdir / f"piper_{name}.wav"
        meta = write_audio(wav, audio, sample_rate)
        fixtures.append(
            {
                "fixture": name,
                "segments": len(segments),
                "synthesis_wall_seconds": wall,
                "time_to_first_generated_audio_chunk_ms": first_chunk_ms,
                "realtime_factor": wall / meta["generated_audio_seconds"],
                "failure_or_truncation_class": (
                    "DETERMINISTIC_SEGMENTATION_APPLIED"
                    if len(segments) > 1
                    else "NONE_OBSERVED_AT_FILE_OUTPUT_SCOPE"
                ),
                **meta,
            }
        )
    del voice
    gc.collect()
    return {
        "cold_load_seconds": cold,
        "warm_load_seconds": warm,
        "fixtures": fixtures,
        "output_sample_rate": fixtures[0]["sample_rate"] if fixtures else None,
    }


def build_base(engine: str, network_attempts: list[str]) -> dict[str, Any]:
    return {
        "schema": "T4_LOCAL_VOICE_CPU_ENGINE_BENCHMARK/v1",
        "research_id": "T7-TTS-KOKORO-001",
        "objective": "E3_THORSTEN_KOKORO_82M_VS_PIPER_GERMAN_CPU_FILE_OUTPUT",
        "engine": engine,
        "evidence_scope": "CPU_FILE_OUTPUT_COMPONENT_ONLY",
        "sandbox_tier": "S1_OCI",
        "runtime_mode": "LOCAL_SOLO",
        "device": "CPU_ONLY",
        "requires_audio_output_device": False,
        "pins": {
            "kokoro_model_revision": KOKORO_MODEL_REV,
            "kokoro_model_sha256": KOKORO_MODEL_SHA256,
            "kokoro_voice_sha256": KOKORO_VOICE_SHA256,
            "kokoro_runtime_commit": KOKORO_RUNTIME_COMMIT,
            "misaki_commit": MISAKI_COMMIT,
            "piper_model_revision": PIPER_MODEL_REV,
            "piper_model_sha256": PIPER_MODEL_SHA256,
            "piper_runtime_version": PIPER_RUNTIME_VERSION,
            "piper_runtime_source_commit": PIPER_RUNTIME_SOURCE_COMMIT,
        },
        "package_versions": selected_versions(),
        "network_guard": {
            "enabled_during_synthesis": True,
            "attempts": network_attempts,
            "outbound_model_api_calls": 0,
            "outbound_asr_api_calls": 0,
            "outbound_tts_api_calls": 0,
        },
        "credits": {
            "cpu_file_output_component": 0,
            "audible_playback": 0,
            "first_audio_played_latency": 0,
            "cancellation_to_silence": 0,
            "heard_output_correctness": 0,
            "blind_quality_parity": 0,
            "stable_male_identity_runtime_quality": 0,
            "german_e2e_voice": 0,
            "trigger4_f2_acceptance": 0,
            "whole_system": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["kokoro", "piper"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--kokoro-config", required=True)
    parser.add_argument("--kokoro-model", required=True)
    parser.add_argument("--kokoro-voice", required=True)
    parser.add_argument("--piper-model", required=True)
    parser.add_argument("--piper-config", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    network_attempts: list[str] = []
    receipt = build_base(args.engine, network_attempts)

    try:
        artifacts = {
            "kokoro_model": require_hash(args.kokoro_model, KOKORO_MODEL_SHA256, "KOKORO_MODEL"),
            "kokoro_voice": require_hash(args.kokoro_voice, KOKORO_VOICE_SHA256, "KOKORO_VOICE"),
            "piper_model": require_hash(args.piper_model, PIPER_MODEL_SHA256, "PIPER_MODEL"),
            "kokoro_config": {
                "path": args.kokoro_config,
                "sha256": sha256_file(args.kokoro_config),
                "bytes": Path(args.kokoro_config).stat().st_size,
            },
            "piper_config": {
                "path": args.piper_config,
                "sha256": sha256_file(args.piper_config),
                "bytes": Path(args.piper_config).stat().st_size,
            },
        }
        receipt["artifacts"] = artifacts
        receipt["vcs_direct_urls"] = {
            "kokoro": verify_vcs_pin("kokoro", KOKORO_RUNTIME_COMMIT),
            "misaki": verify_vcs_pin("misaki", MISAKI_COMMIT),
        }
        if metadata.version("piper-tts") != PIPER_RUNTIME_VERSION:
            raise RuntimeError(
                f"PIPER_RUNTIME_VERSION_MISMATCH:{metadata.version('piper-tts')}!={PIPER_RUNTIME_VERSION}"
            )

        install_network_guard(network_attempts)
        with tempfile.TemporaryDirectory(prefix=f"t4-{args.engine}-") as td:
            outdir = Path(td)
            if args.engine == "kokoro":
                result, short_ue = benchmark_kokoro(
                    {
                        "config": args.kokoro_config,
                        "model": args.kokoro_model,
                        "voice": args.kokoro_voice,
                    },
                    outdir,
                )
                receipt["g2p_observation"] = {
                    "short_ue_U+028F_substitutions": short_ue["substitutions"],
                    "workaround": "U+028F_TO_y_AS_UPSTREAM_MODEL_CARD",
                }
            else:
                result = benchmark_piper(
                    {"model": args.piper_model, "config": args.piper_config},
                    outdir,
                )

        if network_attempts:
            raise RuntimeError(f"NETWORK_ATTEMPT_DURING_SYNTHESIS:{network_attempts!r}")
        receipt.update(result)
        receipt["peak_rss_bytes"] = max_rss_bytes()
        receipt["result"] = "PASS"
        receipt["credits"]["cpu_file_output_component"] = 1
        receipt["failure_class"] = None
        receipt["zero_credit_boundary_preserved"] = True
        rc = 0
    except Exception as exc:
        receipt["result"] = "FAIL"
        receipt["peak_rss_bytes"] = max_rss_bytes()
        receipt["failure_class"] = "PRODUCT_NEGATIVE_OR_EXECUTION_VALIDITY_REQUIRES_REVIEW"
        receipt["error"] = f"{type(exc).__name__}:{exc}"
        receipt["traceback"] = traceback.format_exc()
        receipt["network_guard"]["attempts"] = network_attempts
        rc = 1

    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"engine": args.engine, "result": receipt["result"], "output": str(output)}, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main())
