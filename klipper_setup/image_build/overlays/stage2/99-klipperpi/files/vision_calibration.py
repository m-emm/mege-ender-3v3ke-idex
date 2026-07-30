#!/usr/bin/env python3
"""Graph-driven nozzle-camera calibration through the fine nozzle X/Z stage."""

from __future__ import annotations

import argparse
import html
import json
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

from vision_bed_fiducial import (
    analyze_corner,
    analyze_lighting,
    analyze_metric,
)
from vision_calibration_graph import (
    ANALYSIS_SCHEMA,
    FACT_SET_SCHEMA,
    MANIFEST_SCHEMA,
    SCHEMA_VERSION,
    CalibrationGraphError,
    atomic_write_json,
    canonical_hash,
    content_hash,
    load_json,
    publish_fact_set,
    publish_seed_fact_set,
    rebuild_catalog,
    sha256_file,
    utc_now,
    validate_manifest,
    validate_registry,
)
from vision_nozzle_fine_xz import analyze as analyze_fine_nozzle_xz
from vision_red_marker_x_sweep import analyze as analyze_red_marker_x_sweep
from vision_rough_x_verification import (
    analyze as analyze_rough_x_verification,
    calculate_candidate as calculate_rough_x_candidate,
)


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
PRIOR_PATH = Path(
    os.environ.get(
        "VISION_CALIBRATION_PRIOR_FILE",
        "/usr/local/share/vision/vision_calibration_priors.json",
    )
)
FRAMEBUFFER_DIR = Path(
    os.environ.get("VISION_FRAMEBUFFER_DIR", "/run/vision-preview-nozzle_cam")
)
MOONRAKER_URL = os.environ.get("VISION_MOONRAKER_URL", "http://127.0.0.1")

