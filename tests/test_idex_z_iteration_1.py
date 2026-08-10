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

    t0, t1, delta = module.common_endstop_update(
        293.5,
        292.226,
        0.041,
        contact_target_z=-0.2,
    )

    assert delta == pytest.approx(-0.241)
    assert t0 == pytest.approx(293.259)
    assert t1 == pytest.approx(291.985)
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
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2

    evidence = runner.verify_eddy_probe_reference({"median": -0.2})

    assert scripts == []
    assert evidence["probe_summary"]["median"] == pytest.approx(-0.2)
    assert evidence["median_residual"] == pytest.approx(0.0)
    assert evidence["nozzle_pose"] == {
        "x": pytest.approx(207.391),
        "y": pytest.approx(168.997),
        "z": pytest.approx(5.0),
    }
    assert runner.store.writes["post-eddy-probe-reference.json"] == evidence


def test_post_eddy_probe_residual_is_report_only(caplog):
    module = _load_module()

    class Store:
        def write_json(self, name, value):
            self.value = value

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.store = Store()
    runner.raw_calibration = {
        "eddy_relative_calibration": {
            "nozzle_to_coil": {"x": -57.391, "y": -18.997, "z": 1.399}
        }
    }
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2
    runner._validate_eddy_reference_pose = lambda _pose: {"test": True}
    probe_zs = iter([-0.17, -0.17, -0.17, -0.17, -0.2])
    runner._capture_regular_eddy_probe = lambda **_kwargs: {
        "probe_result": {"x": 150.0, "y": 150.0, "z": next(probe_zs)},
        "position": {},
    }

    evidence = runner.verify_eddy_probe_reference({"median": -0.2})

    assert evidence["median_residual"] == pytest.approx(0.03)
    assert evidence["residual_gate"] == {"passed": False, "enforced": False}
    assert "report-only gate" in caplog.text


def test_eddy_manual_probe_targets_configured_physical_contact_coordinate():
    module = _load_module()

    class Client:
        def __init__(self):
            self.status_calls = 0

        def status(self, objects):
            assert objects == ["manual_probe"]
            self.status_calls += 1
            return {
                "manual_probe": {
                    "is_active": True,
                    "z_position": 0.03 if self.status_calls == 1 else -0.2,
                }
            }

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.client = Client()
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2
    commands = []
    runner._gcode = lambda script, **kwargs: commands.append((script, kwargs))
    runner.eddy_reference_sequence = lambda label: {
        "summary": {"mean": -0.2, "median": -0.2, "span": 0.0}
    }
    runner.capture_pending = lambda *_args: (
        "0.1:100,0.2:90,0.3:80,0.4:70,0.5:60,"
        "0.6:50,0.7:40,0.8:30,0.9:20"
    )
    runner._snapshot_eddy_candidate_base = lambda: None
    runner.deploy_value = lambda *_args, **_kwargs: None
    runner.verify_eddy_probe_reference = lambda _summary: {"passed": True}
    runner.checkpoint = lambda *_args, **_kwargs: None

    runner.calibrate_eddy_curve()

    assert ("TESTZ Z=-0.230000", {}) in commands
    assert not any(command == "TESTZ Z=-0.030000" for command, _ in commands)


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


def test_eddy_reference_gate_requires_target_and_repeatable_three_tap_center():
    module = _load_module()

    passing = module.summarize_taps(
        [-0.225, -0.221, -0.203], attempts=module.EDDY_REFERENCE_TAP_COUNT
    )
    module.Iteration1Runner.require_center_tap(
        passing,
        count=module.EDDY_REFERENCE_TAP_COUNT,
        contact_target_z=-0.2,
    )

    with pytest.raises(module.CalibrationError, match="physical contact target"):
        module.Iteration1Runner.require_center_tap(
            module.summarize_taps([0.06, 0.06, 0.06]),
            count=module.EDDY_REFERENCE_TAP_COUNT,
            contact_target_z=-0.2,
        )

    with pytest.raises(module.CalibrationError, match="repeatable"):
        module.Iteration1Runner.require_center_tap(
            module.summarize_taps([-0.225, -0.2, -0.175]),
            count=module.EDDY_REFERENCE_TAP_COUNT,
            contact_target_z=-0.2,
        )


