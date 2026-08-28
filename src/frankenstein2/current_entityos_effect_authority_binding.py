"""Current-epoch EntityOS effect-authority binding consumer for Frankenstein 2.0 WP105.

This module does not create effect authority.  It consumes a separately supplied
EntityOS binding record plus its current-epoch attestation, verifies the exact source
tuple and epoch relationship, and then narrows the existing generic canonical-effect
bridge to that verified tuple.

No provider, VPS, external effect, UnifiedDB write, or world verification occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .canonical_effect_authority_bridge import (
    CanonicalDispatchResult,
    CanonicalEffectAuthorityEvidence,
    CanonicalEffectAuthorityIdentity,
    CanonicalEffectAuthorityIdentityError,
    EffectCallIntent,
    dispatch_with_canonical_authority,
)
from .effect_executor_interlock import EffectExecutor


BINDING_SCHEMA = "ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING/v1"
ATTESTATION_SCHEMA = "ENTITYOS_EFFECT_AUTHORITY_CURRENT_EPOCH_ATTESTATION/v1"
ATTESTATION_STATUS = "CURRENT_EPOCH_COMPATIBILITY_ATTESTED_NO_AUTHORITY_CHANGE"
ADMITTED_AUTHORITY_STATUS = "ADMITTED_STEERING_AUTHORITY"
EXPECTED_API_VERSION = "ENTITYOS_EFFECT_AUTHORITY_PY_API/v1"
EXPECTED_REPOSITORY = "gschaidergabriel/clay-global-research-entity"


class CurrentEntityOSEffectAuthorityBindingError(RuntimeError):
    """Fail-closed error for stale, malformed, or cross-record authority identity."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CurrentEntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    if len(value) > 1024 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CurrentEntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    return value


