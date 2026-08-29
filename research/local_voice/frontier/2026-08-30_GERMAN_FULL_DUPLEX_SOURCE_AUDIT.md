# Trigger 7 — German Native Full-Duplex Source Audit

Date: 2026-08-30
Claim: `T7-DUPLEX-001/E2_GERMAN_FULL_DUPLEX_SOURCE_AUDIT`
Evidence class: SOURCE_AUDIT_ONLY
Runtime credit: 0
German E2E benchmark credit: 0
Trigger-4 acceptance credit: 0

## Question

Which current native/full-duplex speech systems are more than architecture references for Frankenstein 2.0's German-first local voice target?

## Result

**No audited native/full-duplex candidate currently earns German production-voice credit from primary-source evidence alone.**

This is a useful negative result, not a claim that German can never work. It means the current upstream evidence does not satisfy Trigger-7's German-first production gate. The modular German pipeline remains the production-leading hypothesis while native duplex remains a parallel experimental/donor lane.

## Candidate matrix

| Candidate | Native/full duplex | Public runnable surface | Explicit speech-language evidence | German status | Trigger-7 disposition |
|---|---|---|---|---|---|
| BayLing-Duplex | YES; simultaneous listen/speak, internal turn-taking and interruption | YES; public GitHub + downloadable checkpoint/tokenizer/decoder; GPU recommended for realtime | Primary repo/paper documents duplex behavior but the audited sources do not explicitly establish German speech support | **GERMAN_UNVERIFIED** | Best audited native-duplex **German falsifier candidate**, not production credit |
| Lychee-FD | YES; native end-to-end full-duplex | YES; Apache-2.0 code/model + Docker/custom vLLM | Hugging Face metadata explicitly lists `zh`, `en`; checkpoint is ~25.6 GB and model card reports 13B BF16 | **GERMAN_NOT_SUPPORTED_BY_DECLARED_LANGUAGE_METADATA** | Architecture/reference only for German production until new evidence/model appears |
| MiniCPM-o 4.5 | YES; realtime full-modal/full-duplex local stack available | YES; local Docker/llama.cpp-omni paths reported | Official documentation describes optimized realtime **Chinese-English bilingual** speech interaction | **GERMAN_NOT_ESTABLISHED_FOR_SPEECH** | Architecture/runtime reference; no German production credit |
| DuplexSLA | YES; speech-language-action model with synchronized action/tool channel | NO current released inference/checkpoint in audited repo; README says inference code/checkpoints/bench are coming soon | No German production evidence established | **GERMAN_UNVERIFIED + NOT_CURRENTLY_RUNNABLE_FROM_RELEASED_MODEL** | High-value architecture donor for tool/action timing, no local component credit |
| JoyAI-Talker | YES; thinker-talker/duplex research | No pinned public runnable stack established in this audit | Primary paper reports multilingual TTS corpus, but audited evaluations/support claims do not establish German conversational duplex quality | **GERMAN_UNVERIFIED** | Research/reference only; footprint also conflicts with near-term resident-local bias |

## Exact source pins available from the audit

- BayLing-Duplex GitHub main observed: `41669ac04bbcbfaf5b1be3a2cc563e4b3752d041`
- Lychee-FD GitHub main observed: `7bb1068c59b578e1f8e65fb762cd26708c14cc6d`
- DuplexSLA GitHub main observed: `c17e5fc8b91cf6448bb7715e6574a5864682b4c3`
- BayLing paper: arXiv `2606.14528`
- Lychee-FD paper/model metadata: arXiv `2607.06540`, Hugging Face `HIT-TMG/Lychee-FD`
- DuplexSLA paper: arXiv `2605.20755`

Primary URLs:
- https://github.com/BayLing-Models/BayLing-Duplex
- https://huggingface.co/HIT-TMG/Lychee-FD
- https://github.com/HITsz-TMG/Lychee-FD
- https://github.com/hyzhang24/DuplexSLA

## Architecture consequences

1. Do **not** replace Lane A merely because a model is called full-duplex.
2. Keep the German modular stack as the production-leading hypothesis: streaming ASR -> semantic/two-channel endpoint control -> provider-neutral Frankenstein cognition -> streaming cancellable TTS.
3. Keep native duplex as an experimental lane because it may eventually simplify turn-taking/backchannel/interruption timing.
4. BayLing-Duplex is the highest-information current native-duplex German falsifier among the audited runnable candidates because its public stack directly models interruption and turn-taking. It still needs a real German local test and resource-fit gate.
5. DuplexSLA's synchronized speech/language/action clock is especially relevant as an architecture donor for Frankenstein tools/effects, but unreleased inference/checkpoints prevent runnable credit.
6. Lychee-FD and MiniCPM-o 4.5 are currently negative evidence for the German production gate: their declared speech-language surfaces are Chinese/English rather than German.

## Next discriminator

After the independently claimed `T7-SYS-002` VPS hardware/resource receipt lands:

- if resident headroom can plausibly host BayLing-Duplex plus the rest of Frankenstein, quarantine-pin it and run a **German-only smoke falsifier** with interruption/mid-sentence pause/backchannel cases;
- otherwise preserve it as architecture/reference evidence and spend runtime budget on the modular German stack instead.

The test must not grant production credit from English/Chinese demos or upstream turn-taking metrics.

## Evidence law

```text
NATIVE_DUPLEX != GERMAN_CAPABLE
MULTILINGUAL != GERMAN_DUPLEX_PROVEN
UPSTREAM_DEMO != F2_GERMAN_E2E
PUBLIC_WEIGHTS != TARGET_HARDWARE_FIT
INTERRUPTION_SCORE != FRANKENSTEIN_BARGE_IN_ACCEPTANCE
ARCHITECTURE_VALUE != PRODUCTION_VOICE_CREDIT
GERMAN_UNVERIFIED -> NO_PRODUCTION_CREDIT
```
