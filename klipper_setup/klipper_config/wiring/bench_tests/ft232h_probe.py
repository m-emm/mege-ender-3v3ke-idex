#!/usr/bin/env python3
"""Probe an Adafruit/FTDI FT232H connected to this Mac.

This is intentionally read-only: it lists USB/serial visibility and verifies
that PyFtdi can open the FT232H interface, but it does not toggle GPIO pins or
write serial bytes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

from pyftdi.ftdi import Ftdi
from pyftdi.usbtools import UsbToolsError
from serial.tools import list_ports


FTDI_VID = 0x0403
FT232H_PID = 0x6014
FT232H_URL = "ftdi://ftdi:232h/1"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _yes_no(value: bool) -> str:
    return "OK" if value else "MISS"


def check_system_profiler() -> CheckResult:
    try:
        completed = subprocess.run(
            ["system_profiler", "SPUSBDataType"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return CheckResult("macOS USB tree", False, f"system_profiler failed: {exc}")

    text = completed.stdout
    has_vid = "Vendor ID: 0x0403" in text
    has_pid = "Product ID: 0x6014" in text
    if not (has_vid and has_pid):
        return CheckResult(
            "macOS USB tree",
            False,
            "No FT232H VID/PID pair found in system_profiler output.",
        )

    lines = text.splitlines()
    context = []
    for index, line in enumerate(lines):
        if "Product ID: 0x6014" in line:
            start = max(0, index - 1)
            end = min(len(lines), index + 8)
            context = [item.strip() for item in lines[start:end] if item.strip()]
            break
    return CheckResult("macOS USB tree", True, " | ".join(context))


def check_serial_ports() -> CheckResult:
    ports = list(list_ports.comports())
    matches = [
        port
        for port in ports
        if (port.vid == FTDI_VID and port.pid == FT232H_PID)
        or (
            "usbserial" in str(port.device)
            and port.vid in (None, FTDI_VID)
            and port.pid in (None, FT232H_PID)
        )
    ]
    if not matches:
        if ports:
            seen = ", ".join(port.device for port in ports)
            return CheckResult("serial device", False, f"No FT232H serial port. Seen: {seen}")
        return CheckResult("serial device", False, "No serial ports reported by pyserial.")

    details = []
    for port in matches:
        details.append(
            f"{port.device} vid={_hex_or_none(port.vid)} pid={_hex_or_none(port.pid)} "
            f"serial={port.serial_number or '-'} desc={port.description or '-'}"
        )
    return CheckResult("serial device", True, "; ".join(details))


def check_pyftdi_list() -> CheckResult:
    try:
        devices = Ftdi.list_devices("ftdi:///?")
    except UsbToolsError as exc:
        return CheckResult("PyFtdi list", False, str(exc))

    matches = [
        descriptor
        for descriptor, _interface in devices
        if descriptor.vid == FTDI_VID and descriptor.pid == FT232H_PID
    ]
    if not matches:
        return CheckResult("PyFtdi list", False, f"No FT232H in {len(devices)} FTDI device(s).")

    details = []
    for descriptor in matches:
        details.append(
            f"vid={descriptor.vid:#06x} pid={descriptor.pid:#06x} "
            f"bus={descriptor.bus} address={descriptor.address} "
            f"serial={_clean_usb_text(descriptor.sn) or '-'} "
            f"description={_clean_usb_text(descriptor.description) or '-'}"
        )
    return CheckResult("PyFtdi list", True, "; ".join(details))


def check_pyftdi_open(url: str) -> CheckResult:
    ftdi = Ftdi()
    try:
        ftdi.open_from_url(url)
        detail = f"opened {url}; chip={ftdi.ic_name}; max_frequency={ftdi.frequency_max:g} Hz"
        return CheckResult("PyFtdi open", True, detail)
    except Exception as exc:
        return CheckResult("PyFtdi open", False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            ftdi.close()
        except Exception:
            pass


def _hex_or_none(value: int | None) -> str:
    return "-" if value is None else f"{value:#06x}"


def _clean_usb_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isprintable() and ch != "\uffff").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=FT232H_URL,
        help=f"PyFtdi URL to open, default: {FT232H_URL}",
    )
    args = parser.parse_args()

    results = [
        check_system_profiler(),
        check_serial_ports(),
        check_pyftdi_list(),
        check_pyftdi_open(args.url),
    ]

    print("FT232H probe")
    print("============")
    for result in results:
        print(f"[{_yes_no(result.ok)}] {result.name}: {result.detail}")

    if all(result.ok for result in results):
        print("\nResult: FT232H is visible and PyFtdi can open it.")
        return 0

    print("\nResult: FT232H probe incomplete.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
