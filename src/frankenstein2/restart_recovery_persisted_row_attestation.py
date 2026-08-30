"""Persisted-row load attestation for WP901 restart/recovery planning.

F2-WP-901 generation 4 repository-component scope only.

Accepted WP901 G3 authenticates concrete typed checkpoint / WP900 / outcome source objects,
but explicitly does not prove that the restart checkpoint came from an actual persisted
WP206 row.  This module closes only that boundary.  The canonical ingress receives a
Concrete ``CanonicalPersistentAgencyStore`` plus checkpoint id, opens one SQLite read
transaction, calls the already-accepted WP206 ``load_checkpoint`` path, and re-reads the
same checkpoint row inside the same transaction snapshot to produce deterministic evidence
for the exact persisted columns consumed by that loader boundary.

The resulting receipt is evidence only.  It is not a second persistence authority, does not
schedule work or execute effects, and does not prove target-host execution.  It also does
NOT close rollback/freshness or same-inode live-drift questions; those remain separate
falsifiers.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from typing import Any, ClassVar

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)
from .restart_recovery_continuation import (
    PersistedRestartEvidence,
    RestartContinuationPlan,
)
from .restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    plan_restart_continuation_from_sources,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


LOAD_ATTESTATION_SCHEMA = "FRANKENSTEIN2_PERSISTED_CHECKPOINT_LOAD_ATTESTATION/v1"
LOAD_ATTESTATION_CLASSIFICATION = (
    "PERSISTED_ROW_TRANSACTION_SNAPSHOT_LOAD_EVIDENCE_NOT_TRUTH_RUNTIME_OR_EFFECT_AUTHORITY"
)


class PersistedRowLoadAttestationError(RestartSourceAuthenticationError):
    """Fail-closed G4 persisted-row/load binding error."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PersistedRowLoadAttestationError(
            "load attestation value must be canonical-JSON encodable"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedCheckpointLoadAttestation:
    """Evidence that one checkpoint passed through the accepted WP206 row loader."""

    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    unifieddb_authority_receipt_sha256: str
    row_evidence_sha256: str

    schema: ClassVar[str] = LOAD_ATTESTATION_SCHEMA
    classification: ClassVar[str] = LOAD_ATTESTATION_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_sha256": self.checkpoint_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "unifieddb_authority_receipt_sha256": self.unifieddb_authority_receipt_sha256,
            "row_evidence_sha256": self.row_evidence_sha256,
            "persisted_row_attestation": "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE",
            "transaction_snapshot_binding": "OBSERVED",
            "freshness_attestation": "NOT_OBSERVED",
            "same_inode_live_drift_closure": "NOT_OBSERVED",
            "target_host_execution": "NOT_OBSERVED",
            "truth_authority": "NONE",
            "persistence_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedRowRestartPlanResult:
    """G4 output: accepted G2/G3 plan plus bounded load evidence."""

    plan: RestartContinuationPlan
    load_attestation: PersistedCheckpointLoadAttestation

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.as_dict(),
            "plan_sha256": self.plan.sha256(),
            "load_attestation": self.load_attestation.as_dict(),
            "load_attestation_sha256": self.load_attestation.sha256(),
            "runtime_credit": 0,
            "target_host_execution": "NOT_OBSERVED",
            "whole_system_acceptance": False,
        }


