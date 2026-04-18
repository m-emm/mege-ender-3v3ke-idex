"""Declarative nitehawk holder assembly."""

from shellforgepy.simple import *


def _align_holder_to_extruder(
    holder,
    extruder,
    *,
    nitehawk_holder_extruder_gap,
    nitehawk_holder_width_offset,
    nitehawk_holder_height_offset,
):
    nitehawk_pcb = holder.get_named_non_production_part("nitehawk_pcb")
    board_aligner = align_translation(nitehawk_pcb, extruder, Alignment.LEFT)
    holder = board_aligner(holder)
    holder = align(
        holder,
        extruder,
        Alignment.STACK_BACK,
        stack_gap=nitehawk_holder_extruder_gap,
    )
    holder = align(holder, extruder, Alignment.BOTTOM)
    holder = translate(
        nitehawk_holder_width_offset,
        nitehawk_holder_height_offset,
        0,
    )(holder)
    return holder


def _create_nitehawk_board(
    *,
    nitehawk_width,
    nitehawk_height,
    nitehawk_pcb_thickness,
    nitehawk_hole_diameter,
    nitehawk_holes_center_distance,
    nitehawk_holes_y_offset,
    nitehawk_top_width,
    nitehawk_plug_width,
    nitehawk_plug_length,
    nitehawk_plug_thickness,
    nitehawk_plug_overhang,
    nitehawk_umbilical_connector_height,
    nitehawk_umbilical_connector_gap,
    nitehawk_umbilical_connector_cable_connector_end_diameter,
    nitehawk_umbilical_connector_cable_connector_height,
    nitehawk_umbilical_cable_diameter,
    nitehawk_umbilical_cable_length,
    nitehawk_heater_connector_width,
    nitehawk_heater_connector_length,
    nitehawk_heater_connector_thickness,
    nitehawk_heater_connector_x_offset_from_right,
    nitehawk_heater_connector_y_offset_from_front,
    nitehawk_front_cutter_width,
    nitehawk_front_cutter_back_width,
    nitehawk_front_cutter_y_size,
    big_thing,
):
    pcb = create_box(nitehawk_width, nitehawk_height, nitehawk_pcb_thickness)
    pcb = align(pcb, None, Alignment.CENTER)
    pcb_bbox = get_bounding_box(pcb)
    pcb = translate(0, -pcb_bbox[0][1], -pcb_bbox[0][2] / 2)(pcb)

    hole_cutters = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(nitehawk_hole_diameter / 2, nitehawk_pcb_thickness + 2)
        hole = align(hole, pcb, Alignment.CENTER)
        hole = align(hole, pcb, Alignment.FRONT)
        hole = translate(
            lr.sign * nitehawk_holes_center_distance / 2,
            nitehawk_holes_y_offset,
            0,
        )(hole)

        pcb = pcb.cut(hole)
        hole_cutters.append(hole)

        side_cutter = create_box(big_thing, big_thing, big_thing)
        side_cutter = align(side_cutter, None, Alignment.CENTER)
        side_cutter = translate(0, big_thing / 2, 0)(side_cutter)
        side_cutter = rotate(-lr.sign * 45)(side_cutter)
        side_cutter = translate(lr.sign * nitehawk_top_width / 2, nitehawk_height, 0)(
            side_cutter
        )
        pcb = pcb.cut(side_cutter)

    plug = create_box(
        nitehawk_plug_width,
        nitehawk_plug_length,
        nitehawk_plug_thickness,
    )
    plug = align(plug, pcb, Alignment.CENTER)
    plug = align(plug, pcb, Alignment.BACK)
    plug = align(plug, pcb, Alignment.STACK_TOP)
    plug = translate(0, nitehawk_plug_overhang, 0)(plug)

    umbilical_connector = create_box(
        nitehawk_plug_width,
        nitehawk_umbilical_connector_height,
        nitehawk_plug_thickness,
    )
    umbilical_connector = align(umbilical_connector, plug, Alignment.CENTER)
    umbilical_connector = align(
        umbilical_connector,
        plug,
        Alignment.STACK_BACK,
        stack_gap=nitehawk_umbilical_connector_gap,
    )
    plug = plug.fuse(umbilical_connector)

    umbilical_cable_connector = create_pyramid_stump(
        nitehawk_plug_width,
        nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_plug_thickness,
        nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_umbilical_connector_cable_connector_height,
    )
    umbilical_cable_connector = rotate(-90, axis=(1, 0, 0))(umbilical_cable_connector)
    umbilical_cable_connector = align(
        umbilical_cable_connector,
        umbilical_connector,
        Alignment.CENTER,
    )
    umbilical_cable_connector = align(
        umbilical_cable_connector,
        umbilical_connector,
        Alignment.STACK_BACK,
    )
    plug = plug.fuse(umbilical_cable_connector)

    cable = create_cylinder(
        nitehawk_umbilical_cable_diameter / 2,
        nitehawk_umbilical_cable_length,
        direction=(0, 1, 0),
    )
    cable = align(cable, umbilical_cable_connector, Alignment.CENTER)
    cable = align(cable, umbilical_cable_connector, Alignment.STACK_BACK)
    plug = plug.fuse(cable)

    heater_connector = create_box(
        nitehawk_heater_connector_width,
        nitehawk_heater_connector_length,
        nitehawk_heater_connector_thickness,
    )
    heater_connector = align(heater_connector, pcb, Alignment.RIGHT)
    heater_connector = align(heater_connector, pcb, Alignment.FRONT)
    heater_connector = align(heater_connector, pcb, Alignment.STACK_TOP)
    heater_connector = translate(
        -nitehawk_heater_connector_x_offset_from_right,
        nitehawk_heater_connector_y_offset_from_front,
        0,
    )(heater_connector)

    front_right_cutter = create_box(big_thing, big_thing, big_thing)
    front_right_cutter = align(front_right_cutter, None, Alignment.CENTER)
    front_right_cutter = align(
        front_right_cutter,
        pcb,
        Alignment.STACK_RIGHT,
        stack_gap=-(nitehawk_front_cutter_width - nitehawk_front_cutter_back_width),
    )
    front_right_cutter = align(
        front_right_cutter,
        pcb,
        Alignment.STACK_FRONT,
        stack_gap=-nitehawk_front_cutter_y_size,
    )

    front_cutter = create_right_triangle(
        nitehawk_front_cutter_back_width,
        nitehawk_front_cutter_y_size,
        big_thing,
        extrusion_direction=(0, 0, 1),
        a_normal=(1, 0, 0),
        b_normal=(0, 1, 0),
    )
    front_cutter = align(front_cutter, pcb, Alignment.CENTER)
    front_cutter = align(front_cutter, pcb, Alignment.FRONT)
    front_cutter = align(front_cutter, front_right_cutter, Alignment.STACK_LEFT)
    front_cutter = front_cutter.fuse(front_right_cutter)

    pcb = pcb.cut(front_cutter)
    pcb = pcb.cut(mirror(normal=(1, 0, 0), point=(0, 0, 0))(front_cutter))

    board = LeaderFollowersCuttersPart(pcb)
    board.add_named_follower(pcb, "pcb")
    board = board.fuse(plug)
    board = board.fuse(heater_connector)
    board.add_named_cutter(hole_cutters[0], "hole_1")
    board.add_named_cutter(hole_cutters[1], "hole_2")

    return board


