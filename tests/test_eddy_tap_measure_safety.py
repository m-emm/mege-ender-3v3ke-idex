import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "klipper_setup"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "eddy_tap_measure.py"
)
SPEC = importlib.util.spec_from_file_location("eddy_tap_measure", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeGcmd:
    def __init__(self):
        self.messages = []

    def respond_info(self, message):
        self.messages.append(message)


class FakeToolhead:
    def __init__(self, z):
        self.position = [50.0, 50.0, float(z)]
        self.wait_count = 0

    def get_position(self):
        return list(self.position)

    def wait_moves(self):
        self.wait_count += 1

    def get_status(self, _eventtime):
        return {"axis_maximum": [244.0, 296.0, 289.0, 0.0]}


class FakeGcode:
    def __init__(self, toolhead, restore=True):
        self.toolhead = toolhead
        self.commands = []
        self.restore = restore

    def run_script_from_command(self, script):
        self.commands.append(script)
        if not self.restore:
            return
        for line in script.splitlines():
            if line.startswith("G1 Z"):
                self.toolhead.position[2] = float(line.split()[1][1:])

    @staticmethod
    def error(message):
        return RuntimeError(message)


def make_runner(toolhead, *, restore=True):
    runner = MODULE.EddyTapMeasure.__new__(MODULE.EddyTapMeasure)
    runner.gcode = FakeGcode(toolhead, restore=restore)
    runner.move_speed = 20.0
    runner.last_tap_measurement = None
    runner._require_t0_active = lambda command_name: None
    runner._require_homed = lambda command_name: toolhead
    return runner


def tap_measurement(status="success"):
    return {
        "bed_x": 50.0,
        "bed_y": 50.0,
        "tap": {
            "status": status,
            "index": 1,
            "requested_count": 1,
            "start_z": 5.0,
            "target_z": -2.2,
            "samples": [] if status != "success" else [{"x": 50.0, "y": 50.0, "z": 0.0}],
        },
        "compare": False,
    }


def test_success_restores_to_initial_z_and_uses_no_xy_cleanup():
    toolhead = FakeToolhead(10.0)
    runner = make_runner(toolhead)

    def operation(_gcmd, _toolhead):
        toolhead.position[2] = -2.2
        return tap_measurement()

    runner._cmd_EDDY_TAP_MEASURE_impl = operation
    gcmd = FakeGcmd()

    result = runner.cmd_EDDY_TAP_MEASURE(gcmd)

    assert toolhead.position[2] >= 10.0
    assert [command for command in runner.gcode.commands if "X" in command or "Y" in command] == []
    assert result["safety"]["initial_z"] == pytest.approx(10.0)
    assert result["safety"]["final_z"] >= result["safety"]["initial_z"]
    assert len(gcmd.messages) == 1
    assert "z=0.000000 target=(50.000, 50.000) contact=(50.000, 50.000, 0.000000)" in gcmd.messages[0]
    assert "mean_z=" not in gcmd.messages[0]
    assert "initial_z=" not in gcmd.messages[0]
    assert "final_z=" not in gcmd.messages[0]


def test_no_trigger_return_is_restored_and_reported_as_failure():
    toolhead = FakeToolhead(5.0)
    runner = make_runner(toolhead)

    def operation(_gcmd, _toolhead):
        toolhead.position[2] = -2.2
        runner.last_tap_measurement = tap_measurement("no_trigger")
        return None

    runner._cmd_EDDY_TAP_MEASURE_impl = operation
    gcmd = FakeGcmd()

    runner.cmd_EDDY_TAP_MEASURE(gcmd)

    assert toolhead.position[2] >= 5.0
    assert len(gcmd.messages) == 1
    assert "status=no_trigger" in gcmd.messages[0]
    assert "start_z=5.000000 target_z=-2.200000" in gcmd.messages[0]
    assert "initial_z=" not in gcmd.messages[0]
    assert "final_z=" not in gcmd.messages[0]


def test_operation_error_is_reported_after_restoration():
    toolhead = FakeToolhead(7.0)
    runner = make_runner(toolhead)

    def operation(_gcmd, _toolhead):
        toolhead.position[2] = -2.2
        raise RuntimeError("tap rejected")

    runner._cmd_EDDY_TAP_MEASURE_impl = operation
    gcmd = FakeGcmd()

    with pytest.raises(RuntimeError, match="tap rejected"):
        runner.cmd_EDDY_TAP_MEASURE(gcmd)

    assert toolhead.position[2] >= 7.0
    assert len(gcmd.messages) == 1
    assert "status=error" in gcmd.messages[0]
    assert "initial_z=" not in gcmd.messages[0]
    assert "final_z=" not in gcmd.messages[0]


def test_currently_higher_z_is_not_lowered():
    toolhead = FakeToolhead(3.0)
    runner = make_runner(toolhead)

    def operation(_gcmd, _toolhead):
        toolhead.position[2] = 12.0
        return tap_measurement()

    runner._cmd_EDDY_TAP_MEASURE_impl = operation
    runner.cmd_EDDY_TAP_MEASURE(FakeGcmd())

    assert toolhead.position[2] == pytest.approx(12.0)
    assert runner.gcode.commands == []


def test_summary_uses_mesh_corrected_z_and_stats_only_for_multiple_taps():
    runner = make_runner(FakeToolhead(5.0))
    measurement = tap_measurement()
    measurement["tap"]["requested_count"] = 2
    measurement["tap"]["samples"] = [
        {"x": 50.0, "y": 50.0, "z": -0.10},
        {"x": 50.001, "y": 50.002, "z": -0.12},
    ]
    measurement["mesh"] = {"commanded_z_for_tap_median": -0.11}
    gcmd = FakeGcmd()

    runner._tap_summary(gcmd, measurement, 5.0, 5.0)

    assert gcmd.messages[0].startswith(
        "EDDY_TAP_MEASURE: z=-0.110000 target=(50.000, 50.000) "
        "contact=(50.001, 50.002, -0.110000)"
    )
    assert "stats(mean_z=-0.110000 median_z=-0.110000" in gcmd.messages[0]


def test_restore_failure_is_explicit():
    toolhead = FakeToolhead(5.0)
    runner = make_runner(toolhead, restore=False)

    def operation(_gcmd, _toolhead):
        toolhead.position[2] = -2.2
        return tap_measurement()

    runner._cmd_EDDY_TAP_MEASURE_impl = operation
    gcmd = FakeGcmd()

    with pytest.raises(RuntimeError, match="final Z restore incomplete"):
        runner.cmd_EDDY_TAP_MEASURE(gcmd)

    assert len(gcmd.messages) == 1
    assert "final Z restore error=" in gcmd.messages[0]
