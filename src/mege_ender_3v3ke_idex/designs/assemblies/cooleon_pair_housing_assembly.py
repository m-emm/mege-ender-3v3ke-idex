"""Open-top housing with lid for a back-to-back Cooleon PSU pair."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.trellis_plate import create_trellis_cutters
from shellforgepy.simple import *


def create_cooleon_pair_housing_assembly(
    *,
    cooleon_psu_1,
    cooleon_psu_2,
    cooleon_pair_housing_clearance,
    cooleon_pair_housing_wall_thickness,
    cooleon_pair_housing_input_terminal_extra_space,
    cooleon_pair_housing_mount_rib_length,
    cooleon_pair_housing_mount_rib_thickness,
    cooleon_pair_housing_mount_rib_end_inset,
    cooleon_pair_housing_vent_diamond_size,
    cooleon_pair_housing_vent_pitch,
    cooleon_pair_housing_vent_end_inset,
    cooleon_pair_housing_vent_height,
    cooleon_pair_housing_vent_row_z,
    cooleon_pair_housing_lid_thickness,
    cooleon_pair_housing_lid_body_clearance,
    cooleon_pair_housing_lid_outer_overhang,
    cooleon_pair_housing_lid_rim_depth,
    cooleon_pair_housing_lid_rim_thickness,
    cooleon_pair_housing_lid_rim_clearance,
    cooleon_pair_housing_lid_screw_size,
    cooleon_pair_housing_lid_screw_length,
    cooleon_pair_housing_lid_screw_inset,
    cooleon_pair_housing_lid_screw_boss_diameter,
    cooleon_pair_housing_self_threading_core_radius_adjustment,
    cooleon_pair_housing_self_threading_lead_in,
    cooleon_pair_housing_input_cable_hole_diameter,
    cooleon_pair_housing_input_cable_clamp_hole_diameter,
    cooleon_pair_housing_input_cable_clamp_slit_width,
    cooleon_pair_housing_input_cable_clamp_arm_width,
    cooleon_pair_housing_input_cable_clamp_arm_depth,
    cooleon_pair_housing_input_cable_clamp_arm_thickness,
    cooleon_pair_housing_input_cable_clamp_clearance,
    cooleon_pair_housing_input_cable_clamp_screw_size,
    cooleon_pair_housing_input_cable_clamp_screw_length,
    cooleon_pair_housing_output_cable_hole_diameter,
    cooleon_pair_housing_psu_mount_thread_inset_extra_radius,
):
    """Create a lidded open-top tray around the placed Cooleon PSU bodies."""

    psu_pair_reference = cooleon_psu_1.leader.fuse(cooleon_psu_2.leader)
    psu_pair_bbox = get_bounding_box(psu_pair_reference)
    psu_pair_min, psu_pair_max = psu_pair_bbox
    psu_1_min, psu_1_max = get_bounding_box(cooleon_psu_1.leader)
    psu_2_min, psu_2_max = get_bounding_box(cooleon_psu_2.leader)

    inner_min_x = psu_pair_min[0] - cooleon_pair_housing_clearance
    inner_min_y = psu_pair_min[1] - cooleon_pair_housing_clearance
    inner_min_z = psu_pair_min[2] - cooleon_pair_housing_clearance
    inner_max_x = (
        psu_pair_max[0]
        + cooleon_pair_housing_clearance
        + cooleon_pair_housing_input_terminal_extra_space
    )
    inner_max_y = psu_pair_max[1] + cooleon_pair_housing_clearance
    inner_max_z = psu_pair_max[2] + cooleon_pair_housing_clearance

    wall_thickness = cooleon_pair_housing_wall_thickness
    outer_min_x = inner_min_x - wall_thickness
    outer_min_y = inner_min_y - wall_thickness
    outer_min_z = inner_min_z - wall_thickness
    outer_max_x = inner_max_x + wall_thickness
    outer_max_y = inner_max_y + wall_thickness
    outer_max_z = inner_max_z

    housing_box = create_box(
        outer_max_x - outer_min_x,
        outer_max_y - outer_min_y,
        outer_max_z - outer_min_z,
        origin=(outer_min_x, outer_min_y, outer_min_z),
    )

    inner_space_cutter = create_box(
        inner_max_x - inner_min_x,
        inner_max_y - inner_min_y,
        outer_max_z - inner_min_z + 1,
        origin=(inner_min_x, inner_min_y, inner_min_z),
    )
    housing_box = housing_box.cut(inner_space_cutter)

    mount_screw_parts = []
    for psu in [cooleon_psu_1, cooleon_psu_2]:
        for name in ["mount_screw_0", "mount_screw_1"]:
            mount_screw_parts.append(psu.get_non_production_part_by_name(name))
    mount_screw_items = sorted(
        [
            (get_bounding_box_center(mount_screw_part), mount_screw_part)
            for mount_screw_part in mount_screw_parts
        ],
        key=lambda item: item[0][0],
    )

    input_terminal_centers = [
        get_bounding_box_center(
            psu.get_non_production_part_by_name("input_terminal_block")
        )
        for psu in [cooleon_psu_1, cooleon_psu_2]
    ]
    output_terminal_centers = [
        get_bounding_box_center(
            psu.get_non_production_part_by_name("output_terminal_block")
        )
        for psu in [cooleon_psu_1, cooleon_psu_2]
    ]

    psu_y_faces = sorted([psu_1_min[1], psu_1_max[1], psu_2_min[1], psu_2_max[1]])
    psu_gap_center_y = (psu_y_faces[1] + psu_y_faces[2]) / 2
    rib_z_min = inner_min_z
    rib_height = outer_max_z - rib_z_min
    mount_screw_groups = [
        mount_screw_items[: len(mount_screw_items) // 2],
        mount_screw_items[len(mount_screw_items) // 2 :],
    ]
    separator_wall_targets = []
    separator_gap_target = create_box(
        psu_pair_max[0] - psu_pair_min[0],
        cooleon_pair_housing_mount_rib_thickness,
        rib_height,
        origin=(
            psu_pair_min[0],
            psu_gap_center_y - cooleon_pair_housing_mount_rib_thickness / 2,
            rib_z_min,
        ),
    )
    separator_walls = PartCollector()
    for wall_x_alignment, mount_screw_group in [
        (Alignment.LEFT, mount_screw_groups[0]),
        (Alignment.RIGHT, mount_screw_groups[1]),
    ]:
        separator_wall = create_box(
            cooleon_pair_housing_mount_rib_length,
            cooleon_pair_housing_mount_rib_thickness,
            rib_height,
        )
        separator_wall = align(
            separator_wall,
            separator_gap_target,
            Alignment.CENTER,
            axes=[1],
        )
        separator_wall = align(separator_wall, inner_space_cutter, Alignment.BOTTOM)
        separator_wall = align(separator_wall, psu_pair_reference, wall_x_alignment)
        separator_wall_targets.append((separator_wall, mount_screw_group))
        separator_walls = separator_walls.fuse(separator_wall)
    housing_box = housing_box.fuse(separator_walls)

    psu_mount_thread_insert_cutters = PartCollector()
    psu_mount_thread_insets = PartCollector()
    for separator_wall, mount_screw_group in separator_wall_targets:
        for mount_screw_center, mount_screw_part in mount_screw_group:
            screw_is_on_front_side = mount_screw_center[1] < psu_gap_center_y
            thread_inset_assembly = create_thread_inset_assembly(
                "M3",
                thickness=cooleon_pair_housing_mount_rib_thickness,
                extra_radius=cooleon_pair_housing_psu_mount_thread_inset_extra_radius,
                clearance_type="normal",
            )
            if screw_is_on_front_side:
                thread_inset_assembly = rotate(-90, axis=(1, 0, 0))(
                    thread_inset_assembly
                )
                thread_inset_assembly = align(
                    thread_inset_assembly,
                    separator_wall,
                    Alignment.FRONT,
                )
            else:
                thread_inset_assembly = rotate(90, axis=(1, 0, 0))(
                    thread_inset_assembly
                )
                thread_inset_assembly = align(
                    thread_inset_assembly,
                    separator_wall,
                    Alignment.BACK,
                )
            thread_inset_assembly = align(
                thread_inset_assembly,
                mount_screw_part,
                Alignment.CENTER,
                axes=[0, 2],
            )
            housing_box = thread_inset_assembly.use_as_cutter_on(housing_box)
            psu_mount_thread_insert_cutters = psu_mount_thread_insert_cutters.fuse(
                thread_inset_assembly.get_named_cutter("assembly_cutter")
            )
            psu_mount_thread_insets = psu_mount_thread_insets.fuse(
                thread_inset_assembly.get_named_non_production_part("thread_inset")
            )

    lid_screw_record = MScrew.from_size(cooleon_pair_housing_lid_screw_size)
    lid_screw_bosses = PartCollector()
    lid_pilot_holes = PartCollector()
    lid_clearance_holes = PartCollector()
    lid_screws = PartCollector()
    lid_bosses = []
    lid_screw_positions = []
    boss_radius = cooleon_pair_housing_lid_screw_boss_diameter / 2
    boss_height = outer_max_z - rib_z_min
    lid_z_min = outer_max_z + cooleon_pair_housing_lid_body_clearance
    lid_z_top = lid_z_min + cooleon_pair_housing_lid_thickness
    for x_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        for y_alignment in [Alignment.FRONT, Alignment.BACK]:
            x = (
                outer_min_x + cooleon_pair_housing_lid_screw_inset
                if x_alignment == Alignment.LEFT
                else outer_max_x - cooleon_pair_housing_lid_screw_inset
            )
            y = (
                outer_min_y + cooleon_pair_housing_lid_screw_inset
                if y_alignment == Alignment.FRONT
                else outer_max_y - cooleon_pair_housing_lid_screw_inset
            )
            lid_boss = create_cylinder(
                boss_radius,
                boss_height,
                origin=(x, y, rib_z_min),
            )
            lid_screw_bosses = lid_screw_bosses.fuse(lid_boss)
            lid_bosses.append(lid_boss)

            lid_pilot_hole = create_self_threading_hole_cutter(
                cooleon_pair_housing_lid_screw_size,
                boss_height + 2,
                core_radius_adjustment=(
                    cooleon_pair_housing_self_threading_core_radius_adjustment
                ),
                lead_in=cooleon_pair_housing_self_threading_lead_in,
            )
            lid_pilot_hole = align(lid_pilot_hole, lid_boss, Alignment.CENTER)
            lid_pilot_holes = lid_pilot_holes.fuse(lid_pilot_hole)

            lid_clearance_hole = create_cylinder(
                lid_screw_record.clearance_hole_loose / 2,
                cooleon_pair_housing_lid_thickness + 2,
                origin=(x, y, lid_z_min - 1),
            )
            lid_clearance_holes = lid_clearance_holes.fuse(lid_clearance_hole)
            lid_screw_positions.append((lid_pilot_hole, lid_clearance_hole))

            lid_screw = create_cylinder_screw(
                cooleon_pair_housing_lid_screw_size,
                cooleon_pair_housing_lid_screw_length,
            )
            lid_screw_target = create_box(
                lid_screw_record.cylinder_head_diameter,
                lid_screw_record.cylinder_head_diameter,
                cooleon_pair_housing_lid_thickness,
                origin=(
                    x - lid_screw_record.cylinder_head_diameter / 2,
                    y - lid_screw_record.cylinder_head_diameter / 2,
                    lid_z_min,
                ),
            )
            lid_screw = align(
                lid_screw, lid_screw_target, Alignment.CENTER, axes=[0, 1]
            )
            lid_screw = align(
                lid_screw,
                lid_screw_target,
                Alignment.STACK_TOP,
                stack_gap=-cooleon_pair_housing_lid_screw_length,
            )
            lid_screws = lid_screws.fuse(lid_screw)

    housing_box = housing_box.fuse(lid_screw_bosses)
    housing_box = housing_box.cut(lid_pilot_holes)

    vent_cutters = PartCollector()
    vent_panel_length = inner_max_x - inner_min_x
    vent_panel_height = cooleon_pair_housing_vent_height
    vent_panel_depth = wall_thickness + 4
    vent_center_z = (
        inner_min_z + (inner_max_z - inner_min_z) * cooleon_pair_housing_vent_row_z
    )
    vent_min_z = vent_center_z - vent_panel_height / 2
    vent_band_width = (
        cooleon_pair_housing_vent_pitch - cooleon_pair_housing_vent_diamond_size
    )
    for y_center in [
        outer_min_y + wall_thickness / 2,
        outer_max_y - wall_thickness / 2,
    ]:
        side_vent_cutters = create_trellis_cutters(
            length=vent_panel_length,
            width=vent_panel_height,
            thickness=vent_panel_depth,
            x_border_width=cooleon_pair_housing_vent_end_inset,
            y_border_width=vent_band_width,
            band_width=vent_band_width,
            band_pitch=cooleon_pair_housing_vent_pitch,
            cutter_depth=vent_panel_depth,
        )
        side_vent_cutters = rotate(
            -90,
            center=get_bounding_box_center(side_vent_cutters),
            axis=(1, 0, 0),
        )(side_vent_cutters)
        side_vent_target = create_box(
            vent_panel_length,
            vent_panel_depth,
            vent_panel_height,
            origin=(
                inner_min_x,
                y_center - vent_panel_depth / 2,
                vent_min_z,
            ),
        )
        side_vent_cutters = align(side_vent_cutters, side_vent_target, Alignment.CENTER)
        vent_cutters = vent_cutters.fuse(side_vent_cutters)
    housing_box = housing_box.cut(vent_cutters)

    input_cable_clamp_width = (
        cooleon_pair_housing_input_cable_clamp_hole_diameter
        + 2 * cooleon_pair_housing_input_cable_clamp_arm_width
    )
    input_cable_clamp_y_target = create_box(
        1,
        cooleon_pair_housing_input_cable_clamp_arm_depth,
        1,
        origin=(
            inner_max_x,
            sum(center[1] for center in input_terminal_centers)
            / len(input_terminal_centers)
            - cooleon_pair_housing_input_cable_clamp_arm_depth / 2,
            inner_min_z,
        ),
    )
    input_cable_clamp_x_target = create_box(
        input_cable_clamp_width,
        1,
        1,
        origin=(
            inner_max_x
            - cooleon_pair_housing_input_cable_clamp_clearance
            - input_cable_clamp_width,
            inner_min_y,
            inner_min_z,
        ),
    )
    input_cable_clamp_floor_clearance = create_box(
        1,
        1,
        cooleon_pair_housing_input_cable_clamp_clearance,
        origin=(inner_max_x, inner_min_y, inner_min_z),
    )
    input_cable_clamp = create_box(
        input_cable_clamp_width,
        cooleon_pair_housing_input_cable_clamp_arm_depth,
        cooleon_pair_housing_input_cable_clamp_arm_thickness,
    )
    input_cable_clamp = align(
        input_cable_clamp,
        input_cable_clamp_x_target,
        Alignment.CENTER,
        axes=[0],
    )
    input_cable_clamp = align(
        input_cable_clamp,
        input_cable_clamp_y_target,
        Alignment.CENTER,
        axes=[1],
    )
    input_cable_clamp = align(
        input_cable_clamp,
        input_cable_clamp_floor_clearance,
        Alignment.STACK_TOP,
    )

    input_cable_hole = create_cylinder(
        cooleon_pair_housing_input_cable_hole_diameter / 2,
        wall_thickness + 2,
    )
    input_cable_hole = align(
        input_cable_hole,
        input_cable_clamp,
        Alignment.CENTER,
        axes=[0, 1],
    )
    input_cable_hole = align(input_cable_hole, housing_box, Alignment.BOTTOM)
    housing_box = housing_box.cut(input_cable_hole)

    output_cable_holes = PartCollector()
    for output_terminal_center in output_terminal_centers:
        output_cable_hole_target = create_box(
            wall_thickness + 2,
            cooleon_pair_housing_output_cable_hole_diameter,
            cooleon_pair_housing_output_cable_hole_diameter,
            origin=(
                outer_min_x - 1,
                output_terminal_center[1]
                - cooleon_pair_housing_output_cable_hole_diameter / 2,
                output_terminal_center[2]
                - cooleon_pair_housing_output_cable_hole_diameter / 2,
            ),
        )
        output_cable_hole = create_cylinder(
            cooleon_pair_housing_output_cable_hole_diameter / 2,
            wall_thickness + 2,
            direction=(1, 0, 0),
        )
        output_cable_hole = align(
            output_cable_hole,
            output_cable_hole_target,
            Alignment.CENTER,
        )
        output_cable_holes = output_cable_holes.fuse(output_cable_hole)
    housing_box = housing_box.cut(output_cable_holes)

    input_cable_clamp_cable_hole_cutter = create_cylinder(
        cooleon_pair_housing_input_cable_clamp_hole_diameter / 2,
        cooleon_pair_housing_input_cable_clamp_arm_thickness + 2,
    )
    input_cable_clamp_cable_hole_cutter = align(
        input_cable_clamp_cable_hole_cutter,
        input_cable_hole,
        Alignment.CENTER,
        axes=[0, 1],
    )
    input_cable_clamp_cable_hole_cutter = align(
        input_cable_clamp_cable_hole_cutter,
        input_cable_clamp,
        Alignment.CENTER,
        axes=[2],
    )
    input_cable_clamp = input_cable_clamp.cut(input_cable_clamp_cable_hole_cutter)

    input_cable_clamp_slit_cutter = create_filleted_box(
        cooleon_pair_housing_input_cable_clamp_slit_width,
        cooleon_pair_housing_input_cable_clamp_arm_depth + 2,
        cooleon_pair_housing_input_cable_clamp_arm_thickness + 2,
        fillet_radius=cooleon_pair_housing_input_cable_clamp_slit_width / 3,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    input_cable_clamp_slit_cutter = align(
        input_cable_clamp_slit_cutter,
        input_cable_clamp,
        Alignment.CENTER,
    )
    input_cable_clamp_slit_cutter = align(
        input_cable_clamp_slit_cutter,
        input_cable_clamp,
        Alignment.STACK_BACK,
        stack_gap=(
            -cooleon_pair_housing_input_cable_clamp_arm_depth
            + cooleon_pair_housing_input_cable_clamp_hole_diameter / 2
        ),
    )
    input_cable_clamp = input_cable_clamp.cut(input_cable_clamp_slit_cutter)

    input_cable_clamp_screw_reference = create_box(
        input_cable_clamp_width,
        2 * cooleon_pair_housing_input_cable_clamp_hole_diameter,
        cooleon_pair_housing_input_cable_clamp_arm_thickness,
    )
    input_cable_clamp_screw_reference = align(
        input_cable_clamp_screw_reference,
        input_cable_clamp,
        Alignment.CENTER,
    )
    input_cable_clamp_screw_reference = align(
        input_cable_clamp_screw_reference,
        input_cable_clamp,
        Alignment.BACK,
    )
    input_cable_clamp_screw_assembly = create_screw_mount_assembly(
        input_cable_clamp_screw_reference,
        cooleon_pair_housing_input_cable_clamp_screw_size,
        cooleon_pair_housing_input_cable_clamp_screw_length,
        Alignment.RIGHT,
        flush_with_top=True,
    )
    input_cable_clamp = input_cable_clamp_screw_assembly.use_as_cutter_on(
        input_cable_clamp
    )
    input_cable_clamp_screw = (
        input_cable_clamp_screw_assembly.get_named_non_production_part("screw")
    )

    lid_length = outer_max_x - outer_min_x + 2 * cooleon_pair_housing_lid_outer_overhang
    lid_width = outer_max_y - outer_min_y + 2 * cooleon_pair_housing_lid_outer_overhang
    lid_min_x = outer_min_x - cooleon_pair_housing_lid_outer_overhang
    lid_min_y = outer_min_y - cooleon_pair_housing_lid_outer_overhang

    lid_base = create_filleted_box(
        lid_length,
        lid_width,
        cooleon_pair_housing_lid_thickness,
        fillet_radius=min(
            wall_thickness,
            cooleon_pair_housing_lid_outer_overhang,
        ),
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_base_target = create_box(
        lid_length,
        lid_width,
        cooleon_pair_housing_lid_thickness,
        origin=(lid_min_x, lid_min_y, lid_z_min),
    )
    lid_base = align(lid_base, lid_base_target, Alignment.CENTER)

    lid_drop_depth = (
        cooleon_pair_housing_lid_body_clearance + cooleon_pair_housing_lid_rim_depth
    )
    lid_rim_outer_length = (
        inner_max_x - inner_min_x - 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_rim_outer_width = (
        inner_max_y - inner_min_y - 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_rim_inner_length = lid_rim_outer_length - 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_rim_inner_width = lid_rim_outer_width - 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_ring_fillet = min(
        wall_thickness,
        cooleon_pair_housing_lid_rim_thickness / 2 - 0.1,
    )
    lid_drop_z_min = lid_z_min - lid_drop_depth
    lid_rim = create_filleted_box(
        lid_rim_outer_length,
        lid_rim_outer_width,
        lid_drop_depth,
        fillet_radius=lid_ring_fillet,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_rim_target = create_box(
        lid_rim_outer_length,
        lid_rim_outer_width,
        lid_drop_depth,
        origin=(
            (inner_min_x + inner_max_x - lid_rim_outer_length) / 2,
            (inner_min_y + inner_max_y - lid_rim_outer_width) / 2,
            lid_drop_z_min,
        ),
    )
    lid_rim = align(lid_rim, lid_rim_target, Alignment.CENTER)
    lid_rim_inner_cutter = create_box(
        lid_rim_inner_length,
        lid_rim_inner_width,
        lid_drop_depth + 2,
        origin=(
            (inner_min_x + inner_max_x - lid_rim_inner_length) / 2,
            (inner_min_y + inner_max_y - lid_rim_inner_width) / 2,
            lid_drop_z_min - 1,
        ),
    )
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)

    lid_outer_lip_inner_length = (
        outer_max_x - outer_min_x + 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_outer_lip_inner_width = (
        outer_max_y - outer_min_y + 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_outer_lip_outer_length = lid_outer_lip_inner_length + 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_outer_lip_outer_width = lid_outer_lip_inner_width + 2 * (
        cooleon_pair_housing_lid_rim_thickness
    )
    lid_outer_lip = create_filleted_box(
        lid_outer_lip_outer_length,
        lid_outer_lip_outer_width,
        lid_drop_depth,
        fillet_radius=lid_ring_fillet,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_outer_lip_target = create_box(
        lid_outer_lip_outer_length,
        lid_outer_lip_outer_width,
        lid_drop_depth,
        origin=(
            (outer_min_x + outer_max_x - lid_outer_lip_outer_length) / 2,
            (outer_min_y + outer_max_y - lid_outer_lip_outer_width) / 2,
            lid_drop_z_min,
        ),
    )
    lid_outer_lip = align(lid_outer_lip, lid_outer_lip_target, Alignment.CENTER)
    lid_outer_lip_inner_cutter = create_box(
        lid_outer_lip_inner_length,
        lid_outer_lip_inner_width,
        lid_drop_depth + 2,
        origin=(
            (outer_min_x + outer_max_x - lid_outer_lip_inner_length) / 2,
            (outer_min_y + outer_max_y - lid_outer_lip_inner_width) / 2,
            lid_drop_z_min - 1,
        ),
    )
    lid_outer_lip = lid_outer_lip.cut(lid_outer_lip_inner_cutter)

    for lid_boss in lid_bosses:
        lid_boss_relief_cutter = materialize_bounding_box(
            lid_boss,
            x_enlargement=cooleon_pair_housing_lid_screw_inset,
            y_enlargement=cooleon_pair_housing_lid_screw_inset,
            z_enlargement=cooleon_pair_housing_lid_body_clearance + 0.2,
        )
        lid_rim = lid_rim.cut(lid_boss_relief_cutter)
        lid_outer_lip = lid_outer_lip.cut(lid_boss_relief_cutter)

    lid = lid_base.fuse(lid_rim).fuse(lid_outer_lip)
    lid = lid.cut(lid_clearance_holes)

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(lid, "cooleon_pair_housing_lid")
    housing.add_named_follower(
        input_cable_clamp,
        "cooleon_pair_housing_input_cable_clamp",
    )
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    housing.add_named_cutter(vent_cutters, "side_vent_diamond_cutters")
    housing.add_named_cutter(input_cable_hole, "input_cable_hole")
    housing.add_named_cutter(output_cable_holes, "output_cable_holes")
    housing.add_named_cutter(
        psu_mount_thread_insert_cutters,
        "psu_mount_thread_inset_cutters",
    )
    housing.add_named_cutter(lid_pilot_holes, "lid_mount_pilot_holes")
    housing.add_named_cutter(lid_clearance_holes, "lid_mount_clearance_holes")
    for index, (pilot_hole, clearance_hole) in enumerate(lid_screw_positions, start=1):
        housing.add_named_cutter(pilot_hole, f"lid_mount_pilot_hole_{index}")
        housing.add_named_cutter(clearance_hole, f"lid_mount_clearance_hole_{index}")
    housing.add_named_non_production_part(
        psu_pair_reference,
        "cooleon_psu_pair_body_reference",
    )
    housing.add_named_non_production_part(lid_screws, "lid_mount_screws")
    housing.add_named_non_production_part(
        psu_mount_thread_insets,
        "psu_mount_thread_insets",
    )
    housing.add_named_non_production_part(
        input_cable_clamp_screw,
        "input_cable_clamp_screw",
    )

    return housing
