# Trigger 7 — German Realtime Voice Benchmark V1

Date: 2026-08-29
Status: PREDECLARED BENCHMARK CONTRACT / NO RUNTIME CREDIT
Owner lane: Trigger 7 research; Trigger 4 owns F2 build acceptance
Primary language: German

## 1. Purpose

This benchmark exists to stop Frankenstein 2.0 from selecting a local voice stack by README numbers, isolated WER, isolated TTS latency, generic LLM leaderboards, or one subjective demo.

The unit under test is the **same Frankenstein entity speaking through a candidate local voice organ**. The benchmark therefore measures the complete causal path and preserves the donor requirements: realtime turn taking, WAIT/backchannels, barge-in, memory/tool/state continuity, stable acoustic identity, and correct commit of only what the user could actually have heard.

A result from this benchmark is evidence. It is not automatically V4/V5/V6 and it never self-awards Trigger-4 acceptance.

## 2. Mandatory runtime modes

### LOCAL_SOLO — mandatory floor

All required ASR, dialogue inference and TTS execution for the run is local/self-hosted on the installed target system or the explicitly measured target-class machine. The run records counters and must satisfy:

```text
outbound_model_api_calls == 0
outbound_asr_api_calls == 0
outbound_tts_api_calls == 0
```

Research/download networking before the run is allowed. Network model inference during the run is not.

### CLAUDE_AUGMENTED — optional comparison

The same scenarios may be repeated with the admitted optional Claude provider. This run is scored separately and cannot substitute for LOCAL_SOLO.

## 3. Whole-product resource law

Voice is not allowed to benchmark as though it owns the entire machine. The recorded environment must include enough resource information to evaluate coexistence with the installed Frankenstein runtime:

- GRID10/GWT/J-Space/HCU control path;
- UnifiedDB/memory/state;
- persistent pulse/background services;
- Perception/Retina services admitted on the target;
- audio transport/AEC/turn controller;
- ASR, dialogue model, TTS and their caches;
- installer/host adapter overhead.

A model that fits only when the rest of Frankenstein is stopped is not a production voice winner.

Report at least peak and steady RAM/RSS; GPU/VRAM where present; model disk footprint; warmup time; CPU utilization; and any model loading/contention event visible during the run.

## 4. Receipt format

Use `research/local_voice/tools/t7_voice_receipt.py` over JSONL containing exactly one `run` record plus one or more `turn` records.

### Run record

Required core fields:

```json
{
  "kind": "run",
  "schema_version": 1,
  "run_id": "...",
  "language": "de",
  "runtime_mode": "LOCAL_SOLO",
  "network_counters": {
    "outbound_model_api_calls": 0,
    "outbound_asr_api_calls": 0,
    "outbound_tts_api_calls": 0
  }
}
```

The real benchmark receipt should additionally persist exact source/model revisions, model-file SHA-256, runtime/library versions, host inventory receipt identity, quantization, context size, sampling/decoding controls, audio format/buffer sizes, and process/resource measurements.

### Turn timestamps

Nanosecond monotonic timestamps where available:

- `user_speech_end`
- `asr_final`
- `inference_request`
- `inference_first_token`
- `first_speakable_clause`
- `tts_request`
- `tts_first_audio_ready`
- `first_audio_played`
- `barge_in_detected`
- `playback_stopped`

The receipt tool derives comparable deltas, rejects causal inversions and emits p50/p95/p99/max without inventing missing observations.

### Causal flags

Per turn, record when applicable:

- `barge_in_expected`
- `generation_cancelled`
- `unheard_output_committed`
- `duplicate_audio_detected`
- `replayed_audio_detected`

Any durable spoken outcome must represent what was actually played/heard, not merely generated text.

## 5. Scenario matrix

Use multiple recordings/turns per class. Synthetic audio may validate plumbing, but V4-quality evidence requires real German room audio and real interactive runs on the target/target-class setup.

### A — short natural turns

Examples:

