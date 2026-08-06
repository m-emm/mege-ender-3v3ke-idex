import importlib.util
import json
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


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_tool_xz_sweep_test",
        FILES / "vision_tool_xz_sweep.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _definition():
    registry = json.loads((FILES / "vision_job_types.json").read_text())
    return registry["job_types"]["idex_tool_xz_sweep_report"]


def _inputs():
    return {
        "t0_xy_datum": {},
        "t1_xy_datum": {},
        "partial_bed_coordinate_system": {
            "corner_printer_xyz_mm": [173.0, -18.0, 0.0],
        },
        "bed_metric": {
            "image_y_axis_vector_px_per_mm": [0.0, -10.0],
            "reference_marker_centers_px": [
                [900.0, 400.0],
                [980.0, 400.0],
                [900.0, 480.0],
                [980.0, 480.0],
            ],
            "reference_capture_y_mm": -14.0,
        },
        "bed_fiducial_printer_xy_mapping": {
            "corner_printer_xy_mm": [173.0, -18.0],
            "fiducial_reference_printer_xy_mm": [180.0, -11.0],
            "fiducial_x_vector_model_px_per_mm": {
                "reference_vector_px_per_mm": [10.0, 0.0],
                "capture_y_slope_px_per_mm_per_mm": [0.0, 0.0],
                "reference_capture_y_mm": -14.0,
            },
        },
        "t0_red_marker_offset": {
            "offset_mm": 20.0,
            "reference_commanded_x_mm": 193.0,
            "quality": {"tool_axis_vectors_px_per_mm": {"T0": [8.0, 0.0]}},
        },
        "t1_red_marker_offset": {
            "offset_mm": 20.0,
            "reference_commanded_x_mm": 193.0,
            "quality": {"tool_axis_vectors_px_per_mm": {"T1": [8.0, 0.0]}},
        },
    }


def _resolved():
    return {
        "axis_minimum": [-80.0, -14.8, 0.0],
        "axis_maximum": [355.0, 296.0, 300.0],
        "active_tool_calibration": {
            "active_fingerprint": "sha256:active",
            "tool_xy_endstops_mm": {
                "t0": {"x": -77.635, "y": -14.8},
                "t1": {"x": 351.739, "y": -13.8},
            },
            "tool_y_offsets_mm": {"t0": 0.0, "t1": -1.0},
        },
    }


def test_prepare_builds_both_tool_grids_with_per_tool_commanded_y():
    module = _module()
    definition = _definition()

    result = module.prepare_sweep(
        definition,
        input_values=_inputs(),
        resolved=_resolved(),
    )

    expected_per_tool = len(definition["x_offsets_from_bed_tab_mm"]) * len(
        definition["z_positions_mm"]
    )
    assert len(result["frames"]) == 2 * expected_per_tool
    assert {frame["tool"] for frame in result["frames"]} == {"T0", "T1"}
    assert result["frames"][0]["tool"] == "T0"
    assert result["frames"][-1]["tool"] == "T1"
    assert {
        frame["commanded_position_mm"][1]
        for frame in result["frames"]
        if frame["tool"] == "T0"
    } == {-14.3}
    assert {
        frame["commanded_position_mm"][1]
        for frame in result["frames"]
        if frame["tool"] == "T1"
    } == {-13.3}
    assert [
        frame["commanded_position_mm"][0]
        for frame in result["frames"][: len(definition["x_offsets_from_bed_tab_mm"])]
    ] == [173.0 + value for value in definition["x_offsets_from_bed_tab_mm"]]


def test_prepare_rejects_z_outside_loaded_limits():
    module = _module()
    definition = json.loads(json.dumps(_definition()))
    definition["z_positions_mm"] = [301.0]

    try:
        module.prepare_sweep(
            definition,
            input_values=_inputs(),
            resolved=_resolved(),
        )
    except module.ToolXZSweepError as exc:
        assert "commanded Z" in str(exc)
    else:
        raise AssertionError("out-of-range Z was accepted")


def test_analysis_writes_raw_records_overlays_and_u_plot(tmp_path, monkeypatch):
    module = _module()
    frames = []
    for seq, (tool, x_mm, y_mm, z_mm) in enumerate(
        (
            ("T0", 173.0, -14.3, 0.5),
            ("T0", 178.0, -14.3, 4.0),
            ("T1", 173.0, -13.3, 0.5),
            ("T1", 178.0, -13.3, 4.0),
        )
    ):
        frames.append(
            {
                "seq": seq,
                "frame": f"frame_{seq}",
                "tool": tool,
                "x_offset_from_bed_tab_mm": x_mm - 173.0,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "z_mm": z_mm,
                "expected_marker_pixel_px": [100.0, 100.0],
                "commanded_position_mm": [x_mm, y_mm, z_mm],
            }
        )
    paths = []
    for seq in range(len(frames)):
        path = tmp_path / f"frame_{seq}.jpg"
        assert cv2.imwrite(str(path), np.full((240, 320, 3), 32, dtype=np.uint8))
        paths.append(path)

    fiducial_calls = iter(range(len(frames)))

    def detect(_image):
        index = next(fiducial_calls)
        if index == 2:
            raise module.FourFiducialError("synthetic miss")
        return {
            "centers_px": [[90.0, 90.0], [110.0, 90.0], [90.0, 110.0], [110.0, 110.0]],
            "radii_px": [4.0, 4.0, 4.0, 4.0],
        }

    def localize(_paths, *, frames, **_kwargs):
        return {
            "registrations": [
                {
                    "seq": index,
                    "center_px": [120.0 + 5.0 * index, 80.0 + index],
                    "minimum_correlation": 0.9,
                }
                for index, _frame in enumerate(frames)
            ]
        }

    monkeypatch.setattr(module, "detect_four_fiducials", detect)
    monkeypatch.setattr(module, "localize_nozzle_tip_grid", localize)

    result = module.analyze(
        paths,
        tmp_path / "artifacts",
        frames=frames,
        references={"t0": {}, "t1": {}},
        acquisition_calibration={"tool_xy_endstops_mm": {}},
    )

    assert result["accepted"] is True
    assert len(result["records"]) == len(frames)
    assert result["records"][0]["nozzle_uv_px"] == [120.0, 80.0]
    assert result["records"][2]["fiducials_detected"] is False
    assert result["records"][2]["nozzle_uv_px"] is None
    assert (
        len(list((tmp_path / "artifacts" / "tool_xz_sweep_overlays").glob("*.png")))
        == 4
    )
    assert (tmp_path / "artifacts" / "tool_xz_sweep_u_vs_x.png").is_file()
    assert result["warnings"]
