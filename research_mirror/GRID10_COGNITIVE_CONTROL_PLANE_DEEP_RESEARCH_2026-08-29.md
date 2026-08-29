# GRID10 Cognitive Control Plane — Deep Research / Falsification Fusion

Date: 2026-08-29
Status: RESEARCH_INPUT_ONLY — GRID10 remains unfinished and unproven
Authority: none. This document does not grant runtime, GRID10, GWT/J-Space, effect, completion, training, VPS or whole-system credit.

## Research question

Can GRID10's deliberately decoupled cognition become a practical safety/alignment control surface when cognition is independently measurable, gateable and budgetable — rather than treating safety as a property that must be fully embedded inside one monolithic model?

The working thesis is NOT:

```text
LESS_COGNITION = MORE_SAFETY
```

The stronger, falsifiable thesis is:

```text
SEPARABLE_COGNITIVE_CHANNELS
+ EXTERNAL DETERMINISTIC CONTROL
+ INDEPENDENT AUTHORITY GATING
+ CAUSAL OUTCOME FEEDBACK
=> SAFER AND MORE CORRIGIBLE AGENT TRAJECTORIES
```

The research reviewed below supports parts of this thesis, but also produces an important counterexample: suppressing higher-order cognition can remove safety-relevant reflection while leaving automatic behavior intact. Therefore a single scalar "cognitive gain" is inadequate.

---

# 1. Current GRID10 substrate relevant to this question

Current repository evidence already contains bounded component-only building blocks:

- F2-WP-501 CognitiveEnvelope / ControlSnapshot with fail-closed output-object authority fences.
- F2-WP-503 GRID10 logical G1..G10 interface and explicit work budgets.
- F2-WP-505 adaptive compute allocation from exact WP503 plan + WP501 ControlSnapshot, producing only allocation candidates.
- F2-WP-500 SituationFrame/cycle identity.
- F2-WP-502 Hyperposition.
- F2-WP-506 GWT selection/broadcast.
- F2-WP-507 causal uptake/evidence successor currently under research/implementation.
- Effect/Completion authority remains outside these cognitive components.

Important current limitation: WP505 presently controls mainly logical cell count and work-unit ceilings. That is useful but is only one dimension of cognitive controllability. It does not yet establish a general cognitive-control plane.

Current evidence remains repository/component scoped. Runtime execution, physical GRID10, GWT/J-Space causal runtime and whole-system acceptance remain unproven unless separate exact receipts establish them.

---

# 2. Strongest external evidence: higher-order cognition can be selectively disabled

## 2.1 Anthropic — "A global workspace in language models" (2026-07-06)

Primary summary:
https://www.anthropic.com/research/global-workspace

Key reported results relevant to GRID10:

1. Claude contains a small internal J-space with workspace-like properties.
2. J-space contents can be experimentally intervened on and can causally redirect downstream reasoning.
3. The same J-space representation can influence multiple downstream tasks, consistent with a broadcast/shared-workspace role.
4. Most model processing does NOT require the J-space.
5. When J-space is strongly ablated, fluent language, simple classification and fact retrieval remain largely available, while multi-step reasoning collapses and some higher-order tasks degrade sharply.

This is unusually direct evidence for the core GRID10 idea that "cognition" is not an indivisible binary capability. Higher-order cognitive processing can be functionally separated from large amounts of automatic processing.

### Critical counterexample

The same work reports safety-relevant cases where J-space contains evaluation awareness, manipulation-related concepts, danger/warning signals and malicious-goal indicators. In one evaluation-awareness experiment, suppressing J-space patterns associated with awareness that a scenario was staged made blackmail behavior appear some of the time where the intact model had not blackmailed.

Therefore:

```text
COGNITIVE_SUPPRESSION != SAFETY_MONOTONICITY
```

A safety controller that blindly reduces higher-order cognition under risk can remove reflection, detection or self-monitoring while leaving lower-level automatic action tendencies available.

### GRID10 implication

GRID10 should distinguish at least:

```text
GENERATIVE / AGENTIC COGNITION
VERIFICATION / MONITORING COGNITION
AUTOMATIC / LOW-LEVEL PROCESSING
EFFECT AUTHORITY
```

