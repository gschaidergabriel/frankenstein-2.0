# Orbit -> Frankenstein 2.0: Deep Research + Experiment Worker Packet

Classification: **RESEARCH ROUTING ONLY — NOT MUTATION AUTHORITY, NOT WORLD TRUTH, NOT RUNTIME CREDIT**

Owner direction: run the experiment, deepen the research, and route workers all artifacts/knowledge needed to continue safely.

## 0. Exact experiment/source snapshot

- F2 main observed before the research branch: `fb293b754fd17127be6c5c9ddadbb4abfb5256b6`
- Research branch: `research/orbit-temporal-calibration-20260830`
- Routing issue: `#661`
- Duplicate routing issue `#662` was closed as duplicate and carries no claim.
- Experiment protocol SHA-256: `c585219b64102d0473fc7b1a284690843216e200af0f624d9169407fd977d7ab`
- Holdout seeds: 64 (`10000..10063`)
- Total one-step predictions scored: **491,520**
- Experiment source: `workpackages/research_inbox/ORBIT_TEMPORAL_CALIBRATION_EXPERIMENT_V1.py`
- Experiment result: `workpackages/research_inbox/ORBIT_TEMPORAL_CALIBRATION_EXPERIMENT_RESULT_2026-08-30.json`

Before implementation, workers MUST refresh current main and current granular workpackage evidence. The commit above is an experiment snapshot, not continuing authority.

## 1. Current Frankenstein facts that constrain transfer

### F2-WP-202

`src/frankenstein2/prediction_contract.py` is deliberately deterministic. It freezes an explicitly supplied expected projection plus basis fingerprint and later computes a type-sensitive residual against an explicit observation. The source explicitly states that it does **not** predict missing facts, decide actions, read durable state, invoke a model, or promote a prediction to truth.

**Transfer consequence:** do not replace or weaken PredictionContract/v1. Any probabilistic forecast must be a separate candidate/envelope layer that can bind to the existing deterministic contract.

### F2-WP-302

At the experiment snapshot, `workpackages/active/F2-WP-302.json` is generation 2, state `ACCEPTED`, terminal scope limited to repository-hosted component CI. It preserves PredictionResidual identity/generation/digest fences, UNKNOWN semantics, contradiction preservation, and candidate-only authority. Runtime, physical GRID10 and whole-system credit remain zero.

**Transfer consequence:** calibrated surprise must not bypass the existing familiarity/prediction provenance fences or turn retrieval familiarity into truth.

### F2-WP-803

At the experiment snapshot, `workpackages/active/F2-WP-803.json` is generation 2, state `ACCEPTED`, terminal scope `PREDECLARED_RUN_ADMISSION_BOUND_WORLD_MODEL_PREDICTION_REPOSITORY_HOSTED_COMPONENT_CI_ONLY`. Runtime/VPS/GRID10/GWT/J-Space/provider/training/effect/completion/whole-system credit remain zero.

The current world-model benchmark is intentionally simple: categorical next-observation outcomes are `CORRECT`, `INCORRECT`, or `ABSTAINED`, scored `+1/-1/0`, with strong evaluator-side run/fixture provenance.

**Transfer consequence:** the next useful discriminator is not a rewrite of WP803 provenance. It is testing whether a provenance-bound probability distribution adds information beyond `+1/-1/0` without leaking evaluator-only state.

### F2-WP-800

The held-out cognitive micro-world separates evaluator-only state from public SUT observation. That boundary is essential and must survive any probability/calibration extension.

## 2. External research synthesis

### Orbit

Orbit is a Bayesian time-series forecasting package supporting ETS, LGT, DLT and KTR. Its value here is primarily methodological:

1. initialize/fit/predict separation and model/estimator separation;
2. rolling/expanding time-series backtesting;
3. prediction intervals / probabilistic forecasts;
4. prediction decomposition;
5. KTR time-varying coefficients as a later hypothesis, not a first dependency.

Primary/official references:

