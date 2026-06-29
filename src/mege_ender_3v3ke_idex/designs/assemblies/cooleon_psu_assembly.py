"""Cooleon 24 V PSU reference mock assembly."""

from shellforgepy.simple import *


def create_cooleon_psu_assembly(
    *,
    cooleon_psu_length,
    cooleon_psu_width,
    cooleon_psu_thickness,
    cooleon_psu_corner_fillet_radius,
    cooleon_psu_end_flange_length,
    cooleon_psu_end_flange_lip_width,
    cooleon_psu_end_flange_lip_height,
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
    cooleon_psu_mount_slot_y_offset,
    cooleon_psu_top_vent_panel_length,
    cooleon_psu_top_vent_panel_width,
    cooleon_psu_top_vent_hole_radius,
    cooleon_psu_top_vent_x_spacing,
    cooleon_psu_top_vent_y_spacing,
    cooleon_psu_side_vent_length,
    cooleon_psu_side_vent_height,
    cooleon_psu_side_vent_x_spacing,
    cooleon_psu_label_plate_length,
    cooleon_psu_label_plate_width,
):
    body = create_filleted_box(
        cooleon_psu_length,
        cooleon_psu_width,
        cooleon_psu_thickness,
        fillet_radius=cooleon_psu_corner_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    terminal_well_width = (
        cooleon_psu_terminal_block_width + 2 * cooleon_psu_terminal_cover_overhang
    )
    terminal_well_depth = (
        cooleon_psu_terminal_block_height + cooleon_psu_terminal_cover_height + 1
    )
    terminal_y_origin = (cooleon_psu_width - terminal_well_width) / 2
    input_terminal_x = cooleon_psu_terminal_cover_overhang
    output_terminal_x = (
        cooleon_psu_length
        - cooleon_psu_terminal_block_length
        - cooleon_psu_terminal_cover_overhang
    )

    input_well = create_box(
        cooleon_psu_terminal_block_length + 2 * cooleon_psu_terminal_cover_overhang,
        terminal_well_width,
        terminal_well_depth,
        origin=(
            0,
            terminal_y_origin,
            cooleon_psu_thickness - terminal_well_depth + 0.2,
        ),
    )
    output_well = create_box(
        cooleon_psu_terminal_block_length + 2 * cooleon_psu_terminal_cover_overhang,
        terminal_well_width,
        terminal_well_depth,
        origin=(
            cooleon_psu_length
            - cooleon_psu_terminal_block_length
            - 2 * cooleon_psu_terminal_cover_overhang,
            terminal_y_origin,
            cooleon_psu_thickness - terminal_well_depth + 0.2,
        ),
    )
    body = body.cut(input_well).cut(output_well)

    slot_center_y = cooleon_psu_width / 2 + cooleon_psu_mount_slot_y_offset
    slot_straight_length = max(
        cooleon_psu_mount_slot_length - cooleon_psu_mount_slot_width,
        0.1,
    )
    mount_slot_visuals = []
    for slot_name, slot_center_x in [
        (
            "mount_slot_left",
            cooleon_psu_mount_slot_end_inset + cooleon_psu_mount_slot_length / 2,
        ),
        (
            "mount_slot_right",
            cooleon_psu_length
            - cooleon_psu_mount_slot_end_inset
            - cooleon_psu_mount_slot_length / 2,
        ),
    ]:
        slot_box = create_box(
            slot_straight_length,
            cooleon_psu_mount_slot_width,
            cooleon_psu_thickness + 2,
            origin=(
                slot_center_x - slot_straight_length / 2,
                slot_center_y - cooleon_psu_mount_slot_width / 2,
                -1,
            ),
        )
        slot_cap_left = create_cylinder(
            cooleon_psu_mount_slot_width / 2,
            cooleon_psu_thickness + 2,
            origin=(
                slot_center_x - slot_straight_length / 2,
                slot_center_y,
                -1,
            ),
        )
        slot_cap_right = create_cylinder(
            cooleon_psu_mount_slot_width / 2,
            cooleon_psu_thickness + 2,
            origin=(
                slot_center_x + slot_straight_length / 2,
                slot_center_y,
                -1,
            ),
        )
        slot_cutter = slot_box.fuse(slot_cap_left).fuse(slot_cap_right)
        body = body.cut(slot_cutter)

        slot_visual_box = create_box(
            slot_straight_length,
            cooleon_psu_mount_slot_width,
            0.15,
            origin=(
                slot_center_x - slot_straight_length / 2,
                slot_center_y - cooleon_psu_mount_slot_width / 2,
                cooleon_psu_thickness + 0.02,
            ),
        )
        slot_visual_cap_left = create_cylinder(
            cooleon_psu_mount_slot_width / 2,
            0.15,
            origin=(
                slot_center_x - slot_straight_length / 2,
                slot_center_y,
                cooleon_psu_thickness + 0.02,
            ),
        )
        slot_visual_cap_right = create_cylinder(
            cooleon_psu_mount_slot_width / 2,
            0.15,
            origin=(
                slot_center_x + slot_straight_length / 2,
                slot_center_y,
                cooleon_psu_thickness + 0.02,
            ),
        )
        slot_visual = slot_visual_box.fuse(slot_visual_cap_left).fuse(
            slot_visual_cap_right
        )
        mount_slot_visuals.append((slot_name, slot_visual, slot_cutter))

    side_flange_rails = PartCollector()
    for side_y in [0, cooleon_psu_width - cooleon_psu_end_flange_lip_width]:
        side_flange_rails = side_flange_rails.fuse(
            create_box(
                cooleon_psu_length,
                cooleon_psu_end_flange_lip_width,
                cooleon_psu_end_flange_lip_height,
                origin=(0, side_y, 0),
            )
        )

    end_flange_lines = PartCollector()
    for end_x in [
        cooleon_psu_end_flange_length,
        cooleon_psu_length - cooleon_psu_end_flange_length,
    ]:
        end_flange_lines = end_flange_lines.fuse(
            create_box(
                0.8,
                cooleon_psu_width,
                0.3,
                origin=(end_x - 0.4, 0, cooleon_psu_thickness + 0.02),
            )
        )

    input_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
        origin=(
            input_terminal_x,
            (cooleon_psu_width - cooleon_psu_terminal_block_width) / 2,
            cooleon_psu_thickness
            - cooleon_psu_terminal_block_height
            - cooleon_psu_terminal_cover_height,
        ),
    )
    output_terminal_block = create_box(
        cooleon_psu_terminal_block_length,
        cooleon_psu_terminal_block_width,
        cooleon_psu_terminal_block_height,
        origin=(
            output_terminal_x,
            (cooleon_psu_width - cooleon_psu_terminal_block_width) / 2,
            cooleon_psu_thickness
            - cooleon_psu_terminal_block_height
            - cooleon_psu_terminal_cover_height,
        ),
    )

    input_terminal_cover = create_box(
        cooleon_psu_terminal_block_length + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_block_width + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_cover_height,
        origin=(
            input_terminal_x - cooleon_psu_terminal_cover_overhang,
            (cooleon_psu_width - cooleon_psu_terminal_block_width) / 2
            - cooleon_psu_terminal_cover_overhang,
            cooleon_psu_thickness - cooleon_psu_terminal_cover_height,
        ),
    )
    output_terminal_cover = create_box(
        cooleon_psu_terminal_block_length + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_block_width + 2 * cooleon_psu_terminal_cover_overhang,
        cooleon_psu_terminal_cover_height,
        origin=(
            output_terminal_x - cooleon_psu_terminal_cover_overhang,
            (cooleon_psu_width - cooleon_psu_terminal_block_width) / 2
            - cooleon_psu_terminal_cover_overhang,
            cooleon_psu_thickness - cooleon_psu_terminal_cover_height,
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
            terminal_y = (cooleon_psu_width - cooleon_psu_terminal_block_width) / 2 + (
                terminal_index + 0.5
            ) * cooleon_psu_terminal_block_width / terminal_count
            terminal_screws = terminal_screws.fuse(
                create_cylinder(
                    cooleon_psu_terminal_screw_diameter / 2,
                    cooleon_psu_terminal_screw_head_height,
                    origin=(
                        terminal_x,
                        terminal_y,
                        cooleon_psu_thickness
                        - cooleon_psu_terminal_screw_head_height
                        + 0.03,
                    ),
                )
            )

    vent_panels = PartCollector()
    vent_x_count = int(
        cooleon_psu_top_vent_panel_length / cooleon_psu_top_vent_x_spacing
    )
    vent_y_count = int(
        cooleon_psu_top_vent_panel_width / cooleon_psu_top_vent_y_spacing
    )
    vent_start_x = (cooleon_psu_length - cooleon_psu_top_vent_panel_length) / 2
    vent_start_y = (cooleon_psu_width - cooleon_psu_top_vent_panel_width) / 2
    for vent_x_index in range(vent_x_count):
        for vent_y_index in range(vent_y_count):
            vent_x = vent_start_x + (vent_x_index + 0.5) * (
                cooleon_psu_top_vent_panel_length / vent_x_count
            )
            vent_y = vent_start_y + (vent_y_index + 0.5) * (
                cooleon_psu_top_vent_panel_width / vent_y_count
            )
            vent_panels = vent_panels.fuse(
                create_cylinder(
                    cooleon_psu_top_vent_hole_radius,
                    0.18,
                    origin=(vent_x, vent_y, cooleon_psu_thickness + 0.03),
                )
            )

    side_vent_x_count = int(
        cooleon_psu_top_vent_panel_length / cooleon_psu_side_vent_x_spacing
    )
    for side_y in [-0.08, cooleon_psu_width - 0.08]:
        for vent_x_index in range(side_vent_x_count):
            vent_x = vent_start_x + (vent_x_index + 0.5) * (
                cooleon_psu_top_vent_panel_length / side_vent_x_count
            )
            for vent_z in [5.2, 9.2]:
                vent_panels = vent_panels.fuse(
                    create_box(
                        cooleon_psu_side_vent_length,
                        0.16,
                        cooleon_psu_side_vent_height,
                        origin=(
                            vent_x - cooleon_psu_side_vent_length / 2,
                            side_y,
                            vent_z,
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
    for label_line_index in range(6):
        label_markings = label_markings.fuse(
            create_box(
                cooleon_psu_label_plate_length - 6,
                0.45,
                0.2,
                origin=(
                    cooleon_psu_end_flange_length + 8,
                    (cooleon_psu_width - cooleon_psu_label_plate_width) / 2
                    + 3
                    + label_line_index * 2.0,
                    cooleon_psu_thickness + 0.24,
                ),
            )
        )

    assembly = LeaderFollowersCuttersPart(leader=body)
    assembly.add_named_follower(body, "body")
    assembly.add_named_follower(side_flange_rails, "side_flange_rails")
    assembly.add_named_follower(end_flange_lines, "end_flange_lines")
    assembly.add_named_follower(input_terminal_block, "input_terminal_block")
    assembly.add_named_follower(output_terminal_block, "output_terminal_block")
    assembly.add_named_follower(input_terminal_cover, "input_terminal_cover")
    assembly.add_named_follower(output_terminal_cover, "output_terminal_cover")
    assembly.add_named_follower(terminal_screws, "terminal_screws")
    for slot_name, slot_visual, slot_cutter in mount_slot_visuals:
        assembly.add_named_follower(slot_visual, slot_name)
        assembly.add_named_cutter(slot_cutter, f"{slot_name}_cutter")
    assembly.add_named_follower(vent_panels, "vent_panels")
    assembly.add_named_follower(label_plate, "label_plate")
    assembly.add_named_follower(label_markings, "label_markings")

    return assembly
