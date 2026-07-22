"""Join the positioned Y-axis driver-board holder and TMC5160T Plus."""

import numpy as np
from shellforgepy.simple import *


def join_y_axis_driver_board_holder_with_tmc5160t_plus(
    *,
    y_axis_driver_board_holder,
    bigtreetech_stepper_driver,
    board_holder_mount_screw_hole_inset,
    board_holder_mount_screw_size="M3",
):
    """Return the replaced holder without repositioning either injected input."""

    joined_holder = y_axis_driver_board_holder.copy()

    plate_surface_reference = y_axis_driver_board_holder.get_named_non_production_part(
        "plate_surface_reference"
    )

    plate_surface_reference_size = get_bounding_box_size(plate_surface_reference)
    plate_thickness = plate_surface_reference_size[2]

    mount_holes_fused = PartCollector()
    for name, cutter in bigtreetech_stepper_driver.get_named_cutter_items():
        if name.startswith("mount_hole"):
            mount_holes_fused = mount_holes_fused.fuse(cutter)

    mount_hole_plate = materialize_bounding_box(
        mount_holes_fused, x_enlargement=3, y_enlargement=3, z_size=plate_thickness
    )

    bigtreetech_stepper_driver_bbox = np.array(
        get_bounding_box(bigtreetech_stepper_driver)
    )

    diagonal_direction = np.array(bigtreetech_stepper_driver_bbox[1]) - np.array(
        bigtreetech_stepper_driver_bbox[0]
    )
    diagonal_direction[2] = 0
    length = np.linalg.norm(diagonal_direction)
    diagonal_direction /= length

    diagonal = directed_box_at(
        bigtreetech_stepper_driver_bbox[0],
        diagonal_direction,
        5,
        plate_thickness,
        length,
    )

    diagonal_center = get_bounding_box_center(diagonal)

    other_diagonal = mirror((0, 1, 0), point=diagonal_center)(diagonal)

    cross = diagonal.fuse(other_diagonal)

    cross = align(cross, joined_holder, Alignment.BOTTOM)

    mount_hole_plate = align(mount_hole_plate, joined_holder, Alignment.BOTTOM)
    mount_hole_plate_inner_cutter = materialize_bounding_box(
        mount_hole_plate, x_enlargement=-12, y_enlargement=-12, z_enlargement=100
    )

    btt_cutter = materialize_bounding_box(
        bigtreetech_stepper_driver,
        x_enlargement=-1,
        y_enlargement=-1,
        z_enlargement=100,
    )

    joined_holder = joined_holder.cut(btt_cutter)

    joined_holder = joined_holder.fuse(cross)
    joined_holder = joined_holder.fuse(mount_hole_plate)
    joined_holder = joined_holder.cut(mount_hole_plate_inner_cutter)

    joined_holder = bigtreetech_stepper_driver.use_as_cutter_on(joined_holder)

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
                joined_holder,
                Alignment.CENTER,
            )
            mount_screw_drill = align(
                mount_screw_drill,
                joined_holder,
                left_right_alignment.edge_alignment,
            )
            mount_screw_drill = align(
                mount_screw_drill,
                joined_holder,
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
