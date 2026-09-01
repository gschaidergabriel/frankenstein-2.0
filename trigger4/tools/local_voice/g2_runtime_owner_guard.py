#!/usr/bin/env python3
"""Evidence-bound singleton owner guard for the Trigger-4 G2 runtime workflow.

Only explicitly recorded, queued, never-executed predecessor subjects that were
invalidated by required repairs may be exempted. In-progress runs are never
exempted. This is coordination plumbing, not runtime/product evidence.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

WORKFLOW = "t4-g2-pipewire-monitor-cancel.yml"
INVALIDATED_QUEUED_SUBJECTS = {
    "33554493024": "6cf8ba3a6ae013083b1013e782d3fff2a373d75b",
    "33554578605": "eea45dbd94738adb92c4d439ea90534062044239",
}
INVALIDATION_EVIDENCE_REF = (
    "research/local_voice/falsifiers/"
    "2026-09-02_T4_G2_STALE_QUEUE_SINGLETON_DEADLOCK_GPT56SOL.json"
)


def classify_run(run: dict[str, Any], current_run_id: str) -> str:
    run_id = str(run.get("id"))
    status = run.get("status")
    head_sha = run.get("head_sha")
    if run_id == current_run_id:
        return "SELF"
    if (
        status == "queued"
        and INVALIDATED_QUEUED_SUBJECTS.get(run_id) == head_sha
    ):
        return "EXEMPT_EXACT_INVALIDATED_QUEUED_PREDECESSOR"
    if status in {"queued", "in_progress"}:
        return "BLOCKING_NONTERMINAL_OWNER"
    return "NONBLOCKING_TERMINAL_OR_OTHER"


def query_runs(repo: str, token: str) -> list[dict[str, Any]]:
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
        for run in payload.get("workflow_runs", []):
            if isinstance(run, dict):
                runs.append(run)
    return runs


def evaluate_runs(runs: list[dict[str, Any]], current_run_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocking: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    for run in runs:
        classification = classify_run(run, current_run_id)
        summary = {
            "id": str(run.get("id")),
            "status": run.get("status"),
            "head_sha": run.get("head_sha"),
            "event": run.get("event"),
            "classification": classification,
        }
        if classification == "BLOCKING_NONTERMINAL_OWNER":
            blocking.append(summary)
        elif classification == "EXEMPT_EXACT_INVALIDATED_QUEUED_PREDECESSOR":
            summary["invalidation_evidence_ref"] = INVALIDATION_EVIDENCE_REF
            exempted.append(summary)
    return blocking, exempted


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    current_run_id = str(os.environ["GITHUB_RUN_ID"])
    token = os.environ["GH_TOKEN"]
    blocking, exempted = evaluate_runs(query_runs(repo, token), current_run_id)
    if exempted:
        print("T4_G2_EXACT_INVALIDATED_QUEUED_EXEMPTIONS=" + json.dumps(exempted, sort_keys=True))
    if blocking:
        print("T4_G2_DUPLICATE_NONTERMINAL_OWNER=" + json.dumps(blocking, sort_keys=True))
        return 3
    print("T4_G2_SINGLETON_OWNER=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
