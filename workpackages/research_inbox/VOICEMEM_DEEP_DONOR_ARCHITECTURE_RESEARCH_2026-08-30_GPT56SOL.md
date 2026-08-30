# VoiceMem — Deep Donor Architecture Research for Frankenstein 2.0

**Classification:** RESEARCH INPUT / DONOR FORENSICS / REVIEW + SUCCESSOR CANDIDATES  
**Organ:** GPT-5.6 Sol · federated Architect research organ  
**F2 base observed before packet generation:** `560c05da55ed5d7b7679496742c71ce16b37182d`  
**VoiceMem public source observed:** `xzf-thu/VoiceMem@d587d424a02727d9ff3ef6f8e672a39a19ce64a7`  
**Uploaded ZIP SHA-256:** `535ed07d8af8da7fb8b8b5a31ee3105b0fa92fb7d739863a00c8159e099641e0`  
**Observed package version:** `0.2.3`

## 0. Evidence boundary

This document is not a build receipt and carries zero F2 runtime/whole-system credit.

Observed directly in the uploaded tree:
- 272 files;
- 112 Python files;
- approximately 25,784 Python lines;
- local `compileall` passed (syntax scope only);
- evaluation harness and example score text are present;
- no full benchmark `results/` receipts were observed in the uploaded tree;
- `finetune/README.md` explicitly states that the full training data is not in the repository.

Therefore:
- source mechanism descriptions are `DONOR_SOURCE`;
- empirical comments in source are `DONOR_AUTHOR_ENGINEERING_OBSERVATION`;
- paper/README benchmark numbers are `EXTERNAL_AUTHOR_CLAIM` until reproduced;
- F2 mappings are `INFERENCE/OPEN_HYPOTHESIS`;
- no donor store/model/graph output becomes F2 canonical truth.

## 1. Architectural compression

The highest-value abstraction is not the biological “left brain/right brain” label. VoiceMem behaves more generally as a **demand-shaped, multi-timescale, evidence-partitioned adaptive state architecture**.

Its strongest pattern is to assign different information to different update laws, confidence laws, retrieval laws, consolidation cadence, and action relevance rather than putting all semantically related information into one undifferentiated memory layer.

```text
Perception
  -> typed/raw evidence
  -> cheap admission/gating
  -> multiple memory/update regimes
  -> query-conditioned retrieval/projection
  -> response/action candidate
  -> observed reaction/outcome
  -> response experience / consolidation
  -> later policy/context adaptation
```

F2 must retain stronger authority boundaries:

```text
retrieval != observation
memory != current fact
trait/profile != truth
candidate identity != identity
policy candidate != causal proof
cue match != effect authority
```

## 2. Source architecture map

### Left / informational path

Key sources: `voicemem/leftbrain/brain.py`, `memory_repository.py`, `local_memory_store.py`, `extract_facts_openai.py`, `cognitive_graph/*`, `slot_split/*`, `time_expand.py`, `merged_extraction.py`.

Observed mechanisms include additive fact extraction; code-level junk filtering where prompt-only constraints failed; query/time/lexical rescue over vector similarity; retrieval-pool-driven dynamic slot emergence; query activation history as evidence for latent useful structure; append-only specificity; conservative per-speaker retrieval; near-deduplication; assistant-said exclusion unless explicitly queried; and query-only relative-date transformation.

### Right / person-and-response path

Key sources: `voicemem/rightbrain/brain.py`, `traits_store.py`, `store.py`, `experience_repository.py`.

Observed mechanisms include user-person claims separated from topic entities; emotion as evidence metadata; evidence quote and cause reference beneath trait claim; response experience separated from user trait; `next_time_policy`; temporal supersession instead of destructive deletion; cheap gates with explicit-affect override; semantic trait thresholding; per-source context quotas; delayed consolidation; and reduced repeated generative rewriting after loss of names/numbers/times was observed.

### Streaming / perception path

