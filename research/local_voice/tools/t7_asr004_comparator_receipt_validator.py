#!/usr/bin/env python3
"""Fail-closed validator for the routed T7-ASR-004 matched German comparator receipt.

This validates receipt completeness/comparability only. It never invokes a model,
network, provider, VPS bridge, or effect path and grants no runtime/acceptance credit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = "T7_ASR004_COMPARATOR_RECEIPT/v1"
SEMANTIC_KEY = "95bd53a469133dbfdf39da320f6daa049cec1361084e632dc915c4bc156e3715"
FLEURS_REVISION = "bc0636bc121b131df69ed727a4ddafc5afc8afe4"
ROWS = tuple(range(32))
VARIANTS = (
    "QWEN3_ASR_DIRECT_RAW_DECODER",
    "QWEN3_ASR_WITH_DETERMINISTIC_SPEECH_PRESENCE_VAD_TURN_ADMISSION",
    "MATCHED_FASTER_WHISPER_RAW_DECODER",
    "MATCHED_FASTER_WHISPER_WITH_DETERMINISTIC_SPEECH_PRESENCE_VAD_TURN_ADMISSION",
)
GATED = {
    "QWEN3_ASR_WITH_DETERMINISTIC_SPEECH_PRESENCE_VAD_TURN_ADMISSION",
    "MATCHED_FASTER_WHISPER_WITH_DETERMINISTIC_SPEECH_PRESENCE_VAD_TURN_ADMISSION",
}
REQUIRED_SILENCE = {"digital_silence_1s", "digital_silence_2s", "digital_silence_5s"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ValidationError(ValueError):
    pass


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


def _sha(value: Any, label: str) -> str:
    s = str(value or "").lower()
    _need(bool(SHA256_RE.fullmatch(s)), f"{label} must be lowercase SHA-256 hex")
    return s


def normalize(text: Any) -> str:
    """Pinned primary normalizer: NFKC/casefold; punctuation+symbols -> spaces."""
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        out.append(" " if cat[0] in {"P", "S"} else ch)
    return " ".join("".join(out).split())


def tokens(text: Any) -> list[str]:
    return normalize(text).split()


def chars(text: Any) -> list[str]:
    return list(normalize(text).replace(" ", ""))


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    we = rw = ce = rc = false_rejects = count = 0
    for r in rows:
        count += 1
        refw, hypw = tokens(r["reference"]), tokens(r["hypothesis"])
        refc, hypc = chars(r["reference"]), chars(r["hypothesis"])
        rw += len(refw)
        we += edit_distance(refw, hypw)
        rc += len(refc)
        ce += edit_distance(refc, hypc)
        if r["variant"] in GATED and r["gate_decision"] == "NON_SPEECH":
            false_rejects += 1
    return {
        "utterance_count": count,
        "micro_wer": (we / rw) if rw else None,
        "micro_cer": (ce / rc) if rc else None,
        "word_edits": we,
        "reference_words": rw,
        "char_edits": ce,
        "reference_chars": rc,
        "gate_false_rejects": false_rejects,
    }


def validate_receipt(doc: dict[str, Any]) -> dict[str, Any]:
    _need(doc.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    _need(doc.get("semantic_key") == SEMANTIC_KEY, "semantic_key mismatch")

    fixture = doc.get("fixture") or {}
    _need(fixture.get("dataset") == "google/fleurs", "fixture.dataset must be google/fleurs")
    _need(fixture.get("config") == "de_de", "fixture.config must be de_de")
    _need(fixture.get("revision") == FLEURS_REVISION, "fixture.revision mismatch")
    _need(fixture.get("split") == "test", "fixture.split must be test")
    _need(fixture.get("rows") == list(ROWS), "fixture.rows must be exact ordered rows 0..31")

    evaluator = doc.get("evaluator") or {}
    _need(
        evaluator.get("normalizer") == "NFKC_CASEFOLD_PUNCT_SYMBOL_TO_SPACE_COLLAPSE_WS",
        "evaluator normalizer mismatch",
    )
    _sha(evaluator.get("source_sha256"), "evaluator.source_sha256")

    gate = doc.get("external_gate") or {}
    gate_sha = _sha(gate.get("contract_sha256"), "external_gate.contract_sha256")
    _need(gate.get("deterministic") is True, "external_gate must be deterministic")

    baseline = doc.get("faster_whisper_baseline") or {}
    _need(
        baseline.get("package") == "faster-whisper==1.2.1",
        "baseline package must be faster-whisper==1.2.1 unless a separately admitted baseline contract supersedes this validator",
    )
    _need(
        baseline.get("model_repo") == "Systran/faster-whisper-large-v3",
        "baseline model_repo mismatch",
    )
    _need(bool(str(baseline.get("model_revision") or "")), "baseline model_revision is required")
    digests = baseline.get("artifact_sha256") or []
    _need(isinstance(digests, list) and digests, "baseline artifact_sha256 must be a non-empty list")
    for i, digest in enumerate(digests):
        _sha(digest, f"baseline.artifact_sha256[{i}]")
    _need(baseline.get("device") == "cpu", "baseline device must be cpu")
    _need(baseline.get("compute_type") == "int8", "baseline compute_type must be int8")
    _need(baseline.get("beam_size") == 5, "baseline beam_size must be 5")
    _need(baseline.get("language") == "de", "baseline language must be de")
    _need(
        baseline.get("condition_on_previous_text") is False,
        "baseline condition_on_previous_text must be false",
    )
    _need(baseline.get("raw_vad_filter") is False, "faster-whisper internal VAD must be disabled for raw arm")
    _need(
        isinstance(baseline.get("effective_cpu_threads"), int) and baseline["effective_cpu_threads"] > 0,
        "baseline effective_cpu_threads must be a positive integer",
    )
    for field in ("ctranslate2_version", "runtime_version", "package_source_sha256"):
        _need(bool(str(baseline.get(field) or "")), f"baseline {field} is required")
    _sha(baseline.get("package_source_sha256"), "baseline.package_source_sha256")

    speech = doc.get("speech_records")
    _need(isinstance(speech, list), "speech_records must be a list")
    expected = {(row, variant) for row in ROWS for variant in VARIANTS}
    seen: set[tuple[int, str]] = set()
    audio_by_row: dict[int, set[str]] = defaultdict(set)
    ref_by_row: dict[int, set[str]] = defaultdict(set)
    raw_tx_by_row: dict[int, set[str]] = defaultdict(set)
    tx_by_row: dict[int, set[str]] = defaultdict(set)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for i, r in enumerate(speech):
        _need(isinstance(r, dict), f"speech_records[{i}] must be object")
        row = r.get("fixture_row")
        variant = r.get("variant")
        _need(row in ROWS, f"speech_records[{i}].fixture_row outside 0..31")
        _need(variant in VARIANTS, f"speech_records[{i}].variant unknown")
        key = (int(row), str(variant))
        _need(key not in seen, f"duplicate speech record {key}")
        seen.add(key)
        audio = _sha(r.get("audio_sha256"), f"speech_records[{i}].audio_sha256")
        audio_by_row[int(row)].add(audio)
        for field in (
            "reference",
            "dataset_raw_transcription",
            "dataset_transcription",
            "hypothesis",
            "model_identity",
            "runtime_identity",
        ):
            _need(field in r, f"speech_records[{i}] missing {field}")
        ref_by_row[int(row)].add(str(r["reference"]))
        raw_tx_by_row[int(row)].add(str(r["dataset_raw_transcription"]))
        tx_by_row[int(row)].add(str(r["dataset_transcription"]))
        _need(
            isinstance(r.get("decoder_latency_ms"), (int, float)) and r["decoder_latency_ms"] >= 0,
            f"speech_records[{i}] invalid decoder_latency_ms",
        )
        _need(
            isinstance(r.get("end_to_end_latency_ms"), (int, float)) and r["end_to_end_latency_ms"] >= 0,
            f"speech_records[{i}] invalid end_to_end_latency_ms",
        )
        if variant in GATED:
            _need(
                r.get("external_gate_contract_sha256") == gate_sha,
                f"speech_records[{i}] gated arm must bind shared external gate",
            )
            _need(r.get("gate_decision") in {"SPEECH", "NON_SPEECH"}, f"speech_records[{i}] invalid gate_decision")
            if r.get("gate_decision") == "NON_SPEECH":
                _need(
                    r.get("hypothesis") == "",
                    f"speech_records[{i}] rejected speech row must retain empty hypothesis, not disappear",
                )
        else:
            _need(r.get("gate_decision") in {None, "NOT_APPLICABLE"}, f"speech_records[{i}] raw arm must not hide a gate")
        grouped[str(variant)].append(r)

    _need(
        seen == expected,
        f"speech matrix incomplete: missing={len(expected - seen)} extra={len(seen - expected)}",
    )
    for row in ROWS:
        _need(len(audio_by_row[row]) == 1, f"fixture row {row} audio differs across arms")
        _need(len(ref_by_row[row]) == 1, f"fixture row {row} reference differs across arms")
        _need(len(raw_tx_by_row[row]) == 1, f"fixture row {row} raw_transcription differs across arms")
        _need(len(tx_by_row[row]) == 1, f"fixture row {row} transcription differs across arms")

    non_speech = doc.get("non_speech_records")
    _need(isinstance(non_speech, list), "non_speech_records must be a list")
    ns_seen: set[tuple[str, str]] = set()
    ns_hashes: dict[str, set[str]] = defaultdict(set)
    false_activation: dict[str, int] = defaultdict(int)
    for i, r in enumerate(non_speech):
        _need(isinstance(r, dict), f"non_speech_records[{i}] must be object")
        fixture_id = str(r.get("fixture_id") or "")
        variant = r.get("variant")
        _need(fixture_id, f"non_speech_records[{i}] missing fixture_id")
        _need(variant in VARIANTS, f"non_speech_records[{i}] unknown variant")
        key = (fixture_id, str(variant))
        _need(key not in ns_seen, f"duplicate non-speech record {key}")
        ns_seen.add(key)
        ns_hashes[fixture_id].add(_sha(r.get("audio_sha256"), f"non_speech_records[{i}].audio_sha256"))
        _need("hypothesis" in r, f"non_speech_records[{i}] missing hypothesis")
        if variant in GATED:
            _need(
                r.get("external_gate_contract_sha256") == gate_sha,
                f"non_speech_records[{i}] gated arm must bind shared external gate",
            )
            _need(r.get("gate_decision") in {"SPEECH", "NON_SPEECH"}, f"non_speech_records[{i}] invalid gate_decision")
            if r.get("gate_decision") == "NON_SPEECH":
                _need(
                    r.get("hypothesis") == "",
                    f"non_speech_records[{i}] rejected non-speech must have empty gated hypothesis",
                )
        else:
            _need(r.get("gate_decision") in {None, "NOT_APPLICABLE"}, f"non_speech_records[{i}] raw arm must not hide a gate")
        if normalize(r.get("hypothesis", "")):
            false_activation[str(variant)] += 1

    fixture_ids = {x[0] for x in ns_seen}
    _need(
        REQUIRED_SILENCE <= fixture_ids,
        f"missing required silence fixtures: {sorted(REQUIRED_SILENCE - fixture_ids)}",
    )
    for fixture_id in REQUIRED_SILENCE:
        _need(
            {(fixture_id, variant) for variant in VARIANTS} <= ns_seen,
            f"non-speech matrix incomplete for {fixture_id}",
        )
    for fixture_id, hashes in ns_hashes.items():
        if all((fixture_id, variant) in ns_seen for variant in VARIANTS):
            _need(len(hashes) == 1, f"non-speech fixture {fixture_id} audio differs across arms")

    return {
        "schema": "T7_ASR004_COMPARATOR_VALIDATION/v1",
        "semantic_key": SEMANTIC_KEY,
        "valid": True,
        "evidence_scope": "DETERMINISTIC_RECEIPT_COMPLETENESS_AND_COMPARABILITY_ONLY",
        "speech": {variant: _aggregate(grouped[variant]) for variant in VARIANTS},
        "non_speech_false_text_activation_count": {
            variant: false_activation.get(variant, 0) for variant in VARIANTS
        },
        "matched_fleurs_rows": 32,
        "shared_audio_identity_verified": True,
        "shared_external_gate_identity_verified": True,
        "runtime_credit": 0,
        "german_asr_quality_credit": 0,
        "streaming_credit": 0,
        "trigger4_acceptance_credit": 0,
        "whole_system_credit": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        doc = json.loads(args.receipt.read_text(encoding="utf-8"))
        report = validate_receipt(doc)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
