#!/usr/bin/env python3
"""Fail-closed regression suite for F2-WP-1207 generation-2 release readback."""
from __future__ import annotations

import copy
import unittest

from frankenstein2.portable_release_readback import (
    READBACK_EVIDENCE_SCOPE,
    PortableReleaseReadbackError,
    record_release_readback,
)
from frankenstein2.portable_release_transaction import (
    LINEAGE_SCHEMA,
    RELEASE_SCHEMA,
    REQUEST_SCHEMA,
    PortableReleaseTransactionError,
    ReleaseIdentity,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64
ZERO = "0" * 64


def release(release_id: str, version: str, artifact: str, manifest: str) -> dict:
    return {
        "schema": RELEASE_SCHEMA,
        "release_id": release_id,
        "version": version,
        "artifact_sha256": artifact,
        "manifest_sha256": manifest,
    }


def r1() -> dict:
    return release("frankenstein-2.0-r1", "2.0.0-r1", A, B)


def r2() -> dict:
    return release("frankenstein-2.0-r2", "2.0.0-r2", C, D)


R1_DIGEST = ReleaseIdentity.from_mapping(r1()).digest()
R2_DIGEST = ReleaseIdentity.from_mapping(r2()).digest()


def lineage(*, predecessor: bool = False) -> dict:
    return {
        "schema": LINEAGE_SCHEMA,
        "generation": 7,
        "state_sha256": E,
        "active_release_digest": R2_DIGEST,
        "predecessor_generation": 6 if predecessor else None,
        "predecessor_state_sha256": F if predecessor else None,
        "predecessor_release_digest": R1_DIGEST if predecessor else None,
    }


def update_request(*, injected_failure_stage: str | None = None) -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": "wp1207-g2-update-001",
        "operation": "UPDATE",
        "target_release": r1(),
        "current_lineage": lineage(),
        "expected_generation": 7,
        "expected_state_sha256": E,
        "rollback_release": None,
        "injected_failure_stage": injected_failure_stage,
    }


def install_request(*, injected_failure_stage: str | None = None) -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": "wp1207-g2-install-001",
        "operation": "INSTALL",
        "target_release": r1(),
        "current_lineage": None,
        "expected_generation": None,
        "expected_state_sha256": None,
        "rollback_release": None,
        "injected_failure_stage": injected_failure_stage,
    }


