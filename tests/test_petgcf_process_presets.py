import yaml

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from mege_3devops.process_data.parametric import load_material_spec


PETGCF_06_ANTI_SHIFT_OVERRIDES = {
    "z_hop": "0.45",
    "retract_lift_above": "0",
    "retract_lift_below": "0",
    "retract_lift_enforce": "All Surfaces",
    "wipe": "0",
    "travel_speed": "350",
    "travel_acceleration": "5000",
    "default_acceleration": "5000",
    "initial_layer_acceleration": "5000",
    "travel_jerk": "8",
    "default_jerk": "8",
    "initial_layer_jerk": "8",
    "top_surface_acceleration": "2650",
    "internal_solid_infill_acceleration": "4240",
    "sparse_infill_acceleration": "4240",
}

PETGCF_06_IDEX_SLOW_MOTION_OVERRIDES = {
    "travel_speed": "200",
    "travel_acceleration": "2000",
    "default_acceleration": "2000",
    "initial_layer_acceleration": "2000",
    "outer_wall_acceleration": "2000",
    "inner_wall_acceleration": "2000",
    "top_surface_acceleration": "2000",
    "internal_solid_infill_acceleration": "2000",
    "sparse_infill_acceleration": "2000",
    "bridge_acceleration": "2000",
    "travel_jerk": "2",
    "default_jerk": "2",
    "initial_layer_jerk": "2",
    "outer_wall_jerk": "2",
    "inner_wall_jerk": "2",
    "infill_jerk": "2",
    "top_surface_jerk": "2",
}


def test_petgcf_06_presets_include_anti_shift_motion_overrides():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    presets = config["process_data_presets"]
    petgcf_06_preset_names = sorted(
        name for name in presets if name.startswith("petgcf_") and name.endswith("_06")
    )

    assert petgcf_06_preset_names == [
        "petgcf_low_strength_high_speed_06",
        "petgcf_max_strength_high_speed_06",
        "petgcf_medium_strength_high_speed_06",
        "petgcf_medium_strength_max_quality_06",
        "petgcf_medium_strength_medium_quality_06",
    ]
    for preset_name in petgcf_06_preset_names:
        overrides = presets[preset_name]["overrides"]["process_overrides"]
        for key, value in PETGCF_06_ANTI_SHIFT_OVERRIDES.items():
            assert overrides[key] == value


def test_petgcf_06_idex_one_off_preset_keeps_stock_petgcf_tuning_slowly():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    preset = config["process_data_presets"]["petgcf_max_strength_high_speed_06_idex"]

    assert preset["generator"] == "mege3devops_idex_parametric"
    assert preset["arguments"] == {
        "material_name": "petg_cf_generic",
        "nozzle_diameter_mm": 0.6,
        "nozzle_hardened": True,
        "nozzle_high_flow": True,
        "strength_factor": 0.9,
        "quality_factor": 0.5,
    }
    overrides = preset["overrides"]["process_overrides"]
    assert overrides["sparse_infill_pattern"] == "cubic"
    assert overrides["support_object_first_layer_gap"] == "2.5"
    assert overrides["xy_contour_compensation"] == "-0.3"
    assert overrides["xy_hole_compensation"] == "0.4"
    for key, value in PETGCF_06_ANTI_SHIFT_OVERRIDES.items():
        if key in PETGCF_06_IDEX_SLOW_MOTION_OVERRIDES:
            continue
        assert overrides[key] == value
    for key, value in PETGCF_06_IDEX_SLOW_MOTION_OVERRIDES.items():
        assert overrides[key] == value


def test_plain_pla_06_preset_uses_medium_strength_max_quality_intent():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    preset = config["process_data_presets"]["pla_medium_strength_max_quality_06"]
    arguments = preset["arguments"]
    material = load_material_spec(arguments["material_name"])

    assert preset["generator"] == "mege3devops_parametric"
    assert material.family == "PLA"
    assert arguments["nozzle_diameter_mm"] == 0.6
    assert arguments["nozzle_hardened"] is False
    assert 0.45 <= arguments["strength_factor"] <= 0.55
    assert arguments["quality_factor"] > arguments["strength_factor"]
    assert arguments["quality_factor"] >= 0.9
