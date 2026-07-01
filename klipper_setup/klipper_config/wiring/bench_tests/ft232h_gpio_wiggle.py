#!/usr/bin/env python3
"""Toggle one FT232H GPIO pin for oscilloscope checks."""

from __future__ import annotations

import argparse
import sys
import time

from pyftdi.gpio import GpioMpsseController

from ft232h_stepper_jog import FT232H_URL, PinError, parse_pin


def wiggle(*, url: str, pin_name: str, rate_hz: float, duration_s: float) -> None:
    pin = parse_pin(pin_name, url=url)
    if rate_hz <= 0:
        raise ValueError("rate_hz must be positive.")
    if duration_s <= 0:
        raise ValueError("duration_s must be positive.")

    gpio = GpioMpsseController()
    half_period_s = 0.5 / rate_hz
    deadline = time.monotonic() + duration_s
    value = 0
    edges = 0
    try:
        gpio.configure(url, direction=pin.mask, initial=0, frequency=100_000)
        while time.monotonic() < deadline:
            value = pin.mask if value == 0 else 0
            gpio.write(value)
            edges += 1
            time.sleep(half_period_s)
        gpio.write(0)
    finally:
        try:
            gpio.write(0)
        except Exception:
            pass
        gpio.close()
    print(f"Toggled {pin.name} for {duration_s:g}s at {rate_hz:g} Hz ({edges} edges).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=FT232H_URL)
    parser.add_argument("--pin", default="D5", help="FT232H GPIO pin, default D5")
    parser.add_argument("--rate-hz", type=float, default=2.0)
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--armed", action="store_true", help="Required to toggle the pin.")
    args = parser.parse_args()

    try:
        pin = parse_pin(args.pin, url=args.url)
    except PinError as exc:
        print(f"Pin error: {exc}", file=sys.stderr)
        return 2

    print(
        "FT232H GPIO wiggle\n"
        f"  pin: {pin.name} bit {pin.bit}\n"
        f"  rate: {args.rate_hz:g} Hz\n"
        f"  duration: {args.duration_s:g} s"
    )
    if not args.armed:
        print("\nDry run only. Add --armed to toggle the pin.")
        return 0

    wiggle(
        url=args.url,
        pin_name=args.pin,
        rate_hz=args.rate_hz,
        duration_s=args.duration_s,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
