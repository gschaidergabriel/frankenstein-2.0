import json
from pathlib import Path
import unittest

from src.frankenstein2 import retina_capture_broker as compatibility_broker


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MODULE = "src/frankenstein2/perception_capture_broker.py"
COMPATIBILITY_MODULE = "src/frankenstein2/retina_capture_broker.py"
WP709_CLAIM = "workpackages/active/F2-WP-709.json"


class CaptureBrokerAuthorityUniquenessTests(unittest.TestCase):
    def test_wp709_declares_exactly_one_canonical_capture_broker_authority(self):
        claim = json.loads((ROOT / WP709_CLAIM).read_text(encoding="utf-8"))
        self.assertEqual(claim["workpackage_id"], "F2-WP-709")
        self.assertEqual(claim["state"], "ACCEPTED")
        self.assertEqual(claim["canonical_source"]["path"], CANONICAL_MODULE)
        self.assertTrue((ROOT / CANONICAL_MODULE).is_file())

        capture_modules = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "src/frankenstein2").glob("*capture_broker*.py")
        )
        self.assertEqual(capture_modules, [CANONICAL_MODULE, COMPATIBILITY_MODULE])
        self.assertEqual(
            compatibility_broker.CAPTURE_BROKER_AUTHORITY,
            "DELEGATES_ONLY_TO_PERCEPTION_CAPTURE_BROKER",
        )
        self.assertEqual(
            compatibility_broker.CANONICAL_CAPTURE_BROKER_MODULE,
            CANONICAL_MODULE,
        )

    def test_compatibility_state_has_no_independent_frame_ring_field(self):
        fields = compatibility_broker.CaptureBrokerState.__dataclass_fields__
        self.assertNotIn("frame_refs", fields)
        self.assertNotIn("dropped_frame_ref_ids", fields)
        self.assertIn("_canonical", fields)

    def test_retired_duplicate_unit_suite_does_not_return(self):
        self.assertFalse((ROOT / "tests/test_retina_capture_broker.py").exists())


if __name__ == "__main__":
    unittest.main()
