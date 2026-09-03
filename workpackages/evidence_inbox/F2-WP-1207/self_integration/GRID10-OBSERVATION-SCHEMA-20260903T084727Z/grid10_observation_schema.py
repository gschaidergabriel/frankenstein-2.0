#!/usr/bin/env python3
"""F2-WP-1207: GRID10 functionally-neutral observation schema + harness.

Gabriel's directive (2026-09-03, verbatim summary): GRID10 (`G1`..`G10`) has
no semantic cell assignment yet. Giving cells names now ("G3 = memory") would
be ARCHITECTURE ASSERTED, not MEASURED. Instead: keep cells functionally
neutral and let a real functional role emerge later from observed data:
Inputs, Outputs, Uptake, Reentry, Konflikte (conflicts), Ressourcenverbrauch
(resource use), zeitliche Korrelationen (temporal correlations).

This file does two things:
  1. Defines an OBSERVATION SCHEMA (`GRID10_OBSERVATION_EVENT_SCHEMA` /
     `GRID10_OBSERVATION_REPORT_SCHEMA`) -- a structured, versioned JSON
     shape for exactly those seven dimensions, keyed only by
     `logical_cell_id` (G1..G10). No field anywhere carries a name, role,
     or interpretation for a cell. This is enforced by a runtime assertion
     (`_assert_no_semantic_leakage`) that scans every emitted record for any
     of a short deny-list of interpretive/naming tokens before it is
     written -- a mechanical guard against the exact trap Gabriel warned
     about, not just a promise in prose.
  2. Implements a harness that drives the real, unmodified
     `frankenstein2.grid10_interface` ABI (F2-WP-503; see
     LOCAL-ITER3/grid10_compat_check.py in this same tree for the read-only
     compatibility proof this harness builds on) through a batch of
     synthetic "cycles" and records real, measured per-touch wall-clock
     timing (`time.perf_counter_ns`) plus a whole-run `resource.getrusage`
     delta. It is still entirely synthetic data (no v1 file, no v1 DB row,
     no live process) -- same safety posture as LOCAL-ITER3 -- but produces
     genuinely distinguishable per-cell numbers instead of ten identical
     empty rows, because the synthetic drive pattern is index-formulaic
     (arbitrary, deterministic, cell-index-keyed) rather than uniform.

WHY THE DRIVE PATTERN IS FORMULAIC, NOT NARRATIVE:
  It would be easy to accidentally smuggle semantics in through the *shape*
  of synthetic test data ("let's make G3 the cell that gets reused a lot,
  like a working-memory buffer..."). That is exactly the trap. So every
  per-cell parameter here (touch probability, reentry depth, status pick,
  work units) is a closed-form function of the cell's 1-based index only
  (`cell_index = int(cell_id[1:])`), applied identically to every cell.
  There is no per-cell special-casing, no cell picked out by name or story.
  The resulting variance is real (different cells get different numbers)
  but its SOURCE is an arbitrary index formula, not a claim about what any
  cell "does". A future run against real production traffic would replace
  this synthetic driver with actual GRID10Plan/CellInput/CellOutput events
  and the schema below would not need to change.

Usage:
    python3 grid10_observation_schema.py > grid10_observation_report.json
"""
from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src"))

from frankenstein2.grid10_interface import (  # noqa: E402
    CellBudget,
    CellInput,
    CellOutput,
    GRID10_CELL_IDS,
    Grid10InterfaceError,
    Grid10Plan,
    account_outputs,
)

GRID10_OBSERVATION_EVENT_SCHEMA = "FRANKENSTEIN2_GRID10_OBSERVATION_EVENT/v1"
GRID10_OBSERVATION_REPORT_SCHEMA = "FRANKENSTEIN2_GRID10_OBSERVATION_REPORT/v1"

# Mechanical guard: none of these tokens (nor obvious variants) may appear in
# any per-cell label/value this script writes. Deliberately blunt substring
# match over the canonical-JSON dump of every record -- cheap, and a false
# positive just means picking a different formula constant, not a real cost.
_SEMANTIC_LEAKAGE_DENYLIST = (
    "memory", "gedaechtnis", "gedächtnis", "attention", "reasoning",
    "planning", "planer", "executive", "sensor", "motor", "perception",
    "wahrnehmung", "emotion", "language", "sprache", "vision", "identity",
    "self", "ego", "control", "steuerung", "working memory", "buffer",
    "cache", "role=", "roleof", "function=", "semantik", "semantic_role",
)

