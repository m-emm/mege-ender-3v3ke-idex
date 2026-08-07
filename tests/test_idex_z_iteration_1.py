from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "klipper_setup"
    / "klipper_config"
    / "calibrate_idex_bed_surface_eddy_tap.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("idex_z_iteration_1", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_common_endstop_update_preserves_relative_alignment():
    module = _load_module()

    t0, t1, delta = module.common_endstop_update(293.5, 292.226, 0.041)

    assert delta == pytest.approx(-0.041)
    assert t0 == pytest.approx(293.459)
    assert t1 == pytest.approx(292.185)
    module.assert_relative_alignment(293.5, 292.226, t0, t1, expected_delta=1.274)


def test_tap_measurement_uses_probe_contact_not_post_retract_toolhead_position():
    module = _load_module()

    contact_z, post_retract_z = module.tap_contact_and_post_retract_z(
        {
            "probe": {"last_probe_position": [150.0, 150.0, -0.0125, 0.0]},
            "toolhead": {"position": [150.0, 150.0, 3.9875, 0.0]},
        }
    )

    assert contact_z == pytest.approx(-0.0125)
    assert post_retract_z == pytest.approx(3.9875)
    assert post_retract_z - contact_z == pytest.approx(4.0)


def test_regular_eddy_probe_measurement_uses_canonical_probe_result():
    module = _load_module()

    assert module.probe_result_z_from_status(
        {"probe": {"last_probe_position": [150.0, 150.0, 0.012, 0.0]}}
    ) == pytest.approx(0.012)

    with pytest.raises(module.CalibrationError, match="non-finite"):
        module.probe_result_z_from_status(
            {"probe": {"last_probe_position": [150.0, 150.0, float("nan")]}}
        )


def test_regular_eddy_probe_result_keeps_physical_xy_and_statistics():
    module = _load_module()

    result = module.probe_result_from_status(
        {"probe": {"last_probe_position": [207.391, 168.997, -0.012, 0.0]}}
    )
    assert result == {
        "x": pytest.approx(207.391),
        "y": pytest.approx(168.997),
        "z": pytest.approx(-0.012),
    }
    summary = module.summarize_probe_results(
        [result, {"x": 207.391, "y": 168.997, "z": 0.004}]
    )
    assert summary["median"] == pytest.approx(-0.004)
    assert summary["span"] == pytest.approx(0.016)


def test_post_eddy_probe_reference_runs_regular_probe_and_records_evidence():
    module = _load_module()

    class Store:
        def __init__(self):
            self.writes = {}

        def write_json(self, name, value):
            self.writes[name] = value

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = True
    runner.store = Store()
    runner.raw_calibration = {
        "eddy_relative_calibration": {
            "nozzle_to_coil": {"x": -57.391, "y": -18.997, "z": 1.399}
        }
    }
    scripts = []
    runner._gcode = scripts.append

    evidence = runner.verify_eddy_probe_reference({"median": 0.0})

    assert scripts == []
    assert evidence["probe_summary"]["median"] == pytest.approx(0.0)
    assert evidence["median_residual"] == pytest.approx(0.0)
    assert evidence["nozzle_pose"] == {
        "x": pytest.approx(207.391),
        "y": pytest.approx(168.997),
        "z": pytest.approx(5.0),
    }
    assert runner.store.writes["post-eddy-probe-reference.json"] == evidence


def test_get_position_parser_retains_raw_steps_and_coordinate_layers():
    module = _load_module()

    position = module.parse_get_position_message(
        "mcu: stepper_x:-8654 stepper_y:-3392 stepper_z:-68561 "
        "stepper_z1:-70175 dual_carriage:-2\n"
        "stepper: stepper_x:149.997500 stepper_y:148.812500 "
        "stepper_z:2.950000 stepper_z1:2.950000 dual_carriage:353.087000\n"
        "kinematic: X:149.997500 Y:148.812500 Z:2.950000\n"
        "toolhead: X:150.000000 Y:148.815000 Z:2.950599 E:684.467700\n"
        "gcode: X:150.000000 Y:148.815000 Z:2.924000 E:684.467700\n"
        "gcode base: X:0.000000 Y:-1.185000 Z:0.924000 E:542.357820\n"
        "gcode homing: X:0.000000 Y:-1.185000 Z:0.924000"
    )

    assert position["mcu"]["stepper_z"] == -68561
    assert position["mcu"]["stepper_z1"] == -70175
    assert position["stepper"]["stepper_z"] == pytest.approx(2.95)
    assert position["toolhead"]["Z"] == pytest.approx(2.950599)
    assert position["gcode_homing"]["Z"] == pytest.approx(0.924)


def test_eddy_reference_gate_requires_zero_and_repeatable_three_tap_center():
    module = _load_module()

    passing = module.summarize_taps(
        [-0.025, -0.021, -0.003], attempts=module.EDDY_REFERENCE_TAP_COUNT
    )
    module.Iteration1Runner.require_center_tap(
        passing, count=module.EDDY_REFERENCE_TAP_COUNT
    )

    with pytest.raises(module.CalibrationError, match="native Z=0"):
        module.Iteration1Runner.require_center_tap(
            module.summarize_taps([0.06, 0.06, 0.06]),
            count=module.EDDY_REFERENCE_TAP_COUNT,
        )

    with pytest.raises(module.CalibrationError, match="repeatable"):
        module.Iteration1Runner.require_center_tap(
            module.summarize_taps([-0.025, 0.0, 0.025]),
            count=module.EDDY_REFERENCE_TAP_COUNT,
        )


