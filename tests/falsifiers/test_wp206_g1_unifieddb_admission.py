from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import unittest

from frankenstein2.persistent_agency_kernel import (
    PersistentAgencyIntegrationError,
    PersistentAgencyStore,
)
from state.unifieddb_identity import (
    RESOLUTION_SCHEMA,
    UnifiedDBResolution,
    fingerprint_unifieddb,
)


class PersistentAgencyUnifiedDBAdmissionFalsifier(unittest.TestCase):
    """REVIEW_ONLY falsifiers for WP206 canonical UnifiedDB admission."""

    def test_fresh_target_resolution_must_not_become_a_new_truth_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fresh" / "unified.db"
            path.parent.mkdir()
            resolution = UnifiedDBResolution(
                schema=RESOLUTION_SCHEMA,
                path=str(path),
                source="XDG_FRESH_TARGET",
                exists_at_resolution=False,
                explicit_sources=(),
            )
            fingerprint = fingerprint_unifieddb(path)
            with self.assertRaises(PersistentAgencyIntegrationError):
                PersistentAgencyStore(resolution, fingerprint)
            self.assertFalse(path.exists(), "WP206 must never create a fresh canonical DB implicitly")

    def test_wrong_resolution_schema_must_fail_closed_even_for_existing_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unified.db"
            conn = sqlite3.connect(path)
            try:
                conn.execute("CREATE TABLE sentinel(id INTEGER PRIMARY KEY)")
                conn.commit()
            finally:
                conn.close()
            resolution = UnifiedDBResolution(
                schema="UNTRUSTED_RESOLUTION/v999",
                path=str(path),
                source="EXPLICIT_TEST",
                exists_at_resolution=True,
                explicit_sources=("TEST",),
            )
            fingerprint = fingerprint_unifieddb(path)
            with self.assertRaises(PersistentAgencyIntegrationError):
                PersistentAgencyStore(resolution, fingerprint)


if __name__ == "__main__":
    unittest.main(verbosity=2)
