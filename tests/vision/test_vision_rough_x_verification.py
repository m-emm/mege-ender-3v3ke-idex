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
    name = f"vision_rough_x_verification_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(
        name, FILES / "vision_rough_x_verification.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _reference():
    return {
        "image_x_axis_vector_px_per_mm": [4.0, 0.0],
        "corner_pixel_xy_px": [300.0, 300.0],
        "corner_printer_xyz_mm": [173.0, -18.0, 0.0],
        "image_y_axis_vector_px_per_mm": [0.0, -5.0],
        "corner_pixel_capture_y_mm": -18.0,
        "capture_y_mm": -18.0,
        "expected_offset_mm": 10.0,
        "command_x_mm": 183.0,
    }


def _verification_frames(tmp_path, marker_x=340, include_marker=True):
    paths = []
    frames = []
    for tool in ("T0", "T1"):
        image = np.full((540, 960, 3), (42, 45, 48), dtype=np.uint8)
        cv2.rectangle(image, (260, 175), (430, 285), (82, 84, 86), -1)
        cv2.line(image, (265, 272), (425, 272), (190, 190, 190), 3)
        if include_marker:
            cv2.rectangle(
                image,
                (marker_x - 11, 198),
                (marker_x + 11, 262),
                (18, 20, 230),
                -1,
            )
            cv2.circle(image, (marker_x, 224), 5, (10, 10, 10), -1)
            cv2.line(
                image,
                (marker_x - 8, 245),
                (marker_x + 8, 245),
                (220, 220, 220),
                2,
            )
        path = tmp_path / f"{tool.lower()}.jpg"
        assert cv2.imwrite(str(path), image)
        paths.append(path)
        frames.append({"tool": tool, "x_mm": 183.0})
    return paths, frames


def test_calculates_both_endstops_against_fixed_bed_prior():
    module = _module()
    result = module.calculate_candidate(
        prior_xyz_mm=[173.0, -18.0, 0.0],
        t0_marker_fact={"offset_mm": 16.6, "reference_commanded_x_mm": 190.0},
        t1_marker_fact={"offset_mm": 6.6, "reference_commanded_x_mm": 190.0},
        old_t0_x_endstop_mm=-80.4,
        old_t1_x_endstop_mm=357.5,
    )

    assert result["tools"]["T0"]["calculated_correction_mm"] == pytest.approx(-0.4)
    assert result["tools"]["T1"]["calculated_correction_mm"] == pytest.approx(-10.4)
    assert result["tools"]["T0"]["candidate_x_endstop_mm"] == pytest.approx(-80.8)
    assert result["tools"]["T1"]["candidate_x_endstop_mm"] == pytest.approx(347.1)


def test_accepts_two_markers_at_expected_x_projection(tmp_path):
    module = _module()
    paths, frames = _verification_frames(tmp_path)
    result = module.analyze(
        paths,
        tmp_path / "artifacts",
        frames=frames,
        reference=_reference(),
        localizer={"kind": "rough_x_marker_verification", "version": 1},
    )

    assert result["accepted"]
    assert result["t0_residual_mm"] == pytest.approx(0.0, abs=0.15)
    assert result["t1_residual_mm"] == pytest.approx(0.0, abs=0.15)
    assert result["marker_coincidence_residual_mm"] == pytest.approx(
        0.0, abs=0.15
    )
    assert set(result["artifacts"]) == {
        "verification_overlay",
        "cross_tool_registration",
    }


def test_projects_corner_from_its_capture_y_not_the_physical_prior_y(tmp_path):
    module = _module()
    paths, frames = _verification_frames(tmp_path)
    reference = _reference()
    reference["corner_pixel_xy_px"] = [300.0, 100.0]
    reference["corner_pixel_capture_y_mm"] = 5.0
    reference["capture_y_mm"] = -15.0

    result = module.analyze(
        paths,
        tmp_path / "capture-anchor-artifacts",
        frames=frames,
        reference=reference,
        localizer={"kind": "rough_x_marker_verification", "version": 1},
    )

    assert result["corner_pixel_at_capture_y_px"] == pytest.approx([300.0, 200.0])


def test_rejects_mutually_aligned_markers_at_wrong_absolute_x(tmp_path):
    module = _module()
    paths, frames = _verification_frames(tmp_path, marker_x=352)
    result = module.analyze(
        paths,
        tmp_path / "wrong-artifacts",
        frames=frames,
        reference=_reference(),
        localizer={"kind": "rough_x_marker_verification", "version": 1},
    )

    assert not result["accepted"]
    assert any("absolute marker residual" in reason for reason in result["reasons"])


def test_rejects_missing_marker(tmp_path):
    module = _module()
    paths, frames = _verification_frames(tmp_path, include_marker=False)
    result = module.analyze(
        paths,
        tmp_path / "missing-artifacts",
        frames=frames,
        reference=_reference(),
        localizer={"kind": "rough_x_marker_verification", "version": 1},
    )

    assert not result["accepted"]
    assert any("red marker was not found" in reason for reason in result["reasons"])


def test_registration_spread_ignores_tool_appearance_shift_normal_to_image_x():
    module = _module()
    registration = {
        "usable_representations": ["gray", "clahe"],
        "representations": {
            "gray": {"combined_shift_px": [2.0, 6.0]},
            "clahe": {"combined_shift_px": [2.3, 11.0]},
        },
    }

    spread = module._image_x_representation_spread_px(
        registration, np.asarray([1.0, 0.0])
    )

    assert spread == pytest.approx(0.3)
