# Frankenstein 0.85 fixed-bug regression audit against Frankenstein 2.0

Date: 2026-08-31
Audited F2 baseline observed at audit start: `1139f4198349ed12a5130d79596a2587eaa9f026`
Historical donor repository: `gschaidergabriel/frankenstein`
Current repository: `gschaidergabriel/frankenstein-2.0`

## Scope

The seven items below are historical bugs that were already repaired in Frankenstein 0.85. They are used here only as regression/falsifier specifications against Frankenstein 2.0. This audit does **not** reopen the old fixes and does not claim whole-product or target-runtime acceptance.

Status vocabulary:

- `GREEN`: current F2 source/tests contain an equivalent protection for the failure class at the audited scope.
- `N/A_EXACT + GREEN_STRUCTURAL`: the historical mechanism is not part of current F2; the analogous failure class is structurally prevented and tested at the relevant current boundary.
- `N/A_EXACT + AMBER`: the exact historical mechanism is absent, but a dedicated generic falsifier for the broader failure class is missing.
- `RED`: a current F2 regression was reproduced. None was found in this audit.

## Matrix

| # | Historical fixed bug | F2 status | Current evidence / interpretation | Residual action |
|---|---|---|---|---|
| 1 | Wrong UnifiedDB selected / wrong corpus authority | **GREEN (source/test/CI definition scope)** | `src/state/unifieddb_identity.py`, `tests/test_unifieddb_identity.py`, `.github/workflows/unifieddb-identity-ci.yml`. Explicit DB authorities must agree; conflicts and stale pointers fail closed; relative environment DB paths are forbidden; an existing XDG target precedes legacy compatibility state; fresh installs target XDG instead of a plugin tree. This directly protects the identity/authority class that allowed the old wrong-DB read. | Keep a separate real-runtime content/population receipt if later claiming that the live machine reads the intended populated corpus. This audit does not mint that runtime credit. |
| 2 | Missing `wegehierarchie.py` caused `ModuleNotFoundError` on every hook | **N/A_EXACT + AMBER** | The current F2 tree contains neither the old `wegehierarchie.py` path nor old `stern.py` hook architecture. Release-candidate CI exercises release-specific tests and deterministic build, but this audit found no repo-wide `compileall`/import-every-shipped-module smoke. | Add a package/import-closure falsifier for every Python module shipped in the release artifact, without recreating the historical module. |
| 3 | Dummy ranking / first token monopolized slots / unordered FTS `LIMIT` | **N/A_EXACT + GREEN_STRUCTURAL at ContextCompiler boundary** | Current `ContextCompiler` consumes typed caller-admitted candidates rather than running the old FTS ranking. `tests/test_context_compiler.py` proves deterministic, input-order-independent selection; required channels are reserved before optional priority; caller classifications are preserved. The old FTS-specific `bm25`/`artikel_suchtext` mechanism is not the current context-selection authority. | If a separate semantic retrieval engine is later admitted upstream, give that engine its own ranking falsifier; do not infer ranking quality from ContextCompiler. |
| 4 | Source hunger: SQL `LIMIT` applied before shown-filter caused false nulls | **N/A_EXACT + GREEN_STRUCTURAL at ContextCompiler boundary** | Current tests prove that an oversized optional candidate does not starve a lower-priority candidate that fits, and a required channel with no candidate fails closed. There is no current ContextCompiler analogue of `LIMIT-before-NOT-EXISTS`. | Any future retrieval backend that does pagination/filtering before admission needs its own hunger/rotation test. |
| 5 | Direct insert invisible because FTS projection was not updated | **N/A_EXACT + AMBER (generic projection invariant)** | The historical `artikel` -> `artikel_suchtext` FTS projection is not a current F2 mechanism identified by this audit. Current F2 therefore does not reproduce the exact bug. However, this audit did not find one universal test asserting `canonical write -> every admitted derived search/index projection visible` across future/current projection types. | Add a generic projection-integrity falsifier only where a derived search/index projection actually exists; do not invent a second canonical store. |
| 6 | Possibility-space 3-tuple crashed 2-tuple unpacking in old `stern.py` | **N/A_EXACT + AMBER** | Current F2 tree contains neither old `stern.py` nor a `wegehierarchie.py`/historical tuple path under those identities. No exact recurrence was found, but this audit did not identify a dedicated schema/arity fuzz test covering all candidate/alternative packet boundaries. | Add typed-shape/property tests at the current candidate/alternative boundary when that boundary is selected; reject malformed arity/schema fail-closed rather than positional unpacking. |
| 7 | Silent foreign injection: no retrieval hits still injected unrelated rows | **N/A_EXACT + GREEN_STRUCTURAL at ContextCompiler boundary** | `tests/test_context_compiler.py` explicitly preserves `UNKNOWN_NOT_FILLED_BY_INFERENCE_OR_RETRIEVAL`; required channels without candidates fail closed; caller classification is preserved rather than relabelled. This blocks ContextCompiler from fabricating unrelated fallback context when evidence is absent. | Ensure every future upstream retriever preserves an explicit empty/unknown result instead of manufacturing candidates. |

## Important boundaries

1. **No RED regression was reproduced in current F2 at the audited source/test/CI-definition scope.**
2. Bug 1 has the strongest direct successor protection because F2 has an explicit UnifiedDB identity authority plus regression tests.
3. Bugs 3, 4 and 7 are not the same old FTS code; their analogous ContextCompiler failure modes are structurally covered by deterministic typed selection and fail-closed tests.
4. Bugs 2 and 6 remain useful generic falsifiers even though the historical implementation paths are absent.
5. Bug 5 must not be declared globally impossible merely because the old FTS table is absent. The correct reusable invariant is: **canonical write must be visible through every admitted derived projection that claims to expose it**.
6. Source/test evidence here does not imply target runtime, physical host, GWT/J-Space, effect, training, completion or whole-system credit.

## Recommended worker routing

Priority is falsification, not architecture expansion:

1. `IMPORT_CLOSURE_FALSIFIER`: build the exact release candidate, enumerate shipped Python modules, import/compile them in a clean disposable VPS sandbox, and fail on missing internal dependencies.
2. `CANDIDATE_SCHEMA_SHAPE_FALSIFIER`: select the current typed candidate/alternative packet boundary and fuzz legal/illegal structural shapes, including extra/missing fields and legacy tuple-like malformed inputs if such compatibility input exists.
3. `DERIVED_PROJECTION_INVARIANT`: only for an actually admitted derived search/index projection, insert through every authorized canonical-write path and prove projection visibility or explicit bounded lag/reconciliation semantics.

These are reviewer/falsifier tasks until executable counterevidence demonstrates a product defect. They must not open replacement state, retrieval, context, or effect authorities.

## Evidence paths reviewed

- `src/state/unifieddb_identity.py`
- `tests/test_unifieddb_identity.py`
- `.github/workflows/unifieddb-identity-ci.yml`
- `src/frankenstein2/context_compiler.py`
- `tests/test_context_compiler.py`
- `.github/workflows/trigger4-release-candidate-ci.yml`
- current F2 recursive tree at the observed baseline

Historical bug descriptions and fixes were supplied by the owner and are treated as the regression specification, not as evidence that current F2 contains those old defects.
