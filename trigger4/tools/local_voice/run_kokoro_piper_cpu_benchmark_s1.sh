#!/usr/bin/env bash
set -Eeuo pipefail

stage="START"
emit_blocker() {
  local rc="$1"
  local payload
  payload="$(printf '{"schema":"T4_LOCAL_VOICE_KOKORO_PIPER_CPU_DISCRIMINATOR/v1","research_id":"T7-TTS-KOKORO-001","objective":"E3_THORSTEN_KOKORO_82M_VS_PIPER_GERMAN_CPU_FILE_OUTPUT","result":"BLOCKED","failure_class":"INFRA_AUTH_TRANSPORT_QUOTA_OR_SETUP","stage":"%s","exit_code":%s,"cpu_file_output_component_credit":0,"audible_playback_credit":0,"trigger4_f2_acceptance_credit":0,"whole_system_credit":0}' "$stage" "$rc")"
  printf 'T4_RECEIPT_B64=%s\n' "$(printf '%s' "$payload" | base64 -w0)"
}
trap 'rc=$?; emit_blocker "$rc"; exit "$rc"' ERR

KOKORO_MODEL_REV="734e593d320a3d876bede7020f773dfd481a0cc7"
KOKORO_RUNTIME_COMMIT="b96fef95e6a746495f92443fac7c688f90fc57fc"
MISAKI_COMMIT="6d252a2e02f3b030f22f56686f1a73786c16ffc8"
PIPER_MODEL_REV="4c56824d7a76ee98b08a6e9046e640727397fac7"

stage="OS_PACKAGES"
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update
apt-get -qq install -y --no-install-recommends \
  ca-certificates git espeak-ng libsndfile1 python3 python3-pip python3-venv

stage="PYTHON_VENV"
python3 -m venv /tmp/t4-voicebench-venv
source /tmp/t4-voicebench-venv/bin/activate
python -m pip install -q "pip==25.2"

stage="PYTHON_RUNTIME_PINS"
python -m pip install -q \
  "numpy==1.26.4" \
  "soundfile==0.13.1" \
  "huggingface_hub==0.34.4" \
  "transformers==4.55.4" \
  "loguru==0.7.3" \
  "num2words==0.5.14" \
  "piper-tts==1.7.0"
python -m pip install -q --extra-index-url https://download.pytorch.org/whl/cpu "torch==2.8.0+cpu"
python -m pip install -q "misaki[de] @ git+https://github.com/semidark/misaki.git@${MISAKI_COMMIT}"
python -m pip install -q --no-deps "git+https://github.com/semidark/kokoro.git@${KOKORO_RUNTIME_COMMIT}"

stage="IMPORT_PREFLIGHT"
python - <<'PY'
from num2words import num2words
from kokoro import KModel, KPipeline
assert num2words(42, lang="de")
assert KModel is not None and KPipeline is not None
print("KOKORO_IMPORT_PREFLIGHT=PASS")
PY

stage="PACKAGE_MANIFEST"
python -m pip freeze --all | LC_ALL=C sort > /tmp/t4-package-freeze.txt

stage="ARTIFACT_PREFETCH"
mkdir -p /tmp/t4-hf-cache /tmp/t4-artifacts
export HF_HOME=/tmp/t4-hf-cache
python - <<'PY' > /tmp/t4-artifact-paths.env
from huggingface_hub import hf_hub_download
from pathlib import Path
import shlex
import shutil

cache = "/tmp/t4-hf-cache"
out = Path("/tmp/t4-artifacts")
out.mkdir(parents=True, exist_ok=True)

specs = {
    "KOKORO_CONFIG": ("Thorsten-Voice/Kokoro", "config.json", "734e593d320a3d876bede7020f773dfd481a0cc7"),
    "KOKORO_MODEL": ("Thorsten-Voice/Kokoro", "model.pth", "734e593d320a3d876bede7020f773dfd481a0cc7"),
    "KOKORO_VOICE": ("Thorsten-Voice/Kokoro", "voices/thorsten.pt", "734e593d320a3d876bede7020f773dfd481a0cc7"),
    "PIPER_MODEL": ("Thorsten-Voice/Piper", "de_DE-thorsten-medium.onnx", "4c56824d7a76ee98b08a6e9046e640727397fac7"),
    "PIPER_CONFIG": ("Thorsten-Voice/Piper", "de_DE-thorsten-medium.onnx.json", "4c56824d7a76ee98b08a6e9046e640727397fac7"),
}
for key, (repo, filename, revision) in specs.items():
    src = Path(hf_hub_download(repo_id=repo, filename=filename, revision=revision, cache_dir=cache))
    if key == "PIPER_CONFIG":
        dst = out / "piper_model.onnx.json"
    elif key == "PIPER_MODEL":
        dst = out / "piper_model.onnx"
    elif key == "KOKORO_CONFIG":
        dst = out / "kokoro_config.json"
    elif key == "KOKORO_MODEL":
        dst = out / "kokoro_model.pth"
    else:
        dst = out / "kokoro_voice.pt"
    shutil.copyfile(src, dst)
    print(f"{key}={shlex.quote(str(dst))}")
