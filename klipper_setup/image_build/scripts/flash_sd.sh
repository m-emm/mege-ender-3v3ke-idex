#!/usr/bin/env bash
# Flash a pi-gen image to a removable disk on macOS.
#
# Usage:
#   ./flash_sd.sh <image.img|image.img.xz|image.zip> </dev/diskN>
#   ./flash_sd.sh </dev/diskN>              # auto-picks newest image from image_build/out
#
# Notes:
# - If image_build/out/latest exists, it is preferred.
# - Set DRY_RUN=1 to print what would happen without writing anything.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_BUILD_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${IMAGE_BUILD_DIR}/out"

IMG_PATH="${1:-}"
DISK_DEV="${2:-}"

resolve_latest_image() {
  local latest=""
  if [ -e "${OUT_DIR}/latest" ]; then
    latest="${OUT_DIR}/latest"
  else
    # Prefer common pi-gen artifacts. Ignore errors when glob doesn't match.
    latest="$(ls -1t "${OUT_DIR}"/*.img.xz "${OUT_DIR}"/*.img "${OUT_DIR}"/*.zip 2>/dev/null | head -n 1 || true)"
  fi

  if [ -z "${latest}" ]; then
    echo "No image found in ${OUT_DIR}. Build an image first (./scripts/build_image.sh)." >&2
    exit 1
  fi

  echo "${latest}"
}

bytes_of_file() {
  # macOS stat
  stat -f%z "$1" 2>/dev/null || echo ""
}

format_bytes() {
  local n="$1"
  if [ -z "${n}" ] || ! [[ "${n}" =~ ^[0-9]+$ ]]; then
    echo "unknown"
    return 0
  fi
  awk -v n="${n}" 'BEGIN {
    split("B KB MB GB TB", u, " ");
    v = n + 0.0;
    i = 1;
    while (v >= 1024 && i < 5) { v /= 1024; i++; }
    if (i >= 4) printf("%.1f%s", v, u[i]); else printf("%.0f%s", v, u[i]);
  }'
}

xz_uncompressed_bytes() {
  # Try to read uncompressed size without decompressing.
  # `xz -l --robot` outputs tab-separated rows; one row per file.
  # Column 5 is uncompressed size in bytes.
  local xz_path="$1"
  if ! command -v xz >/dev/null 2>&1; then
    echo ""
    return 0
  fi
  xz -l --robot "${xz_path}" 2>/dev/null | awk -F'\t' '$1=="file" {print $5; exit}'
}

zip_member_uncompressed_bytes() {
  local zip_path="$1"
  local member="$2"
  # `unzip -l` prints a table: Length  Date  Time  Name
  # For a specific member, match the row where the last column equals the member name.
  unzip -l "${zip_path}" "${member}" 2>/dev/null | awk -v m="${member}" '
    $1 ~ /^[0-9]+$/ && $4 == m {print $1; exit}
  '
}

# Allow calling as: ./flash_sd.sh /dev/diskN
if [ -n "${IMG_PATH}" ] && [ -z "${DISK_DEV}" ] && [[ "${IMG_PATH}" =~ ^/dev/disk[0-9]+$ ]]; then
  DISK_DEV="${IMG_PATH}"
  IMG_PATH=""
fi

if [ -z "${IMG_PATH}" ] && [ -n "${DISK_DEV}" ]; then
  IMG_PATH="$(resolve_latest_image)"
  echo "Using newest image: ${IMG_PATH}"
fi

if [ "${IMG_PATH}" = "latest" ]; then
  IMG_PATH="$(resolve_latest_image)"
  echo "Using newest image: ${IMG_PATH}"
fi

if [ -z "${IMG_PATH}" ] || [ -z "${DISK_DEV}" ]; then
  echo "Usage: $0 <image.img|image.img.xz|image.zip> </dev/diskN>" >&2
  echo "       $0 </dev/diskN>   # auto-pick newest from ${OUT_DIR}" >&2
  exit 1
fi

if [ ! -f "${IMG_PATH}" ]; then
  echo "Image not found: ${IMG_PATH}" >&2
  exit 1
fi

IMG_IN_ZIP=""
if [[ "${IMG_PATH}" == *.zip ]]; then
  if ! command -v unzip >/dev/null 2>&1; then
    echo "unzip not found but is required for .zip images." >&2
    exit 1
  fi
  IMG_IN_ZIP="$(unzip -Z1 "${IMG_PATH}" | grep -E '\.img\.xz$' | head -n 1 || true)"
  if [ -z "${IMG_IN_ZIP}" ]; then
    IMG_IN_ZIP="$(unzip -Z1 "${IMG_PATH}" | grep -E '\.img$' | head -n 1 || true)"
  fi
  if [ -z "${IMG_IN_ZIP}" ]; then
    echo "No .img/.img.xz found inside zip: ${IMG_PATH}" >&2
    exit 1
  fi
  if [[ "${IMG_IN_ZIP}" == *.xz ]] && ! command -v xz >/dev/null 2>&1; then
    echo "xz not found but is required to stream .img.xz from zip." >&2
    exit 1
  fi
fi

if [[ ! "${DISK_DEV}" =~ ^/dev/disk[0-9]+$ ]]; then
  echo "Disk must be like /dev/disk2" >&2
  exit 1
