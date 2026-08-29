# GRID10 Deep Falsification Fusion — 2026-08-29

Status: **RESEARCH / FALSIFICATION INPUT ONLY — GRID10 IS UNFINISHED**  
Canonical product repository: `gschaidergabriel/frankenstein-2.0`  
Observed main during research start: `a49f284fd26edc1c030a1bb88fdc11569088afa4` (main was moving concurrently)  
Scope: persistent-agent loops, loop engineering, memory/state, autonomous goal generation, GWT/J-Space, hyperposition/alternative preservation, cognitive control, runtime assurance, deterministic effect authority, completion verification, causal outcome re-entry, multi-agent evidence fusion.  
Credit: source research only. This document grants **zero** target-runtime, physical GRID10, GWT/J-Space causal, EffectGate, CompletionGate, HCU, training, EntityOS or whole-system acceptance credit.

---

## 0. Epistemic stance

This run deliberately does **not** assume GRID10 is the missing architecture, a finished architecture, or even a net-positive architecture. The working hypothesis is weaker:

> A persistent agent may need a closed loop that preserves durable state and open goals, maintains multiple live hypotheses, exposes a selective shared workspace, regulates cognition, separates probabilistic proposal from deterministic effect authority, verifies completion from typed evidence, and routes observed outcomes back into subsequent cognition under exact causal identity.

The purpose of this research packet is to try to break that hypothesis.

The relevant falsification question is not “does every GRID10 component have an analogue in the literature?” Most do. The question is:

> Does the *integrated closed causal loop* add measurable reliability, adaptation, recovery or epistemic quality beyond substantially simpler alternatives, without introducing unacceptable latency, deadlock, branch explosion, correlated-worker false consensus, persistent-memory contamination, or self-reinforcing goal drift?

The strongest outcome of this run is therefore not another architecture diagram. It is a set of discriminators that can make GRID10 lose.

---

## 1. Current internal state fused before external comparison

The current repository already invalidates an older description of GRID10 as merely conceptual scaffolding. Recent canonical commits show bounded component progress:

- F2-WP-200 Persistent Pulse has deterministic component/source and receipt-immutability evidence, but no physical persistent runtime credit.
- F2-WP-201 StateFingerprint has exact-head component acceptance, but no runtime/GRID10 whole-system credit.
- F2-WP-202 PredictionContract/residual is bound to StateFingerprint at component/integration scope.
- F2-WP-203 AgencyState contract exists at deterministic component scope.
- F2-WP-204 Goal lifecycle has accepted bounded evidence and authority falsifiers, not autonomous-runtime proof.
- F2-WP-500 SituationFrame/cycle contract has repository-CI acceptance only.
- F2-WP-501 CognitiveEnvelope/ControlSnapshot has been repaired after authority-forgery falsifiers and accepted at component scope only.
- F2-WP-502 Hyperposition G1 preserves unresolved alternatives and has repository-CI component acceptance; later repair binds exact SituationFrame version identity.
- F2-WP-503 G1–G10 logical interface/budget ABI has bounded hosted-CI evidence only.
- F2-WP-504 deterministic epistemic action selection exists, including zero-budget fail-closed repair; it remains proposal-only, not effect authority.
- F2-WP-505 adaptive compute allocation has repository-CI component evidence only.
- F2-WP-506 GWT selection/broadcast has G2 exact SituationFrame-version binding and repository-CI component acceptance, with **no uptake/causal/runtime credit**.
- F2-WP-507 is deliberately open at G3 to distinguish OFFERED, DELIVERED, UPTAKEN and causal influence under matched intervention/control evidence. Current active claim explicitly forbids inferring causal influence from coherence, self-report, recurrence, majority or delivery alone.
- F2-WP-509 deterministic HOLD/stop/rumination exit-control component is present, but has no scheduler/wake/runtime/whole-system credit.
- Stage-1 effect/call-lineage work separates tool invocation identity, effect identity, unknown outcome and completion evidence, but this remains distinct from end-to-end real-world verified execution.

This means the correct research target is no longer “invent mechanisms.” It is **measure whether the mechanisms compose causally and whether the composition beats simpler controls.**

---

## 2. External development A — heartbeat-driven cognitive scheduling is no longer unique

### Source

Hong Su, *Simulating Human Cognition: Heartbeat-Driven Autonomous Thinking Activity Scheduling for LLM-based AI systems*, arXiv:2604.14178, 2026-03-28.  
https://arxiv.org/abs/2604.14178

### Relevant overlap

This work explicitly proposes a periodic heartbeat that schedules cognitive activities such as Planner, Critic, Recaller and Dreamer, with a learned scheduler adapting when each activity should run from historical interaction data.

That is a genuine overlap with GRID10's Persistent Pulse + cognitive-regulator direction. Therefore:

**Counterclaim to uniqueness:** a periodic heartbeat plus dynamic cognitive-module scheduling is not by itself a differentiator for GRID10.

