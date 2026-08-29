from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest


CANONICAL_ROOT_RAW = os.environ.get("ENTITYOS_CANONICAL_ROOT")
CANONICAL_ROOT = Path(CANONICAL_ROOT_RAW).resolve() if CANONICAL_ROOT_RAW else None
if CANONICAL_ROOT is not None:
    sys.path.insert(0, str(CANONICAL_ROOT / "the artefact"))
    from clayverse.effects import EffectGate, EffectRequest  # type: ignore[import-not-found]
    from clayverse.store import UnifiedDB  # type: ignore[import-not-found]
else:  # pragma: no cover - dedicated CI supplies exact canonical source.
    EffectGate = EffectRequest = UnifiedDB = None  # type: ignore[assignment]


class HarmlessAmbiguousMarkerBridge:
    """Local marker only: proves executor-boundary entry without a real external effect."""

    sha256 = "a" * 64

    def __init__(self, marker_path: Path) -> None:
        self.marker_path = marker_path

    def run(self, argv):
        prior = int(self.marker_path.read_text() or "0") if self.marker_path.exists() else 0
        self.marker_path.write_text(str(prior + 1))
        raise RuntimeError("simulated_post_start_ambiguity")


@unittest.skipUnless(CANONICAL_ROOT is not None, "exact canonical EntityOS checkout required")
class ExactSourceDirectEpisodeNullReplayGapTests(unittest.TestCase):
    """NEGATIVE_RESULT: current exact source re-dispatches an episode_id=None retry."""

    def test_reopen_replays_same_direct_operation_after_post_start_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "unified.db"
            marker = root / "child-start-count.txt"

            db = UnifiedDB(db_path)
            db.ensure_user("user-direct-A", "Direct User")
            session_id = db.ensure_session("user-direct-A", "terminal-direct-A")
            generation = db.session_generation(session_id)
            request = EffectRequest(
                user_id="user-direct-A",
                session_id=session_id,
                capability="entityos.exec",
                target="wp105-direct-episode-null-replay-probe",
                argv=["harmless-marker", "same-logical-operation"],
                expected_generation=generation,
            )

            first_gate = EffectGate(
                db, entityos_bridge=HarmlessAmbiguousMarkerBridge(marker)
            )
            with self.assertRaisesRegex(RuntimeError, "simulated_post_start_ambiguity"):
                first_gate.execute(request, episode_id=None)
            first_rows = db.db.execute(
                "SELECT effect_id,episode_id,status FROM effects ORDER BY ts,effect_id"
            ).fetchall()
            self.assertEqual(len(first_rows), 1)
            self.assertIsNone(first_rows[0]["episode_id"])
            self.assertEqual(first_rows[0]["status"], "FAILED")
            self.assertEqual(marker.read_text(), "1")
            first_effect_id = first_rows[0]["effect_id"]
            db.close()

            reopened = UnifiedDB(db_path)
            second_gate = EffectGate(
                reopened, entityos_bridge=HarmlessAmbiguousMarkerBridge(marker)
            )
            with self.assertRaisesRegex(RuntimeError, "simulated_post_start_ambiguity"):
                second_gate.execute(request, episode_id=None)

            rows = reopened.db.execute(
                "SELECT effect_id,episode_id,status FROM effects ORDER BY ts,effect_id"
            ).fetchall()
            self.assertEqual(marker.read_text(), "2")
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[1]["effect_id"], first_effect_id)
            self.assertIsNone(rows[1]["episode_id"])
            self.assertEqual([row["status"] for row in rows], ["FAILED", "FAILED"])
            reopened.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
