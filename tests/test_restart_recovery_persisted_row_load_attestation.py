#!/usr/bin/env python3
"""Repository regressions for F2-WP-901 G4 persisted-row/load attestation."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.causal_authority_binding import (
    CausalAuthorityBindingError,
    UnifiedDBAuthorityRef,
)
from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    advance_checkpoint,
)
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
)
from frankenstein2.restart_recovery_persisted_row_load_attestation import (
    CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
    CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
    RestartPersistedRowLoadAttestationError,
    load_checkpoint_with_persisted_row_receipt,
    plan_restart_continuation_from_persisted_row_load,
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


REPO_ROOT = Path(__file__).parents[1]


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def authority(
    *,
    receipt_ref: str = CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
    canonical_source: str = CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
):
    return UnifiedDBAuthorityRef(
        receipt_ref=receipt_ref,
        canonical_source=canonical_source,
        fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
    )


def identity(causal_id: str, generation: int) -> CausalIdentity:
    return CausalIdentity(
        session_id="session-wp901-g4-row-load",
        agent_id="agent-wp901-g4-row-load",
        task_id="task-wp901-g4-row-load",
        turn_id="turn-wp901-g4-row-load",
        causal_id=causal_id,
        generation=generation,
        parent_causal_id="causal-wp901-g4-row-load-parent",
    )


class RestartRecoveryPersistedRowLoadAttestationTests(unittest.TestCase):
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

    def sources(self, *, causal_id: str = "causal-wp901-g4-row-load"):
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
            outcome_id="outcome-wp901-g4-row-load",
            status=NO_EFFECT,
            provenance_refs=(causal_ref, "test:wp901:g4:row-load:outcome"),
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
            checkpoint_id="checkpoint-wp901-g4-row-load",
            pulse_id="pulse-wp901-g4-row-load",
            observation_id="observation-wp901-g4-row-load",
            provenance_refs=tuple(sorted(set(reentry_refs) | {causal_ref})),
        )
        whole_loop_seal = seal_whole_persistent_loop(
            seal_id="whole-loop-seal-wp901-g4-row-load",
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
            provenance_refs=(causal_ref, "test:wp901:g4:row-load:whole-loop"),
        )
        evidence = PersistedRestartEvidence(
            evidence_id="restart-evidence-wp901-g4-row-load",
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
        return causal, current_checkpoint, next_checkpoint, whole_loop_seal, outcome, evidence

    def plan(self):
        causal, current, checkpoint, seal, outcome, evidence = self.sources()
        plan = plan_restart_continuation_from_persisted_row_load(
            evidence,
            plan_id="restart-plan-wp901-g4-row-load",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=authority(),
            store=self.store,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return plan, causal, current, checkpoint, seal, outcome, evidence

    def test_exact_persisted_row_load_preserves_g3_g2_semantics(self) -> None:
        plan, _, _, checkpoint, _, _, _ = self.plan()
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.reason_code, "EXPLICIT_UNFINISHED_EVIDENCE")
        self.assertEqual(plan.continuation_refs, ("work:alpha", "work:beta"))
        self.assertEqual(plan.candidate_generation, checkpoint.generation + 1)

    def test_canonical_authority_constants_match_accepted_wp100_receipt(self) -> None:
        receipt_path = REPO_ROOT / CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["workpackage_id"], "F2-WP-100")
        self.assertEqual(payload["status"], "ACCEPTED_AT_SCOPE")
        self.assertEqual(
            payload["canonical_source"]["path"], CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE
        )
        self.assertEqual(
            payload["canonical_source"]["fingerprint_schema"],
            "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )

    def test_receipt_binds_exact_row_predecessor_and_zero_credit_boundary(self) -> None:
        _, current, checkpoint, _, _, evidence = self.sources()
        loaded, receipt = load_checkpoint_with_persisted_row_receipt(
            evidence,
            store=self.store,
            unifieddb_authority=authority(),
        )
        self.assertEqual(loaded.sha256(), checkpoint.sha256())
        raw = receipt.as_dict()
        self.assertEqual(raw["checkpoint_id"], checkpoint.checkpoint_id)
        self.assertEqual(raw["previous_checkpoint_id"], current.checkpoint_id)
        self.assertEqual(raw["predecessor_checkpoint_sha256"], current.sha256())
        self.assertEqual(raw["canonical_db_path"], self.store.canonical_db_path)
        self.assertEqual(raw["db_device"], self.store.db_device)
        self.assertEqual(raw["db_inode"], self.store.db_inode)
        self.assertEqual(
            raw["store_authority_receipt_sha256"], self.store.authority_receipt_sha256
        )
        self.assertEqual(
            raw["unifieddb_authority_receipt_ref"],
            CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
        )
        self.assertEqual(
            raw["unifieddb_authority_canonical_source"],
            CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
        )
        self.assertEqual(len(raw["row_evidence_sha256"]), 64)
        self.assertEqual(len(raw["checkpoint_json_sha256"]), 64)
        self.assertEqual(raw["row_evidence_digest_bound"], True)
        self.assertEqual(raw["unifieddb_component_authority_bound"], True)
        self.assertEqual(raw["wp900_persisted_seal_load"], "NOT_CLAIMED")
        self.assertEqual(raw["same_inode_live_database_drift"], "NOT_CLAIMED")
        self.assertFalse(raw["target_host_execution_observed"])
        self.assertEqual(raw["runtime_credit"], 0)
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "EXISTING_UNIFIEDDB_ONLY")

    def test_hostile_store_subclass_is_rejected_before_loader_dispatch(self) -> None:
        _, _, checkpoint, _, _, evidence = self.sources()

        class HostileStore(CanonicalPersistentAgencyStore):
            calls = 0

            def load_checkpoint(self, checkpoint_id):
                type(self).calls += 1
                return checkpoint

        hostile = object.__new__(HostileStore)
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_CANONICAL_STORE_EXACT_TYPE_REQUIRED",
        ):
            load_checkpoint_with_persisted_row_receipt(
                evidence,
                store=hostile,
                unifieddb_authority=authority(),
            )
        self.assertEqual(HostileStore.calls, 0)

    def test_persisted_checkpoint_json_tamper_fails_inside_canonical_wp206_loader(self) -> None:
        _, _, checkpoint, _, _, evidence = self.sources()
        self.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET checkpoint_json='{}' WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id,),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(Exception, "CHECKPOINT_DIGEST_MISMATCH"):
            load_checkpoint_with_persisted_row_receipt(
                evidence,
                store=self.store,
                unifieddb_authority=authority(),
            )

    def test_persisted_authority_receipt_drift_fails_inside_canonical_wp206_loader(self) -> None:
        _, _, checkpoint, _, _, evidence = self.sources()
        self.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET unifieddb_authority_receipt_sha256=? WHERE checkpoint_id=?",
            ("f" * 64, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(Exception, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"):
            load_checkpoint_with_persisted_row_receipt(
                evidence,
                store=self.store,
                unifieddb_authority=authority(),
            )

    def test_persisted_previous_checkpoint_column_mismatch_fails_closed(self) -> None:
        _, _, checkpoint, _, _, evidence = self.sources()
        self.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET previous_checkpoint_id=? WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_PREVIOUS_CHECKPOINT_ID_MISMATCH",
        ):
            load_checkpoint_with_persisted_row_receipt(
                evidence,
                store=self.store,
                unifieddb_authority=authority(),
            )

    def test_unifieddb_authority_type_rejects_wrong_fingerprint_schema_before_g4(self) -> None:
        with self.assertRaisesRegex(
            CausalAuthorityBindingError,
            "unsupported UnifiedDB fingerprint schema",
        ):
            UnifiedDBAuthorityRef(
                receipt_ref=CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
                canonical_source=CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
                fingerprint_schema="wrong-schema",
            )

    def test_foreign_unifieddb_authority_receipt_ref_fails_closed(self) -> None:
        _, _, _, _, _, evidence = self.sources()
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_RECEIPT_REF_MISMATCH",
        ):
            load_checkpoint_with_persisted_row_receipt(
                evidence,
                store=self.store,
                unifieddb_authority=authority(receipt_ref="receipt:foreign-unifieddb"),
            )

    def test_foreign_unifieddb_authority_canonical_source_fails_closed(self) -> None:
        _, _, _, _, _, evidence = self.sources()
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_CANONICAL_SOURCE_MISMATCH",
        ):
            load_checkpoint_with_persisted_row_receipt(
                evidence,
                store=self.store,
                unifieddb_authority=authority(canonical_source="src/state/foreign_db.py"),
            )

    def test_forged_seal_predecessor_id_is_rejected_after_real_row_load(self) -> None:
        causal, _, _, seal, outcome, evidence = self.sources()
        forged_seal = replace(
            seal,
            current_checkpoint_id="checkpoint-from-different-direct-lineage",
            current_checkpoint_sha256=sha("checkpoint-from-different-direct-lineage"),
        )
        forged_evidence = replace(
            evidence,
            whole_loop_seal_sha256=forged_seal.sha256(),
        )
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_SEAL_PREDECESSOR_ID_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row_load(
                forged_evidence,
                plan_id="forged-predecessor-id",
                expected_evidence_sha256=forged_evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=forged_seal,
                outcome=outcome,
            )

    def test_forged_seal_predecessor_digest_is_rejected_after_real_row_load(self) -> None:
        causal, _, _, seal, outcome, evidence = self.sources()
        forged_seal = replace(
            seal,
            current_checkpoint_sha256=sha("forged-predecessor-digest"),
        )
        forged_evidence = replace(
            evidence,
            whole_loop_seal_sha256=forged_seal.sha256(),
        )
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_SEAL_PREDECESSOR_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row_load(
                forged_evidence,
                plan_id="forged-predecessor-digest",
                expected_evidence_sha256=forged_evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=forged_seal,
                outcome=outcome,
            )

    def test_g3_mixed_causal_lineage_rejection_still_applies_after_row_load(self) -> None:
        _, _, checkpoint, seal, outcome, evidence = self.sources()
        foreign = identity("causal-episode-B", checkpoint.generation)
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_DOWNSTREAM_SOURCE_BINDING_REJECTED:SOURCE_AUTH_CAUSAL_REF_MISSING:checkpoint",
        ):
            plan_restart_continuation_from_persisted_row_load(
                evidence,
                plan_id="mixed-lineage-after-row-load",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=foreign,
                unifieddb_authority=authority(),
                store=self.store,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_expected_evidence_digest_mismatch_fails_after_exact_row_load(self) -> None:
        causal, _, _, seal, outcome, evidence = self.sources()
        with self.assertRaisesRegex(
            RestartPersistedRowLoadAttestationError,
            "PERSISTED_ROW_EXPECTED_EVIDENCE_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row_load(
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
