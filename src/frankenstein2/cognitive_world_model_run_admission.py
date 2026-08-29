"""Evaluator-side predeclared run admission for the F2-WP-803 benchmark.

This module narrows and strengthens generation-2 run provenance after the post-merge
co-forge falsifier. ``PredictionCandidate`` remains public/untrusted.  Before candidate
construction, the evaluator may predeclare one exact WP800 ``RunDescriptor`` plus the
benchmark generation in a ``BenchmarkRunAdmission`` and persist/pin its digest in the
run harness. Evaluation then requires that exact predeclared digest.

The admission is repository evaluation provenance only. It is not world truth, runtime
acceptance, GRID/GWT/J-Space authority, effect authority, completion authority, causal
credit or training evidence.
"""
from __future__ import annotations

from dataclasses import InitVar, dataclass
import hashlib
import json
import re
from typing import Any

from .cognitive_microworld import (
    CognitiveMicroWorldError,
    EpisodeState,
    EvaluatorStep,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
)
from .cognitive_world_model_prediction_benchmark import (
    PredictionCandidate,
    PredictionEvaluation,
    WorldModelPredictionBenchmarkError,
    evaluate_next_observation_prediction,
)

RUN_ADMISSION_SCHEMA = "FRANKENSTEIN2_HELDOUT_WORLD_MODEL_RUN_ADMISSION/v1"
RUN_ADMISSION_CLASSIFICATION = "EVALUATOR_PREDECLARED_BENCHMARK_PROVENANCE_NOT_WORLD_AUTHORITY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_GENERATION = 1_000_000
_ADMISSION_ORIGIN = object()


