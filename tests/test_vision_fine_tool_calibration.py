import importlib.util
import sys
from pathlib import Path

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


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_fine_tool_calibration_test",
        FILES / "vision_fine_tool_calibration.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _position(model, x_mm, z_mm):
    dx = x_mm - model["x_ref_mm"]
    dz = z_mm - model["z_ref_mm"]
    return (
        np.asarray([1.0, dx, dz, dx * dz])
        @ np.asarray(model["position_coefficients"])
    ).tolist()


def _fixture(*, implausible_z=False):
    bed_x = [10.0, 0.0]
    models = {
        "T0": {
            "x_ref_mm": 189.0,
            "z_ref_mm": 5.0,
            "position_coefficients": [
                [269.5, 148.0],
                [11.1 if not implausible_z else 12.0, 0.0],
                [1.0, 2.0],
                [0.2, 0.0],
            ],
            "accepted_sequences": list(range(20)),
        },
        "T1": {
            "x_ref_mm": 189.0,
            "z_ref_mm": 5.0,
            "position_coefficients": [
                [263.4, 151.8],
                [11.08 if not implausible_z else 12.0, 0.0],
                [1.0, 2.0],
                [0.2, 0.0],
            ],
            "accepted_sequences": list(range(20, 40)),
        },
    }
    registrations = []
    sequence = 0
    for tool in ("T0", "T1"):
        for z_mm, x_values in (
            (1.0, [183.0, 186.0, 189.0, 192.0, 195.0, 198.0]),
            (3.0, [189.0]),
            (5.0, [198.0, 195.0, 192.0, 189.0, 186.0, 183.0]),
            (7.0, [189.0]),
            (9.0, [183.0, 186.0, 189.0, 192.0, 195.0, 198.0]),
        ):
            for x_mm in x_values:
                registrations.append(
                    {
                        "seq": sequence,
                        "tool": tool,
                        "x_mm": x_mm,
                        "z_mm": z_mm,
                        "center_px": _position(models[tool], x_mm, z_mm),
                    }
                )
                sequence += 1
    projection = {
        "tool_models": models,
        "bed_x_vector_print_plane_px_per_mm": bed_x,
        "image_y_axis_vector_px_per_mm": [0.0, -10.0],
    }
    partial = {
        "corner_printer_xyz_mm": [173.0, -18.0, 0.0],
        "corner_pixel_xy_px": [100.0, 100.0],
        "corner_pixel_capture_y_mm": -14.0,
    }
    old = {
        "t0": {
            "x_endstop": -77.0,
            "y_endstop": -14.8,
            "z_endstop": 293.0,
        },
        "t1": {
            "x_endstop": 350.0,
            "y_endstop": -15.8,
            "z_endstop": 293.2,
        },
    }
    return projection, partial, registrations, old


def test_stage_5_1_recovers_six_absolute_datums_and_generated_offsets():
    module = _module()
    projection, partial, registrations, old = _fixture()

    result = module.calculate_candidate(
        projection=projection,
        partial_bed=partial,
        registrations=registrations,
        old_datums=old,
        capture_y_mm=-14.0,
    )

    assert result["accepted"], result["reasons"]
    np.testing.assert_allclose(
        result["tools"]["T0"]["coordinate_residual_xyz_mm"],
        [0.4, -0.3, 0.5],
        atol=1e-9,
    )
    np.testing.assert_allclose(
        result["tools"]["T1"]["coordinate_residual_xyz_mm"],
        [-0.2, 0.1, 0.4],
        atol=1e-9,
    )
    persisted = result["calibration"]["persisted_calib"]["new"]
    generated = result["calibration"]["generated_klipper"]["new"]
    assert persisted["t0"]["x"] == -76.6
    assert persisted["t1"]["x"] == 349.8
    assert generated["y_position_endstop"] == persisted["t0"]["y"]
    assert generated["z_position_endstop"] == persisted["t0"]["z"]
    assert generated["t1_y_gcode_offset"] == (
        persisted["t0"]["y"] - persisted["t1"]["y"]
    )
    assert generated["t1_z_gcode_offset"] == (
        persisted["t0"]["z"] - persisted["t1"]["z"]
    )


def test_stage_5_1_rejects_implausible_print_plane_instead_of_emitting_candidate():
    module = _module()
    projection, partial, registrations, old = _fixture(implausible_z=True)

    result = module.calculate_candidate(
        projection=projection,
        partial_bed=partial,
        registrations=registrations,
        old_datums=old,
        capture_y_mm=-14.0,
    )

    assert not result["accepted"]
    assert any("not near commanded Z=0" in reason for reason in result["reasons"])
    assert any("Z correction" in reason for reason in result["reasons"])


def test_t1_virtual_datum_changes_offset_by_t0_minus_t1_residual():
    module = _module()
    old = {
        "t0": {"x_endstop": -77.0, "y_endstop": -14.0, "z_endstop": 293.0},
        "t1": {"x_endstop": 350.0, "y_endstop": -15.0, "z_endstop": 292.8},
    }
    residuals = {"t0": [0.0, 0.4, -0.2], "t1": [0.0, -0.1, 0.3]}

    result = module.generated_calibration(old, residuals)
    old_generated = result["generated_klipper"]["old"]
    new_generated = result["generated_klipper"]["new"]

    assert (
        new_generated["t1_y_gcode_offset"]
        - old_generated["t1_y_gcode_offset"]
    ) == 0.5
    assert (
        new_generated["t1_z_gcode_offset"]
        - old_generated["t1_z_gcode_offset"]
    ) == -0.5
