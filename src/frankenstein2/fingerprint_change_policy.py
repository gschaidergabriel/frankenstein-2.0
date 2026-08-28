"""Explicit candidate-only StateFingerprint change policy for WP206 integration.

This module exists to prevent generic ``fingerprint changed`` truthiness from becoming
Persistent Pulse or effect authority.  It compares already-validated StateFingerprint
values and requires the caller to name whether projection-content change or exact identity
change (including generation movement) is the intended signal.

The result is a candidate classification only.  It does not select ACT/ASK/WAIT/DELEGATE,
read state, wake a process, invoke providers/tools, authorize effects, or mint completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from frankenstein2.state_fingerprint import (
    StateFingerprint,
    identity_changed,
    projection_changed,
)

FINGERPRINT_CHANGE_DECISION_SCHEMA = "FRANKENSTEIN2_FINGERPRINT_CHANGE_DECISION/v1"
POLICY_PROJECTION_CHANGED = "PROJECTION_CHANGED"
POLICY_IDENTITY_CHANGED = "IDENTITY_CHANGED"
CLASSIFICATION = "CANDIDATE_CHANGE_SIGNAL_NOT_PULSE_EFFECT_OR_COMPLETION_AUTHORITY"
_ALLOWED_POLICIES = frozenset({POLICY_PROJECTION_CHANGED, POLICY_IDENTITY_CHANGED})


class FingerprintChangePolicyError(ValueError):
    """Fail-closed fingerprint change-policy error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class FingerprintChangeDecision:
    schema: str
    policy: str
    previous_identity_sha256: str
    current_identity_sha256: str
    previous_generation: int
    current_generation: int
    projection_changed: bool
    identity_changed: bool
    candidate_signal: bool
    classification: str = CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != FINGERPRINT_CHANGE_DECISION_SCHEMA:
            raise FingerprintChangePolicyError("fingerprint change decision schema mismatch")
        if self.policy not in _ALLOWED_POLICIES:
            raise FingerprintChangePolicyError(f"unsupported fingerprint change policy: {self.policy!r}")
        for name in ("previous_identity_sha256", "current_identity_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise FingerprintChangePolicyError(f"{name} must be lowercase 64-hex SHA-256")
        for name in ("previous_generation", "current_generation"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise FingerprintChangePolicyError(f"{name} must be a non-negative integer")
        for name in ("projection_changed", "identity_changed", "candidate_signal"):
            if type(getattr(self, name)) is not bool:
                raise FingerprintChangePolicyError(f"{name} must be bool")
        if self.classification != CLASSIFICATION:
            raise FingerprintChangePolicyError("fingerprint change decision classification mismatch")
        expected = (
            self.projection_changed
            if self.policy == POLICY_PROJECTION_CHANGED
            else self.identity_changed
        )
        if self.candidate_signal is not expected:
            raise FingerprintChangePolicyError("candidate_signal does not match explicit policy")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def evaluate_fingerprint_change(
    previous: StateFingerprint,
    current: StateFingerprint,
    *,
    policy: str,
) -> FingerprintChangeDecision:
    """Evaluate one explicit change policy without promoting it to action authority."""
    if not isinstance(previous, StateFingerprint) or not isinstance(current, StateFingerprint):
        raise FingerprintChangePolicyError("StateFingerprint values required")
    if policy not in _ALLOWED_POLICIES:
        raise FingerprintChangePolicyError(f"unsupported fingerprint change policy: {policy!r}")
    if previous.profile != current.profile:
        raise FingerprintChangePolicyError("fingerprint profile mismatch")
    if previous.projection_schema != current.projection_schema:
        raise FingerprintChangePolicyError("projection schema mismatch")
    if current.generation < previous.generation:
        raise FingerprintChangePolicyError("fingerprint generation moved backwards")

    projection_delta = projection_changed(previous, current)
    identity_delta = identity_changed(previous, current)
    signal = projection_delta if policy == POLICY_PROJECTION_CHANGED else identity_delta
    return FingerprintChangeDecision(
        schema=FINGERPRINT_CHANGE_DECISION_SCHEMA,
        policy=policy,
        previous_identity_sha256=previous.identity_sha256,
        current_identity_sha256=current.identity_sha256,
        previous_generation=previous.generation,
        current_generation=current.generation,
        projection_changed=projection_delta,
        identity_changed=identity_delta,
        candidate_signal=signal,
    )


__all__ = [
    "CLASSIFICATION",
    "FINGERPRINT_CHANGE_DECISION_SCHEMA",
    "POLICY_IDENTITY_CHANGED",
    "POLICY_PROJECTION_CHANGED",
    "FingerprintChangeDecision",
    "FingerprintChangePolicyError",
    "evaluate_fingerprint_change",
]