1. `Wie spät ist es ungefähr?`
2. `Was meinst du damit?`
3. `Ja, genau.`
4. `Nein, das war nicht meine Frage.`
5. `Sag es kürzer.`
6. `Und dann?`

Measure rapid endpointing, short-answer quality, first speakable clause and over-verbosity.

### B — mid-sentence pause / false endpoint

Examples must contain deliberate pauses after syntactically plausible but unfinished fragments:

- `Ich glaube, wir sollten ... [pause] ... zuerst den Speicher prüfen.`
- `Wenn das Modell lokal läuft ... [pause] ... wie viel RAM bleibt dann übrig?`
- `Mach bitte nicht ... [pause] ... nein, anders: prüf erst die Quelle.`

Score false cutoffs, WAIT behavior and speculative cancellation.

### C — self-correction and semantic revision

- `Nimm Qwen drei ... nein, Qwen dreieinhalb vier B.`
- `Setz das auf morgen ... nein, übermorgen.`
- `Ich meinte TTS, nicht ASR.`

A speculative branch created from the first phrase must be cancelled or corrected without committing stale content.

### D — German names, numbers, dates and technical vocabulary

Include at least:

- dates such as `29. August 2026`;
- decimal values and units;
- filenames/identifiers such as `VoiceSessionCapsule`, `GRID10`, `Qwen3.5-4B`, `UnifiedDB`;
- mixed German/English technical phrases;
- locally relevant names only when the user supplies/authorizes them.

Score ASR exactness and TTS pronunciation separately.

### E — barge-in while Frankenstein speaks

Interrupt at multiple phases:

1. during first TTS chunk;
2. mid-sentence;
3. near sentence end;
4. during a tool-related explanation;
5. with a short backchannel that should **not** necessarily cancel the whole turn;
6. with a clear takeover such as `Stopp`, `Nein`, or a new request.

Measure `barge_in_detected -> playback_stopped`, provider cancellation, discarded queued audio and durable heard-text hash.

### F — overlap/backchannel

Test user `mhm`, `ja`, `okay`, laughter/noise and brief overlap while Frank is speaking. The turn controller must distinguish supportive backchannels from real takeover rather than treating every user sound identically.

### G — memory/state continuity

Use a predeclared synthetic benchmark state, not private production memory. Ask about facts introduced earlier in the same controlled session and verify that the provider does not create a second state authority.

### H — tool candidate correctness

Use harmless deterministic mock tools. Score:

- correct tool selection;
- exact argument extraction;
- no invented completion before tool result;
- result integration into speech;
- cancellation behavior if the user interrupts before effect authorization.

The model proposes; Frankenstein's effect boundary remains authoritative.

### I — semantic close

Test natural closures (`Passt, danke`, `Das war's`, `Lass uns später weiterreden`) plus silence safety behavior. The system should not force another response when WAIT/CLOSE is appropriate.

### J — noise/echo/far-field

Repeat a subset with:

- fan/keyboard noise;
- speaker echo from Frankenstein's own output;
- increased microphone distance;
- moderate room reverberation;
- real two-channel own-output reference where available.

## 6. Component-specific measurements

### ASR

Report WER/CER on a pinned German corpus and a separate real-room set. Also report partial stability, endpoint-relative finalization latency, numbers/names/technical-token exactness, and correction behavior after partial hypotheses.

For streaming ASR candidates, sweep their latency/quality control instead of benchmarking one arbitrary setting. Example: Nemotron 3.5 Streaming exposes multiple right-context values; each setting is a distinct point on the Pareto frontier.

### Turn controller

Measure false cutoff and unnecessary wait separately. Do not collapse them into one accuracy number. Test acoustic VAD, two-channel EOT/FVAD, semantic partials and endpoint anticipation as independent signals feeding deterministic commit/cancel state logic.

### Dialogue model

Report TTFT, first-speakable-clause time, tokens/s, German naturalness, instruction/state adherence, tool exactness, memory correctness, verbosity and interruption responsiveness. A small shell receives no factual/effect authority merely because it is fast.

