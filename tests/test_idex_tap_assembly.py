from pathlib import Path

import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader


REPO_ROOT = ASSEMBLIES_DIR.parents[1]
T0_SUFFIX = "t" + "0"
STALE_TAP_PREFIX = "idex_tap_"
STALE_T0_TAP_TOKENS = (
    STALE_TAP_PREFIX + T0_SUFFIX,
    "IdexTap" + "T" + "0",
    "create_" + STALE_TAP_PREFIX + T0_SUFFIX,
)


def _load_assemblies():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    return {assembly["name"]: assembly for assembly in config["assemblies"]}


def test_idex_tap_assemblies_are_t1_named_in_builder_contract():
    assemblies = _load_assemblies()

    expected_resource_files = {
        "idex_tap_t1_assembly": "idex_tap_t1_assembly.yaml",
        "idex_tap_t1_shuttle_assembly": "idex_tap_t1_shuttle_assembly.yaml",
        "idex_tap_t1_stack_assembly": "idex_tap_t1_stack_assembly.yaml",
    }
    for assembly_name, resource_file in expected_resource_files.items():
        assert assembly_name in assemblies
        assert assemblies[assembly_name]["resource_file"] == resource_file

    for old_assembly_name in (
        STALE_TAP_PREFIX + T0_SUFFIX + "_assembly",
        STALE_TAP_PREFIX + T0_SUFFIX + "_shuttle_assembly",
        STALE_TAP_PREFIX + T0_SUFFIX + "_stack_assembly",
    ):
        assert old_assembly_name not in assemblies

    for top_level_name in ("tool_heads_assembly", "whole_printer_assembly"):
        top_level = assemblies[top_level_name]
        assert "idex_tap_t1_assembly" in top_level["depends_on"]
        assert "idex_tap_t1_shuttle_assembly" in top_level["depends_on"]
        assert top_level["inject_parts"]["idex_tap_t1"] == "idex_tap_t1_assembly"
        assert (
            top_level["inject_parts"]["idex_tap_t1_shuttle"]
            == "idex_tap_t1_shuttle_assembly"
        )
        assert STALE_TAP_PREFIX + T0_SUFFIX not in top_level["inject_parts"]
        assert (
            STALE_TAP_PREFIX + T0_SUFFIX + "_shuttle"
            not in top_level["inject_parts"]
        )

    shuttle = assemblies["idex_tap_t1_shuttle_assembly"]
    assert "idex_tap_t1_assembly" in shuttle["depends_on"]
    assert shuttle["inject_parts"]["idex_tap_t1"] == "idex_tap_t1_assembly"


def test_active_idex_tap_files_have_no_t0_prototype_symbols():
    active_paths = [
        REPO_ROOT / "MEGE_IDEX_TAP_CONCEPT.md",
        ASSEMBLIES_DIR / "assemblies.yaml",
        ASSEMBLIES_DIR / "tool_heads_assembly.yaml",
        ASSEMBLIES_DIR / "whole_printer_assembly.yaml",
        ASSEMBLIES_DIR / "idex_tap_t1_assembly.yaml",
        ASSEMBLIES_DIR / "idex_tap_t1_shuttle_assembly.yaml",
        ASSEMBLIES_DIR / "idex_tap_t1_stack_assembly.yaml",
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t1_assembly.py",
        ),
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/"
            "idex_tap_t1_shuttle_assembly.py",
        ),
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/"
            "idex_tap_t1_stack_assembly.py",
        ),
    ]

    for path in active_paths:
        text = path.read_text()
        for stale_token in STALE_T0_TAP_TOKENS:
            assert stale_token not in text, f"{path} still contains {stale_token}"
