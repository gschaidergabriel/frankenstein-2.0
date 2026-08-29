# Trigger 7 — Cancellable PipeWire/ALSA Playback Transport Audit

Date: 2026-08-30
Claim: `T7-AUDIO-002/E2_CANCELLABLE_PIPEWIRE_ALSA_TRANSPORT_AUDIT`
Worker: `GPT-5.6-Sol-TRIGGER7`
Evidence class: `SOURCE_AUDIT_ONLY`
Runtime credit: `0`
German E2E benchmark credit: `0`
Trigger-4 acceptance credit: `0`

## Question

What is the smallest fully-local Linux playback transport that can satisfy Frankenstein 2.0's hard voice invariant:

> user barge-in must stop unspoken output promptly, and text/audio that was generated or queued but not actually heard must never be committed as spoken history.

This audit intentionally does **not** choose ASR, TTS, dialogue-model, AEC or endpointing winners. Those lanes are already active in parallel Trigger-7 work.

## Current F2 contract constraint

Observed F2 source at main `aaaf7257b47bbabf4fde617a8aebfe9bd32bbbc9`:

- `src/frankenstein2/voice_contract.py` blob `ad639b02ea69771014a2cad5b38103036b35bdfb` defines exact immutable `VoiceIntent -> VoiceSessionCapsule -> VoiceOutcome` lineage.
- The current contract is identity/provenance only and explicitly performs no audio I/O.
- `VoiceOutcome` admits `RETURNED`, `INTERRUPTED`, `ENDED`, `ERROR`, `UNKNOWN` and binds one terminal outcome to one exact voice session.

Therefore the playback transport should be a subordinate evidence-producing organ. It should **not** replace `VoiceOutcome`, invent another session identity, write canonical memory directly, or mint completion/effect authority.

## Primary-source findings

### PipeWire native stream

Current PipeWire Stream API documents:

- `pw_stream_set_active(stream, false)` to deactivate a stream;
- `pw_stream_flush(stream, false)` for a non-draining flush; the documentation states that a flush without drain is useful after changing to PAUSED to flush remaining data from queues and converters;
- `pw_stream_get_time_n()` to obtain a timing snapshot containing graph time, stream delay and internal queued/buffered data;
- dequeue/process/queue streaming through `pw_stream_dequeue_buffer()` / `pw_stream_queue_buffer()`; the realtime process path must use RT-safe operations only.

Primary documentation:

- https://docs.pipewire.org/group__pw__stream.html
- https://docs.pipewire.org/page_tutorial4.html
- https://pipewire.pages.freedesktop.org/pipewire/group__pw__stream.html

### ALSA PCM fallback

Current ALSA PCM API documents:

- `snd_pcm_drop()` = stop PCM and drop pending frames;
- `snd_pcm_drain()` = stop while preserving/draining pending frames;
- `snd_pcm_prepare()` = prepare/recover stream for subsequent use;
- `snd_pcm_delay()` and PCM status/timestamps expose pending-frame / timing evidence.

Primary documentation:

- https://www.alsa-project.org/alsa-doc/alsa-lib/group___p_c_m.html

For barge-in, **drain is the wrong semantic** because it intentionally preserves pending playback. The fallback cancellation primitive is `snd_pcm_drop()`, followed by a controlled prepare/restart path.

## Proposed F2 playback ABI

This is a build candidate, not accepted code.

