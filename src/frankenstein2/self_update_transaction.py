"""Fail-closed self-update transaction wrapper for a Frankenstein config/state directory.

F2-WP-1207 self-integration (run SELFINT-20260901-a1c9e2f4).

This module WRAPS the ACCEPTED G10 canonical primitives in
``frankenstein2.portable_release_transaction`` (``build_transaction_plan``,
``record_attempt``). It does not fork or modify that module. That module is pure
planning/validation with no filesystem or process I/O; this module adds the actual
disk mutation, snapshot/rollback and independent-readback plumbing needed to apply
those plans to a real managed directory, while keeping the accepted plan/receipt
validation as the single source of truth for what counts as SUCCEEDED, FAILED, or
ROLLED_BACK.

SANDBOX CONTRACT (enforced by the caller, not by this module): ``managed_dir`` MUST be
a disposable directory. This module never knows about or touches ``~/.claude``; it
operates purely on whatever paths it is given.

State identity
---------------
``state_sha256`` of a managed directory = sha256(canonical_json({relpath: sha256(bytes)}))
over every regular file under ``managed_dir`` (sorted, POSIX-style relative paths).
This is a metadata digest (per-file content hash, not raw concatenation), so it is cheap
to compute even for large files such as a 60MB sqlite copy.

Lineage store (``control_dir/lineage.json``): the current
``portable_release_transaction.StateLineage`` as an exact mapping, or absent before the
first INSTALL.

Generation history (``control_dir/history.json``): list of ``{generation, release,
state_sha256}`` for every generation this store has ever reached. Needed to reconstruct
the exact ``ReleaseIdentity`` mapping for an explicit ROLLBACK plan, because the accepted
lineage schema only carries a release *digest*, not the full mapping.

Generation snapshots (``control_dir/snapshots/gen_<N>/``): full copy of ``managed_dir``
content at the moment generation N became active. Used to restore exact bytes during
failed-attempt recovery and explicit rollback.

Two distinct recovery mechanisms, both provided by the accepted primitive's own receipt
semantics (see ``portable_release_transaction.record_attempt``):

1. Failed-attempt recovery (``ROLLED_BACK`` outcome on an INSTALL/UPDATE plan): abort the
   attempt and prove the managed directory is back to exactly the state it was in
   immediately before the attempt started. ``record_attempt`` binds this to
   ``plan.source_generation`` / ``plan.source_state_sha256`` -- NOT to
   ``plan.rollback_target_state_sha256``, which is ``None`` for INSTALL/UPDATE plans.
2. Explicit ROLLBACK operation (``SUCCEEDED`` outcome on a ROLLBACK plan): deliberately
   move to the exact predecessor generation's content, minted as a *new* forward
   generation (never rewinds the generation counter). ``record_attempt`` binds this to
   ``plan.rollback_target_state_sha256``.

Both are implemented here (``apply_install``/``apply_update`` cover (1) via
``injected_failure_stage`` or observed-digest mismatch; ``apply_rollback`` covers (2)).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Mapping

from frankenstein2.portable_release_transaction import (
    AttemptReceipt,
    LINEAGE_SCHEMA,
    PortableReleaseTransactionError,
    ReleaseIdentity,
    RELEASE_SCHEMA,
    REQUEST_SCHEMA,
    StateLineage,
    TransactionPlan,
    build_transaction_plan,
    record_attempt,
)

SELF_UPDATE_SCHEMA = "FRANKENSTEIN2_SELF_UPDATE_TRANSACTION/v1"

# Whitelist of stage names this wrapper knows how to inject a failure at. Any other
# value (None excluded) is a caller programming error and MUST be refused before any
# mutation -- never silently fall through to the mutate/verify path. Case policy:
# accepted case-insensitively and normalized to this canonical lowercase form (the
# alternative -- demanding exact-case -- was rejected because the canonical
# portable_release_transaction module itself uses UPPERCASE stage-adjacent names
# elsewhere (e.g. outcomes), making an uppercase caller typo entirely plausible and
# worth tolerating rather than silently mis-routing).
KNOWN_INJECTED_FAILURE_STAGES = frozenset({"pre_mutation", "post_mutation"})


class SelfUpdateTransactionError(ValueError):
    """Fail-closed self-update wrapper error (distinct from the wrapped primitive's error)."""


def _normalize_injected_failure_stage(injected_failure_stage: str | None) -> str | None:
    """Fail-closed whitelist for ``injected_failure_stage``.

    ``None`` passes through unchanged (no failure injection requested). Any other value
    is stripped and lowercased, then checked against ``KNOWN_INJECTED_FAILURE_STAGES``.
    An unrecognized value (typo, wrong case treated as a *different* string, a caller
    using the canonical module's own uppercase style, garbage) raises immediately --
    BEFORE the caller has built a plan or written a single byte to disk. This closes a
    defect where an unrecognized stage string used to fall through both the
    ``pre_mutation`` and ``post_mutation`` branches, reach ``_write_payload`` (a real
    mutation), and only then be rejected by the wrapped primitive's own
    ``record_attempt`` (which refuses to mint a SUCCEEDED receipt whenever
    ``injected_failure_stage`` is non-``None``, regardless of its exact text) -- by
    which point the directory was already mutated and torn state resulted.
    """

    if injected_failure_stage is None:
        return None
    normalized = injected_failure_stage.strip().lower()
    if normalized not in KNOWN_INJECTED_FAILURE_STAGES:
        raise SelfUpdateTransactionError(
            "unknown injected_failure_stage "
            f"{injected_failure_stage!r}; must be None or one of "
            f"{sorted(KNOWN_INJECTED_FAILURE_STAGES)} (case-insensitive) -- refused "
            "before any mutation"
        )
    return normalized


def _recover_from_unexpected_post_mutation_failure(
    store: "SelfUpdateStore",
    *,
    restore_generation: int | None,
    expected_state_sha256: str | None,
) -> None:
    """Last-resort fail-closed recovery for an exception raised AFTER a real mutation
    already happened, that was not already handled by one of the explicit
    injected-failure / verification-mismatch recovery branches (for example:
    ``record_attempt`` itself rejecting the outcome for a reason not anticipated by the
    caller). Restores the exact pre-attempt bytes for ``restore_generation`` (``None``
    means "no predecessor snapshot exists -- restore to an empty/absent directory", the
    correct predecessor for a failed first INSTALL) and verifies the restored digest
    equals ``expected_state_sha256`` before letting the triggering exception propagate.

    Disk must never be left disagreeing with the still-unchanged lineage record. If the
    restore itself cannot reproduce the expected digest, this raises a distinct hard
    error naming both digests instead of silently letting the original exception mask a
    still-torn managed_dir.
    """

    if restore_generation is None:
        if store.managed_dir.exists():
            shutil.rmtree(store.managed_dir)
        restored_state = None
    else:
        store._restore_snapshot(restore_generation)
        restored_state = compute_state_digest(store.managed_dir)
    if restored_state != expected_state_sha256:
        raise SelfUpdateTransactionError(
            "RECOVERY FAILED after an unexpected post-mutation error: managed_dir was "
            "restored but does not match the expected predecessor state -- disk and "
            f"lineage may now disagree. expected_state_sha256={expected_state_sha256!r} "
            f"restored_state_sha256={restored_state!r}"
        )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- manifest


def compute_manifest(managed_dir: Path) -> dict[str, str]:
    """relpath (POSIX, sorted) -> sha256(file bytes) for every regular file under managed_dir."""

    managed_dir = Path(managed_dir)
    entries: dict[str, str] = {}
    if not managed_dir.exists():
        return entries
    for root, _dirs, files in os.walk(managed_dir):
        for name in files:
            full = Path(root) / name
            rel = full.relative_to(managed_dir).as_posix()
            entries[rel] = _sha256_file(full)
    return dict(sorted(entries.items()))


def compute_state_digest(managed_dir: Path) -> str:
    """Independent, fresh-process-safe digest of a managed directory's exact content."""

    return _sha256_text(compute_manifest(managed_dir))


def _manifest_digest(manifest: Mapping[str, str]) -> str:
    return _sha256_text(dict(manifest))


def _artifact_digest(manifest: Mapping[str, str]) -> str:
    # Distinct derivation from manifest_sha256 (adds file sizes are not tracked here;
    # instead this covers the sorted (path, hash) pair list as a flat list rather than
    # a mapping, giving a different digest for the same underlying facts).
    pairs = sorted(manifest.items())
    return _sha256_text(pairs)


def release_identity_for_payload(
    payload: Mapping[str, bytes], *, release_id: str, version: str
) -> tuple[ReleaseIdentity, dict[str, str]]:
    manifest = {path: _sha256_bytes(data) for path, data in payload.items()}
    manifest = dict(sorted(manifest.items()))
    identity = ReleaseIdentity(
        schema=RELEASE_SCHEMA,
        release_id=release_id,
        version=version,
        artifact_sha256=_artifact_digest(manifest),
        manifest_sha256=_manifest_digest(manifest),
    )
    return identity, manifest


# --------------------------------------------------------------------------- store


@dataclass(frozen=True, slots=True)
class SelfUpdateStore:
    """Filesystem-backed control plane for one managed directory.

    ``control_dir`` MUST NOT be nested inside ``managed_dir`` (state digests would
    otherwise include the control plane's own bookkeeping and become self-referential).
    """

    managed_dir: Path
    control_dir: Path

    def __post_init__(self) -> None:
        managed = Path(self.managed_dir).resolve()
        control = Path(self.control_dir).resolve()
        if control == managed or control in managed.parents or managed in control.parents:
            raise SelfUpdateTransactionError(
                "control_dir must not be nested inside/outside managed_dir's own tree"
            )
        object.__setattr__(self, "managed_dir", managed)
        object.__setattr__(self, "control_dir", control)

    # -- paths ---------------------------------------------------------------
    @property
    def lineage_path(self) -> Path:
        return self.control_dir / "lineage.json"

    @property
    def history_path(self) -> Path:
        return self.control_dir / "history.json"

    @property
    def snapshots_dir(self) -> Path:
        return self.control_dir / "snapshots"

    def snapshot_path(self, generation: int) -> Path:
        return self.snapshots_dir / f"gen_{generation}"

    # -- lineage ---------------------------------------------------------------
    def load_lineage(self) -> StateLineage | None:
        if not self.lineage_path.exists():
            return None
        raw = json.loads(self.lineage_path.read_text(encoding="utf-8"))
        return StateLineage.from_mapping(raw)

    def _save_lineage(self, lineage: StateLineage | None) -> None:
        self.control_dir.mkdir(parents=True, exist_ok=True)
        if lineage is None:
            if self.lineage_path.exists():
                self.lineage_path.unlink()
            return
        self.lineage_path.write_text(_canonical_json(lineage.as_dict()), encoding="utf-8")

    # -- history (needed to reconstruct full ReleaseIdentity for ROLLBACK) ------
    def load_history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        return json.loads(self.history_path.read_text(encoding="utf-8"))

    def _append_history(self, generation: int, release: ReleaseIdentity, state_sha256: str) -> None:
        history = self.load_history()
        history.append(
            {"generation": generation, "release": release.as_dict(), "state_sha256": state_sha256}
        )
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(_canonical_json(history), encoding="utf-8")

    def _release_for_generation(self, generation: int) -> ReleaseIdentity:
        for entry in self.load_history():
            if entry["generation"] == generation:
                return ReleaseIdentity.from_mapping(entry["release"])
        raise SelfUpdateTransactionError(f"no recorded release identity for generation {generation}")

    # -- snapshots ---------------------------------------------------------------
    def _snapshot_current(self, generation: int) -> None:
        dest = self.snapshot_path(generation)
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.managed_dir.exists():
            shutil.copytree(self.managed_dir, dest)
        else:
            dest.mkdir(parents=True, exist_ok=True)

    def _restore_snapshot(self, generation: int) -> None:
        src = self.snapshot_path(generation)
        if not src.exists():
            raise SelfUpdateTransactionError(f"no snapshot recorded for generation {generation}")
        if self.managed_dir.exists():
            shutil.rmtree(self.managed_dir)
        shutil.copytree(src, self.managed_dir)


# --------------------------------------------------------------------------- helpers


def _write_payload(managed_dir: Path, payload: Mapping[str, bytes]) -> None:
    if managed_dir.exists():
        shutil.rmtree(managed_dir)
    managed_dir.mkdir(parents=True, exist_ok=True)
    for rel, data in payload.items():
        dest = managed_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def _request_dict(
    *,
    attempt_id: str,
    operation: str,
    target_release: ReleaseIdentity,
    current_lineage: StateLineage | None,
    rollback_release: ReleaseIdentity | None,
    injected_failure_stage: str | None,
    expected_generation: int | None = -1,
    expected_state_sha256: str | None = -1,
) -> dict[str, Any]:
    """Build the raw TransactionRequest mapping.

    ``expected_generation``/``expected_state_sha256`` default sentinel (``-1``, distinct
    from a legitimate ``None``) means "trust ``current_lineage`` as the caller's belief" --
    the normal read-then-write path. A caller that wants to simulate a CONCURRENT/STALE
    client (P10) passes its own, possibly-outdated, explicit ``expected_generation`` /
    ``expected_state_sha256`` here; the accepted primitive's own CAS check
    (``TransactionRequest._validate_semantics``) then rejects the request fail-closed if it
    no longer matches the fresh ``current_lineage`` read from disk.
    """

    lineage_dict = None if current_lineage is None else current_lineage.as_dict()
    if expected_generation == -1:
        expected_generation = None if current_lineage is None else current_lineage.generation
    if expected_state_sha256 == -1:
        expected_state_sha256 = None if current_lineage is None else current_lineage.state_sha256
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": attempt_id,
        "operation": operation,
        "target_release": target_release.as_dict(),
        "current_lineage": lineage_dict,
        "expected_generation": expected_generation,
        "expected_state_sha256": expected_state_sha256,
        "rollback_release": None if rollback_release is None else rollback_release.as_dict(),
        "injected_failure_stage": injected_failure_stage,
    }


