#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
KLIPPER_REV="7046bd00ef5c30dec6febc724f8d22967433c45c"
MSGPROTO_SHA256="fdb8c203af0dc336b1a0507804b4ceb5ddd9378b46cf889d52393ea756928486"
MSGPROTO_DIR="${REPO_ROOT}/.cache/klipper-bench/${KLIPPER_REV}"
MSGPROTO="${MSGPROTO_DIR}/msgproto.py"

if [[ ! -x "${PYTHON}" ]]; then
  python3 -m venv "${SCRIPT_DIR}/.venv"
  "${PYTHON}" -m pip install --upgrade pip
  "${PYTHON}" -m pip install -r "${SCRIPT_DIR}/requirements.txt"
fi

if [[ ! -f "${MSGPROTO}" ]]; then
  mkdir -p "${MSGPROTO_DIR}"
  curl --fail --location --silent --show-error \
    "https://raw.githubusercontent.com/Klipper3d/klipper/${KLIPPER_REV}/klippy/msgproto.py" \
    --output "${MSGPROTO}"
fi

ACTUAL_SHA256="$(shasum -a 256 "${MSGPROTO}" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${MSGPROTO_SHA256}" ]]; then
  echo "Klipper msgproto.py checksum mismatch: ${ACTUAL_SHA256}" >&2
  exit 1
fi

exec "${PYTHON}" \
  "${SCRIPT_DIR}/rp2040plus_tmc5160t_plus_y_bench.py" \
  --msgproto "${MSGPROTO}" \
  "$@"