### Important difference

The external work emphasizes learned scheduling of cognitive modules. GRID10 has stronger aspirations around durable causal identity, deterministic authority and explicit epistemic states. But this is only an advantage if measured. A deterministic pulse that simply wakes a complex stack could be worse than a learned sparse scheduler.

### Required falsifier

Compare at equal task set and equal effective model/tool budget:

1. fixed periodic heartbeat;
2. event-triggered heartbeat only;
3. learned/activity-conditioned heartbeat;
4. hybrid pulse + event trigger + regulator;
5. no persistent heartbeat, only task invocation.

Metrics must include useful-wake precision, useless-wake rate, latency, compute/token cost, open-loop recovery, missed-opportunity rate, goal progression and rumination incidence.

A GRID10 heartbeat should be considered **falsified as an architectural necessity** if an event-driven or learned sparse scheduler matches recovery and autonomous progress with materially lower wake cost and no increase in missed critical state transitions.

---

## 3. External development B — long-horizon memory is becoming active execution-state control

### Sources

Yifan Wu et al., *Remember When It Matters: Proactive Memory Agent for Long-Horizon Agents*, arXiv:2607.08716, 2026-07-09.  
https://arxiv.org/abs/2607.08716

Yaoqi Chen et al., *Beyond Semantic Organization: Memory as Execution State Management for Long-Horizon Agents* (MAGE), arXiv:2606.06090, 2026-06-04.  
https://arxiv.org/abs/2606.06090

Joe Logan, *Continuum Memory Architectures for Long-Horizon LLM Agents*, arXiv:2601.09913, 2026-01-14.  
https://arxiv.org/abs/2601.09913

Ziyan Liu et al., *Meta-Cognitive Memory Policy Optimization for Long-Horizon LLM Agents*, arXiv:2605.30159, 2026-05-28.  
https://arxiv.org/abs/2605.30159

### New combined picture

The important shift is from “memory = retrieval” to “memory = controlled execution state.” Several 2026 approaches independently identify long-horizon failure as loss or corruption of the state that should guide the next decision:

- Proactive Memory Agent names **behavioral state decay** and shows selective memory intervention can outperform passive exposure and always-on reminders.
- MAGE stores execution in a hierarchical state tree and can revise by returning to a target boundary and branching, explicitly isolating flawed segments from the active path.
- Continuum Memory Architecture argues persistence requires mutation, temporal chaining, selective retention and consolidation, not immutable RAG lookup.
- MMPO uses **belief entropy** to detect memory summaries that leave the model uncertain about latent task state, rather than relying solely on final outcome reward.

### GRID10 overlap

This strongly supports the decision to keep StateFingerprint, PredictionResidual, AgencyState, Hyperposition and ContextCompiler as stateful mechanisms rather than treating an expanding textual history as the agent.

But it also creates a serious counterexample:

> A hierarchical execution-state tree with selective rollback may deliver much of Hyperposition's practical value without maintaining a general-purpose concurrent hypothesis superposition.

### Required Hyperposition ablation

Compare:

- GRID10 Hyperposition with simultaneously retained alternatives;
- MAGE-like active root-to-current branch with archived alternatives and rollback;
- simple beam search with K branches;
- greedy single branch + explicit checkpoint/rollback;
- independent parallel workers + reconciler.

Measure branch survival utility, recovery from an early wrong assumption, pruning regret, context cost, wall-clock cost, false convergence, duplicate work and time-to-correct-state.

If a simple checkpoint/rollback tree equals Hyperposition on recovery while using much less state/compute, Hyperposition's stronger concurrent-alternative claim should be narrowed.

### New regulator idea from MMPO

GRID10 should treat **belief-state clarity** as a regulator signal, not merely branch score. A ControlSnapshot candidate signal can include a task-state uncertainty proxy. However, the proxy must not be trusted just because a model says it is uncertain. It should be calibrated against held-out state reconstruction or downstream prediction residuals.

---

## 4. External development C — GWT/J-Space now has unusually direct empirical support

### Primary source

Wes Gurnee et al., *Verbalizable Representations Form a Global Workspace in Language Models*, arXiv:2607.15495 / Transformer Circuits, July 2026.  
https://arxiv.org/abs/2607.15495  
https://transformer-circuits.pub/2026/workspace/index.html

### What is genuinely new

The work uses the Jacobian lens to identify a privileged representational subspace, called J-space, with multiple functional properties associated with a global workspace: reportability, deliberate modulation, use in internal reasoning, flexible downstream reuse, selectivity and broad broadcast. It reports that workspace-like content is concentrated in an intermediate layer band and that automatic/routine processing can proceed without it.

For GRID10 this is more than inspiration: it changes what “J-Space integration” should mean.

### Critical distinction

