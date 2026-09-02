#!/usr/bin/env python3
"""Trivial dummy 'subject' for the witness-detach test. Not claude, not any
real agent -- a heartbeat loop that writes its own pid+timestamp to a file
every 0.2s until killed. Used as a stand-in target so the witness-detach
fix can be tested without any contact with a real running instance."""
import sys
import time
from pathlib import Path

out = Path(sys.argv[1])
pid_marker = sys.argv[2] if len(sys.argv) > 2 else "subject"
while True:
    out.write_text(f"{pid_marker} alive {time.time()}\n")
    time.sleep(0.2)