BED_FIDUCIAL_LIGHTING_JOB = "nozzle_cam_bed_fiducial_lighting_sweep"
BED_FIDUCIAL_METRIC_JOB = "nozzle_cam_bed_fiducial_y_metric"
BED_TAB_CORNER_JOB = "nozzle_cam_bed_tab_corner"
RED_MARKER_X_JOB = "idex_tool_red_marker_x_sweep"
ROUGH_X_VERIFY_JOB = "idex_rough_tool_x_verify"
FINE_NOZZLE_XZ_JOB = "idex_nozzle_fine_xz_grid"
JOB_TYPES = (
    BED_FIDUCIAL_LIGHTING_JOB,
    BED_FIDUCIAL_METRIC_JOB,
    BED_TAB_CORNER_JOB,
    RED_MARKER_X_JOB,
    ROUGH_X_VERIFY_JOB,
    FINE_NOZZLE_XZ_JOB,
)
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HASH_RE = re.compile(r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+")
HASH_PLACEHOLDER = "sha256:PLACEHOLDER"


class VisionCalibrationError(RuntimeError):
    pass


def _sanitize(value: str) -> str:
    result = NAME_RE.sub("_", str(value)).strip("._-")
    return (result or "vision_calibration")[:72]


def _load_registry() -> dict[str, Any]:
    return validate_registry(load_json(REGISTRY_PATH))


def _load_seed_registry() -> dict[str, Any]:
    registry = load_json(PRIOR_PATH)
    if registry.get("schema") != "vision-calibration-seed-registry":
        raise VisionCalibrationError("unsupported seed registry")
    if registry.get("schema_version") != 1:
        raise VisionCalibrationError("unsupported seed schema version")
    seeds = registry.get("seeds")
    if not isinstance(seeds, list):
        raise VisionCalibrationError("seed registry must contain a seed list")
    names = {seed.get("name") for seed in seeds if isinstance(seed, dict)}
    expected = {
        "bed.tab_corner.printer_xyz",
        "bed.fiducial_patch.physical_reference",
        "bed.fiducial_patch.printer_z_mm",
    }
    if names != expected:
        raise VisionCalibrationError(
            f"seed registry must contain exactly {sorted(expected)}"
        )
    for seed in seeds:
        if seed.get("definition_version") != 1:
            raise VisionCalibrationError("all seed definitions must be version 1")
    return registry


def sync_seed_facts() -> dict[str, Any]:
    registry = _load_seed_registry()
    results = []
    for seed in registry["seeds"]:
        source = {
            "name": seed["name"],
            "definition_version": seed["definition_version"],
            "revision": seed["revision"],
            "recorded_at_utc": seed["recorded_at_utc"],
            "role": seed["role"],
            "value_items": seed["value_items"],
            "value": seed["value"],
        }
        source_hash = canonical_hash(source)
        fact = {
            "name": seed["name"],
            "definition_version": 1,
            "role": seed["role"],
            "dependencies": [],
            "value_items": seed["value_items"],
            "value": seed["value"],
        }
        fact_set = {
            "schema": FACT_SET_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "fact_set_id": f"seed:{seed['name']}:revision-{seed['revision']}",
            "job_id": f"seed:{seed['name']}",
            "analysis_run_id": f"revision-{seed['revision']}",
            "analysis_hash": source_hash,
            "created_at_utc": seed["recorded_at_utc"],
            "accepted": True,
            "publication_eligible": True,
            "applicability_hash": canonical_hash(
                {
                    "printer": "menderpi",
                    "seed_name": seed["name"],
                    "revision": seed["revision"],
                }
            ),
            "facts": [fact],
            "provenance": {
                "source": "vision_calibration_priors.json",
                "source_sha256": sha256_file(PRIOR_PATH),
                "source_record_hash": source_hash,
            },
            "fact_set_hash": "",
        }
        fact_set["fact_set_hash"] = content_hash(fact_set, "fact_set_hash")
        directory = CALIBRATION_ROOT / "seeds" / fact_set["fact_set_hash"][7:23]
        path = directory / "fact_set.json"
        if path.exists():
            if load_json(path) != fact_set:
                raise VisionCalibrationError(f"seed hash collision at {path}")
        else:
            atomic_write_json(path, fact_set, immutable=True)
        publication = publish_seed_fact_set(CALIBRATION_ROOT, path)
        results.append(
            {
                "name": seed["name"],
                "fact_set_hash": fact_set["fact_set_hash"],
                "already_published": publication["already_published"],
            }
        )
    rebuild_and_render()
    return {"seeds": results}


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
        CALIBRATION_ROOT
        / "seeds"
        / fact_set["fact_set_hash"][7:23]
        / "fact_set.json"
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
    with urllib.request.urlopen(MOONRAKER_URL.rstrip("/") + path, timeout=timeout) as response:
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
    homed = str(status.get("toolhead", {}).get("homed_axes", ""))
    if not all(axis in homed for axis in "xyz"):
        raise VisionCalibrationError("XYZ must be homed; jobs never home automatically")
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
        status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT", {}).get(
            "source_sha256", ""
        )
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
        "safe_tool_change_z_mm": float(
            definition.get("safe_tool_change_z_mm", 5.0)
        ),
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
    elif job_type in {RED_MARKER_X_JOB, ROUGH_X_VERIFY_JOB, FINE_NOZZLE_XZ_JOB}:
        positions.append(
            (
                axis_minimum[0],
                pose["capture_y_mm"],
                pose["safe_tool_change_z_mm"],
            )
        )
    else:
        positions.append((pose["x_mm"], pose["y_base_mm"], pose["z_mm"]))
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
    scope = {
        "camera": "nozzle_cam",
        "registry_job": definition,
        "pose": pose,
        "axis_minimum": axis_minimum,
        "axis_maximum": axis_maximum,
        "active_fingerprint": fingerprint,
    }
    return {
        "pose": pose,
        "axis_minimum": axis_minimum,
        "axis_maximum": axis_maximum,
        "fingerprint": fingerprint,
        "temperatures": temperatures,
        "framebuffer": framebuffer,
        "active_calibration_snapshot": active_snapshot,
        "scope": scope,
        "applicability_hash": canonical_hash(scope),
    }


