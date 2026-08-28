"""Deterministic prediction/residual primitive for Frankenstein 2.0.

F2-WP-202 generation 1.

A PredictionContract freezes an explicitly supplied expected typed projection together
with the fingerprint of the state from which that prediction was made. A later explicit
observation can be compared deterministically. Nothing here predicts missing facts,
decides actions, reads durable state, invokes a model, or promotes a prediction to truth.

Residuals are type-sensitive: ``1`` != ``1.0`` and ``True`` is never numeric ``1``.
Numeric magnitudes are reported only when both leaves have the same numeric JSON type.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

PREDICTION_CONTRACT_SCHEMA = "FRANKENSTEIN2_PREDICTION_CONTRACT/v1"
PREDICTION_RESIDUAL_SCHEMA = "FRANKENSTEIN2_PREDICTION_RESIDUAL/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_IDENTIFIER_LENGTH = 512


class PredictionContractError(ValueError):
    """Fail-closed prediction/residual contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise PredictionContractError(f"{name} must be a string")
    if not value or value != value.strip():
        raise PredictionContractError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise PredictionContractError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PredictionContractError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PredictionContractError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise PredictionContractError("generation must be a positive integer")
    return value


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _validate_json(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)) or type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise PredictionContractError(f"non-finite float at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}/{index}")
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise PredictionContractError(f"mapping key at {path} must be a string")
        for key in sorted(value):
            _validate_json(value[key], f"{path}/{_escape_pointer(key)}")
        return
    raise PredictionContractError(
        f"unsupported projection value at {path}: {type(value).__name__}"
    )


