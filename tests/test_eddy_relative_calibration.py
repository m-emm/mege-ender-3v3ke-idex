import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VISION_PATH = (
    ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "vision_nozzle_align.py"
)
EDDY_PATH = VISION_PATH.with_name("eddy_relative_calibration.py")
CONFIG_PATH = ROOT / "klipper_setup" / "klipper_config" / "printer.cfg"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _target_fit(slope: float, intercept: float, residual: float = 0.01):
    return {
        "ok": True,
        "scale_fit": {
            "ok": True,
            "accepted": True,
            "slope": slope,
            "intercept": intercept,
            "residual_rms": residual,
        },
        "hard_failures": [],
    }


def test_relative_fit_recovers_independent_nozzle_and_eddy_offsets():
    vision = _load(VISION_PATH, "vision_eddy_fit_test")
    bed_scale = 10.0
    nozzle_slope = -0.4
    eddy_slope = -0.38
    bed_feature = -0.1
    nozzle_error = 0.2
    eddy_error = 2.7
    nozzle_intercept = (
        bed_scale + (nozzle_error - bed_feature) * nozzle_slope
    )
    eddy_intercept = bed_scale + (eddy_error - bed_feature) * eddy_slope

    result = vision.validate_eddy_relative_fits(
        bed_scale_px_per_mm=bed_scale,
        bed_fit_residual_px=0.02,
        nozzle_analysis=_target_fit(nozzle_slope, nozzle_intercept),
        eddy_analysis=_target_fit(eddy_slope, eddy_intercept),
        bed_feature_z_mm=bed_feature,
        cad_separation_mm=2.5,
    )

    assert result["ok"] is True
    assert result["nozzle_zero_error_mm"] == pytest.approx(nozzle_error)
    assert result["eddy_zero_error_mm"] == pytest.approx(eddy_error)
    assert result["eddy_above_nozzle_mm"] == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("nozzle", "eddy", "failure"),
    [
        (
            {"ok": False, "hard_failures": ["missing fiducial"], "scale_fit": {}},
            _target_fit(-0.4, 9.0),
            "missing fiducial",
        ),
        (
            _target_fit(-0.4, 9.9),
            _target_fit(0.4, 8.9),
            "disagree in sign",
        ),
        (
            _target_fit(-0.4, 9.9),
            _target_fit(-0.1, 8.9),
            "disagree in magnitude",
        ),
        (
            _target_fit(-0.4, 9.9),
            _target_fit(-0.4, 8.3),
            "vertical separation disagreement",
        ),
    ],
)
def test_relative_fit_rejects_missing_incompatible_or_cad_disagreeing_targets(
    nozzle, eddy, failure
):
    vision = _load(VISION_PATH, f"vision_eddy_reject_{failure.replace(' ', '_')}")
    result = vision.validate_eddy_relative_fits(
        bed_scale_px_per_mm=10.0,
        bed_fit_residual_px=0.02,
        nozzle_analysis=nozzle,
        eddy_analysis=eddy,
        bed_feature_z_mm=-0.1,
        cad_separation_mm=2.5,
    )
    assert result["ok"] is False
    assert failure in "; ".join(result["hard_failures"])


def test_roi_match_reports_ambiguous_repeated_features():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    vision = _load(VISION_PATH, "vision_eddy_ambiguity_test")
    source = np.zeros((180, 260), dtype="float32")
    patch = np.zeros((30, 30), dtype="float32")
    cv2.circle(patch, (15, 15), 10, 1.0, 2)
    cv2.line(patch, (5, 15), (25, 15), 1.0, 2)
    source[60:90, 60:90] = patch
    target = np.zeros_like(source)
    target[60:90, 75:105] = patch
    target[60:90, 155:185] = patch
    match = vision.match_nozzle_z_roi_pair(
        source_feature=source,
        target_feature=target,
        source_roi=(60, 60, 30, 30),
        predicted_delta=(20.0, 0.0),
        search_pad_px=100,
        width=260,
        height=180,
    )
    assert match["accepted"] is True
    assert match["correlation"] > 0.99
    assert match["peak_margin"] < 0.01


