#!/usr/bin/env python3
"""Manual IDEX nozzle vision sweep runner.

This is intentionally report-only. It captures fresh buffered T0 and T1 frames
across a small commanded X sweep, runs the same analysis path for every image,
and writes debug artifacts under /home/pi/printer_data/vision/nozzle_sweep/.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"
VISION_DIR = Path(os.environ.get("VISION_OUTPUT_DIR", "/home/pi/printer_data/vision"))
VISION_ROOT_DIR = VISION_DIR.parent if VISION_DIR.name == "nozzle_cam" else VISION_DIR
NOZZLE_SWEEP_DIR = VISION_DIR / "nozzle_sweep"
NOZZLE_CAMERA_VISION_DIR = (
    VISION_DIR if VISION_DIR.name == "nozzle_cam" else VISION_DIR / "nozzle_cam"
)
NOZZLE_JOB_ROOT = Path(
    os.environ.get("VISION_NOZZLE_JOB_ROOT", str(NOZZLE_CAMERA_VISION_DIR / "jobs"))
)
DEFAULT_VIRTUAL_SD_ROOT = Path(
    os.environ.get("VISION_VIRTUAL_SD_ROOT", "/home/pi/printer_data/gcodes")
)
DEFAULT_VIRTUAL_SD_SUBDIR = os.environ.get(
    "VISION_VIRTUAL_SD_SUBDIR", "vision_jobs"
)
VISION_URL_PREFIX = os.environ.get("VISION_OUTPUT_URL_PREFIX", "/vision").rstrip("/")
VISION_ROOT_URL_PREFIX = (
    VISION_URL_PREFIX[: -len("/nozzle_cam")]
    if VISION_URL_PREFIX.endswith("/nozzle_cam")
    else VISION_URL_PREFIX
)
CAPTURE_BIN = os.environ.get("VISION_CAPTURE_BIN", "/usr/local/bin/vision_capture.py")
CROWSNEST_SERVICE = os.environ.get("VISION_CROWSNEST_SERVICE", "crowsnest")
CROWSNEST_HOST = os.environ.get("VISION_CROWSNEST_HOST", "127.0.0.1")
CROWSNEST_PORT = int(os.environ.get("VISION_CROWSNEST_PORT", "8080"))
WEBCAM_SNAPSHOT_URL = os.environ.get(
    "VISION_WEBCAM_SNAPSHOT_URL", "http://127.0.0.1/webcam/?action=snapshot"
)
WEBCAM_READY_TIMEOUT = float(os.environ.get("VISION_WEBCAM_READY_TIMEOUT", "25"))
RED_BASE_WIDTH = 1920.0
RED_BASE_HEIGHT = 1080.0
RED_MARKER_ROI_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_RED_ROI_1080", "920,330,260,190").split(",")
)
NOZZLE_FEATURE_OFFSET_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_SWEEP_FEATURE_OFFSET_1080", "25,100").split(",")
)
NOZZLE_ROI_SIZE_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_SWEEP_ROI_SIZE_1080", "120,96").split(",")
)
NOZZLE_GLOBAL_MATCH_MARGIN_1080 = float(
    os.environ.get("VISION_NOZZLE_SWEEP_GLOBAL_MARGIN_1080", "36")
)
NOZZLE_GLOBAL_MATCH_SEARCH_1080 = float(
    os.environ.get("VISION_NOZZLE_SWEEP_MATCH_SEARCH_1080", "150")
)
PUBLIC_BASE_URL = os.environ.get("VISION_PUBLIC_BASE_URL", "http://menderpi.local")
NAME_REPLACEMENTS = str.maketrans({c: "_" for c in " /\\:;|?*[]{}()<>'\"`$&!"})
VISION_JOB_SCHEMA_VERSION = 1
VISION_JOB_KIND = "idex_nozzle_sweep"
VISION_JOB_CAMERA = "nozzle_cam"
VISION_JOB_PROFILE = "analysis"
VISION_JOB_LIGHTING = "NOZZLE_CAM_ANALYSIS_LIGHT"
VISION_HASH_PLACEHOLDER = "sha256:PLACEHOLDER"
HASHED_GCODE_TOKEN_RE = re.compile(
    r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+"
)


@dataclass(frozen=True)
class VisionJobFrame:
    seq: int
    frame: str
    tool: str
    dx: float
    x: float
    y: float
    z: float
    feedrate: float
    settle_ms: int
    lighting: str
    camera: str
    profile: str

    @property
    def tool_key(self) -> str:
        return self.tool.lower()

    def manifest_record(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "frame": self.frame,
            "tool": self.tool,
            "dx": self.dx,
            "pose": {
                "x": round(self.x, 4),
                "y": round(self.y, 4),
                "z": round(self.z, 4),
            },
            "feedrate": round(self.feedrate, 3),
            "settle_ms": self.settle_ms,
            "lighting": self.lighting,
            "camera": self.camera,
            "profile": self.profile,
            "capture_command": "VISION_CAPTURE_SYNC",
        }


@dataclass(frozen=True)
class VisionJob:
    job_id: str
    kind: str
    created_at_utc: str
    camera: str
    profile: str
    job_dir: Path
    manifest_path: Path
    gcode_path: Path
    state_path: Path
    events_path: Path
    frames_dir: Path
    analysis_dir: Path
    frames: tuple[VisionJobFrame, ...]
    manifest_hash: str = VISION_HASH_PLACEHOLDER
    gcode_hash: str = VISION_HASH_PLACEHOLDER


def sanitize_name(value: Any) -> str:
    text = str(value or "nozzle_align").translate(NAME_REPLACEMENTS).strip("._-")
    return (text or "nozzle_align")[:80]


def prefixed_url(prefix: str, relative_path: str) -> str:
    if not prefix:
        return "/" + relative_path.lstrip("/")
    return prefix + "/" + relative_path.lstrip("/")


def prefixed_vision_url(relative_path: str) -> str:
    return prefixed_url(VISION_URL_PREFIX, relative_path)


def prefixed_root_vision_url(relative_path: str) -> str:
    return prefixed_url(VISION_ROOT_URL_PREFIX, relative_path)


def vision_url(path: Path) -> str:
    return prefixed_vision_url(path.relative_to(VISION_DIR).as_posix())


def root_vision_url(path: Path) -> str:
    return prefixed_root_vision_url(path.relative_to(VISION_ROOT_DIR).as_posix())


def public_url(path_or_url: Path | str) -> str:
    if isinstance(path_or_url, Path):
        try:
            relative_url = vision_url(path_or_url)
        except ValueError:
            relative_url = str(path_or_url)
    else:
        relative_url = path_or_url
    return PUBLIC_BASE_URL.rstrip("/") + "/" + relative_url.lstrip("/")


def console_respond(base_url: str, message: str) -> None:
    safe = message.replace("\\", "/").replace('"', "'")
    try:
        run_gcode(base_url, f'RESPOND TYPE=echo MSG="{safe}"', timeout=10)
    except Exception:
        pass


def parse_dx_values(value: str) -> list[float]:
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not values:
        raise ValueError("DX list is empty")
    return values


def dx_label(dx: float) -> str:
    return str(dx).replace("-", "m").replace(".", "p")


def gcode_float(value: float) -> str:
    return f"{value:.3f}"


def settle_time_to_ms(settle_time_s: float) -> int:
    return max(0, int(round(settle_time_s * 1000.0)))


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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def generated_job_id(name: str, timestamp: datetime) -> str:
    timestamp_part = timestamp.strftime("%Y%m%dT%H%M%SZ")
    return f"{VISION_JOB_KIND}_{timestamp_part}_{sanitize_name(name)}"


def build_nozzle_sweep_job_frames(
    *,
    x: float,
    y: float,
    z: float,
    dx_values: list[float],
    feedrate: float,
    settle_ms: int,
    camera: str,
    profile: str,
) -> tuple[VisionJobFrame, ...]:
    frames: list[VisionJobFrame] = []
    for tool in ("T0", "T1"):
        for dx in dx_values:
            frame_id = f"{tool.lower()}_dx{dx_label(dx)}"
            frames.append(
                VisionJobFrame(
                    seq=len(frames),
                    frame=frame_id,
                    tool=tool,
                    dx=dx,
                    x=x + dx,
                    y=y,
                    z=z,
                    feedrate=feedrate,
                    settle_ms=settle_ms,
                    lighting=VISION_JOB_LIGHTING,
                    camera=camera,
                    profile=profile,
                )
            )
    return tuple(frames)


def build_vision_job(
    *,
    name: str,
    job_root: Path,
    job_id: str | None,
    x: float,
    y: float,
    z: float,
    dx_values: list[float],
    feedrate: float,
    settle_time: float,
    camera: str,
    profile: str,
    now: datetime | None = None,
) -> VisionJob:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    resolved_job_id = (
        sanitize_name(job_id) if job_id else generated_job_id(name, timestamp)
    )
    job_dir = job_root / resolved_job_id
    frames = build_nozzle_sweep_job_frames(
        x=x,
        y=y,
        z=z,
        dx_values=dx_values,
        feedrate=feedrate,
        settle_ms=settle_time_to_ms(settle_time),
        camera=camera,
        profile=profile,
    )
    return VisionJob(
        job_id=resolved_job_id,
        kind=VISION_JOB_KIND,
        created_at_utc=timestamp.isoformat(),
        camera=camera,
        profile=profile,
        job_dir=job_dir,
        manifest_path=job_dir / "manifest.json",
        gcode_path=job_dir / "acquisition.gcode",
        state_path=job_dir / "state.json",
        events_path=job_dir / "events.jsonl",
        frames_dir=job_dir / "frames",
        analysis_dir=job_dir / "analysis",
        frames=frames,
    )


def render_acquisition_gcode(
    job: VisionJob,
    *,
    manifest_hash: str,
    gcode_hash: str,
) -> str:
    lines = [
        f"; generated vision job: {job.job_id}",
        f"; kind: {job.kind}",
        f"; run dir: {job.job_dir}",
        "",
        "G90",
        (
            f"VISION_JOB_BEGIN JOB={job.job_id} "
            f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
        ),
        f"VISION_PROFILE CAMERA={job.camera} PROFILE={job.profile}",
        VISION_JOB_LIGHTING,
        "",
    ]
    active_tool: str | None = None
    for frame in job.frames:
        if frame.tool != active_tool:
            lines.append(frame.tool)
            active_tool = frame.tool
        lines.extend(
            [
                (
                    f"G1 X{gcode_float(frame.x)} Y{gcode_float(frame.y)} "
                    f"Z{gcode_float(frame.z)} F{frame.feedrate:.0f}"
                ),
                "M400",
                f"G4 P{frame.settle_ms}",
                (
                    f"VISION_CAPTURE_SYNC JOB={job.job_id} SEQ={frame.seq} "
                    f"FRAME={frame.frame} CAMERA={frame.camera} "
                    f"PROFILE={frame.profile} TOOL={frame.tool}"
                ),
                "",
            ]
        )
    lines.append(f"VISION_JOB_END JOB={job.job_id} EXPECTED_FRAMES={len(job.frames)}")
    return "\n".join(lines) + "\n"


def build_manifest(job: VisionJob) -> dict[str, Any]:
    return {
        "schema_version": VISION_JOB_SCHEMA_VERSION,
        "job_id": job.job_id,
        "kind": job.kind,
        "camera": job.camera,
        "profile": job.profile,
        "created_at_utc": job.created_at_utc,
        "manifest_hash": job.manifest_hash,
        "gcode_file": job.gcode_path.name,
        "gcode_hash": job.gcode_hash,
        "frame_count": len(job.frames),
        "state": "prepared",
        "preconditions": {
            "required_homed_axes": "xyz",
            "require_idle": True,
        },
        "frames": [frame.manifest_record() for frame in job.frames],
    }


def job_with_hashes(job: VisionJob) -> VisionJob:
    canonical_gcode = render_acquisition_gcode(
        job,
        manifest_hash=VISION_HASH_PLACEHOLDER,
        gcode_hash=VISION_HASH_PLACEHOLDER,
    )
    gcode_hash = compute_gcode_hash(canonical_gcode)
    manifest_for_hash = build_manifest(
        replace(job, manifest_hash=VISION_HASH_PLACEHOLDER, gcode_hash=gcode_hash)
    )
    manifest_hash = compute_manifest_hash(manifest_for_hash)
    return replace(job, manifest_hash=manifest_hash, gcode_hash=gcode_hash)


def prepare_nozzle_sweep_job(args: argparse.Namespace) -> dict[str, Any]:
    job = build_vision_job(
        name=args.name,
        job_root=Path(args.job_root),
        job_id=args.job_id,
        x=float(args.x),
        y=float(args.y),
        z=float(args.z),
        dx_values=parse_dx_values(args.dx),
        feedrate=float(args.feedrate),
        settle_time=float(args.settle_time),
        camera=sanitize_name(args.camera),
        profile=sanitize_name(args.profile),
    )
    if job.job_dir.exists():
        raise FileExistsError(f"Vision job directory already exists: {job.job_dir}")
    job = job_with_hashes(job)
    manifest = build_manifest(job)
    gcode = render_acquisition_gcode(
        job,
        manifest_hash=job.manifest_hash,
        gcode_hash=job.gcode_hash,
    )
    state = {
        "schema_version": VISION_JOB_SCHEMA_VERSION,
        "job_id": job.job_id,
        "kind": job.kind,
        "state": "prepared",
        "created_at_utc": job.created_at_utc,
        "updated_at_utc": job.created_at_utc,
        "frame_count": len(job.frames),
        "committed_frame_count": 0,
        "manifest_hash": job.manifest_hash,
        "gcode_hash": job.gcode_hash,
    }
    event = {
        "timestamp_utc": job.created_at_utc,
        "job_id": job.job_id,
        "event": "prepared",
        "state": "prepared",
        "manifest_hash": job.manifest_hash,
        "gcode_hash": job.gcode_hash,
    }

    job.frames_dir.mkdir(parents=True)
    job.analysis_dir.mkdir(parents=True)
    atomic_write_json(job.manifest_path, manifest)
    atomic_write_text(job.gcode_path, gcode)
    atomic_write_json(job.state_path, state)
    atomic_write_text(job.events_path, json.dumps(event, sort_keys=True) + "\n")

    return {
        "ok": True,
        "job_id": job.job_id,
        "job_dir": str(job.job_dir),
        "manifest_path": str(job.manifest_path),
        "gcode_path": str(job.gcode_path),
        "state_path": str(job.state_path),
        "events_path": str(job.events_path),
        "state": "prepared",
        "frame_count": len(job.frames),
        "manifest_hash": job.manifest_hash,
        "gcode_hash": job.gcode_hash,
    }


def load_job_frames_for_analysis(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job_dir = manifest_path.parent
    frames: list[dict[str, Any]] = []
    for frame in manifest["frames"]:
        frame_id = frame["frame"]
        image_path = job_dir / "frames" / f"{frame_id}.jpg"
        metadata_path = job_dir / "frames" / f"{frame_id}.json"
        if not image_path.exists():
            raise FileNotFoundError(f"Missing committed job frame image: {image_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Missing committed job frame sidecar: {metadata_path}"
            )
        pose = frame["pose"]
        capture = json.loads(metadata_path.read_text(encoding="utf-8"))
        frames.append(
            {
                "tool": str(frame["tool"]).lower(),
                "macro": str(frame["tool"]).upper(),
                "dx": float(frame["dx"]),
                "dx_label": dx_label(float(frame["dx"])),
                "prefix": frame_id,
                "target_gcode_position": {
                    "x": float(pose["x"]),
                    "y": float(pose["y"]),
                    "z": float(pose["z"]),
                },
                "capture": capture,
                "image_path": str(image_path),
                "metadata_path": str(metadata_path),
                "image_url": safe_vision_url(image_path),
                "metadata_url": safe_vision_url(metadata_path),
            }
        )
    return frames


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_job_event(job_dir: Path, event: str, payload: dict[str, Any]) -> None:
    manifest = read_json(job_dir / "manifest.json")
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "job_id": manifest["job_id"],
        "event": event,
        **payload,
    }
    with (job_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def job_dir_from_root(job_root: Path, job_id: str) -> Path:
    return Path(job_root) / sanitize_name(job_id)


def active_job_lock_path(job_root: Path) -> Path:
    return Path(job_root) / ".active_job.json"


def active_job_from_lock(job_root: Path) -> str | None:
    path = active_job_lock_path(job_root)
    if not path.exists():
        return None
    try:
        payload = read_json(path)
        return str(payload.get("job") or "")
    except Exception:
        return str(path)


def clear_active_job_lock_if_matches(job_root: Path, job_id: str) -> None:
    path = active_job_lock_path(job_root)
    if not path.exists():
        return
    try:
        payload = read_json(path)
        active_job = str(payload.get("job") or "")
    except Exception:
        active_job = ""
    if active_job == sanitize_name(job_id):
        path.unlink(missing_ok=True)


def safe_vision_url(path: Path) -> str:
    try:
        return vision_url(path)
    except ValueError:
        return str(path)


def safe_root_vision_url(path: Path) -> str:
    try:
        return root_vision_url(path)
    except ValueError:
        return safe_vision_url(path)


def verify_jpeg_header(path: Path) -> None:
    data = path.read_bytes()[:4]
    if len(data) < 2 or data[:2] != b"\xff\xd8":
        raise RuntimeError(f"{path} is not a JPEG frame")


def verify_prepared_job_integrity(job_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = job_dir / "manifest.json"
    state_path = job_dir / "state.json"
    gcode_path = job_dir / "acquisition.gcode"
    manifest = read_json(manifest_path)
    state = read_json(state_path)
    if manifest.get("schema_version") != VISION_JOB_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported manifest schema_version={manifest.get('schema_version')!r}"
        )
    if state.get("schema_version") != VISION_JOB_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported state schema_version={state.get('schema_version')!r}"
        )
    if manifest.get("job_id") != state.get("job_id"):
        raise RuntimeError(
            f"manifest job_id {manifest.get('job_id')!r} does not match "
            f"state job_id {state.get('job_id')!r}"
        )
    if manifest.get("manifest_hash") != compute_manifest_hash(manifest):
        raise RuntimeError("manifest hash does not match manifest contents")
    if state.get("manifest_hash") != manifest.get("manifest_hash"):
        raise RuntimeError("state manifest_hash does not match manifest")
    if state.get("gcode_hash") != manifest.get("gcode_hash"):
        raise RuntimeError("state gcode_hash does not match manifest")
    if not gcode_path.exists():
        raise RuntimeError(f"missing acquisition G-code: {gcode_path}")
    if compute_gcode_hash(gcode_path.read_text(encoding="utf-8")) != manifest.get(
        "gcode_hash"
    ):
        raise RuntimeError("acquisition G-code hash does not match manifest")
    return manifest, state


def required_homed_axes(manifest: dict[str, Any]) -> str:
    preconditions = manifest.get("preconditions") or {}
    return str(preconditions.get("required_homed_axes") or "xyz")


def ensure_job_poses_inside_limits(
    manifest: dict[str, Any], status: dict[str, Any]
) -> None:
    toolhead = status.get("toolhead") or {}
    axis_min = toolhead.get("axis_minimum") or []
    axis_max = toolhead.get("axis_maximum") or []
    if len(axis_min) < 3 or len(axis_max) < 3:
        raise RuntimeError("Moonraker toolhead status has no XYZ axis limits")
    for frame in manifest.get("frames") or []:
        pose = frame.get("pose") or {}
        for axis, index in (("x", 0), ("y", 1), ("z", 2)):
            value = float(pose[axis])
            if value < float(axis_min[index]) - 1e-6 or value > float(axis_max[index]) + 1e-6:
                raise RuntimeError(
                    f"frame {frame.get('frame')} {axis.upper()}={value:.4f} is outside "
                    f"Klipper limits {axis_min[index]}..{axis_max[index]}"
                )


def preflight_prepared_job(
    *,
    job_dir: Path,
    job_root: Path,
    moonraker_url: str,
    ready_timeout: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest, state = verify_prepared_job_integrity(job_dir)
    if state.get("state") != "prepared":
        raise RuntimeError(
            f"vision job {manifest.get('job_id')} is {state.get('state')!r}, "
            "expected 'prepared'"
        )
    active_job = active_job_from_lock(job_root)
    if active_job:
        raise RuntimeError(f"another vision job is active: {active_job}")
    status = wait_ready_and_idle(moonraker_url, ready_timeout)
    homed_axes = set(str(status.get("toolhead", {}).get("homed_axes") or ""))
    missing_axes = sorted(set(required_homed_axes(manifest)) - homed_axes)
    if missing_axes:
        raise RuntimeError(f"required axes are not homed: {''.join(missing_axes)}")
    ensure_job_poses_inside_limits(manifest, status)
    return manifest, state, status


def normalized_virtual_sd_subdir(value: str) -> Path:
    subdir = Path(str(value or "."))
    if subdir.is_absolute() or ".." in subdir.parts:
        raise RuntimeError(f"virtual SD subdir must be relative and safe: {value!r}")
    return subdir


def stage_job_gcode_to_virtual_sd(
    *,
    job_dir: Path,
    manifest: dict[str, Any],
    virtual_sd_root: Path,
    virtual_sd_subdir: str,
) -> dict[str, Any]:
    source = job_dir / str(manifest.get("gcode_file") or "acquisition.gcode")
    subdir = normalized_virtual_sd_subdir(virtual_sd_subdir)
    target_dir = Path(virtual_sd_root) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{manifest['job_id']}.gcode"
    source_bytes = source.read_bytes()
    reused = False
    if target.exists():
        if target.read_bytes() != source_bytes:
            raise RuntimeError(f"refusing to overwrite existing virtual SD file: {target}")
        reused = True
    else:
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(source_bytes)
        os.replace(tmp, target)
    copied_gcode_hash = compute_gcode_hash(target.read_text(encoding="utf-8"))
    if copied_gcode_hash != manifest.get("gcode_hash"):
        raise RuntimeError(
            f"copied G-code hash {copied_gcode_hash} does not match "
            f"manifest {manifest.get('gcode_hash')}"
        )
    virtual_sd_filename = (subdir / target.name).as_posix()
    return {
        "virtual_sd_root": str(virtual_sd_root),
        "virtual_sd_filename": virtual_sd_filename,
        "virtual_sd_path": str(target),
        "virtual_sd_reused": reused,
        "virtual_sd_gcode_hash": copied_gcode_hash,
        "virtual_sd_file_sha256": sha256_prefixed(target.read_bytes()),
    }


def record_job_start_request(
    *,
    job_dir: Path,
    state: dict[str, Any],
    moonraker_url: str,
    virtual_sd: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(state)
    requested_at = datetime.now(timezone.utc).isoformat()
    updated.update(
        {
            "moonraker_url": moonraker_url,
            "started_by": "vision_nozzle_align.py",
            "start_requested_at_utc": requested_at,
            "updated_at_utc": requested_at,
            **virtual_sd,
        }
    )
    atomic_write_json(job_dir / "state.json", updated)
    append_job_event(
        job_dir,
        "start_requested",
        {
            "state": updated.get("state"),
            "virtual_sd_filename": virtual_sd["virtual_sd_filename"],
            "virtual_sd_gcode_hash": virtual_sd["virtual_sd_gcode_hash"],
        },
    )
    return updated


def mark_job_terminal(
    *,
    job_dir: Path,
    job_root: Path,
    state_name: str,
    reason: str,
    event: str,
) -> dict[str, Any]:
    state = read_json(job_dir / "state.json")
    if state.get("state") in ("acquired", "completed", "failed", "abandoned"):
        return state
    now = datetime.now(timezone.utc).isoformat()
    state.update({"state": state_name, "updated_at_utc": now})
    if state_name == "failed":
        state.update({"failure": reason, "failed_at_utc": now})
    elif state_name == "abandoned":
        state.update({"abandoned_reason": reason, "abandoned_at_utc": now})
    atomic_write_json(job_dir / "state.json", state)
    append_job_event(job_dir, event, {"state": state_name, "reason": reason})
    clear_active_job_lock_if_matches(job_root, str(state.get("job_id") or ""))
    return state


def verify_acquired_job_frames(
    manifest: dict[str, Any], job_dir: Path
) -> list[dict[str, Any]]:
    frame_records: list[dict[str, Any]] = []
    for frame in manifest.get("frames") or []:
        frame_id = str(frame["frame"])
        image_path = job_dir / "frames" / f"{frame_id}.jpg"
        metadata_path = job_dir / "frames" / f"{frame_id}.json"
        if not image_path.exists():
            raise RuntimeError(f"missing acquired frame image: {image_path}")
        if not metadata_path.exists():
            raise RuntimeError(f"missing acquired frame sidecar: {metadata_path}")
        verify_jpeg_header(image_path)
        metadata = read_json(metadata_path)
        if int(metadata.get("job_seq", -1)) != int(frame["seq"]):
            raise RuntimeError(f"sidecar job_seq mismatch for frame {frame_id}")
        frame_records.append(
            {
                "seq": int(frame["seq"]),
                "frame": frame_id,
                "tool": frame.get("tool"),
                "image_path": str(image_path),
                "metadata_path": str(metadata_path),
                "image_url": safe_vision_url(image_path),
                "metadata_url": safe_vision_url(metadata_path),
                "framebuffer_seq": metadata.get("framebuffer_seq"),
                "image_sha256": metadata.get("image_sha256"),
            }
        )
    return frame_records


def job_execution_summary(
    *,
    job_dir: Path,
    manifest: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if manifest is None:
        manifest = read_json(job_dir / "manifest.json")
    state = read_json(job_dir / "state.json")
    frames: list[dict[str, Any]] = []
    if state.get("state") == "acquired":
        frames = verify_acquired_job_frames(manifest, job_dir)
    summary = {
        "ok": state.get("state") == "acquired" and error is None,
        "job_id": manifest.get("job_id"),
        "job_dir": str(job_dir),
        "manifest_path": str(job_dir / "manifest.json"),
        "gcode_path": str(job_dir / str(manifest.get("gcode_file") or "acquisition.gcode")),
        "state_path": str(job_dir / "state.json"),
        "events_path": str(job_dir / "events.jsonl"),
        "state": state.get("state"),
        "final_state": state.get("state"),
        "frame_count": manifest.get("frame_count"),
        "committed_frame_count": state.get("committed_frame_count", 0),
        "manifest_hash": manifest.get("manifest_hash"),
        "gcode_hash": manifest.get("gcode_hash"),
        "virtual_sd_filename": state.get("virtual_sd_filename"),
        "frames": frames,
    }
    if error:
        summary["error"] = error
    if state.get("failure"):
        summary["failure"] = state.get("failure")
    if state.get("abandoned_reason"):
        summary["abandoned_reason"] = state.get("abandoned_reason")
    return summary


def monitor_acquisition_job(
    *,
    job_dir: Path,
    job_root: Path,
    manifest: dict[str, Any],
    moonraker_url: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_print_state = None
    while time.monotonic() < deadline:
        state = read_json(job_dir / "state.json")
        if state.get("state") == "failed":
            return job_execution_summary(job_dir=job_dir, manifest=manifest)
        if state.get("state") == "abandoned":
            return job_execution_summary(job_dir=job_dir, manifest=manifest)
        status = query_status(moonraker_url)
        webhooks = status.get("webhooks") or {}
        print_stats = status.get("print_stats") or {}
        print_state = str(print_stats.get("state") or "")
        last_print_state = print_state
        if webhooks.get("state") != "ready":
            state = mark_job_terminal(
                job_dir=job_dir,
                job_root=job_root,
                state_name="abandoned",
                reason=f"Moonraker/Klipper left ready state: {webhooks.get('state')}",
                event="abandoned",
            )
            return job_execution_summary(
                job_dir=job_dir,
                manifest=manifest,
                error=state.get("abandoned_reason")
                or f"Moonraker/Klipper left ready state: {webhooks.get('state')}",
            )
        if print_state == "complete":
            state = read_json(job_dir / "state.json")
            if state.get("state") == "acquired":
                return job_execution_summary(job_dir=job_dir, manifest=manifest)
            reason = (
                "virtual SD print completed but vision job state is "
                f"{state.get('state')!r}"
            )
            state = mark_job_terminal(
                job_dir=job_dir,
                job_root=job_root,
                state_name="failed",
                reason=reason,
                event="failed",
            )
            return job_execution_summary(
                job_dir=job_dir, manifest=manifest, error=state.get("failure")
            )
        if print_state in ("cancelled", "error"):
            state = read_json(job_dir / "state.json")
            if state.get("state") == "failed":
                return job_execution_summary(job_dir=job_dir, manifest=manifest)
            reason = (
                f"virtual SD print ended in {print_state}: "
                f"{print_stats.get('message') or 'no Moonraker message'}"
            )
            state = mark_job_terminal(
                job_dir=job_dir,
                job_root=job_root,
                state_name="abandoned",
                reason=reason,
                event="abandoned",
            )
            return job_execution_summary(
                job_dir=job_dir,
                manifest=manifest,
                error=state.get("abandoned_reason") or reason,
            )
        time.sleep(0.5)
    reason = (
        f"timed out after {timeout:.1f}s waiting for acquisition job; "
        f"last print_stats.state={last_print_state!r}"
    )
    state = mark_job_terminal(
        job_dir=job_dir,
        job_root=job_root,
        state_name="failed",
        reason=reason,
        event="failed",
    )
    return job_execution_summary(
        job_dir=job_dir, manifest=manifest, error=state.get("failure") or reason
    )


def start_prepared_job(args: argparse.Namespace) -> dict[str, Any]:
    job_id = sanitize_name(args.start_prepared_job or args.job_id)
    if not job_id:
        raise RuntimeError("--start-prepared-job requires a job id")
    job_root = Path(args.job_root)
    job_dir = job_dir_from_root(job_root, job_id)
    manifest, state, _status = preflight_prepared_job(
        job_dir=job_dir,
        job_root=job_root,
        moonraker_url=args.moonraker_url,
        ready_timeout=float(args.ready_timeout),
    )
    virtual_sd = stage_job_gcode_to_virtual_sd(
        job_dir=job_dir,
        manifest=manifest,
        virtual_sd_root=Path(args.virtual_sd_root),
        virtual_sd_subdir=str(args.virtual_sd_subdir),
    )
    record_job_start_request(
        job_dir=job_dir,
        state=state,
        moonraker_url=args.moonraker_url,
        virtual_sd=virtual_sd,
    )
    run_gcode(
        args.moonraker_url,
        f"SDCARD_PRINT_FILE FILENAME={virtual_sd['virtual_sd_filename']}",
        timeout=30,
    )
    return monitor_acquisition_job(
        job_dir=job_dir,
        job_root=job_root,
        manifest=manifest,
        moonraker_url=args.moonraker_url,
        timeout=float(args.monitor_timeout),
    )


def run_acquisition_job(args: argparse.Namespace) -> dict[str, Any]:
    summary = prepare_nozzle_sweep_job(args)
    start_args = argparse.Namespace(**vars(args))
    start_args.start_prepared_job = summary["job_id"]
    return start_prepared_job(start_args)


def job_analysis_paths(job_dir: Path) -> dict[str, Path]:
    analysis_dir = job_dir / "analysis"
    return {
        "analysis_dir": analysis_dir,
        "overlays_dir": analysis_dir / "overlays",
        "raw_contact_sheet": analysis_dir / "raw_contact_sheet.jpg",
        "overlay_contact_sheet": analysis_dir / "overlay_contact_sheet.jpg",
        "result": analysis_dir / "result.json",
        "facts": analysis_dir / "facts.json",
    }


def assert_analysis_outputs_absent(paths: dict[str, Path]) -> None:
    for key in ("raw_contact_sheet", "overlay_contact_sheet", "result", "facts"):
        if paths[key].exists():
            raise RuntimeError(
                f"refusing to overwrite existing analysis artifact: {paths[key]}"
            )
    overlays_dir = paths["overlays_dir"]
    if overlays_dir.exists() and any(overlays_dir.iterdir()):
        raise RuntimeError(
            f"refusing to overwrite existing analysis overlays in {overlays_dir}"
        )


def mark_job_analysing(job_dir: Path) -> dict[str, Any]:
    state = read_json(job_dir / "state.json")
    if state.get("state") != "acquired":
        raise RuntimeError(
            f"vision job {state.get('job_id')} is {state.get('state')!r}, "
            "expected 'acquired' before analysis"
        )
    now = datetime.now(timezone.utc).isoformat()
    state.update(
        {
            "state": "analysing",
            "analysis_started_at_utc": now,
            "updated_at_utc": now,
        }
    )
    atomic_write_json(job_dir / "state.json", state)
    append_job_event(job_dir, "analysing", {"state": "analysing"})
    return state


def finish_job_analysis(
    *,
    job_dir: Path,
    accepted: bool,
    result_path: Path,
    facts_path: Path,
    raw_contact_sheet_path: Path | None,
    overlay_contact_sheet_path: Path | None,
    reason: str | None = None,
) -> dict[str, Any]:
    state = read_json(job_dir / "state.json")
    now = datetime.now(timezone.utc).isoformat()
    state_name = "completed" if accepted else "failed"
    state.update(
        {
            "state": state_name,
            "analysis_completed_at_utc": now,
            "updated_at_utc": now,
            "analysis_result_path": str(result_path),
            "analysis_result_url": safe_vision_url(result_path),
            "analysis_facts_path": str(facts_path),
            "analysis_facts_url": safe_vision_url(facts_path),
        }
    )
    if raw_contact_sheet_path and raw_contact_sheet_path.exists():
        state.update(
            {
                "raw_contact_sheet_path": str(raw_contact_sheet_path),
                "raw_contact_sheet_url": safe_vision_url(raw_contact_sheet_path),
            }
        )
    if overlay_contact_sheet_path and overlay_contact_sheet_path.exists():
        state.update(
            {
                "overlay_contact_sheet_path": str(overlay_contact_sheet_path),
                "overlay_contact_sheet_url": safe_vision_url(
                    overlay_contact_sheet_path
                ),
            }
        )
    if accepted:
        state.pop("failure", None)
    else:
        state["failure"] = reason or "analysis rejected the measurement"
        state["failed_at_utc"] = now
    atomic_write_json(job_dir / "state.json", state)
    append_job_event(
        job_dir,
        state_name,
        {
            "state": state_name,
            "accepted": accepted,
            "reason": reason,
            "result_path": str(result_path),
            "facts_path": str(facts_path),
        },
    )
    return state


def unique_dx_values_from_manifest(manifest: dict[str, Any]) -> list[float]:
    values: list[float] = []
    seen: set[str] = set()
    for frame in manifest.get("frames") or []:
        value = float(frame["dx"])
        label = dx_label(value)
        if label not in seen:
            values.append(value)
            seen.add(label)
    return values


def write_raw_contact_sheet(
    frames: list[dict[str, Any]], analysis: dict[str, Any], contact_sheet_path: Path
) -> None:
    raw_frames = []
    for frame in frames:
        raw = dict(frame)
        raw["overlay_path"] = raw["image_path"]
        raw_frames.append(raw)
    write_contact_sheet(raw_frames, analysis, contact_sheet_path)


def build_idex_nozzle_sweep_facts(
    *, manifest: dict[str, Any], analysis: dict[str, Any], result_path: Path
) -> dict[str, Any]:
    accepted = bool(analysis.get("ok"))
    return {
        "schema_version": VISION_JOB_SCHEMA_VERSION,
        "job_id": manifest.get("job_id"),
        "kind": manifest.get("kind"),
        "camera": manifest.get("camera"),
        "profile": manifest.get("profile"),
        "manifest_hash": manifest.get("manifest_hash"),
        "gcode_hash": manifest.get("gcode_hash"),
        "measurement": "idex_nozzle_relative_offset",
        "accepted": accepted,
        "ok": accepted,
        "source_result": result_path.name,
        "nozzle_delta_t1_minus_t0": (
            analysis.get("nozzle_delta_t1_minus_t0") if accepted else None
        ),
        "red_marker_delta_t1_minus_t0": analysis.get(
            "red_marker_delta_t1_minus_t0"
        ),
        "quality": {
            "cross_match": analysis.get("cross_match"),
            "red_marker_fits": analysis.get("red_marker_fits"),
            "red_axis_vector_px_per_mm": analysis.get("red_axis_vector_px_per_mm"),
            "red_axis_px_per_mm": analysis.get("red_axis_px_per_mm"),
            "red_axis_angle_deg": analysis.get("red_axis_angle_deg"),
        },
        "hard_failures": analysis.get("hard_failures") or [],
    }


def analyze_acquired_job(args: argparse.Namespace) -> dict[str, Any]:
    job_id = sanitize_name(args.analyze_job or args.job_id)
    if not job_id:
        raise RuntimeError("--analyze-job requires a job id")
    job_root = Path(args.job_root)
    job_dir = job_dir_from_root(job_root, job_id)
    manifest, state = verify_prepared_job_integrity(job_dir)
    if state.get("state") != "acquired":
        raise RuntimeError(
            f"vision job {manifest.get('job_id')} is {state.get('state')!r}, "
            "expected 'acquired'"
        )
    verify_acquired_job_frames(manifest, job_dir)
    paths = job_analysis_paths(job_dir)
    assert_analysis_outputs_absent(paths)
    paths["analysis_dir"].mkdir(parents=True, exist_ok=True)
    paths["overlays_dir"].mkdir(parents=True, exist_ok=True)
    mark_job_analysing(job_dir)

    result: dict[str, Any] = {
        "ok": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "job_id": manifest["job_id"],
        "kind": manifest["kind"],
        "state": "analysing",
        "manifest_path": str(job_dir / "manifest.json"),
        "gcode_path": str(
            job_dir / str(manifest.get("gcode_file") or "acquisition.gcode")
        ),
        "state_path": str(job_dir / "state.json"),
        "events_path": str(job_dir / "events.jsonl"),
        "manifest_hash": manifest["manifest_hash"],
        "gcode_hash": manifest["gcode_hash"],
        "dx_values": unique_dx_values_from_manifest(manifest),
        "analysis_dir": str(paths["analysis_dir"]),
        "analysis_url": safe_vision_url(paths["analysis_dir"]),
        "raw_contact_sheet_path": str(paths["raw_contact_sheet"]),
        "raw_contact_sheet_url": safe_vision_url(paths["raw_contact_sheet"]),
        "overlay_contact_sheet_path": str(paths["overlay_contact_sheet"]),
        "overlay_contact_sheet_url": safe_vision_url(paths["overlay_contact_sheet"]),
        "result_path": str(paths["result"]),
        "result_url": safe_vision_url(paths["result"]),
        "facts_path": str(paths["facts"]),
        "facts_url": safe_vision_url(paths["facts"]),
    }
    try:
        frames = load_job_frames_for_analysis(job_dir / "manifest.json")
        analysis = analyze_sweep_frames(
            frames, paths["analysis_dir"], overlay_dir=paths["overlays_dir"]
        )
        analysis.update(
            {
                "run_name": manifest["job_id"],
                "dx_values": result["dx_values"],
                "job_id": manifest["job_id"],
            }
        )
        if frames:
            write_raw_contact_sheet(frames, analysis, paths["raw_contact_sheet"])
            if all("overlay_path" in frame for frame in frames):
                write_contact_sheet(frames, analysis, paths["overlay_contact_sheet"])
        facts = build_idex_nozzle_sweep_facts(
            manifest=manifest, analysis=analysis, result_path=paths["result"]
        )
        result.update(
            {
                "ok": bool(analysis.get("ok")),
                "accepted": bool(analysis.get("ok")),
                "proxy_only": bool(analysis.get("proxy_only")),
                "message": analysis.get("message"),
                "frames": frames,
                "analysis": analysis,
                "facts": facts,
            }
        )
        atomic_write_json(paths["facts"], facts)
        final_state = finish_job_analysis(
            job_dir=job_dir,
            accepted=bool(analysis.get("ok")),
            result_path=paths["result"],
            facts_path=paths["facts"],
            raw_contact_sheet_path=paths["raw_contact_sheet"],
            overlay_contact_sheet_path=paths["overlay_contact_sheet"],
            reason=analysis.get("message"),
        )
        result["state"] = final_state.get("state")
        result["final_state"] = final_state.get("state")
    except Exception as exc:
        result.update(
            {
                "ok": False,
                "accepted": False,
                "error": str(exc),
                "message": "Nozzle vision job analysis failed before completion.",
            }
        )
        facts = {
            "schema_version": VISION_JOB_SCHEMA_VERSION,
            "job_id": manifest.get("job_id"),
            "kind": manifest.get("kind"),
            "accepted": False,
            "ok": False,
            "hard_failures": [str(exc)],
        }
        atomic_write_json(paths["facts"], facts)
        final_state = finish_job_analysis(
            job_dir=job_dir,
            accepted=False,
            result_path=paths["result"],
            facts_path=paths["facts"],
            raw_contact_sheet_path=paths["raw_contact_sheet"],
            overlay_contact_sheet_path=paths["overlay_contact_sheet"],
            reason=str(exc),
        )
        result["state"] = final_state.get("state")
        result["final_state"] = final_state.get("state")
    finally:
        atomic_write_json(paths["result"], result)
    return result


def run_full_job(args: argparse.Namespace) -> dict[str, Any]:
    acquisition = run_acquisition_job(args)
    if not acquisition.get("ok"):
        return {
            **acquisition,
            "ok": False,
            "analysis_started": False,
            "message": acquisition.get("error")
            or acquisition.get("failure")
            or "acquisition failed before analysis",
        }
    analyze_args = argparse.Namespace(**vars(args))
    analyze_args.analyze_job = acquisition["job_id"]
    result = analyze_acquired_job(analyze_args)
    result["acquisition"] = {
        "ok": acquisition.get("ok"),
        "state": acquisition.get("state"),
        "virtual_sd_filename": acquisition.get("virtual_sd_filename"),
        "committed_frame_count": acquisition.get("committed_frame_count"),
    }
    return result


def html_text(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def html_link(path: Path, label: str | None = None, *, root: bool = True) -> str:
    url = safe_root_vision_url(path) if root else safe_vision_url(path)
    text = label or path.name
    return f'<a href="{html_text(url)}">{html_text(text)}</a>'


def html_optional_link(path: Path, label: str | None = None) -> str:
    if path.exists() or path.is_symlink():
        return html_link(path, label)
    return '<span class="muted">not available</span>'


def read_json_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except Exception as exc:
        return {"_read_error": str(exc)}


def format_report_number(value: Any, digits: int = 3) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def format_report_value(value: Any, unit: str, digits: int = 3) -> str:
    text = format_report_number(value, digits)
    return text if text == "n/a" else f"{text} {unit}"


def render_measurement_result(facts_path: Path, state: dict[str, Any]) -> str:
    facts = read_json_optional(facts_path)
    if not facts:
        return (
            '<section class="measurement"><h2>Measurement Result</h2>'
            '<p class="muted">Analysis has not produced measurement facts yet.</p>'
            "</section>"
        )
    if facts.get("_read_error"):
        return (
            '<section class="measurement"><h2>Measurement Result</h2>'
            f'<p class="failure">Could not read facts.json: '
            f'{html_text(facts.get("_read_error"))}</p></section>'
        )

    accepted = bool(facts.get("accepted") or facts.get("ok"))
    hard_failures = facts.get("hard_failures") or []
    delta = facts.get("nozzle_delta_t1_minus_t0") or {}
    quality = facts.get("quality") or {}
    cross = quality.get("cross_match") or {}
    status_text = "accepted" if accepted else "rejected"
    status_class = "result-ok" if accepted else "result-bad"
    source = delta.get("measurement_source") or cross.get("measurement_source") or "n/a"
    quality_parts = [
        f"{format_report_number(cross.get('usable_pair_count'), 0)} pairs",
        f"rms {format_report_value(cross.get('residual_rms_px'), 'px')}",
    ]
    if cross.get("correlation_median") is not None:
        quality_parts.append(
            f"corr median {format_report_number(cross.get('correlation_median'), 3)}"
        )
    if cross.get("feature_mode"):
        quality_parts.append(f"mode {cross.get('feature_mode')}")

    rows = [
        (
            "Status",
            f'<span class="{status_class}">{html_text(status_text)}</span>',
            html_text(state.get("reason") or "; ".join(str(item) for item in hard_failures)),
        ),
        (
            "T1 - T0 along X",
            html_text(format_report_value(delta.get("along_x_mm_approx"), "mm")),
            html_text(format_report_value(delta.get("along_x_px"), "px")),
        ),
        (
            "T1 - T0 perpendicular",
            html_text(format_report_value(delta.get("perpendicular_mm_approx"), "mm")),
            html_text(format_report_value(delta.get("perpendicular_px"), "px")),
        ),
        (
            "Image delta",
            "dx "
            + html_text(format_report_value(delta.get("dx"), "px"))
            + ", dy "
            + html_text(format_report_value(delta.get("dy"), "px")),
            html_text(source),
        ),
        (
            "Cross-match quality",
            html_text(", ".join(quality_parts)),
            "axis "
            + html_text(format_report_value(cross.get("axis_px_per_mm"), "px/mm"))
            + ", angle "
            + html_text(format_report_value(cross.get("axis_angle_deg"), "deg")),
        ),
    ]
    empty_note = '<span class="muted">n/a</span>'
    row_html = "\n".join(
        "<tr>"
        f"<th>{html_text(label)}</th>"
        f"<td>{value}</td>"
        f"<td>{note or empty_note}</td>"
        "</tr>"
        for label, value, note in rows
    )
    return (
        '<section class="measurement"><h2>Measurement Result</h2>'
        "<table><thead><tr><th>Metric</th><th>Value</th><th>Check</th></tr>"
        f"</thead><tbody>{row_html}</tbody></table></section>"
    )


def job_sort_timestamp(summary: dict[str, Any]) -> str:
    for key in (
        "updated_at_utc",
        "analysis_completed_at_utc",
        "start_requested_at_utc",
        "created_at_utc",
    ):
        if summary.get(key):
            return str(summary[key])
    return ""


def job_artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "url": safe_root_vision_url(path),
        "exists": path.exists() or path.is_symlink(),
    }


def summarize_ui_job(job_dir: Path) -> dict[str, Any] | None:
    manifest_path = job_dir / "manifest.json"
    state_path = job_dir / "state.json"
    if not manifest_path.exists() or not state_path.exists():
        return None
    manifest = read_json_optional(manifest_path)
    state = read_json_optional(state_path)
    if manifest.get("_read_error") or state.get("_read_error"):
        return {
            "job_id": job_dir.name,
            "job_dir": str(job_dir),
            "job_url": safe_root_vision_url(job_dir),
            "page_url": safe_root_vision_url(job_dir / "index.html"),
            "state": "failed",
            "failure": manifest.get("_read_error") or state.get("_read_error"),
        }

    job_id = str(manifest.get("job_id") or state.get("job_id") or job_dir.name)
    state_name = str(state.get("state") or manifest.get("state") or "unknown")
    paths = job_analysis_paths(job_dir)
    gcode_path = job_dir / str(manifest.get("gcode_file") or "acquisition.gcode")
    result = read_json_optional(paths["result"])
    failure = (
        state.get("failure")
        or state.get("abandoned_reason")
        or result.get("error")
        or result.get("message")
        if state_name in ("failed", "abandoned")
        else None
    )
    summary = {
        "job_id": job_id,
        "kind": manifest.get("kind"),
        "camera": manifest.get("camera"),
        "profile": manifest.get("profile"),
        "state": state_name,
        "created_at_utc": manifest.get("created_at_utc") or state.get("created_at_utc"),
        "updated_at_utc": state.get("updated_at_utc"),
        "start_requested_at_utc": state.get("start_requested_at_utc"),
        "analysis_completed_at_utc": state.get("analysis_completed_at_utc"),
        "frame_count": manifest.get("frame_count", len(manifest.get("frames") or [])),
        "committed_frame_count": state.get("committed_frame_count", 0),
        "manifest_hash": manifest.get("manifest_hash"),
        "gcode_hash": manifest.get("gcode_hash"),
        "failure": failure,
        "job_dir": str(job_dir),
        "job_url": safe_root_vision_url(job_dir),
        "page_url": safe_root_vision_url(job_dir / "index.html"),
        "state_url": safe_root_vision_url(state_path),
        "manifest_url": safe_root_vision_url(manifest_path),
        "gcode_url": safe_root_vision_url(gcode_path),
        "events_url": safe_root_vision_url(job_dir / "events.jsonl"),
        "virtual_sd_filename": state.get("virtual_sd_filename"),
        "artifacts": {
            "result": job_artifact_record(paths["result"]),
            "facts": job_artifact_record(paths["facts"]),
            "raw_contact_sheet": job_artifact_record(paths["raw_contact_sheet"]),
            "overlay_contact_sheet": job_artifact_record(
                paths["overlay_contact_sheet"]
            ),
        },
    }
    return summary


def discover_ui_jobs(job_root: Path) -> list[dict[str, Any]]:
    if not job_root.exists():
        return []
    jobs: list[dict[str, Any]] = []
    for job_dir in sorted(path for path in job_root.iterdir() if path.is_dir()):
        summary = summarize_ui_job(job_dir)
        if summary:
            jobs.append(summary)
    jobs.sort(key=job_sort_timestamp, reverse=True)
    return jobs


def job_counts_by_state(jobs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        state = str(job.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts


def active_ui_job(job_root: Path, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    active_job_id = active_job_from_lock(job_root)
    if active_job_id:
        for job in jobs:
            if job.get("job_id") == active_job_id:
                return job
        return {"job_id": active_job_id, "state": "active-lock"}
    for job in jobs:
        if job.get("state") in ("acquiring", "analysing"):
            return job
    return None


def ui_jobs_payload(job_root: Path, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    active = active_ui_job(job_root, jobs)
    return {
        "schema_version": VISION_JOB_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint_url": prefixed_root_vision_url(""),
        "counts_by_state": job_counts_by_state(jobs),
        "active_job": active,
        "jobs": jobs,
    }


def render_html_page(title: str, body: str, *, poll_script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_text(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #607080;
      --line: #d9dee7;
      --accent: #0b6bcb;
      --bad: #b42318;
      --ok: #087443;
      --warn: #9a6700;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.4;
    }}
    main {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1, h2 {{
      margin: 0 0 14px;
      letter-spacing: 0;
    }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 18px; margin-top: 26px; }}
    a {{ color: var(--accent); }}
    code {{
      background: #eef1f5;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 2px 5px;
    }}
    pre {{
      overflow: auto;
      background: #101820;
      color: #f4f7fb;
      padding: 12px;
      border-radius: 6px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      margin: 10px 0 22px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #edf1f6;
      color: #263442;
      font-weight: 650;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 14px 0 24px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .state-completed {{ color: var(--ok); font-weight: 700; }}
    .state-failed, .state-abandoned {{ color: var(--bad); font-weight: 700; }}
    .state-prepared, .state-acquired {{ color: var(--warn); font-weight: 700; }}
    .state-acquiring, .state-analysing {{ color: var(--accent); font-weight: 700; }}
    .result-ok {{ color: var(--ok); font-weight: 700; }}
    .result-bad {{ color: var(--bad); font-weight: 700; }}
    .muted {{ color: var(--muted); }}
    .failure {{
      border-left: 4px solid var(--bad);
      background: #fff4f2;
      padding: 10px 12px;
      margin: 14px 0 18px;
    }}
    .thumb {{
      max-width: 220px;
      max-height: 150px;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .sheet {{
      max-width: min(100%, 900px);
      border: 1px solid var(--line);
      background: #fff;
      display: block;
      margin: 8px 0 18px;
    }}
    .measurement table {{ margin-top: 8px; }}
    .nowrap {{ white-space: nowrap; }}
  </style>
</head>
<body>
<main>
{body}
</main>
{poll_script}
</body>
</html>
"""


