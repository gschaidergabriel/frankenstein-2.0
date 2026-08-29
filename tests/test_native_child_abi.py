from __future__ import annotations

from dataclasses import replace
import sys
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.native_child_abi import (
    ABI_VERSION,
    ChildResourceBudget,
    NativeChildABIError,
    NativeChildRequest,
    verify_native_child_request,
)


class NativeChildABITests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = CausalIdentity(
            session_id="session-1",
            agent_id="parent-agent",
            task_id="parent-task",
            turn_id="turn-1",
            causal_id="causal-parent",
            generation=7,
        )
        self.child = self.parent.derive(
            causal_id="causal-child",
            generation=8,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
        )
        self.binding = NativeChildBinding(
            workpackage_id="F2-WP-601",
            workpackage_generation=1,
            claim_id="F2-WP-601-G1-GPT56SOL-NATIVE-CHILD-ABI-20260829",
            parent=self.parent,
            invocation_id="invocation-601",
            tool_use_id="tool-use-601",
            delegation_id="delegation-601",
            child=self.child,
        )
        self.budget = ChildResourceBudget(
            max_work_units=32,
            max_duration_ms=5000,
            max_output_bytes=65536,
            max_nested_depth=2,
            max_tool_calls=4,
        )
        self.request = NativeChildRequest(
            request_id="child-request-1",
            request_generation=1,
            abi_version=ABI_VERSION,
            binding=self.binding,
            binding_id=self.binding.binding_id(),
            binding_sha256=self.binding.sha256(),
            child_runtime_class="python-native-child",
            payload_ref="payload:task-1",
            payload_sha256="a" * 64,
            input_refs=("input:a", "input:b"),
            requested_capability_refs=("cap:read-memory", "cap:tool-visible"),
            resource_budget=self.budget,
        )

    def test_valid_request_roundtrip_is_deterministic(self) -> None:
        reconstructed = NativeChildRequest.from_mapping(self.request.as_dict())
        self.assertEqual(reconstructed, self.request)
        self.assertEqual(reconstructed.canonical_json(), self.request.canonical_json())
        self.assertEqual(reconstructed.sha256(), self.request.sha256())

    def test_verify_rebinds_every_exact_identity_and_digest(self) -> None:
        verified = verify_native_child_request(
            self.request,
            expected_request_id=self.request.request_id,
            expected_request_generation=self.request.request_generation,
            expected_binding_id=self.binding.binding_id(),
            expected_binding_sha256=self.binding.sha256(),
            expected_request_sha256=self.request.sha256(),
        )
        self.assertIs(verified, self.request)
        cases = (
            {"expected_request_id": "other-request"},
            {"expected_request_generation": 2},
            {"expected_binding_id": "wex:" + "0" * 64},
            {"expected_binding_sha256": "b" * 64},
            {"expected_request_sha256": "c" * 64},
        )
        base = {
            "expected_request_id": self.request.request_id,
            "expected_request_generation": self.request.request_generation,
            "expected_binding_id": self.binding.binding_id(),
            "expected_binding_sha256": self.binding.sha256(),
            "expected_request_sha256": self.request.sha256(),
        }
        for override in cases:
            with self.subTest(override=override):
                args = dict(base)
                args.update(override)
                with self.assertRaises(NativeChildABIError):
                    verify_native_child_request(self.request, **args)

    def test_binding_identity_and_digest_cannot_self_attest(self) -> None:
        with self.assertRaises(NativeChildABIError):
            replace(self.request, binding_id="wex:" + "0" * 64)
        with self.assertRaises(NativeChildABIError):
            replace(self.request, binding_sha256="b" * 64)

    def test_result_already_bound_is_rejected(self) -> None:
        bound = self.binding.bind_result(
            invocation_id=self.binding.invocation_id,
            delegation_id=self.binding.delegation_id,
            child_causal_id=self.binding.child.causal_id,
            result_id="result-601",
            result_sha256="d" * 64,
        )
        with self.assertRaises(NativeChildABIError):
            replace(
                self.request,
                binding=bound,
                binding_id=bound.binding_id(),
                binding_sha256=bound.sha256(),
            )

    def test_exact_binding_type_blocks_polymorphic_self_attestation(self) -> None:
        class ForgedBinding(NativeChildBinding):
            def binding_id(self) -> str:
                return self.binding_id_forged

            @property
            def binding_id_forged(self) -> str:
                return "wex:" + "0" * 64

        forged = ForgedBinding(
            workpackage_id=self.binding.workpackage_id,
            workpackage_generation=self.binding.workpackage_generation,
            claim_id=self.binding.claim_id,
            parent=self.parent,
            invocation_id=self.binding.invocation_id,
            tool_use_id=self.binding.tool_use_id,
            delegation_id=self.binding.delegation_id,
            child=self.child,
        )
        with self.assertRaises(NativeChildABIError):
            replace(
                self.request,
                binding=forged,
                binding_id=forged.binding_id(),
                binding_sha256=forged.sha256(),
            )

    def test_exact_nested_causal_identity_type_is_required(self) -> None:
        class ForgedIdentity(CausalIdentity):
            pass

        forged_parent = ForgedIdentity(**self.parent.as_dict())
        forged_child = CausalIdentity(
            session_id=forged_parent.session_id,
            agent_id="child-agent",
            task_id="child-task",
            turn_id="turn-2",
            causal_id="causal-child-forged-parent",
            generation=8,
            parent_causal_id=forged_parent.causal_id,
        )
        forged_binding = NativeChildBinding(
            workpackage_id=self.binding.workpackage_id,
            workpackage_generation=self.binding.workpackage_generation,
            claim_id=self.binding.claim_id,
            parent=forged_parent,
            invocation_id=self.binding.invocation_id,
            tool_use_id=self.binding.tool_use_id,
            delegation_id=self.binding.delegation_id,
            child=forged_child,
        )
        with self.assertRaises(NativeChildABIError):
            replace(
                self.request,
                binding=forged_binding,
                binding_id=forged_binding.binding_id(),
                binding_sha256=forged_binding.sha256(),
            )

    def test_direct_collections_must_be_immutable_unique_and_canonical(self) -> None:
        with self.assertRaises(NativeChildABIError):
            replace(self.request, input_refs=["input:a", "input:b"])
        with self.assertRaises(NativeChildABIError):
            replace(self.request, input_refs=("input:a", "input:a"))
        with self.assertRaises(NativeChildABIError):
            replace(self.request, input_refs=("input:b", "input:a"))
        with self.assertRaises(NativeChildABIError):
            replace(self.request, requested_capability_refs=("cap:z", "cap:a"))

    def test_wire_mapping_normalizes_json_arrays_then_revalidates(self) -> None:
        raw = self.request.as_dict()
        self.assertIsInstance(raw["input_refs"], list)
        reconstructed = NativeChildRequest.from_mapping(raw)
        self.assertEqual(reconstructed.input_refs, ("input:a", "input:b"))
        self.assertEqual(
            reconstructed.requested_capability_refs,
            ("cap:read-memory", "cap:tool-visible"),
        )
        raw["input_refs"] = ["input:b", "input:a"]
        with self.assertRaises(NativeChildABIError):
            NativeChildRequest.from_mapping(raw)

    def test_resource_budget_is_strict_and_bool_is_not_integer(self) -> None:
        invalids = (
            {"max_work_units": 0},
            {"max_work_units": True},
            {"max_duration_ms": 0},
            {"max_output_bytes": -1},
            {"max_nested_depth": -1},
            {"max_tool_calls": -1},
        )
        for override in invalids:
            with self.subTest(override=override):
                values = self.budget.as_dict()
                values.update(override)
                with self.assertRaises(NativeChildABIError):
                    ChildResourceBudget(**values)

    def test_resource_budget_rejects_integer_outside_canonical_json_domain(self) -> None:
        max_digits = sys.get_int_max_str_digits()
        self.assertGreater(
            max_digits,
            0,
            "WP601 G2 regression requires the admitted finite CPython integer digit limit",
        )
        huge_work_units = 10 ** (max_digits + 1)
        values = self.budget.as_dict()
        values["max_work_units"] = huge_work_units
        with self.assertRaisesRegex(
            NativeChildABIError,
            "outside the canonical JSON integer domain",
        ):
            ChildResourceBudget(**values)

    def test_request_generation_and_digest_formats_are_strict(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(NativeChildABIError):
                    replace(self.request, request_generation=invalid)
        with self.assertRaises(NativeChildABIError):
            replace(self.request, payload_sha256="A" * 64)
        with self.assertRaises(NativeChildABIError):
            replace(self.request, abi_version="F2_NATIVE_CHILD_ABI/v2")

    def test_mapping_rejects_unknown_or_missing_fields(self) -> None:
        raw = self.request.as_dict()
        raw["completion"] = True
        with self.assertRaises(NativeChildABIError):
            NativeChildRequest.from_mapping(raw)
        raw = self.request.as_dict()
        del raw["payload_ref"]
        with self.assertRaises(NativeChildABIError):
            NativeChildRequest.from_mapping(raw)

    def test_requested_capabilities_are_not_grants_or_effect_authority(self) -> None:
        fields = self.request.as_dict()
        self.assertIn("requested_capability_refs", fields)
        for forbidden in (
            "granted_capabilities",
            "capability_authority",
            "spawn_authority",
            "completion",
            "effect",
            "result",
            "world_fact",
        ):
            self.assertNotIn(forbidden, fields)

    def test_wp601_does_not_define_child_result_or_completion_semantics(self) -> None:
        fields = self.request.as_dict()
        self.assertIsNone(self.request.binding.result_id)
        self.assertIsNone(self.request.binding.result_sha256)
        self.assertNotIn("result_status", fields)
        self.assertNotIn("completion_id", fields)
        self.assertNotIn("effect_request", fields)


if __name__ == "__main__":
    unittest.main()
