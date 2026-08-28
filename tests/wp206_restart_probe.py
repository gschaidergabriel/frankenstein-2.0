#!/usr/bin/env python3
"""Fresh-process probe for F2-WP-206 hosted-CI restart evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from frankenstein2.agency_state import AgencyState, Interest, OpenLoop
from frankenstein2.goal_lifecycle import (
    GOAL_ACTIVE,
    GOAL_CANDIDATE,
    GOAL_PATCH_SCHEMA,
    GoalRecord,
    GoalState,
    GoalStatePatch,
    GoalStatusChange,
)
from frankenstein2.persistent_agency_kernel import (
    CHANGE_POLICY_PROJECTION,
    CanonicalPersistentAgencyStore,
    GoalReplayEnvelope,
    advance_checkpoint,
    create_checkpoint,
    evaluate_checkpoint,
    selected_fingerprint_change,
)
from frankenstein2.state_fingerprint import identity_changed, projection_changed
from frankenstein2.wake_hold import OP_EQUALS, WAKE_ANY, WakeCondition
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


def _resolution():
    pointer = os.environ.get("F2_POINTER_PATH")
    kwargs = {
        "env": os.environ,
        "home": Path(os.environ["HOME"]),
    }
    if pointer:
        kwargs["pointer_path"] = Path(pointer)
    return resolve_unifieddb_path(**kwargs)


def _fixture_checkpoint():
    agency = AgencyState.create(
        state_id="agency-state-1",
        generation=3,
        interests=(
            Interest(
                interest_id="interest-restart",
                label="Preserve explicit restart state",
                salience_ppm=800_000,
                provenance_refs=("owner:fixture",),
            ),
        ),
        open_loops=(
            OpenLoop(
                loop_id="loop-restart",
                summary="Verify fresh-process replay",
                state="WAITING",
                priority_ppm=900_000,
                provenance_refs=("test:wp206",),
            ),
        ),
    )
    genesis = GoalState.create(
        state_id="goal-state-1",
        generation=0,
        goals=(
            GoalRecord.candidate(
                goal_id="goal-persist",
                summary="Survive a real process restart",
                priority_ppm=900_000,
                provenance_refs=("owner:explicit-goal",),
            ),
        ),
    )
    patch = GoalStatePatch(
        schema=GOAL_PATCH_SCHEMA,
        transition_id="goal-transition-adopt-1",
        expected_state_id=genesis.state_id,
        expected_generation=genesis.generation,
        expected_state_sha256=genesis.sha256(),
        next_generation=1,
        transition_refs=("evidence:explicit-adoption",),
        status_changes=(
            GoalStatusChange(
                goal_id="goal-persist",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=("evidence:explicit-adoption",),
                adoption_authority_ref="caller:test-owner",
            ),
        ),
    )
    replay = GoalReplayEnvelope.create(genesis=genesis, patches=(patch,))
    condition = WakeCondition(
        condition_id="wake-ready",
        observation_key="ready",
        operator=OP_EQUALS,
        expected_value="yes",
        provenance_refs=("condition:explicit",),
    )
    return create_checkpoint(
        checkpoint_id="checkpoint-0",
        previous_checkpoint_id=None,
        kernel_state_id="persistent-agency-kernel-1",
        generation=0,
        change_policy=CHANGE_POLICY_PROJECTION,
        agency_state=agency,
        goal_replay=replay,
        hold_id="hold-1",
        wake_policy=WAKE_ANY,
        wake_conditions=(condition,),
        hold_provenance_refs=("hold:explicit",),
        pulse_id="pulse-0",
        observation_id="observation-none-0",
        act_candidate_ref="candidate:act-explicit",
        wait_condition_ref="wait:explicit",
        hold_reason_ref="hold:explicit",
        delegate_candidate_ref="candidate:delegate-explicit",
        provenance_refs=("checkpoint:fixture", "owner:explicit"),
    )


def _open_store():
    resolution = _resolution()
    fingerprint = fingerprint_unifieddb(resolution.path)
    store = CanonicalPersistentAgencyStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
    )
    return resolution, fingerprint, store


def write_fixture():
    resolution, fingerprint, store = _open_store()
    mode = store.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    store.connection.execute("PRAGMA wal_autocheckpoint=0")
    store.initialize_schema()
    checkpoint = _fixture_checkpoint()
    digest = store.write_checkpoint(checkpoint)
    wal = Path(str(Path(resolution.path).resolve()) + "-wal")
    payload = {
        "mode": "write",
        "resolved_path": str(Path(resolution.path).resolve()),
        "db_authority_receipt": fingerprint.receipt_sha256(),
        "checkpoint_sha256": digest,
        "journal_mode": str(mode).upper(),
        "wal_exists_before_exit": wal.exists(),
        "wal_size_before_exit": wal.stat().st_size if wal.exists() else 0,
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stdout.flush()
    os._exit(0)


def read_fixture(*, advance: bool):
    resolution, fingerprint, store = _open_store()
    try:
        checkpoint = store.load_checkpoint("checkpoint-0")
        evaluation = evaluate_checkpoint(
            checkpoint,
            evaluation_id="evaluation-after-restart",
            observations=(),
        )
        live_goal = checkpoint.live_goal_state
        result = {
            "mode": "read_advance" if advance else "read",
            "resolved_path": str(Path(resolution.path).resolve()),
            "fingerprint_wal_present": fingerprint.wal_present,
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_sha256": checkpoint.sha256(),
            "checkpoint_generation": checkpoint.generation,
            "goal_statuses": [goal.status for goal in live_goal.goals],
            "agency_sha256": checkpoint.agency_state.sha256(),
            "wake_classification": evaluation.wake_evaluation.classification,
            "wake": evaluation.wake_evaluation.wake,
            "pulse_eligible_actions": list(evaluation.pulse_decision.eligible_actions),
            "pulse_suppressed_by_hold": list(
                evaluation.pulse_decision.suppressed_by_hold
            ),
        }
        if advance:
            next_checkpoint = advance_checkpoint(
                checkpoint,
                checkpoint_id="checkpoint-1",
                pulse_id="pulse-1",
                observation_id="observation-none-1",
            )
            result.update(
                {
                    "projection_changed": projection_changed(
                        checkpoint.state_fingerprint,
                        next_checkpoint.state_fingerprint,
                    ),
                    "identity_changed": identity_changed(
                        checkpoint.state_fingerprint,
                        next_checkpoint.state_fingerprint,
                    ),
                    "selected_change": selected_fingerprint_change(
                        checkpoint, next_checkpoint
                    ),
                    "next_checkpoint_id": next_checkpoint.checkpoint_id,
                    "next_checkpoint_sha256": store.write_checkpoint(next_checkpoint),
                    "next_checkpoint_generation": next_checkpoint.generation,
                }
            )
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        sys.stdout.flush()
    finally:
        store.close()


def read_checkpoint_one():
    resolution, fingerprint, store = _open_store()
    try:
        checkpoint = store.load_checkpoint("checkpoint-1")
        result = {
            "mode": "read_checkpoint_one",
            "resolved_path": str(Path(resolution.path).resolve()),
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_sha256": checkpoint.sha256(),
            "checkpoint_generation": checkpoint.generation,
            "goal_statuses": [goal.status for goal in checkpoint.live_goal_state.goals],
            "db_authority_receipt": fingerprint.receipt_sha256(),
        }
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        sys.stdout.flush()
    finally:
        store.close()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: wp206_restart_probe.py write|read|read_advance|read_one")
    mode = sys.argv[1]
    if mode == "write":
        write_fixture()
        return 0
    if mode == "read":
        read_fixture(advance=False)
        return 0
    if mode == "read_advance":
        read_fixture(advance=True)
        return 0
    if mode == "read_one":
        read_checkpoint_one()
        return 0
    raise SystemExit(f"unknown mode: {mode}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}:{exc}\n")
        sys.stderr.flush()
        raise
