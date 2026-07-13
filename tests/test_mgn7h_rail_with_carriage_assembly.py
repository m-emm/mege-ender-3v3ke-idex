import inspect

import pytest
import yaml
from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.mgn7h_rail_with_carriage_assembly import (
    create_mgn7h_rail_with_carriage_assembly,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn7h_rail
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn7h_rail_with_carriage
from shellforgepy.simple import (
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)


RESOURCE_FILE = ASSEMBLIES_DIR / "mgn7h_rail_with_carriage_assembly.yaml"

MGN7H_PARAMETER_NAMES = [
    "mgn7h_rail_length",
    "mgn7h_rail_width",
    "mgn7h_rail_height",
    "mgn7h_rail_mount_hole_pitch",
    "mgn7h_rail_mount_hole_end_offset",
    "mgn7h_rail_mount_hole_diameter",
    "mgn7h_rail_mount_counterbore_diameter",
    "mgn7h_rail_mount_counterbore_depth",
    "mgn7h_rail_mount_screw_size",
    "mgn7h_rail_side_relief_depth",
    "mgn7h_rail_side_relief_height",
    "rail_mock_clearance",
    "rail_mock_groove_clearance",
    "mgn7h_carriage_length",
    "mgn7h_carriage_width",
    "mgn7h_carriage_height",
    "mgn7h_carriage_h1_offset",
    "mgn7h_carriage_mount_hole_pitch_x",
    "mgn7h_carriage_mount_hole_pitch_y",
    "mgn7h_carriage_mount_hole_depth",
    "mgn7h_carriage_mount_screw_size",
    "mgn7h_carriage_rest_offset_on_rail",
]


def _load_resource():
    return yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)


def _mgn7h_parameters():
    return {name: DEFAULTS[name] for name in MGN7H_PARAMETER_NAMES}


def test_mgn7h_rail_with_carriage_signature_matches_resource_parameters():
    signature_parameters = inspect.signature(
        create_mgn7h_rail_with_carriage_assembly
    ).parameters
    resource = _load_resource()

    for parameter_name in MGN7H_PARAMETER_NAMES:
        assert parameter_name in signature_parameters
        assert parameter_name in resource["Parameters"]


def test_mgn7h_rail_production_exports_single_pla_mockup_rail():
    resource = _load_resource()

    assert resource["Builder"]["Visualization"]["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "rail",
            "color": [0.74, 0.78, 0.82],
        },
        {
            "source": "self",
            "artifact": "followers",
            "names": ["carriage"],
            "name_template": "{name}",
            "color": [0.8, 0.84, 0.88],
        },
    ]

    production = resource["Builder"]["Production"]
    assert production["parts"] == [
        {
            "source": "self",
            "artifact": "followers",
            "names": ["rail_mockup_printable"],
            "name": "mgn7h_rail_mockup",
        }
    ]
    assert production["arrange"]["export_individual_parts"] is False
    assert production["arrange"]["auto_assign_plates"] is False
    assert production["arrange"]["plates"] == [
        {
            "name": "mgn7h_rail_mockup",
            "filename": "mgn7h_rail_mockup",
            "process_data_preset": "pla_medium_strength_max_quality_06",
            "process_data": {
                "overrides": {
                    "process_overrides": {
                        "enable_support": "0",
                        "brim_type": "no_brim",
                    }
                }
            },
            "parts": ["mgn7h_rail_mockup"],
        }
    ]


def test_mgn7h_rail_geometry_preserves_envelope_and_adds_printable_reliefs():
    rail_kwargs = {
        "length_mm": 60,
        "rail_width": 7,
        "rail_height": 4.8,
        "rail_mount_hole_pitch": 15,
        "rail_mount_hole_end_offset": 7.5,
        "rail_mount_hole_diameter": 2.4,
        "rail_mount_counterbore_diameter": 4.2,
        "rail_mount_counterbore_depth": 2.4,
        "rail_side_relief_depth": 0.55,
        "rail_side_relief_height": 1.7,
    }

    relieved_rail = create_mgn7h_rail(**rail_kwargs)
    plain_rail = create_mgn7h_rail(
        **{
            **rail_kwargs,
            "rail_side_relief_depth": 0,
            "rail_side_relief_height": 0,
        }
    )

    assert get_bounding_box_size(relieved_rail.leader) == pytest.approx(
        get_bounding_box_size(plain_rail.leader)
    )
    assert get_bounding_box_size(relieved_rail.leader) == pytest.approx(
        (
            rail_kwargs["length_mm"],
            rail_kwargs["rail_width"],
            rail_kwargs["rail_height"],
        )
    )
    assert get_volume(relieved_rail.leader) < get_volume(plain_rail.leader)

    for cutter_name in ["side_relief_front", "side_relief_back"]:
        assert cutter_name in relieved_rail.cutter_indices_by_name
        assert cutter_name not in plain_rail.cutter_indices_by_name


