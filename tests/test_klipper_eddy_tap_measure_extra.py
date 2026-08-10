import importlib.util
import re
import sys
from pathlib import Path

import pytest


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
        self.printer = None

    def register_command(self, name, callback, desc=None):
        self.commands[name] = callback

    def run_script_from_command(self, script):
        self.scripts.append(script)
        if self.printer is None:
            return
        for line in script.splitlines():
            if line.startswith("G1 "):
                for axis, value in re.findall(r"([XYZ])(-?[0-9.]+)", line):
                    axis_index = "XYZ".index(axis)
                    logical_value = float(value)
                    self.printer.gcode_move.gcode_position[axis_index] = logical_value
                    physical_value = logical_value
                    if axis == "Z" and self.printer.bed_mesh.active:
                        physical_value += self.printer.bed_mesh.transform_z
                    self.printer.toolhead.position[axis_index] = physical_value
            if line == "PROBE METHOD=scan SAMPLES=1":
                toolhead = self.printer.toolhead.position
                offsets = self.printer.probe.get_offsets()
                self.printer.probe.last_probe_position = [
                    toolhead[0] + offsets[0],
                    toolhead[1] + offsets[1],
                    0.0,
                ]

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

    def error(self, message):
        return RuntimeError(message)


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

    def dwell(self, _duration):
        self.printer.eddy_sensor.emit(
            [
                (1.0, 3_200_000.0, self.position[2]),
                (1.1, 3_200_020.0, self.position[2]),
                (1.2, 3_199_980.0, self.position[2]),
            ]
        )


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
            self.pending = [
                ProbeResult(
                    next(self.values),
                    bed_x=self.toolhead.position[0],
                    bed_y=self.toolhead.position[1],
                )
            ]
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
        self.last_probe_position = [0.0, 0.0, 0.0]

    def get_offsets(self):
        return (-57.391, -18.997, 1.399)

    def start_probe_session(self, gcmd):
        session = FakeProbeSession(self.toolhead, gcmd.get("METHOD", "probe"))
        self.sessions.append(session)
        return session

    def get_status(self, _eventtime):
        return {"last_probe_position": self.last_probe_position}


class FakeCalibration:
    def __init__(self, toolhead):
        self.toolhead = toolhead

    def freq_to_height(self, _frequency):
        return self.toolhead.get_position()[2]


class FakeEddySensor:
    def __init__(self, toolhead):
        self.calibration = FakeCalibration(toolhead)
        self.clients = []

    def add_client(self, callback):
        self.clients.append(callback)

    def emit(self, samples):
        message = {"data": samples}
        self.clients = [callback for callback in self.clients if callback(message)]


class FakeIDEXManualTuning:
    def __init__(self, active_tool=0):
        self.active_tool = active_tool

    def get_status(self, _eventtime):
        return {"active_tool": self.active_tool}


class FakeBedMesh:
    def __init__(self, active=False, transform_z=0.0):
        self.active = active
        self.transform_z = transform_z

    def get_status(self, _eventtime):
        return {
            "profile_name": "default" if self.active else "",
            "mesh_matrix": [[0.0]] if self.active else [[]],
        }


class FakeGcodeMove:
    def __init__(self):
        self.gcode_position = [0.0, 0.0, 5.0, 0.0]

    def get_status(self, _eventtime):
        return {"gcode_position": list(self.gcode_position)}


class FakeTemperatureProbe:
    def get_status(self, _eventtime):
        return {"temperature": 38.5}


class FakeReactor:
    def monotonic(self):
        return 1.0


