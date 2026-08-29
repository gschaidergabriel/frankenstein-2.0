"""F2-WP-805 generation-2 E2 falsifier repair.

Evaluator-only recovery provenance sits outside tested-policy input. This module strengthens
WP805's repository benchmark contract; it does not establish runtime, physical GRID10,
GWT/J-Space, model-learning, training, effect, completion, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from frankenstein2.cognitive_microworld import MicroWorldFixture, ObservationView
from frankenstein2.cognitive_transfer_recovery_benchmark import (
    COLD_RESTART,
    CHECKPOINT_RESUME,
    EvaluatorRunMeasurement,
    TransferCase,
    TransferRecoveryBenchmarkError,
)

STRUCTURAL_SPLIT_SCHEMA = "FRANKENSTEIN2_TRANSFER_STRUCTURAL_SPLIT/v1"
PERTURBATION_SCHEMA = "FRANKENSTEIN2_RECOVERY_PERTURBATION/v1"
REFERENCE_PLAN_SCHEMA = "FRANKENSTEIN2_RECOVERY_REFERENCE_PLAN/v1"
REUSE_TRACE_SCHEMA = "FRANKENSTEIN2_RECOVERY_REUSE_TRACE/v1"
RESOURCE_VECTOR_SCHEMA = "FRANKENSTEIN2_RECOVERY_RESOURCE_VECTOR/v1"
SCENARIO_SCHEMA = "FRANKENSTEIN2_RECOVERY_SCENARIO/v1"
BOUND_RUN_SCHEMA = "FRANKENSTEIN2_RECOVERY_BOUND_RUN/v1"
BOUND_PAIR_SCHEMA = "FRANKENSTEIN2_RECOVERY_BOUND_PAIR/v1"
EVALUATOR_ONLY = "EVALUATOR_ONLY_NOT_SUT_INPUT_OR_WORLD_AUTHORITY"
BENCHMARK_ONLY = "REPOSITORY_BENCHMARK_EVIDENCE_NOT_RUNTIME_OR_COGNITION_AUTHORITY"
_MAX_REFS = 4096
_MAX_RESOURCE = 10**15


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 512:
        raise TransferRecoveryBenchmarkError(f"{name} must be a non-empty trimmed bounded string")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise TransferRecoveryBenchmarkError(f"{name} contains control characters")
    return value


def _nint(name: str, value: Any, maximum: int = _MAX_RESOURCE) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise TransferRecoveryBenchmarkError(f"{name} must be a bounded non-negative integer")
    return value


def _refs(name: str, value: Any, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) > _MAX_REFS:
        raise TransferRecoveryBenchmarkError(f"{name} must be a bounded immutable tuple")
    out = tuple(_id(f"{name} item", x) for x in value)
    if nonempty and not out:
        raise TransferRecoveryBenchmarkError(f"{name} must not be empty")
    if len(set(out)) != len(out) or out != tuple(sorted(out)):
        raise TransferRecoveryBenchmarkError(f"{name} must be unique and lexically sorted")
    return out


@dataclass(frozen=True, slots=True)
class StructuralSplitBinding:
    schema: str
    source_fixture_sha256: str
    target_fixture_sha256: str
    source_holdout_set_id: str
    target_holdout_set_id: str
    source_evidence_source_family: str
    target_evidence_source_family: str
    source_donor_path_family: str
    target_donor_path_family: str
    source_method_family: str
    target_method_family: str
    source_primary_source_ids: tuple[str, ...]
    target_primary_source_ids: tuple[str, ...]
    classification: str = EVALUATOR_ONLY

    @classmethod
    def from_fixtures(cls, source: MicroWorldFixture, target: MicroWorldFixture) -> "StructuralSplitBinding":
        if type(source) is not MicroWorldFixture or type(target) is not MicroWorldFixture:
            raise TransferRecoveryBenchmarkError("structural split requires exact MicroWorldFixture values")
        for label, left, right in (
            ("holdout_set_id", source.holdout_set_id, target.holdout_set_id),
            ("evidence_source_family", source.evidence_source_family, target.evidence_source_family),
            ("donor_path_family", source.donor_path_family, target.donor_path_family),
            ("method_family", source.method_family, target.method_family),
        ):
            if left == right:
                raise TransferRecoveryBenchmarkError(f"structural transfer overlap on {label}")
        if set(source.primary_source_ids) & set(target.primary_source_ids):
            raise TransferRecoveryBenchmarkError("structural transfer overlaps primary_source_ids")
        return cls(
            STRUCTURAL_SPLIT_SCHEMA,
            source.sha256(), target.sha256(), source.holdout_set_id, target.holdout_set_id,
            source.evidence_source_family, target.evidence_source_family,
            source.donor_path_family, target.donor_path_family,
            source.method_family, target.method_family,
            source.primary_source_ids, target.primary_source_ids,
        )

    def __post_init__(self) -> None:
        if self.schema != STRUCTURAL_SPLIT_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise TransferRecoveryBenchmarkError("structural split schema/classification mismatch")
        _refs("source_primary_source_ids", self.source_primary_source_ids, nonempty=True)
        _refs("target_primary_source_ids", self.target_primary_source_ids, nonempty=True)

    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecoveryPerturbation:
    schema: str
    perturbation_id: str
    perturbation_generation: int
    pre_change_fixture_sha256: str
    post_change_fixture_sha256: str
    causal_footprint_refs: tuple[str, ...]
    causal_footprint_sha256: str
    classification: str = EVALUATOR_ONLY

    @classmethod
    def create(cls, *, perturbation_id: str, perturbation_generation: int,
               pre_change: MicroWorldFixture, post_change: MicroWorldFixture,
               causal_footprint_refs: tuple[str, ...]) -> "RecoveryPerturbation":
        if type(pre_change) is not MicroWorldFixture or type(post_change) is not MicroWorldFixture:
            raise TransferRecoveryBenchmarkError("perturbation fixtures must be exact MicroWorldFixture values")
        refs = _refs("causal_footprint_refs", causal_footprint_refs, nonempty=True)
        if pre_change.sha256() == post_change.sha256():
            raise TransferRecoveryBenchmarkError("perturbation requires changed full fixture identity")
        return cls(PERTURBATION_SCHEMA, _id("perturbation_id", perturbation_id),
                   _nint("perturbation_generation", perturbation_generation),
                   pre_change.sha256(), post_change.sha256(), refs, _digest(list(refs)))

    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ReferencePlan:
    schema: str
    fixture_sha256: str
    start_node_id: str
    objective: str
    action_ids: tuple[str, ...]
    terminal_node_id: str
    final_cumulative_score: int
    classification: str = EVALUATOR_ONLY

    @property
    def action_count(self) -> int: return len(self.action_ids)
    def as_dict(self) -> dict[str, Any]:
        value = asdict(self); value["action_count"] = self.action_count; return value
    def sha256(self) -> str: return _digest(self.as_dict())


def deterministic_reference_plan(fixture: MicroWorldFixture, *, start_node_id: str,
                                 max_actions: int) -> ReferencePlan:
    """Shortest terminal plan; ties choose highest cumulative score, then lexical actions."""
    if type(fixture) is not MicroWorldFixture:
        raise TransferRecoveryBenchmarkError("oracle fixture must be exact MicroWorldFixture")
    _id("start_node_id", start_node_id); _nint("max_actions", max_actions, 4096)
    start = fixture.node(start_node_id)
    if start.terminal:
        return ReferencePlan(REFERENCE_PLAN_SCHEMA, fixture.sha256(), start_node_id,
                             "MIN_ACTIONS_THEN_MAX_CUMULATIVE_SCORE_THEN_LEXICAL", (),
                             start_node_id, start.evaluator_score)
    frontier: list[tuple[str, tuple[str, ...], int]] = [(start_node_id, (), start.evaluator_score)]
    for depth in range(1, max_actions + 1):
        next_frontier: list[tuple[str, tuple[str, ...], int]] = []
        terminal: list[tuple[str, tuple[str, ...], int]] = []
        for node_id, path, score in frontier:
            for action in sorted(x.action_id for x in fixture.actions):
                try:
                    rule = fixture.transition(node_id, action)
                except Exception:
                    continue
                node = fixture.node(rule.to_node_id)
                candidate = (node.node_id, path + (action,), score + node.evaluator_score)
                (terminal if node.terminal else next_frontier).append(candidate)
        if terminal:
            terminal.sort(key=lambda x: (-x[2], x[1], x[0]))
            node_id, actions, score = terminal[0]
            return ReferencePlan(REFERENCE_PLAN_SCHEMA, fixture.sha256(), start_node_id,
                                 "MIN_ACTIONS_THEN_MAX_CUMULATIVE_SCORE_THEN_LEXICAL",
                                 actions, node_id, score)
        # Deterministic dominance pruning: for each node retain best score, lexical tie-break.
        best: dict[str, tuple[str, tuple[str, ...], int]] = {}
        for candidate in next_frontier:
            prior = best.get(candidate[0])
            if prior is None or candidate[2] > prior[2] or (candidate[2] == prior[2] and candidate[1] < prior[1]):
                best[candidate[0]] = candidate
        frontier = [best[k] for k in sorted(best)]
        if not frontier:
            break
    raise TransferRecoveryBenchmarkError("no terminal reference plan within max_actions")


@dataclass(frozen=True, slots=True)
class ReuseTraceReceipt:
    schema: str
    executed_step_refs: tuple[str, ...]
    replayed_step_refs: tuple[str, ...]
    repeated_work_step_refs: tuple[str, ...]
    retained_dependency_refs: tuple[str, ...]
    valid_retained_dependency_refs: tuple[str, ...]
    invalidated_dependency_refs: tuple[str, ...]
    classification: str = EVALUATOR_ONLY

    def __post_init__(self) -> None:
        if self.schema != REUSE_TRACE_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise TransferRecoveryBenchmarkError("reuse trace schema/classification mismatch")
        executed = set(_refs("executed_step_refs", self.executed_step_refs))
        replayed = set(_refs("replayed_step_refs", self.replayed_step_refs))
        repeated = set(_refs("repeated_work_step_refs", self.repeated_work_step_refs))
        retained = set(_refs("retained_dependency_refs", self.retained_dependency_refs))
        valid = set(_refs("valid_retained_dependency_refs", self.valid_retained_dependency_refs))
        invalid = set(_refs("invalidated_dependency_refs", self.invalidated_dependency_refs))
        if not replayed <= executed or not repeated <= executed:
            raise TransferRecoveryBenchmarkError("replay/repeated-work refs must be derived from executed trace")
        if not valid <= retained:
            raise TransferRecoveryBenchmarkError("valid retained dependencies must be a subset of retained dependencies")
        if valid & invalid:
            raise TransferRecoveryBenchmarkError("dependency cannot be both valid-retained and invalidated")

    @property
    def replayed_steps(self) -> int: return len(self.replayed_step_refs)
    @property
    def repeated_work_steps(self) -> int: return len(self.repeated_work_step_refs)
    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ResourceVector:
    schema: str
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cpu_ms: int = 0
    peak_rss_bytes: int = 0
    gpu_ms: int = 0
    io_bytes: int = 0
    classification: str = EVALUATOR_ONLY

    def __post_init__(self) -> None:
        if self.schema != RESOURCE_VECTOR_SCHEMA or self.classification != EVALUATOR_ONLY:
            raise TransferRecoveryBenchmarkError("resource vector schema/classification mismatch")
        for name in ("model_calls","input_tokens","output_tokens","latency_ms","cpu_ms","peak_rss_bytes","gpu_ms","io_bytes"):
            _nint(name, getattr(self, name))
    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecoveryScenario:
    schema: str
    scenario_id: str
    transfer_case_sha256: str
    structural_split_sha256: str
    perturbation_sha256: str
    target_fixture_sha256: str
    post_change_start_observation_sha256: str
    post_change_episode_id: str
    post_change_episode_generation: int
    post_change_step_index: int
    reference_plan_sha256: str
    classification: str = BENCHMARK_ONLY

    @classmethod
    def create(cls, *, case: TransferCase, split: StructuralSplitBinding,
               perturbation: RecoveryPerturbation, target_fixture: MicroWorldFixture,
               start_observation: ObservationView, reference_plan: ReferencePlan) -> "RecoveryScenario":
        if type(case) is not TransferCase or type(split) is not StructuralSplitBinding or type(perturbation) is not RecoveryPerturbation:
            raise TransferRecoveryBenchmarkError("scenario benchmark values must be exact concrete types")
        if type(target_fixture) is not MicroWorldFixture or type(start_observation) is not ObservationView or type(reference_plan) is not ReferencePlan:
            raise TransferRecoveryBenchmarkError("scenario target/start/oracle must be exact concrete types")
        case.assert_target_observation(start_observation)
        if split.target_fixture_sha256 != target_fixture.sha256() or perturbation.post_change_fixture_sha256 != target_fixture.sha256():
            raise TransferRecoveryBenchmarkError("scenario target fixture is not bound by split/perturbation")
        if reference_plan.fixture_sha256 != target_fixture.sha256():
            raise TransferRecoveryBenchmarkError("reference plan is bound to another target fixture")
        body = {
            "transfer_case_sha256": case.sha256(), "structural_split_sha256": split.sha256(),
            "perturbation_sha256": perturbation.sha256(), "target_fixture_sha256": target_fixture.sha256(),
            "post_change_start_observation_sha256": start_observation.sha256(),
            "post_change_episode_id": start_observation.episode_id,
            "post_change_episode_generation": start_observation.episode_generation,
            "post_change_step_index": start_observation.step_index,
            "reference_plan_sha256": reference_plan.sha256(),
        }
        return cls(SCENARIO_SCHEMA, "recovery-scenario:" + _digest(body), **body)

    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class BoundRecoveryRun:
    schema: str
    run_id: str
    mode: str
    scenario_sha256: str
    base_measurement_sha256: str
    post_change_start_observation_sha256: str
    post_change_episode_id: str
    post_change_episode_generation: int
    post_change_step_index: int
    reference_plan_sha256: str
    reuse_trace_sha256: str
    resource_vector_sha256: str
    action_regret: int
    score_regret: int
    runtime_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = BENCHMARK_ONLY

    @classmethod
    def bind(cls, *, scenario: RecoveryScenario, measurement: EvaluatorRunMeasurement,
             trace: ReuseTraceReceipt, resources: ResourceVector,
             reference_plan: ReferencePlan) -> "BoundRecoveryRun":
        if type(scenario) is not RecoveryScenario or type(measurement) is not EvaluatorRunMeasurement:
            raise TransferRecoveryBenchmarkError("bound run requires exact scenario/base measurement")
        if type(trace) is not ReuseTraceReceipt or type(resources) is not ResourceVector or type(reference_plan) is not ReferencePlan:
            raise TransferRecoveryBenchmarkError("bound run requires exact trace/resource/oracle values")
        if measurement.transfer_case_sha256 != scenario.transfer_case_sha256 or measurement.target_fixture_sha256 != scenario.target_fixture_sha256:
            raise TransferRecoveryBenchmarkError("base measurement is not bound to scenario case/target")
        if reference_plan.sha256() != scenario.reference_plan_sha256:
            raise TransferRecoveryBenchmarkError("bound run oracle mismatch")
        if measurement.replayed_steps != trace.replayed_steps or measurement.repeated_work_steps != trace.repeated_work_steps:
            raise TransferRecoveryBenchmarkError("base replay/repeated-work counters do not match trace-derived counts")
        return cls(
            BOUND_RUN_SCHEMA, measurement.run_id, measurement.mode, scenario.sha256(), measurement.sha256(),
            scenario.post_change_start_observation_sha256, scenario.post_change_episode_id,
            scenario.post_change_episode_generation, scenario.post_change_step_index,
            scenario.reference_plan_sha256, trace.sha256(), resources.sha256(),
            measurement.actions_executed - reference_plan.action_count,
            reference_plan.final_cumulative_score - measurement.final_evaluator_score,
        )

    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class BoundRecoveryPair:
    schema: str
    pair_id: str
    scenario_sha256: str
    cold_run_sha256: str
    resume_run_sha256: str
    shared_post_change_start_sha256: str
    classification: str = BENCHMARK_ONLY

    @classmethod
    def create(cls, *, cold: BoundRecoveryRun, resume: BoundRecoveryRun) -> "BoundRecoveryPair":
        if type(cold) is not BoundRecoveryRun or type(resume) is not BoundRecoveryRun:
            raise TransferRecoveryBenchmarkError("bound pair requires exact bound runs")
        if cold.mode != COLD_RESTART or resume.mode != CHECKPOINT_RESUME:
            raise TransferRecoveryBenchmarkError("bound pair requires cold then checkpoint-resume modes")
        attrs = ("scenario_sha256","post_change_start_observation_sha256","post_change_episode_id",
                 "post_change_episode_generation","post_change_step_index","reference_plan_sha256")
        for attr in attrs:
            if getattr(cold, attr) != getattr(resume, attr):
                raise TransferRecoveryBenchmarkError(f"bound recovery runs differ on {attr}")
        if cold.run_id == resume.run_id:
            raise TransferRecoveryBenchmarkError("bound recovery runs require distinct run ids")
        body = {"scenario_sha256": cold.scenario_sha256, "cold_run_sha256": cold.sha256(),
                "resume_run_sha256": resume.sha256(),
                "shared_post_change_start_sha256": cold.post_change_start_observation_sha256}
        return cls(BOUND_PAIR_SCHEMA, "recovery-e2-pair:" + _digest(body), **body)

    def as_dict(self) -> dict[str, Any]: return asdict(self)
    def sha256(self) -> str: return _digest(self.as_dict())
