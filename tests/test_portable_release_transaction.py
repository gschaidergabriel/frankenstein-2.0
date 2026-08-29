from dataclasses import replace

import pytest

from frankenstein2.portable_release_transaction import (
    APPLIED,
    EVIDENCE_SCOPE,
    FAILED,
    INSTALL,
    ROLLBACK,
    ROLLED_BACK,
    UPDATE,
    PortableReleaseTransactionError,
    ReleaseIdentity,
    StateLineage,
    TransactionRequest,
    compile_transaction,
    simulate_hostile_twin_transaction,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


def release(name, digest):
    return ReleaseIdentity.create(release_id=name, zip_sha256=digest)


def state(generation, digest, lineage="canonical-state"):
    return StateLineage.create(lineage_id=lineage, generation=generation, state_digest=digest)


def test_fresh_install_is_deterministic_and_component_scoped():
    req = TransactionRequest.create(
        operation=INSTALL,
        target_release=release("f2-1.0.0", A),
        expected_result_state=state(0, B),
    )
    one = compile_transaction(req)
    two = compile_transaction(req)
    assert one == two
    receipt = simulate_hostile_twin_transaction(one)
    assert receipt.outcome == APPLIED
    assert receipt.final_release == req.target_release
    assert receipt.final_state == req.expected_result_state
    assert receipt.evidence_scope == EVIDENCE_SCOPE
    assert receipt.physical_target_credit == receipt.runtime_credit == receipt.completion_credit == 0


def test_update_requires_monotonic_same_lineage():
    cur_release = release("f2-1.0.0", A)
    cur_state = state(7, B)
    target = release("f2-1.1.0", C)
    req = TransactionRequest.create(
        operation=UPDATE,
        target_release=target,
        current_release=cur_release,
        current_state=cur_state,
        expected_result_state=state(8, D),
    )
    assert simulate_hostile_twin_transaction(compile_transaction(req)).outcome == APPLIED
    with pytest.raises(PortableReleaseTransactionError, match="advance exactly once"):
        TransactionRequest.create(operation=UPDATE, target_release=target,
                                  current_release=cur_release, current_state=cur_state,
                                  expected_result_state=state(9, D))
    with pytest.raises(PortableReleaseTransactionError, match="lineage_id"):
        TransactionRequest.create(operation=UPDATE, target_release=target,
                                  current_release=cur_release, current_state=cur_state,
                                  expected_result_state=state(8, D, "other"))


def test_explicit_rollback_restores_content_without_generation_rewind():
    old_release = release("f2-1.0.0", A)
    cur_release = release("f2-1.1.0", C)
    old_state = state(4, B)
    cur_state = state(5, D)
    req = TransactionRequest.create(
        operation=ROLLBACK,
        target_release=old_release,
        current_release=cur_release,
        current_state=cur_state,
        rollback_source_release=old_release,
        rollback_source_state=old_state,
        expected_result_state=state(6, B),
    )
    receipt = simulate_hostile_twin_transaction(compile_transaction(req))
    assert receipt.outcome == APPLIED
    assert receipt.final_state.generation == 6
    assert receipt.final_state.state_digest == old_state.state_digest
    with pytest.raises(PortableReleaseTransactionError, match="restore exact source"):
        TransactionRequest.create(operation=ROLLBACK, target_release=old_release,
                                  current_release=cur_release, current_state=cur_state,
                                  rollback_source_release=old_release, rollback_source_state=old_state,
                                  expected_result_state=state(6, E))


def test_failure_paths_never_invent_success_or_predecessor():
    cur_release = release("f2-1.0.0", A)
    cur_state = state(2, B)
    update = TransactionRequest.create(
        operation=UPDATE, target_release=release("f2-1.1.0", C),
        current_release=cur_release, current_state=cur_state,
        expected_result_state=state(3, D), failure_stage="MIGRATE",
    )
    receipt = simulate_hostile_twin_transaction(compile_transaction(update))
    assert receipt.outcome == FAILED
    assert receipt.final_release == cur_release and receipt.final_state == cur_state

    update_after_activation = replace(update, failure_stage="VERIFY")
    receipt = simulate_hostile_twin_transaction(compile_transaction(update_after_activation))
    assert receipt.outcome == ROLLED_BACK
    assert receipt.final_release == cur_release and receipt.final_state == cur_state

    install = TransactionRequest.create(
        operation=INSTALL, target_release=release("f2-1.0.0", A),
        expected_result_state=state(0, B), failure_stage="ACTIVATE",
    )
    receipt = simulate_hostile_twin_transaction(compile_transaction(install))
    assert receipt.outcome == FAILED
    assert receipt.final_release is None and receipt.final_state is None


@pytest.mark.parametrize("bad", ["UNKNOWN", "A" * 64, "a" * 63, "g" * 64, ""])
def test_release_digest_fails_closed(bad):
    with pytest.raises(PortableReleaseTransactionError, match="SHA-256"):
        release("bad", bad)


def test_plan_identity_tamper_and_rollback_source_fail_closed():
    req = TransactionRequest.create(operation=INSTALL, target_release=release("f2-1.0.0", A),
                                    expected_result_state=state(0, B))
    plan = compile_transaction(req)
    with pytest.raises(PortableReleaseTransactionError, match="identity binding"):
        replace(plan, request_digest=C)

    cur_release = release("f2-1.1.0", C)
    cur_state = state(5, D)
    with pytest.raises(PortableReleaseTransactionError, match="older generation"):
        TransactionRequest.create(operation=ROLLBACK, target_release=release("f2-1.0.0", A),
                                  current_release=cur_release, current_state=cur_state,
                                  rollback_source_release=release("f2-1.0.0", A),
                                  rollback_source_state=state(5, B), expected_result_state=state(6, B))
    with pytest.raises(PortableReleaseTransactionError, match="target must equal"):
        TransactionRequest.create(operation=ROLLBACK, target_release=release("f2-0.9.0", E),
                                  current_release=cur_release, current_state=cur_state,
                                  rollback_source_release=release("f2-1.0.0", A),
                                  rollback_source_state=state(4, B), expected_result_state=state(6, B))
