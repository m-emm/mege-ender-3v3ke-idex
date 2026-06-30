import yaml

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.cable_clamp_assembly import (
    create_cable_clamp_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.cooleon_pair_housing_assembly import (
    create_cooleon_pair_housing_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.cooleon_psu_assembly import (
    create_cooleon_psu_assembly,
)
from shellforgepy.builder.builder import _resolve_scene_animation
from shellforgepy.simple import Alignment, align, get_bounding_box_center, rotate


RESOURCE_FILE = ASSEMBLIES_DIR / "cooleon_pair_housing_assembly.yaml"
ANIMATION_KEY = "cooleon_pair_housing_access_open"
HATCH_NAMES = {
    "cooleon_pair_housing_front_left_hatch",
    "cooleon_pair_housing_front_right_hatch",
    "cooleon_pair_housing_back_left_hatch",
    "cooleon_pair_housing_back_right_hatch",
}
LID_NAMES = [
    "cooleon_pair_housing_lid_left",
    "cooleon_pair_housing_lid_right",
]


def _load_resource():
    resource = yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    return resource


def _configured_part_names(rules):
    names = set()
    for rule in rules:
        if "name" in rule:
            names.add(rule["name"])
        names.update(rule.get("names", []))
    return names


def _find_follower_rule(parts, names):
    return next(
        part
        for part in parts
        if part.get("source") == "self"
        and part.get("artifact") == "followers"
        and part.get("names") == names
    )


def _build_cooleon_psu_pair():
    cooleon_psu_1 = create_cooleon_psu_assembly(
        **assembly_kwargs(create_cooleon_psu_assembly)
    )
    cooleon_psu_2 = create_cooleon_psu_assembly(
        **assembly_kwargs(create_cooleon_psu_assembly)
    )

    cooleon_psu_1 = rotate(
        90,
        center=get_bounding_box_center(cooleon_psu_1),
        axis=(1, 0, 0),
    )(cooleon_psu_1)
    cooleon_psu_2 = rotate(
        -90,
        center=get_bounding_box_center(cooleon_psu_2),
        axis=(1, 0, 0),
    )(cooleon_psu_2)
    cooleon_psu_2 = align(cooleon_psu_2, cooleon_psu_1, Alignment.CENTER, axes=[0, 2])
    cooleon_psu_2 = align(
        cooleon_psu_2,
        cooleon_psu_1,
        Alignment.STACK_BACK,
        stack_gap=DEFAULTS["cooleon_psu_back_to_back_gap"],
    )
    return cooleon_psu_1, cooleon_psu_2


def _build_input_cable_clamp():
    return create_cable_clamp_assembly(
        cable_clamp_hole_diameter=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_hole_diameter"
        ],
        cable_clamp_slit_width=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_slit_width"
        ],
        cable_clamp_arm_width=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_arm_width"
        ],
        cable_clamp_arm_depth=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_arm_depth"
        ],
        cable_clamp_arm_thickness=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_arm_thickness"
        ],
        cable_clamp_clearance=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_clearance"
        ],
        cable_clamp_screw_size=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_screw_size"
        ],
        cable_clamp_screw_length=DEFAULTS[
            "cooleon_pair_housing_input_cable_clamp_screw_length"
        ],
        BIG_THING=DEFAULTS["BIG_THING"],
    )


def _build_housing():
    cooleon_psu_1, cooleon_psu_2 = _build_cooleon_psu_pair()
    input_cable_clamp = _build_input_cable_clamp()
    return create_cooleon_pair_housing_assembly(
        **assembly_kwargs(
            create_cooleon_pair_housing_assembly,
            cooleon_psu_1=cooleon_psu_1,
            cooleon_psu_2=cooleon_psu_2,
            input_cable_clamp=input_cable_clamp,
        )
    )


def test_cooleon_pair_housing_lids_lift_for_access_animation():
    resource = _load_resource()
    parts = resource["Builder"]["Visualization"]["parts"]
    expected_lift = 2 * DEFAULTS["cooleon_pair_housing_hatch_height"]
    rule = _find_follower_rule(parts, LID_NAMES)

    assert rule["animation"] == {
        ANIMATION_KEY: [
            0,
            0,
            {"$expr": {"$sub": "2 * ${cooleon_pair_housing_hatch_height}"}},
        ]
    }

    resolved_animation, direction_keys = _resolve_scene_animation(
        rule["animation"],
        DEFAULTS,
    )
    assert direction_keys == set()
    assert resolved_animation[ANIMATION_KEY] == [0, 0, expected_lift]


def test_cooleon_pair_housing_yaml_does_not_export_standalone_hatches():
    resource = _load_resource()
    visualization_names = _configured_part_names(
        resource["Builder"]["Visualization"]["parts"]
    )
    production_names = _configured_part_names(
        resource["Builder"]["Production"]["parts"]
    )
    plate_names = {
        part_name
        for plate in resource["Builder"]["Production"]["arrange"]["plates"]
        for part_name in plate["parts"]
    }

    assert visualization_names.isdisjoint(HATCH_NAMES)
    assert production_names.isdisjoint(HATCH_NAMES)
    assert plate_names.isdisjoint(HATCH_NAMES)


def test_cooleon_pair_housing_generator_fuses_hatches_into_lids():
    housing = _build_housing()

    assert set(housing.follower_indices_by_name) == {
        "cooleon_pair_housing_left_body",
        "cooleon_pair_housing_right_body",
        "cooleon_pair_housing_lid_left",
        "cooleon_pair_housing_lid_right",
        "cooleon_pair_housing_input_cable_clamp",
    }
    assert HATCH_NAMES.isdisjoint(housing.follower_indices_by_name)
    assert "maintenance_hatch_openings" in housing.cutter_indices_by_name
