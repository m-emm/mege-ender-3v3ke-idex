#!/usr/bin/env python3
"""High-resolution camera capture bridge for Klipper vision work.

The daemon mode registers a configurable Klipper remote capture method.
Klipper macros can call it with ``action_call_remote_method`` without blocking
the printer motion queue on the actual image capture.
"""

from __future__ import annotations

import argparse
import hashlib
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
FRAMEBUFFER_PROFILE_REQUEST_FILE_ENV = os.environ.get(
    "VISION_CAMERA_PROFILE_REQUEST_FILE", ""
).strip()
FRAMEBUFFER_PROFILE_REQUEST_FILE = (
    Path(FRAMEBUFFER_PROFILE_REQUEST_FILE_ENV)
    if FRAMEBUFFER_PROFILE_REQUEST_FILE_ENV
    else None
)
KLIPPY_SOCKET = os.environ.get(
    "VISION_KLIPPY_SOCKET", "/home/pi/printer_data/comms/klippy.sock"
)
CROWSNEST_SERVICE = os.environ.get("VISION_CROWSNEST_SERVICE", "crowsnest")
WEBCAM_SNAPSHOT_URL = os.environ.get(
    "VISION_WEBCAM_SNAPSHOT_URL", "http://127.0.0.1/webcam/?action=snapshot"
)
PUBLIC_SNAPSHOT_URL = os.environ.get(
    "VISION_PUBLIC_SNAPSHOT_URL", "/webcam/?action=snapshot"
)
OUTPUT_URL_PREFIX = os.environ.get("VISION_OUTPUT_URL_PREFIX", "/vision").rstrip("/")
CROWSNEST_HOST = os.environ.get("VISION_CROWSNEST_HOST", "127.0.0.1")
CROWSNEST_PORT = int(os.environ.get("VISION_CROWSNEST_PORT", "8080"))
WEBCAM_READY_TIMEOUT = float(os.environ.get("VISION_WEBCAM_READY_TIMEOUT", "25"))
REMOTE_METHOD = os.environ.get("VISION_CAPTURE_REMOTE_METHOD", "vision_capture")
REMOTE_ACTION = os.environ.get("VISION_CAPTURE_REMOTE_ACTION", f"run_{REMOTE_METHOD}")
NOZZLE_SWEEP_REMOTE_METHOD = "idex_nozzle_vision_sweep"
NOZZLE_SWEEP_REMOTE_ACTION = "run_idex_nozzle_vision_sweep"
BED_Y_REMOTE_METHOD = "idex_bed_y_vision_sweep"
BED_Y_REMOTE_ACTION = "run_idex_bed_y_vision_sweep"
NOZZLE_Z_REMOTE_METHOD = "idex_nozzle_z_vision_sweep"
NOZZLE_Z_REMOTE_ACTION = "run_idex_nozzle_z_vision_sweep"
NOZZLE_PROFILE_REMOTE_METHOD = os.environ.get(
    "VISION_PROFILE_REMOTE_METHOD", "nozzle_cam_profile"
)
NOZZLE_PROFILE_REMOTE_ACTION = os.environ.get(
    "VISION_PROFILE_REMOTE_ACTION", "run_nozzle_cam_profile"
)
NOZZLE_ALIGN_BIN = os.environ.get(
    "VISION_NOZZLE_ALIGN_BIN", "/usr/local/bin/vision_nozzle_align.py"
)
CAPTURE_RESOLUTIONS = ((1920, 1080), (1280, 720))
DEFAULT_CAPTURE_RETRIES = int(os.environ.get("VISION_CAPTURE_RETRIES", "3"))
HIGH_RES_MIN_WIDTH = int(os.environ.get("VISION_HIGH_RES_MIN_WIDTH", "1920"))
HIGH_RES_MIN_HEIGHT = int(os.environ.get("VISION_HIGH_RES_MIN_HEIGHT", "1080"))
DEFAULT_FRAME_FRESH_TIMEOUT = float(os.environ.get("VISION_FRAME_FRESH_TIMEOUT", "10"))
DEFAULT_FRAME_MAX_AGE = float(os.environ.get("VISION_FRAME_MAX_AGE", "10"))
DEFAULT_CAMERA_PROFILE = os.environ.get("VISION_CAPTURE_DEFAULT_PROFILE", "").strip()
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HASHED_GCODE_TOKEN_RE = re.compile(
    r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+"
)
VISION_HASH_PLACEHOLDER = "sha256:PLACEHOLDER"
VISION_JOB_SCHEMA_VERSION = 1
VISIOND_CAMERA = os.environ.get("VISIOND_CAMERA", "nozzle_cam")
VISIOND_SOCKET = Path(
    os.environ.get("VISIOND_SOCKET", "/run/vision-capture-nozzle_cam/visiond.sock")
)
VISION_JOB_ROOT = Path(os.environ.get("VISION_JOB_ROOT", str(OUTPUT_DIR / "jobs")))
VISIOND_SOCKET_REQUEST_TIMEOUT = float(
    os.environ.get("VISIOND_SOCKET_REQUEST_TIMEOUT", "30")
)
REGISTER_NOZZLE_METHODS = os.environ.get(
    "VISION_REGISTER_NOZZLE_METHODS", "1"
).strip().lower() not in ("0", "false", "no", "off", "")
VISIOND_SOCKET_ENABLED = os.environ.get(
    "VISIOND_SOCKET_ENABLED", "1" if REGISTER_NOZZLE_METHODS else "0"
).strip().lower() not in ("0", "false", "no", "off", "")