Key sources: `voicemem/stream.py`, `orchestrator.py`, `utils/audio/perceiver.py`, `environment/*`, `voiceprint/*`, `tts.py`.

Observed mechanisms include local speculative work in VAD/silence windows; cancellation when speech resumes; lazy expensive perception; prior-turn affect explicitly reused as prior context rather than fresh perception; UNKNOWN for short/noisy speaker windows; candidate voiceprint != named identity; later reconciliation; adaptive multi-centroid profiles; scene-triggered prospective intentions; exact sub-label matching to reduce false triggers; repeated-day routine induction; sound-only evidence without fabricated textual fact; PCM16 framing repair; and typed startup SKIP/SLOW/FAIL diagnostics.

## 3. P0 donor mechanism: demand-shaped projection

VoiceMem's dynamic slot path does not cluster the whole corpus at ingest time. The candidate pool comes from memories that were **actually retrieved together**. Entities co-occurring in those results form a graph. Connected components are greedily peeled; candidate subsets are scored against historical query-activation sets using mean Jaccard overlap. Low-support candidates are skipped without permanent rejection.

Research principle:

```text
stored evidence
+ repeated real demand
+ query activation history
-> candidate useful projection
```

Safe F2 form:

```text
WP301 RetrievalPlan receipts
+ causal query/need identity
-> query activation log
-> noncanonical ProjectionCandidate
-> held-out utility / anti-feedback test
-> optional admitted projection/index
```

Do not mutate canonical memories or infer new facts from the cluster.

### Counterhypothesis: self-reinforcing retrieval
A newly promoted projection can make its own members easier to retrieve, producing more activation and apparent support for itself.

Required controls:
- shuffled-query control;
- popularity-matched control;
- held-out future-query utility;
- concentration/Gini or maximum-cluster-coverage metric;
- projection cardinality/fan-out budget;
- no expensive reconsideration on unchanged evidence generation;
- counterevidence/reversion path.

This belongs above accepted WP301 G1 as a separate ProjectionCandidate producer, not as a rewrite of deterministic ranking.

## 4. Claim / Evidence / Cause / Policy separation

The donor documents failure of an older graph where one node layer represented traits, topics and emotions. Source comments report collapse into mega-nodes, including a sadness node with 61 items and a person node with 52 links. The v2 direction instead stores a claim, concrete evidence, emotion as evidence metadata, a cause reference back to factual memory, and response experience separately.

F2 already has WP303 FACT/EPISODE/METHOD/PROCESS. VoiceMem suggests relations above those kinds:

```text
ClaimCandidate
  -> supported_by -> EPISODE/EVIDENCE refs
  -> contextualized_by -> causal/fact refs
  -> contradicted_by -> refs
  -> superseded_by -> newer ClaimCandidate

ResponsePolicyCandidate
  -> derived_from -> PROCESS/EPISODE refs
  -> outcome_refs -> measured outcomes
  -> processing_credit_ref -> WP305 candidate
```

`ClaimCandidate` is not FACT. `next_time_policy` is not validated method credit. User reaction after action A does not prove A caused it.

## 5. Non-destructive temporal state

VoiceMem keeps superseded older situation state and downweights it. F2 WP300 G1 already has the stronger deterministic substrate: ACTIVE, DEGRADED, SUPERSEDED, immutable payload/provenance, exact generation/digest fences, and no clock-driven automatic mutation.

Do not add automatic recency decay to WP300. Keep separately:
- lifecycle status;
- query-time temporal relevance signal;
- validity interval/context where evidenced.

Temporal falsifier:
- “What is true now?” should prefer the successor;
- “What was true before date T?” should still retrieve the old state.

## 6. Query transformation without state mutation

`time_expand.py` addresses representation mismatch between normalized absolute dates in storage and relative temporal expressions in queries. It transforms only the retrieval representation.

General F2 form:

```text
CanonicalInput
 -> ContextAdapter(input identity + reference time + timezone + adapter version)
 -> DerivedQueryView
 -> retrieval
```

