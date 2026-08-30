"""Persisted-row load attestation for WP901 restart/recovery planning.

F2-WP-901 generation 4 repository-component scope only.

Accepted WP901 G3 proves that restart planning is bound to concrete typed checkpoint,
whole-loop and outcome objects with one explicit causal provenance witness. G3 deliberately
leaves one boundary open: its checkpoint object may still have been constructed by a caller
rather than loaded from the canonical WP206 checkpoint row.

G4 closes only that repository-component gap. It requires an already-open
:class:`CanonicalPersistentAgencyStore`, loads the requested checkpoint through the store's
accepted ``load_checkpoint`` path, records a non-authoritative load attestation, and passes
that exact loaded object into accepted G3 source authentication. The existing WP206 store,
G3 source binding and G2 deterministic planner remain unchanged.

The WP206 load path already checks, at the scope of the checkpoint row it consumes:

* current UnifiedDB device/inode identity;
* stored canonical path/device/inode and store authority-receipt digest;
* stored checkpoint JSON against the row checkpoint digest; and
* typed checkpoint replay against the same digest.

G4 does NOT claim full-database same-inode mutation detection, target-host execution,
physical GRID10/GWT/J-Space runtime, effects, completion, training or whole-system
acceptance. Those remain separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
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
    "CANONICAL_STORE_CHECKPOINT_ROW_LOAD_EVIDENCE_NOT_TRUTH_PERSISTENCE_EFFECT_OR_COMPLETION_AUTHORITY"
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
    """Evidence emitted only after CanonicalPersistentAgencyStore.load_checkpoint succeeds.

    This object is an observation/projection. It is never accepted as a substitute for
    calling the canonical store loader again at a later trust boundary.
    """

    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
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
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "store_authority_receipt_sha256": self.store_authority_receipt_sha256,
            "unifieddb_fingerprint_schema": self.unifieddb_fingerprint_schema,
            "load_method": "CanonicalPersistentAgencyStore.load_checkpoint",
            "persisted_row_attestation": "OBSERVED_BY_CANONICAL_STORE_LOAD",
            "same_inode_global_db_drift_closure": "NOT_CLAIMED",
            "truth_authority": "NONE",
            "persistence_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedRowRestartPlanningResult:
    """One deterministic restart candidate paired with the row-load evidence that fed it."""

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
    """Load one exact WP206 checkpoint row and emit bounded evidence of that load.

    The caller supplies expected digests only as fail-closed fences. The checkpoint object
    itself is obtained exclusively by ``store.load_checkpoint``; no caller-provided
    checkpoint object exists on this ingress API.
    """

    if type(store) is not CanonicalPersistentAgencyStore:
        raise RestartPersistedRowError(
            "store must be concrete CanonicalPersistentAgencyStore"
        )
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
        checkpoint = store.load_checkpoint(checkpoint_id)
    except PersistentAgencyError as exc:
        raise RestartPersistedRowError(
            f"PERSISTED_ROW_LOAD_REJECTED:{exc}"
        ) from exc

    checkpoint_sha = checkpoint.sha256()
    if checkpoint_sha != expected_checkpoint_sha256:
        raise RestartPersistedRowError("PERSISTED_ROW_CHECKPOINT_DIGEST_MISMATCH")

    fingerprint_schema = getattr(store.fingerprint, "schema", None)
    if type(fingerprint_schema) is not str or not fingerprint_schema:
        raise RestartPersistedRowError("PERSISTED_ROW_FINGERPRINT_SCHEMA_MISSING")

    attestation = PersistedCheckpointRowLoadAttestation(
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_generation=checkpoint.generation,
        checkpoint_sha256=checkpoint_sha,
        canonical_db_path=store.canonical_db_path,
        db_device=store.db_device,
        db_inode=store.db_inode,
        store_authority_receipt_sha256=actual_store_authority,
        unifieddb_fingerprint_schema=fingerprint_schema,
    )
    return checkpoint, attestation


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
    """Canonical G4 component ingress: load persisted row -> G3 source bind -> G2 plan."""

    checkpoint, attestation = load_checkpoint_with_row_attestation(
        store,
        checkpoint_id=checkpoint_id,
        expected_checkpoint_sha256=expected_checkpoint_sha256,
        expected_store_authority_receipt_sha256=expected_store_authority_receipt_sha256,
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
