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
    step_input = BENCH.OUTGOING_PROBE_BY_NAME["STEP input-side"]
    driver_step = BENCH.OUTGOING_PROBE_BY_NAME["STEP driver-side"]
    miso_return = BENCH.RETURN_PROBE_BY_NAME["MISO Pico-side"]

    assert (step_input.pin, step_input.physical_pin) == ("gpio17", 22)
    assert (driver_step.pin, driver_step.physical_pin) == ("gpio16", 21)
    assert (miso_return.pin, miso_return.physical_pin) == ("gpio8", 11)
    assert miso_return.endpoint == "PICO_GPIO_8"


def test_input_probe_masks_are_independent_and_cover_each_bank():
    outgoing_masks = {probe.mask for probe in BENCH.OUTGOING_PROBES}
    return_masks = {probe.mask for probe in BENCH.RETURN_PROBES}

    assert len(outgoing_masks) == len(BENCH.OUTGOING_PROBES)
    assert len(return_masks) == len(BENCH.RETURN_PROBES)
    assert sum(outgoing_masks) == BENCH.OUTGOING_INPUT_MASK
    assert sum(return_masks) == BENCH.RETURN_INPUT_MASK
    assert BENCH.STEP_INPUT_MASK != (
        BENCH.OUTGOING_PROBE_BY_NAME["STEP driver-side"].mask
    )


def test_expected_power_states_match_the_bench_contract():
    assert BENCH.PWR_OK_MASK == BENCH.OUTGOING_PROBE_BY_NAME["PWR_OK"].mask
    assert BENCH.HV_ON_IDLE_STATE & BENCH.PWR_OK_MASK
    assert BENCH.HV_ON_IDLE_STATE & (
        BENCH.OUTGOING_PROBE_BY_NAME["ENABLE driver-side"].mask
    )
    assert BENCH.HV_ON_IDLE_STATE & (
        BENCH.OUTGOING_PROBE_BY_NAME["CS driver-side"].mask
    )
    assert not BENCH.HV_ON_IDLE_STATE & BENCH.STEP_INPUT_MASK


def test_bench_configuration_uses_declared_wiring_pins():
    commands = "\n".join(BENCH.CONFIG_COMMANDS)
    for output in BENCH.OUTPUTS:
        assert f"pin={output.pin}" in commands
    for probe in (*BENCH.OUTGOING_PROBES, *BENCH.RETURN_PROBES):
        assert f"pin={probe.pin}" in commands

    assert (
        BENCH.OUTPUT_BY_NAME["TMC_MISO_TEST"].endpoint
        == "TMC1_J1_MISO_CFG0_5"
    )
