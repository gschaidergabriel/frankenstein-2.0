from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.realtime_reentry import (
    BARGE_IN,
    BILATERAL_SILENCE,
    REALTIME_REENTRY_VERSION,
    TOOL_RETURN,
    RealtimeReentryCursor,
    RealtimeReentryError,
    RealtimeReentryEvidence,
    RealtimeReentryPolicy,
    build_realtime_reentry_evidence,
    verify_realtime_reentry_evidence,
)


class RealtimeReentryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_id = "voice-session-705"
        self.session_sha256 = "a" * 64
        self.policy = RealtimeReentryPolicy(bilateral_silence_threshold_ms=5000)
        self.cursor = RealtimeReentryCursor.initial(
            session_id=self.session_id,
            session_sha256=self.session_sha256,
        )

    def build(self, **overrides):
        values = {
            "cursor": self.cursor,
            "event_type": BARGE_IN,
            "observed_at_ms": 1000,
            "policy": self.policy,
            "barge_in_input_id": "input-activity-1",
        }
        values.update(overrides)
        return build_realtime_reentry_evidence(**values)

    def test_barge_in_roundtrip_and_consumer_verification(self) -> None:
        evidence = self.build()
        self.assertEqual(evidence.reentry_version, REALTIME_REENTRY_VERSION)
        self.assertEqual(evidence.event_sequence, 1)
        self.assertEqual(evidence.causal_generation, 1)
        reconstructed = RealtimeReentryEvidence.from_mapping(evidence.as_dict())
        self.assertEqual(reconstructed, evidence)
        self.assertIs(
            verify_realtime_reentry_evidence(
                evidence,
                expected_reentry_id=evidence.reentry_id(),
                expected_sha256=evidence.sha256(),
                expected_session_id=self.session_id,
                expected_session_sha256=self.session_sha256,
                expected_event_type=BARGE_IN,
                expected_event_sequence=1,
                expected_causal_generation=1,
            ),
            evidence,
        )

    def test_cursor_chain_advances_sequence_and_generation_exactly(self) -> None:
        first = self.build()
        second = build_realtime_reentry_evidence(
            cursor=first.next_cursor(),
            event_type=TOOL_RETURN,
            observed_at_ms=1200,
            policy=self.policy,
            tool_call_id="tool-1",
            tool_result_sha256="b" * 64,
        )
        self.assertEqual(second.event_sequence, 2)
        self.assertEqual(second.causal_generation, 2)
        self.assertEqual(second.predecessor_event_id, first.reentry_id())
        self.assertEqual(second.predecessor_event_sha256, first.sha256())

    def test_empty_cursor_rejects_fake_predecessor_or_generation(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "empty cursor"):
            RealtimeReentryCursor(
                session_id=self.session_id,
                session_sha256=self.session_sha256,
                last_event_sequence=0,
                last_causal_generation=1,
                last_observed_at_ms=0,
                last_event_id=None,
                last_event_sha256=None,
            )
        with self.assertRaisesRegex(RealtimeReentryError, "empty cursor cannot carry"):
            RealtimeReentryCursor(
                session_id=self.session_id,
                session_sha256=self.session_sha256,
                last_event_sequence=0,
                last_causal_generation=0,
                last_observed_at_ms=0,
                last_event_id="wrr:fake",
                last_event_sha256="c" * 64,
            )

    def test_nonempty_cursor_requires_exact_predecessor_binding(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "exact predecessor"):
            RealtimeReentryCursor(
                session_id=self.session_id,
                session_sha256=self.session_sha256,
                last_event_sequence=1,
                last_causal_generation=1,
                last_observed_at_ms=1000,
                last_event_id=None,
                last_event_sha256=None,
            )

    def test_observed_time_cannot_regress_cursor(self) -> None:
        first = self.build(observed_at_ms=2000)
        with self.assertRaisesRegex(RealtimeReentryError, "regresses"):
            build_realtime_reentry_evidence(
                cursor=first.next_cursor(),
                event_type=BARGE_IN,
                observed_at_ms=1999,
                policy=self.policy,
                barge_in_input_id="input-2",
            )

    def test_barge_in_requires_input_identity_and_rejects_cross_payloads(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "explicit input"):
            self.build(barge_in_input_id=None)
        with self.assertRaisesRegex(RealtimeReentryError, "silence-window"):
            self.build(local_silence_ms=1)
        with self.assertRaisesRegex(RealtimeReentryError, "tool-return"):
            self.build(tool_call_id="tool-x", tool_result_sha256="d" * 64)

    def test_bilateral_silence_requires_both_sides_at_threshold(self) -> None:
        evidence = self.build(
            event_type=BILATERAL_SILENCE,
            barge_in_input_id=None,
            local_silence_ms=5000,
            remote_silence_ms=5000,
        )
        self.assertEqual(evidence.event_type, BILATERAL_SILENCE)
        for local, remote in ((4999, 5000), (5000, 4999), (0, 10000)):
            with self.subTest(local=local, remote=remote):
                with self.assertRaisesRegex(RealtimeReentryError, "does not meet"):
                    self.build(
                        event_type=BILATERAL_SILENCE,
                        barge_in_input_id=None,
                        local_silence_ms=local,
                        remote_silence_ms=remote,
                    )

    def test_bilateral_silence_rejects_other_event_evidence(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "barge-in"):
            self.build(event_type=BILATERAL_SILENCE, local_silence_ms=5000, remote_silence_ms=5000)
        with self.assertRaisesRegex(RealtimeReentryError, "tool-return"):
            self.build(
                event_type=BILATERAL_SILENCE,
                barge_in_input_id=None,
                local_silence_ms=5000,
                remote_silence_ms=5000,
                tool_call_id="tool-x",
                tool_result_sha256="e" * 64,
            )

    def test_tool_return_requires_call_identity_and_result_digest(self) -> None:
        evidence = self.build(
            event_type=TOOL_RETURN,
            barge_in_input_id=None,
            tool_call_id="tool-705",
            tool_result_sha256="f" * 64,
        )
        self.assertEqual(evidence.tool_call_id, "tool-705")
        with self.assertRaisesRegex(RealtimeReentryError, "requires exact"):
            self.build(event_type=TOOL_RETURN, barge_in_input_id=None)
        with self.assertRaisesRegex(RealtimeReentryError, "SHA-256"):
            self.build(
                event_type=TOOL_RETURN,
                barge_in_input_id=None,
                tool_call_id="tool-705",
                tool_result_sha256="not-a-digest",
            )

    def test_tool_return_rejects_silence_or_barge_in_evidence(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "barge-in"):
            self.build(event_type=TOOL_RETURN, tool_call_id="tool", tool_result_sha256="1" * 64)
        with self.assertRaisesRegex(RealtimeReentryError, "silence-window"):
            self.build(
                event_type=TOOL_RETURN,
                barge_in_input_id=None,
                local_silence_ms=1,
                tool_call_id="tool",
                tool_result_sha256="1" * 64,
            )

    def test_session_digest_and_identifiers_fail_closed(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "session_sha256"):
            RealtimeReentryCursor.initial(session_id=self.session_id, session_sha256="ABC")
        with self.assertRaisesRegex(RealtimeReentryError, "already trimmed"):
            RealtimeReentryCursor.initial(session_id=" session ", session_sha256=self.session_sha256)

    def test_event_type_is_closed_enum(self) -> None:
        with self.assertRaisesRegex(RealtimeReentryError, "not admitted"):
            self.build(event_type="TRANSCRIPT_TEXT")

    def test_mapping_rejects_unknown_fields(self) -> None:
        evidence = self.build()
        raw = evidence.as_dict()
        raw["semantic_success"] = True
        with self.assertRaisesRegex(RealtimeReentryError, "invalid realtime"):
            RealtimeReentryEvidence.from_mapping(raw)

    def test_content_identity_detects_tampering(self) -> None:
        evidence = self.build()
        original_id = evidence.reentry_id()
        original_digest = evidence.sha256()
        tampered = replace(evidence, observed_at_ms=1001)
        self.assertNotEqual(tampered.reentry_id(), original_id)
        self.assertNotEqual(tampered.sha256(), original_digest)
        with self.assertRaises(RealtimeReentryError):
            verify_realtime_reentry_evidence(
                tampered,
                expected_reentry_id=original_id,
                expected_sha256=original_digest,
                expected_session_id=self.session_id,
                expected_session_sha256=self.session_sha256,
                expected_event_type=BARGE_IN,
                expected_event_sequence=1,
                expected_causal_generation=1,
            )

    def test_cross_session_consumer_binding_fails_closed(self) -> None:
        evidence = self.build()
        with self.assertRaisesRegex(RealtimeReentryError, "session binding"):
            verify_realtime_reentry_evidence(
                evidence,
                expected_reentry_id=evidence.reentry_id(),
                expected_sha256=evidence.sha256(),
                expected_session_id="other-session",
                expected_session_sha256=self.session_sha256,
                expected_event_type=BARGE_IN,
                expected_event_sequence=1,
                expected_causal_generation=1,
            )

    def test_cursor_mapping_rejects_unknown_fields(self) -> None:
        raw = self.cursor.as_dict()
        raw["completion"] = "ACCEPTED"
        with self.assertRaisesRegex(RealtimeReentryError, "invalid realtime"):
            RealtimeReentryCursor.from_mapping(raw)


if __name__ == "__main__":
    unittest.main()
