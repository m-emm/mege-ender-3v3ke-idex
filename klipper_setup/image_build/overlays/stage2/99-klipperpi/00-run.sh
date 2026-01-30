#!/bin/bash -e
# Host-side: copy overlay files (including secrets injected by render_overlay) into the target rootfs.

STAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
FILES_DIR="${STAGE_DIR}/files"
TARGET_DIR="${ROOTFS_DIR}/opt/klipperpi-files"

echo "Copying klipperpi files into rootfs (${TARGET_DIR})"
rm -rf "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
cp -a "${FILES_DIR}/." "${TARGET_DIR}/"

# Ensure authorized_keys has safe perms; final ownership set in chroot.
if [ -f "${TARGET_DIR}/authorized_keys" ]; then
  chmod 600 "${TARGET_DIR}/authorized_keys"
fi

exit 0
