"""WP900 G9 no-bypass semantic mediation repair.

This module does not mint runtime or semantic-GWT credit. It closes a repository
false-green: a semantic outcome must be produced by a fresh isolated executor
whose only treatment-bearing input is semantic state bound to an admitted
DELIVERY->UPTAKE->REENTRY witness. Payload refs, arm labels, broadcast hashes,
environment side channels and caller-selected semantic labels are excluded from
the behavioral input ABI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence

from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import BroadcastEnvelope, WorkspaceSelection

SEMANTIC_ORACLE_SCHEMA = "FRANKENSTEIN2_G9_FROZEN_SEMANTIC_ORACLE/v1"
SEMANTIC_SLOT_PLAN_SCHEMA = "FRANKENSTEIN2_G9_POST_SELECTION_SEMANTIC_SLOT_PLAN/v1"
REENTRY_SEMANTIC_STATE_SCHEMA = "FRANKENSTEIN2_G9_REENTRY_SEMANTIC_STATE/v1"
EXECUTOR_PLAN_SCHEMA = "FRANKENSTEIN2_G9_REENTRY_ONLY_EXECUTOR_PLAN/v1"
EXECUTOR_INPUT_SCHEMA = "FRANKENSTEIN2_G9_REENTRY_ONLY_EXECUTOR_INPUT/v1"
EXECUTION_RECEIPT_SCHEMA = "FRANKENSTEIN2_G9_REENTRY_ONLY_EXECUTION_RECEIPT/v1"
NO_BYPASS_CROSSOVER_SCHEMA = "FRANKENSTEIN2_G9_NO_BYPASS_SEMANTIC_CROSSOVER/v1"

NO_BYPASS_SEMANTIC_CANDIDATE = (
    "NO_BYPASS_SEMANTIC_CONTENT_CAUSALITY_CANDIDATE_REQUIRES_TARGET_EXECUTION_ADMISSION"
)
NO_SEMANTIC_DIFFERENCE = "NO_PREREGISTERED_SEMANTIC_DIFFERENCE"
SEMANTIC_COMPARISON_UNKNOWN = "SEMANTIC_COMPARISON_UNKNOWN"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_BYTES = 1_048_576
_ORACLE_FACTORY = object()
_SLOT_PLAN_FACTORY = object()
_STATE_FACTORY = object()
_EXECUTOR_PLAN_FACTORY = object()
_EXECUTOR_INPUT_FACTORY = object()
_EXECUTION_FACTORY = object()
_CROSSOVER_FACTORY = object()

_WORKER_SOURCE = r"""
import hashlib
import json
import os
import sys

raw = sys.stdin.buffer.read()
request = json.loads(raw.decode("utf-8"))
expected_keys = {
    "schema",
    "executor_plan_sha256",
    "task_context_sha256",
    "runtime_pre_state_sha256",
    "semantic_state_canonical_json",
    "semantic_field_name",
    "decision_mapping",
}
if set(request) != expected_keys:
    raise SystemExit(41)
semantic = json.loads(request["semantic_state_canonical_json"])
field = request["semantic_field_name"]
mapping = dict(request["decision_mapping"])
value = semantic.get(field) if isinstance(semantic, dict) else None
if value not in mapping:
    result = {"decision": "UNKNOWN"}
else:
    result = {"decision": mapping[value]}
