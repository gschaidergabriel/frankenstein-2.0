# CORTEX-P0 — Perception/Voice Inventory (2026-09-05)

Read-only cataloging, no implementation, nothing live-switched. Ordered by
Gabriel after P15 (live canary, F2-WP-1207): before any Cortex v2 redesign,
map what already exists rather than rebuilding in parallel. Two parallel
forks did the actual reading (vision/perception, voice/language); this
document assembles both, unedited beyond merging structure — findings
below are exactly what was verified against real code, not aspirational
docs.

## The single most important finding

**Two entirely separate codebases implement overlapping perception
concepts, on the same machine, with zero code-level connection to each
other, and neither connects to today's F2-WP-1207 GRID10 stack (P7-P15)
at all.**

- **Codebase A — `~/.claude/star/`** ("Frank" assistant). Real,
  hardware-touching, impure. Camera/mic access, cloud VLM calls, actual
  OpenAI Realtime API sessions. Not version-controlled (no `.git`). Files
  last touched 2026-08-27/28 — 9 days stale as of this inventory, no
  process currently running on this host, no systemd unit found under
  these names.
- **Codebase B — `frankenstein-2.0/src/frankenstein2/perception_*.py`**
  ("Perception Fabric", F2-WP-700 through 714, on `main`, dated
  2026-08-29). Deliberately pure/contract-only — every module's own
  docstring states it never opens cameras, reads pixels, calls
  models/providers, or persists frames. Has real CI
  (`.github/workflows/wp70x-*-ci.yml`), receipts, reconciliations —
  same rigor style as today's F2-WP-1207 work, built in the same repo,
  one week earlier, with **no cross-reference in either direction**.

`perception_control.py` exists in BOTH codebases under the identical
name, structurally different: Codebase A's version is a real
head-registry with its own DB tables (`perception_head_policy`,
`perception_head_status` — in the same `unified.db` F2-WP-1207 uses,
though nothing reads/writes across that boundary); Codebase B's version
is a pure boundary wrapper over caller-supplied functions with no
registry of its own.

## Vision / Perception

### `visual_cortex.py` (Codebase A, 1390 lines)
LIVE-CAPABLE / DORMANT. Real cloud-VLM call path:
`vision_beschreibung_holen()` → `_vision_beschreibung_roh()`, providers
`nvidia` (`integrate.api.nvidia.com`) and `mistral` (`api.mistral.ai`),
same free-pool-key pattern used elsewhere in this project. Camera capture
via `capture_frame_mit_fallback()`. Deictic entry points:
`answer_visual_need()`, `versuche_lokalen_fast_path()`. Main loop:
`visueller_zyklus()`. Per prior session memory (not re-verified in this
pass): automatic cloud-VLM escalation was previously locked down — worth
confirming that gate is still intact before any v2 reuse.

### `perception_control.py` (Codebase A, 925 lines)
LIVE-CAPABLE / DORMANT. `Tier` enum = `ON / COMPUTE_OFF /
OUTPUT_OFF(TRANSIENT) / MEMORY_OFF`, `HeadPolicy` dataclass,
`load_registry()`, `taint_blocked()` dependency propagation,
`EvidenceAtom`, `grant_cloud_vision_once()` (single-use opt-in escalation
with auto-revert).

### `capture_worker.py` (Codebase A, 487 lines)
LIVE-CAPABLE / DORMANT. `CaptureWorker`, `KameraBesitzFehler`
(ownership-violation exception), `geteilten_worker_holen/freigeben()`,
`FrameRef`. Self-test only, no pytest suite.

### Motion / scene-change
`motion_gate.py`: `MotionGate`, `MotionStatus`, `MotionResult`.
`frame_quality.py`: blur variance, clipping, near-uniform,
exposure-jump-between-blocks, stale-frame detection — functional
equivalent of an SSIM/scene-change layer, not literally named SSIM.
Codebase B's `retina_pipeline.py` claims a "quality/delta/continuity
boundary" but wasn't read deeply enough in this pass to confirm SSIM
specifically there either.

### Person presence
`presence_bridge.py`: `PresenceBridge`, `PresenceState`,
`_unbekannter_zustand()` (explicit "unknown" state, not defaulted to
false — directly owns/wraps `CaptureWorker`/`MotionGate`/`TrackStore`,
confirming a real existing vision↔voice integration point). `track_store.py`:
`TrackStore`, `TrackState`, MOG2-mask-based detection confidence.

