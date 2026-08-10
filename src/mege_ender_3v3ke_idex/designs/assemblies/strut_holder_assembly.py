"""Simple strut holder assembly."""

import math

from shellforgepy.simple import *

strut_holder_hole_tilt = 20


def create_strut_holder_assembly(
    *,
    strut,
    strut_holder_width,
    strut_holder_length,
    strut_holder_thickness,
    strut_holder_fillet_radius,
    strut_holder_wall_height,
    strut_holder_wall_thickness,
    strut_holder_strut_size,
    strut_holder_strut_clearance,
    strut_holder_wall_length,
    strut_holder_mount_screw_size,
):
    """Create a strut holder with an injected strut reference available."""

    strut_holder_base = create_filleted_box(
        strut_holder_width,
        strut_holder_length,
        strut_holder_thickness,
        fillet_radius=strut_holder_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    strut_holder_base = align(strut_holder_base, strut, Alignment.CENTER, axes=[0])

    strut_holder_walls = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        strut_holder_wall = create_filleted_box(
            strut_holder_wall_thickness,
            strut_holder_wall_length,
            strut_holder_wall_height,
            fillet_radius=strut_holder_fillet_radius,
            no_fillets_at=[Alignment.BOTTOM, Alignment.RIGHT, Alignment.LEFT],
        )
        strut_holder_wall = align(
            strut_holder_wall,
            strut,
            lr.stack_alignment,
            stack_gap=strut_holder_strut_clearance,
        )
        strut_holder_walls = strut_holder_walls.fuse(strut_holder_wall)

    hole_diameter = MScrew.from_size(strut_holder_mount_screw_size).clearance_hole_loose
    long_holes = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        long_hole = create_rounded_slab(
            (strut_holder_wall_height - 2 * hole_diameter)
            * math.cos(math.radians(strut_holder_hole_tilt)),
            hole_diameter,
            500,
            hole_diameter / 2,
        )
        long_hole = rotate(90, axis=(0, 1, 0))(long_hole)

        long_hole = align(
            long_hole,
            strut_holder_walls,
            Alignment.CENTER,
        )

        long_hole = align(
            long_hole,
            strut_holder_walls,
            fb.stack_alignment,
            stack_gap=-3 * hole_diameter,
        )
        long_holes = long_holes.fuse(long_hole)

        screw_hole = create_cylinder(hole_diameter / 2, 500)

        screw_hole = align(
            screw_hole,
            strut_holder_base,
            Alignment.CENTER,
        )
        screw_hole = align(
            screw_hole,
            strut_holder_base,
            fb.edge_alignment,
        )
        screw_hole = translate(0, -fb.sign * 1.5 * hole_diameter, 0)(screw_hole)

        strut_holder_base = strut_holder_base.cut(screw_hole)

    long_holes = rotate(-strut_holder_hole_tilt, axis=(1, 0, 0))(long_holes)

    long_holes = align(long_holes, strut_holder_walls, Alignment.CENTER)

    strut_holder_walls = strut_holder_walls.cut(long_holes)

    strut_holder_walls = align(strut_holder_walls, strut_holder_base, Alignment.CENTER)
    strut_holder_walls = align(
        strut_holder_walls, strut_holder_base, Alignment.STACK_TOP
    )

    strut_holder_base = strut_holder_base.fuse(strut_holder_walls)

    retval = LeaderFollowersCuttersPart(strut_holder_base)
    return retval
