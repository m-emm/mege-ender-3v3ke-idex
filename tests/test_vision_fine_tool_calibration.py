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


def _fixture(module, *, implausible_z=False):
    def project(world):
        x_mm, y_mm, z_mm = world
        denominator = 1.0 + 0.005 * z_mm
        return np.asarray(
            [
                (10.0 * x_mm + 0.3 * y_mm + 50.0) / denominator,
                (0.2 * x_mm - 8.0 * y_mm + 250.0) / denominator,
            ]
        )

    expected = {
        "T0": np.asarray([0.4, -0.3, 0.5]),
        "T1": np.asarray([-0.2, 0.1, 3.0 if implausible_z else 0.4]),
    }
    corner_y = -18.0
    registrations = []
    full_records = {"T0": [], "T1": []}
    sequence = 0
    for tool in ("T0", "T1"):
        camera_y = 2.0 * corner_y + expected[tool][1]
        for z_mm, x_values in (
            (1.0, [183.0, 186.0, 189.0, 192.0, 195.0, 198.0]),
            (3.0, [189.0]),
            (5.0, [198.0, 195.0, 192.0, 189.0, 186.0, 183.0]),
            (7.0, [189.0]),
            (9.0, [183.0, 186.0, 189.0, 192.0, 195.0, 198.0]),
        ):
            for x_mm in x_values:
                record = {
                    "seq": sequence,
                    "tool": tool,
                    "x_mm": x_mm,
                    "z_mm": z_mm,
                    "center_px": project(
                        [
                            x_mm + expected[tool][0],
                            camera_y,
                            z_mm + expected[tool][2],
                        ]
                    ).tolist(),
                }
                registrations.append(record)
                if len(x_values) >= 5:
                    full_records[tool].append(record)
                sequence += 1
    models = {
        tool: module._fit_model(
            full_records[tool], x_ref_mm=189.0, z_ref_mm=5.0
        )
        for tool in ("T0", "T1")
    }
    patch_points = np.asarray(
        [[3.0, 3.0], [11.0, 3.0], [3.0, 11.0], [11.0, 11.0]]
    )
    patch_origin = np.asarray([176.0, -25.0])
    metric_observations = []
    for seq, commanded_y in enumerate([-14.0, -4.0, 6.0, 6.0, -4.0, -14.0]):
        metric_observations.append(
            {
                "seq": seq,
                "commanded_y_mm": commanded_y,
                "centers_px": [
                    project([*(point + patch_origin), -0.6]).tolist()
                    for point in patch_points
                ],
            }
        )
        for point_index, point in enumerate(patch_points):
            metric_observations[-1]["centers_px"][point_index] = project(
                [
                    point[0] + patch_origin[0],
                    point[1] + patch_origin[1] + commanded_y,
                    -0.6,
                ]
            ).tolist()
    corner_observations = [
        {
            "seq": seq,
            "commanded_y_mm": -14.0,
            "pixel_px": project([173.0, -32.0, 0.0]).tolist(),
        }
        for seq in range(5)
    ]
    fiducial_reference = patch_origin + np.mean(patch_points, axis=0)
    fiducial_x_vector = (
        project([fiducial_reference[0] + 1.0, fiducial_reference[1], -0.6])
        - project([*fiducial_reference, -0.6])
    )
    projection = {
        "tool_models": models,
        "fiducial_reference_printer_xy_mm": fiducial_reference.tolist(),
        "fiducial_x_vector_at_fine_capture_px_per_mm":
            fiducial_x_vector.tolist(),
        "fiducial_plane_printer_z_mm": -0.6,
        "fine_capture_y_mm": -14.0,
    }
    partial = {
        "corner_printer_xyz_mm": [173.0, -18.0, 0.0],
        "corner_pixel_capture_y_mm": -14.0,
    }
    mapping = {
        "patch_to_printer_xy_matrix": np.eye(2).tolist(),
        "patch_origin_printer_xy_mm": patch_origin.tolist(),
    }
    physical_reference = {"centers_patch_xy_mm": patch_points.tolist()}
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
    return (
        projection,
        partial,
        registrations,
        metric_observations,
        corner_observations,
        physical_reference,
        mapping,
        old,
        expected,
    )


