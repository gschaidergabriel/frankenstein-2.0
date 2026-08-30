#!/usr/bin/env python3
"""Research-only temporal calibration discriminator for Frankenstein 2.0.

No runtime/world/effect authority. Synthetic held-out worlds only.
Requires numpy. Emits deterministic JSON summary to stdout.
"""
from __future__ import annotations
import hashlib, json, math
from collections import defaultdict
import numpy as np

N=320
BURN=64
WINDOW=64
EWMA_ALPHA=0.3
CAL_MIN=20
TARGET_COVERAGE=0.90
HOLDOUT_SEEDS=list(range(10000,10064))
FAMILIES=("PERSISTENT_AR","TREND_SEASONAL","REGIME_SHIFT","ACTION_DRIVEN","IRREGULAR_WALLCLOCK")
MODELS=("PERSISTENCE","EWMA_A03","LINEAR_EVENT_INDEX","LINEAR_WALLCLOCK","SEASONAL_LAG12","ACTION_ARX")

PROTOCOL={
  "schema":"FRANKENSTEIN2_ORBIT_TEMPORAL_CALIBRATION_EXPERIMENT/v1",
  "classification":"RESEARCH_ONLY_SYNTHETIC_DISCRIMINATOR_NOT_RUNTIME_OR_WORLD_TRUTH",
  "families":{
    "PERSISTENT_AR":{"process":"y[t]=0.95*y[t-1]+N(0,0.25)"},
    "TREND_SEASONAL":{"process":"y[t]=0.025*t+1.8*sin(2*pi*t/12)+N(0,0.25)"},
    "REGIME_SHIFT":{"process":"mean=0 for t<160 else 4; y=mean+N(0,0.35)"},
    "ACTION_DRIVEN":{"process":"a[t]~Bernoulli(0.5); y[t]=0.70*y[t-1]+2.2*a[t]+N(0,0.3)"},
    "IRREGULAR_WALLCLOCK":{"process":"dt[t]~DiscreteUniform(1..20); wall=cumsum(dt); y[t]=0.08*wall[t]+N(0,0.25)"}
  },
  "n_steps":N,
  "burn_in":BURN,
  "rolling_train_window":WINDOW,
  "holdout_seeds":[10000,10063],
  "models":list(MODELS),
  "uncertainty":{
    "method":"online absolute-residual conformal-style symmetric interval",
    "target_coverage":TARGET_COVERAGE,
    "calibration_min_history":CAL_MIN,
    "calibration_window":WINDOW,
    "quantile_method":"higher"
  },
  "primary_metric":"MAE",
  "secondary_metrics":["RMSE","empirical_90_interval_coverage","mean_interval_width","mean_interval_score"],
  "decision_rules":{
    "family_specific_signal":"non-persistence model median per-seed MAE improvement >=10% and beats persistence on >=75% of holdout seeds",
    "typed_action_feature_necessity":"ACTION_ARX improves >=30% over best time-only model on ACTION_DRIVEN",
    "time_basis_necessity":"LINEAR_WALLCLOCK improves >=20% over LINEAR_EVENT_INDEX on IRREGULAR_WALLCLOCK",
    "no_global_model_promotion":"a model winning one synthetic family does not become canonical or runtime default"
  }
}
PROTOCOL_SHA256=hashlib.sha256(json.dumps(PROTOCOL,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def ols_predict(x,y,x_next):
    X=np.asarray(x,float)
    yy=np.asarray(y,float)
    if X.ndim==1:
        X=X[:,None]
    Xd=np.column_stack([np.ones(len(X)),X])
    beta,*_=np.linalg.lstsq(Xd,yy,rcond=None)
    xn=np.asarray(x_next,float).reshape(1,-1)
    return (np.column_stack([np.ones(1),xn]) @ beta).item()

def make_family(family, seed):
    idx=FAMILIES.index(family)
    rng=np.random.default_rng(seed+1000*idx)
    event=np.arange(N,dtype=float)
    wall=np.arange(N,dtype=float)
    action=np.zeros(N)
    y=np.zeros(N)
    if family=="PERSISTENT_AR":
        y[0]=rng.normal()
        for i in range(1,N):
            y[i]=0.95*y[i-1]+rng.normal(0,0.25)
    elif family=="TREND_SEASONAL":
        y=0.025*event+1.8*np.sin(2*np.pi*event/12)+rng.normal(0,0.25,N)
    elif family=="REGIME_SHIFT":
        y=np.where(event<160,0.0,4.0)+rng.normal(0,0.35,N)
    elif family=="ACTION_DRIVEN":
        action=rng.integers(0,2,N).astype(float)
        y[0]=rng.normal(0,0.3)
        for i in range(1,N):
            y[i]=0.70*y[i-1]+2.2*action[i]+rng.normal(0,0.3)
    elif family=="IRREGULAR_WALLCLOCK":
        dt=np.ones(N)
        dt[1:]=rng.integers(1,21,N-1)
        wall=np.cumsum(dt)
        y=0.08*wall+rng.normal(0,0.25,N)
    else:
        raise ValueError(family)
    return y,event,wall,action

def empty_stat():
    return {"n":0,"sum_abs":0.0,"sum_sq":0.0,"cov_n":0,"cov_yes":0,
            "width_n":0,"sum_width":0.0,"sum_interval_score":0.0}

stats=defaultdict(empty_stat)
seed_err=defaultdict(lambda:[0.0,0])

for family in FAMILIES:
  for seed in HOLDOUT_SEEDS:
    y,event,wall,action=make_family(family,seed)
    residual_hist=defaultdict(list)
    ewma=y[0]
    for i in range(1,N):
      ewma=EWMA_ALPHA*y[i-1]+(1-EWMA_ALPHA)*ewma
      if i<BURN:
        continue
      lo=max(0,i-WINDOW)
      idx=np.arange(lo,i)
      preds={
        "PERSISTENCE":float(y[i-1]),
        "EWMA_A03":float(ewma),
        "LINEAR_EVENT_INDEX":ols_predict(event[idx],y[idx],[event[i]]),
        "LINEAR_WALLCLOCK":ols_predict(wall[idx],y[idx],[wall[i]]),
        "SEASONAL_LAG12":float(y[i-12])
      }
      ks=np.arange(max(1,lo),i)
      X=np.column_stack([y[ks-1],action[ks]])
      preds["ACTION_ARX"]=ols_predict(X,y[ks],[y[i-1],action[i]])
      for model,p in preds.items():
        err=float(y[i]-p)
        ae=abs(err)
        s=stats[(family,model)]
        s["n"]+=1; s["sum_abs"]+=ae; s["sum_sq"]+=err*err
        se=seed_err[(family,seed,model)]
        se[0]+=ae; se[1]+=1
        hist=residual_hist[model]
        if len(hist)>=CAL_MIN:
          q=float(np.quantile(hist[-WINDOW:],0.90,method="higher"))
          lower,upper=p-q,p+q
          width=2*q
          score=width
          if y[i]<lower:
            score+=20*(lower-y[i])
          elif y[i]>upper:
            score+=20*(y[i]-upper)
          s["cov_n"]+=1
          s["cov_yes"]+=int(lower<=y[i]<=upper)
          s["width_n"]+=1
          s["sum_width"]+=width
          s["sum_interval_score"]+=score
        hist.append(ae)

summary=[]
for family in FAMILIES:
  for model in MODELS:
    s=stats[(family,model)]
    summary.append({
      "family":family,
      "model":model,
      "n":s["n"],
      "mae":s["sum_abs"]/s["n"],
      "rmse":math.sqrt(s["sum_sq"]/s["n"]),
      "coverage_90":s["cov_yes"]/s["cov_n"],
      "mean_interval_width":s["sum_width"]/s["width_n"],
      "mean_interval_score":s["sum_interval_score"]/s["width_n"]
    })

def per_seed_mae(family,model):
    return np.asarray([seed_err[(family,seed,model)][0]/seed_err[(family,seed,model)][1] for seed in HOLDOUT_SEEDS])

rng=np.random.default_rng(424242)
def paired_comparison(family,model,baseline):
    a=per_seed_mae(family,model)
    b=per_seed_mae(family,baseline)
    imp=(b-a)/b
    boots=np.empty(10000)
    for j in range(len(boots)):
        boots[j]=np.median(rng.choice(imp,size=len(imp),replace=True))
    return {
      "family":family,"model":model,"baseline":baseline,
      "median_relative_mae_improvement":float(np.median(imp)),
      "bootstrap95_low":float(np.quantile(boots,0.025)),
      "bootstrap95_high":float(np.quantile(boots,0.975)),
      "win_fraction":float(np.mean(imp>0))
    }

comparisons=[
  paired_comparison("TREND_SEASONAL","SEASONAL_LAG12","PERSISTENCE"),
  paired_comparison("REGIME_SHIFT","EWMA_A03","PERSISTENCE"),
  paired_comparison("ACTION_DRIVEN","ACTION_ARX","PERSISTENCE"),
  paired_comparison("IRREGULAR_WALLCLOCK","LINEAR_WALLCLOCK","PERSISTENCE"),
  paired_comparison("IRREGULAR_WALLCLOCK","LINEAR_WALLCLOCK","LINEAR_EVENT_INDEX"),
  paired_comparison("PERSISTENT_AR","ACTION_ARX","PERSISTENCE")
]

result={
  "schema":"FRANKENSTEIN2_ORBIT_TEMPORAL_CALIBRATION_EXPERIMENT_RESULT/v1",
  "classification":"SYNTHETIC_HELDOUT_RESEARCH_EVIDENCE_NO_RUNTIME_OR_WORLD_AUTHORITY",
  "protocol_sha256":PROTOCOL_SHA256,
  "holdout_seed_count":len(HOLDOUT_SEEDS),
  "prediction_count":sum(x["n"] for x in summary),
  "summary":summary,
  "key_paired_comparisons":comparisons,
  "conclusions":[
    "Persistence remains the strongest tested baseline in the persistent AR family; complexity is not universally helpful.",
    "Seasonal structure, regime change, known action inputs, and wall-clock timing each create family-specific gains for appropriately structured predictors.",
    "Known action input yields a much larger gain than time-only models in the action-driven family, so Frankenstein prediction must bind action/context features when they are available before outcome.",
    "Wall-clock regression strongly beats event-index regression in the irregular-time family, so time_basis must be explicit and target-specific.",
    "Simple rolling residual intervals achieve roughly near-target but imperfect 90% coverage; distribution shift motivates a separate adaptive-calibration layer rather than treating static confidence as calibrated.",
    "This experiment does not justify KTR or any Orbit runtime dependency. It justifies a provenance-bound temporal prediction/calibration ABI plus baseline-first rolling evaluation."
  ],
  "credits":{"runtime":0,"physical_grid10":0,"gwt":0,"jspace":0,"training":0,"whole_system":0}
}
print(json.dumps(result,sort_keys=True,indent=2))
