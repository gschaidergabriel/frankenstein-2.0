import dataclasses
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import frankenstein2.perception_control as perception_control  # noqa: E402
from frankenstein2.perception_control import (  # noqa: E402
    PerceptionControlError,
    PerceptionControlResult,
    PerceptionDependency,
    PerceptionHeadPolicy,
    PerceptionPolicyRegistry,
    evaluate_perception_head,
    validate_perception_control_result,
)

REFS = ("test:wp702",)


def policy(head_id, tier="ON", *, enabled=True, memory_allowed=True):
    return PerceptionHeadPolicy(head_id=head_id, generation=1, tier=tier, enabled=enabled,
                                memory_allowed=memory_allowed, provenance_refs=REFS)


def registry(*heads, deps=None):
    deps = deps or {head.head_id: () for head in heads}
    return PerceptionPolicyRegistry(
        registry_id="registry-1", generation=1, heads=tuple(heads),
        dependencies=tuple(PerceptionDependency(head_id=head.head_id,
                           depends_on=tuple(deps.get(head.head_id, ()))) for head in heads),
        provenance_refs=REFS,
    )


def evaluate(reg, head_id, fn):
    return evaluate_perception_head(evaluation_id=f"eval-{head_id}", registry=reg,
        expected_registry_sha256=reg.sha256(), head_id=head_id, compute_fn=fn, provenance_refs=REFS)


def validate(result, reg, *, expected_result_sha256=None, expected_registry_sha256=None):
    return validate_perception_control_result(
        result=result,
        expected_result_sha256=expected_result_sha256 or result.sha256(),
        registry=reg,
        expected_registry_sha256=expected_registry_sha256 or reg.sha256(),
    )


