from __future__ import annotations
import gc, importlib.util, json, statistics, time, tracemalloc
from pathlib import Path

spec=importlib.util.spec_from_file_location('r6_e3', Path('/mnt/data/r6_openinference_e3_falsifier.py'))
mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)

source={
 'schema':'FRANKENSTEIN2_GWT_REENTRY_UPTAKE_BINDING/v1',
 'classification':'DERIVED_BINDING_WP507_UPTAKE_AUTHORITY_ONLY_NOT_NEW_UPTAKE_OR_RUNTIME_EVIDENCE',
 'binding_id':'binding-001','canonical_reentry_key':'1'*64,'reentry_witness_sha256':'2'*64,
 'uptake_receipt_id':'uptake-001','uptake_receipt_sha256':'3'*64,'broadcast_id':'broadcast-001',
 'broadcast_generation':4,'broadcast_sha256':'4'*64,'recipient_cell_id':'G7','delivery_status':'DELIVERED',
 'uptake_status':'UPTAKEN','downstream_ref':'receipt://downstream/001','downstream_sha256':'5'*64,
 'binding_status':'WP507_UPTAKEN_BOUND','causal_influence_claim':'NOT_ESTABLISHED_BY_BINDING',
 'truth_authority':'NONE','effect_authority':'NONE',
 'prompt':'TOP-SECRET PROMPT 9c8e9a','output':'TOP-SECRET OUTPUT c4fb7d','api_key':'sk-test-never-export-01'}
TRACE='a'*32; SPAN='b'*16; RECEIPT_REF='workpackages/receipts/F2-WP-508_G4_BROADCAST_BUILDER_LINEAGE_MAIN_CI_33244896581.json'; RECEIPT_SHA='6'*64


def native_encode():
    mod.validate_source(source)
    d={k:source.get(k) for k in mod.CANONICAL_FIELDS if source.get(k) is not None}
    return mod.stable_json(d)


def full_encode():
    p=mod.project_to_openinference(source,observer_enabled=True,target_trace_id=TRACE,target_span_id=SPAN); assert p
    return mod.stable_json(p)


def thin_project(*,trace_id=TRACE, span_id=SPAN):
    mod._require_text('receipt_ref', RECEIPT_REF); mod._require_sha('receipt_sha256', RECEIPT_SHA)
    mod._require_text('broadcast_id', source['broadcast_id']); mod._require_text('recipient_cell_id', source['recipient_cell_id'])
    mod._require_text('binding_status', source['binding_status']); mod._require_text('uptake_status', source['uptake_status'])
    if type(source['broadcast_generation']) is not int or source['broadcast_generation'] < 0: raise ValueError('bad generation')
    if not mod.TRACE_ID_RE.fullmatch(trace_id) or not mod.SPAN_ID_RE.fullmatch(span_id): raise ValueError('bad observer id')
    if source['truth_authority']!='NONE' or source['effect_authority']!='NONE' or source['causal_influence_claim']!='NOT_ESTABLISHED_BY_BINDING': raise ValueError('authority leak')
    return {
      'name':'f2 evidence receipt projection',
      'links':[{'trace_id':trace_id,'span_id':span_id}],
      'attributes':{
        'openinference.span.kind':'EVALUATOR',
        'evaluations.0.evaluation.name':'f2.gwt_reentry_uptake_binding',
        'evaluations.0.evaluation.label':'bound_evidence_only',
        'evaluations.0.evaluation.annotator_kind':'CODE',
        'evaluations.0.evaluation.identifier':'f2-trigger6-openinference-thin-ref-v1',
        'f2.receipt_ref':RECEIPT_REF,
        'f2.receipt_sha256':RECEIPT_SHA,
        'f2.broadcast_id':source['broadcast_id'],
        'f2.broadcast_generation':source['broadcast_generation'],
        'f2.recipient_cell_id':source['recipient_cell_id'],
        'f2.binding_status':source['binding_status'],
        'f2.uptake_status':source['uptake_status'],
        'f2.causal_influence_claim':'NOT_ESTABLISHED_BY_BINDING'
      },
      'observer_semantics':'CORRELATION_ONLY_NOT_CAUSAL_OR_TRUTH_AUTHORITY'}


