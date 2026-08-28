from __future__ import annotations

import hashlib
import unittest

from frankenstein2.prediction_contract import (
    PREDICTION_CONTRACT_SCHEMA,
    PREDICTION_RESIDUAL_SCHEMA,
    PredictionContract,
    PredictionContractError,
)


class PredictionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.basis = hashlib.sha256(b"basis-state").hexdigest()
        self.observed_fp = hashlib.sha256(b"observed-state").hexdigest()

    def contract(self, expected):
        return PredictionContract.create(
            prediction_id="prediction-1",
            target_id="workspace-state",
            generation=2,
            basis_fingerprint_sha256=self.basis,
            expected_projection=expected,
        )

    def observe(self, contract, observed):
        return contract.observe(
            observation_id="observation-1",
            observation_fingerprint_sha256=self.observed_fp,
            observed_projection=observed,
        )

    def test_exact_nested_match_has_zero_residual(self) -> None:
        expected = {
            "goal": "continue",
            "metrics": {"error": 0.25, "count": 3},
            "flags": [True, False],
        }
        contract = self.contract(expected)
        residual = self.observe(contract, expected)
        self.assertEqual(contract.schema, PREDICTION_CONTRACT_SCHEMA)
        self.assertEqual(residual.schema, PREDICTION_RESIDUAL_SCHEMA)
        self.assertTrue(residual.exact_match)
        self.assertEqual(residual.mismatch_count, 0)
        self.assertEqual(residual.numeric_l1, 0.0)
        self.assertEqual(residual.mismatch_fraction, 0.0)
        self.assertEqual(residual.expected_projection_sha256, residual.observed_projection_sha256)
        self.assertEqual(residual.classification, "EXPLICIT_OBSERVATION_RESIDUAL_NOT_WORLD_TRUTH")

    def test_numeric_residual_reports_exact_paths_and_l1(self) -> None:
        contract = self.contract({"x": 10, "nested": {"y": 1.5}})
        residual = self.observe(contract, {"x": 13, "nested": {"y": 1.0}})
        self.assertFalse(residual.exact_match)
        self.assertEqual(residual.changed_paths, ("$/nested/y", "$/x"))
        self.assertEqual(
            residual.numeric_absolute_residuals,
            (("$/nested/y", 0.5), ("$/x", 3.0)),
        )
        self.assertEqual(residual.numeric_l1, 3.5)
        self.assertEqual(residual.mismatch_count, 2)
        self.assertEqual(residual.mismatch_fraction, 1.0)

    def test_missing_and_unexpected_nested_leaves_are_preserved(self) -> None:
        contract = self.contract({"a": {"x": 1, "y": 2}, "keep": 9})
        residual = self.observe(contract, {"a": {"x": 1, "z": 3}, "keep": 9})
        self.assertEqual(residual.missing_paths, ("$/a/y",))
        self.assertEqual(residual.unexpected_paths, ("$/a/z",))
        self.assertEqual(residual.changed_paths, ())
        self.assertEqual(residual.mismatch_count, 2)
        self.assertGreaterEqual(residual.mismatch_fraction, 0.0)
        self.assertLessEqual(residual.mismatch_fraction, 1.0)

    def test_fully_disjoint_structures_have_bounded_unit_mismatch_fraction(self) -> None:
        residual = self.observe(self.contract({"expected": 1}), {"observed": 2})
        self.assertEqual(residual.missing_paths, ("$/expected",))
        self.assertEqual(residual.unexpected_paths, ("$/observed",))
        self.assertEqual(residual.compared_leaf_count, 0)
        self.assertEqual(residual.mismatch_count, 2)
        self.assertEqual(residual.mismatch_fraction, 1.0)

    def test_list_length_residual_is_leaf_precise(self) -> None:
        contract = self.contract({"cells": [{"v": 1}, {"v": 2}]})
        residual = self.observe(contract, {"cells": [{"v": 1}, {"v": 2}, {"v": 3}]})
        self.assertEqual(residual.unexpected_paths, ("$/cells/2/v",))
        self.assertEqual(residual.mismatch_count, 1)
        self.assertGreaterEqual(residual.mismatch_fraction, 0.0)
        self.assertLessEqual(residual.mismatch_fraction, 1.0)

    def test_integer_float_type_change_is_not_silently_normalized(self) -> None:
        residual = self.observe(self.contract({"value": 1}), {"value": 1.0})
        self.assertEqual(residual.type_mismatch_paths, ("$/value",))
        self.assertEqual(residual.changed_paths, ("$/value",))
        self.assertEqual(residual.numeric_absolute_residuals, ())
        self.assertFalse(residual.exact_match)
        self.assertEqual(residual.mismatch_fraction, 1.0)

    def test_boolean_integer_type_change_is_not_numeric(self) -> None:
        residual = self.observe(self.contract({"value": True}), {"value": 1})
        self.assertEqual(residual.type_mismatch_paths, ("$/value",))
        self.assertEqual(residual.numeric_l1, 0.0)

    def test_container_type_change_is_one_explicit_structural_mismatch(self) -> None:
        residual = self.observe(self.contract({"value": {"x": 1}}), {"value": [1]})
        self.assertEqual(residual.type_mismatch_paths, ("$/value",))
        self.assertEqual(residual.mismatch_count, 1)
        self.assertEqual(residual.mismatch_fraction, 1.0)

    def test_canonical_order_makes_contract_digest_mapping_order_independent(self) -> None:
        left = self.contract({"b": 2, "a": 1})
        right = self.contract({"a": 1, "b": 2})
        self.assertEqual(left.expected_projection_canonical_json, right.expected_projection_canonical_json)
        self.assertEqual(left.expected_projection_sha256, right.expected_projection_sha256)
        self.assertEqual(left.sha256(), right.sha256())

    def test_json_pointer_escapes_keys_deterministically(self) -> None:
        residual = self.observe(self.contract({"a/b~c": 1}), {"a/b~c": 2})
        self.assertEqual(residual.changed_paths, ("$/a~1b~0c",))

    def test_expected_projection_is_deeply_frozen_by_canonical_json_copy(self) -> None:
        mutable = {"nested": {"value": 1}}
        contract = self.contract(mutable)
        mutable["nested"]["value"] = 999
        self.assertEqual(contract.expected_projection, {"nested": {"value": 1}})
        residual = self.observe(contract, {"nested": {"value": 1}})
        self.assertTrue(residual.exact_match)

    def test_nonfinite_and_non_json_state_fail_closed(self) -> None:
        with self.assertRaisesRegex(PredictionContractError, "non-finite"):
            self.contract({"x": float("nan")})
        with self.assertRaisesRegex(PredictionContractError, "unsupported projection value"):
            self.contract({"x": object()})
        with self.assertRaisesRegex(PredictionContractError, "mapping key"):
            self.contract({1: "not-a-json-object-key"})

    def test_identifiers_generation_and_fingerprints_fail_closed(self) -> None:
        with self.assertRaises(PredictionContractError):
            PredictionContract.create(
                prediction_id=" bad",
                target_id="x",
                generation=1,
                basis_fingerprint_sha256=self.basis,
                expected_projection={},
            )
        with self.assertRaises(PredictionContractError):
            PredictionContract.create(
                prediction_id="p",
                target_id="x",
                generation=0,
                basis_fingerprint_sha256=self.basis,
                expected_projection={},
            )
        with self.assertRaises(PredictionContractError):
            PredictionContract.create(
                prediction_id="p",
                target_id="x",
                generation=1,
                basis_fingerprint_sha256="not-a-sha",
                expected_projection={},
            )

    def test_observation_requires_explicit_identity_and_fingerprint(self) -> None:
        contract = self.contract({"x": 1})
        with self.assertRaises(PredictionContractError):
            contract.observe(
                observation_id="",
                observation_fingerprint_sha256=self.observed_fp,
                observed_projection={"x": 1},
            )
        with self.assertRaises(PredictionContractError):
            contract.observe(
                observation_id="obs",
                observation_fingerprint_sha256="UNKNOWN",
                observed_projection={"x": 1},
            )

    def test_residual_receipt_is_deterministic(self) -> None:
        contract = self.contract({"x": 5, "y": [1, 2]})
        first = self.observe(contract, {"x": 7, "y": [1, 3]})
        second = self.observe(contract, {"y": [1, 3], "x": 7})
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(len(first.sha256()), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