def _resolve_current_fact(
    requirement: str, fact_name: str, definition_version: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = rebuild_catalog(CALIBRATION_ROOT)
    head = catalog.get("heads", {}).get(fact_name)
    if not isinstance(head, dict):
        raise VisionCalibrationError(f"missing current fact {fact_name}")
    if head["fact_set_hash"] in catalog.get("stale_fact_sets", {}):
        raise VisionCalibrationError(f"current fact {fact_name} is stale")
    path = CALIBRATION_ROOT / head["fact_set_path"]
    fact_set = load_json(path)
    fact = next(
        (item for item in fact_set["facts"] if item["name"] == fact_name), None
    )
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


def _canonical_gcode(gcode: str) -> str:
    return HASH_RE.sub(
        lambda match: f"{match.group('name')}={HASH_PLACEHOLDER}", gcode
    )


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


def _capture_line(
    job_id: str, frame: dict[str, Any], *, tool: str
) -> str:
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
    pose = manifest["motion"]["resolved_pose"]
    feedrate = float(definition.get("velocity_mm_s", 60.0)) * 60.0
    lines = [
        f"; vision calibration job {job_id}",
        "G90",
        (
            f"VISION_JOB_BEGIN JOB={job_id} "
            f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
        ),
    ]
    job_type = manifest["job_type"]
    frames = manifest["frames"]
    if job_type == BED_FIDUCIAL_LIGHTING_JOB:
        lines.extend(
            [
                "T0",
                f"G1 Z{pose['z_mm']:.6f} F{feedrate:.3f}",
                (
                    f"G1 X{pose['x_mm']:.6f} Y{pose['y_base_mm']:.6f} "
                    f"F{feedrate:.3f}"
                ),
            ]
        )
        for frame in frames:
            lines.append(
                f"VISION_PROFILE CAMERA=nozzle_cam PROFILE={frame['profile']}"
            )
            lines.extend(_light_lines(frame["light_pixels"]))
            lines.extend(
                [
                    "M400",
                    f"G4 P{int(definition['settle_ms'])}",
                    _capture_line(job_id, frame, tool="T0"),
                ]
            )
    elif job_type in {BED_FIDUCIAL_METRIC_JOB, BED_TAB_CORNER_JOB}:
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
            z_mm = float(frame["commanded_position_mm"][2])
            x_mm = float(frame["commanded_position_mm"][0])
            if current_z != z_mm:
                lines.append(f"G1 Z{z_mm:.6f} F{feedrate:.3f}")
                current_z = z_mm
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
                (
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} "
                    f"F{feedrate:.3f}"
                ),
                "T0",
                (
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} "
                    f"F{feedrate:.3f}"
                ),
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


def _lighting_schedule(definition: dict[str, Any]) -> list[dict[str, Any]]:
    zero = {str(index): 0.0 for index in range(1, 9)}
    profiles = definition["exposure_profiles"]
    frames = [
        {"profile": profile, "light_pixels": dict(zero), "candidate": "lights_off"}
        for profile in profiles
    ]
    for profile in profiles[1:3]:
        for index in range(1, 9):
            pixels = dict(zero)
            pixels[str(index)] = float(definition["individual_light_intensity"])
            frames.append(
                {
                    "profile": profile,
                    "light_pixels": pixels,
                    "candidate": f"pixel_{index}",
                }
            )
    for indices in definition["combination_pixels"]:
        pixels = dict(zero)
        for index in indices:
            pixels[str(index)] = float(definition["combination_light_intensity"])
        frames.append(
            {
                "profile": profiles[1],
                "light_pixels": pixels,
                "candidate": "pixels_" + "_".join(str(item) for item in indices),
            }
        )
    if len(frames) != 24:
        raise VisionCalibrationError("lighting schedule must contain 24 frames")
    return frames


