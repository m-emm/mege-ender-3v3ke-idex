"""Smoke test for vision_idex_xyz_offset.analyze_idex_xyz_offset.

Uses real captured fact-set fixtures downloaded from the printer:
  - tests/fixtures/vision_idex_xyz_offset/t0_projection_fact_set.json
  - tests/fixtures/vision_idex_xyz_offset/eddy_xz_image_positions_fact_set.json

Synthetic T1 observations are built from T0 by keeping the commanded (x_mm, z_mm)
positions identical and applying a known constant pixel shift to all center_px
observations.  The algorithm must then recover the printer-space (dx, dy, dz)
offset that explains those image-space displacements.

Note on the Y-axis sign convention: the 3D camera model fitted from T0+Eddy data
has its printer-Y axis oriented such that a negative image-V shift corresponds to
a negative dy in the recovered offset.  This is the opposite of what the fine
nozzle calibration's image_y_axis_vector would naively suggest; the two models
use different reference poses.

Empirical camera sensitivities (from forward-probe of the fitted model):
  image-U vs. printer-X: ~10 px/mm  →  +80 px U ≈ +10 mm dx
  image-V vs. printer-Y: ~10 px/mm  →  -31 px V ≈  -3 mm dy  (same sign)
"""

import json
import sys
from pathlib import Path


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
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "vision_idex_xyz_offset"

# Pixel shift injected into T1 observations (image coordinates).
PIXEL_SHIFT_U = 80.0   # image-U (column) shift in pixels  → mainly printer-X
PIXEL_SHIFT_V = -31.0  # image-V (row) shift in pixels     → mainly printer-Y

# Approximate expected mm offsets derived from the empirical camera model response.
# In the fitted 3D camera model, the sign of dy matches the sign of the V pixel
# shift (both are negative here).  Scale is roughly 10 px/mm for both axes.
EXPECTED_DX_MM = PIXEL_SHIFT_U / 9.935   # ≈ +8.05 mm  (positive)
EXPECTED_DY_MM = PIXEL_SHIFT_V / 10.242  # ≈  -3.03 mm (negative — same sign as V)

# Tolerance: within ±2 mm of the linear approximation is fine for a smoke test.
RECOVERY_TOLERANCE_MM = 2.0


def _add_files_to_path():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))


def _load_module():
    _add_files_to_path()
    import vision_idex_xyz_offset  # noqa: PLC0415

    return vision_idex_xyz_offset


def _t0_projection():
    """Extract t0 projection value from the fixture fact-set."""
    fact_set = json.loads((FIXTURES / "t0_projection_fact_set.json").read_text())
    fact = next(
        f
        for f in fact_set["facts"]
        if "projection_model" in f["name"] or "t0_projection" in f["name"]
    )
    return fact["value"]


def _eddy_positions():
    """Extract eddy xz image positions value from the fixture fact-set."""
    fact_set = json.loads(
        (FIXTURES / "eddy_xz_image_positions_fact_set.json").read_text()
    )
    fact = next(f for f in fact_set["facts"] if "eddy" in f["name"])
    return fact["value"]


def _synthetic_t1_projection(
    t0_projection,
    pixel_shift_u: float = PIXEL_SHIFT_U,
    pixel_shift_v: float = PIXEL_SHIFT_V,
):
    """Build a synthetic T1 projection from T0.

    The commanded positions (x_mm, z_mm) are kept identical to T0 so the only
    difference visible to the algorithm is a constant shift in the observed image
    coordinates (center_px).  The algorithm must infer the printer-space (dx, dy)
    offset that explains the pixel displacement.
    """
    t0_positions = t0_projection["tool_models"]["T0"]["accepted_direct_positions"]
    t1_positions = [
        {
            "x_mm": pos["x_mm"],
            "z_mm": pos["z_mm"],
            "center_px": [
                pos["center_px"][0] + pixel_shift_u,
                pos["center_px"][1] + pixel_shift_v,
            ],
        }
        for pos in t0_positions
    ]
    return {"tool_models": {"T1": {"accepted_direct_positions": t1_positions}}}


def test_analyze_idex_xyz_offset_recovers_x_and_y_pixel_shift(tmp_path):
    mod = _load_module()

    t0_proj = _t0_projection()
    t1_proj = _synthetic_t1_projection(t0_proj)
    eddy_pos = _eddy_positions()

    result = mod.analyze_idex_xyz_offset(
        artifact_dir=tmp_path / "artifacts",
        t0_projection=t0_proj,
        t1_projection=t1_proj,
        eddy_positions=eddy_pos,
    )

    assert isinstance(result, dict)
    assert "accepted" in result
    assert "t0_t1_xyz_offset" in result
    assert "camera_model_quality" in result
    assert "artifacts" in result

    offset = result["t0_t1_xyz_offset"]
    assert len(offset) == 3, "offset must be a 3-element [x, y, z] list"

    dx, dy, dz = offset

    assert result["camera_model_quality"]["success"] is True

    # The recovered x-offset should be close to EXPECTED_DX_MM.
    assert abs(dx - EXPECTED_DX_MM) < RECOVERY_TOLERANCE_MM, (
        f"x-offset {dx:.3f} mm deviates from expected {EXPECTED_DX_MM:.3f} mm "
        f"by more than {RECOVERY_TOLERANCE_MM} mm"
    )

    # The recovered y-offset should be close to EXPECTED_DY_MM.
    assert abs(dy - EXPECTED_DY_MM) < RECOVERY_TOLERANCE_MM, (
        f"y-offset {dy:.3f} mm deviates from expected {EXPECTED_DY_MM:.3f} mm "
        f"by more than {RECOVERY_TOLERANCE_MM} mm"
    )

    # z-offset is not independently constrained by image-U/V shifts in the
    # restricted isotropic camera model; it absorbs residual perspective error.
    # Just ensure the result is a finite number, not an extreme outlier.
    assert abs(dz) < 30.0, f"z-offset {dz:.3f} mm is implausibly large"


def test_analyze_idex_xyz_offset_artifacts_written(tmp_path):
    mod = _load_module()

    t0_proj = _t0_projection()
    t1_proj = _synthetic_t1_projection(t0_proj)
    eddy_pos = _eddy_positions()

    artifact_dir = tmp_path / "artifacts"
    result = mod.analyze_idex_xyz_offset(
        artifact_dir=artifact_dir,
        t0_projection=t0_proj,
        t1_projection=t1_proj,
        eddy_positions=eddy_pos,
    )

    # All declared artifact files should exist on disk.
    for key, artifact in result["artifacts"].items():
        path = Path(artifact["path"])
        assert path.is_file(), f"artifact '{key}' not found at {path}"
