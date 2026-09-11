#!/usr/bin/env bash
# Read-only capture of a compact, traceable local dashboard simulator fixture set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESTINATION="${REPO_ROOT}/tests/fixtures/idex_calibration_dashboard"
HOST="pi@menderpi.local"
REMOTE_ROOT="/home/pi/printer_data/calibration"

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --host) HOST="${2:?--host requires a value}"; shift 2 ;;
        --destination) DESTINATION="${2:?--destination requires a value}"; shift 2 ;;
        -h|--help)
            cat <<'EOF'
Usage: scripts/capture_idex_calibration_dashboard_simulator_fixtures.sh [--host USER@HOST] [--destination PATH]

Copies a small read-only snapshot from the printer: calibration state, selected
plot assets, Moonraker status/console samples, and one camera still. It does
not invoke G-code, deploy files, or modify printer state.
EOF
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "${DESTINATION}/artifacts"
temporary="$(mktemp -d)"
cleanup() { rm -rf "${temporary}"; }
trap cleanup EXIT

readonly SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}")

# State is copied explicitly, never recursively. Missing last_successful is a
# normal production condition and is represented by an empty object.
for item in accepted current activity last_successful; do
    if "${SSH[@]}" "test -f '${REMOTE_ROOT}/data/${item}.json'"; then
        scp -q "${HOST}:${REMOTE_ROOT}/data/${item}.json" "${temporary}/source_${item}.json"
    else
        printf '{}\n' > "${temporary}/source_${item}.json"
    fi
done

remote_python() {
    local source="$1"
    local encoded
    encoded="$(printf '%s' "${source}" | base64 | tr -d '\n')"
    "${SSH[@]}" "printf '%s' '${encoded}' | base64 -d | python3"
}

remote_python $'import json\nimport urllib.request\nurl = "http://127.0.0.1:7125/printer/objects/query?webhooks&toolhead&gcode_move&print_stats&extruder&extruder1&heater_bed"\nprint(json.dumps(json.load(urllib.request.urlopen(url, timeout=5)), indent=2))\n' > "${temporary}/moonraker_status.json"
remote_python $'import json\nimport urllib.request\nurl = "http://127.0.0.1:7125/server/gcode_store?count=80"\nprint(json.dumps(json.load(urllib.request.urlopen(url, timeout=5)).get("result", {}).get("gcode_store", []), indent=2))\n' > "${temporary}/moonraker_console.json"
"${SSH[@]}" "curl -fsS --max-time 10 'http://127.0.0.1/webcam/?action=snapshot'" > "${temporary}/camera.jpg"

# These are the representative assets used by the acceptance ledger's current
# evidence. Copying individual files keeps the fixture compact and auditable.
declare -a REMOTE_ASSETS=(
    "2026-09-10_17-58-07_T0_T1_calibration_T0_calibration.png"
    "2026-09-10_17-58-07_T0_T1_calibration_T1_calibration.png"
    "2026-09-10_17-58-07_T0_T1_verification_T0_verification.png"
    "2026-09-10_17-58-07_T0_T1_verification_T1_verification.png"
    "20260910T172427Z_bed_mesh.png"
)
for asset in "${REMOTE_ASSETS[@]}"; do
    scp -q "${HOST}:${REMOTE_ROOT}/artifacts/${asset}" "${temporary}/${asset}"
done

cp "${temporary}/moonraker_status.json" "${temporary}/moonraker_console.json" "${temporary}/camera.jpg" "${DESTINATION}/"
cp "${temporary}"/*.png "${DESTINATION}/artifacts/"

# The seed is a faithful copy of captured accepted evidence. The simulator
# creates a local 'ready' composition by marking the captured persisted mesh
# evidence accepted only within its volatile simulator state.
cp "${temporary}/source_accepted.json" "${DESTINATION}/seed_accepted.json"

python3 - "${DESTINATION}" "${HOST}" "${REMOTE_ROOT}" "${temporary}" <<'PY'
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
temporary = Path(sys.argv[4])
accepted = json.loads((temporary / 'source_accepted.json').read_text())
current = json.loads((temporary / 'source_current.json').read_text())
activity = json.loads((temporary / 'source_activity.json').read_text())
last_successful = json.loads((temporary / 'source_last_successful.json').read_text())
(root / 'captured_context.json').write_text(json.dumps({
    'kind': 'curated_idex_dashboard_context',
    'accepted': {
        chapter: {key: entry.get(key) for key in ('status', 'attempt_id', 'artifact', 'accepted_at')}
        for chapter, entry in (accepted.get('accepted') or {}).items()
    },
    'attempt': {key: (current.get('attempt') or {}).get(key) for key in ('attempt_id', 'status', 'stage', 'run_scope')},
    'activity': {key: activity.get(key) for key in ('state', 'step', 'operation', 'progress')},
    'last_successful_batch_id': last_successful.get('batch_id'),
}, indent=2, sort_keys=True) + '\n')
files = []
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'provenance.json':
        files.append({
            'path': str(path.relative_to(root)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        })
(root / 'provenance.json').write_text(json.dumps({
    'kind': 'idex_calibration_dashboard_simulator_fixture',
    'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
    'source_host': sys.argv[2],
    'source_calibration_root': sys.argv[3],
    'read_only': True,
    'files': files,
}, indent=2, sort_keys=True) + '\n')
PY

echo "Captured local simulator fixtures in ${DESTINATION}"