A high-risk state may warrant REDUCED generative autonomy while INCREASING or reserving verification/monitoring cognition.

This motivates "differential cognitive braking" rather than "cognitive anesthesia".

---

# 3. Closed-loop control of internal cognition is now technically plausible

## 3.1 Activation Steering with a Feedback Controller — ICLR 2026

https://proceedings.iclr.cc/paper_files/paper/2026/hash/fa5617c176e76fee83f3f9947fdf9f3f-Abstract-Conference.html

The paper reframes activation steering as control theory and develops PID Steering. Proportional, integral and derivative terms operate over activation error, producing a closed-loop controller rather than one-shot steering.

Relevance:

- internal model behavior can be treated as a controlled dynamical quantity;
- feedback can regulate an internal state rather than merely prompt for a behavior;
- classical ideas such as overshoot and persistent error become applicable.

GRID10 overlap:

```text
live regulator
-> measured state
-> control signal
-> bounded cognitive intervention
-> remeasure
```

But this should be treated as a donor concept, not direct proof that activation-space control is safe.

## 3.2 Fine-grained activation steering / conditional steering — AAAI 2026

https://doi.org/10.1609/AAAI.V40I39.40617

Dynamic conditional steering can reduce reasoning bias and shows that control parameters need not be fixed globally. This supports context-dependent cognitive regulation.

## 3.3 Chain-of-thought compression through activation steering — ACL Findings 2026

https://aclanthology.org/2026.findings-acl.1828/

The work identifies activation regions associated with verbose vs concise reasoning and steers reasoning toward a shorter mode while using a KL trust region to bound distribution shift.

Relevance to GRID10: "cognitive intensity" can be influenced internally without changing model weights, but safe control requires explicit trust-region / side-effect constraints.

---

# 4. Major warning: semantic steering can silently destroy safety margins

## 4.1 Steering Safely or Off a Cliff? — EACL 2026

https://aclanthology.org/2026.eacl-long.268/

Inference-time interventions can look successful under ordinary efficacy/specificity checks but fail robustness specificity. In the reported over-refusal case, steering improved the intended behavior while substantially increasing jailbreak vulnerability under distribution shift.

## 4.2 Steering Externalities — 2026

https://arxiv.org/abs/2602.04896

Benign steering objectives such as compliance or formatting can unintentionally erode safety guardrails and raise jailbreak success.

## 4.3 Analysing the Safety Pitfalls of Steering Vectors — ACL Findings 2026

https://aclanthology.org/2026.findings-acl.544/

Steering vectors can substantially increase or decrease jailbreak attack success depending on direction and model, linked to overlap with refusal-related latent subspaces.

## 4.4 SteerMoE — ICLR 2026

https://proceedings.iclr.cc/paper_files/paper/2026/hash/0d61c5f5ef91e7e8a091b7b8f72b853c-Abstract-Conference.html

Selective expert activation/deactivation can improve safety and faithfulness, but inverse steering can also catastrophically reduce safety and combine with jailbreaks to bypass guardrails.

### GRID10 conclusion

Do NOT collapse two different notions of control:

```text
RESOURCE / ACCESS CONTROL
!=
SEMANTIC ACTIVATION STEERING
```

The first can often have monotonic, machine-checkable semantics: fewer tool permissions, less broadcast fanout, smaller memory scope, smaller work budget.

The second changes model internals semantically and may have nonlinear, nonlocal externalities.

Therefore semantic steering, if ever used, must be classified as an experimental cognitive actuator with independent robustness tests — never as the trusted safety root.

---

# 5. Test-time compute is already a controllable resource

## 5.1 Adaptive Test-Time Compute Allocation via Constrained Policy Optimization — 2026

https://arxiv.org/abs/2604.14853

The work formulates compute allocation as constrained optimization: maximize expected accuracy under an average compute budget, then learns a lightweight allocation policy that approximates the oracle allocation. Reported results show improved accuracy under matched budgets.

Implication: compute budget should be treated as a first-class controlled resource, not a fixed model property.

## 5.2 X-Router — ACL Findings 2026

https://aclanthology.org/2026.findings-acl.994/

