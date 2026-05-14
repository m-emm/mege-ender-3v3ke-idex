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
DEFAULT_WIFI_ENV_SRC="${HOME:-}/.config/klipperpi-idex/wifi.env"
WIFI_ENV_SRC="${WIFI_ENV_SRC:-}"

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

if [ -z "${WIFI_ENV_SRC}" ]; then
  if [ -f "${SECRETS_DIR}/wifi.env" ]; then
    WIFI_ENV_SRC="${SECRETS_DIR}/wifi.env"
  elif [ -n "${DEFAULT_WIFI_ENV_SRC}" ] && [ -f "${DEFAULT_WIFI_ENV_SRC}" ]; then
    WIFI_ENV_SRC="${DEFAULT_WIFI_ENV_SRC}"
  fi
fi

echo "Refreshing overlay into pi-gen/stage2/99-klipperpi"
rsync -a --delete "${OVERLAY_SRC}/" "${PIGEN_DIR}/stage2/99-klipperpi/"

echo "Injecting secrets (authorized_keys, build.env) into overlay files/"
cp "${AUTHORIZED_KEYS_SRC}" "${PIGEN_DIR}/stage2/99-klipperpi/files/authorized_keys"
cp "${BUILD_ENV_SRC}" "${PIGEN_DIR}/stage2/99-klipperpi/files/build.env"

if [ -n "${WIFI_ENV_SRC}" ]; then
  if [ ! -f "${WIFI_ENV_SRC}" ]; then
    echo "WIFI_ENV_SRC points to a missing file: ${WIFI_ENV_SRC}" >&2
    exit 1
  fi

  echo "Rendering NetworkManager WiFi profile from ${WIFI_ENV_SRC}"
  set -a
  # shellcheck disable=SC1090
  source "${WIFI_ENV_SRC}"
  set +a

  WIFI_PROFILE_SSIDS=()
  if declare -p WIFI_SSIDS >/dev/null 2>&1; then
    eval 'WIFI_PROFILE_SSIDS=("${WIFI_SSIDS[@]}")'
  elif [ -n "${WIFI_SSID:-}" ]; then
    WIFI_PROFILE_SSIDS=("${WIFI_SSID}")
  fi

  if [ "${#WIFI_PROFILE_SSIDS[@]}" -eq 0 ] || [ -z "${WIFI_PASSWORD:-}" ]; then
    echo "${WIFI_ENV_SRC} must define WIFI_SSID or WIFI_SSIDS, plus WIFI_PASSWORD" >&2
    exit 1
  fi

  if [[ "${WIFI_PASSWORD}${WIFI_IFACE:-}" == *$'\n'* ]] || \
     [[ "${WIFI_PASSWORD}${WIFI_IFACE:-}" == *$'\r'* ]]; then
    echo "WiFi values must not contain newline characters" >&2
    exit 1
  fi

  rm -f \
    "${PIGEN_DIR}/stage2/99-klipperpi/files/klipperpi-wifi.nmconnection" \
    "${PIGEN_DIR}/stage2/99-klipperpi/files"/klipperpi-wifi-*.nmconnection

  WIFI_INDEX=0
  for WIFI_PROFILE_SSID in "${WIFI_PROFILE_SSIDS[@]}"; do
    WIFI_INDEX=$((WIFI_INDEX + 1))

    if [ -z "${WIFI_PROFILE_SSID}" ] || [[ "${WIFI_PROFILE_SSID}" == *$'\n'* ]] || \
       [[ "${WIFI_PROFILE_SSID}" == *$'\r'* ]]; then
      echo "WiFi SSIDs must be non-empty and must not contain newline characters" >&2
      exit 1
    fi

    WIFI_UUID="$(uuidgen | tr 'A-Z' 'a-z')"
    WIFI_SAFE_NAME="$(printf '%s' "${WIFI_PROFILE_SSID}" | tr -cs 'A-Za-z0-9_.-' '-' | sed -E 's/^-+//; s/-+$//')"
    if [ -z "${WIFI_SAFE_NAME}" ]; then
      WIFI_SAFE_NAME="network-${WIFI_INDEX}"
    fi

    WIFI_PROFILE="${PIGEN_DIR}/stage2/99-klipperpi/files/klipperpi-wifi-${WIFI_INDEX}-${WIFI_SAFE_NAME}.nmconnection"
    cat > "${WIFI_PROFILE}" <<EOF
[connection]
id=klipperpi-wifi-${WIFI_SAFE_NAME}
uuid=${WIFI_UUID}
type=wifi
autoconnect-priority=80
interface-name=${WIFI_IFACE:-wlan1}

[wifi]
mode=infrastructure
ssid=${WIFI_PROFILE_SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${WIFI_PASSWORD}

[ipv4]
method=auto

[ipv6]
addr-gen-mode=default
method=auto

[proxy]
EOF
    chmod 0600 "${WIFI_PROFILE}"
  done
fi

echo "Rendering pi-gen config at ${OUT_CONFIG}"
cat > "${OUT_CONFIG}" <<EOF
IMG_NAME=${IMG_NAME}
RELEASE=${RELEASE}
ENABLE_SSH=1
DISABLE_FIRST_BOOT_USER_RENAME=1
TARGET_HOSTNAME=${HOSTNAME}
FIRST_USER_NAME=${USERNAME}
FIRST_USER_PASS=raspberry
LOCALE_DEFAULT=${LOCALE:-en_GB.UTF-8}
KEYMAP=${KEYMAP:-us}
TIMEZONE_DEFAULT=${TIMEZONE:-Europe/London}
STAGE_LIST="${STAGE_LIST:-stage0 stage1 stage2}"
EOF

echo "Overlay prepared."