def test_eddy_job_manifest_motion_order_hashes_and_center_transform(tmp_path):
    vision = _load(VISION_PATH, "vision_eddy_job_test")
    job = vision.build_eddy_relative_vision_job(
        name="test",
        job_root=tmp_path,
        job_id="eddy_job",
        bed_y_x=-80.4,
        bed_y_y=-14.8,
        bed_y_z=293.75,
        tool_x=195.0,
        tool_y=-14.8,
        travel_z=20.0,
        y_offsets=[0, 5, 10, 15, 20],
        x_offsets=[0, 3, 6, 9, 12],
        z_values=[1, 2, 4, 8],
        bed_feature_z_mm=-0.1,
        current_t0_z_endstop=293.75,
        bed_center_x=117.5,
        bed_center_y=117.5,
        nozzle_to_coil_x=-8.18,
        nozzle_to_coil_y=9.0,
        nozzle_to_coil_z=2.5,
        feedrate=3600,
        settle_time=0.25,
        camera="nozzle_cam",
        profile="analysis",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
    )
    job = vision.job_with_hashes(job)
    manifest = vision.build_manifest(job)
    gcode = vision.render_acquisition_gcode(
        job, manifest_hash=job.manifest_hash, gcode_hash=job.gcode_hash
    )
    assert manifest["kind"] == vision.EDDY_RELATIVE_JOB_KIND
    assert manifest["frame_count"] == 42
    assert {frame["tool"] for frame in manifest["frames"]} == {"T0"}
    assert manifest["measurement_parameters"]["coil_center_command"] == {
        "x": 125.68,
        "y": 108.5,
    }
    assert [
        frame["z_sample"]
        for frame in manifest["frames"]
        if frame.get("phase") == "tool_xz_sweep"
        and frame.get("x_offset") == 0
    ] == [8.0, 4.0, 2.0, 1.0]
    assert [
        frame["z_sample"]
        for frame in manifest["frames"]
        if frame.get("phase") == "tool_yz_sweep"
        and frame.get("y_offset") == 5
    ] == [8.0, 4.0, 2.0, 1.0]
    first_y_move = gcode.index("G1 X195.000 Y-9.800 Z20.000 F3600")
    first_y_capture = gcode.index("FRAME=t0_y5_z8p0")
    assert gcode.rfind("G1 Z20.000 F3600", 0, first_y_move) >= 0
    assert first_y_move < first_y_capture
    assert manifest["frames"][-1]["phase"] == "center_sanity"
    assert "G1 X125.680 Y108.500 Z20.000 F3600" in gcode
    assert "G28" not in gcode
    assert vision.compute_manifest_hash(manifest) == manifest["manifest_hash"]
    assert vision.compute_gcode_hash(gcode) == manifest["gcode_hash"]


def test_generated_eddy_job_id_is_canonical_and_daemon_length_safe(tmp_path):
    vision = _load(VISION_PATH, "vision_eddy_job_id_test")
    job = vision.build_eddy_relative_vision_job(
        name="eddy_relative_cold_20260728_0850_with_a_long_operator_suffix",
        job_root=tmp_path,
        job_id=None,
        bed_y_x=-80.4,
        bed_y_y=-14.8,
        bed_y_z=293.75,
        tool_x=195.0,
        tool_y=-14.8,
        travel_z=20.0,
        y_offsets=[0, 5, 10, 15, 20],
        x_offsets=[0, 3, 6, 9, 12],
        z_values=[1, 2, 4, 8],
        bed_feature_z_mm=-0.1,
        current_t0_z_endstop=293.75,
        bed_center_x=117.5,
        bed_center_y=117.5,
        nozzle_to_coil_x=-8.18,
        nozzle_to_coil_y=9.0,
        nozzle_to_coil_z=2.5,
        feedrate=3600,
        settle_time=0.25,
        camera="nozzle_cam",
        profile="analysis",
        now=datetime(2026, 7, 28, 6, 50, 18, tzinfo=timezone.utc),
    )
    assert len(job.job_id) <= 80
    assert vision.sanitize_name(job.job_id) == job.job_id
    assert job.job_dir == tmp_path / job.job_id


def test_eddy_full_job_uses_manifest_parent_when_analysis_omits_job_dir():
    source = VISION_PATH.read_text(encoding="utf-8")
    function = source[
        source.index("def run_eddy_relative_full_job(") :
        source.index("\ndef html_text(", source.index("def run_eddy_relative_full_job("))
    ]
    assert 'vision_result.get("job_dir")' in function
    assert 'Path(vision_result["manifest_path"]).parent' in function


