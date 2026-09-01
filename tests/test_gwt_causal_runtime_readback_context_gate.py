"""Executable WP900 G4 discriminators for the known WP507 matched-control context confound.

R6-SEED-012 reproduced that probe_id + nonbroadcast input equality is insufficient
when intervention/control execute under different runner/model/config/environment
contexts. WP900 G4 must not freeze a runtime subject until the causal-readback
binder carries one concrete typed shared execution context across both arms.

The handoff additionally requires construction from the concrete typed context,
not a caller-injected naked digest as the only control-arm context authority.
"""
from dataclasses import fields
import inspect

import frankenstein2.gwt_causal_runtime_readback as causal_readback


def test_wp900_g4_binds_one_typed_shared_probe_execution_context():
    assert hasattr(causal_readback, "ProbeExecutionContext"), (
        "WP900 G4 lacks the typed ProbeExecutionContext required by R6-SEED-012"
    )

    control_fields = {field.name for field in fields(causal_readback.ControlNoBroadcastReadback)}
    assert "execution_context_sha256" in control_fields, (
        "control readback does not bind the shared execution-context digest"
    )

    parameters = inspect.signature(causal_readback.bind_causal_runtime_readback).parameters
    assert "execution_context" in parameters, (
        "causal runtime binder does not consume the concrete shared execution context"
    )


def test_control_readback_context_is_factory_bound_not_naked_digest_only():
    """Require a concrete-context factory + origin validator before runtime freeze."""
    observe = getattr(causal_readback.ControlNoBroadcastReadback, "observe", None)
    assert callable(observe), (
        "ControlNoBroadcastReadback still exposes a naked execution_context_sha256 "
        "without a concrete ProbeExecutionContext observation factory"
    )
    observe_parameters = inspect.signature(observe).parameters
    assert "execution_context" in observe_parameters, (
        "control observation factory must consume exact ProbeExecutionContext"
    )

    assert hasattr(causal_readback, "validate_control_no_broadcast_readback"), (
        "binder lacks a fail-closed factory-origin validator for control readback"
    )
    control_fields = {field.name for field in fields(causal_readback.ControlNoBroadcastReadback)}
    assert "_factory_seal" in control_fields and "_factory_payload_sha256" in control_fields, (
        "control readback lacks immutable observation-factory origin/payload binding"
    )
