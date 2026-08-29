from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from frankenstein2.cognitive_agentic_core_falsifier import (
    EXPLORATION,
    FALSIFIED,
    GOAL_SETTING,
    MODELING,
    PLANNING_EXECUTION,
    POLICY_SCHEMA,
    SUPPORTED_AT_COMPONENT_SCOPE,
    FalsifierPolicy,
)
from frankenstein2.cognitive_agentic_core_repository_binder import (
    MEASUREMENT_CLASSIFICATION,
    MEASUREMENT_SCHEMA,
    NOT_EVALUABLE,
    RepositoryEvidenceBindingError,
    bind_repository_source,
    capability_evidence_from_repository,
    evaluate_repository_bound_agentic_core,
)


CAPABILITIES = (EXPLORATION, MODELING, GOAL_SETTING, PLANNING_EXECUTION)
ROOT = Path(__file__).resolve().parents[1]


def policy(**overrides) -> FalsifierPolicy:
    values = dict(
        schema=POLICY_SCHEMA,
        policy_id="wp807-repository-bound-v1",
        generation=1,
        min_intervention_score_ppm=600_000,
        min_delta_over_baseline_ppm=100_000,
        min_sample_count_per_capability=10,
        max_external_actions_per_capability=10_000,
        require_shared_holdout_set=True,
    )
    values.update(overrides)
    return FalsifierPolicy(**values)


def copy_source_chain(source_root: Path, target_root: Path, capability: str):
    binding = bind_repository_source(source_root, capability)
    for rel in (binding.active_path, binding.reconciliation_path, binding.receipt_path):
        src = source_root / rel
        dst = target_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return bind_repository_source(target_root, capability)


def write_measurement(
    root: Path,
    capability: str,
    *,
    actions: int = 60,
    family_sha: str = "9" * 64,
    receipt_sha_override: str | None = None,
) -> str:
    binding = bind_repository_source(root, capability)
    rel = f"workpackages/measurements/F2-WP-807/{capability.lower()}.json"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": MEASUREMENT_SCHEMA,
        "capability": capability,
        "source_workpackage_id": binding.workpackage_id,
        "source_generation": binding.generation,
        "source_claim_id": binding.claim_id,
        "source_reconciliation_content_sha256": binding.reconciliation_content_sha256,
        "source_receipt_content_sha256": receipt_sha_override or binding.receipt_content_sha256,
        "benchmark_id": f"benchmark/{capability.lower()}",
        "holdout_set_id": "heldout/shared/repository-bound",
        "shared_fixture_family_sha256": family_sha,
        "baseline_id": f"baseline/{capability.lower()}",
        "baseline_score_ppm": 300_000,
        "intervention_score_ppm": 700_000,
        "sample_count": 20,
        "success_count": 14,
        "action_count": actions,
        "measurement_head_sha": "a" * 40,
        "measurement_run_id": 123456,
        "measurement_job_id": 654321,
        "producer_result_sha256": "b" * 64,
        "classification": MEASUREMENT_CLASSIFICATION,
    }
    path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return rel


class RepositoryEvidenceBinderTests(unittest.TestCase):
    def test_current_accepted_wp802_to_wp805_source_chains_bind_exactly(self):
        observed = {}
        for capability in CAPABILITIES:
            binding = bind_repository_source(ROOT, capability)
            observed[capability] = binding
            self.assertTrue(binding.workpackage_id.startswith("F2-WP-80"))
            self.assertEqual(len(binding.reconciliation_content_sha256), 64)
            self.assertEqual(len(binding.receipt_content_sha256), 64)
            self.assertGreater(binding.merged_main_run_id, 0)
            self.assertEqual(len(binding.merged_main_head_sha), 40)
        self.assertEqual(set(observed), set(CAPABILITIES))

    def test_current_repository_without_measurement_records_stays_not_evaluable(self):
        report = evaluate_repository_bound_agentic_core(
            ROOT,
            {},
            policy=policy(),
            report_id="wp807-current-no-measurements",
        )
        self.assertEqual(report.verdict, NOT_EVALUABLE)
        self.assertIsNone(report.inner_report)
        self.assertEqual(
            report.reasons,
            tuple(sorted(f"MISSING_REPOSITORY_MEASUREMENT:{cap}" for cap in CAPABILITIES)),
        )
        self.assertEqual(len(report.source_binding_sha256s), 4)
        self.assertEqual(report.measurement_content_sha256s, ())
        self.assertEqual(report.runtime_credit, 0)
        self.assertEqual(report.physical_grid10_credit, 0)
        self.assertFalse(report.whole_system_acceptance)

    def test_repository_measurement_must_bind_exact_accepted_source_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_source_chain(ROOT, root, EXPLORATION)
            rel = write_measurement(root, EXPLORATION, receipt_sha_override="f" * 64)
            with self.assertRaisesRegex(
                RepositoryEvidenceBindingError,
                "does not bind exact accepted source chain",
            ):
                capability_evidence_from_repository(root, EXPLORATION, rel)

    def test_complete_repository_bound_measurements_reach_inner_component_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {}
            for capability in CAPABILITIES:
                copy_source_chain(ROOT, root, capability)
                paths[capability] = write_measurement(root, capability)
            report = evaluate_repository_bound_agentic_core(
                root,
                paths,
                policy=policy(),
                report_id="wp807-repository-bound-supported",
            )
            self.assertEqual(report.verdict, SUPPORTED_AT_COMPONENT_SCOPE)
            self.assertIsNotNone(report.inner_report)
            self.assertEqual(report.inner_report.verdict, SUPPORTED_AT_COMPONENT_SCOPE)
            self.assertEqual(len(report.source_binding_sha256s), 4)
            self.assertEqual(len(report.measurement_content_sha256s), 4)
            self.assertEqual(report.runtime_credit, 0)
            self.assertEqual(report.gwt_jspace_credit, 0)
            self.assertFalse(report.whole_system_acceptance)

    def test_repository_bound_external_action_overrun_is_falsified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {}
            for capability in CAPABILITIES:
                copy_source_chain(ROOT, root, capability)
                paths[capability] = write_measurement(
                    root,
                    capability,
                    actions=200_000_000 if capability == PLANNING_EXECUTION else 60,
                )
            report = evaluate_repository_bound_agentic_core(
                root,
                paths,
                policy=policy(),
                report_id="wp807-repository-bound-action-overrun",
            )
            self.assertEqual(report.verdict, FALSIFIED)
            self.assertIn(
                f"EXTERNAL_ACTION_BUDGET_EXCEEDED:{PLANNING_EXECUTION}",
                report.reasons,
            )
            self.assertEqual(report.runtime_credit, 0)
            self.assertFalse(report.whole_system_acceptance)

    def test_source_binding_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active_dir = root / "workpackages" / "active"
            active_dir.mkdir(parents=True)
            active = {
                "workpackage_id": "F2-WP-802",
                "generation": 1,
                "claim_id": "claim",
                "state": "ACCEPTED",
                "terminal_scope": "scope",
                "reconciliation_ref": "../../outside.json",
                "acceptance_receipt": "workpackages/receipts/receipt.json",
                "component_test_execution_observed": True,
                "runtime_credit": 0,
                "whole_system_acceptance": False,
            }
            (active_dir / "F2-WP-802.json").write_text(json.dumps(active), encoding="utf-8")
            with self.assertRaisesRegex(
                RepositoryEvidenceBindingError,
                "reconciliation path is outside canonical workpackage namespace",
            ):
                bind_repository_source(root, EXPLORATION)


if __name__ == "__main__":
    unittest.main()
