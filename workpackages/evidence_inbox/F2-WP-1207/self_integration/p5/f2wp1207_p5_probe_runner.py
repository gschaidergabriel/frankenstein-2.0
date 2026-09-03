#!/usr/bin/env python3
"""F2-WP-1207 P5: kontrollierte Probe-Kampagne durch den echten GRID10-Pfad.
Importiert stern.py in-process (derselbe Code, dieselbe DB), ruft
_f2wp1207_grid10_frame_persist() mit cohort=CONTROLLED_PROBE fuer eine
Reihe unterschiedlicher, deterministisch benannter Stimulus-Turns auf.
Kein Effekt auf v1, keine fremde Sitzung beruehrt (eigene, dedizierte
Test-session_ids)."""
import sys
sys.path.insert(0, "/home/ai-core-node/frankenstein-repo/scripts")
import stern  # noqa: E402

STIMULI = [
    ("short_hit", "kurz mit Treffer"),
    ("short_nohit", "kurz ohne Treffer"),
    ("long_hit", "x" * 2000 + " mit Treffer am Ende"),
    ("long_nohit", "y" * 2000 + " ohne Treffer"),
    ("known_topic", "F2-WP-1207 Selbstintegration Status"),
    ("unknown_topic", "voellig unbekanntes Fantasiethema xyzzy123"),
    ("ambiguous", "das koennte vieles bedeuten, mehrdeutig, unklar"),
    ("repeat_a", "immer derselbe Satz zum Testen der Wiederholung"),
    ("repeat_b", "immer derselbe Satz zum Testen der Wiederholung"),
    ("conflict_like", "widerspruechliche Anfrage die zwei Dinge gleichzeitig will"),
]

results = []
probe_session_base = "p5-probe"

for epoch_idx in range(3):
    session_id = f"{probe_session_base}-epoch{epoch_idx}"
    # kontrollierter Reentry: ab der 2. Epoche fuer diese Probe-Session
    # explizit eine neue Epoche erzwingen (force_new), um Reentry-Kettung
    # in den Probe-Daten mitzumessen -- klar als kontrollierte Simulation,
    # nicht als echter Prozess-Tod, dokumentiert.
    if epoch_idx == 0:
        runtime_epoch_id, predecessor = stern._f2wp1207_runtime_epoch(session_id)
    else:
        runtime_epoch_id, predecessor = stern._f2wp1207_runtime_epoch(session_id, force_new=True)
    installation_id = stern._f2wp1207_installation_id()
    import hashlib
    state_root_id = hashlib.sha256(f"F2WP1207_STATE_ROOT_REF/v1:{stern.DB_PATH}".encode()).hexdigest()
    entity_id = stern._f2wp1207_canonical_entity_id()
    if not entity_id:
        print("KEINE entity_id aufloesbar -- P3 nicht sauber? Abbruch.", file=sys.stderr)
        sys.exit(1)
    for tag, _stim in STIMULI:
        turn_event_id = f"probe:{tag}:epoch{epoch_idx}"
        stern._f2wp1207_grid10_frame_persist(
            session_id, turn_event_id, entity_id, installation_id,
            state_root_id, runtime_epoch_id, cohort="CONTROLLED_PROBE",
        )
        results.append((session_id, runtime_epoch_id, tag))

print(f"OK: {len(results)} Probe-Frame-Aufrufe (Dedup durch DB moeglich falls Wiederholung)")
print(f"Epochen: {sorted(set(r[1] for r in results))}")
