import importlib.util
import sys
from pathlib import Path


VISION_EXTRA = (
    Path(__file__).resolve().parents[1]
    / "klipper_setup"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "vision.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("vision_extra_clean_test", VISION_EXTRA)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeGcode:
    def __init__(self):
        self.commands = {}

    def register_command(self, name, callback, desc=None):
        self.commands[name] = callback

    def error(self, message):
        return RuntimeError(message)


class FakeToolhead:
    def __init__(self):
        self.waits = 0

    def wait_moves(self):
        self.waits += 1

    def get_position(self):
        return [10.0, -5.0, 300.0, 0.0]

    def get_status(self, _eventtime):
        return {"homed_axes": "xyz"}


class FakeStatus:
    def __init__(self, value):
        self.value = value

    def get_status(self, _eventtime):
        return self.value


class FakeReactor:
    def monotonic(self):
        return 1.0


class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode()
        self.toolhead = FakeToolhead()
        self.reactor = FakeReactor()
        self.objects = {
            "gcode": self.gcode,
            "toolhead": self.toolhead,
            "gcode_move": FakeStatus(
                {"gcode_position": [10.0, -5.0, 300.0, 0.0]}
            ),
            "extruder": FakeStatus({"temperature": 23.0, "target": 0.0}),
            "extruder1": FakeStatus({"temperature": 23.5, "target": 0.0}),
            "heater_bed": FakeStatus({"temperature": 22.0, "target": 0.0}),
        }

    def get_reactor(self):
        return self.reactor

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer

    def get(self, _name, default=None):
        return default

    def getfloat(self, _name, default=None, **_constraints):
        return default


class FakeGcmd:
    def __init__(self, values):
        self.values = values

    def get(self, name, default=None):
        return self.values.get(name, default)

    def get_int(self, name, default=None, minval=None):
        value = int(self.values.get(name, default))
        assert minval is None or value >= minval
        return value


def test_only_clean_synchronized_commands_are_registered():
    module = _load()
    printer = FakePrinter()
    vision = module.Vision(FakeConfig(printer))
    assert set(printer.gcode.commands) == {
        "VISION_JOB_BEGIN",
        "VISION_PROFILE",
        "VISION_CAPTURE_SYNC",
        "VISION_JOB_END",
    }
    assert vision.get_status(0.0) == {}


def test_capture_records_positions_temperatures_and_waits_for_motion():
    module = _load()
    printer = FakePrinter()
    vision = module.Vision(FakeConfig(printer))
    requests = []
    vision._request_visiond = lambda action, params: requests.append(
        (action, params)
    ) or {"ok": True}

    printer.gcode.commands["VISION_JOB_BEGIN"](
        FakeGcmd(
            {
                "JOB": "job",
                "MANIFEST_HASH": "sha256:m",
                "GCODE_HASH": "sha256:g",
            }
        )
    )
    printer.gcode.commands["VISION_PROFILE"](
        FakeGcmd({"CAMERA": "nozzle_cam", "PROFILE": "analysis"})
    )
    printer.gcode.commands["VISION_CAPTURE_SYNC"](
        FakeGcmd(
            {
                "JOB": "job",
                "SEQ": 0,
                "FRAME": "y_00_00mm",
                "CAMERA": "nozzle_cam",
                "PROFILE": "analysis",
                "TOOL": "T0",
            }
        )
    )
    printer.gcode.commands["VISION_JOB_END"](
        FakeGcmd({"JOB": "job", "EXPECTED_FRAMES": 9})
    )

    assert [action for action, _params in requests] == [
        "job_begin",
        "profile",
        "capture",
        "job_end",
    ]
    assert printer.toolhead.waits == 3
    capture = requests[2][1]
    assert capture["toolhead_position"] == [10.0, -5.0, 300.0, 0.0]
    assert capture["gcode_position"] == [10.0, -5.0, 300.0, 0.0]
    assert capture["homed_axes"] == "xyz"
    assert capture["temperatures"]["heater_bed"]["temperature"] == 22.0
