import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

MOTOR_BENCH_SCRIPT = (
    Path(__file__).parents[1]
    / "klipper_setup/klipper_config/wiring/bench_tests"
    / "rp2040plus_tmc5160t_plus_y_motor_bench.py"
)
SPEC = spec_from_file_location(
    "rp2040plus_tmc5160t_plus_y_motor_bench",
    MOTOR_BENCH_SCRIPT,
)
assert SPEC is not None
assert SPEC.loader is not None
MOTOR_BENCH = module_from_spec(SPEC)
sys.modules[SPEC.name] = MOTOR_BENCH
SPEC.loader.exec_module(MOTOR_BENCH)


def test_driver_connected_pin_assignments_exclude_temporary_probes():
    assert MOTOR_BENCH.STEP_PIN == "gpio0"
    assert MOTOR_BENCH.DIR_PIN == "gpio1"
    assert MOTOR_BENCH.ENABLE_PIN == "gpio2"
    assert MOTOR_BENCH.DIAG_PIN == "gpio3"
    assert MOTOR_BENCH.PWR_OK_PIN == "gpio5"
    assert MOTOR_BENCH.MISO_PIN == "gpio8"
    assert MOTOR_BENCH.CS_PIN == "gpio9"
    assert MOTOR_BENCH.SCLK_PIN == "gpio10"
    assert MOTOR_BENCH.MOSI_PIN == "gpio11"

    commands = "\n".join(MOTOR_BENCH.build_config_commands(12_000_000))
    for removed_probe in (
        "gpio16",
        "gpio17",
        "gpio18",
        "gpio19",
        "gpio20",
        "gpio21",
        "gpio22",
        "gpio26",
        "gpio27",
    ):
        assert removed_probe not in commands


def test_12mhz_configuration_has_safe_enable_watchdog_and_spi_mode():
    commands = MOTOR_BENCH.build_config_commands(12_000_000)

    assert (
        "config_stepper oid=0 step_pin=gpio0 dir_pin=gpio1 "
        "invert_step=0 step_pulse_ticks=60"
    ) in commands
    assert (
        "config_digital_out oid=1 pin=gpio2 value=1 default_value=1 "
        "max_duration=24000000"
    ) in commands
    assert (
        "spi_set_sw_bus oid=2 miso_pin=gpio8 mosi_pin=gpio11 "
        "sclk_pin=gpio10 mode=3 pulse_ticks=24"
    ) in commands
    assert "config_endstop oid=3 pin=gpio5 pull_up=0" in commands
    assert "config_endstop oid=4 pin=gpio3 pull_up=0" in commands
    assert "config_spi_shutdown oid=5 spi_oid=2 shutdown_msg=ec14410150" in commands


def test_very_slow_spi_configuration_is_500_times_slower_than_default():
    default_commands = MOTOR_BENCH.build_config_commands(12_000_000)
    slow_commands = MOTOR_BENCH.build_config_commands(
        12_000_000,
        spi_speed_hz=MOTOR_BENCH.VERY_SLOW_SPI_SPEED_HZ,
    )

    default_spi = next(
        command for command in default_commands if command.startswith("spi_set_sw_bus")
    )
    slow_spi = next(
        command for command in slow_commands if command.startswith("spi_set_sw_bus")
    )

    assert "pulse_ticks=24" in default_spi
    assert "pulse_ticks=12000" in slow_spi
    assert (
        MOTOR_BENCH.SPI_SPEED_HZ / MOTOR_BENCH.VERY_SLOW_SPI_SPEED_HZ
        == pytest.approx(500)
    )


def test_spi_speed_override_is_bench_bounded():
    with pytest.raises(ValueError, match="SPI speed must be between"):
        MOTOR_BENCH.build_config_commands(
            12_000_000,
            spi_speed_hz=MOTOR_BENCH.MIN_SPI_SPEED_HZ - 1,
        )

    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(
        [
            "--armed",
            "--spi-only",
            "--spi-speed-hz",
            str(MOTOR_BENCH.VERY_SLOW_SPI_SPEED_HZ),
        ]
    )
    assert args.spi_speed_hz == MOTOR_BENCH.VERY_SLOW_SPI_SPEED_HZ


