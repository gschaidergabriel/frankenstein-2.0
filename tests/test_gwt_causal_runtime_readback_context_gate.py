"""Executable WP900 G4 discriminator for the known WP507 matched-control context confound.

The research handoff R6-SEED-012 reproduced that probe_id + nonbroadcast input equality
is insufficient when intervention/control execute under different runner/model/config/environment
contexts.  WP900 G4 must not freeze a runtime subject until the causal-readback binder carries
one concrete typed shared execution context across both arms.
"""
from dataclasses import fields
import inspect

import frankenstein2.gwt_causal_runtime_readback as causal_readback


def test_wp900_g4_binds_one_typed_shared_probe_execution_context():
    """Fail until the G4 binder structurally closes the reproduced context confound."""
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