def _metric_patch_x_unit(
    metric: dict[str, Any], image_x_axis: list[float]
) -> list[float]:
    candidates = [
        np.asarray(item, dtype=np.float64)
        for item in metric["image_x_axis_candidates_px_per_mm"]
    ]
    target = np.asarray(image_x_axis, dtype=np.float64)
    selected = max(candidates, key=lambda item: float(np.dot(item, target)))
    homography = np.asarray(metric["patch_to_image_homography"], dtype=np.float64)
    center = np.asarray(
        metric["patch_reference_center_xy_mm"],
        dtype=np.float64,
    )
    epsilon = 1e-4

    def project(point: np.ndarray) -> np.ndarray:
        homogeneous = homography @ np.asarray([point[0], point[1], 1.0])
        return homogeneous[:2] / homogeneous[2]

    jacobian = np.column_stack(
        [
            (project(center + [epsilon, 0]) - project(center)) / epsilon,
            (project(center + [0, epsilon]) - project(center)) / epsilon,
        ]
    )
    return np.linalg.solve(jacobian, selected).tolist()


def prepare_job(
    name: str,
    *,
    job_type: str,
    expected_fingerprint: str | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = _load_registry()
    definition = json.loads(json.dumps(registry["job_types"][job_type]))
    sync_seed_facts()
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
    resolved["scope"]["input_fact_hashes"] = {
        item["requirement"]: item["fact_set_hash"] for item in input_facts
    }
    resolved["applicability_hash"] = canonical_hash(resolved["scope"])
    pose = resolved["pose"]
    job_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + _sanitize(name)
    )
    job_dir = CALIBRATION_ROOT / "jobs" / job_id
    if job_dir.exists():
        raise VisionCalibrationError(f"job already exists: {job_id}")
    frames = []
    if job_type == BED_FIDUCIAL_LIGHTING_JOB:
        for seq, item in enumerate(_lighting_schedule(definition)):
            frames.append(
                {
                    "seq": seq,
                    "frame": f"lighting_{seq:02d}_{item['candidate']}",
                    "camera": "nozzle_cam",
                    "profile": item["profile"],
                    "tool": "T0",
                    "light_pixels": item["light_pixels"],
                    "candidate": item["candidate"],
                    "commanded_position_mm": [
                        pose["x_mm"],
                        pose["y_base_mm"],
                        pose["z_mm"],
                    ],
                }
            )
    elif job_type == BED_FIDUCIAL_METRIC_JOB:
        lighting = input_values["lighting_profile"]
        for seq, offset in enumerate(definition["y_offsets_mm"]):
            frames.append(
                {
                    "seq": seq,
                    "frame": f"metric_y_{seq:02d}_{int(offset):02d}mm",
                    "camera": "nozzle_cam",
                    "profile": lighting["profile"],
                    "tool": "T0",
                    "light_pixels": lighting["light_pixels"],
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
                    "discard_fresh_frames": int(
                        definition["discard_fresh_frames"]
                    ),
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
            input_values["partial_bed_coordinate_system"]["corner_printer_xyz_mm"][
                0
            ]
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
    else:
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
        center_z = [float(item) for item in definition["center_only_z_mm"]]
        for tool in ("T0", "T1"):
            marker = input_values[
                "t0_red_marker_offset"
                if tool == "T0"
                else "t1_red_marker_offset"
            ]
            rows = [
                (full_z[0], offsets),
                (center_z[0], [offsets[2]]),
                (full_z[1], list(reversed(offsets))),
                (center_z[1], [offsets[2]]),
                (full_z[2], offsets),
            ]
            for z_mm, row in rows:
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
                                f"{seq:02d}_{tool.lower()}_"
                                f"x{x_mm:.3f}_z{z_mm:.3f}"
                            ).replace(".", "p"),
                            "camera": "nozzle_cam",
                            "profile": definition["profile"],
                            "tool": tool,
                            "x_offset_from_bed_tab_mm": offset,
                            "x_mm": x_mm,
                            "z_mm": z_mm,
                            "expected_marker_pixel_px": expected_marker.tolist(),
                            "discard_fresh_frames": 1,
                            "commanded_position_mm": [
                                x_mm,
                                pose["capture_y_mm"],
                                z_mm,
                            ],
                        }
                    )
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
        "motion": {
            "velocity_mm_s": float(definition.get("velocity_mm_s", 60.0)),
            "settle_ms": int(definition["settle_ms"]),
            "resolved_pose": pose,
            "axis_minimum": resolved["axis_minimum"],
            "axis_maximum": resolved["axis_maximum"],
            "no_implicit_homing": True,
            "minimum_commanded_z_mm": min(
                float(frame["commanded_position_mm"][2]) for frame in frames
            ),
        },
        "applicability": resolved["scope"],
        "applicability_hash": resolved["applicability_hash"],
        "provenance": {
            "active_printer_fingerprint": resolved["fingerprint"],
            "registry_sha256": sha256_file(REGISTRY_PATH),
            "profile_file_sha256": sha256_file(PROFILE_PATH),
            "preflight_temperatures": resolved["temperatures"],
            "preflight_framebuffer": resolved["framebuffer"],
        },
        "gcode_file": "acquisition.gcode",
        "gcode_hash": HASH_PLACEHOLDER,
        "manifest_hash": HASH_PLACEHOLDER,
    }
    if job_type in {RED_MARKER_X_JOB, FINE_NOZZLE_XZ_JOB}:
        manifest["active_calibration_snapshot"] = resolved[
            "active_calibration_snapshot"
        ]
    if job_type == RED_MARKER_X_JOB:
        partial = input_values["partial_bed_coordinate_system"]
        manifest["red_marker_reference"] = {
            "corner_pixel_xy_px": partial["corner_pixel_xy_px"],
            "corner_pixel_capture_y_mm": partial["corner_pixel_capture_y_mm"],
            "corner_printer_xyz_mm": partial["corner_printer_xyz_mm"],
            "image_y_axis_vector_px_per_mm": partial[
                "image_y_axis_vector_px_per_mm"
            ],
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
            "image_y_axis_vector_px_per_mm": partial[
                "image_y_axis_vector_px_per_mm"
            ],
            "image_x_axis_vector_px_per_mm": x_axis,
            "capture_y_mm": float(definition["capture_y_mm"]),
            "capture_z_mm": float(definition["capture_z_mm"]),
            "active_x_endstops_mm": {
                "t0_x_endstop_mm": active["t0_applied_x_endstop_mm"],
                "t1_x_endstop_mm": active["t1_applied_x_endstop_mm"],
            },
        }
    elif job_type == FINE_NOZZLE_XZ_JOB:
        metric = input_values["bed_metric"]
        partial = input_values["partial_bed_coordinate_system"]
        x_axis = input_values["image_x_axis_z2"]["axis_vector_px_per_mm"]
        corner_at_capture = np.asarray(partial["corner_pixel_xy_px"]) + np.asarray(
            partial["image_y_axis_vector_px_per_mm"]
        ) * (
            float(definition["capture_y_mm"])
            - float(partial["corner_pixel_capture_y_mm"])
        )
        manifest["fine_reference"] = {
            "bed_tab_x_mm": partial["corner_printer_xyz_mm"][0],
            "patch_to_image_homography": metric["patch_to_image_homography"],
            "corner_patch_xy_mm": partial["corner_patch_xy_mm"],
            "patch_x_unit_vector": _metric_patch_x_unit(metric, x_axis),
            "fiducial_plane_printer_z_mm": input_values["fiducial_plane_z"][
                "z_mm"
            ],
            "image_y_axis_vector_px_per_mm": metric[
                "image_y_axis_vector_px_per_mm"
            ],
            "corner_pixel_at_fine_capture_px": corner_at_capture.tolist(),
        }
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
    _moonraker_post(
        "/printer/print/start", {"filename": f"vision_jobs/{job_id}.gcode"}
    )


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


