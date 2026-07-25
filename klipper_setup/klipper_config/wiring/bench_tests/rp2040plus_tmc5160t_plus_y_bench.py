#!/usr/bin/env python3
"""Bench-test the RP2040-Plus/TMC5160T Plus Y interface through Klipper."""

from __future__ import annotations

import argparse
import glob
import importlib.util
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

STEP_OUTPUT_PIN = "gpio0"
PWR_OK_INPUT_PIN = "gpio5"
STEP_INPUT_PIN = "gpio17"
STEP_INPUT_PHYSICAL_PIN = 22
DRIVER_STEP_INPUT_PIN = "gpio16"
DRIVER_STEP_INPUT_PHYSICAL_PIN = 21

DIGITAL_OUT_OID = 0
BUTTONS_OID = 1
INPUT_MASK = 0b111
PWR_OK_MASK = 0b001
STEP_INPUT_MASK = 0b010
DRIVER_STEP_MASK = 0b100
NO_HV_STEP_LOW_STATE = 0
NO_HV_STEP_HIGH_STATE = STEP_INPUT_MASK
HV_ON_STEP_LOW_STATE = PWR_OK_MASK
HV_ON_STEP_HIGH_STATE = PWR_OK_MASK | STEP_INPUT_MASK | DRIVER_STEP_MASK
QUERY_INTERVAL_S = 0.002
CONFIG_COMMANDS = (
    "allocate_oids count=2",
    "config_digital_out oid=0 pin=gpio0 value=0 default_value=0 max_duration=0",
    "config_buttons oid=1 button_count=3",
    "buttons_add oid=1 pos=0 pin=gpio5 pull_up=0",
    "buttons_add oid=1 pos=1 pin=gpio17 pull_up=0",
    "buttons_add oid=1 pos=2 pin=gpio16 pull_up=0",
)
CONFIG_CRC = zlib.crc32("\n".join(CONFIG_COMMANDS).encode()) & 0xFFFFFFFF


class BenchFailure(RuntimeError):
    """A bench assertion or Klipper transport operation failed."""


@dataclass(frozen=True)
class InputState:
    pwr_ok: bool
    step_input: bool
    driver_step: bool


def decode_input_state(raw_state: int) -> InputState:
    return InputState(
        pwr_ok=bool(raw_state & PWR_OK_MASK),
        step_input=bool(raw_state & STEP_INPUT_MASK),
        driver_step=bool(raw_state & DRIVER_STEP_MASK),
    )