def test_maximum_software_spi_rate_has_symmetric_12mhz_half_cycles():
    commands = MOTOR_BENCH.build_config_commands(
        12_000_000,
        spi_speed_hz=MOTOR_BENCH.MAX_SPI_SPEED_HZ,
    )
    spi_command = next(
        command for command in commands if command.startswith("spi_set_sw_bus")
    )

    assert MOTOR_BENCH.MAX_SPI_SPEED_HZ == 3_000_000
    assert "pulse_ticks=4" in spi_command
    with pytest.raises(ValueError, match="SPI speed must be between"):
        MOTOR_BENCH.build_config_commands(
            12_000_000,
            spi_speed_hz=MOTOR_BENCH.MAX_SPI_SPEED_HZ + 1,
        )


def test_22_milliohm_current_quantizes_to_klipper_register_settings():
    current = MOTOR_BENCH.calculate_current_settings(
        1.0,
        sense_resistor_ohms=0.022,
    )

    assert current.globalscaler == 32
    assert current.irun == 24
    assert current.ihold == 24
    assert current.actual_run_current_a == pytest.approx(1.0201069952)


def test_22_milliohm_max_stress_current_quantizes_near_2_5_amps():
    current = MOTOR_BENCH.calculate_current_settings(
        MOTOR_BENCH.MAX_STRESS_CURRENT_A,
        sense_resistor_ohms=0.022,
    )

    assert current.globalscaler == 61
    assert current.irun == 31
    assert current.ihold == 31
    assert current.actual_run_current_a == pytest.approx(2.4890610684)


def test_register_defaults_select_16_microsteps_spreadcycle_and_interpolation():
    registers = dict(MOTOR_BENCH.INIT_REGISTERS)

    assert registers[MOTOR_BENCH.REGISTER_GCONF] == 0x00000008
    assert registers[MOTOR_BENCH.REGISTER_GLOBALSCALER] == 0x20
    assert registers[MOTOR_BENCH.REGISTER_IHOLD_IRUN] == 0x00061818
    assert registers[MOTOR_BENCH.REGISTER_TPWMTHRS] == 0x000FFFFF
    assert registers[MOTOR_BENCH.REGISTER_CHOPCONF] == 0x14410153
    assert registers[MOTOR_BENCH.REGISTER_PWMCONF] == 0xC40C001E
    assert MOTOR_BENCH.CHOPCONF_SHUTDOWN == 0x14410150
    assert MOTOR_BENCH.CHOPCONF_RUN & 0x0F == 3
    assert MOTOR_BENCH.CHOPCONF_SHUTDOWN & 0x0F == 0
    assert (MOTOR_BENCH.CHOPCONF_RUN >> 24) & 0x0F == 4
    assert MOTOR_BENCH.CHOPCONF_RUN & (1 << 28)


def test_spi_frames_and_response_decoding():
    assert MOTOR_BENCH.encode_tmc_read(MOTOR_BENCH.REGISTER_IOIN) == bytes.fromhex(
        "0400000000"
    )
    assert MOTOR_BENCH.encode_tmc_write(
        MOTOR_BENCH.REGISTER_CHOPCONF,
        MOTOR_BENCH.CHOPCONF_RUN,
    ) == bytes.fromhex("ec14410153")

    response = MOTOR_BENCH.decode_tmc_response(bytes.fromhex("a530000010"))
    assert response.status == 0xA5
    assert response.value == 0x30000010


def test_fault_register_flags_decode_independently():
    gstat = MOTOR_BENCH.decode_flags(
        (1 << 1) | (1 << 2),
        MOTOR_BENCH.GSTAT_FLAGS,
    )
    driver = MOTOR_BENCH.decode_flags(
        (1 << 25) | (1 << 29),
        MOTOR_BENCH.DRV_STATUS_FLAGS,
    )

    assert gstat == ("drv_err", "uv_cp")
    assert driver == ("ot", "ola")


