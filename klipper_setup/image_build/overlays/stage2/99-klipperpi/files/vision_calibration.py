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

from vision_bed_tab_y_scale import Y_OFFSETS_MM
from vision_bed_tab_y_scale import analyze as analyze_bed_tab_y_scale
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
FRAMEBUFFER_DIR = Path(
    os.environ.get("VISION_FRAMEBUFFER_DIR", "/run/vision-preview-nozzle_cam")
)
MOONRAKER_URL = os.environ.get("VISION_MOONRAKER_URL", "http://127.0.0.1")
JOB_TYPE = "nozzle_cam_bed_tab_y_scale"
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
    resolved_positions = [
        [x_min, y_min + offset, z_max] for offset in definition["y_offsets_mm"]
    ]
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

    light_settings = _settings_section(
        settings, "gcode_macro nozzle_cam_y_feature_light"
    )
    scope = {
        "camera": "nozzle_cam",
        "profile": definition["profile"],
        "profile_file_sha256": sha256_file(PROFILE_PATH),
        "light_macro": definition["light_macro"],
        "light_gcode": light_settings.get("gcode"),
        "localizer": definition["localizer"],
        "t0_viewing_pose": {"x_mm": x_min, "z_mm": z_max},
        "y_motion": {
            "position_min_mm": y_min,
            "position_endstop_mm": y_endstop,
            "offsets_mm": definition["y_offsets_mm"],
            "velocity_mm_s": definition["velocity_mm_s"],
            "settle_ms": definition["settle_ms"],
            "rotation_distance": stepper_y.get("rotation_distance"),
            "microsteps": stepper_y.get("microsteps"),
        },
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
        },
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
    definition: dict[str, Any],
    pose: dict[str, float],
) -> str:
    feedrate = float(definition["velocity_mm_s"]) * 60.0
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
    for seq, offset in enumerate(definition["y_offsets_mm"]):
        y = pose["y_base_mm"] + float(offset)
        frame = f"y_{seq:02d}_{int(offset):02d}mm"
        lines.extend(
            [
                f"G1 Y{y:.6f} F{feedrate:.3f}",
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
            (
                f"VISION_JOB_END JOB={job_id} "
                f"EXPECTED_FRAMES={len(definition['y_offsets_mm'])}"
            ),
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


def prepare_job(
    name: str,
    *,
    expected_fingerprint: str | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = _load_registry()
    definition = registry["job_types"][JOB_TYPE]
    resolved = _resolve_preflight(
        status or query_printer_status(), definition, expected_fingerprint
    )
    job_id = _job_id(name)
    job_dir = CALIBRATION_ROOT / "jobs" / job_id
    if job_dir.exists():
        raise VisionCalibrationError(f"job already exists: {job_id}")
    frames = []
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
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": JOB_TYPE,
        "definition_version": definition["definition_version"],
        "created_at_utc": utc_now(),
        "camera": "nozzle_cam",
        "profile": definition["profile"],
        "light_macro": definition["light_macro"],
        "localizer": definition["localizer"],
        "publish_on_accept": bool(definition["publish_on_accept"]),
        "frame_count": len(frames),
        "frames": frames,
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
    placeholder_gcode = _gcode(
        job_id,
        HASH_PLACEHOLDER,
        HASH_PLACEHOLDER,
        definition,
        resolved["pose"],
    )
    manifest["gcode_hash"] = _gcode_hash(placeholder_gcode)
    manifest["manifest_hash"] = content_hash(manifest, "manifest_hash")
    final_gcode = _gcode(
        job_id,
        manifest["manifest_hash"],
        manifest["gcode_hash"],
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
    if manifest["definition_version"] != 4:
        raise VisionCalibrationError(
            "only definition-v4 jobs can be analyzed by the current localizer"
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
        result_details = analyze_bed_tab_y_scale(
            frame_paths,
            staging_dir / "artifacts",
            offsets_mm=[float(frame["y_offset_mm"]) for frame in manifest["frames"]],
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
                "dependencies": [],
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
                "facts": [
                    {
                        "name": "camera.nozzle_cam.bed_tab.y_parallax_model",
                        "definition_version": 4,
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
                ],
                "provenance": {
                    "active_printer_fingerprint": manifest["provenance"][
                        "active_printer_fingerprint"
                    ],
                    "manifest_hash": manifest["manifest_hash"],
                    "analysis_hash": analysis["analysis_hash"],
                    "observed_target": result_details["observed_target"],
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


def run_job(
    name: str,
    *,
    expected_fingerprint: str | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    prepared = prepare_job(name, expected_fingerprint=expected_fingerprint)
    current = query_printer_status()
    _resolve_preflight(
        current,
        _load_registry()["job_types"][JOB_TYPE],
        expected_fingerprint
        or validate_manifest(
            load_json(CALIBRATION_ROOT / "jobs" / prepared["job_id"] / "manifest.json")
        )["provenance"]["active_printer_fingerprint"],
    )
    _start_print(prepared["job_id"])
    _wait_for_acquisition(prepared["job_id"], timeout=timeout)
    analyzed = analyze_job(prepared["job_id"])
    return {"prepared": prepared, "analysis": analyzed}


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
        rows.append(
            "<tr>"
            f"<td>{frame['seq']}</td>"
            f"<td>{frame['y_offset_mm']}</td>"
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
                "edge_localization",
                "edge_tracking_overlay",
                "displacement_vs_y",
                "forward_reverse",
                "contact_sheet",
                # Historical definition-v2 artifacts remain readable.
                "motion_overlay_contact_sheet",
                "motion_grid_overlay",
                "patch_selection",
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
                        "edge_localization",
                        "edge_tracking_overlay",
                        "motion_overlay_contact_sheet",
                        "motion_grid_overlay",
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
                edge_localization = artifacts.get("edge_localization")
                edge_tracking = artifacts.get("edge_tracking_overlay")
                if edge_localization and edge_tracking:
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
                    per_frame_overlay = artifacts.get("motion_overlay_contact_sheet")
                    motion_overlay = per_frame_overlay or artifacts.get(
                        "motion_grid_overlay"
                    )
                    if motion_overlay:
                        overlay_path = os.path.relpath(
                            Path(motion_overlay["path"]),
                            job_dir,
                        )
                        overlay_html = (
                            "<h3>Historical motion overlay</h3>"
                            "<p>This analysis predates automatic edge discovery.</p>"
                            f'<a href="{html.escape(overlay_path)}">'
                            f'<img class="hero-overlay" '
                            f'src="{html.escape(overlay_path)}"></a>'
                        )
                    else:
                        overlay_html = (
                            '<p class="warning">No edge overlay was produced.</p>'
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
            "<h2>Frames</h2><table><thead><tr><th>Seq</th><th>Y offset</th>"
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
    if name == "camera.nozzle_cam.bed_tab.y_parallax_model":
        return "Nozzle camera — bed-tab Y parallax"
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
        if not coordinate_fields:
            metrics.append(
                _metric(
                    "Declaration missing",
                    "This historical fact has no coordinate-system field declaration.",
                )
            )
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
    return (
        '<article class="fact-card">'
        f"<h3>{html.escape(_fact_title(name))} "
        f'<span class="badge">{html.escape(role_label)}</span></h3>'
        f'<code class="fact-name">{html.escape(name)}</code>'
        f'<dl class="fact-metrics">{"".join(metrics)}</dl>'
        f"{declarations}"
        f"{warning_html}"
        '<div class="fact-actions">'
        f'<a href="{html.escape(source_base)}/">Source analysis</a>'
        f'<a href="{html.escape(source_base)}/fact_set.json">Fact-set JSON</a>'
        f'<a href="{html.escape(source_base)}/report.md">Analysis report</a>'
        "</div>"
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
    for command in ("prepare", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("job_type", choices=[JOB_TYPE])
        subparser.add_argument("--name", default="bed_tab_y_scale")
        subparser.add_argument("--expected-fingerprint")
        if command == "run":
            subparser.add_argument("--timeout", type=float, default=180.0)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("job_id")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("job_id")
    publish_parser.add_argument("analysis_run_id")
    subparsers.add_parser("rebuild-catalog")
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare":
            result = prepare_job(
                args.name, expected_fingerprint=args.expected_fingerprint
            )
        elif args.command == "run":
            result = run_job(
                args.name,
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
