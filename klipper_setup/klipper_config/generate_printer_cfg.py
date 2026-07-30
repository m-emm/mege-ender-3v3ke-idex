#!/usr/bin/env python3
"""Render the active Klipper config from absolute IDEX calibration values."""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path
from string import Template
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = SCRIPT_DIR / "calib.yaml"
DEFAULT_TEMPLATE_PATH = SCRIPT_DIR / "printer.cfg.template"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "printer.cfg"
FINGERPRINT_INPUT_VERSION = "idex-klipper-config-fingerprint-v1"
FINGERPRINT_MACRO_SECTION = "gcode_macro _IDEX_CONFIG_FINGERPRINT"
FINGERPRINT_CONFIG_OPTION = "variable_source_sha256"
FINGERPRINT_SETTINGS_KEY = "source_sha256"


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_float(mapping: dict[str, Any], key: str, path: str) -> float:
    if key not in mapping:
        raise ValueError(f"Missing {path}.{key}")
    try:
        return float(mapping[key])
    except (TypeError, ValueError):
        raise ValueError(f"{path}.{key} must be numeric") from None


def _require_string(mapping: dict[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _render_config_option(name: str, value: str) -> str:
    lines = value.split("\n")
    first = f"{name}: {lines[0]}" if lines[0] else f"{name}:"
    return "\n".join([first, *(f"    {line}" for line in lines[1:])])


def _load_camera_calibration(
    data: dict[str, Any], calib_path: Path
) -> dict[str, Any] | None:
    cameras = data.get("cameras")
    if cameras is None:
        return None
    cameras = _require_mapping(cameras, "cameras")
    nozzle_cam = _require_mapping(cameras.get("nozzle_cam"), "cameras.nozzle_cam")
    image = _require_mapping(nozzle_cam.get("image"), "cameras.nozzle_cam.image")
    transform = _require_mapping(
        nozzle_cam.get("printer_to_image"), "cameras.nozzle_cam.printer_to_image"
    )
    reference = _require_mapping(
        transform.get("reference"), "cameras.nozzle_cam.printer_to_image.reference"
    )
    axes = _require_mapping(
        transform.get("axes_px_per_mm"),
        "cameras.nozzle_cam.printer_to_image.axes_px_per_mm",
    )
    y_axis = _require_mapping(
        axes.get("y"), "cameras.nozzle_cam.printer_to_image.axes_px_per_mm.y"
    )
    feature = _require_mapping(
        nozzle_cam.get("bed_y_feature"), "cameras.nozzle_cam.bed_y_feature"
    )
    width = int(_require_float(image, "width_px", "cameras.nozzle_cam.image"))
    height = int(_require_float(image, "height_px", "cameras.nozzle_cam.image"))
    if width <= 0 or height <= 0:
        raise ValueError("camera image dimensions must be positive")
    vector_x = _require_float(
        y_axis, "x", "cameras.nozzle_cam.printer_to_image.axes_px_per_mm.y"
    )
    vector_y = _require_float(
        y_axis, "y", "cameras.nozzle_cam.printer_to_image.axes_px_per_mm.y"
    )
    if vector_x * vector_x + vector_y * vector_y <= 1.0e-12:
        raise ValueError("camera bed-Y axis vector must be non-zero")
    template_file = _require_string(
        feature, "template_file", "cameras.nozzle_cam.bed_y_feature"
    )
    template_relative = Path(template_file)
    if template_relative.is_absolute() or ".." in template_relative.parts:
        raise ValueError("camera bed-Y template_file must be a safe relative path")
    template_path = calib_path.parent / template_relative
    if not template_path.is_file():
        raise ValueError(f"camera bed-Y template does not exist: {template_path}")
    template_sha256 = _require_string(
        feature, "template_sha256", "cameras.nozzle_cam.bed_y_feature"
    )
    if not re.fullmatch(r"[0-9a-f]{64}", template_sha256):
        raise ValueError("camera bed-Y template_sha256 must be 64 lowercase hex digits")
    actual_template_sha256 = hashlib.sha256(template_path.read_bytes()).hexdigest()
    if actual_template_sha256 != template_sha256:
        raise ValueError(
            "camera bed-Y template hash mismatch: "
            f"{actual_template_sha256} != {template_sha256}"
        )
    feature_mode = _require_string(
        feature, "feature_mode", "cameras.nozzle_cam.bed_y_feature"
    )
    if feature_mode not in ("gray_norm", "clahe", "grad_y", "grad_mag"):
        raise ValueError(f"unsupported camera bed-Y feature mode {feature_mode!r}")
    return {
        "image_width": width,
        "image_height": height,
        "profile": _require_string(image, "profile", "cameras.nozzle_cam.image"),
        "reference_y": _require_float(
            reference,
            "printer_y_mm",
            "cameras.nozzle_cam.printer_to_image.reference",
        ),
        "reference_pixel_x": _require_float(
            reference, "pixel_x", "cameras.nozzle_cam.printer_to_image.reference"
        ),
        "reference_pixel_y": _require_float(
            reference, "pixel_y", "cameras.nozzle_cam.printer_to_image.reference"
        ),
        "axis_vector_x": vector_x,
        "axis_vector_y": vector_y,
        "template_file": template_file,
        "template_sha256": template_sha256,
        "template_width": int(
            _require_float(
                feature, "template_width_px", "cameras.nozzle_cam.bed_y_feature"
            )
        ),
        "template_height": int(
            _require_float(
                feature, "template_height_px", "cameras.nozzle_cam.bed_y_feature"
            )
        ),
        "feature_mode": feature_mode,
    }


def _load_eddy_relative_calibration(data: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "bed_center_x": 117.5,
        "bed_center_y": 117.5,
        "nozzle_to_coil_x": -8.18,
        "nozzle_to_coil_y": 9.0,
        "nozzle_to_coil_z": 2.5,
        "reg_drive_current": None,
        "calibrate": None,
        "capture": None,
    }
    value = data.get("eddy_relative_calibration")
    if value is None:
        return defaults
    value = _require_mapping(value, "eddy_relative_calibration")
    bed_center = _require_mapping(
        value.get("bed_center"), "eddy_relative_calibration.bed_center"
    )
    nozzle_to_coil = _require_mapping(
        value.get("nozzle_to_coil"), "eddy_relative_calibration.nozzle_to_coil"
    )
    klipper = value.get("klipper")
    reg_drive_current = None
    calibrate = None
    capture = None
    if klipper is not None:
        klipper = _require_mapping(klipper, "eddy_relative_calibration.klipper")
        if klipper.get("capture") is not None:
            capture = _require_mapping(
                klipper["capture"],
                "eddy_relative_calibration.klipper.capture",
            )
        if klipper.get("reg_drive_current") is not None:
            try:
                reg_drive_current = int(klipper["reg_drive_current"])
            except (TypeError, ValueError):
                raise ValueError(
                    "eddy_relative_calibration.klipper.reg_drive_current "
                    "must be an integer"
                ) from None
            if not 0 <= reg_drive_current <= 31:
                raise ValueError(
                    "eddy_relative_calibration.klipper.reg_drive_current "
                    "must be between 0 and 31"
                )
        if klipper.get("calibrate") is not None:
            calibrate_value = klipper.get("calibrate")
            if not isinstance(calibrate_value, str) or not calibrate_value.strip():
                raise ValueError(
                    "eddy_relative_calibration.klipper.calibrate "
                    "must be a non-empty string"
                )
            calibrate = calibrate_value
            pairs = [item.strip() for item in calibrate.split(",") if item.strip()]
            if len(pairs) < 9:
                raise ValueError(
                    "eddy_relative_calibration.klipper.calibrate must contain "
                    "at least 9 height:frequency pairs"
                )
            for pair in pairs:
                try:
                    height, frequency = pair.split(":", 1)
                    float(height)
                    float(frequency)
                except (TypeError, ValueError):
                    raise ValueError(
                        "eddy_relative_calibration.klipper.calibrate contains "
                        f"an invalid height:frequency pair: {pair!r}"
                    ) from None
    return {
        "bed_center_x": _require_float(
            bed_center, "x", "eddy_relative_calibration.bed_center"
        ),
        "bed_center_y": _require_float(
            bed_center, "y", "eddy_relative_calibration.bed_center"
        ),
        "nozzle_to_coil_x": _require_float(
            nozzle_to_coil, "x", "eddy_relative_calibration.nozzle_to_coil"
        ),
        "nozzle_to_coil_y": _require_float(
            nozzle_to_coil, "y", "eddy_relative_calibration.nozzle_to_coil"
        ),
        "nozzle_to_coil_z": _require_float(
            nozzle_to_coil, "z", "eddy_relative_calibration.nozzle_to_coil"
        ),
        "reg_drive_current": reg_drive_current,
        "calibrate": calibrate,
        "capture": capture,
    }


def load_calibration(calib_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    data = _require_mapping(data, "calib.yaml")
    bed_grid_zero = _require_mapping(data.get("bed_grid_zero"), "bed_grid_zero")
    tools = _require_mapping(data.get("tools"), "tools")
    t0 = _require_mapping(tools.get("t0"), "tools.t0")
    t1 = _require_mapping(tools.get("t1"), "tools.t1")

    return {
        "bed_grid_zero": {
            "x": _require_float(bed_grid_zero, "x", "bed_grid_zero"),
            "y": _require_float(bed_grid_zero, "y", "bed_grid_zero"),
        },
        "tools": {
            "t0": {
                "x_endstop": _require_float(t0, "x_endstop", "tools.t0"),
                "y_endstop": _require_float(t0, "y_endstop", "tools.t0"),
                "z_endstop": _require_float(t0, "z_endstop", "tools.t0"),
            },
            "t1": {
                "x_endstop": _require_float(t1, "x_endstop", "tools.t1"),
                "y_endstop": _require_float(t1, "y_endstop", "tools.t1"),
                "z_endstop": _require_float(t1, "z_endstop", "tools.t1"),
            },
        },
        "nozzle_cam": _load_camera_calibration(data, calib_path),
        "eddy_relative": _load_eddy_relative_calibration(data),
    }


def format_mm(value: float) -> str:
    return f"{value:.3f}"


def _hash_file(hasher: "hashlib._Hash", label: str, path: Path) -> None:
    data = path.read_bytes()
    hasher.update(f"{label}:{len(data)}\n".encode("utf-8"))
    hasher.update(data)
    hasher.update(b"\n")


def compute_config_fingerprint(calib_path: Path, template_path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(f"{FINGERPRINT_INPUT_VERSION}\n".encode("utf-8"))
    _hash_file(hasher, "calib.yaml", calib_path)
    _hash_file(hasher, "printer.cfg.template", template_path)
    return hasher.hexdigest()


def normalize_config_fingerprint(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)

    stripped = value.strip()
    if not stripped:
        return ""
    try:
        parsed = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return stripped
    if isinstance(parsed, str):
        return parsed
    return str(parsed)


def active_config_fingerprint(status: dict[str, Any]) -> str | None:
    configfile = status.get("configfile", {})
    config = configfile.get("config", {})
    macro_config = config.get(FINGERPRINT_MACRO_SECTION, {})
    if isinstance(macro_config, dict):
        fingerprint = macro_config.get(FINGERPRINT_CONFIG_OPTION)
        if fingerprint is not None:
            return normalize_config_fingerprint(fingerprint)

    settings = configfile.get("settings", {})
    macro_settings = settings.get(FINGERPRINT_MACRO_SECTION, {})
    if isinstance(macro_settings, dict):
        return normalize_config_fingerprint(
            macro_settings.get(FINGERPRINT_SETTINGS_KEY)
        )

    return None


def live_config_check_errors(
    *,
    local_sha256: str,
    remote_sha256: str,
    expected_fingerprint: str,
    status: dict[str, Any],
) -> list[str]:
    errors = []
    if remote_sha256 != local_sha256:
        errors.append(
            "remote printer.cfg sha256 does not match local printer.cfg "
            f"({remote_sha256} != {local_sha256})"
        )

    webhooks = status.get("webhooks", {})
    state = webhooks.get("state")
    if state != "ready":
        message = webhooks.get("state_message")
        detail = f": {message}" if message else ""
        errors.append(f"Klippy state is {state!r}, expected 'ready'{detail}")

    configfile = status.get("configfile", {})
    save_config_pending = configfile.get("save_config_pending")
    if save_config_pending is not False:
        errors.append(
            "configfile.save_config_pending is "
            f"{save_config_pending!r}, expected False"
        )

    actual_fingerprint = active_config_fingerprint(status)
    if actual_fingerprint is None:
        errors.append(
            "active Klippy config fingerprint is missing: "
            f"[{FINGERPRINT_MACRO_SECTION}] {FINGERPRINT_CONFIG_OPTION}"
        )
    elif actual_fingerprint != expected_fingerprint:
        errors.append(
            "active Klippy config fingerprint does not match local generated "
            f"fingerprint ({actual_fingerprint} != {expected_fingerprint})"
        )

    return errors


def template_values(
    calibration: dict[str, Any], config_fingerprint: str
) -> dict[str, str]:
    bed_grid_zero = calibration["bed_grid_zero"]
    t0 = calibration["tools"]["t0"]
    t1 = calibration["tools"]["t1"]
    nozzle_cam = calibration.get("nozzle_cam")
    eddy_relative = calibration.get("eddy_relative") or {
        "bed_center_x": 117.5,
        "bed_center_y": 117.5,
        "nozzle_to_coil_x": -8.18,
        "nozzle_to_coil_y": 9.0,
        "nozzle_to_coil_z": 2.5,
        "reg_drive_current": None,
        "calibrate": None,
        "capture": None,
    }
    if nozzle_cam is None:
        nozzle_cam = {
            "image_width": 1,
            "image_height": 1,
            "profile": "analysis",
            "reference_y": t0["y_endstop"] + 10.0,
            "reference_pixel_x": 0.0,
            "reference_pixel_y": 0.0,
            "axis_vector_x": 0.0,
            "axis_vector_y": 1.0,
            "template_file": "vision_calibration/nozzle_cam_bed_y_reference.png",
            "template_sha256": "0" * 64,
            "template_width": 1,
            "template_height": 1,
            "feature_mode": "gray_norm",
        }
        bed_y_calibrated = "false"
    else:
        bed_y_calibrated = "true"

    eddy_klipper_lines = []
    if eddy_relative.get("reg_drive_current") is not None:
        eddy_klipper_lines.append(
            f"reg_drive_current: {int(eddy_relative['reg_drive_current'])}"
        )
    if eddy_relative.get("calibrate"):
        eddy_klipper_lines.append(
            _render_config_option("calibrate", eddy_relative["calibrate"])
        )

    return {
        "bed_grid_zero_x": format_mm(bed_grid_zero["x"]),
        "bed_grid_zero_y": format_mm(bed_grid_zero["y"]),
        "t0_x_endstop": format_mm(t0["x_endstop"]),
        "t0_y_endstop": format_mm(t0["y_endstop"]),
        "t0_z_endstop": format_mm(t0["z_endstop"]),
        "t1_x_endstop": format_mm(t1["x_endstop"]),
        "t1_y_endstop": format_mm(t1["y_endstop"]),
        "t1_z_endstop": format_mm(t1["z_endstop"]),
        "t0_y_offset": format_mm(0.0),
        "t1_y_offset": format_mm(t0["y_endstop"] - t1["y_endstop"]),
        "t1_z_offset": format_mm(t0["z_endstop"] - t1["z_endstop"]),
        "config_fingerprint": config_fingerprint,
        "bed_y_calibrated": bed_y_calibrated,
        "bed_y_image_width": str(nozzle_cam["image_width"]),
        "bed_y_image_height": str(nozzle_cam["image_height"]),
        "bed_y_profile": str(nozzle_cam["profile"]),
        "bed_y_reference_y": format_mm(nozzle_cam["reference_y"]),
        "bed_y_reference_pixel_x": f"{nozzle_cam['reference_pixel_x']:.4f}",
        "bed_y_reference_pixel_y": f"{nozzle_cam['reference_pixel_y']:.4f}",
        "bed_y_axis_vector_x": f"{nozzle_cam['axis_vector_x']:.6f}",
        "bed_y_axis_vector_y": f"{nozzle_cam['axis_vector_y']:.6f}",
        "bed_y_template_path": (
            "/home/pi/printer_data/config/" + str(nozzle_cam["template_file"])
        ),
        "bed_y_template_sha256": str(nozzle_cam["template_sha256"]),
        "bed_y_template_width": str(nozzle_cam["template_width"]),
        "bed_y_template_height": str(nozzle_cam["template_height"]),
        "bed_y_feature_mode": str(nozzle_cam["feature_mode"]),
        "eddy_bed_center_x": format_mm(eddy_relative["bed_center_x"]),
        "eddy_bed_center_y": format_mm(eddy_relative["bed_center_y"]),
        "eddy_nozzle_to_coil_x": format_mm(eddy_relative["nozzle_to_coil_x"]),
        "eddy_nozzle_to_coil_y": format_mm(eddy_relative["nozzle_to_coil_y"]),
        "eddy_nozzle_to_coil_z": format_mm(eddy_relative["nozzle_to_coil_z"]),
        "eddy_klipper_calibration": "\n".join(eddy_klipper_lines),
        "eddy_mesh_min_x": format_mm(eddy_relative["bed_center_x"] - 80.0),
        "eddy_mesh_min_y": format_mm(eddy_relative["bed_center_y"] - 80.0),
        "eddy_mesh_max_x": format_mm(eddy_relative["bed_center_x"] + 80.0),
        "eddy_mesh_max_y": format_mm(eddy_relative["bed_center_y"] + 80.0),
    }


def render_config(calib_path: Path, template_path: Path) -> str:
    calibration = load_calibration(calib_path)
    config_fingerprint = compute_config_fingerprint(calib_path, template_path)
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.substitute(template_values(calibration, config_fingerprint))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render printer.cfg from calib.yaml and printer.cfg.template."
    )
    parser.add_argument("--calib", type=Path, default=DEFAULT_CALIB_PATH)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the output file is stale.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write the rendered config to stdout instead of printer.cfg.",
    )
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        help="Write the generated config source fingerprint to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.fingerprint:
        print(compute_config_fingerprint(args.calib, args.template))
        return 0

    rendered = render_config(args.calib, args.template)

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    if args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"{args.output} is missing; regenerate printer.cfg.", file=sys.stderr)
            return 1
        if current != rendered:
            print(
                f"{args.output} is stale; run {Path(__file__).name}.",
                file=sys.stderr,
            )
            return 1
        return 0

    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
