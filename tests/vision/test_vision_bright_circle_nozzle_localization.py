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