def test_tap_threshold_is_required_from_calib():
    module = _load_module()

    calibration = {"eddy_relative_calibration": {"klipper": {"tap_threshold": 5000}}}
    assert module.configured_tap_threshold(calibration) == 5000

    with pytest.raises(module.CalibrationError, match="tap_threshold"):
        module.configured_tap_threshold(
            {"eddy_relative_calibration": {"klipper": {"tap_threshold": None}}}
        )


def test_cli_exposes_each_calibration_phase_as_a_named_step():
    module = _load_module()

    args = module.build_parser().parse_args(
        [
            "--step",
            "eddy-frequency",
            "--run-dir",
            "runs/idex_z_iteration_1/example",
            "--host",
            "pi@example.test",
            "--yes",
        ]
    )

    assert args.step == "eddy-frequency"
    assert args.run_dir == Path("runs/idex_z_iteration_1/example")
    assert args.host == "pi@example.test"
    assert args.yes is True
    assert set(module.STEP_CHOICES) >= {
        "tap-baseline",
        "drive-current",
        "eddy-frequency",
        "curve-doctor",
        "mesh",
        "resume",
    }
    assert "reanchor" not in module.STEP_CHOICES


def test_curve_doctor_step_syncs_the_managed_extra_before_measurement():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.state = module.RunState(run_id="curve-doctor", phase="I1.0")
    calls = []
    runner.confirm = lambda: calls.append("confirm")
    runner.preflight = lambda **kwargs: calls.append(("preflight", kwargs))
    runner.doctor_eddy_curve = lambda: calls.append("doctor")

    module._run_step(runner, "curve-doctor")

    assert calls == [
        "confirm",
        ("preflight", {"checkpoint_state": False, "sync_printer": True}),
        "doctor",
    ]


def _linear_eddy_curve():
    return ",".join(
        f"{height:.1f}:{10000.0 - 1000.0 * height:.1f}"
        for height in [index / 10 for index in range(1, 42)]
    )


def test_curve_doctor_remaps_dense_curve_through_tap_anchored_frequencies():
    module = _load_module()
    source = _linear_eddy_curve()
    source_pairs = module.parse_eddy_curve(source)
    anchors = []
    for target_height in (0.5, 1.0, 2.0, 3.0, 4.0):
        inferred_height = target_height * 0.98
        anchors.append(
            {
                "target_height": target_height,
                "raw_frequency_hz": module.eddy_curve_frequency_at_height(
                    source_pairs, inferred_height
                ),
            }
        )

    candidate, derived = module.doctor_eddy_curve(source, anchors)
    candidate_pairs = module.parse_eddy_curve(candidate)

    assert all(line.endswith(",") for line in candidate.splitlines()[:-1])
    assert all(":" in pair for pair in candidate.replace("\n", "").split(",") if pair)
    assert len(candidate_pairs) >= len(source_pairs)
    for anchor in derived:
        assert module.eddy_curve_height_at_frequency(
            candidate_pairs, anchor["raw_frequency_hz"]
        ) == pytest.approx(anchor["target_height"])
    assert candidate_pairs[0][0] == pytest.approx(0.1 + (0.5 - 0.49))


def test_curve_doctor_rejects_crossed_anchor_data():
    module = _load_module()
    source_pairs = module.parse_eddy_curve(_linear_eddy_curve())

    with pytest.raises(module.CalibrationError, match="cross"):
        module.doctor_eddy_curve(
            _linear_eddy_curve(),
            [
                {
                    "target_height": 0.5,
                    "raw_frequency_hz": module.eddy_curve_frequency_at_height(
                        source_pairs, 2.0
                    ),
                },
                {
                    "target_height": 1.0,
                    "raw_frequency_hz": module.eddy_curve_frequency_at_height(
                        source_pairs, 0.5
                    ),
                },
            ],
        )


def test_curve_doctor_raw_batches_use_tap_relative_commanded_z():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    scripts = []
    runner._gcode = scripts.append

    class Client:
        def status(self, _objects):
            return {
                "eddy_tap_measure": {
                    "last_raw_measurement": {
                        "bed_x": 150.0,
                        "bed_y": 150.0,
                        "nozzle_x": 207.391,
                        "nozzle_y": 168.997,
                        "requested_nozzle_z": 0.493,
                        "toolhead_z": 0.493,
                        "toolhead_position": [207.391, 168.997, 0.493, 0.0],
                        "raw_frequency_hz": 3_216_000.0,
                        "raw_frequency_span_hz": 100.0,
                        "sample_count": 200,
                        "temperature": 39.1,
                    }
                }
            }

    runner.client = Client()
    raw = runner._collect_curve_doctor_raw_batch(target_height=0.5, tap_median=-0.007)

    assert scripts == ["EDDY_RAW_MEASURE X=150.000 Y=150.000 Z=0.493000 DURATION=0.500"]
    assert raw["target_height"] == pytest.approx(0.5)
    assert raw["commanded_z"] == pytest.approx(0.493)


