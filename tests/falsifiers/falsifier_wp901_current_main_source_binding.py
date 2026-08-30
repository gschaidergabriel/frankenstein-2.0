#!/usr/bin/env python3
"""REVIEW_ONLY exact-current WP901 source-binding counterexample."""
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
        evidence_id="current-main-self-attested-evidence",
        source_checkpoint_id="checkpoint-not-loaded-from-wp206",
        source_checkpoint_generation=77,
        source_checkpoint_sha256=SHA_A,
        whole_loop_seal_id="seal-not-loaded-from-wp900",
        whole_loop_seal_sha256=SHA_B,
        outcome_status=NO_EFFECT,
        outcome_sha256=SHA_A,
        unfinished_work_refs=("work:self-attested-only",),
        provenance_refs=("review:current-main-source-binding",),
    )
    plan = plan_restart_continuation(
        evidence,
        plan_id="current-main-self-attested-plan",
        expected_evidence_sha256=evidence.sha256(),
        expected_checkpoint_id=evidence.source_checkpoint_id,
        expected_checkpoint_generation=evidence.source_checkpoint_generation,
        expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
        expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
        expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
    )
    assert plan.disposition == CONTINUE_UNFINISHED
    assert plan.source_checkpoint_id == "checkpoint-not-loaded-from-wp206"
    assert plan.whole_loop_seal_id == "seal-not-loaded-from-wp900"
    print({
        "result": "POSITIVE_CURRENT_MAIN_SELF_ATTESTED_SOURCE_IDENTITY_ACCEPTED",
        "base_main": "d317d05da76d02eb7e5be71af57108a32287fc23",
        "plan_sha256": plan.sha256(),
        "scope": "REVIEW_ONLY_REPOSITORY_COMPONENT_COUNTEREXAMPLE",
        "runtime_credit": 0,
        "effect_credit": 0,
        "whole_system_credit": 0,
    })


if __name__ == "__main__":
    main()