def test_tap_threshold_is_required_from_calib():
    module = _load_module()

    calibration = {"eddy_relative_calibration": {"klipper": {"tap_threshold": 5000}}}
    assert module.configured_tap_threshold(calibration) == 5000

    with pytest.raises(module.CalibrationError, match="tap_threshold"):
        module.configured_tap_threshold(
            {"eddy_relative_calibration": {"klipper": {"tap_threshold": None}}}
        )


def test_bed_to_nozzle_gap_is_required_from_calib():
    module = _load_module()

    for value in (0.2, 0.0, -0.1):
        assert module.configured_bed_to_nozzle_gap(
            {"bed_to_nozzle_gap": value}
        ) == pytest.approx(value)

    for value in (None, True, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(module.CalibrationError, match="bed_to_nozzle_gap"):
            module.configured_bed_to_nozzle_gap({"bed_to_nozzle_gap": value})


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
    assert set(module.STEP_CHOICES) == {
        "preflight",
        "bootstrap-tap",
        "update-endstops",
        "center-verify",
        "tap-baseline",
        "drive-current",
        "eddy-frequency",
        "mesh",
        "run",
        "resume",
    }
    assert "reanchor" not in module.STEP_CHOICES


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


def test_stale_run_state_can_reload_for_resume_and_direct_steps(
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

    state = module._load_run_state(run_dir, strict_hashes=False)
    assert state.run_id == "run"

    # Resume uses the same non-strict load path so deployment-first preflight
    # can synchronize the current source before any motion resumes.


def test_prior_workflow_version_is_rejected_for_the_physical_datum_change(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "prior-coordinate-model"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        '{"run_id": "prior-coordinate-model", "phase": "I1.5", '
        '"committed_phase": "I1.5", '
        f'"workflow_version": {module.WORKFLOW_VERSION - 1}, '
        '"evidence": {}}\n',
        encoding="utf-8",
    )

    with pytest.raises(module.CalibrationError, match="unsupported workflow version"):
        module._load_run_state(run_dir)


def test_checkpoint_records_global_physical_datum_in_every_evidence_record(tmp_path):
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.state = module.RunState(run_id="datum-evidence", phase="I1.0")
    runner.store = module.ArtifactStore(tmp_path, "datum-evidence")
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2

    runner.checkpoint(module.Phase.PREFLIGHT, committed=True, status={"ok": True})

    evidence = runner.state.evidence
    assert evidence["bed_to_nozzle_gap"] == pytest.approx(0.2)
    assert evidence["tap_contact_target_z"] == pytest.approx(-0.2)
    assert evidence["status"] == {"ok": True}


def test_legacy_mesh_verify_state_is_rejected_after_native_tap_mesh_change(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "legacy-run"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        '{"run_id": "legacy-run", "phase": "I1.7", '
        '"committed_phase": "I1.7", '
        f'"workflow_version": {module.WORKFLOW_VERSION}, '
        '"evidence": {}}\n',
        encoding="utf-8",
    )

    with pytest.raises(module.CalibrationError, match="removed phase I1.7"):
        module._load_run_state(run_dir)


def test_resume_after_eddy_calibration_runs_mesh_from_a_clean_frame():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.state = module.RunState(
        run_id="resume-after-eddy",
        phase=module.Phase.EDDY_CALIBRATION.value,
        committed_phase=module.Phase.EDDY_CALIBRATION.value,
    )
    calls = []
    runner.confirm = lambda: calls.append("confirm")
    runner.preflight = lambda **kwargs: calls.append(
        f"preflight:{kwargs.get('sync_printer')}"
    )
    runner.final_mesh = lambda *, clean_frame=True: calls.append(f"mesh:{clean_frame}")
    runner.checkpoint = lambda phase, **kwargs: calls.append(phase.value)
    runner.write_final_report = lambda: calls.append("report")

    runner.resume()

    assert calls == [
        "confirm",
        "preflight:True",
        "mesh:True",
        module.Phase.FINISH.value,
        "report",
    ]


def test_resume_after_committed_tap_mesh_finishes_without_mesh_diagnostic():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.state = module.RunState(
        run_id="resume-after-tap-mesh",
        phase=module.Phase.MESH_SCAN.value,
        committed_phase=module.Phase.MESH_SCAN.value,
    )
    calls = []
    runner.confirm = lambda: calls.append("confirm")
    runner.preflight = lambda **kwargs: calls.append(
        f"preflight:{kwargs.get('sync_printer')}"
    )
    runner.final_mesh = lambda **kwargs: (_ for _ in ()).throw(AssertionError("mesh"))
    runner.checkpoint = lambda phase, **kwargs: calls.append(phase.value)
    runner.write_final_report = lambda: calls.append("report")

    runner.resume()

    assert calls == [
        "confirm",
        "preflight:True",
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
    runner.preflight = lambda **kwargs: calls.append(
        f"preflight:{kwargs.get('sync_printer')}"
    )
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
        "preflight:True",
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


def test_coil_pose_uses_live_nozzle_to_coil_offset():
    module = _load_module()

    nozzle = module.coil_over_target_pose(
        module.Pose(150.0, 150.0, 20.0),
        module.Pose(-57.391, -18.997, 1.399),
    )
    assert nozzle == module.Pose(207.391, 168.997, 18.601)


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
        {"bed_mesh tap_7x7": {"mesh_matrix": []}},
        "tap_7x7",
    )
    with pytest.raises(module.CalibrationError, match="unexpected pending"):
        module.require_only_transient_mesh_pending(
            {"bed_mesh default": {}, "stepper_z": {"position_endstop": 1}},
            "tap_7x7",
        )


def test_atomic_calibration_update(tmp_path):
    module = _load_module()

    calibration = tmp_path / "calib.yaml"
    calibration.write_text(
        "# keep this comment\n"
        "bed_to_nozzle_gap: 0.200\n"
        "tools:\n"
        "  t0:\n"
        "    z_endstop: 10.000\n"
        "  t1:\n"
        "    z_endstop: 8.726\n"
        "eddy_relative_calibration:\n"
        "  klipper:\n"
        "    reg_drive_current: 15\n"
        "    tap_threshold: 5000\n"
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
            ("bed_to_nozzle_gap",): 0.2,
        },
    )
    text = calibration.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "z_endstop: 9.750" in text
    assert "tap_threshold: 5000" in text


def _tap_mesh_runner(module, *, profile=None, pending=None):
    tap_mesh = {
        "profile": "tap_7x7",
        "samples": 1,
        "horizontal_move_z": 5.0,
        "probe_count": (7, 7),
        "probe_count_text": "7,7",
    }

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
                        "profile_name": profile or tap_mesh["profile"],
                        "mesh_matrix": [[0.0, 0.0], [0.0, 0.0]],
                    },
                    "configfile": {
                        "save_config_pending_items": pending
                        if pending is not None
                        else {f"bed_mesh {tap_mesh['profile']}": {}},
                        "settings": {
                            "bed_mesh": {
                                "mesh_min": "42,20",
                                "mesh_max": "190,275",
                            }
                        },
                    },
                }
            raise AssertionError(objects)

    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = False
    runner.tap_threshold = 7500.0
    runner.tap_mesh = {
        "profile": "tap_7x7",
        "samples": 1,
        "horizontal_move_z": 5.0,
        "probe_count": (7, 7),
        "probe_count_text": "7,7",
    }
    runner.tap_mesh = tap_mesh
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2
    runner.client = Client()
    runner.store = Store()
    runner._home_clean_frame = lambda: None
    runner.verify_active_tap_mesh = lambda _status: {
        "passed": True,
        "failures": [],
        "points": [],
    }
    return runner


