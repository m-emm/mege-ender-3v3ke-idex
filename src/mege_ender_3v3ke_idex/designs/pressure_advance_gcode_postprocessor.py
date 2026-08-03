"""Y-banded pressure-advance calibration G-code postprocessor."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
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
    bands,
    restore_advance,
) -> str:
    """Insert pressure-advance changes for positive extrusion in configured Y bands."""

    del context
    normalized_bands = _normalize_bands(bands)
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


__all__ = ["apply_y_banded_pressure_advance"]
