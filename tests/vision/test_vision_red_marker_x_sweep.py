import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest


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
    name = f"vision_red_marker_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(
        name, FILES / "vision_red_marker_x_sweep.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_frames(tmp_path):
    paths = []
    frames = []
    x_values = (160, 170, 180, 190, 200, 210)
    for tool in ("T0", "T1"):
        for x_mm in x_values:
            image = np.full((540, 960, 3), (52, 48, 44), dtype=np.uint8)
            cv2.line(image, (80, 180), (880, 180), (100, 100, 100), 5)
            marker_x = round(
                350 + 4.05 * (x_mm - 160) + (-40 if tool == "T1" else 0)
            )
            marker_y = 210
            hidden = (tool == "T0" and x_mm < 180) or (
                tool == "T1" and x_mm < 190
            )
            if not hidden:
                cv2.rectangle(
                    image,
                    (marker_x - 28, marker_y - 28),
                    (marker_x + 28, marker_y + 28),
                    (105, 105, 105),
                    -1,
                )
                cv2.rectangle(
                    image,
                    (marker_x - 10, marker_y - 23),
                    (marker_x + 10, marker_y + 23),
                    (20, 20, 230),
                    -1,
                )
                cv2.circle(image, (marker_x, marker_y), 5, (10, 10, 10), -1)
                cv2.line(
                    image,
                    (marker_x - 22, marker_y + 15),
                    (marker_x + 22, marker_y + 15),
                    (220, 220, 220),
                    2,
                )
            if tool == "T1":
                # A larger red distractor must not win merely by area.
                cable_x = 250 + round(1.3 * (x_mm - 160))
                cv2.ellipse(
                    image,
                    (cable_x, 105),
                    (25, 45),
                    20,
                    0,
                    300,
                    (20, 20, 220),
                    10,
                )
            path = tmp_path / f"{tool.lower()}_x{x_mm}.jpg"
            assert cv2.imwrite(str(path), image)
            paths.append(path)
            frames.append({"tool": tool, "x_mm": x_mm})
    return paths, frames


def test_recovers_marker_axis_and_rejects_larger_red_distractor(tmp_path):
    module = _module()
    paths, frames = _synthetic_frames(tmp_path)
    result = module.analyze(
        paths,
        tmp_path / "artifacts",
        frames=frames,
        reference={
            "corner_pixel_xy_px": [300.0, 100.0],
            "corner_printer_xyz_mm": [170.0, -20.0, 0.0],
            "image_y_axis_vector_px_per_mm": [-0.11, -5.25],
            "corner_pixel_capture_y_mm": -20.0,
            "capture_y_mm": -14.0,
        },
        localizer={"kind": "red_marker_trajectory", "version": 1},
    )

    assert result["accepted"]
    assert set(result["accepted_x_mm"]) == {"T0", "T1"}
    assert all(
        len(values) == 3 and max(values) - min(values) >= 20
        for values in result["accepted_x_mm"].values()
    )
    assert result["common_axis_vector_px_per_mm"] == pytest.approx(
        [4.05, 0.0], abs=0.1
    )
    assert set(result["artifacts"]) == {
        "contact_sheet",
        "marker_selection",
        "core_registration",
        "cross_tool_registration",
        "trajectory",
    }


def test_rejects_missing_tool_trajectory(tmp_path):
    module = _module()
    paths, frames = _synthetic_frames(tmp_path)
    for path, frame in zip(paths, frames):
        if frame["tool"] == "T1":
            image = np.full((540, 960, 3), 50, dtype=np.uint8)
            assert cv2.imwrite(str(path), image)
    result = module.analyze(
        paths,
        tmp_path / "missing-artifacts",
        frames=frames,
        reference={
            "corner_pixel_xy_px": [300.0, 100.0],
            "corner_printer_xyz_mm": [170.0, -20.0, 0.0],
            "image_y_axis_vector_px_per_mm": [-0.11, -5.25],
            "corner_pixel_capture_y_mm": -20.0,
            "capture_y_mm": -14.0,
        },
        localizer={"kind": "red_marker_trajectory", "version": 1},
    )
    assert not result["accepted"]
    assert any("T1" in reason for reason in result["reasons"])


def test_pair_registration_excludes_one_inconsistent_representation(monkeypatch):
    module = _module()
    calls = iter(
        [
            {"shift_px": [80.0, -1.0], "correlation": 0.75, "boundary_hit": False},
            {"shift_px": [-76.0, 1.0], "correlation": 0.72, "boundary_hit": False},
            {"shift_px": [79.0, -1.2], "correlation": 0.81, "boundary_hit": False},
            {"shift_px": [-79.4, 1.0], "correlation": 0.79, "boundary_hit": False},
        ]
    )

    monkeypatch.setattr(
        module,
        "_one_way_registration",
        lambda *_args, **_kwargs: next(calls),
    )
    representations = {
        "gray": np.zeros((20, 20), dtype=np.uint8),
        "clahe": np.zeros((20, 20), dtype=np.uint8),
    }
    registration = module._pair_registration(
        representations,
        np.asarray([10.0, 10.0]),
        representations,
        np.asarray([10.0, 10.0]),
    )

    assert registration["usable_representations"] == ["clahe"]
    assert registration["shift_px"] == pytest.approx([79.2, -1.1])
    assert registration["minimum_correlation"] == pytest.approx(0.79)
    assert registration["representation_spread_px"] == 0.0
    assert not registration["boundary_hit"]
