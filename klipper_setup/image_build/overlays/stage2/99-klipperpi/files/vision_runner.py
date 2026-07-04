#!/usr/bin/env python3
"""Moonraker-side helper for future vision-in-the-loop routines."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"


def moonraker_get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=15) as response:
        return json.loads(response.read())


def run_gcode(base_url: str, script: str) -> None:
    data = urllib.parse.urlencode({"script": script}).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/printer/gcode/script",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        response.read()


def wait_ready(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = moonraker_get(base_url, "/printer/objects/query?webhooks")["result"][
            "status"
        ]
        if status.get("webhooks", {}).get("state") == "ready":
            return
        time.sleep(0.5)
    raise TimeoutError("Klippy did not become ready")


def capture_once(name: str) -> dict:
    result = subprocess.run(
        ["/usr/local/bin/vision_capture.py", "--capture-once", name],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moonraker-url", default=DEFAULT_MOONRAKER_URL)
    parser.add_argument("--gcode-before")
    parser.add_argument("--gcode-after")
    parser.add_argument("--capture-name", default="vision_runner")
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    args = parser.parse_args()

    wait_ready(args.moonraker_url, args.ready_timeout)
    if args.gcode_before:
        run_gcode(args.moonraker_url, args.gcode_before)
    metadata = capture_once(args.capture_name)
    if args.gcode_after:
        run_gcode(args.moonraker_url, args.gcode_after)
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
