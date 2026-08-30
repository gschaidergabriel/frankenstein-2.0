#!/usr/bin/env python3
"""Trigger-4 executor for the already-claimed T7-ASR-008 Nemotron target benchmark.

This tool is evidence-producing, not credit-authoritative. It deliberately:
- verifies the exact pinned Nemotron 3.5 ASR Q8 artifact before inference;
- reuses the exact T7-ASR-004 FLEURS de_de rows 0..31 and deterministic gate;
- runs de-DE and auto separately;
- exercises RNNT right-context settings 0/1/3/6/13, mapped by the pinned
  source contract to 80/160/320/560/1120 ms;
- records WER/CER, raw/gated non-speech activation, batch wall time, RTF,
  and peak process RSS where GNU time is available;
- marks partial/final-per-utterance latency as NOT_OBSERVED on the file-stream
  CLI surface instead of fabricating those values.

No Trigger-4 acceptance, German E2E, physical-device, GWT/J-Space, effect,
training, or whole-product credit is minted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
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
    load_gate_contract,
    prepare_fixtures,
)
from t7_asr_score import aggregate, normalize_text

SCHEMA = "T7_ASR008_NEMOTRON_TARGET_COMPARATOR_RECEIPT/v1"
SEMANTIC_KEY = "93d61d9b893d411c8085cd5d257968c23448bc426430e603f6e33add1db5e4e3"
MODEL_ID = "nvidia/nemotron-3.5-asr-streaming-0.6b"
MODEL_REVISION = "1c8deaecc64b91f034d73e08dd8b64625eb3395d"
MODEL_SHA256 = "a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae"
MODEL_REMOTE_SIZE_BYTES = 741_548_352
RIGHT_CONTEXTS = ((0, 80), (1, 160), (3, 320), (6, 560), (13, 1120))
LANGUAGE_MODES = ("de-DE", "auto")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command_text(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    except Exception as exc:
        return f"UNAVAILABLE:{type(exc).__name__}:{exc}"


def proc_mem_total_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except Exception:
        pass
    return None


def extract_candidate_text(doc: Any) -> str:
    """Extract transcript text without assuming one exact JSON envelope."""
    preferred = ("transcript", "text", "transcription")
    if isinstance(doc, dict):
        for key in preferred:
            value = doc.get(key)
            if isinstance(value, str):
                return value.strip()
        for key in ("result", "results", "alternative", "alternatives", "data"):
            if key in doc:
                text = extract_candidate_text(doc[key])
                if text:
                    return text
        for value in doc.values():
            text = extract_candidate_text(value)
            if text:
                return text
    elif isinstance(doc, list):
        parts = [extract_candidate_text(x) for x in doc]
        parts = [x for x in parts if x]
        if parts:
            return " ".join(parts).strip()
    return ""


def strings_in(doc: Any):
    if isinstance(doc, str):
        yield doc
    elif isinstance(doc, dict):
        for value in doc.values():
            yield from strings_in(value)
    elif isinstance(doc, list):
        for value in doc:
            yield from strings_in(value)


def map_outputs(output_dir: Path, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    docs: list[tuple[Path, Any]] = []
    for path in sorted(output_dir.rglob("*.json")):
        try:
            docs.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue

    for path, doc in docs:
        haystacks = [path.name, path.stem, *list(strings_in(doc))]
        matches = []
        for utterance_id in expected_ids:
            if any(utterance_id in str(item) for item in haystacks):
                matches.append(utterance_id)
        if len(matches) == 1:
            uid = matches[0]
            if uid in mapped:
                raise RuntimeError(f"duplicate JSON output mapping for {uid}")
            mapped[uid] = {"path": str(path), "document": doc, "text": extract_candidate_text(doc)}

    # Current NeMo-Speech.cpp writes one result per input. If filenames do not
    # preserve identity, refuse to guess from ordering.
    missing = sorted(expected_ids - set(mapped))
    if missing:
        raise RuntimeError(
            f"could not identity-bind {len(missing)} outputs; first missing={missing[:5]!r}"
        )
    return mapped


def parse_gnu_time(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"available": False, "max_rss_bytes": None, "user_seconds": None, "system_seconds": None}
    if not path.exists():
        return result
    result["available"] = True
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if "Maximum resident set size (kbytes):" in line:
            result["max_rss_bytes"] = int(line.rsplit(":", 1)[1].strip()) * 1024
        elif line.startswith("User time (seconds):"):
            result["user_seconds"] = float(line.rsplit(":", 1)[1].strip())
        elif line.startswith("System time (seconds):"):
            result["system_seconds"] = float(line.rsplit(":", 1)[1].strip())
    return result


def run_condition(
    *,
    nemo_binary: Path,
    model: Path,
    input_dir: Path,
    output_dir: Path,
    language: str,
    right_context: int,
    right_context_ms: int,
    device: str,
    expected_ids: set[str],
    total_audio_seconds: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stderr_path = output_dir / "_stderr.log"
    stdout_path = output_dir / "_stdout.log"
    time_path = output_dir / "_time.txt"

    cmd = [
        str(nemo_binary),
        "transcribe",
        str(input_dir),
        "--model",
        str(model),
        "--language",
        language,
        "--device",
        device,
        "--stream",
        "--format",
        "json",
        "--output-dir",
        str(output_dir),
        "--asr.streaming.rnnt_right_context",
        str(right_context),
    ]
    timed_cmd = cmd
    if Path("/usr/bin/time").is_file():
        timed_cmd = ["/usr/bin/time", "-v", "-o", str(time_path), *cmd]

    t0 = time.perf_counter()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        cp = subprocess.run(timed_cmd, stdout=stdout, stderr=stderr, check=False)
    wall_seconds = time.perf_counter() - t0

    result: dict[str, Any] = {
        "language_mode": language,
        "rnnt_right_context": right_context,
        "right_context_ms_source_mapping": right_context_ms,
        "cli_file_feed_chunk_ms": 160,
        "command": cmd,
        "returncode": cp.returncode,
        "wall_seconds": wall_seconds,
        "total_audio_seconds": total_audio_seconds,
        "real_time_factor_batch_wall": wall_seconds / total_audio_seconds if total_audio_seconds else None,
        "gnu_time": parse_gnu_time(time_path),
        "partial_hypothesis_stability": {
            "status": "NOT_OBSERVED_ON_FILE_STREAM_CLI_SURFACE",
            "credit": 0,
        },
        "first_partial_latency_ms": {
            "status": "NOT_OBSERVED_ON_FILE_STREAM_CLI_SURFACE",
            "credit": 0,
        },
        "per_utterance_final_latency_ms": {
            "status": "NOT_OBSERVED_ON_FILE_STREAM_CLI_SURFACE",
            "credit": 0,
        },
    }
    if cp.returncode != 0:
        result["classification"] = "PRODUCT_OR_RUNTIME_NEGATIVE_REQUIRES_LOG_REVIEW"
        result["stderr_tail"] = stderr_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        return result

    try:
        mapped = map_outputs(output_dir, expected_ids)
    except Exception as exc:
        result["classification"] = "EVIDENCE_INVALID_OUTPUT_IDENTITY_BINDING"
        result["mapping_error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["classification"] = "EXECUTED"
    result["outputs"] = {
        uid: {"path": row["path"], "text": row["text"]}
        for uid, row in sorted(mapped.items())
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--nemo-speech", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--work-root", type=Path)
    p.add_argument("--device", default="cpu")
    args = p.parse_args(argv)

    started = utc_now()
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "semantic_key": SEMANTIC_KEY,
        "research_id": "T7-ASR-008",
        "trigger": "4",
        "started_at_utc": started,
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "expected_q8_sha256": MODEL_SHA256,
            "expected_remote_size_bytes": MODEL_REMOTE_SIZE_BYTES,
        },
        "scope": {
            "target_runtime_model_benchmark": True,
            "trigger4_acceptance_credit": 0,
            "german_e2e_voice_credit": 0,
            "physical_device_credit": 0,
            "gwt_jspace_credit": 0,
            "effect_credit": 0,
            "training_credit": 0,
            "whole_system_credit": 0,
        },
        "pass": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if not args.model.is_file():
            raise RuntimeError(f"model artifact missing: {args.model}")
        observed_sha = sha256_file(args.model)
        observed_size = args.model.stat().st_size
        receipt["model"]["observed_q8_sha256"] = observed_sha
        receipt["model"]["observed_size_bytes"] = observed_size
        receipt["model"]["hash_verified"] = observed_sha == MODEL_SHA256
        receipt["model"]["size_matches_source_pin"] = observed_size == MODEL_REMOTE_SIZE_BYTES
        if observed_sha != MODEL_SHA256:
            raise RuntimeError(f"Q8 SHA256 mismatch: {observed_sha}")

        nemo_binary = args.nemo_speech.resolve()
        if not nemo_binary.is_file():
            raise RuntimeError(f"nemo-speech binary missing: {nemo_binary}")
        receipt["runtime"] = {
            "nemo_speech_binary": str(nemo_binary),
            "nemo_speech_binary_sha256": sha256_file(nemo_binary),
            "nemo_speech_version": command_text([str(nemo_binary), "--version"]),
            "nemo_speech_cpp_commit": os.environ.get("NEMO_SPEECH_CPP_COMMIT"),
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "mem_total_bytes": proc_mem_total_bytes(),
            "device": args.device,
        }

        owned_tmp = None
        if args.work_root:
            root = args.work_root
            root.mkdir(parents=True, exist_ok=True)
        else:
            owned_tmp = tempfile.TemporaryDirectory(prefix="t7-asr008-")
            root = Path(owned_tmp.name)

        fixture_root = root / "fixtures"
        speech, non_speech, dataset_meta = prepare_fixtures(fixture_root)
        gate_contract, gate_contract_sha = load_gate_contract()
        receipt["corpus"] = {
            "repo": FLEURS_REPO,
            "config": FLEURS_CONFIG,
            "revision": FLEURS_REVISION,
            "rows": list(ROWS),
            "dataset_meta": dataset_meta,
            "speech": [
                {
                    "utterance_id": f"fleurs_de_de_test_{row['row']:02d}",
                    "row": row["row"],
                    "audio_sha256": row["audio_sha256"],
                    "reference": row["reference"],
                }
                for row in speech
            ],
            "non_speech": [
                {
                    "utterance_id": row["fixture_id"],
                    "audio_sha256": row["audio_sha256"],
                    "duration_seconds": row["duration_seconds"],
                }
                for row in non_speech
            ],
        }

        # Materialize one flat immutable identity set reused by every condition.
        input_dir = root / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        references: dict[str, str] = {}
        source_by_id: dict[str, Path] = {}
        for row in speech:
            uid = f"fleurs_de_de_test_{row['row']:02d}"
            dst = input_dir / f"{uid}{row['path'].suffix}"
            shutil.copy2(row["path"], dst)
            references[uid] = row["reference"]
            source_by_id[uid] = dst
        for row in non_speech:
            uid = row["fixture_id"]
            dst = input_dir / f"{uid}{row['path'].suffix}"
            shutil.copy2(row["path"], dst)
            references[uid] = ""
            source_by_id[uid] = dst

        gate = {}
        for uid, path in sorted(source_by_id.items()):
            gate[uid] = gate_audio(path, gate_contract)
        receipt["gate"] = {
            "contract_sha256": gate_contract_sha,
            "decisions": gate,
            "speech_false_rejects": sum(
                gate[f"fleurs_de_de_test_{row['row']:02d}"]["decision"] != "SPEECH"
                for row in speech
            ),
            "non_speech_false_accepts": sum(
                gate[row["fixture_id"]]["decision"] == "SPEECH" for row in non_speech
            ),
        }

        import soundfile as sf

        total_audio_seconds = sum(float(sf.info(str(path)).duration) for path in source_by_id.values())
        expected_ids = set(source_by_id)
        conditions = []
        for language in LANGUAGE_MODES:
            for right_context, right_context_ms in RIGHT_CONTEXTS:
                out_dir = root / "outputs" / language.replace("-", "_") / f"rc{right_context}"
                cond = run_condition(
                    nemo_binary=nemo_binary,
                    model=args.model.resolve(),
                    input_dir=input_dir,
                    output_dir=out_dir,
                    language=language,
                    right_context=right_context,
                    right_context_ms=right_context_ms,
                    device=args.device,
                    expected_ids=expected_ids,
                    total_audio_seconds=total_audio_seconds,
                )
                if cond.get("classification") == "EXECUTED":
                    records = []
                    raw_non_speech_false = 0
                    gated_non_speech_false = 0
                    for uid in sorted(expected_ids):
                        hyp = cond["outputs"][uid]["text"]
                        if uid.startswith("fleurs_de_de_test_"):
                            records.append(
                                {
                                    "utterance_id": uid,
                                    "reference": references[uid],
                                    "hypothesis": hyp,
                                }
                            )
                        else:
                            active = bool(normalize_text(hyp))
                            raw_non_speech_false += int(active)
                            gated_non_speech_false += int(active and gate[uid]["decision"] == "SPEECH")
                    cond["german_score"] = aggregate(records)
                    cond["non_speech"] = {
                        "fixture_count": len(non_speech),
                        "raw_false_text_activations": raw_non_speech_false,
                        "gated_false_text_activations": gated_non_speech_false,
                    }
                conditions.append(cond)

        receipt["conditions"] = conditions
        receipt["condition_count"] = len(conditions)
        receipt["expected_condition_count"] = len(LANGUAGE_MODES) * len(RIGHT_CONTEXTS)
        receipt["all_conditions_executed"] = (
            len(conditions) == receipt["expected_condition_count"]
            and all(c.get("classification") == "EXECUTED" for c in conditions)
        )
        receipt["pass"] = bool(
            receipt["model"]["hash_verified"]
            and receipt["all_conditions_executed"]
            and receipt["gate"]["speech_false_rejects"] == 0
        )
        receipt["classification"] = (
            "EXECUTED_TARGET_COMPARATOR_NO_AUTOMATIC_ACCEPTANCE"
            if receipt["pass"]
            else "TARGET_COMPARATOR_NEGATIVE_OR_INCOMPLETE"
        )
        receipt["finished_at_utc"] = utc_now()
        receipt["runtime_execution_observed"] = bool(receipt["all_conditions_executed"])
        receipt["nemotron_target_runtime_benchmark_credit_candidate"] = int(receipt["pass"])
        receipt["trigger4_acceptance_credit"] = 0
        receipt["whole_system_credit"] = 0
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if owned_tmp is not None:
            owned_tmp.cleanup()
        return 0 if receipt["pass"] else 3
    except Exception as exc:
        receipt["classification"] = "EXECUTOR_ERROR_OR_INVALID_EVIDENCE"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["finished_at_utc"] = utc_now()
        receipt["runtime_execution_observed"] = False
        receipt["nemotron_target_runtime_benchmark_credit_candidate"] = 0
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
