#!/usr/bin/env python3
"""Graph-driven nozzle-camera calibration through the fine nozzle X/Z stage."""

from __future__ import annotations

import argparse
import html
import json
import logging
import math
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from calib_dao import CalibDAO
from vision_bed_fiducial import analyze_corner, analyze_metric
from vision_calibration_graph import (
    ANALYSIS_SCHEMA,
    FACT_SET_SCHEMA,
    MANIFEST_SCHEMA,
    SCHEMA_VERSION,
    CalibrationGraphError,
    VisionCalibrationError,
    atomic_write_json,
    canonical_hash,
    content_hash,
    load_json,
    publish_fact_set,
    rebuild_catalog,
    sha256_file,
    utc_now,
    validate_manifest,
    validate_registry,
)
from vision_eddy_fiducial_xz import analyze as analyze_eddy_fiducial_xz
from vision_eddy_xyz_offset import analyze as analyze_eddy_xyz_offset
from vision_fine_tool_calibration import (
    calculate_candidate as calculate_fine_tool_candidate,
)
from vision_fine_tool_calibration import write_artifacts as write_fine_tool_artifacts
from vision_idex_xyz_offset import analyze_idex_xyz_offset
from vision_nozzle_fine_xz import analyze as analyze_fine_nozzle_xz
from vision_red_marker_x_sweep import analyze as analyze_red_marker_x_sweep
from vision_rough_x_verification import analyze as analyze_rough_x_verification
from vision_rough_x_verification import (
    calculate_candidate as calculate_rough_x_candidate,
)
from vision_tool_xy_calibration import ToolXYError
from vision_tool_xy_calibration import (
    analyze_measurement as analyze_tool_xy_measurement,
)
from vision_tool_xy_calibration import build_acquisition_gcode as build_tool_xy_gcode
from vision_tool_xy_calibration import build_measurement_fact as build_tool_xy_fact
from vision_tool_xy_calibration import (
    prepare_measurement as prepare_tool_xy_measurement,
)

_logger = logging.getLogger(__name__)

CALIBRATION_ROOT = Path(
    os.environ.get(
        "VISION_CALIBRATION_ROOT",
        "/home/pi/printer_data/vision/calibration",
    )
)
VISION_ROOT = CALIBRATION_ROOT.parent
GCODE_ROOT = Path(
    os.environ.get(
        "VISION_CALIBRATION_GCODE_ROOT",
        "/home/pi/printer_data/gcodes/vision_jobs",
    )
)
REGISTRY_PATH = Path(
    os.environ.get(
        "VISION_CALIBRATION_REGISTRY",
        "/usr/local/share/vision/vision_job_types.json",
    )
)
PROFILE_PATH = Path(
    os.environ.get(
        "VISION_CAMERA_PROFILE_FILE",
        "/usr/local/share/vision/nozzle_cam_profiles.json",
    )
)
FRAMEBUFFER_DIR = Path(
    os.environ.get("VISION_FRAMEBUFFER_DIR", "/run/vision-preview-nozzle_cam")
)
MOONRAKER_URL = os.environ.get("VISION_MOONRAKER_URL", "http://127.0.0.1")

BED_FIDUCIAL_METRIC_JOB = "nozzle_cam_bed_fiducial_y_metric"
BED_TAB_CORNER_JOB = "nozzle_cam_bed_tab_corner"
RED_MARKER_X_JOB = "idex_tool_red_marker_x_sweep"
ROUGH_X_VERIFY_JOB = "idex_rough_tool_x_verify"
IDEX_T0_T1_XYZ_OFFSET_JOB = "idex_t0_t1_xyz_offset"
EDDY_FIDUCIAL_XZ_JOB = "idex_eddy_fiducial_xz_grid"
EDDY_T0_XYZ_OFFSET_JOB = "idex_eddy_t0_xyz_offset"
FINE_NOZZLE_XZ_T0_JOB = "idex_nozzle_fine_xz_grid_t0"
FINE_NOZZLE_XZ_T1_JOB = "idex_nozzle_fine_xz_grid_t1"
FINE_NOZZLE_XZ_JOBS = {
    FINE_NOZZLE_XZ_T0_JOB,
    FINE_NOZZLE_XZ_T1_JOB,
}
TOOL_XY_T0_JOB = "idex_tool_xy_measure_t0"
TOOL_XY_T1_JOB = "idex_tool_xy_measure_t1"
TOOL_XY_JOBS = {TOOL_XY_T0_JOB, TOOL_XY_T1_JOB}
JOB_TYPES = (
    BED_FIDUCIAL_METRIC_JOB,
    BED_TAB_CORNER_JOB,
    RED_MARKER_X_JOB,
    ROUGH_X_VERIFY_JOB,
    EDDY_FIDUCIAL_XZ_JOB,
    FINE_NOZZLE_XZ_T0_JOB,
    FINE_NOZZLE_XZ_T1_JOB,
    TOOL_XY_T0_JOB,
    TOOL_XY_T1_JOB,
    EDDY_T0_XYZ_OFFSET_JOB,
    IDEX_T0_T1_XYZ_OFFSET_JOB,
)
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HASH_RE = re.compile(r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+")
HASH_PLACEHOLDER = "sha256:PLACEHOLDER"
_LOGGED_CATALOG_WARNINGS: set[str] = set()
CALIB = CalibDAO()
RETIRED_PRIOR_FACT_NAMES = {
    "bed.tab_corner.printer_xyz",
    "bed.fiducial_patch.physical_reference",
    "bed.fiducial_patch.printer_z_mm",
}


def _sanitize(value: str) -> str:
    result = NAME_RE.sub("_", str(value)).strip("._-")
    return (result or "vision_calibration")[:72]


def _load_registry() -> dict[str, Any]:
    return validate_registry(load_json(REGISTRY_PATH))


def _is_compute_only_job_type(job_type: str) -> bool:
    definition = validate_registry(load_json(REGISTRY_PATH))["job_types"][job_type]
    return definition.get("localizer", {}).get("kind") == "compute_only"


def _prior_provenance(job_type: str) -> dict[str, Any]:
    result: dict[str, Any] = {"sha256": CALIB.priors_hash()}
    if job_type in {BED_FIDUCIAL_METRIC_JOB, BED_TAB_CORNER_JOB, *FINE_NOZZLE_XZ_JOBS}:
        right, up = CALIB.fiducial_angles()
        result["fiducial_angles_deg"] = {"right": right, "up": up}
    if job_type in {BED_FIDUCIAL_METRIC_JOB, RED_MARKER_X_JOB}:
        result["fiducial_centers_xy_mm"] = CALIB.fiducial_centers()
    if job_type == BED_TAB_CORNER_JOB:
        result["bed_corner_xyz_mm"] = CALIB.bed_corner()
    if job_type in {BED_TAB_CORNER_JOB, *FINE_NOZZLE_XZ_JOBS}:
        result["fiducial_z_mm"] = CALIB.fiducial_z()
    return result


def _acquisition_calibration_snapshot() -> dict[str, Any]:
    datums = CALIB.tool_datums()
    return {
        "calib_sha256": CALIB.calib_hash(),
        "tool_xy_endstops_mm": {
            tool: {
                "x": datums[tool]["x_endstop"],
                "y": datums[tool]["y_endstop"],
            }
            for tool in ("t0", "t1")
        },
    }


def _publish_operation_fact_set(
    operation: str,
    *,
    facts: list[dict[str, Any]],
    provenance: dict[str, Any],
    applicability: dict[str, Any],
) -> dict[str, Any]:
    timestamp = utc_now()
    operation_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + _sanitize(operation)
    )
    analysis_hash = canonical_hash(
        {
            "operation": operation,
            "timestamp": timestamp,
            "facts": facts,
            "provenance": provenance,
        }
    )
    fact_set = {
        "schema": FACT_SET_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fact_set_id": operation_id,
        "job_id": f"operation:{operation}",
        "analysis_run_id": operation_id,
        "analysis_hash": analysis_hash,
        "created_at_utc": timestamp,
        "accepted": True,
        "publication_eligible": True,
        "applicability_hash": canonical_hash(applicability),
        "facts": facts,
        "provenance": {
            "source": "vision_calibration_operation",
            "operation": operation,
            **provenance,
        },
        "fact_set_hash": "",
    }
    fact_set["fact_set_hash"] = content_hash(fact_set, "fact_set_hash")
    path = (
        CALIBRATION_ROOT / "seeds" / fact_set["fact_set_hash"][7:23] / "fact_set.json"
    )
    atomic_write_json(path, fact_set, immutable=True)
    result = publish_seed_fact_set(CALIBRATION_ROOT, path)
    rebuild_and_render()
    return {
        "fact_set_hash": fact_set["fact_set_hash"],
        "publication": result["publication"],
        "facts": [fact["name"] for fact in facts],
    }


def _moonraker_get(path: str, *, timeout: float = 15.0) -> dict[str, Any]:
    with urllib.request.urlopen(
        MOONRAKER_URL.rstrip("/") + path, timeout=timeout
    ) as response:
        payload = json.loads(response.read())
    if "error" in payload:
        raise VisionCalibrationError(f"Moonraker error: {payload['error']}")
    return payload["result"]


def _moonraker_post(
    path: str, payload: dict[str, Any], *, timeout: float = 15.0
) -> dict[str, Any]:
    request = urllib.request.Request(
        MOONRAKER_URL.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read())
    if "error" in result:
        raise VisionCalibrationError(f"Moonraker error: {result['error']}")
    return result["result"]


def query_printer_status() -> dict[str, Any]:
    objects = (
        "webhooks&print_stats&virtual_sdcard&toolhead&gcode_move&configfile"
        "&extruder&extruder1&heater_bed&gcode_macro%20_IDEX_CONFIG_FINGERPRINT"
        "&gcode_macro%20_IDEX_TOOL_STATE"
    )
    return _moonraker_get(f"/printer/objects/query?{objects}")["status"]


def _settings(settings: dict[str, Any], name: str) -> dict[str, Any]:
    value = settings.get(name)
    if not isinstance(value, dict):
        raise VisionCalibrationError(f"active Klipper lacks [{name}] settings")
    return value


