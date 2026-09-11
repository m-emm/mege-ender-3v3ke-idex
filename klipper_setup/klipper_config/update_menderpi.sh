#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 1 ] && [ "$1" = "--check" ]; then
  MODE=check
elif [ "$#" -eq 1 ] && [ "$1" = "--mege-outside-enroll" ]; then
  MODE=outside_enroll
elif [ "$#" -eq 4 ] && [ "$1" = "--mege-outside-activate" ]; then
  MODE=outside_activate
  HUB_WG_PUBLIC_KEY=$2
  OUTSIDE_HOST=$3
  HUB_SSH_HOST_KEY=$4
elif [ "$#" -eq 0 ]; then
  MODE=update
else
  echo "Usage: $0 [--check|--mege-outside-enroll|--mege-outside-activate <hub-wireguard-public-key> os.meges-world.net <hub-ssh-ed25519-public-key>]" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
SETUP_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
SOURCE_CFG="$SCRIPT_DIR/printer.cfg"
SOURCE_HOST_ROOT="$SETUP_DIR/klipper_host"
SOURCE_HOST_OVERLAY="$SOURCE_HOST_ROOT/klippy"
SOURCE_RUNTIME_HELPERS="$SETUP_DIR/runtime_helpers"
SOURCE_OUTSIDE_CLIENT_ROOT="$SETUP_DIR/image_build/overlays/stage2/99-klipperpi/files/mege_outside"
SOURCE_KLIPPER_COMMIT="$SETUP_DIR/KLIPPER_COMMIT"

REMOTE_HOST=${MENDERPI_HOST-}
[ -n "$REMOTE_HOST" ] || REMOTE_HOST=pi@menderpi.local
REMOTE_KLIPPER_DIR=${MENDERPI_KLIPPER_DIR-}
[ -n "$REMOTE_KLIPPER_DIR" ] || REMOTE_KLIPPER_DIR=/opt/klipper
REMOTE_CONFIG_DIR=${MENDERPI_CONFIG_DIR-}
[ -n "$REMOTE_CONFIG_DIR" ] || REMOTE_CONFIG_DIR=/home/pi/printer_data/config
REMOTE_MANAGED_STATE=${MENDERPI_MANAGED_STATE-}
[ -n "$REMOTE_MANAGED_STATE" ] || REMOTE_MANAGED_STATE=/var/lib/klipperpi/managed-overlay.json

TMP_ROOT=${TMPDIR-}
[ -n "$TMP_ROOT" ] || TMP_ROOT=/tmp
LOCAL_TMP_DIR=$(mktemp -d "$TMP_ROOT/klipperpi-update.XXXXXX")
REMOTE_TMP_DIR=

cleanup() {
  rm -rf -- "$LOCAL_TMP_DIR"
  if [ -n "$REMOTE_TMP_DIR" ]; then
    ssh "$REMOTE_HOST" "rm -rf -- '$REMOTE_TMP_DIR'" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

manifest_tree() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path
root = Path(sys.argv[1])
if not root.is_dir():
    raise SystemExit(f"manifest root is not a directory: {root}")
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(root)
    if "__pycache__" in relative.parts or path.suffix == ".pyc":
        continue
    print(f"{relative.as_posix()}\t{hashlib.sha256(path.read_bytes()).hexdigest()}")
PY
}

