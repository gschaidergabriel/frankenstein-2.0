#!/usr/bin/env python3
"""Bound runtime fixture for accepted F2-WP-902 G3 measurement producer.

This is an evidence harness, not a product component. It runs one deterministic,
side-effect-free Python operation repeatedly through the accepted WP902 producer,
binds every sample to the same concrete WholePersistentLoopSeal, source bundle,
host-environment fingerprint and metric schema, and emits a deterministic summary.

No provider/model/tool call, UnifiedDB mutation, external effect, completion action,
or whole-system acceptance is performed or implied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from frankenstein2.whole_persistent_loop import WholePersistentLoopSeal
from frankenstein2.whole_system_characterization import characterize_measurements
from frankenstein2.whole_system_measurement import measure_characterization_sample

RUN_CLASSIFICATION = "WP902_BOUNDED_HOST_MEASUREMENT_FIXTURE_CANDIDATE_ONLY"
MASK64 = (1 << 64) - 1
ITERATIONS = 180_000


def _kernel() -> int:
    value = 0x9E3779B97F4A7C15
    for index in range(ITERATIONS):
        value ^= (index + 0xD1B54A32D192ED03) & MASK64
        value = (value * 0x94D049BB133111EB) & MASK64
        value ^= value >> 29
    return value


EXPECTED_RESULT = _kernel()


def measured_operation() -> int:
    """Stable CPU-only operation measured by the accepted WP902 producer."""
    return _kernel()


def quality_scorer(result: int) -> int:
    """Exact deterministic correctness score outside the timed operation window."""
    return 1_000_000 if result == EXPECTED_RESULT else 0


def concrete_whole_loop_seal() -> WholePersistentLoopSeal:
    """Deterministic concrete WP900-type seal used identically by every trial.

    This is deliberately a component fixture, not a claim that the live runtime has
    exported a production WholePersistentLoopSeal.
    """
    return WholePersistentLoopSeal(
        seal_id="wp902-runtime-fixture-seal-v1",
        generation=1,
        current_checkpoint_id="wp902-fixture-cp-0",
        current_checkpoint_sha256="1" * 64,
        frame_id="wp902-fixture-frame-1",
        frame_sha256="2" * 64,
        contract_id="wp902-fixture-contract-1",
        contract_sha256="3" * 64,
        grid_plan_id="wp902-fixture-grid-1",
        grid_plan_sha256="4" * 64,
        gwt_seal_id="wp902-fixture-gwt-1",
        gwt_seal_sha256="5" * 64,
        decision_kind="ROUTE",
        decision_id="wp902-fixture-decision-1",
        decision_sha256="6" * 64,
        outcome_id="wp902-fixture-outcome-1",
        outcome_sha256="7" * 64,
        next_checkpoint_id="wp902-fixture-cp-1",
        next_checkpoint_sha256="8" * 64,
        reentry_refs=("wp902:fixture:reentry",),
        provenance_refs=("wp902:fixture:whole-loop-seal",),
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--samples-out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--identity-out", type=Path, required=True)
    parser.add_argument("--provenance-ref", action="append", default=[])
    args = parser.parse_args()

    if not 10 <= args.trials <= 100:
        raise SystemExit("trials must be in [10,100]")

    repo_root = args.repo_root.resolve(strict=True)
    fixture_rel = "tools/wp902_runtime_measurement_fixture.py"
    source_paths = (
        "src/frankenstein2/whole_system_measurement.py",
        "src/frankenstein2/whole_system_characterization.py",
        "src/frankenstein2/whole_persistent_loop.py",
        fixture_rel,
    )
    seal = concrete_whole_loop_seal()
    provenance = tuple(sorted(set(args.provenance_ref + [
        "workpackage:F2-WP-902:G3",
        "workpackages/receipts/F2-WP-902_G3_HOST_MEASUREMENT_PRODUCER.json",
        "workpackage:F2-WP-900:bounded-runtime-dependency",
        "workpackages/receipts/F2-WP-900_G3_EXTERNAL_GWT_PATH_RUNTIME_33370079622.json",
        "classification:" + RUN_CLASSIFICATION,
    ])))

    samples = []
    args.samples_out.parent.mkdir(parents=True, exist_ok=True)
    with args.samples_out.open("w", encoding="utf-8") as handle:
        for trial_index in range(args.trials):
            sample = measure_characterization_sample(
                run_id=args.run_id,
                trial_index=trial_index,
                repo_root=repo_root,
                source_paths=source_paths,
                whole_loop_seal=seal,
                operation=measured_operation,
                quality_scorer=quality_scorer,
                provenance_refs=provenance,
            )
            samples.append(sample)
            handle.write(json.dumps(sample.as_dict(), sort_keys=True) + "\n")

    first = samples[0]
    report = characterize_measurements(
        samples,
        expected_source_bundle_sha256=first.source_bundle_sha256,
        expected_whole_loop_seal_sha256=first.whole_loop_seal_sha256,
        expected_environment_fingerprint_sha256=first.environment_fingerprint_sha256,
        expected_metric_schema_id=first.metric_schema_id,
    )
    if any(sample.quality_micros != 1_000_000 for sample in samples):
        raise SystemExit("WP902 fixture quality failure")
    if len({sample.source_bundle_sha256 for sample in samples}) != 1:
        raise SystemExit("WP902 source bundle drift across trials")
    if len({sample.whole_loop_seal_sha256 for sample in samples}) != 1:
        raise SystemExit("WP902 whole-loop seal drift across trials")
    if len({sample.environment_fingerprint_sha256 for sample in samples}) != 1:
        raise SystemExit("WP902 host environment drift across trials")
    if len({sample.metric_schema_id for sample in samples}) != 1:
        raise SystemExit("WP902 metric schema drift across trials")

    report_dict = report.as_dict()
    _write_json(args.report_out, report_dict)
    _write_json(
        args.identity_out,
        {
            "schema": "F2_WP902_BOUNDED_HOST_MEASUREMENT_IDENTITY/v1",
            "classification": RUN_CLASSIFICATION,
            "run_id": args.run_id,
            "trial_count": len(samples),
            "source_bundle_sha256": first.source_bundle_sha256,
            "whole_loop_seal_id": seal.seal_id,
            "whole_loop_seal_sha256": first.whole_loop_seal_sha256,
            "environment_fingerprint_sha256": first.environment_fingerprint_sha256,
            "metric_schema_id": first.metric_schema_id,
            "sample_set_sha256": report.sample_set_sha256,
            "quality_micros_min": report.quality_micros_min,
            "quality_micros_p50": report.quality_micros_p50,
            "quality_micros_p95": report.quality_micros_p95,
            "quality_micros_max": report.quality_micros_max,
            "latency_ns_min": report.latency_ns_min,
            "latency_ns_p50": report.latency_ns_p50,
            "latency_ns_p95": report.latency_ns_p95,
            "latency_ns_max": report.latency_ns_max,
            "peak_rss_bytes_min": report.peak_rss_bytes_min,
            "peak_rss_bytes_p50": report.peak_rss_bytes_p50,
            "peak_rss_bytes_p95": report.peak_rss_bytes_p95,
            "peak_rss_bytes_max": report.peak_rss_bytes_max,
            "runtime_credit": 0,
            "target_runtime_credit": 0,
            "semantic_gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "effect_credit": 0,
            "completion_credit": 0,
            "whole_system_acceptance": False,
            "boundary": "Repeated matched execution of the accepted WP902 G3 measurement producer on a bounded deterministic component fixture. The concrete WholePersistentLoopSeal is a fixture, not an exported production whole-loop seal.",
        },
    )
    print(json.dumps({
        "status": "PASS",
        "run_id": args.run_id,
        "trial_count": len(samples),
        "source_bundle_sha256": first.source_bundle_sha256,
        "whole_loop_seal_sha256": first.whole_loop_seal_sha256,
        "environment_fingerprint_sha256": first.environment_fingerprint_sha256,
        "sample_set_sha256": report.sample_set_sha256,
        "latency_ns_p50": report.latency_ns_p50,
        "latency_ns_p95": report.latency_ns_p95,
        "quality_micros_min": report.quality_micros_min,
        "whole_system_acceptance": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
