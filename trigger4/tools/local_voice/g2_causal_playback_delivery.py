#!/usr/bin/env python3
"""Bounded Trigger-4 G2 delivery adapter.

This module is deliberately subordinate to the existing VoicePacketCortex cancellation
boundary.  It does not decide whether playback may be cancelled.  It only translates an
exact newly-emitted BARGE_IN_CANCEL_PROPAGATED event for the bound packet into termination
of the already-bound playback client, and returns an evidence record for that translation.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any

ADAPTER_ID = "T4_G2_CORTEX_EVENT_BOUND_PAPLAY_DELIVERY/v1"


def propagate_barge_in_cancel_to_bound_playback(
    cortex: Any,
    *,
    packet_id: str,
    turn_id: str,
    monotonic_ms: int,
    playback_proc: Any,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Apply the authoritative Cortex cancel and deliver that exact event to playback.

    Fail closed if the process was already terminal, if the expected Cortex event is not
    emitted exactly once, or if the event does not bind the requested packet.  SIGKILL is
    safety cleanup only after a failed SIGTERM delivery and therefore raises rather than
    returning promotion-bearing evidence.
    """
    if playback_proc.poll() is not None:
        raise RuntimeError("CAUSAL_DELIVERY_PLAYBACK_NOT_LIVE_BEFORE_CANCEL")

    events_before = tuple(cortex.events)
    changed = tuple(cortex.cancel_for_barge_in(turn_id=turn_id, monotonic_ms=monotonic_ms))
    authority_observed_ns = time.monotonic_ns()
    events_after = tuple(cortex.events)

    if len(events_after) != len(events_before) + 1:
        raise RuntimeError("CAUSAL_DELIVERY_EXPECTED_ONE_NEW_AUTHORITY_EVENT")
    event = events_after[-1]
    if getattr(event, "event_kind", None) != "BARGE_IN_CANCEL_PROPAGATED":
        raise RuntimeError("CAUSAL_DELIVERY_WRONG_AUTHORITY_EVENT_KIND")
    packet_refs = tuple(getattr(event, "packet_refs", ()))
    if packet_id not in changed or packet_id not in packet_refs:
        raise RuntimeError("CAUSAL_DELIVERY_BOUND_PACKET_NOT_IN_AUTHORITY_EVENT")
    if playback_proc.poll() is not None:
        raise RuntimeError("CAUSAL_DELIVERY_PLAYBACK_TERMINATED_BEFORE_EVENT_DELIVERY")

    playback_proc.terminate()
    try:
        playback_proc.wait(timeout=3)
    except subprocess.TimeoutExpired as exc:
        # Preserve owner-host/sandbox hygiene, but never promote a SIGKILL cleanup as the
        # product-causal playback stop.
        if playback_proc.poll() is None:
            playback_proc.kill()
            playback_proc.wait(timeout=3)
        raise AssertionError("CAUSAL_DELIVERY_SIGTERM_DID_NOT_TERMINATE_BOUND_PLAYBACK") from exc

    terminal_ns = time.monotonic_ns()
    return changed, {
        "adapter_id": ADAPTER_ID,
        "authority_event_id": getattr(event, "event_id", None),
        "authority_event_kind": getattr(event, "event_kind", None),
        "authority_packet_refs": list(packet_refs),
        "bound_packet_id": packet_id,
        "bound_playback_pid": getattr(playback_proc, "pid", None),
        "authority_observed_ns": authority_observed_ns,
        "playback_terminal_ns": terminal_ns,
        "termination_method": "SIGTERM_FROM_EXACT_CORTEX_CANCEL_EVENT",
        "independent_test_kill_before_terminalization": False,
        "pass": True,
    }
