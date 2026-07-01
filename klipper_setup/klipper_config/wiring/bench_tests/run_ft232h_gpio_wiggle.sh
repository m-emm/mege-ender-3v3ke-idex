#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  python3 -m venv "${SCRIPT_DIR}/.venv"
  "${PYTHON}" -m pip install --upgrade pip
  "${PYTHON}" -m pip install -r "${SCRIPT_DIR}/requirements.txt"
fi

exec "${PYTHON}" "${SCRIPT_DIR}/ft232h_gpio_wiggle.py" "$@"
