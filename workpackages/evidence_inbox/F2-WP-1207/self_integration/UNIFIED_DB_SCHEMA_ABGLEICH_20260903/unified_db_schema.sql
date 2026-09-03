CREATE TABLE active_turns(session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),user_id TEXT NOT NULL REFERENCES users(user_id),turn_id TEXT NOT NULL UNIQUE REFERENCES turns(turn_id),episode_id TEXT NOT NULL UNIQUE REFERENCES workspace_episodes(episode_id),causal_id TEXT NOT NULL UNIQUE,generation INTEGER NOT NULL,resource_refs TEXT NOT NULL DEFAULT '[]',effect_id TEXT REFERENCES effects(effect_id),outcome TEXT,workspace_selected INTEGER NOT NULL DEFAULT 0,started_at REAL NOT NULL);
CREATE TABLE anreicherung (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            artikel_id   TEXT NOT NULL,
            quelle_url   TEXT,
            art          TEXT,
            auszug       TEXT,
            geholt_am    TEXT,
            hash         TEXT
        );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE architekt_engine_log(log_id TEXT PRIMARY KEY,ts REAL NOT NULL,prozess TEXT NOT NULL,engine TEXT NOT NULL,bahn TEXT,modell TEXT,glm_fehlgeschlagen_grund TEXT,dauer_ms REAL);
CREATE TABLE architekt_engine_zustand(id INTEGER PRIMARY KEY CHECK(id=1),glm_bestaetigt INTEGER NOT NULL DEFAULT 0,serie_fehler INTEGER NOT NULL DEFAULT 0,zuletzt_aktualisiert REAL);
CREATE TABLE artikel (
            id TEXT PRIMARY KEY,
            art TEXT NOT NULL,
            titel TEXT,
            quelle TEXT,
            quell_hash TEXT,
            datum TEXT,
            metadaten TEXT,       -- JSON, verbatim source metadata
            offene_fragen TEXT,   -- JSON array
            belegt INTEGER,
            erzeugt_am TEXT
        , duenn INTEGER DEFAULT 0, zuletzt_bearbeitet TEXT, zeitquelle TEXT, wirt TEXT, zuletzt_von TEXT, von_quelle TEXT, logical_id TEXT, id_quelle TEXT, epistemic_class TEXT, status TEXT, scope TEXT, tags TEXT, konfidenz REAL, projekt TEXT, projekt_art TEXT, sphaere TEXT, herkunft TEXT DEFAULT 'gemessen' CHECK (herkunft IN ('gemessen','nutzer')), verfallen INTEGER DEFAULT 0, protected INTEGER DEFAULT 0);
CREATE TABLE artikel_sphaere (
            artikel_id TEXT NOT NULL,
            sphaere TEXT NOT NULL,
            beleg TEXT,
            PRIMARY KEY (artikel_id, sphaere)
        );
CREATE TABLE artikel_suchtext (
                id INTEGER PRIMARY KEY,
                artikel_id TEXT NOT NULL UNIQUE,
                titel TEXT,
                text TEXT,
                blase TEXT,
                indiziert TEXT NOT NULL
            );
CREATE TABLE bahn_lage (
        schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL, zeit TEXT NOT NULL);
CREATE TABLE bahn_lauf (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT NOT NULL, art TEXT NOT NULL, bahn TEXT, modell TEXT,
        ziel_id TEXT, dauer_ms REAL, http INTEGER,
        token_ein INTEGER, token_aus INTEGER,
        ergebnis TEXT NOT NULL,        -- angenommen | verworfen | fehler
        pruefung TEXT,                 -- warum verworfen
        antwort TEXT
    );
CREATE TABLE bahn_livestreak(
  bahn TEXT PRIMARY KEY,
  serie INTEGER NOT NULL DEFAULT 0,
  zuletzt_fehler REAL,
  zuletzt_ergebnis TEXT
);
CREATE TABLE bahn_nutzung(
  bahn TEXT NOT NULL,
  prozess TEXT NOT NULL,
  tag TEXT NOT NULL,
  anfragen INTEGER NOT NULL DEFAULT 0,
  token INTEGER NOT NULL DEFAULT 0,
  fehler INTEGER NOT NULL DEFAULT 0,
  zuletzt REAL NOT NULL,
  PRIMARY KEY(bahn, prozess, tag)
);
CREATE TABLE bearbeitung (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artikel_id TEXT NOT NULL,
        feld TEXT NOT NULL,
        alt_wert TEXT,
        neu_wert TEXT,
        autor TEXT,
        zeit TEXT NOT NULL,
        herkunft TEXT NOT NULL DEFAULT 'nutzer' CHECK (herkunft = 'nutzer')
    );
CREATE TABLE causal_episodes(causal_id TEXT PRIMARY KEY,episode_id TEXT REFERENCES workspace_episodes(episode_id),effect_id TEXT REFERENCES effects(effect_id),observation_turn_id TEXT REFERENCES turns(turn_id),outcome_hash TEXT,credit REAL NOT NULL DEFAULT 0,reentered INTEGER NOT NULL DEFAULT 0,ts REAL NOT NULL);
CREATE TABLE checkpoints(checkpoint_id TEXT PRIMARY KEY,ts REAL NOT NULL,state_hash TEXT NOT NULL,note TEXT NOT NULL);
CREATE TABLE datei (
                id INTEGER PRIMARY KEY,
                pruefsumme TEXT NOT NULL UNIQUE,
                titel TEXT,                 -- Dateiname des ERSTEN gesehenen Fundorts (nur Anzeige)
                art TEXT NOT NULL,          -- 'text' | 'binaer'
                volltext_indiziert INTEGER NOT NULL DEFAULT 0,
                groesse INTEGER,
                text TEXT,                  -- Volltext, EINMAL gespeichert
                indiziert TEXT NOT NULL
            );
CREATE TABLE durable_memory(memory_id TEXT PRIMARY KEY,kind TEXT NOT NULL,subject TEXT NOT NULL,value TEXT NOT NULL,source_turn_id TEXT REFERENCES turns(turn_id),user_id TEXT,ts REAL NOT NULL,provenance TEXT NOT NULL);
CREATE TABLE effects(effect_id TEXT PRIMARY KEY,episode_id TEXT REFERENCES workspace_episodes(episode_id),user_id TEXT NOT NULL,capability TEXT NOT NULL,target TEXT NOT NULL,argv TEXT,requested_generation INTEGER NOT NULL,status TEXT NOT NULL,outcome TEXT,ts REAL NOT NULL,verified_at REAL);
CREATE TABLE entityos_arbeitspaket (
  paket_id   TEXT PRIMARY KEY,
  besteller  TEXT NOT NULL,          -- gabriel | andreas, aus dem gepruefsten Zustand
  session_id TEXT NOT NULL,
  auftrag    TEXT NOT NULL,          -- Caveman: was zu tun ist
  womit      TEXT,                   -- die Sache: Datei, Dienst, Tabelle
  warum      TEXT,                   -- die Begruendung, damit ein Mensch pruefen kann
  stand      TEXT NOT NULL,          -- offen | laeuft | fertig | gescheitert | abgelehnt
  ergebnis   TEXT,
  beleg      TEXT,                   -- WOMIT belegt der Ausfuehrer, dass es getan ist
  erstellt   REAL NOT NULL,
  geaendert  REAL NOT NULL
);
CREATE TABLE entityos_artikel_zuordnung(
  artikel_id TEXT PRIMARY KEY,
  gehoert TEXT NOT NULL,           -- gabriel | andreas | gemeinsam | unbekannt
  grund TEXT NOT NULL,
  sicherheit REAL NOT NULL,        -- 0..1
  erfasst REAL NOT NULL
);
CREATE TABLE entityos_erfolge(
  id TEXT PRIMARY KEY,
  art TEXT NOT NULL,               -- erfolg | fehlschlag
  titel TEXT NOT NULL,
  wirkung TEXT,                    -- was es konkret geaendert hat
  beleg TEXT NOT NULL,             -- Messung/Beobachtung. Ohne Beleg kein Eintrag.
  gehoert TEXT,                    -- gabriel | andreas | gemeinsam
  seit_zero INTEGER NOT NULL DEFAULT 0,
  datum TEXT NOT NULL,
  erfasst REAL NOT NULL
);
CREATE TABLE entityos_profil(
  user_id TEXT NOT NULL,
  feld TEXT NOT NULL,
  wert TEXT NOT NULL,
  herkunft TEXT NOT NULL,          -- eigner | iar.frank.ink | abgeleitet | gemessen
  beleg TEXT,
  erfasst REAL NOT NULL,
  PRIMARY KEY(user_id, feld)
);
CREATE TABLE entityos_projekte(
  projekt TEXT PRIMARY KEY,
  gehoert TEXT,                    -- gabriel | andreas | gemeinsam
  gebaut_von TEXT,                 -- kann abweichen: Besitz ist nicht Urheberschaft
  stand TEXT NOT NULL,             -- laufend | abgeschlossen | gescheitert | ruht
  erfolg TEXT,                     -- erfolgreich | nicht_erfolgreich | offen
  seit_zero INTEGER NOT NULL DEFAULT 0,
  beschreibung TEXT,
  beleg TEXT,
  herkunft TEXT NOT NULL,
  erfasst REAL NOT NULL
);
CREATE TABLE entityos_wirte(
  wirt TEXT PRIMARY KEY,
  gehoert_zu TEXT,
  erste_sichtung REAL NOT NULL,
  zuletzt_gesehen REAL NOT NULL,
  generation INTEGER,
  gesund INTEGER NOT NULL DEFAULT 0,
  boot_id TEXT,
  module TEXT NOT NULL DEFAULT '{}',
  quelle TEXT NOT NULL DEFAULT 'herzschlag'
);
CREATE TABLE eos_architekt_quittungen(quittung_id TEXT PRIMARY KEY,ts REAL NOT NULL,hypothese_id TEXT NOT NULL,hypothese_quelle TEXT NOT NULL,hypothese_text TEXT NOT NULL,zweig TEXT,reproduziert INTEGER NOT NULL,befund TEXT,sicherer_rahmen INTEGER,rahmen_grund TEXT,testboden_vorher TEXT,testboden_nachher TEXT,nicht_schlechter INTEGER,nicht_schlechter_grund TEXT,bericht_vorher_hash TEXT,bericht_nachher_hash TEXT,kanarie_status TEXT,urteil TEXT NOT NULL,live_geschaltet INTEGER NOT NULL DEFAULT 0,hinweis TEXT);
CREATE TABLE eos_bewertungen(bewertung_id TEXT PRIMARY KEY,turn_id TEXT NOT NULL,session_id TEXT NOT NULL,user_id TEXT NOT NULL,wert INTEGER NOT NULL CHECK(wert IN (-1,1)),frage_turn_id TEXT,frage_hash TEXT,frage_laenge INTEGER,antwort_hash TEXT NOT NULL,antwort_laenge INTEGER NOT NULL,modell TEXT,ts REAL NOT NULL,UNIQUE(turn_id, user_id));
CREATE TABLE eos_bug_hypothesen(bug_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,ts REAL NOT NULL,beschreibung TEXT NOT NULL,wo TEXT,status TEXT NOT NULL DEFAULT 'OFFEN' CHECK(status IN ('OFFEN','REPRODUZIERT','WIDERLEGT','BEHOBEN')),befund TEXT);
CREATE TABLE fehler (
            id TEXT PRIMARY KEY,
            art TEXT NOT NULL CHECK (art IN ('sql', 'shell', 'python', 'daten', 'provenienz', 'methode')),
            ausloeser_muster TEXT NOT NULL,
            was_passiert TEXT NOT NULL,
            wie_erkannt TEXT NOT NULL,
            wie_vermieden TEXT NOT NULL,
            schwere TEXT NOT NULL CHECK (schwere IN ('hoch', 'mittel', 'niedrig')),
            beleg TEXT NOT NULL,
            quelle TEXT NOT NULL,
            erkannt_am TEXT,
            bestaetigt_durch TEXT
        );
