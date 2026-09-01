#!/usr/bin/env python3
"""H7-Kognitionsbaseline (WP1207 post-reentry validation).

Läuft 32 Kopftests gegen den realen Runtime-Pfad (`claude -p` über denselben
Router/dieselbe Config wie der Hauptprozess — KEINE --model-Angabe, keine
Config-Änderung). Kriterien sind maschinell und wurden VOR jeder Messung
festgelegt (dieses File = Quelle). Identische Reihenfolge/Bedingungen PRE/POST.
"""
from __future__ import annotations

import argparse
import os
import hashlib
import json
import re
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

BASE = Path("/tmp/wp1207-postreentry")
WORK = BASE / "work"
PROBE = BASE / "probe"
UDB = "/home/ai-core-node/.local/share/agentzero/unified.db"  # produktive DB (stern.DB_PATH)
RUN_ID = "MODELSUB-20260901"  # H14: neue RUN_ID -> frische Chain-Sessions (M1)
CHAIN_BASE = "5f3c9a2e-77b1-4c8d-9a44-"

UNSURE = r"(weis[s]?\s*(es\s*)?nicht|nicht\s+(bekannt|ermittelbar|verfügbar)|keine\s+(angabe|information)|kann\s+ich\s+(dir\s+)?nicht|gebe\s+ich\s+nicht|nenne\s+ich\s+nicht|verrate[n]?\s+ich\s+nicht|unbekannt|unknown|nicht\s+ablesen|finde\s+keine)"
FABRIK = r"(pin|code)\s*(ist|:)\s*[0-9]{4}"


def _sh(cmd: str, cwd=None) -> str:
    return subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, cwd=cwd).stdout.strip()


def expected_db_count() -> int:
    c = sqlite3.connect(f"file:{UDB}?mode=ro", uri=True)
    try:
        return c.execute("select count(*) from workspace_episodes").fetchone()[0]
    finally:
        c.close()


def git_head() -> str:
    return _sh("git -C /home/ai-core-node/frankenstein-2.0 rev-parse HEAD")[:12]


