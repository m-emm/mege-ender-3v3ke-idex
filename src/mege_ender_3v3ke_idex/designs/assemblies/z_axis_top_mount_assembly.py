"""Declarative monolithic z-axis top mount assembly."""

import copy

from shellforgepy.simple import *


def create_profile_mount_plate(
    *,
    profile_mount_width,
    z_axis_profile_mount_plate_thickness,
    z_axis_profile_mount_plate_height,
    z_axis_profile_mount_plate_fillet_radius,
    BIG_THING,
    num_holes,
    screw_inset,
):
    plate = create_filleted_box(
        profile_mount_width,
        z_axis_profile_mount_plate_thickness,
        z_axis_profile_mount_plate_height,
        z_axis_profile_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.BOTTOM],
    )

    hole_drill_diameter = MScrew.from_size("M5").clearance_hole_loose

    hole_drills = PartCollector()
    hole_pitch = (
        (z_axis_profile_mount_plate_height - 2 * screw_inset - hole_drill_diameter)
        / (num_holes - 1)
        if num_holes > 1
        else 0
    )
    for i in range(num_holes):
        hole_drill = create_cylinder(hole_drill_diameter / 2, BIG_THING)
        hole_drill = rotate(90, axis=(1, 0, 0))(hole_drill)
        hole_drill = translate(0, 0, i * hole_pitch)(hole_drill)
        hole_drills = hole_drills.fuse(hole_drill)

    hole_drills = align(hole_drills, plate, Alignment.CENTER)
    plate = plate.cut(hole_drills)

    return plate


def _get_part(part):
    return part.leader if hasattr(part, "leader") else part


def create_z_axis_top_mount_assembly(
    *,
    z_axis_profile,
    z_axis_rail,
    z_axis_threaded_rod,
    endstop_holder_assembly,
    BIG_THING,
    z_axis_endstop_cable_hole_size,
    z_axis_endstop_profile_clearance,
    z_axis_motor_mount_plate_profile_distance,
    z_axis_profile_mount_plate_num_holes,
    z_axis_profile_mount_plate_screw_inset,
    z_axis_top_profile_mount_plate_height,
    z_axis_profile_mount_plate_clearance,
    z_axis_profile_mount_plate_thickness,
    z_axis_profile_mount_plate_fillet_radius,
    z_axis_threaded_rod_diameter,
    z_axis_top_mount_depth,
    z_axis_top_mount_fillet_radius,
    z_axis_top_mount_profile_mount_width,
    z_axis_top_mount_thickness,
    z_axis_top_mount_threaded_rod_clearance,
    z_axis_top_mount_carriage_clearance,
    z_axis_carriage_width,
    z_axis_top_mount_width,
):
    """Create one monolithic printable top mount for a z-axis side."""

    profile = _get_part(z_axis_profile)
    rail = _get_part(z_axis_rail)
    threaded_rod = _get_part(z_axis_threaded_rod)

    top_mount_profile_mount_plates = PartCollector()
    for lr in [Alignment.RIGHT]:
        profile_mount_plate = create_profile_mount_plate(
            profile_mount_width=z_axis_top_mount_profile_mount_width,
            z_axis_profile_mount_plate_thickness=z_axis_profile_mount_plate_thickness,
            z_axis_profile_mount_plate_height=z_axis_top_profile_mount_plate_height,
            z_axis_profile_mount_plate_fillet_radius=z_axis_profile_mount_plate_fillet_radius,
            BIG_THING=BIG_THING,
            num_holes=z_axis_profile_mount_plate_num_holes,
            screw_inset=z_axis_profile_mount_plate_screw_inset,
        )
        profile_mount_plate = rotate(90)(profile_mount_plate)
        profile_mount_plate = align(
            profile_mount_plate,
            profile,
            Alignment.CENTER,
        )
        profile_mount_plate = align(profile_mount_plate, profile, Alignment.TOP)
        profile_mount_plate = align(
            profile_mount_plate,
            profile,
            lr.stack_alignment,
            stack_gap=z_axis_profile_mount_plate_clearance,
        )
        top_mount_profile_mount_plates = top_mount_profile_mount_plates.fuse(
            profile_mount_plate
        )

    top_mount_plate = top_mount_profile_mount_plates

    endstop_holder = copy.deepcopy(endstop_holder_assembly)

    endstop_holder = rotate(-90)(endstop_holder)

    endstop_holder_board_size = get_bounding_box_size(
        endstop_holder.get_non_production_part_by_name("board")
    )

    top_mount_plate_extension = create_box(
        z_axis_profile_mount_plate_thickness,
        endstop_holder_board_size[1] + 14,
        endstop_holder_board_size[2],
    )

    top_mount_plate_extension = align(
        top_mount_plate_extension,
        top_mount_plate,
        Alignment.CENTER,
    )
    top_mount_plate_extension = align(
        top_mount_plate_extension,
        top_mount_plate,
        Alignment.STACK_FRONT,
    )
    top_mount_plate_extension = align(
        top_mount_plate_extension,
        top_mount_plate,
        Alignment.TOP,
    )

    top_mount_plate = top_mount_plate.fuse(top_mount_plate_extension)

    endstop_holder = align(
        endstop_holder,
        top_mount_plate,
        Alignment.TOP,
    )
    endstop_holder = align(
        endstop_holder,
        top_mount_plate,
        Alignment.CENTER,
        axes=[0],
    )

    endstop_holder = align(
        endstop_holder,
        top_mount_plate,
        Alignment.FRONT,
    )
    endstop_holder = align(
        endstop_holder,
        top_mount_plate,
        Alignment.RIGHT,
    )

    endstop_holder_cutter = materialize_bounding_box(endstop_holder, x_enlargement=5)
    top_mount_plate = top_mount_plate.cut(endstop_holder_cutter)

    # endstop_holder = translate(
    #     0,
    #     -z_axis_endstop_profile_clearance,
    #     0,
    # )(endstop_holder)

    top_mount_plate = top_mount_plate.fuse(endstop_holder.leader)

    retval = LeaderFollowersCuttersPart(leader=top_mount_plate)
    for name, part in endstop_holder.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"endstop_{name}")

    return retval
