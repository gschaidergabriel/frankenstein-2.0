import dataclasses
import unittest

from frankenstein2.situation_frame import (
    CYCLE_CONTRACT_SCHEMA,
    SITUATION_FRAME_SCHEMA,
    CycleContract,
    EpistemicRef,
    SituationFrame,
    SituationFrameError,
)

HASH_A = "a" * 64


def make_frame(**overrides):
    values = dict(
        frame_id="frame-1",
        cycle_id="cycle-1",
        generation=3,
        situation_epoch=9,
        agency_state_ref="agency-1",
        agency_state_generation=4,
        agency_state_sha256=HASH_A,
        epistemic_refs=(
            EpistemicRef("UNKNOWN", "unknown:z"),
            EpistemicRef("OBSERVATION", "obs:a"),
            EpistemicRef("MEMORY", "memory:b"),
        ),
        goal_refs=("goal:2", "goal:1"),
        prediction_refs=("prediction:1",),
        context_refs=("context:2", "context:1"),
        unresolved_alternative_refs=("alt:b", "alt:a"),
        completion_deficit_refs=("deficit:1",),
        authority_scope_refs=("authority:effectgate-only",),
        do_not_repeat_refs=("negative:old-path",),
        provenance_refs=("receipt:2", "receipt:1"),
    )
    values.update(overrides)
    return SituationFrame.create(**values)


class SituationFrameTests(unittest.TestCase):
    def test_schema_and_classification_are_explicit(self):
        frame = make_frame()
        self.assertEqual(frame.schema, SITUATION_FRAME_SCHEMA)
        self.assertIn("NOT_WORLD_TRUTH", frame.classification)

    def test_canonicalization_is_order_independent(self):
        a = make_frame()
        b = make_frame(
            epistemic_refs=tuple(reversed(a.epistemic_refs)),
            goal_refs=tuple(reversed(a.goal_refs)),
            context_refs=tuple(reversed(a.context_refs)),
            unresolved_alternative_refs=tuple(reversed(a.unresolved_alternative_refs)),
            provenance_refs=tuple(reversed(a.provenance_refs)),
        )
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.sha256(), b.sha256())

    def test_conflicting_epistemic_typing_fails_closed(self):
        with self.assertRaises(SituationFrameError):
            make_frame(
                epistemic_refs=(
                    EpistemicRef("OBSERVATION", "same-ref"),
                    EpistemicRef("HYPOTHESIS", "same-ref"),
                )
            )

    def test_authority_and_provenance_must_be_explicit(self):
        with self.assertRaises(SituationFrameError):
            make_frame(authority_scope_refs=())
        with self.assertRaises(SituationFrameError):
            make_frame(provenance_refs=())

    def test_frame_is_immutable(self):
        frame = make_frame()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            frame.generation = 99

    def test_contract_binds_exact_frame(self):
        frame = make_frame()
        contract = CycleContract.for_frame(
            frame,
            contract_id="contract-1",
            cycle_generation=4,
            max_grid_cells=10,
            allowed_exits=("HOLD", "ACT", "WAIT"),
            continuation_refs=("checkpoint:1",),
            provenance_refs=("policy:1",),
        )
        self.assertEqual(contract.schema, CYCLE_CONTRACT_SCHEMA)
        self.assertEqual(contract.allowed_exits, ("ACT", "WAIT", "HOLD"))
        contract.assert_matches(frame)

    def test_generation_mismatch_is_rejected(self):
        frame = make_frame()
        contract = CycleContract.for_frame(
            frame,
            contract_id="contract-1",
            cycle_generation=4,
            max_grid_cells=4,
            allowed_exits=("WAIT",),
            continuation_refs=("checkpoint:1",),
            provenance_refs=("policy:1",),
        )
        stale = make_frame(generation=4)
        with self.assertRaisesRegex(SituationFrameError, "generation mismatch"):
            contract.assert_matches(stale)

    def test_digest_mismatch_is_rejected(self):
        frame = make_frame()
        contract = CycleContract.for_frame(
            frame,
            contract_id="contract-1",
            cycle_generation=4,
            max_grid_cells=4,
            allowed_exits=("WAIT",),
            continuation_refs=("checkpoint:1",),
            provenance_refs=("policy:1",),
        )
        altered = make_frame(context_refs=("context:different",))
        with self.assertRaisesRegex(SituationFrameError, "digest mismatch"):
            contract.assert_matches(altered)

    def test_grid_budget_is_bounded_to_ten(self):
        frame = make_frame()
        for invalid in (0, 11, True):
            with self.subTest(invalid=invalid), self.assertRaises(SituationFrameError):
                CycleContract.for_frame(
                    frame,
                    contract_id="contract-1",
                    cycle_generation=4,
                    max_grid_cells=invalid,
                    allowed_exits=("WAIT",),
                    continuation_refs=("checkpoint:1",),
                    provenance_refs=("policy:1",),
                )

    def test_unknown_exit_fails_closed(self):
        frame = make_frame()
        with self.assertRaises(SituationFrameError):
            CycleContract.for_frame(
                frame,
                contract_id="contract-1",
                cycle_generation=4,
                max_grid_cells=4,
                allowed_exits=("DONE",),
                continuation_refs=("checkpoint:1",),
                provenance_refs=("policy:1",),
            )

    def test_contract_digest_is_deterministic(self):
        frame = make_frame()
        kwargs = dict(
            contract_id="contract-1",
            cycle_generation=4,
            max_grid_cells=7,
            continuation_refs=("checkpoint:b", "checkpoint:a"),
            provenance_refs=("policy:b", "policy:a"),
        )
        a = CycleContract.for_frame(frame, allowed_exits=("HOLD", "ACT"), **kwargs)
        b = CycleContract.for_frame(frame, allowed_exits=("ACT", "HOLD"), **kwargs)
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.sha256(), b.sha256())


if __name__ == "__main__":
    unittest.main()
