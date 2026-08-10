import importlib.util
import json
import sys
import weakref
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


def _prior():
    return {
        "model": "linear_commanded_x_to_image_uv_v1",
        "coefficients_px": [[-786.0, 500.0], [9.9, 0.0]],
    }


def _inputs():
    return {
        "t0_xy_datum": {"nozzle_image_prior": _prior()},
        "t1_xy_datum": {"nozzle_image_prior": _prior()},
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
            "tool_z_endstops_mm": {"t0": 293.5, "t1": 292.95},
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


def test_prepare_requires_and_propagates_xy_nozzle_image_prior():
    module = _module()
    inputs = _inputs()
    prior = _prior()
    inputs["t0_xy_datum"] = {"nozzle_image_prior": prior}
    inputs["t1_xy_datum"] = {"nozzle_image_prior": prior}

    result = module.prepare_sweep(
        _definition(),
        input_values=inputs,
        resolved=_resolved(),
    )

    assert result["references"]["t0"]["nozzle_image_prior"] == prior
    assert result["references"]["t1"]["nozzle_image_prior"] == prior


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda inputs: inputs["t0_xy_datum"].clear(), "T0 nozzle_image_prior is required"),
        (
            lambda inputs: inputs["t1_xy_datum"].update(
                {"nozzle_image_prior": {"model": "wrong"}}
            ),
            "T1 nozzle_image_prior.model",
        ),
        (
            lambda inputs: inputs["t0_xy_datum"].update(
                {
                    "nozzle_image_prior": {
                        "model": "linear_commanded_x_to_image_uv_v1",
                        "coefficients_px": [[float("nan"), 500.0], [9.9, 0.0]],
                    }
                }
            ),
            "T0 nozzle_image_prior.coefficients_px",
        ),
    ],
)
def test_prepare_rejects_missing_malformed_or_incomplete_prior(mutate, expected):
    module = _module()
    inputs = _inputs()
    mutate(inputs)

    with pytest.raises(module.ToolXZSweepError, match=expected):
        module.prepare_sweep(_definition(), input_values=inputs, resolved=_resolved())


def test_prepare_accepts_exact_and_extrapolated_commanded_x_values():
    module = _module()
    result = module.prepare_sweep(
        _definition(), input_values=_inputs(), resolved=_resolved()
    )
    assert result["references"]["t0"]["nozzle_image_prior"] == _prior()
    assert result["references"]["t1"]["nozzle_image_prior"] == _prior()

    definition = _definition()
    definition["x_offsets_from_bed_tab_mm"] = [-100, 10, 25, 100]
    result = module.prepare_sweep(
        definition, input_values=_inputs(), resolved=_resolved()
    )
    assert len(result["frames"]) == 2 * 4 * len(definition["z_positions_mm"])


def test_analysis_rejects_missing_prior_before_decoding_images(tmp_path):
    module = _module()
    frames = [
        {
            "seq": 0,
            "tool": "T0",
            "x_mm": 186.0,
            "z_mm": 0.5,
            "commanded_position_mm": [186.0, -14.3, 0.5],
        },
        {
            "seq": 1,
            "tool": "T1",
            "x_mm": 186.0,
            "z_mm": 0.5,
            "commanded_position_mm": [186.0, -13.3, 0.5],
        },
    ]
    with pytest.raises(module.ToolXZSweepError, match="T0 nozzle_image_prior is required"):
        module.analyze(
            [tmp_path / "does-not-exist-t0.jpg", tmp_path / "does-not-exist-t1.jpg"],
            tmp_path / "artifacts",
            frames=frames,
            references={"t0": {}, "t1": {"nozzle_image_prior": _prior()}},
            acquisition_calibration={},
        )


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


def test_robust_u_x_slope_rejects_an_outlier():
    module = _module()
    records = [
        {
            "commanded_x_mm": x_mm,
            "nozzle_uv_px": [u_px, 80.0],
        }
        for x_mm, u_px in (
            (0.0, 10.0),
            (1.0, 12.0),
            (2.0, 14.0),
            (3.0, 16.0),
            (4.0, 100.0),
        )
    ]

    assert module._fit_robust_u_x_slope(records) == pytest.approx(2.0)
    assert module._fit_robust_u_x_slope(records[:2]) is None


def test_huber_row_fit_preserves_point_diagnostics_and_downweights_outlier():
    module = _module()
    x_values = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0])
    u_values = np.asarray([10.0, 12.0, 14.0, 16.0, 100.0])

    fit = module._fit_row_trajectory(
        x_values,
        u_values,
        method="huber_irls",
    )

    assert fit["slope"] == pytest.approx(2.0)
    assert bool(fit["downweighted"][-1]) is True
    assert float(fit["weights"][-1]) == pytest.approx(0.0)
    assert len(fit["residuals_px"]) == len(x_values)


