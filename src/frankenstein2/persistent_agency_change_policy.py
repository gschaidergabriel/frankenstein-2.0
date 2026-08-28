"""Explicit StateFingerprint change policy for F2-WP-206.

This is a bounded interpretation layer over already-validated StateFingerprint values.
It distinguishes projection-content change from lineage/identity-only movement. The result
is descriptive evidence only: it does not choose Pulse actions, wake/resume, effects, goal
adoption, provider/tool invocation, or completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from frankenstein2.state_fingerprint import (
    StateFingerprint,
    StateFingerprintError,
    identity_changed,
    projection_changed,
)

NO_FINGERPRINT_CHANGE = "NO_FINGERPRINT_CHANGE"
LINEAGE_ONLY_CHANGE = "LINEAGE_ONLY_CHANGE"
PROJECTION_CONTENT_CHANGE = "PROJECTION_CONTENT_CHANGE"


@dataclass(frozen=True, slots=True)
class FingerprintChangeAssessment:
    previous_identity_sha256: str
    current_identity_sha256: str
    projection_changed: bool
    identity_changed: bool
    classification: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_fingerprint_change(
    previous: StateFingerprint,
    current: StateFingerprint,
) -> FingerprintChangeAssessment:
    """Classify content vs lineage movement without granting action authority."""
    if not isinstance(previous, StateFingerprint) or not isinstance(current, StateFingerprint):
        raise StateFingerprintError("classify_fingerprint_change requires StateFingerprint values")

    projection_delta = projection_changed(previous, current)
    identity_delta = identity_changed(previous, current)

    if projection_delta:
        classification = PROJECTION_CONTENT_CHANGE
    elif identity_delta:
        classification = LINEAGE_ONLY_CHANGE
    else:
        classification = NO_FINGERPRINT_CHANGE

    return FingerprintChangeAssessment(
        previous_identity_sha256=previous.identity_sha256,
        current_identity_sha256=current.identity_sha256,
        projection_changed=projection_delta,
        identity_changed=identity_delta,
        classification=classification,
    )


__all__ = [
    "FingerprintChangeAssessment",
    "LINEAGE_ONLY_CHANGE",
    "NO_FINGERPRINT_CHANGE",
    "PROJECTION_CONTENT_CHANGE",
    "classify_fingerprint_change",
]
