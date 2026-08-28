"""Exact current EntityOS EffectGate/EffectJournal source binding for F2-WP-105.

This module does not grant authority.  It pins the external binding record already
written by canonical Clay authority and fails closed if any repository/commit/path/
blob/schema/API field differs.  Updating these constants requires a newer admitted
binding record; Frankenstein 2.0 cannot self-promote a donor, harness, or substitute
implementation by editing call-site text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .canonical_effect_authority_bridge import CanonicalEffectAuthorityIdentity


class EntityOSEffectAuthorityBindingError(RuntimeError):
    pass


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    if len(value) > 1024 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    return value


def _git_sha(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 40 or any(ch not in "0123456789abcdef" for ch in token):
        raise EntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    return token


@dataclass(frozen=True, slots=True)
class EntityOSEffectAuthoritySourceBinding:
    binding_repository: str
    binding_commit: str
    binding_path: str
    binding_blob_sha: str
    implementation_commit: str
    effect_gate_path: str
    effect_gate_blob_sha: str
    effect_journal_path: str
    effect_journal_blob_sha: str
    unified_db_path: str
    unified_db_blob_sha: str
    unified_db_schema_version: str
    api_contract: str

    def __post_init__(self) -> None:
        for name in (
            "binding_repository",
            "binding_path",
            "effect_gate_path",
            "effect_journal_path",
            "unified_db_path",
            "unified_db_schema_version",
            "api_contract",
        ):
            _token(name, getattr(self, name))
        for name in (
            "binding_commit",
            "binding_blob_sha",
            "implementation_commit",
            "effect_gate_blob_sha",
            "effect_journal_blob_sha",
            "unified_db_blob_sha",
        ):
            _git_sha(name, getattr(self, name))

    def authority_ref(self) -> str:
        """Full bundle identity; provenance handle only, never self-authorizing."""
        return (
            f"{self.binding_repository}@{self.implementation_commit}:"
            f"gate={self.effect_gate_path}#{self.effect_gate_blob_sha};"
            f"journal={self.effect_journal_path}#{self.effect_journal_blob_sha};"
            f"state={self.unified_db_path}#{self.unified_db_blob_sha}/v{self.unified_db_schema_version};"
            f"api={self.api_contract};"
            f"binding={self.binding_path}#{self.binding_blob_sha}@{self.binding_commit}"
        )

    def primary_bridge_identity(self) -> CanonicalEffectAuthorityIdentity:
        """Primary identity used by the existing bridge after full bundle validation."""
        return CanonicalEffectAuthorityIdentity(
            repository=self.binding_repository,
            commit_sha=self.implementation_commit,
            module_path=self.effect_gate_path,
            source_blob_sha=self.effect_gate_blob_sha,
            state_schema=f"UnifiedDB/{self.unified_db_schema_version}+EffectJournal",
            api_version=self.api_contract,
        )


CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING = EntityOSEffectAuthoritySourceBinding(
    binding_repository="gschaidergabriel/clay-global-research-entity",
    binding_commit="5638204026468b631de5e774e8403d7a6334021e",
    binding_path="research_entity/continuity/ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING_V1.json",
    binding_blob_sha="b4d91a0dd233c9dc15ff8218feea9248ac1c13c5",
    implementation_commit="2b68aad14bf7824d513b52898904909256e3522d",
    effect_gate_path="the artefact/clayverse/effects.py",
    effect_gate_blob_sha="4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
    effect_journal_path="the artefact/clayverse/effect_journal.py",
    effect_journal_blob_sha="cda63471f1467481f2ff79032d3931730a334a20",
    unified_db_path="the artefact/clayverse/store.py",
    unified_db_blob_sha="a88d923ea3d0eab5847f304f35463e5a2b2c4acd",
    unified_db_schema_version="6",
    api_contract="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EntityOSEffectAuthorityBindingError(f"INVALID_{name.upper()}")
    return value


def validate_current_binding_document(document: Mapping[str, Any]) -> EntityOSEffectAuthoritySourceBinding:
    """Validate the canonical external record against the exact admitted F2 pin."""
    root = _mapping(document, "binding_document")
    if root.get("schema") != "ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING/v1":
        raise EntityOSEffectAuthorityBindingError("BINDING_SCHEMA_MISMATCH")
    if root.get("status") != "CURRENT_EXACT_SOURCE_IDENTITY_BINDING_NO_NEW_AUTHORITY":
        raise EntityOSEffectAuthorityBindingError("BINDING_STATUS_MISMATCH")

    impl = _mapping(root.get("implementation_identity"), "implementation_identity")
    gate = _mapping(impl.get("effect_gate"), "effect_gate")
    journal = _mapping(impl.get("effect_journal"), "effect_journal")
    state = _mapping(impl.get("canonical_state_schema"), "canonical_state_schema")
    api = _mapping(root.get("api_contract"), "api_contract")

    expected = CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING
    checks = {
        "IMPLEMENTATION_REPOSITORY": (impl.get("repository"), expected.binding_repository),
        "IMPLEMENTATION_COMMIT": (impl.get("bound_commit"), expected.implementation_commit),
        "EFFECT_GATE_PATH": (gate.get("path"), expected.effect_gate_path),
        "EFFECT_GATE_BLOB_SHA": (gate.get("blob_sha"), expected.effect_gate_blob_sha),
        "EFFECT_JOURNAL_PATH": (journal.get("path"), expected.effect_journal_path),
        "EFFECT_JOURNAL_BLOB_SHA": (journal.get("blob_sha"), expected.effect_journal_blob_sha),
        "UNIFIED_DB_PATH": (state.get("path"), expected.unified_db_path),
        "UNIFIED_DB_BLOB_SHA": (state.get("blob_sha"), expected.unified_db_blob_sha),
        "UNIFIED_DB_SCHEMA_VERSION": (str(state.get("schema_version")), expected.unified_db_schema_version),
        "API_CONTRACT": (api.get("version"), expected.api_contract),
    }
    for name, (observed, wanted) in checks.items():
        if observed != wanted:
            raise EntityOSEffectAuthorityBindingError(f"{name}_MISMATCH")

    required = root.get("required_fail_closed_invariants")
    if not isinstance(required, list):
        raise EntityOSEffectAuthorityBindingError("REQUIRED_INVARIANTS_MISSING")
    required_text = set(required)
    for invariant in (
        "caller does not supply canonical effect_id; EffectJournal.begin allocates it",
        "real or EntityOS-bound execution cannot precede journal PENDING creation",
        "UNKNOWN_AFTER_RESTART remains unknown and cannot authorize automatic replay",
    ):
        if invariant not in required_text:
            raise EntityOSEffectAuthorityBindingError("REQUIRED_INVARIANT_MISSING")
    return expected


__all__ = [
    "CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING",
    "EntityOSEffectAuthorityBindingError",
    "EntityOSEffectAuthoritySourceBinding",
    "validate_current_binding_document",
]
