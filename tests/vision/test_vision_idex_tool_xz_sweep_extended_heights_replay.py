#!/usr/bin/env python3
"""Replay the extended-height live IDEX tool X/Z sweep with overlays."""

from __future__ import annotations

import importlib.util
import copy
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
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
    / "20260810_idex_tool_xz_sweep_extended_heights"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_idex_tool_xz_sweep_replay"


def _analyzer_module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_idex_tool_xz_sweep_extended_heights_replay",
        FILES / "vision_tool_xz_sweep.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_root() -> Path:
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + uuid4().hex[:8]
    )
    root = OUTPUT_ROOT / "runs" / run_id / "extended_heights_replay"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _dataset() -> tuple[dict, list[Path], list[Path]]:
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(f"local captured dataset is absent: {DATASET_ROOT}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    image_paths = [
        DATASET_ROOT / "frames" / f"{frame['frame']}.jpg" for frame in frames
    ]
    sidecar_paths = [
        DATASET_ROOT / "frames" / f"{frame['frame']}.json" for frame in frames
    ]
    missing = [path for path in [*image_paths, *sidecar_paths] if not path.is_file()]
    if missing:
        pytest.skip(f"captured frame or sidecar is absent, e.g. {missing[0]}")
    return manifest, image_paths, sidecar_paths


