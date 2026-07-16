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
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "generated_gcode"
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
    bed_y_calibrated: bool
    bed_y_reference_y_mm: float
    bed_y_profile: str


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
DEFAULT_PRINT_REPLAY_Y_STRESS_PROFILES: tuple[StressProfile, ...] = (
    StressProfile("print_like_200_a2000_scv2", 200.0, 2000.0, 2.0),
    StressProfile("probe_300_a3000_scv2", 300.0, 3000.0, 2.0),
    StressProfile("probe_400_a4000_scv3", 400.0, 4000.0, 3.0),
)


@dataclass(frozen=True)
class TestPlan:
    cycles_per_profile: int = 2
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
class PrintReplayYPlan:
    high_y_mm: float = 147.651
    low_y_mm: float = 84.417
    cycles_per_check: int = 20
    checks_per_profile: int = 3
    reset_velocity_mm_s: float = 100.0
    reset_accel_mm_s2: float = 1000.0
    reset_square_corner_velocity: float = 2.0
    creep_velocity_mm_s: float = 20.0
    creep_accel_mm_s2: float = 500.0
    dwell_ms: int = 100
    endstop_key: str = "stepper_y"
    stress_profiles: tuple[StressProfile, ...] = DEFAULT_PRINT_REPLAY_Y_STRESS_PROFILES


@dataclass(frozen=True)
class CameraRepeatabilityPlan:
    checks_per_profile: int = 20
    reset_y_mm: float = 260.0
    stress_y_mm: float = 5.0
    velocity_mm_s: float = 100.0
    accel_start_mm_s2: float = 1000.0
    accel_stop_mm_s2: float = 1000.0
    accel_step_mm_s2: float = 0.0
    square_corner_velocity: float = 2.0
    approach_velocity_mm_s: float = 20.0
    approach_accel_mm_s2: float = 500.0
    tolerance_mm: float = 0.25
    confirm: int = 1
    settle_ms: int = 750
    run_id: str = "camera_repeatability"


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


def _setting_value(section: str, setting_name: str) -> str:
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"Missing setting {setting_name}")
    return match.group("value")


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
    vision = _section(config_text, "vision")
    return PrinterConfig(
        x=_axis_range(stepper_x),
        y=_axis_range(stepper_y),
        z=_axis_range(stepper_z),
        y_position_endstop=_setting_float(stepper_y, "position_endstop"),
        max_velocity=_setting_float(printer, "max_velocity"),
        max_accel=_setting_float(printer, "max_accel"),
        square_corner_velocity=_setting_float(printer, "square_corner_velocity"),
        bed_y_calibrated=_setting_value(vision, "bed_y_calibrated").lower()
        in ("true", "1", "yes", "on"),
        bed_y_reference_y_mm=_setting_float(vision, "bed_y_reference_y"),
        bed_y_profile=_setting_value(vision, "bed_y_profile"),
    )


def _format_float(value: float) -> str:
    return f"{value:.3f}"


def _feedrate(velocity_mm_s: float) -> str:
    return f"{velocity_mm_s * 60.0:.0f}"


