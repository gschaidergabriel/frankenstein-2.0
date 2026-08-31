#!/usr/bin/env python3
"""Execute the F2-WP-719 FRESH1-FRESH10 successor-composition matrix.

This is a bounded repository/VPS-sandbox discriminator.  It intentionally uses
no provider, network, audio device, GWT runtime, memory write, tool/effect path,
or whole-product authority.  F15/F16/F17 remain upstream prerequisite evidence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
TEST_PATH = ROOT / "tests" / "test_fresh_turn_successor.py"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CASES = (
    ("FRESH1", "test_fresh1_valid_exact_gwt_memory_reentry_creates_distinct_bounded_successor"),
    ("FRESH2", "test_fresh2_stale_or_foreign_gwt_lineage_fails_closed"),
    ("FRESH3", "test_fresh3_mismatched_memory_relation_fails_closed"),
    ("FRESH4", "test_fresh4_exact_replay_is_idempotent_and_semantic_drift_is_rejected"),
    ("FRESH5", "test_fresh5_only_validated_receipt_identity_crosses_cancel_unheard_boundary"),
    ("FRESH6", "test_fresh6_backchannel_like_predecessor_does_not_invent_full_assistant_utterance"),
    ("FRESH7", "test_fresh7_restart_before_successor_creation_preserves_exactly_once_projection"),
    ("FRESH8", "test_fresh8_tool_and_memory_refs_remain_reference_only_without_effect_replay"),
    ("FRESH9", "test_fresh9_packet_successor_composition_requires_no_network_or_external_model"),
    ("FRESH10", "test_fresh10_missing_or_corrupt_prior_receipt_fails_closed"),
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_case_class():
    spec = importlib.util.spec_from_file_location("wp719_test_fresh_turn_successor", TEST_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {TEST_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FreshTurnSuccessorTests


def main() -> int:
    case_class = load_case_class()
    tests = []
    id_by_test = {}
    for fresh_id, method in CASES:
        test = case_class(method)
        tests.append(test)
        id_by_test[test.id()] = fresh_id

    suite = unittest.TestSuite(tests)
    runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=2)
    result = runner.run(suite)

    failed_test_ids = {test.id() for test, _trace in result.failures}
    error_test_ids = {test.id() for test, _trace in result.errors}
    skipped_test_ids = {test.id() for test, _reason in result.skipped}
    unexpected_success_ids = {test.id() for test in result.unexpectedSuccesses}

    matrix = []
    for test in tests:
        test_id = test.id()
        fresh_id = id_by_test[test_id]
        if test_id in failed_test_ids:
            status = "FAIL"
        elif test_id in error_test_ids:
            status = "ERROR"
        elif test_id in skipped_test_ids:
            status = "SKIP"
        elif test_id in unexpected_success_ids:
            status = "UNEXPECTED_SUCCESS"
        else:
            status = "PASS"
        matrix.append({"id": fresh_id, "test": test._testMethodName, "status": status})

    receipt = {
        "schema": "FRANKENSTEIN2_WP719_FRESH_TURN_FALSIFIER_RECEIPT/v1",
        "workpackage_id": "F2-WP-719",
        "generation": 1,
        "work_class": "INTEGRATION_BLOCKER",
        "target_scope": "FRESH_TURN_SUCCESSOR_REPOSITORY_OR_VPS_SANDBOX_DISCRIMINATOR",
        "python": platform.python_version(),
        "implementation_sha256": sha256_file(ROOT / "src" / "frankenstein2" / "fresh_turn_successor.py"),
        "test_sha256": sha256_file(TEST_PATH),
        "matrix": matrix,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "successful": result.wasSuccessful(),
        "credit_fence": {
            "repository_component_ci_credit": 1 if result.wasSuccessful() else 0,
            "target_environment_component_runtime_credit": 0,
            "canonical_memory_write_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "effect_credit": 0,
            "physical_audio_credit": 0,
            "training_credit": 0,
            "completion_credit": 0,
            "whole_system_acceptance": False,
        },
        "classification": (
            "PASS_AT_BOUNDED_REPOSITORY_DISCRIMINATOR_SCOPE"
            if result.wasSuccessful()
            else "PRODUCT_NEGATIVE_OR_TEST_DEFECT_REQUIRES_CLASSIFICATION"
        ),
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