def test_curve_doctor_collects_all_anchors_in_one_upward_sweep():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    calls = []
    runner._gcode = calls.append

    def collect(**kwargs):
        calls.append(kwargs)
        return {"raw_frequency_hz": 3_200_000.0}

    runner._collect_curve_doctor_raw_batch = collect
    anchors = runner._collect_curve_doctor_anchors(0.0, _linear_eddy_curve())

    batch_calls = [call for call in calls if isinstance(call, dict)]
    assert [call["target_height"] for call in batch_calls] == [
        0.5,
        0.5,
        0.5,
        1.0,
        1.0,
        1.0,
        2.0,
        2.0,
        2.0,
        3.0,
        3.0,
        3.0,
        4.0,
        4.0,
        4.0,
    ]
    assert batch_calls[0]["safe_travel"] is True
    assert batch_calls[0]["lift_after"] is False
    assert batch_calls[0]["approach_z"] == pytest.approx(0.1)
    assert all(call["safe_travel"] is False for call in batch_calls[1:])
    assert all(call["lift_after"] is False for call in batch_calls[1:])
    assert all(call["approach_z"] is None for call in batch_calls[1:])
    assert calls[-1] == "G90\nG1 Z5 F1200"
    assert len(anchors) == 5


def test_gcode_logs_and_persists_new_klipper_responses(tmp_path, caplog):
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.store = module.ArtifactStore(tmp_path, "gcode-responses")

    class Client:
        def __init__(self):
            self.entries = [
                {"time": 1.0, "type": "response", "message": "// old response"}
            ]

        def gcode_store(self, *, count=100):
            assert count == 100
            return list(self.entries)

        def gcode(self, script, *, timeout=60.0):
            assert script == "EDDY_RAW_MEASURE X=150 Y=150 Z=1"
            assert timeout == 60.0
            self.entries.extend(
                [
                    {"time": 2.0, "type": "command", "message": script},
                    {
                        "time": 3.0,
                        "type": "response",
                        "message": "// EDDY_RAW_MEASURE: implied_bed_z=0.001",
                    },
                ]
            )
            return "ok"

    runner.client = Client()

    with caplog.at_level("INFO"):
        runner._gcode("EDDY_RAW_MEASURE X=150 Y=150 Z=1")

    assert "G-code response: // EDDY_RAW_MEASURE: implied_bed_z=0.001" in caplog.text
    artifact = next((tmp_path / "gcode-responses").glob("command-*.json"))
    assert json.loads(artifact.read_text())["gcode_responses"] == [
        "// EDDY_RAW_MEASURE: implied_bed_z=0.001"
    ]


def test_compact_curve_doctor_summary_omits_full_raw_evidence(caplog, tmp_path):
    module = _load_module()
    state = module.RunState(
        run_id="curve-doctor-summary",
        phase="I1.5D",
        committed_phase="I1.5D",
        evidence={
            "curve_doctor": {
                "rollback": False,
                "pre_reference": {"median_tap_z": -0.004},
                "post_reference": {"median_tap_z": -0.005},
                "anchors": [
                    {
                        "target_height": 0.5,
                        "raw_frequency_hz": 3_216_000.0,
                        "batch_frequency_span_hz": 80.0,
                        "batches": [{"large": "raw evidence stays on disk"}],
                    }
                ],
                "validation": {
                    "span": 0.002,
                    "results": [{"residual": -0.006, "raw": {"large": "detail"}}],
                },
            }
        },
    )

    summary = module._compact_run_summary(state)
    with caplog.at_level("INFO"):
        module._log_run_summary(state, tmp_path)

    assert summary["curve_doctor"] == {
        "retained": True,
        "pre_tap_median": -0.004,
        "post_tap_median": -0.005,
        "anchor_frequencies_hz": [
            {"height": 0.5, "frequency": 3_216_000.0, "batch_span_hz": 80.0}
        ],
        "validation_residuals": [-0.006],
        "validation_span": 0.002,
    }
    assert "curve-doctor summary: retained=True" in caplog.text
    assert (
        "curve-doctor anchors: z=0.500000 f=3216000.000Hz batch_span=80.000Hz"
        in caplog.text
    )
    assert "raw evidence stays on disk" not in caplog.text


def test_curve_doctor_validation_uses_post_tap_datum_and_shape_gate():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    scripts = []
    runner._gcode = scripts.append
    tap_median = -0.005
    commanded = [tap_median + height for height in module.CURVE_DOCTOR_HEIGHTS]

    class Client:
        def status(self, _objects):
            return {
                "eddy_tap_measure": {
                    "last_scan_height_test": {
                        "results": [
                            {
                                "toolhead_z": height,
                                "scan_bed_z": tap_median + residual,
                            }
                            for height, residual in zip(
                                commanded, (-0.008, -0.004, 0.0, 0.004, 0.008)
                            )
                        ]
                    }
                }
            }

    runner.client = Client()
    validation = runner._validate_curve_doctor_candidate(tap_median)

    assert validation["span"] == pytest.approx(0.016)
    assert all(
        abs(point["residual"]) <= module.CURVE_DOCTOR_ABSOLUTE_TOLERANCE
        for point in validation["results"]
    )
    assert "NOZZLE_ZS=0.495000,0.995000,1.995000,2.995000,3.995000" in scripts[0]


