#!/usr/bin/env python3
"""Drive the APA102/DotStar vision light strip from an FT232H."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from pyftdi.gpio import GpioMpsseController

from ft232h_stepper_jog import FT232H_URL, Pin, PinError, parse_pin


DEFAULT_PATTERN = "green,red,blue,white,green,red,blue,white"
DEFAULT_INTENSITY = 0.25
DEFAULT_PIXEL_COUNT = 8

COLOR_TABLE: dict[str, tuple[int, int, int]] = {
    "off": (0, 0, 0),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
}


@dataclass(frozen=True)
class Pixel:
    red: int
    green: int
    blue: int


def parse_intensity(text: str) -> float:
    intensity = float(text)
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be between 0.0 and 1.0.")
    return intensity


def parse_color(text: str) -> Pixel:
    value = text.strip().lower()
    if value in COLOR_TABLE:
        red, green, blue = COLOR_TABLE[value]
        return Pixel(red, green, blue)
    if value.startswith("#") and len(value) == 7:
        try:
            red = int(value[1:3], 16)
            green = int(value[3:5], 16)
            blue = int(value[5:7], 16)
        except ValueError as exc:
            raise ValueError(f"Invalid RGB hex color {text!r}.") from exc
        return Pixel(red, green, blue)
    valid_names = ", ".join(sorted(COLOR_TABLE))
    raise ValueError(f"Invalid color {text!r}; use one of {valid_names} or #RRGGBB.")


def parse_pattern(text: str) -> list[Pixel]:
    pixels = [parse_color(item) for item in text.split(",") if item.strip()]
    if not pixels:
        raise ValueError("pattern must contain at least one color.")
    return pixels


def repeated_color(color_text: str, pixel_count: int) -> list[Pixel]:
    if pixel_count <= 0:
        raise ValueError("pixel-count must be positive.")
    return [parse_color(color_text)] * pixel_count


def scale_channel(value: int, intensity: float) -> int:
    return max(0, min(255, round(value * intensity)))


def encode_apa102_frame(pixels: list[Pixel], *, intensity: float) -> bytes:
    frame = bytearray(b"\x00\x00\x00\x00")
    for pixel in pixels:
        frame.extend(
            (
                0xFF,
                scale_channel(pixel.blue, intensity),
                scale_channel(pixel.green, intensity),
                scale_channel(pixel.red, intensity),
            )
        )
    end_bytes = max(1, (len(pixels) + 15) // 16)
    frame.extend(b"\xff" * end_bytes)
    return bytes(frame)


def iter_bits(data: bytes):
    for byte in data:
        for bit_index in range(7, -1, -1):
            yield (byte >> bit_index) & 1


def write_apa102_frame(
    gpio: GpioMpsseController,
    *,
    clock_pin: Pin,
    data_pin: Pin,
    frame: bytes,
    bit_delay_s: float,
) -> None:
    for bit in iter_bits(frame):
        value = data_pin.mask if bit else 0
        gpio.write(value)
        if bit_delay_s:
            time.sleep(bit_delay_s)
        gpio.write(value | clock_pin.mask)
        if bit_delay_s:
            time.sleep(bit_delay_s)
        gpio.write(value)
    gpio.write(0)


def drive_pattern(
    *,
    url: str,
    clock_pin: Pin,
    data_pin: Pin,
    pixels: list[Pixel],
    intensity: float,
    bit_delay_s: float,
    hold_s: float,
    off_after: bool,
) -> None:
    if clock_pin.mask == data_pin.mask:
        raise PinError("clock and data must be on different pins.")
    if hold_s < 0:
        raise ValueError("hold_s must be zero or positive.")
    if bit_delay_s < 0:
        raise ValueError("bit_delay_s must be zero or positive.")

    direction = clock_pin.mask | data_pin.mask
    frame = encode_apa102_frame(pixels, intensity=intensity)
    off_frame = encode_apa102_frame([Pixel(0, 0, 0)] * len(pixels), intensity=1.0)
    gpio = GpioMpsseController()
    try:
        gpio.configure(url, direction=direction, initial=0, frequency=100_000)
        write_apa102_frame(
            gpio,
            clock_pin=clock_pin,
            data_pin=data_pin,
            frame=frame,
            bit_delay_s=bit_delay_s,
        )
        if hold_s:
            time.sleep(hold_s)
        if off_after:
            write_apa102_frame(
                gpio,
                clock_pin=clock_pin,
                data_pin=data_pin,
                frame=off_frame,
                bit_delay_s=bit_delay_s,
            )
    finally:
        try:
            gpio.write(0)
        except Exception:
            pass
        gpio.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=FT232H_URL)
    parser.add_argument(
        "--clock-pin", default="D4", help="FT232H clock pin, default D4"
    )
    parser.add_argument("--data-pin", default="D5", help="FT232H data pin, default D5")
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help=f"Comma-separated colors, default {DEFAULT_PATTERN}",
    )
    parser.add_argument(
        "--all-color",
        default=None,
        help="Use one color for every pixel instead of the pattern.",
    )
    parser.add_argument(
        "--pixel-count",
        type=int,
        default=DEFAULT_PIXEL_COUNT,
        help="Pixel count used with --all-color, default 8.",
    )
    parser.add_argument(
        "--intensity",
        default=str(DEFAULT_INTENSITY),
        help="Scale RGB channels from 0.0 to 1.0, default 0.25.",
    )
    parser.add_argument(
        "--bit-delay-us",
        type=float,
        default=0.0,
        help="Optional settle delay after each data/clock edge.",
    )
    parser.add_argument(
        "--hold-s",
        type=float,
        default=0.0,
        help="Optional delay after lighting the strip before exiting.",
    )
    parser.add_argument(
        "--off-after",
        action="store_true",
        help="Send an all-off frame after the optional hold.",
    )
    parser.add_argument(
        "--armed", action="store_true", help="Required to drive the strip."
    )
    args = parser.parse_args()

    try:
        clock_pin = parse_pin(args.clock_pin, url=args.url)
        data_pin = parse_pin(args.data_pin, url=args.url)
        if args.all_color is None:
            pixels = parse_pattern(args.pattern)
            pattern_label = args.pattern
        else:
            pixels = repeated_color(args.all_color, args.pixel_count)
            pattern_label = f"{args.all_color} repeated {args.pixel_count}x"
        intensity = parse_intensity(args.intensity)
        if args.bit_delay_us < 0:
            raise ValueError("bit-delay-us must be zero or positive.")
    except (PinError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    print(
        "FT232H APA102 vision light\n"
        f"  CLOCK: {clock_pin.name} bit {clock_pin.bit}\n"
        f"  DATA:  {data_pin.name} bit {data_pin.bit}\n"
        f"  pixels: {len(pixels)}\n"
        f"  pattern: {pattern_label}\n"
        f"  intensity: {intensity:g}\n"
        f"  APA102 bytes: {len(encode_apa102_frame(pixels, intensity=intensity))}"
    )
    if not args.armed:
        print("\nDry run only. Add --armed to light the strip.")
        return 0

    drive_pattern(
        url=args.url,
        clock_pin=clock_pin,
        data_pin=data_pin,
        pixels=pixels,
        intensity=intensity,
        bit_delay_s=args.bit_delay_us / 1_000_000.0,
        hold_s=args.hold_s,
        off_after=args.off_after,
    )
    print("Finished APA102 frame write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
