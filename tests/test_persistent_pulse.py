from __future__ import annotations

import hashlib
import unittest

from frankenstein2.persistent_pulse import (
    PULSE_DECISION_SCHEMA,
    PULSE_INPUT_SCHEMA,
    PersistentPulseError,
    PulseDecision,
    PulseEligibility,
    PulseInput,
    classify_pulse_eligibility,
)


class PersistentPulseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state_digest = hashlib.sha256(b"explicit-state").hexdigest()

    def pulse(self, **overrides) -> PulseInput:
        values = {
            "pulse_id": "pulse-1",
            "observation_id": "obs-1",
            "state_id": "state-1",
            "generation": 7,
            "state_digest_sha256": self.state_digest,
        }
        values.update(overrides)
        return PulseInput.create(**values)

    def test_empty_explicit_input_invents_no_eligibility(self) -> None:
        decision = classify_pulse_eligibility(self.pulse())
        self.assertEqual(decision.schema, PULSE_DECISION_SCHEMA)
        self.assertEqual(decision.eligible_actions, ())
        self.assertEqual(decision.suppressed_by_hold, ())
        self.assertEqual(
            decision.classification,
            "ELIGIBILITY_ONLY_NO_ACTION_SELECTION_OR_EFFECT_AUTHORITY",
        )

    def test_each_explicit_ref_maps_only_to_its_action_class(self) -> None:
        cases = {
            "act_candidate_ref": "ACT",
            "ask_candidate_ref": "ASK",
            "observe_candidate_ref": "OBSERVE",
            "wait_condition_ref": "WAIT",
            "hold_reason_ref": "HOLD",
            "delegate_candidate_ref": "DELEGATE",
        }
        for field_name, action in cases.items():
            with self.subTest(field_name=field_name):
                decision = classify_pulse_eligibility(self.pulse(**{field_name: "ref-1"}))
                self.assertEqual(decision.eligible_actions, (action,))

    def test_multiple_candidates_remain_multiple_eligibilities_not_selection(self) -> None:
        decision = classify_pulse_eligibility(
            self.pulse(
                act_candidate_ref="act-1",
                ask_candidate_ref="ask-1",
                delegate_candidate_ref="delegate-1",
            )
        )
        self.assertEqual(decision.eligible_actions, ("ACT", "ASK", "DELEGATE"))
        self.assertEqual(
            [item.basis_ref for item in decision.eligible],
            ["act-1", "ask-1", "delegate-1"],
        )

    def test_explicit_hold_fail_closes_effectful_eligibility(self) -> None:
        decision = classify_pulse_eligibility(
            self.pulse(
                act_candidate_ref="act-1",
                ask_candidate_ref="ask-1",
                observe_candidate_ref="observe-1",
                wait_condition_ref="wait-1",
                hold_reason_ref="hold-1",
                delegate_candidate_ref="delegate-1",
            )
        )
        self.assertEqual(decision.eligible_actions, ("ASK", "OBSERVE", "WAIT", "HOLD"))
        self.assertEqual(decision.suppressed_by_hold, ("ACT", "DELEGATE"))

    def test_hold_without_effect_candidates_suppresses_nothing(self) -> None:
        decision = classify_pulse_eligibility(
            self.pulse(hold_reason_ref="hold-1", observe_candidate_ref="observe-1")
        )
        self.assertEqual(decision.eligible_actions, ("OBSERVE", "HOLD"))
        self.assertEqual(decision.suppressed_by_hold, ())

    def test_action_order_is_fixed_and_deterministic(self) -> None:
        decision = classify_pulse_eligibility(
            self.pulse(
                delegate_candidate_ref="d",
                wait_condition_ref="w",
                act_candidate_ref="a",
                observe_candidate_ref="o",
                ask_candidate_ref="q",
            )
        )
        self.assertEqual(decision.eligible_actions, ("ACT", "ASK", "OBSERVE", "WAIT", "DELEGATE"))

    def test_input_and_decision_receipts_are_deterministic(self) -> None:
        first_input = self.pulse(ask_candidate_ref="q", wait_condition_ref="w")
        second_input = self.pulse(wait_condition_ref="w", ask_candidate_ref="q")
        first = classify_pulse_eligibility(first_input)
        second = classify_pulse_eligibility(second_input)
        self.assertEqual(first_input.canonical_json(), second_input.canonical_json())
        self.assertEqual(first_input.sha256(), second_input.sha256())
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.input_sha256, first_input.sha256())

    def test_state_identity_is_bound_without_interpreting_state(self) -> None:
        decision = classify_pulse_eligibility(self.pulse(observe_candidate_ref="o"))
        self.assertEqual(decision.state_id, "state-1")
        self.assertEqual(decision.generation, 7)
        self.assertEqual(decision.state_digest_sha256, self.state_digest)

    def test_identifiers_are_fail_closed(self) -> None:
        for field, value in (
            ("pulse_id", " bad"),
            ("observation_id", ""),
            ("state_id", "bad\ncontrol"),
            ("act_candidate_ref", " trailing "),
        ):
            with self.subTest(field=field):
                with self.assertRaises(PersistentPulseError):
                    self.pulse(**{field: value})

    def test_generation_and_digest_are_fail_closed(self) -> None:
        with self.assertRaises(PersistentPulseError):
            self.pulse(generation=True)
        with self.assertRaises(PersistentPulseError):
            self.pulse(generation=-1)
        with self.assertRaises(PersistentPulseError):
            self.pulse(state_digest_sha256="UNKNOWN")

    def test_direct_reclassification_is_rejected(self) -> None:
        with self.assertRaisesRegex(PersistentPulseError, "classification mismatch"):
            PulseInput(
                schema=PULSE_INPUT_SCHEMA,
                pulse_id="p",
                observation_id="o",
                state_id="s",
                generation=0,
                state_digest_sha256=self.state_digest,
                classification="WORLD_FACT",
            )

    def test_decision_cannot_claim_unsupported_action_or_noncanonical_order(self) -> None:
        with self.assertRaises(PersistentPulseError):
            PulseEligibility(action="EXECUTE", basis_ref="x")
        with self.assertRaisesRegex(PersistentPulseError, "canonically ordered"):
            PulseDecision(
                schema=PULSE_DECISION_SCHEMA,
                pulse_id="p",
                observation_id="o",
                state_id="s",
                generation=0,
                state_digest_sha256=self.state_digest,
                input_sha256="0" * 64,
                eligible=(
                    PulseEligibility(action="WAIT", basis_ref="w"),
                    PulseEligibility(action="ASK", basis_ref="q"),
                ),
                suppressed_by_hold=(),
            )

    def test_direct_decision_rejects_duplicate_eligible_action_classes(self) -> None:
        with self.assertRaisesRegex(PersistentPulseError, "duplicate action classes"):
            PulseDecision(
                schema=PULSE_DECISION_SCHEMA,
                pulse_id="p",
                observation_id="o",
                state_id="s",
                generation=0,
                state_digest_sha256=self.state_digest,
                input_sha256="0" * 64,
                eligible=(
                    PulseEligibility(action="ACT", basis_ref="a-1"),
                    PulseEligibility(action="ACT", basis_ref="a-2"),
                ),
                suppressed_by_hold=(),
            )

    def test_direct_decision_rejects_eligible_suppressed_overlap(self) -> None:
        with self.assertRaisesRegex(PersistentPulseError, "must be disjoint"):
            PulseDecision(
                schema=PULSE_DECISION_SCHEMA,
                pulse_id="p",
                observation_id="o",
                state_id="s",
                generation=0,
                state_digest_sha256=self.state_digest,
                input_sha256="0" * 64,
                eligible=(PulseEligibility(action="ACT", basis_ref="a"),),
                suppressed_by_hold=("ACT",),
            )

    def test_hold_suppression_receipt_rejects_impossible_action(self) -> None:
        with self.assertRaisesRegex(PersistentPulseError, "only contain ACT/DELEGATE"):
            PulseDecision(
                schema=PULSE_DECISION_SCHEMA,
                pulse_id="p",
                observation_id="o",
                state_id="s",
                generation=0,
                state_digest_sha256=self.state_digest,
                input_sha256="0" * 64,
                eligible=(),
                suppressed_by_hold=("ASK",),
            )

    def test_kernel_has_no_default_hold_or_act(self) -> None:
        empty = classify_pulse_eligibility(self.pulse())
        self.assertNotIn("HOLD", empty.eligible_actions)
        self.assertNotIn("ACT", empty.eligible_actions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