def test_curve_doctor_rolls_back_when_candidate_validation_fails():
    module = _load_module()

    class Store:
        def __init__(self):
            self.writes = {}

        def write_json(self, name, value):
            self.writes[name] = value

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.store = Store()
    runner.raw_calibration = {
        "eddy_relative_calibration": {"klipper": {"calibrate": _linear_eddy_curve()}}
    }
    runner.eddy_reference_sequence = lambda label: {"median_tap_z": 0.0, "label": label}
    runner._collect_curve_doctor_anchors = lambda median, source: [
        {
            "target_height": 0.5,
            "raw_frequency_hz": 9500.0,
            "batches": [],
        },
        {
            "target_height": 1.0,
            "raw_frequency_hz": 9000.0,
            "batches": [],
        },
    ]
    calls = []
    runner._snapshot_eddy_candidate_base = lambda: calls.append("snapshot")
    runner.deploy_value = lambda *args, **kwargs: calls.append("deploy")
    runner._validate_curve_doctor_candidate = lambda median: (_ for _ in ()).throw(
        module.CalibrationError("validation failed")
    )
    runner._restore_eddy_candidate_base = lambda: calls.append("restore")
    runner.checkpoint = lambda *args, **kwargs: calls.append("checkpoint")

    with pytest.raises(module.CalibrationError, match="validation failed"):
        runner.doctor_eddy_curve()

    assert calls == ["snapshot", "deploy", "checkpoint", "restore"]
    assert "curve-doctor-failed.json" in runner.store.writes


