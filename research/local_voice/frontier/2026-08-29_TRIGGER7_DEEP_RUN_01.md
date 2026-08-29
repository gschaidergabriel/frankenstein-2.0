# Trigger 7 — Deep Run 01 — Local realtime voice + dual inference

Date: 2026-08-29
Worker: GPT-5.6-Sol-TRIGGER7
Status: SOURCE/ARCHITECTURE FRONTIER ADVANCED; TARGET/VPS RUNTIME NOT OBSERVED

## Owner authority delta absorbed

Frankenstein 2.0 is intentionally dual-mode:

1. **CLAUDE-AUGMENTED** — the installed Frankenstein package may use Claude Code as a strong inference/reasoning organ when Claude Code is available and authorized.
2. **LOCAL-SOLO** — the same installed Frankenstein must also remain operational with local inference when Claude is absent. Qwen3.5-4B-class models are the first 4B local research tier.

Claude/Qwen are replaceable inference organs. Neither is Frankenstein identity, canonical memory, GWT/HCU/J-Space authority, or EffectGate/effect authority.

## Major new result of Run 01

The strongest architecture hypothesis changed from a simple sequential cascade to a **speculative, cancellation-safe local duplex cascade**:

```text
Mic / echo-cleaned two-channel audio
  -> causal VAD + turn-state model
  -> streaming German ASR partials
  -> endpoint anticipation / EOT probability
  -> speculative InferenceProvider request
       [LOCAL Qwen] or [Claude Code]
  -> incremental response text
  -> streaming local TTS
  -> cancellable audio ring buffer
  -> VoiceOutcome commit ONLY for actually heard output
```

Endpoint anticipation can start inference before reactive EOT fires. Any speculative response is invalidated if later speech contradicts the hypothesis. This can hide a material fraction of LLM/TTS latency without lying to memory about unheard speech.

## ASR frontier update

### A1 — NVIDIA Nemotron 3.5 ASR Streaming 0.6B — NEW TOP STREAMING CHALLENGER

Primary source:
- https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- pinned source tree observed: `832de54000fe0ab4f24e23ce1f8a3efa834844a7`

Source facts:
- 0.6B multilingual streaming ASR;
- German `de-DE` is explicitly in the highest `Transcription-ready` tier;
- runtime streaming right-context can be configured from 80 ms through 1.12 s;
- official model repository contains Transformers/NeMo assets and GGUF support;
- current license is `openmdw-1.1`, so licensing must be reviewed before product redistribution assumptions.

Why this matters for Frankenstein:
- real voice quality depends heavily on endpoint behavior, not merely offline WER;
- controllable 80/160/320/560/1120 ms-style streaming windows create a direct quality/latency Pareto experiment;
- German support is explicit rather than inferred from multilingual training.

No F2 WER/RTF claim yet.

### A2 — Qwen3-ASR 0.6B / 1.7B

Retained as top accuracy/efficiency challengers. They remain mandatory comparisons because Qwen3-ASR is German-capable and designed for streaming/offline use. Run 01 does NOT replace this family; it adds Nemotron 3.5 as a potentially more turn-taking-native competitor.

### A3 — German Whisper Large-v3-Turbo

Retained as donor-compatible baseline. It provides architectural continuity and a known implementation family, but it must not receive incumbent preference if Nemotron/Qwen win on real room audio.

## Turn-taking frontier — highest leverage finding

### Endpoint Anticipation

Paper: https://arxiv.org/abs/2606.13450

The paper predicts turn endpoints before they happen and reports, in its own Unmute experiment, approximately 505 ms average latency reduction at the cost of additional speculative compute. Upstream result only; not F2 credit.

**F2 interpretation:** start local Qwen/Claude inference on a high-confidence partial utterance before final ASR endpoint. Keep generation speculative until a commit barrier. If user continues/revises speech, cancel the branch.

### DualTurn Endpointing

