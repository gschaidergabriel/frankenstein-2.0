#!/usr/bin/env python3
"""REVIEW_ONLY regressions for the WP901 store-bound authority successor candidate."""
from __future__ import annotations

from inspect import signature
import unittest

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED
from frankenstein2.restart_recovery_store_bound_authority import (
    STORE_BOUND_RECEIPT_PREFIX,
    plan_restart_continuation_from_store_bound_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class StoreBoundAuthorityIngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PersistedRowLoadAttestationTests(
            methodName="test_real_wp206_row_load_is_attested_before_g3_g2_planning"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def plan(self, fixture: PersistedRowLoadAttestationTests | None = None):
        fixture = self.fixture if fixture is None else fixture
        causal, checkpoint, seal, outcome, evidence = fixture.sources()
        result = plan_restart_continuation_from_store_bound_persisted_row(
            fixture.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-store-bound",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return result, causal, checkpoint, seal, outcome, evidence

    def test_successor_ingress_has_no_caller_authority_parameter(self) -> None:
        params = signature(
            plan_restart_continuation_from_store_bound_persisted_row
        ).parameters
        self.assertNotIn("unifieddb_authority", params)

    def test_downstream_authority_is_derived_from_attested_store_identity(self) -> None:
        result, _, checkpoint, _, _, _ = self.plan()
        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        authority = result.store_bound_unifieddb_authority
        attestation = result.load_attestation
        self.assertEqual(
            authority.receipt_ref,
            STORE_BOUND_RECEIPT_PREFIX
            + attestation.unifieddb_authority_receipt_sha256,
        )
        self.assertEqual(authority.canonical_source, attestation.canonical_db_path)
        self.assertEqual(
            authority.fingerprint_schema,
            self.fixture.store.fingerprint.schema,
        )
        raw = result.as_dict()
        self.assertEqual(
            raw["caller_supplied_unifieddb_authority"],
            "NOT_ACCEPTED_BY_SUCCESSOR_INGRESS",
        )
        self.assertEqual(raw["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(raw["runtime_credit"], 0)
        self.assertFalse(raw["whole_system_acceptance"])

    def test_pr719_foreign_authority_injection_is_not_part_of_successor_abi(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.fixture.sources()
        foreign = UnifiedDBAuthorityRef(
            receipt_ref="receipt:unifieddb:foreign-store",
            canonical_source="src/foreign/unifieddb_authority.py",
            fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )
        with self.assertRaises(TypeError):
            plan_restart_continuation_from_store_bound_persisted_row(
                self.fixture.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=evidence,
                plan_id="restart-plan-wp901-foreign-injection",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=foreign,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_two_real_stores_derive_distinct_authority_refs(self) -> None:
        first, *_ = self.plan()
        second_fixture = PersistedRowLoadAttestationTests(
            methodName="test_real_wp206_row_load_is_attested_before_g3_g2_planning"
        )
        second_fixture.setUp()
        self.addCleanup(second_fixture.tearDown)
        second, *_ = self.plan(second_fixture)

        self.assertNotEqual(
            first.load_attestation.canonical_db_path,
            second.load_attestation.canonical_db_path,
        )
        self.assertNotEqual(
            first.store_bound_unifieddb_authority.receipt_ref,
            second.store_bound_unifieddb_authority.receipt_ref,
        )
        self.assertNotEqual(
            first.store_bound_unifieddb_authority.canonical_source,
            second.store_bound_unifieddb_authority.canonical_source,
        )


if __name__ == "__main__":
    unittest.main()
