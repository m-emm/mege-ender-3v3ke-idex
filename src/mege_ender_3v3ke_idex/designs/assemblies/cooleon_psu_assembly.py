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
    cooleon_psu_label_plate_length,
    cooleon_psu_label_plate_width,
):
    base_plate = create_box(
        cooleon_psu_length,
        cooleon_psu_width,
        cooleon_psu_base_plate_thickness,
    )

    slot_straight_length = max(
        cooleon_psu_mount_slot_length - cooleon_psu_mount_slot_width,
        0.1,
    )
    mount_slots = []
    for slot_name, slot_center_x, slot_center_y in [
        (
            "mount_slot_left_cutter",
            cooleon_psu_mount_slot_end_inset + cooleon_psu_mount_slot_length / 2,
            cooleon_psu_mount_slot_side_inset,
        ),
        (
            "mount_slot_right_cutter",
            cooleon_psu_length
            - cooleon_psu_mount_slot_end_inset
            - cooleon_psu_mount_slot_length / 2,
            cooleon_psu_width - cooleon_psu_mount_slot_side_inset,
        ),
    ]:
        slot_box = create_box(
            slot_straight_length,
            cooleon_psu_mount_slot_width,
            cooleon_psu_base_plate_thickness + 2,
            origin=(
                slot_center_x - slot_straight_length / 2,
                slot_center_y - cooleon_psu_mount_slot_width / 2,
                -1,
            ),
        )
        slot_cap_left = create_cylinder(
            cooleon_psu_mount_slot_width / 2,
            cooleon_psu_base_plate_thickness + 2,
            origin=(
                slot_center_x - slot_straight_length / 2,
                slot_center_y,
                -1,
            ),
        )
        slot_cap_right = create_cylinder(
            cooleon_psu_mount_slot_width / 2,
            cooleon_psu_base_plate_thickness + 2,
            origin=(
                slot_center_x + slot_straight_length / 2,
                slot_center_y,
                -1,
            ),
        )
        slot_cutter = slot_box.fuse(slot_cap_left).fuse(slot_cap_right)
        base_plate = base_plate.cut(slot_cutter)
        mount_slots.append((slot_name, slot_cutter))

    top_cover_width = cooleon_psu_width - 2 * cooleon_psu_top_cover_side_inset
    top_cover = create_filleted_box(
        cooleon_psu_length,
        top_cover_width,
        cooleon_psu_top_cover_height,
        fillet_radius=cooleon_psu_corner_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    top_cover = translate(
        0,
        cooleon_psu_top_cover_side_inset,
        cooleon_psu_thickness - cooleon_psu_top_cover_height,
    )(top_cover)

    side_walls = PartCollector()
    for side_y in [0, cooleon_psu_width - cooleon_psu_side_wall_width]:
        side_wall = create_filleted_box(
            cooleon_psu_length,
            cooleon_psu_side_wall_width,
            cooleon_psu_side_wall_height,
            fillet_radius=cooleon_psu_side_wall_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )
        side_wall = translate(0, side_y, 0)(side_wall)
        side_walls = side_walls.fuse(side_wall)

    end_flange_lines = PartCollector()
    for end_x in [
        cooleon_psu_end_flange_length,
        cooleon_psu_length - cooleon_psu_end_flange_length,
    ]:
        end_flange_lines = end_flange_lines.fuse(
            create_box(
                0.8,
                top_cover_width,
                0.3,
                origin=(
                    end_x - 0.4,
                    cooleon_psu_top_cover_side_inset,
                    cooleon_psu_thickness - 0.3,
                ),
            )
        )

    psu_body = base_plate.fuse(top_cover).fuse(side_walls).fuse(end_flange_lines)

    input_terminal_x = cooleon_psu_terminal_cover_overhang
    output_terminal_x = (
        cooleon_psu_length
        - cooleon_psu_terminal_block_length
        - cooleon_psu_terminal_cover_overhang
    )
    terminal_y = (cooleon_psu_width - cooleon_psu_terminal_block_width) / 2
    terminal_z = cooleon_psu_thickness

    input_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
        origin=(input_terminal_x, terminal_y, terminal_z),
    )
    output_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
        origin=(output_terminal_x, terminal_y, terminal_z),
    )

    input_terminal_cover = create_box(
        cooleon_psu_terminal_block_length + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_block_width + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_cover_height,
        origin=(
            input_terminal_x - cooleon_psu_terminal_cover_overhang,
            terminal_y - cooleon_psu_terminal_cover_overhang,
            terminal_z + cooleon_psu_terminal_block_height,
        ),
    )
    output_terminal_cover = create_box(
        cooleon_psu_terminal_block_length + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_block_width + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_cover_height,
        origin=(
            output_terminal_x - cooleon_psu_terminal_cover_overhang,
            terminal_y - cooleon_psu_terminal_cover_overhang,
            terminal_z + cooleon_psu_terminal_block_height,
        ),
    )

    terminal_screws = PartCollector()
    for terminal_x, terminal_count in [
        (
            input_terminal_x + cooleon_psu_terminal_block_length / 2,
            cooleon_psu_input_terminal_count,
        ),
        (
            output_terminal_x + cooleon_psu_terminal_block_length / 2,
            cooleon_psu_output_terminal_count,
        ),
    ]:
        for terminal_index in range(terminal_count):
            screw_y = terminal_y + (terminal_index + 0.5) * (
                cooleon_psu_terminal_block_width / terminal_count
            )
            terminal_screws = terminal_screws.fuse(
                create_cylinder(
                    cooleon_psu_terminal_screw_diameter / 2,
                    cooleon_psu_terminal_screw_head_height,
                    origin=(
                        terminal_x,
                        screw_y,
                        terminal_z
                        + cooleon_psu_terminal_block_height
                        + cooleon_psu_terminal_cover_height
                        - cooleon_psu_terminal_screw_head_height
                        + 0.03,
                    ),
                )
            )

    label_plate = create_box(
        cooleon_psu_label_plate_length,
        cooleon_psu_label_plate_width,
        0.18,
        origin=(
            cooleon_psu_end_flange_length + 5,
            (cooleon_psu_width - cooleon_psu_label_plate_width) / 2,
            cooleon_psu_thickness + 0.04,
        ),
    )

    label_markings = PartCollector()
    for label_line_index in range(5):
        label_markings = label_markings.fuse(
            create_box(
                cooleon_psu_label_plate_length - 6,
                0.45,
                0.2,
                origin=(
                    cooleon_psu_end_flange_length + 8,
                    (cooleon_psu_width - cooleon_psu_label_plate_width) / 2
                    + 3
                    + label_line_index * 2.2,
                    cooleon_psu_thickness + 0.24,
                ),
            )
        )

    assembly = LeaderFollowersCuttersPart(leader=psu_body)
    for slot_name, slot_cutter in mount_slots:
        assembly.add_named_cutter(slot_cutter, slot_name)
    assembly.add_named_non_production_part(input_terminal_block, "input_terminal_block")
    assembly.add_named_non_production_part(
        output_terminal_block,
        "output_terminal_block",
    )
    assembly.add_named_non_production_part(input_terminal_cover, "input_terminal_cover")
    assembly.add_named_non_production_part(
        output_terminal_cover,
        "output_terminal_cover",
    )
    assembly.add_named_non_production_part(terminal_screws, "terminal_screws")
    assembly.add_named_non_production_part(label_plate, "label_plate")
    assembly.add_named_non_production_part(label_markings, "label_markings")

    return assembly