class BenchmarkRunAdmissionError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise BenchmarkRunAdmissionError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise BenchmarkRunAdmissionError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise BenchmarkRunAdmissionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_GENERATION:
        raise BenchmarkRunAdmissionError(f"{name} must be a bounded non-negative integer")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class BenchmarkRunAdmission:
    """An evaluator-created immutable declaration of one intended benchmark run.

    ``predeclare`` deliberately accepts no PredictionCandidate.  The admission therefore
    can be built and externally pinned before an untrusted policy emits a prediction.
    The outer evaluator/run-package layer is responsible for persisting the returned
    ``sha256`` as the expected admission identity before candidate scoring.
    """

    schema: str
    admission_id: str
    manifest_ref: str
    benchmark_generation: int
    run_id: str
    run_descriptor_sha256: str
    system_under_test_ref: str
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    classification: str = RUN_ADMISSION_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != RUN_ADMISSION_SCHEMA or self.classification != RUN_ADMISSION_CLASSIFICATION:
            raise BenchmarkRunAdmissionError("run-admission schema/classification mismatch")
        for name, value in (
            ("admission_id", self.admission_id),
            ("manifest_ref", self.manifest_ref),
            ("run_id", self.run_id),
            ("system_under_test_ref", self.system_under_test_ref),
            ("fixture_id", self.fixture_id),
        ):
            _id(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("fixture_generation", self.fixture_generation)
        _sha("run_descriptor_sha256", self.run_descriptor_sha256)
        _sha("fixture_sha256", self.fixture_sha256)
        if _origin is not _ADMISSION_ORIGIN:
            raise BenchmarkRunAdmissionError("BenchmarkRunAdmission must be created by predeclare")

    @classmethod
    def predeclare(
        cls,
        fixture: MicroWorldFixture,
        run_descriptor: RunDescriptor,
        *,
        admission_id: str,
        manifest_ref: str,
        benchmark_generation: int,
    ) -> "BenchmarkRunAdmission":
        """Seal exact evaluator-side run provenance before candidate construction."""
        if type(fixture) is not MicroWorldFixture:
            raise BenchmarkRunAdmissionError("fixture must be exact concrete MicroWorldFixture")
        if type(run_descriptor) is not RunDescriptor:
            raise BenchmarkRunAdmissionError("run_descriptor must be exact concrete RunDescriptor")
        if not getattr(run_descriptor, "_builder_verified", False):
            raise BenchmarkRunAdmissionError("run_descriptor must originate from RunDescriptor.for_fixture")
        try:
            run_descriptor.assert_matches_fixture(fixture)
        except CognitiveMicroWorldError as exc:
            raise BenchmarkRunAdmissionError("run descriptor/fixture provenance mismatch") from exc
        _generation("benchmark_generation", benchmark_generation)
        return cls(
            RUN_ADMISSION_SCHEMA,
            admission_id,
            manifest_ref,
            benchmark_generation,
            run_descriptor.run_id,
            run_descriptor.sha256(),
            run_descriptor.system_under_test_ref,
            fixture.fixture_id,
            fixture.generation,
            fixture.sha256(),
            _origin=_ADMISSION_ORIGIN,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "admission_id": self.admission_id,
            "manifest_ref": self.manifest_ref,
            "benchmark_generation": self.benchmark_generation,
            "run_id": self.run_id,
            "run_descriptor_sha256": self.run_descriptor_sha256,
            "system_under_test_ref": self.system_under_test_ref,
            "fixture_id": self.fixture_id,
            "fixture_generation": self.fixture_generation,
            "fixture_sha256": self.fixture_sha256,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def assert_matches(
        self,
        fixture: MicroWorldFixture,
        prediction: PredictionCandidate,
        run_descriptor: RunDescriptor,
    ) -> None:
        if type(fixture) is not MicroWorldFixture:
            raise BenchmarkRunAdmissionError("fixture must be exact concrete MicroWorldFixture")
        if type(prediction) is not PredictionCandidate:
            raise BenchmarkRunAdmissionError("prediction must be exact concrete PredictionCandidate")
        if type(run_descriptor) is not RunDescriptor:
            raise BenchmarkRunAdmissionError("run_descriptor must be exact concrete RunDescriptor")
        if not getattr(run_descriptor, "_builder_verified", False):
            raise BenchmarkRunAdmissionError("run_descriptor must originate from RunDescriptor.for_fixture")
        try:
            run_descriptor.assert_matches_fixture(fixture)
        except CognitiveMicroWorldError as exc:
            raise BenchmarkRunAdmissionError("run descriptor/fixture provenance mismatch") from exc
        expected_fixture = (self.fixture_id, self.fixture_generation, self.fixture_sha256)
        actual_fixture = (fixture.fixture_id, fixture.generation, fixture.sha256())
        if actual_fixture != expected_fixture:
            raise BenchmarkRunAdmissionError("fixture/run admission mismatch")
        if run_descriptor.sha256() != self.run_descriptor_sha256:
            raise BenchmarkRunAdmissionError("run descriptor digest/admission mismatch")
        if run_descriptor.run_id != self.run_id or prediction.benchmark_run_id != self.run_id:
            raise BenchmarkRunAdmissionError("benchmark run id/admission mismatch")
        if (
            run_descriptor.system_under_test_ref != self.system_under_test_ref
            or prediction.policy_id != self.system_under_test_ref
        ):
            raise BenchmarkRunAdmissionError("system-under-test/admission mismatch")
        if prediction.benchmark_generation != self.benchmark_generation:
            raise BenchmarkRunAdmissionError("prediction benchmark generation/admission mismatch")


def evaluate_admitted_next_observation_prediction(
    fixture: MicroWorldFixture,
    *,
    state: EpisodeState,
    action_id: str,
    prediction: PredictionCandidate,
    run_descriptor: RunDescriptor,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
) -> tuple[EpisodeState, ObservationView, EvaluatorStep, PredictionEvaluation]:
    """Score only after matching an externally pinned predeclared admission digest.

    The expected digest is intentionally separate from the candidate and descriptor.  A
    harness/run-package must pin it before candidate scoring.  Constructing a fresh,
    internally consistent descriptor+admission pair after seeing a candidate cannot pass
    when the predeclared expected digest is retained.
    """
    if type(run_admission) is not BenchmarkRunAdmission:
        raise BenchmarkRunAdmissionError("run_admission must be exact concrete BenchmarkRunAdmission")
    expected = _sha("expected_run_admission_sha256", expected_run_admission_sha256)
    if run_admission.sha256() != expected:
        raise BenchmarkRunAdmissionError("run admission digest does not match predeclared expected digest")
    run_admission.assert_matches(fixture, prediction, run_descriptor)
    try:
        return evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id=action_id,
            prediction=prediction,
            run_descriptor=run_descriptor,
        )
    except WorldModelPredictionBenchmarkError:
        raise