validate_local_sources() {
  python3 "$SCRIPT_DIR/generate_printer_cfg.py" --check
  "$SCRIPT_DIR/wiring/generate_wiring_svgs.sh" --check
  python3 "$SCRIPT_DIR/wiring/validate_wiring.py"
  [ -f "$SOURCE_CFG" ] || { echo "Missing $SOURCE_CFG" >&2; exit 1; }
  [ -d "$SOURCE_HOST_OVERLAY" ] || { echo "Missing $SOURCE_HOST_OVERLAY" >&2; exit 1; }
  [ -d "$SOURCE_RUNTIME_HELPERS" ] || { echo "Missing $SOURCE_RUNTIME_HELPERS" >&2; exit 1; }
  [ -d "$SOURCE_OUTSIDE_CLIENT_ROOT" ] || { echo "Missing $SOURCE_OUTSIDE_CLIENT_ROOT" >&2; exit 1; }
  [ -f "$SOURCE_KLIPPER_COMMIT" ] || { echo "Missing $SOURCE_KLIPPER_COMMIT" >&2; exit 1; }
  local commit
  commit=$(tr -d '[:space:]' < "$SOURCE_KLIPPER_COMMIT")
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid Klipper commit: $commit" >&2; exit 1; }
  python3 - "$SOURCE_HOST_ROOT" "$SOURCE_RUNTIME_HELPERS" <<'PY'
import ast
import sys
from pathlib import Path
for root_arg in sys.argv[1:]:
    for path in sorted(Path(root_arg).rglob("*.py")):
        if "__pycache__" not in path.parts and path.suffix != ".pyc":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
PY
  manifest_tree "$SOURCE_HOST_OVERLAY" > "$LOCAL_TMP_DIR/host.manifest"
  manifest_tree "$SOURCE_RUNTIME_HELPERS" > "$LOCAL_TMP_DIR/runtime.manifest"
  manifest_tree "$SOURCE_OUTSIDE_CLIENT_ROOT" > "$LOCAL_TMP_DIR/outside.manifest"
}

remote_payload() {
  ssh "$REMOTE_HOST" \
    "sudo -n env REMOTE_KLIPPER_DIR='$REMOTE_KLIPPER_DIR' REMOTE_CONFIG_DIR='$REMOTE_CONFIG_DIR' REMOTE_MANAGED_STATE='$REMOTE_MANAGED_STATE' python3 -" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

klipper = Path(os.environ["REMOTE_KLIPPER_DIR"])
config = Path(os.environ["REMOTE_CONFIG_DIR"])
state_path = Path(os.environ["REMOTE_MANAGED_STATE"])
def digest(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except OSError:
    state = {}
payload = {
    "ok": False,
    "config_path": str(config / "printer.cfg"),
    "config_sha256": digest(config / "printer.cfg"),
    "managed_state": state,
    "host_targets": {p: digest(klipper / p) for p in state.get("host", {})},
    "runtime_targets": {p: digest(config / p) for p in state.get("runtime", {})},
    "outside_targets": {},
}
outside_targets = {
    "mege-outside-enroll.sh": Path("/usr/local/sbin/mege-outside-enroll"),
    "mege-outside-activate.sh": Path("/usr/local/sbin/mege-outside-activate"),
    "mege.conf.template": Path("/usr/local/share/mege-outside/mege.conf.template"),
    "mege-printer-tunnel.service": Path("/etc/systemd/system/mege-printer-tunnel.service"),
}
payload["outside_targets"] = {
    relative: digest(target) for relative, target in outside_targets.items()
    if relative in state.get("outside", {})
}
def active(unit):
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", unit], check=False
    ).returncode == 0
payload["outside"] = {
    "enrolled": Path("/etc/wireguard/mege.key").is_file()
    and Path("/home/pi/.ssh/mege-outside-printer-tunnel").is_file(),
    "wireguard_config": Path("/etc/wireguard/mege.conf").is_file(),
    "wireguard_active": active("wg-quick@mege.service"),
    "tunnel_active": active("mege-printer-tunnel.service"),
    "handshake_epoch": 0,
}
try:
    for line in subprocess.check_output(
        ["wg", "show", "mege", "latest-handshakes"], text=True
    ).splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].isdigit():
            payload["outside"]["handshake_epoch"] = int(fields[1])
            break
except (FileNotFoundError, subprocess.CalledProcessError):
    pass
