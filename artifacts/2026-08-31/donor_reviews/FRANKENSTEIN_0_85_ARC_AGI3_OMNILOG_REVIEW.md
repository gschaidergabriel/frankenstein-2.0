# Frankenstein 0.85 ARC-AGI-3 / Omni-Log donor review

Date: 2026-08-31
Source repository: `gschaidergabriel/frankenstein-0.85-updated-version-with-several-fixes-ARD-AGI-3-PRIVAT-benchmark-and-omi-log-analytic`
Status: DONOR / RESEARCH EVIDENCE, NOT F2 CANONICAL RUNTIME TRUTH

## Strong findings worth carrying into Frankenstein 2.0

1. **Retrieval path identity is a first-class invariant.** The donor run found that retrieval was reading the wrong UnifiedDB (about 7 MB / skill documentation) instead of the knowledge-bearing DB (about 63 MB). This is directly relevant to F2: a correct retrieval algorithm against the wrong state authority is still wrong. F2 should retain exact DB/state identity in retrieval receipts and tests.

2. **Honest null retrieval is valuable.** The donor changed retrieval from silently returning unrelated rows to explicit `kein Treffer` behavior. That aligns well with F2 fail-closed Unknown/ABSTAIN semantics.

3. **FTS projection completeness must be tested.** Direct inserts into the canonical article table could remain invisible to the FTS projection. A projection completeness discriminator (`canonical row exists -> search projection exists`) is a useful reusable falsifier for F2-derived indexes.

4. **Knowledge can help or hurt depending on epistemic discipline.** The benchmark reports that strategy knowledge improved trap handling but could worsen maze behavior when heuristics hardened faster than observations justified them. F2 should treat retrieved strategy/method memory as weighted candidate evidence, not command authority.

5. **Interactive environments require active observation and world-model correction.** The private games included invisible walls, one-way cells, hidden death cells and moving hunters. The important architectural lesson is not the score; it is that observation must be an action, predictions must be falsifiable, and contradictory environment evidence must update the world model.

6. **Blind-run logging is good evidence practice.** The donor keeps frame/input logs and a SHA manifest and states that the player did not read game source. This is a useful benchmark-harness pattern for future F2 held-out cognitive falsifiers.

## Benchmark interpretation guard

The donor reports a private four-game ARC-AGI-3-like score of about 33.3% for one Opus-style run and compares it with a reported Opus 5 High figure of 30.2% on an official 25-environment harness. This is **not an apples-to-apples leaderboard result**: different environments, only four private games, and the F2/Frankenstein stack had task-specific accumulated knowledge. Treat it as an internal hypothesis-generating measurement, not external SOTA evidence.

The cleanest internal signal is the within-suite behavior change: the report records a progression on the d-series from 2 -> 29 -> 70 actions and level 1 -> 2 -> 3 across configurations. Even that requires preservation of exact seeds, budgets, source identities and logs before causal architectural credit.

## What should NOT be imported as F2 authority

- The donor's monolithic `FranKenstein (GLM 5.3 flash)` coordinator identity is not a replacement for F2/EntityOS authority separation.
- Provider/model output must not become canonical truth.
- The donor's local UnifiedDB paths and `stern.py` layout are historical implementation details, not automatically current F2 state topology.
- Private benchmark percentage must not be promoted as official ARC-AGI-3 performance.
- Self-analysis / feelings prose is archival material, not evidence of consciousness or system capability.

## Recommended F2 extraction targets

- Retrieval-state identity receipt / wrong-DB falsifier.
- Canonical-to-projection completeness check for FTS/derived indexes.
- Explicit NULL/ABSTAIN retrieval contract.
- Strategy-memory hardening / stale-heuristic adversarial tests.
- Hidden-transition / deceptive-observation benchmark fixtures for world-model + ObserveIntent.
- Blind evaluator protocol with source-isolation and per-run SHA manifests.

No canonical F2 runtime, GWT/J-Space, effect, training or whole-product credit is created by this donor review.
