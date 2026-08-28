import unittest

from frankenstein2.state_fingerprint import (
    CLASSIFICATION,
    PROFILE,
    StateFingerprint,
    StateFingerprintError,
    canonical_projection_bytes,
    fingerprint_changed,
    fingerprint_state_projection,
    projection_changed,
)


class StateFingerprintTests(unittest.TestCase):
    def fp(self, projection, *, generation=1, schema="AGENCY_STATE/v1"):
        return fingerprint_state_projection(
            projection_schema=schema,
            generation=generation,
            projection=projection,
        )

    def test_mapping_order_is_canonicalized_without_value_normalization(self):
        a = self.fp({"b": 2, "a": [True, None, " x "]})
        b = self.fp({"a": [True, None, " x "], "b": 2})
        self.assertEqual(a.content_sha256, b.content_sha256)
        self.assertEqual(a.identity_sha256, b.identity_sha256)
        self.assertEqual(canonical_projection_bytes({"z": " x "}), b'{"z":" x "}')

    def test_list_order_remains_caller_significant(self):
        a = self.fp({"items": [1, 2]})
        b = self.fp({"items": [2, 1]})
        self.assertTrue(projection_changed(a, b))
        self.assertTrue(fingerprint_changed(a, b))

    def test_type_remains_caller_significant(self):
        integer = self.fp({"value": 1})
        string = self.fp({"value": "1"})
        boolean = self.fp({"value": True})
        self.assertNotEqual(integer.content_sha256, string.content_sha256)
        self.assertNotEqual(integer.content_sha256, boolean.content_sha256)

    def test_generation_only_movement_changes_identity_not_projection_content(self):
        g1 = self.fp({"open_loops": ["x"]}, generation=1)
        g2 = self.fp({"open_loops": ["x"]}, generation=2)
        self.assertEqual(g1.content_sha256, g2.content_sha256)
        self.assertNotEqual(g1.identity_sha256, g2.identity_sha256)
        self.assertFalse(projection_changed(g1, g2))
        self.assertTrue(fingerprint_changed(g1, g2))

    def test_projection_change_changes_both_content_and_identity(self):
        before = self.fp({"open_loops": ["x"]}, generation=7)
        after = self.fp({"open_loops": ["x", "y"]}, generation=7)
        self.assertTrue(projection_changed(before, after))
        self.assertTrue(fingerprint_changed(before, after))

    def test_schema_change_is_projection_contract_change(self):
        a = self.fp({"x": 1}, schema="SCHEMA_A/v1")
        b = self.fp({"x": 1}, schema="SCHEMA_B/v1")
        self.assertTrue(projection_changed(a, b))
        self.assertTrue(fingerprint_changed(a, b))

    def test_unsupported_types_fail_closed_instead_of_coercing(self):
        for bad in (1.0, b"x", (1, 2), {1, 2}):
            with self.subTest(type=type(bad).__name__):
                with self.assertRaises(StateFingerprintError):
                    self.fp({"value": bad})
        with self.assertRaisesRegex(StateFingerprintError, "mapping keys must be strings"):
            self.fp({1: "x"})

    def test_schema_and_generation_validation_fail_closed(self):
        for schema in ("", " schema", "schema ", "bad\nname"):
            with self.subTest(schema=schema):
                with self.assertRaises(StateFingerprintError):
                    self.fp({}, schema=schema)
        for generation in (-1, True, 1.0, "1"):
            with self.subTest(generation=generation):
                with self.assertRaises(StateFingerprintError):
                    self.fp({}, generation=generation)

    def test_deterministic_result_exposes_no_effect_or_truth_authority(self):
        a = self.fp({"goal": "inspect"}, generation=3)
        b = self.fp({"goal": "inspect"}, generation=3)
        self.assertEqual(a, b)
        self.assertEqual(a.profile, PROFILE)
        self.assertEqual(a.classification, CLASSIFICATION)
        self.assertEqual(a.sha256, a.identity_sha256)
        payload = a.as_dict()
        for forbidden in ("effect", "completion", "truth", "action", "schedule", "provider"):
            self.assertNotIn(forbidden, payload)

    def test_direct_fingerprint_object_rejects_invalid_digest_or_profile(self):
        with self.assertRaises(StateFingerprintError):
            StateFingerprint(PROFILE, "S/v1", 0, "x" * 64, "0" * 64, 2)
        with self.assertRaises(StateFingerprintError):
            StateFingerprint("OTHER", "S/v1", 0, "0" * 64, "0" * 64, 2)

    def test_comparison_rejects_untyped_values(self):
        fp = self.fp({"x": 1})
        with self.assertRaises(StateFingerprintError):
            fingerprint_changed(fp, object())
        with self.assertRaises(StateFingerprintError):
            projection_changed(object(), fp)


if __name__ == "__main__":
    unittest.main()