@dataclass(frozen=True, slots=True)
class SelfUpdateResult:
    plan: TransactionPlan
    receipt: AttemptReceipt
    duration_total_ms: float
    failure_detection_ms: float | None
    rollback_duration_ms: float | None


# --------------------------------------------------------------------------- INSTALL/UPDATE


def apply_transaction(
    store: SelfUpdateStore,
    *,
    operation: str,
    payload: Mapping[str, bytes],
    release_id: str,
    version: str,
    attempt_id: str,
    injected_failure_stage: str | None = None,
    declared_target_release: ReleaseIdentity | None = None,
    expected_generation: int | None = -1,
    expected_state_sha256: str | None = -1,
) -> SelfUpdateResult:
    """Apply an INSTALL or UPDATE transaction against ``store.managed_dir``.

    ``declared_target_release`` lets a caller assert a target identity that may not match
    the actual payload bytes (hostile-twin test, P8): if it disagrees with the identity
    computed from ``payload``, the accepted plan validation rejects the request before any
    mutation happens (``target_release`` and payload are always cross-checked here).

    ``expected_generation``/``expected_state_sha256`` default to "trust the freshly loaded
    lineage" (the normal path). Pass explicit, possibly-stale values to simulate a
    concurrent caller acting on outdated knowledge (P10): the accepted primitive's CAS
    check then rejects fail-closed instead of silently applying on top of newer state.
    """

    t0 = time.monotonic()
    if operation not in ("INSTALL", "UPDATE"):
        raise SelfUpdateTransactionError("apply_transaction only handles INSTALL/UPDATE")
    # Whitelist BEFORE any plan is built or any byte is written -- see
    # _normalize_injected_failure_stage docstring for the defect this closes.
    injected_failure_stage = _normalize_injected_failure_stage(injected_failure_stage)

    current_lineage = store.load_lineage()
    if operation == "INSTALL" and current_lineage is not None:
        raise SelfUpdateTransactionError("INSTALL requires an empty lineage; use UPDATE")
    if operation == "UPDATE" and current_lineage is None:
        raise SelfUpdateTransactionError("UPDATE requires an existing lineage; use INSTALL")

    computed_release, manifest = release_identity_for_payload(
        payload, release_id=release_id, version=version
    )
    target_release = declared_target_release or computed_release
    hostile_twin = target_release.digest() != computed_release.digest()

    request = _request_dict(
        attempt_id=attempt_id,
        operation=operation,
        target_release=target_release,
        current_lineage=current_lineage,
        rollback_release=None,
        injected_failure_stage=injected_failure_stage,
        expected_generation=expected_generation,
        expected_state_sha256=expected_state_sha256,
    )

    # Plan is pure validation - no mutation has happened yet (Phase 4/5 shadow step).
    # A hostile-twin identity, a stale expected_generation/state, or an otherwise
    # malformed request is rejected right here, before _write_payload is ever called.
    plan = build_transaction_plan(request)  # raises PortableReleaseTransactionError, fail-closed

    if hostile_twin:
        # Plan built (identities were self-consistent structurally) but the caller's
        # declared identity does not match the real payload bytes it is about to write.
        # Refuse before mutation -- this is the P8 gate.
        raise SelfUpdateTransactionError(
            "hostile-twin rejected before mutation: declared target_release digest "
            f"{target_release.digest()} != payload-derived digest {computed_release.digest()}"
        )

    detection_start: float | None = None
    rollback_start: float | None = None
    rollback_ms: float | None = None
    failure_ms: float | None = None
    mutated = False

    try:
        if injected_failure_stage == "pre_mutation":
            detection_start = time.monotonic()
            observed_gen = plan.source_generation
            observed_state = plan.source_state_sha256
            receipt = record_attempt(
                plan,
                outcome="FAILED_NO_MUTATION",
                observed_generation=observed_gen,
                observed_state_sha256=observed_state,
                failure_code="INJECTED_PRE_MUTATION",
            )
            failure_ms = (time.monotonic() - detection_start) * 1000.0
            return SelfUpdateResult(plan, receipt, (time.monotonic() - t0) * 1000.0, failure_ms, None)

        # --- mutate ---------------------------------------------------------
        _write_payload(store.managed_dir, payload)
        mutated = True

        if injected_failure_stage == "post_mutation":
            detection_start = time.monotonic()
            # Fail-closed recovery: restore exact pre-attempt bytes.
            rollback_start = time.monotonic()
            if plan.source_generation is None:
                # Failed INSTALL: no predecessor snapshot exists; "restore" = empty dir.
                if store.managed_dir.exists():
                    shutil.rmtree(store.managed_dir)
            else:
                store._restore_snapshot(plan.source_generation)
            rollback_ms = (time.monotonic() - rollback_start) * 1000.0
            observed_after_restore = (
                None if plan.source_generation is None else compute_state_digest(store.managed_dir)
            )
            receipt = record_attempt(
                plan,
                outcome="ROLLED_BACK",
                observed_generation=plan.source_generation,
                observed_state_sha256=observed_after_restore,
                failure_code="INJECTED_POST_MUTATION",
            )
            failure_ms = (time.monotonic() - detection_start) * 1000.0
            return SelfUpdateResult(
                plan, receipt, (time.monotonic() - t0) * 1000.0, failure_ms, rollback_ms
            )

        # --- verify -----------------------------------------------------------
        observed_state = compute_state_digest(store.managed_dir)
        if observed_state != _manifest_digest(manifest):
            # Verification mismatch that was NOT explicitly injected -- still must not be
            # normalized into success. Attempt fail-closed recovery exactly like the
            # injected post-mutation path.
            detection_start = time.monotonic()
            rollback_start = time.monotonic()
            if plan.source_generation is None:
                if store.managed_dir.exists():
                    shutil.rmtree(store.managed_dir)
                restored_state = None
            else:
                store._restore_snapshot(plan.source_generation)
                restored_state = compute_state_digest(store.managed_dir)
            rollback_ms = (time.monotonic() - rollback_start) * 1000.0
            receipt = record_attempt(
                plan,
                outcome="ROLLED_BACK",
                observed_generation=plan.source_generation,
                observed_state_sha256=restored_state,
                failure_code="OBSERVED_DIGEST_MISMATCH",
            )
            failure_ms = (time.monotonic() - detection_start) * 1000.0
            return SelfUpdateResult(
                plan, receipt, (time.monotonic() - t0) * 1000.0, failure_ms, rollback_ms
            )

        receipt = record_attempt(
            plan,
            outcome="SUCCEEDED",
            observed_generation=plan.next_generation,
            observed_state_sha256=observed_state,
        )
        new_lineage = StateLineage(
            schema=LINEAGE_SCHEMA,
            generation=plan.next_generation,
            state_sha256=observed_state,
            active_release_digest=target_release.digest(),
            predecessor_generation=current_lineage.generation if current_lineage else None,
            predecessor_state_sha256=current_lineage.state_sha256 if current_lineage else None,
            predecessor_release_digest=(
                current_lineage.active_release_digest if current_lineage else None
            ),
        )
        store._save_lineage(new_lineage)
        store._append_history(plan.next_generation, target_release, observed_state)
        store._snapshot_current(plan.next_generation)
        return SelfUpdateResult(plan, receipt, (time.monotonic() - t0) * 1000.0, None, None)
    except PortableReleaseTransactionError:
        # A real mutation already happened (mutated=True) but the attempt could not be
        # committed for a reason not already handled by one of the explicit recovery
        # branches above (pre_mutation / post_mutation / verify-mismatch all restore
        # and return before this point). Restore exact pre-attempt bytes before letting
        # the triggering exception propagate -- disk must never be left disagreeing
        # with the still-unchanged lineage record. This is the general fail-closed net;
        # _normalize_injected_failure_stage above already closes the specific known
        # vector (an unrecognized injected_failure_stage reaching the SUCCEEDED path).
        if mutated:
            _recover_from_unexpected_post_mutation_failure(
                store,
                restore_generation=plan.source_generation,
                expected_state_sha256=plan.source_state_sha256,
            )
        raise


