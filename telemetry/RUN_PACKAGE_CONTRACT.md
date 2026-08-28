# Frankenstein 2.0 — Immutable Run Package Contract

Workpackage: `F2-WP-004`

This document describes the canonical package authority; it does **not** grant runtime, instrumentation-coverage, GRID10, whole-system, or scientific acceptance credit by itself.

## Canonical authority

There is exactly one active run-package manifest ABI:

- `runpackages/RUN_PACKAGE_SCHEMA_V1.json`
- schema id: `FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1`
- fail-closed implementation: `runpackages/verify_run_package.py`
- deterministic regression: `tests/test_verify_run_package.py`
- repository CI: `.github/workflows/runpackage-verifier-ci.yml`

Files below `schemas/run_package_manifest.schema.json`, `schemas/run_artifact_index.schema.json`, and `schemas/run_closed_receipt.schema.json` are retained as historical/compatibility design donors. They are **not** a second active manifest authority and must not be used to mint acceptance for a package that fails the canonical verifier.

## Canonical package shape

A package is an immutable directory below `runs/` containing:

```text
<run-package>/
  MANIFEST.json
  <one or more payload files/directories>
```

`MANIFEST.json.files` is the complete SHA-256 index of every payload file. The canonical verifier rejects missing payloads, unindexed extra payloads, path traversal, payload/package symlinks, payload digest mutation, invalid package digest, malformed source identity, impossible PASS/NOT_RUN execution claims, and invalid/non-finite spend values.

The package digest is SHA-256 over canonical JSON of the manifest with `package_digest` removed. `MANIFEST.json` never self-hashes.

## Identity and evidence ceiling

The canonical manifest binds at minimum:

- package/workpackage/generation identity;
- exact source repository/ref/commit/tree;
- declared claim scope and runtime-credit ceiling;
- command vector and typed outcome;
- start/complete/exit fields when execution is claimed;
- provider-call count, paid-spend amount and external-effect flag;
- complete payload path→digest map;
- package digest.

`PASS` requires observed start/completion timestamps and zero exit code. `NOT_RUN` is forbidden from carrying execution-result fields. These gates prevent a source-only package from impersonating an executed result.

## Historical closure donors

The earlier `ARTIFACTS.json` / `SHA256SUMS` / `CLOSED.json` design remains useful as a possible future richer finalizer and as historical provenance. It is not currently the canonical manifest ABI unless and until a successor workpackage deliberately migrates it into the verifier and its regression suite.

Do not delete historical schemas merely to make the repository look cleaner; label and preserve them as donor evidence.

## Promotion boundary

A package can support promotion only at the exact scope its contents and separately observed execution establish.

`COMPONENT_PASS != WHOLE_SYSTEM_PASS`

`SOURCE_PRESENCE != RUNTIME_PASS`

`MODEL_OUTPUT != COMPLETION`

`PACKAGE_VERIFIED != CLAIM_PROVED_BEYOND_DECLARED_SCOPE`
