#!/usr/bin/env python3
"""Replay the live ArUco-located tool X/Z sweep with inspectable overlays.

The raw capture is intentionally kept outside git because it is a 98-frame,
full-resolution printer capture. Populate it once with:

    DATASET=resources/vision_datasets/20260809_aruco_tool_xz_sweep_after_xy
    mkdir -p "$DATASET/frames"
    scp pi@menderpi.local:/home/pi/printer_data/vision/calibration/jobs/\\
        20260809T131349.745445Z-aruco_tool_xz_sweep_after_xy/manifest.json \\
        "$DATASET/manifest.json"
    scp 'pi@menderpi.local:/home/pi/printer_data/vision/calibration/jobs/\\
        20260809T131349.745445Z-aruco_tool_xz_sweep_after_xy/frames/*.jpg' \\
        "$DATASET/frames/"

Run the complete replay with:

    pytest -q -s tests/vision/test_vision_aruco_tool_xz_sweep_replay.py

Run only the quick single-image inspection with:

    pytest -q -s tests/vision/test_vision_aruco_tool_xz_sweep_replay.py::test_single_t0_z1_frame_overlay
"""

from __future__ import annotations

import copy
import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest


_logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
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
    / "20260809_aruco_tool_xz_sweep_after_xy"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_aruco_tool_xz_sweep_replay"


def _analyzer_module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_aruco_tool_xz_sweep_replay", FILES / "vision_tool_xz_sweep.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_root(label: str) -> Path:
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    )
    root = OUTPUT_ROOT / "runs" / run_id / label
    root.mkdir(parents=True, exist_ok=False)
    return root


