from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.prediction_fingerprint_binding import (
    PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
    FingerprintBoundPrediction,
    FingerprintBoundResidual,
    PredictionFingerprintBindingError,
)
from frankenstein2.state_fingerprint import fingerprint_state_projection


class PredictionFingerprintBindingNestedClassificationTests(unittest.TestCase):
    def test_inner_residual_world_truth_relabel_must_fail_closed(self):
        basis = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=7,
            projection={"counter": 1},
        )
        bound = FingerprintBoundPrediction.create(
            prediction_id="prediction-a",
            target_id="agency-state",
            generation=3,
            basis_fingerprint=basis,
            expected_projection={"counter": 2},
        )
        observed = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=8,
            projection={"counter": 2},
        )
        legitimate = bound.observe(
            observation_id="obs-1",
            observation_fingerprint=observed,
            observed_projection={"counter": 2},
        )
        forged_inner = replace(
            legitimate.residual,
            classification="WORLD_TRUTH",
        )

        with self.assertRaisesRegex(
            PredictionFingerprintBindingError,
            "nested residual classification mismatch",
        ):
            FingerprintBoundResidual(
                schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
                binding=bound,
                binding_sha256=legitimate.binding_sha256,
                basis_fingerprint=legitimate.basis_fingerprint,
                observation_fingerprint=legitimate.observation_fingerprint,
                residual=forged_inner,
            )

    def test_legitimate_nested_classification_still_admits(self):
        basis = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=7,
            projection={"counter": 1},
        )
        bound = FingerprintBoundPrediction.create(
            prediction_id="prediction-a",
            target_id="agency-state",
            generation=3,
            basis_fingerprint=basis,
            expected_projection={"counter": 2},
        )
        observed = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=8,
            projection={"counter": 2},
        )
        legitimate = bound.observe(
            observation_id="obs-1",
            observation_fingerprint=observed,
            observed_projection={"counter": 2},
        )
        reconstructed = FingerprintBoundResidual(
            schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
            binding=bound,
            binding_sha256=legitimate.binding_sha256,
            basis_fingerprint=legitimate.basis_fingerprint,
            observation_fingerprint=legitimate.observation_fingerprint,
            residual=legitimate.residual,
        )
        self.assertEqual(reconstructed.sha256(), legitimate.sha256())


if __name__ == "__main__":
    unittest.main(verbosity=2)
