#!/usr/bin/env python3
"""REVIEW-ONLY counterexample for WP206 G6 database-wide data_version fencing.

This does not modify canonical product state and does not grant generation-6 acceptance.
It asks one narrow question: after a long-lived WP206 store is active, does a valid
CanonicalDeliveryStore (WP103) commit to its own typed tables in the same canonical UnifiedDB
cause the current G6 candidate to classify WP206 authority as drift?

A reproduced UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT is evidence that the current candidate
is database-wide across connections rather than scoped to WP206-owned state.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from state.delivery_lifecycle import (
    DeliveryOperation,
    DeliveryTransition,
    derive_delivery_id,
)
from state.delivery_store import CanonicalDeliveryStore
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


def _authority(db: Path, home: Path):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["FRANKENSTEIN2_DB"] = str(db)
    resolution = resolve_unifieddb_path(env=env, home=home)
    fingerprint = fingerprint_unifieddb(resolution.path)
    return resolution, fingerprint


def _bootstrap(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    try:
        connection.execute("CREATE TABLE bootstrap_identity(seed INTEGER NOT NULL)")
        connection.execute("INSERT INTO bootstrap_identity(seed) VALUES(1)")
        connection.commit()
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        assert str(mode).lower() == "wal", mode
    finally:
        connection.close()


def _delivery_identity() -> CausalIdentity:
    return CausalIdentity(
        session_id="session:wp206-review",
        agent_id="agent:root",
        task_id="task:legitimate-wp103-write",
        turn_id="turn:1",
        causal_id="causal:wp206-review-1",
        generation=1,
    )


def _delivery_transition() -> DeliveryTransition:
    causal_id = "causal:wp206-review-1"
    recipient_id = "recipient:review"
    return DeliveryTransition(
        transition_id="transition:wp103-offer-1",
        delivery_id=derive_delivery_id(causal_id, recipient_id),
        causal_event_id=causal_id,
        recipient_id=recipient_id,
        generation=1,
        operation=DeliveryOperation.OFFER,
        transport_attempt_id="attempt:wp103-1",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / "shared-unified.db"
        _bootstrap(db)

        # Establish the legitimate WP103 typed-table surface before the monitored WP206
        # connection is opened, so the discriminator is the later WP103 data commit rather
        # than one-time schema bootstrap.
        resolution, fingerprint = _authority(db, home)
        delivery = CanonicalDeliveryStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        try:
            delivery.initialize_schema()
        finally:
            delivery.close()

        # Re-fingerprint exact current file identity, then activate the candidate WP206 store.
        resolution, fingerprint = _authority(db, home)
        agency = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        try:
            agency.initialize_schema()
            agency._assert_current_file_identity()
            before_version = int(
                agency.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )

            # A separate, canonical WP103 writer performs an ordinary typed delivery commit
            # into its own tables in the same UnifiedDB.
            wp103_resolution, wp103_fingerprint = _authority(db, home)
            delivery = CanonicalDeliveryStore.open(
                resolution=wp103_resolution,
                fingerprint=wp103_fingerprint,
            )
            try:
                record = delivery.apply(_delivery_identity(), _delivery_transition())
                assert record.state.value == "OFFERED", record
            finally:
                delivery.close()

            after_version = int(
                agency.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )
            assert after_version != before_version, (
                before_version,
                after_version,
                "WP103 commit was not observed by the WP206 connection-local data_version",
            )

            try:
                agency._assert_current_file_identity()
            except PersistentAgencyError as exc:
                if str(exc) != "UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT":
                    raise
                print(
                    "PASS_REPRODUCED_WP206_G6_CROSS_SUBSYSTEM_FALSE_POSITIVE: "
                    "a valid CanonicalDeliveryStore WP103 commit changed data_version and "
                    "the current candidate invalidated the unchanged WP206 authority surface"
                )
                print("CLASSIFICATION=REVIEW_ONLY_COUNTEREXAMPLE")
                print("WP103_TYPED_COMMIT=VALID")
                print("WP206_OWNED_MUTATION=NONE_BY_TEST")
                print("CURRENT_G6_DATABASE_WIDE_FENCE=REPRODUCED")
                print("TARGET_RUNTIME_CREDIT=0")
                print("PHYSICAL_GRID10_CREDIT=0")
                print("GWT_JSPACE_RUNTIME_CREDIT=0")
                print("EFFECT_COMPLETION_TRAINING_CREDIT=0")
                print("WHOLE_SYSTEM_ACCEPTANCE=false")
                return 0

            raise AssertionError(
                "Current G6 candidate no longer rejects the legitimate WP103 commit; "
                "review the implementation before interpreting this discriminator."
            )
        finally:
            agency.close()


if __name__ == "__main__":
    raise SystemExit(main())
