#!/usr/bin/env python3
"""High-resolution still-frame camera owner for Mainsail and vision jobs.

This service replaces normal Crowsnest ownership of the camera. It captures
high-resolution MJPEG frames into a RAM-backed ring buffer and serves the latest
good frame as both a snapshot endpoint and a low-FPS MJPEG stream.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

CAMERA_DEVICE = os.environ.get(
    "VISION_CAMERA_DEVICE",
    "/dev/v4l/by-id/usb-Aukey-PC-LM1E_Camera_Aukey-PC-LM1E_Camera-video-index0",
)
RUN_DIR = Path(os.environ.get("VISION_FRAMEBUFFER_DIR", "/run/vision-preview"))
RING_DIR = RUN_DIR / "ring"
HTTP_HOST = os.environ.get("VISION_FRAMEBUFFER_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("VISION_FRAMEBUFFER_PORT", "8080"))
TARGET_WIDTH = int(os.environ.get("VISION_FRAMEBUFFER_WIDTH", "1920"))
TARGET_HEIGHT = int(os.environ.get("VISION_FRAMEBUFFER_HEIGHT", "1080"))
TARGET_FPS = float(os.environ.get("VISION_FRAMEBUFFER_FPS", "1.0"))
STREAM_FPS = float(os.environ.get("VISION_FRAMEBUFFER_STREAM_FPS", str(TARGET_FPS)))
RING_SIZE = int(os.environ.get("VISION_FRAMEBUFFER_RING_SIZE", "30"))
CAPTURE_TIMEOUT = float(os.environ.get("VISION_FRAMEBUFFER_CAPTURE_TIMEOUT", "8"))
CAPTURE_RETRIES = max(
    1, int(os.environ.get("VISION_FRAMEBUFFER_CAPTURE_RETRIES", "3"))
)
STALE_AFTER = float(os.environ.get("VISION_FRAMEBUFFER_STALE_AFTER", "5"))
PUBLIC_SNAPSHOT_URL = os.environ.get(
    "VISION_FRAMEBUFFER_PUBLIC_SNAPSHOT_URL", "/webcam/?action=snapshot"
)
SERVICE_NAME = os.environ.get("VISION_FRAMEBUFFER_SERVICE_NAME", "vision-framebuffer")
CAMERA_PROFILE_FILE_ENV = os.environ.get("VISION_CAMERA_PROFILE_FILE", "").strip()
CAMERA_PROFILE_FILE = Path(CAMERA_PROFILE_FILE_ENV) if CAMERA_PROFILE_FILE_ENV else None
CAMERA_DEFAULT_PROFILE = os.environ.get("VISION_CAMERA_DEFAULT_PROFILE", "").strip()
CAMERA_PROFILE_REQUEST_FILE_ENV = os.environ.get(
    "VISION_CAMERA_PROFILE_REQUEST_FILE", ""
).strip()
CAMERA_PROFILE_REQUEST_FILE = (
    Path(CAMERA_PROFILE_REQUEST_FILE_ENV) if CAMERA_PROFILE_REQUEST_FILE_ENV else None
)
CAMERA_PROFILE_APPLY_TIMEOUT = float(
    os.environ.get("VISION_CAMERA_PROFILE_APPLY_TIMEOUT", "5")
)
NAME_REPLACEMENTS = str.maketrans({c: "_" for c in " /\\:;|?*[]{}()<>'\"`$&!"})


class FramebufferError(RuntimeError):
    pass


def log(message: str) -> None:
    print(
        f"{datetime.now(timezone.utc).isoformat()} {message}",
        file=sys.stderr,
        flush=True,
    )


def run_command(command: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def verify_jpeg(path: Path) -> None:
    data = path.read_bytes()
    if (
        len(data) < 4
        or data[:2] != b"\xff\xd8"
        or data[-2:] != b"\xff\xd9"
    ):
        raise FramebufferError(f"{path} is not a JPEG frame")
    width, height = jpeg_dimensions(path)
    if not width or not height:
        raise FramebufferError(f"{path} has no decodable JPEG dimensions")


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


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def set_mjpeg_format(device: str, width: int, height: int) -> dict[str, Any]:
    fmt = f"width={width},height={height},pixelformat=MJPG"
    result = run_command(
        [
            "v4l2-ctl",
            "-d",
            device,
            f"--set-fmt-video={fmt}",
        ],
        timeout=CAPTURE_TIMEOUT,
    )
    if result.returncode != 0:
        raise FramebufferError(
            result.stderr.strip()
            or result.stdout.strip()
            or "v4l2 format selection failed"
        )
    return {
        "requested_width": width,
        "requested_height": height,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def capture_mjpeg_frame(
    device: str, path: Path, width: int, height: int
) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(1, CAPTURE_RETRIES + 1):
        path.unlink(missing_ok=True)
        try:
            result = run_command(
                [
                    "v4l2-ctl",
                    "-d",
                    device,
                    "--stream-mmap",
                    "--stream-count=1",
                    f"--stream-to={path}",
                ],
                timeout=CAPTURE_TIMEOUT,
            )
            if result.returncode != 0:
                raise FramebufferError(
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "v4l2 capture failed"
                )
            verify_jpeg(path)
            actual_width, actual_height = jpeg_dimensions(path)
            if (actual_width, actual_height) != (width, height):
                raise FramebufferError(
                    "captured JPEG dimensions "
                    f"{actual_width}x{actual_height} do not match "
                    f"requested {width}x{height}"
                )
            return {
                "requested_width": width,
                "requested_height": height,
                "width": actual_width,
                "height": actual_height,
                "stream_stdout": result.stdout.strip(),
                "stream_stderr": result.stderr.strip(),
                "capture_attempt": attempt,
                "capture_retry_count": attempt - 1,
                "capture_errors": errors,
            }
        except Exception as exc:
            errors.append(str(exc))
            path.unlink(missing_ok=True)
            if attempt < CAPTURE_RETRIES:
                time.sleep(0.1)
    raise FramebufferError(
        f"v4l2 capture failed after {CAPTURE_RETRIES} attempts: "
        + "; ".join(errors)
    )


class CameraProfileManager:
    def __init__(
        self,
        *,
        profile_file: Path | None,
        default_profile: str,
        request_file: Path | None,
    ) -> None:
        self.profile_file = profile_file
        self.default_profile = default_profile
        self.request_file = request_file
        self.aliases: dict[str, str] = {}
        self.profiles: dict[str, list[dict[str, Any]]] = {}
        self.requested_profile = default_profile
        self.request_key: tuple[int, int] | None = None
        self.last_request: dict[str, Any] | None = None
        self.last_state: dict[str, Any] = {
            "enabled": profile_file is not None,
            "profile_file": str(profile_file) if profile_file else None,
            "request_file": str(request_file) if request_file else None,
            "requested_profile": default_profile or None,
            "active_profile": None,
            "profile_names": [],
            "applied_controls": [],
            "control_errors": [],
        }
        if profile_file is not None:
            self._load_profiles(profile_file)

    def _load_profiles(self, profile_file: Path) -> None:
        payload = json.loads(profile_file.read_text())
        aliases = payload.get("aliases") or {}
        profiles = payload.get("profiles") or {}
        if not isinstance(aliases, dict) or not isinstance(profiles, dict):
            raise FramebufferError(f"{profile_file} must contain aliases and profiles")
        parsed_profiles: dict[str, list[dict[str, Any]]] = {}
        for profile_name, profile_payload in profiles.items():
            controls = (
                profile_payload.get("controls")
                if isinstance(profile_payload, dict)
                else None
            )
            if not isinstance(controls, list) or not controls:
                raise FramebufferError(
                    f"{profile_file}: profile {profile_name} has no controls"
                )
            parsed_controls = []
            for control in controls:
                if (
                    not isinstance(control, dict)
                    or "name" not in control
                    or "value" not in control
                ):
                    raise FramebufferError(
                        f"{profile_file}: profile {profile_name} has an invalid control"
                    )
                parsed_controls.append(
                    {"name": str(control["name"]), "value": control["value"]}
                )
            parsed_profiles[str(profile_name)] = parsed_controls
        self.aliases = {str(alias): str(target) for alias, target in aliases.items()}
        self.profiles = parsed_profiles

    def _resolve(self, requested_profile: str) -> tuple[str, list[dict[str, Any]]]:
        active_profile = self.aliases.get(requested_profile, requested_profile)
        controls = self.profiles.get(active_profile)
        if controls is None:
            known = ", ".join(sorted(set(self.aliases) | set(self.profiles)))
            raise FramebufferError(
                f"Unknown camera profile {requested_profile!r}; known profiles: {known}"
            )
        return active_profile, controls

    def _update_request(self) -> None:
        if self.request_file is None or not self.request_file.exists():
            return
        stat = self.request_file.stat()
        request_key = (stat.st_mtime_ns, stat.st_size)
        if request_key == self.request_key:
            return
        payload = json.loads(self.request_file.read_text())
        requested_profile = str(payload.get("profile") or "").strip()
        if requested_profile:
            self.requested_profile = requested_profile
            self.last_request = payload
            self.request_key = request_key

    def state(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.last_state))

    def apply(self, device: str) -> dict[str, Any]:
        if self.profile_file is None:
            self.last_state = {
                "enabled": False,
                "profile_file": None,
                "request_file": str(self.request_file) if self.request_file else None,
                "requested_profile": None,
                "active_profile": None,
                "profile_names": [],
                "applied_controls": [],
                "control_errors": [],
            }
            return self.state()

        self._update_request()
        requested_profile = self.requested_profile or self.default_profile
        if not requested_profile:
            raise FramebufferError(
                "Camera profile file configured but no profile selected"
            )
        active_profile, controls = self._resolve(requested_profile)

        applied_controls: list[dict[str, Any]] = []
        control_errors: list[dict[str, Any]] = []
        for control in controls:
            name = str(control["name"])
            value = control["value"]
            if isinstance(value, bool):
                value = int(value)
            result = run_command(
                [
                    "v4l2-ctl",
                    "-d",
                    device,
                    f"--set-ctrl={name}={value}",
                ],
                timeout=CAMERA_PROFILE_APPLY_TIMEOUT,
            )
            record = {
                "name": name,
                "value": value,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
            if result.returncode != 0:
                control_errors.append(record)
                break
            applied_controls.append(record)

        self.last_state = {
            "enabled": True,
            "profile_file": str(self.profile_file),
            "request_file": str(self.request_file) if self.request_file else None,
            "requested_profile": requested_profile,
            "active_profile": active_profile,
            "profile_names": sorted({requested_profile, active_profile}),
            "applied_controls": applied_controls,
            "control_errors": control_errors,
            "last_request": self.last_request,
        }
        if control_errors:
            failed = control_errors[0]
            raise FramebufferError(
                "Could not apply camera profile "
                f"{requested_profile!r} control {failed['name']}={failed['value']}: "
                f"{failed['stderr'] or failed['stdout'] or failed['returncode']}"
            )
        return self.state()


class FrameState:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.latest_bytes: bytes | None = None
        self.latest_meta: dict[str, Any] | None = None
        self.frame_id = 0
        self.frame_seq = 0
        self.frame_times: deque[float] = deque(maxlen=120)
        self.ring: deque[tuple[Path, Path]] = deque(maxlen=max(2, RING_SIZE))
        self.stream_clients = 0
        self.consecutive_errors = 0
        self.total_errors = 0
        self.last_error: str | None = None
        self.profile = {
            "width": TARGET_WIDTH,
            "height": TARGET_HEIGHT,
            "target_fps": TARGET_FPS,
        }
        self.camera_profile = {
            "enabled": CAMERA_PROFILE_FILE is not None,
            "profile_file": str(CAMERA_PROFILE_FILE) if CAMERA_PROFILE_FILE else None,
            "request_file": (
                str(CAMERA_PROFILE_REQUEST_FILE)
                if CAMERA_PROFILE_REQUEST_FILE
                else None
            ),
            "requested_profile": CAMERA_DEFAULT_PROFILE or None,
            "active_profile": None,
            "profile_names": [],
            "applied_controls": [],
            "control_errors": [],
        }
        self.stop_requested = threading.Event()

    def update_profile(self, *, width: int, height: int, target_fps: float) -> None:
        with self.condition:
            self.profile = {"width": width, "height": height, "target_fps": target_fps}
            self.condition.notify_all()

    def update_camera_profile(self, camera_profile: dict[str, Any]) -> None:
        with self.condition:
            self.camera_profile = dict(camera_profile)
            self.condition.notify_all()

    def update_frame(
        self, frame: bytes, meta: dict[str, Any], image_path: Path, meta_path: Path
    ) -> None:
        with self.condition:
            while len(self.ring) >= self.ring.maxlen:
                old_image, old_meta = self.ring.popleft()
                old_image.unlink(missing_ok=True)
                old_meta.unlink(missing_ok=True)
            self.ring.append((image_path, meta_path))
            self.latest_bytes = frame
            self.latest_meta = meta
            self.frame_id = int(meta["frame_id"])
            self.frame_seq = int(meta["frame_seq"])
            self.frame_times.append(time.monotonic())
            self.consecutive_errors = 0
            self.last_error = None
            self.condition.notify_all()

    def update_error(self, message: str) -> None:
        with self.condition:
            self.consecutive_errors += 1
            self.total_errors += 1
            self.last_error = message
            self.condition.notify_all()

    def wait_for_frame(self, timeout: float) -> tuple[bytes, dict[str, Any]] | None:
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.latest_bytes is None or self.latest_meta is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.condition.wait(timeout=remaining)
            return self.latest_bytes, dict(self.latest_meta)

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            now = time.monotonic()
            timestamps = [t for t in self.frame_times if now - t <= 60]
            if len(timestamps) >= 2 and timestamps[-1] > timestamps[0]:
                captured_fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
            else:
                captured_fps = 0.0
            last_meta = dict(self.latest_meta) if self.latest_meta else None
            age = None
            if last_meta and "monotonic_s" in last_meta:
                age = max(0.0, now - float(last_meta["monotonic_s"]))
            target_fps = float(self.profile.get("target_fps") or 0.0)
            return {
                "ok": last_meta is not None and (age is None or age <= STALE_AFTER),
                "camera_device": CAMERA_DEVICE,
                "run_dir": str(RUN_DIR),
                "ring_size": self.ring.maxlen,
                "ring_count": len(self.ring),
                "frame_count": self.frame_id,
                "frame_seq": self.frame_seq,
                "last_frame": last_meta,
                "last_frame_age_s": round(age, 3) if age is not None else None,
                "captured_fps": round(captured_fps, 3),
                "target_fps": target_fps,
                "stream_fps": STREAM_FPS,
                "stream_clients": self.stream_clients,
                "consecutive_errors": self.consecutive_errors,
                "total_errors": self.total_errors,
                "last_error": self.last_error,
                "profile": dict(self.profile),
                "camera_profile": dict(self.camera_profile),
                "stale_after_s": STALE_AFTER,
            }


class CaptureThread(threading.Thread):
    def __init__(self, state: FrameState) -> None:
        super().__init__(daemon=True)
        self.state = state
        self.profile_manager = CameraProfileManager(
            profile_file=CAMERA_PROFILE_FILE,
            default_profile=CAMERA_DEFAULT_PROFILE,
            request_file=CAMERA_PROFILE_REQUEST_FILE,
        )

    def run(self) -> None:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        RING_DIR.mkdir(parents=True, exist_ok=True)
        while not self.state.stop_requested.is_set():
            self.state.update_profile(
                width=TARGET_WIDTH, height=TARGET_HEIGHT, target_fps=TARGET_FPS
            )
            start = time.monotonic()
            tmp_path = RUN_DIR / ".capture.jpg.tmp"
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
                format_info = set_mjpeg_format(
                    CAMERA_DEVICE, TARGET_WIDTH, TARGET_HEIGHT
                )
                camera_profile = self.profile_manager.apply(CAMERA_DEVICE)
                self.state.update_camera_profile(camera_profile)
                capture_info = capture_mjpeg_frame(
                    CAMERA_DEVICE, tmp_path, TARGET_WIDTH, TARGET_HEIGHT
                )
                capture_info["format"] = format_info
                frame = tmp_path.read_bytes()
                self.state.frame_id += 1
                self.state.frame_seq += 1
                timestamp = datetime.now(timezone.utc)
                stamp = timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
                image_path = RING_DIR / f"frame_{self.state.frame_id:08d}_{stamp}.jpg"
                meta_path = image_path.with_suffix(".json")
                actual_width = int(capture_info.get("width") or TARGET_WIDTH)
                actual_height = int(capture_info.get("height") or TARGET_HEIGHT)
                meta = {
                    "frame_id": self.state.frame_id,
                    "frame_seq": self.state.frame_seq,
                    "timestamp_utc": timestamp.isoformat(),
                    "monotonic_s": time.monotonic(),
                    "camera_device": CAMERA_DEVICE,
                    "width": actual_width,
                    "height": actual_height,
                    "requested_width": TARGET_WIDTH,
                    "requested_height": TARGET_HEIGHT,
                    "target_fps": TARGET_FPS,
                    "capture_source": "vision_framebuffer_v4l2_mjpg",
                    "size_bytes": len(frame),
                    "ring_image_path": str(image_path),
                    "ring_metadata_path": str(meta_path),
                    "latest_url": PUBLIC_SNAPSHOT_URL,
                    "capture_info": capture_info,
                    "capture_attempt": capture_info.get("capture_attempt", 1),
                    "capture_retry_count": capture_info.get(
                        "capture_retry_count", 0
                    ),
                    "capture_errors": capture_info.get("capture_errors", []),
                    "camera_profile": camera_profile,
                }
                atomic_write_bytes(image_path, frame)
                atomic_write_json(meta_path, meta)
                atomic_write_bytes(RUN_DIR / "latest.jpg", frame)
                atomic_write_json(RUN_DIR / "latest.json", meta)
                self.state.update_frame(frame, meta, image_path, meta_path)
            except Exception as exc:
                message = str(exc)
                self.state.update_camera_profile(self.profile_manager.state())
                self.state.update_error(message)
                log(f"Capture failed: {message}")
            finally:
                tmp_path.unlink(missing_ok=True)

            interval = 1.0 / max(0.1, TARGET_FPS)
            elapsed = time.monotonic() - start
            self.state.stop_requested.wait(max(0.05, interval - elapsed))


class Handler(BaseHTTPRequestHandler):
    server: "FrameServer"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_snapshot(self) -> None:
        latest = self.server.state.wait_for_frame(timeout=10)
        if latest is None:
            self.send_error(
                HTTPStatus.SERVICE_UNAVAILABLE, "No camera frame available yet"
            )
            return
        frame, meta = latest
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Vision-Frame-Id", str(meta.get("frame_id", "")))
        self.send_header("X-Vision-Timestamp", str(meta.get("timestamp_utc", "")))
        self.end_headers()
        self.wfile.write(frame)

    def send_metadata(self) -> None:
        state = self.server.state.snapshot()
        latest = state.get("last_frame")
        if not latest:
            self.send_error(
                HTTPStatus.SERVICE_UNAVAILABLE, "No camera frame available yet"
            )
            return
        self.send_json(latest)

    def send_state(self) -> None:
        framebuffer = self.server.state.snapshot()
        stream = {
            "captured_fps": framebuffer["captured_fps"],
            "queued_fps": STREAM_FPS,
            "clients": framebuffer["stream_clients"],
            "last_frame_age_s": framebuffer["last_frame_age_s"],
        }
        self.send_json({"result": {"framebuffer": framebuffer, "stream": stream}})

    def send_stream(self) -> None:
        boundary = b"vision-frame"
        self.send_response(200)
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={boundary.decode()}"
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        with self.server.state.condition:
            self.server.state.stream_clients += 1
        try:
            interval = 1.0 / max(0.1, STREAM_FPS)
            while not self.server.state.stop_requested.is_set():
                latest = self.server.state.wait_for_frame(timeout=10)
                if latest is None:
                    time.sleep(0.2)
                    continue
                frame, meta = latest
                header = (
                    b"--"
                    + boundary
                    + b"\r\n"
                    + b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n".encode()
                    + f"X-Vision-Frame-Id: {meta.get('frame_id', '')}\r\n".encode()
                    + f"X-Vision-Timestamp: {meta.get('timestamp_utc', '')}\r\n".encode()
                    + b"\r\n"
                )
                self.wfile.write(header)
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            with self.server.state.condition:
                self.server.state.stream_clients = max(
                    0, self.server.state.stream_clients - 1
                )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        action = (query.get("action") or [""])[0]
        if action == "snapshot" or parsed.path in ("/snapshot", "/latest.jpg"):
            self.send_snapshot()
        elif action == "stream":
            self.send_stream()
        elif parsed.path in ("/state", "/api/state"):
            self.send_state()
        elif parsed.path in ("/latest.json", "/metadata"):
            self.send_metadata()
        elif parsed.path == "/":
            self.send_json({"service": SERVICE_NAME, "state_url": "/state"})
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown vision framebuffer endpoint")


class FrameServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], state: FrameState) -> None:
        super().__init__(server_address, Handler)
        self.state = state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HTTP_HOST)
    parser.add_argument("--port", type=int, default=HTTP_PORT)
    args = parser.parse_args()

    state = FrameState()
    capture_thread = CaptureThread(state)

    def stop(_signum: int, _frame: Any) -> None:
        state.stop_requested.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    capture_thread.start()
    server = FrameServer((args.host, args.port), state)
    server.timeout = 1.0
    log(
        "Serving vision framebuffer on "
        f"http://{args.host}:{args.port} from {CAMERA_DEVICE}"
    )
    try:
        while not state.stop_requested.is_set():
            server.handle_request()
    finally:
        state.stop_requested.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
