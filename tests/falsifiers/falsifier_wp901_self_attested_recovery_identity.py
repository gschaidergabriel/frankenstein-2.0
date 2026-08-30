#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for F2-WP-901 generation 1.

This counterexample does not mutate canonical WP901 semantics. It asks whether the public
planner independently proves that its checkpoint and WP900 seal identities came from actual
WP206/WP900 objects, or merely compares caller-supplied identity strings against the same
caller-constructed evidence envelope.

A positive reproduction means arbitrary well-formed ids/digests can be self-consistently
supplied twice and still produce a continuation candidate. That is source-binding negative
evidence only; it is not runtime/effect/whole-system evidence.
"""
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
    plan_restart_continuation,
)
from frankenstein2.whole_persistent_loop import NO_EFFECT

SHA_A = "a" * 64
SHA_B = "b" * 64


def main() -> None:
    evidence = PersistedRestartEvidence(
        evidence_id="review-forged-recovery-evidence",
        source_checkpoint_id="checkpoint-never-loaded-from-wp206",
        source_checkpoint_generation=77,
        source_checkpoint_sha256=SHA_A,
        whole_loop_seal_id="seal-never-loaded-from-wp900",
        whole_loop_seal_sha256=SHA_B,
        outcome_status=NO_EFFECT,
        outcome_sha256=SHA_A,
        unfinished_work_refs=("work:self-attested-only",),
        provenance_refs=("review:self-attested-counterexample",),
    )

    plan = plan_restart_continuation(
        evidence,
        plan_id="review-self-attested-plan",
        expected_evidence_sha256=evidence.sha256(),
        expected_checkpoint_id=evidence.source_checkpoint_id,
        expected_checkpoint_generation=evidence.source_checkpoint_generation,
        expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
        expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
        expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
    )

    assert plan.disposition == CONTINUE_UNFINISHED
    assert plan.source_checkpoint_id == "checkpoint-never-loaded-from-wp206"
    assert plan.whole_loop_seal_id == "seal-never-loaded-from-wp900"
    assert plan.continuation_refs == ("work:self-attested-only",)
    assert plan.as_dict()["scheduler_authority"] == "NONE"
    assert plan.as_dict()["effect_authority"] == "NONE"

    print(
        {
            "result": "POSITIVE_SELF_ATTESTED_CHECKPOINT_AND_WP900_IDENTITY_ACCEPTED",
            "plan_sha256": plan.sha256(),
            "scope": "REVIEW_ONLY_REPOSITORY_COMPONENT_COUNTEREXAMPLE",
            "runtime_credit": 0,
            "effect_credit": 0,
            "whole_system_credit": 0,
        }
    )


if __name__ == "__main__":
    main()
