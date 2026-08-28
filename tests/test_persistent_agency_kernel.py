from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.agency_state import (
    AGENCY_PATCH_SCHEMA,
    AgencyState,
    AgencyStatePatch,
    DeferredIntent,
    Interest,
    OpenLoop,
)
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
    PROJECTION_SCHEMA,
    TABLE_NAME,
    PersistentAgencyIntegrationError,
    PersistentAgencyStore,
    build_checkpoint,
    rehydrate_agency_state,
    rehydrate_candidate_goal_state,
)
from frankenstein2.persistent_pulse import PulseInput, classify_pulse_eligibility
from frankenstein2.wake_hold import (
    ABSTAIN_NOT_OBSERVED,
    OP_EQUALS,
    WAKE_ANY,
    HoldCheckpoint,
    WakeCondition,
    WakeObservation,
    evaluate_wake,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


class PersistentAgencyKernelTests(unittest.TestCase):
    def resolution(self, db_path: Path):
        return resolve_unifieddb_path(
            env={"FRANKENSTEIN2_DB": str(db_path)},
            home=db_path.parent,
            pointer_path=db_path.parent / "no-pointer.txt",
        )

    def agency(self, generation: int = 0) -> AgencyState:
        return AgencyState.create(
            state_id="agency-main",
            generation=generation,
            interests=(Interest("interest-1", "inspect explicit state", 600_000, ("owner:explicit",)),),
            open_loops=(
                OpenLoop(
                    "loop-1",
                    "wait for explicit receipt",
                    "WAITING",
                    700_000,
                    ("owner:explicit",),
                ),
            ),
            deferred_intents=(
                DeferredIntent(
                    "intent-1",
                    "revisit after explicit receipt",
                    500_000,
                    "wake:receipt",
                    ("owner:explicit",),
                ),
            ),
        )

    def goal(self, generation: int = 0) -> GoalState:
        return GoalState.create(
            state_id="goal-main",
            generation=generation,
            goals=(
                GoalRecord.candidate(
                    goal_id="goal-1",
                    summary="explicitly supplied goal",
                    priority_ppm=800_000,
                    provenance_refs=("owner:goal",),
                ),
            ),
        )

    def pulse(self, agency: AgencyState, *, digest: str | None = None):
        pulse_input = PulseInput.create(
            pulse_id=f"pulse-{agency.generation}",
            observation_id=f"observation-{agency.generation}",
            state_id=agency.state_id,
            generation=agency.generation,
            state_digest_sha256=agency.sha256() if digest is None else digest,
            act_candidate_ref="candidate:act",
            ask_candidate_ref="candidate:ask",
            wait_condition_ref="wake:receipt",
            hold_reason_ref="hold:explicit",
            delegate_candidate_ref="candidate:delegate",
        )
        return classify_pulse_eligibility(pulse_input)

    def hold_and_wake(self, agency: AgencyState, *, digest: str | None = None, observed: bool = False):
        checkpoint = HoldCheckpoint.create(
            hold_id=f"hold-{agency.generation}",
            state_id=agency.state_id,
            generation=agency.generation,
            state_sha256=agency.sha256() if digest is None else digest,
            wake_policy=WAKE_ANY,
            wake_conditions=(
                WakeCondition(
                    "wake-1",
                    "receipt.status",
                    OP_EQUALS,
                    ("condition:explicit",),
                    "done",
                ),
            ),
            provenance_refs=("hold:explicit",),
        )
        observations = (
            (WakeObservation("wake-observation-1", "receipt.status", "done", ("receipt:explicit",)),)
            if observed
            else ()
        )
        evaluation = evaluate_wake(
            checkpoint,
            evaluation_id=f"wake-evaluation-{agency.generation}",
            observed_state_id=agency.state_id,
            observed_generation=agency.generation,
            observed_state_sha256=agency.sha256(),
            observations=observations,
        )
        return checkpoint, evaluation

    def checkpoint(self, *, integration_generation: int = 0, parent: str | None = None):
        agency = self.agency()
        goal = self.goal()
        hold, wake = self.hold_and_wake(agency)
        return build_checkpoint(
            kernel_id="kernel-main",
            integration_generation=integration_generation,
            parent_checkpoint_sha256=parent,
            agency_state=agency,
            goal_state=goal,
            pulse_decision=self.pulse(agency),
            hold_checkpoint=hold,
            wake_evaluation=wake,
            provenance_refs=("integration:test", "owner:explicit"),
        )

    def subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        src = str(Path(__file__).resolve().parents[1] / "src")
        current = env.get("PYTHONPATH")
        env["PYTHONPATH"] = src if not current else src + os.pathsep + current
        return env

    def test_checkpoint_binds_all_component_identities_without_granting_authority(self):
        checkpoint = self.checkpoint()
        agency = json.loads(checkpoint.agency_state_json)
        goal = json.loads(checkpoint.goal_state_json)
        pulse = json.loads(checkpoint.pulse_decision_json)
        wake = json.loads(checkpoint.wake_evaluation_json)

        self.assertEqual(agency["state_id"], pulse["state_id"])
        self.assertEqual(checkpoint.agency_state_sha256, pulse["state_digest_sha256"])
        self.assertEqual(goal["goals"][0]["status"], GOAL_CANDIDATE)
        self.assertEqual(wake["classification"], ABSTAIN_NOT_OBSERVED)
        self.assertFalse(wake["wake"])
        self.assertNotIn("effect", checkpoint.as_dict())
        self.assertNotIn("completion", checkpoint.as_dict())
        self.assertNotIn("selected_action", checkpoint.as_dict())

    def test_projection_content_and_integration_lineage_are_distinct(self):
        first = self.checkpoint()
        second = self.checkpoint(integration_generation=1, parent=first.sha256())
        first_fp = first.state_fingerprint()
        second_fp = second.state_fingerprint()
        self.assertEqual(first_fp.projection_schema, PROJECTION_SCHEMA)
        self.assertEqual(first_fp.projection_sha256, second_fp.projection_sha256)
        self.assertNotEqual(first_fp.identity_sha256, second_fp.identity_sha256)
        self.assertEqual(first.agency_state_sha256, second.agency_state_sha256)
        self.assertEqual(first.goal_state_sha256, second.goal_state_sha256)

    def test_cross_component_digest_mismatches_fail_closed(self):
        agency = self.agency()
        goal = self.goal()
        hold, wake = self.hold_and_wake(agency)
        with self.assertRaisesRegex(PersistentAgencyIntegrationError, "pulse/agency digest mismatch"):
            build_checkpoint(
                kernel_id="kernel-main",
                integration_generation=0,
                parent_checkpoint_sha256=None,
                agency_state=agency,
                goal_state=goal,
                pulse_decision=self.pulse(agency, digest="b" * 64),
                hold_checkpoint=hold,
                wake_evaluation=wake,
                provenance_refs=("integration:test",),
            )

        bad_hold, _ = self.hold_and_wake(agency, digest="b" * 64)
        with self.assertRaisesRegex(PersistentAgencyIntegrationError, "hold/agency digest mismatch"):
            build_checkpoint(
                kernel_id="kernel-main",
                integration_generation=0,
                parent_checkpoint_sha256=None,
                agency_state=agency,
                goal_state=goal,
                pulse_decision=self.pulse(agency),
                hold_checkpoint=bad_hold,
                provenance_refs=("integration:test",),
            )

    def test_unifieddb_store_is_append_only_idempotent_and_fail_closed_on_skips(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "unified.db"
            resolution = self.resolution(db_path)
            self.assertEqual(Path(resolution.path), db_path)
            self.assertTrue(resolution.source.startswith("EXPLICIT_"))
            store = PersistentAgencyStore(resolution)
            first = self.checkpoint()
            inserted = store.persist(first)
            self.assertEqual(inserted.status, "INSERTED")
            repeated = store.persist(first)
            self.assertEqual(repeated.status, "IDEMPOTENT_ALREADY_PRESENT")
            self.assertEqual(store.load_latest("kernel-main").sha256(), first.sha256())

            db_identity = fingerprint_unifieddb(db_path)
            self.assertTrue(db_identity.exists)
            self.assertEqual(db_identity.status, "SQLITE3_REGULAR_FILE")

            skipped = self.checkpoint(integration_generation=2, parent=first.sha256())
            with self.assertRaisesRegex(PersistentAgencyIntegrationError, "stale or skipped"):
                store.persist(skipped)

    def test_persisted_payload_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "unified.db"
            store = PersistentAgencyStore(self.resolution(db_path))
            checkpoint = self.checkpoint()
            store.persist(checkpoint)
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    f"UPDATE {TABLE_NAME} SET payload_json=? WHERE kernel_id=? AND integration_generation=0",
                    (checkpoint.canonical_json().replace("explicitly supplied goal", "tampered goal"), "kernel-main"),
                )
            with self.assertRaises(PersistentAgencyIntegrationError):
                store.load_latest("kernel-main")

    def test_real_subprocess_restart_can_replay_candidate_state_and_persist_next_tick(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "unified.db"
            store = PersistentAgencyStore(self.resolution(db_path))
            first = self.checkpoint()
            store.persist(first)

            script = r'''
import json
from pathlib import Path
import sys
from frankenstein2.agency_state import AGENCY_PATCH_SCHEMA, AgencyStatePatch, Interest
from frankenstein2.goal_lifecycle import GOAL_ACTIVE, GOAL_PATCH_SCHEMA, GoalStatePatch, GoalStatusChange
from frankenstein2.persistent_agency_kernel import PersistentAgencyStore, build_checkpoint, rehydrate_agency_state, rehydrate_candidate_goal_state
from frankenstein2.persistent_pulse import PulseInput, classify_pulse_eligibility
from frankenstein2.wake_hold import OP_EQUALS, WAKE_ANY, HoldCheckpoint, WakeCondition, WakeObservation, evaluate_wake
from state.unifieddb_identity import resolve_unifieddb_path

db = Path(sys.argv[1])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=db.parent, pointer_path=db.parent / "no-pointer.txt")
store = PersistentAgencyStore(resolution)
prior = store.load_latest("kernel-main")
agency0 = rehydrate_agency_state(prior)
goal0 = rehydrate_candidate_goal_state(prior)

agency_patch = AgencyStatePatch(
    schema=AGENCY_PATCH_SCHEMA,
    transition_id="agency-tick-1",
    expected_state_id=agency0.state_id,
    expected_generation=agency0.generation,
    expected_state_sha256=agency0.sha256(),
    next_generation=agency0.generation + 1,
    transition_refs=("integration:restart",),
    upsert_interests=(Interest("interest-2", "explicit next tick", 650000, ("restart:explicit",)),),
)
agency1, agency_receipt = agency0.apply(agency_patch)

goal_change = GoalStatusChange(
    goal_id="goal-1",
    expected_status="CANDIDATE",
    next_status=GOAL_ACTIVE,
    evidence_refs=("evidence:explicit-adoption",),
    adoption_authority_ref="caller-adoption:restart-test",
)
goal_patch = GoalStatePatch(
    schema=GOAL_PATCH_SCHEMA,
    transition_id="goal-tick-1",
    expected_state_id=goal0.state_id,
    expected_generation=goal0.generation,
    expected_state_sha256=goal0.sha256(),
    next_generation=goal0.generation + 1,
    transition_refs=("integration:restart",),
    status_changes=(goal_change,),
)
goal1, goal_receipt = goal0.apply(goal_patch)

pulse_input = PulseInput.create(
    pulse_id="pulse-1",
    observation_id="observation-1",
    state_id=agency1.state_id,
    generation=agency1.generation,
    state_digest_sha256=agency1.sha256(),
    ask_candidate_ref="goal:goal-1",
    wait_condition_ref="wake:receipt",
    hold_reason_ref="hold:explicit",
)
pulse = classify_pulse_eligibility(pulse_input)
hold = HoldCheckpoint.create(
    hold_id="hold-1",
    state_id=agency1.state_id,
    generation=agency1.generation,
    state_sha256=agency1.sha256(),
    wake_policy=WAKE_ANY,
    wake_conditions=(WakeCondition("wake-1", "receipt.status", OP_EQUALS, ("condition:explicit",), "done"),),
    provenance_refs=("hold:explicit",),
)
wake = evaluate_wake(
    hold,
    evaluation_id="wake-evaluation-1",
    observed_state_id=agency1.state_id,
    observed_generation=agency1.generation,
    observed_state_sha256=agency1.sha256(),
    observations=(WakeObservation("wake-observation-1", "receipt.status", "done", ("receipt:explicit",)),),
)
next_checkpoint = build_checkpoint(
    kernel_id="kernel-main",
    integration_generation=prior.integration_generation + 1,
    parent_checkpoint_sha256=prior.sha256(),
    agency_state=agency1,
    goal_state=goal1,
    pulse_decision=pulse,
    hold_checkpoint=hold,
    wake_evaluation=wake,
    provenance_refs=("integration:restart", agency_receipt.sha256(), goal_receipt.sha256()),
)
receipt = store.persist(next_checkpoint)
print(json.dumps({"sha": next_checkpoint.sha256(), "generation": next_checkpoint.integration_generation, "status": receipt.status}, sort_keys=True))
'''
            result = subprocess.run(
                [sys.executable, "-c", script, str(db_path)],
                check=True,
                capture_output=True,
                text=True,
                env=self.subprocess_env(),
            )
            child = json.loads(result.stdout.strip())
            self.assertEqual(child["generation"], 1)
            self.assertEqual(child["status"], "INSERTED")

            latest = store.load_latest("kernel-main")
            self.assertEqual(latest.integration_generation, 1)
            self.assertEqual(latest.parent_checkpoint_sha256, first.sha256())
            self.assertEqual(latest.sha256(), child["sha"])
            self.assertEqual(json.loads(latest.goal_state_json)["goals"][0]["status"], GOAL_ACTIVE)
            self.assertEqual(rehydrate_agency_state(latest).generation, 1)
            with self.assertRaisesRegex(
                PersistentAgencyIntegrationError,
                "NONCANDIDATE_GOAL_REHYDRATION_REQUIRES_SEPARATE_CONTRACT",
            ):
                rehydrate_candidate_goal_state(latest)

            replay_script = r'''
from pathlib import Path
import sys
from frankenstein2.persistent_agency_kernel import PersistentAgencyStore
from state.unifieddb_identity import resolve_unifieddb_path

db = Path(sys.argv[1])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=db.parent, pointer_path=db.parent / "no-pointer.txt")
print(PersistentAgencyStore(resolution).load_latest("kernel-main").sha256())
'''
            replay = subprocess.run(
                [sys.executable, "-c", replay_script, str(db_path)],
                check=True,
                capture_output=True,
                text=True,
                env=self.subprocess_env(),
            )
            self.assertEqual(replay.stdout.strip(), latest.sha256())


if __name__ == "__main__":
    unittest.main(verbosity=2)
