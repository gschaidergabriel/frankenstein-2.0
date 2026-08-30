#!/usr/bin/env python3
"""Fail-closed guard for T7-ASR-008 geometry evidence.

The current ASR008 comparator varies ``rnnt_right_context`` but does not pass a
chunk-duration control to NeMo-Speech.cpp.  Therefore a numeric ``chunk_ms`` in
an ASR008 receipt is an unexecuted dimension and must not be used for runtime
promotion.

This guard intentionally does *not* guess a NeMo-Speech.cpp CLI option.  A
future comparator may remove the numeric chunk claim, or may add explicit
executed invocation evidence for a real chunk control and update this guard in
the same evidence-bearing change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "T7_ASR008_NEMOTRON35_TARGET_COMPARATOR_RECEIPT/v1"
GUARD_SCHEMA = "T7_ASR008_GEOMETRY_GUARD/v1"


def evaluate(receipt: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []

    if receipt.get("schema") != SCHEMA:
        reasons.append("RECEIPT_SCHEMA_MISMATCH")

    configs = receipt.get("configs")
    if not isinstance(configs, list) or not configs:
        reasons.append("CONFIGS_MISSING")
        configs = []

    numeric_chunk_claims: list[dict[str, Any]] = []
    for index, config in enumerate(configs):
        if not isinstance(config, dict):
            reasons.append(f"CONFIG_{index}_NOT_OBJECT")
            continue
        metrics = config.get("metrics")
        if not isinstance(metrics, dict):
            reasons.append(f"CONFIG_{index}_METRICS_MISSING")
            continue
        chunk_ms = metrics.get("chunk_ms")
        if isinstance(chunk_ms, (int, float)) and not isinstance(chunk_ms, bool):
            numeric_chunk_claims.append({
                "config_index": index,
                "chunk_ms": chunk_ms,
                "language": metrics.get("language"),
                "rnnt_right_context": metrics.get("rnnt_right_context"),
            })

    det = receipt.get("deterministic_rerun")
    if isinstance(det, dict):
        chunk_ms = det.get("chunk_ms")
        if isinstance(chunk_ms, (int, float)) and not isinstance(chunk_ms, bool):
            numeric_chunk_claims.append({
                "config_index": "deterministic_rerun",
                "chunk_ms": chunk_ms,
                "language": det.get("language"),
                "rnnt_right_context": det.get("rnnt_right_context"),
            })

    top_geometry = receipt.get("streaming_geometry")
    if isinstance(top_geometry, list):
        for index, item in enumerate(top_geometry):
            if not isinstance(item, dict):
                continue
            chunk_ms = item.get("chunk_ms")
            if isinstance(chunk_ms, (int, float)) and not isinstance(chunk_ms, bool):
                numeric_chunk_claims.append({
                    "config_index": f"streaming_geometry_{index}",
                    "chunk_ms": chunk_ms,
                    "rnnt_right_context": item.get("rnnt_right_context"),
                })

    if numeric_chunk_claims:
        reasons.append("EVIDENCE_INVALID_UNBOUND_CHUNK_DIMENSION")

    accepted = not reasons
    return {
        "schema": GUARD_SCHEMA,
        "accepted": accepted,
        "classification": (
            "ACCEPTED_GEOMETRY_SCOPE"
            if accepted
            else "EVIDENCE_INVALID"
        ),
        "reasons": reasons,
        "numeric_chunk_claims": numeric_chunk_claims,
        "credit": {
            "asr008_geometry_evidence_credit": int(accepted),
            "target_runtime_promotion_allowed_by_this_guard": int(accepted),
            "german_asr_quality_credit": 0,
            "production_streaming_credit": 0,
            "physical_device_credit": 0,
            "gwt_jspace_credit": 0,
            "effect_credit": 0,
            "training_credit": 0,
            "whole_product_credit": 0,
        },
        "next_exact_action": (
            "Bind a real NeMo-Speech.cpp chunk-duration control in the executed invocation, "
            "or remove chunk_ms as an executed dimension from ASR008 receipts; then update this guard with exact CLI evidence."
            if numeric_chunk_claims
            else "No unbound numeric chunk dimension detected; continue normal receipt validation."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("receipt", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    result = evaluate(receipt)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
