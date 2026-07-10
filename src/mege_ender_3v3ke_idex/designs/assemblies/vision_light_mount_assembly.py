"""Vision light mount for below-bed nozzle-offset illumination."""

import numpy as np
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.simple import *


def create_vision_light_mount_assembly(
    *,
    print_bed,
    print_bed_undercarriage,
    apa_strip_front,
    apa_strip_back,
    apa_strip_left,
    apa_strip_right,
    xh_b4b_xh_a,
    vision_lights_mount_additional_pins,
    vision_light_mount_plate_thickness,
    vision_light_mount_plate_border,
    vision_light_mount_plate_fillet_radius,
    vision_light_mount_aperture_clearance,
    vision_light_mount_strip_pocket_clearance,
    vision_light_mount_strip_pocket_depth,
    vision_light_mount_cover_thickness,
    vision_light_mount_clamp_width,
    vision_light_mount_u_wall_thickness,
    vision_light_mount_u_bottom_thickness,
    vision_light_mount_u_spar_clearance_y,
    vision_light_mount_u_spar_clearance_z,
    vision_light_mount_u_ear_height_above_spar,
    vision_light_mount_u_screw_gap_above_spar,
    vision_light_mount_clamp_screw_size,
    vision_light_mount_clamp_screw_length,
    vision_light_mount_clamp_screw_inset,
    vision_light_mount_clamp_nut_clearance,
    vision_light_mount_clamp_cylinder_head_clearance,
    vision_light_mount_screw_mount_clearance_type,
    vision_light_mount_strip_gap,
    BIG_THING,
):
    """Build a PETG-CF mount using the bed/undercarriage as references."""

    _ = print_bed.leader
    _ = BIG_THING

    cover_screw_size = "M2.5"  # TODO: make all these parameters with proper prefix, and add to idex_parameters.yaml
    cover_screw_inset = 3.5
    cover_screw_length = 10
    cover_screw_cylinder_head_clearance = 0.1
    additional_pins_inset = 7

    strip_leaders = {
        Alignment.FRONT: apa_strip_front.leader,
        Alignment.BACK: apa_strip_back.leader,
        Alignment.LEFT: apa_strip_left.leader,
        Alignment.RIGHT: apa_strip_right.leader,
    }

    strip_front_size = get_bounding_box_size(strip_leaders[Alignment.FRONT])

    strip_leaders_fused = PartCollector()
    for strip in strip_leaders.values():
        strip_leaders_fused = strip_leaders_fused.fuse(strip)

    strip_leaders_size = get_bounding_box_size(strip_leaders_fused)

    plate_width = strip_leaders_size[0] + 2 * vision_light_mount_plate_border
    plate_depth = strip_leaders_size[1] + 2 * vision_light_mount_plate_border

    plate = create_filleted_box(
        plate_width,
        plate_depth,
        vision_light_mount_plate_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    plate = align(plate, strip_leaders_fused, Alignment.CENTER)
    plate = align(
        plate,
        strip_leaders_fused,
        Alignment.STACK_BOTTOM,
        stack_gap=-vision_light_mount_strip_pocket_depth,
    )

    aperture_boundary_width = (
        2 * strip_front_size[1] + 2 * vision_light_mount_aperture_clearance
    )

    aperture = materialize_bounding_box(
        strip_leaders_fused,
        x_enlargement=-aperture_boundary_width,
        y_enlargement=-aperture_boundary_width,
        z_enlargement=500,
    )
    aperture = align(aperture, strip_leaders_fused, Alignment.CENTER)
    plate = plate.cut(aperture)

    pocket_top_reference = create_box(1, 1, 0.1)
    pocket_top_reference = align(pocket_top_reference, plate, Alignment.STACK_TOP)
    strip_pockets = PartCollector()
    for strip in strip_leaders.values():
        pocket = materialize_bounding_box(
            strip,
            x_enlargement=2 * vision_light_mount_strip_pocket_clearance,
            y_enlargement=2 * vision_light_mount_strip_pocket_clearance,
            z_enlargement=(
                vision_light_mount_strip_pocket_depth
                + 0.2
                - get_bounding_box_size(strip)[2]
            ),
        )
        pocket = align(pocket, pocket_top_reference, Alignment.TOP)
        strip_pockets = strip_pockets.fuse(pocket)
    plate = plate.cut(strip_pockets)
    front_spar_reference = print_bed_undercarriage.get_named_non_production_part(
        "front_spar_profile_reference"
    )
    spar_size = get_bounding_box_size(front_spar_reference)
    front_spar_keepout = create_box(
        vision_light_mount_clamp_width,
        spar_size[1] + 2 * vision_light_mount_u_spar_clearance_y,
        spar_size[2] + vision_light_mount_u_spar_clearance_z,
    )
    front_spar_keepout = align(
        front_spar_keepout,
        aperture,
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
        + 2 * vision_light_mount_u_wall_thickness
    )
    configured_u_outer_height = (
        get_bounding_box_size(front_spar_keepout)[2]
        + vision_light_mount_u_bottom_thickness
        + vision_light_mount_u_ear_height_above_spar
    )
    u_outer_height = configured_u_outer_height

    bottom_wall = create_filleted_box(
        vision_light_mount_clamp_width,
        u_outer_depth,
        vision_light_mount_u_bottom_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP],
    )
    bottom_wall = align(bottom_wall, front_spar_keepout, Alignment.CENTER)
    bottom_wall = align(bottom_wall, front_spar_keepout, Alignment.STACK_BOTTOM)
    bottom_wall = align(bottom_wall, plate, Alignment.LEFT)

    front_wall = create_filleted_box(
        vision_light_mount_clamp_width,
        vision_light_mount_u_wall_thickness,
        u_outer_height,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BACK, Alignment.FRONT],
    )
    front_wall = align(front_wall, bottom_wall, Alignment.CENTER)
    front_wall = align(front_wall, front_spar_keepout, Alignment.STACK_FRONT)
    front_wall = align(front_wall, bottom_wall, Alignment.BOTTOM)

    back_wall = create_filleted_box(
        vision_light_mount_clamp_width,
        vision_light_mount_u_wall_thickness,
        u_outer_height,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    back_wall = align(back_wall, bottom_wall, Alignment.CENTER)
    back_wall = align(back_wall, front_spar_keepout, Alignment.STACK_BACK)
    back_wall = align(back_wall, bottom_wall, Alignment.BOTTOM)

    u_channel = front_wall.fuse(back_wall).fuse(bottom_wall)

    screw_z_reference = create_box(
        1,
        1,
        2 * vision_light_mount_u_screw_gap_above_spar,
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
        vision_light_mount_clamp_width - 2 * vision_light_mount_clamp_screw_inset,
        1,
        1,
    )
    screw_x_span = align(screw_x_span, u_channel, Alignment.CENTER, axes=[0, 1])
    screw_x_span = align(screw_x_span, screw_z_reference, Alignment.CENTER, axes=[2])

    screw_mounts = None
    for side_alignment in (
        Alignment.LEFT,
        Alignment.RIGHT,
    ):
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
            screw_size=vision_light_mount_clamp_screw_size,
            screw_length=vision_light_mount_clamp_screw_length,
            screw_direction=Alignment.FRONT,
            with_nut_cutter=True,
            nut_cutter_clearance=vision_light_mount_clamp_nut_clearance,
            flush_with_top=False,
            cylinder_head_cutter_clearance=(
                vision_light_mount_clamp_cylinder_head_clearance
            ),
            clearance_type=vision_light_mount_screw_mount_clearance_type,
        )
        screw_mount = screw_mount.prefixed_copy(f"pinch_{side_alignment.name.lower()}_")
        screw_mounts = (
            screw_mount if screw_mounts is None else screw_mounts.fuse(screw_mount)
        )

    u_channel = screw_mounts.use_as_cutter_on(u_channel)

    leader = plate.fuse(u_channel)

    connector_visual_parts = []
    connecctor_cutters = PartCollector()
    for connector_angle in [0, -90]:

        turn_alignment = rotate_alignment(connector_angle)

        connector_alignment = turn_alignment(Alignment.RIGHT)
        strip_to_align = strip_leaders[connector_alignment]
        connector_name = connector_alignment.name.lower()
        connector = rotate(180, axis=(0, 1, 0))(xh_b4b_xh_a)
        connector = rotate(90)(connector)
        connector = rotate(connector_angle)(connector)
        connector = align(connector, strip_to_align, turn_alignment(Alignment.LEFT))
        connector = align(connector, strip_to_align, turn_alignment(Alignment.STACK_FRONT), stack_gap=7)

        connector = align(connector, plate, Alignment.TOP)

