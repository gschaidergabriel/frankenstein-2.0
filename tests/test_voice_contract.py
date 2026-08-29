from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import (
    OUTCOME_ENDED,
    OUTCOME_ERROR,
    OUTCOME_INTERRUPTED,
    OUTCOME_RETURNED,
    OUTCOME_UNKNOWN,
    VOICE_CLASSIFICATION,
    VoiceContractError,
    VoiceIntent,
    VoiceOutcome,
    VoiceSessionCapsule,
    bind_voice_outcome,
)


class VoiceContractTests(unittest.TestCase):
    def root(self) -> CausalIdentity:
        return CausalIdentity(
            session_id="session-704",
            agent_id="frankenstein-2",
            task_id="task-704",
            turn_id="turn-input",
            causal_id="causal-input-704",
            generation=3,
        )

    def intent(self) -> VoiceIntent:
        return VoiceIntent.create(
            causal_identity=self.root(),
            input_ref="voice-input:704",
            input_sha256="a" * 64,
            provenance_refs=("source:user-voice-intent",),
        )

    def session(self) -> VoiceSessionCapsule:
        intent = self.intent()
        session_causal = intent.causal_identity.derive(
            causal_id="causal-voice-session-704",
            generation=4,
            turn_id="turn-voice-session",
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=session_causal,
            provenance_refs=("receipt:voice-session-open",),
        )

    def outcome(self, *, kind: str = OUTCOME_RETURNED, digest: str = "b" * 64) -> VoiceOutcome:
        session = self.session()
        outcome_causal = session.session_causal_identity.derive(
            causal_id="causal-voice-outcome-704",
            generation=5,
            turn_id="turn-voice-outcome",
        )
        return VoiceOutcome.create(
            session=session,
            outcome_causal_identity=outcome_causal,
            outcome_kind=kind,
            result_ref="voice-result:704",
            result_sha256=digest,
            provenance_refs=("receipt:voice-return",),
        )

    def test_happy_path_roundtrips_and_content_ids(self) -> None:
        intent = self.intent()
        session = self.session()
        outcome = self.outcome()
        self.assertEqual(VoiceIntent.from_mapping(intent.as_dict()), intent)
        self.assertEqual(VoiceSessionCapsule.from_mapping(session.as_dict()), session)
        self.assertEqual(VoiceOutcome.from_mapping(outcome.as_dict()), outcome)
        self.assertTrue(intent.intent_id.startswith("voice-intent:"))
        self.assertTrue(session.voice_session_id.startswith("voice-session:"))
        self.assertTrue(outcome.outcome_id.startswith("voice-outcome:"))

    def test_voice_stays_on_same_frankenstein_agent_identity(self) -> None:
        intent = self.intent()
        wrong = intent.causal_identity.derive(
            causal_id="causal-wrong-agent",
            generation=4,
            agent_id="voice-agent-2",
            turn_id="turn-wrong",
        )
        with self.assertRaises(VoiceContractError):
            VoiceSessionCapsule.create(
                intent=intent,
                session_causal_identity=wrong,
                provenance_refs=("receipt:wrong",),
            )

    def test_session_generation_must_advance(self) -> None:
        intent = self.intent()
        stale = intent.causal_identity.derive(
            causal_id="causal-stale",
            generation=intent.causal_identity.generation,
            turn_id="turn-stale",
        )
        with self.assertRaises(VoiceContractError):
            VoiceSessionCapsule.create(intent=intent, session_causal_identity=stale, provenance_refs=("receipt:stale",))

    def test_session_must_keep_causal_session_and_task(self) -> None:
        intent = self.intent()
        for field, value in (("session_id", "other-session"), ("task_id", "other-task")):
            wrong = intent.causal_identity.derive(
                causal_id=f"causal-wrong-{field}", generation=4, turn_id="turn-wrong", **{field: value}
            )
            with self.subTest(field=field):
                with self.assertRaises(VoiceContractError):
                    VoiceSessionCapsule.create(intent=intent, session_causal_identity=wrong, provenance_refs=("receipt:wrong",))

    def test_content_bound_ids_reject_tamper(self) -> None:
        intent = self.intent()
        session = self.session()
        outcome = self.outcome()
        with self.assertRaises(VoiceContractError):
            replace(intent, intent_id="voice-intent:" + "0" * 64)
        with self.assertRaises(VoiceContractError):
            replace(session, voice_session_id="voice-session:" + "0" * 64)
        with self.assertRaises(VoiceContractError):
            replace(outcome, outcome_id="voice-outcome:" + "0" * 64)

    def test_nested_dependency_digests_reject_tamper(self) -> None:
        with self.assertRaises(VoiceContractError):
            replace(self.intent(), causal_identity_sha256="0" * 64)
        with self.assertRaises(VoiceContractError):
            replace(self.session(), intent_sha256="0" * 64)
        with self.assertRaises(VoiceContractError):
            replace(self.outcome(), voice_session_sha256="0" * 64)

    def test_outcome_generation_and_lineage_must_advance(self) -> None:
        session = self.session()
        stale = session.session_causal_identity.derive(
            causal_id="causal-stale-outcome",
            generation=session.session_causal_identity.generation,
            turn_id="turn-stale-outcome",
        )
        with self.assertRaises(VoiceContractError):
            VoiceOutcome.create(
                session=session,
                outcome_causal_identity=stale,
                outcome_kind=OUTCOME_ENDED,
                result_ref=None,
                result_sha256=None,
                provenance_refs=("receipt:stale-outcome",),
            )

    def test_outcome_result_reference_is_atomic_pair(self) -> None:
        with self.assertRaises(VoiceContractError):
            replace(self.outcome(), result_sha256=None)
        with self.assertRaises(VoiceContractError):
            replace(self.outcome(), result_ref=None)

    def test_all_explicit_outcome_kinds_are_admitted_without_semantic_inference(self) -> None:
        for kind in (OUTCOME_RETURNED, OUTCOME_INTERRUPTED, OUTCOME_ENDED, OUTCOME_ERROR, OUTCOME_UNKNOWN):
            with self.subTest(kind=kind):
                outcome = self.outcome(kind=kind)
                self.assertEqual(outcome.outcome_kind, kind)
        session = self.session()
        causal = session.session_causal_identity.derive(
            causal_id="causal-unknown-no-result", generation=5, turn_id="turn-unknown"
        )
        unknown = VoiceOutcome.create(
            session=session,
            outcome_causal_identity=causal,
            outcome_kind=OUTCOME_UNKNOWN,
            result_ref=None,
            result_sha256=None,
            provenance_refs=("receipt:unknown",),
        )
        self.assertIsNone(unknown.result_ref)

    def test_unadmitted_outcome_kind_fails_closed(self) -> None:
        session = self.session()
        causal = session.session_causal_identity.derive(
            causal_id="causal-fake-success", generation=5, turn_id="turn-fake"
        )
        with self.assertRaises(VoiceContractError):
            VoiceOutcome.create(
                session=session,
                outcome_causal_identity=causal,
                outcome_kind="SYSTEM_COMPLETE",
                result_ref=None,
                result_sha256=None,
                provenance_refs=("receipt:fake",),
            )

    def test_bind_outcome_requires_exact_session(self) -> None:
        candidate = self.outcome()
        other_intent = VoiceIntent.create(
            causal_identity=CausalIdentity(
                session_id="session-other", agent_id="frankenstein-2", task_id="task-other",
                turn_id="turn-other", causal_id="causal-other", generation=1,
            ),
            input_ref="voice-input:other",
            input_sha256="c" * 64,
            provenance_refs=("source:other",),
        )
        other_session = VoiceSessionCapsule.create(
            intent=other_intent,
            session_causal_identity=other_intent.causal_identity.derive(
                causal_id="causal-other-session", generation=2, turn_id="turn-other-session"
            ),
            provenance_refs=("receipt:other",),
        )
        with self.assertRaises(VoiceContractError):
            bind_voice_outcome(session=other_session, candidate=candidate)

    def test_exact_replay_is_idempotent(self) -> None:
        session = self.session()
        causal = session.session_causal_identity.derive(
            causal_id="causal-idempotent", generation=5, turn_id="turn-idempotent"
        )
        candidate = VoiceOutcome.create(
            session=session,
            outcome_causal_identity=causal,
            outcome_kind=OUTCOME_RETURNED,
            result_ref="voice-result:idempotent",
            result_sha256="d" * 64,
            provenance_refs=("receipt:idempotent",),
        )
        self.assertIs(bind_voice_outcome(session=session, candidate=candidate, existing=candidate), candidate)

    def test_contradictory_second_terminal_outcome_fails_closed(self) -> None:
        session = self.session()
        causal = session.session_causal_identity.derive(
            causal_id="causal-terminal", generation=5, turn_id="turn-terminal"
        )
        first = VoiceOutcome.create(
            session=session, outcome_causal_identity=causal, outcome_kind=OUTCOME_RETURNED,
            result_ref="voice-result:terminal", result_sha256="e" * 64,
            provenance_refs=("receipt:terminal",),
        )
        second = VoiceOutcome.create(
            session=session, outcome_causal_identity=causal, outcome_kind=OUTCOME_INTERRUPTED,
            result_ref="voice-result:terminal", result_sha256="e" * 64,
            provenance_refs=("receipt:terminal",),
        )
        with self.assertRaises(VoiceContractError):
            bind_voice_outcome(session=session, candidate=second, existing=first)

    def test_mapping_unknown_fields_and_noncanonical_refs_fail_closed(self) -> None:
        raw = self.intent().as_dict()
        raw["identity_authority"] = True
        with self.assertRaises(VoiceContractError):
            VoiceIntent.from_mapping(raw)
        with self.assertRaises(VoiceContractError):
            VoiceIntent.create(
                causal_identity=self.root(),
                input_ref="voice-input:704",
                input_sha256="a" * 64,
                provenance_refs=("z", "a"),
            )

    def test_classification_does_not_mint_runtime_or_effect_authority(self) -> None:
        objects = (self.intent().as_dict(), self.session().as_dict(), self.outcome().as_dict())
        for value in objects:
            self.assertEqual(value["classification"], VOICE_CLASSIFICATION)
            for forbidden in (
                "microphone_open", "provider_call", "model_success", "world_fact",
                "effect_authority", "completion_authority", "unifieddb_write", "runtime_pass",
            ):
                self.assertNotIn(forbidden, value)


if __name__ == "__main__":
    unittest.main()
