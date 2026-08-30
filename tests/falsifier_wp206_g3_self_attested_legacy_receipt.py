#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for WP206 G3 external legacy-evidence admission.

The G3 contract says an expected historical G1 authority receipt must come from an
externally admitted migration/recovery record and arbitrary legacy receipts must not be
accepted.  This negative control deliberately provides no such admitted record.

It writes one valid current checkpoint, replaces only the stored authority-receipt field
with an arbitrary 64-hex value, reads that value back from the same database, supplies it
as ``expected_legacy_receipt_sha256`` together with an unauthenticated evidence-ref string,
and asks the G3 migration API to migrate it.

If migration succeeds, the caller can self-attest the very row being migrated and the
"external admitted evidence" boundary is descriptive rather than enforced.

REVIEW_ONLY / CANDIDATE_FALSIFIER.  No mutation authority, target-runtime credit,
whole-system credit, effect authority or completion authority is claimed.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.persistent_agency_authority_migration import (
    migrate_legacy_authority_receipt,
)
from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from wp206_restart_probe import _fixture_checkpoint


def _create_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS f2_review_bootstrap(id INTEGER PRIMARY KEY)"
        )
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / "unified.db"
        _create_sqlite(db)

        env = os.environ.copy()
        env["HOME"] = str(home)
        env["FRANKENSTEIN2_DB"] = str(db)
        resolution = resolve_unifieddb_path(env=env, home=home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        try:
            store.initialize_schema()
            checkpoint = _fixture_checkpoint()
            checkpoint_sha256 = store.write_checkpoint(checkpoint)

            arbitrary_receipt = "f" * 64
            if arbitrary_receipt == store.authority_receipt_sha256:
                arbitrary_receipt = "e" * 64
            assert arbitrary_receipt != store.authority_receipt_sha256

            # Create a row that is not proven to be an accepted historical G1 row.  The
            # only changed field is the unversioned receipt value that G3 intends to
            # migrate only when authenticated by external admitted evidence.
            store.connection.execute(
                f"""UPDATE {CHECKPOINT_TABLE}
                    SET unifieddb_authority_receipt_sha256=?
                    WHERE checkpoint_id=?""",
                (arbitrary_receipt, checkpoint.checkpoint_id),
            )
            store.connection.commit()

            row = store.connection.execute(
                f"""SELECT checkpoint_sha256, unifieddb_authority_receipt_sha256
                    FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
                (checkpoint.checkpoint_id,),
            ).fetchone()
            assert row is not None
            row_checkpoint_sha256, row_receipt = row
            assert row_checkpoint_sha256 == checkpoint_sha256
            assert row_receipt == arbitrary_receipt

            # No external migration/recovery record is supplied or authenticated.  Both
            # the expected legacy receipt and its claimed provenance are caller-created
            # from the row under migration.
            receipt = migrate_legacy_authority_receipt(
                store,
                migration_id="review/self-attested-row-receipt",
                checkpoint_id=checkpoint.checkpoint_id,
                expected_checkpoint_sha256=row_checkpoint_sha256,
                expected_legacy_receipt_sha256=row_receipt,
                evidence_refs=("review:caller-self-attested-not-admitted",),
            )

            assert receipt.from_receipt_sha256 == arbitrary_receipt
            assert receipt.evidence_refs == (
                "review:caller-self-attested-not-admitted",
            )
            assert receipt.to_receipt_sha256 == store.authority_receipt_sha256
            replayed = store.load_checkpoint(checkpoint.checkpoint_id)
            assert replayed.sha256() == checkpoint_sha256

            print(
                "PASS_REPRODUCED_NEGATIVE_CONTROL: arbitrary row-derived legacy "
                "receipt migrated without authenticated external admission evidence"
            )
            return 0
        finally:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
