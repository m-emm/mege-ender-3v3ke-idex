#!/usr/bin/env python3
"""Apply accepted nozzle vision sweep measurements to calib.yaml."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = SCRIPT_DIR / "calib.yaml"
NOZZLE_Z_MEASUREMENT = "nozzle_cam_nozzle_z_offsets"
BED_Y_MEASUREMENT = "nozzle_cam_bed_y_motion"
BED_Y_JOB_KIND = "nozzle_cam_bed_y_sweep"
VISION_HASH_PLACEHOLDER = "sha256:PLACEHOLDER"


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
    if measurement == BED_Y_MEASUREMENT:
        if not payload.get("accepted", analysis.get("accepted", analysis.get("ok"))):
            raise ValueError(f"{source}: bed-Y measurement was not accepted")
        candidate = payload.get("calibration_candidate") or analysis.get(
            "calibration_candidate"
        )
        if not isinstance(candidate, dict):
            raise ValueError(f"{source}: missing calibration_candidate")
        vector = candidate.get("axis_vector_px_per_mm")
        pixel = candidate.get("reference_pixel_px")
        roi = candidate.get("template_roi_px")
        image_size = candidate.get("image_size_px") or {}
        if not isinstance(vector, list) or len(vector) != 2:
            raise ValueError(f"{source}: invalid axis_vector_px_per_mm")
        if not isinstance(pixel, list) or len(pixel) != 2:
            raise ValueError(f"{source}: invalid reference_pixel_px")
        if not isinstance(roi, list) or len(roi) != 4:
            raise ValueError(f"{source}: invalid template_roi_px")
        return {
            "measurement": BED_Y_MEASUREMENT,
            "source": source,
            "camera": payload.get("camera") or analysis.get("camera") or "nozzle_cam",
            "profile": payload.get("profile") or analysis.get("profile") or "analysis",
            "job_id": payload.get("job_id") or analysis.get("job_id"),
            "manifest_hash": payload.get("manifest_hash") or analysis.get("manifest_hash"),
            "reference_y_offset_mm": _number(
                candidate.get("reference_y_offset_mm"),
                f"{source}: reference_y_offset_mm",
            ),
            "reference_printer_y_mm": _number(
                candidate.get("reference_printer_y_mm"),
                f"{source}: reference_printer_y_mm",
            ),
            "reference_pixel_px": [
                _number(pixel[0], f"{source}: reference_pixel_px[0]"),
                _number(pixel[1], f"{source}: reference_pixel_px[1]"),
            ],
            "axis_vector_px_per_mm": [
                _number(vector[0], f"{source}: axis_vector_px_per_mm[0]"),
                _number(vector[1], f"{source}: axis_vector_px_per_mm[1]"),
            ],
            "template_roi_px": [
                _number(value, f"{source}: template_roi_px") for value in roi
            ],
            "image_width": int(_number(image_size.get("width"), f"{source}: image width")),
            "image_height": int(
                _number(image_size.get("height"), f"{source}: image height")
            ),
            "source_frame": str(candidate.get("source_frame") or ""),
            "source_image_sha256": candidate.get("source_image_sha256"),
            "feature_mode": str(candidate.get("feature_mode") or ""),
            "selected_roi": str(candidate.get("selected_roi") or ""),
            "capture_pose": candidate.get("capture_pose") or {},
            "fit_residual_rms_px": _number(
                candidate.get("fit_residual_rms_px"), f"{source}: fit residual"
            ),
            "correlation_min": _number(
                candidate.get("correlation_min"), f"{source}: correlation min"
            ),
            "correlation_median": _number(
                candidate.get("correlation_median"), f"{source}: correlation median"
            ),
        }
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
    lines = [
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
    ]
    cameras = data.get("cameras")
    if cameras:
        lines.extend(
            [
                yaml.safe_dump(
                    {"cameras": cameras}, sort_keys=False, default_flow_style=False
                ).rstrip(),
            ]
        )
    rendered = "\n".join(lines) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


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


def _local_job_dir(source: str) -> Path:
    if source.startswith(("http://", "https://")):
        raise ValueError("bed-Y calibration import requires local job artifacts")
    source_path = Path(source).resolve()
    if source_path.parent.name == "analysis":
        return source_path.parent.parent
    raise ValueError(
        "bed-Y result must be analysis/facts.json or analysis/result.json inside a job"
    )


def _compute_manifest_hash(manifest: dict[str, Any]) -> str:
    canonical = dict(manifest)
    canonical["manifest_hash"] = VISION_HASH_PLACEHOLDER
    payload = (
        json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_bed_y_job_artifacts(
    measurement: dict[str, Any], job_dir: Path
) -> None:
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"missing bed-Y calibration manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("bed-Y calibration manifest must be a JSON object")

    expected_hash = str(measurement.get("manifest_hash") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_hash):
        raise ValueError("bed-Y result has no valid manifest_hash")
    if manifest.get("manifest_hash") != expected_hash:
        raise ValueError("bed-Y result manifest_hash does not match manifest artifact")
    actual_hash = _compute_manifest_hash(manifest)
    if actual_hash != expected_hash:
        raise ValueError(
            f"bed-Y manifest content hash mismatch: {actual_hash} != {expected_hash}"
        )

    expected_fields = {
        "job_id": measurement["job_id"],
        "camera": measurement["camera"],
        "profile": measurement["profile"],
        "kind": BED_Y_JOB_KIND,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(
                f"bed-Y manifest {field} {manifest.get(field)!r} does not match "
                f"result {expected!r}"
            )

    source_frame = measurement["source_frame"]
    manifest_frame = next(
        (
            frame
            for frame in manifest.get("frames") or []
            if frame.get("frame") == source_frame
        ),
        None,
    )
    if manifest_frame is None:
        raise ValueError(f"bed-Y source frame {source_frame!r} is not in manifest")
    if (
        abs(
            float(manifest_frame.get("y_offset"))
            - measurement["reference_y_offset_mm"]
        )
        > 1.0e-6
    ):
        raise ValueError("bed-Y source frame offset does not match calibration result")
    pose = manifest_frame.get("pose") or {}
    if (
        abs(float(pose.get("y")) - measurement["reference_printer_y_mm"])
        > 1.0e-6
    ):
        raise ValueError("bed-Y source frame pose does not match reference printer Y")

    metadata_path = job_dir / "frames" / f"{source_frame}.json"
    if not metadata_path.is_file():
        raise ValueError(f"missing bed-Y source frame metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("bed-Y source frame metadata must be a JSON object")
    metadata_fields = {
        "job_id": measurement["job_id"],
        "frame": source_frame,
        "camera": measurement["camera"],
        "profile": measurement["profile"],
        "image_sha256": measurement["source_image_sha256"],
        "width": measurement["image_width"],
        "height": measurement["image_height"],
    }
    for field, expected in metadata_fields.items():
        if metadata.get(field) != expected:
            raise ValueError(
                f"bed-Y frame metadata {field} {metadata.get(field)!r} does not "
                f"match result {expected!r}"
            )


def build_bed_y_calibration(
    measurement: dict[str, Any],
    *,
    calib_path: Path,
    dry_run: bool,
    reference_y_offset_mm: float,
) -> tuple[dict[str, Any], Path, str]:
    import cv2

    if measurement["camera"] != "nozzle_cam":
        raise ValueError("bed-Y calibration requires camera nozzle_cam")
    if not measurement["job_id"] or not measurement["source_frame"]:
        raise ValueError("bed-Y calibration requires job_id and source_frame")
    if not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(measurement.get("source_image_sha256") or "")
    ):
        raise ValueError("bed-Y calibration requires a valid source image hash")
    if (
        abs(
            float(measurement["reference_y_offset_mm"])
            - float(reference_y_offset_mm)
        )
        > 1.0e-6
    ):
        raise ValueError(
            "bed-Y calibration candidate does not match --reference-y-offset"
        )
    if measurement["feature_mode"] not in ("gray_norm", "clahe", "grad_y", "grad_mag"):
        raise ValueError(f"unsupported bed-Y feature mode {measurement['feature_mode']!r}")
    fit_residual = float(measurement["fit_residual_rms_px"])
    correlation_min = float(measurement["correlation_min"])
    correlation_median = float(measurement["correlation_median"])
    if not all(
        math.isfinite(value)
        for value in (fit_residual, correlation_min, correlation_median)
    ):
        raise ValueError("bed-Y calibration fit quality must be finite")
    if fit_residual > 0.5:
        raise ValueError("bed-Y calibration fit residual exceeds 0.5 px")
    if correlation_min < 0.95 or not correlation_min <= correlation_median <= 1.0:
        raise ValueError("bed-Y calibration correlation quality is invalid")
    vector_x, vector_y = (
        float(value) for value in measurement["axis_vector_px_per_mm"]
    )
    if not all(math.isfinite(value) for value in (vector_x, vector_y)):
        raise ValueError("bed-Y calibration axis vector must be finite")
    if vector_x * vector_x + vector_y * vector_y <= 1.0e-12:
        raise ValueError("bed-Y calibration axis vector must be non-zero")

    calib = load_calib(calib_path)
    expected_reference_y = (
        float(calib["tools"]["t0"]["y_endstop"]) + float(reference_y_offset_mm)
    )
    if (
        abs(float(measurement["reference_printer_y_mm"]) - expected_reference_y)
        > 1.0e-6
    ):
        raise ValueError(
            "bed-Y reference printer Y does not match T0 Y endstop plus offset"
        )
    job_dir = _local_job_dir(str(measurement["source"]))
    _validate_bed_y_job_artifacts(measurement, job_dir)
    source_image = job_dir / "frames" / f"{measurement['source_frame']}.jpg"
    if not source_image.exists():
        raise ValueError(f"missing bed-Y calibration source frame: {source_image}")
    image = cv2.imread(str(source_image))
    if image is None:
        raise ValueError(f"could not read bed-Y calibration source frame: {source_image}")
    height, width = image.shape[:2]
    if (width, height) != (
        int(measurement["image_width"]),
        int(measurement["image_height"]),
    ):
        raise ValueError("bed-Y calibration frame dimensions do not match facts")
    source_hash = "sha256:" + hashlib.sha256(source_image.read_bytes()).hexdigest()
    expected_source_hash = str(measurement["source_image_sha256"])
    if expected_source_hash != source_hash:
        raise ValueError(
            f"bed-Y source image hash mismatch: {source_hash} != {expected_source_hash}"
        )

    roi_x, roi_y, roi_width, roi_height = measurement["template_roi_px"]
    x = int(round(roi_x))
    y = int(round(roi_y))
    template_width = int(round(roi_width))
    template_height = int(round(roi_height))
    if (
        x < 0
        or y < 0
        or template_width <= 0
        or template_height <= 0
        or x + template_width > width
        or y + template_height > height
    ):
        raise ValueError("bed-Y template ROI is outside the calibration frame")
    template = image[y : y + template_height, x : x + template_width]
    candidate_pixel_x, candidate_pixel_y = measurement["reference_pixel_px"]
    template_center = (x + template_width / 2.0, y + template_height / 2.0)
    if (
        math.hypot(
            float(candidate_pixel_x) - template_center[0],
            float(candidate_pixel_y) - template_center[1],
        )
        > 1.0
    ):
        raise ValueError("bed-Y reference pixel does not match template ROI center")
    encoded_ok, encoded = cv2.imencode(".png", template)
    if not encoded_ok:
        raise ValueError("could not encode bed-Y calibration template")
    template_bytes = bytes(encoded)
    template_sha256 = hashlib.sha256(template_bytes).hexdigest()
    relative_template = Path("vision_calibration") / "nozzle_cam_bed_y_reference.png"
    template_path = calib_path.parent / relative_template
    if not dry_run:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = template_path.with_name(f".{template_path.name}.tmp")
        temporary.write_bytes(template_bytes)
        os.replace(temporary, template_path)

    mapping = {
        "image": {
            "width_px": width,
            "height_px": height,
            "profile": measurement["profile"],
        },
        "printer_to_image": {
            "reference": {
                "printer_y_mm": round(float(measurement["reference_printer_y_mm"]), 4),
                "pixel_x": round(x + template_width / 2.0, 4),
                "pixel_y": round(y + template_height / 2.0, 4),
            },
            "axes_px_per_mm": {
                "y": {
                    "x": round(vector_x, 6),
                    "y": round(vector_y, 6),
                }
            },
        },
        "bed_y_feature": {
            "template_file": str(relative_template),
            "template_sha256": template_sha256,
            "template_width_px": template_width,
            "template_height_px": template_height,
            "feature_mode": measurement["feature_mode"],
            "selected_roi": measurement["selected_roi"],
            "quality": {
                "fit_residual_rms_px": round(
                    float(measurement["fit_residual_rms_px"]), 6
                ),
                "correlation_min": round(float(measurement["correlation_min"]), 6),
                "correlation_median": round(
                    float(measurement["correlation_median"]), 6
                ),
            },
            "source": {
                "job_id": measurement["job_id"],
                "frame": measurement["source_frame"],
                "manifest_sha256": measurement["manifest_hash"],
                "image_sha256": source_hash,
                "capture_pose": measurement["capture_pose"],
            },
        },
    }
    return mapping, template_path, template_sha256


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
        "--update-bed-y",
        action="store_true",
        help="Persist an accepted nozzle_cam_bed_y_motion mapping and template.",
    )
    parser.add_argument(
        "--reference-y-offset",
        type=float,
        default=10.0,
        help="Required Y offset of the reference sweep frame (default: 10 mm).",
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
    if measurement == BED_Y_MEASUREMENT:
        if len(measurements) != 1:
            raise ValueError("bed-Y calibration import accepts exactly one result")
        if not args.update_bed_y:
            raise ValueError("bed-Y calibration import requires --update-bed-y")
        calib = load_calib(args.calib)
        mapping, template_path, template_sha256 = build_bed_y_calibration(
            measurements[0],
            calib_path=args.calib,
            dry_run=args.dry_run,
            reference_y_offset_mm=args.reference_y_offset,
        )
        calib.setdefault("cameras", {})[measurements[0]["camera"]] = mapping
        print(f"camera: {measurements[0]['camera']}")
        print(f"reference_y_mm: {measurements[0]['reference_printer_y_mm']:.4f}")
        print(
            "axis_vector_px_per_mm: "
            f"[{measurements[0]['axis_vector_px_per_mm'][0]:.6f}, "
            f"{measurements[0]['axis_vector_px_per_mm'][1]:.6f}]"
        )
        print(f"template: {template_path}")
        print(f"template_sha256: {template_sha256}")
        if not args.dry_run:
            write_calib(args.calib, calib)
        return 0
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
