import importlib.util
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
KLIPPER_CONFIG_DIR = REPO_ROOT / "klipper_setup" / "klipper_config"
WIRING_DIR = KLIPPER_CONFIG_DIR / "wiring"
ACTIVE_Y_Z_WIRING_PATH = WIRING_DIR / "pico_w_btt_tmc2226_y_z.yaml"
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
    "tmc5160 stepper_y.cs_pin",
    "tmc5160 stepper_y.spi_software_miso_pin",
    "tmc5160 stepper_y.spi_software_mosi_pin",
    "tmc5160 stepper_y.spi_software_sclk_pin",
    "gcode_button multi_head_zero.pin",
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


def _wire_nodes_connected(wiring, start, end):
    adjacency = {}
    for wire in wiring["wires"]:
        adjacency.setdefault(wire["from"], set()).add(wire["to"])
        adjacency.setdefault(wire["to"], set()).add(wire["from"])

    pending = [start]
    visited = set()
    while pending:
        node = pending.pop()
        if node == end:
            return True
        if node in visited:
            continue
        visited.add(node)
        pending.extend(adjacency.get(node, ()) - visited)
    return False


def test_active_wiring_matches_klipper_template():
    validator = _load_validator_module()

    assert validator.validate_wiring() == []


def test_active_wiring_tags_cover_expected_pico_klipper_pins():
    validator = _load_validator_module()
    tags = set(validator.iter_tagged_wiring_refs(validator.DEFAULT_WIRING_FILES))

    assert tags == EXPECTED_KLIPPER_TAGS


def test_reserved_mosfet_driver_remains_wired_but_unconfigured():
    wiring = yaml.safe_load(ACTIVE_Y_Z_WIRING_PATH.read_text(encoding="utf-8"))
    prefixes = {pin_set["prefix"] for pin_set in wiring["pin_sets"]}
    mosfet_control = next(
        wire
        for wire in wiring["wires"]
        if wire["from"] == "PICO_GPIO_21_27"
        and wire["to"] == "MOSFET_RESERVED_UNUSED_HEATBED_ON"
    )

    assert "MOSFET_RESERVED_UNUSED_" in prefixes
    assert "klipper" not in mosfet_control


def test_multi_head_zero_reuses_legacy_primary_y_endstop_header():
    wiring = yaml.safe_load(ACTIVE_Y_Z_WIRING_PATH.read_text(encoding="utf-8"))
    prefixes = {pin_set["prefix"] for pin_set in wiring["pin_sets"]}
    signal_wire = next(
        wire for wire in wiring["wires"] if wire["from"] == "PICO_GPIO_4"
    )

    assert "MULTI_HEAD_ZERO_" in prefixes
    assert "ENDSTOP_Y_" not in prefixes
    assert signal_wire["to"] == "MULTI_HEAD_ZERO_NC"
    assert signal_wire["klipper"] == "gcode_button multi_head_zero.pin"
    assert _wire_nodes_connected(wiring, "MULTI_HEAD_ZERO_GND", "PWR_GND")
    assert _wire_nodes_connected(
        wiring,
        "MULTI_HEAD_ZERO_VCC_UNUSED",
        "PICO_THREEV3_OUT_36",
    )


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

    for view in ("top", "top_discrete", "bottom"):
        svg = tmp_path / f"rp2040plus_btt_tmc5160t_plus_y_{view}.svg"
        assert svg.is_file()
        assert svg.stat().st_size > 0