CREATE TABLE folgerung (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            art TEXT NOT NULL CHECK (art IN ('hypothese','implikation','lehre')),
            aussage TEXT NOT NULL,
            begruendung TEXT,
            gilt_fuer TEXT NOT NULL,
            autor TEXT,
            zeit TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen','gestuetzt','widerlegt','abgeloest')),
            widerlegt_durch INTEGER REFERENCES folgerung(id)
        , konfidenz REAL);
CREATE TABLE folgerung_beleg (
            folgerung_id INTEGER NOT NULL REFERENCES folgerung(id),
            beleg_art TEXT NOT NULL CHECK (beleg_art IN
                ('protokoll','artikel','messung','problem','kante','datei')),
            beleg_id TEXT NOT NULL,
            PRIMARY KEY (folgerung_id, beleg_art, beleg_id)
        );
CREATE VIRTUAL TABLE fts_index_artikel USING fts5(titel, text, content='artikel_suchtext', content_rowid='id')
/* fts_index_artikel(titel,text) */;
CREATE TABLE IF NOT EXISTS 'fts_index_artikel_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'fts_index_artikel_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'fts_index_artikel_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'fts_index_artikel_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE VIRTUAL TABLE fts_index_datei USING fts5(titel, text, content='datei', content_rowid='id')
/* fts_index_datei(titel,text) */;
CREATE TABLE IF NOT EXISTS 'fts_index_datei_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'fts_index_datei_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'fts_index_datei_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'fts_index_datei_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TABLE fundort (
                datei_id INTEGER NOT NULL,  -- FK auf datei.id (robuster Join)
                pruefsumme TEXT NOT NULL,   -- wie vom Eigentuemer verlangt, zur Anzeige/Direktabfrage
                wirt TEXT NOT NULL,
                pfad TEXT NOT NULL,
                blase TEXT,                 -- NULL = Kern/unbeschraenkt
                geaendert TEXT,
                PRIMARY KEY (wirt, pfad)
            );
CREATE TABLE gedaechtnis_ausbeute(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, rolle TEXT, bahn TEXT, modell TEXT,  genommen INTEGER NOT NULL, verworfen INTEGER NOT NULL, gruende TEXT);
CREATE TABLE grabstein (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        was TEXT NOT NULL,
        ziel_id TEXT NOT NULL,
        autor TEXT,
        zeit TEXT NOT NULL,
        grund TEXT,
        inhalt_hash TEXT NOT NULL
    );
CREATE TABLE graph_edges(edge_id TEXT PRIMARY KEY,src TEXT NOT NULL,dst TEXT NOT NULL,kind TEXT NOT NULL,provenance TEXT NOT NULL);
CREATE TABLE graph_kante(
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            confidence REAL,
            graph_epoch INTEGER NOT NULL,
            source_kante_art TEXT NOT NULL,
            beleg TEXT,
            built_at TEXT NOT NULL, verfallen INTEGER, protected INTEGER,
            PRIMARY KEY(source_node_id, target_node_id, edge_type)
        ) WITHOUT ROWID;
CREATE TABLE graph_knoten(
            node_id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,
            external_id TEXT NOT NULL,
            titel TEXT,
            quelle TEXT,
            source_content_hash TEXT,
            datum TEXT,
            metadaten TEXT,
            graph_epoch INTEGER NOT NULL,
            built_at TEXT NOT NULL
        , status TEXT, verfallen INTEGER, protected INTEGER);
CREATE TABLE graph_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
CREATE TABLE graph_nodes(node_id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,source_table TEXT NOT NULL,source_id TEXT NOT NULL);
CREATE TABLE gw_absicht(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, frage TEXT,  werkzeuge TEXT, aussenwirkung TEXT, angekuendigt TEXT,  verdacht TEXT, grund TEXT);
CREATE TABLE gw_ausstrahlung(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, artikel_id TEXT, wert REAL);
CREATE TABLE gw_herkunft(  memory_id TEXT PRIMARY KEY, turn_id TEXT, session_id TEXT, ts REAL NOT NULL,  fremdtext INTEGER NOT NULL DEFAULT 0, werkzeuge TEXT);
CREATE TABLE gw_lernen(  merkmal TEXT NOT NULL, artikel_id TEXT NOT NULL,  boost REAL NOT NULL DEFAULT 0, n INTEGER NOT NULL DEFAULT 0,  belohnt INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL,  PRIMARY KEY(merkmal, artikel_id));
CREATE TABLE gw_wettbewerb(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, artikel_id TEXT, rang INTEGER,  salienz REAL, relevanz REAL, neuheit REAL, wert REAL,  zugelassen INTEGER, gewaehlt INTEGER);
CREATE TABLE heim_belege(beleg_id TEXT PRIMARY KEY, ts REAL NOT NULL, effect_id TEXT, causal_id TEXT,user_id TEXT NOT NULL, wirt TEXT NOT NULL, aktion TEXT NOT NULL,nutzlast_sha256 TEXT NOT NULL, urteil TEXT NOT NULL);
CREATE TABLE kante (
            von TEXT NOT NULL,
            nach TEXT NOT NULL,
            art TEXT NOT NULL,    -- which source field produced this edge
            beleg TEXT, konfidenz REAL, erzeugt_am TEXT, zeitquelle TEXT, verfallen INTEGER DEFAULT 0, protected INTEGER DEFAULT 0,           -- provenance: quelle path of the asserting article
            PRIMARY KEY (von, nach, art)
        );
CREATE TABLE kb_auftrag (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            prozess           TEXT NOT NULL,
            nutzlast          TEXT NOT NULL,
            zustand           TEXT NOT NULL DEFAULT 'offen'
                              CHECK (zustand IN ('offen','laeuft','fertig','unbedienbar')),
            versuche          INTEGER NOT NULL DEFAULT 0,
            letzter_grund     TEXT,
            gesperrte_bahnen  TEXT,
            angelegt          TEXT NOT NULL,
            geaendert         TEXT NOT NULL,
            -- unbedienbar OHNE Grund ist verboten: sonst weiss niemand mehr,
            -- warum etwas liegen blieb, und der Auftrag ist faktisch verloren.
            CHECK (zustand <> 'unbedienbar'
                   OR (letzter_grund IS NOT NULL AND TRIM(letzter_grund) <> ''))
        );
CREATE TABLE kb_buchung (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            zeit                   TEXT NOT NULL,
            konto                   TEXT NOT NULL REFERENCES kb_konto(konto),
            zugang                   TEXT NOT NULL REFERENCES kb_zugang(zugang),
            menge                    REAL NOT NULL CHECK (menge >= 0),
            einheit                  TEXT,
            zweck                    TEXT,
            batch_id                 TEXT,
            taetigkeit_id             INTEGER,
            schluessel_hinweis        TEXT,
            quelle                   TEXT NOT NULL DEFAULT 'buchen'
                                     CHECK (quelle IN ('buchen','synthetic')),
            roh_hash                 TEXT UNIQUE
        );
CREATE TABLE kb_konto (
            konto                 TEXT PRIMARY KEY,
            anzeige                TEXT NOT NULL,
            vorrang                 INTEGER NOT NULL,
            hat_eigenes_limit        INTEGER NOT NULL DEFAULT 0
                                     CHECK (hat_eigenes_limit IN (0,1)),
            eigenes_limit_wert       REAL,
            eigenes_limit_einheit    TEXT,
            eigenes_limit_fenster    TEXT,
            warnung_an              TEXT NOT NULL,
            wirt                    TEXT,
            angelegt                TEXT NOT NULL
        );
CREATE TABLE kb_verdrahtung (
            prozess         TEXT PRIMARY KEY,
            bahn_erst       TEXT,
            bahn_zweit      TEXT,
            bahn_dritt      TEXT,
            hoechstanteil   REAL NOT NULL
                            CHECK (hoechstanteil > 0.0 AND hoechstanteil <= 1.0),
            begruendung     TEXT NOT NULL CHECK (LENGTH(TRIM(begruendung)) > 0),
            max_je_lauf     INTEGER,
            schema_pflicht  INTEGER,
            angelegt        TEXT NOT NULL
        );
