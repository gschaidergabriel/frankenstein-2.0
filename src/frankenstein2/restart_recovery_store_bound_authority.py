"""REVIEW_ONLY WP901 successor candidate: bind G3 authority to the attested WP206 store.

This module is deliberately non-canonical candidate work. It preserves accepted G4
persisted-row/load attestation but removes the independent caller-supplied
``UnifiedDBAuthorityRef`` from the successor ingress. The downstream G3 authority
reference is derived only after the real persisted row has been loaded and attested.

Repository-component evidence only. No target-host, VPS, effect, completion, model,
training, physical GRID10, GWT/J-Space, EntityOS/HCU runtime, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import CanonicalPersistentAgencyStore
from .restart_recovery_continuation import PersistedRestartEvidence, RestartContinuationPlan
from .restart_recovery_persisted_row_attestation import (
    PersistedCheckpointLoadAttestation,
    PersistedRowLoadAttestationError,
    attest_persisted_checkpoint_load,
)
from .restart_recovery_source_authentication import plan_restart_continuation_from_sources
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


STORE_BOUND_AUTHORITY_SCHEMA = "FRANKENSTEIN2_WP901_STORE_BOUND_AUTHORITY_INGRESS/v1"
STORE_BOUND_AUTHORITY_CLASSIFICATION = (
    "REVIEW_ONLY_STORE_DERIVED_AUTHORITY_BINDING_NOT_TARGET_RUNTIME_OR_EFFECT_AUTHORITY"
)
STORE_BOUND_RECEIPT_PREFIX = "sha256:"


class StoreBoundAuthorityIngressError(PersistedRowLoadAttestationError):
    """Fail-closed error for the REVIEW_ONLY store-bound successor ingress."""


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreBoundRestartPlanResult:
    """Candidate successor output exposing the exact derived authority binding."""

    plan: RestartContinuationPlan
    load_attestation: PersistedCheckpointLoadAttestation
    store_bound_unifieddb_authority: UnifiedDBAuthorityRef

    schema: ClassVar[str] = STORE_BOUND_AUTHORITY_SCHEMA
    classification: ClassVar[str] = STORE_BOUND_AUTHORITY_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "plan": self.plan.as_dict(),
            "plan_sha256": self.plan.sha256(),
            "load_attestation": self.load_attestation.as_dict(),
            "load_attestation_sha256": self.load_attestation.sha256(),
            "store_bound_unifieddb_authority": {
                "receipt_ref": self.store_bound_unifieddb_authority.receipt_ref,
                "canonical_source": self.store_bound_unifieddb_authority.canonical_source,
                "fingerprint_schema": self.store_bound_unifieddb_authority.fingerprint_schema,
            },
            "caller_supplied_unifieddb_authority": "NOT_ACCEPTED_BY_SUCCESSOR_INGRESS",
            "target_host_execution": "NOT_OBSERVED",
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }


def derive_store_bound_unifieddb_authority_ref(
    store: CanonicalPersistentAgencyStore,
    *,
    load_attestation: PersistedCheckpointLoadAttestation,
) -> UnifiedDBAuthorityRef:
    """Derive the G3 authority ref from the exact store identity attested by G4."""
    if type(store) is not CanonicalPersistentAgencyStore:
        raise StoreBoundAuthorityIngressError("CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED")
    if type(load_attestation) is not PersistedCheckpointLoadAttestation:
        raise StoreBoundAuthorityIngressError("PERSISTED_CHECKPOINT_LOAD_ATTESTATION_REQUIRED")
    if load_attestation.canonical_db_path != store.canonical_db_path:
        raise StoreBoundAuthorityIngressError("STORE_BOUND_AUTHORITY_DB_PATH_MISMATCH")
    if (load_attestation.db_device, load_attestation.db_inode) != (
        store.db_device,
        store.db_inode,
    ):
        raise StoreBoundAuthorityIngressError("STORE_BOUND_AUTHORITY_FILE_IDENTITY_MISMATCH")
    if (
        load_attestation.unifieddb_authority_receipt_sha256
        != store.authority_receipt_sha256
    ):
        raise StoreBoundAuthorityIngressError("STORE_BOUND_AUTHORITY_RECEIPT_MISMATCH")
    fingerprint_schema = store.fingerprint.schema
    if fingerprint_schema != "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2":
        raise StoreBoundAuthorityIngressError("STORE_BOUND_AUTHORITY_FINGERPRINT_SCHEMA_MISMATCH")

    return UnifiedDBAuthorityRef(
        receipt_ref=(
            STORE_BOUND_RECEIPT_PREFIX
            + load_attestation.unifieddb_authority_receipt_sha256
        ),
        canonical_source=load_attestation.canonical_db_path,
        fingerprint_schema=fingerprint_schema,
    )


def plan_restart_continuation_from_store_bound_persisted_row(
    store: CanonicalPersistentAgencyStore,
    *,
    checkpoint_id: str,
    evidence: PersistedRestartEvidence,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> StoreBoundRestartPlanResult:
    """Candidate G5 ingress: real WP206 row -> store-derived authority -> G3/G2 plan.

    Intentionally absent from this signature: ``unifieddb_authority``. That identity is
    derived from the exact persisted-row/store attestation produced in this call.
    """
    checkpoint, attestation = attest_persisted_checkpoint_load(
        store,
        checkpoint_id=checkpoint_id,
    )
    authority = derive_store_bound_unifieddb_authority_ref(
        store,
        load_attestation=attestation,
    )
    plan = plan_restart_continuation_from_sources(
        evidence,
        plan_id=plan_id,
        expected_evidence_sha256=expected_evidence_sha256,
        causal_identity=causal_identity,
        unifieddb_authority=authority,
        source_checkpoint=checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
    )
    if plan.source_checkpoint_id != attestation.checkpoint_id:
        raise StoreBoundAuthorityIngressError("STORE_BOUND_PLAN_CHECKPOINT_ID_MISMATCH")
    if plan.source_checkpoint_sha256 != attestation.checkpoint_sha256:
        raise StoreBoundAuthorityIngressError("STORE_BOUND_PLAN_CHECKPOINT_DIGEST_MISMATCH")
    if authority.receipt_ref != (
        STORE_BOUND_RECEIPT_PREFIX
        + attestation.unifieddb_authority_receipt_sha256
    ):
        raise StoreBoundAuthorityIngressError("STORE_BOUND_PLAN_AUTHORITY_RECEIPT_MISMATCH")
    if authority.canonical_source != attestation.canonical_db_path:
        raise StoreBoundAuthorityIngressError("STORE_BOUND_PLAN_AUTHORITY_SOURCE_MISMATCH")

    return StoreBoundRestartPlanResult(
        plan=plan,
        load_attestation=attestation,
        store_bound_unifieddb_authority=authority,
    )


__all__ = [
    "STORE_BOUND_AUTHORITY_CLASSIFICATION",
    "STORE_BOUND_AUTHORITY_SCHEMA",
    "STORE_BOUND_RECEIPT_PREFIX",
    "StoreBoundAuthorityIngressError",
    "StoreBoundRestartPlanResult",
    "derive_store_bound_unifieddb_authority_ref",
    "plan_restart_continuation_from_store_bound_persisted_row",
]
