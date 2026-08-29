from __future__ import annotations

import unittest

from frankenstein2.target_trace_replay import (
    REPLAY_PLAN_SCHEMA,
    T3_FIDELITY,
    T4_FIDELITY,
    TARGET_TRACE_SCHEMA,
    TargetTraceReplayError,
    compile_replay_plan,
    normalize_target_trace,
)

PROFILE_DIGEST = "a" * 64


def event(
    event_id: str,
    sequence: int,
    *,
    generation: int = 1,
    kind: str = "SERVICE_STATE",
    subject_id: str = "service.pipewire",
    observed_state: str = "active",
    source: str = "systemd.user",
    offset_ns: int = 0,
    physical_only: bool = False,
    physical_gap_reason: str | None = None,
):
    value = {
        "event_id": event_id,
        "sequence": sequence,
        "generation": generation,
        "kind": kind,
        "subject_id": subject_id,
        "observed_state": observed_state,
        "source": source,
        "offset_ns": offset_ns,
        "physical_only": physical_only,
    }
    if physical_gap_reason is not None:
        value["physical_gap_reason"] = physical_gap_reason
    return value


class TargetTraceReplayTests(unittest.TestCase):
    def test_same_explicit_trace_has_same_digest_and_plan_despite_input_order(self) -> None:
        events = [
            event("evt-0", 0, kind="SESSION_EPOCH", subject_id="session.wayland", observed_state="epoch.7"),
            event("evt-1", 1, kind="DBUS_OWNER", subject_id="dbus.portal", observed_state="owner.42", offset_ns=10),
            event("evt-2", 2, kind="MULTIMEDIA_TOPOLOGY", subject_id="pipewire.graph", observed_state="generation.9", offset_ns=20),
        ]
        a = normalize_target_trace(
            events,
            target_profile_digest_sha256=PROFILE_DIGEST,
            trace_generation=4,
        )
        b = normalize_target_trace(
            reversed(events),
            target_profile_digest_sha256=PROFILE_DIGEST,
            trace_generation=4,
        )
        self.assertEqual(a.schema, TARGET_TRACE_SCHEMA)
        self.assertEqual(a.trace_digest_sha256, b.trace_digest_sha256)
        self.assertEqual(a.canonical_json(), b.canonical_json())

        plan_a = compile_replay_plan(a)
        plan_b = compile_replay_plan(b)
        self.assertEqual(plan_a.schema, REPLAY_PLAN_SCHEMA)
        self.assertEqual(plan_a.plan_digest_sha256, plan_b.plan_digest_sha256)
        self.assertEqual([step.sequence for step in plan_a.replay_steps], [0, 1, 2])
        self.assertEqual(plan_a.max_fidelity, T3_FIDELITY)
        self.assertFalse(plan_a.physical_host_credit)

    def test_physical_only_event_becomes_gap_never_replay_or_t4_credit(self) -> None:
        trace = normalize_target_trace(
            [
                event("evt-0", 0),
                event(
                    "evt-1",
                    1,
                    kind="DEVICE_GENERATION",
                    subject_id="camera.usb-1",
                    observed_state="generation.2",
                    source="kernel.udev",
                    physical_only=True,
                    physical_gap_reason="PHYSICAL_DEVICE_BEHAVIOR",
                ),
            ],
            target_profile_digest_sha256=PROFILE_DIGEST,
            trace_generation=1,
        )
        plan = compile_replay_plan(trace)
        self.assertEqual([step.event_id for step in plan.replay_steps], ["evt-0"])
        self.assertEqual(len(plan.fidelity_gaps), 1)
        self.assertEqual(plan.fidelity_gaps[0].event_id, "evt-1")
        self.assertEqual(plan.fidelity_gaps[0].required_fidelity, T4_FIDELITY)
        self.assertFalse(plan.physical_host_credit)
        self.assertNotIn("evt-1", [step.event_id for step in plan.replay_steps])

    def test_unknown_semantics_are_preserved_as_unknown_gap(self) -> None:
        trace = normalize_target_trace(
            [
                event(
                    "evt-unknown",
                    0,
                    kind="UNKNOWN",
                    subject_id="topology.unknown",
                    observed_state="unknown",
                    source="trace.capture",
                )
            ],
            target_profile_digest_sha256=PROFILE_DIGEST,
            trace_generation=1,
        )
        plan = compile_replay_plan(trace)
        self.assertEqual(plan.replay_steps, ())
        self.assertEqual(plan.fidelity_gaps[0].reason, "UNKNOWN_EVENT_SEMANTICS")
        self.assertEqual(plan.fidelity_gaps[0].required_fidelity, "UNKNOWN")
        self.assertFalse(plan.physical_host_credit)

    def test_generation_regression_for_same_subject_fails_closed(self) -> None:
        with self.assertRaisesRegex(TargetTraceReplayError, "generation regression"):
            normalize_target_trace(
                [
                    event("evt-0", 0, generation=3),
                    event("evt-1", 1, generation=2),
                ],
                target_profile_digest_sha256=PROFILE_DIGEST,
                trace_generation=1,
            )

    def test_duplicate_sequence_and_duplicate_event_identity_fail_closed(self) -> None:
        cases = (
            [event("evt-0", 0), event("evt-1", 0)],
            [event("evt-0", 0), event("evt-0", 1)],
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(TargetTraceReplayError):
                    normalize_target_trace(
                        raw,
                        target_profile_digest_sha256=PROFILE_DIGEST,
                        trace_generation=1,
                    )

    def test_free_form_or_user_content_fields_are_rejected(self) -> None:
        base = event("evt-0", 0)
        forbidden_records = []
        for field in (
            "payload",
            "content",
            "clipboard",
            "raw_camera_frame",
            "raw_microphone_audio",
            "user_document",
            "credential_token",
        ):
            record = dict(base)
            record[field] = "not-admitted"
            forbidden_records.append(record)
        for record in forbidden_records:
            with self.subTest(field=(set(record) - set(base)).pop()):
                with self.assertRaisesRegex(TargetTraceReplayError, "non-allowlisted|privacy-forbidden"):
                    normalize_target_trace(
                        [record],
                        target_profile_digest_sha256=PROFILE_DIGEST,
                        trace_generation=1,
                    )

    def test_free_form_values_and_bad_profile_digest_fail_closed(self) -> None:
        bad_value = event("evt-0", 0, observed_state="this is arbitrary free form text")
        with self.assertRaisesRegex(TargetTraceReplayError, "technical atom"):
            normalize_target_trace(
                [bad_value],
                target_profile_digest_sha256=PROFILE_DIGEST,
                trace_generation=1,
            )
        with self.assertRaisesRegex(TargetTraceReplayError, "SHA-256"):
            normalize_target_trace(
                [event("evt-0", 0)],
                target_profile_digest_sha256="UNKNOWN",
                trace_generation=1,
            )

    def test_physical_gap_reason_is_typed_and_required(self) -> None:
        for reason in (None, "free form reason"):
            raw = event(
                "evt-0",
                0,
                physical_only=True,
                physical_gap_reason=reason,
            )
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(TargetTraceReplayError, "physical_gap_reason"):
                    normalize_target_trace(
                        [raw],
                        target_profile_digest_sha256=PROFILE_DIGEST,
                        trace_generation=1,
                    )


if __name__ == "__main__":
    unittest.main()
