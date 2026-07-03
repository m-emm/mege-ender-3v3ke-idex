import importlib.util
import re
import sys
from datetime import datetime
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
Y_STEP_LOSS_GENERATOR_PATH = KLIPPER_CONFIG_DIR / "generate_y_step_loss_test_gcode.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_printer_cfg", GENERATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_y_step_loss_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_y_step_loss_test_gcode", Y_STEP_LOSS_GENERATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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


def _setting_value(section: str, setting_name: str) -> str:
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Missing setting {setting_name}"
    return match.group("value")


def _macro_variable_float(section: str, variable_name: str) -> float:
    return _setting_float(section, f"variable_{variable_name}")


def _live_config_status(
    fingerprint: str | None,
    *,
    state: str = "ready",
    save_config_pending: bool = False,
) -> dict:
    macro_config = {}
    if fingerprint is not None:
        macro_config["variable_source_sha256"] = f'"{fingerprint}"'
    return {
        "webhooks": {"state": state},
        "configfile": {
            "save_config_pending": save_config_pending,
            "config": {"gcode_macro _IDEX_CONFIG_FINGERPRINT": macro_config},
        },
    }


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


def test_printer_cfg_includes_generated_fingerprint_macro():
    generator = _load_generator_module()
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    fingerprint = generator.compute_config_fingerprint(CALIB_PATH, TEMPLATE_PATH)
    fingerprint_section = _section(config_text, "gcode_macro _IDEX_CONFIG_FINGERPRINT")

    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert f'variable_source_sha256: "{fingerprint}"' in fingerprint_section


def test_printer_motion_limits_match_proven_idex_axes():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    printer = _section(config_text, "printer")

    assert _setting_float(printer, "max_velocity") == pytest.approx(500.0)
    assert _setting_float(printer, "max_accel") == pytest.approx(8000.0)
    assert _setting_float(printer, "max_z_velocity") == pytest.approx(30.0)
    assert _setting_float(printer, "max_z_accel") == pytest.approx(300.0)
    assert _setting_float(printer, "square_corner_velocity") == pytest.approx(10.0)
    assert "[force_move]" not in config_text


def test_stepper_y_uses_tb6600_20t_gt2_pulley_config():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    stepper_y = _section(config_text, "stepper_y")

    assert _setting_value(stepper_y, "step_pin") == "gpio0"
    assert _setting_value(stepper_y, "dir_pin") == "!gpio1"
    assert _setting_value(stepper_y, "enable_pin") == "gpio2"
    assert _setting_float(stepper_y, "microsteps") == pytest.approx(16.0)
    assert _setting_float(stepper_y, "rotation_distance") == pytest.approx(40.0)


def test_y_step_loss_assert_macro_checks_stepper_y_endstop():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    macro = _section(config_text, "gcode_macro Y_STEP_LOSS_ASSERT_ENDSTOP")

    assert 'printer.query_endstops.last_query["stepper_y"]' in macro
    assert "action_raise_error" in macro
    assert "profile=" in macro
    assert "velocity=" in macro
    assert "Re-home Y before normal printing" in macro


