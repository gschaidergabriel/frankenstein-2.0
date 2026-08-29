from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")

CANONICAL_FIELDS = (
    "schema",
    "classification",
    "binding_id",
    "canonical_reentry_key",
    "reentry_witness_sha256",
    "uptake_receipt_id",
    "uptake_receipt_sha256",
    "broadcast_id",
    "broadcast_generation",
    "broadcast_sha256",
    "recipient_cell_id",
    "delivery_status",
    "uptake_status",
    "downstream_ref",
    "downstream_sha256",
    "binding_status",
    "causal_influence_claim",
    "truth_authority",
    "effect_authority",
)

SENSITIVE_KEYS = {
    "prompt",
    "output",
    "tool_definition",
    "api_key",
    "secret",
    "freeform_metadata",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")
    return value


def _require_sha(name: str, value: Any) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def validate_source(source: dict[str, Any]) -> None:
    for field in ("binding_id", "uptake_receipt_id", "broadcast_id", "recipient_cell_id", "delivery_status", "uptake_status", "binding_status"):
        _require_text(field, source.get(field))
    for field in ("canonical_reentry_key", "reentry_witness_sha256", "uptake_receipt_sha256", "broadcast_sha256"):
        _require_sha(field, source.get(field))
    if source.get("downstream_sha256") is not None:
        _require_sha("downstream_sha256", source.get("downstream_sha256"))
    if type(source.get("broadcast_generation")) is not int or source["broadcast_generation"] < 0:
        raise ValueError("broadcast_generation must be non-negative int")
    if source.get("causal_influence_claim") != "NOT_ESTABLISHED_BY_BINDING":
        raise ValueError("projection requires explicit non-causality classification")
    if source.get("truth_authority") != "NONE" or source.get("effect_authority") != "NONE":
        raise ValueError("projection cannot export a source that claims observer truth/effect authority")


def project_to_openinference(
    source: dict[str, Any],
    *,
    observer_enabled: bool,
    target_trace_id: str | None,
    target_span_id: str | None,
) -> dict[str, Any] | None:
    """One-way, non-authoritative metadata projection.

    No reverse adapter exists. The function never mutates `source` and never exports
    prompt/output/tool definitions/secrets/free-form metadata.
    """
    validate_source(source)
    if not observer_enabled:
        return None
    if not isinstance(target_trace_id, str) or TRACE_ID_RE.fullmatch(target_trace_id) is None:
        raise ValueError("target_trace_id must be 32 lowercase hex")
    if not isinstance(target_span_id, str) or SPAN_ID_RE.fullmatch(target_span_id) is None:
        raise ValueError("target_span_id must be 16 lowercase hex")

    attrs = {
        "openinference.span.kind": "EVALUATOR",
        "evaluations.0.evaluation.name": "f2.gwt_reentry_uptake_binding",
        "evaluations.0.evaluation.label": "bound_evidence_only",
        "evaluations.0.evaluation.annotator_kind": "CODE",
        "evaluations.0.evaluation.identifier": "f2-trigger6-openinference-projection-v0",
    }
    for key in CANONICAL_FIELDS:
        value = source.get(key)
        if value is not None:
            attrs[f"f2.{key}"] = value

    return {
        "name": "f2 gwt reentry/uptake evidence projection",
        "links": [{"trace_id": target_trace_id, "span_id": target_span_id}],
        "attributes": attrs,
        "observer_semantics": "CORRELATION_ONLY_NOT_CAUSAL_OR_TRUTH_AUTHORITY",
        "source_digest": sha256_json({key: source.get(key) for key in CANONICAL_FIELDS}),
    }


def run() -> dict[str, Any]:
    source = {
        "schema": "FRANKENSTEIN2_GWT_REENTRY_UPTAKE_BINDING/v1",
        "classification": "DERIVED_BINDING_WP507_UPTAKE_AUTHORITY_ONLY_NOT_NEW_UPTAKE_OR_RUNTIME_EVIDENCE",
        "binding_id": "binding-001",
        "canonical_reentry_key": "1" * 64,
        "reentry_witness_sha256": "2" * 64,
        "uptake_receipt_id": "uptake-001",
        "uptake_receipt_sha256": "3" * 64,
        "broadcast_id": "broadcast-001",
        "broadcast_generation": 4,
        "broadcast_sha256": "4" * 64,
        "recipient_cell_id": "G7",
        "delivery_status": "DELIVERED",
        "uptake_status": "UPTAKEN",
        "downstream_ref": "receipt://downstream/001",
        "downstream_sha256": "5" * 64,
        "binding_status": "WP507_UPTAKEN_BOUND",
        "causal_influence_claim": "NOT_ESTABLISHED_BY_BINDING",
        "truth_authority": "NONE",
        "effect_authority": "NONE",
        "prompt": "TOP-SECRET PROMPT 9c8e9a",
        "output": "TOP-SECRET OUTPUT c4fb7d",
        "tool_definition": "dangerous-tool-schema-ff1190",
        "api_key": "sk-test-never-export-01",
        "secret": "secret-never-export-02",
        "freeform_metadata": {"private": "never-export-03"},
    }
    before = copy.deepcopy(source)
    t1, s1 = "a" * 32, "b" * 16
    t2, s2 = "c" * 32, "d" * 16

    p1 = project_to_openinference(source, observer_enabled=True, target_trace_id=t1, target_span_id=s1)
    p1_repeat = project_to_openinference(source, observer_enabled=True, target_trace_id=t1, target_span_id=s1)
    p2 = project_to_openinference(source, observer_enabled=True, target_trace_id=t2, target_span_id=s2)
    assert p1 is not None and p2 is not None

    tests: list[dict[str, Any]] = []
    def record(name: str, passed: bool, detail: str) -> None:
        tests.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            raise AssertionError(f"{name}: {detail}")

    record("source_not_mutated", source == before, "projector must be observational only")
    record("deterministic_same_inputs", stable_json(p1) == stable_json(p1_repeat), "same source+observer IDs must serialize identically")
    record("exactly_one_posthoc_link", len(p1["links"]) == 1, "OpenInference post-hoc carrier requires one target link")

    for key in CANONICAL_FIELDS:
        if source.get(key) is not None:
            record(f"canonical_field_preserved:{key}", p1["attributes"].get(f"f2.{key}") == source[key], "canonical F2 field must be copied verbatim")

    canon_attrs1 = {k: v for k, v in p1["attributes"].items() if k.startswith("f2.")}
    canon_attrs2 = {k: v for k, v in p2["attributes"].items() if k.startswith("f2.")}
    record("observer_ids_not_authoritative", canon_attrs1 == canon_attrs2, "changing trace/span link IDs must not change canonical F2 attributes")
    record("observer_links_can_change", p1["links"] != p2["links"], "observer correlation IDs remain observer-local")

    serialized = stable_json(p1)
    leaked_tokens = [str(source[k]) for k in SENSITIVE_KEYS if k in source and str(source[k]) in serialized]
    record("privacy_allowlist_no_sensitive_values", not leaked_tokens, f"leaked={leaked_tokens}")
    leaked_keys = [k for k in SENSITIVE_KEYS if k in serialized]
    record("privacy_allowlist_no_sensitive_keys", not leaked_keys, f"leaked_keys={leaked_keys}")

    disabled = project_to_openinference(source, observer_enabled=False, target_trace_id=None, target_span_id=None)
    record("observer_disabled_emits_nothing", disabled is None, "absence of telemetry is not converted into a negative F2 fact")
    record("observer_disabled_source_unchanged", source == before, "disabled observer cannot alter canonical source")

    bad = copy.deepcopy(source)
    bad["broadcast_sha256"] = "BAD"
    try:
        project_to_openinference(bad, observer_enabled=True, target_trace_id=t1, target_span_id=s1)
        malformed_rejected = False
    except ValueError:
        malformed_rejected = True
    record("malformed_canonical_digest_fails_closed", malformed_rejected, "projection must not launder malformed canonical identity")

    bad_authority = copy.deepcopy(source)
    bad_authority["truth_authority"] = "OBSERVER"
    try:
        project_to_openinference(bad_authority, observer_enabled=True, target_trace_id=t1, target_span_id=s1)
        authority_rejected = False
    except ValueError:
        authority_rejected = True
    record("observer_truth_authority_fails_closed", authority_rejected, "projection must reject source shape that grants observer truth authority")

    native_min = {key: source.get(key) for key in CANONICAL_FIELDS if source.get(key) is not None}
    native_bytes = len(stable_json(native_min).encode("utf-8"))
    projection_bytes = len(stable_json(p1).encode("utf-8"))
    overhead_bytes = projection_bytes - native_bytes
    overhead_ratio = projection_bytes / native_bytes

    return {
        "schema": "FRANKENSTEIN2_TRIGGER6_OPENINFERENCE_E3_RESULT/v1",
        "research_id": "R6-SEED-011",
        "claim_target": "E3_CLAIM_REPRODUCED_OPENINFERENCE_PROJECTION_IDENTITY_PRIVACY",
        "experiment_scope": "LOCAL_DETERMINISTIC_JSON_FIXTURE_NOT_OTLP_WIRE_BENCHMARK_NOT_F2_RUNTIME",
        "tests_total": len(tests),
        "tests_passed": sum(1 for t in tests if t["passed"]),
        "tests": tests,
        "measurement": {
            "native_min_json_bytes": native_bytes,
            "projection_json_bytes": projection_bytes,
            "projection_overhead_bytes": overhead_bytes,
            "projection_overhead_ratio": round(overhead_ratio, 6),
            "note": "JSON attribute-carrier size only; not OTLP protobuf/network/collector overhead."
        },
        "result": "E3_REPRODUCED_AT_LOCAL_FIXTURE_SCOPE" if all(t["passed"] for t in tests) else "E3_FALSIFIED",
        "architecture_credit": 0,
        "runtime_credit": 0,
        "gwt_causal_credit": 0,
        "effect_credit": 0,
        "whole_system_credit": 0,
    }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, indent=2))