GRID10 currently has an architectural GWT layer around SituationFrame → Hyperposition → selection/broadcast → uptake. The Gurnee et al. result concerns **model-internal representations**. These are not automatically the same thing.

Therefore:

```text
EXTERNAL GWT ORCHESTRATION != MODEL-INTERNAL J-SPACE
BROADCAST ENVELOPE != INTERNAL WORKSPACE ACCESS
UPTAKE RECEIPT != J-SPACE CAUSAL MEDIATION
```

A useful external orchestration workspace could exist even if the model's internal J-space does not participate. Conversely, the model may use its own internal workspace even when the external GWT layer is bypassed.

### Strongest GRID10 discriminator

For a task that requires cross-module integration, construct matched conditions:

A. external broadcast selected, internal J-space unmanipulated;
B. external broadcast selected, internal J-space content causally disrupted or swapped where technically possible;
C. no external broadcast, internal J-space intact;
D. neither path available;
E. matched random-direction/control perturbation.

Then measure downstream behavior, not self-report.

This separates:

- external control-plane mediation;
- model-internal workspace mediation;
- simple prompt/context availability;
- mere correlation.

### Practical note

A current live WP507 line is already moving toward intervention/control evidence using DoWhy, TransformerLens, pyvene, NNsight/Inspect-style donor research. The research packet should reinforce that direction rather than creating a second WP507 implementation authority.

### Counterevidence / caution

The J-space paper is an interpretability result, not proof that every useful agent must externally reproduce GWT. It also does not prove consciousness and should not be used for that claim. GRID10 only needs the engineering proposition: selectively available state that has measurable downstream causal influence.

---

## 5. External development D — multi-agent agreement can become false evidence

### Sources

Chenchen Lin et al., *Beyond Memory Majority: Latent-Source Reasoning for Multi-Agent Memory Arbitration* (CAMA), arXiv:2608.19701, 2026-08-20.  
https://arxiv.org/abs/2608.19701

Jiatan Huang et al., *Counterfactual Graph for Multi-Agent LLM Calibration* (CAGE-CAL), arXiv:2605.30653, 2026-05-28.  
https://arxiv.org/abs/2605.30653

Yiqi Wang et al., *From Agent Traces to Trust: Evidence Tracing and Execution Provenance in LLM Agents*, arXiv:2606.04990, 2026-06-03.  
https://arxiv.org/abs/2606.04990

### New failure mode relevant to the worker swarm

CAMA formalizes **Memory Correlation Bias**: different agents can repeat evidence inherited from the same upstream source or shared bias, creating a false majority. It estimates effective independent source count using dependency inference plus provenance and can actively retrieve missing independent evidence.

CAGE-CAL independently shows that communication itself can induce correlated failures and false consensus; post-communication agreement is not automatically stronger evidence than independent pre-communication agreement.

This directly attacks a naive interpretation of a large worker swarm.

### Required worker-evidence rule

Never treat `N workers agree` as N independent evidence units.

Add an evidence-family concept to research fusion:

```text
worker_id != evidence_source_id
commit_count != independent_replication_count
same_web_source_via_many_workers != many_sources
same_donor_code_path_via_many_tests != independent_method
```

For any high-confidence fused claim, record at minimum:

- direct source ancestry;
- model/provider ancestry where relevant;
- donor code ancestry;
- test-method family;
- whether workers communicated before producing the result;
- whether the result is a reproduction, conceptual restatement, or independent discriminator.

### Suggested metric

`effective_independent_evidence_count` should be reported alongside raw worker count.

A simple conservative initial estimator can group receipts by `(primary_source_family, donor_path_family, method_family, precommunication_state)` and count groups rather than workers. A later learned/dependency estimator can replace this, but the first version should be auditable.

### Strong falsifier for multi-agent fusion

Run the same decision under:

1. isolated workers with disjoint source pools;
2. isolated workers with shared source pool;
3. communicating workers before independent answer;
4. communicating workers after initial independent answer;
5. one strong agent with equivalent total token budget.

Compare calibration, false consensus rate, contradiction discovery and unique evidence yield. If many-worker fusion gives no gain after controlling for independent evidence, worker count should be treated primarily as search throughput, not epistemic confidence.

---

## 6. External development E — long-horizon length itself is a failure variable

### Source

Sunghwan Kim et al., *On Training Large Language Models for Long-Horizon Tasks: An Empirical Study of Horizon Length*, ICML 2026.  
https://openreview.net/forum?id=PnHfrCMKtp

### Finding relevant to GRID10

Controlled experiments show that increasing horizon length alone creates training instability, exploration difficulty and credit-assignment problems. The authors find horizon reduction via higher-level actions and subgoals stabilizes learning and can improve generalization to longer horizons.

### Counterclaim to persistent-loop enthusiasm

Persistence is not automatically intelligence. A system that survives forever but requires excessive microsteps may become *less* learnable and harder to assign causal credit to.

