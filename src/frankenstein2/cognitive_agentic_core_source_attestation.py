"""F2-WP-807 exact source-acceptance attestation for the four capability families.

This module closes one specific provenance gap in the active WP807 lane: caller supplied
workpackage/receipt identifiers are not sufficient evidence that a capability measurement
came from the accepted WP802-WP805 benchmark implementations.

The current accepted source reconciliations and acceptance receipts are frozen by exact Git
blob identity. ``attest_source_acceptance`` recomputes those Git blob identities from the
supplied bytes, parses the documents, cross-checks terminal workpackage/generation/claim/
scope/authority and merged-main CI success, then returns an origin-sealed attestation.

This is deliberately NOT a capability-measurement producer. It does not create a shared
fixture-family digest, scores, samples, successes, actions, an ARC score, runtime evidence,
or whole-system credit. Those remain separate gates.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ATTESTATION_SCHEMA = "FRANKENSTEIN2_AGENTIC_CORE_SOURCE_ACCEPTANCE_ATTESTATION/v1"
RECONCILIATION_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1"
ACCEPTANCE_RECEIPT_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_ACCEPTANCE_RECEIPT/v1"
ATTESTATION_CLASSIFICATION = "EXACT_REPOSITORY_SOURCE_ACCEPTANCE_ONLY_NO_CAPABILITY_MEASUREMENT"
AUTHORITY_EPOCH = "8.78"

EXPLORATION = "EXPLORATION"
MODELING = "MODELING"
GOAL_SETTING = "GOAL_SETTING"
PLANNING_EXECUTION = "PLANNING_EXECUTION"
REQUIRED_CAPABILITIES = (EXPLORATION, MODELING, GOAL_SETTING, PLANNING_EXECUTION)

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_ORIGIN = object()


class SourceAcceptanceAttestationError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SourceAcceptanceAttestationError(f"{name} must be a non-empty trimmed string")
    if len(value) > 1024 or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise SourceAcceptanceAttestationError(f"{name} is outside the identifier domain")
    return value


def _git_blob_sha1(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise SourceAcceptanceAttestationError("source document must be exact bytes")
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _sha256(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise SourceAcceptanceAttestationError("source document must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _object_from_bytes(name: str, raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise SourceAcceptanceAttestationError(f"{name} must be exact bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceAcceptanceAttestationError(f"{name} must be valid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise SourceAcceptanceAttestationError(f"{name} must decode to a JSON object")
    return value


def _assert_zero_credit_boundary(document: dict[str, Any], *, name: str) -> None:
    zero_fields = (
        "runtime_credit",
        "target_vps_runtime_credit",
        "physical_grid10_credit",
        "gwt_runtime_credit",
        "jspace_runtime_credit",
        "gwt_jspace_credit",
        "provider_model_credit",
        "training_credit",
        "goal_authority_credit",
        "effect_credit",
        "completion_credit",
        "recovery_efficiency_result_credit",
    )
    for field in zero_fields:
        if field in document and document[field] != 0:
            raise SourceAcceptanceAttestationError(f"{name}.{field} must remain zero")
    if "whole_system_acceptance" in document and document["whole_system_acceptance"] is not False:
        raise SourceAcceptanceAttestationError(f"{name}.whole_system_acceptance must remain false")


def _receipt_has_successful_merged_main_ci(receipt: dict[str, Any]) -> bool:
    hosted = receipt.get("repository_hosted_ci")
    if type(hosted) is dict and hosted.get("merged_main_conclusion") == "success":
        return True
    merged = receipt.get("merged_main_ci")
    if type(merged) is dict and merged.get("conclusion") == "success":
        return True
    return False


@dataclass(frozen=True, slots=True)
class FrozenSourceBinding:
    capability: str
    workpackage_id: str
    generation: int
    claim_id: str
    terminal_scope: str
    reconciliation_ref: str
    reconciliation_git_blob_sha1: str
    receipt_ref: str
    receipt_git_blob_sha1: str

    def __post_init__(self) -> None:
        if self.capability not in REQUIRED_CAPABILITIES:
            raise SourceAcceptanceAttestationError("frozen binding capability is not admitted")
        for name, value in (
            ("workpackage_id", self.workpackage_id),
            ("claim_id", self.claim_id),
            ("terminal_scope", self.terminal_scope),
            ("reconciliation_ref", self.reconciliation_ref),
            ("receipt_ref", self.receipt_ref),
        ):
            _id(name, value)
        if type(self.generation) is not int or self.generation < 1:
            raise SourceAcceptanceAttestationError("generation must be a positive integer")
        if _SHA1_RE.fullmatch(self.reconciliation_git_blob_sha1) is None:
            raise SourceAcceptanceAttestationError("reconciliation Git blob SHA must be lowercase 40-hex")
        if _SHA1_RE.fullmatch(self.receipt_git_blob_sha1) is None:
            raise SourceAcceptanceAttestationError("receipt Git blob SHA must be lowercase 40-hex")


SOURCE_BINDINGS: dict[str, FrozenSourceBinding] = {
    EXPLORATION: FrozenSourceBinding(
        EXPLORATION,
        "F2-WP-802",
        1,
        "F2-WP-802-G1-GPT56SOL-HELDOUT-INFORMATION-SEEKING-BENCHMARK-20260829",
        "HELDOUT_INFORMATION_SEEKING_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "workpackages/reconciliations/F2-WP-802/1-F2-WP-802-G1-GPT56SOL-HELDOUT-INFORMATION-SEEKING-BENCHMARK-20260829.json",
        "818ea714c46e27d75c464d13efc99085f38717ab",
        "workpackages/receipts/F2-WP-802_G1_INFORMATION_SEEKING_MAIN_CI_33254306747.json",
        "068bd58037bc25340f2e5ce1141b12354b46f5c8",
    ),
    MODELING: FrozenSourceBinding(
        MODELING,
        "F2-WP-803",
        2,
        "F2-WP-803-G2-GPT56SOL-RUN-DESCRIPTOR-BINDING-20260829",
        "RUN_DESCRIPTOR_BOUND_WORLD_MODEL_PREDICTION_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "workpackages/reconciliations/F2-WP-803/2-F2-WP-803-G2-GPT56SOL-RUN-DESCRIPTOR-BINDING-20260829.json",
        "bcdd5e72010563531b98cfb1efb8dbd77afe0548",
        "workpackages/receipts/F2-WP-803_G2_RUN_DESCRIPTOR_BINDING_MAIN_CI_33254865193.json",
        "342e75443ae015384515ca4bd9f7617671cfed94",
    ),
    GOAL_SETTING: FrozenSourceBinding(
        GOAL_SETTING,
        "F2-WP-804",
        3,
        "F2-WP-804-G3-GPT56SOL-PUBLIC-SIGNAL-DIGEST-BINDING-20260829",
        "PUBLIC_SIGNAL_REF_PLUS_PAYLOAD_DIGEST_BINDING_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "workpackages/reconciliations/F2-WP-804/3-F2-WP-804-G3-GPT56SOL-PUBLIC-SIGNAL-DIGEST-BINDING-20260829.json",
        "54f55faf6324245fd78ac0495bcbd4b03bce084e",
        "workpackages/receipts/F2-WP-804_G3_PUBLIC_SIGNAL_DIGEST_BINDING_MAIN_CI_33255901056.json",
        "e26b1e9dcf20addc84c847fe4bad2b2d085bd24e",
    ),
    PLANNING_EXECUTION: FrozenSourceBinding(
        PLANNING_EXECUTION,
        "F2-WP-805",
        2,
        "F2-WP-805-G2-GPT56SOL-E2-RECOVERY-FALSIFIER-REPAIR-20260829",
        "RECOVERY_E2_FALSIFIER_REPAIR_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        "workpackages/reconciliations/F2-WP-805/2-F2-WP-805-G2-GPT56SOL-E2-RECOVERY-FALSIFIER-REPAIR-20260829.json",
        "142841b73a0f76c5e31b943aca71e23d4bc6a4a3",
        "workpackages/receipts/F2-WP-805_G2_RECOVERY_E2_REPAIR_MAIN_CI_33255617547.json",
        "ae6d87f0bc966ecd77d289433d30a7c348d44a88",
    ),
}


@dataclass(frozen=True, slots=True)
class SourceAcceptanceAttestation:
    schema: str
    capability: str
    workpackage_id: str
    generation: int
    claim_id: str
    authority_epoch: str
    terminal_scope: str
    reconciliation_ref: str
    reconciliation_git_blob_sha1: str
    reconciliation_content_sha256: str
    receipt_ref: str
    receipt_git_blob_sha1: str
    receipt_content_sha256: str
    classification: str = ATTESTATION_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if _origin is not _ATTESTATION_ORIGIN:
            raise SourceAcceptanceAttestationError("SourceAcceptanceAttestation must be created by attestation API")
        if self.schema != ATTESTATION_SCHEMA or self.classification != ATTESTATION_CLASSIFICATION:
            raise SourceAcceptanceAttestationError("attestation schema/classification mismatch")
        if self.capability not in REQUIRED_CAPABILITIES:
            raise SourceAcceptanceAttestationError("attestation capability is not admitted")
        binding = SOURCE_BINDINGS[self.capability]
        expected = (
            binding.workpackage_id,
            binding.generation,
            binding.claim_id,
            AUTHORITY_EPOCH,
            binding.terminal_scope,
            binding.reconciliation_ref,
            binding.reconciliation_git_blob_sha1,
            binding.receipt_ref,
            binding.receipt_git_blob_sha1,
        )
        actual = (
            self.workpackage_id,
            self.generation,
            self.claim_id,
            self.authority_epoch,
            self.terminal_scope,
            self.reconciliation_ref,
            self.reconciliation_git_blob_sha1,
            self.receipt_ref,
            self.receipt_git_blob_sha1,
        )
        if actual != expected:
            raise SourceAcceptanceAttestationError("attestation does not match frozen source binding")
        for name, value in (
            ("reconciliation_content_sha256", self.reconciliation_content_sha256),
            ("receipt_content_sha256", self.receipt_content_sha256),
        ):
            if _SHA256_RE.fullmatch(value) is None:
                raise SourceAcceptanceAttestationError(f"{name} must be lowercase 64-hex SHA-256")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _canonical_sha256(self.as_dict())


def attest_source_acceptance(
    capability: str,
    *,
    reconciliation_bytes: bytes,
    receipt_bytes: bytes,
) -> SourceAcceptanceAttestation:
    """Attest exact current accepted source documents for one WP807 capability family.

    Git blob identity is checked before semantic parsing. A semantically equivalent copy,
    relabelled document, stale generation, or caller-authored substitute therefore fails
    closed instead of becoming source acceptance evidence.
    """
    if capability not in SOURCE_BINDINGS:
        raise SourceAcceptanceAttestationError("capability has no frozen source binding")
    binding = SOURCE_BINDINGS[capability]

    reconciliation_git_sha = _git_blob_sha1(reconciliation_bytes)
    receipt_git_sha = _git_blob_sha1(receipt_bytes)
    if reconciliation_git_sha != binding.reconciliation_git_blob_sha1:
        raise SourceAcceptanceAttestationError("reconciliation bytes do not match frozen Git blob identity")
    if receipt_git_sha != binding.receipt_git_blob_sha1:
        raise SourceAcceptanceAttestationError("receipt bytes do not match frozen Git blob identity")

    reconciliation = _object_from_bytes("reconciliation", reconciliation_bytes)
    receipt = _object_from_bytes("receipt", receipt_bytes)
    if reconciliation.get("schema") != RECONCILIATION_SCHEMA:
        raise SourceAcceptanceAttestationError("reconciliation schema mismatch")
    if receipt.get("schema") != ACCEPTANCE_RECEIPT_SCHEMA:
        raise SourceAcceptanceAttestationError("acceptance receipt schema mismatch")

    expected_identity = (binding.workpackage_id, binding.generation, binding.claim_id)
    reconciliation_identity = (
        reconciliation.get("workpackage_id"),
        reconciliation.get("generation"),
        reconciliation.get("claim_id"),
    )
    receipt_identity = (
        receipt.get("workpackage_id"),
        receipt.get("generation"),
        receipt.get("claim_id"),
    )
    if reconciliation_identity != expected_identity or receipt_identity != expected_identity:
        raise SourceAcceptanceAttestationError("source document workpackage/generation/claim identity mismatch")
    if reconciliation.get("authority_epoch") != AUTHORITY_EPOCH or receipt.get("authority_epoch") != AUTHORITY_EPOCH:
        raise SourceAcceptanceAttestationError("source document authority epoch mismatch")
    if reconciliation.get("terminal_state") != "ACCEPTED":
        raise SourceAcceptanceAttestationError("reconciliation is not terminal ACCEPTED")
    if reconciliation.get("terminal_scope") != binding.terminal_scope:
        raise SourceAcceptanceAttestationError("reconciliation terminal scope mismatch")
    if receipt.get("acceptance_scope") != binding.terminal_scope:
        raise SourceAcceptanceAttestationError("receipt acceptance scope mismatch")
    if reconciliation.get("acceptance_receipt") != binding.receipt_ref:
        raise SourceAcceptanceAttestationError("reconciliation does not point to frozen acceptance receipt")
    if not _receipt_has_successful_merged_main_ci(receipt):
        raise SourceAcceptanceAttestationError("acceptance receipt lacks successful merged-main CI")
    _assert_zero_credit_boundary(reconciliation, name="reconciliation")
    _assert_zero_credit_boundary(receipt, name="receipt")

    return SourceAcceptanceAttestation(
        ATTESTATION_SCHEMA,
        capability,
        binding.workpackage_id,
        binding.generation,
        binding.claim_id,
        AUTHORITY_EPOCH,
        binding.terminal_scope,
        binding.reconciliation_ref,
        reconciliation_git_sha,
        _sha256(reconciliation_bytes),
        binding.receipt_ref,
        receipt_git_sha,
        _sha256(receipt_bytes),
        _origin=_ATTESTATION_ORIGIN,
    )


def attest_source_acceptance_files(repository_root: Path, capability: str) -> SourceAcceptanceAttestation:
    """Read the two frozen repository paths and delegate to the byte-exact attester."""
    if type(repository_root) is not Path:
        raise SourceAcceptanceAttestationError("repository_root must be exact pathlib.Path")
    if capability not in SOURCE_BINDINGS:
        raise SourceAcceptanceAttestationError("capability has no frozen source binding")
    binding = SOURCE_BINDINGS[capability]
    reconciliation_bytes = (repository_root / binding.reconciliation_ref).read_bytes()
    receipt_bytes = (repository_root / binding.receipt_ref).read_bytes()
    return attest_source_acceptance(
        capability,
        reconciliation_bytes=reconciliation_bytes,
        receipt_bytes=receipt_bytes,
    )
