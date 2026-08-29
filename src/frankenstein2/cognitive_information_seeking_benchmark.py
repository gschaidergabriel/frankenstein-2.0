"""F2-WP-802 held-out information-seeking benchmark.

Policy code receives only the public ``ObservationView`` plus explicit immutable public
policy state/configuration. Hidden ``MicroWorldFixture`` state remains evaluator-side.
This is repository evaluation infrastructure only and grants no runtime, GRID/GWT/J-Space,
training, effect, completion, cognition-superiority, or world-truth authority.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any

from .cognitive_microworld import (
    BASELINE,
    INTERVENTION,
    ActionRequest,
    MatchedRunPair,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    begin_episode,
    step_episode,
)

POLICY_SCHEMA = "FRANKENSTEIN2_INFORMATION_SEEKING_POLICY/v1"
RULE_SCHEMA = "FRANKENSTEIN2_INFORMATION_SEEKING_PUBLIC_RULE/v1"
POLICY_STATE_SCHEMA = "FRANKENSTEIN2_INFORMATION_SEEKING_PUBLIC_STATE/v1"
EPISODE_RESULT_SCHEMA = "FRANKENSTEIN2_INFORMATION_SEEKING_EPISODE_RESULT/v1"
MATCHED_RESULT_SCHEMA = "FRANKENSTEIN2_INFORMATION_SEEKING_MATCHED_RESULT/v1"
PUBLIC_POLICY_CLASSIFICATION = "PUBLIC_OBSERVATION_ONLY_NO_EVALUATOR_GROUND_TRUTH"
EVALUATOR_RESULT_CLASSIFICATION = "EVALUATOR_RESULT_NOT_RUNTIME_OR_CAUSAL_CREDIT"
COMMIT_FIRST = "COMMIT_FIRST"
PROBE_THEN_COMMIT = "PROBE_THEN_COMMIT"
_ALLOWED_STRATEGIES = frozenset((COMMIT_FIRST, PROBE_THEN_COMMIT))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_ACTIONS = 4096
_MAX_PROBES = 1_000_000
_POLICY_STATE_ORIGIN = object()
_RESULT_ORIGIN = object()
_MATCHED_RESULT_ORIGIN = object()


class InformationSeekingBenchmarkError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise InformationSeekingBenchmarkError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise InformationSeekingBenchmarkError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise InformationSeekingBenchmarkError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nint(name: str, value: Any, *, maximum: int = _MAX_PROBES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise InformationSeekingBenchmarkError(f"{name} must be a non-negative integer in [0, {maximum}]")
    return value


def _action_ids(name: str, values: Any, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise InformationSeekingBenchmarkError(f"{name} must be an immutable tuple")
    if len(values) > _MAX_ACTIONS:
        raise InformationSeekingBenchmarkError(f"{name} exceeds action ceiling")
    out = tuple(_id(f"{name} item", value) for value in values)
    if nonempty and not out:
        raise InformationSeekingBenchmarkError(f"{name} must not be empty")
    if len(out) != len(set(out)):
        raise InformationSeekingBenchmarkError(f"{name} contains duplicate action ids")
    if out != tuple(sorted(out)):
        raise InformationSeekingBenchmarkError(f"{name} must be in canonical lexical order")
    return out


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PublicDecisionRule:
    schema: str
    observation_ref: str
    observation_sha256: str
    action_id: str

    def __post_init__(self) -> None:
        if self.schema != RULE_SCHEMA:
            raise InformationSeekingBenchmarkError("decision-rule schema mismatch")
        _id("observation_ref", self.observation_ref)
        _sha("observation_sha256", self.observation_sha256)
        _id("action_id", self.action_id)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InformationSeekingPolicy:
    schema: str
    policy_id: str
    strategy: str
    probe_action_ids: tuple[str, ...]
    commit_action_ids: tuple[str, ...]
    max_probes: int
    decision_rules: tuple[PublicDecisionRule, ...]
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise InformationSeekingBenchmarkError("policy schema/classification mismatch")
        _id("policy_id", self.policy_id)
        if self.strategy not in _ALLOWED_STRATEGIES:
            raise InformationSeekingBenchmarkError("unsupported information-seeking strategy")
        probes = _action_ids("probe_action_ids", self.probe_action_ids)
        commits = _action_ids("commit_action_ids", self.commit_action_ids, nonempty=True)
        if set(probes) & set(commits):
            raise InformationSeekingBenchmarkError("probe and commit action ids must be disjoint")
        _nint("max_probes", self.max_probes)
        if self.strategy == COMMIT_FIRST and self.max_probes != 0:
            raise InformationSeekingBenchmarkError("COMMIT_FIRST requires max_probes=0")
        if self.strategy == PROBE_THEN_COMMIT and (self.max_probes < 1 or not probes):
            raise InformationSeekingBenchmarkError("PROBE_THEN_COMMIT requires probe actions and positive max_probes")
        if type(self.decision_rules) is not tuple or any(type(x) is not PublicDecisionRule for x in self.decision_rules):
            raise InformationSeekingBenchmarkError("decision_rules must contain exact concrete PublicDecisionRule values")
        expected = tuple(sorted(self.decision_rules, key=lambda x: (x.observation_ref, x.observation_sha256, x.action_id)))
        if self.decision_rules != expected:
            raise InformationSeekingBenchmarkError("decision_rules must be in canonical lexical order")
        keys = tuple((x.observation_ref, x.observation_sha256) for x in self.decision_rules)
        if len(keys) != len(set(keys)):
            raise InformationSeekingBenchmarkError("at most one decision rule is allowed per public observation")
        if any(rule.action_id not in commits for rule in self.decision_rules):
            raise InformationSeekingBenchmarkError("decision rules may choose only declared commit actions")

    def rule_for(self, observation: ObservationView) -> PublicDecisionRule | None:
        if type(observation) is not ObservationView:
            raise InformationSeekingBenchmarkError("observation must be exact concrete ObservationView")
        for rule in self.decision_rules:
            if (rule.observation_ref, rule.observation_sha256) == (
                observation.observation_ref,
                observation.observation_sha256,
            ):
                return rule
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "strategy": self.strategy,
            "probe_action_ids": list(self.probe_action_ids),
            "commit_action_ids": list(self.commit_action_ids),
            "max_probes": self.max_probes,
            "decision_rules": [x.as_dict() for x in self.decision_rules],
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PublicPolicyState:
    schema: str
    policy_id: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    probes_used: int
    seen_public_payload_sha256s: tuple[str, ...]
    classification: str = PUBLIC_POLICY_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != POLICY_STATE_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise InformationSeekingBenchmarkError("policy-state schema/classification mismatch")
        _id("policy_id", self.policy_id)
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _nint("step_index", self.step_index)
        _nint("probes_used", self.probes_used)
        if type(self.seen_public_payload_sha256s) is not tuple or not self.seen_public_payload_sha256s:
            raise InformationSeekingBenchmarkError("seen public payload digests must be a non-empty immutable tuple")
        for value in self.seen_public_payload_sha256s:
            _sha("seen public payload digest", value)
        if len(self.seen_public_payload_sha256s) != len(set(self.seen_public_payload_sha256s)):
            raise InformationSeekingBenchmarkError("seen public payload digests must be unique")
        if _origin is not _POLICY_STATE_ORIGIN:
            raise InformationSeekingBenchmarkError("PublicPolicyState must be created by the public policy-state API")

    @classmethod
    def for_observation(cls, policy: InformationSeekingPolicy, observation: ObservationView) -> "PublicPolicyState":
        if type(policy) is not InformationSeekingPolicy:
            raise InformationSeekingBenchmarkError("policy must be exact concrete InformationSeekingPolicy")
        if type(observation) is not ObservationView:
            raise InformationSeekingBenchmarkError("observation must be exact concrete ObservationView")
        return cls(
            POLICY_STATE_SCHEMA,
            policy.policy_id,
            observation.episode_id,
            observation.episode_generation,
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            observation.step_index,
            0,
            (observation.observation_sha256,),
            _origin=_POLICY_STATE_ORIGIN,
        )

    def assert_matches(self, policy: InformationSeekingPolicy, observation: ObservationView) -> None:
        if type(policy) is not InformationSeekingPolicy or type(observation) is not ObservationView:
            raise InformationSeekingBenchmarkError("policy/observation must be exact concrete public values")
        expected = (
            policy.policy_id,
            observation.episode_id,
            observation.episode_generation,
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            observation.step_index,
        )
        actual = (
            self.policy_id,
            self.episode_id,
            self.episode_generation,
            self.fixture_id,
            self.fixture_generation,
            self.public_fixture_sha256,
            self.step_index,
        )
        if actual != expected:
            raise InformationSeekingBenchmarkError("public policy state does not match current observation lineage")
        if observation.observation_sha256 not in self.seen_public_payload_sha256s:
            raise InformationSeekingBenchmarkError("current public observation is absent from policy state")
        if self.probes_used > policy.max_probes:
            raise InformationSeekingBenchmarkError("policy state exceeds declared probe budget")

    def advance(
        self,
        policy: InformationSeekingPolicy,
        *,
        prior_observation: ObservationView,
        action_id: str,
        next_observation: ObservationView,
    ) -> "PublicPolicyState":
        self.assert_matches(policy, prior_observation)
        if type(next_observation) is not ObservationView:
            raise InformationSeekingBenchmarkError("next observation must be exact concrete ObservationView")
        if (
            next_observation.episode_id,
            next_observation.episode_generation,
            next_observation.fixture_id,
            next_observation.fixture_generation,
            next_observation.public_fixture_sha256,
            next_observation.step_index,
        ) != (
            prior_observation.episode_id,
            prior_observation.episode_generation,
            prior_observation.fixture_id,
            prior_observation.fixture_generation,
            prior_observation.public_fixture_sha256,
            prior_observation.step_index + 1,
        ):
            raise InformationSeekingBenchmarkError("next public observation breaks episode/fixture/step lineage")
        _id("action_id", action_id)
        probes_used = self.probes_used + (1 if action_id in set(policy.probe_action_ids) else 0)
        if probes_used > policy.max_probes:
            raise InformationSeekingBenchmarkError("probe action exceeds declared probe budget")
        seen = self.seen_public_payload_sha256s
        if next_observation.observation_sha256 not in seen:
            seen = seen + (next_observation.observation_sha256,)
        return PublicPolicyState(
            POLICY_STATE_SCHEMA,
            self.policy_id,
            self.episode_id,
            self.episode_generation,
            self.fixture_id,
            self.fixture_generation,
            self.public_fixture_sha256,
            next_observation.step_index,
            probes_used,
            seen,
            _origin=_POLICY_STATE_ORIGIN,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def choose_public_action(
    policy: InformationSeekingPolicy,
    state: PublicPolicyState,
    observation: ObservationView,
) -> ActionRequest:
    if type(policy) is not InformationSeekingPolicy or type(state) is not PublicPolicyState:
        raise InformationSeekingBenchmarkError("policy/state must be exact concrete public policy values")
    if type(observation) is not ObservationView:
        raise InformationSeekingBenchmarkError("observation must be exact concrete ObservationView")
    state.assert_matches(policy, observation)
    if observation.terminal:
        raise InformationSeekingBenchmarkError("terminal observation requires no policy action")
    available = set(observation.available_action_ids)
    commits = tuple(action for action in policy.commit_action_ids if action in available)
    probes = tuple(action for action in policy.probe_action_ids if action in available)
    if not commits:
        raise InformationSeekingBenchmarkError("no declared commit action is available")

    rule = policy.rule_for(observation)
    if policy.strategy == COMMIT_FIRST:
        action_id = commits[0]
    elif rule is not None:
        if rule.action_id not in available:
            raise InformationSeekingBenchmarkError("public decision rule selects unavailable commit action")
        action_id = rule.action_id
    elif state.probes_used < policy.max_probes:
        if not probes:
            raise InformationSeekingBenchmarkError("probe budget remains but no declared probe action is available")
        action_id = probes[0]
    else:
        action_id = commits[0]
    return ActionRequest.for_observation(observation, action_id=action_id)


@dataclass(frozen=True, slots=True)
class PolicyEpisodeResult:
    schema: str
    run_id: str
    run_descriptor_sha256: str
    policy_id: str
    policy_sha256: str
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    public_fixture_sha256: str
    episode_id: str
    episode_generation: int
    terminal: bool
    step_count: int
    cumulative_score: int
    probe_count: int
    unique_public_payload_count: int
    action_ids: tuple[str, ...]
    evaluator_step_sha256s: tuple[str, ...]
    final_observation_sha256: str
    classification: str = EVALUATOR_RESULT_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != EPISODE_RESULT_SCHEMA or self.classification != EVALUATOR_RESULT_CLASSIFICATION:
            raise InformationSeekingBenchmarkError("episode-result schema/classification mismatch")
        for name, value in (("run_id", self.run_id), ("policy_id", self.policy_id), ("fixture_id", self.fixture_id), ("episode_id", self.episode_id)):
            _id(name, value)
        for name, value in (("run_descriptor_sha256", self.run_descriptor_sha256), ("policy_sha256", self.policy_sha256), ("fixture_sha256", self.fixture_sha256), ("public_fixture_sha256", self.public_fixture_sha256), ("final_observation_sha256", self.final_observation_sha256)):
            _sha(name, value)
        _nint("fixture_generation", self.fixture_generation)
        _nint("episode_generation", self.episode_generation)
        _nint("step_count", self.step_count)
        _nint("probe_count", self.probe_count)
        _nint("unique_public_payload_count", self.unique_public_payload_count)
        if type(self.terminal) is not bool:
            raise InformationSeekingBenchmarkError("terminal must be a boolean")
        if type(self.cumulative_score) is not int or isinstance(self.cumulative_score, bool):
            raise InformationSeekingBenchmarkError("cumulative_score must be an integer")
        if type(self.action_ids) is not tuple or any(type(x) is not str for x in self.action_ids):
            raise InformationSeekingBenchmarkError("action_ids must be an immutable string tuple")
        if type(self.evaluator_step_sha256s) is not tuple:
            raise InformationSeekingBenchmarkError("evaluator_step_sha256s must be an immutable tuple")
        for value in self.evaluator_step_sha256s:
            _sha("evaluator step digest", value)
        if len(self.action_ids) != self.step_count or len(self.evaluator_step_sha256s) != self.step_count:
            raise InformationSeekingBenchmarkError("episode result step evidence length mismatch")
        if self.probe_count > self.step_count or self.unique_public_payload_count < 1:
            raise InformationSeekingBenchmarkError("episode result count invariant violated")
        if _origin is not _RESULT_ORIGIN:
            raise InformationSeekingBenchmarkError("PolicyEpisodeResult must be created by run_policy_episode")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def run_policy_episode(fixture: MicroWorldFixture, *, run: RunDescriptor, policy: InformationSeekingPolicy, episode_id: str, episode_generation: int) -> PolicyEpisodeResult:
    if type(fixture) is not MicroWorldFixture:
        raise InformationSeekingBenchmarkError("fixture must be exact concrete MicroWorldFixture")
    if type(run) is not RunDescriptor:
        raise InformationSeekingBenchmarkError("run must be exact concrete RunDescriptor")
    if type(policy) is not InformationSeekingPolicy:
        raise InformationSeekingBenchmarkError("policy must be exact concrete InformationSeekingPolicy")
    run.assert_matches_fixture(fixture)
    if run.system_under_test_ref != policy.policy_id:
        raise InformationSeekingBenchmarkError("run descriptor does not bind the exact policy id")
    _id("episode_id", episode_id)
    _nint("episode_generation", episode_generation)

    evaluator_state, observation = begin_episode(fixture, episode_id=episode_id, episode_generation=episode_generation)
    public_state = PublicPolicyState.for_observation(policy, observation)
    action_ids: list[str] = []
    step_digests: list[str] = []
    while not observation.terminal:
        request = choose_public_action(policy, public_state, observation)
        next_state, next_observation, evaluator_step = step_episode(fixture, state=evaluator_state, request=request)
        public_state = public_state.advance(policy, prior_observation=observation, action_id=request.action_id, next_observation=next_observation)
        action_ids.append(request.action_id)
        step_digests.append(evaluator_step.sha256())
        evaluator_state, observation = next_state, next_observation

    return PolicyEpisodeResult(
        EPISODE_RESULT_SCHEMA,
        run.run_id,
        run.sha256(),
        policy.policy_id,
        policy.sha256(),
        fixture.fixture_id,
        fixture.generation,
        fixture.sha256(),
        fixture.public_sha256(),
        episode_id,
        episode_generation,
        observation.terminal,
        evaluator_state.step_index,
        evaluator_state.cumulative_score,
        public_state.probes_used,
        len(public_state.seen_public_payload_sha256s),
        tuple(action_ids),
        tuple(step_digests),
        observation.sha256(),
        _origin=_RESULT_ORIGIN,
    )


@dataclass(frozen=True, slots=True)
class MatchedInformationSeekingResult:
    schema: str
    pair_id: str
    pair_sha256: str
    baseline: PolicyEpisodeResult
    intervention: PolicyEpisodeResult
    score_delta: int
    probe_delta: int
    public_payload_novelty_delta: int
    classification: str = EVALUATOR_RESULT_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != MATCHED_RESULT_SCHEMA or self.classification != EVALUATOR_RESULT_CLASSIFICATION:
            raise InformationSeekingBenchmarkError("matched-result schema/classification mismatch")
        _id("pair_id", self.pair_id)
        _sha("pair_sha256", self.pair_sha256)
        if type(self.baseline) is not PolicyEpisodeResult or type(self.intervention) is not PolicyEpisodeResult:
            raise InformationSeekingBenchmarkError("matched result requires exact episode results")
        if self.score_delta != self.intervention.cumulative_score - self.baseline.cumulative_score:
            raise InformationSeekingBenchmarkError("score_delta does not match episode results")
        if self.probe_delta != self.intervention.probe_count - self.baseline.probe_count:
            raise InformationSeekingBenchmarkError("probe_delta does not match episode results")
        if self.public_payload_novelty_delta != self.intervention.unique_public_payload_count - self.baseline.unique_public_payload_count:
            raise InformationSeekingBenchmarkError("public_payload_novelty_delta does not match episode results")
        if _origin is not _MATCHED_RESULT_ORIGIN:
            raise InformationSeekingBenchmarkError("MatchedInformationSeekingResult must be created by the matched benchmark API")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pair_id": self.pair_id,
            "pair_sha256": self.pair_sha256,
            "baseline": self.baseline.as_dict(),
            "intervention": self.intervention.as_dict(),
            "score_delta": self.score_delta,
            "probe_delta": self.probe_delta,
            "public_payload_novelty_delta": self.public_payload_novelty_delta,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def run_matched_information_seeking_benchmark(fixture: MicroWorldFixture, *, pair: MatchedRunPair, baseline_policy: InformationSeekingPolicy, intervention_policy: InformationSeekingPolicy, episode_generation: int = 1) -> MatchedInformationSeekingResult:
    if type(fixture) is not MicroWorldFixture:
        raise InformationSeekingBenchmarkError("fixture must be exact concrete MicroWorldFixture")
    if type(pair) is not MatchedRunPair:
        raise InformationSeekingBenchmarkError("pair must be exact concrete MatchedRunPair")
    if type(baseline_policy) is not InformationSeekingPolicy or type(intervention_policy) is not InformationSeekingPolicy:
        raise InformationSeekingBenchmarkError("matched policies must be exact concrete InformationSeekingPolicy values")
    pair.baseline.assert_matches_fixture(fixture)
    pair.intervention.assert_matches_fixture(fixture)
    if pair.baseline.condition != BASELINE or pair.intervention.condition != INTERVENTION:
        raise InformationSeekingBenchmarkError("matched benchmark requires BASELINE then INTERVENTION conditions")
    if baseline_policy.strategy != COMMIT_FIRST or intervention_policy.strategy != PROBE_THEN_COMMIT:
        raise InformationSeekingBenchmarkError("matched benchmark requires COMMIT_FIRST vs PROBE_THEN_COMMIT")
    if pair.baseline.system_under_test_ref != baseline_policy.policy_id:
        raise InformationSeekingBenchmarkError("baseline run/policy identity mismatch")
    if pair.intervention.system_under_test_ref != intervention_policy.policy_id:
        raise InformationSeekingBenchmarkError("intervention run/policy identity mismatch")
    _nint("episode_generation", episode_generation)

    baseline_result = run_policy_episode(fixture, run=pair.baseline, policy=baseline_policy, episode_id=f"episode:{pair.baseline.run_id}", episode_generation=episode_generation)
    intervention_result = run_policy_episode(fixture, run=pair.intervention, policy=intervention_policy, episode_id=f"episode:{pair.intervention.run_id}", episode_generation=episode_generation)
    return MatchedInformationSeekingResult(
        MATCHED_RESULT_SCHEMA,
        pair.pair_id,
        pair.sha256(),
        baseline_result,
        intervention_result,
        intervention_result.cumulative_score - baseline_result.cumulative_score,
        intervention_result.probe_count - baseline_result.probe_count,
        intervention_result.unique_public_payload_count - baseline_result.unique_public_payload_count,
        _origin=_MATCHED_RESULT_ORIGIN,
    )
