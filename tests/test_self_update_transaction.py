#!/usr/bin/env python3
"""Fail-closed regression suite for the self-update transaction wrapper.

F2-WP-1207 self-integration (run SELFINT-20260901-a1c9e2f4). Exercises
``frankenstein2.self_update_transaction`` (INSTALL/UPDATE/ROLLBACK, injected
pre/post-mutation failure, hostile-twin rejection, CAS/stale-state rejection,
replay/idempotency) purely against disposable ``tmp_path`` directories. Never
touches ``~/.claude`` or any real managed directory.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from frankenstein2.portable_release_transaction import PortableReleaseTransactionError
from frankenstein2.self_update_transaction import (
    SelfUpdateStore,
    SelfUpdateTransactionError,
    apply_rollback,
    apply_transaction,
    compute_state_digest,
    independent_readback,
    release_identity_for_payload,
)


def _store(base: Path) -> SelfUpdateStore:
    return SelfUpdateStore(managed_dir=base / "managed", control_dir=base / "control")


PAYLOAD_V1 = {"settings.json": b'{"v":1}', "star/unified.db": b"gen0-bytes"}
PAYLOAD_V2 = {"settings.json": b'{"v":2}', "star/unified.db": b"gen1-bytes"}
PAYLOAD_V3 = {"settings.json": b'{"v":3}', "star/unified.db": b"gen2-bytes"}


class SelfUpdateTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="selfint-unittest-")
        self.base = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---- P5: successful INSTALL then UPDATE -------------------------------
    def test_install_then_update_succeeds_and_advances_generation(self) -> None:
        store = _store(self.base)
        r1 = apply_transaction(
            store,
            operation="INSTALL",
            payload=PAYLOAD_V1,
            release_id="selfint-r1",
            version="1",
            attempt_id="install-1",
        )
        self.assertEqual(r1.receipt.outcome, "SUCCEEDED")
        self.assertEqual(r1.receipt.observed_generation, 0)

        r2 = apply_transaction(
            store,
            operation="UPDATE",
            payload=PAYLOAD_V2,
            release_id="selfint-r2",
            version="2",
            attempt_id="update-1",
        )
        self.assertEqual(r2.receipt.outcome, "SUCCEEDED")
        self.assertEqual(r2.receipt.observed_generation, 1)

        lineage = store.load_lineage()
        self.assertEqual(lineage.generation, 1)
        self.assertEqual(lineage.predecessor_generation, 0)
        self.assertEqual(compute_state_digest(store.managed_dir), lineage.state_sha256)

    def test_second_install_on_existing_lineage_is_rejected(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        with self.assertRaisesRegex(SelfUpdateTransactionError, "INSTALL requires an empty lineage"):
            apply_transaction(
                store, operation="INSTALL", payload=PAYLOAD_V2,
                release_id="r2", version="2", attempt_id="install-2",
            )

    # ---- P6: injected failure + exact rollback -----------------------------
    def test_injected_pre_mutation_failure_leaves_directory_untouched(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        before = compute_state_digest(store.managed_dir)
        result = apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-fail-pre",
            injected_failure_stage="pre_mutation",
        )
        self.assertEqual(result.receipt.outcome, "FAILED_NO_MUTATION")
        self.assertEqual(result.receipt.failure_code, "INJECTED_PRE_MUTATION")
        after = compute_state_digest(store.managed_dir)
        self.assertEqual(before, after)
        self.assertEqual(store.load_lineage().generation, 0)

    def test_injected_post_mutation_failure_restores_exact_predecessor_bytes(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        before = compute_state_digest(store.managed_dir)
        result = apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-fail-post",
            injected_failure_stage="post_mutation",
        )
        self.assertEqual(result.receipt.outcome, "ROLLED_BACK")
        self.assertEqual(result.receipt.failure_code, "INJECTED_POST_MUTATION")
        self.assertEqual(result.receipt.observed_state_sha256, before)
        after = compute_state_digest(store.managed_dir)
        self.assertEqual(before, after)
        # Failed attempt must not advance the generation counter.
        self.assertEqual(store.load_lineage().generation, 0)

    def test_explicit_rollback_mints_new_generation_with_predecessor_bytes(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        gen0_state = compute_state_digest(store.managed_dir)
        apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-1",
        )
        rb = apply_rollback(store, attempt_id="rollback-1")
        self.assertEqual(rb.receipt.outcome, "SUCCEEDED")
        self.assertEqual(rb.receipt.observed_generation, 2)
        self.assertEqual(rb.receipt.observed_state_sha256, gen0_state)
        lineage = store.load_lineage()
        self.assertEqual(lineage.generation, 2)
        self.assertEqual(lineage.state_sha256, gen0_state)
        self.assertEqual(compute_state_digest(store.managed_dir), gen0_state)

    def test_rollback_without_predecessor_fails_closed(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        with self.assertRaisesRegex(SelfUpdateTransactionError, "no predecessor recorded"):
            apply_rollback(store, attempt_id="rollback-nopred")

    # ---- P7: independent readback (in-process correctness; real proof needs
    #          a fresh interpreter process -- see integration_map.json) -------
    def test_independent_readback_matches_persisted_lineage(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-1",
        )
        readback = independent_readback(store.managed_dir, store.control_dir)
        self.assertTrue(readback["lineage_matches_observed"])
        self.assertEqual(readback["lineage"]["generation"], 1)

    # ---- P8: hostile-twin rejected before mutation -------------------------
    def test_hostile_twin_declared_release_rejected_before_mutation(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        before = compute_state_digest(store.managed_dir)
        forged_identity, _ = release_identity_for_payload(
            {"settings.json": b'{"v":"forged-does-not-match-real-payload"}'},
            release_id="r2-forged", version="2",
        )
        with self.assertRaisesRegex(SelfUpdateTransactionError, "hostile-twin rejected before mutation"):
            apply_transaction(
                store, operation="UPDATE", payload=PAYLOAD_V2,
                release_id="r2", version="2", attempt_id="update-hostile",
                declared_target_release=forged_identity,
            )
        after = compute_state_digest(store.managed_dir)
        self.assertEqual(before, after)
        self.assertEqual(store.load_lineage().generation, 0)

    # ---- P9: replay/idempotency --------------------------------------------
    def test_replaying_same_attempt_id_after_success_is_rejected_not_double_applied(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-1",
        )
        gen1_state = compute_state_digest(store.managed_dir)
        # Replaying the exact same UPDATE request (same payload/release) against the
        # now-advanced lineage must fail closed on CAS (expected_generation no longer
        # matches current lineage) rather than silently re-applying or duplicating state.
        with self.assertRaises(PortableReleaseTransactionError):
            apply_transaction(
                store, operation="UPDATE", payload=PAYLOAD_V2,
                release_id="r2", version="2", attempt_id="update-1-replay",
                expected_generation=0, expected_state_sha256=None,
            )
        self.assertEqual(compute_state_digest(store.managed_dir), gen1_state)
        self.assertEqual(store.load_lineage().generation, 1)

    # ---- P10: concurrent/stale-state CAS fail-closed -----------------------
    def test_stale_caller_expected_generation_is_rejected_fail_closed(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        gen0_lineage = store.load_lineage()
        # Caller B advances the lineage to generation 1.
        apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-caller-b",
        )
        gen1_state = compute_state_digest(store.managed_dir)
        # Caller A, still holding its stale gen0 belief, retries its own UPDATE.
        with self.assertRaisesRegex(PortableReleaseTransactionError, "generation"):
            apply_transaction(
                store, operation="UPDATE", payload=PAYLOAD_V3,
                release_id="r3", version="3", attempt_id="update-caller-a-stale",
                expected_generation=gen0_lineage.generation,
                expected_state_sha256=gen0_lineage.state_sha256,
            )
        # No split-brain / double-apply: state remains exactly caller B's generation 1.
        self.assertEqual(compute_state_digest(store.managed_dir), gen1_state)
        self.assertEqual(store.load_lineage().generation, 1)

    # ---- P6b (defect fix, coordinator report 2026-09-01): unknown
    #      injected_failure_stage must be refused fail-closed, BEFORE any
    #      mutation -- never fall through to _write_payload. Case policy is
    #      case-INSENSITIVE normalize-then-match (documented in
    #      _normalize_injected_failure_stage): "POST_MUTATION" is therefore a
    #      *recognized* alias of "post_mutation", not an unknown stage -- it is
    #      covered separately below. Only genuinely unrecognized strings (a
    #      typo like "bogus") must raise. ---------------------------------
    def test_unknown_injected_failure_stage_rejected_before_mutation(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        before_digest = compute_state_digest(store.managed_dir)
        before_lineage = store.load_lineage()
        for bogus_stage in ("bogus", "PRE-MUTATION-TYPO"):
            with self.assertRaises(SelfUpdateTransactionError):
                apply_transaction(
                    store, operation="UPDATE", payload=PAYLOAD_V2,
                    release_id="r2", version="2",
                    attempt_id=f"update-bogus-{bogus_stage}",
                    injected_failure_stage=bogus_stage,
                )
            after_digest = compute_state_digest(store.managed_dir)
            after_lineage = store.load_lineage()
            self.assertEqual(
                before_digest, after_digest,
                f"disk mutated for unknown stage {bogus_stage!r}",
            )
            self.assertEqual(before_lineage.generation, after_lineage.generation)
            self.assertEqual(before_lineage.state_sha256, after_lineage.state_sha256)

    # ---- documents the case-insensitive normalization decision: the exact
    #      string from the coordinator's repro ("POST_MUTATION") must now be
    #      *recognized* as an alias of "post_mutation" and handled via the
    #      normal, already-proven injected-post-mutation-failure path (exact
    #      rollback), not silently ignored and not raising a stage error. -----
    def test_uppercase_post_mutation_alias_is_normalized_and_handled(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        before = compute_state_digest(store.managed_dir)
        result = apply_transaction(
            store, operation="UPDATE", payload=PAYLOAD_V2,
            release_id="r2", version="2", attempt_id="update-fail-post-upper",
            injected_failure_stage="POST_MUTATION",
        )
        self.assertEqual(result.receipt.outcome, "ROLLED_BACK")
        self.assertEqual(result.receipt.observed_state_sha256, before)
        self.assertEqual(compute_state_digest(store.managed_dir), before)
        self.assertEqual(store.load_lineage().generation, 0)

    # ---- P6c (defect fix): if a mutation DOES happen and something after it
    #      raises (any PortableReleaseTransactionError/SelfUpdateTransactionError,
    #      not just the two known injected stages), disk must be restored to
    #      plan.source_state_sha256 before the exception propagates -- never
    #      leave disk != lineage. -------------------------------------------
    def test_forced_post_mutation_exception_restores_source_state_before_raise(self) -> None:
        store = _store(self.base)
        apply_transaction(
            store, operation="INSTALL", payload=PAYLOAD_V1,
            release_id="r1", version="1", attempt_id="install-1",
        )
        source_state_sha256 = store.load_lineage().state_sha256
        self.assertEqual(source_state_sha256, compute_state_digest(store.managed_dir))

        with self.assertRaises((SelfUpdateTransactionError, PortableReleaseTransactionError)):
            apply_transaction(
                store, operation="UPDATE", payload=PAYLOAD_V2,
                release_id="r2", version="2", attempt_id="update-bogus-post",
                injected_failure_stage="bogus",
            )

        after_digest = compute_state_digest(store.managed_dir)
        after_lineage = store.load_lineage()
        self.assertEqual(
            after_digest, source_state_sha256,
            "torn state: disk digest does not match plan.source_state_sha256 after raise",
        )
        self.assertEqual(after_lineage.generation, 0)
        self.assertEqual(after_lineage.state_sha256, source_state_sha256)

    # ---- control_dir/managed_dir nesting guard ------------------------------
    def test_control_dir_nested_inside_managed_dir_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            SelfUpdateTransactionError, "must not be nested"
        ):
            SelfUpdateStore(
                managed_dir=self.base / "managed",
                control_dir=self.base / "managed" / "control",
            )


if __name__ == "__main__":
    unittest.main()
