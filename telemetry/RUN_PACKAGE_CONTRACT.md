# Frankenstein 2.0 — Immutable Run Package Contract

Workpackage: `F2-WP-004`

This document describes the single current run-package ABI. It does **not** grant runtime, instrumentation-coverage, GRID10, whole-system, or scientific acceptance credit by itself.

## Canonical authority

There is exactly one active run-package ABI, and its current-facing surfaces must agree:

- descriptive contract: `telemetry/RUN_PACKAGE_CONTRACT.md`
- package index/readme: `runpackages/README.md`
- manifest schema: `schemas/run_package_manifest.schema.json`
  - schema id: `FRANKENSTEIN2_RUN_PACKAGE_MANIFEST/v1`
- artifact-index schema: `schemas/run_artifact_index.schema.json`
  - schema id: `FRANKENSTEIN2_RUN_ARTIFACT_INDEX/v1`
- closed-receipt schema: `schemas/run_closed_receipt.schema.json`
  - schema id: `FRANKENSTEIN2_RUN_CLOSED_RECEIPT/v1`
- fail-closed executable authority: `runpackages/verify_run_package.py`
- deterministic verifier regression: `tests/test_verify_run_package.py`
- authority-singleton regression: `tests/test_wp004_authority_singleton.py`
- repository CI: `.github/workflows/runpackage-verifier-ci.yml`

The executable verifier is the fail-closed acceptance implementation for this ABI. The JSON schemas describe its three typed JSON records; they are not independent authorities that can override a verifier failure.

`runpackages/RUN_PACKAGE_SCHEMA_V1.json` is **not** part of the current ABI. It does not exist on current `main`. Any historical single-`MANIFEST.json` / embedded-`files` / `package_digest` / `FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1` design is superseded donor provenance only and cannot mint current acceptance.

## Canonical package shape

A closed package is an immutable directory below `runs/` with the closure-style layout:

```text
runs/<series>/<run_id>/
  manifest.json
  ARTIFACTS.json
  SHA256SUMS
  CLOSED.json
  <typed payload directories/files>
```

The closure files have distinct roles:

- `manifest.json` carries run/workpackage/generation/claim/worker/source identity, evidence scope, participants and typed command/result metadata.
- `ARTIFACTS.json` indexes payload files plus `manifest.json`; it never indexes itself, `SHA256SUMS`, or `CLOSED.json`.
- `SHA256SUMS` covers payload files, `manifest.json`, and `ARTIFACTS.json`; it never covers itself or `CLOSED.json`.
- `CLOSED.json` is written last and binds the manifest, artifact-index, and SHA256SUMS digests together with closure status, evidence classification, runtime-execution observation, runtime-credit ceiling, acceptance scope, and completion deficit.

The canonical verifier rejects missing closure files, malformed schema identities, unsafe/traversing paths, payload or package symlink bypasses, unindexed payloads, digest mismatches, invalid source/workpackage/generation identity, invalid evidence classifications, inconsistent closure metadata, and other declared ABI violations.

## Identity and evidence ceiling

A package can support promotion only at the exact scope its verified contents and separately observed execution establish. Structural closure proves package integrity and evidence binding; it does not create facts that are absent from the payload/receipts.

In particular:

- `COMPONENT_PASS != WHOLE_SYSTEM_PASS`
- `SOURCE_PRESENCE != RUNTIME_PASS`
- `MODEL_OUTPUT != COMPLETION`
- `PACKAGE_VERIFIED != CLAIM_PROVED_BEYOND_DECLARED_SCOPE`
- `PRELOAD_OR_MANIFEST_HASH != SAME_BYTES_PROCESS_CONSUMPTION_PROOF`

Higher claims such as exact-source target/VPS execution must add their own admitted evidence while remaining inside this one package authority rather than inventing a second run-package ABI.

## Historical preservation

Historical package forms, schemas, receipts, and archived runs remain evidence/provenance. Do not rewrite old evidence merely because the current ABI changed. Historical material may be consumed only at the scope its own verifier/receipt establishes and must never compete with this current executable authority.
