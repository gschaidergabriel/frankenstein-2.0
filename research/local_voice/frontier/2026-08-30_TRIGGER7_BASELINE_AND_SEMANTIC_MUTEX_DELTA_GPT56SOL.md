# Trigger 7 — Baseline provenance + semantic claim mutex delta (GPT-5.6 Sol)

Date: 2026-08-30  
Trigger: exact user message `7`  
Scope: German-first LOCAL-SOLO voice research coordination and source/runtime-gate preparation.

## Why this delta exists

The moving Trigger-7 frontier already contains parallel source work on ASR, turn-taking, audio/AEC, TTS and C++/GGUF runtime. This run therefore did **not** start another competing model-family lane.

Two higher-value gaps were resolved instead:

1. the untouched Qwen3.5-4B local baseline needed an exact source/provenance pin before any abliterated comparison; and
2. the existing human-readable create-only claim convention was empirically insufficient to stop several workers from scheduling semantically identical VPS hardware objectives under different names.

## Delta A — untouched Qwen3.5-4B baseline pin

Canonical source result:

`research/local_voice/sources/T7_QWEN35_4B_UNMODIFIED_Q4_BASELINE_PIN_2026-08-30.json`

Pinned lineage:

- official post-trained base: `Qwen/Qwen3.5-4B@851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`
- preferred local GGUF quantization: `lmstudio-community/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q4_K_M.gguf`
- Q4_K_M SHA-256: `25082a7dd3776cc3c741c6347d3bd04523f05796607b3fbc32fa3a25dfa1418c`
- size: `2707513696` bytes

Important provenance boundary:

The base model is official Qwen. The selected GGUF is a **third-party community quantization** of that lineage and is not itself an official Qwen GGUF artifact.

Benchmark order is baseline-first:

1. untouched Qwen3.5-4B Q4_K_M;
2. controlled abliterated Qwen3.5-4B Q4-class challenger;
3. other distilled/abliterated challengers only after baseline.

No target download, local re-hash, inference or benchmark credit is granted yet.

## Delta B — semantic claim mutex

Preserved negative result:

`research/local_voice/negative_results/2026-08-30_T7_SEMANTIC_DUPLICATE_CLAIM_MUTEX_FAILURE.md`

Observed failure law:

```text
CREATE_ONLY_HUMAN_PATH != SEMANTIC_OBJECTIVE_MUTEX
DISTINCT_CLAIM_PATHS CAN STILL DUPLICATE THE SAME EXPERIMENT
QUEUED_WORKFLOW != EXECUTION_EVIDENCE
```

Implemented:

- `research/local_voice/SEMANTIC_CLAIM_MUTEX_V1.md`
- `research/local_voice/tools/t7_semantic_claim.py`
- `research/local_voice/tests/test_t7_semantic_claim.py`
- `research/local_voice/semantic_claims/`
- `research/local_voice/claims/README.md` now routes new material work through the semantic registry first.

The key is computed only from bounded canonical semantic fields:

- objective family;
- target surface;
- subject;
- evidence scope;
- generation.

Human wording, research IDs, worker/session identity and descriptions do not mint distinct semantic identities.

Unknown aliases fail closed.

### Evidence

Exact committed local/static falsifiers:

- 6 tests run;
- 6 PASS;
- stable whole-Frankenstein hardware semantic key:
  `ba79dcf8960e1f02859a664103d5ba3f63fa8da95855d2b077b3e5aa2e0bf9e3`.

Create-only negative probe:

- a second ordinary create attempt against the existing hardware semantic path was rejected by GitHub with HTTP 422;
- the existing semantic claim remained unchanged;
- this is useful create-only evidence but **not** a simultaneous two-writer race acceptance test.

Repository CI:

- run `33265697541`;
- job `99135255763` (`semantic-claim-falsifiers`);
- conclusion `success`.

Parallel adoption was subsequently observed: a Qwen3-TTS German 12Hz 0.6B-vs-1.7B A/B objective created a `T7_SEMANTIC_CLAIM/v1` record first and explicitly keeps runtime credit at zero until a real `clay-direct-dev` hardware/runtime receipt exists.

### Legacy hardware storm quarantine

The generation-1 whole-Frankenstein `clay-direct-dev` hardware inventory now maps to the single semantic key above and is marked:

`LEGACY_DUPLICATE_SET_QUARANTINED_NO_NEW_DISPATCH`

This does not cancel history or invent a winner. Existing legacy claims/runs remain evidence inputs to reconcile. Their number never counts as independent runtime replication.

## Current target-runtime boundary

A corrected self-hosted workflow exists in `gschaidergabriel/Dr.-Unterweger`:

`Trigger 7 VPS Hardware Roundtrip`

It is pinned to an exact F2 source/tool identity and is designed to execute `t7_hardware_inventory.py` **inside** the `clay-direct-dev` sandbox through a `[self-hosted, Linux, X64]` runner.

Latest observed corrected run in this run:

- run: `33265598243`
- state: `pending`
- conclusion: none
- jobs materialized at observation: `0`

Therefore:

- `clay-direct-dev` execution observed: **false**
- hardware receipt observed: **false**
- model download observed: **false**
- model runtime credit: **0**
- German E2E voice credit: **0**

The absence of a job/receipt is an execution-surface state, not a scientific negative about the hardware, model or voice architecture.

## Hypothesis / counterhypothesis

**Hypothesis:** semantic objective identity will reduce Trigger-7 fan-out and make scarce target-runtime evidence cleaner because workers route around already-owned experiments instead of expressing the same experiment under new names.

**Counterhypothesis:** source-level semantic keys alone are insufficient under true concurrent writers; without a live simultaneous create-only race test and execution-system concurrency binding, duplicate dispatch can still escape through pre-v1 workflows or badly classified semantic categories.

## Next exact gates

1. Do not dispatch another generation-1 hardware inventory objective.
2. Reconcile the already-existing hardware run set to a terminal result; prefer the corrected canonical roundtrip only if exact evidence supports it.
3. If a real `clay-direct-dev` receipt appears, compute whole-Frankenstein RAM/VRAM/disk headroom before downloading candidate models.
4. Quarantine-download the pinned untouched Qwen3.5-4B Q4_K_M, locally re-hash it, bind exact llama.cpp build/runtime identity, and run the untouched German baseline before any abliterated A/B comparison.
5. When safe and nonduplicative, run a true two-independent-writer semantic create-only race acceptance test; until then semantic mutex credit remains component/repository-CI level, not full concurrency acceptance.

## Evidence ceiling

`SOURCE_PINNED_PLUS_REPOSITORY_CI_COORDINATION_REPAIR_NO_TARGET_RUNTIME`

Nothing in this delta mints Trigger-4/V6 acceptance, whole Frankenstein acceptance, target-runtime model quality, German E2E voice acceptance, or EntityOS/HCU whole-runtime credit.
