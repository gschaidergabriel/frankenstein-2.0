from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).parents[1] / "src"
sys.path.insert(0, str(SRC))
from frankenstein2.causal_identity import CausalIdentity, CausalIdentityError

BASE = {
    "session_id": "session-001",
    "agent_id": "agent-clay-organ",
    "task_id": "task-42",
    "turn_id": "turn-7",
    "causal_id": "cause-root",
    "generation": 0,
}


class CausalIdentityTests(unittest.TestCase):
    def test_valid_identity_and_roundtrip(self):
        identity = CausalIdentity.from_mapping(BASE)
        self.assertEqual(identity.as_dict()["causal_id"], "cause-root")
        self.assertEqual(CausalIdentity.from_mapping(identity.as_dict()), identity)

    def test_canonical_json_is_deterministic_across_mapping_order(self):
        reordered = dict(reversed(list(BASE.items())))
        a = CausalIdentity.from_mapping(BASE)
        b = CausalIdentity.from_mapping(reordered)
        self.assertEqual(a.canonical_json(), b.canonical_json())
        self.assertEqual(a.sha256(), b.sha256())
        self.assertEqual(json.loads(a.canonical_json()), a.as_dict())

    def test_rejects_missing_unexpected_and_empty_identifiers(self):
        with self.assertRaises(CausalIdentityError):
            CausalIdentity.from_mapping({k: v for k, v in BASE.items() if k != "task_id"})
        with self.assertRaises(CausalIdentityError):
            CausalIdentity.from_mapping({**BASE, "transport_id": "not-causal-authority"})
        with self.assertRaises(CausalIdentityError):
            CausalIdentity.from_mapping({**BASE, "turn_id": "  "})
        with self.assertRaises(CausalIdentityError):
            CausalIdentity.from_mapping({**BASE, "agent_id": " agent "})

    def test_generation_is_exact_non_negative_integer(self):
        for bad in (True, False, -1, 1.0, "1", None):
            with self.subTest(bad=bad), self.assertRaises(CausalIdentityError):
                CausalIdentity.from_mapping({**BASE, "generation": bad})
        self.assertEqual(CausalIdentity.from_mapping({**BASE, "generation": 3}).generation, 3)

    def test_derive_records_parent_without_inventing_identity(self):
        root = CausalIdentity.from_mapping(BASE)
        child = root.derive(causal_id="cause-child", generation=1, turn_id="turn-8")
        self.assertEqual(child.parent_causal_id, root.causal_id)
        self.assertEqual(child.causal_id, "cause-child")
        self.assertEqual(child.session_id, root.session_id)
        self.assertEqual(child.task_id, root.task_id)
        self.assertEqual(child.generation, 1)

    def test_parent_cannot_self_reference(self):
        with self.assertRaises(CausalIdentityError):
            CausalIdentity.from_mapping({**BASE, "parent_causal_id": "cause-root"})

    def test_parent_is_optional_but_if_present_is_validated(self):
        self.assertIsNone(CausalIdentity.from_mapping(BASE).parent_causal_id)
        with self.assertRaises(CausalIdentityError):
            CausalIdentity.from_mapping({**BASE, "parent_causal_id": " parent "})


if __name__ == "__main__":
    unittest.main()
