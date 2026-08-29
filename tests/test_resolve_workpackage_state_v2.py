import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "resolve_workpackage_state_v2.py"
spec = importlib.util.spec_from_file_location("resolver_v2", MODULE_PATH)
resolver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = resolver
assert spec.loader is not None
spec.loader.exec_module(resolver)


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


class ResolverV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "workpackages/active").mkdir(parents=True)
        (self.root / "workpackages/state_events/F2-WP-707").mkdir(parents=True)
        (self.root / "workpackages/reconciliations/F2-WP-707").mkdir(parents=True)
        contract = {
            "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE_VIEW_CONTRACT/v2",
            "authority_order": ["event", "snapshot"],
        }
        (self.root / "workpackages/STATE_VIEW_CONTRACT_V2.json").write_text(json.dumps(contract))
        state = {
            "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE/v1",
            "generation": 15,
            "workpackages": {"F2-WP-706": {"status": "NOT_STARTED", "phase": 7, "title": "x", "evidence": []}},
        }
        (self.root / "workpackages/STATE.json").write_text(json.dumps(state))
        run(["git", "init"], self.root)
        run(["git", "config", "user.email", "test@example.com"], self.root)
        run(["git", "config", "user.name", "test"], self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _commit_bound_files(self):
        active = {
            "workpackage_id": "F2-WP-707",
            "generation": 2,
            "claim_id": "claim-2",
            "state": "ACCEPTED",
        }
        recon = {
            "workpackage_id": "F2-WP-707",
            "generation": 2,
            "claim_id": "claim-2",
        }
        active_p = self.root / "workpackages/active/F2-WP-707.json"
        recon_p = self.root / "workpackages/reconciliations/F2-WP-707/2-claim-2.json"
        active_p.write_text(json.dumps(active, sort_keys=True))
        recon_p.write_text(json.dumps(recon, sort_keys=True))
        run(["git", "add", "."], self.root)
        run(["git", "commit", "-m", "base"], self.root)
        active_blob = run(["git", "rev-parse", "HEAD:workpackages/active/F2-WP-707.json"], self.root)
        recon_blob = run(["git", "rev-parse", "HEAD:workpackages/reconciliations/F2-WP-707/2-claim-2.json"], self.root)
        return active_blob, recon_blob

    def _write_event(self, *, active_blob, recon_blob, seq=1, parent=None, parent_sha=None):
        path = self.root / f"workpackages/state_events/F2-WP-707/{seq:06d}.json"
        event = {
            "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE_EVENT/v1",
            "workpackage_id": "F2-WP-707",
            "sequence": seq,
            "parent_event": parent,
            "parent_event_sha256": parent_sha,
            "observed_main_sha": run(["git", "rev-parse", "HEAD"], self.root),
            "claim_generation": 2,
            "claim_id": "claim-2",
            "broad_status": "ACCEPTED_AT_SCOPE",
            "phase": 7,
            "title": "Retina fan-in",
            "evidence": ["receipt.json"],
            "active_pointer_state": "ACCEPTED",
            "active_pointer_blob_sha": active_blob,
            "reconciliation_ref": "workpackages/reconciliations/F2-WP-707/2-claim-2.json",
            "reconciliation_blob_sha": recon_blob,
        }
        path.write_text(json.dumps(event, indent=2, sort_keys=True))
        return path

    def test_event_overrides_missing_snapshot_row(self):
        active_blob, recon_blob = self._commit_bound_files()
        self._write_event(active_blob=active_blob, recon_blob=recon_blob)
        resolved = resolver.resolve_effective_state(self.root, check_active=True)
        self.assertEqual(resolved["workpackages"]["F2-WP-707"]["status"], "ACCEPTED_AT_SCOPE")
        self.assertIn("F2-WP-707", resolved["migrated_event_heads"])

    def test_stale_active_blob_fails_closed(self):
        active_blob, recon_blob = self._commit_bound_files()
        self._write_event(active_blob="0" * 40, recon_blob=recon_blob)
        with self.assertRaises(resolver.ValidationError):
            resolver.resolve_effective_state(self.root, check_active=True)

    def test_sequence_gap_fails_closed(self):
        active_blob, recon_blob = self._commit_bound_files()
        self._write_event(active_blob=active_blob, recon_blob=recon_blob, seq=2)
        with self.assertRaises(resolver.ValidationError):
            resolver.load_event_chain(self.root, "F2-WP-707")

    def test_bad_parent_digest_fails_closed(self):
        active_blob, recon_blob = self._commit_bound_files()
        p1 = self._write_event(active_blob=active_blob, recon_blob=recon_blob, seq=1)
        p1_sha = hashlib.sha256(p1.read_bytes()).hexdigest()
        self._write_event(
            active_blob=active_blob,
            recon_blob=recon_blob,
            seq=2,
            parent="workpackages/state_events/F2-WP-707/000001.json",
            parent_sha="f" * 64,
        )
        self.assertNotEqual(p1_sha, "f" * 64)
        with self.assertRaises(resolver.ValidationError):
            resolver.load_event_chain(self.root, "F2-WP-707")


if __name__ == "__main__":
    unittest.main()
