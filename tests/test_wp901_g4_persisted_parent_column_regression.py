#!/usr/bin/env python3
"""Canonical regression for WP901 G4 redundant persisted parent-column binding."""
from __future__ import annotations

import unittest

from frankenstein2.persistent_agency_kernel import CHECKPOINT_TABLE
from frankenstein2.restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationError,
    attest_persisted_checkpoint_load,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G4PersistedParentColumnRegression(unittest.TestCase):
    setUp = PersistedRowLoadAttestationTests.setUp
    tearDown = PersistedRowLoadAttestationTests.tearDown
    sources = PersistedRowLoadAttestationTests.sources
    identity = staticmethod(PersistedRowLoadAttestationTests.identity)
    authority = staticmethod(PersistedRowLoadAttestationTests.authority)

    def test_persisted_parent_column_must_match_loaded_checkpoint(self) -> None:
        _, checkpoint, _, _, _ = self.sources()
        forged_parent = checkpoint.checkpoint_id
        self.assertNotEqual(forged_parent, checkpoint.previous_checkpoint_id)

        self.store.connection.execute(
            f"""UPDATE {CHECKPOINT_TABLE}
                SET previous_checkpoint_id=? WHERE checkpoint_id=?""",
            (forged_parent, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()

        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_PREVIOUS_CHECKPOINT_ID_MISMATCH",
        ):
            attest_persisted_checkpoint_load(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