def test_final_mesh_uses_native_tap_profile_and_active_contact_verification():
    module = _load_module()
    runner = _tap_mesh_runner(module)
    commands = []
    checkpoints = []
    runner._gcode = lambda script, **kwargs: commands.append((script, kwargs))
    runner.checkpoint = lambda *args, **kwargs: checkpoints.append((args, kwargs))

    runner.final_mesh()

    assert commands == [
        ("BED_MESH_IDEX_CALIBRATE", {"timeout": 900.0}),
        ("BED_MESH_PROFILE LOAD=tap_7x7", {}),
    ]
    assert all("EDDY_" not in command[0] for command in commands)
    assert commands[-1][0] == "BED_MESH_PROFILE LOAD=tap_7x7"
    assert runner.store.writes["mesh-tap.json"]["profile"] == "tap_7x7"
    assert runner.store.writes["mesh-tap.json"]["tap_contact_target_z"] == pytest.approx(
        -0.2
    )
    assert checkpoints[0][0] == (module.Phase.MESH_SCAN,)
    assert checkpoints[0][1]["committed"] is True


def test_final_mesh_rejects_wrong_active_profile_or_pending_section():
    module = _load_module()
    runner = _tap_mesh_runner(module, profile="default")
    runner._gcode = lambda *_args, **_kwargs: None
    runner.checkpoint = lambda *_args, **_kwargs: None

    with pytest.raises(module.CalibrationError, match="did not leave active profile"):
        runner.final_mesh()

    runner = _tap_mesh_runner(module, pending={"bed_mesh default": {}})
    runner._gcode = lambda *_args, **_kwargs: None
    runner.checkpoint = lambda *_args, **_kwargs: None
    with pytest.raises(module.CalibrationError, match="unexpected pending"):
        runner.final_mesh()


