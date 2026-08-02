import hashlib
import importlib.util
import json
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
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision_bed_fiducial_metric"


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    name = "vision_bed_fiducial_real_image_test"
    spec = importlib.util.spec_from_file_location(name, FILES / "vision_bed_fiducial.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CASES = (
    pytest.param(
        "metric_y_00_00mm",
        [[781, 465], [862, 456], [789, 545], [870, 535]],
        id="forward-y0",
    ),
    pytest.param(
        "metric_y_01_10mm",
        [[780, 364], [861, 355], [788, 444], [870, 436]],
        id="forward-y10",
    ),
    pytest.param(
        "metric_y_02_20mm",
        [[779, 259], [862, 251], [788, 342], [868, 334]],
        id="forward-y20",
    ),
    pytest.param(
        "metric_y_03_20mm",
        [[779, 259], [861, 251], [788, 341], [868, 334]],
        id="reverse-y20",
    ),
    pytest.param(
        "metric_y_04_10mm",
        [[780, 363], [860, 355], [788, 443], [869, 435]],
        id="reverse-y10",
    ),
    pytest.param(
        "metric_y_05_00mm",
        [[783, 464], [861, 457], [789, 543], [869, 535]],
        id="reverse-y0",
    ),
)


@pytest.mark.parametrize(("stem", "expected_centers_px"), CASES)
def test_detect_four_bed_fiducials_from_real_metric_frame(
    stem,
    expected_centers_px,
):
    image_path = FIXTURES / f"{stem}.jpg"
    sidecar_path = FIXTURES / f"{stem}.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    assert sidecar["sha256"] == f"sha256:{digest}"

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    assert image is not None
    assert image.shape[:2] == (sidecar["height"], sidecar["width"])

    detection = _module().detect_four_fiducials(image)

    centers = np.asarray(detection["centers_px"], dtype=np.float64)
    assert centers.shape == (4, 2)
    assert len(detection["radii_px"]) == 4
    np.testing.assert_allclose(
        centers,
        np.asarray(expected_centers_px, dtype=np.float64),
        rtol=0.0,
        atol=5.0,
    )


def test_analyze_metric_from_real_forward_reverse_capture(tmp_path):
    sidecars = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURES.glob("*.json"))
    ]
    frame_paths = [FIXTURES / f"{sidecar['frame']}.jpg" for sidecar in sidecars]
    frames = [
        {
            "commanded_position_mm": sidecar["commanded_position_mm"],
            "y_offset_mm": sidecar["y_offset_mm"],
        }
        for sidecar in sidecars
    ]

    result = _module().analyze_metric(
        frame_paths,
        tmp_path,
        frames=frames,
        patch_points_mm=[[3, 3], [11, 3], [3, 11], [11, 11]],
    )

    assert result["accepted"], result["reasons"]
    assert result["usable_frame_count"] == 6
    assert len(result["detection_records"]) == 6
    assert all(record is not None for record in result["detection_records"])
    assert set(result["artifacts"]) == {
        "fiducial_metric_tracking",
        "fiducial_displacement_plot",
    }