fi

if [ "${DISK_DEV}" = "/dev/disk0" ]; then
  echo "Refusing to flash the primary disk (/dev/disk0)." >&2
  exit 1
fi

if ! command -v diskutil >/dev/null 2>&1; then
  echo "diskutil not found (macOS only script)." >&2
  exit 1
fi

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "DRY_RUN=1 set; will not unmount or write." >&2
  echo "Would flash ${IMG_PATH} -> ${DISK_DEV/disk/rdisk}" >&2
  exit 0
fi

INFO="$(diskutil info "${DISK_DEV}" 2>/dev/null || true)"
if [ -z "${INFO}" ]; then
  echo "Disk ${DISK_DEV} not found." >&2
  exit 1
fi

field_value() {
  local key="$1"
  echo "${INFO}" | awk -F':' -v k="${key}" '
    index($0, k) > 0 {
      v=$2
      gsub(/^[[:space:]]+/, "", v)
      gsub(/[[:space:]]+$/, "", v)
      print v
      exit
    }'
}

REMOVABLE="$(field_value "Removable Media")"
EXTERNAL="$(field_value "Device Location")"

is_truthy_removable() {
  local v="$1"
  v="${v,,}"
  [[ "${v}" == removable* || "${v}" == yes* ]]
}

if ! is_truthy_removable "${REMOVABLE}"; then
  echo "Disk ${DISK_DEV} is not marked removable." >&2
  echo "Removable Media value: '${REMOVABLE}'" >&2
  exit 1
fi

if [ "${EXTERNAL}" != "External" ]; then
  echo "Disk ${DISK_DEV} is not External (value: ${EXTERNAL})." >&2
  exit 1
fi

echo "Unmounting ${DISK_DEV}"
diskutil unmountDisk "${DISK_DEV}"

RAW_DEV="${DISK_DEV/disk/rdisk}"

echo "Flashing ${IMG_PATH} -> ${RAW_DEV} (sudo dd ...)"
if [[ "${IMG_PATH}" == *.xz ]]; then
  TOTAL_BYTES="$(xz_uncompressed_bytes "${IMG_PATH}")"
  echo "Total to write: $(format_bytes "${TOTAL_BYTES}") (${TOTAL_BYTES:-unknown} bytes)"
  xz -dc "${IMG_PATH}" | sudo dd of="${RAW_DEV}" bs=4m status=progress
elif [[ "${IMG_PATH}" == *.zip ]]; then
  echo "Extracting from zip member: ${IMG_IN_ZIP}"
  if [[ "${IMG_IN_ZIP}" == *.xz ]]; then
    # The member is compressed; without extracting it we generally can't read the uncompressed size cheaply.
    echo "Total to write: unknown (zip member is compressed: ${IMG_IN_ZIP})"
    unzip -p "${IMG_PATH}" "${IMG_IN_ZIP}" | xz -dc | sudo dd of="${RAW_DEV}" bs=4m status=progress
  else
    TOTAL_BYTES="$(zip_member_uncompressed_bytes "${IMG_PATH}" "${IMG_IN_ZIP}")"
    echo "Total to write: $(format_bytes "${TOTAL_BYTES}") (${TOTAL_BYTES:-unknown} bytes)"
    unzip -p "${IMG_PATH}" "${IMG_IN_ZIP}" | sudo dd of="${RAW_DEV}" bs=4m status=progress
  fi
else
  TOTAL_BYTES="$(bytes_of_file "${IMG_PATH}")"
  echo "Total to write: $(format_bytes "${TOTAL_BYTES}") (${TOTAL_BYTES:-unknown} bytes)"
  sudo dd if="${IMG_PATH}" of="${RAW_DEV}" bs=4m status=progress
fi

sync
echo "Flash complete."

if [ "${VERIFY:-0}" = "1" ]; then
  echo "Verifying first 16MB..."
  if [[ "${IMG_PATH}" == *.xz ]]; then
    sudo xz -dc "${IMG_PATH}" | head -c $((16*1024*1024)) | \
      sudo dd if="${RAW_DEV}" bs=1m count=16 status=none | cmp -s - && \
      echo "Verify OK" || echo "Verify FAILED"
  elif [[ "${IMG_PATH}" == *.zip ]]; then
    if [[ "${IMG_IN_ZIP}" == *.xz ]]; then
      unzip -p "${IMG_PATH}" "${IMG_IN_ZIP}" | xz -dc | head -c $((16*1024*1024)) | \
        sudo dd if="${RAW_DEV}" bs=1m count=16 status=none | cmp -s - && \
        echo "Verify OK" || echo "Verify FAILED"
    else
      unzip -p "${IMG_PATH}" "${IMG_IN_ZIP}" | head -c $((16*1024*1024)) | \
        sudo dd if="${RAW_DEV}" bs=1m count=16 status=none | cmp -s - && \
        echo "Verify OK" || echo "Verify FAILED"
    fi
  else
    head -c $((16*1024*1024)) "${IMG_PATH}" | \
      sudo dd if="${RAW_DEV}" bs=1m count=16 status=none | cmp -s - && \
      echo "Verify OK" || echo "Verify FAILED"
  fi
fi
