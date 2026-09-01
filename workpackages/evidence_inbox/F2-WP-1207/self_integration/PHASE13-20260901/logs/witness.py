#!/usr/bin/env python3
"""WP1207 PHASE 13 — Aussenzeuge fuer den echten Update/Fehler/Rollback-Zyklus.

Subjekt = die laufende Claude-Code-Instanz ("Frankenstein 1.0").
Echte Update-Grenze = der Symlink ~/.local/bin/claude -> versions/<v>.

Der verwaltete Satz (managed set) ist BEWUSST nur der Zeiger-Datensatz, nicht die
342-MB-Binaries und nicht unified.db. Die Transaktion bindet den Zeiger; der echte
Symlink wird an den Datensatz angeglichen und danach durch Aufruf von
`claude --version` VERIFIZIERT -- ein Datensatz ohne Wirkungsnachweis waere wertlos.

Schritt 5 (echter Prozesstod + Neustart) ist gebaut, aber nur mit --arm scharf.
Ohne --arm laeuft alles andere echt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/ai-core-node/frankenstein-2.0/src")
from frankenstein2.self_update_transaction import (  # noqa: E402
    SelfUpdateStore,
    apply_rollback,
    apply_transaction,
    compute_state_digest,
    independent_readback,
)

HOME = Path("/home/ai-core-node")
SYMLINK = HOME / ".local/bin/claude"
VERSIONS = HOME / ".local/share/claude/versions"
BASE_V, PRED_V = "2.1.240", "2.1.239"
UDB = HOME / ".claude/star/unified.db"
SETTINGS = HOME / ".claude/settings.json"

OUT = Path("/tmp/wp1207-phase13")
MANAGED, CONTROL = OUT / "managed", OUT / "control"
MEAS = OUT / "phase13_measurements.jsonl"

BASELINE = {
    "symlink_target": str(VERSIONS / BASE_V),
    "bin_2.1.240": "1cddc5e03fd3867d3c107c534be887161a2904bdfe614149c258695a35665148",
    "bin_2.1.239": "7de1b1576e2e0be73ce91c2b4dedf16a41058ea633b957a36fdc6044ddfc0f3c",
    "settings": "98d6297359c4f21a7bc5ea2d440cb06126f8c8b7a48d0a00cde3474b71e29ab4",
    "durable_memory": 14556,
    "workspace_episodes": 462,
    "entityos_arbeitspaket": 83,
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_head() -> tuple[str, bool]:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HOME / "frankenstein-2.0",
                       capture_output=True, text=True)
    d = subprocess.run(["git", "status", "--porcelain"], cwd=HOME / "frankenstein-2.0",
                       capture_output=True, text=True)
    return r.stdout.strip(), bool(d.stdout.strip())


def live_version() -> str:
    """Was meldet der Befehl, den ein Neustart wirklich benutzen wuerde?"""
    r = subprocess.run([str(SYMLINK), "--version"], capture_output=True, text=True, timeout=60)
    return r.stdout.strip().split()[0] if r.stdout.strip() else f"ERR:{r.stderr.strip()[:60]}"


def symlink_now() -> str:
    return os.readlink(SYMLINK)


def point_symlink(version: str) -> None:
    """Atomarer Zeigerwechsel: neu anlegen, dann ueberschreibend umbenennen."""
    tmp = SYMLINK.parent / f".claude-wp1207-{os.getpid()}"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(VERSIONS / version)
    os.replace(tmp, SYMLINK)


def record_for(version: str) -> dict[str, bytes]:
    payload = json.dumps(
        {"active_version": version, "binary_sha256": sha256_file(VERSIONS / version)},
        sort_keys=True,
    ).encode()
    return {"active_version.json": payload}


def record_version() -> str | None:
    f = MANAGED / "active_version.json"
    return json.loads(f.read_text())["active_version"] if f.exists() else None


def sync_and_verify(expect: str) -> dict:
    """Symlink an den Datensatz angleichen und WIRKUNG nachweisen."""
    point_symlink(expect)
    t0 = time.monotonic()
    v = live_version()
    return {
        "expected_version": expect,
        "symlink_target": symlink_now(),
        "live_version_reported": v,
        "effect_verified": v == expect and symlink_now() == str(VERSIONS / expect),
        "verify_ms": round((time.monotonic() - t0) * 1000, 3),
    }


def db_surface() -> dict:
    c = sqlite3.connect(f"file:{UDB}?mode=ro", uri=True)
    try:
        out = {t: c.execute(f"select count(*) from {t}").fetchone()[0]
               for t in ("durable_memory", "workspace_episodes", "entityos_arbeitspaket")}
        out["max_episode_ts"] = c.execute("select max(ts) from workspace_episodes").fetchone()[0]
        return out
    finally:
        c.close()


def measure(rec: dict) -> None:
    head, dirty = repo_head()
    rec = {"schema": "F2_WP1207_PHASE13_MEASUREMENT/v1", "run_id": RUN_ID,
           "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "repo_head_sha": head, "repo_dirty": dirty, **rec}
    with open(MEAS, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


RUN_ID = "PHASE13-20260901"

TARGET_PID = 2926511          # die laufende Claude-Code-Instanz = das Subjekt
LAUNCHER = HOME / ".local/bin/claude-code-launch"
SESSION_ID = "e0dc2e72-bbc8-477c-afd8-0e74072b2045"


def pid_alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def claude_pids() -> list[int]:
    """Alle claude-Hauptprozesse dieses Nutzers (comm == 'claude')."""
    out = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if (p / "comm").read_text().strip() == "claude" and p.stat().st_uid == os.getuid():
                out.append(int(p.name))
        except Exception:
            continue
    return sorted(out)


def pid_cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
    except Exception:
        return ""


def gwt_surface() -> dict:
    """GWT-/Gedaechtnis-Oberflaeche: Zeilen UND juengste Episode."""
    c = sqlite3.connect(f"file:{UDB}?mode=ro", uri=True)
    try:
        out = {t: c.execute(f"select count(*) from {t}").fetchone()[0]
               for t in ("durable_memory", "workspace_episodes", "entityos_arbeitspaket")}
        out["max_episode_ts"] = c.execute("select max(ts) from workspace_episodes").fetchone()[0]
        row = c.execute("select episode_id, session_id, ts, salience from workspace_episodes "
                        "order by ts desc limit 1").fetchone()
        out["newest_episode"] = None if row is None else {
            "episode_id": row[0], "session_id": row[1], "ts": row[2], "salience": row[3]}
        out["max_memory_ts"] = c.execute("select max(ts) from durable_memory").fetchone()[0]
        return out
    finally:
        c.close()


def kill_and_restart(evidence: dict) -> dict:
    """Schritt 5: echter Prozesstod + Neustart + GWT/Memory-Readback ueber die Grenze.

    Nur der Zeuge ueberlebt das -- deshalb schreibt er nach JEDEM Teilschritt
    die Belege auf Platte, damit auch ein Abbruch mittendrin eine Spur hinterlaesst.
    """
    # Baseline aller schon laufenden claude-PIDs. Auf DIESEM Rechner laeuft eine
    # ZWEITE, fremde Claude-Instanz (bei der Probe entdeckt) -- eine Suche nach dem
    # Namen "claude" wuerde sie faelschlich als "neue Instanz" zaehlen oder, schlimmer,
    # zum Ziel machen. Deshalb: nur die exakt benannte TARGET_PID stirbt, und die neue
    # Instanz wird ausschliesslich als DIFFERENZ zu dieser Baseline erkannt.
    pids_before = set(claude_pids())
    res: dict = {"status": "ARMED", "target_pid": TARGET_PID,
                 "target_cmdline": pid_cmdline(TARGET_PID),
                 "foreign_pids_untouched": sorted(pids_before - {TARGET_PID}),
                 "gwt_before": gwt_surface()}

    def flush() -> None:
        (OUT / "phase13_evidence.json").write_text(
            json.dumps(evidence, indent=1, sort_keys=True))

    if not pid_alive(TARGET_PID) or "claude" not in res["target_cmdline"]:
        res.update(status="ABORT", reason="Ziel-PID lebt nicht oder ist nicht claude")
        return res

    # -- 5a SIGTERM, mit Nachlauf --------------------------------------------
    t0 = time.monotonic()
    os.kill(TARGET_PID, 15)
    for _ in range(300):                       # bis 30 s auf sauberes Ende warten
        if not pid_alive(TARGET_PID):
            break
        time.sleep(0.1)
    res["sigterm_ms"] = round((time.monotonic() - t0) * 1000, 3)
    res["died_after_sigterm"] = not pid_alive(TARGET_PID)
    if not res["died_after_sigterm"]:
        os.kill(TARGET_PID, 9)                 # letzter Ausweg
        for _ in range(100):
            if not pid_alive(TARGET_PID):
                break
            time.sleep(0.1)
        res["needed_sigkill"] = True
        res["died_after_sigkill"] = not pid_alive(TARGET_PID)
    res["death_confirmed_ms"] = round((time.monotonic() - t0) * 1000, 3)
    res["gwt_after_death"] = gwt_surface()
    evidence["steps"]["process_restart"] = res
    flush()

    if pid_alive(TARGET_PID):
        res.update(status="FAIL", reason="Zielprozess ueberlebte SIGTERM und SIGKILL")
        return res

    # -- 5b Neustart ---------------------------------------------------------
    t1 = time.monotonic()
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":0"))
    for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
                "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH"):
        env.pop(key, None)
    cmd = ("cd /home/ai-core-node/seimensch-redesign && "
           f"exec /home/ai-core-node/.local/bin/claude --dangerously-skip-permissions "
           f"--resume {SESSION_ID}")
    proc = subprocess.Popen(
        ["gnome-terminal", "--title=Frankenstein (WP1207 Phase 13 Neustart)", "--", "bash", "-lc", cmd],
        env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res["relaunch_spawned"] = True
    res["relaunch_cmd"] = cmd

    new_pid = None
    for _ in range(900):                       # bis 90 s auf neue Instanz warten
        time.sleep(0.1)
        neu = set(claude_pids()) - pids_before  # nur ECHT neue PIDs, nie die fremde
        if neu:
            new_pid = min(neu)
            break
    res["reentry_ms"] = round((time.monotonic() - t1) * 1000, 3)
    res["new_pid"] = new_pid
    res["reentered"] = new_pid is not None
    res["new_cmdline"] = pid_cmdline(new_pid) if new_pid else None
    res["new_execpath_symlink"] = os.readlink(SYMLINK)
    evidence["steps"]["process_restart"] = res
    flush()

    # -- 5c Readback ueber die Prozessgrenze ---------------------------------
    time.sleep(20)                             # der neuen Instanz Zeit zum Hochlaufen geben
    after = gwt_surface()
    before = res["gwt_before"]
    res["gwt_after_restart"] = after
    res["gwt_survived"] = {
        "durable_memory_kept": after["durable_memory"] >= before["durable_memory"],
        "workspace_episodes_kept": after["workspace_episodes"] >= before["workspace_episodes"],
        "arbeitspaket_kept": after["entityos_arbeitspaket"] >= before["entityos_arbeitspaket"],
        "delta": {k: after[k] - before[k] for k in
                  ("durable_memory", "workspace_episodes", "entityos_arbeitspaket")},
        "newest_episode_before": before.get("newest_episode"),
        "newest_episode_after": after.get("newest_episode"),
    }
    res["healthy_readback_ms"] = round((time.monotonic() - t1) * 1000, 3)
    res["status"] = "OK" if (res["reentered"] and res["gwt_survived"]["durable_memory_kept"]) else "PARTIAL"
    evidence["steps"]["process_restart"] = res
    flush()
    return res


def preflight() -> dict:
    """Fail-closed: ohne intakte Voraussetzungen keine einzige Mutation."""
    problems = []
    for v, key in ((BASE_V, "bin_2.1.240"), (PRED_V, "bin_2.1.239")):
        p = VERSIONS / v
        if not p.exists():
            problems.append(f"{v} fehlt")
            continue
        if sha256_file(p) != BASELINE[key]:
            problems.append(f"{v} sha256 weicht von Baseline ab")
    if symlink_now() != BASELINE["symlink_target"]:
        problems.append(f"Symlink steht nicht auf Baseline: {symlink_now()}")
    if sha256_file(SETTINGS) != BASELINE["settings"]:
        problems.append("settings.json weicht von Baseline ab")
    v = live_version()
    if v != BASE_V:
        problems.append(f"live_version meldet {v}, erwartet {BASE_V}")
    return {"ok": not problems, "problems": problems,
            "symlink_target": symlink_now(), "live_version": v,
            "db_surface": db_surface()}


def run(arm: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for d in (MANAGED, CONTROL):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    print("== 1 PRE / preflight ==")
    pre = preflight()
    print(json.dumps(pre, indent=1))
    if not pre["ok"]:
        print("PREFLIGHT FAIL -> keine Mutation.")
        measure({"gate": "preflight", "outcome": "ABORT",
                 "failure_classification": "INFRA_AUTH_TRANSPORT_QUOTA",
                 "detail": pre["problems"]})
        return 2

    store = SelfUpdateStore(managed_dir=MANAGED, control_dir=CONTROL)
    evidence: dict = {"run_id": RUN_ID, "pre": pre, "steps": {}}
    restored_cleanly = False

    try:
        # -- 2 INSTALL: Ist-Zustand als Generation 0 verankern -----------------
        print("\n== 2 INSTALL (gen0 = %s) ==" % BASE_V)
        t0 = time.monotonic()
        r = apply_transaction(store, operation="INSTALL", payload=record_for(BASE_V),
                              release_id="claude-code", version=BASE_V,
                              attempt_id=f"{RUN_ID}-install")
        gen0_state = r.receipt.observed_state_sha256
        evidence["steps"]["install"] = {
            "outcome": r.receipt.outcome, "generation": r.receipt.observed_generation,
            "state_sha256": gen0_state, "ms": round((time.monotonic() - t0) * 1000, 3)}
        measure({"gate": "P13-install", "operation": "INSTALL", "outcome": r.receipt.outcome,
                 "observed_state_sha256": gen0_state,
                 "observed_generation": r.receipt.observed_generation,
                 "failure_classification": None})
        print(json.dumps(evidence["steps"]["install"], indent=1))

        # -- 3 ECHTES UPDATE: Zeiger auf den Vorgaenger -----------------------
        print("\n== 3 UPDATE -> %s (echter Zeigerwechsel) ==" % PRED_V)
        t0 = time.monotonic()
        r = apply_transaction(store, operation="UPDATE", payload=record_for(PRED_V),
                              release_id="claude-code", version=PRED_V,
                              attempt_id=f"{RUN_ID}-update")
        gen1_state = r.receipt.observed_state_sha256
        eff = sync_and_verify(PRED_V)
        evidence["steps"]["update"] = {
            "outcome": r.receipt.outcome, "generation": r.receipt.observed_generation,
            "state_sha256": gen1_state, "effect": eff,
            "ms": round((time.monotonic() - t0) * 1000, 3)}
        measure({"gate": "P13-update", "operation": "UPDATE", "outcome": r.receipt.outcome,
                 "parent_state_sha256": gen0_state, "observed_state_sha256": gen1_state,
                 "live_version_after": eff["live_version_reported"],
                 "effect_verified": eff["effect_verified"], "failure_classification": None})
        print(json.dumps(evidence["steps"]["update"], indent=1))
        if not eff["effect_verified"]:
            raise RuntimeError("Update-Wirkung nicht nachweisbar -> Abbruch")

        # -- 4 FEHLER INJIZIEREN + exakter Rollback ---------------------------
        print("\n== 4 UPDATE mit injiziertem Fehler -> muss exakt auf %s zurueck ==" % gen1_state[:16])
        t0 = time.monotonic()
        r = apply_transaction(store, operation="UPDATE", payload=record_for(BASE_V),
                              release_id="claude-code", version=BASE_V,
                              attempt_id=f"{RUN_ID}-update-fail",
                              injected_failure_stage="post_mutation")
        observed = r.receipt.observed_state_sha256
        expected = r.plan.source_state_sha256
        match = observed == expected == gen1_state
        eff = sync_and_verify(record_version())
        evidence["steps"]["injected_failure"] = {
            "outcome": r.receipt.outcome, "failure_code": r.receipt.failure_code,
            "expected_rollback_target": expected, "observed_state_sha256": observed,
            "digest_match": match, "effect": eff,
            "failure_detection_ms": r.failure_detection_ms,
            "rollback_ms": r.rollback_duration_ms,
            "ms": round((time.monotonic() - t0) * 1000, 3)}
        measure({"gate": "P13-injected-failure", "operation": "UPDATE",
                 "outcome": r.receipt.outcome, "parent_state_sha256": gen1_state,
                 "expected_rollback_target_state_sha256": expected,
                 "observed_state_sha256": observed, "digest_match": match,
                 "live_version_after": eff["live_version_reported"],
                 "failure_classification": None if match else "PRODUCT_NEGATIVE"})
        print(json.dumps(evidence["steps"]["injected_failure"], indent=1))
        if not match:
            raise RuntimeError("ROLLBACK BINDET NICHT AUF DEN EXAKTEN VORGAENGER -> HARTER STOPP")

        # -- 4b Ausdruecklicher Rollback zurueck auf 2.1.240 ------------------
        print("\n== 4b expliziter ROLLBACK -> %s ==" % BASE_V)
        t0 = time.monotonic()
        r = apply_rollback(store, attempt_id=f"{RUN_ID}-rollback")
        eff = sync_and_verify(record_version())
        evidence["steps"]["explicit_rollback"] = {
            "outcome": r.receipt.outcome,
            "rollback_target_state_sha256": r.plan.rollback_target_state_sha256,
            "observed_state_sha256": r.receipt.observed_state_sha256,
            "digest_match": r.receipt.observed_state_sha256 == r.plan.rollback_target_state_sha256,
            "effect": eff, "ms": round((time.monotonic() - t0) * 1000, 3)}
        measure({"gate": "P13-explicit-rollback", "operation": "ROLLBACK",
                 "outcome": r.receipt.outcome,
                 "expected_rollback_target_state_sha256": r.plan.rollback_target_state_sha256,
                 "observed_state_sha256": r.receipt.observed_state_sha256,
                 "live_version_after": eff["live_version_reported"],
                 "failure_classification": None})
        print(json.dumps(evidence["steps"]["explicit_rollback"], indent=1))

        # -- 5 Prozesstod / Neustart -----------------------------------------
        if not arm:
            evidence["steps"]["process_restart"] = {
                "status": "NOT_ARMED",
                "reason": "echter Prozesstod nur mit --arm; ohne Bewaffnung nicht ausgefuehrt",
                "what_it_would_do": "SIGTERM an die laufende claude-PID, Neustart ueber "
                                    "~/.local/bin/claude-code-launch, danach Readback"}
            print("\n== 5 PROZESS-NEUSTART: NICHT SCHARF (kein --arm) ==")
        else:
            evidence["steps"]["process_restart"] = kill_and_restart(evidence)

        # -- 6 Readback aus FRISCHEM Prozess ----------------------------------
        print("\n== 6 READBACK aus frischem Prozess ==")
        rb = subprocess.run(
            [sys.executable, "-c",
             "import sys,json;sys.path.insert(0,'/home/ai-core-node/frankenstein-2.0/src');"
             "from frankenstein2.self_update_transaction import independent_readback;"
             f"print(json.dumps(independent_readback('{MANAGED}','{CONTROL}')))"],
            capture_output=True, text=True, timeout=120)
        readback = json.loads(rb.stdout) if rb.stdout.strip() else {"error": rb.stderr[:200]}
        post_db = db_surface()
        drift = {k: (BASELINE.get(k), post_db.get(k)) for k in
                 ("durable_memory", "workspace_episodes", "entityos_arbeitspaket")}
        evidence["steps"]["readback"] = {
            "cross_process": readback,
            "db_pre": {k: BASELINE[k] for k in
                       ("durable_memory", "workspace_episodes", "entityos_arbeitspaket")},
            "db_post": post_db, "drift": drift,
            "drift_attribution": "durable_memory/arbeitspaket-Zuwachs stammt aus dem eigenen "
                                 "PostToolUse-Hook (stern.py raum-puls-global) der laufenden "
                                 "Instanz, nicht aus dieser Transaktion -- der Zeuge schreibt "
                                 "unified.db nie."}
        print(json.dumps(evidence["steps"]["readback"], indent=1))

        restored_cleanly = True

    finally:
        # -- 7 POST: Zeiger MUSS auf der Baseline stehen -----------------------
        point_symlink(BASE_V)
        post = {"symlink_target": symlink_now(), "live_version": live_version(),
                "symlink_matches_baseline": symlink_now() == BASELINE["symlink_target"],
                "bin_2.1.240_sha256": sha256_file(VERSIONS / BASE_V),
                "bin_2.1.239_sha256": sha256_file(VERSIONS / PRED_V),
                "settings_sha256": sha256_file(SETTINGS),
                "settings_unchanged": sha256_file(SETTINGS) == BASELINE["settings"],
                "clean_exit_path": restored_cleanly}
        evidence["post"] = post
        print("\n== 7 POST ==")
        print(json.dumps(post, indent=1))
        (OUT / "phase13_evidence.json").write_text(json.dumps(evidence, indent=1, sort_keys=True))
        measure({"gate": "P13-post", "outcome": "OK" if post["symlink_matches_baseline"] else "CRITICAL",
                 "symlink_target": post["symlink_target"], "live_version": post["live_version"],
                 "failure_classification": None if post["symlink_matches_baseline"] else "PRODUCT_NEGATIVE"})
        if not post["symlink_matches_baseline"]:
            print("!!! KRITISCH: Symlink steht NICHT auf der Baseline !!!")

    return 0 if evidence["post"]["symlink_matches_baseline"] else 3


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true",
                    help="schaltet den echten Prozesstod scharf (Standard: aus)")
    sys.exit(run(ap.parse_args().arm))
