from __future__ import annotations

import hashlib

from frankenstein2.canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityIdentity,
    EffectCallIntent,
)
from frankenstein2.canonical_single_authority_execution import (
    CanonicalAuthorityOutcomeUnknown,
    CanonicalEffectTransactionEvidence,
    CanonicalSingleAuthorityError,
    CanonicalTerminalDisposition,
    execute_once_through_canonical_authority,
)


AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="gschaidergabriel/clay-global-research-entity",
    commit_sha="2b68aad14bf7824d513b52898904909256e3522d",
    module_path="the artefact/clayverse/effects.py",
    source_blob_sha="4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
    state_schema="UnifiedDB/schema-6",
    api_version="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
)

INTENT = EffectCallIntent(
    return_id="return-1",
    binding_id="binding-1",
    invocation_id="invocation-1",
    tool_use_id="tool-1",
    delegation_id="delegation-1",
    child_identity_sha256="a" * 64,
)


def evidence(state: str = "VERIFIED", **changes: object) -> CanonicalEffectTransactionEvidence:
    values: dict[str, object] = {
        "authority": AUTHORITY,
        "effect_id": "effect-1",
        "final_journal_state": state,
        "outcome_sha256": hashlib.sha256(b"outcome").hexdigest(),
        "return_id": INTENT.return_id,
        "binding_id": INTENT.binding_id,
        "invocation_id": INTENT.invocation_id,
        "tool_use_id": INTENT.tool_use_id,
        "delegation_id": INTENT.delegation_id,
        "child_identity_sha256": INTENT.child_identity_sha256,
    }
    values.update(changes)
    return CanonicalEffectTransactionEvidence(**values)  # type: ignore[arg-type]


def expect_error(exc_type: type[BaseException], token: str, fn) -> None:
    try:
        fn()
    except exc_type as exc:
        assert token in str(exc), (token, str(exc))
    else:
        raise AssertionError(f"expected {exc_type.__name__}: {token}")


def test_verified_transaction_is_one_authority_call_and_never_second_dispatch() -> None:
    calls: list[str] = []

    def canonical_transaction(intent: EffectCallIntent) -> CanonicalEffectTransactionEvidence:
        assert intent == INTENT
        calls.append("canonical-effectgate-transaction")
        return evidence("VERIFIED")

    result = execute_once_through_canonical_authority(
        INTENT,
        expected_authority=AUTHORITY,
        execute_transaction=canonical_transaction,
    )

    assert calls == ["canonical-effectgate-transaction"]
    assert result.authority_calls == 1
    assert result.second_executor_dispatch_permitted is False
    assert result.automatic_replay_permitted is False
    assert result.disposition is CanonicalTerminalDisposition.VERIFIED
    assert result.effect_id == "effect-1"


def test_all_bound_terminal_states_return_without_second_dispatch() -> None:
    expected = {
        "VERIFIED": CanonicalTerminalDisposition.VERIFIED,
        "DENIED": CanonicalTerminalDisposition.DENIED,
        "FAILED": CanonicalTerminalDisposition.FAILED,
        "STALE_OUTCOME": CanonicalTerminalDisposition.STALE,
        "UNKNOWN_AFTER_RESTART": CanonicalTerminalDisposition.UNKNOWN,
    }
    for state, disposition in expected.items():
        calls = 0

        def canonical_transaction(
            _intent: EffectCallIntent,
            *,
            _state: str = state,
        ) -> CanonicalEffectTransactionEvidence:
            nonlocal calls
            calls += 1
            return evidence(_state)

        result = execute_once_through_canonical_authority(
            INTENT,
            expected_authority=AUTHORITY,
            execute_transaction=canonical_transaction,
        )
        assert calls == 1
        assert result.disposition is disposition
        assert result.second_executor_dispatch_permitted is False
        assert result.automatic_replay_permitted is False


def test_pending_after_normal_return_fails_closed() -> None:
    expect_error(
        CanonicalSingleAuthorityError,
        "PENDING_AFTER_CANONICAL_RETURN_TOPOLOGY_MISMATCH",
        lambda: execute_once_through_canonical_authority(
            INTENT,
            expected_authority=AUTHORITY,
            execute_transaction=lambda _intent: evidence("PENDING"),
        ),
    )


def test_unknown_journal_state_fails_closed() -> None:
    expect_error(
        CanonicalSingleAuthorityError,
        "UNKNOWN_CANONICAL_JOURNAL_STATE",
        lambda: execute_once_through_canonical_authority(
            INTENT,
            expected_authority=AUTHORITY,
            execute_transaction=lambda _intent: evidence("MAGIC_SUCCESS"),
        ),
    )


def test_authority_identity_mismatch_fails_closed() -> None:
    wrong = CanonicalEffectAuthorityIdentity(
        repository=AUTHORITY.repository,
        commit_sha="1" * 40,
        module_path=AUTHORITY.module_path,
        source_blob_sha=AUTHORITY.source_blob_sha,
        state_schema=AUTHORITY.state_schema,
        api_version=AUTHORITY.api_version,
    )
    expect_error(
        CanonicalSingleAuthorityError,
        "AUTHORITY_IDENTITY_MISMATCH",
        lambda: execute_once_through_canonical_authority(
            INTENT,
            expected_authority=AUTHORITY,
            execute_transaction=lambda _intent: evidence(authority=wrong),
        ),
    )


def test_exact_f2_call_identity_mismatch_fails_closed() -> None:
    expect_error(
        CanonicalSingleAuthorityError,
        "INVOCATION_ID_MISMATCH",
        lambda: execute_once_through_canonical_authority(
            INTENT,
            expected_authority=AUTHORITY,
            execute_transaction=lambda _intent: evidence(invocation_id="other-call"),
        ),
    )


def test_transaction_exception_is_unknown_and_never_replayable() -> None:
    calls = 0

    def uncertain(_intent: EffectCallIntent) -> CanonicalEffectTransactionEvidence:
        nonlocal calls
        calls += 1
        raise TimeoutError("connection lost after unknown boundary")

    try:
        execute_once_through_canonical_authority(
            INTENT,
            expected_authority=AUTHORITY,
            execute_transaction=uncertain,
        )
    except CanonicalAuthorityOutcomeUnknown as exc:
        assert "NO_AUTOMATIC_REPLAY" in str(exc)
        assert exc.replay_permitted is False
    else:
        raise AssertionError("expected canonical transaction outcome to remain UNKNOWN")
    assert calls == 1


def test_invalid_outcome_digest_is_rejected_before_acceptance() -> None:
    expect_error(
        CanonicalSingleAuthorityError,
        "INVALID_OUTCOME_SHA256",
        lambda: evidence(outcome_sha256="not-a-sha256"),
    )


def main() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} canonical single-authority topology falsifiers")


if __name__ == "__main__":
    main()
