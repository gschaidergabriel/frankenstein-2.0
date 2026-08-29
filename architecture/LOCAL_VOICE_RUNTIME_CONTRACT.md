# Frankenstein 2.0 — Local Voice Runtime Contract

Status: PROJECT-OWNER PRODUCT INVARIANT
Date: 2026-08-29

## 1. Product requirement

Frankenstein 2.0 SHALL provide a fully local reactive conversation mode that remains usable when OpenAI/ChatGPT, every external model API, and Internet connectivity are unavailable.

The first required language is German (`de-DE` / German conversational use). Additional languages are later extensions and must not delay German baseline acceptance.

OpenAI Realtime may remain as an optional compatibility, comparison, or explicitly user-selected remote adapter. It is not the canonical voice runtime and must not be required for baseline installation, wake, speech recognition, dialogue cognition, tool routing, speech synthesis, memory continuity, session end detection, or restart recovery.

## 2. Preserve the existing system

This is a provider/runtime substitution, not a second Frankenstein and not a new voice product.

The existing semantic conversation behavior must remain stable across local and optional remote adapters:

```text
WAKE / VAD
  -> SESSION START
  -> AUDIO INPUT
  -> SPEECH / TURN INTERPRETATION
  -> SAME FRANKENSTEIN COGNITIVE + MEMORY + TOOL SURFACE
  -> RESPONSE TOKENS / TOOL CALLS
  -> SPEECH OUTPUT
  -> BARGE-IN / INTERRUPTION
  -> END INTENT + BILATERAL SILENCE RULE
  -> SESSION STOP / RECEIPT
```

The following remain shared authority and must not fork per voice backend:

- canonical durable Frankenstein state lineage;
- UnifiedDB / memory semantics;
- GRID10/GWT cognition and policy where admitted;
- tool definitions, tool result return, and effect boundaries;
- wake/end/session state machine;
- live terminal / observability events;
- identity/personality/system-state projection;
- safety and permission gates.

A voice backend may produce candidate transcript/audio/model output. It may not create an independent memory, state, effect, completion, or identity authority.

## 3. Local Voice ABI

The conversation controller SHALL depend on provider-neutral streaming interfaces rather than OpenAI-specific event names.

Minimum semantic interfaces:

- `AudioInputStream`
- `SpeechActivityEvent`
- `TranscriptDelta`
- `TranscriptFinal`
- `DialogueTokenDelta`
- `ToolCallCandidate`
- `ToolResultReturn`
- `SpeechAudioDelta`
- `BargeIn`
- `EndIntentCandidate`
- `SessionLifecycleEvent`

Required adapters:

1. `local_realtime` — canonical baseline and default after local acceptance;
2. `openai_realtime` — optional compatibility/reference adapter only;
3. future local implementations may be swapped underneath the same ABI.

The controller must be able to run with the OpenAI adapter physically absent and with outbound network disabled.

## 4. Reference local pipeline

The initial implementation should prefer a modular, falsifiable pipeline because it can reuse the current conversation controller and independently benchmark each stage:

```text
MIC
 -> Silero/current local VAD + wake detector
 -> LOCAL STT
 -> LOCAL DIALOGUE MODEL
 -> SAME MEMORY / GRID10 / TOOLS / STATE
 -> LOCAL TTS
 -> SPEAKER
```

Candidate technologies are implementation hypotheses, not permanent product authority:

- STT baseline: Whisper-family local inference (`faster-whisper` or `whisper.cpp`), German locked during German acceptance;
- dialogue baseline: a current Qwen-class instruct model served locally through a provider-neutral/OpenAI-compatible local endpoint such as `llama.cpp`, sized by host capability;
- TTS baseline: local German TTS, initially comparing high-quality XTTS-class synthesis against a very low-latency Piper-class fallback;
- end-to-end speech-to-speech candidate: Qwen3-Omni-class local runtime where hardware permits, evaluated as an alternate backend rather than allowed to bypass Frankenstein state/tools.

