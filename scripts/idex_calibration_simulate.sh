#!/usr/bin/env bash
# Deterministic event API for the local IDEX calibration dashboard simulator.
set -euo pipefail

BASE_URL="http://127.0.0.1:8787"

usage() {
    cat <<'EOF'
Usage: scripts/idex_calibration_simulate.sh [--port PORT] <event> [arguments]

Events:
  reset
  scenario <name>
  start <full|bed_reference|tool_alignment|mesh_refresh>
  step <1..7> [operation text]
  progress <completed>/<total>
  heartbeat
  complete-step <1..7>
  complete-chapter <bed_reference|tool_alignment|mesh>
  fail-step <1..7> <reason>
  restart [full|bed_reference|tool_alignment|mesh_refresh]
  set-heartbeat-age <seconds>
  set-printer <ready|not_homed|error>

The simulator must already be running. This command only posts to 127.0.0.1.
EOF
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --port)
            BASE_URL="http://127.0.0.1:${2:?--port requires a value}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *) break ;;
    esac
done

[[ "$#" -gt 0 ]] || { usage >&2; exit 2; }
event="$1"
shift

python3 - "$BASE_URL" "$event" "$@" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base, event, *args = sys.argv[1:]
payload = {"action": event}
if event == "scenario":
    payload["name"] = args[0]
elif event == "start":
    payload["scope"] = args[0]
elif event == "step":
    payload["number"] = int(args[0])
    if len(args) > 1:
        payload["operation"] = " ".join(args[1:])
elif event == "progress":
    completed, total = args[0].split("/", 1)
    payload.update(completed=int(completed), total=int(total))
elif event == "complete-step":
    payload["number"] = int(args[0])
elif event == "complete-chapter":
    payload["chapter"] = args[0]
elif event == "fail-step":
    payload["number"] = int(args[0])
    payload["reason"] = " ".join(args[1:])
elif event == "restart":
    if args:
        payload["scope"] = args[0]
elif event == "set-heartbeat-age":
    payload["seconds"] = int(args[0])
elif event == "set-printer":
    payload["state"] = args[0]
elif event in {"reset", "heartbeat"}:
    pass
else:
    raise SystemExit(f"Unknown event: {event}")

request = urllib.request.Request(
    base.rstrip("/") + "/__sim__/event",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        print(json.dumps(json.load(response), indent=2))
except urllib.error.HTTPError as exc:
    print(exc.read().decode(errors="replace"), file=sys.stderr)
    raise SystemExit(exc.code)
except urllib.error.URLError as exc:
    raise SystemExit(f"Cannot reach local simulator at {base}: {exc.reason}")
PY