def _dependencies(manifest: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "fact_name": item["fact_name"],
            "fact_set_hash": item["fact_set_hash"],
        }
        for item in manifest["input_facts"]
    ]


def _diagnostic_fields(value: dict[str, Any], coordinate_fields: set[str]) -> list[dict[str, str]]:
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
                    "coordinate_system"
                    if field in coordinate_fields
                    else (
                        "acquisition_profile"
                        if role == "acquisition_profile"
                        else "diagnostic"
                    )
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
        raise VisionCalibrationError(f"job state {state.get('state')} cannot be analyzed")
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
        if job_type == BED_FIDUCIAL_LIGHTING_JOB:
            details = analyze_lighting(
                frame_paths, artifact_dir, frames=manifest["frames"]
            )
        elif job_type == BED_FIDUCIAL_METRIC_JOB:
            physical = _resolve_current_fact(
                "physical_reference",
                "bed.fiducial_patch.physical_reference",
                1,
            )[1]["value"]
            lighting = _resolve_current_fact(
                "lighting_profile",
                "camera.nozzle_cam.bed_fiducial.lighting_profile",
                1,
            )[1]["value"]
            details = analyze_metric(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                patch_points_mm=physical["centers_patch_xy_mm"],
                reference_centers_px=lighting["quality"]["winner_detection"][
                    "centers_px"
                ],
            )
        elif job_type == BED_TAB_CORNER_JOB:
            metric = _resolve_current_fact(
                "bed_metric",
                "camera.nozzle_cam.bed_fiducial.local_metric_model",
                1,
            )[1]["value"]
            capture_y = float(manifest["frames"][0]["commanded_position_mm"][1])
            expected_marker_centers = (
                np.asarray(metric["reference_marker_centers_px"], dtype=np.float64)
                + np.asarray(
                    metric["image_y_axis_vector_px_per_mm"], dtype=np.float64
                )
                * (capture_y - float(metric["reference_capture_y_mm"]))
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
        else:
            details = analyze_fine_nozzle_xz(
                frame_paths,
                artifact_dir,
                frames=manifest["frames"],
                reference=manifest["fine_reference"],
            )
        for artifact in details.get("artifacts", {}).values():
            path = Path(artifact["path"])
            artifact["path"] = str(
                analysis_dir / path.relative_to(staging)
            )
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
                "dependencies": manifest["input_facts"],
            },
            "diagnostics": details,
            "fact_set_path": "fact_set.json" if details["accepted"] else None,
            "analysis_hash": "",
        }
        analysis["analysis_hash"] = content_hash(analysis, "analysis_hash")
        facts = []
        dependencies = _dependencies(manifest)
        width = int(sidecars[0]["width"])
        height = int(sidecars[0]["height"])
        if details["accepted"]:
            if job_type == BED_FIDUCIAL_LIGHTING_JOB:
                value = {
                    "profile": details["winner_profile"],
                    "light_pixels": details["winner_light_pixels"],
                    "camera": "nozzle_cam",
                    "fixed_manual": True,
                    "quality": {
                        "winner_index": details["winner_index"],
                        "winner_detection": details["winner_detection"],
                    },
                    "supporting_artifact_hashes": {
                        key: item["sha256"]
                        for key, item in details["artifacts"].items()
                    },
                }
                facts = [
                    _fact(
                        "camera.nozzle_cam.bed_fiducial.lighting_profile",
                        "acquisition_profile",
                        value,
                        dependencies,
                    )
                ]
            elif job_type == BED_FIDUCIAL_METRIC_JOB:
                value = {
                    "image_y_axis_vector_px_per_mm": details[
                        "image_y_axis_vector_px_per_mm"
                    ],
                    "patch_to_image_homography": details[
                        "patch_to_image_homography"
                    ],
                    "patch_reference_center_xy_mm": details[
                        "patch_reference_center_xy_mm"
                    ],
                    "patch_y_vector_per_printer_y_mm": details[
                        "patch_y_vector_per_printer_y_mm"
                    ],
                    "image_x_axis_candidates_px_per_mm": details[
                        "image_x_axis_candidates_px_per_mm"
                    ],
                    "reference_marker_centers_px": details[
                        "reference_marker_centers_px"
                    ],
                    "reference_capture_y_mm": details[
                        "reference_capture_y_mm"
                    ],
                    "image_dimensions_px": [width, height],
                    "quality": {
                        key: details[key]
                        for key in (
                            "usable_frame_count",
                            "fit_rms_px",
                            "duplicate_disagreement_px",
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
                            "image_x_axis_candidates_px_per_mm",
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
                    for item in manifest["input_facts"]
                }
                metric = input_values["bed_metric"]
                prior = input_values["bed_tab_corner_prior"]
                corner_capture_y = float(
                    manifest["frames"][0]["commanded_position_mm"][1]
                )
                corner_at_metric_reference = (
                    np.asarray(details["corner_pixel_xy_px"], dtype=np.float64)
                    - np.asarray(
                        metric["image_y_axis_vector_px_per_mm"],
                        dtype=np.float64,
                    )
                    * (
                        corner_capture_y
                        - float(metric["reference_capture_y_mm"])
                    )
                )
                corner_patch = _homography_inverse_point(
                    metric["patch_to_image_homography"],
                    corner_at_metric_reference.tolist(),
                )
                value = {
                    "corner_pixel_xy_px": details["corner_pixel_xy_px"],
                    "corner_pixel_capture_y_mm": corner_capture_y,
                    "corner_pixel_at_metric_reference_px":
                        corner_at_metric_reference.tolist(),
                    "corner_printer_xyz_mm": prior["xyz_mm"],
                    "corner_patch_xy_mm": corner_patch,
                    "image_y_axis_vector_px_per_mm": metric[
                        "image_y_axis_vector_px_per_mm"
                    ],
                    "fiducial_plane_printer_z_mm": input_values[
                        "fiducial_plane_z"
                    ]["z_mm"],
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
                            "offset_mm": details[
                                "t0_red_marker_to_bed_tab_x_mm"
                            ],
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
                            "offset_mm": details[
                                "t1_red_marker_to_bed_tab_x_mm"
                            ],
                            "reference_commanded_x_mm": common_x,
                            **diagnostic,
                        },
                        dependencies,
                        {"offset_mm", "reference_commanded_x_mm"},
                    ),
                ]
            elif job_type == ROUGH_X_VERIFY_JOB:
                value = {
                    "verified": True,
                    "verification_command_x_mm": details[
                        "verification_command_x_mm"
                    ],
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
            else:
                projection = {
                    "tool_models": details["models"],
                    "bed_x_vector_fiducial_plane_px_per_mm": details[
                        "bed_x_vector_fiducial_plane_px_per_mm"
                    ],
                    "bed_x_vector_print_plane_px_per_mm": details[
                        "bed_x_vector_print_plane_px_per_mm"
                    ],
                    "image_y_axis_vector_px_per_mm": details[
                        "image_y_axis_vector_px_per_mm"
                    ],
                    "x_vector_z_slope_px_per_mm_per_mm": details[
                        "average_x_vector_z_slope_px_per_mm_per_mm"
                    ],
                    "cross_tool_tip_offset_px_at_x189_z5": details[
                        "cross_tool_tip_offset_px_at_x189_z5"
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
                        "camera.nozzle_cam.nozzle_tip.projection_model",
                        "coordinate_system",
                        projection,
                        dependencies,
                        {
                            "tool_models",
                            "bed_x_vector_fiducial_plane_px_per_mm",
                            "bed_x_vector_print_plane_px_per_mm",
                            "image_y_axis_vector_px_per_mm",
                            "x_vector_z_slope_px_per_mm_per_mm",
                            "cross_tool_tip_offset_px_at_x189_z5",
                        },
                    )
                ]
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
                    "active_printer_fingerprint": manifest["provenance"][
                        "active_printer_fingerprint"
                    ],
                    "manifest_hash": manifest["manifest_hash"],
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
            *(
                [f"- {item}" for item in details.get("warnings", [])]
                or ["- None"]
            ),
            "",
            "## Rejection reasons",
            "",
            *(
                [f"- {item}" for item in details.get("reasons", [])]
                or ["- None"]
            ),
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
    prior_binding, prior = _resolve_current_fact(
        "bed_tab_corner_prior", "bed.tab_corner.printer_xyz", 1
    )
    t0_binding, t0 = _resolve_current_fact(
        "t0_marker", "tool.t0.red_marker_to_bed_tab_x_mm", 1
    )
    t1_binding, t1 = _resolve_current_fact(
        "t1_marker", "tool.t1.red_marker_to_bed_tab_x_mm", 1
    )
    printer_status = status or query_printer_status()
    settings = printer_status["configfile"]["settings"]
    active_t0 = _number(_settings(settings, "stepper_x"), "position_endstop", "stepper_x")
    active_t1 = _number(
        _settings(settings, "dual_carriage"), "position_endstop", "dual_carriage"
    )
    candidate = calculate_rough_x_candidate(
        prior_xyz_mm=prior["value"]["xyz_mm"],
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
    candidate["source_facts"] = [prior_binding, t0_binding, t1_binding]
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
        provenance={"method": "verified_live_activation", "candidate": candidate},
        applicability={
            "printer": "menderpi",
            "active_config_fingerprint": candidate["active_config_fingerprint"],
        },
    )
    return {"candidate": candidate, "activation": activation}


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
            "image_x_axis_candidates_px_per_mm",
        ],
        "camera.nozzle_cam.partial_bed_coordinate_system": [
            "corner_pixel_xy_px",
            "corner_printer_xyz_mm",
            "corner_patch_xy_mm",
        ],
        "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2": [
            "axis_vector_px_per_mm"
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
        "camera.nozzle_cam.nozzle_tip.projection_model": [
            "x_vector_z_slope_px_per_mm_per_mm",
            "cross_tool_tip_offset_px_at_x189_z5",
        ],
    }.get(name, [])
    return "<br>".join(
        f"<strong>{html.escape(field)}</strong>: "
        f"<code>{html.escape(json.dumps(value.get(field)))}</code>"
        for field in fields
        if field in value
    ) or "No coordinate-system values"


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
    body = (
        "<h1>Vision calibration</h1>"
        "<p>Current graph: installed bed fiducials through fine T0/T1 nozzle X/Z.</p>"
        "<h2>Current coordinate-system facts</h2>"
        + ("".join(current_cards) or "<p>None.</p>")
        + "<h2>Jobs</h2><table><tr><th>Job</th><th>Type</th><th>State</th>"
        "<th>Frames</th><th>Analyses</th></tr>"
        + "".join(job_rows)
        + "</table>"
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
            "<th>Image</th></tr>"
            + "".join(frame_rows)
            + "</table>"
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


def rebuild_and_render() -> dict[str, Any]:
    catalog = rebuild_catalog(CALIBRATION_ROOT)
    render_ui(catalog)
    return catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "acquire", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("job_type", choices=JOB_TYPES)
        subparser.add_argument("--name", default="vision_calibration")
        subparser.add_argument("--expected-fingerprint")
        if command in {"acquire", "run"}:
            subparser.add_argument("--timeout", type=float, default=300.0)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("job_id")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("job_id")
    publish_parser.add_argument("analysis_run_id")
    subparsers.add_parser("sync-priors")
    subparsers.add_parser("rebuild-catalog")
    subparsers.add_parser("calculate-rough-x")
    record_parser = subparsers.add_parser("record-rough-x-activation")
    record_parser.add_argument("--old-t0", type=float, required=True)
    record_parser.add_argument("--old-t1", type=float, required=True)
    record_parser.add_argument("--expected-fingerprint")
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
        elif args.command == "analyze":
            result = analyze_job(args.job_id)
        elif args.command == "publish":
            result = publish_fact_set(
                CALIBRATION_ROOT, args.job_id, args.analysis_run_id
            )
            rebuild_and_render()
        elif args.command == "sync-priors":
            result = sync_seed_facts()
        elif args.command == "calculate-rough-x":
            result = calculate_rough_x()
        elif args.command == "record-rough-x-activation":
            result = record_rough_x_activation(
                old_t0_x_endstop_mm=args.old_t0,
                old_t1_x_endstop_mm=args.old_t1,
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
