from __future__ import annotations

import gc
import json
import statistics
import time
from importlib.metadata import version
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Link, SpanContext, SpanKind, TraceFlags, TraceState

TRACE_FLAGS = TraceFlags(TraceFlags.SAMPLED)
RESOURCE = Resource.create({"service.name": "frankenstein2-trigger6-fixture"})
CARRIER_CONTEXT = SpanContext(trace_id=int("1" * 32, 16), span_id=int("2" * 16, 16), is_remote=False, trace_flags=TRACE_FLAGS, trace_state=TraceState())
TARGET_CONTEXT = SpanContext(trace_id=int("a" * 32, 16), span_id=int("b" * 16, 16), is_remote=True, trace_flags=TRACE_FLAGS, trace_state=TraceState())
LINK = Link(TARGET_CONTEXT)
START_NS = 1_800_000_000_000_000_000
END_NS = START_NS + 1_000_000

FULL_ATTRS = {
    "openinference.span.kind":"EVALUATOR","evaluations.0.evaluation.name":"f2.gwt_reentry_uptake_binding","evaluations.0.evaluation.label":"bound_evidence_only","evaluations.0.evaluation.annotator_kind":"CODE","evaluations.0.evaluation.identifier":"f2-trigger6-openinference-projection-v0",
    "f2.schema":"FRANKENSTEIN2_GWT_REENTRY_UPTAKE_BINDING/v1","f2.classification":"DERIVED_BINDING_WP507_UPTAKE_AUTHORITY_ONLY_NOT_NEW_UPTAKE_OR_RUNTIME_EVIDENCE","f2.binding_id":"binding-001","f2.canonical_reentry_key":"1"*64,"f2.reentry_witness_sha256":"2"*64,"f2.uptake_receipt_id":"uptake-001","f2.uptake_receipt_sha256":"3"*64,"f2.broadcast_id":"broadcast-001","f2.broadcast_generation":4,"f2.broadcast_sha256":"4"*64,"f2.recipient_cell_id":"G7","f2.delivery_status":"DELIVERED","f2.uptake_status":"UPTAKEN","f2.downstream_ref":"receipt://downstream/001","f2.downstream_sha256":"5"*64,"f2.binding_status":"WP507_UPTAKEN_BOUND","f2.causal_influence_claim":"NOT_ESTABLISHED_BY_BINDING","f2.truth_authority":"NONE","f2.effect_authority":"NONE"}
RECEIPT_REF="workpackages/receipts/F2-WP-508_G4_BROADCAST_BUILDER_LINEAGE_MAIN_CI_33244896581.json"; RECEIPT_SHA="6"*64
THIN_ATTRS={"openinference.span.kind":"EVALUATOR","evaluations.0.evaluation.name":"f2.gwt_reentry_uptake_binding","evaluations.0.evaluation.label":"bound_evidence_only","evaluations.0.evaluation.annotator_kind":"CODE","evaluations.0.evaluation.identifier":"f2-trigger6-openinference-thin-ref-v1","f2.receipt_ref":RECEIPT_REF,"f2.receipt_sha256":RECEIPT_SHA,"f2.broadcast_id":"broadcast-001","f2.broadcast_generation":4,"f2.recipient_cell_id":"G7","f2.binding_status":"WP507_UPTAKEN_BOUND","f2.uptake_status":"UPTAKEN","f2.causal_influence_claim":"NOT_ESTABLISHED_BY_BINDING"}
FORBIDDEN_TOKENS=("TOP-SECRET","sk-test-never-export-01","prompt","output","api_key")

def make_span(attrs):
    return ReadableSpan(name="f2 evidence receipt projection",context=CARRIER_CONTEXT,parent=None,resource=RESOURCE,attributes=attrs,links=(LINK,),kind=SpanKind.INTERNAL,start_time=START_NS,end_time=END_NS)
def encode(attrs): return encode_spans((make_span(attrs),)).SerializeToString()
def encode_prebuilt(span): return encode_spans((span,)).SerializeToString()
def percentile(values,q): values=sorted(values); return values[int(round((len(values)-1)*q))]
def stats(values): return {"p50_ns":percentile(values,.50),"p95_ns":percentile(values,.95),"p99_ns":percentile(values,.99),"mean_ns":round(statistics.fmean(values),3)}
def bench(func_a,func_b,iterations=30000,warmup=3000):
    for _ in range(warmup): func_a(); func_b()
    a=[]; b=[]; enabled=gc.isenabled(); gc.disable()
    try:
        for i in range(iterations):
            if i%2==0:
                t0=time.perf_counter_ns(); func_a(); t1=time.perf_counter_ns(); t2=time.perf_counter_ns(); func_b(); t3=time.perf_counter_ns()
            else:
                t2=time.perf_counter_ns(); func_b(); t3=time.perf_counter_ns(); t0=time.perf_counter_ns(); func_a(); t1=time.perf_counter_ns()
            a.append(t1-t0); b.append(t3-t2)
    finally:
        if enabled: gc.enable()
    return stats(a),stats(b)

