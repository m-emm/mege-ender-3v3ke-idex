import hashlib
import importlib.util
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml


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
FIXTURE = Path(__file__).parent / "fixtures" / "tool_xy_measurement"


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_tool_xy_calibration_test",
        FILES / "vision_tool_xy_calibration.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _definition(tool):
    registry = json.loads((FILES / "vision_job_types.json").read_text())
    return registry["job_types"][f"idex_tool_xy_measure_{tool.lower()}"]


def _inputs(tool):
    return {
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
        f"{tool.lower()}_red_marker_offset": {
            "offset_mm": 20.0,
            "reference_commanded_x_mm": 193.0,
            "image_line_model": {
                "model": "linear_commanded_x_to_image_uv_v1",
                "coefficients_px": [[-1444.0, 100.0], [8.0, 0.0]],
            },
            "image_line_capture_y_mm": -13.0,
            "quality": {
                "tool_axis_vectors_px_per_mm": {
                    "T0": [8.0, 0.0],
                    "T1": [8.0, 0.0],
                }
            },
        },
    }


def _resolved():
    return {
        "axis_minimum": [-80.0, -14.8, 0.0],
        "axis_maximum": [355.0, 296.0, 300.0],
        "active_tool_calibration": {
            "tool_xy_endstops_mm": {
                "t0": {"x": -77.635, "y": -14.8},
                "t1": {"x": 351.739, "y": -13.8},
            },
            "tool_y_offsets_mm": {"t0": 0.0, "t1": -1.0},
        },
    }


@pytest.mark.parametrize(
    ("tool", "expected_command_y"),
    [("T0", -14.3), ("T1", -13.3)],
)
def test_prepare_derives_per_tool_command_y_with_one_physical_gap(
    tool, expected_command_y
):
    module = _module()

    result = module.prepare_measurement(
        _definition(tool),
        input_values=_inputs(tool),
        resolved=_resolved(),
    )

    assert result["reference"]["capture_y_mm"] == expected_command_y
    assert result["reference"]["internal_capture_y_mm"] == -14.3
    assert result["reference"]["capture_endstop_gap_mm"] == 0.5
    offsets = _definition(tool)["x_offsets_from_bed_tab_mm"]
    assert len(result["frames"]) == len(offsets)
    assert [frame["x_mm"] for frame in result["frames"]] == [
        173.0 + offset for offset in offsets
    ]
    assert {
        tuple(frame["commanded_position_mm"][1:]) for frame in result["frames"]
    } == {(expected_command_y, 0.5)}


def test_prepare_rejects_invalid_gap_offset_and_physical_limit():
    module = _module()
    definition = _definition("T1")

    bad_gap = json.loads(json.dumps(definition))
    bad_gap["capture_endstop_gap_mm"] = 0
    with pytest.raises(module.ToolXYError, match="beyond the Y endstop"):
        module.prepare_measurement(
            bad_gap,
            input_values=_inputs("T1"),
            resolved=_resolved(),
        )

    bad_offset = _resolved()
    bad_offset["active_tool_calibration"]["tool_y_offsets_mm"]["t1"] = -0.5
    with pytest.raises(module.ToolXYError, match="does not equal"):
        module.prepare_measurement(
            definition,
            input_values=_inputs("T1"),
            resolved=bad_offset,
        )

    bad_limit = _resolved()
    bad_limit["axis_minimum"][1] = -14.0
    with pytest.raises(module.ToolXYError, match="outside loaded limits"):
        module.prepare_measurement(
            definition,
            input_values=_inputs("T1"),
            resolved=bad_limit,
        )


@pytest.mark.parametrize("case", ["missing", "wrong_model", "wrong_shape"])
def test_prepare_requires_valid_red_marker_image_line_model(case):
    module = _module()
    inputs = _inputs("T0")
    marker = inputs["t0_red_marker_offset"]
    if case == "missing":
        marker.pop("image_line_model")
    elif case == "wrong_model":
        marker["image_line_model"]["model"] = "wrong"
    else:
        marker["image_line_model"]["coefficients_px"] = [
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0],
        ]
    with pytest.raises(module.ToolXYError, match="red-marker image line model"):
        module.prepare_measurement(
            _definition("T0"),
            input_values=inputs,
            resolved=_resolved(),
        )