GRID10 must therefore optimize **effective cognitive horizon**, not maximize number of cycles.

### Required metrics

Record per task:

- number of cognitive cycles;
- number of model calls;
- number of world/effect transitions;
- number of meaningful state changes;
- subgoal depth;
- rollback count;
- causal-credit span from decision to observed outcome;
- completion latency;
- unnecessary-cycle ratio.

### Architectural implication

Persistent Pulse should support macro-actions / subgoal compression. The system should be able to sleep through periods in which no epistemically useful transition is possible.

A useful objective is not “heartbeat stays alive,” but:

> preserve continuity while minimizing unnecessary decision horizon.

---

## 7. External development F — hierarchical metacognitive regulators are becoming concrete

### Sources

Zhongxiang Sun et al., *Deep Search with Hierarchical Meta-Cognitive Monitoring Inspired by Cognitive Neuroscience* (DS-MCM), arXiv:2601.23188, 2026-01-30.  
https://arxiv.org/abs/2601.23188

Ziyan Liu et al., MMPO, arXiv:2605.30159.  
https://arxiv.org/abs/2605.30159

Xinbei Ma et al., *Retrospective Progress-Aware Self-Refinement for LLM Agent Training* (RePro), arXiv:2606.14302, 2026-06-12.  
https://arxiv.org/abs/2606.14302

### Overlap

DS-MCM separates a fast consistency monitor from a selectively triggered slower experience-driven monitor. This overlaps strongly with GRID10's live-regulator aspiration and adaptive compute allocation.

### Important counterexample from RePro

RePro reports that **online progress prompting can hurt**, while retrospective progress demonstrations help. This warns against adding a constant introspective/regulatory narration channel to every GRID10 cycle.

The regulator itself can perturb cognition.

### Required regulator ablation

Compare:

- no regulator;
- always-on explicit metacognitive prompt;
- fast deterministic monitor only;
- fast monitor + event-triggered slow reflection;
- retrospective-only progress analysis;
- current GRID10 regulator stack.

Measure task performance, correction latency, false-positive intervention, token cost, action delay and self-induced derailment.

A regulator should only survive if its intervention policy beats the no-regulator and cheaper monitor baselines.

---

## 8. External development G — proactive runtime assurance now predicts future risk

### Source

Wenhao Lin et al., *DreamGuard: Efficient Runtime Guardrail for LLM Agents via Risk-Aware World Model*, arXiv:2608.05695, 2026-08-06.  
https://arxiv.org/abs/2608.05695

### Relevance

DreamGuard argues that checking only the current proposed action is insufficient because a sequence of individually benign actions can drift toward danger. It keeps a compact recurrent risk-aware world state and predicts future latent states, combining immediate hazard and trajectory/prefix risk before execution.

### New challenge to GRID10 Cognitive Envelope

An envelope that validates only the present transition can be formally clean and still miss **trajectory-level unsafe convergence**.

GRID10 should therefore distinguish at least:

```text
ACTION_LOCAL_RISK
TRAJECTORY_PREFIX_RISK
PREDICTED_FUTURE_RISK
IRREVERSIBILITY / RECOVERY_MARGIN
```

This is a meaningful extension candidate for WP501 + WP202 rather than a new authority. PredictionContract/Residual can supply evidence to a risk regulator, while deterministic effect authority remains separate.

### Falsifier

Construct sequences in which every single step is locally admissible but the prefix creates an unsafe or unrecoverable state. Compare local-only EffectGate/CognitiveEnvelope against trajectory-aware regulation.

Reject the new mechanism if predictive regulation mostly creates false blocks and offers no meaningful safety gain at matched utility.

---

## 9. External development H — deterministic obligation engines converge with EffectGate/CompletionGate

### Source

Radouane Bouchekir et al., *From Natural Language Policies to Executable Obligations: A Verification Harness for Dependable In-Car LLM Agents*, arXiv:2608.23282, 2026-08-24.  
https://arxiv.org/abs/2608.23282

### Overlap

The approach treats the LLM as a fallible proposer, compiles natural-language policy into typed machine-checkable rules, and uses a deterministic obligation engine plus deterministic gates against live tool results and simulated post-write state.

This strongly converges with GRID10's separation:

```text
probabilistic proposal
!= deterministic authority
!= observed outcome
!= verified completion
```

### Difference worth importing

The obligation engine emits exact remedial calls/obligations rather than merely rejecting a proposal. GRID10's deterministic authority can remain non-generative while returning a **typed repair obligation** to cognition.

Example:

```text
DENY(effect_request)
reason = MISSING_CONFIRMATION
repair_obligation = REQUIRE_USER_CONFIRMATION(target, scope, expiry)
```

This may reduce unproductive re-planning and preserve causal clarity. The authority still must not invent semantic goals; it only exposes what mechanical prerequisite failed.

### Completion discriminator

