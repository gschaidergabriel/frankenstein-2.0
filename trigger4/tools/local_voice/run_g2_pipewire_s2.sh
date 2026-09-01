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
PIPER_RUNTIME_VERSION="$($VENV/bin/python -c 'import importlib.metadata; print(importlib.metadata.version("piper-tts"))')"
test "$PIPER_RUNTIME_VERSION" = '1.7.0'

cat >"$WORK/source.txt" <<'TXT'
Dies ist eine lange lokale deutsche Sprachausgabe fuer den kausalen PipeWire Abbruchtest. Sie muss lange genug laufen, damit ein echter Abbruch mitten in der Wiedergabe gemessen werden kann. Nach dem Abbruch darf die alte Ausgabe nur noch innerhalb des vorher festgelegten kurzen Pufferfensters erscheinen. Danach muss der virtuelle Monitor frei von fortgesetzter alter Sprachausgabe sein.
TXT
cat >"$WORK/replacement.txt" <<'TXT'
Dies ist die eindeutig neue lokale deutsche Sprachausgabe nach dem Abbruch. Sie gehoert zu einer neuen Ausgabegeneration und muss nach der alten unterbrochenen Ausgabe positiv auf demselben virtuellen PipeWire Monitor nachgewiesen werden.
TXT

PIPER_MODEL="$ASSETS/piper.onnx" \
PIPER_CONFIG="$ASSETS/piper.onnx.json" \
OLD_TEXT="$WORK/source.txt" \
NEW_TEXT="$WORK/replacement.txt" \
OLD_WAV="$WORK/source.wav" \
NEW_WAV="$WORK/replacement.wav" \
"$VENV/bin/python" - <<'PY'
import os
from pathlib import Path
import numpy as np
import soundfile as sf
from piper import PiperVoice

model = Path(os.environ['PIPER_MODEL'])
config = Path(os.environ['PIPER_CONFIG'])
voice = PiperVoice.load(str(model), config_path=str(config), use_cuda=False)

def synth(text_path: str, wav_path: str, minimum_seconds: float) -> None:
    text = Path(text_path).read_text(encoding='utf-8').strip()
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
    if audio.size / rate < minimum_seconds:
        raise RuntimeError(f'PIPER_SOURCE_TOO_SHORT:{audio.size / rate:.3f}')
    sf.write(wav_path, audio, rate, subtype='PCM_16')
    print(f'PIPER_WAV={wav_path} RATE={rate} SAMPLES={audio.size} DURATION={audio.size / rate:.6f}')

synth(os.environ['OLD_TEXT'], os.environ['OLD_WAV'], 3.0)
synth(os.environ['NEW_TEXT'], os.environ['NEW_WAV'], 1.0)
if Path(os.environ['OLD_WAV']).read_bytes() == Path(os.environ['NEW_WAV']).read_bytes():
    raise RuntimeError('PIPER_REPLACEMENT_NOT_DISTINCT')
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
export G2_SOURCE_TEXT="$WORK/source.txt"
export G2_REPLACEMENT="$WORK/replacement.wav"
export G2_REPLACEMENT_TEXT="$WORK/replacement.txt"
export G2_ANALYZER="$PWD/research/local_voice/tools/t7_pipewire_monitor_cancel_analyze.py"
export G2_HARNESS="$PWD/trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"
export PIPER_MODEL_SHA256 PIPER_CONFIG_SHA256 PIPER_RUNTIME_VERSION

runuser -u f2audio -- env \
  F2_ROOT="$F2_ROOT" F2_SUBJECT_SHA="$F2_SUBJECT_SHA" G2_WORK="$G2_WORK" G2_RUNTIME="$G2_RUNTIME" \
  G2_VENV="$G2_VENV" G2_SOURCE="$G2_SOURCE" G2_SOURCE_TEXT="$G2_SOURCE_TEXT" \
  G2_REPLACEMENT="$G2_REPLACEMENT" G2_REPLACEMENT_TEXT="$G2_REPLACEMENT_TEXT" \
  G2_ANALYZER="$G2_ANALYZER" G2_HARNESS="$G2_HARNESS" \
  PIPER_MODEL_SHA256="$PIPER_MODEL_SHA256" PIPER_CONFIG_SHA256="$PIPER_CONFIG_SHA256" \
  PIPER_RUNTIME_VERSION="$PIPER_RUNTIME_VERSION" \
  XDG_RUNTIME_DIR="$RUNTIME" HOME="$(getent passwd f2audio | cut -d: -f6)" PYTHONPATH="$PWD/src" \
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
    set +e
    "$G2_VENV/bin/python" "$G2_HARNESS" \
      --source "$G2_SOURCE" \
      --source-text-file "$G2_SOURCE_TEXT" \
      --replacement-source "$G2_REPLACEMENT" \
      --replacement-text-file "$G2_REPLACEMENT_TEXT" \
      --analyzer "$G2_ANALYZER" \
      --workdir "$G2_WORK/evidence" \
      --f2-subject-sha "$F2_SUBJECT_SHA" \
      --tts-model-sha256 "$PIPER_MODEL_SHA256" \
      --tts-config-sha256 "$PIPER_CONFIG_SHA256" \
      --tts-runtime-version "$PIPER_RUNTIME_VERSION" \
      --cancel-after-ms 1200
    harness_status=$?
    set -e
    printf "G2_PIPEWIRE_HARNESS_EXIT=%s\n" "$harness_status"
    cat "$G2_WORK/pipewire.log" >&2 || true
    cat "$G2_WORK/pipewire-pulse.log" >&2 || true
    cat "$G2_WORK/wireplumber.log" >&2 || true
    exit 0
  '