def test_marker_image_line_model_predicts_capture_y_adjusted_center():
    module = _module()
    coefficients = np.asarray([[10.0, 20.0], [4.0, -2.0]])
    center = module._marker_image_center_at_x(
        coefficients,
        193.0,
        source_capture_y_mm=-13.0,
        capture_y_mm=-14.0,
        image_y_vector_px_per_mm=np.asarray([-0.5, -10.0]),
    )
    np.testing.assert_allclose(center, [782.5, -356.0])


def test_prepare_accepts_configured_capture_y_and_commanded_z():
    module = _module()
    definition = json.loads(json.dumps(_definition("T1")))
    definition.pop("capture_endstop_gap_mm")
    definition["capture_y_mm"] = -13.1
    definition["commanded_z_mm"] = 1.25

    result = module.prepare_measurement(
        definition,
        input_values=_inputs("T1"),
        resolved=_resolved(),
    )

    assert result["reference"]["capture_y_mm"] == -13.1
    assert result["reference"]["commanded_z_mm"] == 1.25
    assert {frame["commanded_position_mm"][2] for frame in result["frames"]} == {1.25}


def test_tool_xy_gcode_homes_and_returns_to_t0():
    module = _module()
    definition = _definition("T1")
    prepared = module.prepare_measurement(
        definition,
        input_values=_inputs("T1"),
        resolved=_resolved(),
    )
    manifest = {
        "frames": prepared["frames"],
        "motion": {"resolved_pose": {"safe_tool_change_z_mm": 9.0}},
    }

    lines = module.build_acquisition_gcode(
        "tool-xy-test",
        "sha256:manifest",
        "sha256:gcode",
        manifest,
        definition,
    ).splitlines()

    assert lines[:4] == [
        "; vision calibration job tool-xy-test",
        "G28",
        "G90",
        (
            "VISION_JOB_BEGIN JOB=tool-xy-test "
            "MANIFEST_HASH=sha256:manifest GCODE_HASH=sha256:gcode"
        ),
    ]
    assert lines.count("T1") == 1
    assert lines[-4] == "T0"
    assert sum(line.startswith("VISION_CAPTURE_SYNC") for line in lines) == len(
        definition["x_offsets_from_bed_tab_mm"]
    )
    assert all("Z0.500000" in line for line in lines if line.startswith("G1 Z0."))


def _analysis_frames(count=5):
    frames = []
    for seq, x_mm in enumerate([100.0, 105.0, 110.0, 115.0, 120.0][:count]):
        y_mm = -14.0 + seq
        frames.append(
            {
                "seq": seq,
                "frame": f"frame_{seq}",
                "tool": "T0",
                "x_mm": x_mm,
                "y_mm": y_mm,
                "z_mm": 0.5,
                "expected_marker_pixel_px": [100.0, 100.0],
                "commanded_position_mm": [x_mm, y_mm, 0.5],
            }
        )
    return frames


