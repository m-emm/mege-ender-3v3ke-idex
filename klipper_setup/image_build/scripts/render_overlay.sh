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

# pi-gen arm64 currently ships a Debian sources file that references
# /usr/share/keyrings/debian-archive-keyring.pgp. On modern Debian/Bookworm images
# the keyring file is typically .gpg, and apt will fail with NO_PUBKEY if the
# referenced keyring path doesn't exist.
DEBIAN_SOURCES_FILE="${PIGEN_DIR}/stage0/00-configure-apt/files/debian.sources"
if [ -f "${DEBIAN_SOURCES_FILE}" ] && grep -q "debian-archive-keyring\.pgp" "${DEBIAN_SOURCES_FILE}"; then
  echo "Patching pi-gen debian.sources Signed-By to use debian-archive-keyring.gpg"
  perl -pi -e 's/debian-archive-keyring\.pgp/debian-archive-keyring.gpg/g' "${DEBIAN_SOURCES_FILE}"
fi

# Some Raspberry Pi OS meta-packages have been removed/renamed over time. When they
# disappear, pi-gen fails hard with "Unable to locate package". We don't rely on
# them for this Klipper image, so strip them from the upstream package list.
STAGE2_SYS_TWEAKS_PACKAGES_FILE="${PIGEN_DIR}/stage2/01-sys-tweaks/00-packages"
if [ -f "${STAGE2_SYS_TWEAKS_PACKAGES_FILE}" ]; then
  if grep -Eq '\brpi-swap\b|\brpi-loop-utils\b|\brpi-usb-gadget\b' "${STAGE2_SYS_TWEAKS_PACKAGES_FILE}"; then
    echo "Removing unavailable packages from pi-gen stage2 sys-tweaks package list"
    perl -pi -e 's/\brpi-swap\b//g; s/\brpi-loop-utils\b//g; s/\brpi-usb-gadget\b//g; s/[ \t]{2,}/ /g; s/^[ \t]+//g; s/[ \t]+$//g' "${STAGE2_SYS_TWEAKS_PACKAGES_FILE}"
  fi
fi

STAGE2_SYS_TWEAKS_RUN_FILE="${PIGEN_DIR}/stage2/01-sys-tweaks/01-run.sh"
if [ -f "${STAGE2_SYS_TWEAKS_RUN_FILE}" ]; then
  if grep -q "systemctl enable rpi-resize" "${STAGE2_SYS_TWEAKS_RUN_FILE}" && ! grep -q "rpi-resize\.service not present" "${STAGE2_SYS_TWEAKS_RUN_FILE}"; then
    echo "Patching pi-gen stage2 sys-tweaks to skip missing rpi-resize.service"
    perl -0777 -pi -e 's/\n(\s*)systemctl enable rpi-resize\n/\n$1if [ -f \/lib\/systemd\/system\/rpi-resize.service ] || [ -f \/etc\/systemd\/system\/rpi-resize.service ]; then\n$1  systemctl enable rpi-resize\n$1else\n$1  echo "rpi-resize.service not present; skipping"\n$1fi\n/sm' "${STAGE2_SYS_TWEAKS_RUN_FILE}"
  fi
fi

# Cloud-init isn't needed for this image, and the Raspberry Pi OS package providing
# pi-gen's cloud-init modifications has disappeared in newer repos.
CLOUD_INIT_STAGE_DIR="${PIGEN_DIR}/stage2/04-cloud-init"
if [ -d "${CLOUD_INIT_STAGE_DIR}" ] && [ ! -f "${CLOUD_INIT_STAGE_DIR}/SKIP" ]; then
  echo "Skipping pi-gen stage2/04-cloud-init"
  touch "${CLOUD_INIT_STAGE_DIR}/SKIP"
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