CREATE TABLE kb_warnung (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            zeit                TEXT NOT NULL,
            konto                TEXT,
            zugang                TEXT,
            art                  TEXT NOT NULL CHECK (art IN (
                                 'ueber_norm', 'reset_naehert_sich',
                                 'verbrauch_ohne_fortschritt',
                                 'mehrdeutiger_schluessel',
                                 'kein_limit_kein_muster')),
            text                 TEXT NOT NULL,
            kennzahlen_json       TEXT
        );
CREATE TABLE kb_zugang (
            zugang                    TEXT PRIMARY KEY,
            anzeige                    TEXT NOT NULL,
            einheit                    TEXT,
            fenster_dauer_sekunden      INTEGER,
            fenster_limit                REAL,
            woche_limit                  REAL,
            tag_limit                    REAL,
            minute_limit                 REAL,
            tageswechsel_stunde          INTEGER,
            spitzenzeit_json             TEXT,
            geteilt_mit                  TEXT,
            besonderheit                TEXT NOT NULL,
            mehrdeutiger_schluessel      INTEGER NOT NULL DEFAULT 0
                                         CHECK (mehrdeutiger_schluessel IN (0,1)),
            angelegt                    TEXT NOT NULL
        , modell TEXT, token_minute_limit REAL, token_tag_limit REAL, zustand TEXT NOT NULL DEFAULT 'ungeprueft', zustand_grund TEXT, zustand_gemessen TEXT, grenzen_quelle TEXT, unbekannt_felder TEXT, unbekannt_grund TEXT, kann_embedding INTEGER, kann_schema INTEGER, kann_batch INTEGER, ausgereizt INTEGER NOT NULL DEFAULT 0, konten_anzahl INTEGER, konten_getrennt INTEGER, schluessel_namen TEXT);
CREATE TABLE kommentar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artikel_id TEXT NOT NULL,
        text TEXT NOT NULL,
        autor TEXT,
        zeit TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'offen'
            CHECK (status IN ('offen','beantwortet','gestuetzt','widerlegt','unentscheidbar')),
        antwort_folgerung_id INTEGER REFERENCES folgerung(id)
    );
CREATE TABLE kuration (
            artikel_id           TEXT PRIMARY KEY,
            quelle                TEXT,
            ereignis              TEXT,
            klasse                TEXT NOT NULL,
            alt_hash              TEXT,
            neu_hash              TEXT,
            alt_groesse           INTEGER,
            alt_zeilen            INTEGER,
            neu_groesse           INTEGER,
            neu_zeilen            INTEGER,
            erkannt_am            TEXT NOT NULL,
            zuletzt_geprueft_am   TEXT NOT NULL,
            noetig                TEXT NOT NULL,
            status                TEXT NOT NULL DEFAULT 'offen'
        );
CREATE TABLE leases(resource TEXT PRIMARY KEY,holder TEXT NOT NULL,generation INTEGER NOT NULL,expires_at REAL NOT NULL,nonce TEXT NOT NULL);
CREATE TABLE memory_tabelle (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artikel_id TEXT NOT NULL,
                    memory_text TEXT NOT NULL,
                    quelle TEXT,
                    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
                    priority REAL DEFAULT 1.0,
                    tag TEXT
                , user_id TEXT);
CREATE TABLE messung(
            id TEXT PRIMARY KEY,
            bauteil TEXT NOT NULL,
            quelle TEXT NOT NULL,
            zeile_hash TEXT NOT NULL,
            was TEXT NOT NULL,
            wert REAL NOT NULL,
            einheit TEXT NOT NULL,
            zeit TEXT NOT NULL,
            wirt TEXT,
            instanz TEXT,
            roh TEXT NOT NULL
        );
CREATE TABLE messung_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE mv_claude_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT,
    session_id TEXT,
    user_id TEXT,
    warm INTEGER NOT NULL DEFAULT 0,
    round_no INTEGER,
    num_turns INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    cost_usd REAL,
    duration_ms_claude_code REAL,
    duration_ms_api REAL,
    wall_ms REAL,
    created_at REAL NOT NULL
);
CREATE TABLE mv_eval_runs (
    run_id TEXT PRIMARY KEY,
    iteration INTEGER NOT NULL,
    prompt_version TEXT NOT NULL,
    eval_set_size INTEGER NOT NULL,
    pass_rate REAL NOT NULL,
    avg_faithfulness REAL NOT NULL,
    avg_readability REAL NOT NULL,
    fabrication_count INTEGER NOT NULL,
    notes TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE mv_prestage_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE mv_prestage_turns (
    prestage_id TEXT PRIMARY KEY,
    turn_id TEXT,
    session_id TEXT,
    user_id TEXT,
    raw_prompt TEXT NOT NULL,
    world_digest TEXT,
    connected_systems_json TEXT,
    caveman_prompt TEXT NOT NULL,
    tool_selection_json TEXT,
    memory_artefacts_json TEXT,
    outsourced_json TEXT,
    user_intent TEXT,
    watch_out TEXT,
    hypotheses_json TEXT,
    counter_hypotheses_json TEXT,
    prestage_model TEXT,
    prestage_receipt_json TEXT,
    created_at REAL NOT NULL
, epistemik_json TEXT, epistemik_bekannt_n INTEGER, epistemik_unbekannt_n INTEGER, routing_key TEXT, self_adapted INTEGER, translation_raw_fallback INTEGER, self_reported_gap INTEGER, self_reported_gap_marker TEXT, outcome_ok INTEGER, korpus_treffer_n INTEGER, effects_evidence_json TEXT);
CREATE TABLE mv_translation_log (
    translation_id TEXT PRIMARY KEY,
    turn_id TEXT,
    prestage_id TEXT,
    caveman_original TEXT NOT NULL,
    german_translation TEXT NOT NULL,
    translator_model TEXT,
    translator_receipt_json TEXT,
    faithfulness_score REAL,
    readability_score REAL,
    judge_model TEXT,
    judge_verdict_json TEXT,
    fabrication_flag INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE mv_uebersetzung_ausfall(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, fehler TEXT);
CREATE TABLE om_hypothese_implikation(
    id INTEGER PRIMARY KEY,
    artikel_id TEXT NOT NULL,
    hypothese_id TEXT,
    hypothese_text TEXT NOT NULL,
    text TEXT NOT NULL,
    konfidenz REAL NOT NULL,
    modell TEXT NOT NULL,
    erzeugt_am TEXT NOT NULL
);
CREATE TABLE om_lauf(
    id INTEGER PRIMARY KEY,
    zeit TEXT NOT NULL,
    schritt TEXT NOT NULL,
    ok INTEGER NOT NULL,
    anzahl INTEGER NOT NULL DEFAULT 0,
    ms INTEGER NOT NULL DEFAULT 0,
    hinweis TEXT
);
CREATE TABLE om_projekt(
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    art TEXT NOT NULL,              -- 'feld' (aus artikel.projekt) | 'cluster' (Ko-Vorkommen/Graph)
    eltern_id TEXT,                 -- NULL = keine Elternbeziehung belegt
    konfidenz REAL NOT NULL,
    begruendung TEXT NOT NULL,
    anzahl_artikel INTEGER NOT NULL DEFAULT 0,
    aktualisiert_am TEXT NOT NULL
);
CREATE TABLE om_projekt_kante(
    a_id TEXT NOT NULL,
    b_id TEXT NOT NULL,
    staerke REAL NOT NULL,
    beleg TEXT NOT NULL,
    aktualisiert_am TEXT NOT NULL,
    PRIMARY KEY(a_id, b_id)
);
CREATE TABLE om_projekt_mitglied(
    artikel_id TEXT NOT NULL,
    projekt_id TEXT NOT NULL,
    konfidenz REAL NOT NULL,
    PRIMARY KEY(artikel_id, projekt_id)
);
CREATE TABLE om_skizze(
    artikel_id TEXT PRIMARY KEY,
    mermaid TEXT NOT NULL,
    quelle TEXT NOT NULL,           -- 'mechanisch:<feld>' oder 'modell:<name>'
    erzeugt_am TEXT NOT NULL
);
CREATE TABLE om_zusammenfassung(
    artikel_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    modell TEXT NOT NULL,
    erzeugt_am TEXT NOT NULL
);
CREATE TABLE problem (
            id TEXT PRIMARY KEY,
            bauteil TEXT,
            quelle TEXT NOT NULL,
            zeile_hash TEXT NOT NULL,
            text TEXT NOT NULL,
            art TEXT NOT NULL CHECK (art IN ('problem','huerde','risiko','offene_frage')),
            erkannt_am TEXT,
            status TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen','geloest')),
            geloest_am TEXT,
            geloest_durch TEXT
        );
CREATE TABLE pu_lage (
        schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL, zeit TEXT NOT NULL
    );
CREATE TABLE pu_takt (
        folge INTEGER PRIMARY KEY,
        clay_id TEXT NOT NULL,
        zeit TEXT NOT NULL,
        monoton REAL NOT NULL,
        boot_id TEXT NOT NULL,
        art TEXT NOT NULL,
        delta INTEGER NOT NULL DEFAULT 0,
        kosten_us REAL,
        modellaufrufe INTEGER NOT NULL DEFAULT 0,
        werkzeugaufrufe INTEGER NOT NULL DEFAULT 0,
        detail TEXT
    );
CREATE TABLE retrieval_entrypoint_policy(entry_key TEXT PRIMARY KEY,capital REAL NOT NULL DEFAULT 0.0,reward_ema REAL NOT NULL DEFAULT 0.0,pulls INTEGER NOT NULL DEFAULT 0,updated_at REAL NOT NULL);
CREATE TABLE retrieval_episodes(retrieval_id TEXT PRIMARY KEY,turn_id TEXT NOT NULL UNIQUE REFERENCES turns(turn_id),episode_id TEXT NOT NULL UNIQUE REFERENCES workspace_episodes(episode_id),causal_id TEXT NOT NULL UNIQUE,session_id TEXT NOT NULL REFERENCES sessions(session_id),user_id TEXT NOT NULL REFERENCES users(user_id),generation INTEGER NOT NULL,policy_version INTEGER NOT NULL,mode TEXT NOT NULL CHECK(mode IN ('SHADOW','ACTIVE')),query_hash TEXT NOT NULL,query_token_hashes TEXT NOT NULL,selected_memory_ids TEXT NOT NULL,shadow_memory_ids TEXT NOT NULL,entry_keys TEXT NOT NULL,budget_chars INTEGER NOT NULL,chars_selected INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('PRESENT','UNKNOWN')),ts REAL NOT NULL);
CREATE TABLE retrieval_feedback(receipt_id TEXT PRIMARY KEY,retrieval_id TEXT NOT NULL REFERENCES retrieval_episodes(retrieval_id) ON DELETE CASCADE,causal_id TEXT NOT NULL,generation INTEGER NOT NULL,credit REAL NOT NULL,signal_class TEXT NOT NULL,ts REAL NOT NULL);
CREATE TABLE retrieval_policy_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),mode TEXT NOT NULL CHECK(mode IN ('SHADOW','ACTIVE')),policy_version INTEGER NOT NULL,updated_at REAL NOT NULL);
CREATE TABLE schluessel_lage (
        schluessel      TEXT PRIMARY KEY,
        zuletzt_geprueft TEXT,
        http            INTEGER,
        ms              REAL,
        einordnung      TEXT,      -- MECHANISCH, nur hier steht die Wahrheit
        seit            TEXT,      -- wann dieser Zustand begann
        fehlertext      TEXT,
        modell_meinung  TEXT,      -- VORSCHLAG eines Modells, keine Tatsache
        geprueft_gesamt INTEGER DEFAULT 0,
        gesund_gesamt   INTEGER DEFAULT 0
    , sonde TEXT, rest_kontingent TEXT);
