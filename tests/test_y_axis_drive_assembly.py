import yaml
import pytest

from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.y_axis_drive_assembly import (
    _DriveConfig,
    _align_gt2_motor_pulley_running_surface_to_pulley,
    _create_gt2_motor_pulley_running_surface_reference,
    _create_y_axis_motor_mount,
)
from mege_ender_3v3ke_idex.designs.assemblies.y_axis_nema23_motor_bracket_assembly import (
    create_y_axis_nema23_motor_bracket_assembly,
)
from mege_ender_3v3ke_idex.designs.gt2belt import gt2_thickness, gt2_width
from shellforgepy.simple import create_box, get_bounding_box


def _drive_config():
    return _DriveConfig(
        x_axis_motor_axle_length=DEFAULTS["x_axis_motor_axle_length"],
        motor_mount_axle_clearance=DEFAULTS["motor_mount_axle_clearance"],
        motor_mount_boss_clearance=DEFAULTS["motor_mount_boss_clearance"],
        motor_mount_boss_clearance_z=DEFAULTS["motor_mount_boss_clearance_z"],
        motor_mount_plate_thickness=DEFAULTS["motor_mount_plate_thickness"],
        motor_mount_plate_fillet_radius=DEFAULTS["motor_mount_plate_fillet_radius"],
        y_axis_drive_profile_mount_plate_width=DEFAULTS[
            "y_axis_drive_profile_mount_plate_width"
        ],
        y_axis_drive_profile_mount_plate_height=DEFAULTS[
            "y_axis_drive_profile_mount_plate_height"
        ],
        y_axis_drive_profile_mount_plate_thickness=DEFAULTS[
            "y_axis_drive_profile_mount_plate_thickness"
        ],
        y_axis_drive_profile_mount_plate_fillet_radius=DEFAULTS[
            "y_axis_drive_profile_mount_plate_fillet_radius"
        ],
        y_axis_motor_holder_side_wall_thickness=DEFAULTS[
            "y_axis_motor_holder_side_wall_thickness"
        ],
        y_axis_motor_holder_side_wall_height=DEFAULTS[
            "y_axis_motor_holder_side_wall_height"
        ],
        y_axis_motor_holder_side_wall_depth=DEFAULTS[
            "y_axis_motor_holder_side_wall_depth"
        ],
        y_axis_drive_mount_screw_inset=DEFAULTS["y_axis_drive_mount_screw_inset"],
        y_axis_drive_mount_screw_size=DEFAULTS["y_axis_drive_mount_screw_size"],
        y_axis_drive_mount_screw_length=DEFAULTS["y_axis_drive_mount_screw_length"],
        y_axis_drive_motor_plate_width=DEFAULTS["y_axis_drive_motor_plate_width"],
        y_axis_drive_motor_plate_depth=DEFAULTS["y_axis_drive_motor_plate_depth"],
        y_axis_drive_idler_plate_width=DEFAULTS["y_axis_drive_idler_plate_width"],
        y_axis_drive_motor_pulley_teeth=DEFAULTS["y_axis_drive_motor_pulley_teeth"],
        y_axis_drive_idler_teeth=DEFAULTS["y_axis_drive_idler_teeth"],
        y_axis_drive_belt_clear_span_extra=DEFAULTS[
            "y_axis_drive_belt_clear_span_extra"
        ],
        y_axis_drive_idler_housing_side_wall=DEFAULTS[
            "y_axis_drive_idler_housing_side_wall"
        ],
        y_axis_drive_idler_housing_front_wall=DEFAULTS[
            "y_axis_drive_idler_housing_front_wall"
        ],
        y_axis_drive_idler_housing_top_wall=DEFAULTS[
            "y_axis_drive_idler_housing_top_wall"
        ],
        y_axis_drive_idler_housing_top_above_frame_profile=DEFAULTS[
            "y_axis_drive_idler_housing_top_above_frame_profile"
        ],
        y_axis_drive_idler_cage_top_clearance=DEFAULTS[
            "y_axis_drive_idler_cage_top_clearance"
        ],
        y_axis_drive_idler_cage_front_clearance=DEFAULTS[
            "y_axis_drive_idler_cage_front_clearance"
        ],
        y_axis_drive_idler_cage_height=DEFAULTS["y_axis_drive_idler_cage_height"],
        y_axis_drive_tensioner_screw_holder_thickness=DEFAULTS[
            "y_axis_drive_tensioner_screw_holder_thickness"
        ],
        y_axis_drive_tensioner_screw_holder_depth=DEFAULTS[
            "y_axis_drive_tensioner_screw_holder_depth"
        ],
        y_axis_drive_tensioner_screw_holder_width=DEFAULTS[
            "y_axis_drive_tensioner_screw_holder_width"
        ],
        y_axis_drive_idler_cage_wall=DEFAULTS["y_axis_drive_idler_cage_wall"],
        y_axis_drive_idler_cage_overlength=DEFAULTS[
            "y_axis_drive_idler_cage_overlength"
        ],
        y_axis_drive_idler_clearance=DEFAULTS["y_axis_drive_idler_clearance"],
        y_axis_drive_idler_cage_back_wall=DEFAULTS["y_axis_drive_idler_cage_back_wall"],
        y_axis_drive_idler_tensioner_screw_length=DEFAULTS[
            "y_axis_drive_idler_tensioner_screw_length"
        ],
        y_axis_drive_idler_tensioner_screw_nut_wall=DEFAULTS[
            "y_axis_drive_idler_tensioner_screw_nut_wall"
        ],
        y_axis_drive_idler_tensioner_guide_clearance=DEFAULTS[
            "y_axis_drive_idler_tensioner_guide_clearance"
        ],
        y_axis_drive_idler_axle_screw_length=DEFAULTS[
            "y_axis_drive_idler_axle_screw_length"
        ],
        y_axis_drive_tensioner_screw_size=DEFAULTS["y_axis_drive_tensioner_screw_size"],
        y_axis_drive_use_toothed_belt_visuals=DEFAULTS[
            "y_axis_drive_use_toothed_belt_visuals"
        ],
        y_axis_drive_tensioner_screw_z_offset=DEFAULTS[
            "y_axis_drive_tensioner_screw_z_offset"
        ],
        endcap_tensioner_screw_size=DEFAULTS["endcap_tensioner_screw_size"],
        endcap_belt_clearance=DEFAULTS["endcap_belt_clearance"],
        big_thing=500,
    )