def test_cold_report_only_macro_has_heater_homing_and_no_save_guards():
    config = CONFIG_PATH.read_text(encoding="utf-8")
    start = config.index("[gcode_macro IDEX_EDDY_RELATIVE_CALIBRATE_COLD]")
    end = config.index("\n[", start + 1)
    macro = config[start:end]
    assert "requires an idle printer" in macro
    assert "requires X/Y/Z homed" in macro
    assert "heater targets to be zero" in macro
    assert 'action_call_remote_method(' in macro
    assert '"idex_eddy_relative_calibrate_cold"' in macro
    assert "SAVE_CONFIG" in macro
    assert "\n    SAVE_CONFIG" not in macro
    assert "nozzle_to_coil_x=-8.180" in macro
    assert "nozzle_to_coil_y=9.000" in macro
    assert "nozzle_to_coil_z=2.500" in macro


def test_drive_current_check_rejects_center_and_safety_lift_outside_limits():
    vision = _load(VISION_PATH, "vision_eddy_drive_current_limits_test")
    with pytest.raises(RuntimeError, match="check X=.*outside configured limits"):
        vision.run_drive_current_check(
            base_url="http://unused",
            center_x=301.0,
            center_y=108.5,
            nozzle_zero_error_mm=0.0,
            axis_minimum=[-5.0, -15.0, -1.0],
            axis_maximum=[300.0, 300.0, 293.75],
        )
    with pytest.raises(RuntimeError, match="safety lift Z=.*outside"):
        vision.run_drive_current_check(
            base_url="http://unused",
            center_x=125.68,
            center_y=108.5,
            nozzle_zero_error_mm=2.0,
            axis_minimum=[-5.0, -15.0, -1.0],
            axis_maximum=[300.0, 300.0, 19.0],
        )


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("vision_jobs/foo.gcode", "vision_jobs/foo.gcode"),
        ("foo.gcode", "vision_jobs/foo.gcode"),
        ("/home/pi/printer_data/gcodes/vision_jobs/foo.gcode", "vision_jobs/foo.gcode"),
    ],
)
def test_virtual_sd_filename_matching_accepts_moonraker_path_variants(
    actual, expected
):
    vision = _load(VISION_PATH, f"vision_eddy_filename_{len(actual)}")
    assert vision.virtual_sd_filename_matches(actual, expected)
    assert not vision.virtual_sd_filename_matches("different.gcode", expected)


def test_safe_schedule_enforces_clearance_limits_and_descending_hops():
    eddy = _load(EDDY_PATH, "eddy_schedule_test")
    schedule = eddy.build_sample_schedule(
        nozzle_zero_error_mm=0.2,
        eddy_above_nozzle_mm=2.5,
        vision_sigma_mm=0.04,
        z_min_mm=-1.0,
        z_max_mm=293.75,
    )
    combined = math.hypot(0.04, eddy.DEFAULT_REPEATABILITY_SIGMA_MM)
    assert schedule["levels"][0] >= 0.5 + 3 * combined
    manifest = eddy.build_sweep_manifest(
        job_id="eddy_job",
        center_x=125.68,
        center_y=108.5,
        schedule=schedule,
        vision_facts_hash="sha256:" + "1" * 64,
        drive_current={
            "active_reg_drive_current": 15,
            "proposed_reg_drive_current": 15,
        },
    )
    manifest, gcode = eddy.finalize_sweep_hashes(manifest)
    lines = gcode.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("VISION_EDDY_SAMPLE_SYNC "):
            continue
        if "APPROACH=descending " in line or "APPROACH=descending_anchor " in line:
            assert lines[index - 1] == "M400"
            assert lines[index - 2].startswith("G1 Z")
            assert lines[index - 2].endswith(" F300")
            assert lines[index - 3] == "M400"
            assert lines[index - 4].startswith("G1 Z")
    canonical_manifest = dict(manifest)
    canonical_manifest["manifest_hash"] = eddy.HASH_PLACEHOLDER
    assert (
        eddy.sha256_prefixed(eddy.canonical_json_bytes(canonical_manifest))
        == manifest["manifest_hash"]
    )
    assert eddy.compute_gcode_hash(gcode) == manifest["gcode_hash"]

    with pytest.raises(RuntimeError, match="fewer than"):
        eddy.build_sample_schedule(
            nozzle_zero_error_mm=10.0,
            eddy_above_nozzle_mm=2.5,
            vision_sigma_mm=0.04,
            z_min_mm=-1.0,
            z_max_mm=293.75,
        )


