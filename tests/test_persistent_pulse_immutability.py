from __future__ import annotations

import hashlib
import unittest

from frankenstein2.persistent_pulse import (
    PULSE_DECISION_SCHEMA,
    PersistentPulseError,
    PulseDecision,
    PulseEligibility,
)


class PersistentPulseReceiptImmutabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state_digest = hashlib.sha256(b"explicit-state").hexdigest()

    def decision(self, *, eligible, suppressed_by_hold):
        return PulseDecision(
            schema=PULSE_DECISION_SCHEMA,
            pulse_id="pulse-immutable",
            observation_id="obs-immutable",
            state_id="state-immutable",
            generation=3,
            state_digest_sha256=self.state_digest,
            input_sha256="0" * 64,
            eligible=eligible,
            suppressed_by_hold=suppressed_by_hold,
        )

    def test_mutable_eligible_container_fails_closed(self) -> None:
        items: list[PulseEligibility] = []
        with self.assertRaisesRegex(PersistentPulseError, "eligible must be an immutable tuple"):
            self.decision(eligible=items, suppressed_by_hold=())

    def test_mutable_suppression_container_fails_closed(self) -> None:
        suppressed: list[str] = []
        with self.assertRaisesRegex(
            PersistentPulseError,
            "suppressed_by_hold must be an immutable tuple",
        ):
            self.decision(eligible=(), suppressed_by_hold=suppressed)

    def test_non_pulse_eligibility_member_fails_closed_before_serialization(self) -> None:
        with self.assertRaisesRegex(
            PersistentPulseError,
            "eligible must contain concrete PulseEligibility values",
        ):
            self.decision(eligible=(object(),), suppressed_by_hold=())

    def test_successful_receipt_is_detached_from_caller_mutable_source(self) -> None:
        caller_items = [PulseEligibility(action="ASK", basis_ref="ask-1")]
        decision = self.decision(eligible=tuple(caller_items), suppressed_by_hold=())
        before = decision.sha256()
        caller_items.append(PulseEligibility(action="WAIT", basis_ref="wait-1"))
        after = decision.sha256()
        self.assertEqual(before, after)
        self.assertEqual(decision.eligible_actions, ("ASK",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
