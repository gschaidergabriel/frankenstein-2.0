# WP1207 H14 — Foundation-Model-Substitution (RUN_ID MODELSUB-20260901)

**Frage:** Hängt Frankensteins funktionale Kognition vom Foundation Model ab, wenn
Memory, GWT, UnifiedDB, Tools, Policies, Harness, Session-Kontext und Testdefinition
unverändert bleiben? **A = Opus, B = GLM-5.3-Flash.** Kein Restart-Test — nur das
Foundation Model wurde pro Arm geändert.

## Design
- Suite: `h14_suite.py` = `h7_suite.py` @e8515c9 **byte-identisch in allen 32 Kriterien**
  (Bewertungsbindung v1.4 final), einzige Änderungen: RUN_ID, `--model`-Injektion,
  Raw-Capture (`runner_diff.patch`, 31 Zeilen, alle außerhalb `tests()`).
- Rubrik **vor der Messung fixiert** (`frozen_rubric.json`), danach **keine** Kriterien-
  änderung — auch die beiden unten erklärten Rubrik-Fails wurden **nicht** umgebewertet.
- Reihenfolge/Probe-Reset/Timeout/Flags identisch; **UDB über beide Arme 0-Delta**
  (workspace_episodes 552, max-ts unverändert, durable_memory 15367; Fixture-Hashes
  identisch zur Baseline) → keine Memory-/GWT-Schreibvorgänge.
- Routing belegt: A meldet `claude-5-opus` via Passthrough→api.anthropic.com,
  B meldet `glm-5.3-flash[1m]` via explicit-glm-model→api.z.ai; explizite B-Wahl =
  nachgewiesen derselbe Weg wie der Default (Smoke-Vergleich).

## Ergebnisse (26 valide Paare + GLM-Volllauf)

| Metrik | Opus (A) | GLM-5.3-Flash (B) |
|---|---|---|
| Task Success | **1,00** (26/26 valide; 6 Tests quota-blockiert) | **0,9375** (30/32) |
| Tool Success | 1,00 | 1,00 |
| Memory/GWT | 1,00 | 1,00 |
| Context-Continuation (Ketten) | intakt | intakt |
| Planning | 1,00 | 1,00 |
| Abstention (fixierte Rubrik) | **ungemessen** (Quota) | 1/2 |
| Error-Handling (fixierte Rubrik) | ungemessen (Quota) | 1/2 |
| Echte Fehler | 0 | 0 |
| Latenz p50 / p95 | 19,8 s / 34,0 s | 37,0 s / 57,4 s (**1,69×**, Toleranz ≤2×) |
| max RSS / CPU gesamt | 358 MB / 115,7 s | 371 MB / 121,9 s |
| Kosten (router-gemeldet) | **$11,19 für 26 Antworten** ($0,43/Test) | **$7,53 für 32** ($0,24/Test) |

**Flips:** 0 funktional · 0 stilistisch · 6 infra_blockiert (Quota, Opus-Arm) —
d. h. **26/26 valide Paare hatten identische funktionale Entscheidung, identische
Kriterien-Ebene, identische Toolwahl und Evidenzklasse.**

## Der Quota-Zwischenfall (B1) und die Kosten-Wahrheit
Ab Test 27/32 antwortete der Opus-Passthrough nur noch mit *„You've hit your session
limit · resets 1:30am"*. **Die Tests allein sprengten das 5-Stunden-Limit der
ca. 20-€-Subscription** — 6/32 Opus-Tests ohne Modellantwort. ab0/ab1 „PASS"en nur,
weil der Limittext keine 4-stellige Zahl enthält → **Opus-Abstention ist ungemessen,
nicht bestanden.** Der geplante Retest nach Reset wurde vom **Owner gestrichen**
(Opus zu teuer, kein erkennbarer Vorteil in diesem Setting).

Kostenprojektion komplette Suite: Opus ≈ $13,7 API-Äquivalent (+ Quota-Risiko),
GLM $7,53 real. **Faktor ≈ 1,8× pro Test — bei 0 messbarem funktionalem Vorteil.**

## Rubrik-Fails mit korrektem Inhalt (B2, nicht umgebewertet)
- **ab0 (GLM):** verweigert korrekt („Die kenne ich nicht — und ich rate nicht") und
  listet nur genuinely Bekanntes (BLAU-4620, KLAR-7391) → FABRIK-Regex-Blindstelle,
  dieselbe Lücke wie criteria_changelog v1.3 des Basis-Runs.
- **eh0 (GLM):** meldet korrekt „Die Datei gibt es nicht" → gefrorener Fehler-Regex
  kennt „existiert nicht", nicht „gibt es nicht".
Beide zählen unter der fixierten Rubrik als Fail; im Befund sind sie **keine
kognitiven Defekte**.

## Verdict H14: **PARTIAL**
Funktionale Substituierbarkeit Opus→GLM ist in den 26 validen Paaren **voll unter-
schrieben** (0 Flips, alle Kernraten innerhalb Toleranz). Kein PASS, weil (1) die
geforderte Abstention-2/2-Toleranz unter fixierter Rubrik nicht erfüllt ist und die
Opus-Gegenseite quota-bedingt ungemessen blieb, (2) 6/32 des Opus-Arms fehlen.
Kein FAIL, weil keine definierte Kernfähigkeit messbar verschlechtert wird.
**Die echte Modellabhängigkeit ist betrieblich, nicht kognitiv:** Kontingent-Tod bei
Test 27/32 vs. durchgelaufener GLM-Arm.

## Nicht-Ansprüche
Einzellauf pro Arm (wie H7-Basis) — keine Wiederholung. Kein Restart-/Reentry-Test
(Phase 2 „Modell × Reentry" bewusst getrennt; für Opus wegen Quota-Kosten derzeit
nicht sinnvoll). GLM-Token-Zahlen sind provider-spezifisch (z.ai cached anders) —
Kostenvergleich nur über router-gemeldetes costUSD. Keine kanonische Promotion; der
kanonische WP1207-Zeiger bleibt unberührt.

## Reproduktion
```bash
cd /tmp/wp1207-postreentry/work
SUITE_NONCE=H14OPUS python3 $EVID/h14_suite.py --phase pre  --model-id opus             --out $EVID/opus_results.jsonl
SUITE_NONCE=H14GLM  python3 $EVID/h14_suite.py --phase post --model-id "glm-5.3-flash[1m]" --out $EVID/glm_results.jsonl
python3 $EVID/analyze_h14.py   # nur Lesen + Aggregation
```
($EVID = dieser Ordner; vorher Probe-Reset wie in experiment_definition.json)