def _write_result(root: Path, result: dict) -> None:
    (root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _injected_linear_prior_references(manifest: dict) -> dict:
    """Return replay-only references with a stable X-to-image prior.

    The downloaded live manifest predates XY-prior publication and contains
    ``nozzle_image_prior: null``.  This deliberately supplies the downstream
    XZ analyzer with a fixed commanded-X image line so this replay can distinguish ROI
    seeding problems from bright-circle detection and fitting problems.
    """

    references = copy.deepcopy(manifest["tool_xz_reference"])
    priors = {
        # These are deliberately broad, trajectory-derived test values.  The
        # ROI is large enough to contain the observed Z-dependent vertical
        # motion; only the X-dependent center is constrained tightly.
        "t0": {
            "model": "linear_commanded_x_to_image_uv_v1",
            # Stored as [intercepts [u, v], slopes [u, v]], which is the
            # numpy.lstsq layout consumed by _nozzle_prior_center().
            "coefficients_px": [[-776.0, 510.0], [9.85, 0.0]],
        },
        "t1": {
            "model": "linear_commanded_x_to_image_uv_v1",
            "coefficients_px": [[-766.0, 510.0], [9.80, 0.0]],
        },
    }
    for tool, prior in priors.items():
        references[tool]["nozzle_image_prior"] = prior
        endstop = manifest["acquisition_calibration"]["tool_xy_endstops_mm"][tool]
        references[tool]["nozzle_image_prior_source"] = {
            "acquisition_endstop_xy_mm": [endstop["x"], endstop["y"]],
            "fact_name": f"tool.{tool}.vision_xy_datum",
            "fact_set_hash": f"sha256:replay-{tool}",
        }
    return references


def test_replay_extended_idex_tool_xz_sweep_writes_overlays(monkeypatch):
    manifest, image_paths, sidecar_paths = _dataset()
    assert manifest["job_type"] == "idex_tool_xz_sweep_report"
    assert len(manifest["frames"]) == 96
    assert len(image_paths) == len(sidecar_paths) == len(manifest["frames"])
    assert sorted({float(frame["z_mm"]) for frame in manifest["frames"]}) == [
        0.5,
        1.5,
        2.5,
        3.5,
        4.5,
        5.5,
        6.5,
        7.5,
    ]

    analyzer = _analyzer_module()
    monkeypatch.setattr(analyzer, "GENERATE_OVERLAYS", True)
    root = _run_root()
    result = analyzer.analyze(
        image_paths,
        root / "artifacts",
        frames=manifest["frames"],
        references=_injected_linear_prior_references(manifest),
        acquisition_calibration=manifest["acquisition_calibration"],
    )
    _write_result(root, result)

    overlays = {
        key: Path(artifact["path"])
        for key, artifact in result["artifacts"].items()
        if key.startswith("tool_xz_sweep_overlay_")
    }
    assert len(overlays) == len(manifest["frames"])
    for frame, image_path, sidecar_path in zip(
        manifest["frames"], image_paths, sidecar_paths
    ):
        overlay_path = overlays[f"tool_xz_sweep_overlay_{int(frame['seq']):02d}"]
        source = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
        assert source is not None
        assert overlay is not None
        assert overlay.shape == source.shape
        assert sidecar_path.is_file()
        record = result["records"][int(frame["seq"])]
        _logger.info(
            "Overlay %s tool=%s x=%.3f z=%.3f fiducials=%s nozzle=%s accepted=%s",
            overlay_path.resolve(),
            frame["tool"],
            float(frame["x_mm"]),
            float(frame["z_mm"]),
            "yes" if record["fiducials_detected"] else "no",
            "yes" if record["nozzle_detected"] else "no",
            "yes" if record["accepted_for_u_x_fit"] else "no",
        )

    assert len(result["records"]) == 96
    assert {record["tool"] for record in result["records"]} == {"T0", "T1"}
    assert "fit_strategy_comparison" in result
    assert Path(result["artifacts"]["fit_strategy_comparison"]["path"]).is_file()
    assert Path(result["artifacts"]["fit_strategy_comparison_plot"]["path"]).is_file()
    assert "bright_circle_gate_comparison" in result
    gate_artifact = Path(
        result["artifacts"]["bright_circle_gate_comparison"]["path"]
    )
    assert gate_artifact.is_file()
    _logger.info(
        "Replay summary %s frames=%d fiducials=%d nozzle=%d accepted=%s",
        root.resolve(),
        len(result["records"]),
        sum(record["fiducials_detected"] for record in result["records"]),
        sum(record["nozzle_detected"] for record in result["records"]),
        result["accepted"],
    )


def test_replay_extended_idex_tool_xz_sweep_with_injected_linear_priors(
    monkeypatch,
):
    """Check downstream XZ localization/fitting with a fixed ROI prior."""

    manifest, image_paths, sidecar_paths = _dataset()
    assert manifest["job_type"] == "idex_tool_xz_sweep_report"
    assert len(manifest["frames"]) == 96

    analyzer = _analyzer_module()
    monkeypatch.setattr(analyzer, "GENERATE_OVERLAYS", True)
    references = _injected_linear_prior_references(manifest)
    root = _run_root()
    _logger.info(
        "Injected replay priors t0=%s t1=%s",
        references["t0"]["nozzle_image_prior"]["coefficients_px"],
        references["t1"]["nozzle_image_prior"]["coefficients_px"],
    )
    result = analyzer.analyze(
        image_paths,
        root / "artifacts",
        frames=manifest["frames"],
        references=references,
        acquisition_calibration=manifest["acquisition_calibration"],
    )
    _write_result(root, result)

    overlays = {
        key: Path(artifact["path"])
        for key, artifact in result["artifacts"].items()
        if key.startswith("tool_xz_sweep_overlay_")
    }
    assert len(overlays) == len(manifest["frames"])
    assert len(result["records"]) == 96
    for frame, image_path, sidecar_path in zip(
        manifest["frames"], image_paths, sidecar_paths
    ):
        overlay_path = overlays[f"tool_xz_sweep_overlay_{int(frame['seq']):02d}"]
        source = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
        assert source is not None
        assert overlay is not None
        assert overlay.shape == source.shape
        assert sidecar_path.is_file()
        record = result["records"][int(frame["seq"])]
        localization = record["localization"]
        _logger.info(
            "Overlay %s tool=%s x=%.3f z=%.3f prior=%s roi=%s nozzle=%s "
            "score=%.1f residual=%s accepted=%s",
            overlay_path.resolve(),
            frame["tool"],
            float(frame["x_mm"]),
            float(frame["z_mm"]),
            localization["prior_center_px"],
            localization["roi_px"],
            record["nozzle_uv_px"],
            float(localization["bright_circle_score"]),
            localization["row_residual_px"],
            "yes" if record["accepted_for_u_x_fit"] else "no",
        )

    # These were the representative live-fallback failures.  The test is
    # specifically intended to show whether their ROI seed, rather than the
    # downstream fit, caused the failure.
    for seq in (0, 69):
        record = result["records"][seq]
        localization = record["localization"]
        nozzle_center = record["nozzle_uv_px"]
        assert localization["prior_center_px"] is not None
        assert nozzle_center is not None
        assert localization["roi_px"][0] <= nozzle_center[0] <= localization["roi_px"][2]
        assert localization["roi_px"][1] <= nozzle_center[1] <= localization["roi_px"][3]

    # The joint trajectory selector must keep the good T1 point and the dim T0
    # alternative after reselection, rather than rejecting either on the
    # contaminated pre-reselection row residual or absolute brightness.
    t1_good = result["records"][69]
    assert t1_good["accepted_for_u_x_fit"] is True
    assert t1_good["localization"]["row_residual_px"] <= 4.0
    assert (
        t1_good["localization"]["trajectory_consensus"]["method"]
        == "pair_trajectory_consensus_v1"
    )
    t0_dim = result["records"][0]
    assert t0_dim["accepted_for_u_x_fit"] is True
    assert t0_dim["localization"]["bright_circle_score"] < 45.0
    assert (
        t0_dim["localization"]["quality_gate"]["mode"]
        == "geometry_consensus_fallback"
    )

    gate_comparison = result["bright_circle_gate_comparison"]
    assert gate_comparison["counts"] == {
        "active_accepted": 96,
        "bright_circle_records": 96,
        "legacy_accepted": 77,
        "newly_admitted_geometry_consensus": 19,
        "nozzle_not_detected": 0,
        "rejected_by_active_gate": 0,
    }
    assert all(
        fit["sample_count"] == 6
        for fit in result["u_x_linear_fits"]
        if fit["slope_u_px_per_mm"] is not None
    )
    assert all(
        fit["slope_u_px_per_mm"] is not None
        for fit in result["u_x_linear_fits"]
    )
    assert result["shared_z_curve_fit"]["available"] is False

    _logger.info(
        "Injected-prior replay summary %s frames=%d fiducials=%d nozzle=%d "
        "accepted_u_x=%d shared_fit_available=%s",
        root.resolve(),
        len(result["records"]),
        sum(record["fiducials_detected"] for record in result["records"]),
        sum(record["nozzle_detected"] for record in result["records"]),
        sum(record["accepted_for_u_x_fit"] for record in result["records"]),
        result["shared_z_curve_fit"]["available"],
    )
