# Trigger 7 Owner Authority — Finish Cortex via Text/Information Packet I/O

Status: ACTIVE / OVERRIDES NARROWER PHYSICAL-AUDIO BLOCKERS
Date: 2026-08-31
Scope: all present and future Trigger-7 workers/organs

## Owner intent

Trigger 7 is not allowed to stop merely because a current execution surface lacks a real microphone, speaker, audio device, self-hosted runner, or physical owner-machine audio path.

The job of Trigger 7 is to finish the assigned Frankenstein 2.0 local-voice/cortex work under best engineering judgment as far as possible inside the current tool/runtime envelope, so that Claude Code at the end only has to:

1. integrate the finished subsystem into the real target runtime,
2. minimally adapt the real hardware/audio I/O bindings,
3. run final physical-device tests,
4. fix small target-specific issues,
5. finish/release.

Do not leave major architecture, controller logic, packet contracts, cancellation semantics, state propagation, benchmark harnesses, failure handling, integration adapters, or cortex behavior unfinished merely because true audio transport is unavailable.

## Mandatory substitution law

When real audio input/output is unavailable or would block progress, replace physical audio transport with deterministic text/information packets that preserve the semantics needed by the voice cortex.

The packetized surrogate must approximate the eventual audio path as closely as practical and MUST carry enough information to exercise the same controller/state/cancellation logic.

At minimum model these packet families or typed successors:

### VoiceInputPacket

- session_id / turn_id / packet_id
- monotonic timestamps
- source modality = simulated_audio_text | transcript_fixture | asr_partial | asr_final
- text/transcript payload
- language / locale
- partial/final flag
- confidence / uncertainty
- speech_start / speech_end markers
- VAD state
- endpoint/turn decision metadata
- overlap state
- interrupt intent / barge-in marker
- source duration or simulated audio duration
- sequence number and chunk ordering
- corruption/drop/duplicate/reorder fault flags when testing transport resilience

### VoiceOutputPacket

- session_id / turn_id / packet_id
- generated text segment
- expression/prosody intent metadata
- speech-act / VoiceIntent
- planned audio duration or token-to-audio timing estimate
- first-output timestamp
- chunk sequence
- cancellable flag
- playback state = queued | started | heard | interrupted | cancelled | completed
- heard_fraction or equivalent heard/unheard accounting
- interruption timestamp
- commit eligibility
- VoiceOutcome/re-entry payload

### CortexEventPacket

- wake / session_open / session_close
- VAD transitions
- endpoint decisions
- WAIT / backchannel / answer / tool-use / close intent
- GWT broadcast/uplift where applicable
- Presence/Interruptibility state
- cancellation propagation
- tool request/result
- memory read/write references
- error/fallback/recovery events
- timing and resource observations

## Required simulation fidelity

The surrogate path must exercise, not bypass:

- continuous-session state,
- turn-taking FSM,
- endpointing,
- backchannels,
- WAIT semantics,
- barge-in and cancellation,
- unheard-output rollback/non-commit,
- VoiceSessionCapsule or typed successor,
- VoiceIntent/GWT arbitration,
- Presence/Interruptibility,
- UnifiedDB/state/memory interaction,
- tool/effect boundaries,
- VoiceOutcome causal re-entry,
- semantic/silence close logic,
- reconnect/restart behavior,
- duplicate/drop/reorder protection,
- latency accounting using simulated/observed timestamps,
- long-conversation behavior.

A packet-only result may not claim acoustic quality, WER from unheard audio, real speaker output, microphone/AEC quality, or physical-device latency that was not observed. Those remain final physical integration gates. But absence of those gates MUST NOT prevent implementation completion of the surrounding cortex/runtime logic.

## Completion standard

Trigger 7 should prefer a nearly drop-in subsystem over a research note. Each work item should progress toward code, typed interfaces, fixtures, deterministic tests, benchmark harnesses, adapters, failure cases, and integration documentation.

The expected handoff to Claude Code is a narrow physical integration delta, not a broad implementation task.

Target handoff condition:

```text
CORTEX_LOGIC_COMPLETE == TRUE
PACKET_IO_SIMULATION_COMPLETE == TRUE
TURN/BARGE_IN/CANCEL_STATE_MACHINE_TESTED == TRUE
STATE/MEMORY/VOICEOUTCOME_REENTRY_TESTED == TRUE
FAILURE/RECOVERY_FIXTURES_TESTED == TRUE
REAL_AUDIO_BINDING_REQUIRED == MINIMAL
TARGET_SPECIFIC_ADAPTATION_REQUIRED == MINIMAL
FINAL_PHYSICAL_AUDIO_TESTS_REMAIN == TRUE
```

## Evidence law

```text
NO_PHYSICAL_AUDIO != STOP_WORK
NO_AUDIO_DEVICE != MODEL_FAILURE
PACKET_SIMULATION != ACOUSTIC_ACCEPTANCE
PACKET_SIMULATION == VALID_CORTEX_IMPLEMENTATION_EVIDENCE
SIMULATED_TIMING != PHYSICAL_LATENCY_CREDIT
SIMULATED_HEARD_STATE != REAL_SPEAKER_OUTPUT_CREDIT
IMPLEMENTATION_COMPLETION SHOULD CONTINUE UNTIL ONLY PHYSICAL_BINDING/FINAL_TEST DELTAS REMAIN
```

## Routing law for every future Trigger 7 invocation

Every Trigger-7 worker must read this authority before selecting its next action. If an older checkpoint says the next action is to wait for or route exclusively to a physical audio-capable host, reinterpret that checkpoint under this authority:

- preserve the physical test as a final validation gate,
- but continue building/testing the subsystem with text/information packet I/O now,
- do not duplicate semantic claims merely to change transport,
- keep the same research objective/semantic identity where applicable,
- persist exactly which claims are simulated versus physically observed.

This authority remains active until explicitly superseded by a newer owner instruction.
