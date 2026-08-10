from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np


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


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_bright_circle_nozzle_localization_test",
        FILES / "vision_nozzle_tip_localization.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frame(index: int, x_mm: float) -> dict:
    return {
        "seq": index,
        "tool": "T0",
        "x_mm": x_mm,
        "z_mm": 1.0,
    }


def _write_blank_frames(tmp_path: Path, count: int) -> list[Path]:
    paths = []
    for index in range(count):
        path = tmp_path / f"frame_{index}.png"
        assert cv2.imwrite(str(path), np.full((180, 240, 3), 32, dtype=np.uint8))
        paths.append(path)
    return paths


def _registration_for_quality(
    module,
    *,
    score: float = 20.0,
    inlier_count: int = 4,
    sample_count: int = 6,
    consensus_rms: float = 1.0,
    row_residual: float = 1.0,
    consensus_inlier: bool = True,
) -> dict:
    return {
        "center_px": [100.0, 90.0],
        "bright_circle_score": score,
        "row_residual_px": row_residual,
        "trajectory_consensus_inlier": consensus_inlier,
        "trajectory_consensus": {
            "inlier_count": inlier_count,
            "sample_count": sample_count,
            "inlier_rms_px": consensus_rms,
        },
    }


def test_geometry_consensus_accepts_dim_candidate_normally():
    module = _module()

    result = module.evaluate_bright_circle_quality(
        _registration_for_quality(module, score=2.5)
    )

    assert result["accepted"] is True
    assert result["mode"] == "geometry_consensus_fallback"
    assert result["legacy_brightness_pass"] is False
    assert result["consensus_pass"] is True


def test_geometry_consensus_rejects_score_below_active_floor():
    module = _module()

    result = module.evaluate_bright_circle_quality(
        _registration_for_quality(module, score=-10.1)
    )

    assert result["accepted"] is False
    assert any("active floor" in reason for reason in result["reasons"])


def test_geometry_consensus_rejects_insufficient_inliers():
    module = _module()

    result = module.evaluate_bright_circle_quality(
        _registration_for_quality(module, inlier_count=3)
    )

    assert result["accepted"] is False
    assert any("inliers" in reason for reason in result["reasons"])


def test_geometry_consensus_rejects_high_consensus_rms():
    module = _module()

    result = module.evaluate_bright_circle_quality(
        _registration_for_quality(module, consensus_rms=2.51)
    )

    assert result["accepted"] is False
    assert any("consensus RMS" in reason for reason in result["reasons"])


def test_robust_line_uses_majority_trajectory_with_sloped_outlier():
    module = _module()
    values_x = np.asarray([191.0, 193.0, 195.0, 197.0, 199.0])
    values_y = np.asarray([1109.5, 1128.5, 1122.5, 1166.5, 1185.5])

    slope, intercept = module._robust_line(values_x, values_y)
    residuals = values_y - (slope * values_x + intercept)

    assert slope == 9.5
    assert intercept == -705.0
    assert np.allclose(residuals, [0.0, 0.0, -25.0, 0.0, 0.0])


def test_bright_circle_detector_prefers_disk_over_distractor(tmp_path):
    module = _module()
    image = np.full((540, 960, 3), 35, dtype=np.uint8)
    cv2.circle(image, (480, 270), 5, (245, 245, 245), -1)
    cv2.rectangle(image, (528, 258), (532, 262), (255, 255, 255), -1)
    path = tmp_path / "bright_disk.png"
    assert cv2.imwrite(str(path), image)

    result = module.localize_bright_nozzle_tip_grid(
        [path],
        frames=[_frame(0, 191.0)],
        roi_centers_px=[np.asarray([480.0, 270.0])],
    )
    registration = result["registrations"][0]
    center = np.asarray(registration["center_px"], dtype=np.float64)

    assert registration["localization_method"] == "bright_circle_roi_v1"
    assert np.linalg.norm(center - np.asarray([480.0, 270.0])) < 3.0
    assert registration["bright_circle_score"] > 45.0


def test_candidate_replacement_prefers_row_trajectory_over_brightest_candidate(
    tmp_path, monkeypatch
):
    module = _module()
    paths = _write_blank_frames(tmp_path, 5)
    frames = [_frame(index, 191.0 + index) for index in range(5)]

    def candidates(_image, _center, **_kwargs):
        index = len(seen)
        seen.append(index)
        true_center = [100.0 + 2.0 * index, 90.0]
        false_center = [180.0, 130.0]
        false = index == 2
        return {
            "roi_px": [50, 50, 220, 160],
            "prior_center_px": true_center,
            "score_margin": 30.0,
            "candidates": [
                {
                    "center_px": false_center if false else true_center,
                    "radius_px": 9.0,
                    "score": 150.0,
                },
                {
                    "center_px": true_center if false else false_center,
                    "radius_px": 9.0,
                    "score": 110.0 if false else 80.0,
                },
            ],
        }

    seen: list[int] = []
    monkeypatch.setattr(module, "_bright_circle_candidates", candidates)
    monkeypatch.setattr(
        module,
        "_refine_bright_circle",
        lambda _gray, center, radius: (center, radius, 110.0, 110.0),
    )

    result = module.localize_bright_nozzle_tip_grid(
        paths,
        frames=frames,
        roi_centers_px=[np.asarray([100.0 + 2.0 * index, 90.0]) for index in range(5)],
    )
    selected = [
        np.asarray(registration["center_px"], dtype=np.float64)
        for registration in result["registrations"]
    ]

    assert len(seen) == 5
    assert np.allclose(selected, [[100.0 + 2.0 * index, 90.0] for index in range(5)])


