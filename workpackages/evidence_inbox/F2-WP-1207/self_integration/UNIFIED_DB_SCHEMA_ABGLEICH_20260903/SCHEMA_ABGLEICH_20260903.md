# F2-WP-1207 -- Schema-Abgleich: Sandbox vs. echte `unified.db` (2026-09-03)

Fortsetzung von `self-integration/wp1207-persistence-rebind-reentry-20260903`
(Gold-Test, 64/64 gruen). Dort offen gelassene Luecke ("die Sandbox-Schema
wurde nie gegen das echte Produktionsschema gehalten") wird hier geschlossen.

**Methode / Sicherheitsauflage eingehalten:** die echte
`~/.local/share/agentzero/unified.db` wurde ausschliesslich per
`sqlite3 "file:<pfad>?mode=ro" -readonly ...` geoeffnet -- kein
`INSERT`/`UPDATE`/`DELETE`/schreibendes `PRAGMA`. `~/frankenstein-repo`
wurde nicht editiert; nur ein **frischer** Klon von
`gschaidergabriel/frankenstein` diente dazu, `stern.py db-pfad-zeigen`
aufzurufen (reine Pfad-Aufloesung, kein DB-Zugriff durch dieses Kommando
selbst). Rohbelege in diesem Ordner:

- `db_pfad_zeigen_output.json` -- Pfad-Aufloesung
- `unified_db_schema.sql` + `unified_db_schema_sha256.txt` -- vollstaendiges
  `.schema`-Dump, read-only, mit SHA256 (unabhaengig zweimal reproduziert,
  identischer Hash `399cf879...9aa2dc1`, siehe Reconcile-Beleg)
- `unified_db_objektliste.txt` -- alle Tabellen/Indizes/Views/Trigger
  (`sqlite_master`), read-only
- `suche_identity_konzepte.txt` -- gezielte Suchlaeufe gegen die DDL

## 1. Befund: keine der Sandbox-Tabellen existiert real

Die im Gold-Test getestete Sandbox-Schema (`entity_identity`,
`installation_identity`, `host_binding`, `state_root_identity`,
`runtime_epoch` -- siehe `src/frankenstein2/entity_identity_store.py`,
`SANDBOX_IDENTITY_SCHEMA_SQL`) hat **kein einziges Gegenstueck** in der
echten `unified.db`. Weder die Tabellennamen noch ein `GRID10`-Konzept
tauchen im DDL auf (siehe `suche_identity_konzepte.txt`, Abschnitt 2: leer).
Das ist selbst ein valides, wichtiges Ergebnis -- die F2-WP-1207-
Identity-Schicht ist bislang vollstaendig SHADOW/additiv, nichts davon ist
in Produktion angekommen, auch nicht teilweise oder unter anderem Namen.

## 2. Naechstliegende reale Konzepte (kein Ersatz, nur Kontext)

Aus `suche_identity_konzepte.txt`, Abschnitt 4 -- keines davon deckt die
Sandbox-Semantik ab, aber sie sind die naechstverwandten realen Tabellen:

| reale Tabelle | Zweck laut DDL | Naehe zu Sandbox-Konzept |
|---|---|---|
| `entityos_wirte` | Host-Sichtungen (`wirt`, `boot_id`, `zuletzt_gesehen`, `gesund`) via Herzschlag | am naechsten an `HostBinding`, aber kein Status-Enum, keine `installation_id`, kein Rebind-/Supersede-Konzept, keine Cross-Instance-Invariante |
| `biometric_identity` | biometrische Consent-Records (`embedding_blob`, `consent_version`) | Name-Kollision im Wortsinn ("identity"), aber Domaene ist Bildwiedererkennung, nicht Entity/Installation |
| `visual_entity` | visuelle Objekterkennung (`visual_entity_id`, `current_label`) | ebenfalls "entity", aber Bild-Tracking, keine Verbindung zu Genesis/Installation/StateRoot |
| `system_bestand` | Inventar (Kategorie/Name/Version je Lauf) | am ehesten mit `RuntimeEpoch`-Beobachtung verwandt (Lauf-bezogen), aber kein Chaining, kein `predecessor_epoch_id` |
| `entityos_arbeitspaket` | Delegations-Arbeitspakete (dieses Paket selbst) | strukturell aehnliches "Zustand mit `stand`-Feld"-Muster, aber semantisch unabhaengiges Konzept |

Keine dieser Tabellen kann die Sandbox-Schema ersetzen oder erweitern --
sie loesen andere Probleme. Fazit: eine echte Ankunft der Identity-Schicht
braucht neue Tabellen, kein Reuse.

## 3. Vorgeschlagene additive Migration (NICHT ausgefuehrt)

Namensraum-Praefix `f2_` gewaehlt, weil (a) die echte DB durchgaengig
Subsystem-Praefixe nutzt (`vp_`, `sicht_`, `gw_`, `kb_`, `wm_`, `star_`,
`entityos_`, `eos_`) und `f2_` denselben Zweck fuer
"Frankenstein-2.0-Selbstintegration, SHADOW, nicht kanonisch" erfuellt, und
(b) es auch dann keine Kollision gibt, wenn die unpraefigierten Namen
spaeter fuer etwas anderes vergeben werden (heute waere `entity_identity`
etc. kollisionsfrei, siehe Abschnitt 1 -- der Praefix ist zusaetzliche
Absicherung, kein Kollisionsschutz-Zwang).

```sql
-- Additive, non-destructive proposal. NOT applied against unified.db.
-- Mirrors src/frankenstein2/entity_identity_store.py::SANDBOX_IDENTITY_SCHEMA_SQL
-- 1:1 in field shape, prefixed f2_, plus the partial-unique cross-instance
-- invariant from Teil 2 of this round.

CREATE TABLE IF NOT EXISTS f2_entity_identity (
    entity_id       TEXT PRIMARY KEY,
    schema          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    generated_by    TEXT NOT NULL,
    entropy_bytes   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS f2_installation_identity (
    installation_id TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES f2_entity_identity(entity_id),
    schema          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS f2_host_binding (
    binding_id      TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL REFERENCES f2_installation_identity(installation_id),
    host_id         TEXT NOT NULL,
    bound_at        TEXT NOT NULL,
    attestation     TEXT NOT NULL,
    status          TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'SUPERSEDED', 'REVOKED')),
    schema          TEXT NOT NULL
);

-- Cross-instance invariant (Teil 2 of this round): at most one ACTIVE
-- binding per installation, enforced by the engine, not by caller code.
CREATE UNIQUE INDEX IF NOT EXISTS ux_f2_host_binding_one_active_per_installation
    ON f2_host_binding (installation_id)
    WHERE status = 'ACTIVE';

CREATE INDEX IF NOT EXISTS ix_f2_host_binding_installation_status
    ON f2_host_binding (installation_id, status);

CREATE TABLE IF NOT EXISTS f2_state_root_identity (
    state_root_id       TEXT PRIMARY KEY,
    installation_id     TEXT NOT NULL REFERENCES f2_installation_identity(installation_id),
    state_digest_sha256  TEXT NOT NULL,
    schema               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS f2_runtime_epoch (
    runtime_epoch_id     TEXT PRIMARY KEY,
    state_root_id        TEXT NOT NULL REFERENCES f2_state_root_identity(state_root_id),
    installation_id      TEXT NOT NULL REFERENCES f2_installation_identity(installation_id),
    host_binding_id      TEXT NOT NULL REFERENCES f2_host_binding(binding_id),
    started_at           TEXT NOT NULL,
    predecessor_epoch_id TEXT REFERENCES f2_runtime_epoch(runtime_epoch_id),
    termination_reason   TEXT,
    schema               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_f2_runtime_epoch_state_root
    ON f2_runtime_epoch (state_root_id);
CREATE INDEX IF NOT EXISTS ix_f2_runtime_epoch_predecessor
    ON f2_runtime_epoch (predecessor_epoch_id);
```

### Warum das additiv/risikofrei waere (wenn es je ausgefuehrt wird)

- Ausschliesslich `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT
  EXISTS` -- keine `ALTER TABLE` auf einer bestehenden Tabelle, keine
  bestehende Spalte, kein bestehender Index wird beruehrt.
- Keine Fremdschluessel VON einer bestehenden Tabelle IN diese neuen
  Tabellen und umgekehrt -- vollstaendig isolierter Teilgraph, referenziell
  nur innerhalb der `f2_`-Gruppe selbst.
- `entityos_arbeitspaket`, `entityos_wirte` und alle anderen bestehenden
  Tabellen bleiben unveraendert; keine Namenskollision (Abschnitt 1).
- Diese Migration ist ein **Vorschlag/Dokument**, keine ausgefuehrte
  Aenderung. Sie wurde nicht gegen `unified.db` laufen gelassen -- weder in
  diesem Durchlauf noch je zuvor. Aktivierung bleibt eine separate,
  spaetere, von Gabriel autorisierte Entscheidung (gleiche Regel wie fuer
  jede Aktivierung von F2-WP-1207-Code gegen `stern.py`/`witness_v3.py`).

## 4. Umfang der Migration

5 neue Tabellen, 1 partieller UNIQUE-Index (die Cross-Instance-Invarianz),
3 unterstuetzende Indizes. Kein bestehendes Objekt der 260+ Tabellen/
Indizes/Views/Triggern in `unified_db_objektliste.txt` wird veraendert.
