import json
from pathlib import Path
import unittest

from frankenstein2.cognitive_agentic_core_source_attestation import (
    ATTESTATION_CLASSIFICATION,
    EXPLORATION,
    GOAL_SETTING,
    MODELING,
    PLANNING_EXECUTION,
    REQUIRED_CAPABILITIES,
    SOURCE_BINDINGS,
    SourceAcceptanceAttestationError,
    attest_source_acceptance,
    attest_source_acceptance_files,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class AgenticCoreSourceAttestationTests(unittest.TestCase):
    def test_all_four_frozen_dependency_sources_attest_from_exact_repository_bytes(self):
        observed = {}
        for capability in REQUIRED_CAPABILITIES:
            attestation = attest_source_acceptance_files(REPOSITORY_ROOT, capability)
            binding = SOURCE_BINDINGS[capability]
            self.assertEqual(attestation.capability, capability)
            self.assertEqual(attestation.workpackage_id, binding.workpackage_id)
            self.assertEqual(attestation.generation, binding.generation)
            self.assertEqual(attestation.claim_id, binding.claim_id)
            self.assertEqual(attestation.terminal_scope, binding.terminal_scope)
            self.assertEqual(attestation.reconciliation_git_blob_sha1, binding.reconciliation_git_blob_sha1)
            self.assertEqual(attestation.receipt_git_blob_sha1, binding.receipt_git_blob_sha1)
            self.assertEqual(len(attestation.reconciliation_content_sha256), 64)
            self.assertEqual(len(attestation.receipt_content_sha256), 64)
            self.assertEqual(attestation.classification, ATTESTATION_CLASSIFICATION)
            observed[capability] = attestation.sha256()
        self.assertEqual(set(observed), {EXPLORATION, MODELING, GOAL_SETTING, PLANNING_EXECUTION})
        self.assertEqual(len(set(observed.values())), 4)

    def test_semantically_equivalent_reformatted_reconciliation_is_rejected(self):
        binding = SOURCE_BINDINGS[EXPLORATION]
        raw = (REPOSITORY_ROOT / binding.reconciliation_ref).read_bytes()
        value = json.loads(raw.decode("utf-8"))
        reformatted = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertNotEqual(raw, reformatted)
        receipt = (REPOSITORY_ROOT / binding.receipt_ref).read_bytes()
        with self.assertRaisesRegex(SourceAcceptanceAttestationError, "frozen Git blob identity"):
            attest_source_acceptance(
                EXPLORATION,
                reconciliation_bytes=reformatted,
                receipt_bytes=receipt,
            )

    def test_cross_capability_receipt_substitution_is_rejected_before_semantic_promotion(self):
        exploration = SOURCE_BINDINGS[EXPLORATION]
        modeling = SOURCE_BINDINGS[MODELING]
        reconciliation = (REPOSITORY_ROOT / exploration.reconciliation_ref).read_bytes()
        wrong_receipt = (REPOSITORY_ROOT / modeling.receipt_ref).read_bytes()
        with self.assertRaisesRegex(SourceAcceptanceAttestationError, "receipt bytes do not match frozen Git blob identity"):
            attest_source_acceptance(
                EXPLORATION,
                reconciliation_bytes=reconciliation,
                receipt_bytes=wrong_receipt,
            )

    def test_byte_mutation_cannot_become_source_acceptance(self):
        binding = SOURCE_BINDINGS[PLANNING_EXECUTION]
        reconciliation = bytearray((REPOSITORY_ROOT / binding.reconciliation_ref).read_bytes())
        reconciliation[-2] = ord(" ") if reconciliation[-2] != ord(" ") else ord("\t")
        receipt = (REPOSITORY_ROOT / binding.receipt_ref).read_bytes()
        with self.assertRaisesRegex(SourceAcceptanceAttestationError, "frozen Git blob identity"):
            attest_source_acceptance(
                PLANNING_EXECUTION,
                reconciliation_bytes=bytes(reconciliation),
                receipt_bytes=receipt,
            )

    def test_unknown_capability_is_rejected(self):
        with self.assertRaisesRegex(SourceAcceptanceAttestationError, "no frozen source binding"):
            attest_source_acceptance(
                "UNKNOWN",
                reconciliation_bytes=b"{}",
                receipt_bytes=b"{}",
            )

    def test_source_attestation_does_not_mint_measurement_fields(self):
        attestation = attest_source_acceptance_files(REPOSITORY_ROOT, GOAL_SETTING)
        for forbidden in (
            "shared_fixture_family_sha256",
            "baseline_score_ppm",
            "intervention_score_ppm",
            "sample_count",
            "success_count",
            "action_count",
            "runtime_credit",
            "whole_system_acceptance",
        ):
            self.assertNotIn(forbidden, attestation.as_dict())


if __name__ == "__main__":
    unittest.main()