def create_nitehawk_holder_assembly(
    *,
    sprite_extruder,
    nitehawk_board_angle,
    nitehawk_front_cutter_back_width,
    nitehawk_front_cutter_width,
    nitehawk_front_cutter_y_size,
    nitehawk_heater_connector_length,
    nitehawk_heater_connector_thickness,
    nitehawk_heater_connector_width,
    nitehawk_heater_connector_x_offset_from_right,
    nitehawk_heater_connector_y_offset_from_front,
    nitehawk_height,
    nitehawk_holder_cable_attachment_fillet_radius,
    nitehawk_holder_cable_attachment_holes_diameter,
    nitehawk_holder_cable_attachment_length,
    nitehawk_holder_cable_attachment_num_holes,
    nitehawk_holder_cable_attachment_thickness,
    nitehawk_holder_cable_attachment_width,
    nitehawk_holder_cable_attachment_y_offset,
    nitehawk_holder_fillet_radius,
    nitehawk_holder_height,
    nitehawk_holder_mount_screw_size,
    nitehawk_holder_mount_tower_diameter,
    nitehawk_holder_mount_tower_height,
    nitehawk_holder_mount_tower_x_offset,
    nitehawk_holder_mount_tower_y_offset,
    nitehawk_holder_slit_height,
    nitehawk_holder_thickness,
    nitehawk_holder_width,
    nitehawk_hole_diameter,
    nitehawk_holes_center_distance,
    nitehawk_holes_y_offset,
    nitehawk_mount_tower_base_extension,
    nitehawk_nut_cutter_slack,
    nitehawk_pcb_thickness,
    nitehawk_plug_length,
    nitehawk_plug_overhang,
    nitehawk_plug_thickness,
    nitehawk_plug_width,
    nitehawk_top_width,
    nitehawk_umbilical_cable_diameter,
    nitehawk_umbilical_cable_length,
    nitehawk_umbilical_connector_cable_connector_end_diameter,
    nitehawk_umbilical_connector_cable_connector_height,
    nitehawk_umbilical_connector_gap,
    nitehawk_umbilical_connector_height,
    nitehawk_width,
    nitehawk_holder_extruder_gap,
    nitehawk_holder_width_offset,
    nitehawk_holder_height_offset,
    BIG_THING,
):
    """Create the standalone nitehawk holder assembly."""

    big_thing = BIG_THING

    mount_tower_1 = create_cone(
        nitehawk_holder_mount_tower_diameter / 2 + nitehawk_mount_tower_base_extension,
        nitehawk_holder_mount_tower_diameter / 2,
        nitehawk_holder_mount_tower_height + nitehawk_holder_thickness,
    )
    mount_tower_2 = translate(nitehawk_holes_center_distance, 0, 0)(mount_tower_1)
    mount_towers = LeaderFollowersCuttersPart(mount_tower_1.fuse(mount_tower_2))

    cable_attachment = create_filleted_box(
        nitehawk_holder_cable_attachment_width,
        nitehawk_holder_cable_attachment_length,
        nitehawk_holder_cable_attachment_thickness,
        fillet_radius=nitehawk_holder_cable_attachment_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.FRONT],
    )

    cable_attachment_hole_cutters = PartCollector()
    for i in range(nitehawk_holder_cable_attachment_num_holes):
        for lr in [Alignment.LEFT, Alignment.RIGHT]:
            hole_cutter = create_cylinder(
                nitehawk_holder_cable_attachment_holes_diameter / 2,
                big_thing,
            )
            hole_cutter = align(hole_cutter, cable_attachment, Alignment.CENTER)
            hole_cutter = align(
                hole_cutter,
                cable_attachment,
                lr.stack_alignment,
                stack_gap=-1.5 * nitehawk_holder_cable_attachment_holes_diameter,
            )
            hole_cutter = translate(
                0,
                i
                * (
                    nitehawk_holder_cable_attachment_length
                    / (nitehawk_holder_cable_attachment_num_holes + 1)
                ),
                0,
            )(hole_cutter)
            cable_attachment_hole_cutters = cable_attachment_hole_cutters.fuse(
                hole_cutter
            )

    cable_attachment_hole_cutters = align(
        cable_attachment_hole_cutters,
        cable_attachment,
        Alignment.CENTER,
        axes=[0, 1],
    )
    cable_attachment = cable_attachment.cut(cable_attachment_hole_cutters)
    cable_attachment = align(cable_attachment, mount_towers, Alignment.CENTER)
    cable_attachment = align(cable_attachment, mount_towers, Alignment.BOTTOM)
    cable_attachment = align(cable_attachment, mount_towers, Alignment.FRONT)
    cable_attachment = translate(
        0,
        nitehawk_holder_cable_attachment_y_offset,
        0,
    )(cable_attachment)

    cable_attachment_bevel = create_right_triangle(
        nitehawk_holder_cable_attachment_thickness,
        nitehawk_holder_cable_attachment_thickness,
        nitehawk_holder_cable_attachment_width,
        extrusion_direction=(1, 0, 0),
        a_normal=(0, 0, -1),
        b_normal=(0, -1, 0),
    )
    cable_attachment_bevel = align(
        cable_attachment_bevel,
        cable_attachment,
        Alignment.CENTER,
    )
    cable_attachment_bevel = align(
        cable_attachment_bevel,
        cable_attachment,
        Alignment.STACK_FRONT,
    )
    cable_attachment_bevel = align(
        cable_attachment_bevel, cable_attachment, Alignment.TOP
    )
    cable_attachment = cable_attachment.fuse(cable_attachment_bevel)

    mount_towers.add_named_follower(cable_attachment, "cable_attachment")

    screw_hole_cutter_1 = create_cylinder(
        MScrew.from_size(nitehawk_holder_mount_screw_size).clearance_hole_normal / 2,
        big_thing,
    )
    screw_hole_cutter_1 = align(screw_hole_cutter_1, mount_tower_1, Alignment.CENTER)

    nut_cutter = create_nut(
        nitehawk_holder_mount_screw_size,
        slack=nitehawk_nut_cutter_slack,
    )
    nut_cutter = align(nut_cutter, screw_hole_cutter_1, Alignment.CENTER)
    nut_cutter = align(nut_cutter, mount_tower_1, Alignment.BOTTOM)
    screw_hole_cutter_1 = screw_hole_cutter_1.fuse(nut_cutter)

    mount_towers.add_named_cutter(screw_hole_cutter_1, "screw_hole_cutter_1")

    screw_hole_cutter_2 = align(screw_hole_cutter_1, mount_tower_2, Alignment.CENTER)
    mount_towers.add_named_cutter(screw_hole_cutter_2, "screw_hole_cutter_2")
    mount_towers = rotate(nitehawk_board_angle)(mount_towers)

    holder = create_filleted_box(
        nitehawk_holder_width,
        nitehawk_holder_height,
        nitehawk_holder_thickness,
        fillet_radius=nitehawk_holder_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    holder_front_cutter = create_pyramid_stump(
        nitehawk_holder_width - 4 * nitehawk_holder_slit_height,
        nitehawk_holder_width - 8 * nitehawk_holder_slit_height,
        nitehawk_holder_thickness + 2,
        nitehawk_holder_thickness + 2,
        nitehawk_holder_slit_height,
    )
    holder_front_cutter = rotate(-90, axis=(1, 0, 0))(holder_front_cutter)
    holder_front_cutter = align(holder_front_cutter, holder, Alignment.CENTER)
    holder_front_cutter = align(holder_front_cutter, holder, Alignment.FRONT)
    holder = holder.cut(holder_front_cutter)

    mount_towers = align(mount_towers, holder, Alignment.CENTER)
    mount_towers = align(mount_towers, holder, Alignment.BOTTOM)
    mount_towers = translate(
        nitehawk_holder_mount_tower_x_offset,
        nitehawk_holder_mount_tower_y_offset,
        0,
    )(mount_towers)

    holder = holder.fuse(mount_towers.leader)
    holder = LeaderFollowersCuttersPart(holder)
    holder = mount_towers.use_as_cutter_on(holder)
    holder.add_named_follower(
        mount_towers.get_named_follower("cable_attachment"),
        "cable_attachment",
    )
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_1"),
        "screw_hole_cutter_1",
    )
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_2"),
        "screw_hole_cutter_2",
    )
    holder = holder.fuse(holder.get_named_follower("cable_attachment"))

    holder_screw_hole_cutter_1 = holder.get_named_cutter("screw_hole_cutter_1")

    nitehawk_board = _create_nitehawk_board(
        nitehawk_width=nitehawk_width,
        nitehawk_height=nitehawk_height,
        nitehawk_pcb_thickness=nitehawk_pcb_thickness,
        nitehawk_hole_diameter=nitehawk_hole_diameter,
        nitehawk_holes_center_distance=nitehawk_holes_center_distance,
        nitehawk_holes_y_offset=nitehawk_holes_y_offset,
        nitehawk_top_width=nitehawk_top_width,
        nitehawk_plug_width=nitehawk_plug_width,
        nitehawk_plug_length=nitehawk_plug_length,
        nitehawk_plug_thickness=nitehawk_plug_thickness,
        nitehawk_plug_overhang=nitehawk_plug_overhang,
        nitehawk_umbilical_connector_height=nitehawk_umbilical_connector_height,
        nitehawk_umbilical_connector_gap=nitehawk_umbilical_connector_gap,
        nitehawk_umbilical_connector_cable_connector_end_diameter=nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_umbilical_connector_cable_connector_height=nitehawk_umbilical_connector_cable_connector_height,
        nitehawk_umbilical_cable_diameter=nitehawk_umbilical_cable_diameter,
        nitehawk_umbilical_cable_length=nitehawk_umbilical_cable_length,
        nitehawk_heater_connector_width=nitehawk_heater_connector_width,
        nitehawk_heater_connector_length=nitehawk_heater_connector_length,
        nitehawk_heater_connector_thickness=nitehawk_heater_connector_thickness,
        nitehawk_heater_connector_x_offset_from_right=nitehawk_heater_connector_x_offset_from_right,
        nitehawk_heater_connector_y_offset_from_front=nitehawk_heater_connector_y_offset_from_front,
        nitehawk_front_cutter_width=nitehawk_front_cutter_width,
        nitehawk_front_cutter_back_width=nitehawk_front_cutter_back_width,
        nitehawk_front_cutter_y_size=nitehawk_front_cutter_y_size,
        big_thing=big_thing,
    )
    nitehawk_board = rotate(nitehawk_board_angle)(nitehawk_board)
    nitehawk_pcb = nitehawk_board.get_named_follower("pcb")

    board_alignment = align_translation(
        nitehawk_pcb,
        holder,
        Alignment.STACK_TOP,
        stack_gap=0.0,
    )
    nitehawk_board = board_alignment(nitehawk_board)

    board_hole_1 = nitehawk_board.get_named_cutter("hole_1")
    align_board_translation = align_translation(
        board_hole_1,
        holder_screw_hole_cutter_1,
        Alignment.CENTER,
        axes=[0, 1],
    )
    nitehawk_board = align_board_translation(nitehawk_board)

    holder.add_named_non_production_part(nitehawk_board.leader, "nitehawk_board")
    holder.add_named_non_production_part(
        nitehawk_board.get_named_follower("pcb"),
        "nitehawk_pcb",
    )

    holder = rotate(-90, axis=(1, 0, 0))(holder)
    holder = rotate(180, axis=(0, 1, 0))(holder)

    holder = _align_holder_to_extruder(
        holder,
        sprite_extruder,
        nitehawk_holder_extruder_gap=nitehawk_holder_extruder_gap,
        nitehawk_holder_width_offset=nitehawk_holder_width_offset,
        nitehawk_holder_height_offset=nitehawk_holder_height_offset,
    )
    return holder
