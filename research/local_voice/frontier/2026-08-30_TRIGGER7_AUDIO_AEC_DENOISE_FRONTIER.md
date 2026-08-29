# Trigger 7 — Local AEC / denoise / duplex audio frontier

Date: 2026-08-30
Research ID: `T7-AUDIO-001`
Status: E2 SOURCE FRONTIER; NO TARGET RUNTIME CREDIT

## Evidence boundary

This result is source-grounded architecture research only. It does not establish a working `clay-direct-dev` audio graph, German end-to-end voice quality, V4, Trigger-4 acceptance, or whole-system runtime credit.

## Primary finding

The realtime audio path must keep **acoustic echo cancellation (AEC)** distinct from **noise suppression**.

The first production falsifier should therefore be:

```text
actual Frankenstein playback/render reference
  + raw microphone capture
        -> AEC
        -> optional single denoise stage
        -> VAD / EOT / endpoint intelligence
        -> streaming ASR
```

PipeWire's WebRTC-backed echo-cancel module is the lowest-integration Linux baseline. An embedded WebRTC AudioProcessing/AEC3 path is the product-owned challenger when tighter frame identity, timing and deterministic graph ownership are worth the additional integration cost.

RNNoise and DeepFilterNet remain denoise challengers. They are not substitutes for AEC.

## Causal ownership requirement

Frankenstein already treats actual playback rather than generated text as the spoken causal frontier. The audio-conditioning layer must preserve that rule.

Keep at least these logical streams separately identifiable:

1. **render reference** — the PCM actually routed toward the output device, as close to the final hardware-bound stream as the host stack permits;
2. **raw capture** — microphone input before AEC, retained only where policy/budget permits for diagnosis and benchmark evidence;
3. **AEC capture** — microphone signal after echo removal;
4. **clean capture** — optional post-AEC denoised signal consumed by VAD/turn-taking/ASR.

AEC residual state is not spoken output. Generated TTS audio is not spoken output until the playback frontier records it as actually played.

## Candidate topology A — host-native PipeWire baseline

Use PipeWire `libpipewire-module-echo-cancel` with the WebRTC SPA AEC backend as the first low-integration target falsifier.

Advantages to test:
- native Linux graph integration;
- explicit sink/playback and source/capture topology;
- no second standalone model process required for echo cancellation;
- easy comparison with and without optional denoise.

Open risks:
- exact target PipeWire/WebRTC package version is not yet measured;
- host graph latency and buffering may dominate component latency;
- the render reference must correspond to what the user can actually hear, not merely pre-render TTS buffers;
- device resampling, volume, Bluetooth or external mixer paths can break reference fidelity.

## Candidate topology B — embedded WebRTC APM/AEC3

Embed an auditable WebRTC AudioProcessing/AEC3-compatible layer inside the Frankenstein-owned audio process.

Potential advantages:
- direct ownership of render/capture frame IDs and monotonic timestamps;
- explicit generation/session binding;
- easier causal receipt integration;
- configuration can be fingerprinted with the same run receipt.

Costs/risks:
- more product integration and packaging work;
- target build/runtime dependencies must be pinned;
- incorrect delay estimation or device mapping can make an embedded implementation worse than the host-native path.

This candidate should not displace PipeWire merely because it provides more control. It must win a target benchmark.

## Optional denoise stage

Benchmark exactly one nonlinear denoise stage at a time after the AEC baseline unless target evidence justifies another order.

Challengers:
- WebRTC AudioProcessing noise suppression when available in the same graph;
- RNNoise as the light 48-kHz baseline;
- DeepFilterNet as a heavier speech-enhancement challenger.

Default research hypothesis:

```text
AEC before nonlinear denoise
```

Reason: AEC depends on render/capture correlation and delay structure. This remains a hypothesis until the same target/audio corpus demonstrates the ordering effect.

## Barge-in invariant

During Frankenstein speech plus near-end user interruption:

```text
user speech detected
  -> playback stop requested
  -> actual playback stop observed
  -> generation/TTS branch cancelled
  -> unheard output cannot be durably committed as spoken
```

AEC must continue to receive a truthful render reference through the transition and must not turn residual echo into a false user turn.

## Receipt gap discovered

Current `t7_voice_receipt.py` measures end-to-end timing, TTFT/TTFA, barge-in stop, cancellation and duplicate/replay conditions, but schema v1 does not identify the AEC/denoise stages or bind raw/render/clean frame lineage.

A later schema-compatible extension should record, where available:

- `aec_engine`, exact version/build and config digest;
- `denoiser_engine`, exact version/build and config digest;
- render-reference frame/sample range;
- raw-capture frame/sample range;
- AEC-output frame/sample range;
- denoise-output frame/sample range;
- monotonic timestamps and discontinuity/xrun counters;
- stream sample rate/channel layout/resampler identity;
- measured AEC/denoise processing latency;
- echo leakage/residual metric or source-hidden transcript leakage metric.

Do not mutate the accepted receipt schema solely from this source result; validate the extension against target logs first.

## Predeclared target falsifiers

1. Silence/no playback + German speech: baseline ASR/VAD quality.
2. Frankenstein playback only: false VAD/EOT/ASR self-trigger rate.
3. Near-end German speech while Frankenstein speaks: double-talk barge-in success and false-cutoff rate.
4. Same utterances with AEC off/on: WER/CER and self-transcription leakage delta.
5. Speaker volume and distance sweep: residual echo sensitivity.
6. Keyboard/fan/background-noise sweep: compare no denoise vs one denoise stage.
7. PipeWire WebRTC AEC vs embedded APM/AEC3 under the same audio corpus, buffer size and device path.
8. Measure added p50/p95/p99 audio processing latency, CPU, RSS and xruns; component speed alone is insufficient.
9. Verify playback cancellation leaves no unheard durable VoiceOutcome.
10. Network blocked in LOCAL-SOLO; audio processing must have no model/API dependency.

## Decision

No production winner is selected at E2.

Current order of attack after the already-claimed hardware re-entry finishes:

```text
measure target audio/PipeWire/device graph
-> run PipeWire WebRTC AEC baseline
-> bind actual render/capture lineage into receipts
-> run German playback-only + double-talk corpus
-> add one denoise challenger at a time
-> compare embedded APM/AEC3 only if host-native AEC is inadequate or causal ownership cannot be made exact
```

This lane becomes Trigger-4 material only after real target evidence demonstrates a bundle worth integration.
