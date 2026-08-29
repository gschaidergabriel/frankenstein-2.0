"""F2-WP-807 repository-bound outer evidence admission.

This layer closes the boundary left intentionally open by the inner WP807 agentic-core
falsifier: caller-supplied CapabilityEvidence is only a measurement claim. Repository-bound
evaluation must first authenticate the canonical active -> reconciliation -> acceptance
receipt chain and must load capability measurements from checked-in measurement records.

This module does not make repository text into world truth. It establishes deterministic
repository provenance only. Missing measurement records remain NOT_EVALUABLE. A bound
repository result grants no runtime, physical GRID10, GWT/J-Space, model/provider, training,
effect, completion, external ARC-AGI-3, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .cognitive_agentic_core_falsifier import (
    ACCEPTED,
    CAPABILITY_EVIDENCE_SCHEMA,
    EXPLORATION,
    GOAL_SETTING,
    MODELING,
    NOT_EVALUABLE,
    PLANNING_EXECUTION,
    REQUIRED_CAPABILITIES,
    AgenticCoreReport,
    CapabilityEvidence,
    FalsifierPolicy,
    derive_family_binding_sha256,
    evaluate_agentic_core,
)

SOURCE_BINDING_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_REPOSITORY_SOURCE_BINDING/v1"
MEASUREMENT_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_HELDOUT_MEASUREMENT_RECORD/v1"
OUTER_REPORT_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_REPOSITORY_BOUND_REPORT/v1"
SOURCE_CLASSIFICATION = "REPOSITORY_PROVENANCE_ONLY_NO_CAPABILITY_OR_RUNTIME_AUTHORITY"
MEASUREMENT_CLASSIFICATION = "REPOSITORY_MEASUREMENT_RECORD_NO_WORLD_OR_RUNTIME_AUTHORITY"
OUTER_CLASSIFICATION = "REPOSITORY_BOUND_COMPONENT_FALSIFIER_NO_RUNTIME_OR_EXTERNAL_BENCHMARK_CREDIT"

EXPECTED_WORKPACKAGE = {
    EXPLORATION: "F2-WP-802",
    MODELING: "F2-WP-803",
    GOAL_SETTING: "F2-WP-804",
    PLANNING_EXECUTION: "F2-WP-805",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_COUNT = 1_000_000_000
_PPM = 1_000_000


class RepositoryEvidenceBindingError(ValueError):
    pass


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _require_str(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RepositoryEvidenceBindingError(f"{name} must be a non-empty trimmed string")
    return value


def _require_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise RepositoryEvidenceBindingError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _require_sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RepositoryEvidenceBindingError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _require_git_sha(name: str, value: Any) -> str:
    if type(value) is not str or _GIT_SHA_RE.fullmatch(value) is None:
        raise RepositoryEvidenceBindingError(f"{name} must be lowercase 40-hex Git SHA")
    return value


def _safe_path(root: Path, rel: str) -> Path:
    _require_str("repository relative path", rel)
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise RepositoryEvidenceBindingError("repository path escapes root") from exc
    return candidate


def _read_json(root: Path, rel: str) -> tuple[dict[str, Any], str]:
    path = _safe_path(root, rel)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise RepositoryEvidenceBindingError(f"missing repository artifact: {rel}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryEvidenceBindingError(f"invalid UTF-8 JSON artifact: {rel}") from exc
    if type(value) is not dict:
        raise RepositoryEvidenceBindingError(f"repository artifact must be a JSON object: {rel}")
    return value, _digest_bytes(raw)


def _assert_zero_credit(value: Mapping[str, Any], *, artifact: str) -> None:
    for key in (
        "runtime_credit",
        "target_vps_runtime_credit",
        "physical_grid10_credit",
        "gwt_runtime_credit",
        "jspace_runtime_credit",
        "provider_model_credit",
        "training_credit",
        "effect_credit",
        "completion_credit",
        "recovery_efficiency_result_credit",
        "goal_authority_credit",
    ):
        if key in value and value[key] != 0:
            raise RepositoryEvidenceBindingError(f"{artifact} attempts nonzero {key}")
    if value.get("whole_system_acceptance", False) is not False:
        raise RepositoryEvidenceBindingError(f"{artifact} attempts whole-system acceptance")


def _main_ci_success(receipt: Mapping[str, Any]) -> tuple[int, int | None, str]:
    ci = receipt.get("repository_hosted_ci")
    nested_merged = False
    if type(ci) is not dict:
        ci = receipt.get("merged_main_ci")
        nested_merged = type(ci) is dict
    if type(ci) is not dict:
        raise RepositoryEvidenceBindingError("acceptance receipt lacks merged-main CI evidence")
    conclusion = ci.get("merged_main_conclusion", ci.get("conclusion", ci.get("main_conclusion")))
    if conclusion != "success":
        raise RepositoryEvidenceBindingError("acceptance receipt does not prove successful merged-main CI")
    if nested_merged:
        run_id = ci.get("run_id", ci.get("g3_run_id"))
        job_id = ci.get("job_id", ci.get("g3_job_id"))
        head_sha = ci.get("head_sha", receipt.get("merge_commit"))
    else:
        run_id = ci.get("merged_main_run_id", ci.get("main_run_id"))
        job_id = ci.get("merged_main_job_id", ci.get("main_job_id"))
        head_sha = ci.get("merged_main_head_sha", ci.get("main_head_sha"))
    _require_int("merged-main run id", run_id, 1, _MAX_COUNT)
    if job_id is not None:
        _require_int("merged-main job id", job_id, 1, _MAX_COUNT)
    _require_git_sha("merged-main head sha", head_sha)
    return run_id, job_id, head_sha


@dataclass(frozen=True, slots=True)
class RepositorySourceBinding:
    schema: str
    capability: str
    workpackage_id: str
    generation: int
    claim_id: str
    terminal_scope: str
    active_path: str
    active_content_sha256: str
    reconciliation_path: str
    reconciliation_content_sha256: str
    receipt_path: str
    receipt_content_sha256: str
    merged_main_run_id: int
    merged_main_job_id: int | None
    merged_main_head_sha: str
    classification: str = SOURCE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != SOURCE_BINDING_SCHEMA or self.classification != SOURCE_CLASSIFICATION:
            raise RepositoryEvidenceBindingError("source binding schema/classification mismatch")
        if self.capability not in REQUIRED_CAPABILITIES:
            raise RepositoryEvidenceBindingError("source binding capability is not admitted")
        if self.workpackage_id != EXPECTED_WORKPACKAGE[self.capability]:
            raise RepositoryEvidenceBindingError("source binding workpackage/capability mismatch")
        _require_int("generation", self.generation, 1, 1_000_000)
        for name, value in (
            ("claim_id", self.claim_id),
            ("terminal_scope", self.terminal_scope),
            ("active_path", self.active_path),
            ("reconciliation_path", self.reconciliation_path),
            ("receipt_path", self.receipt_path),
        ):
            _require_str(name, value)
        for name, value in (
            ("active_content_sha256", self.active_content_sha256),
            ("reconciliation_content_sha256", self.reconciliation_content_sha256),
            ("receipt_content_sha256", self.receipt_content_sha256),
        ):
            _require_sha256(name, value)
        _require_int("merged_main_run_id", self.merged_main_run_id, 1, _MAX_COUNT)
        if self.merged_main_job_id is not None:
            _require_int("merged_main_job_id", self.merged_main_job_id, 1, _MAX_COUNT)
        _require_git_sha("merged_main_head_sha", self.merged_main_head_sha)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def bind_repository_source(repository_root: str | Path, capability: str) -> RepositorySourceBinding:
    if capability not in REQUIRED_CAPABILITIES:
        raise RepositoryEvidenceBindingError("capability is not admitted")
    root = Path(repository_root)
    wp = EXPECTED_WORKPACKAGE[capability]
    active_rel = f"workpackages/active/{wp}.json"
    active, active_sha = _read_json(root, active_rel)

    if active.get("workpackage_id") != wp:
        raise RepositoryEvidenceBindingError("active pointer workpackage mismatch")
    generation = _require_int("active generation", active.get("generation"), 1, 1_000_000)
    claim_id = _require_str("active claim_id", active.get("claim_id"))
    if active.get("state") != ACCEPTED:
        raise RepositoryEvidenceBindingError(f"{wp} active pointer is not ACCEPTED")
    scope = _require_str("active terminal_scope", active.get("terminal_scope"))
    reconciliation_rel = _require_str("active reconciliation_ref", active.get("reconciliation_ref"))
    receipt_rel = _require_str("active acceptance_receipt", active.get("acceptance_receipt"))
    if not reconciliation_rel.startswith(f"workpackages/reconciliations/{wp}/"):
        raise RepositoryEvidenceBindingError("reconciliation path is outside canonical workpackage namespace")
    if not receipt_rel.startswith("workpackages/receipts/"):
        raise RepositoryEvidenceBindingError("receipt path is outside canonical receipt namespace")
    if active.get("component_test_execution_observed") is not True:
        raise RepositoryEvidenceBindingError("active pointer lacks component test execution observation")
    _assert_zero_credit(active, artifact="active pointer")

    reconciliation, reconciliation_sha = _read_json(root, reconciliation_rel)
    if reconciliation.get("schema") != "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1":
        raise RepositoryEvidenceBindingError("reconciliation schema mismatch")
    if (
        reconciliation.get("workpackage_id"),
        reconciliation.get("generation"),
        reconciliation.get("claim_id"),
        reconciliation.get("terminal_state"),
        reconciliation.get("terminal_scope"),
    ) != (wp, generation, claim_id, ACCEPTED, scope):
        raise RepositoryEvidenceBindingError("reconciliation does not match active terminal identity")
    if reconciliation.get("acceptance_receipt") != receipt_rel:
        raise RepositoryEvidenceBindingError("reconciliation receipt pointer mismatch")
    _assert_zero_credit(reconciliation, artifact="reconciliation")

    receipt, receipt_sha = _read_json(root, receipt_rel)
    if receipt.get("schema") != "FRANKENSTEIN2_WORKPACKAGE_ACCEPTANCE_RECEIPT/v1":
        raise RepositoryEvidenceBindingError("acceptance receipt schema mismatch")
    if (
        receipt.get("workpackage_id"),
        receipt.get("generation"),
        receipt.get("claim_id"),
        receipt.get("acceptance_scope"),
    ) != (wp, generation, claim_id, scope):
        raise RepositoryEvidenceBindingError("acceptance receipt does not match active terminal identity")
    _assert_zero_credit(receipt, artifact="acceptance receipt")
    run_id, job_id, head_sha = _main_ci_success(receipt)

    return RepositorySourceBinding(
        SOURCE_BINDING_SCHEMA,
        capability,
        wp,
        generation,
        claim_id,
        scope,
        active_rel,
        active_sha,
        reconciliation_rel,
        reconciliation_sha,
        receipt_rel,
        receipt_sha,
        run_id,
        job_id,
        head_sha,
    )


@dataclass(frozen=True, slots=True)
class RepositoryMeasurementRecord:
    schema: str
    capability: str
    source_workpackage_id: str
    source_generation: int
    source_claim_id: str
    source_reconciliation_content_sha256: str
    source_receipt_content_sha256: str
    benchmark_id: str
    holdout_set_id: str
    shared_fixture_family_sha256: str
    baseline_id: str
    baseline_score_ppm: int
    intervention_score_ppm: int
    sample_count: int
    success_count: int
    action_count: int
    measurement_head_sha: str
    measurement_run_id: int
    measurement_job_id: int
    producer_result_sha256: str
    classification: str = MEASUREMENT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != MEASUREMENT_SCHEMA or self.classification != MEASUREMENT_CLASSIFICATION:
            raise RepositoryEvidenceBindingError("measurement schema/classification mismatch")
        if self.capability not in REQUIRED_CAPABILITIES:
            raise RepositoryEvidenceBindingError("measurement capability is not admitted")
        if self.source_workpackage_id != EXPECTED_WORKPACKAGE[self.capability]:
            raise RepositoryEvidenceBindingError("measurement source workpackage mismatch")
        _require_int("source_generation", self.source_generation, 1, 1_000_000)
        for name, value in (
            ("source_claim_id", self.source_claim_id),
            ("benchmark_id", self.benchmark_id),
            ("holdout_set_id", self.holdout_set_id),
            ("baseline_id", self.baseline_id),
        ):
            _require_str(name, value)
        for name, value in (
            ("source_reconciliation_content_sha256", self.source_reconciliation_content_sha256),
            ("source_receipt_content_sha256", self.source_receipt_content_sha256),
            ("shared_fixture_family_sha256", self.shared_fixture_family_sha256),
            ("producer_result_sha256", self.producer_result_sha256),
        ):
            _require_sha256(name, value)
        _require_int("baseline_score_ppm", self.baseline_score_ppm, 0, _PPM)
        _require_int("intervention_score_ppm", self.intervention_score_ppm, 0, _PPM)
        _require_int("sample_count", self.sample_count, 1, _MAX_COUNT)
        _require_int("success_count", self.success_count, 0, self.sample_count)
        _require_int("action_count", self.action_count, 0, _MAX_COUNT)
        _require_git_sha("measurement_head_sha", self.measurement_head_sha)
        _require_int("measurement_run_id", self.measurement_run_id, 1, _MAX_COUNT)
        _require_int("measurement_job_id", self.measurement_job_id, 1, _MAX_COUNT)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def load_repository_measurement(
    repository_root: str | Path,
    binding: RepositorySourceBinding,
    measurement_path: str,
) -> tuple[RepositoryMeasurementRecord, str]:
    if type(binding) is not RepositorySourceBinding:
        raise RepositoryEvidenceBindingError("binding must be exact RepositorySourceBinding")
    data, content_sha = _read_json(Path(repository_root), measurement_path)
    try:
        record = RepositoryMeasurementRecord(**data)
    except TypeError as exc:
        raise RepositoryEvidenceBindingError("measurement record fields do not match schema") from exc
    expected = (
        binding.capability,
        binding.workpackage_id,
        binding.generation,
        binding.claim_id,
        binding.reconciliation_content_sha256,
        binding.receipt_content_sha256,
    )
    actual = (
        record.capability,
        record.source_workpackage_id,
        record.source_generation,
        record.source_claim_id,
        record.source_reconciliation_content_sha256,
        record.source_receipt_content_sha256,
    )
    if actual != expected:
        raise RepositoryEvidenceBindingError("measurement record does not bind exact accepted source chain")
    return record, content_sha


def capability_evidence_from_repository(
    repository_root: str | Path,
    capability: str,
    measurement_path: str,
) -> tuple[CapabilityEvidence, RepositorySourceBinding, RepositoryMeasurementRecord, str]:
    binding = bind_repository_source(repository_root, capability)
    record, measurement_content_sha = load_repository_measurement(repository_root, binding, measurement_path)
    family_binding = derive_family_binding_sha256(
        source_workpackage_id=binding.workpackage_id,
        source_generation=binding.generation,
        source_claim_id=binding.claim_id,
        source_reconciliation_sha256=binding.reconciliation_content_sha256,
        source_receipt_sha256=binding.receipt_content_sha256,
        shared_fixture_family_sha256=record.shared_fixture_family_sha256,
    )
    evidence = CapabilityEvidence(
        CAPABILITY_EVIDENCE_SCHEMA,
        capability,
        binding.workpackage_id,
        binding.generation,
        binding.claim_id,
        ACCEPTED,
        binding.terminal_scope,
        binding.reconciliation_content_sha256,
        binding.receipt_content_sha256,
        record.benchmark_id,
        record.holdout_set_id,
        record.shared_fixture_family_sha256,
        family_binding,
        record.baseline_id,
        record.baseline_score_ppm,
        record.intervention_score_ppm,
        record.sample_count,
        record.success_count,
        record.action_count,
    )
    return evidence, binding, record, measurement_content_sha


@dataclass(frozen=True, slots=True)
class RepositoryBoundAgenticCoreReport:
    schema: str
    report_id: str
    verdict: str
    reasons: tuple[str, ...]
    source_binding_sha256s: tuple[str, ...]
    measurement_content_sha256s: tuple[str, ...]
    inner_report_sha256: str | None
    inner_report: AgenticCoreReport | None
    runtime_credit: int = 0
    physical_grid10_credit: int = 0
    gwt_jspace_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    classification: str = OUTER_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != OUTER_REPORT_SCHEMA or self.classification != OUTER_CLASSIFICATION:
            raise RepositoryEvidenceBindingError("outer report schema/classification mismatch")
        _require_str("report_id", self.report_id)
        if self.verdict not in (NOT_EVALUABLE, "FALSIFIED", "SUPPORTED_AT_COMPONENT_SCOPE"):
            raise RepositoryEvidenceBindingError("outer report verdict is not admitted")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise RepositoryEvidenceBindingError("outer report reasons must be unique and sorted")
        for value in (*self.source_binding_sha256s, *self.measurement_content_sha256s):
            _require_sha256("outer report evidence digest", value)
        if self.inner_report is None:
            if self.inner_report_sha256 is not None:
                raise RepositoryEvidenceBindingError("outer report has digest without inner report")
        else:
            if type(self.inner_report) is not AgenticCoreReport:
                raise RepositoryEvidenceBindingError("inner_report must be exact AgenticCoreReport")
            if self.inner_report_sha256 != self.inner_report.sha256():
                raise RepositoryEvidenceBindingError("inner report digest mismatch")
            if self.verdict != self.inner_report.verdict:
                raise RepositoryEvidenceBindingError("outer/inner verdict mismatch")
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
            raise RepositoryEvidenceBindingError("outer report cannot mint higher-scope credit")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def evaluate_repository_bound_agentic_core(
    repository_root: str | Path,
    measurement_paths: Mapping[str, str],
    *,
    policy: FalsifierPolicy,
    report_id: str,
) -> RepositoryBoundAgenticCoreReport:
    if type(policy) is not FalsifierPolicy:
        raise RepositoryEvidenceBindingError("policy must be exact FalsifierPolicy")
    if not isinstance(measurement_paths, Mapping):
        raise RepositoryEvidenceBindingError("measurement_paths must be a mapping")

    missing = tuple(sorted(set(REQUIRED_CAPABILITIES) - set(measurement_paths)))
    extra = tuple(sorted(set(measurement_paths) - set(REQUIRED_CAPABILITIES)))
    if extra:
        raise RepositoryEvidenceBindingError("measurement_paths contains non-admitted capabilities")

    bindings: list[RepositorySourceBinding] = []
    measurement_digests: list[str] = []
    evidence: list[CapabilityEvidence] = []
    reasons = [f"MISSING_REPOSITORY_MEASUREMENT:{capability}" for capability in missing]

    for capability in REQUIRED_CAPABILITIES:
        binding = bind_repository_source(repository_root, capability)
        bindings.append(binding)
        if capability in missing:
            continue
        item, _, _, measurement_digest = capability_evidence_from_repository(
            repository_root,
            capability,
            measurement_paths[capability],
        )
        evidence.append(item)
        measurement_digests.append(measurement_digest)

    if missing:
        return RepositoryBoundAgenticCoreReport(
            OUTER_REPORT_SCHEMA,
            report_id,
            NOT_EVALUABLE,
            tuple(sorted(reasons)),
            tuple(binding.sha256() for binding in bindings),
            tuple(measurement_digests),
            None,
            None,
        )

    inner = evaluate_agentic_core(tuple(evidence), policy=policy, report_id=f"{report_id}:inner")
    return RepositoryBoundAgenticCoreReport(
        OUTER_REPORT_SCHEMA,
        report_id,
        inner.verdict,
        inner.reasons,
        tuple(binding.sha256() for binding in bindings),
        tuple(measurement_digests),
        inner.sha256(),
        inner,
    )
