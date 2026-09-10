#!/bin/bash -e
# Host-side: copy the rendered image payload into the target rootfs.

STAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
FILES_DIR="${STAGE_DIR}/files"
KLIPPER_HOST_DIR="${STAGE_DIR}/../../../../klipper_host"
TARGET_DIR="${ROOTFS_DIR}/opt/klipperpi-files"

echo "Copying klipperpi files into rootfs (${TARGET_DIR})"
rm -rf "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
cp -a "${FILES_DIR}/." "${TARGET_DIR}/"

if [ -d "${KLIPPER_HOST_DIR}" ]; then
  mkdir -p "${TARGET_DIR}/klipper_host"
  cp -a "${KLIPPER_HOST_DIR}/." "${TARGET_DIR}/klipper_host/"
fi

KLIPPER_COMMIT_FILE="${STAGE_DIR}/../../../../KLIPPER_COMMIT"
if [ ! -f "${KLIPPER_COMMIT_FILE}" ]; then
  echo "Missing shared Klipper commit file: ${KLIPPER_COMMIT_FILE}" >&2
  exit 1
fi
install -m 0644 "${KLIPPER_COMMIT_FILE}" "${TARGET_DIR}/KLIPPER_COMMIT"

# Ensure authorized_keys has safe perms; final ownership set in chroot.
if [ -f "${TARGET_DIR}/authorized_keys" ]; then
  chmod 600 "${TARGET_DIR}/authorized_keys"
fi

exit 0
