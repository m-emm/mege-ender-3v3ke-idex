#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
FILES_DIR="${REPO_ROOT}/klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
CROWSNEST_COMMIT="${CROWSNEST_COMMIT:-f92045ac36ab42c9d3770251dcffbaabc6e1fdf2}"
CAMERA_DEVICE="${VISION_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0}"

required_files=(
  crowsnest.conf
  moonraker.conf
  nginx-mainsail.conf
  vision_capture.py
  vision_runner.py
  vision-capture.service
)

for file in "${required_files[@]}"; do
  if [[ ! -f "${FILES_DIR}/${file}" ]]; then
    echo "Missing required file: ${FILES_DIR}/${file}" >&2
    exit 1
  fi
done

echo "Checking camera on ${REMOTE_HOST}: ${CAMERA_DEVICE}"
ssh "${REMOTE_HOST}" "CAMERA_DEVICE='${CAMERA_DEVICE}' bash -s" <<'REMOTE_CHECK'
set -euo pipefail
if [[ ! -e "${CAMERA_DEVICE}" ]]; then
  echo "Camera device not found: ${CAMERA_DEVICE}" >&2
  echo "Available camera paths:" >&2
  ls -l /dev/video* /dev/v4l/by-id/* /dev/v4l/by-path/* 2>/dev/null >&2 || true
  exit 1
fi
REMOTE_CHECK

remote_tmp="$(ssh "${REMOTE_HOST}" "mktemp -d /tmp/webcam-vision.XXXXXX")"
cleanup() {
  ssh "${REMOTE_HOST}" "rm -rf '${remote_tmp}'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp \
  "${FILES_DIR}/crowsnest.conf" \
  "${FILES_DIR}/moonraker.conf" \
  "${FILES_DIR}/nginx-mainsail.conf" \
  "${FILES_DIR}/vision_capture.py" \
  "${FILES_DIR}/vision_runner.py" \
  "${FILES_DIR}/vision-capture.service" \
  "${REMOTE_HOST}:${remote_tmp}/"

ssh "${REMOTE_HOST}" \
  "REMOTE_TMP='${remote_tmp}' CROWSNEST_COMMIT='${CROWSNEST_COMMIT}' CAMERA_DEVICE='${CAMERA_DEVICE}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

USERNAME="$(id -un)"
USER_HOME="${HOME}"
PRINTER_DATA="${USER_HOME}/printer_data"
CONFIG_DIR="${PRINTER_DATA}/config"
LOG_DIR="${PRINTER_DATA}/logs"
VISION_DIR="${PRINTER_DATA}/vision"
TS="$(date +%Y%m%d-%H%M%S)"

backup_if_exists() {
  local path="$1"
  if [[ -e "${path}" || -L "${path}" ]]; then
    sudo cp -a "${path}" "${path}.bak.${TS}"
  fi
}

echo "Installing webcam and vision-capture dependencies..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  acl \
  ca-certificates \
  curl \
  git \
  sudo \
  crudini \
  python3 \
  python3-venv \
  v4l-utils \
  build-essential \
  libevent-dev \
  libjpeg-dev \
  libbsd-dev \
  pkg-config

echo "Installing/updating Crowsnest at ${CROWSNEST_COMMIT}..."
if [[ ! -d /opt/crowsnest/.git ]]; then
  sudo rm -rf /opt/crowsnest
  sudo git clone https://github.com/mainsail-crew/crowsnest.git /opt/crowsnest
  sudo chown -R "${USERNAME}:${USERNAME}" /opt/crowsnest
fi
sudo -u "${USERNAME}" git -C /opt/crowsnest fetch --tags origin
sudo -u "${USERNAME}" git -C /opt/crowsnest checkout -f "${CROWSNEST_COMMIT}"
sudo chown -R "${USERNAME}:${USERNAME}" /opt/crowsnest

if [[ ! -f /etc/systemd/system/crowsnest.service ]] || \
   [[ ! -d "${USER_HOME}/crowsnest-env" ]] || \
   { [[ ! -x /opt/crowsnest/bin/ustreamer/ustreamer ]] && ! command -v ustreamer >/dev/null 2>&1; }; then
  echo "Running Crowsnest unattended installer..."
  sudo env \
    SUDO_USER="${USERNAME}" \
    BASE_USER="${USERNAME}" \
    CROWSNEST_UNATTENDED=1 \
    CROWSNEST_ADD_CROWSNEST_MOONRAKER=0 \
    CROWSNEST_SKIP_REBOOT_PROMPT=1 \
    make -C /opt/crowsnest install
fi
sudo ln -sfn /opt/crowsnest "${USER_HOME}/crowsnest"
sudo chown -h "${USERNAME}:${USERNAME}" "${USER_HOME}/crowsnest"

echo "Installing tracked configs and services..."
sudo install -d -m 0755 -o "${USERNAME}" -g "${USERNAME}" \
  "${CONFIG_DIR}" "${LOG_DIR}" "${PRINTER_DATA}/systemd" "${VISION_DIR}"
sudo setfacl -m u:www-data:--x "${USER_HOME}"

backup_if_exists "${CONFIG_DIR}/crowsnest.conf"
backup_if_exists "${CONFIG_DIR}/moonraker.conf"
backup_if_exists /etc/nginx/sites-available/mainsail
backup_if_exists /etc/systemd/system/vision-capture.service

sudo install -m 0644 "${REMOTE_TMP}/crowsnest.conf" "${CONFIG_DIR}/crowsnest.conf"
sudo install -m 0644 "${REMOTE_TMP}/moonraker.conf" "${CONFIG_DIR}/moonraker.conf"
sudo chown "${USERNAME}:${USERNAME}" \
  "${CONFIG_DIR}/crowsnest.conf" \
  "${CONFIG_DIR}/moonraker.conf"

sudo install -m 0644 "${REMOTE_TMP}/nginx-mainsail.conf" /etc/nginx/sites-available/mainsail
sudo ln -sf /etc/nginx/sites-available/mainsail /etc/nginx/sites-enabled/mainsail
sudo rm -f /etc/nginx/sites-enabled/default

sudo install -m 0755 "${REMOTE_TMP}/vision_capture.py" /usr/local/bin/vision_capture.py
sudo install -m 0755 "${REMOTE_TMP}/vision_runner.py" /usr/local/bin/vision_runner.py
sudo install -m 0644 "${REMOTE_TMP}/vision-capture.service" /etc/systemd/system/vision-capture.service
sudo usermod -a -G video "${USERNAME}" || true

echo "Restarting services..."
sudo systemctl daemon-reload
sudo systemctl enable nginx moonraker crowsnest vision-capture
sudo systemctl restart nginx
sudo systemctl restart moonraker
sudo systemctl restart crowsnest
sudo systemctl restart vision-capture

echo "Service state:"
systemctl --no-pager --full status crowsnest vision-capture nginx moonraker | sed -n '1,120p'

echo "Camera device:"
ls -l "${CAMERA_DEVICE}"
REMOTE_SCRIPT

echo "Webcam and vision-capture deployment complete."