def _build_motor_mount():
    cfg = _drive_config()
    frame_back_profile = create_box(380, 40, 40, origin=(20, 304.85, -20))
    belt_reference = create_box(
        gt2_thickness,
        500,
        gt2_width,
        origin=(209.91, -190, 11),
    )
    motor_bracket = create_y_axis_nema23_motor_bracket_assembly(
        **assembly_kwargs(create_y_axis_nema23_motor_bracket_assembly)
    )
    return (
        _create_y_axis_motor_mount(
            frame_back_profile,
            belt_reference,
            motor_bracket,
            cfg,
        ),
        belt_reference,
        cfg,
    )


def test_y_axis_motor_pulley_top_is_flush_with_axle_top():
    motor_mount, _, _ = _build_motor_mount()

    pulley = motor_mount.get_non_production_part_by_name("motor_pulley")
    axle = motor_mount.get_non_production_part_by_name("motor_axle")

    assert get_bounding_box(pulley)[1][2] == pytest.approx(get_bounding_box(axle)[1][2])


def test_y_axis_motor_pulley_running_surface_matches_belt_height():
    motor_mount, belt_reference, cfg = _build_motor_mount()

    pulley = motor_mount.get_non_production_part_by_name("motor_pulley")
    running_surface = _create_gt2_motor_pulley_running_surface_reference(
        cfg.y_axis_drive_motor_pulley_teeth
    )
    running_surface = _align_gt2_motor_pulley_running_surface_to_pulley(
        running_surface,
        pulley,
    )

    belt_bbox = get_bounding_box(belt_reference)
    running_surface_bbox = get_bounding_box(running_surface)

    assert running_surface_bbox[0][2] == pytest.approx(belt_bbox[0][2])
    assert running_surface_bbox[1][2] == pytest.approx(belt_bbox[1][2])


def test_y_axis_drive_visualizes_printer_foot_mount_screws():
    resource = yaml.safe_load(
        (ASSEMBLIES_DIR / "y_axis_drive_assembly.yaml").read_text()
    )
    visualization_parts = resource["Builder"]["Visualization"]["parts"]

    for corner in ("left_front", "left_back", "right_front", "right_back"):
        assert {
            "source": "dependencies",
            "assembly": f"printer_foot_{corner}_assembly",
            "artifact": "non_production_parts",
            "names": ["screw"],
            "name": f"printer_foot_screw_{corner}",
        } in visualization_parts
