"""Fail-closed Perception Fabric acceptance harness for Frankenstein 2.0.

F2-WP-714 generation 2 — PREPARATION_ONLY.

This module evaluates evidence *about* the Perception Fabric. It does not open devices,
perform capture, dereference external receipt bytes, call a model/provider, persist raw
frames, mutate UnifiedDB/world truth, or mint effect/completion/whole-system authority.

Generation 2 closes a successor-staleness gap discovered after F2-WP-711 generation 1 was
superseded and deliberately re-enters each accepted WP711 successor. Required upstream
evidence is bound to the exact current accepted generation/claim/scope/receipt reference.
Final-review eligibility also requires a non-synthetic clock-alignment-witness evidence-
dereference case in addition to the existing non-synthetic local real-device / OS-permission
case. At this revision the current temporal prerequisite is WP711 generation 3.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

CASE_RESULT_PASS = "PASS"
CASE_RESULT_FAIL = "FAIL"
CASE_RESULT_NOT_RUN = "NOT_RUN"
CASE_RESULTS = frozenset({CASE_RESULT_PASS, CASE_RESULT_FAIL, CASE_RESULT_NOT_RUN})

ASSESSMENT_BLOCKED = "BLOCKED"
ASSESSMENT_FAIL_CLOSED = "FAIL_CLOSED"
ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW = "ELIGIBLE_FOR_FINAL_REVIEW"

REQUIRED_UPSTREAM_WORKPACKAGES = (
    "F2-WP-708",
    "F2-WP-710",
    "F2-WP-711",
    "F2-WP-712",
    "F2-WP-713",
)

# Generation-specific acceptance prerequisites. A future accepted successor must deliberately
# update this table through the existing active WP714 generation while it remains open, or a
# successor WP714 generation after closure; otherwise the harness fails closed rather than
# silently accepting a superseded receipt.
EXPECTED_UPSTREAM_ACCEPTANCES: dict[str, dict[str, Any]] = {
    "F2-WP-708": {
        "generation": 1,
        "claim_id": "F2-WP-708-G1-GPT56SOL-OBSERVE-INTENT-20260829",
        "accepted_scope": "OBSERVE_INTENT_VISUAL_NEED_BINDING_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "receipt_ref": "workpackages/receipts/F2-WP-708_G1_OBSERVE_INTENT_MAIN_CI_33249981934.json",
    },
    "F2-WP-710": {
        "generation": 1,
        "claim_id": "F2-WP-710-G1-GPT56SOL-DYNAMIC-PERCEPTION-SCHEDULER-20260829",
        "accepted_scope": "DYNAMIC_PERCEPTION_SCHEDULER_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "receipt_ref": "workpackages/receipts/F2-WP-710_G1_DYNAMIC_PERCEPTION_SCHEDULER_MAIN_CI_33249974788.json",
    },
    "F2-WP-711": {
        "generation": 3,
        "claim_id": "F2-WP-711-G3-GPT56SOL-WITNESS-ADMISSION-FENCE-20260829",
        "accepted_scope": "TEMPORAL_OBSERVATION_WINDOW_SEPARATELY_ADMITTED_CLOCK_WITNESS_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "receipt_ref": "workpackages/receipts/F2-WP-711_G3_WITNESS_ADMISSION_MAIN_CI_33253196613.json",
    },
    "F2-WP-712": {
        "generation": 1,
        "claim_id": "F2-WP-712-G1-GPT56SOL-PERCEPTION-WORLD-BRIDGE-20260829",
        "accepted_scope": "PERCEPTION_WORLD_BRIDGE_TYPED_EVENT_PERMISSION_REVALIDATION_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "receipt_ref": "workpackages/receipts/F2-WP-712_G1_PERCEPTION_WORLD_BRIDGE_MAIN_CI_33250104685.json",
    },
    "F2-WP-713": {
        "generation": 1,
        "claim_id": "F2-WP-713-G1-GPT56SOL-DASHBOARD-AUDIT-20260829",
        "accepted_scope": "PERCEPTION_DASHBOARD_CAPABILITY_AUDIT_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "receipt_ref": "workpackages/receipts/F2-WP-713_G1_PERCEPTION_DASHBOARD_MAIN_CI_33250134474.json",
    },
}

REQUIRED_CASE_IDS = (
    "ZERO_SOURCE_HEALTH_NO_FABRICATION",
    "ONE_SOURCE_CAPTURE_EVENT_RELOOK",
    "N_SOURCES_GREATER_THAN_WORKERS",
    "FOUR_SOURCE_WHEN_AVAILABLE",
    "ZERO_BASELINE_GENERIC_VLM_CALLS",
    "ZERO_DEFAULT_RAW_FRAME_PERSISTENCE",
    "TYPED_WORLD_PROVENANCE",
    "GRID_TRIGGERED_RELOOK",
    "SOURCE_ADD_REMOVE_REBIND_CHURN",
    "QUEUED_INTENT_PERMISSION_REVOCATION",
    "CLOCK_SKEW_NO_FALSE_CONTEMPORANEITY",
    "CLOCK_ALIGNMENT_WITNESS_EVIDENCE_DEREFERENCE",
    "MEMORY_OFF_NON_RESURRECTION",
    "BRIDGE_RECONNECT_NO_STALE_REPLAY",
    "RESOURCE_PRESSURE_DEGRADES_PERCEPTION_FIRST",
    "LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PerceptionAcceptanceError(ValueError):
    """Fail-closed acceptance-harness contract error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionAcceptanceError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionAcceptanceError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PerceptionAcceptanceError(f"{name} must be an integer >= 0")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise PerceptionAcceptanceError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise PerceptionAcceptanceError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionAcceptanceError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PerceptionAcceptanceError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class UpstreamAcceptance:
    workpackage_id: str
    generation: int
    claim_id: str
    accepted_scope: str
    receipt_ref: str
    receipt_sha256: str

    schema: ClassVar[str] = "FRANKENSTEIN2_PERCEPTION_UPSTREAM_ACCEPTANCE/v2"

    def __post_init__(self) -> None:
        object.__setattr__(self, "workpackage_id", _text("workpackage_id", self.workpackage_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "claim_id", _text("claim_id", self.claim_id))
        object.__setattr__(self, "accepted_scope", _text("accepted_scope", self.accepted_scope))
        object.__setattr__(self, "receipt_ref", _text("receipt_ref", self.receipt_ref))
        _sha256("receipt_sha256", self.receipt_sha256)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "workpackage_id": self.workpackage_id,
            "generation": self.generation,
            "claim_id": self.claim_id,
            "accepted_scope": self.accepted_scope,
            "receipt_ref": self.receipt_ref,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionAcceptanceCase:
    case_id: str
    result: str
    evidence_refs: tuple[str, ...]
    synthetic: bool

    schema: ClassVar[str] = "FRANKENSTEIN2_PERCEPTION_ACCEPTANCE_CASE/v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _text("case_id", self.case_id))
        if self.case_id not in REQUIRED_CASE_IDS:
            raise PerceptionAcceptanceError(f"unknown acceptance case: {self.case_id}")
        if self.result not in CASE_RESULTS:
            raise PerceptionAcceptanceError("result must be PASS, FAIL or NOT_RUN")
        object.__setattr__(self, "evidence_refs", _refs("evidence_refs", self.evidence_refs))
        if type(self.synthetic) is not bool:
            raise PerceptionAcceptanceError("synthetic must be bool")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "case_id": self.case_id,
            "result": self.result,
            "evidence_refs": list(self.evidence_refs),
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionAcceptanceAssessment:
    assessment: str
    dependency_blockers: tuple[str, ...]
    case_blockers: tuple[str, ...]
    failed_cases: tuple[str, ...]
    local_hardware_receipt_bound: bool
    alignment_witness_evidence_bound: bool
    terminal_acceptance_minted: bool
    provenance_digest: str

    schema: ClassVar[str] = "FRANKENSTEIN2_PERCEPTION_ACCEPTANCE_ASSESSMENT/v2"
    classification: ClassVar[str] = "PREPARATION_ONLY_NO_TERMINAL_ACCEPTANCE_AUTHORITY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "assessment": self.assessment,
            "dependency_blockers": list(self.dependency_blockers),
            "case_blockers": list(self.case_blockers),
            "failed_cases": list(self.failed_cases),
            "local_hardware_receipt_bound": self.local_hardware_receipt_bound,
            "alignment_witness_evidence_bound": self.alignment_witness_evidence_bound,
            "terminal_acceptance_minted": self.terminal_acceptance_minted,
            "provenance_digest": self.provenance_digest,
            "runtime_credit": 0,
            "perception_runtime_credit": 0,
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _upstream_identity_matches_current(item: UpstreamAcceptance) -> bool:
    expected = EXPECTED_UPSTREAM_ACCEPTANCES[item.workpackage_id]
    return (
        item.generation == expected["generation"]
        and item.claim_id == expected["claim_id"]
        and item.accepted_scope == expected["accepted_scope"]
        and item.receipt_ref == expected["receipt_ref"]
    )


def assess_perception_acceptance(
    *,
    upstream_acceptances: tuple[UpstreamAcceptance, ...],
    cases: tuple[PerceptionAcceptanceCase, ...],
) -> PerceptionAcceptanceAssessment:
    """Evaluate evidence without minting terminal acceptance.

    All five current upstream acceptance identities must be represented exactly once. All
    required cases must be represented exactly once. Any FAIL dominates. Missing/NOT_RUN
    evidence blocks. The local-real-device and clock-alignment-witness-dereference cases must
    both PASS with non-synthetic evidence. Even then this preparation-only harness returns
    ELIGIBLE_FOR_FINAL_REVIEW rather than PASS.

    ``receipt_sha256`` binds externally dereferenced receipt bytes supplied to this pure
    harness. This module deliberately performs no filesystem/network dereference itself.
    """
    if type(upstream_acceptances) is not tuple or any(
        type(item) is not UpstreamAcceptance for item in upstream_acceptances
    ):
        raise PerceptionAcceptanceError(
            "upstream_acceptances must be an immutable tuple of concrete UpstreamAcceptance values"
        )
    if type(cases) is not tuple or any(type(item) is not PerceptionAcceptanceCase for item in cases):
        raise PerceptionAcceptanceError(
            "cases must be an immutable tuple of concrete PerceptionAcceptanceCase values"
        )

    upstream_ids = [item.workpackage_id for item in upstream_acceptances]
    if len(upstream_ids) != len(set(upstream_ids)):
        raise PerceptionAcceptanceError("upstream workpackage ids must not contain duplicates")
    unexpected_upstream = sorted(set(upstream_ids) - set(REQUIRED_UPSTREAM_WORKPACKAGES))
    if unexpected_upstream:
        raise PerceptionAcceptanceError(
            f"unexpected upstream workpackage ids: {', '.join(unexpected_upstream)}"
        )

    case_ids = [item.case_id for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise PerceptionAcceptanceError("acceptance case ids must not contain duplicates")

    dependency_blockers = set(REQUIRED_UPSTREAM_WORKPACKAGES) - set(upstream_ids)
    for item in upstream_acceptances:
        if not _upstream_identity_matches_current(item):
            dependency_blockers.add(f"{item.workpackage_id}:CURRENT_ACCEPTANCE_IDENTITY_MISMATCH")
    dependency_blockers_tuple = tuple(sorted(dependency_blockers))

    by_case = {item.case_id: item for item in cases}
    case_blockers = set(
        case_id
        for case_id in REQUIRED_CASE_IDS
        if case_id not in by_case or by_case[case_id].result == CASE_RESULT_NOT_RUN
    )
    failed_cases = tuple(sorted(item.case_id for item in cases if item.result == CASE_RESULT_FAIL))

    local_case = by_case.get("LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE")
    local_hardware_receipt_bound = bool(
        local_case is not None
        and local_case.result == CASE_RESULT_PASS
        and local_case.synthetic is False
    )
    if local_case is not None and local_case.result == CASE_RESULT_PASS and local_case.synthetic:
        case_blockers.add("LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE:NON_SYNTHETIC_REQUIRED")

    clock_case = by_case.get("CLOCK_ALIGNMENT_WITNESS_EVIDENCE_DEREFERENCE")
    alignment_witness_evidence_bound = bool(
        clock_case is not None
        and clock_case.result == CASE_RESULT_PASS
        and clock_case.synthetic is False
    )
    if clock_case is not None and clock_case.result == CASE_RESULT_PASS and clock_case.synthetic:
        case_blockers.add("CLOCK_ALIGNMENT_WITNESS_EVIDENCE_DEREFERENCE:NON_SYNTHETIC_REQUIRED")

    case_blockers_tuple = tuple(sorted(case_blockers))
    evidence_payload = {
        "expected_upstream_acceptances": EXPECTED_UPSTREAM_ACCEPTANCES,
        "upstream_acceptances": [
            item.as_dict() for item in sorted(upstream_acceptances, key=lambda item: item.workpackage_id)
        ],
        "cases": [item.as_dict() for item in sorted(cases, key=lambda item: item.case_id)],
    }
    provenance_digest = _digest(evidence_payload)

    if failed_cases:
        assessment = ASSESSMENT_FAIL_CLOSED
    elif (
        dependency_blockers_tuple
        or case_blockers_tuple
        or not local_hardware_receipt_bound
        or not alignment_witness_evidence_bound
    ):
        assessment = ASSESSMENT_BLOCKED
    else:
        assessment = ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW

    return PerceptionAcceptanceAssessment(
        assessment=assessment,
        dependency_blockers=dependency_blockers_tuple,
        case_blockers=case_blockers_tuple,
        failed_cases=failed_cases,
        local_hardware_receipt_bound=local_hardware_receipt_bound,
        alignment_witness_evidence_bound=alignment_witness_evidence_bound,
        terminal_acceptance_minted=False,
        provenance_digest=provenance_digest,
    )
