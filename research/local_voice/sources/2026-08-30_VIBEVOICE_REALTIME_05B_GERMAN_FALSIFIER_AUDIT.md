# Trigger 7 — VibeVoice-Realtime-0.5B German falsifier source audit

Date: 2026-08-30
Trigger: 7
Research ID: T7-TTS-002
Objective: E2_VIBEVOICE_REALTIME_05B_GERMAN_FALSIFIER_SOURCE_AUDIT
Evidence class: PRIMARY_SOURCE_AUDIT_ONLY
Runtime credit: 0
German E2E credit: 0
Trigger-4/V6 acceptance credit: 0

## Decision

`microsoft/VibeVoice-Realtime-0.5B` is admitted to the Trigger-7 research frontier as a **compact streaming-TTS German falsifier**, not as a production winner.

Why it is worth testing:

- small 0.5B realtime model class;
- streaming text input;
- upstream reports approximately 300 ms first audible speech, explicitly hardware dependent;
- robust long-form generation is advertised around 10 minutes;
- MIT license is declared on the official Hugging Face release;
- Microsoft added an experimental German speaker option.

Why it receives no German production credit from source evidence:

- the official model card says the realtime release is primarily/intended for English;
- non-English output is explicitly described as experimental/unsupported and potentially unpredictable;
- current model is single-speaker and does not explicitly model overlapping conversational speech;
- upstream latency is not a Frankenstein target-runtime measurement;
- no F2 German stable-male-identity, ExpressionVector, cancellation, chunk-continuity or long-session benchmark has been observed.

## Immutable upstream pin

Model repository:

`microsoft/VibeVoice-Realtime-0.5B`

Observed current Hugging Face revision:

`6bce5f06044837fe6d2c5d7a71a84f0416bd57e4`

Model artifact:

`model.safetensors`

Observed artifact size:

`2035332888 bytes` (~2.04 GB)

Observed SHA-256:

`7758b150b8139deb48ac1ff6f181f745c8fedd5511232fd974b3eb217d83b514`

Observed Xet hash:

`f4ef91562d7f139a6d69649c4415c758ce4ab69f11826b2f6bbaac904e0fc0ef`

Declared license:

`MIT`

Primary source URLs:

- https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B
- https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B/tree/6bce5f06044837fe6d2c5d7a71a84f0416bd57e4
- https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B/blob/6bce5f06044837fe6d2c5d7a71a84f0416bd57e4/model.safetensors
- https://github.com/microsoft/VibeVoice

## Architecture facts supported by primary source

The official model card describes the realtime model as an interleaved/windowed streaming design. Incoming text is incrementally encoded while diffusion-based acoustic latent generation continues from prior context. The realtime variant removes the semantic tokenizer and uses an acoustic tokenizer at 7.5 Hz.

The release identifies the language model substrate as `Qwen2.5-0.5B`; the acoustic tokenizer decoder is described as roughly 340M parameters and the diffusion head as roughly 40M parameters. Context training extends to 8192 tokens.

These facts explain why the model is architecturally interesting for Frankenstein: text can begin arriving from the dialogue provider before the full answer exists, allowing TTFT and TTS synthesis to overlap. They do **not** prove low end-to-end conversational latency on the target system.

## German evidence boundary

Microsoft added experimental speakers for DE/FR/IT/JP/KR/NL/PL/PT/ES in December 2025. However the current official model card simultaneously states that the realtime model is trained/intended for English and that other languages may produce unpredictable output.

Therefore the correct Trigger-7 classification is:

```text
GERMAN_SPEAKER_AVAILABLE == TRUE
GERMAN_PRODUCTION_SUPPORT == UNPROVEN
GERMAN_F2_E2E_CREDIT == 0
```

The experimental German voice is useful precisely because it gives a cheap falsifier: if German naturalness/pronunciation is poor on the target hardware, the model can be rejected early despite attractive size/latency.

## Safety / packaging / runtime gates

Before any runtime promotion:

1. quarantine-download the exact pinned revision, not mutable `main`;
2. verify `model.safetensors` SHA-256 after retrieval;
3. pin the exact inference code/runtime revision separately from the weight revision;
4. inspect any executable Python/custom model code before use;
5. keep the test inside the authorized `clay-direct-dev` research sandbox;
6. record runtime/framework versions and all artifact identities;
7. measure outbound model/API counters and require LOCAL-SOLO inference for local acceptance;
8. do not treat MIT metadata as proof that every downstream bundled voice/resource has identical redistribution terms; inspect concrete bundled assets.

## Bounded German falsifier benchmark

Use the common Trigger-7 causal receipt format and the same German text set used for competing TTS candidates.

Minimum first pass:

### A. Latency

- cold/warm startup;
- text arrival -> first audible PCM p50/p95;
- real-time factor;
- streamed-chunk cadence/jitter;
- generation cancellation -> playback stop latency.

### B. German speech quality

Pinned utterances must cover:

- ordinary conversational German;
- compound words;
- dates and numbers;
- names used by Frankenstein;
- technical German/English mixtures;
- abbreviations;
- punctuation and sentence-boundary prosody;
- 30–60 second multi-sentence answer;
- at least one 5+ minute continuity run if the short pass survives.

### C. Frankenstein voice ABI

Reject as a primary candidate if it cannot satisfy all of:

- stable acceptable male acoustic identity;
- intelligible natural German;
- incremental synthesis without sentence-boundary collapse;
- immediate cancellation without replay/duplicate chunks;
- no false commit of unheard audio;
- deterministic enough speaker selection for long sessions;
- acceptable state-derived expression mapping or a well-defined constrained fallback.

### D. Resource coexistence

Measure RSS/PSS/GPU/VRAM and contention while the resident Frankenstein body is accounted for. A 0.5B label alone does not establish whole-system fit; the acoustic decoder and runtime memory footprint are material.

## High-information decision rule

Promote to a target runtime benchmark only if the exact pinned package remains auditable and fits the hardware envelope from `t7_hardware_inventory.py`.

After the first German run:

```text
IF German quality is clearly below Qwen3-TTS / compact baseline
    -> preserve NEGATIVE_RESULT and retire from production frontier.
ELSE IF TTFA/resource use is materially better while cancellation and identity hold
    -> keep as compact Pareto challenger and benchmark head-to-head.
ELSE
    -> retain only as architecture/reference evidence.
```

## Current conclusion

VibeVoice-Realtime-0.5B improves Trigger-7 coverage because it tests a different point on the quality/latency/resource Pareto frontier: a small streaming diffusion TTS whose text/audio pipeline can overlap with LLM generation. Its strongest present weakness is exactly the project-critical axis: German is experimental rather than supported.

This audit therefore adds a **measurable falsifier**, not a source-derived winner.

Evidence law:

```text
PRIMARY_MODEL_CARD != F2_RUNTIME
UPSTREAM_300MS != F2_TTFA
EXPERIMENTAL_DE_VOICE != GERMAN_ACCEPTANCE
0.5B_LABEL != WHOLE_FRANKENSTEIN_RESOURCE_FIT
MIT_MODEL_METADATA != AUTOMATIC_ALL_ASSET_PACKAGING_APPROVAL
SOURCE_AUDIT_COMPLETE != TRIGGER4_ACCEPTANCE
```
