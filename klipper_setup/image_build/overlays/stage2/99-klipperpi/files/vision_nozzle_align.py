#!/usr/bin/env python3
"""Manual IDEX nozzle vision sweep runner.

This is intentionally report-only. It captures fresh buffered T0 and T1 frames
across a small commanded X sweep, runs the same analysis path for every image,
and writes debug artifacts under /home/pi/printer_data/vision/nozzle_sweep/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"
VISION_DIR = Path(os.environ.get("VISION_OUTPUT_DIR", "/home/pi/printer_data/vision"))
NOZZLE_SWEEP_DIR = VISION_DIR / "nozzle_sweep"
VISION_URL_PREFIX = os.environ.get("VISION_OUTPUT_URL_PREFIX", "/vision").rstrip("/")
CAPTURE_BIN = os.environ.get("VISION_CAPTURE_BIN", "/usr/local/bin/vision_capture.py")
CROWSNEST_SERVICE = os.environ.get("VISION_CROWSNEST_SERVICE", "crowsnest")
CROWSNEST_HOST = os.environ.get("VISION_CROWSNEST_HOST", "127.0.0.1")
CROWSNEST_PORT = int(os.environ.get("VISION_CROWSNEST_PORT", "8080"))
WEBCAM_SNAPSHOT_URL = os.environ.get(
    "VISION_WEBCAM_SNAPSHOT_URL", "http://127.0.0.1/webcam/?action=snapshot"
)
WEBCAM_READY_TIMEOUT = float(os.environ.get("VISION_WEBCAM_READY_TIMEOUT", "25"))
RED_BASE_WIDTH = 1920.0
RED_BASE_HEIGHT = 1080.0
RED_MARKER_ROI_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_RED_ROI_1080", "920,330,260,190").split(",")
)
NOZZLE_FEATURE_OFFSET_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_SWEEP_FEATURE_OFFSET_1080", "25,100").split(",")
)
NOZZLE_ROI_SIZE_1080 = tuple(
    float(v)
    for v in os.environ.get("VISION_NOZZLE_SWEEP_ROI_SIZE_1080", "120,96").split(",")
)
NOZZLE_GLOBAL_MATCH_MARGIN_1080 = float(
    os.environ.get("VISION_NOZZLE_SWEEP_GLOBAL_MARGIN_1080", "36")
)
NOZZLE_GLOBAL_MATCH_SEARCH_1080 = float(
    os.environ.get("VISION_NOZZLE_SWEEP_MATCH_SEARCH_1080", "150")
)
PUBLIC_BASE_URL = os.environ.get("VISION_PUBLIC_BASE_URL", "http://menderpi.local")
NAME_REPLACEMENTS = str.maketrans({c: "_" for c in " /\\:;|?*[]{}()<>'\"`$&!"})


def sanitize_name(value: Any) -> str:
    text = str(value or "nozzle_align").translate(NAME_REPLACEMENTS).strip("._-")
    return (text or "nozzle_align")[:80]


def prefixed_vision_url(relative_path: str) -> str:
    if not VISION_URL_PREFIX:
        return "/" + relative_path.lstrip("/")
    return VISION_URL_PREFIX + "/" + relative_path.lstrip("/")


def vision_url(path: Path) -> str:
    return prefixed_vision_url(path.relative_to(VISION_DIR).as_posix())


def public_url(path_or_url: Path | str) -> str:
    if isinstance(path_or_url, Path):
        relative_url = vision_url(path_or_url)
    else:
        relative_url = path_or_url
    return PUBLIC_BASE_URL.rstrip("/") + "/" + relative_url.lstrip("/")


def console_respond(base_url: str, message: str) -> None:
    safe = message.replace("\\", "/").replace('"', "'")
    try:
        run_gcode(base_url, f'RESPOND TYPE=echo MSG="{safe}"', timeout=10)
    except Exception:
        pass


def parse_dx_values(value: str) -> list[float]:
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not values:
        raise ValueError("DX list is empty")
    return values


def dx_label(dx: float) -> str:
    return str(dx).replace("-", "m").replace(".", "p")


def moonraker_get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=15) as response:
        return json.loads(response.read())


def run_command(command: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def service_is_active(service: str) -> bool:
    result = run_command(["systemctl", "is-active", "--quiet", service], timeout=5)
    return result.returncode == 0


def stop_service(service: str) -> None:
    result = run_command(["systemctl", "stop", service], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"Could not stop {service}: {result.stderr.strip()}")


def reset_failed_service(service: str) -> None:
    run_command(["systemctl", "reset-failed", service], timeout=10)


def wait_for_tcp(host: str, port: int, timeout: float) -> float:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return round(timeout - max(0.0, deadline - time.monotonic()), 3)
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {host}:{port}: {last_error}")


def wait_for_webcam_snapshot(timeout: float) -> float:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(WEBCAM_SNAPSHOT_URL, timeout=3) as response:
                data = response.read(4)
            if data[:2] == b"\xff\xd8":
                return round(timeout - max(0.0, deadline - time.monotonic()), 3)
            last_error = RuntimeError("snapshot endpoint did not return a JPEG")
        except Exception as exc:
            last_error = exc
        time.sleep(0.75)
    raise RuntimeError(f"Timed out waiting for webcam snapshot: {last_error}")


def start_preview_service() -> dict[str, Any]:
    reset_failed_service(CROWSNEST_SERVICE)
    result = run_command(["systemctl", "start", CROWSNEST_SERVICE], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"Could not start {CROWSNEST_SERVICE}: {result.stderr.strip()}")
    return {
        "tcp_ready_after_s": wait_for_tcp(
            CROWSNEST_HOST, CROWSNEST_PORT, WEBCAM_READY_TIMEOUT
        ),
        "snapshot_ready_after_s": wait_for_webcam_snapshot(WEBCAM_READY_TIMEOUT),
    }


def run_gcode(base_url: str, script: str, *, timeout: float = 60.0) -> None:
    data = urllib.parse.urlencode({"script": script}).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/printer/gcode/script",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def query_status(base_url: str) -> dict[str, Any]:
    path = "/printer/objects/query?toolhead&gcode_move&webhooks&print_stats"
    return moonraker_get(base_url, path)["result"]["status"]


def wait_ready_and_idle(base_url: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = query_status(base_url)
        webhooks = status.get("webhooks", {})
        print_stats = status.get("print_stats", {})
        if webhooks.get("state") == "ready" and print_stats.get("state") in (
            "standby",
            "complete",
        ):
            return status
        time.sleep(0.5)
    raise TimeoutError("Printer did not become ready and idle")


def capture_once(name: str, fresh_after_utc: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            CAPTURE_BIN,
            "--capture-once",
            name,
            "--require-high-res",
            "--fresh-after-utc",
            fresh_after_utc,
            "--fresh-timeout",
            "12",
            "--retries",
            "5",
            "--no-crowsnest-management",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def copy_capture_artifacts_to_run(
    metadata: dict[str, Any], run_dir: Path, prefix: str
) -> dict[str, str]:
    image_source = Path(metadata["image_path"])
    meta_source = Path(metadata["metadata_path"])
    image_target = run_dir / f"{prefix}.jpg"
    meta_target = run_dir / f"{prefix}_capture.json"
    shutil.copy2(image_source, image_target)
    shutil.copy2(meta_source, meta_target)
    return {
        "image_path": str(image_target),
        "metadata_path": str(meta_target),
        "image_url": vision_url(image_target),
        "metadata_url": vision_url(meta_target),
    }


def scale_rect_1080(
    rect: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    return clamp_rect(
        x * width / RED_BASE_WIDTH,
        y * height / RED_BASE_HEIGHT,
        w * width / RED_BASE_WIDTH,
        h * height / RED_BASE_HEIGHT,
        width,
        height,
    )


def clamp_rect(
    x: float, y: float, w: float, h: float, width: int, height: int
) -> tuple[int, int, int, int]:
    ix = max(0, min(width - 1, int(round(x))))
    iy = max(0, min(height - 1, int(round(y))))
    iw = max(1, int(round(w)))
    ih = max(1, int(round(h)))
    if ix + iw > width:
        iw = max(1, width - ix)
    if iy + ih > height:
        ih = max(1, height - iy)
    return ix, iy, iw, ih


def point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def detect_red_marker(image: Any) -> dict[str, Any]:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    roi = scale_rect_1080(RED_MARKER_ROI_1080, width, height)
    x, y, w, h = roi
    crop = image[y : y + h, x : x + w]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask_low = cv2.inRange(hsv, np.array([0, 70, 35]), np.array([14, 255, 255]))
    mask_high = cv2.inRange(hsv, np.array([168, 70, 35]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(mask_low, mask_high)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scale = (width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT) / 2.0
    min_area = max(80.0, 160.0 * scale * scale)
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        cx = float(moments["m10"] / moments["m00"] + x)
        cy = float(moments["m01"] / moments["m00"] + y)
        bx, by, bw, bh = cv2.boundingRect(contour)
        candidates.append(
            {
                "center_px": [round(cx, 3), round(cy, 3)],
                "bbox": [int(bx + x), int(by + y), int(bw), int(bh)],
                "area": round(area, 3),
            }
        )
    candidates.sort(key=lambda item: item["area"], reverse=True)
    if not candidates:
        return {
            "accepted": False,
            "roi": list(roi),
            "rejection_reason": "no red marker blob found",
            "candidates": [],
        }
    best = candidates[0]
    return {
        "accepted": True,
        "roi": list(roi),
        "center_px": best["center_px"],
        "bbox": best["bbox"],
        "area": best["area"],
        "candidates": candidates[:5],
    }


def derive_nozzle_roi(
    red_marker: dict[str, Any], width: int, height: int
) -> tuple[int, int, int, int]:
    if not red_marker.get("accepted"):
        raise RuntimeError(
            "Cannot derive nozzle ROI because red marker detection was not accepted: "
            f"{red_marker.get('rejection_reason', 'unknown red marker failure')}"
        )
    center_x, center_y = red_marker["center_px"]
    offset_x = NOZZLE_FEATURE_OFFSET_1080[0] * width / RED_BASE_WIDTH
    offset_y = NOZZLE_FEATURE_OFFSET_1080[1] * height / RED_BASE_HEIGHT
    roi_w = NOZZLE_ROI_SIZE_1080[0] * width / RED_BASE_WIDTH
    roi_h = NOZZLE_ROI_SIZE_1080[1] * height / RED_BASE_HEIGHT
    start_x = center_x + offset_x - roi_w / 2.0
    start_y = center_y + offset_y - roi_h / 2.0
    return clamp_rect(start_x, start_y, roi_w, roi_h, width, height)


def detect_nozzle_candidates(image: Any, roi: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    x, y, w, h = roi
    crop = image[y : y + h, x : x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 1.2)
    scale = (width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT) / 2.0
    min_radius = max(5, int(round(8 * scale)))
    max_radius = max(14, int(round(35 * scale)))
    target_radius = 18.0 * scale
    candidates: list[dict[str, Any]] = []

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(14, int(round(22 * scale))),
        param1=90,
        param2=14,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is not None:
        for cx, cy, radius in np.round(circles[0, :]).astype(int):
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.circle(mask, (int(cx), int(cy)), max(int(radius) - 2, 1), 255, -1)
            mean_inside = float(cv2.mean(gray, mask=mask)[0])
            darkness = 255.0 - mean_inside
            candidates.append(
                {
                    "source": "hough",
                    "cx": float(cx + x),
                    "cy": float(cy + y),
                    "r": float(radius),
                    "mean_inside": round(mean_inside, 3),
                    "base_score": round(0.35 * darkness - 1.7 * abs(radius - target_radius), 3),
                }
            )

    _, dark = cv2.threshold(blur, 78, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((3, 3), np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 35 * scale * scale or area > 3800 * scale * scale:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0:
            continue
        circularity = 4.0 * math.pi * area / (perimeter * perimeter)
        if circularity < 0.28:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if radius < min_radius or radius > max_radius:
            continue
        mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        mean_inside = float(cv2.mean(gray, mask=mask)[0])
        darkness = 255.0 - mean_inside
        candidates.append(
            {
                "source": "dark_contour",
                "cx": float(cx + x),
                "cy": float(cy + y),
                "r": float(radius),
                "mean_inside": round(mean_inside, 3),
                "area": round(area, 3),
                "circularity": round(circularity, 3),
                "base_score": round(
                    0.42 * darkness
                    + 20.0 * circularity
                    - 1.8 * abs(radius - target_radius),
                    3,
                ),
            }
        )

    candidates.sort(key=lambda item: item["base_score"], reverse=True)
    return candidates[:12]


def derive_global_nozzle_roi(
    frames: list[dict[str, Any]], width: int, height: int
) -> tuple[int, int, int, int]:
    feature_boxes = []
    for frame in frames:
        red = frame.get("red_marker", {})
        feature_roi = derive_nozzle_roi(red, width, height)
        frame["feature_roi"] = list(feature_roi)
        fx, fy, fw, fh = feature_roi
        frame["expected_nozzle_feature_center_px"] = [
            round(fx + fw / 2.0, 3),
            round(fy + fh / 2.0, 3),
        ]
        feature_boxes.append(feature_roi)
    if not feature_boxes:
        raise RuntimeError("Cannot derive global nozzle ROI because no feature ROIs exist")
    margin = NOZZLE_GLOBAL_MATCH_MARGIN_1080 * (
        width / RED_BASE_WIDTH + height / RED_BASE_HEIGHT
    ) / 2.0
    left = min(box[0] for box in feature_boxes) - margin
    top = min(box[1] for box in feature_boxes) - margin
    right = max(box[0] + box[2] for box in feature_boxes) + margin
    bottom = max(box[1] + box[3] for box in feature_boxes) + margin
    return clamp_rect(left, top, right - left, bottom - top, width, height)


def normalized_registration_feature(image: Any, roi: tuple[int, int, int, int], mode: str) -> Any:
    import cv2

    x, y, w, h = roi
    crop = image[y : y + h, x : x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(gray)
    feature = clahe.astype("float32")
    if mode == "grad":
        grad_x = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
        feature = cv2.magnitude(grad_x, grad_y)
    mean = float(feature.mean())
    std = float(feature.std())
    return (feature - mean) / (std + 1.0e-6)


def match_registration_features(source_feature: Any, target_feature: Any, search_px: int) -> dict[str, Any]:
    import cv2

    padded = cv2.copyMakeBorder(
        source_feature,
        search_px,
        search_px,
        search_px,
        search_px,
        cv2.BORDER_CONSTANT,
        value=0,
    )
    result = cv2.matchTemplate(
        padded.astype("float32"),
        target_feature.astype("float32"),
        cv2.TM_CCOEFF_NORMED,
    )
    _min_value, max_value, _min_loc, max_loc = cv2.minMaxLoc(result)
    # matchTemplate returns where the target crop must be placed in the padded
    # source crop. The content displacement is the inverse of that placement.
    return {
        "dx": float(-(max_loc[0] - search_px)),
        "dy": float(-(max_loc[1] - search_px)),
        "correlation": float(max_value),
    }


def solve_pairwise_registration(
    records: list[dict[str, Any]], sign: float
) -> dict[str, Any] | None:
    import numpy as np

    if len(records) < 4:
        return None
    rows = []
    values = []
    weights = []
    for record in records:
        observed_dx = sign * float(record["observed_dx"])
        observed_dy = sign * float(record["observed_dy"])
        command_delta = float(record["target_command_dx"]) - float(
            record["source_command_dx"]
        )
        tool_delta = (
            (1.0 if record["target_tool"] == "t1" else 0.0)
            - (1.0 if record["source_tool"] == "t1" else 0.0)
        )
        rows.append([command_delta, 0.0, tool_delta, 0.0])
        values.append(observed_dx)
        weights.append(max(0.01, float(record["correlation"])))
        rows.append([0.0, command_delta, 0.0, tool_delta])
        values.append(observed_dy)
        weights.append(max(0.01, float(record["correlation"])))
    matrix = np.array(rows, dtype=float)
    vector = np.array(values, dtype=float)
    weight_matrix = np.diag(np.sqrt(np.array(weights, dtype=float)))
    solution = np.linalg.lstsq(weight_matrix @ matrix, weight_matrix @ vector, rcond=None)[0]

    residuals = []
    weighted_sum = 0.0
    weight_total = 0.0
    for record in records:
        observed = (
            sign * float(record["observed_dx"]),
            sign * float(record["observed_dy"]),
        )
        command_delta = float(record["target_command_dx"]) - float(
            record["source_command_dx"]
        )
        tool_delta = (
            (1.0 if record["target_tool"] == "t1" else 0.0)
            - (1.0 if record["source_tool"] == "t1" else 0.0)
        )
        predicted = (
            command_delta * float(solution[0]) + tool_delta * float(solution[2]),
            command_delta * float(solution[1]) + tool_delta * float(solution[3]),
        )
        distance = point_distance(observed, predicted)
        weight = max(0.01, float(record["correlation"]))
        weighted_sum += weight * distance * distance
        weight_total += weight
        residuals.append(
            {
                "source": record["source"],
                "target": record["target"],
                "observed_dx": round(observed[0], 3),
                "observed_dy": round(observed[1], 3),
                "predicted_dx": round(predicted[0], 3),
                "predicted_dy": round(predicted[1], 3),
                "residual_px": round(distance, 3),
                "correlation": round(float(record["correlation"]), 4),
            }
        )
    weighted_rms = math.sqrt(weighted_sum / max(1.0e-9, weight_total))
    return {
        "axis_vector_px_per_mm": [float(solution[0]), float(solution[1])],
        "t1_minus_t0_pixels": [float(solution[2]), float(solution[3])],
        "residual_rms_px": float(weighted_rms),
        "residuals": residuals,
    }


def fit_global_roi_cross_match(
    frames: list[dict[str, Any]],
    global_roi: tuple[int, int, int, int],
    red_axis_vector: tuple[float, float] | None,
) -> dict[str, Any]:
    import cv2

    search_px = max(
        8,
        int(
            round(
                NOZZLE_GLOBAL_MATCH_SEARCH_1080
                * (
                    frames[0].get("image_width", RED_BASE_WIDTH) / RED_BASE_WIDTH
                    + frames[0].get("image_height", RED_BASE_HEIGHT) / RED_BASE_HEIGHT
                )
                / 2.0
            )
        )
        if frames
        else int(round(NOZZLE_GLOBAL_MATCH_SEARCH_1080)),
    )
    items = []
    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            continue
        items.append(
            {
                "frame": frame,
                "gray": normalized_registration_feature(image, global_roi, "gray"),
                "grad": normalized_registration_feature(image, global_roi, "grad"),
            }
        )
    if len(items) < 4:
        return {
            "accepted": False,
            "rejection_reason": "need at least four readable frames for cross-match",
        }

    dx_values = sorted({float(item["frame"]["dx"]) for item in items})
    dx_steps = [
        dx_values[index + 1] - dx_values[index]
        for index in range(len(dx_values) - 1)
        if dx_values[index + 1] > dx_values[index]
    ]
    max_cross_tool_command_delta = min(dx_steps) if dx_steps else 0.0

    candidates = []
    for mode in ("gray", "grad"):
        pairwise_rows = []
        usable_records = []
        usable_same_tool = 0
        usable_cross_tool = 0
        for source_item in items:
            source_frame = source_item["frame"]
            row = {"source": source_frame["prefix"], "matches": []}
            for target_item in items:
                target_frame = target_item["frame"]
                if source_frame is target_frame:
                    row["matches"].append(
                        {
                            "target": target_frame["prefix"],
                            "dx": 0.0,
                            "dy": 0.0,
                            "correlation": 1.0,
                            "used": False,
                        }
                    )
                    continue
                match = match_registration_features(
                    source_item[mode], target_item[mode], search_px
                )
                same_tool = source_frame["tool"] == target_frame["tool"]
                threshold = 0.42 if same_tool else 0.16
                command_delta = abs(float(target_frame["dx"]) - float(source_frame["dx"]))
                useful_cross_tool_pair = (
                    same_tool
                    or command_delta <= max_cross_tool_command_delta + 1.0e-6
                )
                used = match["correlation"] >= threshold and useful_cross_tool_pair
                if used:
                    record = {
                        "source": source_frame["prefix"],
                        "target": target_frame["prefix"],
                        "source_tool": source_frame["tool"],
                        "target_tool": target_frame["tool"],
                        "source_command_dx": source_frame["dx"],
                        "target_command_dx": target_frame["dx"],
                        "observed_dx": match["dx"],
                        "observed_dy": match["dy"],
                        "correlation": match["correlation"],
                    }
                    usable_records.append(record)
                    if same_tool:
                        usable_same_tool += 1
                    else:
                        usable_cross_tool += 1
                row["matches"].append(
                    {
                        "target": target_frame["prefix"],
                        "dx": round(match["dx"], 3),
                        "dy": round(match["dy"], 3),
                        "correlation": round(match["correlation"], 4),
                        "used": used,
                    }
                )
            pairwise_rows.append(row)

        for sign in (1.0, -1.0):
            fit = solve_pairwise_registration(usable_records, sign)
            if fit is None:
                continue
            axis = fit["axis_vector_px_per_mm"]
            axis_len = math.hypot(axis[0], axis[1])
            red_alignment = None
            red_ratio_penalty = 0.0
            if red_axis_vector and axis_len > 0:
                red_len = math.hypot(red_axis_vector[0], red_axis_vector[1])
                if red_len > 0:
                    red_alignment = (
                        axis[0] * red_axis_vector[0] + axis[1] * red_axis_vector[1]
                    ) / (axis_len * red_len)
                    red_ratio_penalty = abs(axis_len - red_len) / red_len
            if red_alignment is not None and red_alignment < 0:
                direction_penalty = 1000.0
            else:
                direction_penalty = 0.0
            score = (
                float(fit["residual_rms_px"])
                + direction_penalty
                + 3.0 * red_ratio_penalty
                + (0.15 if mode == "grad" else 0.0)
            )
            correlations = [float(record["correlation"]) for record in usable_records]
            correlations_sorted = sorted(correlations)
            median_corr = correlations_sorted[len(correlations_sorted) // 2] if correlations else 0.0
            candidates.append(
                {
                    **fit,
                    "feature_mode": mode,
                    "sign": sign,
                    "score": round(score, 4),
                    "red_axis_alignment": (
                        round(red_alignment, 4) if red_alignment is not None else None
                    ),
                    "usable_pair_count": len(usable_records),
                    "usable_same_tool_pair_count": usable_same_tool,
                    "usable_cross_tool_pair_count": usable_cross_tool,
                    "rejected_pair_count": len(items) * (len(items) - 1) - len(usable_records),
                    "correlation_min": round(min(correlations), 4) if correlations else None,
                    "correlation_median": round(median_corr, 4) if correlations else None,
                    "pairwise_match_matrix": pairwise_rows,
                }
            )

    if not candidates:
        return {
            "accepted": False,
            "rejection_reason": "no usable cross-match model could be fitted",
            "global_roi": list(global_roi),
            "search_px": search_px,
        }

    best = min(candidates, key=lambda item: item["score"])
    axis = best["axis_vector_px_per_mm"]
    delta = best["t1_minus_t0_pixels"]
    axis_len = math.hypot(axis[0], axis[1])
    accepted = (
        best["usable_pair_count"] >= 12
        and best["usable_same_tool_pair_count"] >= 6
        and best["usable_cross_tool_pair_count"] >= 4
        and best["residual_rms_px"] <= 4.0
        and axis_len >= 1.0
    )
    if axis_len > 0:
        ux, uy = axis[0] / axis_len, axis[1] / axis_len
        px, py = -uy, ux
        along_x_px = delta[0] * ux + delta[1] * uy
        perpendicular_px = delta[0] * px + delta[1] * py
    else:
        along_x_px = 0.0
        perpendicular_px = 0.0
    reference_points = []
    for frame in frames:
        expected = frame.get("expected_nozzle_feature_center_px")
        if not expected:
            continue
        tool_index = 1.0 if frame["tool"] == "t1" else 0.0
        reference_points.append(
            (
                float(expected[0]) - float(frame["dx"]) * axis[0] - tool_index * delta[0],
                float(expected[1]) - float(frame["dx"]) * axis[1] - tool_index * delta[1],
            )
        )
    reference_center = None
    if reference_points:
        reference_center = (
            sum(point[0] for point in reference_points) / len(reference_points),
            sum(point[1] for point in reference_points) / len(reference_points),
        )
        for frame in frames:
            tool_index = 1.0 if frame["tool"] == "t1" else 0.0
            predicted = (
                reference_center[0] + float(frame["dx"]) * axis[0] + tool_index * delta[0],
                reference_center[1] + float(frame["dx"]) * axis[1] + tool_index * delta[1],
            )
            frame["registration_prediction_center_px"] = [
                round(predicted[0], 3),
                round(predicted[1], 3),
            ]
    if not accepted:
        reason = (
            "cross-match fit did not meet pair-count/residual thresholds: "
            f"pairs={best['usable_pair_count']}, rms={best['residual_rms_px']:.2f}px"
        )
    else:
        reason = ""
    return {
        **best,
        "accepted": accepted,
        "rejection_reason": reason,
        "global_roi": list(global_roi),
        "search_px": search_px,
        "axis_vector_px_per_mm": [round(axis[0], 4), round(axis[1], 4)],
        "axis_px_per_mm": round(axis_len, 4),
        "axis_angle_deg": round(math.degrees(math.atan2(axis[1], axis[0])), 4)
        if axis_len > 0
        else None,
        "t1_minus_t0_pixels": [round(delta[0], 4), round(delta[1], 4)],
        "along_x_px": round(along_x_px, 4),
        "along_x_mm_approx": round(along_x_px / axis_len, 5) if axis_len > 0 else None,
        "perpendicular_px": round(perpendicular_px, 4),
        "perpendicular_mm_approx": round(perpendicular_px / axis_len, 5)
        if axis_len > 0
        else None,
        "reference_center_px": [round(reference_center[0], 4), round(reference_center[1], 4)]
        if reference_center
        else None,
        "residual_rms_px": round(float(best["residual_rms_px"]), 4),
        "measurement_source": "global_roi_cross_match",
    }


def fit_points_by_dx(samples: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [sample for sample in samples if sample.get("point_px")]
    if len(usable) < 2:
        return {"ok": False, "rejection_reason": "need at least two points"}
    dxs = [float(sample["dx"]) for sample in usable]
    xs = [float(sample["point_px"][0]) for sample in usable]
    ys = [float(sample["point_px"][1]) for sample in usable]
    mean_dx = sum(dxs) / len(dxs)
    denom = sum((dx - mean_dx) ** 2 for dx in dxs)
    if denom <= 0:
        return {"ok": False, "rejection_reason": "dx values do not vary"}
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    vx = sum((dx - mean_dx) * (px - mean_x) for dx, px in zip(dxs, xs)) / denom
    vy = sum((dx - mean_dx) * (py - mean_y) for dx, py in zip(dxs, ys)) / denom
    ix = mean_x - vx * mean_dx
    iy = mean_y - vy * mean_dx
    residuals = [
        point_distance((px, py), (ix + dx * vx, iy + dx * vy))
        for dx, px, py in zip(dxs, xs, ys)
    ]
    rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    px_per_mm = math.hypot(vx, vy)
    return {
        "ok": True,
        "count": len(usable),
        "intercept_px": [round(ix, 3), round(iy, 3)],
        "vector_px_per_mm": [round(vx, 3), round(vy, 3)],
        "px_per_mm": round(px_per_mm, 3),
        "axis_angle_deg": round(math.degrees(math.atan2(vy, vx)), 3),
        "residual_rms_px": round(rms, 3),
        "residuals_px": [round(value, 3) for value in residuals],
    }


def average_axis_vector(fits: dict[str, dict[str, Any]]) -> tuple[float, float] | None:
    vectors = [
        fit["vector_px_per_mm"]
        for fit in fits.values()
        if fit.get("ok") and fit.get("px_per_mm", 0) > 1
    ]
    if not vectors:
        return None
    return (
        sum(float(vector[0]) for vector in vectors) / len(vectors),
        sum(float(vector[1]) for vector in vectors) / len(vectors),
    )


def choose_motion_consistent_nozzle(
    frames: list[dict[str, Any]], axis_vector: tuple[float, float] | None
) -> dict[str, Any]:
    if axis_vector is None:
        return {
            "accepted": False,
            "confidence": 0.0,
            "rejection_reason": "no stable red-marker motion vector",
        }
    vx, vy = axis_vector
    scale = 1.0
    if frames:
        scale = (
            frames[0].get("image_width", RED_BASE_WIDTH) / RED_BASE_WIDTH
            + frames[0].get("image_height", RED_BASE_HEIGHT) / RED_BASE_HEIGHT
        ) / 2.0
    cluster_radius = 22.0 * scale
    residual_limit = 18.0 * scale
    members: list[dict[str, Any]] = []
    for frame in frames:
        for candidate in frame.get("nozzle_candidates", []):
            dx = float(frame["dx"])
            intercept = (candidate["cx"] - dx * vx, candidate["cy"] - dx * vy)
            members.append(
                {
                    "dx": dx,
                    "dx_label": frame["dx_label"],
                    "candidate": candidate,
                    "intercept": intercept,
                }
            )
    if not members:
        return {
            "accepted": False,
            "confidence": 0.0,
            "rejection_reason": "no nozzle candidates in red-marker ROI",
        }

    best_cluster: list[dict[str, Any]] = []
    best_score = -1.0e9
    for seed in members:
        cluster = [
            member
            for member in members
            if point_distance(member["intercept"], seed["intercept"]) <= cluster_radius
        ]
        distinct_dx = {member["dx_label"] for member in cluster}
        if len(distinct_dx) < 2:
            continue
        score = (
            130.0 * len(distinct_dx)
            + sum(float(member["candidate"].get("base_score", 0.0)) for member in cluster)
            / max(1, len(cluster))
        )
        if score > best_score:
            best_score = score
            best_cluster = cluster

    if not best_cluster:
        return {
            "accepted": False,
            "confidence": 0.0,
            "rejection_reason": "no candidate cluster followed the commanded X motion",
        }

    selected_by_dx: dict[str, dict[str, Any]] = {}
    for member in best_cluster:
        label = member["dx_label"]
        current = selected_by_dx.get(label)
        if current is None or member["candidate"].get("base_score", 0) > current.get(
            "base_score", -1.0e9
        ):
            selected_by_dx[label] = member["candidate"]

    intercepts = []
    residuals = []
    for frame in frames:
        candidate = selected_by_dx.get(frame["dx_label"])
        if not candidate:
            continue
        dx = float(frame["dx"])
        intercepts.append((candidate["cx"] - dx * vx, candidate["cy"] - dx * vy))
    ix = sum(point[0] for point in intercepts) / len(intercepts)
    iy = sum(point[1] for point in intercepts) / len(intercepts)
    for frame in frames:
        candidate = selected_by_dx.get(frame["dx_label"])
        if not candidate:
            continue
        dx = float(frame["dx"])
        predicted = (ix + dx * vx, iy + dx * vy)
        residuals.append(point_distance((candidate["cx"], candidate["cy"]), predicted))
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    accepted = len(selected_by_dx) >= 2 and rms <= residual_limit
    confidence = max(
        0.0,
        min(1.0, 0.22 + 0.2 * len(selected_by_dx) - rms / max(1.0, 80.0 * scale)),
    )
    if not accepted:
        reason = f"candidate residual {rms:.1f}px exceeds {residual_limit:.1f}px"
    else:
        reason = ""
    return {
        "accepted": accepted,
        "confidence": round(confidence, 4),
        "intercept_px": [round(ix, 3), round(iy, 3)],
        "selected_by_dx": {
            label: {
                **candidate,
                "cx": round(candidate["cx"], 3),
                "cy": round(candidate["cy"], 3),
                "r": round(candidate["r"], 3),
            }
            for label, candidate in selected_by_dx.items()
        },
        "selected_count": len(selected_by_dx),
        "residual_rms_px": round(rms, 3),
        "residuals_px": [round(value, 3) for value in residuals],
        "rejection_reason": reason,
    }


def annotate_sweep_frame(
    image: Any,
    frame: dict[str, Any],
    nozzle_result: dict[str, Any] | None,
    axis_vector: tuple[float, float] | None,
) -> Any:
    import cv2

    overlay = image.copy()
    red = frame.get("red_marker", {})
    red_roi = red.get("roi")
    if red_roi:
        x, y, w, h = red_roi
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 180, 0), 2)
    if red.get("accepted"):
        bx, by, bw, bh = red["bbox"]
        cx, cy = red["center_px"]
        cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
        cv2.drawMarker(
            overlay,
            (int(round(cx)), int(round(cy))),
            (0, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=28,
            thickness=2,
        )
    if frame.get("global_nozzle_roi"):
        gx, gy, gw, gh = frame["global_nozzle_roi"]
        cv2.rectangle(overlay, (gx, gy), (gx + gw, gy + gh), (0, 220, 255), 2)
    nozzle_roi = frame.get("feature_roi") or frame.get("nozzle_roi")
    if nozzle_roi:
        nx, ny, nw, nh = nozzle_roi
        cv2.rectangle(overlay, (nx, ny), (nx + nw, ny + nh), (255, 255, 0), 2)
    expected = frame.get("expected_nozzle_feature_center_px")
    if expected:
        cv2.drawMarker(
            overlay,
            (int(round(expected[0])), int(round(expected[1]))),
            (255, 255, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=18,
            thickness=2,
        )
    selected = None
    predicted_center = frame.get("registration_prediction_center_px")
    if predicted_center:
        predicted = (int(round(predicted_center[0])), int(round(predicted_center[1])))
        marker_size = max(18, int(round(28 * image.shape[1] / RED_BASE_WIDTH)))
        half_box = max(20, int(round(34 * image.shape[1] / RED_BASE_WIDTH)))
        cv2.rectangle(
            overlay,
            (predicted[0] - half_box, predicted[1] - half_box),
            (predicted[0] + half_box, predicted[1] + half_box),
            (255, 0, 255),
            2,
        )
        cv2.drawMarker(
            overlay,
            predicted,
            (255, 0, 255),
            markerType=cv2.MARKER_TILTED_CROSS,
            markerSize=marker_size,
            thickness=2,
        )
    label = f"{frame['tool'].upper()} dx={frame['dx']:.3g}mm"
    if nozzle_result and nozzle_result.get("measurement_source") == "global_roi_cross_match":
        label += " global-ROI cross-match"
    else:
        label += " nozzle=rejected"
    cv2.rectangle(overlay, (0, 0), (780, 48), (0, 0, 0), -1)
    cv2.putText(
        overlay,
        label,
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
    )
    return overlay


def crop_for_contact_tile(image: Any, frame: dict[str, Any]) -> Any:
    height, width = image.shape[:2]
    boxes = []
    red = frame.get("red_marker", {})
    if red.get("accepted"):
        boxes.append(red["bbox"])
    nozzle_roi = frame.get("feature_roi") or frame.get("nozzle_roi")
    if nozzle_roi:
        boxes.append(nozzle_roi)
    if frame.get("global_nozzle_roi"):
        boxes.append(frame["global_nozzle_roi"])
    red_roi = red.get("roi")
    if red_roi:
        boxes.append(red_roi)
    if not boxes:
        boxes.append((0, 0, width, height))
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    pad_x = int(round(140 * width / RED_BASE_WIDTH))
    pad_y = int(round(105 * height / RED_BASE_HEIGHT))
    x, y, w, h = clamp_rect(
        left - pad_x,
        top - pad_y,
        (right - left) + 2 * pad_x,
        (bottom - top) + 2 * pad_y,
        width,
        height,
    )
    return image[y : y + h, x : x + w]


def letterbox(image: Any, tile_w: int, tile_h: int) -> Any:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = min(tile_w / width, tile_h / height)
    resized_w = max(1, int(round(width * scale)))
    resized_h = max(1, int(round(height * scale)))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((tile_h, tile_w, 3), 245, dtype=np.uint8)
    x = (tile_w - resized_w) // 2
    y = (tile_h - resized_h) // 2
    canvas[y : y + resized_h, x : x + resized_w] = resized
    return canvas


def draw_text_lines(
    canvas: Any,
    lines: list[str],
    origin: tuple[int, int],
    *,
    line_height: int = 26,
    scale: float = 0.62,
    color: tuple[int, int, int] = (20, 20, 20),
) -> None:
    import cv2

    x, y = origin
    for index, line in enumerate(lines):
        cv2.putText(
            canvas,
            line,
            (x, y + index * line_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            2,
            cv2.LINE_AA,
        )


def write_contact_sheet(
    frames: list[dict[str, Any]], analysis: dict[str, Any], contact_sheet_path: Path
) -> None:
    import cv2
    import numpy as np

    tile_w, tile_h = 540, 405
    dx_labels = [dx_label(float(dx)) for dx in analysis["dx_values"]]
    cols, rows = max(1, len(dx_labels)), 2
    summary_h = 345
    sheet = np.full((rows * tile_h + summary_h, cols * tile_w, 3), 255, dtype=np.uint8)
    frame_by_key = {(frame["tool"], frame["dx_label"]): frame for frame in frames}
    for row, tool in enumerate(("t0", "t1")):
        for col, label in enumerate(dx_labels):
            frame = frame_by_key.get((tool, label))
            if not frame:
                continue
            overlay = cv2.imread(frame["overlay_path"])
            if overlay is None:
                overlay = cv2.imread(frame["image_path"])
            crop = crop_for_contact_tile(overlay, frame)
            tile = letterbox(crop, tile_w, tile_h)
            y = row * tile_h
            x = col * tile_w
            sheet[y : y + tile_h, x : x + tile_w] = tile
            cv2.rectangle(sheet, (x, y), (x + tile_w - 1, y + tile_h - 1), (80, 80, 80), 2)

    summary_lines = [
        f"IDEX nozzle vision sweep: {analysis['run_name']}",
        f"report: {public_url(contact_sheet_path)}",
        "measurement: global ROI cross-match; red marker is locator only",
    ]
    red_axis = analysis.get("red_axis_vector_px_per_mm")
    if red_axis:
        summary_lines.append(
            "red-marker image X axis: "
            f"vx={red_axis[0]:.3f}px/mm, vy={red_axis[1]:.3f}px/mm, "
            f"|v|={analysis['red_axis_px_per_mm']:.3f}px/mm, "
            f"angle={analysis['red_axis_angle_deg']:.3f}deg"
        )
    cross = analysis.get("cross_match", {})
    if cross:
        summary_lines.append(
            "cross-match image X axis: "
            f"vx={cross.get('axis_vector_px_per_mm', [None, None])[0]}px/mm, "
            f"vy={cross.get('axis_vector_px_per_mm', [None, None])[1]}px/mm, "
            f"|v|={cross.get('axis_px_per_mm')}px/mm, "
            f"angle={cross.get('axis_angle_deg')}deg"
        )
        summary_lines.append(
            "cross-match quality: "
            f"mode={cross.get('feature_mode')} pairs={cross.get('usable_pair_count')} "
            f"same={cross.get('usable_same_tool_pair_count')} "
            f"cross={cross.get('usable_cross_tool_pair_count')} "
            f"rms={cross.get('residual_rms_px')}px "
            f"corr_med={cross.get('correlation_median')}"
        )
    for tool in ("t0", "t1"):
        fit = analysis.get("red_marker_fits", {}).get(tool, {})
        summary_lines.append(
            f"{tool.upper()} red fit: ok={fit.get('ok')} "
            f"intercept={fit.get('intercept_px')} rms={fit.get('residual_rms_px')}"
        )
    red_delta = analysis.get("red_marker_delta_t1_minus_t0") or {}
    summary_lines.append(
        "red locator T1-T0 sanity: "
        f"dx={red_delta.get('dx')} dy={red_delta.get('dy')} "
        f"alongX={red_delta.get('along_axis_mm_approx')}mm"
    )
    nozzle_delta = analysis.get("nozzle_delta_t1_minus_t0") or {}
    summary_lines.append(
        "nozzle-image T1-T0: "
        f"dx={nozzle_delta.get('dx')} dy={nozzle_delta.get('dy')} "
        f"alongX={nozzle_delta.get('along_x_mm_approx')}mm "
        f"perp={nozzle_delta.get('perpendicular_mm_approx')}mm"
    )
    if not analysis.get("ok"):
        failures = analysis.get("hard_failures") or [cross.get("rejection_reason", "rejected")]
        summary_lines.append(f"STATUS: FAILED; {'; '.join(str(item) for item in failures[:3])}")
    else:
        summary_lines.append("STATUS: global ROI cross-match accepted.")

    summary_y = rows * tile_h + 35
    cv2.rectangle(sheet, (0, rows * tile_h), (cols * tile_w, sheet.shape[0]), (238, 238, 238), -1)
    draw_text_lines(sheet, summary_lines, (24, summary_y), line_height=27, scale=0.58)
    cv2.imwrite(str(contact_sheet_path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def update_sweep_latest_links(
    run_dir: Path, result_path: Path, contact_sheet_path: Path | None
) -> None:
    NOZZLE_SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    links = [(result_path, "latest_result.json"), (run_dir, "latest")]
    if contact_sheet_path:
        links.append((contact_sheet_path, "latest_contact_sheet.jpg"))
    for target, name in links:
        latest = NOZZLE_SWEEP_DIR / name
        tmp = NOZZLE_SWEEP_DIR / f".{name}.tmp"
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        os.symlink(target.relative_to(NOZZLE_SWEEP_DIR), tmp)
        os.replace(tmp, latest)


def analyze_sweep_frames(frames: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - depends on Pi package install
        return {
            "ok": False,
            "proxy_only": True,
            "error": f"OpenCV import failed: {exc}",
        }

    hard_failures: list[str] = []
    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            frame["analysis_error"] = f"Could not read {frame['image_path']}"
            hard_failures.append(
                f"{frame['tool']} dx={frame['dx']}: {frame['analysis_error']}"
            )
            continue
        height, width = image.shape[:2]
        frame["image_width"] = width
        frame["image_height"] = height
        red = detect_red_marker(image)
        frame["red_marker"] = red
        if not red.get("accepted"):
            reason = red.get("rejection_reason", "red marker detection failed")
            frame["analysis_error"] = reason
            hard_failures.append(f"{frame['tool']} dx={frame['dx']}: {reason}")
            continue
        try:
            nozzle_roi = derive_nozzle_roi(red, width, height)
        except RuntimeError as exc:
            frame["analysis_error"] = str(exc)
            hard_failures.append(f"{frame['tool']} dx={frame['dx']}: {exc}")
            continue
        frame["nozzle_roi"] = list(nozzle_roi)
        frame["feature_roi"] = list(nozzle_roi)
        candidates = detect_nozzle_candidates(image, nozzle_roi)
        frame["nozzle_candidates"] = candidates
        if not candidates:
            reason = "no nozzle candidates found in red-marker-derived ROI"
            frame["analysis_error"] = reason
            hard_failures.append(f"{frame['tool']} dx={frame['dx']}: {reason}")

    red_marker_fits: dict[str, dict[str, Any]] = {}
    for tool in ("t0", "t1"):
        samples = [
            {
                "dx": frame["dx"],
                "point_px": frame.get("red_marker", {}).get("center_px"),
            }
            for frame in frames
            if frame["tool"] == tool
        ]
        red_marker_fits[tool] = fit_points_by_dx(samples)
        if not red_marker_fits[tool].get("ok"):
            hard_failures.append(
                f"{tool}: red marker fit failed: "
                f"{red_marker_fits[tool].get('rejection_reason', 'unknown fit failure')}"
            )

    red_axis_vector = average_axis_vector(red_marker_fits)
    if red_axis_vector is None:
        hard_failures.append("red marker image X axis could not be fit for both tools")
    red_axis_px_per_mm = math.hypot(*(red_axis_vector or (0.0, 0.0)))
    red_axis_angle = (
        math.degrees(math.atan2(red_axis_vector[1], red_axis_vector[0]))
        if red_axis_vector
        else None
    )

    analysis_frames = [
        frame
        for frame in frames
        if frame.get("image_width")
        and frame.get("image_height")
        and frame.get("red_marker", {}).get("accepted")
        and frame.get("nozzle_candidates")
    ]
    global_roi = None
    if analysis_frames:
        try:
            global_roi = derive_global_nozzle_roi(
                analysis_frames,
                int(analysis_frames[0]["image_width"]),
                int(analysis_frames[0]["image_height"]),
            )
        except RuntimeError as exc:
            hard_failures.append(str(exc))
    else:
        hard_failures.append("no readable frames passed red marker and nozzle-candidate gates")
    if global_roi:
        for frame in analysis_frames:
            frame["global_nozzle_roi"] = list(global_roi)

    if hard_failures:
        cross_match = {
            "accepted": False,
            "rejection_reason": "; ".join(hard_failures),
        }
    elif global_roi and red_axis_vector:
        cross_match = fit_global_roi_cross_match(analysis_frames, global_roi, red_axis_vector)
        if not cross_match.get("accepted"):
            hard_failures.append(
                "global ROI cross-match failed: "
                f"{cross_match.get('rejection_reason', 'unknown cross-match failure')}"
            )
    else:
        reason = "no global ROI or red marker axis could be derived"
        hard_failures.append(reason)
        cross_match = {"accepted": False, "rejection_reason": reason}

    for frame in frames:
        image = cv2.imread(frame["image_path"])
        if image is None:
            continue
        overlay = annotate_sweep_frame(image, frame, cross_match, red_axis_vector)
        overlay_path = run_dir / f"{frame['prefix']}_overlay.jpg"
        cv2.imwrite(str(overlay_path), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        frame["overlay_path"] = str(overlay_path)
        frame["overlay_url"] = vision_url(overlay_path)

    red_delta = None
    if red_marker_fits.get("t0", {}).get("ok") and red_marker_fits.get("t1", {}).get("ok"):
        t0 = red_marker_fits["t0"]["intercept_px"]
        t1 = red_marker_fits["t1"]["intercept_px"]
        dx = float(t1[0]) - float(t0[0])
        dy = float(t1[1]) - float(t0[1])
        red_delta = {"dx": round(dx, 3), "dy": round(dy, 3), "distance": round(math.hypot(dx, dy), 3)}
        if red_axis_vector and red_axis_px_per_mm > 0:
            ux, uy = (
                red_axis_vector[0] / red_axis_px_per_mm,
                red_axis_vector[1] / red_axis_px_per_mm,
            )
            red_delta["along_axis_mm_approx"] = round(
                (dx * ux + dy * uy) / red_axis_px_per_mm, 4
            )

    nozzle_delta = None
    if cross_match.get("accepted") and cross_match.get("t1_minus_t0_pixels"):
        dx, dy = cross_match["t1_minus_t0_pixels"]
        nozzle_delta = {
            "dx": round(dx, 3),
            "dy": round(dy, 3),
            "distance": round(math.hypot(dx, dy), 3),
            "along_x_px": cross_match.get("along_x_px"),
            "along_x_mm_approx": cross_match.get("along_x_mm_approx"),
            "perpendicular_px": cross_match.get("perpendicular_px"),
            "perpendicular_mm_approx": cross_match.get("perpendicular_mm_approx"),
            "measurement_source": "global_roi_cross_match",
        }

    if nozzle_delta:
        message = "Global ROI cross-match accepted."
    else:
        message = (
            "Nozzle vision sweep failed hard: " + "; ".join(hard_failures)
            if hard_failures
            else "Nozzle vision sweep rejected: global ROI cross-match was not reliable enough."
        )

    return {
        "ok": bool(nozzle_delta),
        "proxy_only": not bool(nozzle_delta),
        "hard_failures": hard_failures,
        "red_marker_fits": red_marker_fits,
        "red_axis_vector_px_per_mm": [round(red_axis_vector[0], 3), round(red_axis_vector[1], 3)] if red_axis_vector else None,
        "red_axis_px_per_mm": round(red_axis_px_per_mm, 3) if red_axis_vector else None,
        "red_axis_angle_deg": round(red_axis_angle, 3) if red_axis_angle is not None else None,
        "global_nozzle_roi": list(global_roi) if global_roi else None,
        "cross_match": cross_match,
        "red_marker_delta_t1_minus_t0": red_delta,
        "nozzle_delta_t1_minus_t0": nozzle_delta,
        "message": message,
    }


def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc)
    run_name = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{sanitize_name(args.name)}"
    run_dir = NOZZLE_SWEEP_DIR / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "result.json"
    contact_sheet_path = run_dir / "contact_sheet.jpg"
    dx_values = parse_dx_values(args.dx)
    result: dict[str, Any] = {
        "ok": False,
        "timestamp_utc": timestamp.isoformat(),
        "run_name": run_name,
        "target_gcode_position": {"x": args.x, "y": args.y, "z": args.z},
        "dx_values": dx_values,
        "report_only": True,
        "offsets_applied": False,
        "camera_source": "vision_framebuffer",
        "crowsnest_managed": False,
        "run_dir": str(run_dir),
        "run_url": vision_url(run_dir),
        "result_url": vision_url(result_path),
        "contact_sheet_url": vision_url(contact_sheet_path),
        "contact_sheet_public_url": public_url(contact_sheet_path),
        "latest_contact_sheet_url": vision_url(
            NOZZLE_SWEEP_DIR / "latest_contact_sheet.jpg"
        ),
        "latest_contact_sheet_public_url": public_url(
            vision_url(NOZZLE_SWEEP_DIR / "latest_contact_sheet.jpg")
        ),
    }

    frames: list[dict[str, Any]] = []
    try:
        status = wait_ready_and_idle(args.moonraker_url, args.ready_timeout)
        if "x" not in status["toolhead"].get("homed_axes", ""):
            raise RuntimeError("X is not homed")
        if "y" not in status["toolhead"].get("homed_axes", ""):
            raise RuntimeError("Y is not homed")
        if "z" not in status["toolhead"].get("homed_axes", ""):
            raise RuntimeError("Z is not homed")

        original_extruder = status["toolhead"].get("extruder", "extruder")
        original_position = status["gcode_move"].get(
            "gcode_position", [args.x, args.y, args.z, 0]
        )
        result["original"] = {
            "extruder": original_extruder,
            "gcode_position": original_position,
        }
        result["crowsnest_was_active"] = service_is_active(CROWSNEST_SERVICE)

        for tool, macro in (("t0", "T0"), ("t1", "T1")):
            for dx in dx_values:
                x_target = args.x + dx
                prefix = f"{tool}_dx{dx_label(dx)}"
                run_gcode(
                    args.moonraker_url,
                    (
                        f"{macro}\n"
                        "G90\n"
                        f"G1 X{x_target:.3f} Y{args.y:.3f} Z{args.z:.3f} "
                        f"F{args.feedrate:.0f}\n"
                        "M400"
                    ),
                )
                time.sleep(args.settle_time)
                fresh_after_utc = datetime.now(timezone.utc).isoformat()
                capture_name = f"{run_name}_{prefix}"
                capture = capture_once(capture_name, fresh_after_utc)
                artifacts = copy_capture_artifacts_to_run(capture, run_dir, prefix)
                frames.append(
                    {
                        "tool": tool,
                        "macro": macro,
                        "dx": dx,
                        "dx_label": dx_label(dx),
                        "prefix": prefix,
                        "target_gcode_position": {
                            "x": round(x_target, 4),
                            "y": args.y,
                            "z": args.z,
                        },
                        "capture": capture,
                        "image_path": artifacts["image_path"],
                        "metadata_path": artifacts["metadata_path"],
                        "image_url": artifacts["image_url"],
                        "metadata_url": artifacts["metadata_url"],
                    }
                )

        analysis = analyze_sweep_frames(frames, run_dir)
        analysis.update({"run_name": run_name, "dx_values": dx_values})
        result["frames"] = frames
        result["analysis"] = analysis
        result["ok"] = bool(analysis.get("ok"))
        result["proxy_only"] = bool(analysis.get("proxy_only"))
        result["message"] = analysis.get("message")
        if frames:
            write_contact_sheet(frames, analysis, contact_sheet_path)
            result["contact_sheet_path"] = str(contact_sheet_path)
            result["contact_sheet_url"] = vision_url(contact_sheet_path)
            result["contact_sheet_public_url"] = public_url(contact_sheet_path)

    except Exception as exc:
        result["error"] = str(exc)
        result["message"] = "Nozzle vision sweep failed before producing a complete result."
        if frames:
            result["frames"] = frames
    finally:
        if args.restore and result.get("original"):
            try:
                original = result["original"]
                macro = "T1" if original.get("extruder") == "extruder1" else "T0"
                pos = original.get("gcode_position") or [args.x, args.y, args.z]
                run_gcode(
                    args.moonraker_url,
                    (
                        f"{macro}\n"
                        "G90\n"
                        f"G1 X{float(pos[0]):.3f} Y{float(pos[1]):.3f} "
                        f"Z{float(pos[2]):.3f} F{args.feedrate:.0f}\n"
                        "M400"
                    ),
                )
                result["restore"] = {"ok": True, "tool": macro, "gcode_position": pos[:3]}
            except Exception as exc:
                result["restore"] = {"ok": False, "error": str(exc)}

        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        update_sweep_latest_links(
            run_dir,
            result_path,
            contact_sheet_path if contact_sheet_path.exists() else None,
        )
        if contact_sheet_path.exists():
            console_respond(
                args.moonraker_url,
                f"IDEX nozzle sweep report: {public_url(contact_sheet_path)}",
            )
            console_respond(
                args.moonraker_url,
                "Latest nozzle sweep report: "
                f"{public_url(vision_url(NOZZLE_SWEEP_DIR / 'latest_contact_sheet.jpg'))}",
            )
        elif result.get("error"):
            console_respond(
                args.moonraker_url,
                f"IDEX nozzle sweep failed: {result['error']}",
            )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moonraker-url", default=DEFAULT_MOONRAKER_URL)
    parser.add_argument("--name", default="manual")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Required. The single-image nozzle check path was removed.",
    )
    parser.add_argument("--x", type=float, default=195.0)
    parser.add_argument("--y", type=float, default=-14.8)
    parser.add_argument("--z", type=float)
    parser.add_argument("--dx", default="0,3,6,9,12")
    parser.add_argument("--feedrate", type=float, default=3600.0)
    parser.add_argument("--settle-time", type=float, default=0.75)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument("--restore", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--manage-crowsnest",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Compatibility no-op; nozzle vision uses the RAM framebuffer.",
    )
    args = parser.parse_args()
    if not args.sweep:
        parser.error("single-image nozzle vision check was removed; use --sweep")
    if args.z is None:
        args.z = 20.0
    result = run_sweep(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
