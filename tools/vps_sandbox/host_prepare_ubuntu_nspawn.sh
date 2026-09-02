#!/usr/bin/env bash
set -Eeuo pipefail

# One-time guarded preparation for a reusable, read-only-by-convention Ubuntu 24.04
# base root. Tests never execute directly in this base; run_ubuntu_sandbox.sh copies it
# into a disposable per-run root first.
#
# v2 exists specifically to prevent a historical/minimal noble rootfs from being
# accepted merely because its marker names the right suite. A reusable base is
# READY only when both marker identity and required executable capabilities agree.

base_parent="/var/lib/frankenstein2-sandbox-images"
default_base_root="$base_parent/ubuntu-24.04-base-v2"
base_root="$(readlink -m -- "${F2_NSPAWN_BASE_ROOT:-$default_base_root}")"
marker="$base_root/.f2-sandbox-base.json"
mirror="${F2_UBUNTU_MIRROR:-http://archive.ubuntu.com/ubuntu}"
suite="${F2_UBUNTU_SUITE:-noble}"
base_schema="F2_VPS_SANDBOX_BASE/v2"

if [[ "$suite" != "noble" ]]; then
  echo "refusing unreviewed Ubuntu suite: $suite" >&2
  exit 50
fi

case "$base_root" in
  /var/lib/frankenstein2-sandbox-images/ubuntu-24.04-base-v2) ;;
  *) echo "refusing unapproved nspawn base root: $base_root" >&2; exit 51 ;;
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

base_capabilities_ready() {
  [[ -f "$marker" ]] || return 1
  "${root[@]}" grep -q '"schema":"F2_VPS_SANDBOX_BASE/v2"' "$marker" || return 1
  "${root[@]}" grep -q '"suite":"noble"' "$marker" || return 1
  "${root[@]}" test -x "$base_root/usr/bin/python3" || return 1
  "${root[@]}" test -x "$base_root/usr/bin/git" || return 1
  "${root[@]}" test -x "$base_root/usr/bin/curl" || return 1
  "${root[@]}" test -x "$base_root/bin/bash" || "${root[@]}" test -x "$base_root/usr/bin/bash" || return 1
}

if [[ -e "$base_root" ]]; then
  if base_capabilities_ready; then
    printf '%s\n' \
      "F2_NSPAWN_PREPARE=ALREADY_READY" \
      "base_root=$base_root" \
      "base_schema=$base_schema" \
      "required_capabilities=python3,git,curl,bash"
    exit 0
  fi
  echo "existing v2 base is incomplete or marker/capabilities disagree; refusing destructive replacement: $base_root" >&2
  exit 55
fi

if ! command -v debootstrap >/dev/null 2>&1 || ! command -v systemd-nspawn >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  "${root[@]}" apt-get update
  "${root[@]}" apt-get install -y --no-install-recommends debootstrap systemd-container ca-certificates
fi

command -v debootstrap >/dev/null 2>&1 || { echo "debootstrap unavailable after preparation" >&2; exit 56; }
command -v systemd-nspawn >/dev/null 2>&1 || { echo "systemd-nspawn unavailable after preparation" >&2; exit 57; }

tmp="$base_parent/.ubuntu-24.04-base-v2.tmp.$$"
case "$tmp" in "$base_parent"/.ubuntu-24.04-base-v2.tmp.*) ;; *) exit 58 ;; esac

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

# Prove the capabilities before publishing the immutable-by-convention base.
"${root[@]}" test -x "$tmp/usr/bin/python3"
"${root[@]}" test -x "$tmp/usr/bin/git"
"${root[@]}" test -x "$tmp/usr/bin/curl"
if ! "${root[@]}" test -x "$tmp/bin/bash" && ! "${root[@]}" test -x "$tmp/usr/bin/bash"; then
  echo "prepared base missing bash" >&2
  exit 60
fi

"${root[@]}" sh -c "printf '%s\n' '{\"schema\":\"F2_VPS_SANDBOX_BASE/v2\",\"suite\":\"noble\",\"ubuntu\":\"24.04\",\"test_root\":false,\"capabilities\":[\"python3\",\"git\",\"curl\",\"bash\"]}' > '$tmp/.f2-sandbox-base.json'"
"${root[@]}" chmod 0444 "$tmp/.f2-sandbox-base.json"

if [[ -e "$base_root" ]]; then
  echo "base root appeared concurrently; refusing replacement" >&2
  exit 59
fi
"${root[@]}" mv -- "$tmp" "$base_root"
trap - EXIT

# Validate the published base without mutating it.
base_capabilities_ready || { echo "published v2 base failed capability validation" >&2; exit 61; }
"${root[@]}" grep -q '^NAME="Ubuntu"' "$base_root/etc/os-release"

printf '%s\n' \
  "F2_NSPAWN_PREPARE=PASS" \
  "base_root=$base_root" \
  "base_schema=$base_schema" \
  "suite=$suite" \
  "ubuntu=24.04" \
  "required_capabilities=python3,git,curl,bash" \
  "test_execution_in_base=FORBIDDEN" \
  "disposable_clone_required=true"
