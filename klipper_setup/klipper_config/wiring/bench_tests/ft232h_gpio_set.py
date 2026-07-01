#!/usr/bin/env python3
"""Set one FT232H GPIO output high or low and leave it there."""

from __future__ import annotations

import argparse
import sys

from pyftdi.gpio import GpioMpsseController

from ft232h_stepper_jog import FT232H_URL, PinError, parse_pin


def set_gpio(*, url: str, pin_name: str, level: int) -> None:
    pin = parse_pin(pin_name, url=url)
    value = pin.mask if level else 0
    gpio = GpioMpsseController()
    try:
        gpio.configure(url, direction=pin.mask, initial=value, frequency=100_000)
        gpio.write(value)
    finally:
        # Keep the FTDI output latch in its current state after this process exits.
        gpio.close(freeze=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=FT232H_URL)
    parser.add_argument("--pin", default="D4", help="FT232H GPIO pin, default D4")
    parser.add_argument(
        "--level",
        choices=("0", "1", "low", "high"),
        required=True,
        help="Output level to hold.",
    )
    args = parser.parse_args()

    level = 1 if args.level in ("1", "high") else 0
    try:
        pin = parse_pin(args.pin, url=args.url)
        set_gpio(url=args.url, pin_name=args.pin, level=level)
    except PinError as exc:
        print(f"Pin error: {exc}", file=sys.stderr)
        return 2
    print(f"Set {pin.name} {'HIGH' if level else 'LOW'} and left it latched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