_OUTPUT_STATUS_CYCLE = ("COMPLETE", "PARTIAL", "ABSTAIN", "UNKNOWN", "NOT_COMPUTED")

N_SCENARIOS = 24
UNIFORM_BUDGET = CellBudget  # alias for readability at call sites


def _assert_no_semantic_leakage(record: Any) -> None:
    blob = json.dumps(record, sort_keys=True, ensure_ascii=False).lower()
    for token in _SEMANTIC_LEAKAGE_DENYLIST:
        if token in blob:
            raise AssertionError(
                f"semantic leakage guard tripped: forbidden token {token!r} "
                f"found in observation record -- refusing to emit"
            )


def _cell_index(cell_id: str) -> int:
    return int(cell_id[1:])


def _budget_for(cell_id: str) -> CellBudget:
    # Identical shape for every cell on purpose -- the ABI budget itself
    # carries no per-cell distinction; only the *drive pattern* below varies.
    return CellBudget(
        cell_id=cell_id,
        role_label=f"observation-schema-neutral-slot-{cell_id}",
        max_input_refs=6,
        max_output_refs=4,
        max_work_units=9,
        max_reentry_depth=3,
    )


def _touch_probability(cell_index: int) -> float:
    # Arbitrary closed-form index formula. See module docstring: this is
    # deliberately mechanical, not a narrative choice about any cell.
    return 0.25 + 0.055 * cell_index  # G1 -> 0.305 .. G10 -> 0.80


def _should_touch(cell_index: int, scenario_index: int) -> bool:
    # Deterministic pseudo-selection derived from a simple LCG-style mix of
    # (scenario_index, cell_index) mapped into [0,1), compared against the
    # index-formulaic probability above. No RNG import needed, fully
    # reproducible run-to-run.
    mixed = (scenario_index * 2654435761 + cell_index * 40503) & 0xFFFFFFFF
    frac = mixed / 0xFFFFFFFF
    return frac < _touch_probability(cell_index)


def _reentry_depth_for(cell_index: int, scenario_index: int, budget: CellBudget) -> int:
    return (scenario_index + cell_index) % (budget.max_reentry_depth + 1)


def _work_units_requested_for(cell_index: int, scenario_index: int, budget: CellBudget) -> int:
    return 1 + ((scenario_index * 3 + cell_index * 2) % budget.max_work_units)


def _status_for(cell_index: int, scenario_index: int) -> str:
    return _OUTPUT_STATUS_CYCLE[(scenario_index + cell_index) % len(_OUTPUT_STATUS_CYCLE)]


def _work_units_used_for(requested: int, cell_index: int, scenario_index: int) -> int:
    # Never exceed requested (ABI invariant); vary how much of the request
    # is "used" via the same index formula family.
    if requested == 0:
        return 0
    used_fraction_step = (scenario_index + cell_index) % (requested + 1)
    return used_fraction_step


def _ref_list(prefix: str, count: int) -> tuple[str, ...]:
    return tuple(f"{prefix}-{i:03d}" for i in range(count))


def _ref_length_stats(refs: tuple[str, ...]) -> dict[str, float]:
    if not refs:
        return {"count": 0, "min_chars": 0, "max_chars": 0, "avg_chars": 0.0}
    lengths = [len(r) for r in refs]
    return {
        "count": len(refs),
        "min_chars": min(lengths),
        "max_chars": max(lengths),
        "avg_chars": sum(lengths) / len(lengths),
    }


