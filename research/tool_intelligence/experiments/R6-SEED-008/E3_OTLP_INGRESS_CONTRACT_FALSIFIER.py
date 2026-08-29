#!/usr/bin/env python3
import hashlib, json, resource, statistics, time

ALLOWED = {
    "/v1/logs": "resourceLogs",
    "/v1/metrics": "resourceMetrics",
    "/v1/traces": "resourceSpans",
}
F2_KEYS = ("f2.causal_id", "f2.generation", "f2.effect_id")
SENSITIVE_PREFIXES = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "tool_parameters",
)

class Reject(ValueError): pass

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def attr_map(attrs):
    out = {}
    for a in attrs or []:
        if not isinstance(a, dict) or not isinstance(a.get("key"), str) or not isinstance(a.get("value"), dict):
            raise Reject("MALFORMED_ATTRIBUTE")
        v = a["value"]
        vals = [v.get(k) for k in ("stringValue","intValue","doubleValue","boolValue") if k in v]
        if len(vals) != 1:
            raise Reject("AMBIGUOUS_ATTRIBUTE_VALUE")
        out[a["key"]] = vals[0]
    return out

def iter_records(endpoint, doc):
    root = ALLOWED.get(endpoint)
    if not root: raise Reject("UNSUPPORTED_ENDPOINT")
    if not isinstance(doc, dict) or root not in doc or not isinstance(doc[root], list):
        raise Reject("WRONG_OR_MISSING_SIGNAL_ROOT")
    if endpoint == "/v1/logs":
        for rg in doc[root]:
            for sg in rg.get("scopeLogs", []):
                for rec in sg.get("logRecords", []): yield rec
    elif endpoint == "/v1/traces":
        for rg in doc[root]:
            for ss in rg.get("scopeSpans", []):
                for rec in ss.get("spans", []): yield rec
    else:
        for rg in doc[root]:
            for sm in rg.get("scopeMetrics", []):
                for rec in sm.get("metrics", []): yield rec

def normalize(endpoint, raw):
    try: doc = json.loads(raw)
    except Exception as e: raise Reject("MALFORMED_JSON") from e
    records = list(iter_records(endpoint, doc))
    if not records: raise Reject("EMPTY_SIGNAL")
    out=[]
    for rec in records:
        attrs = attr_map(rec.get("attributes", []))
        present = [k in attrs for k in F2_KEYS]
        if any(present) and not all(present): raise Reject("PARTIAL_F2_IDENTITY")
        explicit = all(present)
        if explicit:
            if not isinstance(attrs["f2.causal_id"], str) or not attrs["f2.causal_id"]: raise Reject("INVALID_CAUSAL_ID")
            if not isinstance(attrs["f2.effect_id"], str) or not attrs["f2.effect_id"]: raise Reject("INVALID_EFFECT_ID")
            try: gen=int(attrs["f2.generation"])
            except Exception as e: raise Reject("INVALID_GENERATION") from e
            if gen < 0: raise Reject("INVALID_GENERATION")
        else: gen=None
        redacted=[]; kept={}
        for k,v in attrs.items():
            if any(k == p or k.startswith(p + ".") for p in SENSITIVE_PREFIXES): redacted.append(k)
            else: kept[k]=v
        provenance = {
            "endpoint": endpoint,
            "traceId": rec.get("traceId"),
            "spanId": rec.get("spanId"),
            "timeUnixNano": rec.get("timeUnixNano"),
            "attributes": kept,
        }
        event_id = hashlib.sha256(canon(provenance).encode()).hexdigest()
        out.append({
            "ingress_event_sha256": event_id,
            "f2_identity_status": "EXPLICIT" if explicit else "UNKNOWN_MISSING_EXACT_BINDING",
            "causal_id": attrs.get("f2.causal_id") if explicit else None,
            "generation": gen,
            "effect_id": attrs.get("f2.effect_id") if explicit else None,
            "upstream_tool_call_id": attrs.get("gen_ai.tool.call.id"),
            "attributes": kept,
            "redacted_keys": sorted(redacted),
        })
    return out

def logs(records): return json.dumps({"resourceLogs":[{"scopeLogs":[{"logRecords":records}]}]})
def traces(records): return json.dumps({"resourceSpans":[{"scopeSpans":[{"spans":records}]}]})
def metrics(records): return json.dumps({"resourceMetrics":[{"scopeMetrics":[{"metrics":records}]}]})
def A(k,v):
    key = "boolValue" if isinstance(v,bool) else "intValue" if isinstance(v,int) else "doubleValue" if isinstance(v,float) else "stringValue"
    return {"key":k,"value":{key:v}}

