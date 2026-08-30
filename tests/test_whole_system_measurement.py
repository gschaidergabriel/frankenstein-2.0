from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from frankenstein2.whole_persistent_loop import WholePersistentLoopSeal
from frankenstein2.whole_system_characterization import DEFAULT_METRIC_SCHEMA, characterize_measurements
from frankenstein2.whole_system_measurement import (
    HostEnvironmentEvidence,
    WholeSystemMeasurementError,
    measure_characterization_sample,
    observe_source_bundle,
)


def _seal() -> WholePersistentLoopSeal:
    return WholePersistentLoopSeal(
        seal_id="seal-1",
        generation=1,
        current_checkpoint_id="cp-0",
        current_checkpoint_sha256="1" * 64,
        frame_id="frame-1",
        frame_sha256="2" * 64,
        contract_id="contract-1",
        contract_sha256="3" * 64,
        grid_plan_id="grid-1",
        grid_plan_sha256="4" * 64,
        gwt_seal_id="gwt-1",
        gwt_seal_sha256="5" * 64,
        decision_kind="ROUTE",
        decision_id="decision-1",
        decision_sha256="6" * 64,
        outcome_id="outcome-1",
        outcome_sha256="7" * 64,
        next_checkpoint_id="cp-1",
        next_checkpoint_sha256="8" * 64,
        reentry_refs=("reentry-1",),
        provenance_refs=("wp900:test-fixture",),
    )


def _environment(release: str = "test-release") -> HostEnvironmentEvidence:
    return HostEnvironmentEvidence(
        os_name="posix",
        sys_platform="linux",
        platform_system="Linux",
        platform_release=release,
        machine="x86_64",
        python_implementation="CPython",
        python_version="3.12.0",
        byteorder="little",
    )


