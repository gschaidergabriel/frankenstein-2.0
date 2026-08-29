"""F2-WP-805 generation-2 recovery-efficiency falsifier repair.

This evaluator-only layer repairs concrete E2 gaps in the generation-1 transfer/recovery
benchmark without expanding its authority. It binds structural holdout families, a typed
perturbation, one exact post-change public start identity, a deterministic finite-microworld
reference plan, trace-derived reuse/replay accounting, and an optional evaluator resource
vector. Tested policy inputs remain the public WP800/G1 surfaces; none of the evaluator
objects in this module are SUT inputs.

Repository-hosted component evidence from this module grants no target-runtime, physical
GRID10, GWT/J-Space, model/provider, training, effect, completion, cognition-superiority or
whole-system credit.
"""
from __future__ import annotations

from collections import deque
from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any

from frankenstein2.cognitive_microworld import (
    EpisodeState,
    MicroWorldFixture,
    ObservationView,
    observation_for_state,
)
from frankenstein2.cognitive_transfer_recovery_benchmark import (
    CHECKPOINT_RESUME,
    COLD_RESTART,
    RecoveryCheckpoint,
    TransferCase,
)

PERTURBATION_SCHEMA = "FRANKENSTEIN2_RECOVERY_PERTURBATION/v2"
FAMILY_VECTOR_SCHEMA = "FRANKENSTEIN2_STRUCTURAL_FAMILY_VECTOR/v2"
START_IDENTITY_SCHEMA = "FRANKENSTEIN2_POSTCHANGE_PUBLIC_START/v2"
SCENARIO_SCHEMA = "FRANKENSTEIN2_RECOVERY_SCENARIO/v2"
REFERENCE_PLAN_SCHEMA = "FRANKENSTEIN2_RECOVERY_REFERENCE_PLAN/v2"
TRACE_STEP_SCHEMA = "FRANKENSTEIN2_RECOVERY_TRACE_STEP/v2"
TRACE_SCHEMA = "FRANKENSTEIN2_RECOVERY_TRACE_RECEIPT/v2"
RESOURCE_SCHEMA = "FRANKENSTEIN2_EVALUATOR_RESOURCE_VECTOR/v2"
RUN_SCHEMA = "FRANKENSTEIN2_RECOVERY_RUN_MEASUREMENT/v2"
COMPARISON_SCHEMA = "FRANKENSTEIN2_MATCHED_RECOVERY_COMPARISON/v2"
SUMMARY_SCHEMA = "FRANKENSTEIN2_RECOVERY_EFFICIENCY_SUMMARY/v2"

EVALUATOR_ONLY = "EVALUATOR_ONLY_NOT_SUT_INPUT_OR_WORLD_AUTHORITY"
PUBLIC_IDENTITY_ONLY = "PUBLIC_OBSERVATION_IDENTITY_NO_WORLD_AUTHORITY"
MEASUREMENT_ONLY = "REPOSITORY_COMPONENT_MEASUREMENT_NO_RUNTIME_OR_COGNITION_AUTHORITY"
SHORTEST_TERMINAL_PATH = "SHORTEST_TERMINAL_PATH"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID = 512
_MAX_COUNT = 1_000_000_000
_MAX_STEPS = 4096
_ALLOWED_MODES = frozenset((COLD_RESTART, CHECKPOINT_RESUME))

_PERTURBATION_ORIGIN = object()
_SCENARIO_ORIGIN = object()
_REFERENCE_ORIGIN = object()
_TRACE_ORIGIN = object()
_RUN_ORIGIN = object()
_COMPARISON_ORIGIN = object()