def main():
    full_span=make_span(FULL_ATTRS); thin_span=make_span(THIN_ATTRS); full_wire=encode_prebuilt(full_span); thin_wire=encode_prebuilt(thin_span)
    full_req=encode_spans((full_span,)); thin_req=encode_spans((thin_span,)); full_pb_span=full_req.resource_spans[0].scope_spans[0].spans[0]; thin_pb_span=thin_req.resource_spans[0].scope_spans[0].spans[0]
    assert len(full_pb_span.links)==1 and len(thin_pb_span.links)==1
    assert full_pb_span.links[0].trace_id==TARGET_CONTEXT.trace_id.to_bytes(16,'big'); assert thin_pb_span.links[0].span_id==TARGET_CONTEXT.span_id.to_bytes(8,'big')
    full_text=full_wire.decode('latin1',errors='ignore'); thin_text=thin_wire.decode('latin1',errors='ignore')
    for token in FORBIDDEN_TOKENS: assert token not in full_text and token not in thin_text
    full_build,thin_build=bench(lambda:encode(FULL_ATTRS),lambda:encode(THIN_ATTRS)); full_pre,thin_pre=bench(lambda:encode_prebuilt(full_span),lambda:encode_prebuilt(thin_span))
    result={"schema":"FRANKENSTEIN2_TRIGGER6_OPENINFERENCE_E4_OTLP_PROTOBUF_ABLATION/v1","research_id":"R6-SEED-011","claim_target":"E4_F2_ABLATION_OPENINFERENCE_OTLP_PROTOBUF_V1","scope":"LOCAL_OPENTELEMETRY_SDK_OTLP_PROTOBUF_SERIALIZATION_ONLY_NO_COLLECTOR_NO_NETWORK_NO_VPS_NO_F2_TARGET_RUNTIME","environment":{"opentelemetry_api":version("opentelemetry-api"),"opentelemetry_sdk":version("opentelemetry-sdk"),"opentelemetry_proto":version("opentelemetry-proto"),"opentelemetry_exporter_otlp_proto_common":version("opentelemetry-exporter-otlp-proto-common")},"wire_bytes":{"full":len(full_wire),"thin":len(thin_wire),"thin_vs_full_ratio":round(len(thin_wire)/len(full_wire),6),"savings_bytes":len(full_wire)-len(thin_wire)},"span_attributes":{"full":len(FULL_ATTRS),"thin":len(THIN_ATTRS)},"posthoc_link_count":{"full":len(full_pb_span.links),"thin":len(thin_pb_span.links)},"latency_build_plus_encode":{"full":full_build,"thin":thin_build,"ratios":{"p50":round(thin_build['p50_ns']/full_build['p50_ns'],6),"p95":round(thin_build['p95_ns']/full_build['p95_ns'],6),"p99":round(thin_build['p99_ns']/full_build['p99_ns'],6),"mean":round(thin_build['mean_ns']/full_build['mean_ns'],6)}},"latency_encode_prebuilt_span":{"full":full_pre,"thin":thin_pre,"ratios":{"p50":round(thin_pre['p50_ns']/full_pre['p50_ns'],6),"p95":round(thin_pre['p95_ns']/full_pre['p95_ns'],6),"p99":round(thin_pre['p99_ns']/full_pre['p99_ns'],6),"mean":round(thin_pre['mean_ns']/full_pre['mean_ns'],6)}},"semantic_invariants":{"exactly_one_posthoc_link_preserved":True,"observer_ids_are_only_link_context":True,"sensitive_content_absent_from_wire":True,"canonical_receipt_ref_digest_present_in_thin_attributes":True,"causal_influence_not_established":True},"result":"THIN_REF_DOMINATES_FULL_FIELD_AT_LOCAL_OTLP_PROTOBUF_SCOPE" if len(thin_wire)<len(full_wire) and thin_build['p50_ns']<full_build['p50_ns'] else "NO_DOMINANCE","architecture_credit":0,"runtime_credit":0,"gwt_causal_credit":0,"effect_credit":0,"whole_system_credit":0}
    print(json.dumps(result,sort_keys=True,indent=2))
if __name__=="__main__": main()