def _sha40(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 40 or any(ch not in "0123456789abcdef" for ch in token):
        raise CurrentEntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    return token


def _object(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentEntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    return value


def _require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise CurrentEntityOSEffectAuthorityBindingError(f"{name.upper()}_MISMATCH")


@dataclass(frozen=True, slots=True)
class CurrentEntityOSEffectAuthorityBinding:
    """Verified external authority tuple, still not an authority grant by Frankenstein."""

    binding_repository: str
    binding_record_path: str
    binding_record_blob_sha: str
    binding_record_commit_sha: str
    current_epoch_attestation_path: str
    current_epoch_attestation_commit_sha: str
    implementation_commit_sha: str
    effect_gate_path: str
    effect_gate_blob_sha: str
    effect_journal_path: str
    effect_journal_blob_sha: str
    unifieddb_path: str
    unifieddb_blob_sha: str
    unifieddb_schema_version: str
    api_version: str
    supervisor_epoch: str
    supervisor_delta: str

    def __post_init__(self) -> None:
        _token("binding_repository", self.binding_repository)
        _token("binding_record_path", self.binding_record_path)
        _sha40("binding_record_blob_sha", self.binding_record_blob_sha)
        _sha40("binding_record_commit_sha", self.binding_record_commit_sha)
        _token("current_epoch_attestation_path", self.current_epoch_attestation_path)
        _sha40(
            "current_epoch_attestation_commit_sha",
            self.current_epoch_attestation_commit_sha,
        )
        _sha40("implementation_commit_sha", self.implementation_commit_sha)
        _token("effect_gate_path", self.effect_gate_path)
        _sha40("effect_gate_blob_sha", self.effect_gate_blob_sha)
        _token("effect_journal_path", self.effect_journal_path)
        _sha40("effect_journal_blob_sha", self.effect_journal_blob_sha)
        _token("unifieddb_path", self.unifieddb_path)
        _sha40("unifieddb_blob_sha", self.unifieddb_blob_sha)
        _token("unifieddb_schema_version", self.unifieddb_schema_version)
        _token("api_version", self.api_version)
        _token("supervisor_epoch", self.supervisor_epoch)
        _token("supervisor_delta", self.supervisor_delta)

    def bridge_identity(self) -> CanonicalEffectAuthorityIdentity:
        """Return the already-existing bridge identity for exact dispatch gating.

        EffectJournal/UnifiedDB source identity remains bound in this wrapper record and
        is validated before this identity is ever produced.
        """
        return CanonicalEffectAuthorityIdentity(
            repository=self.binding_repository,
            commit_sha=self.implementation_commit_sha,
            module_path=self.effect_gate_path,
            source_blob_sha=self.effect_gate_blob_sha,
            state_schema=f"UnifiedDB/v{self.unifieddb_schema_version}",
            api_version=self.api_version,
        )


def load_current_entityos_effect_authority_binding(
    *,
    binding_document: Mapping[str, Any],
    binding_record_path: str,
    binding_record_blob_sha: str,
    binding_record_commit_sha: str,
    attestation_document: Mapping[str, Any],
    attestation_path: str,
    attestation_commit_sha: str,
) -> CurrentEntityOSEffectAuthorityBinding:
    """Verify the cross-repository binding + current-epoch attestation pair.

    The caller supplies documents read from the canonical research repository.  This
    function verifies their declared identity relationship; it does not discover or
    self-select authority.  An attestation sourced from a NON_AUTHORITY steering surface
    is rejected even when that surface says authority_change=false.
    """
    binding = _object("binding_document", binding_document)
    attestation = _object("attestation_document", attestation_document)

    _require_equal("binding_schema", binding.get("schema"), BINDING_SCHEMA)
    _require_equal("attestation_schema", attestation.get("schema"), ATTESTATION_SCHEMA)
    _require_equal("attestation_status", attestation.get("status"), ATTESTATION_STATUS)
    _require_equal(
        "attestation_repository",
        attestation.get("canonical_repository"),
        EXPECTED_REPOSITORY,
    )

    binding_record_path = _token("binding_record_path", binding_record_path)
    binding_record_blob_sha = _sha40("binding_record_blob_sha", binding_record_blob_sha)
    binding_record_commit_sha = _sha40(
        "binding_record_commit_sha", binding_record_commit_sha
    )
    attestation_path = _token("attestation_path", attestation_path)
    attestation_commit_sha = _sha40("attestation_commit_sha", attestation_commit_sha)

    implementation = _object("implementation_identity", binding.get("implementation_identity"))
    gate = _object("effect_gate", implementation.get("effect_gate"))
    journal = _object("effect_journal", implementation.get("effect_journal"))
    state = _object("canonical_state_schema", implementation.get("canonical_state_schema"))
    api = _object("api_contract", binding.get("api_contract"))
    attested_binding = _object("attested_binding", attestation.get("attested_binding"))
    epoch = _object("current_epoch_basis", attestation.get("current_epoch_basis"))
    resolution = _object("resolution", attestation.get("resolution"))

    _require_equal("binding_repository", implementation.get("repository"), EXPECTED_REPOSITORY)
    _require_equal("api_version", api.get("version"), EXPECTED_API_VERSION)
    _require_equal("attested_binding_path", attested_binding.get("path"), binding_record_path)
    _require_equal(
        "attested_binding_blob_sha",
        attested_binding.get("blob_sha"),
        binding_record_blob_sha,
    )
    _require_equal(
        "attested_binding_commit",
        attested_binding.get("binding_commit"),
        binding_record_commit_sha,
    )
    _require_equal(
        "attested_implementation_commit",
        attested_binding.get("implementation_bound_commit"),
        implementation.get("bound_commit"),
    )
    for key, actual, expected in (
        ("effect_gate_path", attested_binding.get("effect_gate_path"), gate.get("path")),
        (
            "effect_gate_blob_sha",
            attested_binding.get("effect_gate_blob_sha"),
            gate.get("blob_sha"),
        ),
        (
            "effect_journal_path",
            attested_binding.get("effect_journal_path"),
            journal.get("path"),
        ),
        (
            "effect_journal_blob_sha",
            attested_binding.get("effect_journal_blob_sha"),
            journal.get("blob_sha"),
        ),
        ("unifieddb_path", attested_binding.get("unifieddb_path"), state.get("path")),
        (
            "unifieddb_blob_sha",
            attested_binding.get("unifieddb_blob_sha"),
            state.get("blob_sha"),
        ),
        (
            "unifieddb_schema_version",
            str(attested_binding.get("unifieddb_schema_version")),
            str(state.get("schema_version")),
        ),
        ("attested_api_version", attested_binding.get("api_version"), api.get("version")),
    ):
        _require_equal(key, actual, expected)

    _require_equal(
        "authority_status",
        epoch.get("authority_status"),
        ADMITTED_AUTHORITY_STATUS,
    )
    if epoch.get("authority_change") is not False:
        raise CurrentEntityOSEffectAuthorityBindingError("CURRENT_EPOCH_AUTHORITY_CHANGED")
    if resolution.get("current_epoch_authority_binding_verified") is not True:
        raise CurrentEntityOSEffectAuthorityBindingError(
            "CURRENT_EPOCH_BINDING_NOT_VERIFIED"
        )
    if resolution.get("implementation_tuple_changed") is not False:
        raise CurrentEntityOSEffectAuthorityBindingError(
            "IMPLEMENTATION_TUPLE_CHANGED"
        )
    if resolution.get("new_effect_authority_created") is not False:
        raise CurrentEntityOSEffectAuthorityBindingError(
            "ATTESTATION_CREATED_NEW_AUTHORITY"
        )
    if resolution.get("authority_broadened") is not False:
        raise CurrentEntityOSEffectAuthorityBindingError("AUTHORITY_BROADENED")

    return CurrentEntityOSEffectAuthorityBinding(
        binding_repository=_token("repository", implementation.get("repository")),
        binding_record_path=binding_record_path,
        binding_record_blob_sha=binding_record_blob_sha,
        binding_record_commit_sha=binding_record_commit_sha,
        current_epoch_attestation_path=attestation_path,
        current_epoch_attestation_commit_sha=attestation_commit_sha,
        implementation_commit_sha=_sha40("bound_commit", implementation.get("bound_commit")),
        effect_gate_path=_token("effect_gate_path", gate.get("path")),
        effect_gate_blob_sha=_sha40("effect_gate_blob_sha", gate.get("blob_sha")),
        effect_journal_path=_token("effect_journal_path", journal.get("path")),
        effect_journal_blob_sha=_sha40(
            "effect_journal_blob_sha", journal.get("blob_sha")
        ),
        unifieddb_path=_token("unifieddb_path", state.get("path")),
        unifieddb_blob_sha=_sha40("unifieddb_blob_sha", state.get("blob_sha")),
        unifieddb_schema_version=_token(
            "unifieddb_schema_version", str(state.get("schema_version"))
        ),
        api_version=_token("api_version", api.get("version")),
        supervisor_epoch=_token("supervisor_epoch", str(epoch.get("schema_version"))),
        supervisor_delta=_token("supervisor_delta", epoch.get("selected_delta")),
    )


def dispatch_with_current_entityos_authority(
    intent: EffectCallIntent,
    *,
    binding: CurrentEntityOSEffectAuthorityBinding,
    authorize: Callable[[EffectCallIntent], CanonicalEffectAuthorityEvidence],
    executor: EffectExecutor,
) -> CanonicalDispatchResult:
    """Dispatch through the generic bridge only after current binding verification."""
    if not isinstance(binding, CurrentEntityOSEffectAuthorityBinding):
        raise CanonicalEffectAuthorityIdentityError("CURRENT_ENTITYOS_BINDING_UNRESOLVED")
    return dispatch_with_canonical_authority(
        intent,
        expected_authority=binding.bridge_identity(),
        authorize=authorize,
        executor=executor,
    )


__all__ = [
    "ADMITTED_AUTHORITY_STATUS",
    "ATTESTATION_SCHEMA",
    "ATTESTATION_STATUS",
    "BINDING_SCHEMA",
    "CurrentEntityOSEffectAuthorityBinding",
    "CurrentEntityOSEffectAuthorityBindingError",
    "dispatch_with_current_entityos_authority",
    "load_current_entityos_effect_authority_binding",
]
