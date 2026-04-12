"""Standalone x-axis endstop holder with profile groove mount."""

from mege_ender_3v3ke_idex.designs.assemblies.creality_endstop_holder_assembly import (
    create_creality_endstop_holder_assembly,
)
from shellforgepy.simple import *


def _create_groove_holder(
    *,
    screw_size,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    big_thing,
):
    mount_screw_cutter = create_cylinder(
        MScrew.from_size(screw_size).clearance_hole_normal / 2,
        big_thing,
    )

    groove_holder = create_pyramid_stump(
        endstop_holder_mount_plate_width,
        endstop_holder_mount_plate_width,
        endstop_holder_groove_holder_bottom_width,
        endstop_holder_groove_holder_top_width,
        endstop_holder_groove_holder_height,
    )

    groove_holder_hole_cutter = create_cylinder(
        MScrew.from_size(screw_size).core_hole / 2 - 0.1,
        big_thing,
    )
    groove_holder_hole_cutter = align(
        groove_holder_hole_cutter,
        groove_holder,
        Alignment.CENTER,
    )
    groove_holder = groove_holder.cut(groove_holder_hole_cutter)

    mount_screw_cutter = align(
        mount_screw_cutter,
        groove_holder,
        Alignment.CENTER,
    )

    groove_holder_larger_hole_cutter = align(
        mount_screw_cutter,
        groove_holder,
        Alignment.STACK_TOP,
        stack_gap=endstop_holder_groove_holder_height / 3,
    )
    groove_holder = groove_holder.cut(groove_holder_larger_hole_cutter)

    slit_cutter = create_box(
        endstop_holder_groove_holder_slit,
        big_thing,
        big_thing,
    )
    slit_cutter = align(slit_cutter, groove_holder, Alignment.CENTER)
    groove_holder = groove_holder.cut(slit_cutter)

    retval = LeaderFollowersCuttersPart(leader=groove_holder)
    retval.add_named_cutter(mount_screw_cutter, "mount_screw_cutter")
    return retval


def create_x_axis_endstop_assembly(
    *,
    x_axis_carriage_stopper_depth,
    x_axis_carriage_stopper_thickness,
    x_axis_carriage_stopper_fillet_radius,
    x_axis_endstop_mount_base_width,
    x_axis_endstop_mount_base_inward_extension,
    endstop_holder_y_offset,
    endstop_holder_mount_screw_size,
    endstop_holder_mount_screw_length,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    BIG_THING,
):
    """Create one x-axis endstop holder with an integrated profile groove clamp."""

    holder = create_creality_endstop_holder_assembly()
    holder = rotate(180, axis=(0, 0, 1), center=get_bounding_box_center(holder.leader))(
        holder
    )
    holder_size = get_bounding_box_size(holder.leader)

    mount_pedestal_width = x_axis_endstop_mount_base_width
    mount_pedestal_depth = max(
        x_axis_carriage_stopper_depth,
        holder_size[1] + x_axis_endstop_mount_base_inward_extension,
    )

    mount_pedestal = create_filleted_box(
        mount_pedestal_width,
        mount_pedestal_depth,
        x_axis_carriage_stopper_thickness,
        fillet_radius=x_axis_carriage_stopper_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    groove_holder = _create_groove_holder(
        screw_size=endstop_holder_mount_screw_size,
        endstop_holder_mount_plate_width=endstop_holder_mount_plate_width,
        endstop_holder_groove_holder_bottom_width=endstop_holder_groove_holder_bottom_width,
        endstop_holder_groove_holder_top_width=endstop_holder_groove_holder_top_width,
        endstop_holder_groove_holder_height=endstop_holder_groove_holder_height,
        endstop_holder_groove_holder_slit=endstop_holder_groove_holder_slit,
        big_thing=BIG_THING,
    )
    groove_holder = align(groove_holder, mount_pedestal, Alignment.CENTER)
    groove_holder = align(groove_holder, mount_pedestal, Alignment.STACK_BOTTOM)
    groove_holder = align(groove_holder, mount_pedestal, Alignment.FRONT)

    mount_pedestal = groove_holder.use_as_cutter_on(mount_pedestal)

    holder = align(holder, mount_pedestal, Alignment.CENTER, axes=[0])
    holder = align(holder, mount_pedestal, Alignment.BACK)
    holder = align(holder, mount_pedestal, Alignment.STACK_TOP)
    holder = translate(
        0,
        endstop_holder_y_offset,
        0,
    )(holder)

    mount_screw = create_cylinder_screw(
        endstop_holder_mount_screw_size,
        endstop_holder_mount_screw_length,
    )
    mount_screw = align(mount_screw, groove_holder.leader, Alignment.CENTER, axes=[0, 1])
    mount_screw = align(mount_screw, mount_pedestal, Alignment.TOP)
    mount_screw = translate(
        0,
        0,
        MScrew.from_size(endstop_holder_mount_screw_size).cylinder_head_height,
    )(mount_screw)

    leader = groove_holder.leader.fuse(mount_pedestal).fuse(holder.leader)
    retval = LeaderFollowersCuttersPart(leader=leader)
    retval.add_named_non_production_part(mount_screw, "mount_screw")
    retval.add_named_non_production_part(
        holder.get_non_production_part_by_name("board"),
        "board",
    )
    retval.add_named_cutter(
        groove_holder.get_cutter_part_by_name("mount_screw_cutter"),
        "mount_screw_cutter",
    )
    return retval
