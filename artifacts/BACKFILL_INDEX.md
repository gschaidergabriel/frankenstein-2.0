# Frankenstein 2.0 Artifact Backfill Index

Owner directive: all artifacts created for Frankenstein 2.0 must also be discoverable from `artifacts/`.

This index backfills pre-existing artifact classes without reclassifying their canonical authority. The original canonical/evidence path remains authoritative; this folder is the central artifact catalogue.

## Existing artifact families covered

- `architecture/` — architecture documents and contracts
- `docs/` — generated documentation and reports
- `research/` — research packets, local-voice research, falsifier material
- `receipts/` — top-level receipts
- `checkpoints/` — generated checkpoints / reentry artifacts
- `provenance/` — provenance material
- `coordination/` — coordination artifacts
- `workpackages/receipts/` — workpackage evidence receipts
- `workpackages/reconciliations/` — terminal/reconciliation artifacts
- `workpackages/deltas/` — worker deltas / handoffs
- `workpackages/state_events/` — append-only workpackage transition evidence
- `AI_START_HERE_DO_NOT_SCAN_REPO/` — release/handoff artifacts

## Rule

New user-facing documents, generated reports, donor reviews, diagrams, datasets, benchmark outputs, release packages, evidence bundles and comparable outputs must have an `artifacts/...` entry at creation time.

Canonical truth is not duplicated by interpretation: where the original path is itself authority/evidence, `artifacts/` records a catalogue/reference or byte-identical mirror, never a separately editable competing truth.

Secrets, credentials, raw private DBs and unsafe host material are excluded.

## Current donor review

- `artifacts/2026-08-31/donor_reviews/FRANKENSTEIN_0_85_ARC_AGI3_OMNILOG_REVIEW.md`

## Historical external/project artifacts identified for later byte-level import when raw bytes are available

- `GABRIEL_GSCHAIDER_GRF_FRANKENSTEIN2_COMPLETE_MONOGRAPH_2026-08-31_v2_RETINA.docx`
- current Architect/Clay fast-bootstrap text sources
- prior PDF research/root-cause reports referenced by the project file archive

These entries are not claimed byte-imported unless an actual repository object exists under `artifacts/`.
