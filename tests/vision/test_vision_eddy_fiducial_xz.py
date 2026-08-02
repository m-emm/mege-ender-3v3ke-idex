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


def _module(filename, name):
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(name, FILES / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_eddy_circle_detector_recovers_center_from_simple_ring():
    analyzer = _module(
        "vision_eddy_fiducial_xz.py",
        "vision_eddy_fiducial_circle_test",
    )
    image = np.full((540, 960, 3), 32, dtype=np.uint8)
    cv2.circle(image, (560, 220), 44, (235, 235, 235), 7)
    cv2.circle(image, (560, 220), 18, (110, 110, 110), 3)
    localizer = {
        "roi_1080": [700, 180, 850, 650],
        "expected_center_1080": [1120, 440],
        "radius_range_1080": [45, 120],
        "hough_threshold": 20,
        "minimum_edge_score": 6,
        "center_weight": 0.02,
    }

    result = analyzer.detect_circle(image, localizer)

    assert result["accepted"]
    np.testing.assert_allclose(result["center_px"], [560, 220], atol=2.0)
    assert 40 <= result["radius_px"] <= 50


def test_eddy_grid_analysis_emits_raw_commanded_and_image_positions(tmp_path):
    analyzer = _module(
        "vision_eddy_fiducial_xz.py",
        "vision_eddy_fiducial_grid_test",
    )
    localizer = {
        "roi_1080": [700, 180, 850, 650],
        "expected_center_1080": [1120, 440],
        "radius_range_1080": [45, 120],
        "hough_threshold": 20,
        "minimum_edge_score": 6,
        "center_weight": 0.02,
    }
    frame_paths = []
    frames = []
    x_positions = [230.0, 234.666667, 239.333333, 244.0]
    z_positions = [0.5, 3.333333, 6.166667, 9.0]
    for row_index, z_mm in enumerate(z_positions):
        row = x_positions if row_index % 2 == 0 else list(reversed(x_positions))
        for x_mm in row:
            seq = len(frames)
            image = np.full((540, 960, 3), 32, dtype=np.uint8)
            center = (560 + seq, 220 + row_index)
            cv2.circle(image, center, 44, (235, 235, 235), 7)
            path = tmp_path / f"frame_{seq:02d}.png"
            assert cv2.imwrite(str(path), image)
            frame_paths.append(path)
            frames.append(
                {
                    "seq": seq,
                    "frame": f"frame_{seq:02d}",
                    "x_mm": x_mm,
                    "z_mm": z_mm,
                }
            )

    result = analyzer.analyze(
        frame_paths,
        tmp_path / "artifacts",
        frames=frames,
        localizer=localizer,
    )

    assert result["accepted"]
    assert len(result["raw_positions"]) == 16
    assert result["raw_positions"][0] == {
        "commanded_x_mm": 230.0,
        "commanded_z_mm": 0.5,
        "image_x_px": result["raw_positions"][0]["image_x_px"],
        "image_y_px": result["raw_positions"][0]["image_y_px"],
    }
    np.testing.assert_allclose(
        [
            result["raw_positions"][0]["image_x_px"],
            result["raw_positions"][0]["image_y_px"],
        ],
        [560, 220],
        atol=2.0,
    )
    assert "eddy_fiducial_xz_grid" in result["artifacts"]
