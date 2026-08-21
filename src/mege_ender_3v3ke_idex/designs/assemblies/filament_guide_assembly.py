"""Filament-guide assembly reference geometry."""

from shellforgepy.simple import *


def create_filament_guide_assembly():

    wheel_thickness = 3
    wheel_z_oversize = 1

    spool_height = 5
    spool_waist_diameter = 14
    extra_shaft_cutter_size = 2

    num_inner_bite_cutters = 12
    inner_bite_depth = 1

    bearing_type = "695"  # "625"

    bearing = create_ball_bearing_mockup_assembly(
        bearing_type,
        shaft_cutter_length=100,
        shaft_cutter_clearance=extra_shaft_cutter_size,
    )

    bearing_size = get_bounding_box_size(bearing)

    shaft_cutter_size = get_bounding_box_size(bearing.get_named_cutter("shaft_cutter"))
    bearing_clearance_cutter_size = get_bounding_box_size(
        bearing.get_named_cutter("clearance_cutter")
    )

    wheel_diameter = bearing_size[0] + 2 * wheel_thickness

    wheel = create_cylinder(wheel_diameter / 2, bearing_size[2] + wheel_z_oversize)

    wheel = align(wheel, bearing, Alignment.CENTER)
    wheel = align(wheel, bearing, Alignment.BOTTOM)

    guide_spool = create_cone(
        wheel_diameter / 2, spool_waist_diameter / 2, spool_height
    )
    guide_spool = align(guide_spool, wheel, Alignment.CENTER)
    guide_spool = align(guide_spool, wheel, Alignment.STACK_TOP)

    half_spool = guide_spool.fuse(wheel)

    half_spool = bearing.use_as_cutter_on(half_spool)

    inner_bite_cutters = PartCollector()
    for i in range(num_inner_bite_cutters):

        angle = i * 360 / num_inner_bite_cutters

        inner_bite_cutter = create_cylinder(
            inner_bite_depth, bearing_clearance_cutter_size[2]
        )

        inner_bite_cutter = translate(bearing_clearance_cutter_size[0] / 2, 0, 0)(
            inner_bite_cutter
        )
        inner_bite_cutter = rotate(angle)(inner_bite_cutter)
        inner_bite_cutters = inner_bite_cutters.fuse(inner_bite_cutter)

    inner_bite_cutters = align(inner_bite_cutters, half_spool, Alignment.CENTER)
    inner_bite_cutters = align(inner_bite_cutters, half_spool, Alignment.BOTTOM)

    half_spool = half_spool.cut(inner_bite_cutters)

    retval = LeaderFollowersCuttersPart(half_spool)

    retval.add_named_non_production_part(bearing.leader, "bearing")
    retval.add_named_non_production_part(
        bearing.get_named_non_production_part("ball_cover"), "ball_cover"
    )

    half_spool_bbox = get_bounding_box(retval)
    half_spool_bbox_center = get_bounding_box_center(retval)

    mirrored = mirror(
        normal=(0, 0, 1),
        point=[
            half_spool_bbox_center[0],
            half_spool_bbox_center[1],
            half_spool_bbox[1][2],
        ],
    )(retval)

    mirrored = mirrored.prefixed_copy("top")

    retval = retval.fuse(mirrored)
    support_ring_thickness = 0.6
    support_z_gap = 0.4

    support_ring = create_ring(
        outer_radius=shaft_cutter_size[0] / 2 + support_ring_thickness,
        inner_radius=shaft_cutter_size[0] / 2,
        height=bearing_clearance_cutter_size[2] - support_z_gap,
    )
    support_ring = align(support_ring, retval, Alignment.CENTER)
    support_ring = align(support_ring, retval, Alignment.BOTTOM)

    retval = retval.fuse(support_ring)

    return retval