class RecoveryE2Error(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RecoveryE2Error(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise RecoveryE2Error(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise RecoveryE2Error(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nint(name: str, value: Any, maximum: int = _MAX_COUNT) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise RecoveryE2Error(f"{name} must be a non-negative integer in [0, {maximum}]")
    return value


def _refs(name: str, values: Any, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise RecoveryE2Error(f"{name} must be an immutable tuple")
    if len(values) > _MAX_STEPS:
        raise RecoveryE2Error(f"{name} exceeds bounded reference ceiling")
    out = tuple(_id(f"{name} item", item) for item in values)
    if nonempty and not out:
        raise RecoveryE2Error(f"{name} must not be empty")
    if len(out) != len(set(out)):
        raise RecoveryE2Error(f"{name} contains duplicate references")
    if out != tuple(sorted(out)):
        raise RecoveryE2Error(f"{name} must be in canonical lexical order")
    return out


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class StructuralFamilyVector:
    schema: str
    evidence_source_family: str
    donor_path_family: str
    method_family: str
    classification: str = EVALUATOR_ONLY

    def __post_init__(self) -> None:
        if self.schema != FAMILY_VECTOR_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("family-vector schema/classification mismatch")
        _id("evidence_source_family", self.evidence_source_family)
        _id("donor_path_family", self.donor_path_family)
        _id("method_family", self.method_family)

    @classmethod
    def from_fixture(cls, fixture: MicroWorldFixture) -> "StructuralFamilyVector":
        if type(fixture) is not MicroWorldFixture:
            raise RecoveryE2Error("fixture must be exact concrete MicroWorldFixture")
        return cls(
            FAMILY_VECTOR_SCHEMA,
            fixture.evidence_source_family,
            fixture.donor_path_family,
            fixture.method_family,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def overlaps(self, other: "StructuralFamilyVector") -> tuple[str, ...]:
        if type(other) is not StructuralFamilyVector:
            raise RecoveryE2Error("other must be exact concrete StructuralFamilyVector")
        overlap: list[str] = []
        for field in ("evidence_source_family", "donor_path_family", "method_family"):
            if getattr(self, field) == getattr(other, field):
                overlap.append(field)
        return tuple(overlap)


@dataclass(frozen=True, slots=True)
class RecoveryPerturbation:
    schema: str
    perturbation_id: str
    perturbation_kind: str
    change_generation: int
    source_fixture_id: str
    source_fixture_generation: int
    source_fixture_sha256: str
    target_fixture_id: str
    target_fixture_generation: int
    target_fixture_sha256: str
    changed_component_refs: tuple[str, ...]
    causal_footprint_sha256: str
    classification: str = EVALUATOR_ONLY
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != PERTURBATION_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("perturbation schema/classification mismatch")
        for name, value in (
            ("perturbation_id", self.perturbation_id),
            ("perturbation_kind", self.perturbation_kind),
            ("source_fixture_id", self.source_fixture_id),
            ("target_fixture_id", self.target_fixture_id),
        ):
            _id(name, value)
        for name, value in (
            ("change_generation", self.change_generation),
            ("source_fixture_generation", self.source_fixture_generation),
            ("target_fixture_generation", self.target_fixture_generation),
        ):
            _nint(name, value)
        _sha("source_fixture_sha256", self.source_fixture_sha256)
        _sha("target_fixture_sha256", self.target_fixture_sha256)
        _refs("changed_component_refs", self.changed_component_refs, nonempty=True)
        _sha("causal_footprint_sha256", self.causal_footprint_sha256)
        if self.source_fixture_id == self.target_fixture_id and self.source_fixture_generation == self.target_fixture_generation:
            raise RecoveryE2Error("perturbation requires a source/target identity or generation change")
        if _origin is not _PERTURBATION_ORIGIN:
            raise RecoveryE2Error("RecoveryPerturbation must be sealed by evaluator API")

    @classmethod
    def seal(
        cls,
        *,
        source_fixture: MicroWorldFixture,
        target_fixture: MicroWorldFixture,
        perturbation_kind: str,
        change_generation: int,
        changed_component_refs: tuple[str, ...],
    ) -> "RecoveryPerturbation":
        if type(source_fixture) is not MicroWorldFixture or type(target_fixture) is not MicroWorldFixture:
            raise RecoveryE2Error("source/target fixtures must be exact concrete MicroWorldFixture")
        _id("perturbation_kind", perturbation_kind)
        _nint("change_generation", change_generation)
        refs = _refs("changed_component_refs", changed_component_refs, nonempty=True)
        footprint = _digest(
            {
                "source_fixture_sha256": source_fixture.sha256(),
                "target_fixture_sha256": target_fixture.sha256(),
                "perturbation_kind": perturbation_kind,
                "change_generation": change_generation,
                "changed_component_refs": list(refs),
            }
        )
        body = {
            "perturbation_kind": perturbation_kind,
            "change_generation": change_generation,
            "source_fixture_id": source_fixture.fixture_id,
            "source_fixture_generation": source_fixture.generation,
            "source_fixture_sha256": source_fixture.sha256(),
            "target_fixture_id": target_fixture.fixture_id,
            "target_fixture_generation": target_fixture.generation,
            "target_fixture_sha256": target_fixture.sha256(),
            "changed_component_refs": refs,
            "causal_footprint_sha256": footprint,
        }
        return cls(
            PERTURBATION_SCHEMA,
            "perturbation:" + _digest(body),
            **body,
            _origin=_PERTURBATION_ORIGIN,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PostChangeStartIdentity:
    schema: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    observation_sha256: str
    classification: str = PUBLIC_IDENTITY_ONLY

    def __post_init__(self) -> None:
        if self.schema != START_IDENTITY_SCHEMA or self.classification != PUBLIC_IDENTITY_ONLY:
            raise RecoveryE2Error("start-identity schema/classification mismatch")
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _nint("step_index", self.step_index)
        _sha("observation_sha256", self.observation_sha256)

    @classmethod
    def from_observation(cls, observation: ObservationView) -> "PostChangeStartIdentity":
        if type(observation) is not ObservationView:
            raise RecoveryE2Error("observation must be exact concrete ObservationView")
        return cls(
            START_IDENTITY_SCHEMA,
            observation.episode_id,
            observation.episode_generation,
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            observation.step_index,
            observation.sha256(),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecoveryScenario:
    schema: str
    scenario_id: str
    transfer_case_sha256: str
    source_fixture_sha256: str
    target_fixture_sha256: str
    source_family_vector_sha256: str
    target_family_vector_sha256: str
    perturbation_sha256: str
    postchange_start_sha256: str
    action_budget: int
    classification: str = EVALUATOR_ONLY
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != SCENARIO_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("scenario schema/classification mismatch")
        _id("scenario_id", self.scenario_id)
        for name, value in (
            ("transfer_case_sha256", self.transfer_case_sha256),
            ("source_fixture_sha256", self.source_fixture_sha256),
            ("target_fixture_sha256", self.target_fixture_sha256),
            ("source_family_vector_sha256", self.source_family_vector_sha256),
            ("target_family_vector_sha256", self.target_family_vector_sha256),
            ("perturbation_sha256", self.perturbation_sha256),
            ("postchange_start_sha256", self.postchange_start_sha256),
        ):
            _sha(name, value)
        _nint("action_budget", self.action_budget, _MAX_STEPS)
        if self.action_budget < 1:
            raise RecoveryE2Error("action_budget must be positive")
        if _origin is not _SCENARIO_ORIGIN:
            raise RecoveryE2Error("RecoveryScenario must be sealed by evaluator API")

    @classmethod
    def seal(
        cls,
        *,
        case: TransferCase,
        source_fixture: MicroWorldFixture,
        target_fixture: MicroWorldFixture,
        perturbation: RecoveryPerturbation,
        target_start_state: EpisodeState,
        target_start_observation: ObservationView,
    ) -> "RecoveryScenario":
        if type(case) is not TransferCase:
            raise RecoveryE2Error("case must be exact concrete TransferCase")
        if type(source_fixture) is not MicroWorldFixture or type(target_fixture) is not MicroWorldFixture:
            raise RecoveryE2Error("source/target fixtures must be exact concrete MicroWorldFixture")
        if type(perturbation) is not RecoveryPerturbation:
            raise RecoveryE2Error("perturbation must be exact concrete RecoveryPerturbation")
        if type(target_start_state) is not EpisodeState or type(target_start_observation) is not ObservationView:
            raise RecoveryE2Error("target start state/observation must be exact concrete WP800 values")

        expected_case = (
            source_fixture.fixture_id,
            source_fixture.generation,
            source_fixture.holdout_set_id,
            source_fixture.public_sha256(),
            target_fixture.fixture_id,
            target_fixture.generation,
            target_fixture.holdout_set_id,
            target_fixture.public_sha256(),
        )
        observed_case = (
            case.source_fixture_id,
            case.source_fixture_generation,
            case.source_holdout_set_id,
            case.source_public_fixture_sha256,
            case.target_fixture_id,
            case.target_fixture_generation,
            case.target_holdout_set_id,
            case.target_public_fixture_sha256,
        )
        if observed_case != expected_case:
            raise RecoveryE2Error("transfer case does not bind exact source/target public fixtures")
        expected_perturbation = (
            source_fixture.fixture_id,
            source_fixture.generation,
            source_fixture.sha256(),
            target_fixture.fixture_id,
            target_fixture.generation,
            target_fixture.sha256(),
        )
        observed_perturbation = (
            perturbation.source_fixture_id,
            perturbation.source_fixture_generation,
            perturbation.source_fixture_sha256,
            perturbation.target_fixture_id,
            perturbation.target_fixture_generation,
            perturbation.target_fixture_sha256,
        )
        if observed_perturbation != expected_perturbation:
            raise RecoveryE2Error("perturbation does not bind exact source/target evaluator fixtures")

        source_family = StructuralFamilyVector.from_fixture(source_fixture)
        target_family = StructuralFamilyVector.from_fixture(target_fixture)
        overlap = source_family.overlaps(target_family)
        if overlap:
            raise RecoveryE2Error("structural holdout overlap: " + ",".join(overlap))

        expected_observation = observation_for_state(target_fixture, target_start_state)
        if expected_observation != target_start_observation:
            raise RecoveryE2Error("post-change public start does not match evaluator target state")
        start = PostChangeStartIdentity.from_observation(target_start_observation)
        if (
            start.fixture_id,
            start.fixture_generation,
            start.public_fixture_sha256,
        ) != (
            target_fixture.fixture_id,
            target_fixture.generation,
            target_fixture.public_sha256(),
        ):
            raise RecoveryE2Error("post-change start is not bound to exact target public fixture")

        body = {
            "transfer_case_sha256": case.sha256(),
            "source_fixture_sha256": source_fixture.sha256(),
            "target_fixture_sha256": target_fixture.sha256(),
            "source_family_vector_sha256": source_family.sha256(),
            "target_family_vector_sha256": target_family.sha256(),
            "perturbation_sha256": perturbation.sha256(),
            "postchange_start_sha256": start.sha256(),
            "action_budget": case.action_budget,
        }
        return cls(SCENARIO_SCHEMA, "scenario:" + _digest(body), **body, _origin=_SCENARIO_ORIGIN)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluatorReferencePlan:
    schema: str
    reference_id: str
    scenario_sha256: str
    start_identity_sha256: str
    objective: str
    action_ids: tuple[str, ...]
    terminal_node_id: str
    terminal_evaluator_score: int
    classification: str = EVALUATOR_ONLY
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != REFERENCE_PLAN_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("reference-plan schema/classification mismatch")
        _id("reference_id", self.reference_id)
        _sha("scenario_sha256", self.scenario_sha256)
        _sha("start_identity_sha256", self.start_identity_sha256)
        if self.objective != SHORTEST_TERMINAL_PATH:
            raise RecoveryE2Error("unsupported reference-plan objective")
        if type(self.action_ids) is not tuple or len(self.action_ids) > _MAX_STEPS:
            raise RecoveryE2Error("action_ids must be a bounded immutable tuple")
        for action_id in self.action_ids:
            _id("action_id", action_id)
        _id("terminal_node_id", self.terminal_node_id)
        if type(self.terminal_evaluator_score) is not int:
            raise RecoveryE2Error("terminal_evaluator_score must be an integer")
        if _origin is not _REFERENCE_ORIGIN:
            raise RecoveryE2Error("EvaluatorReferencePlan must be created by evaluator API")

    @classmethod
    def shortest_terminal(
        cls,
        *,
        scenario: RecoveryScenario,
        target_fixture: MicroWorldFixture,
        target_start_state: EpisodeState,
        target_start_observation: ObservationView,
    ) -> "EvaluatorReferencePlan":
        if type(scenario) is not RecoveryScenario:
            raise RecoveryE2Error("scenario must be exact concrete RecoveryScenario")
        if type(target_fixture) is not MicroWorldFixture or type(target_start_state) is not EpisodeState:
            raise RecoveryE2Error("target fixture/state must be exact concrete WP800 values")
        if type(target_start_observation) is not ObservationView:
            raise RecoveryE2Error("target observation must be exact concrete ObservationView")
        if target_fixture.sha256() != scenario.target_fixture_sha256:
            raise RecoveryE2Error("reference fixture does not match scenario target fixture")
        if observation_for_state(target_fixture, target_start_state) != target_start_observation:
            raise RecoveryE2Error("reference start observation does not match evaluator state")
        start = PostChangeStartIdentity.from_observation(target_start_observation)
        if start.sha256() != scenario.postchange_start_sha256:
            raise RecoveryE2Error("reference plan start does not match scenario start")

        start_node = target_start_state.current_node_id
        if target_fixture.node(start_node).terminal:
            actions: tuple[str, ...] = ()
            terminal_node = start_node
        else:
            queue: deque[tuple[str, tuple[str, ...]]] = deque([(start_node, ())])
            visited = {start_node}
            found: tuple[tuple[str, ...], str] | None = None
            transitions = tuple(sorted(target_fixture.transitions, key=lambda r: (r.from_node_id, r.action_id, r.to_node_id)))
            while queue and found is None:
                node_id, path = queue.popleft()
                for rule in transitions:
                    if rule.from_node_id != node_id:
                        continue
                    next_path = path + (rule.action_id,)
                    if len(next_path) > scenario.action_budget:
                        continue
                    next_node = target_fixture.node(rule.to_node_id)
                    if next_node.terminal:
                        found = (next_path, next_node.node_id)
                        break
                    if next_node.node_id not in visited:
                        visited.add(next_node.node_id)
                        queue.append((next_node.node_id, next_path))
            if found is None:
                raise RecoveryE2Error("no terminal reference plan exists within matched action budget")
            actions, terminal_node = found

        body = {
            "scenario_sha256": scenario.sha256(),
            "start_identity_sha256": start.sha256(),
            "objective": SHORTEST_TERMINAL_PATH,
            "action_ids": list(actions),
            "terminal_node_id": terminal_node,
            "terminal_evaluator_score": target_fixture.node(terminal_node).evaluator_score,
        }
        return cls(
            REFERENCE_PLAN_SCHEMA,
            "reference:" + _digest(body),
            scenario.sha256(),
            start.sha256(),
            SHORTEST_TERMINAL_PATH,
            actions,
            terminal_node,
            target_fixture.node(terminal_node).evaluator_score,
            _origin=_REFERENCE_ORIGIN,
        )

    @property
    def action_count(self) -> int:
        return len(self.action_ids)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecoveryTraceStep:
    schema: str
    sequence_index: int
    action_id: str
    work_unit_ref: str
    reuse_source_ref: str | None
    reuse_valid: bool
    classification: str = EVALUATOR_ONLY

    def __post_init__(self) -> None:
        if self.schema != TRACE_STEP_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("trace-step schema/classification mismatch")
        _nint("sequence_index", self.sequence_index, _MAX_STEPS)
        _id("action_id", self.action_id)
        _id("work_unit_ref", self.work_unit_ref)
        if self.reuse_source_ref is not None:
            _id("reuse_source_ref", self.reuse_source_ref)
        if type(self.reuse_valid) is not bool:
            raise RecoveryE2Error("reuse_valid must be a boolean")
        if self.reuse_source_ref is None and self.reuse_valid:
            raise RecoveryE2Error("new work cannot claim reuse_valid without reuse_source_ref")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RecoveryTraceReceipt:
    schema: str
    trace_id: str
    scenario_sha256: str
    start_identity_sha256: str
    steps: tuple[RecoveryTraceStep, ...]
    action_trace_sha256: str
    replayed_steps: int
    valid_reuse_steps: int
    invalid_reuse_steps: int
    repeated_work_steps: int
    classification: str = EVALUATOR_ONLY
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != TRACE_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("trace schema/classification mismatch")
        _id("trace_id", self.trace_id)
        _sha("scenario_sha256", self.scenario_sha256)
        _sha("start_identity_sha256", self.start_identity_sha256)
        if type(self.steps) is not tuple or len(self.steps) > _MAX_STEPS or any(type(x) is not RecoveryTraceStep for x in self.steps):
            raise RecoveryE2Error("steps must be a bounded tuple of exact RecoveryTraceStep values")
        if tuple(step.sequence_index for step in self.steps) != tuple(range(len(self.steps))):
            raise RecoveryE2Error("trace steps must have exact contiguous sequence indexes")
        _sha("action_trace_sha256", self.action_trace_sha256)
        for name, value in (
            ("replayed_steps", self.replayed_steps),
            ("valid_reuse_steps", self.valid_reuse_steps),
            ("invalid_reuse_steps", self.invalid_reuse_steps),
            ("repeated_work_steps", self.repeated_work_steps),
        ):
            _nint(name, value, _MAX_STEPS)
        expected_replayed = sum(step.reuse_source_ref is not None for step in self.steps)
        expected_valid = sum(step.reuse_source_ref is not None and step.reuse_valid for step in self.steps)
        expected_invalid = expected_replayed - expected_valid
        work_units = tuple(step.work_unit_ref for step in self.steps)
        expected_repeated = len(work_units) - len(set(work_units))
        if (self.replayed_steps, self.valid_reuse_steps, self.invalid_reuse_steps, self.repeated_work_steps) != (
            expected_replayed,
            expected_valid,
            expected_invalid,
            expected_repeated,
        ):
            raise RecoveryE2Error("trace-derived reuse/replay metrics mismatch")
        if _origin is not _TRACE_ORIGIN:
            raise RecoveryE2Error("RecoveryTraceReceipt must be sealed by evaluator API")

    @classmethod
    def seal(
        cls,
        *,
        scenario: RecoveryScenario,
        start_identity: PostChangeStartIdentity,
        steps: tuple[RecoveryTraceStep, ...],
    ) -> "RecoveryTraceReceipt":
        if type(scenario) is not RecoveryScenario or type(start_identity) is not PostChangeStartIdentity:
            raise RecoveryE2Error("scenario/start identity must be exact concrete values")
        if start_identity.sha256() != scenario.postchange_start_sha256:
            raise RecoveryE2Error("trace start identity does not match scenario")
        if type(steps) is not tuple or any(type(step) is not RecoveryTraceStep for step in steps):
            raise RecoveryE2Error("steps must be exact concrete RecoveryTraceStep values")
        if len(steps) > scenario.action_budget:
            raise RecoveryE2Error("trace exceeds scenario action budget")
        trace_body = [step.as_dict() for step in steps]
        action_trace_sha = _digest(trace_body)
        replayed = sum(step.reuse_source_ref is not None for step in steps)
        valid = sum(step.reuse_source_ref is not None and step.reuse_valid for step in steps)
        invalid = replayed - valid
        work_units = tuple(step.work_unit_ref for step in steps)
        repeated = len(work_units) - len(set(work_units))
        identity = {
            "scenario_sha256": scenario.sha256(),
            "start_identity_sha256": start_identity.sha256(),
            "action_trace_sha256": action_trace_sha,
        }
        return cls(
            TRACE_SCHEMA,
            "trace:" + _digest(identity),
            scenario.sha256(),
            start_identity.sha256(),
            steps,
            action_trace_sha,
            replayed,
            valid,
            invalid,
            repeated,
            _origin=_TRACE_ORIGIN,
        )

    @property
    def actions_executed(self) -> int:
        return len(self.steps)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "trace_id": self.trace_id,
            "scenario_sha256": self.scenario_sha256,
            "start_identity_sha256": self.start_identity_sha256,
            "steps": [step.as_dict() for step in self.steps],
            "action_trace_sha256": self.action_trace_sha256,
            "replayed_steps": self.replayed_steps,
            "valid_reuse_steps": self.valid_reuse_steps,
            "invalid_reuse_steps": self.invalid_reuse_steps,
            "repeated_work_steps": self.repeated_work_steps,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluatorResourceVector:
    schema: str
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_us: int = 0
    cpu_time_us: int = 0
    peak_rss_bytes: int = 0
    gpu_time_us: int = 0
    io_bytes: int = 0
    classification: str = EVALUATOR_ONLY

    def __post_init__(self) -> None:
        if self.schema != RESOURCE_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise RecoveryE2Error("resource-vector schema/classification mismatch")
        for name in (
            "model_calls",
            "input_tokens",
            "output_tokens",
            "latency_us",
            "cpu_time_us",
            "peak_rss_bytes",
            "gpu_time_us",
            "io_bytes",
        ):
            _nint(name, getattr(self, name))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecoveryRunMeasurementV2:
    schema: str
    run_id: str
    mode: str
    scenario_sha256: str
    start_identity_sha256: str
    reference_plan_sha256: str
    checkpoint_sha256: str | None
    trace_sha256: str
    actions_executed: int
    replayed_steps: int
    valid_reuse_steps: int
    invalid_reuse_steps: int
    repeated_work_steps: int
    final_evaluator_score: int
    terminal: bool
    action_regret: int
    score_regret: int
    resource_vector: EvaluatorResourceVector | None
    runtime_credit: int = 0
    physical_grid10_credit: int = 0
    gwt_jspace_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = MEASUREMENT_ONLY
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != RUN_SCHEMA or self.classification != MEASUREMENT_ONLY:
            raise RecoveryE2Error("run schema/classification mismatch")
        _id("run_id", self.run_id)
        if self.mode not in _ALLOWED_MODES:
            raise RecoveryE2Error("mode is not admitted")
        for name, value in (
            ("scenario_sha256", self.scenario_sha256),
            ("start_identity_sha256", self.start_identity_sha256),
            ("reference_plan_sha256", self.reference_plan_sha256),
            ("trace_sha256", self.trace_sha256),
        ):
            _sha(name, value)
        if self.checkpoint_sha256 is not None:
            _sha("checkpoint_sha256", self.checkpoint_sha256)
        if self.mode == CHECKPOINT_RESUME and self.checkpoint_sha256 is None:
            raise RecoveryE2Error("checkpoint-resume requires checkpoint identity")
        if self.mode == COLD_RESTART and self.checkpoint_sha256 is not None:
            raise RecoveryE2Error("cold restart cannot claim checkpoint consumption")
        for name in (
            "actions_executed",
            "replayed_steps",
            "valid_reuse_steps",
            "invalid_reuse_steps",
            "repeated_work_steps",
        ):
            _nint(name, getattr(self, name), _MAX_STEPS)
        if type(self.final_evaluator_score) is not int or type(self.action_regret) is not int or type(self.score_regret) is not int:
            raise RecoveryE2Error("score/regret values must be integers")
        if type(self.terminal) is not bool:
            raise RecoveryE2Error("terminal must be a boolean")
        if self.resource_vector is not None and type(self.resource_vector) is not EvaluatorResourceVector:
            raise RecoveryE2Error("resource_vector must be exact EvaluatorResourceVector or None")
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_grid10_credit,
                self.gwt_jspace_credit,
                self.effect_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance is not False:
            raise RecoveryE2Error("repository measurement cannot mint higher-scope credit")
        if _origin is not _RUN_ORIGIN:
            raise RecoveryE2Error("RecoveryRunMeasurementV2 must be created by evaluator API")

    @classmethod
    def measure(
        cls,
        *,
        run_id: str,
        mode: str,
        scenario: RecoveryScenario,
        start_identity: PostChangeStartIdentity,
        reference_plan: EvaluatorReferencePlan,
        trace: RecoveryTraceReceipt,
        checkpoint: RecoveryCheckpoint | None,
        final_evaluator_score: int,
        terminal: bool,
        resource_vector: EvaluatorResourceVector | None = None,
    ) -> "RecoveryRunMeasurementV2":
        if type(scenario) is not RecoveryScenario or type(start_identity) is not PostChangeStartIdentity:
            raise RecoveryE2Error("scenario/start identity must be exact values")
        if type(reference_plan) is not EvaluatorReferencePlan or type(trace) is not RecoveryTraceReceipt:
            raise RecoveryE2Error("reference plan/trace must be exact evaluator values")
        if mode not in _ALLOWED_MODES:
            raise RecoveryE2Error("mode is not admitted")
        if start_identity.sha256() != scenario.postchange_start_sha256:
            raise RecoveryE2Error("run start identity does not match scenario")
        if reference_plan.scenario_sha256 != scenario.sha256() or reference_plan.start_identity_sha256 != start_identity.sha256():
            raise RecoveryE2Error("reference plan does not bind exact scenario/start")
        if trace.scenario_sha256 != scenario.sha256() or trace.start_identity_sha256 != start_identity.sha256():
            raise RecoveryE2Error("trace does not bind exact scenario/start")
        checkpoint_sha: str | None = None
        if mode == CHECKPOINT_RESUME:
            if type(checkpoint) is not RecoveryCheckpoint:
                raise RecoveryE2Error("checkpoint-resume requires exact RecoveryCheckpoint")
            if checkpoint.transfer_case_sha256 != scenario.transfer_case_sha256:
                raise RecoveryE2Error("checkpoint transfer case does not match scenario")
            checkpoint_start = (
                checkpoint.episode_id,
                checkpoint.episode_generation,
                checkpoint.target_fixture_id,
                checkpoint.target_fixture_generation,
                checkpoint.target_public_fixture_sha256,
                checkpoint.step_index,
                checkpoint.observation_sha256,
            )
            exact_start = (
                start_identity.episode_id,
                start_identity.episode_generation,
                start_identity.fixture_id,
                start_identity.fixture_generation,
                start_identity.public_fixture_sha256,
                start_identity.step_index,
                start_identity.observation_sha256,
            )
            if checkpoint_start != exact_start:
                raise RecoveryE2Error("checkpoint does not bind exact shared post-change start identity")
            checkpoint_sha = checkpoint.sha256()
        elif checkpoint is not None:
            raise RecoveryE2Error("cold restart must not consume checkpoint")
        if resource_vector is not None and type(resource_vector) is not EvaluatorResourceVector:
            raise RecoveryE2Error("resource_vector must be exact EvaluatorResourceVector or None")
        actions = trace.actions_executed
        if actions > scenario.action_budget:
            raise RecoveryE2Error("run exceeds scenario action budget")
        return cls(
            RUN_SCHEMA,
            run_id,
            mode,
            scenario.sha256(),
            start_identity.sha256(),
            reference_plan.sha256(),
            checkpoint_sha,
            trace.sha256(),
            actions,
            trace.replayed_steps,
            trace.valid_reuse_steps,
            trace.invalid_reuse_steps,
            trace.repeated_work_steps,
            final_evaluator_score,
            terminal,
            actions - reference_plan.action_count,
            reference_plan.terminal_evaluator_score - final_evaluator_score,
            resource_vector,
            _origin=_RUN_ORIGIN,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MatchedRecoveryComparisonV2:
    schema: str
    comparison_id: str
    cold_restart: RecoveryRunMeasurementV2
    checkpoint_resume: RecoveryRunMeasurementV2
    classification: str = MEASUREMENT_ONLY
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != COMPARISON_SCHEMA or self.classification != MEASUREMENT_ONLY:
            raise RecoveryE2Error("comparison schema/classification mismatch")
        _id("comparison_id", self.comparison_id)
        if type(self.cold_restart) is not RecoveryRunMeasurementV2 or type(self.checkpoint_resume) is not RecoveryRunMeasurementV2:
            raise RecoveryE2Error("comparison requires exact v2 run measurements")
        if self.cold_restart.mode != COLD_RESTART or self.checkpoint_resume.mode != CHECKPOINT_RESUME:
            raise RecoveryE2Error("comparison requires cold-restart then checkpoint-resume")
        for field in ("scenario_sha256", "start_identity_sha256", "reference_plan_sha256"):
            if getattr(self.cold_restart, field) != getattr(self.checkpoint_resume, field):
                raise RecoveryE2Error(f"matched recovery comparison differs on {field}")
        if self.cold_restart.run_id == self.checkpoint_resume.run_id:
            raise RecoveryE2Error("matched runs require distinct run_id values")
        expected = "recovery-v2:" + _digest(
            {
                "cold": self.cold_restart.sha256(),
                "resume": self.checkpoint_resume.sha256(),
            }
        )
        if self.comparison_id != expected:
            raise RecoveryE2Error("comparison_id does not bind exact runs")
        if _origin is not _COMPARISON_ORIGIN:
            raise RecoveryE2Error("MatchedRecoveryComparisonV2 must be created by evaluator API")

    @classmethod
    def create(
        cls,
        *,
        cold_restart: RecoveryRunMeasurementV2,
        checkpoint_resume: RecoveryRunMeasurementV2,
    ) -> "MatchedRecoveryComparisonV2":
        if type(cold_restart) is not RecoveryRunMeasurementV2 or type(checkpoint_resume) is not RecoveryRunMeasurementV2:
            raise RecoveryE2Error("comparison requires exact v2 run measurements")
        comparison_id = "recovery-v2:" + _digest({"cold": cold_restart.sha256(), "resume": checkpoint_resume.sha256()})
        return cls(COMPARISON_SCHEMA, comparison_id, cold_restart, checkpoint_resume, _origin=_COMPARISON_ORIGIN)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "comparison_id": self.comparison_id,
            "cold_restart": self.cold_restart.as_dict(),
            "checkpoint_resume": self.checkpoint_resume.as_dict(),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecoveryEfficiencySummaryV2:
    schema: str
    comparison_sha256: str
    evaluator_score_delta: int
    action_delta: int
    action_regret_delta: int
    score_regret_delta: int
    replayed_step_delta: int
    valid_reuse_delta: int
    invalid_reuse_delta: int
    repeated_work_delta: int
    resource_delta: dict[str, int] | None
    runtime_credit: int = 0
    physical_grid10_credit: int = 0
    gwt_jspace_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = MEASUREMENT_ONLY

    def __post_init__(self) -> None:
        if self.schema != SUMMARY_SCHEMA or self.classification != MEASUREMENT_ONLY:
            raise RecoveryE2Error("summary schema/classification mismatch")
        _sha("comparison_sha256", self.comparison_sha256)
        for name in (
            "evaluator_score_delta",
            "action_delta",
            "action_regret_delta",
            "score_regret_delta",
            "replayed_step_delta",
            "valid_reuse_delta",
            "invalid_reuse_delta",
            "repeated_work_delta",
        ):
            if type(getattr(self, name)) is not int:
                raise RecoveryE2Error(f"{name} must be an integer delta")
        if self.resource_delta is not None:
            if type(self.resource_delta) is not dict or any(type(k) is not str or type(v) is not int for k, v in self.resource_delta.items()):
                raise RecoveryE2Error("resource_delta must be a string->integer dictionary or None")
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_grid10_credit,
                self.gwt_jspace_credit,
                self.effect_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance is not False:
            raise RecoveryE2Error("summary cannot mint higher-scope credit")

    @classmethod
    def from_comparison(cls, comparison: MatchedRecoveryComparisonV2) -> "RecoveryEfficiencySummaryV2":
        if type(comparison) is not MatchedRecoveryComparisonV2:
            raise RecoveryE2Error("comparison must be exact MatchedRecoveryComparisonV2")
        cold, resume = comparison.cold_restart, comparison.checkpoint_resume
        resource_delta: dict[str, int] | None = None
        if cold.resource_vector is not None and resume.resource_vector is not None:
            cold_resource = cold.resource_vector.as_dict()
            resume_resource = resume.resource_vector.as_dict()
            metric_names = (
                "model_calls",
                "input_tokens",
                "output_tokens",
                "latency_us",
                "cpu_time_us",
                "peak_rss_bytes",
                "gpu_time_us",
                "io_bytes",
            )
            resource_delta = {name: resume_resource[name] - cold_resource[name] for name in metric_names}
        return cls(
            SUMMARY_SCHEMA,
            comparison.sha256(),
            resume.final_evaluator_score - cold.final_evaluator_score,
            resume.actions_executed - cold.actions_executed,
            resume.action_regret - cold.action_regret,
            resume.score_regret - cold.score_regret,
            resume.replayed_steps - cold.replayed_steps,
            resume.valid_reuse_steps - cold.valid_reuse_steps,
            resume.invalid_reuse_steps - cold.invalid_reuse_steps,
            resume.repeated_work_steps - cold.repeated_work_steps,
            resource_delta,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())
