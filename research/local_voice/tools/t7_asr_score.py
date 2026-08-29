#!/usr/bin/env python3
"""Deterministic provider-neutral Trigger-7 German ASR scoring harness."""
from __future__ import annotations
import argparse, json, math, re, statistics, sys, unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence
WORD_RE = re.compile(r"\w+", re.UNICODE)

def normalize_text(text: str) -> str:
    return " ".join(WORD_RE.findall(unicodedata.normalize("NFKC", str(text)).casefold()))

def word_tokens(text: str) -> list[str]:
    n = normalize_text(text); return n.split() if n else []

def char_tokens(text: str) -> list[str]:
    return list(normalize_text(text).replace(" ", ""))

def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    if len(a) > len(b): a, b = b, a
    prev = list(range(len(a) + 1))
    for i, y in enumerate(b, 1):
        cur = [i]
        for j, x in enumerate(a, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (x != y)))
        prev = cur
    return prev[-1]

def percentile(values: Sequence[float], q: float) -> float | None:
    if not values: return None
    vals = sorted(float(v) for v in values)
    if len(vals) == 1: return vals[0]
    pos = (len(vals)-1)*q; lo = math.floor(pos); hi = math.ceil(pos)
    if lo == hi: return vals[lo]
    w = pos-lo; return vals[lo]*(1-w) + vals[hi]*w

