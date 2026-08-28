"""Bounded Stage-2 Persistent Agency Kernel integration for Frankenstein 2.0.

F2-WP-206 generation 1.

The kernel composes accepted persistent-agency components and stores typed checkpoints only
inside an already-existing, fingerprint-bound canonical UnifiedDB. It does not create a DB,
infer goals/world facts, select an action, auto-resume, invoke providers/tools, authorize an
effect, or mint completion.

A checkpoint may preserve a non-CANDIDATE GoalState produced by validated lifecycle evolution,
but public replay of such a goal deliberately fails closed until a separate admitted goal
rehydration contract exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable

from frankenstein2.agency_state import (
    AGENCY_STATE_SCHEMA,
    AgencyState,
    DeferredIntent,
    Interest,
    OpenLoop,
)
from frankenstein2.goal_lifecycle import (
    GOAL_CANDIDATE,
    GOAL_STATE_SCHEMA,
    GoalRecord,
    GoalState,
)
from frankenstein2.persistent_pulse import PulseDecision
from frankenstein2.state_fingerprint import StateFingerprint, fingerprint_state_projection
from frankenstein2.wake_hold import HoldCheckpoint, WakeEvaluation
from state.unifieddb_identity import (
    FINGERPRINT_SCHEMA,
    RESOLUTION_SCHEMA,
    UnifiedDBFingerprint,
    UnifiedDBResolution,
)

CHECKPOINT_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_CHECKPOINT/v1"
WRITE_RECEIPT_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_WRITE_RECEIPT/v1"
PROJECTION_SCHEMA = "FRANKENSTEIN2_PERSISTENT_AGENCY_PROJECTION/v1"
TABLE_NAME = "frankenstein2_persistent_agency_checkpoints"
CLASSIFICATION = "TYPED_PERSISTENT_AGENCY_CHECKPOINT_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512


class PersistentAgencyIntegrationError(RuntimeError):
    """Fail-closed integration/persistence contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise PersistentAgencyIntegrationError(f"{name} must be a string")
    if not value or value != value.strip():
        raise PersistentAgencyIntegrationError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise PersistentAgencyIntegrationError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PersistentAgencyIntegrationError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PersistentAgencyIntegrationError("integration_generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PersistentAgencyIntegrationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _optional_sha256(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _sha256(name, value)


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PersistentAgencyIntegrationError("provenance_refs must be an iterable of strings")
    checked = tuple(_identifier("provenance_ref", value) for value in values)
    if not checked:
        raise PersistentAgencyIntegrationError("provenance_refs must not be empty")
    if len(set(checked)) != len(checked):
        raise PersistentAgencyIntegrationError("provenance_refs contain duplicate references")
    return tuple(sorted(checked))


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest_json_text(text: str) -> str:
    if not isinstance(text, str):
        raise PersistentAgencyIntegrationError("checkpoint component payload must be JSON text")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PersistentAgencyIntegrationError("checkpoint component payload is not valid JSON") from exc
    canonical = _canonical_json(value)
    if canonical != text:
        raise PersistentAgencyIntegrationError("checkpoint component payload is not canonical JSON")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def _projection_without_generation(
    agency_payload: dict[str, Any], goal_payload: dict[str, Any]
) -> dict[str, Any]:
    agency_projection = dict(agency_payload)
    goal_projection = dict(goal_payload)
    agency_projection.pop("generation", None)
    goal_projection.pop("generation", None)
    return {"agency_state": agency_projection, "goal_state": goal_projection}


@dataclass(frozen=True, slots=True)
class PersistentAgencyCheckpoint:
    schema: str
    kernel_id: str
    integration_generation: int
    parent_checkpoint_sha256: str | None
    agency_state_json: str
    agency_state_sha256: str
    goal_state_json: str
    goal_state_sha256: str
    state_fingerprint_json: str
    state_fingerprint_sha256: str
    pulse_decision_json: str
    pulse_decision_sha256: str
    hold_checkpoint_json: str | None
    hold_checkpoint_sha256: str | None
    wake_evaluation_json: str | None
    wake_evaluation_sha256: str | None
    provenance_refs: tuple[str, ...]
    classification: str = CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != CHECKPOINT_SCHEMA:
            raise PersistentAgencyIntegrationError("persistent agency checkpoint schema mismatch")
        object.__setattr__(self, "kernel_id", _identifier("kernel_id", self.kernel_id))
        object.__setattr__(self, "integration_generation", _generation(self.integration_generation))
        object.__setattr__(
            self,
            "parent_checkpoint_sha256",
            _optional_sha256("parent_checkpoint_sha256", self.parent_checkpoint_sha256),
        )
        if self.integration_generation == 0 and self.parent_checkpoint_sha256 is not None:
            raise PersistentAgencyIntegrationError("generation zero must not carry a parent checkpoint")
        if self.integration_generation > 0 and self.parent_checkpoint_sha256 is None:
            raise PersistentAgencyIntegrationError("nonzero generation requires parent_checkpoint_sha256")

        for field_name in (
            "agency_state_sha256",
            "goal_state_sha256",
            "state_fingerprint_sha256",
            "pulse_decision_sha256",
        ):
            object.__setattr__(self, field_name, _sha256(field_name, getattr(self, field_name)))
        object.__setattr__(
            self,
            "hold_checkpoint_sha256",
            _optional_sha256("hold_checkpoint_sha256", self.hold_checkpoint_sha256),
        )
        object.__setattr__(
            self,
            "wake_evaluation_sha256",
            _optional_sha256("wake_evaluation_sha256", self.wake_evaluation_sha256),
        )
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))
        if self.classification != CLASSIFICATION:
            raise PersistentAgencyIntegrationError("persistent agency classification mismatch")

        if _digest_json_text(self.agency_state_json) != self.agency_state_sha256:
            raise PersistentAgencyIntegrationError("agency_state_sha256 does not bind agency_state_json")
        if _digest_json_text(self.goal_state_json) != self.goal_state_sha256:
            raise PersistentAgencyIntegrationError("goal_state_sha256 does not bind goal_state_json")
        if _digest_json_text(self.state_fingerprint_json) != self.state_fingerprint_sha256:
            raise PersistentAgencyIntegrationError("state_fingerprint_sha256 does not bind fingerprint JSON")
        if _digest_json_text(self.pulse_decision_json) != self.pulse_decision_sha256:
            raise PersistentAgencyIntegrationError("pulse_decision_sha256 does not bind pulse JSON")

        if (self.hold_checkpoint_json is None) != (self.hold_checkpoint_sha256 is None):
            raise PersistentAgencyIntegrationError("hold checkpoint JSON/digest presence mismatch")
        if self.hold_checkpoint_json is not None:
            if _digest_json_text(self.hold_checkpoint_json) != self.hold_checkpoint_sha256:
                raise PersistentAgencyIntegrationError("hold_checkpoint_sha256 does not bind hold JSON")

        if (self.wake_evaluation_json is None) != (self.wake_evaluation_sha256 is None):
            raise PersistentAgencyIntegrationError("wake evaluation JSON/digest presence mismatch")
        if self.wake_evaluation_json is not None:
            if self.hold_checkpoint_json is None:
                raise PersistentAgencyIntegrationError("wake evaluation requires an explicit hold checkpoint")
            if _digest_json_text(self.wake_evaluation_json) != self.wake_evaluation_sha256:
                raise PersistentAgencyIntegrationError("wake_evaluation_sha256 does not bind wake JSON")

        self._validate_internal_bindings()

    def _validate_internal_bindings(self) -> None:
        agency = json.loads(self.agency_state_json)
        goal = json.loads(self.goal_state_json)
        fingerprint = json.loads(self.state_fingerprint_json)
        pulse = json.loads(self.pulse_decision_json)
        if agency.get("schema") != AGENCY_STATE_SCHEMA:
            raise PersistentAgencyIntegrationError("persisted agency state schema mismatch")
        if goal.get("schema") != GOAL_STATE_SCHEMA:
            raise PersistentAgencyIntegrationError("persisted goal state schema mismatch")
        if pulse.get("state_id") != agency.get("state_id"):
            raise PersistentAgencyIntegrationError("pulse/agency state_id mismatch")
        if pulse.get("generation") != agency.get("generation"):
            raise PersistentAgencyIntegrationError("pulse/agency generation mismatch")
        if pulse.get("state_digest_sha256") != self.agency_state_sha256:
            raise PersistentAgencyIntegrationError("pulse/agency digest mismatch")

        projection = _projection_without_generation(agency, goal)
        expected_fp = fingerprint_state_projection(
            projection_schema=PROJECTION_SCHEMA,
            generation=self.integration_generation,
            projection=projection,
        )
        if fingerprint != expected_fp.as_dict():
            raise PersistentAgencyIntegrationError("state fingerprint does not match integrated projection")

        if self.hold_checkpoint_json is not None:
            hold = json.loads(self.hold_checkpoint_json)
            if hold.get("state_id") != agency.get("state_id"):
                raise PersistentAgencyIntegrationError("hold/agency state_id mismatch")
            if hold.get("generation") != agency.get("generation"):
                raise PersistentAgencyIntegrationError("hold/agency generation mismatch")
            if hold.get("state_sha256") != self.agency_state_sha256:
                raise PersistentAgencyIntegrationError("hold/agency digest mismatch")

        if self.wake_evaluation_json is not None:
            wake = json.loads(self.wake_evaluation_json)
            if wake.get("checkpoint_sha256") != self.hold_checkpoint_sha256:
                raise PersistentAgencyIntegrationError("wake/hold checkpoint digest mismatch")
            if wake.get("observed_state_id") != agency.get("state_id"):
                raise PersistentAgencyIntegrationError("wake/agency state_id mismatch")
            if wake.get("observed_generation") != agency.get("generation"):
                raise PersistentAgencyIntegrationError("wake/agency generation mismatch")
            if wake.get("observed_state_sha256") != self.agency_state_sha256:
                raise PersistentAgencyIntegrationError("wake/agency digest mismatch")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PersistentAgencyCheckpoint":
        if not isinstance(value, dict):
            raise PersistentAgencyIntegrationError("checkpoint payload must be an object")
        expected = {
            "schema",
            "kernel_id",
            "integration_generation",
            "parent_checkpoint_sha256",
            "agency_state_json",
            "agency_state_sha256",
            "goal_state_json",
            "goal_state_sha256",
            "state_fingerprint_json",
            "state_fingerprint_sha256",
            "pulse_decision_json",
            "pulse_decision_sha256",
            "hold_checkpoint_json",
            "hold_checkpoint_sha256",
            "wake_evaluation_json",
            "wake_evaluation_sha256",
            "provenance_refs",
            "classification",
        }
        if set(value) != expected:
            raise PersistentAgencyIntegrationError("checkpoint payload field set mismatch")
        return cls(
            schema=value["schema"],
            kernel_id=value["kernel_id"],
            integration_generation=value["integration_generation"],
            parent_checkpoint_sha256=value["parent_checkpoint_sha256"],
            agency_state_json=value["agency_state_json"],
            agency_state_sha256=value["agency_state_sha256"],
            goal_state_json=value["goal_state_json"],
            goal_state_sha256=value["goal_state_sha256"],
            state_fingerprint_json=value["state_fingerprint_json"],
            state_fingerprint_sha256=value["state_fingerprint_sha256"],
            pulse_decision_json=value["pulse_decision_json"],
            pulse_decision_sha256=value["pulse_decision_sha256"],
            hold_checkpoint_json=value["hold_checkpoint_json"],
            hold_checkpoint_sha256=value["hold_checkpoint_sha256"],
            wake_evaluation_json=value["wake_evaluation_json"],
            wake_evaluation_sha256=value["wake_evaluation_sha256"],
            provenance_refs=tuple(value["provenance_refs"]),
            classification=value["classification"],
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def state_fingerprint(self) -> StateFingerprint:
        return StateFingerprint(**json.loads(self.state_fingerprint_json))


@dataclass(frozen=True, slots=True)
class CheckpointWriteReceipt:
    schema: str
    kernel_id: str
    integration_generation: int
    checkpoint_sha256: str
    db_path: str
    resolution_source: str
    unifieddb_authority_receipt_sha256: str
    status: str
    classification: str = "SQLITE_CHECKPOINT_WRITE_RECEIPT_NOT_EFFECT_OR_COMPLETION"

    def __post_init__(self) -> None:
        if self.schema != WRITE_RECEIPT_SCHEMA:
            raise PersistentAgencyIntegrationError("checkpoint write receipt schema mismatch")
        object.__setattr__(self, "kernel_id", _identifier("kernel_id", self.kernel_id))
        object.__setattr__(self, "integration_generation", _generation(self.integration_generation))
        object.__setattr__(self, "checkpoint_sha256", _sha256("checkpoint_sha256", self.checkpoint_sha256))
        if not isinstance(self.db_path, str) or not Path(self.db_path).is_absolute():
            raise PersistentAgencyIntegrationError("write receipt db_path must be absolute")
        object.__setattr__(self, "resolution_source", _identifier("resolution_source", self.resolution_source))
        object.__setattr__(
            self,
            "unifieddb_authority_receipt_sha256",
            _sha256("unifieddb_authority_receipt_sha256", self.unifieddb_authority_receipt_sha256),
        )
        if self.status not in {"INSERTED", "IDEMPOTENT_ALREADY_PRESENT"}:
            raise PersistentAgencyIntegrationError("unsupported checkpoint write status")
        if self.classification != "SQLITE_CHECKPOINT_WRITE_RECEIPT_NOT_EFFECT_OR_COMPLETION":
            raise PersistentAgencyIntegrationError("checkpoint write receipt classification mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def build_checkpoint(
    *,
    kernel_id: str,
    integration_generation: int,
    parent_checkpoint_sha256: str | None,
    agency_state: AgencyState,
    goal_state: GoalState,
    pulse_decision: PulseDecision,
    provenance_refs: Iterable[str],
    hold_checkpoint: HoldCheckpoint | None = None,
    wake_evaluation: WakeEvaluation | None = None,
) -> PersistentAgencyCheckpoint:
    if not isinstance(agency_state, AgencyState):
        raise PersistentAgencyIntegrationError("agency_state must be AgencyState")
    if not isinstance(goal_state, GoalState):
        raise PersistentAgencyIntegrationError("goal_state must be GoalState")
    if not isinstance(pulse_decision, PulseDecision):
        raise PersistentAgencyIntegrationError("pulse_decision must be PulseDecision")
    if hold_checkpoint is not None and not isinstance(hold_checkpoint, HoldCheckpoint):
        raise PersistentAgencyIntegrationError("hold_checkpoint must be HoldCheckpoint or None")
    if wake_evaluation is not None and not isinstance(wake_evaluation, WakeEvaluation):
        raise PersistentAgencyIntegrationError("wake_evaluation must be WakeEvaluation or None")
    if wake_evaluation is not None and hold_checkpoint is None:
        raise PersistentAgencyIntegrationError("wake_evaluation requires hold_checkpoint")

    agency_json = agency_state.canonical_json()
    goal_json = goal_state.canonical_json()
    agency_sha = agency_state.sha256()
    goal_sha = goal_state.sha256()
    if pulse_decision.state_id != agency_state.state_id:
        raise PersistentAgencyIntegrationError("pulse/agency state_id mismatch")
    if pulse_decision.generation != agency_state.generation:
        raise PersistentAgencyIntegrationError("pulse/agency generation mismatch")
    if pulse_decision.state_digest_sha256 != agency_sha:
        raise PersistentAgencyIntegrationError("pulse/agency digest mismatch")

    if hold_checkpoint is not None:
        if hold_checkpoint.state_id != agency_state.state_id:
            raise PersistentAgencyIntegrationError("hold/agency state_id mismatch")
        if hold_checkpoint.generation != agency_state.generation:
            raise PersistentAgencyIntegrationError("hold/agency generation mismatch")
        if hold_checkpoint.state_sha256 != agency_sha:
            raise PersistentAgencyIntegrationError("hold/agency digest mismatch")

    if wake_evaluation is not None:
        assert hold_checkpoint is not None
        if wake_evaluation.checkpoint_sha256 != hold_checkpoint.sha256():
            raise PersistentAgencyIntegrationError("wake/hold checkpoint digest mismatch")
        if wake_evaluation.observed_state_id != agency_state.state_id:
            raise PersistentAgencyIntegrationError("wake/agency state_id mismatch")
        if wake_evaluation.observed_generation != agency_state.generation:
            raise PersistentAgencyIntegrationError("wake/agency generation mismatch")
        if wake_evaluation.observed_state_sha256 != agency_sha:
            raise PersistentAgencyIntegrationError("wake/agency digest mismatch")

    agency_payload = json.loads(agency_json)
    goal_payload = json.loads(goal_json)
    projection = _projection_without_generation(agency_payload, goal_payload)
    fingerprint = fingerprint_state_projection(
        projection_schema=PROJECTION_SCHEMA,
        generation=integration_generation,
        projection=projection,
    )
    fp_json = _canonical_json(fingerprint.as_dict())
    pulse_json = pulse_decision.canonical_json()
    hold_json = None if hold_checkpoint is None else hold_checkpoint.canonical_json()
    wake_json = None if wake_evaluation is None else wake_evaluation.canonical_json()

    return PersistentAgencyCheckpoint(
        schema=CHECKPOINT_SCHEMA,
        kernel_id=kernel_id,
        integration_generation=integration_generation,
        parent_checkpoint_sha256=parent_checkpoint_sha256,
        agency_state_json=agency_json,
        agency_state_sha256=agency_sha,
        goal_state_json=goal_json,
        goal_state_sha256=goal_sha,
        state_fingerprint_json=fp_json,
        state_fingerprint_sha256=hashlib.sha256(fp_json.encode("utf-8")).hexdigest(),
        pulse_decision_json=pulse_json,
        pulse_decision_sha256=pulse_decision.sha256(),
        hold_checkpoint_json=hold_json,
        hold_checkpoint_sha256=None if hold_checkpoint is None else hold_checkpoint.sha256(),
        wake_evaluation_json=wake_json,
        wake_evaluation_sha256=None if wake_evaluation is None else wake_evaluation.sha256(),
        provenance_refs=tuple(provenance_refs),
    )


def rehydrate_agency_state(checkpoint: PersistentAgencyCheckpoint) -> AgencyState:
    """Rehydrate AgencyState through its public validated constructors only."""
    if not isinstance(checkpoint, PersistentAgencyCheckpoint):
        raise PersistentAgencyIntegrationError("checkpoint must be PersistentAgencyCheckpoint")
    payload = json.loads(checkpoint.agency_state_json)
    interests = tuple(Interest(**item) for item in payload.get("interests", ()))
    loops = tuple(OpenLoop(**item) for item in payload.get("open_loops", ()))
    intents = tuple(DeferredIntent(**item) for item in payload.get("deferred_intents", ()))
    state = AgencyState.create(
        state_id=payload.get("state_id"),
        generation=payload.get("generation"),
        interests=interests,
        open_loops=loops,
        deferred_intents=intents,
    )
    if state.canonical_json() != checkpoint.agency_state_json:
        raise PersistentAgencyIntegrationError("rehydrated AgencyState does not match persisted payload")
    return state


def rehydrate_candidate_goal_state(checkpoint: PersistentAgencyCheckpoint) -> GoalState:
    """Replay candidate-only GoalState through the public lifecycle constructor."""
    if not isinstance(checkpoint, PersistentAgencyCheckpoint):
        raise PersistentAgencyIntegrationError("checkpoint must be PersistentAgencyCheckpoint")
    payload = json.loads(checkpoint.goal_state_json)
    goals: list[GoalRecord] = []
    for item in payload.get("goals", ()):
        if item.get("status") != GOAL_CANDIDATE:
            raise PersistentAgencyIntegrationError(
                "NONCANDIDATE_GOAL_REHYDRATION_REQUIRES_SEPARATE_CONTRACT"
            )
        goals.append(
            GoalRecord.candidate(
                goal_id=item.get("goal_id"),
                summary=item.get("summary"),
                priority_ppm=item.get("priority_ppm"),
                provenance_refs=tuple(item.get("provenance_refs", ())),
            )
        )
    state = GoalState.create(
        state_id=payload.get("state_id"),
        generation=payload.get("generation"),
        goals=goals,
    )
    if state.canonical_json() != checkpoint.goal_state_json:
        raise PersistentAgencyIntegrationError("rehydrated candidate GoalState does not match persisted payload")
    return state


class PersistentAgencyStore:
    """Append-only checkpoint lane inside one fingerprint-bound canonical UnifiedDB."""

    def __init__(
        self,
        resolution: UnifiedDBResolution,
        fingerprint: UnifiedDBFingerprint,
    ) -> None:
        if not isinstance(resolution, UnifiedDBResolution):
            raise PersistentAgencyIntegrationError("resolution must be UnifiedDBResolution")
        if not isinstance(fingerprint, UnifiedDBFingerprint):
            raise PersistentAgencyIntegrationError("fingerprint must be UnifiedDBFingerprint")
        if resolution.schema != RESOLUTION_SCHEMA:
            raise PersistentAgencyIntegrationError("UnifiedDB resolution schema mismatch")
        if fingerprint.schema != FINGERPRINT_SCHEMA:
            raise PersistentAgencyIntegrationError("UnifiedDB fingerprint schema mismatch")
        if not resolution.exists_at_resolution:
            raise PersistentAgencyIntegrationError("canonical UnifiedDB must exist before WP206 writer open")
        if not fingerprint.exists or fingerprint.status != "SQLITE3_REGULAR_FILE":
            raise PersistentAgencyIntegrationError("UnifiedDB fingerprint is not an existing SQLite identity")
        if not fingerprint.real_path:
            raise PersistentAgencyIntegrationError("UnifiedDB fingerprint real_path missing")
        if not _same_real_path(resolution.path, fingerprint.real_path):
            raise PersistentAgencyIntegrationError("UnifiedDB resolution/fingerprint path mismatch")
        if fingerprint.device is None or fingerprint.inode is None:
            raise PersistentAgencyIntegrationError("UnifiedDB fingerprint file identity missing")

        self.resolution = resolution
        self.fingerprint = fingerprint
        self.path = Path(fingerprint.real_path)
        self.authority_receipt_sha256 = fingerprint.receipt_sha256()
        self._assert_current_file_identity()

    def _assert_current_file_identity(self) -> None:
        try:
            current = self.path.stat()
        except OSError as exc:
            raise PersistentAgencyIntegrationError("canonical UnifiedDB missing at WP206 access") from exc
        if (current.st_dev, current.st_ino) != (self.fingerprint.device, self.fingerprint.inode):
            raise PersistentAgencyIntegrationError("canonical UnifiedDB replaced after fingerprint")

    def _connect(self) -> sqlite3.Connection:
        self._assert_current_file_identity()
        uri = self.path.as_uri() + "?mode=rw"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        except sqlite3.Error as exc:
            raise PersistentAgencyIntegrationError("canonical UnifiedDB read/write open failed") from exc
        try:
            rows = conn.execute("PRAGMA database_list").fetchall()
            main_paths = [row[2] for row in rows if len(row) >= 3 and row[1] == "main"]
            if len(main_paths) != 1 or not main_paths[0]:
                raise PersistentAgencyIntegrationError("SQLite main database path unavailable")
            if not _same_real_path(main_paths[0], str(self.path)):
                raise PersistentAgencyIntegrationError("SQLite connection not bound to fingerprinted UnifiedDB")
            self._assert_current_file_identity()
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def _schema_statement() -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                kernel_id TEXT NOT NULL,
                integration_generation INTEGER NOT NULL CHECK (integration_generation >= 0),
                checkpoint_sha256 TEXT NOT NULL UNIQUE,
                parent_checkpoint_sha256 TEXT,
                payload_json TEXT NOT NULL,
                unifieddb_authority_receipt_sha256 TEXT NOT NULL,
                PRIMARY KEY (kernel_id, integration_generation)
            )
        """

    def initialize(self) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(self._schema_statement())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def persist(self, checkpoint: PersistentAgencyCheckpoint) -> CheckpointWriteReceipt:
        if not isinstance(checkpoint, PersistentAgencyCheckpoint):
            raise PersistentAgencyIntegrationError("checkpoint must be PersistentAgencyCheckpoint")
        payload = checkpoint.canonical_json()
        checkpoint_sha = checkpoint.sha256()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(self._schema_statement())
            existing = conn.execute(
                f"SELECT checkpoint_sha256,payload_json,unifieddb_authority_receipt_sha256 "
                f"FROM {TABLE_NAME} WHERE kernel_id=? AND integration_generation=?",
                (checkpoint.kernel_id, checkpoint.integration_generation),
            ).fetchone()
            if existing is not None:
                if existing == (checkpoint_sha, payload, self.authority_receipt_sha256):
                    conn.commit()
                    return self._receipt(checkpoint, checkpoint_sha, "IDEMPOTENT_ALREADY_PRESENT")
                raise PersistentAgencyIntegrationError(
                    "checkpoint generation already exists with different payload or authority"
                )

            latest = conn.execute(
                f"SELECT integration_generation,checkpoint_sha256 FROM {TABLE_NAME} "
                "WHERE kernel_id=? ORDER BY integration_generation DESC LIMIT 1",
                (checkpoint.kernel_id,),
            ).fetchone()
            if latest is None:
                if checkpoint.integration_generation != 0 or checkpoint.parent_checkpoint_sha256 is not None:
                    raise PersistentAgencyIntegrationError(
                        "first persisted checkpoint must be generation zero without parent"
                    )
            else:
                latest_generation, latest_sha = int(latest[0]), str(latest[1])
                if checkpoint.integration_generation != latest_generation + 1:
                    raise PersistentAgencyIntegrationError(
                        "checkpoint integration generation is stale or skipped"
                    )
                if checkpoint.parent_checkpoint_sha256 != latest_sha:
                    raise PersistentAgencyIntegrationError(
                        "checkpoint parent digest does not match latest persisted checkpoint"
                    )

            conn.execute(
                f"INSERT INTO {TABLE_NAME} "
                "(kernel_id,integration_generation,checkpoint_sha256,parent_checkpoint_sha256,"
                "payload_json,unifieddb_authority_receipt_sha256) VALUES (?,?,?,?,?,?)",
                (
                    checkpoint.kernel_id,
                    checkpoint.integration_generation,
                    checkpoint_sha,
                    checkpoint.parent_checkpoint_sha256,
                    payload,
                    self.authority_receipt_sha256,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self._receipt(checkpoint, checkpoint_sha, "INSERTED")

    def _receipt(
        self,
        checkpoint: PersistentAgencyCheckpoint,
        checkpoint_sha: str,
        status: str,
    ) -> CheckpointWriteReceipt:
        return CheckpointWriteReceipt(
            schema=WRITE_RECEIPT_SCHEMA,
            kernel_id=checkpoint.kernel_id,
            integration_generation=checkpoint.integration_generation,
            checkpoint_sha256=checkpoint_sha,
            db_path=str(self.path),
            resolution_source=self.resolution.source,
            unifieddb_authority_receipt_sha256=self.authority_receipt_sha256,
            status=status,
        )

    def load_generation(
        self, kernel_id: str, integration_generation: int
    ) -> PersistentAgencyCheckpoint:
        kernel = _identifier("kernel_id", kernel_id)
        generation = _generation(integration_generation)
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT checkpoint_sha256,payload_json,unifieddb_authority_receipt_sha256 "
                f"FROM {TABLE_NAME} WHERE kernel_id=? AND integration_generation=?",
                (kernel, generation),
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistentAgencyIntegrationError("WP206 checkpoint schema unavailable") from exc
        finally:
            conn.close()
        if row is None:
            raise PersistentAgencyIntegrationError("checkpoint not found")
        expected_sha, payload_json, authority_sha = str(row[0]), str(row[1]), str(row[2])
        if authority_sha != self.authority_receipt_sha256:
            raise PersistentAgencyIntegrationError("persisted checkpoint authority receipt mismatch")
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise PersistentAgencyIntegrationError("persisted checkpoint JSON is invalid") from exc
        checkpoint = PersistentAgencyCheckpoint.from_dict(payload)
        if checkpoint.kernel_id != kernel or checkpoint.integration_generation != generation:
            raise PersistentAgencyIntegrationError("persisted checkpoint row/payload identity mismatch")
        if checkpoint.canonical_json() != payload_json:
            raise PersistentAgencyIntegrationError("persisted checkpoint JSON is not canonical")
        if checkpoint.sha256() != expected_sha:
            raise PersistentAgencyIntegrationError("persisted checkpoint digest mismatch")
        return checkpoint

    def load_latest(self, kernel_id: str) -> PersistentAgencyCheckpoint:
        kernel = _identifier("kernel_id", kernel_id)
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT integration_generation FROM {TABLE_NAME} "
                "WHERE kernel_id=? ORDER BY integration_generation DESC LIMIT 1",
                (kernel,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistentAgencyIntegrationError("WP206 checkpoint schema unavailable") from exc
        finally:
            conn.close()
        if row is None:
            raise PersistentAgencyIntegrationError("checkpoint not found")
        return self.load_generation(kernel, int(row[0]))


__all__ = [
    "CHECKPOINT_SCHEMA",
    "CLASSIFICATION",
    "PROJECTION_SCHEMA",
    "TABLE_NAME",
    "WRITE_RECEIPT_SCHEMA",
    "CheckpointWriteReceipt",
    "PersistentAgencyCheckpoint",
    "PersistentAgencyIntegrationError",
    "PersistentAgencyStore",
    "build_checkpoint",
    "rehydrate_agency_state",
    "rehydrate_candidate_goal_state",
]