def timestamped_output_path(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
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
    _validate_axis_target("Y", printer.y, plan.reset_y_mm)
    _validate_axis_target("Y", printer.y, plan.stress_y_mm)
    _validate_axis_target("Y", printer.y, printer.y_position_endstop)

    if not printer.y_position_endstop < plan.stress_y_mm < plan.reset_y_mm:
        raise ValueError("Y targets must satisfy endstop < stress_y_mm < reset_y_mm")


def _validate_print_replay_y_plan(
    printer: PrinterConfig, plan: PrintReplayYPlan
) -> None:
    if plan.cycles_per_check <= 0:
        raise ValueError("cycles_per_check must be positive")
    if plan.checks_per_profile <= 0:
        raise ValueError("checks_per_profile must be positive")
    if not plan.stress_profiles:
        raise ValueError("stress_profiles must not be empty")
    _validate_axis_target("Y", printer.y, plan.high_y_mm)
    _validate_axis_target("Y", printer.y, plan.low_y_mm)
    _validate_axis_target("Y", printer.y, printer.y_position_endstop)

    if not printer.y_position_endstop < plan.low_y_mm < plan.high_y_mm:
        raise ValueError("Y targets must satisfy endstop < low_y_mm < high_y_mm")


def camera_stress_profiles(plan: CameraRepeatabilityPlan) -> tuple[StressProfile, ...]:
    start = float(plan.accel_start_mm_s2)
    stop = float(plan.accel_stop_mm_s2)
    step = float(plan.accel_step_mm_s2)
    if start <= 0.0 or stop <= 0.0:
        raise ValueError("camera acceleration values must be positive")
    if stop < start:
        raise ValueError("camera accel stop must be >= start")
    if stop == start:
        values = [start]
    else:
        if step <= 0.0:
            raise ValueError("camera accel step must be positive when stop > start")
        values = []
        value = start
        while value <= stop + 1.0e-9:
            values.append(value)
            value += step
        if abs(values[-1] - stop) > 1.0e-6:
            raise ValueError("camera acceleration step must land exactly on stop")
    return tuple(
        StressProfile(
            name=f"accel_{accel:g}",
            velocity_mm_s=float(plan.velocity_mm_s),
            accel_mm_s2=accel,
            square_corner_velocity=float(plan.square_corner_velocity),
        )
        for accel in values
    )


def _validate_camera_repeatability_plan(
    printer: PrinterConfig, plan: CameraRepeatabilityPlan
) -> tuple[StressProfile, ...]:
    if not printer.bed_y_calibrated:
        raise ValueError("camera-repeatability requires calibrated bed Y vision")
    if plan.checks_per_profile <= 0:
        raise ValueError("camera checks per profile must be positive")
    if plan.velocity_mm_s <= 0.0 or plan.approach_velocity_mm_s <= 0.0:
        raise ValueError("camera motion velocities must be positive")
    if plan.approach_accel_mm_s2 <= 0.0 or plan.tolerance_mm <= 0.0:
        raise ValueError("camera approach accel and tolerance must be positive")
    if plan.confirm not in (0, 1, 2):
        raise ValueError("camera confirmation count must be 0, 1, or 2")
    reference_y = printer.bed_y_reference_y_mm
    for value in (reference_y, plan.reset_y_mm, plan.stress_y_mm):
        _validate_axis_target("Y", printer.y, value)
    if not printer.y_position_endstop < reference_y < plan.stress_y_mm < plan.reset_y_mm:
        raise ValueError(
            "camera Y targets must satisfy endstop < reference < stress < reset"
        )
    return camera_stress_profiles(plan)


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
            f"heaters off, then running {total_checks} Y-only endstop checks."
            '"'
        ),
        "M104 S0",
        "M140 S0",
        "G90",
        "M400",
        "G28 Y",
        "M400",
        f"G1 Y{_format_float(plan.reset_y_mm)} F{_feedrate(plan.reset_velocity_mm_s)}",
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
                    f"G1 Y{_format_float(plan.reset_y_mm)} F{_feedrate(plan.reset_velocity_mm_s)}",
                    "M400",
                    _set_velocity_limit(
                        velocity=profile.velocity_mm_s,
                        accel=profile.accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                    f"G1 Y{_format_float(plan.stress_y_mm)} F{_feedrate(profile.velocity_mm_s)}",
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
                    f"G1 Y{_format_float(y_endstop)} F{_feedrate(plan.creep_velocity_mm_s)}",
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


def generate_print_replay_y_gcode(
    printer: PrinterConfig,
    plan: PrintReplayYPlan = PrintReplayYPlan(),
) -> str:
    _validate_print_replay_y_plan(printer, plan)

    y_endstop = printer.y_position_endstop
    total_checks = len(plan.stress_profiles) * plan.checks_per_profile
    stress_moves_per_check = plan.cycles_per_check

    lines = [
        "; Y print-replay step-loss characterization generated by generate_y_step_loss_test_gcode.py",
        "; This file keeps heaters off and replays the suspect print Y travel leg only.",
        "; Suspect print travel leg: Y147.651 -> Y84.417 toward the Y endstop.",
        f"; Endstop verification key: {plan.endstop_key}",
        (
            f"; Y configured range: {_format_float(printer.y.position_min)}.."
            f"{_format_float(printer.y.position_max)}"
        ),
        f"; Y endstop: {_format_float(y_endstop)}",
        f"; Y high replay target: {_format_float(plan.high_y_mm)}",
        f"; Y low replay target: {_format_float(plan.low_y_mm)}",
        f"; Cycles per check: {plan.cycles_per_check}",
        f"; Checks per profile: {plan.checks_per_profile}",
        f"; Stress moves toward endstop per check: {stress_moves_per_check}",
        f"; Stress profiles: {', '.join(profile.name for profile in plan.stress_profiles)}",
        f"; Total endstop checks: {total_checks}",
        "M117 Y print replay characterization",
        (
            'RESPOND TYPE=echo MSG="Y print replay characterization: '
            f"heaters off, then running {total_checks} endstop checks "
            f"after {stress_moves_per_check} replay moves toward lower Y per check."
            '"'
        ),
        "M104 S0",
        "M140 S0",
        "G90",
        "M400",
        "G28 Y",
        "M400",
    ]

    check_index = 0
    for profile in plan.stress_profiles:
        lines.append(
            (
                f'RESPOND TYPE=echo MSG="Y print replay profile {profile.name}: '
                f"velocity {profile.velocity_mm_s:g} mm/s, "
                f"accel {profile.accel_mm_s2:g} mm/s^2, "
                f"SCV {profile.square_corner_velocity:g}, "
                f"{plan.cycles_per_check} stress moves per check, "
                f'{plan.checks_per_profile} checks."'
            )
        )
        for check in range(1, plan.checks_per_profile + 1):
            check_index += 1
            lines.extend(
                [
                    (
                        f"; Replay check {check_index}/{total_checks}: "
                        f"profile={profile.name} "
                        f"velocity={profile.velocity_mm_s:g} "
                        f"accel={profile.accel_mm_s2:g} "
                        f"scv={profile.square_corner_velocity:g} "
                        f"check={check}"
                    ),
                    _set_velocity_limit(
                        velocity=plan.reset_velocity_mm_s,
                        accel=plan.reset_accel_mm_s2,
                        square_corner_velocity=plan.reset_square_corner_velocity,
                    ),
                    f"G1 Y{_format_float(plan.high_y_mm)} F{_feedrate(plan.reset_velocity_mm_s)}",
                    "M400",
                    _set_velocity_limit(
                        velocity=profile.velocity_mm_s,
                        accel=profile.accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                ]
            )
            for cycle in range(1, plan.cycles_per_check + 1):
                lines.extend(
                    [
                        (
                            f"; Replay cycle {cycle}/{plan.cycles_per_check}: "
                            f"Y{_format_float(plan.high_y_mm)} -> "
                            f"Y{_format_float(plan.low_y_mm)} toward endstop"
                        ),
                        f"G1 Y{_format_float(plan.low_y_mm)} F{_feedrate(profile.velocity_mm_s)}",
                    ]
                )
                if cycle < plan.cycles_per_check:
                    lines.append(
                        f"G1 Y{_format_float(plan.high_y_mm)} F{_feedrate(profile.velocity_mm_s)}"
                    )
            lines.extend(
                [
                    "M400",
                    _set_velocity_limit(
                        velocity=plan.creep_velocity_mm_s,
                        accel=plan.creep_accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                    f"G1 Y{_format_float(y_endstop)} F{_feedrate(plan.creep_velocity_mm_s)}",
                    "M400",
                    f"G4 P{plan.dwell_ms}",
                    "QUERY_ENDSTOPS",
                    (
                        "Y_STEP_LOSS_ASSERT_ENDSTOP "
                        f"PROFILE={profile.name} "
                        f"VELOCITY={profile.velocity_mm_s:g} "
                        f"ACCEL={profile.accel_mm_s2:g} "
                        f"SCV={profile.square_corner_velocity:g} "
                        f"CYCLE={check} STEP={check_index}"
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
            f'RESPOND TYPE=echo MSG="Y print replay characterization passed: {total_checks} endstop checks completed."',
            "M117 Y print replay passed",
            "",
        ]
    )
    return "\n".join(lines)


def _camera_measurement_lines(
    *,
    printer: PrinterConfig,
    plan: CameraRepeatabilityPlan,
    step: int,
) -> list[str]:
    return [
        f"VISION_PROFILE CAMERA=nozzle_cam PROFILE={printer.bed_y_profile}",
        "NOZZLE_CAM_Y_FEATURE_LIGHT",
        f"G4 P{plan.settle_ms}",
        (
            "VISION_MEASURE_BED_Y "
            f"EXPECTED_Y={_format_float(printer.bed_y_reference_y_mm)} "
            f"TOLERANCE={plan.tolerance_mm:g} "
            f"CONFIRM={plan.confirm} ASSERT=1 "
            f"RUN={plan.run_id} STEP={step}"
        ),
    ]


def generate_camera_repeatability_gcode(
    printer: PrinterConfig,
    plan: CameraRepeatabilityPlan = CameraRepeatabilityPlan(),
) -> str:
    profiles = _validate_camera_repeatability_plan(printer, plan)
    total_checks = len(profiles) * plan.checks_per_profile
    reference_y = printer.bed_y_reference_y_mm
    lines = [
        "; Y camera repeatability characterization generated by generate_y_step_loss_test_gcode.py",
        "; One initial G28 Y is followed only by camera checks at the calibrated safe point.",
        "; This file keeps heaters off and performs Y-only linear moves.",
        f"; Camera reference Y: {_format_float(reference_y)}",
        f"; Reset Y: {_format_float(plan.reset_y_mm)}",
        f"; Stress Y: {_format_float(plan.stress_y_mm)}",
        f"; Profiles: {', '.join(profile.name for profile in profiles)}",
        f"; Checks per profile: {plan.checks_per_profile}",
        f"; Total post-motion checks: {total_checks}",
        f"; Position tolerance: {plan.tolerance_mm:g} mm",
        "M117 Y camera repeatability",
        "M104 S0",
        "M140 S0",
        "G90",
        "M400",
        "G28 Y",
        "M400",
        _set_velocity_limit(
            velocity=plan.approach_velocity_mm_s,
            accel=plan.approach_accel_mm_s2,
            square_corner_velocity=printer.square_corner_velocity,
        ),
        f"G1 Y{_format_float(reference_y)} F{_feedrate(plan.approach_velocity_mm_s)}",
        "M400",
        _set_velocity_limit(
            velocity=printer.max_velocity,
            accel=printer.max_accel,
            square_corner_velocity=printer.square_corner_velocity,
        ),
        'RESPOND TYPE=echo MSG="Y camera repeatability baseline check."',
    ]
    lines.extend(_camera_measurement_lines(printer=printer, plan=plan, step=0))

    check_index = 0
    for profile in profiles:
        lines.append(
            'RESPOND TYPE=echo MSG="Y camera profile '
            f"{profile.name}: velocity {profile.velocity_mm_s:g} mm/s, "
            f"accel {profile.accel_mm_s2:g} mm/s^2, "
            f"SCV {profile.square_corner_velocity:g}, "
            f'{plan.checks_per_profile} checks."'
        )
        for cycle in range(1, plan.checks_per_profile + 1):
            check_index += 1
            lines.extend(
                [
                    (
                        f"; Camera check {check_index}/{total_checks}: "
                        f"profile={profile.name} cycle={cycle}"
                    ),
                    _set_velocity_limit(
                        velocity=profile.velocity_mm_s,
                        accel=profile.accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                    f"G1 Y{_format_float(plan.reset_y_mm)} F{_feedrate(profile.velocity_mm_s)}",
                    f"G1 Y{_format_float(plan.stress_y_mm)} F{_feedrate(profile.velocity_mm_s)}",
                    "M400",
                    _set_velocity_limit(
                        velocity=plan.approach_velocity_mm_s,
                        accel=plan.approach_accel_mm_s2,
                        square_corner_velocity=profile.square_corner_velocity,
                    ),
                    f"G1 Y{_format_float(reference_y)} F{_feedrate(plan.approach_velocity_mm_s)}",
                    "M400",
                    _set_velocity_limit(
                        velocity=printer.max_velocity,
                        accel=printer.max_accel,
                        square_corner_velocity=printer.square_corner_velocity,
                    ),
                ]
            )
            lines.extend(
                _camera_measurement_lines(
                    printer=printer, plan=plan, step=check_index
                )
            )

    lines.extend(
        [
            "M400",
            _set_velocity_limit(
                velocity=printer.max_velocity,
                accel=printer.max_accel,
                square_corner_velocity=printer.square_corner_velocity,
            ),
            "VISION_LIGHT_OFF",
            (
                'RESPOND TYPE=echo MSG="Y camera repeatability passed: baseline plus '
                f'{total_checks} post-motion checks completed."'
            ),
            "M117 Y camera repeatability passed",
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
        "--pattern",
        choices=("cold-quick", "print-replay-y", "camera-repeatability"),
        default="cold-quick",
        help=(
            "Motion pattern to generate. cold-quick preserves the existing "
            "acceleration ladder; print-replay-y repeats the suspect print Y "
            "travel leg."
        ),
    )
    parser.add_argument("--camera-reset-y", type=float, default=260.0)
    parser.add_argument("--camera-stress-y", type=float, default=5.0)
    parser.add_argument("--camera-velocity", type=float, default=100.0)
    parser.add_argument("--camera-accel-start", type=float, default=1000.0)
    parser.add_argument("--camera-accel-stop", type=float, default=1000.0)
    parser.add_argument("--camera-accel-step", type=float, default=0.0)
    parser.add_argument("--camera-scv", type=float, default=2.0)
    parser.add_argument("--camera-checks-per-profile", type=int, default=20)
    parser.add_argument("--camera-approach-velocity", type=float, default=20.0)
    parser.add_argument("--camera-approach-accel", type=float, default=500.0)
    parser.add_argument("--camera-tolerance", type=float, default=0.25)
    parser.add_argument("--camera-confirm", type=int, default=1)
    parser.add_argument("--camera-run-id", default="camera_repeatability")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to a unique timestamped G-code file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the timestamped output file when --output is omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    printer = load_printer_config(args.config)
    if args.pattern == "print-replay-y":
        gcode = generate_print_replay_y_gcode(printer)
    elif args.pattern == "camera-repeatability":
        gcode = generate_camera_repeatability_gcode(
            printer,
            CameraRepeatabilityPlan(
                checks_per_profile=args.camera_checks_per_profile,
                reset_y_mm=args.camera_reset_y,
                stress_y_mm=args.camera_stress_y,
                velocity_mm_s=args.camera_velocity,
                accel_start_mm_s2=args.camera_accel_start,
                accel_stop_mm_s2=args.camera_accel_stop,
                accel_step_mm_s2=args.camera_accel_step,
                square_corner_velocity=args.camera_scv,
                approach_velocity_mm_s=args.camera_approach_velocity,
                approach_accel_mm_s2=args.camera_approach_accel,
                tolerance_mm=args.camera_tolerance,
                confirm=args.camera_confirm,
                run_id=args.camera_run_id,
            ),
        )
    else:
        gcode = generate_gcode(printer)
    output_path = args.output or timestamped_output_path(args.output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gcode, encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
