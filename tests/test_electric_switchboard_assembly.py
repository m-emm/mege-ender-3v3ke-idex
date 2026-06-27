import yaml

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader


ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"


def test_electric_switchboard_keeps_original_fuse_holder():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    electric_switchboard = assemblies["electric_switchboard_assembly"]

    assert electric_switchboard["depends_on"] == [
        "emergency_button_assembly",
        "fuse_holder_assembly",
    ]
    assert electric_switchboard["inject_parts"]["fuse_holder"] == "fuse_holder_assembly"
    assert (
        assemblies["fuse_holder_assembly"]["resource_file"]
        == "fuse_holder_assembly.yaml"
    )
    assert (
        assemblies["big_fuses_holder_assembly"]["resource_file"]
        == "fuse_holder_assembly.yaml"
    )
