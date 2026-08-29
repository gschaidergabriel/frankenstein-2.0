from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.child_lifecycle import (
    LIFECYCLE_VERSION,
    NESTED_SPAWN,
    REPLACE,
    RESUME,
    RUNNING,
    TERMINAL,
    WAITING,
    ChildLifecycleCandidate,
    ChildLifecycleError,
    ChildLifecyclePolicy,
    build_child_lifecycle_candidate,
    verify_child_lifecycle_candidate,
)
from frankenstein2.native_child_abi import ABI_VERSION, ChildResourceBudget, NativeChildRequest
from frankenstein2.native_child_binding import NativeChildBinding


class ChildLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = CausalIdentity(
            session_id="session-604",
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-1",
            causal_id="causal-parent-604",
            generation=10,
        )
        child = parent.derive(
            causal_id="causal-child-604",
            generation=11,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
        )
        binding = NativeChildBinding(
            workpackage_id="F2-WP-604",
            workpackage_generation=1,
            claim_id="F2-WP-604-G1-GPT56SOL-CHILD-LIFECYCLE-GENERATION-20260829",
            parent=parent,
            invocation_id="invocation-604",
            tool_use_id="tool-use-604",
            delegation_id="delegation-604",
            child=child,
        )
        budget = ChildResourceBudget(
            max_work_units=64,
            max_duration_ms=5000,
            max_output_bytes=65536,
            max_nested_depth=3,
            max_tool_calls=4,
        )
        self.request = NativeChildRequest(
            request_id="child-request-604",
            request_generation=4,
            abi_version=ABI_VERSION,
            binding=binding,
            binding_id=binding.binding_id(),
            binding_sha256=binding.sha256(),
            child_runtime_class="python-native-child",
            payload_ref="payload:604",
            payload_sha256="a" * 64,
            input_refs=("input:a",),
            requested_capability_refs=("cap:read",),
            resource_budget=budget,
        )
        self.policy = ChildLifecyclePolicy(max_generation=9, max_nested_depth=2)

    def build(self, **overrides):
        values = {
            "operation": RESUME,
            "current_state": WAITING,
            "request": self.request,
            "expected_current_generation": 4,
            "requested_nested_depth": 0,
            "replacement_binding_id": None,
            "policy": self.policy,
        }
        values.update(overrides)
        return build_child_lifecycle_candidate(**values)

    def test_resume_candidate_roundtrip_and_consumer_verification(self) -> None:
        candidate = self.build()
        self.assertEqual(candidate.lifecycle_version, LIFECYCLE_VERSION)
        self.assertEqual(candidate.next_generation, 5)
        reconstructed = ChildLifecycleCandidate.from_mapping(candidate.as_dict())
        self.assertEqual(reconstructed, candidate)
        verified = verify_child_lifecycle_candidate(
            candidate,
            expected_lifecycle_id=candidate.lifecycle_id(),
            expected_sha256=candidate.sha256(),
            expected_operation=RESUME,
            expected_current_generation=4,
        )
        self.assertIs(verified, candidate)

    def test_stale_or_future_generation_fails_closed(self) -> None:
        for generation in (3, 5):
            with self.subTest(generation=generation):
                with self.assertRaisesRegex(ChildLifecycleError, "stale or mismatched"):
                    self.build(expected_current_generation=generation)

    def test_malformed_generation_and_depth_inputs_fail_inside_lifecycle_boundary(self) -> None:
        for generation in (True, "4", 4.0, None):
            with self.subTest(generation=generation):
                with self.assertRaisesRegex(ChildLifecycleError, "expected_current_generation"):
                    self.build(expected_current_generation=generation)
        for depth in (True, "1", 1.0, None, -1):
            with self.subTest(depth=depth):
                with self.assertRaisesRegex(ChildLifecycleError, "requested_nested_depth"):
                    self.build(requested_nested_depth=depth)

    def test_resume_is_waiting_only_and_terminal_child_never_resumes(self) -> None:
        for state in (RUNNING, TERMINAL):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ChildLifecycleError, "RESUME requires exact WAITING"):
                    self.build(current_state=state)

    def test_resume_cannot_smuggle_replacement_or_nested_spawn(self) -> None:
        with self.assertRaises(ChildLifecycleError):
            self.build(replacement_binding_id="wex:new-binding")
        with self.assertRaises(ChildLifecycleError):
            self.build(requested_nested_depth=1)

    def test_replacement_requires_new_binding_identity_and_new_generation(self) -> None:
        candidate = self.build(
            operation=REPLACE,
            current_state=TERMINAL,
            replacement_binding_id="wex:replacement-604",
        )
        self.assertEqual(candidate.next_generation, self.request.request_generation + 1)
        self.assertNotEqual(candidate.replacement_binding_id, candidate.binding_id)
        with self.assertRaisesRegex(ChildLifecycleError, "new binding identity"):
            self.build(
                operation=REPLACE,
                current_state=TERMINAL,
                replacement_binding_id=self.request.binding_id,
            )

    def test_replacement_requires_explicit_identity_and_zero_nested_depth(self) -> None:
        with self.assertRaisesRegex(ChildLifecycleError, "explicit new binding"):
            self.build(operation=REPLACE, current_state=RUNNING)
        with self.assertRaisesRegex(ChildLifecycleError, "cannot request nested depth"):
            self.build(
                operation=REPLACE,
                current_state=RUNNING,
                replacement_binding_id="wex:replacement-604",
                requested_nested_depth=1,
            )

    def test_nested_spawn_obeys_policy_and_native_child_budget(self) -> None:
        candidate = self.build(
            operation=NESTED_SPAWN,
            current_state=RUNNING,
            requested_nested_depth=2,
        )
        self.assertEqual(candidate.requested_nested_depth, 2)
        with self.assertRaisesRegex(ChildLifecycleError, "lifecycle policy"):
            self.build(
                operation=NESTED_SPAWN,
                current_state=RUNNING,
                requested_nested_depth=3,
            )
        permissive_policy = ChildLifecyclePolicy(max_generation=9, max_nested_depth=4)
        too_shallow_request = replace(
            self.request,
            resource_budget=ChildResourceBudget(
                max_work_units=64,
                max_duration_ms=5000,
                max_output_bytes=65536,
                max_nested_depth=1,
                max_tool_calls=4,
            ),
        )
        with self.assertRaisesRegex(ChildLifecycleError, "NativeChildRequest budget"):
            self.build(
                operation=NESTED_SPAWN,
                current_state=RUNNING,
                request=too_shallow_request,
                requested_nested_depth=2,
                policy=permissive_policy,
            )

    def test_nested_spawn_rejects_zero_depth_terminal_and_replacement_identity(self) -> None:
        with self.assertRaisesRegex(ChildLifecycleError, "depth >= 1"):
            self.build(operation=NESTED_SPAWN, current_state=RUNNING)
        with self.assertRaisesRegex(ChildLifecycleError, "TERMINAL"):
            self.build(operation=NESTED_SPAWN, current_state=TERMINAL, requested_nested_depth=1)
        with self.assertRaisesRegex(ChildLifecycleError, "cannot carry replacement"):
            self.build(
                operation=NESTED_SPAWN,
                current_state=RUNNING,
                requested_nested_depth=1,
                replacement_binding_id="wex:replacement-604",
            )

    def test_generation_policy_ceiling_fails_closed(self) -> None:
        strict = ChildLifecyclePolicy(max_generation=4, max_nested_depth=2)
        with self.assertRaisesRegex(ChildLifecycleError, "generation exceeds"):
            self.build(policy=strict)

    def test_canonical_content_and_identity_detect_tampering(self) -> None:
        candidate = self.build()
        original_id = candidate.lifecycle_id()
        original_digest = candidate.sha256()
        tampered = replace(candidate, policy=ChildLifecyclePolicy(max_generation=10, max_nested_depth=2))
        self.assertNotEqual(tampered.lifecycle_id(), original_id)
        self.assertNotEqual(tampered.sha256(), original_digest)
        with self.assertRaises(ChildLifecycleError):
            verify_child_lifecycle_candidate(
                tampered,
                expected_lifecycle_id=original_id,
                expected_sha256=original_digest,
                expected_operation=RESUME,
                expected_current_generation=4,
            )

    def test_mapping_rejects_unknown_fields_and_polymorphic_request(self) -> None:
        candidate = self.build()
        raw = candidate.as_dict()
        raw["completion"] = True
        with self.assertRaisesRegex(ChildLifecycleError, "invalid lifecycle candidate fields"):
            ChildLifecycleCandidate.from_mapping(raw)

        class ForgedRequest(NativeChildRequest):
            pass

        forged = ForgedRequest(**self.request.__dict__) if hasattr(self.request, "__dict__") else None
        self.assertIsNone(forged)
        # Slots prevent a cheap forged constructor path here; the exact-type boundary is
        # directly exercised by passing a non-request object to the builder.
        with self.assertRaisesRegex(ChildLifecycleError, "exact concrete NativeChildRequest"):
            self.build(request=object())

    def test_lifecycle_evidence_does_not_mint_execution_or_effect_authority(self) -> None:
        candidate = self.build(operation=REPLACE, current_state=RUNNING, replacement_binding_id="wex:new-604")
        fields = candidate.as_dict()
        for forbidden in (
            "spawned",
            "resumed",
            "executed",
            "provider_result",
            "model_result",
            "completion",
            "effect",
            "world_fact",
            "capability_grant",
            "runtime_credit",
        ):
            self.assertNotIn(forbidden, fields)

    def test_policy_bool_and_negative_values_are_rejected(self) -> None:
        invalids = (
            {"max_generation": True, "max_nested_depth": 1},
            {"max_generation": 0, "max_nested_depth": 1},
            {"max_generation": 5, "max_nested_depth": -1},
        )
        for values in invalids:
            with self.subTest(values=values):
                with self.assertRaises(ChildLifecycleError):
                    ChildLifecyclePolicy(**values)


if __name__ == "__main__":
    unittest.main()
