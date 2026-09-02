"""CANDIDATE_PATCH regression for WP900 G5 -> WP206 runtime identity persistence.

This does not claim canonical WP206 generation-7 mutation authority. It exercises the
smallest repair after REVIEW_ONLY PR #894 showed that the historical seal-only adapter
cannot distinguish valid G5 runtime subjects that share one deterministic whole-loop
seal.
"""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from frankenstein2.whole_loop_persistence_integration import (
    WholeLoopPersistenceIntegrationError,
    persist_runtime_bound_successor_and_readback,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components
from tests.test_wp900_g5_runtime_bound_whole_loop import SOURCE_A, SOURCE_B, _bind


def _open_store(root):
    root.mkdir()
    home = root / "home"
    home.mkdir()
    db = root / "canonical" / "unified.db"
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


def test_runtime_bound_persistence_preserves_distinct_valid_g5_subjects(tmp_path):
    _, _, _, whole_a, _, candidate_a = _bind(exact_source_sha256=SOURCE_A)
    _, _, _, whole_b, _, candidate_b = _bind(exact_source_sha256=SOURCE_B)
    assert whole_a.sha256() == whole_b.sha256()
    assert candidate_a.whole_loop_seal_sha256 == candidate_b.whole_loop_seal_sha256
    assert candidate_a.exact_source_sha256 != candidate_b.exact_source_sha256
    assert candidate_a.sha256() != candidate_b.sha256()

    current, _, _, _, _, _, _, _, successor = fixture_components()
    store = _open_store(tmp_path / "canonical-authority")
    try:
        store.write_checkpoint(current)
        evidence_a = persist_runtime_bound_successor_and_readback(
            store,
            seal=whole_a,
            runtime_binding=candidate_a,
            next_checkpoint=successor,
        )
        # Exact same deterministic successor bytes are an admitted idempotent replay in the
        # same WP206 authority. The second valid G5 subject therefore shares deterministic
        # persisted-readback evidence while retaining its distinct runtime/source identity.
        evidence_b = persist_runtime_bound_successor_and_readback(
            store,
            seal=whole_b,
            runtime_binding=candidate_b,
            next_checkpoint=successor,
        )
    finally:
        store.close()

    assert evidence_a.persisted_readback_sha256 == evidence_b.persisted_readback_sha256
    assert evidence_a.whole_loop_seal_sha256 == evidence_b.whole_loop_seal_sha256
    assert evidence_a.exact_source_sha256 == SOURCE_A
    assert evidence_b.exact_source_sha256 == SOURCE_B
    assert evidence_a.runtime_bound_whole_loop_sha256 == candidate_a.sha256()
    assert evidence_b.runtime_bound_whole_loop_sha256 == candidate_b.sha256()
    assert evidence_a.sha256() != evidence_b.sha256()

    payload = evidence_a.as_dict()
    assert payload["runtime_identity_preserved"] is True
    assert payload["canonical_persistence_authority"] == "WP206_CANONICAL_PERSISTENT_AGENCY_STORE"
    assert payload["runtime_credit"] == 0
    assert payload["semantic_gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_forged_runtime_identity_fails_closed_before_successor_write(tmp_path):
    _, _, _, whole, _, candidate = _bind(exact_source_sha256=SOURCE_A)
    forged = replace(candidate, exact_source_sha256=SOURCE_B)
    current, _, _, _, _, _, _, _, successor = fixture_components()
    store = _open_store(tmp_path / "forged")
    try:
        store.write_checkpoint(current)
        with pytest.raises(
            WholeLoopPersistenceIntegrationError,
            match="INVALID_RUNTIME_BOUND_WHOLE_LOOP",
        ):
            persist_runtime_bound_successor_and_readback(
                store,
                seal=whole,
                runtime_binding=forged,
                next_checkpoint=successor,
            )
        with pytest.raises(PersistentAgencyError, match="CHECKPOINT_NOT_FOUND"):
            store.load_checkpoint(successor.checkpoint_id)
    finally:
        store.close()


def test_runtime_binding_must_match_exact_whole_loop_seal_before_write(tmp_path):
    _, _, _, whole, _, candidate = _bind(exact_source_sha256=SOURCE_A)
    mismatched_seal = replace(whole, seal_id="whole-loop-mismatched")
    current, _, _, _, _, _, _, _, successor = fixture_components()
    store = _open_store(tmp_path / "seal-mismatch")
    try:
        store.write_checkpoint(current)
        with pytest.raises(
            WholeLoopPersistenceIntegrationError,
            match="RUNTIME_BINDING_SEAL_ID_MISMATCH",
        ):
            persist_runtime_bound_successor_and_readback(
                store,
                seal=mismatched_seal,
                runtime_binding=candidate,
                next_checkpoint=successor,
            )
        with pytest.raises(PersistentAgencyError, match="CHECKPOINT_NOT_FOUND"):
            store.load_checkpoint(successor.checkpoint_id)
    finally:
        store.close()
