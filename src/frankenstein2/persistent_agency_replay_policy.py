"""Explicit StateFingerprint replay-policy binding for F2-WP-206.

This module keeps projection-content change and lineage/identity change as distinct,
caller-selected replay semantics.  A policy binding is deterministic evidence only: it
cannot select an action, resume execution, authorize an effect, or mint completion.

The binding digest is inserted into a PersistentAgencyCheckpoint provenance reference so
changing the selected policy necessarily changes the checkpoint/replay identity.  The
underlying StateFingerprint remains the complete typed measurement; no free-floating
``changed`` boolean is trusted on replay.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from typing import Any

from frankenstein2.persistent_agency_kernel import (
    PersistentAgencyCheckpoint,
    PersistentAgencyIntegrationError,
)
from frankenstein2.state_fingerprint import (
    StateFingerprint,
    identity_changed,
    projection_changed,
)

REPLAY_POLICY_SCHEMA = "FRANKENSTEIN2_FINGERPRINT_REPLAY_POLICY/v1"
POLICY_PROJECTION_CHANGED = "PROJECTION_CHANGED"
POLICY_IDENTITY_CHANGED = "IDENTITY_CHANGED"
_ALLOWED_POLICIES = frozenset({POLICY_PROJECTION_CHANGED, POLICY_IDENTITY_CHANGED})
REF_PREFIX = "fingerprint-replay-policy:"
CLASSIFICATION = "EXPLICIT_FINGERPRINT_CHANGE_POLICY_NOT_ACTION_AUTHORITY"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fingerprint_json(value: StateFingerprint) -> str:
    if not isinstance(value, StateFingerprint):
        raise PersistentAgencyIntegrationError("replay policy requires StateFingerprint values")
    return _canonical_json(value.as_dict())


@dataclass(frozen=True, slots=True)
class FingerprintReplayPolicyBinding:
    schema: str
    policy: str
    previous_checkpoint_sha256: str
    previous_fingerprint_json: str
    previous_fingerprint_sha256: str
    current_integration_generation: int
    current_fingerprint_json: str
    current_fingerprint_sha256: str
    changed: bool
    classification: str = CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != REPLAY_POLICY_SCHEMA:
            raise PersistentAgencyIntegrationError("replay policy schema mismatch")
        if self.policy not in _ALLOWED_POLICIES:
            raise PersistentAgencyIntegrationError("unsupported fingerprint replay policy")
        if not isinstance(self.current_integration_generation, int) or isinstance(
            self.current_integration_generation, bool
        ) or self.current_integration_generation <= 0:
            raise PersistentAgencyIntegrationError(
                "replay policy requires a positive current integration generation"
            )
        if not isinstance(self.changed, bool):
            raise PersistentAgencyIntegrationError("replay policy changed must be boolean")
        if self.classification != CLASSIFICATION:
            raise PersistentAgencyIntegrationError("replay policy classification mismatch")

        try:
            previous_payload = json.loads(self.previous_fingerprint_json)
            current_payload = json.loads(self.current_fingerprint_json)
            previous = StateFingerprint(**previous_payload)
            current = StateFingerprint(**current_payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PersistentAgencyIntegrationError("invalid replay-policy fingerprint payload") from exc

        if _canonical_json(previous_payload) != self.previous_fingerprint_json:
            raise PersistentAgencyIntegrationError("previous replay fingerprint is not canonical JSON")
        if _canonical_json(current_payload) != self.current_fingerprint_json:
            raise PersistentAgencyIntegrationError("current replay fingerprint is not canonical JSON")
        if _sha256_text(self.previous_fingerprint_json) != self.previous_fingerprint_sha256:
            raise PersistentAgencyIntegrationError("previous replay fingerprint digest mismatch")
        if _sha256_text(self.current_fingerprint_json) != self.current_fingerprint_sha256:
            raise PersistentAgencyIntegrationError("current replay fingerprint digest mismatch")
        if len(self.previous_checkpoint_sha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.previous_checkpoint_sha256
        ):
            raise PersistentAgencyIntegrationError("previous_checkpoint_sha256 must be lowercase SHA-256")

        expected = (
            projection_changed(previous, current)
            if self.policy == POLICY_PROJECTION_CHANGED
            else identity_changed(previous, current)
        )
        if self.changed is not expected:
            raise PersistentAgencyIntegrationError("replay policy changed result does not match fingerprints")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())

    def provenance_ref(self) -> str:
        return REF_PREFIX + self.sha256()


def build_replay_policy_binding(
    previous: PersistentAgencyCheckpoint,
    current: PersistentAgencyCheckpoint,
    *,
    policy: str,
) -> FingerprintReplayPolicyBinding:
    """Build a deterministic policy receipt over one exact checkpoint transition."""
    if not isinstance(previous, PersistentAgencyCheckpoint) or not isinstance(
        current, PersistentAgencyCheckpoint
    ):
        raise PersistentAgencyIntegrationError("replay policy requires checkpoint values")
    if current.integration_generation != previous.integration_generation + 1:
        raise PersistentAgencyIntegrationError("replay policy checkpoint generation is not contiguous")
    if current.parent_checkpoint_sha256 != previous.sha256():
        raise PersistentAgencyIntegrationError("replay policy parent checkpoint mismatch")
    if policy not in _ALLOWED_POLICIES:
        raise PersistentAgencyIntegrationError("unsupported fingerprint replay policy")

    previous_fp = previous.state_fingerprint()
    current_fp = current.state_fingerprint()
    previous_json = _fingerprint_json(previous_fp)
    current_json = _fingerprint_json(current_fp)
    changed = (
        projection_changed(previous_fp, current_fp)
        if policy == POLICY_PROJECTION_CHANGED
        else identity_changed(previous_fp, current_fp)
    )
    return FingerprintReplayPolicyBinding(
        schema=REPLAY_POLICY_SCHEMA,
        policy=policy,
        previous_checkpoint_sha256=previous.sha256(),
        previous_fingerprint_json=previous_json,
        previous_fingerprint_sha256=_sha256_text(previous_json),
        current_integration_generation=current.integration_generation,
        current_fingerprint_json=current_json,
        current_fingerprint_sha256=_sha256_text(current_json),
        changed=changed,
    )


def bind_checkpoint_replay_policy(
    previous: PersistentAgencyCheckpoint,
    current: PersistentAgencyCheckpoint,
    *,
    policy: str,
) -> tuple[PersistentAgencyCheckpoint, FingerprintReplayPolicyBinding]:
    """Return a checkpoint whose replay identity includes the explicit policy receipt."""
    binding = build_replay_policy_binding(previous, current, policy=policy)
    refs = tuple(ref for ref in current.provenance_refs if not ref.startswith(REF_PREFIX))
    bound = replace(current, provenance_refs=refs + (binding.provenance_ref(),))
    return bound, binding


def verify_checkpoint_replay_policy(
    previous: PersistentAgencyCheckpoint,
    current: PersistentAgencyCheckpoint,
    binding: FingerprintReplayPolicyBinding,
) -> bool:
    """Fail closed unless the persisted checkpoint carries this exact replay policy."""
    if not isinstance(binding, FingerprintReplayPolicyBinding):
        raise PersistentAgencyIntegrationError("binding must be FingerprintReplayPolicyBinding")
    if current.integration_generation != binding.current_integration_generation:
        raise PersistentAgencyIntegrationError("replay policy generation mismatch")
    if current.parent_checkpoint_sha256 != previous.sha256():
        raise PersistentAgencyIntegrationError("replay policy parent checkpoint mismatch")
    if binding.previous_checkpoint_sha256 != previous.sha256():
        raise PersistentAgencyIntegrationError("replay policy previous checkpoint digest mismatch")
    if current.state_fingerprint_sha256 != binding.current_fingerprint_sha256:
        raise PersistentAgencyIntegrationError("replay policy current fingerprint digest mismatch")
    if previous.state_fingerprint_sha256 != binding.previous_fingerprint_sha256:
        raise PersistentAgencyIntegrationError("replay policy previous fingerprint digest mismatch")
    if binding.provenance_ref() not in current.provenance_refs:
        raise PersistentAgencyIntegrationError("checkpoint is missing exact fingerprint replay policy binding")
    return True


__all__ = [
    "CLASSIFICATION",
    "FingerprintReplayPolicyBinding",
    "POLICY_IDENTITY_CHANGED",
    "POLICY_PROJECTION_CHANGED",
    "REF_PREFIX",
    "REPLAY_POLICY_SCHEMA",
    "bind_checkpoint_replay_policy",
    "build_replay_policy_binding",
    "verify_checkpoint_replay_policy",
]