class CaptureError(RuntimeError):
    pass


def log(message: str) -> None:
    print(
        f"{datetime.now(timezone.utc).isoformat()} {message}",
        file=sys.stderr,
        flush=True,
    )


def run_command(
    command: list[str], *, timeout: float = 30.0
) -> subprocess.CompletedProcess:
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


def sanitize_profile(name: Any) -> str:
    cleaned = NAME_RE.sub("_", str(name or "")).strip("._-")
    return cleaned[:80]


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


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def canonicalize_gcode_for_hash(gcode: str) -> str:
    normalized = gcode.replace("\r\n", "\n").replace("\r", "\n")

    def replace_token(match: re.Match[str]) -> str:
        return f"{match.group('name')}={VISION_HASH_PLACEHOLDER}"

    return HASHED_GCODE_TOKEN_RE.sub(replace_token, normalized)


def compute_gcode_hash(gcode: str) -> str:
    return sha256_prefixed(canonicalize_gcode_for_hash(gcode).encode("utf-8"))


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    canonical = dict(manifest)
    canonical["manifest_hash"] = VISION_HASH_PLACEHOLDER
    return sha256_prefixed(canonical_json_bytes(canonical))


def request_framebuffer_profile(
    profile: str, params: dict[str, Any] | None = None
) -> datetime | None:
    if FRAMEBUFFER_PROFILE_REQUEST_FILE is None:
        return None
    if not profile:
        return None
    requested_at = datetime.now(timezone.utc)
    atomic_write_json(
        FRAMEBUFFER_PROFILE_REQUEST_FILE,
        {
            "profile": profile,
            "requested_at_utc": requested_at.isoformat(),
            "source": "vision_capture",
            "params": params or {},
        },
    )
    return requested_at


def metadata_matches_profile(metadata: dict[str, Any], profile: str | None) -> bool:
    if not profile:
        return True
    camera_profile = metadata.get("camera_profile") or {}
    names = set(camera_profile.get("profile_names") or [])
    for key in ("requested_profile", "active_profile"):
        value = camera_profile.get(key)
        if value:
            names.add(str(value))
    return profile in names


