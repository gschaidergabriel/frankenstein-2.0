from __future__ import annotations

import hashlib
import json
import math
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


FRAME_SHA = "1" * 64
POLICY_SHA = "2" * 64
PUBLIC_OBSERVATION_REF = "wp804:public-observation:identical"
PUBLIC_OBSERVATION_SHA256 = hashlib.sha256(b"wp804-identical-public-observation").hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized_information_gain_micros(outcomes_by_alternative: dict[str, str]) -> int:
    """Uniform-prior Shannon information gain normalized into the existing 0..1e6 ABI."""
    n = len(outcomes_by_alternative)
    if n < 2:
        raise ValueError("at least two compatible alternatives are required")
    counts: dict[str, int] = {}
    for outcome in outcomes_by_alternative.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    prior_entropy = math.log2(n)
    posterior_entropy = sum((count / n) * math.log2(count) for count in counts.values())
    gain = (prior_entropy - posterior_entropy) / prior_entropy
    return round(gain * 1_000_000)


def make_state(case_id: str, goal_ids: tuple[str, ...]):
    generation = 1
    return create_hyperposition(
        hyperposition_id=f"hyper:wp804:{case_id}",
        generation=generation,
        alternatives=tuple(
            Alternative(
                alternative_id=goal_id,
                proposition_ref=f"candidate-goal:{goal_id}",
                generation=generation,
                epistemic_status=EpistemicStatus.UNKNOWN,
                provenance_refs=(PUBLIC_OBSERVATION_REF, f"sha256:{PUBLIC_OBSERVATION_SHA256}"),
                uncertainty_micros=1_000_000,
            )
            for goal_id in goal_ids
        ),
        provenance_refs=(PUBLIC_OBSERVATION_REF, f"sha256:{PUBLIC_OBSERVATION_SHA256}"),
        policy_ref="wp804:compatible-goal-set-only",
    )


def grid_plan():
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role:{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=10,
            max_reentry_depth=1,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid:wp804:e4",
        cycle_id="cycle:wp804:e4",
        generation=1,
        frame_id="frame:wp804:e4",
        frame_generation=1,
        frame_sha256=FRAME_SHA,
        policy_id="policy:wp804:e4",
        policy_generation=1,
        policy_sha256=POLICY_SHA,
        cells=cells,
        max_total_work_units=20,
        provenance_refs=("trigger6:e4:matched-ablation",),
    )


def baseline_from_binary_abstain(decision: str) -> str | None:
    if decision != "ABSTAIN":
        raise ValueError("this ablation only covers the WP804 ambiguous boundary")
    return None


def derive_candidates(state, bound_probe_outcome_model: dict[str, dict[str, str]] | None):
    if bound_probe_outcome_model is None:
        return "MISSING_BOUND_PROBE_OUTCOME_MODEL", ()

    alternative_ids = tuple(item.alternative_id for item in state.alternatives)
    expected = set(alternative_ids)
    model_sha = canonical_sha256(bound_probe_outcome_model)
    provenance = (
        PUBLIC_OBSERVATION_REF,
        f"probe-outcome-model:sha256:{model_sha}",
        "trigger6:e4:synthetic-public-model",
    )
    candidates = []
    for probe_id in sorted(bound_probe_outcome_model):
        outcomes = bound_probe_outcome_model[probe_id]
        if set(outcomes) != expected:
            raise ValueError("probe outcome model must bind exactly the compatible alternative set")
        gain = normalized_information_gain_micros(outcomes)
        discriminator = create_discriminator_candidate(
            state=state,
            expected_generation=state.generation,
            expected_state_sha256=state.sha256(),
            discriminator_id=f"disc:{state.hyperposition_id}:{probe_id}",
            target_alternative_ids=alternative_ids,
            evidence_need_ref=f"evidence-need:{probe_id}",
            expected_information_gain_micros=gain,
            estimated_cost_micros=100_000,
            provenance_refs=provenance,
        )
        candidates.append(
            EpistemicActionCandidate(
                candidate_id=f"candidate:{probe_id}",
                action_ref=f"action:{probe_id}",
                cell_id="G1",
                work_units_requested=1,
                discriminator=discriminator,
                provenance_refs=provenance,
            )
        )
    return "BOUND_MODEL_PRESENT", tuple(candidates)


