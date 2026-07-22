"""Join the positioned Y-axis driver-board holder and TMC5160T Plus."""

import copy

from shellforgepy.simple import *


def join_y_axis_driver_board_holder_with_tmc5160t_plus(
    *,
    y_axis_driver_board_holder,
    bigtreetech_stepper_driver,
    board_holder_mount_screw_hole_inset,
    board_holder_mount_screw_size="M3",
):
    """Return the replaced holder without repositioning either injected input."""

    joined_holder = LeaderFollowersCuttersPart(
        y_axis_driver_board_holder.leader.copy(),
        additional_data=copy.deepcopy(y_axis_driver_board_holder.additional_data),
    )

    for name, follower in y_axis_driver_board_holder.get_named_follower_items():
        joined_holder.add_named_follower(follower.copy(), name)

    for name, cutter in y_axis_driver_board_holder.get_named_cutter_items():
        joined_holder.add_named_cutter(cutter.copy(), name)

    for (
        name,
        non_production_part,
    ) in y_axis_driver_board_holder.get_named_non_production_part_items():
        if name == "reference_tmc5160t_plus_driver":
            continue
        joined_holder.add_named_non_production_part(
            non_production_part.copy(),
            name,
        )

    for (
        name,
        index,
    ) in y_axis_driver_board_holder.direction_vector_indices_by_name.items():
        joined_holder.add_named_direction_vector(
            tuple(y_axis_driver_board_holder.direction_vectors[index]),
            name,
        )

    joined_holder.leader = bigtreetech_stepper_driver.use_as_cutter_on(
        joined_holder.leader
    )

    mount_screw_hole_diameter = MScrew.from_size(
        board_holder_mount_screw_size
    ).clearance_hole_normal
    mount_screw_holes = PartCollector()
    mount_screw_hole_centers = []
    drill_length = max(get_bounding_box_size(joined_holder.leader)) * 2
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
            mount_screw_drill = create_cylinder(
                mount_screw_hole_diameter / 2,
                drill_length,
            )
            mount_screw_drill = align(
                mount_screw_drill,
                joined_holder.leader,
                Alignment.CENTER,
                axes=[2],
            )
            mount_screw_drill = align(
                mount_screw_drill,
                joined_holder.leader,
                left_right_alignment.edge_alignment,
            )
            mount_screw_drill = align(
                mount_screw_drill,
                joined_holder.leader,
                front_back_alignment.edge_alignment,
            )
            mount_screw_drill = translate(
                -left_right_alignment.sign * board_holder_mount_screw_hole_inset,
                -front_back_alignment.sign * board_holder_mount_screw_hole_inset,
                0,
            )(mount_screw_drill)
            mount_screw_hole_centers.append(
                tuple(get_bounding_box_center(mount_screw_drill))
            )
            mount_screw_holes = mount_screw_holes.fuse(mount_screw_drill)

    joined_holder.leader = joined_holder.leader.cut(mount_screw_holes)
    joined_holder.add_named_cutter(mount_screw_holes, "mount_screw_holes")
    joined_holder.additional_data["mount_screw_hole_centers"] = mount_screw_hole_centers
    joined_holder.additional_data["mount_screw_hole_diameter"] = (
        mount_screw_hole_diameter
    )

    joined_holder.add_consumed_part_ref(
        y_axis_driver_board_holder.part_ref_for_leader()
    )
    for name in y_axis_driver_board_holder.follower_indices_by_name:
        joined_holder.add_consumed_part_ref(
            y_axis_driver_board_holder.part_ref_for_named_follower(name)
        )
    for name in y_axis_driver_board_holder.cutter_indices_by_name:
        joined_holder.add_consumed_part_ref(
            y_axis_driver_board_holder.part_ref_for_named_cutter(name)
        )
    for name in y_axis_driver_board_holder.non_production_indices_by_name:
        joined_holder.add_consumed_part_ref(
            y_axis_driver_board_holder.part_ref_for_named_non_production_part(name)
        )

    return {"y_axis_driver_board_holder": joined_holder}