def test_row_residual_rejects_isolated_bright_circle_outlier(tmp_path, monkeypatch):
    module = _module()
    paths = _write_blank_frames(tmp_path, 5)
    frames = [_frame(index, 191.0 + index) for index in range(5)]

    def candidates(_image, _center, **_kwargs):
        index = len(seen)
        seen.append(index)
        center = [100.0 + 2.0 * index, 115.0 if index == 2 else 90.0]
        return {
            "roi_px": [50, 50, 220, 160],
            "prior_center_px": [100.0 + 2.0 * index, 90.0],
            "score_margin": None,
            "candidates": [{"center_px": center, "radius_px": 9.0, "score": 110.0}],
        }

    seen: list[int] = []
    monkeypatch.setattr(module, "_bright_circle_candidates", candidates)
    monkeypatch.setattr(
        module,
        "_refine_bright_circle",
        lambda _gray, center, radius: (center, radius, 110.0, 110.0),
    )

    result = module.localize_bright_nozzle_tip_grid(
        paths,
        frames=frames,
        roi_centers_px=[np.asarray([100.0 + 2.0 * index, 90.0]) for index in range(5)],
    )
    outlier = result["registrations"][2]

    assert outlier["row_residual_px"] > 4.0
    assert outlier["accepted_for_u_x_fit"] is False
    assert "row residual" in outlier["rejection_reason"]


def test_marker_prior_uses_robust_offset_and_large_xy_roi(tmp_path, monkeypatch):
    module = _module()
    paths = _write_blank_frames(tmp_path, 3)
    frames = [_frame(index, 191.0 + index) for index in range(3)]
    marker_centers = [np.asarray([100.0 + index, 90.0]) for index in range(3)]
    seen_rois = []

    def rings(_image, marker):
        marker = np.asarray(marker, dtype=np.float64)
        center = marker + [50.0, 10.0]
        return [
            {
                "center_px": center.tolist(),
                "radius_px": 40.0,
                "marker_delta_px": [50.0, 10.0],
                "edge_score": 100.0,
            }
        ]

    def tips(_image, ring, *, physical_tip_only=False):
        assert physical_tip_only
        center = np.asarray(ring["center_px"], dtype=np.float64) + [12.0, 2.0]
        return [
            {
                "center_px": center.tolist(),
                "tip_to_ring_delta_px": [12.0, 2.0],
                "score": 100.0,
            }
        ]

    def bright(_image, center, **kwargs):
        seen_rois.append(kwargs)
        center = np.asarray(center, dtype=np.float64)
        return {
            "roi_px": [
                int(center[0] - kwargs["half_width_px"]),
                int(center[1] - kwargs["half_height_px"]),
                int(center[0] + kwargs["half_width_px"]),
                int(center[1] + kwargs["half_height_px"]),
            ],
            "prior_center_px": center.tolist(),
            "score_margin": 10.0,
            "candidates": [
                {
                    "center_px": center.tolist(),
                    "radius_px": 9.0,
                    "score": 100.0,
                }
            ],
        }

    monkeypatch.setattr(module, "_ring_candidates", rings)
    monkeypatch.setattr(module, "_tip_candidates", tips)
    monkeypatch.setattr(module, "_bright_circle_candidates", bright)
    monkeypatch.setattr(
        module,
        "_refine_bright_circle",
        lambda _gray, center, radius: (center, radius, 100.0, 100.0),
    )

    result = module.localize_bright_nozzle_tip_from_marker_prior_grid(
        paths,
        frames=frames,
        marker_prior_centers_px=marker_centers,
    )

    assert all(kwargs["half_width_px"] == 55.0 for kwargs in seen_rois)
    assert all(kwargs["half_height_px"] == 45.0 for kwargs in seen_rois)
    for registration in result["registrations"]:
        assert registration["localization_seed_method"] == "red_marker_image_line_v1"
        assert registration["coarse_marker_to_nozzle_offset_px"] == [62.0, 12.0]
        assert registration["accepted_for_u_x_fit"] is True