- Orbit repository: https://github.com/uber/orbit
- Orbit paper: Edwin Ng et al., *Orbit: Probabilistic Forecast with Exponential Smoothing*, arXiv:2004.08492, https://arxiv.org/abs/2004.08492
- Orbit backtesting docs: https://uber.github.io/orbit/tutorials/backtest.html
- KTR tutorial: https://orbit-ml.readthedocs.io/en/stable/tutorials/ktr2.html

### Forecast evaluation

Rolling-origin out-of-sample evaluation is the appropriate baseline when temporal ordering matters. Tashman (2000) explicitly discusses rolling origins, rolling windows, recalibration and multiple test periods. Orbit's BackTester implements expanding and rolling windows.

Reference:
- Leonard J. Tashman, *Out-of-sample tests of forecasting accuracy: an analysis and review*, International Journal of Forecasting 16(4), 2000, DOI 10.1016/S0169-2070(00)00065-0.

### Probabilistic calibration

Gneiting, Balabdaoui & Raftery distinguish calibration from sharpness and recommend proper scoring rules for probabilistic forecast evaluation. A single scalar confidence is not itself calibration evidence.

Reference:
- Gneiting, Balabdaoui & Raftery, *Probabilistic Forecasts, Calibration and Sharpness*, JRSS B 69(2), 2007, DOI 10.1111/j.1467-9868.2007.00587.x.

### Distribution shift / adaptive intervals

Static residual intervals can lose coverage under changing distributions. Adaptive Conformal Inference and follow-on time-series work explicitly target online distribution shift / temporal dependency.

References:
- Gibbs & Candès, *Adaptive Conformal Inference Under Distribution Shift*, NeurIPS 2021, arXiv:2106.00170.
- Zaffran et al., *Adaptive Conformal Predictions for Time Series*, ICML 2022, PMLR 162.

## 3. Experiment design

This was a **synthetic held-out discriminator**, not a runtime or whole-system test.

Five families were fixed before the final holdout run:

1. `PERSISTENT_AR`: strong persistence / low-value complexity control.
2. `TREND_SEASONAL`: fixed seasonal structure.
3. `REGIME_SHIFT`: abrupt distribution change.
4. `ACTION_DRIVEN`: next state depends on an action known before outcome.
5. `IRREGULAR_WALLCLOCK`: process evolves by elapsed wall-clock time while event spacing is irregular.

Six fixed predictors:

- `PERSISTENCE`
- `EWMA_A03`
- `LINEAR_EVENT_INDEX`
- `LINEAR_WALLCLOCK`
- `SEASONAL_LAG12`
- `ACTION_ARX`

Evaluation:

- rolling one-step prediction;
- 64-step training window;
- primary metric: MAE;
- secondary: RMSE, empirical 90% interval coverage, mean interval width, interval score;
- online past-residual symmetric interval, never using future residuals;
- paired per-seed improvement vs baseline;
- 10,000 bootstrap resamples for median improvement intervals.

## 4. Held-out results

### Negative control: persistence really can be best

`PERSISTENT_AR`:
- Persistence MAE: **0.20000**
- best tested non-persistence comparison (`ACTION_ARX`) median relative improvement: **-0.94%**
- bootstrap 95% interval: **[-1.52%, -0.53%]**
- it beat persistence on only **28.1%** of seeds.

**Interpretation:** complexity is not universally useful. This is a direct falsifier against “add KTR because it is more sophisticated.”

### Seasonal structure

`TREND_SEASONAL`:
- Persistence MAE: **0.63937**
- Seasonal lag-12 MAE: **0.37875**
- median relative MAE improvement: **40.94%**
- bootstrap 95% interval: **[40.50%, 41.41%]**
- win fraction: **100%**.

**Interpretation:** explicit temporal structure can be useful, but the correct inductive bias matters more than generic complexity.

### Regime shift

`REGIME_SHIFT`:
- Persistence MAE: **0.40597**
- EWMA MAE: **0.34198**
- median relative improvement: **15.50%**
- bootstrap 95% interval: **[14.88%, 16.24%]**
- win fraction: **100%**.