def _number(mapping: dict[str, Any], key: str, context: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        raise VisionCalibrationError(f"{context}.{key} is unavailable")
    return float(value)


def _profile_names() -> set[str]:
    payload = load_json(PROFILE_PATH)
    aliases = payload.get("aliases") or {}
    profiles = payload.get("profiles") or {}
    return set(aliases) | set(profiles)


def _framebuffer_status() -> dict[str, Any]:
    image = FRAMEBUFFER_DIR / "latest.jpg"
    metadata = FRAMEBUFFER_DIR / "latest.json"
    if not image.is_file() or not metadata.is_file():
        raise VisionCalibrationError("nozzle-camera framebuffer is unavailable")
    value = load_json(metadata)
    if not isinstance(value.get("frame_seq"), int):
        raise VisionCalibrationError("framebuffer sequence is unavailable")
    if int(value.get("width", 0)) <= 0 or int(value.get("height", 0)) <= 0:
        raise VisionCalibrationError("framebuffer dimensions are invalid")
    if cv2.imread(str(image), cv2.IMREAD_COLOR) is None:
        raise VisionCalibrationError("latest framebuffer JPEG cannot be decoded")
    return {
        "frame_seq": value["frame_seq"],
        "width": value["width"],
        "height": value["height"],
        "profile_names": value.get("camera_profile", {}).get("profile_names", []),
        "image_sha256": sha256_file(image),
        "metadata_sha256": sha256_file(metadata),
    }


def _preflight(
    status: dict[str, Any],
    job_type: str,
    definition: dict[str, Any],
    expected_fingerprint: str | None,
) -> dict[str, Any]:
    if status.get("webhooks", {}).get("state") != "ready":
        raise VisionCalibrationError("Klipper is not ready")
    print_state = str(status.get("print_stats", {}).get("state", "")).lower()
    if print_state not in {"standby", "complete"}:
        raise VisionCalibrationError(f"printer is not idle: {print_state}")
    if bool(status.get("virtual_sdcard", {}).get("is_active")):
        raise VisionCalibrationError("virtual-SD print is active")
    settings = status.get("configfile", {}).get("settings")
    if not isinstance(settings, dict):
        raise VisionCalibrationError("active Klipper settings are unavailable")
    stepper_x = _settings(settings, "stepper_x")
    stepper_y = _settings(settings, "stepper_y")
    stepper_z = _settings(settings, "stepper_z")
    dual = _settings(settings, "dual_carriage")
    axis_minimum = [
        _number(stepper_x, "position_min", "stepper_x"),
        _number(stepper_y, "position_min", "stepper_y"),
        _number(stepper_z, "position_min", "stepper_z"),
    ]
    axis_maximum = [
        max(
            _number(stepper_x, "position_max", "stepper_x"),
            _number(dual, "position_max", "dual_carriage"),
        ),
        _number(stepper_y, "position_max", "stepper_y"),
        _number(stepper_z, "position_max", "stepper_z"),
    ]
    fingerprint = str(
        status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT", {}).get("source_sha256", "")
    )
    if not fingerprint:
        raise VisionCalibrationError("active printer fingerprint is unavailable")
    if expected_fingerprint and fingerprint != expected_fingerprint:
        raise VisionCalibrationError(
            f"active fingerprint {fingerprint} != {expected_fingerprint}"
        )
    temperatures = {}
    for name in ("extruder", "extruder1", "heater_bed"):
        item = status.get(name) or {}
        target = float(item.get("target", 0.0))
        current = float(item.get("temperature", 0.0))
        temperatures[name] = {"temperature": current, "target": target}
        if abs(target) > 0.01:
            raise VisionCalibrationError(f"{name} target is not off")
        if current > 50.0:
            raise VisionCalibrationError(f"{name} is not cold ({current:.1f} C)")
    known_profiles = _profile_names()
    profiles = []
    if "profile" in definition:
        profiles.append(definition["profile"])
    profiles.extend(definition.get("exposure_profiles", []))
    unknown = sorted(set(profiles) - known_profiles)
    if unknown:
        raise VisionCalibrationError(f"unknown camera profiles: {unknown}")
    framebuffer = _framebuffer_status()
    pose = {
        "x_mm": _number(stepper_x, "position_min", "stepper_x"),
        "y_base_mm": _number(stepper_y, "position_min", "stepper_y"),
        "z_mm": _number(stepper_z, "position_max", "stepper_z"),
        "capture_y_mm": float(definition.get("capture_y_mm", axis_minimum[1])),
        "capture_z_mm": float(definition.get("capture_z_mm", axis_minimum[2])),
        "safe_tool_change_z_mm": float(definition.get("safe_tool_change_z_mm", 5.0)),
    }
    positions = []
    if job_type == BED_FIDUCIAL_METRIC_JOB:
        positions.extend(
            [
                (pose["x_mm"], pose["y_base_mm"] + float(offset), pose["z_mm"])
                for offset in definition["y_offsets_mm"]
            ]
        )
    elif job_type == BED_TAB_CORNER_JOB:
        positions.append(
            (
                pose["x_mm"],
                pose["y_base_mm"] + float(definition["capture_y_offset_mm"]),
                pose["z_mm"],
            )
        )
    elif job_type in {
        RED_MARKER_X_JOB,
        ROUGH_X_VERIFY_JOB,
        EDDY_FIDUCIAL_XZ_JOB,
        *FINE_NOZZLE_XZ_JOBS,
    }:
        positions.append(
            (
                axis_minimum[0],
                pose["capture_y_mm"],
                pose["safe_tool_change_z_mm"],
            )
        )
    for x, y, z in positions:
        if not (
            axis_minimum[0] <= x <= axis_maximum[0]
            and axis_minimum[1] <= y <= axis_maximum[1]
            and axis_minimum[2] <= z <= axis_maximum[2]
        ):
            raise VisionCalibrationError(f"resolved pose {(x, y, z)} is out of limits")
    active_snapshot = {
        "t0_x_endstop_mm": _number(stepper_x, "position_endstop", "stepper_x"),
        "t1_x_endstop_mm": _number(dual, "position_endstop", "dual_carriage"),
    }
    active_tool_calibration = None
    if job_type in TOOL_XY_JOBS:
        tool_state = status.get("gcode_macro _IDEX_TOOL_STATE")
        if not isinstance(tool_state, dict):
            raise VisionCalibrationError(
                "active _IDEX_TOOL_STATE is unavailable for tool-XY acquisition"
            )
        active_tool_calibration = {
            "active_fingerprint": fingerprint,
            "tool_xy_endstops_mm": {
                "t0": {
                    "x": active_snapshot["t0_x_endstop_mm"],
                    "y": _number(tool_state, "t0_y_endstop", "_IDEX_TOOL_STATE"),
                },
                "t1": {
                    "x": active_snapshot["t1_x_endstop_mm"],
                    "y": _number(tool_state, "t1_y_endstop", "_IDEX_TOOL_STATE"),
                },
            },
            "tool_y_offsets_mm": {
                "t0": _number(tool_state, "t0_y_offset", "_IDEX_TOOL_STATE"),
                "t1": _number(tool_state, "t1_y_offset", "_IDEX_TOOL_STATE"),
            },
        }
    scope = {
        "camera": "nozzle_cam",
        "registry_job": definition,
        "pose": pose,
        "axis_minimum": axis_minimum,
        "axis_maximum": axis_maximum,
        "active_fingerprint": fingerprint,
    }
    if active_tool_calibration is not None:
        scope["active_tool_calibration"] = active_tool_calibration
    return {
        "pose": pose,
        "axis_minimum": axis_minimum,
        "axis_maximum": axis_maximum,
        "fingerprint": fingerprint,
        "temperatures": temperatures,
        "framebuffer": framebuffer,
        "active_calibration_snapshot": active_snapshot,
        "active_tool_calibration": active_tool_calibration,
        "scope": scope,
        "applicability_hash": canonical_hash(scope),
    }


def _log_catalog_warnings(catalog: dict[str, Any]) -> None:
    for warning in catalog.get("warnings", []):
        warning_key = "|".join(
            str(warning.get(field, ""))
            for field in ("code", "publication_id", "fact_name", "fact_set_hash")
        )
        if warning_key in _LOGGED_CATALOG_WARNINGS:
            continue
        _LOGGED_CATALOG_WARNINGS.add(warning_key)
        _logger.warning("catalog: %s", warning["message"])


def _resolve_current_fact(
    requirement: str, fact_name: str, definition_version: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = rebuild_catalog(CALIBRATION_ROOT)
    _log_catalog_warnings(catalog)
    head = catalog.get("heads", {}).get(fact_name)
    if not isinstance(head, dict):
        raise VisionCalibrationError(f"missing current fact {fact_name}")
    if head["fact_set_hash"] in catalog.get("stale_fact_sets", {}):
        _logger.warning(
            "current fact %s is stale (fact_set_hash=%s)",
            fact_name,
            head["fact_set_hash"],
        )
        # raise VisionCalibrationError(f"current fact {fact_name} is stale")
    path = CALIBRATION_ROOT / head["fact_set_path"]
    fact_set = load_json(path)
    fact = next((item for item in fact_set["facts"] if item["name"] == fact_name), None)
    if fact is None or int(fact["definition_version"]) != definition_version:
        raise VisionCalibrationError(
            f"{fact_name} is not definition version {definition_version}"
        )
    return (
        {
            "requirement": requirement,
            "fact_name": fact_name,
            "fact_definition_version": definition_version,
            "fact_set_hash": fact_set["fact_set_hash"],
            "fact_set_path": head["fact_set_path"],
        },
        fact,
    )


def _load_bound_fact(binding: dict[str, Any]) -> Any:
    """Load a fact value directly from the fact_set_path stored in a manifest binding.

    Preferred over re-resolving the catalog head for compute jobs, where
    determinism requires using the exact fact that was bound at job creation.
    """
    path = CALIBRATION_ROOT / binding["fact_set_path"]
    fact_set = load_json(path)
    fact = next(
        (f for f in fact_set["facts"] if f["name"] == binding["fact_name"]), None
    )
    if fact is None:
        raise VisionCalibrationError(
            f"bound fact {binding['fact_name']} not found in {path}"
        )
    return fact["value"]


def _canonical_gcode(gcode: str) -> str:
    return HASH_RE.sub(lambda match: f"{match.group('name')}={HASH_PLACEHOLDER}", gcode)


def _gcode_hash(gcode: str) -> str:
    return canonical_hash(_canonical_gcode(gcode))


def _light_lines(pixels: dict[str, float]) -> list[str]:
    lines = ["VISION_LIGHT_OFF"]
    for index in range(1, 9):
        value = float(pixels[str(index)])
        if value > 0:
            lines.append(
                f"SET_LED LED=vision_light INDEX={index} "
                f"RED={value:.4f} GREEN={value:.4f} BLUE={value:.4f}"
            )
    return lines


def _capture_line(job_id: str, frame: dict[str, Any], *, tool: str) -> str:
    return (
        f"VISION_CAPTURE_SYNC JOB={job_id} SEQ={frame['seq']} "
        f"FRAME={frame['frame']} CAMERA=nozzle_cam "
        f"PROFILE={frame['profile']} TOOL={tool}"
    )


def _gcode(
    job_id: str,
    manifest_hash: str,
    gcode_hash: str,
    manifest: dict[str, Any],
    definition: dict[str, Any],
) -> str:
    if manifest["job_type"] in TOOL_XY_JOBS:
        return build_tool_xy_gcode(
            job_id,
            manifest_hash,
            gcode_hash,
            manifest,
            definition,
        )
    pose = manifest["motion"]["resolved_pose"]
    feedrate = float(definition.get("velocity_mm_s", 60.0)) * 60.0
    lines = [
        f"; vision calibration job {job_id}",
        "G28",
        "G90",
        (
            f"VISION_JOB_BEGIN JOB={job_id} "
            f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
        ),
    ]
    job_type = manifest["job_type"]
    frames = manifest["frames"]
    if job_type in {BED_FIDUCIAL_METRIC_JOB, BED_TAB_CORNER_JOB}:
        profile = frames[0]["profile"]
        lines.extend(
            [
                f"VISION_PROFILE CAMERA=nozzle_cam PROFILE={profile}",
                *_light_lines(frames[0]["light_pixels"]),
                "T0",
                f"G1 Z{pose['z_mm']:.6f} F{feedrate:.3f}",
                (
                    f"G1 X{pose['x_mm']:.6f} Y{pose['y_base_mm']:.6f} "
                    f"F{feedrate:.3f}"
                ),
            ]
        )
        last_y = None
        for frame in frames:
            y_mm = float(frame["commanded_position_mm"][1])
            if last_y != y_mm:
                lines.append(f"G1 Y{y_mm:.6f} F{feedrate:.3f}")
                last_y = y_mm
            lines.extend(
                [
                    "M400",
                    f"G4 P{int(definition['settle_ms'])}",
                    _capture_line(job_id, frame, tool="T0"),
                ]
            )
    else:
        lines.extend(
            [
                f"VISION_PROFILE CAMERA=nozzle_cam PROFILE={definition['profile']}",
                definition["light_macro"],
            ]
        )
        current_tool = None
        current_z = None
        current_y = None
        for frame in frames:
            tool = frame["tool"]
            if tool != current_tool:
                lines.extend(
                    [
                        (
                            f"G1 Z{pose['safe_tool_change_z_mm']:.6f} "
                            f"F{feedrate:.3f}"
                        ),
                        tool,
                        (
                            f"G1 Z{pose['safe_tool_change_z_mm']:.6f} "
                            f"F{feedrate:.3f}"
                        ),
                        (
                            f"G1 Y{float(frame['commanded_position_mm'][1]):.6f} "
                            f"F{feedrate:.3f}"
                        ),
                        "M400",
                        f"G4 P{int(definition['tool_change_settle_ms'])}",
                    ]
                )
                current_tool = tool
                current_z = pose["safe_tool_change_z_mm"]
                current_y = float(frame["commanded_position_mm"][1])
            z_mm = float(frame["commanded_position_mm"][2])
            x_mm = float(frame["commanded_position_mm"][0])
            y_mm = float(frame["commanded_position_mm"][1])
            if current_z != z_mm:
                lines.append(f"G1 Z{z_mm:.6f} F{feedrate:.3f}")
                current_z = z_mm
            if current_y != y_mm:
                lines.append(f"G1 Y{y_mm:.6f} F{feedrate:.3f}")
                current_y = y_mm
            lines.extend(
                [
                    f"G1 X{x_mm:.6f} F{feedrate:.3f}",
                    "M400",
                    f"G4 P{int(definition['settle_ms'])}",
                    _capture_line(job_id, frame, tool=tool),
                ]
            )
        lines.extend(
            [
                (f"G1 Z{pose['safe_tool_change_z_mm']:.6f} " f"F{feedrate:.3f}"),
                "T0",
                (f"G1 Z{pose['safe_tool_change_z_mm']:.6f} " f"F{feedrate:.3f}"),
            ]
        )
    lines.extend(
        [
            f"VISION_JOB_END JOB={job_id} EXPECTED_FRAMES={len(frames)}",
            "VISION_LIGHT_OFF",
            "",
        ]
    )
    return "\n".join(lines)


def _update_state(job_dir: Path, **values: Any) -> dict[str, Any]:
    path = job_dir / "state.json"
    state = load_json(path) if path.exists() else {}
    state.update(values)
    state["updated_at_utc"] = utc_now()
    atomic_write_json(path, state)
    return state


def _metric_x_axis_at_capture(
    metric: dict[str, Any],
    image_x_axis: list[float],
    capture_y_mm: float,
) -> tuple[list[float], list[float], dict[str, Any]]:
    models = metric["image_x_axis_candidate_models"]
    target = np.asarray(image_x_axis, dtype=np.float64)
    evaluated = [
        np.asarray(model["reference_vector_px_per_mm"], dtype=np.float64)
        + np.asarray(
            model["capture_y_slope_px_per_mm_per_mm"],
            dtype=np.float64,
        )
        * (float(capture_y_mm) - float(model["reference_capture_y_mm"]))
        for model in models
    ]
    selected_index = max(
        range(len(evaluated)),
        key=lambda index: float(np.dot(evaluated[index], target)),
    )
    patch_vector = metric["patch_x_axis_candidates_patch_mm_per_printer_mm"][
        selected_index
    ]
    return (
        np.asarray(patch_vector, dtype=np.float64).tolist(),
        evaluated[selected_index].tolist(),
        models[selected_index],
    )


def _bed_fiducial_printer_xy_mapping(
    *,
    metric: dict[str, Any],
    partial: dict[str, Any],
    image_x_axis: list[float],
    patch_points_mm: list[list[float]],
    capture_y_mm: float,
) -> dict[str, Any]:
    patch_x, image_x_at_capture, image_x_model = _metric_x_axis_at_capture(
        metric,
        image_x_axis,
        capture_y_mm,
    )
    patch_y = np.asarray(
        metric["patch_y_vector_per_printer_y_mm"],
        dtype=np.float64,
    )
    printer_to_patch = np.column_stack(
        (
            np.asarray(patch_x, dtype=np.float64),
            patch_y,
        )
    )
    if not math.isfinite(float(np.linalg.cond(printer_to_patch))):
        raise VisionCalibrationError("resolved patch/printer basis is singular")
    corner_patch = np.asarray(partial["corner_patch_xy_mm"], dtype=np.float64)
    corner_printer = np.asarray(
        partial["corner_printer_xyz_mm"][:2],
        dtype=np.float64,
    )
    patch_to_printer = np.linalg.inv(printer_to_patch)
    patch_origin = corner_printer - patch_to_printer @ corner_patch
    fiducial_centers = [
        (
            corner_printer
            + patch_to_printer @ (np.asarray(point, dtype=np.float64) - corner_patch)
        ).tolist()
        for point in patch_points_mm
    ]
    reference = np.mean(
        np.asarray(fiducial_centers, dtype=np.float64),
        axis=0,
    )
    return {
        "corner_patch_xy_mm": corner_patch.tolist(),
        "corner_printer_xy_mm": corner_printer.tolist(),
        "patch_x_vector_per_printer_x_mm": patch_x,
        "patch_y_vector_per_printer_y_mm": patch_y.tolist(),
        "printer_to_patch_xy_matrix": printer_to_patch.tolist(),
        "patch_to_printer_xy_matrix": patch_to_printer.tolist(),
        "patch_origin_printer_xy_mm": patch_origin.tolist(),
        "fiducial_center_printer_xy_mm": fiducial_centers,
        "fiducial_reference_printer_xy_mm": reference.tolist(),
        "fiducial_x_vector_model_px_per_mm": image_x_model,
        "fiducial_x_vector_at_red_capture_px_per_mm": image_x_at_capture,
        "red_capture_y_mm": float(capture_y_mm),
    }


def prepare_job(
    name: str,
    *,
    job_type: str,
    expected_fingerprint: str | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _logger.info(f"preparing job of type {job_type} with name {name}")
    registry = _load_registry()
    definition = json.loads(json.dumps(registry["job_types"][job_type]))
    input_facts = []
    input_values = {}
    for requirement in definition["requires"]:
        binding, fact = _resolve_current_fact(
            requirement["requirement"],
            requirement["fact_name"],
            int(requirement["fact_definition_version"]),
        )
        input_facts.append(binding)
        input_values[requirement["requirement"]] = fact["value"]
    resolved = _preflight(
        status or query_printer_status(),
        job_type,
        definition,
        expected_fingerprint,
    )
    pose = resolved["pose"]
    tool_xy_prepared = None
    if job_type in TOOL_XY_JOBS:
        try:
            tool_xy_prepared = prepare_tool_xy_measurement(
                definition,
                input_values=input_values,
                resolved=resolved,
            )
        except ToolXYError as exc:
            raise VisionCalibrationError(str(exc)) from None
        pose["capture_y_mm"] = float(tool_xy_prepared["reference"]["capture_y_mm"])
        pose["capture_z_mm"] = float(tool_xy_prepared["reference"]["commanded_z_mm"])
    resolved["scope"]["input_fact_hashes"] = {
        item["requirement"]: item["fact_set_hash"] for item in input_facts
    }
    resolved["applicability_hash"] = canonical_hash(resolved["scope"])
    job_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + _sanitize(name)
    )
    job_dir = CALIBRATION_ROOT / "jobs" / job_id
    if job_dir.exists():
        raise VisionCalibrationError(f"job already exists: {job_id}")
    frames = []
    if job_type == BED_FIDUCIAL_METRIC_JOB:
        for seq, offset in enumerate(definition["y_offsets_mm"]):
            frames.append(
                {
                    "seq": seq,
                    "frame": f"metric_y_{seq:02d}_{int(offset):02d}mm",
                    "camera": "nozzle_cam",
                    "profile": definition["profile"],
                    "tool": "T0",
                    "light_pixels": definition["light_pixels"],
                    "y_offset_mm": offset,
                    "pass": "forward" if seq < 3 else "reverse",
                    "commanded_position_mm": [
                        pose["x_mm"],
                        pose["y_base_mm"] + float(offset),
                        pose["z_mm"],
                    ],
                }
            )
    elif job_type == BED_TAB_CORNER_JOB:
        offset = float(definition["capture_y_offset_mm"])
        for seq in range(int(definition["duplicate_count"])):
            frames.append(
                {
                    "seq": seq,
                    "frame": f"corner_duplicate_{seq:02d}",
                    "camera": "nozzle_cam",
                    "profile": definition["profile"],
                    "tool": "T0",
                    "light_pixels": definition["light_pixels"],
                    "duplicate_index": seq,
                    "discard_fresh_frames": int(definition["discard_fresh_frames"]),
                    "commanded_position_mm": [
                        pose["x_mm"],
                        pose["y_base_mm"] + offset,
                        pose["z_mm"],
                    ],
                }
            )
    elif job_type == RED_MARKER_X_JOB:
        for tool in ("T0", "T1"):
            for x_mm in definition["x_positions_mm"]:
                seq = len(frames)
                frames.append(
                    {
                        "seq": seq,
                        "frame": f"{seq:02d}_{tool.lower()}_x{int(x_mm)}",
                        "camera": "nozzle_cam",
                        "profile": definition["profile"],
                        "tool": tool,
                        "x_mm": x_mm,
                        "discard_fresh_frames": 1,
                        "commanded_position_mm": [
                            float(x_mm),
                            pose["capture_y_mm"],
                            pose["capture_z_mm"],
                        ],
                    }
                )
    elif job_type == ROUGH_X_VERIFY_JOB:
        bed_tab_x = float(
            input_values["partial_bed_coordinate_system"]["corner_printer_xyz_mm"][0]
        )
        command_x = bed_tab_x + float(definition["verification_offset_x_mm"])
        definition["command_x_mm"] = command_x
        for tool in ("T0", "T1"):
            seq = len(frames)
            frames.append(
                {
                    "seq": seq,
                    "frame": f"{seq:02d}_{tool.lower()}_x{command_x:.3f}".replace(
                        ".", "p"
                    ),
                    "camera": "nozzle_cam",
                    "profile": definition["profile"],
                    "tool": tool,
                    "x_mm": command_x,
                    "discard_fresh_frames": 1,
                    "commanded_position_mm": [
                        command_x,
                        pose["capture_y_mm"],
                        pose["capture_z_mm"],
                    ],
                }
            )
    elif job_type == EDDY_FIDUCIAL_XZ_JOB:
        x_positions = [float(item) for item in definition["x_positions_mm"]]
        for row_index, z_value in enumerate(definition["z_positions_mm"]):
            z_mm = float(z_value)
            row = x_positions if row_index % 2 == 0 else list(reversed(x_positions))
            for x_mm in row:
                seq = len(frames)
                frames.append(
                    {
                        "seq": seq,
                        "frame": f"{seq:02d}_eddy_x{x_mm:.3f}_z{z_mm:.3f}".replace(
                            ".", "p"
                        ),
                        "camera": "nozzle_cam",
                        "profile": definition["profile"],
                        "tool": "T0",
                        "x_mm": x_mm,
                        "z_mm": z_mm,
                        "discard_fresh_frames": int(definition["discard_fresh_frames"]),
                        "commanded_position_mm": [
                            x_mm,
                            pose["capture_y_mm"],
                            z_mm,
                        ],
                    }
                )
    elif job_type in FINE_NOZZLE_XZ_JOBS:
        partial = input_values["partial_bed_coordinate_system"]
        x_axis = input_values["image_x_axis_z2"]["axis_vector_px_per_mm"]
        bed_tab_x = float(partial["corner_printer_xyz_mm"][0])
        corner_at_capture = np.asarray(partial["corner_pixel_xy_px"]) + np.asarray(
            partial["image_y_axis_vector_px_per_mm"]
        ) * (
            float(definition["capture_y_mm"])
            - float(partial["corner_pixel_capture_y_mm"])
        )
        offsets = [float(item) for item in definition["x_offsets_from_bed_tab_mm"]]
        full_z = [float(item) for item in definition["full_row_z_mm"]]
        tool = str(definition["tool"])
        marker = input_values[f"{tool.lower()}_red_marker_offset"]
        for row_index, z_mm in enumerate(full_z):
            row = offsets if row_index % 2 == 0 else list(reversed(offsets))
            for offset in row:
                x_mm = bed_tab_x + offset
                seq = len(frames)
                expected_marker = corner_at_capture + np.asarray(x_axis) * (
                    float(marker["offset_mm"])
                    + x_mm
                    - float(marker["reference_commanded_x_mm"])
                )
                frames.append(
                    {
                        "seq": seq,
                        "frame": (
                            f"{seq:02d}_{tool.lower()}_" f"x{x_mm:.3f}_z{z_mm:.3f}"
                        ).replace(".", "p"),
                        "camera": "nozzle_cam",
                        "profile": definition["profile"],
                        "tool": tool,
                        "x_offset_from_bed_tab_mm": offset,
                        "x_mm": x_mm,
                        "z_mm": z_mm,
                        "y_mm": pose["capture_y_mm"],
                        "expected_marker_pixel_px": expected_marker.tolist(),
                        "discard_fresh_frames": 1,
                        "commanded_position_mm": [
                            x_mm,
                            pose["capture_y_mm"],
                            z_mm,
                        ],
                    }
                )
    elif job_type in TOOL_XY_JOBS:
        assert tool_xy_prepared is not None
        frames = tool_xy_prepared["frames"]
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": job_type,
        "definition_version": 1,
        "created_at_utc": utc_now(),
        "camera": "nozzle_cam",
        "localizer": definition["localizer"],
        "publish_on_accept": True,
        "frame_count": len(frames),
        "frames": frames,
        "input_facts": input_facts,
        "applicability": resolved["scope"],
        "applicability_hash": resolved["applicability_hash"],
        "provenance": {
            "active_printer_fingerprint": resolved["fingerprint"],
            "registry_sha256": sha256_file(REGISTRY_PATH),
            "profile_file_sha256": sha256_file(PROFILE_PATH),
            "priors": _prior_provenance(job_type),
            "preflight_temperatures": resolved["temperatures"],
            "preflight_framebuffer": resolved["framebuffer"],
        },
        "gcode_file": "acquisition.gcode",
        "gcode_hash": HASH_PLACEHOLDER,
        "manifest_hash": HASH_PLACEHOLDER,
    }

    if not _is_compute_only_job_type(job_type):
        manifest["motion"] = {
            "velocity_mm_s": float(definition.get("velocity_mm_s", 60.0)),
            "settle_ms": int(definition["settle_ms"]),
            "resolved_pose": pose,
            "axis_minimum": resolved["axis_minimum"],
            "axis_maximum": resolved["axis_maximum"],
            "no_implicit_homing": True,
            "minimum_commanded_z_mm": min(
                float(frame["commanded_position_mm"][2]) for frame in frames
            ),
        }

    if job_type in {
        RED_MARKER_X_JOB,
        *FINE_NOZZLE_XZ_JOBS,
    }:
        manifest["active_calibration_snapshot"] = resolved[
            "active_calibration_snapshot"
        ]
    if job_type == RED_MARKER_X_JOB:
        partial = input_values["partial_bed_coordinate_system"]
        manifest["red_marker_reference"] = {
            "corner_pixel_xy_px": partial["corner_pixel_xy_px"],
            "corner_pixel_capture_y_mm": partial["corner_pixel_capture_y_mm"],
            "corner_printer_xyz_mm": partial["corner_printer_xyz_mm"],
            "image_y_axis_vector_px_per_mm": partial["image_y_axis_vector_px_per_mm"],
            "capture_y_mm": float(definition["capture_y_mm"]),
            "capture_z_mm": float(definition["capture_z_mm"]),
        }
    elif job_type == ROUGH_X_VERIFY_JOB:
        partial = input_values["partial_bed_coordinate_system"]
        x_axis = input_values["image_x_axis"]["axis_vector_px_per_mm"]
        active = input_values["rough_x_active_snapshot"]
        manifest["verification_reference"] = {
            "command_x_mm": definition["command_x_mm"],
            "expected_offset_mm": definition["verification_offset_x_mm"],
            "corner_pixel_xy_px": partial["corner_pixel_xy_px"],
            "corner_pixel_capture_y_mm": partial["corner_pixel_capture_y_mm"],
            "corner_printer_xyz_mm": partial["corner_printer_xyz_mm"],
            "image_y_axis_vector_px_per_mm": partial["image_y_axis_vector_px_per_mm"],
            "image_x_axis_vector_px_per_mm": x_axis,
            "capture_y_mm": float(definition["capture_y_mm"]),
            "capture_z_mm": float(definition["capture_z_mm"]),
            "active_x_endstops_mm": {
                "t0_x_endstop_mm": active["t0_applied_x_endstop_mm"],
                "t1_x_endstop_mm": active["t1_applied_x_endstop_mm"],
            },
        }
    elif job_type in FINE_NOZZLE_XZ_JOBS:
        metric = input_values["bed_metric"]
        partial = input_values["partial_bed_coordinate_system"]
        mapping = input_values["bed_fiducial_printer_xy_mapping"]
        x_axis = input_values["image_x_axis_z2"]["axis_vector_px_per_mm"]
        corner_at_capture = np.asarray(partial["corner_pixel_xy_px"]) + np.asarray(
            partial["image_y_axis_vector_px_per_mm"]
        ) * (
            float(definition["capture_y_mm"])
            - float(partial["corner_pixel_capture_y_mm"])
        )
        x_model = mapping["fiducial_x_vector_model_px_per_mm"]
        fiducial_x_at_capture = np.asarray(
            x_model["reference_vector_px_per_mm"],
            dtype=np.float64,
        ) + np.asarray(
            x_model["capture_y_slope_px_per_mm_per_mm"],
            dtype=np.float64,
        ) * (
            float(definition["capture_y_mm"]) - float(x_model["reference_capture_y_mm"])
        )
        fiducial_pixel_at_capture = np.mean(
            np.asarray(metric["reference_marker_centers_px"], dtype=np.float64),
            axis=0,
        ) + np.asarray(
            metric["image_y_axis_vector_px_per_mm"],
            dtype=np.float64,
        ) * (
            float(definition["capture_y_mm"]) - float(metric["reference_capture_y_mm"])
        )
        manifest["fine_reference"] = {
            "bed_tab_x_mm": partial["corner_printer_xyz_mm"][0],
            "fiducial_plane_printer_z_mm": CALIB.fiducial_z(),
            "fiducial_reference_printer_xy_mm": mapping[
                "fiducial_reference_printer_xy_mm"
            ],
            "fiducial_reference_pixel_at_fine_capture_px": fiducial_pixel_at_capture.tolist(),
            "fiducial_x_vector_at_fine_capture_px_per_mm": fiducial_x_at_capture.tolist(),
            "fiducial_x_vector_model_px_per_mm": x_model,
            "fine_capture_y_mm": float(definition["capture_y_mm"]),
            "image_y_axis_vector_px_per_mm": metric["image_y_axis_vector_px_per_mm"],
            "corner_pixel_at_fine_capture_px": corner_at_capture.tolist(),
            "coarse_image_x_axis_px_per_mm": x_axis,
        }
        manifest["acquisition_calibration"] = _acquisition_calibration_snapshot()
    elif job_type in TOOL_XY_JOBS:
        assert tool_xy_prepared is not None
        manifest["tool_xy_reference"] = tool_xy_prepared["reference"]
        manifest["acquisition_calibration"] = tool_xy_prepared[
            "active_tool_calibration"
        ]
    placeholder = _gcode(
        job_id, HASH_PLACEHOLDER, HASH_PLACEHOLDER, manifest, definition
    )
    manifest["gcode_hash"] = _gcode_hash(placeholder)
    manifest["manifest_hash"] = content_hash(manifest, "manifest_hash")
    final_gcode = _gcode(
        job_id,
        manifest["manifest_hash"],
        manifest["gcode_hash"],
        manifest,
        definition,
    )
    if _gcode_hash(final_gcode) != manifest["gcode_hash"]:
        raise VisionCalibrationError("generated G-code hash is unstable")
    validate_manifest(manifest)
    job_dir.mkdir(parents=True)
    (job_dir / "frames").mkdir()
    (job_dir / "analysis").mkdir()
    (job_dir / "acquisition.gcode").write_text(final_gcode, encoding="utf-8")
    atomic_write_json(job_dir / "manifest.json", manifest, immutable=True)
    _update_state(
        job_dir,
        schema="vision-calibration-job-state",
        schema_version=1,
        job_id=job_id,
        state="prepared",
        committed_frame_count=0,
    )
    GCODE_ROOT.mkdir(parents=True, exist_ok=True)
    gcode_path = GCODE_ROOT / f"{job_id}.gcode"
    shutil.copyfile(job_dir / "acquisition.gcode", gcode_path)
    rebuild_and_render()
    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "gcode_path": str(gcode_path),
        "manifest_hash": manifest["manifest_hash"],
        "gcode_hash": manifest["gcode_hash"],
        "review_url": f"/vision/calibration/jobs/{job_id}/",
    }


