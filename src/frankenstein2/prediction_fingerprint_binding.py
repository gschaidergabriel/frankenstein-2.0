"""Typed StateFingerprint binding for F2-WP-202 prediction residuals.

F2-WP-202 generation 2.

This adapter binds the accepted StateFingerprint primitive to the accepted
PredictionContract/residual primitive without changing either authority boundary.
It accepts only explicit caller-supplied fingerprints/projections and verifies that an
observation projection reproduces its supplied StateFingerprint before residual
calculation.

It does NOT read persistence, infer missing observations, select Pulse actions, schedule
work, call providers/tools, authorize effects, assert world truth, or mint completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from .prediction_contract import (
    PredictionContract,
    PredictionContractError,
    PredictionResidual,
)
from .state_fingerprint import (
    StateFingerprint,
    StateFingerprintError,
    fingerprint_state_projection,
)

PREDICTION_FINGERPRINT_BINDING_SCHEMA = (
    "FRANKENSTEIN2_PREDICTION_FINGERPRINT_BINDING/v1"
)
PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA = (
    "FRANKENSTEIN2_PREDICTION_FINGERPRINT_RESIDUAL/v1"
)
BINDING_CLASSIFICATION = (
    "TYPED_STATE_FINGERPRINT_BINDING_NOT_WORLD_TRUTH_OR_ACTION_AUTHORITY"
)
RESIDUAL_CLASSIFICATION = (
    "TYPED_FINGERPRINT_BOUND_RESIDUAL_NOT_WORLD_TRUTH_OR_ACTION_AUTHORITY"
)


class PredictionFingerprintBindingError(ValueError):
    """Fail-closed typed fingerprint-binding error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_fingerprint(name: str, value: Any) -> StateFingerprint:
    if not isinstance(value, StateFingerprint):
        raise PredictionFingerprintBindingError(
            f"{name} must be an accepted StateFingerprint value"
        )
    return value


def _verify_projection_fingerprint(
    *,
    fingerprint: StateFingerprint,
    projection: Any,
) -> StateFingerprint:
    """Recompute an explicit projection under the supplied fingerprint ABI."""
    try:
        recomputed = fingerprint_state_projection(
            projection_schema=fingerprint.projection_schema,
            generation=fingerprint.generation,
            projection=projection,
        )
    except StateFingerprintError as exc:
        raise PredictionFingerprintBindingError(
            "observed projection is outside the accepted StateFingerprint domain"
        ) from exc

    if recomputed.as_dict() != fingerprint.as_dict():
        raise PredictionFingerprintBindingError(
            "observed projection does not reproduce supplied StateFingerprint"
        )
    return recomputed


@dataclass(frozen=True, slots=True)
class FingerprintBoundPrediction:
    schema: str
    contract: PredictionContract
    basis_fingerprint: StateFingerprint
    classification: str = BINDING_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PREDICTION_FINGERPRINT_BINDING_SCHEMA:
            raise PredictionFingerprintBindingError("binding schema mismatch")
        if not isinstance(self.contract, PredictionContract):
            raise PredictionFingerprintBindingError(
                "contract must be a PredictionContract"
            )
        basis = _require_fingerprint("basis_fingerprint", self.basis_fingerprint)
        if self.contract.basis_fingerprint_sha256 != basis.identity_sha256:
            raise PredictionFingerprintBindingError(
                "PredictionContract basis hash does not match StateFingerprint identity"
            )
        if self.classification != BINDING_CLASSIFICATION:
            raise PredictionFingerprintBindingError("binding classification mismatch")

    @classmethod
    def create(
        cls,
        *,
        prediction_id: str,
        target_id: str,
        generation: int,
        basis_fingerprint: StateFingerprint,
        expected_projection: Any,
    ) -> "FingerprintBoundPrediction":
        basis = _require_fingerprint("basis_fingerprint", basis_fingerprint)
        try:
            contract = PredictionContract.create(
                prediction_id=prediction_id,
                target_id=target_id,
                generation=generation,
                basis_fingerprint_sha256=basis.identity_sha256,
                expected_projection=expected_projection,
            )
        except PredictionContractError as exc:
            raise PredictionFingerprintBindingError(
                "PredictionContract creation failed"
            ) from exc
        return cls(
            schema=PREDICTION_FINGERPRINT_BINDING_SCHEMA,
            contract=contract,
            basis_fingerprint=basis,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "contract": self.contract.as_dict(),
            "basis_fingerprint": self.basis_fingerprint.as_dict(),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_json(self.as_dict())

    def observe(
        self,
        *,
        observation_id: str,
        observation_fingerprint: StateFingerprint,
        observed_projection: Any,
    ) -> "FingerprintBoundResidual":
        observed_fp = _require_fingerprint(
            "observation_fingerprint", observation_fingerprint
        )
        _verify_projection_fingerprint(
            fingerprint=observed_fp,
            projection=observed_projection,
        )
        try:
            residual = self.contract.observe(
                observation_id=observation_id,
                observation_fingerprint_sha256=observed_fp.identity_sha256,
                observed_projection=observed_projection,
            )
        except PredictionContractError as exc:
            raise PredictionFingerprintBindingError(
                "PredictionContract observation failed"
            ) from exc
        return FingerprintBoundResidual(
            schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
            binding_sha256=self.sha256(),
            basis_fingerprint=self.basis_fingerprint,
            observation_fingerprint=observed_fp,
            residual=residual,
        )


@dataclass(frozen=True, slots=True)
class FingerprintBoundResidual:
    schema: str
    binding_sha256: str
    basis_fingerprint: StateFingerprint
    observation_fingerprint: StateFingerprint
    residual: PredictionResidual
    classification: str = RESIDUAL_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA:
            raise PredictionFingerprintBindingError("bound residual schema mismatch")
        if not isinstance(self.binding_sha256, str) or len(self.binding_sha256) != 64:
            raise PredictionFingerprintBindingError("binding_sha256 must be a SHA-256")
        basis = _require_fingerprint("basis_fingerprint", self.basis_fingerprint)
        observed = _require_fingerprint(
            "observation_fingerprint", self.observation_fingerprint
        )
        if not isinstance(self.residual, PredictionResidual):
            raise PredictionFingerprintBindingError(
                "residual must be a PredictionResidual"
            )
        if self.residual.basis_fingerprint_sha256 != basis.identity_sha256:
            raise PredictionFingerprintBindingError(
                "residual basis fingerprint identity mismatch"
            )
        if self.residual.observation_fingerprint_sha256 != observed.identity_sha256:
            raise PredictionFingerprintBindingError(
                "residual observation fingerprint identity mismatch"
            )
        if self.classification != RESIDUAL_CLASSIFICATION:
            raise PredictionFingerprintBindingError(
                "bound residual classification mismatch"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "binding_sha256": self.binding_sha256,
            "basis_fingerprint": self.basis_fingerprint.as_dict(),
            "observation_fingerprint": self.observation_fingerprint.as_dict(),
            "residual": self.residual.as_dict(),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_json(self.as_dict())


__all__ = [
    "BINDING_CLASSIFICATION",
    "PREDICTION_FINGERPRINT_BINDING_SCHEMA",
    "PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA",
    "RESIDUAL_CLASSIFICATION",
    "FingerprintBoundPrediction",
    "FingerprintBoundResidual",
    "PredictionFingerprintBindingError",
]
