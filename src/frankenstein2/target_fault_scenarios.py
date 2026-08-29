"""Deterministic Target Host Reality Twin fault-scenario primitives.

F2-WP-1204 generation 1.

This module deliberately does not mutate a real host, device, session, network, service,
filesystem, package manager or process.  It compiles typed fault specifications into an
immutable deterministic timeline and replays that timeline into a noncanonical projection.
The resulting evidence is T0/T2 preparation only and can never mint physical-host,
CompletionGate, EffectGate, GRID/GWT/J-Space or whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

FAULT_SPEC_SCHEMA = "FRANKENSTEIN2_FAULT_SPEC/v1"
FAULT_EVENT_SCHEMA = "FRANKENSTEIN2_FAULT_EVENT/v1"
FAULT_SCENARIO_SCHEMA = "FRANKENSTEIN2_FAULT_SCENARIO/v1"
FAULT_REPLAY_SCHEMA = "FRANKENSTEIN2_FAULT_REPLAY_RESULT/v1"
FAULT_REPLAY_CLASSIFICATION = "SIMULATED_FAULT_TIMELINE_NO_PHYSICAL_OR_COMPLETION_CREDIT"

PERMISSION = "PERMISSION"
DEVICE = "DEVICE"
SESSION_SERVICE = "SESSION_SERVICE"
NETWORK_BRIDGE = "NETWORK_BRIDGE"
FILESYSTEM_PACKAGE = "FILESYSTEM_PACKAGE"
PROCESS_LIFECYCLE = "PROCESS_LIFECYCLE"
TIME = "TIME"

PERMISSION_DENY = "PERMISSION_DENY"
PERMISSION_REVOKE = "PERMISSION_REVOKE"
STALE_GENERATION = "STALE_GENERATION"
DEVICE_ABSENT = "DEVICE_ABSENT"
DEVICE_LATE = "DEVICE_LATE"
DEVICE_REMOVE = "DEVICE_REMOVE"
DEVICE_READD = "DEVICE_READD"
DEFAULT_ROUTE_CHANGE = "DEFAULT_ROUTE_CHANGE"
DEVICE_EBUSY = "DEVICE_EBUSY"
PIPEWIRE_RESTART = "PIPEWIRE_RESTART"
WIREPLUMBER_RESTART = "WIREPLUMBER_RESTART"
PORTAL_RESTART = "PORTAL_RESTART"
USER_MANAGER_RESTART = "USER_MANAGER_RESTART"
NETWORK_LATENCY = "NETWORK_LATENCY"
NETWORK_LOSS = "NETWORK_LOSS"
NETWORK_RESET = "NETWORK_RESET"
DNS_FAILURE = "DNS_FAILURE"
BRIDGE_DISCONNECT = "BRIDGE_DISCONNECT"
BRIDGE_RECONNECT = "BRIDGE_RECONNECT"
CLOCK_SKEW = "CLOCK_SKEW"
WRONG_OWNERSHIP = "WRONG_OWNERSHIP"
READ_ONLY = "READ_ONLY"
LOW_SPACE = "LOW_SPACE"
PACKAGE_LOCK = "PACKAGE_LOCK"
PARTIAL_INSTALL = "PARTIAL_INSTALL"
PROCESS_KILL = "PROCESS_KILL"
REBOOT = "REBOOT"
LOGOUT_LOGIN = "LOGOUT_LOGIN"
SUSPEND_RESUME = "SUSPEND_RESUME"

ACTION_DOMAIN: dict[str, str] = {
    PERMISSION_DENY: PERMISSION,
    PERMISSION_REVOKE: PERMISSION,
    STALE_GENERATION: PERMISSION,
    DEVICE_ABSENT: DEVICE,
    DEVICE_LATE: DEVICE,
    DEVICE_REMOVE: DEVICE,
    DEVICE_READD: DEVICE,
    DEFAULT_ROUTE_CHANGE: DEVICE,
    DEVICE_EBUSY: DEVICE,
    PIPEWIRE_RESTART: SESSION_SERVICE,
    WIREPLUMBER_RESTART: SESSION_SERVICE,
    PORTAL_RESTART: SESSION_SERVICE,
    USER_MANAGER_RESTART: SESSION_SERVICE,
    NETWORK_LATENCY: NETWORK_BRIDGE,
    NETWORK_LOSS: NETWORK_BRIDGE,
    NETWORK_RESET: NETWORK_BRIDGE,
    DNS_FAILURE: NETWORK_BRIDGE,
    BRIDGE_DISCONNECT: NETWORK_BRIDGE,
    BRIDGE_RECONNECT: NETWORK_BRIDGE,
    CLOCK_SKEW: TIME,
    WRONG_OWNERSHIP: FILESYSTEM_PACKAGE,
    READ_ONLY: FILESYSTEM_PACKAGE,
    LOW_SPACE: FILESYSTEM_PACKAGE,
    PACKAGE_LOCK: FILESYSTEM_PACKAGE,
    PARTIAL_INSTALL: FILESYSTEM_PACKAGE,
    PROCESS_KILL: PROCESS_LIFECYCLE,
    REBOOT: PROCESS_LIFECYCLE,
    LOGOUT_LOGIN: PROCESS_LIFECYCLE,
    SUSPEND_RESUME: PROCESS_LIFECYCLE,
}

# These actions invalidate cached authority/topology and advance the simulated host generation.
GENERATION_INVALIDATING_ACTIONS = frozenset(
    {
        PERMISSION_REVOKE,
        DEVICE_LATE,
        DEVICE_REMOVE,
        DEVICE_READD,
        DEFAULT_ROUTE_CHANGE,
        PIPEWIRE_RESTART,
        WIREPLUMBER_RESTART,
        PORTAL_RESTART,
        USER_MANAGER_RESTART,
        NETWORK_RESET,
        BRIDGE_DISCONNECT,
        BRIDGE_RECONNECT,
        REBOOT,
        LOGOUT_LOGIN,
        SUSPEND_RESUME,
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_EVENTS = 100_000
_MAX_OFFSET_MS = 31 * 24 * 60 * 60 * 1000
_MAX_PARAMETER_BYTES = 64 * 1024
_MAX_GENERATION = 2**63 - 1


class TargetFaultScenarioError(ValueError):
    """Fail-closed validation error for the noncanonical fault-scenario layer."""


def _exact_string(name: str, value: Any) -> str:
    if type(value) is not str:
        raise TargetFaultScenarioError(f"{name} must be an exact concrete string")
    if not value or value != value.strip():
        raise TargetFaultScenarioError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise TargetFaultScenarioError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetFaultScenarioError(f"{name} contains control characters")
    return value


def _literal(name: str, value: Any, expected: str) -> str:
    if type(value) is not str or value != expected:
        raise TargetFaultScenarioError(f"{name} mismatch")
    return value


def _exact_int(name: str, value: Any, *, minimum: int = 0, maximum: int = _MAX_GENERATION) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TargetFaultScenarioError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _sha256_or_unknown(name: str, value: Any) -> str:
    if type(value) is not str:
        raise TargetFaultScenarioError(f"{name} must be an exact concrete string")
    if value == "UNKNOWN":
        return value
    if _SHA256_RE.fullmatch(value) is None:
        raise TargetFaultScenarioError(f"{name} must be UNKNOWN or lowercase 64-hex SHA-256 text")
    return value


def _action(value: Any) -> str:
    value = _exact_string("action", value)
    if value not in ACTION_DOMAIN:
        raise TargetFaultScenarioError(f"unsupported fault action: {value}")
    return value


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
        raise TargetFaultScenarioError("value is not canonical JSON-safe data") from exc
    if len(encoded.encode("utf-8")) > _MAX_PARAMETER_BYTES:
        raise TargetFaultScenarioError(f"canonical JSON exceeds {_MAX_PARAMETER_BYTES} bytes")
    return encoded


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_parameters(parameters: Mapping[str, Any] | None) -> str:
    if parameters is None:
        return "{}"
    if not isinstance(parameters, Mapping):
        raise TargetFaultScenarioError("parameters must be a mapping")
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in parameters.items():
        key = _exact_string("parameter key", raw_key)
        if key in normalized:
            raise TargetFaultScenarioError(f"duplicate parameter key: {key}")
        normalized[key] = raw_value
    encoded = _canonical_json(normalized)
    decoded = json.loads(encoded)
    if type(decoded) is not dict:
        raise TargetFaultScenarioError("parameters must encode to a JSON object")
    return encoded


def _parameter_object(parameters_json: str) -> dict[str, Any]:
    if type(parameters_json) is not str:
        raise TargetFaultScenarioError("parameters_json must be an exact concrete string")
    try:
        value = json.loads(parameters_json)
    except json.JSONDecodeError as exc:
        raise TargetFaultScenarioError("parameters_json is invalid JSON") from exc
    if type(value) is not dict or _canonical_json(value) != parameters_json:
        raise TargetFaultScenarioError("parameters_json must be a canonical JSON object")
    return value


def _require_int_parameter(
    action: str,
    parameters: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if key not in parameters:
        raise TargetFaultScenarioError(f"{action} requires parameter {key}")
    return _exact_int(f"{action}.{key}", parameters[key], minimum=minimum, maximum=maximum)


def _validate_action_parameters(action: str, parameters_json: str, generation_before: int | None = None) -> None:
    parameters = _parameter_object(parameters_json)
    if action == NETWORK_LATENCY:
        _require_int_parameter(action, parameters, "latency_ms", minimum=0, maximum=3_600_000)
    elif action == NETWORK_LOSS:
        _require_int_parameter(action, parameters, "loss_percent", minimum=0, maximum=100)
    elif action == CLOCK_SKEW:
        _require_int_parameter(action, parameters, "offset_ms", minimum=-86_400_000, maximum=86_400_000)
    elif action == LOW_SPACE:
        _require_int_parameter(action, parameters, "remaining_bytes", minimum=0, maximum=_MAX_GENERATION)
    elif action == DEVICE_LATE:
        _require_int_parameter(action, parameters, "delay_ms", minimum=0, maximum=_MAX_OFFSET_MS)
    elif action == STALE_GENERATION:
        if generation_before is None:
            return
        claimed = _require_int_parameter(
            action,
            parameters,
            "claimed_generation",
            minimum=0,
            maximum=_MAX_GENERATION,
        )
        if claimed >= generation_before:
            raise TargetFaultScenarioError(
                "STALE_GENERATION.claimed_generation must be lower than the current simulated generation"
            )


def _spec_identity_payload(
    *,
    action: str,
    target: str,
    offset_ms: int,
    parameters_json: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "target": target,
        "offset_ms": offset_ms,
        "parameters": json.loads(parameters_json),
    }


@dataclass(frozen=True, slots=True)
class FaultSpec:
    """One requested noncanonical fault before generation/sequence assignment."""

    schema: str
    action: str
    target: str
    offset_ms: int
    parameters_json: str

    def __post_init__(self) -> None:
        _literal("fault spec schema", self.schema, FAULT_SPEC_SCHEMA)
        object.__setattr__(self, "action", _action(self.action))
        object.__setattr__(self, "target", _exact_string("target", self.target))
        object.__setattr__(
            self,
            "offset_ms",
            _exact_int("offset_ms", self.offset_ms, minimum=0, maximum=_MAX_OFFSET_MS),
        )
        _validate_action_parameters(self.action, self.parameters_json)

    @classmethod
    def create(
        cls,
        *,
        action: str,
        target: str,
        offset_ms: int,
        parameters: Mapping[str, Any] | None = None,
    ) -> "FaultSpec":
        return cls(
            schema=FAULT_SPEC_SCHEMA,
            action=action,
            target=target,
            offset_ms=offset_ms,
            parameters_json=_canonical_parameters(parameters),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            **_spec_identity_payload(
                action=self.action,
                target=self.target,
                offset_ms=self.offset_ms,
                parameters_json=self.parameters_json,
            ),
        }

    def validated_copy(self) -> "FaultSpec":
        return FaultSpec(
            schema=self.schema,
            action=self.action,
            target=self.target,
            offset_ms=self.offset_ms,
            parameters_json=self.parameters_json,
        )


def _event_identity_payload(
    *,
    sequence: int,
    action: str,
    domain: str,
    target: str,
    offset_ms: int,
    generation_before: int,
    generation_after: int,
    parameters_json: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "action": action,
        "domain": domain,
        "target": target,
        "offset_ms": offset_ms,
        "generation_before": generation_before,
        "generation_after": generation_after,
        "parameters": json.loads(parameters_json),
    }


def _event_id(**identity_fields: Any) -> str:
    return "fault-event:" + _digest(_event_identity_payload(**identity_fields))


@dataclass(frozen=True, slots=True)
class FaultEvent:
    """Compiled fault event with exact sequence and simulated generation transition."""

    schema: str
    event_id: str
    sequence: int
    action: str
    domain: str
    target: str
    offset_ms: int
    generation_before: int
    generation_after: int
    parameters_json: str

    def __post_init__(self) -> None:
        _literal("fault event schema", self.schema, FAULT_EVENT_SCHEMA)
        object.__setattr__(self, "event_id", _exact_string("event_id", self.event_id))
        object.__setattr__(self, "sequence", _exact_int("sequence", self.sequence, minimum=0, maximum=_MAX_EVENTS - 1))
        object.__setattr__(self, "action", _action(self.action))
        expected_domain = ACTION_DOMAIN[self.action]
        if type(self.domain) is not str or self.domain != expected_domain:
            raise TargetFaultScenarioError("fault event domain does not match action")
        object.__setattr__(self, "target", _exact_string("target", self.target))
        object.__setattr__(self, "offset_ms", _exact_int("offset_ms", self.offset_ms, minimum=0, maximum=_MAX_OFFSET_MS))
        object.__setattr__(self, "generation_before", _exact_int("generation_before", self.generation_before))
        object.__setattr__(self, "generation_after", _exact_int("generation_after", self.generation_after))
        expected_delta = 1 if self.action in GENERATION_INVALIDATING_ACTIONS else 0
        if self.generation_after != self.generation_before + expected_delta:
            raise TargetFaultScenarioError("fault event generation transition does not match action semantics")
        _validate_action_parameters(self.action, self.parameters_json, self.generation_before)
        expected_id = _event_id(
            sequence=self.sequence,
            action=self.action,
            domain=self.domain,
            target=self.target,
            offset_ms=self.offset_ms,
            generation_before=self.generation_before,
            generation_after=self.generation_after,
            parameters_json=self.parameters_json,
        )
        if self.event_id != expected_id:
            raise TargetFaultScenarioError("event_id does not bind exact fault event content")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "event_id": self.event_id,
            **_event_identity_payload(
                sequence=self.sequence,
                action=self.action,
                domain=self.domain,
                target=self.target,
                offset_ms=self.offset_ms,
                generation_before=self.generation_before,
                generation_after=self.generation_after,
                parameters_json=self.parameters_json,
            ),
        }

    def validated_copy(self) -> "FaultEvent":
        return FaultEvent(
            schema=self.schema,
            event_id=self.event_id,
            sequence=self.sequence,
            action=self.action,
            domain=self.domain,
            target=self.target,
            offset_ms=self.offset_ms,
            generation_before=self.generation_before,
            generation_after=self.generation_after,
            parameters_json=self.parameters_json,
        )


def _scenario_identity_payload(
    *,
    scenario_name: str,
    seed: int,
    target_profile_digest: str,
    start_generation: int,
    events: Iterable[FaultEvent],
) -> dict[str, Any]:
    return {
        "scenario_name": scenario_name,
        "seed": seed,
        "target_profile_digest": target_profile_digest,
        "start_generation": start_generation,
        "events": [event.as_dict() for event in events],
    }


def _scenario_id(**identity_fields: Any) -> str:
    return "fault-scenario:" + _digest(_scenario_identity_payload(**identity_fields))


@dataclass(frozen=True, slots=True)
class FaultScenario:
    """Immutable deterministic timeline. It is a test projection, never host truth."""

    schema: str
    scenario_id: str
    scenario_name: str
    seed: int
    target_profile_digest: str
    start_generation: int
    events: tuple[FaultEvent, ...]

    def __post_init__(self) -> None:
        _literal("fault scenario schema", self.schema, FAULT_SCENARIO_SCHEMA)
        object.__setattr__(self, "scenario_id", _exact_string("scenario_id", self.scenario_id))
        object.__setattr__(self, "scenario_name", _exact_string("scenario_name", self.scenario_name))
        object.__setattr__(self, "seed", _exact_int("seed", self.seed, minimum=0, maximum=_MAX_GENERATION))
        object.__setattr__(self, "target_profile_digest", _sha256_or_unknown("target_profile_digest", self.target_profile_digest))
        object.__setattr__(self, "start_generation", _exact_int("start_generation", self.start_generation))
        if type(self.events) is not tuple:
            raise TargetFaultScenarioError("events must be an exact tuple")
        if not self.events:
            raise TargetFaultScenarioError("scenario must contain at least one event")
        if len(self.events) > _MAX_EVENTS:
            raise TargetFaultScenarioError(f"scenario exceeds {_MAX_EVENTS} events")

        current_generation = self.start_generation
        previous_offset = -1
        validated: list[FaultEvent] = []
        for expected_sequence, raw_event in enumerate(self.events):
            if type(raw_event) is not FaultEvent:
                raise TargetFaultScenarioError("scenario events must be concrete FaultEvent instances")
            event = raw_event.validated_copy()
            if event.sequence != expected_sequence:
                raise TargetFaultScenarioError("fault event sequence must be contiguous from zero")
            if event.offset_ms < previous_offset:
                raise TargetFaultScenarioError("fault event timeline offsets must be monotonic")
            if event.generation_before != current_generation:
                raise TargetFaultScenarioError("fault event generation chain is discontinuous")
            previous_offset = event.offset_ms
            current_generation = event.generation_after
            validated.append(event)
        object.__setattr__(self, "events", tuple(validated))

        expected_id = _scenario_id(
            scenario_name=self.scenario_name,
            seed=self.seed,
            target_profile_digest=self.target_profile_digest,
            start_generation=self.start_generation,
            events=self.events,
        )
        if self.scenario_id != expected_id:
            raise TargetFaultScenarioError("scenario_id does not bind exact deterministic timeline")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "scenario_id": self.scenario_id,
            **_scenario_identity_payload(
                scenario_name=self.scenario_name,
                seed=self.seed,
                target_profile_digest=self.target_profile_digest,
                start_generation=self.start_generation,
                events=self.events,
            ),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def validated_copy(self) -> "FaultScenario":
        return FaultScenario(
            schema=self.schema,
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            seed=self.seed,
            target_profile_digest=self.target_profile_digest,
            start_generation=self.start_generation,
            events=self.events,
        )


def compile_fault_scenario(
    *,
    scenario_name: str,
    seed: int,
    target_profile_digest: str,
    start_generation: int,
    specs: Iterable[FaultSpec],
) -> FaultScenario:
    """Compile explicit fault specs into a deterministic, generation-bound timeline.

    ``seed`` is identity-bearing even when the caller supplies explicit offsets.  Future
    schedulers may derive offsets from it, but this compiler intentionally performs no
    hidden randomization: same exact inputs always mean the same exact timeline.
    """

    scenario_name = _exact_string("scenario_name", scenario_name)
    seed = _exact_int("seed", seed, minimum=0, maximum=_MAX_GENERATION)
    target_profile_digest = _sha256_or_unknown("target_profile_digest", target_profile_digest)
    start_generation = _exact_int("start_generation", start_generation)
    if isinstance(specs, (str, bytes)):
        raise TargetFaultScenarioError("specs must be an iterable of FaultSpec objects")
    spec_tuple = tuple(specs)
    if not spec_tuple:
        raise TargetFaultScenarioError("at least one FaultSpec is required")
    if len(spec_tuple) > _MAX_EVENTS:
        raise TargetFaultScenarioError(f"scenario exceeds {_MAX_EVENTS} events")

    current_generation = start_generation
    previous_offset = -1
    events: list[FaultEvent] = []
    for sequence, raw_spec in enumerate(spec_tuple):
        if type(raw_spec) is not FaultSpec:
            raise TargetFaultScenarioError("specs must contain concrete FaultSpec instances")
        spec = raw_spec.validated_copy()
        if spec.offset_ms < previous_offset:
            raise TargetFaultScenarioError("FaultSpec offsets must already be monotonic")
        previous_offset = spec.offset_ms
        _validate_action_parameters(spec.action, spec.parameters_json, current_generation)
        generation_after = current_generation + (1 if spec.action in GENERATION_INVALIDATING_ACTIONS else 0)
        identity = {
            "sequence": sequence,
            "action": spec.action,
            "domain": ACTION_DOMAIN[spec.action],
            "target": spec.target,
            "offset_ms": spec.offset_ms,
            "generation_before": current_generation,
            "generation_after": generation_after,
            "parameters_json": spec.parameters_json,
        }
        event = FaultEvent(
            schema=FAULT_EVENT_SCHEMA,
            event_id=_event_id(**identity),
            **identity,
        )
        events.append(event)
        current_generation = generation_after

    scenario_identity = {
        "scenario_name": scenario_name,
        "seed": seed,
        "target_profile_digest": target_profile_digest,
        "start_generation": start_generation,
        "events": tuple(events),
    }
    return FaultScenario(
        schema=FAULT_SCENARIO_SCHEMA,
        scenario_id=_scenario_id(**scenario_identity),
        **scenario_identity,
    )


@dataclass(frozen=True, slots=True)
class FaultReplayResult:
    """Deterministic replay receipt for the simulated timeline only."""

    schema: str
    scenario_id: str
    scenario_sha256: str
    target_profile_digest: str
    start_generation: int
    final_generation: int
    applied_event_ids: tuple[str, ...]
    domain_counts: tuple[tuple[str, int], ...]
    classification: str = FAULT_REPLAY_CLASSIFICATION
    runtime_execution_observed: bool = False
    physical_host_credit: int = 0
    completion_credit: int = 0

    def __post_init__(self) -> None:
        _literal("fault replay schema", self.schema, FAULT_REPLAY_SCHEMA)
        _literal("fault replay classification", self.classification, FAULT_REPLAY_CLASSIFICATION)
        object.__setattr__(self, "scenario_id", _exact_string("scenario_id", self.scenario_id))
        if type(self.scenario_sha256) is not str or _SHA256_RE.fullmatch(self.scenario_sha256) is None:
            raise TargetFaultScenarioError("scenario_sha256 must be lowercase 64-hex SHA-256 text")
        object.__setattr__(self, "target_profile_digest", _sha256_or_unknown("target_profile_digest", self.target_profile_digest))
        object.__setattr__(self, "start_generation", _exact_int("start_generation", self.start_generation))
        object.__setattr__(self, "final_generation", _exact_int("final_generation", self.final_generation))
        if type(self.applied_event_ids) is not tuple or not self.applied_event_ids:
            raise TargetFaultScenarioError("applied_event_ids must be a non-empty tuple")
        for event_id in self.applied_event_ids:
            _exact_string("applied_event_id", event_id)
        if len(set(self.applied_event_ids)) != len(self.applied_event_ids):
            raise TargetFaultScenarioError("applied_event_ids must be unique")
        if type(self.domain_counts) is not tuple:
            raise TargetFaultScenarioError("domain_counts must be a tuple")
        for item in self.domain_counts:
            if type(item) is not tuple or len(item) != 2:
                raise TargetFaultScenarioError("domain_counts items must be (domain, count) tuples")
            _exact_string("domain", item[0])
            _exact_int("domain count", item[1], minimum=0, maximum=_MAX_EVENTS)
        if type(self.runtime_execution_observed) is not bool or self.runtime_execution_observed:
            raise TargetFaultScenarioError("source-level replay cannot claim runtime execution")
        if type(self.physical_host_credit) is not int or self.physical_host_credit != 0:
            raise TargetFaultScenarioError("source-level replay cannot claim physical host credit")
        if type(self.completion_credit) is not int or self.completion_credit != 0:
            raise TargetFaultScenarioError("source-level replay cannot claim completion credit")

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["domain_counts"] = {key: count for key, count in self.domain_counts}
        return value


def replay_fault_scenario(scenario: FaultScenario) -> FaultReplayResult:
    """Validate and replay one scenario without performing any real-world mutation."""

    if type(scenario) is not FaultScenario:
        raise TargetFaultScenarioError("scenario must be a concrete FaultScenario")
    scenario = scenario.validated_copy()
    current_generation = scenario.start_generation
    domain_counts: dict[str, int] = {}
    applied: list[str] = []
    for event in scenario.events:
        # Reconstruct at the consumer boundary so object.__setattr__ drift cannot bypass
        # constructor invariants on frozen dataclasses.
        event = event.validated_copy()
        if event.generation_before != current_generation:
            raise TargetFaultScenarioError("replay encountered stale/out-of-order generation")
        current_generation = event.generation_after
        domain_counts[event.domain] = domain_counts.get(event.domain, 0) + 1
        applied.append(event.event_id)

    return FaultReplayResult(
        schema=FAULT_REPLAY_SCHEMA,
        scenario_id=scenario.scenario_id,
        scenario_sha256=scenario.sha256(),
        target_profile_digest=scenario.target_profile_digest,
        start_generation=scenario.start_generation,
        final_generation=current_generation,
        applied_event_ids=tuple(applied),
        domain_counts=tuple(sorted(domain_counts.items())),
    )
