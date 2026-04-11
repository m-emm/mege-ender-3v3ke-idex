"""Declarative x-axis endstop support side assembly."""

from shellforgepy.simple import *


def _get_leader_part(part_like):
    return part_like.leader if hasattr(part_like, "leader") else part_like


def _resolve_side(side):
    normalized = str(side).strip().lower()
    if normalized == "left":
        return Alignment.LEFT
    if normalized == "right":
        return Alignment.RIGHT
    raise ValueError(f"Unsupported x-axis endstop side: {side}")


def create_x_axis_endstop_side_assembly(
    *,
    side,
    rail_stopper,
    endstop_holder,
    carriage_end_rail_connector_thickness,
):
    """Create one side of the x-axis endstop support."""

    side_alignment = _resolve_side(side)
    rail_stopper_part = rail_stopper
    holder_rotation_center = get_bounding_box_center(_get_leader_part(endstop_holder))
    holder_part = rotate(180, center=holder_rotation_center)(endstop_holder)

    rail_stopper_fused = _get_leader_part(rail_stopper_part).fuse(
        rail_stopper_part.get_named_follower("groove_holder")
    )
    holder_part = align(holder_part, rail_stopper_fused, Alignment.BACK)

    fused = holder_part.leader.fuse(rail_stopper_fused)
    fused_size = get_bounding_box_size(fused)
    stopper_size = get_bounding_box_size(rail_stopper_fused)
    holder_size = get_bounding_box_size(holder_part)

    connector = create_box(
        fused_size[0] - holder_size[0],
        stopper_size[1],
        carriage_end_rail_connector_thickness,
    )
    connector = align(connector, rail_stopper_fused, Alignment.CENTER)
    connector = align(
        connector,
        rail_stopper_fused,
        side_alignment.opposite,
    )
    connector = align(
        connector,
        rail_stopper_fused,
        Alignment.STACK_TOP,
    )
    connector = rail_stopper_part.use_as_cutter_on(connector)

    leader = rail_stopper_fused.fuse(connector).fuse(holder_part.leader)
    retval = LeaderFollowersCuttersPart(leader=leader)
    retval.add_named_non_production_part(
        holder_part.get_non_production_part_by_name("board"),
        "endstop_board",
    )
    return retval
