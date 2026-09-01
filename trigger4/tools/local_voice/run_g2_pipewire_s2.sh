#!/usr/bin/env bash
set -Eeuo pipefail

: "${F2_SUBJECT_SHA:?F2_SUBJECT_SHA is required}"

test "$(git rev-parse HEAD)" = "$F2_SUBJECT_SHA"

WORK=/tmp/t4-g2-pipewire
ASSETS=/tmp/t4-g2-pipewire-assets
VENV=/tmp/t4-g2-pipewire-venv
RUNTIME=/tmp/t4-g2-pipewire-runtime
rm -rf "$WORK" "$ASSETS" "$VENV" "$RUNTIME"
mkdir -p "$WORK" "$ASSETS" "$RUNTIME"

PIPER_MODEL_URL='https://huggingface.co/Thorsten-Voice/Piper/resolve/4c56824d7a76ee98b08a6e9046e640727397fac7/de_DE-thorsten-medium.onnx?download=true'
PIPER_CONFIG_URL='https://huggingface.co/Thorsten-Voice/Piper/resolve/4c56824d7a76ee98b08a6e9046e640727397fac7/de_DE-thorsten-medium.onnx.json?download=true'
PIPER_MODEL_SHA256='7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819'
PIPER_CONFIG_SHA256='974adee790533adb273a1ac88f49027d2a1b8f0f2cf4905954a4791e79264e85'

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl dbus-user-session espeak-ng git libsndfile1 \
  pipewire pipewire-bin pipewire-pulse pulseaudio-utils python3 python3-pip python3-venv \
  wireplumber >/tmp/t4-g2-apt.log 2>&1

for x in pipewire pipewire-pulse wireplumber pactl parec paplay pw-dump pw-metadata python3 curl; do
  command -v "$x" >/dev/null
  printf 'TOOL %s %s\n' "$x" "$(command -v "$x")"
done

curl -fL --retry 3 --retry-delay 2 "$PIPER_MODEL_URL" -o "$ASSETS/piper.onnx"
curl -fL --retry 3 --retry-delay 2 "$PIPER_CONFIG_URL" -o "$ASSETS/piper.onnx.json"
printf '%s  %s\n' "$PIPER_MODEL_SHA256" "$ASSETS/piper.onnx" | sha256sum -c -
printf '%s  %s\n' "$PIPER_CONFIG_SHA256" "$ASSETS/piper.onnx.json" | sha256sum -c -

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check \
  'numpy==1.26.4' 'soundfile==0.13.1' 'piper-tts==1.7.0'

PIPER_MODEL="$ASSETS/piper.onnx" \
PIPER_CONFIG="$ASSETS/piper.onnx.json" \
SOURCE_WAV="$WORK/source.wav" \
REPLACEMENT_WAV="$WORK/replacement.wav" \
TTS_RECEIPT="$WORK/tts-receipt.json" \
PIPER_MODEL_SHA256="$PIPER_MODEL_SHA256" \
PIPER_CONFIG_SHA256="$PIPER_CONFIG_SHA256" \
"$VENV/bin/python" - <<'PY'
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import numpy as np
import soundfile as sf
from piper import PiperVoice

model = Path(os.environ['PIPER_MODEL'])
config = Path(os.environ['PIPER_CONFIG'])
source_out = Path(os.environ['SOURCE_WAV'])
replacement_out = Path(os.environ['REPLACEMENT_WAV'])
receipt_out = Path(os.environ['TTS_RECEIPT'])

source_text = (
    'Dies ist eine lange lokale deutsche Sprachausgabe fuer den kausalen PipeWire Abbruchtest. '
    'Sie muss lange genug laufen, damit ein echter Abbruch mitten in der Wiedergabe gemessen werden kann. '
    'Nach dem Abbruch darf die alte Ausgabe nur noch innerhalb des vorher festgelegten kurzen Pufferfensters erscheinen. '
    'Danach muss der virtuelle Monitor frei von fortgesetzter alter Sprachausgabe sein.'
)
replacement_text = (
    'Neue Ausgabe nach dem Abbruch. Diese zweite Generation muss eindeutig neu sein und auf demselben '
    'virtuellen PipeWire Monitor positiv beobachtet werden.'
)

voice = PiperVoice.load(str(model), config_path=str(config), use_cuda=False)


