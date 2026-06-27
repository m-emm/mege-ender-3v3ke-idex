import pytest
import yaml

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.fuse_holder_assembly import (
    create_fuse_holder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.hv_switchbox_assembly import (
    create_hv_switchbox_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.panasonic_ssr_assembly import (
    create_panasonic_ssr_assembly,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size


RESOURCE_FILE = ASSEMBLIES_DIR / "hv_switchbox_assembly.yaml"
ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
SSR_PARAMETER_SUFFIXES = (
    "width",
    "length",
    "height",
    "corner_fillet_radius",
    "mount_hole_diameter",
    "mount_hole_pitch",
    "terminal_screw_x_inset",
    "output_terminal_y_inset",
    "input_terminal_y_inset",
    "output_terminal_screw_size",
    "input_terminal_screw_size",
    "terminal_screw_head_height",
    "output_cover_depth",
    "input_cover_depth",
    "cover_recess_depth",
)


@pytest.fixture(scope="module")
def hv_switchbox():
    fuse_holder = create_fuse_holder_assembly(
        **assembly_kwargs(create_fuse_holder_assembly)
    )
    ssr = create_panasonic_ssr_assembly(
        **assembly_kwargs(
            create_panasonic_ssr_assembly,
            **{
                f"panasonic_ssr_{suffix}": DEFAULTS[f"fotek_ssr_{suffix}"]
                for suffix in SSR_PARAMETER_SUFFIXES
            },
        )
    )
    return create_hv_switchbox_assembly(
        **assembly_kwargs(
            create_hv_switchbox_assembly,
            fuse_holder=fuse_holder,
            ssr=ssr,
        )
    )


def _all_named_artifacts(assembly):
    return (
        set(assembly.follower_indices_by_name)
        | set(assembly.cutter_indices_by_name)
        | set(assembly.non_production_indices_by_name)
    )


def _assert_inside_hv_inner_enclosure(part):
    bbox = get_bounding_box(part)
    wall = DEFAULTS["hv_switchbox_wall_thickness"]
    inner_bounds = (
        (0, wall, wall),
        (
            DEFAULTS["hv_switchbox_width"] - wall,
            DEFAULTS["hv_switchbox_depth"] - wall,
            DEFAULTS["hv_switchbox_height"] - wall,
        ),
    )

    for axis in range(3):
        assert bbox[0][axis] >= inner_bounds[0][axis] - 0.05
        assert bbox[1][axis] <= inner_bounds[1][axis] + 0.05


def test_hv_switchbox_reference_matches_requested_external_size(hv_switchbox):
    reference = hv_switchbox.get_named_non_production_part(
        "hv_switchbox_body_reference"
    )

    assert get_bounding_box_size(reference) == pytest.approx(
        (
            DEFAULTS["hv_switchbox_width"],
            DEFAULTS["hv_switchbox_depth"],
            DEFAULTS["hv_switchbox_height"],
        ),
        abs=0.05,
    )


def test_hv_switchbox_exports_lid_cable_cover_fuse_holder_and_ssr(hv_switchbox):
    names = _all_named_artifacts(hv_switchbox)

    assert "hv_switchbox_lid" in hv_switchbox.follower_indices_by_name
    assert "hv_switchbox_cable_cutout_cover" in hv_switchbox.follower_indices_by_name
    assert "fuse_holder_holder_body" in names
    assert "fuse_holder_mount_hole" in names
    assert "ssr_body" in names
    assert "ssr_mounting_hole_pattern" in names
    assert not any("emergency" in name.lower() for name in names)


def test_hv_switchbox_uses_fotek_ssr_body_and_keeps_it_internal(hv_switchbox):
    ssr_body = hv_switchbox.get_named_non_production_part("ssr_body")

    assert get_bounding_box_size(ssr_body) == pytest.approx(
        (
            DEFAULTS["fotek_ssr_height"],
            DEFAULTS["fotek_ssr_length"],
            DEFAULTS["fotek_ssr_width"],
        ),
        abs=0.05,
    )
    _assert_inside_hv_inner_enclosure(ssr_body)


def test_hv_switchbox_has_six_internal_m4_terminal_stations(hv_switchbox):
    for terminal_index in range(1, DEFAULTS["hv_switchbox_terminal_num_spots"] + 1):
        hv_switchbox.get_named_non_production_part(f"terminal_screw_{terminal_index}")
        hv_switchbox.get_named_non_production_part(f"terminal_nut_{terminal_index}")
        hv_switchbox.get_named_cutter(f"terminal_hole_{terminal_index}")
        hv_switchbox.get_named_cutter(f"terminal_nut_pocket_{terminal_index}")

    assert DEFAULTS["hv_switchbox_terminal_num_spots"] == 6


def test_hv_switchbox_ssr_mounting_hardware_is_fully_internal(hv_switchbox):
    for mount_index in [1, 2]:
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_non_production_part(f"ssr_mount_screw_{mount_index}")
        )
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_non_production_part(f"ssr_mount_nut_{mount_index}")
        )
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_cutter(f"ssr_mount_hole_{mount_index}")
        )
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_cutter(f"ssr_mount_nut_pocket_{mount_index}")
        )


def test_hv_switchbox_terminal_hardware_is_fully_internal(hv_switchbox):
    for terminal_index in range(1, DEFAULTS["hv_switchbox_terminal_num_spots"] + 1):
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_non_production_part(
                f"terminal_screw_{terminal_index}"
            )
        )
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_non_production_part(f"terminal_nut_{terminal_index}")
        )
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_cutter(f"terminal_hole_{terminal_index}")
        )
        _assert_inside_hv_inner_enclosure(
            hv_switchbox.get_named_cutter(f"terminal_nut_pocket_{terminal_index}")
        )


def test_hv_switchbox_resource_uses_petgcf_production_settings():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    production = resource["Builder"]["Production"]
    plates = {plate["name"]: plate for plate in production["arrange"]["plates"]}

    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    for plate_name in ["hv_switchbox_box", "hv_switchbox_lid"]:
        plate = plates[plate_name]
        overrides = plate["process_data"]["overrides"]["process_overrides"]
        assert plate["process_data_preset"] == "petgcf_max_strength_high_speed_06"
        assert overrides["brim_type"] == "no_brim"
        assert overrides["enable_support"] == "1"
        assert overrides["support_type"] == "tree(auto)"
        assert overrides["support_style"] == "organic"
        assert overrides["support_on_build_plate_only"] == "1"
        assert overrides["support_interface_spacing"] == "2"
        assert overrides["wall_loops"] == "3"


def test_hv_switchbox_is_registered_and_injected_into_whole_printer():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    hv_switchbox = assemblies["hv_switchbox_assembly"]
    assert hv_switchbox["resource_file"] == "hv_switchbox_assembly.yaml"
    assert hv_switchbox["depends_on"] == [
        "fuse_holder_assembly",
        "fotek_ssr_assembly",
    ]
    assert hv_switchbox["inject_parts"] == {
        "fuse_holder": "fuse_holder_assembly",
        "ssr": "fotek_ssr_assembly",
    }

    whole_printer = assemblies["whole_printer_assembly"]
    assert "hv_switchbox_assembly" in whole_printer["depends_on"]
    assert whole_printer["inject_parts"]["hv_switchbox"] == "hv_switchbox_assembly"
