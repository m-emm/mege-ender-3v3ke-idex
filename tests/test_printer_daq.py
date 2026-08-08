import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "klipper_setup" / "klipper_config"
EXTRAS_DIR = REPO_ROOT / "klipper_setup" / "klipper_host" / "klippy" / "extras"
IMAGE_EXTRAS_DIR = (
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
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_host_module(name):
    sys.path.insert(0, str(CONFIG_DIR))
    try:
        return _load(CONFIG_DIR / (name + ".py"), "printer_daq_" + name)
    finally:
        sys.path.pop(0)


class FakeSqliteDict(dict):
    def __init__(self, *_args, **_kwargs):
        super().__init__()

    def close(self):
        pass


class FakeGcmd:
    def __init__(self, values):
        self.values = values
        self.responses = []

    def get(self, name, default=None):
        return self.values.get(name, default)

    def get_int(self, name, default=None, minval=None, maxval=None):
        value = int(self.values.get(name, default))
        assert minval is None or value >= minval
        assert maxval is None or value <= maxval
        return value

    def get_float(self, name, default=None, above=None):
        value = float(self.values.get(name, default))
        assert above is None or value > above
        return value

    def get_command_parameters(self):
        return dict(self.values)

    def respond_info(self, value):
        self.responses.append(value)

    def error(self, value):
        return RuntimeError(value)


class FakeGcode:
    def __init__(self):
        self.commands = {}

    def register_command(self, name, callback, desc=None):
        self.commands[name] = callback

    def create_gcode_command(self, _name, _raw, values):
        return FakeGcmd(values)

    def error(self, value):
        return RuntimeError(value)


class FakeReactor:
    def monotonic(self):
        return 1.0


class FakeToolhead:
    def __init__(self):
        self.position = [5.0, 20.0, 0.5, 0.0]

    def get_position(self):
        return list(self.position)


class FakeProbeSession:
    def run_probe(self, _gcmd):
        pass

    def pull_probed_results(self):
        return [type("Contact", (), {"bed_x": 5.0, "bed_y": 20.0, "bed_z": -0.01})()]

    def end_probe_session(self):
        pass


class FakeProbe:
    def get_offsets(self):
        return (-57.391, -18.997, 1.399)

    def start_probe_session(self, _gcmd):
        return FakeProbeSession()


class FakeEddyHelper:
    def _require_scan_ready(self, _command):
        return self.toolhead

    def _capture_raw_measurement(self, toolhead, _duration):
        return {
            "raw_frequency_hz": 3_200_000.0,
            "raw_frequency_span_hz": 12.0,
            "sample_count": 20,
            "built_in_sensor_height": toolhead.position[2],
            "stream_height": toolhead.position[2],
            "implied_bed_z": 0.0,
            "temperature": 39.0,
        }

    def _temperature(self):
        return 39.0


class FakeProbeConfig:
    def getfloat(self, name, minval=None):
        assert name == "tap_threshold"
        assert minval == 0.0
        return 7500.0


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer

    def get(self, _name, default=None):
        if _name == "database_path":
            return "/tmp/test-daq.sqlite"
        return default

    def getsection(self, name):
        assert name == "probe_eddy_current btt_eddy"
        return FakeProbeConfig()


class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode()
        self.toolhead = FakeToolhead()
        helper = FakeEddyHelper()
        helper.toolhead = self.toolhead
        self.objects = {
            "gcode": self.gcode,
            "toolhead": self.toolhead,
            "probe": FakeProbe(),
            "eddy_tap_measure": helper,
        }

    def lookup_object(self, name):
        return self.objects[name]

    def get_reactor(self):
        return FakeReactor()

    def register_event_handler(self, _event, _callback):
        pass


def test_generic_daq_store_uses_flat_deterministic_keys():
    module = _load(EXTRAS_DIR / "daq.py", "printer_daq_extra")
    module.SqliteDict = FakeSqliteDict
    store = module.DaqStore("/tmp/test-daq.sqlite")
    store.start_job("grid_1", "eddy_grid")
    record = store.write_record("grid_1", 7, {"record_type": "eddy_native"})
    job = store.finish_job("grid_1")

    assert module.DaqStore.record_key("grid_1", 7) == "grid_1_000007"
    assert record["job_id"] == "grid_1"
    assert record["record_kind"] == "measurement"
    assert job["status"] == "completed"
    with pytest.raises(ValueError, match="already exists"):
        store.start_job("grid_1")


def test_eddy_daq_persists_same_point_tap_and_native_sample():
    daq_module = _load(EXTRAS_DIR / "daq.py", "printer_daq_generic")
    daq_module.SqliteDict = FakeSqliteDict
    eddy_module = _load(EXTRAS_DIR / "eddy_daq.py", "printer_daq_eddy")
    printer = FakePrinter()
    daq = daq_module.load_config(FakeConfig(printer))
    printer.objects["daq"] = daq
    eddy_module.load_config(FakeConfig(printer))

    printer.gcode.commands["DAQ_JOB_START"](
        FakeGcmd({"JOB_ID": "grid_1", "JOB_TYPE": "eddy_grid", "EXPECTED_RECORDS": 2})
    )
    printer.gcode.commands["DAQ_EDDY_TAP"](
        FakeGcmd({"JOB_ID": "grid_1", "RECORD_INDEX": 0, "POINT_INDEX": 0, "TAP_INDEX": 0, "X": 5.0, "Y": 20.0})
    )
    printer.toolhead.position[:2] = [62.391, 38.997]
    printer.gcode.commands["DAQ_EDDY_SAMPLE"](
        FakeGcmd({"JOB_ID": "grid_1", "RECORD_INDEX": 1, "POINT_INDEX": 0, "HEIGHT_INDEX": 0, "X": 5.0, "Y": 20.0, "Z": 0.5, "DURATION": 0.5})
    )
    printer.gcode.commands["DAQ_JOB_FINISH"](FakeGcmd({"JOB_ID": "grid_1"}))

    assert daq.store.db["grid_1"]["record_count"] == 2
    assert daq.store.db["grid_1_000000"]["tap_contact_z"] == pytest.approx(-0.01)
    assert daq.store.db["grid_1_000001"]["raw_frequency_hz"] == pytest.approx(3_200_000.0)
    assert daq.store.db["grid_1"]["status"] == "completed"


def test_eddy_grid_uses_common_reachable_area_and_bottom_to_top_heights():
    module = _load_host_module("eddy_daq")
    config = (CONFIG_DIR / "printer.cfg").read_text(encoding="utf-8")
    geometry = module.derive_geometry(config, columns=2, rows=2, left_border_mm=5.0)
    points = module.grid_points(geometry)
    gcode = module.render_gcode(
        job_id="grid_1",
        geometry=geometry,
        tap_threshold=7500.0,
        config_fingerprint="a" * 64,
        endstop_positions={
            "t0_x_endstop": -77.635,
            "t0_y_endstop": -14.8,
            "t0_z_endstop": 293.641,
            "t1_x_endstop": 353.087,
            "t1_y_endstop": -13.615,
            "t1_z_endstop": 292.367,
        },
    )

    mesh_min = module._pair_setting(config, "bed_mesh", "mesh_min")
    mesh_max = module._pair_setting(config, "bed_mesh", "mesh_max")
    assert geometry.x.minimum == pytest.approx(mesh_min[0] + 5.0)
    assert geometry.x.maximum == pytest.approx(mesh_max[0])
    assert geometry.y.minimum == pytest.approx(mesh_min[1])
    assert geometry.y.maximum == pytest.approx(mesh_max[1])
    assert [point.column for point in points] == [0, 1, 1, 0]
    assert "EXPECTED_RECORDS=20" in gcode
    assert "T0_Z_ENDSTOP=293.641000" in gcode
    assert "T1_Z_ENDSTOP=292.367000" in gcode
    assert "G1 Z0.400000" in gcode
    assert gcode.index("Z=0.500000") < gcode.index("Z=1.000000") < gcode.index("Z=1.500000") < gcode.index("Z=2.000000")


def test_download_writes_metadata_and_flat_jsonl(monkeypatch, tmp_path):
    module = _load_host_module("daq")
    monkeypatch.setattr(
        module,
        "_remote_jobs",
        lambda *_args: {
            "metadata": {"job_id": "grid_1", "record_kind": "job"},
            "records": [{"job_id": "grid_1", "record_index": 0, "record_kind": "measurement"}],
        },
    )

    metadata_path, records_path = module.download_job("printer", "/tmp/daq.sqlite", "grid_1", tmp_path)

    assert json.loads(metadata_path.read_text())["job_id"] == "grid_1"
    assert json.loads(records_path.read_text())["record_index"] == 0


def test_daq_image_extras_match_primary_and_config_loads_them():
    assert (EXTRAS_DIR / "daq.py").read_bytes() == (IMAGE_EXTRAS_DIR / "daq.py").read_bytes()
    assert (EXTRAS_DIR / "eddy_daq.py").read_bytes() == (IMAGE_EXTRAS_DIR / "eddy_daq.py").read_bytes()
    config_text = (CONFIG_DIR / "printer.cfg").read_text(encoding="utf-8")
    assert "[daq]" in config_text
    assert "[eddy_daq]" in config_text