Source: https://huggingface.co/anyreach-ai/dualturn-endpointing

Interesting properties:
- causal, frame-level two-channel user+agent model;
- ~80 ms prediction cadence;
- EOT + VAD + future-VAD outputs;
- designed for local/on-device operation;
- can listen to Frankenstein's own output channel, which is directly relevant to overlap and barge-in.

This is a stronger interaction primitive than `silence > N ms` alone.

### New F2 turn controller hypothesis

Do NOT collapse everything into one neural policy. Use:

```text
acoustic VAD
+ DualTurn-like EOT/FVAD
+ streaming ASR semantic partial
+ endpoint anticipation
+ Presence/Interruptibility
+ deterministic cancellation/commit FSM
```

Neural signals propose. Deterministic event/state rules own commit/cancel semantics.

## TTS frontier update

### T1 — Qwen3-TTS 12Hz 0.6B

Primary source: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice

Source facts:
- German among 10 supported languages;
- instruction-controllable tone/rhythm/emotion;
- upstream advertises streaming and first-audio latency as low as ~97 ms under its setup;
- Apache-2.0.

This remains the first quality-oriented candidate for ExpressionVector-driven Frankenstein speech.

### T2 — Fun-CosyVoice3 0.5B — PROMOTED CHALLENGER

Primary source: https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512

Source facts:
- explicit German support among 9 languages;
- zero-shot multilingual/cross-lingual voice cloning;
- instruction support for emotion/speed/volume;
- text-in + audio-out bi-streaming;
- upstream claims latency as low as ~150 ms.

Why promoted: the feature set maps unusually well to `ExpressionVector` and stable male identity requirements. It must now be benchmarked beside Qwen3-TTS, not treated as a secondary curiosity.

### T3 — Chatterbox Multilingual V3 — NEW QUALITY/PORTABILITY CHALLENGER

Primary source: https://huggingface.co/ResembleAI/chatterbox

Source facts:
- current multilingual V3 is a 0.5B-class family;
- German supported;
- MIT license;
- voice cloning and explicit expressiveness controls;
- community GGUF/ONNX local conversion paths exist.

This family may be operationally simpler than Qwen/Cosy on some target systems. No streaming-quality credit until measured.

### T4 — Piper/Thorsten

Retained only as latency/resource floor. It may still be useful for instant acknowledgements or emergency degraded mode even if a richer TTS wins full dialogue.

## Local LLM frontier — owner-requested 4B path

### L1 — first server candidate: KAINE Qwen3.5-4B abliterated Q4_K_M

Source:
- https://huggingface.co/kaineone/Qwen3.5-4B-abliterated-GGUF
- immutable repo revision: `551991a575c1d4221ca0f0cfca74037d26268411`
- file: `KAINE-Qwen3.5-4B-abliterated.Q4_K_M.gguf`
- size: about 2.78 GB according to current model card
- license: Apache-2.0
- runtime path: current llama.cpp / llama-server

Reason for first execution:
- simple single-file GGUF deployment;
- exact immutable repository revision available;
- model card explicitly documents current llama-server compatibility;
- small enough for the known 16 GB-class VPS memory envelope to be plausible, though latency remains unmeasured.

Abliteration removes/reduces refusal behavior. Therefore the model MUST remain behind Frankenstein's deterministic tool/effect boundary. It must never gain direct effect authority merely because it is less refusal-prone.

### L2 — quality-preservation challenger: wangzhang Qwen3.5-4B-abliterated

Source:
- https://huggingface.co/wangzhang/Qwen3.5-4B-abliterated
- immutable source revision: `3bcc7a546b609f8d4f7344b52a5dda1b8298cf7d`

Upstream self-reported properties:
- 3/200 refusal test result;
- KL divergence 0.0065 against the base behavior distribution;
- 50 optimization trials.

