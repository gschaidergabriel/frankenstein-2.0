"""F2-WP-805 deterministic transfer/recovery/efficient-planning benchmark contracts.

This module keeps tested-policy inputs on the public WP800 ObservationView side and keeps
full-fixture/evaluator measurements on a separate evaluator-only surface. It is repository
evaluation infrastructure only; it grants no runtime, GRID10/GWT/J-Space, effect,
completion, training, world-truth, goal-authority, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from frankenstein2.cognitive_microworld import ObservationView

POLICY_STATE_SCHEMA = "FRANKENSTEIN2_TRANSFER_POLICY_STATE/v1"
TRANSFER_CASE_SCHEMA = "FRANKENSTEIN2_TRANSFER_CASE/v1"
RECOVERY_CHECKPOINT_SCHEMA = "FRANKENSTEIN2_PUBLIC_RECOVERY_CHECKPOINT/v1"
RUN_MEASUREMENT_SCHEMA = "FRANKENSTEIN2_TRANSFER_RECOVERY_RUN_MEASUREMENT/v1"
MATCHED_COMPARISON_SCHEMA = "FRANKENSTEIN2_TRANSFER_RECOVERY_MATCHED_COMPARISON/v1"
EFFICIENCY_SUMMARY_SCHEMA = "FRANKENSTEIN2_TRANSFER_RECOVERY_EFFICIENCY_SUMMARY/v1"
PUBLIC_POLICY_CLASSIFICATION = "PUBLIC_SUT_STATE_NO_EVALUATOR_GROUND_TRUTH"
EVALUATOR_CLASSIFICATION = "EVALUATOR_ONLY_MEASUREMENT_NOT_POLICY_INPUT_OR_WORLD_AUTHORITY"
BENCHMARK_CLASSIFICATION = "REPOSITORY_BENCHMARK_EVIDENCE_NOT_RUNTIME_OR_COGNITION_AUTHORITY"
COLD_RESTART = "COLD_RESTART"
CHECKPOINT_RESUME = "CHECKPOINT_RESUME"
_ALLOWED_MODES = frozenset((COLD_RESTART, CHECKPOINT_RESUME))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_ACTIONS = 4096
_MAX_BUDGET = 1_000_000
_MAX_SCORE_ABS = 1_000_000_000
_RUN_ORIGIN = object()
_COMPARE_ORIGIN = object()

_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "current_node_id",
        "fixture_sha256",
        "hidden_ground_truth_ref",
        "hidden_ground_truth_sha256",
        "evaluator_score",
        "cumulative_score",
        "transition_ref",
        "transition_sha256",
        "to_node_id",
        "from_node_id",
        "nodes",
        "transitions",
    }
)


class TransferRecoveryBenchmarkError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise TransferRecoveryBenchmarkError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise TransferRecoveryBenchmarkError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise TransferRecoveryBenchmarkError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nint(name: str, value: Any, *, maximum: int = _MAX_BUDGET) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise TransferRecoveryBenchmarkError(f"{name} must be a non-negative integer in [0, {maximum}]")
    return value


def _pint(name: str, value: Any, *, maximum: int = _MAX_BUDGET) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise TransferRecoveryBenchmarkError(f"{name} must be a positive integer in [1, {maximum}]")
    return value


def _score(name: str, value: Any) -> int:
    if type(value) is not int or not -_MAX_SCORE_ABS <= value <= _MAX_SCORE_ABS:
        raise TransferRecoveryBenchmarkError(f"{name} exceeds bounded evaluator score domain")
    return value


def _bool(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise TransferRecoveryBenchmarkError(f"{name} must be a boolean")
    return value


def _actions(name: str, values: Any) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise TransferRecoveryBenchmarkError(f"{name} must be a non-empty immutable tuple")
    if len(values) > _MAX_ACTIONS:
        raise TransferRecoveryBenchmarkError(f"{name} exceeds action ceiling")
    out = tuple(_id(f"{name} item", value) for value in values)
    if len(out) != len(set(out)):
        raise TransferRecoveryBenchmarkError(f"{name} contains duplicates")
    if out != tuple(sorted(out)):
        raise TransferRecoveryBenchmarkError(f"{name} must be in canonical lexical order")
    return out


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def assert_public_only_payload(value: Any, *, path: str = "payload") -> None:
    """Fail closed if a tested-policy payload carries known evaluator-only fields/types."""
    if type(value) is ObservationView:
        assert_public_only_payload(value.as_dict(), path=path)
        return
    if isinstance(value, ObservationView):
        raise TransferRecoveryBenchmarkError(f"{path} must use exact concrete ObservationView")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise TransferRecoveryBenchmarkError(f"{path} mapping keys must be strings")
            if key in _FORBIDDEN_PUBLIC_KEYS:
                raise TransferRecoveryBenchmarkError(f"{path} contains evaluator-only key {key}")
            assert_public_only_payload(item, path=f"{path}.{key}")
        return
    if type(value) in (tuple, list):
        for index, item in enumerate(value):
            assert_public_only_payload(item, path=f"{path}[{index}]")
        return
    if value is None or type(value) in (str, int, bool):
        return
    raise TransferRecoveryBenchmarkError(f"{path} contains unsupported public payload type")


@dataclass(frozen=True, slots=True)
class PublicPolicyState:
    schema: str
    policy_ref: str
    policy_generation: int
    source_fixture_id: str
    source_holdout_set_id: str
    source_public_fixture_sha256: str
    artifact_sha256: str
    allowed_action_ids: tuple[str, ...]
    max_action_budget: int
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != POLICY_STATE_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise TransferRecoveryBenchmarkError("policy-state schema/classification mismatch")
        _id("policy_ref", self.policy_ref)
        _nint("policy_generation", self.policy_generation)
        _id("source_fixture_id", self.source_fixture_id)
        _id("source_holdout_set_id", self.source_holdout_set_id)
        _sha("source_public_fixture_sha256", self.source_public_fixture_sha256)
        _sha("artifact_sha256", self.artifact_sha256)
        _actions("allowed_action_ids", self.allowed_action_ids)
        _pint("max_action_budget", self.max_action_budget)
        assert_public_only_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class TransferCase:
    schema: str
    case_id: str
    source_fixture_id: str
    source_fixture_generation: int
    source_holdout_set_id: str
    source_public_fixture_sha256: str
    target_fixture_id: str
    target_fixture_generation: int
    target_holdout_set_id: str
    target_public_fixture_sha256: str
    episode_family_id: str
    action_budget: int
    classification: str = BENCHMARK_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != TRANSFER_CASE_SCHEMA or self.classification != BENCHMARK_CLASSIFICATION:
            raise TransferRecoveryBenchmarkError("transfer-case schema/classification mismatch")
        _id("case_id", self.case_id)
        _id("source_fixture_id", self.source_fixture_id)
        _nint("source_fixture_generation", self.source_fixture_generation)
        _id("source_holdout_set_id", self.source_holdout_set_id)
        _sha("source_public_fixture_sha256", self.source_public_fixture_sha256)
        _id("target_fixture_id", self.target_fixture_id)
        _nint("target_fixture_generation", self.target_fixture_generation)
        _id("target_holdout_set_id", self.target_holdout_set_id)
        _sha("target_public_fixture_sha256", self.target_public_fixture_sha256)
        _id("episode_family_id", self.episode_family_id)
        _pint("action_budget", self.action_budget)
        if self.source_fixture_id == self.target_fixture_id:
            raise TransferRecoveryBenchmarkError("transfer requires distinct source and target fixture_id")
        if self.source_public_fixture_sha256 == self.target_public_fixture_sha256:
            raise TransferRecoveryBenchmarkError("transfer requires distinct source and target public fixture digests")
        if self.source_holdout_set_id == self.target_holdout_set_id:
            raise TransferRecoveryBenchmarkError("transfer requires distinct source and target holdout sets")

    @classmethod
    def create(
        cls,
        *,
        source_fixture_id: str,
        source_fixture_generation: int,
        source_holdout_set_id: str,
        source_public_fixture_sha256: str,
        target_fixture_id: str,
        target_fixture_generation: int,
        target_holdout_set_id: str,
        target_public_fixture_sha256: str,
        episode_family_id: str,
        action_budget: int,
    ) -> "TransferCase":
        body = {
            "source_fixture_id": source_fixture_id,
            "source_fixture_generation": source_fixture_generation,
            "source_holdout_set_id": source_holdout_set_id,
            "source_public_fixture_sha256": source_public_fixture_sha256,
            "target_fixture_id": target_fixture_id,
            "target_fixture_generation": target_fixture_generation,
            "target_holdout_set_id": target_holdout_set_id,
            "target_public_fixture_sha256": target_public_fixture_sha256,
            "episode_family_id": episode_family_id,
            "action_budget": action_budget,
        }
        return cls(TRANSFER_CASE_SCHEMA, "transfer:" + _digest(body), **body)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def assert_policy_source(self, policy: PublicPolicyState) -> None:
        if type(policy) is not PublicPolicyState:
            raise TransferRecoveryBenchmarkError("policy must be exact concrete PublicPolicyState")
        expected = (
            self.source_fixture_id,
            self.source_holdout_set_id,
            self.source_public_fixture_sha256,
        )
        observed = (
            policy.source_fixture_id,
            policy.source_holdout_set_id,
            policy.source_public_fixture_sha256,
        )
        if observed != expected:
            raise TransferRecoveryBenchmarkError("policy artifact is not bound to exact source public fixture")
        if policy.max_action_budget < self.action_budget:
            raise TransferRecoveryBenchmarkError("policy artifact budget is below transfer-case action budget")

    def assert_target_observation(self, observation: ObservationView) -> None:
        if type(observation) is not ObservationView:
            raise TransferRecoveryBenchmarkError("target observation must be exact concrete ObservationView")
        if (observation.fixture_id, observation.fixture_generation, observation.public_fixture_sha256) != (
            self.target_fixture_id,
            self.target_fixture_generation,
            self.target_public_fixture_sha256,
        ):
            raise TransferRecoveryBenchmarkError("observation is not bound to exact target public fixture")


@dataclass(frozen=True, slots=True)
class RecoveryCheckpoint:
    schema: str
    checkpoint_id: str
    transfer_case_sha256: str
    policy_state_sha256: str
    episode_id: str
    episode_generation: int
    target_fixture_id: str
    target_fixture_generation: int
    target_public_fixture_sha256: str
    step_index: int
    observation_sha256: str
    action_history_sha256: str
    actions_consumed: int
    remaining_action_budget: int
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RECOVERY_CHECKPOINT_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise TransferRecoveryBenchmarkError("checkpoint schema/classification mismatch")
        for name, value in (
            ("transfer_case_sha256", self.transfer_case_sha256),
            ("policy_state_sha256", self.policy_state_sha256),
            ("target_public_fixture_sha256", self.target_public_fixture_sha256),
            ("observation_sha256", self.observation_sha256),
            ("action_history_sha256", self.action_history_sha256),
        ):
            _sha(name, value)
        _id("checkpoint_id", self.checkpoint_id)
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("target_fixture_id", self.target_fixture_id)
        _nint("target_fixture_generation", self.target_fixture_generation)
        _nint("step_index", self.step_index)
        _nint("actions_consumed", self.actions_consumed)
        _nint("remaining_action_budget", self.remaining_action_budget)
        if self.actions_consumed != self.step_index:
            raise TransferRecoveryBenchmarkError("actions_consumed must equal public episode step_index")
        expected = "checkpoint:" + _digest(self.identity_body())
        if self.checkpoint_id != expected:
            raise TransferRecoveryBenchmarkError("checkpoint_id does not bind exact public checkpoint identity")

    @classmethod
    def seal(
        cls,
        *,
        case: TransferCase,
        policy: PublicPolicyState,
        observation: ObservationView,
        action_history_sha256: str,
    ) -> "RecoveryCheckpoint":
        if type(case) is not TransferCase or type(policy) is not PublicPolicyState:
            raise TransferRecoveryBenchmarkError("case/policy must be exact concrete benchmark values")
        case.assert_policy_source(policy)
        case.assert_target_observation(observation)
        _sha("action_history_sha256", action_history_sha256)
        if observation.step_index > case.action_budget:
            raise TransferRecoveryBenchmarkError("observation step exceeds transfer-case action budget")
        body = {
            "transfer_case_sha256": case.sha256(),
            "policy_state_sha256": policy.sha256(),
            "episode_id": observation.episode_id,
            "episode_generation": observation.episode_generation,
            "target_fixture_id": observation.fixture_id,
            "target_fixture_generation": observation.fixture_generation,
            "target_public_fixture_sha256": observation.public_fixture_sha256,
            "step_index": observation.step_index,
            "observation_sha256": observation.sha256(),
            "action_history_sha256": action_history_sha256,
            "actions_consumed": observation.step_index,
            "remaining_action_budget": case.action_budget - observation.step_index,
        }
        return cls(RECOVERY_CHECKPOINT_SCHEMA, "checkpoint:" + _digest(body), **body)

    def identity_body(self) -> dict[str, Any]:
        return {
            "transfer_case_sha256": self.transfer_case_sha256,
            "policy_state_sha256": self.policy_state_sha256,
            "episode_id": self.episode_id,
            "episode_generation": self.episode_generation,
            "target_fixture_id": self.target_fixture_id,
            "target_fixture_generation": self.target_fixture_generation,
            "target_public_fixture_sha256": self.target_public_fixture_sha256,
            "step_index": self.step_index,
            "observation_sha256": self.observation_sha256,
            "action_history_sha256": self.action_history_sha256,
            "actions_consumed": self.actions_consumed,
            "remaining_action_budget": self.remaining_action_budget,
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def assert_resume(self, *, case: TransferCase, policy: PublicPolicyState, observation: ObservationView) -> None:
        if type(case) is not TransferCase or type(policy) is not PublicPolicyState or type(observation) is not ObservationView:
            raise TransferRecoveryBenchmarkError("resume inputs must be exact concrete benchmark/public values")
        case.assert_policy_source(policy)
        case.assert_target_observation(observation)
        if self.transfer_case_sha256 != case.sha256() or self.policy_state_sha256 != policy.sha256():
            raise TransferRecoveryBenchmarkError("checkpoint case/policy digest mismatch")
        observed = (
            observation.episode_id,
            observation.episode_generation,
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            observation.step_index,
            observation.sha256(),
        )
        expected = (
            self.episode_id,
            self.episode_generation,
            self.target_fixture_id,
            self.target_fixture_generation,
            self.target_public_fixture_sha256,
            self.step_index,
            self.observation_sha256,
        )
        if observed != expected:
            raise TransferRecoveryBenchmarkError("resume observation does not match sealed checkpoint")


@dataclass(frozen=True, slots=True)
class EvaluatorRunMeasurement:
    schema: str
    run_id: str
    mode: str
    transfer_case_sha256: str
    target_fixture_sha256: str
    checkpoint_sha256: str | None
    action_budget: int
    actions_executed: int
    replayed_steps: int
    repeated_work_steps: int
    final_evaluator_score: int
    terminal: bool
    runtime_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = EVALUATOR_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != RUN_MEASUREMENT_SCHEMA or self.classification != EVALUATOR_CLASSIFICATION:
            raise TransferRecoveryBenchmarkError("run-measurement schema/classification mismatch")
        _id("run_id", self.run_id)
        if self.mode not in _ALLOWED_MODES:
            raise TransferRecoveryBenchmarkError("mode must be COLD_RESTART or CHECKPOINT_RESUME")
        _sha("transfer_case_sha256", self.transfer_case_sha256)
        _sha("target_fixture_sha256", self.target_fixture_sha256)
        if self.checkpoint_sha256 is not None:
            _sha("checkpoint_sha256", self.checkpoint_sha256)
        if self.mode == CHECKPOINT_RESUME and self.checkpoint_sha256 is None:
            raise TransferRecoveryBenchmarkError("checkpoint-resume measurement requires checkpoint_sha256")
        if self.mode == COLD_RESTART and self.checkpoint_sha256 is not None:
            raise TransferRecoveryBenchmarkError("cold-restart measurement must not claim checkpoint consumption")
        _pint("action_budget", self.action_budget)
        _nint("actions_executed", self.actions_executed)
        _nint("replayed_steps", self.replayed_steps)
        _nint("repeated_work_steps", self.repeated_work_steps)
        if self.actions_executed > self.action_budget:
            raise TransferRecoveryBenchmarkError("actions_executed exceeds matched action budget")
        if self.replayed_steps > self.actions_executed or self.repeated_work_steps > self.actions_executed:
            raise TransferRecoveryBenchmarkError("replay/repeated-work count exceeds executed actions")
        _score("final_evaluator_score", self.final_evaluator_score)
        _bool("terminal", self.terminal)
        if self.runtime_credit != 0 or self.whole_system_acceptance is not False:
            raise TransferRecoveryBenchmarkError("repository benchmark measurement cannot mint runtime/whole-system credit")
        if _origin is not _RUN_ORIGIN:
            raise TransferRecoveryBenchmarkError("EvaluatorRunMeasurement must be created by measure_run")

    @classmethod
    def measure_run(
        cls,
        *,
        run_id: str,
        mode: str,
        case: TransferCase,
        target_fixture_sha256: str,
        checkpoint: RecoveryCheckpoint | None,
        actions_executed: int,
        replayed_steps: int,
        repeated_work_steps: int,
        final_evaluator_score: int,
        terminal: bool,
    ) -> "EvaluatorRunMeasurement":
        if type(case) is not TransferCase:
            raise TransferRecoveryBenchmarkError("case must be exact concrete TransferCase")
        if checkpoint is not None:
            if type(checkpoint) is not RecoveryCheckpoint:
                raise TransferRecoveryBenchmarkError("checkpoint must be exact concrete RecoveryCheckpoint")
            if checkpoint.transfer_case_sha256 != case.sha256():
                raise TransferRecoveryBenchmarkError("checkpoint is bound to a different transfer case")
        return cls(
            RUN_MEASUREMENT_SCHEMA,
            run_id,
            mode,
            case.sha256(),
            target_fixture_sha256,
            None if checkpoint is None else checkpoint.sha256(),
            case.action_budget,
            actions_executed,
            replayed_steps,
            repeated_work_steps,
            final_evaluator_score,
            terminal,
            _origin=_RUN_ORIGIN,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "mode": self.mode,
            "transfer_case_sha256": self.transfer_case_sha256,
            "target_fixture_sha256": self.target_fixture_sha256,
            "checkpoint_sha256": self.checkpoint_sha256,
            "action_budget": self.action_budget,
            "actions_executed": self.actions_executed,
            "replayed_steps": self.replayed_steps,
            "repeated_work_steps": self.repeated_work_steps,
            "final_evaluator_score": self.final_evaluator_score,
            "terminal": self.terminal,
            "runtime_credit": self.runtime_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MatchedRecoveryComparison:
    schema: str
    comparison_id: str
    cold_restart: EvaluatorRunMeasurement
    checkpoint_resume: EvaluatorRunMeasurement
    classification: str = BENCHMARK_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != MATCHED_COMPARISON_SCHEMA or self.classification != BENCHMARK_CLASSIFICATION:
            raise TransferRecoveryBenchmarkError("comparison schema/classification mismatch")
        _id("comparison_id", self.comparison_id)
        if type(self.cold_restart) is not EvaluatorRunMeasurement or type(self.checkpoint_resume) is not EvaluatorRunMeasurement:
            raise TransferRecoveryBenchmarkError("comparison requires exact evaluator measurements")
        if self.cold_restart.mode != COLD_RESTART or self.checkpoint_resume.mode != CHECKPOINT_RESUME:
            raise TransferRecoveryBenchmarkError("comparison requires COLD_RESTART then CHECKPOINT_RESUME")
        for name in ("transfer_case_sha256", "target_fixture_sha256", "action_budget"):
            if getattr(self.cold_restart, name) != getattr(self.checkpoint_resume, name):
                raise TransferRecoveryBenchmarkError(f"matched recovery comparison differs on {name}")
        if self.cold_restart.run_id == self.checkpoint_resume.run_id:
            raise TransferRecoveryBenchmarkError("matched comparison requires distinct run_id values")
        expected = "recovery-pair:" + _digest(
            {
                "cold_restart_sha256": self.cold_restart.sha256(),
                "checkpoint_resume_sha256": self.checkpoint_resume.sha256(),
            }
        )
        if self.comparison_id != expected:
            raise TransferRecoveryBenchmarkError("comparison_id does not bind exact measurements")
        if _origin is not _COMPARE_ORIGIN:
            raise TransferRecoveryBenchmarkError("MatchedRecoveryComparison must be created by create")

    @classmethod
    def create(
        cls,
        *,
        cold_restart: EvaluatorRunMeasurement,
        checkpoint_resume: EvaluatorRunMeasurement,
    ) -> "MatchedRecoveryComparison":
        if type(cold_restart) is not EvaluatorRunMeasurement or type(checkpoint_resume) is not EvaluatorRunMeasurement:
            raise TransferRecoveryBenchmarkError("comparison requires exact evaluator measurements")
        comparison_id = "recovery-pair:" + _digest(
            {
                "cold_restart_sha256": cold_restart.sha256(),
                "checkpoint_resume_sha256": checkpoint_resume.sha256(),
            }
        )
        return cls(MATCHED_COMPARISON_SCHEMA, comparison_id, cold_restart, checkpoint_resume, _origin=_COMPARE_ORIGIN)

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
class EfficiencySummary:
    schema: str
    comparison_sha256: str
    evaluator_score_delta: int
    action_count_delta: int
    replayed_step_delta: int
    repeated_work_delta: int
    terminal_delta: int
    runtime_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = BENCHMARK_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != EFFICIENCY_SUMMARY_SCHEMA or self.classification != BENCHMARK_CLASSIFICATION:
            raise TransferRecoveryBenchmarkError("efficiency-summary schema/classification mismatch")
        _sha("comparison_sha256", self.comparison_sha256)
        for name, value in (
            ("evaluator_score_delta", self.evaluator_score_delta),
            ("action_count_delta", self.action_count_delta),
            ("replayed_step_delta", self.replayed_step_delta),
            ("repeated_work_delta", self.repeated_work_delta),
        ):
            if type(value) is not int:
                raise TransferRecoveryBenchmarkError(f"{name} must be an integer delta")
        if self.terminal_delta not in (-1, 0, 1):
            raise TransferRecoveryBenchmarkError("terminal_delta must be -1, 0 or 1")
        if self.runtime_credit != 0 or self.whole_system_acceptance is not False:
            raise TransferRecoveryBenchmarkError("efficiency summary cannot mint runtime/whole-system credit")

    @classmethod
    def from_comparison(cls, comparison: MatchedRecoveryComparison) -> "EfficiencySummary":
        if type(comparison) is not MatchedRecoveryComparison:
            raise TransferRecoveryBenchmarkError("comparison must be exact concrete MatchedRecoveryComparison")
        cold, resume = comparison.cold_restart, comparison.checkpoint_resume
        return cls(
            EFFICIENCY_SUMMARY_SCHEMA,
            comparison.sha256(),
            resume.final_evaluator_score - cold.final_evaluator_score,
            resume.actions_executed - cold.actions_executed,
            resume.replayed_steps - cold.replayed_steps,
            resume.repeated_work_steps - cold.repeated_work_steps,
            int(resume.terminal) - int(cold.terminal),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())
