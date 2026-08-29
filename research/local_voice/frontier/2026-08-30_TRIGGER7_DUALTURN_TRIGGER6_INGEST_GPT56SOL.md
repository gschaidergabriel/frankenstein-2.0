# Trigger 7 ingest — Trigger 6 DualTurn German E5 build candidate

Date: 2026-08-30
Trigger: 7
Upstream research delta: `R6-20260830-DUALTURN-GERMAN-TURNTAKING-GPT56SOL-01`
Observed F2 source commit: `ad16eeb81dfc7ba89506c0a488f7c89673038315`
Evidence boundary: E5_BUILD_CANDIDATE_PLAN_ONLY
Runtime credit: 0
F2 benchmark credit: 0
Integration credit: 0

## Ingest decision

Trigger 7 accepts the Trigger-6 result as a **build-falsifier candidate**, not as evidence that DualTurn improves German Frankenstein turn-taking.

The upstream delta correctly matches the existing Trigger-7 need for a separate perception-only EOT/FVAD signal and preserves authority: DualTurn may emit a perception candidate; it must not own dialogue state, GWT authority, canonical memory, effect authority or conversation completion.

## Exact upstream source identities carried forward

- paper: `arXiv:2603.08216v1`
- official repo: `anyreachai/dualturn@2d0db21e767b953f5017c1cc697928b54161d645`
- endpointing repository observed revision: `anyreach-ai/dualturn-endpointing@c3860ed`

Before executable credit, Trigger 4 still must resolve the full immutable Hugging Face artifact revision and artifact SHA-256. Mutable `main` is not sufficient.

## High-information target ablation

The accepted next discriminator is exactly the three-way German comparison proposed by Trigger 6:

```text
B0 = current Frankenstein turn-taking baseline
B1 = mono/fallback DualTurn path
C1 = true dual-channel DualTurn path with own-output/reference channel
```

Run on `clay-direct-dev` with identical German scenarios and Trigger-7 causal receipts.

Minimum scenario families:

- ordinary end-of-turn;
- German mid-sentence pause;
- hesitation/restart;
- short backchannel (`ja`, `mhm`, `genau`) while Frankenstein is speaking;
- user interruption/barge-in;
- own-speaker echo / reference audio;
- overlap where user continues after a short apparent endpoint;
- semantic close versus temporary silence.

Measure at least:

- false endpoint rate;
- missed endpoint rate;
- endpoint decision latency;
- barge-in detect -> playback stop latency;
- unwanted assistant starts during user continuation;
- WAIT correctness;
- cancellation correctness and unheard-output commit errors.

## Promotion law

```text
E5_PLAN_ONLY != E3_REPRODUCED
SOURCE_PIN != ARTIFACT_PIN
DUAL_CHANNEL_ARCHITECTURE_VALUE != GERMAN_BENEFIT
PERCEPTION_SIGNAL != DIALOGUE_AUTHORITY
```

Promote further only if C1 materially improves the German turn-taking Pareto frontier without increasing false interruptions or violating the voice ABI. A B1/C1 regression is a first-class negative result and should retire or narrow the candidate.

## Routing

Trigger 6 already produced a Trigger-4 handoff. Trigger 7 does not create a duplicate build lane. It consumes the eventual Trigger-4 measured result and updates the voice frontier from actual target evidence.