def synthesize(text: str, out: Path) -> dict:
    parts = []
    rates = set()
    for chunk in voice.synthesize(text):
        arr = np.asarray(chunk.audio_float_array, dtype=np.float32)
        if arr.ndim != 1 or arr.size == 0 or not np.isfinite(arr).all():
            raise RuntimeError('PIPER_INVALID_AUDIO_CHUNK')
        parts.append(arr)
        rates.add(int(chunk.sample_rate))
    if not parts or len(rates) != 1:
        raise RuntimeError('PIPER_NO_UNIQUE_AUDIO_RATE')
    audio = np.concatenate(parts)
    rate = rates.pop()
    sf.write(out, audio, rate, subtype='PCM_16')
    return {'rate': rate, 'samples': int(audio.size), 'duration_s': float(audio.size / rate)}


source_meta = synthesize(source_text, source_out)
replacement_meta = synthesize(replacement_text, replacement_out)
if source_meta['duration_s'] < 3.0:
    raise RuntimeError('PIPER_SOURCE_TOO_SHORT')
if replacement_meta['duration_s'] < 0.5:
    raise RuntimeError('PIPER_REPLACEMENT_TOO_SHORT')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


source_sha = sha(source_out)
replacement_sha = sha(replacement_out)
if source_sha == replacement_sha:
    raise RuntimeError('PIPER_SOURCE_REPLACEMENT_COLLISION')

receipt = {
    'schema': 'T4_G2_LOCAL_TTS_BINDING_RECEIPT/v1',
    'provenance': 'LOCAL_PINNED_PIPER_TTS__NO_EXTERNAL_INFERENCE_API',
    'piper_tts_version': importlib.metadata.version('piper-tts'),
    'model_sha256': os.environ['PIPER_MODEL_SHA256'],
    'config_sha256': os.environ['PIPER_CONFIG_SHA256'],
    'source_text': source_text,
    'replacement_text': replacement_text,
    'source_wav_sha256': source_sha,
    'replacement_wav_sha256': replacement_sha,
    'source_meta': source_meta,
    'replacement_meta': replacement_meta,
}
receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
print(f'PIPER_SOURCE_RATE={source_meta["rate"]}')
print(f'PIPER_SOURCE_SAMPLES={source_meta["samples"]}')
print(f'PIPER_SOURCE_DURATION={source_meta["duration_s"]:.6f}')
print(f'PIPER_REPLACEMENT_RATE={replacement_meta["rate"]}')
print(f'PIPER_REPLACEMENT_SAMPLES={replacement_meta["samples"]}')
print(f'PIPER_REPLACEMENT_DURATION={replacement_meta["duration_s"]:.6f}')
print(f'TTS_RECEIPT_SHA256={sha(receipt_out)}')
PY

if ! id -u f2audio >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash f2audio
fi
chown -R f2audio:f2audio "$WORK" "$RUNTIME"
chmod 700 "$RUNTIME"

export F2_ROOT="$PWD"
export G2_WORK="$WORK"
export G2_RUNTIME="$RUNTIME"
export G2_VENV="$VENV"
export G2_SOURCE="$WORK/source.wav"
export G2_REPLACEMENT="$WORK/replacement.wav"
export G2_TTS_RECEIPT="$WORK/tts-receipt.json"
export G2_PREFLIGHT_RECEIPT="$WORK/preflight-bound.json"
export G2_ANALYZER="$PWD/research/local_voice/tools/t7_pipewire_monitor_cancel_analyze.py"
export G2_HARNESS="$PWD/trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"
export PIPER_MODEL_SHA256 PIPER_CONFIG_SHA256

runuser -u f2audio -- env \
  F2_ROOT="$F2_ROOT" \
  F2_SUBJECT_SHA="$F2_SUBJECT_SHA" \
  G2_WORK="$G2_WORK" \
  G2_RUNTIME="$G2_RUNTIME" \
  G2_VENV="$G2_VENV" \
  G2_SOURCE="$G2_SOURCE" \
  G2_REPLACEMENT="$G2_REPLACEMENT" \
  G2_TTS_RECEIPT="$G2_TTS_RECEIPT" \
  G2_PREFLIGHT_RECEIPT="$G2_PREFLIGHT_RECEIPT" \
  G2_ANALYZER="$G2_ANALYZER" \
  G2_HARNESS="$G2_HARNESS" \
  PIPER_MODEL_SHA256="$PIPER_MODEL_SHA256" \
  PIPER_CONFIG_SHA256="$PIPER_CONFIG_SHA256" \
  XDG_RUNTIME_DIR="$RUNTIME" \
  HOME="$(getent passwd f2audio | cut -d: -f6)" \
  PYTHONPATH="$PWD/src" \
  dbus-run-session -- bash -lc '
    set -Eeuo pipefail
    pipewire >"$G2_WORK/pipewire.log" 2>&1 & pw_pid=$!
    pipewire-pulse >"$G2_WORK/pipewire-pulse.log" 2>&1 & pulse_pid=$!
    wireplumber >"$G2_WORK/wireplumber.log" 2>&1 & wp_pid=$!
    cleanup_session() {
      kill "$wp_pid" "$pulse_pid" "$pw_pid" 2>/dev/null || true
      wait "$wp_pid" "$pulse_pid" "$pw_pid" 2>/dev/null || true
    }
    trap cleanup_session EXIT
    for i in $(seq 1 40); do
      if pactl info >/tmp/t4-g2-pactl-info.txt 2>/tmp/t4-g2-pactl-info.err; then break; fi
      sleep 0.25
    done
    pactl info
    pipewire --version
    wireplumber --version || true

    SETTINGS="$G2_WORK/preflight-settings.txt"
    pw-metadata -n settings >"$SETTINGS"
    SETTINGS="$SETTINGS" OUT="$G2_PREFLIGHT_RECEIPT" "$G2_VENV/bin/python" - <<"PY"
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