envelope = {
    "pid": os.getpid(),
    "input_sha256": hashlib.sha256(raw).hexdigest(),
    "semantic_output": result,
}
sys.stdout.write(json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False))
"""


class G9NoBypassError(ValueError):
    pass


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise G9NoBypassError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise G9NoBypassError(f"{name} is not bounded printable text")
    return value


def _sha(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise G9NoBypassError(f"{name} must be lowercase SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise G9NoBypassError("provenance_refs must be iterable")
    items = tuple(_text("provenance_ref", value) for value in values)
    if not items or len(set(items)) != len(items):
        raise G9NoBypassError("provenance_refs must be non-empty and unique")
    return tuple(sorted(items))


def _canonical_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise G9NoBypassError("value is not canonical-JSON encodable") from exc
    if len(encoded.encode("utf-8")) > _MAX_BYTES:
        raise G9NoBypassError("canonical JSON exceeds size bound")
    return encoded


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_constant(value: str) -> None:
    raise G9NoBypassError(f"non-finite JSON constant is not admissible: {value}")


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise G9NoBypassError(f"duplicate JSON key is not admissible: {key}")
        result[key] = value
    return result


def _parse_json(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_BYTES:
        raise G9NoBypassError("exact bounded JSON bytes required")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except G9NoBypassError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise G9NoBypassError("invalid UTF-8 JSON") from exc


def _seal(value: Any, token: object) -> Any:
    object.__setattr__(value, "_factory_seal", token)
    object.__setattr__(value, "_factory_sha256", _digest(value.as_dict()))
    return value


def _validate_seal(value: Any, expected_type: type, token: object, name: str) -> None:
    if (
        type(value) is not expected_type
        or value._factory_seal is not token
        or value._factory_sha256 != _digest(value.as_dict())
    ):
        raise G9NoBypassError(f"{name} lacks valid factory origin")


@dataclass(frozen=True, slots=True, kw_only=True)
class FrozenSemanticOracle:
    oracle_id: str
    field_name: str
    allowed_values: tuple[str, ...]
    unknown_value: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = SEMANTIC_ORACLE_SCHEMA
    algorithm = "TOP_LEVEL_STRING_ENUM_EXACT_V1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "oracle_id", _text("oracle_id", self.oracle_id))
        object.__setattr__(self, "field_name", _text("field_name", self.field_name))
        object.__setattr__(self, "unknown_value", _text("unknown_value", self.unknown_value))
        values = tuple(sorted(_text("allowed_value", item) for item in self.allowed_values))
        if len(values) < 2 or len(set(values)) != len(values) or self.unknown_value in values:
            raise G9NoBypassError("invalid semantic oracle value set")
        object.__setattr__(self, "allowed_values", values)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def create(cls, **kwargs: Any) -> "FrozenSemanticOracle":
        return _seal(cls(**kwargs), _ORACLE_FACTORY)

    def classify(self, raw: bytes) -> tuple[str, str, str]:
        value = _parse_json(raw)
        canonical = _canonical_json(value)
        semantic_class = self.unknown_value
        if (
            type(value) is dict
            and type(value.get(self.field_name)) is str
            and value[self.field_name] in self.allowed_values
        ):
            semantic_class = value[self.field_name]
        return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest(), semantic_class

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "oracle_id": self.oracle_id,
            "field_name": self.field_name,
            "allowed_values": list(self.allowed_values),
            "unknown_value": self.unknown_value,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_frozen_semantic_oracle(value: FrozenSemanticOracle) -> None:
    _validate_seal(value, FrozenSemanticOracle, _ORACLE_FACTORY, "semantic oracle")


@dataclass(frozen=True, slots=True, kw_only=True)
class PostSelectionSemanticSlotPlan:
    plan_id: str
    semantic_slot_ref: str
    selection_sha256: str
    broadcast_sha256: str
    broadcast_id: str
    recipient_cell_id: str
    payload_oracle: FrozenSemanticOracle
    outcome_oracle: FrozenSemanticOracle
    trial_semantic_order: tuple[str, str, str, str]
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = SEMANTIC_SLOT_PLAN_SCHEMA

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        semantic_slot_ref: str,
        selection: WorkspaceSelection,
        broadcast: BroadcastEnvelope,
        payload_oracle: FrozenSemanticOracle,
        outcome_oracle: FrozenSemanticOracle,
        trial_semantic_order: tuple[str, str, str, str],
        provenance_refs: Iterable[str],
    ) -> "PostSelectionSemanticSlotPlan":
        validate_frozen_semantic_oracle(payload_oracle)
        validate_frozen_semantic_oracle(outcome_oracle)
        if type(selection) is not WorkspaceSelection or type(broadcast) is not BroadcastEnvelope:
            raise G9NoBypassError("exact selection and broadcast are required")
        if broadcast.selection_sha256 != selection.sha256():
            raise G9NoBypassError("broadcast does not bind preregistered selection")
        if broadcast.candidate_payload_refs != (semantic_slot_ref,):
            raise G9NoBypassError("broadcast must expose exactly one treatment-invariant semantic slot")
        if len(broadcast.recipient_cell_ids) != 1:
            raise G9NoBypassError("exactly one recipient is required for discriminator")
        value = cls(
            plan_id=plan_id,
            semantic_slot_ref=semantic_slot_ref,
            selection_sha256=selection.sha256(),
            broadcast_sha256=broadcast.sha256(),
            broadcast_id=broadcast.broadcast_id,
            recipient_cell_id=broadcast.recipient_cell_ids[0],
            payload_oracle=payload_oracle,
            outcome_oracle=outcome_oracle,
            trial_semantic_order=trial_semantic_order,
            provenance_refs=tuple(provenance_refs),
        )
        return _seal(value, _SLOT_PLAN_FACTORY)

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text("plan_id", self.plan_id))
        object.__setattr__(self, "semantic_slot_ref", _text("semantic_slot_ref", self.semantic_slot_ref))
        for name in ("selection_sha256", "broadcast_sha256"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        object.__setattr__(self, "broadcast_id", _text("broadcast_id", self.broadcast_id))
        object.__setattr__(self, "recipient_cell_id", _text("recipient_cell_id", self.recipient_cell_id))
        order = tuple(_text("trial_semantic_class", item) for item in self.trial_semantic_order)
        if not (len(order) == 4 and order[0] == order[3] and order[1] == order[2] and order[0] != order[1]):
            raise G9NoBypassError("trial semantic order must be ABBA")
        if any(item not in self.payload_oracle.allowed_values for item in order):
            raise G9NoBypassError("trial semantic class not admitted by frozen payload oracle")
        object.__setattr__(self, "trial_semantic_order", order)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_id": self.plan_id,
            "semantic_slot_ref": self.semantic_slot_ref,
            "selection_sha256": self.selection_sha256,
            "broadcast_sha256": self.broadcast_sha256,
            "broadcast_id": self.broadcast_id,
            "recipient_cell_id": self.recipient_cell_id,
            "payload_oracle_sha256": self.payload_oracle.sha256(),
            "outcome_oracle_sha256": self.outcome_oracle.sha256(),
            "trial_semantic_order": list(self.trial_semantic_order),
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_semantic_slot_plan(value: PostSelectionSemanticSlotPlan) -> None:
    validate_frozen_semantic_oracle(value.payload_oracle)
    validate_frozen_semantic_oracle(value.outcome_oracle)
    _validate_seal(value, PostSelectionSemanticSlotPlan, _SLOT_PLAN_FACTORY, "semantic slot plan")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryDerivedSemanticState:
    plan_sha256: str
    trial_position: int
    semantic_class: str
    canonical_semantic_json: str
    semantic_sha256: str
    raw_payload_sha256: str
    runtime_witness_sha256: str
    uptake_receipt_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    runtime_instance_id: str
    process_identity: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = REENTRY_SEMANTIC_STATE_SCHEMA

    @classmethod
    def observe(
        cls,
        *,
        plan: PostSelectionSemanticSlotPlan,
        broadcast: BroadcastEnvelope,
        runtime_witness: GwtRuntimeWitnessReceipt,
        uptake_receipt: CellUptakeReceipt,
        trial_position: int,
        semantic_payload: bytes,
        provenance_refs: Iterable[str],
    ) -> "ReentryDerivedSemanticState":
        validate_semantic_slot_plan(plan)
        if type(broadcast) is not BroadcastEnvelope or broadcast.sha256() != plan.broadcast_sha256:
            raise G9NoBypassError("trial broadcast differs from frozen treatment-invariant envelope")
        try:
            validate_gwt_runtime_witness_receipt(runtime_witness)
        except ValueError as exc:
            raise G9NoBypassError("runtime witness is not factory-valid") from exc
        if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
            raise G9NoBypassError("full DELIVERY->UPTAKE->REENTRY path is required")
        if (
            runtime_witness.broadcast_id != broadcast.broadcast_id
            or runtime_witness.broadcast_sha256 != broadcast.sha256()
            or runtime_witness.recipient_cell_id != plan.recipient_cell_id
        ):
            raise G9NoBypassError("runtime witness does not bind frozen broadcast/recipient")
        if type(uptake_receipt) is not CellUptakeReceipt:
            raise G9NoBypassError("exact uptake receipt is required")
        try:
            uptake_receipt.assert_broadcast_binding(broadcast)
        except GWTUptakeError as exc:
            raise G9NoBypassError("uptake receipt does not bind frozen broadcast") from exc
        if (
            runtime_witness.uptake_receipt_id != uptake_receipt.receipt_id
            or runtime_witness.uptake_receipt_sha256 != uptake_receipt.sha256()
            or uptake_receipt.delivery_status != "DELIVERED"
            or uptake_receipt.uptake_status != "UPTAKEN"
            or uptake_receipt.downstream_ref != plan.semantic_slot_ref
        ):
            raise G9NoBypassError("semantic slot was not delivered and uptaken on witnessed path")
        raw_sha = hashlib.sha256(semantic_payload).hexdigest()
        if uptake_receipt.downstream_sha256 != raw_sha:
            raise G9NoBypassError("semantic payload bytes do not match witnessed slot readback")
        canonical, semantic_sha, semantic_class = plan.payload_oracle.classify(semantic_payload)
        if semantic_class == plan.payload_oracle.unknown_value:
            raise G9NoBypassError("frozen payload oracle returned UNKNOWN")
        if type(trial_position) is not int or not 1 <= trial_position <= 4:
            raise G9NoBypassError("trial_position must be 1..4")
        if semantic_class != plan.trial_semantic_order[trial_position - 1]:
            raise G9NoBypassError("payload violates preregistered semantic trial order")
        identity = runtime_witness.identity
        return _seal(
            cls(
                plan_sha256=plan.sha256(),
                trial_position=trial_position,
                semantic_class=semantic_class,
                canonical_semantic_json=canonical,
                semantic_sha256=semantic_sha,
                raw_payload_sha256=raw_sha,
                runtime_witness_sha256=runtime_witness.sha256(),
                uptake_receipt_sha256=uptake_receipt.sha256(),
                exact_source_sha256=identity.exact_source_sha256,
                boot_id_sha256=identity.boot_id_sha256,
                runtime_instance_id=identity.runtime_instance_id,
                process_identity=identity.process_identity,
                provenance_refs=tuple(provenance_refs),
            ),
            _STATE_FACTORY,
        )

    def __post_init__(self) -> None:
        for name in (
            "plan_sha256",
            "semantic_sha256",
            "raw_payload_sha256",
            "runtime_witness_sha256",
            "uptake_receipt_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        object.__setattr__(self, "semantic_class", _text("semantic_class", self.semantic_class))
        object.__setattr__(self, "runtime_instance_id", _text("runtime_instance_id", self.runtime_instance_id))
        object.__setattr__(self, "process_identity", _text("process_identity", self.process_identity))
        _parse_json(self.canonical_semantic_json.encode("utf-8"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_sha256": self.plan_sha256,
            "trial_position": self.trial_position,
            "semantic_class": self.semantic_class,
            "canonical_semantic_json": self.canonical_semantic_json,
            "semantic_sha256": self.semantic_sha256,
            "raw_payload_sha256": self.raw_payload_sha256,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_reentry_semantic_state(value: ReentryDerivedSemanticState) -> None:
    _validate_seal(value, ReentryDerivedSemanticState, _STATE_FACTORY, "reentry semantic state")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryOnlyExecutorPlan:
    plan_id: str
    semantic_field_name: str
    decision_mapping: tuple[tuple[str, str], ...]
    task_context_sha256: str
    runtime_pre_state_sha256: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = EXECUTOR_PLAN_SCHEMA
    worker_source_sha256 = hashlib.sha256(_WORKER_SOURCE.encode("utf-8")).hexdigest()

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text("plan_id", self.plan_id))
        object.__setattr__(self, "semantic_field_name", _text("semantic_field_name", self.semantic_field_name))
        mapping = tuple(sorted((_text("semantic_value", a), _text("decision", b)) for a, b in self.decision_mapping))
        if len(mapping) < 2 or len({a for a, _ in mapping}) != len(mapping):
            raise G9NoBypassError("executor decision mapping must contain unique semantic keys")
        object.__setattr__(self, "decision_mapping", mapping)
        object.__setattr__(self, "task_context_sha256", _sha("task_context_sha256", self.task_context_sha256))
        object.__setattr__(self, "runtime_pre_state_sha256", _sha("runtime_pre_state_sha256", self.runtime_pre_state_sha256))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def create(cls, **kwargs: Any) -> "ReentryOnlyExecutorPlan":
        return _seal(cls(**kwargs), _EXECUTOR_PLAN_FACTORY)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_id": self.plan_id,
            "semantic_field_name": self.semantic_field_name,
            "decision_mapping": [list(item) for item in self.decision_mapping],
            "task_context_sha256": self.task_context_sha256,
            "runtime_pre_state_sha256": self.runtime_pre_state_sha256,
            "worker_source_sha256": self.worker_source_sha256,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_executor_plan(value: ReentryOnlyExecutorPlan) -> None:
    _validate_seal(value, ReentryOnlyExecutorPlan, _EXECUTOR_PLAN_FACTORY, "executor plan")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryOnlyExecutorInput:
    executor_plan_sha256: str
    task_context_sha256: str
    runtime_pre_state_sha256: str
    semantic_state_canonical_json: str
    semantic_field_name: str
    decision_mapping: tuple[tuple[str, str], ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = EXECUTOR_INPUT_SCHEMA

    @classmethod
    def bind(
        cls,
        *,
        executor_plan: ReentryOnlyExecutorPlan,
        semantic_state: ReentryDerivedSemanticState,
    ) -> "ReentryOnlyExecutorInput":
        validate_executor_plan(executor_plan)
        validate_reentry_semantic_state(semantic_state)
        return _seal(
            cls(
                executor_plan_sha256=executor_plan.sha256(),
                task_context_sha256=executor_plan.task_context_sha256,
                runtime_pre_state_sha256=executor_plan.runtime_pre_state_sha256,
                semantic_state_canonical_json=semantic_state.canonical_semantic_json,
                semantic_field_name=executor_plan.semantic_field_name,
                decision_mapping=executor_plan.decision_mapping,
            ),
            _EXECUTOR_INPUT_FACTORY,
        )

    def __post_init__(self) -> None:
        for name in ("executor_plan_sha256", "task_context_sha256", "runtime_pre_state_sha256"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        object.__setattr__(self, "semantic_field_name", _text("semantic_field_name", self.semantic_field_name))
        _parse_json(self.semantic_state_canonical_json.encode("utf-8"))
        mapping = tuple(sorted((_text("semantic_value", a), _text("decision", b)) for a, b in self.decision_mapping))
        object.__setattr__(self, "decision_mapping", mapping)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "executor_plan_sha256": self.executor_plan_sha256,
            "task_context_sha256": self.task_context_sha256,
            "runtime_pre_state_sha256": self.runtime_pre_state_sha256,
            "semantic_state_canonical_json": self.semantic_state_canonical_json,
            "semantic_field_name": self.semantic_field_name,
            "decision_mapping": [list(item) for item in self.decision_mapping],
        }

    def to_bytes(self) -> bytes:
        return _canonical_json(self.as_dict()).encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


def validate_executor_input(value: ReentryOnlyExecutorInput) -> None:
    _validate_seal(value, ReentryOnlyExecutorInput, _EXECUTOR_INPUT_FACTORY, "executor input")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryOnlyExecutionReceipt:
    executor_plan_sha256: str
    executor_input_sha256: str
    semantic_state_sha256: str
    worker_source_sha256: str
    child_pid: int
    semantic_output_canonical_json: str
    semantic_output_sha256: str
    outcome_class: str
    environment_keys: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = EXECUTION_RECEIPT_SCHEMA
    evidence_scope = "FRESH_ISOLATED_PROCESS_REENTRY_ONLY_EXECUTOR_REPOSITORY_CANDIDATE"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_content_causal_candidate_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in ("executor_plan_sha256", "executor_input_sha256", "semantic_state_sha256", "worker_source_sha256", "semantic_output_sha256"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if type(self.child_pid) is not int or self.child_pid < 1:
            raise G9NoBypassError("child_pid must be positive")
        _parse_json(self.semantic_output_canonical_json.encode("utf-8"))
        object.__setattr__(self, "outcome_class", _text("outcome_class", self.outcome_class))
        keys = tuple(sorted(_text("environment_key", item) for item in self.environment_keys))
        object.__setattr__(self, "environment_keys", keys)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "executor_plan_sha256": self.executor_plan_sha256,
            "executor_input_sha256": self.executor_input_sha256,
            "semantic_state_sha256": self.semantic_state_sha256,
            "worker_source_sha256": self.worker_source_sha256,
            "child_pid": self.child_pid,
            "semantic_output_canonical_json": self.semantic_output_canonical_json,
            "semantic_output_sha256": self.semantic_output_sha256,
            "outcome_class": self.outcome_class,
            "environment_keys": list(self.environment_keys),
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "semantic_content_causal_candidate_credit": self.semantic_content_causal_candidate_credit,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_execution_receipt(value: ReentryOnlyExecutionReceipt) -> None:
    _validate_seal(value, ReentryOnlyExecutionReceipt, _EXECUTION_FACTORY, "execution receipt")


def execute_reentry_only(
    *,
    executor_plan: ReentryOnlyExecutorPlan,
    semantic_state: ReentryDerivedSemanticState,
    outcome_oracle: FrozenSemanticOracle,
) -> ReentryOnlyExecutionReceipt:
    validate_executor_plan(executor_plan)
    validate_reentry_semantic_state(semantic_state)
    validate_frozen_semantic_oracle(outcome_oracle)
    request = ReentryOnlyExecutorInput.bind(
        executor_plan=executor_plan,
        semantic_state=semantic_state,
    )
    validate_executor_input(request)
    raw_request = request.to_bytes()
    clean_env = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
    }
    process = subprocess.Popen(
        [sys.executable, "-I", "-c", _WORKER_SOURCE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_env,
    )
    stdout, stderr = process.communicate(raw_request, timeout=15)
    if process.returncode != 0:
        raise G9NoBypassError(
            f"isolated executor failed closed rc={process.returncode}: "
            f"{stderr.decode('utf-8', errors='replace')[:200]}"
        )
    envelope = _parse_json(stdout)
    if type(envelope) is not dict or set(envelope) != {"pid", "input_sha256", "semantic_output"}:
        raise G9NoBypassError("isolated executor returned invalid envelope")
    if envelope["input_sha256"] != hashlib.sha256(raw_request).hexdigest():
        raise G9NoBypassError("isolated executor did not bind exact serialized input")
    semantic_output = envelope["semantic_output"]
    canonical_output = _canonical_json(semantic_output)
    raw_output = canonical_output.encode("utf-8")
    _, semantic_output_sha, outcome_class = outcome_oracle.classify(raw_output)
    return _seal(
        ReentryOnlyExecutionReceipt(
            executor_plan_sha256=executor_plan.sha256(),
            executor_input_sha256=request.sha256(),
            semantic_state_sha256=semantic_state.sha256(),
            worker_source_sha256=ReentryOnlyExecutorPlan.worker_source_sha256,
            child_pid=int(envelope["pid"]),
            semantic_output_canonical_json=canonical_output,
            semantic_output_sha256=semantic_output_sha,
            outcome_class=outcome_class,
            environment_keys=tuple(clean_env),
        ),
        _EXECUTION_FACTORY,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class NoBypassSemanticCrossoverCandidate:
    semantic_slot_plan_sha256: str
    executor_plan_sha256: str
    semantic_order: tuple[str, str, str, str]
    raw_payload_sha256s: tuple[str, str, str, str]
    execution_receipt_sha256s: tuple[str, str, str, str]
    child_pids: tuple[int, int, int, int]
    observed_mapping: tuple[tuple[str, str], tuple[str, str]]
    exact_source_sha256: str
    boot_id_sha256: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = NO_BYPASS_CROSSOVER_SCHEMA
    evidence_scope = "REPOSITORY_NO_BYPASS_CAUSAL_PROTOCOL_CANDIDATE_REQUIRES_EXACT_TARGET_EXECUTION"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_content_causal_candidate_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in ("semantic_slot_plan_sha256", "executor_plan_sha256", "exact_source_sha256", "boot_id_sha256"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        object.__setattr__(self, "classification", _text("classification", self.classification))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "semantic_slot_plan_sha256": self.semantic_slot_plan_sha256,
            "executor_plan_sha256": self.executor_plan_sha256,
            "semantic_order": list(self.semantic_order),
            "raw_payload_sha256s": list(self.raw_payload_sha256s),
            "execution_receipt_sha256s": list(self.execution_receipt_sha256s),
            "child_pids": list(self.child_pids),
            "observed_mapping": [list(item) for item in self.observed_mapping],
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "classification": self.classification,
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "semantic_content_causal_candidate_credit": self.semantic_content_causal_candidate_credit,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_no_bypass_crossover(value: NoBypassSemanticCrossoverCandidate) -> None:
    _validate_seal(value, NoBypassSemanticCrossoverCandidate, _CROSSOVER_FACTORY, "no-bypass crossover")


def bind_no_bypass_crossover(
    *,
    semantic_slot_plan: PostSelectionSemanticSlotPlan,
    executor_plan: ReentryOnlyExecutorPlan,
    semantic_states: Sequence[ReentryDerivedSemanticState],
    execution_receipts: Sequence[ReentryOnlyExecutionReceipt],
    provenance_refs: Iterable[str],
) -> NoBypassSemanticCrossoverCandidate:
    validate_semantic_slot_plan(semantic_slot_plan)
    validate_executor_plan(executor_plan)
    if len(semantic_states) != 4 or len(execution_receipts) != 4:
        raise G9NoBypassError("exactly four states and four executions are required")
    states = tuple(semantic_states)
    receipts = tuple(execution_receipts)
    for state in states:
        validate_reentry_semantic_state(state)
    for receipt in receipts:
        validate_execution_receipt(receipt)
    if tuple(state.trial_position for state in states) != (1, 2, 3, 4):
        raise G9NoBypassError("states must be supplied in trial order 1..4")
    order = tuple(state.semantic_class for state in states)
    if order != semantic_slot_plan.trial_semantic_order:
        raise G9NoBypassError("observed semantics violate preregistered ABBA order")
    if len({state.raw_payload_sha256 for state in states}) != 4:
        raise G9NoBypassError("four byte-distinct semantic surface variants are required")
    if len({state.runtime_instance_id for state in states}) != 4 or len({state.process_identity for state in states}) != 4:
        raise G9NoBypassError("fresh witnessed runtime/process identity is required per trial")
    if len({receipt.child_pid for receipt in receipts}) != 4:
        raise G9NoBypassError("fresh isolated executor process is required per trial")
    if any(receipt.executor_plan_sha256 != executor_plan.sha256() for receipt in receipts):
        raise G9NoBypassError("executor plan changed across trials")
    if any(receipt.semantic_state_sha256 != state.sha256() for state, receipt in zip(states, receipts)):
        raise G9NoBypassError("execution receipt does not bind corresponding reentry semantic state")
    sources = {state.exact_source_sha256 for state in states}
    boots = {state.boot_id_sha256 for state in states}
    if len(sources) != 1 or len(boots) != 1:
        raise G9NoBypassError("source and boot identity must remain invariant across crossover")
    observed: list[tuple[str, str]] = []
    for semantic_class in sorted(set(order)):
        outcomes = {
            receipt.outcome_class
            for state, receipt in zip(states, receipts)
            if state.semantic_class == semantic_class
        }
        if semantic_slot_plan.outcome_oracle.unknown_value in outcomes or len(outcomes) != 1:
            classification = SEMANTIC_COMPARISON_UNKNOWN
            break
        observed.append((semantic_class, next(iter(outcomes))))
    else:
        expected_mapping = tuple(sorted(executor_plan.decision_mapping))
        classification = (
            NO_BYPASS_SEMANTIC_CANDIDATE
            if tuple(sorted(observed)) == expected_mapping
            else NO_SEMANTIC_DIFFERENCE
        )
    return _seal(
        NoBypassSemanticCrossoverCandidate(
            semantic_slot_plan_sha256=semantic_slot_plan.sha256(),
            executor_plan_sha256=executor_plan.sha256(),
            semantic_order=order,
            raw_payload_sha256s=tuple(state.raw_payload_sha256 for state in states),
            execution_receipt_sha256s=tuple(receipt.sha256() for receipt in receipts),
            child_pids=tuple(receipt.child_pid for receipt in receipts),
            observed_mapping=tuple(observed),
            exact_source_sha256=next(iter(sources)),
            boot_id_sha256=next(iter(boots)),
            classification=classification,
            provenance_refs=tuple(provenance_refs),
        ),
        _CROSSOVER_FACTORY,
    )


def behavioral_input_keys() -> frozenset[str]:
    return frozenset(
        {
            "schema",
            "executor_plan_sha256",
            "task_context_sha256",
            "runtime_pre_state_sha256",
            "semantic_state_canonical_json",
            "semantic_field_name",
            "decision_mapping",
        }
    )


FORBIDDEN_BEHAVIORAL_INPUT_KEYS = frozenset(
    {
        "condition",
        "arm",
        "trial_position",
        "payload_ref",
        "payload_sha256",
        "broadcast_id",
        "broadcast_sha256",
        "candidate_id",
        "semantic_class",
        "expected_outcome",
        "runtime_witness_sha256",
        "registry_handle",
        "resolver",
    }
)

if behavioral_input_keys() & FORBIDDEN_BEHAVIORAL_INPUT_KEYS:
    raise RuntimeError("G9 executor behavioral ABI leaks treatment metadata")


__all__ = [
    "FORBIDDEN_BEHAVIORAL_INPUT_KEYS",
    "FrozenSemanticOracle",
    "G9NoBypassError",
    "NO_BYPASS_SEMANTIC_CANDIDATE",
    "NO_SEMANTIC_DIFFERENCE",
    "NoBypassSemanticCrossoverCandidate",
    "PostSelectionSemanticSlotPlan",
    "ReentryDerivedSemanticState",
    "ReentryOnlyExecutionReceipt",
    "ReentryOnlyExecutorInput",
    "ReentryOnlyExecutorPlan",
    "SEMANTIC_COMPARISON_UNKNOWN",
    "behavioral_input_keys",
    "bind_no_bypass_crossover",
    "execute_reentry_only",
    "validate_execution_receipt",
    "validate_frozen_semantic_oracle",
    "validate_no_bypass_crossover",
    "validate_reentry_semantic_state",
    "validate_semantic_slot_plan",
]
