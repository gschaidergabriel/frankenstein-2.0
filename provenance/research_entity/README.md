# Research-Entity provenance mirror

This directory is the canonical Frankenstein 2.0 pointer layer for Research-Entity inputs consumed by Triggerword-4 assembly.

It is deliberately **not** a copy of the Research-Entity knowledge base and **not** a second authority store. `MIRROR_MANIFEST.json` records exact repository, commit, path and blob identities so an F2 build step can be reconstructed against the source that actually informed it.

## Authority rule

A mirrored item is a historical build input. Before using it as *current* authority, re-resolve the upstream repository/ref. Newer owner/supervisor/current-source authority wins. Preserve the old manifest as provenance; add a successor capture rather than rewriting what a past build consumed.

## Trigger continuity

The initial mirror binds the current Triggerword-4 router/directives, the Triggerword-5 forensic-ingest contract/state and the shared sparse generative world-substrate extension. Triggerword 5 remains the analysis/ingest lane feeding Triggerword 4; Triggerword 4 remains the Frankenstein-2.0 build/assembly lane.

## Donor rule

`gschaidergabriel/frankenstein` is recorded at the exact donor commit consumed by this checkpoint and remains read-only for F2 assembly. Successor implementation belongs in `gschaidergabriel/frankenstein-2.0`.

## Evidence boundary

This mirror proves source identity and provenance at its declared scope only. It does not prove that mirrored mechanisms execute, that a runtime passed, that a provider call occurred, that canonical truth was minted, or that an external effect happened. Runtime/effect/completion credit remains zero unless separate exact runtime evidence establishes it.

## Verification

For each `mirrored_sources[]` entry in `MIRROR_MANIFEST.json`:

1. resolve the listed repository and commit;
2. fetch the listed path at that commit;
3. require the returned source blob SHA to equal `blob_sha`;
4. if the upstream ref has moved, treat the difference as a successor state, not as corruption of this historical capture.
