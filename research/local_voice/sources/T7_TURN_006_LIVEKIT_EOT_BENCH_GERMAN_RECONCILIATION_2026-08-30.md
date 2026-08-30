# T7-TURN-006 — LiveKit eot-bench German reconciliation

Date: 2026-08-30
Trigger: 7
Evidence scope: UPSTREAM_REPRODUCIBLE_BENCHMARK / SOURCE-LEVEL ONLY
F2 runtime credit: 0
Trigger-4 acceptance credit: 0

## Question

Does a current causal German end-of-turn benchmark materially change the Trigger-7 semantic endpointing frontier, especially the provisional SmartTurn v3.2 candidate?

## Sources pinned

- `livekit/eot-bench` observed main: `6594d8b3b8af385b15f116dde310ce45af92d646` (2026-08-28).
- German report blob: `c816bcaad9738b1046ca8ff43073993824992a89`.
- LiveKit Turn Detector v1-mini German manifest blob: `6b4372a67e64e736c8be8c7f3c3eb7c2f1a4bad9`.
- SmartTurn v3.2 German manifest blob: `a8b5d85c13f69390bb3c8ae9d6cf545649d87805`.
- Dataset: `livekit/eot-bench-data`, validation split, language `de`, minimum silence span 100 ms.
- Upstream benchmark repository/dataset license declaration: Apache-2.0. Model licenses remain separate and must be checked independently before packaging.

## Why this source is unusually relevant to Frankenstein

The benchmark evaluates the actual causal decision Trigger 7 cares about: at each silence in a complete human turn, respond or keep listening. It contains real human-to-agent conversations, aligned audio/text context, every silence pause >=100 ms, and German as one of 14 languages. Mid-turn pauses are `hold`; the final pause is `eot`. The policy sweep jointly varies confidence threshold, action delay and timeout, so low false-cutoff and low dead-air latency cannot be conflated into one accuracy number.

This is a materially better external discriminator for the Frankenstein endpoint controller than generic EOT accuracy or an English-only source result.

## Exact German upstream operating points

All numbers below are upstream `livekit/eot-bench` results at the pinned head, not Frankenstein measurements.

| Model | false cutoffs @ 300 ms | false cutoffs @ 600 ms | mean latency @ <=5% cutoff | mean latency @ <=10% cutoff |
|---|---:|---:|---:|---:|
| LiveKit Turn Detector v1 | 11.8% | 5.7% | 672 ms | 350 ms |
| LiveKit Turn Detector v1-mini | 24.8% | 10.7% | 947 ms | 618 ms |
| SmartTurn v3.2 | 35.5% | 14.2% | 963 ms | 706 ms |
| VAD baseline | 53.6% | 21.5% | 1100 ms | 800 ms |

German v1-mini run manifest:

- adapter id: `livekit/turn-detector-v1-mini-livekit-local-inference-0.2.5`
- `n_rows=8956`
- `n_spans=1107`
- inference interval 100 ms
- transcript lag 500 ms
- max audio 1.2 s

German SmartTurn run manifest:

- adapter id: `pipecat-ai/smart-turn-v3-smart-turn-v3.2-gpu`
- `n_rows=8956`
- `n_spans=1107`
- inference interval 100 ms
- transcript lag 500 ms

## Reconciliation with the existing Trigger-7 SmartTurn finding

The earlier SmartTurn v3.2 source pin remains valid as a runnable semantic EOT candidate. This new evidence changes its rank.

On the same German causal span set, LiveKit v1-mini beats SmartTurn v3.2 at every reported operating point:

- at ~300 ms latency: 24.8% vs 35.5% false cutoffs, an absolute improvement of 10.7 percentage points;
- at ~600 ms latency: 10.7% vs 14.2%, improvement 3.5 points;
- at <=5% false-cutoff: 947 ms vs 963 ms mean latency, 16 ms lower;
- at <=10% false-cutoff: 618 ms vs 706 ms, 88 ms lower.

The full LiveKit v1 is much stronger again, but this result does NOT make it a LOCAL-SOLO production candidate: exact local artifact availability, model license, packaging constraints and runtime fit must be separately established. The immediate local challenger is v1-mini, not the hosted/full model.

## Hypothesis update

Previous working hypothesis:

> SmartTurn v3.2 is a strong German semantic-EOT candidate worth benchmarking against the Frankenstein endpoint controller.

Updated hypothesis:

> SmartTurn v3.2 remains useful, but it is no longer the default learned EOT candidate. A three-way causal German benchmark should compare (1) the current Frankenstein deterministic/semantic endpoint controller, (2) SmartTurn v3.2, and (3) LiveKit Turn Detector v1-mini on the same eot-bench German spans plus Frankenstein room audio. The final controller may be a policy/fusion layer rather than a single detector.

Counterhypothesis retained:

> eot-bench is task-oriented human-to-agent data and may not predict long, informal Frankenstein room conversation, barge-in, dialect, echo or backchannel behavior. Upstream ranking therefore cannot replace real room-audio testing.

## Architecture consequence

Do not replace the existing deterministic cancellation/commit FSM with a model. Treat learned EOT scores as candidate signals into the same authoritative turn controller. This preserves:

- true barge-in/cancellation;
- unheard-output commit safety;
- VoiceIntent/GWT/WAIT semantics;
- provider independence;
- LOCAL-SOLO fallback;
- causal receiptability.

A useful deployment shape is therefore:

`VAD/acoustic state + learned EOT score + transcript/semantic state + explicit timeout -> deterministic turn policy -> cancellable generation/playback`.

## Next exact discriminator

1. Pin/import the German `eot-bench-data` validation split and its span-set manifest into the Trigger-7 quarantine/evidence workflow without copying upstream scores as F2 results.
2. Run the current Frankenstein endpoint controller over the same 1,107 German pause decisions.
3. Run the already pinned SmartTurn v3.2 artifact and a separately pinned v1-mini local artifact under one receipt schema.
4. Compare Pareto frontiers at explicit false-cutoff budgets, not raw accuracy.
5. Add real Frankenstein room audio as the second corpus before promotion to Trigger 4.

Acceptance consequence: NONE YET. This is an E2 source-level frontier correction and benchmark-corpus promotion only.
