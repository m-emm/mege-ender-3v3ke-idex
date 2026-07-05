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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAMERA_DEVICE = os.environ.get(
    "VISION_CAMERA_DEVICE",
    "/dev/v4l/by-id/usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0",
)
OUTPUT_DIR = Path(os.environ.get("VISION_OUTPUT_DIR", "/home/pi/printer_data/vision"))
FRAMEBUFFER_DIR = Path(os.environ.get("VISION_FRAMEBUFFER_DIR", "/run/vision-preview"))
FRAMEBUFFER_LATEST_IMAGE = FRAMEBUFFER_DIR / "latest.jpg"
FRAMEBUFFER_LATEST_METADATA = FRAMEBUFFER_DIR / "latest.json"
KLIPPY_SOCKET = os.environ.get(
    "VISION_KLIPPY_SOCKET", "/home/pi/printer_data/comms/klippy.sock"
)
CROWSNEST_SERVICE = os.environ.get("VISION_CROWSNEST_SERVICE", "crowsnest")
WEBCAM_SNAPSHOT_URL = os.environ.get(
    "VISION_WEBCAM_SNAPSHOT_URL", "http://127.0.0.1/webcam/?action=snapshot"
)
CROWSNEST_HOST = os.environ.get("VISION_CROWSNEST_HOST", "127.0.0.1")
CROWSNEST_PORT = int(os.environ.get("VISION_CROWSNEST_PORT", "8080"))
WEBCAM_READY_TIMEOUT = float(os.environ.get("VISION_WEBCAM_READY_TIMEOUT", "25"))
REMOTE_METHOD = "vision_capture"
REMOTE_ACTION = "run_vision_capture"
NOZZLE_ALIGN_REMOTE_METHOD = "idex_nozzle_vision_check"
NOZZLE_ALIGN_REMOTE_ACTION = "run_idex_nozzle_vision_check"
NOZZLE_SWEEP_REMOTE_METHOD = "idex_nozzle_vision_sweep"
NOZZLE_SWEEP_REMOTE_ACTION = "run_idex_nozzle_vision_sweep"
NOZZLE_ALIGN_BIN = os.environ.get(
    "VISION_NOZZLE_ALIGN_BIN", "/usr/local/bin/vision_nozzle_align.py"
)
CAPTURE_RESOLUTIONS = ((1920, 1080), (1280, 720))
DEFAULT_CAPTURE_RETRIES = int(os.environ.get("VISION_CAPTURE_RETRIES", "3"))
HIGH_RES_MIN_WIDTH = int(os.environ.get("VISION_HIGH_RES_MIN_WIDTH", "1920"))
HIGH_RES_MIN_HEIGHT = int(os.environ.get("VISION_HIGH_RES_MIN_HEIGHT", "1080"))
DEFAULT_FRAME_FRESH_TIMEOUT = float(os.environ.get("VISION_FRAME_FRESH_TIMEOUT", "10"))
DEFAULT_FRAME_MAX_AGE = float(os.environ.get("VISION_FRAME_MAX_AGE", "10"))
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class CaptureError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} {message}", file=sys.stderr, flush=True)


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


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def service_is_active(service: str) -> bool:
    result = run_command(["systemctl", "is-active", "--quiet", service], timeout=5)
    return result.returncode == 0


def stop_service(service: str) -> None:
    result = run_command(["systemctl", "stop", service], timeout=15)
    if result.returncode != 0:
        raise CaptureError(f"Could not stop {service}: {result.stderr.strip()}")


def reset_failed_service(service: str) -> None:
    run_command(["systemctl", "reset-failed", service], timeout=10)


def wait_for_tcp(host: str, port: int, timeout: float) -> float:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return round(timeout - max(0.0, deadline - time.monotonic()), 3)
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    raise CaptureError(f"Timed out waiting for {host}:{port}: {last_error}")


def wait_for_webcam_snapshot(timeout: float) -> float:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(WEBCAM_SNAPSHOT_URL, timeout=3) as response:
                data = response.read(4)
            if data[:2] == b"\xff\xd8":
                return round(timeout - max(0.0, deadline - time.monotonic()), 3)
            last_error = CaptureError("snapshot endpoint did not return a JPEG")
        except Exception as exc:
            last_error = exc
        time.sleep(0.75)
    raise CaptureError(f"Timed out waiting for webcam snapshot: {last_error}")


