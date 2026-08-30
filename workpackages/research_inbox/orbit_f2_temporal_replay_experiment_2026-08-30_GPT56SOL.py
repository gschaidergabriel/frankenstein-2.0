from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ORBIT_ROOT = Path('/mnt/data/orbit-dev-extracted/orbit-dev')
sys.path.insert(0, str(ORBIT_ROOT))
from orbit.diagnostics.backtest import TimeSeriesSplitter

SCHEMA = 'FRANKENSTEIN2_ORBIT_DONOR_TEMPORAL_REPLAY_EXPERIMENT/v1'
SEEDS = list(range(1000, 1020))
QUANTILES = (0.05, 0.50, 0.95)

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())

def canonical_sha(obj) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return sha256_bytes(s.encode())

def qloss(y, qpred, q):
    e = y - qpred
    return np.mean(np.maximum(q * e, (q - 1.0) * e))

def interval_score(y, lo, hi, alpha=0.10):
    width = hi - lo
    below = y < lo
    above = y > hi
    score = width.copy()
    score[below] += 2.0 / alpha * (lo[below] - y[below])
    score[above] += 2.0 / alpha * (y[above] - hi[above])
    return float(np.mean(score))

def continuous_metrics(pred_df: pd.DataFrame) -> dict:
    y = pred_df.actual.to_numpy(float)
    p05 = pred_df.p05.to_numpy(float)
    p50 = pred_df.p50.to_numpy(float)
    p95 = pred_df.p95.to_numpy(float)
    return {
        'n': int(len(pred_df)),
        'mae_p50': float(np.mean(np.abs(y - p50))),
        'rmse_p50': float(np.sqrt(np.mean((y - p50) ** 2))),
        'coverage_90': float(np.mean((y >= p05) & (y <= p95))),
        'mean_interval_width_90': float(np.mean(p95 - p05)),
        'interval_score_90': interval_score(y, p05, p95, 0.10),
        'mean_pinball_05_50_95': float(np.mean([qloss(y,p05,.05), qloss(y,p50,.5), qloss(y,p95,.95)])),
    }

def ece_binary(y, p, bins=10):
    edges = np.linspace(0,1,bins+1)
    total = len(y); acc = 0.0
    for i in range(bins):
        m=(p>=edges[i])&(p<edges[i+1]) if i < bins-1 else (p>=edges[i])&(p<=edges[i+1])
        if np.any(m):
            acc += np.sum(m)/total * abs(np.mean(y[m])-np.mean(p[m]))
    return float(acc)

def binary_metrics(df):
    y=df.target.to_numpy(int); p=np.clip(df.prob.to_numpy(float),1e-9,1-1e-9)
    cls=(p>=.5).astype(int); correct=(cls==y)
    return {
        'n': int(len(y)), 'accuracy': float(np.mean(correct)),
        'wp803_hard_score_mean': float(np.mean(np.where(correct,1,-1))),
        'brier': float(np.mean((p-y)**2)),
        'log_loss': float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
        'ece_10bin': ece_binary(y,p,10),
        'mean_confidence': float(np.mean(np.maximum(p,1-p))),
    }

def fit_predict_point(model: str, train: pd.DataFrame, test: pd.DataFrame, *, ycol='y', date_col='time', period=None):
    y=train[ycol].to_numpy(float); h=len(test)
    if model == 'persistence': return np.repeat(y[-1], h)
    if model == 'ewma_a025':
        level=y[0]
        for v in y[1:]: level=.25*v+.75*level
        return np.repeat(level,h)
    if model == 'trend_event_index':
        x=np.arange(len(y),dtype=float); slope,intercept=np.polyfit(x,y,1)
        return intercept+slope*np.arange(len(y),len(y)+h,dtype=float)
    if model == 'trend_wall_clock':
        t0=pd.Timestamp(train[date_col].iloc[0])
        x=(pd.to_datetime(train[date_col])-t0).dt.total_seconds().to_numpy()/60.0
        xt=(pd.to_datetime(test[date_col])-t0).dt.total_seconds().to_numpy()/60.0
        slope,intercept=np.polyfit(x,y,1)
        return intercept+slope*xt
    if model == 'seasonal_naive':
        if period is None or period < 1 or len(y) < period: return np.repeat(y[-1],h)
        return np.array([y[len(y)-period+(j%period)] for j in range(h)],dtype=float)
    raise ValueError(model)

