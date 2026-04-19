"""Standalone x-axis belt carriage assembly."""

import logging

from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def create_x_axis_belt_carriage_assembly(
    *,
    carriage,
    axis_profile,
    sprite_extruder,
    tool_head_mount_base_plate_height,
    tool_head_mount_belt_clamp_base_thickness,
    tool_head_mount_belt_clamp_length,
    tool_head_mount_belt_clamp_thickness,
    tool_head_mount_belt_clamp_y_offset,
    tool_head_mount_belt_deflector_belt_clearance,
    tool_head_mount_belt_deflector_cage_thickness,
    tool_head_mount_belt_deflector_into_profile_distance,
    tool_head_mount_belt_deflector_thickness,
    tool_head_mount_belt_path_cutter_clearance,
    tool_head_mount_carriage_mount_plate_fillet_radius,
    tool_head_mount_carriage_mount_plate_thickness,
    tool_head_mount_carriage_mount_plate_width,
    tool_head_mount_clamp_base_cutter_clearance,
    tool_head_mount_plate_carriage_clearance,
    tool_head_mount_side_plate_depth,
    tool_head_mount_side_plate_height,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_y_extension,
    x_axis_belt_carriage_belt_clamp_clearance,
    x_axis_belt_carriage_right_gap,
    x_axis_belt_carriage_bridge_profile_wall,
    x_axis_belt_carriage_bridge_depth,
    x_axis_belt_carriage_bridge_thickness,
    x_axis_belt_carriage_bridge_web_height,
    x_axis_belt_carriage_mount_eye_fillet_radius,
    x_axis_belt_carriage_mount_eye_hole_diameter,
    x_axis_belt_carriage_mount_eye_length,
    x_axis_belt_carriage_mount_eye_thickness,
    x_axis_belt_carriage_mount_eye_width,
    drive_position,
    BIG_THING,
):
    """Create a standalone x-axis belt carriage assembly."""

    normalized_drive_position = str(drive_position).strip().lower()
    if normalized_drive_position == "bottom":
        drive_alignment = Alignment.BOTTOM
    elif normalized_drive_position == "top":
        drive_alignment = Alignment.TOP
    else:
        raise ValueError(f"Unsupported drive_position '{drive_position}'")

    sprite_extruder_all_fused = sprite_extruder.leaders_followers_fused().fuse(
        sprite_extruder.get_non_production_parts_fused()
    )

    assembly = None
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        clamp_lfc = create_gt_belt_clamp(
            base_thicknness=tool_head_mount_belt_clamp_base_thickness,
            clamp_thickness=tool_head_mount_belt_clamp_thickness,
            clamp_length=tool_head_mount_belt_clamp_length,
            screw_size="M3",
            screw_hole_border=1.9,
            teeth_clearance=0.1,
            single_screw=True,
            extra_scew_hole_clearance=0.2,
            use_threaded_inset=True,
        )
        clamp_lfc = rotate(90, axis=(1, 0, 0))(clamp_lfc)
        clamp_lfc = rotate(90)(clamp_lfc)

        if lr == Alignment.RIGHT:
            clamp_lfc = rotate(180)(clamp_lfc)

        clamp_lfc = align(clamp_lfc, sprite_extruder, Alignment.CENTER)
        clamp_lfc = align(
            clamp_lfc,
            axis_profile,
            Alignment.STACK_FRONT,
            stack_gap=tool_head_mount_belt_clamp_y_offset,
        )
        clamp_lfc = clamp_lfc.aligned_from_follower(
            "belt_path_cutter",
            sprite_extruder_all_fused,
            lr.stack_alignment,
            stack_gap=tool_head_mount_belt_clamp_base_thickness * 1.5,
        )

        clamp_lfc = align(clamp_lfc, axis_profile, Alignment.CENTER, axes=[2])

        current_belt_path_cutter = clamp_lfc.get_named_follower("belt_path_cutter")
        current_belt_path_cutter_size = get_bounding_box_size(current_belt_path_cutter)

        belt_deflector_clearance = 0.5

        belt_deflector = create_box(
            tool_head_mount_belt_deflector_thickness,
            BIG_THING,
            current_belt_path_cutter_size[2] - 2 * belt_deflector_clearance,
        )
        belt_deflector = align(
            belt_deflector,
            current_belt_path_cutter,
            Alignment.CENTER,
        )

        clamp_part = clamp_lfc.get_named_follower("clamp")
        base_part = clamp_lfc.leader

        camp_and_base_fused = clamp_part.fuse(base_part)

        belt_deflector = fit_part_between(
            belt_deflector,
            cut_normal=(0, 1, 0),
            limiting_start_part=axis_profile,
            limiting_end_part=camp_and_base_fused,
            start_gap=-tool_head_mount_belt_deflector_into_profile_distance,
            end_gap=x_axis_belt_carriage_belt_clamp_clearance,
        )

        belt_deflector = align(
            belt_deflector,
            clamp_lfc.get_named_follower("belt_path_cutter"),
            lr.stack_alignment,
        )

        base_and_clamp_fused = base_part.fuse(clamp_part)
        all_clamp_size = get_bounding_box_size(base_and_clamp_fused)

        bdc_x_size = all_clamp_size[0]
        bdc_y_size = tool_head_mount_belt_deflector_cage_thickness
        bdc_z_size = all_clamp_size[2]

        belt_deflector_cage = create_box(bdc_x_size, bdc_y_size, bdc_z_size)
        belt_deflector_cage = align(
            belt_deflector_cage,
            base_and_clamp_fused,
            Alignment.CENTER,
        )
        belt_deflector_cage = align(
            belt_deflector_cage, belt_deflector, Alignment.FRONT
        )
        belt_deflector_cage = belt_deflector_cage.cut(current_belt_path_cutter)

        belt_deflector_connector = create_box(
            tool_head_mount_belt_clamp_thickness,
            x_axis_belt_carriage_belt_clamp_clearance,
            all_clamp_size[2],
        )

        belt_deflector_connector = align(
            belt_deflector_connector,
            clamp_part,
            Alignment.CENTER,
        )
        belt_deflector_connector = align(
            belt_deflector_connector, clamp_part, lr.opposite
        )
        belt_deflector_connector = align(
            belt_deflector_connector,
            clamp_part,
            Alignment.STACK_BACK,
        )

        clamp_part = clamp_part.fuse(belt_deflector)
        clamp_part = clamp_part.fuse(belt_deflector_cage)
        clamp_part = clamp_part.fuse(belt_deflector_connector)

        clamp_lfc_new = LeaderFollowersCuttersPart(clamp_part)

        clamp_lfc_new.add_named_follower(clamp_lfc.leader, "base")
        for name, npp in clamp_lfc.get_named_non_production_part_items():
            clamp_lfc_new.add_named_non_production_part(npp, name)

        clamp_lfc_new = clamp_lfc_new.prefixed_copy(f"belt_clamp_{lr.name.lower()}")

        if assembly is None:
            assembly = clamp_lfc_new
        else:
            assembly = assembly.fuse(clamp_lfc_new)

    return assembly
