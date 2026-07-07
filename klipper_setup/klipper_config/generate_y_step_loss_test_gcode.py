#!/usr/bin/env python3
"""Generate a cold quick Y-axis step-loss characterization G-code file."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "printer.cfg"
OUTPUT_FILENAME_PREFIX = "y_step_loss_characterization"


@dataclass(frozen=True)
class AxisRange:
    position_min: float
    position_max: float


@dataclass(frozen=True)
class PrinterConfig:
    x: AxisRange
    y: AxisRange
    z: AxisRange
    y_position_endstop: float
    max_velocity: float
    max_accel: float
    square_corner_velocity: float


@dataclass(frozen=True)
class StressProfile:
    name: str
    velocity_mm_s: float
    accel_mm_s2: float
    square_corner_velocity: float


DEFAULT_ACCEL_LADDER_MM_S2: tuple[float, ...] = (
    3500.0,
    4000.0,
    4500.0,
    5000.0,
    5500.0,
    6000.0,
    6500.0,
    7000.0,
    7500.0,
    8000.0,
)
DEFAULT_STRESS_PROFILES: tuple[StressProfile, ...] = tuple(
    StressProfile(f"accel_{accel:g}", 500.0, accel, 5.0)
    for accel in DEFAULT_ACCEL_LADDER_MM_S2
)


@dataclass(frozen=True)
class TestPlan:
    cycles_per_profile: int = 2
    x_position_mm: float = 100.0
    z_height_mm: float = 10.0
    reset_y_mm: float = 260.0
    stress_y_mm: float = 5.0
    reset_velocity_mm_s: float = 200.0
    reset_accel_mm_s2: float = 1000.0
    reset_square_corner_velocity: float = 5.0
    creep_velocity_mm_s: float = 20.0
    creep_accel_mm_s2: float = 500.0
    dwell_ms: int = 100
    endstop_key: str = "stepper_y"
    stress_profiles: tuple[StressProfile, ...] = DEFAULT_STRESS_PROFILES


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def _section(config_text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\n(?P<body>.*?)(?=^\[|\Z)",
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise ValueError(f"Missing [{name}] section")
    return match.group("body")


def _setting_float(section: str, setting_name: str) -> float:
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"Missing setting {setting_name}")
    return float(match.group("value"))


def _axis_range(section: str) -> AxisRange:
    return AxisRange(
        position_min=_setting_float(section, "position_min"),
        position_max=_setting_float(section, "position_max"),
    )


def load_printer_config(config_path: Path = DEFAULT_CONFIG_PATH) -> PrinterConfig:
    config_text = config_path.read_text(encoding="utf-8")
    printer = _section(config_text, "printer")
    stepper_x = _section(config_text, "stepper_x")
    stepper_y = _section(config_text, "stepper_y")
    stepper_z = _section(config_text, "stepper_z")
    return PrinterConfig(
        x=_axis_range(stepper_x),
        y=_axis_range(stepper_y),
        z=_axis_range(stepper_z),
        y_position_endstop=_setting_float(stepper_y, "position_endstop"),
        max_velocity=_setting_float(printer, "max_velocity"),
        max_accel=_setting_float(printer, "max_accel"),
        square_corner_velocity=_setting_float(printer, "square_corner_velocity"),
    )


def _format_float(value: float) -> str:
    return f"{value:.3f}"


def _feedrate(velocity_mm_s: float) -> str:
    return f"{velocity_mm_s * 60.0:.0f}"


def timestamped_output_path(
    output_dir: Path = SCRIPT_DIR,
    now: datetime | None = None,
) -> Path:
    current_time = now or datetime.now()
    return output_dir / f"{OUTPUT_FILENAME_PREFIX}_{current_time:%Y%m%d_%H%M%S}.gcode"


def _validate_axis_target(axis_name: str, axis: AxisRange, value: float) -> None:
    if not axis.position_min <= value <= axis.position_max:
        raise ValueError(
            f"{axis_name} target {value:.3f} is outside configured "
            f"{axis_name} range {axis.position_min:.3f}..{axis.position_max:.3f}"
        )


def _validate_plan(printer: PrinterConfig, plan: TestPlan) -> None:
    if plan.cycles_per_profile <= 0:
        raise ValueError("cycles_per_profile must be positive")
    if not plan.stress_profiles:
        raise ValueError("stress_profiles must not be empty")
    _validate_axis_target("X", printer.x, plan.x_position_mm)
    _validate_axis_target("Z", printer.z, plan.z_height_mm)
    _validate_axis_target("Y", printer.y, plan.reset_y_mm)
    _validate_axis_target("Y", printer.y, plan.stress_y_mm)
    _validate_axis_target("Y", printer.y, printer.y_position_endstop)

    if not printer.y_position_endstop < plan.stress_y_mm < plan.reset_y_mm:
        raise ValueError("Y targets must satisfy endstop < stress_y_mm < reset_y_mm")


def _set_velocity_limit(
    *,
    velocity: float,
    accel: float,
    square_corner_velocity: float,
) -> str:
    return (
        "SET_VELOCITY_LIMIT "
        f"VELOCITY={velocity:g} "
        f"ACCEL={accel:g} "
        f"SQUARE_CORNER_VELOCITY={square_corner_velocity:g}"
    )


def generate_gcode(printer: PrinterConfig, plan: TestPlan = TestPlan()) -> str:
    _validate_plan(printer, plan)

    y_endstop = printer.y_position_endstop
    total_checks = len(plan.stress_profiles) * plan.cycles_per_profile

    lines = [
        "; Y cold quick step-loss characterization generated by generate_y_step_loss_test_gcode.py",
        "; This file keeps heaters off and performs Y-only linear moves.",
        f"; Endstop verification key: {plan.endstop_key}",
        f"; Z characterization height: {_format_float(plan.z_height_mm)}",
        (
            f"; Y configured range: {_format_float(printer.y.position_min)}.."
            f"{_format_float(printer.y.position_max)}"
        ),
        f"; Y endstop: {_format_float(y_endstop)}",
        f"; Y reset target: {_format_float(plan.reset_y_mm)}",
        f"; Y stress target: {_format_float(plan.stress_y_mm)}",
        f"; Stress profiles: {', '.join(profile.name for profile in plan.stress_profiles)}",
        f"; Cycles per profile: {plan.cycles_per_profile}",
        f"; Total endstop checks: {total_checks}",
        "M117 Y cold quick characterization",
        (
            'RESPOND TYPE=echo MSG="Y cold quick characterization: '
            f"heaters off, then running {total_checks} Y-only endstop checks." '"'
        ),
        "M104 S0",
        "M140 S0",
        "T0",
        "G90",
        "M400",
        "G28 X Y Z",
        "M400",
        f"G1 Z{_format_float(plan.z_height_mm)} F{_feedrate(10.0)}",
        (
            f"G1 X{_format_float(plan.x_position_mm)} "
            f"Y{_format_float(plan.reset_y_mm)} "
            f"F{_feedrate(plan.reset_velocity_mm_s)}"
        ),
        "M400",
    ]

    check_index = 0
    for profile in plan.stress_profiles:
        lines.extend(
            [
                (
                    f'RESPOND TYPE=echo MSG="Y cold quick profile {profile.name}: '
                    f"velocity {profile.velocity_mm_s:g} mm/s, "
                    f"accel {profile.accel_mm_s2:g} mm/s^2, "
                    f"SCV {profile.square_corner_velocity:g}, "
                    f'{plan.cycles_per_profile} cycles."'
                ),
            ]
        )
        for cycle in range(1, plan.cycles_per_profile + 1):
            check_index += 1
            lines.extend(
                [
                    (
                        f"; Check {check_index}/{total_checks}: "
                        f"profile={profile.name} "
                        f"velocity={profile.velocity_mm_s:g} "
                        f"accel={profile.accel_mm_s2:g} "
                        f"scv={profile.square_corner_velocity:g} "
                        f"cycle={cycle}"
                    ),
                    _set_velocity_limit(
                        velocity=plan.reset_velocity_mm_s,
                        accel=plan.reset_accel_mm_s2,
                        square_corner_velocity=plan.reset_square_corner_velocity,
                    ),
                    (
                        f"G1 X{_format_float(plan.x_position_mm)} "
                        f"Y{_format_float(plan.reset_y_mm)} "
                        f"Z{_format_float(plan.z_height_mm)} "
                        f"F{_feedrate(plan.reset_velocity_mm_s)}"
                    ),
                    "M400",
                    _set_velocity_limit(
                        velocity=profile.velocity_mm_s,
                        accel=profile.accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                    (
                        f"G1 X{_format_float(plan.x_position_mm)} "
                        f"Y{_format_float(plan.stress_y_mm)} "
                        f"F{_feedrate(profile.velocity_mm_s)}"
                    ),
                ]
            )
            lines.extend(
                [
                    "M400",
                    _set_velocity_limit(
                        velocity=plan.creep_velocity_mm_s,
                        accel=plan.creep_accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                    (
                        f"G1 X{_format_float(plan.x_position_mm)} "
                        f"Y{_format_float(y_endstop)} "
                        f"F{_feedrate(plan.creep_velocity_mm_s)}"
                    ),
                    "M400",
                    f"G4 P{plan.dwell_ms}",
                    "QUERY_ENDSTOPS",
                    (
                        "Y_STEP_LOSS_ASSERT_ENDSTOP "
                        f"PROFILE={profile.name} "
                        f"VELOCITY={profile.velocity_mm_s:g} "
                        f"ACCEL={profile.accel_mm_s2:g} "
                        f"SCV={profile.square_corner_velocity:g} "
                        f"CYCLE={cycle} STEP={check_index}"
                    ),
                ]
            )

    lines.extend(
        [
            "M400",
            _set_velocity_limit(
                velocity=printer.max_velocity,
                accel=printer.max_accel,
                square_corner_velocity=printer.square_corner_velocity,
            ),
            f'RESPOND TYPE=echo MSG="Y cold quick characterization passed: {total_checks} endstop checks completed."',
            "M117 Y cold quick passed",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a cold quick Y-axis step-loss characterization G-code file."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to a unique timestamped G-code file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR,
        help="Directory for the timestamped output file when --output is omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    printer = load_printer_config(args.config)
    gcode = generate_gcode(printer)
    output_path = args.output or timestamped_output_path(args.output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gcode, encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