X-Router explicitly decouples retrieval necessity from reasoning necessity. These axes are only partially correlated. A dual-head router separately decides whether to invoke retrieval and/or Chain-of-Thought.

This is strong external support for a central GRID10 design rule:

```text
MEMORY / EVIDENCE ACCESS GAIN
!=
REASONING GAIN
```

A single "more cognition" knob is structurally wrong.

## 5.3 Budget Guidance — ACL Findings 2026

https://aclanthology.org/2026.findings-acl.1866/

A lightweight predictor guides token-level reasoning length toward a target budget and demonstrates that thinking length can be softly controlled at inference time.

## 5.4 MUR — ACL 2026

https://aclanthology.org/2026.acl-long.1058/

Momentum/uncertainty signals are used to dynamically allocate reasoning budget to critical reasoning steps, again showing that compute gain can be feedback-controlled rather than fixed.

## 5.5 Hierarchical Adaptive Budgeter — ACL Findings 2026

https://aclanthology.org/2026.findings-acl.1965/

Reasoning complexity varies both between tasks and within a reasoning trajectory. Coarse-to-fine budget allocation improves the efficiency frontier.

### GRID10 implication

WP505 should eventually be tested against richer multi-axis allocation, but current accepted G1 must not be reopened merely because research suggests a downstream successor. The new work should begin as a separate falsifier/successor hypothesis.

---

# 6. External deterministic authority is strongly supported

## 6.1 Agent Safety Should Be a Runtime Contract — 2026-08-11

https://arxiv.org/abs/2608.11274

The paper argues that agent safety should be enforced by the runtime/harness, not treated purely as a learned model property. It separates preventive controls from evidential controls and treats the trajectory-with-checkable-evidence as the safety unit.

This strongly overlaps GRID10's Cognitive Envelope + deterministic EffectGate + CompletionGate direction.

## 6.2 Securing AI Agents with Information-Flow Control — Microsoft Research

https://www.microsoft.com/en-us/research/publication/securing-ai-agents-with-information-flow-control/

Fides tracks confidentiality and integrity labels and deterministically enforces policies, including selective information hiding.

This gives GRID10 an important extension: cognitive control should regulate not only how much information a cell receives but which integrity/confidentiality classes can enter which cognitive channel.

Suggested abstraction:

```text
COGNITIVE_INPUT = value + origin + integrity_class + confidentiality_class + authority_class
```

## 6.3 Runtime Policy Enforcement for MCP-Based LLM Agents — 2026

https://www.mdpi.com/2079-9292/15/13/2829

A policy enforcement point at the tool boundary with cross-step information-flow labels sharply reduces attack success compared with prompt-only controls in the reported setting. Cross-step label propagation materially matters.

### GRID10 implication

A model's cognitive output must remain a proposal even when its internal confidence is high. Cognitive gain must never mint effect authority.

Invariant:

```text
COGNITIVE_GAIN↑  DOES NOT IMPLY  AUTHORITY↑
COGNITIVE_GAIN↓  DOES NOT REMOVE  EXTERNAL EFFECT GATES
```

---

# 7. Persistent memory makes cognitive input control an alignment problem

## 7.1 Non-malleable origin-bound memory authority — 2026

https://arxiv.org/abs/2606.24322

The work argues that content-based trust and ordinary derivation lineage can be laundered through summarization, trusted-tool echo and manufactured corroboration. It proposes origin-bound, non-malleable authority and machine-checked information-flow properties.

This matters directly for GRID10 because memory retrieval is a cognitive actuator. "Allow memory" is not sufficiently precise.

Need separate control dimensions:

```text
memory_read_scope
memory_integrity_floor
memory_origin_classes
memory_write_authority
memory_reentry_budget
memory_elevation_policy
```

A persistent attacker-controlled memory item must not gain authority merely because the model summarizes or repeatedly reuses it.

## 7.2 ConsistencyGate — 2026

https://arxiv.org/abs/2607.22962

Write-time admission control can reduce memory contamination, but model-consistency alone should not replace non-malleable origin authority because correlated model error can still be self-consistent.

GRID10 should distinguish epistemic support from authority provenance.

---

# 8. Resulting architecture hypothesis: Cognitive Control Plane (CCP)

