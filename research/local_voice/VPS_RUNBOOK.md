# Trigger 7 — VPS Local Voice Research Runbook

This runbook is for the dedicated `research/local-voice-continuous` lane.

It is intentionally separate from canonical Frankenstein user state. Model caches and experiment workdirs are rebuildable research artifacts.

## 0. Preconditions

Before every epoch:

1. refresh this branch and read `RESEARCH_LEDGER.md`, `MODEL_REGISTRY.json`, `BENCHMARK_PROTOCOL.md`;
2. record current F2 main SHA and research branch SHA;
3. inspect currently running voice research processes to avoid duplicate model loads/downloads;
4. record disk/RAM/CPU/GPU capability;
5. fail closed if available disk is insufficient for the chosen candidate plus working space;
6. never write secrets into git or receipts.

## 1. Research cache

Use a dedicated rebuildable cache chosen by the execution environment, for example:

```bash
export F2_VOICE_RESEARCH_ROOT="${F2_VOICE_RESEARCH_ROOT:-$HOME/.cache/frankenstein-2.0/voice-research}"
mkdir -p "$F2_VOICE_RESEARCH_ROOT"/{models,repos,venvs,runs,tmp}
```

This path must not be the canonical Frankenstein durable user-state location.

## 2. Environment receipt

Before acquisition or benchmarks archive at least:

```bash
uname -a
python3 --version || true
nvidia-smi || true
lscpu || true
free -h || true
df -h "$F2_VOICE_RESEARCH_ROOT" || true
```

Record CUDA/ROCm/Metal/CPU backend versions when relevant.

## 3. Acquisition pattern

Prefer exact revisions rather than floating `main`.

Hugging Face example:

```bash
hf download ORG/MODEL \
  --revision EXACT_REVISION \
  --local-dir "$F2_VOICE_RESEARCH_ROOT/models/CANDIDATE_ID"
```

GitHub runtime example:

```bash
git clone https://github.com/ORG/REPO.git "$F2_VOICE_RESEARCH_ROOT/repos/REPO"
cd "$F2_VOICE_RESEARCH_ROOT/repos/REPO"
git checkout EXACT_COMMIT
```

After acquisition record:

```bash
find MODEL_OR_REPO_PATH -type f -print0 | sort -z | xargs -0 sha256sum > artifact.sha256
```

For very large model trees, a manifest may retain upstream blob/content identities plus selected local hashes if hashing cost is explicitly recorded; never claim a hash was measured when it was not.

## 4. First acquisition queue

Start with the highest-information smaller candidates before large duplex models.

### ASR

1. `Qwen/Qwen3-ASR-0.6B-hf`
2. current `faster-whisper` baseline with multilingual large-v3-turbo class checkpoint
3. `ggml-org/whisper.cpp` runtime with an appropriate multilingual model

Only then, if the 0.6B result leaves a quality gap worth paying for:

4. `Qwen/Qwen3-ASR-1.7B-hf`

### TTS

1. `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` or the best locally redistributable 0.6B German checkpoint confirmed by its current model card
2. Piper German latency baseline
3. 1.7B Qwen3-TTS challenger if resources permit

### Duplex / native speech research

Only after capability/disk checks:

- `BayLing-Models/BayLing-Duplex` plus required GLM-4-Voice tokenizer/decoder;
- `kyutai-labs/moshi` compatible checkpoint/runtime;
- any newer open speech-to-speech candidate discovered by the epoch.

Large native speech models are not allowed to starve the smaller modular benchmark lane.

## 5. Component-first benchmark sequence

For each new model:

```text
LOAD/WARMUP
-> smoke inference
-> deterministic sample set
-> latency microbench
-> quality sample set
-> resource trace
-> 10+ minute stability test where practical
-> ACCEPT_FOR_INTEGRATION | REJECT | RETEST_WITH_CONFIG
```

Do not wire an unbenchmarked model into the full Frankenstein voice loop merely because the demo works.

## 6. Whole-loop research sequence

For a candidate stack:

```text
MIC/AUDIO FIXTURE
-> VAD/ENDPOINTING
-> ASR
-> FRANKENSTEIN LOCAL DIALOGUE + MEMORY/TOOLS
-> TTS
-> AUDIO SINK
```

Then test:

- streaming partials;
- first token and first audio;
- actual barge-in cancellation;
- tool-call result re-entry;
- no duplicate response;
- 5+ minute spontaneous German conversation;
- restart continuity;
- no external inference network.

Synthetic audio fixtures may be used on VPS for most tests, but physical microphone/speaker/echo-cancellation acceptance remains a local-machine gate.

## 7. Continuous research loop

A persistent Trigger 7 worker may execute:

```text
REFRESH
-> WATCH arXiv/HF/GitHub
-> DIFF against ledger/registry
-> SELECT highest-information candidate
-> ACQUIRE if needed
-> BENCH
-> FALSIFY
-> UPDATE ledger + registry + raw receipts
-> PROMOTE candidate only through bounded PR
-> SELECT next experiment
-> repeat
```

The loop should back off when there is no new upstream evidence instead of hammering services. "Continuous" means the research program has no terminal completion state; it does not justify uncontrolled network polling or duplicate downloads.

## 8. Research receipts

Recommended path:

```text
research/local_voice/runs/<YYYYMMDD>/<run_id>/
  run.json
  environment.txt
  model_manifest.json
  metrics.json
  latency.csv
  transcript_results.jsonl
  tts_samples_manifest.json
  resource_trace.csv
  conclusions.md
```

Large generated audio/model binaries remain outside git; commit manifests, hashes, small representative evidence where licensing/privacy permits, and exact reproduction instructions.

## 9. Failure discipline

Record negative results such as:

- model cannot fit;
- model loads but misses latency budget;
- German quality regression;
- streaming path is fake/batched;
- barge-in cancellation leaves queued speech;
- echo causes self-transcription;
- tool syntax unreliable;
- long-session memory leak;
- license prevents distribution;
- model requires external service despite local-looking wrapper.

A negative result is valuable research evidence and should prevent repeated dead ends.

## 10. Promotion

Research can propose, not self-authorize, product replacement.

Promotion PR must include:

- champion/challenger table;
- same-hardware metrics;
- exact revisions;
- known regressions;
- offline inference proof;
- integration tests proving Frankenstein state/memory/tools remain shared authority.