CREATE TABLE schluessel_lauf (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT NOT NULL, schluessel TEXT NOT NULL,
        http INTEGER, ms REAL, einordnung TEXT, fehlertext TEXT
    , sonde TEXT, rest_kontingent TEXT);
CREATE TABLE sessions(session_id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(user_id),created_at REAL NOT NULL,updated_at REAL NOT NULL,generation INTEGER NOT NULL DEFAULT 1,terminal_name TEXT NOT NULL UNIQUE);
CREATE TABLE sicht_arbeitsraum (
  eintrag_id    TEXT PRIMARY KEY,
  aufnahme_id   TEXT NOT NULL,
  kandidat_id   TEXT NOT NULL,
  objekt_id     TEXT,
  hypothese_id  TEXT,
  turn_id       TEXT,
  session_id    TEXT,
  angemeldet_am REAL NOT NULL,
  -- Die Zuendmerkmale aus der Architektur, Abschnitt „G": Neuheit,
  -- Vorhersagefehler, Ungewissheit, Zielbezug, Risiko.
  zuendungsgrund TEXT NOT NULL DEFAULT '{}',
  zuendung      INTEGER NOT NULL DEFAULT 0,
  broadcast_id  TEXT,
  abgelehnt_grund TEXT,
  entschieden_am REAL
);
CREATE TABLE sicht_aufnahme (
  aufnahme_id   TEXT PRIMARY KEY,
  datei_id      TEXT,
  quelle_id     TEXT NOT NULL,
  quelle_klasse TEXT NOT NULL,
  bild_hash     TEXT,
  breite        INTEGER,
  hoehe         INTEGER,
  user_id       TEXT,
  turn_id       TEXT,
  causal_id     TEXT,
  session_id    TEXT,
  stufe         TEXT NOT NULL,
  stufe_version TEXT,
  -- ⭐ Das ist die Rueckwaertsrichtung des Abrufs: was der Bestand VOR der
  -- Analyse schon wusste und was deshalb in den Messauftrag ging. Ohne diese
  -- Spalte laesst sich spaeter nicht mehr sagen, ob eine Erkennung aus dem
  -- Bild kam oder aus der Erwartung (NR-RET-014, Prior-Dominanz).
  abruf_kontext TEXT,
  abruf_treffer INTEGER DEFAULT 0,
  dauer_ms      REAL,
  ergebnis      TEXT,
  fehlergrund   TEXT,
  begonnen_am   REAL NOT NULL,
  beendet_am    REAL
);
CREATE TABLE sicht_evidenz (
  evidenz_id        TEXT PRIMARY KEY,
  aufnahme_id       TEXT NOT NULL,
  quelle_id         TEXT NOT NULL,
  quelle_epoche     INTEGER NOT NULL,
  aufnahme_zeit     REAL,
  eingang_zeit      REAL NOT NULL,
  -- Nicht die Bildpunkte, nur ihr Fingerabdruck. Das Bild bleibt in der
  -- Dateiablage; eine Datenbank ist der falsche Ort fuer Bilddaten, und ein
  -- Hash reicht, um spaeter zu beweisen, dass es dasselbe Bild war.
  rohbezug_hash     TEXT,
  raum_bezug        TEXT,
  transformation    TEXT NOT NULL,
  transformation_version TEXT NOT NULL,
  beobachtungsart   TEXT NOT NULL,
  wert              TEXT NOT NULL,
  bottom_up_praezision REAL,
  -- ⚠️ NR-RET-012: YOLO-Konfidenz, CLIP-Kosinus und OCR-Guete sind NICHT
  -- vergleichbar. Diese Spalte sagt, gegen welche Kalibrierung die Zahl
  -- gelesen werden darf. Steht hier 'UNKALIBRIERT', ist die Zahl nur
  -- innerhalb derselben Transformation ordnend, nicht ueber sie hinweg.
  kalibrierung_ref  TEXT NOT NULL DEFAULT 'UNKALIBRIERT',
  -- Konstant. Eine Spalte, die immer dasselbe sagt, ist hier Absicht: sie
  -- steht in jeder Zeile, die jemand liest.
  autoritaet        TEXT NOT NULL DEFAULT 'NUR_BEOBACHTUNG',
  erzeugt_am        REAL NOT NULL
);
CREATE TABLE sicht_hypothese (
  hypothese_id  TEXT PRIMARY KEY,
  aufnahme_id   TEXT NOT NULL,
  anker         TEXT NOT NULL,
  art           TEXT NOT NULL,
  -- ⭐⭐ F57, mechanisch: mengenwertige Lesarten
  -- [{"lesart":..., "p":..., "aus":[evidenz_id,...]}, ...].
  -- Eine Kaskadenstufe darf die Gewichte verschieben, aber keine Lesart
  -- entfernen — siehe verengen(). In einer vierstufigen Kaskade ist ein
  -- frueher Ausschluss an vier Stellen nicht mehr einholbar.
  lesarten      TEXT NOT NULL,
  lesarten_geschlossen INTEGER NOT NULL DEFAULT 0,
  stuetzende_evidenz    TEXT NOT NULL DEFAULT '[]',
  widersprechende_evidenz TEXT NOT NULL DEFAULT '[]',
  bestand_stuetze       TEXT NOT NULL DEFAULT '[]',
  sensor_praezision     REAL,
  prior_praezision      REAL,
  kontext_verstaerkung  REAL,
  -- Anteil der Stuetzung, der aus dem Bestand statt aus dem Bild kommt.
  -- NR-RET-014: ein starker Prior kann schwache Sensorik dominieren und die
  -- Trefferquote heben, waehrend er falsche Vorannahmen mit durchwinkt.
  -- Deshalb als Zahl gefuehrt und nicht als Gefuehl.
  prior_dominanz        REAL,
  zuversicht    REAL,
  zustand       TEXT NOT NULL,
  revision      INTEGER NOT NULL DEFAULT 1,
  vorgaenger_id TEXT,
  abgeloest_von TEXT,
  erzeugt_am    REAL NOT NULL
);
CREATE TABLE sicht_kaskade_stufe (
  stufe         TEXT PRIMARY KEY,
  rang          INTEGER NOT NULL,
  zweck         TEXT NOT NULL,
  fehlerfall    TEXT NOT NULL,
  aktiv         INTEGER NOT NULL DEFAULT 0,
  gemessen_ms   REAL,
  messgrundlage TEXT NOT NULL,
  quelle        TEXT
);
CREATE TABLE sicht_merkmal (
  merkmal_id   TEXT PRIMARY KEY,
  aufnahme_id  TEXT NOT NULL,
  anker        TEXT NOT NULL,
  verfahren    TEXT NOT NULL,
  dimension    INTEGER NOT NULL,
  vektor       TEXT NOT NULL,
  rahmen_hash  TEXT,
  erzeugt_am   REAL NOT NULL
);
CREATE TABLE sicht_nutzung (
  nutzung_id    TEXT PRIMARY KEY,
  eintrag_id    TEXT,
  objekt_id     TEXT,
  evidenz_id    TEXT,
  turn_id       TEXT,
  causal_id     TEXT,
  nutzungsart   TEXT NOT NULL,
  beleg         TEXT,
  -- ⭐ Wer das festgestellt hat. „MECHANISCH" heisst: eine Regel hat es
  -- geprueft. Ein Modell, das behauptet, es habe etwas benutzt, ist kein
  -- Beleg — genau davor warnt NR-RET-017.
  festgestellt_von TEXT NOT NULL,
  erzeugt_am    REAL NOT NULL
);
CREATE TABLE sicht_sichtbarkeit (
  sichtbarkeit  TEXT PRIMARY KEY,
  vorlage_en    TEXT NOT NULL,
  messbar       INTEGER NOT NULL,
  belegt_abwesenheit INTEGER NOT NULL,
  zerfall       TEXT NOT NULL,
  warum         TEXT NOT NULL
);
CREATE TABLE sicht_weltobjekt (
  objekt_id     TEXT PRIMARY KEY,
  quelle_id     TEXT NOT NULL,
  semantische_identitaet TEXT,
  erst_aufnahme_id TEXT NOT NULL,
  erst_gesehen_am  REAL NOT NULL,
  vorgaenger_id TEXT,
  teilung_von   TEXT,
  verschmelzung_von TEXT,
  provenienz    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE sicht_weltobjekt_stand (
  stand_id      TEXT PRIMARY KEY,
  objekt_id     TEXT NOT NULL,
  gueltig_ab    REAL NOT NULL,
  gueltig_bis   REAL,
  sichtbarkeit  TEXT NOT NULL,
  -- Nicht schmueckend: der Grund unterscheidet „VERDECKT, weil eine Kiste
  -- davor steht" von „VERDECKT, weil wir es annehmen". Ohne Grund ist ein
  -- Sichtbarkeitszustand eine Behauptung.
  sichtbarkeit_grund TEXT,
  raum_zustand  TEXT,
  merkmale_mit_evidenz TEXT NOT NULL DEFAULT '[]',
  beziehungen_mit_evidenz TEXT NOT NULL DEFAULT '[]',
  letzte_positive_evidenz_epoche INTEGER,
  letzte_explizit_negative_epoche INTEGER,
  ungewissheit  REAL,
  stuetzende_hypothese_id TEXT,
  aufnahme_id   TEXT,
  turn_id       TEXT,
  causal_id     TEXT,
  erzeugt_am    REAL NOT NULL
);
CREATE TABLE sicht_zuordnung (
  zuordnung_id  TEXT PRIMARY KEY,
  aufnahme_id   TEXT NOT NULL,
  anker         TEXT NOT NULL,
  objekt_id     TEXT,
  entscheidung  TEXT NOT NULL,
  begruendung   TEXT NOT NULL,
  aehnlichkeit  REAL,
  abstand_zum_zweiten REAL,
  verfahren     TEXT NOT NULL,
  verfahren_version TEXT,
  erzeugt_am    REAL NOT NULL
);
CREATE TABLE speicher_rueckweg(pfad TEXT PRIMARY KEY, erfasst REAL NOT NULL, warum TEXT, modelle INTEGER, verzeichnis TEXT NOT NULL);
CREATE TABLE speicherwacht_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, belegt_prozent REAL, frei_gb REAL, stufe TEXT, gehandelt INTEGER NOT NULL, befreit_gb REAL, bericht TEXT, df_gb REAL, gezaehlt_gb REAL, luecke_gb REAL, nicht_zaehlbar TEXT, bilanz_urteil TEXT);
CREATE TABLE taetigkeit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wirt TEXT,
    instanz TEXT,
    sitzung TEXT,
    zeit TEXT,
    werkzeug TEXT,
    ziel_pfad TEXT,
    aktion TEXT,
    ergebnis TEXT,
    quelle TEXT,
    zeile_nr INTEGER,
    roh_hash TEXT UNIQUE
);
CREATE TABLE taetigkeit_kante (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taetigkeit_id INTEGER NOT NULL,
    artikel_id TEXT NOT NULL,
    art TEXT NOT NULL,
    beleg TEXT,
    UNIQUE(taetigkeit_id, artikel_id, art)
);
CREATE TABLE turn_compressions(
    compression_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(turn_id),
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    level INTEGER NOT NULL,
    level_name TEXT NOT NULL,
    content TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    derived_from_turn_ids TEXT NOT NULL,
    extractor TEXT NOT NULL,
    prompt_version TEXT,
    created_at REAL NOT NULL,
    UNIQUE(turn_id, level)
);
CREATE TABLE turns(turn_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(session_id),user_id TEXT NOT NULL REFERENCES users(user_id),ordinal INTEGER NOT NULL,ts REAL NOT NULL,role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),content TEXT NOT NULL,fidelity TEXT NOT NULL DEFAULT 'full',compression_generation INTEGER NOT NULL DEFAULT 0,resource_refs TEXT NOT NULL DEFAULT '[]',causal_refs TEXT NOT NULL DEFAULT '[]',provenance TEXT NOT NULL DEFAULT '{}',UNIQUE(session_id, ordinal));
CREATE TABLE users(user_id TEXT PRIMARY KEY,display_name TEXT NOT NULL,rights TEXT NOT NULL DEFAULT 'equal',clerk_subject TEXT UNIQUE);
CREATE TABLE vd_aufnahme (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit          TEXT NOT NULL,
        strom         TEXT NOT NULL,
        neu           INTEGER NOT NULL,
        geaendert     INTEGER NOT NULL,
        offen_gesamt  INTEGER NOT NULL,
        schwelle      INTEGER NOT NULL,
        ausgeloest    INTEGER NOT NULL
    );
