#!/usr/bin/env python3
"""Bench-test the RP2040-Plus/TMC5160T Plus Y interface through Klipper."""

from __future__ import annotations

import argparse
import glob
import importlib.util
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class BenchOutput:
    name: str
    oid: int
    pin: str
    idle_value: int
    endpoint: str


@dataclass(frozen=True)
class InputProbe:
    name: str
    position: int
    pin: str
    physical_pin: int
    endpoint: str

    @property
    def mask(self) -> int:
        return 1 << self.position


@dataclass(frozen=True)
class LoopbackTest:
    output_name: str
    input_masks: int
    path: str


class BenchFailure(RuntimeError):
    """A bench assertion or Klipper transport operation failed."""


OUTPUTS = (
    BenchOutput("STEP", 0, "gpio0", 0, "U1_01_1A_STEP"),
    BenchOutput("DIR", 1, "gpio1", 0, "U1_03_2A_DIR"),
    BenchOutput("ENABLE", 2, "gpio2", 1, "U1_05_3A_ENABLE"),
    BenchOutput("CS", 3, "gpio9", 1, "U1_09_4A_CS"),
    BenchOutput("SCLK", 4, "gpio10", 0, "U1_11_5A_SCLK"),
    BenchOutput("MOSI", 5, "gpio11", 0, "U1_13_6A_MOSI"),
    BenchOutput("TMC_DIAG_TEST", 6, "gpio26", 0, "C15_R20_TMC_DIAG"),
    BenchOutput("TMC_MISO_TEST", 7, "gpio27", 0, "C16_R19_TMC_MISO"),
)
OUTPUT_BY_NAME = {output.name: output for output in OUTPUTS}

OUTGOING_BUTTONS_OID = 8
RETURN_BUTTONS_OID = 9
OUTGOING_PROBES = (
    InputProbe("PWR_OK", 0, "gpio5", 7, "B19_VIO_OK"),
    InputProbe("STEP input-side", 1, "gpio17", 22, "U1_01_1A_STEP"),
    InputProbe("STEP driver-side", 2, "gpio16", 21, "C14_R13_STEP"),
    InputProbe("ENABLE driver-side", 3, "gpio18", 24, "C20_R15_ENABLE"),
    InputProbe("MOSI driver-side", 4, "gpio19", 25, "C19_R18_MOSI"),
    InputProbe("SCLK driver-side", 5, "gpio20", 26, "C18_R17_SCLK"),
    InputProbe("CS driver-side", 6, "gpio21", 27, "C17_R16_CS"),
    InputProbe("DIR driver-side", 7, "gpio22", 29, "C13_R14_DIR"),
)
RETURN_PROBES = (
    InputProbe("DIAG Pico-side", 0, "gpio3", 5, "C06_R20_PICO_DIAG"),
    InputProbe("MISO Pico-side", 1, "gpio8", 11, "C05_R19_PICO_MISO"),
)
OUTGOING_PROBE_BY_NAME = {probe.name: probe for probe in OUTGOING_PROBES}
RETURN_PROBE_BY_NAME = {probe.name: probe for probe in RETURN_PROBES}

PWR_OK_MASK = OUTGOING_PROBE_BY_NAME["PWR_OK"].mask
STEP_INPUT_MASK = OUTGOING_PROBE_BY_NAME["STEP input-side"].mask
DRIVER_SIDE_MASK = sum(
    probe.mask for probe in OUTGOING_PROBES if "driver-side" in probe.name
)
OUTGOING_INPUT_MASK = (1 << len(OUTGOING_PROBES)) - 1
RETURN_INPUT_MASK = (1 << len(RETURN_PROBES)) - 1
HV_ON_IDLE_STATE = (
    PWR_OK_MASK
    | OUTGOING_PROBE_BY_NAME["ENABLE driver-side"].mask
    | OUTGOING_PROBE_BY_NAME["CS driver-side"].mask
)