def test_write_verification_uses_tmc_write_echo_for_write_only_registers():
    class FakeClient:
        def __init__(self):
            self.commands = []

        def send_command(self, command):
            self.commands.append(command)

        def request(self, command, _response_name, predicate):
            self.commands.append(command)
            response = {
                "oid": MOTOR_BENCH.SPI_OID,
                "response": bytes.fromhex("0000000400"),
            }
            assert predicate(response)
            return response

    client = FakeClient()
    MOTOR_BENCH.write_register_verified(
        client,
        MOTOR_BENCH.REGISTER_DRV_CONF,
        0x00000400,
    )

    assert client.commands == [
        "spi_send oid=2 data=8a00000400",
        "spi_transfer oid=2 data=0000000000",
    ]


def test_jog_is_fixed_equal_and_bounded():
    assert MOTOR_BENCH.JOG_STEPS == 128
    assert MOTOR_BENCH.JOG_STEP_RATE_HZ == 400
    assert MOTOR_BENCH.JOG_STEPS / MOTOR_BENCH.JOG_STEP_RATE_HZ == pytest.approx(0.32)
    assert MOTOR_BENCH.ENABLE_WATCHDOG_S == 2.0
    assert MOTOR_BENCH.SPI_SHUTDOWN_DATA == bytes.fromhex("ec14410150")


def test_low_current_hold_is_fixed_and_below_nominal_current():
    current = MOTOR_BENCH.calculate_current_settings(MOTOR_BENCH.LOW_CURRENT_HOLD_A)

    assert MOTOR_BENCH.LOW_CURRENT_HOLD_A == 0.2
    assert current.actual_run_current_a == pytest.approx(0.2040213990)
    assert current.irun == 4
    assert current.ihold == 4
    assert MOTOR_BENCH.LOW_CURRENT_HOLD_DURATION_S == 10.0
    assert MOTOR_BENCH.WATCHDOG_REFRESH_INTERVAL_S < MOTOR_BENCH.ENABLE_WATCHDOG_S