class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode()
        self.toolhead = FakeToolhead()
        self.toolhead.printer = self
        self.probe = FakeProbe(self.toolhead)
        self.eddy_sensor = FakeEddySensor(self.toolhead)
        self.idex_manual_tuning = FakeIDEXManualTuning()
        self.bed_mesh = FakeBedMesh()
        self.gcode_move = FakeGcodeMove()
        self.temperature_probe = FakeTemperatureProbe()
        self.reactor = FakeReactor()
        self.gcode.printer = self
        self.objects = {
            "gcode": self.gcode,
            "toolhead": self.toolhead,
            "probe": self.probe,
            "probe_eddy_current btt_eddy": self.eddy_sensor,
            "idex_manual_tuning": self.idex_manual_tuning,
            "bed_mesh": self.bed_mesh,
            "gcode_move": self.gcode_move,
            "temperature_probe btt_eddy": self.temperature_probe,
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

    def get(self, name, default=None):
        return self.values.get(name, default)

    def getsection(self, name):
        assert name == "probe_eddy_current btt_eddy"
        return FakeProbeConfig()


def test_eddy_tap_measure_reports_contact_statistics_and_threshold_override():
    module = _load()
    printer = FakePrinter()
    measure = module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 123.456, "Y": 234.567, "THRESHOLD": 5100, "COUNT": 3})
    printer.gcode.commands["_EDDY_TAP_MEASURE"](gcmd)

    assert printer.gcode.scripts == [
        "G90\nG1 Z5.000 F1200\nG1 X123.456 Y234.567 F1200",
        "G90\nG1 Z5.000 F1200\nG1 X180.847 Y253.564 F1200",
        "G90\nG1 Z5.000 F1200",
    ]
    assert "threshold=5100.000" in gcmd.responses[0]
    assert "reference=(123.456, 234.567)" in gcmd.responses[0]
    assert "contact=(123.456, 234.567, -0.012000)" in gcmd.responses[1]
    assert "post_retract_z=3.990000" in gcmd.responses[1]
    assert any("mean=-0.010000 median=-0.010000" in response for response in gcmd.responses)
    assert any("span=0.004000" in response for response in gcmd.responses)
    assert any(
        "EDDY_TAP_MEASURE mesh: inactive; commanded_z_for_tap_median=unavailable"
        in response
        for response in gcmd.responses
    )
    assert "tap_median=-0.010000 eddy_probe=-0.004000" in gcmd.responses[-1]
    assert "delta_probe_minus_tap=0.006000" in gcmd.responses[-1]
    measurement = measure.get_status(0.0)["last_tap_measurement"]
    assert measurement["mesh"] == {
        "active_transform_z": None,
        "commanded_z_for_tap_median": None,
    }
    assert all(session.ended for session in printer.probe.sessions)


def test_eddy_tap_measure_maps_tap_z_through_active_mesh_transform():
    module = _load()
    printer = FakePrinter()
    printer.bed_mesh.active = True
    printer.bed_mesh.transform_z = 0.037
    measure = module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 123.456, "Y": 234.567, "COUNT": 1})
    printer.gcode.commands["_EDDY_TAP_MEASURE"](gcmd)

    assert any(
        "active_transform_z=0.037000 tap_median_z=-0.012000 "
        "commanded_z_for_tap_median=-0.049000" in response
        for response in gcmd.responses
    )
    measurement = measure.get_status(0.0)["last_tap_measurement"]
    assert measurement["mesh"] == {
        "active_transform_z": pytest.approx(0.037),
        "commanded_z_for_tap_median": pytest.approx(-0.049),
    }


def test_eddy_tap_measure_scan_mode_reports_same_point_structured_evidence():
    module = _load()
    printer = FakePrinter()
    measure = module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd(
        {
            "X": 150.0,
            "Y": 150.0,
            "COUNT": 1,
            "EDDY_MODE": "scan",
            "SCAN_COUNT": 3,
            "SCAN_HEIGHT": 2.0,
            "DURATION": 0.2,
            "XY_SPEED": 100.0,
        }
    )
    printer.gcode.commands["_EDDY_TAP_MEASURE"](gcmd)

    assert printer.gcode.scripts[:4] == [
        "G90\nG1 Z5.000 F1200\nG1 X150.000 Y150.000 F6000",
        "G90\nG1 Z5.000 F1200\nG1 X207.391 Y168.997 F6000",
        "G90\nG1 Z1.888 F1200",
        "G90\nG1 Z1.988 F1200",
    ]
    assert printer.gcode.scripts.count("PROBE METHOD=scan SAMPLES=1") == 3
    assert printer.gcode.scripts[-1] == "G90\nG1 Z5.000 F1200"
    measurement = measure.get_status(0.0)["last_tap_measurement"]
    assert measurement["eddy_mode"] == "scan"
    assert measurement["tap"]["count"] == 1
    assert measurement["tap"]["samples"][0] == {
        "x": pytest.approx(150.0),
        "y": pytest.approx(150.0),
        "z": pytest.approx(-0.012),
    }
    assert measurement["tap_coordinate_deltas"] == [{"x": 0.0, "y": 0.0}]
    assert measurement["coil_nozzle_x"] == pytest.approx(207.391)
    assert measurement["stationary_scan"]["count"] == 3
    assert measurement["scan_coordinate_deltas"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 0.0, "y": 0.0},
        {"x": 0.0, "y": 0.0},
    ]
    assert measurement["stationary_scan"]["scan_bed_z_median"] == pytest.approx(0.0)
    assert measurement["delta_scan_minus_tap"] == pytest.approx(0.012)
    assert any("target=(150.000, 150.000)" in response for response in gcmd.responses)


