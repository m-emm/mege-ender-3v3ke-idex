#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--check]" >&2
}

MODE="update"
if [[ "$#" -eq 1 && "$1" == "--check" ]]; then
  MODE="check"
elif [[ "$#" -ne 0 ]]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/calibration_dashboard"
SOURCE_NGINX="${REPO_ROOT}/klipper_setup/image_build/overlays/stage2/99-klipperpi/files/nginx-mainsail.conf"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_DASHBOARD_DIR="/home/pi/printer_data/vision/multi_head_zero_calibration"
REMOTE_NGINX="/etc/nginx/sites-available/mainsail"
ASSETS=(index.html style.css app.js)

for asset in "${ASSETS[@]}"; do
  [[ -f "${SOURCE_DIR}/${asset}" ]] || { echo "Missing dashboard asset: ${asset}" >&2; exit 1; }
done
[[ -f "${SOURCE_NGINX}" ]] || { echo "Missing Nginx source: ${SOURCE_NGINX}" >&2; exit 1; }

directory_sha() {
  python3 - "$1" "${ASSETS[@]}" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for name in sys.argv[2:]:
    path = root / name
    digest.update(name.encode("utf-8") + b"\0")
    digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}

local_assets_sha="$(directory_sha "${SOURCE_DIR}")"
local_nginx_sha="$(sha256sum "${SOURCE_NGINX}" | awk '{print $1}')"

check_remote() {
  ssh "${REMOTE_HOST}" "CHECK_LOCAL_ASSETS_SHA='${local_assets_sha}' CHECK_LOCAL_NGINX_SHA='${local_nginx_sha}' REMOTE_DASHBOARD_DIR='${REMOTE_DASHBOARD_DIR}' REMOTE_NGINX='${REMOTE_NGINX}' python3 -" <<'PY'
import hashlib
import os
from pathlib import Path
import sys
import urllib.request

assets = ("index.html", "style.css", "app.js")
root = Path(os.environ["REMOTE_DASHBOARD_DIR"])
nginx = Path(os.environ["REMOTE_NGINX"])
digest = hashlib.sha256()
try:
    for name in assets:
        path = root / name
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    remote_assets = digest.hexdigest()
except OSError:
    remote_assets = ""
remote_nginx = hashlib.sha256(nginx.read_bytes()).hexdigest() if nginx.is_file() else ""
print(f"  Local dashboard assets sha256: {os.environ['CHECK_LOCAL_ASSETS_SHA']}")
print(f"  Remote dashboard assets sha256: {remote_assets}")
print(f"  Local Nginx config sha256: {os.environ['CHECK_LOCAL_NGINX_SHA']}")
print(f"  Remote Nginx config sha256: {remote_nginx}")
if remote_assets != os.environ["CHECK_LOCAL_ASSETS_SHA"]:
    raise SystemExit("dashboard asset parity check failed")
if remote_nginx != os.environ["CHECK_LOCAL_NGINX_SHA"]:
    raise SystemExit("Nginx config parity check failed")
with urllib.request.urlopen("http://127.0.0.1/calibration/", timeout=10) as response:
    if response.status != 200:
        raise SystemExit(f"dashboard HTTP status is {response.status}")
print("Calibration dashboard check passed.")
PY
}

if [[ "${MODE}" == "check" ]]; then
  check_remote
  exit 0
fi

remote_tmp="$(ssh "${REMOTE_HOST}" "mktemp -d /tmp/multi-head-zero-dashboard.XXXXXX")"
case "${remote_tmp}" in
  /tmp/multi-head-zero-dashboard.*) ;;
  *) echo "Refusing unexpected remote temporary directory: ${remote_tmp}" >&2; exit 1 ;;
esac
cleanup() {
  ssh "${REMOTE_HOST}" "rm -rf -- '${remote_tmp}'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp "${SOURCE_DIR}"/* "${SOURCE_NGINX}" "${REMOTE_HOST}:${remote_tmp}/"

ssh "${REMOTE_HOST}" \
  "REMOTE_TMP='${remote_tmp}' REMOTE_DASHBOARD_DIR='${REMOTE_DASHBOARD_DIR}' REMOTE_NGINX='${REMOTE_NGINX}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

mkdir -p "${REMOTE_DASHBOARD_DIR}" "${REMOTE_DASHBOARD_DIR}/data" "${REMOTE_DASHBOARD_DIR}/artifacts"
if [[ ! -f "${REMOTE_DASHBOARD_DIR}/data/current.json" ]]; then
  DASHBOARD_STATE_PATH="${REMOTE_DASHBOARD_DIR}/data/current.json" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["DASHBOARD_STATE_PATH"])
temporary = path.with_name(".%s.initial.tmp" % path.name)
temporary.write_text(
    json.dumps(
        {
            "schema_version": 2,
            "kind": "multi_head_zero_calibration_dashboard",
            "status": "idle",
            "workflow": "awaiting calibration",
            "events": [{"message": "No calibration run has been published yet."}],
            "chapters": {},
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
temporary.replace(path)
PY
fi
for asset in index.html style.css app.js; do
  install -m 0644 "${REMOTE_TMP}/${asset}" "${REMOTE_DASHBOARD_DIR}/${asset}"
done
sudo install -m 0644 "${REMOTE_TMP}/nginx-mainsail.conf" "${REMOTE_NGINX}"
sudo nginx -t
sudo systemctl reload nginx
REMOTE_SCRIPT

check_remote
echo "Calibration dashboard deployed: http://menderpi.local/calibration/"