def _synthetic_records(eddy, *, break_monotonic=False, incomplete=False):
    schedule = eddy.build_sample_schedule(
        nozzle_zero_error_mm=0.2,
        eddy_above_nozzle_mm=2.5,
        vision_sigma_mm=0.04,
        z_min_mm=-1.0,
        z_max_mm=293.75,
    )
    records = []
    for sample in schedule["samples"]:
        gap = float(sample["nozzle_gap"])
        frequency = 12_000_000.0 - gap * 100_000.0
        if break_monotonic and gap >= 2.0:
            frequency += 300_000.0
        raw = [frequency + ((index % 5) - 2) for index in range(100)]
        median, mad = eddy.median_mad(raw)
        records.append(
            {
                **sample,
                "raw_frequency_hz": raw,
                "median_frequency_hz": median,
                "mad_frequency_hz": mad,
                "sample_count": 20 if incomplete and sample["seq"] == 2 else 100,
                "coil_temperature_c": 36.5 + sample["seq"] * 0.0001,
                "mcu_temperature_c": 40.1,
                "captured_at_utc": "2026-07-27T00:00:00+00:00",
                "errors": 0,
                "overflows": 0,
                "complete": not (incomplete and sample["seq"] == 2),
            }
        )
    manifest = {"samples": schedule["samples"]}
    return records, manifest


def test_frequency_analysis_accepts_synchronized_complete_monotonic_data():
    eddy = _load(EDDY_PATH, "eddy_analysis_accept_test")
    records, manifest = _synthetic_records(eddy)
    result = eddy.analyze_records(records, manifest)
    assert result["accepted"] is True
    assert result["usable_level_count"] >= 12
    assert result["usable_span_mm"] >= 1.0
    assert result["reference_drift_accepted"] is True
    candidate = result["candidate"]
    assert candidate["active"] is False
    lower, upper = candidate["usable_range_mm"]
    assert lower < candidate["descend_z"] < upper


def test_analysis_artifacts_include_temperature_and_reference_drift_plots(
    tmp_path,
):
    pytest.importorskip("cv2")
    eddy = _load(EDDY_PATH, "eddy_analysis_artifacts_test")
    records, manifest = _synthetic_records(eddy)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "sweep.gcode").write_text("M400\n", encoding="utf-8")
    for record in records:
        raw_record = {
            "samples": [
                [index / eddy.SAMPLE_RATE_HZ, frequency, record["commanded_z"]]
                for index, frequency in enumerate(record["raw_frequency_hz"])
            ],
            "captured_at_utc": record["captured_at_utc"],
            "errors": record["errors"],
            "overflows": record["overflows"],
            "complete": record["complete"],
            "temperatures": {
                "coil": {"temperature": record["coil_temperature_c"]},
                "mcu": {"temperature": record["mcu_temperature_c"]},
            },
        }
        (raw_dir / f"{record['seq']:03d}_{record['sample']}.json").write_text(
            json.dumps(raw_record), encoding="utf-8"
        )

    analysis = eddy.write_analysis_artifacts(tmp_path, manifest)

    plots = analysis["artifacts"]["plots"]
    assert set(plots) == {
        "frequency_vs_nozzle_gap",
        "frequency_vs_coil_gap",
        "repeatability_and_direction",
        "temperature",
        "reference_frequency_drift",
    }
    assert all(Path(path).is_file() for path in plots.values())
    assert analysis["candidate"]["active"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"break_monotonic": True}, "frequency stops decreasing"),
        ({"incomplete": True}, "incomplete"),
    ],
)
def test_frequency_analysis_rejects_monotonic_or_sensor_data_failures(
    kwargs, message
):
    eddy = _load(EDDY_PATH, f"eddy_analysis_reject_{message.replace(' ', '_')}")
    records, manifest = _synthetic_records(eddy, **kwargs)
    result = eddy.analyze_records(records, manifest)
    assert result["accepted"] is False
    assert message in "; ".join(result["hard_failures"])
