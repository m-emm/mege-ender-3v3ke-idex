"""Cooleon 24 V PSU reference mock assembly."""

from shellforgepy.simple import *


def create_cooleon_psu_assembly(
    *,
    cooleon_psu_length,
    cooleon_psu_width,
    cooleon_psu_thickness,
    cooleon_psu_corner_fillet_radius,
    cooleon_psu_base_plate_thickness,
    cooleon_psu_top_cover_side_inset,
    cooleon_psu_top_cover_height,
    cooleon_psu_side_wall_width,
    cooleon_psu_side_wall_height,
    cooleon_psu_side_wall_fillet_radius,
    cooleon_psu_end_flange_length,
    cooleon_psu_terminal_block_length,
    cooleon_psu_terminal_block_width,
    cooleon_psu_terminal_block_height,
    cooleon_psu_terminal_cover_height,
    cooleon_psu_terminal_cover_overhang,
    cooleon_psu_terminal_screw_diameter,
    cooleon_psu_terminal_screw_head_height,
    cooleon_psu_input_terminal_count,
    cooleon_psu_output_terminal_count,
    cooleon_psu_mount_slot_length,
    cooleon_psu_mount_slot_width,
    cooleon_psu_mount_slot_end_inset,
    cooleon_psu_mount_slot_side_inset,
):
    base_plate = create_box(
        cooleon_psu_length,
        cooleon_psu_width,
        cooleon_psu_base_plate_thickness,
    )

    body = create_box(
        cooleon_psu_length - 2 * cooleon_psu_terminal_block_length,
        cooleon_psu_width,
        cooleon_psu_top_cover_height,
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
    input_terminal_block = align(input_terminal_block, base_plate, Alignment.RIGHT)
    output_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
    )
    output_terminal_block = align(output_terminal_block, base_plate, Alignment.CENTER)
    output_terminal_block = align(
        output_terminal_block, base_plate, Alignment.STACK_TOP
    )
    output_terminal_block = align(output_terminal_block, base_plate, Alignment.LEFT)

    assembly = LeaderFollowersCuttersPart(leader=psu_body)

    assembly.add_named_non_production_part(input_terminal_block, "input_terminal_block")
    assembly.add_named_non_production_part(
        output_terminal_block,
        "output_terminal_block",
    )

    return assembly
