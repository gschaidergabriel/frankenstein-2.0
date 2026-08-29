#!/usr/bin/env python3
"""Fail-closed regression suite for F2-WP-1207."""
from __future__ import annotations

import copy
import unittest

from frankenstein2.portable_release_transaction import (
    EVIDENCE_SCOPE,
    LINEAGE_SCHEMA,
    RELEASE_SCHEMA,
    REQUEST_SCHEMA,
    PortableReleaseTransactionError,
    ReleaseIdentity,
    build_transaction_plan,
    record_attempt,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def release(release_id: str, version: str, artifact: str, manifest: str) -> dict:
    return {
        "schema": RELEASE_SCHEMA,
        "release_id": release_id,
        "version": version,
        "artifact_sha256": artifact,
        "manifest_sha256": manifest,
    }


R1 = release("frankenstein-2.0-r1", "2.0.0-r1", A, B)
R2 = release("frankenstein-2.0-r2", "2.0.0-r2", C, D)
R1_DIGEST = ReleaseIdentity.from_mapping(R1).digest()
R2_DIGEST = ReleaseIdentity.from_mapping(R2).digest()


def lineage(*, predecessor: bool = True) -> dict:
    return {
        "schema": LINEAGE_SCHEMA,
        "generation": 7,
        "state_sha256": E,
        "active_release_digest": R2_DIGEST,
        "predecessor_generation": 6 if predecessor else None,
        "predecessor_state_sha256": F if predecessor else None,
        "predecessor_release_digest": R1_DIGEST if predecessor else None,
    }


def update_request() -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": "wp1207-update-001",
        "operation": "UPDATE",
        "target_release": copy.deepcopy(R1),
        "current_lineage": lineage(predecessor=False),
        "expected_generation": 7,
        "expected_state_sha256": E,
        "rollback_release": None,
        "injected_failure_stage": None,
    }