try:
    payload["klipper_commit"] = subprocess.check_output(
        ["git", "-C", str(klipper), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.check_call(
        ["/opt/klipper-env/bin/python3", "-c", "import sqlitedict"],
        stdout=subprocess.DEVNULL,
    )
    payload["dependency_ok"] = True
    deadline = time.monotonic() + 60
    while True:
        with urllib.request.urlopen(
            "http://127.0.0.1:7125/printer/objects/query?webhooks&configfile",
            timeout=10,
        ) as response:
            payload["status"] = json.loads(response.read())["result"]["status"]
        if payload["status"].get("webhooks", {}).get("state") != "startup":
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(2)
    payload["ok"] = True
except Exception as exc:
    payload["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(payload, sort_keys=True))
PY
}

check_live_config() {
  echo "Checking $REMOTE_HOST using directory manifests..."
  echo "  $SOURCE_CFG -> $REMOTE_CONFIG_DIR/printer.cfg"
  echo "  $SOURCE_HOST_ROOT/klippy/ -> $REMOTE_KLIPPER_DIR/"
  echo "  $SOURCE_RUNTIME_HELPERS/ -> $REMOTE_CONFIG_DIR/"
  echo "  Precedence: upstream Klipper, then klipper_host/klippy/, then runtime_helpers/"
  validate_local_sources
  local config_sha expected_fingerprint payload
  config_sha=$(sha256sum "$SOURCE_CFG" | awk '{print $1}')
  expected_fingerprint=$(python3 "$SCRIPT_DIR/generate_printer_cfg.py" --fingerprint)
  payload=$(remote_payload)
  CHECK_LOCAL_CONFIG_SHA=$config_sha \
  CHECK_EXPECTED_FINGERPRINT=$expected_fingerprint \
  CHECK_LOCAL_HOST_MANIFEST="$(cat "$LOCAL_TMP_DIR/host.manifest")" \
  CHECK_LOCAL_RUNTIME_MANIFEST="$(cat "$LOCAL_TMP_DIR/runtime.manifest")" \
  CHECK_LOCAL_OUTSIDE_MANIFEST="$(cat "$LOCAL_TMP_DIR/outside.manifest")" \
  CHECK_EXPECTED_KLIPPER_COMMIT="$(tr -d '[:space:]' < "$SOURCE_KLIPPER_COMMIT")" \
  CHECK_REMOTE_PAYLOAD=$payload \
  python3 - "$SCRIPT_DIR/generate_printer_cfg.py" <<'PY'
import importlib.util
import json
import os
import sys
import time
spec = importlib.util.spec_from_file_location("generate_printer_cfg", sys.argv[1])
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
def manifest(value):
    return {line.split("\t", 1)[0]: line.split("\t", 1)[1]
            for line in value.splitlines() if line}
local_config = os.environ["CHECK_LOCAL_CONFIG_SHA"]
local_host = manifest(os.environ["CHECK_LOCAL_HOST_MANIFEST"])
local_runtime = manifest(os.environ["CHECK_LOCAL_RUNTIME_MANIFEST"])
local_outside = manifest(os.environ["CHECK_LOCAL_OUTSIDE_MANIFEST"])
remote = json.loads(os.environ["CHECK_REMOTE_PAYLOAD"])
state = remote.get("managed_state", {})
errors = []
if not remote.get("ok"):
    errors.append(f"remote inspection failed: {remote.get('error', 'unknown error')}")
if remote.get("config_sha256") != local_config:
    errors.append("remote printer.cfg does not match generated local config")
if remote.get("klipper_commit") != os.environ["CHECK_EXPECTED_KLIPPER_COMMIT"]:
    errors.append("remote Klipper commit does not match shared pin")
if not remote.get("dependency_ok"):
    errors.append("remote Klipper environment is missing sqlitedict")
for label, local, section, target_key in (
    ("host overlay", local_host, "host", "host_targets"),
    ("runtime bundle", local_runtime, "runtime", "runtime_targets"),
    ("outside-client bundle", local_outside, "outside", "outside_targets"),
):
    managed = state.get(section, {})
    missing = sorted(set(local) - set(managed))
    unexpected = sorted(set(managed) - set(local))
    if missing:
        errors.append(f"{label} manifest missing: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{label} manifest has unexpected paths: {', '.join(unexpected)}")
    for relative, expected in local.items():
        if remote.get(target_key, {}).get(relative) != expected:
            errors.append(f"{label} mismatch at {relative}")
outside = remote.get("outside", {})
if outside.get("wireguard_config"):
    if not outside.get("wireguard_active"):
        errors.append("WireGuard configuration exists but wg-quick@mege is not active")
    if not outside.get("tunnel_active"):
        errors.append("WireGuard configuration exists but mege-printer-tunnel is not active")
    handshake = outside.get("handshake_epoch", 0)
    if not isinstance(handshake, int) or handshake <= 0 or time.time() - handshake > 300:
        errors.append("WireGuard handshake is absent or older than 300 seconds")
elif outside.get("wireguard_active") or outside.get("tunnel_active"):
    errors.append("outside services are active before mege.conf exists")
status = remote.get("status", {})
errors.extend(generator.live_config_check_errors(
    local_sha256=local_config,
    remote_sha256=remote.get("config_sha256", ""),
    expected_fingerprint=os.environ["CHECK_EXPECTED_FINGERPRINT"],
    status=status,
))
bed = status.get("configfile", {}).get("settings", {}).get("heater_bed", {})
if bed.get("heater_pin") != "gpio20":
    errors.append(f"live heater_bed.heater_pin is {bed.get('heater_pin')!r}, expected 'gpio20'")
try:
    if abs(float(bed.get("pwm_cycle_time")) - 2.0) > 1e-6:
        errors.append("live heater_bed.pwm_cycle_time is not 2.0")
except (TypeError, ValueError):
    errors.append("live heater_bed.pwm_cycle_time is not numeric")
print(f"  Remote config: {remote.get('config_path')}")
print(f"  Remote Klipper commit: {remote.get('klipper_commit')}")
print(f"  Klippy state: {status.get('webhooks', {}).get('state')}")
print(f"  Managed host files: {len(state.get('host', {}))}")
print(f"  Managed runtime files: {len(state.get('runtime', {}))}")
print(f"  Managed outside-client files: {len(state.get('outside', {}))}")
print(f"  Outside enrollment: {'yes' if outside.get('enrolled') else 'no'}")
if outside.get("wireguard_config"):
    print(f"  Outside WireGuard handshake epoch: {outside.get('handshake_epoch')}")
else:
    print("  Outside activation: not activated")
if errors:
    print("Directory deployment check failed:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    raise SystemExit(1)
print("Directory deployment check passed.")
PY
}

if [ "$MODE" = check ]; then
  check_live_config
  MENDERPI_HOST="$REMOTE_HOST" bash "$SCRIPT_DIR/deploy_installed_overlay.sh" --check
  MENDERPI_HOST="$REMOTE_HOST" bash "$SCRIPT_DIR/deploy_multi_head_zero_calibration_dashboard.sh" --check
  MENDERPI_HOST="$REMOTE_HOST" bash "$SCRIPT_DIR/deploy_eddy_tap_dashboard.sh" --check
  exit 0
fi

if [ "$MODE" = outside_activate ]; then
  echo "Activating the enrolled Mege outside client on $REMOTE_HOST..."
  HUB_WG_PUBLIC_KEY_B64=$(printf '%s' "$HUB_WG_PUBLIC_KEY" | base64 | tr -d '\n')
  OUTSIDE_HOST_B64=$(printf '%s' "$OUTSIDE_HOST" | base64 | tr -d '\n')
  HUB_SSH_HOST_KEY_B64=$(printf '%s' "$HUB_SSH_HOST_KEY" | base64 | tr -d '\n')
  ssh "$REMOTE_HOST" "sudo -n bash -s" <<REMOTE_SCRIPT
set -euo pipefail
hub_wg_public_key=\$(printf '%s' '$HUB_WG_PUBLIC_KEY_B64' | base64 -d)
outside_host=\$(printf '%s' '$OUTSIDE_HOST_B64' | base64 -d)
hub_ssh_host_key=\$(printf '%s' '$HUB_SSH_HOST_KEY_B64' | base64 -d)
/usr/local/sbin/mege-outside-activate "\$hub_wg_public_key" "\$outside_host" "\$hub_ssh_host_key"
REMOTE_SCRIPT
  exit 0
fi

python3 "$SCRIPT_DIR/generate_printer_cfg.py"
validate_local_sources
REMOTE_TMP_DIR=$(ssh "$REMOTE_HOST" "mktemp -d /tmp/klipperpi-update.XXXXXX")
case "$REMOTE_TMP_DIR" in
  /tmp/klipperpi-update.*) ;;
  *) echo "Refusing unexpected remote temporary directory: $REMOTE_TMP_DIR" >&2; exit 1 ;;
esac

echo "Staging config, canonical host overlay, runtime helpers, and outside-client files..."
scp -r "$SOURCE_HOST_ROOT" "$SOURCE_RUNTIME_HELPERS" "$SOURCE_OUTSIDE_CLIENT_ROOT" "$SOURCE_CFG" \
  "$SOURCE_KLIPPER_COMMIT" "$LOCAL_TMP_DIR/host.manifest" \
  "$LOCAL_TMP_DIR/runtime.manifest" "$LOCAL_TMP_DIR/outside.manifest" \
  "$REMOTE_HOST:$REMOTE_TMP_DIR/"

ssh "$REMOTE_HOST" \
  "REMOTE_TMP_DIR='$REMOTE_TMP_DIR' REMOTE_KLIPPER_DIR='$REMOTE_KLIPPER_DIR' REMOTE_CONFIG_DIR='$REMOTE_CONFIG_DIR' REMOTE_MANAGED_STATE='$REMOTE_MANAGED_STATE' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
HOST_OVERLAY="$REMOTE_TMP_DIR/klipper_host/klippy"
RUNTIME_HELPERS="$REMOTE_TMP_DIR/runtime_helpers"
OUTSIDE_CLIENT="$REMOTE_TMP_DIR/mege_outside"
CFG="$REMOTE_TMP_DIR/printer.cfg"
COMMIT_FILE="$REMOTE_TMP_DIR/KLIPPER_COMMIT"
HOST_MANIFEST="$REMOTE_TMP_DIR/host.manifest"
RUNTIME_MANIFEST="$REMOTE_TMP_DIR/runtime.manifest"
OUTSIDE_MANIFEST="$REMOTE_TMP_DIR/outside.manifest"
MAIN_CFG="$REMOTE_CONFIG_DIR/printer.cfg"
BACKUP_ROOT="$HOME/printer_data/backup/klipperpi-update-$(date +%Y%m%d-%H%M%S)"

manifest_tree() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path
root = Path(sys.argv[1])
for path in sorted(root.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
        relative = path.relative_to(root)
        print(f"{relative.as_posix()}\t{hashlib.sha256(path.read_bytes()).hexdigest()}")
PY
}
[ -d "$HOST_OVERLAY" ] && [ -d "$RUNTIME_HELPERS" ] && [ -d "$OUTSIDE_CLIENT" ] && [ -f "$CFG" ] && [ -f "$COMMIT_FILE" ] || {
  echo "Staged deployment bundle is incomplete" >&2
  exit 1
}
cmp -s "$HOST_MANIFEST" <(manifest_tree "$HOST_OVERLAY") || { echo "Host manifest mismatch" >&2; exit 1; }
cmp -s "$RUNTIME_MANIFEST" <(manifest_tree "$RUNTIME_HELPERS") || { echo "Runtime manifest mismatch" >&2; exit 1; }
cmp -s "$OUTSIDE_MANIFEST" <(manifest_tree "$OUTSIDE_CLIENT") || { echo "Outside-client manifest mismatch" >&2; exit 1; }
COMMIT=$(tr -d '[:space:]' < "$COMMIT_FILE")
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid shared Klipper commit" >&2; exit 1; }
[ "$(git -C "$REMOTE_KLIPPER_DIR" rev-parse HEAD)" = "$COMMIT" ] || {
  echo "Remote Klipper checkout does not match shared pin" >&2
  exit 1
}

python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen(
    "http://127.0.0.1:7125/printer/objects/query?webhooks&print_stats&heater_bed&virtual_sdcard",
    timeout=10,
) as response:
    status = json.loads(response.read())["result"]["status"]
webhooks = status.get("webhooks", {})
if webhooks.get("state") == "ready":
    if status.get("print_stats", {}).get("state") not in {"standby", "complete", "cancelled", "error"}:
        raise SystemExit("Refusing deployment while a print is active")
    if status.get("virtual_sdcard", {}).get("is_active", False):
        raise SystemExit("Refusing deployment while virtual SD is active")
    if status.get("heater_bed", {}).get("target", 0.0) not in {0, 0.0}:
        raise SystemExit("Refusing deployment while bed heater is active")
elif webhooks.get("state") == "error":
    print("Klippy is in config/error state; allowing recovery deployment")
else:
    raise SystemExit(f"Refusing deployment with unverified Klippy state={webhooks.get('state')!r}")
PY

sudo install -d -m 0755 "$BACKUP_ROOT/host" "$BACKUP_ROOT/runtime" "$REMOTE_CONFIG_DIR" "$(dirname -- "$REMOTE_MANAGED_STATE")"
if [ -f "$MAIN_CFG" ]; then sudo cp -a "$MAIN_CFG" "$BACKUP_ROOT/printer.cfg"; fi
sudo install -m 0644 "$CFG" "$MAIN_CFG"
echo "Installed printer.cfg -> $MAIN_CFG"

sudo python3 - "$REMOTE_MANAGED_STATE" "$HOST_OVERLAY" "$RUNTIME_HELPERS" "$OUTSIDE_CLIENT" "$BACKUP_ROOT" "$REMOTE_KLIPPER_DIR" "$REMOTE_CONFIG_DIR" <<'PY'
import hashlib
import json
import shutil
import sys
from pathlib import Path
state_path, host_source, runtime_source, outside_source, backup_root, host_target, runtime_target = map(Path, sys.argv[1:])
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def safe_join(root, relative):
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise SystemExit(f"managed path escapes target: {relative}")
    return path
def read_manifest(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            relative, checksum = line.split("\t", 1)
            result[relative] = checksum
    return result
def outside_target(relative):
    targets = {
        "mege-outside-enroll.sh": Path("/usr/local/sbin/mege-outside-enroll"),
        "mege-outside-activate.sh": Path("/usr/local/sbin/mege-outside-activate"),
        "mege.conf.template": Path("/usr/local/share/mege-outside/mege.conf.template"),
        "mege-printer-tunnel.service": Path("/etc/systemd/system/mege-printer-tunnel.service"),
    }
    try:
        return targets[relative]
    except KeyError:
        raise SystemExit(f"unsupported outside-client path: {relative}")
try:
    old_state = json.loads(state_path.read_text(encoding="utf-8"))
except FileNotFoundError:
    old_state = {}
new_state = {
    "version": 2,
    "host": read_manifest(host_source.parent.parent / "host.manifest"),
    "runtime": read_manifest(runtime_source.parent / "runtime.manifest"),
    "outside": read_manifest(outside_source.parent / "outside.manifest"),
}
for section, target in (("host", host_target), ("runtime", runtime_target)):
    for relative, checksum in old_state.get(section, {}).items():
        if relative in new_state[section]:
            continue
        target_path = safe_join(target, relative)
        if not target_path.exists():
            continue
        if not target_path.is_file() or digest(target_path) != checksum:
            raise SystemExit(f"refusing to prune modified managed {section} path: {relative}")
        backup = safe_join(backup_root / section, relative)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, backup)
        target_path.unlink()
        print(f"Pruned retired {section} path: {relative}")
for relative, checksum in old_state.get("outside", {}).items():
    if relative in new_state["outside"]:
        continue
    target_path = outside_target(relative)
    if not target_path.exists():
        continue
    if not target_path.is_file() or digest(target_path) != checksum:
        raise SystemExit(f"refusing to prune modified outside-client path: {relative}")
    backup = safe_join(backup_root / "outside", relative)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_path, backup)
    target_path.unlink()
    print(f"Pruned retired outside-client path: {relative}")
