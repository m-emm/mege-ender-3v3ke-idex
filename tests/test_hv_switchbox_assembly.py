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
from shellforgepy.simple import (
    MScrew,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
)


RESOURCE_FILE = ASSEMBLIES_DIR / "hv_switchbox_assembly.yaml"
ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
WHOLE_PRINTER_RESOURCE_FILE = ASSEMBLIES_DIR / "whole_printer_assembly.yaml"
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
FUSE_HOLDER_PARAMETER_SUFFIXES = (
    "thread_diameter",
    "thread_length",
    "total_cylinder_length",
    "thin_cylinder_diameter",
    "thin_cylinder_length",
    "thicker_cylinder_diameter",
    "thicker_cylinder_length",
    "front_diameter",
    "front_length",
    "mount_nut_outer_diameter",
    "mount_nut_thickness",
    "mount_hole_clearance",
    "body_clearance",
)


@pytest.fixture(scope="module")
def hv_switchbox():
    fuse_holder = create_fuse_holder_assembly(
        **assembly_kwargs(
            create_fuse_holder_assembly,
            **{
                f"fuse_holder_{suffix}": DEFAULTS[f"big_fuses_holder_{suffix}"]
                for suffix in FUSE_HOLDER_PARAMETER_SUFFIXES
            },
        )
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


def _visualized_names(resource):
    names = set()
    for part in resource["Builder"]["Visualization"]["parts"]:
        names.update(part.get("names", []))
        if "name" in part:
            names.add(part["name"])
    return names


def _visualized_names_for(resource, *, source=None, assembly=None):
    names = set()
    for part in resource["Builder"]["Visualization"]["parts"]:
        if source is not None and part.get("source") != source:
            continue
        if assembly is not None and part.get("assembly") != assembly:
            continue
        names.update(part.get("names", []))
        if "name" in part:
            names.add(part["name"])
    return names


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
    assert "hv_switchbox_terminal_rail" not in names
    assert "ssr_mount_bosses" not in names
    assert "lid_mount_screw_0_thread_inset" in names
    assert "lid_mount_screw_3_thread_inset" in names
    assert not any(
        name.startswith("lid_mount_screw_") and name.endswith("_nut") for name in names
    )
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


def test_hv_switchbox_uses_big_fuses_holder(hv_switchbox):
    holder_body = hv_switchbox.get_named_non_production_part("fuse_holder_holder_body")
    mount_nut = hv_switchbox.get_named_non_production_part("fuse_holder_mount_nut")
    mount_hole = hv_switchbox.get_named_cutter("fuse_holder_mount_hole")

    assert get_bounding_box_size(holder_body) == pytest.approx(
        (
            DEFAULTS["big_fuses_holder_front_diameter"],
            DEFAULTS["big_fuses_holder_front_diameter"],
            DEFAULTS["big_fuses_holder_total_cylinder_length"],
        ),
        abs=0.05,
    )
    assert get_bounding_box_size(mount_nut)[2] == pytest.approx(
        DEFAULTS["big_fuses_holder_mount_nut_thickness"],
        abs=0.05,
    )
    assert max(get_bounding_box_size(mount_nut)[:2]) == pytest.approx(
        DEFAULTS["big_fuses_holder_mount_nut_outer_diameter"],
        abs=0.05,
    )
    assert get_bounding_box_size(mount_hole)[:2] == pytest.approx(
        (
            DEFAULTS["big_fuses_holder_thread_diameter"]
            + DEFAULTS["big_fuses_holder_mount_hole_clearance"],
            DEFAULTS["big_fuses_holder_thread_diameter"]
            + DEFAULTS["big_fuses_holder_mount_hole_clearance"],
        ),
        abs=0.05,
    )


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


def test_hv_switchbox_ssr_mount_nut_pockets_open_to_boss_top(hv_switchbox):
    boss_center_x = (
        DEFAULTS["hv_switchbox_width"]
        - DEFAULTS["hv_switchbox_wall_thickness"]
        - DEFAULTS["hv_switchbox_ssr_mount_boss_depth"] / 2
    )
    boss_top_z = (
        DEFAULTS["hv_switchbox_ssr_z_center"]
        + DEFAULTS["hv_switchbox_ssr_mount_boss_height"] / 2
    )

    for mount_index in [1, 2]:
        mount_hole = hv_switchbox.get_named_cutter(f"ssr_mount_hole_{mount_index}")
        mount_nut = hv_switchbox.get_named_non_production_part(
            f"ssr_mount_nut_{mount_index}"
        )
        mount_pocket = hv_switchbox.get_named_cutter(
            f"ssr_mount_nut_pocket_{mount_index}"
        )
        mount_hole_center = get_bounding_box_center(mount_hole)

        assert get_bounding_box(mount_pocket)[1][2] >= boss_top_z - 0.05
        assert get_bounding_box_center(mount_nut) == pytest.approx(
            (
                boss_center_x,
                mount_hole_center[1],
                DEFAULTS["hv_switchbox_ssr_z_center"],
            ),
            abs=0.05,
        )


def test_hv_switchbox_terminal_nut_pockets_open_to_rail_top(hv_switchbox):
    rail_center_x = (
        DEFAULTS["hv_switchbox_width"]
        - DEFAULTS["hv_switchbox_wall_thickness"]
        - DEFAULTS["hv_switchbox_terminal_rail_height"] / 2
    )
    rail_center_z = (
        DEFAULTS["hv_switchbox_terminal_rail_z_offset_from_bottom"]
        + DEFAULTS["hv_switchbox_terminal_rail_width"] / 2
    )
    rail_top_z = (
        DEFAULTS["hv_switchbox_terminal_rail_z_offset_from_bottom"]
        + DEFAULTS["hv_switchbox_terminal_rail_width"]
    )

    for terminal_index in range(1, DEFAULTS["hv_switchbox_terminal_num_spots"] + 1):
        terminal_hole = hv_switchbox.get_named_cutter(f"terminal_hole_{terminal_index}")
        terminal_nut = hv_switchbox.get_named_non_production_part(
            f"terminal_nut_{terminal_index}"
        )
        terminal_pocket = hv_switchbox.get_named_cutter(
            f"terminal_nut_pocket_{terminal_index}"
        )
        terminal_hole_center = get_bounding_box_center(terminal_hole)

        assert get_bounding_box(terminal_pocket)[1][2] >= rail_top_z - 0.05
        assert get_bounding_box_center(terminal_nut) == pytest.approx(
            (
                rail_center_x,
                terminal_hole_center[1],
                rail_center_z,
            ),
            abs=0.05,
        )


def test_hv_switchbox_lid_screws_use_threaded_insets(hv_switchbox):
    screw_spec = MScrew.from_size(DEFAULTS["hv_switchbox_lid_screw_size"])
    inset_depth = (
        screw_spec.thread_inset_length
        + DEFAULTS["hv_switchbox_lid_thread_inset_extra_screw_depth"]
    )

    for lid_screw_index in range(4):
        screw = hv_switchbox.get_named_non_production_part(
            f"lid_mount_screw_{lid_screw_index}_screw"
        )
        hole = hv_switchbox.get_named_cutter(
            f"lid_mount_screw_{lid_screw_index}_hole_cutter"
        )
        inset = hv_switchbox.get_named_non_production_part(
            f"lid_mount_screw_{lid_screw_index}_thread_inset"
        )
        inset_cutter = hv_switchbox.get_named_cutter(
            f"lid_mount_screw_{lid_screw_index}_assembly_cutter"
        )

        screw_center = get_bounding_box_center(screw)
        hole_center = get_bounding_box_center(hole)
        inset_center = get_bounding_box_center(inset)
        inset_bbox = get_bounding_box(inset)
        inset_cutter_bbox = get_bounding_box(inset_cutter)

        assert inset_center[1:] == pytest.approx(hole_center[1:], abs=0.05)
        assert screw_center[1:] == pytest.approx(hole_center[1:], abs=0.05)
        assert inset_bbox[0][0] == pytest.approx(0, abs=0.05)
        assert inset_cutter_bbox[0][0] == pytest.approx(0, abs=0.05)
        assert get_bounding_box_size(inset)[0] == pytest.approx(
            screw_spec.thread_inset_length,
            abs=0.05,
        )
        assert get_bounding_box_size(inset_cutter)[0] == pytest.approx(
            inset_depth,
            abs=0.05,
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


def test_hv_switchbox_resources_do_not_visualize_duplicate_fused_parts():
    duplicate_names = {"hv_switchbox_terminal_rail", "ssr_mount_bosses"}

    hv_resource = yaml.safe_load(RESOURCE_FILE.read_text())
    whole_printer_resource = yaml.safe_load(WHOLE_PRINTER_RESOURCE_FILE.read_text())

    assert _visualized_names(hv_resource).isdisjoint(duplicate_names)
    assert _visualized_names(whole_printer_resource).isdisjoint(duplicate_names)


def test_hv_switchbox_resources_visualize_lid_threaded_insets():
    hv_resource = yaml.safe_load(RESOURCE_FILE.read_text())
    whole_printer_resource = yaml.safe_load(WHOLE_PRINTER_RESOURCE_FILE.read_text())
    hv_resource_names = _visualized_names(hv_resource)
    whole_printer_hv_names = _visualized_names_for(
        whole_printer_resource,
        source="injected",
        assembly="hv_switchbox",
    )

    assert "lid_mount_screw_*_thread_inset" in hv_resource_names
    assert "lid_mount_screw_*_nut" not in hv_resource_names
    assert "lid_mount_screw_*_thread_inset" in whole_printer_hv_names
    assert "lid_mount_screw_*_nut" not in whole_printer_hv_names


def test_hv_switchbox_is_registered_and_injected_into_whole_printer():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    hv_switchbox = assemblies["hv_switchbox_assembly"]
    assert hv_switchbox["resource_file"] == "hv_switchbox_assembly.yaml"
    assert hv_switchbox["depends_on"] == [
        "big_fuses_holder_assembly",
        "fotek_ssr_assembly",
    ]
    assert hv_switchbox["inject_parts"] == {
        "fuse_holder": "big_fuses_holder_assembly",
        "ssr": "fotek_ssr_assembly",
    }
    assert "fuse_holder_assembly" in assemblies
    assert "big_fuses_holder_assembly" in assemblies
    assert (
        assemblies["big_fuses_holder_assembly"]["resource_file"]
        == "fuse_holder_assembly.yaml"
    )
    assert assemblies["electric_switchboard_assembly"]["depends_on"] == [
        "emergency_button_assembly",
        "fuse_holder_assembly",
    ]
    assert assemblies["electric_switchboard_assembly"]["inject_parts"][
        "fuse_holder"
    ] == ("fuse_holder_assembly")
    assert hv_switchbox["parameters"][
        "hv_switchbox_lid_thread_inset_extra_screw_depth"
    ] == {"$ref": "hv_switchbox_lid_thread_inset_extra_screw_depth"}

    whole_printer = assemblies["whole_printer_assembly"]
    assert "hv_switchbox_assembly" in whole_printer["depends_on"]
    assert whole_printer["inject_parts"]["hv_switchbox"] == "hv_switchbox_assembly"