# --------------------------------------------------------------------------- ROLLBACK (explicit)


def apply_rollback(
    store: SelfUpdateStore, *, attempt_id: str, injected_failure_stage: str | None = None
) -> SelfUpdateResult:
    """Explicit deliberate ROLLBACK: mint a new forward generation whose content matches
    the exact predecessor generation. Uses the accepted primitive's ROLLBACK operation
    semantics (SUCCEEDED outcome bound to plan.rollback_target_state_sha256)."""

    t0 = time.monotonic()
    # Same whitelist as apply_transaction, same reason: refuse an unrecognized stage
    # before anything is built or mutated rather than let it fall through.
    injected_failure_stage = _normalize_injected_failure_stage(injected_failure_stage)
    current_lineage = store.load_lineage()
    if current_lineage is None:
        raise SelfUpdateTransactionError("ROLLBACK requires an existing lineage")
    if current_lineage.predecessor_generation is None:
        raise SelfUpdateTransactionError("no predecessor recorded; cannot roll back")

    rollback_release = store._release_for_generation(current_lineage.predecessor_generation)
    if rollback_release.digest() != current_lineage.predecessor_release_digest:
        raise SelfUpdateTransactionError(
            "recorded history release does not match predecessor_release_digest in lineage"
        )

    request = _request_dict(
        attempt_id=attempt_id,
        operation="ROLLBACK",
        target_release=rollback_release,
        current_lineage=current_lineage,
        rollback_release=rollback_release,
        injected_failure_stage=injected_failure_stage,
    )
    plan = build_transaction_plan(request)

    if injected_failure_stage == "pre_mutation":
        receipt = record_attempt(
            plan,
            outcome="FAILED_NO_MUTATION",
            observed_generation=plan.source_generation,
            observed_state_sha256=plan.source_state_sha256,
            failure_code="INJECTED_PRE_MUTATION",
        )
        return SelfUpdateResult(plan, receipt, (time.monotonic() - t0) * 1000.0, None, None)

    mutated = False
    try:
        store._restore_snapshot(current_lineage.predecessor_generation)
        mutated = True
        observed_state = compute_state_digest(store.managed_dir)
        if observed_state != plan.rollback_target_state_sha256:
            raise SelfUpdateTransactionError(
                "restored predecessor snapshot does not match plan.rollback_target_state_sha256 "
                f"(observed={observed_state}, expected={plan.rollback_target_state_sha256})"
            )

        receipt = record_attempt(
            plan,
            outcome="SUCCEEDED",
            observed_generation=plan.next_generation,
            observed_state_sha256=observed_state,
        )
        new_lineage = StateLineage(
            schema=LINEAGE_SCHEMA,
            generation=plan.next_generation,
            state_sha256=observed_state,
            active_release_digest=rollback_release.digest(),
            predecessor_generation=current_lineage.generation,
            predecessor_state_sha256=current_lineage.state_sha256,
            predecessor_release_digest=current_lineage.active_release_digest,
        )
        store._save_lineage(new_lineage)
        store._append_history(plan.next_generation, rollback_release, observed_state)
        store._snapshot_current(plan.next_generation)
        return SelfUpdateResult(plan, receipt, (time.monotonic() - t0) * 1000.0, None, None)
    except (PortableReleaseTransactionError, SelfUpdateTransactionError):
        # Same fail-closed net as apply_transaction: the managed_dir was already
        # mutated to the ROLLBACK target's bytes (mutated=True) but the attempt could
        # not be committed. Restore it to the generation that was actually active
        # before this rollback attempt started (current_lineage, not the rollback
        # target) before letting the triggering exception propagate.
        if mutated:
            _recover_from_unexpected_post_mutation_failure(
                store,
                restore_generation=current_lineage.generation,
                expected_state_sha256=current_lineage.state_sha256,
            )
        raise


# --------------------------------------------------------------------------- readback


def independent_readback(managed_dir: Path, control_dir: Path) -> dict[str, Any]:
    """Re-read state from disk only. Callers should invoke this from a FRESH python
    process (e.g. `python3 -c "..."`) for a real process-restart readback (P7); calling
    it in-process only proves the function is correct, not that state survived a process
    boundary."""

    store = SelfUpdateStore(managed_dir=Path(managed_dir), control_dir=Path(control_dir))
    lineage = store.load_lineage()
    observed_state = compute_state_digest(store.managed_dir)
    return {
        "lineage": None if lineage is None else lineage.as_dict(),
        "observed_state_sha256": observed_state,
        "lineage_matches_observed": (lineage is not None and lineage.state_sha256 == observed_state),
    }
