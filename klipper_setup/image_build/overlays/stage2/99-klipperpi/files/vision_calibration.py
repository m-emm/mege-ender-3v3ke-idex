#!/usr/bin/env python3
"""Clean-slate vision calibration jobs, analysis, publication, and UI."""

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

from vision_bed_tab_corner import analyze as analyze_bed_tab_corner
from vision_bed_tab_y_scale import Y_OFFSETS_MM
from vision_bed_tab_y_scale import analyze as analyze_bed_tab_y_scale
from vision_red_marker_x_sweep import analyze as analyze_red_marker_x_sweep
from vision_rough_x_verification import (
    analyze as analyze_rough_x_verification,
    calculate_candidate as calculate_rough_x_candidate,
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
BED_TAB_Y_JOB_TYPE = "nozzle_cam_bed_tab_y_scale"
BED_TAB_CORNER_JOB_TYPE = "nozzle_cam_bed_tab_corner"
RED_MARKER_X_JOB_TYPE = "idex_tool_red_marker_x_sweep"
ROUGH_X_VERIFY_JOB_TYPE = "idex_rough_tool_x_verify"
FINE_NOZZLE_XZ_JOB_TYPE = "idex_nozzle_fine_xz_grid"
JOB_TYPES = (
    BED_TAB_Y_JOB_TYPE,
    BED_TAB_CORNER_JOB_TYPE,
    RED_MARKER_X_JOB_TYPE,
    ROUGH_X_VERIFY_JOB_TYPE,
    FINE_NOZZLE_XZ_JOB_TYPE,
)
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HASH_TOKEN_RE = re.compile(r"\b(?P<name>MANIFEST_HASH|GCODE_HASH)=sha256:\S+")
HASH_PLACEHOLDER = "sha256:PLACEHOLDER"


class VisionCalibrationError(RuntimeError):
    pass


def _sanitize(value: str) -> str:
    cleaned = NAME_RE.sub("_", value).strip("._-")
    return (cleaned or "bed_tab_y_scale")[:64]


def _load_registry() -> dict[str, Any]:
    return validate_registry(load_json(REGISTRY_PATH))


def _load_seed_registry() -> dict[str, Any]:
    registry = load_json(PRIOR_PATH)
    if registry.get("schema") != "vision-calibration-seed-registry":
        raise VisionCalibrationError("unsupported calibration seed registry")
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise VisionCalibrationError("unsupported calibration seed schema version")
    seeds = registry.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise VisionCalibrationError("calibration seed registry contains no seeds")
    expected_names = {
        "bed.tab_corner.printer_xyz",
        "bed.reference_plane.tab_to_print_plane_z_mm",
    }
    names = {seed.get("name") for seed in seeds if isinstance(seed, dict)}
    if names != expected_names:
        raise VisionCalibrationError("calibration seed registry has invalid facts")
    for seed in seeds:
        if not isinstance(seed, dict):
            raise VisionCalibrationError("calibration seed must be an object")
        if seed.get("definition_version") != 4:
            raise VisionCalibrationError(
                f"seed {seed.get('name')} definition_version must be 4"
            )
        if seed.get("role") not in ("coordinate_system", "diagnostic"):
            raise VisionCalibrationError(f"seed {seed.get('name')} has an invalid role")
        value = seed.get("value")
        value_items = seed.get("value_items")
        if not isinstance(value, dict) or not isinstance(value_items, list):
            raise VisionCalibrationError(
                f"seed {seed.get('name')} has invalid value declarations"
            )
        if {item.get("field") for item in value_items} != set(value):
            raise VisionCalibrationError(
                f"seed {seed.get('name')} declarations do not cover its value"
            )
    return registry


def sync_seed_facts() -> dict[str, Any]:
    registry = _load_seed_registry()
    registry_hash = sha256_file(PRIOR_PATH)
    results = []
    for seed in registry["seeds"]:
        seed_content_hash = canonical_hash(seed)
        analysis_hash = canonical_hash(
            {
                "kind": "vision_calibration_seed",
                "seed": seed,
                "seed_registry_sha256": registry_hash,
            }
        )
        fact_set = {
            "schema": FACT_SET_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "fact_set_id": f"seed:{seed['name']}:{seed_content_hash[7:19]}",
            "job_id": f"seed:{seed['name']}",
            "analysis_run_id": f"revision-{seed['revision']}",
            "analysis_hash": analysis_hash,
            "created_at_utc": seed["recorded_at_utc"],
            "accepted": True,
            "publication_eligible": True,
            "applicability_hash": canonical_hash(
                {"printer": "menderpi", "seed_name": seed["name"]}
            ),
            "facts": [
                {
                    "name": seed["name"],
                    "definition_version": seed["definition_version"],
                    "role": seed["role"],
                    "dependencies": [],
                    "value_items": seed["value_items"],
                    "value": seed["value"],
                }
            ],
            "provenance": {
                "source": "user_initial_prior",
                "seed_registry_sha256": registry_hash,
                "seed_content_hash": seed_content_hash,
                "revision": seed["revision"],
            },
            "fact_set_hash": "",
        }
        fact_set["fact_set_hash"] = content_hash(fact_set, "fact_set_hash")
        seed_dir = CALIBRATION_ROOT / "seeds" / fact_set["fact_set_hash"][7:23]
        fact_set_path = seed_dir / "fact_set.json"
        if not fact_set_path.exists():
            atomic_write_json(fact_set_path, fact_set, immutable=True)
        publication = publish_seed_fact_set(CALIBRATION_ROOT, fact_set_path)
        results.append(
            {
                "name": seed["name"],
                "fact_set_hash": fact_set["fact_set_hash"],
                "publication": publication["publication"],
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
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    analysis_hash = canonical_hash(
        {
            "kind": "vision_calibration_operation",
            "operation": operation,
            "facts": facts,
            "provenance": provenance,
            "applicability": applicability,
        }
    )
    fact_set = {
        "schema": FACT_SET_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fact_set_id": f"operation:{operation}:{analysis_hash[7:19]}",
        "job_id": f"operation:{operation}",
        "analysis_run_id": stamp,
        "analysis_hash": analysis_hash,
        "created_at_utc": created_at,
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
    operation_dir = CALIBRATION_ROOT / "seeds" / fact_set["fact_set_hash"][7:23]
    fact_set_path = operation_dir / "fact_set.json"
    atomic_write_json(fact_set_path, fact_set, immutable=True)
    publication = publish_seed_fact_set(CALIBRATION_ROOT, fact_set_path)
    rebuild_and_render()
    return {
        "operation": operation,
        "fact_set_hash": fact_set["fact_set_hash"],
        "fact_set_path": str(fact_set_path),
        "publication": publication["publication"],
        "facts": [fact["name"] for fact in facts],
    }


def calculate_rough_x(
    *,
    old_t0_x_endstop_mm: float | None = None,
    old_t1_x_endstop_mm: float | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior_binding, prior_fact = _resolve_current_fact(
        "bed_tab_corner_prior", "bed.tab_corner.printer_xyz", 4
    )
    t0_binding, t0_fact = _resolve_current_fact(
        "t0_marker", "tool.t0.red_marker_to_bed_tab_x_mm", 5
    )
    t1_binding, t1_fact = _resolve_current_fact(
        "t1_marker", "tool.t1.red_marker_to_bed_tab_x_mm", 5
    )
    printer_status = status or query_printer_status()
    settings = printer_status.get("configfile", {}).get("settings")
    if not isinstance(settings, dict):
        raise VisionCalibrationError("active Klipper settings are unavailable")
    stepper_x = _settings_section(settings, "stepper_x")
    dual_carriage = _settings_section(settings, "dual_carriage")
    active_t0 = _number(stepper_x, "position_endstop", "stepper_x")
    active_t1 = _number(dual_carriage, "position_endstop", "dual_carriage")
    old_t0 = active_t0 if old_t0_x_endstop_mm is None else old_t0_x_endstop_mm
    old_t1 = active_t1 if old_t1_x_endstop_mm is None else old_t1_x_endstop_mm
    candidate = calculate_rough_x_candidate(
        prior_xyz_mm=prior_fact["value"]["xyz_mm"],
        t0_marker_fact=t0_fact["value"],
        t1_marker_fact=t1_fact["value"],
        old_t0_x_endstop_mm=float(old_t0),
        old_t1_x_endstop_mm=float(old_t1),
    )
    candidate["active_before_or_current_mm"] = {
        "T0": active_t0,
        "T1": active_t1,
    }
    candidate["source_facts"] = [
        prior_binding,
        t0_binding,
        t1_binding,
    ]
    candidate["active_config_fingerprint"] = str(
        printer_status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT", {}).get(
            "source_sha256"
        )
        or ""
    )
    return candidate


def record_rough_x_activation(
    *,
    old_t0_x_endstop_mm: float,
    old_t1_x_endstop_mm: float,
    expected_fingerprint: str | None = None,
) -> dict[str, Any]:
    status = query_printer_status()
    candidate = calculate_rough_x(
        old_t0_x_endstop_mm=old_t0_x_endstop_mm,
        old_t1_x_endstop_mm=old_t1_x_endstop_mm,
        status=status,
    )
    active_fingerprint = candidate["active_config_fingerprint"]
    if expected_fingerprint and active_fingerprint != expected_fingerprint:
        raise VisionCalibrationError(
            f"active fingerprint {active_fingerprint} does not match "
            f"{expected_fingerprint}"
        )
    active = candidate["active_before_or_current_mm"]
    for tool in ("T0", "T1"):
        expected = candidate["tools"][tool]["candidate_x_endstop_mm"]
        if abs(float(active[tool]) - float(expected)) > 0.0011:
            raise VisionCalibrationError(
                f"active {tool} X endstop {active[tool]} does not match "
                f"candidate {expected}"
            )
    source_facts = candidate["source_facts"]
    dependencies = [
        {
            "fact_name": binding["fact_name"],
            "fact_set_hash": binding["fact_set_hash"],
        }
        for binding in source_facts
    ]
    t0 = candidate["tools"]["T0"]
    t1 = candidate["tools"]["T1"]
    value = {
        "bed_tab_x_mm": float(candidate["bed_tab_corner_xyz_mm"][0]),
        "t0_old_x_endstop_mm": float(old_t0_x_endstop_mm),
        "t0_calculated_correction_mm": t0["calculated_correction_mm"],
        "t0_applied_x_endstop_mm": float(active["T0"]),
        "t1_old_x_endstop_mm": float(old_t1_x_endstop_mm),
        "t1_calculated_correction_mm": t1["calculated_correction_mm"],
        "t1_applied_x_endstop_mm": float(active["T1"]),
        "active_config_fingerprint": active_fingerprint,
        "calculation": (
            "new_x_endstop = old_x_endstop + bed_tab_x + "
            "marker_to_bed_tab_x - reference_commanded_x"
        ),
        "source_fact_set_hashes": {
            binding["fact_name"]: binding["fact_set_hash"]
            for binding in source_facts
        },
    }
    coordinate_fields = {
        "bed_tab_x_mm",
        "t0_old_x_endstop_mm",
        "t0_calculated_correction_mm",
        "t0_applied_x_endstop_mm",
        "t1_old_x_endstop_mm",
        "t1_calculated_correction_mm",
        "t1_applied_x_endstop_mm",
    }
    activation = _publish_operation_fact_set(
        "rough_tool_x_activation",
        facts=[
            {
                "name": "calibration.rough_tool_x.active_snapshot",
                "definition_version": 5,
                "role": "coordinate_system",
                "dependencies": dependencies,
                "value_items": [
                    {
                        "field": field,
                        "role": (
                            "coordinate_system"
                            if field in coordinate_fields
                            else "diagnostic"
                        ),
                    }
                    for field in value
                ],
                "value": value,
            }
        ],
        provenance={
            "method": "verified_live_activation",
            "candidate": candidate,
        },
        applicability={
            "printer": "menderpi",
            "active_config_fingerprint": active_fingerprint,
        },
    )
    return {"candidate": candidate, "activation": activation}


def _canonical_gcode(gcode: str) -> str:
    return HASH_TOKEN_RE.sub(
        lambda match: f"{match.group('name')}={HASH_PLACEHOLDER}", gcode
    )


def _gcode_hash(gcode: str) -> str:
    return canonical_hash(_canonical_gcode(gcode))


def _moonraker_get(path: str, *, timeout: float = 15.0) -> dict[str, Any]:
    with urllib.request.urlopen(
        MOONRAKER_URL.rstrip("/") + path, timeout=timeout
    ) as response:
        return json.loads(response.read())


def _moonraker_post(
    path: str, fields: dict[str, Any], *, timeout: float = 30.0
) -> dict[str, Any]:
    request = urllib.request.Request(
        MOONRAKER_URL.rstrip("/") + path,
        data=urllib.parse.urlencode(fields).encode(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload) if payload else {}


def query_printer_status() -> dict[str, Any]:
    query = (
        "/printer/objects/query?"
        "webhooks=state&"
        "print_stats=state,filename&"
        "virtual_sdcard=is_active,progress&"
        "toolhead=homed_axes,position,axis_minimum,axis_maximum&"
        "gcode_move=gcode_position&"
        "configfile=settings,save_config_pending&"
        "extruder=temperature,target&"
        "extruder1=temperature,target&"
        "heater_bed=temperature,target&"
        "temperature_probe%20btt_eddy=temperature&"
        "temperature_sensor%20btt_eddy_mcu=temperature&"
        "gcode_macro%20_IDEX_CONFIG_FINGERPRINT=source_sha256"
    )
    response = _moonraker_get(query)
    return response["result"]["status"]


def _number(mapping: dict[str, Any], key: str, context: str) -> float:
    try:
        return float(mapping[key])
    except (KeyError, TypeError, ValueError):
        raise VisionCalibrationError(f"missing numeric {context}.{key}") from None


def _settings_section(settings: dict[str, Any], name: str) -> dict[str, Any]:
    section = settings.get(name)
    if not isinstance(section, dict):
        raise VisionCalibrationError(f"active Klipper lacks [{name}] settings")
    return section


def _resolve_preflight(
    status: dict[str, Any],
    job_type: str,
    definition: dict[str, Any],
    expected_fingerprint: str | None,
) -> dict[str, Any]:
    if status.get("webhooks", {}).get("state") != "ready":
        raise VisionCalibrationError("Klipper is not ready")
    print_state = status.get("print_stats", {}).get("state")
    if print_state not in ("standby", "complete"):
        raise VisionCalibrationError(
            f"printer is not idle; print_stats.state={print_state!r}"
        )
    if status.get("virtual_sdcard", {}).get("is_active"):
        raise VisionCalibrationError("an active virtual-SD print is running")
    homed_axes = str(status.get("toolhead", {}).get("homed_axes") or "")
    if not all(axis in homed_axes for axis in "xyz"):
        raise VisionCalibrationError(
            "XYZ must already be homed; this job never homes automatically"
        )
    fingerprint = str(
        status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT", {}).get("source_sha256")
        or ""
    )
    if not fingerprint:
        raise VisionCalibrationError("active Klipper fingerprint is unavailable")
    if expected_fingerprint and expected_fingerprint != fingerprint:
        raise VisionCalibrationError(
            f"active fingerprint {fingerprint} does not match "
            f"{expected_fingerprint}"
        )

    configfile = status.get("configfile", {})
    settings = configfile.get("settings")
    if not isinstance(settings, dict):
        raise VisionCalibrationError("active Klipper settings are unavailable")
    stepper_x = _settings_section(settings, "stepper_x")
    stepper_y = _settings_section(settings, "stepper_y")
    stepper_z = _settings_section(settings, "stepper_z")
    x_min = _number(stepper_x, "position_min", "stepper_x")
    y_min = _number(stepper_y, "position_min", "stepper_y")
    y_endstop = _number(stepper_y, "position_endstop", "stepper_y")
    z_max = _number(stepper_z, "position_max", "stepper_z")
    axis_minimum = [float(item) for item in status["toolhead"]["axis_minimum"]]
    axis_maximum = [float(item) for item in status["toolhead"]["axis_maximum"]]
    if job_type == BED_TAB_Y_JOB_TYPE:
        resolved_positions = [
            [x_min, y_min + offset, z_max] for offset in definition["y_offsets_mm"]
        ]
    elif job_type == BED_TAB_CORNER_JOB_TYPE:
        resolved_positions = [
            [x_min, y_min + float(definition["capture_y_offset_mm"]), z_max]
        ] * int(definition["duplicate_count"])
    elif job_type in (
        RED_MARKER_X_JOB_TYPE,
        ROUGH_X_VERIFY_JOB_TYPE,
        FINE_NOZZLE_XZ_JOB_TYPE,
    ):
        dual_carriage = _settings_section(settings, "dual_carriage")
        if job_type == RED_MARKER_X_JOB_TYPE:
            x_positions = [
                float(value) for value in definition["x_positions_mm"]
            ]
        elif job_type == FINE_NOZZLE_XZ_JOB_TYPE:
            x_positions = [
                float(value) for value in definition["resolved_x_positions_mm"]
            ]
        else:
            x_positions = [float(definition["command_x_mm"])]
        capture_y = float(definition["capture_y_mm"])
        safe_z = float(definition["safe_tool_change_z_mm"])
        z_positions = (
            [float(value) for value in definition["z_positions_mm"]]
            if job_type == FINE_NOZZLE_XZ_JOB_TYPE
            else [float(definition["capture_z_mm"])]
        )
        resolved_positions = [
            [x, capture_y, z]
            for _tool in ("T0", "T1")
            for z in z_positions
            for x in x_positions
        ]
        for heater_name in ("extruder", "extruder1", "heater_bed"):
            if abs(float(status.get(heater_name, {}).get("target") or 0.0)) > 0.01:
                raise VisionCalibrationError(
                    f"{heater_name} target must be off for the cold marker job"
                )
        for axis_name, value in (
            [("Y", capture_y), ("Z", safe_z)]
            + [("Z", value) for value in z_positions]
        ):
            axis_index = "XYZ".index(axis_name)
            if not axis_minimum[axis_index] <= value <= axis_maximum[axis_index]:
                raise VisionCalibrationError(
                    f"marker {axis_name}={value} lies outside active limits"
                )
        tool_limits = {
            "T0": (
                _number(stepper_x, "position_min", "stepper_x"),
                _number(stepper_x, "position_max", "stepper_x"),
            ),
            "T1": (
                _number(dual_carriage, "position_min", "dual_carriage"),
                _number(dual_carriage, "position_max", "dual_carriage"),
            ),
        }
        for tool, (minimum, maximum) in tool_limits.items():
            for x in x_positions:
                if not minimum <= x <= maximum:
                    raise VisionCalibrationError(
                        f"marker {tool} X={x} lies outside active limits "
                        f"[{minimum}, {maximum}]"
                    )
    else:
        raise VisionCalibrationError(f"unsupported preflight job type {job_type}")
    for index, position in enumerate(resolved_positions):
        for axis, value, minimum, maximum in zip(
            "xyz", position, axis_minimum, axis_maximum
        ):
            if not minimum <= value <= maximum:
                raise VisionCalibrationError(
                    f"resolved frame {index} {axis.upper()}={value} lies "
                    f"outside active limits [{minimum}, {maximum}]"
                )

    profile_data = load_json(PROFILE_PATH)
    profiles = profile_data.get("profiles")
    aliases = profile_data.get("aliases") or {}
    resolved_profile = aliases.get(definition["profile"], definition["profile"])
    if not isinstance(profiles, dict) or resolved_profile not in profiles:
        raise VisionCalibrationError(
            f"fixed profile {definition['profile']!r} is unavailable"
        )
    latest_image = FRAMEBUFFER_DIR / "latest.jpg"
    latest_metadata_path = FRAMEBUFFER_DIR / "latest.json"
    if not latest_image.is_file() or not latest_metadata_path.is_file():
        raise VisionCalibrationError("nozzle camera framebuffer is unavailable")
    latest_metadata = load_json(latest_metadata_path)
    if (
        int(latest_metadata.get("width") or 0) <= 0
        or int(latest_metadata.get("height") or 0) <= 0
    ):
        raise VisionCalibrationError("camera framebuffer dimensions are invalid")
    image_bytes = latest_image.read_bytes()
    if not image_bytes.startswith(b"\xff\xd8") or not image_bytes.endswith(b"\xff\xd9"):
        raise VisionCalibrationError("camera framebuffer is not a complete JPEG")

    light_section = (
        "gcode_macro nozzle_cam_analysis_light"
        if job_type in (
            RED_MARKER_X_JOB_TYPE,
            ROUGH_X_VERIFY_JOB_TYPE,
            FINE_NOZZLE_XZ_JOB_TYPE,
        )
        else "gcode_macro nozzle_cam_y_feature_light"
    )
    light_settings = _settings_section(settings, light_section)
    scope: dict[str, Any] = {
        "camera": "nozzle_cam",
        "profile": definition["profile"],
        "profile_file_sha256": sha256_file(PROFILE_PATH),
        "light_macro": definition["light_macro"],
        "light_gcode": light_settings.get("gcode"),
        "localizer": definition["localizer"],
        "t0_viewing_pose": {"x_mm": x_min, "z_mm": z_max},
    }
    if job_type == BED_TAB_Y_JOB_TYPE:
        scope["y_motion"] = {
            "position_min_mm": y_min,
            "position_endstop_mm": y_endstop,
            "offsets_mm": definition["y_offsets_mm"],
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "rotation_distance": stepper_y.get("rotation_distance"),
            "microsteps": stepper_y.get("microsteps"),
        }
    elif job_type == BED_TAB_CORNER_JOB_TYPE:
        scope["corner_capture"] = {
            "position_min_mm": y_min,
            "y_offset_mm": definition["capture_y_offset_mm"],
            "duplicate_count": definition["duplicate_count"],
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "discard_fresh_frames": definition["discard_fresh_frames"],
        }
    elif job_type == RED_MARKER_X_JOB_TYPE:
        scope["red_marker_sweep"] = {
            "x_positions_mm": definition["x_positions_mm"],
            "capture_y_mm": definition["capture_y_mm"],
            "capture_z_mm": definition["capture_z_mm"],
            "safe_tool_change_z_mm": definition["safe_tool_change_z_mm"],
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "tool_change_settle_ms": definition["tool_change_settle_ms"],
            "discard_fresh_frames": definition["discard_fresh_frames"],
            "t0_x_limits_mm": [
                _number(stepper_x, "position_min", "stepper_x"),
                _number(stepper_x, "position_max", "stepper_x"),
            ],
            "t1_x_limits_mm": [
                _number(dual_carriage, "position_min", "dual_carriage"),
                _number(dual_carriage, "position_max", "dual_carriage"),
            ],
        }
    elif job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        scope["fine_nozzle_xz_grid"] = {
            "x_offsets_from_bed_tab_mm": definition[
                "x_offsets_from_bed_tab_mm"
            ],
            "resolved_x_positions_mm": definition["resolved_x_positions_mm"],
            "z_positions_mm": definition["z_positions_mm"],
            "capture_y_mm": definition["capture_y_mm"],
            "safe_tool_change_z_mm": definition["safe_tool_change_z_mm"],
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "tool_change_settle_ms": definition["tool_change_settle_ms"],
            "discard_fresh_frames": definition["discard_fresh_frames"],
            "t0_x_limits_mm": [
                _number(stepper_x, "position_min", "stepper_x"),
                _number(stepper_x, "position_max", "stepper_x"),
            ],
            "t1_x_limits_mm": [
                _number(dual_carriage, "position_min", "dual_carriage"),
                _number(dual_carriage, "position_max", "dual_carriage"),
            ],
        }
    else:
        scope["rough_x_verification"] = {
            "command_x_mm": float(definition["command_x_mm"]),
            "verification_offset_x_mm": float(
                definition["verification_offset_x_mm"]
            ),
            "capture_y_mm": definition["capture_y_mm"],
            "capture_z_mm": definition["capture_z_mm"],
            "safe_tool_change_z_mm": definition["safe_tool_change_z_mm"],
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "tool_change_settle_ms": definition["tool_change_settle_ms"],
            "discard_fresh_frames": definition["discard_fresh_frames"],
        }
    return {
        "fingerprint": fingerprint,
        "scope": scope,
        "applicability_hash": canonical_hash(scope),
        "pose": {
            "x_mm": x_min,
            "y_base_mm": y_min,
            "y_endstop_mm": y_endstop,
            "z_mm": z_max,
            **(
                {
                    "capture_y_mm": float(definition["capture_y_mm"]),
                    "safe_tool_change_z_mm": float(
                        definition["safe_tool_change_z_mm"]
                    ),
                    **(
                        {}
                        if job_type == FINE_NOZZLE_XZ_JOB_TYPE
                        else {
                            "capture_z_mm": float(
                                definition["capture_z_mm"]
                            )
                        }
                    ),
                }
                if job_type
                in (
                    RED_MARKER_X_JOB_TYPE,
                    ROUGH_X_VERIFY_JOB_TYPE,
                    FINE_NOZZLE_XZ_JOB_TYPE,
                )
                else {}
            ),
        },
        "active_calibration_snapshot": (
            {
                "t0_x_endstop_mm": _number(
                    stepper_x, "position_endstop", "stepper_x"
                ),
                "t1_x_endstop_mm": _number(
                    dual_carriage, "position_endstop", "dual_carriage"
                ),
            }
            if job_type
            in (
                RED_MARKER_X_JOB_TYPE,
                ROUGH_X_VERIFY_JOB_TYPE,
                FINE_NOZZLE_XZ_JOB_TYPE,
            )
            else None
        ),
        "axis_minimum": axis_minimum,
        "axis_maximum": axis_maximum,
        "framebuffer": {
            "width": latest_metadata["width"],
            "height": latest_metadata["height"],
            "frame_seq": latest_metadata.get("frame_seq"),
            "camera_profile": latest_metadata.get("camera_profile"),
        },
        "temperatures": {
            name: status.get(name, {})
            for name in (
                "extruder",
                "extruder1",
                "heater_bed",
                "temperature_probe btt_eddy",
                "temperature_sensor btt_eddy_mcu",
            )
        },
    }


def _job_id(name: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{timestamp}-{_sanitize(name)}"


def _gcode(
    job_id: str,
    manifest_hash: str,
    gcode_hash: str,
    job_type: str,
    definition: dict[str, Any],
    pose: dict[str, float],
) -> str:
    feedrate = float(definition["velocity_mm_s"]) * 60.0
    if job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        lines = [
            f"; vision calibration job {job_id}",
            "G90",
            (
                f"VISION_JOB_BEGIN JOB={job_id} "
                f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
            ),
            ("VISION_PROFILE CAMERA=nozzle_cam " f"PROFILE={definition['profile']}"),
            definition["light_macro"],
        ]
        seq = 0
        x_positions = [
            float(value) for value in definition["resolved_x_positions_mm"]
        ]
        z_positions = [float(value) for value in definition["z_positions_mm"]]
        for tool in ("T0", "T1"):
            lines.extend(
                [
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                    tool,
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                    f"G1 Y{pose['capture_y_mm']:.6f} F{feedrate:.3f}",
                    "M400",
                    f"G4 P{int(definition['tool_change_settle_ms'])}",
                ]
            )
            for z_index, z_mm in enumerate(z_positions):
                row_x = (
                    x_positions
                    if z_index % 2 == 0
                    else list(reversed(x_positions))
                )
                lines.extend(
                    [
                        f"G1 X{row_x[0]:.6f} F{feedrate:.3f}",
                        f"G1 Z{z_mm:.6f} F{feedrate:.3f}",
                    ]
                )
                for x_mm in row_x:
                    frame = (
                        f"{seq:02d}_{tool.lower()}_"
                        f"x{x_mm:.3f}_z{z_mm:.3f}"
                    ).replace(".", "p")
                    lines.extend(
                        [
                            f"G1 X{x_mm:.6f} F{feedrate:.3f}",
                            "M400",
                            f"G4 P{int(definition['settle_ms'])}",
                            (
                                f"VISION_CAPTURE_SYNC JOB={job_id} SEQ={seq} "
                                f"FRAME={frame} CAMERA=nozzle_cam "
                                f"PROFILE={definition['profile']} TOOL={tool}"
                            ),
                        ]
                    )
                    seq += 1
        lines.extend(
            [
                f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                "T0",
                f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                (f"VISION_JOB_END JOB={job_id} EXPECTED_FRAMES={seq}"),
                "VISION_LIGHT_OFF",
                "",
            ]
        )
        return "\n".join(lines)
    if job_type == ROUGH_X_VERIFY_JOB_TYPE:
        lines = [
            f"; vision calibration job {job_id}",
            "G90",
            (
                f"VISION_JOB_BEGIN JOB={job_id} "
                f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
            ),
            ("VISION_PROFILE CAMERA=nozzle_cam " f"PROFILE={definition['profile']}"),
            definition["light_macro"],
        ]
        command_x = float(definition["command_x_mm"])
        for seq, tool in enumerate(("T0", "T1")):
            frame = f"{seq:02d}_{tool.lower()}_x{command_x:.3f}".replace(".", "p")
            lines.extend(
                [
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                    tool,
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                    f"G1 Y{pose['capture_y_mm']:.6f} F{feedrate:.3f}",
                    f"G1 X{command_x:.6f} F{feedrate:.3f}",
                    "M400",
                    f"G4 P{int(definition['tool_change_settle_ms'])}",
                    f"G4 P{int(definition['settle_ms'])}",
                    (
                        f"VISION_CAPTURE_SYNC JOB={job_id} SEQ={seq} "
                        f"FRAME={frame} CAMERA=nozzle_cam "
                        f"PROFILE={definition['profile']} TOOL={tool}"
                    ),
                ]
            )
        lines.extend(
            [
                f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                "T0",
                f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                "VISION_JOB_END JOB="
                f"{job_id} EXPECTED_FRAMES=2",
                "VISION_LIGHT_OFF",
                "",
            ]
        )
        return "\n".join(lines)
    if job_type == RED_MARKER_X_JOB_TYPE:
        lines = [
            f"; vision calibration job {job_id}",
            "G90",
            (
                f"VISION_JOB_BEGIN JOB={job_id} "
                f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
            ),
            ("VISION_PROFILE CAMERA=nozzle_cam " f"PROFILE={definition['profile']}"),
            definition["light_macro"],
        ]
        seq = 0
        for tool in ("T0", "T1"):
            lines.extend(
                [
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                    tool,
                    f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                    f"G1 Y{pose['capture_y_mm']:.6f} F{feedrate:.3f}",
                    "M400",
                    f"G4 P{int(definition['tool_change_settle_ms'])}",
                ]
            )
            for x_mm in definition["x_positions_mm"]:
                frame = f"{seq:02d}_{tool.lower()}_x{int(x_mm)}"
                lines.extend(
                    [
                        f"G1 X{float(x_mm):.6f} F{feedrate:.3f}",
                        "M400",
                        f"G4 P{int(definition['settle_ms'])}",
                        (
                            f"VISION_CAPTURE_SYNC JOB={job_id} SEQ={seq} "
                            f"FRAME={frame} CAMERA=nozzle_cam "
                            f"PROFILE={definition['profile']} TOOL={tool}"
                        ),
                    ]
                )
                seq += 1
        lines.extend(
            [
                f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                "T0",
                f"G1 Z{pose['safe_tool_change_z_mm']:.6f} F{feedrate:.3f}",
                (f"VISION_JOB_END JOB={job_id} " f"EXPECTED_FRAMES={seq}"),
                "VISION_LIGHT_OFF",
                "",
            ]
        )
        return "\n".join(lines)
    lines = [
        f"; vision calibration job {job_id}",
        "G90",
        (
            f"VISION_JOB_BEGIN JOB={job_id} "
            f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
        ),
        ("VISION_PROFILE CAMERA=nozzle_cam " f"PROFILE={definition['profile']}"),
        definition["light_macro"],
        f"T0",
        f"G1 Z{pose['z_mm']:.6f} F{feedrate:.3f}",
        (f"G1 X{pose['x_mm']:.6f} Y{pose['y_base_mm']:.6f} " f"F{feedrate:.3f}"),
    ]
    if job_type == BED_TAB_Y_JOB_TYPE:
        captures = [
            (seq, float(offset), f"y_{seq:02d}_{int(offset):02d}mm")
            for seq, offset in enumerate(definition["y_offsets_mm"])
        ]
    elif job_type == BED_TAB_CORNER_JOB_TYPE:
        offset = float(definition["capture_y_offset_mm"])
        captures = [
            (seq, offset, f"corner_duplicate_{seq:02d}")
            for seq in range(int(definition["duplicate_count"]))
        ]
    else:
        raise VisionCalibrationError(f"unsupported G-code job type {job_type}")
    last_offset = None
    for seq, offset, frame in captures:
        y = pose["y_base_mm"] + offset
        if job_type == BED_TAB_Y_JOB_TYPE or last_offset != offset:
            lines.append(f"G1 Y{y:.6f} F{feedrate:.3f}")
            last_offset = offset
        lines.extend(
            [
                "M400",
                f"G4 P{int(definition['settle_ms'])}",
                (
                    f"VISION_CAPTURE_SYNC JOB={job_id} SEQ={seq} "
                    f"FRAME={frame} CAMERA=nozzle_cam "
                    f"PROFILE={definition['profile']} TOOL=T0"
                ),
            ]
        )
    lines.extend(
        [
            (f"VISION_JOB_END JOB={job_id} " f"EXPECTED_FRAMES={len(captures)}"),
            "VISION_LIGHT_OFF",
            "",
        ]
    )
    return "\n".join(lines)


def _update_state(job_dir: Path, **values: Any) -> dict[str, Any]:
    state_path = job_dir / "state.json"
    state = load_json(state_path) if state_path.exists() else {}
    state.update(values)
    state["updated_at_utc"] = utc_now()
    atomic_write_json(state_path, state)
    return state


def _resolve_current_fact(
    requirement: str,
    fact_name: str,
    expected_definition_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = rebuild_catalog(CALIBRATION_ROOT)
    head = catalog.get("heads", {}).get(fact_name)
    if not isinstance(head, dict):
        raise VisionCalibrationError(
            f"required current fact {fact_name!r} is unavailable"
        )
    if head.get("fact_set_hash") in catalog.get("stale_fact_sets", {}):
        reasons = catalog["stale_fact_sets"][head["fact_set_hash"]]
        raise VisionCalibrationError(
            f"required current fact {fact_name!r} is stale: "
            + "; ".join(str(reason) for reason in reasons)
        )
    relative_path = head.get("fact_set_path")
    if not isinstance(relative_path, str):
        raise VisionCalibrationError(
            f"required fact {fact_name!r} has no source fact-set path"
        )
    fact_set_path = (CALIBRATION_ROOT / relative_path).resolve()
    if CALIBRATION_ROOT.resolve() not in fact_set_path.parents:
        raise VisionCalibrationError(
            f"required fact {fact_name!r} resolved outside calibration storage"
        )
    fact_set = load_json(fact_set_path)
    fact = next(
        (item for item in fact_set.get("facts", []) if item.get("name") == fact_name),
        None,
    )
    if fact is None:
        raise VisionCalibrationError(
            f"current fact set does not contain required fact {fact_name!r}"
        )
    if fact.get("definition_version") != expected_definition_version:
        raise VisionCalibrationError(
            f"required current fact {fact_name!r} has definition version "
            f"{fact.get('definition_version')!r}, expected "
            f"{expected_definition_version}"
        )
    return (
        {
            "requirement": requirement,
            "fact_name": fact_name,
            "fact_set_hash": head["fact_set_hash"],
            "fact_definition_version": fact.get("definition_version"),
            "source_job_id": head["job_id"],
            "source_analysis_run_id": head["analysis_run_id"],
        },
        fact,
    )


def _bed_tab_corner_prediction(
    bed_y_fact: dict[str, Any], target_y_offset_mm: float
) -> dict[str, Any]:
    value = bed_y_fact.get("value", {})
    vector = value.get("axis_vector_px_per_mm")
    target = value.get("observed_target") or {}
    line = target.get("reference_line_px")
    side = target.get("reference_tab_side")
    if (
        not isinstance(vector, list)
        or len(vector) != 2
        or not isinstance(line, list)
        or len(line) != 3
        or not isinstance(side, dict)
    ):
        raise VisionCalibrationError(
            "bed-tab Y fact lacks the observed tab geometry needed for corner prediction"
        )
    seam_y = float(target.get("reference_seam_y_px", line[1]))
    denominator = float(side["y1"]) - float(side["y0"])
    if abs(denominator) < 1.0e-9:
        raise VisionCalibrationError("bed-tab side geometry is degenerate")
    source_x = (
        float(side["x0"])
        + (seam_y - float(side["y0"]))
        * (float(side["x1"]) - float(side["x0"]))
        / denominator
    )
    source_corner = [source_x, seam_y]
    expected_corner = [
        source_corner[0] + float(vector[0]) * target_y_offset_mm,
        source_corner[1] + float(vector[1]) * target_y_offset_mm,
    ]
    return {
        "source_reference_corner_px": source_corner,
        "source_reference_y_offset_mm": 0.0,
        "capture_y_offset_mm": target_y_offset_mm,
        "expected_corner_px": expected_corner,
        "image_y_axis_vector_px_per_mm": [
            float(vector[0]),
            float(vector[1]),
        ],
    }


def prepare_job(
    name: str,
    *,
    job_type: str = BED_TAB_Y_JOB_TYPE,
    expected_fingerprint: str | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = _load_registry()
    if job_type not in JOB_TYPES:
        raise VisionCalibrationError(f"unsupported job type {job_type}")
    definition = json.loads(json.dumps(registry["job_types"][job_type]))
    input_facts = []
    input_fact_values: dict[str, dict[str, Any]] = {}
    corner_prediction = None
    if job_type == BED_TAB_CORNER_JOB_TYPE:
        sync_seed_facts()
    if job_type in (
        BED_TAB_CORNER_JOB_TYPE,
        RED_MARKER_X_JOB_TYPE,
        ROUGH_X_VERIFY_JOB_TYPE,
        FINE_NOZZLE_XZ_JOB_TYPE,
    ):
        for requirement in definition["requires"]:
            binding, fact = _resolve_current_fact(
                requirement["requirement"],
                requirement["fact_name"],
                int(requirement["fact_definition_version"]),
            )
            input_facts.append(binding)
            input_fact_values[requirement["requirement"]] = fact
    if job_type == BED_TAB_CORNER_JOB_TYPE:
        corner_prediction = _bed_tab_corner_prediction(
            input_fact_values["bed_y_model"],
            float(definition["capture_y_offset_mm"]),
        )
    if job_type == ROUGH_X_VERIFY_JOB_TYPE:
        partial_value = input_fact_values["partial_bed_coordinate_system"]["value"]
        active_value = input_fact_values["rough_x_active_snapshot"]["value"]
        bed_tab_x = float(partial_value["corner_printer_xyz_mm"][0])
        active_bed_tab_x = float(active_value["bed_tab_x_mm"])
        if abs(bed_tab_x - active_bed_tab_x) > 1.0e-9:
            raise VisionCalibrationError(
                "rough-X activation and partial bed coordinate system use "
                "different bed-tab X values"
            )
        definition["command_x_mm"] = bed_tab_x + float(
            definition["verification_offset_x_mm"]
        )
    if job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        partial_value = input_fact_values["partial_bed_coordinate_system"]["value"]
        bed_tab_x = float(partial_value["corner_printer_xyz_mm"][0])
        definition["resolved_x_positions_mm"] = [
            bed_tab_x + float(offset)
            for offset in definition["x_offsets_from_bed_tab_mm"]
        ]
    resolved = _resolve_preflight(
        status or query_printer_status(),
        job_type,
        definition,
        expected_fingerprint,
    )
    if input_facts:
        resolved["scope"]["input_fact_hashes"] = {
            item["requirement"]: item["fact_set_hash"] for item in input_facts
        }
        resolved["applicability_hash"] = canonical_hash(resolved["scope"])
    if job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        active_value = input_fact_values["rough_x_active_snapshot"]["value"]
        expected_active = {
            "t0_x_endstop_mm": float(active_value["t0_applied_x_endstop_mm"]),
            "t1_x_endstop_mm": float(active_value["t1_applied_x_endstop_mm"]),
        }
        if resolved["active_calibration_snapshot"] != expected_active:
            raise VisionCalibrationError(
                "active T0/T1 X calibration does not match the verified "
                "rough-X snapshot"
            )
    job_id = _job_id(name)
    job_dir = CALIBRATION_ROOT / "jobs" / job_id
    if job_dir.exists():
        raise VisionCalibrationError(f"job already exists: {job_id}")
    frames = []
    if job_type == BED_TAB_Y_JOB_TYPE:
        forward_count = len(definition["y_offsets_mm"]) // 2
        for seq, offset in enumerate(definition["y_offsets_mm"]):
            frames.append(
                {
                    "seq": seq,
                    "frame": f"y_{seq:02d}_{int(offset):02d}mm",
                    "camera": "nozzle_cam",
                    "profile": definition["profile"],
                    "tool": "T0",
                    "y_offset_mm": offset,
                    "commanded_position_mm": [
                        resolved["pose"]["x_mm"],
                        resolved["pose"]["y_base_mm"] + float(offset),
                        resolved["pose"]["z_mm"],
                    ],
                    "pass": "forward" if seq < forward_count else "reverse",
                }
            )
    elif job_type == BED_TAB_CORNER_JOB_TYPE:
        offset = float(definition["capture_y_offset_mm"])
        for seq in range(int(definition["duplicate_count"])):
            frames.append(
                {
                    "seq": seq,
                    "frame": f"corner_duplicate_{seq:02d}",
                    "camera": "nozzle_cam",
                    "profile": definition["profile"],
                    "tool": "T0",
                    "y_offset_mm": offset,
                    "duplicate_index": seq,
                    "commanded_position_mm": [
                        resolved["pose"]["x_mm"],
                        resolved["pose"]["y_base_mm"] + offset,
                        resolved["pose"]["z_mm"],
                    ],
                    "pass": "duplicate",
                    "discard_fresh_frames": int(
                        definition["discard_fresh_frames"]
                    ),
                }
            )
    elif job_type == RED_MARKER_X_JOB_TYPE:
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
                        "commanded_position_mm": [
                            float(x_mm),
                            resolved["pose"]["capture_y_mm"],
                            resolved["pose"]["capture_z_mm"],
                        ],
                        "pass": tool.lower(),
                        "discard_fresh_frames": int(
                            definition["discard_fresh_frames"]
                        ),
                    }
                )
    elif job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        offsets = [
            float(value) for value in definition["x_offsets_from_bed_tab_mm"]
        ]
        x_positions = [
            float(value) for value in definition["resolved_x_positions_mm"]
        ]
        for tool in ("T0", "T1"):
            for z_index, z_mm in enumerate(definition["z_positions_mm"]):
                row = list(zip(offsets, x_positions))
                if z_index % 2:
                    row.reverse()
                for offset, x_mm in row:
                    seq = len(frames)
                    frame_name = (
                        f"{seq:02d}_{tool.lower()}_"
                        f"x{x_mm:.3f}_z{float(z_mm):.3f}"
                    ).replace(".", "p")
                    frames.append(
                        {
                            "seq": seq,
                            "frame": frame_name,
                            "camera": "nozzle_cam",
                            "profile": definition["profile"],
                            "tool": tool,
                            "x_offset_from_bed_tab_mm": offset,
                            "x_mm": x_mm,
                            "z_mm": float(z_mm),
                            "commanded_position_mm": [
                                x_mm,
                                resolved["pose"]["capture_y_mm"],
                                float(z_mm),
                            ],
                            "pass": f"{tool.lower()}_z{float(z_mm):g}",
                            "discard_fresh_frames": int(
                                definition["discard_fresh_frames"]
                            ),
                        }
                    )
    else:
        command_x = float(definition["command_x_mm"])
        for tool in ("T0", "T1"):
            seq = len(frames)
            frame_name = f"{seq:02d}_{tool.lower()}_x{command_x:.3f}".replace(
                ".", "p"
            )
            frames.append(
                {
                    "seq": seq,
                    "frame": frame_name,
                    "camera": "nozzle_cam",
                    "profile": definition["profile"],
                    "tool": tool,
                    "x_mm": command_x,
                    "commanded_position_mm": [
                        command_x,
                        resolved["pose"]["capture_y_mm"],
                        resolved["pose"]["capture_z_mm"],
                    ],
                    "pass": "verification",
                    "discard_fresh_frames": int(
                        definition["discard_fresh_frames"]
                    ),
                }
            )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": job_type,
        "definition_version": definition["definition_version"],
        "created_at_utc": utc_now(),
        "camera": "nozzle_cam",
        "profile": definition["profile"],
        "light_macro": definition["light_macro"],
        "localizer": definition["localizer"],
        "publish_on_accept": bool(definition["publish_on_accept"]),
        "frame_count": len(frames),
        "frames": frames,
        "input_facts": input_facts,
        "motion": {
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "resolved_pose": resolved["pose"],
            "axis_minimum": resolved["axis_minimum"],
            "axis_maximum": resolved["axis_maximum"],
            "no_implicit_homing": True,
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
    if job_type in (RED_MARKER_X_JOB_TYPE, FINE_NOZZLE_XZ_JOB_TYPE):
        manifest["active_calibration_snapshot"] = resolved[
            "active_calibration_snapshot"
        ]
    if corner_prediction is not None:
        prior_value = input_fact_values["bed_tab_corner_prior"]["value"]
        z_value = input_fact_values["tab_plane_z"]["value"]
        manifest["corner_reference"] = {
            **corner_prediction,
            "corner_printer_xyz_mm": prior_value["xyz_mm"],
            "tab_to_print_plane_z_mm": z_value["z_offset_mm"],
            "prior_provisional": bool(prior_value.get("provisional")),
        }
    if job_type == RED_MARKER_X_JOB_TYPE:
        partial_value = input_fact_values["partial_bed_coordinate_system"]["value"]
        bed_y_value = input_fact_values["bed_y_model"]["value"]
        manifest["red_marker_reference"] = {
            "corner_pixel_xy_px": partial_value["corner_pixel_xy_px"],
            "corner_pixel_capture_y_mm": partial_value[
                "corner_pixel_capture_y_mm"
            ],
            "corner_printer_xyz_mm": partial_value["corner_printer_xyz_mm"],
            "image_y_axis_vector_px_per_mm": bed_y_value[
                "axis_vector_px_per_mm"
            ],
            "capture_y_mm": float(definition["capture_y_mm"]),
            "capture_z_mm": float(definition["capture_z_mm"]),
        }
    if job_type == ROUGH_X_VERIFY_JOB_TYPE:
        partial_value = input_fact_values["partial_bed_coordinate_system"]["value"]
        x_axis_value = input_fact_values["image_x_axis"]["value"]
        manifest["verification_reference"] = {
            "command_x_mm": float(definition["command_x_mm"]),
            "expected_offset_mm": float(definition["verification_offset_x_mm"]),
            "corner_pixel_xy_px": partial_value["corner_pixel_xy_px"],
            "corner_pixel_capture_y_mm": partial_value[
                "corner_pixel_capture_y_mm"
            ],
            "corner_printer_xyz_mm": partial_value["corner_printer_xyz_mm"],
            "image_y_axis_vector_px_per_mm": partial_value[
                "image_y_axis_vector_px_per_mm"
            ],
            "image_x_axis_vector_px_per_mm": x_axis_value[
                "axis_vector_px_per_mm"
            ],
            "capture_y_mm": float(definition["capture_y_mm"]),
            "capture_z_mm": float(definition["capture_z_mm"]),
            "active_x_endstops_mm": {
                "t0_x_endstop_mm": float(
                    input_fact_values["rough_x_active_snapshot"]["value"][
                        "t0_applied_x_endstop_mm"
                    ]
                ),
                "t1_x_endstop_mm": float(
                    input_fact_values["rough_x_active_snapshot"]["value"][
                        "t1_applied_x_endstop_mm"
                    ]
                ),
            },
        }
    if job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        partial_value = input_fact_values["partial_bed_coordinate_system"]["value"]
        manifest["grid_reference"] = {
            "bed_tab_x_mm": float(partial_value["corner_printer_xyz_mm"][0]),
            "x_offsets_from_bed_tab_mm": definition[
                "x_offsets_from_bed_tab_mm"
            ],
            "resolved_x_positions_mm": definition["resolved_x_positions_mm"],
            "z_positions_mm": definition["z_positions_mm"],
            "capture_y_mm": float(definition["capture_y_mm"]),
            "survey_only": True,
            "analysis_contract_pending": True,
        }
    placeholder_gcode = _gcode(
        job_id,
        HASH_PLACEHOLDER,
        HASH_PLACEHOLDER,
        job_type,
        definition,
        resolved["pose"],
    )
    manifest["gcode_hash"] = _gcode_hash(placeholder_gcode)
    manifest["manifest_hash"] = content_hash(manifest, "manifest_hash")
    final_gcode = _gcode(
        job_id,
        manifest["manifest_hash"],
        manifest["gcode_hash"],
        job_type,
        definition,
        resolved["pose"],
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
        schema_version=SCHEMA_VERSION,
        job_id=job_id,
        state="prepared",
        committed_frame_count=0,
    )
    GCODE_ROOT.mkdir(parents=True, exist_ok=True)
    gcode_path = GCODE_ROOT / f"{job_id}.gcode"
    if gcode_path.exists():
        raise VisionCalibrationError(f"G-code target already exists: {gcode_path}")
    shutil.copyfile(job_dir / "acquisition.gcode", gcode_path)
    rebuild_and_render()
    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(job_dir / "manifest.json"),
        "gcode_path": str(gcode_path),
        "manifest_hash": manifest["manifest_hash"],
        "gcode_hash": manifest["gcode_hash"],
        "applicability_hash": manifest["applicability_hash"],
        "review_url": f"/vision/calibration/jobs/{job_id}/",
    }


def _start_print(job_id: str) -> None:
    _moonraker_post("/printer/print/start", {"filename": f"vision_jobs/{job_id}.gcode"})


def _wait_for_acquisition(job_id: str, timeout: float = 180.0) -> dict[str, Any]:
    job_dir = CALIBRATION_ROOT / "jobs" / job_id
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = load_json(job_dir / "state.json")
        if state.get("state") == "acquired":
            return state
        if state.get("state") == "failed":
            raise VisionCalibrationError(
                f"vision acquisition failed: {state.get('failure')}"
            )
        time.sleep(0.5)
    raise VisionCalibrationError(f"timed out waiting for acquisition job {job_id}")


def _frame_integrity(
    manifest: dict[str, Any], job_dir: Path
) -> tuple[list[Path], list[dict[str, Any]]]:
    paths: list[Path] = []
    sidecars: list[dict[str, Any]] = []
    dimensions: set[tuple[int, int]] = set()
    profiles: set[str] = set()
    framebuffer_sequences: list[int] = []
    for frame in manifest["frames"]:
        image_path = job_dir / "frames" / f"{frame['frame']}.jpg"
        sidecar_path = job_dir / "frames" / f"{frame['frame']}.json"
        if not image_path.is_file() or not sidecar_path.is_file():
            raise VisionCalibrationError(
                f"incomplete frame artifacts for {frame['frame']}"
            )
        sidecar = load_json(sidecar_path)
        if sidecar.get("sha256") != sha256_file(image_path):
            raise VisionCalibrationError(f"image hash mismatch for {frame['frame']}")
        if sidecar.get("job_seq") != frame["seq"]:
            raise VisionCalibrationError(
                f"sidecar sequence mismatch for {frame['frame']}"
            )
        if int(sidecar.get("capture_errors") or 0) != 0:
            raise VisionCalibrationError(
                f"frame {frame['frame']} was contaminated by capture errors"
            )
        dimensions.add((int(sidecar["width"]), int(sidecar["height"])))
        profile_names = sidecar.get("camera_profile", {}).get("profile_names") or []
        if manifest["profile"] not in profile_names:
            raise VisionCalibrationError(
                f"frame {frame['frame']} used the wrong camera profile"
            )
        profiles.update(str(item) for item in profile_names)
        framebuffer_sequences.append(int(sidecar["framebuffer_seq"]))
        if manifest["job_type"] in (
            BED_TAB_CORNER_JOB_TYPE,
            RED_MARKER_X_JOB_TYPE,
            ROUGH_X_VERIFY_JOB_TYPE,
        ):
            discarded = sidecar.get("discarded_framebuffer_sequences")
            if (
                not isinstance(discarded, list)
                or len(discarded) != 1
                or not isinstance(discarded[0], int)
                or discarded[0] >= int(sidecar["framebuffer_seq"])
            ):
                raise VisionCalibrationError(
                    f"frame {frame['frame']} lacks its required discarded "
                    "fresh-frame provenance"
                )
        paths.append(image_path)
        sidecars.append(sidecar)
    if len(dimensions) != 1:
        raise VisionCalibrationError("committed frame dimensions changed")
    if len(set(framebuffer_sequences)) != len(framebuffer_sequences):
        raise VisionCalibrationError("stale framebuffer sequence was committed")
    return paths, sidecars


def _analysis_run_id(manifest: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{manifest['manifest_hash'].split(':', 1)[1][:10]}"


def _report_markdown(
    manifest: dict[str, Any], analysis: dict[str, Any], result: dict[str, Any]
) -> str:
    if manifest.get("job_type") == ROUGH_X_VERIFY_JOB_TYPE:
        lines = [
            "# Rough T0/T1 X verification",
            "",
            f"- Job: `{manifest['job_id']}`",
            f"- Analysis: `{analysis['analysis_run_id']}`",
            f"- Result: **{analysis['state']}**",
            (
                "- Commanded X: "
                f"`{result.get('verification_command_x_mm')}` mm"
            ),
            (
                "- Expected marker offset from bed-tab corner: "
                f"`{result.get('expected_offset_mm')}` mm"
            ),
            (
                "- T0 marker offset / residual: "
                f"`{result.get('t0_marker_offset_mm')}` mm / "
                f"`{result.get('t0_residual_mm')}` mm"
            ),
            (
                "- T1 marker offset / residual: "
                f"`{result.get('t1_marker_offset_mm')}` mm / "
                f"`{result.get('t1_residual_mm')}` mm"
            ),
            (
                "- Marker coincidence residual: "
                f"`{result.get('marker_coincidence_residual_mm')}` mm"
            ),
            (
                "- Cross-tool registration correlation: "
                f"`{(result.get('cross_registration') or {}).get('minimum_correlation')}`"
            ),
            "",
            "Both images were acquired at the same X=bed-tab-X+10 mm command. "
            "Acceptance requires each marker to be at the absolute +10 mm "
            "image-X position and the two marker image-X coordinates to agree.",
        ]
        if result.get("warnings"):
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in result["warnings"])
        if analysis["state"] == "rejected":
            lines.extend(["", "## Rejection reasons", ""])
            lines.extend(f"- {reason}" for reason in result.get("reasons", []))
        return "\n".join(lines) + "\n"
    if manifest.get("job_type") == RED_MARKER_X_JOB_TYPE:
        lines = [
            "# Coarse T0/T1 red-marker X sweep",
            "",
            f"- Job: `{manifest['job_id']}`",
            f"- Analysis: `{analysis['analysis_run_id']}`",
            f"- Result: **{analysis['state']}**",
            (
                "- Common image X-axis vector: "
                f"`{result.get('common_axis_vector_px_per_mm')}` px/mm"
            ),
            (
                "- Accepted T0 X positions: "
                f"`{result.get('accepted_x_mm', {}).get('T0')}` mm"
            ),
            (
                "- Accepted T1 X positions: "
                f"`{result.get('accepted_x_mm', {}).get('T1')}` mm"
            ),
            (
                "- Common commanded X: "
                f"`{result.get('common_commanded_x_mm')}` mm"
            ),
            (
                "- Cross-tool marker shift: "
                f"`{result.get('cross_tool_shift_px')}` px"
            ),
            (
                "- T0 marker to bed-tab X: "
                f"`{result.get('t0_red_marker_to_bed_tab_x_mm')}` mm"
            ),
            (
                "- T1 marker to bed-tab X: "
                f"`{result.get('t1_red_marker_to_bed_tab_x_mm')}` mm"
            ),
            "",
            "Red color only proposed candidate regions. The published coordinate "
            "facts come from bidirectional grayscale/CLAHE registration and the "
            "dependency-bound bed-tab coordinate system.",
            "This job publishes facts but does not modify calib.yaml or live "
            "Klipper coordinates.",
        ]
        if result.get("warnings"):
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in result["warnings"])
        if analysis["state"] == "rejected":
            lines.extend(["", "## Rejection reasons", ""])
            lines.extend(f"- {reason}" for reason in result.get("reasons", []))
        return "\n".join(lines) + "\n"
    if manifest.get("job_type", BED_TAB_Y_JOB_TYPE) == BED_TAB_CORNER_JOB_TYPE:
        corner = result.get("corner_pixel_xy_px")
        reference = manifest["corner_reference"]
        lines = [
            "# Bed-tab corner reference analysis",
            "",
            f"- Job: `{manifest['job_id']}`",
            f"- Analysis: `{analysis['analysis_run_id']}`",
            f"- Result: **{analysis['state']}**",
            f"- Observed corner pixel: `{corner}` px",
            (
                "- Provisional printer corner XYZ: "
                f"`{reference['corner_printer_xyz_mm']}` mm"
            ),
            (
                "- Image Y-axis vector: "
                f"`{reference['image_y_axis_vector_px_per_mm']}` px/mm"
            ),
            ("- Upstream-predicted pixel: " f"`{reference['expected_corner_px']}` px"),
            (
                "- Prediction-to-localization distance: "
                f"`{result.get('expected_distance_px')}` px"
            ),
            (
                "- Duplicate repeatability: "
                f"`{result.get('repeatability_rms_px')}` px RMS / "
                f"`{result.get('repeatability_max_px')}` px maximum"
            ),
            (
                "- Duplicate registration correlation: "
                f"`{result.get('minimum_correlation')}` minimum / "
                f"`{result.get('median_correlation')}` median"
            ),
            (
                "- Usable/line-confirmed duplicates: "
                f"`{result.get('usable_frame_count')}` / "
                f"`{result.get('line_confirmation_count')}`"
            ),
            "",
            "The pixel location is bound to the exact current Y-parallax fact, "
            "the provisional bed-tab printer-XYZ prior, and the tab-plane Z seed.",
            "This job does not modify calib.yaml or live Klipper coordinates.",
        ]
        if reference.get("prior_provisional"):
            lines.extend(
                [
                    "",
                    "## Provisional prior",
                    "",
                    "The printer XYZ prior is intentionally provisional. Replacing "
                    "and publishing the measured prior will make this corner reference "
                    "stale and require this job to be rerun.",
                ]
            )
        if result.get("warnings"):
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in result["warnings"])
        if analysis["state"] == "rejected":
            lines.extend(["", "## Rejection reasons", ""])
            lines.extend(f"- {reason}" for reason in result.get("reasons", []))
        return "\n".join(lines) + "\n"

    axis_vector = result.get("axis_vector_px_per_mm")
    has_axis_vector = (
        isinstance(axis_vector, list)
        and len(axis_vector) == 2
        and all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in axis_vector
        )
    )
    lines = [
        "# Bed-tab Y/parallax analysis",
        "",
        f"- Job: `{manifest['job_id']}`",
        f"- Analysis: `{analysis['analysis_run_id']}`",
        f"- Result: **{analysis['state']}**",
        (
            "- Axis vector: " f"`[{axis_vector[0]:.6f}, {axis_vector[1]:.6f}] px/mm`"
            if has_axis_vector
            else "- Axis vector: unavailable"
        ),
        f"- Scalar scale: `{result.get('scale_px_per_mm')}` px/mm",
        f"- Inverse scale: `{result.get('inverse_scale_mm_per_px')}` mm/px",
        f"- Image-axis angle: `{result.get('angle_deg')}` degrees",
        (
            "- Edge localizer: "
            f"`{result.get('localizer', {}).get('kind')}` "
            f"version `{result.get('localizer', {}).get('version')}`"
        ),
        f"- Discovered edge candidates: `{result.get('discovered_candidate_count', 0)}`",
        f"- Selected edge: `{result.get('selected_candidate_id')}`",
        (
            "- Joint residual RMS: "
            f"`{result.get('joint_residual_rms_px')}` px / "
            f"`{result.get('joint_residual_rms_mm')}` mm"
        ),
        (
            "- Duplicate-position disagreement: "
            f"`{result.get('duplicate_position_disagreement_px')}` px / "
            f"`{result.get('duplicate_position_disagreement_mm')}` mm"
        ),
        (
            "- Forward/reverse: "
            f"`{result.get('forward_reverse_magnitude_delta_fraction')}` magnitude "
            f"fraction, `{result.get('forward_reverse_angle_delta_deg')}` degrees"
        ),
        "",
        "This measurement is relative. The image-axis sign was measured, not assumed.",
        (
            "Accepted facts publish immediately by job policy. Publication does "
            "not modify calib.yaml or Klipper."
        ),
    ]
    observed_target = result.get("observed_target")
    if observed_target:
        lines.extend(
            [
                "",
                "## Observed target",
                "",
                f"- Reference line: `{observed_target['reference_line_px']}` px",
                f"- Duplicate line: `{observed_target['duplicate_line_px']}` px",
                f"- Tracking strip: `{observed_target['tracking_strip_px']}` px",
                (
                    "- Duplicate zero-frame agreement: "
                    f"`{observed_target['duplicate_y_delta_px']}` px vertically, "
                    f"`{observed_target['duplicate_overlap_fraction']}` overlap"
                ),
                "",
                (
                    "These pixel coordinates were discovered from this acquisition. "
                    "They are provenance, not configured inputs."
                ),
            ]
        )
    if result.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
    if analysis["state"] == "rejected":
        lines.extend(["", "## Rejection reasons", ""])
        lines.extend(f"- {reason}" for reason in result.get("reasons", []))
    return "\n".join(lines) + "\n"


def analyze_job(job_id: str) -> dict[str, Any]:
    job_dir = CALIBRATION_ROOT / "jobs" / _sanitize(job_id)
    manifest = validate_manifest(load_json(job_dir / "manifest.json"))
    if manifest["job_type"] == FINE_NOZZLE_XZ_JOB_TYPE:
        raise VisionCalibrationError(
            "fine nozzle X/Z survey analysis is intentionally pending; "
            "the acquired frames are planning evidence, not calibration facts"
        )
    if manifest["job_type"] == BED_TAB_Y_JOB_TYPE and (
        manifest["definition_version"] != 5
    ):
        raise VisionCalibrationError(
            "only definition-v5 bed-tab Y jobs use the current localizer"
        )
    if manifest["job_type"] == BED_TAB_CORNER_JOB_TYPE and (
        manifest["definition_version"] != 5
    ):
        raise VisionCalibrationError(
            "only definition-v5 bed-tab corner jobs use the current localizer"
        )
    if manifest["job_type"] == RED_MARKER_X_JOB_TYPE and (
        manifest["definition_version"] != 5
    ):
        raise VisionCalibrationError(
            "only definition-v5 red-marker jobs use the current localizer"
        )
    if manifest["job_type"] == ROUGH_X_VERIFY_JOB_TYPE and (
        manifest["definition_version"] != 5
    ):
        raise VisionCalibrationError(
            "only definition-v5 rough-X verification jobs use the current localizer"
        )
    state = load_json(job_dir / "state.json")
    if state.get("state") not in ("acquired", "analyzed", "rejected"):
        raise VisionCalibrationError(
            f"job state {state.get('state')!r} cannot be analyzed"
        )
    frame_paths, sidecars = _frame_integrity(manifest, job_dir)
    analysis_run_id = _analysis_run_id(manifest)
    analysis_dir = job_dir / "analysis" / analysis_run_id
    if analysis_dir.exists():
        raise VisionCalibrationError(f"analysis run already exists: {analysis_run_id}")
    staging_dir = analysis_dir.with_name(f".{analysis_run_id}.tmp")
    if staging_dir.exists():
        raise VisionCalibrationError(
            f"analysis staging directory already exists: {staging_dir.name}"
        )
    staging_dir.mkdir(parents=True)
    try:
        if manifest["job_type"] == BED_TAB_Y_JOB_TYPE:
            result_details = analyze_bed_tab_y_scale(
                frame_paths,
                staging_dir / "artifacts",
                offsets_mm=[
                    float(frame["y_offset_mm"]) for frame in manifest["frames"]
                ],
                localizer=manifest["localizer"],
            )
        elif manifest["job_type"] == BED_TAB_CORNER_JOB_TYPE:
            result_details = analyze_bed_tab_corner(
                frame_paths,
                staging_dir / "artifacts",
                expected_corner_px=manifest["corner_reference"]["expected_corner_px"],
                localizer=manifest["localizer"],
            )
        elif manifest["job_type"] == RED_MARKER_X_JOB_TYPE:
            result_details = analyze_red_marker_x_sweep(
                frame_paths,
                staging_dir / "artifacts",
                frames=manifest["frames"],
                reference=manifest["red_marker_reference"],
                localizer=manifest["localizer"],
            )
        else:
            result_details = analyze_rough_x_verification(
                frame_paths,
                staging_dir / "artifacts",
                frames=manifest["frames"],
                reference=manifest["verification_reference"],
                localizer=manifest["localizer"],
            )
        for artifact in result_details.get("artifacts", {}).values():
            staging_path = Path(artifact["path"])
            relative_path = staging_path.relative_to(staging_dir)
            artifact["path"] = str(analysis_dir / relative_path)
        state_name = "accepted" if result_details["accepted"] else "rejected"
        analysis = {
            "schema": ANALYSIS_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "analysis_run_id": analysis_run_id,
            "job_id": manifest["job_id"],
            "job_type": manifest["job_type"],
            "definition_version": manifest["definition_version"],
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
                "dependencies": manifest.get("input_facts", []),
            },
            "diagnostics": result_details,
            "fact_set_path": "fact_set.json" if result_details["accepted"] else None,
            "analysis_hash": "",
        }
        analysis["analysis_hash"] = content_hash(analysis, "analysis_hash")
        fact_set = None
        if result_details["accepted"]:
            width = int(sidecars[0]["width"])
            height = int(sidecars[0]["height"])
            if manifest["job_type"] == BED_TAB_Y_JOB_TYPE:
                facts = [
                    {
                        "name": "camera.nozzle_cam.bed_tab.y_parallax_model",
                        "definition_version": 5,
                        "role": "coordinate_system",
                        "dependencies": [],
                        "value_items": [
                            {
                                "field": "axis_vector_px_per_mm",
                                "role": "coordinate_system",
                            },
                            {"field": "camera", "role": "diagnostic"},
                            {"field": "profile", "role": "diagnostic"},
                            {"field": "light_macro", "role": "diagnostic"},
                            {
                                "field": "image_dimensions_px",
                                "role": "diagnostic",
                            },
                            {
                                "field": "applicability_hash",
                                "role": "diagnostic",
                            },
                            {"field": "observed_target", "role": "diagnostic"},
                            {"field": "quality", "role": "diagnostic"},
                            {
                                "field": "supporting_artifact_hashes",
                                "role": "diagnostic",
                            },
                        ],
                        "value": {
                            "axis_vector_px_per_mm": result_details[
                                "axis_vector_px_per_mm"
                            ],
                            "camera": manifest["camera"],
                            "profile": manifest["profile"],
                            "light_macro": manifest["light_macro"],
                            "image_dimensions_px": [width, height],
                            "applicability_hash": manifest["applicability_hash"],
                            "observed_target": result_details["observed_target"],
                            "quality": {
                                "usable_frame_count": result_details[
                                    "usable_frame_count"
                                ],
                                "commanded_span_mm": result_details[
                                    "commanded_span_mm"
                                ],
                                "discovered_candidate_count": result_details[
                                    "discovered_candidate_count"
                                ],
                                "selected_candidate_id": result_details[
                                    "selected_candidate_id"
                                ],
                                "minimum_correlation": result_details[
                                    "minimum_correlation"
                                ],
                                "median_correlation": result_details[
                                    "median_correlation"
                                ],
                                "joint_residual_rms_px": result_details[
                                    "joint_residual_rms_px"
                                ],
                                "joint_residual_rms_mm": result_details[
                                    "joint_residual_rms_mm"
                                ],
                                "duplicate_position_disagreement_px": result_details[
                                    "duplicate_position_disagreement_px"
                                ],
                                "duplicate_position_disagreement_mm": result_details[
                                    "duplicate_position_disagreement_mm"
                                ],
                                "forward_reverse_magnitude_delta_fraction": result_details[
                                    "forward_reverse_magnitude_delta_fraction"
                                ],
                                "forward_reverse_angle_delta_deg": result_details[
                                    "forward_reverse_angle_delta_deg"
                                ],
                                "warnings": result_details["warnings"],
                            },
                            "supporting_artifact_hashes": {
                                name: item["sha256"]
                                for name, item in result_details["artifacts"].items()
                            },
                        },
                    }
                ]
                observed_provenance = result_details["observed_target"]
            elif manifest["job_type"] == BED_TAB_CORNER_JOB_TYPE:
                dependencies = [
                    {
                        "fact_name": item["fact_name"],
                        "fact_set_hash": item["fact_set_hash"],
                    }
                    for item in manifest["input_facts"]
                ]
                reference = manifest["corner_reference"]
                facts = [
                    {
                        "name": "camera.nozzle_cam.partial_bed_coordinate_system",
                        "definition_version": 5,
                        "role": "coordinate_system",
                        "dependencies": dependencies,
                        "value_items": [
                            {
                                "field": "corner_pixel_xy_px",
                                "role": "coordinate_system",
                            },
                            {
                                "field": "corner_pixel_capture_y_mm",
                                "role": "coordinate_system",
                            },
                            {
                                "field": "corner_printer_xyz_mm",
                                "role": "coordinate_system",
                            },
                            {
                                "field": "image_y_axis_vector_px_per_mm",
                                "role": "coordinate_system",
                            },
                            {
                                "field": "tab_to_print_plane_z_mm",
                                "role": "coordinate_system",
                            },
                            {"field": "mapping_convention", "role": "diagnostic"},
                            {"field": "camera", "role": "diagnostic"},
                            {"field": "profile", "role": "diagnostic"},
                            {"field": "light_macro", "role": "diagnostic"},
                            {
                                "field": "image_dimensions_px",
                                "role": "diagnostic",
                            },
                            {
                                "field": "capture_pose_mm",
                                "role": "diagnostic",
                            },
                            {
                                "field": "upstream_prediction",
                                "role": "diagnostic",
                            },
                            {
                                "field": "prior_provisional",
                                "role": "diagnostic",
                            },
                            {"field": "quality", "role": "diagnostic"},
                            {
                                "field": "supporting_artifact_hashes",
                                "role": "diagnostic",
                            },
                        ],
                        "value": {
                            "corner_pixel_xy_px": result_details["corner_pixel_xy_px"],
                            "corner_pixel_capture_y_mm": float(
                                manifest["frames"][0]["commanded_position_mm"][1]
                            ),
                            "corner_printer_xyz_mm": reference["corner_printer_xyz_mm"],
                            "image_y_axis_vector_px_per_mm": reference[
                                "image_y_axis_vector_px_per_mm"
                            ],
                            "tab_to_print_plane_z_mm": reference[
                                "tab_to_print_plane_z_mm"
                            ],
                            "mapping_convention": (
                                "pixel_xy = corner_pixel_xy_px + "
                                "image_y_axis_vector_px_per_mm * "
                                "(capture_y_mm - corner_pixel_capture_y_mm)"
                            ),
                            "camera": manifest["camera"],
                            "profile": manifest["profile"],
                            "light_macro": manifest["light_macro"],
                            "image_dimensions_px": [width, height],
                            "capture_pose_mm": manifest["frames"][0][
                                "commanded_position_mm"
                            ],
                            "upstream_prediction": {
                                "expected_corner_px": reference["expected_corner_px"],
                                "distance_px": result_details["expected_distance_px"],
                            },
                            "prior_provisional": reference["prior_provisional"],
                            "quality": {
                                key: result_details[key]
                                for key in (
                                    "usable_frame_count",
                                    "line_confirmation_count",
                                    "minimum_correlation",
                                    "median_correlation",
                                    "repeatability_rms_px",
                                    "repeatability_max_px",
                                    "maximum_representation_spread_px",
                                    "maximum_forward_reverse_disagreement_px",
                                    "warnings",
                                )
                            },
                            "supporting_artifact_hashes": {
                                name: item["sha256"]
                                for name, item in result_details["artifacts"].items()
                            },
                        },
                    }
                ]
                observed_provenance = {
                    "corner_pixel_xy_px": result_details["corner_pixel_xy_px"],
                    "corner_pixel_capture_y_mm": float(
                        manifest["frames"][0]["commanded_position_mm"][1]
                    ),
                    "selected_candidate": result_details["selected_candidate"],
                }
            elif manifest["job_type"] == RED_MARKER_X_JOB_TYPE:
                dependencies = [
                    {
                        "fact_name": item["fact_name"],
                        "fact_set_hash": item["fact_set_hash"],
                    }
                    for item in manifest["input_facts"]
                ]
                diagnostic_fields = [
                    {"field": "camera", "role": "diagnostic"},
                    {"field": "profile", "role": "diagnostic"},
                    {"field": "light_macro", "role": "diagnostic"},
                    {"field": "image_dimensions_px", "role": "diagnostic"},
                    {"field": "quality", "role": "diagnostic"},
                    {
                        "field": "supporting_artifact_hashes",
                        "role": "diagnostic",
                    },
                ]
                diagnostics = {
                    "camera": manifest["camera"],
                    "profile": manifest["profile"],
                    "light_macro": manifest["light_macro"],
                    "image_dimensions_px": [width, height],
                    "quality": {
                        "accepted_x_mm": result_details["accepted_x_mm"],
                        "tool_axis_vectors_px_per_mm": result_details[
                            "tool_axis_vectors_px_per_mm"
                        ],
                        "tool_fit_rms_px": result_details["tool_fit_rms_px"],
                        "tool_minimum_correlation": result_details[
                            "tool_minimum_correlation"
                        ],
                        "tool_scale_delta_fraction": result_details[
                            "tool_scale_delta_fraction"
                        ],
                        "tool_angle_delta_deg": result_details[
                            "tool_angle_delta_deg"
                        ],
                        "cross_tool_minimum_correlation": result_details[
                            "cross_tool_minimum_correlation"
                        ],
                        "cross_tool_shift_px": result_details[
                            "cross_tool_shift_px"
                        ],
                        "warnings": result_details["warnings"],
                    },
                    "supporting_artifact_hashes": {
                        name: item["sha256"]
                        for name, item in result_details["artifacts"].items()
                    },
                }

                def coordinate_fact(
                    name: str,
                    coordinate_value: dict[str, Any],
                    coordinate_fields: list[str],
                ) -> dict[str, Any]:
                    return {
                        "name": name,
                        "definition_version": 5,
                        "role": "coordinate_system",
                        "dependencies": dependencies,
                        "value_items": [
                            *[
                                {"field": field, "role": "coordinate_system"}
                                for field in coordinate_fields
                            ],
                            *diagnostic_fields,
                        ],
                        "value": {**coordinate_value, **diagnostics},
                    }

                common_x = result_details["common_commanded_x_mm"]
                facts = [
                    coordinate_fact(
                        "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2",
                        {
                            "axis_vector_px_per_mm": result_details[
                                "common_axis_vector_px_per_mm"
                            ]
                        },
                        ["axis_vector_px_per_mm"],
                    ),
                    coordinate_fact(
                        "tool.t0.red_marker_to_bed_tab_x_mm",
                        {
                            "offset_mm": result_details[
                                "t0_red_marker_to_bed_tab_x_mm"
                            ],
                            "reference_commanded_x_mm": common_x,
                        },
                        ["offset_mm", "reference_commanded_x_mm"],
                    ),
                    coordinate_fact(
                        "tool.t1.red_marker_to_bed_tab_x_mm",
                        {
                            "offset_mm": result_details[
                                "t1_red_marker_to_bed_tab_x_mm"
                            ],
                            "reference_commanded_x_mm": common_x,
                        },
                        ["offset_mm", "reference_commanded_x_mm"],
                    ),
                ]
                observed_provenance = {
                    "selected_candidate_ids": result_details[
                        "selected_candidate_ids"
                    ],
                    "accepted_x_mm": result_details["accepted_x_mm"],
                    "common_commanded_x_mm": common_x,
                    "corner_pixel_at_capture_y_px": result_details[
                        "corner_pixel_at_capture_y_px"
                    ],
                }
            else:
                dependencies = [
                    {
                        "fact_name": item["fact_name"],
                        "fact_set_hash": item["fact_set_hash"],
                    }
                    for item in manifest["input_facts"]
                ]
                verification_value = {
                    "verified": True,
                    "verification_command_x_mm": result_details[
                        "verification_command_x_mm"
                    ],
                    "expected_offset_mm": result_details["expected_offset_mm"],
                    "t0_marker_offset_mm": result_details[
                        "t0_marker_offset_mm"
                    ],
                    "t1_marker_offset_mm": result_details[
                        "t1_marker_offset_mm"
                    ],
                    "t0_residual_mm": result_details["t0_residual_mm"],
                    "t1_residual_mm": result_details["t1_residual_mm"],
                    "marker_coincidence_residual_mm": result_details[
                        "marker_coincidence_residual_mm"
                    ],
                    "cross_registration": result_details["cross_registration"],
                    "camera": manifest["camera"],
                    "profile": manifest["profile"],
                    "light_macro": manifest["light_macro"],
                    "image_dimensions_px": [width, height],
                    "supporting_artifact_hashes": {
                        name: item["sha256"]
                        for name, item in result_details["artifacts"].items()
                    },
                }
                facts = [
                    {
                        "name": "calibration.rough_tool_x.verified",
                        "definition_version": 5,
                        "role": "diagnostic",
                        "dependencies": dependencies,
                        "value_items": [
                            {"field": field, "role": "diagnostic"}
                            for field in verification_value
                        ],
                        "value": verification_value,
                    }
                ]
                observed_provenance = {
                    "corner_pixel_at_capture_y_px": result_details[
                        "corner_pixel_at_capture_y_px"
                    ],
                    "expected_image_x_point_px": result_details[
                        "expected_image_x_point_px"
                    ],
                    "records": result_details["records"],
                }
            fact_set = {
                "schema": FACT_SET_SCHEMA,
                "schema_version": SCHEMA_VERSION,
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
                    "analysis_hash": analysis["analysis_hash"],
                    "observed_target": observed_provenance,
                    "input_facts": manifest.get("input_facts", []),
                },
                "fact_set_hash": "",
            }
            fact_set["fact_set_hash"] = content_hash(fact_set, "fact_set_hash")
        report_text = _report_markdown(manifest, analysis, result_details)
        atomic_write_json(staging_dir / "result.json", analysis, immutable=True)
        if fact_set:
            atomic_write_json(staging_dir / "fact_set.json", fact_set, immutable=True)
        (staging_dir / "report.md").write_text(report_text, encoding="utf-8")
        os.replace(staging_dir, analysis_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    report_path = analysis_dir / "report.md"
    _update_state(
        job_dir,
        state="analyzed" if result_details["accepted"] else "rejected",
        latest_analysis_run_id=analysis_run_id,
        latest_analysis_state=state_name,
    )
    publication = None
    if fact_set and manifest.get("publish_on_accept"):
        publication = publish_fact_set(
            CALIBRATION_ROOT,
            manifest["job_id"],
            analysis_run_id,
            active_applicability_hash=manifest["applicability_hash"],
        )["publication"]
    rebuild_and_render()
    return {
        "job_id": manifest["job_id"],
        "analysis_run_id": analysis_run_id,
        "state": state_name,
        "analysis_path": str(analysis_dir / "result.json"),
        "fact_set_path": str(analysis_dir / "fact_set.json") if fact_set else None,
        "publication": publication,
        "report_path": str(report_path),
        "review_url": (
            f"/vision/calibration/jobs/{manifest['job_id']}/"
            f"analysis/{analysis_run_id}/"
        ),
    }


def acquire_job(
    name: str,
    *,
    job_type: str = BED_TAB_Y_JOB_TYPE,
    expected_fingerprint: str | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    prepared = prepare_job(
        name,
        job_type=job_type,
        expected_fingerprint=expected_fingerprint,
    )
    manifest = validate_manifest(
        load_json(CALIBRATION_ROOT / "jobs" / prepared["job_id"] / "manifest.json")
    )
    current = query_printer_status()
    current_definition = json.loads(
        json.dumps(_load_registry()["job_types"][job_type])
    )
    if job_type == ROUGH_X_VERIFY_JOB_TYPE:
        current_definition["command_x_mm"] = manifest["verification_reference"][
            "command_x_mm"
        ]
    if job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        current_definition["resolved_x_positions_mm"] = manifest[
            "grid_reference"
        ]["resolved_x_positions_mm"]
    current_resolved = _resolve_preflight(
        current,
        job_type,
        current_definition,
        expected_fingerprint or manifest["provenance"]["active_printer_fingerprint"],
    )
    if (
        job_type in (RED_MARKER_X_JOB_TYPE, FINE_NOZZLE_XZ_JOB_TYPE)
        and current_resolved["active_calibration_snapshot"]
        != manifest["active_calibration_snapshot"]
    ):
        raise VisionCalibrationError(
            "active T0/T1 X calibration changed after job preparation"
        )
    if (
        job_type == ROUGH_X_VERIFY_JOB_TYPE
        and current_resolved["active_calibration_snapshot"]
        != manifest["verification_reference"]["active_x_endstops_mm"]
    ):
        raise VisionCalibrationError(
            "active T0/T1 X calibration does not match the rough-X activation"
        )
    if manifest.get("input_facts"):
        catalog = rebuild_catalog(CALIBRATION_ROOT)
        for binding in manifest["input_facts"]:
            current_hash = (
                catalog.get("heads", {})
                .get(binding["fact_name"], {})
                .get("fact_set_hash")
            )
            if current_hash != binding["fact_set_hash"]:
                raise VisionCalibrationError(
                    f"bound input {binding['fact_name']} is no longer current"
                )
    _start_print(prepared["job_id"])
    state = _wait_for_acquisition(prepared["job_id"], timeout=timeout)
    rebuild_and_render()
    return {"prepared": prepared, "state": state}


def run_job(
    name: str,
    *,
    job_type: str = BED_TAB_Y_JOB_TYPE,
    expected_fingerprint: str | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    if job_type == FINE_NOZZLE_XZ_JOB_TYPE:
        raise VisionCalibrationError(
            "fine nozzle X/Z analysis is not implemented yet; use acquire "
            "to collect the registered planning grid"
        )
    acquired = acquire_job(
        name,
        job_type=job_type,
        expected_fingerprint=expected_fingerprint,
        timeout=timeout,
    )
    analyzed = analyze_job(acquired["prepared"]["job_id"])
    return {"prepared": acquired["prepared"], "analysis": analyzed}


ROUGH_X_CALIBRATION_STAGES = (
    (
        BED_TAB_Y_JOB_TYPE,
        "bed_y",
        ("camera.nozzle_cam.bed_tab.y_parallax_model",),
    ),
    (
        BED_TAB_CORNER_JOB_TYPE,
        "corner",
        ("camera.nozzle_cam.partial_bed_coordinate_system",),
    ),
    (
        RED_MARKER_X_JOB_TYPE,
        "markers",
        (
            "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2",
            "tool.t0.red_marker_to_bed_tab_x_mm",
            "tool.t1.red_marker_to_bed_tab_x_mm",
        ),
    ),
)


def _fact_names_are_fresh(
    catalog: dict[str, Any],
    job_type: str,
    fact_names: tuple[str, ...],
) -> bool:
    heads = catalog.get("heads", {})
    stale = catalog.get("stale_fact_sets", {})
    expected_version = int(
        _load_registry()["job_types"][job_type]["fact_definition_version"]
    )
    for fact_name in fact_names:
        head = heads.get(fact_name)
        if not isinstance(head, dict):
            return False
        if head.get("fact_set_hash") in stale:
            return False
        loaded = _load_current_fact(fact_name, head)
        if loaded is None or loaded[1].get("definition_version") != expected_version:
            return False
    return True


def _wait_for_printer_idle(timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = query_printer_status()
        virtual_sd_active = bool(
            latest.get("virtual_sdcard", {}).get("is_active", False)
        )
        print_state = str(
            latest.get("print_stats", {}).get("state", "")
        ).lower()
        if not virtual_sd_active and print_state not in {"printing", "paused"}:
            return latest
        time.sleep(0.25)
    raise VisionCalibrationError(
        "printer did not return to idle after calibration acquisition"
    )


def calibrate_rough_x_sequence(
    name: str,
    *,
    expected_fingerprint: str | None = None,
    timeout: float = 180.0,
    force: bool = False,
) -> dict[str, Any]:
    seed_result = sync_seed_facts()
    initial_status = _wait_for_printer_idle()
    active_fingerprint = str(
        initial_status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT", {}).get(
            "source_sha256"
        )
        or ""
    )
    if expected_fingerprint and active_fingerprint != expected_fingerprint:
        raise VisionCalibrationError(
            f"active fingerprint {active_fingerprint} does not match "
            f"{expected_fingerprint}"
        )
    fingerprint = expected_fingerprint or active_fingerprint
    sequence_name = _sanitize(name)
    stages: list[dict[str, Any]] = []
    for job_type, stage_slug, fact_names in ROUGH_X_CALIBRATION_STAGES:
        catalog = rebuild_catalog(CALIBRATION_ROOT)
        fresh_before = _fact_names_are_fresh(catalog, job_type, fact_names)
        if fresh_before and not force:
            stages.append(
                {
                    "job_type": job_type,
                    "action": "reused_current_facts",
                    "fact_names": list(fact_names),
                }
            )
            continue
        _wait_for_printer_idle()
        stage_name = f"{sequence_name[:24]}_{stage_slug}"
        result = run_job(
            stage_name,
            job_type=job_type,
            expected_fingerprint=fingerprint,
            timeout=timeout,
        )
        if result["analysis"]["state"] != "accepted":
            raise VisionCalibrationError(
                f"{job_type} analysis was {result['analysis']['state']}; "
                f"inspect {result['analysis']['review_url']}"
            )
        catalog = rebuild_catalog(CALIBRATION_ROOT)
        if not _fact_names_are_fresh(catalog, job_type, fact_names):
            raise VisionCalibrationError(
                f"{job_type} completed without fresh current output facts"
            )
        stages.append(
            {
                "job_type": job_type,
                "action": "acquired_analyzed_published",
                "job_id": result["prepared"]["job_id"],
                "analysis_run_id": result["analysis"]["analysis_run_id"],
                "review_url": result["analysis"]["review_url"],
                "fact_names": list(fact_names),
            }
        )
    candidate = calculate_rough_x(status=initial_status)
    operation_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-rough-x-calibration"
    )
    operation = {
        "schema": "vision-calibration-operation-result",
        "schema_version": SCHEMA_VERSION,
        "operation_id": operation_id,
        "created_at_utc": utc_now(),
        "name": sequence_name,
        "active_config_fingerprint": active_fingerprint,
        "force": bool(force),
        "seed_sync": seed_result,
        "stages": stages,
        "candidate": candidate,
        "result_hash": "",
    }
    operation["result_hash"] = content_hash(operation, "result_hash")
    operation_path = (
        CALIBRATION_ROOT / "operations" / operation_id / "result.json"
    )
    atomic_write_json(operation_path, operation, immutable=True)
    rebuild_and_render()
    return {
        "operation_id": operation_id,
        "operation_path": str(operation_path),
        "stages": stages,
        "candidate": candidate,
    }


def _write_job_page(job: dict[str, Any], root: Path) -> None:
    job_id = job["job_id"]
    job_dir = root / "jobs" / job_id
    manifest = load_json(job_dir / "manifest.json")
    state = load_json(job_dir / "state.json")
    rows = []
    for frame in manifest["frames"]:
        image = job_dir / "frames" / f"{frame['frame']}.jpg"
        image_html = (
            f'<a href="frames/{html.escape(image.name)}">'
            f'<img src="frames/{html.escape(image.name)}" loading="lazy"></a>'
            if image.exists()
            else "<span>pending</span>"
        )
        if "x_mm" in frame and "z_mm" in frame:
            position_label = (
                f"{frame['tool']} X={frame['x_mm']} mm "
                f"Z={frame['z_mm']} mm"
            )
        elif "x_mm" in frame:
            position_label = f"{frame['tool']} X={frame['x_mm']} mm"
        else:
            position_label = f"Y offset={frame.get('y_offset_mm')} mm"
        rows.append(
            "<tr>"
            f"<td>{frame['seq']}</td>"
            f"<td>{html.escape(position_label)}</td>"
            f"<td>{html.escape(frame['pass'])}</td>"
            f"<td>{image_html}</td>"
            "</tr>"
        )
    analyses = []
    latest_analysis_html = ""
    analysis_root = job_dir / "analysis"
    if analysis_root.exists():
        for analysis_dir in sorted(
            (path for path in analysis_root.iterdir() if path.is_dir()),
            reverse=True,
        ):
            result_path = analysis_dir / "result.json"
            if not result_path.exists():
                continue
            result = load_json(result_path)
            relative = f"analysis/{analysis_dir.name}/"
            warnings = result.get("diagnostics", {}).get("warnings", [])
            warning_suffix = f" with {len(warnings)} warning(s)" if warnings else ""
            analyses.append(
                f'<li><a href="{relative}">{html.escape(analysis_dir.name)}</a>'
                f" — {html.escape(result['state'] + warning_suffix)}</li>"
            )
            artifact_items = []
            artifacts = result.get("diagnostics", {}).get("artifacts", {})
            artifact_order = (
                "marker_selection",
                "core_registration",
                "cross_tool_registration",
                "trajectory",
                "corner_localization",
                "corner_duplicate_registration",
                "edge_localization",
                "edge_tracking_overlay",
                "displacement_vs_y",
                "forward_reverse",
                "contact_sheet",
            )
            ordered_artifacts = sorted(
                artifacts.items(),
                key=lambda item: (
                    (
                        artifact_order.index(item[0])
                        if item[0] in artifact_order
                        else len(artifact_order)
                    ),
                    item[0],
                ),
            )
            for name, record in ordered_artifacts:
                artifact_path = Path(record["path"])
                relative_artifact = os.path.relpath(artifact_path, analysis_dir)
                display_name = name.replace("_", " ").title()
                image_class = (
                    ' class="hero-overlay"'
                    if name
                    in (
                        "corner_localization",
                        "corner_duplicate_registration",
                        "edge_localization",
                        "edge_tracking_overlay",
                        "marker_selection",
                        "core_registration",
                        "cross_tool_registration",
                        "trajectory",
                    )
                    else ""
                )
                artifact_items.append(
                    f'<figure><a href="{html.escape(relative_artifact)}">'
                    f'<img{image_class} src="{html.escape(relative_artifact)}"></a>'
                    f"<figcaption>{html.escape(display_name)}</figcaption></figure>"
                )
            fact_link = (
                '<a href="fact_set.json">fact set</a>'
                if (analysis_dir / "fact_set.json").exists()
                else "no fact set"
            )
            warning_html = (
                "<h2>Warnings</h2><ul>"
                + "".join(
                    f"<li>{html.escape(str(warning))}</li>" for warning in warnings
                )
                + "</ul>"
                if warnings
                else ""
            )
            analysis_html = _page(
                f"{job_id} / {analysis_dir.name}",
                (
                    f"<p><strong>{html.escape(result['state'])}</strong> · "
                    f'<a href="result.json">result JSON</a> · {fact_link} · '
                    f'<a href="report.md">report.md</a></p>'
                    f"{warning_html}"
                    f"<div class=\"gallery\">{''.join(artifact_items)}</div>"
                ),
                prefix="../../../../",
            )
            (analysis_dir / "index.html").write_text(analysis_html, encoding="utf-8")
            if not latest_analysis_html:
                latest_warning_html = (
                    '<div class="warning"><strong>Warnings:</strong><ul>'
                    + "".join(
                        f"<li>{html.escape(str(warning))}</li>" for warning in warnings
                    )
                    + "</ul></div>"
                    if warnings
                    else ""
                )
                corner_localization = artifacts.get("corner_localization")
                corner_duplicates = artifacts.get("corner_duplicate_registration")
                edge_localization = artifacts.get("edge_localization")
                edge_tracking = artifacts.get("edge_tracking_overlay")
                marker_selection = artifacts.get("marker_selection")
                core_registration = artifacts.get("core_registration")
                cross_tool_registration = artifacts.get(
                    "cross_tool_registration"
                )
                if marker_selection and core_registration and cross_tool_registration:
                    selection_path = os.path.relpath(
                        Path(marker_selection["path"]), job_dir
                    )
                    core_path = os.path.relpath(
                        Path(core_registration["path"]), job_dir
                    )
                    cross_path = os.path.relpath(
                        Path(cross_tool_registration["path"]), job_dir
                    )
                    overlay_html = (
                        "<h3>Automatically selected red-marker trajectories</h3>"
                        "<p>Green boxes are the marker observations used in the "
                        "fit; red boxes are color candidates excluded by trajectory "
                        "or registration consistency.</p>"
                        f'<a href="{html.escape(selection_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(selection_path)}"></a>'
                        "<h3>Within-tool registration</h3>"
                        "<p>The same shifted line grid is drawn on each accepted "
                        "full frame so the measured motion can be compared directly "
                        "with the visible marker motion.</p>"
                        f'<a href="{html.escape(core_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(core_path)}"></a>'
                        "<h3>Cross-tool common-X registration</h3>"
                        "<p>T0 and T1 are shown side by side at the accepted common "
                        "commanded X. The boxes and crosses show the bidirectional "
                        "grayscale/CLAHE registration.</p>"
                        f'<a href="{html.escape(cross_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(cross_path)}"></a>'
                    )
                elif corner_localization and corner_duplicates:
                    localization_path = os.path.relpath(
                        Path(corner_localization["path"]),
                        job_dir,
                    )
                    duplicates_path = os.path.relpath(
                        Path(corner_duplicates["path"]),
                        job_dir,
                    )
                    overlay_html = (
                        "<h3>Automatically localized bed-tab corner</h3>"
                        "<p>Cyan is the upstream Y-model prediction. Yellow is "
                        "the selected horizontal tab top, descending side, their "
                        "intersection, and the registration ROI. Other semantic "
                        "corner candidates are red.</p>"
                        f'<a href="{html.escape(localization_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(localization_path)}"></a>'
                        "<h3>Duplicate registration and line confirmation</h3>"
                        "<p>Each panel is a fixed-pose duplicate. Cyan is the "
                        "registration-projected corner and yellow is the "
                        "independently detected edge intersection.</p>"
                        f'<a href="{html.escape(duplicates_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(duplicates_path)}"></a>'
                    )
                elif edge_localization and edge_tracking:
                    localization_path = os.path.relpath(
                        Path(edge_localization["path"]),
                        job_dir,
                    )
                    tracking_path = os.path.relpath(
                        Path(edge_tracking["path"]),
                        job_dir,
                    )
                    overlay_html = (
                        "<h3>Automatically discovered bed-tab top edge</h3>"
                        "<p>The two zero-offset frames show every coordinate-free "
                        "horizontal-edge candidate. Green is the selected tab top, "
                        "its descending side, and tracking strip; red candidates "
                        "were rejected because they lack tab geometry or fail "
                        "measured motion quality.</p>"
                        f'<a href="{html.escape(localization_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(localization_path)}"></a>'
                        "<h3>Measured edge versus fitted motion</h3>"
                        "<p>Each panel is one acquired full frame. Yellow is the "
                        "measured seam and tracking strip; cyan is the fitted model. "
                        "Green labels are the forward pass and magenta labels are "
                        "the reverse pass.</p>"
                        f'<a href="{html.escape(tracking_path)}">'
                        f'<img class="hero-overlay" '
                        f'src="{html.escape(tracking_path)}"></a>'
                    )
                else:
                    overlay_html = (
                        '<p class="warning">No current calibration overlay was '
                        "produced.</p>"
                    )
                artifact_links = "".join(
                    "<li>"
                    f'<a href="{html.escape(os.path.relpath(Path(record["path"]), job_dir))}">'
                    f"{html.escape(name.replace('_', ' ').title())}</a>"
                    "</li>"
                    for name, record in ordered_artifacts
                )
                latest_analysis_html = (
                    '<section class="latest-analysis" id="latest-analysis">'
                    "<h2>Latest analysis</h2>"
                    f'<p class="result-state {html.escape(result["state"])}">'
                    f'{html.escape(result["state"].upper())}{html.escape(warning_suffix)}</p>'
                    f'<p><a class="button" href="{html.escape(relative)}">'
                    "Open full analysis</a></p>"
                    f"{latest_warning_html}{overlay_html}"
                    "<h3>All analysis artifacts</h3>"
                    f"<ul>{artifact_links or '<li>none</li>'}</ul>"
                    "</section>"
                )
    page = _page(
        job_id,
        (
            f"<p>State: <strong>{html.escape(str(state.get('state')))}</strong> · "
            f"Frames: {state.get('committed_frame_count', 0)}/"
            f"{manifest['frame_count']} · "
            '<a href="manifest.json">manifest</a> · '
            '<a href="state.json">state</a> · '
            '<a href="acquisition.gcode">G-code</a></p>'
            f"{latest_analysis_html}"
            f"<h2>Analyses</h2><ul>{''.join(analyses) or '<li>none</li>'}</ul>"
            "<h2>Frames</h2><table><thead><tr><th>Seq</th><th>Position</th>"
            f"<th>Pass</th><th>Image</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        ),
        prefix="../../../",
    )
    (job_dir / "index.html").write_text(page, encoding="utf-8")


def _page(title: str, body: str, *, prefix: str = "") -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)}</title>
<style>
body{{font:16px system-ui,sans-serif;max-width:1400px;margin:24px auto;padding:0 18px;background:#17191c;color:#eee}}
a{{color:#58b7ff}} table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #444;padding:8px;text-align:left}}
img{{max-width:420px;max-height:300px}} .gallery{{display:flex;flex-wrap:wrap;gap:18px}} figure{{margin:0}} code{{color:#9ee493}}
.latest-analysis{{border:2px solid #58b7ff;border-radius:8px;padding:18px;margin:24px 0;background:#20252b}}
.hero-overlay{{display:block;width:100%;max-width:1200px;max-height:none;border:3px solid #58b7ff;box-sizing:border-box}}
.button{{display:inline-block;padding:10px 16px;background:#1676b8;color:white;border-radius:5px;text-decoration:none;font-weight:700}}
.result-state{{display:inline-block;padding:6px 10px;border-radius:4px;font-weight:800;letter-spacing:.04em}}
.result-state.accepted{{background:#174f2b;color:#aef2bf}} .result-state.rejected{{background:#5d2222;color:#ffc1c1}}
.warning{{border-left:4px solid #f0b429;padding:8px 12px;background:#332c18;margin:12px 0}}
.fact-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:18px;margin:18px 0}}
.fact-card{{border:1px solid #4b5560;border-radius:8px;padding:18px;background:#20252b;min-width:0}}
.fact-card h3{{margin:0 0 5px}} .fact-name{{display:block;overflow-wrap:anywhere;margin-bottom:16px}}
.fact-metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:14px 0}}
.fact-metrics div{{background:#171b1f;border-radius:5px;padding:10px;min-width:0}}
.fact-metrics dt{{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:#aab5c0;margin-bottom:4px}}
.fact-metrics dd{{margin:0;font-size:1.03rem;overflow-wrap:anywhere}}
.fact-actions{{display:flex;flex-wrap:wrap;gap:14px;margin:14px 0}}
.fact-meta{{color:#bbc3cb;font-size:.92rem}} .hash{{overflow-wrap:anywhere}}
.badge{{display:inline-block;padding:3px 8px;border-radius:999px;background:#174f2b;color:#aef2bf;font-size:.78rem;font-weight:800;text-transform:uppercase}}
.badge.warning{{background:#5c4615;color:#ffe59b;border:0;margin:0}}
details{{border-top:1px solid #414951;margin-top:14px;padding-top:12px}} summary{{cursor:pointer;color:#58b7ff;font-weight:700}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#121416;border:1px solid #3b4249;border-radius:5px;padding:12px;max-height:620px;overflow:auto}}
</style></head><body><p><a href="{prefix}index.html">Vision calibration</a></p>
<h1>{html.escape(title)}</h1>{body}</body></html>
"""


def _format_number(value: Any, digits: int = 6) -> str:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f"{float(value):.{digits}f}"
    return "unavailable"


def _load_current_fact(
    name: str, head: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    relative_path = head.get("fact_set_path")
    if isinstance(relative_path, str):
        fact_set_path = CALIBRATION_ROOT / relative_path
    else:
        fact_set_path = (
            CALIBRATION_ROOT
            / "jobs"
            / str(head["job_id"])
            / "analysis"
            / str(head["analysis_run_id"])
            / "fact_set.json"
        )
    if not fact_set_path.is_file():
        return None
    fact_set = load_json(fact_set_path)
    for fact in fact_set.get("facts", []):
        if fact.get("name") == name:
            return fact_set, fact
    return None


def _fact_title(name: str) -> str:
    titles = {
        "camera.nozzle_cam.bed_tab.y_parallax_model": (
            "Nozzle camera — bed-tab Y parallax"
        ),
        "bed.tab_corner.printer_xyz": "Bed-tab corner printer prior",
        "bed.reference_plane.tab_to_print_plane_z_mm": (
            "Bed-tab plane to print-plane Z"
        ),
        "camera.nozzle_cam.partial_bed_coordinate_system": (
            "Nozzle camera — partial bed coordinate system"
        ),
        "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2": (
            "Nozzle camera — image X axis at Z2"
        ),
        "tool.t0.red_marker_to_bed_tab_x_mm": (
            "T0 red marker — X from bed tab"
        ),
        "tool.t1.red_marker_to_bed_tab_x_mm": (
            "T1 red marker — X from bed tab"
        ),
        "calibration.rough_tool_x.active_snapshot": (
            "Active rough T0/T1 X calibration"
        ),
        "calibration.rough_tool_x.verified": (
            "Rough T0/T1 X verification"
        ),
    }
    if name in titles:
        return titles[name]
    return name.replace(".", " · ").replace("_", " ")


def _metric(label: str, value: str) -> str:
    return f"<div><dt>{html.escape(label)}</dt>" f"<dd>{html.escape(value)}</dd></div>"


def _fact_item_fields(fact: dict[str, Any], role: str) -> list[str]:
    return [
        str(item["field"])
        for item in fact.get("value_items", [])
        if isinstance(item, dict)
        and item.get("role") == role
        and isinstance(item.get("field"), str)
    ]


def _fact_card(
    name: str,
    head: dict[str, Any],
    fact_set: dict[str, Any],
    fact: dict[str, Any],
    *,
    source_prefix: str,
    overview: bool,
) -> str:
    value = fact.get("value", {})
    quality = value.get("quality", {})
    coordinate_fields = _fact_item_fields(fact, "coordinate_system")
    diagnostic_fields = _fact_item_fields(fact, "diagnostic")
    vector = value.get("axis_vector_px_per_mm")
    vector_valid = (
        "axis_vector_px_per_mm" in coordinate_fields
        and isinstance(vector, list)
        and len(vector) == 2
        and all(
            isinstance(component, (int, float)) and math.isfinite(float(component))
            for component in vector
        )
    )
    metrics = []
    if vector_valid:
        x_component, y_component = (float(vector[0]), float(vector[1]))
        scale = math.hypot(x_component, y_component)
        inverse_scale = 1.0 / scale if scale else float("nan")
        angle = math.degrees(math.atan2(y_component, x_component))
        metrics.extend(
            (
                _metric(
                    "Axis vector",
                    (
                        f"[{_format_number(x_component)}, "
                        f"{_format_number(y_component)}] px/mm"
                    ),
                ),
                _metric("Scalar scale", f"{_format_number(scale)} px/mm"),
                _metric(
                    "Inverse scale",
                    f"{_format_number(inverse_scale)} mm/px",
                ),
                _metric("Image-axis angle", f"{_format_number(angle, 3)}°"),
            )
        )
    image_y_vector = value.get("image_y_axis_vector_px_per_mm")
    if (
        "image_y_axis_vector_px_per_mm" in coordinate_fields
        and isinstance(image_y_vector, list)
        and len(image_y_vector) == 2
    ):
        image_y_scale = math.hypot(float(image_y_vector[0]), float(image_y_vector[1]))
        metrics.extend(
            (
                _metric(
                    "Image Y-axis vector",
                    (
                        f"[{_format_number(image_y_vector[0])}, "
                        f"{_format_number(image_y_vector[1])}] px/mm"
                    ),
                ),
                _metric(
                    "Image Y scale",
                    f"{_format_number(image_y_scale)} px/mm",
                ),
            )
        )
    coordinate_metric_specs = (
        ("xyz_mm", "Printer XYZ prior", "mm"),
        ("corner_pixel_xy_px", "Corner pixel XY", "px"),
        ("corner_pixel_capture_y_mm", "Corner pixel capture Y", "mm"),
        ("corner_printer_xyz_mm", "Corner printer XYZ", "mm"),
        ("z_offset_mm", "Z offset", "mm"),
        ("tab_to_print_plane_z_mm", "Tab to print-plane Z", "mm"),
        ("offset_mm", "Marker X from bed tab", "mm"),
        ("reference_commanded_x_mm", "Reference commanded X", "mm"),
        ("bed_tab_x_mm", "Bed-tab X anchor", "mm"),
        ("t0_old_x_endstop_mm", "T0 old X endstop", "mm"),
        ("t0_calculated_correction_mm", "T0 X correction", "mm"),
        ("t0_applied_x_endstop_mm", "T0 applied X endstop", "mm"),
        ("t1_old_x_endstop_mm", "T1 old X endstop", "mm"),
        ("t1_calculated_correction_mm", "T1 X correction", "mm"),
        ("t1_applied_x_endstop_mm", "T1 applied X endstop", "mm"),
    )
    for field, label, unit in coordinate_metric_specs:
        if field not in coordinate_fields or field not in value:
            continue
        metric_value = value[field]
        if isinstance(metric_value, list):
            rendered = (
                "["
                + ", ".join(_format_number(component, 4) for component in metric_value)
                + "]"
            )
        else:
            rendered = _format_number(metric_value, 4)
        metrics.append(_metric(label, f"{rendered} {unit}"))
    if not overview:
        fit_px = quality.get("joint_residual_rms_px")
        fit_mm = quality.get("joint_residual_rms_mm")
        duplicate_px = quality.get("duplicate_position_disagreement_px")
        duplicate_mm = quality.get("duplicate_position_disagreement_mm")
        minimum_correlation = quality.get("minimum_correlation")
        median_correlation = quality.get("median_correlation")
        usable_frames = quality.get("usable_frame_count")
        commanded_span = quality.get("commanded_span_mm")
        if fit_px is not None or fit_mm is not None:
            metrics.append(
                _metric(
                    "Fit RMS",
                    (
                        f"{_format_number(fit_px, 3)} px / "
                        f"{_format_number(fit_mm, 4)} mm"
                    ),
                )
            )
        if duplicate_px is not None or duplicate_mm is not None:
            metrics.append(
                _metric(
                    "Duplicate discrepancy",
                    (
                        f"{_format_number(duplicate_px, 3)} px / "
                        f"{_format_number(duplicate_mm, 4)} mm"
                    ),
                )
            )
        if minimum_correlation is not None or median_correlation is not None:
            metrics.append(
                _metric(
                    "Registration correlation",
                    (
                        f"{_format_number(minimum_correlation, 3)} minimum / "
                        f"{_format_number(median_correlation, 3)} median"
                    ),
                )
            )
        if usable_frames is not None or commanded_span is not None:
            metrics.append(
                _metric(
                    "Sweep coverage",
                    (
                        f"{usable_frames if usable_frames is not None else 'unavailable'} "
                        f"frames / {_format_number(commanded_span, 1)} mm"
                    ),
                )
            )
        if quality.get("repeatability_rms_px") is not None:
            metrics.append(
                _metric(
                    "Corner repeatability",
                    (
                        f"{_format_number(quality.get('repeatability_rms_px'), 3)} "
                        "px RMS / "
                        f"{_format_number(quality.get('repeatability_max_px'), 3)} "
                        "px maximum"
                    ),
                )
            )
        if quality.get("line_confirmation_count") is not None:
            metrics.append(
                _metric(
                    "Corner duplicates",
                    (
                        f"{quality.get('usable_frame_count')} usable / "
                        f"{quality.get('line_confirmation_count')} line-confirmed"
                    ),
                )
            )
        camera = value.get("camera")
        profile = value.get("profile")
        light = value.get("light_macro")
        if camera is not None or profile is not None:
            metrics.append(
                _metric(
                    "Capture",
                    f"{camera or 'unavailable'} · {profile or 'unavailable'}",
                )
            )
        if light is not None:
            metrics.append(_metric("Lighting", str(light)))
        dimensions = value.get("image_dimensions_px")
        if isinstance(dimensions, list) and len(dimensions) == 2:
            metrics.append(
                _metric("Image size", f"{dimensions[0]} × {dimensions[1]} px")
            )

    job_id = str(head["job_id"])
    analysis_run_id = str(head["analysis_run_id"])
    source_base = (
        f"{source_prefix}/{urllib.parse.quote(job_id)}/analysis/"
        f"{urllib.parse.quote(analysis_run_id)}"
    )
    warnings = quality.get("warnings") or []
    warning_html = ""
    if warnings and not overview:
        warning_html = (
            '<div class="warning"><strong>Warnings</strong><ul>'
            + "".join(f"<li>{html.escape(str(warning))}</li>" for warning in warnings)
            + "</ul></div>"
        )
    raw_record = {
        "current_head": head,
        "fact": fact,
        "fact_set_provenance": fact_set.get("provenance", {}),
    }
    raw_json = html.escape(json.dumps(raw_record, indent=2, sort_keys=True))
    published = html.escape(str(head.get("published_at_utc", "unavailable")))
    fact_set_hash = html.escape(str(head["fact_set_hash"]))
    role = str(fact.get("role", "unclassified"))
    role_label = role.replace("_", " ")
    if overview:
        return (
            '<article class="fact-card fact-card-overview">'
            f"<h3>{html.escape(_fact_title(name))} "
            f'<span class="badge">{html.escape(role_label)}</span></h3>'
            f'<dl class="fact-metrics">{"".join(metrics)}</dl>'
            '<p class="fact-actions"><a href="calibration/facts/">'
            "Full fact and diagnostics</a></p>"
            "</article>"
        )
    declarations = (
        '<p class="fact-meta"><strong>Coordinate-system fields:</strong> '
        f"{html.escape(', '.join(coordinate_fields) or 'none')}<br>"
        "<strong>Diagnostic fields:</strong> "
        f"{html.escape(', '.join(diagnostic_fields) or 'none')}</p>"
    )
    if head.get("source_kind") in ("seed", "operation"):
        fact_set_link = "../" + str(head["fact_set_path"])
        source_label = (
            "Operation fact-set JSON"
            if head.get("source_kind") == "operation"
            else "Seed fact-set JSON"
        )
        actions = (
            '<div class="fact-actions">'
            f'<a href="{html.escape(fact_set_link)}">{source_label}</a>'
            "</div>"
        )
    else:
        actions = (
            '<div class="fact-actions">'
            f'<a href="{html.escape(source_base)}/">Source analysis</a>'
            f'<a href="{html.escape(source_base)}/fact_set.json">Fact-set JSON</a>'
            f'<a href="{html.escape(source_base)}/report.md">Analysis report</a>'
            "</div>"
        )
    return (
        '<article class="fact-card">'
        f"<h3>{html.escape(_fact_title(name))} "
        f'<span class="badge">{html.escape(role_label)}</span></h3>'
        f'<code class="fact-name">{html.escape(name)}</code>'
        f'<dl class="fact-metrics">{"".join(metrics)}</dl>'
        f"{declarations}"
        f"{warning_html}"
        f"{actions}"
        '<p class="fact-meta">'
        f"Definition v{html.escape(str(fact.get('definition_version', 'unavailable')))}"
        f" · Published {published}<br>"
        f'<span class="hash">Fact set: <code>{fact_set_hash}</code></span></p>'
        "<details><summary>Raw fact value and provenance</summary>"
        f"<pre>{raw_json}</pre></details>"
        "</article>"
    )


def render_ui(catalog: dict[str, Any]) -> None:
    VISION_ROOT.mkdir(parents=True, exist_ok=True)
    jobs = catalog.get("jobs", [])
    for job in jobs:
        _write_job_page(job, CALIBRATION_ROOT)
    rows = []
    for job in sorted(jobs, key=lambda item: item["created_at_utc"], reverse=True):
        rows.append(
            "<tr>"
            f'<td><a href="calibration/jobs/{html.escape(job["job_id"])}/">'
            f"{html.escape(job['job_id'])}</a></td>"
            f"<td>{html.escape(job['state'] or '')}</td>"
            f"<td>{job['committed_frame_count']}/{job['frame_count']}</td>"
            f"<td>{len(job['analyses'])}</td>"
            "</tr>"
        )
    dashboard_facts = []
    report_facts = []
    for name, head in sorted(catalog.get("heads", {}).items()):
        loaded = _load_current_fact(name, head)
        if loaded is None:
            missing = (
                '<article class="fact-card">'
                f"<h3>{html.escape(_fact_title(name))}</h3>"
                f'<code class="fact-name">{html.escape(name)}</code>'
                '<p class="warning">The current catalog head could not be resolved '
                "to its immutable fact set.</p></article>"
            )
            dashboard_facts.append(missing)
            report_facts.append(missing)
            continue
        fact_set, fact = loaded
        if fact.get("role") == "coordinate_system":
            dashboard_facts.append(
                _fact_card(
                    name,
                    head,
                    fact_set,
                    fact,
                    source_prefix="calibration/jobs",
                    overview=True,
                )
            )
        report_facts.append(
            _fact_card(
                name,
                head,
                fact_set,
                fact,
                source_prefix="../jobs",
                overview=False,
            )
        )
    stale = catalog.get("stale_fact_sets", {})
    facts_report_dir = CALIBRATION_ROOT / "facts"
    facts_report_dir.mkdir(parents=True, exist_ok=True)
    facts_report_body = (
        "<p>This report resolves every current catalog head to the actual "
        "immutable fact value. Derived values are calculated for readability; "
        "the collapsible section preserves the exact stored fact and provenance.</p>"
        '<p><a href="../catalog.json">Open calibration catalog JSON</a></p>'
        f'<div class="fact-grid">{"".join(report_facts) or "<p>No facts published.</p>"}</div>'
        f"<p>Stale consumers: {len(stale)}</p>"
    )
    (facts_report_dir / "index.html").write_text(
        _page("Current calibration facts", facts_report_body, prefix="../../"),
        encoding="utf-8",
    )
    body = (
        "<p>Clean-slate calibration framework. Accepted facts publish "
        "immediately according to each job manifest; rejected analyses publish "
        "nothing.</p>"
        "<h2>Current facts</h2>"
        '<p><a class="button" href="calibration/facts/">'
        "Open current facts report</a></p>"
        f'<div class="fact-grid">{"".join(dashboard_facts) or "<p>No facts published.</p>"}</div>'
        f"<p>Stale consumers: {len(stale)}</p>"
        "<h2>Jobs</h2><table><thead><tr><th>Job</th><th>State</th>"
        f"<th>Frames</th><th>Analyses</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    (VISION_ROOT / "index.html").write_text(
        _page("Vision calibration", body), encoding="utf-8"
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
        subparser.add_argument("--name", default="bed_tab_y_scale")
        subparser.add_argument("--expected-fingerprint")
        if command in ("acquire", "run"):
            subparser.add_argument("--timeout", type=float, default=180.0)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("job_id")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("job_id")
    publish_parser.add_argument("analysis_run_id")
    subparsers.add_parser("rebuild-catalog")
    subparsers.add_parser("sync-priors")
    rough_x_parser = subparsers.add_parser("calibrate-rough-x")
    rough_x_parser.add_argument("--name", default="rough_x_calibration")
    rough_x_parser.add_argument("--expected-fingerprint")
    rough_x_parser.add_argument("--timeout", type=float, default=180.0)
    rough_x_parser.add_argument("--force", action="store_true")
    calculate_parser = subparsers.add_parser("calculate-rough-x")
    calculate_parser.add_argument("--old-t0", type=float)
    calculate_parser.add_argument("--old-t1", type=float)
    activation_parser = subparsers.add_parser("record-rough-x-activation")
    activation_parser.add_argument("--old-t0", type=float, required=True)
    activation_parser.add_argument("--old-t1", type=float, required=True)
    activation_parser.add_argument("--expected-fingerprint")
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
        elif args.command == "calibrate-rough-x":
            result = calibrate_rough_x_sequence(
                args.name,
                expected_fingerprint=args.expected_fingerprint,
                timeout=args.timeout,
                force=args.force,
            )
        elif args.command == "calculate-rough-x":
            result = calculate_rough_x(
                old_t0_x_endstop_mm=args.old_t0,
                old_t1_x_endstop_mm=args.old_t1,
            )
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
