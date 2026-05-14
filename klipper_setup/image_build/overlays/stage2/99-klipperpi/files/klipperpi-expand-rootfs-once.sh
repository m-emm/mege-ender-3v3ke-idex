#!/usr/bin/env bash
set -euo pipefail

MARKER_DIR="/var/lib/klipperpi"
MARKER="${MARKER_DIR}/rootfs-expanded"
ROOT_PART="$(findmnt -n -o SOURCE /)"

mkdir -p "${MARKER_DIR}"

if [ ! -b "${ROOT_PART}" ]; then
  echo "Root source is not a block device: ${ROOT_PART}" >&2
  touch "${MARKER}"
  exit 0
fi

ROOT_NAME="$(lsblk -no NAME "${ROOT_PART}" | head -n1)"
PARENT_NAME="$(lsblk -no PKNAME "${ROOT_PART}" | head -n1)"

if [ -z "${ROOT_NAME}" ] || [ -z "${PARENT_NAME}" ]; then
  echo "Could not determine root partition parent for ${ROOT_PART}" >&2
  touch "${MARKER}"
  exit 0
fi

DISK="/dev/${PARENT_NAME}"
PART_NUM="${ROOT_NAME##*[!0-9]}"

if [ ! -b "${DISK}" ] || [ -z "${PART_NUM}" ]; then
  echo "Could not determine disk/partition number for ${ROOT_PART}" >&2
  touch "${MARKER}"
  exit 0
fi

disk_bytes="$(blockdev --getsize64 "${DISK}")"
part_bytes="$(blockdev --getsize64 "${ROOT_PART}")"

if [ "${part_bytes}" -lt $((disk_bytes - 1024 * 1024 * 1024)) ]; then
  echo "Expanding ${ROOT_PART} to fill ${DISK}"
  if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_expand_rootfs || true
  else
    printf 'd\n%s\nn\np\n%s\n\n\nw\n' "${PART_NUM}" "${PART_NUM}" | fdisk "${DISK}"
  fi
  partprobe "${DISK}" 2>/dev/null || true
  sleep 2
fi

echo "Growing ext4 filesystem on ${ROOT_PART}"
if resize2fs "${ROOT_PART}"; then
  touch "${MARKER}"
else
  echo "resize2fs failed; rebooting so the kernel can re-read the partition table" >&2
  systemctl reboot
fi
