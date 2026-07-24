import importlib.util
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WIRING_DIR = REPO_ROOT / "klipper_setup" / "klipper_config" / "wiring"
GENERATOR_PATH = WIRING_DIR / "tmc5160t_plus_84dd4cb_delta.py"
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"

EXPECTED_NEW_CONNECTIONS = {
    ("LINE18_F1_5A_OUT", "HV06_R1A_HVIN"),
    ("HV06_R1A_HVIN", "HV07_R1B_HVIN"),
    ("HV07_R1B_HVIN", "HV08_R1C_HVIN"),
    ("LINE18_AUX_24V_A", "LINE18_AUX_24V_B"),
    ("LINE18_AUX_24V_B", "TMC1_J2_VM_1"),
    ("LINE18_PWR_GND_A", "C11_R22_GND"),
    ("LINE18_PWR_GND_A", "HV11_D1_A"),
    ("PICO_GND_38", "A20_C1_GND"),
    ("A14_C3_GND", "A12_U3P2_GND"),
    ("A12_U3P2_GND", "HV11_D1_A"),
    ("HV11_D1_A", "LINE18_ENDSTOP_GND"),
    ("PICO_VBUS_40", "A02_C2_VBUS"),
    ("HV15_R1A_DZ1", "HV14_R1B_DZ1"),
    ("HV14_R1B_DZ1", "HV13_R1C_DZ1"),
    ("A05_U3_IN_FEED", "A11_U3P3_IN"),
    ("A13_U3P1_OUT", "A16_U3_OUT_FEED"),
    ("A01_C1_VIO", "TMC1_J2_VIO_7"),
}

EXPECTED_REMOVED_CONNECTIONS = {
    ("LINE18_F1_5A_OUT", "HV08_R1_24V"),
    ("LINE18_F1_5A_OUT", "TMC1_J2_VM_1"),
    ("TMC1_J2_GND_LOGIC_8", "C11_R22_GND"),
    ("U1_07_GND", "A14_DZ2_A"),
    ("A14_DZ2_A", "HV11_D1_A"),
    ("PICO_GND_03", "LINE18_ENDSTOP_GND"),
    ("PICO_VBUS_40", "U1_14_VCC"),
    ("C08_R14_VIO", "TMC1_J2_VIO_7"),
}


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "tmc5160t_plus_84dd4cb_delta",
        GENERATOR_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rendered_delta(tmp_path):
    module = _load_generator_module()
    return module, module.render_tmc5160t_plus_84dd4cb_delta(tmp_path)


def test_84dd4cb_delta_classifies_exact_component_and_coordinate_graph_changes(
    rendered_delta,
):
    _, result = rendered_delta

    assert result.components.added == ("C3", "R1A", "R1B", "R1C", "U3")
    assert result.components.changed == ("C1", "R3", "R5", "R6")
    assert result.components.removed == ("DZ2", "R1", "R4")
    assert len(result.components.unchanged) == 23

    assert result.connections.count("new") == 17
    assert result.connections.count("changed") == 0
    assert result.connections.count("unchanged") == 77
    assert len(result.connections.removed_edges) == 8
    assert {
        (edge.from_pin, edge.to_pin) for edge in result.connections.removed_edges
    } == EXPECTED_REMOVED_CONNECTIONS


def test_component_delta_svg_highlights_install_replace_and_remove_actions(
    rendered_delta,
):
    module, result = rendered_delta
    root = ET.parse(result.top_path).getroot()

    assert root.attrib["data-delta-kind"] == "component-placement"
    assert root.attrib["data-redesign-commit"] == module.REDESIGN_COMMIT
    groups = {
        group.attrib["data-component"]: group
        for group in root.iter(f"{SVG_NAMESPACE}g")
        if group.attrib.get("data-component")
    }
    for ref in (*result.components.added, *result.components.changed):
        group = groups[ref]
        assert group.attrib["data-delta"] in {"added", "changed"}
        highlighted_shapes = [
            node
            for node in group.iter()
            if node.attrib.get("stroke") == module.DELTA_PURPLE
        ]
        assert highlighted_shapes
        assert all(
            float(node.attrib["stroke-width"]) >= 4 for node in highlighted_shapes
        )

    assert groups["C3"].attrib["data-replaces"] == "DZ2"
    assert groups["R1C"].attrib["data-replaces"] == "R1"
    assert groups["R4"].attrib["data-delta"] == "removed"
    assert any(
        node.attrib.get("stroke-dasharray") == "8 5" for node in groups["R4"].iter()
    )
    assert "DZ2" not in {
        ref
        for ref, group in groups.items()
        if group.attrib.get("data-delta") == "removed"
    }
    assert "R1" not in {
        ref
        for ref, group in groups.items()
        if group.attrib.get("data-delta") == "removed"
    }

    text_values = {
        node.text for node in root.iter(f"{SVG_NAMESPACE}text") if node.text is not None
    }
    assert "REPLACES DZ2" in text_values
    assert "REPLACES R1" in text_values
    assert any(text.startswith("84dd4cb REDESIGN DELTA") for text in text_values)
    assert result.top_path.name == module.TOP_DELTA_FILENAME


def test_bottom_delta_svg_marks_removed_and_new_coordinate_graph_edges(
    rendered_delta,
):
    module, result = rendered_delta
    root = ET.parse(result.bottom_path).getroot()

    assert root.attrib["data-delta-kind"] == "coordinate-graph"
    assert root.attrib["data-new-connections"] == "17"
    assert root.attrib["data-changed-connections"] == "0"
    assert root.attrib["data-removed-connections"] == "8"
    assert root.attrib["data-unchanged-connections"] == "77"
    assert any(
        node.attrib.get("class") == "delta-background"
        and node.attrib.get("fill") == "#ffffff"
        for node in root
    )

    target_lines = [
        node
        for node in root.iter(f"{SVG_NAMESPACE}line")
        if "data-connection-index" in node.attrib
    ]
    target_status_by_index = {
        int(node.attrib["data-connection-index"]): node.attrib["data-delta"]
        for node in target_lines
    }
    assert list(target_status_by_index.values()).count("new") == 17
    assert list(target_status_by_index.values()).count("changed") == 0
    assert list(target_status_by_index.values()).count("unchanged") == 77
    assert all(
        node.attrib["stroke-width"] == "6"
        for node in target_lines
        if node.attrib["data-delta"] == "new"
    )
    assert all(
        node.attrib["stroke-width"] == "1.5" and node.attrib["stroke-opacity"] == "0.28"
        for node in target_lines
        if node.attrib["data-delta"] == "unchanged"
    )
    new_connections = {
        (node.attrib["data-from"], node.attrib["data-to"])
        for node in target_lines
        if node.attrib["data-delta"] == "new"
    }
    assert new_connections == EXPECTED_NEW_CONNECTIONS

    removed_lines = [
        node
        for node in root.iter(f"{SVG_NAMESPACE}line")
        if node.attrib.get("data-delta") == "removed"
    ]
    assert len(removed_lines) == 8
    assert {
        (node.attrib["data-from"], node.attrib["data-to"]) for node in removed_lines
    } == EXPECTED_REMOVED_CONNECTIONS
    assert all(
        node.attrib["stroke"] == module.REMOVED_PURPLE
        and node.attrib["stroke-dasharray"] == "12 8"
        and node.attrib["stroke-width"] == "4"
        for node in removed_lines
    )
    assert result.bottom_path.name == module.BOTTOM_DELTA_FILENAME