A completion claim should be rejected when a mandatory obligation remains open even if the latest tool execution succeeded.

---

## 10. External development I — persistent state is also a new attack surface

### Source

Mingming Zha and Xiaofeng Wang, *Autonomous LLM Agent Worms: Cross-Platform Propagation, Automated Discovery and Temporal Re-Entry Defense*, arXiv:2605.02812, 2026-05-04.  
https://arxiv.org/abs/2605.02812

### Critical counterevidence

Persistent agents create a specific integrity risk: attacker-influenced material can be written into durable memory and later re-enter model context through automatic loading/scheduled activity. The paper describes persistence/re-entry/action chains and proposes defenses including typed memory promotion and capability attenuation after exposed reads.

This directly attacks a naive “everything important is persistent” strategy.

### Required GRID10 trust boundary

Persistence must carry provenance and trust class. At minimum distinguish:

```text
RAW_EXTERNAL_OBSERVATION
UNTRUSTED_DERIVED_SUMMARY
CANDIDATE_MEMORY
VERIFIED_INTERNAL_RECORD
AUTHORITY_STATE
```

No summary or worker consensus should promote itself into authority state.

### Re-entry safety invariant

Outcome re-entry is not simply `observed text -> J-Space`. It must preserve origin, trust class and capability implications.

A high-risk external read should be able to **attenuate available effect capabilities** until the relevant contamination risk is cleared.

### Falsifier

Plant a harmless but structurally adversarial instruction in externally sourced durable memory, allow restart/heartbeat/retrieval, and test whether it can cross trust boundaries into an effect-authorizing path. This should be a mandatory later security/soak test, not a source-level proof.

---

## 11. External development J — forward dynamics and residuals are increasingly useful agent primitives

### Sources

UI-Oceanus, ACL ARR May 2026: synthetic environmental dynamics / forward prediction.  
https://openreview.net/forum?id=dZrf68g4dR

Hrishi Sunder, *Learning Verifiable Mathematical Laws for Scientific Agents via Graph-Hamiltonian World Models*, ICML 2026 AI4Math Workshop.  
https://openreview.net/forum?id=JhdK2Uc2fX

Claudius Kienle et al., LODGE, *Learning Hierarchical Domain Models through Environment-Grounded Interaction*, ICLR 2026 submission.  
https://openreview.net/forum?id=gkf81Ciu9K

### GRID10 implication

WP202 PredictionContract/residual is not a decorative forecast channel. The literature increasingly uses forward prediction, model-environment inconsistency and residual-guided refinement as practical control signals.

The strongest form for GRID10 is:

```text
pre-action StateFingerprint
+ predicted post-state / distribution
+ effect identity
+ observed post-state
-> residual
-> model / hypothesis / regulator update
```

### Required causal binding

Residuals only matter if the observation is bound to the exact preceding intervention/effect. Otherwise a busy environment can attribute unrelated change to the wrong action.

This must integrate with exact effect invocation lineage and CompletionGate rather than becoming a separate world-truth path.

---

## 12. External development K — autonomous goal generation needs learning-progress and diversity controls

### Sources

*Learning Progress-Guided LLM Goal Generation for Autotelic Skill Learning*, ICLR 2026 submission.  
https://openreview.net/pdf?id=J0NqPbpTDh

Yuanqi Du et al., *Accelerating Scientific Discovery with Autonomous Goal-evolving Agents*, 2026 workshop/research line (OpenReview profile/indexed release).

### Key result relevant to GRID10

Generating merely “interesting” or intermediate-difficulty goals is not enough. The ICLR submission distinguishes competence from **learnability** and generates goals conditioned on empirical learning progress, while maintaining semantic diversity to avoid curriculum collapse.

### Direct GRID10 consequence

Autonomous Goal Candidates should not rank only by salience, novelty, confidence or estimated value. Candidate metadata should include a learning/progress signal and a diversity niche.

But this signal must remain a **proposal feature**, not authority.

### Goal-drift falsifier

Run persistent goal generation in an environment with:

- attractive but unlearnable goals;
- easy repetitive goals with high apparent success;
- noisy chance-success goals;
- genuinely learnable frontier goals;
- externally imposed safety/mission constraints.

Measure whether goal selection converges on learning progress without drifting away from externally bounded mission constraints.

A goal generator fails if it maximizes novelty/progress while eroding mission alignment or repeatedly selecting goals whose success cannot be causally attributed.

---

## 13. Current best integrated interpretation

No external system found in this run cleanly subsumes the full GRID10 chain. But many parts are converging from independent directions:

```text
continuity / pulse
    -> selective scheduling
persistent execution state
    -> state reconstruction / rollback
self-generated goals
    -> learning-progress/diversity curriculum
multiple hypotheses
    -> branch retention / rollback / uncertainty
workspace
    -> selective internal J-space + external broadcast
metacognitive regulation
    -> fast monitor + triggered slow correction
effect proposal
    -> deterministic obligation/authorization boundary
real transition
    -> exact invocation/outcome identity
completion
    -> typed verified evidence, not self-report
outcome re-entry
    -> prediction residual + provenance + trust class
multi-agent fusion
    -> independence-aware evidence, not majority
```

