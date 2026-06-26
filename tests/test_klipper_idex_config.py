import importlib.util
import re
from pathlib import Path

import pytest

from mege_ender_3v3ke_idex.designs import (
    two_material_offset_line_calibration_grid as grid_calibration,
    two_material_offset_line_calibration_grid_x as x_grid_calibration,
    two_material_offset_line_calibration_grid_y as y_grid_calibration,
)
from mege_ender_3v3ke_idex.designs.two_material_offset_line_calibration import (
    LINE_SEGMENT_LENGTH_MM,
    OFFSET_COUNT_EACH_SIDE,
    OFFSET_CANDIDATES_MM,
    OFFSET_STEP_MM,
    ZERO_CANDIDATE_INDEX,
    ZERO_LINE_SEGMENT_LENGTH_MM,
    format_offset_label,
    format_right_endpoint_label,
    parse_idex_calibration_values,
    segment_length_for_candidate,
    x_nominal_center_for_candidate,
    x_t1_center_for_endpoint_delta,
)


KLIPPER_CONFIG_DIR = (
    Path(__file__).resolve().parents[1] / "klipper_setup" / "klipper_config"
)
CONFIG_PATH = KLIPPER_CONFIG_DIR / "printer.cfg"
CALIB_PATH = KLIPPER_CONFIG_DIR / "calib.yaml"
TEMPLATE_PATH = KLIPPER_CONFIG_DIR / "printer.cfg.template"
GENERATOR_PATH = KLIPPER_CONFIG_DIR / "generate_printer_cfg.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_printer_cfg", GENERATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _calibration_source():
    return _load_generator_module().load_calibration(CALIB_PATH)