No model name is accepted merely by documentation or benchmark reputation. The installer selects only locally present, verified profiles from an F2-owned capability manifest.

## 5. Hardware-adaptive profiles

The product shall preserve one semantic system while permitting different local compute profiles.

Suggested profile classes:

- `VOICE_LOCAL_MIN`: fastest viable German offline conversation; quality may be DEGRADED but functional;
- `VOICE_LOCAL_BALANCED`: default target for ordinary capable local hardware;
- `VOICE_LOCAL_QUALITY`: strongest fully local model set the detected host can sustain within latency/resource limits;
- `VOICE_LOCAL_OMNI_EXPERIMENTAL`: end-to-end speech model path when explicitly admitted by hardware and tests.

Profile selection must be evidence-based from real CPU/GPU/RAM/VRAM capability detection. A smaller model is not a different Frankenstein identity.

## 6. Realtime requirements

Local mode is not accepted merely because batch STT + LLM + WAV synthesis works.

The reactive mode must prove:

- incremental/streamed input handling;
- bounded end-of-turn detection;
- first response audio begins before a long answer is fully generated where the selected TTS/runtime supports streaming;
- user interruption/barge-in stops or supersedes queued speech;
- tool calls can interrupt the response path and re-enter with tool results;
- wake and session-stop behavior remains compatible with the existing conversation contract;
- no duplicate assistant turns after interruption/retry;
- restart recovers the same durable identity/state;
- complete operation with outbound network disabled.

## 7. German quality target

The goal is to approach the present OpenAI Realtime conversation experience while remaining honest about local hardware limits.

OpenAI Realtime is used only as a frozen comparison baseline during development. It is not part of the acceptance path.

Acceptance SHALL compare at least:

- German recognition accuracy on clean speech, normal room noise, names, numbers, commands, and spontaneous speech;
- semantic answer quality and adherence to Frankenstein state/personality;
- tool-selection/tool-argument accuracy;
- first-transcript, first-token, and first-audio latency;
- interruption recovery and turn-taking naturalness;
- German pronunciation, prosody, intelligibility, and voice consistency;
- long-session memory/state continuity;
- hallucinated tool/end-intent rate;
- CPU/GPU/RAM/VRAM usage and thermal/resource stability.

`near_parity` may only be claimed after the same German test corpus is run against the frozen remote reference and the selected local profile. Until then the correct status is `UNMEASURED`, `DEGRADED`, or `LOCAL_ACCEPTED`, not "same quality".

## 8. Offline acceptance gate

A local voice profile is accepted only if an exact run proves:

1. outbound network disabled before session start;
2. no OpenAI/API key required or read;
3. wake -> German user turn -> local transcript -> local cognition -> spoken German response succeeds;
4. at least one existing Frankenstein read tool succeeds and re-enters the conversation;
5. at least one interruption/barge-in succeeds without duplicate speech;
6. explicit end intent plus configured bilateral-silence policy terminates correctly;
7. service/process restart preserves the same durable state lineage;
8. latency/resource measurements are recorded;
9. model/runtime identities and hashes are recorded;
10. no remote provider process or network request contributed to the result.

## 9. Distribution rule

The final release package must either include the selected local voice runtime/models where licensing and size permit, or include deterministic model acquisition instructions/manifests that the local installer can execute before offline acceptance.

After acquisition and installation, normal voice operation must remain completely local.

The installer must report exact status per profile: `NATIVE`, `ADAPTED`, `DEGRADED`, or `BLOCKED`. It must never silently fall back to ChatGPT/OpenAI because local inference is slow or unavailable.

## 10. Completion consequence

Frankenstein 2.0 is not voice-complete if the reactive conversation mode requires ChatGPT/OpenAI or another external model service.

The canonical target is:

```text
FRANKENSTEIN 2.0 + LOCAL MIC + LOCAL COMPUTE + LOCAL SPEAKER
= COMPLETE GERMAN REACTIVE CONVERSATION MODE

INTERNET / OPENAI / CHATGPT / VPS
= OPTIONAL EXTENSION ONLY
```
