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


class PredictionFingerprintBoundReceiptFalsifier(unittest.TestCase):
    """REVIEW_ONLY falsifiers for F2-WP-202 G2 receipt rehydration boundaries."""

    @staticmethod
    def _receipt():
        basis_projection = {"counter": 1}
        expected_projection = {"counter": 2}
        basis = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=7,
            projection=basis_projection,
        )
        bound = FingerprintBoundPrediction.create(
            prediction_id="prediction-bound-falsifier",
            target_id="agency-state",
            generation=3,
            basis_fingerprint=basis,
            expected_projection=expected_projection,
        )
        observed = fingerprint_state_projection(
            projection_schema="AGENCY_STATE/v1",
            generation=8,
            projection=expected_projection,
        )
        receipt = bound.observe(
            observation_id="obs-falsifier",
            observation_fingerprint=observed,
            observed_projection=expected_projection,
        )
        return receipt

    def test_non_hex_binding_digest_must_fail_closed(self):
        receipt = self._receipt()
        with self.assertRaises(PredictionFingerprintBindingError):
            FingerprintBoundResidual(
                schema=PREDICTION_FINGERPRINT_RESIDUAL_SCHEMA,
                binding=receipt.binding,
                binding_sha256="z" * 64,
                basis_fingerprint=receipt.basis_fingerprint,
                observation_fingerprint=receipt.observation_fingerprint,
                residual=receipt.residual,
            )

    def test_inner_residual_cannot_be_reclassified_as_world_truth(self):
        receipt = self._receipt()
        poisoned = replace(
            receipt.residual,
            classification="WORLD_TRUTH",
        )
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