def test_curve_doctor_rollback_restores_calib_and_generated_config(
    tmp_path, monkeypatch
):
    module = _load_module()
    source_curve = _linear_eddy_curve()
    calib_path = tmp_path / "calib.yaml"
    config_path = tmp_path / "printer.cfg"
    original_calib = (
        "eddy_relative_calibration:\n"
        "  klipper:\n"
        "    calibrate: |\n"
        f"      {source_curve}\n"
    )
    calib_path.write_text(original_calib, encoding="utf-8")
    config_path.write_text("original generated config\n", encoding="utf-8")
    monkeypatch.setattr(module, "CALIB_PATH", calib_path)
    monkeypatch.setattr(module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(module, "_run_local", lambda *args, **kwargs: None)

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.store = module.ArtifactStore(tmp_path, "curve-doctor")
    runner.state = module.RunState(run_id="curve-doctor", phase="I1.0")
    runner.raw_calibration = {
        "eddy_relative_calibration": {"klipper": {"calibrate": source_curve}}
    }
    runner.eddy_reference_sequence = lambda label: {"median_tap_z": 0.0, "label": label}
    runner._collect_curve_doctor_anchors = lambda median, source: [
        {"target_height": 0.5, "raw_frequency_hz": 9500.0, "batches": []},
        {"target_height": 1.0, "raw_frequency_hz": 9000.0, "batches": []},
    ]
    runner._validate_curve_doctor_candidate = lambda median: (_ for _ in ()).throw(
        module.CalibrationError("candidate failed")
    )
    runner.checkpoint = lambda *args, **kwargs: None

    with pytest.raises(module.CalibrationError, match="candidate failed"):
        runner.doctor_eddy_curve()

    assert calib_path.read_text(encoding="utf-8") == original_calib
    assert config_path.read_text(encoding="utf-8") == "original generated config\n"


def test_direct_step_can_reload_stale_run_state_but_resume_remains_strict(
    tmp_path, monkeypatch
):
    module = _load_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        '{"run_id": "run", "phase": "I1.1", '
        f'"workflow_version": {module.WORKFLOW_VERSION}, '
        '"source_hashes": {"calib.yaml": "old"}, "evidence": {}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_config_hashes", lambda: {"calib.yaml": "new"})

    with pytest.raises(module.CalibrationError, match="source hashes changed"):
        module._load_run_state(run_dir)

    state = module._load_run_state(run_dir, strict_hashes=False)
    assert state.run_id == "run"


def test_legacy_run_state_is_rejected_after_reanchor_removal(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "legacy-run"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        '{"run_id": "legacy-run", "phase": "I1.6", '
        '"committed_phase": "I1.6", "evidence": {}}\n',
        encoding="utf-8",
    )

    with pytest.raises(module.CalibrationError, match="unsupported workflow version"):
        module._load_run_state(run_dir)


def test_resume_after_eddy_calibration_runs_mesh_from_a_clean_frame():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.state = module.RunState(
        run_id="resume-after-eddy",
        phase=module.Phase.EDDY_CALIBRATION.value,
        committed_phase=module.Phase.EDDY_CALIBRATION.value,
    )
    calls = []
    runner.confirm = lambda: calls.append("confirm")
    runner.preflight = lambda **kwargs: calls.append("preflight")
    runner.final_mesh = lambda *, clean_frame=True: calls.append(f"mesh:{clean_frame}")
    runner.checkpoint = lambda phase, **kwargs: calls.append(phase.value)
    runner.write_final_report = lambda: calls.append("report")

    runner.resume()

    assert calls == [
        "confirm",
        "preflight",
        "mesh:True",
        module.Phase.FINISH.value,
        "report",
    ]


def test_full_run_reuses_verified_frames_for_drive_current_and_mesh():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.state = module.RunState(
        run_id="full-run", phase=module.Phase.PREFLIGHT.value
    )
    calls = []
    runner.confirm = lambda: calls.append("confirm")
    runner.preflight = lambda: calls.append("preflight")
    runner.bootstrap_tap = lambda: (
        calls.append("bootstrap") or type("Summary", (), {"median": 0.0})()
    )
    runner.update_endstops = lambda median: calls.append("endstops")
    runner.verify_center = lambda *args, **kwargs: calls.append("center")
    runner.calibrate_drive_current = lambda *, clean_frame=True: calls.append(
        f"drive:{clean_frame}"
    )
    runner.calibrate_eddy_curve = lambda: calls.append("eddy")
    runner.final_mesh = lambda *, clean_frame=True: calls.append(f"mesh:{clean_frame}")
    runner.checkpoint = lambda phase, **kwargs: calls.append(phase.value)
    runner.write_final_report = lambda: calls.append("report")

    runner.run()

    assert calls == [
        "confirm",
        "preflight",
        "bootstrap",
        "endstops",
        "center",
        "drive:False",
        "eddy",
        "mesh:False",
        module.Phase.FINISH.value,
        "report",
    ]


def test_tap_acceptance_counts_rejections_and_enforces_spread():
    module = _load_module()

    summary = module.summarize_taps(
        [-0.002, 0.001, 0.000, -0.001, 0.002, 0.001, -0.001],
        attempts=9,
    )
    assert summary.rejected_attempts == 2
    module.require_tap_acceptance(summary)

    with pytest.raises(module.CalibrationError, match="tap span"):
        module.require_tap_acceptance(
            module.summarize_taps([0.0, 0.04, 0.0, 0.0, 0.0, 0.0, 0.0])
        )


def test_coil_pose_and_safe_grid_keep_both_sensor_points_in_bounds():
    module = _load_module()

    nozzle = module.coil_over_target_pose(
        module.Pose(150.0, 150.0, 20.0),
        module.Pose(-57.391, -18.997, 1.399),
    )
    assert nozzle == module.Pose(207.391, 168.997, 18.601)

    points = module.derive_safe_tap_grid(
        nozzle_x=module.AxisBounds(0, 255),
        nozzle_y=module.AxisBounds(20, 275),
        mesh_x=module.AxisBounds(0, 190),
        mesh_y=module.AxisBounds(20, 275),
        coil_offset_x=-57.391,
        coil_offset_y=-18.997,
    )
    assert len(points) == 9
    for point in points:
        assert 62.391 <= point.x <= 185.0
        assert 43.997 <= point.y <= 270.0
        assert 0 <= point.x + (-57.391) <= 190
        assert 20 <= point.y + (-18.997) <= 275


def test_pending_config_supports_mapping_and_record_shapes():
    module = _load_module()

    assert (
        module.extract_pending_value(
            {"probe_eddy_current btt_eddy": {"reg_drive_current": {"value": 17}}},
            "probe_eddy_current btt_eddy",
            "reg_drive_current",
        )
        == 17
    )
    assert (
        module.extract_pending_value(
            [
                {
                    "section": "probe_eddy_current btt_eddy",
                    "option": "reg_drive_current",
                    "value": 17,
                }
            ],
            "probe_eddy_current btt_eddy",
            "reg_drive_current",
        )
        == 17
    )
    module.require_only_transient_mesh_pending(
        {"bed_mesh default": {"mesh_matrix": []}}
    )
    module.require_only_transient_mesh_pending(
        {f"bed_mesh {module.MESH_MANUAL_PROFILE}": {"mesh_matrix": []}}
    )
    with pytest.raises(module.CalibrationError, match="unexpected pending"):
        module.require_only_transient_mesh_pending(
            {"bed_mesh default": {}, "stepper_z": {"position_endstop": 1}}
        )


def test_mesh_inverse_and_atomic_calibration_update(tmp_path):
    module = _load_module()

    assert module.mesh_corrected_contact_z(0.021, 0.021) == pytest.approx(0.0)
    calibration = tmp_path / "calib.yaml"
    calibration.write_text(
        "# keep this comment\n"
        "tools:\n"
        "  t0:\n"
        "    z_endstop: 10.000\n"
        "  t1:\n"
        "    z_endstop: 8.726\n"
        "eddy_relative_calibration:\n"
        "  klipper:\n"
        "    reg_drive_current: 15\n"
        "    tap_threshold: 5000\n"
        "    tap_z_offset: 0.000\n"
        "    calibrate: |\n"
        "      0.1:100,\n"
        "      0.2:90,\n"
        "      0.3:80,\n"
        "      0.4:70,\n"
        "      0.5:60,\n"
        "      0.6:50,\n"
        "      0.7:40,\n"
        "      0.8:30,\n"
        "      0.9:20\n",
        encoding="utf-8",
    )
    module.atomic_update_calibration(
        calibration,
        {
            ("tools", "t0", "z_endstop"): 9.75,
            ("tools", "t1", "z_endstop"): 8.476,
            ("eddy_relative_calibration", "klipper", "tap_z_offset"): 0.0,
        },
    )
    text = calibration.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "z_endstop: 9.750" in text
    assert "tap_threshold: 5000" in text


def test_mesh_interpolation_and_tap_acceptance_use_inverse_correction():
    module = _load_module()
    matrix = [[0.0, 0.1], [0.2, 0.3]]
    point = module.MeshPoint(0.5, 0.5)
    assert module.mesh_correction_at(
        matrix,
        mesh_min=module.MeshPoint(0.0, 0.0),
        mesh_max=module.MeshPoint(1.0, 1.0),
        point=point,
    ) == pytest.approx(0.15)
    result = module.mesh_tap_acceptance(
        {point: (0.149, 0.150, 0.151)},
        {point: 0.15},
    )
    assert result["max_abs"] <= 0.001


def _mesh_verification_runner(module):
    class Store:
        def __init__(self):
            self.writes = {}

        def write_json(self, name, value):
            self.writes[name] = value

    runner = object.__new__(module.Iteration1Runner)
    runner.raw_calibration = {
        "eddy_relative_calibration": {
            "nozzle_to_coil": {"x": -57.391, "y": -18.997, "z": 1.399}
        }
    }
    runner.tap_threshold = 6500
    runner.store = Store()
    return runner


def _flat_mesh():
    return {
        "mesh_matrix": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        "mesh_min": [0.0, 20.0],
        "mesh_max": [190.0, 275.0],
    }


def test_same_point_mesh_measurement_uses_one_tap_three_scans_and_fast_xy():
    module = _load_module()
    runner = _mesh_verification_runner(module)
    commands = []
    runner._gcode = lambda script, **kwargs: commands.append((script, kwargs))
    point = module.MeshPoint(123.696, 156.998)
    runner.client = type(
        "Client",
        (),
        {
            "status": lambda _self, objects: {
                "eddy_tap_measure": {
                    "last_tap_measurement": {
                        "bed_x": point.x,
                        "bed_y": point.y,
                        "tap": {"count": 1},
                        "stationary_scan": {"count": 3},
                    }
                }
            }
        },
    )()

    captured = runner._capture_same_point_mesh_measurement(point=point)

    assert captured["bed_x"] == pytest.approx(point.x)
    assert len(commands) == 1
    command = commands[0][0]
    assert "EDDY_TAP_MEASURE" in command
    assert "COUNT=1" in command
    assert "EDDY_MODE=scan" in command
    assert "SCAN_COUNT=3" in command
    assert "XY_SPEED=100.000" in command


def test_mesh_reference_failure_still_attempts_all_grid_points():
    module = _load_module()
    runner = _mesh_verification_runner(module)
    attempted = []

    def collect_taps(**kwargs):
        point = (kwargs["x"], kwargs["y"])
        attempted.append(point)
        if len(attempted) == 1:
            return None, [{"attempt": 1, "ok": False, "error": "not enough lift"}]
        summary = module.summarize_taps([0.0, 0.0, 0.0], attempts=3)
        return summary, [
            {"attempt": index, "ok": True, "z": 0.0} for index in range(1, 4)
        ]

    runner.collect_taps = collect_taps

    with pytest.raises(module.CalibrationError, match="surveyed all 9 points"):
        runner.verify_mesh_against_tap(_flat_mesh())

    assert attempted[0] == (module.REFERENCE_X, module.REFERENCE_Y)
    assert len(attempted) == 10
    report = runner.store.writes["mesh-verification.json"]
    assert report["attempted_points"] == 9
    assert report["successful_points"] == 9
    assert report["failed_points"] == []
    assert report["reference"]["ok"] is False
    assert report["reference"]["error"] == "no successful tap samples"


def test_mesh_reference_success_records_exact_center_evidence():
    module = _load_module()
    runner = _mesh_verification_runner(module)
    attempted = []

    def collect_taps(**kwargs):
        attempted.append((kwargs["x"], kwargs["y"]))
        summary = module.summarize_taps([0.0, 0.0, 0.0], attempts=3)
        return summary, [
            {"attempt": index, "ok": True, "z": 0.0} for index in range(1, 4)
        ]

    runner.collect_taps = collect_taps

    report = runner.verify_mesh_against_tap(_flat_mesh())

    assert len(attempted) == 10
    reference = report["reference"]
    assert reference["point"] == {"x": 150.0, "y": 150.0}
    assert reference["ok"] is True
    assert reference["samples"] == [0.0, 0.0, 0.0]
    assert reference["summary"]["mean"] == pytest.approx(0.0)
    assert reference["summary"]["span"] == pytest.approx(0.0)
    assert reference["mesh_correction"] == pytest.approx(0.0)
    assert reference["mesh_corrected_mean"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("reference_samples", "mesh", "expected_error"),
    [
        (
            (0.0, 0.0, 0.0),
            {
                "mesh_matrix": [[0.01, 0.01], [0.01, 0.01]],
                "mesh_min": [0.0, 20.0],
                "mesh_max": [190.0, 275.0],
            },
            "reference mesh correction exceeds tolerance",
        ),
        (
            (0.04, 0.04, 0.04),
            _flat_mesh(),
            "mesh-corrected reference tap exceeds point tolerance",
        ),
    ],
)
def test_mesh_reference_failure_records_correction_and_corrected_mean(
    reference_samples, mesh, expected_error
):
    module = _load_module()
    runner = _mesh_verification_runner(module)
    calls = 0

    def collect_taps(**kwargs):
        nonlocal calls
        calls += 1
        samples = reference_samples if calls == 1 else (0.0, 0.0, 0.0)
        summary = module.summarize_taps(samples, attempts=3)
        return summary, [
            {"attempt": index, "ok": True, "z": samples[0]} for index in range(1, 4)
        ]

    runner.collect_taps = collect_taps

    with pytest.raises(module.CalibrationError, match="surveyed all 9 points"):
        runner.verify_mesh_against_tap(mesh)

    report = runner.store.writes["mesh-verification.json"]
    assert calls == 10
    assert report["reference"]["ok"] is False
    assert expected_error in report["reference"]["error"]
    assert "mesh_correction" in report["reference"]
    assert "mesh_corrected_mean" in report["reference"]


def test_clean_mesh_diagnostic_surveys_all_points_and_reports_stationary_residuals():
    module = _load_module()
    runner = _mesh_verification_runner(module)
    runner._gcode = lambda *_args, **_kwargs: None
    attempts = []

    def same_point_measurement(**kwargs):
        point = kwargs["point"]
        attempts.append((point.x, point.y))
        return {
            "eddy_mode": "scan",
            "bed_x": point.x,
            "bed_y": point.y,
            "tap": {
                "count": 1,
                "samples": [{"x": point.x, "y": point.y, "z": 0.0}],
                "mean": 0.0,
                "median": 0.0,
                "span": 0.0,
                "standard_deviation": 0.0,
            },
            "stationary_scan": {
                "bed_x": point.x,
                "bed_y": point.y,
                "count": 3,
                "scan_bed_z_median": 0.01,
                "scan_bed_z_span": 0.001,
            },
        }

    runner._capture_same_point_mesh_measurement = same_point_measurement
    snapshot = {
        "mesh_min": [0.0, 20.0],
        "mesh_max": [190.0, 275.0],
        "mesh_matrix": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
    }

    report = runner.diagnose_mesh_against_tap(snapshot)

    assert attempts[0] == (module.REFERENCE_X, module.REFERENCE_Y)
    assert len(attempts) == 10
    assert report["error"] is None
    assert report["attempted_points"] == 9
    assert report["successful_tap_points"] == 9
    assert report["rapid_mesh_vs_tap"]["max_abs"] == pytest.approx(0.0)
    assert report["rapid_mesh_minus_stationary"]["median"] == pytest.approx(-0.01)
    assert report["stationary_eddy_minus_tap"]["median"] == pytest.approx(0.01)
    assert report["rapid_mesh_minus_tap"]["max_abs"] == pytest.approx(0.0)


def test_active_mesh_raw_tap_check_uses_clean_raw_contact():
    module = _load_module()
    runner = _mesh_verification_runner(module)
    selected = []

    def collect_taps(**kwargs):
        selected.append((kwargs["x"], kwargs["y"]))
        summary = module.summarize_taps([0.0], attempts=1)
        return summary, [{"attempt": 1, "ok": True, "z": 0.0}]

    runner.collect_taps = collect_taps
    report = runner.verify_active_mesh_transform(
        {
            "point_results": [
                {
                    "point": {"x": 62.0, "y": 44.0},
                    "mesh_correction": 0.2,
                    "tap_summary": {"mean": 0.0},
                }
            ]
        }
    )

    assert selected == [(62.0, 44.0)]
    assert report["expected_raw_tap"] == pytest.approx(0.0)
    assert report["delta_active_minus_clean_raw"] == pytest.approx(0.0)
    assert report["ok"] is True


def test_final_mesh_reloads_rapid_profile_even_when_diagnostic_fails():
    module = _load_module()

    class Store:
        def __init__(self):
            self.writes = {}

        def write_json(self, name, value):
            self.writes[name] = value

    class Client:
        def status(self, objects):
            if objects == ["configfile"]:
                return {"configfile": {"save_config_pending_items": {}}}
            if objects == ["bed_mesh", "configfile"]:
                return {
                    "bed_mesh": {
                        "profile_name": module.MESH_MANUAL_PROFILE,
                        "mesh_matrix": [[0.0, 0.0], [0.0, 0.0]],
                        "probed_matrix": [[0.0, 0.0], [0.0, 0.0]],
                        "mesh_min": [0.0, 20.0],
                        "mesh_max": [190.0, 275.0],
                    },
                    "configfile": {"save_config_pending_items": {}},
                }
            if objects == ["bed_mesh"]:
                return {
                    "bed_mesh": {
                        "profile_name": module.MESH_MANUAL_PROFILE,
                        "mesh_matrix": [[0.0]],
                    }
                }
            raise AssertionError(objects)

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.client = Client()
    runner.store = Store()
    runner._home_clean_frame = lambda: None
    commands = []
    runner._gcode = lambda script, **kwargs: commands.append((script, kwargs))
    runner._mesh_snapshot = lambda mesh: {"mesh_matrix": mesh["mesh_matrix"]}
    runner.diagnose_mesh_against_tap = lambda snapshot: {
        "error": "rapid-mesh-vs-Tap gate failed",
        "point_results": [],
    }
    runner.verify_active_mesh_transform = lambda verification: {"ok": True}

    with pytest.raises(module.CalibrationError, match="rapid-mesh-vs-Tap gate failed"):
        runner.final_mesh()

    assert any(
        command[0] == f"BED_MESH_PROFILE SAVE={module.MESH_MANUAL_PROFILE}"
        for command in commands
    )
    assert any(
        command[0] == f"BED_MESH_PROFILE LOAD={module.MESH_MANUAL_PROFILE}"
        for command in commands
    )
    assert runner.store.writes["mesh-verification.json"]["rapid_mesh_profile"] == (
        module.MESH_MANUAL_PROFILE
    )
    assert runner.store.writes["mesh-verification.json"]["rapid_mesh_reloaded"] is True


def test_final_mesh_runs_one_scan_at_final_clearance():
    module = _load_module()

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = True
    scripts = []
    checkpoints = []
    homes = []
    runner._home_clean_frame = lambda: homes.append("home")
    runner._gcode = lambda script, **kwargs: scripts.append((script, kwargs))
    runner.checkpoint = lambda *args, **kwargs: checkpoints.append((args, kwargs))

    runner.final_mesh()

    assert scripts == [
        (
            "BED_MESH_CALIBRATE METHOD=scan PROFILE=default HORIZONTAL_MOVE_Z=1",
            {"timeout": 900.0},
        )
    ]
    assert checkpoints == [((module.Phase.MESH_SCAN,), {"committed": False})]
    assert homes == ["home"]


def test_final_mesh_can_reuse_committed_post_eddy_frame():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = True
    homes = []
    runner._home_clean_frame = lambda: homes.append("home")
    runner._gcode = lambda *args, **kwargs: None
    runner.checkpoint = lambda *args, **kwargs: None

    runner.final_mesh(clean_frame=False)

    assert homes == []


def test_drive_current_can_reuse_verified_frame_with_safe_lift():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = True
    runner.raw_calibration = {
        "eddy_relative_calibration": {
            "nozzle_to_coil": {"x": -57.391, "y": -18.997, "z": 1.399}
        }
    }
    homes = []
    scripts = []
    runner._home_clean_frame = lambda: homes.append("home")
    runner._gcode = lambda script, **kwargs: scripts.append((script, kwargs))
    runner.checkpoint = lambda *args, **kwargs: None

    runner.calibrate_drive_current(clean_frame=False)

    assert homes == []
    assert scripts[0] == (
        "G90\nG1 Z20.000 F1200\nG1 X207.391 Y168.997 F1200\nG1 Z18.601 F1200",
        {},
    )
    assert scripts[1] == (
        "LDC_CALIBRATE_DRIVE_CURRENT CHIP=btt_eddy",
        {"timeout": 120.0},
    )


def test_direct_drive_current_and_mesh_steps_start_with_clean_frame():
    module = _load_module()
    drive_runner = object.__new__(module.Iteration1Runner)
    drive_runner.dry_run = True
    drive_runner.raw_calibration = {
        "eddy_relative_calibration": {
            "nozzle_to_coil": {"x": -57.391, "y": -18.997, "z": 1.399}
        }
    }
    drive_homes = []
    drive_runner._home_clean_frame = lambda: drive_homes.append("home")
    drive_runner._gcode = lambda *args, **kwargs: None
    drive_runner.checkpoint = lambda *args, **kwargs: None

    drive_runner.calibrate_drive_current()

    mesh_runner = object.__new__(module.Iteration1Runner)
    mesh_runner.dry_run = True
    mesh_homes = []
    mesh_runner._home_clean_frame = lambda: mesh_homes.append("home")
    mesh_runner._gcode = lambda *args, **kwargs: None
    mesh_runner.checkpoint = lambda *args, **kwargs: None

    mesh_runner.final_mesh()

    assert drive_homes == ["home"]
    assert mesh_homes == ["home"]


def test_dry_run_does_not_send_gcode_or_write_artifacts(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "_run_local", lambda *args, **kwargs: None)

    class FakeClient:
        def __init__(self):
            self.gcode_calls = []

        def status(self, objects):
            return {
                "webhooks": {"state": "ready"},
                "print_stats": {"state": "standby"},
                "virtual_sdcard": {"is_active": False},
                "configfile": {
                    "save_config_pending": False,
                    "save_config_pending_items": {},
                },
                "gcode_move": {"homing_origin": [0.0, 0.0, 0.0]},
                "heater_bed": {"temperature": 25.0, "target": 0.0},
                "extruder": {"temperature": 25.0, "target": 0.0},
                "extruder1": {"temperature": 25.0, "target": 0.0},
                "temperature_probe btt_eddy": {"temperature": 25.0},
            }

        def gcode(self, script, timeout=60.0):
            self.gcode_calls.append(script)
            raise AssertionError("dry-run sent G-code")

    client = FakeClient()
    store = module.ArtifactStore(tmp_path, "idex-test-dry-run", enabled=False)
    runner = module.Iteration1Runner(
        client=client,
        store=store,
        dry_run=True,
        assume_yes=True,
    )
    state = runner.run()
    assert state.evidence["dry_run"] is True
    assert client.gcode_calls == []
