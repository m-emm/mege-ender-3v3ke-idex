#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
FILES_DIR="${REPO_ROOT}/klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
PRIMARY_CAMERA_DEVICE="${VISION_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0}"
NOZZLE_CAMERA_DEVICE="${NOZZLE_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Vimicro_corp._PC-LM1E_Camera_PC-LM1E_Audio-video-index0}"
WEBCAM_HEALTH_DURATION="${WEBCAM_HEALTH_DURATION:-10}"
WEBCAM_HEALTH_IGNORE_INITIAL_SAMPLES="${WEBCAM_HEALTH_IGNORE_INITIAL_SAMPLES:-2}"
VISION_CLEAN_SLATE="${VISION_CLEAN_SLATE:-0}"

required_files=(
  moonraker.conf
  nginx-mainsail.conf
  vision_framebuffer.py
  vision_capture.py
  vision_calibration.py
  vision_calibration_graph.py
  vision_bed_tab_y_scale.py
  vision_bed_tab_corner.py
  vision_red_marker_x_sweep.py
  vision_job_types.json
  vision_calibration_priors.json
  webcam_health_probe.py
  nozzle_cam_profiles.json
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
if [[ ! -f "${SCRIPT_DIR}/calib.yaml" ]]; then
  echo "Missing required file: ${SCRIPT_DIR}/calib.yaml" >&2
  exit 1
fi

echo "Checking cameras on ${REMOTE_HOST}:"
echo "  primary: ${PRIMARY_CAMERA_DEVICE}"
echo "  nozzle_cam: ${NOZZLE_CAMERA_DEVICE}"
echo "  health probe duration: ${WEBCAM_HEALTH_DURATION}s"
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
  "${FILES_DIR}/vision_calibration.py" \
  "${FILES_DIR}/vision_calibration_graph.py" \
  "${FILES_DIR}/vision_bed_tab_y_scale.py" \
  "${FILES_DIR}/vision_bed_tab_corner.py" \
  "${FILES_DIR}/vision_red_marker_x_sweep.py" \
  "${FILES_DIR}/vision_job_types.json" \
  "${FILES_DIR}/vision_calibration_priors.json" \
  "${FILES_DIR}/webcam_health_probe.py" \
  "${FILES_DIR}/nozzle_cam_profiles.json" \
  "${FILES_DIR}/vision-framebuffer.service" \
  "${FILES_DIR}/vision-framebuffer-nozzle-cam.service" \
  "${FILES_DIR}/vision-capture.service" \
  "${FILES_DIR}/vision-capture-nozzle-cam.service" \
  "${SCRIPT_DIR}/calib.yaml" \
  "${REMOTE_HOST}:${remote_tmp}/"

ssh "${REMOTE_HOST}" \
  "REMOTE_TMP='${remote_tmp}' PRIMARY_CAMERA_DEVICE='${PRIMARY_CAMERA_DEVICE}' NOZZLE_CAMERA_DEVICE='${NOZZLE_CAMERA_DEVICE}' WEBCAM_HEALTH_DURATION='${WEBCAM_HEALTH_DURATION}' WEBCAM_HEALTH_IGNORE_INITIAL_SAMPLES='${WEBCAM_HEALTH_IGNORE_INITIAL_SAMPLES}' VISION_CLEAN_SLATE='${VISION_CLEAN_SLATE}' bash -s" <<'REMOTE_SCRIPT'
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

if [[ "${VISION_CLEAN_SLATE}" == "1" ]]; then
  if [[ "${USERNAME}" != "pi" || "${USER_HOME}" != "/home/pi" ]]; then
    echo "Refusing clean-slate deletion for unexpected user/home: ${USERNAME} ${USER_HOME}" >&2
    exit 1
  fi
  echo "Checking that Klipper is ready and no virtual-SD print is active..."
  python3 - <<'PY'
import json
import urllib.request

url = (
    "http://127.0.0.1/printer/objects/query?"
    "webhooks=state&print_stats=state,filename&virtual_sdcard=is_active"
)
with urllib.request.urlopen(url, timeout=10) as response:
    status = json.loads(response.read())["result"]["status"]
if status.get("webhooks", {}).get("state") != "ready":
    raise SystemExit(f"Klipper is not ready: {status}")
if status.get("print_stats", {}).get("state") not in ("standby", "complete"):
    raise SystemExit(f"Printer is not idle: {status}")
if status.get("virtual_sdcard", {}).get("is_active"):
    raise SystemExit(f"Virtual SD is active: {status}")
PY
  echo "Stopping vision writers and removing the authorized legacy data..."
  sudo systemctl stop vision-capture.service vision-capture-nozzle-cam.service
  python3 - <<'PY'
import shutil
from pathlib import Path

for expected in (
    Path("/home/pi/printer_data/vision"),
    Path("/home/pi/printer_data/gcodes/vision_jobs"),
):
    expected.mkdir(parents=True, exist_ok=True)
    if expected.resolve() != expected:
        raise SystemExit(f"Refusing unexpected cleanup target: {expected.resolve()}")
    for child in list(expected.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
PY
fi

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
  "${CONFIG_DIR}" "${LOG_DIR}" "${PRINTER_DATA}/systemd" \
  "${VISION_DIR}" "${VISION_DIR}/calibration/jobs" \
  "${VISION_DIR}/calibration/publications" \
  "${PRINTER_DATA}/gcodes/vision_jobs"
sudo install -d -m 0755 /usr/local/share/vision
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
sudo install -m 0755 "${REMOTE_TMP}/vision_calibration.py" /usr/local/bin/vision_calibration.py
sudo install -m 0644 "${REMOTE_TMP}/vision_calibration_graph.py" /usr/local/bin/vision_calibration_graph.py
sudo install -m 0644 "${REMOTE_TMP}/vision_bed_tab_y_scale.py" /usr/local/bin/vision_bed_tab_y_scale.py
sudo install -m 0644 "${REMOTE_TMP}/vision_bed_tab_corner.py" /usr/local/bin/vision_bed_tab_corner.py
sudo install -m 0644 "${REMOTE_TMP}/vision_red_marker_x_sweep.py" /usr/local/bin/vision_red_marker_x_sweep.py
sudo install -m 0755 "${REMOTE_TMP}/webcam_health_probe.py" /usr/local/bin/webcam_health_probe.py
sudo install -m 0644 "${REMOTE_TMP}/nozzle_cam_profiles.json" /usr/local/share/vision/nozzle_cam_profiles.json
sudo install -m 0644 "${REMOTE_TMP}/vision_job_types.json" /usr/local/share/vision/vision_job_types.json
sudo install -m 0644 "${REMOTE_TMP}/vision_calibration_priors.json" /usr/local/share/vision/vision_calibration_priors.json
sudo install -m 0644 "${REMOTE_TMP}/calib.yaml" /usr/local/share/vision/calib.yaml
sudo rm -f \
  /usr/local/bin/vision_bed_y.py \
  /usr/local/bin/vision_nozzle_align.py \
  /usr/local/bin/vision_rough_calibration.py \
  /usr/local/bin/eddy_relative_calibration.py \
  /usr/local/bin/eddy_z_diagnostic.py \
  /usr/local/bin/vision_runner.py
sudo install -m 0644 "${REMOTE_TMP}/vision-framebuffer.service" /etc/systemd/system/vision-framebuffer.service
sudo install -m 0644 "${REMOTE_TMP}/vision-framebuffer-nozzle-cam.service" /etc/systemd/system/vision-framebuffer-nozzle-cam.service
sudo install -m 0644 "${REMOTE_TMP}/vision-capture.service" /etc/systemd/system/vision-capture.service
sudo install -m 0644 "${REMOTE_TMP}/vision-capture-nozzle-cam.service" /etc/systemd/system/vision-capture-nozzle-cam.service
sudo usermod -a -G video "${USERNAME}" || true
sudo rm -f /run/vision-preview/profile_request.json \
  /run/vision-preview-nozzle_cam/profile_request.json
sudo chown -R "${USERNAME}:${USERNAME}" "${VISION_DIR}"

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

echo "Regenerating static vision UI..."
sudo -u "${USERNAME}" env \
  VISION_OUTPUT_DIR="${VISION_DIR}" \
  VISION_OUTPUT_URL_PREFIX=/vision \
  /usr/local/bin/vision_calibration.py sync-priors
sudo -u "${USERNAME}" env \
  VISION_OUTPUT_DIR="${VISION_DIR}" \
  VISION_OUTPUT_URL_PREFIX=/vision \
  /usr/local/bin/vision_calibration.py rebuild-catalog

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
  --duration "${WEBCAM_HEALTH_DURATION}" \
  --state-url http://127.0.0.1:8080/state \
  --stream-url 'http://127.0.0.1:8080/?action=stream' \
  --snapshot-url 'http://127.0.0.1/webcam/?action=snapshot' \
  --camera-device "${PRIMARY_CAMERA_DEVICE}" \
  --min-stream-bytes 250000 \
  --min-median-queued-fps 0.4 \
  --max-zero-samples 1 \
  --max-consecutive-zero 1 \
  --ignore-initial-samples "${WEBCAM_HEALTH_IGNORE_INITIAL_SAMPLES}" \
  --max-snapshot-p95 2.5 \
  --json-output "${REMOTE_TMP}/webcam_health_primary.json"; then
  echo "Webcam preview stream health check failed." >&2
  echo "Report: ${REMOTE_TMP}/webcam_health_primary.json" >&2
  exit 1
fi

echo "Nozzle camera stream health:"
if ! /usr/local/bin/webcam_health_probe.py \
  --duration "${WEBCAM_HEALTH_DURATION}" \
  --state-url http://127.0.0.1:8081/state \
  --stream-url 'http://127.0.0.1:8081/?action=stream' \
  --snapshot-url 'http://127.0.0.1/nozzle_cam/?action=snapshot' \
  --camera-device "${NOZZLE_CAMERA_DEVICE}" \
  --min-stream-bytes 250000 \
  --min-median-queued-fps 0.4 \
  --max-zero-samples 1 \
  --max-consecutive-zero 1 \
  --ignore-initial-samples "${WEBCAM_HEALTH_IGNORE_INITIAL_SAMPLES}" \
  --max-snapshot-p95 2.5 \
  --json-output "${REMOTE_TMP}/webcam_health_nozzle_cam.json"; then
  echo "Nozzle camera preview stream health check failed." >&2
  echo "Report: ${REMOTE_TMP}/webcam_health_nozzle_cam.json" >&2
  exit 1
fi

echo "Camera devices:"
ls -l "${PRIMARY_CAMERA_DEVICE}" "${NOZZLE_CAMERA_DEVICE}"
REMOTE_SCRIPT

echo "Webcam and vision-capture deployment complete."
