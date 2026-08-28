from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "state" / "work_execution_binding.py"
SPEC = importlib.util.spec_from_file_location("work_execution_binding", MODULE)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


class WorkExecutionBindingTests(unittest.TestCase):
    def binding(self, **overrides):
        data = {
            "workpackage_id": "F2-WP-102",
            "generation": 1,
            "claim_id": "claim-102-g1",
            "causal_id": "causal:42",
            "invocation_id": "inv:7",
            "tool_use_id": "toolu:abc",
            "child_agent_id": "agent:child-3",
            "child_execution_id": "childexec:9",
            "identity_provenance": "observed:test-fixture",
        }
        data.update(overrides)
        return mod.make_binding(**data)

    def test_binding_id_is_deterministic_and_sensitive_to_tool_identity(self):
        a = self.binding()
        b = self.binding()
        c = self.binding(tool_use_id="toolu:def")
        self.assertEqual(a.binding_id, b.binding_id)
        self.assertNotEqual(a.binding_id, c.binding_id)
        self.assertTrue(a.binding_id.startswith("wex:"))
        self.assertEqual(len(a.binding_id), 68)

    def test_generation_is_strict_positive_integer(self):
        for invalid in (0, -1, True, "01", "g1", 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(mod.WorkExecutionBindingError, "INVALID_GENERATION"):
                    self.binding(generation=invalid)

    def test_empty_or_unsafe_observed_identity_fails_closed(self):
        for field in ("invocation_id", "tool_use_id", "child_agent_id", "child_execution_id"):
            with self.subTest(field=field):
                with self.assertRaises(mod.WorkExecutionBindingError):
                    self.binding(**{field: ""})

    def test_result_cross_talk_is_rejected_by_expected_identity(self):
        b = self.binding()
        with self.assertRaisesRegex(mod.WorkExecutionBindingError, "TOOL_USE_ID_MISMATCH"):
            mod.bind_result(
                b,
                result_id="result:1",
                outcome="SUCCESS",
                result_sha256="1" * 64,
                result_provenance="observed:test",
                expected_tool_use_id="toolu:other",
            )
        with self.assertRaisesRegex(mod.WorkExecutionBindingError, "GENERATION_MISMATCH"):
            mod.bind_result(
                b,
                result_id="result:1",
                outcome="SUCCESS",
                result_sha256="1" * 64,
                result_provenance="observed:test",
                expected_generation=2,
            )

    def test_unknown_result_stays_non_success_and_is_not_completion(self):
        b = self.binding()
        result = mod.bind_result(
            b,
            result_id="result:unknown",
            outcome="UNKNOWN",
            result_sha256="2" * 64,
            result_provenance="observed:transport-lost",
        )
        self.assertEqual(result.outcome, "UNKNOWN")
        self.assertFalse(result.is_success_result)
        self.assertNotIn("completion", result.to_dict())
        self.assertNotIn("effect", result.to_dict())

    def test_success_result_is_still_only_result_classification(self):
        b = self.binding()
        result = mod.bind_result(
            b,
            result_id="result:success",
            outcome="SUCCESS",
            result_sha256="3" * 64,
            result_provenance="observed:fixture",
        )
        self.assertTrue(result.is_success_result)
        self.assertNotIn("completion_id", result.to_dict())
        self.assertNotIn("effect_verified", result.to_dict())

    def test_serialized_binding_rejects_tamper_and_authority_scope_creep(self):
        b = self.binding()
        payload = b.to_dict()
        self.assertEqual(mod.validate_binding_dict(payload), b)

        tampered = dict(payload)
        tampered["child_agent_id"] = "agent:other"
        with self.assertRaisesRegex(mod.WorkExecutionBindingError, "BINDING_ID_MISMATCH"):
            mod.validate_binding_dict(tampered)

        scope_creep = dict(payload)
        scope_creep["completion"] = True
        with self.assertRaisesRegex(mod.WorkExecutionBindingError, "UNKNOWN_FIELDS:completion"):
            mod.validate_binding_dict(scope_creep)

    def test_result_digest_must_be_sha256(self):
        with self.assertRaisesRegex(mod.WorkExecutionBindingError, "INVALID_RESULT_SHA256"):
            mod.bind_result(
                self.binding(),
                result_id="result:bad",
                outcome="FAILURE",
                result_sha256="not-a-digest",
                result_provenance="observed:test",
            )


if __name__ == "__main__":
    unittest.main()
