#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
FILES_DIR="${REPO_ROOT}/klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
PRIMARY_CAMERA_DEVICE="${VISION_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0}"
NOZZLE_CAMERA_DEVICE="${NOZZLE_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Vimicro_corp._PC-LM1E_Camera_PC-LM1E_Audio-video-index0}"

required_files=(
  moonraker.conf
  nginx-mainsail.conf
  vision_framebuffer.py
  vision_capture.py
  vision_nozzle_align.py
  vision_runner.py
  webcam_health_probe.py
  vision-framebuffer.service
  vision-framebuffer-nozzle-cam.service
  vision-capture.service
  vision-capture-nozzle-cam.service
)

for file in "${required_files[@]}"; do
  if [[ ! -f "${FILES_DIR}/${file}" ]]; then
    echo "Missing required file: ${FILES_DIR}/${file}" >&2
    exit 1
  fi
done

echo "Checking cameras on ${REMOTE_HOST}:"
echo "  primary: ${PRIMARY_CAMERA_DEVICE}"
echo "  nozzle_cam: ${NOZZLE_CAMERA_DEVICE}"
ssh "${REMOTE_HOST}" \
  "PRIMARY_CAMERA_DEVICE='${PRIMARY_CAMERA_DEVICE}' NOZZLE_CAMERA_DEVICE='${NOZZLE_CAMERA_DEVICE}' bash -s" <<'REMOTE_CHECK'
set -euo pipefail
missing=0
for pair in "primary:${PRIMARY_CAMERA_DEVICE}" "nozzle_cam:${NOZZLE_CAMERA_DEVICE}"; do
  name="${pair%%:*}"
  path="${pair#*:}"
  if [[ ! -e "${path}" ]]; then
    echo "${name} camera device not found: ${path}" >&2
    missing=1
  fi
done
if [[ "${missing}" -ne 0 ]]; then
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
  "${FILES_DIR}/moonraker.conf" \
  "${FILES_DIR}/nginx-mainsail.conf" \
  "${FILES_DIR}/vision_framebuffer.py" \
  "${FILES_DIR}/vision_capture.py" \
  "${FILES_DIR}/vision_nozzle_align.py" \
  "${FILES_DIR}/vision_runner.py" \
  "${FILES_DIR}/webcam_health_probe.py" \
  "${FILES_DIR}/vision-framebuffer.service" \
  "${FILES_DIR}/vision-framebuffer-nozzle-cam.service" \
  "${FILES_DIR}/vision-capture.service" \
  "${FILES_DIR}/vision-capture-nozzle-cam.service" \
  "${REMOTE_HOST}:${remote_tmp}/"

ssh "${REMOTE_HOST}" \
  "REMOTE_TMP='${remote_tmp}' PRIMARY_CAMERA_DEVICE='${PRIMARY_CAMERA_DEVICE}' NOZZLE_CAMERA_DEVICE='${NOZZLE_CAMERA_DEVICE}' bash -s" <<'REMOTE_SCRIPT'
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
  sudo \
  python3 \
  python3-opencv \
  v4l-utils

echo "Installing tracked configs and services..."
sudo install -d -m 0755 -o "${USERNAME}" -g "${USERNAME}" \
  "${CONFIG_DIR}" "${LOG_DIR}" "${PRINTER_DATA}/systemd" "${VISION_DIR}" "${VISION_DIR}/nozzle_cam"
sudo setfacl -m u:www-data:--x "${USER_HOME}"

backup_if_exists "${CONFIG_DIR}/crowsnest.conf"
backup_if_exists "${CONFIG_DIR}/moonraker.conf"
backup_if_exists /etc/nginx/sites-available/mainsail
backup_if_exists /etc/systemd/system/vision-framebuffer.service
backup_if_exists /etc/systemd/system/vision-framebuffer-nozzle-cam.service
backup_if_exists /etc/systemd/system/vision-capture.service
backup_if_exists /etc/systemd/system/vision-capture-nozzle-cam.service