def _start_print(job_id: str) -> None:
    _moonraker_post("/printer/print/start", {"filename": f"vision_jobs/{job_id}.gcode"})


def _wait_for_acquisition(job_id: str, timeout: float) -> dict[str, Any]:
    path = CALIBRATION_ROOT / "jobs" / job_id / "state.json"
    deadline = time.monotonic() + timeout
    latest = {}
    while time.monotonic() < deadline:
        latest = load_json(path)
        if latest.get("state") in {"acquired", "failed"}:
            break
        time.sleep(0.25)
    if latest.get("state") != "acquired":
        raise VisionCalibrationError(
            f"acquisition ended in {latest.get('state')!r}: {latest}"
        )
    return latest


def _frame_integrity(
    manifest: dict[str, Any], job_dir: Path
) -> tuple[list[Path], list[dict[str, Any]]]:
    paths = []
    sidecars = []
    for frame in manifest["frames"]:
        image_path = job_dir / "frames" / f"{frame['frame']}.jpg"
        sidecar_path = job_dir / "frames" / f"{frame['frame']}.json"
        if not image_path.is_file() or not sidecar_path.is_file():
            raise VisionCalibrationError(f"missing frame {frame['frame']}")
        sidecar = load_json(sidecar_path)
        if sidecar.get("sha256") != sha256_file(image_path):
            raise VisionCalibrationError(f"frame hash mismatch {frame['frame']}")
        if sidecar.get("job_seq") != frame["seq"]:
            raise VisionCalibrationError(f"frame sequence mismatch {frame['frame']}")
        profile_names = sidecar.get("camera_profile", {}).get("profile_names", [])
        if frame["profile"] not in profile_names:
            raise VisionCalibrationError(
                f"frame {frame['frame']} lacks profile {frame['profile']}"
            )
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise VisionCalibrationError(f"frame {frame['frame']} is invalid JPEG")
        if [image.shape[1], image.shape[0]] != [
            int(sidecar["width"]),
            int(sidecar["height"]),
        ]:
            raise VisionCalibrationError(f"frame dimensions mismatch {frame['frame']}")
        paths.append(image_path)
        sidecars.append(sidecar)
    return paths, sidecars


