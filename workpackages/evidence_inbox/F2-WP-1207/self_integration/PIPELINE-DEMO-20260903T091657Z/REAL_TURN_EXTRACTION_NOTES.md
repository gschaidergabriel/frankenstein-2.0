# Real turn extraction notes — F2-WP-1207 SHADOW pipeline demo

Paket: `paket-1788426634287-6f53f2`. Exact commands/queries used to pull the
8 real turns this pipeline run was driven by, plus the honesty caveats about
what these markers actually are.

## 1. Safety posture (read-only, verified)

Both sources touched are the ones Gabriel's directive explicitly permits
read-only access to, and only via read-only tools:

- `~/frankenstein-repo/scripts/hook.log` — read via `grep`/`tail`, no write
  call issued anywhere in this round.
- `~/.local/share/agentzero/unified.db` (the real `unified.db`) — read via
  `sqlite3.connect("file:...?mode=ro", uri=True)` in Python, plus one
  whole-file `hashlib.sha256` read for the fingerprint. No `INSERT`/
  `UPDATE`/`DELETE` issued.

Baseline captured before any read, for later comparison:
- `~/frankenstein-repo` `git status --short` was empty (clean) at HEAD
  `a92a2f006e17f442d2209078a2628e3d51520f6f`.
- `hook.log` sha256 at round start: `814dab2ae616984c024f65c32b1f45e717d55de87130d935846dc36268b443ec`
  (776033 bytes, 6619 lines at that point — this file is live and grows on
  its own from the running hook system; any later growth is the live system
  writing, not this round, which never opened it for writing).

## 2. `hook.log`: confirms real `UserPromptSubmit` activity, no linkage

```
grep -c "UserPromptSubmit" ~/frankenstein-repo/scripts/hook.log
# -> 134
```

134 real, already-completed `UserPromptSubmit` hook timing lines exist in
this log (format: `<ISO ts> dauer event=UserPromptSubmit <N>ms`, e.g.
`2026-09-03T09:09:48Z dauer event=UserPromptSubmit 246ms`). This confirms
real `UserPromptSubmit` events fired during the current live session — but
this log has **no session id, no retrieval metadata, no turn id**: it is
pure aggregate timing, one line per hook-event type per invocation. It
cannot by itself be joined to a specific typed entry.

## 3. `unified.db`: real session/turn/retrieval linkage

Query used (read-only connection):

```sql
SELECT t.turn_id, t.session_id, t.ts, t.provenance,
       r.retrieval_id, r.mode, r.budget_chars, r.chars_selected, r.entry_keys
FROM turns t
LEFT JOIN retrieval_episodes r ON r.turn_id = t.turn_id
WHERE t.session_id NOT LIKE 'selbsttest%'
  AND t.session_id NOT LIKE 'echttest%'
  AND t.session_id NOT LIKE 'manueller%'
ORDER BY t.ts DESC
LIMIT 40
```

The 8 most recent rows (excluding self-test/echo-test session markers) were
taken verbatim as this round's real substrate — see `real_turns_raw.json` in
this directory for the exact extracted rows.

## 4. Honesty caveat: what these rows actually are

`unified.db`'s `turns` table has **no `role='user'` rows at all** — every row
is `role='system'`. This is v1's own existing hook-cycle instrumentation, not
a chat transcript: `stern.py` writes a `t-open-*` marker when a session
cycle opens, a `t-mc-*` ("MicroClay-Schattenrunde") marker when its own
SHADOW-mode retrieval round runs, and a `t-close-*` marker when the cycle
closes via `stern.py reconcile`. The `t-mc-*` rows are the ones that carry a
linked `retrieval_episodes` row (`mode='SHADOW'`, real `budget_chars`/
`chars_selected`/`entry_keys`) — this is v1's own pre-existing SHADOW
discipline (see `scripts/stern.py`'s `retrieval_policy_state.DEFAULT_MODE =
"SHADOW"`, confirmed by reading a fresh `gschaidergabriel/frankenstein`
clone for this round), reused here as the closest real substrate to a typed
`UserPromptSubmit` retrieval record.

**What this round claims:** these are real, already-completed, timestamped
turn-cycle markers with real session ids and (for `t-mc-*` rows) real
retrieval-size metadata, and there is independent corroborating evidence
(134 real raw `UserPromptSubmit` timing events in the same session's
`hook.log`, overlapping in time) that real `UserPromptSubmit` events did
fire throughout this session.

**What this round does NOT claim:** that a `t-mc-*`/`t-close-*`/`t-open-*`
row IS literally a `UserPromptSubmit` payload, or that the hook.log timing
lines and the `unified.db` rows have been cryptographically joined
one-to-one (no shared id exists between the two sources for that). The
`typed_entry.event_type_provenance` field in every output record says this
explicitly, so nobody reading `shadow_pipeline_report.json` later has to
re-derive this caveat.

## 5. Turns actually used (8, real, distinct)

| turn_id | session_id (first 8) | ts (unix) | marker kind | retrieval linked | chars_selected |
|---|---|---|---|---|---|
| t-close-1788426682320-afdb41 | a2f7b438 | 1788426682.32 | close | no | — |
| t-mc-1788426588562-b7b5be    | a2f7b438 | 1788426588.56 | mc    | yes | 11416 |
| t-close-1788426066267-b30ec5 | a2f7b438 | 1788426066.27 | close | no | — |
| t-mc-1788426053153-872baf    | a2f7b438 | 1788426053.15 | mc    | yes | 10898 |
| t-close-1788425952977-6f150c | a2f7b438 | 1788425952.98 | close | no | — |
| t-mc-1788425867934-3de973    | a2f7b438 | 1788425867.93 | mc    | yes | 9865 |
| t-close-1788425716105-de22f8 | a2f7b438 | 1788425716.11 | close | no | — |
| t-mc-1788425696942-0f9813    | a2f7b438 | 1788425696.94 | mc    | yes | 10899 |

All from the same real session (`a2f7b438-df52-4465-8786-b49905bbacaf`, the
current live Claude Code session) — deliberately not mixed with the
`selbsttest-*`/`echttest-*`/`manueller-test-hook` marker sessions also
present in `unified.db`, to keep this round's substrate to genuinely live
turn activity only.