def training_one_step_residuals(model: str, train: pd.DataFrame, *, ycol='y', date_col='time', period=None):
    y=train[ycol].to_numpy(float); residuals=[]
    if model == 'persistence': return y[1:]-y[:-1]
    if model == 'ewma_a025':
        level=y[0]
        for i in range(1,len(y)):
            residuals.append(y[i]-level); level=.25*y[i]+.75*level
        return np.asarray(residuals)
    if model == 'seasonal_naive':
        return y[period:]-y[:-period] if period and len(y)>period else y[1:]-y[:-1]
    start=max(12, int(0.10*len(y)))
    if model == 'trend_event_index': x=np.arange(len(y),dtype=float)
    elif model == 'trend_wall_clock':
        t0=pd.Timestamp(train[date_col].iloc[0]); x=(pd.to_datetime(train[date_col])-t0).dt.total_seconds().to_numpy()/60.0
    else: raise ValueError(model)
    sx=np.cumsum(x); sy=np.cumsum(y); sxx=np.cumsum(x*x); sxy=np.cumsum(x*y)
    for i in range(start,len(y)):
        n=float(i); Sx=sx[i-1]; Sy=sy[i-1]; Sxx=sxx[i-1]; Sxy=sxy[i-1]; den=n*Sxx-Sx*Sx
        if abs(den)<1e-12: pred=Sy/n
        else:
            slope=(n*Sxy-Sx*Sy)/den; intercept=(Sy-slope*Sx)/n; pred=intercept+slope*x[i]
        residuals.append(y[i]-pred)
    return np.asarray(residuals,dtype=float)

def predict_quantiles(model, train, test, *, ycol='y', date_col='time', period=None):
    point=fit_predict_point(model,train,test,ycol=ycol,date_col=date_col,period=period)
    res=training_one_step_residuals(model,train,ycol=ycol,date_col=date_col,period=period)
    res=res[np.isfinite(res)]
    if len(res)<8: res=np.array([0.0])
    qs=np.quantile(res,QUANTILES)
    return point+qs[0],point+qs[1],point+qs[2]

def run_continuous(df, models, *, min_train_len, forecast_len, incremental_len, date_col='time', period=None, dataset_id='x'):
    splitter=TimeSeriesSplitter(df, min_train_len=min_train_len, forecast_len=forecast_len, incremental_len=incremental_len, window_type='expanding', date_col=date_col)
    rows=[]; split_meta=[]
    for tr,te,scheme,k in splitter.split():
        split_meta.append({'split_key':int(k),'train_start':str(scheme['train_period'][0]),'train_end':str(scheme['train_period'][1]),'test_start':str(scheme['test_period'][0]),'test_end':str(scheme['test_period'][1]),'train_rows':int(len(tr)),'test_rows':int(len(te))})
        for m in models:
            p05,p50,p95=predict_quantiles(m,tr,te,date_col=date_col,period=period)
            for j in range(len(te)):
                rows.append({'dataset_id':dataset_id,'split_key':int(k),'model':m,'time':str(te[date_col].iloc[j]),'actual':float(te.y.iloc[j]),'p05':float(p05[j]),'p50':float(p50[j]),'p95':float(p95[j])})
    out=pd.DataFrame(rows)
    return out,{m:continuous_metrics(out[out.model==m]) for m in models},split_meta

def make_regular(seed,n=360):
    rng=np.random.default_rng(seed); t=np.arange(n); eps=rng.normal(0,1.2,n); ar=np.zeros(n)
    for i in range(1,n): ar[i]=.62*ar[i-1]+eps[i]
    y=50+.028*t+3.8*np.sin(2*np.pi*t/24)+ar; shift=int(.64*n); y[shift:]+=7.5+.025*(t[shift:]-shift)
    for s in (int(.38*n),int(.77*n)): y[s:s+3]+=rng.normal(5.0,0.5,3)
    return pd.DataFrame({'time':pd.date_range('2026-01-01',periods=n,freq='5min'),'y':y})

def make_irregular(seed,n=320):
    rng=np.random.default_rng(seed); gaps=np.empty(n,dtype=int); cut=int(.58*n)
    gaps[:cut]=rng.integers(1,4,cut); gaps[cut:]=rng.integers(9,22,n-cut); elapsed=np.cumsum(gaps).astype(float)
    eps=rng.normal(0,1.0,n); ar=np.zeros(n)
    for i in range(1,n): ar[i]=.50*ar[i-1]+eps[i]
    y=15+.035*elapsed+1.8*np.sin(2*np.pi*elapsed/(24*60))+ar
    times=pd.Timestamp('2026-01-01')+pd.to_timedelta(elapsed,unit='m')
    return pd.DataFrame({'time':times,'y':y,'elapsed_min':elapsed,'gap_min':gaps})

