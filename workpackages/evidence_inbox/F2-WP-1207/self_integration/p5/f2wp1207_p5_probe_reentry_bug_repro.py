import sys, hashlib
sys.path.insert(0, "/home/ai-core-node/frankenstein-repo/scripts")
import stern

session_id = "p5-probe-reentry-chain"
STIMULI = ["short_hit","short_nohit","long_hit","long_nohit","known_topic"]

for epoch_idx in range(3):
    if epoch_idx == 0:
        runtime_epoch_id, predecessor = stern._f2wp1207_runtime_epoch(session_id)
    else:
        runtime_epoch_id, predecessor = stern._f2wp1207_runtime_epoch(session_id, force_new=True)
    installation_id = stern._f2wp1207_installation_id()
    state_root_id = hashlib.sha256(f"F2WP1207_STATE_ROOT_REF/v1:{stern.DB_PATH}".encode()).hexdigest()
    entity_id = stern._f2wp1207_canonical_entity_id()
    for tag in STIMULI:
        turn_event_id = f"probe-chain:{tag}:epoch{epoch_idx}"
        stern._f2wp1207_grid10_frame_persist(
            session_id, turn_event_id, entity_id, installation_id,
            state_root_id, runtime_epoch_id, cohort="CONTROLLED_PROBE",
        )
    print(f"epoch{epoch_idx}: id={runtime_epoch_id[:12]}... predecessor={str(predecessor)[:12] if predecessor else None}")