#         connector = translate(0, 2 * cover_screw_inset, -2)(connector)

        connector_visual_parts.append(
            (f"xh_connector_{connector_name}_housing", connector.leader)
        )
        for name, part in connector.get_named_follower_items():
            connector_visual_parts.append(
                (f"xh_connector_{connector_name}_{name}", part)
            )
        for name, part in connector.get_named_non_production_part_items():
            connector_visual_parts.append(
                (f"xh_connector_{connector_name}_{name}", part)
            )

        connector_cutter = materialize_bounding_box(
            connector,
            x_enlargement=1.5,
            y_enlargement=0.5,
            z_enlargement=0.0,
        )

        pins_window_cutter = materialize_bounding_box(
            connector.get_named_non_production_part("pins"),
            x_enlargement=2,
            y_enlargement=2,
        )
        connector_cutter = connector_cutter.fuse(pins_window_cutter)
        connecctor_cutters = connecctor_cutters.fuse(connector_cutter)

    leader = leader.cut(connecctor_cutters)

    cover_screw = MScrew.from_size(cover_screw_size)
    additional_pins_side_inset = cover_screw_inset
    additional_pins_holders = PartCollector()
    additional_pins_base_plate_cutters = PartCollector()
    additional_pins_visual_parts = []
    pin_cutters = PartCollector()
    for i in range(4):

        
        angle = i * 90
        turn_alignment = rotate_alignment(angle)

        strip_to_align = strip_leaders[turn_alignment(Alignment.LEFT)]

        positioned_pins = vision_lights_mount_additional_pins.copy()
        positioned_pins = rotate(180, axis=(0, 1, 0))(positioned_pins)
        positioned_pins = rotate(-90, axis=(0, 0, 1))(positioned_pins)
        positioned_pins = rotate(angle)(positioned_pins)


        # positioned_pins = positioned_pins.aligned_from_follower(
        #     "additional_pins_base_plate",
        #     plate,
        #     Alignment.BOTTOM,
        # )
        positioned_pins = align(positioned_pins, plate, Alignment.BOTTOM)

        positioned_pins = positioned_pins.aligned_from_follower(
            "additional_pins_base_plate",
            strip_to_align,
            turn_alignment(Alignment.STACK_BACK),
        )
        positioned_pins = positioned_pins.aligned_from_follower(
            "additional_pins_base_plate",
            strip_to_align,
            turn_alignment(Alignment.RIGHT),
        )

        # translation_vector_raw = np.array([ -additional_pins_side_inset-cover_screw_inset , -additional_pins_side_inset-cover_screw_inset, 0 ])

        # rotation_matrix = np.array(
        #     [
        #         [np.cos(np.radians(angle)), -np.sin(np.radians(angle)), 0],
        #         [np.sin(np.radians(angle)), np.cos(np.radians(angle)), 0],
        #         [0, 0, 1],
        #     ]

        # )
        # translation_vector_rotated = rotation_matrix @ translation_vector_raw


        # positioned_pins = translate(*translation_vector_rotated)(positioned_pins)

        additional_pins_holders = additional_pins_holders.fuse(positioned_pins.leader)
        additional_pins_base_plate = positioned_pins.get_follower_part_by_name(
            "additional_pins_base_plate"
        )
        additional_pins_base_plate_cutters = additional_pins_base_plate_cutters.fuse(
            materialize_bounding_box(additional_pins_base_plate, z_enlargement=500)
        )

        prefix = f"vision_lights_mount_additional_pins_{turn_alignment(Alignment.LEFT).name.lower()}"
        prefixed_pins = positioned_pins.prefixed_copy(prefix)
        for name, part in prefixed_pins.get_named_non_production_part_items():
            additional_pins_visual_parts.append((name, part))

        pin_cutters = pin_cutters.fuse(
            positioned_pins.get_cutter_part_by_name("pin_cutters")
        )

    leader = leader.cut(additional_pins_base_plate_cutters)
    leader = leader.fuse(additional_pins_holders)

    cover_plate = create_filleted_box(
        plate_width,
        plate_depth,
        vision_light_mount_cover_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    cover_plate = align(cover_plate, plate, Alignment.CENTER)
    cover_plate = align(cover_plate, plate, Alignment.STACK_TOP, stack_gap=5)

    cover_bbox = get_bounding_box(cover_plate)
    plate_bbox = get_bounding_box(plate)
    strips_bbox = get_bounding_box(strip_leaders_fused)

    strip_downholder = create_box(
        plate_width,
        3,
        cover_bbox[1][2] - strips_bbox[1][2],
    )
    strip_downholder_rotated = create_box(
        3,
        plate_depth,
        cover_bbox[1][2] - strips_bbox[1][2],
    )

    strip_downholder_rotated = align(
        strip_downholder_rotated, strip_downholder, Alignment.CENTER
    )

    strip_downholder = strip_downholder.fuse(strip_downholder_rotated)

    strip_downholder = align(strip_downholder, cover_plate, Alignment.CENTER)
    strip_downholder = align(strip_downholder, cover_plate, Alignment.TOP)

    downholder_border_cutter = create_box_hole_cutter(
        plate_width
        - 2 * vision_light_mount_plate_border
        - 2 * vision_light_mount_strip_pocket_clearance,
        plate_depth
        - 2 * vision_light_mount_plate_border
        - 2 * vision_light_mount_strip_pocket_clearance,
        500,
    )
    downholder_border_cutter = align(
        downholder_border_cutter, strip_downholder, Alignment.CENTER
    )

    downholder_border_cutter = downholder_border_cutter.cutters[0]

    downholder_border_cutter_shaver = create_box(BIG_THING, BIG_THING, BIG_THING)

    downholder_border_cutter_shaver = align(
        downholder_border_cutter_shaver, cover_plate, Alignment.CENTER
    )
    downholder_border_cutter_shaver = align(
        downholder_border_cutter_shaver, cover_plate, Alignment.BOTTOM
    )
    downholder_border_cutter = downholder_border_cutter.cut(
        downholder_border_cutter_shaver
    )

    strip_downholder = strip_downholder.cut(downholder_border_cutter)

    strip_downholder_inner_cutter = materialize_bounding_box(
        aperture,
        x_enlargement=2 * vision_light_mount_strip_gap,
        y_enlargement=2 * vision_light_mount_strip_gap,
        z_enlargement=500,
    )

    strip_downholder_inner_cutter = align(
        strip_downholder_inner_cutter, cover_plate, Alignment.STACK_BOTTOM
    )
    strip_downholder = strip_downholder.cut(strip_downholder_inner_cutter)

    cover_inner_walls = materialize_bounding_box(
        aperture,
        x_enlargement=2 * vision_light_mount_strip_gap
        - 2 * vision_light_mount_strip_pocket_clearance,
        y_enlargement=2 * vision_light_mount_strip_gap
        - 2 * vision_light_mount_strip_pocket_clearance,
        z_enlargement=-400,
    )
    cover_inner_walls = align(cover_inner_walls, cover_plate, Alignment.STACK_BOTTOM)
    cover_inner_walls = cover_inner_walls.cut(aperture)
    cover_inner_wall_bottom_shaver = create_box(BIG_THING, BIG_THING, BIG_THING)
    cover_inner_wall_bottom_shaver = align(
        cover_inner_wall_bottom_shaver, cover_plate, Alignment.CENTER
    )
    cover_inner_wall_bottom_shaver = align(
        cover_inner_wall_bottom_shaver, plate, Alignment.TOP
    )
    cover_inner_wall_bottom_shaver = translate(0, 0, 1)(cover_inner_wall_bottom_shaver)
    cover_inner_walls = cover_inner_walls.cut(cover_inner_wall_bottom_shaver)

    outer_walls_z_thickness = get_bounding_box_size(cover_inner_walls)[2]
    cover_outer_walls = create_filleted_box(
        plate_width,
        plate_depth,
        outer_walls_z_thickness,
        fillet_radius=vision_light_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    cover_outer_walls_thickness = 1.3
    cover_outer_walls_inner_cutter = materialize_bounding_box(
        cover_outer_walls,
        x_enlargement=-2 * cover_outer_walls_thickness,
        y_enlargement=-2 * cover_outer_walls_thickness,
        z_enlargement=100,
    )
    cover_outer_walls = cover_outer_walls.cut(cover_outer_walls_inner_cutter)
    cover_outer_walls = align(cover_outer_walls, cover_plate, Alignment.CENTER)
    cover_outer_walls = align(cover_outer_walls, cover_inner_walls, Alignment.BOTTOM)
    cover_inner_walls = cover_inner_walls.fuse(cover_outer_walls)

    cover_inner_walls = cover_inner_walls.cut(connecctor_cutters)

    for strip in strip_leaders.values():
        strip_cutter = materialize_bounding_box(
            strip,
            x_enlargement=2 * vision_light_mount_strip_pocket_clearance,
            y_enlargement=2 * vision_light_mount_strip_pocket_clearance,
            z_enlargement=500,
        )
        cover_plate = cover_plate.cut(strip_cutter)
        cover_inner_walls = cover_inner_walls.cut(strip_cutter)

    cover = cover_plate.fuse(strip_downholder)

    cover = cover.cut(aperture)

    cover_screw_target_height = get_bounding_box_size(cover)[2]
    cover_mount_clearance_holes = PartCollector()
    cover_mount_cylinder_head_cutters = PartCollector()
    cover_mount_self_threading_holes = PartCollector()
    cover_screw_mounts = None

    edge_map = {
        (Alignment.LEFT, Alignment.FRONT): Alignment.EDGE_LEFT,
        (Alignment.LEFT, Alignment.BACK): Alignment.EDGE_BACK,
        (Alignment.RIGHT, Alignment.FRONT): Alignment.EDGE_RIGHT,
        (Alignment.RIGHT, Alignment.BACK): Alignment.EDGE_FRONT,
    }
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:

            for i in [0, 1]:

                target = create_cylinder(1, cover_screw_target_height)
                target = align(target, cover_plate, Alignment.CENTER)
                target = align(target, cover_plate, lr.edge_alignment)
                target = align(target, cover_plate, fb.edge_alignment)
                target = translate(
                    -lr.sign * cover_screw_inset,
                    -fb.sign * cover_screw_inset,
                    0,
                )(target)

                # if i == 1, then we "rotate"  to the center of the edge in the clockwise direction, so that we additionally have a screw on the edge center

                if i == 1:
                    edge = edge_map[(lr, fb)]

                    target = align(target, cover_plate, Alignment.CENTER)
                    target = align(target, cover_plate, edge)
                    translate_vector = np.array(
                        [1 if edge.axis == i else 0 for i in range(3)]
                    ) * (cover_screw_inset * -edge.sign)

                    target = translate(*translate_vector)(target)

                target = align(target, cover_plate, Alignment.TOP)

                mount_screw_assembly = create_screw_mount_assembly(
                    target,
                    screw_size=cover_screw_size,
                    screw_length=cover_screw_length,
                    screw_direction=Alignment.TOP,
                    with_nut_cutter=False,
                    flush_with_top=True,
                    cylinder_head_cutter_clearance=cover_screw_cylinder_head_clearance,
                    clearance_type="loose",
                )
                cover_mount_clearance_holes = cover_mount_clearance_holes.fuse(
                    mount_screw_assembly.get_named_cutter("hole_cutter")
                )
                cover_mount_cylinder_head_cutters = (
                    cover_mount_cylinder_head_cutters.fuse(
                        mount_screw_assembly.get_named_cutter("cylinder_head_cutter")
                    )
                )
                mount_screw_assembly = mount_screw_assembly.prefixed_copy(
                    f"cover_{lr.name.lower()}_{fb.name.lower()}_{'edge' if i == 0 else 'center'}_"
                )
                cover_screw_mounts = (
                    mount_screw_assembly
                    if cover_screw_mounts is None
                    else cover_screw_mounts.fuse(mount_screw_assembly)
                )

                self_threading_hole = create_self_threading_hole_cutter(
                    cover_screw_size,
                    vision_light_mount_plate_thickness + 2,
                    lead_in=True,
                )
                self_threading_hole = align(
                    self_threading_hole,
                    target,
                    Alignment.CENTER,
                    axes=[0, 1],
                )
                self_threading_hole = align(self_threading_hole, plate, Alignment.TOP)
                cover_mount_self_threading_holes = (
                    cover_mount_self_threading_holes.fuse(self_threading_hole)
                )

    cover = cover.fuse(cover_inner_walls)

    cover = cover.cut(cover_mount_clearance_holes)
    cover = cover.cut(cover_mount_cylinder_head_cutters)
    cover = cover.cut(pin_cutters)

    leader = leader.cut(cover_mount_self_threading_holes)

    clamp_screw_holes = PartCollector()
    for _name, cutter in screw_mounts.get_named_cutter_items():
        clamp_screw_holes = clamp_screw_holes.fuse(cutter)

    clamp_screws = PartCollector()
    clamp_nuts = PartCollector()
    for name, part in screw_mounts.get_named_non_production_part_items():
        if name.endswith("_screw"):
            clamp_screws = clamp_screws.fuse(part)
        elif name.endswith("_nut"):
            clamp_nuts = clamp_nuts.fuse(part)

    cover_mount_screws = PartCollector()
    for name, part in cover_screw_mounts.get_named_non_production_part_items():
        if name.endswith("_screw"):
            cover_mount_screws = cover_mount_screws.fuse(part)

    assembly = LeaderFollowersCuttersPart(leader)
    assembly.add_named_cutter(aperture, "aperture")
    assembly.add_named_cutter(strip_pockets, "strip_pockets")
    assembly.add_named_cutter(front_spar_keepout, "front_spar_keepout")
    assembly.add_named_cutter(clamp_screw_holes, "clamp_screw_holes")
    assembly.add_named_cutter(
        cover_mount_clearance_holes,
        "cover_mount_clearance_holes",
    )
    assembly.add_named_cutter(
        cover_mount_cylinder_head_cutters,
        "cover_mount_cylinder_head_cutters",
    )
    assembly.add_named_cutter(
        cover_mount_self_threading_holes,
        "cover_mount_self_threading_holes",
    )
    assembly.add_named_non_production_part(clamp_screws, "clamp_screws")
    assembly.add_named_non_production_part(clamp_nuts, "clamp_nuts")
    assembly.add_named_non_production_part(cover_mount_screws, "cover_mount_screws")
    assembly.add_named_follower(cover, "cover")
    for name, part in connector_visual_parts:
        assembly.add_named_non_production_part(part, name)
    for name, part in additional_pins_visual_parts:
        assembly.add_named_non_production_part(part, name)

    return assembly
