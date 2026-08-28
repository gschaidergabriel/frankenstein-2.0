import unittest

from frankenstein2.persistent_agency_change_policy import (
    LINEAGE_ONLY_CHANGE,
    NO_FINGERPRINT_CHANGE,
    PROJECTION_CONTENT_CHANGE,
    classify_fingerprint_change,
)
from frankenstein2.state_fingerprint import fingerprint_state_projection


class PersistentAgencyChangePolicyTests(unittest.TestCase):
    def fingerprint(self, generation, projection):
        return fingerprint_state_projection(
            projection_schema="FRANKENSTEIN2_PERSISTENT_AGENCY_PROJECTION/v1",
            generation=generation,
            projection=projection,
        )

    def test_same_projection_new_generation_is_lineage_only(self):
        previous = self.fingerprint(0, {"agency": {"state": "same"}})
        current = self.fingerprint(1, {"agency": {"state": "same"}})
        result = classify_fingerprint_change(previous, current)
        self.assertEqual(result.classification, LINEAGE_ONLY_CHANGE)
        self.assertFalse(result.projection_changed)
        self.assertTrue(result.identity_changed)

    def test_changed_projection_is_content_change(self):
        previous = self.fingerprint(0, {"agency": {"state": "before"}})
        current = self.fingerprint(1, {"agency": {"state": "after"}})
        result = classify_fingerprint_change(previous, current)
        self.assertEqual(result.classification, PROJECTION_CONTENT_CHANGE)
        self.assertTrue(result.projection_changed)
        self.assertTrue(result.identity_changed)

    def test_identical_fingerprint_is_no_change(self):
        fingerprint = self.fingerprint(0, {"agency": {"state": "same"}})
        result = classify_fingerprint_change(fingerprint, fingerprint)
        self.assertEqual(result.classification, NO_FINGERPRINT_CHANGE)
        self.assertFalse(result.projection_changed)
        self.assertFalse(result.identity_changed)

    def test_assessment_carries_no_action_or_effect_authority_fields(self):
        previous = self.fingerprint(0, {"agency": {"state": "same"}})
        current = self.fingerprint(1, {"agency": {"state": "same"}})
        payload = classify_fingerprint_change(previous, current).as_dict()
        for forbidden in (
            "act",
            "delegate",
            "selected_action",
            "resume",
            "wake",
            "effect",
            "completion",
        ):
            self.assertNotIn(forbidden, payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
