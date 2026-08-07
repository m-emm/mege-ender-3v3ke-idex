from __future__ import annotations

import importlib.util
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
    scripts = []
    runner._gcode = scripts.append

    evidence = runner.verify_eddy_probe_reference()

    assert scripts == [
        "G90\nG1 X150.000 Y150.000 Z5 F1200\nPROBE METHOD=probe"
    ]
    assert evidence["probe_z"] == pytest.approx(0.0)
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
            module.summarize_taps([0.021, 0.021, 0.021]),
            count=module.EDDY_REFERENCE_TAP_COUNT,
        )

    with pytest.raises(module.CalibrationError, match="repeatable"):
        module.Iteration1Runner.require_center_tap(
            module.summarize_taps([-0.016, 0.0, 0.016]),
            count=module.EDDY_REFERENCE_TAP_COUNT,
        )


def test_tap_threshold_is_required_from_calib():
    module = _load_module()

    calibration = {
        "eddy_relative_calibration": {"klipper": {"tap_threshold": 5000}}
    }
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
        "mesh",
        "resume",
    }


def test_direct_step_can_reload_stale_run_state_but_resume_remains_strict(tmp_path, monkeypatch):
    module = _load_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        '{"run_id": "run", "phase": "I1.1", '
        '"source_hashes": {"calib.yaml": "old"}, "evidence": {}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_config_hashes", lambda: {"calib.yaml": "new"})

    with pytest.raises(module.CalibrationError, match="source hashes changed"):
        module._load_run_state(run_dir)

    state = module._load_run_state(run_dir, strict_hashes=False)
    assert state.run_id == "run"


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