### Object heads / OCR / pose
Inside `active_sensing.py` (759 lines): `ocr_verfuegbar()`/`ocr_lesen()`
(real, availability-gated), `pose_grob_schaetzen()` (`cv2.CascadeClassifier`),
`roi_zuschneiden()`, `belichtung_retten()`. Object-detection-as-a-head
lives in `perception_control.py`'s `object_known_compute()`.

### Active sensing
`active_sensing.active_sense()` (line 394) — real and central,
budget-gated (`ActiveSensingBudget`), takes a `VisualNeed`, has a genuine
camera-driven A/B comparison test (`vergleichstest()`) — real evidence,
not aspirational.

### `perceptual_field.py` (Codebase A, 548 lines)
LIVE-CAPABLE / DORMANT. `VisualNeed`/`new_visual_need()`,
`ObservedEvidence`/`InferredHypothesis` (epistemic separation —
independently reinvents the same concept Codebase B's
`epistemic_perception.py` also has), `PerceptEvent`,
`percept_event_to_kandidat()` (candidate for GWT),
`run_gwt_ignition_probe()` — **this is the real GWT integration point on
the Codebase A side**. `hard_rule_prior_never_overrides_test()` suggests a
real prior-vs-observation precedence test exists.

### Visual memory
`familiarity.py` (`familiarity_prototype` table), `action_grounded_memory.py`
(`action_grounded_event` table), `visual_entity`/`visual_entity_label_history`
tables (owning file not fully traced).

