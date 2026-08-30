#!/usr/bin/env python3
"""Fail-closed validator for T7-ASR-008 Nemotron 3.5 target comparator receipts.

Validation is independent of model execution.  It proves only that a receipt is
structurally complete, pinned to the admitted subject and internally consistent.
It never mints German-quality, production-streaming, physical-device, GWT,
effect, training, whole-voice or whole-product credit.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

SCHEMA = "T7_ASR008_NEMOTRON35_TARGET_COMPARATOR_RECEIPT/v1"
VALIDATION_SCHEMA = "T7_ASR008_NEMOTRON35_TARGET_COMPARATOR_VALIDATION/v1"
SEMANTIC_KEY = "93d61d9b893d411c8085cd5d257968c23448bc426430e603f6e33add1db5e4e3"
MODEL_ID = "nvidia/nemotron-3.5-asr-streaming-0.6b"
MODEL_REVISION = "1c8deaecc64b91f034d73e08dd8b64625eb3395d"
MODEL_SHA256 = "a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae"
RUNTIME_REPO = "NVIDIA/NeMo-Speech.cpp"
RUNTIME_COMMIT = "4f9676226f667d14608487df744f375db87127f8"
FLEURS_REPO = "google/fleurs"
FLEURS_CONFIG = "de_de"
FLEURS_REVISION = "bc0636bc121b131df69ed727a4ddafc5afc8afe4"
ROWS = tuple(range(32))
GEOMETRIES = ((80, 0), (160, 1), (320, 3), (560, 6), (1120, 13))
LANGUAGES = ("de-DE", "auto")
NORMALIZER = "NFKC_CASEFOLD_PUNCT_SYMBOL_TO_SPACE_COLLAPSE_WS"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ValidationError(ValueError):
    pass


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


def sha(value: Any, label: str) -> str:
    out = str(value or "").lower()
    need(bool(SHA256_RE.fullmatch(out)), f"{label} must be lowercase SHA-256 hex")
    return out


def finite_nonnegative(value: Any, label: str) -> float:
    need(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} must be numeric")
    out = float(value)
    need(math.isfinite(out) and out >= 0, f"{label} must be finite and nonnegative")
    return out


def validate(doc: dict[str, Any]) -> dict[str, Any]:
    need(doc.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    need(doc.get("semantic_key") == SEMANTIC_KEY, "semantic_key mismatch")
    need(doc.get("research_id") == "T7-ASR-008", "research_id mismatch")
    need(doc.get("execution_observed") is True, "execution_observed must be true")
    need(doc.get("pass") is True, "executor pass must be true")
    need(doc.get("classification") == "EXECUTED_NO_HARNESS_COUNTEREXAMPLE", "classification mismatch")
    need(doc.get("target_surface") == "clay-direct-dev", "target_surface mismatch")
    source_commit = str(doc.get("source_repo_commit") or "")
    need(bool(COMMIT_RE.fullmatch(source_commit)), "source_repo_commit must be exact 40-hex commit")

    model = doc.get("model") or {}
    need(model.get("id") == MODEL_ID, "model.id mismatch")
    need(model.get("revision") == MODEL_REVISION, "model.revision mismatch")
    need(model.get("q8_sha256") == MODEL_SHA256, "model.q8_sha256 mismatch")
    need(isinstance(model.get("bytes"), int) and model["bytes"] > 0, "model.bytes must be positive integer")

    runtime = doc.get("runtime") or {}
    need(runtime.get("repo") == RUNTIME_REPO, "runtime.repo mismatch")
    need(runtime.get("commit") == RUNTIME_COMMIT, "runtime.commit mismatch")
    sha(runtime.get("binary_sha256"), "runtime.binary_sha256")
    need(runtime.get("device") == "cpu", "runtime.device must be cpu")
    need(bool(str(runtime.get("transcribe_help_sha256") or "")), "runtime.transcribe_help_sha256 missing")
    sha(runtime.get("transcribe_help_sha256"), "runtime.transcribe_help_sha256")

    fixture = doc.get("fixture") or {}
    need(fixture.get("dataset") == FLEURS_REPO, "fixture.dataset mismatch")
    need(fixture.get("config") == FLEURS_CONFIG, "fixture.config mismatch")
    need(fixture.get("revision") == FLEURS_REVISION, "fixture.revision mismatch")
    need(fixture.get("split") == "test", "fixture.split mismatch")
    need(fixture.get("rows") == list(ROWS), "fixture.rows must be exact ordered 0..31")
    selected = fixture.get("selected_rows")
    need(isinstance(selected, list) and len(selected) == len(ROWS), "fixture.selected_rows must contain 32 rows")
    seen_rows: set[int] = set()
    audio_by_row: dict[int, tuple[str, str]] = {}
    for i, row in enumerate(selected):
        need(isinstance(row, dict), f"selected_rows[{i}] must be object")
        n = row.get("row")
        need(n in ROWS and n not in seen_rows, f"selected_rows[{i}].row invalid/duplicate")
        seen_rows.add(int(n))
        audio_by_row[int(n)] = (
            sha(row.get("audio_sha256"), f"selected_rows[{i}].audio_sha256"),
            sha(row.get("benchmark_wav_sha256"), f"selected_rows[{i}].benchmark_wav_sha256"),
        )
    need(seen_rows == set(ROWS), "selected_rows coverage mismatch")

    gate = doc.get("external_gate") or {}
    gate_sha = sha(gate.get("contract_sha256"), "external_gate.contract_sha256")
    need(gate.get("deterministic") is True, "external gate must be deterministic")
    need(isinstance(gate.get("contract"), dict), "external_gate.contract must be object")
    need(doc.get("normalizer") == NORMALIZER, "normalizer mismatch")
    need(doc.get("streaming_geometry") == [
        {"chunk_ms": ms, "rnnt_right_context": rc} for ms, rc in GEOMETRIES
    ], "streaming_geometry mismatch")
    need(doc.get("languages") == list(LANGUAGES), "languages mismatch")

    configs = doc.get("configs")
    need(isinstance(configs, list), "configs must be list")
    expected = {(lang, ms, rc) for lang in LANGUAGES for ms, rc in GEOMETRIES}
    seen: set[tuple[str, int, int]] = set()
    summaries: list[dict[str, Any]] = []
    for i, cfg in enumerate(configs):
        need(isinstance(cfg, dict), f"configs[{i}] must be object")
        metrics = cfg.get("metrics") or {}
        key = (metrics.get("language"), metrics.get("chunk_ms"), metrics.get("rnnt_right_context"))
        need(key in expected and key not in seen, f"configs[{i}] geometry/language invalid or duplicate: {key}")
        seen.add(key)  # type: ignore[arg-type]
        need(metrics.get("stream_mode") is True, f"configs[{i}] must be streaming")
        need(metrics.get("batching") is False, f"configs[{i}] batching must be false")
        need(metrics.get("utterance_count") == 32, f"configs[{i}] utterance_count must be 32")
        finite_nonnegative(metrics.get("micro_wer"), f"configs[{i}].micro_wer")
        finite_nonnegative(metrics.get("micro_cer"), f"configs[{i}].micro_cer")
        finite_nonnegative(metrics.get("batch_wall_ms"), f"configs[{i}].batch_wall_ms")
        need(metrics.get("partial_stability") == "NOT_EXPOSED_BY_CURRENT_DIRECTORY_CLI_SURFACE", f"configs[{i}] partial-stability scope mismatch")
        need(metrics.get("first_stable_token_latency") == "NOT_EXPOSED_BY_CURRENT_DIRECTORY_CLI_SURFACE", f"configs[{i}] first-token scope mismatch")
        need(metrics.get("final_latency_scope") == "BATCH_WALL_ONLY_NOT_PER_UTTERANCE", f"configs[{i}] final-latency scope mismatch")

        speech = cfg.get("speech_records")
        need(isinstance(speech, list) and len(speech) == 32, f"configs[{i}] must preserve 32 speech records")
        cfg_rows: set[int] = set()
        for j, row in enumerate(speech):
            n = row.get("fixture_row") if isinstance(row, dict) else None
            need(n in ROWS and n not in cfg_rows, f"configs[{i}].speech_records[{j}] row invalid/duplicate")
            cfg_rows.add(int(n))
            need((row.get("audio_sha256"), row.get("benchmark_wav_sha256")) == audio_by_row[int(n)], f"configs[{i}].speech_records[{j}] fixture hash mismatch")
            need(row.get("external_gate_contract_sha256") == gate_sha, f"configs[{i}].speech_records[{j}] gate hash mismatch")
            need(row.get("gate_decision") in {"SPEECH", "NON_SPEECH"}, f"configs[{i}].speech_records[{j}] invalid gate decision")
            need(isinstance(row.get("reference"), str) and isinstance(row.get("hypothesis"), str), f"configs[{i}].speech_records[{j}] text fields missing")
        need(cfg_rows == set(ROWS), f"configs[{i}] row coverage mismatch")

        non_speech = cfg.get("non_speech_records")
        need(isinstance(non_speech, list) and non_speech, f"configs[{i}] non_speech_records missing")
        for j, row in enumerate(non_speech):
            need(isinstance(row, dict), f"configs[{i}].non_speech_records[{j}] must be object")
            sha(row.get("audio_sha256"), f"configs[{i}].non_speech_records[{j}].audio_sha256")
            sha(row.get("benchmark_wav_sha256"), f"configs[{i}].non_speech_records[{j}].benchmark_wav_sha256")
            need(row.get("external_gate_contract_sha256") == gate_sha, f"configs[{i}].non_speech_records[{j}] gate hash mismatch")
            need(row.get("gate_decision") in {"SPEECH", "NON_SPEECH"}, f"configs[{i}].non_speech_records[{j}] invalid gate decision")
            need(isinstance(row.get("raw_hypothesis"), str) and isinstance(row.get("gated_hypothesis"), str), f"configs[{i}].non_speech_records[{j}] text fields missing")
            if row.get("gate_decision") == "NON_SPEECH":
                need(row.get("gated_hypothesis") == "", f"configs[{i}].non_speech_records[{j}] rejected audio must have empty gated hypothesis")

        summaries.append({
            "language": key[0], "chunk_ms": key[1], "rnnt_right_context": key[2],
            "micro_wer": metrics["micro_wer"], "micro_cer": metrics["micro_cer"],
            "batch_wall_ms": metrics["batch_wall_ms"],
            "speech_gate_false_rejects": metrics.get("speech_gate_false_rejects"),
            "non_speech_false_text_activations_raw": metrics.get("non_speech_false_text_activations_raw"),
            "non_speech_false_text_activations_gated": metrics.get("non_speech_false_text_activations_gated"),
        })
    need(seen == expected, f"config matrix incomplete: missing={sorted(expected-seen)}")

    det = doc.get("deterministic_rerun") or {}
    need(det.get("language") == "de-DE" and det.get("chunk_ms") == 320 and det.get("rnnt_right_context") == 3, "deterministic rerun geometry mismatch")
    need(det.get("reruns") == 2 and det.get("byte_equal_stdout") is True, "deterministic rerun did not prove byte equality")
    hashes = det.get("stdout_sha256")
    need(isinstance(hashes, list) and len(hashes) == 2, "deterministic rerun hashes missing")
    hashes = [sha(x, f"deterministic_rerun.stdout_sha256[{i}]") for i, x in enumerate(hashes)]
    need(hashes[0] == hashes[1], "deterministic rerun hashes differ")

    credits = doc.get("credits") or {}
    need(credits.get("nemotron_target_runtime_credit") == 1, "executor runtime-credit claim must be exactly 1 before validation")
    for field in (
        "german_asr_quality_credit", "production_streaming_credit", "trigger4_acceptance_credit",
        "physical_device_credit", "gwt_jspace_credit", "effect_credit", "training_credit",
        "whole_voice_e2e_credit", "whole_product_credit",
    ):
        need(credits.get(field) == 0, f"{field} must remain zero")

    return {
        "schema": VALIDATION_SCHEMA,
        "valid": True,
        "classification": "VALID_EXACT_SCOPE_TARGET_RUNTIME_RECEIPT",
        "semantic_key": SEMANTIC_KEY,
        "research_id": "T7-ASR-008",
        "source_repo_commit": source_commit,
        "validated_subject": {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "model_q8_sha256": MODEL_SHA256,
            "runtime_repo": RUNTIME_REPO,
            "runtime_commit": RUNTIME_COMMIT,
            "target_surface": "clay-direct-dev",
        },
        "validated_matrix": summaries,
        "promotion_eligibility": {
            "nemotron_target_component_runtime": 1,
            "german_asr_quality": 0,
            "production_streaming": 0,
            "physical_device": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
        "scope_note": "Validation establishes exact bounded comparator execution only; broader quality/latency/product conclusions require separate comparison and acceptance.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("receipt")
    ap.add_argument("--output")
    args = ap.parse_args()
    try:
        doc = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        result = validate(doc)
        rc = 0
    except Exception as exc:
        result = {
            "schema": VALIDATION_SCHEMA,
            "valid": False,
            "classification": "EVIDENCE_INVALID",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "promotion_eligibility": {"nemotron_target_component_runtime": 0},
        }
        rc = 2
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
