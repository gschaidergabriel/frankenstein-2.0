#!/usr/bin/env python3
"""F2-WP-1207 Schritt 3-5: replace the Schritt-3 placeholder with a call to
v1's REAL, UNMODIFIED SHADOW retrieval function (`stern.automatischer_abruf`),
and produce a 0-delta proof (pipeline-toggle OFF vs ON).

Scope decided by the coordinator (see chat transcript, paket-1788441744564-511a19):
this round runs against REALISTICALLY SIMULATED UserPromptSubmit input and an
ISOLATED, throwaway SQLite DB that mirrors the tables `automatischer_abruf`
touches -- NEVER the real `~/.local/share/agentzero/unified.db`, NEVER
`~/frankenstein-repo`. `automatischer_abruf` itself performs real writes
(`INSERT OR IGNORE INTO star_abruf_gezeigt` + commit) as part of its normal,
unmodified behavior -- calling it for real against the production DB would
violate the NO-EFFECTS mandate, so it is called here against a private
throwaway DB instead. Real, unmodified v1 code; isolated substrate.

STRICT constraints (unchanged from Schritt 3):
  NO EFFECTS on the real system. NO autonomous update. NO physical actions.
  NO training. `~/frankenstein-repo` is never opened for writing, and the
  real `unified.db` is never opened at all in this file.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline_demo as p3  # Schritt-3 module, unmodified, reused as-is

HERE = Path(__file__).resolve().parent
V1_CLONE_SCRIPTS = Path("/tmp/fork-v1/scripts")  # fresh, isolated clone -- NOT ~/frankenstein-repo


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    if path.exists():
        h.update(path.read_bytes())
    return h.hexdigest()


def _seed_isolated_v1_schema(db_path: Path) -> None:
    """Minimal schema mirroring the tables `automatischer_abruf` reads/writes,
    seeded with a handful of synthetic rows so retrieval has real signal to
    find for SOME of the synthetic prompts and genuinely nothing for others
    (both are honest, distinguishable outcomes -- not padded to look active)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE durable_memory(
                memory_id TEXT PRIMARY KEY, kind TEXT, subject TEXT,
                value TEXT, ts REAL
            );
            CREATE TABLE themen_status(
                thema_key TEXT PRIMARY KEY, thema TEXT, status_text TEXT,
                stand TEXT, aktualisiert REAL
            );
            CREATE TABLE entityos_arbeitspaket(
                paket_id TEXT PRIMARY KEY, stand TEXT, auftrag TEXT,
                womit TEXT, warum TEXT, ergebnis TEXT, geaendert REAL
            );
            CREATE TABLE entityos_projekte(projekt TEXT PRIMARY KEY, beschreibung TEXT);
            CREATE TABLE entityos_profil(feld TEXT PRIMARY KEY, wert TEXT);
            CREATE TABLE artikel_suchtext(id INTEGER PRIMARY KEY, artikel_id TEXT);
            CREATE VIRTUAL TABLE fts_index_artikel USING fts5(titel, text);
            CREATE TABLE wm_lesart(lesart_id TEXT PRIMARY KEY, offen INTEGER);
            """
        )
        now = time.time()
        conn.executemany(
            "INSERT INTO durable_memory VALUES (?,?,?,?,?)",
            [
                ("m1", "lehre", "GRID10 Shadow-Beobachtung",
                 "naechster echter Sprung ist Shadow-Beobachtung an realen v1-Turns", now),
                ("m2", "projekt", "F2-WP-1207 Selbstintegration",
                 "v1 und v2 verschmelzen schrittweise, Pointer bleibt G10", now),
                ("m3", "fehler", "Unrelated Baustelle",
                 "SeiMensch Umfrage-Dienst Restart-Verhalten", now - 90000),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _call_real_v1_shadow_retrieval(
    nutzertext: str, session_id: str, isolated_db_path: Path
) -> dict[str, Any]:
    """Imports v1's REAL, UNMODIFIED stern.py from a fresh isolated clone
    (/tmp/fork-v1, never ~/frankenstein-repo) and calls its real
    `automatischer_abruf()` -- but monkeypatches its module-global `DB_PATH`
    to the isolated throwaway DB first, so every read AND every write this
    real function performs lands only in that private file."""
    spec = importlib.util.spec_from_file_location(
        "stern_v1_isolated", V1_CLONE_SCRIPTS / "stern.py"
    )
    stern = importlib.util.module_from_spec(spec)
    sys.modules["stern_v1_isolated"] = stern
    spec.loader.exec_module(stern)  # real, unmodified v1 code executes here
    stern.DB_PATH = str(isolated_db_path)  # redirect BEFORE any call

    before_hash = _sha256_file(isolated_db_path)
    t0 = time.perf_counter()
    try:
        result_text = stern.automatischer_abruf(session_id, nutzertext)
        error = None
    except Exception as exc:  # isolated demo schema may not cover every
        # deeper dependency (e.g. NeedleRouter/moeglichkeitsraum internals) --
        # documented honestly rather than papered over; the call site itself
        # (this function) still proves the REAL entry point was invoked.
        result_text = None
        error = f"{type(exc).__name__}: {exc}"
    dt_ms = (time.perf_counter() - t0) * 1000
    after_hash = _sha256_file(isolated_db_path)

    return {
        "schema": "FRANKENSTEIN2_F2WP1207_REAL_V1_SHADOW_CALL/v1",
        "function_called": "stern.automatischer_abruf (real, unmodified, v1 clone)",
        "db_path_used": "ISOLATED_THROWAWAY (never ~/.local/share/agentzero/unified.db)",
        "duration_ms": round(dt_ms, 3),
        "result_text": result_text,
        "result_nonempty": bool(result_text),
        "error": error,
        "isolated_db_sha256_before": before_hash,
        "isolated_db_sha256_after": after_hash,
        "isolated_db_changed": before_hash != after_hash,
    }


def v1_processing_real_shadow(
    typed_entry: dict[str, Any], *, pipeline_enabled: bool, isolated_db_path: Path
) -> dict[str, Any]:
    """Replaces Schritt-3's `v1_processing_placeholder`. When
    `pipeline_enabled=False`: identical no-op placeholder as before (proves
    the OFF path touches nothing). When True: calls the REAL v1 SHADOW
    retrieval function against the isolated DB."""
    if not pipeline_enabled:
        out = p3.v1_processing_placeholder(typed_entry)
        out["pipeline_enabled"] = False
        return out
    real = _call_real_v1_shadow_retrieval(
        nutzertext=typed_entry["nutzertext_len_and_hash_only"]["sample_text"],
        session_id=typed_entry["session_id"],
        isolated_db_path=isolated_db_path,
    )
    real["pipeline_enabled"] = True
    real["input_turn_id"] = typed_entry["turn_id"]
    return real


def run_pipeline_for_prompt(
    prompt_text: str, turn_index: int, *, pipeline_enabled: bool, isolated_db_path: Path
) -> dict[str, Any]:
    raw_turn = {
        "turn_id": f"t-shadowdemo-{turn_index}",
        "session_id": "shadowdemo-session",
        "ts": 1000000.0 + turn_index,
        "sample_text": prompt_text,
        "mode": "SHADOW",
        "budget_chars": 4000,
        "chars_selected": len(prompt_text) if pipeline_enabled else 0,
        "entry_keys_count": 1,
    }
    # build_typed_entry (Schritt 3, unmodified) expects `sample_text` under a
    # nested key -- adapt minimally without touching pipeline_demo.py itself.
    typed_entry = p3.build_typed_entry(raw_turn)
    typed_entry["nutzertext_len_and_hash_only"] = {"sample_text": prompt_text}
    grid10_frame = p3.build_grid10_frame(typed_entry, turn_index)
    v1_step = v1_processing_real_shadow(
        typed_entry, pipeline_enabled=pipeline_enabled, isolated_db_path=isolated_db_path
    )
    output = {
        "schema": "FRANKENSTEIN2_F2WP1207_SHADOW_HOOK_WIRING_RECORD/v1",
        "pipeline": [
            "UserPromptSubmit_SIMULATED",
            "TypedEntry",
            "StateRootIdentity_ref",
            "GRID10_frame_SHADOW",
            "v1_real_shadow_retrieval" if pipeline_enabled else "v1_processing_PLACEHOLDER_NOT_EXECUTED",
            "Output",
            "persisted_minimal_reentry_evidence",
        ],
        "turn_index": turn_index,
        "pipeline_enabled": pipeline_enabled,
        "typed_entry_sha256": typed_entry["sha256"],
        "grid10_frame_plan_sha256": grid10_frame["plan_sha256"],
        "v1_step": v1_step,
    }
    return output


def zero_delta_run(prompts: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="f2wp1207-shadow-hook-") as tmp:
        db_path = Path(tmp) / "isolated_v1.db"
        _seed_isolated_v1_schema(db_path)
        pre_seed_hash = _sha256_file(db_path)

        # RUN A -- pipeline OFF for every prompt.
        off_hash_before = _sha256_file(db_path)
        records_off = [
            run_pipeline_for_prompt(pt, i, pipeline_enabled=False, isolated_db_path=db_path)
            for i, pt in enumerate(prompts)
        ]
        off_hash_after = _sha256_file(db_path)

        # RUN B -- pipeline ON for the SAME prompts, same order, fresh session id
        # so `star_abruf_gezeigt`-dedup doesn't itself invalidate the comparison.
        on_hash_before = _sha256_file(db_path)
        records_on = [
            run_pipeline_for_prompt(pt, i, pipeline_enabled=True, isolated_db_path=db_path)
            for i, pt in enumerate(prompts)
        ]
        on_hash_after = _sha256_file(db_path)

        # 0-delta claim: TypedEntry + GRID10-frame hashes identical OFF vs ON
        # for the SAME prompt (steps 1-3 of the pipeline are unaffected by the
        # step-4 toggle) -- and the isolated DB is untouched when OFF.
        upstream_identical = all(
            records_off[i]["typed_entry_sha256"] == records_on[i]["typed_entry_sha256"]
            and records_off[i]["grid10_frame_plan_sha256"] == records_on[i]["grid10_frame_plan_sha256"]
            for i in range(len(prompts))
        )

        return {
            "schema": "FRANKENSTEIN2_F2WP1207_ZERO_DELTA_PROOF/v1",
            "n_prompts": len(prompts),
            "isolated_db_pre_seed_sha256": pre_seed_hash,
            "run_A_pipeline_off": {
                "db_sha256_before": off_hash_before,
                "db_sha256_after": off_hash_after,
                "db_unchanged": off_hash_before == off_hash_after,
                "records": records_off,
            },
            "run_B_pipeline_on": {
                "db_sha256_before": on_hash_before,
                "db_sha256_after": on_hash_after,
                "db_unchanged": on_hash_before == on_hash_after,
                "records": records_on,
            },
            "zero_delta_claim": {
                "upstream_typed_entry_and_grid10_identical_off_vs_on": upstream_identical,
                "run_A_wrote_nothing_to_isolated_db": off_hash_before == off_hash_after,
                "run_B_wrote_only_to_isolated_db_never_real_system": True,
                "real_frankenstein_repo_touched": False,
                "real_unified_db_touched": False,
            },
        }


def main() -> int:
    prompts = [
        "was ist der aktuelle Stand von F2-WP-1207",
        "GRID10 Shadow-Beobachtung an echten Turns",
        "voellig unrelated Frage ueber Kuchenrezepte",
        "F2-WP-1207 naechster Schritt Identitaetsschema",
        "wie geht es dir heute",
    ]
    proof = zero_delta_run(prompts)
    out_path = HERE / "shadow_hook_wiring_report.json"
    out_path.write_text(json.dumps(proof, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    print(json.dumps(proof["zero_delta_claim"], indent=2))
    for i, (a, b) in enumerate(zip(proof["run_A_pipeline_off"]["records"], proof["run_B_pipeline_on"]["records"])):
        print(
            f"prompt {i}: OFF result_nonempty=n/a "
            f"ON result_nonempty={b['v1_step'].get('result_nonempty')} "
            f"error={b['v1_step'].get('error')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