def test_unarmed_invocation_is_a_hardware_free_dry_run():
    result = subprocess.run(
        [
            sys.executable,
            str(MOTOR_BENCH_SCRIPT),
            "--device",
            "/dev/this-device-must-not-be-opened",
            "--jog",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Dry run only." in result.stdout
    assert "PHYSICAL EMERGENCY STOP" in result.stdout
    assert "128 steps forward + 128 backward" in result.stdout


def test_low_current_step_test_is_fixed_slow_and_bounded():
    assert MOTOR_BENCH.LOW_CURRENT_PRE_STEP_HOLD_S == 5.0
    assert MOTOR_BENCH.LOW_CURRENT_STEP_COUNT == 1_000
    assert MOTOR_BENCH.LOW_CURRENT_STEP_RATE_HZ == 200
    assert MOTOR_BENCH.LOW_CURRENT_EXPECTED_MCU_POSITION == -1_000
    assert (
        MOTOR_BENCH.LOW_CURRENT_STEP_COUNT / MOTOR_BENCH.LOW_CURRENT_STEP_RATE_HZ
        == pytest.approx(5.0)
    )


def test_full_current_reverse_test_is_equal_slow_and_bounded():
    assert MOTOR_BENCH.FULL_CURRENT_REVERSE_STEP_COUNT == 2_000
    assert MOTOR_BENCH.FULL_CURRENT_REVERSE_STEP_RATE_HZ == 200
    assert (
        MOTOR_BENCH.FULL_CURRENT_REVERSE_STEP_COUNT
        * 2
        / MOTOR_BENCH.FULL_CURRENT_REVERSE_STEP_RATE_HZ
        == pytest.approx(20.0)
    )


def test_repeated_motion_test_has_three_ten_cycle_enable_groups():
    motion_duration_s = (
        MOTOR_BENCH.REPEATED_MOTION_STEP_COUNT
        * 2
        * MOTOR_BENCH.REPEATED_MOTION_CYCLES_PER_RUN
        / MOTOR_BENCH.REPEATED_MOTION_STEP_RATE_HZ
    )
    enabled_duration_s = (
        MOTOR_BENCH.JOG_START_LEAD_S
        + motion_duration_s
        + MOTOR_BENCH.JOG_COMPLETION_MARGIN_S
    )
    current = MOTOR_BENCH.calculate_current_settings(
        MOTOR_BENCH.REPEATED_MOTION_CURRENT_A
    )

    assert MOTOR_BENCH.REPEATED_MOTION_RUNS == 3
    assert MOTOR_BENCH.REPEATED_MOTION_CYCLES_PER_RUN == 10
    assert (
        MOTOR_BENCH.REPEATED_MOTION_RUNS * MOTOR_BENCH.REPEATED_MOTION_CYCLES_PER_RUN
        == 30
    )
    assert (
        MOTOR_BENCH.REPEATED_MOTION_STEP_COUNT
        == MOTOR_BENCH.FULL_CURRENT_REVERSE_STEP_COUNT
    )
    assert motion_duration_s == pytest.approx(6.25)
    assert enabled_duration_s == pytest.approx(6.70)
    assert current.requested_run_current_a == MOTOR_BENCH.REPEATED_MOTION_CURRENT_A
    assert current.actual_run_current_a == pytest.approx(
        MOTOR_BENCH.REPEATED_MOTION_CURRENT_A,
        rel=0.03,
    )


def test_max_stress_test_has_long_ten_revolution_legs():
    assert MOTOR_BENCH.MICROSTEPS == 16
    assert MOTOR_BENCH.MOTOR_FULL_STEPS_PER_REVOLUTION == 200
    assert MOTOR_BENCH.MAX_STRESS_REVOLUTIONS_PER_LEG == 10
    assert MOTOR_BENCH.MAX_STRESS_STEP_COUNT == 32_000
    assert MOTOR_BENCH.MAX_STRESS_STEP_RATE_HZ == 6_400
    assert MOTOR_BENCH.MAX_STRESS_LEG_DURATION_S == pytest.approx(5.0)
    assert MOTOR_BENCH.MAX_STRESS_RUNS == 3
    assert (
        MOTOR_BENCH.MAX_STRESS_MONITOR_INTERVAL_S
        < MOTOR_BENCH.ENABLE_WATCHDOG_S
    )


def test_position_checks_are_relative_to_each_invocation():
    MOTOR_BENCH.require_position_delta(
        start_position=-1_000,
        end_position=-1_000,
        expected_delta=0,
        stage="test",
    )
    with pytest.raises(MOTOR_BENCH.BenchFailure, match="position delta"):
        MOTOR_BENCH.require_position_delta(
            start_position=-1_000,
            end_position=0,
            expected_delta=0,
            stage="test",
        )


def test_enable_probe_is_an_explicit_armed_mode():
    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(["--armed", "--enable-probe"])

    assert args.armed
    assert args.enable_probe
    assert not args.spi_only
    assert not args.jog


def test_low_current_hold_is_an_explicit_armed_mode():
    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(["--armed", "--low-current-hold"])

    assert args.armed
    assert args.low_current_hold
    assert not args.spi_only
    assert not args.enable_probe
    assert not args.jog


def test_low_current_step_test_is_an_explicit_armed_mode():
    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(["--armed", "--low-current-step-test"])

    assert args.armed
    assert args.low_current_step_test
    assert not args.spi_only
    assert not args.enable_probe
    assert not args.low_current_hold
    assert not args.jog


def test_full_current_reverse_test_is_an_explicit_armed_mode():
    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(["--armed", "--full-current-reverse-test"])

    assert args.armed
    assert args.full_current_reverse_test
    assert not args.spi_only
    assert not args.enable_probe
    assert not args.low_current_hold
    assert not args.low_current_step_test
    assert not args.jog


def test_repeated_motion_test_is_an_explicit_armed_mode():
    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(["--armed", "--repeated-motion-test"])

    assert args.armed
    assert args.repeated_motion_test
    assert not args.spi_only
    assert not args.enable_probe
    assert not args.low_current_hold
    assert not args.low_current_step_test
    assert not args.full_current_reverse_test
    assert not args.jog


def test_max_stress_test_is_an_explicit_armed_mode():
    parser = MOTOR_BENCH.build_parser()
    args = parser.parse_args(["--armed", "--max-stress-test"])

    assert args.armed
    assert args.max_stress_test
    assert not args.spi_only
    assert not args.repeated_motion_test
    assert not args.jog
