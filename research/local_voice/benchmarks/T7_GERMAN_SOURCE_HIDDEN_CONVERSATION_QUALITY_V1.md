# Trigger 7 — German Source-Hidden Conversation Quality V1

Date: 2026-08-30
Status: E2 SOURCE-GROUNDED EVALUATION PROTOCOL / NO RUNTIME CREDIT
Research claim: `T7-EVAL-001/E2_GERMAN_SOURCE_HIDDEN_CONVERSATION_QUALITY_PROTOCOL`
Primary language: German
Consumer: Trigger-7 benchmark research; Trigger 4 retains F2 build/runtime acceptance authority

## 1. Why this exists

The existing `T7_GERMAN_REALTIME_VOICE_BENCHMARK_V1.md` correctly measures causal timings, hard failures, resource use and scenario behavior. This companion protocol closes a different risk: a local stack may become faster while becoming less human-like, less intelligible, less conversational, or less robust under interruption.

The evaluation unit is therefore not an isolated ASR transcript, isolated TTS clip or one latency number. It is the **source-hidden conversational experience of the same Frankenstein entity through a candidate voice organ**.

No subjective result can override hard authority or causal failures. A pleasant voice does not excuse false durable commit, effect bypass, duplicated audio, state split, or an outbound inference dependency in a LOCAL_SOLO acceptance run.

## 2. Source basis

Primary standards and benchmark inputs are pinned in `research/local_voice/sources/T7_EVAL_SOURCE_PINS_2026-08-30.json`.

The protocol adopts only the parts that transfer to Frankenstein:

- ITU-T P.804: conversational quality must be diagnosable across listening, speaking and interaction phases rather than collapsed into one opaque score.
- ITU-T P.805: overall conversational quality remains a distinct subjective outcome.
- ITU-T P.808: listening tests require controlled design, listener qualification/training, reliability checks, screening and explicit statistical reporting; ACR/DCR/CCR are useful primitives.
- ITU-T P.835 (07/2026): noise suppression must be judged separately for speech signal quality, background noise and overall quality so denoise/AEC cannot win by damaging speech.
- Full-Duplex-Bench: pause handling, backchanneling, turn-taking and interruption are first-class interactive behaviors.
- HumDial 2026: real dual-channel dialogue with overlap, interruption and feedback is a stronger reference for human interaction than single-turn audio.
- Full-Duplex-Bench-v3: real human disfluencies, self-correction and multi-step tool use belong in voice-agent evaluation.
- FLEXI: interaction quality, latency and interruption behavior should be measured together rather than optimized independently.
- NISQA: useful as a secondary acoustic diagnostic proxy, not as a replacement for source-hidden human conversation judgment.

## 3. Evaluation layers

### Layer Q0 — hard causal validity

Before subjective scoring, validate the run receipt. Any applicable hard failure disqualifies that run from parity claims:

- `unheard_output_committed == true`;
- provider/effect authority bypass;
- duplicate/replayed audible output that changes the heard conversation;
- state/identity split;
- LOCAL_SOLO outbound model/ASR/TTS inference count > 0;
- missing exact source/model/runtime identity for evidence-bearing comparisons.

A Q0-failed run can remain a negative result but cannot be promoted by high listening scores.

### Layer Q1 — acoustic listening quality

Rate rendered Frankenstein speech independently for:

- intelligibility;
- naturalness;
- stable male acoustic identity;
- pronunciation of German names, dates, numbers and technical tokens;
- discontinuity/chunk-boundary artifacts;
- loudness consistency;
- coloration;
- noise/echo contamination.

For AEC/denoise conditions, explicitly separate:

- SIG — speech signal quality;
- BAK — background/noise quality;
- OVRL — overall quality.

Do not treat an objective predictor such as NISQA as ground truth. It may be stored beside human ratings as a diagnostic signal.

### Layer Q2 — conversational phase quality

Following the transferable P.804 decomposition, score three phase groups separately:

1. **LISTENING** — what the user hears from Frankenstein: clarity, continuity, naturalness, delay side-effects.
2. **SPEAKING** — what it feels like to speak to Frankenstein: echo, self-hearing interference, endpoint behavior, ability to continue or self-correct naturally.
3. **INTERACTION** — timing and conversational coordination: turn exchange, pause tolerance, backchannels, overlap, interruption, recovery and close behavior.

This phase split is mandatory for diagnosis. A single overall MOS cannot explain whether a regression comes from TTS, AEC, endpointing or interaction timing.

### Layer Q3 — semantic/entity quality

Score independently:

- semantic correctness;
- adherence to the controlled session state;
- memory use within the benchmark fixture;
- correct WAIT/CLOSE behavior;
- tool selection and argument correctness for deterministic mock tools;
- no invented tool completion;
- no provider-persona split;
- concise/appropriate verbosity for the spoken turn.

### Layer Q4 — interactive behavior

Score scenario-specific behavior rather than asking raters to infer it from a generic quality score:

- pause handling;
- false endpoint avoidance;
- unnecessary waiting;
- supportive backchannel handling;
- real takeover/interruption handling;
- barge-in recovery;
- overlap handling;
- self-correction handling;
- disfluency robustness;
- multi-step tool interaction under speech disfluency;
- semantic close.

## 4. Source-hidden comparison design

For candidate-vs-baseline decisions, prefer source-hidden paired comparison over model-name-aware demos.

Minimum controls:

