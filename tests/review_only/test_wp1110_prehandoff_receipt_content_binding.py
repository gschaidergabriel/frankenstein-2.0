"""REVIEW_ONLY falsifier for F2-WP-1110 generation 2.

This test intentionally describes a missing evidence-binding invariant. It must not be
interpreted as a canonical mutation authority or runtime failure. The current clean-machine
API binds only the textual prehandoff_receipt_ref; a mutable object at the same reference
could therefore be substituted without changing the acceptance inputs.

Expected closure: the clean-machine evidence subject must bind immutable receipt content
(e.g. a canonical receipt SHA-256 or an equivalently content-addressed reference), in addition
to the release manifest and outer release artifact subject.
"""
from __future__ import annotations

from dataclasses import fields
import inspect
import unittest

from frankenstein2.clean_machine_acceptance import (
    AcceptanceObservation,
    evaluate_clean_machine_acceptance,
)


class WP1110PreHandoffReceiptContentBindingFalsifier(unittest.TestCase):
    def test_clean_machine_observation_binds_immutable_prehandoff_receipt_content(self):
        observation_fields = {field.name for field in fields(AcceptanceObservation)}
        evaluator_parameters = set(inspect.signature(evaluate_clean_machine_acceptance).parameters)

        self.assertIn(
            "prehandoff_receipt_sha256",
            observation_fields,
            "REVIEW_ONLY: clean-machine observations currently bind only a textual receipt ref; "
            "they need immutable prehandoff receipt content identity or an equivalent content-addressed invariant",
        )
        self.assertIn(
            "prehandoff_receipt_sha256",
            evaluator_parameters,
            "REVIEW_ONLY: the matrix-level expected subject must include immutable prehandoff receipt content identity",
        )


if __name__ == "__main__":
    unittest.main()