PY
source /tmp/t4-artifact-paths.env

stage="ENGINE_BENCHMARKS"
set +e
python trigger4/tools/local_voice/kokoro_piper_cpu_benchmark.py \
  --engine kokoro \
  --output /tmp/t4-kokoro.json \
  --kokoro-config "$KOKORO_CONFIG" \
  --kokoro-model "$KOKORO_MODEL" \
  --kokoro-voice "$KOKORO_VOICE" \
  --piper-model "$PIPER_MODEL" \
  --piper-config "$PIPER_CONFIG"
kokoro_rc=$?

python trigger4/tools/local_voice/kokoro_piper_cpu_benchmark.py \
  --engine piper \
  --output /tmp/t4-piper.json \
  --kokoro-config "$KOKORO_CONFIG" \
  --kokoro-model "$KOKORO_MODEL" \
  --kokoro-voice "$KOKORO_VOICE" \
  --piper-model "$PIPER_MODEL" \
  --piper-config "$PIPER_CONFIG"
piper_rc=$?
set -e

stage="COMBINE_RECEIPT"
python - "$kokoro_rc" "$piper_rc" <<'PY' > /tmp/t4-combined.json
import json
from pathlib import Path
import subprocess
import sys

kokoro_rc, piper_rc = map(int, sys.argv[1:3])

def load(path):
    p = Path(path)
    if not p.exists():
        return {
            "schema": "T4_LOCAL_VOICE_CPU_ENGINE_BENCHMARK/v1",
            "result": "FAIL",
            "error": f"MISSING_ENGINE_RECEIPT:{path}",
            "failure_class": "EVIDENCE_INVALID",
        }
    return json.loads(p.read_text())

kokoro = load("/tmp/t4-kokoro.json")
piper = load("/tmp/t4-piper.json")
both_pass = kokoro.get("result") == "PASS" and piper.get("result") == "PASS" and kokoro_rc == 0 and piper_rc == 0

if both_pass:
    failure_class = None
    result = "PASS"
    component_credit = 1
else:
    errors = " | ".join(str(x.get("error", "")) for x in (kokoro, piper))
    if any(token in errors for token in ("HASH_MISMATCH", "VCS_PIN_MISMATCH", "DIRECT_URL_MISSING", "NETWORK_ATTEMPT")):
        failure_class = "EVIDENCE_INVALID"
    elif "MISSING_ENGINE_RECEIPT" in errors:
        failure_class = "INFRA_AUTH_TRANSPORT_QUOTA"
    else:
        failure_class = "PRODUCT_NEGATIVE_OR_EXECUTION_VALIDITY_REQUIRES_REVIEW"
    result = "FAIL"
    component_credit = 0

receipt = {
    "schema": "T4_LOCAL_VOICE_KOKORO_PIPER_CPU_DISCRIMINATOR/v1",
    "research_id": "T7-TTS-KOKORO-001",
    "objective": "E3_THORSTEN_KOKORO_82M_VS_PIPER_GERMAN_CPU_FILE_OUTPUT",
    "result": result,
    "failure_class": failure_class,
    "source_sha_inside_sandbox": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "target_surface": "clay-direct-dev",
    "sandbox_tier": "S1_OCI",
    "runtime_mode": "LOCAL_SOLO",
    "network_mode": "ON_FOR_PACKAGE_AND_ARTIFACT_ACQUISITION__SYNTHESIS_GUARDED_OFFLINE",
    "package_freeze": Path("/tmp/t4-package-freeze.txt").read_text().splitlines(),
    "engines": {"kokoro": kokoro, "piper": piper},
    "credits": {
        "cpu_file_output_component": component_credit,
        "audible_playback": 0,
        "first_audio_played_latency": 0,
        "cancellation_to_silence": 0,
        "heard_output_correctness": 0,
        "blind_quality_parity": 0,
        "stable_male_identity_runtime_quality": 0,
        "german_e2e_voice": 0,
        "trigger4_f2_acceptance": 0,
        "whole_system": 0,
    },
    "zero_credit_boundary_preserved": True,
    "next_exact_action": (
        "Trigger 7 consumes the measured CPU/file-output result without widening scope."
        if both_pass
        else "Classify the exact engine/setup failure; repair only the invalidated runtime boundary and rerun the identical discriminator."
    ),
}
print(json.dumps(receipt, indent=2, sort_keys=True))
PY

trap - ERR
printf 'T4_RECEIPT_B64=%s\n' "$(base64 -w0 /tmp/t4-combined.json)"

if [[ "$kokoro_rc" -ne 0 || "$piper_rc" -ne 0 ]]; then
  exit 1
fi