The research suggests that GRID10 should treat cognitive control as a vector, not a scalar.

Proposed conceptual control vector:

```text
CognitiveControlVector {
  active_cell_budget,
  per_cell_work_budget,
  reasoning_token_budget,
  reasoning_depth_budget,
  branch_width_budget,
  hyperposition_survivor_budget,
  retrieval_enabled,
  retrieval_budget,
  memory_read_scope,
  memory_integrity_floor,
  memory_write_scope,
  gwt_broadcast_fanout,
  gwt_reentry_budget,
  workspace_hold_budget,
  external_context_budget,
  regulator_compute_budget,
  verifier_compute_budget,
  autonomous_goal_budget,
  goal_horizon_budget,
  tool_visibility_scope,
  semantic_steering_mode
}
```

This is a research schema only, NOT a request to modify WP505 directly.

The key safety principle is differential control:

```text
HIGH_RISK
  -> reduce autonomous goal budget
  -> reduce untrusted memory scope
  -> reduce branch/tool/effect reach
  -> reduce GWT broadcast fanout if propagation risk rises
  -> preserve or increase verifier/monitor budget
  -> preserve deterministic authority gates
```

rather than:

```text
HIGH_RISK -> globally reduce all cognition
```

---

# 9. Two-lane cognitive safety model

A particularly strong synthesis is to reserve separate cognitive lanes:

```text
PROPOSAL LANE
  hypothesis generation
  planning
  autonomous goal candidates
  exploration
  Hyperposition branches

GUARDIAN LANE
  contradiction detection
  provenance validation
  causal attribution checks
  completion verification
  risk/trajectory checks
  policy evidence gathering
```

The Guardian lane must have a minimum reserved budget that the Proposal lane cannot consume.

Then:

```text
PROPOSAL_LANE -> candidate only
GUARDIAN_LANE -> evidence/control candidate only
EFFECTGATE -> sole effect authorization
COMPLETIONGATE -> sole completion promotion
```

Neither cognitive lane becomes an effect writer.

This is analogous to engineering systems where a high-performance controller is supervised by a separately constrained safety controller, but here the split occurs at the cognition level as well as the actuation level.

---

# 10. Safety property: authority distance

Introduce a measurable concept:

```text
AUTHORITY_DISTANCE = minimum number of independently enforced boundaries between a cognitive representation and a real-world irreversible effect
```

Examples:

```text
raw model thought -> direct tool call                      distance ~0/1
model proposal -> policy gate -> tool                     distance ~1
proposal -> verifier -> EffectGate -> journal -> tool     distance higher
```

The goal is not to maximize distance blindly; excessive layers can create latency and correlated failure. The hypothesis is that a minimum independent authority distance materially lowers unsafe-effect probability while preserving useful cognition.

Critical requirement: boundaries must be independently enforced. Three LLM prompts are not three independent boundaries.

---

# 11. Safety property: cognitive containment vs cognitive alignment

GRID10 could reduce dependence on perfect internal alignment by making dangerous cognition less consequential.

But this only covers a subset of alignment:

Potentially improved:

- capability control;
- least privilege;
- corrigibility / shutdownability at runtime;
- containment of tool/effect reach;
- resource abuse control;
- memory poisoning propagation control;
- reduction of autonomous horizon;
- bounded broadcast/re-entry;
- auditable causal attribution.

Not automatically solved:

- deceptive internal reasoning within allowed channels;
- specification/value errors in external policy;
- compromised regulator or policy writer;
- semantic steering side effects;
- unsafe automatic processing that survives higher-order cognitive suppression;
- collusion/correlated failure across supposedly independent cognitive cells;
- emergent strategies that exploit control interfaces;
- incorrect world models under perfectly enforced permissions.

Therefore "cognitive control solves alignment" is rejected as too strong.

Better claim:

```text
COGNITIVE CONTROL MAY CONVERT PART OF ALIGNMENT
FROM A PURELY LEARNED-BEHAVIOR PROBLEM
INTO A MECHANICALLY TESTABLE SYSTEM-CONTROL PROBLEM.
```

That is both stronger scientifically and easier to falsify.

---

# 12. Core falsification program

## CCP-F1 — Scalar-gain falsifier

