#!/usr/bin/env python3
"""Deterministic semantic claim-key compiler for Trigger 7.

This tool does not create the canonical GitHub claim by itself. It compiles a
bounded semantic objective into a stable key/path. The caller must then perform
a create-only write to that exact path in the canonical F2 repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

SCHEMA = "T7_SEMANTIC_OBJECTIVE/v1"
CLAIM_SCHEMA = "T7_SEMANTIC_CLAIM/v1"
CLAIM_ROOT = "research/local_voice/semantic_claims"


def _norm_atom(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("semantic objective fields must be non-empty strings")
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = value.replace("_", "-")
    value = re.sub(r"[^a-z0-9.+-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


FAMILY_ALIASES = {
    "target-runtime-hardware-inventory": "TARGET_RUNTIME_HARDWARE_INVENTORY",
    "vps-hardware-inventory": "TARGET_RUNTIME_HARDWARE_INVENTORY",
    "vps-bridge-hardware-inventory": "TARGET_RUNTIME_HARDWARE_INVENTORY",
    "clay-direct-dev-hardware-inventory": "TARGET_RUNTIME_HARDWARE_INVENTORY",
    "local-llm-unmodified-baseline": "LOCAL_LLM_UNMODIFIED_BASELINE",
    "official-qwen3.5-4b-baseline": "LOCAL_LLM_UNMODIFIED_BASELINE",
    "official-qwen35-4b-baseline": "LOCAL_LLM_UNMODIFIED_BASELINE",
    "german-asr-benchmark": "GERMAN_ASR_BENCHMARK",
    "german-tts-benchmark": "GERMAN_TTS_BENCHMARK",
    "german-turn-controller-benchmark": "GERMAN_TURN_CONTROLLER_BENCHMARK",
    "full-duplex-german-falsifier": "FULL_DUPLEX_GERMAN_FALSIFIER",
}

TARGET_ALIASES = {
    "clay-direct-dev": "clay-direct-dev",
    "claydirectdev": "clay-direct-dev",
    "f2-repository": "frankenstein-2.0-repository",
    "frankenstein-2.0-repository": "frankenstein-2.0-repository",
    "source-only": "source-only",
}

SUBJECT_ALIASES = {
    "frankenstein": "FRANKENSTEIN_2_0",
    "frankenstein-2.0": "FRANKENSTEIN_2_0",
    "f2": "FRANKENSTEIN_2_0",
    "whole-frankenstein": "FRANKENSTEIN_2_0",
    "whole-frankenstein-resource-envelope": "FRANKENSTEIN_2_0_RESOURCE_ENVELOPE",
    "qwen3.5-4b": "QWEN3_5_4B",
    "qwen35-4b": "QWEN3_5_4B",
    "qwen3-asr": "QWEN3_ASR",
    "nemotron-3.5-asr-streaming-0.6b": "NEMOTRON_3_5_ASR_STREAMING_0_6B",
}

EVIDENCE_SCOPE_ALIASES = {
    "target-runtime-hardware-receipt": "TARGET_RUNTIME_HARDWARE_RECEIPT",
    "hardware-receipt": "TARGET_RUNTIME_HARDWARE_RECEIPT",
    "whole-frankenstein-resource-envelope": "TARGET_RUNTIME_HARDWARE_RECEIPT",
    "source-pin": "SOURCE_PIN",
    "source-only": "SOURCE_PIN",
    "target-runtime-model-benchmark": "TARGET_RUNTIME_MODEL_BENCHMARK",
    "german-e2e-voice-benchmark": "GERMAN_E2E_VOICE_BENCHMARK",
    "component-benchmark": "COMPONENT_BENCHMARK",
}


def _resolve(value: str, aliases: dict[str, str], field: str) -> str:
    key = _norm_atom(value)
    if key not in aliases:
        allowed = ", ".join(sorted(aliases))
        raise ValueError(
            f"unknown {field} alias {value!r}; fail closed. "
            f"Use one of the admitted aliases: {allowed}"
        )
    return aliases[key]


@dataclass(frozen=True)
class SemanticObjective:
    family: str
    target_surface: str
    subject: str
    evidence_scope: str
    generation: int = 1

    @classmethod
    def from_inputs(
        cls,
        *,
        family: str,
        target_surface: str,
        subject: str,
        evidence_scope: str,
        generation: int = 1,
    ) -> "SemanticObjective":
        if not isinstance(generation, int) or generation < 1:
            raise ValueError("generation must be an integer >= 1")
        return cls(
            family=_resolve(family, FAMILY_ALIASES, "family"),
            target_surface=_resolve(target_surface, TARGET_ALIASES, "target_surface"),
            subject=_resolve(subject, SUBJECT_ALIASES, "subject"),
            evidence_scope=_resolve(
                evidence_scope, EVIDENCE_SCOPE_ALIASES, "evidence_scope"
            ),
            generation=generation,
        )

    def canonical_object(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "family": self.family,
            "target_surface": self.target_surface,
            "subject": self.subject,
            "evidence_scope": self.evidence_scope,
            "generation": self.generation,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_object(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def semantic_key(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def claim_path(self) -> str:
        return f"{CLAIM_ROOT}/{self.semantic_key()}.json"

    def claim_payload(
        self,
        *,
        human_claim_path: str,
        research_id: str,
        objective: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": CLAIM_SCHEMA,
            "semantic_key": self.semantic_key(),
            "semantic_objective": self.canonical_object(),
            "canonical_claim_path": self.claim_path(),
            "human_claim_path": human_claim_path,
            "research_id": research_id,
            "objective": objective,
            "state": "CLAIMED_CREATE_ONLY",
            "evidence_credit": 0,
            "runtime_credit": 0,
            "acceptance_credit": 0,
        }
        if description:
            payload["description"] = description
        return payload


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Compile a Trigger-7 semantic objective to its canonical create-only "
            "claim key/path. Free-text description is metadata and never part of the key."
        )
    )
    p.add_argument("--family", required=True)
    p.add_argument("--target-surface", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--evidence-scope", required=True)
    p.add_argument("--generation", type=int, default=1)
    p.add_argument("--research-id", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--human-claim-path", required=True)
    p.add_argument("--description")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    objective = SemanticObjective.from_inputs(
        family=args.family,
        target_surface=args.target_surface,
        subject=args.subject,
        evidence_scope=args.evidence_scope,
        generation=args.generation,
    )
    output = {
        "semantic_key": objective.semantic_key(),
        "canonical_claim_path": objective.claim_path(),
        "canonical_json": objective.canonical_json(),
        "claim_payload": objective.claim_payload(
            human_claim_path=args.human_claim_path,
            research_id=args.research_id,
            objective=args.objective,
            description=args.description,
        ),
        "create_only_required": True,
        "existing_path_means": "LOSE_CLAIM_AND_ROUTE_TO_NONDUPLICATE_OBJECTIVE",
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