def _dataset() -> tuple[dict, list[Path]]:
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(f"local captured dataset is absent: {DATASET_ROOT}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    paths = [DATASET_ROOT / "frames" / f"{frame['frame']}.jpg" for frame in frames]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        pytest.skip(f"{len(missing)} raw frames are absent, e.g. {missing[0]}")
    return manifest, paths


def _write_result(root: Path, result: dict) -> None:
    (root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_nozzle_xy_priors() -> dict[str, dict]:
    """Fit image-space nozzle position as a function of commanded X.

    The observations are from the preceding XY calibration, at Z=0.5 mm.
    They are an external prior for this replay and intentionally do not use
    any XZ-sweep nozzle result, so the diagnostic cannot become circular.
    """

    priors: dict[str, dict] = {}
    for tool in ("T0", "T1"):
        fact_path = DATASET_ROOT / "source_inputs" / f"{tool.lower()}_xy_fact_set.json"
        if not fact_path.is_file():
            pytest.skip(f"XY prior fact set is absent: {fact_path}")
        observations = json.loads(fact_path.read_text(encoding="utf-8"))["provenance"][
            "observations"
        ]["records"]
        x_mm = np.asarray([record["x_mm"] for record in observations], dtype=np.float64)
        centers = np.asarray(
            [record["center_px"] for record in observations], dtype=np.float64
        )
        design = np.column_stack((np.ones_like(x_mm), x_mm))
        coefficients, _, _, _ = np.linalg.lstsq(design, centers, rcond=None)
        residuals = design @ coefficients - centers
        fit_rms = np.sqrt(np.mean(residuals**2, axis=0))
        priors[tool] = {
            "model": "linear_commanded_x_to_image_uv_v1",
            "coefficients_px": coefficients.tolist(),
        }
        _logger.info(
            "Nozzle prior %s x->pixel coefficients x=(%.3f, %.3f) "
            "y=(%.3f, %.3f) fit_rms=(%.3f, %.3f)px",
            tool,
            coefficients[0, 0],
            coefficients[1, 0],
            coefficients[0, 1],
            coefficients[1, 1],
            fit_rms[0],
            fit_rms[1],
        )
    return priors


def _replay_references(manifest: dict, priors: dict[str, dict]) -> dict:
    references = copy.deepcopy(manifest["tool_xz_reference"])
    for tool in ("T0", "T1"):
        references[tool.lower()]["nozzle_image_prior"] = priors[tool]
    return references


def _draw_nozzle_prior_roi(
    overlay_path: Path,
    frame: dict,
    record: dict,
    prior: dict[str, np.ndarray],
) -> bool:
    """Draw and log the diagnostic XY-prior ROI without changing detection."""

    overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
    assert overlay is not None
    height, width = overlay.shape[:2]
    coefficients = prior["coefficients"]
    predicted_center = (
        np.array([1.0, float(frame["x_mm"])], dtype=np.float64) @ coefficients
    )
    x0 = max(0, int(round(predicted_center[0] - NOZZLE_PRIOR_ROI_HALF_WIDTH_PX)))
    y0 = max(0, int(round(predicted_center[1] - NOZZLE_PRIOR_ROI_HALF_HEIGHT_PX)))
    x1 = min(
        width - 1, int(round(predicted_center[0] + NOZZLE_PRIOR_ROI_HALF_WIDTH_PX))
    )
    y1 = min(
        height - 1, int(round(predicted_center[1] + NOZZLE_PRIOR_ROI_HALF_HEIGHT_PX))
    )

    # Cyan distinguishes this prior ROI from the yellow fiducials, green
    # selected nozzle, and magenta ArUco/patch geometry already on the overlay.
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (255, 255, 0), 3)
    cv2.drawMarker(
        overlay,
        tuple(np.rint(predicted_center).astype(int)),
        (255, 255, 0),
        cv2.MARKER_CROSS,
        24,
        2,
    )
    label = (
        f"prior nozzle ROI x={x0}:{x1} y={y0}:{y1} "
        f"center=({predicted_center[0]:.1f},{predicted_center[1]:.1f})"
    )
    cv2.putText(
        overlay,
        label,
        (24, min(height - 20, 260)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (0, 0, 0),
        5,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        label,
        (24, min(height - 20, 260)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )
    assert cv2.imwrite(str(overlay_path), overlay)

    detected = record.get("nozzle_uv_px")
    inside = False
    if detected is not None:
        detected_xy = np.asarray(detected, dtype=np.float64)
        inside = x0 <= detected_xy[0] <= x1 and y0 <= detected_xy[1] <= y1
        offset = detected_xy - predicted_center
        detected_text = f"({detected_xy[0]:.1f},{detected_xy[1]:.1f})"
        offset_text = f"({offset[0]:+.1f},{offset[1]:+.1f})"
    else:
        detected_text = "none"
        offset_text = "n/a"
    _logger.info(
        "ROI %s tool=%s x=%.3f z=%.3f bounds=[%d,%d..%d,%d] "
        "prior=(%.1f,%.1f) selected=%s offset=%s inside=%s accepted_for_fit=%s",
        overlay_path.resolve(),
        frame["tool"],
        float(frame["x_mm"]),
        float(frame["z_mm"]),
        x0,
        y0,
        x1,
        y1,
        predicted_center[0],
        predicted_center[1],
        detected_text,
        offset_text,
        "yes" if inside else "no",
        "yes" if record["accepted_for_u_x_fit"] else "no",
    )
    return inside


def _draw_prior_rois(
    frames: list[dict], result: dict, priors: dict[str, dict[str, np.ndarray]]
) -> None:
    overlays = {
        key: Path(artifact["path"])
        for key, artifact in result["artifacts"].items()
        if key.startswith("tool_xz_sweep_overlay_")
    }
    for frame in frames:
        seq = int(frame["seq"])
        _draw_nozzle_prior_roi(
            overlays[f"tool_xz_sweep_overlay_{seq:02d}"],
            frame,
            result["records"][seq],
            priors[frame["tool"]],
        )


def _log_and_check_overlays(frames: list[dict], paths: list[Path], result: dict):
    overlays = {
        key: Path(artifact["path"])
        for key, artifact in result["artifacts"].items()
        if key.startswith("tool_xz_sweep_overlay_")
    }
    assert len(overlays) == len(frames)
    for frame, source_path in zip(frames, paths):
        key = f"tool_xz_sweep_overlay_{int(frame['seq']):02d}"
        overlay_path = overlays[key]
        source = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
        assert source is not None
        assert overlay is not None
        assert overlay.shape == source.shape
        record = result["records"][int(frame["seq"])]
        localization = record.get("localization") or {}
        if record["nozzle_detected"]:
            assert localization.get("localization_method") == "bright_circle_roi_v1"
            assert localization.get("roi_px") is not None
            roi_x0, roi_y0, roi_x1, roi_y1 = localization["roi_px"]
            u, v = record["nozzle_uv_px"]
            assert roi_x0 <= u <= roi_x1
            assert roi_y0 <= v <= roi_y1
        _logger.info(
            "Overlay %s tool=%s x=%.3f z=%.3f fiducials=%s nozzle=%s "
            "method=%s score=%s row_residual=%s",
            overlay_path.resolve(),
            frame["tool"],
            float(frame["x_mm"]),
            float(frame["z_mm"]),
            "yes" if record["fiducials_detected"] else "no",
            "yes" if record["nozzle_detected"] else "no",
            localization.get("localization_method", "none"),
            localization.get("bright_circle_score", "n/a"),
            localization.get("row_residual_px", "n/a"),
        )


def test_replay_aruco_tool_xz_sweep_writes_full_overlays(monkeypatch):
    """Replay every raw frame and write one full-resolution diagnostic overlay."""

    manifest, paths = _dataset()
    analyzer = _analyzer_module()
    monkeypatch.setattr(analyzer, "GENERATE_OVERLAYS", True)
    root = _run_root("full_replay")
    priors = _load_nozzle_xy_priors()
    result = analyzer.analyze(
        paths,
        root / "artifacts",
        frames=manifest["frames"],
        references=_replay_references(manifest, priors),
        acquisition_calibration=manifest["acquisition_calibration"],
    )
    _write_result(root, result)
    _log_and_check_overlays(manifest["frames"], paths, result)

    # The replay is intentionally acquisition-locked: the fitting experiment
    # must consume the same 98 decoded frames and commanded positions.
    assert len(manifest["frames"]) == 98
    assert len(result["records"]) == len(manifest["frames"])
    for frame, record in zip(manifest["frames"], result["records"]):
        assert record["seq"] == frame["seq"]
        assert record["tool"] == frame["tool"]
        assert record["commanded_x_mm"] == pytest.approx(frame["x_mm"])
        assert record["commanded_y_mm"] == pytest.approx(frame["y_mm"])
        assert record["commanded_z_mm"] == pytest.approx(frame["z_mm"])

    comparison = result["fit_strategy_comparison"]
    assert {
        "theil_sen_plus_soft_l1",
        "ols_plus_linear",
        "huber_irls_plus_huber",
        "soft_l1_plus_soft_l1",
    } == set(comparison["strategies"])
    comparison_json = Path(result["artifacts"]["fit_strategy_comparison"]["path"])
    comparison_plot = Path(result["artifacts"]["fit_strategy_comparison_plot"]["path"])
    assert comparison_json.is_file()
    assert comparison_plot.is_file()
    assert all(
        "row_fits" in strategy and "shared_z_curve_fit" in strategy
        for strategy in comparison["strategies"].values()
    )

    shared_fit = result["shared_z_curve_fit"]
    assert shared_fit["available"] is False
    assert shared_fit["boundary_saturated"] is True
    assert abs(shared_fit["t1_z_delta_mm"]) == pytest.approx(1.5)
    assert "operational T1 delta bound" in shared_fit["reason"]
    physical = shared_fit["physical_z_diagnostics"]
    assert physical["acquisition_t0_z_endstop_mm"] == pytest.approx(293.626)
    assert physical["acquisition_t1_z_endstop_mm"] == pytest.approx(292.402)
    assert physical["manual_reference_delta_mm"] == pytest.approx(0.6)
    assert physical["difference_from_manual_reference_mm"] == pytest.approx(0.9)
    assert all(
        "u_x_fit" in record
        for record in result["records"]
        if record["accepted_for_u_x_fit"]
    )

    fiducial_count = sum(record["fiducials_detected"] for record in result["records"])
    nozzle_count = sum(record["nozzle_detected"] for record in result["records"])
    fit_count = sum(record["accepted_for_u_x_fit"] for record in result["records"])
    _logger.info(
        "Replay summary %s frames=%d fiducials=%d nozzle=%d fit=%d warnings=%s",
        root.resolve(),
        len(result["records"]),
        fiducial_count,
        nozzle_count,
        fit_count,
        result["warnings"],
    )
    false_points = {
        7: np.asarray([1060.0, 515.0]),
        71: np.asarray([1081.0, 524.0]),
    }
    for seq, false_point in false_points.items():
        selected = np.asarray(result["records"][seq]["nozzle_uv_px"])
        assert np.linalg.norm(selected - false_point) > 20.0
    assert result["accepted"] is True


def test_single_t0_z1_frame_overlay():
    """Quickly inspect only the first T0 frame at commanded Z=1.0 mm."""

    manifest, paths = _dataset()
    frame_index = next(
        index
        for index, frame in enumerate(manifest["frames"])
        if frame["tool"] == "T0" and abs(float(frame["z_mm"]) - 1.0) < 1.0e-9
    )
    frame = manifest["frames"][frame_index]
    source_path = paths[frame_index]
    analyzer = _analyzer_module()
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    assert image is not None

    fiducials = analyzer.detect_four_fiducials(image)
    prior = _load_nozzle_xy_priors()[frame["tool"]]
    prior_center = np.asarray([1.0, float(frame["x_mm"])]) @ np.asarray(
        prior["coefficients_px"], dtype=np.float64
    )
    localized = analyzer.localize_bright_nozzle_tip_grid(
        [source_path],
        frames=[frame],
        roi_centers_px=[prior_center],
    )
    registration = localized["registrations"][0]
    record = analyzer._base_record(frame)
    centers = np.asarray(fiducials["centers_px"], dtype=np.float64)
    record.update(
        {
            "fiducials_detected": True,
            "fiducial_centers_uv_px": centers.tolist(),
            "fiducial_radii_px": [float(value) for value in fiducials["radii_px"]],
            "fiducial_centroid_uv_px": np.mean(centers, axis=0).tolist(),
            "fiducial_fit": analyzer._finite(
                {
                    "roi_px": fiducials.get("roi_px"),
                    "patch_corners_px": fiducials.get("patch_corners_px"),
                    "right_edge_angle_deg": fiducials.get("right_edge_angle_deg"),
                    "down_edge_angle_deg": fiducials.get("down_edge_angle_deg"),
                    "geometry": fiducials.get("geometry"),
                    "locator": fiducials.get("locator"),
                }
            ),
            "nozzle_detected": True,
            "nozzle_uv_px": np.asarray(registration["center_px"]).tolist(),
            "localization": analyzer._finite(registration),
        }
    )
    record["accepted_for_u_x_fit"] = not analyzer._registration_fit_reasons(
        registration
    )
    overlay_path = _run_root("single_frame_overlays") / f"{frame['frame']}.png"
    analyzer._write_overlay(image, frame, record, overlay_path)
    _logger.info(
        "Overlay %s tool=%s x=%.3f z=%.3f fiducial_angle=%.3f nozzle=(%.2f,%.2f)",
        overlay_path.resolve(),
        frame["tool"],
        float(frame["x_mm"]),
        float(frame["z_mm"]),
        float(fiducials["right_edge_angle_deg"]),
        float(record["nozzle_uv_px"][0]),
        float(record["nozzle_uv_px"][1]),
    )
    assert overlay_path.is_file()
    overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
    assert overlay is not None
    assert overlay.shape == image.shape
    assert registration["localization_method"] == "bright_circle_roi_v1"
    assert (
        registration["roi_px"][0]
        <= registration["center_px"][0]
        <= registration["roi_px"][2]
    )
    assert (
        registration["roi_px"][1]
        <= registration["center_px"][1]
        <= registration["roi_px"][3]
    )