def test_tmc5160_review_wiring_declares_discrete_component_placements():
    wiring = _load_tmc5160_review_wiring()
    placements = {
        placement["ref"]: placement for placement in wiring["component_placements"]
    }

    assert set(placements) == {
        "U1",
        "U2",
        "U3",
        "Q1",
        "C1",
        "C2",
        "C3",
        "D1",
        "DZ1",
        "DZ2",
        "R1A",
        "R1B",
        "R1C",
        *(
            f"R{number}"
            for number in (2, 3, 5, *(n for n in range(7, 24) if n not in {19, 21}))
        ),
    }
    assert "R19" not in placements
    assert "R21" not in placements
    assert placements["U1"]["terminals"][1] == "U1_01_1A_STEP"
    assert placements["U1"]["terminals"][14] == "U1_14_VCC"
    assert placements["U2"]["terminals"] == {
        1: "HV01_U2P1_LEDA_A",
        2: "HV02_U2P2_LEDA_K",
        3: "HV03_U2P3_LEDB_K",
        4: "HV04_U2P4_LEDB_A",
        5: "HV17_U2P5_E_B",
        6: "HV18_U2P6_C_B",
        7: "HV19_U2P7_C_A",
        8: "HV20_U2P8_E_A",
    }
    assert placements["Q1"]["terminals"] == {
        "collector": "A08_Q1_C",
        "base": "A09_Q1_B",
        "emitter": "A10_Q1_E",
    }
    assert placements["U3"]["kind"] == "voltage_regulator"
    assert placements["U3"]["part"] == "UTC_LP2950L_33_T92"
    assert placements["U3"]["terminals"] == {
        "output": "A13_U3P1_OUT",
        "ground": "A12_U3P2_GND",
        "input": "A11_U3P3_IN",
    }
    assert placements["DZ1"]["terminals"] == {
        "anode": "HV12_DZ1_A",
        "cathode": "HV09_DZ1_K",
    }
    assert placements["D1"]["terminals"] == {
        "anode": "HV11_D1_A",
        "cathode": "HV10_D1_K",
    }
    assert "R6" not in placements
    assert placements["R23"]["terminals"] == {
        "start": "B10_R23_AUX24",
        "end": "B11_R23_DZ2",
    }
    assert placements["DZ2"]["terminals"] == {
        "anode": "B12_DZ2_A",
        "cathode": "B09_DZ2_K",
    }
    assert len(
        {
            pin_name
            for placement in placements.values()
            for pin_name in placement["terminals"].values()
        }
    ) == sum(len(placement["terminals"]) for placement in placements.values())


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
    assert top["pins"] == ["DIAG0", "DIAG1"]


def test_tmc5160_review_wiring_has_four_true_2x10_component_carriers():
    wiring = _load_tmc5160_review_wiring()
    expected_pairs = {
        "A": [
            ("01_C1_VIO", "20_C1_GND"),
            ("02_C2_VBUS", "19_C2_GND"),
            ("03_R2_VBUS", "18_R2_BASE"),
            ("04_R3_BASE", "17_R3_U2A"),
            ("05_U3_IN_FEED", "16_U3_OUT_FEED"),
            ("06_R5_VIO", "15_R5_GND"),
            ("07_C3_VIO", "14_C3_GND"),
            ("08_Q1_C", "13_U3P1_OUT"),
            ("09_Q1_B", "12_U3P2_GND"),
            ("10_Q1_E", "11_U3P3_IN"),
        ],
        "B": [
            ("01_NC", "20_NC"),
            ("02_NC", "19_VIO_OK"),
            ("03_R12_3V3", "18_R12_MOSI"),
            ("04_R7_3V3", "17_R7_STEP"),
            ("05_R11_3V3", "16_R11_SCLK"),
            ("06_R8_3V3", "15_R8_DIR"),
            ("07_R10_3V3", "14_R10_CS"),
            ("08_R9_3V3", "13_R9_ENABLE"),
            ("09_DZ2_K", "12_DZ2_A"),
            ("10_R23_AUX24", "11_R23_DZ2"),
        ],
        "C": [
            ("01_R15_VIO", "20_R15_ENABLE"),
            ("02_R18_VIO", "19_R18_MOSI"),
            ("03_R17_VIO", "18_R17_SCLK"),
            ("04_R16_VIO", "17_R16_CS"),
            ("05_NC", "16_NC"),
            ("06_R20_PICO_DIAG", "15_R20_TMC_DIAG"),
            ("07_R13_VIO", "14_R13_STEP"),
            ("08_R14_VIO", "13_R14_DIR"),
            ("09_NC", "12_NC"),
            ("10_R22_PICO_DIAG", "11_R22_GND"),
        ],
        "HV": [
            ("01_U2P1_LEDA_A", "20_U2P8_E_A"),
            ("02_U2P2_LEDA_K", "19_U2P7_C_A"),
            ("03_U2P3_LEDB_K", "18_U2P6_C_B"),
            ("04_U2P4_LEDB_A", "17_U2P5_E_B"),
            ("05_NC", "16_NC"),
            ("06_R1A_HVIN", "15_R1A_DZ1"),
            ("07_R1B_HVIN", "14_R1B_DZ1"),
            ("08_R1C_HVIN", "13_R1C_DZ1"),
            ("09_DZ1_K", "12_DZ1_A"),
            ("10_D1_K", "11_D1_A"),
        ],
    }

    for prefix, pairs in expected_pairs.items():
        rows = _pin_sets_with_prefix(wiring, prefix)
        assert len(rows) == 2
        assert list(zip(rows[0]["pins"], rows[1]["pins"], strict=True)) == pairs

    socket_a_left = _pin_sets_with_prefix(wiring, "A")[0]["pins"]
    assert socket_a_left[7:] == ["08_Q1_C", "09_Q1_B", "10_Q1_E"]
    assert _pin_sets_with_prefix(wiring, "U2_") == []

    hv_guard_contacts = {
        "HV05_NC",
        "HV16_NC",
    }
    assert all(
        not hv_guard_contacts & {wire["from"], wire["to"]} for wire in wiring["wires"]
    )


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
    assert _pin_sets_with_prefix(wiring, "TMC_FAN_") == []
    assert all(
        not wire[endpoint].startswith("MOTOR_Y_")
        for wire in wiring["wires"]
        for endpoint in ("from", "to")
    )