state_tmp = backup_root / "managed-overlay.json"
state_tmp.write_text(json.dumps(new_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

sudo rsync -a --checksum --backup --backup-dir="$BACKUP_ROOT/host" \
  --exclude '__pycache__/' --exclude '*.pyc' "$HOST_OVERLAY/" "$REMOTE_KLIPPER_DIR/"
sudo rsync -a --checksum --backup --backup-dir="$BACKUP_ROOT/runtime" \
  --exclude '__pycache__/' --exclude '*.pyc' "$RUNTIME_HELPERS/" "$REMOTE_CONFIG_DIR/"
sudo install -d -m 0755 /usr/local/share/mege-outside
sudo install -m 0755 "$OUTSIDE_CLIENT/mege-outside-enroll.sh" /usr/local/sbin/mege-outside-enroll
sudo install -m 0755 "$OUTSIDE_CLIENT/mege-outside-activate.sh" /usr/local/sbin/mege-outside-activate
sudo install -m 0644 "$OUTSIDE_CLIENT/mege.conf.template" /usr/local/share/mege-outside/mege.conf.template
sudo install -m 0644 "$OUTSIDE_CLIENT/mege-printer-tunnel.service" /etc/systemd/system/mege-printer-tunnel.service
sudo systemctl daemon-reload
sudo install -m 0644 "$BACKUP_ROOT/managed-overlay.json" "$REMOTE_MANAGED_STATE"
echo "Installed klipper_host/klippy/ -> $REMOTE_KLIPPER_DIR/"
echo "Installed runtime_helpers/ -> $REMOTE_CONFIG_DIR/"
echo "Installed mege_outside/ enrollment, activation, and tunnel units"
echo "Managed backups -> $BACKUP_ROOT"

sudo systemctl restart klipper
python3 - <<'PY'
import json
import time
import urllib.request
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen("http://127.0.0.1:7125/printer/objects/query?webhooks", timeout=5) as response:
            status = json.loads(response.read())["result"]["status"]
        if status.get("webhooks", {}).get("state") == "ready":
            print("Klippy reached ready state.")
            break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit("Klippy did not reach ready state after restart")
PY
REMOTE_SCRIPT

echo "Verifying deployed directory bundles..."
check_live_config
echo "Deploying the tracked installed-file overlay..."
MENDERPI_HOST="$REMOTE_HOST" bash "$SCRIPT_DIR/deploy_installed_overlay.sh"
echo "Deploying the multi-head-zero calibration dashboard..."
MENDERPI_HOST="$REMOTE_HOST" bash "$SCRIPT_DIR/deploy_multi_head_zero_calibration_dashboard.sh"
echo "Deploying the Eddy tap trace dashboard..."
MENDERPI_HOST="$REMOTE_HOST" bash "$SCRIPT_DIR/deploy_eddy_tap_dashboard.sh"
echo "Deploying the complete tracked vision code set..."
MENDERPI_HOST="$REMOTE_HOST" "$SCRIPT_DIR/deploy_vision_code.sh"
if [ "$MODE" = outside_enroll ]; then
  if ! ssh "$REMOTE_HOST" "command -v wg >/dev/null 2>&1"; then
    echo "Installing the required wireguard-tools package on $REMOTE_HOST..."
    ssh "$REMOTE_HOST" "sudo -n apt-get update && sudo -n apt-get install -y --no-install-recommends wireguard-tools"
  fi
  echo "Creating or reusing the printer's Mege outside key pairs..."
  ssh "$REMOTE_HOST" "sudo -n /usr/local/sbin/mege-outside-enroll"
fi
echo "Update complete."