def wait_for_buffered_frame(
    *,
    fresh_after_utc: datetime | None,
    timeout: float,
    max_age: float,
    required_profile: str | None = None,
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
            if not metadata_matches_profile(metadata, required_profile):
                camera_profile = metadata.get("camera_profile") or {}
                last_error = CaptureError(
                    "latest buffered frame has profile "
                    f"{camera_profile.get('profile_names')} but needs {required_profile}"
                )
                time.sleep(0.1)
                continue
            verify_jpeg(FRAMEBUFFER_LATEST_IMAGE)
            return FRAMEBUFFER_LATEST_IMAGE, metadata
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise CaptureError(f"Timed out waiting for buffered frame: {last_error}")


def framebuffer_seq(metadata: dict[str, Any]) -> int:
    value = metadata.get("frame_seq")
    if value is None:
        raise CaptureError("buffered frame metadata has no frame_seq")
    return int(value)


def wait_for_buffered_frame_seq_after(
    *,
    previous_frame_seq: int,
    timeout: float,
    required_profile: str | None = None,
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
            seq = framebuffer_seq(metadata)
            if seq <= previous_frame_seq:
                last_error = CaptureError(
                    f"latest buffered frame_seq {seq} has not advanced past "
                    f"{previous_frame_seq}"
                )
                time.sleep(0.05)
                continue
            if not metadata_matches_profile(metadata, required_profile):
                camera_profile = metadata.get("camera_profile") or {}
                last_error = CaptureError(
                    "latest buffered frame has profile "
                    f"{camera_profile.get('profile_names')} but needs {required_profile}"
                )
                time.sleep(0.05)
                continue
            verify_jpeg(FRAMEBUFFER_LATEST_IMAGE)
            return FRAMEBUFFER_LATEST_IMAGE, metadata
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise CaptureError(
        "Timed out waiting for buffered frame_seq advancement: "
        f"{last_error}"
    )


def wait_for_active_profile(profile: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if not FRAMEBUFFER_LATEST_METADATA.exists():
                raise CaptureError(f"{FRAMEBUFFER_LATEST_METADATA} does not exist")
            metadata = read_framebuffer_metadata()
            if metadata_matches_profile(metadata, profile):
                return metadata
            camera_profile = metadata.get("camera_profile") or {}
            last_error = CaptureError(
                "active framebuffer profile is "
                f"{camera_profile.get('profile_names')} but needs {profile}"
            )
        except Exception as exc:
            last_error = exc
        time.sleep(0.05)
    raise CaptureError(f"Timed out waiting for camera profile {profile!r}: {last_error}")


def capture_with_resolution(
    device: str, image_path: Path, width: int, height: int
) -> dict[str, Any]:
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
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
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


def output_url(name: str) -> str:
    if not OUTPUT_URL_PREFIX:
        return f"/{name}"
    return f"{OUTPUT_URL_PREFIX}/{name}"


def capture_frame(params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    require_high_res = bool(params.get("require_high_res"))
    fresh = as_bool(params.get("fresh"), True)
    fresh_timeout = float(params.get("fresh_timeout") or DEFAULT_FRAME_FRESH_TIMEOUT)
    max_age = float(params.get("max_age") or DEFAULT_FRAME_MAX_AGE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    requested_profile = sanitize_profile(
        params.get("profile") or DEFAULT_CAMERA_PROFILE
    )
    profile_request_time = request_framebuffer_profile(requested_profile, params)
    timestamp = datetime.now(timezone.utc)
    timestamp_name = timestamp.strftime("%Y%m%dT%H%M%SZ")
    requested_name = sanitize_name(params.get("name"))
    image_path = OUTPUT_DIR / f"{timestamp_name}_{requested_name}.jpg"
    metadata_path = OUTPUT_DIR / f"{timestamp_name}_{requested_name}.json"
    tmp_path = image_path.with_suffix(".jpg.tmp")
    fresh_after = parse_utc_timestamp(params.get("fresh_after_utc"))
    if fresh and fresh_after is None:
        fresh_after = profile_request_time or timestamp

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
        "requested_camera_profile": requested_profile or None,
        "profile_request_utc": (
            profile_request_time.isoformat() if profile_request_time else None
        ),
        "framebuffer_profile_request_file": (
            str(FRAMEBUFFER_PROFILE_REQUEST_FILE)
            if FRAMEBUFFER_PROFILE_REQUEST_FILE
            else None
        ),
        "attempts": [],
    }

    try:
        source_image, source_metadata = wait_for_buffered_frame(
            fresh_after_utc=fresh_after,
            timeout=fresh_timeout,
            max_age=max_age,
            required_profile=requested_profile or None,
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
                "url": output_url(image_path.name),
                "latest_url": output_url("latest.jpg"),
                "source_latest_url": PUBLIC_SNAPSHOT_URL,
                "width": captured_width,
                "height": captured_height,
                "size_bytes": image_path.stat().st_size,
                "capture_source": "vision_framebuffer",
                "source_frame": source_metadata,
                "camera_profile": source_metadata.get("camera_profile"),
            }
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    update_latest_symlinks(image_path, metadata_path)
    log(f"Persisted buffered vision frame: {image_path}")
    return metadata


class VisionJobApi:
    def __init__(
        self,
        *,
        job_root: Path = VISION_JOB_ROOT,
        camera: str = VISIOND_CAMERA,
        request_timeout: float = VISIOND_SOCKET_REQUEST_TIMEOUT,
    ) -> None:
        self.job_root = job_root
        self.camera = camera
        self.request_timeout = request_timeout
        self.lock_path = job_root / ".active_job.json"

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            action = str(request.get("action") or "")
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise CaptureError("request params must be an object")
            if action == "job_begin":
                result = self.job_begin(params)
            elif action == "profile":
                result = self.profile(params)
            elif action == "capture":
                result = self.capture(params)
            elif action == "job_end":
                result = self.job_end(params)
            else:
                raise CaptureError(f"unknown request action {action!r}")
            return {"ok": True, "result": result}
        except Exception as exc:
            self._record_failure_if_active(request, exc)
            return {"ok": False, "error": str(exc)}

    def _job_dir(self, job_id: Any) -> Path:
        job = sanitize_name(job_id)
        if not job:
            raise CaptureError("JOB is required")
        return self.job_root / job

    def _manifest_path(self, job_id: Any) -> Path:
        return self._job_dir(job_id) / "manifest.json"

    def _state_path(self, job_id: Any) -> Path:
        return self._job_dir(job_id) / "state.json"

    def _events_path(self, job_id: Any) -> Path:
        return self._job_dir(job_id) / "events.jsonl"

    def _frames_dir(self, job_id: Any) -> Path:
        return self._job_dir(job_id) / "frames"

    def _load_manifest(self, job_id: Any) -> dict[str, Any]:
        path = self._manifest_path(job_id)
        if not path.exists():
            raise CaptureError(f"missing vision job manifest: {path}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if int(manifest.get("schema_version") or 0) != VISION_JOB_SCHEMA_VERSION:
            raise CaptureError(
                f"unsupported vision job schema_version {manifest.get('schema_version')}"
            )
        if str(manifest.get("job_id")) != sanitize_name(job_id):
            raise CaptureError(
                f"manifest job_id {manifest.get('job_id')!r} does not match JOB={job_id!r}"
            )
        if str(manifest.get("camera")) != self.camera:
            raise CaptureError(
                f"manifest camera {manifest.get('camera')!r} does not match {self.camera!r}"
            )
        return manifest

    def _load_state(self, job_id: Any) -> dict[str, Any]:
        path = self._state_path(job_id)
        if not path.exists():
            raise CaptureError(f"missing vision job state: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_state(self, job_id: Any, state: dict[str, Any]) -> None:
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(self._state_path(job_id), state)

    def _append_event(self, job_id: Any, event: str, payload: dict[str, Any]) -> None:
        append_jsonl(
            self._events_path(job_id),
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "job_id": sanitize_name(job_id),
                "event": event,
                **payload,
            },
        )

    def _verify_hashes(
        self,
        manifest: dict[str, Any],
        *,
        expected_manifest_hash: str,
        expected_gcode_hash: str,
    ) -> None:
        manifest_hash = str(manifest.get("manifest_hash") or "")
        gcode_hash = str(manifest.get("gcode_hash") or "")
        if manifest_hash != expected_manifest_hash:
            raise CaptureError(
                f"manifest hash mismatch: {manifest_hash} != {expected_manifest_hash}"
            )
        if gcode_hash != expected_gcode_hash:
            raise CaptureError(
                f"manifest gcode_hash mismatch: {gcode_hash} != {expected_gcode_hash}"
            )

        gcode_file = str(manifest.get("gcode_file") or "acquisition.gcode")
        gcode_path = self._job_dir(manifest["job_id"]) / gcode_file
        if not gcode_path.exists():
            raise CaptureError(f"missing acquisition G-code: {gcode_path}")
        computed_gcode_hash = compute_gcode_hash(gcode_path.read_text(encoding="utf-8"))
        computed_manifest_hash = compute_manifest_hash(manifest)
        if computed_gcode_hash != expected_gcode_hash:
            raise CaptureError(
                f"acquisition G-code hash mismatch: {computed_gcode_hash} != "
                f"{expected_gcode_hash}"
            )
        if computed_manifest_hash != expected_manifest_hash:
            raise CaptureError(
                f"manifest content hash mismatch: {computed_manifest_hash} != "
                f"{expected_manifest_hash}"
            )

    def _active_job(self) -> str | None:
        if not self.lock_path.exists():
            return None
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
            return str(payload.get("job") or "")
        except Exception:
            return ""

    def _acquire_lock(self, job_id: str) -> None:
        self.job_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "job": job_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with self.lock_path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except FileExistsError:
            raise CaptureError(
                f"another vision job is active: {self._active_job() or self.lock_path}"
            ) from None

    def _release_lock(self, job_id: str) -> None:
        active = self._active_job()
        if active and active != job_id:
            raise CaptureError(f"active job lock belongs to {active!r}, not {job_id!r}")
        self.lock_path.unlink(missing_ok=True)

    def _require_active(self, job_id: str) -> None:
        active = self._active_job()
        if active != job_id:
            raise CaptureError(f"active job is {active!r}, not {job_id!r}")

    def _frame_by_seq(self, manifest: dict[str, Any], seq: int) -> dict[str, Any]:
        for frame in manifest.get("frames") or []:
            if int(frame.get("seq")) == seq:
                return frame
        raise CaptureError(f"manifest has no frame with seq={seq}")

    def _completed_frame_ids(self, job_id: str, manifest: dict[str, Any]) -> list[str]:
        completed: list[str] = []
        frames_dir = self._frames_dir(job_id)
        for frame in manifest.get("frames") or []:
            frame_id = str(frame.get("frame") or "")
            image = frames_dir / f"{frame_id}.jpg"
            sidecar = frames_dir / f"{frame_id}.json"
            if image.exists() or sidecar.exists():
                if not image.exists() or not sidecar.exists():
                    raise CaptureError(f"incomplete committed frame artifacts for {frame_id}")
                verify_jpeg(image)
                json.loads(sidecar.read_text(encoding="utf-8"))
                completed.append(frame_id)
        return completed

    def job_begin(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = sanitize_name(params.get("job"))
        manifest = self._load_manifest(job_id)
        state = self._load_state(job_id)
        if state.get("state") != "prepared":
            raise CaptureError(
                f"vision job {job_id} is {state.get('state')!r}, expected 'prepared'"
            )
        self._verify_hashes(
            manifest,
            expected_manifest_hash=str(params.get("manifest_hash") or ""),
            expected_gcode_hash=str(params.get("gcode_hash") or ""),
        )
        completed = self._completed_frame_ids(job_id, manifest)
        if completed:
            raise CaptureError(
                f"prepared vision job already has committed frames: {completed}"
            )
        self._acquire_lock(job_id)
        state.update(
            {
                "state": "acquiring",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "committed_frame_count": 0,
                "next_seq": 0,
                "active_camera": self.camera,
            }
        )
        self._write_state(job_id, state)
        self._append_event(
            job_id,
            "acquiring",
            {
                "state": "acquiring",
                "manifest_hash": manifest["manifest_hash"],
                "gcode_hash": manifest["gcode_hash"],
            },
        )
        return {
            "job": job_id,
            "state": "acquiring",
            "frame_count": int(manifest.get("frame_count") or 0),
        }

    def profile(self, params: dict[str, Any]) -> dict[str, Any]:
        camera = sanitize_name(params.get("camera"))
        profile = sanitize_profile(params.get("profile"))
        if camera != self.camera:
            raise CaptureError(f"VISION_PROFILE CAMERA={camera!r} is not {self.camera!r}")
        if not profile:
            raise CaptureError("VISION_PROFILE PROFILE is required")
        requested_at = request_framebuffer_profile(profile, params)
        if requested_at is None:
            raise CaptureError("No framebuffer profile request file is configured")
        metadata = wait_for_active_profile(profile, timeout=self.request_timeout)
        return {
            "camera": camera,
            "profile": profile,
            "profile_request_utc": requested_at.isoformat(),
            "framebuffer_seq": framebuffer_seq(metadata),
            "camera_profile": metadata.get("camera_profile"),
        }

    def capture(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = sanitize_name(params.get("job"))
        seq = int(params.get("seq"))
        frame_id = sanitize_name(params.get("frame"))
        camera = sanitize_name(params.get("camera"))
        profile = sanitize_profile(params.get("profile"))
        if camera != self.camera:
            raise CaptureError(f"VISION_CAPTURE_SYNC CAMERA={camera!r} is not {self.camera!r}")
        if not profile:
            raise CaptureError("VISION_CAPTURE_SYNC PROFILE is required")
        self._require_active(job_id)
        manifest = self._load_manifest(job_id)
        state = self._load_state(job_id)
        if state.get("state") != "acquiring":
            raise CaptureError(
                f"vision job {job_id} is {state.get('state')!r}, expected 'acquiring'"
            )
        expected_seq = int(state.get("next_seq", state.get("committed_frame_count", 0)))
        if seq != expected_seq:
            raise CaptureError(f"expected job seq {expected_seq}, got {seq}")
        manifest_frame = self._frame_by_seq(manifest, seq)
        if str(manifest_frame.get("frame")) != frame_id:
            raise CaptureError(
                f"manifest seq {seq} frame is {manifest_frame.get('frame')!r}, "
                f"got {frame_id!r}"
            )
        if str(manifest_frame.get("camera")) != camera:
            raise CaptureError(
                f"manifest seq {seq} camera is {manifest_frame.get('camera')!r}, "
                f"got {camera!r}"
            )
        if str(manifest_frame.get("profile")) != profile:
            raise CaptureError(
                f"manifest seq {seq} profile is {manifest_frame.get('profile')!r}, "
                f"got {profile!r}"
            )

        image_path = self._frames_dir(job_id) / f"{frame_id}.jpg"
        sidecar_path = self._frames_dir(job_id) / f"{frame_id}.json"
        if image_path.exists() or sidecar_path.exists():
            raise CaptureError(f"refusing to overwrite committed frame {frame_id}")

        try:
            previous_seq = framebuffer_seq(read_framebuffer_metadata())
        except Exception:
            previous_seq = -1
        source_image, source_metadata = wait_for_buffered_frame_seq_after(
            previous_frame_seq=previous_seq,
            timeout=self.request_timeout,
            required_profile=profile,
        )
        captured_width = int(source_metadata.get("width") or 0)
        captured_height = int(source_metadata.get("height") or 0)
        if not captured_width or not captured_height:
            captured_width, captured_height = jpeg_dimensions(source_image)
        image_bytes = source_image.read_bytes()
        image_sha256 = sha256_prefixed(image_bytes)
        framebuffer_frame_seq = framebuffer_seq(source_metadata)
        sidecar = {
            "schema_version": VISION_JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "job_seq": seq,
            "frame": frame_id,
            "camera": camera,
            "profile": profile,
            "tool": params.get("tool"),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "image_path": str(image_path),
            "metadata_path": str(sidecar_path),
            "image_sha256": image_sha256,
            "width": captured_width,
            "height": captured_height,
            "size_bytes": len(image_bytes),
            "manifest_frame": manifest_frame,
            "klipper": {
                "tool": params.get("tool"),
                "toolhead_position": params.get("toolhead_position"),
                "gcode_position": params.get("gcode_position"),
                "homed_axes": params.get("homed_axes"),
                "camera": camera,
                "profile": profile,
                "job_seq": seq,
                "framebuffer_seq": framebuffer_frame_seq,
            },
            "framebuffer_seq": framebuffer_frame_seq,
            "source_frame": source_metadata,
        }
        self._commit_frame(image_path, sidecar_path, image_bytes, sidecar)

        completed_count = int(state.get("committed_frame_count") or 0) + 1
        state.update(
            {
                "committed_frame_count": completed_count,
                "next_seq": seq + 1,
                "last_committed_frame": frame_id,
                "last_framebuffer_seq": framebuffer_frame_seq,
            }
        )
        self._write_state(job_id, state)
        self._append_event(
            job_id,
            "frame_committed",
            {
                "state": "acquiring",
                "seq": seq,
                "frame": frame_id,
                "framebuffer_seq": framebuffer_frame_seq,
                "image_sha256": image_sha256,
            },
        )
        return {
            "job": job_id,
            "seq": seq,
            "frame": frame_id,
            "framebuffer_seq": framebuffer_frame_seq,
            "committed_frame_count": completed_count,
        }

    def _commit_frame(
        self,
        image_path: Path,
        sidecar_path: Path,
        image_bytes: bytes,
        sidecar: dict[str, Any],
    ) -> None:
        if image_path.exists() or sidecar_path.exists():
            raise CaptureError(f"refusing to overwrite {image_path} / {sidecar_path}")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_tmp = image_path.with_name(f".{image_path.name}.tmp")
        sidecar_tmp = sidecar_path.with_name(f".{sidecar_path.name}.tmp")
        image_tmp.unlink(missing_ok=True)
        sidecar_tmp.unlink(missing_ok=True)
        try:
            image_tmp.write_bytes(image_bytes)
            verify_jpeg(image_tmp)
            sidecar_tmp.write_text(
                json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            json.loads(sidecar_tmp.read_text(encoding="utf-8"))
            os.replace(image_tmp, image_path)
            os.replace(sidecar_tmp, sidecar_path)
            verify_jpeg(image_path)
            json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception:
            image_tmp.unlink(missing_ok=True)
            sidecar_tmp.unlink(missing_ok=True)
            image_path.unlink(missing_ok=True)
            sidecar_path.unlink(missing_ok=True)
            raise

    def job_end(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = sanitize_name(params.get("job"))
        expected_frames = int(params.get("expected_frames"))
        self._require_active(job_id)
        manifest = self._load_manifest(job_id)
        state = self._load_state(job_id)
        manifest_frame_count = int(manifest.get("frame_count") or 0)
        if expected_frames != manifest_frame_count:
            raise CaptureError(
                f"VISION_JOB_END EXPECTED_FRAMES={expected_frames} does not match "
                f"manifest frame_count={manifest_frame_count}"
            )
        completed = self._completed_frame_ids(job_id, manifest)
        if len(completed) != expected_frames:
            raise CaptureError(
                f"vision job {job_id} has {len(completed)} committed frames, "
                f"expected {expected_frames}"
            )
        if int(state.get("committed_frame_count") or 0) != expected_frames:
            raise CaptureError(
                f"state committed_frame_count={state.get('committed_frame_count')} "
                f"does not match expected {expected_frames}"
            )
        state.update(
            {
                "state": "acquired",
                "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                "committed_frame_count": expected_frames,
            }
        )
        self._write_state(job_id, state)
        self._append_event(
            job_id,
            "acquired",
            {
                "state": "acquired",
                "expected_frames": expected_frames,
                "frames": completed,
            },
        )
        self._release_lock(job_id)
        return {
            "job": job_id,
            "state": "acquired",
            "committed_frame_count": expected_frames,
        }

    def _record_failure_if_active(
        self, request: dict[str, Any], exc: Exception
    ) -> None:
        params = request.get("params") if isinstance(request, dict) else None
        if not isinstance(params, dict):
            return
        job_id = sanitize_name(params.get("job"))
        if not job_id:
            return
        if self._active_job() != job_id:
            return
        try:
            state = self._load_state(job_id)
            state.update(
                {
                    "state": "failed",
                    "failure": str(exc),
                    "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._write_state(job_id, state)
            self._append_event(
                job_id,
                "failed",
                {
                    "state": "failed",
                    "action": request.get("action"),
                    "error": str(exc),
                },
            )
        except Exception as failure_record_exc:
            log(f"Could not record vision job failure for {job_id}: {failure_record_exc}")
        try:
            self._release_lock(job_id)
        except Exception as release_exc:
            log(f"Could not release vision job lock for {job_id}: {release_exc}")


class VisiondJobSocketServer(threading.Thread):
    def __init__(
        self,
        *,
        socket_path: Path = VISIOND_SOCKET,
        api: VisionJobApi | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.socket_path = socket_path
        self.api = api or VisionJobApi()

    def run(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o666)
            server.listen(8)
            log(f"Serving synchronous vision job socket: {self.socket_path}")
            while True:
                conn, _addr = server.accept()
                threading.Thread(
                    target=self._handle_connection, args=(conn,), daemon=True
                ).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            try:
                conn.settimeout(VISIOND_SOCKET_REQUEST_TIMEOUT)
                raw = b""
                while b"\n" not in raw:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                line = raw.split(b"\n", 1)[0]
                if not line:
                    raise CaptureError("empty visiond socket request")
                request = json.loads(line.decode("utf-8"))
                if not isinstance(request, dict):
                    raise CaptureError("visiond socket request must be an object")
                response = self.api.handle(request)
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            conn.sendall(json.dumps(response, separators=(",", ":")).encode() + b"\n")


class KlippyRemoteCaptureDaemon:
    def __init__(self) -> None:
        self.capture_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(
            maxsize=20
        )
        self.worker = threading.Thread(target=self._capture_worker, daemon=True)
        self.job_socket = VisiondJobSocketServer() if VISIOND_SOCKET_ENABLED else None
        self.next_id = 1

    def _capture_worker(self) -> None:
        while True:
            job_kind, params = self.capture_queue.get()
            try:
                if job_kind == REMOTE_ACTION:
                    capture_frame(params)
                elif job_kind == NOZZLE_SWEEP_REMOTE_ACTION:
                    self._run_nozzle_sweep(params)
                elif job_kind == BED_Y_REMOTE_ACTION:
                    self._run_bed_y_sweep(params)
                elif job_kind == NOZZLE_Z_REMOTE_ACTION:
                    self._run_nozzle_z_sweep(params)
                elif job_kind == NOZZLE_PROFILE_REMOTE_ACTION:
                    self._request_nozzle_profile(params)
                else:
                    log(f"Unknown vision job kind: {job_kind}")
            except Exception as exc:
                log(f"Vision job {job_kind} failed: {exc}")
            finally:
                self.capture_queue.task_done()

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
            str(params.get("dx", "0,3,6,9,12")),
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

    def _run_bed_y_sweep(self, params: dict[str, Any]) -> None:
        command = [
            NOZZLE_ALIGN_BIN,
            "--run-bed-y-job",
            "--name",
            sanitize_name(params.get("name", "bed_y")),
            "--x",
            str(float(params.get("x", -80.4))),
            "--y",
            str(float(params.get("y", -14.8))),
            "--z",
            str(float(params.get("z", 293.75))),
            "--y-offsets",
            str(params.get("y_offsets", "0,5,10,15,20")),
            "--no-manage-crowsnest",
        ]
        result = run_command(command, timeout=420)
        if result.stdout.strip():
            log(f"Bed Y vision sweep result: {result.stdout.strip()}")
        if result.stderr.strip():
            log(f"Bed Y vision sweep stderr: {result.stderr.strip()}")
        if result.returncode != 0:
            raise CaptureError(
                result.stderr.strip()
                or result.stdout.strip()
                or "bed Y vision sweep failed"
            )

    def _run_nozzle_z_sweep(self, params: dict[str, Any]) -> None:
        command = [
            NOZZLE_ALIGN_BIN,
            "--run-nozzle-z-job",
            "--name",
            sanitize_name(params.get("name", "nozzle_z")),
            "--bed-y-x",
            str(float(params.get("bed_y_x", -80.4))),
            "--bed-y-y",
            str(float(params.get("bed_y_y", -14.8))),
            "--bed-y-z",
            str(float(params.get("bed_y_z", 293.75))),
            "--tool-x",
            str(float(params.get("tool_x", 195.0))),
            "--tool-y",
            str(float(params.get("tool_y", -14.8))),
            "--travel-z",
            str(float(params.get("travel_z", 20.0))),
            "--y-offsets",
            str(params.get("y_offsets", "0,5,10,15,20")),
            "--x-offsets",
            str(params.get("x_offsets", "0,3,6,9,12")),
            "--z-values",
            str(params.get("z_values", "1,2,4,8")),
            "--bed-feature-z-mm",
            str(float(params.get("bed_feature_z_mm", -0.1))),
            "--current-t0-z-endstop",
            str(float(params.get("current_t0_z_endstop", 293.75))),
            "--current-t1-z-endstop",
            str(float(params.get("current_t1_z_endstop", 293.65))),
            "--no-manage-crowsnest",
        ]
        result = run_command(command, timeout=900)
        if result.stdout.strip():
            log(f"Nozzle Z vision sweep result: {result.stdout.strip()}")
        if result.stderr.strip():
            log(f"Nozzle Z vision sweep stderr: {result.stderr.strip()}")
        if result.returncode != 0:
            raise CaptureError(
                result.stderr.strip()
                or result.stdout.strip()
                or "nozzle Z vision sweep failed"
            )

    def _request_nozzle_profile(self, params: dict[str, Any]) -> None:
        profile = sanitize_profile(params.get("profile") or DEFAULT_CAMERA_PROFILE)
        if not profile:
            raise CaptureError("No nozzle camera profile requested")
        requested_at = request_framebuffer_profile(profile, params)
        if requested_at is None:
            raise CaptureError("No framebuffer profile request file is configured")
        log(
            f"Requested nozzle camera profile {profile!r} at {requested_at.isoformat()}"
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
        if REGISTER_NOZZLE_METHODS:
            self._register_remote_method(
                sock, NOZZLE_SWEEP_REMOTE_METHOD, NOZZLE_SWEEP_REMOTE_ACTION
            )
            self._register_remote_method(sock, BED_Y_REMOTE_METHOD, BED_Y_REMOTE_ACTION)
            self._register_remote_method(
                sock, NOZZLE_Z_REMOTE_METHOD, NOZZLE_Z_REMOTE_ACTION
            )
            self._register_remote_method(
                sock, NOZZLE_PROFILE_REMOTE_METHOD, NOZZLE_PROFILE_REMOTE_ACTION
            )

    def _handle_message(self, message: dict[str, Any]) -> None:
        action = message.get("action")
        valid_actions = {REMOTE_ACTION}
        if REGISTER_NOZZLE_METHODS:
            valid_actions.update(
                (
                    NOZZLE_SWEEP_REMOTE_ACTION,
                    BED_Y_REMOTE_ACTION,
                    NOZZLE_Z_REMOTE_ACTION,
                    NOZZLE_PROFILE_REMOTE_ACTION,
                )
            )
        if action not in valid_actions:
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
        if self.job_socket is not None:
            self.job_socket.start()
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
    parser.add_argument(
        "--fresh-timeout", type=float, default=DEFAULT_FRAME_FRESH_TIMEOUT
    )
    parser.add_argument("--max-age", type=float, default=DEFAULT_FRAME_MAX_AGE)
    parser.add_argument("--profile", default=DEFAULT_CAMERA_PROFILE)
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
                "profile": args.profile,
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