def describe_input_state(raw_state: int) -> str:
    state = decode_input_state(raw_state)
    return (
        f"PWR_OK={int(state.pwr_ok)}, "
        f"STEP probe {STEP_INPUT_PIN}/physical-{STEP_INPUT_PHYSICAL_PIN}="
        f"{int(state.step_input)}, "
        f"driver STEP {DRIVER_STEP_INPUT_PIN}/physical-"
        f"{DRIVER_STEP_INPUT_PHYSICAL_PIN}={int(state.driver_step)}"
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


class ButtonReports:
    def __init__(self, client: KlipperSerial) -> None:
        self.client = client
        self.ack_count = 0
        self.states: list[int] = []

    def accept(self, responses: list[dict[str, Any]]) -> None:
        pending = list(responses)
        while pending:
            acknowledgements: list[int] = []
            for response in pending:
                if (
                    response["#name"] != "buttons_state"
                    or response["oid"] != BUTTONS_OID
                ):
                    continue
                firmware_ack = response["ack_count"]
                ack_diff = (firmware_ack - self.ack_count) & 0xFF
                ack_diff -= (ack_diff & 0x80) << 1
                message_ack_count = self.ack_count + ack_diff
                reported_states = bytearray(response["state"])
                new_count = message_ack_count + len(reported_states) - self.ack_count
                if new_count <= 0:
                    continue
                self.states.extend(reported_states[-new_count:])
                self.ack_count += new_count
                acknowledgements.append(new_count)
            pending = []
            for count in acknowledgements:
                pending.extend(
                    self.client.send_command(
                        f"buttons_ack oid={BUTTONS_OID} count={count}"
                    )
                )

    def collect(self, duration_s: float) -> None:
        self.accept(self.client.poll(duration_s))

    def wait_for(
        self,
        expected_state: int,
        timeout_s: float,
        *,
        fixed_mask: int,
        fixed_value: int,
    ) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.collect(min(0.05, deadline - time.monotonic()))
            while self.states:
                raw_state = self.states.pop(0) & INPUT_MASK
                if raw_state & fixed_mask != fixed_value:
                    raise BenchFailure(
                        "A fixed input has the wrong state: "
                        + describe_input_state(raw_state)
                    )
                if raw_state == expected_state:
                    return
        raise BenchFailure(
            "Timed out waiting for " + describe_input_state(expected_state)
        )

    def assert_quiet(self, duration_s: float, expected_state: int) -> None:
        self.collect(duration_s)
        while self.states:
            raw_state = self.states.pop(0) & INPUT_MASK
            if raw_state != expected_state:
                raise BenchFailure(
                    "An input changed after reaching the expected state: "
                    + describe_input_state(raw_state)
                )


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

    client.send_command(f"update_digital_out oid={DIGITAL_OUT_OID} value=0")
    clock_response = client.request("get_clock", "clock")
    clock_frequency = client.parser.get_constant_int("CLOCK_FREQ")
    start_clock = (clock_response["clock"] + int(clock_frequency * 0.05)) & 0xFFFFFFFF
    rest_ticks = int(clock_frequency * QUERY_INTERVAL_S)
    client.send_command(
        f"buttons_query oid={BUTTONS_OID} clock={start_clock} "
        f"rest_ticks={rest_ticks} retransmit_count=50 invert={INPUT_MASK}"
    )


def run_no_hv_test(client: KlipperSerial, timeout_s: float) -> None:
    reports = ButtonReports(client)
    fixed_mask = PWR_OK_MASK | DRIVER_STEP_MASK
    print("1. STEP LOW: checking all three inputs are LOW ...", flush=True)
    reports.wait_for(
        NO_HV_STEP_LOW_STATE,
        timeout_s,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    reports.assert_quiet(0.05, NO_HV_STEP_LOW_STATE)
    print("   PASS: PWR_OK=LOW, STEP probe=LOW, driver STEP=LOW")

    print("2. STEP HIGH: checking the physical-pin-22 probe follows ...", flush=True)
    reports.accept(
        client.send_command(f"update_digital_out oid={DIGITAL_OUT_OID} value=1")
    )
    reports.wait_for(
        NO_HV_STEP_HIGH_STATE,
        timeout_s,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    reports.assert_quiet(0.05, NO_HV_STEP_HIGH_STATE)
    print("   PASS: STEP probe=HIGH while PWR_OK and driver STEP remain LOW")

    print("3. STEP LOW: checking the physical-pin-22 probe returns LOW ...", flush=True)
    reports.accept(
        client.send_command(f"update_digital_out oid={DIGITAL_OUT_OID} value=0")
    )
    reports.wait_for(
        NO_HV_STEP_LOW_STATE,
        timeout_s,
        fixed_mask=fixed_mask,
        fixed_value=0,
    )
    reports.assert_quiet(0.05, NO_HV_STEP_LOW_STATE)
    print("   PASS: STEP probe returned LOW; driver STEP stayed LOW")


def run_hv_on_test(client: KlipperSerial, timeout_s: float) -> None:
    reports = ButtonReports(client)
    print(
        "1. STEP LOW: checking VIO is up and both STEP probes are LOW ...", flush=True
    )
    reports.wait_for(
        HV_ON_STEP_LOW_STATE,
        timeout_s,
        fixed_mask=PWR_OK_MASK,
        fixed_value=PWR_OK_MASK,
    )
    reports.assert_quiet(0.05, HV_ON_STEP_LOW_STATE)
    print("   PASS: PWR_OK=HIGH, STEP probe=LOW, driver STEP=LOW")

    print("2. STEP HIGH: checking STEP reaches both temporary probes ...", flush=True)
    reports.accept(
        client.send_command(f"update_digital_out oid={DIGITAL_OUT_OID} value=1")
    )
    reports.wait_for(
        HV_ON_STEP_HIGH_STATE,
        timeout_s,
        fixed_mask=PWR_OK_MASK,
        fixed_value=PWR_OK_MASK,
    )
    reports.assert_quiet(0.05, HV_ON_STEP_HIGH_STATE)
    print("   PASS: PWR_OK=HIGH and STEP is HIGH on gpio17 and gpio16")

    print("3. STEP LOW: checking both temporary probes return LOW ...", flush=True)
    reports.accept(
        client.send_command(f"update_digital_out oid={DIGITAL_OUT_OID} value=0")
    )
    reports.wait_for(
        HV_ON_STEP_LOW_STATE,
        timeout_s,
        fixed_mask=PWR_OK_MASK,
        fixed_value=PWR_OK_MASK,
    )
    reports.assert_quiet(0.05, HV_ON_STEP_LOW_STATE)
    print("   PASS: PWR_OK stayed HIGH; gpio17 and gpio16 returned LOW")


def print_plan(device: str | None, *, hv_on: bool) -> None:
    power_state = "ON; VIO and PWR_OK must be HIGH" if hv_on else "OFF"
    driver_step_assertion = "follows STEP" if hv_on else "always LOW"
    print(
        "RP2040-Plus + TMC5160T Plus Y bench test\n"
        f"  expected HV state: {power_state}\n"
        f"  serial device: {device or 'auto-detect /dev/cu.usbmodem*'}\n"
        f"  drive: {STEP_OUTPUT_PIN} -> U1_01_1A_STEP\n"
        f"  assert {'HIGH' if hv_on else 'LOW'}: "
        f"{PWR_OK_INPUT_PIN} <- B19_R6_VIO_OK\n"
        f"  assert follows STEP: {STEP_INPUT_PIN} (physical pin "
        f"{STEP_INPUT_PHYSICAL_PIN}) <- U1_01_1A_STEP\n"
        f"  assert {driver_step_assertion}: {DRIVER_STEP_INPUT_PIN} (physical pin "
        f"{DRIVER_STEP_INPUT_PHYSICAL_PIN}) <- C14_R13_STEP"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Klipper USB serial device")
    parser.add_argument("--baud", type=int, default=250000)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument(
        "--hv-on",
        action="store_true",
        help="Expect powered VIO, HIGH PWR_OK, and STEP propagation to gpio16.",
    )
    parser.add_argument(
        "--msgproto",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help="Confirm the selected power state and allow the script to drive gpio0.",
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
                client.send_command(f"update_digital_out oid={DIGITAL_OUT_OID} value=0")
            except BenchFailure:
                pass
        if client is not None:
            client.close()

    power_label = "HV-on" if args.hv_on else "no-HV"
    print(f"\nPASS: all {power_label} bench assertions succeeded; STEP was left LOW.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