def test_eddy_tap_measure_warns_and_keeps_tap_results_when_coil_is_unreachable():
    module = _load()
    printer = FakePrinter()
    module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 300.0, "Y": 150.0, "COUNT": 1})
    printer.gcode.commands["_EDDY_TAP_MEASURE"](gcmd)

    assert any(
        "warning: Eddy coil target is unreachable" in response
        for response in gcmd.responses
    )
    assert len(printer.probe.sessions) == 1
    assert printer.gcode.scripts == ["G90\nG1 Z5.000 F1200\nG1 X300.000 Y150.000 F1200"]


def test_eddy_raw_measure_reports_native_frequency_and_builtin_height():
    module = _load()
    printer = FakePrinter()
    measure = module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 150.0, "Y": 150.0, "Z": 1.0, "DURATION": 0.2})
    printer.gcode.commands["_EDDY_RAW_MEASURE"](gcmd)

    assert printer.gcode.scripts == [
        "G90\nG1 Z5.000 F1200\nG1 X207.391 Y168.997 F1200",
        "G90\nG1 Z1.000 F1200",
        "G90\nG1 Z5.000 F1200",
    ]
    assert "raw_frequency_hz=3200000.000" in gcmd.responses[-1]
    assert "built_in_sensor_height=1.000000" in gcmd.responses[-1]
    assert "implied_bed_z=0.000000" in gcmd.responses[-1]
    assert "temperature=38.500" in gcmd.responses[-1]
    raw_status = measure.get_status(0.0)["last_raw_measurement"]
    assert raw_status["bed_x"] == pytest.approx(150.0)
    assert raw_status["nozzle_x"] == pytest.approx(207.391)
    assert raw_status["requested_nozzle_z"] == pytest.approx(1.0)
    assert raw_status["raw_frequency_hz"] == pytest.approx(3_200_000.0)
    assert raw_status["toolhead_position"][:3] == pytest.approx([207.391, 168.997, 1.0])


def test_eddy_raw_measure_can_collect_an_upward_sweep_without_intermediate_lifts():
    module = _load()
    printer = FakePrinter()
    module.load_config(FakeConfig(printer))

    first = FakeGcmd(
        {
            "X": 150.0,
            "Y": 150.0,
            "Z": 0.5,
            "SAFE_TRAVEL": 1,
            "LIFT_AFTER": 0,
            "APPROACH_Z": 0.1,
        }
    )
    printer.gcode.commands["_EDDY_RAW_MEASURE"](first)
    second = FakeGcmd(
        {
            "X": 150.0,
            "Y": 150.0,
            "Z": 1.0,
            "SAFE_TRAVEL": 0,
            "LIFT_AFTER": 0,
        }
    )
    printer.gcode.commands["_EDDY_RAW_MEASURE"](second)

    assert printer.gcode.scripts == [
        "G90\nG1 Z5.000 F1200\nG1 X207.391 Y168.997 F1200",
        "G90\nG1 Z0.100 F1200",
        "G90\nG1 Z0.500 F1200",
        "G90\nG1 Z1.000 F1200",
    ]


def test_stationary_scan_measure_repeats_at_one_upward_approached_height():
    module = _load()
    printer = FakePrinter()
    measure = module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 150.0, "Y": 150.0, "Z": 2.0, "COUNT": 3, "DURATION": 0.2})
    printer.gcode.commands["_EDDY_STATIONARY_SCAN_MEASURE"](gcmd)

    assert printer.gcode.scripts[:6] == [
        "G90\nG1 Z5.000 F1200\nG1 X207.391 Y168.997 F1200",
        "G90\nG1 Z1.900 F1200",
        "G90\nG1 Z2.000 F1200",
        "PROBE METHOD=scan SAMPLES=1",
        "PROBE METHOD=scan SAMPLES=1",
        "PROBE METHOD=scan SAMPLES=1",
    ]
    assert printer.gcode.scripts[-1] == "G90\nG1 Z5.000 F1200"
    measurement = measure.get_status(0.0)["last_stationary_scan_measurement"]
    assert measurement["count"] == 3
    assert measurement["scan_bed_z_median"] == pytest.approx(0.0)
    assert measurement["scan_bed_z_span"] == pytest.approx(0.0)
    assert len(measurement["results"]) == 3
    assert (
        sum(
            response.startswith("EDDY_STATIONARY_SCAN_MEASURE sample")
            for response in gcmd.responses
        )
        == 3
    )


