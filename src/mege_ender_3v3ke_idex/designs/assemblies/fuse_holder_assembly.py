"""Panel-mount fuse holder reference assembly."""

import math

from shellforgepy.simple import *


def create_fuse_holder_assembly(
    *,
    fuse_holder_thread_diameter,
    fuse_holder_thread_length,
    fuse_holder_total_cylinder_length,
    fuse_holder_thin_cylinder_diameter,
    fuse_holder_thin_cylinder_length,
    fuse_holder_thicker_cylinder_diameter,
    fuse_holder_thicker_cylinder_length,
    fuse_holder_front_diameter,
    fuse_holder_front_length,
    fuse_holder_mount_nut_outer_diameter,
    fuse_holder_mount_nut_thickness,
    fuse_holder_mount_hole_clearance,
    fuse_holder_body_clearance,
):
    """Create a simplified side-mounted fuse holder with panel cutters."""

    fuse_holder_shoulder_length = (
        fuse_holder_total_cylinder_length
        - fuse_holder_thin_cylinder_length
        - fuse_holder_thicker_cylinder_length
        - fuse_holder_thread_length
        - fuse_holder_front_length
    )
    fuse_holder_thicker_cylinder_start = fuse_holder_thin_cylinder_length
    fuse_holder_shoulder_start = (
        fuse_holder_thicker_cylinder_start + fuse_holder_thicker_cylinder_length
    )
    fuse_holder_thread_start = fuse_holder_shoulder_start + fuse_holder_shoulder_length
    fuse_holder_front_start = fuse_holder_thread_start + fuse_holder_thread_length
    fuse_holder_mount_hole_diameter = (
        fuse_holder_thread_diameter + fuse_holder_mount_hole_clearance
    )

    thin_cylinder = create_cylinder(
        fuse_holder_thin_cylinder_diameter / 2,
        fuse_holder_thin_cylinder_length,
        direction=(1, 0, 0),
    )
    thicker_cylinder = create_cylinder(
        fuse_holder_thicker_cylinder_diameter / 2,
        fuse_holder_thicker_cylinder_length,
        origin=(fuse_holder_thicker_cylinder_start, 0, 0),
        direction=(1, 0, 0),
    )
    shoulder = create_cylinder(
        fuse_holder_thread_diameter / 2,
        fuse_holder_shoulder_length,
        origin=(fuse_holder_shoulder_start, 0, 0),
        direction=(1, 0, 0),
    )
    thread = create_cylinder(
        fuse_holder_thread_diameter / 2,
        fuse_holder_thread_length,
        origin=(fuse_holder_thread_start, 0, 0),
        direction=(1, 0, 0),
    )
    front_cap = create_cylinder(
        fuse_holder_front_diameter / 2,
        fuse_holder_front_length,
        origin=(fuse_holder_front_start, 0, 0),
        direction=(1, 0, 0),
    )

    holder_body = thin_cylinder.fuse(thicker_cylinder)
    holder_body = holder_body.fuse(shoulder)
    holder_body = holder_body.fuse(thread)
    holder_body = holder_body.fuse(front_cap)

    nut_points = []
    for point_index in range(6):
        angle = point_index * math.pi / 3
        nut_points.append(
            (
                fuse_holder_mount_nut_outer_diameter / 2 * math.cos(angle),
                fuse_holder_mount_nut_outer_diameter / 2 * math.sin(angle),
            )
        )
    mount_nut = create_extruded_polygon(
        nut_points,
        fuse_holder_mount_nut_thickness,
    )
    mount_nut = rotate(90, axis=(0, 1, 0))(mount_nut)
    mount_nut = align(mount_nut, front_cap, Alignment.CENTER, axes=[1, 2])
    mount_nut = align(mount_nut, front_cap, Alignment.STACK_LEFT)

    mount_nut_bore = create_cylinder(
        fuse_holder_mount_hole_diameter / 2,
        fuse_holder_mount_nut_thickness + 2,
        direction=(1, 0, 0),
    )
    mount_nut_bore = align(mount_nut_bore, mount_nut, Alignment.CENTER)
    mount_nut = mount_nut.cut(mount_nut_bore)

    blade_1 = create_box(14, 3.2, 0.8, origin=(-12, -1.6, 1.8))
    blade_2 = create_box(14, 3.2, 0.8, origin=(-12, -1.6, -2.6))
    blade_hole_1 = create_cylinder(1.0, 1.4, origin=(-8, 0, 1.5))
    blade_hole_2 = create_cylinder(1.0, 1.4, origin=(-8, 0, -2.9))
    blade_1 = blade_1.cut(blade_hole_1)
    blade_2 = blade_2.cut(blade_hole_2)
    terminal_blades = blade_1.fuse(blade_2)

    holder_reference = holder_body.fuse(mount_nut).fuse(terminal_blades)

    mount_panel_reference = create_cylinder(
        fuse_holder_mount_hole_diameter / 2,
        1.8,
        origin=(
            fuse_holder_front_start - fuse_holder_mount_nut_thickness - 1.8,
            0,
            0,
        ),
        direction=(1, 0, 0),
    )

    cutter_length = fuse_holder_total_cylinder_length + 20
    mount_hole = create_cylinder(
        fuse_holder_mount_hole_diameter / 2,
        cutter_length,
        direction=(1, 0, 0),
    )
    mount_hole = align(mount_hole, holder_body, Alignment.CENTER)

    body_clearance = create_cylinder(
        (fuse_holder_front_diameter + fuse_holder_body_clearance) / 2,
        cutter_length,
        direction=(1, 0, 0),
    )
    body_clearance = align(body_clearance, holder_body, Alignment.CENTER)

    assembly = LeaderFollowersCuttersPart(leader=holder_body)
    assembly.add_named_follower(holder_body, "holder_body")
    assembly.add_named_follower(mount_nut, "mount_nut")
    assembly.add_named_follower(terminal_blades, "terminal_blades")
    assembly.add_named_non_production_part(holder_reference, "holder_reference")
    assembly.add_named_non_production_part(
        mount_panel_reference, "mount_panel_reference"
    )
    assembly.add_named_cutter(mount_hole, "mount_hole")
    assembly.add_named_cutter(body_clearance, "body_clearance")

    return assembly