def test_stage_5_1_recovers_six_absolute_datums_and_generated_offsets():
    module = _module()
    (
        projection,
        partial,
        registrations,
        metric,
        corner,
        physical,
        mapping,
        old,
        expected,
    ) = _fixture(module)

    result_t0 = module.calculate_candidate(
        tool="T0",
        projection=projection,
        partial_bed=partial,
        registrations=[r for r in registrations if r["tool"] == "T0"],
        metric_observations=metric,
        corner_observations=corner,
        physical_reference=physical,
        mapping=mapping,
        old_datums=old,
    )
    result_t1 = module.calculate_candidate(
        tool="T1",
        projection=projection,
        partial_bed=partial,
        registrations=[r for r in registrations if r["tool"] == "T1"],
        metric_observations=metric,
        corner_observations=corner,
        physical_reference=physical,
        mapping=mapping,
        old_datums=old,
    )

    assert result_t0["accepted"], result_t0["reasons"]
    assert result_t1["accepted"], result_t1["reasons"]
    np.testing.assert_allclose(
        result_t0["tools"]["T0"]["coordinate_residual_xyz_mm"],
        expected["T0"],
        atol=0.16,
    )
    np.testing.assert_allclose(
        result_t1["tools"]["T1"]["coordinate_residual_xyz_mm"],
        expected["T1"],
        atol=0.16,
    )
    persisted_t0 = result_t0["calibration"]["persisted_calib"]["new"]
    persisted_t1 = result_t1["calibration"]["persisted_calib"]["new"]
    generated_t0 = result_t0["calibration"]["generated_klipper"]["new"]
    assert abs(persisted_t0["t0"]["x"] - (-76.6)) < 0.16
    assert abs(persisted_t1["t1"]["x"] - 349.8) < 0.16
    assert generated_t0["y_position_endstop"] == persisted_t0["t0"]["y"]
    assert generated_t0["z_position_endstop"] == persisted_t0["t0"]["z"]
    assert generated_t0["t1_y_gcode_offset"] == (
        persisted_t0["t0"]["y"] - persisted_t0["t1"]["y"]
    )
    assert generated_t0["t1_z_gcode_offset"] == (
        persisted_t0["t0"]["z"] - persisted_t0["t1"]["z"]
    )


def test_stage_5_1_rejects_implausible_print_plane_instead_of_emitting_candidate():
    module = _module()
    (
        projection,
        partial,
        registrations,
        metric,
        corner,
        physical,
        mapping,
        old,
        _expected,
    ) = _fixture(module, implausible_z=True)

    result = module.calculate_candidate(
        tool="T1",
        projection=projection,
        partial_bed=partial,
        registrations=[r for r in registrations if r["tool"] == "T1"],
        metric_observations=metric,
        corner_observations=corner,
        physical_reference=physical,
        mapping=mapping,
        old_datums=old,
    )

    assert not result["accepted"]
    assert any("Z correction" in reason for reason in result["reasons"])


def test_t1_virtual_datum_changes_offset_by_t0_minus_t1_residual():
    module = _module()
    old = {
        "t0": {"x_endstop": -77.0, "y_endstop": -14.0, "z_endstop": 293.0},
        "t1": {"x_endstop": 350.0, "y_endstop": -15.0, "z_endstop": 292.8},
    }
    residuals = {"t0": [0.0, 0.4, -0.2], "t1": [0.0, -0.1, 0.3]}

    result_t0 = module.generated_calibration(
        old, tool="T0", residual_xyz_mm=residuals["t0"]
    )
    updated = {
        "t0": {
            f"{a}_endstop": v
            for a, v in result_t0["persisted_calib"]["new"]["t0"].items()
        },
        "t1": old["t1"],
    }
    result_t1 = module.generated_calibration(
        updated, tool="T1", residual_xyz_mm=residuals["t1"]
    )
    old_generated = result_t0["generated_klipper"]["old"]
    new_generated = result_t1["generated_klipper"]["new"]

    assert (
        new_generated["t1_y_gcode_offset"]
        - old_generated["t1_y_gcode_offset"]
    ) == 0.5
    assert (
        new_generated["t1_z_gcode_offset"]
        - old_generated["t1_z_gcode_offset"]
    ) == -0.5
