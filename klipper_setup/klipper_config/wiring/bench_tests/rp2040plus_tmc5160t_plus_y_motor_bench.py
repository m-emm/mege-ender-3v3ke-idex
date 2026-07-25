#!/usr/bin/env python3
"""Bench-test a powered TMC5160T Plus and optionally jog a secured motor."""

from __future__ import annotations

import argparse
import math
import signal
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rp2040plus_tmc5160t_plus_y_bench import (  # noqa: E402
    BenchFailure,
    KlipperSerial,
    load_klipper_msgproto,
    select_serial_device,
)


STEP_PIN = "gpio0"
DIR_PIN = "gpio1"
ENABLE_PIN = "gpio2"
DIAG_PIN = "gpio3"
PWR_OK_PIN = "gpio5"
MISO_PIN = "gpio8"
CS_PIN = "gpio9"
SCLK_PIN = "gpio10"
MOSI_PIN = "gpio11"

STEPPER_OID = 0
ENABLE_OID = 1
SPI_OID = 2
PWR_OK_OID = 3
DIAG_OID = 4
SPI_SHUTDOWN_OID = 5
OID_COUNT = 6

SPI_MODE = 3
SPI_SPEED_HZ = 500_000
MIN_SPI_SPEED_HZ = 1_000
MAX_SPI_SPEED_HZ = SPI_SPEED_HZ
VERY_SLOW_SPI_SPEED_HZ = MIN_SPI_SPEED_HZ
STEP_PULSE_DURATION_S = 0.000005
ENABLE_WATCHDOG_S = 2.0

SENSE_RESISTOR_OHMS = 0.022
REQUESTED_CURRENT_A = 1.0
LOW_CURRENT_HOLD_A = 0.2
LOW_CURRENT_HOLD_DURATION_S = 10.0
LOW_CURRENT_PRE_STEP_HOLD_S = 5.0
LOW_CURRENT_STEP_COUNT = 1_000
LOW_CURRENT_STEP_RATE_HZ = 200
LOW_CURRENT_EXPECTED_MCU_POSITION = -LOW_CURRENT_STEP_COUNT
FULL_CURRENT_REVERSE_STEP_COUNT = 2_000
FULL_CURRENT_REVERSE_STEP_RATE_HZ = 200
REPEATED_MOTION_RUNS = 3
REPEATED_MOTION_CYCLES_PER_RUN = 10
REPEATED_MOTION_STEP_COUNT = FULL_CURRENT_REVERSE_STEP_COUNT
REPEATED_MOTION_STEP_RATE_HZ = 6_400
REPEATED_MOTION_CURRENT_A = 1.5
WATCHDOG_REFRESH_INTERVAL_S = 0.75
MICROSTEPS = 16
JOG_STEPS = 128
JOG_STEP_RATE_HZ = 400
JOG_START_LEAD_S = 0.25
JOG_COMPLETION_MARGIN_S = 0.20

TMC_VERSION = 0x30
TMC_VREF = 0.325
TMC_MAX_CURRENT_A = 10.0

REGISTER_GCONF = 0x00
REGISTER_GSTAT = 0x01
REGISTER_IOIN = 0x04
REGISTER_DRV_CONF = 0x0A
REGISTER_GLOBALSCALER = 0x0B
REGISTER_IHOLD_IRUN = 0x10
REGISTER_TPOWERDOWN = 0x11
REGISTER_TPWMTHRS = 0x13
REGISTER_TCOOLTHRS = 0x14
REGISTER_THIGH = 0x15
REGISTER_MSLUT0 = 0x60
REGISTER_MSLUT1 = 0x61
REGISTER_MSLUT2 = 0x62
REGISTER_MSLUT3 = 0x63
REGISTER_MSLUT4 = 0x64
REGISTER_MSLUT5 = 0x65
REGISTER_MSLUT6 = 0x66
REGISTER_MSLUT7 = 0x67
REGISTER_MSLUTSEL = 0x68
REGISTER_MSLUTSTART = 0x69
REGISTER_CHOPCONF = 0x6C
REGISTER_COOLCONF = 0x6D
REGISTER_DRV_STATUS = 0x6F
REGISTER_PWMCONF = 0x70

REGISTER_NAMES = {
    REGISTER_GCONF: "GCONF",
    REGISTER_GSTAT: "GSTAT",
    REGISTER_IOIN: "IOIN",
    REGISTER_DRV_CONF: "DRV_CONF",
    REGISTER_GLOBALSCALER: "GLOBALSCALER",
    REGISTER_IHOLD_IRUN: "IHOLD_IRUN",
    REGISTER_TPOWERDOWN: "TPOWERDOWN",
    REGISTER_TPWMTHRS: "TPWMTHRS",
    REGISTER_TCOOLTHRS: "TCOOLTHRS",
    REGISTER_THIGH: "THIGH",
    REGISTER_MSLUT0: "MSLUT0",
    REGISTER_MSLUT1: "MSLUT1",
    REGISTER_MSLUT2: "MSLUT2",
    REGISTER_MSLUT3: "MSLUT3",
    REGISTER_MSLUT4: "MSLUT4",
    REGISTER_MSLUT5: "MSLUT5",
    REGISTER_MSLUT6: "MSLUT6",
    REGISTER_MSLUT7: "MSLUT7",
    REGISTER_MSLUTSEL: "MSLUTSEL",
    REGISTER_MSLUTSTART: "MSLUTSTART",
    REGISTER_CHOPCONF: "CHOPCONF",
    REGISTER_COOLCONF: "COOLCONF",
    REGISTER_DRV_STATUS: "DRV_STATUS",
    REGISTER_PWMCONF: "PWMCONF",
}

GSTAT_FLAGS = {
    "reset": 1 << 0,
    "drv_err": 1 << 1,
    "uv_cp": 1 << 2,
}
DRV_STATUS_FLAGS = {
    "s2vsa": 1 << 12,
    "s2vsb": 1 << 13,
    "ot": 1 << 25,
    "otpw": 1 << 26,
    "s2ga": 1 << 27,
    "s2gb": 1 << 28,
    "ola": 1 << 29,
    "olb": 1 << 30,
    "stst": 1 << 31,
}
FATAL_DRV_STATUS_FLAGS = (
    "s2vsa",
    "s2vsb",
    "ot",
    "otpw",
    "s2ga",
    "s2gb",
)

