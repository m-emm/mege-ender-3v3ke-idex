import importlib.util
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WIRING_DIR = REPO_ROOT / "klipper_setup" / "klipper_config" / "wiring"
GENERATOR_PATH = WIRING_DIR / "tmc5160t_plus_dual_rail_delta.py"
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"

EXPECTED_NEW_CONNECTIONS = {
    ("LINE18_PWR_GND_A", "TMC5160_HV_GND"),
    ("TMC1_J1_MISO_CFG0_5", "PICO_GPIO_8"),
    ("TMC1_J2_GND_LOGIC_8", "PICO_GND_13"),
    ("LINE18_AUX_24V_B", "B10_R23_AUX24"),
    ("B11_R23_DZ2", "B09_DZ2_K"),
    ("B12_DZ2_A", "HV04_U2P4_LEDB_A"),
    ("LINE18_PWR_GND_A", "TMC1_J2_GND_MOTOR_2"),
    ("LINE18_PWR_GND_A", "TMC1_J2_GND_LOGIC_8"),
    ("LINE18_PWR_GND_A", "U1_07_GND"),
    ("LINE18_PWR_GND_A", "PICO_GND_28"),
    ("LINE18_PWR_GND_A", "PICO_GND_38"),
    ("LINE18_PWR_GND_A", "LINE18_ENDSTOP_GND"),
    ("LINE18_PWR_GND_A", "A20_C1_GND"),
    ("LINE18_PWR_GND_B", "C11_R22_GND"),
    ("LINE18_PWR_GND_B", "A19_C2_GND"),
    ("LINE18_PWR_GND_B", "A15_R5_GND"),
    ("LINE18_PWR_GND_B", "A14_C3_GND"),
    ("LINE18_PWR_GND_B", "A12_U3P2_GND"),
    ("LINE18_PWR_GND_B", "HV11_D1_A"),
    ("LINE18_PWR_GND_B", "HV02_U2P2_LEDA_K"),
    ("LINE18_PWR_GND_B", "HV03_U2P3_LEDB_K"),
    ("LINE18_PWR_GND_B", "HV17_U2P5_E_B"),
    ("HV20_U2P8_E_A", "HV18_U2P6_C_B"),
    ("PICO_THREEV3_OUT_36", "B03_R12_3V3"),
    ("A01_C1_VIO", "B19_VIO_OK"),
    ("B19_VIO_OK", "PICO_GPIO_5"),
}

EXPECTED_REMOVED_CONNECTIONS = {
    ("LINE18_PWR_GND_B", "TMC5160_HV_GND"),
    ("LINE18_PWR_GND_B", "TMC1_J2_GND_MOTOR_2"),
    ("TMC1_J2_GND_MOTOR_2", "TMC1_J2_GND_LOGIC_8"),
    ("LINE18_PWR_GND_A", "C11_R22_GND"),
    ("C11_R22_GND", "C12_R21_GND"),
    ("C12_R21_GND", "U1_07_GND"),
    ("U1_07_GND", "PICO_GND_28"),
    ("LINE18_PWR_GND_A", "HV11_D1_A"),
    ("PICO_GND_38", "A20_C1_GND"),
    ("A20_C1_GND", "A19_C2_GND"),
    ("A19_C2_GND", "A15_R5_GND"),
    ("A15_R5_GND", "A14_C3_GND"),
    ("A14_C3_GND", "A12_U3P2_GND"),
    ("A12_U3P2_GND", "HV11_D1_A"),
    ("HV11_D1_A", "HV03_U2P3_LEDB_K"),
    ("HV03_U2P3_LEDB_K", "HV17_U2P5_E_B"),
    ("HV17_U2P5_E_B", "HV20_U2P8_E_A"),
    ("HV02_U2P2_LEDA_K", "HV04_U2P4_LEDB_A"),
    ("HV11_D1_A", "LINE18_ENDSTOP_GND"),
    ("PICO_THREEV3_OUT_36", "B02_R6_3V3"),
    ("B02_R6_3V3", "B03_R12_3V3"),
    ("B19_R6_PWR_OK", "HV18_U2P6_C_B"),
    ("HV18_U2P6_C_B", "PICO_GPIO_5"),
    ("TMC1_J1_MISO_CFG0_5", "C16_R19_TMC_MISO"),
    ("C05_R19_PICO_MISO", "C09_R21_PICO_MISO"),
    ("C09_R21_PICO_MISO", "PICO_GPIO_8"),
}


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "tmc5160t_plus_dual_rail_delta",
        GENERATOR_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(WIRING_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(WIRING_DIR))
    return module