### TTS

Report TTFA, real-time factor, stable male identity, German intelligibility, names/numbers/technical pronunciation, chunk-boundary continuity, prosody/expression control, replay/duplication and cancellation. Record the exact first audible PCM point, not merely the time the model emitted a tensor.

## 7. Quality comparison

Use source-hidden/blind comparison where practical between:

- historical/current external Realtime reference;
- current local donor-compatible baseline;
- each local candidate.

Score at least:

1. semantic correctness;
2. conversational naturalness;
3. timing/turn-taking;
4. voice naturalness;
5. emotional/prosodic fit;
6. interruption recovery;
7. long-session consistency.

Do not let latency improvements buy a win by degrading German conversation quality.

## 8. Hard failures vs diagnostic metrics

Hard failures for LOCAL_SOLO evidence:

- any outbound model/ASR/TTS inference call;
- false durable commit of unheard output;
- provider directly bypasses EffectGate/equivalent authority;
- duplicate/replayed audio that changes what the user hears;
- identity/state split between provider and Frankenstein;
- model cannot coexist with the admitted local core resource envelope.

Diagnostic/optimization metrics are compared as a Pareto frontier. Absolute latency acceptance numbers remain provisional until the donor/reference and target hardware have been measured with the same receipt.

## 9. Candidate order for the next executable target run

Subject to hardware inventory and license/dependency audit:

### ASR

1. NVIDIA Nemotron 3.5 ASR Streaming 0.6B — sweep right-context;
2. Qwen3-ASR 0.6B;
3. Qwen3-ASR 1.7B if resources permit;
4. German Whisper Large-v3-Turbo donor-compatible baseline.

### Dialogue

1. **official Qwen3.5-4B local quantization/reference first**;
2. previously pinned Qwen3.5-4B abliterated Q4 as controlled variant;
3. smaller fast-shell candidate only under no-fact/no-effect policy;
4. Claude-distilled/other 4B challengers after the official baseline exists.

Reason: abliteration is an intervention on refusal/alignment behavior, not evidence of better German realtime dialogue. The official model is required to isolate any gain/regression.

### TTS

Initial quality/latency frontier to measure:

1. Qwen3-TTS 12Hz 0.6B;
2. Fun-CosyVoice3 0.5B;
3. Chatterbox Multilingual;
4. dots.tts MF/SOAR path if the target hardware can host the 2B stack;
5. MOSS-TTS-Realtime 1.7B where its dependency/hardware footprint fits;
6. NVIDIA MagpieTTS Multilingual 357M as a smaller stable-voice challenger;
7. Piper/Thorsten and/or MOSS-TTS-Nano only as low-resource/latency-floor challengers until German quality is proven.

## 10. Source-evidence warnings discovered in Deep Run 02

- Upstream latency figures are not portable across GPUs/runtimes and are not F2 results.
- MOSS-TTS-Realtime currently advertises 180 ms TTFB / 0.51 RTF on one L20 after warmup, but a public reproducibility issue notes the published fixture/script and aggregation details are insufficient to recreate the number exactly. Treat it as a hypothesis, not a benchmark truth.
- DualTurn endpointing's published model metadata is English-oriented. Its two-channel causal design is highly relevant, but German conversational endpoint quality must be falsified on our own audio.
- MagpieTTS v2607 supports German but removed zero-shot voice cloning; stable Frank acoustic identity may therefore require selecting/adapting a fixed supported voice rather than assuming cloning.
- dots.tts is a 2B system with strong upstream multilingual/streaming evidence; H100/H800-class latency numbers do not prove target portability.

## 11. Required persistence

Every executed run must persist:

- exact run JSONL receipt;
- generated summary from `t7_voice_receipt.py`;
- host inventory receipt;
- source/model revisions and hashes;
- dependency/runtime versions;
- resource measurements;
- raw metric table;
- negative results;
- listening-score provenance;
- continuation decision.

No missing receipt may be replaced with prose such as `worked well`.
