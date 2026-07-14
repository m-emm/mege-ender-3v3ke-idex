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
DEFAULT_VIRTUAL_SD_SUBDIR = os.environ.get("VISION_VIRTUAL_SD_SUBDIR", "vision_jobs")
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
    for v in os.environ.get("VISION_NOZZLE_SWEEP_FEATURE_OFFSET_1080", "25,100").split(
        ","
    )
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
NOZZLE_Z_TIP_ROI_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_Z_TIP_ROI_1080", "620,250,820,650").split(
        ","
    )
)
NOZZLE_Z_COARSE_ROI_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_Z_COARSE_ROI_1080", "960,360,160,150").split(
        ","
    )
)
NOZZLE_Z_REFINED_ROI_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_Z_REFINED_ROI_1080", "1030,500,95,80").split(
        ","
    )
)
NOZZLE_Z_COARSE_SEARCH_PAD_1080 = float(
    os.environ.get("VISION_NOZZLE_Z_COARSE_SEARCH_PAD_1080", "75")
)
NOZZLE_Z_REFINED_SEARCH_PAD_1080 = float(
    os.environ.get("VISION_NOZZLE_Z_REFINED_SEARCH_PAD_1080", "45")
)
NOZZLE_Z_COARSE_MIN_CORRELATION = float(
    os.environ.get("VISION_NOZZLE_Z_COARSE_MIN_CORRELATION", "0.80")
)
NOZZLE_Z_REFINED_MIN_CORRELATION = float(
    os.environ.get("VISION_NOZZLE_Z_REFINED_MIN_CORRELATION", "0.85")
)
PUBLIC_BASE_URL = os.environ.get("VISION_PUBLIC_BASE_URL", "http://menderpi.local")
NAME_REPLACEMENTS = str.maketrans({c: "_" for c in " /\\:;|?*[]{}()<>'\"`$&!"})
VISION_JOB_SCHEMA_VERSION = 1
VISION_JOB_KIND = "idex_nozzle_sweep"
BED_Y_JOB_KIND = "nozzle_cam_bed_y_sweep"
BED_Y_MEASUREMENT = "nozzle_cam_bed_y_motion"
NOZZLE_Z_JOB_KIND = "nozzle_cam_nozzle_z_sweep"
NOZZLE_Z_MEASUREMENT = "nozzle_cam_nozzle_z_offsets"
VISION_JOB_CAMERA = "nozzle_cam"
VISION_JOB_PROFILE = "analysis"
VISION_JOB_LIGHTING = "NOZZLE_CAM_ANALYSIS_LIGHT"
BED_Y_JOB_LIGHTING = "NOZZLE_CAM_Y_FEATURE_LIGHT"
NOZZLE_Z_TOOL_LIGHTING = VISION_JOB_LIGHTING
VISION_LIGHTING_SETTLE_MS = 750
DEFAULT_NOZZLE_Z_BED_FEATURE_Z_MM = -0.1
DEFAULT_T0_Z_ENDSTOP = 293.75
DEFAULT_T1_Z_ENDSTOP = 293.65
NOZZLE_Z_MAX_PER_Z_X_FIT_RESIDUAL_PX = float(
    os.environ.get("VISION_NOZZLE_Z_MAX_PER_Z_X_FIT_RESIDUAL_PX", "1.25")
)
NOZZLE_Z_MAX_SCALE_FIT_RESIDUAL_PX_PER_MM = float(
    os.environ.get("VISION_NOZZLE_Z_MAX_SCALE_FIT_RESIDUAL_PX_PER_MM", "0.08")
)
NOZZLE_Z_MIN_SCALE_SLOPE_ABS = float(
    os.environ.get("VISION_NOZZLE_Z_MIN_SCALE_SLOPE_ABS", "0.05")
)
NOZZLE_Z_MAX_TOOL_SLOPE_RELATIVE_SPREAD = float(
    os.environ.get("VISION_NOZZLE_Z_MAX_TOOL_SLOPE_RELATIVE_SPREAD", "0.25")
)
BED_Y_ROIS_1080 = {
    "marked_line_tight": (690.0, 438.0, 300.0, 125.0),
    "marked_line_context": (690.0, 420.0, 570.0, 185.0),
}
BED_Y_FEATURE_MODES = ("gray_norm", "clahe", "grad_y", "grad_mag")
BED_Y_SEARCH_X_PAD_1080 = 95.0
BED_Y_SEARCH_UP_1080 = 330.0
BED_Y_SEARCH_DOWN_1080 = 120.0
VISION_HASH_PLACEHOLDER = "sha256:PLACEHOLDER"
HASHED_GCODE_TOKEN_RE = re.compile(r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+")


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
    phase: str | None = None
    target: str | None = None
    y_offset: float | None = None
    x_offset: float | None = None
    z_sample: float | None = None

    @property
    def tool_key(self) -> str:
        return self.tool.lower()

    def manifest_record(self) -> dict[str, Any]:
        record = {
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
        if self.phase is not None:
            record["phase"] = self.phase
        if self.target is not None:
            record["target"] = self.target
        if self.y_offset is not None:
            record["y_offset"] = round(self.y_offset, 4)
        if self.x_offset is not None:
            record["x_offset"] = round(self.x_offset, 4)
        if self.z_sample is not None:
            record["z_sample"] = round(self.z_sample, 4)
        return record


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
    measurement_parameters: dict[str, Any] | None = None
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


def parse_y_offsets(value: str) -> list[float]:
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not values:
        raise ValueError("Y offset list is empty")
    return values


def parse_float_list(value: str, label: str) -> list[float]:
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not values:
        raise ValueError(f"{label} list is empty")
    return values


def z_values_high_to_low(values: list[float]) -> list[float]:
    unique: dict[str, float] = {}
    for value in values:
        unique[dx_label(value)] = float(value)
    return sorted(unique.values(), reverse=True)


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


def generated_job_id_for_kind(kind: str, name: str, timestamp: datetime) -> str:
    timestamp_part = timestamp.strftime("%Y%m%dT%H%M%SZ")
    return f"{kind}_{timestamp_part}_{sanitize_name(name)}"


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


def build_bed_y_sweep_job_frames(
    *,
    x: float,
    y: float,
    z: float,
    y_offsets: list[float],
    feedrate: float,
    settle_ms: int,
    camera: str,
    profile: str,
) -> tuple[VisionJobFrame, ...]:
    frames: list[VisionJobFrame] = []
    for y_offset in y_offsets:
        frame_id = f"bed_y_{dx_label(y_offset)}"
        frames.append(
            VisionJobFrame(
                seq=len(frames),
                frame=frame_id,
                tool="T0",
                dx=0.0,
                x=x,
                y=y + y_offset,
                z=z,
                feedrate=feedrate,
                settle_ms=settle_ms,
                lighting=BED_Y_JOB_LIGHTING,
                camera=camera,
                profile=profile,
                phase="bed_y_sweep",
                target="bed_features",
                y_offset=y_offset,
            )
        )
    return tuple(frames)


def build_nozzle_z_sweep_job_frames(
    *,
    bed_y_x: float,
    bed_y_y: float,
    bed_y_z: float,
    tool_x: float,
    tool_y: float,
    y_offsets: list[float],
    x_offsets: list[float],
    z_values: list[float],
    feedrate: float,
    settle_ms: int,
    camera: str,
    profile: str,
) -> tuple[VisionJobFrame, ...]:
    frames: list[VisionJobFrame] = list(
        build_bed_y_sweep_job_frames(
            x=bed_y_x,
            y=bed_y_y,
            z=bed_y_z,
            y_offsets=y_offsets,
            feedrate=feedrate,
            settle_ms=settle_ms,
            camera=camera,
            profile=profile,
        )
    )
    for tool in ("T0", "T1"):
        for x_offset in x_offsets:
            for z_sample in z_values_high_to_low(z_values):
                frame_id = f"{tool.lower()}_x{dx_label(x_offset)}_z{dx_label(z_sample)}"
                frames.append(
                    VisionJobFrame(
                        seq=len(frames),
                        frame=frame_id,
                        tool=tool,
                        dx=x_offset,
                        x=tool_x + x_offset,
                        y=tool_y,
                        z=z_sample,
                        feedrate=feedrate,
                        settle_ms=settle_ms,
                        lighting=NOZZLE_Z_TOOL_LIGHTING,
                        camera=camera,
                        profile=profile,
                        phase="tool_xz_sweep",
                        target="nozzle_tip",
                        x_offset=x_offset,
                        z_sample=z_sample,
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


def build_bed_y_vision_job(
    *,
    name: str,
    job_root: Path,
    job_id: str | None,
    x: float,
    y: float,
    z: float,
    y_offsets: list[float],
    feedrate: float,
    settle_time: float,
    camera: str,
    profile: str,
    now: datetime | None = None,
) -> VisionJob:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    resolved_job_id = (
        sanitize_name(job_id)
        if job_id
        else generated_job_id_for_kind(BED_Y_JOB_KIND, name, timestamp)
    )
    job_dir = job_root / resolved_job_id
    frames = build_bed_y_sweep_job_frames(
        x=x,
        y=y,
        z=z,
        y_offsets=y_offsets,
        feedrate=feedrate,
        settle_ms=settle_time_to_ms(settle_time),
        camera=camera,
        profile=profile,
    )
    return VisionJob(
        job_id=resolved_job_id,
        kind=BED_Y_JOB_KIND,
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
        measurement_parameters={
            "base_x": round(x, 4),
            "base_y": round(y, 4),
            "z": round(z, 4),
            "y_offsets": [round(value, 4) for value in y_offsets],
            "lighting": BED_Y_JOB_LIGHTING,
        },
    )


def build_nozzle_z_vision_job(
    *,
    name: str,
    job_root: Path,
    job_id: str | None,
    bed_y_x: float,
    bed_y_y: float,
    bed_y_z: float,
    tool_x: float,
    tool_y: float,
    travel_z: float,
    y_offsets: list[float],
    x_offsets: list[float],
    z_values: list[float],
    bed_feature_z_mm: float,
    current_t0_z_endstop: float,
    current_t1_z_endstop: float,
    feedrate: float,
    settle_time: float,
    camera: str,
    profile: str,
    now: datetime | None = None,
) -> VisionJob:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    resolved_job_id = (
        sanitize_name(job_id)
        if job_id
        else generated_job_id_for_kind(NOZZLE_Z_JOB_KIND, name, timestamp)
    )
    job_dir = job_root / resolved_job_id
    z_capture_order = z_values_high_to_low(z_values)
    frames = build_nozzle_z_sweep_job_frames(
        bed_y_x=bed_y_x,
        bed_y_y=bed_y_y,
        bed_y_z=bed_y_z,
        tool_x=tool_x,
        tool_y=tool_y,
        y_offsets=y_offsets,
        x_offsets=x_offsets,
        z_values=z_capture_order,
        feedrate=feedrate,
        settle_ms=settle_time_to_ms(settle_time),
        camera=camera,
        profile=profile,
    )
    return VisionJob(
        job_id=resolved_job_id,
        kind=NOZZLE_Z_JOB_KIND,
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
        measurement_parameters={
            "bed_y_pose": {
                "x": round(bed_y_x, 4),
                "y": round(bed_y_y, 4),
                "z": round(bed_y_z, 4),
            },
            "tool_pose": {
                "x": round(tool_x, 4),
                "y": round(tool_y, 4),
                "travel_z": round(travel_z, 4),
            },
            "y_offsets": [round(value, 4) for value in y_offsets],
            "x_offsets": [round(value, 4) for value in x_offsets],
            "z_values": [round(value, 4) for value in z_values],
            "z_capture_order": [round(value, 4) for value in z_capture_order],
            "bed_feature_z_mm": round(bed_feature_z_mm, 4),
            "current_calib_yaml": {
                "tools": {
                    "t0": {"z_endstop": round(current_t0_z_endstop, 4)},
                    "t1": {"z_endstop": round(current_t1_z_endstop, 4)},
                }
            },
            "lighting": {
                "bed_y_sweep": {"macro": BED_Y_JOB_LIGHTING},
                "tool_xz_sweep": {"macro": NOZZLE_Z_TOOL_LIGHTING},
            },
        },
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
        "",
    ]
    active_tool: str | None = None
    active_lighting: str | None = None
    active_profile = job.profile
    previous_tool_frame: VisionJobFrame | None = None
    travel_z = None
    if job.kind == NOZZLE_Z_JOB_KIND:
        parameters = job.measurement_parameters or {}
        tool_pose = parameters.get("tool_pose") or {}
        try:
            travel_z = float(tool_pose.get("travel_z"))
        except (TypeError, ValueError):
            travel_z = None
    for frame in job.frames:
        if frame.profile != active_profile:
            lines.append(
                f"VISION_PROFILE CAMERA={frame.camera} PROFILE={frame.profile}"
            )
            active_profile = frame.profile
        if frame.lighting != active_lighting:
            lines.append(frame.lighting)
            lines.append(f"G4 P{VISION_LIGHTING_SETTLE_MS}")
            lines.append("")
            active_lighting = frame.lighting
        if frame.tool != active_tool:
            lines.append(frame.tool)
            active_tool = frame.tool
        if (
            job.kind == NOZZLE_Z_JOB_KIND
            and frame.phase == "tool_xz_sweep"
            and previous_tool_frame is not None
            and (
                frame.tool != previous_tool_frame.tool
                or abs(frame.x - previous_tool_frame.x) > 1.0e-6
                or abs(frame.y - previous_tool_frame.y) > 1.0e-6
            )
            and travel_z is not None
        ):
            lines.extend(
                [
                    f"G1 Z{gcode_float(travel_z)} F{frame.feedrate:.0f}",
                    "M400",
                    (
                        f"G1 X{gcode_float(frame.x)} Y{gcode_float(frame.y)} "
                        f"Z{gcode_float(travel_z)} F{frame.feedrate:.0f}"
                    ),
                    "M400",
                ]
            )
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
        if frame.phase == "tool_xz_sweep":
            previous_tool_frame = frame
    lines.append(f"VISION_JOB_END JOB={job.job_id} EXPECTED_FRAMES={len(job.frames)}")
    return "\n".join(lines) + "\n"


def build_manifest(job: VisionJob) -> dict[str, Any]:
    manifest = {
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
    if job.measurement_parameters is not None:
        manifest["measurement_parameters"] = job.measurement_parameters
    return manifest


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


def prepare_bed_y_sweep_job(args: argparse.Namespace) -> dict[str, Any]:
    job = build_bed_y_vision_job(
        name=args.name,
        job_root=Path(args.job_root),
        job_id=args.job_id,
        x=float(args.x),
        y=float(args.y),
        z=float(args.z),
        y_offsets=parse_y_offsets(args.y_offsets),
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


def prepare_nozzle_z_sweep_job(args: argparse.Namespace) -> dict[str, Any]:
    job = build_nozzle_z_vision_job(
        name=args.name,
        job_root=Path(args.job_root),
        job_id=args.job_id,
        bed_y_x=float(args.bed_y_x),
        bed_y_y=float(args.bed_y_y),
        bed_y_z=float(args.bed_y_z),
        tool_x=float(args.tool_x),
        tool_y=float(args.tool_y),
        travel_z=float(args.travel_z),
        y_offsets=parse_y_offsets(args.y_offsets),
        x_offsets=parse_float_list(args.x_offsets, "X offset"),
        z_values=parse_float_list(args.z_values, "Z sample"),
        bed_feature_z_mm=float(args.bed_feature_z_mm),
        current_t0_z_endstop=float(args.current_t0_z_endstop),
        current_t1_z_endstop=float(args.current_t1_z_endstop),
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


def load_bed_y_job_frames_for_analysis(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job_dir = manifest_path.parent
    frames: list[dict[str, Any]] = []
    for frame in manifest["frames"]:
        if frame.get("phase") != "bed_y_sweep":
            continue
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
                "tool": str(frame.get("tool") or "T0").lower(),
                "macro": str(frame.get("tool") or "T0").upper(),
                "phase": frame.get("phase"),
                "target": frame.get("target"),
                "y_offset": float(frame["y_offset"]),
                "prefix": frame_id,
                "target_gcode_position": {
                    "x": float(pose["x"]),
                    "y": float(pose["y"]),
                    "z": float(pose["z"]),
                },
                "lighting": frame.get("lighting"),
                "capture": capture,
                "image_path": str(image_path),
                "metadata_path": str(metadata_path),
                "image_url": safe_vision_url(image_path),
                "metadata_url": safe_vision_url(metadata_path),
            }
        )
    return frames


def load_nozzle_z_job_frames_for_analysis(manifest_path: Path) -> list[dict[str, Any]]:
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
        record = {
            "tool": str(frame.get("tool") or "T0").lower(),
            "macro": str(frame.get("tool") or "T0").upper(),
            "dx": float(frame.get("dx", 0.0)),
            "dx_label": dx_label(float(frame.get("dx", 0.0))),
            "phase": frame.get("phase"),
            "target": frame.get("target"),
            "prefix": frame_id,
            "target_gcode_position": {
                "x": float(pose["x"]),
                "y": float(pose["y"]),
                "z": float(pose["z"]),
            },
            "lighting": frame.get("lighting"),
            "camera": frame.get("camera"),
            "profile": frame.get("profile"),
            "capture": capture,
            "image_path": str(image_path),
            "metadata_path": str(metadata_path),
            "image_url": safe_vision_url(image_path),
            "metadata_url": safe_vision_url(metadata_path),
        }
        if frame.get("y_offset") is not None:
            record["y_offset"] = float(frame["y_offset"])
        if frame.get("x_offset") is not None:
            record["x_offset"] = float(frame["x_offset"])
        if frame.get("z_sample") is not None:
            record["z_sample"] = float(frame["z_sample"])
        frames.append(record)
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


def verify_prepared_job_integrity(
    job_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
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
            if (
                value < float(axis_min[index]) - 1e-6
                or value > float(axis_max[index]) + 1e-6
            ):
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
            raise RuntimeError(
                f"refusing to overwrite existing virtual SD file: {target}"
            )
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
        "gcode_path": str(
            job_dir / str(manifest.get("gcode_file") or "acquisition.gcode")
        ),
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


def run_bed_y_acquisition_job(args: argparse.Namespace) -> dict[str, Any]:
    summary = prepare_bed_y_sweep_job(args)
    start_args = argparse.Namespace(**vars(args))
    start_args.start_prepared_job = summary["job_id"]
    return start_prepared_job(start_args)


def run_nozzle_z_acquisition_job(args: argparse.Namespace) -> dict[str, Any]:
    summary = prepare_nozzle_z_sweep_job(args)
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


def reset_interrupted_analysis(job_dir: Path, paths: dict[str, Path]) -> None:
    for key in ("result", "facts"):
        if paths[key].exists():
            raise RuntimeError(
                f"refusing to retry interrupted analysis because {paths[key]} exists"
            )
    analysis_dir = paths["analysis_dir"]
    if analysis_dir.exists():
        shutil.rmtree(analysis_dir)
    state = read_json(job_dir / "state.json")
    now = datetime.now(timezone.utc).isoformat()
    state.update(
        {
            "state": "acquired",
            "analysis_retry_at_utc": now,
            "updated_at_utc": now,
        }
    )
    state.pop("analysis_result_path", None)
    state.pop("analysis_result_url", None)
    state.pop("analysis_facts_path", None)
    state.pop("analysis_facts_url", None)
    atomic_write_json(job_dir / "state.json", state)
    append_job_event(
        job_dir,
        "analysis_retry",
        {"state": "acquired", "reason": "previous analysis was interrupted"},
    )


def mark_job_analysing(job_dir: Path) -> dict[str, Any]:
    state = read_json(job_dir / "state.json")
    state_name = state.get("state")
    if state_name not in {"acquired", "completed", "failed"}:
        raise RuntimeError(
            f"vision job {state.get('job_id')} is {state_name!r}, "
            "expected 'acquired', 'completed', or 'failed' before analysis"
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
        "red_marker_delta_t1_minus_t0": analysis.get("red_marker_delta_t1_minus_t0"),
        "quality": {
            "cross_match": analysis.get("cross_match"),
            "red_marker_fits": analysis.get("red_marker_fits"),
            "red_axis_vector_px_per_mm": analysis.get("red_axis_vector_px_per_mm"),
            "red_axis_px_per_mm": analysis.get("red_axis_px_per_mm"),
            "red_axis_angle_deg": analysis.get("red_axis_angle_deg"),
        },
        "hard_failures": analysis.get("hard_failures") or [],
    }


def round_float(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def round_vector(vector: Any, digits: int = 4) -> list[float] | None:
    if vector is None:
        return None
    return [round(float(value), digits) for value in vector]


def median_float(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def subpixel_peak_offset(
    response: Any, max_loc: tuple[int, int]
) -> tuple[float, float]:
    x, y = max_loc
    height, width = response.shape[:2]

    def axis_offset(v0: float, v_minus: float, v_plus: float) -> float:
        denominator = v_minus - 2.0 * v0 + v_plus
        if abs(denominator) < 1.0e-9:
            return 0.0
        offset = 0.5 * (v_minus - v_plus) / denominator
        return max(-1.0, min(1.0, float(offset)))

    center = float(response[y, x])
    dx = 0.0
    dy = 0.0
    if 0 < x < width - 1:
        dx = axis_offset(center, float(response[y, x - 1]), float(response[y, x + 1]))
    if 0 < y < height - 1:
        dy = axis_offset(center, float(response[y - 1, x]), float(response[y + 1, x]))
    return dx, dy


def bed_y_preprocess_image(image: Any, mode: str) -> Any:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if mode == "gray_norm":
        feature = gray.astype("float32")
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        if mode == "clahe":
            feature = clahe.astype("float32")
        elif mode == "grad_y":
            feature = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
        elif mode == "grad_mag":
            grad_x = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
            feature = cv2.magnitude(grad_x, grad_y)
        else:
            raise ValueError(f"unknown bed-Y feature mode: {mode}")
    feature = feature.astype("float32")
    std = float(feature.std())
    if std <= 1.0e-6:
        return np.zeros(feature.shape, dtype="float32")
    return (feature - float(feature.mean())) / std


def bed_y_search_rect(
    roi: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int]:
    x, y, w, h = roi
    pad_x = BED_Y_SEARCH_X_PAD_1080 * width / RED_BASE_WIDTH
    search_up = BED_Y_SEARCH_UP_1080 * height / RED_BASE_HEIGHT
    search_down = BED_Y_SEARCH_DOWN_1080 * height / RED_BASE_HEIGHT
    return clamp_rect(
        x - pad_x,
        y - search_up,
        w + 2.0 * pad_x,
        h + search_up + search_down,
        width,
        height,
    )


def fit_bed_y_displacements(matches: list[dict[str, Any]]) -> dict[str, Any]:
    import numpy as np

    usable = [match for match in matches if match.get("accepted")]
    if len(usable) < 3:
        return {"ok": False, "rejection_reason": "need at least three usable frames"}
    offsets = np.array([float(match["y_offset"]) for match in usable], dtype=float)
    if float(offsets.max() - offsets.min()) <= 1.0e-9:
        return {"ok": False, "rejection_reason": "Y offsets do not vary"}
    observed = np.array(
        [[float(match["dx"]), float(match["dy"])] for match in usable],
        dtype=float,
    )
    weights = np.array(
        [max(0.01, float(match.get("correlation") or 0.01)) for match in usable],
        dtype=float,
    )
    design = np.column_stack((offsets, np.ones(len(offsets))))
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_observed = observed * np.sqrt(weights)[:, None]
    solution = np.linalg.lstsq(weighted_design, weighted_observed, rcond=None)[0]
    vector = solution[0]
    intercept = solution[1]
    predicted = design @ solution
    residual_vectors = observed - predicted
    residual_distances = np.linalg.norm(residual_vectors, axis=1)
    rms = math.sqrt(float(np.mean(residual_distances * residual_distances)))
    correlations = [float(match.get("correlation") or 0.0) for match in usable]
    return {
        "ok": True,
        "usable_frame_count": len(usable),
        "axis_vector_px_per_mm": [float(vector[0]), float(vector[1])],
        "intercept_px": [float(intercept[0]), float(intercept[1])],
        "residual_rms_px": rms,
        "residuals": [
            {
                "frame": match["frame"],
                "y_offset": round(float(match["y_offset"]), 4),
                "observed_dx": round(float(match["dx"]), 4),
                "observed_dy": round(float(match["dy"]), 4),
                "predicted_dx": round(float(predicted[index, 0]), 4),
                "predicted_dy": round(float(predicted[index, 1]), 4),
                "residual_px": round(float(residual_distances[index]), 4),
                "correlation": round(float(match.get("correlation") or 0.0), 4),
            }
            for index, match in enumerate(usable)
        ],
        "correlation_min": min(correlations) if correlations else None,
        "correlation_median": median_float(correlations),
    }


def match_bed_y_roi_mode(
    *,
    frames: list[dict[str, Any]],
    images: dict[str, Any],
    reference_frame: dict[str, Any],
    roi_name: str,
    roi_1080: tuple[float, float, float, float],
    mode: str,
) -> dict[str, Any]:
    import cv2

    reference_image = images[reference_frame["prefix"]]
    height, width = reference_image.shape[:2]
    roi = scale_rect_1080(roi_1080, width, height)
    search_rect = bed_y_search_rect(roi, width, height)
    features = {
        frame["prefix"]: bed_y_preprocess_image(images[frame["prefix"]], mode)
        for frame in frames
        if frame["prefix"] in images
    }
    rx, ry, rw, rh = roi
    sx, sy, sw, sh = search_rect
    reference_feature = features[reference_frame["prefix"]]
    template = reference_feature[ry : ry + rh, rx : rx + rw]
    texture_std = float(template.std())
    matches: list[dict[str, Any]] = []
    if texture_std <= 0.015:
        return {
            "roi_name": roi_name,
            "feature_mode": mode,
            "accepted": False,
            "rejection_reason": (
                f"reference ROI has too little texture for template matching "
                f"(std={texture_std:.5f})"
            ),
            "roi": list(roi),
            "search_roi": list(search_rect),
            "matches": [],
            "score": 1.0e9,
        }

    for frame in frames:
        prefix = frame["prefix"]
        if prefix not in features:
            continue
        feature = features[prefix]
        if prefix == reference_frame["prefix"]:
            matches.append(
                {
                    "frame": prefix,
                    "y_offset": float(frame["y_offset"]),
                    "dx": 0.0,
                    "dy": 0.0,
                    "correlation": 1.0,
                    "roi": list(roi),
                    "search_roi": list(search_rect),
                    "match_roi": list(roi),
                    "accepted": True,
                }
            )
            continue
        search = feature[sy : sy + sh, sx : sx + sw]
        if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
            matches.append(
                {
                    "frame": prefix,
                    "y_offset": float(frame["y_offset"]),
                    "accepted": False,
                    "rejection_reason": "search window is smaller than template",
                }
            )
            continue
        response = cv2.matchTemplate(
            search.astype("float32"),
            template.astype("float32"),
            cv2.TM_CCOEFF_NORMED,
        )
        _min_value, max_value, _min_loc, max_loc = cv2.minMaxLoc(response)
        sub_dx, sub_dy = subpixel_peak_offset(response, max_loc)
        matched_x = float(sx + max_loc[0]) + sub_dx
        matched_y = float(sy + max_loc[1]) + sub_dy
        dx = matched_x - float(rx)
        dy = matched_y - float(ry)
        matches.append(
            {
                "frame": prefix,
                "y_offset": float(frame["y_offset"]),
                "dx": dx,
                "dy": dy,
                "correlation": float(max_value),
                "roi": list(roi),
                "search_roi": list(search_rect),
                "match_roi": [
                    round(matched_x, 3),
                    round(matched_y, 3),
                    rw,
                    rh,
                ],
                "accepted": True,
            }
        )

    fit = fit_bed_y_displacements(matches)
    if not fit.get("ok"):
        return {
            "roi_name": roi_name,
            "feature_mode": mode,
            "accepted": False,
            "rejection_reason": fit.get("rejection_reason", "fit failed"),
            "roi": list(roi),
            "search_roi": list(search_rect),
            "matches": matches,
            "fit": fit,
            "texture_std": round(texture_std, 6),
            "score": 1.0e9,
        }
    vector = fit["axis_vector_px_per_mm"]
    scale = math.hypot(float(vector[0]), float(vector[1]))
    angle = (
        math.degrees(math.atan2(float(vector[1]), float(vector[0]))) if scale else None
    )
    corr_min = float(fit.get("correlation_min") or 0.0)
    corr_threshold = 0.72 if mode.startswith("grad") else 0.82
    hard_failures: list[str] = []
    if fit["usable_frame_count"] < 4:
        hard_failures.append("fewer than four usable Y sweep frames")
    if corr_min < corr_threshold:
        hard_failures.append(
            f"correlation_min {corr_min:.3f} below {corr_threshold:.3f}"
        )
    if float(fit["residual_rms_px"]) > 1.2:
        hard_failures.append(
            f"residual RMS {float(fit['residual_rms_px']):.3f}px too high"
        )
    if not (7.0 <= scale <= 14.5):
        hard_failures.append(f"scale {scale:.3f}px/mm outside expected local range")
    if abs(float(vector[0])) > 1.5:
        hard_failures.append(f"cross-axis drift {float(vector[0]):.3f}px/mm too high")
    if float(vector[1]) >= 0:
        hard_failures.append("image Y component is not negative")
    score = (
        float(fit["residual_rms_px"])
        + 0.2 * abs(float(vector[0]))
        + max(0.0, corr_threshold - corr_min) * 4.0
        + (0.03 if mode != "grad_y" else 0.0)
        + (0.04 if roi_name != "marked_line_tight" else 0.0)
    )
    return {
        "roi_name": roi_name,
        "feature_mode": mode,
        "accepted": not hard_failures,
        "rejection_reason": "; ".join(hard_failures),
        "hard_failures": hard_failures,
        "roi": list(roi),
        "search_roi": list(search_rect),
        "matches": matches,
        "fit": fit,
        "texture_std": round(texture_std, 6),
        "bed_y_axis_vector_px_per_mm": round_vector(vector),
        "bed_y_scale_px_per_mm": round(scale, 4),
        "bed_y_mm_per_px": round(1.0 / scale, 6) if scale > 0 else None,
        "bed_y_axis_angle_deg": round(angle, 4) if angle is not None else None,
        "bed_y_cross_axis_px_per_mm": round(float(vector[0]), 4),
        "bed_y_fit_residual_rms_px": round(float(fit["residual_rms_px"]), 4),
        "bed_y_correlation_min": round(corr_min, 4),
        "bed_y_correlation_median": round_float(fit.get("correlation_median"), 4),
        "score": round(score, 6),
    }


def bed_y_parallax_spread(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    accepted_by_roi: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not candidate.get("accepted"):
            continue
        roi_name = str(candidate.get("roi_name"))
        current = accepted_by_roi.get(roi_name)
        if current is None or float(candidate.get("score", 1.0e9)) < float(
            current.get("score", 1.0e9)
        ):
            accepted_by_roi[roi_name] = candidate
    selected = list(accepted_by_roi.values())
    vectors = [
        tuple(float(value) for value in candidate["bed_y_axis_vector_px_per_mm"])
        for candidate in selected
        if candidate.get("bed_y_axis_vector_px_per_mm")
    ]
    scales = [
        float(candidate["bed_y_scale_px_per_mm"])
        for candidate in selected
        if candidate.get("bed_y_scale_px_per_mm") is not None
    ]
    angles = [
        float(candidate["bed_y_axis_angle_deg"])
        for candidate in selected
        if candidate.get("bed_y_axis_angle_deg") is not None
    ]
    vector_spread = 0.0
    for index, first in enumerate(vectors):
        for second in vectors[index + 1 :]:
            vector_spread = max(vector_spread, point_distance(first, second))
    scale_spread = max(scales) - min(scales) if len(scales) >= 2 else 0.0
    scale_median = median_float(scales) or 0.0
    angle_spread = max(angles) - min(angles) if len(angles) >= 2 else 0.0
    return {
        "accepted_roi_count": len(selected),
        "accepted_rois": [candidate.get("roi_name") for candidate in selected],
        "axis_vector_spread_px_per_mm": round(vector_spread, 4),
        "scale_spread_px_per_mm": round(scale_spread, 4),
        "scale_spread_percent": (
            round(100.0 * scale_spread / scale_median, 4) if scale_median > 0 else None
        ),
        "angle_spread_deg": round(angle_spread, 4),
        "meaning": "local perspective variation between accepted bed-feature ROIs; not a full Z-height solve",
    }


def annotate_bed_y_frame(
    image: Any, frame: dict[str, Any], selected: dict[str, Any] | None
) -> Any:
    import cv2

    overlay = image.copy()
    match_by_frame = {
        match.get("frame"): match for match in (selected or {}).get("matches", [])
    }
    match = match_by_frame.get(frame["prefix"])
    if match:
        for key, color in (
            ("search_roi", (80, 80, 80)),
            ("roi", (255, 190, 0)),
            ("match_roi", (0, 255, 0)),
        ):
            rect = match.get(key)
            if rect:
                x, y, w, h = [int(round(float(value))) for value in rect]
                cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
    label = (
        f"bed Y {float(frame['y_offset']):.3g}mm "
        f"{(selected or {}).get('roi_name', 'no ROI')} "
        f"{(selected or {}).get('feature_mode', 'no mode')}"
    )
    if match and match.get("correlation") is not None:
        label += f" corr={float(match['correlation']):.3f}"
    cv2.rectangle(overlay, (0, 0), (900, 48), (0, 0, 0), -1)
    cv2.putText(
        overlay,
        label,
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return overlay


def crop_for_bed_y_contact_tile(image: Any, frame: dict[str, Any]) -> Any:
    height, width = image.shape[:2]
    boxes = []
    for key in ("bed_y_match_roi", "bed_y_reference_roi", "bed_y_search_roi"):
        if frame.get(key):
            boxes.append(frame[key])
    if not boxes:
        boxes = [scale_rect_1080(BED_Y_ROIS_1080["marked_line_context"], width, height)]
    left = min(float(box[0]) for box in boxes)
    top = min(float(box[1]) for box in boxes)
    right = max(float(box[0]) + float(box[2]) for box in boxes)
    bottom = max(float(box[1]) + float(box[3]) for box in boxes)
    pad_x = 120.0 * width / RED_BASE_WIDTH
    pad_y = 85.0 * height / RED_BASE_HEIGHT
    x, y, w, h = clamp_rect(
        left - pad_x,
        top - pad_y,
        (right - left) + 2.0 * pad_x,
        (bottom - top) + 2.0 * pad_y,
        width,
        height,
    )
    return image[y : y + h, x : x + w]


def write_bed_y_contact_sheet(
    frames: list[dict[str, Any]],
    analysis: dict[str, Any],
    contact_sheet_path: Path,
    *,
    use_overlays: bool,
) -> None:
    import cv2
    import numpy as np

    tile_w, tile_h = 430, 300
    cols = max(1, len(frames))
    summary_h = 285
    sheet = np.full((tile_h + summary_h, cols * tile_w, 3), 255, dtype=np.uint8)
    for col, frame in enumerate(frames):
        path = frame.get("overlay_path") if use_overlays else frame.get("image_path")
        image = cv2.imread(str(path)) if path else None
        if image is None and frame.get("image_path"):
            image = cv2.imread(frame["image_path"])
        if image is None:
            continue
        crop = crop_for_bed_y_contact_tile(image, frame)
        tile = letterbox(crop, tile_w, tile_h)
        x = col * tile_w
        sheet[0:tile_h, x : x + tile_w] = tile
        cv2.rectangle(sheet, (x, 0), (x + tile_w - 1, tile_h - 1), (80, 80, 80), 2)
        cv2.putText(
            sheet,
            f"Y+{float(frame['y_offset']):.3g}mm",
            (x + 16, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

    summary_lines = [
        f"Nozzle camera bed Y sweep: {analysis.get('run_name')}",
        f"report: {public_url(contact_sheet_path)}",
        "negative image Y means the feature moves upward in the camera image as printer Y increases",
    ]
    if analysis.get("ok"):
        vector = analysis.get("bed_y_axis_vector_px_per_mm") or [None, None]
        summary_lines.extend(
            [
                "selected: "
                f"roi={analysis.get('selected_roi')} mode={analysis.get('feature_mode')}",
                "bed Y image vector: "
                f"dx={vector[0]}px/mm dy={vector[1]}px/mm "
                f"scale={analysis.get('bed_y_scale_px_per_mm')}px/mm "
                f"angle={analysis.get('bed_y_axis_angle_deg')}deg",
                "quality: "
                f"rms={analysis.get('bed_y_fit_residual_rms_px')}px "
                f"corr_min={analysis.get('bed_y_correlation_min')} "
                f"corr_median={analysis.get('bed_y_correlation_median')}",
            ]
        )
    else:
        failures = analysis.get("hard_failures") or [analysis.get("message")]
        summary_lines.append(
            f"STATUS: FAILED; {'; '.join(str(item) for item in failures[:3])}"
        )
    spread = analysis.get("bed_y_parallax_spread") or {}
    summary_lines.append(
        "local parallax spread: "
        f"vectors={spread.get('axis_vector_spread_px_per_mm')}px/mm "
        f"scale={spread.get('scale_spread_px_per_mm')}px/mm"
    )
    cv2.rectangle(
        sheet, (0, tile_h), (sheet.shape[1], sheet.shape[0]), (238, 238, 238), -1
    )
    draw_text_lines(sheet, summary_lines, (24, tile_h + 36), line_height=27, scale=0.58)
    cv2.imwrite(str(contact_sheet_path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def analyze_bed_y_sweep_frames(
    frames: list[dict[str, Any]], run_dir: Path, overlay_dir: Path | None = None
) -> dict[str, Any]:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on Pi package install
        return {
            "ok": False,
            "proxy_only": True,
            "measurement": BED_Y_MEASUREMENT,
            "error": f"OpenCV import failed: {exc}",
            "hard_failures": [f"OpenCV import failed: {exc}"],
        }

    hard_failures: list[str] = []
    images: dict[str, Any] = {}
    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            frame["analysis_error"] = f"Could not read {frame['image_path']}"
            hard_failures.append(frame["analysis_error"])
            continue
        height, width = image.shape[:2]
        frame["image_width"] = width
        frame["image_height"] = height
        images[frame["prefix"]] = image
    analysis_frames = [frame for frame in frames if frame["prefix"] in images]
    if len(analysis_frames) < 3:
        message = "Bed Y sweep needs at least three readable frames."
        hard_failures.append(message)
        selected = None
        candidates: list[dict[str, Any]] = []
    else:
        reference_frame = min(
            analysis_frames, key=lambda frame: abs(float(frame.get("y_offset", 0.0)))
        )
        candidates = []
        for roi_name, roi_1080 in BED_Y_ROIS_1080.items():
            for mode in BED_Y_FEATURE_MODES:
                candidates.append(
                    match_bed_y_roi_mode(
                        frames=analysis_frames,
                        images=images,
                        reference_frame=reference_frame,
                        roi_name=roi_name,
                        roi_1080=roi_1080,
                        mode=mode,
                    )
                )
        accepted_candidates = [
            candidate for candidate in candidates if candidate.get("accepted")
        ]
        selected = min(
            accepted_candidates or candidates,
            key=lambda candidate: float(candidate.get("score", 1.0e9)),
        )
        if not accepted_candidates:
            hard_failures.append(
                selected.get("rejection_reason") or "no accepted bed Y template fit"
            )

    match_by_frame = {
        match.get("frame"): match for match in (selected or {}).get("matches", [])
    }
    for frame in frames:
        image = images.get(frame["prefix"])
        if image is None:
            continue
        match = match_by_frame.get(frame["prefix"])
        if match:
            if match.get("roi"):
                frame["bed_y_reference_roi"] = match["roi"]
            if match.get("search_roi"):
                frame["bed_y_search_roi"] = match["search_roi"]
            if match.get("match_roi"):
                frame["bed_y_match_roi"] = match["match_roi"]
        overlay = annotate_bed_y_frame(image, frame, selected)
        overlay_root = overlay_dir or run_dir
        overlay_root.mkdir(parents=True, exist_ok=True)
        overlay_path = overlay_root / f"{frame['prefix']}_overlay.jpg"
        cv2.imwrite(str(overlay_path), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        frame["overlay_path"] = str(overlay_path)
        frame["overlay_url"] = safe_vision_url(overlay_path)

    spread = bed_y_parallax_spread(candidates)
    ok = bool(selected and selected.get("accepted"))
    message = (
        "Bed Y feature motion accepted."
        if ok
        else "Bed Y feature motion rejected: "
        + "; ".join(str(item) for item in hard_failures)
    )
    return {
        "ok": ok,
        "proxy_only": not ok,
        "measurement": BED_Y_MEASUREMENT,
        "hard_failures": hard_failures,
        "selected_roi": selected.get("roi_name") if selected else None,
        "feature_mode": selected.get("feature_mode") if selected else None,
        "selected_result": selected,
        "roi_results": candidates,
        "accepted_roi_results": [
            candidate for candidate in candidates if candidate.get("accepted")
        ],
        "bed_y_axis_vector_px_per_mm": (
            selected.get("bed_y_axis_vector_px_per_mm") if selected and ok else None
        ),
        "bed_y_scale_px_per_mm": (
            selected.get("bed_y_scale_px_per_mm") if selected and ok else None
        ),
        "bed_y_mm_per_px": selected.get("bed_y_mm_per_px") if selected and ok else None,
        "bed_y_axis_angle_deg": (
            selected.get("bed_y_axis_angle_deg") if selected and ok else None
        ),
        "bed_y_cross_axis_px_per_mm": (
            selected.get("bed_y_cross_axis_px_per_mm") if selected and ok else None
        ),
        "bed_y_fit_residual_rms_px": (
            selected.get("bed_y_fit_residual_rms_px") if selected else None
        ),
        "bed_y_correlation_min": (
            selected.get("bed_y_correlation_min") if selected else None
        ),
        "bed_y_correlation_median": (
            selected.get("bed_y_correlation_median") if selected else None
        ),
        "bed_y_parallax_spread": spread,
        "lighting": frames[0].get("lighting") if frames else BED_Y_JOB_LIGHTING,
        "reference_frame": (
            reference_frame["prefix"] if "reference_frame" in locals() else None
        ),
        "reference_y_offset": (
            round(float(reference_frame["y_offset"]), 4)
            if "reference_frame" in locals()
            else None
        ),
        "message": message,
    }


def build_bed_y_motion_facts(
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
        "measurement": BED_Y_MEASUREMENT,
        "accepted": accepted,
        "ok": accepted,
        "source_result": result_path.name,
        "bed_y_axis_vector_px_per_mm": analysis.get("bed_y_axis_vector_px_per_mm"),
        "bed_y_scale_px_per_mm": analysis.get("bed_y_scale_px_per_mm"),
        "bed_y_mm_per_px": analysis.get("bed_y_mm_per_px"),
        "bed_y_axis_angle_deg": analysis.get("bed_y_axis_angle_deg"),
        "bed_y_cross_axis_px_per_mm": analysis.get("bed_y_cross_axis_px_per_mm"),
        "bed_y_fit_residual_rms_px": analysis.get("bed_y_fit_residual_rms_px"),
        "bed_y_correlation_min": analysis.get("bed_y_correlation_min"),
        "bed_y_correlation_median": analysis.get("bed_y_correlation_median"),
        "bed_y_parallax_spread": analysis.get("bed_y_parallax_spread"),
        "lighting": analysis.get("lighting"),
        "quality": {
            "selected_roi": analysis.get("selected_roi"),
            "feature_mode": analysis.get("feature_mode"),
            "reference_frame": analysis.get("reference_frame"),
            "reference_y_offset": analysis.get("reference_y_offset"),
            "fit_residual_rms_px": analysis.get("bed_y_fit_residual_rms_px"),
            "correlation_min": analysis.get("bed_y_correlation_min"),
            "correlation_median": analysis.get("bed_y_correlation_median"),
        },
        "hard_failures": analysis.get("hard_failures") or [],
    }


def linear_fit_xy(xs: list[float], ys: list[float]) -> dict[str, Any]:
    if len(xs) != len(ys) or len(xs) < 2:
        return {"ok": False, "rejection_reason": "need at least two samples"}
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((value - mean_x) ** 2 for value in xs)
    if denom <= 0:
        return {"ok": False, "rejection_reason": "sample x values do not vary"}
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    return {
        "ok": True,
        "count": len(xs),
        "slope": slope,
        "intercept": intercept,
        "residual_rms": rms,
        "residuals": residuals,
    }


def scaled_nozzle_z_pixels_1080(value: float, width: int, height: int) -> int:
    scale = (width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT) / 2.0
    return max(1, int(round(float(value) * scale)))


def nozzle_z_preprocess_image(image: Any) -> Any:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    feature = clahe.astype("float32")
    std = float(feature.std())
    if std <= 1.0e-6:
        return np.zeros(feature.shape, dtype="float32")
    return (feature - float(feature.mean())) / std


def match_nozzle_z_roi_pair(
    *,
    source_feature: Any,
    target_feature: Any,
    source_roi: tuple[int, int, int, int],
    predicted_delta: tuple[float, float],
    search_pad_px: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    import cv2

    x, y, w, h = source_roi
    template = source_feature[y : y + h, x : x + w]
    if template.shape[0] != h or template.shape[1] != w:
        return {
            "accepted": False,
            "rejection_reason": "template ROI is outside the source image",
            "roi": list(source_roi),
        }
    texture_std = float(template.std())
    if texture_std <= 0.015:
        return {
            "accepted": False,
            "rejection_reason": (
                "template ROI has too little texture for cross-alignment "
                f"(std={texture_std:.5f})"
            ),
            "roi": list(source_roi),
        }

    predicted_x = float(x) + float(predicted_delta[0])
    predicted_y = float(y) + float(predicted_delta[1])
    pad = max(1, int(round(search_pad_px)))
    search_roi = clamp_rect(
        predicted_x - pad,
        predicted_y - pad,
        float(w + 2 * pad),
        float(h + 2 * pad),
        width,
        height,
    )
    sx, sy, sw, sh = search_roi
    search = target_feature[sy : sy + sh, sx : sx + sw]
    if search.shape[0] < h or search.shape[1] < w:
        return {
            "accepted": False,
            "rejection_reason": "search window is smaller than template",
            "roi": list(source_roi),
            "search_roi": list(search_roi),
        }

    response = cv2.matchTemplate(
        search.astype("float32"),
        template.astype("float32"),
        cv2.TM_CCOEFF_NORMED,
    )
    _min_value, max_value, _min_loc, max_loc = cv2.minMaxLoc(response)
    sub_dx, sub_dy = subpixel_peak_offset(response, max_loc)
    matched_x = float(sx + max_loc[0]) + sub_dx
    matched_y = float(sy + max_loc[1]) + sub_dy
    dx = matched_x - float(x)
    dy = matched_y - float(y)
    return {
        "accepted": True,
        "dx": dx,
        "dy": dy,
        "correlation": float(max_value),
        "roi": list(source_roi),
        "search_roi": list(search_roi),
        "match_roi": [round(matched_x, 3), round(matched_y, 3), w, h],
        "matched_origin_px": [matched_x, matched_y],
        "predicted_origin_px": [round(predicted_x, 3), round(predicted_y, 3)],
        "texture_std": round(texture_std, 5),
    }


def track_nozzle_z_roi_group(
    *,
    group_frames: list[dict[str, Any]],
    features: dict[str, Any],
    width: int,
    height: int,
) -> dict[str, Any]:
    ordered = sorted(
        group_frames,
        key=lambda frame: float(frame.get("x_offset", frame.get("dx", 0.0))),
    )
    tool = str(ordered[0].get("tool", "")).lower() if ordered else ""
    z_sample = float(ordered[0]["z_sample"]) if ordered else None
    coarse_roi = scale_rect_1080(NOZZLE_Z_COARSE_ROI_1080, width, height)
    refined_roi = scale_rect_1080(NOZZLE_Z_REFINED_ROI_1080, width, height)
    coarse_pad = scaled_nozzle_z_pixels_1080(
        NOZZLE_Z_COARSE_SEARCH_PAD_1080, width, height
    )
    refined_pad = scaled_nozzle_z_pixels_1080(
        NOZZLE_Z_REFINED_SEARCH_PAD_1080, width, height
    )
    failures: list[str] = []
    detections: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    pairwise: list[dict[str, Any]] = []

    if len(ordered) < 2:
        reason = "need at least two X samples at the same Z"
        return {
            "ok": False,
            "tool": tool,
            "z_sample": z_sample,
            "rejection_reason": reason,
            "hard_failures": [reason],
            "samples": [],
            "diagnostic_samples": [],
            "detections": detections,
            "pairwise": pairwise,
            "fit": {"ok": False, "rejection_reason": reason},
        }

    current_coarse_roi = coarse_roi
    current_refined_roi = refined_roi
    first = ordered[0]
    rx, ry, rw, rh = current_refined_roi
    first_point = [float(rx + rw / 2.0), float(ry + rh / 2.0)]
    samples.append(
        {
            "tool": tool,
            "x_offset": float(first.get("x_offset", first.get("dx", 0.0))),
            "z_sample": float(first["z_sample"]),
            "point_px": first_point,
            "frame": first["prefix"],
        }
    )
    detections[first["prefix"]] = {
        "accepted": True,
        "source": "roi_cross_alignment_reference",
        "point_px": [round(first_point[0], 3), round(first_point[1], 3)],
        "coarse_roi": list(current_coarse_roi),
        "refined_roi": list(current_refined_roi),
    }

    for index in range(1, len(ordered)):
        source_frame = ordered[index - 1]
        target_frame = ordered[index]
        source_prefix = source_frame["prefix"]
        target_prefix = target_frame["prefix"]
        coarse_match = match_nozzle_z_roi_pair(
            source_feature=features[source_prefix],
            target_feature=features[target_prefix],
            source_roi=current_coarse_roi,
            predicted_delta=(0.0, 0.0),
            search_pad_px=coarse_pad,
            width=width,
            height=height,
        )
        pair_record = {
            "source": source_prefix,
            "target": target_prefix,
            "source_x_offset": float(
                source_frame.get("x_offset", source_frame.get("dx", 0.0))
            ),
            "target_x_offset": float(
                target_frame.get("x_offset", target_frame.get("dx", 0.0))
            ),
            "coarse": coarse_match,
        }
        coarse_ok = (
            bool(coarse_match.get("accepted"))
            and float(coarse_match.get("correlation") or 0.0)
            >= NOZZLE_Z_COARSE_MIN_CORRELATION
        )
        if not coarse_ok:
            reason = (
                f"{target_prefix}: coarse ROI correlation "
                f"{float(coarse_match.get('correlation') or 0.0):.3f} below "
                f"{NOZZLE_Z_COARSE_MIN_CORRELATION:.2f}"
            )
            if coarse_match.get("rejection_reason"):
                reason = f"{target_prefix}: {coarse_match['rejection_reason']}"
            failures.append(reason)
            detections[target_prefix] = {
                "accepted": False,
                "source": "roi_cross_alignment",
                "rejection_reason": reason,
                "coarse_roi": list(current_coarse_roi),
                "refined_roi": list(current_refined_roi),
                "coarse_pair": coarse_match,
            }
            pairwise.append(pair_record)
            break

        refined_match = match_nozzle_z_roi_pair(
            source_feature=features[source_prefix],
            target_feature=features[target_prefix],
            source_roi=current_refined_roi,
            predicted_delta=(float(coarse_match["dx"]), float(coarse_match["dy"])),
            search_pad_px=refined_pad,
            width=width,
            height=height,
        )
        pair_record["refined"] = refined_match
        refined_ok = (
            bool(refined_match.get("accepted"))
            and float(refined_match.get("correlation") or 0.0)
            >= NOZZLE_Z_REFINED_MIN_CORRELATION
        )
        if not refined_ok:
            reason = (
                f"{target_prefix}: refined ROI correlation "
                f"{float(refined_match.get('correlation') or 0.0):.3f} below "
                f"{NOZZLE_Z_REFINED_MIN_CORRELATION:.2f}"
            )
            if refined_match.get("rejection_reason"):
                reason = f"{target_prefix}: {refined_match['rejection_reason']}"
            failures.append(reason)
            detections[target_prefix] = {
                "accepted": False,
                "source": "roi_cross_alignment",
                "rejection_reason": reason,
                "coarse_roi": list(current_coarse_roi),
                "refined_roi": list(current_refined_roi),
                "coarse_pair": coarse_match,
                "refined_pair": refined_match,
            }
            pairwise.append(pair_record)
            break

        cx, cy = coarse_match["matched_origin_px"]
        rx, ry = refined_match["matched_origin_px"]
        cw, ch = current_coarse_roi[2], current_coarse_roi[3]
        rw, rh = current_refined_roi[2], current_refined_roi[3]
        current_coarse_roi = clamp_rect(cx, cy, cw, ch, width, height)
        current_refined_roi = clamp_rect(rx, ry, rw, rh, width, height)
        point = [float(rx + rw / 2.0), float(ry + rh / 2.0)]
        samples.append(
            {
                "tool": tool,
                "x_offset": float(
                    target_frame.get("x_offset", target_frame.get("dx", 0.0))
                ),
                "z_sample": float(target_frame["z_sample"]),
                "point_px": point,
                "frame": target_prefix,
            }
        )
        detections[target_prefix] = {
            "accepted": True,
            "source": "roi_cross_alignment",
            "point_px": [round(point[0], 3), round(point[1], 3)],
            "coarse_roi": list(current_coarse_roi),
            "refined_roi": list(current_refined_roi),
            "coarse_pair": coarse_match,
            "refined_pair": refined_match,
        }
        pairwise.append(pair_record)

    for frame in ordered:
        detections.setdefault(
            frame["prefix"],
            {
                "accepted": False,
                "source": "roi_cross_alignment",
                "rejection_reason": "not analyzed after an earlier pair failure",
                "coarse_roi": list(current_coarse_roi),
                "refined_roi": list(current_refined_roi),
            },
        )

    fit = fit_points_by_dx(
        [
            {"dx": sample["x_offset"], "point_px": sample["point_px"]}
            for sample in samples
        ]
    )
    fit["z_sample"] = z_sample
    fit["sample_count"] = len(samples)
    if failures:
        fit["accepted"] = False
        if fit.get("ok"):
            fit["rejection_reason"] = "; ".join(failures)
    elif fit.get("ok"):
        fit["accepted"] = True
    else:
        failures.append(str(fit.get("rejection_reason") or "per-Z fit failed"))

    coarse_correlations = [
        float(match["coarse"].get("correlation"))
        for match in pairwise
        if match.get("coarse", {}).get("correlation") is not None
    ]
    refined_correlations = [
        float(match["refined"].get("correlation"))
        for match in pairwise
        if match.get("refined", {}).get("correlation") is not None
    ]
    ok = bool(not failures and fit.get("ok") and fit.get("accepted"))
    return {
        "ok": ok,
        "tool": tool,
        "z_sample": z_sample,
        "rejection_reason": "; ".join(failures) if failures else "",
        "hard_failures": failures,
        "samples": samples if ok else [],
        "diagnostic_samples": samples,
        "detections": detections,
        "pairwise": pairwise,
        "fit": fit,
        "coarse_roi": list(coarse_roi),
        "refined_roi": list(refined_roi),
        "coarse_search_pad_px": coarse_pad,
        "refined_search_pad_px": refined_pad,
        "coarse_correlation_min": (
            min(coarse_correlations) if coarse_correlations else None
        ),
        "coarse_correlation_median": median_float(coarse_correlations),
        "refined_correlation_min": (
            min(refined_correlations) if refined_correlations else None
        ),
        "refined_correlation_median": median_float(refined_correlations),
    }


def detect_nozzle_z_tip(image: Any, frame: dict[str, Any]) -> dict[str, Any]:
    height, width = image.shape[:2]
    attempts: list[dict[str, Any]] = []
    red = detect_red_marker(image)
    frame["red_marker"] = red
    if red.get("accepted"):
        try:
            red_roi = derive_nozzle_roi(red, width, height)
            candidates = detect_nozzle_candidates(image, red_roi)
            attempts.append(
                {
                    "source": "red_marker_roi",
                    "roi": list(red_roi),
                    "candidate_count": len(candidates),
                }
            )
            if candidates:
                best = candidates[0]
                return {
                    "accepted": True,
                    "source": "red_marker_roi",
                    "roi": list(red_roi),
                    "center_px": [round(best["cx"], 3), round(best["cy"], 3)],
                    "candidate": best,
                    "candidates": candidates[:6],
                    "attempts": attempts,
                }
        except RuntimeError as exc:
            attempts.append({"source": "red_marker_roi", "error": str(exc)})

    generic_roi = scale_rect_1080(NOZZLE_Z_TIP_ROI_1080, width, height)
    candidates = detect_nozzle_candidates(image, generic_roi)
    attempts.append(
        {
            "source": "generic_nozzle_z_roi",
            "roi": list(generic_roi),
            "candidate_count": len(candidates),
        }
    )
    if candidates:
        best = candidates[0]
        return {
            "accepted": True,
            "source": "generic_nozzle_z_roi",
            "roi": list(generic_roi),
            "center_px": [round(best["cx"], 3), round(best["cy"], 3)],
            "candidate": best,
            "candidates": candidates[:6],
            "attempts": attempts,
        }
    return {
        "accepted": False,
        "roi": list(generic_roi),
        "rejection_reason": "no nozzle tip candidate found",
        "attempts": attempts,
        "candidates": [],
    }


def annotate_nozzle_z_frame(
    image: Any, frame: dict[str, Any], detection: dict[str, Any]
) -> Any:
    import cv2

    overlay = image.copy()

    def draw_rect(rect: Any, color: tuple[int, int, int], thickness: int) -> None:
        if not rect:
            return
        x, y, w, h = [int(round(float(value))) for value in rect]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, thickness)

    red = frame.get("red_marker") or {}
    if red.get("roi"):
        x, y, w, h = red["roi"]
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
            markerSize=24,
            thickness=2,
        )
    roi = detection.get("roi")
    if roi:
        x, y, w, h = roi
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 220, 255), 2)
    coarse_pair = detection.get("coarse_pair") or {}
    refined_pair = detection.get("refined_pair") or {}
    draw_rect(coarse_pair.get("search_roi"), (120, 80, 255), 1)
    draw_rect(coarse_pair.get("match_roi"), (0, 220, 255), 1)
    draw_rect(detection.get("coarse_roi"), (0, 180, 255), 2)
    draw_rect(refined_pair.get("search_roi"), (255, 90, 180), 1)
    draw_rect(refined_pair.get("match_roi"), (80, 255, 80), 1)
    draw_rect(detection.get("refined_roi"), (0, 255, 0), 2)
    for candidate in detection.get("candidates") or []:
        cv2.circle(
            overlay,
            (int(round(candidate["cx"])), int(round(candidate["cy"]))),
            int(round(candidate.get("r") or 10)),
            (255, 255, 0),
            1,
            cv2.LINE_AA,
        )
    point = detection.get("point_px") or detection.get("center_px")
    if detection.get("accepted") and point:
        cx, cy = point
        cv2.drawMarker(
            overlay,
            (int(round(cx)), int(round(cy))),
            (0, 255, 0),
            markerType=cv2.MARKER_TILTED_CROSS,
            markerSize=30,
            thickness=2,
        )
    corr_label = ""
    if refined_pair.get("correlation") is not None:
        corr_label = f" r={float(refined_pair['correlation']):.3f}"
    elif coarse_pair.get("correlation") is not None:
        corr_label = f" c={float(coarse_pair['correlation']):.3f}"
    label = (
        f"{frame['tool'].upper()} x={frame.get('x_offset', frame.get('dx')):.3g} "
        f"z={frame.get('z_sample'):.3g} "
        f"{detection.get('source') if detection.get('accepted') else 'rejected'}"
        f"{corr_label}"
    )
    cv2.rectangle(overlay, (0, 0), (860, 48), (0, 0, 0), -1)
    cv2.putText(
        overlay,
        label,
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.82,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return overlay


def analyze_tool_xz_sweep_frames(
    frames: list[dict[str, Any]], run_dir: Path, overlay_dir: Path | None = None
) -> dict[str, Any]:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on Pi package install
        return {
            "ok": False,
            "proxy_only": True,
            "error": f"OpenCV import failed: {exc}",
            "hard_failures": [f"OpenCV import failed: {exc}"],
        }

    hard_failures: list[str] = []
    groups: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for frame in frames:
        tool = str(frame.get("tool", "")).lower()
        if tool not in {"t0", "t1"}:
            hard_failures.append(
                f"{frame['prefix']}: unsupported tool {frame.get('tool')!r}"
            )
            continue
        z_sample = float(frame["z_sample"])
        groups.setdefault((tool, z_sample), []).append(frame)

    image_shape: tuple[int, int] | None = None
    fits_by_tool: dict[str, dict[str, Any]] = {"t0": {}, "t1": {}}
    alignment_by_tool_z: dict[str, dict[str, Any]] = {"t0": {}, "t1": {}}
    frame_detections: dict[str, dict[str, Any]] = {}
    accepted_samples: list[dict[str, Any]] = []
    coarse_correlations: list[float] = []
    refined_correlations: list[float] = []
    overlay_root = overlay_dir or run_dir
    overlay_root.mkdir(parents=True, exist_ok=True)
    for tool in ("t0", "t1"):
        z_values = sorted(
            {key[1] for key in groups if key[0] == tool},
            reverse=True,
        )
        for z_sample in z_values:
            group_frames = groups[(tool, z_sample)]
            group_images: dict[str, Any] = {}
            group_features: dict[str, Any] = {}
            group_failures: list[str] = []
            for frame in group_frames:
                image = cv2.imread(frame["image_path"])
                if image is None:
                    reason = f"Could not read {frame['image_path']}"
                    frame["analysis_error"] = reason
                    group_failures.append(reason)
                    continue
                frame_height, frame_width = image.shape[:2]
                if image_shape is None:
                    image_shape = (frame_width, frame_height)
                elif image_shape != (frame_width, frame_height):
                    reason = (
                        f"{frame['prefix']}: image size "
                        f"{frame_width}x{frame_height} does not match first tool "
                        f"frame size {image_shape[0]}x{image_shape[1]}"
                    )
                    frame["analysis_error"] = reason
                    group_failures.append(reason)
                    continue
                frame["image_width"] = frame_width
                frame["image_height"] = frame_height
                group_images[frame["prefix"]] = image
                group_features[frame["prefix"]] = nozzle_z_preprocess_image(image)

            width = image_shape[0] if image_shape else RED_BASE_WIDTH
            height = image_shape[1] if image_shape else RED_BASE_HEIGHT
            if group_failures:
                coarse_roi = scale_rect_1080(NOZZLE_Z_COARSE_ROI_1080, width, height)
                refined_roi = scale_rect_1080(NOZZLE_Z_REFINED_ROI_1080, width, height)
                group_result = {
                    "ok": False,
                    "tool": tool,
                    "z_sample": z_sample,
                    "hard_failures": group_failures,
                    "rejection_reason": "; ".join(group_failures),
                    "samples": [],
                    "diagnostic_samples": [],
                    "detections": {
                        frame["prefix"]: {
                            "accepted": False,
                            "source": "roi_cross_alignment",
                            "rejection_reason": (
                                frame.get("analysis_error")
                                or "group contained unreadable frames"
                            ),
                            "coarse_roi": list(coarse_roi),
                            "refined_roi": list(refined_roi),
                        }
                        for frame in group_frames
                    },
                    "pairwise": [],
                    "fit": {
                        "ok": False,
                        "accepted": False,
                        "z_sample": z_sample,
                        "sample_count": 0,
                        "rejection_reason": "; ".join(group_failures),
                    },
                    "coarse_roi": list(coarse_roi),
                    "refined_roi": list(refined_roi),
                }
            else:
                group_result = track_nozzle_z_roi_group(
                    group_frames=group_frames,
                    features=group_features,
                    width=width,
                    height=height,
                )
            label = dx_label(z_sample)
            fit = group_result.get("fit") or {}
            fits_by_tool[tool][label] = fit
            frame_detections.update(group_result.get("detections") or {})
            if group_result.get("ok"):
                accepted_samples.extend(group_result.get("samples") or [])
            else:
                hard_failures.extend(
                    f"{tool.upper()} Z={z_sample:g}: {failure}"
                    for failure in (
                        group_result.get("hard_failures")
                        or [group_result.get("rejection_reason") or "rejected"]
                    )
                )
            for pair in group_result.get("pairwise") or []:
                coarse = pair.get("coarse") or {}
                refined = pair.get("refined") or {}
                if coarse.get("correlation") is not None:
                    coarse_correlations.append(float(coarse["correlation"]))
                if refined.get("correlation") is not None:
                    refined_correlations.append(float(refined["correlation"]))
            alignment_by_tool_z[tool][label] = {
                "accepted": bool(group_result.get("ok")),
                "z_sample": z_sample,
                "fit": fit,
                "coarse_roi": group_result.get("coarse_roi"),
                "refined_roi": group_result.get("refined_roi"),
                "coarse_search_pad_px": group_result.get("coarse_search_pad_px"),
                "refined_search_pad_px": group_result.get("refined_search_pad_px"),
                "coarse_correlation_min": group_result.get("coarse_correlation_min"),
                "coarse_correlation_median": group_result.get(
                    "coarse_correlation_median"
                ),
                "refined_correlation_min": group_result.get("refined_correlation_min"),
                "refined_correlation_median": group_result.get(
                    "refined_correlation_median"
                ),
                "samples": group_result.get("diagnostic_samples") or [],
                "pairwise": group_result.get("pairwise") or [],
                "rejection_reason": group_result.get("rejection_reason") or "",
            }

            for frame in group_frames:
                image = group_images.get(frame["prefix"])
                if image is None:
                    continue
                width = frame.get("image_width") or (
                    image_shape[0] if image_shape else RED_BASE_WIDTH
                )
                height = frame.get("image_height") or (
                    image_shape[1] if image_shape else RED_BASE_HEIGHT
                )
                detection = frame_detections.get(
                    frame["prefix"],
                    {
                        "accepted": False,
                        "source": "roi_cross_alignment",
                        "rejection_reason": (
                            frame.get("analysis_error")
                            or "frame was not part of a complete tool/Z group"
                        ),
                        "coarse_roi": list(
                            scale_rect_1080(
                                NOZZLE_Z_COARSE_ROI_1080,
                                int(width),
                                int(height),
                            )
                        ),
                        "refined_roi": list(
                            scale_rect_1080(
                                NOZZLE_Z_REFINED_ROI_1080,
                                int(width),
                                int(height),
                            )
                        ),
                    },
                )
                frame["nozzle_z_alignment"] = detection
                frame["nozzle_z_detection"] = detection
                if detection.get("accepted") and detection.get("point_px"):
                    frame["point_px"] = detection["point_px"]
                overlay = annotate_nozzle_z_frame(image, frame, detection)
                overlay_path = overlay_root / f"{frame['prefix']}_overlay.jpg"
                cv2.imwrite(
                    str(overlay_path), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92]
                )
                frame["overlay_path"] = str(overlay_path)
                frame["overlay_url"] = safe_vision_url(overlay_path)

    all_vectors: list[tuple[float, float]] = []
    for tool in ("t0", "t1"):
        for fit in fits_by_tool[tool].values():
            if (
                fit.get("ok")
                and fit.get("accepted", True)
                and fit.get("px_per_mm", 0) > 0
            ):
                vector = fit["vector_px_per_mm"]
                all_vectors.append((float(vector[0]), float(vector[1])))

    if not all_vectors:
        hard_failures.append("no per-Z X-scale fits could be computed")
        axis_unit = None
    else:
        avg_vector = (
            sum(vector[0] for vector in all_vectors) / len(all_vectors),
            sum(vector[1] for vector in all_vectors) / len(all_vectors),
        )
        axis_len = math.hypot(avg_vector[0], avg_vector[1])
        axis_unit = (
            (avg_vector[0] / axis_len, avg_vector[1] / axis_len)
            if axis_len > 0
            else None
        )
        if axis_unit is None:
            hard_failures.append("average image X axis has zero length")

    scale_samples_by_tool: dict[str, list[dict[str, Any]]] = {"t0": [], "t1": []}
    scale_fit_by_tool: dict[str, dict[str, Any]] = {}
    if axis_unit:
        ux, uy = axis_unit
        for tool in ("t0", "t1"):
            for fit in fits_by_tool[tool].values():
                if not fit.get("ok") or not fit.get("accepted", True):
                    continue
                vector = fit["vector_px_per_mm"]
                projected_scale = float(vector[0]) * ux + float(vector[1]) * uy
                scale_samples_by_tool[tool].append(
                    {
                        "z_sample": float(fit["z_sample"]),
                        "scale_px_per_mm": projected_scale,
                        "fit_residual_rms_px": fit.get("residual_rms_px"),
                        "sample_count": fit.get("sample_count"),
                    }
                )
            samples = scale_samples_by_tool[tool]
            if len(samples) < 3:
                scale_fit_by_tool[tool] = {
                    "ok": False,
                    "rejection_reason": "need at least three Z samples",
                }
                hard_failures.append(f"{tool.upper()}: need at least three Z samples")
                continue
            fit = linear_fit_xy(
                [float(sample["z_sample"]) for sample in samples],
                [float(sample["scale_px_per_mm"]) for sample in samples],
            )
            if fit.get("ok"):
                scale_residual = float(fit["residual_rms"])
                scale_quality_ok = (
                    scale_residual <= NOZZLE_Z_MAX_SCALE_FIT_RESIDUAL_PX_PER_MM
                )
                fit.update(
                    {
                        "slope_px_per_mm2": round(float(fit["slope"]), 6),
                        "intercept_px_per_mm": round(float(fit["intercept"]), 6),
                        "residual_rms_px_per_mm": round(scale_residual, 6),
                        "accepted": scale_quality_ok,
                        "samples": [
                            {
                                "z_sample": round(float(sample["z_sample"]), 4),
                                "scale_px_per_mm": round(
                                    float(sample["scale_px_per_mm"]), 6
                                ),
                                "fit_residual_rms_px": sample.get(
                                    "fit_residual_rms_px"
                                ),
                                "sample_count": sample.get("sample_count"),
                            }
                            for sample in samples
                        ],
                    }
                )
                noisy_x_fits = [
                    sample
                    for sample in samples
                    if sample.get("fit_residual_rms_px") is None
                    or float(sample["fit_residual_rms_px"])
                    > NOZZLE_Z_MAX_PER_Z_X_FIT_RESIDUAL_PX
                ]
                if noisy_x_fits:
                    fit["accepted"] = False
                    details = ", ".join(
                        f"Z={float(sample['z_sample']):.3g} "
                        f"rms={float(sample.get('fit_residual_rms_px') or 0):.3f}px"
                        for sample in noisy_x_fits
                    )
                    hard_failures.append(
                        f"{tool.upper()}: per-Z X fit residual too high ({details})"
                    )
                if not scale_quality_ok:
                    hard_failures.append(
                        f"{tool.upper()}: scale-vs-Z residual "
                        f"{scale_residual:.3f}px/mm too high"
                    )
            else:
                hard_failures.append(f"{tool.upper()}: {fit.get('rejection_reason')}")
            scale_fit_by_tool[tool] = fit

    slope_values = [
        float(fit["slope"]) for fit in scale_fit_by_tool.values() if fit.get("ok")
    ]
    common_slope = sum(slope_values) / len(slope_values) if slope_values else None
    if common_slope is None or abs(common_slope) < NOZZLE_Z_MIN_SCALE_SLOPE_ABS:
        hard_failures.append("tool X image scale does not vary enough with Z")
    if len(slope_values) == 2:
        first_slope, second_slope = slope_values
        if abs(first_slope) < NOZZLE_Z_MIN_SCALE_SLOPE_ABS:
            hard_failures.append(
                f"T0: scale-vs-Z slope {first_slope:.6f}px/mm^2 too small"
            )
        if abs(second_slope) < NOZZLE_Z_MIN_SCALE_SLOPE_ABS:
            hard_failures.append(
                f"T1: scale-vs-Z slope {second_slope:.6f}px/mm^2 too small"
            )
        if first_slope * second_slope <= 0:
            hard_failures.append(
                "T0/T1 scale-vs-Z slopes disagree in sign "
                f"({first_slope:.6f}, {second_slope:.6f})"
            )
        elif common_slope is not None and abs(common_slope) > 0:
            relative_spread = abs(first_slope - second_slope) / abs(common_slope)
            if relative_spread > NOZZLE_Z_MAX_TOOL_SLOPE_RELATIVE_SPREAD:
                hard_failures.append(
                    "T0/T1 scale-vs-Z slopes disagree too much "
                    f"(relative spread {relative_spread:.3f})"
                )

    ok = (
        len(slope_values) == 2
        and common_slope is not None
        and abs(common_slope) >= NOZZLE_Z_MIN_SCALE_SLOPE_ABS
        and all(scale_fit_by_tool.get(tool, {}).get("ok") for tool in ("t0", "t1"))
        and all(
            scale_fit_by_tool.get(tool, {}).get("accepted") for tool in ("t0", "t1")
        )
        and not hard_failures
    )
    if ok:
        message = "Tool X/Z image-scale fits accepted."
    else:
        message = "Tool X/Z image-scale fits rejected: " + "; ".join(hard_failures)

    return {
        "ok": ok,
        "proxy_only": not ok,
        "hard_failures": hard_failures,
        "alignment_method": "iterative_roi_cross_alignment",
        "coarse_roi_1080": list(NOZZLE_Z_COARSE_ROI_1080),
        "refined_roi_1080": list(NOZZLE_Z_REFINED_ROI_1080),
        "coarse_search_pad_1080": NOZZLE_Z_COARSE_SEARCH_PAD_1080,
        "refined_search_pad_1080": NOZZLE_Z_REFINED_SEARCH_PAD_1080,
        "coarse_min_correlation_threshold": NOZZLE_Z_COARSE_MIN_CORRELATION,
        "refined_min_correlation_threshold": NOZZLE_Z_REFINED_MIN_CORRELATION,
        "coarse_correlation_min": (
            min(coarse_correlations) if coarse_correlations else None
        ),
        "coarse_correlation_median": median_float(coarse_correlations),
        "refined_correlation_min": (
            min(refined_correlations) if refined_correlations else None
        ),
        "refined_correlation_median": median_float(refined_correlations),
        "accepted_sample_count": len(accepted_samples),
        "frame_count": len(frames),
        "x_axis_unit_vector_px": (
            [
                round(axis_unit[0], 6),
                round(axis_unit[1], 6),
            ]
            if axis_unit
            else None
        ),
        "per_z_x_fits": fits_by_tool,
        "pairwise_alignment_by_tool_z": alignment_by_tool_z,
        "scale_samples_by_tool": scale_samples_by_tool,
        "scale_fit_by_tool": scale_fit_by_tool,
        "common_scale_slope_px_per_mm2": (
            round(common_slope, 6) if common_slope is not None else None
        ),
        "lighting": frames[0].get("lighting") if frames else NOZZLE_Z_TOOL_LIGHTING,
        "message": message,
    }


def phase_lighting_from_manifest(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lighting: dict[str, dict[str, Any]] = {}
    parameters = manifest.get("measurement_parameters") or {}
    parameter_lighting = parameters.get("lighting")
    if isinstance(parameter_lighting, dict):
        for phase, value in parameter_lighting.items():
            if isinstance(value, dict):
                lighting[str(phase)] = dict(value)
            else:
                lighting[str(phase)] = {"macro": value}
    for frame in manifest.get("frames") or []:
        phase = frame.get("phase")
        macro = frame.get("lighting")
        if phase and macro:
            lighting.setdefault(str(phase), {"macro": macro})
    return lighting


def build_nozzle_z_offsets_facts(
    *, manifest: dict[str, Any], analysis: dict[str, Any], result_path: Path
) -> dict[str, Any]:
    bed_analysis = analysis.get("bed_y_sweep") or {}
    tool_analysis = analysis.get("tool_xz_sweep") or {}
    parameters = manifest.get("measurement_parameters") or {}
    current = parameters.get("current_calib_yaml") or {}
    current_tools = current.get("tools") or {}
    current_t0 = float(
        ((current_tools.get("t0") or {}).get("z_endstop") or DEFAULT_T0_Z_ENDSTOP)
    )
    current_t1 = float(
        ((current_tools.get("t1") or {}).get("z_endstop") or DEFAULT_T1_Z_ENDSTOP)
    )
    bed_feature_z_mm = float(
        parameters.get("bed_feature_z_mm", DEFAULT_NOZZLE_Z_BED_FEATURE_Z_MM)
    )
    bed_scale = bed_analysis.get("bed_y_scale_px_per_mm")
    common_slope = tool_analysis.get("common_scale_slope_px_per_mm2")
    tool_zero_error: dict[str, Any] = {"T0": None, "T1": None}
    tool_to_bed_feature: dict[str, Any] = {"T0": None, "T1": None}
    suggested_calib = {
        "tools": {
            "t0": {"z_endstop": None},
            "t1": {"z_endstop": None},
        }
    }
    suggested_runtime_t1_z_offset = None
    calibration_inputs_accepted = bool(
        bed_analysis.get("ok") and tool_analysis.get("ok")
    )
    if (
        calibration_inputs_accepted
        and bed_scale is not None
        and common_slope not in (None, 0)
    ):
        scale_fit_by_tool = tool_analysis.get("scale_fit_by_tool") or {}
        for tool_key, public_tool, current_value in (
            ("t0", "T0", current_t0),
            ("t1", "T1", current_t1),
        ):
            fit = scale_fit_by_tool.get(tool_key) or {}
            if fit.get("ok") and fit.get("intercept") is not None:
                z_to_bed = (float(fit["intercept"]) - float(bed_scale)) / float(
                    common_slope
                )
                zero_error = bed_feature_z_mm + z_to_bed
                tool_to_bed_feature[public_tool] = round(z_to_bed, 6)
                tool_zero_error[public_tool] = round(zero_error, 6)
                suggested_calib["tools"][tool_key]["z_endstop"] = round(
                    current_value + zero_error, 3
                )
        t0_new = suggested_calib["tools"]["t0"]["z_endstop"]
        t1_new = suggested_calib["tools"]["t1"]["z_endstop"]
        if t0_new is not None and t1_new is not None:
            suggested_runtime_t1_z_offset = round(float(t0_new) - float(t1_new), 3)
    delta = None
    if tool_zero_error["T0"] is not None and tool_zero_error["T1"] is not None:
        delta = round(float(tool_zero_error["T1"]) - float(tool_zero_error["T0"]), 6)
    accepted = bool(analysis.get("ok"))
    hard_failures = analysis.get("hard_failures") or []
    return {
        "schema_version": VISION_JOB_SCHEMA_VERSION,
        "job_id": manifest.get("job_id"),
        "kind": manifest.get("kind"),
        "camera": manifest.get("camera"),
        "profile": manifest.get("profile"),
        "manifest_hash": manifest.get("manifest_hash"),
        "gcode_hash": manifest.get("gcode_hash"),
        "measurement": NOZZLE_Z_MEASUREMENT,
        "accepted": accepted,
        "ok": accepted,
        "source_result": result_path.name,
        "bed_feature_z_mm": bed_feature_z_mm,
        "bed_y_axis_vector_px_per_mm": bed_analysis.get("bed_y_axis_vector_px_per_mm"),
        "bed_y_scale_px_per_mm": bed_scale,
        "tool_zero_error_mm": tool_zero_error,
        "tool_z_to_bed_feature_at_command_0_mm": tool_to_bed_feature,
        "tool_delta_t1_minus_t0_z_mm": delta,
        "suggested_calib_yaml": suggested_calib,
        "suggested_runtime_t1_z_offset": suggested_runtime_t1_z_offset,
        "lighting": phase_lighting_from_manifest(manifest),
        "quality": {
            "bed_y_sweep": {
                "accepted": bool(bed_analysis.get("ok")),
                "selected_roi": bed_analysis.get("selected_roi"),
                "feature_mode": bed_analysis.get("feature_mode"),
                "fit_residual_rms_px": bed_analysis.get("bed_y_fit_residual_rms_px"),
                "correlation_min": bed_analysis.get("bed_y_correlation_min"),
                "correlation_median": bed_analysis.get("bed_y_correlation_median"),
                "parallax_spread": bed_analysis.get("bed_y_parallax_spread"),
            },
            "tool_xz_sweep": {
                "accepted": bool(tool_analysis.get("ok")),
                "alignment_method": tool_analysis.get("alignment_method"),
                "coarse_roi_1080": tool_analysis.get("coarse_roi_1080"),
                "refined_roi_1080": tool_analysis.get("refined_roi_1080"),
                "coarse_correlation_min": tool_analysis.get("coarse_correlation_min"),
                "coarse_correlation_median": tool_analysis.get(
                    "coarse_correlation_median"
                ),
                "refined_correlation_min": tool_analysis.get("refined_correlation_min"),
                "refined_correlation_median": tool_analysis.get(
                    "refined_correlation_median"
                ),
                "accepted_sample_count": tool_analysis.get("accepted_sample_count"),
                "frame_count": tool_analysis.get("frame_count"),
                "common_scale_slope_px_per_mm2": common_slope,
                "scale_fit_by_tool": tool_analysis.get("scale_fit_by_tool"),
                "pairwise_alignment_by_tool_z": tool_analysis.get(
                    "pairwise_alignment_by_tool_z"
                ),
                "x_axis_unit_vector_px": tool_analysis.get("x_axis_unit_vector_px"),
            },
        },
        "hard_failures": hard_failures,
        "rejection_reasons": hard_failures,
    }


def write_nozzle_z_contact_sheet(
    frames: list[dict[str, Any]],
    analysis: dict[str, Any],
    contact_sheet_path: Path,
    *,
    use_overlays: bool,
) -> None:
    import cv2
    import numpy as np

    tile_w, tile_h = 260, 195
    cols = 9
    rows = max(1, math.ceil(len(frames) / cols))
    summary_h = 285
    sheet = np.full((rows * tile_h + summary_h, cols * tile_w, 3), 255, dtype=np.uint8)
    for index, frame in enumerate(frames):
        source_path = (
            frame.get("overlay_path") if use_overlays else frame.get("image_path")
        )
        image = cv2.imread(str(source_path or frame.get("image_path")))
        if image is None:
            continue
        tile = letterbox(image, tile_w, tile_h)
        row = index // cols
        col = index % cols
        x = col * tile_w
        y = row * tile_h
        sheet[y : y + tile_h, x : x + tile_w] = tile
        cv2.rectangle(sheet, (x, y), (x + tile_w - 1, y + tile_h - 1), (80, 80, 80), 1)
        label = frame["prefix"]
        cv2.rectangle(sheet, (x, y), (x + tile_w, y + 28), (0, 0, 0), -1)
        cv2.putText(
            sheet,
            label[:32],
            (x + 6, y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    facts = analysis.get("facts_preview") or {}
    summary_lines = [
        f"Nozzle camera one-run Z sweep: {analysis.get('run_name')}",
        f"report: {public_url(contact_sheet_path)}",
        "phases: bed_y_sweep uses NOZZLE_CAM_Y_FEATURE_LIGHT; tool_xz_sweep uses NOZZLE_CAM_ANALYSIS_LIGHT",
    ]
    if analysis.get("ok"):
        zero = facts.get("tool_zero_error_mm") or {}
        suggested = facts.get("suggested_calib_yaml", {}).get("tools", {})
        summary_lines.extend(
            [
                "status: accepted",
                f"T0 zero error={zero.get('T0')}mm, suggested z_endstop={suggested.get('t0', {}).get('z_endstop')}",
                f"T1 zero error={zero.get('T1')}mm, suggested z_endstop={suggested.get('t1', {}).get('z_endstop')}",
                f"suggested runtime t1_z_offset={facts.get('suggested_runtime_t1_z_offset')}",
            ]
        )
    else:
        failures = analysis.get("hard_failures") or [analysis.get("message")]
        summary_lines.append(
            f"STATUS: FAILED; {'; '.join(str(item) for item in failures[:3])}"
        )
    y0 = rows * tile_h
    cv2.rectangle(sheet, (0, y0), (sheet.shape[1], sheet.shape[0]), (238, 238, 238), -1)
    draw_text_lines(sheet, summary_lines, (24, y0 + 36), line_height=27, scale=0.55)
    cv2.imwrite(str(contact_sheet_path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def analyze_nozzle_z_sweep_frames(
    frames: list[dict[str, Any]],
    run_dir: Path,
    overlay_dir: Path | None,
    manifest: dict[str, Any],
    result_path: Path,
) -> dict[str, Any]:
    bed_frames = [frame for frame in frames if frame.get("phase") == "bed_y_sweep"]
    tool_frames = [frame for frame in frames if frame.get("phase") == "tool_xz_sweep"]
    bed_analysis = analyze_bed_y_sweep_frames(
        bed_frames, run_dir, overlay_dir=overlay_dir
    )
    tool_analysis = analyze_tool_xz_sweep_frames(
        tool_frames, run_dir, overlay_dir=overlay_dir
    )
    hard_failures: list[str] = []
    if not bed_analysis.get("ok"):
        hard_failures.extend(
            "bed_y_sweep: " + str(item)
            for item in (bed_analysis.get("hard_failures") or ["rejected"])
        )
    if not tool_analysis.get("ok"):
        hard_failures.extend(
            "tool_xz_sweep: " + str(item)
            for item in (tool_analysis.get("hard_failures") or ["rejected"])
        )
    ok = bool(bed_analysis.get("ok") and tool_analysis.get("ok"))
    analysis = {
        "ok": ok,
        "proxy_only": not ok,
        "measurement": NOZZLE_Z_MEASUREMENT,
        "hard_failures": hard_failures,
        "bed_y_sweep": bed_analysis,
        "tool_xz_sweep": tool_analysis,
        "lighting": phase_lighting_from_manifest(manifest),
        "phase_frame_counts": {
            "bed_y_sweep": len(bed_frames),
            "tool_xz_sweep": len(tool_frames),
        },
        "message": (
            "Nozzle camera one-run Z calibration accepted."
            if ok
            else "Nozzle camera one-run Z calibration rejected: "
            + "; ".join(hard_failures)
        ),
    }
    facts_preview = build_nozzle_z_offsets_facts(
        manifest=manifest, analysis=analysis, result_path=result_path
    )
    analysis["facts_preview"] = facts_preview
    return analysis


def analyze_acquired_job(args: argparse.Namespace) -> dict[str, Any]:
    job_id = sanitize_name(args.analyze_job or args.job_id)
    if not job_id:
        raise RuntimeError("--analyze-job requires a job id")
    job_root = Path(args.job_root)
    job_dir = job_dir_from_root(job_root, job_id)
    manifest, state = verify_prepared_job_integrity(job_dir)
    state_name = state.get("state")
    paths = job_analysis_paths(job_dir)
    if state_name == "analysing":
        reset_interrupted_analysis(job_dir, paths)
        state_name = "acquired"
    if state_name not in {"acquired", "completed", "failed"}:
        raise RuntimeError(
            f"vision job {manifest.get('job_id')} is {state_name!r}, "
            "expected 'acquired', 'completed', or 'failed'"
        )
    verify_acquired_job_frames(manifest, job_dir)
    if state_name == "acquired":
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
    if manifest.get("kind") == BED_Y_JOB_KIND:
        result["y_offsets"] = [
            float(frame["y_offset"])
            for frame in manifest.get("frames") or []
            if frame.get("phase") == "bed_y_sweep"
        ]
    elif manifest.get("kind") == NOZZLE_Z_JOB_KIND:
        result["phase_frame_counts"] = {
            phase: sum(
                1
                for frame in manifest.get("frames") or []
                if frame.get("phase") == phase
            )
            for phase in ("bed_y_sweep", "tool_xz_sweep")
        }
        result["y_offsets"] = [
            float(frame["y_offset"])
            for frame in manifest.get("frames") or []
            if frame.get("phase") == "bed_y_sweep"
        ]
        result["x_offsets"] = sorted(
            {
                float(frame["x_offset"])
                for frame in manifest.get("frames") or []
                if frame.get("phase") == "tool_xz_sweep"
            }
        )
        result["z_values"] = sorted(
            {
                float(frame["z_sample"])
                for frame in manifest.get("frames") or []
                if frame.get("phase") == "tool_xz_sweep"
            }
        )
    else:
        result["dx_values"] = unique_dx_values_from_manifest(manifest)
    try:
        if manifest.get("kind") == BED_Y_JOB_KIND:
            frames = load_bed_y_job_frames_for_analysis(job_dir / "manifest.json")
            analysis = analyze_bed_y_sweep_frames(
                frames, paths["analysis_dir"], overlay_dir=paths["overlays_dir"]
            )
            analysis.update(
                {
                    "run_name": manifest["job_id"],
                    "y_offsets": result["y_offsets"],
                    "job_id": manifest["job_id"],
                }
            )
            if frames:
                write_bed_y_contact_sheet(
                    frames,
                    analysis,
                    paths["raw_contact_sheet"],
                    use_overlays=False,
                )
                write_bed_y_contact_sheet(
                    frames,
                    analysis,
                    paths["overlay_contact_sheet"],
                    use_overlays=True,
                )
            facts = build_bed_y_motion_facts(
                manifest=manifest, analysis=analysis, result_path=paths["result"]
            )
        elif manifest.get("kind") == NOZZLE_Z_JOB_KIND:
            frames = load_nozzle_z_job_frames_for_analysis(job_dir / "manifest.json")
            analysis = analyze_nozzle_z_sweep_frames(
                frames,
                paths["analysis_dir"],
                overlay_dir=paths["overlays_dir"],
                manifest=manifest,
                result_path=paths["result"],
            )
            analysis.update(
                {
                    "run_name": manifest["job_id"],
                    "job_id": manifest["job_id"],
                }
            )
            facts = build_nozzle_z_offsets_facts(
                manifest=manifest, analysis=analysis, result_path=paths["result"]
            )
            analysis["facts_preview"] = facts
            if frames:
                write_nozzle_z_contact_sheet(
                    frames,
                    analysis,
                    paths["raw_contact_sheet"],
                    use_overlays=False,
                )
                write_nozzle_z_contact_sheet(
                    frames,
                    analysis,
                    paths["overlay_contact_sheet"],
                    use_overlays=True,
                )
        else:
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
                    write_contact_sheet(
                        frames, analysis, paths["overlay_contact_sheet"]
                    )
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
            "measurement": (
                BED_Y_MEASUREMENT
                if manifest.get("kind") == BED_Y_JOB_KIND
                else (
                    NOZZLE_Z_MEASUREMENT
                    if manifest.get("kind") == NOZZLE_Z_JOB_KIND
                    else "idex_nozzle_relative_offset"
                )
            ),
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


def run_bed_y_full_job(args: argparse.Namespace) -> dict[str, Any]:
    acquisition = run_bed_y_acquisition_job(args)
    if not acquisition.get("ok"):
        return {
            **acquisition,
            "ok": False,
            "analysis_started": False,
            "message": acquisition.get("error")
            or acquisition.get("failure")
            or "bed Y acquisition failed before analysis",
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


def run_nozzle_z_full_job(args: argparse.Namespace) -> dict[str, Any]:
    acquisition = run_nozzle_z_acquisition_job(args)
    if not acquisition.get("ok"):
        return {
            **acquisition,
            "ok": False,
            "analysis_started": False,
            "message": acquisition.get("error")
            or acquisition.get("failure")
            or "nozzle Z acquisition failed before analysis",
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


def render_bed_y_motion_result(facts: dict[str, Any], state: dict[str, Any]) -> str:
    accepted = bool(facts.get("accepted") or facts.get("ok"))
    hard_failures = facts.get("hard_failures") or []
    quality = facts.get("quality") or {}
    spread = facts.get("bed_y_parallax_spread") or {}
    vector = facts.get("bed_y_axis_vector_px_per_mm") or [None, None]
    status_text = "accepted" if accepted else "rejected"
    status_class = "result-ok" if accepted else "result-bad"
    spread_text = (
        "vector spread "
        + format_report_value(spread.get("axis_vector_spread_px_per_mm"), "px/mm")
        + ", scale spread "
        + format_report_value(spread.get("scale_spread_px_per_mm"), "px/mm")
    )
    if spread.get("scale_spread_percent") is not None:
        spread_text += ", " + format_report_value(
            spread.get("scale_spread_percent"), "%"
        )
    quality_text = (
        "rms "
        + format_report_value(facts.get("bed_y_fit_residual_rms_px"), "px")
        + ", corr min "
        + format_report_number(facts.get("bed_y_correlation_min"), 3)
        + ", corr median "
        + format_report_number(facts.get("bed_y_correlation_median"), 3)
    )
    rows = [
        (
            "Status",
            f'<span class="{status_class}">{html_text(status_text)}</span>',
            html_text(
                state.get("failure") or "; ".join(str(item) for item in hard_failures)
            ),
        ),
        (
            "Bed Y scale",
            html_text(format_report_value(facts.get("bed_y_scale_px_per_mm"), "px/mm")),
            html_text(format_report_value(facts.get("bed_y_mm_per_px"), "mm/px", 5)),
        ),
        (
            "Image vector",
            "dx "
            + html_text(format_report_value(vector[0], "px/mm"))
            + ", dy "
            + html_text(format_report_value(vector[1], "px/mm")),
            "image +Y is downward; negative image Y means the feature moves upward in the camera image as printer Y increases",
        ),
        (
            "Direction",
            html_text(format_report_value(facts.get("bed_y_axis_angle_deg"), "deg")),
            "cross-axis drift "
            + html_text(
                format_report_value(facts.get("bed_y_cross_axis_px_per_mm"), "px/mm")
            ),
        ),
        (
            "Parallax spread",
            html_text(spread_text),
            html_text(spread.get("meaning") or "local ROI variation only"),
        ),
        (
            "Quality",
            html_text(quality_text),
            "roi "
            + html_text(quality.get("selected_roi"))
            + ", mode "
            + html_text(quality.get("feature_mode")),
        ),
        (
            "Lighting",
            html_text(facts.get("lighting")),
            "primary bed Y feature light",
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
        '<section class="measurement"><h2>Nozzle Camera Bed Y Sweep</h2>'
        "<table><thead><tr><th>Metric</th><th>Value</th><th>Meaning</th></tr>"
        f"</thead><tbody>{row_html}</tbody></table></section>"
    )


def render_nozzle_z_offsets_result(facts: dict[str, Any], state: dict[str, Any]) -> str:
    accepted = bool(facts.get("accepted") or facts.get("ok"))
    hard_failures = facts.get("hard_failures") or facts.get("rejection_reasons") or []
    zero = facts.get("tool_zero_error_mm") or {}
    to_feature = facts.get("tool_z_to_bed_feature_at_command_0_mm") or {}
    suggested = facts.get("suggested_calib_yaml", {}).get("tools", {})
    lighting = facts.get("lighting") or {}
    quality = facts.get("quality") or {}
    bed_quality = quality.get("bed_y_sweep") or {}
    tool_quality = quality.get("tool_xz_sweep") or {}
    status_text = "accepted" if accepted else "rejected"
    status_class = "result-ok" if accepted else "result-bad"
    lighting_text = ", ".join(
        f"{phase}: {(value or {}).get('macro')}"
        for phase, value in sorted(lighting.items())
    )
    rows = [
        (
            "Status",
            f'<span class="{status_class}">{html_text(status_text)}</span>',
            html_text(
                state.get("failure") or "; ".join(str(item) for item in hard_failures)
            ),
        ),
        (
            "Bed feature Z",
            html_text(format_report_value(facts.get("bed_feature_z_mm"), "mm")),
            "relative to print-surface Z=0",
        ),
        (
            "Bed Y scale",
            html_text(format_report_value(facts.get("bed_y_scale_px_per_mm"), "px/mm")),
            "from bed_y_sweep fixed-feature motion",
        ),
        (
            "T0 zero error",
            html_text(format_report_value(zero.get("T0"), "mm")),
            "to bed feature at commanded Z=0: "
            + html_text(format_report_value(to_feature.get("T0"), "mm")),
        ),
        (
            "T1 zero error",
            html_text(format_report_value(zero.get("T1"), "mm")),
            "to bed feature at commanded Z=0: "
            + html_text(format_report_value(to_feature.get("T1"), "mm")),
        ),
        (
            "Suggested calib.yaml",
            "t0.z_endstop "
            + html_text(
                format_report_number((suggested.get("t0") or {}).get("z_endstop"), 3)
            )
            + ", t1.z_endstop "
            + html_text(
                format_report_number((suggested.get("t1") or {}).get("z_endstop"), 3)
            ),
            "measurement job is report-only; apply separately",
        ),
        (
            "Runtime T1 Z offset",
            html_text(
                format_report_value(facts.get("suggested_runtime_t1_z_offset"), "mm")
            ),
            "generated as t0.z_endstop - t1.z_endstop",
        ),
        (
            "T1 - T0 Z delta",
            html_text(
                format_report_value(facts.get("tool_delta_t1_minus_t0_z_mm"), "mm")
            ),
            "positive means T1 zero error is higher than T0",
        ),
        (
            "Tool X/Z quality",
            "samples "
            + html_text(
                format_report_number(tool_quality.get("accepted_sample_count"), 0)
            )
            + "/"
            + html_text(format_report_number(tool_quality.get("frame_count"), 0))
            + ", slope "
            + html_text(
                format_report_value(
                    tool_quality.get("common_scale_slope_px_per_mm2"),
                    "px/mm^2",
                    6,
                )
            ),
            "per-tool X image scale fitted against commanded Z",
        ),
        (
            "Bed Y quality",
            "roi "
            + html_text(bed_quality.get("selected_roi"))
            + ", mode "
            + html_text(bed_quality.get("feature_mode")),
            "corr median "
            + html_text(format_report_number(bed_quality.get("correlation_median"), 3)),
        ),
        (
            "Lighting",
            html_text(lighting_text or "n/a"),
            "phase-specific macros recorded in manifest and facts",
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
        '<section class="measurement"><h2>Nozzle Camera Z Calibration</h2>'
        "<table><thead><tr><th>Metric</th><th>Value</th><th>Meaning</th></tr>"
        f"</thead><tbody>{row_html}</tbody></table></section>"
    )


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
    if facts.get("measurement") == BED_Y_MEASUREMENT:
        return render_bed_y_motion_result(facts, state)
    if facts.get("measurement") == NOZZLE_Z_MEASUREMENT:
        return render_nozzle_z_offsets_result(facts, state)

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
            html_text(
                state.get("reason") or "; ".join(str(item) for item in hard_failures)
            ),
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
        "phase_frame_counts": {
            str(phase): sum(
                1
                for frame in manifest.get("frames") or []
                if frame.get("phase") == phase
            )
            for phase in sorted(
                {
                    frame.get("phase")
                    for frame in manifest.get("frames") or []
                    if frame.get("phase")
                }
            )
        },
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
        "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table>"
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
    count_text = (
        ", ".join(
            f"{html_text(state)}={html_text(count)}"
            for state, count in sorted(counts.items())
        )
        or "none"
    )
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
/usr/local/bin/vision_nozzle_align.py --run-job --name nozzle_sweep --x 195 --y -14.8 --z 20 --dx 0,3,6,9,12
/usr/local/bin/vision_nozzle_align.py --run-bed-y-job --name bed_y --x -80.4 --y -14.8 --z 293.75 --y-offsets 0,5,10,15,20
/usr/local/bin/vision_nozzle_align.py --run-nozzle-z-job --name nozzle_z --bed-y-x -80.4 --bed-y-y -14.8 --bed-y-z 293.75 --tool-x 195 --tool-y -14.8 --travel-z 20 --y-offsets 0,5,10,15,20 --x-offsets 0,3,6,9,12 --z-values 1,2,4,8 --bed-feature-z-mm -0.1</pre>
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
            f"<td>{html_text(frame.get('phase'))}</td>"
            f"<td>{html_text(frame.get('target'))}</td>"
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
        "<table><thead><tr><th>Seq</th><th>Frame</th><th>Phase</th>"
        "<th>Target</th><th>Tool</th><th>Pose</th><th>Profile</th>"
        "<th>Captured</th><th>Framebuffer</th>"
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


def attach_ui_refresh(
    result: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    try:
        result["ui"] = refresh_vision_ui(Path(args.job_root))
    except Exception as exc:
        result["ui_error"] = str(exc)
    return result


def moonraker_get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=15) as response:
        return json.loads(response.read())


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
        raise RuntimeError(
            f"Could not start {CROWSNEST_SERVICE}: {result.stderr.strip()}"
        )
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


def detect_nozzle_candidates(
    image: Any, roi: tuple[int, int, int, int]
) -> list[dict[str, Any]]:
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
                    "base_score": round(
                        0.35 * darkness - 1.7 * abs(radius - target_radius), 3
                    ),
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
        raise RuntimeError(
            "Cannot derive global nozzle ROI because no feature ROIs exist"
        )
    margin = (
        NOZZLE_GLOBAL_MATCH_MARGIN_1080
        * (width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT)
        / 2.0
    )
    left = min(box[0] for box in feature_boxes) - margin
    top = min(box[1] for box in feature_boxes) - margin
    right = max(box[0] + box[2] for box in feature_boxes) + margin
    bottom = max(box[1] + box[3] for box in feature_boxes) + margin
    return clamp_rect(left, top, right - left, bottom - top, width, height)


def normalized_registration_feature(
    image: Any, roi: tuple[int, int, int, int], mode: str
) -> Any:
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


def match_registration_features(
    source_feature: Any, target_feature: Any, search_px: int
) -> dict[str, Any]:
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
        tool_delta = (1.0 if record["target_tool"] == "t1" else 0.0) - (
            1.0 if record["source_tool"] == "t1" else 0.0
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
    solution = np.linalg.lstsq(
        weight_matrix @ matrix, weight_matrix @ vector, rcond=None
    )[0]

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
        tool_delta = (1.0 if record["target_tool"] == "t1" else 0.0) - (
            1.0 if record["source_tool"] == "t1" else 0.0
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
        (
            int(
                round(
                    NOZZLE_GLOBAL_MATCH_SEARCH_1080
                    * (
                        frames[0].get("image_width", RED_BASE_WIDTH) / RED_BASE_WIDTH
                        + frames[0].get("image_height", RED_BASE_HEIGHT)
                        / RED_BASE_HEIGHT
                    )
                    / 2.0
                )
            )
            if frames
            else int(round(NOZZLE_GLOBAL_MATCH_SEARCH_1080))
        ),
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
                command_delta = abs(
                    float(target_frame["dx"]) - float(source_frame["dx"])
                )
                useful_cross_tool_pair = (
                    same_tool or command_delta <= max_cross_tool_command_delta + 1.0e-6
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
            median_corr = (
                correlations_sorted[len(correlations_sorted) // 2]
                if correlations
                else 0.0
            )
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
                    "rejected_pair_count": len(items) * (len(items) - 1)
                    - len(usable_records),
                    "correlation_min": (
                        round(min(correlations), 4) if correlations else None
                    ),
                    "correlation_median": (
                        round(median_corr, 4) if correlations else None
                    ),
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
                float(expected[0])
                - float(frame["dx"]) * axis[0]
                - tool_index * delta[0],
                float(expected[1])
                - float(frame["dx"]) * axis[1]
                - tool_index * delta[1],
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
                reference_center[0]
                + float(frame["dx"]) * axis[0]
                + tool_index * delta[0],
                reference_center[1]
                + float(frame["dx"]) * axis[1]
                + tool_index * delta[1],
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
        "axis_angle_deg": (
            round(math.degrees(math.atan2(axis[1], axis[0])), 4)
            if axis_len > 0
            else None
        ),
        "t1_minus_t0_pixels": [round(delta[0], 4), round(delta[1], 4)],
        "along_x_px": round(along_x_px, 4),
        "along_x_mm_approx": round(along_x_px / axis_len, 5) if axis_len > 0 else None,
        "perpendicular_px": round(perpendicular_px, 4),
        "perpendicular_mm_approx": (
            round(perpendicular_px / axis_len, 5) if axis_len > 0 else None
        ),
        "reference_center_px": (
            [round(reference_center[0], 4), round(reference_center[1], 4)]
            if reference_center
            else None
        ),
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
        score = 130.0 * len(distinct_dx) + sum(
            float(member["candidate"].get("base_score", 0.0)) for member in cluster
        ) / max(1, len(cluster))
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
    if (
        nozzle_result
        and nozzle_result.get("measurement_source") == "global_roi_cross_match"
    ):
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
            cv2.rectangle(
                sheet, (x, y), (x + tile_w - 1, y + tile_h - 1), (80, 80, 80), 2
            )

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
        failures = analysis.get("hard_failures") or [
            cross.get("rejection_reason", "rejected")
        ]
        summary_lines.append(
            f"STATUS: FAILED; {'; '.join(str(item) for item in failures[:3])}"
        )
    else:
        summary_lines.append("STATUS: global ROI cross-match accepted.")

    summary_y = rows * tile_h + 35
    cv2.rectangle(
        sheet, (0, rows * tile_h), (cols * tile_w, sheet.shape[0]), (238, 238, 238), -1
    )
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
        hard_failures.append(
            "no readable frames passed red marker and nozzle-candidate gates"
        )
    if global_roi:
        for frame in analysis_frames:
            frame["global_nozzle_roi"] = list(global_roi)

    if hard_failures:
        cross_match = {
            "accepted": False,
            "rejection_reason": "; ".join(hard_failures),
        }
    elif global_roi and red_axis_vector:
        cross_match = fit_global_roi_cross_match(
            analysis_frames, global_roi, red_axis_vector
        )
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
    if red_marker_fits.get("t0", {}).get("ok") and red_marker_fits.get("t1", {}).get(
        "ok"
    ):
        t0 = red_marker_fits["t0"]["intercept_px"]
        t1 = red_marker_fits["t1"]["intercept_px"]
        dx = float(t1[0]) - float(t0[0])
        dy = float(t1[1]) - float(t0[1])
        red_delta = {
            "dx": round(dx, 3),
            "dy": round(dy, 3),
            "distance": round(math.hypot(dx, dy), 3),
        }
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
        "red_axis_vector_px_per_mm": (
            [round(red_axis_vector[0], 3), round(red_axis_vector[1], 3)]
            if red_axis_vector
            else None
        ),
        "red_axis_px_per_mm": round(red_axis_px_per_mm, 3) if red_axis_vector else None,
        "red_axis_angle_deg": (
            round(red_axis_angle, 3) if red_axis_angle is not None else None
        ),
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
        result["message"] = (
            "Nozzle vision sweep failed before producing a complete result."
        )
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
                result["restore"] = {
                    "ok": True,
                    "tool": macro,
                    "gcode_position": pos[:3],
                }
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
        "--prepare-bed-y-job",
        action="store_true",
        help="Generate an immutable prepared bed Y feature sweep job.",
    )
    mode.add_argument(
        "--prepare-nozzle-z-job",
        action="store_true",
        help="Generate one immutable bed-Y plus nozzle X/Z calibration job.",
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
        "--run-nozzle-z-acquisition-job",
        action="store_true",
        help="Prepare, start, and monitor one combined nozzle Z acquisition job.",
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
        "--run-bed-y-job",
        action="store_true",
        help="Prepare, acquire, analyze, and report a complete bed Y feature sweep.",
    )
    mode.add_argument(
        "--run-nozzle-z-job",
        action="store_true",
        help="Prepare, acquire, analyze, and report a complete nozzle Z sweep.",
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
    parser.add_argument("--y-offsets", default="0,5,10,15,20")
    parser.add_argument("--x-offsets", default="0,3,6,9,12")
    parser.add_argument("--z-values", default="1,2,4,8")
    parser.add_argument("--bed-y-x", type=float, default=-80.4)
    parser.add_argument("--bed-y-y", type=float, default=-14.8)
    parser.add_argument("--bed-y-z", type=float, default=DEFAULT_T0_Z_ENDSTOP)
    parser.add_argument("--tool-x", type=float, default=195.0)
    parser.add_argument("--tool-y", type=float, default=-14.8)
    parser.add_argument("--travel-z", type=float, default=20.0)
    parser.add_argument(
        "--bed-feature-z-mm",
        type=float,
        default=DEFAULT_NOZZLE_Z_BED_FEATURE_Z_MM,
    )
    parser.add_argument(
        "--current-t0-z-endstop",
        type=float,
        default=DEFAULT_T0_Z_ENDSTOP,
    )
    parser.add_argument(
        "--current-t1-z-endstop",
        type=float,
        default=DEFAULT_T1_Z_ENDSTOP,
    )
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
    parser.add_argument(
        "--restore", action=argparse.BooleanOptionalAction, default=True
    )
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
        and not args.prepare_bed_y_job
        and not args.prepare_nozzle_z_job
        and not args.start_prepared_job
        and not args.run_acquisition_job
        and not args.run_nozzle_z_acquisition_job
        and not args.analyze_job
        and not args.run_job
        and not args.run_bed_y_job
        and not args.run_nozzle_z_job
        and not args.refresh_ui
    ):
        parser.error(
            "single-image nozzle vision check was removed; use --sweep, "
            "--prepare-job, --prepare-bed-y-job, --prepare-nozzle-z-job, "
            "--start-prepared-job, --run-acquisition-job, "
            "--run-nozzle-z-acquisition-job, --analyze-job, --run-job, "
            "--run-bed-y-job, --run-nozzle-z-job, or --refresh-ui"
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
    if args.prepare_bed_y_job:
        summary = prepare_bed_y_sweep_job(args)
        attach_ui_refresh(summary, args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary.get("ok") else 1
    if args.prepare_nozzle_z_job:
        summary = prepare_nozzle_z_sweep_job(args)
        attach_ui_refresh(summary, args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary.get("ok") else 1
    if (
        args.start_prepared_job
        or args.run_acquisition_job
        or args.run_nozzle_z_acquisition_job
    ):
        try:
            if args.run_nozzle_z_acquisition_job:
                result = run_nozzle_z_acquisition_job(args)
            elif args.run_acquisition_job:
                result = run_acquisition_job(args)
            else:
                result = start_prepared_job(args)
        except Exception as exc:
            result = {
                "ok": False,
                "error": str(exc),
                "job_id": args.start_prepared_job or args.job_id,
            }
        attach_ui_refresh(result, args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.analyze_job or args.run_job or args.run_bed_y_job or args.run_nozzle_z_job:
        try:
            if args.run_bed_y_job:
                result = run_bed_y_full_job(args)
            elif args.run_nozzle_z_job:
                result = run_nozzle_z_full_job(args)
            else:
                result = (
                    run_full_job(args) if args.run_job else analyze_acquired_job(args)
                )
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