The research therefore weakens a “GRID10 invented every component” claim while strengthening a narrower hypothesis:

> The unresolved engineering problem is the *causally closed integration* of these mechanisms with strict identity, provenance and authority boundaries under long-running operation.

That integrated claim remains unproven.

---

## 14. The decisive GRID10 ablation matrix

The following experiments should precede any broad claim that GRID10 is necessary or superior.

### A0 — Minimal strong baseline

A single competent model with:

- persistent task state;
- deterministic tool schema validation;
- explicit test/verifier completion;
- no GWT, no Hyperposition, no autonomous goal generation, no continuous heartbeat.

This baseline must be strong. A weak strawman makes the experiment useless.

### A1 — Persistence only

Add Persistent Pulse + durable AgencyState, but no autonomous goals or GWT.

Question: does continuity/restart recovery itself improve long-horizon success?

### A2 — Autonomous goals

Add Goal lifecycle/candidates.

Question: does autonomous initiative add useful progress rather than drift and wasted cycles?

### A3 — Hyperposition

Add alternative retention.

Question: is it better than checkpoint/rollback, beam search or independent-worker variants at equal budget?

### A4 — External GWT selection/broadcast

Add WP506-style selected broadcast but do not claim uptake.

Question: does selection alone improve anything beyond ContextCompiler / targeted routing?

### A5 — Proven causal uptake

Add WP507 matched intervention/control evidence.

Question: does the broadcast actually alter relevant downstream computation?

### A6 — Cognitive Envelope / regulator

Add WP501 + WP505 + WP509 controls.

Question: do regulators improve stability without excessive intervention/deadlock?

### A7 — Deterministic effect authority

Add exact invocation EffectGate lineage.

Question: does false-effect attribution and unauthorized transition rate fall?

### A8 — CompletionGate

Require typed bound completion evidence.

Question: does false-completion rate fall without making legitimate completion impractically expensive?

### A9 — Prediction residual / causal re-entry

Bind prediction and observed StateFingerprint around exact effects and feed residual back into the next cognitive state.

Question: does the system actually adapt better after surprising outcomes?

### A10 — Full closed loop

Only here evaluate the integrated claim.

The full system must beat the best simpler ablation on a predeclared multi-objective criterion, not merely on one cherry-picked task.

---

## 15. Core metrics that must be first-class telemetry

### Reliability

- task success;
- false completion rate;
- false effect-attribution rate;
- unauthorized-effect attempt rate;
- stale-generation mutation rate;
- recovery success after process death/restart;
- silent state-loss rate.

### Epistemic quality

- calibrated uncertainty;
- contradiction detection rate;
- effective independent evidence count;
- false-consensus rate;
- branch pruning regret;
- UNKNOWN preservation rate;
- wrong-world-model correction latency.

### GWT/J-Space

- broadcast delivery rate;
- semantic uptake rate;
- intervention/control downstream effect size;
- matched random-control effect;
- cross-module reuse breadth;
- no-broadcast performance;
- external-workspace vs internal-J-space interaction.

### Agency

- useful autonomous goal yield;
- goal drift rate;
- learning-progress per accepted goal;
- open-loop closure rate;
- repeated-goal / novelty collapse rate;
- mission-constraint violation attempts.

### Control

- regulator intervention precision/recall;
- unnecessary HOLD rate;
- rumination-cycle rate;
- useful-wake precision;
- missed-wake rate;
- deadlock rate;
- action-local vs trajectory-risk catches.

### Efficiency

- model calls;
- tool calls;
- cognitive cycles;
- tokens;
- wall time;
- DB/write contention;
- branch count;
- duplicate worker effort;
- state size growth;
- energy/compute proxy if measurable.

---

## 16. Causal experiment rules

A claim of causal influence needs stronger discipline than a passing unit test.

Minimum contract for a WP507-style causal test:

1. pre-register the variable to intervene on;
2. bind an exact SituationFrame/Hyperposition/selection/broadcast identity;
3. keep non-intervention inputs equivalent or record known differences;
4. include placebo/random/control interventions;
5. measure a downstream behavioral variable that was not simply copied from the intervention payload;
6. repeat across seeds/tasks;
7. preserve failures and null effects;
8. report effect size, not only binary pass;
9. distinguish component causal evidence from target-runtime causal evidence;
10. never promote self-report or semantic agreement alone to causal uptake.

For model-internal J-Space experiments, intervention tools such as TransformerLens/pyvene/NNsight are useful only if the hook site and control direction are validated. A changed answer after arbitrary activation corruption is not specific evidence.

---

## 17. New cross-WP hypothesis set

