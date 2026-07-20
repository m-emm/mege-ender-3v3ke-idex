import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
KLIPPER_CONFIG_DIR = REPO_ROOT / "klipper_setup" / "klipper_config"
WIRING_DIR = KLIPPER_CONFIG_DIR / "wiring"
VALIDATOR_PATH = WIRING_DIR / "validate_wiring.py"
TMC5160_REVIEW_PATH = WIRING_DIR / "rp2040plus_btt_tmc5160t_plus_y.yaml"
MEGE_CIRCUITS_SRC = REPO_ROOT.parent / "mege-circuits" / "src"


EXPECTED_KLIPPER_TAGS = {
    "stepper_x.step_pin",
    "stepper_x.dir_pin",
    "stepper_x.enable_pin",
    "stepper_x.endstop_pin",
    "tmc2209 stepper_x.uart_pin",
    "dual_carriage.step_pin",
    "dual_carriage.dir_pin",
    "dual_carriage.enable_pin",
    "dual_carriage.endstop_pin",
    "tmc2209 dual_carriage.uart_pin",
    "stepper_y.step_pin",
    "stepper_y.dir_pin",
    "stepper_y.enable_pin",
    "stepper_y.endstop_pin",
    "tmc2209 stepper_y.uart_pin",
    "gcode_button y_tmc_diag.pin",
    "dotstar vision_light.clock_pin",
    "dotstar vision_light.data_pin",
    "stepper_z.step_pin",
    "stepper_z.dir_pin",
    "stepper_z.enable_pin",
    "stepper_z.endstop_pin",
    "tmc2209 stepper_z.uart_pin",
    "stepper_z1.step_pin",
    "stepper_z1.dir_pin",
    "stepper_z1.enable_pin",
    "stepper_z1.endstop_pin",
    "tmc2209 stepper_z1.uart_pin",
    "heater_bed.heater_pin",
    "heater_bed.boost_pin",
    "heater_bed.sensor_pin",
}


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_wiring", VALIDATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_tmc5160_review_wiring():
    return yaml.safe_load(TMC5160_REVIEW_PATH.read_text(encoding="utf-8"))


def _pin_sets_with_prefix(wiring, prefix):
    return [pin_set for pin_set in wiring["pin_sets"] if pin_set["prefix"] == prefix]


def test_active_wiring_matches_klipper_template():
    validator = _load_validator_module()

    assert validator.validate_wiring() == []


def test_active_wiring_tags_cover_expected_pico_klipper_pins():
    validator = _load_validator_module()
    tags = set(validator.iter_tagged_wiring_refs(validator.DEFAULT_WIRING_FILES))

    assert tags == EXPECTED_KLIPPER_TAGS


def test_generated_wiring_svgs_are_current():
    subprocess.run(
        [str(WIRING_DIR / "generate_wiring_svgs.sh"), "--check"],
        cwd=REPO_ROOT,
        check=True,
    )