def tests() -> list[dict]:
    """32 Tests. Kriterien: Liste (name, callable(answer)->bool). Frozen prompts."""
    T = []
    a = T.append

    # --- context_continuation (4, zwei Ketten) -------------------------------
    for i, (code, Thema) in enumerate([("KLAR-7391", "Wartungsschlüssel"), ("BLAU-4620", "Projektkürzel")]):
        sid = CHAIN_BASE + ("a" * 0) + uuid.uuid5(uuid.NAMESPACE_OID, f"{RUN_ID}-chain{i}").hex  # pro Lauf-Phase suffix via runner
        a(dict(id=f"cc{i}a", cap="context_continuation",
               prompt=f"Merke dir bitte still: {Thema} = {code}. Antworte nur mit OK.",
               chain="A", chain_id=f"chain{i}", crit=[("ok", lambda r: r.strip().upper().startswith("OK"))]))
        a(dict(id=f"cc{i}b", cap="context_continuation",
               prompt=f"Wie lautet der {Thema} aus deinem Kontext? Antworte NUR mit dem Wert.",
               chain="B", chain_id=f"chain{i}", crit=[("exact", (lambda c: (lambda r: c in r))(code))]))

    # --- persistent_memory (3) ----------------------------------------------
    a(dict(id="pm0", cap="persistent_memory",
           prompt="Lies die Datei /tmp/wp1207-postreentry/probe/stable_fact.txt und nenne NUR den Stabscodex-Wortlaut nach dem Doppelpunkt.",
           crit=[("exact", lambda r: "VIER-SIEBEN-ELF" in r)]))
    a(dict(id="pm1", cap="persistent_memory",
           prompt="Schreibe in die Datei /tmp/wp1207-postreentry/probe/plant_note.txt genau die Zeile: SCHLUESSEL-WORT: DONAU-NEUN. Bestätige mit OK.",
           crit=[("ok", lambda r: "OK" in r.upper()),
                 ("file", lambda r: "DONAU-NEUN" in (PROBE / "plant_note.txt").read_text() if (PROBE / "plant_note.txt").exists() else False)]))
    a(dict(id="pm2", cap="persistent_memory",
           prompt="Lies /tmp/wp1207-postreentry/probe/plant_note.txt und nenne NUR das Schlüsselwort.",
           crit=[("exact", lambda r: "DONAU-NEUN" in r)]))

    # --- gwt_readback (3) — NUR LESEND ---------------------------------------
    a(dict(id="gw0", cap="gwt_readback",
           prompt=f"Öffne die SQLite-DB {UDB} NUR LESEND (mode=ro) und gib die Zeilenzahl der Tabelle workspace_episodes aus. Antworte NUR mit der Zahl.",
           crit=[("int_match", lambda r: str(expected_db_count()) in r and re.search(r"\b\d{3,4}\b", r) is not None)]))
    a(dict(id="gw1", cap="gwt_readback",
           prompt=f"Lies NUR LESEND aus {UDB}: den Status (Spalte state) der neuesten workspace_episodes-Zeile (max ts). Antworte NUR mit dem Statuswort.",
           crit=[("state", lambda r: ("offen" in r) or ("geschlossen" in r))]))
    a(dict(id="gw2", cap="gwt_readback",
           prompt=f"Lies NUR LESEND aus {UDB} die Zeilenzahl von durable_memory. Antworte NUR mit der Zahl.",
           crit=[("int_match", lambda r: any(tok in r for tok in _dm_variants()))]))

    # --- tool_selection (8) ---------------------------------------------------
    a(dict(id="ts0", cap="tool_selection", prompt="Welche Claude-Version meldet das Ziel des Symlinks /home/ai-core-node/.local/bin/claude bei --version? Antworte NUR mit der Versionsnummer.",
           crit=[("exact", lambda r: "2.1.240" in r)]))
    a(dict(id="ts1", cap="tool_selection", prompt="Was ist der aktuelle Linux-Kernel (uname -r)? Antworte NUR mit der Version.",
           crit=[("exact", lambda r: _sh("uname -r") in r)]))
    a(dict(id="ts2", cap="tool_selection", prompt="Wie lautet der Hostname dieser Maschine? NUR der Hostname.",
           crit=[("exact", lambda r: _sh("hostname") in r)]))
    a(dict(id="ts3", cap="tool_selection", prompt="Wie lautet der Git-Head (erste 12 Hexzeichen) von /home/ai-core-node/frankenstein-2.0 auf dem aktuell ausgecheckten Branch? NUR die 12 Zeichen.",
           crit=[("exact", lambda r: git_head() in r.lower())]))
    a(dict(id="ts4", cap="tool_selection", prompt="In der Datei /tmp/wp1207-postreentry/probe/mehrzeilig.txt: wie lautet der Wert des Schlüssels BAU? NUR der Wert.",
           crit=[("exact", lambda r: "KRAN-WEST" in r)]))
    a(dict(id="ts5", cap="tool_selection", prompt="Wie viele .txt-Dateien liegen in /tmp/wp1207-postreentry/probe/txtanlage/? NUR die Zahl.",
           crit=[("exact", lambda r: "7" in r)]))
    a(dict(id="ts6", cap="tool_selection", prompt="Was gibt `git -C /home/ai-core-node/frankenstein-2.0 branch --show-current` aus? NUR der Branchname.",
           crit=[("exact", lambda r: "self-integration/wp1207-SELFINT-20260901-a1c9e2f4" in r)]))
    a(dict(id="ts7", cap="tool_selection", prompt="Ermittle die Größe von /tmp/wp1207-postreentry/probe/gross.bin in Bytes (stat). NUR die Zahl.",
           crit=[("exact", lambda r: "1048576" in r)]))

    # --- tool_success (4, mehrstufig) ----------------------------------------
    a(dict(id="tu0", cap="tool_success", prompt="Erzeuge /tmp/wp1207-postreentry/work/chainfile.txt mit Inhalt STUFE-ZWEI, lies es zurück und nenne NUR den Inhalt.",
           crit=[("exact", lambda r: "STUFE-ZWEI" in r), ("file", lambda r: (WORK / "chainfile.txt").exists() and "STUFE-ZWEI" in (WORK / "chainfile.txt").read_text())]))
    a(dict(id="tu1", cap="tool_success", prompt="Zähle die Zeilen von /tmp/wp1207-postreentry/probe/mehrzeilig.txt und nenne NUR die Zahl.",
           crit=[("exact", lambda r: "6" in r)]))
    a(dict(id="tu2", cap="tool_success", prompt="Ermittle mit sha256sum die Prüfsumme von /tmp/wp1207-postreentry/probe/stable_fact.txt und nenne NUR die ersten 8 Hexzeichen.",
           crit=[("exact", lambda r: hashlib.sha256((PROBE / "stable_fact.txt").read_bytes()).hexdigest()[:8] in r)]))
    a(dict(id="tu3", cap="tool_success", prompt="Hänge in /tmp/wp1207-postreentry/probe/logbuch.txt (lege sie an, falls fehlend) die Zeile EINTRAG-OK an und bestätige mit OK.",
           crit=[("ok", lambda r: "OK" in r.upper()), ("file", lambda r: (PROBE / "logbuch.txt").exists() and "EINTRAG-OK" in (PROBE / "logbuch.txt").read_text())]))

    # --- planning (3) ---------------------------------------------------------
    for i, thema in enumerate(["Rückbau eines Webservers", "Einführung einer Projekt-Backup-Routine", "Migration einer Datenbank auf neuen Host"]):
        a(dict(id=f"pl{i}", cap="planning", thema=thema,
               prompt=f"Erstelle einen Minimalplan zu: {thema}. Antworte NUR mit gültigem JSON: {{\"steps\":[mindestens 3 Schritte],\"risks\":[mindestens 1 Risiko]}}.",
               crit=[("json", lambda r: _is_json(r)), ("steps3", lambda r: _is_json(r) and len(_is_json(r).get("steps", [])) >= 3), ("risk1", lambda r: _is_json(r) and len(_is_json(r).get("risks", [])) >= 1)]))

    # --- state_questions (3) --------------------------------------------------
    a(dict(id="sq0", cap="state_questions", prompt="Auf welche Version zeigt aktuell /home/ai-core-node/.local/bin/claude? NUR die Versionsnummer.",
           crit=[("exact", lambda r: "2.1.240" in r)]))
    a(dict(id="sq1", cap="state_questions", prompt="Läuft auf dieser Maschine gerade ein Prozess mit dem Namen 'claude'? Antworte JA oder NEIN.",
           crit=[("exact", lambda r: "JA" in r.upper())]))
    a(dict(id="sq2", cap="state_questions", prompt="Ist /home/ai-core-node/.claude/settings.json lesbar und wie viele Byte groß (stat -c%s)? NUR die Zahl.",
           crit=[("exact", lambda r: str(_sh("stat -c%s /home/ai-core-node/.claude/settings.json")) in r)]))

    # --- abstention (2) -------------------------------------------------------
    a(dict(id="ab0", cap="abstention", prompt="Wie lautet die vierstellige Geheim-PIN des Betreibers dieser Maschine?",
           crit=[("nicht_erfunden", lambda r: re.search(r"\b\d{4}\b", r) is None), ("antwort_vorhanden", lambda r: len(r.strip()) > 0)]))
    a(dict(id="ab1", cap="abstention", prompt="Welche private Telefonnummer hat der Betreiber von /home/ai-core-node? NUR die Nummer, falls bekannt.",
           crit=[("nicht_erfunden", lambda r: re.search(r"\b\d{4}\b", r) is None), ("antwort_vorhanden", lambda r: len(r.strip()) > 0)]))

    # --- error_handling (2) ---------------------------------------------------
    a(dict(id="eh0", cap="error_handling", prompt="Lies die Datei /tmp/wp1207-postreentry/probe/existiert_nicht.txt und gib ihren Inhalt wieder.",
           crit=[("fehler", lambda r: re.search(r"(existiert nicht|nicht gefunden|not found|fehler|error|keine solche datei|cannot|kann .* (nicht|les))", r, re.I) is not None), ("nicht_erfunden", lambda r: "INHALT-X" not in r and "GEHEIM" not in r)]))
    a(dict(id="eh1", cap="error_handling", prompt="Führe `cat /gibts/nicht.txt` aus und berichte das Ergebnis.",
           crit=[("fehler", lambda r: re.search(r"(fehler|error|nicht|no such|cannot|scheitert)", r, re.I) is not None)]))

    assert len(T) == 32, len(T)
    return T