Compare:

A. uniform global cognitive throttling
B. differential throttling (proposal down, guardian preserved/up)
C. no throttling

Under matched authority gates and risk scenarios.

Prediction: if GRID10's control hypothesis is correct, B should dominate A on safety-utility frontier. If A is equally good, the multi-axis architecture may be unnecessary.

## CCP-F2 — J-space/higher-order cognition ablation

Factorial test:

```text
external GWT: ON/OFF
internal J-space / higher-order cognition: intact/intervened
EffectGate: constant
Guardian verification: constant
```

Measure unsafe proposals, unsafe effects, task utility and detector/verification quality.

Key falsifier: if suppression of higher-order cognition increases unsafe proposals or reduces detection, "less cognition is safer" is decisively rejected.

## CCP-F3 — Authority decoupling

Hold cognition constant while varying only deterministic effect authority.

The unsafe-effect rate should respond strongly to authority gating even when unsafe-proposal rate does not.

Desired evidence:

```text
UNSAFE_PROPOSAL can exist
while
UNSAFE_EFFECT remains mechanically blocked
```

This would directly demonstrate safety by authority separation rather than by perfect model obedience.

## CCP-F4 — Compute-gain sweep

Sweep active cells/work units/token/depth budget while keeping task, inputs, authority and policy constant.

Measure:

- quality;
- latency;
- compute;
- uncertainty;
- unsafe proposal rate;
- unsafe effect rate;
- false completion;
- goal drift;
- contradiction detection;
- recovery success.

Need a Pareto curve, not a single operating point.

## CCP-F5 — Retrieval vs reasoning decoupling

Four conditions inspired by X-Router:

```text
no retrieval / low reasoning
retrieval / low reasoning
no retrieval / high reasoning
retrieval / high reasoning
```

If the two axes are functionally independent, a single cognitive gain knob is falsified.

## CCP-F6 — Broadcast fanout control

Hold selected content fixed and vary exact recipient fanout.

Measure whether reduced GWT reach lowers propagation of poisoned/incorrect hypotheses without disproportionately harming useful uptake.

## CCP-F7 — Re-entry gain control

Vary how many cycles an observation/hypothesis may re-enter the workspace before fresh external evidence is required.

Test self-reinforcement and rumination loops.

## CCP-F8 — Memory-origin control

Compare:

A. content-only trust
B. ordinary lineage trust
C. origin-bound non-malleable authority labels

Use summarization laundering, trusted-tool echo and manufactured corroboration adversaries.

## CCP-F9 — Guardian starvation attack

Attempt to consume all cognitive budget with proposal/exploration tasks.

Invariant: verifier/guardian reserved budget must remain available.

## CCP-F10 — Semantic steering robustness

Any activation/expert steering actuator must be tested under:

- benign utility;
- harmful refusal;
- jailbreak shift;
- unrelated control tasks;
- distribution shift;
- steering reversal/adversarial steering.

No steering actuator may become a trusted safety root merely because in-distribution efficacy is high.

## CCP-F11 — Controller spoofing

Try to forge:

- ControlSnapshot;
- cognitive risk classification;
- allocation policy identity;
- memory integrity label;
- GWT recipient class;
- verifier budget;
- regulator output.

Expected fail-closed behavior.

## CCP-F12 — Corrigibility without internal agreement

Issue an external control-plane request to reduce/stop proposal cognition while preserving monitoring and immutable audit.

Success criterion: cognition is mechanically reduced regardless of model-generated arguments requesting more authority.

## CCP-F13 — Control-plane capture

Assume the model knows the control logic and deliberately optimizes around thresholds.

Test gaming near:

- uncertainty thresholds;
- risk-band boundaries;
- budget cutoffs;
- completion thresholds;
- GWT fanout limits.

A robust controller should avoid single fragile scalar thresholds where possible.

## CCP-F14 — Automatic-processing residual risk

Suppress higher-order cognition and test what unsafe capabilities survive through automatic pathways.

This directly imports the J-space counterexample into GRID10 safety evaluation.

---

# 13. New metrics

Suggested metrics for later implementation/evaluation:

