# Frankenstein 2.0 Run Packages

`F2-WP-004` has one current run-package ABI. All current-facing documentation, schemas, tests and the executable verifier must describe the same closure-style package.

Canonical surfaces:

- `telemetry/RUN_PACKAGE_CONTRACT.md`
- `schemas/run_package_manifest.schema.json` → `FRANKENSTEIN2_RUN_PACKAGE_MANIFEST/v1`
- `schemas/run_artifact_index.schema.json` → `FRANKENSTEIN2_RUN_ARTIFACT_INDEX/v1`
- `schemas/run_closed_receipt.schema.json` → `FRANKENSTEIN2_RUN_CLOSED_RECEIPT/v1`
- `runpackages/verify_run_package.py` — fail-closed executable authority
- `tests/test_verify_run_package.py`
- `tests/test_wp004_authority_singleton.py`
- `.github/workflows/runpackage-verifier-ci.yml`

Canonical closed package shape:

```text
runs/<series>/<run_id>/
  manifest.json
  ARTIFACTS.json
  SHA256SUMS
  CLOSED.json
  <typed payload directories/files>
```

`ARTIFACTS.json` indexes payload files plus `manifest.json`, but never indexes itself, `SHA256SUMS`, or `CLOSED.json`. `SHA256SUMS` covers payload files, `manifest.json`, and `ARTIFACTS.json`, but never itself or `CLOSED.json`. `CLOSED.json` is written last and binds all three closure digests.

The JSON schemas are descriptive typed surfaces of this same ABI; they are not independent acceptance authorities. A package that fails `runpackages/verify_run_package.py` is not accepted merely because an individual JSON document validates structurally.

The earlier single-manifest design using `MANIFEST.json`, embedded `files`, `package_digest`, or `FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1` is historical/superseded donor provenance only. `runpackages/RUN_PACKAGE_SCHEMA_V1.json` is not a current authority and does not exist on current `main`.

A successful verifier run grants evidence only at the classification/scope encoded in the closed package. It never upgrades component evidence to whole-system acceptance, and package/source digest identity alone does not prove which bytes a target process consumed.
