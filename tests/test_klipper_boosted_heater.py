import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HEATERS_PATH = (
    REPO_ROOT / "klipper_setup" / "klipper_host" / "klippy" / "extras" / "heaters.py"
)


def _load_heaters_module():
    spec = importlib.util.spec_from_file_location("boosted_heaters", HEATERS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("aggregate_pwm", "expected_primary", "expected_boost"),
    [
        (0.0, 0.0, 0.0),
        (120.0 / 740.0, 0.5, 0.0),
        (240.0 / 740.0, 1.0, 0.0),
        (490.0 / 740.0, 1.0, 0.5),
        (1.0, 1.0, 1.0),
        (2.0, 1.0, 1.0),
    ],
)
def test_boosted_heater_power_split(aggregate_pwm, expected_primary, expected_boost):
    heaters = _load_heaters_module()

    primary, boost = heaters.split_boosted_heater_power(
        aggregate_pwm,
        primary_power=240.0,
        boost_power=500.0,
    )

    assert primary == pytest.approx(expected_primary)
    assert boost == pytest.approx(expected_boost)


def test_boosted_heater_power_split_clamps_negative_power_request():
    heaters = _load_heaters_module()

    assert heaters.split_boosted_heater_power(-1.0, 240.0, 500.0) == (0.0, 0.0)
