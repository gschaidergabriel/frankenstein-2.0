# Trigger 7 negative result — semantic claim created before compiler admission

Date: 2026-08-31
Status: PRESERVED_COORDINATION_NEGATIVE / REPAIRED_FORWARD
Scope: Trigger-7 semantic duplicate-work mutex only

## Observed failure

Two current source-research claims were created directly under `research/local_voice/semantic_claims/` using new canonical semantic values that were not admitted by `research/local_voice/tools/t7_semantic_claim.py` at claim-creation time:

- `6fcd22aed92beee2278dba80309ed1558898aafd170eaa8d353106845cb68849.json`
  - claim commit: `2de3e32c9d071e5f23dbec8e77542e2ae180bdee`
  - objective: 2026 full-duplex German source triage
- `efa6ce947e57106992c07f380a4a49df3fe990395d656e38cc04123fe83dc33a.json`
  - claim commit: `134be4a0dababc859e94ca029f2989131f25db2a`
  - objective: Full-Duplex-Bench v3 German tool/rollback donor audit

At those points the semantic claim protocol required unknown semantic categories to fail closed and required a versioned compiler admission plus test before a new category could be used.

Therefore:

`CORRECT_SHA256_SHAPE != VALID_PRE_ADMISSION_CLAIM_ORDER`

`CREATE_ONLY_PATH != COMPILER_ADMITTED_SEMANTIC_IDENTITY`

The source research performed after these claims is not erased by this coordination defect. Both research paths remained source/research scoped and minted no model-runtime, acoustic, Trigger-4 acceptance, or whole-product credit. The defect is specifically claim-admission ordering and future duplicate-work safety.

## Forward repair

The compiler was extended in commit `95960f105dfc619c6c1a60f09b6bd9d10ddfaabf` to admit the exact already-materialized canonical semantic identities without changing their hashes.

The semantic mutex test suite was strengthened in commit `bf9022dcdacaa3fa57acc852c445a559d40c236d` so every current `research/local_voice/semantic_claims/*.json` must:

1. round-trip through the fail-closed compiler;
2. reproduce the exact canonical semantic object;
3. reproduce the stored semantic key; and
4. use that exact key as its filename.

This is a forward enforcement repair. It does **not** retroactively claim that the original ordering was valid.

## Required future law

For any new semantic category:

1. add the smallest explicit compiler admission;
2. add/extend a deterministic regression test;
3. let the semantic-claim CI pass;
4. only then create the canonical create-only semantic claim;
5. only the create-only winner may create human claim / workflow / runtime dispatch.

If a worker cannot compile the proposed objective before the create-only write, it must stop or route a compiler-admission change first. It must not hand-calculate a new key and bypass the registry.

## Credit boundary

- coordination defect discovered: 1
- forward compiler admission repair: source change only
- forward all-claim roundtrip enforcement: repository-CI candidate until CI executes
- research/source facts from the two audited lanes: preserved at their prior exact scope
- runtime credit from this repair: 0
- acoustic credit: 0
- Trigger-4 acceptance credit: 0
- whole-product credit: 0