WAVE_TABLE_REGISTERS = (
    (REGISTER_MSLUT0, 2_863_314_260),
    (REGISTER_MSLUT1, 1_251_300_522),
    (REGISTER_MSLUT2, 608_774_441),
    (REGISTER_MSLUT3, 269_500_962),
    (REGISTER_MSLUT4, 4_227_858_431),
    (REGISTER_MSLUT5, 3_048_961_917),
    (REGISTER_MSLUT6, 1_227_445_590),
    (REGISTER_MSLUT7, 4_211_234),
    (REGISTER_MSLUTSEL, 0xFFFF8056),
    (REGISTER_MSLUTSTART, 0x00F70000),
)


@dataclass(frozen=True)
class CurrentSettings:
    requested_run_current_a: float
    actual_run_current_a: float
    globalscaler: int
    irun: int
    ihold: int


@dataclass(frozen=True)
class TmcResponse:
    status: int
    value: int


def calculate_current_settings(
    run_current_a: float = REQUESTED_CURRENT_A,
    *,
    sense_resistor_ohms: float = SENSE_RESISTOR_OHMS,
) -> CurrentSettings:
    if not 0.0 < run_current_a <= TMC_MAX_CURRENT_A:
        raise ValueError("run current must be between 0 and 10 A")
    if sense_resistor_ohms <= 0.0:
        raise ValueError("sense resistor must be positive")

    globalscaler = int(
        run_current_a * 256.0 * math.sqrt(2.0) * sense_resistor_ohms / TMC_VREF + 0.5
    )
    globalscaler = max(32, globalscaler)
    if globalscaler >= 256:
        globalscaler = 0
    effective_globalscaler = globalscaler or 256

    current_scale = int(
        run_current_a
        * 256.0
        * 32.0
        * math.sqrt(2.0)
        * sense_resistor_ohms
        / (effective_globalscaler * TMC_VREF)
        - 1.0
        + 0.5
    )
    current_scale = max(0, min(31, current_scale))
    actual_current = (
        effective_globalscaler
        * (current_scale + 1)
        * TMC_VREF
        / (256.0 * 32.0 * math.sqrt(2.0) * sense_resistor_ohms)
    )
    return CurrentSettings(
        requested_run_current_a=run_current_a,
        actual_run_current_a=actual_current,
        globalscaler=globalscaler,
        irun=current_scale,
        ihold=current_scale,
    )