sudo rm -f "${CONFIG_DIR}/crowsnest.conf"
sudo install -m 0644 "${REMOTE_TMP}/moonraker.conf" "${CONFIG_DIR}/moonraker.conf"
sudo chown "${USERNAME}:${USERNAME}" "${CONFIG_DIR}/moonraker.conf"

sudo install -m 0644 "${REMOTE_TMP}/nginx-mainsail.conf" /etc/nginx/sites-available/mainsail
sudo ln -sf /etc/nginx/sites-available/mainsail /etc/nginx/sites-enabled/mainsail
sudo rm -f /etc/nginx/sites-enabled/default

sudo install -m 0755 "${REMOTE_TMP}/vision_framebuffer.py" /usr/local/bin/vision_framebuffer.py
sudo install -m 0755 "${REMOTE_TMP}/vision_capture.py" /usr/local/bin/vision_capture.py
sudo install -m 0755 "${REMOTE_TMP}/vision_nozzle_align.py" /usr/local/bin/vision_nozzle_align.py
sudo install -m 0755 "${REMOTE_TMP}/vision_runner.py" /usr/local/bin/vision_runner.py
sudo install -m 0755 "${REMOTE_TMP}/webcam_health_probe.py" /usr/local/bin/webcam_health_probe.py
sudo install -m 0644 "${REMOTE_TMP}/vision-framebuffer.service" /etc/systemd/system/vision-framebuffer.service
sudo install -m 0644 "${REMOTE_TMP}/vision-framebuffer-nozzle-cam.service" /etc/systemd/system/vision-framebuffer-nozzle-cam.service
sudo install -m 0644 "${REMOTE_TMP}/vision-capture.service" /etc/systemd/system/vision-capture.service
sudo install -m 0644 "${REMOTE_TMP}/vision-capture-nozzle-cam.service" /etc/systemd/system/vision-capture-nozzle-cam.service
sudo usermod -a -G video "${USERNAME}" || true

echo "Restarting services..."
sudo systemctl daemon-reload
sudo systemctl enable nginx moonraker \
  vision-framebuffer vision-framebuffer-nozzle-cam \
  vision-capture vision-capture-nozzle-cam
sudo systemctl disable --now crowsnest || true
sudo systemctl restart nginx
sudo systemctl restart moonraker
sudo systemctl reset-failed crowsnest vision-framebuffer vision-framebuffer-nozzle-cam || true
sudo systemctl restart vision-framebuffer
sudo systemctl restart vision-framebuffer-nozzle-cam
sudo systemctl restart vision-capture
sudo systemctl restart vision-capture-nozzle-cam

echo "Waiting for RAM-buffered webcam endpoints..."
python3 - <<'PY'
import socket
import sys
import time
import urllib.request

targets = [
    ("Printer Camera", 8080, "http://127.0.0.1/webcam/?action=snapshot"),
    ("nozzle_cam", 8081, "http://127.0.0.1/nozzle_cam/?action=snapshot"),
]

for name, port, url in targets:
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass
            with urllib.request.urlopen(url, timeout=4) as response:
                data = response.read(4)
            if data[:2] == b"\xff\xd8":
                break
            last_error = "snapshot endpoint did not return JPEG data"
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    else:
        print(f"{name} endpoint did not become ready: {last_error}", file=sys.stderr)
        sys.exit(1)
PY

echo "Ensuring Moonraker database webcam registration..."
python3 - <<'PY'
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:7125"
TARGETS = [
    {
        "name": "Printer Camera",
        "enabled": "true",
        "icon": "mdiWebcam",
        "aspect_ratio": "16:9",
        "target_fps": "1",
        "target_fps_idle": "1",
        "location": "printer",
        "service": "mjpegstreamer",
        "stream_url": "/webcam/?action=stream",
        "snapshot_url": "/webcam/?action=snapshot",
        "flip_horizontal": "false",
        "flip_vertical": "false",
        "rotation": "0",
    },
    {
        "name": "nozzle_cam",
        "enabled": "true",
        "icon": "mdiWebcam",
        "aspect_ratio": "16:9",
        "target_fps": "1",
        "target_fps_idle": "1",
        "location": "printer",
        "service": "mjpegstreamer",
        "stream_url": "/nozzle_cam/?action=stream",
        "snapshot_url": "/nozzle_cam/?action=snapshot",
        "flip_horizontal": "false",
        "flip_vertical": "false",
        "rotation": "0",
    },
]


