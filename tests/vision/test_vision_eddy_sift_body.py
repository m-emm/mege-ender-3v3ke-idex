"""Verify SIFT-based sensor-body localisation on the Eddy fiducial XZ dataset.

What this test does
-------------------
1. Crops the BTT Eddy sensor body from frame 00 at hardcoded pixel coordinates.
2. Computes SIFT keypoints + descriptors on that crop (the template).
3. For every frame in the dataset, matches the template via BFMatcher +
   Lowe-ratio test + RANSAC homography.
4. Projects the original template bounding box into each frame using the
   recovered homography and draws it as a green rectangle.
5. Writes per-frame full-resolution PNG overlays, a 4x4 contact sheet, and
   the template images (plain + keypoints visualised) into a timestamped run
   directory under output/vision_eddy_sift_body/.

Nothing else: no fiducial, no logo, no scatter plots.  The sole purpose is to
confirm that SIFT reliably finds the sensor body in every frame.

Dataset location
----------------
    resources/vision_datasets/20260731_eddy_fiducial_xz_once/

If the dataset is absent the test is skipped.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = (
    REPO_ROOT
    / "resources"
    / "vision_datasets"
    / "20260731_eddy_fiducial_xz_once"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_eddy_sift_body"

# ---------------------------------------------------------------------------
# Frozen SIFT template — committed PNG of the BTT Eddy sensor body crop.
# Extracted once from frame 00 of the 20260731 dataset at
#   x=[815,1000], y=[163,427]  (185×264 px, 1920×1080 source)
# and checked in as a stable resource so matching is independent of
# the live dataset being present.
# ---------------------------------------------------------------------------
TEMPLATE_PATH = REPO_ROOT / "resources" / "eddy_sift_body_template.png"

# SIFT matching parameters
LOWE_RATIO = 0.75
MIN_INLIERS = 8


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _make_template() -> tuple[np.ndarray, list, np.ndarray]:
    """Load the frozen template PNG and compute SIFT.  Returns (crop_bgr, keypoints, descriptors)."""
    assert TEMPLATE_PATH.is_file(), (
        f"Committed SIFT template not found: {TEMPLATE_PATH}\n"
        "Re-generate with: python -c \"import cv2; from pathlib import Path; "
        "img=cv2.imread('resources/vision_datasets/20260731_eddy_fiducial_xz_once/frames/"
        "00_eddy_x230p000_z0p500.jpg'); "
        "cv2.imwrite('resources/eddy_sift_body_template.png', img[163:427,815:1000])\""
    )
    crop = cv2.imread(str(TEMPLATE_PATH), cv2.IMREAD_COLOR)
    assert crop is not None, f"cannot read template {TEMPLATE_PATH}"
    sift = cv2.SIFT_create()
    kp, des = sift.detectAndCompute(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), None)
    assert des is not None and len(kp) >= 4, (
        f"Too few SIFT keypoints in template ({len(kp)}); template file may be corrupt"
    )
    return crop, kp, des


def _match_frame(
    frame: np.ndarray,
    template_kp: list,
    template_des: np.ndarray,
) -> tuple[bool, np.ndarray | None, int]:
    """Match template against frame.  Returns (found, homography_M, n_inliers)."""
    sift = cv2.SIFT_create()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    kp2, des2 = sift.detectAndCompute(gray, None)
    if des2 is None or len(kp2) < 4:
        return False, None, 0

    bf = cv2.BFMatcher(cv2.NORM_L2)
    raw_matches = bf.knnMatch(template_des, des2, k=2)
    good = [
        m
        for m, n in raw_matches
        if len([m, n]) == 2 and m.distance < LOWE_RATIO * n.distance
    ]
    if len(good) < MIN_INLIERS:
        return False, None, 0

    src_pts = np.float32([template_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if M is None:
        return False, None, 0
    n_inliers = int(np.sum(mask)) if mask is not None else 0
    return n_inliers >= MIN_INLIERS, M, n_inliers


def _project_template_box(
    M: np.ndarray, template_w: int, template_h: int
) -> tuple[np.ndarray, tuple[int, int]]:
    """Project the template corners through M → full-frame coordinates.

    The homography M maps crop-space coordinates (origin at (0,0) in the crop)
    directly to full-frame coordinates in the target frame — no offset needed.
    """
    w, h = template_w, template_h
    corners_crop = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    corners_frame = cv2.perspectiveTransform(corners_crop, M).reshape(-1, 2)
    cx = int(round(float(np.mean(corners_frame[:, 0]))))
    cy = int(round(float(np.mean(corners_frame[:, 1]))))
    return corners_frame.astype(int), (cx, cy)


def _draw_overlay(
    frame: np.ndarray,
    found: bool,
    corners: np.ndarray | None,
    center: tuple[int, int] | None,
    n_inliers: int,
    label: str,
) -> np.ndarray:
    out = frame.copy()
    if found and corners is not None and center is not None:
        cv2.polylines(out, [corners.reshape(-1, 1, 2)], True, (0, 230, 0), 3)
        cv2.drawMarker(out, center, (0, 230, 0), cv2.MARKER_CROSS, 60, 3)
        cv2.putText(
            out,
            f"FOUND  inliers={n_inliers}  center=({center[0]},{center[1]})",
            (24, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.90,
            (0, 230, 0),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(
            out,
            f"NOT FOUND  inliers={n_inliers}",
            (24, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.90,
            (0, 60, 255),
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        out, label,
        (24, 98),
        cv2.FONT_HERSHEY_SIMPLEX, 0.72, (220, 220, 0), 2, cv2.LINE_AA,
    )
    return out


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_sift_body_localisation_all_frames():
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(
            f"dataset absent: {DATASET_ROOT}  "
            "(populate from printer — see test_vision_eddy_fiducial_xz_captured_replay.py)"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame_records = manifest["frames"]
    frame_paths = [
        DATASET_ROOT / "frames" / f"{rec['frame']}.jpg" for rec in frame_records
    ]
    missing = [p for p in frame_paths if not p.is_file()]
    if missing:
        pytest.skip(f"{len(missing)} frames absent, e.g. {missing[0].name}")

    # Per-run output directory
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + uuid4().hex[:8]
    )
    run_dir = OUTPUT_ROOT / "runs" / run_id
    overlays_dir = run_dir / "frame_overlays"
    overlays_dir.mkdir(parents=True)

    # ------------------------------------------------------------------ #
    # 1. Load frozen template                                             #
    # ------------------------------------------------------------------ #
    template_crop, template_kp, template_des = _make_template()
    th, tw = template_crop.shape[:2]

    # Save plain template crop
    template_plain_path = run_dir / "template_body.png"
    cv2.imwrite(str(template_plain_path), template_crop)

    # Save template with SIFT keypoints drawn
    kp_vis = cv2.drawKeypoints(
        template_crop,
        template_kp,
        None,
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS,
    )
    cv2.putText(
        kp_vis,
        f"SIFT template  {TEMPLATE_PATH.name}  ({tw}x{th} px)  "
        f"{len(template_kp)} keypoints",
        (8, th - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (0, 240, 255),
        1,
        cv2.LINE_AA,
    )
    template_kp_path = run_dir / "template_body_keypoints.png"
    cv2.imwrite(str(template_kp_path), kp_vis)

    # ------------------------------------------------------------------ #
    # 2. Match against every frame                                        #
    # ------------------------------------------------------------------ #
    per_frame: list[dict] = []
    panels: list[np.ndarray] = []

    for idx, (fp, rec) in enumerate(zip(frame_paths, frame_records)):
        frame = cv2.imread(str(fp), cv2.IMREAD_COLOR)
        assert frame is not None, f"cannot read {fp}"

        found, M, n_inliers = _match_frame(frame, template_kp, template_des)

        corners = center = None
        if found and M is not None:
            corners, center = _project_template_box(M, tw, th)

        label = (
            f"{rec['frame']}  X={float(rec['x_mm']):.3f}mm  Z={float(rec['z_mm']):.3f}mm"
        )
        overlay = _draw_overlay(frame, found, corners, center, n_inliers, label)
        overlay_path = overlays_dir / f"{idx:02d}_{rec['frame']}_sift_body.png"
        cv2.imwrite(str(overlay_path), overlay)

        per_frame.append(
            {
                "seq": idx,
                "frame": rec["frame"],
                "x_mm": float(rec["x_mm"]),
                "z_mm": float(rec["z_mm"]),
                "found": found,
                "n_inliers": n_inliers,
                "center_px": list(center) if center else None,
            }
        )
        panels.append(cv2.resize(overlay, (480, 270), interpolation=cv2.INTER_AREA))

    # ------------------------------------------------------------------ #
    # 3. Contact sheet (4 columns)                                        #
    # ------------------------------------------------------------------ #
    rows = []
    blank = np.zeros_like(panels[0])
    for start in range(0, len(panels), 4):
        row = panels[start : start + 4]
        while len(row) < 4:
            row.append(blank)
        rows.append(cv2.hconcat(row))
    contact_sheet_path = run_dir / "contact_sheet.jpg"
    cv2.imwrite(str(contact_sheet_path), cv2.vconcat(rows))

    # ------------------------------------------------------------------ #
    # 4. Inspection summary (markdown)                                    #
    # ------------------------------------------------------------------ #
    found_count = sum(1 for r in per_frame if r["found"])
    lines = [
        "# Eddy SIFT body localisation — inspection summary",
        "",
        f"Run: `{run_id}`",
        "",
        "## Template",
        "",
        f"- Template file: `{TEMPLATE_PATH.name}`  ({tw}×{th} px)",
        f"- Origin: frame 00, region x=[815,1000] y=[163,427] of 1920×1080 source",
        f"- Frozen and committed; not re-derived from the dataset.",
        f"- SIFT keypoints extracted: {len(template_kp)}",
        f"- [Plain crop](template_body.png)",
        f"- [Keypoints visualised](template_body_keypoints.png)",
        "",
        "## Match results",
        "",
        f"**{found_count}/{len(per_frame)} frames matched** "
        f"(threshold: ≥{MIN_INLIERS} RANSAC inliers, Lowe ratio={LOWE_RATIO})",
        "",
        "| # | frame | X mm | Z mm | found | inliers | center px |",
        "|---|-------|------|------|-------|---------|-----------|",
    ]
    for r in per_frame:
        cx = f"({r['center_px'][0]},{r['center_px'][1]})" if r["center_px"] else "—"
        status = "✓" if r["found"] else "✗"
        lines.append(
            f"| {r['seq']:02d} | {r['frame']} | {r['x_mm']:.3f} | {r['z_mm']:.3f}"
            f" | {status} | {r['n_inliers']} | {cx} |"
        )
    lines += [
        "",
        "## Files",
        "",
        f"- [Contact sheet (4×4)](contact_sheet.jpg)",
        f"- Per-frame overlays: `frame_overlays/` ({len(per_frame)} PNG files)",
        "",
        "### Per-frame overlays",
        "",
    ]
    for r in per_frame:
        rel = f"frame_overlays/{r['seq']:02d}_{r['frame']}_sift_body.png"
        lines.append(f"- [{r['frame']}]({rel})")

    (run_dir / "inspection_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    # ------------------------------------------------------------------ #
    # 5. Console output                                                   #
    # ------------------------------------------------------------------ #
    print(f"\nEDDY SIFT BODY RUN DIRECTORY:\n{run_dir.resolve()}")
    print(f"\nTEMPLATE:")
    print(f"  plain:     {template_plain_path.resolve()}")
    print(f"  keypoints: {template_kp_path.resolve()}")
    print(f"\nCONTACT SHEET:\n  {contact_sheet_path.resolve()}")
    print(f"\nPER-FRAME OVERLAYS ({found_count}/{len(per_frame)} found):")
    for r in per_frame:
        cx = (
            f"center=({r['center_px'][0]},{r['center_px'][1]})"
            if r["center_px"]
            else "NOT FOUND"
        )
        overlay_path = (
            overlays_dir / f"{r['seq']:02d}_{r['frame']}_sift_body.png"
        )
        print(
            f"  {r['seq']:02d} {r['frame']}"
            f"  X={r['x_mm']:.3f} Z={r['z_mm']:.3f}"
            f"  inliers={r['n_inliers']}  {cx}"
        )
        print(f"     {overlay_path.resolve()}")

    # ------------------------------------------------------------------ #
    # 6. Assertions                                                       #
    # ------------------------------------------------------------------ #
    assert template_plain_path.is_file()
    assert template_kp_path.is_file()
    assert contact_sheet_path.is_file()
    assert len(template_kp) >= 50, (
        f"only {len(template_kp)} SIFT keypoints extracted from template; "
        "template region may be wrong"
    )

    not_found = [r for r in per_frame if not r["found"]]
    assert not not_found, (
        f"{len(not_found)}/{len(per_frame)} frames not matched: "
        + ", ".join(r["frame"] for r in not_found)
    )

    # All detected body centres must lie within the image
    frame_00_check = cv2.imread(str(frame_paths[0]), cv2.IMREAD_COLOR)
    assert frame_00_check is not None
    h_img, w_img = frame_00_check.shape[:2]
    for r in per_frame:
        if r["center_px"]:
            cx, cy = r["center_px"]
            assert 0 <= cx < w_img and 0 <= cy < h_img, (
                f"frame {r['frame']}: body centre ({cx},{cy}) outside image "
                f"({w_img}×{h_img})"
            )
