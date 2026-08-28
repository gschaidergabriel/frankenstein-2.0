from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from frankenstein2.current_entityos_effect_authority_binding import (
    load_current_entityos_effect_authority_binding,
)


BINDING_PATH = Path(
    "research_entity/continuity/ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING_V1.json"
)
ATTESTATION_PATH = Path(
    "research_entity/continuity/"
    "ENTITYOS_EFFECT_AUTHORITY_BINDING_8_78_ADMITTED_AUTHORITY_REENTRY_2026-08-29.json"
)
BINDING_BLOB = "b4d91a0dd233c9dc15ff8218feea9248ac1c13c5"
BINDING_COMMIT = "5638204026468b631de5e774e8403d7a6334021e"
ATTESTATION_COMMIT = "76e2b8383e597be14af8210b3616c572bea3a934"
IMPLEMENTATION_COMMIT = "2b68aad14bf7824d513b52898904909256e3522d"


def _roots() -> tuple[Path, Path]:
    meta = os.environ.get("ENTITYOS_META_ROOT")
    impl = os.environ.get("ENTITYOS_IMPL_ROOT")
    if not meta or not impl:
        raise RuntimeError("ENTITYOS_META_ROOT and ENTITYOS_IMPL_ROOT are required")
    return Path(meta).resolve(), Path(impl).resolve()


def _load_external_modules(impl_root: Path):
    artefact = impl_root / "the artefact"
    if not artefact.is_dir():
        raise RuntimeError(f"missing exact EntityOS artefact root: {artefact}")
    sys.path.insert(0, str(artefact))
    from clayverse.effect_journal import EffectJournal
    from clayverse.effects import EffectGate, EffectRequest
    from clayverse.store import UnifiedDB

    return EffectJournal, EffectGate, EffectRequest, UnifiedDB


class ExactBoundEntityOSEffectRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.meta_root, cls.impl_root = _roots()
        binding_doc = json.loads((cls.meta_root / BINDING_PATH).read_text())
        attestation_doc = json.loads((cls.meta_root / ATTESTATION_PATH).read_text())
        cls.binding = load_current_entityos_effect_authority_binding(
            binding_document=binding_doc,
            binding_record_path=str(BINDING_PATH),
            binding_record_blob_sha=BINDING_BLOB,
            binding_record_commit_sha=BINDING_COMMIT,
            attestation_document=attestation_doc,
            attestation_path=str(ATTESTATION_PATH),
            attestation_commit_sha=ATTESTATION_COMMIT,
        )
        (
            cls.EffectJournal,
            cls.EffectGate,
            cls.EffectRequest,
            cls.UnifiedDB,
        ) = _load_external_modules(cls.impl_root)

    def test_current_binding_resolves_exact_runtime_tuple(self) -> None:
        self.assertEqual(self.binding.implementation_commit_sha, IMPLEMENTATION_COMMIT)
        self.assertEqual(
            self.binding.effect_gate_blob_sha,
            "4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
        )
        self.assertEqual(
            self.binding.effect_journal_blob_sha,
            "cda63471f1467481f2ff79032d3931730a334a20",
        )
        self.assertEqual(
            self.binding.unifieddb_blob_sha,
            "a88d923ea3d0eab5847f304f35463e5a2b2c4acd",
        )
        self.assertEqual(self.binding.supervisor_epoch, "8.78")
        self.assertEqual(self.binding.supervisor_delta, "SUPERVISOR_STEERING_8_78")

    def test_exact_effectgate_state_noop_journals_pending_then_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self.UnifiedDB(Path(tmp) / "unified.db")
            try:
                db.ensure_user("user-A", "User A")
                session_id = db.ensure_session("user-A", "terminal-A")
                gate = self.EffectGate(db)
                effect_id, outcome = gate.execute(
                    self.EffectRequest(
                        user_id="user-A",
                        session_id=session_id,
                        capability="state.noop",
                        target="wp105-zero-real-effect",
                        argv=None,
                        expected_generation=db.session_generation(session_id),
                    )
                )
                row = db.db.execute(
                    "SELECT status,capability,outcome FROM effects WHERE effect_id=?",
                    (effect_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["status"], "VERIFIED")
                self.assertEqual(row["capability"], "state.noop")
                self.assertTrue(outcome["ok"])
                self.assertEqual(outcome["boundary"], "internal")
                causal = db.db.execute(
                    "SELECT causal_id,reentered FROM causal_episodes WHERE effect_id=?",
                    (effect_id,),
                ).fetchone()
                self.assertIsNotNone(causal)
                self.assertEqual(causal["reentered"], 1)
            finally:
                db.close()

    def test_exact_journal_restart_converts_pending_to_unknown_without_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unified.db"
            db = self.UnifiedDB(path)
            db.ensure_user("user-A", "User A")
            session_id = db.ensure_session("user-A", "terminal-A")
            generation = db.session_generation(session_id)
            journal = self.EffectJournal(db)
            effect_id = journal.begin(
                None,
                session_id,
                "user-A",
                "state.noop",
                "wp105-restart-unknown",
                generation,
                None,
            )
            pending = db.db.execute(
                "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
            ).fetchone()
            self.assertEqual(pending["status"], "PENDING")
            db.close()

            db = self.UnifiedDB(path)
            try:
                journal = self.EffectJournal(db)
                self.assertEqual(journal.recover_pending(), 1)
                row = db.db.execute(
                    "SELECT status,outcome FROM effects WHERE effect_id=?", (effect_id,)
                ).fetchone()
                self.assertEqual(row["status"], "UNKNOWN_AFTER_RESTART")
                self.assertEqual(journal.recover_pending(), 0)
                count = db.db.execute(
                    "SELECT count(*) FROM effects WHERE effect_id=?", (effect_id,)
                ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