CREATE TABLE vd_gesehen (
        strom            TEXT NOT NULL,
        quell_id         TEXT NOT NULL,
        zeit             TEXT NOT NULL,
        anreicherung_id  INTEGER,
        PRIMARY KEY (strom, quell_id)
    );
CREATE TABLE vd_grenze (
        zugang            TEXT PRIMARY KEY,
        anzahl_429        INTEGER NOT NULL DEFAULT 0,
        erste_429         TEXT,
        letzte_429        TEXT,
        letzte_wartezeit  REAL,
        rufe_ohne_429     INTEGER NOT NULL DEFAULT 0,
        bemerkung         TEXT
    );
CREATE TABLE vd_lauf (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit             TEXT NOT NULL,
        strom            TEXT NOT NULL,
        quellen          INTEGER NOT NULL,
        bahn             TEXT,
        modell           TEXT,
        http             INTEGER,
        dauer_ms         REAL,
        token_ein        INTEGER,
        token_aus        INTEGER,
        ergebnis         TEXT NOT NULL,
        grund            TEXT,
        detail           TEXT,
        anreicherung_id  INTEGER,
        verdichtung_id   TEXT
    );
CREATE TABLE vd_strom (
        strom            TEXT PRIMARY KEY,
        schwelle         INTEGER NOT NULL,
        rate_je_stunde   REAL,
        rate_beleg       TEXT,
        aktiv            INTEGER NOT NULL DEFAULT 1,
        angelegt         TEXT NOT NULL,
        letzte_pruefung  TEXT,
        letzter_lauf     TEXT
    , portion INTEGER);
CREATE TABLE vp_alias (
      alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
      target_kind TEXT, target_id TEXT, alias_norm TEXT,
      alias_class TEXT, confidence REAL, source_epoch INTEGER
    );
CREATE TABLE vp_alias_df (
  wort TEXT PRIMARY KEY,
  df INTEGER NOT NULL,          -- in wie vielen Aliassen kommt das Wort vor
  gebaut_am TEXT
);
CREATE VIRTUAL TABLE vp_alias_fts USING fts5(alias_norm, content='vp_alias', content_rowid='alias_id')
/* vp_alias_fts(alias_norm) */;
CREATE TABLE IF NOT EXISTS 'vp_alias_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'vp_alias_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'vp_alias_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'vp_alias_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TABLE vp_alias_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE vp_datei_fts USING fts5(titel, datei_id UNINDEXED)
/* vp_datei_fts(titel,datei_id) */;
CREATE TABLE IF NOT EXISTS 'vp_datei_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'vp_datei_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'vp_datei_fts_content'(id INTEGER PRIMARY KEY, c0, c1);
CREATE TABLE IF NOT EXISTS 'vp_datei_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'vp_datei_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE VIRTUAL TABLE vp_dir_fts USING fts5(verzeichnisname, datei_id UNINDEXED)
/* vp_dir_fts(verzeichnisname,datei_id) */;
CREATE TABLE IF NOT EXISTS 'vp_dir_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'vp_dir_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'vp_dir_fts_content'(id INTEGER PRIMARY KEY, c0, c1);
CREATE TABLE IF NOT EXISTS 'vp_dir_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'vp_dir_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TABLE vp_edge_lern (
      query_class TEXT, edge_art TEXT,
      gewicht REAL DEFAULT 0, beobachtungen INTEGER DEFAULT 0,
      zuletzt_gelernt TEXT, gesehen INTEGER DEFAULT 0, genutzt INTEGER DEFAULT 0,
      PRIMARY KEY(query_class, edge_art)
    );
CREATE TABLE vp_edge_lern_backup_preflift(
  query_class TEXT,
  edge_art TEXT,
  gewicht REAL,
  beobachtungen INT,
  zuletzt_gelernt TEXT
);
CREATE TABLE vp_ereignis (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      zeit TEXT, art TEXT, detail TEXT
    );
CREATE TABLE vp_erfolgsmarke (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL, frage TEXT, region TEXT, anker TEXT,
  getragen INTEGER,              -- 1 = der Eintritt hat zur Antwort gefuehrt
  quelle TEXT                    -- wer die Marke gesetzt hat
);
CREATE TABLE vp_gesehen (
      lauf TEXT, record_id TEXT, zeit TEXT
    );
CREATE TABLE vp_karte_region (
  version INTEGER NOT NULL, region TEXT NOT NULL,
  projekt TEXT, art TEXT, artikel_n INTEGER,
  landmarken TEXT,               -- JSON: die am staerksten vernetzten Artikel
  PRIMARY KEY(version, region)
);
CREATE TABLE vp_karte_version (
  version INTEGER PRIMARY KEY AUTOINCREMENT,
  gebaut_am TEXT NOT NULL,
  anlass TEXT,
  regionen INTEGER, landmarken INTEGER, wegweiser INTEGER,
  korpus_artikel INTEGER, korpus_kanten INTEGER,
  verhaeltnis REAL,              -- Kartenzeilen / Korpuszeilen. Muss klein bleiben.
  erkundungsanteil REAL DEFAULT 0.0,   -- 0.0 = Gegenmittel gegen das Echo NICHT aktiv
  dauer_s REAL
);
CREATE TABLE vp_karte_wegweiser (
  version INTEGER NOT NULL, wort TEXT NOT NULL, region TEXT NOT NULL,
  staerke REAL NOT NULL,         -- Lift: wie stark zeigt dieses Wort auf die Region
  PRIMARY KEY(version, wort, region)
);
CREATE TABLE vp_lese_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      zeit TEXT, ort_id TEXT, paket_id TEXT, bytes INTEGER, erlaubt INTEGER, grund TEXT
    );
CREATE TABLE vp_paket_log (
      paket_id TEXT PRIMARY KEY, zeit TEXT, epoch_sekunden INTEGER,
      frage TEXT, orte_json TEXT
    );
CREATE TABLE vp_plan_cache (
      sig_hash TEXT PRIMARY KEY,
      source_epoch INTEGER, graph_epoch INTEGER,
      anchor_ids TEXT, gap_terms TEXT,
      plan_json TEXT,
      erzeugt_am TEXT, treffer_anzahl INTEGER DEFAULT 0, zuletzt_getroffen TEXT
    );
