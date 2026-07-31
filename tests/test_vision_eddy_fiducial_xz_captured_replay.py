#!/usr/bin/env python3
"""Captured-image replay test for the Eddy fiducial XZ grid analyzer.

Dataset: raw JPEGs captured on 2026-07-31 with job
    20260731T120351.998734Z-eddy_fiducial_xz_once

To populate the dataset from the printer (one-time):

    mkdir -p resources/vision_datasets/20260731_eddy_fiducial_xz_once/frames
    scp pi@menderpi.local:~/printer_data/vision/calibration/jobs/\\
        20260731T120351.998734Z-eddy_fiducial_xz_once/manifest.json \\
        resources/vision_datasets/20260731_eddy_fiducial_xz_once/
    scp 'pi@menderpi.local:~/printer_data/vision/calibration/jobs/\\
        20260731T120351.998734Z-eddy_fiducial_xz_once/frames/*.jpg' \\
        resources/vision_datasets/20260731_eddy_fiducial_xz_once/frames/
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
DATASET_ROOT = (
    REPO_ROOT
    / "resources"
    / "vision_datasets"
    / "20260731_eddy_fiducial_xz_once"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_eddy_fiducial_xz_replay"
JOB_TYPES_JSON = FILES / "vision_job_types.json"
JOB_TYPE_KEY = "idex_eddy_fiducial_xz_grid"


def _load_analyzer():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_eddy_fiducial_xz",
        FILES / "vision_eddy_fiducial_xz.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _current_localizer() -> dict:
    """Load the active localizer from vision_job_types.json."""
    data = json.loads(JOB_TYPES_JSON.read_text(encoding="utf-8"))
    return data["job_types"][JOB_TYPE_KEY]["localizer"]


def _run_id() -> str:
    return (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + __import__("uuid").uuid4().hex[:8]
    )


def test_replay_captured_eddy_fiducial_xz_and_render_overlays():
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(
            f"local captured dataset is absent: {DATASET_ROOT}  "
            "(see docstring for download instructions)"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    frame_paths = [
        DATASET_ROOT / "frames" / f"{frame['frame']}.jpg" for frame in frames
    ]
    missing_frames = [p for p in frame_paths if not p.is_file()]
    if missing_frames:
        pytest.skip(
            f"{len(missing_frames)} raw frames are absent, "
            f"e.g. {missing_frames[0].name}"
        )

    analyzer = _load_analyzer()
    localizer = _current_localizer()

    run_id = _run_id()
    run_root = OUTPUT_ROOT / "runs" / run_id
    artifact_dir = run_root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    result = analyzer.analyze(
        frame_paths,
        artifact_dir,
        frames=frames,
        localizer=localizer,
    )

    # Persist result JSON for post-hoc inspection.
    result_json_path = run_root / "result.json"
    result_json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Copy per-frame overlays to a named subdirectory for easy browsing.
    overlays_dir = run_root / "frame_overlays"
    overlays_dir.mkdir(parents=True)
    for key, artifact in result["artifacts"].items():
        if key.startswith("eddy_circle_overlay_"):
            src = Path(artifact["path"])
            seq = key.split("_")[-1]
            dst = overlays_dir / f"{seq}_{src.name}"
            dst.write_bytes(src.read_bytes())

    # Write commanded-X vs image-X plot (one line per Z height).
    plot_path = run_root / "commanded_x_vs_image_x.png"
    _write_commanded_x_vs_image_x_plot(result, plot_path)

    # --- log intermediates and generated files ---
    print(f"\nEDDY FIDUCIAL XZ REPLAY OUTPUT:\n{run_root.resolve()}")
    print("\nKEY FILES:")
    print(f"  BACKGROUND:        {result['artifacts']['eddy_background']['path']}")
    print(f"  DIFF CONTACT:      {result['artifacts'].get('eddy_diff_grid', {}).get('path', '—')}")
    print(f"  OVERLAY CONTACT:   {result['artifacts']['eddy_fiducial_xz_grid']['path']}")
    print(f"  POSITION PLOT:     {plot_path}")
    print(f"  RESULT JSON:       {result_json_path}")
    print(f"\nPER-FRAME OVERLAYS ({overlays_dir.name}/):")
    for seq in range(len(frames)):
        key = f"eddy_circle_overlay_{seq:02d}"
        if key in result["artifacts"]:
            print(f"  frame {seq:02d}: {result['artifacts'][key]['path']}")

    # --- structural assertions ---
    records = result["records"]
    assert len(records) == len(frames), "one record per frame"

    detected_count = sum(1 for r in records if r["detected"])
    missed = [r["seq"] for r in records if not r["detected"]]
    print(
        f"\nDETECTED: {detected_count}/{len(records)}"
        + (f"  MISSED seqs: {missed}" if missed else "  (all accepted)")
    )
    for r in records:
        sift = r.get("sift_roi_px")
        cx = f"({r['image_x_px']:.0f},{r['image_y_px']:.0f})" if r["detected"] else "MISSED"
        roi = f"  roi=[{sift[0]},{sift[1]},{sift[2]},{sift[3]}]" if sift else "  roi=none"
        print(
            f"  seq={r['seq']:02d}  X={r['commanded_x_mm']:.3f}  Z={r['commanded_z_mm']:.3f}"
            f"  center={cx}{roi}"
        )

    assert result["image_dimensions_px"] is not None
    assert len(result["raw_positions"]) == len(frames)

    for record in records:
        assert "seq" in record
        assert "commanded_x_mm" in record
        assert "commanded_z_mm" in record
        if record["detected"]:
            assert record["image_x_px"] is not None
            assert record["image_y_px"] is not None
            assert record["radius_px"] is not None

    assert "eddy_background" in result["artifacts"]
    assert Path(result["artifacts"]["eddy_background"]["path"]).is_file()
    assert "eddy_diff_grid" in result["artifacts"]
    assert Path(result["artifacts"]["eddy_diff_grid"]["path"]).is_file()

    assert "eddy_fiducial_xz_grid" in result["artifacts"]
    contact_path = Path(result["artifacts"]["eddy_fiducial_xz_grid"]["path"])
    assert contact_path.is_file(), f"contact sheet missing: {contact_path}"

    overlay_keys = [k for k in result["artifacts"] if k.startswith("eddy_circle_overlay_")]
    assert len(overlay_keys) == len(frames), (
        f"expected {len(frames)} overlays, got {len(overlay_keys)}"
    )
    for key in overlay_keys:
        assert Path(result["artifacts"][key]["path"]).is_file()

    assert plot_path.is_file()

    # Write inspection summary
    summary_lines = [
        "# Eddy fiducial XZ replay — inspection summary",
        "",
        f"Run: `{run_id}`",
        f"Detected: **{detected_count}/{len(records)}** frames",
        "",
        "## Files",
        "",
        f"- [Commanded X vs image X plot](commanded_x_vs_image_x.png)",
        f"- [Circle overlay contact sheet](artifacts/eddy_fiducial_xz_grid.jpg)",
        f"- [Diff contact sheet](artifacts/eddy_diff_grid.jpg)",
        f"- [Background](artifacts/eddy_background.png)",
        f"- [Result JSON](result.json)",
        f"- Per-frame overlays: `frame_overlays/` ({len(overlay_keys)} files)",
        "",
        "## Per-frame detections",
        "",
        "| seq | X mm | Z mm | detected | image X px | image Y px | SIFT ROI |",
        "|-----|------|------|----------|------------|------------|----------|",
    ]
    for r in records:
        cx = f"{r['image_x_px']:.0f}" if r["detected"] else "—"
        cy = f"{r['image_y_px']:.0f}" if r["detected"] else "—"
        sift = r.get("sift_roi_px")
        roi = f"[{sift[0]},{sift[1]},{sift[2]},{sift[3]}]" if sift else "none"
        status = "✓" if r["detected"] else "✗"
        summary_lines.append(
            f"| {r['seq']:02d} | {r['commanded_x_mm']:.3f} | {r['commanded_z_mm']:.3f}"
            f" | {status} | {cx} | {cy} | {roi} |"
        )
    (run_root / "inspection_summary.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    print(f"\nRUN DIRECTORY:\n{run_root.resolve()}")


# ---------------------------------------------------------------------------
# Visualisation helpers
# ---------------------------------------------------------------------------

def _distinct_bgr_colors(count: int) -> list[tuple[int, int, int]]:
    hues = np.linspace(0, 179, count, endpoint=False, dtype=np.uint8)
    hsv = np.zeros((1, count, 3), dtype=np.uint8)
    hsv[0, :, 0] = hues
    hsv[0, :, 1] = 190
    hsv[0, :, 2] = 200
    return [
        tuple(int(c) for c in col)
        for col in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0]
    ]


def _plot_point(
    x_val: float, x_min: float, x_max: float,
    y_val: float, y_min: float, y_max: float,
    rect: tuple[int, int, int, int],
) -> tuple[int, int]:
    left, top, right, bottom = rect
    px = left + int(round((x_val - x_min) / max(x_max - x_min, 1e-9) * (right - left)))
    py = bottom - int(round((y_val - y_min) / max(y_max - y_min, 1e-9) * (bottom - top)))
    return max(left, min(right, px)), max(top, min(bottom, py))


def _write_commanded_x_vs_image_x_plot(result: dict, path: Path) -> None:
    """Plot of commanded X (mm) vs detected image X (px), one line per Z height."""
    records = result["records"]
    detected = [r for r in records if r["detected"]]
    if not detected:
        return

    z_values = sorted({r["commanded_z_mm"] for r in records})
    x_mm_values = sorted({r["commanded_x_mm"] for r in records})
    z_colors = _distinct_bgr_colors(len(z_values))

    all_img_x = [r["image_x_px"] for r in detected]
    x_mm_min, x_mm_max = min(x_mm_values), max(x_mm_values)
    img_x_min, img_x_max = min(all_img_x), max(all_img_x)
    x_margin = max(0.3, (x_mm_max - x_mm_min) * 0.08)
    y_margin = max(5.0, (img_x_max - img_x_min) * 0.10)
    x_lim = (x_mm_min - x_margin, x_mm_max + x_margin)
    y_lim = (img_x_min - y_margin, img_x_max + y_margin)

    canvas = np.full((720, 980, 3), 245, dtype=np.uint8)
    cv2.putText(
        canvas,
        "Eddy fiducial: commanded X (mm) vs detected image X (px)",
        (36, 46),
        cv2.FONT_HERSHEY_SIMPLEX, 0.82, (20, 20, 20), 2, cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "one line per commanded Z height   circle=detected   red cross=missed",
        (36, 78),
        cv2.FONT_HERSHEY_SIMPLEX, 0.56, (50, 50, 50), 1, cv2.LINE_AA,
    )

    rect = (90, 110, 920, 580)
    left, top, right, bottom = rect

    # Grid
    for xv in x_mm_values:
        pt_top = _plot_point(xv, *x_lim, y_lim[1], *y_lim, rect)
        pt_bot = _plot_point(xv, *x_lim, y_lim[0], *y_lim, rect)
        cv2.line(canvas, pt_top, pt_bot, (215, 215, 215), 1)
        cv2.putText(canvas, f"{xv:.1f}", (pt_bot[0] - 16, bottom + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (55, 55, 55), 1, cv2.LINE_AA)
    for yv in np.linspace(y_lim[0], y_lim[1], 6):
        pt_l = _plot_point(x_lim[0], *x_lim, float(yv), *y_lim, rect)
        pt_r = _plot_point(x_lim[1], *x_lim, float(yv), *y_lim, rect)
        cv2.line(canvas, pt_l, pt_r, (215, 215, 215), 1)
        cv2.putText(canvas, f"{yv:.0f}", (left - 60, pt_l[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (55, 55, 55), 1, cv2.LINE_AA)
    cv2.rectangle(canvas, (left, top), (right, bottom), (65, 65, 65), 2)

    # Lines + points per Z height
    for z_idx, z_val in enumerate(z_values):
        color = z_colors[z_idx]
        z_records = sorted(
            [r for r in records if abs(r["commanded_z_mm"] - z_val) < 1e-6],
            key=lambda r: r["commanded_x_mm"],
        )
        line_pts = [
            _plot_point(r["commanded_x_mm"], *x_lim, r["image_x_px"], *y_lim, rect)
            for r in z_records if r["detected"]
        ]
        if len(line_pts) >= 2:
            cv2.polylines(
                canvas,
                [np.asarray(line_pts, dtype=np.int32)],
                False, color, 2, cv2.LINE_AA,
            )
        for r in z_records:
            pt = _plot_point(
                r["commanded_x_mm"], *x_lim,
                r["image_x_px"] if r["detected"] else (y_lim[0] + y_lim[1]) / 2,
                *y_lim, rect,
            )
            if r["detected"]:
                cv2.circle(canvas, pt, 7, (20, 20, 20), 2, cv2.LINE_AA)
                cv2.circle(canvas, pt, 5, color, -1, cv2.LINE_AA)
            else:
                cv2.drawMarker(canvas, pt, (0, 0, 200),
                               cv2.MARKER_TILTED_CROSS, 16, 2, cv2.LINE_AA)

    # Axis labels
    cv2.putText(canvas, "commanded X (mm)",
                (left + (right - left) // 2 - 80, bottom + 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.56, (25, 25, 25), 1, cv2.LINE_AA)
    cv2.putText(canvas, "image X (px)",
                (left - 80, top - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (25, 25, 25), 1, cv2.LINE_AA)

    # Legend
    for i, z_val in enumerate(z_values):
        lx = 36 + i * 220
        ly = 630
        cv2.line(canvas, (lx, ly), (lx + 26, ly), z_colors[i], 3, cv2.LINE_AA)
        cv2.putText(canvas, f"Z={z_val:.3f} mm", (lx + 34, ly + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (35, 35, 35), 1, cv2.LINE_AA)

    # Stats
    detected_count = len(detected)
    total = len(records)
    cv2.putText(
        canvas,
        f"detected {detected_count}/{total}   "
        f"image X range: {img_x_min:.0f}..{img_x_max:.0f} px",
        (36, 680),
        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 40, 40), 1, cv2.LINE_AA,
    )

    cv2.imwrite(str(path), canvas)