settings_path = Path(os.environ["SETTINGS"])
out = Path(os.environ["OUT"])
text = settings_path.read_text(errors="replace")


def value(key: str) -> int:
    patterns = (
        rf"key:[\"'']{re.escape(key)}[\"''][^\\n]*value:[\"'']?([0-9]+)",
        rf"{re.escape(key)}[^0-9\\n]+([0-9]+)",
    )
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    raise SystemExit(f"PREFLIGHT_METADATA_MISSING:{key}")


rate = value("clock.rate")
quantum = value("clock.quantum")
if rate <= 0 or quantum <= 0:
    raise SystemExit("PREFLIGHT_CLOCK_INVALID")
max_inflight_quanta = 12
derived_ms = math.ceil((quantum / rate) * 1000.0 * max_inflight_quanta)
if not 10 <= derived_ms <= 1000:
    raise SystemExit(f"PREFLIGHT_DERIVED_BOUND_OUT_OF_RANGE:{derived_ms}")
receipt = {
    "schema": "T4_G2_PIPEWIRE_PREFLIGHT_BOUND/v1",
    "captured_before_harness_control": True,
    "clock_rate": rate,
    "clock_quantum": quantum,
    "policy": {
        "max_inflight_quanta": max_inflight_quanta,
        "formula": "ceil(clock.quantum/clock.rate*1000*max_inflight_quanta)",
    },
    "derived_max_inflight_ms": derived_ms,
    "settings_sha256": hashlib.sha256(text.encode()).hexdigest(),
    "captured_monotonic_ns": time.monotonic_ns(),
}
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(f"G2_DERIVED_MAX_INFLIGHT_MS={derived_ms}")
PY

    G2_MAX_INFLIGHT_MS="$("$G2_VENV/bin/python" -c "import json; print(json.load(open(\"$G2_PREFLIGHT_RECEIPT\"))[\"derived_max_inflight_ms\"])")"
    test -n "$G2_MAX_INFLIGHT_MS"
    printf "G2_PREFLIGHT_RECEIPT_SHA256=%s\n" "$(sha256sum "$G2_PREFLIGHT_RECEIPT" | awk "{print \\$1}")"
    printf "G2_MAX_INFLIGHT_MS=%s\n" "$G2_MAX_INFLIGHT_MS"

    set +e
    "$G2_VENV/bin/python" "$G2_HARNESS" \
      --source "$G2_SOURCE" \
      --replacement-source "$G2_REPLACEMENT" \
      --tts-receipt "$G2_TTS_RECEIPT" \
      --preflight-receipt "$G2_PREFLIGHT_RECEIPT" \
      --analyzer "$G2_ANALYZER" \
      --workdir "$G2_WORK/evidence" \
      --f2-subject-sha "$F2_SUBJECT_SHA" \
      --tts-model-sha256 "$PIPER_MODEL_SHA256" \
      --tts-config-sha256 "$PIPER_CONFIG_SHA256" \
      --cancel-after-ms 1200 \
      --max-inflight-ms "$G2_MAX_INFLIGHT_MS"
    harness_status=$?
    set -e
    printf "G2_PIPEWIRE_HARNESS_EXIT=%s\n" "$harness_status"
    cat "$G2_WORK/pipewire.log" >&2 || true
    cat "$G2_WORK/pipewire-pulse.log" >&2 || true
    cat "$G2_WORK/wireplumber.log" >&2 || true
    exit 0
  '