def run_scenarios(n_scenarios: int = N_SCENARIOS) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    conflict_observations: list[dict[str, Any]] = []

    rusage_before = resource.getrusage(resource.RUSAGE_SELF)
    wall_before = time.perf_counter()

    for scenario_index in range(n_scenarios):
        cells = tuple(_budget_for(cid) for cid in GRID10_CELL_IDS)
        plan = Grid10Plan.create(
            plan_id=f"grid10-obs-schema-scenario-{scenario_index:03d}",
            cycle_id=f"obs-cycle-{scenario_index:03d}",
            generation=0,
            frame_id=f"obs-frame-{scenario_index:03d}",
            frame_generation=0,
            frame_sha256="c" * 64,
            policy_id="obs-policy-neutral",
            policy_generation=0,
            policy_sha256="d" * 64,
            cells=cells,
            max_total_work_units=999,
            provenance_refs=(f"synthetic:grid10-obs-schema:scenario-{scenario_index:03d}",),
        )

        pairs = []
        sequence_index = 0
        for cell_id in GRID10_CELL_IDS:
            cell_index = _cell_index(cell_id)
            if not _should_touch(cell_index, scenario_index):
                continue  # this cell is simply not touched in this cycle
            budget = plan.budget_for(cell_id)

            requested = _work_units_requested_for(cell_index, scenario_index, budget)
            reentry_depth = _reentry_depth_for(cell_index, scenario_index, budget)
            input_refs = _ref_list(f"in-{cell_id}-{scenario_index:03d}", cell_index % (budget.max_input_refs + 1))

            t0 = time.perf_counter_ns()
            try:
                cell_input = CellInput.for_plan(
                    plan,
                    cell_id=cell_id,
                    work_units_requested=requested,
                    reentry_depth=reentry_depth,
                    input_refs=input_refs,
                    provenance_refs=(f"synthetic:grid10-obs-schema:{cell_id}:{scenario_index:03d}",),
                )

                status = _status_for(cell_index, scenario_index)
                used = _work_units_used_for(requested, cell_index, scenario_index)
                output_refs = _ref_list(f"out-{cell_id}-{scenario_index:03d}", cell_index % (budget.max_output_refs + 1))
                evidence_refs = _ref_list(f"ev-{cell_id}-{scenario_index:03d}", 1)

                cell_output = CellOutput.for_input(
                    plan,
                    cell_input,
                    status=status,
                    work_units_used=used,
                    output_refs=output_refs,
                    evidence_refs=evidence_refs,
                    provenance_refs=(f"synthetic:grid10-obs-schema:{cell_id}:{scenario_index:03d}:out",),
                )
                t1 = time.perf_counter_ns()

                event = {
                    "schema": GRID10_OBSERVATION_EVENT_SCHEMA,
                    "scenario_index": scenario_index,
                    "plan_id": plan.plan_id,
                    "cycle_id": plan.cycle_id,
                    "logical_cell_id": cell_id,
                    "sequence_index": sequence_index,
                    "outcome": "ok",
                    "wall_time_ns": t1 - t0,
                    "input": {
                        "work_units_requested": requested,
                        "reentry_depth": reentry_depth,
                        "input_ref_stats": _ref_length_stats(input_refs),
                        "provenance_ref_count": 1,
                    },
                    "output": {
                        "status": status,
                        "work_units_used": used,
                        "output_ref_stats": _ref_length_stats(output_refs),
                        "evidence_ref_count": len(evidence_refs),
                    },
                }
                pairs.append((cell_input, cell_output))
                sequence_index += 1
            except Grid10InterfaceError as exc:
                t1 = time.perf_counter_ns()
                event = {
                    "schema": GRID10_OBSERVATION_EVENT_SCHEMA,
                    "scenario_index": scenario_index,
                    "plan_id": plan.plan_id,
                    "cycle_id": plan.cycle_id,
                    "logical_cell_id": cell_id,
                    "sequence_index": sequence_index,
                    "outcome": "rejected",
                    "wall_time_ns": t1 - t0,
                    "rejection_reason": str(exc),
                    "input": None,
                    "output": None,
                }
                sequence_index += 1

            _assert_no_semantic_leakage(event)
            events.append(event)

        # account_outputs closes out this cycle's receipt -- exercises the
        # real ABI accounting path (not just construction) for whichever
        # subset of cells this synthetic cycle actually touched.
        if pairs:
            receipt = account_outputs(plan, pairs)
            _ = receipt  # receipt itself is not semantic; not stored per-cell here

    # --- deliberate structural CONFLICT probes (not part of the 24-scenario
    # uptake/timing loop above; these are two isolated, explicit tests of
    # what the ABI does and does not detect) ---

    # Probe 1: two CellOutputs for the SAME logical cell inside ONE
    # account_outputs() call -- the one conflict shape the module actively
    # detects and rejects.
    probe_cells = tuple(_budget_for(cid) for cid in GRID10_CELL_IDS)
    probe_plan = Grid10Plan.create(
        plan_id="grid10-obs-schema-conflict-probe-1",
        cycle_id="conflict-probe-1",
        generation=0,
        frame_id="conflict-probe-1-frame",
        frame_generation=0,
        frame_sha256="e" * 64,
        policy_id="conflict-probe-policy",
        policy_generation=0,
        policy_sha256="f" * 64,
        cells=probe_cells,
        max_total_work_units=999,
        provenance_refs=("synthetic:grid10-obs-schema:conflict-probe-1",),
    )
    target_cell = "G5"  # arbitrary fixed choice for reproducibility, not semantic
    ci_a = CellInput.for_plan(
        probe_plan, cell_id=target_cell, work_units_requested=2, reentry_depth=0,
        input_refs=(), provenance_refs=("synthetic:conflict-probe-1:a",),
    )
    co_a = CellOutput.for_input(
        probe_plan, ci_a, status="COMPLETE", work_units_used=1,
        provenance_refs=("synthetic:conflict-probe-1:a:out",),
    )
    ci_b = CellInput.for_plan(
        probe_plan, cell_id=target_cell, work_units_requested=2, reentry_depth=1,
        input_refs=(), provenance_refs=("synthetic:conflict-probe-1:b",),
    )
    co_b = CellOutput.for_input(
        probe_plan, ci_b, status="COMPLETE", work_units_used=1,
        provenance_refs=("synthetic:conflict-probe-1:b:out",),
    )
    try:
        account_outputs(probe_plan, [(ci_a, co_a), (ci_b, co_b)])
        probe1_result = {"detected": False, "note": "UNEXPECTED: no error raised"}
    except Grid10InterfaceError as exc:
        probe1_result = {"detected": True, "error": str(exc)}
    conflict_observations.append({
        "probe": "same_cell_twice_in_one_account_outputs_call",
        "target_cell": target_cell,
        "result": probe1_result,
        "conclusion": (
            "ABI actively detects and hard-rejects two CellOutputs for the "
            "same logical_cell_id within a single account_outputs() call."
            if probe1_result["detected"]
            else "ABI did NOT reject duplicate cell outputs -- investigate."
        ),
    })

    # Probe 2: two INDEPENDENT Grid10Plan instances (different frame_id,
    # different plan_id) both constructing CellInput/CellOutput for the SAME
    # logical_cell_id, interleaved in wall-clock/code order. The module has
    # no shared mutable state (no module-level registry, no lock, no global
    # counter) -- so honestly: it cannot detect this as a conflict, because
    # from its point of view there is no second party to conflict with.
    plan_x = Grid10Plan.create(
        plan_id="grid10-obs-schema-conflict-probe-2-x", cycle_id="cp2-x", generation=0,
        frame_id="cp2-frame-x", frame_generation=0, frame_sha256="1" * 64,
        policy_id="cp2-policy-x", policy_generation=0, policy_sha256="2" * 64,
        cells=tuple(_budget_for(cid) for cid in GRID10_CELL_IDS),
        max_total_work_units=999, provenance_refs=("synthetic:cp2:x",),
    )
    plan_y = Grid10Plan.create(
        plan_id="grid10-obs-schema-conflict-probe-2-y", cycle_id="cp2-y", generation=0,
        frame_id="cp2-frame-y", frame_generation=0, frame_sha256="3" * 64,
        policy_id="cp2-policy-y", policy_generation=0, policy_sha256="4" * 64,
        cells=tuple(_budget_for(cid) for cid in GRID10_CELL_IDS),
        max_total_work_units=999, provenance_refs=("synthetic:cp2:y",),
    )
    same_cell = "G8"  # arbitrary fixed choice, not semantic
    ci_x = CellInput.for_plan(plan_x, cell_id=same_cell, work_units_requested=3, reentry_depth=0,
                               input_refs=(), provenance_refs=("synthetic:cp2:x:in",))
    ci_y = CellInput.for_plan(plan_y, cell_id=same_cell, work_units_requested=3, reentry_depth=0,
                               input_refs=(), provenance_refs=("synthetic:cp2:y:in",))
    co_x = CellOutput.for_input(plan_x, ci_x, status="COMPLETE", work_units_used=1,
                                 provenance_refs=("synthetic:cp2:x:out",))
    co_y = CellOutput.for_input(plan_y, ci_y, status="COMPLETE", work_units_used=1,
                                 provenance_refs=("synthetic:cp2:y:out",))
    both_succeeded_independently = True
    try:
        account_outputs(plan_x, [(ci_x, co_x)])
        account_outputs(plan_y, [(ci_y, co_y)])
    except Grid10InterfaceError:
        both_succeeded_independently = False
    conflict_observations.append({
        "probe": "same_cell_across_two_independent_plans",
        "target_cell": same_cell,
        "result": {"both_accounted_independently": both_succeeded_independently},
        "conclusion": (
            "Confirmed by code reading and by this probe: grid10_interface.py "
            "has no module-level mutable state (no registry/lock/counter) "
            "shared across Grid10Plan instances. Two independent frames "
            "claiming the same logical_cell_id is therefore structurally "
            "UNDETECTABLE by this module -- not because it is proven safe, "
            "but because the module has no notion of 'another plan' to "
            "conflict with. Any real cross-frame conflict guard would have "
            "to live in whatever orchestrator constructs/dispatches "
            "Grid10Plan instances, not in this ABI itself."
        ),
    })

    wall_after = time.perf_counter()
    rusage_after = resource.getrusage(resource.RUSAGE_SELF)

    resource_summary = {
        "wall_clock_seconds_total": wall_after - wall_before,
        "ru_utime_delta_seconds": rusage_after.ru_utime - rusage_before.ru_utime,
        "ru_stime_delta_seconds": rusage_after.ru_stime - rusage_before.ru_stime,
        "ru_maxrss_before_kb": rusage_before.ru_maxrss,
        "ru_maxrss_after_kb": rusage_after.ru_maxrss,
        "ru_maxrss_delta_kb": rusage_after.ru_maxrss - rusage_before.ru_maxrss,
        "note": (
            "getrusage granularity is coarse (whole-process, whole-run); "
            "per-touch cost is measured separately via time.perf_counter_ns "
            "on each event ('wall_time_ns'). Both are real measurements, "
            "not estimates."
        ),
    }

    return {
        "events": events,
        "conflict_observations": conflict_observations,
        "resource_summary": resource_summary,
        "n_scenarios": n_scenarios,
    }


