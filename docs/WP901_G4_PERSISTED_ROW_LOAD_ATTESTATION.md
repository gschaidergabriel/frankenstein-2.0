# F2-WP-901 G4 — Persisted-row load attestation

Status: implementation candidate for repository-component acceptance only.

## Boundary closed

Accepted WP901 G3 authenticates concrete typed restart sources, but deliberately leaves persisted-row/load attestation unobserved. G4 adds one canonical ingress that starts from `CanonicalPersistentAgencyStore` plus a checkpoint id rather than a caller-supplied checkpoint object.

The G4 ingress:

1. requires a clean SQLite transaction boundary;
2. begins one read transaction;
3. calls accepted `CanonicalPersistentAgencyStore.load_checkpoint()`;
4. re-reads the exact checkpoint row inside the same SQLite transaction snapshot;
5. binds generation, checkpoint digest, raw persisted checkpoint JSON, canonical DB path, device, inode and WP206 bound-file authority receipt into a deterministic row-evidence digest;
6. emits a non-authoritative `PersistedCheckpointLoadAttestation`;
7. passes the checkpoint returned by the loader directly into accepted WP901 G3 source authentication;
8. preserves all accepted G2 continuation semantics.

## Why the same transaction matters

A second query outside the loader's database snapshot could accidentally attest a later committed row rather than the snapshot from which the checkpoint was loaded. G4 therefore keeps the accepted loader call and row-evidence query inside one SQLite read transaction.

This is still a repository-component mechanism. It is not cryptographic remote attestation and it does not prove target-host execution.

## Explicit non-claims

G4 does **not** claim:

- non-rollbackable freshness;
- closure of the separately researched stale rollback/freeze question;
- closure of WP206 same-inode live data/schema drift;
- target-host/VPS execution or readback;
- physical GRID10, GWT/J-Space, provider/model or training execution;
- truth, scheduler, effect or completion authority;
- Frankenstein 2.0 whole-system acceptance.

Those remain separate gates. In particular, repository CI success must not be promoted to target-runtime evidence.

## Falsifiers

The G4 regression suite requires failure on:

- persisted checkpoint JSON changed without matching digest;
- stored UnifiedDB authority receipt mismatch;
- checkpoint-id substitution;
- caller-owned open transaction that would weaken the snapshot boundary;
- restart evidence whose checkpoint digest disagrees with the actually loaded checkpoint.

Positive coverage also reruns accepted WP206, WP901 G2 and WP901 G3 suites.
