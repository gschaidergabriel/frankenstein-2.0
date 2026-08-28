from __future__ import annotations

import unittest

from frankenstein2.prediction_fingerprint_binding import (
    PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
    FingerprintBoundPrediction,
    FingerprintBoundResidual,
    PredictionFingerprintBindingError,
)
from frankenstein2.state_fingerprint import fingerprint_state_projection


class PredictionFingerprintBindingProvenanceTests(unittest.TestCase):
    def fp(self, projection, *, generation=7):
        return fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=generation,
            projection=projection,
        )

    def bound(self, *, expected_projection, prediction_id="prediction-a", target_id="agency-state"):
        return FingerprintBoundPrediction.create(
            prediction_id=prediction_id,
            target_id=target_id,
            generation=3,
            basis_fingerprint=self.fp({"counter": 1}),
            expected_projection=expected_projection,
        )

    def receipt(self, bound, observed_projection):
        observed = self.fp(observed_projection, generation=8)
        return bound.observe(
            observation_id="obs-1",
            observation_fingerprint=observed,
            observed_projection=observed_projection,
        )

    def test_generation_zero_statefingerprint_is_bound_without_renumbering(self):
        basis = self.fp({"bootstrap": True}, generation=0)
        bound = FingerprintBoundPrediction.create(
            prediction_id="prediction-from-bootstrap-state",
            target_id="agency-state",
            generation=1,
            basis_fingerprint=basis,
            expected_projection={"bootstrap": False},
        )
        self.assertEqual(bound.basis_fingerprint.generation, 0)
        self.assertEqual(bound.basis_fingerprint.identity_sha256, basis.identity_sha256)
        self.assertEqual(bound.contract.generation, 1)
        self.assertEqual(
            bound.contract.basis_fingerprint_sha256,
            basis.identity_sha256,
        )
        self.assertEqual(
            bound.as_dict()["basis_fingerprint"],
            basis.as_dict(),
        )

    def test_nonhex_or_arbitrary_binding_digest_cannot_be_asserted(self):
        bound = self.bound(expected_projection={"counter": 2})
        receipt = self.receipt(bound, {"counter": 2})
        with self.assertRaisesRegex(
            PredictionFingerprintBindingError,
            "binding_sha256 does not match",
        ):
            FingerprintBoundResidual(
                schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
                binding=bound,
                binding_sha256="x" * 64,
                basis_fingerprint=receipt.basis_fingerprint,
                observation_fingerprint=receipt.observation_fingerprint,
                residual=receipt.residual,
            )

    def test_residual_from_one_prediction_cannot_be_rebound_to_another(self):
        bound_a = self.bound(
            prediction_id="prediction-a",
            expected_projection={"counter": 2},
        )
        bound_b = self.bound(
            prediction_id="prediction-b",
            expected_projection={"counter": 3},
        )
        receipt_a = self.receipt(bound_a, {"counter": 2})
        with self.assertRaisesRegex(
            PredictionFingerprintBindingError,
            "prediction_id does not match",
        ):
            FingerprintBoundResidual(
                schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
                binding=bound_b,
                binding_sha256=bound_b.sha256(),
                basis_fingerprint=receipt_a.basis_fingerprint,
                observation_fingerprint=receipt_a.observation_fingerprint,
                residual=receipt_a.residual,
            )

    def test_expected_projection_contract_identity_is_bound(self):
        bound_a = self.bound(expected_projection={"counter": 2})
        bound_b = self.bound(expected_projection={"counter": 3})
        receipt_a = self.receipt(bound_a, {"counter": 2})
        with self.assertRaisesRegex(
            PredictionFingerprintBindingError,
            "expected projection does not match",
        ):
            FingerprintBoundResidual(
                schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
                binding=bound_b,
                binding_sha256=bound_b.sha256(),
                basis_fingerprint=receipt_a.basis_fingerprint,
                observation_fingerprint=receipt_a.observation_fingerprint,
                residual=receipt_a.residual,
            )

    def test_legitimate_observe_path_remains_deterministic(self):
        bound = self.bound(expected_projection={"counter": 2})
        first = self.receipt(bound, {"counter": 2})
        second = self.receipt(bound, {"counter": 2})
        self.assertEqual(first.binding_sha256, bound.sha256())
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertTrue(first.residual.exact_match)


if __name__ == "__main__":
    unittest.main(verbosity=2)