def test_tmc5160_review_wiring_loads_and_renders_with_mege_circuits(tmp_path):
    env = os.environ.copy()
    if MEGE_CIRCUITS_SRC.is_dir():
        prior_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(MEGE_CIRCUITS_SRC)
        if prior_pythonpath:
            env["PYTHONPATH"] += os.pathsep + prior_pythonpath

    subprocess.run(
        [
            sys.executable,
            "-m",
            "mege_circuits.pinout",
            str(TMC5160_REVIEW_PATH),
            "-o",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )

    for view in ("top", "bottom"):
        svg = tmp_path / f"rp2040plus_btt_tmc5160t_plus_y_{view}.svg"
        assert svg.is_file()
        assert svg.stat().st_size > 0


def test_tmc5160_review_wiring_uses_stepstick_spi_adapter_pattern():
    wiring = _load_tmc5160_review_wiring()
    j1 = _pin_sets_with_prefix(wiring, "TMC1_J1_")[0]
    top = _pin_sets_with_prefix(wiring, "TMC1_TOP_")[0]

    assert j1["pins"] == [
        "EN_1",
        "MOSI_CFG1_2",
        "SCK_CFG2_3",
        "CS_CFG3_4",
        "MISO_CFG0_5",
        "CLK_NC_6",
        "STEP_7",
        "DIR_8",
    ]
    assert _pin_sets_with_prefix(wiring, "TMC1_J2_")[0]["pins"] == [
        "VM_1",
        "GND_MOTOR_2",
        "B2_NC_3",
        "B1_NC_4",
        "A1_NC_5",
        "A2_NC_6",
        "VIO_7",
        "GND_LOGIC_8",
    ]
    assert top["pins"] == ["DIAG"]
    assert top["origin"] == [j1["origin"][0] + 1, j1["origin"][1] + 1]


def test_tmc5160_review_wiring_has_three_true_2x10_component_carriers():
    wiring = _load_tmc5160_review_wiring()
    expected_pairs = {
        "A_": [
            ("01_R1_24V", "20_R1_DZ1"),
            ("02_DZ1_K", "19_DZ1_A"),
            ("03_R2_VBUS", "18_R2_BASE"),
            ("04_R3_BASE", "17_R3_U2A"),
            ("05_R4_Q1C", "16_R4_VIO"),
            ("06_R5_VIO", "15_R5_GND"),
            ("07_DZ2_K", "14_DZ2_A"),
            ("08_Q1_C", "13_NC"),
            ("09_Q1_B", "12_NC"),
            ("10_Q1_E", "11_NC"),
        ],
        "B_": [
            ("01_D1_K", "20_D1_A"),
            ("02_R6_3V3", "19_R6_PWR_OK"),
            ("03_R7_3V3", "18_R7_STEP"),
            ("04_R8_3V3", "17_R8_DIR"),
            ("05_R9_3V3", "16_R9_ENABLE"),
            ("06_R10_3V3", "15_R10_CS"),
            ("07_R11_3V3", "14_R11_SCLK"),
            ("08_R12_3V3", "13_R12_MOSI"),
            ("09_C1_VIO", "12_C1_GND"),
            ("10_C2_VBUS", "11_C2_GND"),
        ],
        "C_": [
            ("01_R15_VIO", "20_R15_ENABLE"),
            ("02_R18_VIO", "19_R18_MOSI"),
            ("03_R17_VIO", "18_R17_SCLK"),
            ("04_R16_VIO", "17_R16_CS"),
            ("05_R19_PICO_MISO", "16_R19_TMC_MISO"),
            ("06_R20_PICO_DIAG", "15_R20_TMC_DIAG"),
            ("07_R13_VIO", "14_R13_STEP"),
            ("08_R14_VIO", "13_R14_DIR"),
            ("09_R21_PICO_MISO", "12_R21_GND"),
            ("10_R22_PICO_DIAG", "11_R22_GND"),
        ],
    }

    row_offsets = {"A_": (3, 0), "B_": (0, -3), "C_": (3, 0)}
    row_directions = {"A_": "down", "B_": "left", "C_": "down"}
    for prefix, pairs in expected_pairs.items():
        rows = _pin_sets_with_prefix(wiring, prefix)
        assert len(rows) == 2
        assert (
            rows[1]["origin"][0] - rows[0]["origin"][0],
            rows[1]["origin"][1] - rows[0]["origin"][1],
        ) == row_offsets[prefix]
        assert rows[0]["direction"] == rows[1]["direction"] == row_directions[prefix]
        assert list(zip(rows[0]["pins"], rows[1]["pins"], strict=True)) == pairs

    socket_a_left = _pin_sets_with_prefix(wiring, "A_")[0]["pins"]
    assert socket_a_left[7:] == ["08_Q1_C", "09_Q1_B", "10_Q1_E"]


def test_tmc5160_review_wiring_has_official_high_current_terminal_order():
    wiring = _load_tmc5160_review_wiring()

    assert _pin_sets_with_prefix(wiring, "TMC5160_HV_")[0]["pins"] == [
        "1B",
        "2B",
        "1A",
        "2A",
        "GND",
        "HVIN_8_60V",
    ]
    assert _pin_sets_with_prefix(wiring, "MOTOR_Y_") == []
    assert all(
        not wire[endpoint].startswith("MOTOR_Y_")
        for wire in wiring["wires"]
        for endpoint in ("from", "to")
    )


def test_tmc5160_review_wiring_stays_out_of_active_klipper_validation():
    wiring = _load_tmc5160_review_wiring()
    validator = _load_validator_module()
    wire_pairs = {(wire["from"], wire["to"]) for wire in wiring["wires"]}

    assert all("klipper" not in wire for wire in wiring["wires"])
    assert TMC5160_REVIEW_PATH not in validator.DEFAULT_WIRING_FILES
    assert ("PICO_GND_03", "ENDSTOP_Y_GND") in wire_pairs
    assert ("PICO_THREEV3_OUT_36", "ENDSTOP_Y_VCC") in wire_pairs
    assert all("PICO_GND_13" not in pair for pair in wire_pairs)
    assert ("U1_07_GND", "PICO_GND_28") in wire_pairs
    assert ("B_11_C2_GND", "B_12_C1_GND") in wire_pairs
    assert ("B_12_C1_GND", "B_20_D1_A") in wire_pairs
    assert ("B_20_D1_A", "A_15_R5_GND") in wire_pairs
    assert ("A_15_R5_GND", "A_14_DZ2_A") in wire_pairs
    assert ("A_14_DZ2_A", "U2_03_LED_B_CATHODE") in wire_pairs
    assert ("U2_03_LED_B_CATHODE", "U2_05_EMITTER_B") in wire_pairs
    assert ("U2_05_EMITTER_B", "U2_08_EMITTER_A") in wire_pairs


def test_tmc5160_review_wiring_uses_only_available_wire_colors():
    wiring = _load_tmc5160_review_wiring()
    colors = wiring["color_map"]

    assert colors == {
        "power": "#ff0000",
        "hazard_power": "#ff0000",
        "lv_power": "#9ca3af",
        "ground": "#000000",
        "clock": "#0057d8",
        "data": "#d9a900",
        "control": "#d9a900",
        "return": "#d9a900",
        "power_good": "#d9a900",
        "default": "#d9a900",
    }
    assert {colors[wire["type"]] for wire in wiring["wires"]} == {
        "#ff0000",
        "#9ca3af",
        "#000000",
        "#0057d8",
        "#d9a900",
    }
    assert all("color" not in wire for wire in wiring["wires"])

    pull_up_supply_contacts = {
        "B_02_R6_3V3",
        "B_03_R7_3V3",
        "B_04_R8_3V3",
        "B_05_R9_3V3",
        "B_06_R10_3V3",
        "B_07_R11_3V3",
        "B_08_R12_3V3",
        "C_01_R15_VIO",
        "C_02_R18_VIO",
        "C_03_R17_VIO",
        "C_04_R16_VIO",
        "C_07_R13_VIO",
        "C_08_R14_VIO",
    }
    for wire in wiring["wires"]:
        if pull_up_supply_contacts & {wire["from"], wire["to"]}:
            assert wire["type"] == "lv_power"


def test_generated_tmc5160_review_svgs_include_physical_boundaries():
    expected_labels = {
        "PICO_VBUS_40",
        "U1_14_VCC",
        "TMC1_J1_MOSI_CFG1_2",
        "TMC1_TOP_DIAG",
        "A_08_Q1_C",
        "A_13_NC",
        "B_01_D1_K",
        "C_14_R13_STEP",
        "TMC5160_HV_1B",
        "TMC5160_HV_HVIN_8_60V",
        "TMC_FAN_24V",
    }

    for view in ("top", "bottom"):
        svg_text = (
            WIRING_DIR
            / "diagrams"
            / f"rp2040plus_btt_tmc5160t_plus_y_{view}.svg"
        ).read_text(encoding="utf-8")
        for label in expected_labels:
            assert label in svg_text
        assert "NC_Q1" not in svg_text


def test_generated_yz_wiring_svg_includes_bed_thermistor_damping_capacitor():
    for view in ("top", "bottom"):
        svg_text = (
            WIRING_DIR / "diagrams" / f"pico_w_btt_tmc2226_y_z_{view}.svg"
        ).read_text()

        assert "C_BED_THERM_DAMP_100UF_POS" in svg_text
        assert "C_BED_THERM_DAMP_100UF_NEG" in svg_text


def test_generated_yz_wiring_svg_includes_vision_light_header():
    for view in ("top", "bottom"):
        svg_text = (
            WIRING_DIR / "diagrams" / f"pico_w_btt_tmc2226_y_z_{view}.svg"
        ).read_text()

        assert "VISION_APA102_FIVE_V" in svg_text
        assert "VISION_APA102_THREEV3" in svg_text
        assert "VISION_APA102_GND" in svg_text
        assert "VISION_APA102_CLOCK" in svg_text
        assert "VISION_APA102_DATA" in svg_text


def test_active_looking_legacy_wiring_paths_are_removed():
    assert not (KLIPPER_CONFIG_DIR / "archive" / "wiring").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "snippets").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "scripts").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "legacy_configs").exists()
