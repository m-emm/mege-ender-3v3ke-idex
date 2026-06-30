import yaml

from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, AssemblyDefaultsLoader
from shellforgepy.builder.builder import _resolve_scene_animation


RESOURCE_FILE = ASSEMBLIES_DIR / "cooleon_pair_housing_assembly.yaml"
ANIMATION_KEY = "cooleon_pair_housing_access_open"


def _load_visualization_parts():
    resource = yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    return resource["Builder"]["Visualization"]["parts"]


def _find_follower_rule(parts, names):
    return next(
        part
        for part in parts
        if part.get("source") == "self"
        and part.get("artifact") == "followers"
        and part.get("names") == names
    )


def test_cooleon_pair_housing_lids_and_hatches_lift_for_access_animation():
    parts = _load_visualization_parts()
    lid_names = [
        "cooleon_pair_housing_lid_left",
        "cooleon_pair_housing_lid_right",
    ]
    hatch_names = [
        "cooleon_pair_housing_front_left_hatch",
        "cooleon_pair_housing_front_right_hatch",
        "cooleon_pair_housing_back_left_hatch",
        "cooleon_pair_housing_back_right_hatch",
    ]
    expected_lift = 2 * DEFAULTS["cooleon_pair_housing_hatch_height"]

    for rule in [
        _find_follower_rule(parts, lid_names),
        _find_follower_rule(parts, hatch_names),
    ]:
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