def test_tmc5160_wiring_is_active_klipper_y_truth():
    wiring = _load_tmc5160_review_wiring()
    validator = _load_validator_module()
    wire_pairs = {(wire["from"], wire["to"]) for wire in wiring["wires"]}

    assert TMC5160_REVIEW_PATH in validator.DEFAULT_WIRING_FILES
    assert {
        "stepper_y.step_pin",
        "stepper_y.dir_pin",
        "stepper_y.enable_pin",
        "stepper_y.endstop_pin",
        "tmc5160 stepper_y.cs_pin",
        "tmc5160 stepper_y.spi_software_miso_pin",
        "tmc5160 stepper_y.spi_software_mosi_pin",
        "tmc5160 stepper_y.spi_software_sclk_pin",
    } == {
        tag
        for wire in wiring["wires"]
        for tag in validator.klipper_tags(wire.get("klipper"))
    }
    assert ("PICO_THREEV3_OUT_36", "LINE18_ENDSTOP_VCC") in wire_pairs
    assert ("TMC1_J1_MISO_CFG0_5", "PICO_GPIO_8") in wire_pairs
    assert ("TMC1_J2_GND_LOGIC_8", "PICO_GND_13") in wire_pairs
    assert all(
        not {
            "C05_R19_PICO_MISO",
            "C09_R21_PICO_MISO",
            "C12_R21_GND",
            "C16_R19_TMC_MISO",
        }
        & set(pair)
        for pair in wire_pairs
    )
    assert (
        "HV20_U2P8_E_A",
        "HV18_U2P6_C_B",
    ) in wire_pairs


def test_tmc5160_review_wiring_uses_two_post_ground_star():
    wiring = _load_tmc5160_review_wiring()
    hubs = {"LINE18_PWR_GND_A", "LINE18_PWR_GND_B"}
    expected_spokes = {
        frozenset(("LINE18_PWR_GND_A", "TMC5160_HV_GND")),
        frozenset(("LINE18_PWR_GND_A", "TMC1_J2_GND_MOTOR_2")),
        frozenset(("LINE18_PWR_GND_A", "TMC1_J2_GND_LOGIC_8")),
        frozenset(("LINE18_PWR_GND_A", "U1_07_GND")),
        frozenset(("LINE18_PWR_GND_A", "PICO_GND_28")),
        frozenset(("LINE18_PWR_GND_A", "PICO_GND_38")),
        frozenset(("LINE18_PWR_GND_A", "LINE18_ENDSTOP_GND")),
        frozenset(("LINE18_PWR_GND_A", "A20_C1_GND")),
        frozenset(("LINE18_PWR_GND_B", "C11_R22_GND")),
        frozenset(("LINE18_PWR_GND_B", "A19_C2_GND")),
        frozenset(("LINE18_PWR_GND_B", "A15_R5_GND")),
        frozenset(("LINE18_PWR_GND_B", "A14_C3_GND")),
        frozenset(("LINE18_PWR_GND_B", "A12_U3P2_GND")),
        frozenset(("LINE18_PWR_GND_B", "HV11_D1_A")),
        frozenset(("LINE18_PWR_GND_B", "HV02_U2P2_LEDA_K")),
        frozenset(("LINE18_PWR_GND_B", "HV03_U2P3_LEDB_K")),
        frozenset(("LINE18_PWR_GND_B", "HV17_U2P5_E_B")),
    }
    ground_wires = [wire for wire in wiring["wires"] if wire["type"] == "ground"]
    ground_edges = {
        frozenset((wire["from"], wire["to"])) for wire in ground_wires
    }

    paired_miso_return = frozenset(
        ("TMC1_J2_GND_LOGIC_8", "PICO_GND_13")
    )
    assert ground_edges == {
        frozenset(hubs),
        *expected_spokes,
        paired_miso_return,
    }
    assert all(
        hubs & {wire["from"], wire["to"]}
        or frozenset((wire["from"], wire["to"])) == paired_miso_return
        for wire in ground_wires
    )

    non_hub_contacts = Counter(
        endpoint
        for wire in ground_wires
        for endpoint in (wire["from"], wire["to"])
        if endpoint not in hubs
    )
    assert non_hub_contacts["TMC1_J2_GND_LOGIC_8"] == 2
    assert all(
        count == 1
        for contact, count in non_hub_contacts.items()
        if contact != "TMC1_J2_GND_LOGIC_8"
    )
    hub_contacts = Counter(
        endpoint
        for wire in ground_wires
        for endpoint in (wire["from"], wire["to"])
        if endpoint in hubs
    )
    assert hub_contacts == {
        "LINE18_PWR_GND_A": 9,
        "LINE18_PWR_GND_B": 10,
    }


