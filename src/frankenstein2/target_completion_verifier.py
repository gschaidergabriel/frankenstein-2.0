"""Independent target-completion / negative-space verifier for Frankenstein 2.0.

F2-WP-1206 generation 1.

This module evaluates a caller-supplied TargetObligation set against independently
supplied target observations. It is intentionally not an installer, target probe,
model judge, or physical-host attester.

Hard boundaries:

* missing mandatory evidence is UNKNOWN, never PASS;
* installer/builder/model self-report cannot satisfy independent readback;
* absent/stale/wrong-owner/wrong-user/wrong-session/unproven negative-space
  findings are first-class;
* counterevidence probes must be present and clear;
* evidence below an obligation's minimum fidelity is UNKNOWN;
* T0-T3 evidence never becomes T4 physical credit;
* this component never mints whole-product or physical-host acceptance.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

REPORT_SCHEMA = "FRANKENSTEIN2_TARGET_COMPLETION_REPORT/v1"
VERIFIER_SCOPE = "INDEPENDENT_NEGATIVE_SPACE_COMPONENT_ONLY"

FIDELITY_ORDER = (
    "T0_CONTRACT",
    "T1_UBUNTU_USERSPACE",
    "T2_DEVICE_SESSION_FAULT_TWIN",
    "T3_TARGET_TRACE_REPLAY",
    "T4_PHYSICAL",
)
_FIDELITY_RANK = {name: index for index, name in enumerate(FIDELITY_ORDER)}

NEGATIVE_SPACE_CATEGORIES = (
    "absent",
    "stale",
    "wrong_owner",
    "wrong_user",
    "wrong_session",
    "unproven",
)
NEGATIVE_SPACE_STATES = {"CLEAR", "DETECTED", "UNKNOWN"}
READBACK_STATES = {"PASS", "FAIL", "UNKNOWN"}
COUNTEREVIDENCE_STATES = {"CLEAR", "COUNTEREVIDENCE", "UNKNOWN"}

_FORBIDDEN_SELF_REPORT_SOURCES = {
    "INSTALLER_SELF_REPORT",
    "BUILDER_SELF_REPORT",
    "MODEL_SELF_REPORT",
    "EXECUTOR_SELF_REPORT",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TargetCompletionVerificationError(ValueError):
    """Fail-closed input/contract error for the independent verifier."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TargetCompletionVerificationError(f"{name} must be an object")
    return value


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TargetCompletionVerificationError(f"{name} must be a non-empty trimmed string")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TargetCompletionVerificationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _fidelity(name: str, value: Any) -> str:
    if value not in _FIDELITY_RANK:
        raise TargetCompletionVerificationError(
            f"{name} must be one of {', '.join(FIDELITY_ORDER)}"
        )
    return str(value)


