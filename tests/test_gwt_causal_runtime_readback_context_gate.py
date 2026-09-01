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

import pytest

import frankenstein2.gwt_causal_runtime_readback as causal_readback

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def _context():
    return causal_readback.ProbeExecutionContext(
        runner_identity="runner:vps-clay-host",
        execution_surface="S1:ubuntu-24.04-oci",
        runtime_engine_identity="python:cpython-3.11",
        runtime_engine_config_sha256=SHA_A,
        environment_sha256=SHA_B,
        dependency_set_sha256=SHA_C,
        boot_id_sha256=SHA_D,
        exact_source_sha256=SHA_E,
        provenance_refs=("prov:wp900-g4-context-gate",),
    )


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


def test_concrete_context_factory_derives_digest_and_direct_digest_injection_fails_closed():
    """Execute the construction boundary, not only structural reflection checks."""
    execution_context = _context()
    observed = causal_readback.ControlNoBroadcastReadback.observe(
        execution_context=execution_context,
        runtime_instance_id="runtime:wp900-g4:control",
        process_identity="pid:control:start:1",
        boot_id_sha256=execution_context.boot_id_sha256,
        exact_source_sha256=execution_context.exact_source_sha256,
        probe_id="probe:wp900-g4:context-gate",
        nonbroadcast_input_sha256=SHA_F,
        downstream_ref="readback:control",
        downstream_sha256=SHA_A,
        observed_monotonic_ns=1,
        reentry_observed=False,
        provenance_refs=("prov:factory-observation",),
    )
    causal_readback.validate_control_no_broadcast_readback(observed)
    assert observed.execution_context_sha256 == execution_context.sha256()

    nominal = causal_readback.ControlNoBroadcastReadback(
        runtime_instance_id="runtime:wp900-g4:nominal",
        process_identity="pid:nominal:start:1",
        boot_id_sha256=execution_context.boot_id_sha256,
        exact_source_sha256=execution_context.exact_source_sha256,
        execution_context_sha256=execution_context.sha256(),
        probe_id="probe:wp900-g4:context-gate",
        nonbroadcast_input_sha256=SHA_F,
        downstream_ref="readback:nominal",
        downstream_sha256=SHA_A,
        observed_monotonic_ns=2,
        reentry_observed=False,
        provenance_refs=("prov:naked-digest",),
    )
    with pytest.raises(causal_readback.GwtCausalRuntimeReadbackError, match="factory origin"):
        causal_readback.validate_control_no_broadcast_readback(nominal)
