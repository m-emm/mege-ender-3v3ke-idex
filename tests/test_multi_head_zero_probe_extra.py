import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXTRA_PATH = (
    ROOT
    / "klipper_setup"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "multi_head_zero_probe.py"
)


def load_extra():
    spec = importlib.util.spec_from_file_location(
        "multi_head_zero_probe_test", EXTRA_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeGcmd:
    def __init__(self, values):
        self.values = values
        self.responses = []

    def get_float(self, name, default=None, above=None):
        value = float(self.values.get(name, default))
        assert above is None or value > above
        return value

    def get_int(self, name, default=None, minval=None, maxval=None):
        value = int(self.values.get(name, default))
        assert minval is None or value >= minval
        assert maxval is None or value <= maxval
        return value

    def respond_info(self, message):
        self.responses.append(message)


class FakeGcode:
    def __init__(self, printer):
        self.printer = printer
        self.commands = {}
        self.scripts = []

    def register_command(self, name, callback, desc=None):
        self.commands[name] = callback

    def error(self, message):
        return RuntimeError(message)

    def run_script_from_command(self, script):
        self.scripts.append(script)
        for line in script.splitlines():
            if line == "BED_MESH_CLEAR":
                self.printer.bed_mesh.active = False
            elif line.startswith("T") and line in {"T0", "T1"}:
                tool = int(line[-1])
                self.printer.manual.active_tool = tool
                self.printer.tool_state.active_tool = tool
                self.printer.toolhead.extruder = (
                    "extruder" if tool == 0 else "extruder1"
                )
                self.printer.carriage.tool = tool
                self.printer.gcode_move.origin = [0.0, -1.5, 0.6] if tool else [0.0] * 3
            elif line.startswith("G1 "):
                values = {}
                for token in line.split():
                    if token[0] in "XYZ":
                        values[token[0]] = float(token[1:])
                for axis, value in values.items():
                    index = "XYZ".index(axis)
                    self.printer.toolhead.position[index] = (
                        value + self.printer.gcode_move.origin[index]
                    )


class FakeToolhead:
    def __init__(self):
        self.position = [10.0, 10.0, 1.0, 0.0]
        self.extruder = "extruder"
        self.homed_axes = "xyz"
        self.manual_moves = []

    def get_status(self, _eventtime):
        return {
            "homed_axes": self.homed_axes,
            "extruder": self.extruder,
            "axis_minimum": [-100.0, -100.0, -2.2],
            "axis_maximum": [400.0, 300.0, 300.0],
        }

    def get_position(self):
        return list(self.position)

    def get_last_move_time(self):
        return 1.0

    def manual_move(self, position, _speed):
        self.manual_moves.append(list(position))
        self.position = list(position)

    def wait_moves(self):
        pass


class FakeStatus:
    def __init__(self, **values):
        self.__dict__.update(values)

    def get_status(self, _eventtime):
        return self.__dict__.copy()


class FakeBedMesh:
    def __init__(self, active):
        self.active = active

    def get_status(self, _eventtime):
        return {
            "profile_name": "default" if self.active else "",
            "mesh_matrix": [[0.1]] if self.active else [[]],
        }


class FakeGcodeMove:
    def __init__(self):
        self.origin = [0.0, 0.0, 0.0]

    def get_status(self, _eventtime):
        return {"homing_origin": list(self.origin)}


class FakeCarriage:
    def __init__(self):
        self.tool = 0

    def get_status(self, _eventtime):
        if self.tool == 0:
            return {"carriage_0": "PRIMARY", "carriage_1": "INACTIVE"}
        return {"carriage_0": "INACTIVE", "carriage_1": "PRIMARY"}


class FakeEndstop:
    def __init__(self, printer):
        self.printer = printer

    def add_stepper(self, _stepper):
        pass

    def query_endstop(self, _print_time):
        return self.printer.stuck_switch or self.printer.toolhead.position[2] < 2.0


class FakePins:
    def __init__(self, printer):
        self.printer = printer

    def setup_pin(self, _pin_type, _pin):
        return FakeEndstop(self.printer)


class FakeHoming:
    def __init__(self, printer):
        self.printer = printer
        self.calls = []

    def probing_move(self, _endstop, target, _speed):
        self.calls.append(list(target))
        trigger = [target[0], target[1], 2.25, 0.0]
        self.printer.toolhead.position = list(trigger)
        return trigger


class FakePrinter:
    command_error = RuntimeError

    def __init__(self, mesh_active=True):
        self.stuck_switch = False
        self.toolhead = FakeToolhead()
        self.manual = FakeStatus(active_tool=0)
        self.tool_state = FakeStatus(active_tool=0)
        self.carriage = FakeCarriage()
        self.bed_mesh = FakeBedMesh(mesh_active)
        self.gcode_move = FakeGcodeMove()
        self.gcode = FakeGcode(self)
        self.homing = FakeHoming(self)
        self.objects = {
            "gcode": self.gcode,
            "toolhead": self.toolhead,
            "print_stats": FakeStatus(state="standby"),
            "bed_mesh": self.bed_mesh,
            "idex_manual_tuning": self.manual,
            "gcode_macro _IDEX_TOOL_STATE": self.tool_state,
            "dual_carriage": self.carriage,
            "gcode_move": self.gcode_move,
            "pins": FakePins(self),
            "homing": self.homing,
        }

    def lookup_object(self, name):
        return self.objects[name]

    def get_reactor(self):
        return FakeStatus(monotonic=lambda: 1.0)

    def register_event_handler(self, _name, _callback):
        pass


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer

    def get(self, name):
        assert name == "pin"
        return "^gpio4"

    def getfloat(self, _name, default, above=None):
        assert above is None or default > above
        return default


def test_contact_recovers_upward_clears_mesh_selects_once_and_uses_logical_t1():
    module = load_extra()
    printer = FakePrinter(mesh_active=True)
    probe = module.load_config(FakeConfig(printer))
    gcmd = FakeGcmd({"TOOL": 1, "COUNT": 2})

    probe.cmd_MULTI_HEAD_ZERO_CONTACT(gcmd)

    measurement = probe.get_status(0.0)["last_measurement"]
    assert printer.bed_mesh.active is False
    assert printer.toolhead.manual_moves[0][2] == pytest.approx(10.0)
    assert printer.gcode.scripts.count("T1\nM400") == 1
    assert (
        printer.gcode.scripts.count("G90\nG1 X75.000 Y-9.000 F1200\nG1 Z4.000 F1200")
        == 1
    )
    assert printer.homing.calls == [
        pytest.approx([75.0, -10.5, -0.4, 0.0]),
        pytest.approx([75.0, -10.5, -0.4, 0.0]),
    ]
    assert measurement["completed_count"] == 2
    assert measurement["machine_commanded_y"] == pytest.approx(-10.5)
    assert measurement["tap"]["mean"] == pytest.approx(1.65)
    assert any("upward recovery" in response for response in gcmd.responses)


def test_contact_refuses_downward_start_below_the_configured_minimum():
    module = load_extra()
    printer = FakePrinter(mesh_active=False)
    probe = module.load_config(FakeConfig(printer))

    with pytest.raises(RuntimeError, match="safe minimum"):
        probe.cmd_MULTI_HEAD_ZERO_CONTACT(FakeGcmd({"TOOL": 0, "START_Z": 3.9}))

    assert printer.gcode.scripts == []


def test_contact_aborts_after_upward_recovery_when_the_switch_stays_triggered():
    module = load_extra()
    printer = FakePrinter(mesh_active=False)
    printer.stuck_switch = True
    probe = module.load_config(FakeConfig(printer))

    with pytest.raises(RuntimeError, match="remains TRIGGERED after upward recovery"):
        probe.cmd_MULTI_HEAD_ZERO_CONTACT(FakeGcmd({"TOOL": 1}))

    assert printer.toolhead.manual_moves[0][2] == pytest.approx(10.0)
    assert not any(script.startswith("T1") for script in printer.gcode.scripts)
    assert not any("G1 X" in script for script in printer.gcode.scripts)


def test_contact_requires_homing_before_any_motion():
    module = load_extra()
    printer = FakePrinter(mesh_active=False)
    printer.toolhead.homed_axes = "xy"
    probe = module.load_config(FakeConfig(printer))

    with pytest.raises(RuntimeError, match="requires XYZ homing"):
        probe.cmd_MULTI_HEAD_ZERO_CONTACT(FakeGcmd({"TOOL": 0}))

    assert printer.toolhead.manual_moves == []
    assert printer.gcode.scripts == []