### Codebase B — Perception Fabric (`frankenstein-2.0/src/frankenstein2/`)
`perception_fabric.py` (permission snapshots, `ObserveIntent`, bounded
0..4 worker allocation), `retina_pipeline.py` (deterministic
frame/quality/delta/continuity boundary — a positive result is only a
`PerceptEvent` candidate, never asserted truth), `retina_fanin.py`
(permitted-source fan-in, generation 2), `perception_capture_broker.py`
(single-owner/multi-reader capture broker, hardware-independent — almost
certainly what Gabriel meant by "single-owner capture broker"; a
`DUPLICATE-CAPTURE-AUTHORITY-REPAIR` reconciliation exists in its history,
worth reading before reuse), `visual_need.py` (candidate-only planning,
parallel to Codebase A's `perceptual_field.VisualNeed`), plus
`perception_scheduler.py`, `perception_world_bridge.py`,
`perception_dashboard.py`(+`_policy`), `perception_host_permissions.py`,
`perception_acceptance.py`, `perception_compute_binding.py`,
`perception_temporal.py`, `epistemic_perception.py` — not individually
read in full this pass.

### Not found / unconfirmed
SSIM by that literal name. A genuinely running/daemonized instance of
either vision stack right now.

## Voice / Language

### `RealtimeSession` (`realtime_gespraech.py:803`, Codebase A, 2757 lines)
LIVE-QUALITY, DORMANT ON THIS HOST. Production-hardened (echo-cancellation
feedback-loop fixes, reasoning-effort cost/quality A-B tests with real
usage numbers, speaker-role security enforced server-side not just via
prompt). External provider: `wss://api.openai.com/v1/realtime` (confirmed
by grep). Speaker role (`user`/`guest`) gates tool access in
`_tool_ausfuehren()`, defaults to `guest` (safest) on ambiguity. Cost
tracked via dedicated session UUID, logged through
`stern.realtime_kosten_event_loggen()`. **Gabriel's claim verified:** the
actual cognition/turn-taking backbone is the external OpenAI Realtime
model — local code wraps it (session setup, tool execution, cost logging,
speaker gating), doesn't replace its reasoning.

### `VoiceSessionCapsule` (`voice_session_capsule.py:100`)
Real typed per-turn context bundle: `identity_version`, `voice_identity`,
`presence` (from `PresenceBridge`, or `None`), `current_visual_state`,
`current_activity`, `expression_vector` (from `AusdrucksVektor`),
`winning_intent`, `relevant_memory_refs` (**hard rule: IDs/short text
only, never full rows** — this system independently arrived at the same
"typed, evidence-referenced, no raw dump" discipline as today's F2-WP-1207
P10/P12 work, without copying from it), `tool_permissions`,
`privacy_policy`, `session_reason`, `goals_effects`, `ts`.

### `PresenceBridge` (`presence_bridge.py:126`)
Real vision coupling — see Vision section above.

### `voice_loop_core.py` / `AusdrucksVektor` (line 330)
`AusdrucksVektor` dataclass: `assurance, valence, tension, curiosity,
urgency, warmth, energy, brevity` (user-side) **plus** `frank_emotion`,
`frank_emotion_grund` — Frank's own emotion, deterministically derived
from real state signals (`_frank_emotion_bestimmen()`), explicitly not
randomized per an inline-quoted Gabriel directive ("er soll er selbst
sein"). Separate deterministic tone-mapping for Frank's own emotion vs.
the user's.

### Deictic vision coupling
**Verified real, not a fake path**, by both forks independently (import
graph + direct code read). Transcript → cheap regex-based (no LLM,
"leicht, kein cv2") `VisualNeed` extraction via `perceptual_field` →
routed through `active_sensing.active_sense()` (the cost ladder),
explicitly NOT directly through `visual_cortex.answer_visual_need()`.
Separate trigger-word sets for OCR-style requests vs. general visual
attention, graceful fallback (`roi_hint=None`) if directional-word
extraction fails. Both imports wrapped in try/except → `None` on failure
(fail-open on cv2/camera-less machines) — the whole coupling is optional
by design.

### Speech input/transcription, TTS
Handled inside `realtime_gespraech.py`/`gespraechsmodus.py` as part of the
realtime session's audio streaming — ASR/TTS run server-side via OpenAI
Realtime; no separate local ASR/TTS stack found wired in these files
(`piper` exists installed in the venv, unclear if actually used here —
flagged unverified, not guessed).

### GWT / GRID10 / P10 / P11 / P12 integration
**None found anywhere in the voice stack.** No references to GRID10,
`f2_grid10_*`, `f2wp1207`, `EffectGate`, or `SELF_OBSERVATION` in any
voice-side file. `initiative_episode` (a table this code writes to) is
the closest existing thing to a GWT-style broadcast log — worth a closer
look as a possible integration seam, not confirmed to be the same GWT
concept used elsewhere.

### Duplicates
Four separately-named files with overlapping voice-session
responsibility: `gespraechsmodus.py` (1227 lines), `realtime_gespraech.py`
(2757 lines, contains `RealtimeSession`), `frank_voice_lite.py` (37KB,
appears to be a local VAD+Whisper wake-word path — separate concern, not
necessarily a true duplicate), `voice_loop_core.py` (906 lines, looks like
pure logic/`AusdrucksVektor`, separate from session/network code). Not
disambiguated in this pass — flagged as the canonicalization candidate.

### Tests/evidence
**None found.** No `test_voice*`/`test_gespraech*`/`test_presence*`/
`test_ausdruck*` files anywhere under `~/.claude/star`.

### Fail-closed/fallback patterns
Consistent across both forks' findings: vision-side imports wrapped in
try/except → `None` on failure, checked before use; speaker role defaults
to the most restrictive option on ambiguity. Same fail-closed discipline
as today's F2-WP-1207 work — arrived at independently in this older
codebase, not copied from it.

## Not investigated this pass (explicit scope limits, not oversights)
`voice_outcome_events.py`, `frank_voice_lite.py` internals,
`gespraechsmodus.py` internals beyond what the `RealtimeSession` read
implies, exact DB schema for `initiative_episode`/`folgerung`, whether any
of Codebase A is actually invoked live on a *different* host (prior
memory says andreas-MACO — unverifiable from this host), Codebase B's
`perception_scheduler.py`/`perception_world_bridge.py`/
`perception_dashboard.py`/`perception_host_permissions.py`/
`perception_acceptance.py`/`perception_compute_binding.py`/
`perception_temporal.py`/`epistemic_perception.py` in depth, whether
Codebase A's cloud-VLM auto-escalation lockdown (per prior session memory)
still holds.

## Canonicalization candidates flagged for a later decision (not decided here)

1. `perception_control.py` — two structurally different implementations,
   same name, same rough purpose.
2. `VisualNeed`/`perceptual_field` (Codebase A) vs `visual_need.py`
   (Codebase B) — parallel concepts, different implementations.
3. `capture_worker.py` (Codebase A, real/impure) vs
   `perception_capture_broker.py` (Codebase B, pure) — same role,
   different rigor level.
4. Four voice-session files (`gespraechsmodus.py`, `realtime_gespraech.py`,
   `frank_voice_lite.py`, `voice_loop_core.py`) with overlapping scope.

## Explicitly not done in this round
No implementation. No live wiring. No recommendation forced on which
codebase or module "wins" — this document is the map, not the decision.