Interpretation: attractive because the research goal is not merely fewer refusals; it is to preserve useful intelligence while moving values/effect control into Frankenstein's own architecture. These upstream numbers are NOT German/F2 benchmarks.

### L3 — high-interest challenger: Claude-Opus-reasoning-distilled Qwen3.5-4B abliterated

Source:
- https://huggingface.co/huihui-ai/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated
- derived from `Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled`
- Apache-2.0 according to current model card
- GGUF quantizations exist, including Q4_K_M, through current quantization repos.

Why important:
- it is structurally close to the owner's desired experiment: preserve Claude-like reasoning behavior while running a 4B local core;
- it may outperform the plain abliterated base on planning/reasoning.

Why it is NOT first:
- the card itself calls the abliteration a crude proof-of-concept;
- the distillation source advertises English/Chinese/Korean more directly than German;
- CoT-heavy behavior can be actively bad for realtime voice TTFT;
- tool/state adherence must be independently tested.

It should be benchmarked after the plain 4B baseline, with thinking suppressed or tightly budgeted for the realtime channel.

## Claude Code provider — important architecture improvement

Current Anthropic documentation supports:
- `claude -p` programmatic mode;
- `--output-format stream-json`;
- `--input-format stream-json`;
- multiple user turns through streaming JSON input without relaunching the `claude` binary;
- session resume;
- current Claude Agent SDK `ClaudeSDKClient` with persistent multi-turn sessions and explicit interruption support.

Primary docs:
- https://docs.anthropic.com/en/docs/claude-code/cli-usage
- https://docs.claude.com/api/agent-sdk/python

This means Frankenstein 2.0 should NOT blindly copy the historical donor's one-short-lived-process-per-turn bridge. The preferred CLAUDE-AUGMENTED research path is a persistent provider process/client:

```text
VoiceLoop
  -> InferenceProvider ABI
      -> ClaudeAgentProvider (persistent ClaudeSDKClient / stream-json)
      -> LlamaCppProvider (persistent local Qwen server)
```

Both providers receive the same compact `VoiceSessionCapsule` and return the same typed candidate response stream.

### Cancellation law

On barge-in:
1. stop audio playback immediately;
2. invalidate unheard TTS chunks;
3. interrupt/cancel provider generation where supported;
4. do not commit unspoken generated text as `spoken_act`;
5. preserve only causal evidence that actually happened.

The Agent SDK's explicit interruption capability is therefore directly relevant to Frankenstein voice quality, not merely developer convenience.

## Native full-duplex frontier

### BayLing-Duplex

Paper: https://arxiv.org/abs/2606.14528
Source: https://github.com/BayLing-Models/BayLing-Duplex

Interesting because listen/speak/stop are represented in one autoregressive path and interruption is native. Still not promoted to German F2 candidate without German-quality evidence and hardware fit.

### JoyAI-Talker — NEW architecture reference

Paper: https://arxiv.org/abs/2608.01119

New Thinker-Talker + state-driven duplex architecture. Especially relevant because Frankenstein already wants state-derived expression rather than TTS personality theatre. Research reference pending released artifact/hardware/language validation.

### DuplexSLA — very high architectural relevance, not executable yet

Paper: https://arxiv.org/abs/2605.20755
Source: https://github.com/hyzhang24/DuplexSLA

It combines full-duplex speech with a structured action stream on a shared clock, which resembles Frankenstein's need for voice + tools/effects. Current project page says inference code/checkpoints are still forthcoming, so it receives architecture credit only.

### Lychee-FD

Source: https://huggingface.co/HIT-TMG/Lychee-FD

Now actually released, Apache-2.0, but ~13B BF16 and explicitly Chinese/English in current model metadata. Its default serving design expects substantial GPU resources. Therefore it is not the current 16 GB/CPU-oriented German candidate, but remains useful full-duplex architecture/training evidence.

## Proposed Frankenstein 2.0 inference ABI

