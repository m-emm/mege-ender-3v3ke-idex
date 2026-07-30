import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES_DIR = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
MODULE_PATH = FILES_DIR / "eddy_z_diagnostic.py"


def _load_module():
    sys.path.insert(0, str(FILES_DIR))
    spec = importlib.util.spec_from_file_location("eddy_z_diagnostic_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(module):
    schedule = module.build_sample_schedule()
    manifest = module.build_sweep_manifest(
        job_id="synthetic_diagnostic",
        schedule=schedule,
        active_config_fingerprint="a" * 64,
        x_offset=-8.18,
        y_offset=9.0,
        nozzle_to_coil_z=2.5,
    )
    manifest, gcode = module.finalize_sweep_hashes(manifest)
    return schedule, manifest, gcode


def _synthetic_records(module, manifest):
    records = []
    for sample in manifest["samples"]:
        value = float(sample["commanded_z"])
        if sample["phase"] == "reference":
            value = 3.0 + {"before": 0.0, "mid": 0.004, "after": 0.008}[sample["label"]]
        elif sample["phase"] == "stationary":
            value = 2.0 + int(sample["cycle"]) * 0.0002
        elif sample["phase"] == "hysteresis":
            value = float(sample["target_z"])
            if sample["approach"] == "ascending":
                value += 0.03
        elif sample["phase"] == "small_step":
            requested = float(sample["requested_delta"])
            if sample["role"] == "baseline":
                value = 2.0
            elif abs(requested) < 0.04:
                value = 2.0 + math.copysign(0.0005, requested)
            else:
                value = 2.0 + requested - math.copysign(0.012, requested)
        elif sample["phase"] == "homing":
            cycle = int(sample["cycle"])
            sensor_x = float(sample["sensor_x"])
            value = (
                1.0 + cycle * 0.001 + (sensor_x - 117.5) * (0.0002 + cycle * 0.000001)
            )
        points = [
            [
                index / 400.0,
                1_000_000.0 - value * 10_000.0,
                value + (-1) ** index * 0.0005,
            ]
            for index in range(100)
        ]
        heights = [point[2] for point in points]
        records.append(
            {
                **sample,
                "sample_count": len(points),
                "raw_samples": points,
                "median_frequency_hz": 1_000_000.0 - value * 10_000.0,
                "mad_frequency_hz": 5.0,
                "median_height_mm": value,
                "mad_height_mm": 0.0005,
                "stddev_height_mm": 0.0005,
                "errors": 0,
                "overflows": 0,
                "complete": True,
                "temperatures": {
                    "coil": {"temperature": 31.0 + sample["seq"] * 0.001},
                    "mcu": {"temperature": 34.0},
                },
            }
        )
    return records


def _mesh():
    matrix = []
    for row in range(5):
        values = []
        for column in range(5):
            plane = 0.02 * column - 0.01 * row
            warp = 0.006 if row == 2 and column == 2 else 0.0
            values.append(plane + warp)
        matrix.append(values)
    return {
        "probed_matrix": matrix,
        "mesh_min": [37.5, 37.5],
        "mesh_max": [197.5, 197.5],
    }


def _status():
    return {
        "webhooks": {"state": "ready"},
        "print_stats": {"state": "standby"},
        "toolhead": {"homed_axes": "xyz"},
        "heater_bed": {"target": 0.0, "temperature": 25.0},
        "extruder": {"target": 0.0, "temperature": 25.0},
        "extruder1": {"target": 0.0, "temperature": 25.0},
        "configfile": {
            "save_config_pending": False,
            "settings": {
                "stepper_x": {"position_min": -80.4, "position_max": 235.0},
                "stepper_y": {"position_min": -15.82, "position_max": 235.0},
                "stepper_z": {"position_min": 0.0, "position_max": 293.75},
                "probe_eddy_current btt_eddy": {
                    "reg_drive_current": 15,
                    "calibrate": ",".join(
                        f"{index / 10:.1f}:{1_000_000 - index * 1000}"
                        for index in range(20)
                    ),
                },
            },
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "a" * 64},
    }


def test_schedule_is_hashed_and_keeps_all_lateral_motion_at_z5():
    module = _load_module()
    schedule, manifest, gcode = _manifest(module)

    assert len(schedule["samples"]) == 134
    assert sum(sample["phase"] == "reference" for sample in schedule["samples"]) == 3
    assert sum(sample["phase"] == "hysteresis" for sample in schedule["samples"]) == 36
    assert sum(sample["phase"] == "small_step" for sample in schedule["samples"]) == 60
    assert sum(sample["phase"] == "homing" for sample in schedule["samples"]) == 30
    assert gcode.count("G28 Z") == 10
    assert "BED_MESH_CALIBRATE" in gcode
    assert "SAVE_CONFIG" not in "\n".join(
        line for line in gcode.splitlines() if not line.startswith(";")
    )
    assert manifest["manifest_hash"].startswith("sha256:")
    assert manifest["gcode_hash"] == module.compute_gcode_hash(gcode)
    module.validate_schedule_safety(
        schedule,
        x_min=-80.4,
        x_max=235.0,
        y_min=-15.82,
        y_max=235.0,
        z_min=0.0,
        z_max=293.75,
    )
    assert schedule["center_nozzle"] == {"x": 125.68, "y": 108.5}
    baselines = [
        sample
        for sample in schedule["samples"]
        if sample["phase"] == "small_step" and sample["role"] == "baseline"
    ]
    assert all(
        (
            sample["pre_moves"][0]["z"] > module.SMALL_STEP_BASE_MM
            if sample["requested_delta"] > 0
            else sample["pre_moves"][0]["z"] < module.SMALL_STEP_BASE_MM
        )
        for sample in baselines
    )


def test_preflight_checks_calibration_pending_state_temperature_and_fingerprint():
    module = _load_module()
    schedule = module.build_sample_schedule()
    status = _status()

    assert module.preflight(status, expected_fingerprint="a" * 64, schedule=schedule)[
        "ok"
    ]

    cases = [
        ("save_config_pending", True, "save_config_pending"),
        (
            "heater_bed.temperature",
            36.0,
            "heater_bed is above",
        ),
        (
            "probe_eddy_current btt_eddy.calibrate",
            "",
            "calibrate curve is missing",
        ),
    ]
    for dotted_path, value, message in cases:
        changed = json.loads(json.dumps(status))
        target = changed
        path = dotted_path.split(".")
        if path[0] == "save_config_pending":
            changed["configfile"]["save_config_pending"] = value
        elif path[0] == "heater_bed":
            changed["heater_bed"]["temperature"] = value
        else:
            changed["configfile"]["settings"]["probe_eddy_current btt_eddy"][
                "calibrate"
            ] = value
        with pytest.raises(RuntimeError, match=message):
            module.preflight(
                changed,
                expected_fingerprint="a" * 64,
                schedule=schedule,
            )

    with pytest.raises(RuntimeError, match="fingerprint"):
        module.preflight(status, expected_fingerprint="b" * 64, schedule=schedule)


def test_synthetic_analysis_recovers_hysteresis_stiction_homing_tilt_and_warp(
    tmp_path,
):
    module = _load_module()
    _schedule, manifest, _gcode = _manifest(module)
    records = _synthetic_records(module, manifest)
    analysis = module.analyze_records(
        records,
        manifest,
        _mesh(),
    )

    assert analysis["ok"]
    assert analysis["maximum_absolute_hysteresis_mm"] == pytest.approx(0.03)
    assert analysis["small_step_response"][
        "smallest_reliably_resolved_reversal_mm"
    ] == pytest.approx(0.04)
    center = analysis["homing_repeatability"]["positions"][1]
    assert center["range"] == pytest.approx(0.009)
    assert analysis["gantry_plane"]["left_to_right_span_mm"]["range"] > 0
    bed = analysis["bed_planeness"]
    assert bed["best_fit_plane"]["x_span_mm"] > 0
    assert bed["best_fit_plane"]["y_span_mm"] < 0
    assert bed["residual_peak_to_valley_mm"] > 0
    assert analysis["quality"]["reference_drift_mm"] == pytest.approx(0.008)
    module.write_samples(tmp_path, records)
    plots = module.write_plots(tmp_path, analysis)
    report = module.write_report(tmp_path, analysis)
    assert (tmp_path / "samples.csv").is_file()
    assert (tmp_path / "samples.json").is_file()
    assert report.is_file()
    assert len(plots) == 7
    assert all(Path(path).is_file() for path in plots)


def test_incomplete_window_and_reference_drift_are_hard_data_failures():
    module = _load_module()
    _schedule, manifest, _gcode = _manifest(module)
    records = _synthetic_records(module, manifest)
    records[0]["complete"] = False
    references = [record for record in records if record.get("reference")]
    references[-1]["median_height_mm"] += 0.1

    analysis = module.analyze_records(records, manifest, _mesh())

    assert not analysis["ok"]
    assert any("incomplete" in failure for failure in analysis["hard_failures"])
    assert any("reference drift" in failure for failure in analysis["hard_failures"])


def test_mesh_requires_complete_5x5_and_reports_plane_removed_warp():
    module = _load_module()

    incomplete = module.analyze_mesh({"probed_matrix": [[0.0] * 5] * 4})
    complete = module.analyze_mesh(_mesh())

    assert incomplete["hard_failures"]
    assert complete["hard_failures"] == []
    assert complete["peak_to_valley_mm"] > 0
    assert complete["residual_peak_to_valley_mm"] > 0


def test_runner_attempts_mesh_clear_when_acquisition_fails(monkeypatch, tmp_path):
    module = _load_module()
    import vision_nozzle_align

    monkeypatch.setattr(module, "query_status", lambda _url: {})
    monkeypatch.setattr(
        module,
        "preflight",
        lambda _status, **_kwargs: {
            "ok": True,
            "active_config_fingerprint": "a" * 64,
        },
    )
    monkeypatch.setattr(
        vision_nozzle_align,
        "stage_and_run_eddy_sweep",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
    )
    monkeypatch.setattr(
        vision_nozzle_align,
        "refresh_vision_ui_best_effort",
        lambda _job_root: None,
    )
    commands = []
    monkeypatch.setattr(
        module,
        "run_gcode",
        lambda _url, command, **_kwargs: commands.append(command),
    )
    args = SimpleNamespace(
        name="cleanup",
        job_root=tmp_path / "jobs",
        bed_center_x=117.5,
        bed_center_y=117.5,
        nozzle_to_coil_x=-8.18,
        nozzle_to_coil_y=9.0,
        nozzle_to_coil_z=2.5,
        active_config_fingerprint="a" * 64,
        moonraker_url="http://127.0.0.1:7125",
        virtual_sd_root=tmp_path / "gcodes",
        virtual_sd_subdir="vision_jobs",
        eddy_monitor_timeout=30.0,
    )

    with pytest.raises(RuntimeError, match="synthetic failure"):
        module.run_job(args)

    assert commands[-1] == "BED_MESH_CLEAR"


def test_browser_renderer_surfaces_baseline_metrics_and_artifacts(
    monkeypatch, tmp_path
):
    module = _load_module()
    _schedule, manifest, _gcode = _manifest(module)
    analysis = module.analyze_records(
        _synthetic_records(module, manifest),
        manifest,
        _mesh(),
    )
    import vision_nozzle_align

    vision_root = tmp_path / "vision"
    job_dir = vision_root / "nozzle_cam" / "jobs" / manifest["job_id"]
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True)
    analysis["artifacts"] = {
        "report": str(job_dir / "report.md"),
        "analysis_json": str(job_dir / "analysis.json"),
        "samples_csv": str(job_dir / "samples.csv"),
        "plots": [str(plots_dir / "hysteresis.png")],
    }
    monkeypatch.setattr(vision_nozzle_align, "VISION_ROOT_DIR", vision_root)
    monkeypatch.setattr(vision_nozzle_align, "VISION_ROOT_URL_PREFIX", "/vision")

    rendered = vision_nozzle_align.render_eddy_z_diagnostic_result(
        analysis,
        {"state": "completed", "reason": "complete cold baseline"},
    )

    assert "Cold Eddy Z Diagnostic" in rendered
    assert "Maximum directional hysteresis" in rendered
    assert "Residual bed warp" in rendered
    assert "/vision/nozzle_cam/jobs/" in rendered
    assert "baseline only" in rendered
