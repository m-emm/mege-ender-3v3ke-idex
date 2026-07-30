import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np


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


def _load():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    name = f"vision_bed_tab_corner_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(
        name, FILES / "vision_bed_tab_corner.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_frames(tmp_path, shifts=None):
    height, width = 540, 960
    random = np.random.default_rng(42)
    base = np.full((height, width, 3), (172, 184, 196), dtype=np.uint8)
    noise = random.normal(0, 4, base.shape[:2]).astype(np.int16)
    for channel in range(3):
        base[:, :, channel] = np.clip(
            base[:, :, channel].astype(np.int16) + noise, 0, 255
        ).astype(np.uint8)
    cv2.fillPoly(
        base,
        [np.asarray([[260, 205], [600, 205], [680, 430], [260, 430]])],
        (26, 28, 31),
        lineType=cv2.LINE_AA,
    )
    cv2.line(base, (260, 205), (600, 205), (235, 238, 240), 3, cv2.LINE_AA)
    cv2.line(base, (600, 205), (680, 430), (215, 220, 225), 3, cv2.LINE_AA)
    for x in range(300, 610, 35):
        cv2.circle(base, (x, 250 + (x % 4) * 13), 7, (72, 78, 84), -1)
    cv2.rectangle(base, (80, 455), (880, 475), (48, 50, 54), -1)
    cv2.line(base, (80, 455), (880, 455), (230, 230, 230), 2, cv2.LINE_AA)
    shifts = shifts or [(0.0, 0.0), (0.4, -0.2), (-0.3, 0.3), (0.2, 0.4), (-0.2, -0.3)]
    paths = []
    for index, (x_shift, y_shift) in enumerate(shifts):
        matrix = np.asarray([[1.0, 0.0, x_shift], [0.0, 1.0, y_shift]])
        image = cv2.warpAffine(
            base,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        path = tmp_path / f"duplicate_{index}.jpg"
        assert cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 96])
        paths.append(path)
    return paths


def test_corner_localizer_uses_prediction_and_duplicate_registration(tmp_path):
    module = _load()
    frames = _synthetic_frames(tmp_path)
    result = module.analyze(
        frames,
        tmp_path / "artifacts",
        expected_corner_px=[600.0, 205.0],
        localizer={"kind": "bed_tab_corner", "version": 1},
    )

    assert result["accepted"], result["reasons"]
    assert (
        np.linalg.norm(
            np.asarray(result["corner_pixel_xy_px"]) - np.asarray([600.0, 205.0])
        )
        < 3.0
    )
    assert result["usable_frame_count"] == 5
    assert result["line_confirmation_count"] == 5
    assert result["median_correlation"] > 0.95
    assert result["repeatability_max_px"] < 1.0
    assert set(result["artifacts"]) == {
        "corner_localization",
        "corner_duplicate_registration",
    }


def test_corner_localizer_rejects_missing_semantic_corner_near_prediction(tmp_path):
    module = _load()
    frames = _synthetic_frames(tmp_path)
    result = module.analyze(
        frames,
        tmp_path / "artifacts",
        expected_corner_px=[120.0, 90.0],
        localizer={"kind": "bed_tab_corner", "version": 1},
    )

    assert not result["accepted"]
    assert any("upstream Y-model prediction" in reason for reason in result["reasons"])