```text
PlaybackSession
  voice_session_id
  voice_session_sha256
  playback_generation        # monotonic within exact voice session
  utterance_id
  stream_backend             # PIPEWIRE_NATIVE | ALSA_PCM
  device_ref
  sample_rate_hz
  channels
  sample_format
  started_monotonic_ns

AudioChunk
  voice_session_id
  playback_generation
  utterance_id
  chunk_index
  pcm_sha256
  frame_count
  produced_monotonic_ns
  queued_monotonic_ns | null
  first_frame_estimated_audible_ns | null
  last_frame_estimated_audible_ns | null

PlaybackCancelReceipt
  voice_session_id
  old_playback_generation
  new_playback_generation
  cancel_reason               # BARGE_IN | SESSION_END | ERROR | SUPERSEDED
  detected_monotonic_ns
  transport_cancel_called_ns
  queue_flush_completed_ns | null
  queued_audio_before_cancel_ns | null
  residual_audio_after_cancel_ns | null
  backend
  backend_result

PlaybackCommitReceipt
  voice_session_id
  playback_generation
  utterance_id
  highest_committable_chunk_index
  evidence_basis              # PLAYED_TIMELINE_ESTIMATE | DEVICE_TIMESTAMP | VERIFIED_LOOPBACK
  committed_audio_sha256
  committed_text_span_ref
```

Authority:

```text
PLAYBACK_RECEIPT = VOICE_EVIDENCE_ONLY
PLAYBACK_RECEIPT != MEMORY_AUTHORITY
PLAYBACK_RECEIPT != EFFECT_AUTHORITY
PLAYBACK_RECEIPT != SESSION_COMPLETION
```

## Cancellation algorithm candidate

### PipeWire native

```text
on BARGE_IN:
  1. atomically advance playback_generation
  2. stop accepting/queueing chunks from the old generation
  3. pw_stream_set_active(stream, false)
  4. pw_stream_flush(stream, false)
  5. record transport/timing state and cancellation receipt
  6. reject every late callback/chunk whose generation != current generation
  7. on next admitted utterance, reactivate and queue only the new generation
```

The exact ordering between deactivate/flush and backend state transitions must be proven in the target implementation; this audit grants no runtime guarantee from documentation alone.

### ALSA fallback

```text
on BARGE_IN:
  1. atomically advance playback_generation
  2. stop writers for the old generation
  3. snd_pcm_drop(handle)
  4. record pending/delay/timing evidence
  5. snd_pcm_prepare(handle) before next admitted playback
  6. reject old-generation chunks/callbacks
```

Do not substitute `snd_pcm_drain()` for cancellation.

## Critical memory / causal rule

The existing Trigger-7 protocol already requires:

> text/audio not actually heard must not remain falsely committed as spoken.

Therefore:

```text
TTS_GENERATED != SPOKEN
CHUNK_QUEUED != SPOKEN
BACKEND_ACCEPTED_BUFFER != SPOKEN
PLAYBACK_GENERATION_CURRENT + PLAYED_EVIDENCE -> ELIGIBLE_FOR_SPOKEN_COMMIT
```

A cancellation advances `playback_generation`. Any old-generation chunk arriving afterward is stale by construction and cannot become spoken-history evidence.

This generation fence also closes a race where TTS inference continues briefly after barge-in and hands late PCM to the audio callback.

## Integration with current `VoiceOutcome`

Recommended mapping:

- barge-in does **not** automatically end the entire `VoiceSessionCapsule`;
- it terminates/supersedes one playback generation and may produce an interruption evidence receipt;
- only the higher voice-loop policy decides whether the exact voice session's terminal `VoiceOutcome` is `INTERRUPTED`, `RETURNED`, `ENDED`, `ERROR` or remains live;
- `VoiceOutcome.result_ref/result_sha256` may eventually bind a deterministic aggregate of admitted playback/ASR/turn receipts, but that is a separate F2 contract change and should be tested independently.

## Required metrics

For every cancellation benchmark record:

- `barge_in_detected_to_cancel_call_ms`
- `cancel_call_to_transport_quiescent_ms`
- `barge_in_detected_to_last_audible_agent_sample_ms`
- `queued_audio_before_cancel_ms`
- `residual_audio_after_cancel_ms`
- stale chunks rejected after generation advance
- duplicate/replayed chunk count
- unheard text/audio commit violations
- XRUN/underrun count after restart
- CPU/RSS and configured quantum/buffer latency

`pw_stream_get_time_n()` / ALSA delay/timestamp facilities can support transport estimates, but the acceptance-grade `last audible sample` measurement should prefer physical or software loopback capture because queue state is not identical to sound actually emitted by the speaker.

