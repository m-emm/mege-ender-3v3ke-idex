import re
from pathlib import Path

import pytest

from mege_ender_3v3ke_idex.designs.two_material_offset_line_calibration import (
    OFFSET_CANDIDATES_MM,
    format_offset_label,
    format_right_endpoint_label,
    parse_idex_calibration_values,
    x_nominal_center_for_candidate,
    x_t1_center_for_endpoint_delta,
)


CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "klipper_setup"
    / "klipper_config"
    / "printer.cfg"
)


def _section(config_text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\n(?P<body>.*?)(?=^\[|\Z)",
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing [{name}] section"
    return match.group("body")


def test_idex_part_fan_pins_and_slicer_routing():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    assert "pin: nitehawk:gpio6" in _section(config_text, "fan_generic left_part_fan")
    assert "pin: right_nitehawk:gpio6" in _section(
        config_text, "fan_generic right_part_fan"
    )

    fan_state = _section(config_text, "gcode_macro _IDEX_PART_FAN_STATE")
    assert "variable_speed: 0.0" in fan_state

    m106 = _section(config_text, "gcode_macro M106")
    assert "rename_existing" not in m106
    assert "SET_GCODE_VARIABLE MACRO=_IDEX_PART_FAN_STATE VARIABLE=speed" in m106
    assert "_IDEX_APPLY_PART_FAN TOOL={tool_state.active_tool|int}" in m106

    m107 = _section(config_text, "gcode_macro M107")
    assert "rename_existing" not in m107
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED=0" in m107
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED=0" in m107

    apply_fan = _section(config_text, "gcode_macro _IDEX_APPLY_PART_FAN")
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED={speed}" in apply_fan
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED=0" in apply_fan
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED={speed}" in apply_fan
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED=0" in apply_fan

    diagnostic = _section(config_text, "gcode_macro IDEX_SET_PART_FAN")
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED={speed}" in diagnostic
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED={speed}" in diagnostic

    assert "_IDEX_APPLY_PART_FAN TOOL=0" in _section(config_text, "gcode_macro T0")
    assert "_IDEX_APPLY_PART_FAN TOOL=1" in _section(config_text, "gcode_macro T1")


def test_idex_tool_offsets_are_current_machine_calibration():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    tool_state = _section(config_text, "gcode_macro _IDEX_TOOL_STATE")
    dual_carriage = _section(config_text, "dual_carriage")

    assert "variable_t0_x_offset" not in tool_state
    assert "variable_t1_x_offset" not in tool_state
    assert "variable_t0_y_offset: 0.0" in tool_state
    assert "variable_t0_z_offset: -0.25" in tool_state
    assert "variable_t1_y_offset: -0.1" in tool_state
    assert "variable_t1_z_offset: -0.2" in tool_state

    assert "position_endstop: 344.900" in dual_carriage
    assert "position_max: 344.900" in dual_carriage


def test_offset_line_calibration_parses_active_calibration_values():
    values = parse_idex_calibration_values(CONFIG_PATH.read_text(encoding="utf-8"))

    assert values == {
        "right_x_endpoint": 344.9,
        "t0_y": 0.0,
        "t1_y": -0.1,
    }


def test_offset_line_calibration_rejects_nonzero_t0_y_offset():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config_text = config_text.replace(
        "variable_t0_y_offset: 0.0",
        "variable_t0_y_offset: 0.1",
    )

    with pytest.raises(ValueError, match="T0 Y offset must be 0.0"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_rejects_x_tool_offsets():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config_text = config_text.replace(
        "variable_t0_y_offset: 0.0",
        "variable_t0_x_offset: 0.0\nvariable_t0_y_offset: 0.0",
    )

    with pytest.raises(ValueError, match="variable_t0_x_offset"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_rejects_mismatched_right_endpoint_values():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config_text = config_text.replace(
        "position_endstop: 344.900\nposition_min: 0.000\nposition_max: 344.900",
        "position_endstop: 344.900\nposition_min: 0.000\nposition_max: 345.000",
    )

    with pytest.raises(ValueError, match="position_endstop and position_max"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_formats_offset_labels():
    assert format_offset_label(0.0) == "0.0"
    assert format_offset_label(-0.0) == "0.0"
    assert format_offset_label(0.14) == "0.1"
    assert format_offset_label(-0.64) == "-0.6"


def test_offset_line_calibration_formats_right_endpoint_labels():
    assert format_right_endpoint_label(344.4) == "4.4"
    assert format_right_endpoint_label(344.9) == "4.9"
    assert format_right_endpoint_label(345.0) == "5.0"
    assert format_right_endpoint_label(345.4) == "5.4"


def test_offset_line_calibration_labels_active_current_offsets():
    values = parse_idex_calibration_values(CONFIG_PATH.read_text(encoding="utf-8"))
    middle_index = len(OFFSET_CANDIDATES_MM) // 2

    x_labels = [
        format_right_endpoint_label(values["right_x_endpoint"] + candidate_offset)
        for candidate_offset in OFFSET_CANDIDATES_MM
    ]
    y_labels = [
        format_offset_label(values["t1_y"] + candidate_offset)
        for candidate_offset in OFFSET_CANDIDATES_MM
    ]

    assert x_labels[middle_index] == "4.9"
    assert y_labels[middle_index] == "-0.1"
    assert x_labels[0] == "4.4"
    assert x_labels[-1] == "5.4"
    assert y_labels[0] == "-0.6"
    assert y_labels[-1] == "0.4"


def test_offset_line_calibration_x_endpoint_delta_moves_t1_opposite_direction():
    middle_index = len(OFFSET_CANDIDATES_MM) // 2
    nominal_x = x_nominal_center_for_candidate(middle_index)

    assert x_t1_center_for_endpoint_delta(middle_index, 0.1) == pytest.approx(
        nominal_x - 0.1
    )
    assert x_t1_center_for_endpoint_delta(middle_index, -0.1) == pytest.approx(
        nominal_x + 0.1
    )


def test_idex_tool_parking_uses_full_speed_travel():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    tool_state = _section(config_text, "gcode_macro _IDEX_TOOL_STATE")
    select_left = _section(config_text, "gcode_macro IDEX_SELECT_LEFT")
    select_right = _section(config_text, "gcode_macro IDEX_SELECT_RIGHT")

    assert "variable_park_move_speed: 180.0" in tool_state
    for select_macro in [select_left, select_right]:
        assert "park_move_speed|float * 60.0" in select_macro
        assert "F{park_feed}" in select_macro
        assert "F3000" not in select_macro


def test_idex_tool_parking_uses_absolute_edges():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    select_left = _section(config_text, "gcode_macro IDEX_SELECT_LEFT")
    select_right = _section(config_text, "gcode_macro IDEX_SELECT_RIGHT")

    for select_macro in [select_left, select_right]:
        assert "dual_carriage.position_max|float" in select_macro
        assert "x_positive_offset_clearance" not in select_macro
        assert "x_negative_offset_clearance" not in select_macro

    assert "stepper_x.position_min|float" in select_right


def test_idex_tool_offset_macro_clears_x_and_rejects_x_runtime_updates():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    apply_offset = _section(config_text, "gcode_macro _IDEX_APPLY_TOOL_OFFSET")
    set_offset = _section(config_text, "gcode_macro IDEX_SET_TOOL_OFFSET")

    assert "SET_GCODE_OFFSET X=0 Y={y} Z={z}" in apply_offset
    assert "t0_x_offset" not in apply_offset
    assert "t1_x_offset" not in apply_offset
    assert "params.X is defined" in set_offset
    assert "position_endstop and position_max together" in set_offset
    assert "VARIABLE=t{tool}_x_offset" not in set_offset