class PerceptionControlTests(unittest.TestCase):
    def test_on_calls_once_and_can_persist(self):
        calls = []
        reg = registry(policy("object.known"))
        result = evaluate(reg, "object.known", lambda: (calls.append("called") or {"cup": True}, 800000))
        self.assertEqual(calls, ["called"])
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.value, {"cup": True})
        self.assertTrue(result.memory_match_allowed)
        self.assertTrue(result.persistence_allowed)

    def test_compute_off_never_invokes_compute_and_never_fabricates_false(self):
        calls = []
        reg = registry(policy("object.known", "COMPUTE_OFF"))
        result = evaluate(reg, "object.known", lambda: (calls.append("should-not-run") or False, 0))
        self.assertEqual(calls, [])
        self.assertEqual(result.status, "NOT_COMPUTED")
        self.assertIsNone(result.value)
        self.assertIsNone(result.confidence_micros)
        self.assertFalse(result.computed)

    def test_direct_result_constructor_cannot_launder_compute_off_policy(self):
        protected_policy = policy("protected.head", "COMPUTE_OFF")
        reg = registry(protected_policy)
        calls = []
        evaluated = evaluate(reg, "protected.head", lambda: (calls.append("must-not-run") or {"forged": True}, 1_000_000))
        self.assertEqual(calls, [])
        self.assertEqual(evaluated.status, "NOT_COMPUTED")
        self.assertFalse(evaluated.egress_allowed)
        self.assertFalse(evaluated.persistence_allowed)
        with self.assertRaises(PerceptionControlError):
            PerceptionControlResult(
                evaluation_id="eval-forged",
                head_id="protected.head",
                registry_sha256=reg.sha256(),
                policy_sha256=protected_policy.sha256(),
                status="OK",
                value={"forged": True},
                confidence_micros=1_000_000,
                computed=True,
                internal_computed=True,
                egress_allowed=True,
                memory_match_allowed=True,
                persistence_allowed=True,
                blocked_by=None,
                reason="caller_forged_policy_bypass",
                provenance_refs=("caller:self-attested",),
            )

    def test_factory_only_result_has_no_reusable_origin_token_and_cannot_replace(self):
        reg = registry(policy("head"))
        result = evaluate(reg, "head", lambda: ({"ok": True}, 800000))
        self.assertFalse(hasattr(perception_control, "_EVALUATOR_ORIGIN"))
        with self.assertRaises(PerceptionControlError):
            dataclasses.replace(result, persistence_allowed=False)
        with self.assertRaises(PerceptionControlError):
            PerceptionControlResult(_evaluator_origin=object())

    def test_consumer_revalidation_accepts_exact_canonical_result(self):
        reg = registry(policy("head"))
        result = evaluate(reg, "head", lambda: ({"ok": True}, 800000))
        expected = result.sha256()
        self.assertIs(validate(result, reg, expected_result_sha256=expected), result)

    def test_consumer_revalidation_rejects_post_evaluation_digest_drift(self):
        reg = registry(policy("sensitive.head", "MEMORY_OFF"))
        result = evaluate(reg, "sensitive.head", lambda: ({"same_cycle": True}, 900000))
        expected = result.sha256()
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        object.__setattr__(result, "memory_match_allowed", True)
        object.__setattr__(result, "persistence_allowed", True)
        object.__setattr__(result, "reason", "post_evaluation_drift")
        with self.assertRaisesRegex(PerceptionControlError, "result digest mismatch"):
            validate(result, reg, expected_result_sha256=expected)

    def test_consumer_revalidation_rejects_policy_forgery_even_with_recomputed_digest(self):
        reg = registry(policy("sensitive.head", "MEMORY_OFF"))
        result = evaluate(reg, "sensitive.head", lambda: ({"same_cycle": True}, 900000))
        object.__setattr__(result, "memory_match_allowed", True)
        object.__setattr__(result, "persistence_allowed", True)
        object.__setattr__(result, "reason", "policy_allows_egress")
        forged_digest = result.sha256()
        with self.assertRaisesRegex(PerceptionControlError, "memory/persistence authority mismatches"):
            validate(result, reg, expected_result_sha256=forged_digest)

    def test_consumer_revalidation_rejects_result_bound_to_different_registry(self):
        reg = registry(policy("head"))
        result = evaluate(reg, "head", lambda: (True, 800000))
        other = PerceptionPolicyRegistry(
            registry_id="registry-2", generation=1,
            heads=(policy("head"),),
            dependencies=(PerceptionDependency(head_id="head", depends_on=()),),
            provenance_refs=REFS,
        )
        with self.assertRaisesRegex(PerceptionControlError, "registry identity mismatch"):
            validate_perception_control_result(
                result=result,
                expected_result_sha256=result.sha256(),
                registry=other,
                expected_registry_sha256=other.sha256(),
            )

    def test_consumer_revalidation_rejects_current_policy_semantic_drift(self):
        original = policy("head")
        reg = registry(original)
        result = evaluate(reg, "head", lambda: (True, 800000))
        changed = registry(policy("head", "MEMORY_OFF"))
        with self.assertRaisesRegex(PerceptionControlError, "registry identity mismatch"):
            validate_perception_control_result(
                result=result,
                expected_result_sha256=result.sha256(),
                registry=changed,
                expected_registry_sha256=changed.sha256(),
            )

    def test_disabled_is_equivalent_to_compute_off_for_execution(self):
        calls = []
        reg = registry(policy("head", "ON", enabled=False))
        result = evaluate(reg, "head", lambda: (calls.append(1) or True, 900000))
        self.assertEqual(calls, [])
        self.assertEqual(result.status, "NOT_COMPUTED")

    def test_transitive_compute_off_taint_blocks_downstream_without_call(self):
        calls = []
        reg = registry(policy("a", "COMPUTE_OFF"), policy("b"), policy("c"),
                       deps={"a": (), "b": ("a",), "c": ("b",)})
        result = evaluate(reg, "c", lambda: (calls.append(1) or "fabricated", 700000))
        self.assertEqual(calls, [])
        self.assertEqual(result.status, "NOT_COMPUTED")
        self.assertEqual(result.blocked_by, "a")
        self.assertEqual(result.reason, "taint_blocked_by:a")
        self.assertIs(validate(result, reg), result)

    def test_output_off_computes_once_but_blocks_all_egress_and_persistence(self):
        calls = []
        reg = registry(policy("privacy.nudity", "OUTPUT_OFF"))
        result = evaluate(reg, "privacy.nudity", lambda: (calls.append(1) or "sensitive", 950000))
        self.assertEqual(calls, [1])
        self.assertEqual(result.status, "OUTPUT_BLOCKED")
        self.assertTrue(result.internal_computed)
        self.assertIsNone(result.value)
        self.assertIsNone(result.confidence_micros)
        self.assertFalse(result.egress_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertNotIn("sensitive", result.as_dict().values())
        self.assertIs(validate(result, reg), result)

    def test_memory_off_egresses_same_cycle_but_cannot_match_or_persist(self):
        reg = registry(policy("person.pose", "MEMORY_OFF"))
        result = evaluate(reg, "person.pose", lambda: ({"pose": "standing"}, 740000))
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.value, {"pose": "standing"})
        self.assertTrue(result.egress_allowed)
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertIs(validate(result, reg), result)

    def test_upstream_memory_off_taints_derived_memory_and_persistence(self):
        reg = registry(policy("sensitive.source", "MEMORY_OFF"), policy("derived.summary"),
                       deps={"sensitive.source": (), "derived.summary": ("sensitive.source",)})
        result = evaluate(reg, "derived.summary", lambda: ({"summary": "same-cycle"}, 760000))
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.value, {"summary": "same-cycle"})
        self.assertTrue(result.egress_allowed)
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertEqual(result.reason, "upstream_memory_or_persistence_taint")
        self.assertIs(validate(result, reg), result)

    def test_transitive_upstream_memory_off_cannot_be_laundered(self):
        reg = registry(policy("a", "MEMORY_OFF"), policy("b"), policy("c"),
                       deps={"a": (), "b": ("a",), "c": ("b",)})
        result = evaluate(reg, "c", lambda: ("derived", 710000))
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.value, "derived")
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertEqual(result.reason, "upstream_memory_or_persistence_taint")
        self.assertIs(validate(result, reg), result)

    def test_upstream_memory_allowed_false_taints_derived_persistence(self):
        reg = registry(policy("a", "ON", memory_allowed=False), policy("b"),
                       deps={"a": (), "b": ("a",)})
        result = evaluate(reg, "b", lambda: (True, 680000))
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.value)
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertEqual(result.reason, "upstream_memory_or_persistence_taint")
        self.assertIs(validate(result, reg), result)

    def test_output_off_upstream_also_cannot_launder_memory_or_persistence(self):
        reg = registry(policy("a", "OUTPUT_OFF"), policy("b"),
                       deps={"a": (), "b": ("a",)})
        result = evaluate(reg, "b", lambda: ("derived", 690000))
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.value, "derived")
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertIs(validate(result, reg), result)

    def test_on_with_memory_disallowed_has_same_cycle_egress_only(self):
        reg = registry(policy("face.presence", "ON", memory_allowed=False))
        result = evaluate(reg, "face.presence", lambda: (True, 600000))
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.value)
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        self.assertIs(validate(result, reg), result)

    def test_unknown_head_fails_closed_without_compute(self):
        calls = []
        reg = registry(policy("known"))
        result = evaluate(reg, "missing", lambda: (calls.append(1) or True, 500000))
        self.assertEqual(calls, [])
        self.assertEqual(result.status, "NOT_COMPUTED")
        self.assertEqual(result.reason, "unknown_head_not_in_registry")
        self.assertIs(validate(result, reg), result)

    def test_compute_error_is_typed_non_evidence(self):
        reg = registry(policy("head"))

        def boom():
            raise RuntimeError("secret detail")

        result = evaluate(reg, "head", boom)
        self.assertEqual(result.status, "COMPUTE_ERROR")
        self.assertIsNone(result.value)
        self.assertEqual(result.reason, "compute_error:RuntimeError")
        self.assertNotIn("secret detail", result.reason)
        self.assertIs(validate(result, reg), result)

    def test_registry_digest_is_order_independent_after_canonicalization(self):
        a = policy("a")
        b = policy("b")
        r1 = registry(a, b, deps={"a": (), "b": ("a",)})
        r2 = PerceptionPolicyRegistry(registry_id="registry-1", generation=1, heads=(b, a),
            dependencies=(PerceptionDependency(head_id="b", depends_on=("a",)),
                          PerceptionDependency(head_id="a", depends_on=())), provenance_refs=REFS)
        self.assertEqual(r1.sha256(), r2.sha256())

    def test_digest_mismatch_rejected_before_compute(self):
        calls = []
        reg = registry(policy("head"))
        with self.assertRaises(PerceptionControlError):
            evaluate_perception_head(evaluation_id="eval", registry=reg, expected_registry_sha256="0" * 64,
                head_id="head", compute_fn=lambda: (calls.append(1) or True, 1), provenance_refs=REFS)
        self.assertEqual(calls, [])

    def test_consumer_expected_result_digest_mismatch_fails_closed(self):
        reg = registry(policy("head"))
        result = evaluate(reg, "head", lambda: (True, 800000))
        with self.assertRaisesRegex(PerceptionControlError, "result digest mismatch"):
            validate(result, reg, expected_result_sha256="0" * 64)

    def test_cycle_and_unknown_dependency_rejected(self):
        a = policy("a")
        b = policy("b")
        with self.assertRaises(PerceptionControlError):
            registry(a, b, deps={"a": ("b",), "b": ("a",)})
        with self.assertRaises(PerceptionControlError):
            registry(a, deps={"a": ("missing",)})

    def test_invalid_tier_and_non_json_compute_value_rejected(self):
        with self.assertRaises(PerceptionControlError):
            policy("head", "MAYBE_OFF")
        reg = registry(policy("head"))
        with self.assertRaises(PerceptionControlError):
            evaluate(reg, "head", lambda: (object(), 123))


if __name__ == "__main__":
    unittest.main()
