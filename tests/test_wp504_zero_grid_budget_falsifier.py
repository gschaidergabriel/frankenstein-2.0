#!/usr/bin/env python3
"""Candidate falsifier: unavailable GRID work budget must fail closed in WP504."""
from __future__ import annotations

import unittest

from frankenstein2.epistemic_action_selection import (
    EpistemicActionCandidate,
    select_epistemic_action,
)
from frankenstein2.grid10_interface import CellBudget, Grid10Plan
from frankenstein2.hyperposition import (
    Alternative,
    EpistemicStatus,
    create_discriminator_candidate,
    create_hyperposition,
)


def make_hyperposition():
    return create_hyperposition(
        hyperposition_id="hyper:zero-budget-falsifier",
        generation=1,
        alternatives=(
            Alternative(
                alternative_id="alt:a",
                proposition_ref="hypothesis:a",
                generation=1,
                epistemic_status=EpistemicStatus.INFERRED,
                provenance_refs=("falsifier:source",),
                support_refs=("evidence:a",),
                score_micros=500_000,
                uncertainty_micros=500_000,
            ),
            Alternative(
                alternative_id="alt:b",
                proposition_ref="hypothesis:b",
                generation=1,
                epistemic_status=EpistemicStatus.UNKNOWN,
                provenance_refs=("falsifier:source",),
                uncertainty_micros=900_000,
            ),
        ),
        provenance_refs=("falsifier:source",),
    )


def zero_budget_plan():
    return Grid10Plan.create(
        plan_id="grid:zero-budget",
        cycle_id="cycle:zero-budget",
        generation=1,
        frame_id="frame:zero-budget",
        frame_generation=1,
        frame_sha256="1" * 64,
        policy_id="policy:zero-budget",
        policy_generation=1,
        policy_sha256="2" * 64,
        cells=tuple(
            CellBudget(
                cell_id=f"G{i}",
                role_label=f"role:{i}",
                max_input_refs=1,
                max_output_refs=1,
                max_work_units=0,
                max_reentry_depth=0,
            )
            for i in range(1, 11)
        ),
        max_total_work_units=0,
        provenance_refs=("falsifier:source",),
    )


class WP504ZeroGridBudgetFalsifier(unittest.TestCase):
    def test_zero_total_and_cell_budget_cannot_emit_selected_proposal(self):
        hp = make_hyperposition()
        plan = zero_budget_plan()
        discriminator = create_discriminator_candidate(
            state=hp,
            expected_generation=hp.generation,
            expected_state_sha256=hp.sha256(),
            discriminator_id="disc:zero-budget",
            target_alternative_ids=("alt:a", "alt:b"),
            evidence_need_ref="need:zero-budget",
            expected_information_gain_micros=900_000,
            estimated_cost_micros=0,
            provenance_refs=("falsifier:source",),
        )
        candidate = EpistemicActionCandidate(
            candidate_id="candidate:zero-work",
            action_ref="action:zero-work",
            cell_id="G1",
            work_units_requested=0,
            discriminator=discriminator,
            provenance_refs=("falsifier:source",),
        )

        proposal = select_epistemic_action(
            proposal_id="proposal:zero-budget",
            state=hp,
            expected_hyperposition_generation=hp.generation,
            expected_hyperposition_sha256=hp.sha256(),
            plan=plan,
            expected_plan_generation=plan.generation,
            expected_plan_sha256=plan.sha256(),
            candidates=(candidate,),
            provenance_refs=("falsifier:source",),
        )

        # The active WP504 claim explicitly requires fail-closed behavior when GRID work
        # budget is unavailable. A zero-total/zero-cell plan therefore may not select.
        self.assertEqual(proposal.status, "NO_ELIGIBLE_CANDIDATE")
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertEqual(proposal.as_dict()["effect_authority"], "NONE")


if __name__ == "__main__":
    unittest.main()
