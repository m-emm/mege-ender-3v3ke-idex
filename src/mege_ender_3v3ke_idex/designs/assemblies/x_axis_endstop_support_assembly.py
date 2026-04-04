"""Declarative x-axis endstop support assembly."""

from mege_ender_3v3ke_idex.designs.endstop_holder import create_endstop_holder
from shellforgepy.simple import *


def _named_only(part):
    cleaned = LeaderFollowersCuttersPart(
        leader=part.leader,
        additional_data=dict(part.additional_data),
    )
    for name, follower in part.get_named_follower_items():
        cleaned.add_named_follower(follower, name)
    for name, cutter in part.get_named_cutter_items():
        cleaned.add_named_cutter(cutter, name)
    for name, non_production_part in part.get_named_non_production_part_items():
        cleaned.add_named_non_production_part(non_production_part, name)
    return cleaned


def _get_leader_part(part_like):
    return part_like.leader if hasattr(part_like, "leader") else part_like


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


def _create_carriage_end_rail_stopper(
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
    big_thing,
):
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


def create_x_axis_endstop_support_assembly(
    *,
    x_axis_lower_profile,
    x_axis_rail,
    carriage_end_rail_stopper_length,
    carriage_end_rail_stopper_thickness,
    carriage_end_rail_stopper_depth,
    carriage_end_rail_stopper_fillet_radius,
    carriage_end_rail_connector_thickness,
    endstop_holder_mount_screw_size,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    endstop_holder_stack_gap,
    endstop_holder_y_offset,
    context=None,
):
    """Create the lower-lane x-axis endstop support pair."""

    big_thing = (context or {}).get("BIG_THING", 500)
    lower_axis_profile = _get_leader_part(x_axis_lower_profile)
    rail_with_carriages = x_axis_rail

    retval = LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))
    supports_fused = PartCollector()

    for endcap_side in (Alignment.LEFT, Alignment.RIGHT):
        rail_end_stopper = _create_carriage_end_rail_stopper(
            carriage_end_rail_stopper_length=carriage_end_rail_stopper_length,
            carriage_end_rail_stopper_depth=carriage_end_rail_stopper_depth,
            carriage_end_rail_stopper_thickness=carriage_end_rail_stopper_thickness,
            carriage_end_rail_stopper_fillet_radius=carriage_end_rail_stopper_fillet_radius,
            endstop_holder_mount_screw_size=endstop_holder_mount_screw_size,
            endstop_holder_mount_plate_width=endstop_holder_mount_plate_width,
            endstop_holder_groove_holder_bottom_width=endstop_holder_groove_holder_bottom_width,
            endstop_holder_groove_holder_top_width=endstop_holder_groove_holder_top_width,
            endstop_holder_groove_holder_height=endstop_holder_groove_holder_height,
            endstop_holder_groove_holder_slit=endstop_holder_groove_holder_slit,
            big_thing=big_thing,
        )
        rail_end_stopper = align(
            rail_end_stopper,
            rail_with_carriages,
            Alignment.CENTER,
        )
        rail_end_stopper = align(
            rail_end_stopper,
            rail_with_carriages,
            Alignment.BOTTOM,
        )
        rail_end_stopper = align(
            rail_end_stopper,
            rail_with_carriages,
            endcap_side.stack_alignment,
        )

        rail_end_stopper_fused = rail_end_stopper.leader.fuse(
            rail_end_stopper.get_named_follower("groove_holder")
        )

        endstop_holder = create_endstop_holder()
        endstop_holder = rotate(-endcap_side.sign * 90)(endstop_holder)
        endstop_holder = align(
            endstop_holder,
            lower_axis_profile,
            Alignment.CENTER,
        )
        endstop_holder = align(
            endstop_holder,
            rail_end_stopper_fused,
            Alignment.STACK_TOP,
        )
        endstop_holder = translate(0, endstop_holder_y_offset, 0)(endstop_holder)

        endstop_holder_board_aligner = align_translation(
            endstop_holder.get_non_production_part_by_name("board"),
            rail_with_carriages,
            endcap_side.stack_alignment,
            stack_gap=endstop_holder_stack_gap,
        )
        endstop_holder = endstop_holder_board_aligner(endstop_holder)
        retval.add_named_non_production_part(
            endstop_holder.get_non_production_part_by_name("board"),
            f"endstop_board_{endcap_side.name.lower()}",
        )

        fused = endstop_holder.leader.fuse(rail_end_stopper_fused)
        fused_size = get_bounding_box_size(fused)
        stopper_size = get_bounding_box_size(rail_end_stopper_fused)
        endstop_holder_size = get_bounding_box_size(endstop_holder)

        connector = create_box(
            fused_size[0] - endstop_holder_size[0],
            stopper_size[1],
            carriage_end_rail_connector_thickness,
        )
        connector = align(connector, rail_end_stopper_fused, Alignment.CENTER)
        connector = align(
            connector,
            rail_end_stopper_fused,
            endcap_side.opposite,
        )
        connector = align(
            connector,
            rail_end_stopper_fused,
            Alignment.STACK_TOP,
        )
        connector = rail_end_stopper.use_as_cutter_on(connector)

        rail_end_stopper_fused = rail_end_stopper_fused.fuse(connector)
        rail_end_stopper_fused = rail_end_stopper_fused.fuse(endstop_holder.leader)
        retval.add_named_follower(
            rail_end_stopper_fused,
            f"rail_end_stopper_{endcap_side.name.lower()}",
        )
        supports_fused = supports_fused.fuse(rail_end_stopper_fused)

    retval.leader = supports_fused
    return _named_only(retval)