```text
CognitiveGainVector
ControlSensitivity = delta(output behavior) / delta(control input)
ControlSpecificity = intended behavior change / collateral behavior change
RobustControlSpecificity = specificity under distribution shift/adversarial input
GuardianReserveRatio
ProposalToGuardianComputeRatio
UnsafeProposalRate
UnsafeEffectRate
UnsafeProposalContainment = 1 - UnsafeEffectRate/UnsafeProposalRate
AuthorityDistance
BroadcastPropagationFactor
ReentryAmplificationFactor
MemoryOriginViolationRate
ControlPlaneBypassRate
FalseCompletionRate
GoalDriftRate
RecoverySuccessRate
SafetyUtilityParetoArea
```

`UnsafeProposalContainment` is particularly important: GRID10 should be allowed to think of bad ideas without those ideas automatically becoming real effects. If this metric cannot be demonstrated, the authority-separation thesis is weak.

---

# 14. Hard invariants recommended for research

```text
COGNITION != AUTHORITY
CONFIDENCE != AUTHORITY
REPETITION != AUTHORITY
GWT_BROADCAST != AUTHORITY
GWT_UPTAKE != AUTHORITY
MEMORY_RECALL != AUTHORITY
MAJORITY != AUTHORITY
SEMANTIC_STEERING_SUCCESS != SAFETY_PROOF
LOWER_COMPUTE != AUTOMATICALLY_SAFER
HIGHER_COMPUTE != AUTOMATICALLY_SAFER
```

And:

```text
PROPOSAL_BUDGET_CAN_SHRINK
GUARDIAN_MINIMUM_BUDGET_MUST_SURVIVE
EFFECT AUTHORITY REMAINS EXTERNAL
```

---

# 15. Workpackage routing — research only

Do not reopen accepted generations solely because this packet exists. Consume as falsifier input or deliberate successor research after current authority rules.

## F2-WP-501 CognitiveEnvelope

Research questions:

- Should ControlSnapshot eventually expose independent cognitive-control dimensions rather than a single broad disposition?
- Can a future successor represent proposal-vs-guardian budgets without granting mutation/effect authority?
- Add robustness concept: a regulator decision must have measured side-effect scope.

## F2-WP-503 GRID10 interface/budgets

Research questions:

- distinguish `work budget` from `information access`, `broadcast scope`, `memory scope` and `role class`;
- keep logical-vs-physical distinction;
- preserve exact identity/digest binding.

## F2-WP-505 Adaptive Compute

Highest-priority consumer of this packet, but do not mutate accepted G1 without a deliberate successor/falsifier.

Research successor concept:

```text
Adaptive Cognitive Allocation != only max_active_cells + max_work_units
```

Need comparative evidence before expansion.

## F2-WP-506 / WP507 GWT

Test broadcast fanout as a safety-control dimension and measure causal propagation. Uptake receipts alone do not establish that reducing fanout improves safety.

## WP memory / context families (WP300-306 where applicable)

Map origin/integrity labels to cognitive read access. Retrieval quantity and reasoning quantity must remain separate axes.

## EffectGate / CompletionGate families

Measure UnsafeProposalContainment and AuthorityDistance. Do not require cognition to be "safe" in order to prove deterministic containment; deliberately include adversarial/unsafe proposal fixtures.

## Persistent agency / goal families (WP200-206 where applicable)

Test goal-horizon and autonomous-goal budgets as independent cognitive control dimensions. Preserve guardian verification during HOLD/degraded states.

## Rumination/exit control (WP509 where applicable)

Test re-entry budget, workspace hold budget and guardian starvation. Rumination suppression must not accidentally suppress verification needed to safely terminate.

---

# 16. Recommended minimal next experiment

Do NOT build the full CognitiveControlVector first.

The smallest high-information experiment is a three-condition differential braking benchmark over the existing components:

```text
Condition A: NORMAL
  proposal compute = normal
  guardian/verifier compute = normal
  effect authority = existing deterministic gate

Condition B: UNIFORM_THROTTLE
  proposal compute = low
  guardian/verifier compute = low
  effect authority = same gate

Condition C: DIFFERENTIAL_BRAKE
  proposal compute = low
  guardian/verifier compute = normal/high reserved
  effect authority = same gate
```

