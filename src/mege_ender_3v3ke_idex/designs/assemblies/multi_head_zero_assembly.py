"""Standalone multi-head zero reference assembly."""

from shellforgepy.simple import *


def create_multi_head_zero_assembly(
    *,
    multi_head_zero_body_width,
    multi_head_zero_body_depth,
    multi_head_zero_body_height,
    multi_head_zero_ball_top_height,
    multi_head_zero_ball_diameter,
    multi_head_zero_ball_shaft_diameter,
    multi_head_zero_ball_shaft_receptacle_diameter,
    multi_head_zero_ball_shaft_receptacle_height,
):
    """Create the multi-head zero body and its moving ball reference."""

    mount_holes_width_pitch = 10.5
    mount_holes_depth_pitch = 15.5
    mount_hole_drill_depth = 2.5
    mount_hole_screw_size = "M3"
    side_mount_hole_pitch = 13.5
    side_mount_hole_offset_from_bottom = 12
    side_mount_hole_head_drill_diameter = 5.85

    side_mount_hole_head_drill_depth = 3.25

    connector_width = 7.5
    connector_height = 5.75
    connector_bottom_offset = 3
    connector_protrusion = 2.5

    body = create_box(
        multi_head_zero_body_width,
        multi_head_zero_body_depth,
        multi_head_zero_body_height,
    )

    mount_hole_drills = None

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:

            mount_hole_drill = create_cylinder(
                MScrew.from_size(mount_hole_screw_size).clearance_hole_normal / 2, 50
            )

            mount_hole_drill = translate(
                lr.sign * mount_holes_width_pitch / 2,
                fb.sign * mount_holes_depth_pitch / 2,
                0,
            )(mount_hole_drill)

            if mount_hole_drills is None:
                mount_hole_drills = LeaderFollowersCuttersPart(mount_hole_drill)

            else:
                mount_hole_drills = mount_hole_drills.fuse(mount_hole_drill)

            mount_hole_drills.add_named_cutter(
                mount_hole_drill, f"mount_hole_{lr.name.lower()}_{fb.name.lower()}"
            )

    mount_hole_drills = align(mount_hole_drills, body, Alignment.CENTER)
    mount_hole_drills = align(
        mount_hole_drills, body, Alignment.STACK_TOP, stack_gap=-mount_hole_drill_depth
    )

    body = body.cut(mount_hole_drills.leader)

    side_hole_drills = None
    for fb in [Alignment.FRONT, Alignment.BACK]:
        side_hole_drill = create_cylinder(
            MScrew.from_size(mount_hole_screw_size).clearance_hole_normal / 2, 100
        )

        side_hole_drill = rotate(90, axis=(0, 1, 0))(side_hole_drill)
        side_hole_drill = translate(
            0,
            fb.sign * side_mount_hole_pitch / 2,
            0,
        )(side_hole_drill)

        if side_hole_drills is None:
            side_hole_drills = LeaderFollowersCuttersPart(side_hole_drill)
        else:
            side_hole_drills = side_hole_drills.fuse(side_hole_drill)

        side_hole_drills.add_named_cutter(
            side_hole_drill, f"side_hole_{fb.name.lower()}"
        )

    side_hole_drills = align(side_hole_drills, body, Alignment.CENTER)
    side_hole_drills = align(side_hole_drills, body, Alignment.EDGE_BOTTOM)
    side_hole_drills = translate(0, 0, side_mount_hole_offset_from_bottom)(
        side_hole_drills
    )

    body = body.cut(side_hole_drills.leader)

    for name, cutter in side_hole_drills.get_named_cutter_items():

        head_cutter = create_cylinder(
            side_mount_hole_head_drill_diameter / 2, side_mount_hole_head_drill_depth
        )
        head_cutter = rotate(90, axis=(0, 1, 0))(head_cutter)
        head_cutter = align(head_cutter, cutter, Alignment.CENTER)
        head_cutter = align(head_cutter, body, Alignment.LEFT)
        body = body.cut(head_cutter)

    ball = create_sphere(multi_head_zero_ball_diameter / 2)
    ball = align(ball, body, Alignment.CENTER)
    ball = align(ball, body, Alignment.TOP)
    ball = translate(0, 0, multi_head_zero_ball_top_height)(ball)

    shaft = create_cylinder(
        multi_head_zero_ball_shaft_diameter / 2,
        2 * (multi_head_zero_ball_top_height - multi_head_zero_ball_diameter / 2),
    )
    shaft = align(shaft, ball, Alignment.CENTER)

    _, shaft = cut_in_two(shaft, cut_normal=(0, 0, 1))

    receptacle = create_cylinder(
        multi_head_zero_ball_shaft_receptacle_diameter / 2,
        multi_head_zero_ball_shaft_receptacle_height,
    )
    receptacle = align(receptacle, body, Alignment.CENTER)
    receptacle = align(receptacle, body, Alignment.STACK_TOP)

    shaft_bore = create_cylinder(
        multi_head_zero_ball_shaft_diameter / 2,
        multi_head_zero_ball_shaft_receptacle_height,
    )
    shaft_bore = align(shaft_bore, receptacle, Alignment.CENTER)

    ball = shaft.fuse(ball)

    body = body.fuse(receptacle)
    body = body.cut(shaft_bore)

    assembly = LeaderFollowersCuttersPart(body)
    assembly.add_named_non_production_part(ball, "ball")

    for name, cutter in mount_hole_drills.get_named_cutter_items():
        assembly.add_named_cutter(cutter, name)
    for name, cutter in side_hole_drills.get_named_cutter_items():
        assembly.add_named_cutter(cutter, name)

    connector = create_box(connector_width, connector_protrusion, connector_height)
    connector = align(connector, body, Alignment.CENTER)
    connector = align(connector, body, Alignment.BOTTOM)
    connector = align(connector, body, Alignment.STACK_FRONT)

    connector = translate(0, 0, connector_bottom_offset)(connector)

    assembly.add_named_non_production_part(connector, "connector")

    return assembly
