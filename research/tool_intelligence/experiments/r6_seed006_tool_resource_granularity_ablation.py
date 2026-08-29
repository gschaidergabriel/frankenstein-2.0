#!/usr/bin/env python3
"""R6-SEED-006 E4 research fixture: aggregate-vs-tool resource identifiability.

Research-only synthetic ablation. It does not implement F2-WP-605 and grants no runtime,
resource-controller, effect, GRID10, GWT/J-Space, training or whole-system credit.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def scenario(name: str, failed_peak_mb: int, successful_peak_mb: int) -> dict[str, Any]:
    tools = [
        {
            "tool_use_id": "tool-A",
            "effect_id": "effect-A",
            "causal_id": "cause-A",
            "exit_code": 137,
            "peak_memory_mb": failed_peak_mb,
            "duration_ms": 80,
        },
        {
            "tool_use_id": "tool-B",
            "effect_id": "effect-B",
            "causal_id": "cause-B",
            "exit_code": 0,
            "peak_memory_mb": successful_peak_mb,
            "duration_ms": 120,
        },
    ]
    return {"scenario": name, "run_id": "run-R6-SEED006-E4", "generation": 1, "tools": tools}


def aggregate_view(s: dict[str, Any]) -> dict[str, Any]:
    tools = s["tools"]
    return {
        "run_id": s["run_id"],
        "generation": s["generation"],
        "tool_count": len(tools),
        "failure_count": sum(t["exit_code"] != 0 for t in tools),
        "session_peak_memory_mb": max(t["peak_memory_mb"] for t in tools),
        "sum_tool_peak_memory_mb": sum(t["peak_memory_mb"] for t in tools),
        "total_duration_ms": sum(t["duration_ms"] for t in tools),
    }


def per_tool_performance_events(s: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for idx, t in enumerate(s["tools"], start=1):
        events.append(
            {
                "schema": "FRANKENSTEIN2_TELEMETRY_EVENT/v1",
                "event_id": f"event-{s['scenario']}-{idx}",
                "run_id": s["run_id"],
                "ts": f"2026-08-29T13:28:0{idx}Z",
                "channel": "PERFORMANCE",
                "component": "research_fixture_resource_observer",
                "event_type": "TOOL_RESOURCE_OBSERVATION",
                "session_id": "session-E4",
                "agent_id": "agent-research-fixture",
                "task_id": "task-resource-identifiability",
                "turn_id": "turn-1",
                "tool_use_id": t["tool_use_id"],
                "effect_id": t["effect_id"],
                "causal_id": t["causal_id"],
                "generation": s["generation"],
                "epistemic_status": "OBSERVED",
                "payload": {
                    "metric_semantics": "SYNTHETIC_GROUND_TRUTH_FOR_RESEARCH_ABLATION",
                    "exit_code": t["exit_code"],
                    "peak_memory_mb": t["peak_memory_mb"],
                    "termination_cause": "UNKNOWN",
                    "coverage_status": "MEASURED_SYNTHETIC",
                },
                "provenance_refs": ["R6-SEED-006/E4_F2_TOOL_RESOURCE_GRANULARITY_ABLATION"],
            }
        )
    return events


def failed_tool_has_session_peak(s: dict[str, Any]) -> bool:
    failed = next(t for t in s["tools"] if t["exit_code"] != 0)
    return failed["peak_memory_mb"] == max(t["peak_memory_mb"] for t in s["tools"])


def main() -> None:
    a = scenario("A_FAILED_TOOL_IS_HIGH_PEAK", failed_peak_mb=320, successful_peak_mb=60)
    b = scenario("B_SUCCESSFUL_TOOL_IS_HIGH_PEAK", failed_peak_mb=60, successful_peak_mb=320)

    aggregate_a = aggregate_view(a)
    aggregate_b = aggregate_view(b)
    events_a = per_tool_performance_events(a)
    events_b = per_tool_performance_events(b)

    result = {
        "schema": "FRANKENSTEIN2_TRIGGER6_E4_RESOURCE_GRANULARITY_ABLATION_RESULT/v1",
        "baseline_aggregate_digest_a": digest(aggregate_a),
        "baseline_aggregate_digest_b": digest(aggregate_b),
        "baseline_collision": aggregate_a == aggregate_b,
        "candidate_tool_event_digest_a": digest(events_a),
        "candidate_tool_event_digest_b": digest(events_b),
        "candidate_collision": events_a == events_b,
        "causal_question": "does the failed tool carry the run's highest observed tool peak?",
        "scenario_a_answer": failed_tool_has_session_peak(a),
        "scenario_b_answer": failed_tool_has_session_peak(b),
        "interpretation": "Aggregate run metrics collide while the causal answer differs; tool/effect-bound PERFORMANCE events preserve the distinction.",
        "credit_boundary": "RESEARCH_FIXTURE_ONLY_NO_F2_RUNTIME_OR_BUILD_CREDIT",
    }
    print(canonical(result))


if __name__ == "__main__":
    main()