def make_binary(seed,n=420):
    rng=np.random.default_rng(seed); state=np.zeros(n+1,dtype=int); state[0]=rng.integers(0,2); cut=int(.62*n)
    for t in range(n):
        stay=.86 if t<cut else .66
        state[t+1]=state[t] if rng.random()<stay else 1-state[t]
    return pd.DataFrame({'time':pd.date_range('2026-01-01',periods=n,freq='2min'),'current':state[:-1],'target':state[1:]})

def transition_prob(train,current):
    sub=train[train.current==current]
    return float((sub.target.sum()+1)/(len(sub)+2)) if len(sub) else .5

def run_binary(df, min_train_len=140, forecast_len=14, incremental_len=14):
    splitter=TimeSeriesSplitter(df,min_train_len=min_train_len,forecast_len=forecast_len,incremental_len=incremental_len,window_type='expanding',date_col='time')
    rows=[]
    for tr,te,scheme,k in splitter.split():
        global_p=float((tr.target.sum()+1)/(len(tr)+2))
        for _,r in te.iterrows():
            p=transition_prob(tr,int(r.current)); hard=.99 if p>=.5 else .01
            for model,prob in [('global_frequency',global_p),('calibrated_transition',p),('overconfident_same_decision',hard)]:
                rows.append({'split_key':int(k),'model':model,'time':str(r.time),'current':int(r.current),'target':int(r.target),'prob':float(prob)})
    out=pd.DataFrame(rows)
    return out,{m:binary_metrics(out[out.model==m]) for m in out.model.unique()}

def local_iclaims():
    p=ORBIT_ROOT/'examples/data/iclaims_example.csv'; df=pd.read_csv(p)
    df['time']=pd.to_datetime(df['week'],format='%m/%d/%y'); df['y']=np.log(df['claims'].astype(float))
    return df[['time','y']].sort_values('time').reset_index(drop=True)