def test_tmc5160_u3_regulator_terminals_join_the_intended_electrical_nets():
    wiring = _load_tmc5160_review_wiring()

    assert _wire_nodes_connected(wiring, "A08_Q1_C", "A11_U3P3_IN")
    assert _wire_nodes_connected(wiring, "A12_U3P2_GND", "PICO_GND_38")
    assert _wire_nodes_connected(wiring, "A13_U3P1_OUT", "TMC1_J2_VIO_7")


def test_tmc5160_review_wiring_separates_hvin_from_24v_adapter_power():
    wiring = _load_tmc5160_review_wiring()
    wire_pairs = {(wire["from"], wire["to"]) for wire in wiring["wires"]}

    assert {
        ("LINE18_PWR_HVIN_SW_A", "LINE18_PWR_HVIN_SW_B"),
        ("LINE18_PWR_HVIN_SW_B", "LINE18_F1_5A_IN"),
        ("LINE18_F1_5A_OUT", "TMC5160_HV_HVIN_8_60V"),
        ("LINE18_F1_5A_OUT", "HV06_R1A_HVIN"),
        ("HV06_R1A_HVIN", "HV07_R1B_HVIN"),
        ("HV07_R1B_HVIN", "HV08_R1C_HVIN"),
        ("HV15_R1A_DZ1", "HV14_R1B_DZ1"),
        ("HV14_R1B_DZ1", "HV13_R1C_DZ1"),
        ("HV13_R1C_DZ1", "HV09_DZ1_K"),
    } <= wire_pairs
    assert {
        ("LINE18_AUX_24V_A", "LINE18_AUX_24V_B"),
        ("LINE18_AUX_24V_B", "TMC1_J2_VM_1"),
        ("LINE18_AUX_24V_B", "B10_R23_AUX24"),
        ("B11_R23_DZ2", "B09_DZ2_K"),
        ("B12_DZ2_A", "HV04_U2P4_LEDB_A"),
    } <= wire_pairs
    assert all(
        "LINE18_AUX_24V" not in endpoint
        for wire in wiring["wires"]
        if "TMC5160_HV_HVIN" in {wire["from"], wire["to"]}
        for endpoint in (wire["from"], wire["to"])
    )