def select_probe(state, candidates):
    plan = grid_plan()
    return select_epistemic_action(
        proposal_id=f"proposal:{state.hyperposition_id}",
        state=state,
        expected_hyperposition_generation=state.generation,
        expected_hyperposition_sha256=state.sha256(),
        plan=plan,
        expected_plan_generation=plan.generation,
        expected_plan_sha256=plan.sha256(),
        candidates=candidates,
        provenance_refs=("trigger6:e4:matched-ablation",),
    )


class Trigger6WP804GoalProbeAblation(unittest.TestCase):
    def setUp(self) -> None:
        self.case_a = make_state("case-a", ("goal:a1", "goal:a2", "goal:a3", "goal:a4"))
        self.case_b = make_state("case-b", ("goal:b1", "goal:b2", "goal:b3", "goal:b4"))
        self.model_a = {
            "probe-color": {
                "goal:a1": "red", "goal:a2": "red", "goal:a3": "blue", "goal:a4": "blue"
            },
            "probe-shape": {
                "goal:a1": "round", "goal:a2": "round", "goal:a3": "round", "goal:a4": "round"
            },
        }
        self.model_b = {
            "probe-color": {
                "goal:b1": "red", "goal:b2": "red", "goal:b3": "red", "goal:b4": "red"
            },
            "probe-shape": {
                "goal:b1": "round", "goal:b2": "round", "goal:b3": "square", "goal:b4": "square"
            },
        }

    def test_binary_abstain_baseline_cannot_distinguish_matched_cases(self) -> None:
        self.assertIsNone(baseline_from_binary_abstain("ABSTAIN"))
        self.assertIsNone(baseline_from_binary_abstain("ABSTAIN"))

    def test_goal_set_without_bound_outcome_model_is_not_causally_sufficient(self) -> None:
        status_a, candidates_a = derive_candidates(self.case_a, None)
        status_b, candidates_b = derive_candidates(self.case_b, None)
        self.assertEqual(status_a, "MISSING_BOUND_PROBE_OUTCOME_MODEL")
        self.assertEqual(status_b, "MISSING_BOUND_PROBE_OUTCOME_MODEL")
        self.assertEqual(candidates_a, ())
        self.assertEqual(candidates_b, ())

    def test_bound_outcome_model_yields_different_unique_information_probes(self) -> None:
        status_a, candidates_a = derive_candidates(self.case_a, self.model_a)
        status_b, candidates_b = derive_candidates(self.case_b, self.model_b)
        self.assertEqual(status_a, "BOUND_MODEL_PRESENT")
        self.assertEqual(status_b, "BOUND_MODEL_PRESENT")

        by_action_a = {item.action_ref: item.expected_information_gain_micros for item in candidates_a}
        by_action_b = {item.action_ref: item.expected_information_gain_micros for item in candidates_b}
        self.assertEqual(by_action_a["action:probe-color"], 500_000)
        self.assertEqual(by_action_a["action:probe-shape"], 0)
        self.assertEqual(by_action_b["action:probe-color"], 0)
        self.assertEqual(by_action_b["action:probe-shape"], 500_000)

        proposal_a = select_probe(self.case_a, candidates_a)
        proposal_b = select_probe(self.case_b, candidates_b)
        self.assertEqual(proposal_a.selected_action_ref, "action:probe-color")
        self.assertEqual(proposal_b.selected_action_ref, "action:probe-shape")
        self.assertEqual(proposal_a.tied_candidate_ids, ("candidate:probe-color",))
        self.assertEqual(proposal_b.tied_candidate_ids, ("candidate:probe-shape",))
        self.assertEqual(proposal_a.as_dict()["execution_authority"], "NONE")
        self.assertEqual(proposal_b.as_dict()["effect_authority"], "NONE")

    def test_outcome_model_must_bind_exact_compatible_goal_set(self) -> None:
        bad = dict(self.model_a)
        bad["probe-color"] = dict(bad["probe-color"])
        bad["probe-color"].pop("goal:a4")
        with self.assertRaisesRegex(ValueError, "bind exactly"):
            derive_candidates(self.case_a, bad)


if __name__ == "__main__":
    unittest.main()