def _percentile(sorted_values: list[int], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def aggregate_per_cell(events: list[dict[str, Any]], n_scenarios: int) -> dict[str, Any]:
    per_cell: dict[str, Any] = {}
    for cell_id in GRID10_CELL_IDS:
        cell_events = [e for e in events if e["logical_cell_id"] == cell_id]
        ok_events = [e for e in cell_events if e["outcome"] == "ok"]
        touches = len(ok_events)
        wall_times = sorted(e["wall_time_ns"] for e in ok_events)
        reentry_values = [e["input"]["reentry_depth"] for e in ok_events]
        status_dist: dict[str, int] = {}
        work_used_total = 0
        for e in ok_events:
            st = e["output"]["status"]
            status_dist[st] = status_dist.get(st, 0) + 1
            work_used_total += e["output"]["work_units_used"]

        per_cell[cell_id] = {
            "logical_cell_id": cell_id,
            "uptake": {
                "touches": touches,
                "scenarios_total": n_scenarios,
                "touch_rate": touches / n_scenarios if n_scenarios else 0.0,
            },
            "inputs": {
                "input_ref_count_total": sum(e["input"]["input_ref_stats"]["count"] for e in ok_events),
                "work_units_requested_total": sum(e["input"]["work_units_requested"] for e in ok_events),
            },
            "outputs": {
                "status_distribution": status_dist,
                "work_units_used_total": work_used_total,
                "output_ref_count_total": sum(e["output"]["output_ref_stats"]["count"] for e in ok_events),
            },
            "reentry": {
                "values_observed": reentry_values,
                "max_reentry_depth_seen": max(reentry_values) if reentry_values else 0,
                "reentry_gt0_count": sum(1 for r in reentry_values if r > 0),
            },
            "resource": {
                "wall_time_ns_count": len(wall_times),
                "wall_time_ns_min": wall_times[0] if wall_times else 0,
                "wall_time_ns_max": wall_times[-1] if wall_times else 0,
                "wall_time_ns_mean": (sum(wall_times) / len(wall_times)) if wall_times else 0.0,
                "wall_time_ns_p50": _percentile(wall_times, 0.5),
                "wall_time_ns_p95": _percentile(wall_times, 0.95),
                "wall_time_ns_total": sum(wall_times),
            },
        }
    return per_cell


def temporal_correlation(events: list[dict[str, Any]], n_scenarios: int) -> dict[str, Any]:
    """Pure co-occurrence observation across scenario-cycles: how often are
    two cells touched within the SAME scenario, and how often does one
    cell's sequence_index immediately precede another's within a scenario.
    No interpretation -- raw counts + normalized rates only."""
    by_scenario: dict[int, list[str]] = {}
    for e in events:
        if e["outcome"] != "ok":
            continue
        by_scenario.setdefault(e["scenario_index"], []).append(e["logical_cell_id"])

    co_occurrence: dict[str, int] = {}
    immediate_adjacency: dict[str, int] = {}
    touch_counts: dict[str, int] = {cid: 0 for cid in GRID10_CELL_IDS}

    for scenario_index, touched_in_order in by_scenario.items():
        touched_set = set(touched_in_order)
        for cid in touched_set:
            touch_counts[cid] += 1
        cells_sorted = sorted(touched_set)
        for i, a in enumerate(cells_sorted):
            for b in cells_sorted[i + 1:]:
                key = f"{a}|{b}"
                co_occurrence[key] = co_occurrence.get(key, 0) + 1
        for i in range(len(touched_in_order) - 1):
            a, b = touched_in_order[i], touched_in_order[i + 1]
            if a == b:
                continue
            key = f"{a}->{b}"
            immediate_adjacency[key] = immediate_adjacency.get(key, 0) + 1

    co_occurrence_normalized = {}
    for key, count in co_occurrence.items():
        a, b = key.split("|")
        union = touch_counts[a] + touch_counts[b] - count
        co_occurrence_normalized[key] = {
            "co_occurrences": count,
            "jaccard": (count / union) if union else 0.0,
        }

    return {
        "note": (
            "Raw co-occurrence + immediate-sequence-adjacency counts across "
            f"{n_scenarios} synthetic scenario-cycles. Purely observational -- "
            "no semantic or causal interpretation. Because this run's drive "
            "pattern is an independent per-cell touch-probability formula "
            "(no cross-cell coupling was coded), any correlation seen here "
            "should be close to what independent-probability chance predicts; "
            "a REAL production run against actual GRID10 traffic through this "
            "same schema would be the one where non-chance correlation is "
            "actually meaningful to look for."
        ),
        "cell_touch_counts": touch_counts,
        "pairwise_co_occurrence": co_occurrence_normalized,
        "immediate_sequence_adjacency": immediate_adjacency,
    }


def build_report() -> dict[str, Any]:
    run = run_scenarios(N_SCENARIOS)
    events = run["events"]
    per_cell = aggregate_per_cell(events, run["n_scenarios"])
    temporal = temporal_correlation(events, run["n_scenarios"])

    for cell_report in per_cell.values():
        _assert_no_semantic_leakage(cell_report)
    _assert_no_semantic_leakage(temporal)

    distinguishable_check = {
        "touch_rate_min": min(c["uptake"]["touch_rate"] for c in per_cell.values()),
        "touch_rate_max": max(c["uptake"]["touch_rate"] for c in per_cell.values()),
        "touch_rate_spread_nonzero": (
            max(c["uptake"]["touch_rate"] for c in per_cell.values())
            - min(c["uptake"]["touch_rate"] for c in per_cell.values())
        ) > 0,
        "wall_time_ns_mean_min": min(c["resource"]["wall_time_ns_mean"] for c in per_cell.values() if c["resource"]["wall_time_ns_count"]),
        "wall_time_ns_mean_max": max(c["resource"]["wall_time_ns_mean"] for c in per_cell.values() if c["resource"]["wall_time_ns_count"]),
        "at_least_one_cell_never_touched_or_always_touched": any(
            c["uptake"]["touches"] == 0 or c["uptake"]["touches"] == run["n_scenarios"]
            for c in per_cell.values()
        ),
    }

    report = {
        "schema": GRID10_OBSERVATION_REPORT_SCHEMA,
        "check": "F2-WP-1207-grid10-observation-schema",
        "python_version": sys.version,
        "n_scenarios": run["n_scenarios"],
        "semantic_neutrality": {
            "policy": (
                "No logical_cell_id (G1..G10) is assigned a name, role, or "
                "functional interpretation anywhere in this report. Every "
                "record was scanned against a denylist of interpretive "
                "tokens before being emitted (see _assert_no_semantic_leakage "
                "in the source); this run passed that guard for all "
                f"{len(events)} events + 10 per-cell aggregates + the "
                "temporal-correlation block."
            ),
            "denylist_size": len(_SEMANTIC_LEAKAGE_DENYLIST),
        },
        "per_cell": per_cell,
        "temporal_correlation": temporal,
        "conflict_observations": run["conflict_observations"],
        "resource_summary": run["resource_summary"],
        "distinguishability_check": distinguishable_check,
        "raw_event_count": len(events),
    }
    return report


def main() -> int:
    report = build_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
