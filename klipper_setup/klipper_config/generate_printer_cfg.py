#!/usr/bin/env python3
"""Render the active Klipper config from absolute IDEX calibration values."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from string import Template
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = SCRIPT_DIR / "calib.yaml"
DEFAULT_TEMPLATE_PATH = SCRIPT_DIR / "printer.cfg.template"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "printer.cfg"


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
    }


def format_mm(value: float) -> str:
    return f"{value:.3f}"


def template_values(calibration: dict[str, Any]) -> dict[str, str]:
    bed_grid_zero = calibration["bed_grid_zero"]
    t0 = calibration["tools"]["t0"]
    t1 = calibration["tools"]["t1"]

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
    }


def render_config(calib_path: Path, template_path: Path) -> str:
    calibration = load_calibration(calib_path)
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.substitute(template_values(calibration))


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
