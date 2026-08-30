#!/usr/bin/env python3
"""Finish G6 reentry arming and adapt the predecessor live-drift assertion.

Run only after trigger4_wp206_g6_owned_surface_witness_repair.py in the G6 repair workflow.
The G3 row-level authority invariant stays unchanged.  Only the earlier live-connection G6
reason changes from database-wide revision drift to WP206-owned-surface drift.
"""
from __future__ import annotations

from pathlib import Path


SOURCE = Path("src/frankenstein2/persistent_agency_kernel.py")
G3_TEST = Path("tests/test_wp206_legacy_authority_recovery.py")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{name} anchor mismatch: expected 1, observed {count}")
    return text.replace(old, new, 1)


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '''        self.sqlite_data_version_baseline = int(data_version_row[0])
        self._wp206_owned_surface_witness_sha256: str | None = None

    @classmethod
''',
        '''        self.sqlite_data_version_baseline = int(data_version_row[0])
        self._wp206_owned_surface_witness_sha256: str | None = None
        existing_wp206_table = self.connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
            (CHECKPOINT_TABLE,),
        ).fetchone()
        if existing_wp206_table is not None:
            # Reopen establishes a fresh same-process observation baseline over the already
            # admitted WP206-owned surface. Cross-reopen data_version continuity is never used.
            self._adopt_wp206_monitor_state(self._capture_wp206_monitor_state())

    @classmethod
''',
        "reopen monitor arming",
    )
    SOURCE.write_text(source, encoding="utf-8")

    test = G3_TEST.read_text(encoding="utf-8")
    test = replace_once(
        test,
        '''            # G6 is the earlier live-connection fence: the receipt tamper was committed by
            # a different SQLite connection, so the already-open store must reject that
            # revision before it reads the now-invalid checkpoint row.
            with self.assertRaisesRegex(
                PersistentAgencyError, "UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT"
            ):
                store.load_checkpoint("checkpoint-0")
''',
        '''            # G6 is the earlier live-connection fence: the receipt tamper was committed by
            # a different SQLite connection and changed WP206-owned checkpoint state, so the
            # already-open store must reject that owned-surface drift before reading the row.
            with self.assertRaisesRegex(
                PersistentAgencyError, "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT"
            ):
                store.load_checkpoint("checkpoint-0")
''',
        "G3 live-drift successor reason",
    )
    G3_TEST.write_text(test, encoding="utf-8")
    print("PATCHED_WP206_G6_REOPEN_MONITOR_AND_G3_SUCCESSOR_REASON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