def common_prefix_len(a: Sequence[str], b: Sequence[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y: break
        n += 1
    return n

def similarity(a: Sequence[str], b: Sequence[str]) -> float:
    return max(0.0, 1.0 - edit_distance(a,b)/max(len(a),len(b),1))

def group_key(r: dict[str,Any]) -> tuple[str,str,str]:
    return (str(r.get("candidate_id","UNKNOWN")), str(r.get("condition","baseline")), str(r.get("right_context_ms","NA")))

def group_label(k: tuple[str,str,str]) -> str:
    return f"candidate={k[0]}|condition={k[1]}|right_context_ms={k[2]}"

def validate_record(r: dict[str,Any], line_no: int) -> None:
    for f in ("utterance_id","reference","hypothesis"):
        if f not in r: raise ValueError(f"line {line_no}: missing required field {f!r}")
    if not str(r["utterance_id"]): raise ValueError(f"line {line_no}: empty utterance_id")
    if "technical_terms" in r and not isinstance(r["technical_terms"], list): raise ValueError(f"line {line_no}: technical_terms must be list")
    if "partials" in r and not isinstance(r["partials"], list): raise ValueError(f"line {line_no}: partials must be list")
    if "user_speech_end_ns" in r and "asr_final_ns" in r and int(r["asr_final_ns"]) < int(r["user_speech_end_ns"]):
        raise ValueError(f"line {line_no}: asr_final_ns precedes user_speech_end_ns")

def score_record(r: dict[str,Any]) -> dict[str,Any]:
    rw, hw = word_tokens(r["reference"]), word_tokens(r["hypothesis"])
    rc, hc = char_tokens(r["reference"]), char_tokens(r["hypothesis"])
    we, ce = edit_distance(rw,hw), edit_distance(rc,hc)
    hyp_norm = normalize_text(r["hypothesis"])
    terms=[]
    for raw in map(str, r.get("technical_terms", [])):
        tn=normalize_text(raw)
        matched=bool(tn) and f" {tn} " in f" {hyp_norm} "
        terms.append({"term":raw,"matched":matched})
    latency=None
    if "user_speech_end_ns" in r and "asr_final_ns" in r:
        latency=(int(r["asr_final_ns"])-int(r["user_speech_end_ns"]))/1_000_000.0
    partials=[word_tokens(x) for x in r.get("partials",[])]
    sims=[similarity(p,hw) for p in partials]
    prefixes=[common_prefix_len(p,hw) for p in partials]
    regressions=sum(cur < prev for prev,cur in zip(prefixes,prefixes[1:]))
    return {
      "utterance_id":str(r["utterance_id"]),"reference_words":len(rw),"hypothesis_words":len(hw),"word_edits":we,
      "wer":we/len(rw) if rw else (0.0 if not hw else 1.0),"reference_chars":len(rc),"char_edits":ce,
      "cer":ce/len(rc) if rc else (0.0 if not hc else 1.0),"technical_terms":terms,
      "technical_term_total":len(terms),"technical_term_matches":sum(x["matched"] for x in terms),
      "finalization_latency_ms":latency,"partial_count":len(partials),
      "partial_mean_final_similarity":statistics.fmean(sims) if sims else None,
      "partial_last_final_similarity":sims[-1] if sims else None,"partial_prefix_regressions":regressions}

def aggregate(records: list[dict[str,Any]]) -> dict[str,Any]:
    s=[score_record(r) for r in records]
    rw=sum(x["reference_words"] for x in s); we=sum(x["word_edits"] for x in s)
    rc=sum(x["reference_chars"] for x in s); ce=sum(x["char_edits"] for x in s)
    tt=sum(x["technical_term_total"] for x in s); tm=sum(x["technical_term_matches"] for x in s)
    lat=[x["finalization_latency_ms"] for x in s if x["finalization_latency_ms"] is not None]
    ps=[x["partial_mean_final_similarity"] for x in s if x["partial_mean_final_similarity"] is not None]
    return {"utterance_count":len(s),"utterance_ids":sorted(x["utterance_id"] for x in s),
      "micro_wer":we/rw if rw else None,"word_edits":we,"reference_words":rw,
      "micro_cer":ce/rc if rc else None,"char_edits":ce,"reference_chars":rc,
      "technical_term_recall":tm/tt if tt else None,"technical_term_matches":tm,"technical_term_total":tt,
      "finalization_latency_ms":{"count":len(lat),"p50":percentile(lat,.5),"p95":percentile(lat,.95),"p99":percentile(lat,.99),"max":max(lat) if lat else None},
      "partial_stability":{"utterances_with_partials":len(ps),"mean_partial_to_final_similarity":statistics.fmean(ps) if ps else None,"prefix_regressions":sum(x["partial_prefix_regressions"] for x in s)},
      "utterances":s}

def comparability(groups: dict[str,dict[str,Any]]) -> dict[str,Any]:
    labels=sorted(groups)
    if not labels: return {"identical_corpus":True,"reference_group":None,"differences":{}}
    ref=labels[0]; ids=set(groups[ref]["utterance_ids"]); diff={}
    for label in labels[1:]:
        other=set(groups[label]["utterance_ids"]); missing=sorted(ids-other); extra=sorted(other-ids)
        if missing or extra: diff[label]={"missing_vs_reference":missing,"extra_vs_reference":extra}
    return {"identical_corpus":not diff,"reference_group":ref,"differences":diff}

def load_jsonl(path: Path) -> list[dict[str,Any]]:
    out=[]; seen=set()
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        r=json.loads(line); validate_record(r,n); key=(group_key(r),str(r["utterance_id"]))
        if key in seen: raise ValueError(f"line {n}: duplicate utterance_id within group")
        seen.add(key); out.append(r)
    if not out: raise ValueError("input contains no records")
    return out

def build_report(records: list[dict[str,Any]]) -> dict[str,Any]:
    grouped=defaultdict(list)
    for r in records: grouped[group_key(r)].append(r)
    groups={group_label(k):aggregate(v) for k,v in sorted(grouped.items())}
    return {"schema":"T7_GERMAN_ASR_SCORE/v1","evidence_scope":"DETERMINISTIC_SCORING_ONLY_NO_MODEL_RUNTIME_CREDIT",
      "normalization":"NFKC_CASEFOLD_WORD_CHARS; CER removes whitespace; punctuation ignored","groups":groups,
      "corpus_comparability":comparability(groups),"runtime_credit":0,"trigger4_acceptance_credit":0}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("input_jsonl",type=Path); p.add_argument("--output",type=Path); a=p.parse_args(argv)
    try: report=build_report(load_jsonl(a.input_jsonl))
    except (OSError,ValueError,json.JSONDecodeError) as e: print(f"ERROR: {e}",file=sys.stderr); return 2
    payload=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if a.output: a.output.write_text(payload,encoding="utf-8")
    else: sys.stdout.write(payload)
    return 0
if __name__ == "__main__": raise SystemExit(main())
