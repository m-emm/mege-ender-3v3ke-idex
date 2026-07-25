import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

BENCH_SCRIPT = (
    Path(__file__).parents[1]
    / "klipper_setup/klipper_config/wiring/bench_tests"
    / "rp2040plus_tmc5160t_plus_y_bench.py"
)
SPEC = spec_from_file_location("rp2040plus_tmc5160t_plus_y_bench", BENCH_SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
BENCH = module_from_spec(SPEC)
sys.modules[SPEC.name] = BENCH
SPEC.loader.exec_module(BENCH)


def test_temporary_probe_names_resolve_to_rp2040_gpio_numbers():
    assert BENCH.STEP_INPUT_PIN == "gpio17"
    assert BENCH.STEP_INPUT_PHYSICAL_PIN == 22
    assert BENCH.DRIVER_STEP_INPUT_PIN == "gpio16"
    assert BENCH.DRIVER_STEP_INPUT_PHYSICAL_PIN == 21


def test_input_state_decoder_keeps_three_assertions_independent():
    low = BENCH.decode_input_state(0)
    assert not low.pwr_ok
    assert not low.step_input
    assert not low.driver_step

    step_high = BENCH.decode_input_state(BENCH.STEP_INPUT_MASK)
    assert not step_high.pwr_ok
    assert step_high.step_input
    assert not step_high.driver_step

    all_high = BENCH.decode_input_state(BENCH.HV_ON_STEP_HIGH_STATE)
    assert all_high.pwr_ok
    assert all_high.step_input
    assert all_high.driver_step


def test_expected_power_states_match_the_bench_contract():
    assert BENCH.NO_HV_STEP_LOW_STATE == 0
    assert BENCH.NO_HV_STEP_HIGH_STATE == BENCH.STEP_INPUT_MASK
    assert BENCH.HV_ON_STEP_LOW_STATE == BENCH.PWR_OK_MASK
    assert BENCH.HV_ON_STEP_HIGH_STATE == BENCH.INPUT_MASK


def test_bench_configuration_uses_declared_wiring_pins():
    commands = "\n".join(BENCH.CONFIG_COMMANDS)
    assert f"pin={BENCH.STEP_OUTPUT_PIN}" in commands
    assert f"pin={BENCH.PWR_OK_INPUT_PIN}" in commands
    assert f"pin={BENCH.STEP_INPUT_PIN}" in commands
    assert f"pin={BENCH.DRIVER_STEP_INPUT_PIN}" in commands
