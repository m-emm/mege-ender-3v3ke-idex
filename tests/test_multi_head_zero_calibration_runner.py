import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/run_multi_head_zero_contact_map.py"
APPLIER_PATH = ROOT / "scripts/apply_multi_head_zero_maximum_calibration.py"
VERIFIER_PATH = ROOT / "scripts/verify_multi_head_zero_alignment.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("multi_head_zero_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_applier():
    spec = importlib.util.spec_from_file_location(
        "multi_head_zero_applier", APPLIER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "multi_head_zero_verifier", VERIFIER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_tool_selection_is_exposed_to_the_user():
    runner = load_runner()
    assert runner.build_parser().parse_args([]).tool == "both"
    assert runner.build_parser().parse_args(["--tool", "T1"]).tool == "T1"
    with pytest.raises(SystemExit):
        runner.build_parser().parse_args(["--workflow", "calibration"])


def test_calibration_seed_is_serpentine_and_keeps_the_18_contact_contract():
    runner = load_runner()
    args = SimpleNamespace(
        tool="T0",
        moonraker_url="unused",
        x_min=0.0,
        x_max=6.0,
        y_min=-3.0,
        y_max=3.0,
        ball_radius_mm=10.0,
        ring_radius_mm=3.0,
    )
    records = []
    progress = []

    def contact(_url, *, x, y, sample_index, phase, **kwargs):
        return {
            "sample_index": sample_index,
            "commanded_x": x,
            "commanded_y": y,
            "trigger_z": 1.0 - 0.05 * ((x - 3.0) ** 2 + y**2),
            "status": "completed",
            "phase": phase,
            "tool": kwargs["tool"],
        }

    summary = runner.run_calibration(
        args,
        0,
        records,
        contact_function=contact,
        progress_callback=lambda record: progress.append(record["sample_index"]),
    )

    assert len(records) == 18
    assert progress == list(range(1, 19))
    assert [
        (record["commanded_x"], record["commanded_y"]) for record in records[:9]
    ] == [
        (0.0, -3.0),
        (3.0, -3.0),
        (6.0, -3.0),
        (6.0, 0.0),
        (3.0, 0.0),
        (0.0, 0.0),
        (0.0, 3.0),
        (3.0, 3.0),
        (6.0, 3.0),
    ]
    assert summary["phase_1"]["fit"]["status"] == "valid"


def test_verification_uses_centre_and_eight_point_ring():
    runner = load_runner()
    args = SimpleNamespace(
        tool="T0",
        moonraker_url="unused",
        reference_x=75.0,
        reference_y=-9.0,
        ball_radius_mm=5.0,
        ring_radius_mm=2.8,
    )
    records = []

    def contact(_url, *, x, y, sample_index, phase, **kwargs):
        return {
            "sample_index": sample_index,
            "commanded_x": x,
            "commanded_y": y,
            "trigger_z": 1.0 + 0.01 * (x - 75.0) - 0.02 * (y + 9.0),
            "status": "completed",
            "phase": phase,
            "tool": kwargs["tool"],
        }

    summary = runner.run_verification(args, 0, records, contact_function=contact)

    assert len(records) == 9
    assert summary["algorithm"] == "nine_contact_octagonal_verification_v2"
    assert summary["termination_reason"] == "nine_contact_complete"
    assert [record["direction"] for record in records[1:]] == [
        "east",
        "north_east",
        "north",
        "north_west",
        "west",
        "south_west",
        "south",
        "south_east",
    ]
    assert summary["estimated_center"]["trigger_z"] == pytest.approx(1.0)
    assert summary["periphery_mean_z"] == pytest.approx(1.0)


def test_runtime_frame_requires_zero_manual_adjustment_and_inactive_mesh():
    runner = load_runner()
    current = {
        "gcode_move": {"homing_origin": [0.0, -1.5, 0.6]},
        "bed_mesh": {"profile_name": "", "mesh_matrix": [[]]},
        "idex_manual_tuning": {
            "manual_z_adjust": 0.0,
            "active_tool_z_offset": 0.6,
        },
        "gcode_macro _IDEX_TOOL_STATE": {
            "t1_y_offset": -1.5,
            "t1_z_offset": 0.6,
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "abc123"},
    }

    provenance = runner.runtime_frame_provenance(current, 1)
    assert provenance["origin_error_mm"] == pytest.approx([0.0, 0.0, 0.0])
    assert provenance["mesh"]["active"] is False

    current["bed_mesh"]["profile_name"] = "default"
    with pytest.raises(runner.ContactMapError, match="inactive runtime mesh"):
        runner.runtime_frame_provenance(current, 1)


def test_captured_trace_isolates_t0_centre_change_from_t1_frame_conversion():
    trace = json.loads(
        (ROOT / "tests/fixtures/multi_head_zero_latest_z_trace.json").read_text(
            encoding="utf-8"
        )
    )

    assert trace["mesh"] == {"profile_name": "", "mesh_matrix": [[]]}
    assert (
        trace["t1"]["verification_centre_machine_z"]
        - trace["t1"]["verification_gcode_origin_z"]
    ) == pytest.approx(trace["t1"]["verification_centre_logical_z"])
    assert trace["t1"]["verification_centre_machine_z"] == pytest.approx(
        trace["t1"]["calibration_centre_machine_z"]
    )
    assert (
        trace["t0"]["verification_centre_logical_z"]
        - trace["t0"]["calibration_centre_logical_z"]
    ) == pytest.approx(-0.1225)


def test_preparation_homes_only_when_xyz_is_not_already_homed(monkeypatch):
    runner = load_runner()
    statuses = iter(
        (
            {"webhooks": {"state": "ready"}, "toolhead": {"homed_axes": "xy"}},
            {
                "webhooks": {"state": "ready"},
                "toolhead": {"homed_axes": "xyz"},
                "multi_head_zero_probe": {"state": "RELEASED"},
            },
        )
    )
    commands = []
    monkeypatch.setattr(runner, "status", lambda _url: next(statuses))
    monkeypatch.setattr(runner, "printer_log", lambda *_args: None)
    monkeypatch.setattr(
        runner, "run_gcode", lambda _url, script: commands.append(script)
    )

    _, _, homing_required = runner.require_ready_and_prepare("unused")

    assert homing_required is True
    assert commands == ["G28\nM400", "BED_MESH_CLEAR\nM400"]


def test_tool_switch_lifts_once_and_is_skipped_for_the_active_tool(monkeypatch):
    runner = load_runner()
    commands = []
    observed_tools = iter(("T0", runner.ContactMapError("T1 inactive"), "T1"))

    def verify(_url, tool, _index):
        result = next(observed_tools)
        if isinstance(result, Exception):
            raise result
        assert result == tool
        return {"active_tool": int(tool[-1])}

    monkeypatch.setattr(runner, "verify_selected_tool", verify)
    monkeypatch.setattr(runner, "printer_log", lambda *_args: None)
    monkeypatch.setattr(
        runner, "run_gcode", lambda _url, script: commands.append(script)
    )

    runner.select_tool_once("unused", "T0")
    runner.select_tool_once("unused", "T1")

    assert commands == ["G90\nG1 Z10.000 F1200\nT1\nM400"]


def test_contact_converts_logical_target_and_normalizes_measurement(monkeypatch):
    runner = load_runner()
    commands = []
    monkeypatch.setattr(
        runner,
        "verify_selected_tool",
        lambda *_args: {"active_tool": 1, "toolhead_extruder": "extruder1"},
    )
    statuses = iter(
        (
            {
                "gcode_move": {"homing_origin": [0.0, -3.0, 1.5]},
                "multi_head_zero_probe": {"start_z": 4.0},
                "bed_mesh": {"profile_name": "", "mesh_matrix": [[]]},
                "idex_manual_tuning": {
                    "manual_z_adjust": 0.0,
                    "active_tool_z_offset": 1.5,
                },
                "gcode_macro _IDEX_TOOL_STATE": {
                    "t1_y_offset": -3.0,
                    "t1_z_offset": 1.5,
                },
                "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "abc123"},
            },
            {
                "gcode_move": {"homing_origin": [0.0, -3.0, 1.5]},
                "multi_head_zero_probe": {"start_z": 4.0},
                "bed_mesh": {"profile_name": "", "mesh_matrix": [[]]},
                "idex_manual_tuning": {
                    "manual_z_adjust": 0.0,
                    "active_tool_z_offset": 1.5,
                },
                "gcode_macro _IDEX_TOOL_STATE": {
                    "t1_y_offset": -3.0,
                    "t1_z_offset": 1.5,
                },
                "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "abc123"},
                "multi_head_zero_probe": {
                    "last_measurement": {
                        "status": "completed",
                        "commanded_x": 75.0,
                        "commanded_y": -9.0,
                        "machine_commanded_x": 75.0,
                        "machine_commanded_y": -12.0,
                        "gcode_origin": [0.0, -3.0, 1.5],
                        "trigger_x": 75.0,
                        "trigger_y": -12.0,
                        "trigger_z": 2.25,
                    }
                },
            },
        )
    )
    monkeypatch.setattr(runner, "status", lambda _url: next(statuses))
    monkeypatch.setattr(
        runner, "run_gcode", lambda _url, script: commands.append(script)
    )

    record = runner.perform_contact(
        "unused",
        tool="T1",
        tool_index=1,
        x=75.0,
        y=-9.0,
        sample_index=1,
        phase="phase_1_seed",
    )

    assert commands == [
        "MULTI_HEAD_ZERO_CONTACT X=75.000 Y=-9.000 TOOL=1 " "ALLOW_NO_CONTACT=1\nM400"
    ]
    assert record["commanded_x"] == 75.0
    assert record["commanded_y"] == -9.0
    assert record["trigger_x"] == 75.0
    assert record["trigger_y"] == -9.0
    assert record["trigger_z"] == pytest.approx(0.75)
    assert record["machine_commanded_x"] == 75.0
    assert record["machine_commanded_y"] == -12.0
    assert record["machine_trigger_z"] == 2.25
    assert record["frame_provenance"]["mesh"]["active"] is False
    assert record["frame_provenance"]["origin_error_mm"] == pytest.approx(
        [0.0, 0.0, 0.0]
    )


def test_workflow_event_is_emitted_to_the_printer_console(monkeypatch):
    runner = load_runner()
    commands = []
    monkeypatch.setattr(
        runner, "run_gcode", lambda _url, script: commands.append(script)
    )

    runner.printer_log("unused", 'T0 1/18 phase_1_seed Z=0.500 "quoted"')

    assert commands == [
        "RESPOND TYPE=echo MSG=\"MHZ calibration: T0 1/18 phase_1_seed Z=0.500 'quoted'\""
    ]


def test_t1_endstop_correction_reduces_positive_logical_residuals():
    applier = load_applier()
    source = {"t1": {"x_endstop": 300.0, "y_endstop": -10.0, "z_endstop": 290.0}}
    t0 = {"x": 10.0, "y": 20.0, "z": 30.0}
    t1 = {"x": 10.2, "y": 20.3, "z": 30.4}

    error, suggested = applier.suggested_t1_endstops(source, t0, t1)

    assert error == pytest.approx({"x": 0.2, "y": 0.3, "z": 0.4})
    assert suggested == {
        "x_endstop": 299.8,
        "y_endstop": -10.3,
        "z_endstop": 289.6,
    }


def test_verification_z_pass_uses_only_the_physical_centre_contact(tmp_path):
    verifier = load_verifier()
    directions = verifier.VERIFICATION_DIRECTIONS

    def measurement(name, x, y, centre_z, periphery_z):
        return {
            "run_dir": tmp_path / name,
            "x": x,
            "y": y,
            "z": centre_z,
            "centre_z": centre_z,
            "periphery_mean_z": periphery_z,
            "ring": {
                direction: {"x": 0.0, "y": 0.0, "z": periphery_z}
                for direction in directions
            },
        }

    result = verifier.paired_result(
        tmp_path / "calibration_result.json",
        measurement("T0", 75.0, -9.0, 0.800, 0.200),
        measurement("T1", 75.01, -9.01, 0.810, 0.400),
    )

    assert result["pass"] is True
    assert result["pass_components"] == {"x": True, "y": True, "z_center": True}
    assert result["z_diagnostics"]["periphery_mean_delta_mm"] == pytest.approx(0.2)
    assert result["z_diagnostics"]["authoritative_for_z"] is False


def test_dashboard_snapshot_is_atomic_and_retains_completed_run(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "DEFAULT_DASHBOARD_ROOT", str(tmp_path))
    dashboard = runner.DashboardPublisher("run-1", "calibration", "both")
    dashboard.payload["status"] = "running"
    dashboard.update_run(
        "T0",
        "calibration",
        [{"sample_index": 1, "status": "completed", "trigger_z": 0.5}],
        18,
        "running",
    )
    dashboard.finish("completed")

    snapshot = tmp_path / "data" / "current.json"
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["chapters"]["calibration"]["runs"]["t0"]["progress"] == {
        "completed": 1,
        "total": 18,
    }
    assert payload["last_completed"]["run_id"] == "run-1"
    assert not list((tmp_path / "data").glob(".*.tmp"))

    verification = runner.DashboardPublisher("run-2", "verification", "both")
    verification.update_run(
        "T0",
        "verification",
        [{"sample_index": 1, "status": "completed", "trigger_z": 0.51}],
        9,
        "running",
    )
    retained = json.loads(snapshot.read_text(encoding="utf-8"))
    assert retained["schema_version"] == 2
    assert retained["chapters"]["calibration"]["runs"]["t0"]["progress"] == {
        "completed": 1,
        "total": 18,
    }
    assert retained["chapters"]["verification"]["runs"]["t0"]["progress"] == {
        "completed": 1,
        "total": 9,
    }


def test_dashboard_assets_render_live_and_final_sections():
    dashboard_dir = ROOT / "klipper_setup/klipper_config/calibration_dashboard"
    html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    script = (dashboard_dir / "app.js").read_text(encoding="utf-8")
    captured = json.loads(
        (
            ROOT / "tests/fixtures/multi_head_zero_dashboard_t0_calibration.json"
        ).read_text(encoding="utf-8")
    )

    assert 'id="calibration-chapter"' in html
    assert 'id="verification-chapter"' in html
    assert "data/current.json" in script
    assert "normaliseChapters" in script
    assert "last_completed" in script
    assert "isometricPlot" in script
    assert "plot-modal" in html
    assert "Paired verification plot" not in script
    assert "Z repeatability audit" in script
    assert "zToXyScale: 1.0" in script
    assert "rotationDegrees: 10" in script
    assert "gridDivisions: 6" in script
    assert "height: 390" in script
    assert "xySpanPixels: 247.5" in script
    assert "grid-line" in script
    assert "plotBounds" in script
    assert len(captured["runs"]["t0"]["records"]) == 18
    assert captured["runs"]["t0"]["records"][9]["trigger_z"] == pytest.approx(0.8405)