def _canonical_json(value: Any) -> str:
    _validate_json(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    raise PredictionContractError(f"unsupported JSON type: {type(value).__name__}")


def _leaf_count(value: Any) -> int:
    if isinstance(value, Mapping):
        return 1 if not value else sum(_leaf_count(value[key]) for key in value)
    if isinstance(value, list):
        return 1 if not value else sum(_leaf_count(item) for item in value)
    return 1


def _record_leaf_paths(value: Any, path: str, output: list[str]) -> None:
    if isinstance(value, Mapping) and value:
        for key in sorted(value):
            _record_leaf_paths(value[key], f"{path}/{_escape_pointer(key)}", output)
        return
    if isinstance(value, list) and value:
        for index, item in enumerate(value):
            _record_leaf_paths(item, f"{path}/{index}", output)
        return
    output.append(path)


def _compare(expected: Any, observed: Any, path: str, out: dict[str, Any]) -> int:
    """Populate diff lists and return count of directly compared leaves."""
    expected_type = _json_type(expected)
    observed_type = _json_type(observed)
    if expected_type != observed_type:
        out["type_mismatch"].append(path)
        out["changed"].append(path)
        return 1

    if isinstance(expected, Mapping):
        expected_keys = set(expected)
        observed_keys = set(observed)
        for key in sorted(expected_keys - observed_keys):
            _record_leaf_paths(expected[key], f"{path}/{_escape_pointer(key)}", out["missing"])
        for key in sorted(observed_keys - expected_keys):
            _record_leaf_paths(observed[key], f"{path}/{_escape_pointer(key)}", out["unexpected"])
        compared = sum(
            _compare(expected[key], observed[key], f"{path}/{_escape_pointer(key)}", out)
            for key in sorted(expected_keys & observed_keys)
        )
        return 1 if not expected and not observed else compared

    if isinstance(expected, list):
        common = min(len(expected), len(observed))
        compared = sum(
            _compare(expected[index], observed[index], f"{path}/{index}", out)
            for index in range(common)
        )
        for index in range(common, len(expected)):
            _record_leaf_paths(expected[index], f"{path}/{index}", out["missing"])
        for index in range(common, len(observed)):
            _record_leaf_paths(observed[index], f"{path}/{index}", out["unexpected"])
        return 1 if not expected and not observed else compared

    if expected != observed:
        out["changed"].append(path)
        if type(expected) is int and type(observed) is int:
            out["numeric"][path] = float(abs(observed - expected))
        elif type(expected) is float and type(observed) is float:
            out["numeric"][path] = abs(observed - expected)
    return 1


@dataclass(frozen=True, slots=True)
class PredictionResidual:
    schema: str
    prediction_id: str
    observation_id: str
    target_id: str
    generation: int
    basis_fingerprint_sha256: str
    observation_fingerprint_sha256: str
    expected_projection_sha256: str
    observed_projection_sha256: str
    exact_match: bool
    changed_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    unexpected_paths: tuple[str, ...]
    type_mismatch_paths: tuple[str, ...]
    numeric_absolute_residuals: tuple[tuple[str, float], ...]
    numeric_l1: float
    mismatch_count: int
    expected_leaf_count: int
    observed_leaf_count: int
    compared_leaf_count: int
    mismatch_fraction: float
    classification: str = "EXPLICIT_OBSERVATION_RESIDUAL_NOT_WORLD_TRUTH"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PredictionContract:
    schema: str
    prediction_id: str
    target_id: str
    generation: int
    basis_fingerprint_sha256: str
    expected_projection_canonical_json: str

    def __post_init__(self) -> None:
        if self.schema != PREDICTION_CONTRACT_SCHEMA:
            raise PredictionContractError("prediction contract schema mismatch")
        _identifier("prediction_id", self.prediction_id)
        _identifier("target_id", self.target_id)
        _generation(self.generation)
        _sha256("basis_fingerprint_sha256", self.basis_fingerprint_sha256)
        if not isinstance(self.expected_projection_canonical_json, str):
            raise PredictionContractError("expected projection canonical JSON must be a string")
        try:
            parsed = json.loads(self.expected_projection_canonical_json)
        except json.JSONDecodeError as exc:
            raise PredictionContractError("expected projection JSON is invalid") from exc
        if _canonical_json(parsed) != self.expected_projection_canonical_json:
            raise PredictionContractError("expected projection JSON is not canonical")

    @classmethod
    def create(
        cls,
        *,
        prediction_id: str,
        target_id: str,
        generation: int,
        basis_fingerprint_sha256: str,
        expected_projection: Any,
    ) -> "PredictionContract":
        return cls(
            schema=PREDICTION_CONTRACT_SCHEMA,
            prediction_id=prediction_id,
            target_id=target_id,
            generation=generation,
            basis_fingerprint_sha256=basis_fingerprint_sha256,
            expected_projection_canonical_json=_canonical_json(expected_projection),
        )

    @property
    def expected_projection(self) -> Any:
        return json.loads(self.expected_projection_canonical_json)

    @property
    def expected_projection_sha256(self) -> str:
        return hashlib.sha256(
            self.expected_projection_canonical_json.encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "prediction_id": self.prediction_id,
            "target_id": self.target_id,
            "generation": self.generation,
            "basis_fingerprint_sha256": self.basis_fingerprint_sha256,
            "expected_projection": self.expected_projection,
            "expected_projection_sha256": self.expected_projection_sha256,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def observe(
        self,
        *,
        observation_id: str,
        observation_fingerprint_sha256: str,
        observed_projection: Any,
    ) -> PredictionResidual:
        observation_id = _identifier("observation_id", observation_id)
        observation_fingerprint_sha256 = _sha256(
            "observation_fingerprint_sha256", observation_fingerprint_sha256
        )
        _validate_json(observed_projection)
        expected = self.expected_projection
        out: dict[str, Any] = {
            "changed": [],
            "missing": [],
            "unexpected": [],
            "type_mismatch": [],
            "numeric": {},
        }
        compared_leaf_count = _compare(expected, observed_projection, "$", out)
        changed = tuple(sorted(set(out["changed"])))
        missing = tuple(sorted(set(out["missing"])))
        unexpected = tuple(sorted(set(out["unexpected"])))
        type_mismatch = tuple(sorted(set(out["type_mismatch"])))
        numeric = tuple(sorted(out["numeric"].items()))
        mismatch_count = len(changed) + len(missing) + len(unexpected)
        expected_leaf_count = _leaf_count(expected)
        observed_leaf_count = _leaf_count(observed_projection)
        comparison_opportunities = (
            compared_leaf_count + len(missing) + len(unexpected)
        )
        denominator = max(comparison_opportunities, 1)
        return PredictionResidual(
            schema=PREDICTION_RESIDUAL_SCHEMA,
            prediction_id=self.prediction_id,
            observation_id=observation_id,
            target_id=self.target_id,
            generation=self.generation,
            basis_fingerprint_sha256=self.basis_fingerprint_sha256,
            observation_fingerprint_sha256=observation_fingerprint_sha256,
            expected_projection_sha256=self.expected_projection_sha256,
            observed_projection_sha256=_digest_json(observed_projection),
            exact_match=mismatch_count == 0,
            changed_paths=changed,
            missing_paths=missing,
            unexpected_paths=unexpected,
            type_mismatch_paths=type_mismatch,
            numeric_absolute_residuals=numeric,
            numeric_l1=float(sum(value for _, value in numeric)),
            mismatch_count=mismatch_count,
            expected_leaf_count=expected_leaf_count,
            observed_leaf_count=observed_leaf_count,
            compared_leaf_count=compared_leaf_count,
            mismatch_fraction=mismatch_count / denominator,
        )


__all__ = [
    "PREDICTION_CONTRACT_SCHEMA",
    "PREDICTION_RESIDUAL_SCHEMA",
    "PredictionContract",
    "PredictionContractError",
    "PredictionResidual",
]
