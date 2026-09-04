"""Self-contained front-spar mount for the multi-head-zero reference."""

import math

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.simple import *


def create_multi_head_zero_mount_assembly(
    *,
    print_bed,
    print_bed_undercarriage,
    multi_head_zero,
    multi_head_zero_mount_clamp_fillet_radius,
    multi_head_zero_mount_clamp_width,
    multi_head_zero_mount_u_wall_thickness,
    multi_head_zero_mount_u_bottom_thickness,
    multi_head_zero_mount_u_spar_clearance_y,
    multi_head_zero_mount_u_spar_clearance_z,
    multi_head_zero_mount_u_ear_height_above_spar,
    multi_head_zero_mount_u_screw_gap_above_spar,
    multi_head_zero_mount_clamp_screw_size,
    multi_head_zero_mount_clamp_screw_length,
    multi_head_zero_mount_clamp_screw_inset,
    multi_head_zero_mount_clamp_nut_clearance,
    multi_head_zero_mount_clamp_cylinder_head_clearance,
    multi_head_zero_mount_clamp_thread_inset_holder_thickness,
    multi_head_zero_mount_clamp_thread_inset_extra_radius,
    multi_head_zero_mount_clamp_thread_inset_hole_radius_adjustment,
    multi_head_zero_mount_screw_mount_clearance_type,
):
    """Create a front-spar clamp and bridge to the multi-head-zero body."""

    _ = print_bed
    _ = multi_head_zero_mount_clamp_nut_clearance

    multi_head_zero_body_reference = multi_head_zero.get_named_non_production_part(
        "body_reference"
    )
    front_spar_reference = print_bed_undercarriage.get_named_non_production_part(
        "front_spar_profile_reference"
    )

    spar_size = get_bounding_box_size(front_spar_reference)
    front_spar_keepout = create_box(
        multi_head_zero_mount_clamp_width,
        spar_size[1] + 2 * multi_head_zero_mount_u_spar_clearance_y,
        spar_size[2] + multi_head_zero_mount_u_spar_clearance_z,
    )
    front_spar_keepout = align(
        front_spar_keepout,
        multi_head_zero_body_reference,
        Alignment.CENTER,
        axes=[0],
    )
    front_spar_keepout = align(
        front_spar_keepout,
        front_spar_reference,
        Alignment.CENTER,
        axes=[1, 2],
    )

    u_outer_depth = (
        get_bounding_box_size(front_spar_keepout)[1]
        + 2 * multi_head_zero_mount_u_wall_thickness
    )
    u_outer_height = (
        get_bounding_box_size(front_spar_keepout)[2]
        + multi_head_zero_mount_u_bottom_thickness
        + multi_head_zero_mount_u_ear_height_above_spar
    )

    bottom_wall = create_filleted_box(
        multi_head_zero_mount_clamp_width,
        u_outer_depth,
        multi_head_zero_mount_u_bottom_thickness,
        fillet_radius=multi_head_zero_mount_clamp_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    bottom_wall = align(bottom_wall, front_spar_keepout, Alignment.CENTER)
    bottom_wall = align(bottom_wall, front_spar_keepout, Alignment.STACK_BOTTOM)

    front_wall = create_filleted_box(
        multi_head_zero_mount_clamp_width,
        multi_head_zero_mount_u_wall_thickness,
        u_outer_height,
        fillet_radius=multi_head_zero_mount_clamp_fillet_radius,
        no_fillets_at=[Alignment.BACK, Alignment.FRONT, Alignment.BOTTOM],
    )
    front_wall = align(front_wall, bottom_wall, Alignment.CENTER)
    front_wall = align(front_wall, front_spar_keepout, Alignment.STACK_FRONT)
    front_wall = align(front_wall, bottom_wall, Alignment.BOTTOM)

    back_wall = create_filleted_box(
        multi_head_zero_mount_clamp_width,
        multi_head_zero_mount_u_wall_thickness,
        u_outer_height,
        fillet_radius=multi_head_zero_mount_clamp_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.BOTTOM],
    )
    back_wall = align(back_wall, bottom_wall, Alignment.CENTER)
    back_wall = align(back_wall, front_spar_keepout, Alignment.STACK_BACK)
    back_wall = align(back_wall, bottom_wall, Alignment.BOTTOM)

    lips = PartCollector()
    lip_size = 1.5
    lip_protrusion = 1
    lip_z_offset = 0.0
    for fr in [Alignment.FRONT, Alignment.BACK]:

        lip = create_box(multi_head_zero_mount_clamp_width, lip_size, lip_size)

        lip = rotate(45, axis=(1, 0, 0))(lip)

        lip = align(lip, bottom_wall, Alignment.CENTER)
        if fr == Alignment.FRONT:
            lip = align(lip, front_wall, Alignment.BACK)
        else:
            lip = align(lip, back_wall, Alignment.FRONT)

        lip = align(lip, bottom_wall, Alignment.EDGE_TOP)
        lip = translate(
            0,
            -fr.sign * lip_protrusion,
            spar_size[2] + lip_z_offset + math.sqrt(2) / 2 * lip_size,
        )(lip)

        lips = lips.fuse(lip)

    u_channel = front_wall.fuse(back_wall).fuse(bottom_wall)
    u_channel = u_channel.fuse(lips)

    screw_z_reference = create_box(
        1,
        1,
        2 * multi_head_zero_mount_u_screw_gap_above_spar,
    )
    screw_z_reference = align(
        screw_z_reference,
        front_spar_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    screw_z_reference = align(
        screw_z_reference,
        front_spar_reference,
        Alignment.STACK_TOP,
    )

    screw_x_span = create_box(
        multi_head_zero_mount_clamp_width - 2 * multi_head_zero_mount_clamp_screw_inset,
        1,
        1,
    )
    screw_x_span = align(screw_x_span, u_channel, Alignment.CENTER, axes=[0, 1])
    screw_x_span = align(screw_x_span, screw_z_reference, Alignment.CENTER, axes=[2])

    screw_mounts = None
    clamp_thread_inset_bosses = PartCollector()
    clamp_thread_inset_cutters = PartCollector()
    clamp_thread_insets = PartCollector()
    for side_alignment in (Alignment.LEFT, Alignment.RIGHT):
        screw_target = create_box(0.1, u_outer_depth, 0.1)
        screw_target = align(screw_target, screw_x_span, side_alignment)
        screw_target = align(screw_target, u_channel, Alignment.CENTER, axes=[1])
        screw_target = align(
            screw_target,
            screw_z_reference,
            Alignment.CENTER,
            axes=[2],
        )
        screw_mount = create_screw_mount_assembly(
            screw_target,
            screw_size=multi_head_zero_mount_clamp_screw_size,
            screw_length=multi_head_zero_mount_clamp_screw_length,
            screw_direction=Alignment.FRONT,
            with_nut_cutter=False,
            flush_with_top=False,
            cylinder_head_cutter_clearance=(
                multi_head_zero_mount_clamp_cylinder_head_clearance
            ),
            clearance_type=multi_head_zero_mount_screw_mount_clearance_type,
        )
        screw_hole = screw_mount.get_named_cutter("hole_cutter")
        thread_inset_assembly = create_thread_inset_assembly(
            size=multi_head_zero_mount_clamp_screw_size,
            thickness=multi_head_zero_mount_clamp_thread_inset_holder_thickness,
            extra_radius=multi_head_zero_mount_clamp_thread_inset_extra_radius,
            clearance_type=multi_head_zero_mount_screw_mount_clearance_type,
            thread_inset_hole_radius_adjustment=(
                multi_head_zero_mount_clamp_thread_inset_hole_radius_adjustment
            ),
        )
        thread_inset_assembly = rotate(90, axis=(1, 0, 0))(thread_inset_assembly)
        thread_inset_assembly = align(
            thread_inset_assembly,
            screw_hole,
            Alignment.CENTER,
        )
        thread_inset_assembly = align(
            thread_inset_assembly,
            u_channel,
            Alignment.STACK_BACK,
            stack_gap=-multi_head_zero_mount_u_wall_thickness,
        )

        thread_inset_boss = thread_inset_assembly.get_named_cutter("assembly_cutter")
        thread_inset_cutter = thread_inset_boss.cut(thread_inset_assembly.leader)
        clamp_thread_inset_bosses = clamp_thread_inset_bosses.fuse(thread_inset_boss)
        clamp_thread_inset_cutters = clamp_thread_inset_cutters.fuse(
            thread_inset_cutter
        )
        clamp_thread_insets = clamp_thread_insets.fuse(
            thread_inset_assembly.get_named_non_production_part("thread_inset")
        )

        screw_mount = screw_mount.prefixed_copy(f"pinch_{side_alignment.name.lower()}")
        screw_mounts = (
            screw_mount if screw_mounts is None else screw_mounts.fuse(screw_mount)
        )

    u_channel = u_channel.fuse(clamp_thread_inset_bosses)
    u_channel = u_channel.cut(clamp_thread_inset_cutters)
    u_channel = screw_mounts.use_as_cutter_on(u_channel)

    bridge = materialize_bounding_box(u_channel, z_size=30, y_size=80)
    bridge = align(bridge, multi_head_zero_body_reference, Alignment.CENTER)
    bridge = align(bridge, u_channel, Alignment.BOTTOM)
    bridge = fit_part_between(
        bridge,
        cut_normal=(0, 1, 0),
        limiting_start_part=u_channel,
        limiting_end_part=multi_head_zero_body_reference,
    )

    bridge_size = get_bounding_box_size(bridge)

    top_mount_plate = materialize_bounding_box(
        multi_head_zero_body_reference, z_size=4, x_size=bridge_size[0], y_enlargement=5
    )
    top_mount_plate = align(
        top_mount_plate, multi_head_zero_body_reference, Alignment.STACK_TOP
    )
    top_mount_plate = align(
        top_mount_plate, multi_head_zero_body_reference, Alignment.FRONT
    )

    top_mount_plate = multi_head_zero.use_as_cutter_on(top_mount_plate)

    shaft_space_cutter = create_cylinder(12.5 / 2, 100)
    shaft_space_cutter = align(
        shaft_space_cutter, multi_head_zero_body_reference, Alignment.CENTER
    )
    top_mount_plate = top_mount_plate.cut(shaft_space_cutter)

    bridge = bridge.fuse(top_mount_plate)

    side_mount_plates = PartCollector()
    connector = multi_head_zero.get_named_non_production_part("connector")
    connector_cutter = materialize_bounding_box(
        connector, x_enlargement=10, y_enlargement=1.0, z_enlargement=10
    )
    connector_cutter = align(connector_cutter, bridge, Alignment.BOTTOM)
    side_mount_plate_clearance = 0.6
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        side_mount_plate = materialize_bounding_box(
            multi_head_zero_body_reference, x_size=2, z_size=bridge_size[2]
        )

        side_mount_plate = align(
            side_mount_plate,
            multi_head_zero_body_reference,
            lr.stack_alignment,
            stack_gap=side_mount_plate_clearance,
        )
        side_mount_plate = align(side_mount_plate, bridge, Alignment.BOTTOM)
        side_mount_plate = side_mount_plate.cut(connector_cutter)
        side_mount_plates = side_mount_plates.fuse(side_mount_plate)

    bridge = bridge.fuse(side_mount_plates)

    leader = bridge.fuse(u_channel)
    clamp_screw_holes = PartCollector()
    for _name, cutter in screw_mounts.get_named_cutter_items():
        clamp_screw_holes = clamp_screw_holes.fuse(cutter)

    clamp_screws = PartCollector()
    for name, part in screw_mounts.get_named_non_production_part_items():
        if name.endswith("_screw"):
            clamp_screws = clamp_screws.fuse(part)

    assembly = LeaderFollowersCuttersPart(leader)
    assembly.add_named_cutter(front_spar_keepout, "front_spar_keepout")
    assembly.add_named_cutter(clamp_screw_holes, "clamp_screw_holes")
    assembly.add_named_cutter(
        clamp_thread_inset_cutters,
        "clamp_thread_inset_cutters",
    )
    assembly.add_named_non_production_part(clamp_screws, "clamp_screws")
    assembly.add_named_non_production_part(
        clamp_thread_insets,
        "clamp_thread_insets",
    )
    assembly.add_named_non_production_part(u_channel, "u_clamp_preview")
    assembly.set_hidden_by_default("u_clamp_preview")
    return assembly
