from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from frankenstein2.effect_executor_interlock import ExecutorOutcomeUnknown
from frankenstein2.entityos_unknown_outcome_adapter import (
    EntityOSUnknownOutcomeAdapterError,
    translate_executor_unknown_to_canonical,
)


FIXTURE = Path(__file__).parent / "fixtures" / "entityos_effect_unknown_pr430_2f99" / "clayverse"
BOUND_STORE = Path(__file__).parent / "fixtures" / "entityos_effect_authority_2b68" / "clayverse" / "store.py"
EXPECTED_GIT_BLOBS = {
    "effects.py": "ae1b8db9111868374258435e97c7dfeda41bc318",
    "effect_journal.py": "4615150638dc4409317550d44b84d942a260de58",
    "entityos_bridge.py": "7781580f4e862c23491cc862e19c5d1f62b3ada6",
    "store.py": "a88d923ea3d0eab5847f304f35463e5a2b2c4acd",
}
PR430_HEAD = "2f99e400f1c0ea1b8598573ab0fab993885cba5e"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


class PR430ExactCandidateUnknownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        package = cls.root / "pr430_clayverse"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        for name in ("effects.py", "effect_journal.py", "entityos_bridge.py"):
            shutil.copyfile(FIXTURE / name, package / name)
        shutil.copyfile(BOUND_STORE, package / "store.py")
        sys.path.insert(0, str(cls.root))
        cls.effects = importlib.import_module("pr430_clayverse.effects")
        cls.bridge_module = importlib.import_module("pr430_clayverse.entityos_bridge")
        cls.store_module = importlib.import_module("pr430_clayverse.store")

    @classmethod
    def tearDownClass(cls) -> None:
        sys.path.remove(str(cls.root))
        for name in list(sys.modules):
            if name == "pr430_clayverse" or name.startswith("pr430_clayverse."):
                sys.modules.pop(name, None)
        cls.temp.cleanup()

    def setUp(self) -> None:
        self.db_temp = tempfile.TemporaryDirectory()
        self.db = self.store_module.UnifiedDB(Path(self.db_temp.name) / "unified.db")
        self.user_id = "pr430-user"
        self.db.ensure_user(self.user_id, "PR430 Candidate User")
        self.session_id = self.db.ensure_session(self.user_id, "pr430-candidate-session")
        self.generation = self.db.session_generation(self.session_id)

    def tearDown(self) -> None:
        self.db.close()
        self.db_temp.cleanup()

    def latest_effect(self):
        return self.db.db.execute(
            "SELECT effect_id,status,outcome FROM effects ORDER BY ts DESC,effect_id DESC LIMIT 1"
        ).fetchone()

    def request(self):
        return self.effects.EffectRequest(
            self.user_id,
            self.session_id,
            "entityos.exec",
            "candidate-only",
            ["payload"],
            self.generation,
        )

    def test_fixture_is_byte_exact_pr430_candidate(self) -> None:
        self.assertEqual(git_blob_sha(FIXTURE / "effects.py"), EXPECTED_GIT_BLOBS["effects.py"])
        self.assertEqual(git_blob_sha(FIXTURE / "effect_journal.py"), EXPECTED_GIT_BLOBS["effect_journal.py"])
        self.assertEqual(git_blob_sha(FIXTURE / "entityos_bridge.py"), EXPECTED_GIT_BLOBS["entityos_bridge.py"])
        self.assertEqual(git_blob_sha(BOUND_STORE), EXPECTED_GIT_BLOBS["store.py"])

    def _assert_bridge_return_path_becomes_unknown(self, exc: Exception) -> None:
        bridge = self.bridge_module.EntityOSBridge("/unused", "a" * 64, timeout=0.01)

        class StartedProcess:
            returncode = None

            def __init__(self):
                self.killed = False
                self.waited = False

            def communicate(self, *, timeout):
                raise exc

            def kill(self):
                self.killed = True

            def wait(self, *, timeout):
                self.waited = True
                self.returncode = -9
                return self.returncode

        proc = StartedProcess()
        with patch.object(
            self.bridge_module.EntityOSBridge,
            "_open_verified",
            lambda _self: os.open("/dev/null", os.O_RDONLY),
        ), patch.object(self.bridge_module.subprocess, "Popen", lambda *_args, **_kwargs: proc):
            with self.assertRaises(self.bridge_module.EntityOSOutcomeUnknown) as caught:
                bridge.run(["payload"])
        self.assertFalse(caught.exception.replay_permitted)
        self.assertTrue(proc.killed)
        self.assertTrue(proc.waited)

    def test_exact_pr430_timeout_after_popen_is_unknown_nonreplayable(self) -> None:
        self._assert_bridge_return_path_becomes_unknown(
            subprocess.TimeoutExpired(cmd=["EntityOS"], timeout=0.01)
        )

    def test_exact_pr430_ordinary_error_after_popen_is_unknown_nonreplayable(self) -> None:
        self._assert_bridge_return_path_becomes_unknown(OSError("result channel lost"))

    def test_exact_pr430_native_unknown_terminalizes_unknown_outcome(self) -> None:
        candidate_unknown = self.bridge_module.EntityOSOutcomeUnknown

        class NativeUnknownBridge:
            sha256 = "a" * 64

            def run(self, _argv):
                raise candidate_unknown("return channel lost after child start")

        gate = self.effects.EffectGate(self.db, entityos_bridge=NativeUnknownBridge())
        with self.assertRaises(candidate_unknown):
            gate.execute(self.request())

        row = self.latest_effect()
        self.assertEqual(row["status"], "UNKNOWN_OUTCOME")
        receipt = json.loads(row["outcome"])
        self.assertEqual(receipt["certainty"], "unknown")
        self.assertEqual(receipt["error"], "EntityOSOutcomeUnknown")
        self.assertNotIn("ok", receipt)
        causal = self.db.db.execute(
            "SELECT credit,reentered FROM causal_episodes WHERE effect_id=?",
            (row["effect_id"],),
        ).fetchone()
        self.assertEqual(causal["credit"], 0.0)
        self.assertEqual(causal["reentered"], 1)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)

    def test_counterexample_f2_executor_unknown_is_not_pr430_native_unknown(self) -> None:
        candidate_unknown = self.bridge_module.EntityOSOutcomeUnknown
        self.assertFalse(issubclass(ExecutorOutcomeUnknown, candidate_unknown))

        class F2UnknownBridge:
            sha256 = "b" * 64

            def run(self, _argv):
                raise ExecutorOutcomeUnknown("EXECUTOR_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY")

        gate = self.effects.EffectGate(self.db, entityos_bridge=F2UnknownBridge())
        with self.assertRaises(ExecutorOutcomeUnknown):
            gate.execute(self.request())

        row = self.latest_effect()
        self.assertEqual(row["status"], "FAILED")
        receipt = json.loads(row["outcome"])
        self.assertEqual(receipt["error"], "ExecutorOutcomeUnknown")
        self.assertEqual(receipt["reason"], "entityos_execution_failure")
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)

    def test_adapter_translates_only_f2_unknown_into_candidate_canonical_unknown(self) -> None:
        candidate_unknown = self.bridge_module.EntityOSOutcomeUnknown

        class AdaptedF2UnknownBridge:
            sha256 = "c" * 64

            def run(self, _argv):
                def dispatch():
                    raise ExecutorOutcomeUnknown(
                        "EXECUTOR_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY"
                    )

                return translate_executor_unknown_to_canonical(
                    dispatch,
                    canonical_unknown_type=candidate_unknown,
                )

        gate = self.effects.EffectGate(self.db, entityos_bridge=AdaptedF2UnknownBridge())
        with self.assertRaises(candidate_unknown) as caught:
            gate.execute(self.request())
        self.assertFalse(caught.exception.replay_permitted)

        row = self.latest_effect()
        self.assertEqual(row["status"], "UNKNOWN_OUTCOME")
        receipt = json.loads(row["outcome"])
        self.assertEqual(receipt["certainty"], "unknown")
        self.assertEqual(receipt["error"], "EntityOSOutcomeUnknown")
        self.assertEqual(receipt["reason"], "entityos_outcome_unknown")
        causal = self.db.db.execute(
            "SELECT credit,reentered FROM causal_episodes WHERE effect_id=?",
            (row["effect_id"],),
        ).fetchone()
        self.assertEqual(causal["credit"], 0.0)
        self.assertEqual(causal["reentered"], 1)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)

    def test_bad_canonical_unknown_contract_fails_before_dispatch(self) -> None:
        calls = 0

        class UnsafeUnknown(RuntimeError):
            replay_permitted = True

        def dispatch():
            nonlocal calls
            calls += 1
            raise AssertionError("dispatch must not run")

        with self.assertRaisesRegex(
            EntityOSUnknownOutcomeAdapterError,
            "CANONICAL_UNKNOWN_MUST_FORBID_REPLAY",
        ):
            translate_executor_unknown_to_canonical(
                dispatch,
                canonical_unknown_type=UnsafeUnknown,
            )
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