def test_analysis_cancels_commanded_x_and_y_and_rejects_a_datum_outlier(
    tmp_path, monkeypatch
):
    module = _module()
    frames = _analysis_frames()
    paths = []
    for frame in frames:
        path = tmp_path / f"{frame['frame']}.jpg"
        assert cv2.imwrite(str(path), np.full((240, 320, 3), 32, dtype=np.uint8))
        paths.append(path)

    fiducials = {
        "centers_px": [[90.0, 90.0], [110.0, 90.0], [90.0, 110.0], [110.0, 110.0]],
        "radii_px": [4.0, 4.0, 4.0, 4.0],
    }
    monkeypatch.setattr(
        module,
        "detect_four_fiducials",
        lambda _image, **_kwargs: fiducials,
    )

    def localize(_paths, *, frames, **_kwargs):
        registrations = []
        for index, frame in enumerate(frames):
            x_datum = 50.0 if index != 4 else 52.0
            y_datum = -20.0
            delta = [
                float(frame["commanded_position_mm"][0]) - x_datum,
                y_datum - float(frame["commanded_position_mm"][1]),
            ]
            registrations.append(
                {
                    "seq": index,
                    "tool": "T0",
                    "x_mm": frame["x_mm"],
                    "z_mm": 0.5,
                    "center_px": (np.asarray([100.0, 100.0]) + delta).tolist(),
                    "localization_method": "bright_circle_roi_v1",
                    "bright_circle_score": 100.0,
                    "bright_circle_radius_px": 8.0,
                    "row_residual_px": 0.1,
                    "trajectory_consensus_inlier": True,
                    "trajectory_consensus": {
                        "inlier_count": 5,
                        "sample_count": 5,
                        "inlier_rms_px": 0.1,
                    },
                    "quality_gate": {
                        "accepted": True,
                        "reasons": [],
                    },
                }
            )
        return {"registrations": registrations}

    monkeypatch.setattr(
        module, "localize_bright_nozzle_tip_from_marker_prior_grid", localize
    )
    acquisition = _resolved()["active_tool_calibration"]
    result = module.analyze_measurement(
        paths,
        tmp_path / "artifacts",
        frames=frames,
        reference={
            "tool": "T0",
            "image_x_vector_px_per_mm": [1.0, 0.0],
            "image_y_vector_px_per_mm": [0.0, 1.0],
            "marker_x_vector_px_per_mm": [1.0, 0.0],
            "corner_printer_xy_mm": [0.0, 0.0],
            "fiducial_reference_printer_xy_mm": [0.0, 0.0],
            "marker_offset_mm": 0.0,
            "marker_reference_commanded_x_mm": 0.0,
            "marker_image_line_model": {
                "model": "linear_commanded_x_to_image_uv_v1",
                "coefficients_px": [[0.0, 0.0], [1.0, 1.0]],
            },
            "marker_image_line_capture_y_mm": -14.0,
        },
        acquisition_calibration=acquisition,
    )

    assert result["accepted"], result["reasons"]
    assert result["accepted_count"] == 4
    assert result["accepted_x_span_mm"] == 15.0
    assert result["x_datum_mm"] == 50.0
    assert result["y_datum_mm"] == -20.0
    assert not result["records"][-1]["accepted"]
    assert "datum residual" in result["records"][-1]["rejection_reasons"][-1]
    measurement_fact = module.build_measurement_fact(
        result,
        acquisition_calibration=acquisition,
    )
    assert {
        key: measurement_fact[key]
        for key in (
            "x_datum_mm",
            "y_datum_mm",
            "acquisition_endstop_xy_mm",
            "commanded_z_mm",
        )
    } == {
        "x_datum_mm": 50.0,
        "y_datum_mm": -20.0,
        "acquisition_endstop_xy_mm": [-77.635, -14.8],
        "commanded_z_mm": 0.5,
    }
    prior = measurement_fact["nozzle_image_prior"]
    assert prior["model"] == "linear_commanded_x_to_image_uv_v1"
    assert len(prior["coefficients_px"]) == 2
    assert set(prior) == {"model", "coefficients_px"}


def _fact_value(fact_set, fact_name):
    return next(
        fact["value"] for fact in fact_set["facts"] if fact["name"] == fact_name
    )


