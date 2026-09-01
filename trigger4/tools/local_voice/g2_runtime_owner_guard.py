#!/usr/bin/env python3
"""Fail-closed singleton guard for the promotion-bearing Trigger-4 G2 S2 run.

Only two exact, already-recorded historical subjects may be exempted, and only
while GitHub still proves they are queued and have never started a job. Any
in-progress run, changed subject, missing job evidence, or future queue remains
a blocking owner.
"""
from __future__ import annotations

import json
import os
from typing import Any
import urllib.request

WORKFLOW = "t4-g2-pipewire-monitor-cancel.yml"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"

# Exact subjects declared historical-only by the current G2 repair evidence.
# This is intentionally closed-world: adding another exemption requires a new
# reviewed source change and fresh evidence.
EXPLICITLY_INVALIDATED_QUEUED_SUBJECTS = {
    ("33554493024", "6cf8ba3a6ae013083b1013e782d3fff2a373d75b"): {
        "reason": "pre-required-repair G2 subject; terminal promotion invalidated",
        "evidence": "research/local_voice/falsifiers/2026-09-02_T4_G2_STALE_QUEUE_SINGLETON_DEADLOCK_GPT56SOL.json",
    },
    ("33554578605", "eea45dbd94738adb92c4d439ea90534062044239"): {
        "reason": "analyzer-v2 duplicate predating terminal H1/H2/H3/H5 and launcher repairs",
        "evidence": "research/local_voice/falsifiers/2026-09-02_T4_G2_STALE_QUEUE_SINGLETON_DEADLOCK_GPT56SOL.json",
    },
}


def _api_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("GITHUB_RESPONSE_NOT_OBJECT")
    return value


def jobs_prove_never_started(jobs: list[dict[str, Any]]) -> bool:
    """Return true only when at least one job exists and every job is untouched/queued."""
    if not jobs:
        return False
    for job in jobs:
        if not isinstance(job, dict):
            return False
        if job.get("status") != "queued" or job.get("conclusion") is not None:
            return False
        steps = job.get("steps")
        if steps not in (None, []):
            return False
    return True


def can_exempt_stale_queued_run(run: dict[str, Any], jobs: list[dict[str, Any]]) -> bool:
    run_id = str(run.get("id"))
    head_sha = str(run.get("head_sha") or "")
    if (run_id, head_sha) not in EXPLICITLY_INVALIDATED_QUEUED_SUBJECTS:
        return False
    if run.get("status") != "queued":
        return False
    if run.get("conclusion") is not None:
        return False
    # Both invalidated subjects were historical push auto-dispatches. Never let a
    # manual/current dispatch inherit their exemption merely by reusing an id/sha
    # shape in test fixtures or future code.
    if run.get("event") != "push":
        return False
    return jobs_prove_never_started(jobs)


def evaluate_runs(
    runs: list[dict[str, Any]],
    *,
    current_run_id: str,
    jobs_by_run: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    owners: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("id"))
        if run_id == current_run_id:
            continue
        jobs = jobs_by_run.get(run_id, [])
        if can_exempt_stale_queued_run(run, jobs):
            exempted.append(
                {
                    "id": run_id,
                    "status": run.get("status"),
                    "head_sha": run.get("head_sha"),
                    "event": run.get("event"),
                    "reason": EXPLICITLY_INVALIDATED_QUEUED_SUBJECTS[(run_id, str(run.get("head_sha")))]["reason"],
                }
            )
            continue
        owners.append(
            {
                "id": run_id,
                "status": run.get("status"),
                "head_sha": run.get("head_sha"),
                "event": run.get("event"),
            }
        )
    return owners, exempted


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    current_run_id = str(os.environ["GITHUB_RUN_ID"])
    token = os.environ["GH_TOKEN"]

    runs: list[dict[str, Any]] = []
    for status in ("queued", "in_progress"):
        payload = _api_json(
            f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW}/runs?status={status}&per_page=100",
            token,
        )
        items = payload.get("workflow_runs") or []
        if not isinstance(items, list):
            raise RuntimeError("GITHUB_WORKFLOW_RUNS_NOT_LIST")
        runs.extend(item for item in items if isinstance(item, dict))

    jobs_by_run: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        run_id = str(run.get("id"))
        if run_id == current_run_id:
            continue
        # Job evidence is fetched for every candidate. A missing/invalid response
        # therefore fails closed rather than silently qualifying an exemption.
        payload = _api_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
        jobs = payload.get("jobs") or []
        if not isinstance(jobs, list):
            raise RuntimeError(f"GITHUB_RUN_JOBS_NOT_LIST:{run_id}")
        jobs_by_run[run_id] = [job for job in jobs if isinstance(job, dict)]

    owners, exempted = evaluate_runs(runs, current_run_id=current_run_id, jobs_by_run=jobs_by_run)
    if exempted:
        print("T4_G2_EXEMPTED_INVALIDATED_QUEUED_SUBJECTS=" + json.dumps(exempted, sort_keys=True))
    if owners:
        print("T4_G2_DUPLICATE_NONTERMINAL_OWNER=" + json.dumps(owners, sort_keys=True))
        return 3
    print("T4_G2_SINGLETON_OWNER=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