def test_eddy_scan_height_test_reports_invariant_scan_results():
    module = _load()
    printer = FakePrinter()
    measure = module.load_config(FakeConfig(printer))

    gcmd = FakeGcmd({"X": 150.0, "Y": 150.0, "NOZZLE_ZS": "0.5,1,2,3"})
    printer.gcode.commands["_EDDY_SCAN_HEIGHT_TEST"](gcmd)

    scan_scripts = [
        script
        for script in printer.gcode.scripts
        if script == "PROBE METHOD=scan SAMPLES=1"
    ]
    assert len(scan_scripts) == 4
    point_reports = [
        response
        for response in gcmd.responses
        if response.startswith("EDDY_SCAN_HEIGHT_TEST point:")
    ]
    assert len(point_reports) == 4
    assert all(
        "scan_probe=(150.000, 150.000, 0.000000)" in report for report in point_reports
    )
    assert "scan_bed_z_span=0.000000" in gcmd.responses[-1]
    assert printer.gcode.scripts[:6] == [
        "G90\nG1 Z5.000 F1200\nG1 X207.391 Y168.997 F1200",
        "G90\nG1 Z0.400 F1200",
        "G90\nG1 Z0.500 F1200",
        "PROBE METHOD=scan SAMPLES=1",
        "G90\nG1 Z1.000 F1200",
        "PROBE METHOD=scan SAMPLES=1",
    ]
    assert printer.gcode.scripts.count("G90\nG1 Z5.000 F1200") == 1
    assert printer.gcode.scripts[-1] == "G90\nG1 Z5.000 F1200"
    scan_status = measure.get_status(0.0)["last_scan_height_test"]
    assert scan_status["requested_nozzle_zs"] == [0.5, 1.0, 2.0, 3.0]
    assert scan_status["scan_bed_z_span"] == pytest.approx(0.0)
    assert len(scan_status["results"]) == 4


def test_eddy_scan_diagnostics_require_t0_and_a_cleared_mesh():
    module = _load()
    printer = FakePrinter()
    module.load_config(FakeConfig(printer))

    printer.idex_manual_tuning.active_tool = 1
    with pytest.raises(RuntimeError, match="requires T0"):
        printer.gcode.commands["_EDDY_RAW_MEASURE"](FakeGcmd())

    printer.idex_manual_tuning.active_tool = 0
    printer.bed_mesh.active = True
    with pytest.raises(RuntimeError, match="BED_MESH_CLEAR"):
        printer.gcode.commands["_EDDY_SCAN_HEIGHT_TEST"](FakeGcmd())


def test_eddy_scan_height_test_rejects_invalid_heights_and_unreachable_targets():
    module = _load()
    printer = FakePrinter()
    module.load_config(FakeConfig(printer))

    with pytest.raises(RuntimeError, match="NOZZLE_ZS"):
        printer.gcode.commands["_EDDY_SCAN_HEIGHT_TEST"](
            FakeGcmd({"NOZZLE_ZS": "3,not-a-number"})
        )
    with pytest.raises(RuntimeError, match="strictly ascending"):
        printer.gcode.commands["_EDDY_SCAN_HEIGHT_TEST"](
            FakeGcmd({"NOZZLE_ZS": "3,2,1"})
        )
    with pytest.raises(RuntimeError, match="unreachable"):
        printer.gcode.commands["_EDDY_RAW_MEASURE"](FakeGcmd({"X": 300.0}))


def test_eddy_tap_measure_is_deployed_and_generated_macro_is_present():
    assert EXTRA_PATH.read_text(encoding="utf-8") == IMAGE_EXTRA_PATH.read_text(
        encoding="utf-8"
    )
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    assert "[eddy_tap_measure]" in config_text
    assert "[gcode_macro EDDY_TAP_MEASURE]" in config_text
    assert (
        "_EDDY_TAP_MEASURE X={x} Y={y} THRESHOLD={threshold} COUNT={count} "
        "EDDY_MODE={eddy_mode}" in config_text
    )
    assert "[gcode_macro EDDY_RAW_MEASURE]" in config_text
    assert (
        "_EDDY_RAW_MEASURE X={x} Y={y} Z={z} DURATION={duration} "
        "SAFE_TRAVEL={safe_travel} LIFT_AFTER={lift_after}" in config_text
    )
    assert "[gcode_macro EDDY_SCAN_HEIGHT_TEST]" in config_text
    assert (
        "_EDDY_SCAN_HEIGHT_TEST X={x} Y={y} NOZZLE_ZS={nozzle_zs} "
        "DURATION={duration}" in config_text
    )
    assert "[gcode_macro EDDY_STATIONARY_SCAN_MEASURE]" in config_text
    assert (
        "_EDDY_STATIONARY_SCAN_MEASURE X={x} Y={y} Z={z} COUNT={count} "
        "DURATION={duration} XY_SPEED={xy_speed}" in config_text
    )
    updater = UPDATER_PATH.read_text(encoding="utf-8")
    assert "SOURCE_EDDY_TAP_MEASURE" in updater
    assert "EXPECTED_EDDY_TAP_MEASURE_SHA256" in updater