def thin_encode(): return mod.stable_json(thin_project())


def percentile(v,q): v=sorted(v); return v[int(round((len(v)-1)*q))]
def stats(v):
    vv=sorted(v); return {'p50_ns':percentile(vv,.5),'p95_ns':percentile(vv,.95),'p99_ns':percentile(vv,.99),'mean_ns':round(statistics.fmean(vv),3)}
def bench(iterations=30000,warmup=3000):
    for _ in range(warmup): native_encode(); full_encode(); thin_encode()
    arr={'native':[],'full':[],'thin':[]}; funcs={'native':native_encode,'full':full_encode,'thin':thin_encode}; order=['native','full','thin']
    ge=gc.isenabled(); gc.disable()
    try:
      for i in range(iterations):
        rotated=order[i%3:]+order[:i%3]
        for name in rotated:
          t0=time.perf_counter_ns(); funcs[name](); t1=time.perf_counter_ns(); arr[name].append(t1-t0)
    finally:
      if ge: gc.enable()
    return {k:stats(v) for k,v in arr.items()}
def mem(func,iterations=5000):
    gc.collect(); tracemalloc.start(); b,_=tracemalloc.get_traced_memory(); checksum=0
    for _ in range(iterations): checksum ^= len(func())
    cur,peak=tracemalloc.get_traced_memory(); tracemalloc.stop(); return {'peak_bytes_over_baseline':peak-b,'current_bytes_over_baseline':cur-b,'checksum':checksum}

native=native_encode(); full=full_encode(); thin=thin_encode(); timing=bench(); memory={'native':mem(native_encode),'full':mem(full_encode),'thin':mem(thin_encode)}
p1=thin_project(trace_id='a'*32,span_id='b'*16); p2=thin_project(trace_id='c'*32,span_id='d'*16)
assert {k:v for k,v in p1['attributes'].items() if k.startswith('f2.')} == {k:v for k,v in p2['attributes'].items() if k.startswith('f2.')}
serialized=mod.stable_json(p1)
for forbidden in ('TOP-SECRET','sk-test-never-export-01','prompt','output','api_key'): assert forbidden not in serialized
assert p1['attributes']['f2.receipt_ref']==RECEIPT_REF and p1['attributes']['f2.receipt_sha256']==RECEIPT_SHA

result={
 'schema':'FRANKENSTEIN2_TRIGGER6_OPENINFERENCE_E4_THIN_REF_ABLATION/v1','research_id':'R6-SEED-011','claim_target':'E4_F2_ABLATION_OPENINFERENCE_THIN_RECEIPT_REF_V1',
 'scope':'LOCAL_PYTHON_JSON_DESIGN_ABLATION_NOT_OTLP_NOT_COLLECTOR_NOT_VPS_NOT_F2_TARGET_RUNTIME',
 'payload_bytes':{'native':len(native.encode()),'full':len(full.encode()),'thin':len(thin.encode()),'thin_vs_native_ratio':round(len(thin.encode())/len(native.encode()),6),'thin_vs_full_ratio':round(len(thin.encode())/len(full.encode()),6)},
 'latency':timing,
 'latency_ratios':{'thin_vs_native_p50':round(timing['thin']['p50_ns']/timing['native']['p50_ns'],6),'thin_vs_full_p50':round(timing['thin']['p50_ns']/timing['full']['p50_ns'],6),'thin_vs_native_p95':round(timing['thin']['p95_ns']/timing['native']['p95_ns'],6),'thin_vs_full_p95':round(timing['thin']['p95_ns']/timing['full']['p95_ns'],6)},
 'tracemalloc':memory,
 'semantic_invariants':{'receipt_ref_digest_preserved':True,'observer_ids_non_authoritative':True,'sensitive_content_absent':True,'causal_influence_not_established':True},
 'result':'THIN_REF_DOMINATES_FULL_FIELD_AT_LOCAL_JSON_SCOPE' if len(thin)<len(full) and timing['thin']['p50_ns']<timing['full']['p50_ns'] else 'NO_DOMINANCE',
 'architecture_credit':0,'runtime_credit':0,'gwt_causal_credit':0,'effect_credit':0,'whole_system_credit':0}
print(json.dumps(result,sort_keys=True,indent=2))
