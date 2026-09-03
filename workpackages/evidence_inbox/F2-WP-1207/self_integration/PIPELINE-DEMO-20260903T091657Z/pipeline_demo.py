#!/usr/bin/env python3
"""F2-WP-1207: first end-to-end SHADOW pipeline demonstration against REAL
historical turn data.

Gabriel's directive (paket-1788426634287-6f53f2, 2026-09-03): all prior
F2-WP-1207 rounds ran v2 components ALONGSIDE v1 (isolated compat checks,
sandbox tests, synthetic-scenario harnesses). This round is the first to show
that v2 building blocks can sit INSIDE the shape of a real v1 turn -- as
observers, not actors -- driven by REAL, already-completed turn data instead
of synthetic scenarios.

Pipeline (Gabriel's exact wording):

    UserPromptSubmit
      -> Typed Entry
      -> StateRootIdentity
      -> GRID10 frame
      -> existing v1 processing   [PLACEHOLDER -- not executed, see below]
      -> Output
      -> persisted minimal reentry evidence

STRICT constraints honored throughout this file and its run:
  - NO EFFECTS. Nothing here calls a real v1 function, writes to the real
    `unified.db`, writes to `~/frankenstein-repo`, or registers any hook.
  - NO autonomous update. No config/state/pointer is changed anywhere.
  - NO physical actions. Pure in-memory dataclass construction + one output
    JSON file written into THIS fresh clone's evidence tree.
  - NO training. No model call of any kind.

Real substrate this run is driven by (all read-only, see companion
`REAL_TURN_EXTRACTION_NOTES.md` in this same directory for the exact
extraction queries and honesty caveats):
  1. `~/frankenstein-repo/scripts/hook.log` -- confirms 134 real
     `UserPromptSubmit` hook events fired in the current live session
     (timing-only lines, no session/retrieval linkage in this log).
  2. The real `unified.db` (`~/.local/share/agentzero/unified.db`), tables
     `turns` + `retrieval_episodes`, LEFT JOINed on `turn_id` -- gives real
     `session_id`, real `ts`, and (where present) real SHADOW-mode retrieval
     metadata (`mode`, `budget_chars`, `chars_selected`, `entry_keys` count)
     for 8 already-completed turn-cycle markers written by the live
     `stern.py` hook chain (`t-open-*` session-open, `t-mc-*` MicroClay
     shadow round, `t-close-*` session-close markers -- these are the real,
     already-existing "observe without acting" instrumentation v1 itself
     runs every turn cycle; this pipeline reuses their real timing/size
     characteristics as its own driving data instead of inventing scenarios).
  3. `python3 ~/.claude/star/stern.py db-pfad-zeigen` (explicitly read-only
     per its own docstring/PHASE 19 Punkt 3) -- real resolved `DB_PATH`.
  4. One read-only full-file SHA-256 of the real `unified.db` at pipeline
     start -- a point-in-time fingerprint, not a mutation.

Modules reused, UNMODIFIED, from this repo's own
`self-integration/wp1207-entity-identity-layering-v2-20260903` branch
(commit `6386d19`):
  - `frankenstein2.entity_identity` (`StateRootIdentity` WITH the
    `installation_id` field Gabriel flagged as "der wichtigste naechste
    Schema-Fix" -- this is the whole reason this branch, not
    `state_migration.py`'s host-bound `StateRootIdentity`, was used here).
  - `frankenstein2.grid10_interface` (the real ten-logical-cell ABI,
    F2-WP-503 -- `Grid10Plan`/`CellBudget`/`CellInput`/`CellOutput`/
    `account_outputs`, byte-for-byte the shipped module).

The GRID10-observation-event schema tags
(`FRANKENSTEIN2_GRID10_OBSERVATION_EVENT/v1` /
`FRANKENSTEIN2_GRID10_OBSERVATION_REPORT/v1`) and the semantic-neutrality
denylist guard are reused verbatim from the prior
`self-integration/wp1207-grid10-observation-schema-20260903T084727Z` round's
`grid10_observation_schema.py` -- this round's contribution is REPLACING that
round's index-formulaic synthetic drive pattern with a real-turn-derived one
(see `_grid10_frame_for_turn` below), keeping the schema and the no-naming
guard identical.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src"))

from frankenstein2.entity_identity import (  # noqa: E402
    EntityIdentityGenesisRecord,
    InstallationIdentity,
    StateRootIdentity,
    generate_entity_identity,
)
from frankenstein2.grid10_interface import (  # noqa: E402
    CellBudget,
    CellInput,
    CellOutput,
    GRID10_CELL_IDS,
    Grid10InterfaceError,
    Grid10Plan,
    account_outputs,
)

# ---------------------------------------------------------------------------
# Same denylist discipline as grid10_observation_schema.py -- reused
# verbatim, not weakened, even though this run's inputs are structural
# metadata (ids, counts, hashes), never raw turn content.
# ---------------------------------------------------------------------------
_SEMANTIC_LEAKAGE_DENYLIST = (
    "memory", "gedaechtnis", "gedächtnis", "attention", "reasoning",
    "planning", "planer", "executive", "sensor", "motor", "perception",
    "wahrnehmung", "emotion", "language", "sprache", "vision", "identity",
    "self", "ego", "control", "steuerung", "working memory", "buffer",
    "cache", "role=", "roleof", "function=", "semantik", "semantic_role",
)


def _assert_no_semantic_leakage(record: Any) -> None:
    blob = json.dumps(record, sort_keys=True, ensure_ascii=False).lower()
    for token in _SEMANTIC_LEAKAGE_DENYLIST:
        if token in blob:
            raise AssertionError(
                f"semantic leakage guard tripped: forbidden token {token!r} "
                f"found in pipeline record -- refusing to emit"
            )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


TYPED_ENTRY_SCHEMA = "FRANKENSTEIN2_F2WP1207_TYPED_USER_PROMPT_SUBMIT_ENTRY/v1"
PIPELINE_RECORD_SCHEMA = "FRANKENSTEIN2_F2WP1207_SHADOW_PIPELINE_RECORD/v1"
V1_PLACEHOLDER_SCHEMA = "FRANKENSTEIN2_F2WP1207_V1_PROCESSING_PLACEHOLDER/v1"


# ---------------------------------------------------------------------------
# Step 1: Typed Entry -- a schema-tagged, canonical-json+sha256 typed
# representation of one real, already-completed UserPromptSubmit-adjacent
# hook-cycle turn. Field names/shape chosen to mirror the fields the real
# `turns`/`retrieval_episodes` join actually has -- no invented fields.
# ---------------------------------------------------------------------------
def build_typed_entry(raw_turn: dict[str, Any]) -> dict[str, Any]:
    entry_keys = json.loads(raw_turn["entry_keys"]) if raw_turn.get("entry_keys") else None
    entry = {
        "schema": TYPED_ENTRY_SCHEMA,
        "event_type": "UserPromptSubmit",
        "event_type_provenance": (
            "hook_cycle_marker: real turn_id/session_id/ts from unified.db "
            "'turns' table, LEFT JOINed to 'retrieval_episodes' on turn_id -- "
            "the closest real substrate available this round to a raw "
            "UserPromptSubmit record (see module docstring, honesty caveat)."
        ),
        "turn_id": raw_turn["turn_id"],
        "session_id": raw_turn["session_id"],
        "ts_unix": raw_turn["ts"],
        "hook_cycle_marker_kind": raw_turn["turn_id"].split("-")[1],
        "retrieval": (
            {
                "mode": raw_turn["mode"],
                "budget_chars": raw_turn["budget_chars"],
                "chars_selected": raw_turn["chars_selected"],
                "entry_key_count": len(entry_keys) if entry_keys is not None else 0,
            }
            if raw_turn.get("retrieval_id")
            else None
        ),
    }
    entry["sha256"] = _digest({k: v for k, v in entry.items() if k != "sha256"})
    _assert_no_semantic_leakage(entry)
    return entry


# ---------------------------------------------------------------------------
# Step 2: StateRootIdentity (frankenstein2.entity_identity, WITH
# installation_id). Built ONCE per pipeline run (one observed real DB root,
# shared across all turns in this run) -- read-only derivation, no DB write.
#
# EntityIdentity/InstallationIdentity are minted via generate_entity_identity
# EXACTLY ONCE for this demo run, in-memory only, explicitly labeled
# DEMO-SCOPED -- minting the project's real, canonical EntityIdentity is an
# owner decision out of scope here (see INTEGRATION_HYPOTHESES.md Part 5).
# ---------------------------------------------------------------------------
def build_state_root_identity(
    *, db_path: str, db_fingerprint_sha256: str
) -> dict[str, Any]:
    genesis: EntityIdentityGenesisRecord = generate_entity_identity(
        generated_by="F2-WP-1207 pipeline_demo (paket-1788426634287-6f53f2), DEMO-SCOPED, not persisted"
    )
    installation = InstallationIdentity.create(
        installation_id=f"demo-installation-{genesis.entity_id[:16]}",
        entity_id=genesis.entity_id,
    )
    state_root = StateRootIdentity.create(
        state_root_id=f"demo-state-root-{_digest(db_path)[:16]}",
        installation_id=installation.installation_id,
        state_digest_sha256=db_fingerprint_sha256,
    )
    record = {
        "entity_identity_genesis": genesis.as_dict(),
        "entity_identity_genesis_sha256": genesis.sha256(),
        "installation_identity": installation.as_dict(),
        "installation_identity_sha256": installation.sha256(),
        "state_root_identity": state_root.as_dict(),
        "state_root_identity_sha256": state_root.sha256(),
        "observed_db_path": db_path,
        "observed_db_fingerprint_sha256": db_fingerprint_sha256,
        "demo_scope_note": (
            "EntityIdentity/InstallationIdentity minted once for THIS "
            "pipeline_demo run only -- transient, never written to the real "
            "unified.db or any file outside this evidence tree. NOT the "
            "project's canonical identity; minting that remains a separate "
            "owner decision (INTEGRATION_HYPOTHESES.md Part 5)."
        ),
    }
    # NOTE: the semantic-leakage denylist is a GRID10-cell-naming guard
    # (see grid10_observation_schema.py) -- it is deliberately NOT applied
    # here. This record legitimately uses "identity"/"self" in field names
    # (StateRootIdentity, EntityIdentity, ...), which would be a false
    # positive for a guard whose purpose is "no GRID10 cell gets a
    # semantic name". The guard IS applied to the GRID10 frame below, which
    # is the actual place semantic leakage would matter.
    return record


# ---------------------------------------------------------------------------
# Step 3: GRID10 frame, SHADOW mode -- real-turn-derived drive pattern
# (replaces the prior round's index-formulaic synthetic pattern). Every
# per-cell number below is a closed-form function of REAL fields on the
# typed entry (chars_selected, entry_key_count, hook_cycle_marker_kind,
# ts_unix) -- no cell is picked out by name/story, matching the
# semantic-neutrality discipline of grid10_observation_schema.py exactly.
# Purely observational: builds+validates CellInput/CellOutput pairs and
# calls the real (unmodified) account_outputs() accounting path, but never
# feeds a v1 concept into any cell and never touches v1/real DB state.
# ---------------------------------------------------------------------------
_MARKER_KIND_TO_REENTRY_BASE = {"open": 0, "mc": 1, "close": 2}


def _budget_for(cell_id: str) -> CellBudget:
    return CellBudget(
        cell_id=cell_id,
        role_label=f"f2wp1207-shadow-pipeline-neutral-slot-{cell_id}",
        max_input_refs=6,
        max_output_refs=4,
        max_work_units=11,
        max_reentry_depth=3,
    )


def build_grid10_frame(typed_entry: dict[str, Any], turn_index: int) -> dict[str, Any]:
    retrieval = typed_entry["retrieval"]
    chars_selected = retrieval["chars_selected"] if retrieval else 0
    entry_key_count = retrieval["entry_key_count"] if retrieval else 0
    marker_kind = typed_entry["hook_cycle_marker_kind"]
    marker_base = _MARKER_KIND_TO_REENTRY_BASE.get(marker_kind, 0)
    ts_int = int(typed_entry["ts_unix"])

    cells = tuple(_budget_for(cid) for cid in GRID10_CELL_IDS)
    plan = Grid10Plan.create(
        plan_id=f"f2wp1207-shadow-pipeline-turn-{turn_index:02d}",
        cycle_id=f"shadow-cycle-{typed_entry['turn_id']}",
        generation=0,
        frame_id=f"shadow-frame-{typed_entry['turn_id']}",
        frame_generation=0,
        frame_sha256=typed_entry["sha256"] if len(typed_entry["sha256"]) == 64 else ("0" * 64),
        policy_id="f2wp1207-shadow-pipeline-policy",
        policy_generation=0,
        policy_sha256=hashlib.sha256(b"f2wp1207-shadow-pipeline-policy-v1").hexdigest(),
        cells=cells,
        max_total_work_units=110,
        provenance_refs=(f"real-turn:{typed_entry['turn_id']}",),
    )

    events: list[dict[str, Any]] = []
    pairs = []
    for cell_id in GRID10_CELL_IDS:
        cell_index = int(cell_id[1:])
        budget = plan.budget_for(cell_id)

        # Every value below is a closed-form function of REAL fields
        # (chars_selected, entry_key_count, marker_base, ts_int, cell_index)
        # -- no cell-specific special-casing, no narrative choice.
        requested = 1 + ((chars_selected + entry_key_count * 7 + cell_index * 3) % budget.max_work_units)
        reentry_depth = (marker_base + cell_index + (ts_int % 5)) % (budget.max_reentry_depth + 1)
        used = (chars_selected + cell_index) % (requested + 1)
        input_refs = (f"real-turn:{typed_entry['turn_id']}", f"real-session:{typed_entry['session_id'][:12]}")
        output_refs = (f"real-turn-out:{typed_entry['turn_id']}:{cell_id}",)
        status = "COMPLETE" if retrieval is not None else "NOT_COMPUTED"

        try:
            cell_input = CellInput.for_plan(
                plan,
                cell_id=cell_id,
                work_units_requested=requested,
                reentry_depth=reentry_depth,
                input_refs=input_refs,
                provenance_refs=(f"real-turn:{typed_entry['turn_id']}:{cell_id}",),
            )
            cell_output = CellOutput.for_input(
                plan,
                cell_input,
                status=status,
                work_units_used=used,
                output_refs=output_refs,
                evidence_refs=(f"real-turn-evidence:{typed_entry['turn_id']}:{cell_id}",),
                provenance_refs=(f"real-turn:{typed_entry['turn_id']}:{cell_id}:out",),
            )
            pairs.append((cell_input, cell_output))
            events.append({
                "logical_cell_id": cell_id,
                "outcome": "ok",
                "work_units_requested": requested,
                "reentry_depth": reentry_depth,
                "work_units_used": used,
                "status": status,
            })
        except Grid10InterfaceError as exc:
            events.append({
                "logical_cell_id": cell_id,
                "outcome": "rejected",
                "rejection_reason": str(exc),
            })

    receipt = account_outputs(plan, pairs) if pairs else None

    frame = {
        "schema": "FRANKENSTEIN2_F2WP1207_GRID10_SHADOW_FRAME/v1",
        "mode": "SHADOW",
        "effects_applied": False,
        "v1_concept_assigned_to_any_cell": False,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.sha256(),
        "driven_by_real_turn": typed_entry["turn_id"],
        "events": events,
        "receipt": (
            {
                "completed_cell_ids": list(receipt.completed_cell_ids),
                "missing_cell_ids": list(receipt.missing_cell_ids),
                "total_work_units_used": receipt.total_work_units_used,
                "remaining_work_units": receipt.remaining_work_units,
                "receipt_sha256": receipt.sha256(),
            }
            if receipt is not None
            else None
        ),
    }
    _assert_no_semantic_leakage(frame)
    return frame


# ---------------------------------------------------------------------------
# Step 4: "bestehende v1-Verarbeitung" -- explicit, honest PLACEHOLDER.
# Does not import, call, or simulate any real v1 function. Documents WHERE
# in the real chain this would sit (v1's own hook-driven retrieval/response
# path in stern.py) without executing it -- the one deliberate no-op in an
# otherwise real pipeline, per Gabriel's NO-EFFECTS mandate.
# ---------------------------------------------------------------------------
def v1_processing_placeholder(typed_entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": V1_PLACEHOLDER_SCHEMA,
        "status": "NOT_EXECUTED_PLACEHOLDER",
        "would_call_in_real_activation": (
            "v1's real UserPromptSubmit-adjacent hook chain in "
            "~/frankenstein-repo/scripts/stern.py -- e.g. its existing "
            "automatischer_abruf()/semantische_suche() SHADOW-mode retrieval "
            "path that ALREADY wrote the real retrieval_episodes row this "
            "turn's Typed Entry is derived from."
        ),
        "why_not_executed": (
            "F2-WP-1207 mandate for this round: NO EFFECTS, NO autonomous "
            "update, NO physical actions, NO training -- this pipeline is "
            "observation/state-passthrough only. Calling a real v1 function "
            "here would make this an activation, not a demonstration."
        ),
        "input_turn_id": typed_entry["turn_id"],
    }


# ---------------------------------------------------------------------------
# Step 5: Output -> persisted minimal reentry evidence.
# ---------------------------------------------------------------------------
def run_pipeline_for_turn(raw_turn: dict[str, Any], turn_index: int) -> dict[str, Any]:
    typed_entry = build_typed_entry(raw_turn)
    grid10_frame = build_grid10_frame(typed_entry, turn_index)
    v1_placeholder = v1_processing_placeholder(typed_entry)
    output = {
        "schema": PIPELINE_RECORD_SCHEMA,
        "pipeline": [
            "UserPromptSubmit",
            "TypedEntry",
            "StateRootIdentity",
            "GRID10_frame_SHADOW",
            "v1_processing_PLACEHOLDER_NOT_EXECUTED",
            "Output",
            "persisted_minimal_reentry_evidence",
        ],
        "turn_index": turn_index,
        "typed_entry": typed_entry,
        "grid10_frame": grid10_frame,
        "v1_processing_placeholder": v1_placeholder,
        "no_effects_attestation": {
            "unified_db_written": False,
            "frankenstein_repo_written": False,
            "hooks_registered": False,
            "autonomous_update_performed": False,
            "training_performed": False,
            "physical_actions_performed": False,
        },
    }
    output["record_sha256"] = _digest({k: v for k, v in output.items() if k != "record_sha256"})
    # (outer guard skipped -- the `pipeline` step-name list legitimately
    # contains the literal string "StateRootIdentity"; the GRID10-cell
    # no-naming guard already ran, and passed, inside build_grid10_frame.)
    return output


def main() -> int:
    here = Path(__file__).resolve().parent
    raw_turns = json.loads((here / "real_turns_raw.json").read_text())
    fingerprint = (here / "unified_db_fingerprint_sha256.txt").read_text().strip()
    db_path = json.loads((here / "db_pfad_zeigen_output.json").read_text())["db_path_aufgeloest"]

    state_root_record = build_state_root_identity(
        db_path=db_path, db_fingerprint_sha256=fingerprint
    )

    records = [
        run_pipeline_for_turn(raw_turn, idx) for idx, raw_turn in enumerate(raw_turns)
    ]

    record_hashes = [r["record_sha256"] for r in records]
    distinctness_check = {
        "n_turns_processed": len(records),
        "n_distinct_record_sha256": len(set(record_hashes)),
        "all_records_distinct": len(set(record_hashes)) == len(record_hashes),
        "n_distinct_grid10_plan_sha256": len({r["grid10_frame"]["plan_sha256"] for r in records}),
        "n_distinct_typed_entry_sha256": len({r["typed_entry"]["sha256"] for r in records}),
        "work_units_used_spread": {
            "min": min(r["grid10_frame"]["receipt"]["total_work_units_used"] for r in records if r["grid10_frame"]["receipt"]),
            "max": max(r["grid10_frame"]["receipt"]["total_work_units_used"] for r in records if r["grid10_frame"]["receipt"]),
        },
    }

    manifest = {
        "schema": "FRANKENSTEIN2_F2WP1207_SHADOW_PIPELINE_MANIFEST/v1",
        "paket_id": "paket-1788426634287-6f53f2",
        "state_root_identity_record": state_root_record,
        "records": records,
        "distinctness_check": distinctness_check,
    }
    # (manifest-level guard skipped -- state_root_identity_record legitimately
    # contains "identity"; per-record GRID10-frame guard already ran above.)

    out_path = here / "shadow_pipeline_report.json"
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    print(json.dumps(distinctness_check, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
