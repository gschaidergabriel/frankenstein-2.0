# Trigger 7 — Local Dialogue Frontier, 2026-08-29

Purpose: seed the dialogue-model tournament without prematurely locking Frankenstein to one model family.

## Current high-information challengers

### Gemma 4 E2B-it

Sources:

- Hugging Face: `google/gemma-4-E2B-it`
- paper: arXiv `2607.02770`

Why test:

- small/on-device-oriented member of current Gemma 4 family;
- multilingual support reported by the model card;
- native system role and function-calling claims;
- current local ecosystem includes llama.cpp-compatible quantizations.

Risks/questions:

- BF16 source checkpoint is still large; use a pinned quantized local build for constrained hardware;
- spoken German quality and concise conversational behavior are not implied by general benchmarks;
- verify tool calling and KV/prompt reuse in the exact selected runtime revision.

Status: `DIALOGUE_CHALLENGER`.

### Current Qwen 3.x / 3.5 small instruct class

Why test:

- strong multilingual/conversational lineage;
- multiple current GGUF/local-runtime variants;
- likely attractive latency/quality trade-off in 4B-ish class.

Important falsifier:

- `llama.cpp` has had model/template-specific tool-call parsing failures and multi-turn/cache regressions on some Qwen3.5 configurations/releases. Never infer reliability from a single successful text chat. Pin model + llama.cpp revision and run the full F2 tool schema repeatedly.

Status: `DIALOGUE_CHALLENGER_WITH_RUNTIME_FALSIFIERS`.

### Gemma 4 larger challengers

E4B/12B/26B-A4B classes may be evaluated when hardware permits if E2B leaves a meaningful quality gap.

Do not download larger models solely because they score higher on text benchmarks. Require a hypothesis that the extra quality is worth the added first-token latency and memory footprint in live voice.

## Dialogue-specific benchmark rule

The local model is selected for **spoken Frankenstein**, not for generic benchmark prestige.

A winning candidate must demonstrate:

- natural German back-and-forth;
- low first-token latency;
- correct short answers without over-explaining;
- ability to become detailed when asked;
- reliable tool-call emission under the actual F2 schema;
- cancellation after barge-in;
- context/state projection without independent memory authority;
- no pathological long thinking pause in ordinary conversation;
- stable behavior across 50+ rapid turns;
- acceptable tokens/sec while ASR and TTS are simultaneously resident/active.

## Architecture hypothesis

For perceived human-likeness, latency may be improved more by **pipeline scheduling** than by replacing the LLM alone:

- start LLM as soon as transcript confidence is sufficient where safe;
- stream tokens immediately;
- split output into speakable semantic chunks;
- begin TTS on the first stable clause while the LLM continues;
- cancel both generation and synthesis immediately on barge-in;
- maintain a small spoken-response policy distinct from long-form text style;
- optionally route trivial acknowledgements through a very fast local path while keeping the same Frankenstein state authority.

These are research hypotheses. Measure semantic errors caused by premature speculative start before promotion.
