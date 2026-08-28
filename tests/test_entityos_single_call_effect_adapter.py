from __future__ import annotations

import unittest

from frankenstein2.canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityIdentity,
    EffectCallIntent,
)
from frankenstein2.effect_request_identity import EffectRequestIdentity
from frankenstein2.entityos_single_call_effect_adapter import (
    EntityOSSingleCallAdapterError,
    ExactJournalObservation,
    observe_single_call_entityos_transaction,
    run_and_observe_single_call_entityos_transaction,
    submit_single_call_entityos_transaction,
)


AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="gschaidergabriel/clay-global-research-entity",
    commit_sha="2b68aad14bf7824d513b52898904909256e3522d",
    module_path="the artefact/clayverse/effects.py",
    source_blob_sha="4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
    state_schema="6",
    api_version="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
)
OTHER_AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="example/other",
    commit_sha="1" * 40,
    module_path="other/effects.py",
    source_blob_sha="2" * 40,
    state_schema="1",
    api_version="OTHER/v1",
)
CHILD_A = "a" * 64
CHILD_B = "b" * 64
JOURNAL_SHA_A = "c" * 64
JOURNAL_SHA_B = "d" * 64


def request(label: str) -> EffectRequestIdentity:
    return EffectRequestIdentity(
        user_id="user-1",
        session_id="same-session",
        capability="state.noop",
        target=f"noop-{label}",
        argv=None,
        expected_generation=7,
    )


def intent(label: str) -> EffectCallIntent:
    return EffectCallIntent(
        return_id=None,
        binding_id=f"binding-{label}",
        invocation_id=f"invocation-{label}",
        tool_use_id=f"tool-{label}",
        delegation_id=f"delegation-{label}",
        child_identity_sha256=CHILD_A if label == "A" else CHILD_B,
        request=request(label),
    )


class FakeBoundEntityOSPort:
    """Deterministic no-real-effect port; models the exact single-call contract only."""

    def __init__(self, *, authority=AUTHORITY) -> None:
        self._authority = authority
        self.execute_calls: list[str] = []
        self.observe_calls: list[str] = []
        self._journal: dict[str, ExactJournalObservation] = {}

    @property
    def authority_identity(self):
        return self._authority

    def execute_once(self, semantic_request: EffectRequestIdentity):
        label = semantic_request.target.rsplit("-", 1)[-1]
        self.execute_calls.append(semantic_request.sha256())
        effect_id = f"canonical-effect-{label}"
        evidence_sha = JOURNAL_SHA_A if label == "A" else JOURNAL_SHA_B
        self._journal[effect_id] = ExactJournalObservation(
            effect_id=effect_id,
            status="VERIFIED",
            evidence_ref=f"effects:{effect_id}:VERIFIED",
            evidence_sha256=evidence_sha,
        )
        return effect_id, {
            "ok": True,
            "target": semantic_request.target,
            "boundary": "internal",
        }

    def observe_exact(self, effect_id: str):
        self.observe_calls.append(effect_id)
        return self._journal[effect_id]


class RaisingPort(FakeBoundEntityOSPort):
    def execute_once(self, semantic_request: EffectRequestIdentity):
        self.execute_calls.append(semantic_request.sha256())
        raise RuntimeError("transport disappeared after entry")


