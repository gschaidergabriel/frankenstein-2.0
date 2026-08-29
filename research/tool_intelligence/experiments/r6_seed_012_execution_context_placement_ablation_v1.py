"""R6-SEED-012 E4 deterministic research ablation.

Compares current WP507 arm serialization with two thin execution-context
binding candidates. Timing is a local research microbenchmark only, never F2
runtime evidence.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time

WP507_SOURCE_BLOB_SHA = "f25c03d4e4e49c4fed44acd0c5c96edfb40f664e"
N = 200_000


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def base_arm(arm_id: str, condition: str, output_sha: str, broadcast: bool) -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_GWT_CAUSAL_PROBE_ARM/v2",
        "classification": "DECLARED_MATCHED_PROBE_ARM_NOT_WORLD_TRUTH",
        "arm_id": arm_id,
        "probe_id": "probe-1",
        "condition": condition,
        "nonbroadcast_input_sha256": "1" * 64,
        "downstream_output_sha256": output_sha,
        "broadcast_id": "b1" if broadcast else None,
        "broadcast_sha256": "a" * 64 if broadcast else None,
        "provenance_refs": ["run:generic"],
    }


def main() -> None:
    context = {
        "schema": "FRANKENSTEIN2_PROBE_EXECUTION_CONTEXT/v1",
        "runner_identity": "runner-v1",
        "code_artifact_sha256": "4" * 64,
        "engine_identity": "engine-A",
        "execution_config_sha256": "5" * 64,
        "environment_sha256": "6" * 64,
        "sample_case_id": "case-1",
        "attempt_policy_id": "single",
    }
    context_other = dict(context)
    context_other["engine_identity"] = "engine-B"
    context_other["execution_config_sha256"] = "7" * 64
    context_sha = digest(context)
    context_other_sha = digest(context_other)

    intervention = base_arm("arm-i", "INTERVENTION_BROADCAST", "2" * 64, True)
    control = base_arm("arm-c", "CONTROL_NO_BROADCAST", "3" * 64, False)

    candidate_a_i = dict(intervention, matched_execution_context_sha256=context_sha)
    candidate_a_c = dict(control, matched_execution_context_sha256=context_other_sha)
    candidate_b_i = dict(intervention, execution_context_sha256=context_sha)
    candidate_b_c_confounded = dict(control, execution_context_sha256=context_other_sha)
    candidate_b_c_matched = dict(control, execution_context_sha256=context_sha)

    def size(value: object) -> int:
        return len(canonical_json(value).encode("utf-8"))

    eq_times: list[float] = []
    hash_times: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        for _ in range(N):
            _ = context_sha == context_other_sha
        eq_times.append(time.perf_counter() - started)
    for _ in range(5):
        started = time.perf_counter()
        for _ in range(N):
            _ = digest(context)
        hash_times.append(time.perf_counter() - started)

    baseline_bytes = size(intervention) + size(control)
    candidate_a_bytes = size(candidate_a_i) + size(candidate_a_c)
    candidate_b_confounded_bytes = (
        size(candidate_b_i) + size(candidate_b_c_confounded) + size(context) + size(context_other)
    )
    candidate_b_matched_bytes = size(candidate_b_i) + size(candidate_b_c_matched) + size(context)

    result = {
        "wp507_source_blob_sha": WP507_SOURCE_BLOB_SHA,
        "context_sha256": context_sha,
        "context_other_sha256": context_other_sha,
        "context_bytes": size(context),
        "baseline_pair_bytes": baseline_bytes,
        "candidate_a_pair_bytes": candidate_a_bytes,
        "candidate_a_added_bytes": candidate_a_bytes - baseline_bytes,
        "candidate_b_matched_pair_plus_one_shared_context_bytes": candidate_b_matched_bytes,
        "candidate_b_matched_added_bytes": candidate_b_matched_bytes - baseline_bytes,
        "candidate_b_confounded_pair_plus_two_contexts_bytes": candidate_b_confounded_bytes,
        "candidate_b_rejects_mismatch": context_sha != context_other_sha,
        "candidate_a_rejects_mismatch_if_digest_is_honestly_constructed": context_sha != context_other_sha,
        "candidate_a_has_typed_context_semantics": False,
        "candidate_b_has_typed_context_semantics": True,
        "local_research_microbenchmark": {
            "iterations": N,
            "digest_equality_ns_per_op_median": statistics.median(eq_times) / N * 1e9,
            "typed_context_sha256_us_per_op_median": statistics.median(hash_times) / N * 1e6,
            "scope": "LOCAL_RESEARCH_RUNTIME_ONLY_NOT_F2_TARGET_RUNTIME",
        },
    }
    assert result["baseline_pair_bytes"] == 968
    assert result["candidate_a_pair_bytes"] == 1172
    assert result["context_bytes"] == 438
    assert result["candidate_b_matched_pair_plus_one_shared_context_bytes"] == 1594
    assert result["candidate_b_confounded_pair_plus_two_contexts_bytes"] == 2032
    assert result["candidate_b_rejects_mismatch"] is True
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
