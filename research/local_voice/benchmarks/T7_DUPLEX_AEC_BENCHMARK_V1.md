# Trigger 7 — German duplex AEC benchmark v1

Status: PREDECLARED / NOT YET EXECUTED
Research ID: `T7-AUDIO-001`
Language: German first
Acceptance ownership: Trigger 4 only

## Purpose

Measure whether the local audio-conditioning path prevents Frankenstein's own playback from becoming false user speech while preserving real near-end German speech, barge-in timing and ASR quality.

This benchmark compares audio graphs, not model README claims.

## Required source/runtime identity

Every executed run must bind:

- exact F2 source SHA;
- target/sandbox identity;
- audio server and version;
- AEC engine/version/build/config digest;
- denoiser engine/version/build/config digest or `NONE`;
- capture/render device identities and sample format;
- resampler identity if present;
- ASR model/runtime identity;
- corpus digest;
- monotonic run/turn IDs;
- outbound model/ASR/TTS counters for LOCAL-SOLO evidence.

## Conditions

At minimum execute the same pinned corpus under:

- `C0_RAW`: no AEC, no added denoise;
- `C1_AEC`: PipeWire/WebRTC AEC baseline, no added denoise;
- `C2_AEC_NS`: same AEC plus exactly one declared denoise stage;
- `C3_EMBEDDED_AEC`: embedded APM/AEC3 challenger only if implemented and source-bound.

Do not compare different microphones, speaker volumes, buffers or ASR models as if the difference were caused by AEC.

## Scenarios

### S0 — near-end only

Frankenstein silent. User reads German benchmark utterances.

Measure baseline WER/CER, VAD/EOT behavior and processing latency. AEC/NS must not materially damage clean speech without an offsetting benefit.

### S1 — playback only

Frankenstein plays pinned German speech; user is silent.

Measure:
- false VAD activation;
- false EOT/user-turn creation;
- own-output ASR leakage;
- false barge-in/cancellation;
- residual echo proxy.

### S2 — double talk / barge-in

User begins German speech while Frankenstein is speaking.

Include immediate interruption, mid-word overlap, short backchannel, longer corrective interruption and hesitation before interruption.

Measure:
- true interruption detection rate;
- false cutoff rate;
- barge-in detect -> actual playback stop p50/p95/p99;
- generation cancellation correctness;
- unheard-output durable-commit violations;
- post-stop ASR recovery.

### S3 — room/noise stress

Repeat selected S0-S2 samples with fan/keyboard noise, varied speaker volume and at least two microphone distances available on target.

Measure degradation rather than declaring one absolute room score portable across hardware.

## Core metrics

- German WER/CER by scenario;
- own-playback transcript leakage rate;
- false user-turn rate during S1;
- true/false barge-in rates during S2;
- `barge_in_to_stop_ms` p50/p95/p99;
- added audio-conditioning latency p50/p95/p99;
- CPU utilization and RSS/PSS;
- xruns/discontinuities/dropped audio chunks;
- duplicate/replayed audio;
- unheard-output commit violations;
- stream/frame lineage completeness.

## Causal frame lineage

Where the runtime exposes it, retain identifiers/ranges for:

```text
render_ref -> raw_capture -> aec_capture -> optional_ns_capture -> VAD/EOT/ASR
```

A run with unknown render-reference provenance may still be useful diagnostic evidence but cannot establish exact duplex causal closure.

## Decision rule

Keep a Pareto frontier. Do not collapse German quality, false self-trigger rate, barge-in correctness, tail latency and compute into one opaque score.

Minimum promotion logic for an E3/V4 candidate:

1. executable target evidence exists;
2. exact source/runtime/audio-graph identity exists;
3. S1 self-playback leakage is materially lower than C0;
4. S2 real user interruption remains reliable;
5. no unheard-output durable-commit violation is observed in the admitted corpus;
6. p95/p99 and resource cost fit the whole-resident Frankenstein budget;
7. LOCAL-SOLO has zero outbound model/ASR/TTS inference calls;
8. result is routed to Trigger 4 rather than self-awarded acceptance.

No fixed numerical threshold is invented before the target baseline and real room corpus are measured.
