"""Cooleon 24 V PSU reference mock assembly."""

from shellforgepy.simple import *


def create_cooleon_psu_assembly(
    *,
    cooleon_psu_length,
    cooleon_psu_width,
    cooleon_psu_thickness,
    cooleon_psu_base_plate_thickness,
    cooleon_psu_side_wall_width,
    cooleon_psu_terminal_block_length,
    cooleon_psu_terminal_block_width,
    cooleon_psu_terminal_block_height,
    cooleon_psu_mount_slot_length,
    cooleon_psu_mount_slot_width,
    cooleon_psu_mount_slot_side_inset,
):

    mount_screw_size = "M3"
    mount_screw_length = 10
    base_plate = create_box(
        cooleon_psu_length,
        cooleon_psu_width,
        cooleon_psu_base_plate_thickness,
    )

    mount_screws = []

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        fb = [
            a
            for a in Alignment.__members__.values()
            if a.axis == 1 and a.sign == -lr.sign
        ][0]

        mount_slot_cutter = create_rounded_slab(
            cooleon_psu_mount_slot_length,
            cooleon_psu_mount_slot_width,
            100,
            cooleon_psu_mount_slot_width / 2,
        )

        mount_slot_cutter = align(mount_slot_cutter, base_plate, Alignment.CENTER)
        mount_slot_cutter = align(mount_slot_cutter, base_plate, fb)
        mount_slot_cutter = align(mount_slot_cutter, base_plate, lr)

        mount_slot_cutter = translate(
            lr.sign * cooleon_psu_mount_slot_width,
            -fb.sign * cooleon_psu_mount_slot_side_inset,
            0,
        )(mount_slot_cutter)

        base_plate = base_plate.cut(mount_slot_cutter)

        mount_screw = create_cylinder_screw(mount_screw_size, mount_screw_length)

        mount_screw = align(mount_screw, mount_slot_cutter, Alignment.CENTER)
        mount_screw = align(mount_screw, mount_slot_cutter, lr.opposite)
        mount_screw = align(
            mount_screw,
            base_plate,
            Alignment.STACK_BOTTOM,
            stack_gap=-MScrew.from_size(mount_screw_size).cylinder_head_height
            - cooleon_psu_base_plate_thickness,
        )
        mount_screws.append(mount_screw)

    body = create_box(
        cooleon_psu_length - 2 * cooleon_psu_thickness,
        cooleon_psu_width,
        cooleon_psu_thickness,
    )

    body = align(body, base_plate, Alignment.CENTER)
    body = align(body, base_plate, Alignment.BOTTOM)

    side_walls = PartCollector()
    for side_y in [Alignment.FRONT, Alignment.BACK]:
        side_wall_web = create_rounded_slab(
            cooleon_psu_length,
            cooleon_psu_thickness * 2,
            cooleon_psu_side_wall_width,
            round_radius=cooleon_psu_thickness,
        )
        side_wall_web = rotate(90, axis=(1, 0, 0))(side_wall_web)

        side_wall_web, _ = cut_in_two(side_wall_web, cut_normal=(0, 0, 1))
        side_wall_web = align(side_wall_web, body, Alignment.CENTER)
        side_wall_web = align(side_wall_web, body, Alignment.BOTTOM)

        side_wall_web = align(side_wall_web, body, side_y)

        side_walls = side_walls.fuse(side_wall_web)

    body = align(body, base_plate, Alignment.CENTER)
    body = align(body, base_plate, Alignment.BOTTOM)

    psu_body = base_plate.fuse(body).fuse(side_walls)

    input_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
    )

    input_terminal_block = align(input_terminal_block, base_plate, Alignment.CENTER)
    input_terminal_block = align(input_terminal_block, base_plate, Alignment.STACK_TOP)
    input_terminal_block = align(input_terminal_block, body, Alignment.STACK_RIGHT)
    output_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
    )
    output_terminal_block = align(output_terminal_block, base_plate, Alignment.CENTER)
    output_terminal_block = align(
        output_terminal_block, base_plate, Alignment.STACK_TOP
    )
    output_terminal_block = align(output_terminal_block, body, Alignment.STACK_LEFT)

    assembly = LeaderFollowersCuttersPart(leader=psu_body)

    assembly.add_named_non_production_part(input_terminal_block, "input_terminal_block")
    assembly.add_named_non_production_part(
        output_terminal_block,
        "output_terminal_block",
    )

    for i, mount_screw in enumerate(mount_screws):
        assembly.add_named_non_production_part(mount_screw, f"mount_screw_{i}")

    return assembly