## E3 falsifier / Trigger-4 test capsule

### Test audio

Generate or use deterministic PCM with a clearly detectable post-cutover sentinel sequence:

```text
PREAMBLE -> CUT_POINT -> SENTINEL_A -> SENTINEL_B -> TAIL
```

### Procedure

1. Start playback and capture actual output through monitor/loopback where available.
2. Trigger deterministic cancellation at `CUT_POINT`.
3. Advance playback generation before transport cancellation.
4. Attempt to inject at least one deliberately late old-generation chunk.
5. Verify the stale chunk is rejected before queueing.
6. Measure time from cancel trigger to last emitted old-generation sample.
7. Verify post-cutover sentinels are absent beyond the declared residual window.
8. Start a new playback generation and verify clean restart without old samples.
9. Build the would-be spoken-history commit from playback receipts.
10. Verify no unheard old-generation text/audio is eligible for commit.

### Hard failures

```text
OLD_GENERATION_CHUNK_ACCEPTED
POST_CANCEL_SENTINEL_PLAYED_OUTSIDE_BOUND
UNHEARD_OUTPUT_COMMITTED
CANCEL_USES_DRAIN_SEMANTICS
PLAYBACK_RECEIPT_WRITES_CANONICAL_MEMORY_DIRECTLY
PLAYBACK_TRANSPORT_MINTS_VOICE_SESSION_OUTCOME_DIRECTLY
CROSS_SESSION_GENERATION_COLLISION
RESTART_REPLAYS_STALE_AUDIO
```

## Hypotheses and counterhypotheses

### H1 — native PipeWire is the best primary transport

Reason: first-class low-latency graph/stream API, explicit stream activation/flush and timing introspection.

Counterhypothesis: the actual VPS/audio deployment path may expose ALSA more reliably, or PipeWire server/device policy may add more jitter/complexity than direct ALSA.

Discriminator: same deterministic cancellation/loopback benchmark on both backends on target hardware.

### H2 — queue flush is enough to define heard output

Counterhypothesis: hardware/device buffering after the application/graph boundary can still emit old audio after the queue is logically flushed.

Discriminator: loopback capture of last audible old-generation sample versus transport queue/timing estimate.

### H3 — very small audio buffers always improve conversation

Counterhypothesis: lower quantum/buffer latency increases scheduling overhead/XRUNs enough to worsen perceived latency/stability under concurrent ASR/LLM/TTS load.

Discriminator: Pareto sweep of configured buffer/quantum sizes under the full resident Frankenstein load, tracking p95 cancellation latency, XRUNs and CPU.

## Decision

`PROMOTE_TO_TRIGGER4_BUILD_FALSIFIER`

Implement a small provider-neutral playback transport with:

1. exact `voice_session_id` binding;
2. monotonic `playback_generation` fence;
3. PipeWire-native cancellable backend;
4. ALSA `snd_pcm_drop()` fallback;
5. timing/cancel/commit receipts;
6. deterministic stale-generation rejection;
7. loopback-based cancellation correctness test.

Do **not** promote either backend to accepted production transport before target-hardware E3/V3 evidence.

## Evidence boundary

```text
PRIMARY_DOCS_READ = YES
F2_CURRENT_CONTRACT_READ = YES
BUILD_CANDIDATE = YES
SOURCE_AUDIT_COMPLETE = YES
TARGET_RUNTIME_EXECUTION = NO
TARGET_HARDWARE_LOOPBACK = NO
GERMAN_E2E_BENCHMARK = NO
TRIGGER4_ACCEPTANCE = NO
RUNTIME_CREDIT = 0
VOICE_ACCEPTANCE_CREDIT = 0
```

The current connector available to this organ can read/write GitHub state but does not expose the repository's `workflow_dispatch` write action. Therefore this organ cannot honestly turn the already-authorized `clay-direct-dev` sandbox route into a runtime receipt in this invocation. This is a tool-surface limitation, **not** a negative result about PipeWire, ALSA, the VPS, or Frankenstein.
