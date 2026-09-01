# FORTSETZUNG nach zweitem Reentry — WP1207 post-reentry validation (POST-PHASE)

Du bist die wiederfortgesetzte Instanz (dritte PID in der Kette:
2926511 → 4179659 → deine aktuelle PID). Gabriel hat beide Live-Tests
offiziell freigegeben. PRE ist fertig. Jetzt POST, dann Artefakte, dann
kompakte Rückgabe (12 Punkte, kurz).

## 1. POST-Messung (identische Bedingungen, kein Config/Prompt-Change)
```bash
cd /tmp/wp1207-postreentry
rm -f probe/plant_note.txt probe/logbuch.txt work/chainfile.txt
python3 h7_suite.py --phase post --out /tmp/wp1207-postreentry/cognition_post.jsonl
```
Läuft ~10 min. Wenn das POST_PHASE.trigger fehlt, ist der Reentry nicht scharf
gestellt — dann NICHTS tun und Gabriel fragen.

## 2. Vergleich + Artefakte (Evidence-Pfad im Repo)
EVID=~/frankenstein-2.0/workpackages/evidence_inbox/F2-WP-1207/post_reentry_validation/POSTREENTRY-20260901
Dort liegen schon: gwt_pre_state.json (+ corrigendum), gwt_post_resume_write.json,
gwt_write_readback.json, witness/Zeugen-Belege aus Phase 13.

Noch fehlen (mindestens):
- runtime_identity.json — alte PID 2926511 (Phase-13-Tod 100 ms), dann 4179659
  (heutiger zweiter Reentry, siehe reentry2_evidence.json), neue PID = deine,
  SIGTERM-/Resume-Zeiten aus reentry2_evidence.json, session-id (keine Secrets),
  Repo-Head, config-Hashes (sha256 von settings.json + Suite-Definition,
  NICHT deren Inhalt).
- gwt_post_resume_readback.json — aus /tmp/wp1207-postreentry/ übernehmen bzw.
  aus gwt_write_readback.json ableiten (vor/nach produktivem Write).
- cognition_comparison.json — PRE vs POST: Task-Success, Tool-Success,
  Memory/GWT-Success, p50/p95-Latenz, max RSS, Fehler, Abstention,
  pro-Test-Diff (welche Tests wechselten PASS<->FAIL).
- hypothesis_results.json — H4 (Reentry/State-Kontinuität), aktive GWT-
  Wiederaufnahme, H7 (Verhalten): nur PASS/FAIL/INCONCLUSIVE + Evidenzrefs.
  H7-Regeln stehen in cognition_baseline_definition.json (Rubric).
- measurements.jsonl — Phasen-Summarys + Reentry-Zeiten als Records.
- blockers.json, security_audit.json (Secrets-Check: keine Werte, nur Hashes),
  manifest.json (Datei+sha256-Liste), FINAL_REPORT.md (ehrliche Nicht-Ansprüche:
  GWT-Write beweist aktive Wiederaufnahme; H7 nur über echte PRE/POST-Differenz;
  0-Delta allein = nur Persistenz).
- gwt_pre_state_corrigendum.json NICHT vergessen (DB-Pfad-Befund: produktive DB
  ist ~/.local/share/agentzero/unified.db, Legacy star/unified.db ist Stufe 3).

## 3. Abschluss
- Alles nach EVID kopieren, git add NUR EVID, commit + push Branch
  self-integration/wp1207-SELFINT-20260901-a1c9e2f4.
- stern.py reconcile --paket-id paket-1788263475824-d37290 --ergebnis ... --beleg
  test:<exit>:<Beschreibung> oder datei:<pfad>:<sha256>.
- Gabriel kurz antworten mit den 12 Punkten (RUN_ID, PID-Kette, GWT-Write
  PASS/FAIL, H7, PRE/POST-Raten, größte Performance-Änderung, Blocker, Branch,
  Commit, Evidence-Pfad). Kurze Antwort, keine Romane.