def _analysis_run_id(manifest: dict[str, Any]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{timestamp}-{manifest['manifest_hash'][7:17]}"


def _active_input_facts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in manifest["input_facts"]
        if item["fact_name"] not in RETIRED_PRIOR_FACT_NAMES
    ]


def _dependencies(manifest: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "fact_name": item["fact_name"],
            "fact_set_hash": item["fact_set_hash"],
        }
        for item in _active_input_facts(manifest)
    ]


def _diagnostic_fields(
    value: dict[str, Any], coordinate_fields: set[str]
) -> list[dict[str, str]]:
    return [
        {
            "field": field,
            "role": (
                "coordinate_system" if field in coordinate_fields else "diagnostic"
            ),
        }
        for field in value
    ]


def _fact(
    name: str,
    role: str,
    value: dict[str, Any],
    dependencies: list[dict[str, str]],
    coordinate_fields: set[str] = frozenset(),
) -> dict[str, Any]:
    return {
        "name": name,
        "definition_version": 1,
        "role": role,
        "dependencies": dependencies,
        "value_items": [
            {
                "field": field,
                "role": (
                    "coordinate_system" if field in coordinate_fields else "diagnostic"
                ),
            }
            for field in value
        ],
        "value": value,
    }


def _homography_inverse_point(
    homography: list[list[float]], point: list[float]
) -> list[float]:
    inverse = np.linalg.inv(np.asarray(homography, dtype=np.float64))
    result = inverse @ np.asarray([point[0], point[1], 1.0])
    return (result[:2] / result[2]).tolist()