OUTGOING_TESTS = (
    LoopbackTest(
        "STEP",
        STEP_INPUT_MASK | OUTGOING_PROBE_BY_NAME["STEP driver-side"].mask,
        "gpio0 -> U1_01_1A_STEP -> C14_R13_STEP -> gpio16",
    ),
    LoopbackTest(
        "DIR",
        OUTGOING_PROBE_BY_NAME["DIR driver-side"].mask,
        "gpio1 -> U1_03_2A_DIR -> C13_R14_DIR -> gpio22",
    ),
    LoopbackTest(
        "ENABLE",
        OUTGOING_PROBE_BY_NAME["ENABLE driver-side"].mask,
        "gpio2 -> U1_05_3A_ENABLE -> C20_R15_ENABLE -> gpio18",
    ),
    LoopbackTest(
        "CS",
        OUTGOING_PROBE_BY_NAME["CS driver-side"].mask,
        "gpio9 -> U1_09_4A_CS -> C17_R16_CS -> gpio21",
    ),
    LoopbackTest(
        "SCLK",
        OUTGOING_PROBE_BY_NAME["SCLK driver-side"].mask,
        "gpio10 -> U1_11_5A_SCLK -> C18_R17_SCLK -> gpio20",
    ),
    LoopbackTest(
        "MOSI",
        OUTGOING_PROBE_BY_NAME["MOSI driver-side"].mask,
        "gpio11 -> U1_13_6A_MOSI -> C19_R18_MOSI -> gpio19",
    ),
)
RETURN_TESTS = (
    LoopbackTest(
        "TMC_DIAG_TEST",
        RETURN_PROBE_BY_NAME["DIAG Pico-side"].mask,
        "gpio26 -> C15_R20_TMC_DIAG -> R20 -> gpio3",
    ),
    LoopbackTest(
        "TMC_MISO_TEST",
        RETURN_PROBE_BY_NAME["MISO Pico-side"].mask,
        "gpio27 -> C16_R19_TMC_MISO -> R19 -> gpio8",
    ),
)

QUERY_INTERVAL_S = 0.002
CONFIG_COMMANDS = (
    "allocate_oids count=10",
    *(
        f"config_digital_out oid={output.oid} pin={output.pin} "
        f"value={output.idle_value} default_value={output.idle_value} "
        "max_duration=0"
        for output in OUTPUTS
    ),
    f"config_buttons oid={OUTGOING_BUTTONS_OID} "
    f"button_count={len(OUTGOING_PROBES)}",
    *(
        f"buttons_add oid={OUTGOING_BUTTONS_OID} pos={probe.position} "
        f"pin={probe.pin} pull_up=0"
        for probe in OUTGOING_PROBES
    ),
    f"config_buttons oid={RETURN_BUTTONS_OID} "
    f"button_count={len(RETURN_PROBES)}",
    *(
        f"buttons_add oid={RETURN_BUTTONS_OID} pos={probe.position} "
        f"pin={probe.pin} pull_up=0"
        for probe in RETURN_PROBES
    ),
)
CONFIG_CRC = zlib.crc32("\n".join(CONFIG_COMMANDS).encode()) & 0xFFFFFFFF


def describe_input_state(raw_state: int, probes: tuple[InputProbe, ...]) -> str:
    return ", ".join(
        f"{probe.name} {probe.pin}/physical-{probe.physical_pin} "
        f"<- {probe.endpoint}={int(bool(raw_state & probe.mask))}"
        for probe in probes
    )


def select_serial_device(requested_device: str | None) -> str:
    if requested_device:
        return requested_device
    candidates = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not candidates:
        raise BenchFailure(
            "No /dev/cu.usbmodem* device found. Connect the Klipper Pico or "
            "pass --device explicitly."
        )
    if len(candidates) > 1:
        raise BenchFailure(
            "Multiple USB modem devices found; pass --device explicitly: "
            + ", ".join(candidates)
        )
    return candidates[0]


