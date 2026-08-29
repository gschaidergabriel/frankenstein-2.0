"""Trigger-6 WP805 matching-validity falsifier.

Research-only executable counterexample. It imports the canonical F2 WP800/WP805 source
and demonstrates two contract-level gaps without mutating product source or granting runtime,
GRID/GWT/J-Space, effect, cognition-superiority, completion or whole-system credit.
"""
from __future__ import annotations

import hashlib

from frankenstein2.cognitive_microworld import (
    ACTION_REQUEST_SCHEMA,
    FIXTURE_SCHEMA,
    OBSERVATION_SCHEMA,
    ActionSpec,
    MicroWorldFixture,
    ObservationView,
    WorldNode,
)
from frankenstein2.cognitive_transfer_recovery_benchmark import (
    CHECKPOINT_RESUME,
    COLD_RESTART,
    POLICY_STATE_SCHEMA,
    EvaluatorRunMeasurement,
    MatchedRecoveryComparison,
    PublicPolicyState,
    RecoveryCheckpoint,
    TransferCase,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def obs(*, step: int, episode: str = "ep-target", episode_generation: int = 7) -> ObservationView:
    return ObservationView(
        schema=OBSERVATION_SCHEMA,
        episode_id=episode,
        episode_generation=episode_generation,
        fixture_id="target-fixture",
        fixture_generation=3,
        public_fixture_sha256=h("target-public"),
        step_index=step,
        observation_ref=f"obs:{step}",
        observation_sha256=h(f"obs:{step}"),
        available_action_ids=("go",),
        terminal=False,
    )


def reproduce_g1_unbound_matched_start() -> dict[str, object]:
    case = TransferCase.create(
        source_fixture_id="source-fixture",
        source_fixture_generation=1,
        source_holdout_set_id="source-holdout",
        source_public_fixture_sha256=h("source-public"),
        target_fixture_id="target-fixture",
        target_fixture_generation=3,
        target_holdout_set_id="target-holdout",
        target_public_fixture_sha256=h("target-public"),
        episode_family_id="family-1",
        action_budget=8,
    )
    policy = PublicPolicyState(
        POLICY_STATE_SCHEMA,
        "policy:source",
        1,
        "source-fixture",
        "source-holdout",
        h("source-public"),
        h("policy-artifact"),
        ("go",),
        8,
    )
    cold_public_start = obs(step=0, episode="ep-cold")
    resume_public_start = obs(step=2, episode="ep-resume")
    assert cold_public_start.sha256() != resume_public_start.sha256()
    checkpoint = RecoveryCheckpoint.seal(
        case=case,
        policy=policy,
        observation=resume_public_start,
        action_history_sha256=h("resume-history"),
    )
    cold = EvaluatorRunMeasurement.measure_run(
        run_id="cold",
        mode=COLD_RESTART,
        case=case,
        target_fixture_sha256=h("hidden-target-fixture"),
        checkpoint=None,
        actions_executed=6,
        replayed_steps=2,
        repeated_work_steps=2,
        final_evaluator_score=4,
        terminal=True,
    )
    resume = EvaluatorRunMeasurement.measure_run(
        run_id="resume",
        mode=CHECKPOINT_RESUME,
        case=case,
        target_fixture_sha256=h("hidden-target-fixture"),
        checkpoint=checkpoint,
        actions_executed=4,
        replayed_steps=0,
        repeated_work_steps=0,
        final_evaluator_score=5,
        terminal=True,
    )
    pair = MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=resume)
    assert "start_observation_sha256" not in cold.as_dict()
    assert "start_observation_sha256" not in resume.as_dict()
    return {
        "reproduced": True,
        "cold_public_start_sha256": cold_public_start.sha256(),
        "resume_public_start_sha256": resume_public_start.sha256(),
        "starts_differ": cold_public_start.sha256() != resume_public_start.sha256(),
        "comparison_created": pair.comparison_id,
        "contract_has_start_observation_binding": False,
    }


def simple_fixture(*, fixture_id: str, holdout: str, public_tag: str) -> MicroWorldFixture:
    action = ActionSpec("go", f"payload:{public_tag}", h(f"payload:{public_tag}"))
    node = WorldNode(
        "n0",
        f"public:{public_tag}",
        h(f"public:{public_tag}"),
        f"hidden:{public_tag}",
        h(f"hidden:{public_tag}"),
        True,
        1,
    )
    return MicroWorldFixture(
        schema=FIXTURE_SCHEMA,
        fixture_id=fixture_id,
        generation=1,
        holdout_set_id=holdout,
        initial_node_id="n0",
        max_steps=1,
        actions=(action,),
        nodes=(node,),
        transitions=(),
        evidence_source_family="same-evidence-source-family",
        primary_source_ids=("source-1",),
        donor_path_family="same-donor-path-family",
        method_family="same-method-family",
    )


def reproduce_g3_structural_family_relabeling() -> dict[str, object]:
    source = simple_fixture(fixture_id="source-structural", holdout="holdout-A", public_tag="source")
    target = simple_fixture(fixture_id="target-structural", holdout="holdout-B", public_tag="target")
    assert source.evidence_source_family == target.evidence_source_family
    assert source.donor_path_family == target.donor_path_family
    assert source.method_family == target.method_family
    case = TransferCase.create(
        source_fixture_id=source.fixture_id,
        source_fixture_generation=source.generation,
        source_holdout_set_id=source.holdout_set_id,
        source_public_fixture_sha256=source.public_sha256(),
        target_fixture_id=target.fixture_id,
        target_fixture_generation=target.generation,
        target_holdout_set_id=target.holdout_set_id,
        target_public_fixture_sha256=target.public_sha256(),
        episode_family_id="same-structural-family-test",
        action_budget=1,
    )
    return {
        "reproduced": True,
        "transfer_case_created": case.case_id,
        "holdout_labels_differ": source.holdout_set_id != target.holdout_set_id,
        "evidence_source_family_equal": source.evidence_source_family == target.evidence_source_family,
        "donor_path_family_equal": source.donor_path_family == target.donor_path_family,
        "method_family_equal": source.method_family == target.method_family,
        "contract_binds_structural_family_vector": False,
    }


if __name__ == "__main__":
    print(reproduce_g1_unbound_matched_start())
    print(reproduce_g3_structural_family_relabeling())
