#!/usr/bin/env python3
"""Bounded F2-WP-719 fresh-turn successor falsifier.

Runs only the FRESH1-FRESH10 repository suite against the exact checkout. It does
not call providers, write canonical memory, execute effects, touch audio devices,
or mint target-runtime/whole-product credit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

# FRESH10 execution marker only; no semantic change.


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    src = str(repo / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_fresh_turn_successor.py",
        "-v",
    ]
    completed = subprocess.run(command, cwd=repo, env=env, check=False)
    receipt = {
        "schema": "F2_WP719_FRESH_TURN_SUCCESSOR_FALSIFIER/v1",
        "workpackage_id": "F2-WP-719",
        "probe_family": "FRESH1-FRESH10",
        "command": command,
        "returncode": completed.returncode,
        "repository_component_ci_credit": 0,
        "target_environment_component_runtime_credit": 0,
        "canonical_memory_write_credit": 0,
        "gwt_runtime_credit": 0,
        "jspace_runtime_credit": 0,
        "effect_credit": 0,
        "physical_audio_credit": 0,
        "training_credit": 0,
        "completion_credit": 0,
        "whole_system_acceptance": False,
        "classification": (
            "REPOSITORY_FALSIFIER_ONLY_NOT_TARGET_RUNTIME_MEMORY_GWT_EFFECT_AUDIO_OR_COMPLETION_AUTHORITY"
        ),
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
