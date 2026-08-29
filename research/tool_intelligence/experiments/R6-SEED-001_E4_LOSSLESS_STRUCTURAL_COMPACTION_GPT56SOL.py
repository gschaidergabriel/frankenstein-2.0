#!/usr/bin/env python3
"""Trigger-6 E4 research ablation: lossless structural ContextView compaction.

Research-only experiment. This does not create target-runtime, integration, or
whole-system credit. It compares current F2-style canonical ContextView JSON to
a self-describing row-oriented structural representation that is lossless,
side-store-free, deterministic, and digest-bound.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import statistics
import time
from typing import Any

CODEC = "F2_CONTEXT_STRUCTURAL_COMPACTION/v1"
SEL_FIELDS = [
    "item_id","item_sha256","channel","payload_ref","payload_sha256",
    "source_ref","source_sha256","source_generation","source_classification",
    "priority_bp","cost_units","required","provenance_refs","evidence_refs",
    "cost_witness_sha256","cost_renderer_id","cost_renderer_version",
    "cost_tokenizer_id","cost_tokenizer_version","cost_witness_generation",
    "cost_measurement_ref","cost_witness_provenance_refs","selection_reason",
]
OMIT_FIELDS = [
    "item_id","item_sha256","channel","priority_bp","cost_units","required",
    "omission_reason",
]
VIEW_FIELDS = [
    "schema","context_id","task_id","task_generation","need_sha256",
    "selected_count","selected_cost_units","classification",
]
LEX_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-/:.]*|\d+|[^\s]")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def make_view(n_selected: int, n_omitted: int | None = None) -> dict[str, Any]:
    if n_omitted is None:
        n_omitted = max(1, n_selected // 4)
    channels = [
        "EVIDENCE","COUNTEREVIDENCE","HYPERPOSITION","METHOD","STATE","GOAL"
    ]
    selected = []
    for i in range(n_selected):
        selected.append({
            "item_id": f"item-{i:04d}",
            "item_sha256": sha256_text(f"item-{i}"),
            "channel": channels[i % len(channels)],
            "payload_ref": f"unifieddb://epistemic/{i:06d}",
            "payload_sha256": sha256_text(f"payload-{i}"),
            "source_ref": f"record-{i:06d}",
            "source_sha256": sha256_text(f"source-{i}"),
            "source_generation": 4 + (i % 3),
            "source_classification":
                ["OBSERVED","INFERRED","NEGATIVE_RESULT","UNKNOWN"][i % 4],
            "priority_bp": 10000 - (i % 4000),
            "cost_units": 120 + (i % 73),
            "required": i < max(1, n_selected // 16),
            "provenance_refs": [
                f"provenance-sha256:{sha256_text(f'prov-{i}')}",
                f"causal:{i // 2:06d}",
            ],
            "evidence_refs": [
                f"epistemic-record-sha256:{sha256_text(f'ev-{i}')}",
                f"observation:{i:06d}",
            ],
            "cost_witness_sha256": sha256_text(f"costw-{i}"),
            "cost_renderer_id": "f2-context-renderer",
            "cost_renderer_version": "4",
            "cost_tokenizer_id": "target-model-tokenizer",
            "cost_tokenizer_version": "pinned-v1",
            "cost_witness_generation": 1,
            "cost_measurement_ref": f"measurement:{i:06d}",
            "cost_witness_provenance_refs": [
                f"measure-provenance:{sha256_text(f'mp-{i}')[:24]}"
            ],
            "selection_reason":
                "REQUIRED_CHANNEL"
                if i < max(1, n_selected // 16)
                else "PRIORITY_WITHIN_BUDGET",
        })
    omitted = []
    for i in range(n_omitted):
        j = n_selected + i
        omitted.append({
            "item_id": f"item-{j:04d}",
            "item_sha256": sha256_text(f"item-{j}"),
            "channel": channels[j % len(channels)],
            "priority_bp": 3000 - (i % 1000),
            "cost_units": 180 + (i % 40),
            "required": False,
            "omission_reason": "BUDGET_EXHAUSTED",
        })
    return {
        "schema": "FRANKENSTEIN2_CONTEXT_VIEW/v1",
        "context_id": "ctx-e4-ablation",
        "task_id": "task-e4-lossless-structural",
        "task_generation": 4,
        "need_sha256": sha256_text(f"need-{n_selected}-{n_omitted}"),
        "selected": selected,
        "omitted": omitted,
        "selected_count": len(selected),
        "selected_cost_units": sum(row["cost_units"] for row in selected),
        "classification":
            "BOUNDED_CONTEXT_REFERENCE_VIEW_NOT_TRUTH_OR_EFFECT_AUTHORITY",
    }


def encode_compact(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "codec": CODEC,
        "source_context_view_sha256": sha256_text(canonical_json(view)),
        "view_fields": VIEW_FIELDS,
        "view": [view[key] for key in VIEW_FIELDS],
        "selected_fields": SEL_FIELDS,
        "selected": [[row[key] for key in SEL_FIELDS] for row in view["selected"]],
        "omitted_fields": OMIT_FIELDS,
        "omitted": [[row[key] for key in OMIT_FIELDS] for row in view["omitted"]],
    }


def decode_compact(encoded: dict[str, Any]) -> dict[str, Any]:
    if encoded.get("codec") != CODEC:
        raise ValueError("unsupported codec")
    if (
        encoded.get("view_fields") != VIEW_FIELDS
        or encoded.get("selected_fields") != SEL_FIELDS
        or encoded.get("omitted_fields") != OMIT_FIELDS
    ):
        raise ValueError("field contract mismatch")
    if not isinstance(encoded.get("view"), list) or len(encoded["view"]) != len(VIEW_FIELDS):
        raise ValueError("view row length mismatch")
    view = dict(zip(VIEW_FIELDS, encoded["view"]))
    selected = []
    for row in encoded["selected"]:
        if not isinstance(row, list) or len(row) != len(SEL_FIELDS):
            raise ValueError("selected row length mismatch")
        selected.append(dict(zip(SEL_FIELDS, row)))
    omitted = []
    for row in encoded["omitted"]:
        if not isinstance(row, list) or len(row) != len(OMIT_FIELDS):
            raise ValueError("omitted row length mismatch")
        omitted.append(dict(zip(OMIT_FIELDS, row)))
    view["selected"] = selected
    view["omitted"] = omitted
    if encoded.get("source_context_view_sha256") != sha256_text(canonical_json(view)):
        raise ValueError("source context digest mismatch")
    return view


def lexical_proxy(text: str) -> int:
    return len(LEX_RE.findall(text))


def char4_proxy(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 4)


def benchmark(n_selected: int) -> dict[str, Any]:
    view = make_view(n_selected)
    baseline = canonical_json(view)
    encoded = encode_compact(view)
    compact = canonical_json(encoded)
    recovered = decode_compact(encoded)
    assert canonical_json(recovered) == baseline

    repetitions = 500 if n_selected <= 64 else 100
    encode_ns = []
    decode_ns = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        sample = encode_compact(view)
        encode_ns.append(time.perf_counter_ns() - start)
        start = time.perf_counter_ns()
        decode_compact(sample)
        decode_ns.append(time.perf_counter_ns() - start)

    baseline_bytes = len(baseline.encode("utf-8"))
    compact_bytes = len(compact.encode("utf-8"))
    baseline_lex = lexical_proxy(baseline)
    compact_lex = lexical_proxy(compact)
    baseline_char4 = char4_proxy(baseline)
    compact_char4 = char4_proxy(compact)
    return {
        "selected": n_selected,
        "omitted": len(view["omitted"]),
        "baseline_bytes": baseline_bytes,
        "compact_bytes": compact_bytes,
        "byte_savings_pct": round(100 * (1 - compact_bytes / baseline_bytes), 6),
        "baseline_lexical_token_proxy": baseline_lex,
        "compact_lexical_token_proxy": compact_lex,
        "lexical_proxy_savings_pct":
            round(100 * (1 - compact_lex / baseline_lex), 6),
        "baseline_char4_token_proxy": baseline_char4,
        "compact_char4_token_proxy": compact_char4,
        "char4_proxy_savings_pct":
            round(100 * (1 - compact_char4 / baseline_char4), 6),
        "encode_p50_us": round(statistics.median(encode_ns) / 1000, 3),
        "decode_p50_us": round(statistics.median(decode_ns) / 1000, 3),
        "roundtrip_sha256": sha256_text(baseline),
    }


def adversarial_tests() -> dict[str, str]:
    encoded = encode_compact(make_view(16))
    cases = {}

    def expect_reject(name: str, sample: dict[str, Any]) -> None:
        try:
            decode_compact(sample)
        except ValueError as exc:
            cases[name] = f"PASS_REJECTED:{exc}"
        else:
            cases[name] = "FAIL_OPEN"

    sample = copy.deepcopy(encoded)
    sample["codec"] = "F2_CONTEXT_STRUCTURAL_COMPACTION/v0"
    expect_reject("unsupported_codec", sample)

    sample = copy.deepcopy(encoded)
    sample["selected_fields"][0], sample["selected_fields"][1] = (
        sample["selected_fields"][1],
        sample["selected_fields"][0],
    )
    expect_reject("field_order_mutation", sample)

    sample = copy.deepcopy(encoded)
    sample["selected"][0] = sample["selected"][0][:-1]
    expect_reject("row_truncation", sample)

    sample = copy.deepcopy(encoded)
    sample["selected"][0][SEL_FIELDS.index("payload_sha256")] = "0" * 64
    expect_reject("payload_digest_mutation", sample)

    sample = copy.deepcopy(encoded)
    sample["source_context_view_sha256"] = "f" * 64
    expect_reject("source_digest_tamper", sample)

    sample = copy.deepcopy(encoded)
    sample["selected_fields"][1] = sample["selected_fields"][0]
    expect_reject("duplicate_field_name", sample)

    return cases


def main() -> None:
    output = {
        "schema": "FRANKENSTEIN2_TRIGGER6_E4_STRUCTURAL_COMPACTION_ABLATION/v1",
        "scope": "RESEARCH_ONLY_SYNTHETIC_F2_STYLE_CONTEXTVIEW",
        "tokenizer_measurement":
            "NO_PINNED_TARGET_TOKENIZER_AVAILABLE; lexical and chars/4 proxies only",
        "benchmarks": [benchmark(n) for n in (1, 4, 16, 64, 256)],
        "adversarial": adversarial_tests(),
    }
    print(json.dumps(output, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