def main():
    zip_path=Path('/mnt/data/orbit-dev.zip')
    source={'orbit_zip_sha256':sha256_file(zip_path),'orbit_backtest_py_sha256':sha256_file(ORBIT_ROOT/'orbit/diagnostics/backtest.py'),'orbit_metrics_py_sha256':sha256_file(ORBIT_ROOT/'orbit/diagnostics/metrics.py'),'orbit_root':str(ORBIT_ROOT),'f2_main_observed_before_experiment':'ccd6aa17cedba2481103161d34a861066c5da90b','authority_epoch_observed':'8.78'}
    config={'continuous_quantiles':list(QUANTILES),'splitter':'Orbit TimeSeriesSplitter expanding window; date_col period selection, discrete-index split semantics','uncertainty':'empirical one-step training residual quantiles; no future residuals used','continuous_models':['persistence','ewma_a025','trend_event_index','trend_wall_clock','seasonal_naive'],'binary_models':['global_frequency','calibrated_transition','overconfident_same_decision'],'synthetic_seeds':SEEDS,'classification':'RESEARCH_BENCHMARK_NOT_WORLD_TRUTH_NOT_RUNTIME_CREDIT'}
    results={}
    ic=local_iclaims(); _,met,splits=run_continuous(ic,['persistence','ewma_a025','trend_event_index','seasonal_naive'],min_train_len=156,forecast_len=8,incremental_len=8,period=52,dataset_id='orbit_iclaims_local')
    results['orbit_iclaims_local']={'data_sha256':canonical_sha(ic.assign(time=ic.time.astype(str)).to_dict('records')),'metrics':met,'n_splits':len(splits),'split_descriptor_sha256':canonical_sha(splits)}
    for name,maker,models,period,min_train,fl,inc in [('f2_regular_pulse_synth',make_regular,['persistence','ewma_a025','trend_event_index','seasonal_naive'],24,144,12,12),('f2_irregular_event_synth',make_irregular,['persistence','ewma_a025','trend_event_index','trend_wall_clock'],None,120,10,10)]:
        allp=[]; seed_metrics=[]; data_hashes=[]
        for seed in SEEDS:
            df=maker(seed); p,m,_=run_continuous(df,models,min_train_len=min_train,forecast_len=fl,incremental_len=inc,period=period,dataset_id=f'{name}:{seed}')
            allp.append(p); seed_metrics.append({'seed':seed,'metrics':m}); dh=df.copy(); dh['time']=dh.time.astype(str); data_hashes.append(canonical_sha(dh.to_dict('records')))
        pool=pd.concat(allp,ignore_index=True); pooled={m:continuous_metrics(pool[pool.model==m]) for m in models}
        results[name]={'pooled_metrics':pooled,'seed_count':len(SEEDS),'seed_metrics':seed_metrics,'data_sha256s':data_hashes}
    allb=[]; seedm=[]
    for seed in SEEDS:
        df=make_binary(seed); b,m=run_binary(df); b['dataset_id']=f'f2_discrete_transition_synth:{seed}'; allb.append(b); seedm.append({'seed':seed,'metrics':m})
    poolb=pd.concat(allb,ignore_index=True); pooledb={m:binary_metrics(poolb[poolb.model==m]) for m in poolb.model.unique()}
    results['f2_discrete_transition_synth']={'pooled_metrics':pooledb,'seed_count':len(SEEDS),'seed_metrics':seedm}
    from orbit.diagnostics.metrics import rmsse
    train=np.array([0.,1.,2.,3.]); test=np.array([10.,11.]); pred=test.copy()
    try:
        with np.errstate(all='ignore'): val=rmsse(test,pred,train)
        rmsse_result={'returned':None if not np.isfinite(val) else float(val),'is_finite':bool(np.isfinite(val))}
    except Exception as e: rmsse_result={'exception':type(e).__name__,'message':str(e)}
    results['orbit_rmsse_falsifier']={'input':{'train':train.tolist(),'test':test.tolist(),'prediction':pred.tolist()},'result':rmsse_result,'source_observation':'function indexes first non-zero from train_actual but then assigns train_actual = test_actual[first_nz:]'}
    irr=results['f2_irregular_event_synth']['pooled_metrics']; disc=results['f2_discrete_transition_synth']['pooled_metrics']; reg=results['f2_regular_pulse_synth']['pooled_metrics']; icm=results['orbit_iclaims_local']['metrics']
    findings={
      'H1_time_basis_matters':{'status':'SUPPORTED' if irr['trend_wall_clock']['mae_p50'] < irr['trend_event_index']['mae_p50'] else 'NOT_SUPPORTED','event_index_mae':irr['trend_event_index']['mae_p50'],'wall_clock_mae':irr['trend_wall_clock']['mae_p50'],'ratio_wall_over_event':irr['trend_wall_clock']['mae_p50']/irr['trend_event_index']['mae_p50']},
      'H2_hard_correct_incorrect_score_loses_calibration_information':{'status':'SUPPORTED' if abs(disc['calibrated_transition']['wp803_hard_score_mean']-disc['overconfident_same_decision']['wp803_hard_score_mean'])<1e-12 and disc['calibrated_transition']['brier'] < disc['overconfident_same_decision']['brier'] else 'NOT_SUPPORTED','hard_score_calibrated':disc['calibrated_transition']['wp803_hard_score_mean'],'hard_score_overconfident':disc['overconfident_same_decision']['wp803_hard_score_mean'],'brier_calibrated':disc['calibrated_transition']['brier'],'brier_overconfident':disc['overconfident_same_decision']['brier'],'logloss_calibrated':disc['calibrated_transition']['log_loss'],'logloss_overconfident':disc['overconfident_same_decision']['log_loss']},
      'H3_simple_temporal_baselines_can_add_value_over_persistence_on_some_targets':{'status':'MIXED','regular_best_mae_model':min(reg,key=lambda m:reg[m]['mae_p50']),'regular_metrics':{m:reg[m]['mae_p50'] for m in reg},'iclaims_best_mae_model':min(icm,key=lambda m:icm[m]['mae_p50']),'iclaims_metrics':{m:icm[m]['mae_p50'] for m in icm},'interpretation':'admission must be target-specific; no global claim that temporal models beat persistence'},
      'H4_orbit_rmsse_is_safe_for_f2_evidence':{'status':'FALSIFIED' if not results['orbit_rmsse_falsifier']['result'].get('is_finite',False) else 'NOT_FALSIFIED','reason':'perfect prediction falsifier does not yield finite 0 under the uploaded source path'}
    }
    artifact={'schema':SCHEMA,'source':source,'config':config,'results':results,'findings':findings}; artifact['artifact_sha256']=canonical_sha(artifact)
    out=Path('/mnt/data/ORBIT_F2_TEMPORAL_REPLAY_EXPERIMENT_2026-08-30_GPT56SOL.json'); out.write_text(json.dumps(artifact,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)); print(out)

if __name__=='__main__': main()