Never overwrite the original input or memory. This generalizes to aliases, units, generation/version references, roles and known entity IDs. Every adapter should expose input digest, adapter identity/version, reference identities, output digest, transformation class and provenance.

## 7. Memory pollution is a write-side retrieval problem

VoiceMem source comments describe prompt-only attempts failing to stop extraction of assistant outputs and one-off requests. Because semantically similar junk can crowd true memories out of top-k, code-level admission filters and conservative clause rescue are used.

F2 implication: retrieval quality cannot be repaired only at retrieval time.

Needed tests:
- request-only should not become factual memory;
- fact + request should preserve the fact;
- quoted assistant text should not silently become user fact;
- imperative-shaped stable preferences must remain distinguishable from requests;
- injected junk should not displace critical memory from top-k.

## 8. Experience memory and method learning

VoiceMem keeps assistant response experience separate from user traits and may store previous failure, effective approach and next-time policy.

Safe F2 chain:

```text
Action/response episode
 -> verified reaction/outcome evidence
 -> Process/Method candidate
 -> matched ablation or repeated evidence (WP305)
 -> bounded Method credit candidate
 -> ContextCompiler may retrieve it
```

Unsafe chain:

```text
one positive reaction -> causal method truth
```

The donor is strongest as candidate generation; F2 already provides a stricter method-credit boundary.

## 9. Source quotas as epistemic context composition

VoiceMem observed that high-priority profile/response-experience items could consume the full top-k and hide relevant episodes, so it uses per-source quotas.

For WP306 this suggests a testable extension: combine cost-aware context selection with source-class diversity/coverage constraints. Do not adopt blindly; a quota can suppress a legitimately dominant source.

Required ablation: no quota vs fixed quota vs adaptive quota by task/need; measure held-out answer quality, evidence coverage, irrelevant tokens and cost.

## 10. Consolidation should not run at every delta

Donor comments report high latency from per-ingest consolidation and describe moving it to accumulated-new-memory or session boundaries. Repeated LLM refinement was also reported as lossy for factual fields.

General rule:
- fast path writes evidence;
- slow path consolidates when justified;
- evidence text remains immutable or minimally normalized;
- summaries/projections are rebuildable derivatives.

This aligns strongly with F2's canonical-evidence vs projection distinction.

## 11. Prospective memory = deferred intent + future cue

`scene_trigger.py` is directly transferable at the mechanism level.

Donor:

```text
pending intention
+ future detected scene
-> trigger eligibility
```

F2:

```text
DeferredIntent.revisit_condition_ref
+ fresh typed Perception/Presence evidence
-> CueMatchCandidate
-> revisit evaluator
-> Agency/Pulse re-entry
-> normal action/effect authorization
```

CueMatchCandidate cannot directly execute an effect. Coarse scene plus specific label provides a useful false-trigger defense.

## 12. Unknown-first identity and adaptive prototypes

The donor documents fragmentation caused by short/noisy speaker windows and changes behavior toward “unknown this turn rather than pollute identity”. This is compatible with WP706's law that soft familiarity is not identity.

Potential donor primitive:
- quality-weighted prototype;
- cumulative averaging while evidence is sparse;
- capped support so new evidence eventually retains influence;
- multiple subcentroids for legitimate modes;
- candidate reconciliation only after stronger evidence.

Identity authority must remain outside the prototype.

Required adversarial test: inject low-quality cross-person samples; verify prototypes may form candidates but canonical identity does not drift/merge. Test short/noisy, repeated-clean and explicit-name-conflict cases separately.

## 13. Speculative compute inside natural slack

VoiceMem uses VAD/silence as a compute window: begin local speculative work, cancel if speech resumes, avoid irreversible/network effects.

WP505 G1 currently handles deterministic compute allocation, not temporal slack exploitation. A future runtime extension can model a typed `SlackBudget` carrying window identity, bounded work, cancellation generation, allowed candidate classes and forbidden effect classes.