@pytest.mark.parametrize("tool", ["T0", "T1"])
def test_real_images_use_bright_circle_xy_localization(tool, tmp_path):
    module = _module()
    fixture = json.loads((FIXTURE / "fixture.json").read_text())
    case = fixture["cases"][tool]
    directory = FIXTURE / case["directory"]
    source_manifest = json.loads((directory / "source_manifest.json").read_text())
    frames = [
        frame
        for frame in source_manifest["frames"]
        if int(frame["seq"]) in set(case["source_sequences"])
    ]
    frame_paths = [directory / f"{frame['frame']}.jpg" for frame in frames]
    for frame, image_path in zip(frames, frame_paths):
        sidecar = json.loads((directory / f"{frame['frame']}.json").read_text())
        assert (
            sidecar["sha256"]
            == "sha256:" + hashlib.sha256(image_path.read_bytes()).hexdigest()
        )
        assert sidecar["commanded_position_mm"] == frame["commanded_position_mm"]

    fine_reference = source_manifest["fine_reference"]
    source_facts = json.loads(
        (
            FIXTURE / fixture["source_fact_sets"]["red_marker_and_mapping"]["path"]
        ).read_text()
    )
    mapping = _fact_value(
        source_facts, "camera.nozzle_cam.bed_fiducial.printer_xy_mapping"
    )
    marker = _fact_value(
        source_facts, f"tool.{tool.lower()}.red_marker_to_bed_tab_x_mm"
    )
    marker_design = np.column_stack(
        (
            np.ones(len(frames), dtype=np.float64),
            np.asarray([float(frame["x_mm"]) for frame in frames]),
        )
    )
    marker_centers = np.asarray(
        [frame["expected_marker_pixel_px"] for frame in frames], dtype=np.float64
    )
    marker_coefficients, _, _, _ = np.linalg.lstsq(
        marker_design, marker_centers, rcond=None
    )
    result = module.analyze_measurement(
        frame_paths,
        tmp_path / tool.lower(),
        frames=frames,
        reference={
            "tool": tool,
            "image_x_vector_px_per_mm": fine_reference[
                "fiducial_x_vector_at_fine_capture_px_per_mm"
            ],
            "image_y_vector_px_per_mm": fine_reference["image_y_axis_vector_px_per_mm"],
            "marker_x_vector_px_per_mm": marker["quality"][
                "tool_axis_vectors_px_per_mm"
            ][tool],
            "corner_printer_xy_mm": mapping["corner_printer_xy_mm"],
            "fiducial_reference_printer_xy_mm": mapping[
                "fiducial_reference_printer_xy_mm"
            ],
            "marker_offset_mm": marker["offset_mm"],
            "marker_reference_commanded_x_mm": marker["reference_commanded_x_mm"],
            "marker_image_line_model": {
                "model": "linear_commanded_x_to_image_uv_v1",
                "coefficients_px": marker_coefficients.tolist(),
            },
            "marker_image_line_capture_y_mm": float(
                frames[0]["commanded_position_mm"][1]
            ),
        },
        acquisition_calibration=source_manifest["acquisition_calibration"],
        require_locator=False,
    )

    localized_records = [
        record for record in result["records"] if record.get("center_px") is not None
    ]
    assert len(localized_records) >= 2
    assert all(
        record["localization_method"] == "bright_circle_roi_v1"
        for record in localized_records
    )
    if result["accepted"]:
        assert np.all(np.isfinite([result["x_datum_mm"], result["y_datum_mm"]]))
    else:
        assert result["reasons"]
    assert set(result["artifacts"]) == {
        "tool_xy_measurement",
        "tool_xy_overlay_01",
        "tool_xy_overlay_02",
        "tool_xy_overlay_03",
    }


def test_real_fixture_retains_exact_source_fact_sets():
    fixture = json.loads((FIXTURE / "fixture.json").read_text())
    for source in fixture["source_fact_sets"].values():
        fact_set = json.loads((FIXTURE / source["path"]).read_text())
        assert fact_set["fact_set_hash"] == source["fact_set_hash"]
    bed = json.loads(
        (FIXTURE / fixture["source_fact_sets"]["bed_metric"]["path"]).read_text()
    )
    red = json.loads(
        (
            FIXTURE / fixture["source_fact_sets"]["red_marker_and_mapping"]["path"]
        ).read_text()
    )
    assert _fact_value(bed, "camera.nozzle_cam.bed_fiducial.local_metric_model")
    assert _fact_value(red, "camera.nozzle_cam.bed_fiducial.printer_xy_mapping")
    assert _fact_value(red, "tool.t0.red_marker_to_bed_tab_x_mm")
    assert _fact_value(red, "tool.t1.red_marker_to_bed_tab_x_mm")


def _replay_run_id():
    return (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + f"-{uuid.uuid4().hex[:8]}"
    )


