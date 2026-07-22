#!/usr/bin/env python3
"""Continuously try a raw BTT Eddy Duo LDC1612 measurement over USB."""

from __future__ import annotations

import argparse
import glob
import sys
import time
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
KLIPPY_DIR = SCRIPT_DIR / "klipper" / "klippy"
sys.path.insert(0, str(KLIPPY_DIR))

try:
    import serial
    import msgproto
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Run this with klipper_setup/rp2040_firmware/katapult_venv/bin/python "
        "after the local Klipper source and flashing-helper venv have been set up."
    ) from exc


LDC1612_ADDRESS = 0x2A
LDC1612_MANUFACTURER_ID = 0x5449
LDC1612_DEVICE_ID = 0x3055
LDC1612_FREQUENCY_SCALE = 12_000_000 * 2 / (1 << 28)
CALIBRATION_ZERO_MM_HZ = (3_349_907.488 + 3_348_362.535) / 2
CALIBRATION_FIVE_MM_HZ = (3_212_084.860 + 3_213_660.389) / 2

MEASUREMENTS_PER_SECOND= 2

class I2CError(Exception):
    def __init__(self, status: str):
        super().__init__(status)
        self.status = status


class KlipperUSB:
    def __init__(self, device: str):
        self.serial = serial.Serial(device, 250_000, timeout=0.01)
        self.parser = msgproto.MessageParser()
        self.sequence = 0
        self.buffer = bytearray()
        self._identify()

    @staticmethod
    def _frame(sequence: int, command: list[int]) -> bytes:
        frame = [5 + len(command), (sequence & 0x0F) | 0x10, *command]
        frame.extend(msgproto.crc16_ccitt(frame))
        frame.append(0x7E)
        return bytes(frame)

    def _send(self, command: str) -> None:
        encoded = self.parser.create_command(command)
        self.serial.write(self._frame(self.sequence, encoded))
        self.serial.flush()
        self.sequence = (self.sequence + 1) & 0x0F

    def _read_packet(self, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            packet_length = self.parser.check_packet(self.buffer)
            if packet_length > 0:
                packet = bytes(self.buffer[:packet_length])
                del self.buffer[:packet_length]
                return packet
            if packet_length < 0:
                del self.buffer[0]
                continue
            incoming = self.serial.read(self.serial.in_waiting or 1)
            self.buffer.extend(incoming)
        raise TimeoutError("Timed out waiting for the Eddy")

    def _read_response(self, name: str, timeout: float = 1.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            packet = self._read_packet(deadline - time.monotonic())
            if len(packet) == 5:  # ACK packet
                continue
            response = self.parser.parse(packet)
            if response["#name"] == name:
                return response
        raise TimeoutError(f"Timed out waiting for {name}")

    def request(self, command: str, response: str) -> dict:
        self._send(command)
        return self._read_response(response)

    def _identify(self) -> None:
        first_chunk = None
        for sequence in range(16):
            self.sequence = sequence
            self._send("identify offset=0 count=40")
            try:
                first_chunk = self._read_response("identify_response", 0.15)
                break
            except TimeoutError:
                continue
        if first_chunk is None:
            raise TimeoutError("The USB device did not answer Klipper identify")

        identify_data = bytearray(first_chunk["data"])
        chunk = first_chunk["data"]
        while len(chunk) == 40:
            response = self.request(
                f"identify offset={len(identify_data)} count=40",
                "identify_response",
            )
            chunk = response["data"]
            identify_data.extend(chunk)
        self.parser.process_identify(bytes(identify_data))

    def configure_i2c(self, speed: int, software_i2c: bool, address: int) -> None:
        if software_i2c:
            clock_frequency = self.parser.get_constant_int("CLOCK_FREQ")
            pulse_ticks = max(1, round(clock_frequency / speed / 2))
            bus_command = (
                "i2c_set_sw_bus oid=0 scl_pin=gpio21 sda_pin=gpio20 "
                f"pulse_ticks={pulse_ticks} address={address}"
            )
        else:
            bus_command = (
                f"i2c_set_bus oid=0 i2c_bus=i2c0f rate={speed} "
                f"address={address}"
            )
        for command in (
            "allocate_oids count=1",
            "config_i2c oid=0",
            bus_command,
            "finalize_config crc=0",
        ):
            self._send(command)
            time.sleep(0.02)

    def transfer(self, write: bytes, read_length: int = 0) -> bytes:
        response = self.request(
            f"i2c_transfer oid=0 write={write.hex()} read_len={read_length}",
            "i2c_response",
        )
        if response["i2c_bus_status"] != "SUCCESS":
            raise I2CError(response["i2c_bus_status"])
        return response["response"]

    def read_register(self, register: int) -> int:
        response = self.transfer(bytes([register]), 2)
        return int.from_bytes(response, "big")

    def write_register(self, register: int, value: int) -> None:
        self.transfer(bytes([register, value >> 8, value & 0xFF]))

    def reset_and_close(self) -> None:
        try:
            if self.serial.is_open:
                self._send("reset")
                time.sleep(0.1)
        except (serial.SerialException, OSError):
            pass
        finally:
            self.serial.close()

    def close(self) -> None:
        self.serial.close()


def find_device(requested_device: str | None) -> str:
    if requested_device:
        return requested_device
    devices = sorted(glob.glob("/dev/cu.usbmodem*"))
    if len(devices) != 1:
        raise SystemExit(
            f"Found {len(devices)} /dev/cu.usbmodem devices; pass --device explicitly."
        )
    return devices[0]


def initialize_ldc1612(eddy: KlipperUSB) -> None:
    for register, value in (
        (0x08, 0x0753),  # conversion count: 400 samples/second
        (0x0C, 0x0000),
        (0x10, 0x0EA6),
        (0x14, 0x2001),
        (0x19, 0xF801),
        (0x1B, 0x020D),
        (0x1A, 0x1601),
        (0x1E, 0x7800),
    ):
        eddy.write_register(register, value)


def frequency_to_distance_mm(frequency_hz: float) -> float:
    return 5 * (CALIBRATION_ZERO_MM_HZ - frequency_hz) / (
        CALIBRATION_ZERO_MM_HZ - CALIBRATION_FIVE_MM_HZ
    )


def measure(eddy: KlipperUSB, initialized: bool) -> bool:
    manufacturer_id = eddy.read_register(0x7E)
    device_id = eddy.read_register(0x7F)
    if (manufacturer_id, device_id) != (
        LDC1612_MANUFACTURER_ID,
        LDC1612_DEVICE_ID,
    ):
        print(
            f"INVALID_ID: got 0x{manufacturer_id:04x},0x{device_id:04x}; "
            "expected 0x5449,0x3055",
            flush=True,
        )
        return initialized

    if not initialized:
        initialize_ldc1612(eddy)
        initialized = True
        time.sleep(0.05)

    status = eddy.read_register(0x18)
    raw = (eddy.read_register(0x00) << 16) | eddy.read_register(0x01)
    frequency_hz = (raw & 0x0FFFFFFF) * LDC1612_FREQUENCY_SCALE
    distance_mm = frequency_to_distance_mm(frequency_hz)
    print(
        f"OK: distance={distance_mm:.2f} mm raw=0x{raw:08x} "
        f"status=0x{status:04x}",
        flush=True,
    )
    return initialized


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--device", help="USB serial device to use")
    argument_parser.add_argument(
        "--i2c-speed",
        type=int,
        default=400_000,
        help="internal LDC1612 I2C speed in Hz (default: 400000)",
    )
    argument_parser.add_argument(
        "--i2c-address",
        type=lambda value: int(value, 0),
        default=LDC1612_ADDRESS,
        help="internal LDC1612 7-bit address (default: 0x2a)",
    )
    argument_parser.add_argument(
        "--software-i2c",
        action="store_true",
        help="bit-bang gpio21/gpio20 instead of using RP2040 hardware I2C",
    )
    args = argument_parser.parse_args()
    if args.i2c_speed <= 0:
        argument_parser.error("--i2c-speed must be positive")
    if not 0 <= args.i2c_address <= 0x7F:
        argument_parser.error("--i2c-address must be a 7-bit address")

    device = find_device(args.device)
    eddy = KlipperUSB(device)
    owns_configuration = False
    try:
        config = eddy.request("get_config", "config")
        if config["is_config"]:
            raise SystemExit(
                "The Eddy is already configured by another process; disconnect it "
                "there or unplug/replug it before running this bench test."
            )
        owns_configuration = True
        eddy.configure_i2c(
            args.i2c_speed,
            args.software_i2c,
            args.i2c_address,
        )
        i2c_mode = "software gpio21/gpio20" if args.software_i2c else "hardware i2c0f"
        print(
            f"Connected to {device} ({eddy.parser.version}); "
            f"{i2c_mode} at {args.i2c_speed} Hz, address "
            f"0x{args.i2c_address:02x}; Ctrl-C stops."
        )

        initialized = False
        while True:
            timestamp = datetime.now().isoformat(timespec="seconds")
            print(f"{timestamp} ", end="", flush=True)
            try:
                initialized = measure(eddy, initialized)
            except I2CError as exc:
                print(f"NACK: {exc.status}", flush=True)
            time.sleep(1/MEASUREMENTS_PER_SECOND)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if owns_configuration:
            eddy.reset_and_close()
        else:
            eddy.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
