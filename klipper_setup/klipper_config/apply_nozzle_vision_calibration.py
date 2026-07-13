#!/usr/bin/env python3
"""Apply accepted nozzle vision sweep measurements to calib.yaml."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = SCRIPT_DIR / "calib.yaml"
NOZZLE_Z_MEASUREMENT = "nozzle_cam_nozzle_z_offsets"


def _load_json_source(source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=15) as response:
            return json.loads(response.read())
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _number(value: Any, label: str) -> float:
    if value is None:
        raise ValueError(f"Missing {label}")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric, got {value!r}") from None


def extract_measurement(payload: dict[str, Any], source: str) -> dict[str, Any]:
    analysis = payload.get("analysis", payload)
    if not payload.get("ok", analysis.get("ok")):
        raise ValueError(f"{source}: result is not ok")
    measurement = payload.get("measurement") or analysis.get("measurement")
    if measurement == NOZZLE_Z_MEASUREMENT:
        suggested = payload.get("suggested_calib_yaml") or analysis.get(
            "suggested_calib_yaml"
        )
        if suggested is None:
            suggested = (
                payload.get("facts")
                or analysis.get("facts")
                or analysis.get("facts_preview")
                or {}
            ).get("suggested_calib_yaml")
        tools = (suggested or {}).get("tools") or {}
        t0 = tools.get("t0") or {}
        t1 = tools.get("t1") or {}
        return {
            "measurement": NOZZLE_Z_MEASUREMENT,
            "t0_z_endstop": _number(
                t0.get("z_endstop"), f"{source}: suggested t0.z_endstop"
            ),
            "t1_z_endstop": _number(
                t1.get("z_endstop"), f"{source}: suggested t1.z_endstop"
            ),
            "suggested_runtime_t1_z_offset": _number(
                payload.get("suggested_runtime_t1_z_offset")
                or analysis.get("suggested_runtime_t1_z_offset")
                or (
                    payload.get("facts")
                    or analysis.get("facts")
                    or analysis.get("facts_preview")
                    or {}
                ).get("suggested_runtime_t1_z_offset"),
                f"{source}: suggested_runtime_t1_z_offset",
            ),
        }

    cross_match = analysis.get("cross_match", {})
    if not cross_match.get("accepted"):
        raise ValueError(f"{source}: cross-match was not accepted")

    nozzle_delta = (
        analysis.get("nozzle_delta_t1_minus_t0")
        or analysis.get("nozzle_delta")
        or cross_match
    )
    return {
        "measurement": "idex_nozzle_relative_offset",
        "along_x_mm": _number(
            nozzle_delta.get("along_x_mm_approx")
            or cross_match.get("along_x_mm_approx"),
            f"{source}: along_x_mm_approx",
        ),
        "perpendicular_mm": _number(
            nozzle_delta.get("perpendicular_mm_approx")
            or cross_match.get("perpendicular_mm_approx"),
            f"{source}: perpendicular_mm_approx",
        ),
    }


def load_calib(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def write_calib(path: Path, data: dict[str, Any]) -> None:
    bed = data["bed_grid_zero"]
    t0 = data["tools"]["t0"]
    t1 = data["tools"]["t1"]
    path.write_text(
        "\n".join(
            [
                "bed_grid_zero:",
                f"  x: {float(bed['x']):.3f}",
                f"  y: {float(bed['y']):.3f}",
                "tools:",
                "  t0:",
                f"    x_endstop: {float(t0['x_endstop']):.3f}",
                f"    y_endstop: {float(t0['y_endstop']):.3f}",
                f"    z_endstop: {float(t0['z_endstop']):.3f}",
                "  t1:",
                f"    x_endstop: {float(t1['x_endstop']):.3f}",
                f"    y_endstop: {float(t1['y_endstop']):.3f}",
                f"    z_endstop: {float(t1['z_endstop']):.3f}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def apply_measurement(
    calib: dict[str, Any], *, along_x_mm: float, perpendicular_mm: float, update_y: bool
) -> dict[str, Any]:
    t0 = calib["tools"]["t0"]
    t1 = calib["tools"]["t1"]

    old_x = float(t1["x_endstop"])
    t1["x_endstop"] = round(old_x + along_x_mm, 3)

    if update_y:
        current_y_offset = float(t0["y_endstop"]) - float(t1["y_endstop"])
        new_y_offset = current_y_offset - perpendicular_mm
        t1["y_endstop"] = round(float(t0["y_endstop"]) - new_y_offset, 3)

    return calib


def apply_z_measurement(
    calib: dict[str, Any], *, t0_z_endstop: float, t1_z_endstop: float, update_z: bool
) -> dict[str, Any]:
    if update_z:
        calib["tools"]["t0"]["z_endstop"] = round(t0_z_endstop, 3)
        calib["tools"]["t1"]["z_endstop"] = round(t1_z_endstop, 3)
    return calib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply accepted IDEX nozzle vision sweep results to calib.yaml."
    )
    parser.add_argument("results", nargs="+", help="result.json path or URL")
    parser.add_argument("--calib", type=Path, default=DEFAULT_CALIB_PATH)
    parser.add_argument(
        "--update-y",
        action="store_true",
        help="Also apply one provisional T1 Y correction from perpendicular_mm_approx.",
    )
    parser.add_argument(
        "--update-z",
        action="store_true",
        help="Apply accepted nozzle_cam_nozzle_z_offsets facts to both Z endstops.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the proposed values without writing calib.yaml.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    measurements = [
        extract_measurement(_load_json_source(source), source) for source in args.results
    ]
    measurement_names = {str(item["measurement"]) for item in measurements}
    if len(measurement_names) != 1:
        raise ValueError(f"Cannot mix measurement types: {sorted(measurement_names)}")
    measurement = measurements[0]["measurement"]
    if measurement == NOZZLE_Z_MEASUREMENT:
        t0_z_endstop = statistics.fmean(item["t0_z_endstop"] for item in measurements)
        t1_z_endstop = statistics.fmean(item["t1_z_endstop"] for item in measurements)
        runtime_t1_z_offset = statistics.fmean(
            item["suggested_runtime_t1_z_offset"] for item in measurements
        )
        calib = load_calib(args.calib)
        old_t0 = dict(calib["tools"]["t0"])
        old_t1 = dict(calib["tools"]["t1"])
        apply_z_measurement(
            calib,
            t0_z_endstop=t0_z_endstop,
            t1_z_endstop=t1_z_endstop,
            update_z=args.update_z,
        )
        new_t0 = calib["tools"]["t0"]
        new_t1 = calib["tools"]["t1"]
        print(f"accepted_results: {len(measurements)}")
        print(f"avg_t0_z_endstop: {t0_z_endstop:.5f}")
        print(f"avg_t1_z_endstop: {t1_z_endstop:.5f}")
        print(f"suggested_runtime_t1_z_offset: {runtime_t1_z_offset:.5f}")
        if args.update_z:
            print(
                "t0.z_endstop: "
                f"{float(old_t0['z_endstop']):.3f} -> {float(new_t0['z_endstop']):.3f}"
            )
            print(
                "t1.z_endstop: "
                f"{float(old_t1['z_endstop']):.3f} -> {float(new_t1['z_endstop']):.3f}"
            )
        else:
            print("t0.z_endstop: unchanged (--update-z not set)")
            print("t1.z_endstop: unchanged (--update-z not set)")
        if args.update_z and not args.dry_run:
            write_calib(args.calib, calib)
        return 0

    along_x_mm = statistics.fmean(item["along_x_mm"] for item in measurements)
    perpendicular_mm = statistics.fmean(item["perpendicular_mm"] for item in measurements)

    calib = load_calib(args.calib)
    old_t1 = dict(calib["tools"]["t1"])
    apply_measurement(
        calib,
        along_x_mm=along_x_mm,
        perpendicular_mm=perpendicular_mm,
        update_y=args.update_y,
    )
    new_t1 = calib["tools"]["t1"]

    print(f"accepted_results: {len(measurements)}")
    print(f"avg_along_x_mm: {along_x_mm:.5f}")
    print(f"avg_perpendicular_mm: {perpendicular_mm:.5f}")
    print(
        "t1.x_endstop: "
        f"{float(old_t1['x_endstop']):.3f} -> {float(new_t1['x_endstop']):.3f}"
    )
    if args.update_y:
        print(
            "t1.y_endstop: "
            f"{float(old_t1['y_endstop']):.3f} -> {float(new_t1['y_endstop']):.3f}"
        )
    else:
        print("t1.y_endstop: unchanged")

    if not args.dry_run:
        write_calib(args.calib, calib)
    return 0


if __name__ == "__main__":
    sys.exit(main())
