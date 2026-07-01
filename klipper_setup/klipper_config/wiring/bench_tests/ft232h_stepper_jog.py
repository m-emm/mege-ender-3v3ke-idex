#!/usr/bin/env python3
"""Pulse STEP/DIR from an FT232H for a tiny stepper jog.

The Adafruit FT232H board labels normal wide GPIO pins as D0-D7 and C0-C7.
Pins C8/C9 are FT232H CBUS pins; this script refuses them unless the EEPROM
has explicitly configured them as GPIO. The stock board observed here has
C8=DRIVE1 and C9=DRIVE0, so they are not usable as STEP/DIR outputs.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from pyftdi.eeprom import FtdiEeprom
from pyftdi.gpio import GpioAsyncController
from pyftdi.gpio import GpioMpsseController


FT232H_URL = "ftdi://ftdi:232h/1"


@dataclass(frozen=True)
class Pin:
    name: str
    bit: int
    mask: int


class PinError(ValueError):
    pass


def parse_pin(name: str, *, url: str) -> Pin:
    label = name.strip().upper()
    if len(label) < 2 or label[0] not in ("D", "C") or not label[1:].isdigit():
        raise PinError(f"Invalid pin {name!r}; use D0-D7 or C0-C7.")
    group = label[0]
    index = int(label[1:])
    if group == "D" and 0 <= index <= 7:
        bit = index
        return Pin(label, bit, 1 << bit)
    if group == "C" and 0 <= index <= 7:
        bit = 8 + index
        return Pin(label, bit, 1 << bit)
    if group == "C" and index in (8, 9):
        raise PinError(_cbus_error(label, url))
    raise PinError(f"Pin {label} is outside the FT232H GPIO range this script can drive.")


def _cbus_error(label: str, url: str) -> str:
    functions = {}
    gpio_pins = []
    try:
        eeprom = FtdiEeprom()
        eeprom.open(url)
        gpio_pins = list(eeprom.cbus_pins)
        functions = {
            f"C{index}": eeprom._config.get(f"cbus_func_{index}", "-")
            for index in range(10)
        }
    except Exception as exc:
        return (
            f"{label} is a CBUS pin, not a normal MPSSE GPIO pin. "
            f"Could not read EEPROM details: {type(exc).__name__}: {exc}"
        )
    return (
        f"{label} is a CBUS pin, not a normal MPSSE GPIO pin. "
        f"Current EEPROM has CBUS GPIO pins {gpio_pins or 'none'}; "
        f"C8={functions.get('C8', '-')}, C9={functions.get('C9', '-')}. "
        "Move STEP/DIR to C0-C7 or D0-D7 for this jog script, or deliberately "
        "reconfigure the FT232H EEPROM in a separate step."
    )


def jog(
    *,
    url: str,
    step_pin: Pin,
    dir_pin: Pin,
    steps: int,
    direction: int,
    rate_hz: float,
    pulse_high_s: float,
) -> tuple[float, float]:
    if step_pin.mask == dir_pin.mask:
        raise PinError("STEP and DIR must be on different pins.")
    if steps <= 0:
        raise ValueError("steps must be positive.")
    if rate_hz <= 0:
        raise ValueError("rate_hz must be positive.")
    period_s = 1.0 / rate_hz
    if pulse_high_s <= 0 or pulse_high_s >= period_s:
        raise ValueError("pulse high time must be positive and shorter than the step period.")

    direction_mask = step_pin.mask | dir_pin.mask
    base_value = dir_pin.mask if direction else 0
    gpio = GpioMpsseController()
    start_time = time.monotonic()
    try:
        gpio.configure(url, direction=direction_mask, initial=0, frequency=100_000)
        gpio.write(base_value)
        time.sleep(0.05)
        for _index in range(steps):
            gpio.write(base_value | step_pin.mask)
            time.sleep(pulse_high_s)
            gpio.write(base_value)
            time.sleep(period_s - pulse_high_s)
        time.sleep(0.05)
        gpio.write(0)
    finally:
        try:
            gpio.write(0)
        except Exception:
            pass
        gpio.close()
    elapsed_s = time.monotonic() - start_time
    return elapsed_s, steps / elapsed_s


def stream_jog(
    *,
    url: str,
    step_pin: Pin,
    dir_pin: Pin,
    steps: int,
    direction: int,
    rate_hz: float,
    duty: float,
    samples_per_period: int,
) -> tuple[float, float, float, int, int]:
    if step_pin.mask == dir_pin.mask:
        raise PinError("STEP and DIR must be on different pins.")
    if step_pin.bit > 7 or dir_pin.bit > 7:
        raise PinError("Stream mode uses FTDI bitbang and only supports D0-D7.")
    if steps <= 0:
        raise ValueError("steps must be positive.")
    if rate_hz <= 0:
        raise ValueError("rate_hz must be positive.")
    if not 0 < duty < 1:
        raise ValueError("duty must be between 0 and 1.")
    if samples_per_period < 2:
        raise ValueError("samples_per_period must be at least 2.")

    high_samples = max(1, min(samples_per_period - 1, round(samples_per_period * duty)))
    low_samples = samples_per_period - high_samples
    requested_sample_rate = rate_hz * samples_per_period
    direction_mask = step_pin.mask | dir_pin.mask
    base_value = dir_pin.mask if direction else 0
    high_value = base_value | step_pin.mask
    period = bytes([high_value] * high_samples + [base_value] * low_samples)
    waveform = period * steps

    gpio = GpioAsyncController()
    start_time = time.monotonic()
    try:
        gpio.configure(
            url,
            direction=direction_mask,
            initial=base_value,
            frequency=requested_sample_rate,
        )
        actual_sample_rate = gpio.frequency
        gpio.write(waveform)
        time.sleep(len(waveform) / actual_sample_rate + 0.05)
        gpio.write(base_value)
        time.sleep(0.02)
        gpio.write(0)
    finally:
        try:
            gpio.write(0)
        except Exception:
            pass
        gpio.close()
    elapsed_s = time.monotonic() - start_time
    return elapsed_s, steps / elapsed_s, actual_sample_rate, high_samples, low_samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=FT232H_URL)
    parser.add_argument("--step-pin", default="D4", help="FT232H pin for STEP, default D4")
    parser.add_argument("--dir-pin", default="D5", help="FT232H pin for DIR, default D5")
    parser.add_argument("--steps", type=int, default=25, help="Number of STEP pulses")
    parser.add_argument("--rate-hz", type=float, default=100.0, help="STEP pulse rate")
    parser.add_argument(
        "--pulse-high-us",
        type=float,
        default=1000.0,
        help="STEP high time in microseconds for sleep mode",
    )
    parser.add_argument(
        "--mode",
        choices=("sleep", "stream"),
        default="sleep",
        help="sleep writes each edge from Python; stream clocks a buffered FTDI waveform.",
    )
    parser.add_argument(
        "--duty",
        type=float,
        default=0.5,
        help="STEP duty cycle for stream mode, default 0.5.",
    )
    parser.add_argument(
        "--samples-per-period",
        type=int,
        default=4,
        help="FTDI output samples per STEP period in stream mode, default 4.",
    )
    parser.add_argument(
        "--direction",
        choices=("0", "1"),
        default="0",
        help="DIR output level during jog",
    )
    parser.add_argument(
        "--armed",
        action="store_true",
        help="Required to actually generate pulses.",
    )
    args = parser.parse_args()

    try:
        step_pin = parse_pin(args.step_pin, url=args.url)
        dir_pin = parse_pin(args.dir_pin, url=args.url)
    except PinError as exc:
        print(f"Pin error: {exc}", file=sys.stderr)
        return 2

    print(
        "FT232H stepper jog\n"
        f"  STEP: {step_pin.name} bit {step_pin.bit}\n"
        f"  DIR:  {dir_pin.name} bit {dir_pin.bit} level {args.direction}\n"
        f"  pulses: {args.steps} at {args.rate_hz:g} Hz, "
        f"high {args.pulse_high_us:g} us\n"
        f"  mode: {args.mode}"
    )

    if not args.armed:
        print("\nDry run only. Add --armed to generate pulses.")
        return 0

    if args.mode == "stream":
        elapsed_s, average_rate, actual_sample_rate, high_samples, low_samples = stream_jog(
            url=args.url,
            step_pin=step_pin,
            dir_pin=dir_pin,
            steps=args.steps,
            direction=int(args.direction),
            rate_hz=args.rate_hz,
            duty=args.duty,
            samples_per_period=args.samples_per_period,
        )
        actual_step_rate = actual_sample_rate / args.samples_per_period
        print(
            "\nStreamed jog complete. "
            f"FTDI sample rate {actual_sample_rate:.1f} Hz, "
            f"nominal STEP {actual_step_rate:.1f} Hz, "
            f"samples high/low {high_samples}/{low_samples}, "
            f"wall-average {average_rate:.1f} pulses/s over {elapsed_s:.3f}s."
        )
    else:
        elapsed_s, average_rate = jog(
            url=args.url,
            step_pin=step_pin,
            dir_pin=dir_pin,
            steps=args.steps,
            direction=int(args.direction),
            rate_hz=args.rate_hz,
            pulse_high_s=args.pulse_high_us / 1_000_000.0,
        )
        print(
            f"\nJog complete. Wall-average {average_rate:.1f} pulses/s "
            f"over {elapsed_s:.3f}s."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