**Interpretation:** short-memory adaptation can outperform persistence under a shift. This supports adaptive/recent evidence weighting as a testable candidate, not a truth rule.

### Known action is more important than time-only forecasting

`ACTION_DRIVEN`:
- Persistence MAE: **1.11156**
- ACTION_ARX MAE: **0.24654**
- median relative improvement: **77.75%**
- bootstrap 95% interval: **[77.32%, 78.29%]**
- win fraction: **100%**.

**Interpretation:** if the action is known before outcome, a prediction ABI that ignores it can be structurally wrong. `action_id/action_digest` and other pre-outcome typed context must be explicit predictor inputs/provenance, never smuggled in post hoc.

### Time basis is an architectural field, not a formatting detail

`IRREGULAR_WALLCLOCK`:
- Persistence MAE: **0.88200**
- Linear wall-clock MAE: **0.20509**
- median improvement vs persistence: **76.88%**
- bootstrap 95% interval: **[76.32%, 77.11%]**
- win fraction: **100%**.

More importantly:
- wall-clock regression vs event-index regression median improvement: **81.54%**
- bootstrap 95% interval: **[80.63%, 83.09%]**
- win fraction: **100%**.

**Interpretation:** `time_basis` must be explicit and target-specific. Wall-clock, pulse index, episode step and causal event index are not interchangeable.

### Calibration result

For the best model in each synthetic family, empirical nominal-90% interval coverage was approximately **0.8905–0.8935**. That is close but systematically below 0.90.

**Interpretation:** the simple rolling residual interval is useful as a baseline but not sufficient evidence of calibrated uncertainty, especially under shifts. A separate adaptive-calibration experiment is justified; “model confidence” alone is not.

## 5. What the experiment supports vs does not support

### Supported at synthetic-research scope

1. A provenance-bound temporal prediction/calibration ABI is worth building/evaluating.
2. `time_basis` is required.
3. pre-outcome action/context features can dominate pure temporal history and must be explicitly bound.
4. rolling-origin evaluation with persistence baseline should be mandatory for temporal claims.
5. uncertainty should be evaluated by empirical calibration/proper scores, not self-reported confidence.
6. simple adaptive baselines can beat persistence in some regimes.

### NOT supported

1. KTR as a runtime dependency.
2. Orbit as a second state/truth system.
3. regression coefficients as causal proof.
4. probabilistic predictions as EffectGate/completion authority.
5. runtime/physical GRID10/GWT/J-Space/training/whole-system credit.
6. a claim that synthetic worlds imply real Frankenstein gains.

## 6. Worker routing

### Route A — Stage 8 / WP803 successor falsifier (highest priority)

Goal: test whether a **probability-bearing next-observation candidate** provides measurable calibration information beyond current `+1/-1/0` while preserving all G2 provenance fences.

Required design properties:

- exact public ObservationView only;
- exact action binding before evaluator step;
- exact policy/generation/state digest;
- probability mass over public candidate identities plus explicit UNKNOWN/ABSTAIN if admitted;
- canonical ordering and exact sum/domain validation;
- no hidden node, transition, score, fixture ancestry or evaluator fields in candidate;
- run/admission binding remains evaluator-side;
- evaluator computes Brier/log or another declared proper score only after world step;
- current discrete CORRECT/INCORRECT/ABSTAINED remains available as a compatibility measurement.

Mandatory negative tests:

- probability vector created after observation of outcome;
- post-hoc candidate relabel;
- probabilities not summing to admitted mass;
- duplicate candidate identity;
- hidden fixture field leak;
- stale observation/action/run/policy generation;
- probability assigned to an unavailable/private observation identity;
- forged calibration receipt;
- high-confidence wrong vs low-confidence wrong must be distinguishable by proper score while both remain `INCORRECT` in the existing categorical view.

Do **not** reopen or weaken WP803 G2 merely because a richer score is useful. Use a successor/falsifier scope only after refreshing current main and overlap.

### Route B — WP202 envelope, not rewrite

Goal: define the smallest optional `ProbabilisticPredictionEnvelope` (name provisional) that binds:

- prediction identity/generation;
- basis fingerprint;
- target identity;
- horizon;
- `time_basis`;
- explicit feature/provenance digest;
- optional action/context digest known before outcome;
- distribution/quantile representation;
- predictor identity/config digest;
- classification `CANDIDATE_NOT_WORLD_TRUTH`.

The existing PredictionContract/v1 remains deterministic and unchanged. The envelope may reference/freeze the point projection that WP202 later compares.

Mandatory falsifiers: wrong basis, wrong horizon, wrong time basis, post-outcome feature mutation, feature digest mismatch, NaN/Inf probability/quantile, non-monotone quantiles, probability-domain violation.

### Route C — WP302 calibrated-surprise review

Do not redefine current prediction error from raw mismatch into surprise directly.

Candidate formula should keep these distinct:

- `raw_residual`
- `normalized_residual`
- `calibration_violation`
- `predictive_surprise`

`predictive_surprise` must consume a provenance-bound calibration measurement. If calibration evidence is absent/stale, output UNKNOWN rather than manufacturing confidence.

Mandatory discriminator: same raw error under wide vs narrow predeclared intervals must yield different surprise, while neither interval becomes world truth.

### Route D — temporal replay harness over real F2 evidence

Synthetic evidence is only a discriminator. The next serious experiment should use actual repository/run-package sequences where temporal ordering and feature availability are reconstructable without hidden-future leakage.

Minimum requirements:

- predeclare target and horizon;
- exact source/run/package digests;
- temporal ordering preserved;
- only features available before target observation;
- persistence baseline always present;
- target-specific `time_basis`;
- rolling-origin evaluation;
- multiple test periods;
- negative family where persistence should remain competitive;
- result scoped as replay/evaluation evidence only.

If real replay shows no stable positive skill over persistence, STOP runtime-model work and retain only the evaluation/calibration infrastructure.

### Route E — KTR / complex model gate (deferred)

Do not add Pyro/CmdStan/Orbit runtime dependency yet.

Admit a KTR/DLT/other complex predictor experiment only if:

1. real F2 replay shows repeatable temporal signal;
2. simple baselines leave material residual structure;
3. time/action/context provenance ABI is stable;
4. complexity is compared against persistence/EWMA/simple regression on identical folds;
5. gain survives held-out runs and cost/latency accounting.

KTR coefficients remain model-internal descriptive contributions, never causal authority.

### Route F — future WP505 / perception / realtime consumers

Only after calibration is demonstrated may later workers test calibrated surprise as an input to:

- adaptive compute allocation;
- re-observe/ASK/WAIT candidates;
- perception refresh priority;
- latency/resource forecasting.

No direct effect path from forecast to real action is authorized by this packet.

## 7. Serious counterhypotheses workers must preserve

H0-A: real Frankenstein transitions are too event-driven/nonstationary for temporal predictors to beat persistence reliably.

H0-B: apparent temporal skill disappears when action/context leakage is removed.

H0-C: wall-clock/event-index choice can manufacture apparent skill; target-specific time basis is necessary.

H0-D: calibration intervals become stale under distribution shift and create false confidence.

H0-E: model complexity/cost exceeds actionable information gain.

H0-F: a probability layer creates a new self-attested authority channel unless evaluator-side provenance is stricter than candidate construction.

## 8. Acceptance ladder for follow-on work

- Source/unit/CI acceptance may establish only repository component behavior.
- Integration/runtime claims require their own exact evidence.
- No lower-level PASS grants physical GRID10, GWT/J-Space, provider/model, training, effect, completion or whole-system credit.
- Preserve negative results.
- Refresh current main and exact active claim before opening any workpackage.

## 9. Recommended next exact action

**Highest-information next step:** build a research-only WP803 successor falsifier for probability-bearing public predictions + proper scoring, and in parallel design a real-F2 temporal replay extractor. Do not add KTR yet.

The decision gate after real replay is binary:

- positive persistence-relative skill with correct provenance -> test simple calibrated temporal models;
- no stable skill -> keep calibration/evaluation infrastructure, stop runtime forecast complexity.