def build_chopconf(*, toff: int) -> int:
    if not 0 <= toff <= 0x0F:
        raise ValueError("toff must fit in four bits")
    mres = int(math.log2(256 // MICROSTEPS))
    return (
        toff
        | (5 << 4)  # HSTRT
        | (2 << 7)  # HEND
        | (2 << 15)  # TBL
        | (4 << 20)  # TPFD
        | (mres << 24)
        | (1 << 28)  # INTPOL
    )


CHOPCONF_RUN = build_chopconf(toff=3)
CHOPCONF_SHUTDOWN = build_chopconf(toff=0)
SPI_SHUTDOWN_DATA = bytes((REGISTER_CHOPCONF | 0x80,)) + CHOPCONF_SHUTDOWN.to_bytes(
    4, "big"
)


def build_init_registers(
    current: CurrentSettings | None = None,
) -> tuple[tuple[int, int], ...]:
    current = current or calculate_current_settings()
    ihold_irun = (6 << 16) | (current.irun << 8) | current.ihold
    pwmconf = (
        30  # PWM_OFS
        | (1 << 18)  # PWM_AUTOSCALE
        | (1 << 19)  # PWM_AUTOGRAD
        | (4 << 24)  # PWM_REG
        | (12 << 28)  # PWM_LIM
    )
    return (
        (REGISTER_GCONF, 1 << 3),  # MULTISTEP_FILT, SpreadCycle
        (REGISTER_DRV_CONF, 4 << 8),  # BBMCLKS
        (REGISTER_GLOBALSCALER, current.globalscaler),
        (REGISTER_IHOLD_IRUN, ihold_irun),
        (REGISTER_TPOWERDOWN, 10),
        (REGISTER_TPWMTHRS, 0xFFFFF),
        (REGISTER_TCOOLTHRS, 0),
        (REGISTER_THIGH, 0),
        *WAVE_TABLE_REGISTERS,
        (REGISTER_CHOPCONF, CHOPCONF_RUN),
        (REGISTER_COOLCONF, 0),
        (REGISTER_PWMCONF, pwmconf),
    )


INIT_REGISTERS = build_init_registers()


def encode_tmc_read(register: int) -> bytes:
    return bytes((register & 0x7F, 0, 0, 0, 0))


def encode_tmc_write(register: int, value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("TMC register value must fit in 32 bits")
    return bytes((register | 0x80,)) + value.to_bytes(4, "big")


def decode_tmc_response(response: bytes | bytearray) -> TmcResponse:
    if len(response) != 5:
        raise BenchFailure(
            f"Expected a five-byte TMC SPI response, received {len(response)}"
        )
    return TmcResponse(status=response[0], value=int.from_bytes(response[1:], "big"))


def decode_flags(value: int, flag_masks: dict[str, int]) -> tuple[str, ...]:
    return tuple(name for name, mask in flag_masks.items() if value & mask)


def build_config_commands(
    clock_frequency: int,
    *,
    spi_speed_hz: int = SPI_SPEED_HZ,
) -> tuple[str, ...]:
    if clock_frequency <= 0:
        raise ValueError("clock frequency must be positive")
    if not MIN_SPI_SPEED_HZ <= spi_speed_hz <= MAX_SPI_SPEED_HZ:
        raise ValueError(
            f"SPI speed must be between {MIN_SPI_SPEED_HZ} and "
            f"{MAX_SPI_SPEED_HZ} Hz"
        )
    step_pulse_ticks = round(clock_frequency * STEP_PULSE_DURATION_S)
    watchdog_ticks = round(clock_frequency * ENABLE_WATCHDOG_S)
    spi_pulse_ticks = round(clock_frequency / spi_speed_hz)
    if spi_pulse_ticks < 2:
        raise ValueError("SPI speed is too high for the MCU clock")
    return (
        f"allocate_oids count={OID_COUNT}",
        f"config_stepper oid={STEPPER_OID} step_pin={STEP_PIN} "
        f"dir_pin={DIR_PIN} invert_step=0 step_pulse_ticks={step_pulse_ticks}",
        f"config_digital_out oid={ENABLE_OID} pin={ENABLE_PIN} "
        f"value=1 default_value=1 max_duration={watchdog_ticks}",
        f"config_spi oid={SPI_OID} pin={CS_PIN} cs_active_high=0",
        f"spi_set_sw_bus oid={SPI_OID} miso_pin={MISO_PIN} "
        f"mosi_pin={MOSI_PIN} sclk_pin={SCLK_PIN} "
        f"mode={SPI_MODE} pulse_ticks={spi_pulse_ticks}",
        f"config_endstop oid={PWR_OK_OID} pin={PWR_OK_PIN} pull_up=0",
        f"config_endstop oid={DIAG_OID} pin={DIAG_PIN} pull_up=0",
        f"config_spi_shutdown oid={SPI_SHUTDOWN_OID} spi_oid={SPI_OID} "
        f"shutdown_msg={SPI_SHUTDOWN_DATA.hex()}",
    )


def configure_bench(
    client: KlipperSerial,
    *,
    spi_speed_hz: int = SPI_SPEED_HZ,
) -> None:
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    config_commands = build_config_commands(
        clock_frequency,
        spi_speed_hz=spi_speed_hz,
    )
    config_crc = zlib.crc32("\n".join(config_commands).encode()) & 0xFFFFFFFF
    config = client.request("get_config", "config")
    if config["is_shutdown"]:
        raise BenchFailure("The Klipper MCU is in shutdown state; reconnect USB.")
    if config["is_config"]:
        if config["crc"] != config_crc:
            raise BenchFailure(
                "The MCU already has a different Klipper configuration "
                f"(crc={config['crc']}, motor-bench crc={config_crc}). "
                "Reconnect USB to reset it, then rerun this bench test."
            )
    else:
        for command in config_commands:
            client.send_command(command)
        client.send_command(f"finalize_config crc={config_crc}")

    client.send_command(f"update_digital_out oid={ENABLE_OID} value=1")
    client.send_command(f"reset_step_clock oid={STEPPER_OID} clock=0")


def query_input(client: KlipperSerial, oid: int) -> bool:
    response = client.request(
        f"endstop_query_state oid={oid}",
        "endstop_state",
        predicate=lambda item, oid=oid: item["oid"] == oid,
    )
    return bool(response["pin_value"])


def require_safe_inputs(client: KlipperSerial, *, stage: str) -> None:
    pwr_ok = query_input(client, PWR_OK_OID)
    diag = query_input(client, DIAG_OID)
    if not pwr_ok:
        raise BenchFailure(f"{stage}: PWR_OK is LOW; refusing powered driver access")
    if diag:
        raise BenchFailure(f"{stage}: DIAG1 is HIGH; refusing to continue")


def spi_send(client: KlipperSerial, data: bytes) -> None:
    client.send_command(f"spi_send oid={SPI_OID} data={data.hex()}")


def spi_transfer(client: KlipperSerial, data: bytes) -> bytes:
    response = client.request(
        f"spi_transfer oid={SPI_OID} data={data.hex()}",
        "spi_transfer_response",
        predicate=lambda item: item["oid"] == SPI_OID,
    )
    return bytes(response["response"])


def read_register(client: KlipperSerial, register: int) -> TmcResponse:
    command = encode_tmc_read(register)
    spi_send(client, command)
    return decode_tmc_response(spi_transfer(client, command))


def write_register(client: KlipperSerial, register: int, value: int) -> None:
    spi_send(client, encode_tmc_write(register, value))


def write_register_verified(
    client: KlipperSerial,
    register: int,
    value: int,
    *,
    attempts: int = 5,
) -> None:
    write_command = encode_tmc_write(register, value)
    dummy_read = bytes(5)
    last_value = 0
    for _attempt in range(attempts):
        spi_send(client, write_command)
        last_value = decode_tmc_response(spi_transfer(client, dummy_read)).value
        if last_value == value:
            return
    name = REGISTER_NAMES[register]
    raise BenchFailure(
        f"Unable to write TMC register {name}={value:#010x} "
        f"after {attempts} attempts; last SPI write echo was "
        f"{last_value:#010x}"
    )


def require_ioin(
    response: TmcResponse,
    *,
    expected_disabled: bool,
    stage: str,
) -> None:
    version = (response.value >> 24) & 0xFF
    driver_disabled = bool(response.value & (1 << 4))
    if version != TMC_VERSION:
        raise BenchFailure(
            f"{stage}: IOIN VERSION is 0x{version:02x}, expected 0x{TMC_VERSION:02x}"
        )
    if driver_disabled != expected_disabled:
        expected = "HIGH/disabled" if expected_disabled else "LOW/enabled"
        actual = "HIGH/disabled" if driver_disabled else "LOW/enabled"
        raise BenchFailure(
            f"{stage}: TMC DRV_ENN is {actual}, expected {expected}; "
            "check GPIO2/ENABLE polarity and wiring"
        )


def require_clean_status(
    client: KlipperSerial,
    *,
    stage: str,
) -> tuple[TmcResponse, TmcResponse]:
    gstat = read_register(client, REGISTER_GSTAT)
    drv_status = read_register(client, REGISTER_DRV_STATUS)
    gstat_flags = decode_flags(gstat.value, GSTAT_FLAGS)
    drv_flags = decode_flags(drv_status.value, DRV_STATUS_FLAGS)
    gstat_faults = tuple(flag for flag in gstat_flags if flag in ("drv_err", "uv_cp"))
    driver_faults = tuple(flag for flag in drv_flags if flag in FATAL_DRV_STATUS_FLAGS)
    if gstat_faults or driver_faults:
        details = ", ".join((*gstat_faults, *driver_faults))
        raise BenchFailure(f"{stage}: TMC fault flags asserted: {details}")
    print(
        f"   {stage}: GSTAT={gstat.value:#010x} "
        f"DRV_STATUS={drv_status.value:#010x} "
        f"flags={','.join((*gstat_flags, *drv_flags)) or 'none'}",
        flush=True,
    )
    return gstat, drv_status


def initialize_driver(
    client: KlipperSerial,
    *,
    current: CurrentSettings | None = None,
) -> None:
    current = current or calculate_current_settings()
    init_registers = build_init_registers(current)
    print("2. Verifying SPI identity with the motor disabled ...", flush=True)
    ioin = read_register(client, REGISTER_IOIN)
    require_ioin(ioin, expected_disabled=True, stage="pre-initialization")
    print(
        f"   PASS: IOIN={ioin.value:#010x}, VERSION=0x{TMC_VERSION:02x}, "
        "DRV_ENN=HIGH/disabled",
        flush=True,
    )

    initial_gstat = read_register(client, REGISTER_GSTAT)
    print(
        f"   initial GSTAT={initial_gstat.value:#010x} "
        f"flags={','.join(decode_flags(initial_gstat.value, GSTAT_FLAGS)) or 'none'}",
        flush=True,
    )
    write_register(client, REGISTER_GSTAT, sum(GSTAT_FLAGS.values()))

    print("3. Programming the pinned Klipper TMC5160 defaults ...", flush=True)
    for register, value in init_registers:
        write_register_verified(client, register, value)
    print(
        "   PASS: register programming verified by SPI write echo; "
        f"requested current={current.requested_run_current_a:.3f} A RMS, "
        f"quantized current={current.actual_run_current_a:.3f} A RMS",
        flush=True,
    )
    require_clean_status(client, stage="post-initialization")


def disable_driver(client: KlipperSerial) -> None:
    client.send_command(f"update_digital_out oid={ENABLE_OID} value=1")
    write_register(client, REGISTER_CHOPCONF, CHOPCONF_SHUTDOWN)


def verify_disabled_postcondition(client: KlipperSerial, *, stage: str) -> None:
    require_safe_inputs(client, stage=stage)
    ioin = read_register(client, REGISTER_IOIN)
    require_ioin(ioin, expected_disabled=True, stage=stage)
    chopconf = read_register(client, REGISTER_CHOPCONF)
    if chopconf.value != CHOPCONF_SHUTDOWN:
        raise BenchFailure(
            f"{stage}: CHOPCONF is {chopconf.value:#010x}, "
            f"expected shutdown value {CHOPCONF_SHUTDOWN:#010x}"
        )
    require_clean_status(client, stage=stage)


def run_enable_probe(client: KlipperSerial) -> None:
    print(
        "4. Probing ENABLE with CHOPCONF.toff=0 (no motor current) ...",
        flush=True,
    )
    require_safe_inputs(client, stage="pre-enable-probe")
    write_register_verified(
        client,
        REGISTER_CHOPCONF,
        CHOPCONF_SHUTDOWN,
    )
    shutdown_chopconf = read_register(client, REGISTER_CHOPCONF)
    if shutdown_chopconf.value != CHOPCONF_SHUTDOWN:
        raise BenchFailure(
            "enable probe: CHOPCONF.toff=0 readback failed; " "refusing to lower ENABLE"
        )

    client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
    time.sleep(0.05)
    require_safe_inputs(client, stage="enable probe")
    enabled_ioin = read_register(client, REGISTER_IOIN)
    require_ioin(
        enabled_ioin,
        expected_disabled=False,
        stage="enable probe",
    )

    client.send_command(f"update_digital_out oid={ENABLE_OID} value=1")
    time.sleep(0.05)
    require_safe_inputs(client, stage="post-enable-probe")
    disabled_ioin = read_register(client, REGISTER_IOIN)
    require_ioin(
        disabled_ioin,
        expected_disabled=True,
        stage="post-enable-probe",
    )
    final_chopconf = read_register(client, REGISTER_CHOPCONF)
    if final_chopconf.value != CHOPCONF_SHUTDOWN:
        raise BenchFailure("enable probe: CHOPCONF changed while toggling ENABLE")
    require_clean_status(client, stage="post-enable-probe")
    print(
        "   PASS: DRV_ENN followed GPIO2 LOW/HIGH, SPI remained healthy, "
        "and the bridge stayed off",
        flush=True,
    )


def wait_with_enable_watchdog(
    client: KlipperSerial,
    duration_s: float,
) -> None:
    wait_started = time.monotonic()
    wait_deadline = wait_started + duration_s
    next_watchdog_refresh = wait_started + WATCHDOG_REFRESH_INTERVAL_S
    while True:
        now = time.monotonic()
        if now >= wait_deadline:
            return
        wake_at = min(wait_deadline, next_watchdog_refresh)
        time.sleep(max(0.0, wake_at - now))
        now = time.monotonic()
        if now >= next_watchdog_refresh and now < wait_deadline:
            client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
            next_watchdog_refresh += WATCHDOG_REFRESH_INTERVAL_S


def run_low_current_hold(
    client: KlipperSerial,
    *,
    current: CurrentSettings,
) -> None:
    print(
        f"4. Enabling the bridge for a {LOW_CURRENT_HOLD_DURATION_S:.0f}-second "
        "low-current hold without STEP pulses ...",
        flush=True,
    )
    require_safe_inputs(client, stage="pre-low-current-hold")

    enabled_ioin: TmcResponse | None = None
    client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
    try:
        wait_with_enable_watchdog(client, LOW_CURRENT_HOLD_DURATION_S)
        enabled_ioin = read_register(client, REGISTER_IOIN)
    finally:
        disable_driver(client)

    time.sleep(0.05)
    require_safe_inputs(client, stage="post-low-current-hold")
    recovered_ioin = read_register(client, REGISTER_IOIN)
    if enabled_ioin is None:
        raise BenchFailure("low-current hold ended without an enabled IOIN response")
    try:
        require_ioin(
            enabled_ioin,
            expected_disabled=False,
            stage="low-current hold",
        )
    except BenchFailure as enabled_error:
        raise BenchFailure(
            f"{enabled_error}; after disabling, " f"IOIN={recovered_ioin.value:#010x}"
        ) from enabled_error
    require_ioin(
        recovered_ioin,
        expected_disabled=True,
        stage="post-low-current-hold",
    )
    require_clean_status(client, stage="post-low-current-hold")
    print(
        f"   PASS: held at {current.actual_run_current_a:.3f} A RMS for "
        f"{LOW_CURRENT_HOLD_DURATION_S:.1f} s; SPI remained healthy; "
        "ENABLE restored HIGH",
        flush=True,
    )


def run_low_current_step_test(
    client: KlipperSerial,
    *,
    current: CurrentSettings,
) -> None:
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    interval_ticks = round(clock_frequency / LOW_CURRENT_STEP_RATE_HZ)
    motion_duration_s = LOW_CURRENT_STEP_COUNT / LOW_CURRENT_STEP_RATE_HZ

    print(
        f"4. Holding for {LOW_CURRENT_PRE_STEP_HOLD_S:.0f} seconds, then "
        f"sending {LOW_CURRENT_STEP_COUNT} STEP pulses at "
        f"{LOW_CURRENT_STEP_RATE_HZ} pulses/s ...",
        flush=True,
    )
    require_safe_inputs(client, stage="pre-low-current-step-test")

    enabled_ioin: TmcResponse | None = None
    position: dict[str, Any] | None = None
    client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
    try:
        wait_with_enable_watchdog(
            client,
            LOW_CURRENT_PRE_STEP_HOLD_S,
        )
        clock = client.request("get_clock", "clock")["clock"]
        start_clock = (clock + round(clock_frequency * JOG_START_LEAD_S)) & 0xFFFFFFFF
        client.send_command(f"reset_step_clock oid={STEPPER_OID} clock={start_clock}")
        client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=0")
        client.send_command(
            f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
            f"count={LOW_CURRENT_STEP_COUNT} add=0"
        )
        wait_with_enable_watchdog(
            client,
            JOG_START_LEAD_S + motion_duration_s + JOG_COMPLETION_MARGIN_S,
        )
        position = client.request(
            f"stepper_get_position oid={STEPPER_OID}",
            "stepper_position",
            predicate=lambda item: item["oid"] == STEPPER_OID,
        )
        enabled_ioin = read_register(client, REGISTER_IOIN)
    finally:
        disable_driver(client)

    time.sleep(0.05)
    require_safe_inputs(client, stage="post-low-current-step-test")
    recovered_ioin = read_register(client, REGISTER_IOIN)
    if position is None or position["pos"] != LOW_CURRENT_EXPECTED_MCU_POSITION:
        actual_position = None if position is None else position["pos"]
        raise BenchFailure(
            f"MCU STEP position is {actual_position}, expected "
            f"{LOW_CURRENT_EXPECTED_MCU_POSITION}"
        )
    print(
        f"   MCU PASS: completed {LOW_CURRENT_STEP_COUNT} forward pulses "
        f"at {LOW_CURRENT_STEP_RATE_HZ} pulses/s; signed position "
        f"{position['pos']}; ENABLE restored HIGH",
        flush=True,
    )
    if enabled_ioin is None:
        raise BenchFailure(
            "low-current step test ended without an enabled IOIN response"
        )
    try:
        require_ioin(
            enabled_ioin,
            expected_disabled=False,
            stage="low-current step test",
        )
    except BenchFailure as enabled_error:
        raise BenchFailure(
            f"{enabled_error}; after disabling, " f"IOIN={recovered_ioin.value:#010x}"
        ) from enabled_error
    require_ioin(
        recovered_ioin,
        expected_disabled=True,
        stage="post-low-current-step-test",
    )
    require_clean_status(client, stage="post-low-current-step-test")
    print(
        f"   PASS: held at {current.actual_run_current_a:.3f} A RMS, "
        "moved, and retained SPI",
        flush=True,
    )


def run_full_current_reverse_test(
    client: KlipperSerial,
    *,
    current: CurrentSettings,
) -> None:
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    interval_ticks = round(clock_frequency / FULL_CURRENT_REVERSE_STEP_RATE_HZ)
    motion_duration_s = (
        FULL_CURRENT_REVERSE_STEP_COUNT * 2 / FULL_CURRENT_REVERSE_STEP_RATE_HZ
    )

    print(
        f"4. Holding for {LOW_CURRENT_PRE_STEP_HOLD_S:.0f} seconds, then "
        f"sending {FULL_CURRENT_REVERSE_STEP_COUNT} pulses forward and "
        f"{FULL_CURRENT_REVERSE_STEP_COUNT} in reverse at "
        f"{FULL_CURRENT_REVERSE_STEP_RATE_HZ} pulses/s ...",
        flush=True,
    )
    require_safe_inputs(client, stage="pre-full-current-reverse-test")

    enabled_ioin: TmcResponse | None = None
    position: dict[str, Any] | None = None
    client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
    try:
        wait_with_enable_watchdog(
            client,
            LOW_CURRENT_PRE_STEP_HOLD_S,
        )
        clock = client.request("get_clock", "clock")["clock"]
        start_clock = (clock + round(clock_frequency * JOG_START_LEAD_S)) & 0xFFFFFFFF
        client.send_command(f"reset_step_clock oid={STEPPER_OID} clock={start_clock}")
        client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=0")
        client.send_command(
            f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
            f"count={FULL_CURRENT_REVERSE_STEP_COUNT} add=0"
        )
        client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=1")
        client.send_command(
            f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
            f"count={FULL_CURRENT_REVERSE_STEP_COUNT} add=0"
        )
        wait_with_enable_watchdog(
            client,
            JOG_START_LEAD_S + motion_duration_s + JOG_COMPLETION_MARGIN_S,
        )
        position = client.request(
            f"stepper_get_position oid={STEPPER_OID}",
            "stepper_position",
            predicate=lambda item: item["oid"] == STEPPER_OID,
        )
        enabled_ioin = read_register(client, REGISTER_IOIN)
    finally:
        disable_driver(client)

    time.sleep(0.05)
    require_safe_inputs(client, stage="post-full-current-reverse-test")
    recovered_ioin = read_register(client, REGISTER_IOIN)
    if position is None or position["pos"] != 0:
        actual_position = None if position is None else position["pos"]
        raise BenchFailure(
            f"Equal forward/reverse queues ended at MCU position "
            f"{actual_position}, expected zero"
        )
    print(
        f"   MCU PASS: completed {FULL_CURRENT_REVERSE_STEP_COUNT} forward "
        f"and {FULL_CURRENT_REVERSE_STEP_COUNT} reverse pulses; signed "
        "position returned to zero; ENABLE restored HIGH",
        flush=True,
    )
    if enabled_ioin is None:
        raise BenchFailure(
            "full-current reverse test ended without an enabled IOIN response"
        )
    try:
        require_ioin(
            enabled_ioin,
            expected_disabled=False,
            stage="full-current reverse test",
        )
    except BenchFailure as enabled_error:
        raise BenchFailure(
            f"{enabled_error}; after disabling, " f"IOIN={recovered_ioin.value:#010x}"
        ) from enabled_error
    require_ioin(
        recovered_ioin,
        expected_disabled=True,
        stage="post-full-current-reverse-test",
    )
    require_clean_status(client, stage="post-full-current-reverse-test")
    print(
        f"   PASS: moved forward and back at "
        f"{current.actual_run_current_a:.3f} A RMS and retained SPI",
        flush=True,
    )


def run_repeated_motion_test(
    client: KlipperSerial,
    *,
    current: CurrentSettings,
) -> None:
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    interval_ticks = round(clock_frequency / REPEATED_MOTION_STEP_RATE_HZ)
    motion_duration_s = (
        REPEATED_MOTION_STEP_COUNT
        * 2
        * REPEATED_MOTION_CYCLES_PER_RUN
        / REPEATED_MOTION_STEP_RATE_HZ
    )
    enabled_duration_s = JOG_START_LEAD_S + motion_duration_s + JOG_COMPLETION_MARGIN_S

    print(
        f"4. Running {REPEATED_MOTION_RUNS} enable groups with no initial "
        f"hold; each group performs {REPEATED_MOTION_CYCLES_PER_RUN} "
        f"continuous cycles of {REPEATED_MOTION_STEP_COUNT} pulses forward "
        f"and {REPEATED_MOTION_STEP_COUNT} in reverse at "
        f"{REPEATED_MOTION_STEP_RATE_HZ} pulses/s ...",
        flush=True,
    )

    for run in range(1, REPEATED_MOTION_RUNS + 1):
        stage = f"repeated motion group {run}/{REPEATED_MOTION_RUNS}"
        require_safe_inputs(client, stage=f"pre-{stage}")
        write_register_verified(
            client,
            REGISTER_CHOPCONF,
            CHOPCONF_RUN,
        )

        position: dict[str, Any] | None = None
        client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
        try:
            clock = client.request("get_clock", "clock")["clock"]
            start_clock = (
                clock + round(clock_frequency * JOG_START_LEAD_S)
            ) & 0xFFFFFFFF
            client.send_command(
                f"reset_step_clock oid={STEPPER_OID} clock={start_clock}"
            )
            for _cycle in range(REPEATED_MOTION_CYCLES_PER_RUN):
                client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=0")
                client.send_command(
                    f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
                    f"count={REPEATED_MOTION_STEP_COUNT} add=0"
                )
                client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=1")
                client.send_command(
                    f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
                    f"count={REPEATED_MOTION_STEP_COUNT} add=0"
                )
            wait_with_enable_watchdog(client, enabled_duration_s)
            position = client.request(
                f"stepper_get_position oid={STEPPER_OID}",
                "stepper_position",
                predicate=lambda item: item["oid"] == STEPPER_OID,
            )
        finally:
            disable_driver(client)

        if position is None or position["pos"] != 0:
            actual_position = None if position is None else position["pos"]
            raise BenchFailure(
                f"{stage}: equal forward/reverse queues ended at MCU "
                f"position {actual_position}, expected zero"
            )
        time.sleep(0.05)
        verify_disabled_postcondition(client, stage=f"post-{stage}")
        print(
            f"   PASS group {run}/{REPEATED_MOTION_RUNS}: "
            f"{REPEATED_MOTION_CYCLES_PER_RUN} continuous cycles in "
            f"{motion_duration_s:.2f} s, MCU position zero, ENABLE HIGH, "
            "and SPI/status clean",
            flush=True,
        )

    print(
        f"   PASS: all "
        f"{REPEATED_MOTION_RUNS * REPEATED_MOTION_CYCLES_PER_RUN} "
        f"back-and-forth cycles completed in {REPEATED_MOTION_RUNS} "
        f"enable groups at {current.actual_run_current_a:.3f} A RMS",
        flush=True,
    )


def run_jog(client: KlipperSerial) -> None:
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    interval_ticks = round(clock_frequency / JOG_STEP_RATE_HZ)
    total_motion_s = JOG_STEPS * 2 / JOG_STEP_RATE_HZ

    print(
        "4. Enabling the driver for one bounded forward/reverse jog ...",
        flush=True,
    )
    require_safe_inputs(client, stage="pre-jog")
    client.send_command(f"update_digital_out oid={ENABLE_OID} value=0")
    time.sleep(0.05)
    require_safe_inputs(client, stage="enabled pre-jog")
    enabled_ioin = read_register(client, REGISTER_IOIN)
    try:
        require_ioin(
            enabled_ioin,
            expected_disabled=False,
            stage="enabled pre-jog",
        )
    except BenchFailure as enabled_error:
        client.send_command(f"update_digital_out oid={ENABLE_OID} value=1")
        time.sleep(0.05)
        require_safe_inputs(client, stage="post-enable-probe")
        recovered_ioin = read_register(client, REGISTER_IOIN)
        recovered_gstat = read_register(client, REGISTER_GSTAT)
        recovered_drv_status = read_register(client, REGISTER_DRV_STATUS)
        write_register(client, REGISTER_CHOPCONF, CHOPCONF_SHUTDOWN)
        gstat_flags = decode_flags(recovered_gstat.value, GSTAT_FLAGS)
        drv_flags = decode_flags(
            recovered_drv_status.value,
            DRV_STATUS_FLAGS,
        )
        raise BenchFailure(
            f"{enabled_error}; after immediate disable: "
            f"IOIN={recovered_ioin.value:#010x}, "
            f"GSTAT={recovered_gstat.value:#010x} "
            f"({','.join(gstat_flags) or 'none'}), "
            f"DRV_STATUS={recovered_drv_status.value:#010x} "
            f"({','.join(drv_flags) or 'none'})"
        ) from enabled_error
    require_safe_inputs(client, stage="enabled pre-jog")

    clock = client.request("get_clock", "clock")["clock"]
    start_clock = (clock + round(clock_frequency * JOG_START_LEAD_S)) & 0xFFFFFFFF
    client.send_command(f"reset_step_clock oid={STEPPER_OID} clock={start_clock}")
    client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=0")
    client.send_command(
        f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
        f"count={JOG_STEPS} add=0"
    )
    client.send_command(f"set_next_step_dir oid={STEPPER_OID} dir=1")
    client.send_command(
        f"queue_step oid={STEPPER_OID} interval={interval_ticks} "
        f"count={JOG_STEPS} add=0"
    )

    deadline = (
        time.monotonic() + JOG_START_LEAD_S + total_motion_s + JOG_COMPLETION_MARGIN_S
    )
    while time.monotonic() < deadline:
        require_safe_inputs(client, stage="jog")
        time.sleep(min(0.04, max(0.0, deadline - time.monotonic())))

    position = client.request(
        f"stepper_get_position oid={STEPPER_OID}",
        "stepper_position",
        predicate=lambda item: item["oid"] == STEPPER_OID,
    )
    disable_driver(client)
    if position["pos"] != 0:
        raise BenchFailure(
            "Equal forward/reverse queues did not return the MCU step count "
            f"to zero (position={position['pos']})"
        )
    print(
        f"   PASS: {JOG_STEPS} microsteps forward and {JOG_STEPS} backward; "
        "MCU step count returned to zero; ENABLE restored HIGH",
        flush=True,
    )


def safe_cleanup(client: KlipperSerial, *, stop_motion: bool) -> bool:
    cleanup_ok = True
    try:
        client.send_command(f"update_digital_out oid={ENABLE_OID} value=1")
    except (BenchFailure, OSError):
        cleanup_ok = False
    try:
        write_register(client, REGISTER_CHOPCONF, CHOPCONF_SHUTDOWN)
    except (BenchFailure, OSError):
        cleanup_ok = False
    if stop_motion or not cleanup_ok:
        try:
            client.send_command("emergency_stop")
        except (BenchFailure, OSError):
            cleanup_ok = False
    return cleanup_ok


def print_plan(
    device: str | None,
    *,
    mode: str,
    current: CurrentSettings,
    spi_speed_hz: int,
) -> None:
    print(
        "RP2040-Plus + TMC5160T Plus powered motor bench\n"
        f"  mode: {mode}\n"
        "  required power: MOTOR_HVIN=24 V, AUX_24V=24 V, PWR_OK=HIGH\n"
        f"  serial device: {device or 'auto-detect /dev/cu.usbmodem*'}\n"
        f"  SPI: mode {SPI_MODE}, {spi_speed_hz / 1000:g} kHz software bus\n"
        f"  current: requested {current.requested_run_current_a:.3f} A RMS, "
        f"quantized {current.actual_run_current_a:.3f} A RMS, "
        f"Rsense={SENSE_RESISTOR_OHMS:.3f} ohm\n"
        f"  microsteps: {MICROSTEPS}; STEP pulse: "
        f"{STEP_PULSE_DURATION_S * 1_000_000:.0f} us\n"
        f"  jog: {JOG_STEPS} steps forward + {JOG_STEPS} backward at "
        f"{JOG_STEP_RATE_HZ} pulses/s\n"
        f"  low-current step test: hold "
        f"{LOW_CURRENT_PRE_STEP_HOLD_S:.0f} s, then "
        f"{LOW_CURRENT_STEP_COUNT} pulses at "
        f"{LOW_CURRENT_STEP_RATE_HZ} pulses/s\n"
        f"  full-current reverse test: "
        f"{FULL_CURRENT_REVERSE_STEP_COUNT} forward + "
        f"{FULL_CURRENT_REVERSE_STEP_COUNT} reverse at "
        f"{FULL_CURRENT_REVERSE_STEP_RATE_HZ} pulses/s\n"
        f"  repeated motion test: {REPEATED_MOTION_RUNS} enable groups x "
        f"{REPEATED_MOTION_CYCLES_PER_RUN} continuous cycles, each "
        f"{REPEATED_MOTION_STEP_COUNT} forward + "
        f"{REPEATED_MOTION_STEP_COUNT} reverse at "
        f"{REPEATED_MOTION_STEP_RATE_HZ} pulses/s\n"
        f"  safety: ENABLE gpio2 idles HIGH; {ENABLE_WATCHDOG_S:.0f} s MCU "
        "watchdog; shutdown writes CHOPCONF.toff=0\n"
        "\n"
        "PHYSICAL EMERGENCY STOP: switch off the 24 V supply.\n"
        "Do not connect or disconnect the motor or ribbon while powered.\n"
        "Arming confirms the motor phase pairs were continuity-checked with "
        "power off and the motor is secured with a free shaft."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Klipper USB serial device")
    parser.add_argument("--baud", type=int, default=250000)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--msgproto", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--spi-speed-hz",
        type=int,
        default=SPI_SPEED_HZ,
        help=(
            "Software-SPI clock rate. The bench-safe range is "
            f"{MIN_SPI_SPEED_HZ}..{MAX_SPI_SPEED_HZ} Hz; default: "
            f"{SPI_SPEED_HZ}."
        ),
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help="Confirm the printed electrical and mechanical safety preconditions.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--spi-only",
        action="store_true",
        help="Verify and initialize the powered driver without enabling the motor.",
    )
    mode.add_argument(
        "--enable-probe",
        action="store_true",
        help=(
            "Toggle ENABLE with CHOPCONF.toff=0 to test logic without "
            "energizing the motor."
        ),
    )
    mode.add_argument(
        "--low-current-hold",
        action="store_true",
        help=(
            "Enable approximately 0.2 A RMS for ten seconds without "
            "sending STEP pulses."
        ),
    )
    mode.add_argument(
        "--low-current-step-test",
        action="store_true",
        help=(
            "Hold at approximately 0.2 A RMS for five seconds, then "
            "send 1,000 STEP pulses at 200 pulses/s."
        ),
    )
    mode.add_argument(
        "--full-current-reverse-test",
        action="store_true",
        help=(
            "Hold at approximately 1 A RMS, then send 2,000 forward "
            "and 2,000 reverse STEP pulses at 200 pulses/s."
        ),
    )
    mode.add_argument(
        "--repeated-motion-test",
        action="store_true",
        help=(
            "Run three groups of ten continuous fast 1.5 A forward/reverse "
            "cycles, checking SPI after every group."
        ),
    )
    mode.add_argument(
        "--jog",
        action="store_true",
        help="Run SPI checks and the fixed, bounded forward/reverse motor jog.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    requested_current_a = (
        LOW_CURRENT_HOLD_A
        if args.low_current_hold or args.low_current_step_test
        else (
            REPEATED_MOTION_CURRENT_A
            if args.repeated_motion_test
            else REQUESTED_CURRENT_A
        )
    )
    current = calculate_current_settings(requested_current_a)
    if not MIN_SPI_SPEED_HZ <= args.spi_speed_hz <= MAX_SPI_SPEED_HZ:
        parser.error(
            f"--spi-speed-hz must be between {MIN_SPI_SPEED_HZ} and "
            f"{MAX_SPI_SPEED_HZ}"
        )
    mode = (
        "jog"
        if args.jog
        else (
            "full-current forward/reverse STEP test"
            if args.full_current_reverse_test
            else (
                "three enable groups of ten continuous forward/reverse cycles"
                if args.repeated_motion_test
                else (
                    "five-second hold plus low-current STEP test"
                    if args.low_current_step_test
                    else (
                        "ten-second low-current hold"
                        if args.low_current_hold
                        else (
                            "no-current ENABLE probe"
                            if args.enable_probe
                            else "SPI diagnostics only"
                        )
                    )
                )
            )
        )
    )
    print_plan(
        args.device,
        mode=mode,
        current=current,
        spi_speed_hz=args.spi_speed_hz,
    )
    if not args.armed:
        print(
            "\nDry run only. Select --spi-only, --enable-probe, "
            "--low-current-hold, --low-current-step-test, "
            "--full-current-reverse-test, --repeated-motion-test, or --jog "
            "and add --armed "
            "after confirming the printed preconditions."
        )
        return 0
    selected_mode_count = sum(
        (
            args.spi_only,
            args.enable_probe,
            args.low_current_hold,
            args.low_current_step_test,
            args.full_current_reverse_test,
            args.repeated_motion_test,
            args.jog,
        )
    )
    if selected_mode_count != 1:
        parser.error(
            "--armed requires exactly one of --spi-only, --enable-probe, "
            "--low-current-hold, --low-current-step-test, "
            "--full-current-reverse-test, --repeated-motion-test, or --jog"
        )
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.msgproto is None:
        print(
            "Use run_rp2040plus_tmc5160t_plus_y_motor_bench.sh so the "
            "pinned Klipper protocol module is supplied.",
            file=sys.stderr,
        )
        return 2

    def terminate(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"received signal {signum}")

    signal.signal(signal.SIGTERM, terminate)

    client: KlipperSerial | None = None
    bench_configured = False
    success = False
    try:
        device = select_serial_device(args.device)
        msgproto = load_klipper_msgproto(args.msgproto)
        client = KlipperSerial(
            device=device,
            baud=args.baud,
            msgproto=msgproto,
            command_timeout_s=args.timeout,
        )
        client.identify()
        version, build_versions = client.parser.get_version_info()
        print(f"\nConnected to {device}")
        print(f"Klipper firmware: {version} ({build_versions})")
        configure_bench(client, spi_speed_hz=args.spi_speed_hz)
        bench_configured = True

        print("1. Requiring stable powered-safe inputs ...", flush=True)
        require_safe_inputs(client, stage="startup")
        time.sleep(0.05)
        require_safe_inputs(client, stage="startup")
        print("   PASS: PWR_OK=HIGH and DIAG1=LOW")

        initialize_driver(client, current=current)
        if args.jog:
            run_jog(client)
        elif args.repeated_motion_test:
            run_repeated_motion_test(client, current=current)
        elif args.full_current_reverse_test:
            run_full_current_reverse_test(client, current=current)
        elif args.low_current_step_test:
            run_low_current_step_test(client, current=current)
        elif args.low_current_hold:
            run_low_current_hold(client, current=current)
        elif args.enable_probe:
            run_enable_probe(client)
        else:
            print("4. SPI-only mode: motor remained disabled throughout.")

        disable_driver(client)
        verify_disabled_postcondition(client, stage="final")
        success = True
    except KeyboardInterrupt:
        print("\nFAIL: interrupted; restoring the hardware-safe state", file=sys.stderr)
    except (BenchFailure, OSError, ValueError) as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
    finally:
        cleanup_ok = True
        if client is not None and bench_configured:
            stop_motion = not success
            cleanup_ok = safe_cleanup(client, stop_motion=stop_motion)
            if stop_motion and cleanup_ok:
                print(
                    "Safety shutdown: Klipper emergency_stop cleared any "
                    "queued motion. Reconnect Pico USB before retrying.",
                    file=sys.stderr,
                )
            if not cleanup_ok:
                print(
                    "FAIL: normal cleanup was not acknowledged; Klipper "
                    "emergency_stop was requested. Switch off 24 V now.",
                    file=sys.stderr,
                )
        if client is not None:
            client.close()
        success = success and cleanup_ok

    if not success:
        return 1
    action = (
        "SPI diagnostics"
        if args.spi_only
        else (
            "SPI diagnostics and full-current reverse test"
            if args.full_current_reverse_test
            else (
                "SPI diagnostics and repeated motion test"
                if args.repeated_motion_test
                else (
                    "SPI diagnostics and low-current STEP test"
                    if args.low_current_step_test
                    else (
                        "SPI diagnostics and low-current hold"
                        if args.low_current_hold
                        else (
                            "SPI diagnostics and no-current ENABLE probe"
                            if args.enable_probe
                            else "SPI diagnostics and jog"
                        )
                    )
                )
            )
        )
    )
    print(
        f"\nPASS: {action} succeeded; ENABLE is HIGH and "
        "CHOPCONF.toff is zero.\n"
        "MANUAL CHECK: confirm the shaft moved a small angle in each direction "
        "and returned approximately to its starting position."
        if args.jog
        else f"\nPASS: {action} succeeded; ENABLE is HIGH and " "CHOPCONF.toff is zero."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