def state_class(state: Any) -> str:
    state_name = sanitize_name(state or "unknown").replace("_", "-")
    return f"state-{state_name}"


def render_job_rows(jobs: list[dict[str, Any]]) -> str:
    if not jobs:
        return '<p class="muted">No jobs in this group.</p>'
    rows = []
    for job in jobs:
        state = str(job.get("state") or "unknown")
        failure = job.get("failure") or ""
        rows.append(
            "<tr>"
            f"<td>{html_link(Path(str(job['job_dir'])) / 'index.html', job['job_id'])}</td>"
            f'<td class="{html_text(state_class(state))}">{html_text(state)}</td>'
            f"<td>{html_text(job.get('kind'))}</td>"
            f"<td>{html_text(job.get('created_at_utc'))}</td>"
            f"<td>{html_text(job.get('updated_at_utc'))}</td>"
            f"<td>{html_text(job.get('committed_frame_count'))}/"
            f"{html_text(job.get('frame_count'))}</td>"
            f"<td>{html_text(failure)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Job</th><th>State</th><th>Kind</th>"
        "<th>Created</th><th>Updated</th><th>Frames</th><th>Reason</th>"
        "</tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def render_global_vision_index(payload: dict[str, Any]) -> str:
    jobs = payload["jobs"]
    active = payload.get("active_job")
    prepared = [job for job in jobs if job.get("state") == "prepared"]
    history = [
        job
        for job in jobs
        if job.get("state") in ("completed", "failed", "abandoned", "acquired")
    ]
    active_jobs = (
        [active]
        if active and active.get("job_id")
        else [job for job in jobs if job.get("state") in ("acquiring", "analysing")]
    )
    counts = payload.get("counts_by_state") or {}
    count_text = ", ".join(
        f"{html_text(state)}={html_text(count)}" for state, count in sorted(counts.items())
    ) or "none"
    body = f"""
<h1>Vision Jobs</h1>
<p class="muted">Canonical browser URL: <a href="{html_text(prefixed_root_vision_url(''))}">{html_text(public_url(prefixed_root_vision_url('')))}</a></p>
<div class="summary">
  <div class="metric"><span>Generated</span><strong id="generated-at">{html_text(payload.get('generated_at_utc'))}</strong></div>
  <div class="metric"><span>Jobs</span><strong>{html_text(len(jobs))}</strong></div>
  <div class="metric"><span>States</span><strong>{count_text}</strong></div>
  <div class="metric"><span>Data</span>{html_link(VISION_ROOT_DIR / 'jobs.json', 'jobs.json')}</div>
</div>
<h2>Commands</h2>
<pre>/usr/local/bin/vision_nozzle_align.py --refresh-ui
/usr/local/bin/vision_nozzle_align.py --run-job --name nozzle_sweep --x 195 --y -14.8 --z 20 --dx 0,3,6,9,12</pre>
<h2>Active</h2>
{render_job_rows([job for job in active_jobs if job])}
<h2>Prepared</h2>
{render_job_rows(prepared)}
<h2>History</h2>
{render_job_rows(history)}
"""
    poll_script = """
<script>
async function pollJobs() {
  try {
    const response = await fetch('jobs.json?ts=' + Date.now(), {cache: 'no-store'});
    if (!response.ok) return;
    const payload = await response.json();
    const generated = document.getElementById('generated-at');
    if (generated) generated.textContent = payload.generated_at_utc || '';
  } catch (_err) {}
}
setInterval(pollJobs, 5000);
</script>
"""
    return render_html_page("Vision Jobs", body, poll_script=poll_script)


def frame_capture_time(metadata: dict[str, Any]) -> Any:
    source = metadata.get("source_frame") or {}
    return metadata.get("timestamp_utc") or source.get("timestamp_utc")


def render_job_frame_rows(
    manifest: dict[str, Any], job_dir: Path, paths: dict[str, Path]
) -> str:
    rows = []
    for frame in manifest.get("frames") or []:
        frame_id = str(frame.get("frame"))
        image_path = job_dir / "frames" / f"{frame_id}.jpg"
        sidecar_path = job_dir / "frames" / f"{frame_id}.json"
        overlay_path = paths["overlays_dir"] / f"{frame_id}_overlay.jpg"
        metadata = read_json_optional(sidecar_path)
        pose = frame.get("pose") or {}
        thumbnail = (
            f'<a href="{html_text(safe_root_vision_url(image_path))}">'
            f'<img class="thumb" src="{html_text(safe_root_vision_url(image_path))}" '
            f'alt="{html_text(frame_id)} raw"></a>'
            if image_path.exists()
            else '<span class="muted">missing</span>'
        )
        overlay = (
            html_link(overlay_path, "overlay")
            if overlay_path.exists()
            else '<span class="muted">pending</span>'
        )
        rows.append(
            "<tr>"
            f"<td>{html_text(frame.get('seq'))}</td>"
            f"<td>{html_text(frame_id)}</td>"
            f"<td>{html_text(frame.get('tool'))}</td>"
            f"<td>X{html_text(pose.get('x'))} Y{html_text(pose.get('y'))} "
            f"Z{html_text(pose.get('z'))}</td>"
            f"<td>{html_text(frame.get('profile'))}</td>"
            f"<td>{html_text(frame_capture_time(metadata))}</td>"
            f"<td>{html_text(metadata.get('framebuffer_seq'))}</td>"
            f"<td>{thumbnail}</td>"
            f"<td>{html_optional_link(sidecar_path, 'sidecar')}</td>"
            f"<td>{overlay}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Seq</th><th>Frame</th><th>Tool</th>"
        "<th>Pose</th><th>Profile</th><th>Captured</th><th>Framebuffer</th>"
        "<th>Raw</th><th>Sidecar</th><th>Overlay</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def render_job_detail_page(job_dir: Path) -> str:
    manifest = read_json(job_dir / "manifest.json")
    state = read_json(job_dir / "state.json")
    paths = job_analysis_paths(job_dir)
    state_name = str(state.get("state") or manifest.get("state") or "unknown")
    failure = state.get("failure") or state.get("abandoned_reason")
    gcode_path = job_dir / str(manifest.get("gcode_file") or "acquisition.gcode")
    raw_sheet = paths["raw_contact_sheet"]
    overlay_sheet = paths["overlay_contact_sheet"]
    result_path = paths["result"]
    facts_path = paths["facts"]
    measurement_result = render_measurement_result(facts_path, state)
    failure_block = (
        f'<div class="failure"><strong>Failure:</strong> {html_text(failure)}</div>'
        if failure
        else ""
    )
    contact_sheets = ""
    if raw_sheet.exists():
        contact_sheets += (
            f'<h2>Raw Contact Sheet</h2><a href="{html_text(safe_root_vision_url(raw_sheet))}">'
            f'<img class="sheet" src="{html_text(safe_root_vision_url(raw_sheet))}" '
            'alt="raw contact sheet"></a>'
        )
    if overlay_sheet.exists():
        contact_sheets += (
            f'<h2>Overlay Contact Sheet</h2><a href="{html_text(safe_root_vision_url(overlay_sheet))}">'
            f'<img class="sheet" src="{html_text(safe_root_vision_url(overlay_sheet))}" '
            'alt="overlay contact sheet"></a>'
        )
    body = f"""
<p>{html_link(VISION_ROOT_DIR / 'index.html', 'Vision Jobs')}</p>
<h1>{html_text(manifest.get('job_id') or job_dir.name)}</h1>
<div class="summary">
  <div class="metric"><span>State</span><strong id="job-state" class="{html_text(state_class(state_name))}">{html_text(state_name)}</strong></div>
  <div class="metric"><span>Frames</span><strong id="job-progress">{html_text(state.get('committed_frame_count', 0))}/{html_text(manifest.get('frame_count'))}</strong></div>
  <div class="metric"><span>Kind</span><strong>{html_text(manifest.get('kind'))}</strong></div>
  <div class="metric"><span>Virtual SD</span><strong>{html_text(state.get('virtual_sd_filename'))}</strong></div>
</div>
{failure_block}
{measurement_result}
<h2>Artifacts</h2>
<table><tbody>
  <tr><th>Manifest</th><td>{html_optional_link(job_dir / 'manifest.json', 'manifest.json')}</td></tr>
  <tr><th>G-code</th><td>{html_optional_link(gcode_path, gcode_path.name)}</td></tr>
  <tr><th>State</th><td>{html_optional_link(job_dir / 'state.json', 'state.json')}</td></tr>
  <tr><th>Events</th><td>{html_optional_link(job_dir / 'events.jsonl', 'events.jsonl')}</td></tr>
  <tr><th>Result</th><td>{html_optional_link(result_path, 'result.json')}</td></tr>
  <tr><th>Facts</th><td>{html_optional_link(facts_path, 'facts.json')}</td></tr>
</tbody></table>
<h2>Hashes</h2>
<table><tbody>
  <tr><th>Manifest hash</th><td><code>{html_text(manifest.get('manifest_hash'))}</code></td></tr>
  <tr><th>G-code hash</th><td><code>{html_text(manifest.get('gcode_hash'))}</code></td></tr>
</tbody></table>
{contact_sheets}
<h2>Frames</h2>
{render_job_frame_rows(manifest, job_dir, paths)}
"""
    poll_script = """
<script>
async function pollState() {
  try {
    const response = await fetch('state.json?ts=' + Date.now(), {cache: 'no-store'});
    if (!response.ok) return;
    const state = await response.json();
    const stateNode = document.getElementById('job-state');
    const progressNode = document.getElementById('job-progress');
    if (stateNode) stateNode.textContent = state.state || '';
    if (progressNode) progressNode.textContent =
      String(state.committed_frame_count || 0) + '/' + String(state.frame_count || '');
  } catch (_err) {}
}
setInterval(pollState, 4000);
</script>
"""
    return render_html_page(
        f"Vision Job {manifest.get('job_id') or job_dir.name}",
        body,
        poll_script=poll_script,
    )


def refresh_vision_ui(job_root: Path | None = None) -> dict[str, Any]:
    resolved_job_root = Path(job_root or NOZZLE_JOB_ROOT)
    VISION_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = discover_ui_jobs(resolved_job_root)
    for job in jobs:
        job_dir = Path(str(job["job_dir"]))
        if (job_dir / "manifest.json").exists() and (job_dir / "state.json").exists():
            atomic_write_text(job_dir / "index.html", render_job_detail_page(job_dir))
    payload = ui_jobs_payload(resolved_job_root, jobs)
    jobs_path = VISION_ROOT_DIR / "jobs.json"
    index_path = VISION_ROOT_DIR / "index.html"
    atomic_write_json(jobs_path, payload)
    atomic_write_text(index_path, render_global_vision_index(payload))
    return {
        "ok": True,
        "entrypoint_path": str(index_path),
        "entrypoint_url": prefixed_root_vision_url(""),
        "entrypoint_public_url": public_url(prefixed_root_vision_url("")),
        "index_url": safe_root_vision_url(index_path),
        "jobs_path": str(jobs_path),
        "jobs_url": safe_root_vision_url(jobs_path),
        "job_count": len(jobs),
        "counts_by_state": payload["counts_by_state"],
    }


def attach_ui_refresh(result: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    try:
        result["ui"] = refresh_vision_ui(Path(args.job_root))
    except Exception as exc:
        result["ui_error"] = str(exc)
    return result


def moonraker_get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=15) as response:
        return json.loads(response.read())


def run_command(command: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def service_is_active(service: str) -> bool:
    result = run_command(["systemctl", "is-active", "--quiet", service], timeout=5)
    return result.returncode == 0


def stop_service(service: str) -> None:
    result = run_command(["systemctl", "stop", service], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"Could not stop {service}: {result.stderr.strip()}")


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
    raise RuntimeError(f"Timed out waiting for {host}:{port}: {last_error}")


def wait_for_webcam_snapshot(timeout: float) -> float:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(WEBCAM_SNAPSHOT_URL, timeout=3) as response:
                data = response.read(4)
            if data[:2] == b"\xff\xd8":
                return round(timeout - max(0.0, deadline - time.monotonic()), 3)
            last_error = RuntimeError("snapshot endpoint did not return a JPEG")
        except Exception as exc:
            last_error = exc
        time.sleep(0.75)
    raise RuntimeError(f"Timed out waiting for webcam snapshot: {last_error}")


def start_preview_service() -> dict[str, Any]:
    reset_failed_service(CROWSNEST_SERVICE)
    result = run_command(["systemctl", "start", CROWSNEST_SERVICE], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"Could not start {CROWSNEST_SERVICE}: {result.stderr.strip()}")
    return {
        "tcp_ready_after_s": wait_for_tcp(
            CROWSNEST_HOST, CROWSNEST_PORT, WEBCAM_READY_TIMEOUT
        ),
        "snapshot_ready_after_s": wait_for_webcam_snapshot(WEBCAM_READY_TIMEOUT),
    }


def run_gcode(base_url: str, script: str, *, timeout: float = 60.0) -> None:
    data = urllib.parse.urlencode({"script": script}).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/printer/gcode/script",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def query_status(base_url: str) -> dict[str, Any]:
    path = "/printer/objects/query?toolhead&gcode_move&webhooks&print_stats"
    return moonraker_get(base_url, path)["result"]["status"]


def wait_ready_and_idle(base_url: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = query_status(base_url)
        webhooks = status.get("webhooks", {})
        print_stats = status.get("print_stats", {})
        if webhooks.get("state") == "ready" and print_stats.get("state") in (
            "standby",
            "complete",
        ):
            return status
        time.sleep(0.5)
    raise TimeoutError("Printer did not become ready and idle")


def capture_once(name: str, fresh_after_utc: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            CAPTURE_BIN,
            "--capture-once",
            name,
            "--require-high-res",
            "--fresh-after-utc",
            fresh_after_utc,
            "--fresh-timeout",
            "12",
            "--retries",
            "5",
            "--no-crowsnest-management",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def copy_capture_artifacts_to_run(
    metadata: dict[str, Any], run_dir: Path, prefix: str
) -> dict[str, str]:
    image_source = Path(metadata["image_path"])
    meta_source = Path(metadata["metadata_path"])
    image_target = run_dir / f"{prefix}.jpg"
    meta_target = run_dir / f"{prefix}_capture.json"
    shutil.copy2(image_source, image_target)
    shutil.copy2(meta_source, meta_target)
    return {
        "image_path": str(image_target),
        "metadata_path": str(meta_target),
        "image_url": vision_url(image_target),
        "metadata_url": vision_url(meta_target),
    }


def scale_rect_1080(
    rect: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    return clamp_rect(
        x * width / RED_BASE_WIDTH,
        y * height / RED_BASE_HEIGHT,
        w * width / RED_BASE_WIDTH,
        h * height / RED_BASE_HEIGHT,
        width,
        height,
    )


def clamp_rect(
    x: float, y: float, w: float, h: float, width: int, height: int
) -> tuple[int, int, int, int]:
    ix = max(0, min(width - 1, int(round(x))))
    iy = max(0, min(height - 1, int(round(y))))
    iw = max(1, int(round(w)))
    ih = max(1, int(round(h)))
    if ix + iw > width:
        iw = max(1, width - ix)
    if iy + ih > height:
        ih = max(1, height - iy)
    return ix, iy, iw, ih


def point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def detect_red_marker(image: Any) -> dict[str, Any]:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    roi = scale_rect_1080(RED_MARKER_ROI_1080, width, height)
    x, y, w, h = roi
    crop = image[y : y + h, x : x + w]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask_low = cv2.inRange(hsv, np.array([0, 70, 35]), np.array([14, 255, 255]))
    mask_high = cv2.inRange(hsv, np.array([168, 70, 35]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(mask_low, mask_high)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scale = (width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT) / 2.0
    min_area = max(80.0, 160.0 * scale * scale)
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        cx = float(moments["m10"] / moments["m00"] + x)
        cy = float(moments["m01"] / moments["m00"] + y)
        bx, by, bw, bh = cv2.boundingRect(contour)
        candidates.append(
            {
                "center_px": [round(cx, 3), round(cy, 3)],
                "bbox": [int(bx + x), int(by + y), int(bw), int(bh)],
                "area": round(area, 3),
            }
        )
    candidates.sort(key=lambda item: item["area"], reverse=True)
    if not candidates:
        return {
            "accepted": False,
            "roi": list(roi),
            "rejection_reason": "no red marker blob found",
            "candidates": [],
        }
    best = candidates[0]
    return {
        "accepted": True,
        "roi": list(roi),
        "center_px": best["center_px"],
        "bbox": best["bbox"],
        "area": best["area"],
        "candidates": candidates[:5],
    }


def derive_nozzle_roi(
    red_marker: dict[str, Any], width: int, height: int
) -> tuple[int, int, int, int]:
    if not red_marker.get("accepted"):
        raise RuntimeError(
            "Cannot derive nozzle ROI because red marker detection was not accepted: "
            f"{red_marker.get('rejection_reason', 'unknown red marker failure')}"
        )
    center_x, center_y = red_marker["center_px"]
    offset_x = NOZZLE_FEATURE_OFFSET_1080[0] * width / RED_BASE_WIDTH
    offset_y = NOZZLE_FEATURE_OFFSET_1080[1] * height / RED_BASE_HEIGHT
    roi_w = NOZZLE_ROI_SIZE_1080[0] * width / RED_BASE_WIDTH
    roi_h = NOZZLE_ROI_SIZE_1080[1] * height / RED_BASE_HEIGHT
    start_x = center_x + offset_x - roi_w / 2.0
    start_y = center_y + offset_y - roi_h / 2.0
    return clamp_rect(start_x, start_y, roi_w, roi_h, width, height)


def detect_nozzle_candidates(image: Any, roi: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    x, y, w, h = roi
    crop = image[y : y + h, x : x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 1.2)
    scale = (width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT) / 2.0
    min_radius = max(5, int(round(8 * scale)))
    max_radius = max(14, int(round(35 * scale)))
    target_radius = 18.0 * scale
    candidates: list[dict[str, Any]] = []

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(14, int(round(22 * scale))),
        param1=90,
        param2=14,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is not None:
        for cx, cy, radius in np.round(circles[0, :]).astype(int):
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.circle(mask, (int(cx), int(cy)), max(int(radius) - 2, 1), 255, -1)
            mean_inside = float(cv2.mean(gray, mask=mask)[0])
            darkness = 255.0 - mean_inside
            candidates.append(
                {
                    "source": "hough",
                    "cx": float(cx + x),
                    "cy": float(cy + y),
                    "r": float(radius),
                    "mean_inside": round(mean_inside, 3),
                    "base_score": round(0.35 * darkness - 1.7 * abs(radius - target_radius), 3),
                }
            )

    _, dark = cv2.threshold(blur, 78, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((3, 3), np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 35 * scale * scale or area > 3800 * scale * scale:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0:
            continue
        circularity = 4.0 * math.pi * area / (perimeter * perimeter)
        if circularity < 0.28:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if radius < min_radius or radius > max_radius:
            continue
        mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        mean_inside = float(cv2.mean(gray, mask=mask)[0])
        darkness = 255.0 - mean_inside
        candidates.append(
            {
                "source": "dark_contour",
                "cx": float(cx + x),
                "cy": float(cy + y),
                "r": float(radius),
                "mean_inside": round(mean_inside, 3),
                "area": round(area, 3),
                "circularity": round(circularity, 3),
                "base_score": round(
                    0.42 * darkness
                    + 20.0 * circularity
                    - 1.8 * abs(radius - target_radius),
                    3,
                ),
            }
        )

    candidates.sort(key=lambda item: item["base_score"], reverse=True)
    return candidates[:12]


def derive_global_nozzle_roi(
    frames: list[dict[str, Any]], width: int, height: int
) -> tuple[int, int, int, int]:
    feature_boxes = []
    for frame in frames:
        red = frame.get("red_marker", {})
        feature_roi = derive_nozzle_roi(red, width, height)
        frame["feature_roi"] = list(feature_roi)
        fx, fy, fw, fh = feature_roi
        frame["expected_nozzle_feature_center_px"] = [
            round(fx + fw / 2.0, 3),
            round(fy + fh / 2.0, 3),
        ]
        feature_boxes.append(feature_roi)
    if not feature_boxes:
        raise RuntimeError("Cannot derive global nozzle ROI because no feature ROIs exist")
    margin = NOZZLE_GLOBAL_MATCH_MARGIN_1080 * (
        width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT
    ) / 2.0
    left = min(box[0] for box in feature_boxes) - margin
    top = min(box[1] for box in feature_boxes) - margin
    right = max(box[0] + box[2] for box in feature_boxes) + margin
    bottom = max(box[1] + box[3] for box in feature_boxes) + margin
    return clamp_rect(left, top, right - left, bottom - top, width, height)


def normalized_registration_feature(image: Any, roi: tuple[int, int, int, int], mode: str) -> Any:
    import cv2

    x, y, w, h = roi
    crop = image[y : y + h, x : x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(gray)
    feature = clahe.astype("float32")
    if mode == "grad":
        grad_x = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
        feature = cv2.magnitude(grad_x, grad_y)
    mean = float(feature.mean())
    std = float(feature.std())
    return (feature - mean) / (std + 1.0e-6)


def match_registration_features(source_feature: Any, target_feature: Any, search_px: int) -> dict[str, Any]:
    import cv2

    padded = cv2.copyMakeBorder(
        source_feature,
        search_px,
        search_px,
        search_px,
        search_px,
        cv2.BORDER_CONSTANT,
        value=0,
    )
    result = cv2.matchTemplate(
        padded.astype("float32"),
        target_feature.astype("float32"),
        cv2.TM_CCOEFF_NORMED,
    )
    _min_value, max_value, _min_loc, max_loc = cv2.minMaxLoc(result)
    # matchTemplate returns where the target crop must be placed in the padded
    # source crop. The content displacement is the inverse of that placement.
    return {
        "dx": float(-(max_loc[0] - search_px)),
        "dy": float(-(max_loc[1] - search_px)),
        "correlation": float(max_value),
    }


def solve_pairwise_registration(
    records: list[dict[str, Any]], sign: float
) -> dict[str, Any] | None:
    import numpy as np

    if len(records) < 4:
        return None
    rows = []
    values = []
    weights = []
    for record in records:
        observed_dx = sign * float(record["observed_dx"])
        observed_dy = sign * float(record["observed_dy"])
        command_delta = float(record["target_command_dx"]) - float(
            record["source_command_dx"]
        )
        tool_delta = (
            (1.0 if record["target_tool"] == "t1" else 0.0)
            - (1.0 if record["source_tool"] == "t1" else 0.0)
        )
        rows.append([command_delta, 0.0, tool_delta, 0.0])
        values.append(observed_dx)
        weights.append(max(0.01, float(record["correlation"])))
        rows.append([0.0, command_delta, 0.0, tool_delta])
        values.append(observed_dy)
        weights.append(max(0.01, float(record["correlation"])))
    matrix = np.array(rows, dtype=float)
    vector = np.array(values, dtype=float)
    weight_matrix = np.diag(np.sqrt(np.array(weights, dtype=float)))
    solution = np.linalg.lstsq(weight_matrix @ matrix, weight_matrix @ vector, rcond=None)[0]

    residuals = []
    weighted_sum = 0.0
    weight_total = 0.0
    for record in records:
        observed = (
            sign * float(record["observed_dx"]),
            sign * float(record["observed_dy"]),
        )
        command_delta = float(record["target_command_dx"]) - float(
            record["source_command_dx"]
        )
        tool_delta = (
            (1.0 if record["target_tool"] == "t1" else 0.0)
            - (1.0 if record["source_tool"] == "t1" else 0.0)
        )
        predicted = (
            command_delta * float(solution[0]) + tool_delta * float(solution[2]),
            command_delta * float(solution[1]) + tool_delta * float(solution[3]),
        )
        distance = point_distance(observed, predicted)
        weight = max(0.01, float(record["correlation"]))
        weighted_sum += weight * distance * distance
        weight_total += weight
        residuals.append(
            {
                "source": record["source"],
                "target": record["target"],
                "observed_dx": round(observed[0], 3),
                "observed_dy": round(observed[1], 3),
                "predicted_dx": round(predicted[0], 3),
                "predicted_dy": round(predicted[1], 3),
                "residual_px": round(distance, 3),
                "correlation": round(float(record["correlation"]), 4),
            }
        )
    weighted_rms = math.sqrt(weighted_sum / max(1.0e-9, weight_total))
    return {
        "axis_vector_px_per_mm": [float(solution[0]), float(solution[1])],
        "t1_minus_t0_pixels": [float(solution[2]), float(solution[3])],
        "residual_rms_px": float(weighted_rms),
        "residuals": residuals,
    }


def fit_global_roi_cross_match(
    frames: list[dict[str, Any]],
    global_roi: tuple[int, int, int, int],
    red_axis_vector: tuple[float, float] | None,
) -> dict[str, Any]:
    import cv2

    search_px = max(
        8,
        int(
            round(
                NOZZLE_GLOBAL_MATCH_SEARCH_1080
                * (
                    frames[0].get("image_width", RED_BASE_WIDTH) / RED_BASE_WIDTH
                    + frames[0].get("image_height", RED_BASE_HEIGHT) / RED_BASE_HEIGHT
                )
                / 2.0
            )
        )
        if frames
        else int(round(NOZZLE_GLOBAL_MATCH_SEARCH_1080)),
    )
    items = []
    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            continue
        items.append(
            {
                "frame": frame,
                "gray": normalized_registration_feature(image, global_roi, "gray"),
                "grad": normalized_registration_feature(image, global_roi, "grad"),
            }
        )
    if len(items) < 4:
        return {
            "accepted": False,
            "rejection_reason": "need at least four readable frames for cross-match",
        }

    dx_values = sorted({float(item["frame"]["dx"]) for item in items})
    dx_steps = [
        dx_values[index + 1] - dx_values[index]
        for index in range(len(dx_values) - 1)
        if dx_values[index + 1] > dx_values[index]
    ]
    max_cross_tool_command_delta = min(dx_steps) if dx_steps else 0.0

    candidates = []
    for mode in ("gray", "grad"):
        pairwise_rows = []
        usable_records = []
        usable_same_tool = 0
        usable_cross_tool = 0
        for source_item in items:
            source_frame = source_item["frame"]
            row = {"source": source_frame["prefix"], "matches": []}
            for target_item in items:
                target_frame = target_item["frame"]
                if source_frame is target_frame:
                    row["matches"].append(
                        {
                            "target": target_frame["prefix"],
                            "dx": 0.0,
                            "dy": 0.0,
                            "correlation": 1.0,
                            "used": False,
                        }
                    )
                    continue
                match = match_registration_features(
                    source_item[mode], target_item[mode], search_px
                )
                same_tool = source_frame["tool"] == target_frame["tool"]
                threshold = 0.42 if same_tool else 0.16
                command_delta = abs(float(target_frame["dx"]) - float(source_frame["dx"]))
                useful_cross_tool_pair = (
                    same_tool
                    or command_delta <= max_cross_tool_command_delta + 1.0e-6
                )
                used = match["correlation"] >= threshold and useful_cross_tool_pair
                if used:
                    record = {
                        "source": source_frame["prefix"],
                        "target": target_frame["prefix"],
                        "source_tool": source_frame["tool"],
                        "target_tool": target_frame["tool"],
                        "source_command_dx": source_frame["dx"],
                        "target_command_dx": target_frame["dx"],
                        "observed_dx": match["dx"],
                        "observed_dy": match["dy"],
                        "correlation": match["correlation"],
                    }
                    usable_records.append(record)
                    if same_tool:
                        usable_same_tool += 1
                    else:
                        usable_cross_tool += 1
                row["matches"].append(
                    {
                        "target": target_frame["prefix"],
                        "dx": round(match["dx"], 3),
                        "dy": round(match["dy"], 3),
                        "correlation": round(match["correlation"], 4),
                        "used": used,
                    }
                )
            pairwise_rows.append(row)

        for sign in (1.0, -1.0):
            fit = solve_pairwise_registration(usable_records, sign)
            if fit is None:
                continue
            axis = fit["axis_vector_px_per_mm"]
            axis_len = math.hypot(axis[0], axis[1])
            red_alignment = None
            red_ratio_penalty = 0.0
            if red_axis_vector and axis_len > 0:
                red_len = math.hypot(red_axis_vector[0], red_axis_vector[1])
                if red_len > 0:
                    red_alignment = (
                        axis[0] * red_axis_vector[0] + axis[1] * red_axis_vector[1]
                    ) / (axis_len * red_len)
                    red_ratio_penalty = abs(axis_len - red_len) / red_len
            if red_alignment is not None and red_alignment < 0:
                direction_penalty = 1000.0
            else:
                direction_penalty = 0.0
            score = (
                float(fit["residual_rms_px"])
                + direction_penalty
                + 3.0 * red_ratio_penalty
                + (0.15 if mode == "grad" else 0.0)
            )
            correlations = [float(record["correlation"]) for record in usable_records]
            correlations_sorted = sorted(correlations)
            median_corr = correlations_sorted[len(correlations_sorted) // 2] if correlations else 0.0
            candidates.append(
                {
                    **fit,
                    "feature_mode": mode,
                    "sign": sign,
                    "score": round(score, 4),
                    "red_axis_alignment": (
                        round(red_alignment, 4) if red_alignment is not None else None
                    ),
                    "usable_pair_count": len(usable_records),
                    "usable_same_tool_pair_count": usable_same_tool,
                    "usable_cross_tool_pair_count": usable_cross_tool,
                    "rejected_pair_count": len(items) * (len(items) - 1) - len(usable_records),
                    "correlation_min": round(min(correlations), 4) if correlations else None,
                    "correlation_median": round(median_corr, 4) if correlations else None,
                    "pairwise_match_matrix": pairwise_rows,
                }
            )

    if not candidates:
        return {
            "accepted": False,
            "rejection_reason": "no usable cross-match model could be fitted",
            "global_roi": list(global_roi),
            "search_px": search_px,
        }

    best = min(candidates, key=lambda item: item["score"])
    axis = best["axis_vector_px_per_mm"]
    delta = best["t1_minus_t0_pixels"]
    axis_len = math.hypot(axis[0], axis[1])
    accepted = (
        best["usable_pair_count"] >= 12
        and best["usable_same_tool_pair_count"] >= 6
        and best["usable_cross_tool_pair_count"] >= 4
        and best["residual_rms_px"] <= 4.0
        and axis_len >= 1.0
    )
    if axis_len > 0:
        ux, uy = axis[0] / axis_len, axis[1] / axis_len
        px, py = -uy, ux
        along_x_px = delta[0] * ux + delta[1] * uy
        perpendicular_px = delta[0] * px + delta[1] * py
    else:
        along_x_px = 0.0
        perpendicular_px = 0.0
    reference_points = []
    for frame in frames:
        expected = frame.get("expected_nozzle_feature_center_px")
        if not expected:
            continue
        tool_index = 1.0 if frame["tool"] == "t1" else 0.0
        reference_points.append(
            (
                float(expected[0]) - float(frame["dx"]) * axis[0] - tool_index * delta[0],
                float(expected[1]) - float(frame["dx"]) * axis[1] - tool_index * delta[1],
            )
        )
    reference_center = None
    if reference_points:
        reference_center = (
            sum(point[0] for point in reference_points) / len(reference_points),
            sum(point[1] for point in reference_points) / len(reference_points),
        )
        for frame in frames:
            tool_index = 1.0 if frame["tool"] == "t1" else 0.0
            predicted = (
                reference_center[0] + float(frame["dx"]) * axis[0] + tool_index * delta[0],
                reference_center[1] + float(frame["dx"]) * axis[1] + tool_index * delta[1],
            )
            frame["registration_prediction_center_px"] = [
                round(predicted[0], 3),
                round(predicted[1], 3),
            ]
    if not accepted:
        reason = (
            "cross-match fit did not meet pair-count/residual thresholds: "
            f"pairs={best['usable_pair_count']}, rms={best['residual_rms_px']:.2f}px"
        )
    else:
        reason = ""
    return {
        **best,
        "accepted": accepted,
        "rejection_reason": reason,
        "global_roi": list(global_roi),
        "search_px": search_px,
        "axis_vector_px_per_mm": [round(axis[0], 4), round(axis[1], 4)],
        "axis_px_per_mm": round(axis_len, 4),
        "axis_angle_deg": round(math.degrees(math.atan2(axis[1], axis[0])), 4)
        if axis_len > 0
        else None,
        "t1_minus_t0_pixels": [round(delta[0], 4), round(delta[1], 4)],
        "along_x_px": round(along_x_px, 4),
        "along_x_mm_approx": round(along_x_px / axis_len, 5) if axis_len > 0 else None,
        "perpendicular_px": round(perpendicular_px, 4),
        "perpendicular_mm_approx": round(perpendicular_px / axis_len, 5)
        if axis_len > 0
        else None,
        "reference_center_px": [round(reference_center[0], 4), round(reference_center[1], 4)]
        if reference_center
        else None,
        "residual_rms_px": round(float(best["residual_rms_px"]), 4),
        "measurement_source": "global_roi_cross_match",
    }


def fit_points_by_dx(samples: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [sample for sample in samples if sample.get("point_px")]
    if len(usable) < 2:
        return {"ok": False, "rejection_reason": "need at least two points"}
    dxs = [float(sample["dx"]) for sample in usable]
    xs = [float(sample["point_px"][0]) for sample in usable]
    ys = [float(sample["point_px"][1]) for sample in usable]
    mean_dx = sum(dxs) / len(dxs)
    denom = sum((dx - mean_dx) ** 2 for dx in dxs)
    if denom <= 0:
        return {"ok": False, "rejection_reason": "dx values do not vary"}
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    vx = sum((dx - mean_dx) * (px - mean_x) for dx, px in zip(dxs, xs)) / denom
    vy = sum((dx - mean_dx) * (py - mean_y) for dx, py in zip(dxs, ys)) / denom
    ix = mean_x - vx * mean_dx
    iy = mean_y - vy * mean_dx
    residuals = [
        point_distance((px, py), (ix + dx * vx, iy + dx * vy))
        for dx, px, py in zip(dxs, xs, ys)
    ]
    rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    px_per_mm = math.hypot(vx, vy)
    return {
        "ok": True,
        "count": len(usable),
        "intercept_px": [round(ix, 3), round(iy, 3)],
        "vector_px_per_mm": [round(vx, 3), round(vy, 3)],
        "px_per_mm": round(px_per_mm, 3),
        "axis_angle_deg": round(math.degrees(math.atan2(vy, vx)), 3),
        "residual_rms_px": round(rms, 3),
        "residuals_px": [round(value, 3) for value in residuals],
    }


def average_axis_vector(fits: dict[str, dict[str, Any]]) -> tuple[float, float] | None:
    vectors = [
        fit["vector_px_per_mm"]
        for fit in fits.values()
        if fit.get("ok") and fit.get("px_per_mm", 0) > 1
    ]
    if not vectors:
        return None
    return (
        sum(float(vector[0]) for vector in vectors) / len(vectors),
        sum(float(vector[1]) for vector in vectors) / len(vectors),
    )


def choose_motion_consistent_nozzle(
    frames: list[dict[str, Any]], axis_vector: tuple[float, float] | None
) -> dict[str, Any]:
    if axis_vector is None:
        return {
            "accepted": False,
            "confidence": 0.0,
            "rejection_reason": "no stable red-marker motion vector",
        }
    vx, vy = axis_vector
    scale = 1.0
    if frames:
        scale = (
            frames[0].get("image_width", RED_BASE_WIDTH) / RED_BASE_WIDTH
            + frames[0].get("image_height", RED_BASE_HEIGHT) / RED_BASE_HEIGHT
        ) / 2.0
    cluster_radius = 22.0 * scale
    residual_limit = 18.0 * scale
    members: list[dict[str, Any]] = []
    for frame in frames:
        for candidate in frame.get("nozzle_candidates", []):
            dx = float(frame["dx"])
            intercept = (candidate["cx"] - dx * vx, candidate["cy"] - dx * vy)
            members.append(
                {
                    "dx": dx,
                    "dx_label": frame["dx_label"],
                    "candidate": candidate,
                    "intercept": intercept,
                }
            )
    if not members:
        return {
            "accepted": False,
            "confidence": 0.0,
            "rejection_reason": "no nozzle candidates in red-marker ROI",
        }

    best_cluster: list[dict[str, Any]] = []
    best_score = -1.0e9
    for seed in members:
        cluster = [
            member
            for member in members
            if point_distance(member["intercept"], seed["intercept"]) <= cluster_radius
        ]
        distinct_dx = {member["dx_label"] for member in cluster}
        if len(distinct_dx) < 2:
            continue
        score = (
            130.0 * len(distinct_dx)
            + sum(float(member["candidate"].get("base_score", 0.0)) for member in cluster)
            / max(1, len(cluster))
        )
        if score > best_score:
            best_score = score
            best_cluster = cluster

    if not best_cluster:
        return {
            "accepted": False,
            "confidence": 0.0,
            "rejection_reason": "no candidate cluster followed the commanded X motion",
        }

    selected_by_dx: dict[str, dict[str, Any]] = {}
    for member in best_cluster:
        label = member["dx_label"]
        current = selected_by_dx.get(label)
        if current is None or member["candidate"].get("base_score", 0) > current.get(
            "base_score", -1.0e9
        ):
            selected_by_dx[label] = member["candidate"]

    intercepts = []
    residuals = []
    for frame in frames:
        candidate = selected_by_dx.get(frame["dx_label"])
        if not candidate:
            continue
        dx = float(frame["dx"])
        intercepts.append((candidate["cx"] - dx * vx, candidate["cy"] - dx * vy))
    ix = sum(point[0] for point in intercepts) / len(intercepts)
    iy = sum(point[1] for point in intercepts) / len(intercepts)
    for frame in frames:
        candidate = selected_by_dx.get(frame["dx_label"])
        if not candidate:
            continue
        dx = float(frame["dx"])
        predicted = (ix + dx * vx, iy + dx * vy)
        residuals.append(point_distance((candidate["cx"], candidate["cy"]), predicted))
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    accepted = len(selected_by_dx) >= 2 and rms <= residual_limit
    confidence = max(
        0.0,
        min(1.0, 0.22 + 0.2 * len(selected_by_dx) - rms / max(1.0, 80.0 * scale)),
    )
    if not accepted:
        reason = f"candidate residual {rms:.1f}px exceeds {residual_limit:.1f}px"
    else:
        reason = ""
    return {
        "accepted": accepted,
        "confidence": round(confidence, 4),
        "intercept_px": [round(ix, 3), round(iy, 3)],
        "selected_by_dx": {
            label: {
                **candidate,
                "cx": round(candidate["cx"], 3),
                "cy": round(candidate["cy"], 3),
                "r": round(candidate["r"], 3),
            }
            for label, candidate in selected_by_dx.items()
        },
        "selected_count": len(selected_by_dx),
        "residual_rms_px": round(rms, 3),
        "residuals_px": [round(value, 3) for value in residuals],
        "rejection_reason": reason,
    }


def annotate_sweep_frame(
    image: Any,
    frame: dict[str, Any],
    nozzle_result: dict[str, Any] | None,
    axis_vector: tuple[float, float] | None,
) -> Any:
    import cv2

    overlay = image.copy()
    red = frame.get("red_marker", {})
    red_roi = red.get("roi")
    if red_roi:
        x, y, w, h = red_roi
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 180, 0), 2)
    if red.get("accepted"):
        bx, by, bw, bh = red["bbox"]
        cx, cy = red["center_px"]
        cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
        cv2.drawMarker(
            overlay,
            (int(round(cx)), int(round(cy))),
            (0, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=28,
            thickness=2,
        )
    if frame.get("global_nozzle_roi"):
        gx, gy, gw, gh = frame["global_nozzle_roi"]
        cv2.rectangle(overlay, (gx, gy), (gx + gw, gy + gh), (0, 220, 255), 2)
    nozzle_roi = frame.get("feature_roi") or frame.get("nozzle_roi")
    if nozzle_roi:
        nx, ny, nw, nh = nozzle_roi
        cv2.rectangle(overlay, (nx, ny), (nx + nw, ny + nh), (255, 255, 0), 2)
    expected = frame.get("expected_nozzle_feature_center_px")
    if expected:
        cv2.drawMarker(
            overlay,
            (int(round(expected[0])), int(round(expected[1]))),
            (255, 255, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=18,
            thickness=2,
        )
    selected = None
    predicted_center = frame.get("registration_prediction_center_px")
    if predicted_center:
        predicted = (int(round(predicted_center[0])), int(round(predicted_center[1])))
        marker_size = max(18, int(round(28 * image.shape[1] / RED_BASE_WIDTH)))
        half_box = max(20, int(round(34 * image.shape[1] / RED_BASE_WIDTH)))
        cv2.rectangle(
            overlay,
            (predicted[0] - half_box, predicted[1] - half_box),
            (predicted[0] + half_box, predicted[1] + half_box),
            (255, 0, 255),
            2,
        )
        cv2.drawMarker(
            overlay,
            predicted,
            (255, 0, 255),
            markerType=cv2.MARKER_TILTED_CROSS,
            markerSize=marker_size,
            thickness=2,
        )
    label = f"{frame['tool'].upper()} dx={frame['dx']:.3g}mm"
    if nozzle_result and nozzle_result.get("measurement_source") == "global_roi_cross_match":
        label += " global-ROI cross-match"
    else:
        label += " nozzle=rejected"
    cv2.rectangle(overlay, (0, 0), (780, 48), (0, 0, 0), -1)
    cv2.putText(
        overlay,
        label,
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
    )
    return overlay


def crop_for_contact_tile(image: Any, frame: dict[str, Any]) -> Any:
    height, width = image.shape[:2]
    boxes = []
    red = frame.get("red_marker", {})
    if red.get("accepted"):
        boxes.append(red["bbox"])
    nozzle_roi = frame.get("feature_roi") or frame.get("nozzle_roi")
    if nozzle_roi:
        boxes.append(nozzle_roi)
    if frame.get("global_nozzle_roi"):
        boxes.append(frame["global_nozzle_roi"])
    red_roi = red.get("roi")
    if red_roi:
        boxes.append(red_roi)
    if not boxes:
        boxes.append((0, 0, width, height))
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    pad_x = int(round(140 * width / RED_BASE_WIDTH))
    pad_y = int(round(105 * height / RED_BASE_HEIGHT))
    x, y, w, h = clamp_rect(
        left - pad_x,
        top - pad_y,
        (right - left) + 2 * pad_x,
        (bottom - top) + 2 * pad_y,
        width,
        height,
    )
    return image[y : y + h, x : x + w]


def letterbox(image: Any, tile_w: int, tile_h: int) -> Any:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = min(tile_w / width, tile_h / height)
    resized_w = max(1, int(round(width * scale)))
    resized_h = max(1, int(round(height * scale)))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((tile_h, tile_w, 3), 245, dtype=np.uint8)
    x = (tile_w - resized_w) // 2
    y = (tile_h - resized_h) // 2
    canvas[y : y + resized_h, x : x + resized_w] = resized
    return canvas


def draw_text_lines(
    canvas: Any,
    lines: list[str],
    origin: tuple[int, int],
    *,
    line_height: int = 26,
    scale: float = 0.62,
    color: tuple[int, int, int] = (20, 20, 20),
) -> None:
    import cv2

    x, y = origin
    for index, line in enumerate(lines):
        cv2.putText(
            canvas,
            line,
            (x, y + index * line_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            2,
            cv2.LINE_AA,
        )


def write_contact_sheet(
    frames: list[dict[str, Any]], analysis: dict[str, Any], contact_sheet_path: Path
) -> None:
    import cv2
    import numpy as np

    tile_w, tile_h = 540, 405
    dx_labels = [dx_label(float(dx)) for dx in analysis["dx_values"]]
    cols, rows = max(1, len(dx_labels)), 2
    summary_h = 345
    sheet = np.full((rows * tile_h + summary_h, cols * tile_w, 3), 255, dtype=np.uint8)
    frame_by_key = {(frame["tool"], frame["dx_label"]): frame for frame in frames}
    for row, tool in enumerate(("t0", "t1")):
        for col, label in enumerate(dx_labels):
            frame = frame_by_key.get((tool, label))
            if not frame:
                continue
            overlay = cv2.imread(frame["overlay_path"])
            if overlay is None:
                overlay = cv2.imread(frame["image_path"])
            crop = crop_for_contact_tile(overlay, frame)
            tile = letterbox(crop, tile_w, tile_h)
            y = row * tile_h
            x = col * tile_w
            sheet[y : y + tile_h, x : x + tile_w] = tile
            cv2.rectangle(sheet, (x, y), (x + tile_w - 1, y + tile_h - 1), (80, 80, 80), 2)

    summary_lines = [
        f"IDEX nozzle vision sweep: {analysis['run_name']}",
        f"report: {public_url(contact_sheet_path)}",
        "measurement: global ROI cross-match; red marker is locator only",
    ]
    red_axis = analysis.get("red_axis_vector_px_per_mm")
    if red_axis:
        summary_lines.append(
            "red-marker image X axis: "
            f"vx={red_axis[0]:.3f}px/mm, vy={red_axis[1]:.3f}px/mm, "
            f"|v|={analysis['red_axis_px_per_mm']:.3f}px/mm, "
            f"angle={analysis['red_axis_angle_deg']:.3f}deg"
        )
    cross = analysis.get("cross_match", {})
    if cross:
        summary_lines.append(
            "cross-match image X axis: "
            f"vx={cross.get('axis_vector_px_per_mm', [None, None])[0]}px/mm, "
            f"vy={cross.get('axis_vector_px_per_mm', [None, None])[1]}px/mm, "
            f"|v|={cross.get('axis_px_per_mm')}px/mm, "
            f"angle={cross.get('axis_angle_deg')}deg"
        )
        summary_lines.append(
            "cross-match quality: "
            f"mode={cross.get('feature_mode')} pairs={cross.get('usable_pair_count')} "
            f"same={cross.get('usable_same_tool_pair_count')} "
            f"cross={cross.get('usable_cross_tool_pair_count')} "
            f"rms={cross.get('residual_rms_px')}px "
            f"corr_med={cross.get('correlation_median')}"
        )
    for tool in ("t0", "t1"):
        fit = analysis.get("red_marker_fits", {}).get(tool, {})
        summary_lines.append(
            f"{tool.upper()} red fit: ok={fit.get('ok')} "
            f"intercept={fit.get('intercept_px')} rms={fit.get('residual_rms_px')}"
        )
    red_delta = analysis.get("red_marker_delta_t1_minus_t0") or {}
    summary_lines.append(
        "red locator T1-T0 sanity: "
        f"dx={red_delta.get('dx')} dy={red_delta.get('dy')} "
        f"alongX={red_delta.get('along_axis_mm_approx')}mm"
    )
    nozzle_delta = analysis.get("nozzle_delta_t1_minus_t0") or {}
    summary_lines.append(
        "nozzle-image T1-T0: "
        f"dx={nozzle_delta.get('dx')} dy={nozzle_delta.get('dy')} "
        f"alongX={nozzle_delta.get('along_x_mm_approx')}mm "
        f"perp={nozzle_delta.get('perpendicular_mm_approx')}mm"
    )
    if not analysis.get("ok"):
        failures = analysis.get("hard_failures") or [cross.get("rejection_reason", "rejected")]
        summary_lines.append(f"STATUS: FAILED; {'; '.join(str(item) for item in failures[:3])}")
    else:
        summary_lines.append("STATUS: global ROI cross-match accepted.")

    summary_y = rows * tile_h + 35
    cv2.rectangle(sheet, (0, rows * tile_h), (cols * tile_w, sheet.shape[0]), (238, 238, 238), -1)
    draw_text_lines(sheet, summary_lines, (24, summary_y), line_height=27, scale=0.58)
    cv2.imwrite(str(contact_sheet_path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def update_sweep_latest_links(
    run_dir: Path, result_path: Path, contact_sheet_path: Path | None
) -> None:
    NOZZLE_SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    links = [(result_path, "latest_result.json"), (run_dir, "latest")]
    if contact_sheet_path:
        links.append((contact_sheet_path, "latest_contact_sheet.jpg"))
    for target, name in links:
        latest = NOZZLE_SWEEP_DIR / name
        tmp = NOZZLE_SWEEP_DIR / f".{name}.tmp"
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        os.symlink(os.path.relpath(target, NOZZLE_SWEEP_DIR), tmp)
        os.replace(tmp, latest)


def analyze_sweep_frames(
    frames: list[dict[str, Any]], run_dir: Path, overlay_dir: Path | None = None
) -> dict[str, Any]:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on Pi package install
        return {
            "ok": False,
            "proxy_only": True,
            "error": f"OpenCV import failed: {exc}",
        }

    hard_failures: list[str] = []
    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            frame["analysis_error"] = f"Could not read {frame['image_path']}"
            hard_failures.append(
                f"{frame['tool']} dx={frame['dx']}: {frame['analysis_error']}"
            )
            continue
        height, width = image.shape[:2]
        frame["image_width"] = width
        frame["image_height"] = height
        red = detect_red_marker(image)
        frame["red_marker"] = red
        if not red.get("accepted"):
            reason = red.get("rejection_reason", "red marker detection failed")
            frame["analysis_error"] = reason
            hard_failures.append(f"{frame['tool']} dx={frame['dx']}: {reason}")
            continue
        try:
            nozzle_roi = derive_nozzle_roi(red, width, height)
        except RuntimeError as exc:
            frame["analysis_error"] = str(exc)
            hard_failures.append(f"{frame['tool']} dx={frame['dx']}: {exc}")
            continue
        frame["nozzle_roi"] = list(nozzle_roi)
        frame["feature_roi"] = list(nozzle_roi)
        candidates = detect_nozzle_candidates(image, nozzle_roi)
        frame["nozzle_candidates"] = candidates
        if not candidates:
            reason = "no nozzle candidates found in red-marker-derived ROI"
            frame["analysis_error"] = reason
            hard_failures.append(f"{frame['tool']} dx={frame['dx']}: {reason}")

    red_marker_fits: dict[str, dict[str, Any]] = {}
    for tool in ("t0", "t1"):
        samples = [
            {
                "dx": frame["dx"],
                "point_px": frame.get("red_marker", {}).get("center_px"),
            }
            for frame in frames
            if frame["tool"] == tool
        ]
        red_marker_fits[tool] = fit_points_by_dx(samples)
        if not red_marker_fits[tool].get("ok"):
            hard_failures.append(
                f"{tool}: red marker fit failed: "
                f"{red_marker_fits[tool].get('rejection_reason', 'unknown fit failure')}"
            )

    red_axis_vector = average_axis_vector(red_marker_fits)
    if red_axis_vector is None:
        hard_failures.append("red marker image X axis could not be fit for both tools")
    red_axis_px_per_mm = math.hypot(*(red_axis_vector or (0.0, 0.0)))
    red_axis_angle = (
        math.degrees(math.atan2(red_axis_vector[1], red_axis_vector[0]))
        if red_axis_vector
        else None
    )

    analysis_frames = [
        frame
        for frame in frames
        if frame.get("image_width")
        and frame.get("image_height")
        and frame.get("red_marker", {}).get("accepted")
        and frame.get("nozzle_candidates")
    ]
    global_roi = None
    if analysis_frames:
        try:
            global_roi = derive_global_nozzle_roi(
                analysis_frames,
                int(analysis_frames[0]["image_width"]),
                int(analysis_frames[0]["image_height"]),
            )
        except RuntimeError as exc:
            hard_failures.append(str(exc))
    else:
        hard_failures.append("no readable frames passed red marker and nozzle-candidate gates")
    if global_roi:
        for frame in analysis_frames:
            frame["global_nozzle_roi"] = list(global_roi)

    if hard_failures:
        cross_match = {
            "accepted": False,
            "rejection_reason": "; ".join(hard_failures),
        }
    elif global_roi and red_axis_vector:
        cross_match = fit_global_roi_cross_match(analysis_frames, global_roi, red_axis_vector)
        if not cross_match.get("accepted"):
            hard_failures.append(
                "global ROI cross-match failed: "
                f"{cross_match.get('rejection_reason', 'unknown cross-match failure')}"
            )
    else:
        reason = "no global ROI or red marker axis could be derived"
        hard_failures.append(reason)
        cross_match = {"accepted": False, "rejection_reason": reason}

    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            continue
        overlay = annotate_sweep_frame(image, frame, cross_match, red_axis_vector)
        overlay_root = overlay_dir or run_dir
        overlay_root.mkdir(parents=True, exist_ok=True)
        overlay_path = overlay_root / f"{frame['prefix']}_overlay.jpg"
        cv2.imwrite(str(overlay_path), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        frame["overlay_path"] = str(overlay_path)
        frame["overlay_url"] = safe_vision_url(overlay_path)

    red_delta = None
    if red_marker_fits.get("t0", {}).get("ok") and red_marker_fits.get("t1", {}).get("ok"):
        t0 = red_marker_fits["t0"]["intercept_px"]
        t1 = red_marker_fits["t1"]["intercept_px"]
        dx = float(t1[0]) - float(t0[0])
        dy = float(t1[1]) - float(t0[1])
        red_delta = {"dx": round(dx, 3), "dy": round(dy, 3), "distance": round(math.hypot(dx, dy), 3)}
        if red_axis_vector and red_axis_px_per_mm > 0:
            ux, uy = (
                red_axis_vector[0] / red_axis_px_per_mm,
                red_axis_vector[1] / red_axis_px_per_mm,
            )
            red_delta["along_axis_mm_approx"] = round(
                (dx * ux + dy * uy) / red_axis_px_per_mm, 4
            )

    nozzle_delta = None
    if cross_match.get("accepted") and cross_match.get("t1_minus_t0_pixels"):
        dx, dy = cross_match["t1_minus_t0_pixels"]
        nozzle_delta = {
            "dx": round(dx, 3),
            "dy": round(dy, 3),
            "distance": round(math.hypot(dx, dy), 3),
            "along_x_px": cross_match.get("along_x_px"),
            "along_x_mm_approx": cross_match.get("along_x_mm_approx"),
            "perpendicular_px": cross_match.get("perpendicular_px"),
            "perpendicular_mm_approx": cross_match.get("perpendicular_mm_approx"),
            "measurement_source": "global_roi_cross_match",
        }

    if nozzle_delta:
        message = "Global ROI cross-match accepted."
    else:
        message = (
            "Nozzle vision sweep failed hard: " + "; ".join(hard_failures)
            if hard_failures
            else "Nozzle vision sweep rejected: global ROI cross-match was not reliable enough."
        )

    return {
        "ok": bool(nozzle_delta),
        "proxy_only": not bool(nozzle_delta),
        "hard_failures": hard_failures,
        "red_marker_fits": red_marker_fits,
        "red_axis_vector_px_per_mm": [round(red_axis_vector[0], 3), round(red_axis_vector[1], 3)] if red_axis_vector else None,
        "red_axis_px_per_mm": round(red_axis_px_per_mm, 3) if red_axis_vector else None,
        "red_axis_angle_deg": round(red_axis_angle, 3) if red_axis_angle is not None else None,
        "global_nozzle_roi": list(global_roi) if global_roi else None,
        "cross_match": cross_match,
        "red_marker_delta_t1_minus_t0": red_delta,
        "nozzle_delta_t1_minus_t0": nozzle_delta,
        "message": message,
    }


def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc)
    run_name = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{sanitize_name(args.name)}"
    run_dir = NOZZLE_SWEEP_DIR / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "result.json"
    contact_sheet_path = run_dir / "contact_sheet.jpg"
    dx_values = parse_dx_values(args.dx)
    result: dict[str, Any] = {
        "ok": False,
        "timestamp_utc": timestamp.isoformat(),
        "run_name": run_name,
        "target_gcode_position": {"x": args.x, "y": args.y, "z": args.z},
        "dx_values": dx_values,
        "report_only": True,
        "offsets_applied": False,
        "camera_source": "vision_framebuffer",
        "crowsnest_managed": False,
        "run_dir": str(run_dir),
        "run_url": vision_url(run_dir),
        "result_url": vision_url(result_path),
        "contact_sheet_url": vision_url(contact_sheet_path),
        "contact_sheet_public_url": public_url(contact_sheet_path),
        "latest_contact_sheet_url": vision_url(
            NOZZLE_SWEEP_DIR / "latest_contact_sheet.jpg"
        ),
        "latest_contact_sheet_public_url": public_url(
            vision_url(NOZZLE_SWEEP_DIR / "latest_contact_sheet.jpg")
        ),
    }

    frames: list[dict[str, Any]] = []
    try:
        status = wait_ready_and_idle(args.moonraker_url, args.ready_timeout)
        if "x" not in status["toolhead"].get("homed_axes", ""):
            raise RuntimeError("X is not homed")
        if "y" not in status["toolhead"].get("homed_axes", ""):
            raise RuntimeError("Y is not homed")
        if "z" not in status["toolhead"].get("homed_axes", ""):
            raise RuntimeError("Z is not homed")

        original_extruder = status["toolhead"].get("extruder", "extruder")
        original_position = status["gcode_move"].get(
            "gcode_position", [args.x, args.y, args.z, 0]
        )
        result["original"] = {
            "extruder": original_extruder,
            "gcode_position": original_position,
        }
        result["crowsnest_was_active"] = service_is_active(CROWSNEST_SERVICE)

        for tool, macro in (("t0", "T0"), ("t1", "T1")):
            for dx in dx_values:
                x_target = args.x + dx
                prefix = f"{tool}_dx{dx_label(dx)}"
                run_gcode(
                    args.moonraker_url,
                    (
                        f"{macro}\n"
                        "G90\n"
                        f"G1 X{x_target:.3f} Y{args.y:.3f} Z{args.z:.3f} "
                        f"F{args.feedrate:.0f}\n"
                        "M400"
                    ),
                )
                time.sleep(args.settle_time)
                fresh_after_utc = datetime.now(timezone.utc).isoformat()
                capture_name = f"{run_name}_{prefix}"
                capture = capture_once(capture_name, fresh_after_utc)
                artifacts = copy_capture_artifacts_to_run(capture, run_dir, prefix)
                frames.append(
                    {
                        "tool": tool,
                        "macro": macro,
                        "dx": dx,
                        "dx_label": dx_label(dx),
                        "prefix": prefix,
                        "target_gcode_position": {
                            "x": round(x_target, 4),
                            "y": args.y,
                            "z": args.z,
                        },
                        "capture": capture,
                        "image_path": artifacts["image_path"],
                        "metadata_path": artifacts["metadata_path"],
                        "image_url": artifacts["image_url"],
                        "metadata_url": artifacts["metadata_url"],
                    }
                )

        analysis = analyze_sweep_frames(frames, run_dir)
        analysis.update({"run_name": run_name, "dx_values": dx_values})
        result["frames"] = frames
        result["analysis"] = analysis
        result["ok"] = bool(analysis.get("ok"))
        result["proxy_only"] = bool(analysis.get("proxy_only"))
        result["message"] = analysis.get("message")
        if frames:
            write_contact_sheet(frames, analysis, contact_sheet_path)
            result["contact_sheet_path"] = str(contact_sheet_path)
            result["contact_sheet_url"] = vision_url(contact_sheet_path)
            result["contact_sheet_public_url"] = public_url(contact_sheet_path)

    except Exception as exc:
        result["error"] = str(exc)
        result["message"] = "Nozzle vision sweep failed before producing a complete result."
        if frames:
            result["frames"] = frames
    finally:
        if args.restore and result.get("original"):
            try:
                original = result["original"]
                macro = "T1" if original.get("extruder") == "extruder1" else "T0"
                pos = original.get("gcode_position") or [args.x, args.y, args.z]
                run_gcode(
                    args.moonraker_url,
                    (
                        f"{macro}\n"
                        "G90\n"
                        f"G1 X{float(pos[0]):.3f} Y{float(pos[1]):.3f} "
                        f"Z{float(pos[2]):.3f} F{args.feedrate:.0f}\n"
                        "M400"
                    ),
                )
                result["restore"] = {"ok": True, "tool": macro, "gcode_position": pos[:3]}
            except Exception as exc:
                result["restore"] = {"ok": False, "error": str(exc)}

        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        update_sweep_latest_links(
            run_dir,
            result_path,
            contact_sheet_path if contact_sheet_path.exists() else None,
        )
        if contact_sheet_path.exists():
            console_respond(
                args.moonraker_url,
                f"IDEX nozzle sweep report: {public_url(contact_sheet_path)}",
            )
            console_respond(
                args.moonraker_url,
                "Latest nozzle sweep report: "
                f"{public_url(vision_url(NOZZLE_SWEEP_DIR / 'latest_contact_sheet.jpg'))}",
            )
        elif result.get("error"):
            console_respond(
                args.moonraker_url,
                f"IDEX nozzle sweep failed: {result['error']}",
            )

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moonraker-url", default=DEFAULT_MOONRAKER_URL)
    parser.add_argument("--name", default="manual")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--sweep",
        action="store_true",
        help="Required. The single-image nozzle check path was removed.",
    )
    mode.add_argument(
        "--prepare-job",
        action="store_true",
        help="Generate an immutable prepared vision job without moving the printer.",
    )
    mode.add_argument(
        "--start-prepared-job",
        metavar="JOB_ID",
        help="Start and monitor an existing prepared vision job through virtual SD.",
    )
    mode.add_argument(
        "--run-acquisition-job",
        action="store_true",
        help="Prepare, start, and monitor an acquisition-only virtual SD vision job.",
    )
    mode.add_argument(
        "--analyze-job",
        metavar="JOB_ID",
        help="Analyze an acquired vision job and write job-local report artifacts.",
    )
    mode.add_argument(
        "--run-job",
        action="store_true",
        help="Prepare, acquire, analyze, and report a complete nozzle vision job.",
    )
    mode.add_argument(
        "--refresh-ui",
        action="store_true",
        help="Regenerate static vision job HTML and jobs.json without printer motion.",
    )
    parser.add_argument("--x", type=float, default=195.0)
    parser.add_argument("--y", type=float, default=-14.8)
    parser.add_argument("--z", type=float)
    parser.add_argument("--dx", default="0,3,6,9,12")
    parser.add_argument("--feedrate", type=float, default=3600.0)
    parser.add_argument("--settle-time", type=float, default=0.75)
    parser.add_argument("--job-root", type=Path, default=NOZZLE_JOB_ROOT)
    parser.add_argument("--job-id")
    parser.add_argument("--camera", default=VISION_JOB_CAMERA)
    parser.add_argument("--profile", default=VISION_JOB_PROFILE)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument("--virtual-sd-root", type=Path, default=DEFAULT_VIRTUAL_SD_ROOT)
    parser.add_argument("--virtual-sd-subdir", default=DEFAULT_VIRTUAL_SD_SUBDIR)
    parser.add_argument("--monitor-timeout", type=float, default=180.0)
    parser.add_argument("--restore", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--manage-crowsnest",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Compatibility no-op; nozzle vision uses the RAM framebuffer.",
    )
    args = parser.parse_args(argv)
    if (
        not args.sweep
        and not args.prepare_job
        and not args.start_prepared_job
        and not args.run_acquisition_job
        and not args.analyze_job
        and not args.run_job
        and not args.refresh_ui
    ):
        parser.error(
            "single-image nozzle vision check was removed; use --sweep, "
            "--prepare-job, --start-prepared-job, --run-acquisition-job, "
            "--analyze-job, --run-job, or --refresh-ui"
        )
    if args.z is None:
        args.z = 20.0
    if args.refresh_ui:
        summary = refresh_vision_ui(Path(args.job_root))
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.prepare_job:
        summary = prepare_nozzle_sweep_job(args)
        attach_ui_refresh(summary, args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary.get("ok") else 1
    if args.start_prepared_job or args.run_acquisition_job:
        try:
            result = (
                run_acquisition_job(args)
                if args.run_acquisition_job
                else start_prepared_job(args)
            )
        except Exception as exc:
            result = {
                "ok": False,
                "error": str(exc),
                "job_id": args.start_prepared_job or args.job_id,
            }
        attach_ui_refresh(result, args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.analyze_job or args.run_job:
        try:
            result = run_full_job(args) if args.run_job else analyze_acquired_job(args)
        except Exception as exc:
            result = {
                "ok": False,
                "error": str(exc),
                "job_id": args.analyze_job or args.job_id,
            }
        attach_ui_refresh(result, args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    result = run_sweep(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