def test_active_tap_mesh_verification_surveys_configured_bounds_and_reference():
    module = _load_module()
    runner = _tap_mesh_runner(module)
    status = runner.client.status(["bed_mesh", "configfile"])
    calls = []

    def collect_taps(**kwargs):
        calls.append((kwargs["x"], kwargs["y"]))
        contact_z = runner.tap_contact_target_z
        return (
            module.summarize_taps([contact_z]),
            [
                {
                    "ok": True,
                    "contact_x": kwargs["x"],
                    "contact_y": kwargs["y"],
                    "contact_z": contact_z,
                    "post_retract_toolhead_z": 3.8,
                }
            ],
        )

    runner.collect_taps = collect_taps
    runner.active_mesh_transform_z_at = lambda _point: 0.0
    verification = module.Iteration1Runner.verify_active_tap_mesh(runner, status)

    assert verification["passed"] is True
    assert calls == [
        (42.0, 20.0),
        (150.0, 20.0),
        (190.0, 20.0),
        (42.0, 150.0),
        (150.0, 150.0),
        (190.0, 150.0),
        (42.0, 275.0),
        (150.0, 275.0),
        (190.0, 275.0),
    ]
    assert all(
        point["measured_bed_to_nozzle_gap"] == pytest.approx(0.2)
        for point in verification["points"]
    )
    assert all(point["gap_residual"] == pytest.approx(0.0) for point in verification["points"])


def test_active_tap_mesh_verification_records_failure_after_all_points():
    module = _load_module()
    runner = _tap_mesh_runner(module)
    status = runner.client.status(["bed_mesh", "configfile"])
    calls = []

    def collect_taps(**kwargs):
        calls.append((kwargs["x"], kwargs["y"]))
        if kwargs["x"] == 190.0 and kwargs["y"] == 275.0:
            raise module.CalibrationError("simulated Tap acquisition failure")
        contact_z = runner.tap_contact_target_z
        return (
            module.summarize_taps([contact_z]),
            [
                {
                    "ok": True,
                    "contact_x": kwargs["x"],
                    "contact_y": kwargs["y"],
                    "contact_z": contact_z,
                    "post_retract_toolhead_z": 3.8,
                }
            ],
        )

    runner.collect_taps = collect_taps
    runner.active_mesh_transform_z_at = lambda _point: 0.0
    verification = module.Iteration1Runner.verify_active_tap_mesh(runner, status)

    assert verification["passed"] is False
    assert verification["failure_count"] == 1
    assert "simulated Tap acquisition failure" in verification["failures"][0]
    assert len(calls) == 9


def test_active_tap_mesh_verification_uses_configured_tap_median():
    module = _load_module()
    runner = _tap_mesh_runner(module)
    runner.tap_mesh["samples"] = 3
    status = runner.client.status(["bed_mesh", "configfile"])
    sample_counts = []

    def collect_taps(**kwargs):
        sample_counts.append((kwargs["count"], kwargs["max_attempts"]))
        values = [-0.201, -0.199, -0.200]
        return (
            module.summarize_taps(values),
            [
                {
                    "ok": True,
                    "contact_x": kwargs["x"],
                    "contact_y": kwargs["y"],
                    "contact_z": value,
                    "post_retract_toolhead_z": 3.8,
                }
                for value in values
            ],
        )

    runner.collect_taps = collect_taps
    runner.active_mesh_transform_z_at = lambda _point: 0.0
    verification = module.Iteration1Runner.verify_active_tap_mesh(runner, status)

    assert verification["passed"] is True
    assert sample_counts == [(3, 3)] * 9
    assert all(
        point["raw_contact_z"] == pytest.approx(-0.200)
        for point in verification["points"]
    )