def test_mgn7h_rail_mount_hole_centers_follow_end_offset_and_pitch():
    rail = create_mgn7h_rail(
        length_mm=60,
        rail_width=7,
        rail_height=4.8,
        rail_mount_hole_pitch=15,
        rail_mount_hole_end_offset=7.5,
        rail_mount_hole_diameter=2.4,
        rail_mount_counterbore_diameter=4.2,
        rail_mount_counterbore_depth=2.4,
        rail_side_relief_depth=0,
        rail_side_relief_height=0,
    )

    hole_centers = [
        get_bounding_box_center(rail.get_named_cutter(f"mounting_hole_{index}"))
        for index in range(1, 5)
    ]
    assert [center[0] for center in hole_centers] == pytest.approx(
        [7.5, 22.5, 37.5, 52.5]
    )
    assert [center[1] for center in hole_centers] == pytest.approx([3.5] * 4)


def test_mgn7h_printable_mockup_follower_is_clearance_adjusted():
    rail_width = 7
    rail_height = 4.8
    rail_mock_clearance = 0.15
    rail_side_relief_depth = 0.55
    rail_side_relief_height = 1.7
    rail_mock_groove_clearance = 0.06
    rail_kwargs = {
        "length_mm": 60,
        "rail_width": rail_width,
        "rail_height": rail_height,
        "rail_mount_hole_pitch": 15,
        "rail_mount_hole_end_offset": 7.5,
        "rail_mount_hole_diameter": 2.4,
        "rail_mount_counterbore_diameter": 4.2,
        "rail_mount_counterbore_depth": 2.4,
        "rail_side_relief_depth": rail_side_relief_depth,
        "rail_side_relief_height": rail_side_relief_height,
    }

    assembly = create_mgn7h_rail_with_carriage(
        **rail_kwargs,
        rail_mock_clearance=rail_mock_clearance,
        rail_mock_groove_clearance=rail_mock_groove_clearance,
    )
    printable = assembly.get_named_follower("rail_mockup_printable")
    expected_width = rail_width - 2 * rail_mock_clearance
    expected_height = rail_height - 2 * rail_mock_clearance

    assert get_bounding_box_size(printable) == pytest.approx(
        (rail_kwargs["length_mm"], expected_width, expected_height)
    )
    assert get_bounding_box_center(printable) == pytest.approx(
        get_bounding_box_center(assembly.leader)
    )

    expected_printable = create_mgn7h_rail(
        **{
            **rail_kwargs,
            "rail_width": expected_width,
            "rail_height": expected_height,
            "rail_side_relief_depth": rail_side_relief_depth
            + rail_mock_groove_clearance,
        }
    )
    baseline_printable = create_mgn7h_rail(
        **{
            **rail_kwargs,
            "rail_width": expected_width,
            "rail_height": expected_height,
        }
    )

    assert get_volume(printable) == pytest.approx(get_volume(expected_printable.leader))
    assert get_volume(printable) < get_volume(baseline_printable.leader)

    hole_centers = [
        get_bounding_box_center(
            expected_printable.get_named_cutter(f"mounting_hole_{index}")
        )
        for index in range(1, 5)
    ]
    assert [center[0] for center in hole_centers] == pytest.approx(
        [7.5, 22.5, 37.5, 52.5]
    )


def test_mgn7h_assembly_keeps_carriage_context_and_printable_mockup():
    assembly = create_mgn7h_rail_with_carriage_assembly(
        **assembly_kwargs(
            create_mgn7h_rail_with_carriage_assembly,
            **_mgn7h_parameters(),
        )
    )

    assert get_volume(assembly.leader) > 0
    assert assembly.get_named_follower("carriage")
    assert assembly.get_named_follower("rail_mockup_printable")
    assert "rail_body" in assembly.follower_indices_by_name