def _load_subject(root: Path, *, mutate_source: bool = False):
    path = root / "bench_subject.py"
    mutation = "\n    with open(__file__, 'a', encoding='utf-8') as handle:\n        handle.write('\\n# mutated-during-trial')" if mutate_source else ""
    path.write_text(
        "def measured_operation():" + mutation + "\n    return {'ok': True}\n\n"
        "def quality_scorer(result):\n    return 900000 if result == {'ok': True} else 0\n",
        encoding="utf-8",
    )
    module_name = f"wp902_test_subject_{id(root)}_{int(mutate_source)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class WholeSystemMeasurementTests(unittest.TestCase):
    def test_source_bundle_digest_is_bound_to_exact_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            first = observe_source_bundle(repo_root=root, source_paths=("a.py",))
            (root / "a.py").write_text("x = 2\n", encoding="utf-8")
            second = observe_source_bundle(repo_root=root, source_paths=("a.py",))
            self.assertNotEqual(first.sha256(), second.sha256())
            self.assertNotEqual(first.files, second.files)

    def test_source_bundle_rejects_absolute_parent_and_symlink_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            for bad in (str((root / "a.py").resolve()), "../a.py", "./a.py"):
                with self.subTest(path=bad):
                    with self.assertRaises(WholeSystemMeasurementError):
                        observe_source_bundle(repo_root=root, source_paths=(bad,))
            link = root / "link.py"
            try:
                link.symlink_to(root / "a.py")
            except (OSError, NotImplementedError):
                return
            with self.assertRaisesRegex(WholeSystemMeasurementError, "symlink"):
                observe_source_bundle(repo_root=root, source_paths=("link.py",))

    def test_measurement_derives_source_environment_and_loop_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root)
            with (
                patch("frankenstein2.whole_system_measurement.observe_host_environment", side_effect=[_environment(), _environment()]),
                patch("frankenstein2.whole_system_measurement._peak_rss_bytes", side_effect=[1024, 2048]),
                patch("frankenstein2.whole_system_measurement.time.perf_counter_ns", side_effect=[10_000, 10_750]),
            ):
                sample = measure_characterization_sample(
                    run_id="run-1",
                    trial_index=0,
                    repo_root=root,
                    source_paths=("bench_subject.py",),
                    whole_loop_seal=_seal(),
                    operation=subject.measured_operation,
                    quality_scorer=subject.quality_scorer,
                    provenance_refs=("runpackage:run-1",),
                )
            expected_bundle = observe_source_bundle(repo_root=root, source_paths=("bench_subject.py",))
            self.assertEqual(sample.source_bundle_sha256, expected_bundle.sha256())
            self.assertEqual(sample.whole_loop_seal_sha256, _seal().sha256())
            self.assertEqual(sample.environment_fingerprint_sha256, _environment().sha256())
            self.assertEqual(sample.metric_schema_id, DEFAULT_METRIC_SCHEMA)
            self.assertEqual(sample.latency_ns, 750)
            self.assertEqual(sample.peak_rss_bytes, 2048)
            self.assertEqual(sample.quality_micros, 900_000)
            self.assertTrue(any(ref.startswith("wp902:source-bundle:") for ref in sample.provenance_refs))
            self.assertTrue(any(ref.startswith("wp902:quality-scorer:") for ref in sample.provenance_refs))

    def test_producer_samples_traverse_existing_characterization_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root)
            environment = _environment()
            seal = _seal()
            samples = []
            for trial_index, (started_ns, finished_ns, rss_after) in enumerate(
                ((100, 200, 2048), (300, 550, 3072), (700, 1100, 4096))
            ):
                with (
                    patch(
                        "frankenstein2.whole_system_measurement.observe_host_environment",
                        side_effect=[environment, environment],
                    ),
                    patch(
                        "frankenstein2.whole_system_measurement._peak_rss_bytes",
                        side_effect=[1024, rss_after],
                    ),
                    patch(
                        "frankenstein2.whole_system_measurement.time.perf_counter_ns",
                        side_effect=[started_ns, finished_ns],
                    ),
                ):
                    samples.append(
                        measure_characterization_sample(
                            run_id="g3-to-g2-integration",
                            trial_index=trial_index,
                            repo_root=root,
                            source_paths=("bench_subject.py",),
                            whole_loop_seal=seal,
                            operation=subject.measured_operation,
                            quality_scorer=subject.quality_scorer,
                            provenance_refs=("integration:wp902:g3-to-g2",),
                        )
                    )

            first = samples[0]
            report = characterize_measurements(
                samples,
                expected_source_bundle_sha256=first.source_bundle_sha256,
                expected_whole_loop_seal_sha256=first.whole_loop_seal_sha256,
                expected_environment_fingerprint_sha256=first.environment_fingerprint_sha256,
                expected_metric_schema_id=first.metric_schema_id,
            )

            self.assertEqual(report.sample_count, 3)
            self.assertEqual(report.source_bundle_sha256, first.source_bundle_sha256)
            self.assertEqual(report.whole_loop_seal_sha256, seal.sha256())
            self.assertEqual(report.environment_fingerprint_sha256, environment.sha256())
            self.assertEqual(report.latency_ns_min, 100)
            self.assertEqual(report.latency_ns_max, 400)
            self.assertEqual(report.peak_rss_bytes_min, 2048)
            self.assertEqual(report.peak_rss_bytes_max, 4096)
            self.assertEqual(report.quality_micros_min, 900_000)
            self.assertEqual(report.quality_micros_max, 900_000)
            self.assertEqual(report.as_dict()["runtime_authority"], "NONE")
            self.assertFalse(report.as_dict()["whole_system_acceptance"])

    def test_operation_and_quality_scorer_source_must_be_inside_bound_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root)
            (root / "other.py").write_text("x = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(WholeSystemMeasurementError, "operation source file"):
                measure_characterization_sample(
                    run_id="run-1",
                    trial_index=0,
                    repo_root=root,
                    source_paths=("other.py",),
                    whole_loop_seal=_seal(),
                    operation=subject.measured_operation,
                    quality_scorer=subject.quality_scorer,
                    provenance_refs=("runpackage:run-1",),
                )

    def test_source_mutation_during_trial_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root, mutate_source=True)
            with (
                patch("frankenstein2.whole_system_measurement.observe_host_environment", side_effect=[_environment(), _environment()]),
                patch("frankenstein2.whole_system_measurement._peak_rss_bytes", side_effect=[1024, 2048]),
                patch("frankenstein2.whole_system_measurement.time.perf_counter_ns", side_effect=[10, 20]),
            ):
                with self.assertRaisesRegex(WholeSystemMeasurementError, "source bundle changed"):
                    measure_characterization_sample(
                        run_id="run-mutate",
                        trial_index=0,
                        repo_root=root,
                        source_paths=("bench_subject.py",),
                        whole_loop_seal=_seal(),
                        operation=subject.measured_operation,
                        quality_scorer=subject.quality_scorer,
                        provenance_refs=("runpackage:run-mutate",),
                    )

    def test_environment_drift_during_trial_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root)
            with (
                patch("frankenstein2.whole_system_measurement.observe_host_environment", side_effect=[_environment("a"), _environment("b")]),
                patch("frankenstein2.whole_system_measurement._peak_rss_bytes", side_effect=[100, 200]),
                patch("frankenstein2.whole_system_measurement.time.perf_counter_ns", side_effect=[10, 20]),
            ):
                with self.assertRaisesRegex(WholeSystemMeasurementError, "environment fingerprint changed"):
                    measure_characterization_sample(
                        run_id="run-env",
                        trial_index=0,
                        repo_root=root,
                        source_paths=("bench_subject.py",),
                        whole_loop_seal=_seal(),
                        operation=subject.measured_operation,
                        quality_scorer=subject.quality_scorer,
                        provenance_refs=("runpackage:run-env",),
                    )

    def test_backward_clock_and_invalid_quality_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root)
            with (
                patch("frankenstein2.whole_system_measurement.observe_host_environment", side_effect=[_environment(), _environment()]),
                patch("frankenstein2.whole_system_measurement._peak_rss_bytes", side_effect=[100, 200]),
                patch("frankenstein2.whole_system_measurement.time.perf_counter_ns", side_effect=[20, 10]),
            ):
                with self.assertRaisesRegex(WholeSystemMeasurementError, "clock moved backwards"):
                    measure_characterization_sample(
                        run_id="run-clock",
                        trial_index=0,
                        repo_root=root,
                        source_paths=("bench_subject.py",),
                        whole_loop_seal=_seal(),
                        operation=subject.measured_operation,
                        quality_scorer=subject.quality_scorer,
                        provenance_refs=("runpackage:run-clock",),
                    )

            path = root / "bench_subject.py"
            path.write_text("def measured_operation():\n    return 1\n\ndef quality_scorer(result):\n    return 1000001\n", encoding="utf-8")
            module_name = f"wp902_bad_quality_{id(root)}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            assert spec is not None and spec.loader is not None
            bad_quality = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = bad_quality
            spec.loader.exec_module(bad_quality)
            with (
                patch("frankenstein2.whole_system_measurement.observe_host_environment", side_effect=[_environment(), _environment()]),
                patch("frankenstein2.whole_system_measurement._peak_rss_bytes", side_effect=[100, 200]),
                patch("frankenstein2.whole_system_measurement.time.perf_counter_ns", side_effect=[10, 20]),
            ):
                with self.assertRaisesRegex(WholeSystemMeasurementError, "quality_scorer"):
                    measure_characterization_sample(
                        run_id="run-quality",
                        trial_index=0,
                        repo_root=root,
                        source_paths=("bench_subject.py",),
                        whole_loop_seal=_seal(),
                        operation=bad_quality.measured_operation,
                        quality_scorer=bad_quality.quality_scorer,
                        provenance_refs=("runpackage:run-quality",),
                    )

    def test_real_repository_host_probe_emits_candidate_not_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subject = _load_subject(root)
            sample = measure_characterization_sample(
                run_id="repo-host-smoke",
                trial_index=0,
                repo_root=root,
                source_paths=("bench_subject.py",),
                whole_loop_seal=_seal(),
                operation=subject.measured_operation,
                quality_scorer=subject.quality_scorer,
                provenance_refs=("ci:repository-host-smoke",),
            )
            self.assertGreaterEqual(sample.latency_ns, 0)
            self.assertGreater(sample.peak_rss_bytes, 0)
            self.assertEqual(sample.quality_micros, 900_000)
            self.assertIn("CANDIDATE", sample.classification)


if __name__ == "__main__":
    unittest.main()
