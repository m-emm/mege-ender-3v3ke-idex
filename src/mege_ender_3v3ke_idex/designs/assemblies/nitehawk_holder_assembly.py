"""Declarative nitehawk holder assembly."""

import copy

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


def create_nitehawk_holder_assembly(
    *,
    sprite_extruder,
    nitehawk_board,
    holder_mount_plate_depth,
    holder_mount_plate_left_extension,
    holder_mount_plate_size,
    holder_mount_plate_spacer,
    holder_mount_plate_thickness,
    holder_mount_plate_top_offset,
    nitehawk_board_angle,
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
    nitehawk_holes_center_distance,
    nitehawk_mount_tower_base_extension,
    nitehawk_nut_cutter_slack,
    nitehawk_holder_extruder_gap,
    nitehawk_holder_width_offset,
    nitehawk_holder_height_offset,
    tool_head_additional_mount_plate_clearance,
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
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_1"),
        "screw_hole_cutter_1",
    )
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_2"),
        "screw_hole_cutter_2",
    )
    holder = holder.fuse(mount_towers.get_named_follower("cable_attachment"))

    holder_screw_hole_cutter_1 = holder.get_named_cutter("screw_hole_cutter_1")

    nitehawk_board = copy.deepcopy(nitehawk_board)
    nitehawk_board = rotate(nitehawk_board_angle)(nitehawk_board)
    nitehawk_pcb = nitehawk_board.leader

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

    holder.add_named_non_production_part(nitehawk_board.leader, "nitehawk_pcb")
    for name, part in nitehawk_board.get_named_follower_items():
        if name == "pcb":
            continue
        holder.add_named_non_production_part(part, f"nitehawk_board_{name}")

    holder = rotate(-90, axis=(1, 0, 0))(holder)
    holder = rotate(180, axis=(0, 1, 0))(holder)

    holder = _align_holder_to_extruder(
        holder,
        sprite_extruder,
        nitehawk_holder_extruder_gap=nitehawk_holder_extruder_gap,
        nitehawk_holder_width_offset=nitehawk_holder_width_offset,
        nitehawk_holder_height_offset=nitehawk_holder_height_offset,
    )

    holder_mount_plates = PartCollector()
    holder_mount_plate = create_box(
        holder_mount_plate_thickness,
        holder_mount_plate_depth,
        holder_mount_plate_size,
    )

    mount_box = create_box(
        holder_mount_plate_spacer,
        holder_mount_plate_size,
        holder_mount_plate_size,
    )
    mount_box = align(mount_box, holder_mount_plate, Alignment.CENTER)
    mount_box = align(mount_box, sprite_extruder, Alignment.BACK)
    mount_box = align(mount_box, holder_mount_plate, Alignment.STACK_LEFT)
    holder_mount_plate = mount_box

    holder_mount_plate = align(holder_mount_plate, holder, Alignment.CENTER)
    holder_mount_plate = align(holder_mount_plate, sprite_extruder, Alignment.TOP)
    holder_mount_plate = align(
        holder_mount_plate,
        sprite_extruder,
        lr.stack_alignment,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    holder_mount_plate = align(holder_mount_plate, holder, Alignment.BACK)
    holder_mount_plate = translate(0, 0, -holder_mount_plate_top_offset)(
        holder_mount_plate
    )

    holder_bottom_gap = 4
    lower_holder_cutter = create_box(big_thing, big_thing, big_thing)
    lower_holder_cutter = align(
        lower_holder_cutter,
        holder.leader,
        Alignment.CENTER,
        axes=[0, 1],
    )
    lower_holder_cutter = align(
        lower_holder_cutter,
        sprite_extruder,
        Alignment.STACK_BOTTOM,
        stack_gap=-holder_bottom_gap,
    )
    holder = holder.cut(lower_holder_cutter)

    holder_mount_plates = create_filleted_box(
        3,
        12,
        10,
        fillet_radius=1,
        no_fillets_at=[Alignment.RIGHT, Alignment.LEFT, Alignment.BACK],
    )
    holder_mount_plates = align(holder_mount_plates, holder, Alignment.CENTER)
    holder_mount_plates = align(holder_mount_plates, holder, Alignment.STACK_FRONT)

    holder_mount_plates = align(
        holder_mount_plates, sprite_extruder, Alignment.STACK_RIGHT, stack_gap=0.5
    )
    holder_mount_plates = align(holder_mount_plates, holder, Alignment.BOTTOM)

    holder = holder.fuse(holder_mount_plates)

    for _, cutter in sprite_extruder.get_named_cutter_items():
        holder.leader = holder.leader.cut(cutter)
    return holder
