import unittest

from frankenstein2.codex_cli_route import (
    ADAPTED,
    ADAPTER_SURFACE,
    BLOCKED,
    CodexHostCapabilityReport,
    CodexRouteError,
    CodexSurfaceObservation,
    DECLARED,
    DEGRADED,
    FIRING_VERIFIED,
    NATIVE,
    NATIVE_SURFACE,
    OBSERVED,
    REPORT_SCHEMA,
    REQUIRED_ROLES,
    SURFACE_SCHEMA,
    plan_codex_route,
)

ENV_SHA = "1" * 64
RELEASE_SHA = "2" * 64


def surface(
    role,
    *,
    suffix="one",
    evidence=FIRING_VERIFIED,
    mode=NATIVE_SURFACE,
    timing=True,
    payload=True,
    matcher=True,
    multiplicity=True,
):
    return CodexSurfaceObservation(
        schema=SURFACE_SCHEMA,
        surface_id=f"surface.{role.lower()}.{suffix}",
        semantic_role=role,
        concrete_event=f"codex.event.{role.lower()}.{suffix}",
        evidence_level=evidence,
        surface_mode=mode,
        timing_verified=timing,
        payload_identity_verified=payload,
        matcher_coverage_verified=matcher,
        firing_multiplicity_verified=multiplicity,
    )


def report(*surfaces):
    return CodexHostCapabilityReport(
        schema=REPORT_SCHEMA,
        report_id="codex-host-report-1",
        target_environment_identity_sha256=ENV_SHA,
        codex_version="caller-observed-version",
        surfaces=tuple(surfaces),
    )


def complete_surfaces(*, adapter_role=None):
    items = []
    for role in REQUIRED_ROLES:
        items.append(
            surface(
                role,
                mode=ADAPTER_SURFACE if role == adapter_role else NATIVE_SURFACE,
            )
        )
    return items


def route(capability_report, state_root="/var/lib/frankenstein2"):
    return plan_codex_route(
        report=capability_report,
        release_manifest_sha256=RELEASE_SHA,
        state_lineage_id="f2-state-lineage-1",
        durable_state_root=state_root,
        route_id="codex-route-1",
    )


