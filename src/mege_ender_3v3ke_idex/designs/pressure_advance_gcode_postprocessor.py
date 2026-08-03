"""Y-banded pressure-advance calibration G-code postprocessor."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

_WORD_PATTERN = re.compile(
    r"(?:^|\s)([A-Za-z])([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)
_POSITION_EPSILON = 1e-6
_EXTRUSION_EPSILON = 1e-9


@dataclass(frozen=True)
class _PressureAdvanceBand:
    y_min: float
    y_max: float
    advance: float
    label: str


def _decimal_value(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"sweep.{field_name} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"sweep.{field_name} must be finite")
    return result


def expand_pressure_advance_sweep(
    sweep: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Expand a compact pressure-advance sweep into labelled Y bands."""

    if not isinstance(sweep, Mapping):
        raise ValueError("sweep must be a mapping")

    y_min_start = _decimal_value(sweep["y_min_start"], "y_min_start")
    band_height = _decimal_value(sweep["band_height"], "band_height")
    y_pitch = _decimal_value(sweep["y_pitch"], "y_pitch")
    advance_start = _decimal_value(sweep["advance_start"], "advance_start")
    if band_height <= 0:
        raise ValueError("sweep.band_height must be positive")
    if y_pitch < band_height:
        raise ValueError("sweep.y_pitch must be at least sweep.band_height")
    if advance_start < 0:
        raise ValueError("sweep.advance_start must be non-negative")

    has_pitch_count = "advance_pitch" in sweep or "count" in sweep
    has_stop_intervals = "advance_stop" in sweep or "intervals" in sweep
    if has_pitch_count == has_stop_intervals:
        raise ValueError(
            "sweep must define exactly one of advance_pitch/count or "
            "advance_stop/intervals"
        )

    if has_pitch_count:
        if "advance_pitch" not in sweep or "count" not in sweep:
            raise ValueError("sweep.advance_pitch and sweep.count are both required")
        advance_pitch = _decimal_value(sweep["advance_pitch"], "advance_pitch")
        count = int(sweep["count"])
        if Decimal(count) != _decimal_value(sweep["count"], "count"):
            raise ValueError("sweep.count must be an integer")
        if advance_pitch <= 0:
            raise ValueError("sweep.advance_pitch must be positive")
    else:
        if "advance_stop" not in sweep or "intervals" not in sweep:
            raise ValueError("sweep.advance_stop and sweep.intervals are both required")
        advance_stop = _decimal_value(sweep["advance_stop"], "advance_stop")
        intervals = int(sweep["intervals"])
        if Decimal(intervals) != _decimal_value(sweep["intervals"], "intervals"):
            raise ValueError("sweep.intervals must be an integer")
        if intervals <= 0:
            raise ValueError("sweep.intervals must be positive")
        if advance_stop <= advance_start:
            raise ValueError("sweep.advance_stop must exceed sweep.advance_start")
        count = intervals + 1
        advance_pitch = (advance_stop - advance_start) / Decimal(intervals)

    if count <= 0:
        raise ValueError("sweep.count must be positive")
    label_decimals = int(sweep.get("label_decimals", 3))
    if label_decimals < 0 or label_decimals > 6:
        raise ValueError("sweep.label_decimals must be between 0 and 6")
    quantum = Decimal(1).scaleb(-label_decimals)

    bands = []
    previous_advance = None
    for index in range(count):
        advance = (advance_start + advance_pitch * index).quantize(
            quantum,
            rounding=ROUND_HALF_UP,
        )
        if previous_advance is not None and advance <= previous_advance:
            raise ValueError(
                "sweep values must remain strictly increasing after rounding"
            )
        previous_advance = advance
        y_min = y_min_start + y_pitch * index
        bands.append(
            {
                "y_min": float(y_min),
                "y_max": float(y_min + band_height),
                "advance": float(advance),
                "label": f"{advance:.{label_decimals}f}",
            }
        )
    return tuple(bands)


def _parse_words(code: str) -> dict[str, float]:
    return {
        match.group(1).upper(): float(match.group(2))
        for match in _WORD_PATTERN.finditer(code)
    }


def _command(code: str) -> str:
    stripped = code.strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0].upper()


def _normalize_bands(
    bands: Sequence[Mapping[str, Any]],
) -> tuple[_PressureAdvanceBand, ...]:
    if not isinstance(bands, Sequence) or isinstance(bands, (str, bytes)):
        raise ValueError("bands must be a sequence of mappings")
    normalized = []
    for index, band in enumerate(bands):
        if not isinstance(band, Mapping):
            raise ValueError(f"bands[{index}] must be a mapping")
        y_min = float(band["y_min"])
        y_max = float(band["y_max"])
        advance = float(band["advance"])
        label = str(band.get("label", f"{advance:.2f}"))
        if not all(math.isfinite(value) for value in (y_min, y_max, advance)):
            raise ValueError(f"bands[{index}] values must be finite")
        if y_max <= y_min:
            raise ValueError(f"bands[{index}] y_max must be greater than y_min")
        if advance < 0:
            raise ValueError(f"bands[{index}] advance must be non-negative")
        normalized.append(_PressureAdvanceBand(y_min, y_max, advance, label))

    if not normalized:
        raise ValueError("bands must not be empty")
    ordered = tuple(sorted(normalized, key=lambda band: band.y_min))
    for previous, current in zip(ordered, ordered[1:]):
        if current.y_min < previous.y_max - _POSITION_EPSILON:
            raise ValueError("pressure-advance bands must not overlap")
    return ordered