```text
InferenceRequest
- request_id
- voice_session_capsule_digest
- provider_preference: AUTO | LOCAL | CLAUDE
- deadline_ms
- max_spoken_tokens
- interruption_generation
- tool_policy_digest
- memory_projection_refs
- user_partial_or_final_text
- partial_is_speculative

InferenceChunk
- request_id
- provider_id
- text_delta
- semantic_commit_candidate
- tool_candidate
- final
- cancelled
- provider_latency_ms

ProviderOutcome
- request_id
- provider_id
- ttft_ms
- completed
- interrupted
- tool_candidates
- generated_text_hash
- heard_text_hash
```

Critical law: provider output is candidate state. Only Frankenstein's deterministic GWT/effect/voice commit logic decides what becomes action or durable spoken outcome.

## Four-mode LLM experiment

Use identical German prompts, state capsules and tool schemas:

A. `CLAUDE_CODE_PERSISTENT`
B. `QWEN35_4B_OFFICIAL_Q4`
C. `QWEN35_4B_ABLITERATED_Q4`
D. `QWEN35_4B_CLAUDE_DISTILLED_ABLITERATED_Q4`

Measure:
- TTFT p50/p95;
- text generation tokens/s;
- time to first speakable clause;
- German naturalness;
- short-turn quality;
- interruption response;
- tool-selection exactness;
- state/identity adherence;
- memory-use correctness;
- hallucination rate;
- unnecessary refusal rate;
- action-policy violations;
- long-session drift;
- response verbosity under voice constraints.

Do not select the local model by generic benchmark score. Select by the F2 voice workload Pareto frontier.

## Target/VPS execution state

This Trigger-7 invocation does not have a connected SSH/VPS shell surface. Plugin discovery found no SSH/VPS/remote-shell connector. Therefore:

- target/VPS hardware inventory: NOT OBSERVED;
- model weight download to target/VPS: NOT EXECUTED;
- llama.cpp local model load on target/VPS: NOT EXECUTED;
- German runtime benchmark: NOT EXECUTED;
- V2/V3/V4 runtime credit: ZERO.

This is a platform/tool boundary, not a model failure.

## Exact next executable action

On the first authorized environment that exposes the target/VPS shell:

1. run `research/local_voice/tools/t7_hardware_inventory.py` and persist receipt;
2. verify free disk/RAM and current `llama-server` support;
3. run the pinned quarantine downloader against:
   - repo `kaineone/Qwen3.5-4B-abliterated-GGUF`
   - revision `551991a575c1d4221ca0f0cfca74037d26268411`
   - local quarantine name `qwen35-4b-kaine-abliterated-q4km-r551991a`
4. inspect the resulting SHA256 manifest and verify only expected GGUF/metadata artifacts;
5. launch `llama-server` bound to localhost only, initial context 4096, thinking disabled/zero reasoning budget for the realtime channel;
6. run German F2 provider benchmark;
7. if generation is too slow, retain it as deeper async thinker and test a smaller shell rather than discarding the 4B model immediately;
8. compare against the official Qwen3.5-4B Q4 and later the Claude-distilled abliterated challenger;
9. route measured result to Trigger 4 only after an E3 receipt exists.

## Current Run-01 conclusion

The strongest current production hypothesis is:

```text
LOCAL AUDIO ORGAN:
  Nemotron3.5/Qwen3-ASR
  + semantic/dual-channel endpointing
  + speculative cancellation-safe turn controller
  + Qwen3-TTS/CosyVoice3/Chatterbox measured TTS frontier

INFERENCE ORGAN:
  Claude Code persistent provider when present
  OR local Qwen3.5-4B-class provider

AUTHORITY:
  Frankenstein state/GWT/HCU/J-Space/EffectGate remains singular and provider-independent.
```

The next decisive information cannot come from more README comparison alone. It must come from the real target/VPS hardware receipt and the first pinned 4B runtime measurement.