def test_tmc5160_review_wiring_uses_declared_wire_types():
    wiring = _load_tmc5160_review_wiring()
    declared_wire_types = set(wiring["color_map"])
    used_wire_types = {wire["type"] for wire in wiring["wires"]}

    assert used_wire_types <= declared_wire_types
    assert all(
        isinstance(color, str) and color for color in wiring["color_map"].values()
    )

    pull_up_supply_contacts = {
        "B03_R12_3V3",
        "B04_R7_3V3",
        "B05_R11_3V3",
        "B06_R8_3V3",
        "B07_R10_3V3",
        "B08_R9_3V3",
        "C01_R15_VIO",
        "C02_R18_VIO",
        "C03_R17_VIO",
        "C04_R16_VIO",
        "C07_R13_VIO",
        "C08_R14_VIO",
    }
    for wire in wiring["wires"]:
        if pull_up_supply_contacts & {wire["from"], wire["to"]}:
            assert wire["type"] == "lv_power"

    pull_up_branch_pairs = {
        ("U1_01_1A_STEP", "B17_R7_STEP"),
        ("U1_03_2A_DIR", "B15_R8_DIR"),
        ("U1_05_3A_ENABLE", "B13_R9_ENABLE"),
        ("U1_09_4A_CS", "B14_R10_CS"),
        ("U1_11_5A_SCLK", "B16_R11_SCLK"),
        ("U1_13_6A_MOSI", "B18_R12_MOSI"),
    }
    assert {
        (wire["from"], wire["to"])
        for wire in wiring["wires"]
        if wire["type"] == "lv_power"
    }.issuperset(pull_up_branch_pairs)

    assert {
        ("PICO_THREEV3_OUT_36", "B03_R12_3V3"),
        ("A01_C1_VIO", "B19_VIO_OK"),
        ("B19_VIO_OK", "PICO_GPIO_5"),
    } <= {
        (wire["from"], wire["to"])
        for wire in wiring["wires"]
        if wire["type"] in {"lv_power", "power_good"}
    }
    assert all(
        "B02_NC" not in {wire["from"], wire["to"]} for wire in wiring["wires"]
    )


def test_generated_tmc5160_review_svgs_include_physical_boundaries():
    wiring = _load_tmc5160_review_wiring()
    expected_pin_labels = {
        f"{pin_set.get('prefix', '')}{pin}"
        for pin_set in wiring["pin_sets"]
        for pin in pin_set["pins"]
    }
    expected_box_ids = {box["id"] for box in wiring.get("boxes", [])}

    for view in ("top", "bottom"):
        svg_text = (
            WIRING_DIR / "diagrams" / f"rp2040plus_btt_tmc5160t_plus_y_{view}.svg"
        ).read_text(encoding="utf-8")
        for label in expected_pin_labels:
            assert label in svg_text
        for box_id in expected_box_ids:
            assert f'data-box="{box_id}"' in svg_text
        assert "NC_Q1" not in svg_text


def test_generated_tmc5160_discrete_top_is_an_assembly_view_without_wires():
    wiring = _load_tmc5160_review_wiring()
    svg_path = (
        WIRING_DIR / "diagrams" / "rp2040plus_btt_tmc5160t_plus_y_top_discrete.svg"
    )
    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    namespace = "{http://www.w3.org/2000/svg}"

    component_refs = {
        node.attrib["data-component"]
        for node in root.iter()
        if node.attrib.get("class") == "discrete-component"
    }
    assert component_refs == {
        placement["ref"] for placement in wiring["component_placements"]
    }
    rendered_box_ids = {
        node.attrib["data-box"]
        for node in root.iter()
        if node.attrib.get("class") == "pinout-box"
    }
    assert rendered_box_ids == {box["id"] for box in wiring.get("boxes", [])}
    assert len(
        [
            node
            for node in root.iter(f"{namespace}circle")
            if node.attrib.get("class") == "discrete-pin"
        ]
    ) == sum(len(pin_set["pins"]) for pin_set in wiring["pin_sets"])

    text_values = {
        node.text for node in root.iter(f"{namespace}text") if node.text is not None
    }
    assert {
        group["label"] for group in wiring["discrete_view"]["groups"]
    } <= text_values
    assert "PICO_THREEV3_EN_37" not in text_values
    assert any(node.attrib.get("class") == "cathode-band" for node in root.iter())
    assert any(node.attrib.get("class") == "dip-pin-one-marker" for node in root.iter())
    assert any(
        node.attrib.get("class") == "transistor-terminal-label" for node in root.iter()
    )
    assert all(
        "stroke" not in node.attrib or node.attrib.get("class")
        for node in root.iter(f"{namespace}line")
    )

    pin_positions = {
        node.attrib["data-pin"]: (
            float(node.attrib["cx"]),
            float(node.attrib["cy"]),
        )
        for node in root.iter(f"{namespace}circle")
        if node.attrib.get("class") == "discrete-pin"
    }
    placements = {
        placement["ref"]: placement for placement in wiring["component_placements"]
    }
    for ref in ("D1", "DZ1", "DZ2"):
        terminals = placements[ref]["terminals"]
        anode_position = pin_positions[terminals["anode"]]
        cathode_position = pin_positions[terminals["cathode"]]
        band = next(
            node
            for node in root.iter(f"{namespace}line")
            if node.attrib.get("class") == "cathode-band"
            and node.attrib.get("data-component") == ref
        )
        band_center = (
            (float(band.attrib["x1"]) + float(band.attrib["x2"])) / 2.0,
            (float(band.attrib["y1"]) + float(band.attrib["y2"])) / 2.0,
        )
        assert math.dist(band_center, cathode_position) < math.dist(
            band_center, anode_position
        )

        polarity_labels = {
            node.attrib["data-terminal"]: (
                float(node.attrib["x"]),
                float(node.attrib["y"]),
            )
            for node in root.iter(f"{namespace}text")
            if node.attrib.get("class") == "polarity-label"
            and node.attrib.get("data-component") == ref
        }
        assert math.dist(polarity_labels["anode"], anode_position) < math.dist(
            polarity_labels["anode"], cathode_position
        )
        assert math.dist(polarity_labels["cathode"], cathode_position) < math.dist(
            polarity_labels["cathode"], anode_position
        )