def _synthetic_shared_fits(delta_mm=-0.6):
    fits = []
    for tool in ("T0", "T1"):
        for z_mm in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            physical_z = z_mm + (delta_mm if tool == "T1" else 0.0)
            fits.append(
                {
                    "tool": tool,
                    "z_mm": z_mm,
                    "slope_u_px_per_mm": 9.85 - 0.1 * physical_z + 0.01 * physical_z**2,
                    "slope_uncertainty_px_per_mm": 0.03,
                    "u_x_correlation_coefficient": 0.999,
                }
            )
    return fits


def test_profiled_shared_fit_recovers_delta_independent_of_input_order():
    module = _module()
    fits = _synthetic_shared_fits()

    result = module.estimate_tool_z_delta(fits)
    reversed_result = module.estimate_tool_z_delta(list(reversed(fits)))

    assert result["available"] is True
    assert result["t1_z_delta_mm"] == pytest.approx(-0.6, abs=0.02)
    assert reversed_result["t1_z_delta_mm"] == pytest.approx(
        result["t1_z_delta_mm"], abs=1.0e-9
    )
    assert result["fit_method"] == "quadratic_profiled_huber_with_jackknife"
    assert result["jackknife_delta_span_mm"] == pytest.approx(0.0, abs=1.0e-5)


def test_profiled_shared_fit_bound_saturation_is_unavailable():
    module = _module()
    fits = _synthetic_shared_fits(delta_mm=2.2)

    result = module.estimate_tool_z_delta(fits)

    assert result["available"] is False
    assert result["boundary_saturated"] is True
    assert "operational T1 delta bound" in result["reason"]


def test_profiled_shared_fit_reports_leave_one_row_instability(monkeypatch):
    module = _module()
    fits = _synthetic_shared_fits()

    original_profile = module._profile_shared_curve

    def unstable_profile(rows, **kwargs):
        result = original_profile(rows, **kwargs)
        if len(rows) == len(fits) - 1:
            row_signature = sum(int(round(row["z_mm"] * 10.0)) for row in rows)
            result["delta"] += 0.8 if row_signature % 2 else -0.8
        return result

    monkeypatch.setattr(module, "_profile_shared_curve", unstable_profile)

    result = module.estimate_tool_z_delta(fits)

    assert result["available"] is False
    assert result["jackknife_delta_span_mm"] > module.MAX_DELTA_JACKKNIFE_SPAN_MM
    assert "leave-one-row-out" in result["reason"]


def test_registration_quality_rejects_bad_image_correlation():
    module = _module()
    registration = {
        "minimum_correlation": 0.1,
        "median_correlation": 0.9,
        "representation_spread_px": 0.2,
        "tip_prediction_error_px": 1.0,
        "maximum_tip_prediction_error_px": 8.0,
    }

    reasons = module._registration_fit_reasons(registration)
    assert len(reasons) == 1
    assert "minimum tip correlation" in reasons[0]


def test_shared_z_curve_rejects_bad_correlation_and_curve_outlier():
    module = _module()
    expected_delta = -0.6
    fits = []
    for tool in ("T0", "T1"):
        for z_mm in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            physical_z = z_mm + (expected_delta if tool == "T1" else 0.0)
            slope = 9.85 - 0.1 * physical_z + 0.01 * physical_z**2
            fits.append(
                {
                    "tool": tool,
                    "z_mm": z_mm,
                    "slope_u_px_per_mm": slope,
                    "u_x_correlation_coefficient": 0.999,
                }
            )

    next(fit for fit in fits if fit["tool"] == "T0" and fit["z_mm"] == 3.5)[
        "u_x_correlation_coefficient"
    ] = 0.2
    next(fit for fit in fits if fit["tool"] == "T1" and fit["z_mm"] == 2.0)[
        "slope_u_px_per_mm"
    ] += 1.0

    result = module.estimate_tool_z_delta(fits)

    assert result["available"] is True
    assert result["t1_z_delta_mm"] == pytest.approx(expected_delta, abs=0.02)
    assert result["rms_slope_px_per_mm"] < 1.0e-6
    assert {row["reason"] for row in result["excluded_rows"]} == {
        "bad_u_x_correlation",
        "shared_curve_residual_outlier",
    }


def test_printer_install_paths_include_scipy():
    stage_dir = FILES.parent
    install_sources = (
        stage_dir / "00-packages",
        stage_dir / "01-run-chroot.sh",
        REPO_ROOT / "klipper_setup" / "klipper_config" / "deploy_webcam_vision.sh",
        REPO_ROOT / "klipper_setup" / "klipper_config" / "deploy_vision_code.sh",
    )

    for source in install_sources:
        assert "python3-scipy" in source.read_text(encoding="utf-8")


