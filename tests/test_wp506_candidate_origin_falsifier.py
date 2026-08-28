import unittest

from frankenstein2.gwt_workspace import (
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def policy(*, max_selected=2, max_cost=10):
    return SelectionPolicy(
        policy_id="policy:wp506-review",
        generation=1,
        max_selected_candidates=max_selected,
        max_total_cost_units=max_cost,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=0,
        information_gain_weight=1,
        cost_weight=0,
    )


def candidate(candidate_id, payload_ref, provenance_refs):
    return WorkspaceCandidate(
        candidate_id=candidate_id,
        payload_ref=payload_ref,
        epistemic_class="OBSERVED_EVIDENCE",
        provenance_refs=tuple(provenance_refs),
        salience_micros=900_000,
        goal_relevance_micros=800_000,
        uncertainty_micros=0,
        information_gain_micros=700_000,
        estimated_cost_units=1,
    )


def select(candidates):
    return build_workspace_selection(
        selection_id="selection:wp506-review",
        cycle_id="cycle:current",
        generation=1,
        frame_id="frame:current",
        frame_generation=3,
        frame_sha256=HASH_A,
        grid_plan_id="grid:current",
        grid_plan_generation=7,
        grid_plan_sha256=HASH_B,
        policy=policy(),
        candidates=tuple(candidates),
    )


class WP506CandidateOriginFalsifier(unittest.TestCase):
    """REVIEW_ONLY: expected to fail until candidate-origin admission is explicit."""

    def test_foreign_candidate_cannot_enter_only_by_caller_supplied_provenance_text(self):
        foreign = candidate(
            "candidate:foreign",
            "payload:foreign",
            ("receipt:unbound-foreign-run",),
        )

        # A valid outer frame/GRID-plan digest does not prove that this candidate was
        # produced by that cycle. The selector must fail closed unless candidate origin
        # is bound to an admitted CellInput/CellOutput (or equivalent producer receipt).
        with self.assertRaises(GwtWorkspaceError):
            select((foreign,))

    def test_alias_ids_cannot_amplify_one_payload_source_inside_selection_budget(self):
        alias_a = candidate(
            "candidate:alias-a",
            "payload:same",
            ("receipt:same-producer",),
        )
        alias_b = candidate(
            "candidate:alias-b",
            "payload:same",
            ("receipt:same-producer",),
        )

        # Distinct candidate IDs must not let one producer/payload consume two selection
        # slots before broadcast. Reject or prove weight-neutral alias handling.
        with self.assertRaises(GwtWorkspaceError):
            select((alias_a, alias_b))


if __name__ == "__main__":
    unittest.main()
