import yaml

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader


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
