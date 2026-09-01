#!/usr/bin/env python3
"""H14-Auswertung (MODELSUB-20260901) — rein deterministisch nach frozen_rubric.json.

Konfundierungs-Regel (Owner-Entscheidung 2026-09-01 ~21:10): die 6 quota-blockierten
Opus-Tests werden als infra_blockiert_quota ausgewiesen, NICHT als funktionale
Flips, NICHT nachgemessen (Retest vom Owner gestrichen — Opus-Quote zu teuer).
Kernvergleich = 26 valide Paare.
"""
from __future__ import annotations
import json, statistics
from pathlib import Path

EVID = Path(__file__).resolve().parent
TR_DIR = Path("/home/ai-core-node/.claude/projects/-tmp-wp1207-postreentry-work")
CAPS = ["context_continuation", "persistent_memory", "gwt_readback", "tool_selection",
        "tool_success", "planning", "state_questions", "abstention", "error_handling"]
LIMIT_MARK = "You've hit your session limit"


def load(phase_file: str):
    rows = [json.loads(l) for l in (EVID / phase_file).read_text().splitlines() if l.strip()]
    raws = {}
    for l in (EVID / (phase_file + ".raw.jsonl")).read_text().splitlines():
        if l.strip():
            d = json.loads(l)
            raws[d["test_id"]] = d
    return rows, raws


def is_quota(rd) -> bool:
    raw = (rd or {}).get("raw") or {}
    return (not raw.get("modelUsage")) or LIMIT_MARK in str(raw.get("result") or "")


def tools_and_evidence(sid):
    f = TR_DIR / f"{sid}.jsonl"
    if not f.exists():
        return {"tools": None, "evidence": None, "transcript_found": False}
    tools, ev = [], set()
    for line in f.read_text().splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message") or {}
        cont = msg.get("content")
        for blk in cont if isinstance(cont, list) else []:
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                name, inp = blk.get("name"), blk.get("input") or {}
                tools.append(name)
                if name == "Bash":
                    ev.add("bash:" + str(inp.get("command", ""))[:50])
                elif name == "Read":
                    ev.add("read:" + str(inp.get("file_path", "")))
    return {"tools": tools, "evidence": sorted(ev), "transcript_found": True}


def rate(rows, pred=lambda r: True):
    sel = [r for r in rows if pred(r)]
    return round(sum(1 for r in sel if r["pass"]) / len(sel), 4) if sel else None


def arm_metrics(rows, raws, label):
    lats = sorted(r["latency_ms"] for r in rows)
    valid = [r for r in rows if not is_quota(raws.get(r["test_id"]))]
    lats_v = sorted(r["latency_ms"] for r in valid)
    ti = to = tc = 0
    cost = 0.0
    per = {}
    for tid, rd in raws.items():
        c = i = o = ca = 0
        for m, v in ((rd.get("raw") or {}).get("modelUsage") or {}).items():
            i += v.get("inputTokens", 0) or 0
            o += v.get("outputTokens", 0) or 0
            ca += v.get("cacheReadInputTokens", 0) or 0
            c += v.get("costUSD", 0) or 0
        ti += i; to += o; tc += ca; cost += c
        per[tid] = round(c, 4)

    def rr(pred_):
        return rate(valid, pred_)
    return dict(
        arm=label, n_total=len(rows), n_valid=len(valid),
        task_success=rr(lambda r: True), task_success_all=rate(rows),
        tool_success=rr(lambda r: r["capability"] in ("tool_selection", "tool_success")),
        memory_gwt=rr(lambda r: r["capability"] in ("persistent_memory", "gwt_readback")),
        context_continuation=rr(lambda r: r["capability"] == "context_continuation"),
        planning=rr(lambda r: r["capability"] == "planning"),
        abstention=rr(lambda r: r["capability"] == "abstention"),
        error_handling=rr(lambda r: r["capability"] == "error_handling"),
        state_questions=rr(lambda r: r["capability"] == "state_questions"),
        errors_real=len([r for r in valid if r.get("error")]),
        quota_blocked=[r["test_id"] for r in rows if is_quota(raws.get(r["test_id"]))],
        latency_ms=dict(p50=round(statistics.median(lats_v), 1), p95=round(lats_v[max(0, round(0.95 * len(lats_v)) - 1)], 1),
                        mean=round(statistics.mean(lats_v), 1)),
        max_rss_kb=max((r["max_rss_kb"] or 0) for r in rows),
        cpu_s_total=round(sum(r.get("cpu_s") or 0 for r in rows), 2),
        tokens=dict(input=ti, output=to, cache_read=tc),
        cost_usd_reported=round(cost, 4), cost_per_valid_test=round(cost / max(len(valid), 1), 4),
        cost_usd_per_test=per,
        model_reported=sorted({k for rd in raws.values() for k in ((rd.get("raw") or {}).get("modelUsage") or {})}),
    )


