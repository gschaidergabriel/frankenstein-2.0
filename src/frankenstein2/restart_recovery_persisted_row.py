"""Persisted-row load attestation for WP901 restart/recovery planning.

F2-WP-901 generation 4 repository-component scope only.

Accepted WP901 G3 proves that restart planning is bound to concrete typed checkpoint,
whole-loop and outcome objects with one explicit causal provenance witness. G3 deliberately
leaves one boundary open: its checkpoint object may still have been constructed by a caller
rather than loaded from the canonical WP206 checkpoint row.

G4 closes only that repository-component gap. It requires the exact concrete
:class:`CanonicalPersistentAgencyStore`, opens one SQLite read snapshot, loads the requested
checkpoint through the accepted WP206 ``load_checkpoint`` path, re-reads the exact persisted
columns inside that same snapshot, binds them to a deterministic row-evidence digest, and
passes the exact loaded checkpoint object into accepted G3 source authentication.

The existing WP206 implementation is not modified. This is intentionally a WP901-owned
snapshot adapter around the concrete WP206 store, avoiding a competing mutation of WP206
while preserving the stronger invariants: no hostile subclass substitution, no caller-made
checkpoint object, one database snapshot, exact row columns, exact store identity, and exact
checkpoint digest.

G4 does NOT claim full-database same-inode mutation detection, target-host execution,
physical GRID10/GWT/J-Space runtime, effects, completion, training or whole-system
acceptance. Those remain separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
from typing import Any, ClassVar

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)
from .restart_recovery_continuation import PersistedRestartEvidence, RestartContinuationPlan
from .restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    plan_restart_continuation_from_sources,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


ROW_ATTESTATION_SCHEMA = "FRANKENSTEIN2_RESTART_PERSISTED_ROW_LOAD_ATTESTATION/v1"
ROW_ATTESTATION_CLASSIFICATION = (
    "CANONICAL_STORE_SNAPSHOT_ROW_LOAD_EVIDENCE_NOT_TRUTH_PERSISTENCE_EFFECT_OR_COMPLETION_AUTHORITY"
)
PLANNING_RESULT_SCHEMA = "FRANKENSTEIN2_RESTART_PERSISTED_ROW_PLANNING_RESULT/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RestartPersistedRowError(RestartSourceAuthenticationError):
    """Fail-closed error for the WP901 persisted-row ingress boundary."""


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RestartPersistedRowError(
            f"{name} must be exact concrete lowercase 64-hex SHA-256"
        )
    return value


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
        raise RestartPersistedRowError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedCheckpointRowLoadAttestation:
    """Evidence emitted only after a concrete WP206 store load in one DB snapshot."""

    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
    checkpoint_json_sha256: str
    row_evidence_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    store_authority_receipt_sha256: str
    unifieddb_fingerprint_schema: str

    schema: ClassVar[str] = ROW_ATTESTATION_SCHEMA
    classification: ClassVar[str] = ROW_ATTESTATION_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "checkpoint_table": CHECKPOINT_TABLE,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_sha256": self.checkpoint_sha256,
            "checkpoint_json_sha256": self.checkpoint_json_sha256,
            "row_evidence_sha256": self.row_evidence_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "store_authority_receipt_sha256": self.store_authority_receipt_sha256,
            "unifieddb_fingerprint_schema": self.unifieddb_fingerprint_schema,
            "load_method": "CanonicalPersistentAgencyStore.load_checkpoint",
            "receipt_minter": "WP901_SNAPSHOT_ADAPTER_AROUND_CONCRETE_WP206_STORE",
            "sqlite_snapshot_bound": True,
            "persisted_row_attestation": "OBSERVED_BY_CANONICAL_STORE_LOAD_AND_SAME_SNAPSHOT_ROW_BINDING",
            "same_inode_global_db_drift_closure": "NOT_CLAIMED",
            "truth_authority": "NONE",
            "persistence_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "target_host_execution_observed": False,
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedRowRestartPlanningResult:
    """One deterministic restart candidate paired with row-load evidence that fed it."""

    attestation: PersistedCheckpointRowLoadAttestation
    plan: RestartContinuationPlan

    schema: ClassVar[str] = PLANNING_RESULT_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "attestation": self.attestation.as_dict(),
            "attestation_sha256": self.attestation.sha256(),
            "plan": self.plan.as_dict(),
            "plan_sha256": self.plan.sha256(),
            "truth_authority": "NONE",
            "persistence_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def load_checkpoint_with_row_attestation(
    store: CanonicalPersistentAgencyStore,
    *,
    checkpoint_id: str,
    expected_checkpoint_sha256: str,
    expected_store_authority_receipt_sha256: str,
) -> tuple[PersistentAgencyCheckpoint, PersistedCheckpointRowLoadAttestation]:
    """Load one exact WP206 row and attest exact columns from the same SQLite snapshot.

    Caller digests are only fail-closed expectations. The checkpoint object itself is
    obtained exclusively by ``CanonicalPersistentAgencyStore.load_checkpoint``. The
    follow-up row read occurs in the same explicit SQLite transaction/snapshot and must
    reproduce the loaded checkpoint and store authority identities exactly.
    """

    # Reject subclasses so an overridden load_checkpoint cannot mint false positive credit.
    if type(store) is not CanonicalPersistentAgencyStore:
        raise RestartPersistedRowError(
            "store must be concrete CanonicalPersistentAgencyStore"
        )
    if store.connection.in_transaction:
        raise RestartPersistedRowError("PERSISTED_ROW_CALLER_TRANSACTION_ALREADY_OPEN")

    expected_checkpoint_sha256 = _sha256(
        "expected_checkpoint_sha256", expected_checkpoint_sha256
    )
    expected_store_authority_receipt_sha256 = _sha256(
        "expected_store_authority_receipt_sha256",
        expected_store_authority_receipt_sha256,
    )
    actual_store_authority = _sha256(
        "store.authority_receipt_sha256", store.authority_receipt_sha256
    )
    if actual_store_authority != expected_store_authority_receipt_sha256:
        raise RestartPersistedRowError(
            "PERSISTED_ROW_STORE_AUTHORITY_RECEIPT_MISMATCH"
        )

    try:
        # BEGIN + first SELECT in load_checkpoint establishes one stable read snapshot.
        store.connection.execute("BEGIN")
        try:
            checkpoint = store.load_checkpoint(checkpoint_id)
        except PersistentAgencyError as exc:
            raise RestartPersistedRowError(
                f"PERSISTED_ROW_LOAD_REJECTED:{exc}"
            ) from exc

        row = store.connection.execute(
            f"""SELECT checkpoint_id, previous_checkpoint_id, kernel_state_id,
                       generation, checkpoint_sha256, checkpoint_json,
                       canonical_db_path, db_device, db_inode,
                       unifieddb_authority_receipt_sha256
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        if row is None:
            raise RestartPersistedRowError(
                "PERSISTED_ROW_DISAPPEARED_INSIDE_SQLITE_SNAPSHOT"
            )
        (
            row_checkpoint_id,
            row_previous_checkpoint_id,
            row_kernel_state_id,
            row_generation,
            row_checkpoint_sha,
            row_checkpoint_json,
            row_db_path,
            row_device,
            row_inode,
            row_store_authority,
        ) = row

        checkpoint_sha = checkpoint.sha256()
        if checkpoint_sha != expected_checkpoint_sha256:
            raise RestartPersistedRowError(
                "PERSISTED_ROW_CHECKPOINT_DIGEST_MISMATCH"
            )
        if row_checkpoint_id != checkpoint.checkpoint_id:
            raise RestartPersistedRowError("PERSISTED_ROW_ID_MISMATCH")
        if row_generation != checkpoint.generation:
            raise RestartPersistedRowError("PERSISTED_ROW_GENERATION_MISMATCH")
        if row_checkpoint_sha != checkpoint_sha:
            raise RestartPersistedRowError("PERSISTED_ROW_STORED_DIGEST_MISMATCH")
        if os.path.normcase(os.path.realpath(row_db_path)) != os.path.normcase(
            store.canonical_db_path
        ):
            raise RestartPersistedRowError("PERSISTED_ROW_DB_PATH_MISMATCH")
        if (row_device, row_inode) != (store.db_device, store.db_inode):
            raise RestartPersistedRowError("PERSISTED_ROW_DB_FILE_IDENTITY_MISMATCH")
        if row_store_authority != actual_store_authority:
            raise RestartPersistedRowError(
                "PERSISTED_ROW_STORED_AUTHORITY_RECEIPT_MISMATCH"
            )

        checkpoint_json_sha = hashlib.sha256(
            row_checkpoint_json.encode("utf-8")
        ).hexdigest()
        row_evidence = {
            "checkpoint_id": row_checkpoint_id,
            "previous_checkpoint_id": row_previous_checkpoint_id,
            "kernel_state_id": row_kernel_state_id,
            "generation": row_generation,
            "checkpoint_sha256": row_checkpoint_sha,
            "checkpoint_json_sha256": checkpoint_json_sha,
            "canonical_db_path": os.path.realpath(row_db_path),
            "db_device": row_device,
            "db_inode": row_inode,
            "unifieddb_authority_receipt_sha256": row_store_authority,
        }
        fingerprint_schema = getattr(store.fingerprint, "schema", None)
        if type(fingerprint_schema) is not str or not fingerprint_schema:
            raise RestartPersistedRowError(
                "PERSISTED_ROW_FINGERPRINT_SCHEMA_MISSING"
            )

        attestation = PersistedCheckpointRowLoadAttestation(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_generation=checkpoint.generation,
            checkpoint_sha256=checkpoint_sha,
            checkpoint_json_sha256=checkpoint_json_sha,
            row_evidence_sha256=_digest(row_evidence),
            canonical_db_path=store.canonical_db_path,
            db_device=store.db_device,
            db_inode=store.db_inode,
            store_authority_receipt_sha256=actual_store_authority,
            unifieddb_fingerprint_schema=fingerprint_schema,
        )
        store.connection.commit()
        return checkpoint, attestation
    except Exception:
        if store.connection.in_transaction:
            store.connection.rollback()
        raise


