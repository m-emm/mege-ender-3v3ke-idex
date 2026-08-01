#!/usr/bin/env python3
"""Probe webcam preview health.

The probe intentionally measures the Mainsail-facing MJPEG preview path. It
works with both the RAM-buffered still-frame service and the older uStreamer
preview path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CAMERA_DEVICE = (
    "/dev/v4l/by-id/" "usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0"
)


def run_command(command: list[str], *, timeout: float = 10.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def read_url(url: str, *, timeout: float = 3.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def read_json_url(url: str, *, timeout: float = 3.0) -> dict[str, Any]:
    return json.loads(read_url(url, timeout=timeout))


def sample_snapshot(url: str, timeout: float) -> dict[str, Any]:
    start = time.monotonic()
    try:
        data = read_url(url, timeout=timeout)
        elapsed = time.monotonic() - start
        return {
            "ok": data[:2] == b"\xff\xd8",
            "elapsed_s": round(elapsed, 4),
            "size_bytes": len(data),
            "jpeg": data[:2] == b"\xff\xd8",
        }
    except Exception as exc:
        elapsed = time.monotonic() - start
        return {"ok": False, "elapsed_s": round(elapsed, 4), "error": str(exc)}


def start_stream_client(url: str, output_path: Path, duration: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "curl",
            "-sS",
            "--max-time",
            str(duration + 3),
            "-o",
            str(output_path),
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def collect_usb_path(camera_device: str) -> dict[str, Any]:
    path = run_command(["readlink", "-f", camera_device], timeout=5)
    udev_path = run_command(
        ["udevadm", "info", "-q", "path", "-n", camera_device], timeout=5
    )
    return {
        "device": camera_device,
        "resolved": path.get("stdout"),
        "udev_path": udev_path.get("stdout"),
    }


def collect_process_snapshot() -> dict[str, Any]:
    return {
        "services": run_command(
            [
                "systemctl",
                "is-active",
                "vision-framebuffer",
                "vision-framebuffer-nozzle-cam",
                "nginx",
                "moonraker",
                "vision-capture",
                "vision-capture-nozzle-cam",
            ],
            timeout=10,
        ),
        "load": run_command(["uptime"], timeout=5),
        "throttled": run_command(["vcgencmd", "get_throttled"], timeout=5),
        "temperature": run_command(["vcgencmd", "measure_temp"], timeout=5),
        "vision_framebuffer_processes": run_command(
            [
                "sh",
                "-c",
                "ps -o pid,ppid,pcpu,pmem,stat,etime,args -p $(pgrep -f 'vision_framebuffer.py' | paste -sd, -)",
            ],
            timeout=5,
        ),
    }


def collect_recent_uvc_messages() -> list[str]:
    result = run_command(["dmesg", "--ctime"], timeout=10)
    if not result.get("ok"):
        return []
    pattern = re.compile(
        r"usb|uvc|video|reset|resubmit|bandwidth|thrott|under-voltage", re.I
    )
    return [
        line for line in result.get("stdout", "").splitlines() if pattern.search(line)
    ][-80:]


def consecutive_zero_count(samples: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    for sample in samples:
        fps = sample.get("captured_fps")
        if fps == 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return round(ordered[index], 4)


def probe(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    stream_output = output_dir / "webcam_health_stream_probe.mjpg"
    if stream_output.exists():
        stream_output.unlink()

    result: dict[str, Any] = {
        "ok": False,
        "timestamp_utc": timestamp.isoformat(),
        "duration_s": args.duration,
        "state_url": args.state_url,
        "stream_url": args.stream_url,
        "snapshot_url": args.snapshot_url,
        "camera": collect_usb_path(args.camera_device),
        "process_before": collect_process_snapshot(),
        "uvc_messages_before": collect_recent_uvc_messages(),
        "state_samples": [],
        "snapshot_samples": [],
    }

    stream_proc = start_stream_client(args.stream_url, stream_output, args.duration)
    try:
        deadline = time.monotonic() + args.duration
        next_snapshot = 0.0
        while time.monotonic() < deadline:
            sample_time = datetime.now(timezone.utc).isoformat()
            sample: dict[str, Any] = {"timestamp_utc": sample_time}
            try:
                state = read_json_url(args.state_url, timeout=1.5)
                result_state = state.get("result", {})
                source = (
                    result_state.get("framebuffer") or result_state.get("source") or {}
                )
                stream = state.get("result", {}).get("stream", {})
                sample.update(
                    {
                        "ok": bool(source.get("ok", state.get("ok"))),
                        "captured_fps": source.get("captured_fps"),
                        "queued_fps": stream.get("queued_fps"),
                        "clients": stream.get("clients"),
                        "last_frame_age_s": source.get("last_frame_age_s"),
                    }
                )
            except Exception as exc:
                sample.update({"ok": False, "error": str(exc)})
            result["state_samples"].append(sample)

            now = time.monotonic()
            if now >= next_snapshot:
                result["snapshot_samples"].append(
                    sample_snapshot(args.snapshot_url, args.snapshot_timeout)
                )
                next_snapshot = now + args.snapshot_interval
            time.sleep(args.sample_interval)
    finally:
        try:
            stdout, stderr = stream_proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stream_proc.kill()
            stdout, stderr = stream_proc.communicate(timeout=5)

    stream_size = stream_output.stat().st_size if stream_output.exists() else 0
    samples = result["state_samples"]
    captured_values = [
        float(s["captured_fps"])
        for s in samples
        if isinstance(s.get("captured_fps"), (int, float))
    ]
    queued_values = [
        float(s["queued_fps"])
        for s in samples
        if isinstance(s.get("queued_fps"), (int, float))
    ]
    snapshot_times = [
        float(s["elapsed_s"])
        for s in result["snapshot_samples"]
        if s.get("ok") and isinstance(s.get("elapsed_s"), (int, float))
    ]
    evaluated_samples = samples[args.ignore_initial_samples :]
    evaluated_captured_values = [
        float(s["captured_fps"])
        for s in evaluated_samples
        if isinstance(s.get("captured_fps"), (int, float))
    ]
    zero_samples = sum(1 for v in evaluated_captured_values if v == 0)
    longest_zero_run = consecutive_zero_count(evaluated_samples)

    result.update(
        {
            "stream_client": {
                "returncode": stream_proc.returncode,
                "stderr": (stderr or "").strip(),
                "stdout": (stdout or "").strip(),
                "bytes": stream_size,
                "bytes_per_second": round(stream_size / max(1, args.duration), 1),
            },
            "summary": {
                "sample_count": len(samples),
                "captured_fps_min": min(captured_values) if captured_values else None,
                "captured_fps_median": percentile(
                    [float(v) for v in captured_values], 0.5
                ),
                "queued_fps_median": percentile([float(v) for v in queued_values], 0.5),
                "zero_captured_samples": zero_samples,
                "longest_zero_captured_run": longest_zero_run,
                "snapshot_p95_s": percentile(snapshot_times, 0.95),
                "snapshot_max_s": max(snapshot_times) if snapshot_times else None,
                "ignored_initial_samples": args.ignore_initial_samples,
                "evaluated_sample_count": len(evaluated_samples),
            },
            "process_after": collect_process_snapshot(),
            "uvc_messages_after": collect_recent_uvc_messages(),
        }
    )

    summary = result["summary"]
    result["ok"] = (
        stream_size >= args.min_stream_bytes
        and summary["longest_zero_captured_run"] <= args.max_consecutive_zero
        and summary["zero_captured_samples"] <= args.max_zero_samples
        and (summary["queued_fps_median"] or 0) >= args.min_median_queued_fps
        and (
            summary["snapshot_p95_s"] is None
            or summary["snapshot_p95_s"] <= args.max_snapshot_p95
        )
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--snapshot-interval", type=float, default=5.0)
    parser.add_argument("--snapshot-timeout", type=float, default=5.0)
    parser.add_argument("--state-url", default="http://127.0.0.1:8080/state")
    parser.add_argument("--stream-url", default="http://127.0.0.1:8080/?action=stream")
    parser.add_argument(
        "--snapshot-url", default="http://127.0.0.1/webcam/?action=snapshot"
    )
    parser.add_argument(
        "--camera-device",
        default=os.environ.get("VISION_CAMERA_DEVICE", DEFAULT_CAMERA_DEVICE),
    )
    parser.add_argument("--output-dir", default="/tmp")
    parser.add_argument("--min-stream-bytes", type=int, default=250_000)
    parser.add_argument("--min-median-queued-fps", type=float, default=12.0)
    parser.add_argument("--max-zero-samples", type=int, default=1)
    parser.add_argument("--max-consecutive-zero", type=int, default=1)
    parser.add_argument("--ignore-initial-samples", type=int, default=0)
    parser.add_argument("--max-snapshot-p95", type=float, default=0.5)
    parser.add_argument("--json-output", metavar="PATH")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()

    result = probe(args)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(text)
    print(text, end="")
    return 0 if result.get("ok") or args.no_fail else 1


if __name__ == "__main__":
    sys.exit(main())