CREATE TABLE vp_sitzung (
      id TEXT PRIMARY KEY,
      rechner TEXT NOT NULL,
      rolle TEXT NOT NULL,           -- z.B. 'clayverse' / 'gabriel' / 'andreas'
      gestartet REAL NOT NULL,
      lebenszeichen REAL NOT NULL
    );
CREATE TABLE vp_snapshot (
      snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
      erzeugt_am TEXT, state_hash TEXT,
      normals_score TEXT, normals_bestanden INTEGER,
      beobachtungen_gesamt INTEGER, edge_lern_snapshot TEXT
    , source_epoch INTEGER, graph_epoch INTEGER);
CREATE TABLE vp_weg (
  von TEXT NOT NULL,
  nach TEXT NOT NULL,
  art TEXT,                          -- Kantenart, aus der der Weg entstand
  nutzung INTEGER NOT NULL DEFAULT 0,
  getragen INTEGER NOT NULL DEFAULT 0,
  guete REAL NOT NULL DEFAULT 0.0,   -- 0 = langsame Strasse, 1 = Autobahn
  sitzungen TEXT,                    -- verschiedene Sitzungen, die ihn trugen (JSON-Liste)
  tunnel INTEGER NOT NULL DEFAULT 0,
  erste_nutzung REAL NOT NULL,
  letzte_nutzung REAL NOT NULL,
  PRIMARY KEY(von, nach)
);
CREATE TABLE wa_ereignis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT, art TEXT, ziel TEXT, detail TEXT, quelle TEXT
    );
CREATE TABLE wa_grenze (
        id INTEGER PRIMARY KEY AUTOINCREMENT, zeit TEXT, detail TEXT
    );
CREATE TABLE wa_snapshot (
        ziel TEXT PRIMARY KEY,
        zeit TEXT, rchar INTEGER, wchar INTEGER, cpu_ticks INTEGER,
        active_enter TEXT, active_state TEXT
    );
CREATE TABLE wake_events(
    coalesce_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    subject_ref TEXT,
    ts REAL NOT NULL,
    first_ts REAL NOT NULL,
    count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE weg(
            id TEXT PRIMARY KEY,
            ursprung TEXT NOT NULL,
            ziel_wirt TEXT NOT NULL,
            ziel_dienst TEXT,
            ziel_pfad TEXT,
            transport TEXT NOT NULL,
            proxyjump_via TEXT,
            konto TEXT,
            befehl TEXT NOT NULL,
            tor TEXT NOT NULL,
            darf TEXT NOT NULL,
            schritte TEXT,
            erreichbar INTEGER NOT NULL,
            fehler TEXT,
            zuletzt_bewiesen TEXT NOT NULL,
            beleg TEXT NOT NULL
        );
CREATE TABLE wk_aufgabe (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        art           TEXT NOT NULL,
        artikel_id    TEXT NOT NULL,
        wert          REAL NOT NULL DEFAULT 0,
        zustand       TEXT NOT NULL DEFAULT 'offen'
                      CHECK (zustand IN ('offen','laeuft','fertig','verworfen','unbedienbar')),
        versuche      INTEGER NOT NULL DEFAULT 0,
        letzter_grund TEXT,
        angelegt      TEXT NOT NULL,
        geaendert     TEXT NOT NULL,
        UNIQUE (art, artikel_id)
    );
CREATE TABLE wm_cast_regel (
        von_domaene  TEXT NOT NULL,
        nach_domaene TEXT NOT NULL,
        erlaubt      INTEGER NOT NULL,
        bedingung    TEXT,
        beleg        TEXT NOT NULL,
        kandidat     TEXT NOT NULL,
        offen        INTEGER NOT NULL DEFAULT 1,
        erzeugt_am   TEXT NOT NULL,
        PRIMARY KEY (von_domaene, nach_domaene)
    );
CREATE TABLE wm_guss_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit         TEXT NOT NULL,
        von_domaene  TEXT NOT NULL,
        nach_domaene TEXT NOT NULL,
        ergebnis     TEXT NOT NULL,
        grund        TEXT NOT NULL,
        bedingung    TEXT,
        beleg        TEXT,
        gegenstand   TEXT,
        kandidat     TEXT NOT NULL,
        offen        INTEGER NOT NULL DEFAULT 1
    );
CREATE TABLE wm_lesart (
        lesart_id    TEXT PRIMARY KEY,
        artikel_id   TEXT NOT NULL,
        achse        TEXT NOT NULL,
        wert         TEXT,
        kontext_json TEXT NOT NULL DEFAULT '{}',
        domaene      TEXT NOT NULL DEFAULT 'FACT_EXACT',
        basis_json   TEXT NOT NULL,
        quelle       TEXT NOT NULL,
        konfidenz    REAL,
        erzeugt_am   TEXT NOT NULL,
        gueltig_von  TEXT NOT NULL,
        gueltig_bis  TEXT,
        kandidat     TEXT NOT NULL,
        offen        INTEGER NOT NULL DEFAULT 1,
        offen_grund  TEXT
    );
CREATE TABLE wm_topologie (
        von          TEXT NOT NULL,
        nach         TEXT NOT NULL,
        topologie    TEXT NOT NULL,
        herkunft_art TEXT NOT NULL DEFAULT '',
        gewicht      REAL NOT NULL DEFAULT 1.0,
        basis_json   TEXT NOT NULL,
        quelle       TEXT,
        erzeugt_am   TEXT NOT NULL,
        gueltig_von  TEXT NOT NULL,
        gueltig_bis  TEXT,
        kandidat     TEXT NOT NULL,
        offen        INTEGER NOT NULL DEFAULT 1,
        offen_grund  TEXT,
        PRIMARY KEY (von, nach, topologie, herkunft_art)
    );
CREATE TABLE wm_topologie_name (
        topologie  TEXT PRIMARY KEY,
        h_nummer   TEXT NOT NULL,
        bedeutung  TEXT NOT NULL,
        kandidat   TEXT NOT NULL,
        offen      INTEGER NOT NULL DEFAULT 1
    );