def attest_persisted_checkpoint_load(
    store: CanonicalPersistentAgencyStore,
    *,
    checkpoint_id: str,
) -> tuple[PersistentAgencyCheckpoint, PersistedCheckpointLoadAttestation]:
    """Load one checkpoint and bind the exact persisted-row snapshot used by WP206.

    Both the accepted ``load_checkpoint`` call and the row-evidence read occur inside one
    SQLite read transaction.  This prevents an intervening committed writer from turning
    the second query into evidence for a different database snapshot.  Existing WP206
    digest/path/device/inode/authority checks remain the source of checkpoint admission.
    """
    if type(store) is not CanonicalPersistentAgencyStore:
        raise PersistedRowLoadAttestationError(
            "CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED"
        )
    if type(checkpoint_id) is not str or not checkpoint_id or checkpoint_id != checkpoint_id.strip():
        raise PersistedRowLoadAttestationError(
            "checkpoint_id must be non-empty already-trimmed string"
        )
    if store.connection.in_transaction:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_LOAD_REQUIRES_CLEAN_TRANSACTION_BOUNDARY"
        )

    connection = store.connection
    try:
        connection.execute("BEGIN")
        checkpoint = store.load_checkpoint(checkpoint_id)
        row = connection.execute(
            f"""SELECT generation, checkpoint_sha256, checkpoint_json,
                       canonical_db_path, db_device, db_inode,
                       unifieddb_authority_receipt_sha256
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise PersistedRowLoadAttestationError(
                "PERSISTED_ROW_DISAPPEARED_WITHIN_LOAD_SNAPSHOT"
            )
        (
            stored_generation,
            stored_checkpoint_sha,
            stored_checkpoint_json,
            stored_path,
            stored_device,
            stored_inode,
            stored_authority_receipt,
        ) = row

        if stored_generation != checkpoint.generation:
            raise PersistedRowLoadAttestationError(
                "PERSISTED_ROW_CHECKPOINT_GENERATION_MISMATCH"
            )
        if stored_checkpoint_sha != checkpoint.sha256():
            raise PersistedRowLoadAttestationError(
                "PERSISTED_ROW_CHECKPOINT_DIGEST_MISMATCH"
            )
        if not _same_real_path(stored_path, store.canonical_db_path):
            raise PersistedRowLoadAttestationError(
                "PERSISTED_ROW_DB_PATH_AUTHORITY_MISMATCH"
            )
        if (stored_device, stored_inode) != (store.db_device, store.db_inode):
            raise PersistedRowLoadAttestationError(
                "PERSISTED_ROW_DB_FILE_IDENTITY_MISMATCH"
            )
        if stored_authority_receipt != store.authority_receipt_sha256:
            raise PersistedRowLoadAttestationError(
                "PERSISTED_ROW_DB_AUTHORITY_RECEIPT_MISMATCH"
            )

        row_evidence = {
            "schema": "FRANKENSTEIN2_PERSISTED_CHECKPOINT_ROW_EVIDENCE/v1",
            "checkpoint_id": checkpoint_id,
            "generation": stored_generation,
            "checkpoint_sha256": stored_checkpoint_sha,
            "checkpoint_json": stored_checkpoint_json,
            "canonical_db_path": stored_path,
            "db_device": stored_device,
            "db_inode": stored_inode,
            "unifieddb_authority_receipt_sha256": stored_authority_receipt,
        }
        attestation = PersistedCheckpointLoadAttestation(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_generation=checkpoint.generation,
            checkpoint_sha256=checkpoint.sha256(),
            canonical_db_path=store.canonical_db_path,
            db_device=store.db_device,
            db_inode=store.db_inode,
            unifieddb_authority_receipt_sha256=store.authority_receipt_sha256,
            row_evidence_sha256=_digest(row_evidence),
        )
        connection.commit()
        return checkpoint, attestation
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def plan_restart_continuation_from_persisted_row(
    store: CanonicalPersistentAgencyStore,
    *,
    checkpoint_id: str,
    evidence: PersistedRestartEvidence,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> PersistedRowRestartPlanResult:
    """Canonical G4 ingress: persisted WP206 row -> accepted G3 -> accepted G2 plan."""
    checkpoint, attestation = attest_persisted_checkpoint_load(
        store,
        checkpoint_id=checkpoint_id,
    )
    plan = plan_restart_continuation_from_sources(
        evidence,
        plan_id=plan_id,
        expected_evidence_sha256=expected_evidence_sha256,
        causal_identity=causal_identity,
        unifieddb_authority=unifieddb_authority,
        source_checkpoint=checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
    )
    if plan.source_checkpoint_id != attestation.checkpoint_id:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_PLAN_CHECKPOINT_ID_MISMATCH"
        )
    if plan.source_checkpoint_sha256 != attestation.checkpoint_sha256:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_PLAN_CHECKPOINT_DIGEST_MISMATCH"
        )
    return PersistedRowRestartPlanResult(
        plan=plan,
        load_attestation=attestation,
    )


__all__ = [
    "LOAD_ATTESTATION_CLASSIFICATION",
    "LOAD_ATTESTATION_SCHEMA",
    "PersistedCheckpointLoadAttestation",
    "PersistedRowLoadAttestationError",
    "PersistedRowRestartPlanResult",
    "attest_persisted_checkpoint_load",
    "plan_restart_continuation_from_persisted_row",
]