def test_analysis_writes_raw_records_and_two_plots(tmp_path, monkeypatch):
    module = _module()
    assert len(module.PLOT_COLORS) >= 8
    assert len(set(module.PLOT_COLORS)) == len(module.PLOT_COLORS)
    frames = []
    for seq, (tool, x_mm, y_mm, z_mm) in enumerate(
        (
            ("T0", 173.0, -14.3, 0.5),
            ("T0", 178.0, -14.3, 0.5),
            ("T0", 183.0, -14.3, 0.5),
            ("T0", 173.0, -14.3, 4.0),
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
    decoded_refs = []
    live_during_detection = []
    real_imread = module.cv2.imread

    def imread(path, flags):
        image = real_imread(path, flags)
        decoded_refs.append(weakref.ref(image))
        return image

    def detect(_image):
        index = next(fiducial_calls)
        live_during_detection.append(
            sum(reference() is not None for reference in decoded_refs)
        )
        if index == 5:
            raise module.FourFiducialError("synthetic miss")
        return {
            "centers_px": [[90.0, 90.0], [110.0, 90.0], [90.0, 110.0], [110.0, 110.0]],
            "radii_px": [4.0, 4.0, 4.0, 4.0],
        }

    def localize(_paths, *, frames, roi_centers_px):
        return {
            "registrations": [
                {
                    "seq": index,
                    "center_px": [120.0 + 5.0 * index, 80.0 + index],
                    "localization_method": "bright_circle_roi_v1",
                    "roi_px": [80, 40, 160, 120],
                    "prior_center_px": roi_centers_px[index].tolist(),
                    "bright_circle_score": 60.0,
                    "bright_circle_radius_px": 10.0,
                    "row_residual_px": 0.0,
                    "trajectory_consensus": {
                        "inlier_count": 4,
                        "sample_count": 4,
                        "inlier_rms_px": 0.0,
                    },
                    "trajectory_consensus_inlier": True,
                    "trajectory_consensus_residual_px": 0.0,
                }
                for index, _frame in enumerate(frames)
            ]
        }

    monkeypatch.setattr(module, "detect_four_fiducials", detect)
    monkeypatch.setattr(module, "localize_bright_nozzle_tip_grid", localize)
    monkeypatch.setattr(module.cv2, "imread", imread)

    references = {
        "t0": {"nozzle_image_prior": _prior()},
        "t1": {"nozzle_image_prior": _prior()},
    }

    result = module.analyze(
        paths,
        tmp_path / "artifacts",
        frames=frames,
        references=references,
        acquisition_calibration={"tool_xy_endstops_mm": {}},
    )

    assert result["accepted"] is True
    assert len(result["records"]) == len(frames)
    assert result["records"][0]["nozzle_uv_px"] == [120.0, 80.0]
    assert result["records"][5]["fiducials_detected"] is False
    assert result["records"][5]["nozzle_uv_px"] is None
    assert not (tmp_path / "artifacts" / "tool_xz_sweep_overlays").exists()
    assert (tmp_path / "artifacts" / "tool_xz_sweep_u_vs_x.png").is_file()
    assert (tmp_path / "artifacts" / "tool_xz_sweep_u_slope_vs_z.png").is_file()
    assert (tmp_path / "artifacts" / "tool_xz_sweep_shared_z_fit.png").is_file()
    assert set(result["artifacts"]) == {
        "bright_circle_gate_comparison",
        "tool_xz_sweep_u_vs_x",
        "tool_xz_sweep_u_slope_vs_z",
        "tool_xz_sweep_shared_z_fit",
        "fit_strategy_comparison",
        "fit_strategy_comparison_plot",
    }
    fits = result["u_x_linear_fits"]
    t0_fit = next(fit for fit in fits if fit["tool"] == "T0" and fit["z_mm"] == 0.5)
    assert t0_fit["slope_u_px_per_mm"] == pytest.approx(1.0)
    assert t0_fit["sample_count"] == 3
    assert t0_fit["fit_method"] == "huber_irls"
    assert all(
        "point_diagnostics" in fit
        for fit in fits
        if fit["slope_u_px_per_mm"] is not None
    )
    assert (
        result["fit_strategy_comparison"]["strategies"]["huber_irls_plus_huber"][
            "shared_z_curve_fit"
        ]["available"]
        is False
    )
    assert any(fit["slope_u_px_per_mm"] is None for fit in fits)
    assert result["shared_z_curve_fit"]["available"] is False
    assert result["warnings"]
    assert live_during_detection == [1, 1, 1, 1, 1, 1]