class PortableReleaseReadbackTests(unittest.TestCase):
    def test_success_requires_exact_target_release_readback(self) -> None:
        receipt = record_release_readback(
            update_request(),
            outcome="SUCCEEDED",
            observed_generation=8,
            observed_state_sha256=ZERO,
            observed_active_release_digest=R1_DIGEST,
        )
        self.assertEqual(receipt.expected_active_release_digest, R1_DIGEST)
        self.assertEqual(receipt.observed_active_release_digest, R1_DIGEST)
        self.assertEqual(receipt.evidence_scope, READBACK_EVIDENCE_SCOPE)

    def test_correct_generation_and_state_cannot_mask_wrong_active_release(self) -> None:
        with self.assertRaisesRegex(PortableReleaseReadbackError, "planned target release"):
            record_release_readback(
                update_request(),
                outcome="SUCCEEDED",
                observed_generation=8,
                observed_state_sha256=ZERO,
                observed_active_release_digest=R2_DIGEST,
            )

    def test_success_requires_explicit_release_readback(self) -> None:
        with self.assertRaisesRegex(PortableReleaseReadbackError, "planned target release"):
            record_release_readback(
                update_request(),
                outcome="SUCCEEDED",
                observed_generation=8,
                observed_state_sha256=ZERO,
                observed_active_release_digest=None,
            )

    def test_failed_no_mutation_requires_exact_pre_attempt_release(self) -> None:
        request = update_request(injected_failure_stage="after-copy")
        receipt = record_release_readback(
            request,
            outcome="FAILED_NO_MUTATION",
            observed_generation=7,
            observed_state_sha256=E,
            observed_active_release_digest=R2_DIGEST,
            failure_code="INJECTED_AFTER_COPY",
        )
        self.assertEqual(receipt.expected_active_release_digest, R2_DIGEST)

        with self.assertRaisesRegex(PortableReleaseReadbackError, "pre-attempt release"):
            record_release_readback(
                request,
                outcome="FAILED_NO_MUTATION",
                observed_generation=7,
                observed_state_sha256=E,
                observed_active_release_digest=R1_DIGEST,
                failure_code="INJECTED_AFTER_COPY",
            )

    def test_rolled_back_requires_exact_pre_attempt_release(self) -> None:
        request = update_request()
        receipt = record_release_readback(
            request,
            outcome="ROLLED_BACK",
            observed_generation=7,
            observed_state_sha256=E,
            observed_active_release_digest=R2_DIGEST,
            failure_code="ACTIVATION_FAILED_ROLLBACK_VERIFIED",
        )
        self.assertEqual(receipt.expected_active_release_digest, R2_DIGEST)

        with self.assertRaisesRegex(PortableReleaseReadbackError, "pre-attempt release"):
            record_release_readback(
                request,
                outcome="ROLLED_BACK",
                observed_generation=7,
                observed_state_sha256=E,
                observed_active_release_digest=R1_DIGEST,
                failure_code="ACTIVATION_FAILED_ROLLBACK_VERIFIED",
            )

    def test_failed_first_install_cannot_invent_active_release(self) -> None:
        request = install_request(injected_failure_stage="before-state-create")
        receipt = record_release_readback(
            request,
            outcome="FAILED_NO_MUTATION",
            observed_generation=None,
            observed_state_sha256=None,
            observed_active_release_digest=None,
            failure_code="INJECTED_BEFORE_STATE_CREATE",
        )
        self.assertIsNone(receipt.expected_active_release_digest)

        with self.assertRaisesRegex(PortableReleaseReadbackError, "must not invent"):
            record_release_readback(
                request,
                outcome="FAILED_NO_MUTATION",
                observed_generation=None,
                observed_state_sha256=None,
                observed_active_release_digest=R1_DIGEST,
                failure_code="INJECTED_BEFORE_STATE_CREATE",
            )

    def test_fresh_install_success_binds_target_release(self) -> None:
        receipt = record_release_readback(
            install_request(),
            outcome="SUCCEEDED",
            observed_generation=0,
            observed_state_sha256=ZERO,
            observed_active_release_digest=R1_DIGEST,
        )
        self.assertEqual(receipt.expected_active_release_digest, R1_DIGEST)

    def test_g1_failure_semantics_are_reused_not_weakened(self) -> None:
        with self.assertRaisesRegex(PortableReleaseTransactionError, "synthetic SUCCEEDED"):
            record_release_readback(
                update_request(injected_failure_stage="after-copy"),
                outcome="SUCCEEDED",
                observed_generation=8,
                observed_state_sha256=ZERO,
                observed_active_release_digest=R1_DIGEST,
            )

    def test_readback_receipt_is_deterministic(self) -> None:
        request = update_request()
        first = record_release_readback(
            request,
            outcome="SUCCEEDED",
            observed_generation=8,
            observed_state_sha256=ZERO,
            observed_active_release_digest=R1_DIGEST,
        )
        second = record_release_readback(
            copy.deepcopy(request),
            outcome="SUCCEEDED",
            observed_generation=8,
            observed_state_sha256=ZERO,
            observed_active_release_digest=R1_DIGEST,
        )
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.digest(), second.digest())

    def test_malformed_observed_release_digest_fails_closed(self) -> None:
        with self.assertRaisesRegex(PortableReleaseReadbackError, "64-hex"):
            record_release_readback(
                update_request(),
                outcome="SUCCEEDED",
                observed_generation=8,
                observed_state_sha256=ZERO,
                observed_active_release_digest="ABC",
            )


if __name__ == "__main__":
    unittest.main()
