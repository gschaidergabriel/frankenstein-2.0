#!/usr/bin/env python3
"""Repository-hosted regressions for F2-WP-901 generation 4 row/load attestation."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    advance_checkpoint,
)
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
)
from frankenstein2.restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationError,
    attest_persisted_checkpoint_load,
    plan_restart_continuation_from_persisted_row,
)
from frankenstein2.restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    causal_identity_ref,
)
from frankenstein2.whole_persistent_loop import (
    LoopOutcomeEvidence,
    NO_EFFECT,
    required_reentry_refs,
    seal_whole_persistent_loop,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


class PersistedRowLoadAttestationTests(unittest.TestCase):
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
                "CREATE TABLE f2_wp901_g4_bootstrap(id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()
        env = {"FRANKENSTEIN2_DB": str(self.db)}
        resolution = resolve_unifieddb_path(env=env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        self.store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        self.store.initialize_schema()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    @staticmethod
    def authority() -> UnifiedDBAuthorityRef:
        return UnifiedDBAuthorityRef(
            receipt_ref="receipt:unifieddb:accepted-component",
            canonical_source="src/frankenstein2/unifieddb_authority.py",
            fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )

    @staticmethod
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

    def sources(self):
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

        causal = self.identity(current_checkpoint.generation + 1)
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
        whole_loop_seal = seal_whole_persistent_loop(
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
            whole_loop_seal_id=whole_loop_seal.seal_id,
            whole_loop_seal_sha256=whole_loop_seal.sha256(),
            outcome_status=outcome.status,
            outcome_sha256=outcome.sha256(),
            unfinished_work_refs=("work:alpha", "work:beta"),
            completed_work_refs=("work:done",),
            effect_attempt_refs=(),
            provenance_refs=(causal_ref, "receipt:wp900", "receipt:wp206"),
        )
        self.store.write_checkpoint(current_checkpoint)
        self.store.write_checkpoint(next_checkpoint)
        return causal, next_checkpoint, whole_loop_seal, outcome, evidence

    def plan(self):
        causal, checkpoint, seal, outcome, evidence = self.sources()
        result = plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-g4",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=self.authority(),
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return result, causal, checkpoint, seal, outcome, evidence

    def test_real_wp206_row_load_is_attested_before_g3_g2_planning(self) -> None:
        result, _, checkpoint, _, _, _ = self.plan()
        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(result.plan.reason_code, "EXPLICIT_UNFINISHED_EVIDENCE")
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        self.assertEqual(result.plan.source_checkpoint_sha256, checkpoint.sha256())
        attestation = result.load_attestation
        self.assertEqual(attestation.checkpoint_id, checkpoint.checkpoint_id)
        self.assertEqual(attestation.checkpoint_generation, checkpoint.generation)
        self.assertEqual(attestation.checkpoint_sha256, checkpoint.sha256())
        self.assertEqual(attestation.canonical_db_path, str(self.db.resolve()))
        self.assertEqual(attestation.db_device, self.store.db_device)
        self.assertEqual(attestation.db_inode, self.store.db_inode)
        self.assertEqual(
            attestation.unifieddb_authority_receipt_sha256,
            self.store.authority_receipt_sha256,
        )
        self.assertEqual(len(attestation.row_evidence_sha256), 64)

    def test_foreign_caller_authority_ref_is_accepted_despite_store_attestation(self) -> None:
        """REVIEW_ONLY falsifier: G4 does not bind the G3 authority ref to the loaded store."""
        causal, checkpoint, seal, outcome, evidence = self.sources()
        foreign_authority = UnifiedDBAuthorityRef(
            receipt_ref="receipt:unifieddb:foreign-component",
            canonical_source="foreign/not-the-loaded-unifieddb-authority.py",
            fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )
        self.assertNotEqual(foreign_authority.receipt_ref, self.authority().receipt_ref)
        self.assertNotEqual(foreign_authority.canonical_source, self.authority().canonical_source)

        result = plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-g4-foreign-authority",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=foreign_authority,
            whole_loop_seal=seal,
            outcome=outcome,
        )

        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        self.assertEqual(
            result.load_attestation.unifieddb_authority_receipt_sha256,
            self.store.authority_receipt_sha256,
        )

    def test_attestation_explicitly_denies_freshness_target_runtime_and_effect_credit(self) -> None:
        result, *_ = self.plan()
        raw = result.load_attestation.as_dict()
        self.assertEqual(raw["persisted_row_attestation"], "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE")
        self.assertEqual(raw["transaction_snapshot_binding"], "OBSERVED")
        self.assertEqual(raw["freshness_attestation"], "NOT_OBSERVED")
        self.assertEqual(raw["same_inode_live_drift_closure"], "NOT_OBSERVED")
        self.assertEqual(raw["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["runtime_credit"], 0)
        self.assertFalse(raw["whole_system_acceptance"])

    def test_tampered_persisted_checkpoint_json_fails_in_existing_wp206_loader(self) -> None:
        _, checkpoint, _, _, _ = self.sources()
        row = self.store.connection.execute(
            f"SELECT checkpoint_json FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["kernel_state_id"] = "tampered-kernel"
        self.store.connection.execute(
            f"UPDATE {CHECKPOINT_TABLE} SET checkpoint_json=? WHERE checkpoint_id=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), checkpoint.checkpoint_id),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(Exception, "CHECKPOINT_DIGEST_MISMATCH"):
            attest_persisted_checkpoint_load(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
            )

    def test_wrong_persisted_authority_receipt_fails_before_attestation(self) -> None:
        _, checkpoint, _, _, _ = self.sources()
        self.store.connection.execute(
            f"UPDATE {CHECKPOINT_TABLE} SET unifieddb_authority_receipt_sha256=? WHERE checkpoint_id=?",
            ("0" * 64, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(Exception, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"):
            attest_persisted_checkpoint_load(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
            )

    def test_substituted_checkpoint_id_cannot_mint_load_evidence(self) -> None:
        self.sources()
        with self.assertRaisesRegex(Exception, "CHECKPOINT_NOT_FOUND"):
            attest_persisted_checkpoint_load(
                self.store,
                checkpoint_id="checkpoint-not-persisted",
            )

    def test_caller_transaction_fails_closed_instead_of_weakening_snapshot_boundary(self) -> None:
        _, checkpoint, _, _, _ = self.sources()
        self.store.connection.execute("BEGIN")
        try:
            with self.assertRaisesRegex(
                PersistedRowLoadAttestationError,
                "PERSISTED_ROW_LOAD_REQUIRES_CLEAN_TRANSACTION_BOUNDARY",
            ):
                attest_persisted_checkpoint_load(
                    self.store,
                    checkpoint_id=checkpoint.checkpoint_id,
                )
        finally:
            self.store.connection.rollback()

    def test_loaded_checkpoint_still_must_pass_all_g3_causal_source_invariants(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        wrong_evidence = replace(
            evidence,
            source_checkpoint_sha256="f" * 64,
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_EVIDENCE_CHECKPOINT_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=wrong_evidence,
                plan_id="restart-plan-wp901-g4-wrong-evidence",
                expected_evidence_sha256=wrong_evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=self.authority(),
                whole_loop_seal=seal,
                outcome=outcome,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)