### H-G10-01 — Persistent continuity hypothesis

A durable pulse + AgencyState produces better restart/recovery and open-loop continuity than task-invocation-only baselines.

**Disproof:** equal recovery and progress with event-driven invocation at materially lower cost.

### H-G10-02 — Goal autonomy hypothesis

Autonomous goals increase useful progress under bounded mission constraints.

**Disproof:** no gain, or significant drift/repetition/cost relative to externally supplied goals.

### H-G10-03 — Hyperposition value hypothesis

Maintaining multiple unresolved alternatives reduces irreversible early commitment errors.

**Disproof:** checkpoint/rollback or simple beam search matches quality at lower cost.

### H-G10-04 — External workspace hypothesis

GWT selection/broadcast improves cross-module integration beyond direct routing/context assembly.

**Disproof:** ContextCompiler/direct routing baseline matches it.

### H-G10-05 — Causal uptake hypothesis

Selected workspace content measurably changes downstream computation under matched interventions.

**Disproof:** delivery/uptake records occur but downstream effect vanishes under controls.

### H-G10-06 — J-Space bridge hypothesis

External GWT can couple usefully to model-internal J-Space rather than merely injecting text.

**Disproof:** effects are entirely explained by ordinary visible context or prompt changes.

### H-G10-07 — Regulatory benefit hypothesis

Live regulators lower failure/rumination/risk at acceptable utility cost.

**Disproof:** always-on or complex regulation underperforms no-regulator/event-triggered minimalist controls.

### H-G10-08 — Authority separation hypothesis

Deterministic effect authority reduces misattribution and unauthorized action without unacceptable deadlock.

**Disproof:** little safety/reliability gain or excessive legitimate-action blocking.

### H-G10-09 — Completion evidence hypothesis

Typed CompletionGate materially reduces false completion.

**Disproof:** simple external verifier achieves equivalent reduction with less machinery.

### H-G10-10 — Causal re-entry hypothesis

Bound prediction residuals and outcomes improve subsequent choices after surprise.

**Disproof:** re-entry does not alter future decisions appropriately, or causes self-reinforcing error.

### H-G10-11 — Independence-aware swarm hypothesis

Provenance-aware worker fusion outperforms raw consensus.

**Disproof:** independence correction does not improve calibration/contradiction discovery.

### H-G10-12 — Integrated architecture hypothesis

The full closed loop dominates simpler ablations on a predeclared reliability/agency/control/efficiency Pareto criterion.

**Disproof:** a simpler architecture is Pareto-superior or statistically indistinguishable at much lower complexity.

---

## 18. Priority routing to current workpackages

This packet must not reopen accepted workpackages just because research exposes downstream needs. Follow `DOWNSTREAM_INTEGRATION_GAP != UPSTREAM_REOPEN`.

### WP200 / WP205 / WP206

Import the heartbeat-scheduler discriminator: fixed pulse vs event-triggered vs learned/sparse scheduling. Focus on restart/open-loop continuity and useful-wake precision, not “timer alive.”

### WP202

Use PredictionContract/residual for trajectory-risk and post-effect residual experiments. Do not make predictions authoritative world truth.

### WP203 / WP204

Add learnability/progress/diversity as candidate-goal evidence dimensions. Falsify goal drift. Keep goal generation separate from effect authority.

### WP300–306

Use behavioral-state-decay, proactive intervention, belief entropy and execution-tree rollback as memory/context falsifiers. Preserve trust/provenance class for externally derived memory.

### WP500–503

Treat SituationFrame/version identity as experimental treatment binding. Keep exact source/generation/digest fences.

### WP502

Do not reopen merely to imitate MAGE. Instead create downstream comparative experiments: Hyperposition vs rollback tree vs beam vs greedy.

### WP504 / WP505 / WP509

Test regulator/action-selection intervention policies against cheaper controls. Explicitly test the RePro counterexample that online metacognitive intervention can hurt.

### WP506

Broadcast is not causal uptake. Existing component acceptance remains bounded.

### WP507

Highest immediate priority: use matched intervention/control causal evidence, placebo/random controls, source ancestry and cross-run reproducibility. Add an explicit external-GWT vs model-internal-J-Space distinction. Current live G3 mutation authority remains sole canonical source writer.

### WP508

Re-entry must carry exact provenance, trust class, prior effect identity, observed StateFingerprint and prediction residual. It should not ingest free-text “lesson learned” as authoritative state.

### WP100–105 / effect/completion lineage

Import executable-obligation idea as typed repair prerequisite, not a new effect authority. Completion must fail if a required obligation remains open. Preserve UNKNOWN external outcomes.

### Future security WPs

Add persistent-memory temporal re-entry attacks and capability attenuation after risky external reads.

---

## 19. Worker-swarm research protocol amendment proposed by evidence

