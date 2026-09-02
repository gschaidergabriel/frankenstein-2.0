"""WP900 G10 independent semantic mediator authority candidate.

G9 proved a real no-bypass semantic target-component crossover, but the exact
per-trial semantic bytes were still handed to the trial process while the
independent source/readback discriminator ran beside it. G10 closes only that
remaining mediation gap at repository scope: a factory-valid independent
source-range must bind the exact semantic bytes to a LIVE GWT reentry witness,
then emit one canonical wire packet. Downstream trial code consumes only that
packet; the behavioral child consumes only the reentry-derived semantic JSON.

Repository construction cannot prove operational process independence. All
runtime / semantic-GWT / J-Space credits remain zero until exact target
execution binds source -> wire -> trial -> child identities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any, Iterable

from frankenstein2.gwt_reentry_causal_admission import (
    IndependentEventSourceRangeReceipt,
    SOURCE_EVENT_GWT_REENTRY,
    validate_independent_event_source_range,
)
from frankenstein2.gwt_runtime_witness import (
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import BroadcastEnvelope
from frankenstein2.gwt_semantic_reentry_only_execution import (
    PostSelectionSemanticSlotPlan,
    ReentryOnlyExecutorPlan,
    validate_executor_plan,
    validate_semantic_slot_plan,
)

SEMANTIC_MEDIATOR_RECEIPT_SCHEMA = "FRANKENSTEIN2_G10_INDEPENDENT_SEMANTIC_MEDIATOR_RECEIPT/v1"
SEMANTIC_MEDIATOR_WIRE_SCHEMA = "FRANKENSTEIN2_G10_INDEPENDENT_SEMANTIC_MEDIATOR_WIRE/v1"
MEDIATED_SEMANTIC_STATE_SCHEMA = "FRANKENSTEIN2_G10_MEDIATED_SEMANTIC_STATE/v1"
MEDIATED_EXECUTION_RECEIPT_SCHEMA = "FRANKENSTEIN2_G10_MEDIATED_EXECUTION_RECEIPT/v1"

MEDIATOR_AUTHORITY_CANDIDATE = (
    "INDEPENDENT_SEMANTIC_MEDIATOR_AUTHORITY_CANDIDATE_REQUIRES_TARGET_EXECUTION"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_BYTES = 1_048_576
_MAX_TEXT = 512
_MEDIATOR_FACTORY = object()
_STATE_FACTORY = object()
_EXECUTION_FACTORY = object()

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
result = {"decision": mapping[value]} if value in mapping else {"decision": "UNKNOWN"}
envelope = {
    "pid": os.getpid(),
    "input_sha256": hashlib.sha256(raw).hexdigest(),
    "semantic_output": result,
}
sys.stdout.write(json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False))
"""


class G10MediatorError(ValueError):
    pass


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise G10MediatorError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise G10MediatorError(f"{name} is not bounded printable text")
    return value


