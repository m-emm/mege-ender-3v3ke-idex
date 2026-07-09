import yaml

import pytest

pytest.importorskip("cadquery")

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.xh_connector_assembly import (
    XH_CONNECTOR_BODY_WIDTH_EXTRA,
    XH_CONNECTOR_HOUSING_DEPTH,
    XH_CONNECTOR_HOUSING_HEIGHT,
    XH_CONNECTOR_PIN_SIDE,
    XH_CONNECTOR_PIN_CENTER_X_FROM_LEFT,
    XH_CONNECTOR_PIN_TAIL_LENGTH,
    XH_CONNECTOR_PITCH,
    XH_CONNECTOR_FLOOR_THICKNESS,
    XH_CONNECTOR_WALL_THICKNESS,
    create_xh_connector_assembly,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import (
    Alignment,
    align,
    create_box,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
    materialize_bounding_box,
)


RESOURCE_FILE = ASSEMBLIES_DIR / "xh_connector_assembly.yaml"
ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"


def _bbox_volume(part):
    size = get_bounding_box_size(part)
    return size[0] * size[1] * size[2]


def _plain_hollow_housing(pin_count):
    housing_width = (pin_count - 1) * XH_CONNECTOR_PITCH + XH_CONNECTOR_BODY_WIDTH_EXTRA
    housing = create_box(
        XH_CONNECTOR_HOUSING_DEPTH,
        housing_width,
        XH_CONNECTOR_HOUSING_HEIGHT,
    )
    inner_cutter = materialize_bounding_box(
        housing,
        x_enlargement=-2 * XH_CONNECTOR_WALL_THICKNESS,
        y_enlargement=-2 * XH_CONNECTOR_WALL_THICKNESS,
        z_enlargement=-XH_CONNECTOR_FLOOR_THICKNESS,
    )
    inner_cutter = align(inner_cutter, housing, Alignment.CENTER)
    inner_cutter = align(inner_cutter, housing, Alignment.TOP)
    return housing.cut(inner_cutter)


def test_xh_connector_uses_housing_leader_and_nonproduction_pins():
    connector = create_xh_connector_assembly(xh_connector_num_pins=4)

    assert isinstance(connector, LeaderFollowersCuttersPart)

    housing_size = get_bounding_box_size(connector.leader)
    assert housing_size == pytest.approx(
        (
            XH_CONNECTOR_HOUSING_DEPTH,
            3 * XH_CONNECTOR_PITCH + XH_CONNECTOR_BODY_WIDTH_EXTRA,
            XH_CONNECTOR_HOUSING_HEIGHT,
        )
    )
    assert get_volume(connector.leader) > 0
    assert get_volume(connector.leader) < _bbox_volume(connector.leader)
    assert connector.cutter_indices_by_name == {}
    assert get_volume(connector.leader) < get_volume(_plain_hollow_housing(4))

    pins = connector.get_named_non_production_part("pins")
    pins_bbox = get_bounding_box(pins)
    housing_bbox = get_bounding_box(connector.leader)
    pin_center = get_bounding_box_center(pins)

    assert pins_bbox[1][2] == pytest.approx(housing_bbox[1][2])
    assert pins_bbox[0][2] == pytest.approx(
        housing_bbox[0][2] - XH_CONNECTOR_PIN_TAIL_LENGTH
    )
    assert pin_center[0] - housing_bbox[0][0] == pytest.approx(
        XH_CONNECTOR_PIN_CENTER_X_FROM_LEFT
    )
    assert housing_bbox[0][0] < pins_bbox[0][0] < pins_bbox[1][0] < housing_bbox[1][0]
    assert housing_bbox[0][1] < pins_bbox[0][1] < pins_bbox[1][1] < housing_bbox[1][1]


@pytest.mark.parametrize("pin_count", [2, 3, 4, 6])
def test_xh_connector_pin_count_parameter_scales_housing_and_pin_row(pin_count):
    connector = create_xh_connector_assembly(xh_connector_num_pins=pin_count)

    assert get_bounding_box_size(connector.leader) == pytest.approx(
        (
            XH_CONNECTOR_HOUSING_DEPTH,
            (pin_count - 1) * XH_CONNECTOR_PITCH + XH_CONNECTOR_BODY_WIDTH_EXTRA,
            XH_CONNECTOR_HOUSING_HEIGHT,
        )
    )

    pins = connector.get_named_non_production_part("pins")
    assert get_bounding_box_size(pins)[1] == pytest.approx(
        (pin_count - 1) * XH_CONNECTOR_PITCH + XH_CONNECTOR_PIN_SIDE
    )


def test_xh_connector_rejects_single_pin_variant():
    with pytest.raises(ValueError, match="at least 2"):
        create_xh_connector_assembly(xh_connector_num_pins=1)


def test_xh_connector_yaml_visualizes_reference_only_parts():
    resource = yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)

    assert resource["Builder"]["Production"]["parts"] == []

    visual_parts = resource["Builder"]["Visualization"]["parts"]
    assert {
        "source": "self",
        "artifact": "leader",
        "name": "xh_connector_housing",
        "color": [0.92, 0.92, 0.86],
    } in visual_parts
    assert any(
        part.get("source") == "self"
        and part.get("artifact") == "non_production_parts"
        and part.get("names") == ["pins"]
        and part.get("name_template") == "{name}"
        for part in visual_parts
    )


def test_xh_connector_assembly_registry_has_generic_and_b4b_instances():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    assert assemblies["xh_connector_assembly"] == {
        "name": "xh_connector_assembly",
        "resource_file": "xh_connector_assembly.yaml",
        "depends_on": [],
        "parameters": {"xh_connector_num_pins": 4},
    }
    assert assemblies["xh_b4b_xh_a_assembly"] == {
        "name": "xh_b4b_xh_a_assembly",
        "resource_file": "xh_connector_assembly.yaml",
        "depends_on": [],
        "parameters": {"xh_connector_num_pins": 4},
    }
