# Frankenstein 2.0 — Immutable Run Package Contract

Workpackage: `F2-WP-004`

This document describes the canonical package authority; it does **not** grant runtime, instrumentation-coverage, GRID10, whole-system, or scientific acceptance credit by itself.

## Canonical authority

There is exactly one active run-package ABI: the closure-style multi-file package already accepted by F2-WP-004 generation 2 and enforced by the current verifier.

Canonical surfaces:

- `schemas/run_package_manifest.schema.json` — `FRANKENSTEIN2_RUN_PACKAGE_MANIFEST/v1`
- `schemas/run_artifact_index.schema.json` — `FRANKENSTEIN2_RUN_ARTIFACT_INDEX/v1`
- `schemas/run_closed_receipt.schema.json` — `FRANKENSTEIN2_RUN_CLOSED_RECEIPT/v1`
- `runpackages/verify_run_package.py`
- `tests/test_verify_run_package.py`
- `.github/workflows/runpackage-verifier-ci.yml`
- `runpackages/README.md`

`runpackages/RUN_PACKAGE_SCHEMA_V1.json` and the single-manifest schema id `FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1` are retired historical design forms. The file is intentionally absent and MUST NOT be recreated as a competing current authority.

The executable verifier is the fail-closed admission implementation for the schema set above. Documentation or schema metadata that disagrees with the verifier and accepted F2-WP-004 reconciliation is stale and cannot create a second ABI.

## Canonical package shape

A package is an immutable closure directory below `runs/` with this shape:

```text
runs/<series>/<run_id>/
  manifest.json
  ARTIFACTS.json
  SHA256SUMS
  CLOSED.json
  <typed payload directories/files>
```

`manifest.json` binds the run/workpackage/generation/claim identity, source commit identity, evidence scope, participant observability, and the fixed closure filenames.

`ARTIFACTS.json` indexes payload files plus `manifest.json`, but never indexes itself, `SHA256SUMS`, or `CLOSED.json`.

`SHA256SUMS` covers payload files, `manifest.json`, and `ARTIFACTS.json`, but never itself or `CLOSED.json`.

`CLOSED.json` is written last and binds the SHA-256 digests of `manifest.json`, `ARTIFACTS.json`, and `SHA256SUMS` together with the closure status and evidence ceiling.

The canonical verifier rejects missing closure files, package/file symlinks, unsafe paths, unindexed or missing payloads, digest mutation, schema/identity mismatches, inconsistent evidence classification, and closure-digest mismatches.

## Identity and evidence ceiling

The canonical manifest binds at minimum:

- run/workpackage/generation/claim identity;
- exact source commit before execution and optional source commit after execution;
- declared evidence classification, observed-runtime flag, and runtime-credit ceiling;
- participant identity and observability;
- artifact-index and closure-receipt bindings.

The closed receipt must agree with the manifest evidence classification and runtime fields. A source-only package cannot impersonate runtime evidence, and a verified package cannot promote evidence beyond its declared and separately observed scope.

## Historical donor forms

The earlier single-manifest package shape using `MANIFEST.json`, embedded `files`, `package_digest`, or `FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1` remains historical provenance only. It is not a current package ABI and must not be revived by documentation drift.

Historical evidence may be preserved for reproducibility, but compatibility history never outranks the accepted current F2-WP-004 closure ABI.

## Authority singleton invariant

Current-facing WP004 documentation, JSON-schema metadata, verifier constants, regression tests, and CI must agree on the same closure-style ABI.

```text
MISSING_RETIRED_SCHEMA_REFERENCE != ACTIVE_AUTHORITY
DOCUMENTATION_DRIFT != NEW_ABI
VERIFIER_AND_ACCEPTED_RECONCILIATION > STALE_PROSE
ONE_WP004_RUN_PACKAGE_AUTHORITY_ONLY
```

## Promotion boundary

A package can support promotion only at the exact scope its contents and separately observed execution establish.

`COMPONENT_PASS != WHOLE_SYSTEM_PASS`

`SOURCE_PRESENCE != RUNTIME_PASS`

`MODEL_OUTPUT != COMPLETION`

`PACKAGE_VERIFIED != CLAIM_PROVED_BEYOND_DECLARED_SCOPE`
