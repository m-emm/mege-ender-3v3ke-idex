#!/usr/bin/env python3
"""Check active wiring YAML pin tags against the Klipper template."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
KLIPPER_CONFIG_DIR = SCRIPT_DIR.parent
DEFAULT_TEMPLATE_PATH = KLIPPER_CONFIG_DIR / "printer.cfg.template"
DEFAULT_WIRING_FILES = (
    SCRIPT_DIR / "pico_w_btt_tmc2226_x.yaml",
    SCRIPT_DIR / "pico_w_btt_tmc2226_y_z.yaml",
)


def load_template_settings(template_path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current_section: str | None = None

    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        section_match = re.fullmatch(r"\[(.+)\]", line)
        if section_match:
            current_section = section_match.group(1)
            sections.setdefault(current_section, {})
            continue

        if current_section is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        sections[current_section][key.strip()] = value.split("#", 1)[0].strip()

    return sections


def normalize_klipper_pin(value: str) -> tuple[str, str]:
    pin = value.strip()
    while pin and pin[0] in "!^~":
        pin = pin[1:].strip()

    if ":" in pin:
        mcu, pin_name = pin.split(":", 1)
    else:
        mcu, pin_name = "", pin

    gpio_match = re.search(r"gpio([0-9]+)", pin_name, flags=re.IGNORECASE)
    if gpio_match is None:
        raise ValueError(f"Klipper pin value is not a GPIO pin: {value!r}")

    return mcu, f"gpio{gpio_match.group(1)}"


def normalize_pico_gpio_endpoint(endpoint: Any) -> str | None:
    endpoint_text = str(endpoint)
    match = re.match(r"^PICO_GPIO_([0-9]+)(?:_|$)", endpoint_text)
    if match is None:
        return None
    return f"gpio{match.group(1)}"


def klipper_tags(raw_tag: Any) -> list[str]:
    if raw_tag is None:
        return []
    if isinstance(raw_tag, str):
        return [raw_tag]
    if isinstance(raw_tag, list) and all(isinstance(item, str) for item in raw_tag):
        return raw_tag
    raise ValueError(f"klipper wire metadata must be a string or list: {raw_tag!r}")


def split_klipper_ref(ref: str) -> tuple[str, str]:
    if "." not in ref:
        raise ValueError(f"Klipper reference must be SECTION.option: {ref!r}")
    section_name, option_name = ref.rsplit(".", 1)
    if not section_name or not option_name:
        raise ValueError(f"Klipper reference must be SECTION.option: {ref!r}")
    return section_name, option_name


def load_wiring_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a mapping")
    return data


def iter_tagged_wiring_refs(wiring_paths: tuple[Path, ...]) -> list[str]:
    refs: list[str] = []
    for wiring_path in wiring_paths:
        data = load_wiring_config(wiring_path)
        for wire in data.get("wires", []):
            refs.extend(klipper_tags(wire.get("klipper")))
    return refs


def validate_wiring(
    *,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    wiring_paths: tuple[Path, ...] = DEFAULT_WIRING_FILES,
) -> list[str]:
    errors: list[str] = []
    settings = load_template_settings(template_path)

    for wiring_path in wiring_paths:
        data = load_wiring_config(wiring_path)
        metadata = data.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            errors.append(f"{wiring_path}: metadata must be a mapping")
            continue

        expected_mcu = str(metadata.get("klipper_mcu", ""))
        raw_wires = data.get("wires", [])
        if not isinstance(raw_wires, list):
            errors.append(f"{wiring_path}: wires must be a list")
            continue

        for index, wire in enumerate(raw_wires):
            if not isinstance(wire, dict):
                errors.append(f"{wiring_path}: wire[{index}] must be a mapping")
                continue

            try:
                refs = klipper_tags(wire.get("klipper"))
            except ValueError as exc:
                errors.append(f"{wiring_path}: wire[{index}]: {exc}")
                continue
            if not refs:
                continue

            gpio_endpoints = [
                gpio
                for endpoint in (wire.get("from"), wire.get("to"))
                if (gpio := normalize_pico_gpio_endpoint(endpoint)) is not None
            ]
            if len(gpio_endpoints) != 1:
                errors.append(
                    f"{wiring_path}: wire[{index}] tagged {refs!r} must have "
                    f"exactly one PICO_GPIO_* endpoint, found {gpio_endpoints!r}"
                )
                continue
            wiring_gpio = gpio_endpoints[0]

            for ref in refs:
                try:
                    section_name, option_name = split_klipper_ref(ref)
                except ValueError as exc:
                    errors.append(f"{wiring_path}: wire[{index}]: {exc}")
                    continue

                section = settings.get(section_name)
                if section is None:
                    errors.append(
                        f"{wiring_path}: {ref} references missing "
                        f"[{section_name}] in {template_path}"
                    )
                    continue

                raw_pin = section.get(option_name)
                if raw_pin is None:
                    errors.append(
                        f"{wiring_path}: {ref} references missing option "
                        f"{option_name!r} in [{section_name}]"
                    )
                    continue

                try:
                    template_mcu, template_gpio = normalize_klipper_pin(raw_pin)
                except ValueError as exc:
                    errors.append(f"{wiring_path}: {ref}: {exc}")
                    continue

                if template_mcu != expected_mcu:
                    expected_label = expected_mcu or "<primary mcu>"
                    actual_label = template_mcu or "<primary mcu>"
                    errors.append(
                        f"{wiring_path}: {ref} MCU mismatch: wiring expects "
                        f"{expected_label}, template has {actual_label} "
                        f"({raw_pin!r})"
                    )

                if template_gpio != wiring_gpio:
                    errors.append(
                        f"{wiring_path}: {ref} GPIO mismatch: wiring has "
                        f"{wiring_gpio}, template has {template_gpio} ({raw_pin!r})"
                    )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate tagged active wiring YAML pins against printer.cfg.template."
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("wiring", nargs="*", type=Path, default=DEFAULT_WIRING_FILES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = validate_wiring(
        template_path=args.template,
        wiring_paths=tuple(args.wiring),
    )
    if errors:
        print("Wiring validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Wiring validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
