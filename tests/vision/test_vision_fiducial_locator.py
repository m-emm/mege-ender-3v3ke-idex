import importlib.util
import logging
import math
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
LIVE_XY_FIXTURE = (
    REPO_ROOT / "tests" / "vision" / "fixtures" / "fiducial_locator_xy"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_fiducial_locator_replay"


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


def test_live_xy_ring_centers_are_refined_and_render_debug_overlay():
    """Replay one live XY frame and leave a directly inspectable overlay."""

    module = _module()
    frame_path = LIVE_XY_FIXTURE / "t0_x197p000_z0p500.jpg"
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    assert image is not None, f"could not decode {frame_path}"

    detection = module.detect_four_fiducials(image)
    centers = np.asarray(detection["centers_px"], dtype=np.float64)
    assert centers.shape == (4, 2)

    # Fixture-local annotations from the bright outer ring, in the detector's
    # oriented [top_left, top_right, bottom_left, bottom_right] order.
    annotated_centers = np.asarray(
        [
            [874.2, 541.3],
            [794.5, 545.4],
            [870.0, 462.2],
            [789.6, 466.0],
        ],
        dtype=np.float64,
    )
    refined_errors = np.linalg.norm(centers - annotated_centers, axis=1)
    assert np.max(refined_errors) < 2.0

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + uuid4().hex[:8]
    )
    overlay_path = OUTPUT_ROOT / "runs" / run_id / "t0_x197_fiducials.png"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay = image.copy()

    patch = np.rint(np.asarray(detection["patch_corners_px"])).astype(np.int32)
    cv2.polylines(overlay, [patch], True, (0, 255, 0), 2, cv2.LINE_AA)
    for candidate in detection["candidates"]:
        center = tuple(np.rint(np.asarray(candidate["center_px"])).astype(int))
        cv2.circle(
            overlay,
            center,
            int(round(candidate["radius_px"])),
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )
    radii = detection["radii_px"]
    for index, (center, radius, annotated) in enumerate(
        zip(centers, radii, annotated_centers)
    ):
        refined = tuple(np.rint(center).astype(int))
        reference = tuple(np.rint(annotated).astype(int))
        cv2.circle(
            overlay,
            refined,
            int(round(radius)),
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.drawMarker(overlay, refined, (0, 255, 0), cv2.MARKER_CROSS, 22, 2)
        cv2.drawMarker(overlay, reference, (255, 0, 255), cv2.MARKER_TILTED_CROSS, 18, 2)
        cv2.putText(
            overlay,
            f"{index}: d={refined_errors[index]:.1f}px",
            (refined[0] + 12, refined[1] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    assert cv2.imwrite(str(overlay_path), overlay)
    _logger.info("Overlay %s", overlay_path.resolve())


def test_t0_xy_replay_has_stable_fiducials_across_four_frames():
    """The stationary bed patch must not jitter as the tool moves in X."""

    module = _module()
    frame_paths = [
        LIVE_XY_FIXTURE / f"{index:02d}_t0_x{191 + 2 * index}p000_z0p500.jpg"
        for index in range(1, 5)
    ]
    detections = []
    for frame_path in frame_paths:
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        assert image is not None, f"could not decode {frame_path}"
        detections.append((frame_path, image, module.detect_four_fiducials(image)))

    centers = np.asarray(
        [detection["centers_px"] for _path, _image, detection in detections],
        dtype=np.float64,
    )
    center_spread = np.ptp(centers, axis=0)
    assert float(np.max(center_spread)) < 1.5, center_spread

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + uuid4().hex[:8]
    )
    overlay_dir = OUTPUT_ROOT / "runs" / run_id / "t0_xy_replay_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    median_centers = np.median(centers, axis=0)
    for frame_path, image, detection in detections:
        overlay = image.copy()
        patch = np.rint(np.asarray(detection["patch_corners_px"])).astype(np.int32)
        cv2.polylines(overlay, [patch], True, (0, 255, 0), 2, cv2.LINE_AA)
        detected_centers = np.asarray(detection["centers_px"], dtype=np.float64)
        for center, radius in zip(detected_centers, detection["radii_px"]):
            center_px = tuple(np.rint(center).astype(int))
            cv2.circle(
                overlay,
                center_px,
                int(round(radius)),
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.drawMarker(overlay, center_px, (0, 255, 0), cv2.MARKER_CROSS, 18, 2)
        for candidate in detection["candidates"]:
            if "hough_center_px" not in candidate:
                continue
            hough_center = tuple(
                np.rint(np.asarray(candidate["hough_center_px"])).astype(int)
            )
            cv2.circle(
                overlay,
                hough_center,
                int(round(candidate["hough_radius_px"])),
                (255, 0, 0),
                1,
                cv2.LINE_AA,
            )
        frame_spread = np.ptp(
            np.asarray(
                [d["centers_px"] for _p, _i, d in detections], dtype=np.float64
            ),
            axis=0,
        )
        cv2.putText(
            overlay,
            f"{frame_path.stem} max_spread={float(np.max(frame_spread)):.2f}px",
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            "blue=Hough seed yellow=refined circle green=refined center",
            (24, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        output_path = overlay_dir / f"{frame_path.stem}_fiducials.png"
        assert cv2.imwrite(str(output_path), overlay)
        _logger.info("Overlay %s", output_path.resolve())

    np.testing.assert_allclose(median_centers, centers[0], atol=1.5)


def test_live_xy_aruco_fallback_handles_small_marker_frames():
    """The low-Z marker remains locatable when native ArUco misses it."""

    module = _module()
    for frame_name in (
        "02_t0_x195p000_z0p500.jpg",
        "03_t0_x197p000_z0p500.jpg",
    ):
        image = cv2.imread(str(LIVE_XY_FIXTURE / frame_name), cv2.IMREAD_COLOR)
        assert image is not None, f"could not decode {frame_name}"
        detection = module.detect_four_fiducials(image)
        assert detection["locator"]["marker_id"] == module.LOCATOR_MARKER_ID
        assert len(detection["centers_px"]) == 4