def analyze_job(job_id: str) -> dict[str, Any]:
    job_dir = CALIBRATION_ROOT / "jobs" / _sanitize(job_id)
    manifest = validate_manifest(load_json(job_dir / "manifest.json"))
    state = load_json(job_dir / "state.json")
    if state.get("state") not in {"acquired", "analyzed", "rejected"}:
        raise VisionCalibrationError(
            f"job state {state.get('state')} cannot be analyzed"
        )

    _logger.info(f"analyzing job {job_id} of type {manifest['job_type']}")
    frame_paths, sidecars = _frame_integrity(manifest, job_dir)
    analysis_run_id = _analysis_run_id(manifest)
    analysis_dir = job_dir / "analysis" / analysis_run_id
    staging = analysis_dir.with_name("." + analysis_run_id + ".tmp")
    if analysis_dir.exists() or staging.exists():
        raise VisionCalibrationError(f"analysis run already exists: {analysis_run_id}")
    staging.mkdir(parents=True)
    artifact_dir = staging / "artifacts"
    try:
        job_type = manifest["job_type"]
        if job_type == BED_FIDUCIAL_METRIC_JOB:
            details = analyze_metric(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                patch_points_mm=CALIB.fiducial_centers(),
            )
        elif job_type == BED_TAB_CORNER_JOB:
            metric = _resolve_current_fact(
                "bed_metric",
                "camera.nozzle_cam.bed_fiducial.local_metric_model",
                1,
            )[1]["value"]
            capture_y = float(manifest["frames"][0]["commanded_position_mm"][1])
            expected_marker_centers = np.asarray(
                metric["reference_marker_centers_px"], dtype=np.float64
            ) + np.asarray(
                metric["image_y_axis_vector_px_per_mm"], dtype=np.float64
            ) * (
                capture_y - float(metric["reference_capture_y_mm"])
            )
            details = analyze_corner(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                expected_marker_centers_px=expected_marker_centers.tolist(),
            )
        elif job_type == RED_MARKER_X_JOB:
            details = analyze_red_marker_x_sweep(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                reference=manifest["red_marker_reference"],
                localizer=manifest["localizer"],
            )
        elif job_type == ROUGH_X_VERIFY_JOB:
            details = analyze_rough_x_verification(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                reference=manifest["verification_reference"],
                localizer=manifest["localizer"],
            )
        elif job_type == EDDY_FIDUCIAL_XZ_JOB:
            details = analyze_eddy_fiducial_xz(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                localizer=manifest["localizer"],
            )
        elif job_type in FINE_NOZZLE_XZ_JOBS:
            details = analyze_fine_nozzle_xz(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                reference=manifest["fine_reference"],
                acquisition_calibration=manifest.get("acquisition_calibration"),
            )
        elif job_type in TOOL_XY_JOBS:
            details = analyze_tool_xy_measurement(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                reference=manifest["tool_xy_reference"],
                acquisition_calibration=manifest["acquisition_calibration"],
            )
        elif job_type == EDDY_T0_XYZ_OFFSET_JOB:
            bindings = {item["requirement"]: item for item in manifest["input_facts"]}
            details = analyze_eddy_xyz_offset(
                t0_projection=_load_bound_fact(bindings["t0_projection_model"]),
                eddy_positions=_load_bound_fact(bindings["eddy_xz_image_positions"]),
            )
        elif job_type == IDEX_T0_T1_XYZ_OFFSET_JOB:
            bindings = {item["requirement"]: item for item in manifest["input_facts"]}
            details = analyze_idex_xyz_offset(
                artifact_dir,
                t0_projection=_load_bound_fact(bindings["t0_projection_model"]),
                t1_projection=_load_bound_fact(bindings["t1_projection_model"]),
                eddy_positions=_load_bound_fact(bindings["eddy_xz_image_positions"]),
            )
        else:
            raise VisionCalibrationError(f"unsupported job type: {job_type}")
        for artifact in details.get("artifacts", {}).values():
            path = Path(artifact["path"])
            artifact["path"] = str(analysis_dir / path.relative_to(staging))
        state_name = "accepted" if details["accepted"] else "rejected"
        analysis = {
            "schema": ANALYSIS_SCHEMA,
            "schema_version": 1,
            "analysis_run_id": analysis_run_id,
            "job_id": manifest["job_id"],
            "job_type": job_type,
            "definition_version": 1,
            "created_at_utc": utc_now(),
            "state": state_name,
            "manifest_hash": manifest["manifest_hash"],
            "input_bindings": {
                "frames": [
                    {
                        "seq": frame["seq"],
                        "image_sha256": sidecar["sha256"],
                        "sidecar_sha256": sha256_file(
                            job_dir / "frames" / f"{frame['frame']}.json"
                        ),
                    }
                    for frame, sidecar in zip(manifest["frames"], sidecars)
                ],
                "dependencies": _active_input_facts(manifest),
            },
            "diagnostics": details,
            "fact_set_path": "fact_set.json" if details["accepted"] else None,
            "analysis_hash": "",
        }
        analysis["analysis_hash"] = content_hash(analysis, "analysis_hash")
        facts = []
        dependencies = _dependencies(manifest)
        width = int(sidecars[0]["width"]) if sidecars else 0
        height = int(sidecars[0]["height"]) if sidecars else 0
        if details["accepted"]:
            if job_type == BED_FIDUCIAL_METRIC_JOB:
                detection_records_keys = ["centers_px", "commanded_position_mm"]

                value = {
                    "image_y_axis_vector_px_per_mm": details[
                        "image_y_axis_vector_px_per_mm"
                    ],
                    "patch_to_image_homography": details["patch_to_image_homography"],
                    "patch_reference_center_xy_mm": details[
                        "patch_reference_center_xy_mm"
                    ],
                    "patch_y_vector_per_printer_y_mm": details[
                        "patch_y_vector_per_printer_y_mm"
                    ],
                    "patch_x_axis_candidates_patch_mm_per_printer_mm": details[
                        "patch_x_axis_candidates_patch_mm_per_printer_mm"
                    ],
                    "image_x_axis_candidate_models": details[
                        "image_x_axis_candidate_models"
                    ],
                    "reference_marker_centers_px": details[
                        "reference_marker_centers_px"
                    ],
                    "reference_capture_y_mm": details["reference_capture_y_mm"],
                    "image_dimensions_px": [width, height],
                    "detection_records": [
                        {key: record[key] for key in detection_records_keys}
                        for record in details["detection_records"]
                        if record is not None
                    ],
                    "quality": {
                        key: details[key]
                        for key in (
                            "usable_frame_count",
                            "fit_rms_px",
                            "duplicate_disagreement_px",
                            "image_x_vector_capture_y_fit_rms_px_per_mm",
                            "warnings",
                        )
                    },
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.bed_fiducial.local_metric_model",
                        "coordinate_system",
                        value,
                        dependencies,
                        {
                            "image_y_axis_vector_px_per_mm",
                            "patch_to_image_homography",
                            "patch_reference_center_xy_mm",
                            "patch_y_vector_per_printer_y_mm",
                            "patch_x_axis_candidates_patch_mm_per_printer_mm",
                            "image_x_axis_candidate_models",
                            "reference_marker_centers_px",
                            "reference_capture_y_mm",
                        },
                    )
                ]
            elif job_type == BED_TAB_CORNER_JOB:
                input_values = {
                    item["requirement"]: _resolve_current_fact(
                        item["requirement"],
                        item["fact_name"],
                        item["fact_definition_version"],
                    )[1]["value"]
                    for item in _active_input_facts(manifest)
                }
                metric = input_values["bed_metric"]
                corner_capture_y = float(
                    manifest["frames"][0]["commanded_position_mm"][1]
                )
                corner_at_metric_reference = np.asarray(
                    details["corner_pixel_xy_px"], dtype=np.float64
                ) - np.asarray(
                    metric["image_y_axis_vector_px_per_mm"],
                    dtype=np.float64,
                ) * (
                    corner_capture_y - float(metric["reference_capture_y_mm"])
                )
                corner_patch = _homography_inverse_point(
                    metric["patch_to_image_homography"],
                    corner_at_metric_reference.tolist(),
                )
                value = {
                    "corner_pixel_xy_px": details["corner_pixel_xy_px"],
                    "corner_pixel_capture_y_mm": corner_capture_y,
                    "corner_pixel_at_metric_reference_px": corner_at_metric_reference.tolist(),
                    "corner_printer_xyz_mm": CALIB.bed_corner(),
                    "corner_patch_xy_mm": corner_patch,
                    "image_y_axis_vector_px_per_mm": metric[
                        "image_y_axis_vector_px_per_mm"
                    ],
                    "fiducial_plane_printer_z_mm": CALIB.fiducial_z(),
                    "observed_patch_marker_centers_px": details[
                        "patch_marker_centers_px"
                    ],
                    "quality": {
                        "usable_frame_count": details["usable_frame_count"],
                        "repeatability_max_px": details["repeatability_max_px"],
                        "warnings": details["warnings"],
                    },
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.partial_bed_coordinate_system",
                        "coordinate_system",
                        value,
                        dependencies,
                        {
                            "corner_pixel_xy_px",
                            "corner_pixel_capture_y_mm",
                            "corner_printer_xyz_mm",
                            "corner_patch_xy_mm",
                            "image_y_axis_vector_px_per_mm",
                            "fiducial_plane_printer_z_mm",
                            "observed_patch_marker_centers_px",
                        },
                    )
                ]
            elif job_type == RED_MARKER_X_JOB:
                input_values = {
                    item["requirement"]: _resolve_current_fact(
                        item["requirement"],
                        item["fact_name"],
                        item["fact_definition_version"],
                    )[1]["value"]
                    for item in _active_input_facts(manifest)
                }
                diagnostic = {
                    "camera": "nozzle_cam",
                    "image_dimensions_px": [width, height],
                    "quality": {
                        key: details[key]
                        for key in (
                            "accepted_x_mm",
                            "tool_axis_vectors_px_per_mm",
                            "tool_fit_rms_px",
                            "tool_minimum_correlation",
                            "tool_scale_delta_fraction",
                            "tool_angle_delta_deg",
                            "cross_tool_minimum_correlation",
                            "warnings",
                        )
                    },
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                common_x = details["common_commanded_x_mm"]
                mapping = _bed_fiducial_printer_xy_mapping(
                    metric=input_values["bed_metric"],
                    partial=input_values["partial_bed_coordinate_system"],
                    image_x_axis=details["common_axis_vector_px_per_mm"],
                    patch_points_mm=CALIB.fiducial_centers(),
                    capture_y_mm=float(
                        manifest["red_marker_reference"]["capture_y_mm"]
                    ),
                )
                facts = [
                    _fact(
                        "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2",
                        "coordinate_system",
                        {
                            "axis_vector_px_per_mm": details[
                                "common_axis_vector_px_per_mm"
                            ],
                            **diagnostic,
                        },
                        dependencies,
                        {"axis_vector_px_per_mm"},
                    ),
                    _fact(
                        "tool.t0.red_marker_to_bed_tab_x_mm",
                        "coordinate_system",
                        {
                            "offset_mm": details["t0_red_marker_to_bed_tab_x_mm"],
                            "reference_commanded_x_mm": common_x,
                            **diagnostic,
                        },
                        dependencies,
                        {"offset_mm", "reference_commanded_x_mm"},
                    ),
                    _fact(
                        "tool.t1.red_marker_to_bed_tab_x_mm",
                        "coordinate_system",
                        {
                            "offset_mm": details["t1_red_marker_to_bed_tab_x_mm"],
                            "reference_commanded_x_mm": common_x,
                            **diagnostic,
                        },
                        dependencies,
                        {"offset_mm", "reference_commanded_x_mm"},
                    ),
                    _fact(
                        "camera.nozzle_cam.bed_fiducial.printer_xy_mapping",
                        "coordinate_system",
                        {
                            **mapping,
                            **diagnostic,
                        },
                        dependencies,
                        {
                            "corner_patch_xy_mm",
                            "corner_printer_xy_mm",
                            "patch_x_vector_per_printer_x_mm",
                            "patch_y_vector_per_printer_y_mm",
                            "printer_to_patch_xy_matrix",
                            "patch_to_printer_xy_matrix",
                            "patch_origin_printer_xy_mm",
                            "fiducial_center_printer_xy_mm",
                            "fiducial_reference_printer_xy_mm",
                            "fiducial_x_vector_model_px_per_mm",
                            "fiducial_x_vector_at_red_capture_px_per_mm",
                            "red_capture_y_mm",
                        },
                    ),
                ]
            elif job_type == ROUGH_X_VERIFY_JOB:
                value = {
                    "verified": True,
                    "verification_command_x_mm": details["verification_command_x_mm"],
                    "expected_offset_mm": details["expected_offset_mm"],
                    "t0_residual_mm": details["t0_residual_mm"],
                    "t1_residual_mm": details["t1_residual_mm"],
                    "marker_coincidence_residual_mm": details[
                        "marker_coincidence_residual_mm"
                    ],
                    "records": details["records"],
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                facts = [
                    _fact(
                        "calibration.rough_tool_x.verified",
                        "diagnostic",
                        value,
                        dependencies,
                    )
                ]
            elif job_type == EDDY_FIDUCIAL_XZ_JOB:
                value = {
                    "camera": "nozzle_cam",
                    "image_dimensions_px": details["image_dimensions_px"],
                    "positions": details["raw_positions"],
                    "detector_records": details["records"],
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.eddy_fiducial.xz_image_positions",
                        "diagnostic",
                        value,
                        dependencies,
                    )
                ]
            elif job_type in FINE_NOZZLE_XZ_JOBS:
                tool = str(manifest["frames"][0]["tool"])
                projection = {
                    "tool_models": details["models"],
                    "fiducial_reference_printer_xy_mm": details[
                        "fiducial_reference_printer_xy_mm"
                    ],
                    "fiducial_reference_pixel_at_fine_capture_px": details[
                        "fiducial_reference_pixel_at_fine_capture_px"
                    ],
                    "fiducial_x_vector_at_fine_capture_px_per_mm": details[
                        "fiducial_x_vector_at_fine_capture_px_per_mm"
                    ],
                    "fiducial_plane_printer_z_mm": details[
                        "fiducial_plane_printer_z_mm"
                    ],
                    "fine_capture_y_mm": details["fine_capture_y_mm"],
                    "image_y_axis_vector_px_per_mm": details[
                        "image_y_axis_vector_px_per_mm"
                    ],
                    "tip_tracking": details["tip_tracking"],
                    "vector_comparison_at_commanded_z0": details[
                        "vector_comparison_at_commanded_z0"
                    ],
                    "quality": {
                        "warnings": details["warnings"],
                    },
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.nozzle_tip."
                        f"{tool.lower()}_projection_model",
                        "coordinate_system",
                        projection,
                        dependencies,
                        {
                            "tool_models",
                            "fiducial_reference_printer_xy_mm",
                            "fiducial_reference_pixel_at_fine_capture_px",
                            "fiducial_x_vector_at_fine_capture_px_per_mm",
                            "fiducial_plane_printer_z_mm",
                            "fine_capture_y_mm",
                            "image_y_axis_vector_px_per_mm",
                        },
                    )
                ]
            elif job_type in TOOL_XY_JOBS:
                value = build_tool_xy_fact(
                    details,
                    acquisition_calibration=manifest["acquisition_calibration"],
                )
                facts = [
                    _fact(
                        f"tool.{details['tool'].lower()}.vision_xy_datum",
                        "coordinate_system",
                        value,
                        dependencies,
                        {"x_datum_mm", "y_datum_mm"},
                    )
                ]
            elif job_type == EDDY_T0_XYZ_OFFSET_JOB:
                value = {
                    "tool": "T0",
                    "offset_xyz_mm": details["offset_xyz_mm"],
                    "fit_rms_px": details["fit_rms_px"],
                    "max_error_px": details["max_error_px"],
                    "n_eddy_detections": details["n_eddy_detections"],
                    "nozzle_model_fit_rms_px": details["nozzle_model_fit_rms_px"],
                    "detection_residuals": details["detection_residuals"],
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.eddy_fiducial.t0_xyz_offset",
                        "coordinate_system",
                        value,
                        dependencies,
                        {"offset_xyz_mm"},
                    )
                ]
            elif job_type == IDEX_T0_T1_XYZ_OFFSET_JOB:
                value = {
                    "tool": "IDEX",
                    "t0_t1_xyz_offset": details["t0_t1_xyz_offset"],
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.t0_t1_xyz_offset",
                        "coordinate_system",
                        value,
                        dependencies,
                        {"t0_t1_xyz_offset"},
                    )
                ]
            else:
                raise VisionCalibrationError(
                    f"unsupported accepted job type: {job_type}"
                )
            fact_set = {
                "schema": FACT_SET_SCHEMA,
                "schema_version": 1,
                "fact_set_id": f"{manifest['job_id']}:{analysis_run_id}",
                "job_id": manifest["job_id"],
                "analysis_run_id": analysis_run_id,
                "analysis_hash": analysis["analysis_hash"],
                "created_at_utc": utc_now(),
                "accepted": True,
                "publication_eligible": True,
                "applicability_hash": manifest["applicability_hash"],
                "facts": facts,
                "provenance": {
                    "active_printer_fingerprint": manifest.get("provenance", {}).get(
                        "active_printer_fingerprint"
                    ),
                    "manifest_hash": manifest["manifest_hash"],
                    "priors": _prior_provenance(job_type),
                    "observations": details,
                },
                "fact_set_hash": "",
            }
            fact_set["fact_set_hash"] = content_hash(fact_set, "fact_set_hash")
            atomic_write_json(staging / "fact_set.json", fact_set, immutable=True)
        atomic_write_json(staging / "result.json", analysis, immutable=True)
        report = [
            f"# {job_type}",
            "",
            f"- Job: `{job_id}`",
            f"- Analysis: `{analysis_run_id}`",
            f"- State: **{state_name}**",
            f"- Frames: `{len(frame_paths)}`",
            "",
            "## Coordinate results",
            "",
            "```json",
            json.dumps(
                [fact["value"] for fact in facts] if facts else {},
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
            "## Warnings",
            "",
            *([f"- {item}" for item in details.get("warnings", [])] or ["- None"]),
            "",
            "## Rejection reasons",
            "",
            *([f"- {item}" for item in details.get("reasons", [])] or ["- None"]),
            "",
        ]
        (staging / "report.md").write_text("\n".join(report), encoding="utf-8")
        staging.replace(analysis_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _update_state(
        job_dir,
        state="analyzed" if details["accepted"] else "rejected",
        latest_analysis_run_id=analysis_run_id,
    )
    publication = None
    if details["accepted"]:
        publication = publish_fact_set(
            CALIBRATION_ROOT, manifest["job_id"], analysis_run_id
        )["publication"]
    rebuild_and_render()
    return {
        "job_id": job_id,
        "analysis_run_id": analysis_run_id,
        "state": state_name,
        "publication": publication,
        "review_url": (
            f"/vision/calibration/jobs/{job_id}/analysis/{analysis_run_id}/"
        ),
        "details": details,
    }


def compute_job(
    name: str,
    *,
    job_type: str,
) -> dict[str, Any]:
    """Create and immediately analyze a compute-only vision job (no image capture).

    The job manifest is written with zero frames and state is set directly to
    ``acquired`` — no gcode or printer motion is involved.  ``analyze_job`` is
    then called immediately and the full result is returned.
    """
    definition = validate_registry(load_json(REGISTRY_PATH))["job_types"][job_type]

    if not _is_compute_only_job_type(job_type):
        raise VisionCalibrationError(
            f"job type {job_type} is not a compute-only job type"
        )

    # Resolve required input facts.
    input_facts: list[dict[str, Any]] = []
    for item in definition["requires"]:
        req, _fact_obj = _resolve_current_fact(
            item["requirement"],
            item["fact_name"],
            item["fact_definition_version"],
        )
        input_facts.append(req)

    job_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + _sanitize(name)
    )
    job_dir = CALIBRATION_ROOT / "jobs" / _sanitize(job_id)
    if job_dir.exists():
        raise VisionCalibrationError(f"job already exists: {job_id}")

    # Applicability is fully determined by the bound input fact hashes.
    applicability_scope = {
        "camera": "nozzle_cam",
        "job_type": job_type,
        "input_fact_hashes": {
            item["requirement"]: item["fact_set_hash"] for item in input_facts
        },
    }
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": job_type,
        "definition_version": 1,
        "created_at_utc": utc_now(),
        "camera": "nozzle_cam",
        "localizer": definition["localizer"],
        "publish_on_accept": True,
        "frame_count": 0,
        "frames": [],
        "input_facts": input_facts,
        "applicability": applicability_scope,
        "applicability_hash": canonical_hash(applicability_scope),
        "manifest_hash": HASH_PLACEHOLDER,
    }
    manifest["manifest_hash"] = content_hash(manifest, "manifest_hash")
    validate_manifest(manifest)

    job_dir.mkdir(parents=True)
    (job_dir / "frames").mkdir()
    (job_dir / "analysis").mkdir()
    atomic_write_json(job_dir / "manifest.json", manifest, immutable=True)
    _update_state(
        job_dir,
        schema="vision-calibration-job-state",
        schema_version=1,
        job_id=job_id,
        state="acquired",
        committed_frame_count=0,
    )
    rebuild_and_render()
    analysis = analyze_job(job_id)
    return {"job_id": job_id, "analysis": analysis}


