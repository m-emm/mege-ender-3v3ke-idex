#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
FILES_DIR="${REPO_ROOT}/klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
PRIORS_FILE="${SCRIPT_DIR}/priors.yaml"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"

shopt -s nullglob
python_files=("${FILES_DIR}"/*.py)
json_files=("${FILES_DIR}"/*.json)
png_files=("${FILES_DIR}"/*.png)

if (( ${#python_files[@]} == 0 )); then
  echo "No top-level Python files found in ${FILES_DIR}" >&2
  exit 1
fi
if (( ${#json_files[@]} == 0 )); then
  echo "No top-level JSON files found in ${FILES_DIR}" >&2
  exit 1
fi
if [[ ! -f "${PRIORS_FILE}" ]]; then
  echo "Missing required file: ${PRIORS_FILE}" >&2
  exit 1
fi

echo "Deploying ${#python_files[@]} Python files, ${#json_files[@]} JSON files, and ${#png_files[@]} PNG files to ${REMOTE_HOST}"

remote_tmp="$(ssh "${REMOTE_HOST}" "mktemp -d /tmp/vision-code.XXXXXX")"
case "${remote_tmp}" in
  /tmp/vision-code.*)
    ;;
  *)
    echo "Refusing unexpected remote temporary directory: ${remote_tmp}" >&2
    exit 1
    ;;
esac
cleanup() {
  ssh "${REMOTE_HOST}" "rm -rf -- '${remote_tmp}'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp "${python_files[@]}" "${json_files[@]}" ${png_files[@]+"${png_files[@]}"} "${PRIORS_FILE}" "${REMOTE_HOST}:${remote_tmp}/"

ssh "${REMOTE_HOST}" "REMOTE_TMP='${remote_tmp}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

sudo install -d -m 0755 /usr/local/bin /usr/local/share/vision

for source in "${REMOTE_TMP}"/*.py; do
  filename="${source##*/}"
  mode=0644
  case "${filename}" in
    vision_calibration.py|vision_capture.py|vision_framebuffer.py|webcam_health_probe.py)
      mode=0755
      ;;
  esac
  echo "Installing ${filename} -> /usr/local/bin/${filename}"
  sudo install -m "${mode}" "${source}" "/usr/local/bin/${filename}"
done

for source in "${REMOTE_TMP}"/*.json; do
  filename="${source##*/}"
  echo "Installing ${filename} -> /usr/local/share/vision/${filename}"
  sudo install -m 0644 "${source}" "/usr/local/share/vision/${filename}"
done

for source in "${REMOTE_TMP}"/*.png; do
  [[ -e "${source}" ]] || continue
  filename="${source##*/}"
  echo "Installing ${filename} -> /usr/local/share/vision/${filename}"
  sudo install -m 0644 "${source}" "/usr/local/share/vision/${filename}"
done

sudo install -m 0644 "${REMOTE_TMP}/priors.yaml" /usr/local/share/vision/priors.yaml
sudo rm -f /usr/local/share/vision/vision_calibration_priors.json

echo "Ensuring Python vision dependencies"
sudo apt-get install -y --no-install-recommends python3-matplotlib python3-scipy
python3 -c 'from scipy.stats import theilslopes'

echo "Restarting vision services"
sudo systemctl restart vision-framebuffer.service
sudo systemctl restart vision-framebuffer-nozzle-cam.service
sudo systemctl restart vision-capture.service
sudo systemctl restart vision-capture-nozzle-cam.service

echo "Fixing vision data ownership"
sudo chown -R pi:pi /home/pi/printer_data/vision/ 2>/dev/null || true

echo "Rebuilding static vision UI"
VISION_OUTPUT_DIR=/home/pi/printer_data/vision \
VISION_OUTPUT_URL_PREFIX=/vision \
  /usr/local/bin/vision_calibration.py rebuild-catalog

echo "Vision service state"
systemctl is-active \
  vision-framebuffer.service \
  vision-framebuffer-nozzle-cam.service \
  vision-capture.service \
  vision-capture-nozzle-cam.service
REMOTE_SCRIPT

echo "Vision code deployment complete. Python vision dependencies were ensured; Klipper, Moonraker, nginx, and webcam registration were not changed."