class CodexCliRouteTests(unittest.TestCase):
    def test_all_required_verified_native_is_native(self):
        result = route(report(*complete_surfaces()))
        self.assertEqual(result.classification, NATIVE)
        self.assertEqual(result.missing_roles, ())
        self.assertEqual(result.unverified_roles, ())
        self.assertEqual(result.ambiguous_roles, ())
        self.assertEqual(result.adapter_roles, ())
        self.assertEqual(len(result.role_bindings), len(REQUIRED_ROLES))

    def test_one_verified_adapter_role_is_adapted(self):
        result = route(report(*complete_surfaces(adapter_role="PRE_EFFECT")))
        self.assertEqual(result.classification, ADAPTED)
        self.assertEqual(result.adapter_roles, ("PRE_EFFECT",))

    def test_matching_name_without_full_firing_evidence_is_degraded(self):
        items = complete_surfaces()
        index = REQUIRED_ROLES.index("USER_TURN")
        items[index] = surface(
            "USER_TURN",
            evidence=OBSERVED,
            timing=False,
            payload=False,
            matcher=False,
            multiplicity=False,
        )
        result = route(report(*items))
        self.assertEqual(result.classification, DEGRADED)
        self.assertEqual(result.unverified_roles, ("USER_TURN",))
        self.assertIn("MATCHING_SURFACE_WITHOUT_FULL_FIRING_EVIDENCE", result.notes)
        self.assertNotIn(
            ("USER_TURN", "surface.user_turn.one"), result.role_bindings
        )

    def test_declared_surface_is_not_firing_evidence(self):
        items = complete_surfaces()
        index = REQUIRED_ROLES.index("SESSION_STOP")
        items[index] = surface("SESSION_STOP", evidence=DECLARED)
        result = route(report(*items))
        self.assertEqual(result.classification, DEGRADED)
        self.assertEqual(result.unverified_roles, ("SESSION_STOP",))

    def test_missing_required_role_is_blocked(self):
        items = [item for item in complete_surfaces() if item.semantic_role != "POST_EFFECT"]
        result = route(report(*items))
        self.assertEqual(result.classification, BLOCKED)
        self.assertEqual(result.missing_roles, ("POST_EFFECT",))
        self.assertIn("REQUIRED_ROLE_MISSING", result.notes)

    def test_multiple_verified_surfaces_for_required_role_is_blocked(self):
        items = complete_surfaces()
        items.append(surface("PRE_EFFECT", suffix="two"))
        result = route(report(*items))
        self.assertEqual(result.classification, BLOCKED)
        self.assertEqual(result.ambiguous_roles, ("PRE_EFFECT",))
        self.assertIn("MULTIPLE_FULLY_VERIFIED_SURFACES_FOR_REQUIRED_ROLE", result.notes)

    def test_durable_state_under_codex_cache_is_blocked(self):
        result = route(
            report(*complete_surfaces()),
            state_root="/home/test/.codex/plugin-cache/frankenstein2",
        )
        self.assertEqual(result.classification, BLOCKED)
        self.assertIn(
            "DURABLE_STATE_ROOT_MATCHES_DISPOSABLE_HOST_OR_CACHE_LOCATION",
            result.notes,
        )

    def test_durable_state_under_tmp_is_blocked(self):
        result = route(report(*complete_surfaces()), state_root="/tmp/frankenstein2")
        self.assertEqual(result.classification, BLOCKED)

    def test_background_wake_is_optional(self):
        result = route(report(*complete_surfaces()))
        self.assertEqual(result.classification, NATIVE)
        self.assertNotIn("BACKGROUND_WAKE", dict(result.role_bindings))

    def test_verified_background_wake_can_be_bound(self):
        items = complete_surfaces()
        items.append(surface("BACKGROUND_WAKE"))
        result = route(report(*items))
        self.assertEqual(result.classification, NATIVE)
        self.assertIn("BACKGROUND_WAKE", dict(result.role_bindings))

    def test_ambiguous_optional_background_wake_does_not_mint_required_failure(self):
        items = complete_surfaces()
        items.extend(
            [
                surface("BACKGROUND_WAKE", suffix="one"),
                surface("BACKGROUND_WAKE", suffix="two"),
            ]
        )
        result = route(report(*items))
        self.assertEqual(result.classification, NATIVE)
        self.assertNotIn("BACKGROUND_WAKE", dict(result.role_bindings))
        self.assertIn("OPTIONAL_BACKGROUND_WAKE_AMBIGUOUS_NOT_BOUND", result.notes)

    def test_report_digest_is_surface_order_independent(self):
        items = complete_surfaces()
        forward = report(*items)
        reverse = report(*reversed(items))
        self.assertEqual(forward.sha256(), reverse.sha256())

    def test_route_digest_is_deterministic(self):
        capability_report = report(*complete_surfaces())
        first = route(capability_report)
        second = route(capability_report)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256(), second.sha256())

    def test_duplicate_surface_identity_is_rejected(self):
        duplicate = surface("SESSION_START")
        with self.assertRaises(CodexRouteError):
            report(duplicate, duplicate)

    def test_bad_environment_digest_is_rejected(self):
        with self.assertRaises(CodexRouteError):
            CodexHostCapabilityReport(
                schema=REPORT_SCHEMA,
                report_id="bad-report",
                target_environment_identity_sha256="not-a-sha",
                codex_version="caller-observed-version",
                surfaces=tuple(complete_surfaces()),
            )

    def test_non_boolean_verification_flags_are_rejected(self):
        with self.assertRaises(CodexRouteError):
            surface("SESSION_START", timing=1)

    def test_report_requires_exact_surface_type(self):
        with self.assertRaises(CodexRouteError):
            CodexHostCapabilityReport(
                schema=REPORT_SCHEMA,
                report_id="bad-report",
                target_environment_identity_sha256=ENV_SHA,
                codex_version="caller-observed-version",
                surfaces=(object(),),
            )


if __name__ == "__main__":
    unittest.main()
