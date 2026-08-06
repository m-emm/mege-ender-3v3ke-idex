import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRA_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "idex_manual_tuning.py"
)
IMAGE_EXTRA_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "idex_manual_tuning.py"
)
IMAGE_INSTALL_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "01-run-chroot.sh"
)
UPDATER_PATH = REPO_ROOT / "klipper_setup" / "klipper_config" / "update_menderpi.sh"


def _load():
    spec = importlib.util.spec_from_file_location("idex_manual_tuning_test", EXTRA_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeGcode:
    def __init__(self):
        self.commands = {}
        self.scripts = []

    def register_command(self, name, callback, desc=None):
        self.commands[name] = callback

    def run_script_from_command(self, script):
        self.scripts.append(script)


class FakeReactor:
    def monotonic(self):
        return 1.0


class FakeGcodeMove:
    def __init__(self):
        self.status = {
            "homing_origin": [0.0, 0.0, 0.0, 0.0],
            "speed_factor": 100.0,
            "extrude_factor": 1.0,
        }

    def get_status(self, _eventtime):
        return self.status


class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode()
        self.reactor = FakeReactor()
        self.gcode_move = FakeGcodeMove()
        self.objects = {"gcode": self.gcode, "gcode_move": self.gcode_move}
        self.event_handlers = {}

    def lookup_object(self, name):
        return self.objects[name]

    def get_reactor(self):
        return self.reactor

    def register_event_handler(self, name, callback):
        self.event_handlers[name] = callback


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer


class FakeGcmd:
    def __init__(self, values=None):
        self.values = values or {}
        self.responses = []

    def get_int(self, name, default=None, minval=None, maxval=None):
        value = int(self.values.get(name, default))
        assert minval is None or value >= minval
        assert maxval is None or value <= maxval
        return value

    def get_float(self, name, default=None, above=None):
        value = float(self.values.get(name, default))
        assert above is None or value > above
        return value

    def respond_info(self, message):
        self.responses.append(message)


def test_manual_tuning_survives_tool_change_and_restores_flow_after_activation():
    module = _load()
    printer = FakePrinter()
    tuning = module.IDEXManualTuning(FakeConfig(printer))

    assert set(printer.gcode.commands) == {
        "IDEX_MANUAL_TUNING_CAPTURE",
        "IDEX_MANUAL_TUNING_APPLY",
        "IDEX_MANUAL_TUNING_STATUS",
        "IDEX_MANUAL_TUNING_RESET",
    }
    assert "virtual_sdcard:reset_file" in printer.event_handlers

    printer.gcode_move.status = {
        "homing_origin": [0.0, 0.0, 0.060, 0.0],
        "speed_factor": 0.80,
        "extrude_factor": 0.93,
    }
    printer.gcode.commands["IDEX_MANUAL_TUNING_CAPTURE"](FakeGcmd({"TOOL": 0}))

    # Klipper resets M221 during ACTIVATE_EXTRUDER; capture must precede it.
    printer.gcode_move.status["extrude_factor"] = 1.0
    printer.gcode.commands["IDEX_MANUAL_TUNING_APPLY"](
        FakeGcmd(
            {"TOOL": 1, "TOOL_Z": 1.274, "Y": 1.185, "MOVE": 1, "MOVE_SPEED": 5}
        )
    )

    assert printer.gcode.scripts == [
        "SET_GCODE_OFFSET X=0 Y=1.185000 Z=1.334000 MOVE=1 MOVE_SPEED=5.000000",
        "M220 S80.000000",
        "M221 S93.000000",
    ]
    assert tuning.get_status(0.0) == {
        "active_tool": 1,
        "active_tool_z_offset": 1.274,
        "manual_z_adjust": 0.06,
        "effective_z_offset": 1.334,
        "speed_factor": 80.0,
        "flow_factor": 93.0,
    }


def test_status_resynchronizes_babystep_and_reset_event_returns_to_neutral():
    module = _load()
    printer = FakePrinter()
    tuning = module.IDEXManualTuning(FakeConfig(printer))
    tuning.active_tool = 1
    tuning.active_tool_z_offset = 1.274
    printer.gcode_move.status = {
        "homing_origin": [0.0, 0.0, 1.354, 0.0],
        "speed_factor": 0.72,
        "extrude_factor": 0.91,
    }

    status_gcmd = FakeGcmd()
    printer.gcode.commands["IDEX_MANUAL_TUNING_STATUS"](status_gcmd)
    assert "manual_z=0.0800" in status_gcmd.responses[0]
    assert "speed=72.0% flow=91.0%" in status_gcmd.responses[0]

    printer.event_handlers["virtual_sdcard:reset_file"]()
    assert tuning.get_status(0.0)["manual_z_adjust"] == 0.0
    assert tuning.get_status(0.0)["speed_factor"] == 100.0
    assert tuning.get_status(0.0)["flow_factor"] == 100.0
    assert printer.gcode.scripts[-3:] == [
        "SET_GCODE_OFFSET Z=1.274000 MOVE=0",
        "M220 S100",
        "M221 S100",
    ]


def test_extra_is_packaged_and_deployed_with_the_managed_klipper_extras():
    assert EXTRA_PATH.read_text(encoding="utf-8") == IMAGE_EXTRA_PATH.read_text(
        encoding="utf-8"
    )
    image_install = IMAGE_INSTALL_PATH.read_text(encoding="utf-8")
    updater = UPDATER_PATH.read_text(encoding="utf-8")

    assert "idex_manual_tuning.py" in image_install
    assert "SOURCE_IDEX_MANUAL_TUNING" in updater
    assert "REMOTE_TMP_IDEX_MANUAL_TUNING" in updater
    assert "EXPECTED_IDEX_MANUAL_TUNING_SHA256" in updater