def test_active_absolute_tap_mesh_maps_the_tapped_plane_to_gcode_zero():
    module = _load_module()
    runner = _tap_mesh_runner(module)
    runner.bed_to_nozzle_gap = 0.0
    runner.tap_contact_target_z = 0.0
    status = runner.client.status(["bed_mesh", "configfile"])
    raw_contact_z = 0.054576

    def collect_taps(**kwargs):
        return (
            module.summarize_taps([raw_contact_z]),
            [
                {
                    "ok": True,
                    "contact_x": kwargs["x"],
                    "contact_y": kwargs["y"],
                    "contact_z": raw_contact_z,
                    "post_retract_toolhead_z": 3.8,
                }
            ],
        )

    runner.collect_taps = collect_taps
    runner.active_mesh_transform_z_at = lambda _point: raw_contact_z
    verification = module.Iteration1Runner.verify_active_tap_mesh(runner, status)

    assert verification["passed"] is True
    assert all(
        point["measured_bed_to_nozzle_gap"] == pytest.approx(0.0)
        for point in verification["points"]
    )


def test_final_mesh_keeps_active_profile_and_evidence_after_failed_verification():
    module = _load_module()
    runner = _tap_mesh_runner(module)
    checkpoints = []
    runner._gcode = lambda *_args, **_kwargs: None
    runner.checkpoint = lambda *args, **kwargs: checkpoints.append((args, kwargs))
    runner.verify_active_tap_mesh = lambda _status: {
        "passed": False,
        "failures": ["(42.000, 20.000): simulated failure"],
        "points": [{} for _ in range(9)],
    }

    with pytest.raises(module.CalibrationError, match="surveying all points"):
        runner.final_mesh()

    artifact = runner.store.writes["mesh-tap.json"]
    assert artifact["active_profile_verification"]["passed"] is False
    assert checkpoints == [
        (
            (module.Phase.MESH_SCAN,),
            {
                "committed": False,
                "mesh_status": runner.client.status(["bed_mesh", "configfile"]),
                "mesh_tap": artifact,
            },
        )
    ]


def test_final_mesh_runs_one_native_tap_mesh_at_safe_clearance():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = True
    runner.tap_threshold = 7500.0
    runner.tap_mesh = {
        "profile": "tap_7x7",
        "samples": 1,
        "horizontal_move_z": 5.0,
        "probe_count": (7, 7),
        "probe_count_text": "7,7",
    }
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2
    scripts = []
    checkpoints = []
    homes = []
    runner._home_clean_frame = lambda: homes.append("home")
    runner._gcode = lambda script, **kwargs: scripts.append((script, kwargs))
    runner.checkpoint = lambda *args, **kwargs: checkpoints.append((args, kwargs))

    runner.final_mesh()

    assert scripts == [
        ("BED_MESH_IDEX_CALIBRATE", {"timeout": 900.0}),
    ]
    assert checkpoints == [
        (
            (module.Phase.MESH_SCAN,),
            {
                "committed": False,
                "bed_to_nozzle_gap": 0.2,
                "tap_contact_target_z": -0.2,
            },
        )
    ]
    assert homes == ["home"]


def test_final_mesh_can_reuse_committed_post_eddy_frame():
    module = _load_module()
    runner = object.__new__(module.Iteration1Runner)
    runner.dry_run = True
    runner.tap_threshold = 7500.0
    runner.tap_mesh = {
        "profile": "tap_7x7",
        "samples": 1,
        "horizontal_move_z": 5.0,
        "probe_count": (7, 7),
        "probe_count_text": "7,7",
    }
    runner.bed_to_nozzle_gap = 0.2
    runner.tap_contact_target_z = -0.2
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
    mesh_runner.tap_threshold = 7500.0
    mesh_runner.tap_mesh = {
        "profile": "tap_7x7",
        "samples": 1,
        "horizontal_move_z": 5.0,
        "probe_count": (7, 7),
        "probe_count_text": "7,7",
    }
    mesh_runner.bed_to_nozzle_gap = 0.2
    mesh_runner.tap_contact_target_z = -0.2
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
