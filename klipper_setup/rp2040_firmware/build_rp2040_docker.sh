#!/bin/bash
set -euo pipefail

# Build RP2040 Klipper firmware using Docker.
# Host-side RP2040 builds are intentionally unsupported in this repo.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="klipper-rp2040-builder"

INTERACTIVE=0
CONFIG_FILE="rp2040_config"

: "${KLIPPER_REF:=576d0ca13}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [-i] [-d | -k] [-c <config_file>]

Options:
  -i   Start the builder container and drop into an interactive shell (debug)
  -d   Build Klipper for direct BOOTSEL flashing (uses rp2040_config_direct)
  -k   Build Klipper for Katapult (bootloader offset; uses rp2040_config)
  -c   Use an explicit config file from this directory
  -h   Show this help

Environment:
  KLIPPER_REF  Git ref/commit for Klipper (default: ${KLIPPER_REF})
  CLEAN=1      Opt in to make clean before building. By default, existing
               ignored build output is reused and rebuilt incrementally.
EOF
}

while getopts ":idkc:h" opt; do
  case "${opt}" in
    i)
      INTERACTIVE=1
      ;;
    d)
      CONFIG_FILE="rp2040_config_direct"
      ;;
    k)
      CONFIG_FILE="rp2040_config"
      ;;
    c)
      CONFIG_FILE="${OPTARG}"
      ;;
    h)
      usage
      exit 0
      ;;
    \?)
      echo "Unknown option: -${OPTARG}" >&2
      usage >&2
      exit 2
      ;;
  esac
done
shift $((OPTIND - 1))

if [[ ! -f "${SCRIPT_DIR}/${CONFIG_FILE}" ]]; then
  echo "ERROR: Config not found: ${SCRIPT_DIR}/${CONFIG_FILE}" >&2
  echo "Available configs:" >&2
  (cd "${SCRIPT_DIR}" && ls -1 rp2040_config* 2>/dev/null || true) >&2
  exit 1
fi

if grep -qE '^CONFIG_RPXXXX_HAVE_BOOTLOADER=y' "${SCRIPT_DIR}/${CONFIG_FILE}"; then
  EXPECTED_FIRMWARE="klipper.bin"
else
  EXPECTED_FIRMWARE="klipper.uf2"
fi

echo "==> Building Docker image..."
echo "    KLIPPER_REF=${KLIPPER_REF}"
echo "    Config=${CONFIG_FILE}"
echo "    Expected firmware=${EXPECTED_FIRMWARE}"

docker build  -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo "==> Running build in Docker container..."

if [[ "${INTERACTIVE}" -eq 1 ]]; then
  echo "==> Interactive mode: starting container shell for debugging."
  echo "    Inside the container you can run: /work/build_rp2040_script_for_in_docker.sh"
  echo "    Selected config: ${CONFIG_FILE}"
  docker run --rm -it \
    -v "${SCRIPT_DIR}:/work" \
    -u "$(id -u):$(id -g)" \
    -e "KLIPPER_REF=${KLIPPER_REF}" \
    -e "KLIPPER_CONFIG_FILE=${CONFIG_FILE}" \
    -e "CLEAN=${CLEAN:-0}" \
    -e "EXPECTED_FIRMWARE=${EXPECTED_FIRMWARE}" \
    "${IMAGE_NAME}" \
    bash
  exit 0
fi

docker run --rm \
  -v "${SCRIPT_DIR}:/work" \
  -u "$(id -u):$(id -g)" \
  -e "KLIPPER_REF=${KLIPPER_REF}" \
  -e "KLIPPER_CONFIG_FILE=${CONFIG_FILE}" \
  -e "CLEAN=${CLEAN:-0}" \
  -e "EXPECTED_FIRMWARE=${EXPECTED_FIRMWARE}" \
  "${IMAGE_NAME}" \
  bash -lc "/work/build_rp2040_script_for_in_docker.sh"

echo ""
if [[ "${EXPECTED_FIRMWARE}" == "klipper.bin" && -f "${SCRIPT_DIR}/klipper/out/klipper.bin" ]]; then
  echo "==> Success! Firmware ready to flash via Katapult."
  echo "    Location: ${SCRIPT_DIR}/klipper/out/klipper.bin"
elif [[ "${EXPECTED_FIRMWARE}" == "klipper.uf2" && -f "${SCRIPT_DIR}/klipper/out/klipper.uf2" ]]; then
  echo "==> Success! Firmware ready to flash (BOOTSEL mass storage)."
  echo "    Location: ${SCRIPT_DIR}/klipper/out/klipper.uf2"
else
  echo "==> Build finished, but ${EXPECTED_FIRMWARE} was not found in ${SCRIPT_DIR}/klipper/out" >&2
  exit 1
fi

echo ""
echo "To flash:"
echo "  Direct (no Katapult): ./flash_rp2040.sh"
echo "  Katapult path:        ./flash_klipper_via_katapult.sh -d <device>"