def load_klipper_msgproto(path: Path) -> ModuleType:
    if not path.is_file():
        raise BenchFailure(f"Klipper msgproto.py not found: {path}")
    spec = importlib.util.spec_from_file_location("klipper_msgproto", path)
    if spec is None or spec.loader is None:
        raise BenchFailure(f"Could not load Klipper msgproto.py: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KlipperSerial:
    """Small stop-and-wait transport for native Klipper MCU messages."""

    def __init__(
        self,
        *,
        device: str,
        baud: int,
        msgproto: ModuleType,
        command_timeout_s: float,
    ) -> None:
        try:
            import serial
        except ImportError as exc:
            raise BenchFailure(
                "pyserial is required; use run_rp2040plus_tmc5160t_plus_y_bench.sh."
            ) from exc

        self.msgproto = msgproto
        self.parser = msgproto.MessageParser()
        self.command_timeout_s = command_timeout_s
        self.sequence = 0
        self.receive_buffer = bytearray()
        try:
            self.serial = serial.Serial(
                port=device,
                baudrate=baud,
                timeout=0.02,
                write_timeout=1.0,
                exclusive=True,
            )
        except (OSError, serial.SerialException) as exc:
            raise BenchFailure(f"Could not open {device}: {exc}") from exc
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()

    def close(self) -> None:
        self.serial.close()

    def _read_frame(self, deadline: float) -> bytes | None:
        while time.monotonic() < deadline:
            packet_length = self.parser.check_packet(self.receive_buffer)
            if packet_length > 0:
                frame = bytes(self.receive_buffer[:packet_length])
                del self.receive_buffer[:packet_length]
                return frame
            if packet_length < 0:
                sync_position = self.receive_buffer.find(
                    bytes((self.msgproto.MESSAGE_SYNC,))
                )
                if sync_position < 0:
                    self.receive_buffer.clear()
                else:
                    del self.receive_buffer[: sync_position + 1]
                continue
            data = self.serial.read(4096)
            if data:
                self.receive_buffer.extend(data)
        return None

    def send_command(self, command: str) -> list[dict[str, Any]]:
        encoded_command = self.parser.create_command(command)
        responses: list[dict[str, Any]] = []
        sequence = self.sequence

        for attempt in range(5):
            packet_data = [
                self.msgproto.MESSAGE_MIN + len(encoded_command),
                self.msgproto.MESSAGE_DEST
                | (sequence & self.msgproto.MESSAGE_SEQ_MASK),
                *encoded_command,
            ]
            packet_data.extend(self.msgproto.crc16_ccitt(packet_data))
            packet_data.append(self.msgproto.MESSAGE_SYNC)
            packet = bytes(packet_data)
            if attempt:
                packet = bytes((self.msgproto.MESSAGE_SYNC,)) + packet
            self.serial.write(packet)
            self.serial.flush()
            deadline = time.monotonic() + self.command_timeout_s

            while True:
                frame = self._read_frame(deadline)
                if frame is None:
                    break
                response_sequence = frame[self.msgproto.MESSAGE_POS_SEQ] & 0x0F
                if len(frame) == self.msgproto.MESSAGE_MIN:
                    expected_ack = (sequence + 1) & 0x0F
                    if response_sequence == expected_ack:
                        self.sequence = expected_ack
                        return responses
                    sequence = response_sequence
                    break
                responses.append(self.parser.parse(frame))

        raise BenchFailure(f"No Klipper acknowledgement for: {command}")

    def request(
        self,
        command: str,
        response_name: str,
        *,
        predicate: Any = None,
    ) -> dict[str, Any]:
        for _attempt in range(5):
            for response in self.send_command(command):
                if response["#name"] != response_name:
                    continue
                if predicate is None or predicate(response):
                    return response
        raise BenchFailure(
            f"No {response_name!r} response to Klipper command: {command}"
        )

    def identify(self) -> None:
        identify_data = bytearray()
        while True:
            offset = len(identify_data)
            response = self.request(
                f"identify offset={offset} count=40",
                "identify_response",
                predicate=lambda item, offset=offset: item["offset"] == offset,
            )
            chunk = response["data"]
            if not chunk:
                break
            identify_data.extend(chunk)
        parser = self.msgproto.MessageParser()
        parser.process_identify(bytes(identify_data))
        self.parser = parser

    def poll(self, duration_s: float) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        deadline = time.monotonic() + duration_s
        while True:
            frame = self._read_frame(deadline)
            if frame is None:
                return responses
            if len(frame) != self.msgproto.MESSAGE_MIN:
                responses.append(self.parser.parse(frame))


@dataclass
class ButtonReportGroup:
    oid: int
    probes: tuple[InputProbe, ...]
    input_mask: int
    ack_count: int = 0
    states: list[int] = field(default_factory=list)


class ButtonReports:
    def __init__(self, client: KlipperSerial) -> None:
        self.client = client
        self.groups = {
            OUTGOING_BUTTONS_OID: ButtonReportGroup(
                OUTGOING_BUTTONS_OID,
                OUTGOING_PROBES,
                OUTGOING_INPUT_MASK,
            ),
            RETURN_BUTTONS_OID: ButtonReportGroup(
                RETURN_BUTTONS_OID,
                RETURN_PROBES,
                RETURN_INPUT_MASK,
            ),
        }

    def accept(self, responses: list[dict[str, Any]]) -> None:
        pending = list(responses)
        while pending:
            acknowledgements: list[tuple[int, int]] = []
            for response in pending:
                if response["#name"] != "buttons_state":
                    continue
                group = self.groups.get(response["oid"])
                if group is None:
                    continue
                firmware_ack = response["ack_count"]
                ack_diff = (firmware_ack - group.ack_count) & 0xFF
                ack_diff -= (ack_diff & 0x80) << 1
                message_ack_count = group.ack_count + ack_diff
                reported_states = bytearray(response["state"])
                new_count = (
                    message_ack_count + len(reported_states) - group.ack_count
                )
                if new_count <= 0:
                    continue
                group.states.extend(reported_states[-new_count:])
                group.ack_count += new_count
                acknowledgements.append((group.oid, new_count))
            pending = []
            for oid, count in acknowledgements:
                pending.extend(
                    self.client.send_command(
                        f"buttons_ack oid={oid} count={count}"
                    )
                )

    def collect(self, duration_s: float) -> None:
        self.accept(self.client.poll(duration_s))

    def discard_pending_states(self, duration_s: float = 0.15) -> None:
        self.collect(duration_s)
        for group in self.groups.values():
            group.states.clear()

    def wait_for(
        self,
        expected_state: int,
        timeout_s: float,
        *,
        oid: int,
        fixed_mask: int,
        fixed_value: int,
    ) -> None:
        group = self.groups[oid]
        last_state: int | None = None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.collect(min(0.05, deadline - time.monotonic()))
            while group.states:
                raw_state = group.states.pop(0) & group.input_mask
                last_state = raw_state
                if raw_state & fixed_mask != fixed_value:
                    raise BenchFailure(
                        "A fixed input has the wrong state: "
                        + describe_input_state(raw_state, group.probes)
                    )
                if raw_state == expected_state:
                    return
        expected_description = describe_input_state(expected_state, group.probes)
        last_description = (
            describe_input_state(last_state, group.probes)
            if last_state is not None
            else "no state received"
        )
        raise BenchFailure(
            f"Timed out waiting for {expected_description}; "
            f"last observed: {last_description}"
        )

    def assert_quiet(
        self,
        duration_s: float,
        expected_state: int,
        *,
        oid: int,
    ) -> None:
        group = self.groups[oid]
        self.collect(duration_s)
        while group.states:
            raw_state = group.states.pop(0) & group.input_mask
            if raw_state != expected_state:
                raise BenchFailure(
                    "An input changed after reaching the expected state: "
                    + describe_input_state(raw_state, group.probes)
                )


def update_output(
    client: KlipperSerial,
    output: BenchOutput,
    value: int,
    reports: ButtonReports | None = None,
) -> None:
    responses = client.send_command(
        f"update_digital_out oid={output.oid} value={value}"
    )
    if reports is not None:
        reports.accept(responses)


def restore_idle_outputs(client: KlipperSerial) -> None:
    for output in OUTPUTS:
        update_output(client, output, output.idle_value)


def configure_bench(client: KlipperSerial) -> None:
    config = client.request("get_config", "config")
    if config["is_shutdown"]:
        raise BenchFailure("The Klipper MCU is in shutdown state; reconnect USB.")
    if config["is_config"]:
        if config["crc"] != CONFIG_CRC:
            raise BenchFailure(
                "The MCU already has a different Klipper configuration "
                f"(crc={config['crc']}, bench crc={CONFIG_CRC}). Reconnect USB "
                "to reset it, then rerun this bench test."
            )
    else:
        for command in CONFIG_COMMANDS:
            client.send_command(command)
        client.send_command(f"finalize_config crc={CONFIG_CRC}")

    restore_idle_outputs(client)
    clock_response = client.request("get_clock", "clock")
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    start_clock = (clock_response["clock"] + int(clock_frequency * 0.05)) & 0xFFFFFFFF
    rest_ticks = int(clock_frequency * QUERY_INTERVAL_S)
    for oid, input_mask in (
        (OUTGOING_BUTTONS_OID, OUTGOING_INPUT_MASK),
        (RETURN_BUTTONS_OID, RETURN_INPUT_MASK),
    ):
        client.send_command(
            f"buttons_query oid={oid} clock={start_clock} "
            f"rest_ticks={rest_ticks} retransmit_count=50 invert={input_mask}"
        )


def wait_for_outgoing_state(
    reports: ButtonReports,
    expected_state: int,
    timeout_s: float,
    *,
    pwr_ok: bool,
) -> None:
    reports.wait_for(
        expected_state,
        timeout_s,
        oid=OUTGOING_BUTTONS_OID,
        fixed_mask=PWR_OK_MASK,
        fixed_value=PWR_OK_MASK if pwr_ok else 0,
    )
    reports.assert_quiet(
        0.05,
        expected_state,
        oid=OUTGOING_BUTTONS_OID,
    )


def wait_for_return_state(
    reports: ButtonReports,
    expected_state: int,
    timeout_s: float,
) -> None:
    reports.wait_for(
        expected_state,
        timeout_s,
        oid=RETURN_BUTTONS_OID,
        fixed_mask=0,
        fixed_value=0,
    )
    reports.assert_quiet(
        0.05,
        expected_state,
        oid=RETURN_BUTTONS_OID,
    )


def run_no_hv_test(client: KlipperSerial, timeout_s: float) -> None:
    reports = ButtonReports(client)
    fixed_mask = PWR_OK_MASK | DRIVER_SIDE_MASK
    print(
        "1. Synchronizing reports and checking the safe idle state ...",
        flush=True,
    )
    reports.discard_pending_states()
    update_output(client, OUTPUT_BY_NAME["STEP"], 1, reports)
    reports.wait_for(
        STEP_INPUT_MASK,
        timeout_s,
        oid=OUTGOING_BUTTONS_OID,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    update_output(client, OUTPUT_BY_NAME["STEP"], 0, reports)
    reports.wait_for(
        0,
        timeout_s,
        oid=OUTGOING_BUTTONS_OID,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    update_output(client, OUTPUT_BY_NAME["TMC_DIAG_TEST"], 1, reports)
    wait_for_return_state(
        reports,
        RETURN_PROBE_BY_NAME["DIAG Pico-side"].mask,
        timeout_s,
    )
    update_output(client, OUTPUT_BY_NAME["TMC_DIAG_TEST"], 0, reports)
    wait_for_return_state(reports, 0, timeout_s)
    print("   PASS: PWR_OK and all driver-side/return probes are LOW")

    print("2. STEP HIGH: checking the physical-pin-22 probe follows ...", flush=True)
    update_output(client, OUTPUT_BY_NAME["STEP"], 1, reports)
    reports.wait_for(
        STEP_INPUT_MASK,
        timeout_s,
        oid=OUTGOING_BUTTONS_OID,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    reports.assert_quiet(0.05, STEP_INPUT_MASK, oid=OUTGOING_BUTTONS_OID)
    reports.assert_quiet(0.05, 0, oid=RETURN_BUTTONS_OID)
    print("   PASS: input-side STEP=HIGH while all driver-side probes remain LOW")

    print("3. STEP LOW: checking the physical-pin-22 probe returns LOW ...", flush=True)
    update_output(client, OUTPUT_BY_NAME["STEP"], 0, reports)
    reports.wait_for(
        0,
        timeout_s,
        oid=OUTGOING_BUTTONS_OID,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    reports.assert_quiet(0.05, 0, oid=OUTGOING_BUTTONS_OID)
    reports.assert_quiet(0.05, 0, oid=RETURN_BUTTONS_OID)
    print("   PASS: input-side STEP returned LOW; driver-side probes stayed LOW")


def run_hv_on_test(client: KlipperSerial, timeout_s: float) -> None:
    reports = ButtonReports(client)
    print(
        "1. Synchronizing reports and checking the safe idle state ...",
        flush=True,
    )
    reports.discard_pending_states()
    update_output(client, OUTPUT_BY_NAME["STEP"], 1, reports)
    wait_for_outgoing_state(
        reports,
        HV_ON_IDLE_STATE
        ^ (
            STEP_INPUT_MASK
            | OUTGOING_PROBE_BY_NAME["STEP driver-side"].mask
        ),
        timeout_s,
        pwr_ok=True,
    )
    update_output(client, OUTPUT_BY_NAME["STEP"], 0, reports)
    wait_for_outgoing_state(
        reports,
        HV_ON_IDLE_STATE,
        timeout_s,
        pwr_ok=True,
    )
    update_output(client, OUTPUT_BY_NAME["TMC_DIAG_TEST"], 1, reports)
    wait_for_return_state(
        reports,
        RETURN_PROBE_BY_NAME["DIAG Pico-side"].mask,
        timeout_s,
    )
    update_output(client, OUTPUT_BY_NAME["TMC_DIAG_TEST"], 0, reports)
    wait_for_return_state(reports, 0, timeout_s)
    print(
        "   PASS: PWR_OK=HIGH; ENABLE/CS=HIGH; "
        "STEP/DIR/SCLK/MOSI and both returns=LOW"
    )

    test_number = 2
    for loopback in OUTGOING_TESTS:
        output = OUTPUT_BY_NAME[loopback.output_name]
        toggled_value = 1 - output.idle_value
        expected_state = HV_ON_IDLE_STATE ^ loopback.input_masks
        print(
            f"{test_number}. {output.name}: driving {output.idle_value} -> "
            f"{toggled_value} and checking only its loopback changes ...",
            flush=True,
        )
        update_output(client, output, toggled_value, reports)
        wait_for_outgoing_state(
            reports,
            expected_state,
            timeout_s,
            pwr_ok=True,
        )
        reports.assert_quiet(0.05, 0, oid=RETURN_BUTTONS_OID)
        print(f"   PASS: {loopback.path}")

        update_output(client, output, output.idle_value, reports)
        wait_for_outgoing_state(
            reports,
            HV_ON_IDLE_STATE,
            timeout_s,
            pwr_ok=True,
        )
        print(f"   PASS: {output.name} returned to safe idle")
        test_number += 1

    for loopback in RETURN_TESTS:
        output = OUTPUT_BY_NAME[loopback.output_name]
        print(
            f"{test_number}. {output.name}: driving its TMC-side probe HIGH "
            "and checking only the intended Pico input changes ...",
            flush=True,
        )
        update_output(client, output, 1, reports)
        wait_for_return_state(reports, loopback.input_masks, timeout_s)
        reports.assert_quiet(
            0.05,
            HV_ON_IDLE_STATE,
            oid=OUTGOING_BUTTONS_OID,
        )
        print(f"   PASS: {loopback.path}")

        update_output(client, output, output.idle_value, reports)
        wait_for_return_state(reports, 0, timeout_s)
        print(f"   PASS: {output.name} returned LOW")
        test_number += 1

    reports.assert_quiet(
        0.05,
        HV_ON_IDLE_STATE,
        oid=OUTGOING_BUTTONS_OID,
    )
    reports.assert_quiet(0.05, 0, oid=RETURN_BUTTONS_OID)


def print_plan(device: str | None, *, hv_on: bool) -> None:
    power_state = "ON; VIO and PWR_OK must be HIGH" if hv_on else "OFF"
    outgoing_expectation = (
        "each selected driver-side probe follows its source alone"
        if hv_on
        else "all driver-side probes remain LOW"
    )
    outgoing_lines = "\n".join(
        f"    {loopback.path}" for loopback in OUTGOING_TESTS
    )
    return_lines = "\n".join(f"    {loopback.path}" for loopback in RETURN_TESTS)
    print(
        "RP2040-Plus + TMC5160T Plus Y bench test\n"
        f"  expected HV state: {power_state}\n"
        f"  serial device: {device or 'auto-detect /dev/cu.usbmodem*'}\n"
        f"  outgoing expectation: {outgoing_expectation}\n"
        f"{outgoing_lines}\n"
        "  protected return loopbacks:\n"
        f"{return_lines}\n"
        "  safe idle: STEP/DIR/SCLK/MOSI/return sources LOW; "
        "ENABLE and CS HIGH"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Klipper USB serial device")
    parser.add_argument("--baud", type=int, default=250000)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument(
        "--hv-on",
        action="store_true",
        help=(
            "Expect powered VIO and test all outgoing and protected-return "
            "loopbacks."
        ),
    )
    parser.add_argument(
        "--msgproto",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help=(
            "Confirm the selected power state and allow the script to toggle "
            "the listed GPIOs."
        ),
    )
    args = parser.parse_args()

    print_plan(args.device, hv_on=args.hv_on)
    if not args.armed:
        print("\nDry run only. Confirm the expected power state, then add --armed.")
        return 0
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.msgproto is None:
        print(
            "Use run_rp2040plus_tmc5160t_plus_y_bench.sh so the pinned "
            "Klipper protocol module is supplied.",
            file=sys.stderr,
        )
        return 2

    client: KlipperSerial | None = None
    bench_configured = False
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
        configure_bench(client)
        bench_configured = True
        if args.hv_on:
            run_hv_on_test(client, args.timeout)
        else:
            run_no_hv_test(client, args.timeout)
    except (BenchFailure, OSError) as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if client is not None and bench_configured:
            try:
                restore_idle_outputs(client)
            except BenchFailure:
                pass
        if client is not None:
            client.close()

    power_label = "HV-on" if args.hv_on else "no-HV"
    print(
        f"\nPASS: all {power_label} bench assertions succeeded; "
        "all outputs were restored to safe idle."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
