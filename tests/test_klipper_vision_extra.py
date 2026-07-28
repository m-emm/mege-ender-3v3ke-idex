import errno
import importlib.util
import sys
from pathlib import Path

import pytest


VISION_EXTRA_PATH = (
    Path(__file__).resolve().parents[1]
    / "klipper_setup"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "vision.py"
)


def _load_vision_extra_module():
    spec = importlib.util.spec_from_file_location("klipper_vision_extra_test", VISION_EXTRA_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GcodeError(Exception):
    pass


class FakeGcode:
    def __init__(self):
        self.commands = {}

    def register_command(self, name, func, desc=None):
        self.commands[name] = func

    def error(self, message):
        return GcodeError(message)


class FakeReactor:
    def __init__(self, completion_response={"ok": True, "result": {}}):
        self.completion_response = completion_response

    def monotonic(self):
        return 100.0

    def completion(self):
        return FakeCompletion(self.completion_response)

    def register_fd(self, _fileno, _read_callback, _write_callback):
        return object()

    def unregister_fd(self, _fd_handle):
        return None

    def set_fd_wake(self, _fd_handle, _readable, _writable):
        return None


class FakeCompletion:
    def __init__(self, response):
        self.response = response
        self.completed = response is not None

    def test(self):
        return self.completed

    def complete(self, response):
        self.response = response
        self.completed = True

    def wait(self, _deadline, _default):
        return self.response


class FakeToolhead:
    def __init__(self):
        self.wait_count = 0
        self.last_move_time = 100.0
        self.dwells = []

    def wait_moves(self):
        self.wait_count += 1

    def get_last_move_time(self):
        return self.last_move_time

    def dwell(self, duration):
        self.dwells.append(duration)
        self.last_move_time += duration

    def get_position(self):
        return [195.0, -14.8, 20.0, 0.0]

    def get_status(self, _eventtime):
        return {"homed_axes": "xyz"}


class FakeGcodeMove:
    def get_status(self, _eventtime):
        return {"gcode_position": [195.0, -14.8, 20.0, 0.0]}


class FakePrinter:
    def __init__(self, reactor=None):
        self.gcode = FakeGcode()
        self.toolhead = FakeToolhead()
        self.reactor = reactor or FakeReactor()
        self.objects = {
            "gcode": self.gcode,
            "toolhead": self.toolhead,
            "gcode_move": FakeGcodeMove(),
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

    def getint(self, _name, default=None, **_constraints):
        return default

    def getboolean(self, _name, default=None):
        return default


class FakeGcmd:
    def __init__(self, params):
        self.params = params
        self.responses = []

    def get(self, name, default=None):
        return self.params.get(name, default)

    def get_int(self, name, default=None, minval=None):
        value = self.params.get(name, default)
        if value is None:
            raise AssertionError(f"missing int param {name}")
        value = int(value)
        if minval is not None and value < minval:
            raise AssertionError(f"{name} below minval")
        return value

    def get_float(self, name, default=None):
        value = self.params.get(name, default)
        if value is None:
            raise AssertionError(f"missing float param {name}")
        return float(value)

    def respond_info(self, message):
        self.responses.append(message)

    def error(self, message):
        return GcodeError(message)


class FakeStatusObject:
    def __init__(self, status):
        self.status = status

    def get_status(self, _eventtime):
        return self.status


class FakeProbe:
    def __init__(self, batch):
        self.batch = batch
        self.callback_result = None

    def add_client(self, callback):
        self.callback_result = callback(self.batch)


def test_vision_commands_register_and_wait_for_motion():
    module = _load_vision_extra_module()
    printer = FakePrinter()
    vision = module.Vision(FakeConfig(printer))
    requests = []

    def fake_request(action, params):
        requests.append((action, params))
        return {"ok": True}

    vision._request_visiond = fake_request

    assert {
        "VISION_JOB_BEGIN",
        "VISION_PROFILE",
        "VISION_CAPTURE_SYNC",
        "VISION_JOB_END",
        "VISION_EDDY_SAMPLE_SYNC",
        "VISION_MEASURE_BED_Y",
        "VISION_BED_Y_REFERENCE",
        "VISION_VALIDATE_BED_Y_REFERENCE",
        "VISION_MEASURE_BED_Y_RELATIVE",
    } <= set(printer.gcode.commands)

    printer.gcode.commands["VISION_JOB_BEGIN"](
        FakeGcmd(
            {
                "JOB": "job1",
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
                "JOB": "job1",
                "SEQ": "0",
                "FRAME": "t0_dx0",
                "CAMERA": "nozzle_cam",
                "PROFILE": "analysis",
                "TOOL": "T0",
            }
        )
    )
    printer.gcode.commands["VISION_JOB_END"](
        FakeGcmd({"JOB": "job1", "EXPECTED_FRAMES": "1"})
    )

    assert printer.toolhead.wait_count == 3
    assert [request[0] for request in requests] == [
        "job_begin",
        "profile",
        "capture",
        "job_end",
    ]
    capture_params = requests[2][1]
    assert capture_params["seq"] == 0
    assert capture_params["toolhead_position"] == [195.0, -14.8, 20.0, 0.0]
    assert capture_params["homed_axes"] == "xyz"


def test_eddy_sample_waits_for_bulk_batch_and_keeps_exact_sample_window():
    module = _load_vision_extra_module()
    printer = FakePrinter(reactor=FakeReactor(None))
    samples = [
        (100.0 + index / 400.0, 12_000_000.0 - index, 20.0)
        for index in range(201)
    ]
    probe = FakeProbe(
        {
            "data": samples,
            "errors": 0,
            "overflows": 0,
        }
    )
    printer.objects.update(
        {
            "probe": probe,
            "temperature_probe btt_eddy": FakeStatusObject(
                {"temperature": 36.5}
            ),
            "temperature_sensor btt_eddy_mcu": FakeStatusObject(
                {"temperature": 40.1}
            ),
        }
    )
    vision = module.Vision(FakeConfig(printer))
    requests = []

    def fake_request(action, params):
        requests.append((action, params))
        return {
            "ok": True,
            "result": {"median_frequency_hz": 11_999_900.0},
        }

    vision._request_visiond = fake_request
    gcmd = FakeGcmd(
        {
            "JOB": "job1",
            "SEQ": "3",
            "SAMPLE": "pass1_gap1p0",
            "MANIFEST_HASH": "sha256:m",
            "APPROACH": "descending",
            "COMMANDED_Z": "1.2",
            "NOZZLE_GAP": "1.0",
            "COIL_GAP": "3.5",
            "SETTLE_MS": "100",
            "DURATION_MS": "250",
        }
    )

    result = printer.gcode.commands["VISION_EDDY_SAMPLE_SYNC"](gcmd)

    assert result["median_frequency_hz"] == 11_999_900.0
    assert probe.callback_result is False
    assert printer.toolhead.dwells == [0.35]
    assert len(requests) == 1
    action, params = requests[0]
    assert action == "eddy_sample"
    assert params["sample_window"] == [100.1, 100.35]
    assert len(params["samples"]) == 101
    assert params["samples"][0][0] == pytest.approx(100.1)
    assert params["samples"][-1][0] == pytest.approx(100.35)
    assert params["errors"] == 0
    assert params["overflows"] == 0
    assert params["complete"] is True
    assert params["temperatures"]["coil"]["temperature"] == 36.5
    assert params["temperatures"]["mcu"]["temperature"] == 40.1


def test_visiond_error_response_raises_hard_command_error(monkeypatch):
    module = _load_vision_extra_module()
    printer = FakePrinter(reactor=FakeReactor({"ok": False, "error": "bad profile"}))
    vision = module.Vision(FakeConfig(printer))

    class FakeSocket:
        def setblocking(self, _enabled):
            return None

        def connect(self, _path):
            raise OSError(errno.EINPROGRESS, "in progress")

        def fileno(self):
            return 10

        def close(self):
            return None

    monkeypatch.setattr(module.socket, "socket", lambda *_args, **_kwargs: FakeSocket())

    with pytest.raises(GcodeError, match="bad profile"):
        vision._request_visiond("profile", {"camera": "nozzle_cam", "profile": "bad"})


def test_visiond_socket_timeout_raises_hard_command_error(monkeypatch):
    module = _load_vision_extra_module()
    printer = FakePrinter(reactor=FakeReactor(None))
    vision = module.Vision(FakeConfig(printer))

    class FakeSocket:
        def setblocking(self, _enabled):
            return None

        def connect(self, _path):
            return None

        def fileno(self):
            return 11

        def close(self):
            return None

    monkeypatch.setattr(module.socket, "socket", lambda *_args, **_kwargs: FakeSocket())

    with pytest.raises(GcodeError, match="timed out"):
        vision._request_visiond("capture", {"job": "job1"})
