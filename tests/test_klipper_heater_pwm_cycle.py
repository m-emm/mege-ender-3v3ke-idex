import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HEATER_PATHS = [
    REPO_ROOT / "klipper_setup/klipper_host/klippy/extras/heaters.py",
    REPO_ROOT
    / "klipper_setup/image_build/overlays/stage2/99-klipperpi/files/klipper_host/klippy/extras/heaters.py",
]


class FakeMcu:
    def max_nominal_duration(self):
        return 3.0


class FakePwm:
    def __init__(self):
        self.mcu = FakeMcu()
        self.cycle_time = None
        self.max_duration = None

    def get_mcu(self):
        return self.mcu

    def setup_cycle_time(self, cycle_time):
        self.cycle_time = cycle_time

    def setup_max_duration(self, max_duration):
        self.max_duration = max_duration


class FakePins:
    def __init__(self, pwm):
        self.pwm = pwm

    def setup_pin(self, pin_type, pin):
        assert pin_type == "pwm"
        assert pin == "gpio20"
        return self.pwm


class FakeGcode:
    def register_mux_command(self, *args, **kwargs):
        pass


class FakePrinter:
    def __init__(self, pwm):
        self.pins = FakePins(pwm)
        self.gcode = FakeGcode()

    def get_start_args(self):
        return {}

    def lookup_object(self, name):
        return {"pins": self.pins, "gcode": self.gcode}[name]

    def load_object(self, config, name):
        pass

    def register_event_handler(self, event, handler):
        pass


class FakeSensor:
    def setup_minmax(self, min_temp, max_temp):
        pass

    def setup_callback(self, callback):
        pass

    def get_report_time_delta(self):
        return 0.3


class FakeConfig:
    def __init__(self, pwm):
        self.printer = FakePrinter(pwm)
        self.pwm_cycle_max = None

    def get_printer(self):
        return self.printer

    def get_name(self):
        return "heater heater_bed"

    def get(self, key):
        assert key == "heater_pin"
        return "gpio20"

    def getfloat(self, key, default=None, **kwargs):
        values = {
            "min_temp": 0.0,
            "max_temp": 130.0,
            "min_extrude_temp": 0.0,
            "max_power": 1.0,
            "smooth_time": 1.0,
            "max_delta": 2.0,
            "pwm_cycle_time": 2.0,
        }
        if key == "pwm_cycle_time":
            self.pwm_cycle_max = kwargs["maxval"]
        return values.get(key, default)

    def getchoice(self, key, choices):
        assert key == "control"
        return choices["watermark"]


def load_heaters(path):
    spec = importlib.util.spec_from_file_location(f"heaters_{path.stat().st_ino}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("heater_path", HEATER_PATHS)
def test_heater_allows_two_second_ssr_cycle_up_to_mcu_limit(heater_path):
    heaters = load_heaters(heater_path)
    pwm = FakePwm()
    config = FakeConfig(pwm)

    heaters.Heater(config, FakeSensor())

    assert config.pwm_cycle_max == 3.0
    assert pwm.cycle_time == 2.0
    assert pwm.max_duration == heaters.MAX_HEAT_TIME == 3.0