class EntityOSSingleCallEffectAdapterTests(unittest.TestCase):
    def test_one_logical_request_invokes_canonical_transaction_exactly_once(self) -> None:
        port = FakeBoundEntityOSPort()
        call = intent("A")
        observed = run_and_observe_single_call_entityos_transaction(
            call,
            expected_authority=AUTHORITY,
            port=port,
        )
        self.assertEqual(port.execute_calls, [call.request_sha256])
        self.assertEqual(port.observe_calls, ["canonical-effect-A"])
        self.assertEqual(observed.submission.effect_id, "canonical-effect-A")
        self.assertEqual(observed.submission.request_sha256, call.request_sha256)
        self.assertTrue(observed.verified)

    def test_overlapping_ab_identity_survives_reverse_observation_order(self) -> None:
        port = FakeBoundEntityOSPort()
        a = intent("A")
        b = intent("B")
        submitted_a = submit_single_call_entityos_transaction(
            a, expected_authority=AUTHORITY, port=port
        )
        submitted_b = submit_single_call_entityos_transaction(
            b, expected_authority=AUTHORITY, port=port
        )

        # Observe B then A. The adapter must use each returned effect_id directly;
        # observation order must not alter request/effect bijection.
        observed_b = observe_single_call_entityos_transaction(
            submitted_b, request=b.request, port=port
        )
        observed_a = observe_single_call_entityos_transaction(
            submitted_a, request=a.request, port=port
        )

        self.assertEqual(port.execute_calls, [a.request_sha256, b.request_sha256])
        self.assertEqual(port.observe_calls, ["canonical-effect-B", "canonical-effect-A"])
        self.assertEqual(observed_a.submission.request_sha256, a.request_sha256)
        self.assertEqual(observed_b.submission.request_sha256, b.request_sha256)
        self.assertEqual(observed_a.submission.effect_id, "canonical-effect-A")
        self.assertEqual(observed_b.submission.effect_id, "canonical-effect-B")
        self.assertNotEqual(a.request_sha256, b.request_sha256)

    def test_swapping_request_digest_fails_without_second_dispatch(self) -> None:
        port = FakeBoundEntityOSPort()
        a = intent("A")
        b = intent("B")
        submitted_a = submit_single_call_entityos_transaction(
            a, expected_authority=AUTHORITY, port=port
        )
        with self.assertRaisesRegex(
            EntityOSSingleCallAdapterError, "REQUEST_SHA256_MISMATCH"
        ):
            observe_single_call_entityos_transaction(
                submitted_a, request=b.request, port=port
            )
        self.assertEqual(port.execute_calls, [a.request_sha256])
        self.assertEqual(port.observe_calls, [])

    def test_journal_effect_id_substitution_fails_closed(self) -> None:
        class WrongObserverPort(FakeBoundEntityOSPort):
            def observe_exact(self, effect_id: str):
                self.observe_calls.append(effect_id)
                return ExactJournalObservation(
                    effect_id="canonical-effect-B",
                    status="VERIFIED",
                    evidence_ref="effects:canonical-effect-B:VERIFIED",
                    evidence_sha256=JOURNAL_SHA_B,
                )

        port = WrongObserverPort()
        a = intent("A")
        submitted = submit_single_call_entityos_transaction(
            a, expected_authority=AUTHORITY, port=port
        )
        with self.assertRaisesRegex(
            EntityOSSingleCallAdapterError, "JOURNAL_EFFECT_ID_MISMATCH"
        ):
            observe_single_call_entityos_transaction(
                submitted, request=a.request, port=port
            )
        self.assertEqual(port.execute_calls, [a.request_sha256])
        self.assertEqual(port.observe_calls, ["canonical-effect-A"])

    def test_authority_mismatch_stops_before_canonical_call(self) -> None:
        port = FakeBoundEntityOSPort(authority=OTHER_AUTHORITY)
        with self.assertRaisesRegex(
            EntityOSSingleCallAdapterError, "AUTHORITY_IDENTITY_MISMATCH"
        ):
            submit_single_call_entityos_transaction(
                intent("A"), expected_authority=AUTHORITY, port=port
            )
        self.assertEqual(port.execute_calls, [])
        self.assertEqual(port.observe_calls, [])

    def test_exception_after_transaction_entry_is_unknown_and_never_retried(self) -> None:
        port = RaisingPort()
        call = intent("A")
        with self.assertRaisesRegex(
            EntityOSSingleCallAdapterError,
            "ENTITYOS_TRANSACTION_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY",
        ):
            submit_single_call_entityos_transaction(
                call, expected_authority=AUTHORITY, port=port
            )
        self.assertEqual(port.execute_calls, [call.request_sha256])
        self.assertEqual(port.observe_calls, [])

    def test_unknown_after_restart_is_observed_not_replayed(self) -> None:
        port = FakeBoundEntityOSPort()
        call = intent("A")
        submitted = submit_single_call_entityos_transaction(
            call, expected_authority=AUTHORITY, port=port
        )
        port._journal[submitted.effect_id] = ExactJournalObservation(
            effect_id=submitted.effect_id,
            status="UNKNOWN_AFTER_RESTART",
            evidence_ref=f"effects:{submitted.effect_id}:UNKNOWN_AFTER_RESTART",
            evidence_sha256=JOURNAL_SHA_A,
        )
        observed = observe_single_call_entityos_transaction(
            submitted, request=call.request, port=port
        )
        self.assertFalse(observed.verified)
        self.assertTrue(observed.final)
        self.assertTrue(observed.replay_forbidden)
        self.assertEqual(port.execute_calls, [call.request_sha256])


if __name__ == "__main__":
    unittest.main(verbosity=2)