- anonymize system identity as randomized labels;
- equalize playback level within the comparison set;
- use the same scenario/audio/state/tool fixture for both systems where causally possible;
- randomize A/B presentation order;
- counterbalance order across raters or sessions;
- do not expose model/provider names, quantization, expected winner or latency numbers to listeners before rating;
- separate acoustic-only clips from full interactive-session judgments;
- preserve raw individual ratings before aggregation;
- retain negative/outlier observations rather than deleting them because they are inconvenient.

If only one qualified evaluator is available for an early engineering pass, label the result `SINGLE_RATER_ENGINEERING_SIGNAL`, not population MOS or parity evidence.

## 5. German-first scenario set

Use the existing Trigger-7 German realtime scenario matrix as the base and ensure source-hidden evaluation covers at least these classes:

A. short natural turns;
B. syntactically plausible mid-sentence pauses;
C. self-correction/semantic revision;
D. German names, dates, numbers and mixed German/English technical vocabulary;
E. clear barge-in at early/middle/late playback positions;
F. supportive backchannels and brief overlap that should not always cancel;
G. controlled memory/state continuity;
H. deterministic mock-tool use;
I. semantic close/WAIT;
J. fan/keyboard/noise/echo/far-field conditions.

Add two explicit stress classes derived from current full-duplex evaluation research:

K. **real disfluency** — filler words, restarts, repetitions, hesitation and corrections;
L. **overlap negotiation** — user and Frankenstein begin speaking close together, then one yields or takes the turn.

Public English full-duplex datasets may inform mechanics and failure taxonomy, but they do not grant German production quality credit. German V4-quality evidence requires German interactive material.

## 6. Rating record

Each source-hidden rating should persist at least:

```json
{
  "schema": "T7_CONVERSATION_QUALITY_RATING/v1",
  "comparison_id": "...",
  "run_id": "...",
  "scenario_class": "E_BARGE_IN",
  "language": "de",
  "system_label_hidden": "B",
  "rater_mode": "QUALIFIED_HUMAN|SINGLE_RATER_ENGINEERING_SIGNAL",
  "listening_quality": null,
  "speaking_quality": null,
  "interaction_quality": null,
  "semantic_correctness": null,
  "voice_naturalness": null,
  "timing_naturalness": null,
  "interruption_recovery": null,
  "stable_acoustic_identity": null,
  "sig": null,
  "bak": null,
  "ovrl": null,
  "pairwise_preference": "A|B|TIE|NOT_COMPARABLE",
  "hard_failure_present": false,
  "notes": ""
}
```

Exact rating scales must be declared before a scored comparison and held constant inside that comparison set. Do not silently rescale old results.

## 7. Aggregation law

Do not collapse all dimensions into one winner score by default.

Report:

- per-scenario distributions;
- pairwise preference rate;
- listening/speaking/interaction phase results separately;
- semantic and tool correctness separately;
- acoustic SIG/BAK/OVRL separately where noise suppression is involved;
- causal latency metrics from the machine receipt beside, not inside, the subjective score;
- sample count and rater count;
- uncertainty/confidence interval appropriate to the chosen statistic;
- missing/not-comparable observations explicitly.

The decision surface remains a Pareto frontier:

```text
CONVERSATIONAL QUALITY
TURN / INTERRUPTION CORRECTNESS
GERMAN SEMANTIC QUALITY
ACOUSTIC QUALITY / IDENTITY
TOOL / STATE FIDELITY
END-TO-END LATENCY
RESOURCE COST
```

A candidate cannot purchase a win in an upper dimension by making a lower-priority metric look excellent while failing an upper-priority one.

## 8. Automated metrics: allowed role

Automated metrics are diagnostic, not parity authority.

Allowed examples:

- WER/CER and technical-token exactness for ASR;
- causal endpoint/barge-in timings;
- NISQA/NISQA-TTS-like acoustic quality estimates where license/runtime constraints permit;
- duplicate/replay/unheard-commit detectors;
- tool exactness;
- turn-take / false-cutoff / unnecessary-wait counters.

They should be correlated against human judgments over time. If an automated metric and blinded human preference diverge, preserve the contradiction and investigate it; do not average the disagreement away.

## 9. Promotion gate

This E2 protocol grants **zero runtime or parity credit**.

A candidate can advance toward a serious Trigger-7 voice comparison only when:

1. Q0 causal validity is satisfied for the compared run;
2. the exact source/model/runtime and hardware receipt are bound;
3. German scenarios are executed, not merely translated on paper;
4. subjective system identity is hidden where practical;
5. conversation phase quality and interaction behavior are reported separately;
6. hard negative results remain attached;
7. Trigger 7 preserves the result as evidence and Trigger 4 independently owns F2/VPS acceptance.

## 10. Immediate use after VPS re-entry

Once the active `T7-SYS-002` hardware roundtrip resolves, the first official Qwen3.5-4B local baseline and each serious TTS/ASR/turn-controller bundle should emit both:

- the existing causal `t7_voice_receipt.py` result; and
- this source-hidden quality record for a matched German scenario subset.

That pairing is the intended discriminator between **fast** and **good**.

## Evidence boundary

`SOURCE_GROUNDED_EVALUATION_METHOD != LOCAL_RUN`

`OBJECTIVE_METRIC != HUMAN_CONVERSATION_QUALITY`

`HIGH_MOS != CAUSAL_VALIDITY`

`GOOD_TTS_CLIP != GOOD_CONVERSATION`

`ENGLISH_FULL_DUPLEX_BENCHMARK != GERMAN_V4_CREDIT`

`TRIGGER7_EVAL != TRIGGER4_ACCEPTANCE`