def acquire_job(
    name: str,
    *,
    job_type: str,
    expected_fingerprint: str | None = None,
    timeout: float = 300.0,
) -> dict[str, Any]:
    prepared = prepare_job(
        name,
        job_type=job_type,
        expected_fingerprint=expected_fingerprint,
    )
    _start_print(prepared["job_id"])
    state = _wait_for_acquisition(prepared["job_id"], timeout)
    rebuild_and_render()
    return {"prepared": prepared, "state": state}


def run_job(
    name: str,
    *,
    job_type: str,
    expected_fingerprint: str | None = None,
    timeout: float = 300.0,
) -> dict[str, Any]:

    if _is_compute_only_job_type(job_type):
        result = compute_job(name, job_type=job_type)

        return {"prepared": result, "analysis": result}

    else:
        acquired = acquire_job(
            name,
            job_type=job_type,
            expected_fingerprint=expected_fingerprint,
            timeout=timeout,
        )
        analysis = analyze_job(acquired["prepared"]["job_id"])
    return {"prepared": acquired["prepared"], "analysis": analysis}


def calculate_rough_x(
    *,
    old_t0_x_endstop_mm: float | None = None,
    old_t1_x_endstop_mm: float | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    t0_binding, t0 = _resolve_current_fact(
        "t0_marker", "tool.t0.red_marker_to_bed_tab_x_mm", 1
    )
    t1_binding, t1 = _resolve_current_fact(
        "t1_marker", "tool.t1.red_marker_to_bed_tab_x_mm", 1
    )
    printer_status = status or query_printer_status()
    settings = printer_status["configfile"]["settings"]
    active_t0 = _number(
        _settings(settings, "stepper_x"), "position_endstop", "stepper_x"
    )
    active_t1 = _number(
        _settings(settings, "dual_carriage"), "position_endstop", "dual_carriage"
    )
    candidate = calculate_rough_x_candidate(
        prior_xyz_mm=CALIB.bed_corner(),
        t0_marker_fact=t0["value"],
        t1_marker_fact=t1["value"],
        old_t0_x_endstop_mm=(
            active_t0 if old_t0_x_endstop_mm is None else old_t0_x_endstop_mm
        ),
        old_t1_x_endstop_mm=(
            active_t1 if old_t1_x_endstop_mm is None else old_t1_x_endstop_mm
        ),
    )
    candidate["active_before_or_current_mm"] = {"T0": active_t0, "T1": active_t1}
    candidate["source_facts"] = [t0_binding, t1_binding]
    candidate["source_priors_sha256"] = CALIB.priors_hash()
    candidate["active_config_fingerprint"] = str(
        printer_status["gcode_macro _IDEX_CONFIG_FINGERPRINT"]["source_sha256"]
    )
    return candidate


def record_rough_x_activation(
    *,
    old_t0_x_endstop_mm: float,
    old_t1_x_endstop_mm: float,
    expected_fingerprint: str | None = None,
) -> dict[str, Any]:
    candidate = calculate_rough_x(
        old_t0_x_endstop_mm=old_t0_x_endstop_mm,
        old_t1_x_endstop_mm=old_t1_x_endstop_mm,
    )
    active = candidate["active_before_or_current_mm"]
    if (
        expected_fingerprint
        and candidate["active_config_fingerprint"] != expected_fingerprint
    ):
        raise VisionCalibrationError("active fingerprint does not match deployment")
    for tool in ("T0", "T1"):
        expected = candidate["tools"][tool]["candidate_x_endstop_mm"]
        if abs(float(active[tool]) - float(expected)) > 0.0011:
            raise VisionCalibrationError(
                f"active {tool} endstop {active[tool]} != candidate {expected}"
            )
    value = {
        "bed_tab_x_mm": candidate["bed_tab_corner_xyz_mm"][0],
        "t0_old_x_endstop_mm": old_t0_x_endstop_mm,
        "t0_calculated_correction_mm": candidate["tools"]["T0"][
            "calculated_correction_mm"
        ],
        "t0_applied_x_endstop_mm": active["T0"],
        "t1_old_x_endstop_mm": old_t1_x_endstop_mm,
        "t1_calculated_correction_mm": candidate["tools"]["T1"][
            "calculated_correction_mm"
        ],
        "t1_applied_x_endstop_mm": active["T1"],
        "active_config_fingerprint": candidate["active_config_fingerprint"],
        "source_priors_sha256": candidate["source_priors_sha256"],
        "source_fact_set_hashes": {
            item["fact_name"]: item["fact_set_hash"]
            for item in candidate["source_facts"]
        },
    }
    dependencies = [
        {
            "fact_name": item["fact_name"],
            "fact_set_hash": item["fact_set_hash"],
        }
        for item in candidate["source_facts"]
    ]
    fact = _fact(
        "calibration.rough_tool_x.active_snapshot",
        "coordinate_system",
        value,
        dependencies,
        {
            "bed_tab_x_mm",
            "t0_old_x_endstop_mm",
            "t0_calculated_correction_mm",
            "t0_applied_x_endstop_mm",
            "t1_old_x_endstop_mm",
            "t1_calculated_correction_mm",
            "t1_applied_x_endstop_mm",
        },
    )
    activation = _publish_operation_fact_set(
        "rough_tool_x_activation",
        facts=[fact],
        provenance={
            "method": "verified_live_activation",
            "candidate": candidate,
            "source_priors_sha256": candidate["source_priors_sha256"],
        },
        applicability={
            "printer": "menderpi",
            "active_config_fingerprint": candidate["active_config_fingerprint"],
        },
    )
    return {"candidate": candidate, "activation": activation}


def _active_generated_calibration(status: dict[str, Any]) -> dict[str, float]:
    settings = status["configfile"]["settings"]
    tool_state = status.get("gcode_macro _IDEX_TOOL_STATE") or {}
    return {
        "t0_x_position_endstop": _number(
            _settings(settings, "stepper_x"), "position_endstop", "stepper_x"
        ),
        "t1_x_position_endstop": _number(
            _settings(settings, "dual_carriage"),
            "position_endstop",
            "dual_carriage",
        ),
        "y_position_endstop": _number(
            _settings(settings, "stepper_y"), "position_endstop", "stepper_y"
        ),
        "z_position_endstop": _number(
            _settings(settings, "stepper_z"), "position_endstop", "stepper_z"
        ),
        "t1_y_gcode_offset": _number(
            tool_state, "t1_y_offset", "gcode_macro _IDEX_TOOL_STATE"
        ),
        "t1_z_gcode_offset": _number(
            tool_state, "t1_z_offset", "gcode_macro _IDEX_TOOL_STATE"
        ),
    }


def _require_generated_matches(
    active: dict[str, float],
    expected: dict[str, float],
    *,
    context: str,
) -> None:
    for field, expected_value in expected.items():
        active_value = float(active[field])
        if abs(active_value - float(expected_value)) > 0.0011:
            raise VisionCalibrationError(
                f"{context}: active {field}={active_value:.6f} differs from "
                f"expected {float(expected_value):.6f}"
            )


def calculate_fine_tool_xyz(
    *,
    tool: str,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tool = tool.upper()
    if tool not in {"T0", "T1"}:
        raise VisionCalibrationError("fine-tool calculation requires T0 or T1")
    projection_binding, projection_fact = _resolve_current_fact(
        "nozzle_tip_projection",
        f"camera.nozzle_cam.nozzle_tip.{tool.lower()}_projection_model",
        1,
    )
    partial_binding, partial_fact = _resolve_current_fact(
        "partial_bed_coordinate_system",
        "camera.nozzle_cam.partial_bed_coordinate_system",
        1,
    )
    metric_binding, metric_fact = _resolve_current_fact(
        "bed_metric",
        "camera.nozzle_cam.bed_fiducial.local_metric_model",
        1,
    )
    mapping_binding, mapping_fact = _resolve_current_fact(
        "bed_fiducial_printer_xy_mapping",
        "camera.nozzle_cam.bed_fiducial.printer_xy_mapping",
        1,
    )
    rough_binding, _rough_fact = _resolve_current_fact(
        "rough_x_active_snapshot",
        "calibration.rough_tool_x.active_snapshot",
        1,
    )
    source_facts = [
        projection_binding,
        metric_binding,
        partial_binding,
        mapping_binding,
        rough_binding,
    ]
    projection_fact_set = load_json(
        CALIBRATION_ROOT / projection_binding["fact_set_path"]
    )
    registrations = (
        projection_fact_set.get("provenance", {})
        .get("observations", {})
        .get("registrations")
    )
    if not isinstance(registrations, list) or not registrations:
        raise VisionCalibrationError(
            "nozzle-tip projection fact lacks bound registration observations"
        )
    metric_fact_set = load_json(CALIBRATION_ROOT / metric_binding["fact_set_path"])
    metric_details = metric_fact_set.get("provenance", {}).get("observations", {})
    metric_detections = metric_details.get("detection_records", [])
    metric_observations = []
    for record in metric_details.get("local_metric_records", []):
        seq = int(record["seq"])
        if not 0 <= seq < len(metric_detections):
            continue
        detection = metric_detections[seq]
        if not isinstance(detection, dict) or not detection.get("centers_px"):
            continue
        metric_observations.append(
            {
                "seq": seq,
                "commanded_y_mm": float(record["commanded_y_mm"]),
                "centers_px": detection["centers_px"],
            }
        )
    corner_fact_set = load_json(CALIBRATION_ROOT / partial_binding["fact_set_path"])
    corner_details = corner_fact_set.get("provenance", {}).get("observations", {})
    corner_capture_y = float(partial_fact["value"]["corner_pixel_capture_y_mm"])
    corner_observations = [
        {
            "seq": int(record["frame_index"]),
            "commanded_y_mm": corner_capture_y,
            "pixel_px": record["registered_corner_pixel_xy_px"],
        }
        for record in corner_details.get("records", [])
        if record.get("registered_corner_pixel_xy_px") is not None
    ]
    if len(metric_observations) < 4:
        raise VisionCalibrationError(
            "bed metric fact lacks enough bound fiducial observations"
        )
    if len(corner_observations) < 3:
        raise VisionCalibrationError(
            "bed-tab corner fact lacks enough bound corner observations"
        )

    old_datums = CALIB.tool_datums()
    printer_status = status or query_printer_status()
    old_generated = {
        "t0_x_position_endstop": old_datums["t0"]["x_endstop"],
        "t1_x_position_endstop": old_datums["t1"]["x_endstop"],
        "y_position_endstop": old_datums["t0"]["y_endstop"],
        "z_position_endstop": old_datums["t0"]["z_endstop"],
        "t1_y_gcode_offset": (
            old_datums["t0"]["y_endstop"] - old_datums["t1"]["y_endstop"]
        ),
        "t1_z_gcode_offset": (
            old_datums["t0"]["z_endstop"] - old_datums["t1"]["z_endstop"]
        ),
    }
    _require_generated_matches(
        _active_generated_calibration(printer_status),
        old_generated,
        context="source calibration is not the active Klipper calibration",
    )
    calculation = calculate_fine_tool_candidate(
        tool=tool,
        projection=projection_fact["value"],
        registrations=registrations,
        metric_observations=metric_observations,
        corner_observations=corner_observations,
        physical_reference={"centers_patch_xy_mm": CALIB.fiducial_centers()},
        mapping=mapping_fact["value"],
        partial_bed=partial_fact["value"],
        old_datums=old_datums,
    )
    fingerprint = str(
        printer_status["gcode_macro _IDEX_CONFIG_FINGERPRINT"]["source_sha256"]
    )
    calculation_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + f"-fine_tool_xyz_{tool.lower()}"
    )
    calculation_dir = CALIBRATION_ROOT / "calculations" / calculation_id
    calculation_dir.mkdir(parents=True)
    candidate_path = calculation_dir / "calib_candidate.yaml"
    candidate_hash = None
    if calculation["accepted"]:
        candidate_hash = CALIB.write_candidate(
            candidate_path,
            calculation["calibration"]["persisted_calib"]["new"],
        )

    calculation.update(
        {
            "schema": "vision-calibration-fine-tool-xyz-calculation",
            "schema_version": 1,
            "calculation_id": calculation_id,
            "created_at_utc": utc_now(),
            "source_facts": source_facts,
            "source_calib_sha256": CALIB.calib_hash(),
            "source_priors_sha256": CALIB.priors_hash(),
            "source_priors": {
                "fiducial_centers_xy_mm": CALIB.fiducial_centers(),
                "fiducial_z_mm": CALIB.fiducial_z(),
            },
            "source_active_config_fingerprint": fingerprint,
            "candidate_calib_path": (
                "calib_candidate.yaml" if candidate_hash is not None else None
            ),
            "candidate_calib_sha256": candidate_hash,
        }
    )
    calculation["artifacts"] = write_fine_tool_artifacts(
        calculation, calculation_dir / "artifacts"
    )

    publication = None
    if calculation["accepted"]:
        dependencies = [
            {
                "fact_name": item["fact_name"],
                "fact_set_hash": item["fact_set_hash"],
            }
            for item in source_facts
        ]
        tool_facts = []
        for selected_tool in (tool,):
            item = calculation["tools"][selected_tool]
            crossing = item["scale_crossing"]
            z_reference_value = {
                "fiducial_reference_printer_x_mm": crossing[
                    "fiducial_reference_printer_x_mm"
                ],
                "fiducial_x_vector_px_per_mm": crossing["fiducial_x_vector_px_per_mm"],
                "commanded_z_at_fiducial_plane_mm": crossing[
                    "commanded_z_at_fiducial_plane_mm"
                ],
                "fiducial_plane_printer_z_mm": crossing["fiducial_plane_printer_z_mm"],
                "bed_referenced_z_at_commanded_zero_mm": crossing[
                    "bed_referenced_z_at_commanded_zero_mm"
                ],
                "magnitude_crossing_commanded_z_mm": crossing[
                    "magnitude_crossing_commanded_z_mm"
                ],
                "closest_full_vector_commanded_z_mm": crossing[
                    "closest_full_vector_commanded_z_mm"
                ],
                "lateral_extrapolation_distance_mm": item[
                    "lateral_extrapolation_distance_mm"
                ],
                "maximum_leave_out_change_mm": item["stability"]["maximum_change_mm"],
                "position_fit_rms_px": item["projection_model"]["position_fit_rms_px"],
            }
            tool_facts.append(
                _fact(
                    f"tool.{tool.lower()}.nozzle_z_fiducial_reference",
                    "coordinate_system",
                    z_reference_value,
                    dependencies,
                    {
                        "fiducial_reference_printer_x_mm",
                        "fiducial_x_vector_px_per_mm",
                        "commanded_z_at_fiducial_plane_mm",
                        "fiducial_plane_printer_z_mm",
                        "bed_referenced_z_at_commanded_zero_mm",
                    },
                )
            )
            value = {
                "reference_commanded_xyz_mm": item["reference_commanded_xyz_mm"],
                "measured_nozzle_xyz_mm": item["measured_nozzle_xyz_mm"],
                "coordinate_residual_xyz_mm": item["coordinate_residual_xyz_mm"],
            }
            tool_facts.append(
                _fact(
                    f"tool.{tool.lower()}.nozzle_to_bed_tab_xyz_mm",
                    "coordinate_system",
                    value,
                    dependencies,
                    {
                        "reference_commanded_xyz_mm",
                        "measured_nozzle_xyz_mm",
                        "coordinate_residual_xyz_mm",
                    },
                )
            )
        candidate_value = {
            "tool": tool,
            "calculation_id": calculation_id,
            "persisted_calib": calculation["calibration"]["persisted_calib"],
            "generated_klipper": calculation["calibration"]["generated_klipper"],
            "candidate_calib_sha256": candidate_hash,
            "source_calib_sha256": calculation["source_calib_sha256"],
            "source_priors_sha256": calculation["source_priors_sha256"],
            "source_active_config_fingerprint": fingerprint,
            "z_reference_method": "fiducial_plane_lateral_scale_transport",
        }
        candidate_fact = _fact(
            f"calibration.fine_tool_xyz.{tool.lower()}_candidate",
            "coordinate_system",
            candidate_value,
            dependencies,
            {"persisted_calib", "generated_klipper"},
        )
        publication = _publish_operation_fact_set(
            f"fine_tool_xyz_{tool.lower()}_candidate",
            facts=[*tool_facts, candidate_fact],
            provenance={
                "method": "stage_5_1_fiducial_plane_scale_transport",
                "calculation_id": calculation_id,
                "source_calib_sha256": calculation["source_calib_sha256"],
                "source_priors_sha256": calculation["source_priors_sha256"],
                "candidate_calib_sha256": candidate_hash,
            },
            applicability={
                "printer": "menderpi",
                "active_config_fingerprint": fingerprint,
                "source_priors_sha256": calculation["source_priors_sha256"],
                "source_fact_set_hashes": [
                    item["fact_set_hash"] for item in source_facts
                ],
            },
        )
        calculation["candidate_fact_set_hash"] = publication["fact_set_hash"]
    calculation["publication"] = publication
    calculation["result_hash"] = canonical_hash(
        {key: value for key, value in calculation.items() if key != "result_hash"}
    )
    atomic_write_json(calculation_dir / "result.json", calculation, immutable=True)
    report = [
        f"# Stage 5.1 fine {tool} XYZ calculation",
        "",
        f"- Calculation: `{calculation_id}`",
        f"- State: **{'accepted' if calculation['accepted'] else 'rejected'}**",
        f"- Source calib: `{calculation['source_calib_sha256']}`",
        f"- Candidate calib: `{candidate_hash or 'not produced'}`",
        "- Z reference: fiducial-plane lateral scale transport",
        "",
        "## Tool results",
        "",
    ]
    for selected_tool in (tool,):
        item = calculation["tools"][selected_tool]
        report.extend(
            [
                f"### {selected_tool}",
                "",
                "- Coordinate residual XYZ: `"
                + json.dumps(item["coordinate_residual_xyz_mm"])
                + "` mm",
                (
                    "- Commanded Z at fiducial plane: "
                    f"`{item['scale_crossing']['commanded_z_at_fiducial_plane_mm']:.6f}` mm"
                ),
                (
                    "- Bed-referenced Z at commanded zero: "
                    f"`{item['scale_crossing']['bed_referenced_z_at_commanded_zero_mm']:.6f}` mm"
                ),
                (
                    "- Accepted projection samples: "
                    f"`{item['projection_model']['accepted_count']}`"
                ),
                (
                    "- Complete Z rows used: `"
                    + ", ".join(
                        f"{float(row['z_mm']):.3f} mm "
                        f"({int(row['accepted_count'])} X samples)"
                        for row in item["full_row_coverage"]
                    )
                    + "`"
                ),
                "",
            ]
        )
        baseline = float(item["stability"]["baseline_commanded_z_at_fiducial_plane_mm"])
        report.extend(
            [
                "## Sensitivity checks",
                "",
                (
                    "These checks refit the complete model after deliberately "
                    "removing data. A small crossing change means the result "
                    "does not depend strongly on one measurement or one Z row."
                ),
                "",
                (
                    "- **Single-sample check:** remove one accepted X/Z image, "
                    "refit, and compare its fiducial-plane crossing with the "
                    f"full-data crossing `{baseline:+.6f}` mm."
                ),
                (
                    "- **Full-row check:** remove every accepted X sample at "
                    "one commanded Z height, refit from the remaining rows, "
                    "and compare the crossing. This is the check previously "
                    "reported as “leave-one-full-row crossing.”"
                ),
                "",
                "| Omitted Z row | Refit crossing | Change from full data |",
                "| ---: | ---: | ---: |",
                *[
                    (
                        f"| {float(trial['left_out_z_mm']):.3f} mm "
                        f"| {float(trial['commanded_z_at_fiducial_plane_mm']):+.6f} mm "
                        f"| {float(trial['change_mm']):+.6f} mm |"
                    )
                    for trial in item["stability"]["trials"]
                    if trial["kind"] == "leave_one_full_z_row"
                ],
                "",
            ]
        )
    report.extend(
        [
            "## Rejection reasons",
            "",
            *([f"- {item}" for item in calculation["reasons"]] or ["- None"]),
            "",
            "## Warnings",
            "",
            *([f"- {item}" for item in calculation["warnings"]] or ["- None"]),
            "",
        ]
    )
    (calculation_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    rebuild_and_render()
    return {
        "calculation_id": calculation_id,
        "accepted": calculation["accepted"],
        "reasons": calculation["reasons"],
        "candidate_calib_path": (
            str(candidate_path) if candidate_hash is not None else None
        ),
        "candidate_calib_sha256": candidate_hash,
        "publication": publication,
        "review_url": f"/vision/calibration/calculations/{calculation_id}/",
        "tools": calculation["tools"],
    }


def record_fine_tool_xyz_activation(
    *,
    calculation_id: str,
    expected_fingerprint: str | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    calculation_dir = CALIBRATION_ROOT / "calculations" / _sanitize(calculation_id)
    result = load_json(calculation_dir / "result.json")
    if result.get("accepted") is not True:
        raise VisionCalibrationError("rejected fine-tool calculation cannot activate")
    candidate_path = calculation_dir / "calib_candidate.yaml"
    if CALIB.calib_hash() != result["candidate_calib_sha256"]:
        raise VisionCalibrationError(
            "synchronized calib.yaml does not match the accepted candidate"
        )
    if sha256_file(candidate_path) != result["candidate_calib_sha256"]:
        raise VisionCalibrationError("stored candidate calibration hash mismatch")
    printer_status = status or query_printer_status()
    fingerprint = str(
        printer_status["gcode_macro _IDEX_CONFIG_FINGERPRINT"]["source_sha256"]
    )
    if expected_fingerprint and fingerprint != expected_fingerprint:
        raise VisionCalibrationError(
            f"active fingerprint {fingerprint} != {expected_fingerprint}"
        )
    expected_generated = result["calibration"]["generated_klipper"]["new"]
    tool = str(result["tool"])
    active_generated = _active_generated_calibration(printer_status)
    _require_generated_matches(
        active_generated,
        expected_generated,
        context="deployed fine calibration",
    )
    candidate_binding, candidate_fact = _resolve_current_fact(
        "fine_tool_xyz_candidate",
        f"calibration.fine_tool_xyz.{tool.lower()}_candidate",
        1,
    )
    if candidate_fact["value"]["calculation_id"] != calculation_id:
        raise VisionCalibrationError(
            "current fine-tool candidate is not the requested calculation"
        )
    dependencies = [
        {
            "fact_name": candidate_binding["fact_name"],
            "fact_set_hash": candidate_binding["fact_set_hash"],
        }
    ]
    value = {
        "calculation_id": calculation_id,
        "persisted_calib": result["calibration"]["persisted_calib"]["new"],
        "generated_klipper": active_generated,
        "active_config_fingerprint": fingerprint,
        "active_calib_sha256": CALIB.calib_hash(),
        "z_reference_method": "fiducial_plane_lateral_scale_transport",
        "supersedes": "calibration.rough_tool_x.active_snapshot",
    }
    fact = _fact(
        f"calibration.fine_tool_xyz.{tool.lower()}_active_snapshot",
        "coordinate_system",
        value,
        dependencies,
        {"persisted_calib", "generated_klipper"},
    )
    activation = _publish_operation_fact_set(
        f"fine_tool_xyz_{tool.lower()}_activation",
        facts=[fact],
        provenance={
            "method": "verified_live_stage_5_1_activation",
            "calculation_id": calculation_id,
            "candidate_fact_set_hash": candidate_binding["fact_set_hash"],
        },
        applicability={
            "printer": "menderpi",
            "active_config_fingerprint": fingerprint,
            "active_calib_sha256": CALIB.calib_hash(),
        },
    )
    return {"active_snapshot": value, "activation": activation}


def _json_link(path: str, label: str) -> str:
    return f'<a href="{html.escape(path)}">{html.escape(label)}</a>'


def _page(title: str, body: str, *, prefix: str = "") -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{background:#15171b;color:#e8e8e8;font-family:system-ui;margin:0 auto;max-width:1500px;padding:28px}}
a{{color:#52b7f3}} table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #4a4f58;padding:8px;text-align:left}}
img{{max-width:100%;height:auto}} .card{{background:#20242b;border:1px solid #4a4f58;border-radius:8px;padding:14px;margin:12px 0}}
.good{{color:#82d173}} .bad{{color:#ff6b6b}} code,pre{{background:#111318;padding:3px;overflow:auto}}
</style></head><body><p><a href="{prefix}">Vision calibration</a></p>{body}</body></html>"""


def _coordinate_summary(name: str, value: dict[str, Any]) -> str:
    fields = {
        "bed.tab_corner.printer_xyz": ["xyz_mm"],
        "bed.fiducial_patch.physical_reference": [
            "outer_diameter_mm",
            "center_spacing_xy_mm",
        ],
        "bed.fiducial_patch.printer_z_mm": ["z_mm"],
        "camera.nozzle_cam.bed_fiducial.local_metric_model": [
            "image_y_axis_vector_px_per_mm",
            "patch_y_vector_per_printer_y_mm",
            "image_x_axis_candidate_models",
        ],
        "camera.nozzle_cam.partial_bed_coordinate_system": [
            "corner_pixel_xy_px",
            "corner_printer_xyz_mm",
            "corner_patch_xy_mm",
        ],
        "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2": [
            "axis_vector_px_per_mm"
        ],
        "camera.nozzle_cam.bed_fiducial.printer_xy_mapping": [
            "patch_x_vector_per_printer_x_mm",
            "patch_y_vector_per_printer_y_mm",
            "fiducial_reference_printer_xy_mm",
        ],
        "tool.t0.red_marker_to_bed_tab_x_mm": [
            "offset_mm",
            "reference_commanded_x_mm",
        ],
        "tool.t1.red_marker_to_bed_tab_x_mm": [
            "offset_mm",
            "reference_commanded_x_mm",
        ],
        "calibration.rough_tool_x.active_snapshot": [
            "t0_applied_x_endstop_mm",
            "t1_applied_x_endstop_mm",
        ],
        "camera.nozzle_cam.nozzle_tip.t0_projection_model": [
            "fiducial_reference_printer_xy_mm",
            "fiducial_x_vector_at_fine_capture_px_per_mm",
            "fiducial_plane_printer_z_mm",
            "fine_capture_y_mm",
        ],
        "camera.nozzle_cam.nozzle_tip.t1_projection_model": [
            "fiducial_reference_printer_xy_mm",
            "fiducial_x_vector_at_fine_capture_px_per_mm",
            "fiducial_plane_printer_z_mm",
            "fine_capture_y_mm",
        ],
        "tool.t0.nozzle_z_fiducial_reference": [
            "commanded_z_at_fiducial_plane_mm",
            "fiducial_plane_printer_z_mm",
            "bed_referenced_z_at_commanded_zero_mm",
        ],
        "tool.t1.nozzle_z_fiducial_reference": [
            "commanded_z_at_fiducial_plane_mm",
            "fiducial_plane_printer_z_mm",
            "bed_referenced_z_at_commanded_zero_mm",
        ],
        "tool.t0.nozzle_to_bed_tab_xyz_mm": [
            "coordinate_residual_xyz_mm",
            "measured_nozzle_xyz_mm",
        ],
        "tool.t1.nozzle_to_bed_tab_xyz_mm": [
            "coordinate_residual_xyz_mm",
            "measured_nozzle_xyz_mm",
        ],
        "calibration.fine_tool_xyz.t0_candidate": [
            "persisted_calib",
            "generated_klipper",
        ],
        "calibration.fine_tool_xyz.t1_candidate": [
            "persisted_calib",
            "generated_klipper",
        ],
        "calibration.fine_tool_xyz.t0_active_snapshot": [
            "persisted_calib",
            "generated_klipper",
            "z_reference_method",
        ],
        "calibration.fine_tool_xyz.t1_active_snapshot": [
            "persisted_calib",
            "generated_klipper",
            "z_reference_method",
        ],
    }.get(name, [])
    return (
        "<br>".join(
            f"<strong>{html.escape(field)}</strong>: "
            f"<code>{html.escape(json.dumps(value.get(field)))}</code>"
            for field in fields
            if field in value
        )
        or "No coordinate-system values"
    )


def _load_head_fact(head: dict[str, Any], name: str) -> dict[str, Any] | None:
    path = CALIBRATION_ROOT / head["fact_set_path"]
    if not path.exists():
        return None
    fact_set = load_json(path)
    return next((fact for fact in fact_set["facts"] if fact["name"] == name), None)


def render_ui(catalog: dict[str, Any]) -> None:
    VISION_ROOT.mkdir(parents=True, exist_ok=True)
    current_cards = []
    for name, head in sorted(catalog.get("heads", {}).items()):
        fact = _load_head_fact(head, name)
        if fact is None or fact["role"] != "coordinate_system":
            continue
        current_cards.append(
            f'<div class="card"><h3>{html.escape(name)}</h3>'
            f"{_coordinate_summary(name, fact['value'])}"
            f"<details><summary>Raw fact and provenance</summary><pre>"
            f"{html.escape(json.dumps(fact, indent=2, sort_keys=True))}"
            "</pre></details></div>"
        )
    job_rows = []
    for job in reversed(catalog.get("jobs", [])):
        job_rows.append(
            "<tr>"
            f"<td>{_json_link('calibration/jobs/' + job['job_id'] + '/', job['job_id'])}</td>"
            f"<td>{html.escape(job['job_type'])}</td>"
            f"<td>{html.escape(str(job['state']))}</td>"
            f"<td>{job['committed_frame_count']}/{job['frame_count']}</td>"
            f"<td>{len(job['analyses'])}</td></tr>"
        )
    calculation_rows = []
    calculations_root = CALIBRATION_ROOT / "calculations"
    if calculations_root.exists():
        for calculation_dir in sorted(
            (
                item
                for item in calculations_root.iterdir()
                if item.is_dir() and (item / "result.json").exists()
            ),
            reverse=True,
        ):
            result = load_json(calculation_dir / "result.json")
            state = "accepted" if result.get("accepted") else "rejected"
            calculation_rows.append(
                "<tr>"
                f"<td>{_json_link('calibration/calculations/' + calculation_dir.name + '/', calculation_dir.name)}</td>"
                f"<td>{html.escape(str(result.get('tool', 'legacy T0/T1')))}</td>"
                f"<td class=\"{'good' if state == 'accepted' else 'bad'}\">"
                f"{state}</td>"
                f"<td>{html.escape('; '.join(result.get('reasons', [])) or 'none')}</td>"
                "</tr>"
            )
    warning_items = "".join(
        f"<li>{html.escape(item['message'])}</li>"
        for item in catalog.get("warnings", [])
    )
    body = (
        "<h1>Vision calibration</h1>"
        "<p>Current graph: installed bed fiducials through fine T0/T1 nozzle X/Z.</p>"
        + (
            "<h2>Catalog warnings</h2><ul>" + warning_items + "</ul>"
            if warning_items
            else ""
        )
        + "<h2>Current coordinate-system facts</h2>"
        + ("".join(current_cards) or "<p>None.</p>")
        + "<h2>Stage 5.1 calculations</h2>"
        + (
            "<table><tr><th>Calculation</th><th>Tool</th><th>State</th>"
            "<th>Gates</th></tr>" + "".join(calculation_rows) + "</table>"
            if calculation_rows
            else "<p>None.</p>"
        )
        + "<h2>Jobs</h2><table><tr><th>Job</th><th>Type</th><th>State</th>"
        "<th>Frames</th><th>Analyses</th></tr>" + "".join(job_rows) + "</table>"
    )
    (VISION_ROOT / "index.html").write_text(
        _page("Vision calibration", body, prefix=""), encoding="utf-8"
    )
    for job in catalog.get("jobs", []):
        job_dir = CALIBRATION_ROOT / "jobs" / job["job_id"]
        manifest = load_json(job_dir / "manifest.json")
        frame_rows = []
        for frame in manifest["frames"]:
            image = f"frames/{frame['frame']}.jpg"
            if (job_dir / image).exists():
                content = f'<a href="{image}"><img src="{image}" width="360"></a>'
            else:
                content = "pending"
            frame_rows.append(
                f"<tr><td>{frame['seq']}</td><td>{html.escape(frame['frame'])}</td>"
                f"<td>{content}</td></tr>"
            )
        analyses = []
        for item in job["analyses"]:
            path = f"analysis/{item['analysis_run_id']}/"
            analyses.append(
                f"<li>{_json_link(path, item['analysis_run_id'])} — "
                f"{html.escape(item['state'])}</li>"
            )
        job_body = (
            f"<h1>{html.escape(job['job_id'])}</h1>"
            f"<p>Type: <code>{html.escape(job['job_type'])}</code> · "
            f"State: <strong>{html.escape(str(job['state']))}</strong></p>"
            f"<p>{_json_link('manifest.json', 'manifest')} · "
            f"{_json_link('acquisition.gcode', 'G-code')}</p>"
            "<h2>Analyses</h2><ul>"
            + ("".join(analyses) or "<li>None</li>")
            + "</ul><h2>Frames</h2><table><tr><th>Seq</th><th>Name</th>"
            "<th>Image</th></tr>" + "".join(frame_rows) + "</table>"
        )
        (job_dir / "index.html").write_text(
            _page(job["job_id"], job_body, prefix="../../../"),
            encoding="utf-8",
        )
        for item in job["analyses"]:
            analysis_dir = job_dir / "analysis" / item["analysis_run_id"]
            result = load_json(analysis_dir / "result.json")
            artifact_html = []
            for name, artifact in result["diagnostics"].get("artifacts", {}).items():
                relative = Path(artifact["path"]).relative_to(analysis_dir)
                artifact_html.append(
                    f'<div class="card"><h3>{html.escape(name)}</h3>'
                    f'<a href="{relative}"><img src="{relative}"></a></div>'
                )
            analysis_body = (
                f"<h1>{html.escape(item['analysis_run_id'])}</h1>"
                f"<p class=\"{'good' if item['state'] == 'accepted' else 'bad'}\">"
                f"State: {html.escape(item['state'])}</p>"
                f"<p>{_json_link('report.md', 'report')} · "
                f"{_json_link('result.json', 'result JSON')}"
                + (
                    f" · {_json_link('fact_set.json', 'fact set')}"
                    if (analysis_dir / "fact_set.json").exists()
                    else ""
                )
                + "</p><h2>Primary artifacts</h2>"
                + ("".join(artifact_html) or "<p>None.</p>")
            )
            (analysis_dir / "index.html").write_text(
                _page(item["analysis_run_id"], analysis_body, prefix="../../../../../"),
                encoding="utf-8",
            )
    if calculations_root.exists():
        for calculation_dir in (
            item
            for item in calculations_root.iterdir()
            if item.is_dir() and (item / "result.json").exists()
        ):
            result = load_json(calculation_dir / "result.json")
            artifact_html = []
            for name, artifact in result.get("artifacts", {}).items():
                relative = Path(artifact["path"]).relative_to(calculation_dir)
                if relative.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    artifact_html.append(
                        f'<div class="card"><h3>{html.escape(name)}</h3>'
                        f'<a href="{relative}"><img src="{relative}"></a></div>'
                    )
                else:
                    artifact_html.append(
                        f'<div class="card"><h3>{html.escape(name)}</h3>'
                        f"{_json_link(str(relative), relative.name)}</div>"
                    )
            state = "accepted" if result.get("accepted") else "rejected"
            calculation_body = (
                f"<h1>{html.escape(calculation_dir.name)}</h1>"
                f"<p class=\"{'good' if state == 'accepted' else 'bad'}\">"
                f"State: {state}</p>"
                f"<p>{_json_link('report.md', 'report')} · "
                f"{_json_link('result.json', 'result JSON')}"
                + (
                    f" · {_json_link('calib_candidate.yaml', 'calib candidate')}"
                    if (calculation_dir / "calib_candidate.yaml").exists()
                    else ""
                )
                + "</p><h2>Gate result</h2><ul>"
                + (
                    "".join(
                        f"<li>{html.escape(reason)}</li>"
                        for reason in result.get("reasons", [])
                    )
                    or "<li>All gates passed.</li>"
                )
                + "</ul><h2>Artifacts</h2>"
                + ("".join(artifact_html) or "<p>None.</p>")
            )
            (calculation_dir / "index.html").write_text(
                _page(
                    calculation_dir.name,
                    calculation_body,
                    prefix="../../../",
                ),
                encoding="utf-8",
            )


def rebuild_and_render() -> dict[str, Any]:
    catalog = rebuild_catalog(CALIBRATION_ROOT)
    _log_catalog_warnings(catalog)
    render_ui(catalog)
    return catalog


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "acquire", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("job_type", choices=JOB_TYPES)
        subparser.add_argument("--name", default="vision_calibration")
        subparser.add_argument("--expected-fingerprint")
        if command in {"acquire", "run"}:
            subparser.add_argument("--timeout", type=float, default=300.0)
    compute_parser = subparsers.add_parser("compute")
    compute_parser.add_argument(
        "job_type",
        choices=sorted(
            job_type for job_type in JOB_TYPES if _is_compute_only_job_type(job_type)
        ),
    )
    compute_parser.add_argument("--name", default="vision_calibration")
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("job_id")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("job_id")
    publish_parser.add_argument("analysis_run_id")
    subparsers.add_parser("rebuild-catalog")
    subparsers.add_parser("calculate-rough-x")
    fine_calculate_parser = subparsers.add_parser("calculate-fine-tool-xyz")
    fine_calculate_parser.add_argument("--tool", required=True, choices=("T0", "T1"))
    record_parser = subparsers.add_parser("record-rough-x-activation")
    record_parser.add_argument("--old-t0", type=float, required=True)
    record_parser.add_argument("--old-t1", type=float, required=True)
    record_parser.add_argument("--expected-fingerprint")
    fine_record_parser = subparsers.add_parser("record-fine-tool-xyz-activation")
    fine_record_parser.add_argument("calculation_id")
    fine_record_parser.add_argument("--expected-fingerprint")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_job(
                args.name,
                job_type=args.job_type,
                expected_fingerprint=args.expected_fingerprint,
            )
        elif args.command == "acquire":
            result = acquire_job(
                args.name,
                job_type=args.job_type,
                expected_fingerprint=args.expected_fingerprint,
                timeout=args.timeout,
            )
        elif args.command == "run":
            result = run_job(
                args.name,
                job_type=args.job_type,
                expected_fingerprint=args.expected_fingerprint,
                timeout=args.timeout,
            )
        elif args.command == "compute":
            result = compute_job(args.name, job_type=args.job_type)
        elif args.command == "analyze":
            result = analyze_job(args.job_id)
        elif args.command == "publish":
            result = publish_fact_set(
                CALIBRATION_ROOT, args.job_id, args.analysis_run_id
            )
            rebuild_and_render()
        elif args.command == "calculate-rough-x":
            result = calculate_rough_x()
        elif args.command == "calculate-fine-tool-xyz":
            result = calculate_fine_tool_xyz(tool=args.tool)
        elif args.command == "record-rough-x-activation":
            result = record_rough_x_activation(
                old_t0_x_endstop_mm=args.old_t0,
                old_t1_x_endstop_mm=args.old_t1,
                expected_fingerprint=args.expected_fingerprint,
            )
        elif args.command == "record-fine-tool-xyz-activation":
            result = record_fine_tool_xyz_activation(
                calculation_id=args.calculation_id,
                expected_fingerprint=args.expected_fingerprint,
            )
        else:
            result = rebuild_and_render()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        CalibrationGraphError,
        VisionCalibrationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"vision calibration failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
