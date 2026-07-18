import inspect

import pytest
import yaml
from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_cable_attach_shield_assembly import (
    create_tool_head_cable_attach_shield_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_machined_assembly import (
    create_tool_head_mount_machined_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_carriage_assembly import (
    create_x_axis_carriage_assembly,
)
from shellforgepy.builder import graph_model as builder_graph_model
from shellforgepy.simple import get_bounding_box_center, get_volume


SHIELD_PARAMETER_NAMES = [
    "tool_head_cable_attach_shield_height",
    "tool_head_cable_attach_shield_thickness",
    "tool_head_cable_attach_shield_fillet_radius",
    "tool_head_cable_attach_shield_plate_flange_overlap",
    "tool_head_cable_attach_shield_flange_width",
    "tool_head_cable_attach_shield_flange_depth",
    "tool_head_cable_attach_shield_flange_thickness",
    "tool_head_cable_attach_shield_hole_diameter",
    "tool_head_cable_attach_shield_hole_columns",
    "tool_head_cable_attach_shield_hole_rows",
    "tool_head_cable_attach_shield_hole_x_margin",
    "tool_head_cable_attach_shield_hole_z_margin",
]


def _shield_parameters():
    return {name: DEFAULTS[name] for name in SHIELD_PARAMETER_NAMES}


def _create_mount():
    carriage = create_x_axis_carriage_assembly()
    return create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=carriage,
            drive_position="bottom",
        )
    )


def _recut_delta(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def test_tool_head_cable_attach_shield_has_simple_mount_only_signature():
    parameters = inspect.signature(
        create_tool_head_cable_attach_shield_assembly
    ).parameters

    assert "tool_head_mount_machined" in parameters
    assert "nitehawk_board" not in parameters
    assert "sprite_extruder" not in parameters
    for parameter_name in SHIELD_PARAMETER_NAMES:
        assert parameter_name in parameters


def test_tool_head_cable_attach_shield_drills_grid_and_front_mount_holes():
    mount = _create_mount()
    shield = create_tool_head_cable_attach_shield_assembly(
        tool_head_mount_machined=mount,
        **_shield_parameters(),
    )

    assert get_volume(shield.leader) > 0

    cable_hole_names = [
        name
        for name in shield.cutter_indices_by_name
        if name.startswith("cable_tie_hole_")
    ]
    assert len(cable_hole_names) == (
        DEFAULTS["tool_head_cable_attach_shield_hole_columns"]
        * DEFAULTS["tool_head_cable_attach_shield_hole_rows"]
    )

    plate_hole_center_y = get_bounding_box_center(
        shield.get_named_cutter("cable_tie_hole_0_0")
    )[1]
    for side in ["left", "right"]:
        shield_hole = shield.get_named_cutter(f"flange_mount_hole_{side}")
        mount_hole = mount.get_named_cutter(f"hole_drill_{side.upper()}_FRONT")
        assert get_bounding_box_center(shield_hole) == pytest.approx(
            get_bounding_box_center(mount_hole)
        )
        assert (
            abs(get_bounding_box_center(shield_hole)[1] - plate_hole_center_y)
            >= DEFAULTS["tool_head_cable_attach_shield_thickness"]
        )
        assert shield.get_named_non_production_part(f"flange_mount_screw_{side}")

    for cutter_name in cable_hole_names + [
        "flange_mount_hole_left",
        "flange_mount_hole_right",
    ]:
        assert _recut_delta(shield.leader, shield.get_named_cutter(cutter_name)) < 0.01


def test_tool_head_cable_attach_shield_yaml_and_graph_wiring():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    resource = yaml.load(
        (ASSEMBLIES_DIR / "tool_head_cable_attach_shield_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    tool_heads_resource = yaml.load(
        (ASSEMBLIES_DIR / "tool_heads_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    whole_printer_resource = yaml.load(
        (ASSEMBLIES_DIR / "whole_printer_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    assert resource["Builder"]["Visualization"]["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "tool_head_cable_attach_shield",
        },
        {
            "source": "self",
            "artifact": "non_production_parts",
            "name_template": "{name}",
        },
        {
            "source": "injected",
            "assembly": "tool_head_mount_machined",
            "artifact": "leader",
            "name": "tool_head_mount_machined",
        },
    ]
    production = resource["Builder"]["Production"]
    assert production["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "tool_head_cable_attach_shield",
            "prod_rotation_angle": 90,
            "prod_rotation_axis": [1, 0, 0],
        }
    ]
    assert (
        production["arrange"]["plates"][0]["process_data_preset"]
        == "petgcf_max_strength_high_speed_06"
    )

    expected = {
        "tool_head_cable_attach_shield_assembly": (
            "tool_head_mount_machined_bottom_assembly",
            None,
        ),
        "tool_head_cable_attach_shield_left_assembly": (
            "tool_head_mount_machined_bottom_assembly",
            "tool_head_cable_attach_shield_left",
        ),
        "tool_head_cable_attach_shield_right_assembly": (
            "tool_head_mount_machined_top_assembly",
            "tool_head_cable_attach_shield_right",
        ),
    }
    for assembly_name, (mount_name, alias) in expected.items():
        assembly = assemblies[assembly_name]
        assert (
            assembly["resource_file"] == "tool_head_cable_attach_shield_assembly.yaml"
        )
        expected_dependencies = ["x_axis_rail_assembly", mount_name]
        expected_injected_parts = {"tool_head_mount_machined": mount_name}
        if assembly_name == "tool_head_cable_attach_shield_right_assembly":
            expected_dependencies.append("opb991t11z_sensor_assembly")
            expected_injected_parts["light_barrier_assembly"] = (
                "opb991t11z_sensor_assembly"
            )
        assert assembly["depends_on"] == expected_dependencies
        assert assembly["inject_parts"] == expected_injected_parts
        if alias is not None:
            assert (
                assemblies["tool_heads_assembly"]["inject_parts"][alias]
                == assembly_name
            )
            assert assembly_name in assemblies["tool_heads_assembly"]["depends_on"]
            assert (
                assemblies["whole_printer_assembly"]["inject_parts"][alias]
                == assembly_name
            )
            assert assembly_name in assemblies["whole_printer_assembly"]["depends_on"]

    placements = config["placement"]["alignments"]
    assert {
        "rigid_group": ["tool_head_cable_attach_shield_left_assembly"],
        "to": "tool_head_mount_machined_bottom_assembly",
    } in placements
    assert {
        "rigid_group": ["tool_head_cable_attach_shield_right_assembly"],
        "to": "tool_head_mount_machined_top_assembly",
    } in placements

    tool_head_parts = tool_heads_resource["Builder"]["Visualization"]["parts"]
    whole_printer_parts = whole_printer_resource["Builder"]["Visualization"]["parts"]
    for alias in [
        "tool_head_cable_attach_shield_left",
        "tool_head_cable_attach_shield_right",
    ]:
        assert any(part.get("assembly") == alias for part in tool_head_parts)
        assert any(part.get("assembly") == alias for part in whole_printer_parts)

    graph = builder_graph_model.build_graph_model(config["assemblies"], config)
    for assembly_name in expected:
        assert assembly_name in graph.assemblies_by_name
