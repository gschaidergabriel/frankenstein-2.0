#!/usr/bin/env python3
"""Fail-closed singleton guard for the promotion-bearing G2 S2 runtime.

Only two historical workflow runs are exempted, and only while they remain
queued with the exact run identity recorded by the Trigger-4 falsifier at
95e9517b8f9e5f5b49e6036296169ce645e8f944. Both subjects were invalidated by
required later G2 repairs before any executed steps were observed.

This file is execution-control logic, not runtime/product evidence. It never
mints credit and it never exempts an in-progress predecessor.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Iterable

WORKFLOW = "t4-g2-pipewire-monitor-cancel.yml"
INVALIDATION_CLASS = "RUNTIME_PROBE_INVALIDATED_BY_REQUIRED_REPAIR"

# Exact, bounded exceptions. Different SHA/event/status => not exempt.
INVALIDATED_QUEUED_PREDECESSORS: dict[str, dict[str, Any]] = {
    "33554493024": {
        "head_sha": "6cf8ba3a6ae013083b1013e782d3fff2a373d75b",
        "event": "push",
        "executed_steps_observed": False,
        "classification": INVALIDATION_CLASS,
        "evidence_commit": "95e9517b8f9e5f5b49e6036296169ce645e8f944",
    },
    "33554578605": {
        "head_sha": "eea45dbd94738adb92c4d439ea90534062044239",
        "event": "push",
        "executed_steps_observed": False,
        "classification": INVALIDATION_CLASS,
        "evidence_commit": "95e9517b8f9e5f5b49e6036296169ce645e8f944",
    },
}


def is_exact_invalidated_queued_predecessor(run: dict[str, Any]) -> bool:
    """Return True only for an exact, never-started invalidated queued subject."""
    run_id = str(run.get("id"))
    evidence = INVALIDATED_QUEUED_PREDECESSORS.get(run_id)
    if evidence is None:
        return False
    if run.get("status") != "queued":
        return False
    if run.get("head_sha") != evidence["head_sha"]:
        return False
    if run.get("event") != evidence["event"]:
        return False
    if evidence.get("executed_steps_observed") is not False:
        return False
    return evidence.get("classification") == INVALIDATION_CLASS


def blocking_owners(
    runs: Iterable[dict[str, Any]], current_run_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition nonterminal runs into blockers and exact historical exemptions."""
    blockers: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("id"))
        status = run.get("status")
        if run_id == current_run_id:
            continue
        if status not in {"queued", "in_progress"}:
            continue
        compact = {
            "id": run_id,
            "status": status,
            "head_sha": run.get("head_sha"),
            "event": run.get("event"),
        }
        if is_exact_invalidated_queued_predecessor(run):
            compact["classification"] = INVALIDATION_CLASS
            exempted.append(compact)
            continue
        blockers.append(compact)
    return blockers, exempted


def fetch_nonterminal_runs(repo: str, token: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for status in ("queued", "in_progress"):
        url = (
            f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW}/runs"
            f"?status={status}&per_page=100"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.load(response)
        workflow_runs = payload.get("workflow_runs")
        if not isinstance(workflow_runs, list):
            raise RuntimeError("GitHub workflow_runs payload is not a list")
        runs.extend(workflow_runs)
    return runs


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    current_run_id = str(os.environ["GITHUB_RUN_ID"])
    token = os.environ["GH_TOKEN"]
    runs = fetch_nonterminal_runs(repo, token)
    blockers, exempted = blocking_owners(runs, current_run_id)
    if exempted:
        print("T4_G2_INVALIDATED_QUEUED_EXEMPTIONS=" + json.dumps(exempted, sort_keys=True))
    if blockers:
        print("T4_G2_DUPLICATE_NONTERMINAL_OWNER=" + json.dumps(blockers, sort_keys=True))
        return 3
    print("T4_G2_SINGLETON_OWNER=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