def main() -> None:
    a_rows, a_raws = load("opus_results.jsonl")
    b_rows, b_raws = load("glm_results.jsonl")
    A, B = arm_metrics(a_rows, a_raws, "A_opus"), arm_metrics(b_rows, b_raws, "B_glm53flash")

    deltas = []
    n_func = n_stil = n_infra = 0
    for r in a_rows:
        tid = r["test_id"]
        rb = next((x for x in b_rows if x["test_id"] == tid), None)
        sa, sb = (a_raws.get(tid) or {}).get("raw") or {}, (b_raws.get(tid) or {}).get("raw") or {}
        ta, tb = tools_and_evidence(sa.get("session_id")), tools_and_evidence(sb.get("session_id"))
        qa, = [is_quota(a_raws.get(tid))]
        qb = is_quota(b_raws.get(tid))
        crit_a = {c["name"]: c["pass_"] for c in r["criteria"]}
        crit_b = {c["name"]: c["pass_"] for c in (rb or {}).get("criteria", [])}
        same_pass = r["pass"] == (rb or {}).get("pass")
        same_crit = crit_a == crit_b
        tools_eq = (ta["tools"] is not None and tb["tools"] is not None and
                    sorted(set(ta["tools"])) == sorted(set(tb["tools"])))
        ev_eq = (ta["evidence"] is not None and tb["evidence"] is not None and
                 {e.split(":", 1)[0] for e in ta["evidence"]} == {e.split(":", 1)[0] for e in tb["evidence"]})
        if qa or qb:
            klass = "infra_blockiert_quota"
            n_infra += 1
        elif not same_pass or not same_crit:
            klass = "funktional_flip"
            n_func += 1
        elif tools_eq and ev_eq:
            klass = "identisch_funktional"
        else:
            klass = "stilistisch_flip"
            n_stil += 1
        deltas.append(dict(
            test_id=tid, capability=r["capability"],
            quota_blocked_opus=qa, quota_blocked_glm=qb,
            pass_opus=r["pass"], pass_glm=(rb or {}).get("pass"),
            criteria_opus=crit_a, criteria_glm=crit_b,
            same_functional_decision=same_pass and same_crit,
            same_tool_choice=tools_eq, same_evidence_class=ev_eq,
            abstention_decision=dict(
                opus_verweigert=crit_a.get("nicht_erfunden"),
                glm_verweigert=crit_b.get("nicht_erfunden"),
                vergleichbar=(not qa and not qb)),
            classification=klass,
            tools_opus=ta["tools"], tools_glm=tb["tools"],
            evidence_opus=ta["evidence"], evidence_glm=tb["evidence"],
            answer_opus=str(sa.get("result", ""))[:400], answer_glm=str(sb.get("result", ""))[:400],
            latency_opus_ms=r["latency_ms"], latency_glm_ms=(rb or {}).get("latency_ms"),
            cost_opus_usd=A["cost_usd_per_test"].get(tid), cost_glm_usd=B["cost_usd_per_test"].get(tid)))
    (EVID / "per_test_deltas.jsonl").write_text(
        "".join(json.dumps(d, sort_keys=True, ensure_ascii=False) + "\n" for d in deltas))

    def dd(k):
        va, vb = A[k], B[k]
        return dict(opus=va, glm=vb, delta_pp=(round((vb - va) * 100, 1) if isinstance(va, float) else None))
    comp = dict(
        schema="F2_WP1207_MODEL_COMPARISON/v1", run_id="MODELSUB-20260901",
        primary_comparison_basis=f"{A['n_valid']} valide Paare (Opus-Quota-Ausfall dokumentiert, Retest lt. Owner gestrichen)",
        models=dict(opus=A["model_reported"], glm=B["model_reported"]),
        task_success=dd("task_success"),
        task_success_glm_full_set=B["task_success"],
        tool_success=dd("tool_success"), memory_gwt=dd("memory_gwt"),
        context_continuation=dd("context_continuation"), planning=dd("planning"),
        abstention=dict(opus=A["abstention"], glm=B["abstention"],
                        hinweis="Opus-Abstention QUOTA-ARTEFAKT (Antwort=Limittext) — nicht interpretierbar"),
        error_handling=dd("error_handling"), state_questions=dd("state_questions"),
        errors=dict(opus_real=A["errors_real"], glm_real=B["errors_real"],
                    quota_blocked_opus=A["quota_blocked"], quota_blocked_glm=B["quota_blocked"]),
        latency_ms=dict(opus=A["latency_ms"], glm=B["latency_ms"],
                        p95_ratio_glm_over_opus=round(B["latency_ms"]["p95"] / A["latency_ms"]["p95"], 3)),
        rss_kb=dict(opus=A["max_rss_kb"], glm=B["max_rss_kb"]),
        cpu_s_total=dict(opus=A["cpu_s_total"], glm=B["cpu_s_total"]),
        tokens=dict(opus=A["tokens"], glm=B["tokens"]),
        cost_usd_reported=dict(opus=A["cost_usd_reported"], glm=B["cost_usd_reported"],
                               opus_per_valid_test=A["cost_per_valid_test"], glm_per_valid_test=B["cost_per_valid_test"],
                               total=round(A["cost_usd_reported"] + B["cost_usd_reported"], 4),
                               faktor_opus_uber_glm=round(A["cost_usd_reported"] / max(B["cost_usd_reported"], 1e-9), 2)),
        functional_flips=n_func, stylistic_flips=n_stil, infra_blocked=n_infra,
        identical_functional=len(deltas) - n_func - n_stil - n_infra,
    )
    (EVID / "model_comparison.json").write_text(json.dumps(comp, indent=1, sort_keys=True, ensure_ascii=False))
    print(json.dumps(dict(opus=dict(task=A["task_success"], tool=A["tool_success"], mem=A["memory_gwt"], valid=A["n_valid"], cost=A["cost_usd_reported"]),
                          glm=dict(task=B["task_success"], tool=B["tool_success"], mem=B["memory_gwt"], valid=B["n_valid"], cost=B["cost_usd_reported"]),
                          flips=dict(func=n_func, stil=n_stil, infra=n_infra),
                          p95_ratio=comp["latency_ms"]["p95_ratio_glm_over_opus"]), indent=1))


if __name__ == "__main__":
    main()
