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


class PredictionResidualClassificationFalsifier(unittest.TestCase):
    def test_inner_residual_world_truth_relabel_must_fail_closed(self):
        basis = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=7,
            projection={"counter": 1},
        )
        bound = FingerprintBoundPrediction.create(
            prediction_id="prediction-classification-falsifier",
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
        receipt = bound.observe(
            observation_id="obs-classification-falsifier",
            observation_fingerprint=observed,
            observed_projection={"counter": 2},
        )
        poisoned = replace(receipt.residual, classification="WORLD_TRUTH")

        with self.assertRaises(PredictionFingerprintBindingError):
            FingerprintBoundResidual(
                schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
                binding=receipt.binding,
                binding_sha256=receipt.binding_sha256,
                basis_fingerprint=receipt.basis_fingerprint,
                observation_fingerprint=receipt.observation_fingerprint,
                residual=poisoned,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
