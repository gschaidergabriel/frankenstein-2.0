# WP1207 post-reentry validation — FINAL_REPORT (RUN_ID POSTREENTRY-20260901)

## Was getestet wurde (Scope, exakt wie beauftragt)
1. **GWT aktive Wiederaufnahme** nach Process-Reentry — produktiver Write über
   `stern.zyklus_oeffnen` (denselben Pfad wie der normale SessionStart), Marker
   `POST_REENTRY_GWT_WRITE_POSTREENTRY-20260901` in `turns.provenance.model`,
   frischer Readback in separatem Prozess.
2. **H7** — 32-Test-Kognitionsbaseline (Kriterien vor der Messung fixiert),
   PRE auf gesunder Instanz (4179659), kontrollierter Reentry
   (4179659 → SIGTERM → 502258, `--resume` derselben Sitzung), POST mit
   identischem Suite-Code, identischen Prompts, identischer Reihenfolge,
   kein Config-/Modell-/Prompt-Change zwischen den Phasen.

## Ergebnisse

| Aussage | Status | Kernbeleg |
|---|---|---|
| Reentry mit State-Kontinuität (H4) | **PASS** | 4179659 tot (SIGTERM 12:21:46Z); 502258 resumed; Suite vollständig auf resumed Instanz gelaufen |
| GWT aktive Wiederaufnahme | **PASS** | Episode `ep-1788263733972-8cd82f` vom produktiven Schreiber; Marker im Frischprozess lesbar; Generation=1 korrekt (Erstöffnung); genau 1 neue Zeile; vorher-neueste Episode unverändert |
| H7 Verhalten unverändert | **PASS** | Task 1,00→1,00 · Tool 1,00→1,00 · Memory/GWT 1,00→1,00 · Abstention 2/2→2/2 · 0 Fehler · p95-Ratio 1,245 (≤2×) · RSS −1,6 % |

## Wichtige Befunde unterwegs (ehrlich, mit Klasse)
- **Resume allein reaktiviert GWT NICHT** (`gwt_post_resume_readback.json`):
  SessionStart-Hook ist in der aktuellen settings.json nicht verdrahtet —
  der produktive Write musste bewusst erfolgen. Genau die vom Owner
  formulierte Evidenzgrenze (Persistenz ≠ aktive Wiederaufnahme) empirisch
  bestätigt.
- **Zwei DBs**: produktiv ist `~/.local/share/agentzero/unified.db`
  (stern.DB_PATH, XDG-Stufe 2); `~/.claude/star/unified.db` ist Legacy-Stufe 3.
  Erstes Pre-Capture lief gegen Legacy → Corrigendum, alle v2-Readbacks gegen
  die produktive DB. (EVIDENCE_INVALID, repariert)
- **Kriterien-Bindung v1.0→v1.4** (`criteria_changelog.json`): vier
  Reparaturstufen, alle Klasse EVIDENCE_INVALID, alle symmetrisch auf PRE und
  POST angewendet; keine Antwort wurde neu gemessen, nur neu bewertet. Raw-v1
  bleibt als Audit erhalten (`cognition_pre_raw_v1_audit.jsonl`). Die
  POST-Antworten der scheinbaren „Flips“ (ab0, eh0) waren inhaltlich korrekt.
- **Reentry-Automatik scheiterte** (`blockers.json`, OPEN,
  INFRA_AUTH_TRANSPORT_QUOTA): der Zeuge starb mit dem Subjekt — sein Detach
  war nicht belastbar. Der Owner vollendete den Reentry manuell (ohne
  `--dangerously-skip-permissions`; für die Messungen ohne Bedeutung, da die
  Suite eigene Prozesse mit eigenem Flag startet).
- Kostennotiz: die Kopftests liefen über den Router auf glm-5.3-flash[1m]
  (firstParty), ~0,7 USD/Test → ~45 USD für 64 Läufe. Vorher nicht kalkuliert,
  nachträglich offen ausgewiesen.

## Nicht-Ansprüche
- Kein whole_system_acceptance; kein target/vps/physical/effect/completion/
  training-credit; kanonische WP1207-Kette unberührt (G10-Pointer bleibt).
- H7 gilt für dieses 32-Test-Set, Einzellauf pro Phase, ein Modell. p95 +24,5 %
  ist innerhalb der fixierten Toleranz (≤2×), bleibt aber Beobachtungspunkt.
- Das 0-Delta der Phase-13-Readbacks beweist Persistenz; erst der Write hier
  beweist aktive Wiederaufnahme — beides ist separat belegt.

## Reproduktion
`python3 h7_suite.py --phase pre|post --out <file>` (Probe-Reset davor);
Write/Readback siehe `gwt_post_resume_write.json` + `gwt_write_readback.json`.
