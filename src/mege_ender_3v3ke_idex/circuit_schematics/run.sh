#!/usr/bin/env bash

set -euo pipefail
trap 'echo "Script $0 failed at line $LINENO" >&2' ERR

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 path/to/design.py" >&2
    exit 2
fi

CALL_DIR="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." >/dev/null 2>&1 && pwd)"

DESIGN_SCRIPT="$1"
if [[ "${DESIGN_SCRIPT}" != /* ]]; then
    DESIGN_SCRIPT="${CALL_DIR}/${DESIGN_SCRIPT}"
fi

if [[ ! -f "${DESIGN_SCRIPT}" ]]; then
    echo "Design script not found: ${DESIGN_SCRIPT}" >&2
    exit 2
fi

MARKER="$(mktemp -t circuit_schematic_run.XXXXXX)"
trap 'rm -f "${MARKER}"' EXIT

cd "${REPO_ROOT}"
PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" python "${DESIGN_SCRIPT}"

EXPECTED_SVG="${DESIGN_SCRIPT%.*}.svg"
if [[ -f "${EXPECTED_SVG}" && "${EXPECTED_SVG}" -nt "${MARKER}" ]]; then
    SVG_FILE="${EXPECTED_SVG}"
else
    SVG_FILE="$(
        find "$(dirname "${DESIGN_SCRIPT}")" -maxdepth 1 -type f -name "*.svg" -newer "${MARKER}" -print |
        sort |
        tail -n 1
    )"
fi

if [[ -z "${SVG_FILE}" ]]; then
    echo "No generated SVG found next to ${DESIGN_SCRIPT}" >&2
    exit 1
fi

open -a "Google Chrome" "${SVG_FILE}"
