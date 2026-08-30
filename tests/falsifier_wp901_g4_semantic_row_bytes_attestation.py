#!/usr/bin/env python3
"""REVIEW_ONLY executable discriminator for WP901 G4 row-evidence completeness.

A successful run means the counterexample is reproduced: two byte-distinct persisted
``checkpoint_json`` column values, both accepted by the canonical WP206 loader and denoting
the same typed checkpoint, produce the same G4 row-load attestation digest.  This is narrow
counterevidence only against the active G4 claim that the attestation binds a deterministic
evidence digest over the exact persisted columns consumed by the loader.
"""
from __future__ import annotations

import json

from frankenstein2.restart_recovery_persisted_row import (
    load_checkpoint_with_row_attestation,
)
from tests.test_restart_recovery_persisted_row import RestartRecoveryPersistedRowTests


def main() -> None:
    case = RestartRecoveryPersistedRowTests(
        methodName="test_canonical_store_row_load_feeds_g3_and_preserves_g2_semantics"
    )
    case.setUp()
    try:
        checkpoint_id = case.checkpoint.checkpoint_id
        expected_checkpoint_sha = case.checkpoint.sha256()
        expected_store_authority = case.store.authority_receipt_sha256

        loaded_before, attestation_before = load_checkpoint_with_row_attestation(
            case.store,
            checkpoint_id=checkpoint_id,
            expected_checkpoint_sha256=expected_checkpoint_sha,
            expected_store_authority_receipt_sha256=expected_store_authority,
        )
        row_before = case.store.connection.execute(
            "SELECT checkpoint_json FROM f2_persistent_agency_checkpoints WHERE checkpoint_id=?",
            (checkpoint_id,),
        ).fetchone()
        assert row_before is not None
        raw_before = row_before[0]
        parsed = json.loads(raw_before)

        # Change only the exact persisted TEXT representation.  JSON value, checkpoint
        # digest, typed replay, row identity and store authority remain unchanged.
        raw_after = json.dumps(parsed, ensure_ascii=False, sort_keys=True, indent=2)
        assert raw_after != raw_before
        assert json.loads(raw_after) == parsed
        case.store.connection.execute(
            "UPDATE f2_persistent_agency_checkpoints SET checkpoint_json=? WHERE checkpoint_id=?",
            (raw_after, checkpoint_id),
        )
        case.store.connection.commit()

        loaded_after, attestation_after = load_checkpoint_with_row_attestation(
            case.store,
            checkpoint_id=checkpoint_id,
            expected_checkpoint_sha256=expected_checkpoint_sha,
            expected_store_authority_receipt_sha256=expected_store_authority,
        )
        row_after = case.store.connection.execute(
            "SELECT checkpoint_json FROM f2_persistent_agency_checkpoints WHERE checkpoint_id=?",
            (checkpoint_id,),
        ).fetchone()
        assert row_after is not None

        assert row_after[0] == raw_after
        assert raw_before != raw_after
        assert loaded_before.sha256() == loaded_after.sha256() == expected_checkpoint_sha

        before_payload = attestation_before.as_dict()
        after_payload = attestation_after.as_dict()
        assert "row_evidence_sha256" not in before_payload
        assert "persisted_columns_sha256" not in before_payload
        assert before_payload == after_payload
        assert attestation_before.sha256() == attestation_after.sha256()

        print(
            "PASS_REPRODUCED_WP901_G4_ROW_EVIDENCE_GAP: "
            "byte-distinct persisted checkpoint_json values were both accepted and produced "
            "the same row-load attestation; no exact persisted-column evidence digest is present"
        )
    finally:
        case.tearDown()


if __name__ == "__main__":
    main()
