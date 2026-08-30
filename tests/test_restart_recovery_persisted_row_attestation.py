#!/usr/bin/env python3
"""Repository-hosted regressions for F2-WP-901 generation 4 persisted-row binding."""
from __future__ import annotations

from dataclasses import replace
import hashlib
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
from frankenstein2.restart_recovery_persisted_row_attestation import (
    RestartPersistedRowAttestationError,
    attest_persisted_restart_checkpoint,
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


def identity(causal_id: str, generation: int) -> CausalIdentity:
    return CausalIdentity(
        session_id="session-wp901-g4",
        agent_id="agent-wp901-g4",
        task_id="task-wp901-g4",
        turn_id="turn-wp901-g4",
        causal_id=causal_id,
        generation=generation,
        parent_causal_id="causal-wp901-g4-parent",
    )


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
                "CREATE TABLE IF NOT EXISTS f2_test_bootstrap(id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()
        self.env = os.environ.copy()
        self.env["FRANKENSTEIN2_DB"] = str(self.db)
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        self.store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        self.store.initialize_schema()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def sources(self, *, causal_id: str = "causal-wp901-g4"):
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

        causal = identity(causal_id, current_checkpoint.generation + 1)
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
        plan = plan_restart_continuation_from_persisted_row(
            evidence,
            plan_id="restart-plan-wp901-g4",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=authority(),
            store=self.store,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return plan, causal, checkpoint, seal, outcome, evidence

    def test_canonical_g4_ingress_loads_row_then_preserves_g3_g2_semantics(self) -> None:
        plan, _, checkpoint, _, _, _ = self.plan()
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.reason_code, "EXPLICIT_UNFINISHED_EVIDENCE")
        self.assertEqual(plan.continuation_refs, ("work:alpha", "work:beta"))
        self.assertEqual(plan.candidate_generation, checkpoint.generation + 1)

    def test_attestation_binds_exact_store_file_identity_without_new_authority(self) -> None:
        _, checkpoint, _, _, evidence = self.sources()
        loaded, receipt = attest_persisted_restart_checkpoint(
            evidence,
            store=self.store,
        )
        self.assertEqual(loaded.sha256(), checkpoint.sha256())
        raw = receipt.as_dict()
        self.assertEqual(
            raw["persisted_checkpoint_row_attestation"],
            "OBSERVED_VIA_CANONICAL_STORE_LOAD",
        )
        self.assertEqual(raw["canonical_db_path"], self.store.canonical_db_path)
        self.assertEqual(raw["db_device"], self.store.db_device)
        self.assertEqual(raw["db_inode"], self.store.db_inode)
        self.assertEqual(
            raw["bound_file_authority_receipt_sha256"],
            self.store.authority_receipt_sha256,
        )
        self.assertEqual(raw["wp900_persisted_seal_attestation"], "NOT_OBSERVED")
        self.assertEqual(raw["target_host_runtime_credit"], 0)
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "EXISTING_UNIFIEDDB_ONLY")

    def test_pr683_shape_cannot_self_attest_nonexistent_checkpoint_at_g4_ingress(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        forged = replace(
            evidence,
            source_checkpoint_id="checkpoint-never-loaded-from-wp206",
            source_checkpoint_sha256=sha("checkpoint-never-loaded-from-wp206"),
        )
        with self.assertRaisesRegex(
            RestartPersistedRowAttestationError,
            "PERSISTED_RESTART_CHECKPOINT_LOAD_REJECTED:CHECKPOINT_NOT_FOUND",
        ):
            plan_restart_continuation_from_persisted_row(
                forged,
                plan_id="forged-row-plan",
                expected_evidence_sha256=forged.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )
        self.assertEqual(checkpoint.checkpoint_id, "checkpoint-wp901-g4")

    def test_same_row_id_with_forged_evidence_digest_fails_against_loaded_checkpoint(self) -> None:
        causal, _, seal, outcome, evidence = self.sources()
        forged = replace(evidence, source_checkpoint_sha256=sha("forged-checkpoint"))
        with self.assertRaisesRegex(
            RestartPersistedRowAttestationError,
            "PERSISTED_RESTART_CHECKPOINT_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                forged,
                plan_id="forged-digest-plan",
                expected_evidence_sha256=forged.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_persisted_checkpoint_payload_tamper_fails_inside_wp206_load_boundary(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        self.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET checkpoint_json='{}' WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id,),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(
            RestartPersistedRowAttestationError,
            "PERSISTED_RESTART_CHECKPOINT_LOAD_REJECTED:CHECKPOINT_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                evidence,
                plan_id="tampered-row-plan",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_persisted_authority_receipt_drift_fails_inside_wp206_load_boundary(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        self.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET unifieddb_authority_receipt_sha256=? WHERE checkpoint_id=?",
            ("f" * 64, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(
            RestartPersistedRowAttestationError,
            "PERSISTED_RESTART_CHECKPOINT_LOAD_REJECTED:CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                evidence,
                plan_id="authority-drift-plan",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_g3_mixed_causal_lineage_rejection_still_applies_after_row_load(self) -> None:
        _, checkpoint, seal, outcome, evidence = self.sources()
        foreign = identity("causal-episode-B", checkpoint.generation)
        with self.assertRaisesRegex(
            RestartPersistedRowAttestationError,
            "PERSISTED_ROW_DOWNSTREAM_SOURCE_BINDING_REJECTED:SOURCE_AUTH_CAUSAL_REF_MISSING:checkpoint",
        ):
            plan_restart_continuation_from_persisted_row(
                evidence,
                plan_id="mixed-lineage-after-load",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=foreign,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_expected_evidence_digest_mismatch_fails_after_exact_row_attestation(self) -> None:
        causal, _, seal, outcome, evidence = self.sources()
        with self.assertRaisesRegex(
            RestartPersistedRowAttestationError,
            "PERSISTED_ROW_EXPECTED_EVIDENCE_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                evidence,
                plan_id="bad-expected-evidence",
                expected_evidence_sha256=sha("wrong-evidence"),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
