"""Join the X-axis MCU holder with a replacement part fan lid."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _copy_holder_without_old_lid_and_fan(x_axis_mcu_holder):
    joined_holder = LeaderFollowersCuttersPart(
        x_axis_mcu_holder.leader.copy(),
        additional_data=x_axis_mcu_holder.additional_data.copy(),
    )

    for name, follower in x_axis_mcu_holder.get_named_follower_items():
        if name == "top_lid":
            continue
        joined_holder.add_named_follower(follower.copy(), name)

    for name, cutter in x_axis_mcu_holder.get_named_cutter_items():
        joined_holder.add_named_cutter(cutter.copy(), name)

    for name, non_production_part in (
        x_axis_mcu_holder.get_named_non_production_part_items()
    ):
        if name == "fan":
            continue
        joined_holder.add_named_non_production_part(non_production_part.copy(), name)

    return joined_holder


def _create_replacement_top_lid(
    *,
    side_walls,
    replacement_lid_thickness,
    replacement_lid_clearance,
):
    side_walls_size = get_bounding_box_size(side_walls)
    top_lid = create_box(
        side_walls_size[0],
        side_walls_size[1],
        replacement_lid_thickness,
    )
    top_lid = align(top_lid, side_walls, Alignment.CENTER, axes=[0, 1])
    top_lid = align(
        top_lid,
        side_walls,
        Alignment.STACK_TOP,
        stack_gap=replacement_lid_clearance,
    )
    return top_lid


def _get_named_follower_or_non_production_part(part, name):
    if name in part.follower_indices_by_name:
        return part.get_named_follower(name)
    if name in part.non_production_indices_by_name:
        return part.get_named_non_production_part(name)
    raise KeyError(
        f"Part '{name}' not found in followers or non-production parts. "
        f"Available followers: {sorted(part.follower_indices_by_name)}. "
        f"Available non-production parts: {sorted(part.non_production_indices_by_name)}."
    )


def _position_part_fan_on_lid(
    *,
    part_fan,
    top_lid,
    pico_board,
    fan_rotation_angle,
    fan_lid_y_offset,
    fan_lid_stack_gap,
):
    positioned_fan = part_fan.copy()
    if fan_rotation_angle:
        positioned_fan = rotate(
            fan_rotation_angle,
            axis=(0, 0, 1),
            center=get_bounding_box_center(positioned_fan),
        )(positioned_fan)

    positioned_fan = positioned_fan.aligned_from_follower(
        "mount_plate",
        top_lid,
        Alignment.CENTER,
        axes=[1],
    )
    positioned_fan = positioned_fan.aligned_from_follower(
        "mount_plate",
        pico_board,
        Alignment.CENTER,
        axes=[0],
    )
    positioned_fan = positioned_fan.aligned_from_follower(
        "mount_plate",
        top_lid,
        Alignment.STACK_TOP,
        stack_gap=fan_lid_stack_gap,
    )

    if fan_lid_y_offset:
        positioned_fan = translate(0, fan_lid_y_offset, 0)(positioned_fan)

    return positioned_fan


def join_x_axis_mcu_holder_with_fan(
    *,
    x_axis_mcu_holder,
    part_fan,
    fan_rotation_angle=0.0,
    fan_lid_y_offset=0.0,
    fan_lid_stack_gap=0.0,
    replacement_lid_thickness=1.2,
    replacement_lid_clearance=0.4,
):
    """Return the X-axis MCU holder with a rough replacement part-fan lid."""

    _logger.info("Joining X-axis MCU holder with replacement part fan")

    side_walls = x_axis_mcu_holder.get_named_follower("side_walls")
    pico_board = _get_named_follower_or_non_production_part(
        x_axis_mcu_holder,
        "pico_board_board",
    )

    joined_holder = _copy_holder_without_old_lid_and_fan(x_axis_mcu_holder)

    replacement_top_lid = _create_replacement_top_lid(
        side_walls=side_walls,
        replacement_lid_thickness=replacement_lid_thickness,
        replacement_lid_clearance=replacement_lid_clearance,
    )
    positioned_fan = _position_part_fan_on_lid(
        part_fan=part_fan,
        top_lid=replacement_top_lid,
        pico_board=pico_board,
        fan_rotation_angle=fan_rotation_angle,
        fan_lid_y_offset=fan_lid_y_offset,
        fan_lid_stack_gap=fan_lid_stack_gap,
    )

    replacement_top_lid = positioned_fan.use_as_cutter_on(replacement_top_lid)
    replacement_top_lid = replacement_top_lid.fuse(
        positioned_fan.get_named_follower("mount_plate")
    )
    replacement_top_lid = replacement_top_lid.fuse(
        positioned_fan.get_named_follower("outlet")
    )

    joined_holder.add_named_follower(replacement_top_lid, "top_lid")
    joined_holder.add_named_non_production_part(
        positioned_fan.leader.copy(),
        "part_fan",
    )

    joined_holder.add_consumed_part_ref(
        x_axis_mcu_holder.part_ref_for_named_follower("top_lid")
    )
    joined_holder.add_consumed_part_ref(
        part_fan.part_ref_for_named_follower("mount_plate")
    )
    joined_holder.add_consumed_part_ref(
        part_fan.part_ref_for_named_follower("outlet")
    )

    joined_part_fan = LeaderFollowersCuttersPart(positioned_fan.leader.copy())

    return {
        "x_axis_mcu_holder": joined_holder,
        "part_fan": joined_part_fan,
    }
