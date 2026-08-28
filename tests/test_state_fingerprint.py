from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.state_fingerprint import (
    PROFILE,
    StateFingerprintError,
    canonical_projection_bytes,
    fingerprint_state_projection,
    identity_changed,
    projection_changed,
)


class StateFingerprintTests(unittest.TestCase):
    def fp(self, *, generation=1, projection=None, schema="STATE/v1"):
        if projection is None:
            projection = {"open_loops": ["a"], "counter": 7}
        return fingerprint_state_projection(
            projection_schema=schema,
            generation=generation,
            projection=projection,
        )

    def test_mapping_order_is_deterministic(self):
        left = self.fp(projection={"b": 2, "a": [1, True, None]})
        right = self.fp(projection={"a": [1, True, None], "b": 2})
        self.assertEqual(left.projection_sha256, right.projection_sha256)
        self.assertEqual(left.identity_sha256, right.identity_sha256)

    def test_same_projection_and_generation_is_exactly_stable(self):
        left = self.fp()
        right = self.fp()
        self.assertFalse(projection_changed(left, right))
        self.assertFalse(identity_changed(left, right))
        self.assertEqual(left.as_dict(), right.as_dict())

    def test_generation_only_movement_separates_content_from_identity(self):
        previous = self.fp(generation=1)
        current = self.fp(generation=2)
        self.assertEqual(previous.projection_sha256, current.projection_sha256)
        self.assertNotEqual(previous.identity_sha256, current.identity_sha256)
        self.assertFalse(projection_changed(previous, current))
        self.assertTrue(identity_changed(previous, current))

    def test_projection_content_change_marks_both_surfaces(self):
        previous = self.fp(projection={"value": 1})
        current = self.fp(projection={"value": 2})
        self.assertTrue(projection_changed(previous, current))
        self.assertTrue(identity_changed(previous, current))

    def test_schema_change_counts_as_typed_projection_change(self):
        previous = self.fp(schema="STATE/v1")
        current = self.fp(schema="STATE/v2")
        self.assertTrue(projection_changed(previous, current))
        self.assertTrue(identity_changed(previous, current))

    def test_list_order_is_caller_significant(self):
        left = self.fp(projection=["a", "b"])
        right = self.fp(projection=["b", "a"])
        self.assertTrue(projection_changed(left, right))

    def test_bool_and_int_remain_distinct_json_types(self):
        boolean = self.fp(projection={"value": True})
        integer = self.fp(projection={"value": 1})
        self.assertTrue(projection_changed(boolean, integer))

    def test_unicode_canonical_bytes_are_utf8_and_stable(self):
        payload = {"name": "Mensch", "symbol": "Δ"}
        self.assertEqual(
            canonical_projection_bytes(payload),
            canonical_projection_bytes(dict(reversed(list(payload.items())))),
        )
        fp = self.fp(projection=payload)
        self.assertEqual(fp.canonical_bytes, len(canonical_projection_bytes(payload)))

    def test_non_string_mapping_keys_fail_closed(self):
        with self.assertRaisesRegex(StateFingerprintError, "mapping keys must be strings"):
            self.fp(projection={1: "x"})

    def test_float_tuple_bytes_set_and_custom_object_fail_closed(self):
        for value in (1.5, (1, 2), b"x", {1, 2}, object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(StateFingerprintError):
                    self.fp(projection=value)

    def test_generation_must_be_nonnegative_int_not_bool(self):
        for value in (-1, True, 1.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(StateFingerprintError, "generation"):
                    self.fp(generation=value)

    def test_projection_schema_is_explicit_trimmed_identifier(self):
        for value in ("", " STATE/v1", "STATE/v1 "):
            with self.subTest(value=repr(value)):
                with self.assertRaises(StateFingerprintError):
                    self.fp(schema=value)

    def test_comparison_helpers_fail_closed_on_wrong_types(self):
        fp = self.fp()
        with self.assertRaises(StateFingerprintError):
            projection_changed(fp, object())
        with self.assertRaises(StateFingerprintError):
            identity_changed(object(), fp)

    def test_fingerprint_dataclass_rejects_tampered_digests(self):
        fp = self.fp()
        with self.assertRaisesRegex(StateFingerprintError, "projection_sha256"):
            replace(fp, projection_sha256="not-a-hash")
        with self.assertRaisesRegex(StateFingerprintError, "identity_sha256"):
            replace(fp, identity_sha256="A" * 64)

    def test_profile_and_classification_are_explicit_and_non_authoritative(self):
        fp = self.fp()
        self.assertEqual(fp.profile, PROFILE)
        self.assertEqual(
            fp.classification,
            "EXPLICIT_TYPED_PROJECTION_FINGERPRINT_NOT_WORLD_TRUTH",
        )
        self.assertTrue(
            {
                "pulse_action",
                "wake_decision",
                "effect_authorized",
                "completion_verified",
                "world_fact",
            }.isdisjoint(fp.as_dict())
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
