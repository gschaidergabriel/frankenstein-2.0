"""REVIEW_ONLY discriminator for WP900 G5 runtime identity -> WP206 persistence.

This deliberately adds no adapter or persistence authority.  It runs the accepted G5
binder and the existing WP900->WP206 persistence adapter over the same deterministic
whole-loop seal, then asks whether canonical persistence distinguishes two otherwise
valid G5 candidates whose only changed authority-bearing field is exact source identity.
"""
from __future__ import annotations

import sqlite3

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.runtime_bound_whole_loop import validate_runtime_bound_whole_loop
from frankenstein2.whole_loop_persistence_integration import persist_sealed_successor_and_readback
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from test_whole_persistent_loop import fixture_components
from test_wp900_g5_runtime_bound_whole_loop import SOURCE_A, SOURCE_B, _bind


def _open_store(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    db = tmp_path / "canonical" / "unified.db"
    db.parent.mkdir()
    connection = sqlite3.connect(db)
    try:
        connection.execute("CREATE TABLE f2_bootstrap(id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=home)
    fingerprint = fingerprint_unifieddb(resolution.path)
    store = CanonicalPersistentAgencyStore.open(resolution=resolution, fingerprint=fingerprint)
    store.initialize_schema()
    return store


def test_wp206_persistence_does_not_yet_bind_wp900_g5_runtime_source_identity(tmp_path):
    # Both G5 candidates are valid and intentionally share the exact deterministic
    # WholePersistentLoopSeal.  Only the admitted exact source/runtime subject differs.
    _, _, _, whole_a, _, candidate_a = _bind(exact_source_sha256=SOURCE_A)
    _, _, _, whole_b, _, candidate_b = _bind(exact_source_sha256=SOURCE_B)
    validate_runtime_bound_whole_loop(candidate_a)
    validate_runtime_bound_whole_loop(candidate_b)
    assert whole_a.sha256() == whole_b.sha256()
    assert candidate_a.whole_loop_seal_sha256 == whole_a.sha256()
    assert candidate_b.whole_loop_seal_sha256 == whole_b.sha256()
    assert candidate_a.exact_source_sha256 != candidate_b.exact_source_sha256
    assert candidate_a.sha256() != candidate_b.sha256()

    # Reuse the canonical deterministic fixture and existing WP206 authority.  No second
    # writer/receipt schema is introduced.  The persistence adapter consumes only the
    # whole-loop seal, so its evidence cannot distinguish the two valid G5 subjects.
    current, _, _, _, _, _, _, _, successor = fixture_components()
    store = _open_store(tmp_path)
    try:
        store.write_checkpoint(current)
        persisted = persist_sealed_successor_and_readback(
            store,
            seal=whole_a,
            next_checkpoint=successor,
        )
    finally:
        store.close()

    assert persisted.whole_loop_seal_sha256 == candidate_a.whole_loop_seal_sha256
    assert persisted.whole_loop_seal_sha256 == candidate_b.whole_loop_seal_sha256
    assert "exact_source_sha256" not in persisted.as_dict()
    assert "causal_runtime_readback_sha256" not in persisted.as_dict()
    assert persisted.runtime_credit == 0 if hasattr(persisted, "runtime_credit") else persisted.as_dict()["runtime_credit"] == 0
    assert persisted.as_dict()["whole_system_acceptance"] is False