def test_generated_tmc5160_u3_has_correct_flat_face_and_semantic_pin_order():
    svg_path = (
        WIRING_DIR / "diagrams" / "rp2040plus_btt_tmc5160t_plus_y_top_discrete.svg"
    )
    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    namespace = "{http://www.w3.org/2000/svg}"
    pin_positions = {
        node.attrib["data-pin"]: (
            float(node.attrib["cx"]),
            float(node.attrib["cy"]),
        )
        for node in root.iter(f"{namespace}circle")
        if node.attrib.get("class") == "discrete-pin"
    }
    u3_pins = {
        "output": "A13_U3P1_OUT",
        "ground": "A12_U3P2_GND",
        "input": "A11_U3P3_IN",
    }
    contact_xs = {pin_positions[pin_name][0] for pin_name in u3_pins.values()}
    assert len(contact_xs) == 1
    contact_x = contact_xs.pop()

    body = next(
        node
        for node in root.iter(f"{namespace}path")
        if node.attrib.get("class") == "to92-body"
        and node.attrib.get("data-component") == "U3"
    )
    flat_face = next(
        node
        for node in root.iter(f"{namespace}line")
        if node.attrib.get("class") == "to92-flat-face"
        and node.attrib.get("data-component") == "U3"
    )
    body_min_x = float(body.attrib["data-body-min-x"])
    body_max_x = float(body.attrib["data-body-max-x"])
    flat_xs = {float(flat_face.attrib["x1"]), float(flat_face.attrib["x2"])}
    assert len(flat_xs) == 1
    flat_x = flat_xs.pop()

    assert body.attrib["data-part"] == "UTC_LP2950L_33_T92"
    assert body_min_x > contact_x
    assert flat_x == pytest.approx(body_min_x)
    assert body_max_x > flat_x
    assert flat_x - contact_x < body_max_x - flat_x

    expected_labels = {
        "output": ("OUT", "1"),
        "ground": ("GND", "2"),
        "input": ("IN", "3"),
    }
    labels = {
        node.attrib["data-terminal"]: (
            node.text,
            node.attrib["data-pin-number"],
        )
        for node in root.iter(f"{namespace}text")
        if node.attrib.get("class") == "to92-terminal-label"
        and node.attrib.get("data-component") == "U3"
    }
    assert labels == expected_labels

    leads = {
        node.attrib["data-terminal"]: node
        for node in root.iter(f"{namespace}line")
        if node.attrib.get("class") == "to92-lead"
        and node.attrib.get("data-component") == "U3"
    }
    for terminal, pin_name in u3_pins.items():
        assert (
            float(leads[terminal].attrib["x1"]),
            float(leads[terminal].attrib["y1"]),
        ) == pytest.approx(pin_positions[pin_name])


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


def test_generated_yz_wiring_svg_includes_multi_head_zero_header():
    for view in ("top", "bottom"):
        svg_text = (
            WIRING_DIR / "diagrams" / f"pico_w_btt_tmc2226_y_z_{view}.svg"
        ).read_text()

        assert "MULTI_HEAD_ZERO_NC" in svg_text
        assert "MULTI_HEAD_ZERO_GND" in svg_text
        assert "MULTI_HEAD_ZERO_VCC_UNUSED" in svg_text


def test_active_looking_legacy_wiring_paths_are_removed():
    assert not (KLIPPER_CONFIG_DIR / "archive" / "wiring").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "snippets").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "scripts").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "legacy_configs").exists()
