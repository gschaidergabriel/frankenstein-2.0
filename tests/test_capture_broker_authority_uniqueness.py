import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MODULE = "src/frankenstein2/perception_capture_broker.py"
WP709_CLAIM = "workpackages/active/F2-WP-709.json"


class CaptureBrokerAuthorityUniquenessTests(unittest.TestCase):
    def test_wp709_declares_one_canonical_capture_broker_module(self):
        claim = json.loads((ROOT / WP709_CLAIM).read_text(encoding="utf-8"))
        self.assertEqual(claim["workpackage_id"], "F2-WP-709")
        self.assertEqual(claim["state"], "ACCEPTED")
        self.assertEqual(claim["canonical_source"]["path"], CANONICAL_MODULE)
        self.assertTrue((ROOT / CANONICAL_MODULE).is_file())

        capture_modules = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "src/frankenstein2").glob("*capture_broker*.py")
        )
        self.assertEqual(capture_modules, [CANONICAL_MODULE])

    def test_no_retired_duplicate_capture_broker_test_remains(self):
        self.assertFalse((ROOT / "tests/test_retina_capture_broker.py").exists())


if __name__ == "__main__":
    unittest.main()
