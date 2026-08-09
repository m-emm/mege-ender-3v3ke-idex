import importlib.util
import math
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
    spec = importlib.util.spec_from_file_location(
        "vision_fiducial_locator_test", FILES / "vision_four_fiducials.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _patch_image() -> np.ndarray:
    patch = np.zeros((140, 140, 3), dtype=np.uint8)
    patch[47:93, 47:93] = 255
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, 42, 38)
    patch[51:89, 51:89] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    for center_x, center_y in ((30, 30), (110, 30), (30, 110), (110, 110)):
        cv2.circle(patch, (center_x, center_y), 13, (255, 255, 255), 3)
        cv2.circle(patch, (center_x, center_y), 8, (255, 255, 255), 2)
        cv2.circle(patch, (center_x, center_y), 2, (255, 255, 255), -1)
    return patch


def _frame_for_pose(angle_deg: float, scale: float) -> np.ndarray:
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    patch = _patch_image()
    center = np.asarray([900.0, 500.0])
    local = np.asarray(
        [[-70.0, -70.0], [70.0, -70.0], [70.0, 70.0], [-70.0, 70.0]],
        dtype=np.float32,
    )
    angle = math.radians(angle_deg)
    rotation = np.asarray(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]],
        dtype=np.float32,
    )
    destination = center + (local @ rotation.T) * scale
    destination += np.asarray([[0.0, 0.0], [0.0, 0.0], [8.0, -4.0], [-4.0, 5.0]])
    source = np.asarray(
        [[0.0, 0.0], [140.0, 0.0], [140.0, 140.0], [0.0, 140.0]],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(source, destination.astype(np.float32))
    warped = cv2.warpPerspective(patch, homography, (1920, 1080))
    mask = cv2.warpPerspective(
        np.full((140, 140), 255, dtype=np.uint8), homography, (1920, 1080)
    )
    frame[mask > 0] = warped[mask > 0]
    return frame


@pytest.mark.parametrize("angle_deg,scale", [(-18.0, 0.75), (7.0, 1.0), (31.0, 1.15)])
def test_aruco_locator_and_circle_geometry_follow_patch_pose(angle_deg, scale):
    module = _module()
    image = _frame_for_pose(angle_deg, scale)

    detection = module.detect_four_fiducials(image)
    locator = detection["locator"]
    assert locator["marker_id"] == 42
    assert len(locator["marker_corners_px"]) == 4
    assert len(detection["patch_corners_px"]) == 4

    expected = np.asarray(locator["expected_fiducial_centers_px"], dtype=float)
    centers = np.asarray(detection["centers_px"], dtype=float)
    np.testing.assert_allclose(centers, expected, rtol=0.0, atol=5.0)

    measured_angle = float(detection["right_edge_angle_deg"])
    expected_angle = float(
        math.degrees(
            math.atan2(
                locator["expected_fiducial_centers_px"][1][1]
                - locator["expected_fiducial_centers_px"][0][1],
                locator["expected_fiducial_centers_px"][1][0]
                - locator["expected_fiducial_centers_px"][0][0],
            )
        )
    )
    angle_error = abs((measured_angle - expected_angle + 180.0) % 360.0 - 180.0)
    assert angle_error < 4.0
    assert detection["geometry"]["geometry_score"] > 60.0


def test_aruco_orientation_keeps_named_corners_stable_after_quarter_turn():
    module = _module()
    for angle_deg in (0.0, 90.0, 180.0, 270.0):
        detection = module.detect_four_fiducials(_frame_for_pose(angle_deg, 1.0))
        centers = np.asarray(detection["centers_px"], dtype=float)
        expected = np.asarray(
            detection["locator"]["expected_fiducial_centers_px"], dtype=float
        )
        np.testing.assert_allclose(centers, expected, rtol=0.0, atol=8.0)


def test_circle_geometry_rejects_a_non_square_rectangle():
    module = _module()
    candidates = [
        {"center_px": point, "radius_px": 10.0}
        for point in ((200.0, 200.0), (280.0, 200.0), (200.0, 250.0), (280.0, 250.0))
    ]

    with pytest.raises(module.FourFiducialError, match="square geometry"):
        module.find_four_fiducials(candidates, expected_edge_length_px=80.0)


def test_circle_geometry_reports_edge_angle_without_a_camera_angle_prior():
    module = _module()
    angle_deg = -20.0
    angle = math.radians(angle_deg)
    right = np.asarray([80.0 * math.cos(angle), 80.0 * math.sin(angle)])
    down = np.asarray([80.0 * math.sin(-angle), 80.0 * math.cos(angle)])
    top_left = np.asarray([300.0, 300.0])
    points = np.asarray(
        [top_left, top_left + right, top_left + down, top_left + right + down]
    )

    selected = module.find_four_fiducials(
        [{"center_px": point.tolist(), "radius_px": 10.0} for point in points],
        expected_edge_length_px=80.0,
        reference_centers_px=points,
    )
    geometry = module.quad_geometry(
        np.asarray([candidate["center_px"] for candidate in selected]),
        reference_centers_px=points,
    )
    assert geometry is not None
    _score, details = geometry
    assert abs(float(details["right_edge_angle_deg"]) - angle_deg) < 1e-6
