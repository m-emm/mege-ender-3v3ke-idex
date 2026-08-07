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
    / "eddy_tap_measure.py"
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
    / "eddy_tap_measure.py"
)
CONFIG_PATH = REPO_ROOT / "klipper_setup" / "klipper_config" / "printer.cfg"
UPDATER_PATH = REPO_ROOT / "klipper_setup" / "klipper_config" / "update_menderpi.sh"


def _load():
    spec = importlib.util.spec_from_file_location("eddy_tap_measure_test", EXTRA_PATH)
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

    def create_gcode_command(self, _name, _raw_command, params):
        return FakeGcmd(params)

    def error(self, message):
        return RuntimeError(message)


class FakeGcmd:
    def __init__(self, values=None):
        self.values = values or {}
        self.responses = []

    def get_command_parameters(self):
        return self.values

    def get(self, name, default=None):
        return self.values.get(name, default)

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


class FakeToolhead:
    def __init__(self):
        self.position = [0.0, 0.0, 5.0, 0.0]

    def get_status(self, _eventtime):
        return {
            "homed_axes": "xyz",
            "axis_minimum": {"x": 0.0, "y": 0.0, "z": 0.0},
            "axis_maximum": {"x": 255.0, "y": 296.0, "z": 300.0},
        }

    def get_position(self):
        return list(self.position)

    def wait_moves(self):
        pass


class ProbeResult:
    def __init__(self, bed_z, bed_x=123.456, bed_y=234.567):
        self.bed_x = bed_x
        self.bed_y = bed_y
        self.bed_z = bed_z


class FakeProbeSession:
    def __init__(self, toolhead, method):
        self.toolhead = toolhead
        self.method = method
        self.values = iter([-0.012, -0.008, -0.010])
        self.pending = []
        self.ended = False

    def run_probe(self, _gcmd):
        self.toolhead.position[2] = 3.99
        if self.method == "tap":
            self.pending = [ProbeResult(next(self.values))]
        else:
            self.pending = [ProbeResult(-0.004)]

    def pull_probed_results(self):
        pending, self.pending = self.pending, []
        return pending

    def end_probe_session(self):
        self.ended = True


class FakeProbe:
    def __init__(self, toolhead):
        self.toolhead = toolhead
        self.sessions = []

    def get_offsets(self):
        return (-57.391, -18.997, 1.399)

    def start_probe_session(self, gcmd):
        session = FakeProbeSession(self.toolhead, gcmd.get("METHOD", "probe"))
        self.sessions.append(session)
        return session


class FakeReactor:
    def monotonic(self):
        return 1.0


class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode()
        self.toolhead = FakeToolhead()
        self.probe = FakeProbe(self.toolhead)
        self.reactor = FakeReactor()
        self.objects = {
            "gcode": self.gcode,
            "toolhead": self.toolhead,
            "probe": self.probe,
        }

    def lookup_object(self, name):
        return self.objects[name]

    def get_reactor(self):
        return self.reactor


class FakeProbeConfig:
    def getfloat(self, name, default=None, minval=None):
        assert name == "tap_threshold"
        assert minval == 0.0
        return 5000.0


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer
        self.values = {
            "reference_x": 150.0,
            "reference_y": 150.0,
            "move_z": 5.0,
            "move_speed": 20.0,
        }

    def get_printer(self):
        return self.printer

    def getfloat(self, name, default=None, above=None):
        value = float(self.values.get(name, default))
        assert above is None or value > above
        return value

    def getint(self, name, default=None, minval=None):
        value = int(self.values.get(name, default))
        assert minval is None or value >= minval
        return value

    def getsection(self, name):
        assert name == "probe_eddy_current btt_eddy"
        return FakeProbeConfig()


def test_eddy_tap_measure_reports_contact_statistics_and_threshold_override():
    module = _load()
    printer = FakePrinter()
    module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 123.456, "Y": 234.567, "THRESHOLD": 5100, "COUNT": 3})
    printer.gcode.commands["_EDDY_TAP_MEASURE"](gcmd)

    assert printer.gcode.scripts == [
        "G90\nG1 X123.456 Y234.567 Z5.000 F1200",
        "G90\nG1 Z5.000 F1200\nG1 X180.847 Y253.564 F1200",
        "G90\nG1 Z5.000 F1200",
    ]
    assert "threshold=5100.000" in gcmd.responses[0]
    assert "reference=(123.456, 234.567)" in gcmd.responses[0]
    assert "contact_z=-0.012000" in gcmd.responses[1]
    assert "post_retract_z=3.990000" in gcmd.responses[1]
    assert "mean=-0.010000 median=-0.010000" in gcmd.responses[-2]
    assert "span=0.004000" in gcmd.responses[-2]
    assert "tap_median=-0.010000 eddy_probe=-0.004000" in gcmd.responses[-1]
    assert "delta_probe_minus_tap=0.006000" in gcmd.responses[-1]
    assert all(session.ended for session in printer.probe.sessions)


def test_eddy_tap_measure_warns_and_keeps_tap_results_when_coil_is_unreachable():
    module = _load()
    printer = FakePrinter()
    module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 300.0, "Y": 150.0, "COUNT": 1})
    printer.gcode.commands["_EDDY_TAP_MEASURE"](gcmd)

    assert any("warning: Eddy coil target is unreachable" in response for response in gcmd.responses)
    assert len(printer.probe.sessions) == 1
    assert printer.gcode.scripts == ["G90\nG1 X300.000 Y150.000 Z5.000 F1200"]


def test_eddy_tap_measure_is_deployed_and_generated_macro_is_present():
    assert EXTRA_PATH.read_text(encoding="utf-8") == IMAGE_EXTRA_PATH.read_text(
        encoding="utf-8"
    )
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    assert "[eddy_tap_measure]" in config_text
    assert "[gcode_macro EDDY_TAP_MEASURE]" in config_text
    assert "_EDDY_TAP_MEASURE X={x} Y={y} THRESHOLD={threshold} COUNT={count}" in config_text
    updater = UPDATER_PATH.read_text(encoding="utf-8")
    assert "SOURCE_EDDY_TAP_MEASURE" in updater
    assert "EXPECTED_EDDY_TAP_MEASURE_SHA256" in updater