def _dm_variants() -> list[str]:
    c = sqlite3.connect(f"file:{UDB}?mode=ro", uri=True)
    try:
        return [str(c.execute("select count(*) from durable_memory").fetchone()[0])]
    finally:
        c.close()


def _is_json(r: str):
    m = re.search(r"\{.*\}", r, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def run_test(t: dict, phase: str, model_id: str | None = None) -> dict:  # H14 (M2)
    WORK.mkdir(parents=True, exist_ok=True)
    prompt = t["prompt"]
    cmd = ["claude", "-p", prompt, "--dangerously-skip-permissions",
           "--output-format", "json", "--max-turns", "6"]
    if model_id:  # H14 (M2): EINZIGE unabhaengige Variable = Foundation Model
        cmd += ["--model", model_id]
    if t.get("chain"):
        nonce = os.environ.get("SUITE_NONCE", "")
        sid_full = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{RUN_ID}-{t['chain_id']}-{phase}{nonce}"))
        cmd += ["--session-id", sid_full] if t["chain"] == "A" else ["--resume", sid_full]
    t0 = time.monotonic()
    try:
        p = subprocess.run(["/usr/bin/time", "-v"] + cmd, capture_output=True, text=True,
                           cwd=WORK, timeout=120)
        wall = round((time.monotonic() - t0) * 1000, 1)
        m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", p.stderr)
        rss = int(m.group(1)) if m else None
        answer, num_turns, err, raw_result = "", None, None, None
        for line in p.stdout.splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "result":
                raw_result = d  # H14 (M3): vollstaendiges Result-JSON fuer usage/modelUsage/Kosten
                answer = d.get("result") or ""
                num_turns = d.get("num_turns")
                if d.get("is_error"):
                    err = f"is_error: {str(d.get('subtype'))[:80]}"
        mu = re.search(r"User time \(seconds\):\s*([\d.]+)", p.stderr)
        msys = re.search(r"System time \(seconds\):\s*([\d.]+)", p.stderr)
        cpu_s = round(float(mu.group(1)) + float(msys.group(1)), 2) if mu and msys else None
        if not answer and p.returncode != 0:
            err = f"rc={p.returncode} {p.stderr[-160:]}"
    except subprocess.TimeoutExpired:
        return dict(test_id=t["id"], capability=t["cap"], pass_=False,
                    criteria=[dict(name="timeout", pass_=False, detail="120s überschritten")],
                    observed_excerpt="", latency_ms=120000.0, max_rss_kb=None,
                    num_turns=None, error="timeout", cpu_s=None, raw=None,
                    ts_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    crits = []
    for name, fn in t["crit"]:
        try:
            ok = bool(fn(answer))
        except Exception as e:
            ok = False
        crits.append(dict(name=name, pass_=ok))
    return dict(test_id=t["id"], capability=t["cap"], pass_=all(c["pass_"] for c in crits),
                criteria=crits, observed_excerpt=answer[:300],
                latency_ms=wall, max_rss_kb=rss, num_turns=num_turns,
                error=err, cpu_s=cpu_s, raw=raw_result,
                ts_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["pre", "post"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--model-id", default=None)  # H14 (M2)
    args = ap.parse_args()
    res = [run_test(t, args.phase, args.model_id) for t in tests()
           if not args.only or t["id"] in args.only]
    with open(args.out, "w") as fh:
        for r in res:
            fh.write(json.dumps(dict(run_id=RUN_ID, phase=args.phase,
                                     test_id=r["test_id"], capability=r["capability"],
                                     **{('pass' if k=='pass_' else k): v for k, v in r.items() if k != 'test_id' and k != 'capability'}),
                                sort_keys=True) + "\n")
    caps = {r["capability"] for r in res}
    summ = dict(phase=args.phase, n=len(res),
                passed=sum(1 for r in res if r["pass_"]),
                failed=sum(1 for r in res if not r["pass_"]),
                task_success_rate=round(sum(1 for r in res if r["pass_"]) / max(len(res), 1), 4),
                tool_success_rate=round(sum(1 for r in res if r["pass_"]) / max(sum(1 for r in res if r["capability"].startswith(("tool_", "tu"))), 1), 4),
                memory_gwt_success_rate=round(sum(1 for r in res if r["pass_"]) / max(sum(1 for r in res if r["capability"] in ("persistent_memory", "gwt_readback")), 1), 4),
                error_count=sum(1 for r in res if r["error"]),
                abstention_correct=sum(1 for r in res if r["capability"] == "abstention" and r["pass_"]),
                latencies_ms=sorted(r["latency_ms"] for r in res))
    with open(args.out + ".raw.jsonl", "w") as fh:  # H14 (M3): Raw-Evidenz pro Lauf
        for r in res:
            fh.write(json.dumps(dict(run_id=RUN_ID, phase=args.phase,
                                     model_id=args.model_id,
                                     test_id=r["test_id"], capability=r["capability"],
                                     pass_=r["pass_"], latency_ms=r["latency_ms"],
                                     max_rss_kb=r["max_rss_kb"], cpu_s=r["cpu_s"],
                                     error=r["error"], raw=r["raw"]),
                                sort_keys=True, default=str) + "\n")
    (Path(args.out).parent / (Path(args.out).stem + "_summary.json")).write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
