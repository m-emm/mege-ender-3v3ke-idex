#!/usr/bin/env bash
# Prepare the pi-gen tree with our klipper overlay and config derived from secrets/build.env.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_BUILD_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OVERLAY_SRC="${IMAGE_BUILD_DIR}/overlays/stage2/99-klipperpi"
PIGEN_DIR="${IMAGE_BUILD_DIR}/pi-gen"
SECRETS_DIR="${IMAGE_BUILD_DIR}/secrets"
OUT_CONFIG="${PIGEN_DIR}/config"

BUILD_ENV_SRC="${SECRETS_DIR}/build.env"
AUTHORIZED_KEYS_SRC="${SECRETS_DIR}/authorized_keys"

if [ ! -d "${PIGEN_DIR}" ]; then
  echo "pi-gen not found at ${PIGEN_DIR}. Bootstrapping local clone." >&2
  "${SCRIPT_DIR}/setup_pigen_submodule.sh" >&2
fi

if [ ! -d "${PIGEN_DIR}" ]; then
  echo "pi-gen still not found at ${PIGEN_DIR}." >&2
  exit 1
fi

if [ ! -f "${BUILD_ENV_SRC}" ]; then
  echo "Missing ${BUILD_ENV_SRC}. Please create it from the template in the concept doc." >&2
  exit 1
fi

if [ ! -f "${AUTHORIZED_KEYS_SRC}" ]; then
  echo "Missing ${AUTHORIZED_KEYS_SRC}. Put your SSH public key there." >&2
  exit 1
fi

echo "Loading build parameters from secrets/build.env"
set -a
source "${BUILD_ENV_SRC}"
set +a

if [ -z "${IMG_NAME:-}" ] || [ -z "${RELEASE:-}" ] || [ -z "${HOSTNAME:-}" ] || [ -z "${USERNAME:-}" ]; then
  echo "build.env must define IMG_NAME, RELEASE, HOSTNAME, USERNAME" >&2
  exit 1
fi

echo "Refreshing overlay into pi-gen/stage2/99-klipperpi"
rsync -a --delete "${OVERLAY_SRC}/" "${PIGEN_DIR}/stage2/99-klipperpi/"

echo "Injecting secrets (authorized_keys, build.env) into overlay files/"
cp "${AUTHORIZED_KEYS_SRC}" "${PIGEN_DIR}/stage2/99-klipperpi/files/authorized_keys"
cp "${BUILD_ENV_SRC}" "${PIGEN_DIR}/stage2/99-klipperpi/files/build.env"

echo "Rendering pi-gen config at ${OUT_CONFIG}"
cat > "${OUT_CONFIG}" <<EOF
IMG_NAME=${IMG_NAME}
RELEASE=${RELEASE}
ENABLE_SSH=1
TARGET_HOSTNAME=${HOSTNAME}
FIRST_USER_NAME=${USERNAME}
FIRST_USER_PASS=raspberry
LOCALE_DEFAULT=${LOCALE:-en_GB.UTF-8}
KEYMAP=${KEYMAP:-us}
TIMEZONE_DEFAULT=${TIMEZONE:-Europe/London}
STAGE_LIST="${STAGE_LIST:-stage0 stage1 stage2}"
EOF

echo "Overlay prepared."