class PortableReleaseTransactionTests(unittest.TestCase):
    def test_fresh_install_plan_is_deterministic_and_scoped(self) -> None:
        raw = {
            "schema": REQUEST_SCHEMA,
            "attempt_id": "wp1207-install-001",
            "operation": "INSTALL",
            "target_release": copy.deepcopy(R1),
            "current_lineage": None,
            "expected_generation": None,
            "expected_state_sha256": None,
            "rollback_release": None,
            "injected_failure_stage": None,
        }
        left = build_transaction_plan(raw)
        right = build_transaction_plan(copy.deepcopy(raw))
        self.assertEqual(left.as_dict(), right.as_dict())
        self.assertEqual(left.digest(), right.digest())
        self.assertEqual(left.next_generation, 0)
        self.assertEqual(left.evidence_scope, EVIDENCE_SCOPE)
        self.assertIsNone(left.source_lineage_digest)

    def test_update_requires_exact_generation_and_state_digest(self) -> None:
        raw = update_request()
        plan = build_transaction_plan(raw)
        self.assertEqual(plan.source_generation, 7)
        self.assertEqual(plan.source_state_sha256, E)
        self.assertEqual(plan.next_generation, 8)

        bad_generation = copy.deepcopy(raw)
        bad_generation["expected_generation"] = 6
        with self.assertRaisesRegex(PortableReleaseTransactionError, "generation"):
            build_transaction_plan(bad_generation)

        bad_state = copy.deepcopy(raw)
        bad_state["expected_state_sha256"] = F
        with self.assertRaisesRegex(PortableReleaseTransactionError, "state digest"):
            build_transaction_plan(bad_state)

    def test_update_never_infers_missing_continuity(self) -> None:
        raw = update_request()
        raw["expected_generation"] = None
        raw["expected_state_sha256"] = None
        with self.assertRaisesRegex(PortableReleaseTransactionError, "requires exact"):
            build_transaction_plan(raw)

    def test_update_rejects_same_release_as_active(self) -> None:
        raw = update_request()
        raw["target_release"] = copy.deepcopy(R2)
        with self.assertRaisesRegex(PortableReleaseTransactionError, "must differ"):
            build_transaction_plan(raw)

    def test_rollback_binds_exact_predecessor_release_and_state(self) -> None:
        raw = {
            "schema": REQUEST_SCHEMA,
            "attempt_id": "wp1207-rollback-001",
            "operation": "ROLLBACK",
            "target_release": copy.deepcopy(R1),
            "current_lineage": lineage(predecessor=True),
            "expected_generation": 7,
            "expected_state_sha256": E,
            "rollback_release": copy.deepcopy(R1),
            "injected_failure_stage": None,
        }
        plan = build_transaction_plan(raw)
        self.assertEqual(plan.rollback_target_generation, 6)
        self.assertEqual(plan.rollback_target_state_sha256, F)
        self.assertEqual(plan.rollback_target_release_digest, R1_DIGEST)

        wrong = copy.deepcopy(raw)
        wrong["rollback_release"] = copy.deepcopy(R2)
        with self.assertRaisesRegex(PortableReleaseTransactionError, "exact predecessor"):
            build_transaction_plan(wrong)

    def test_rollback_without_predecessor_lineage_fails_closed(self) -> None:
        raw = {
            "schema": REQUEST_SCHEMA,
            "attempt_id": "wp1207-rollback-002",
            "operation": "ROLLBACK",
            "target_release": copy.deepcopy(R1),
            "current_lineage": lineage(predecessor=False),
            "expected_generation": 7,
            "expected_state_sha256": E,
            "rollback_release": copy.deepcopy(R1),
            "injected_failure_stage": None,
        }
        with self.assertRaisesRegex(PortableReleaseTransactionError, "exact predecessor"):
            build_transaction_plan(raw)

    def test_injected_failure_can_never_mint_success(self) -> None:
        raw = update_request()
        raw["injected_failure_stage"] = "after-state-copy-before-activation"
        plan = build_transaction_plan(raw)
        with self.assertRaisesRegex(PortableReleaseTransactionError, "synthetic SUCCEEDED"):
            record_attempt(
                plan,
                outcome="SUCCEEDED",
                observed_generation=8,
                observed_state_sha256=A,
            )

        receipt = record_attempt(
            plan,
            outcome="FAILED_NO_MUTATION",
            observed_generation=7,
            observed_state_sha256=E,
            failure_code="INJECTED_AFTER_STATE_COPY",
        )
        self.assertEqual(receipt.outcome, "FAILED_NO_MUTATION")
        self.assertEqual(receipt.evidence_scope, EVIDENCE_SCOPE)

    def test_rolled_back_receipt_requires_exact_pre_attempt_lineage(self) -> None:
        plan = build_transaction_plan(update_request())
        receipt = record_attempt(
            plan,
            outcome="ROLLED_BACK",
            observed_generation=7,
            observed_state_sha256=E,
            failure_code="ACTIVATION_FAILED_ROLLBACK_VERIFIED",
        )
        self.assertEqual(receipt.observed_generation, 7)
        self.assertEqual(receipt.observed_state_sha256, E)

        with self.assertRaisesRegex(PortableReleaseTransactionError, "exact pre-attempt"):
            record_attempt(
                plan,
                outcome="ROLLED_BACK",
                observed_generation=8,
                observed_state_sha256=A,
                failure_code="BAD_ROLLBACK",
            )

    def test_success_receipt_requires_observed_next_generation_and_state(self) -> None:
        plan = build_transaction_plan(update_request())
        receipt = record_attempt(
            plan,
            outcome="SUCCEEDED",
            observed_generation=8,
            observed_state_sha256=A,
        )
        self.assertEqual(receipt.outcome, "SUCCEEDED")
        self.assertEqual(receipt.plan_digest, plan.digest())

        with self.assertRaisesRegex(PortableReleaseTransactionError, "exact next generation"):
            record_attempt(
                plan,
                outcome="SUCCEEDED",
                observed_generation=7,
                observed_state_sha256=A,
            )

    def test_failed_first_install_cannot_invent_lineage(self) -> None:
        plan = build_transaction_plan(
            {
                "schema": REQUEST_SCHEMA,
                "attempt_id": "wp1207-install-fail",
                "operation": "INSTALL",
                "target_release": copy.deepcopy(R1),
                "current_lineage": None,
                "expected_generation": None,
                "expected_state_sha256": None,
                "rollback_release": None,
                "injected_failure_stage": "before-state-create",
            }
        )
        receipt = record_attempt(
            plan,
            outcome="FAILED_NO_MUTATION",
            observed_generation=None,
            observed_state_sha256=None,
            failure_code="INJECTED_BEFORE_STATE_CREATE",
        )
        self.assertIsNone(receipt.observed_generation)
        self.assertIsNone(receipt.observed_state_sha256)

        with self.assertRaisesRegex(PortableReleaseTransactionError, "must not invent"):
            record_attempt(
                plan,
                outcome="FAILED_NO_MUTATION",
                observed_generation=0,
                observed_state_sha256=A,
                failure_code="INJECTED_BEFORE_STATE_CREATE",
            )

    def test_malformed_release_digest_is_rejected(self) -> None:
        raw = update_request()
        raw["target_release"]["artifact_sha256"] = "ABC"
        with self.assertRaisesRegex(PortableReleaseTransactionError, "64-hex"):
            build_transaction_plan(raw)

    def test_partial_predecessor_lineage_is_rejected(self) -> None:
        raw = update_request()
        raw["current_lineage"]["predecessor_generation"] = 6
        raw["current_lineage"]["predecessor_state_sha256"] = None
        raw["current_lineage"]["predecessor_release_digest"] = None
        with self.assertRaisesRegex(PortableReleaseTransactionError, "all present or all absent"):
            build_transaction_plan(raw)


if __name__ == "__main__":
    unittest.main()
