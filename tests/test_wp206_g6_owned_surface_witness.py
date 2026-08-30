#!/usr/bin/env python3
"""WP206 G6 acceptance matrix for a WP206-owned SQLite surface witness.

Executable counterevidence in review PR #746 proved that treating connection-local
PRAGMA main.data_version as the verdict is database-wide: a valid WP103 typed commit on
another connection changed data_version and incorrectly invalidated unchanged WP206 state.

G6 therefore requires data_version to be only a dirty/revalidation hint.  The verdict is a
bounded in-memory witness of the WP206-owned checkpoint schema and rows.  This file grants
repository-component evidence only; it grants no target/runtime/GRID10/GWT/J-Space/effect/
completion/training/whole-system credit.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
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
        session_id="session:wp206-g6-witness",
        agent_id="agent:root",
        task_id="task:legitimate-wp103-write",
        turn_id="turn:1",
        causal_id="causal:wp206-g6-witness-1",
        generation=1,
    )


def _delivery_transition() -> DeliveryTransition:
    causal_id = "causal:wp206-g6-witness-1"
    recipient_id = "recipient:wp206-g6-witness"
    return DeliveryTransition(
        transition_id="transition:wp103-offer-wp206-g6-witness",
        delivery_id=derive_delivery_id(causal_id, recipient_id),
        causal_event_id=causal_id,
        recipient_id=recipient_id,
        generation=1,
        operation=DeliveryOperation.OFFER,
        transport_attempt_id="attempt:wp103-wp206-g6-witness",
    )


def _prepare_shared_db(root: Path):
    home = root / "home"
    home.mkdir()
    db = root / "canonical" / "shared-unified.db"
    _bootstrap(db)

    # Materialize WP103 before opening the monitored WP206 connection so the test isolates
    # the later legitimate WP103 data transition rather than schema bootstrap.
    resolution, fingerprint = _authority(db, home)
    delivery = CanonicalDeliveryStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
    )
    try:
        delivery.initialize_schema()
    finally:
        delivery.close()

    resolution, fingerprint = _authority(db, home)
    agency = CanonicalPersistentAgencyStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
    )
    agency.initialize_schema()
    agency._assert_current_file_identity()
    return home, db, agency


def _assert_no_change_fast_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _, _, agency = _prepare_shared_db(Path(tmp))
        try:
            agency._assert_current_file_identity()
            agency._assert_current_file_identity()
        finally:
            agency.close()


def _assert_legitimate_wp103_commit_is_noninterfering() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, db, agency = _prepare_shared_db(Path(tmp))
        try:
            before_version = int(
                agency.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )
            resolution, fingerprint = _authority(db, home)
            delivery = CanonicalDeliveryStore.open(
                resolution=resolution,
                fingerprint=fingerprint,
            )
            try:
                record = delivery.apply(_delivery_identity(), _delivery_transition())
                assert record.state.value == "OFFERED", record
            finally:
                delivery.close()

            after_version = int(
                agency.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )
            assert after_version != before_version, (before_version, after_version)

            # This is the #746 discriminator inverted into the required G6 acceptance law:
            # unrelated typed activity dirties the observer but must not invalidate WP206.
            agency._assert_current_file_identity()
            assert int(
                agency.connection.execute("PRAGMA main.data_version").fetchone()[0]
            ) == agency.sqlite_data_version_baseline
        finally:
            agency.close()


def _assert_external_wp206_schema_mutation_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _, db, agency = _prepare_shared_db(Path(tmp))
        try:
            external = sqlite3.connect(db)
            try:
                external.execute(
                    f"CREATE INDEX idx_wp206_external_tamper ON {CHECKPOINT_TABLE}(checkpoint_id)"
                )
                external.commit()
            finally:
                external.close()

            try:
                agency._assert_current_file_identity()
            except PersistentAgencyError as exc:
                assert str(exc) == "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT", exc
            else:
                raise AssertionError(
                    "external WP206-owned schema mutation did not fail closed"
                )
        finally:
            agency.close()


def main() -> int:
    _assert_no_change_fast_path()
    _assert_legitimate_wp103_commit_is_noninterfering()
    _assert_external_wp206_schema_mutation_fails_closed()
    print("PASS_WP206_G6_OWNED_SURFACE_WITNESS_ACCEPTANCE_MATRIX")
    print("DATA_VERSION_ROLE=CONNECTION_LOCAL_DIRTY_HINT_ONLY")
    print("WP103_TYPED_COMMIT=NONINTERFERING")
    print("WP206_EXTERNAL_SCHEMA_MUTATION=FAIL_CLOSED")
    print("TARGET_RUNTIME_CREDIT=0")
    print("PHYSICAL_GRID10_CREDIT=0")
    print("GWT_JSPACE_RUNTIME_CREDIT=0")
    print("EFFECT_COMPLETION_TRAINING_CREDIT=0")
    print("WHOLE_SYSTEM_ACCEPTANCE=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