CREATE TABLE workspace_episodes(episode_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(session_id),ts REAL NOT NULL,observation_turn_id TEXT REFERENCES turns(turn_id),salience REAL NOT NULL,alternatives TEXT NOT NULL,selected TEXT,state TEXT NOT NULL);
CREATE TABLE zero_raum (
  session_id TEXT PRIMARY KEY,          -- eine Zeile je Sitzung, wird ueberschrieben
  mensch     TEXT NOT NULL,             -- gabriel | andreas
  platz      INTEGER NOT NULL,
  was        TEXT NOT NULL,             -- Caveman: was ich gerade tue
  womit      TEXT,                      -- die angefasste Sache: Datei, Tabelle, Dienst
  zustand    TEXT NOT NULL,             -- arbeitet | wartet | frei
  seit       REAL NOT NULL,
  spitzname  TEXT                       -- PHASE 37, stern.py-Selbstheilung migriert dies auch nachtraeglich
);
CREATE TABLE zero_raum_ruf (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  von TEXT NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX architekt_engine_log_ts_idx ON architekt_engine_log(ts);
CREATE INDEX eos_architekt_quittungen_hyp_idx ON eos_architekt_quittungen(hypothese_id, ts);
CREATE INDEX eos_bewertungen_session_idx ON eos_bewertungen(session_id, ts);
CREATE INDEX eos_bug_hypothesen_status_idx ON eos_bug_hypothesen(status, ts);
CREATE INDEX eos_bug_hypothesen_user_idx ON eos_bug_hypothesen(user_id, ts);
CREATE INDEX gw_absicht_ts ON gw_absicht(ts);
CREATE INDEX gw_ausstrahlung_ts ON gw_ausstrahlung(ts);
CREATE INDEX gw_herkunft_ts ON gw_herkunft(ts);
CREATE INDEX idx_arbeitspaket_stand ON entityos_arbeitspaket(stand, erstellt);
CREATE INDEX idx_artikel_art ON artikel(art);
CREATE INDEX idx_artikel_baunotiz_lookup ON artikel(art, von_quelle, datum);
CREATE INDEX idx_artikel_epistemic_class ON artikel(epistemic_class);
CREATE INDEX idx_artikel_logical_id ON artikel(logical_id);
CREATE INDEX idx_artikel_projekt ON artikel(projekt);
CREATE INDEX idx_artikel_quelle ON artikel(quelle);
CREATE INDEX idx_artikel_sphaere ON artikel(sphaere);
CREATE INDEX idx_artikel_status ON artikel(status);
CREATE INDEX idx_artikel_verdichtung_lookup ON artikel(art, von_quelle, datum);
CREATE INDEX idx_asuchtext_blase ON artikel_suchtext(blase);
CREATE INDEX idx_bahn_lauf_art_zeit ON bahn_lauf(art, zeit);
CREATE INDEX idx_bearbeitung_artikel ON bearbeitung(artikel_id);
CREATE INDEX idx_erfolgsmarke_region ON vp_erfolgsmarke(region, ts);
CREATE INDEX idx_fehler_art ON fehler(art);
CREATE INDEX idx_fehler_schwere ON fehler(schwere);
CREATE INDEX idx_folgerung_beleg_fid ON folgerung_beleg(folgerung_id);
CREATE INDEX idx_folgerung_gilt_fuer ON folgerung(gilt_fuer);
CREATE INDEX idx_fundort_blase ON fundort(blase);
CREATE INDEX idx_fundort_datei ON fundort(datei_id);
CREATE INDEX idx_fundort_pruefsumme ON fundort(pruefsumme);
CREATE INDEX idx_grabstein_ziel ON grabstein(was, ziel_id);
CREATE INDEX idx_graph_kante_source_epoch
            ON graph_kante(source_node_id, graph_epoch DESC, weight DESC);
CREATE INDEX idx_graph_kante_target_epoch
            ON graph_kante(target_node_id, graph_epoch DESC, weight DESC);
CREATE INDEX idx_graph_knoten_external
            ON graph_knoten(external_id);
CREATE INDEX idx_graph_knoten_type
            ON graph_knoten(node_type);
CREATE INDEX idx_kante_nach ON kante(nach);
CREATE INDEX idx_kante_von ON kante(von);
CREATE INDEX idx_karte_wegweiser_wort ON vp_karte_wegweiser(wort);
CREATE INDEX idx_kommentar_artikel ON kommentar(artikel_id);
CREATE INDEX idx_kommentar_status ON kommentar(status);
CREATE INDEX idx_memory_artikel ON memory_tabelle(artikel_id);
CREATE INDEX idx_memory_tag ON memory_tabelle(tag);
CREATE INDEX idx_memory_user ON memory_tabelle(user_id);
CREATE INDEX idx_messung_bauteil ON messung(bauteil);
CREATE INDEX idx_messung_einheit ON messung(einheit);
CREATE INDEX idx_messung_zeile ON messung(zeile_hash);
CREATE INDEX idx_om_implikation_artikel ON om_hypothese_implikation(artikel_id);
CREATE INDEX idx_om_mitglied_artikel ON om_projekt_mitglied(artikel_id);
CREATE INDEX idx_om_mitglied_projekt ON om_projekt_mitglied(projekt_id);
CREATE INDEX idx_problem_bauteil ON problem(bauteil);
CREATE INDEX idx_problem_status ON problem(status);
CREATE INDEX idx_problem_zeile_hash ON problem(zeile_hash);
CREATE INDEX idx_retrieval_session_ts ON retrieval_episodes(session_id,ts DESC);
CREATE INDEX idx_taetigkeit_sitzung ON taetigkeit(sitzung);
CREATE INDEX idx_taetigkeit_ziel_pfad ON taetigkeit(ziel_pfad);
CREATE INDEX idx_turn_compressions_turn ON turn_compressions(turn_id, level);
CREATE INDEX idx_turns_session_ord ON turns(session_id, ordinal DESC);
CREATE INDEX idx_vd_aufnahme_strom ON vd_aufnahme(strom, zeit);
CREATE INDEX idx_vd_lauf_strom ON vd_lauf(strom, zeit);
CREATE INDEX idx_vp_alias_df_df ON vp_alias_df(df);
CREATE INDEX idx_vp_weg_guete ON vp_weg(guete DESC);
CREATE INDEX idx_wake_events_ts ON wake_events(ts);
CREATE INDEX idx_weg_ursprung_ziel ON weg(ursprung, ziel_wirt);
CREATE INDEX idx_weg_ziel ON weg(ziel_wirt);
CREATE INDEX idx_wk_aufgabe_art ON wk_aufgabe(art, zustand);
CREATE INDEX idx_wk_aufgabe_wahl ON wk_aufgabe(zustand, wert DESC);
CREATE INDEX ix_kuration_status_noetig ON kuration(status, noetig);
CREATE INDEX ix_schluessel_lauf_zeit ON schluessel_lauf(zeit);
CREATE INDEX ix_taetigkeit_zeit ON taetigkeit(zeit);
CREATE INDEX kb_auftrag_zustand
            ON kb_auftrag(zustand, prozess);
CREATE INDEX kb_buchung_batch
            ON kb_buchung(batch_id);
CREATE INDEX kb_buchung_kz_zeit
            ON kb_buchung(konto, zugang, zeit);
CREATE INDEX kb_warnung_zeit ON kb_warnung(zeit);
CREATE INDEX mv_prestage_turns_routing_idx
    ON mv_prestage_turns(routing_key, epistemik_unbekannt_n);
CREATE INDEX mv_prestage_turns_session_idx
    ON mv_prestage_turns(session_id, created_at);
CREATE INDEX sicht_arbeitsraum_turn ON sicht_arbeitsraum(turn_id);
CREATE INDEX sicht_aufnahme_quelle ON sicht_aufnahme(quelle_id);
CREATE INDEX sicht_aufnahme_turn ON sicht_aufnahme(turn_id);
CREATE INDEX sicht_evidenz_art ON sicht_evidenz(beobachtungsart);
CREATE INDEX sicht_evidenz_aufnahme ON sicht_evidenz(aufnahme_id);
CREATE INDEX sicht_hypothese_aufnahme ON sicht_hypothese(aufnahme_id);
CREATE INDEX sicht_hypothese_offen
  ON sicht_hypothese(abgeloest_von) WHERE abgeloest_von IS NULL;
CREATE INDEX sicht_merkmal_aufnahme ON sicht_merkmal(aufnahme_id);
CREATE INDEX sicht_merkmal_verfahren ON sicht_merkmal(verfahren);
CREATE INDEX sicht_nutzung_turn ON sicht_nutzung(turn_id);
CREATE INDEX sicht_stand_jetzt
  ON sicht_weltobjekt_stand(objekt_id) WHERE gueltig_bis IS NULL;
CREATE INDEX sicht_stand_objekt ON sicht_weltobjekt_stand(objekt_id);
CREATE INDEX sicht_weltobjekt_quelle ON sicht_weltobjekt(quelle_id);
CREATE INDEX sicht_zuordnung_aufnahme ON sicht_zuordnung(aufnahme_id);
CREATE INDEX wm_guss_log_ix1 ON wm_guss_log(ergebnis, zeit);
CREATE INDEX wm_lesart_ix1 ON wm_lesart(artikel_id, gueltig_bis);
CREATE INDEX wm_lesart_ix2 ON wm_lesart(artikel_id, achse, gueltig_bis);
CREATE INDEX wm_lesart_ix3 ON wm_lesart(achse, gueltig_bis);
CREATE INDEX wm_topologie_ix1 ON wm_topologie(von, topologie, gueltig_bis);
CREATE INDEX wm_topologie_ix2 ON wm_topologie(topologie);
CREATE INDEX wm_topologie_ix3 ON wm_topologie(nach, topologie, gueltig_bis);
CREATE TRIGGER sicht_evidenz_kein_aendern
BEFORE UPDATE ON sicht_evidenz BEGIN
  SELECT RAISE(ABORT, 'sicht_evidenz ist unveraenderlich: eine spaetere Deutung loest eine Hypothese ab, sie schreibt keine Beobachtung um');
END;
CREATE TRIGGER sicht_evidenz_kein_loeschen
BEFORE DELETE ON sicht_evidenz BEGIN
  SELECT RAISE(ABORT, 'sicht_evidenz ist unveraenderlich: was angekommen ist, bleibt');
END;
CREATE VIEW kondensat AS
SELECT
    'messung'        AS kind,
    json_extract(metadaten, '$.bauteil') AS bauteil,
    NULL             AS gilt_fuer,
    NULL             AS folgerung_id,
    id               AS ref_id,
    titel            AS label,
    datum            AS zeit
FROM artikel
WHERE art = 'vorfall'

UNION ALL

SELECT
    'problem_offen'  AS kind,
    bauteil          AS bauteil,
    NULL             AS gilt_fuer,
    NULL             AS folgerung_id,
    id               AS ref_id,
    substr(text, 1, 120) AS label,
    erkannt_am       AS zeit
FROM problem
WHERE status = 'offen'

UNION ALL

SELECT
    'folgerung'      AS kind,
    NULL             AS bauteil,
    gilt_fuer        AS gilt_fuer,
    id               AS folgerung_id,
    CAST(id AS TEXT) AS ref_id,
    substr(aussage, 1, 120) || ' [' || status || ']' AS label,
    zeit             AS zeit
FROM folgerung

UNION ALL

SELECT
    'beleg'          AS kind,
    NULL             AS bauteil,
    f.gilt_fuer      AS gilt_fuer,
    fb.folgerung_id  AS folgerung_id,
    fb.beleg_art || ':' || fb.beleg_id AS ref_id,
    fb.beleg_art     AS label,
    NULL             AS zeit
FROM folgerung_beleg fb
JOIN folgerung f ON f.id = fb.folgerung_id
/* kondensat(kind,bauteil,gilt_fuer,folgerung_id,ref_id,label,zeit) */;
CREATE VIEW messung_kompakt AS
        SELECT
            bauteil AS bauteil,
            was     AS was,
            wert    AS wert,
            einheit AS einheit,
            zeit    AS zeit,
            quelle  AS quelle
        FROM messung
        ORDER BY zeit DESC, bauteil
/* messung_kompakt(bauteil,was,wert,einheit,zeit,quelle) */;
CREATE VIEW mv_prestage_lernbild AS
SELECT
    routing_key,
    CASE WHEN epistemik_unbekannt_n > 0 THEN 1 ELSE 0 END AS hatte_luecke,
    COUNT(*) AS n,
    SUM(COALESCE(self_adapted, 0)) AS n_self_adapted,
    SUM(COALESCE(translation_raw_fallback, 0)) AS n_uebersetzung_ausgefallen,
    SUM(COALESCE(self_reported_gap, 0)) AS n_selbst_gemeldete_luecke,
    SUM(CASE WHEN outcome_ok = 0 THEN 1 ELSE 0 END) AS n_nicht_ok
FROM mv_prestage_turns
WHERE routing_key IS NOT NULL AND routing_key != ''
GROUP BY routing_key, CASE WHEN epistemik_unbekannt_n > 0 THEN 1 ELSE 0 END
/* mv_prestage_lernbild(routing_key,hatte_luecke,n,n_self_adapted,n_uebersetzung_ausgefallen,n_selbst_gemeldete_luecke,n_nicht_ok) */;
CREATE TABLE star_abruf_gezeigt(session_id TEXT NOT NULL, item_id TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY(session_id, item_id));
CREATE TABLE star_konfig(
  schluessel TEXT PRIMARY KEY,
  wert TEXT NOT NULL,
  typ TEXT NOT NULL,
  quelle TEXT,
  geaendert REAL NOT NULL
);
CREATE TABLE star_digest(
  "commit" TEXT PRIMARY KEY,
  datum TEXT,
  titel TEXT,
  geholt_am REAL,
  lauf_id TEXT
);
CREATE TABLE star_digest_lauf(
  lauf_id TEXT PRIMARY KEY,
  generated_at TEXT,
  dauer_ms INTEGER,
  quelle TEXT,
  lookback_tage INTEGER,
  fehler TEXT,
  unveraendert INTEGER
);
CREATE TABLE star_faehigkeit(tool_name TEXT PRIMARY KEY, zugelassen INTEGER NOT NULL DEFAULT 1, grund TEXT, geaendert REAL NOT NULL);
CREATE TABLE udb_nvidia_embedding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artikel_id TEXT NOT NULL,
    quelle_tabelle TEXT NOT NULL DEFAULT 'artikel' CHECK (quelle_tabelle IN ('artikel','durable_memory')),
    modell TEXT NOT NULL,
    dim INTEGER NOT NULL,
    embedding_json TEXT NOT NULL,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(artikel_id, quelle_tabelle)
);
CREATE TABLE retrieval_episodes_semantisch (
    retrieval_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    modell TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    kandidaten_anzahl INTEGER NOT NULL,
    ausgewaehlt_json TEXT NOT NULL,
    mechanisch_selected_json TEXT,
    weicht_ab INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PRESENT','UNKNOWN','FEHLER')),
    ts REAL NOT NULL
);
CREATE INDEX idx_retrieval_sem_session_ts ON retrieval_episodes_semantisch(session_id, ts DESC);
CREATE TABLE bau_historie (
  eintrag_id   TEXT PRIMARY KEY,
  phase        TEXT NOT NULL,
  beschreibung TEXT,
  abgeschlossen_am TEXT NOT NULL,
  von          TEXT NOT NULL,
  messergebnis TEXT,
  beleg        TEXT,
  erzeugt_am   TEXT NOT NULL
);
CREATE TABLE gw_dauersieger(artikel_id TEXT PRIMARY KEY, serie INTEGER NOT NULL DEFAULT 0, zuletzt_ts REAL NOT NULL, zuletzt_session TEXT);
CREATE TABLE star_sebukku(session_id TEXT PRIMARY KEY, ts REAL, grund TEXT, effect_id TEXT);
CREATE TABLE system_gesundheit(id TEXT PRIMARY KEY, ts REAL, cpu_prozent REAL, ram_prozent REAL, disk_prozent REAL, load1 REAL, load5 REAL, load15 REAL, kerne INTEGER, quelle TEXT, roh TEXT);
CREATE TABLE system_bestand(id TEXT PRIMARY KEY, lauf_id TEXT, ts REAL, kategorie TEXT, name TEXT, version TEXT, quelle TEXT);
CREATE TABLE vault_uebersicht(id TEXT PRIMARY KEY, url TEXT, konto TEXT, status TEXT, letzte_nutzung REAL, fehlschlaege_in_folge INTEGER DEFAULT 0, letzte_latenz_ms REAL, letzter_http_status INTEGER, erzeugt_von TEXT, erzeugt_am REAL, aktualisiert_am REAL, loeschen_angefordert INTEGER DEFAULT 0, loesch_grund TEXT);
CREATE TABLE vault_ereignis(id TEXT PRIMARY KEY, ts REAL, aktion TEXT, eintrag_id TEXT, url TEXT, grund TEXT);
CREATE TABLE raum_nachricht(id INTEGER PRIMARY KEY AUTOINCREMENT, von_session_id TEXT NOT NULL, an_session_id TEXT, text TEXT NOT NULL, erstellt_am REAL NOT NULL, gelesen_am REAL);
CREATE TABLE raum_nachricht_gelesen(nachricht_id INTEGER NOT NULL, session_id TEXT NOT NULL, gelesen_am REAL NOT NULL, PRIMARY KEY (nachricht_id, session_id));
CREATE TABLE star_quota_zustand(session_id TEXT PRIMARY KEY, reset_text TEXT, reset_epoch REAL, reset_geparst INTEGER, zuerst_erkannt REAL, versuche INTEGER NOT NULL DEFAULT 0, letzter_versuch_pid INTEGER, letzter_versuch_um REAL, fortgesetzt INTEGER NOT NULL DEFAULT 0, tmux_session TEXT);
CREATE TABLE arbeitspaket_verdacht(id TEXT PRIMARY KEY, paket_id TEXT NOT NULL, erkannt_um REAL NOT NULL, alter_stand TEXT NOT NULL, alter_beleg TEXT, neuer_befund TEXT NOT NULL, grund TEXT);
CREATE TABLE themen_status(thema_key TEXT PRIMARY KEY, thema TEXT NOT NULL, status_text TEXT NOT NULL, stand TEXT NOT NULL, paket_id TEXT, session_id TEXT, aktualisiert REAL NOT NULL);
CREATE TABLE star_stimmen(id TEXT PRIMARY KEY, name TEXT NOT NULL, rolle TEXT NOT NULL, embedding_json TEXT NOT NULL, angelegt REAL NOT NULL, aktualisiert REAL NOT NULL);
CREATE TABLE action_grounded_event(event_id TEXT PRIMARY KEY, created_at REAL NOT NULL, action_id TEXT NOT NULL, action_kind TEXT NOT NULL, action_description TEXT NOT NULL, action_ok INTEGER NOT NULL, action_error TEXT, pre_ts REAL NOT NULL, pre_source TEXT NOT NULL, pre_caption TEXT, pre_mean_brightness REAL, pre_sensor_quality REAL, pre_provenance TEXT NOT NULL, post_ts REAL, post_source TEXT, post_caption TEXT, post_mean_brightness REAL, post_sensor_quality REAL, post_provenance TEXT, visual_diff_std_delta REAL, visual_diff_mean_delta REAL, expected_change INTEGER NOT NULL, prior_count INTEGER NOT NULL DEFAULT 0, prior_conflict_count INTEGER NOT NULL DEFAULT 0, priors_json TEXT, outcome_label TEXT NOT NULL, outcome_confidence REAL, outcome_reason TEXT NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE biometric_identity (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    embedding_blob BLOB NOT NULL,
    model_id TEXT NOT NULL,
    consent_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    revoked_at REAL,
    notes TEXT
);
CREATE TABLE familiarity_prototype(prototype_id TEXT PRIMARY KEY, visual_entity_id TEXT NOT NULL, label TEXT NOT NULL, tier TEXT NOT NULL, confirm_cheap_count INTEGER NOT NULL DEFAULT 0, confirm_expensive_count INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, last_confirmed_at REAL, last_expensive_confirmed_at REAL, active INTEGER NOT NULL DEFAULT 1, rollback_of TEXT, rollback_reason TEXT, provenance TEXT NOT NULL);
CREATE TABLE gespraech_erinnerung(id TEXT PRIMARY KEY, ts REAL NOT NULL, subject TEXT NOT NULL, value TEXT NOT NULL, quelle TEXT NOT NULL DEFAULT 'realtime');
CREATE TABLE initiative_episode (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    candidate_type TEXT NOT NULL,
    candidate_text TEXT,
    score REAL NOT NULL,
    importance REAL,
    interruptibility REAL,
    chatter_debt REAL,
    decision TEXT NOT NULL CHECK (decision IN ('WAIT','SPEAK','SELF_RESOLVE','DROP')),
    realtime_seconds REAL NOT NULL DEFAULT 0,
    user_feedback TEXT,
    outcome_json TEXT NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL
, causal_event_id TEXT, voice_event_kind TEXT);
CREATE TABLE perception_head_policy(head_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL, tier TEXT NOT NULL, memory_allowed INTEGER NOT NULL, cost_ms REAL, model TEXT, version TEXT, updated_at REAL NOT NULL, updated_by TEXT NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE perception_head_status(head_id TEXT PRIMARY KEY, last_run_at REAL, last_latency_ms REAL, confidence REAL, status TEXT, reason TEXT, provenance TEXT);
CREATE TABLE phase43_concept (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE
);
CREATE TABLE pool_nutzung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at REAL NOT NULL,
    engine TEXT,
    prompt_len INTEGER,
    caller TEXT
, input_tokens INTEGER, output_tokens INTEGER, tokens_estimated INTEGER, hostname TEXT, machine_id TEXT);
CREATE TABLE presence_episode (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    user_present_probability REAL,
    at_desk_probability REAL,
    interruptibility_probability REAL,
    visual_state TEXT NOT NULL CHECK (visual_state IN ('OK','DEGRADED','UNKNOWN','OFF')),
    summary_json TEXT NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL
);
CREATE TABLE star_telegram_nachricht(id TEXT PRIMARY KEY, ts REAL NOT NULL, richtung TEXT NOT NULL, chat_id TEXT NOT NULL, von_user TEXT, telegram_message_id INTEGER, text TEXT, verarbeitet INTEGER NOT NULL DEFAULT 0, rohdaten TEXT);
CREATE TABLE star_waechter(id TEXT PRIMARY KEY, session_id TEXT, beschreibung TEXT, gestartet REAL, letzter_herzschlag REAL, status TEXT NOT NULL DEFAULT 'aktiv', blockiert_grund TEXT, blockiert_um REAL, alarmiert_um REAL);
CREATE TABLE visual_entity(visual_entity_id TEXT PRIMARY KEY, created_at REAL NOT NULL, last_seen_at REAL NOT NULL, current_label TEXT NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE visual_entity_label_history(id TEXT PRIMARY KEY, visual_entity_id TEXT NOT NULL, ts REAL NOT NULL, label TEXT NOT NULL, confidence REAL, reason TEXT NOT NULL, provenance TEXT NOT NULL, FOREIGN KEY(visual_entity_id) REFERENCES visual_entity(visual_entity_id));
CREATE TABLE visual_event (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    event_type TEXT NOT NULL,
    observed_json TEXT NOT NULL DEFAULT '{}',
    inferred_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL,
    sensor_quality REAL,
    persisted_because TEXT NOT NULL,
    provenance TEXT NOT NULL
);
CREATE TABLE voice_realtime_kosten_event(id TEXT PRIMARY KEY, zeit REAL NOT NULL, session_uuid TEXT NOT NULL, response_id TEXT, modell TEXT, text_input_tokens INTEGER, text_output_tokens INTEGER, audio_input_tokens INTEGER, audio_output_tokens INTEGER, cached_input_tokens INTEGER, total_tokens INTEGER, geschaetzte_kosten_usd REAL, geschaetzt_unverifiziert INTEGER NOT NULL DEFAULT 1, roh_usage_json TEXT NOT NULL DEFAULT '{}');