def request(method, path, fields=None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())


deadline = time.monotonic() + 30
last_error = None
while time.monotonic() < deadline:
    try:
        webcams = request("GET", "/server/webcams/list")["result"]["webcams"]
        break
    except Exception as exc:
        last_error = exc
        time.sleep(1)
else:
    print(f"Moonraker did not become ready for webcam registration: {last_error}", file=sys.stderr)
    sys.exit(1)

target_names = {target["name"] for target in TARGETS}
target_uids = {}
for webcam in webcams:
    uid = webcam.get("uid")
    source = webcam.get("source")
    name = webcam.get("name")
    if source == "database" and name in target_names and name not in target_uids:
        target_uids[name] = uid
    elif source == "database" and uid:
        request("DELETE", f"/server/webcams/item?uid={urllib.parse.quote(uid)}")

for target in TARGETS:
    target_uid = target_uids.get(target["name"])
    if target_uid:
        request("POST", f"/server/webcams/item?uid={urllib.parse.quote(target_uid)}", target)
    else:
        request("POST", "/server/webcams/item", target)

webcams = request("GET", "/server/webcams/list")["result"]["webcams"]
actual_names = [webcam.get("name") for webcam in webcams if webcam.get("source") == "database"]
if sorted(actual_names) != sorted(target_names):
    print(json.dumps({"unexpected_webcams": webcams}, indent=2), file=sys.stderr)
    sys.exit(1)
print(json.dumps({"webcams": webcams}, indent=2, sort_keys=True))
PY

echo "Service state:"
(systemctl --no-pager --full status \
  vision-framebuffer vision-framebuffer-nozzle-cam \
  vision-capture vision-capture-nozzle-cam \
  nginx moonraker crowsnest || true) | sed -n '1,220p'

echo "Moonraker webcam registration:"
curl -fsS http://127.0.0.1:7125/server/webcams/list || true

echo "Primary webcam stream health:"
if ! /usr/local/bin/webcam_health_probe.py \
  --duration 90 \
  --state-url http://127.0.0.1:8080/state \
  --stream-url 'http://127.0.0.1:8080/?action=stream' \
  --snapshot-url 'http://127.0.0.1/webcam/?action=snapshot' \
  --camera-device "${PRIMARY_CAMERA_DEVICE}" \
  --min-stream-bytes 250000 \
  --min-median-queued-fps 0.4 \
  --max-zero-samples 1 \
  --max-consecutive-zero 1 \
  --ignore-initial-samples 6 \
  --max-snapshot-p95 2.5 \
  --json-output "${VISION_DIR}/webcam_health_latest.json"; then
  echo "Webcam preview stream health check failed." >&2
  echo "Report: ${VISION_DIR}/webcam_health_latest.json" >&2
  exit 1
fi

echo "Nozzle camera stream health:"
if ! /usr/local/bin/webcam_health_probe.py \
  --duration 90 \
  --state-url http://127.0.0.1:8081/state \
  --stream-url 'http://127.0.0.1:8081/?action=stream' \
  --snapshot-url 'http://127.0.0.1/nozzle_cam/?action=snapshot' \
  --camera-device "${NOZZLE_CAMERA_DEVICE}" \
  --min-stream-bytes 250000 \
  --min-median-queued-fps 0.4 \
  --max-zero-samples 1 \
  --max-consecutive-zero 1 \
  --ignore-initial-samples 6 \
  --max-snapshot-p95 2.5 \
  --json-output "${VISION_DIR}/nozzle_cam/webcam_health_latest.json"; then
  echo "Nozzle camera preview stream health check failed." >&2
  echo "Report: ${VISION_DIR}/nozzle_cam/webcam_health_latest.json" >&2
  exit 1
fi

echo "Camera devices:"
ls -l "${PRIMARY_CAMERA_DEVICE}" "${NOZZLE_CAMERA_DEVICE}"
REMOTE_SCRIPT

echo "Webcam and vision-capture deployment complete."
