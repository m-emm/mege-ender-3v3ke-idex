"""Declarative z-axis top guide-rod mount assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.z_axis_components import create_profile_mount_plate
from shellforgepy.simple import *


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def _get_rod_part(rod):
    return rod.leader if hasattr(rod, "leader") else rod


def create_z_axis_guide_rod_top_mount_assembly(
    *,
    z_axis_profile,
    z_axis_guide_rod,
    z_axis_threaded_rod,
    BIG_THING,
    z_axis_cylinder_head_clearance,
    z_axis_default_clearance_hole_type,
    z_axis_default_screw_nut_cutter_clearance,
    z_axis_guide_rod_clamp_width,
    z_axis_motor_mount_plate_profile_distance,
    z_axis_profile_mount_plate_num_holes,
    z_axis_profile_mount_plate_screw_inset,
    z_axis_top_profile_mount_plate_height,
    z_axis_profile_mount_plate_clearance,
    z_axis_profile_mount_plate_thickness,
    z_axis_profile_mount_plate_fillet_radius,
    z_axis_rod_clamp_gap,
    z_axis_threaded_rod_diameter,
    z_axis_top_mount_depth,
    z_axis_top_mount_fillet_radius,
    z_axis_top_mount_holder_depth,
    z_axis_top_mount_holder_height,
    z_axis_top_mount_profile_mount_width,
    z_axis_top_mount_reinforcement_factor,
    z_axis_top_mount_reinforcement_thickness,
    z_axis_top_mount_screw_inset,
    z_axis_top_mount_screw_length,
    z_axis_top_mount_screw_size,
    z_axis_top_mount_thickness,
    z_axis_top_mount_threaded_rod_clearance,
    z_axis_top_mount_carriage_clearance,
    z_axis_carriage_width,
    z_axis_top_mount_width,
):
    """Create the printable top mount for one z-axis side."""

    profile = _get_profile_part(z_axis_profile)
    guide_rod = _get_rod_part(z_axis_guide_rod)
    threaded_rod = _get_rod_part(z_axis_threaded_rod)

    top_mount_plate = create_filleted_box(
        z_axis_top_mount_width,
        z_axis_top_mount_depth,
        z_axis_top_mount_thickness,
        z_axis_top_mount_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    top_mount_plate = align(top_mount_plate, guide_rod, Alignment.CENTER)
    top_mount_plate = align(
        top_mount_plate,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_motor_mount_plate_profile_distance,
    )

    rod_holder = create_filleted_box(
        z_axis_guide_rod_clamp_width,
        z_axis_top_mount_holder_depth,
        z_axis_top_mount_holder_height,
        z_axis_top_mount_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )
    rod_holder = align(rod_holder, top_mount_plate, Alignment.CENTER)
    rod_holder = align(rod_holder, top_mount_plate, Alignment.STACK_TOP)
    rod_holder = align(rod_holder, top_mount_plate, Alignment.FRONT)
    top_mount_plate = top_mount_plate.fuse(rod_holder)

    rod_holder_reinforcement = create_right_triangle(
        z_axis_top_mount_holder_height * z_axis_top_mount_reinforcement_factor,
        z_axis_top_mount_holder_height * z_axis_top_mount_reinforcement_factor,
        z_axis_top_mount_reinforcement_thickness,
        extrusion_direction=(1, 0, 0),
        a_normal=(0, 0, -1),
        b_normal=(0, 1, 0),
    )
    rod_holder_reinforcement = align(
        rod_holder_reinforcement,
        rod_holder,
        Alignment.CENTER,
    )
    rod_holder_reinforcement = align(
        rod_holder_reinforcement,
        rod_holder,
        Alignment.BOTTOM,
    )
    rod_holder_reinforcement = align(
        rod_holder_reinforcement,
        rod_holder,
        Alignment.STACK_BACK,
    )
    top_mount_plate = top_mount_plate.fuse(rod_holder_reinforcement)

    guide_rod_top_aligner = align_translation(
        top_mount_plate,
        z_axis_profile,
        Alignment.STACK_TOP,
        stack_gap=-z_axis_top_mount_thickness,
    )
    top_mount_plate = guide_rod_top_aligner(top_mount_plate)
    rod_holder = guide_rod_top_aligner(rod_holder)

    top_mount_plate = top_mount_plate.cut(guide_rod)

    rod_holder_representation = create_box(
        z_axis_guide_rod_clamp_width,
        z_axis_top_mount_holder_depth,
        z_axis_top_mount_holder_height - z_axis_top_mount_thickness,
    )
    rod_holder_representation = align(
        rod_holder_representation,
        rod_holder,
        Alignment.CENTER,
    )
    rod_holder_representation = align(
        rod_holder_representation,
        rod_holder,
        Alignment.TOP,
    )

    screw_assembly = create_four_screws_mount_assembly(
        rod_holder_representation,
        screw_size=z_axis_top_mount_screw_size,
        screw_length=z_axis_top_mount_screw_length,
        screw_direction=Alignment.FRONT,
        flush_with_top=True,
        length_inset=z_axis_top_mount_screw_inset,
        width_inset=z_axis_top_mount_screw_inset,
        cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
        clearance_type=z_axis_default_clearance_hole_type,
        nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
    )
    top_mount_plate = screw_assembly.use_as_cutter_on(top_mount_plate)

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

        top_mount_profile_mount_plate = create_profile_mount_plate(
            profile_mount_width=z_axis_top_mount_profile_mount_width,
            z_axis_profile_mount_plate_thickness=z_axis_profile_mount_plate_thickness,
            z_axis_profile_mount_plate_height=z_axis_top_profile_mount_plate_height,
            z_axis_profile_mount_plate_fillet_radius=z_axis_profile_mount_plate_fillet_radius,
            BIG_THING=BIG_THING,
            num_holes=z_axis_profile_mount_plate_num_holes,
            screw_inset=z_axis_profile_mount_plate_screw_inset,
        )
        top_mount_profile_mount_plate = rotate(90)(top_mount_profile_mount_plate)

        top_mount_profile_mount_plate = align(
            top_mount_profile_mount_plate,
            z_axis_profile,
            Alignment.CENTER,
        )
        top_mount_profile_mount_plate = align(
            top_mount_profile_mount_plate,
            z_axis_profile,
            Alignment.TOP,
        )
        top_mount_profile_mount_plate = align(
            top_mount_profile_mount_plate,
            z_axis_profile,
            lr.stack_alignment,
            stack_gap=z_axis_profile_mount_plate_clearance,
        )
        top_mount_profile_mount_plates = top_mount_profile_mount_plates.fuse(
            top_mount_profile_mount_plate
        )

    top_mount_plate = top_mount_plate.fuse(top_mount_profile_mount_plates)

    top_mount_plate_box = create_box(
        z_axis_top_mount_width,
        BIG_THING,
        z_axis_top_profile_mount_plate_height / 2,
    )

    top_mount_plate_box_cutter = create_box(
        z_axis_carriage_width + 2 * z_axis_top_mount_carriage_clearance,
        BIG_THING,
        BIG_THING,
    )

    top_mount_plate_box_cutter = align(
        top_mount_plate_box_cutter, top_mount_plate_box, Alignment.CENTER
    )
    top_mount_plate_box_cutter = align(
        top_mount_plate_box_cutter, top_mount_plate_box, Alignment.BACK
    )
    top_mount_plate_box_cutter = translate(0, -z_axis_profile_mount_plate_thickness, 0)(
        top_mount_plate_box_cutter
    )

    top_mount_plate_box = top_mount_plate_box.cut(top_mount_plate_box_cutter)

    top_mount_plate_box = align(top_mount_plate_box, top_mount_plate, Alignment.CENTER)
    top_mount_plate_box = align(
        top_mount_plate_box, top_mount_profile_mount_plates, Alignment.TOP
    )
    top_mount_plate_box = align(
        top_mount_plate_box,
        z_axis_profile,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_profile_mount_plate_thickness,
    )

    top_mount_profile_mount_plates_bbox = materialize_bounding_box(
        top_mount_profile_mount_plates,
        x_enlargement=2 * z_axis_profile_mount_plate_clearance,
    )

    top_mount_plate_box = top_mount_plate_box.cut(top_mount_profile_mount_plates_bbox)

    rod_plane_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    rod_plane_cutter = align(rod_plane_cutter, top_mount_plate, Alignment.CENTER)

    rod_size = get_bounding_box_size(guide_rod)
    rod_plane_cutter = align(
        rod_plane_cutter,
        guide_rod,
        Alignment.STACK_FRONT,
        stack_gap=-rod_size[1] / 2 - z_axis_rod_clamp_gap / 2,
    )

    top_mount_plate_box = top_mount_plate_box.cut(rod_plane_cutter)

    diagonal_cutter = create_right_triangle(
        BIG_THING,
        BIG_THING,
        BIG_THING,
        extrusion_direction=(1, 0, 0),
        a_normal=(0, 0, -1),
        b_normal=(0, 1, 0),
    )
    diagonal_cutter = align(diagonal_cutter, top_mount_plate, Alignment.CENTER)
    diagonal_cutter = align(diagonal_cutter, z_axis_profile, Alignment.TOP)
    diagonal_cutter = align(
        diagonal_cutter, guide_rod, Alignment.STACK_BACK, stack_gap=-rod_size[1] / 2 + z_axis_rod_clamp_gap / 2
    )

    diagonal_cutter = translate(0, 0, -z_axis_top_mount_thickness)(diagonal_cutter)

    top_mount_plate = top_mount_plate.fuse(top_mount_plate_box)

    top_mount_plate = top_mount_plate.cut(diagonal_cutter)

    rod_center = get_bounding_box_center(guide_rod)
    rod_holder_center = get_bounding_box_center(rod_holder)
    cut_point = (
        rod_holder_center[0],
        rod_center[1],
        rod_holder_center[2],
    )
    top_mount_back, top_mount_clamp = cut_in_two(
        top_mount_plate,
        cut_normal=(0, 1, 0),
        cut_point=cut_point,
        cut_thickness=z_axis_rod_clamp_gap,
    )

    retval = LeaderFollowersCuttersPart(leader=top_mount_back)
    retval.add_named_follower(top_mount_clamp, "top_mount_clamp")
    for name, part in screw_assembly.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"top_mount_{name}")

    return retval
