"""Deterministic durable-state migration planning for Frankenstein 2.0.

F2-WP-1105 generation 1.

This module is deliberately plan-only. It validates explicit caller-supplied
state-root/lineage observations and emits a deterministic migration plan.
It does not touch the filesystem, inspect a host, mutate UnifiedDB, execute an
installer, authorize effects, or mint target/whole-system completion.

Core law:
    ONE_CANONICAL_STATE_LINEAGE
    DISPOSABLE_CACHE != CANONICAL_STATE_ROOT
    COPY != VERIFIED
    VERIFIED != SWITCHED
    SWITCHED != RESTART_SAFE
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any

ROOT_SCHEMA = "FRANKENSTEIN2_STATE_ROOT_IDENTITY/v1"
LINEAGE_SCHEMA = "FRANKENSTEIN2_STATE_LINEAGE/v1"
REQUEST_SCHEMA = "FRANKENSTEIN2_STATE_MIGRATION_REQUEST/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_STATE_MIGRATION_PLAN/v1"

STORAGE_CANONICAL_DURABLE = "CANONICAL_DURABLE"
STORAGE_DISPOSABLE_HOST_CACHE = "DISPOSABLE_HOST_CACHE"
STORAGE_ADAPTER_PRIVATE_CACHE = "ADAPTER_PRIVATE_CACHE"
_ALLOWED_STORAGE_CLASSES = frozenset(
    {
        STORAGE_CANONICAL_DURABLE,
        STORAGE_DISPOSABLE_HOST_CACHE,
        STORAGE_ADAPTER_PRIVATE_CACHE,
    }
)

TARGET_EMPTY_VERIFIED = "EMPTY_VERIFIED"
TARGET_SAME_LINEAGE_VERIFIED = "SAME_LINEAGE_VERIFIED"
TARGET_CONFLICTING_LINEAGE = "CONFLICTING_LINEAGE"
TARGET_UNKNOWN = "UNKNOWN"
_ALLOWED_TARGET_OBSERVATIONS = frozenset(
    {
        TARGET_EMPTY_VERIFIED,
        TARGET_SAME_LINEAGE_VERIFIED,
        TARGET_CONFLICTING_LINEAGE,
        TARGET_UNKNOWN,
    }
)

STEP_FREEZE_SOURCE = "FREEZE_SOURCE_READ_ONLY"
STEP_COPY = "COPY_TO_TARGET_STAGING"
STEP_VERIFY = "VERIFY_STAGING_STATE_DIGEST"
STEP_SWITCH = "SWITCH_CANONICAL_ROOT"
STEP_READBACK = "READBACK_CANONICAL_LINEAGE"
STEP_RETAIN_ROLLBACK = "RETAIN_SOURCE_AS_ROLLBACK"
_CANONICAL_STEPS = (
    STEP_FREEZE_SOURCE,
    STEP_COPY,
    STEP_VERIFY,
    STEP_SWITCH,
    STEP_READBACK,
    STEP_RETAIN_ROLLBACK,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_OBVIOUS_TRANSIENT_PREFIXES = (
    PurePosixPath("/tmp"),
    PurePosixPath("/var/tmp"),
    PurePosixPath("/run"),
    PurePosixPath("/dev/shm"),
)


class StateMigrationError(ValueError):
    """Fail-closed state migration planning error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise StateMigrationError(f"{name} must be a string")
    if not value or value != value.strip():
        raise StateMigrationError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise StateMigrationError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise StateMigrationError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise StateMigrationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise StateMigrationError(f"{name} must be a non-negative integer")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_absolute_path(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if not value.startswith("/"):
        raise StateMigrationError(f"{name} must be an absolute POSIX path")
    parsed = PurePosixPath(value)
    normalized = str(parsed)
    if normalized != value:
        raise StateMigrationError(f"{name} must already be normalized")
    if ".." in parsed.parts:
        raise StateMigrationError(f"{name} must not contain parent traversal")
    return value


def _is_obviously_transient(path: str) -> bool:
    parsed = PurePosixPath(path)
    if ".cache" in parsed.parts:
        return True
    for prefix in _OBVIOUS_TRANSIENT_PREFIXES:
        if parsed == prefix or prefix in parsed.parents:
            return True
    return False


@dataclass(frozen=True, slots=True)
class StateRootIdentity:
    schema: str
    root_id: str
    path: str
    storage_class: str
    host_identity_sha256: str
    observed_root_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema != ROOT_SCHEMA:
            raise StateMigrationError("state root schema mismatch")
        object.__setattr__(self, "root_id", _identifier("root_id", self.root_id))
        object.__setattr__(self, "path", _normalized_absolute_path("path", self.path))
        if self.storage_class not in _ALLOWED_STORAGE_CLASSES:
            raise StateMigrationError(f"unsupported storage_class: {self.storage_class!r}")
        object.__setattr__(
            self,
            "host_identity_sha256",
            _sha256("host_identity_sha256", self.host_identity_sha256),
        )
        object.__setattr__(
            self,
            "observed_root_fingerprint_sha256",
            _sha256(
                "observed_root_fingerprint_sha256",
                self.observed_root_fingerprint_sha256,
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        root_id: str,
        path: str,
        storage_class: str,
        host_identity_sha256: str,
        observed_root_fingerprint_sha256: str,
    ) -> "StateRootIdentity":
        return cls(
            schema=ROOT_SCHEMA,
            root_id=root_id,
            path=path,
            storage_class=storage_class,
            host_identity_sha256=host_identity_sha256,
            observed_root_fingerprint_sha256=observed_root_fingerprint_sha256,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def assert_eligible_canonical_root(self, *, role: str) -> None:
        if self.storage_class != STORAGE_CANONICAL_DURABLE:
            raise StateMigrationError(
                f"{role} must be classified CANONICAL_DURABLE, got {self.storage_class}"
            )
        if _is_obviously_transient(self.path):
            raise StateMigrationError(
                f"{role} path is mechanically transient/cache-like and cannot be canonical"
            )


def _revalidate_root(value: Any, *, role: str) -> StateRootIdentity:
    if type(value) is not StateRootIdentity:
        raise StateMigrationError(f"{role} must be exact StateRootIdentity")
    return StateRootIdentity(
        schema=value.schema,
        root_id=value.root_id,
        path=value.path,
        storage_class=value.storage_class,
        host_identity_sha256=value.host_identity_sha256,
        observed_root_fingerprint_sha256=value.observed_root_fingerprint_sha256,
    )


@dataclass(frozen=True, slots=True)
class StateLineage:
    schema: str
    lineage_id: str
    generation: int
    state_sha256: str
    root: StateRootIdentity

    def __post_init__(self) -> None:
        if self.schema != LINEAGE_SCHEMA:
            raise StateMigrationError("state lineage schema mismatch")
        object.__setattr__(self, "lineage_id", _identifier("lineage_id", self.lineage_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        object.__setattr__(self, "state_sha256", _sha256("state_sha256", self.state_sha256))
        root = _revalidate_root(self.root, role="lineage root")
        root.assert_eligible_canonical_root(role="lineage root")
        object.__setattr__(self, "root", root)

    @classmethod
    def create(
        cls,
        *,
        lineage_id: str,
        generation: int,
        state_sha256: str,
        root: StateRootIdentity,
    ) -> "StateLineage":
        return cls(
            schema=LINEAGE_SCHEMA,
            lineage_id=lineage_id,
            generation=generation,
            state_sha256=state_sha256,
            root=root,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "lineage_id": self.lineage_id,
            "generation": self.generation,
            "state_sha256": self.state_sha256,
            "root": self.root.as_dict(),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _revalidate_lineage(value: Any) -> StateLineage:
    if type(value) is not StateLineage:
        raise StateMigrationError("source_lineage must be exact StateLineage")
    return StateLineage(
        schema=value.schema,
        lineage_id=value.lineage_id,
        generation=value.generation,
        state_sha256=value.state_sha256,
        root=_revalidate_root(value.root, role="source lineage root"),
    )


@dataclass(frozen=True, slots=True)
class TargetRootObservation:
    status: str
    observed_lineage_id: str | None = None
    observed_generation: int | None = None
    observed_state_sha256: str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_TARGET_OBSERVATIONS:
            raise StateMigrationError(f"unsupported target observation: {self.status!r}")

        if self.status == TARGET_EMPTY_VERIFIED:
            if any(
                value is not None
                for value in (
                    self.observed_lineage_id,
                    self.observed_generation,
                    self.observed_state_sha256,
                )
            ):
                raise StateMigrationError(
                    "EMPTY_VERIFIED target must not carry lineage/generation/state observations"
                )
            if self.evidence_ref is None:
                raise StateMigrationError("EMPTY_VERIFIED target requires evidence_ref")

        elif self.status == TARGET_SAME_LINEAGE_VERIFIED:
            object.__setattr__(
                self,
                "observed_lineage_id",
                _identifier("observed_lineage_id", self.observed_lineage_id),
            )
            object.__setattr__(
                self,
                "observed_generation",
                _generation("observed_generation", self.observed_generation),
            )
            object.__setattr__(
                self,
                "observed_state_sha256",
                _sha256("observed_state_sha256", self.observed_state_sha256),
            )
            if self.evidence_ref is None:
                raise StateMigrationError("SAME_LINEAGE_VERIFIED target requires evidence_ref")

        elif self.status == TARGET_CONFLICTING_LINEAGE:
            if self.observed_lineage_id is not None:
                object.__setattr__(
                    self,
                    "observed_lineage_id",
                    _identifier("observed_lineage_id", self.observed_lineage_id),
                )
            if self.observed_generation is not None:
                object.__setattr__(
                    self,
                    "observed_generation",
                    _generation("observed_generation", self.observed_generation),
                )
            if self.observed_state_sha256 is not None:
                object.__setattr__(
                    self,
                    "observed_state_sha256",
                    _sha256("observed_state_sha256", self.observed_state_sha256),
                )
            if self.evidence_ref is None:
                raise StateMigrationError("CONFLICTING_LINEAGE target requires evidence_ref")

        else:  # UNKNOWN
            if any(
                value is not None
                for value in (
                    self.observed_lineage_id,
                    self.observed_generation,
                    self.observed_state_sha256,
                    self.evidence_ref,
                )
            ):
                raise StateMigrationError(
                    "UNKNOWN target observation must not masquerade as observed evidence"
                )

        if self.evidence_ref is not None:
            object.__setattr__(
                self, "evidence_ref", _identifier("evidence_ref", self.evidence_ref)
            )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _revalidate_target_observation(value: Any) -> TargetRootObservation:
    if type(value) is not TargetRootObservation:
        raise StateMigrationError(
            "target_observation must be exact TargetRootObservation"
        )
    return TargetRootObservation(
        status=value.status,
        observed_lineage_id=value.observed_lineage_id,
        observed_generation=value.observed_generation,
        observed_state_sha256=value.observed_state_sha256,
        evidence_ref=value.evidence_ref,
    )


@dataclass(frozen=True, slots=True)
class StateMigrationRequest:
    schema: str
    migration_id: str
    source_lineage: StateLineage
    target_root: StateRootIdentity
    target_observation: TargetRootObservation
    rollback_root: StateRootIdentity
    expected_source_lineage_sha256: str
    expected_source_root_sha256: str
    expected_target_root_sha256: str
    expected_rollback_root_sha256: str

    def __post_init__(self) -> None:
        if self.schema != REQUEST_SCHEMA:
            raise StateMigrationError("state migration request schema mismatch")
        object.__setattr__(
            self, "migration_id", _identifier("migration_id", self.migration_id)
        )

        source = _revalidate_lineage(self.source_lineage)
        target = _revalidate_root(self.target_root, role="target root")
        rollback = _revalidate_root(self.rollback_root, role="rollback root")
        observation = _revalidate_target_observation(self.target_observation)

        source.root.assert_eligible_canonical_root(role="source root")
        target.assert_eligible_canonical_root(role="target root")
        rollback.assert_eligible_canonical_root(role="rollback root")

        if target.sha256() == source.root.sha256():
            raise StateMigrationError("target root must differ from source root")
        if rollback.sha256() != source.root.sha256():
            raise StateMigrationError(
                "generation-1 plan requires rollback_root to be the exact source root"
            )
        if target.host_identity_sha256 != source.root.host_identity_sha256:
            raise StateMigrationError(
                "source and target roots must bind the same explicit host identity"
            )

        object.__setattr__(self, "source_lineage", source)
        object.__setattr__(self, "target_root", target)
        object.__setattr__(self, "rollback_root", rollback)
        object.__setattr__(self, "target_observation", observation)

        expected_source_lineage = _sha256(
            "expected_source_lineage_sha256", self.expected_source_lineage_sha256
        )
        expected_source_root = _sha256(
            "expected_source_root_sha256", self.expected_source_root_sha256
        )
        expected_target_root = _sha256(
            "expected_target_root_sha256", self.expected_target_root_sha256
        )
        expected_rollback_root = _sha256(
            "expected_rollback_root_sha256", self.expected_rollback_root_sha256
        )

        if expected_source_lineage != source.sha256():
            raise StateMigrationError("source lineage digest fence mismatch")
        if expected_source_root != source.root.sha256():
            raise StateMigrationError("source root digest fence mismatch")
        if expected_target_root != target.sha256():
            raise StateMigrationError("target root digest fence mismatch")
        if expected_rollback_root != rollback.sha256():
            raise StateMigrationError("rollback root digest fence mismatch")

        object.__setattr__(
            self, "expected_source_lineage_sha256", expected_source_lineage
        )
        object.__setattr__(self, "expected_source_root_sha256", expected_source_root)
        object.__setattr__(self, "expected_target_root_sha256", expected_target_root)
        object.__setattr__(
            self, "expected_rollback_root_sha256", expected_rollback_root
        )

        self._validate_target_prestate()

    def _validate_target_prestate(self) -> None:
        obs = self.target_observation
        source = self.source_lineage

        if obs.status == TARGET_UNKNOWN:
            raise StateMigrationError(
                "target root prestate is UNKNOWN; refuse silent second-lineage creation"
            )
        if obs.status == TARGET_CONFLICTING_LINEAGE:
            raise StateMigrationError(
                "target root contains a conflicting lineage; explicit reconciliation required"
            )
        if obs.status == TARGET_SAME_LINEAGE_VERIFIED:
            if obs.observed_lineage_id != source.lineage_id:
                raise StateMigrationError(
                    "SAME_LINEAGE_VERIFIED observation lineage_id does not match source"
                )
            assert obs.observed_generation is not None
            assert obs.observed_state_sha256 is not None
            if obs.observed_generation > source.generation:
                raise StateMigrationError(
                    "target contains a newer lineage generation; refuse overwrite"
                )
            if (
                obs.observed_generation == source.generation
                and obs.observed_state_sha256 != source.state_sha256
            ):
                raise StateMigrationError(
                    "same-generation target state digest conflicts with source"
                )

    @classmethod
    def create(
        cls,
        *,
        migration_id: str,
        source_lineage: StateLineage,
        target_root: StateRootIdentity,
        target_observation: TargetRootObservation,
        rollback_root: StateRootIdentity,
    ) -> "StateMigrationRequest":
        source = _revalidate_lineage(source_lineage)
        target = _revalidate_root(target_root, role="target root")
        rollback = _revalidate_root(rollback_root, role="rollback root")
        return cls(
            schema=REQUEST_SCHEMA,
            migration_id=migration_id,
            source_lineage=source,
            target_root=target,
            target_observation=_revalidate_target_observation(target_observation),
            rollback_root=rollback,
            expected_source_lineage_sha256=source.sha256(),
            expected_source_root_sha256=source.root.sha256(),
            expected_target_root_sha256=target.sha256(),
            expected_rollback_root_sha256=rollback.sha256(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "source_lineage": self.source_lineage.as_dict(),
            "target_root": self.target_root.as_dict(),
            "target_observation": self.target_observation.as_dict(),
            "rollback_root": self.rollback_root.as_dict(),
            "expected_source_lineage_sha256": self.expected_source_lineage_sha256,
            "expected_source_root_sha256": self.expected_source_root_sha256,
            "expected_target_root_sha256": self.expected_target_root_sha256,
            "expected_rollback_root_sha256": self.expected_rollback_root_sha256,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _revalidate_request(value: Any) -> StateMigrationRequest:
    if type(value) is not StateMigrationRequest:
        raise StateMigrationError("request must be exact StateMigrationRequest")
    return StateMigrationRequest(
        schema=value.schema,
        migration_id=value.migration_id,
        source_lineage=_revalidate_lineage(value.source_lineage),
        target_root=_revalidate_root(value.target_root, role="target root"),
        target_observation=_revalidate_target_observation(value.target_observation),
        rollback_root=_revalidate_root(value.rollback_root, role="rollback root"),
        expected_source_lineage_sha256=value.expected_source_lineage_sha256,
        expected_source_root_sha256=value.expected_source_root_sha256,
        expected_target_root_sha256=value.expected_target_root_sha256,
        expected_rollback_root_sha256=value.expected_rollback_root_sha256,
    )


@dataclass(frozen=True, slots=True)
class StateMigrationPlan:
    schema: str
    migration_id: str
    request_sha256: str
    lineage_id: str
    generation: int
    state_sha256: str
    source_root_sha256: str
    target_root_sha256: str
    rollback_root_sha256: str
    steps: tuple[str, ...]
    acceptance_requirements: tuple[str, ...]
    classification: str = (
        "PLAN_ONLY_NOT_FILESYSTEM_UNIFIEDDB_EFFECT_OR_COMPLETION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        if self.schema != PLAN_SCHEMA:
            raise StateMigrationError("state migration plan schema mismatch")
        if self.steps != _CANONICAL_STEPS:
            raise StateMigrationError("state migration steps must match canonical order")

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = list(self.steps)
        data["acceptance_requirements"] = list(self.acceptance_requirements)
        return data

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def build_state_migration_plan(request: StateMigrationRequest) -> StateMigrationPlan:
    """Revalidate current object content and emit a deterministic non-executing plan."""

    current = _revalidate_request(request)
    source = current.source_lineage

    acceptance_requirements = (
        "SOURCE_REMAINS_INTACT_UNTIL_TARGET_READBACK_VERIFIED",
        "STAGED_COPY_STATE_SHA256_EQUALS_EXPECTED_SOURCE_STATE_SHA256",
        "TARGET_CANONICAL_ROOT_BINDS_SAME_LINEAGE_ID",
        "TARGET_CANONICAL_ROOT_BINDS_SAME_OR_EXPLICITLY_MIGRATED_GENERATION",
        "POST_SWITCH_DURABLE_READBACK_REQUIRED",
        "ROLLBACK_ROOT_REMAINS_EXACT_SOURCE_ROOT_UNTIL_ACCEPTANCE",
        "FILES_COPIED_OR_ZERO_EXIT_CODE_NEVER_EQUALS_COMPLETION",
    )

    return StateMigrationPlan(
        schema=PLAN_SCHEMA,
        migration_id=current.migration_id,
        request_sha256=current.sha256(),
        lineage_id=source.lineage_id,
        generation=source.generation,
        state_sha256=source.state_sha256,
        source_root_sha256=source.root.sha256(),
        target_root_sha256=current.target_root.sha256(),
        rollback_root_sha256=current.rollback_root.sha256(),
        steps=_CANONICAL_STEPS,
        acceptance_requirements=acceptance_requirements,
    )
