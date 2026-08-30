#!/usr/bin/env bash
set -euo pipefail

# Frankenstein 2 VPS multimodal empirical-lab bootstrap.
# Core media-store works with Python stdlib only. Optional tools increase generation/decoding reach.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORE_ROOT="${F2_MEDIA_LAB_ROOT:-$HOME/.cache/frankenstein2/media_lab}"
BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

mkdir -p "$STORE_ROOT" "$BIN_DIR" "$SYSTEMD_USER_DIR"
chmod 700 "$STORE_ROOT" || true

export F2_MEDIA_LAB_ROOT="$STORE_ROOT"
export F2_MEDIA_LAB_MAX_BYTES="${F2_MEDIA_LAB_MAX_BYTES:-10737418240}"
export F2_MEDIA_LAB_LOW_WATER_BYTES="${F2_MEDIA_LAB_LOW_WATER_BYTES:-8589934592}"
export F2_MEDIA_LAB_MAX_AGE_HOURS="${F2_MEDIA_LAB_MAX_AGE_HOURS:-72}"

if [[ "$F2_MEDIA_LAB_MAX_BYTES" -gt 10737418240 ]]; then
  echo "REFUSE: F2_MEDIA_LAB_MAX_BYTES may not exceed 10 GiB" >&2
  exit 2
fi

install_apt_tools() {
  local pkgs=(ffmpeg sox espeak-ng python3 python3-pip)
  if ! command -v apt-get >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}"
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo apt-get update
    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}"
  else
    echo "INFO: no non-interactive sudo; core store still works. Optional missing packages: ${pkgs[*]}" >&2
  fi
}

install_ytdlp() {
  if command -v yt-dlp >/dev/null 2>&1; then
    return 0
  fi
  if command -v pipx >/dev/null 2>&1; then
    pipx install yt-dlp || true
    return 0
  fi
  if python3 -m pip --version >/dev/null 2>&1; then
    python3 -m pip install --user --upgrade yt-dlp || true
  fi
}

install_apt_tools || true
install_ytdlp || true

cat > "$BIN_DIR/f2-media" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$REPO_ROOT/src\${PYTHONPATH:+:\$PYTHONPATH}"
export F2_MEDIA_LAB_ROOT="\${F2_MEDIA_LAB_ROOT:-$STORE_ROOT}"
export F2_MEDIA_LAB_MAX_BYTES="\${F2_MEDIA_LAB_MAX_BYTES:-10737418240}"
export F2_MEDIA_LAB_LOW_WATER_BYTES="\${F2_MEDIA_LAB_LOW_WATER_BYTES:-8589934592}"
export F2_MEDIA_LAB_MAX_AGE_HOURS="\${F2_MEDIA_LAB_MAX_AGE_HOURS:-72}"
exec python3 "$REPO_ROOT/src/frankenstein2/media_lab_store.py" "\$@"
EOF
chmod 755 "$BIN_DIR/f2-media"

cat > "$SYSTEMD_USER_DIR/frankenstein2-media-lab-gc.service" <<EOF
[Unit]
Description=Frankenstein 2 disposable multimodal media GC

[Service]
Type=oneshot
Environment=F2_MEDIA_LAB_ROOT=$STORE_ROOT
Environment=F2_MEDIA_LAB_MAX_BYTES=10737418240
Environment=F2_MEDIA_LAB_LOW_WATER_BYTES=8589934592
Environment=F2_MEDIA_LAB_MAX_AGE_HOURS=72
ExecStart=$BIN_DIR/f2-media gc --aggressive
EOF

cat > "$SYSTEMD_USER_DIR/frankenstein2-media-lab-gc.timer" <<'EOF'
[Unit]
Description=Run Frankenstein 2 multimodal media GC every 15 minutes

[Timer]
OnBootSec=5m
OnUnitActiveSec=15m
AccuracySec=1m
Persistent=true

[Install]
WantedBy=timers.target
EOF

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || true
  systemctl --user enable --now frankenstein2-media-lab-gc.timer || true
fi

"$BIN_DIR/f2-media" gc --aggressive
"$BIN_DIR/f2-media" status

cat <<EOF

F2 VPS multimodal lab ready.
CLI: $BIN_DIR/f2-media
Store: $STORE_ROOT
Hard cap: 10 GiB
Low-water target: 8 GiB
Default age GC: 72 h
Janitor: every 15 min when user systemd is available

Examples:
  f2-media fetch 'https://host/path/test.webm'
  f2-media fetch-ytdlp 'https://public-media-page/...'
  f2-media tone --frequency 997 --seconds 1
  f2-media speech 'Frankenstein, was siehst du?' --voice de
  f2-media generate image --size 1280x720
  f2-media generate video --seconds 5 --size 1280x720 --fps 24
  f2-media ingest /tmp/worker_generated_scene.mp4
EOF
