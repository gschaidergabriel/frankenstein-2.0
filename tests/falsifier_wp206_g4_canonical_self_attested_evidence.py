#!/usr/bin/env python3
"""REVIEW_ONLY exact-current falsifier replay for canonical WP206 G4 recovery.

Exact target: src/frankenstein2/wp206_legacy_authority_recovery.py
Accepted G4 blob observed from canonical active pointer:
20eaee5570875568784e6f9234343b6027fdc3ee

G4 closed conflicting repeat provenance, but its public recovery boundary still receives
an expected legacy authority receipt plus provenance from the caller. This negative control
asks whether a first recovery can still self-attest those values from the row being migrated.
It writes a valid checkpoint, replaces only the stored authority receipt with an arbitrary
64-hex value, reads that value back, and submits the row-derived value plus a caller-created
provenance string.

A zero exit code means the post-G3 evidence-laundering counterexample remains reproducible
against the exact G4 source surface. It is repository-hosted negative evidence only and
mints no target-runtime or whole-system credit.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
)
from frankenstein2.wp206_legacy_authority_recovery import (
    RECOVERED,
    recover_legacy_g1_checkpoint_authority,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from wp206_restart_probe import _fixture_checkpoint


def _bootstrap(path: Path) -> None:
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
        _bootstrap(db)

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
            checkpoint_sha = store.write_checkpoint(checkpoint)

            arbitrary = "f" * 64
            if arbitrary == store.authority_receipt_sha256:
                arbitrary = "e" * 64
            assert arbitrary != store.authority_receipt_sha256

            store.connection.execute(
                f"UPDATE {CHECKPOINT_TABLE} "
                "SET unifieddb_authority_receipt_sha256=? WHERE checkpoint_id=?",
                (arbitrary, checkpoint.checkpoint_id),
            )
            store.connection.commit()

            row = store.connection.execute(
                f"SELECT checkpoint_sha256, unifieddb_authority_receipt_sha256 "
                f"FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?",
                (checkpoint.checkpoint_id,),
            ).fetchone()
            assert row == (checkpoint_sha, arbitrary)

            receipt = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id=checkpoint.checkpoint_id,
                expected_legacy_authority_receipt_sha256=row[1],
                recovery_provenance_ref="review:g4-caller-self-attested-not-admitted",
            )
            assert receipt.status == RECOVERED
            assert receipt.legacy_authority_receipt_sha256 == arbitrary
            assert (
                receipt.recovery_provenance_ref
                == "review:g4-caller-self-attested-not-admitted"
            )
            assert (
                receipt.rebound_authority_receipt_sha256
                == store.authority_receipt_sha256
            )

            replayed = store.load_checkpoint(checkpoint.checkpoint_id)
            assert replayed.sha256() == checkpoint_sha
            print(
                "PASS_REPRODUCED_POST_G4_NEGATIVE_CONTROL: WP206 G4 accepted "
                "arbitrary row-derived legacy receipt plus caller-created provenance "
                "without independently authenticated admission evidence"
            )
            return 0
        finally:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