Speculative result must bind input generation/digest, completion/cancellation state, validity fence and exact compute cost. Acceptance must measure actual critical-path latency saved rather than theoretical overlap.

## 14. Lazy perception and typed staleness

Expensive perception is lazy in VoiceMem. Where current full emotion perception is too expensive for a speculative window, prior-turn affect can be reused as prior context.

F2 must strengthen the typing:
- PRIOR_AFFECT != CURRENT_AFFECT_OBSERVATION;
- stale evidence carries source turn/generation/age;
- required-current evidence missing -> UNKNOWN/HOLD.

This permits efficient context reuse without epistemic collapse.

## 15. Hybrid deterministic gate + expensive model

VoiceMem repeatedly uses cheap deterministic/lexical/acoustic gates for obvious cases and expensive model work for uncertain/high-value cases: rho threshold before slot judgment, explicit dissatisfaction/correction override, short/filler gating, and coarse acoustic fallback.

This supports HCU selective computation, but false negatives must be measured. Candidate WP800/WP806 test: held-out rare but important events; compare always-heavy, always-cheap and gated policies; report miss rate, cost, latency and calibration.

## 16. Same-input model-call fusion

`merged_extraction.py` records excessive chat-call fan-out for analyses consuming the same utterance and merges fact extraction, cognitive annotation and trait extraction into one structured call with fallback if fields are absent/invalid.

Transfer conditions:
- same immutable input;
- outputs independently verifiable;
- no hidden sequential dependency;
- each output keeps provenance;
- malformed one field does not grant success to others.

This is a good HCU/provider-cost optimization candidate.

## 17. Prompt locality is an ABI problem

A donor comment records a structured-output failure caused by competing nearby output instructions. Moving the explicit output shape to the nearer user prompt repaired the behavior.

Architectural lesson: prompt contract prose is not an ABI.

Required: schema parser, exact field validation, negative cases, prompt-perturbation tests, and no success merely because a model says it complied.

## 18. Evaluation/evidence lessons

VoiceMem evaluation code persists incrementally per conversation, supports resume, separates expensive answer generation from rescoring, keeps config, and records Git/source/environment provenance. These ideas map well to F2 run packages.

Boundary: uploaded source includes example output text but no complete benchmark receipts; benchmark performance is not independently reproduced. Training code/hyperparameters exist, but full training data is absent, so training reproduction remains blocked by data lineage.

## 19. External triangulation

- **VoiceMem — arXiv:2608.26005:** primary author description; performance remains author-reported until reproduced.
- **SAGE graph-memory — arXiv:2605.12061:** independently studies self-evolving graph memory with reader/writer feedback; supports studying feedback-driven memory structure, not transfer proof.
- **MOSS — arXiv:2607.04391:** auditable relational memory and inductively derived conceptual vocabulary; useful comparison for emergent ontology/projection.
- **SAGE novelty gate — arXiv:2605.30711:** cheap novelty gating plus expensive uncertain-case handling; relevant fast/slow analogy.
- **Complementary learning systems — PMID:22141588:** supports different update regimes for different forms of memory; does not validate left/right-brain branding.
- **Prospective-memory systematic review — PMID:42364798:** useful analogy for separating cue detection, intention retrieval and post-retrieval control.

## 20. F2 delta map

| VoiceMem donor | Current F2 | Correct action |
|---|---|---|
| Supersession without deletion | WP300 G1 accepted | REVIEW; keep |
| Multi-axis retrieval | WP301 G1 accepted | REVIEW; keep |
| Query-activation-derived emerging slots | not part of WP301 G1 | separate ProjectionCandidate research |
| Familiarity with uncertainty | WP302 G2 + WP706 G1 | add quality/open-set falsifiers |
| Claim/evidence/cause separation | WP303 G1 gives memory kinds | relation/candidate layer only if tests justify |
| Response experience -> next policy | WP304/WP305 | candidate generation + ablation; no causal promotion |
| Query-only temporal expansion | WP306 G4 context substrate | provenance-bound adapter candidate |
| Source quotas | WP306 | ablation candidate |
| Deferred scene trigger | WP203/205 + Presence | prospective cue evaluator candidate |
| Lazy perception | WP700/701 | dependency/cost gating candidate |
| Speculative VAD-window compute | WP505/WP705 | runtime successor research |
| Adaptive multi-centroid | WP706 | soft prototype candidate, never identity authority |
| Evaluation checkpoint/provenance | WP005/runpackages | donor-method input |

