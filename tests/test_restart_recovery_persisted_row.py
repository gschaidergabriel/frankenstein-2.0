#!/usr/bin/env python3
"""Repository-hosted regressions for F2-WP-901 G4 persisted-row loading."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    advance_checkpoint,
)
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
)
from frankenstein2.restart_recovery_persisted_row import (
    ROW_ATTESTATION_CLASSIFICATION,
    RestartPersistedRowError,
    load_checkpoint_with_row_attestation,
    plan_restart_continuation_from_persisted_row,
)
from frankenstein2.restart_recovery_source_authentication import causal_identity_ref
from frankenstein2.whole_persistent_loop import (
    LoopOutcomeEvidence,
    NO_EFFECT,
    required_reentry_refs,
    seal_whole_persistent_loop,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def authority() -> UnifiedDBAuthorityRef:
    return UnifiedDBAuthorityRef(
        receipt_ref="receipt:unifieddb:accepted-component",
        canonical_source="src/frankenstein2/unifieddb_authority.py",
        fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
    )


def identity(generation: int) -> CausalIdentity:
    return CausalIdentity(
        session_id="session-wp901-g4",
        agent_id="agent-wp901-g4",
        task_id="task-wp901-g4",
        turn_id="turn-wp901-g4",
        causal_id="causal-wp901-g4",
        generation=generation,
        parent_causal_id="causal-wp901-g4-parent",
    )


class RestartRecoveryPersistedRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "CREATE TABLE f2_test_bootstrap(id INTEGER PRIMARY KEY, note TEXT)"
            )
            connection.commit()
        finally:
            connection.close()

        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["FRANKENSTEIN2_DB"] = str(self.db)
        resolution = resolve_unifieddb_path(env=env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        self.store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        self.store.initialize_schema()

        (
            current_checkpoint,
            frame,
            contract,
            grid_plan,
            gwt_seal,
            gwt_evidence,
            decision,
            _fixture_outcome,
            _fixture_next_checkpoint,
        ) = fixture_components()
        causal = identity(current_checkpoint.generation + 1)
        causal_ref = causal_identity_ref(causal)
        outcome = LoopOutcomeEvidence(
            outcome_id="outcome-wp901-g4",
            status=NO_EFFECT,
            provenance_refs=(causal_ref, "test:wp901:g4:outcome"),
        )
        reentry_refs = required_reentry_refs(
            current_checkpoint=current_checkpoint,
            frame=frame,
            contract=contract,
            plan=grid_plan,
            gwt_seal=gwt_seal,
            decision=decision,
            outcome=outcome,
        )
        checkpoint = advance_checkpoint(
            current_checkpoint,
            checkpoint_id="checkpoint-wp901-g4",
            pulse_id="pulse-wp901-g4",
            observation_id="observation-wp901-g4",
            provenance_refs=tuple(sorted(set(reentry_refs) | {causal_ref})),
        )
        seal = seal_whole_persistent_loop(
            seal_id="whole-loop-seal-wp901-g4",
            generation=current_checkpoint.generation,
            current_checkpoint=current_checkpoint,
            frame=frame,
            contract=contract,
            plan=grid_plan,
            gwt_seal=gwt_seal,
            gwt_evidence=gwt_evidence,
            decision=decision,
            outcome=outcome,
            next_checkpoint=checkpoint,
            provenance_refs=(causal_ref, "test:wp901:g4:whole-loop"),
        )
        evidence = PersistedRestartEvidence(
            evidence_id="restart-evidence-wp901-g4",
            source_checkpoint_id=checkpoint.checkpoint_id,
            source_checkpoint_generation=checkpoint.generation,
            source_checkpoint_sha256=checkpoint.sha256(),
            whole_loop_seal_id=seal.seal_id,
            whole_loop_seal_sha256=seal.sha256(),
            outcome_status=outcome.status,
            outcome_sha256=outcome.sha256(),
            unfinished_work_refs=("work:alpha", "work:beta"),
            completed_work_refs=("work:done",),
            effect_attempt_refs=(),
            provenance_refs=(causal_ref, "receipt:wp900", "receipt:wp206"),
        )

        self.store.write_checkpoint(current_checkpoint)
        self.store.write_checkpoint(checkpoint)
        self.current_checkpoint = current_checkpoint
        self.checkpoint = checkpoint
        self.causal = causal
        self.outcome = outcome
        self.seal = seal
        self.evidence = evidence

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def plan(self):
        return plan_restart_continuation_from_persisted_row(
            self.evidence,
            store=self.store,
            checkpoint_id=self.checkpoint.checkpoint_id,
            expected_checkpoint_sha256=self.checkpoint.sha256(),
            expected_store_authority_receipt_sha256=self.store.authority_receipt_sha256,
            plan_id="restart-plan-wp901-g4",
            expected_evidence_sha256=self.evidence.sha256(),
            causal_identity=self.causal,
            unifieddb_authority=authority(),
            whole_loop_seal=self.seal,
            outcome=self.outcome,
        )

    def test_canonical_store_row_load_feeds_g3_and_preserves_g2_semantics(self) -> None:
        result = self.plan()
        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(result.plan.reason_code, "EXPLICIT_UNFINISHED_EVIDENCE")
        self.assertEqual(result.plan.continuation_refs, ("work:alpha", "work:beta"))
        self.assertEqual(result.attestation.checkpoint_id, self.checkpoint.checkpoint_id)
        self.assertEqual(result.attestation.checkpoint_sha256, self.checkpoint.sha256())
        self.assertEqual(
            result.attestation.store_authority_receipt_sha256,
            self.store.authority_receipt_sha256,
        )
        self.assertEqual(result.attestation.classification, ROW_ATTESTATION_CLASSIFICATION)
        payload = result.attestation.as_dict()
        self.assertEqual(
            payload["persisted_row_attestation"],
            "OBSERVED_BY_CANONICAL_STORE_LOAD",
        )
        self.assertEqual(payload["same_inode_global_db_drift_closure"], "NOT_CLAIMED")
        self.assertEqual(payload["truth_authority"], "NONE")
        self.assertEqual(payload["persistence_authority"], "NONE")
        self.assertEqual(payload["runtime_credit"], 0)
        self.assertFalse(payload["whole_system_acceptance"])

    def test_expected_checkpoint_digest_mismatch_fails_after_real_load(self) -> None:
        with self.assertRaisesRegex(
            RestartPersistedRowError,
            "PERSISTED_ROW_CHECKPOINT_DIGEST_MISMATCH",
        ):
            load_checkpoint_with_row_attestation(
                self.store,
                checkpoint_id=self.checkpoint.checkpoint_id,
                expected_checkpoint_sha256=sha("wrong-checkpoint"),
                expected_store_authority_receipt_sha256=self.store.authority_receipt_sha256,
            )

    def test_expected_store_authority_receipt_mismatch_fails_before_planning(self) -> None:
        with self.assertRaisesRegex(
            RestartPersistedRowError,
            "PERSISTED_ROW_STORE_AUTHORITY_RECEIPT_MISMATCH",
        ):
            load_checkpoint_with_row_attestation(
                self.store,
                checkpoint_id=self.checkpoint.checkpoint_id,
                expected_checkpoint_sha256=self.checkpoint.sha256(),
                expected_store_authority_receipt_sha256=sha("wrong-store-authority"),
            )

    def test_tampered_persisted_checkpoint_json_is_rejected_by_wp206_loader(self) -> None:
        row = self.store.connection.execute(
            "SELECT checkpoint_json FROM f2_persistent_agency_checkpoints WHERE checkpoint_id=?",
            (self.checkpoint.checkpoint_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        payload = json.loads(row[0])
        payload["kernel_state_id"] = "tampered-kernel-state"
        self.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET checkpoint_json=? WHERE checkpoint_id=?",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                self.checkpoint.checkpoint_id,
            ),
        )
        self.store.connection.commit()

        with self.assertRaisesRegex(
            RestartPersistedRowError,
            "PERSISTED_ROW_LOAD_REJECTED:CHECKPOINT_DIGEST_MISMATCH",
        ):
            self.plan()

    def test_forged_recovery_evidence_cannot_substitute_for_loaded_checkpoint(self) -> None:
        forged = replace(
            self.evidence,
            source_checkpoint_id="caller-constructed-checkpoint",
            source_checkpoint_sha256=sha("caller-constructed-checkpoint"),
        )
        with self.assertRaisesRegex(
            RestartPersistedRowError,
            "SOURCE_AUTH_EVIDENCE_CHECKPOINT_ID_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                forged,
                store=self.store,
                checkpoint_id=self.checkpoint.checkpoint_id,
                expected_checkpoint_sha256=self.checkpoint.sha256(),
                expected_store_authority_receipt_sha256=self.store.authority_receipt_sha256,
                plan_id="forged-restart-plan-wp901-g4",
                expected_evidence_sha256=forged.sha256(),
                causal_identity=self.causal,
                unifieddb_authority=authority(),
                whole_loop_seal=self.seal,
                outcome=self.outcome,
            )

    def test_unrelated_same_inode_db_mutation_does_not_overclaim_global_drift_closure(self) -> None:
        self.store.connection.execute(
            "INSERT INTO f2_test_bootstrap(note) VALUES(?)",
            ("unrelated same-inode mutation",),
        )
        self.store.connection.commit()
        result = self.plan()
        self.assertEqual(
            result.attestation.as_dict()["same_inode_global_db_drift_closure"],
            "NOT_CLAIMED",
        )


if __name__ == "__main__":
    unittest.main()