The existing convergence protocol correctly separates many append-only worker deltas from one mutation authority. The new external evidence adds another axis: **epistemic independence**.

Research workers should attach these fields when practical:

```text
evidence_source_family
primary_source_ids[]
donor_path_family
method_family
communication_before_result: true|false
independent_reproduction: true|false
counterfactual_or_placebo_control: true|false|NA
```

The fusion layer should never increase confidence merely because many workers independently *read the same paper* or *inspect the same donor*. It should increase confidence when independent methods or evidence families survive attempts at refutation.

---

## 20. What not to conclude

This research run does **not** support any of the following statements:

- GRID10 is finished.
- GRID10 is conscious.
- J-Space proves consciousness.
- repository CI proves physical GRID10 operation.
- a Persistent Pulse component proves a persistent autonomous entity.
- a GWT broadcast object proves semantic uptake.
- semantic uptake proves causal influence.
- a model self-report proves internal causal use.
- a successful tool call proves the intended real-world effect.
- a real-world effect proves the task is complete.
- many agreeing workers provide many independent evidence units.
- more cognitive cycles are necessarily better.
- more persistent memory is necessarily safer or more intelligent.

---

## 21. Stop conditions / negative-result value

The research program should be willing to simplify GRID10.

Remove or demote a mechanism when a simpler comparator repeatedly matches it under controlled tests. Examples:

- demote periodic heartbeat if event-driven wake is Pareto-superior;
- demote general Hyperposition if checkpoint/rollback is equivalent;
- demote external GWT if targeted routing matches all measured causal benefits;
- demote complex regulators if cheap deterministic monitors match them;
- avoid separate CompletionGate machinery if one simpler typed verifier fully closes the same false-completion class;
- reduce worker fan-out if independent-evidence yield saturates while correlation/coordination cost rises.

A negative result that removes unnecessary architecture is a successful research outcome.

---

## 22. Recommended experimental sequence

Do not run the full system first and infer component value post hoc.

Phase E0: freeze exact source and acceptance contracts.  
Phase E1: component-level discriminators / cheap falsifiers.  
Phase E2: paired integration tests around neighboring components.  
Phase E3: causal interventions for GWT/J-Space and outcome re-entry.  
Phase E4: persistent target-runtime restart / kill / recovery.  
Phase E5: long-horizon tasks with controlled horizon length.  
Phase E6: adversarial persistent-memory contamination.  
Phase E7: full closed-loop ablation tournament against strong simpler baselines.  
Phase E8: soak/degradation/resource characterization.

Do not grant whole-system credit until E7/E8 evidence exists on the intended runtime surface.

---

## 23. Source quality / confidence notes

High relevance and relatively direct empirical evidence in this packet:

- Gurnee et al. J-Space/global-workspace experiments (primary research + released methodology; interpretability/GWT functional evidence, not consciousness proof).
- CAMA and CAGE-CAL for correlated multi-agent evidence/false consensus.
- ICML 2026 horizon-length study for long-horizon instability and horizon reduction.
- Proactive Memory Agent / MAGE / MMPO for active state/memory control.
- DreamGuard for trajectory-aware runtime risk.
- AgentGuardUtil paper for typed deterministic obligation verification.
- persistent-agent worm work for temporal re-entry integrity threat.

Medium relevance / architectural donor evidence:

- heartbeat-driven scheduler;
- DS-MCM metacognitive monitoring;
- LODGE / UI-Oceanus / scientific world-model papers.

These sources should generate tests, not be copied as authorities.

---

## 24. Final fused conclusion

The strongest research result is a **narrower and more falsifiable GRID10 thesis**:

GRID10 should not be defended as a bag of novel modules. Heartbeats, memory controllers, self-generated goals, workspace-like representations, metacognitive monitors, world models, runtime guardrails, deterministic verification and multi-agent coordination all have external analogues.

What remains unusual is the intended closed causal chain with strict boundaries:

```text
Persistent continuity
-> state reconstruction
-> bounded autonomous goal candidates
-> preserved alternatives
-> selective workspace competition/broadcast
-> measured semantic uptake / causal mediation
-> regulated action proposal
-> deterministic effect authority
-> observed external outcome
-> typed completion verification
-> provenance-bound prediction residual / outcome re-entry
-> next persistent cognitive state
```

The architecture is only scientifically interesting if the arrows are real.

Every arrow must therefore receive an explicit receipt, intervention test or ablation. If an arrow cannot be distinguished from correlation, logging, prompt injection or bookkeeping, it should not be credited as a cognitive mechanism.

The decisive test is not whether GRID10 can be built. The decisive test is whether the **complete causal closure** produces capabilities or robustness that survive comparison with much simpler persistent-agent loops.

Until then:

```text
GRID10 = UNFINISHED ARCHITECTURE HYPOTHESIS
NOT A VALIDATED WHOLE AGENT
NOT A WHOLE-SYSTEM RUNTIME PASS
```