def expect_reject(fn, code):
    try: fn()
    except Reject as e:
        assert str(e)==code, (str(e),code); return
    raise AssertionError(f"expected {code}")

def run():
    tests=[]
    def T(name, f): f(); tests.append(name)

    base_attrs=[A("event.name","tool_result"), A("gen_ai.tool.call.id","call-7"), A("session.id","s-1")]
    T("unknown_ids_are_not_synthesized", lambda: (
        (lambda x: (x[0]["f2_identity_status"]=="UNKNOWN_MISSING_EXACT_BINDING" and x[0]["causal_id"] is None and x[0]["effect_id"] is None and x[0]["upstream_tool_call_id"]=="call-7") or (_ for _ in ()).throw(AssertionError()))(normalize("/v1/logs", logs([{"timeUnixNano":"10","attributes":base_attrs}])))
    ))
    T("explicit_identity_preserved", lambda: (
        (lambda x: (x[0]["causal_id"]=="c-1" and x[0]["generation"]==3 and x[0]["effect_id"]=="e-1") or (_ for _ in ()).throw(AssertionError()))(normalize("/v1/traces", traces([{"traceId":"abc","spanId":"def","attributes":base_attrs+[A("f2.causal_id","c-1"),A("f2.generation",3),A("f2.effect_id","e-1")]}])))
    ))
    T("partial_identity_fails_closed", lambda: expect_reject(lambda: normalize("/v1/logs", logs([{"attributes":base_attrs+[A("f2.causal_id","c-1")]}])), "PARTIAL_F2_IDENTITY"))
    T("wrong_signal_root_rejected", lambda: expect_reject(lambda: normalize("/v1/traces", logs([{"attributes":base_attrs}])), "WRONG_OR_MISSING_SIGNAL_ROOT"))
    T("malformed_attribute_rejected", lambda: expect_reject(lambda: normalize("/v1/logs", logs([{"attributes":[{"key":"x","value":{}}]}])), "AMBIGUOUS_ATTRIBUTE_VALUE"))
    def redact_test():
        x=normalize("/v1/logs", logs([{"attributes":base_attrs+[A("gen_ai.tool.call.arguments",'{"secret":"x"}'),A("gen_ai.system_instructions","secret prompt")]}]))[0]
        assert "gen_ai.tool.call.arguments" not in x["attributes"] and "gen_ai.system_instructions" not in x["attributes"]
        assert set(x["redacted_keys"])=={"gen_ai.system_instructions","gen_ai.tool.call.arguments"}
    T("sensitive_content_minimized", redact_test)
    def replay_test():
        raw=logs([{"timeUnixNano":"10","attributes":base_attrs}]); a=normalize("/v1/logs",raw)[0]; b=normalize("/v1/logs",raw)[0]
        assert a["ingress_event_sha256"]==b["ingress_event_sha256"]
    T("replay_identity_deterministic", replay_test)
    T("metrics_endpoint_supported", lambda: normalize("/v1/metrics", metrics([{"name":"tokens","attributes":base_attrs}])))
    T("traces_endpoint_supported_not_discarded", lambda: normalize("/v1/traces", traces([{"traceId":"abc","spanId":"def","attributes":base_attrs}])))
    T("protobuf_payload_not_supported_by_json_fixture", lambda: expect_reject(lambda: normalize("/v1/logs", b"\x0a\x03abc"), "MALFORMED_JSON"))

    raw=logs([{"timeUnixNano":"10","attributes":base_attrs+[A("service.name","fixture")]}])
    N=20000; times=[]
    rss0=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for _ in range(N):
        t=time.perf_counter_ns(); normalize("/v1/logs",raw); times.append(time.perf_counter_ns()-t)
    rss1=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    times.sort()
    def q(p): return times[min(len(times)-1, int(len(times)*p))]/1000.0
    result={
        "schema":"R6_SEED008_OTLP_INGRESS_E3_FIXTURE_RESULT/v1",
        "tests_passed":len(tests),"tests_total":10,"tests":tests,
        "benchmark":{"iterations":N,"median_us":statistics.median(times)/1000.0,"p95_us":q(.95),"p99_us":q(.99),"max_us":max(times)/1000.0,"ru_maxrss_delta_kib":max(0,rss1-rss0)},
    }
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__=="__main__": run()