@pytest.fixture
def rendered_delta(tmp_path):
    module = _load_generator_module()
    return module, module.render_tmc5160t_plus_dual_rail_delta(tmp_path)


def test_dual_rail_delta_classifies_only_the_latest_board_rework(rendered_delta):
    _, result = rendered_delta

    assert result.components.added == ("DZ2", "R23")
    assert result.components.changed == ()
    assert result.components.removed == ("R19", "R21", "R6")
    assert len(result.components.unchanged) == 29

    assert result.connections.count("new") == 26
    assert result.connections.count("changed") == 0
    assert result.connections.count("unchanged") == 68
    assert {
        (edge.from_pin, edge.to_pin) for edge in result.connections.removed_edges
    } == EXPECTED_REMOVED_CONNECTIONS


def test_dual_rail_component_delta_marks_additions_and_removals(rendered_delta):
    module, result = rendered_delta
    root = ET.parse(result.top_path).getroot()

    assert root.attrib["data-delta-kind"] == "component-placement"
    assert root.attrib["data-delta-id"] == module.DELTA_IDENTIFIER
    groups = {
        group.attrib["data-component"]: group
        for group in root.iter(f"{SVG_NAMESPACE}g")
        if "discrete-component" in group.attrib.get("class", "").split()
    }
    assert {
        ref
        for ref, group in groups.items()
        if group.attrib.get("data-delta") == "added"
    } == {"DZ2", "R23"}
    assert {
        ref
        for ref, group in groups.items()
        if group.attrib.get("data-delta") in {"changed", "removed"}
    } == {"R6", "R19", "R21"}
    assert result.top_path.name == module.TOP_DELTA_FILENAME


def test_dual_rail_bottom_delta_marks_exact_rewire_connections(rendered_delta):
    module, result = rendered_delta
    root = ET.parse(result.bottom_path).getroot()

    assert root.attrib["data-delta-kind"] == "coordinate-graph"
    assert root.attrib["data-delta-id"] == module.DELTA_IDENTIFIER
    assert root.attrib["data-new-connections"] == "26"
    assert root.attrib["data-changed-connections"] == "0"
    assert root.attrib["data-removed-connections"] == "26"
    assert root.attrib["data-unchanged-connections"] == "68"

    target_lines = [
        node
        for node in root.iter(f"{SVG_NAMESPACE}line")
        if "data-connection-index" in node.attrib
    ]
    assert {
        (node.attrib["data-from"], node.attrib["data-to"])
        for node in target_lines
        if node.attrib["data-delta"] == "new"
    } == EXPECTED_NEW_CONNECTIONS

    removed_lines = [
        node
        for node in root.iter(f"{SVG_NAMESPACE}line")
        if node.attrib.get("data-delta") == "removed"
    ]
    assert {
        (node.attrib["data-from"], node.attrib["data-to"])
        for node in removed_lines
    } == EXPECTED_REMOVED_CONNECTIONS
    text_values = {
        node.text for node in root.iter(f"{SVG_NAMESPACE}text") if node.text
    }
    assert module.PRESENTATION.wiring_extra_note in text_values
    assert result.bottom_path.name == module.BOTTOM_DELTA_FILENAME