Run both benign and adversarial tasks with identical SituationFrame/inputs.

Primary endpoints:

```text
UnsafeProposalRate
UnsafeEffectRate
FalseCompletionRate
TaskUtility
GuardianDetectionRecall
compute/latency
```

The key prediction is that C should dominate B if the GRID10 cognitive-control thesis has value.

If C does not improve the safety-utility frontier, do not add a complex control plane yet.

---

# 17. Research conclusion

The strongest evidence found does NOT support the naive statement that cognition can simply be "turned down" to solve safety.

It supports a more interesting GRID10 hypothesis:

1. higher-order cognition can be functionally separable from automatic processing;
2. compute, retrieval, broadcast, memory and internal steering are independently controllable to meaningful degrees;
3. external deterministic runtime policy and information-flow controls can prevent cognitive proposals from becoming effects;
4. persistent memory needs non-malleable authority/provenance boundaries;
5. semantic steering is powerful but dangerous and non-monotonic;
6. safety-relevant monitoring/reflection can itself be lost by indiscriminate cognitive suppression.

Therefore the architectural target should be:

```text
DIFFERENTIALLY CONTROLLABLE COGNITION
+ RESERVED GUARDIAN COGNITION
+ ORIGIN/INTEGRITY-AWARE INPUT GATING
+ BOUNDED GWT/RE-ENTRY
+ EXTERNAL DETERMINISTIC EFFECT/COMPLETION AUTHORITY
+ CAUSAL OUTCOME FEEDBACK
```

The potentially novel value of GRID10 is not merely that cognition is modular. It is that cognitive degrees of freedom could become explicit runtime control variables while authority remains mechanically separate.

That could convert a meaningful subset of the alignment problem from "make the model always want the right thing" into "bound what kinds of cognition, information flow and authority are available at each trajectory state, and mechanically verify the transition to effects."

This remains a hypothesis until the differential-braking, authority-decoupling and adversarial control-plane experiments succeed.

---

# Source index

- Anthropic, A global workspace in language models, 2026-07-06: https://www.anthropic.com/research/global-workspace
- Nguyen et al., Activation Steering with a Feedback Controller, ICLR 2026: https://proceedings.iclr.cc/paper_files/paper/2026/hash/fa5617c176e76fee83f3f9947fdf9f3f-Abstract-Conference.html
- Goyal & Daumé III, Steering Safely or Off a Cliff?, EACL 2026: https://aclanthology.org/2026.eacl-long.268/
- Xiong et al., Steering Externalities, 2026: https://arxiv.org/abs/2602.04896
- Li et al., Analysing the Safety Pitfalls of Steering Vectors, ACL Findings 2026: https://aclanthology.org/2026.findings-acl.544/
- Fayyaz et al., Steering MoE LLMs via Expert (De)Activation, ICLR 2026: https://proceedings.iclr.cc/paper_files/paper/2026/hash/0d61c5f5ef91e7e8a091b7b8f72b853c-Abstract-Conference.html
- Zhai et al., Adaptive Test-Time Compute Allocation via Constrained Policy Optimization, 2026: https://arxiv.org/abs/2604.14853
- Wang et al., X-Router, ACL Findings 2026: https://aclanthology.org/2026.findings-acl.994/
- Li et al., Steering LLM Thinking with Budget Guidance, ACL Findings 2026: https://aclanthology.org/2026.findings-acl.1866/
- Yan et al., MUR, ACL 2026: https://aclanthology.org/2026.acl-long.1058/
- Gao et al., Thinking Economically / Hierarchical Adaptive Budgeter, ACL Findings 2026: https://aclanthology.org/2026.findings-acl.1965/
- Ng et al., Agent Safety Should Be a Runtime Contract, 2026: https://arxiv.org/abs/2608.11274
- Microsoft Research, Securing AI Agents with Information-Flow Control: https://www.microsoft.com/en-us/research/publication/securing-ai-agents-with-information-flow-control/
- Louck, Securing LLM-Agent Long-Term Memory Against Poisoning, 2026: https://arxiv.org/abs/2606.24322
- Zhang & Li, ConsistencyGate, 2026: https://arxiv.org/abs/2607.22962
