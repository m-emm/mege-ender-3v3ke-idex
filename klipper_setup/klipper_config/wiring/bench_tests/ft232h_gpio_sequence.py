#!/usr/bin/env python3
"""Hold one FT232H GPIO pin through a timed high/low sequence."""

from __future__ import annotations

import argparse
import sys
import time

from pyftdi.gpio import GpioMpsseController

from ft232h_stepper_jog import FT232H_URL, PinError, parse_pin


def parse_level(text: str) -> int:
    value = text.strip().lower()
    if value in ("1", "high", "h"):
        return 1
    if value in ("0", "low", "l"):
        return 0
    raise ValueError(f"Invalid level {text!r}; use low/high or 0/1.")


def parse_sequence(text: str) -> list[tuple[int, float]]:
    sequence: list[tuple[int, float]] = []
    for raw_segment in text.split(","):
        segment = raw_segment.strip()
        if not segment:
            continue
        try:
            level_text, duration_text = segment.split(":", 1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid sequence segment {segment!r}; expected level:seconds."
            ) from exc
        level = parse_level(level_text)
        duration_s = float(duration_text)
        if duration_s <= 0:
            raise ValueError("Sequence durations must be positive.")
        sequence.append((level, duration_s))
    if not sequence:
        raise ValueError("Sequence must contain at least one level:seconds segment.")
    return sequence


def run_sequence(*, url: str, pin_name: str, sequence: list[tuple[int, float]]) -> None:
    pin = parse_pin(pin_name, url=url)
    first_level = sequence[0][0]
    first_value = pin.mask if first_level else 0
    gpio = GpioMpsseController()
    try:
        gpio.configure(url, direction=pin.mask, initial=first_value, frequency=100_000)
        for index, (level, duration_s) in enumerate(sequence, start=1):
            value = pin.mask if level else 0
            gpio.write(value)
            print(
                f"{index}: {pin.name} {'HIGH' if level else 'LOW'} "
                f"for {duration_s:g}s",
                flush=True,
            )
            time.sleep(duration_s)
        gpio.write(pin.mask if sequence[-1][0] else 0)
    finally:
        gpio.close(freeze=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=FT232H_URL)
    parser.add_argument("--pin", default="D6", help="FT232H GPIO pin, default D6")
    parser.add_argument(
        "--sequence",
        default="low:8,high:8,low:8,high:8",
        help="Comma-separated level:seconds holds, default low:8,high:8,low:8,high:8",
    )
    parser.add_argument("--armed", action="store_true", help="Required to drive the pin.")
    args = parser.parse_args()

    try:
        pin = parse_pin(args.pin, url=args.url)
        sequence = parse_sequence(args.sequence)
    except (PinError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    print(
        "FT232H GPIO sequence\n"
        f"  pin: {pin.name} bit {pin.bit}\n"
        f"  sequence: {args.sequence}"
    )
    if not args.armed:
        print("\nDry run only. Add --armed to drive the pin.")
        return 0

    run_sequence(url=args.url, pin_name=args.pin, sequence=sequence)
    print(f"Finished; left {pin.name} {'HIGH' if sequence[-1][0] else 'LOW'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
