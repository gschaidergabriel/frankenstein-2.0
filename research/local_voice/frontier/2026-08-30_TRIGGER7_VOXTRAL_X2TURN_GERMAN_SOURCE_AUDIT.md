# Trigger 7 — Voxtral Realtime + X2-Turn German source audit

Date: 2026-08-30
Research ID: `T7-TURN-002`
Status: `E2_SOURCE_AUDIT_COMPLETE / GERMAN_X2_TURN_UNVERIFIED / NO_TARGET_RUNTIME_CREDIT`

## 0. Evidence boundary

This result is a primary-source/source-code audit only. It does **not** establish target/VPS execution, German F2 end-to-end quality, whole-Frankenstein residency, V4, Trigger-4 acceptance, or V6.

```text
UPSTREAM_GERMAN_ASR != F2_GERMAN_ASR
VOXTRAL_GERMAN_ASR != X2_TURN_GERMAN_TURN_SEMANTICS
X2_BILINGUAL_TURN_METRICS != GERMAN_TURN_METRICS
SOURCE_PIN != MODEL_ARTIFACT_DOWNLOAD
4B_FITS_GPU != WHOLE_FRANKENSTEIN_FITS
```

## 1. Primary source pins observed

### Voxtral Mini 4B Realtime 2602

- upstream model: `mistralai/Voxtral-Mini-4B-Realtime-2602`
- primary model card: `https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602`
- observed model-card revision surface: `f74a921cfb3cdb758dd16f9a9c8a67faed7c0465`
- license: Apache-2.0
- architecture class: native streaming multilingual ASR, roughly 4B total
- current card exposes configurable transcription delay in multiples of 80 ms; 480 ms is the recommended accuracy/latency operating point
- exact downloadable weight-file revision/hash is **not** claimed by this audit and must be resolved again immediately before quarantine download

### X2-Turn

- source repository: `X-Square-Robot/X2-Turn`
- observed GitHub `main`: `3609a0fd11b4a1dc2b2629e95538bbe0860da96d`
- model: `x-square-robot/X2-Turn-4B-0812`
- paper: arXiv `2608.10878`
- license: Apache-2.0
- base model: Voxtral Mini 4B Realtime 2602
- published language scope: Chinese + English, including mixed speech
- local Transformers loader is documented without `trust_remote_code`
- upstream quick-start asks for Linux + NVIDIA GPU + at least 24 GB VRAM

## 2. New high-value finding: fused ASR + turn prediction is a direct Frankenstein architecture candidate

X2-Turn adds a frame-synchronous turn-state head in parallel with ASR over shared streaming Voxtral representations. It emits a turn prediction every 80 ms.

Published inference labels:

```text
idle
noidle
speaking
turn_end
backchannel
uncertain
```

This is unusually well aligned with Frankenstein's existing voice-control needs:

```text
continuous audio
  -> streaming transcript
  + simultaneous turn-state evidence
  -> VoiceIntent / WAIT / interruption policy
  -> generation ownership
  -> cancellable TTS/playback
```

Potential systems advantage, still only a hypothesis:

> one shared streaming speech backbone may reduce duplicated audio/front-end compute and synchronization error compared with a separate ASR model plus an independent semantic endpoint model.

That hypothesis requires same-hardware measurement. Source architecture alone does not establish lower latency or lower resident memory.

## 3. Voxtral is immediately relevant to German ASR

The official Voxtral model card publishes German FLEURS WER at multiple streaming delays:

| delay | upstream German WER |
| ---: | ---: |
| 160 ms | 9.50% |
| 240 ms | 8.15% |
| 480 ms | 6.19% |
| 960 ms | 4.87% |
| 2400 ms | 4.15% |

Interpretation for Trigger 7:

- German support is directly evidenced upstream for the **base Voxtral ASR**.
- 160/240/480 ms form the first useful F2 latency/accuracy sweep; 960/2400 ms remain accuracy references but may be too slow for natural turn timing.
- upstream FLEURS WER is not room-audio, far-field, echo, dialect, technical-name or actual Frankenstein evidence.

Decision:

`Voxtral-Mini-4B-Realtime-2602` is promoted to a **high-resource German streaming ASR challenger**, conditional on whole-body hardware headroom.

It does not replace Nemotron/Qwen3-ASR/Whisper before the common German corpus is measured.

## 4. Critical counterhypothesis: X2-Turn may lose the German advantage of its base model

The X2 checkpoint is published/evaluated as Chinese-English. The paper's Easy-Turn evaluation is bilingual Chinese-English, not German.

Therefore the central counterhypothesis is:

> the shared Voxtral representation may still transcribe German reasonably, while the X2 turn head's semantic `speaking` / `turn_end` / `backchannel` boundary may be poorly calibrated for German syntax and discourse particles.

German is particularly useful as a falsifier because clause-final information, subordinate-clause ordering and long compounds can make premature semantic endpointing expensive.

Examples that must not be treated as easy English equivalents:

- `Ich glaube, dass wir ...` followed by a pause before the subordinate clause completes;
- self-repair: `Nein, ich meine — also eigentlich ...`;
- short backchannels: `ja`, `mhm`, `okay`, `genau`, `nein`;
- conjunction continuation after a strong prosodic pause;
- mixed German/English technical names and identifiers;
- user speech beginning while Frank is still playing audio.

Result: X2-Turn remains `GERMAN_TURN_UNVERIFIED`. It receives architecture/falsifier credit only.

## 5. Hardware/resource consequence

The X2 project quick-start currently specifies at least 24 GB VRAM for its 4B demo path. That does not prove 24 GB is a hard minimum for every optimized runtime, but it is enough to block an unmeasured default-profile promotion.

The relevant Trigger-7 test is not:

```text
CAN_X2_LOAD?
```

It is:

```text
CAN_X2_OR_VOXTRAL_COEXIST_WITH
  GRID10/GWT/J-Space/HCU control
  + UnifiedDB/state/memory
  + local dialogue model
  + TTS
  + AEC/denoise
  + audio buffers
  + Retina/other admitted resident services
WITHOUT swap/eviction/tail-latency collapse?
```

Until the pending `clay-direct-dev` hardware/residency receipt exists, classify X2-Turn as a Profile-H/high-resource research candidate, not a baseline product dependency.

## 6. Smallest German falsifier

### Phase A — ASR backbone

Use the same pinned German audio corpus for:

1. Voxtral Realtime at 160 ms, 240 ms and 480 ms;
2. Nemotron 3.5 Streaming at its predeclared right-context sweep;
3. Qwen3-ASR 0.6B / 1.7B where runnable;
4. donor Whisper baseline.

Record at least:

- WER/CER;
- partial transcript revision rate;
- speech onset -> first stable lexical evidence;
- endpoint -> final transcript latency;
- mixed German/English technical tokens;
- echo/noise/double-talk slices;
- CPU/RAM/GPU/VRAM and p50/p95/p99.

### Phase B — X2 turn head

Run a German turn corpus with labels for:

- complete turn;
- incomplete pause;
- self-correction;
- backchannel;
- interruption;
- overlap/double talk;
- deliberate hesitation;
- compound/subordinate clauses.

Compare X2's 80-ms state stream against the current deterministic/semantic controller and DualTurn-style challenger.

Primary failure metrics:

```text
false_turn_end_rate
false_backchannel_rate
missed_turn_end_rate
barge_in_detection_latency
premature_generation_start_rate
cancelled_branch_rate
unheard_output_commit_errors
```

A single-frame `turn_end` is evidence, not authority. F2 policy must smooth/gate predictions and retain deterministic generation/cancellation ownership.

## 7. Salvage path if German X2 turn semantics fail

Failure of the released bilingual checkpoint would **not** invalidate the architecture.

Possible next research step:

```text
retain/pin German-capable Voxtral streaming backbone
-> collect/label German F2 turn-state corpus
-> train or adapt only the lightweight turn-state head if licensing/runtime permits
-> preserve ASR quality and deterministic F2 turn policy
```

This is a future hypothesis, not a training authorization or current implementation decision.

## 8. Decision

```text
VOXTRAL REALTIME 4B
  status: PROMOTED_TO_GERMAN_ASR_CHALLENGER
  reason: direct upstream German streaming evidence + configurable latency
  blocker: target whole-body residency/runtime benchmark

X2-TURN 4B
  status: PROMOTED_TO_FUSED_ASR_TURN_ARCHITECTURE_FALSIFIER
  production German credit: 0
  reason: strong architectural fit, but published turn evaluation is Chinese/English
  blocker: German turn corpus + target resource receipt
```

No currently favored lightweight modular production stack is displaced by this source audit.

## 9. Exact next gate

After the already-active VPS/hardware re-entry claim produces a real `clay-direct-dev` resource receipt:

1. verify exact Voxtral/X2 model artifact revisions and hashes before download;
2. run plain Voxtral first so German ASR quality is isolated from X2 fine-tuning/turn-head effects;
3. if resident headroom permits, run X2 on the same German audio;
4. measure X2 German turn labels separately from transcript quality;
5. route only a measured bundle through the common `t7_voice_receipt.py` causal receipt path;
6. hand to Trigger 4 only after real target evidence, never from this E2 audit.

## 10. Sources

Primary/current sources consulted in this audit:

- Mistral AI, `mistralai/Voxtral-Mini-4B-Realtime-2602`, Hugging Face model card.
- Fu et al., `X2-Turn: Frame-Synchronous Dual-Head Modeling for Joint Streaming ASR and Turn State Prediction`, arXiv:2608.10878.
- `X-Square-Robot/X2-Turn`, GitHub source at observed `main` SHA `3609a0fd11b4a1dc2b2629e95538bbe0860da96d`.
- `x-square-robot/X2-Turn-4B-0812`, Hugging Face model card.

All published benchmark values above remain `UPSTREAM_RESULT` until reproduced in the Frankenstein target envelope.
