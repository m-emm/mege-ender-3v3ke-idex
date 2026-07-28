"""Report-only cold Eddy relative-calibration helpers.

This module deliberately contains no configuration writer.  It generates a
hashed motion/sample manifest, analyzes raw LDC1612 windows, and emits only
artifacts and an inactive Klipper candidate.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HASH_PLACEHOLDER = "sha256:PLACEHOLDER"
SCHEMA_VERSION = 1
SAMPLE_RATE_HZ = 400
SETTLE_MS = 100
DURATION_MS = 250
APPROACH_HOP_MM = 0.5
DESCEND_SPEED_MM_S = 5.0
MIN_USABLE_LEVELS = 12
MIN_USABLE_SPAN_MM = 1.0
MIN_CLEARANCE_MM = 0.5
DEFAULT_REPEATABILITY_SIGMA_MM = 0.05
MAX_REFERENCE_EQUIVALENT_DRIFT_MM = 0.05


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def gcode_float(value: float) -> str:
    rendered = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return "0" if rendered in ("", "-0") else rendered


def median_mad(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    median = float(statistics.median(values))
    mad = float(statistics.median(abs(value - median) for value in values))
    return median, mad


def conservative_lower_gap_mm(
    vision_sigma_mm: float,
    repeatability_sigma_mm: float = DEFAULT_REPEATABILITY_SIGMA_MM,
) -> float:
    combined = math.hypot(float(vision_sigma_mm), float(repeatability_sigma_mm))
    return MIN_CLEARANCE_MM + 3.0 * combined


def calibration_levels(
    lower_gap_mm: float, upper_gap_mm: float = 4.0, step_mm: float = 0.1
) -> list[float]:
    if step_mm <= 0:
        raise ValueError("step_mm must be positive")
    start_index = math.ceil((float(lower_gap_mm) - 1.0e-9) / step_mm)
    end_index = math.floor((float(upper_gap_mm) + 1.0e-9) / step_mm)
    return [round(index * step_mm, 4) for index in range(start_index, end_index + 1)]


def build_sample_schedule(
    *,
    nozzle_zero_error_mm: float,
    eddy_above_nozzle_mm: float,
    vision_sigma_mm: float,
    z_min_mm: float,
    z_max_mm: float,
    upper_gap_mm: float = 4.0,
    step_mm: float = 0.1,
    repeatability_sigma_mm: float = DEFAULT_REPEATABILITY_SIGMA_MM,
) -> dict[str, Any]:
    requested_lower = conservative_lower_gap_mm(
        vision_sigma_mm, repeatability_sigma_mm
    )
    reachable_lower = max(
        requested_lower,
        float(z_min_mm) + float(nozzle_zero_error_mm),
    )
    reachable_upper = min(
        float(upper_gap_mm),
        float(z_max_mm) + float(nozzle_zero_error_mm) - APPROACH_HOP_MM,
    )
    levels = calibration_levels(reachable_lower, reachable_upper, step_mm)
    if len(levels) < MIN_USABLE_LEVELS:
        raise RuntimeError(
            "safe reachable Eddy sweep has fewer than "
            f"{MIN_USABLE_LEVELS} levels ({len(levels)})"
        )
    if levels[-1] - levels[0] < MIN_USABLE_SPAN_MM:
        raise RuntimeError(
            "safe reachable Eddy sweep spans less than "
            f"{MIN_USABLE_SPAN_MM:.1f}mm"
        )

    samples: list[dict[str, Any]] = []

    def add_sample(
        pass_name: str, approach: str, gap: float, *, reference: bool = False
    ) -> None:
        seq = len(samples)
        sample_id = (
            f"{pass_name}_{seq:03d}_g{gcode_float(gap).replace('.', 'p')}"
        )
        samples.append(
            {
                "seq": seq,
                "sample": sample_id,
                "pass": pass_name,
                "reference": reference,
                "approach": approach,
                "nozzle_gap": round(gap, 4),
                "coil_gap": round(gap + eddy_above_nozzle_mm, 4),
                "commanded_z": round(gap - nozzle_zero_error_mm, 4),
                "settle_ms": SETTLE_MS,
                "duration_ms": DURATION_MS,
            }
        )

    reference_gap = min(3.0, levels[-1])
    if reference_gap < levels[0]:
        reference_gap = levels[-1]
    add_sample("reference_before", "descending", reference_gap, reference=True)
    for pass_index in (1, 2):
        for gap in reversed(levels):
            add_sample(f"descending_{pass_index}", "descending", gap)
        if pass_index == 1:
            add_sample("reference_mid", "descending", reference_gap, reference=True)

    validation_gaps = sorted(
        {
            levels[0],
            levels[-1],
            *(
                value
                for value in (1.0, 2.0, 3.0)
                if levels[0] <= value <= levels[-1]
            ),
        }
    )
    for index, gap in enumerate(validation_gaps):
        add_sample(
            "ascending_validation",
            "descending_anchor" if index == 0 else "ascending",
            gap,
        )
    add_sample("reference_after", "descending", reference_gap, reference=True)

    for sample in samples:
        command_z = float(sample["commanded_z"])
        if command_z < z_min_mm - 1.0e-9 or command_z > z_max_mm + 1.0e-9:
            raise RuntimeError(
                f"sample {sample['sample']} commanded Z={command_z:.4f} "
                f"outside configured [{z_min_mm:.4f}, {z_max_mm:.4f}]"
            )
        if sample["approach"] in ("descending", "descending_anchor"):
            hop_z = command_z + APPROACH_HOP_MM
            if hop_z > z_max_mm + 1.0e-9:
                raise RuntimeError(
                    f"sample {sample['sample']} approach Z={hop_z:.4f} "
                    f"above configured maximum {z_max_mm:.4f}"
                )

    return {
        "requested_lower_gap_mm": round(requested_lower, 6),
        "reachable_lower_gap_mm": levels[0],
        "reachable_upper_gap_mm": levels[-1],
        "truncated_at_lower_bound": levels[0] > requested_lower + 0.0001,
        "levels": levels,
        "samples": samples,
        "combined_uncertainty_mm": round(
            math.hypot(vision_sigma_mm, repeatability_sigma_mm), 6
        ),
        "repeatability_sigma_assumption_mm": repeatability_sigma_mm,
    }


def build_sweep_manifest(
    *,
    job_id: str,
    center_x: float,
    center_y: float,
    schedule: dict[str, Any],
    vision_facts_hash: str,
    drive_current: dict[str, Any],
) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eddy_relative_frequency_sweep",
        "job_id": job_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_hash": HASH_PLACEHOLDER,
        "gcode_hash": HASH_PLACEHOLDER,
        "report_only": True,
        "save_config_allowed": False,
        "center": {"x": round(center_x, 4), "y": round(center_y, 4)},
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "settle_ms": SETTLE_MS,
        "duration_ms": DURATION_MS,
        "approach_hop_mm": APPROACH_HOP_MM,
        "descend_speed_mm_s": DESCEND_SPEED_MM_S,
        "vision_facts_hash": vision_facts_hash,
        "drive_current": drive_current,
        "schedule": {
            key: value
            for key, value in schedule.items()
            if key != "samples"
        },
        "samples": schedule["samples"],
    }
    manifest_hash = sha256_prefixed(canonical_json_bytes(manifest))
    manifest["manifest_hash"] = manifest_hash
    return manifest


def render_sweep_gcode(
    manifest: dict[str, Any], *, final_z_mm: float = 20.0
) -> str:
    center = manifest["center"]
    lines = [
        f"; report-only Eddy relative sweep for {manifest['job_id']}",
        "; no SAVE_CONFIG; no probe calibration activation",
        "G90",
        "T0",
        f"G1 Z{gcode_float(final_z_mm)} F1200",
        (
            f"G1 X{gcode_float(center['x'])} Y{gcode_float(center['y'])} "
            f"Z{gcode_float(final_z_mm)} F3600"
        ),
        "M400",
    ]
    previous_approach = None
    for sample in manifest["samples"]:
        command_z = float(sample["commanded_z"])
        approach = sample["approach"]
        if approach in ("descending", "descending_anchor"):
            lines.extend(
                [
                    f"G1 Z{gcode_float(command_z + APPROACH_HOP_MM)} F1200",
                    "M400",
                    f"G1 Z{gcode_float(command_z)} F{DESCEND_SPEED_MM_S * 60.0:.0f}",
                    "M400",
                ]
            )
        elif approach == "ascending":
            if previous_approach not in ("descending_anchor", "ascending"):
                raise RuntimeError(
                    "ascending sample does not follow the validation anchor"
                )
            lines.extend(
                [
                    f"G1 Z{gcode_float(command_z)} F{DESCEND_SPEED_MM_S * 60.0:.0f}",
                    "M400",
                ]
            )
        else:
            raise RuntimeError(f"unsupported approach {approach!r}")
        lines.append(
            "VISION_EDDY_SAMPLE_SYNC "
            f"JOB={manifest['job_id']} SEQ={sample['seq']} "
            f"SAMPLE={sample['sample']} "
            f"MANIFEST_HASH={manifest['manifest_hash']} "
            f"APPROACH={approach} "
            f"COMMANDED_Z={gcode_float(command_z)} "
            f"NOZZLE_GAP={gcode_float(sample['nozzle_gap'])} "
            f"COIL_GAP={gcode_float(sample['coil_gap'])} "
            f"SETTLE_MS={SETTLE_MS} DURATION_MS={DURATION_MS}"
        )
        previous_approach = approach
    lines.extend([f"G1 Z{gcode_float(final_z_mm)} F1200", "M400"])
    return "\n".join(lines) + "\n"


def compute_gcode_hash(gcode: str) -> str:
    canonical = re.sub(
        r"\bMANIFEST_HASH=sha256:\S+",
        "MANIFEST_HASH=sha256:PLACEHOLDER",
        gcode.replace("\r\n", "\n").replace("\r", "\n"),
    )
    return sha256_prefixed(canonical.encode("utf-8"))


def finalize_sweep_hashes(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    manifest = json.loads(json.dumps(manifest))
    manifest["manifest_hash"] = HASH_PLACEHOLDER
    manifest["gcode_hash"] = HASH_PLACEHOLDER
    manifest["gcode_hash"] = compute_gcode_hash(render_sweep_gcode(manifest))
    manifest["manifest_hash"] = HASH_PLACEHOLDER
    manifest["manifest_hash"] = sha256_prefixed(canonical_json_bytes(manifest))
    gcode = render_sweep_gcode(manifest)
    if compute_gcode_hash(gcode) != manifest["gcode_hash"]:
        raise RuntimeError("Eddy sweep G-code hash did not stabilize")
    return manifest, gcode


def validate_monotonic_points(
    points: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    accepted: list[dict[str, Any]] = []
    failures: list[str] = []
    last: dict[str, Any] | None = None
    for point in sorted(points, key=lambda value: float(value["nozzle_gap"])):
        if last is not None:
            freq_diff = float(last["median_frequency_hz"]) - float(
                point["median_frequency_hz"]
            )
            combined_mad = math.hypot(
                float(last["mad_frequency_hz"]),
                float(point["mad_frequency_hz"]),
            )
            if freq_diff < 0:
                failures.append(
                    "frequency stops decreasing at "
                    f"{point['nozzle_gap']:.3f}mm"
                )
                break
            if freq_diff < 2.5 * combined_mad:
                failures.append(
                    "adjacent frequency change is below 2.5 combined MAD at "
                    f"{last['nozzle_gap']:.3f}->{point['nozzle_gap']:.3f}mm"
                )
                break
        accepted.append(point)
        last = point
    return accepted, failures


def _temperature(record: dict[str, Any], key: str) -> float | None:
    value = ((record.get("temperatures") or {}).get(key) or {}).get("temperature")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_sample_records(sweep_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sample in manifest["samples"]:
        path = sweep_dir / "raw" / f"{sample['seq']:03d}_{sample['sample']}.json"
        if not path.is_file():
            raise RuntimeError(f"missing Eddy sample sidecar: {path}")
        record = json.loads(path.read_text(encoding="utf-8"))
        frequencies = [float(item[1]) for item in record.get("samples") or []]
        median, mad = median_mad(frequencies)
        records.append(
            {
                **sample,
                "sample_path": str(path),
                "sample_count": len(frequencies),
                "raw_frequency_hz": frequencies,
                "median_frequency_hz": median,
                "mad_frequency_hz": mad,
                "coil_temperature_c": _temperature(record, "coil"),
                "mcu_temperature_c": _temperature(record, "mcu"),
                "captured_at_utc": record.get("captured_at_utc"),
                "errors": int(record.get("errors") or 0),
                "overflows": int(record.get("overflows") or 0),
                "complete": bool(record.get("complete")),
            }
        )
    return records


def aggregate_descending_levels(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[float, list[dict[str, Any]]] = {}
    for record in records:
        if not str(record["pass"]).startswith("descending_"):
            continue
        grouped.setdefault(float(record["nozzle_gap"]), []).append(record)
    points: list[dict[str, Any]] = []
    for gap, group in grouped.items():
        frequencies = [
            frequency
            for record in group
            for frequency in record["raw_frequency_hz"]
        ]
        median, mad = median_mad(frequencies)
        points.append(
            {
                "nozzle_gap": gap,
                "coil_gap": float(group[0]["coil_gap"]),
                "median_frequency_hz": median,
                "mad_frequency_hz": mad,
                "sample_count": len(frequencies),
                "pass_medians_hz": [
                    float(record["median_frequency_hz"]) for record in group
                ],
            }
        )
    return sorted(points, key=lambda point: float(point["nozzle_gap"]))


def _linear_frequency_slope(points: list[dict[str, Any]]) -> float | None:
    if len(points) < 2:
        return None
    xs = [float(point["nozzle_gap"]) for point in points]
    ys = [float(point["median_frequency_hz"]) for point in points]
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    denom = sum((value - mean_x) ** 2 for value in xs)
    if denom <= 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom


def analyze_records(
    records: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    hard_failures: list[str] = []
    incomplete = [
        record
        for record in records
        if not record["complete"]
        or record["sample_count"] < int(SAMPLE_RATE_HZ * DURATION_MS / 1000 * 0.8)
        or record["errors"]
        or record["overflows"]
    ]
    if incomplete:
        hard_failures.append(
            f"{len(incomplete)} sample windows are incomplete or contain sensor errors"
        )
    points = aggregate_descending_levels(records)
    accepted_points, monotonic_failures = validate_monotonic_points(points)
    hard_failures.extend(monotonic_failures)
    if len(accepted_points) < MIN_USABLE_LEVELS:
        hard_failures.append(
            f"only {len(accepted_points)} usable levels; require {MIN_USABLE_LEVELS}"
        )
    usable_span = (
        float(accepted_points[-1]["nozzle_gap"])
        - float(accepted_points[0]["nozzle_gap"])
        if len(accepted_points) >= 2
        else 0.0
    )
    if usable_span < MIN_USABLE_SPAN_MM:
        hard_failures.append(
            f"usable span {usable_span:.3f}mm is below {MIN_USABLE_SPAN_MM:.3f}mm"
        )

    references = [record for record in records if record.get("reference")]
    reference_medians = [
        float(record["median_frequency_hz"])
        for record in references
        if record["median_frequency_hz"] is not None
    ]
    reference_mads = [
        float(record["mad_frequency_hz"])
        for record in references
        if record["mad_frequency_hz"] is not None
    ]
    reference_drift_hz = (
        max(reference_medians) - min(reference_medians)
        if len(reference_medians) >= 2
        else math.inf
    )
    slope = _linear_frequency_slope(points)
    reference_drift_mm = (
        abs(reference_drift_hz / slope)
        if slope not in (None, 0) and math.isfinite(reference_drift_hz)
        else math.inf
    )
    reference_noise_limit_hz = 2.5 * math.sqrt(
        sum(value * value for value in reference_mads)
    )
    drift_ok = (
        reference_drift_mm <= MAX_REFERENCE_EQUIVALENT_DRIFT_MM
        and reference_drift_hz <= max(reference_noise_limit_hz, 1.0)
    )
    if not drift_ok:
        hard_failures.append(
            "reference-height drift rejected: "
            f"{reference_drift_hz:.3f}Hz, equivalent {reference_drift_mm:.4f}mm"
        )

    candidate = None
    if not hard_failures:
        lower = float(accepted_points[0]["nozzle_gap"])
        upper = float(accepted_points[-1]["nozzle_gap"])
        descend_z = round(lower + min(0.1, (upper - lower) / 2.0), 3)
        if not lower < descend_z < upper:
            hard_failures.append(
                "could not choose descend_z strictly inside measured usable range"
            )
        else:
            calibrate = ",".join(
                f"{float(point['nozzle_gap']):.6f}:"
                f"{float(point['median_frequency_hz']):.3f}"
                for point in accepted_points
            )
            candidate = {
                "active": False,
                "section": "probe_eddy_current btt_eddy",
                "calibrate": calibrate,
                "descend_z": descend_z,
                "usable_range_mm": [lower, upper],
            }

    accepted = not hard_failures and candidate is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement": "cold_contact_free_eddy_relative_calibration",
        "accepted": accepted,
        "ok": accepted,
        "relative_to": "vision-observed bed reference plane",
        "bed_center_warp_is_uncertainty": True,
        "record_count": len(records),
        "frequency_points": points,
        "accepted_frequency_points": accepted_points,
        "usable_level_count": len(accepted_points),
        "usable_span_mm": round(usable_span, 6),
        "reference_samples": references,
        "reference_drift_hz": reference_drift_hz,
        "reference_drift_equivalent_mm": reference_drift_mm,
        "reference_drift_accepted": drift_ok,
        "temperature_range_c": {
            "coil": _range(
                [
                    record["coil_temperature_c"]
                    for record in records
                    if record["coil_temperature_c"] is not None
                ]
            ),
            "mcu": _range(
                [
                    record["mcu_temperature_c"]
                    for record in records
                    if record["mcu_temperature_c"] is not None
                ]
            ),
        },
        "candidate": candidate,
        "hard_failures": hard_failures,
    }


def _range(values: list[float]) -> list[float] | None:
    return [min(values), max(values)] if values else None


def write_raw_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "seq",
        "sample",
        "pass",
        "reference",
        "approach",
        "commanded_z",
        "nozzle_gap",
        "coil_gap",
        "median_frequency_hz",
        "mad_frequency_hz",
        "sample_count",
        "coil_temperature_c",
        "mcu_temperature_c",
        "captured_at_utc",
        "errors",
        "overflows",
        "complete",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in fields})


def _plot(
    path: Path,
    *,
    series: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    title: str,
    x_label: str,
    y_label: str,
) -> None:
    import cv2
    import numpy as np

    width, height = 1200, 760
    left, right, top, bottom = 110, 40, 80, 100
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    values = [
        (
            float(point[x_key]),
            float(point[y_key]),
            str(point.get("label") or ""),
            tuple(point.get("color") or (40, 90, 210)),
        )
        for point in series
        if point.get(x_key) is not None and point.get(y_key) is not None
    ]
    if not values:
        cv2.putText(
            image,
            "No data",
            (left, top + 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.imwrite(str(path), image)
        return
    xs = [value[0] for value in values]
    ys = [value[1] for value in values]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xpad = max((xmax - xmin) * 0.05, 0.05)
    ypad = max((ymax - ymin) * 0.08, 1.0)
    xmin, xmax = xmin - xpad, xmax + xpad
    ymin, ymax = ymin - ypad, ymax + ypad

    def pixel(x: float, y: float) -> tuple[int, int]:
        px = left + (x - xmin) / (xmax - xmin) * (width - left - right)
        py = top + (ymax - y) / (ymax - ymin) * (height - top - bottom)
        return int(round(px)), int(round(py))

    cv2.rectangle(
        image,
        (left, top),
        (width - right, height - bottom),
        (70, 70, 70),
        2,
    )
    for index in range(6):
        x = xmin + (xmax - xmin) * index / 5
        y = ymin + (ymax - ymin) * index / 5
        px, _ = pixel(x, ymin)
        _, py = pixel(xmin, y)
        cv2.line(image, (px, top), (px, height - bottom), (225, 225, 225), 1)
        cv2.line(image, (left, py), (width - right, py), (225, 225, 225), 1)
        cv2.putText(
            image,
            f"{x:.3g}",
            (px - 22, height - bottom + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (50, 50, 50),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"{y:.7g}",
            (8, py + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (50, 50, 50),
            1,
            cv2.LINE_AA,
        )
    for first, second in zip(values, values[1:]):
        cv2.line(
            image,
            pixel(first[0], first[1]),
            pixel(second[0], second[1]),
            second[3],
            2,
            cv2.LINE_AA,
        )
    for x, y, _label, color in values:
        cv2.circle(image, pixel(x, y), 5, color, -1, cv2.LINE_AA)
    cv2.putText(
        image,
        title,
        (left, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        x_label,
        (width // 2 - 100, height - 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        y_label,
        (left, 68),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 94])


def write_plots(
    sweep_dir: Path, records: list[dict[str, Any]], analysis: dict[str, Any]
) -> dict[str, str]:
    plots_dir = sweep_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    points = analysis["frequency_points"]
    nozzle_path = plots_dir / "frequency_vs_nozzle_gap.jpg"
    coil_path = plots_dir / "frequency_vs_coil_gap.jpg"
    direction_path = plots_dir / "repeatability_and_direction.jpg"
    temperature_path = plots_dir / "temperature.jpg"
    reference_drift_path = plots_dir / "reference_frequency_drift.jpg"
    _plot(
        nozzle_path,
        series=points,
        x_key="nozzle_gap",
        y_key="median_frequency_hz",
        title="Cold Eddy frequency vs vision-referenced nozzle gap",
        x_label="nozzle gap (mm)",
        y_label="frequency (Hz)",
    )
    _plot(
        coil_path,
        series=points,
        x_key="coil_gap",
        y_key="median_frequency_hz",
        title="Cold Eddy frequency vs vision-referenced coil-plane gap",
        x_label="coil-plane gap (mm)",
        y_label="frequency (Hz)",
    )
    direction_series = []
    for record in records:
        if record.get("reference"):
            continue
        color = (
            (40, 90, 210)
            if str(record["pass"]).startswith("descending")
            else (40, 160, 40)
        )
        direction_series.append(
            {
                "nozzle_gap": record["nozzle_gap"],
                "median_frequency_hz": record["median_frequency_hz"],
                "color": color,
            }
        )
    direction_series.sort(key=lambda value: float(value["nozzle_gap"]))
    _plot(
        direction_path,
        series=direction_series,
        x_key="nozzle_gap",
        y_key="median_frequency_hz",
        title="Descending repeatability and sparse ascending validation",
        x_label="nozzle gap (mm)",
        y_label="frequency (Hz)",
    )
    drift_series = [
        {
            "seq": record["seq"],
            "coil_temperature_c": record["coil_temperature_c"],
            "color": (180, 90, 20),
        }
        for record in records
        if record["coil_temperature_c"] is not None
    ]
    _plot(
        temperature_path,
        series=drift_series,
        x_key="seq",
        y_key="coil_temperature_c",
        title="Eddy coil temperature through sweep",
        x_label="sample sequence",
        y_label="coil temperature (C)",
    )
    reference_drift_series = [
        {
            "seq": record["seq"],
            "median_frequency_hz": record["median_frequency_hz"],
            "color": (150, 60, 170),
        }
        for record in records
        if record.get("reference")
        and record.get("median_frequency_hz") is not None
    ]
    _plot(
        reference_drift_path,
        series=reference_drift_series,
        x_key="seq",
        y_key="median_frequency_hz",
        title="Reference-height frequency drift (before, midway, after)",
        x_label="sample sequence",
        y_label="reference frequency (Hz)",
    )
    return {
        "frequency_vs_nozzle_gap": str(nozzle_path),
        "frequency_vs_coil_gap": str(coil_path),
        "repeatability_and_direction": str(direction_path),
        "temperature": str(temperature_path),
        "reference_frequency_drift": str(reference_drift_path),
    }


def write_analysis_artifacts(
    sweep_dir: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    records = load_sample_records(sweep_dir, manifest)
    analysis = analyze_records(records, manifest)
    csv_path = sweep_dir / "samples.csv"
    records_path = sweep_dir / "samples.json"
    analysis_path = sweep_dir / "analysis.json"
    candidate_path = sweep_dir / "klipper_candidate.txt"
    write_raw_csv(csv_path, records)
    records_path.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plots = write_plots(sweep_dir, records, analysis)
    candidate = analysis.get("candidate")
    candidate_text = (
        "# REPORT ONLY - inactive; do not paste without review\n"
        "[probe_eddy_current btt_eddy]\n"
        f"calibrate: {candidate['calibrate']}\n"
        f"descend_z: {candidate['descend_z']:.3f}\n"
        if candidate
        else "# No candidate produced because quality gates failed.\n"
    )
    candidate_path.write_text(candidate_text, encoding="utf-8")
    provenance_files = [
        sweep_dir / "manifest.json",
        sweep_dir / "sweep.gcode",
        *sorted((sweep_dir / "raw").glob("*.json")),
    ]
    analysis["artifacts"] = {
        "samples_csv": str(csv_path),
        "samples_json": str(records_path),
        "candidate": str(candidate_path),
        "plots": plots,
    }
    analysis["provenance"] = {
        str(path.relative_to(sweep_dir)): sha256_file(path)
        for path in provenance_files
    }
    analysis_path.write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    analysis["artifacts"]["analysis"] = str(analysis_path)
    return analysis
