"""F2-WP-807 bounded general-agentic-core falsifier.

This module aggregates exact, receipt-bound held-out component measurements for four
agentic capability families: exploration, modeling, goal setting, and planning/execution.
It is inspired by the capability decomposition used by interactive ARC-AGI-3-style
benchmarks, but it is NOT an ARC-AGI-3 implementation and cannot mint an ARC score.

Inputs remain measurement claims until independently bound to their exact workpackage
reconciliation/receipt identities. Shared fixture-family identity is represented as a
SHA-256 digest and each capability record mechanically binds that digest to its exact
source reconciliation/receipt identities. The outer binder still has to verify that the
upstream evidence actually attests the supplied family digest; this component does not
turn caller input into source truth.

External environment-action count is an explicit policy-gated efficiency dimension.
Internal reasoning/tool work is intentionally outside that count; this component only
fails closed when supplied external-action evidence exceeds the declared per-capability
budget. That budget is a local falsifier policy, not an ARC score or human-baseline claim.

A supported report is therefore repository-component measurement only: no runtime,
GRID10, GWT/J-Space, model, training, effect, completion, world-truth, causal, or
whole-system credit is granted.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any

CAPABILITY_EVIDENCE_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_CAPABILITY_EVIDENCE/v2"
POLICY_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_FALSIFIER_POLICY/v2"
REPORT_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_FALSIFIER_REPORT/v1"
FAMILY_BINDING_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_FAMILY_BINDING/v1"

EXPLORATION = "EXPLORATION"
MODELING = "MODELING"
GOAL_SETTING = "GOAL_SETTING"
PLANNING_EXECUTION = "PLANNING_EXECUTION"
REQUIRED_CAPABILITIES = (
    EXPLORATION,
    MODELING,
    GOAL_SETTING,
    PLANNING_EXECUTION,
)
EXPECTED_WORKPACKAGE = {
    EXPLORATION: "F2-WP-802",
    MODELING: "F2-WP-803",
    GOAL_SETTING: "F2-WP-804",
    PLANNING_EXECUTION: "F2-WP-805",
}

ACTIVE = "ACTIVE"
ACCEPTED = "ACCEPTED"
FAILED_TERMINAL = "FAILED_TERMINAL"
RETIRED_STALE = "RETIRED_STALE"
SUPERSEDED = "SUPERSEDED"
_ALLOWED_SOURCE_STATES = frozenset((ACTIVE, ACCEPTED, FAILED_TERMINAL, RETIRED_STALE, SUPERSEDED))

NOT_EVALUABLE = "NOT_EVALUABLE"
FALSIFIED = "FALSIFIED"
SUPPORTED_AT_COMPONENT_SCOPE = "SUPPORTED_AT_COMPONENT_SCOPE"
_ALLOWED_VERDICTS = frozenset((NOT_EVALUABLE, FALSIFIED, SUPPORTED_AT_COMPONENT_SCOPE))

MEASUREMENT_CLASSIFICATION = "RECEIPT_BOUND_MEASUREMENT_CANDIDATE_NO_AUTHORITY"
REPORT_CLASSIFICATION = "REPOSITORY_COMPONENT_FALSIFIER_NO_EXTERNAL_BENCHMARK_OR_RUNTIME_CREDIT"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_GENERATION = 1_000_000
_MAX_COUNT = 1_000_000_000
_PPM = 1_000_000
_REPORT_ORIGIN = object()


class AgenticCoreFalsifierError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AgenticCoreFalsifierError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise AgenticCoreFalsifierError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise AgenticCoreFalsifierError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _bounded_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AgenticCoreFalsifierError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _bool(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise AgenticCoreFalsifierError(f"{name} must be a boolean")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def derive_family_binding_sha256(
    *,
    source_workpackage_id: str,
    source_generation: int,
    source_claim_id: str,
    source_reconciliation_sha256: str,
    source_receipt_sha256: str,
    shared_fixture_family_sha256: str,
) -> str:
    """Bind one declared shared family identity to exact upstream evidence identities.

    This is a tamper-evident identity binding, not source-content attestation. A caller that
    has not independently verified the referenced reconciliation/receipt must not promote
    this digest to factual provenance.
    """
    _id("source_workpackage_id", source_workpackage_id)
    _bounded_int("source_generation", source_generation, 1, _MAX_GENERATION)
    _id("source_claim_id", source_claim_id)
    _sha("source_reconciliation_sha256", source_reconciliation_sha256)
    _sha("source_receipt_sha256", source_receipt_sha256)
    _sha("shared_fixture_family_sha256", shared_fixture_family_sha256)
    return _digest(
        {
            "schema": FAMILY_BINDING_SCHEMA,
            "source_workpackage_id": source_workpackage_id,
            "source_generation": source_generation,
            "source_claim_id": source_claim_id,
            "source_reconciliation_sha256": source_reconciliation_sha256,
            "source_receipt_sha256": source_receipt_sha256,
            "shared_fixture_family_sha256": shared_fixture_family_sha256,
        }
    )


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    schema: str
    capability: str
    source_workpackage_id: str
    source_generation: int
    source_claim_id: str
    source_terminal_state: str
    source_terminal_scope: str
    source_reconciliation_sha256: str
    source_receipt_sha256: str
    benchmark_id: str
    holdout_set_id: str
    shared_fixture_family_sha256: str
    family_binding_sha256: str
    baseline_id: str
    baseline_score_ppm: int
    intervention_score_ppm: int
    sample_count: int
    success_count: int
    action_count: int
    classification: str = MEASUREMENT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != CAPABILITY_EVIDENCE_SCHEMA or self.classification != MEASUREMENT_CLASSIFICATION:
            raise AgenticCoreFalsifierError("capability evidence schema/classification mismatch")
        if self.capability not in REQUIRED_CAPABILITIES:
            raise AgenticCoreFalsifierError("capability is not admitted")
        expected = EXPECTED_WORKPACKAGE[self.capability]
        if self.source_workpackage_id != expected:
            raise AgenticCoreFalsifierError(
                f"{self.capability} must bind canonical source workpackage {expected}"
            )
        _bounded_int("source_generation", self.source_generation, 1, _MAX_GENERATION)
        for name, value in (
            ("source_claim_id", self.source_claim_id),
            ("source_terminal_scope", self.source_terminal_scope),
            ("benchmark_id", self.benchmark_id),
            ("holdout_set_id", self.holdout_set_id),
            ("baseline_id", self.baseline_id),
        ):
            _id(name, value)
        if self.source_terminal_state not in _ALLOWED_SOURCE_STATES:
            raise AgenticCoreFalsifierError("source_terminal_state is not admitted")
        _sha("source_reconciliation_sha256", self.source_reconciliation_sha256)
        _sha("source_receipt_sha256", self.source_receipt_sha256)
        _sha("shared_fixture_family_sha256", self.shared_fixture_family_sha256)
        _sha("family_binding_sha256", self.family_binding_sha256)
        expected_binding = derive_family_binding_sha256(
            source_workpackage_id=self.source_workpackage_id,
            source_generation=self.source_generation,
            source_claim_id=self.source_claim_id,
            source_reconciliation_sha256=self.source_reconciliation_sha256,
            source_receipt_sha256=self.source_receipt_sha256,
            shared_fixture_family_sha256=self.shared_fixture_family_sha256,
        )
        if self.family_binding_sha256 != expected_binding:
            raise AgenticCoreFalsifierError("family binding digest mismatch")
        _bounded_int("baseline_score_ppm", self.baseline_score_ppm, 0, _PPM)
        _bounded_int("intervention_score_ppm", self.intervention_score_ppm, 0, _PPM)
        _bounded_int("sample_count", self.sample_count, 1, _MAX_COUNT)
        _bounded_int("success_count", self.success_count, 0, self.sample_count)
        _bounded_int("action_count", self.action_count, 0, _MAX_COUNT)

    @property
    def delta_ppm(self) -> int:
        return self.intervention_score_ppm - self.baseline_score_ppm

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class FalsifierPolicy:
    schema: str
    policy_id: str
    generation: int
    min_intervention_score_ppm: int
    min_delta_over_baseline_ppm: int
    min_sample_count_per_capability: int
    max_external_actions_per_capability: int
    require_shared_holdout_set: bool = True

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA:
            raise AgenticCoreFalsifierError("policy schema mismatch")
        _id("policy_id", self.policy_id)
        _bounded_int("generation", self.generation, 1, _MAX_GENERATION)
        _bounded_int("min_intervention_score_ppm", self.min_intervention_score_ppm, 0, _PPM)
        _bounded_int("min_delta_over_baseline_ppm", self.min_delta_over_baseline_ppm, 0, _PPM)
        _bounded_int("min_sample_count_per_capability", self.min_sample_count_per_capability, 1, _MAX_COUNT)
        _bounded_int("max_external_actions_per_capability", self.max_external_actions_per_capability, 0, _MAX_COUNT)
        _bool("require_shared_holdout_set", self.require_shared_holdout_set)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class AgenticCoreReport:
    schema: str
    report_id: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    capability_evidence_sha256: tuple[str, ...]
    verdict: str
    reasons: tuple[str, ...]
    min_capability_score_ppm: int | None
    min_delta_over_baseline_ppm: int | None
    total_sample_count: int
    total_success_count: int
    total_action_count: int
    external_arc_agi3_credit: int = 0
    runtime_credit: int = 0
    physical_grid10_credit: int = 0
    gwt_jspace_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = REPORT_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if _origin is not _REPORT_ORIGIN:
            raise AgenticCoreFalsifierError("AgenticCoreReport must be created by evaluator API")
        if self.schema != REPORT_SCHEMA or self.classification != REPORT_CLASSIFICATION:
            raise AgenticCoreFalsifierError("report schema/classification mismatch")
        _id("report_id", self.report_id)
        _id("policy_id", self.policy_id)
        _bounded_int("policy_generation", self.policy_generation, 1, _MAX_GENERATION)
        _sha("policy_sha256", self.policy_sha256)
        if type(self.capability_evidence_sha256) is not tuple:
            raise AgenticCoreFalsifierError("capability_evidence_sha256 must be an immutable tuple")
        for value in self.capability_evidence_sha256:
            _sha("capability_evidence_sha256 item", value)
        if self.verdict not in _ALLOWED_VERDICTS:
            raise AgenticCoreFalsifierError("verdict is not admitted")
        if type(self.reasons) is not tuple or any(type(x) is not str or not x for x in self.reasons):
            raise AgenticCoreFalsifierError("reasons must be a tuple of non-empty strings")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise AgenticCoreFalsifierError("reasons must be unique and lexically sorted")
        if self.min_capability_score_ppm is not None:
            _bounded_int("min_capability_score_ppm", self.min_capability_score_ppm, 0, _PPM)
        if self.min_delta_over_baseline_ppm is not None:
            _bounded_int("min_delta_over_baseline_ppm", self.min_delta_over_baseline_ppm, -_PPM, _PPM)
        for name, value in (
            ("total_sample_count", self.total_sample_count),
            ("total_success_count", self.total_success_count),
            ("total_action_count", self.total_action_count),
        ):
            _bounded_int(name, value, 0, _MAX_COUNT)
        for name, value in (
            ("external_arc_agi3_credit", self.external_arc_agi3_credit),
            ("runtime_credit", self.runtime_credit),
            ("physical_grid10_credit", self.physical_grid10_credit),
            ("gwt_jspace_credit", self.gwt_jspace_credit),
            ("effect_credit", self.effect_credit),
            ("completion_credit", self.completion_credit),
        ):
            if value != 0:
                raise AgenticCoreFalsifierError(f"{name} must remain zero at WP807 component scope")
        if self.whole_system_acceptance is not False:
            raise AgenticCoreFalsifierError("whole_system_acceptance must remain false")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def evaluate_agentic_core(
    evidence: tuple[CapabilityEvidence, ...],
    *,
    policy: FalsifierPolicy,
    report_id: str,
) -> AgenticCoreReport:
    """Evaluate a matched four-capability evidence set with fail-closed semantics.

    Missing or non-terminal upstream evidence is NOT_EVALUABLE. Accepted evidence that
    violates matched holdout/family lineage, independence, score, delta, sample, or
    external-action budget criteria is FALSIFIED. Only a complete set satisfying every
    criterion is SUPPORTED_AT_COMPONENT_SCOPE.
    """
    if type(policy) is not FalsifierPolicy:
        raise AgenticCoreFalsifierError("policy must be exact concrete FalsifierPolicy")
    _id("report_id", report_id)
    if type(evidence) is not tuple or any(type(x) is not CapabilityEvidence for x in evidence):
        raise AgenticCoreFalsifierError("evidence must be an immutable tuple of exact CapabilityEvidence")
    if len(evidence) > len(REQUIRED_CAPABILITIES):
        raise AgenticCoreFalsifierError("evidence set exceeds one record per required capability")
    ordered = tuple(sorted(evidence, key=lambda x: x.capability))
    capabilities = tuple(x.capability for x in ordered)
    if len(set(capabilities)) != len(capabilities):
        raise AgenticCoreFalsifierError("duplicate capability evidence is not admitted")

    reasons: list[str] = []
    verdict = SUPPORTED_AT_COMPONENT_SCOPE
    missing = sorted(set(REQUIRED_CAPABILITIES) - set(capabilities))
    if missing:
        verdict = NOT_EVALUABLE
        reasons.extend(f"MISSING_CAPABILITY:{capability}" for capability in missing)

    nonaccepted = [x.capability for x in ordered if x.source_terminal_state != ACCEPTED]
    if nonaccepted:
        verdict = NOT_EVALUABLE
        reasons.extend(f"SOURCE_NOT_ACCEPTED:{capability}" for capability in sorted(nonaccepted))

    if verdict != NOT_EVALUABLE:
        receipt_shas = tuple(x.source_receipt_sha256 for x in ordered)
        reconciliation_shas = tuple(x.source_reconciliation_sha256 for x in ordered)
        if len(set(receipt_shas)) != len(receipt_shas):
            verdict = FALSIFIED
            reasons.append("NONINDEPENDENT_DUPLICATE_RECEIPT")
        if len(set(reconciliation_shas)) != len(reconciliation_shas):
            verdict = FALSIFIED
            reasons.append("NONINDEPENDENT_DUPLICATE_RECONCILIATION")
        if policy.require_shared_holdout_set and len({x.holdout_set_id for x in ordered}) != 1:
            verdict = FALSIFIED
            reasons.append("MIXED_HOLDOUT_SET")
        if len({x.shared_fixture_family_sha256 for x in ordered}) != 1:
            verdict = FALSIFIED
            reasons.append("MIXED_PROVENANCE_FAMILY")
        for item in ordered:
            if item.sample_count < policy.min_sample_count_per_capability:
                verdict = FALSIFIED
                reasons.append(f"INSUFFICIENT_SAMPLE:{item.capability}")
            if item.intervention_score_ppm < policy.min_intervention_score_ppm:
                verdict = FALSIFIED
                reasons.append(f"INTERVENTION_BELOW_FLOOR:{item.capability}")
            if item.delta_ppm < policy.min_delta_over_baseline_ppm:
                verdict = FALSIFIED
                reasons.append(f"DELTA_BELOW_BASELINE_FLOOR:{item.capability}")
            if item.action_count > policy.max_external_actions_per_capability:
                verdict = FALSIFIED
                reasons.append(f"EXTERNAL_ACTION_BUDGET_EXCEEDED:{item.capability}")

    min_score = min((x.intervention_score_ppm for x in ordered), default=None)
    min_delta = min((x.delta_ppm for x in ordered), default=None)
    total_samples = sum(x.sample_count for x in ordered)
    total_successes = sum(x.success_count for x in ordered)
    total_actions = sum(x.action_count for x in ordered)
    if any(value > _MAX_COUNT for value in (total_samples, total_successes, total_actions)):
        raise AgenticCoreFalsifierError("aggregate count exceeds bounded domain")

    return AgenticCoreReport(
        REPORT_SCHEMA,
        report_id,
        policy.policy_id,
        policy.generation,
        policy.sha256(),
        tuple(x.sha256() for x in ordered),
        verdict,
        tuple(sorted(set(reasons))),
        min_score,
        min_delta,
        total_samples,
        total_successes,
        total_actions,
        _origin=_REPORT_ORIGIN,
    )