def _bool(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise TargetCompletionVerificationError(f"{name} must be boolean")
    return value


def _evidence_refs(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TargetCompletionVerificationError(f"{name} must be an array of strings")
    refs: list[str] = []
    for index, item in enumerate(value):
        refs.append(_identifier(f"{name}[{index}]", item))
    if len(set(refs)) != len(refs):
        raise TargetCompletionVerificationError(f"{name} contains duplicate evidence refs")
    return tuple(refs)


def _expected_counter_probe_keys(obligation: Mapping[str, Any]) -> tuple[str, ...]:
    probes = obligation.get("counterevidence_probes")
    if not isinstance(probes, Sequence) or isinstance(probes, (str, bytes, bytearray)):
        raise TargetCompletionVerificationError("counterevidence_probes must be an array")
    if not probes:
        raise TargetCompletionVerificationError(
            "each mandatory obligation requires at least one counterevidence probe"
        )
    keys: list[str] = []
    for index, raw_probe in enumerate(probes):
        probe = _mapping(f"counterevidence_probes[{index}]", raw_probe)
        explicit = probe.get("probe_id", probe.get("id"))
        if explicit is None:
            key = f"counterevidence[{index}]"
        else:
            key = _identifier(f"counterevidence_probes[{index}].probe_id", explicit)
        if key in keys:
            raise TargetCompletionVerificationError(
                f"duplicate counterevidence probe key: {key}"
            )
        keys.append(key)
    return tuple(keys)


def _counterevidence_results(
    value: Any, expected_keys: tuple[str, ...]
) -> tuple[dict[str, str], list[str]]:
    results: dict[str, str] = {}
    missing: list[str] = []

    if isinstance(value, Mapping):
        for key in expected_keys:
            raw = value.get(key)
            if raw is None:
                missing.append(key)
                continue
            if raw not in COUNTEREVIDENCE_STATES:
                raise TargetCompletionVerificationError(
                    f"counterevidence[{key}] has invalid state {raw!r}"
                )
            results[key] = str(raw)
        return results, missing

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > len(expected_keys):
            raise TargetCompletionVerificationError(
                "counterevidence result array has more entries than required probes"
            )
        for index, key in enumerate(expected_keys):
            if index >= len(value):
                missing.append(key)
                continue
            raw = value[index]
            if raw not in COUNTEREVIDENCE_STATES:
                raise TargetCompletionVerificationError(
                    f"counterevidence[{index}] has invalid state {raw!r}"
                )
            results[key] = str(raw)
        return results, missing

    raise TargetCompletionVerificationError(
        "counterevidence must be an object keyed by probe id or an ordered array"
    )


def _negative_space(value: Any) -> tuple[dict[str, str], list[str]]:
    raw = _mapping("negative_space", value)
    normalized: dict[str, str] = {}
    missing: list[str] = []
    for category in NEGATIVE_SPACE_CATEGORIES:
        state = raw.get(category)
        if state is None:
            missing.append(category)
            continue
        if state not in NEGATIVE_SPACE_STATES:
            raise TargetCompletionVerificationError(
                f"negative_space.{category} has invalid state {state!r}"
            )
        normalized[category] = str(state)
    return normalized, missing


def _normalize_obligations(
    obligations: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...]]:
    if not isinstance(obligations, Sequence) or isinstance(
        obligations, (str, bytes, bytearray)
    ):
        raise TargetCompletionVerificationError("obligations must be an array")
    if not obligations:
        raise TargetCompletionVerificationError("obligations must not be empty")

    by_id: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    for index, raw in enumerate(obligations):
        obligation = _mapping(f"obligations[{index}]", raw)
        obligation_id = _identifier(
            f"obligations[{index}].obligation_id", obligation.get("obligation_id")
        )
        if obligation_id in by_id:
            raise TargetCompletionVerificationError(
                f"duplicate obligation_id: {obligation_id}"
            )
        _sha256(
            f"obligations[{index}].target_profile_digest",
            obligation.get("target_profile_digest"),
        )
        _fidelity(
            f"obligations[{index}].minimum_fidelity", obligation.get("minimum_fidelity")
        )
        _bool(
            f"obligations[{index}].physical_required", obligation.get("physical_required")
        )
        _expected_counter_probe_keys(obligation)
        by_id[obligation_id] = obligation
        order.append(obligation_id)
    return by_id, tuple(order)


def _normalize_observations(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(observations, Sequence) or isinstance(
        observations, (str, bytes, bytearray)
    ):
        raise TargetCompletionVerificationError("observations must be an array")
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(observations):
        observation = _mapping(f"observations[{index}]", raw)
        obligation_id = _identifier(
            f"observations[{index}].obligation_id", observation.get("obligation_id")
        )
        if obligation_id in by_id:
            raise TargetCompletionVerificationError(
                f"duplicate observation for obligation_id: {obligation_id}"
            )
        by_id[obligation_id] = observation
    return by_id


def _evaluate_one(
    obligation: Mapping[str, Any], observation: Mapping[str, Any] | None
) -> dict[str, Any]:
    obligation_id = str(obligation["obligation_id"])
    minimum_fidelity = _fidelity("minimum_fidelity", obligation["minimum_fidelity"])
    physical_required = _bool("physical_required", obligation["physical_required"])
    expected_profile = _sha256("target_profile_digest", obligation["target_profile_digest"])
    expected_counter_keys = _expected_counter_probe_keys(obligation)

    reasons: list[str] = []
    evidence_refs: tuple[str, ...] = ()
    observation_fidelity: str | None = None
    physical_only_pending = False

    if observation is None:
        return {
            "obligation_id": obligation_id,
            "status": "UNKNOWN",
            "reasons": ["MISSING_OBSERVATION"],
            "evidence_refs": [],
            "physical_only_pending": physical_required,
        }

    source_class = _identifier("source_class", observation.get("source_class"))
    observed_profile = _sha256(
        "observation.target_profile_digest", observation.get("target_profile_digest")
    )
    observation_fidelity = _fidelity("observation.fidelity", observation.get("fidelity"))
    positive_readback = observation.get("positive_readback")
    if positive_readback not in READBACK_STATES:
        raise TargetCompletionVerificationError(
            f"positive_readback must be one of {sorted(READBACK_STATES)}"
        )
    evidence_refs = _evidence_refs("observation.evidence_refs", observation.get("evidence_refs", []))
    negative_space, missing_negative = _negative_space(observation.get("negative_space", {}))
    counter_results, missing_counter = _counterevidence_results(
        observation.get("counterevidence", {}), expected_counter_keys
    )

    fail_reasons: list[str] = []
    unknown_reasons: list[str] = []

    if source_class in _FORBIDDEN_SELF_REPORT_SOURCES:
        unknown_reasons.append("NON_INDEPENDENT_SELF_REPORT_SOURCE")
    if observed_profile != expected_profile:
        unknown_reasons.append("TARGET_PROFILE_DIGEST_MISMATCH")
    if _FIDELITY_RANK[observation_fidelity] < _FIDELITY_RANK[minimum_fidelity]:
        unknown_reasons.append("BELOW_MINIMUM_FIDELITY")
    if physical_required and observation_fidelity != "T4_PHYSICAL":
        unknown_reasons.append("PHYSICAL_EVIDENCE_REQUIRED")
        physical_only_pending = True

    if positive_readback == "FAIL":
        fail_reasons.append("POSITIVE_READBACK_FAILED")
    elif positive_readback == "UNKNOWN":
        unknown_reasons.append("POSITIVE_READBACK_UNKNOWN")

    for category in NEGATIVE_SPACE_CATEGORIES:
        if category in missing_negative:
            unknown_reasons.append(f"NEGATIVE_SPACE_{category.upper()}_MISSING")
            continue
        state = negative_space[category]
        if state == "DETECTED":
            fail_reasons.append(f"NEGATIVE_SPACE_{category.upper()}_DETECTED")
        elif state == "UNKNOWN":
            unknown_reasons.append(f"NEGATIVE_SPACE_{category.upper()}_UNKNOWN")

    for probe_key in expected_counter_keys:
        if probe_key in missing_counter:
            unknown_reasons.append(f"COUNTEREVIDENCE_PROBE_MISSING:{probe_key}")
            continue
        outcome = counter_results[probe_key]
        if outcome == "COUNTEREVIDENCE":
            fail_reasons.append(f"COUNTEREVIDENCE_DETECTED:{probe_key}")
        elif outcome == "UNKNOWN":
            unknown_reasons.append(f"COUNTEREVIDENCE_UNKNOWN:{probe_key}")

    if not evidence_refs:
        unknown_reasons.append("NO_EVIDENCE_REFS")

    if fail_reasons:
        status = "FAIL"
        reasons.extend(sorted(set(fail_reasons)))
        reasons.extend(sorted(set(unknown_reasons)))
    elif unknown_reasons:
        status = "UNKNOWN"
        reasons.extend(sorted(set(unknown_reasons)))
    else:
        status = "PASS"
        reasons.append("INDEPENDENT_READBACK_AND_NEGATIVE_SPACE_CLEAR_AT_DECLARED_SCOPE")

    return {
        "obligation_id": obligation_id,
        "status": status,
        "reasons": reasons,
        "evidence_refs": list(evidence_refs),
        "observed_fidelity": observation_fidelity,
        "physical_only_pending": physical_only_pending,
    }


def verify_target_obligations(
    obligations: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a deterministic fail-closed TargetCompletionReport.

    Every supplied obligation is treated as mandatory. Unknown observation ids are
    preserved as negative-space evidence rather than silently ignored.
    """

    obligation_map, order = _normalize_obligations(obligations)
    observation_map = _normalize_observations(observations)

    unexpected_observation_ids = sorted(set(observation_map) - set(obligation_map))
    results = [_evaluate_one(obligation_map[oid], observation_map.get(oid)) for oid in order]

    failed = [item["obligation_id"] for item in results if item["status"] == "FAIL"]
    unknown = [item["obligation_id"] for item in results if item["status"] == "UNKNOWN"]
    passed = [item["obligation_id"] for item in results if item["status"] == "PASS"]
    physical_only = [
        item["obligation_id"]
        for item in results
        if item["status"] == "UNKNOWN"
        and item.get("physical_only_pending")
        and set(item["reasons"]) == {"PHYSICAL_EVIDENCE_REQUIRED"}
    ]

    if failed:
        top_status = "DEGRADED"
    elif unexpected_observation_ids:
        # An observation without a declared obligation is negative-space drift: the
        # verifier cannot know whether the obligation set omitted a target requirement.
        top_status = "UNKNOWN"
    elif unknown and len(physical_only) == len(unknown):
        top_status = "READY_FOR_PHYSICAL_ACCEPTANCE"
    elif unknown:
        top_status = "UNKNOWN"
    else:
        top_status = "COMPLETE_AT_TWIN_SCOPE"

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "verifier_scope": VERIFIER_SCOPE,
        "status": top_status,
        "obligation_count": len(results),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "unknown_count": len(unknown),
        "passed_obligation_ids": passed,
        "failed_obligation_ids": failed,
        "unknown_obligation_ids": unknown,
        "physical_only_pending_obligation_ids": physical_only,
        "unexpected_observation_ids": unexpected_observation_ids,
        "obligations": results,
        "whole_product_credit": False,
        "physical_host_credit": False,
        "physical_acceptance_minting": "FORBIDDEN_IN_THIS_COMPONENT",
    }
    report["report_digest"] = _digest(report)
    return report


__all__ = [
    "COUNTEREVIDENCE_STATES",
    "FIDELITY_ORDER",
    "NEGATIVE_SPACE_CATEGORIES",
    "NEGATIVE_SPACE_STATES",
    "READBACK_STATES",
    "REPORT_SCHEMA",
    "TargetCompletionVerificationError",
    "VERIFIER_SCOPE",
    "verify_target_obligations",
]
