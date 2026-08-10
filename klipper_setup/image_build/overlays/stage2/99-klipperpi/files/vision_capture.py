#!/usr/bin/env python3
"""Framebuffer-backed manual capture and strict calibration-job frame commits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

OUTPUT_DIR = Path(os.environ.get("VISION_OUTPUT_DIR", "/home/pi/printer_data/vision"))
FRAMEBUFFER_DIR = Path(os.environ.get("VISION_FRAMEBUFFER_DIR", "/run/vision-preview"))
FRAMEBUFFER_LATEST_IMAGE = FRAMEBUFFER_DIR / "latest.jpg"
FRAMEBUFFER_LATEST_METADATA = FRAMEBUFFER_DIR / "latest.json"
PROFILE_REQUEST_ENV = os.environ.get("VISION_CAMERA_PROFILE_REQUEST_FILE", "").strip()
PROFILE_REQUEST_FILE = Path(PROFILE_REQUEST_ENV) if PROFILE_REQUEST_ENV else None
KLIPPY_SOCKET = os.environ.get(
    "VISION_KLIPPY_SOCKET", "/home/pi/printer_data/comms/klippy.sock"
)
PUBLIC_SNAPSHOT_URL = os.environ.get(
    "VISION_PUBLIC_SNAPSHOT_URL", "/webcam/?action=snapshot"
)
OUTPUT_URL_PREFIX = os.environ.get("VISION_OUTPUT_URL_PREFIX", "/vision").rstrip("/")
REMOTE_METHOD = os.environ.get("VISION_CAPTURE_REMOTE_METHOD", "vision_capture")
REMOTE_ACTION = os.environ.get("VISION_CAPTURE_REMOTE_ACTION", f"run_{REMOTE_METHOD}")
PROFILE_REMOTE_METHOD = os.environ.get(
    "VISION_PROFILE_REMOTE_METHOD", "nozzle_cam_profile"
)
PROFILE_REMOTE_ACTION = os.environ.get(
    "VISION_PROFILE_REMOTE_ACTION", "run_nozzle_cam_profile"
)
METRIC_CALIBRATION_REMOTE_METHOD = "idex_bed_fiducial_metric_calibrate"
METRIC_CALIBRATION_REMOTE_ACTION = "run_idex_bed_fiducial_metric_calibrate"
CORNER_CALIBRATION_REMOTE_METHOD = "idex_bed_tab_corner_calibrate"
CORNER_CALIBRATION_REMOTE_ACTION = "run_idex_bed_tab_corner_calibrate"
RED_MARKER_CALIBRATION_REMOTE_METHOD = "idex_red_marker_x_sweep_calibrate"
RED_MARKER_CALIBRATION_REMOTE_ACTION = "run_idex_red_marker_x_sweep_calibrate"
ROUGH_X_VERIFY_REMOTE_METHOD = "idex_rough_tool_x_verify"
ROUGH_X_VERIFY_REMOTE_ACTION = "run_idex_rough_tool_x_verify"
EDDY_FIDUCIAL_XZ_REMOTE_METHOD = "idex_eddy_fiducial_xz_acquire"
EDDY_FIDUCIAL_XZ_REMOTE_ACTION = "run_idex_eddy_fiducial_xz_acquire"
TOOL_XZ_SWEEP_REMOTE_METHOD = "idex_tool_xz_sweep_report"
TOOL_XZ_SWEEP_REMOTE_ACTION = "run_idex_tool_xz_sweep_report"
CALIBRATION_BIN = os.environ.get(
    "VISION_CALIBRATION_BIN", "/usr/local/bin/vision_calibration.py"
)
DEFAULT_PROFILE = os.environ.get("VISION_CAPTURE_DEFAULT_PROFILE", "").strip()
DEFAULT_FRAME_TIMEOUT = float(os.environ.get("VISION_FRAME_FRESH_TIMEOUT", "10"))
DEFAULT_FRAME_MAX_AGE = float(os.environ.get("VISION_FRAME_MAX_AGE", "10"))
DEFAULT_CAPTURE_RETRIES = int(os.environ.get("VISION_CAPTURE_RETRIES", "3"))
VISIOND_CAMERA = os.environ.get("VISIOND_CAMERA", "nozzle_cam")
VISIOND_SOCKET = Path(
    os.environ.get("VISIOND_SOCKET", "/run/vision-capture-nozzle_cam/visiond.sock")
)
VISIOND_ENABLED = os.environ.get("VISIOND_SOCKET_ENABLED", "0").lower() not in (
    "0",
    "false",
    "no",
    "off",
    "",
)
VISIOND_TIMEOUT = float(os.environ.get("VISIOND_SOCKET_REQUEST_TIMEOUT", "45"))
JOB_ROOT = Path(
    os.environ.get(
        "VISION_JOB_ROOT",
        "/home/pi/printer_data/vision/calibration/jobs",
    )
)
REGISTER_CALIBRATION = os.environ.get(
    "VISION_REGISTER_CALIBRATION_METHODS", "0"
).lower() not in ("0", "false", "no", "off", "")
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HASH_TOKEN_RE = re.compile(r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+")
HASH_PLACEHOLDER = "sha256:PLACEHOLDER"


class CaptureError(RuntimeError):
    pass


def log(message: str) -> None:
    print(
        f"{datetime.now(timezone.utc).isoformat()} {message}",
        file=os.sys.stderr,
        flush=True,
    )


def sanitize_name(value: Any) -> str:
    cleaned = NAME_RE.sub("_", str(value or "capture")).strip("._-")
    return (cleaned or "capture")[:80]


def sanitize_profile(value: Any) -> str:
    cleaned = NAME_RE.sub("_", str(value or "")).strip("._-")
    return cleaned[:80]


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_hash", None)
    return canonical_hash(payload)


def compute_gcode_hash(gcode: str) -> str:
    canonical = HASH_TOKEN_RE.sub(
        lambda match: f"{match.group('name')}={HASH_PLACEHOLDER}", gcode
    )
    return canonical_hash(canonical)


def verify_jpeg(path: Path) -> None:
    if not path.is_file():
        raise CaptureError(f"missing JPEG: {path}")
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise CaptureError(f"incomplete JPEG markers: {path}")
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise CaptureError(f"JPEG decode failed: {path}")


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise CaptureError(f"cannot decode JPEG dimensions: {path}")
    return int(image.shape[1]), int(image.shape[0])


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_framebuffer_metadata() -> dict[str, Any]:
    try:
        value = json.loads(FRAMEBUFFER_LATEST_METADATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CaptureError("framebuffer metadata is unavailable") from None
    if not isinstance(value, dict):
        raise CaptureError("framebuffer metadata must be an object")
    return value


def framebuffer_seq(metadata: dict[str, Any]) -> int:
    try:
        return int(metadata["frame_seq"])
    except (KeyError, TypeError, ValueError):
        raise CaptureError("framebuffer metadata has no integer frame_seq") from None


def metadata_matches_profile(metadata: dict[str, Any], profile: str | None) -> bool:
    if not profile:
        return True
    camera_profile = metadata.get("camera_profile") or {}
    names = camera_profile.get("profile_names") or []
    return profile in names


def request_framebuffer_profile(profile: str) -> str:
    if PROFILE_REQUEST_FILE is None:
        raise CaptureError("no framebuffer profile request file is configured")
    payload = {
        "profile": profile,
        "requested_at_utc": datetime.now(timezone.utc).isoformat(),
        "requester": "vision_capture",
    }
    atomic_write_json(PROFILE_REQUEST_FILE, payload)
    return payload["requested_at_utc"]


def wait_for_active_profile(profile: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_metadata: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            metadata = read_framebuffer_metadata()
            last_metadata = metadata
            if metadata_matches_profile(metadata, profile):
                return metadata
        except CaptureError:
            pass
        time.sleep(0.05)
    raise CaptureError(
        f"timed out waiting for profile {profile!r}; last={last_metadata}"
    )


def wait_for_new_frame(
    previous_seq: int,
    *,
    timeout: float,
    profile: str | None,
) -> tuple[Path, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            metadata = read_framebuffer_metadata()
            sequence = framebuffer_seq(metadata)
            if sequence <= previous_seq:
                time.sleep(0.025)
                continue
            if not metadata_matches_profile(metadata, profile):
                time.sleep(0.025)
                continue
            verify_jpeg(FRAMEBUFFER_LATEST_IMAGE)
            return FRAMEBUFFER_LATEST_IMAGE, metadata
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise CaptureError(
        f"timed out waiting for fresh framebuffer frame after {previous_seq}: "
        f"{last_error}"
    )


def wait_for_buffered_frame(
    *,
    fresh_after_utc: datetime | None,
    timeout: float,
    max_age: float,
    profile: str | None,
) -> tuple[Path, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            metadata = read_framebuffer_metadata()
            verify_jpeg(FRAMEBUFFER_LATEST_IMAGE)
            if not metadata_matches_profile(metadata, profile):
                raise CaptureError(f"active camera profile does not include {profile}")
            captured = _parse_utc(metadata.get("captured_at_utc"))
            if fresh_after_utc and (captured is None or captured <= fresh_after_utc):
                raise CaptureError("buffered frame is older than requested time")
            age = time.time() - FRAMEBUFFER_LATEST_IMAGE.stat().st_mtime
            if age > max_age:
                raise CaptureError(f"buffered frame is stale ({age:.2f}s)")
            return FRAMEBUFFER_LATEST_IMAGE, metadata
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise CaptureError(f"no usable buffered frame: {last_error}")


def update_latest_symlinks(image_path: Path, metadata_path: Path) -> None:
    for link, target in (
        (OUTPUT_DIR / "latest.jpg", image_path),
        (OUTPUT_DIR / "latest.json", metadata_path),
    ):
        link.parent.mkdir(parents=True, exist_ok=True)
        temporary = link.with_name(f".{link.name}.tmp.{os.getpid()}")
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target.name)
        temporary.replace(link)


def capture_frame(params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    name = sanitize_name(params.get("name", "capture"))
    profile = sanitize_profile(params.get("profile") or DEFAULT_PROFILE)
    fresh_after = _parse_utc(params.get("fresh_after_utc"))
    if profile:
        request_framebuffer_profile(profile)
        wait_for_active_profile(profile, DEFAULT_FRAME_TIMEOUT)
    source_path, source_metadata = wait_for_buffered_frame(
        fresh_after_utc=fresh_after,
        timeout=float(params.get("fresh_timeout", DEFAULT_FRAME_TIMEOUT)),
        max_age=float(params.get("max_age", DEFAULT_FRAME_MAX_AGE)),
        profile=profile or None,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    image_path = OUTPUT_DIR / f"{timestamp}_{name}.jpg"
    metadata_path = image_path.with_suffix(".json")
    shutil.copyfile(source_path, image_path)
    verify_jpeg(image_path)
    width, height = jpeg_dimensions(image_path)
    metadata = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "reason": params.get("reason", "manual"),
        "width": width,
        "height": height,
        "size_bytes": image_path.stat().st_size,
        "sha256": file_hash(image_path),
        "image_path": str(image_path),
        "image_url": f"{OUTPUT_URL_PREFIX}/{image_path.name}",
        "source_latest_url": PUBLIC_SNAPSHOT_URL,
        "capture_source": "vision_framebuffer",
        "framebuffer_seq": framebuffer_seq(source_metadata),
        "camera_profile": source_metadata.get("camera_profile"),
        "klipper": params,
    }
    atomic_write_json(metadata_path, metadata)
    update_latest_symlinks(image_path, metadata_path)
    log(f"Persisted buffered vision frame: {image_path}")
    return metadata


class VisionJobApi:
    def __init__(
        self,
        *,
        job_root: Path = JOB_ROOT,
        camera: str = VISIOND_CAMERA,
        request_timeout: float = VISIOND_TIMEOUT,
    ) -> None:
        self.job_root = job_root
        self.camera = camera
        self.request_timeout = request_timeout
        self.lock_path = job_root / ".active_job.json"

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise CaptureError("request params must be an object")
            handlers = {
                "job_begin": self.job_begin,
                "profile": self.profile,
                "capture": self.capture,
                "job_end": self.job_end,
            }
            action = str(request.get("action") or "")
            if action not in handlers:
                raise CaptureError(f"unknown request action {action!r}")
            return {"ok": True, "result": handlers[action](params)}
        except Exception as exc:
            self._record_failure_if_active(request, exc)
            return {"ok": False, "error": str(exc)}

    def _job_dir(self, job_id: Any) -> Path:
        return self.job_root / sanitize_name(job_id)

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
            raise CaptureError(f"missing calibration manifest: {path}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("schema") != "vision-calibration-acquisition-manifest":
            raise CaptureError("unsupported acquisition manifest schema")
        if manifest.get("schema_version") != 1:
            raise CaptureError("unsupported acquisition manifest schema_version")
        if manifest.get("job_type") not in (
            "nozzle_cam_bed_fiducial_y_metric",
            "nozzle_cam_bed_tab_corner",
            "idex_tool_red_marker_x_sweep",
            "idex_rough_tool_x_verify",
            "idex_eddy_fiducial_xz_grid",
            "idex_tool_xy_measure_t0",
            "idex_tool_xy_measure_t1",
            "idex_tool_xz_sweep_report",
        ):
            raise CaptureError("unsupported acquisition job_type")
        if manifest.get("job_id") != sanitize_name(job_id):
            raise CaptureError("manifest job_id does not match JOB")
        if manifest.get("camera") != self.camera:
            raise CaptureError("manifest camera does not match capture service")
        if compute_manifest_hash(manifest) != manifest.get("manifest_hash"):
            raise CaptureError("manifest content hash mismatch")
        return manifest

    def _load_state(self, job_id: Any) -> dict[str, Any]:
        path = self._state_path(job_id)
        if not path.exists():
            raise CaptureError(f"missing calibration job state: {path}")
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

    def _active_job(self) -> str | None:
        if not self.lock_path.exists():
            return None
        try:
            return str(
                json.loads(self.lock_path.read_text(encoding="utf-8")).get("job", "")
            )
        except Exception:
            return ""

    def _acquire_lock(self, job_id: str) -> str | None:
        self.job_root.mkdir(parents=True, exist_ok=True)
        displaced_job = self._active_job()
        if self.lock_path.exists():
            if displaced_job and displaced_job != job_id:
                try:
                    state = self._load_state(displaced_job)
                    previous_state = state.get("state")
                    if previous_state == "acquiring":
                        state.update(
                            {
                                "state": "failed",
                                "failure": (
                                    f"acquisition lock replaced by job {job_id}"
                                ),
                                "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                                "superseded_by_job": job_id,
                            }
                        )
                        self._write_state(displaced_job, state)
                    self._append_event(
                        displaced_job,
                        "acquisition_lock_replaced",
                        {
                            "state": state.get("state"),
                            "previous_state": previous_state,
                            "superseded_by_job": job_id,
                        },
                    )
                except Exception as exc:
                    log(f"Could not update displaced job {displaced_job}: {exc}")
            self.lock_path.unlink(missing_ok=True)
        with self.lock_path.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "job": job_id,
                        "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                )
                + "\n"
            )
        return displaced_job if displaced_job != job_id else None

    def _release_lock(self, job_id: str) -> None:
        active = self._active_job()
        if active and active != job_id:
            raise CaptureError(f"active job lock belongs to {active!r}, not {job_id!r}")
        self.lock_path.unlink(missing_ok=True)

    def _require_active(self, job_id: str) -> None:
        if self._active_job() != job_id:
            raise CaptureError(f"active job is {self._active_job()!r}, not {job_id!r}")

    def _frame(self, manifest: dict[str, Any], seq: int) -> dict[str, Any]:
        for frame in manifest["frames"]:
            if frame["seq"] == seq:
                return frame
        raise CaptureError(f"manifest has no frame with seq={seq}")

    def _verify_hashes(
        self,
        manifest: dict[str, Any],
        manifest_hash: str,
        gcode_hash: str,
    ) -> None:
        if manifest_hash != manifest["manifest_hash"]:
            raise CaptureError("manifest hash mismatch")
        if gcode_hash != manifest["gcode_hash"]:
            raise CaptureError("G-code hash mismatch")
        path = self._job_dir(manifest["job_id"]) / manifest["gcode_file"]
        if not path.is_file():
            raise CaptureError(f"missing acquisition G-code: {path}")
        if compute_gcode_hash(path.read_text(encoding="utf-8")) != gcode_hash:
            raise CaptureError("acquisition G-code content hash mismatch")

    def job_begin(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = sanitize_name(params.get("job"))
        manifest = self._load_manifest(job_id)
        state = self._load_state(job_id)
        if state.get("state") != "prepared":
            raise CaptureError(
                f"calibration job is {state.get('state')!r}, expected 'prepared'"
            )
        self._verify_hashes(
            manifest,
            str(params.get("manifest_hash") or ""),
            str(params.get("gcode_hash") or ""),
        )
        committed = list(self._frames_dir(job_id).glob("*.jpg"))
        if committed:
            raise CaptureError("prepared job already contains committed frames")
        displaced_job = self._acquire_lock(job_id)
        state.update(
            {
                "state": "acquiring",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "committed_frame_count": 0,
                "next_seq": 0,
            }
        )
        self._write_state(job_id, state)
        self._append_event(
            job_id,
            "acquiring",
            {"state": "acquiring", "displaced_job": displaced_job},
        )
        return {
            "job": job_id,
            "state": "acquiring",
            "displaced_job": displaced_job,
        }

    def profile(self, params: dict[str, Any]) -> dict[str, Any]:
        camera = sanitize_name(params.get("camera"))
        profile = sanitize_profile(params.get("profile"))
        if camera != self.camera:
            raise CaptureError(f"camera {camera!r} is not {self.camera!r}")
        if not profile:
            raise CaptureError("PROFILE is required")
        requested_at = request_framebuffer_profile(profile)
        metadata = wait_for_active_profile(profile, self.request_timeout)
        return {
            "camera": camera,
            "profile": profile,
            "requested_at_utc": requested_at,
            "framebuffer_seq": framebuffer_seq(metadata),
        }

    def capture(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = sanitize_name(params.get("job"))
        self._require_active(job_id)
        manifest = self._load_manifest(job_id)
        state = self._load_state(job_id)
        if state.get("state") != "acquiring":
            raise CaptureError("job is not acquiring")
        seq = int(params.get("seq"))
        expected_seq = int(state.get("next_seq", 0))
        if seq != expected_seq:
            raise CaptureError(f"expected job seq {expected_seq}, got {seq}")
        frame = self._frame(manifest, seq)
        if params.get("frame") != frame["frame"]:
            raise CaptureError(
                f"frame is {params.get('frame')!r}, expected {frame['frame']!r}"
            )
        if params.get("camera") != manifest["camera"]:
            raise CaptureError("camera is inconsistent with manifest")
        frame_profile = frame["profile"]
        if params.get("profile") != frame_profile:
            raise CaptureError("profile is inconsistent with manifest")
        if params.get("tool") != frame["tool"]:
            raise CaptureError("tool is inconsistent with manifest")
        frames_dir = self._frames_dir(job_id)
        image_path = frames_dir / f"{frame['frame']}.jpg"
        sidecar_path = frames_dir / f"{frame['frame']}.json"
        if image_path.exists() or sidecar_path.exists():
            raise CaptureError(f"refusing to overwrite frame {frame['frame']}")
        previous_seq = framebuffer_seq(read_framebuffer_metadata())
        discarded_framebuffer_sequences = []
        for _index in range(int(frame.get("discard_fresh_frames") or 0)):
            _discarded_path, discarded_metadata = wait_for_new_frame(
                previous_seq,
                timeout=self.request_timeout,
                profile=frame_profile,
            )
            previous_seq = framebuffer_seq(discarded_metadata)
            discarded_framebuffer_sequences.append(previous_seq)
        source_path, source_metadata = wait_for_new_frame(
            previous_seq,
            timeout=self.request_timeout,
            profile=frame_profile,
        )
        temporary_image = frames_dir / f".{frame['frame']}.tmp.jpg"
        shutil.copyfile(source_path, temporary_image)
        verify_jpeg(temporary_image)
        width, height = jpeg_dimensions(temporary_image)
        image_sha256 = file_hash(temporary_image)
        sidecar = {
            "schema": "vision-calibration-frame-sidecar",
            "schema_version": 1,
            "job_id": job_id,
            "job_seq": seq,
            "frame": frame["frame"],
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "commanded_position_mm": frame["commanded_position_mm"],
            "y_offset_mm": frame.get("y_offset_mm"),
            "x_mm": frame.get("x_mm"),
            "pass": frame.get("pass"),
            "duplicate_index": frame.get("duplicate_index"),
            "actual_toolhead_position_mm": params.get("toolhead_position"),
            "actual_gcode_position_mm": params.get("gcode_position"),
            "homed_axes": params.get("homed_axes"),
            "temperatures": params.get("temperatures"),
            "framebuffer_seq": framebuffer_seq(source_metadata),
            "discarded_framebuffer_sequences": discarded_framebuffer_sequences,
            "width": width,
            "height": height,
            "size_bytes": temporary_image.stat().st_size,
            "sha256": image_sha256,
            "camera_profile": source_metadata.get("camera_profile"),
            "framebuffer_captured_at_utc": source_metadata.get("captured_at_utc"),
            "capture_errors": source_metadata.get("capture_errors", 0),
            "capture_retries": source_metadata.get("capture_retries", 0),
        }
        atomic_write_json(sidecar_path, sidecar)
        temporary_image.replace(image_path)
        state["committed_frame_count"] = seq + 1
        state["next_seq"] = seq + 1
        state["last_framebuffer_seq"] = sidecar["framebuffer_seq"]
        self._write_state(job_id, state)
        self._append_event(
            job_id,
            "frame_committed",
            {
                "seq": seq,
                "frame": frame["frame"],
                "sha256": image_sha256,
                "framebuffer_seq": sidecar["framebuffer_seq"],
            },
        )
        return sidecar

    def job_end(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = sanitize_name(params.get("job"))
        self._require_active(job_id)
        manifest = self._load_manifest(job_id)
        state = self._load_state(job_id)
        expected = int(params.get("expected_frames"))
        if expected != manifest["frame_count"]:
            raise CaptureError("EXPECTED_FRAMES does not match manifest")
        committed = int(state.get("committed_frame_count", 0))
        if committed != expected:
            raise CaptureError(
                f"job has {committed} committed frames, expected {expected}"
            )
        state.update(
            {
                "state": "acquired",
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._write_state(job_id, state)
        self._append_event(job_id, "acquired", {"state": "acquired"})
        self._release_lock(job_id)
        return {"job": job_id, "state": "acquired", "frame_count": committed}

    def _record_failure_if_active(
        self, request: dict[str, Any], exc: Exception
    ) -> None:
        params = request.get("params") or {}
        job_id = sanitize_name(params.get("job")) if isinstance(params, dict) else ""
        if not job_id or self._active_job() != job_id:
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
                {"state": "failed", "error": str(exc)},
            )
        finally:
            self._release_lock(job_id)


class VisiondSocketServer(threading.Thread):
    def __init__(self, api: VisionJobApi | None = None) -> None:
        super().__init__(daemon=True)
        self.api = api or VisionJobApi()

    def run(self) -> None:
        VISIOND_SOCKET.parent.mkdir(parents=True, exist_ok=True)
        VISIOND_SOCKET.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(VISIOND_SOCKET))
            os.chmod(VISIOND_SOCKET, 0o666)
            server.listen(8)
            log(f"Serving synchronized capture socket: {VISIOND_SOCKET}")
            while True:
                connection, _address = server.accept()
                threading.Thread(
                    target=self._handle, args=(connection,), daemon=True
                ).start()

    def _handle(self, connection: socket.socket) -> None:
        with connection:
            try:
                connection.settimeout(VISIOND_TIMEOUT)
                raw = b""
                while b"\n" not in raw:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                request = json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))
                response = self.api.handle(request)
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            connection.sendall(
                json.dumps(response, separators=(",", ":")).encode() + b"\n"
            )


class KlippyRemoteDaemon:
    def __init__(self) -> None:
        self.jobs: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=20)
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.socket_server = VisiondSocketServer() if VISIOND_ENABLED else None
        self.next_id = 1

    def _worker(self) -> None:
        while True:
            action, params = self.jobs.get()
            try:
                if action == REMOTE_ACTION:
                    capture_frame(params)
                elif action == PROFILE_REMOTE_ACTION:
                    profile = sanitize_profile(params.get("profile") or DEFAULT_PROFILE)
                    request_framebuffer_profile(profile)
                    wait_for_active_profile(profile, VISIOND_TIMEOUT)
                elif action == METRIC_CALIBRATION_REMOTE_ACTION:
                    command = [
                        CALIBRATION_BIN,
                        "run",
                        "nozzle_cam_bed_fiducial_y_metric",
                        "--name",
                        sanitize_name(params.get("name", "bed_fiducial_metric")),
                    ]
                    fingerprint = str(params.get("active_config_fingerprint") or "")
                    if fingerprint:
                        command.extend(["--expected-fingerprint", fingerprint])
                    result = subprocess.run(
                        command,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=300,
                    )
                    if result.stdout.strip():
                        log(result.stdout.strip())
                    if result.returncode:
                        raise CaptureError(
                            result.stderr.strip()
                            or "bed-fiducial metric calibration job failed"
                        )
                elif action == CORNER_CALIBRATION_REMOTE_ACTION:
                    command = [
                        CALIBRATION_BIN,
                        "run",
                        "nozzle_cam_bed_tab_corner",
                        "--name",
                        sanitize_name(params.get("name", "bed_tab_corner")),
                    ]
                    fingerprint = str(params.get("active_config_fingerprint") or "")
                    if fingerprint:
                        command.extend(["--expected-fingerprint", fingerprint])
                    result = subprocess.run(
                        command,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=300,
                    )
                    if result.stdout.strip():
                        log(result.stdout.strip())
                    if result.returncode:
                        raise CaptureError(
                            result.stderr.strip()
                            or "bed-tab corner calibration job failed"
                        )
                elif action == RED_MARKER_CALIBRATION_REMOTE_ACTION:
                    command = [
                        CALIBRATION_BIN,
                        "run",
                        "idex_tool_red_marker_x_sweep",
                        "--name",
                        sanitize_name(params.get("name", "red_marker_x_sweep")),
                    ]
                    fingerprint = str(params.get("active_config_fingerprint") or "")
                    if fingerprint:
                        command.extend(["--expected-fingerprint", fingerprint])
                    result = subprocess.run(
                        command,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=360,
                    )
                    if result.stdout.strip():
                        log(result.stdout.strip())
                    if result.returncode:
                        raise CaptureError(
                            result.stderr.strip()
                            or "red-marker X calibration job failed"
                        )
                elif action == ROUGH_X_VERIFY_REMOTE_ACTION:
                    command = [
                        CALIBRATION_BIN,
                        "run",
                        "idex_rough_tool_x_verify",
                        "--name",
                        sanitize_name(params.get("name", "rough_x_verify")),
                    ]
                    fingerprint = str(params.get("active_config_fingerprint") or "")
                    if fingerprint:
                        command.extend(["--expected-fingerprint", fingerprint])
                    result = subprocess.run(
                        command,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=300,
                    )
                    if result.stdout.strip():
                        log(result.stdout.strip())
                    if result.returncode:
                        raise CaptureError(
                            result.stderr.strip() or "rough-X verification job failed"
                        )
                elif action == EDDY_FIDUCIAL_XZ_REMOTE_ACTION:
                    command = [
                        CALIBRATION_BIN,
                        "run",
                        "idex_eddy_fiducial_xz_grid",
                        "--name",
                        sanitize_name(params.get("name", "eddy_fiducial_xz")),
                    ]
                    fingerprint = str(params.get("active_config_fingerprint") or "")
                    if fingerprint:
                        command.extend(["--expected-fingerprint", fingerprint])
                    result = subprocess.run(
                        command,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=600,
                    )
                    if result.stdout.strip():
                        log(result.stdout.strip())
                    if result.returncode:
                        raise CaptureError(
                            result.stderr.strip()
                            or "Eddy fiducial X/Z acquisition job failed"
                        )
                elif action == TOOL_XZ_SWEEP_REMOTE_ACTION:
                    command = [
                        CALIBRATION_BIN,
                        "run",
                        "idex_tool_xz_sweep_report",
                        "--name",
                        sanitize_name(params.get("name", "tool_xz_sweep_report")),
                    ]
                    fingerprint = str(params.get("active_config_fingerprint") or "")
                    if fingerprint:
                        command.extend(["--expected-fingerprint", fingerprint])
                    result = subprocess.run(
                        command,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=900,
                    )
                    if result.stdout.strip():
                        log(result.stdout.strip())
                    if result.returncode:
                        raise CaptureError(
                            result.stderr.strip()
                            or "combined tool X/Z sweep report failed"
                        )
                else:
                    raise CaptureError(f"unknown queued action {action}")
            except Exception as exc:
                log(f"vision action {action} failed: {exc}")
            finally:
                self.jobs.task_done()

    def _send(self, sock: socket.socket, payload: dict[str, Any]) -> None:
        sock.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\x03")

    def _register_method(
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
        self._register_method(sock, REMOTE_METHOD, REMOTE_ACTION)
        if PROFILE_REQUEST_FILE is not None:
            self._register_method(sock, PROFILE_REMOTE_METHOD, PROFILE_REMOTE_ACTION)
        if REGISTER_CALIBRATION:
            self._register_method(
                sock,
                METRIC_CALIBRATION_REMOTE_METHOD,
                METRIC_CALIBRATION_REMOTE_ACTION,
            )
            self._register_method(
                sock,
                CORNER_CALIBRATION_REMOTE_METHOD,
                CORNER_CALIBRATION_REMOTE_ACTION,
            )
            self._register_method(
                sock,
                RED_MARKER_CALIBRATION_REMOTE_METHOD,
                RED_MARKER_CALIBRATION_REMOTE_ACTION,
            )
            self._register_method(
                sock,
                ROUGH_X_VERIFY_REMOTE_METHOD,
                ROUGH_X_VERIFY_REMOTE_ACTION,
            )
            self._register_method(
                sock,
                EDDY_FIDUCIAL_XZ_REMOTE_METHOD,
                EDDY_FIDUCIAL_XZ_REMOTE_ACTION,
            )
            self._register_method(
                sock,
                TOOL_XZ_SWEEP_REMOTE_METHOD,
                TOOL_XZ_SWEEP_REMOTE_ACTION,
            )

    def _handle_message(self, message: dict[str, Any]) -> None:
        action = message.get("action")
        valid = {REMOTE_ACTION, PROFILE_REMOTE_ACTION}
        if REGISTER_CALIBRATION:
            valid.add(METRIC_CALIBRATION_REMOTE_ACTION)
            valid.add(CORNER_CALIBRATION_REMOTE_ACTION)
            valid.add(RED_MARKER_CALIBRATION_REMOTE_ACTION)
            valid.add(ROUGH_X_VERIFY_REMOTE_ACTION)
            valid.add(EDDY_FIDUCIAL_XZ_REMOTE_ACTION)
            valid.add(TOOL_XZ_SWEEP_REMOTE_ACTION)
        if action not in valid:
            return
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {"raw_params": params}
        try:
            self.jobs.put_nowait((action, params))
        except queue.Full:
            log("vision queue is full; dropping request")

    def run(self) -> None:
        self.worker.start()
        if self.socket_server is not None:
            self.socket_server.start()
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
                            if raw:
                                self._handle_message(json.loads(raw.decode()))
            except Exception as exc:
                log(f"Klipper remote bridge disconnected: {exc}")
                time.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--capture-once", metavar="NAME")
    parser.add_argument("--fresh-after-utc")
    parser.add_argument("--fresh-timeout", type=float, default=DEFAULT_FRAME_TIMEOUT)
    parser.add_argument("--max-age", type=float, default=DEFAULT_FRAME_MAX_AGE)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--retries", type=int, default=DEFAULT_CAPTURE_RETRIES)
    parser.add_argument("--require-high-res", action="store_true")
    parser.add_argument("--no-crowsnest-management", action="store_true")
    args = parser.parse_args()
    if args.capture_once:
        result = capture_frame(
            {
                "name": args.capture_once,
                "reason": "capture_once",
                "fresh_after_utc": args.fresh_after_utc,
                "fresh_timeout": args.fresh_timeout,
                "max_age": args.max_age,
                "profile": args.profile,
                "retries": args.retries,
            }
        )
        if args.require_high_res and (
            result["width"] < 1920 or result["height"] < 1080
        ):
            raise CaptureError(
                f"captured {result['width']}x{result['height']}, expected high-res"
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.daemon:
        KlippyRemoteDaemon().run()
        return 0
    parser.error("choose --daemon or --capture-once")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