def _sha(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise G10MediatorError(f"{name} must be lowercase SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise G10MediatorError("provenance_refs must be iterable")
    refs = tuple(_text("provenance_ref", item) for item in values)
    if not refs or len(set(refs)) != len(refs):
        raise G10MediatorError("provenance_refs must be non-empty and unique")
    return tuple(sorted(refs))


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
        raise G10MediatorError("value is not canonical-JSON encodable") from exc
    if len(encoded.encode("utf-8")) > _MAX_BYTES:
        raise G10MediatorError("canonical JSON exceeds size bound")
    return encoded


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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
        raise G10MediatorError(f"{name} lacks valid factory origin")


def _strict_json(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_BYTES:
        raise G10MediatorError("exact bounded wire bytes required")

    def no_constants(value: str) -> None:
        raise G10MediatorError(f"non-finite JSON constant is not admissible: {value}")

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise G10MediatorError(f"duplicate JSON key is not admissible: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=no_constants,
        )
    except G10MediatorError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise G10MediatorError("invalid mediator wire JSON") from exc


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentSemanticMediatorReceipt:
    plan_sha256: str
    trial_position: int
    semantic_slot_ref: str
    canonical_semantic_json: str
    semantic_sha256: str
    raw_payload_sha256: str
    semantic_class: str
    source_range_sha256: str
    source_event_sequence: int
    source_process_identity: str
    runtime_witness_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = SEMANTIC_MEDIATOR_RECEIPT_SCHEMA
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    whole_system_acceptance = False

    @classmethod
    def observe(
        cls,
        *,
        plan: PostSelectionSemanticSlotPlan,
        broadcast: BroadcastEnvelope,
        source_range: IndependentEventSourceRangeReceipt,
        uptake_receipt: CellUptakeReceipt,
        semantic_payload: bytes,
        trial_position: int,
        source_process_identity: str,
        provenance_refs: Iterable[str],
    ) -> "IndependentSemanticMediatorReceipt":
        validate_semantic_slot_plan(plan)
        if type(broadcast) is not BroadcastEnvelope:
            raise G10MediatorError("exact broadcast envelope required")
        if broadcast.sha256() != plan.broadcast_sha256 or broadcast.broadcast_id != plan.broadcast_id:
            raise G10MediatorError("broadcast differs from frozen semantic slot plan")
        if type(uptake_receipt) is not CellUptakeReceipt:
            raise G10MediatorError("exact factory CellUptakeReceipt required")
        try:
            uptake_receipt.assert_broadcast_binding(broadcast)
        except GWTUptakeError as exc:
            raise G10MediatorError("semantic uptake receipt is not factory-valid for frozen broadcast") from exc
        try:
            validate_independent_event_source_range(source_range)
        except ValueError as exc:
            raise G10MediatorError("source range is not factory-valid") from exc
        source_identity = _text("source_process_identity", source_process_identity)
        if source_range.observer_identity != source_identity:
            raise G10MediatorError("source range observer is not the semantic source process")
        if type(semantic_payload) is not bytes or not semantic_payload or len(semantic_payload) > _MAX_BYTES:
            raise G10MediatorError("exact bounded semantic payload bytes required")
        if type(trial_position) is not int or not 1 <= trial_position <= 4:
            raise G10MediatorError("trial_position must be 1..4")

        raw_sha = hashlib.sha256(semantic_payload).hexdigest()
        if (
            uptake_receipt.delivery_status != "DELIVERED"
            or uptake_receipt.uptake_status != "UPTAKEN"
            or uptake_receipt.cell_id != plan.recipient_cell_id
            or uptake_receipt.downstream_ref != plan.semantic_slot_ref
            or uptake_receipt.downstream_sha256 != raw_sha
        ):
            raise G10MediatorError("factory-valid uptake does not bind exact semantic slot bytes")
        matching = tuple(
            event
            for event in source_range.events
            if event.event_kind == SOURCE_EVENT_GWT_REENTRY
            and event.payload_sha256 == raw_sha
        )
        if len(matching) != 1:
            raise G10MediatorError(
                "source range must contain exactly one GWT_REENTRY event bound to semantic payload bytes"
            )
        event = matching[0]
        witness = event.runtime_witness
        if witness is None:
            raise G10MediatorError("semantic source event lacks runtime witness")
        try:
            validate_gwt_runtime_witness_receipt(witness)
        except ValueError as exc:
            raise G10MediatorError("semantic source event runtime witness is not factory-valid") from exc
        if witness.classification != LIVE_GWT_PATH_OBSERVED:
            raise G10MediatorError("semantic source event requires full DELIVERY->UPTAKE->REENTRY")
        if witness.identity.process_identity != source_identity:
            raise G10MediatorError("runtime witness was not observed by semantic source process")
        if witness.uptake_receipt_sha256 != uptake_receipt.sha256():
            raise G10MediatorError("source runtime witness does not bind exact semantic uptake receipt")
        if (
            witness.broadcast_id != plan.broadcast_id
            or witness.broadcast_sha256 != plan.broadcast_sha256
            or witness.recipient_cell_id != plan.recipient_cell_id
        ):
            raise G10MediatorError("semantic source event does not bind frozen semantic slot plan")
        canonical, semantic_sha, semantic_class = plan.payload_oracle.classify(semantic_payload)
        if semantic_class == plan.payload_oracle.unknown_value:
            raise G10MediatorError("frozen semantic oracle returned UNKNOWN")
        if semantic_class != plan.trial_semantic_order[trial_position - 1]:
            raise G10MediatorError("mediated semantic class violates preregistered trial order")

        value = cls(
            plan_sha256=plan.sha256(),
            trial_position=trial_position,
            semantic_slot_ref=plan.semantic_slot_ref,
            canonical_semantic_json=canonical,
            semantic_sha256=semantic_sha,
            raw_payload_sha256=raw_sha,
            semantic_class=semantic_class,
            source_range_sha256=source_range.sha256(),
            source_event_sequence=event.source_sequence,
            source_process_identity=source_identity,
            runtime_witness_sha256=witness.sha256(),
            exact_source_sha256=witness.identity.exact_source_sha256,
            boot_id_sha256=witness.identity.boot_id_sha256,
            provenance_refs=tuple(provenance_refs),
        )
        return _seal(value, _MEDIATOR_FACTORY)

    def __post_init__(self) -> None:
        for name in (
            "plan_sha256",
            "semantic_sha256",
            "raw_payload_sha256",
            "source_range_sha256",
            "runtime_witness_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if type(self.trial_position) is not int or not 1 <= self.trial_position <= 4:
            raise G10MediatorError("trial_position must be 1..4")
        if type(self.source_event_sequence) is not int or self.source_event_sequence < 1:
            raise G10MediatorError("source_event_sequence must be positive")
        for name in ("semantic_slot_ref", "semantic_class", "source_process_identity"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        semantic = _strict_json(self.canonical_semantic_json.encode("utf-8"))
        canonical = _canonical_json(semantic)
        if canonical != self.canonical_semantic_json:
            raise G10MediatorError("semantic JSON is not canonical")
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != self.semantic_sha256:
            raise G10MediatorError("semantic_sha256 mismatch")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_sha256": self.plan_sha256,
            "trial_position": self.trial_position,
            "semantic_slot_ref": self.semantic_slot_ref,
            "canonical_semantic_json": self.canonical_semantic_json,
            "semantic_sha256": self.semantic_sha256,
            "raw_payload_sha256": self.raw_payload_sha256,
            "semantic_class": self.semantic_class,
            "source_range_sha256": self.source_range_sha256,
            "source_event_sequence": self.source_event_sequence,
            "source_process_identity": self.source_process_identity,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def to_wire(self) -> bytes:
        _validate_seal(self, IndependentSemanticMediatorReceipt, _MEDIATOR_FACTORY, "semantic mediator")
        body = self.as_dict()
        envelope = {
            "schema": SEMANTIC_MEDIATOR_WIRE_SCHEMA,
            "body": body,
            "body_sha256": _digest(body),
        }
        return _canonical_json(envelope).encode("utf-8")


def validate_semantic_mediator_receipt(value: IndependentSemanticMediatorReceipt) -> None:
    _validate_seal(value, IndependentSemanticMediatorReceipt, _MEDIATOR_FACTORY, "semantic mediator")


@dataclass(frozen=True, slots=True, kw_only=True)
class MediatedSemanticState:
    plan_sha256: str
    trial_position: int
    canonical_semantic_json: str
    semantic_sha256: str
    raw_payload_sha256: str
    semantic_class: str
    source_range_sha256: str
    source_event_sequence: int
    source_process_identity: str
    runtime_witness_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    wire_sha256: str
    trial_process_identity: str
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = MEDIATED_SEMANTIC_STATE_SCHEMA
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    whole_system_acceptance = False

    @classmethod
    def from_wire(
        cls,
        *,
        plan: PostSelectionSemanticSlotPlan,
        wire: bytes,
        trial_process_identity: str,
    ) -> "MediatedSemanticState":
        validate_semantic_slot_plan(plan)
        value = _strict_json(wire)
        if type(value) is not dict or set(value) != {"schema", "body", "body_sha256"}:
            raise G10MediatorError("invalid mediator wire envelope")
        if value["schema"] != SEMANTIC_MEDIATOR_WIRE_SCHEMA or type(value["body"]) is not dict:
            raise G10MediatorError("invalid mediator wire schema")
        if value["body_sha256"] != _digest(value["body"]):
            raise G10MediatorError("mediator wire body digest mismatch")
        body = value["body"]
        required = {
            "schema",
            "plan_sha256",
            "trial_position",
            "semantic_slot_ref",
            "canonical_semantic_json",
            "semantic_sha256",
            "raw_payload_sha256",
            "semantic_class",
            "source_range_sha256",
            "source_event_sequence",
            "source_process_identity",
            "runtime_witness_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "provenance_refs",
        }
        if set(body) != required or body["schema"] != SEMANTIC_MEDIATOR_RECEIPT_SCHEMA:
            raise G10MediatorError("mediator wire body shape mismatch")
        if body["plan_sha256"] != plan.sha256() or body["semantic_slot_ref"] != plan.semantic_slot_ref:
            raise G10MediatorError("mediator wire does not bind frozen semantic plan")
        pos = body["trial_position"]
        if type(pos) is not int or not 1 <= pos <= 4:
            raise G10MediatorError("wire trial_position must be 1..4")
        semantic = _strict_json(body["canonical_semantic_json"].encode("utf-8"))
        canonical = _canonical_json(semantic)
        if canonical != body["canonical_semantic_json"]:
            raise G10MediatorError("wire semantic JSON is not canonical")
        semantic_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if semantic_sha != body["semantic_sha256"]:
            raise G10MediatorError("wire semantic digest mismatch")
        _, oracle_sha, semantic_class = plan.payload_oracle.classify(canonical.encode("utf-8"))
        if oracle_sha != semantic_sha or semantic_class != body["semantic_class"]:
            raise G10MediatorError("wire semantic class is not frozen-oracle derived")
        if semantic_class != plan.trial_semantic_order[pos - 1]:
            raise G10MediatorError("wire semantic class violates preregistered order")
        source_identity = _text("source_process_identity", body["source_process_identity"])
        trial_identity = _text("trial_process_identity", trial_process_identity)
        if source_identity == trial_identity:
            raise G10MediatorError("source and trial process identities must differ")

        state = cls(
            plan_sha256=body["plan_sha256"],
            trial_position=pos,
            canonical_semantic_json=canonical,
            semantic_sha256=semantic_sha,
            raw_payload_sha256=_sha("raw_payload_sha256", body["raw_payload_sha256"]),
            semantic_class=semantic_class,
            source_range_sha256=_sha("source_range_sha256", body["source_range_sha256"]),
            source_event_sequence=body["source_event_sequence"],
            source_process_identity=source_identity,
            runtime_witness_sha256=_sha("runtime_witness_sha256", body["runtime_witness_sha256"]),
            exact_source_sha256=_sha("exact_source_sha256", body["exact_source_sha256"]),
            boot_id_sha256=_sha("boot_id_sha256", body["boot_id_sha256"]),
            wire_sha256=hashlib.sha256(wire).hexdigest(),
            trial_process_identity=trial_identity,
        )
        return _seal(state, _STATE_FACTORY)

    def __post_init__(self) -> None:
        for name in (
            "plan_sha256",
            "semantic_sha256",
            "raw_payload_sha256",
            "source_range_sha256",
            "runtime_witness_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "wire_sha256",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if type(self.trial_position) is not int or not 1 <= self.trial_position <= 4:
            raise G10MediatorError("trial_position must be 1..4")
        if type(self.source_event_sequence) is not int or self.source_event_sequence < 1:
            raise G10MediatorError("source_event_sequence must be positive")
        for name in ("semantic_class", "source_process_identity", "trial_process_identity"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_sha256": self.plan_sha256,
            "trial_position": self.trial_position,
            "canonical_semantic_json": self.canonical_semantic_json,
            "semantic_sha256": self.semantic_sha256,
            "raw_payload_sha256": self.raw_payload_sha256,
            "semantic_class": self.semantic_class,
            "source_range_sha256": self.source_range_sha256,
            "source_event_sequence": self.source_event_sequence,
            "source_process_identity": self.source_process_identity,
            "runtime_witness_sha256": self.runtime_witness_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "wire_sha256": self.wire_sha256,
            "trial_process_identity": self.trial_process_identity,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_mediated_semantic_state(value: MediatedSemanticState) -> None:
    _validate_seal(value, MediatedSemanticState, _STATE_FACTORY, "mediated semantic state")


@dataclass(frozen=True, slots=True, kw_only=True)
class MediatedExecutionReceipt:
    state_sha256: str
    executor_plan_sha256: str
    executor_input_sha256: str
    worker_source_sha256: str
    child_pid: int
    environment_keys: tuple[str, ...]
    semantic_output_sha256: str
    outcome_class: str
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = MEDIATED_EXECUTION_RECEIPT_SCHEMA
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in (
            "state_sha256",
            "executor_plan_sha256",
            "executor_input_sha256",
            "worker_source_sha256",
            "semantic_output_sha256",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if type(self.child_pid) is not int or self.child_pid < 1:
            raise G10MediatorError("child_pid must be positive")
        keys = tuple(_text("environment_key", key) for key in self.environment_keys)
        if keys != ("PYTHONHASHSEED", "PYTHONIOENCODING"):
            raise G10MediatorError("executor environment keys differ from sanitized ABI")
        object.__setattr__(self, "environment_keys", keys)
        object.__setattr__(self, "outcome_class", _text("outcome_class", self.outcome_class))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "state_sha256": self.state_sha256,
            "executor_plan_sha256": self.executor_plan_sha256,
            "executor_input_sha256": self.executor_input_sha256,
            "worker_source_sha256": self.worker_source_sha256,
            "child_pid": self.child_pid,
            "environment_keys": list(self.environment_keys),
            "semantic_output_sha256": self.semantic_output_sha256,
            "outcome_class": self.outcome_class,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def execute_mediated_reentry_only(
    *,
    executor_plan: ReentryOnlyExecutorPlan,
    semantic_state: MediatedSemanticState,
) -> MediatedExecutionReceipt:
    validate_executor_plan(executor_plan)
    validate_mediated_semantic_state(semantic_state)
    request = {
        "schema": "FRANKENSTEIN2_G10_MEDIATED_EXECUTOR_INPUT/v1",
        "executor_plan_sha256": executor_plan.sha256(),
        "task_context_sha256": executor_plan.task_context_sha256,
        "runtime_pre_state_sha256": executor_plan.runtime_pre_state_sha256,
        "semantic_state_canonical_json": semantic_state.canonical_semantic_json,
        "semantic_field_name": executor_plan.semantic_field_name,
        "decision_mapping": list(executor_plan.decision_mapping),
    }
    raw = _canonical_json(request).encode("utf-8")
    env = {
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
    }
    process = subprocess.run(
        [sys.executable, "-I", "-c", _WORKER_SOURCE],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if process.returncode != 0:
        raise G10MediatorError(
            f"mediated executor failed rc={process.returncode}: "
            f"{process.stderr.decode('utf-8', errors='replace')[:1000]}"
        )
    output = _strict_json(process.stdout)
    if type(output) is not dict or set(output) != {"pid", "input_sha256", "semantic_output"}:
        raise G10MediatorError("invalid mediated executor output shape")
    if output["input_sha256"] != hashlib.sha256(raw).hexdigest():
        raise G10MediatorError("mediated executor input digest mismatch")
    semantic_output = output["semantic_output"]
    if type(semantic_output) is not dict or set(semantic_output) != {"decision"}:
        raise G10MediatorError("invalid semantic output")
    decision = _text("decision", semantic_output["decision"])
    receipt = MediatedExecutionReceipt(
        state_sha256=semantic_state.sha256(),
        executor_plan_sha256=executor_plan.sha256(),
        executor_input_sha256=hashlib.sha256(raw).hexdigest(),
        worker_source_sha256=hashlib.sha256(_WORKER_SOURCE.encode("utf-8")).hexdigest(),
        child_pid=output["pid"],
        environment_keys=tuple(sorted(env)),
        semantic_output_sha256=_digest(semantic_output),
        outcome_class=decision,
    )
    return _seal(receipt, _EXECUTION_FACTORY)


def validate_mediated_execution_receipt(value: MediatedExecutionReceipt) -> None:
    _validate_seal(value, MediatedExecutionReceipt, _EXECUTION_FACTORY, "mediated execution receipt")


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
        "semantic_payload",
        "payload_ref",
        "payload_sha256",
        "raw_payload_sha256",
        "semantic_class",
        "trial_position",
        "arm",
        "condition",
        "source_range_sha256",
        "source_event_sequence",
        "source_process_identity",
        "runtime_witness_sha256",
        "wire_sha256",
        "broadcast_id",
        "broadcast_sha256",
        "expected_outcome",
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentSemanticMediatorCrossoverCandidate:
    semantic_order: tuple[str, str, str, str]
    outcome_order: tuple[str, str, str, str]
    raw_payload_sha256s: tuple[str, str, str, str]
    wire_sha256s: tuple[str, str, str, str]
    source_process_identities: tuple[str, str, str, str]
    trial_process_identities: tuple[str, str, str, str]
    child_pids: tuple[int, int, int, int]
    exact_source_sha256: str
    boot_id_sha256: str
    observed_mapping: tuple[tuple[str, str], ...]
    provenance_refs: tuple[str, ...]
    classification: str
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)

    schema = "FRANKENSTEIN2_G10_INDEPENDENT_SEMANTIC_MEDIATOR_CROSSOVER/v1"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if len(self.semantic_order) != 4 or len(self.outcome_order) != 4:
            raise G10MediatorError("crossover requires exactly four trials")
        for name in ("raw_payload_sha256s", "wire_sha256s"):
            values = tuple(_sha(name, value) for value in getattr(self, name))
            if len(values) != 4 or len(set(values)) != 4:
                raise G10MediatorError(f"{name} must contain four distinct digests")
            object.__setattr__(self, name, values)
        for name in ("source_process_identities", "trial_process_identities"):
            values = tuple(_text(name, value) for value in getattr(self, name))
            if len(values) != 4 or len(set(values)) != 4:
                raise G10MediatorError(f"{name} must contain four distinct identities")
            object.__setattr__(self, name, values)
        if set(self.source_process_identities) & set(self.trial_process_identities):
            raise G10MediatorError("source and trial process identity sets must be disjoint")
        if len(self.child_pids) != 4 or any(type(pid) is not int or pid < 1 for pid in self.child_pids):
            raise G10MediatorError("four positive child PIDs required")
        if len(set(self.child_pids)) != 4:
            raise G10MediatorError("executor child PIDs must be fresh per trial")
        object.__setattr__(self, "exact_source_sha256", _sha("exact_source_sha256", self.exact_source_sha256))
        object.__setattr__(self, "boot_id_sha256", _sha("boot_id_sha256", self.boot_id_sha256))
        mapping = tuple(
            sorted(
                (_text("semantic_class", semantic), _text("outcome_class", outcome))
                for semantic, outcome in self.observed_mapping
            )
        )
        if len(mapping) < 2 or len({semantic for semantic, _ in mapping}) != len(mapping):
            raise G10MediatorError("observed mapping requires at least two unique semantic classes")
        object.__setattr__(self, "observed_mapping", mapping)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))
        object.__setattr__(self, "classification", _text("classification", self.classification))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "semantic_order": list(self.semantic_order),
            "outcome_order": list(self.outcome_order),
            "raw_payload_sha256s": list(self.raw_payload_sha256s),
            "wire_sha256s": list(self.wire_sha256s),
            "source_process_identities": list(self.source_process_identities),
            "trial_process_identities": list(self.trial_process_identities),
            "child_pids": list(self.child_pids),
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "observed_mapping": [list(item) for item in self.observed_mapping],
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_independent_semantic_mediator_crossover(
    *,
    plan: PostSelectionSemanticSlotPlan,
    states: tuple[MediatedSemanticState, MediatedSemanticState, MediatedSemanticState, MediatedSemanticState],
    execution_receipts: tuple[
        MediatedExecutionReceipt,
        MediatedExecutionReceipt,
        MediatedExecutionReceipt,
        MediatedExecutionReceipt,
    ],
    provenance_refs: Iterable[str],
) -> IndependentSemanticMediatorCrossoverCandidate:
    validate_semantic_slot_plan(plan)
    if type(states) is not tuple or len(states) != 4:
        raise G10MediatorError("states must contain exactly four mediated trials")
    if type(execution_receipts) is not tuple or len(execution_receipts) != 4:
        raise G10MediatorError("execution_receipts must contain exactly four trials")
    for state in states:
        validate_mediated_semantic_state(state)
    for receipt in execution_receipts:
        validate_mediated_execution_receipt(receipt)
    if tuple(state.trial_position for state in states) != (1, 2, 3, 4):
        raise G10MediatorError("mediated trials must be bound in preregistered physical order")
    semantic_order = tuple(state.semantic_class for state in states)
    if semantic_order != plan.trial_semantic_order:
        raise G10MediatorError("mediated semantic order differs from frozen plan")
    for state, receipt in zip(states, execution_receipts):
        if receipt.state_sha256 != state.sha256():
            raise G10MediatorError("execution receipt does not bind corresponding mediated state")
        if receipt.executor_plan_sha256 != execution_receipts[0].executor_plan_sha256:
            raise G10MediatorError("executor plan changed across crossover")
    mapping: dict[str, str] = {}
    for state, receipt in zip(states, execution_receipts):
        prior = mapping.setdefault(state.semantic_class, receipt.outcome_class)
        if prior != receipt.outcome_class:
            raise G10MediatorError("outcome changed within one semantic class")
    if len(mapping) < 2 or len(set(mapping.values())) < 2:
        raise G10MediatorError("between-class behavioral discrimination was not observed")
    exact_sources = {state.exact_source_sha256 for state in states}
    boots = {state.boot_id_sha256 for state in states}
    if len(exact_sources) != 1 or len(boots) != 1:
        raise G10MediatorError("crossover source/boot identity changed across trials")
    candidate = IndependentSemanticMediatorCrossoverCandidate(
        semantic_order=semantic_order,  # type: ignore[arg-type]
        outcome_order=tuple(receipt.outcome_class for receipt in execution_receipts),  # type: ignore[arg-type]
        raw_payload_sha256s=tuple(state.raw_payload_sha256 for state in states),  # type: ignore[arg-type]
        wire_sha256s=tuple(state.wire_sha256 for state in states),  # type: ignore[arg-type]
        source_process_identities=tuple(state.source_process_identity for state in states),  # type: ignore[arg-type]
        trial_process_identities=tuple(state.trial_process_identity for state in states),  # type: ignore[arg-type]
        child_pids=tuple(receipt.child_pid for receipt in execution_receipts),  # type: ignore[arg-type]
        exact_source_sha256=next(iter(exact_sources)),
        boot_id_sha256=next(iter(boots)),
        observed_mapping=tuple(mapping.items()),
        provenance_refs=tuple(provenance_refs),
        classification=MEDIATOR_AUTHORITY_CANDIDATE,
    )
    return _seal(candidate, _EXECUTION_FACTORY)


def validate_independent_semantic_mediator_crossover(
    value: IndependentSemanticMediatorCrossoverCandidate,
) -> None:
    _validate_seal(
        value,
        IndependentSemanticMediatorCrossoverCandidate,
        _EXECUTION_FACTORY,
        "independent semantic mediator crossover",
    )

__all__ = [
    "FORBIDDEN_BEHAVIORAL_INPUT_KEYS",
    "G10MediatorError",
    "IndependentSemanticMediatorCrossoverCandidate",
    "IndependentSemanticMediatorReceipt",
    "MEDIATOR_AUTHORITY_CANDIDATE",
    "MediatedExecutionReceipt",
    "MediatedSemanticState",
    "behavioral_input_keys",
    "bind_independent_semantic_mediator_crossover",
    "execute_mediated_reentry_only",
    "validate_independent_semantic_mediator_crossover",
    "validate_mediated_execution_receipt",
    "validate_mediated_semantic_state",
    "validate_semantic_mediator_receipt",
]