def test_y_step_loss_generator_emits_print_motif_endstop_checks(tmp_path):
    generator = _load_y_step_loss_generator_module()
    printer = generator.load_printer_config(CONFIG_PATH)
    gcode = generator.generate_gcode(printer)
    output = tmp_path / "y_step_loss_characterization.gcode"

    assert generator.main(["--config", str(CONFIG_PATH), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == gcode
    assert not hasattr(generator, "load_y_axis_config")
    assert "--mode" not in generator.build_parser().format_help()

    lines = [line.strip() for line in gcode.splitlines() if line.strip()]
    assert "; Endstop verification key: stepper_y" in lines
    assert "; Z characterization height: 10.000" in lines
    assert "; Total endstop checks: 90" in lines
    assert "G28 X Y Z" in lines
    assert "G1 Z10.000 F600" in lines
    assert "G28 Y" not in lines
    assert "Y away distance" not in gcode

    assertion_lines = [
        line for line in lines if line.startswith("Y_STEP_LOSS_ASSERT_ENDSTOP ")
    ]
    assert len(assertion_lines) == 90
    profile_names = [
        re.search(r"\bPROFILE=(\S+)\b", line).group(1) for line in assertion_lines
    ]
    assert sorted(set(profile_names)) == [
        "accel_2500",
        "accel_3500",
        "accel_4500",
        "scv_3",
        "scv_5",
        "scv_8",
        "speed_300",
        "speed_350",
        "speed_400",
    ]
    assert {name: profile_names.count(name) for name in set(profile_names)} == {
        name: 10 for name in set(profile_names)
    }
    accel_values = [
        int(re.search(r"\bACCEL=(\d+)\b", line).group(1)) for line in assertion_lines
    ]
    assert sorted(set(accel_values)) == [2500, 3500, 4500]

    for index, line in enumerate(lines):
        if line.startswith("Y_STEP_LOSS_ASSERT_ENDSTOP "):
            assert lines[index - 1] == "QUERY_ENDSTOPS"

    motif_points = generator.transformed_print_motif_points(printer)
    high_stress_anchor = motif_points[generator.PRINT_MOTIF_ENDSTOP_GAP_ANCHOR_INDEX]
    assert high_stress_anchor.y == pytest.approx(printer.y_position_endstop + 5.0)
    assert any(
        (
            f"X{generator._format_float(high_stress_anchor.x)} "
            f"Y{generator._format_float(high_stress_anchor.y)}"
        )
        in line
        for line in lines
    )

    stepper_x = _section(CONFIG_PATH.read_text(encoding="utf-8"), "stepper_x")
    stepper_y = _section(CONFIG_PATH.read_text(encoding="utf-8"), "stepper_y")
    stepper_z = _section(CONFIG_PATH.read_text(encoding="utf-8"), "stepper_z")
    x_min = _setting_float(stepper_x, "position_min")
    x_max = _setting_float(stepper_x, "position_max")
    y_min = _setting_float(stepper_y, "position_min")
    y_max = _setting_float(stepper_y, "position_max")
    z_min = _setting_float(stepper_z, "position_min")
    z_max = _setting_float(stepper_z, "position_max")
    x_targets = [
        float(match.group(1)) for match in re.finditer(r"\bX(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    y_targets = [
        float(match.group(1)) for match in re.finditer(r"\bY(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    z_targets = [
        float(match.group(1)) for match in re.finditer(r"\bZ(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    assert x_targets
    assert y_targets
    assert z_targets
    assert min(x_targets) >= x_min - 1e-9
    assert max(x_targets) <= x_max + 1e-9
    assert min(y_targets) >= y_min - 1e-9
    assert max(y_targets) <= y_max + 1e-9
    assert min(z_targets) >= z_min - 1e-9
    assert max(z_targets) <= z_max + 1e-9


def test_y_step_loss_generator_default_output_path_is_timestamped(tmp_path):
    generator = _load_y_step_loss_generator_module()

    output_path = generator.timestamped_output_path(
        tmp_path,
        now=datetime(2026, 7, 2, 10, 1, 58),
    )

    assert (
        output_path == tmp_path / "y_step_loss_characterization_20260702_100158.gcode"
    )


def test_config_fingerprint_changes_when_source_inputs_change(tmp_path):
    generator = _load_generator_module()
    calib = tmp_path / "calib.yaml"
    template = tmp_path / "printer.cfg.template"
    calib_text = CALIB_PATH.read_text(encoding="utf-8")
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    calib.write_text(calib_text, encoding="utf-8")
    template.write_text(template_text, encoding="utf-8")

    original = generator.compute_config_fingerprint(calib, template)
    calib.write_text(f"{calib_text}\n# changed calibration source\n", encoding="utf-8")
    assert generator.compute_config_fingerprint(calib, template) != original

    calib.write_text(calib_text, encoding="utf-8")
    template.write_text(
        f"{template_text}\n# changed template source\n", encoding="utf-8"
    )
    assert generator.compute_config_fingerprint(calib, template) != original


def test_live_config_check_accepts_matching_ready_config():
    generator = _load_generator_module()
    fingerprint = "a" * 64

    assert (
        generator.live_config_check_errors(
            local_sha256="b" * 64,
            remote_sha256="b" * 64,
            expected_fingerprint=fingerprint,
            status=_live_config_status(fingerprint),
        )
        == []
    )


def test_live_config_check_rejects_remote_hash_mismatch():
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="b" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status("c" * 64),
    )

    assert any("sha256 does not match" in error for error in errors)


@pytest.mark.parametrize("live_fingerprint", [None, "d" * 64])
def test_live_config_check_rejects_missing_or_different_live_fingerprint(
    live_fingerprint,
):
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="a" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status(live_fingerprint),
    )

    assert errors
    assert any("fingerprint" in error for error in errors)


def test_live_config_check_rejects_non_ready_klippy_state():
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="a" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status("c" * 64, state="startup"),
    )

    assert any("expected 'ready'" in error for error in errors)


def test_live_config_check_rejects_pending_save_config():
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="a" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status("c" * 64, save_config_pending=True),
    )

    assert any("save_config_pending" in error for error in errors)


def test_boosted_heatbed_config_uses_measured_60c_pid():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    heater_bed = _section(config_text, "heater_bed")

    assert "heater_pin: gpio21" in heater_bed
    assert "boost_pin: gpio20" in heater_bed
    assert _setting_float(heater_bed, "primary_heater_power") == pytest.approx(240.0)
    assert _setting_float(heater_bed, "boost_heater_power") == pytest.approx(500.0)
    assert _setting_float(heater_bed, "pwm_cycle_time") == pytest.approx(2.0)
    assert "sensor_pin: gpio26" in heater_bed
    assert "control: pid" in heater_bed
    assert _setting_float(heater_bed, "pid_Kp") == pytest.approx(31.396)
    assert _setting_float(heater_bed, "pid_Ki") == pytest.approx(0.337)
    assert _setting_float(heater_bed, "pid_Kd") == pytest.approx(731.124)
    assert "max_delta:" not in heater_bed


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


def test_bed_cooling_macro_moves_t0_to_center_and_waits_for_target():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    bed_cooling = _section(config_text, "gcode_macro BED_COOLING")

    assert _macro_variable_float(bed_cooling, "target") == pytest.approx(40.0)
    assert _macro_variable_float(bed_cooling, "x_center") == pytest.approx(122.0)
    assert _macro_variable_float(bed_cooling, "y_center") == pytest.approx(145.0)
    assert _macro_variable_float(bed_cooling, "z_height") == pytest.approx(5.0)
    assert _macro_variable_float(bed_cooling, "xy_move_speed") == pytest.approx(60.0)
    assert _macro_variable_float(bed_cooling, "z_move_speed") == pytest.approx(20.0)
    assert _macro_variable_float(bed_cooling, "fan_speed") == pytest.approx(1.0)

    assert "params.TARGET|default(target)|float" in bed_cooling
    assert "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0" in bed_cooling
    assert '"x" not in homed or "y" not in homed or "z" not in homed' in bed_cooling
    assert re.search(r"^\s*G28\s*$", bed_cooling, flags=re.MULTILINE)
    assert re.search(r"^\s*T0\s*$", bed_cooling, flags=re.MULTILINE)
    assert "G1 Z{z} F{z_feed}" in bed_cooling
    assert "G1 X{x} Y{y} F{xy_feed}" in bed_cooling
    assert "IDEX_SET_PART_FAN TOOL=both SPEED={fan_speed}" in bed_cooling
    assert "TEMPERATURE_WAIT SENSOR=heater_bed MAXIMUM={target_temp}" in bed_cooling
    assert re.search(r"^\s*M107\s*$", bed_cooling, flags=re.MULTILINE)


def test_x_travel_test_macros_are_gui_safe_and_test_both_toolheads():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    expected_macros = [
        ("TEST_X_TRAVEL_ACCEL_FOURK", 4000),
        ("TEST_X_TRAVEL_ACCEL_SIXK", 6000),
        ("TEST_X_TRAVEL_ACCEL_EIGHTK", 8000),
    ]

    alias = _section(config_text, "gcode_macro TEST_X_TRAVEL")
    assert "TEST_X_TRAVEL_ACCEL_FOURK" in alias

    for macro_name, accel in expected_macros:
        macro = _section(config_text, f"gcode_macro {macro_name}")
        assert f"_TEST_X_TRAVEL_RUN ACCEL={accel}" in macro

    runner = _section(config_text, "gcode_macro _TEST_X_TRAVEL_RUN")
    assert "printer.configfile.settings.stepper_x" in runner
    assert "printer.configfile.settings.dual_carriage" in runner
    assert "(left_min + left_max) / 2.0" in runner
    assert "(right_min + right_max) / 2.0" in runner
    assert "SET_DUAL_CARRIAGE CARRIAGE=0 MODE=PRIMARY" in runner
    assert "SET_DUAL_CARRIAGE CARRIAGE=1 MODE=PRIMARY" in runner
    assert "G1 X{left_park_x} F{park_feed}" in runner
    assert "G1 X{right_park_x} F{park_feed}" in runner
    assert "G1 X{left_mid} F{center_velocity * 60.0}" in runner
    assert "G1 X{left_target} F{test_velocity * 60.0}" in runner
    assert "G1 X{right_mid} F{center_velocity * 60.0}" in runner
    assert "G1 X{right_target} F{test_velocity * 60.0}" in runner
    assert re.search(r"^\s*G28 X\s*$", runner, flags=re.MULTILINE)
    assert re.search(r"^\s*T0\s*$", runner, flags=re.MULTILINE) is None
    assert re.search(r"^\s*T1\s*$", runner, flags=re.MULTILINE) is None
    assert "SAVE_GCODE_STATE NAME=TEST_X_TRAVEL_STATE" not in runner
    assert "RESTORE_GCODE_STATE NAME=TEST_X_TRAVEL_STATE" not in runner

    assert "gcode_macro TEST_Y_TRAVEL" not in config_text
    assert "gcode_macro _TEST_Y_TRAVEL_RUN" not in config_text
    assert "TEST_Y_TRAVEL_ACCEL_FOURK" not in config_text
    assert "TEST_Y_TRAVEL_ACCEL_EIGHTK" not in config_text

    assert "gcode_macro Y_TEST_TRAVEL_100" not in config_text
    assert "Y_TEST_TRAVEL_100_A4000" not in config_text


def test_x_driver_currents_are_raised_for_travel_testing():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    left_x_tmc = _section(config_text, "tmc2209 stepper_x")
    right_x_tmc = _section(config_text, "tmc2209 dual_carriage")

    assert _setting_float(left_x_tmc, "run_current") == pytest.approx(1.4)
    assert _setting_float(right_x_tmc, "run_current") == pytest.approx(1.4)


def test_idex_tool_selection_skips_offset_move_at_axis_edges():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    for macro_name, tool in [("T0", 0), ("T1", 1)]:
        macro = _section(config_text, f"gcode_macro {macro_name}")
        assert "printer.toolhead.axis_minimum" in macro
        assert "printer.toolhead.axis_maximum" in macro
        assert "offset_target_y" in macro
        assert "offset_target_z" in macro
        assert "can_move_offsets" in macro
        assert f"_IDEX_APPLY_TOOL_OFFSET TOOL={tool} MOVE={{can_move_offsets}}" in macro
        assert "offset compensation move skipped at current Y/Z edge" in macro


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


def test_absolute_grid_x_materials_use_same_y_row_for_both_tools(monkeypatch):
    calibration = grid_calibration.read_grid_calibration(CALIB_PATH)
    calls = []

    def create_pattern_spy(**kwargs):
        calls.append(kwargs)
        return object(), object()

    monkeypatch.setattr(
        x_grid_calibration,
        "create_absolute_x_alignment_pattern",
        create_pattern_spy,
    )

    x_grid_calibration.create_absolute_x_alignment_materials(calibration)

    assert len(calls) == 2
    assert (
        calls[0]["line_y_min_mm"]
        == calls[1]["line_y_min_mm"]
        == pytest.approx(
            grid_calibration.grid_coordinate(calibration["bed_grid_zero"][1], -1)
        )
    )
    assert (
        calls[0]["line_y_max_mm"]
        == calls[1]["line_y_max_mm"]
        == pytest.approx(
            grid_calibration.grid_coordinate(calibration["bed_grid_zero"][1], 0)
        )
    )
    assert calls[0]["label_panel"] is calls[1]["label_panel"]
    assert calls[0]["label_panel"]["name"] == "z_guide_panel_outline"


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
