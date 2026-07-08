import yaml
import pytest

from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.y_axis_drive_assembly import (
    _DriveConfig,
    _align_gt2_motor_pulley_running_surface_to_pulley,
    _create_y_axis_drive_belt_sections,
    _create_gt2_motor_pulley_running_surface_reference,
    _create_y_axis_idler_mount,
    _create_y_axis_motor_mount,
)
from mege_ender_3v3ke_idex.designs.assemblies.y_axis_nema23_motor_bracket_assembly import (
    create_y_axis_nema23_motor_bracket_assembly,
)
from mege_ender_3v3ke_idex.designs.gt2belt import gt2_thickness, gt2_width
from shellforgepy.simple import create_box, get_bounding_box, get_volume


def _drive_config(**overrides):
    values = {
        "y_axis_motor_bracket_lowering": DEFAULTS["y_axis_motor_bracket_lowering"],
    }
    values.update(overrides)

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
        y_axis_motor_bracket_lowering=values["y_axis_motor_bracket_lowering"],
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


def _build_motor_mount(cfg=None):
    if cfg is None:
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


def _build_idler_mount(cfg=None):
    if cfg is None:
        cfg = _drive_config()

    frame_front_profile = create_box(380, 40, 40, origin=(20, -344.85, -20))
    belt_reference = create_box(
        gt2_thickness,
        500,
        gt2_width,
        origin=(209.91, -310, 11),
    )
    return (
        _create_y_axis_idler_mount(
            frame_front_profile,
            belt_reference,
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


def _assert_bbox_equal(left, right):
    left_bbox = get_bounding_box(left)
    right_bbox = get_bounding_box(right)

    for point_index in [0, 1]:
        for axis in [0, 1, 2]:
            assert left_bbox[point_index][axis] == pytest.approx(
                right_bbox[point_index][axis]
            )


def _assert_bbox_shifted_z(shifted, original, z_delta):
    shifted_bbox = get_bounding_box(shifted)
    original_bbox = get_bounding_box(original)

    for axis in [0, 1]:
        assert shifted_bbox[0][axis] == pytest.approx(original_bbox[0][axis])
        assert shifted_bbox[1][axis] == pytest.approx(original_bbox[1][axis])

    assert shifted_bbox[0][2] == pytest.approx(original_bbox[0][2] + z_delta)
    assert shifted_bbox[1][2] == pytest.approx(original_bbox[1][2] + z_delta)


def test_y_axis_motor_mount_plate_geometry_is_unchanged_by_bracket_lowering():
    lowered_mount, _, _ = _build_motor_mount(
        _drive_config(y_axis_motor_bracket_lowering=6.0)
    )
    original_mount, _, _ = _build_motor_mount(
        _drive_config(y_axis_motor_bracket_lowering=0.0)
    )

    _assert_bbox_equal(lowered_mount.leader, original_mount.leader)
    assert get_volume(lowered_mount.leader) == pytest.approx(
        get_volume(original_mount.leader)
    )


def test_y_axis_motor_bracket_visuals_are_lowered_on_unchanged_mount_plate():
    lowering = 6.0
    lowered_mount, _, _ = _build_motor_mount(
        _drive_config(y_axis_motor_bracket_lowering=lowering)
    )
    original_mount, _, _ = _build_motor_mount(
        _drive_config(y_axis_motor_bracket_lowering=0.0)
    )

    for name in [
        "motor_bracket",
        "motor_body",
        "motor_bracket_motor_mount_screw_left_front",
        "motor_bracket_motor_mount_screw_left_back",
        "motor_bracket_motor_mount_screw_right_front",
        "motor_bracket_motor_mount_screw_right_back",
    ]:
        _assert_bbox_shifted_z(
            lowered_mount.get_non_production_part_by_name(name),
            original_mount.get_non_production_part_by_name(name),
            -lowering,
        )

    for name in [
        "motor_pulley",
        "motor_bracket_frame_mount_screw_left",
        "motor_bracket_frame_mount_screw_right",
        "motor_profile_mount_screw_left",
        "motor_profile_mount_screw_right",
    ]:
        _assert_bbox_equal(
            lowered_mount.get_non_production_part_by_name(name),
            original_mount.get_non_production_part_by_name(name),
        )


def test_y_axis_motor_axle_extends_to_fixed_pulley_after_bracket_lowering():
    lowering = 6.0
    lowered_mount, _, _ = _build_motor_mount(
        _drive_config(y_axis_motor_bracket_lowering=lowering)
    )
    original_mount, _, _ = _build_motor_mount(
        _drive_config(y_axis_motor_bracket_lowering=0.0)
    )

    lowered_axle_bbox = get_bounding_box(
        lowered_mount.get_non_production_part_by_name("motor_axle")
    )
    original_axle_bbox = get_bounding_box(
        original_mount.get_non_production_part_by_name("motor_axle")
    )
    lowered_pulley_bbox = get_bounding_box(
        lowered_mount.get_non_production_part_by_name("motor_pulley")
    )

    assert lowered_axle_bbox[0][2] == pytest.approx(original_axle_bbox[0][2] - lowering)
    assert lowered_axle_bbox[1][2] == pytest.approx(original_axle_bbox[1][2])
    assert lowered_axle_bbox[1][2] == pytest.approx(lowered_pulley_bbox[1][2])


def test_y_axis_belt_sections_stay_at_undercarriage_belt_reference_height():
    cfg = _drive_config(y_axis_motor_bracket_lowering=6.0)
    motor_mount, back_belt_reference, _ = _build_motor_mount(cfg)
    idler_mount, _, _ = _build_idler_mount(cfg)

    belt_sections = _create_y_axis_drive_belt_sections(
        motor_mount,
        idler_mount,
        back_belt_reference,
        cfg,
    )
    reference_bbox = get_bounding_box(back_belt_reference)

    for _, belt_section in belt_sections:
        belt_bbox = get_bounding_box(belt_section)
        assert belt_bbox[0][2] == pytest.approx(reference_bbox[0][2])
        assert belt_bbox[1][2] == pytest.approx(reference_bbox[1][2])


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


def test_y_axis_visualizes_printer_feet_and_mount_screws():
    resource = yaml.safe_load((ASSEMBLIES_DIR / "y_axis_assembly.yaml").read_text())
    visualization_parts = resource["Builder"]["Visualization"]["parts"]

    for corner in ("left_front", "left_back", "right_front", "right_back"):
        assert {
            "source": "dependencies",
            "assembly": f"printer_foot_{corner}_assembly",
            "artifact": "leader",
            "name": f"printer_foot_{corner}",
        } in visualization_parts
        assert {
            "source": "dependencies",
            "assembly": f"printer_foot_{corner}_assembly",
            "artifact": "non_production_parts",
            "names": ["screw"],
            "name": f"printer_foot_screw_{corner}",
        } in visualization_parts
