#!/usr/bin/env bash
# "Harness leader" stand-in: simulates a session/job that hosts a subject
# process plus a witness spawned as a background job inside that same
# session (the situation blockers.json describes for witness_v2.py -- a
# witness launched without ever detaching itself from whatever session
# launched it). Started by the test driver with start_new_session=True, so
# this script's own PID == its own PGID == its own SID (fresh group).
set -u
DIR="$1"
WORK="$2"
mkdir -p "$WORK"

python3 "$DIR/dummy_subject.py" "$WORK/subject_heartbeat.txt" SUBJECT &
echo $! > "$WORK/subject.pid"
SUBJECT_PID=$(cat "$WORK/subject.pid")

# naive witness: same code, --daemonize OMITTED -> stays in this pgid,
# reproduces the v2 vulnerability.
python3 "$DIR/witness_v3.py" --arm \
  --target-pid "$SUBJECT_PID" \
  --relaunch-cmd "python3 $DIR/dummy_subject.py $WORK/relaunched_naive_heartbeat.txt REPLACEMENT_NAIVE" \
  --evidence "$WORK/evidence_naive.json" \
  --timeout 30 &
echo $! > "$WORK/naive_witness.pid"

# fixed witness: same code, --daemonize SET -> double-forks out of this
# pgid/session before doing anything else with the target.
python3 "$DIR/witness_v3.py" --arm --daemonize \
  --target-pid "$SUBJECT_PID" \
  --relaunch-cmd "python3 $DIR/dummy_subject.py $WORK/relaunched_fixed_heartbeat.txt REPLACEMENT_FIXED" \
  --evidence "$WORK/evidence_fixed.json" \
  --timeout 30 &
echo $! > "$WORK/fixed_witness_launcher.pid"

echo $$ > "$WORK/harness_leader.pid"
sleep 60