def _band_index_for_y(y: float, bands: tuple[_PressureAdvanceBand, ...]) -> int | None:
    matches = [
        index
        for index, band in enumerate(bands)
        if band.y_min - _POSITION_EPSILON <= y <= band.y_max + _POSITION_EPSILON
    ]
    if len(matches) > 1:
        raise ValueError(f"Y={y:g} lies in overlapping pressure-advance bands")
    return matches[0] if matches else None


def _format_advance(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def apply_y_banded_pressure_advance(
    gcode_text: str,
    *,
    context,
    restore_advance,
    bands=None,
    sweep=None,
) -> str:
    """Insert pressure-advance changes for positive extrusion in configured Y bands."""

    del context
    if (bands is None) == (sweep is None):
        raise ValueError("exactly one of bands or sweep must be configured")
    normalized_bands = _normalize_bands(
        expand_pressure_advance_sweep(sweep) if sweep is not None else bands
    )
    restore_value = float(restore_advance)
    if not math.isfinite(restore_value) or restore_value < 0:
        raise ValueError("restore_advance must be a finite non-negative number")

    absolute_xyz = True
    absolute_e = True
    x = 0.0
    y = 0.0
    e = 0.0
    active_band_index = None
    encountered_band_indices: set[int] = set()
    output_lines: list[str] = []

    for line_number, line in enumerate(gcode_text.splitlines(keepends=True), start=1):
        code = line.split(";", 1)[0]
        command = _command(code)
        words = _parse_words(code)

        if command == "G90":
            absolute_xyz = True
        elif command == "G91":
            absolute_xyz = False
        elif command == "M82":
            absolute_e = True
        elif command == "M83":
            absolute_e = False
        elif command == "G92":
            if "X" in words:
                x = words["X"]
            if "Y" in words:
                y = words["Y"]
            if "E" in words:
                e = words["E"]
        elif command in {"G0", "G1", "G2", "G3"}:
            target_x = words.get("X", x) if absolute_xyz else x + words.get("X", 0.0)
            target_y = words.get("Y", y) if absolute_xyz else y + words.get("Y", 0.0)
            target_e = words.get("E", e) if absolute_e else e + words.get("E", 0.0)
            extrusion_delta = target_e - e
            if extrusion_delta > _EXTRUSION_EPSILON:
                if command in {"G2", "G3"}:
                    raise ValueError(
                        f"Unsupported extrusion arc at G-code line {line_number}"
                    )
                start_band_index = _band_index_for_y(y, normalized_bands)
                end_band_index = _band_index_for_y(target_y, normalized_bands)
                crosses_band_boundary = (
                    start_band_index != end_band_index
                    and abs(target_y - y) > _POSITION_EPSILON
                    and (start_band_index is not None or end_band_index is not None)
                )
                if not crosses_band_boundary:
                    band_index = end_band_index
                    if band_index is not None:
                        encountered_band_indices.add(band_index)
                        if active_band_index != band_index:
                            band = normalized_bands[band_index]
                            newline = "\r\n" if line.endswith("\r\n") else "\n"
                            output_lines.append(
                                "SET_PRESSURE_ADVANCE ADVANCE="
                                f"{_format_advance(band.advance)}"
                                f" ; shellforgepy PA calibration {band.label}{newline}"
                            )
                            active_band_index = band_index
            x = target_x
            y = target_y
            e = target_e

        output_lines.append(line)

    missing_indices = sorted(
        set(range(len(normalized_bands))) - encountered_band_indices
    )
    if missing_indices:
        missing_labels = ", ".join(
            normalized_bands[index].label for index in missing_indices
        )
        raise ValueError(
            "No positive extrusion was found in pressure-advance band(s): "
            + missing_labels
        )

    newline = "\r\n" if "\r\n" in gcode_text else "\n"
    restore_line = (
        "SET_PRESSURE_ADVANCE ADVANCE="
        f"{_format_advance(restore_value)}"
        f" ; shellforgepy PA calibration restore{newline}"
    )
    insertion_index = next(
        (
            index
            for index in range(len(output_lines) - 1, -1, -1)
            if output_lines[index].lstrip().startswith("; filament end gcode")
        ),
        len(output_lines),
    )
    output_lines.insert(insertion_index, restore_line)
    return "".join(output_lines)


__all__ = ["apply_y_banded_pressure_advance", "expand_pressure_advance_sweep"]
