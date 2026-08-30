#!/usr/bin/env bash
set -Eeuo pipefail

# One-time guarded preparation for a reusable, read-only-by-convention Ubuntu 24.04
# base root. Tests never execute directly in this base; run_ubuntu_sandbox.sh copies it
# into a disposable per-run root first.

base_parent="/var/lib/frankenstein2-sandbox-images"
base_root="$base_parent/ubuntu-24.04-base"
marker="$base_root/.f2-sandbox-base.json"
mirror="${F2_UBUNTU_MIRROR:-http://archive.ubuntu.com/ubuntu}"
suite="${F2_UBUNTU_SUITE:-noble}"

if [[ "$suite" != "noble" ]]; then
  echo "refusing unreviewed Ubuntu suite: $suite" >&2
  exit 50
fi

case "$base_root" in
  /var/lib/frankenstein2-sandbox-images/ubuntu-24.04-base) ;;
  *) echo "internal safety error: unexpected base root" >&2; exit 51 ;;
esac

if [[ "$EUID" -eq 0 ]]; then
  root=()
else
  command -v sudo >/dev/null 2>&1 || { echo "sudo required" >&2; exit 52; }
  sudo -n true >/dev/null 2>&1 || { echo "passwordless sudo/root required" >&2; exit 53; }
  root=(sudo -n)
fi

source /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) echo "unsupported host distro for automatic preparation: ${ID:-unknown}" >&2; exit 54 ;; esac

"${root[@]}" mkdir -p -- "$base_parent"

exec 9>"/var/tmp/f2-sandbox-provision.lock"
flock -x 9

if [[ -f "$marker" ]]; then
  if "${root[@]}" grep -q '"suite":"noble"' "$marker"; then
    echo "F2_NSPAWN_PREPARE=ALREADY_READY base_root=$base_root"
    exit 0
  fi
  echo "existing base marker is not recognized; refusing destructive replacement" >&2
  exit 55
fi

if ! command -v debootstrap >/dev/null 2>&1 || ! command -v systemd-nspawn >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  "${root[@]}" apt-get update
  "${root[@]}" apt-get install -y --no-install-recommends debootstrap systemd-container ca-certificates
fi

command -v debootstrap >/dev/null 2>&1 || { echo "debootstrap unavailable after preparation" >&2; exit 56; }
command -v systemd-nspawn >/dev/null 2>&1 || { echo "systemd-nspawn unavailable after preparation" >&2; exit 57; }

tmp="$base_parent/.ubuntu-24.04-base.tmp.$$"
case "$tmp" in "$base_parent"/.ubuntu-24.04-base.tmp.*) ;; *) exit 58 ;; esac

cleanup_tmp() {
  if [[ -d "$tmp" ]]; then
    "${root[@]}" rm -rf --one-file-system -- "$tmp"
  fi
}
trap cleanup_tmp EXIT

"${root[@]}" mkdir -p -- "$tmp"
"${root[@]}" debootstrap \
  --variant=minbase \
  --include=systemd,systemd-sysv,dbus,python3,ca-certificates,curl,git,procps,iproute2,iputils-ping,util-linux \
  "$suite" "$tmp" "$mirror"

# Freeze package identity for evidence and make the base unmistakably non-test state.
"${root[@]}" sh -c "printf '%s\n' '{\"schema\":\"F2_VPS_SANDBOX_BASE/v1\",\"suite\":\"noble\",\"ubuntu\":\"24.04\",\"test_root\":false}' > '$tmp/.f2-sandbox-base.json'"
"${root[@]}" chmod 0444 "$tmp/.f2-sandbox-base.json"

if [[ -e "$base_root" ]]; then
  echo "base root appeared concurrently; refusing replacement" >&2
  exit 59
fi
"${root[@]}" mv -- "$tmp" "$base_root"
trap - EXIT

# Smoke the immutable-by-convention base read-only from the host. Do not execute a
# destructive test in it; the runtime script always clones it first.
"${root[@]}" test -f "$marker"
"${root[@]}" grep -q '^NAME="Ubuntu"' "$base_root/etc/os-release"

printf '%s\n' \
  "F2_NSPAWN_PREPARE=PASS" \
  "base_root=$base_root" \
  "suite=$suite" \
  "ubuntu=24.04" \
  "test_execution_in_base=FORBIDDEN" \
  "disposable_clone_required=true"
