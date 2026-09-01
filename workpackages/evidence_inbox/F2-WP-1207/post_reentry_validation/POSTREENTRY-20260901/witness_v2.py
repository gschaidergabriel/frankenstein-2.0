#!/usr/bin/env python3
"""Zeuge v2 — zweiter kontrollierter Process-Reentry (WP1207 post-reentry, H7).

Nur der Zeuge überlebt den Tod der Hauptinstanz. Ohne --arm tut er nichts.
Ablauf mit --arm: SIGTERM an die benannte PID -> Tod bestätigen -> Neustart
über den echten Launcher mit --resume derselben Sitzung -> neue PID per
Baseline-Differenz erkennen -> Trigger-Datei für die fortgesetzte Instanz
schreiben. Kein weiterer Eingriff.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 4179659
SESSION = "e0dc2e72-bbc8-477c-afd8-0e74072b2045"
OUT = Path("/tmp/wp1207-postreentry")
EVID = OUT / "reentry2_evidence.json"


def alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
    except Exception:
        return ""


def claude_pids() -> set[int]:
    out = set()
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                if (p / "comm").read_text().strip() == "claude" and p.stat().st_uid == os.getuid():
                    out.add(int(p.name))
            except Exception:
                pass
    return out


def flush(res: dict) -> None:
    EVID.write_text(json.dumps(res, indent=1, sort_keys=True))


def main() -> int:
    if "--arm" not in sys.argv:
        print("NICHT SCHARF — nur mit --arm. Ziel wäre:", TARGET, cmdline(TARGET)[:80])
        return 2
    res = {"target_pid": TARGET, "target_cmdline": cmdline(TARGET)[:120],
           "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "pids_before": sorted(claude_pids())}
    flush(res)
    if "claude" not in res["target_cmdline"]:
        res["status"] = "ABORT — Ziel ist kein claude-Prozess"
        flush(res)
        return 3
    os.kill(TARGET, 15)
    for _ in range(300):
        if not alive(TARGET):
            break
        time.sleep(0.1)
    res["died"] = not alive(TARGET)
    res["death_ms"] = None
    flush(res)
    if not res["died"]:
        res["status"] = "FAIL — überlebte SIGTERM"
        flush(res)
        return 4
    t1 = time.monotonic()
    cmd = ("cd /home/ai-core-node/seimensch-redesign && exec "
           "/home/ai-core-node/.local/bin/claude --dangerously-skip-permissions "
           f"--resume {SESSION}")
    subprocess.Popen(["gnome-terminal", "--title=Frankenstein (WP1207 post-reentry)", "--",
                      "bash", "-lc", cmd],
                     env=dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":0")),
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    new_pid = None
    for _ in range(900):
        time.sleep(0.1)
        neu = claude_pids() - set(res["pids_before"])
        if neu:
            new_pid = min(neu)
            break
    res["new_pid"] = new_pid
    res["reentry_ms"] = round((time.monotonic() - t1) * 1000, 3)
    res["new_cmdline"] = cmdline(new_pid)[:160] if new_pid else None
    res["status"] = "OK" if new_pid else "FAIL — keine neue Instanz"
    (OUT / "POST_PHASE.trigger").write_text(json.dumps(
        {"armed": True, "old_pid": TARGET, "new_pid": new_pid,
         "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
    flush(res)
    print(json.dumps({k: res[k] for k in ("status", "died", "new_pid", "reentry_ms")}))
    return 0 if new_pid else 5


if __name__ == "__main__":
    sys.exit(main())