def start_service(service: str, *, wait_for_webcam: bool = False) -> dict[str, Any]:
    reset_failed_service(service)
    result = run_command(["systemctl", "start", service], timeout=15)
    if result.returncode != 0:
        raise CaptureError(f"Could not start {service}: {result.stderr.strip()}")
    readiness: dict[str, Any] = {}
    if wait_for_webcam:
        readiness["tcp_ready_after_s"] = wait_for_tcp(
            CROWSNEST_HOST, CROWSNEST_PORT, WEBCAM_READY_TIMEOUT
        )
        readiness["snapshot_ready_after_s"] = wait_for_webcam_snapshot(
            WEBCAM_READY_TIMEOUT
        )
    return readiness


def verify_jpeg(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise CaptureError(f"{path} is not a JPEG frame")


def jpeg_dimensions(path: Path) -> tuple[int | None, int | None]:
    data = path.read_bytes()
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC2):
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        segment_length = int.from_bytes(data[i + 2 : i + 4], "big")
        if segment_length < 2:
            break
        i += 2 + segment_length
    return None, None


def parse_utc_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_framebuffer_metadata() -> dict[str, Any]:
    return json.loads(FRAMEBUFFER_LATEST_METADATA.read_text())


def wait_for_buffered_frame(
    *,
    fresh_after_utc: datetime | None,
    timeout: float,
    max_age: float,
) -> tuple[Path, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if not FRAMEBUFFER_LATEST_IMAGE.exists():
                raise CaptureError(f"{FRAMEBUFFER_LATEST_IMAGE} does not exist")
            if not FRAMEBUFFER_LATEST_METADATA.exists():
                raise CaptureError(f"{FRAMEBUFFER_LATEST_METADATA} does not exist")
            metadata = read_framebuffer_metadata()
            frame_time = parse_utc_timestamp(metadata.get("timestamp_utc"))
            if frame_time is None:
                raise CaptureError("buffered frame metadata has no timestamp_utc")
            if fresh_after_utc is not None and frame_time <= fresh_after_utc:
                last_error = CaptureError(
                    "latest buffered frame is older than requested freshness point"
                )
                time.sleep(0.1)
                continue
            age = (datetime.now(timezone.utc) - frame_time).total_seconds()
            if age > max_age:
                last_error = CaptureError(
                    f"latest buffered frame is stale: {age:.3f}s > {max_age:.3f}s"
                )
                time.sleep(0.1)
                continue
            verify_jpeg(FRAMEBUFFER_LATEST_IMAGE)
            return FRAMEBUFFER_LATEST_IMAGE, metadata
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise CaptureError(f"Timed out waiting for buffered frame: {last_error}")


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


def capture_with_opencv_resolution(
    device: str, image_path: Path, width: int, height: int
) -> dict[str, Any]:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on Pi package install
        raise CaptureError(f"OpenCV import failed: {exc}") from exc

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    try:
        if not cap.isOpened():
            raise CaptureError(f"OpenCV could not open {device}")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 5)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_width = int(round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        actual_height = int(round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        actual_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        frame = None
        frames_read = 0
        for _ in range(8):
            ok, candidate = cap.read()
            if ok and candidate is not None:
                frame = candidate
                frames_read += 1
            time.sleep(0.08)
        if frame is None:
            raise CaptureError(f"OpenCV produced no decoded frame at {width}x{height}")

        frame_height, frame_width = frame.shape[:2]
        if frame_width < width or frame_height < height:
            raise CaptureError(
                "OpenCV decoded lower resolution than requested: "
                f"{frame_width}x{frame_height}, requested {width}x{height}"
            )
        ok, encoded = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        )
        if not ok:
            raise CaptureError("OpenCV could not encode JPEG frame")
        image_path.write_bytes(encoded.tobytes())
        verify_jpeg(image_path)
        return {
            "source": "opencv_v4l2_mjpg",
            "requested_width": width,
            "requested_height": height,
            "width": frame_width,
            "height": frame_height,
            "actual_width": actual_width,
            "actual_height": actual_height,
            "actual_fourcc": actual_fourcc,
            "frames_read": frames_read,
        }
    finally:
        cap.release()


def capture_from_webcam_snapshot(image_path: Path) -> dict[str, Any]:
    with urllib.request.urlopen(WEBCAM_SNAPSHOT_URL, timeout=20) as response:
        image_path.write_bytes(response.read())
    verify_jpeg(image_path)
    width, height = jpeg_dimensions(image_path)
    return {
        "source": "webcam_snapshot",
        "url": WEBCAM_SNAPSHOT_URL,
        "width": width,
        "height": height,
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
    require_high_res = bool(params.get("require_high_res"))
    fresh = as_bool(params.get("fresh"), True)
    fresh_timeout = float(params.get("fresh_timeout") or DEFAULT_FRAME_FRESH_TIMEOUT)
    max_age = float(params.get("max_age") or DEFAULT_FRAME_MAX_AGE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc)
    timestamp_name = timestamp.strftime("%Y%m%dT%H%M%SZ")
    requested_name = sanitize_name(params.get("name"))
    image_path = OUTPUT_DIR / f"{timestamp_name}_{requested_name}.jpg"
    metadata_path = OUTPUT_DIR / f"{timestamp_name}_{requested_name}.json"
    tmp_path = image_path.with_suffix(".jpg.tmp")
    fresh_after = parse_utc_timestamp(params.get("fresh_after_utc"))
    if fresh and fresh_after is None:
        fresh_after = timestamp

    metadata: dict[str, Any] = {
        "timestamp_utc": timestamp.isoformat(),
        "requested_name": requested_name,
        "params": params,
        "framebuffer_dir": str(FRAMEBUFFER_DIR),
        "framebuffer_latest_image": str(FRAMEBUFFER_LATEST_IMAGE),
        "framebuffer_latest_metadata": str(FRAMEBUFFER_LATEST_METADATA),
        "require_high_res": require_high_res,
        "fresh": fresh,
        "fresh_after_utc": fresh_after.isoformat() if fresh_after else None,
        "fresh_timeout": fresh_timeout,
        "max_age": max_age,
        "attempts": [],
    }

    try:
        source_image, source_metadata = wait_for_buffered_frame(
            fresh_after_utc=fresh_after,
            timeout=fresh_timeout,
            max_age=max_age,
        )
        captured_width = int(source_metadata.get("width") or 0)
        captured_height = int(source_metadata.get("height") or 0)
        if not captured_width or not captured_height:
            captured_width, captured_height = jpeg_dimensions(source_image)
        captured_width = int(captured_width or 0)
        captured_height = int(captured_height or 0)
        if require_high_res and (
            captured_width < HIGH_RES_MIN_WIDTH or captured_height < HIGH_RES_MIN_HEIGHT
        ):
            raise CaptureError(
                "Buffered frame is below required high-res size: "
                f"{captured_width}x{captured_height}"
            )
        tmp_path.write_bytes(source_image.read_bytes())
        verify_jpeg(tmp_path)
        os.replace(tmp_path, image_path)
        metadata["attempts"].append(
            {
                "ok": True,
                "source": "vision_framebuffer",
                "source_metadata": source_metadata,
            }
        )
        metadata.update(
            {
                "ok": True,
                "image_path": str(image_path),
                "metadata_path": str(metadata_path),
                "url": f"/vision/{image_path.name}",
                "latest_url": "/vision/latest.jpg",
                "source_latest_url": "/webcam/?action=snapshot",
                "width": captured_width,
                "height": captured_height,
                "size_bytes": image_path.stat().st_size,
                "capture_source": "vision_framebuffer",
                "source_frame": source_metadata,
            }
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    update_latest_symlinks(image_path, metadata_path)
    log(f"Persisted buffered vision frame: {image_path}")
    return metadata


class KlippyRemoteCaptureDaemon:
    def __init__(self) -> None:
        self.capture_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(
            maxsize=20
        )
        self.worker = threading.Thread(target=self._capture_worker, daemon=True)
        self.next_id = 1

    def _capture_worker(self) -> None:
        while True:
            job_kind, params = self.capture_queue.get()
            try:
                if job_kind == REMOTE_ACTION:
                    capture_frame(params)
                elif job_kind == NOZZLE_ALIGN_REMOTE_ACTION:
                    self._run_nozzle_alignment(params)
                elif job_kind == NOZZLE_SWEEP_REMOTE_ACTION:
                    self._run_nozzle_sweep(params)
                else:
                    log(f"Unknown vision job kind: {job_kind}")
            except Exception as exc:
                log(f"Vision job {job_kind} failed: {exc}")
            finally:
                self.capture_queue.task_done()

    def _run_nozzle_alignment(self, params: dict[str, Any]) -> None:
        command = [
            NOZZLE_ALIGN_BIN,
            "--name",
            sanitize_name(params.get("name", "manual")),
            "--x",
            str(float(params.get("x", 196.0))),
            "--y",
            str(float(params.get("y", -14.8))),
            "--z",
            str(float(params.get("z", 2.0))),
            "--no-manage-crowsnest",
        ]
        if int(params.get("restore", 1)) == 0:
            command.append("--no-restore")
        result = run_command(command, timeout=240)
        if result.stdout.strip():
            log(f"Nozzle vision result: {result.stdout.strip()}")
        if result.stderr.strip():
            log(f"Nozzle vision stderr: {result.stderr.strip()}")
        if result.returncode != 0:
            raise CaptureError(
                result.stderr.strip() or result.stdout.strip() or "nozzle vision failed"
            )

    def _run_nozzle_sweep(self, params: dict[str, Any]) -> None:
        command = [
            NOZZLE_ALIGN_BIN,
            "--sweep",
            "--name",
            sanitize_name(params.get("name", "manual")),
            "--x",
            str(float(params.get("x", 196.0))),
            "--y",
            str(float(params.get("y", -14.8))),
            "--z",
            str(float(params.get("z", 20.0))),
            "--dx",
            str(params.get("dx", "0,1,2")),
            "--no-manage-crowsnest",
        ]
        if int(params.get("restore", 1)) == 0:
            command.append("--no-restore")
        result = run_command(command, timeout=420)
        if result.stdout.strip():
            log(f"Nozzle vision sweep result: {result.stdout.strip()}")
        if result.stderr.strip():
            log(f"Nozzle vision sweep stderr: {result.stderr.strip()}")
        if result.returncode != 0:
            raise CaptureError(
                result.stderr.strip()
                or result.stdout.strip()
                or "nozzle vision sweep failed"
            )

    def _send(self, sock: socket.socket, payload: dict[str, Any]) -> None:
        sock.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\x03")

    def _register_remote_method(
        self, sock: socket.socket, remote_method: str, action: str
    ) -> None:
        request_id = self.next_id
        self.next_id += 1
        self._send(
            sock,
            {
                "id": request_id,
                "method": "register_remote_method",
                "params": {
                    "remote_method": remote_method,
                    "response_template": {"action": action},
                },
            },
        )
        log(f"Registered Klipper remote method: {remote_method}")

    def _register(self, sock: socket.socket) -> None:
        self._register_remote_method(sock, REMOTE_METHOD, REMOTE_ACTION)
        self._register_remote_method(
            sock, NOZZLE_ALIGN_REMOTE_METHOD, NOZZLE_ALIGN_REMOTE_ACTION
        )
        self._register_remote_method(
            sock, NOZZLE_SWEEP_REMOTE_METHOD, NOZZLE_SWEEP_REMOTE_ACTION
        )

    def _handle_message(self, message: dict[str, Any]) -> None:
        action = message.get("action")
        if action not in (
            REMOTE_ACTION,
            NOZZLE_ALIGN_REMOTE_ACTION,
            NOZZLE_SWEEP_REMOTE_ACTION,
        ):
            return
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {"raw_params": params}
        try:
            self.capture_queue.put_nowait((action, params))
            log(f"Queued vision job {action}: {params}")
        except queue.Full:
            log("Vision queue is full; dropping request")

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
    parser.add_argument("--require-high-res", action="store_true")
    parser.add_argument("--fresh-after-utc")
    parser.add_argument("--fresh-timeout", type=float, default=DEFAULT_FRAME_FRESH_TIMEOUT)
    parser.add_argument("--max-age", type=float, default=DEFAULT_FRAME_MAX_AGE)
    parser.add_argument(
        "--no-fresh",
        action="store_true",
        help="Persist the latest buffered frame immediately instead of waiting for a new one.",
    )
    parser.add_argument(
        "--no-crowsnest-management",
        action="store_true",
        help="Compatibility no-op; buffered capture never stops or starts Crowsnest.",
    )
    parser.add_argument("--retries", type=int, default=DEFAULT_CAPTURE_RETRIES)
    args = parser.parse_args()

    if args.capture_once:
        metadata = capture_frame(
            {
                "name": args.capture_once,
                "reason": "capture_once",
                "require_high_res": args.require_high_res,
                "retries": args.retries,
                "fresh": not args.no_fresh,
                "fresh_after_utc": args.fresh_after_utc,
                "fresh_timeout": args.fresh_timeout,
                "max_age": args.max_age,
                "manage_crowsnest": False,
            }
        )
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0
    if args.daemon:
        KlippyRemoteCaptureDaemon().run()
        return 0

    parser.error("use --daemon or --capture-once NAME")
    return 2


if __name__ == "__main__":
    sys.exit(main())