def _section(config_text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\n(?P<body>.*?)(?=^\[|\Z)",
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing [{name}] section"
    return match.group("body")


def _setting_float(section: str, setting_name: str) -> float:
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Missing setting {setting_name}"
    return float(match.group("value"))


def _macro_variable_float(section: str, variable_name: str) -> float:
    return _setting_float(section, f"variable_{variable_name}")


def test_printer_cfg_is_generated_from_calibration_source():
    generator = _load_generator_module()

    assert generator.render_config(CALIB_PATH, TEMPLATE_PATH) == CONFIG_PATH.read_text(
        encoding="utf-8"
    )
    assert (
        generator.main(
            [
                "--check",
                "--calib",
                str(CALIB_PATH),
                "--template",
                str(TEMPLATE_PATH),
                "--output",
                str(CONFIG_PATH),
            ]
        )
        == 0
    )


def test_printer_cfg_check_rejects_stale_output(tmp_path):
    generator = _load_generator_module()
    stale_cfg = tmp_path / "printer.cfg"
    stale_cfg.write_text("# stale\n", encoding="utf-8")

    assert (
        generator.main(
            [
                "--check",
                "--calib",
                str(CALIB_PATH),
                "--template",
                str(TEMPLATE_PATH),
                "--output",
                str(stale_cfg),
            ]
        )
        == 1
    )


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


def test_mainsail_pause_resume_cancel_macros_are_defined():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    pause = _section(config_text, "gcode_macro PAUSE")
    assert "rename_existing: PAUSE_BASE" in pause
    assert re.search(r"^\s*PAUSE_BASE\s*$", pause, flags=re.MULTILINE)

    resume = _section(config_text, "gcode_macro RESUME")
    assert "rename_existing: RESUME_BASE" in resume
    assert "RESUME_BASE {rawparams}" in resume

    cancel = _section(config_text, "gcode_macro CANCEL_PRINT")
    assert "rename_existing: CANCEL_PRINT_BASE" in cancel
    assert "M107" in cancel
    assert "TURN_OFF_HEATERS" in cancel
    assert "CLEAR_PAUSE" in cancel
    assert "_IDEX_CANCEL_PARK" in cancel
    assert cancel.rstrip().endswith("CANCEL_PRINT_BASE")
    assert "M84" not in cancel


def test_idex_cancel_park_is_homed_axis_guarded():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    cancel_park = _section(config_text, "gcode_macro _IDEX_CANCEL_PARK")

    assert '"z" in homed' in cancel_park
    assert '"x" in homed' in cancel_park
    assert '"y" in homed' in cancel_park
    assert "position.z|float + 5.0" in cancel_park
    assert "axis_max.z|float" in cancel_park
    assert "tool_state.active_tool|int == 0" in cancel_park
    assert "IDEX_SELECT_LEFT" in cancel_park
    assert "IDEX_SELECT_RIGHT" in cancel_park
    assert "axis_max.y|float - 5.0" in cancel_park
    assert "M84" not in cancel_park


def test_idex_next_printable_corner_cycles_exact_safe_corners():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    corner_macro = _section(config_text, "gcode_macro IDEX_NEXT_PRINTABLE_CORNER")

    assert "variable_corner_index: 0" in corner_macro
    assert "variable_x_min: 0.0" in corner_macro
    assert "variable_x_max: 244.0" in corner_macro
    assert "variable_y_min: 0.0" in corner_macro
    assert "variable_y_max: 290.0" in corner_macro
    assert "variable_z_travel: 10.0" in corner_macro
    assert "variable_z_touch: 0.0" in corner_macro
    assert "variable_xy_move_speed:" in corner_macro
    assert "variable_z_move_speed:" in corner_macro

    assert '"x" not in homed' in corner_macro
    assert '"y" not in homed' in corner_macro
    assert '"z" not in homed' in corner_macro
    assert "Home X, Y, and Z before running IDEX_NEXT_PRINTABLE_CORNER." in corner_macro

    assert "front-left" in corner_macro
    assert "front-right" in corner_macro
    assert "back-right" in corner_macro
    assert "back-left" in corner_macro
    assert "next_index = (index + 1) % 4" in corner_macro
    assert (
        "SET_GCODE_VARIABLE MACRO=IDEX_NEXT_PRINTABLE_CORNER "
        "VARIABLE=corner_index VALUE={next_index}"
    ) in corner_macro

    assert "tool_state.active_tool|int == 0" in corner_macro
    assert "IDEX_SELECT_LEFT" in corner_macro
    assert "IDEX_SELECT_RIGHT" in corner_macro

    z_travel_index = corner_macro.index("G1 Z{z_travel|float}")
    xy_index = corner_macro.index("G1 X{target_x} Y{target_y}")
    z_touch_index = corner_macro.index("G1 Z{z_touch|float}")
    assert z_travel_index < xy_index < z_touch_index


def test_idex_tool_selection_resets_next_printable_corner():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    reset_counter = (
        "SET_GCODE_VARIABLE MACRO=IDEX_NEXT_PRINTABLE_CORNER "
        "VARIABLE=corner_index VALUE=0"
    )

    for macro_name in ["T0", "T1"]:
        tool_macro = _section(config_text, f"gcode_macro {macro_name}")
        assert reset_counter in tool_macro


def test_idex_tool_offsets_are_current_machine_calibration():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    calibration = _calibration_source()
    t0 = calibration["tools"]["t0"]
    t1 = calibration["tools"]["t1"]
    stepper_x = _section(config_text, "stepper_x")
    tool_state = _section(config_text, "gcode_macro _IDEX_TOOL_STATE")
    dual_carriage = _section(config_text, "dual_carriage")
    stepper_y = _section(config_text, "stepper_y")
    stepper_z = _section(config_text, "stepper_z")

    assert "variable_t0_x_offset" not in tool_state
    assert "variable_t1_x_offset" not in tool_state
    assert "variable_t0_z_offset" not in tool_state

    assert _setting_float(stepper_x, "position_endstop") == pytest.approx(
        t0["x_endstop"]
    )
    assert _setting_float(stepper_x, "position_min") == pytest.approx(t0["x_endstop"])
    assert _setting_float(dual_carriage, "position_endstop") == pytest.approx(
        t1["x_endstop"]
    )
    assert _setting_float(dual_carriage, "position_max") == pytest.approx(
        t1["x_endstop"]
    )
    assert _setting_float(stepper_y, "position_endstop") == pytest.approx(
        t0["y_endstop"]
    )
    assert _setting_float(stepper_y, "position_min") == pytest.approx(t0["y_endstop"])
    assert _setting_float(stepper_z, "position_endstop") == pytest.approx(
        t0["z_endstop"]
    )
    assert _setting_float(stepper_z, "position_max") == pytest.approx(t0["z_endstop"])

    assert _macro_variable_float(tool_state, "t0_y_endstop") == pytest.approx(
        t0["y_endstop"]
    )
    assert _macro_variable_float(tool_state, "t1_y_endstop") == pytest.approx(
        t1["y_endstop"]
    )
    assert _macro_variable_float(tool_state, "t0_z_endstop") == pytest.approx(
        t0["z_endstop"]
    )
    assert _macro_variable_float(tool_state, "t1_z_endstop") == pytest.approx(
        t1["z_endstop"]
    )
    assert _macro_variable_float(tool_state, "t0_y_offset") == pytest.approx(0.000)
    assert _macro_variable_float(tool_state, "t1_y_offset") == pytest.approx(
        t0["y_endstop"] - t1["y_endstop"]
    )
    assert _macro_variable_float(tool_state, "t1_z_offset") == pytest.approx(
        t0["z_endstop"] - t1["z_endstop"]
    )


def test_grid_calibration_reads_current_calibration_source():
    calibration = _calibration_source()
    bed_grid_zero = calibration["bed_grid_zero"]
    t0 = calibration["tools"]["t0"]
    t1 = calibration["tools"]["t1"]
    values = grid_calibration.read_grid_calibration(CALIB_PATH)

    assert values["bed_grid_zero"] == pytest.approx(
        (bed_grid_zero["x"], bed_grid_zero["y"])
    )
    assert values["t0_x_endstop"] == pytest.approx(t0["x_endstop"])
    assert values["t1_x_endstop"] == pytest.approx(t1["x_endstop"])
    assert values["t0_y_endstop"] == pytest.approx(t0["y_endstop"])
    assert values["t1_y_endstop"] == pytest.approx(t1["y_endstop"])


def test_offset_line_calibration_parses_active_calibration_values():
    calibration = _calibration_source()
    t0 = calibration["tools"]["t0"]
    t1 = calibration["tools"]["t1"]
    values = parse_idex_calibration_values(CONFIG_PATH.read_text(encoding="utf-8"))

    assert values["right_x_endpoint"] == pytest.approx(t1["x_endstop"])
    assert values["t0_y"] == pytest.approx(0.0)
    assert values["t1_y"] == pytest.approx(t0["y_endstop"] - t1["y_endstop"])


def test_offset_line_calibration_rejects_nonzero_t0_y_offset():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config_text = re.sub(
        r"variable_t0_y_offset: \S+",
        "variable_t0_y_offset: 0.1",
        config_text,
    )

    with pytest.raises(ValueError, match="T0 Y offset must be 0.0"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_rejects_x_tool_offsets():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config_text = re.sub(
        r"variable_t0_y_offset: \S+",
        "variable_t0_x_offset: 0.0\nvariable_t0_y_offset: 0.0",
        config_text,
    )

    with pytest.raises(ValueError, match="variable_t0_x_offset"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_rejects_mismatched_right_endpoint_values():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    dual_carriage = _section(config_text, "dual_carriage")
    right_endpoint = _setting_float(dual_carriage, "position_endstop")
    mismatched_max = right_endpoint - 0.2
    modified_dual_carriage, replacement_count = re.subn(
        r"(?m)^position_max: \S+",
        f"position_max: {mismatched_max:.3f}",
        dual_carriage,
        count=1,
    )
    assert replacement_count == 1
    config_text = config_text.replace(dual_carriage, modified_dual_carriage, 1)

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


def test_offset_line_calibration_candidates_are_centered_on_zero():
    assert len(OFFSET_CANDIDATES_MM) == 2 * OFFSET_COUNT_EACH_SIDE + 1
    assert OFFSET_CANDIDATES_MM[ZERO_CANDIDATE_INDEX] == 0.0
    assert OFFSET_CANDIDATES_MM[0] == pytest.approx(
        -OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert OFFSET_CANDIDATES_MM[-1] == pytest.approx(
        OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )

    for index, candidate_offset in enumerate(OFFSET_CANDIDATES_MM):
        mirror_index = 2 * ZERO_CANDIDATE_INDEX - index
        assert OFFSET_CANDIDATES_MM[mirror_index] == pytest.approx(-candidate_offset)


def test_offset_line_calibration_long_marker_is_center_zero_candidate():
    for index in range(len(OFFSET_CANDIDATES_MM)):
        if index == ZERO_CANDIDATE_INDEX:
            assert segment_length_for_candidate(index) == ZERO_LINE_SEGMENT_LENGTH_MM
        else:
            assert segment_length_for_candidate(index) == LINE_SEGMENT_LENGTH_MM


def test_offset_line_calibration_labels_active_current_offsets():
    values = parse_idex_calibration_values(CONFIG_PATH.read_text(encoding="utf-8"))

    x_labels = [
        format_right_endpoint_label(values["right_x_endpoint"] + candidate_offset)
        for candidate_offset in OFFSET_CANDIDATES_MM
    ]
    y_labels = [
        format_offset_label(values["t1_y"] + candidate_offset)
        for candidate_offset in OFFSET_CANDIDATES_MM
    ]

    assert x_labels[ZERO_CANDIDATE_INDEX] == format_right_endpoint_label(
        values["right_x_endpoint"]
    )
    assert y_labels[ZERO_CANDIDATE_INDEX] == format_offset_label(values["t1_y"])
    assert x_labels[0] == format_right_endpoint_label(
        values["right_x_endpoint"] - OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert x_labels[-1] == format_right_endpoint_label(
        values["right_x_endpoint"] + OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert y_labels[0] == format_offset_label(
        values["t1_y"] - OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert y_labels[-1] == format_offset_label(
        values["t1_y"] + OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )


def test_offset_line_calibration_x_endpoint_delta_moves_t1_opposite_direction():
    middle_index = len(OFFSET_CANDIDATES_MM) // 2
    nominal_x = x_nominal_center_for_candidate(middle_index)

    assert x_t1_center_for_endpoint_delta(middle_index, 0.1) == pytest.approx(
        nominal_x - 0.1
    )
    assert x_t1_center_for_endpoint_delta(middle_index, -0.1) == pytest.approx(
        nominal_x + 0.1
    )


def test_absolute_y_calibration_candidates_move_same_direction():
    painted_grid_y = 107.0

    assert y_grid_calibration.y_line_center_for_calibration_offset(
        painted_grid_y, 0.3
    ) == pytest.approx(106.7)
    assert y_grid_calibration.y_line_center_for_calibration_offset(
        painted_grid_y, -0.3
    ) == pytest.approx(107.3)


def test_absolute_grid_plate_definitions_split_y_calibration():
    plate_definitions = y_grid_calibration.create_plate_definitions(
        {
            y_grid_calibration.Y_T0_PLATE_NAME: ("y_t0_preview",),
            y_grid_calibration.Y_T1_PLATE_NAME: ("y_t1_preview",),
        }
    )

    assert [plate["name"] for plate in plate_definitions] == [
        y_grid_calibration.Y_T0_PLATE_NAME,
        y_grid_calibration.Y_T1_PLATE_NAME,
    ]
    assert plate_definitions[0]["parts"] == [
        "y_t0_preview",
        y_grid_calibration.Y_T0_LINES_PART_NAME,
        y_grid_calibration.Y_T0_LABELS_PART_NAME,
    ]
    assert plate_definitions[1]["parts"] == [
        "y_t1_preview",
        y_grid_calibration.Y_T1_LINES_PART_NAME,
        y_grid_calibration.Y_T1_LABELS_PART_NAME,
    ]


def test_absolute_grid_plate_definitions_split_x_calibration():
    plate_definitions = x_grid_calibration.create_plate_definitions(
        {
            x_grid_calibration.X_T0_PLATE_NAME: ("x_t0_preview",),
            x_grid_calibration.X_T1_PLATE_NAME: ("x_t1_preview",),
        }
    )

    assert [plate["name"] for plate in plate_definitions] == [
        x_grid_calibration.X_T0_PLATE_NAME,
        x_grid_calibration.X_T1_PLATE_NAME,
    ]
    assert plate_definitions[0]["parts"] == [
        "x_t0_preview",
        x_grid_calibration.X_T0_LINES_PART_NAME,
        x_grid_calibration.X_T0_LABELS_PART_NAME,
    ]
    assert plate_definitions[1]["parts"] == [
        "x_t1_preview",
        x_grid_calibration.X_T1_LINES_PART_NAME,
        x_grid_calibration.X_T1_LABELS_PART_NAME,
    ]


def test_absolute_grid_y_part_metadata_routes_base_and_text_materials():
    metadata = y_grid_calibration.CALIBRATION_PART_METADATA

    assert metadata[y_grid_calibration.Y_T0_LINES_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T0_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }
    assert metadata[y_grid_calibration.Y_T0_LABELS_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T0_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[y_grid_calibration.Y_T1_LINES_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T1_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[y_grid_calibration.Y_T1_LABELS_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T1_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }


def test_absolute_grid_x_part_metadata_routes_base_and_text_materials():
    metadata = x_grid_calibration.CALIBRATION_PART_METADATA

    assert metadata[x_grid_calibration.X_T0_LINES_PART_NAME] == {
        "production_group": x_grid_calibration.X_T0_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }
    assert metadata[x_grid_calibration.X_T0_LABELS_PART_NAME] == {
        "production_group": x_grid_calibration.X_T0_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[x_grid_calibration.X_T1_LINES_PART_NAME] == {
        "production_group": x_grid_calibration.X_T1_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[x_grid_calibration.X_T1_LABELS_PART_NAME] == {
        "production_group": x_grid_calibration.X_T1_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }


def test_absolute_grid_y_label_slab_is_calibrated_tool_material():
    calibration = grid_calibration.read_grid_calibration(CALIB_PATH)
    base_material, text_material = (
        y_grid_calibration.create_absolute_y_alignment_materials(
            bed_grid_zero=calibration["bed_grid_zero"],
            calibration_value_mm=calibration["t0_y_endstop"],
        )
    )

    base_min, _ = grid_calibration.get_bounding_box(base_material)
    text_min, text_max = grid_calibration.get_bounding_box(text_material)

    assert base_min[0] < text_min[0]
    assert base_min[0] == pytest.approx(grid_calibration.SAFE_BED_ORIGIN[0])
    assert text_min[1] < base_min[1]
    assert base_min[1] - text_min[1] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_GAP_MM
        + grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM
    )
    assert text_min[2] == pytest.approx(0.0)
    assert text_max[2] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_PAD_THICKNESS_MM
        + grid_calibration.CALIBRATION_LABEL_TEXT_THICKNESS_MM
    )


def test_absolute_grid_x_label_slab_has_writing_anchor():
    calibration = grid_calibration.read_grid_calibration(CALIB_PATH)
    base_material, text_material, _, _ = (
        x_grid_calibration.create_absolute_x_alignment_materials(calibration)
    )

    base_min, _ = grid_calibration.get_bounding_box(base_material)
    text_min, text_max = grid_calibration.get_bounding_box(text_material)

    assert text_min[1] < base_min[1]
    assert base_min[1] - text_min[1] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_GAP_MM
        + grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM
    )
    assert text_min[2] == pytest.approx(0.0)
    assert text_max[2] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_PAD_THICKNESS_MM
        + grid_calibration.CALIBRATION_LABEL_TEXT_THICKNESS_MM
    )


def test_absolute_grid_x_and_y_parts_fit_dual_area():
    calibration = grid_calibration.read_grid_calibration(CALIB_PATH)
    x_parts = x_grid_calibration.create_absolute_x_alignment_materials(calibration)
    y_t0_parts = y_grid_calibration.create_absolute_y_alignment_materials(
        bed_grid_zero=calibration["bed_grid_zero"],
        calibration_value_mm=calibration["t0_y_endstop"],
    )
    y_t1_parts = y_grid_calibration.create_absolute_y_alignment_materials(
        bed_grid_zero=calibration["bed_grid_zero"],
        calibration_value_mm=calibration["t1_y_endstop"],
    )

    grid_calibration.assert_absolute_patterns_fit_dual_area(
        [*x_parts, *y_t0_parts, *y_t1_parts]
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


def test_idex_tool_offset_macro_clears_x_and_rejects_t0_runtime_updates():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    apply_offset = _section(config_text, "gcode_macro _IDEX_APPLY_TOOL_OFFSET")
    set_offset = _section(config_text, "gcode_macro IDEX_SET_TOOL_OFFSET")

    assert "SET_GCODE_OFFSET X=0 Y={y} Z={z}" in apply_offset
    assert "t0_x_offset" not in apply_offset
    assert "t1_x_offset" not in apply_offset
    assert "state.t0_z_offset" not in apply_offset
    assert "{% set z = 0.0 %}" in apply_offset
    assert "state.t1_z_offset|float" in apply_offset
    assert "params.X is defined" in set_offset
    assert "position_endstop and position_max together" in set_offset
    assert "params.Z is defined and tool == 0" in set_offset
    assert "T0 Z is calibrated mechanically" in set_offset
    assert "VARIABLE=t{tool}_x_offset" not in set_offset
