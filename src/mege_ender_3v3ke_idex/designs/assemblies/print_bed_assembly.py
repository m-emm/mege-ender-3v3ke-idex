"""Declarative print bed assembly."""

from shellforgepy.simple import *


def create_print_bed_assembly(
    *,
    frame,
    print_bed_width,
    print_bed_depth,
    print_bed_thickness,
    print_bed_mount_hole_diameter,
    print_bed_mount_screw_size,
    print_bed_mount_screw_length,
    print_bed_mount_hole_pitch,
    print_bed_foil_thickness,
    print_bed_damper_height,
    print_bed_damper_diameter,
    print_bed_vertical_gap_to_frame,
    context=None,
):
    """Create the print bed assembly positioned relative to the frame."""

    big_thing = (context or {}).get("BIG_THING", 500)
    plate = create_box(print_bed_width, print_bed_depth, print_bed_thickness)
    inset = (print_bed_depth - print_bed_mount_hole_pitch) / 2

    retval = LeaderFollowersCuttersPart(plate)

    for lr in [Alignment.EDGE_LEFT, Alignment.EDGE_RIGHT]:
        for fb in [Alignment.EDGE_FRONT, Alignment.EDGE_BACK]:
            hole_drill = create_cylinder(print_bed_mount_hole_diameter / 2, big_thing)
            hole_drill = align(hole_drill, plate, Alignment.CENTER, axes=[2])
            hole_drill = align(hole_drill, plate, lr)
            hole_drill = align(hole_drill, plate, fb)
            hole_drill = translate(-inset * lr.sign, -inset * fb.sign, 0)(hole_drill)

            retval = retval.cut(hole_drill)

            screw = create_conical_head_screw(
                print_bed_mount_screw_size,
                print_bed_mount_screw_length,
            )
            screw = align(screw, hole_drill, Alignment.CENTER)
            screw = align(screw, plate, Alignment.TOP)

            retval.add_named_non_production_part(
                screw,
                f"screw_{lr.name.lower().replace('edge_', '')}_{fb.name.lower().replace('edge_', '')}",
            )
            retval = retval.cut(screw)

            damper = create_cylinder(
                print_bed_damper_diameter / 2,
                print_bed_damper_height,
            )
            damper = align(damper, hole_drill, Alignment.CENTER)
            damper = align(damper, plate, Alignment.STACK_BOTTOM)
            damper = damper.cut(hole_drill)

            retval.add_named_non_production_part(
                damper,
                f"damper_{lr.name.lower().replace('edge_', '')}_{fb.name.lower().replace('edge_', '')}",
            )

    foil = create_box(print_bed_width, print_bed_depth, print_bed_foil_thickness)
    foil = align(foil, plate, Alignment.CENTER, axes=[0, 1])
    foil = align(foil, plate, Alignment.STACK_TOP)
    retval.add_named_non_production_part(foil, "print_bed_foil")

    retval = align(retval, frame, Alignment.CENTER, axes=[0, 1])
    retval = align(
        retval,
        frame,
        Alignment.STACK_TOP,
        stack_gap=print_bed_vertical_gap_to_frame,
    )

    return retval
