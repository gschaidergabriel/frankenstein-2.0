# Frankenstein 2.0 Run Packages

`F2-WP-004` has one current run-package authority.

Canonical contract:

- `telemetry/RUN_PACKAGE_CONTRACT.md`
- `schemas/run_package_manifest.schema.json`
- `schemas/run_artifact_index.schema.json`
- `schemas/run_closed_receipt.schema.json`
- `runpackages/verify_run_package.py`
- `tests/test_verify_run_package.py`

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

Any earlier single-manifest package contract using `MANIFEST.json`, embedded `files`, `package_digest`, or `FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1` is historical/superseded and must not be used for new F2 evidence.

A successful verifier run grants evidence only at the classification/scope encoded in the closed package. It never upgrades component evidence to whole-system acceptance.
