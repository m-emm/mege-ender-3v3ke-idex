"""Declarative monolithic z-axis top mount assembly."""

import copy

from mege_ender_3v3ke_idex.designs.z_axis_components import create_profile_mount_plate
from shellforgepy.simple import *


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

    top_mount_plate = create_filleted_box(
        z_axis_top_mount_width,
        z_axis_top_mount_depth,
        z_axis_top_mount_thickness,
        z_axis_top_mount_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    top_mount_plate = align(top_mount_plate, rail, Alignment.CENTER, axes=[0])
    top_mount_plate = align(
        top_mount_plate,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_motor_mount_plate_profile_distance,
    )
    flat_mount_plate = top_mount_plate

    top_aligner = align_translation(
        top_mount_plate,
        profile,
        Alignment.STACK_TOP,
        stack_gap=-z_axis_top_mount_thickness,
    )
    top_mount_plate = top_aligner(top_mount_plate)
    flat_mount_plate = top_aligner(flat_mount_plate)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_top_mount_threaded_rod_clearance,
        BIG_THING,
    )
    threaded_rod_cutter = align(
        threaded_rod_cutter,
        threaded_rod,
        Alignment.CENTER,
    )
    threaded_rod_cutter = align(
        threaded_rod_cutter,
        top_mount_plate,
        Alignment.CENTER,
        axes=[2],
    )
    top_mount_plate = top_mount_plate.cut(threaded_rod_cutter)

    top_mount_profile_mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
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

    top_mount_plate = top_mount_plate.fuse(top_mount_profile_mount_plates)

    top_mount_plate_box = create_box(
        z_axis_top_mount_width,
        z_axis_top_mount_depth,
        z_axis_top_profile_mount_plate_height / 2,
    )
    carriage_clearance_cutter = create_box(
        z_axis_carriage_width + 2 * z_axis_top_mount_carriage_clearance,
        BIG_THING,
        BIG_THING,
    )
    carriage_clearance_cutter = align(
        carriage_clearance_cutter,
        top_mount_plate_box,
        Alignment.CENTER,
    )
    carriage_clearance_cutter = align(
        carriage_clearance_cutter,
        top_mount_plate_box,
        Alignment.BACK,
    )
    carriage_clearance_cutter = translate(
        0,
        -z_axis_profile_mount_plate_thickness,
        0,
    )(carriage_clearance_cutter)
    top_mount_plate_box = top_mount_plate_box.cut(carriage_clearance_cutter)
    top_mount_plate_box = align(
        top_mount_plate_box,
        top_mount_plate,
        Alignment.CENTER,
    )
    top_mount_plate_box = align(
        top_mount_plate_box,
        top_mount_profile_mount_plates,
        Alignment.TOP,
    )
    top_mount_plate_box = align(
        top_mount_plate_box,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_profile_mount_plate_thickness,
    )
    profile_mount_plates_bbox = materialize_bounding_box(top_mount_profile_mount_plates)
    top_mount_plate_box = top_mount_plate_box.cut(profile_mount_plates_bbox)
    top_mount_plate = top_mount_plate.fuse(top_mount_plate_box)

    endstop_holder = copy.deepcopy(endstop_holder_assembly)
    endstop_holder = align(
        endstop_holder,
        flat_mount_plate,
        Alignment.CENTER,
        axes=[0],
    )
    endstop_holder = align(
        endstop_holder,
        flat_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    endstop_holder = align(
        endstop_holder,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_profile_mount_plate_clearance,
    )
    endstop_holder = translate(
        0,
        -z_axis_endstop_profile_clearance,
        0,
    )(endstop_holder)

    endstop_board = endstop_holder.get_non_production_part_by_name("board")
    cable_cutter = create_cylinder(
        z_axis_endstop_cable_hole_size / 2,
        BIG_THING,
        direction=(1, 0, 0),
    )
    cable_cutter = align(cable_cutter, endstop_board, Alignment.CENTER)
    cable_cutter = align(cable_cutter, endstop_board, Alignment.TOP)
    cable_cutter = align(
        cable_cutter,
        top_mount_plate,
        Alignment.STACK_RIGHT,
        stack_gap=-z_axis_carriage_width / 2,
    )
    top_mount_plate = top_mount_plate.cut(cable_cutter)
    top_mount_plate = top_mount_plate.fuse(endstop_holder.leader)

    retval = LeaderFollowersCuttersPart(leader=top_mount_plate)
    for name, part in endstop_holder.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"endstop_{name}")

    return retval
