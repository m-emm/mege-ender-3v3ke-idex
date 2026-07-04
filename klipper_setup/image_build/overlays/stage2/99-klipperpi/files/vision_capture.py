#!/usr/bin/env python3
"""High-resolution camera capture bridge for Klipper vision work.

The daemon mode registers a Klipper remote method named ``vision_capture``.
Klipper macros can call it with ``action_call_remote_method`` without blocking
the printer motion queue on the actual image capture.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAMERA_DEVICE = os.environ.get(
    "VISION_CAMERA_DEVICE",
    "/dev/v4l/by-id/usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0",
)
OUTPUT_DIR = Path(os.environ.get("VISION_OUTPUT_DIR", "/home/pi/printer_data/vision"))
KLIPPY_SOCKET = os.environ.get(
    "VISION_KLIPPY_SOCKET", "/home/pi/printer_data/comms/klippy.sock"
)
CROWSNEST_SERVICE = os.environ.get("VISION_CROWSNEST_SERVICE", "crowsnest")
REMOTE_METHOD = "vision_capture"
REMOTE_ACTION = "run_vision_capture"
CAPTURE_RESOLUTIONS = ((1920, 1080), (1280, 720))
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class CaptureError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} {message}", flush=True)


def run_command(command: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def sanitize_name(name: Any) -> str:
    cleaned = NAME_RE.sub("_", str(name or "capture")).strip("._-")
    return (cleaned or "capture")[:80]


def service_is_active(service: str) -> bool:
    result = run_command(["systemctl", "is-active", "--quiet", service], timeout=5)
    return result.returncode == 0


def stop_service(service: str) -> None:
    result = run_command(["systemctl", "stop", service], timeout=15)
    if result.returncode != 0:
        raise CaptureError(f"Could not stop {service}: {result.stderr.strip()}")


def start_service(service: str) -> None:
    result = run_command(["systemctl", "start", service], timeout=15)
    if result.returncode != 0:
        raise CaptureError(f"Could not start {service}: {result.stderr.strip()}")


def verify_jpeg(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise CaptureError(f"{path} is not a JPEG frame")


def capture_with_resolution(device: str, image_path: Path, width: int, height: int) -> dict[str, Any]:
    fmt = f"width={width},height={height},pixelformat=MJPG"
    warmup = run_command(
        [
            "v4l2-ctl",
            "-d",
            device,
            f"--set-fmt-video={fmt}",
            "--stream-mmap",
            "--stream-count=3",
            "--stream-to=/dev/null",
        ],
        timeout=20,
    )
    capture = run_command(
        [
            "v4l2-ctl",
            "-d",
            device,
            f"--set-fmt-video={fmt}",
            "--stream-mmap",
            "--stream-count=1",
            f"--stream-to={image_path}",
        ],
        timeout=20,
    )
    if capture.returncode != 0:
        raise CaptureError(
            "v4l2 capture failed "
            f"at {width}x{height}: {capture.stderr.strip() or capture.stdout.strip()}"
        )
    verify_jpeg(image_path)
    return {
        "width": width,
        "height": height,
        "warmup_stdout": warmup.stdout.strip(),
        "warmup_stderr": warmup.stderr.strip(),
        "capture_stdout": capture.stdout.strip(),
        "capture_stderr": capture.stderr.strip(),
    }


def update_latest_symlinks(image_path: Path, metadata_path: Path) -> None:
    for source, latest_name in (
        (image_path, "latest.jpg"),
        (metadata_path, "latest.json"),
    ):
        latest = OUTPUT_DIR / latest_name
        tmp = OUTPUT_DIR / f".{latest_name}.tmp"
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        os.symlink(source.name, tmp)
        os.replace(tmp, latest)


def capture_frame(params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc)
    timestamp_name = timestamp.strftime("%Y%m%dT%H%M%SZ")
    requested_name = sanitize_name(params.get("name"))
    image_path = OUTPUT_DIR / f"{timestamp_name}_{requested_name}.jpg"
    metadata_path = OUTPUT_DIR / f"{timestamp_name}_{requested_name}.json"
    tmp_path = image_path.with_suffix(".jpg.tmp")
    crowsnest_was_active = service_is_active(CROWSNEST_SERVICE)

    metadata: dict[str, Any] = {
        "timestamp_utc": timestamp.isoformat(),
        "requested_name": requested_name,
        "params": params,
        "camera_device": CAMERA_DEVICE,
        "crowsnest_service": CROWSNEST_SERVICE,
        "crowsnest_was_active": crowsnest_was_active,
        "attempts": [],
    }

    try:
        if crowsnest_was_active:
            log(f"Stopping {CROWSNEST_SERVICE} for exclusive high-res capture")
            stop_service(CROWSNEST_SERVICE)
            time.sleep(0.5)

        last_error: Exception | None = None
        for width, height in CAPTURE_RESOLUTIONS:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
                attempt = capture_with_resolution(CAMERA_DEVICE, tmp_path, width, height)
                metadata["attempts"].append({"ok": True, **attempt})
                os.replace(tmp_path, image_path)
                metadata.update(
                    {
                        "ok": True,
                        "image_path": str(image_path),
                        "metadata_path": str(metadata_path),
                        "url": f"/vision/{image_path.name}",
                        "latest_url": "/vision/latest.jpg",
                        "width": width,
                        "height": height,
                        "size_bytes": image_path.stat().st_size,
                    }
                )
                break
            except Exception as exc:
                last_error = exc
                metadata["attempts"].append(
                    {"ok": False, "width": width, "height": height, "error": str(exc)}
                )
        else:
            raise CaptureError(f"All capture resolutions failed: {last_error}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        if crowsnest_was_active:
            try:
                log(f"Restarting {CROWSNEST_SERVICE} after high-res capture")
                start_service(CROWSNEST_SERVICE)
            except Exception as exc:
                metadata["crowsnest_restart_error"] = str(exc)

    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    update_latest_symlinks(image_path, metadata_path)
    log(f"Captured high-res frame: {image_path}")
    return metadata


class KlippyRemoteCaptureDaemon:
    def __init__(self) -> None:
        self.capture_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=20)
        self.worker = threading.Thread(target=self._capture_worker, daemon=True)
        self.next_id = 1

    def _capture_worker(self) -> None:
        while True:
            params = self.capture_queue.get()
            try:
                capture_frame(params)
            except Exception as exc:
                log(f"Capture request failed: {exc}")
            finally:
                self.capture_queue.task_done()

    def _send(self, sock: socket.socket, payload: dict[str, Any]) -> None:
        sock.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\x03")

    def _register(self, sock: socket.socket) -> None:
        request_id = self.next_id
        self.next_id += 1
        self._send(
            sock,
            {
                "id": request_id,
                "method": "register_remote_method",
                "params": {
                    "remote_method": REMOTE_METHOD,
                    "response_template": {"action": REMOTE_ACTION},
                },
            },
        )
        log(f"Registered Klipper remote method: {REMOTE_METHOD}")

    def _handle_message(self, message: dict[str, Any]) -> None:
        if message.get("action") != REMOTE_ACTION:
            return
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {"raw_params": params}
        try:
            self.capture_queue.put_nowait(params)
            log(f"Queued vision capture request: {params}")
        except queue.Full:
            log("Capture queue is full; dropping request")

    def run(self) -> None:
        self.worker.start()
        while True:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.connect(KLIPPY_SOCKET)
                    self._register(sock)
                    buffer = b""
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            raise ConnectionError("Klippy socket closed")
                        buffer += chunk
                        messages = buffer.split(b"\x03")
                        buffer = messages.pop()
                        for raw in messages:
                            if not raw:
                                continue
                            self._handle_message(json.loads(raw.decode()))
            except Exception as exc:
                log(f"Klipper remote-method bridge disconnected: {exc}")
                time.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--capture-once", metavar="NAME")
    args = parser.parse_args()

    if args.capture_once:
        metadata = capture_frame({"name": args.capture_once, "reason": "capture_once"})
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0
    if args.daemon:
        KlippyRemoteCaptureDaemon().run()
        return 0

    parser.error("use --daemon or --capture-once NAME")
    return 2


if __name__ == "__main__":
    sys.exit(main())
