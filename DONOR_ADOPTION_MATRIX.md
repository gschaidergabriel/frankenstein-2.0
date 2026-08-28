# Frankenstein 2.0 — Donor Adoption Matrix

This matrix separates **source availability** from **Frankenstein-2.0 completion**.

## Exact Frankenstein 1.x donor freeze

The current primary donor baseline for this assembly generation is frozen as:

- repository: `gschaidergabriel/frankenstein`
- branch: `main`
- commit: `5641dc6b2df6ebed1df246ee7533134324f6c427`
- tree: `9f529a1ea8896cf9988298ea58e827c241d6949f`
- immutable provenance manifest: `provenance/frankenstein1-donor-freeze-20260828T2139P0700.json`

This is a **source-provenance freeze only**. It does not grant runtime, integration, GRID10, provider-path or whole-system credit. Any later donor synchronization requires a new deliberate receipt; this freeze remains historical evidence for the exact source used by this assembly generation.

Adoption classes:

- `DIRECT_ADOPT` — move source with minor packaging/interface changes.
- `ADAPT_TO_GRID` — substantial implementation exists but must be rebound to F2 state, GRID10 and causal ABI.
- `CONCEPT_DISTILL` — preserve mechanism/lesson, do not copy implementation wholesale.
- `REIMPLEMENT` — build an F2-native successor using donor lessons.
- `UNKNOWN` — source-level audit still required.

| Area | Primary donor/lineage | Adoption | F2 status | Key remaining work |
|---|---|---:|---:|---|
| UnifiedDB durable state | current Frankenstein + Agent-Zero/Clay lineage | ADAPT_TO_GRID | open | canonical resolver/fingerprint; causal identities; remove session/latest-entry shortcuts |
| Handoff/reconcile workpackages | current Frankenstein | ADAPT_TO_GRID | open | bind exact native Agent tool-use and child identity |
| Native Claude child execution | Claude Code runtime + Frankenstein harness | ADAPT_TO_GRID | open | WorkExecution ABI; resume/replacement/nesting; causal result return |
| GRID10 | Clay research/staging | ADAPT_TO_GRID | in progress | migrate source + tests; finish real runtime gates; bind to F2 data spine |
| Cognitive Envelope / ControlSnapshot | GRID10 research/staging | ADAPT_TO_GRID | in progress | real consumers for every material control; held-out lesions |
| Hyperposition | Clay/HCU research | ADAPT_TO_GRID | in progress | bind branches/discriminators to F2 cycle and telemetry |
| Voice / OpenAI Realtime | current Frankenstein | ADAPT_TO_GRID | open | preserve one cognition; repair call/result provenance; integrate Presence/GRID |
| Visual Cortex / Perception Control | current Frankenstein | ADAPT_TO_GRID | open | permanent Retina; active sensing; typed epistemic outputs |
| Presence/familiarity | current Frankenstein | ADAPT_TO_GRID | open | candidate-level attribution and stale-generation tests |
| Retrieval / MicroClay | current Frankenstein | ADAPT_TO_GRID | open | causal retrieval IDs; move LLM relevance out of deterministic hook path |
| Memory evolution/degradation | Project-Frankenstein historical lineage | CONCEPT_DISTILL | open | recover exact source/parameters; F2-native salience/evolution system |
| Consciousness daemon / persistent loop precursor | Project-Frankenstein historical lineage | CONCEPT_DISTILL | open | distill pulse/continuity ideas into new Persistent Pulse |
| Agent-Zero cognition | Agent-Zero lineage | CONCEPT_DISTILL | open | retain autonomy/initiative strengths; route through GRID10 alignment/control |
| QUBO world model | Project-Frankenstein/research lineage | ADAPT_TO_GRID | open | exact source extraction; define bounded projection ABI and ablations |
| NeRD physics | Project-Frankenstein/research lineage | ADAPT_TO_GRID | open | exact source extraction; bounded physical plausibility simulator; performance tests |
| Cognitive Micro-Lab | Project-Frankenstein lab idea + F2 synthesis | REIMPLEMENT | open | small universal consistency/simulation environment |
| Sparse generative world substrate | F2/Clay research synthesis | REIMPLEMENT | open | atoms/operators/uncertainty/decay + bounded WorldSlice materialization |
| Xeno assimilator/gardener roles | Clay/Xeno research | CONCEPT_DISTILL | open | integrate as functions, not identities |
| Effect/execution/completion correctness | EntityOS + Frankenstein forensics | REIMPLEMENT | open | per-invocation request→admission→execution→verification→re-entry lineage |
| RLM/RAH/context virtualization | external/research harness work | ADAPT_TO_GRID | open | adaptive R0/R1/R2/R3 selection; budget/depth/fanout control |
| Recursive Cognitive Process Distillation | distilled research-worker process | REIMPLEMENT | open | MethodEpisode→Hypothesis→Shadow→Rule pipeline |
| ARC-AGI-3-style agentic tests | benchmark methodology | REIMPLEMENT | open | held-out custom interactive worlds; no public-game-specific credit |
| Full telemetry/data spine | F2 requirement | REIMPLEMENT | in progress | six DBs, collectors, test packages, dashboards/analysis |
| Root-cause bug ledger | F2 requirement | REIMPLEMENT | in progress | schema + automatic linkage to tests/fix commits/regressions |

## Promotion rule

No row becomes `F2 COMPLETE` simply because the donor implementation is mature. Promotion requires migration into this repository, F2 ABI integration, tests, measurements and acceptance evidence.