## 21. Worker priority

### P0 — high information / low architectural risk
1. Demand-shaped ProjectionCandidate experiment over stored retrieval/query-activation receipts, with shuffled/popularity controls.
2. Memory contamination micro-suite: request junk, assistant-output contamination, composite fact+request, source monopoly.
3. Prospective DeferredIntent cue evaluator as candidate-only re-entry mechanism, no effect authority.
4. Open-set familiarity/identity adversarial suite using quality + repeated observations + UNKNOWN.

### P1
5. Query-semantic ContextAdapter with exact reference-time/timezone/generation provenance.
6. Source-quota ContextCompiler ablation.
7. Same-input transform fusion benchmark with schema/fallback tests.
8. VAD/slack speculative compute A/B trace.

### P2
9. Adaptive multi-prototype generalization beyond voice after identity poisoning tests pass.
10. Routine/scene-derived long-term behavior pattern induction, only as hypothesis/projection.

## 22. Explicit anti-import laws

- Do not add a second canonical truth store.
- Do not copy “left brain/right brain” as a scientific claim.
- Do not treat trait/persona inference as fact.
- Do not treat retrieval co-activation as truth or causal structure.
- Do not let a cue-trigger directly execute effects.
- Do not let soft similarity mint identity.
- Do not automatically decay canonical memory from wall clock.
- Do not repeatedly generatively rewrite evidence-bearing source text.
- Do not grant F2 credit from donor paper/README claims.
- Do not treat compileall as runtime validation.
- Do not claim training reproducibility without the absent dataset lineage.

## 23. Exact next worker discriminators

### D1 — Demand-shaped projection
Input: canonical retrieval/query receipts.  
A: current static retrieval projections.  
B: candidate projection learned from historical co-activation.  
Controls: shuffled activation, popularity-matched activation.  
Measure: held-out recall/precision, token cost, fan-out, concentration.  
Pass: B improves held-out utility beyond controls without unacceptable concentration.  
Fail: gain disappears under control or creates feedback monopoly.

### D2 — Context contamination
Inject user fact, one-off request, assistant text, same-token irrelevant memory, and superseded historical state. Measure top-k useful evidence rate and critical-fact displacement.

### D3 — Prospective cue
DeferredIntent condition requires coarse+specific cue. Feed exact cue, near miss, stale cue and conflicting cue. Pass only a revisit candidate; never effect.

### D4 — Open-set identity/familiarity
Short/noisy sample, repeated clean sample and explicit conflicting named identity. Measure false merge, false split and UNKNOWN rate. Soft familiarity never becomes canonical identity.

### D5 — Speculative compute
A/B identical stream. Measure p50/p95 critical-path latency, cancelled work, CPU/GPU contention and stale-result rejection. No claimed benefit without trace evidence.

## 24. Bottom line

The deepest transferable lesson is:

> Organize memory not merely by what information describes, but by **how it may change, what evidence supports it, what may supersede it, when it should be retrieved, what kind of decision it may influence, and what authority it must never acquire.**

The second lesson is:

> Let **real usage create candidate structure**, but require held-out utility and anti-feedback controls before promotion.

The third is:

> Treat **uncertainty, candidate status, supersession, and response experience as first-class typed states**, rather than squeezing them into one graph or one embedding score.

These ideas should be fed forward as bounded research inputs above existing F2 primitives, not as a wholesale VoiceMem import.
