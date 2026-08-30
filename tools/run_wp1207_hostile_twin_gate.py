#!/usr/bin/env python3
"""Execute the bounded WP1207 hostile-twin release cycle in one fresh scratch root.

This is an execution adapter, not an authority surface. Environment/target promotion must be
bound by an external runner receipt that identifies the actual host/sandbox and exact inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from frankenstein2.hostile_twin_release_executor import (  # noqa: E402
    FAIL_AFTER_EXTRACT,
    BoundReleaseCandidate,
    HostileTwinExecutionError,
    ScratchHostileTwin,
    request_for_install,
    request_for_rollback,
    request_for_update,
)

SCHEMA = "F2_WP1207_HOSTILE_TWIN_GATE_RECEIPT/v1"


def _fresh_root(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_dir():
            raise HostileTwinExecutionError("twin root must be absent or an empty plain directory")
        if any(path.iterdir()):
            raise HostileTwinExecutionError("twin root must be fresh/empty")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predecessor-bundle", required=True)
    parser.add_argument("--candidate-bundle", required=True)
    parser.add_argument("--twin-root", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    twin_root = Path(args.twin_root)
    _fresh_root(twin_root)
    state_path = Path(args.state_file)
    if state_path.is_symlink() or not state_path.is_file():
        raise HostileTwinExecutionError("state-file must be a regular non-symlink file")
    state = state_path.read_bytes()

    predecessor = BoundReleaseCandidate.from_bundle(args.predecessor_bundle)
    candidate = BoundReleaseCandidate.from_bundle(args.candidate_bundle)
    if predecessor.portable_release_digest == candidate.portable_release_digest:
        raise HostileTwinExecutionError("predecessor and candidate release identities must differ")

    receipts = []
    twin = ScratchHostileTwin(twin_root)
    receipts.append(twin.execute(
        request_for_install(attempt_id="wp1207-fresh-install", release=predecessor.release_identity),
        candidate=predecessor,
        canonical_state_bytes=state,
    ).as_dict())

    twin = ScratchHostileTwin(twin_root)
    g0 = twin.readback()
    if g0 is None:
        raise HostileTwinExecutionError("fresh install did not survive process re-entry")
    receipts.append(twin.execute(
        request_for_update(
            attempt_id="wp1207-candidate-injected-failure",
            release=candidate.release_identity,
            current=g0,
            injected_failure_stage=FAIL_AFTER_EXTRACT,
        ),
        candidate=candidate,
        canonical_state_bytes=state,
    ).as_dict())

    twin = ScratchHostileTwin(twin_root)
    after_failure = twin.readback()
    if after_failure != g0:
        raise HostileTwinExecutionError("injected update failure changed durable lineage")
    receipts.append(twin.execute(
        request_for_update(
            attempt_id="wp1207-candidate-update",
            release=candidate.release_identity,
            current=after_failure,
        ),
        candidate=candidate,
        canonical_state_bytes=state,
    ).as_dict())

    twin = ScratchHostileTwin(twin_root)
    g1 = twin.readback()
    if g1 is None or g1.active_release_digest != candidate.portable_release_digest:
        raise HostileTwinExecutionError("candidate update did not survive process re-entry")
    receipts.append(twin.execute(
        request_for_rollback(
            attempt_id="wp1207-predecessor-rollback",
            release=predecessor.release_identity,
            current=g1,
        ),
        candidate=predecessor,
        canonical_state_bytes=state,
    ).as_dict())

    twin = ScratchHostileTwin(twin_root)
    final = twin.readback()
    if final is None or final.active_release_digest != predecessor.portable_release_digest:
        raise HostileTwinExecutionError("rollback did not survive process re-entry")
    if final.state_sha256 != hashlib.sha256(state).hexdigest():
        raise HostileTwinExecutionError("rollback changed canonical state bytes")

    out = {
        "schema": SCHEMA,
        "predecessor": {
            "outer_bundle_sha256": predecessor.outer_sha256,
            "artifact_sha256": predecessor.release_identity.artifact_sha256,
            "manifest_sha256": predecessor.release_identity.manifest_sha256,
            "release_digest": predecessor.portable_release_digest,
        },
        "candidate": {
            "outer_bundle_sha256": candidate.outer_sha256,
            "artifact_sha256": candidate.release_identity.artifact_sha256,
            "manifest_sha256": candidate.release_identity.manifest_sha256,
            "release_digest": candidate.portable_release_digest,
        },
        "canonical_state_sha256": hashlib.sha256(state).hexdigest(),
        "operations": receipts,
        "process_reentry_readback": "PASS",
        "final_lineage": final.as_dict(),
        "execution_scope": "BOUNDED_FILESYSTEM_HOSTILE_TWIN_GATE_EXTERNAL_ENVIRONMENT_CLASSIFICATION_REQUIRED",
        "target_runtime_credit": 0,
        "physical_host_credit": 0,
        "effect_credit": 0,
        "completion_credit": 0,
        "whole_system_acceptance": False,
    }
    receipt_path = Path(args.receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "receipt": str(receipt_path),
        "predecessor_release_digest": predecessor.portable_release_digest,
        "candidate_release_digest": candidate.portable_release_digest,
        "outcomes": [item["outcome"] for item in receipts],
        "final_generation": final.generation,
        "target_runtime_credit": 0,
        "whole_system_acceptance": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
