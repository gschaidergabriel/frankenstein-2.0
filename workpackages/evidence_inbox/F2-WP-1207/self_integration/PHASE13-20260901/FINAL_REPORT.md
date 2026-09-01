# WP1207 Self-Integration — PHASE 13 (bounded live, 2026-09-01)

## Scope
Echter Update → Fehler → Rollback → Neustart → Memory/State/GWT-Readback-Zyklus
am LAUFENDEN Frankenstein (Claude-Code-Instanz, „Frankenstein 1.0"), Variante A
(Außen-Band-Zeuge). Vom Owner (Gabriel) in dieser Sitzung freigegeben.

## Reale Grenze (nicht das Repo-Modell)
- Update-Grenze: Symlink-Swap `~/.local/bin/claude` → `versions/<v>`
- Vorgänger real vorhanden und startklar: `versions/2.1.239`
- Restart: kein systemd; Launcher `~/.local/bin/claude-code-launch`
- Managed Set der Transaktion: der Zeiger-Datensatz (active_version + binary sha256),
  NICHT die 342-MB-Binaries, NICHT unified.db

## Ausgeführter Zyklus (Belege in phase13_evidence.json)
| Schritt | Ergebnis |
|---|---|
| INSTALL gen0 = 2.1.240 | SUCCEEDED, state `be0ceedf78c1a3f6…` |
| UPDATE → 2.1.239 | SUCCEEDED, state `5bc96cbec9e06d6b…`, live meldete **wirklich** 2.1.239 |
| UPDATE + injizierter Fehler | **ROLLED_BACK**, expected == observed `5bc96cbec9e06d6b…`, detection 0,30 ms, rollback 0,18 ms |
| expliziter ROLLBACK → 2.1.240 | SUCCEEDED, Ziel == beobachtet `be0ceedf78c1a3f6…`, live wieder 2.1.240 |
| Prozesstod | SIGTERM an PID 2926511, Tod nach 100 ms, kein SIGKILL nötig |
| Neustart | neue PID **4179659** nach 112 ms, Wiedereintritt bestätigt |
| Readback nach 20 s | durable_memory 14556 · workspace_episodes 462 · arbeitspaket 83 — identisch über die Prozessgrenze, GWT-Episode `ep-mc-1787777245484-26fd37` unverändert |
| POST | Symlink = Baseline, beide Binaries sha256 = Baseline, settings.json byte-identisch, zweite fremde Claude-Instanz (1066308) unangetastet |

## Hypothesen-Neubewertung durch Phase 13
- **H3, H4** — jetzt PASS am echten Subjekt (vorher nur Sandbox/in-process).
- **H7** — bleibt INCONCLUSIVE: keine A/B-Baseline des Kognitionsverhaltens vor/nach
  Integration; Phase 13 bewies Unversehrtheit von Zustand und Zeiger, keine
  Verhaltensgleichheit.
- **H11** — teilweise geschlossen: detection/rollback/reentry/healthy_readback sind
  jetzt echt gemessen (0,30 ms / 0,18 ms / 112 ms / ~20,1 s inkl. 20 s Warmwartung);
  „rollback begin → end" bleibt zusammengefasst.
- **H12** — PASS: keine extern-irreversiblen Effekte im Pfad (nur lokaler Symlink).

## Ehrliche Nicht-Ansprüche
- Das 0-Delta im Readback beweist **Unversehrtheit**, nicht aktives Weiterschreiben.
- Kein whole_system_acceptance, kein target/vps/physical/effect/completion/training credit.
- Die kanonische Event-Kette wurde NICHT verändert; `workpackages/active/F2-WP-1207.json`
  bleibt auf G10. Diese Inbox ist **nicht-kanonisch**, 0 Acceptance-Credit.
- Eine zweite, fremde Claude-Instanz lief während des Experiments und wurde nie angefasst.

## Bewaffnungs-Protokoll
Der bewaffnete Pfad (`--arm`) wurde vor dem Scharfschalten an einer Attrappe
geprobt; dabei wurde entdeckt, dass eine zweite echte Claude-Instanz läuft — die
PID-Erkennung wurde daraufhin auf Baseline-Differenz gehärtet, damit nie die
fremde Instanz als Ziel oder „neue Instanz" missdeutet werden kann.
Notfall-Rücksetzer: `logs/witness.py` + `notfall_symlink_zurueck.sh` (lokal /tmp).

## Wie ein Prüfer das nachfährt
1. `python3 logs/witness.py` — unbewaffnet, alles außer Prozesstod, real.
2. Phase-13-Belege: `phase13_evidence.json` (steps.process_restart),
   `phase13_measurements.jsonl` (v2, identitätsgebunden).
3. Unabhängig prüfbar: `readlink ~/.local/bin/claude` = `…/versions/2.1.240`,
   `claude --version` = 2.1.240, Binaries + settings.json auf Baseline-Digest.