@pytest.mark.parametrize("tool", ["T0", "T1"])
def test_bright_circle_xy_replay_writes_inspection_overlays(tool):
    """Replay XY frames with the red-marker line prior and retain every overlay."""
    module = _module()
    fixture = json.loads((FIXTURE / "fixture.json").read_text())
    case = fixture["cases"][tool]
    directory = FIXTURE / case["directory"]
    source_manifest = json.loads((directory / "source_manifest.json").read_text())
    frames = [
        frame
        for frame in source_manifest["frames"]
        if int(frame["seq"]) in set(case["source_sequences"])
    ]
    frame_paths = [directory / f"{frame['frame']}.jpg" for frame in frames]
    source_facts = json.loads(
        (FIXTURE / fixture["source_fact_sets"]["red_marker_and_mapping"]["path"]).read_text()
    )
    mapping = _fact_value(
        source_facts, "camera.nozzle_cam.bed_fiducial.printer_xy_mapping"
    )
    marker = _fact_value(
        source_facts, f"tool.{tool.lower()}.red_marker_to_bed_tab_x_mm"
    )
    marker_design = np.column_stack(
        (
            np.ones(len(frames), dtype=np.float64),
            np.asarray([float(frame["x_mm"]) for frame in frames]),
        )
    )
    marker_centers = np.asarray(
        [frame["expected_marker_pixel_px"] for frame in frames], dtype=np.float64
    )
    marker_coefficients, _, _, _ = np.linalg.lstsq(
        marker_design, marker_centers, rcond=None
    )
    fine_reference = source_manifest["fine_reference"]
    reference = {
        "tool": tool,
        "image_x_vector_px_per_mm": fine_reference[
            "fiducial_x_vector_at_fine_capture_px_per_mm"
        ],
        "image_y_vector_px_per_mm": fine_reference[
            "image_y_axis_vector_px_per_mm"
        ],
        "marker_x_vector_px_per_mm": marker["quality"][
            "tool_axis_vectors_px_per_mm"
        ][tool],
        "corner_printer_xy_mm": mapping["corner_printer_xy_mm"],
        "fiducial_reference_printer_xy_mm": mapping[
            "fiducial_reference_printer_xy_mm"
        ],
        "marker_offset_mm": marker["offset_mm"],
        "marker_reference_commanded_x_mm": marker["reference_commanded_x_mm"],
        "marker_image_line_model": {
            "model": "linear_commanded_x_to_image_uv_v1",
            "coefficients_px": marker_coefficients.tolist(),
        },
        "marker_image_line_capture_y_mm": float(
            frames[0]["commanded_position_mm"][1]
        ),
    }
    run_root = (
        REPO_ROOT
        / "output"
        / "vision_tool_xy_bright_circle_replay"
        / "runs"
        / _replay_run_id()
        / tool.lower()
    )
    artifact_dir = run_root / "artifacts"
    result = module.analyze_measurement(
        frame_paths,
        artifact_dir,
        frames=frames,
        reference=reference,
        acquisition_calibration=source_manifest["acquisition_calibration"],
        require_locator=False,
    )
    (run_root / "result.json").parent.mkdir(parents=True, exist_ok=True)
    (run_root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name, artifact in sorted(result["artifacts"].items()):
        path = Path(artifact["path"])
        assert path.exists(), f"missing {name}: {path}"
        _logger.info("Overlay %s", path.resolve())

    _logger.info(
        "XY replay tool=%s accepted=%s accepted_count=%d reasons=%s",
        tool,
        result["accepted"],
        result["accepted_count"],
        result["reasons"],
    )
    assert all(
        record.get("localization_method") == "bright_circle_roi_v1"
        for record in result["records"]
        if record.get("center_px") is not None
    )


def _candidate_source(tool, datum_xy, fingerprint="active-fingerprint"):
    endstops = {
        "t0": {"x": -77.635, "y": -14.8},
        "t1": {"x": 351.739, "y": -13.8},
    }
    return {
        "fact_set_hash": f"sha256:{tool.lower()}-measurement",
        "value": {
            "x_datum_mm": datum_xy[0],
            "y_datum_mm": datum_xy[1],
            "acquisition_endstop_xy_mm": [
                endstops[tool.lower()]["x"],
                endstops[tool.lower()]["y"],
            ],
            "commanded_z_mm": 0.5,
        },
        "dependencies": [
            {
                "fact_name": "camera.nozzle_cam.bed_fiducial.local_metric_model",
                "fact_set_hash": "sha256:metric",
            },
            {
                "fact_name": "camera.nozzle_cam.bed_fiducial.printer_xy_mapping",
                "fact_set_hash": "sha256:mapping",
            },
        ],
        "active_printer_fingerprint": fingerprint,
        "priors_hash": "sha256:priors",
        "acquisition_calibration": {
            "active_fingerprint": fingerprint,
            "tool_xy_endstops_mm": endstops,
            "tool_y_offsets_mm": {"t0": 0.0, "t1": -1.0},
        },
    }


def test_candidate_corrects_both_t1_endstop_signs_and_preserves_calib(tmp_path):
    module = _module()
    calib_path = tmp_path / "calib.yaml"
    calib_path.write_text(
        yaml.safe_dump(
            {
                "unrelated": {"keep": "this"},
                "tools": {
                    "t0": {
                        "x_endstop": -77.635,
                        "y_endstop": -14.8,
                        "z_endstop": 293.75,
                    },
                    "t1": {
                        "x_endstop": 350.516,
                        "y_endstop": -15.82,
                        "z_endstop": 293.65,
                    },
                },
            },
            sort_keys=False,
        )
    )
    active = {
        "active_fingerprint": "active-fingerprint",
        "tool_xy_endstops_mm": {
            "t0": {"x": -77.635, "y": -14.8},
            "t1": {"x": 351.739, "y": -13.8},
        },
    }
    result = module.calculate_candidate(
        tmp_path / "analysis" / "artifacts",
        t0_source=_candidate_source("T0", [166.353885, -14.862874]),
        t1_source=_candidate_source("T1", [166.895501, -14.984996]),
        active_calibration=active,
        calib=module.CalibDAO(calib_path=calib_path),
    )

    np.testing.assert_allclose(
        result["alignment_error_xy_mm"], [0.541616, -0.122122], atol=1e-6
    )
    np.testing.assert_allclose(
        result["suggested_t1_endstop_xy_mm"],
        [351.197384, -13.677878],
        atol=1e-6,
    )
    candidate = yaml.safe_load(
        (tmp_path / "analysis" / "calib_candidate.yaml").read_text()
    )
    assert candidate["unrelated"] == {"keep": "this"}
    assert candidate["tools"]["t0"]["x_endstop"] == -77.635
    assert candidate["tools"]["t1"]["x_endstop"] == pytest.approx(351.197384)
    assert candidate["tools"]["t1"]["y_endstop"] == pytest.approx(-13.677878)
    assert result["warnings"]
    assert (
        cv2.imread(str(tmp_path / "analysis" / "artifacts" / "tool_xy_candidate.png"))
        is not None
    )
    assert module.build_candidate_fact(result)["x_alignment_error_mm"] == pytest.approx(
        0.541616
    )


def test_candidate_rejects_stale_measurements(tmp_path):
    module = _module()
    calib_path = tmp_path / "calib.yaml"
    calib_path.write_text(
        yaml.safe_dump(
            {
                "tools": {
                    "t0": {"x_endstop": -77.635, "y_endstop": -14.8, "z_endstop": 1},
                    "t1": {"x_endstop": 351.739, "y_endstop": -13.8, "z_endstop": 1},
                }
            }
        )
    )
    with pytest.raises(module.ToolXYError, match="fingerprints do not match"):
        module.calculate_candidate(
            tmp_path / "artifacts",
            t0_source=_candidate_source("T0", [1.0, 2.0]),
            t1_source=_candidate_source("T1", [1.0, 2.0]),
            active_calibration={
                "active_fingerprint": "different",
                "tool_xy_endstops_mm": {
                    "t0": {"x": -77.635, "y": -14.8},
                    "t1": {"x": 351.739, "y": -13.8},
                },
            },
            calib=module.CalibDAO(calib_path=calib_path),
        )
