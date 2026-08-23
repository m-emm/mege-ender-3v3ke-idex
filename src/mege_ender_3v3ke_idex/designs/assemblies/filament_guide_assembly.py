"""Filament-guide assembly reference geometry."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def create_filament_guide_spool():

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
    shaft_cutter = bearing.get_named_cutter("shaft_cutter")

    shaft_cutter_size = get_bounding_box_size(shaft_cutter)
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
    retval.add_named_cutter(bearing.get_named_cutter("shaft_cutter"), "shaft_cutter")

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


def create_filament_guide_assembly():
    frame_depth = 8.5
    frame_width = 4
    spacer_thickness = 1.5
    spacer_bearing_clearance = 0.2
    spool_gap = 0.1
    frame_spool_clearance = 1.5

    left_spool = create_filament_guide_spool()
    left_spool = left_spool.prefixed_copy("left_filament_guide_spool")

    right_spool = create_filament_guide_spool()
    right_spool = right_spool.prefixed_copy("right_filament_guide_spool")

    right_spool = align(
        right_spool, left_spool, Alignment.STACK_RIGHT, stack_gap=spool_gap
    )

    fused = left_spool.fuse(right_spool)

    frame = materialize_bounding_box(
        fused,
        y_size=frame_depth,
        z_enlargement=2 * (frame_width + frame_spool_clearance),
        x_enlargement=2 * (frame_width + frame_spool_clearance),
    )

    frame_cutter = materialize_bounding_box(
        fused,
        x_enlargement=2 * frame_spool_clearance,
        y_enlargement=2 * frame_spool_clearance,
        z_enlargement=2 * frame_spool_clearance,
    )

    frame = frame.cut(frame_cutter)

    retval = LeaderFollowersCuttersPart(frame)

    retval.add_named_non_production_part(left_spool.leader, "left_filament_guide_spool")
    retval.add_named_non_production_part(
        right_spool.leader, "right_filament_guide_spool"
    )

    retval = retval.merge_except_leader(left_spool)
    retval = retval.merge_except_leader(right_spool)

    for name, cutter in left_spool.get_named_cutter_items():
        _logger.info(f"Found left spool cutter: {name}")

    checked_one = False

    spacers = PartCollector()

    for name, cutter in retval.get_named_cutter_items():
        _logger.info(f"Checking cutter: {name}")
        checked_one = True
        if "shaft" in name:
            clearance_hole_diameter = MScrew.from_size("M5").clearance_hole_normal
            screw_cutter = create_cylinder(clearance_hole_diameter / 2, 100)
            screw_cutter = align(screw_cutter, cutter, Alignment.CENTER)

            retval = retval.cut(screw_cutter)

            for bt in [Alignment.BOTTOM, Alignment.TOP]:
                spacer = create_cylinder(
                    clearance_hole_diameter / 2 + spacer_thickness,
                    frame_spool_clearance - spacer_bearing_clearance,
                )
                spacer = align(spacer, cutter, Alignment.CENTER)
                spacer = align(
                    spacer,
                    right_spool,
                    bt.stack_alignment,
                    stack_gap=spacer_bearing_clearance,
                )
                spacer = spacer.cut(screw_cutter)
                spacers = spacers.fuse(spacer)

    retval = retval.fuse(spacers)

    mount_eye_depth = 20
    mount_eye_fillet_radius = 2
    mount_eye_screw_hole_inset = 6
    mount_eye_screw_size = "M5"
    mount_eye_hole_diameter = MScrew.from_size(
        mount_eye_screw_size
    ).clearance_hole_normal

    mount_eye = create_filleted_box(
        frame_width,
        mount_eye_depth,
        mount_eye_hole_diameter * 3,
        fillet_radius=mount_eye_fillet_radius,
        no_fillets_at=[Alignment.RIGHT, Alignment.LEFT, Alignment.BACK],
    )

    mount_eye = align(mount_eye, retval, Alignment.CENTER)

    mount_eye = align(mount_eye, retval, Alignment.LEFT)
    mount_eye = align(mount_eye, retval, Alignment.STACK_FRONT)

    mount_screw_cutter = create_cylinder(
        mount_eye_hole_diameter / 2, mount_eye_depth + 10
    )
    mount_screw_cutter = rotate(90, axis=(0, 1, 0))(mount_screw_cutter)
    mount_screw_cutter = align(mount_screw_cutter, mount_eye, Alignment.CENTER)
    mount_screw_cutter = align(mount_screw_cutter, mount_eye, Alignment.EDGE_FRONT)

    mount_screw_cutter = translate(0, mount_eye_screw_hole_inset, 0)(mount_screw_cutter)

    mount_eye = mount_eye.cut(mount_screw_cutter)

    retval = retval.fuse(mount_eye)

    if not checked_one:
        raise RuntimeError("No cutters were found in the filament guide assembly.")

    return retval
