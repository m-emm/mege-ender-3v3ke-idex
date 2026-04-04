"""Declarative x-axis endstop rail stopper assembly."""

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
        big_thing,
        endstop_holder_groove_holder_slit,
        big_thing,
    )
    slit_cutter = align(slit_cutter, groove_holder, Alignment.CENTER)
    groove_holder = groove_holder.cut(slit_cutter)

    retval = LeaderFollowersCuttersPart(leader=groove_holder)
    retval.add_named_cutter(mount_screw_cutter, "mount_screw_cutter")
    return retval


def create_x_axis_endstop_rail_stopper_assembly(
    *,
    carriage_end_rail_stopper_length,
    carriage_end_rail_stopper_depth,
    carriage_end_rail_stopper_thickness,
    carriage_end_rail_stopper_fillet_radius,
    endstop_holder_mount_screw_size,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    context=None,
):
    """Create one x-axis rail stopper with groove holder."""

    big_thing = (context or {}).get("BIG_THING", 500)

    stopper = create_filleted_box(
        carriage_end_rail_stopper_length,
        carriage_end_rail_stopper_depth,
        carriage_end_rail_stopper_thickness,
        fillet_radius=carriage_end_rail_stopper_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    groove_holder = _create_groove_holder(
        screw_size=endstop_holder_mount_screw_size,
        endstop_holder_mount_plate_width=endstop_holder_mount_plate_width,
        endstop_holder_groove_holder_bottom_width=endstop_holder_groove_holder_bottom_width,
        endstop_holder_groove_holder_top_width=endstop_holder_groove_holder_top_width,
        endstop_holder_groove_holder_height=endstop_holder_groove_holder_height,
        endstop_holder_groove_holder_slit=endstop_holder_groove_holder_slit,
        big_thing=big_thing,
    )
    groove_holder = align(groove_holder, stopper, Alignment.CENTER)
    groove_holder = align(groove_holder, stopper, Alignment.STACK_BOTTOM)

    stopper = groove_holder.use_as_cutter_on(stopper)

    retval = LeaderFollowersCuttersPart(stopper)
    retval.add_named_follower(groove_holder.leader, "groove_holder")
    retval.add_named_cutter(
        groove_holder.get_cutter_part_by_name("mount_screw_cutter"),
        "mount_screw_cutter",
    )
    return retval
