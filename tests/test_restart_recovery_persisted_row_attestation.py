#!/usr/bin/env python3
"""Repository-hosted regressions for WP901 G4 persisted-row load attestation."""
from __future__ import annotations

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
    PersistentAgencyError,
    advance_checkpoint,
)
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
)
from frankenstein2.restart_recovery_persisted_row_attestation import (
    RestartPersistedRowAttestationError,
    load_checkpoint_with_attestation,
    plan_restart_continuation_from_persisted_row,
    store_authority_receipt_ref,
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


class RestartRecoveryPersistedRowAttestationTests(unittest.TestCase):
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
                "CREATE TABLE f2_test_bootstrap(id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env["FRANKENSTEIN2_DB"] = str(self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    @staticmethod
    def make_sources():
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
        causal = CausalIdentity(
            session_id="session-wp901-g4",
            agent_id="agent-wp901-g4",
            task_id="task-wp901-g4",
            turn_id="turn-wp901-g4",
            causal_id="causal-wp901-g4",
            generation=current_checkpoint.generation + 1,
            parent_causal_id="causal-wp901-g4-parent",
        )
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
        next_checkpoint = advance_checkpoint(
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
            next_checkpoint=next_checkpoint,
            provenance_refs=(causal_ref, "test:wp901:g4:whole-loop"),
        )
        evidence = PersistedRestartEvidence(
            evidence_id="restart-evidence-wp901-g4",
            source_checkpoint_id=next_checkpoint.checkpoint_id,
            source_checkpoint_generation=next_checkpoint.generation,
            source_checkpoint_sha256=next_checkpoint.sha256(),
            whole_loop_seal_id=seal.seal_id,
            whole_loop_seal_sha256=seal.sha256(),
            outcome_status=outcome.status,
            outcome_sha256=outcome.sha256(),
            unfinished_work_refs=("work:alpha", "work:beta"),
            completed_work_refs=("work:done",),
            effect_attempt_refs=(),
            provenance_refs=(causal_ref, "receipt:wp900", "receipt:wp206"),
        )
        return current_checkpoint, causal, next_checkpoint, seal, outcome, evidence

    def persist_sources(self):
        current, causal, checkpoint, seal, outcome, evidence = self.make_sources()
        store = self.open_store()
        try:
            store.initialize_schema()
            store.write_checkpoint(current)
            store.write_checkpoint(checkpoint)
            authority_receipt = store.authority_receipt_sha256
        finally:
            store.close()
        return causal, checkpoint, seal, outcome, evidence, authority_receipt

    @staticmethod
    def authority_for_store(store: CanonicalPersistentAgencyStore) -> UnifiedDBAuthorityRef:
        return UnifiedDBAuthorityRef(
            receipt_ref=store_authority_receipt_ref(store),
            canonical_source="src/frankenstein2/persistent_agency_kernel.py",
            fingerprint_schema=store.fingerprint.schema,
        )

    def test_fresh_connection_load_is_attested_before_g3_restart_plan(self) -> None:
        causal, expected_checkpoint, seal, outcome, evidence, writer_receipt = (
            self.persist_sources()
        )
        store = self.open_store()
        try:
            self.assertEqual(store.authority_receipt_sha256, writer_receipt)
            authority = self.authority_for_store(store)
            plan, attestation = plan_restart_continuation_from_persisted_row(
                store,
                expected_checkpoint.checkpoint_id,
                evidence,
                plan_id="restart-plan-wp901-g4",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority,
                whole_loop_seal=seal,
                outcome=outcome,
            )
            self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
            self.assertEqual(plan.reason_code, "EXPLICIT_UNFINISHED_EVIDENCE")
            self.assertEqual(plan.continuation_refs, ("work:alpha", "work:beta"))
            self.assertEqual(attestation.checkpoint_id, expected_checkpoint.checkpoint_id)
            self.assertEqual(attestation.checkpoint_generation, expected_checkpoint.generation)
            self.assertEqual(attestation.checkpoint_sha256, expected_checkpoint.sha256())
            self.assertEqual(attestation.canonical_db_path, str(self.db.resolve()))
            self.assertEqual(attestation.db_device, self.db.stat().st_dev)
            self.assertEqual(attestation.db_inode, self.db.stat().st_ino)
            self.assertEqual(
                attestation.unifieddb_authority_receipt_sha256,
                writer_receipt,
            )
            raw = attestation.as_dict()
            self.assertTrue(raw["persisted_row_consumed"])
            self.assertTrue(raw["sqlite_snapshot_bound"])
            self.assertEqual(raw["truth_authority"], "NONE")
            self.assertEqual(raw["persistence_authority"], "NONE")
            self.assertEqual(raw["effect_authority"], "NONE")
            self.assertFalse(raw["target_host_execution_observed"])
        finally:
            store.close()

    def test_tampered_checkpoint_json_is_rejected_by_wp206_loader(self) -> None:
        _, checkpoint, _, _, _, _ = self.persist_sources()
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                "SELECT checkpoint_json FROM f2_persistent_agency_checkpoints WHERE checkpoint_id=?",
                (checkpoint.checkpoint_id,),
            ).fetchone()
            payload = json.loads(row[0])
            payload["provenance_refs"] = ["tampered:after-persist"]
            connection.execute(
                "UPDATE f2_persistent_agency_checkpoints SET checkpoint_json=? WHERE checkpoint_id=?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")), checkpoint.checkpoint_id),
            )
            connection.commit()
        finally:
            connection.close()
        store = self.open_store()
        try:
            with self.assertRaisesRegex(PersistentAgencyError, "CHECKPOINT_DIGEST_MISMATCH"):
                load_checkpoint_with_attestation(
                    store,
                    checkpoint.checkpoint_id,
                    unifieddb_authority=self.authority_for_store(store),
                )
        finally:
            store.close()

    def test_tampered_stored_authority_receipt_is_rejected_by_wp206_loader(self) -> None:
        _, checkpoint, _, _, _, _ = self.persist_sources()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE f2_persistent_agency_checkpoints SET unifieddb_authority_receipt_sha256=? WHERE checkpoint_id=?",
                ("0" * 64, checkpoint.checkpoint_id),
            )
            connection.commit()
        finally:
            connection.close()
        store = self.open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH",
            ):
                load_checkpoint_with_attestation(
                    store,
                    checkpoint.checkpoint_id,
                    unifieddb_authority=self.authority_for_store(store),
                )
        finally:
            store.close()

    def test_tampered_stored_db_identity_is_rejected_by_wp206_loader(self) -> None:
        _, checkpoint, _, _, _, _ = self.persist_sources()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE f2_persistent_agency_checkpoints SET db_inode=db_inode+1 WHERE checkpoint_id=?",
                (checkpoint.checkpoint_id,),
            )
            connection.commit()
        finally:
            connection.close()
        store = self.open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "CHECKPOINT_DB_FILE_IDENTITY_DRIFT",
            ):
                load_checkpoint_with_attestation(
                    store,
                    checkpoint.checkpoint_id,
                    unifieddb_authority=self.authority_for_store(store),
                )
        finally:
            store.close()

    def test_wrong_caller_authority_ref_fails_before_row_consumption(self) -> None:
        _, checkpoint, _, _, _, _ = self.persist_sources()
        store = self.open_store()
        try:
            wrong = UnifiedDBAuthorityRef(
                receipt_ref="f2:wp206-bound-file-authority-sha256:" + "0" * 64,
                canonical_source="src/frankenstein2/persistent_agency_kernel.py",
                fingerprint_schema=store.fingerprint.schema,
            )
            with self.assertRaisesRegex(
                RestartPersistedRowAttestationError,
                "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
            ):
                load_checkpoint_with_attestation(
                    store,
                    checkpoint.checkpoint_id,
                    unifieddb_authority=wrong,
                )
        finally:
            store.close()

    def test_substituted_persisted_checkpoint_id_fails_in_g3_binding(self) -> None:
        causal, _checkpoint, seal, outcome, evidence, _ = self.persist_sources()
        current_checkpoint = fixture_components()[0]
        store = self.open_store()
        try:
            with self.assertRaisesRegex(
                Exception,
                "SOURCE_AUTH_CAUSAL_CHECKPOINT_GENERATION_MISMATCH|SOURCE_AUTH_EVIDENCE_CHECKPOINT_ID_MISMATCH",
            ):
                plan_restart_continuation_from_persisted_row(
                    store,
                    current_checkpoint.checkpoint_id,
                    evidence,
                    plan_id="substituted-row",
                    expected_evidence_sha256=evidence.sha256(),
                    causal_identity=causal,
                    unifieddb_authority=self.authority_for_store(store),
                    whole_loop_seal=seal,
                    outcome=outcome,
                )
        finally:
            store.close()

    def test_existing_caller_transaction_is_not_consumed_or_committed(self) -> None:
        _, checkpoint, _, _, _, _ = self.persist_sources()
        store = self.open_store()
        try:
            store.connection.execute("BEGIN")
            with self.assertRaisesRegex(
                RestartPersistedRowAttestationError,
                "PERSISTED_ROW_CALLER_TRANSACTION_ALREADY_OPEN",
            ):
                load_checkpoint_with_attestation(
                    store,
                    checkpoint.checkpoint_id,
                    unifieddb_authority=self.authority_for_store(store),
                )
            self.assertTrue(store.connection.in_transaction)
            store.connection.rollback()
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
