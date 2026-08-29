import yaml

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from mege_3devops.process_data.parametric import load_material_spec


PETGCF_06_STOCK_PRESET_NAMES = (
    "petgcf_low_strength_high_speed_06",
    "petgcf_max_strength_high_speed_06",
    "petgcf_medium_strength_high_speed_06",
    "petgcf_medium_strength_max_quality_06",
    "petgcf_medium_strength_medium_quality_06",
)

MIGRATED_PETGCF_RESOURCE_FILES = (
    "aukey_nozzle_cam_holder_assembly.yaml",
    "cooleon_pair_housing_assembly.yaml",
    "creality_psu_assembly.yaml",
    "electric_switchboard_assembly.yaml",
    "heatbed_psu_housing_assembly.yaml",
    "hv_switchbox_assembly.yaml",
    "nitehawk_usb_dual_board_housing_assembly.yaml",
    "part_fan_assembly.yaml",
    "printer_host_and_screen_assembly.yaml",
    "tb6600_stripboard_interface_housing_assembly.yaml",
    "tool_heads_assembly.yaml",
    "vision_light_mount_assembly.yaml",
    "x_axis_belt_carriage_assembly.yaml",
    "y_z_axis_mcu_holder_fan_joiner.yaml",
    "z_axis_top_mount_assembly.yaml",
)


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def _assert_petgcf_06_intent(preset, *, generator):
    arguments = preset["arguments"]
    material = load_material_spec(arguments["material_name"])

    assert preset["generator"] == generator
    assert material.family == "PETG_CF"
    assert arguments["nozzle_diameter_mm"] == 0.6
    assert arguments["nozzle_hardened"] is True
    assert arguments["nozzle_high_flow"] is True

    overrides = preset.get("overrides", {}).get("process_overrides")
    assert isinstance(overrides, dict)
    assert all(isinstance(key, str) and key for key in overrides)


def _find_process_override_mappings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "process_overrides":
                yield child
            yield from _find_process_override_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _find_process_override_mappings(child)


def test_petgcf_06_stock_presets_keep_valid_petgcf_process_intent():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    presets = config["process_data_presets"]

    for preset_name in PETGCF_06_STOCK_PRESET_NAMES:
        assert preset_name in presets
        _assert_petgcf_06_intent(
            presets[preset_name], generator="mege3devops_parametric"
        )


def test_petgcf_06_idex_one_off_preset_keeps_valid_petgcf_process_intent():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    preset = config["process_data_presets"]["petgcf_max_strength_high_speed_06_idex"]

    _assert_petgcf_06_intent(preset, generator="mege3devops_idex_parametric")


def test_migrated_petgcf_assemblies_keep_small_valid_local_override_mappings():
    for resource_name in MIGRATED_PETGCF_RESOURCE_FILES:
        resource = _load_yaml(ASSEMBLIES_DIR / resource_name)
        for overrides in _find_process_override_mappings(resource):
            assert isinstance(overrides, dict), resource_name
            assert all(isinstance(key, str) and key for key in overrides), resource_name
            assert len(overrides) <= 5, resource_name


def test_plain_pla_06_preset_keeps_valid_pla_nozzle_intent():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")

    preset = config["process_data_presets"]["pla_medium_strength_max_quality_06"]
    arguments = preset["arguments"]
    material = load_material_spec(arguments["material_name"])

    assert preset["generator"] == "mege3devops_parametric"
    assert material.family == "PLA"
    assert arguments["nozzle_diameter_mm"] == 0.6
    assert arguments["nozzle_hardened"] is False
    assert arguments["nozzle_high_flow"] is True
    assert isinstance(preset.get("overrides", {}).get("process_overrides"), dict)
