# F2-WP-901 G4 — Persisted Checkpoint Row Load Attestation

Status: generation-4 candidate component contract; repository source/tests/CI only until terminal reconciliation.

## Why G4 exists

WP901 G3 removed the canonical restart ingress path that trusted mutually self-consistent caller checkpoint/seal strings. It now requires concrete typed checkpoint, whole-loop, outcome and causal-identity objects. G3 intentionally records `persisted_row_attestation = NOT_OBSERVED`, because a concrete `PersistentAgencyCheckpoint` can still be constructed in memory rather than recovered from the canonical WP206 checkpoint row.

G4 closes only that repository-component gap.

## Canonical component path

```text
existing canonical UnifiedDB
        |
        v
CanonicalPersistentAgencyStore.load_checkpoint(checkpoint_id)
        |
        | existing WP206 checks:
        | - current DB device/inode
        | - stored canonical path/device/inode
        | - stored store-authority receipt digest
        | - row checkpoint digest
        | - typed checkpoint replay digest
        v
PersistentAgencyCheckpoint + PersistedCheckpointRowLoadAttestation
        |
        v
accepted WP901 G3 source authentication
        |
        v
accepted WP901 G2 deterministic continuation planner
        |
        v
RestartContinuationPlan candidate
```

## What is newly evidenced

At repository-component scope, the canonical G4 ingress no longer accepts a caller-supplied checkpoint object. It calls the existing WP206 canonical store loader, fences the loaded checkpoint digest and the live store authority-receipt digest, emits a typed non-authoritative load attestation, and passes exactly the loaded checkpoint into G3.

The G4 attestation records the checkpoint id/generation/digest, canonical store path, device, inode, store-bound authority-receipt digest, and UnifiedDB fingerprint schema. It explicitly reports `same_inode_global_db_drift_closure = NOT_CLAIMED`.

## Deliberate boundaries

G4 does **not** modify WP206 storage semantics or create another database. It does not claim that an accepted `UnifiedDBAuthorityRef` itself proves a row load. It does not claim full-database same-inode mutation closure; that remains a separate WP206 discriminator. Repository CI is not target-host/VPS runtime evidence.

Zero target-host/VPS/physical-GRID10/semantic-GWT/J-Space/provider/model/effect/completion/training/whole-system credit is granted by this component contract.

## Regression set

The G4 suite requires:

- happy-path canonical store row load feeding G3 while preserving accepted G2 continuation semantics;
- expected checkpoint digest mismatch rejection;
- expected store-authority receipt mismatch rejection;
- persisted checkpoint JSON tamper rejection by the existing WP206 loader;
- forged recovery evidence unable to substitute a caller-constructed checkpoint for the loaded row;
- unrelated same-inode DB mutation does not get misreported as globally closed.

The G4 CI also reruns the accepted G2 planner suites and G3 source-authentication suite.

## Next gate after repository acceptance

Even a green merged-main G4 remains component evidence. Promotion-bearing restart/recovery credit still requires an exact-source owner-target-host run that opens the actual canonical UnifiedDB, reads back the persisted checkpoint through this path, executes the bounded restart/recovery continuation path, and records exact source/artifact/host/evidence identities without converting model/provider output into state or effect authority.