def plan_restart_continuation_from_persisted_row(
    evidence: PersistedRestartEvidence,
    *,
    store: CanonicalPersistentAgencyStore,
    checkpoint_id: str,
    expected_checkpoint_sha256: str,
    expected_store_authority_receipt_sha256: str,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> PersistedRowRestartPlanningResult:
    """Canonical G4 component ingress: persisted row -> G3 source bind -> G2 plan."""

    checkpoint, attestation = load_checkpoint_with_row_attestation(
        store,
        checkpoint_id=checkpoint_id,
        expected_checkpoint_sha256=expected_checkpoint_sha256,
        expected_store_authority_receipt_sha256=expected_store_authority_receipt_sha256,
    )
    if type(unifieddb_authority) is not UnifiedDBAuthorityRef:
        raise RestartPersistedRowError(
            "unifieddb_authority must be concrete UnifiedDBAuthorityRef"
        )
    if unifieddb_authority.fingerprint_schema != attestation.unifieddb_fingerprint_schema:
        raise RestartPersistedRowError(
            "PERSISTED_ROW_UNIFIEDDB_FINGERPRINT_SCHEMA_MISMATCH"
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
    return PersistedRowRestartPlanningResult(attestation=attestation, plan=plan)


__all__ = [
    "PLANNING_RESULT_SCHEMA",
    "ROW_ATTESTATION_SCHEMA",
    "PersistedCheckpointRowLoadAttestation",
    "PersistedRowRestartPlanningResult",
    "RestartPersistedRowError",
    "load_checkpoint_with_row_attestation",
    "plan_restart_continuation_from_persisted_row",
]
