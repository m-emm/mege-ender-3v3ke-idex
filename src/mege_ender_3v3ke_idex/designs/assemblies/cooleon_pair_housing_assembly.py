"""Open-top housing with lid for a back-to-back Cooleon PSU pair."""

from mege_ender_3v3ke_idex.designs.trellis_plate import create_trellis_cutters
from shellforgepy.simple import *


def create_cooleon_pair_housing_assembly(
    *,
    cooleon_psu_1,
    cooleon_psu_2,
    input_cable_clamp,
    cooleon_pair_housing_clearance,
    cooleon_pair_housing_wall_thickness,
    cooleon_pair_housing_input_terminal_extra_space,
    cooleon_pair_housing_output_terminal_extra_space,
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
    cooleon_pair_housing_output_cable_hole_diameter,
    cooleon_pair_housing_psu_mount_thread_inset_extra_radius,
):
    """Create a lidded open-top tray around the placed Cooleon PSU bodies."""

    psu_pair_reference = cooleon_psu_1.leader.fuse(cooleon_psu_2.leader)
    psu_pair_size = get_bounding_box_size(psu_pair_reference)
    wall_thickness = cooleon_pair_housing_wall_thickness

    inner_core = materialize_bounding_box(
        psu_pair_reference,
        x_enlargement=2 * cooleon_pair_housing_clearance,
        y_enlargement=2 * cooleon_pair_housing_clearance,
        z_enlargement=2 * cooleon_pair_housing_clearance,
    )
    inner_core_size = get_bounding_box_size(inner_core)

    input_service_space = create_box(
        cooleon_pair_housing_input_terminal_extra_space,
        inner_core_size[1],
        inner_core_size[2],
    )
    input_service_space = align(
        input_service_space,
        inner_core,
        Alignment.CENTER,
        axes=[1, 2],
    )
    input_service_space = align(
        input_service_space,
        inner_core,
        Alignment.STACK_RIGHT,
    )

    output_service_space = create_box(
        cooleon_pair_housing_output_terminal_extra_space,
        inner_core_size[1],
        inner_core_size[2],
    )
    output_service_space = align(
        output_service_space,
        inner_core,
        Alignment.CENTER,
        axes=[1, 2],
    )
    output_service_space = align(
        output_service_space,
        inner_core,
        Alignment.STACK_LEFT,
    )

    inner_reference = inner_core.fuse(input_service_space).fuse(output_service_space)
    inner_reference_size = get_bounding_box_size(inner_reference)

    housing_box = create_box(
        inner_reference_size[0] + 2 * wall_thickness,
        inner_reference_size[1] + 2 * wall_thickness,
        inner_reference_size[2] + wall_thickness,
    )
    housing_box = align(housing_box, inner_reference, Alignment.CENTER, axes=[0, 1])
    housing_box = align(housing_box, inner_reference, Alignment.TOP)

    inner_space_cutter = create_box(
        inner_reference_size[0],
        inner_reference_size[1],
        inner_reference_size[2] + wall_thickness + 2,
    )
    inner_space_cutter = align(
        inner_space_cutter,
        inner_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    inner_space_cutter = align(inner_space_cutter, inner_reference, Alignment.BOTTOM)
    housing_box = housing_box.cut(inner_space_cutter)

    inner_min, inner_max = get_bounding_box(inner_reference)
    outer_min, outer_max = get_bounding_box(housing_box)
    inner_height = inner_reference_size[2]
    rib_height = outer_max[2] - inner_min[2]

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

    input_terminal_reference = cooleon_psu_1.get_non_production_part_by_name(
        "input_terminal_block"
    ).fuse(cooleon_psu_2.get_non_production_part_by_name("input_terminal_block"))
    output_terminal_parts = [
        cooleon_psu_1.get_non_production_part_by_name("output_terminal_block"),
        cooleon_psu_2.get_non_production_part_by_name("output_terminal_block"),
    ]

    psu_1_center = get_bounding_box_center(cooleon_psu_1.leader)
    psu_2_center = get_bounding_box_center(cooleon_psu_2.leader)
    if psu_1_center[1] < psu_2_center[1]:
        front_psu = cooleon_psu_1.leader
    else:
        front_psu = cooleon_psu_2.leader
    psu_y_faces = sorted(
        [
            get_bounding_box(cooleon_psu_1.leader)[0][1],
            get_bounding_box(cooleon_psu_1.leader)[1][1],
            get_bounding_box(cooleon_psu_2.leader)[0][1],
            get_bounding_box(cooleon_psu_2.leader)[1][1],
        ]
    )
    psu_gap_width = psu_y_faces[2] - psu_y_faces[1]
    psu_gap_center_y = (psu_y_faces[1] + psu_y_faces[2]) / 2

    gap_reference = create_box(
        psu_pair_size[0],
        psu_gap_width,
        rib_height,
    )
    gap_reference = align(gap_reference, psu_pair_reference, Alignment.CENTER, axes=[0])
    gap_reference = align(gap_reference, inner_reference, Alignment.BOTTOM)
    gap_reference = align(gap_reference, front_psu, Alignment.STACK_BACK)

    separator_walls = PartCollector()
    separator_wall_targets = []
    mount_screw_groups = [
        mount_screw_items[: len(mount_screw_items) // 2],
        mount_screw_items[len(mount_screw_items) // 2 :],
    ]
    for mount_screw_group in mount_screw_groups:
        mount_screw_reference = mount_screw_group[0][1].fuse(mount_screw_group[1][1])
        separator_wall = create_box(
            cooleon_pair_housing_mount_rib_length,
            cooleon_pair_housing_mount_rib_thickness,
            rib_height,
        )
        separator_wall = align(
            separator_wall,
            mount_screw_reference,
            Alignment.CENTER,
            axes=[0],
        )
        separator_wall = align(
            separator_wall,
            gap_reference,
            Alignment.CENTER,
            axes=[1],
        )
        separator_wall = align(separator_wall, inner_reference, Alignment.BOTTOM)
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
    boss_height = rib_height

    lid_base_reference = create_box(
        get_bounding_box_size(housing_box)[0]
        + 2 * cooleon_pair_housing_lid_outer_overhang,
        get_bounding_box_size(housing_box)[1]
        + 2 * cooleon_pair_housing_lid_outer_overhang,
        cooleon_pair_housing_lid_thickness,
    )
    lid_base_reference = align(
        lid_base_reference,
        housing_box,
        Alignment.CENTER,
        axes=[0, 1],
    )
    lid_base_reference = align(
        lid_base_reference,
        housing_box,
        Alignment.STACK_TOP,
        stack_gap=cooleon_pair_housing_lid_body_clearance,
    )

    boss_placement_frame = create_box(
        get_bounding_box_size(housing_box)[0]
        - 2 * cooleon_pair_housing_lid_screw_inset
        + 2 * boss_radius,
        get_bounding_box_size(housing_box)[1]
        - 2 * cooleon_pair_housing_lid_screw_inset
        + 2 * boss_radius,
        boss_height,
    )
    boss_placement_frame = align(
        boss_placement_frame,
        housing_box,
        Alignment.CENTER,
        axes=[0, 1],
    )
    boss_placement_frame = align(boss_placement_frame, housing_box, Alignment.BOTTOM)

    for x_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        for y_alignment in [Alignment.FRONT, Alignment.BACK]:
            lid_boss = create_cylinder(
                boss_radius,
                boss_height,
            )
            lid_boss = align(lid_boss, boss_placement_frame, x_alignment)
            lid_boss = align(lid_boss, boss_placement_frame, y_alignment)
            lid_boss = align(lid_boss, housing_box, Alignment.BOTTOM)
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
            )
            lid_clearance_hole = align(
                lid_clearance_hole,
                lid_boss,
                Alignment.CENTER,
                axes=[0, 1],
            )
            lid_clearance_hole = align(
                lid_clearance_hole,
                lid_base_reference,
                Alignment.CENTER,
                axes=[2],
            )
            lid_clearance_holes = lid_clearance_holes.fuse(lid_clearance_hole)
            lid_screw_positions.append((lid_pilot_hole, lid_clearance_hole))

            lid_screw = create_cylinder_screw(
                cooleon_pair_housing_lid_screw_size,
                cooleon_pair_housing_lid_screw_length,
            )
            lid_screw = align(
                lid_screw,
                lid_boss,
                Alignment.CENTER,
                axes=[0, 1],
            )
            lid_screw = align(
                lid_screw,
                lid_base_reference,
                Alignment.STACK_TOP,
                stack_gap=-cooleon_pair_housing_lid_screw_length,
            )
            lid_screws = lid_screws.fuse(lid_screw)

    housing_box = housing_box.fuse(lid_screw_bosses)
    housing_box = housing_box.cut(lid_pilot_holes)

    vent_cutters = PartCollector()
    vent_panel_length = inner_reference_size[0]
    vent_panel_height = cooleon_pair_housing_vent_height
    vent_panel_depth = wall_thickness + 4
    vent_band_width = (
        cooleon_pair_housing_vent_pitch - cooleon_pair_housing_vent_diamond_size
    )
    vent_bottom_spacer_height = max(
        0.1,
        (inner_height - vent_panel_height) * cooleon_pair_housing_vent_row_z,
    )
    vent_bottom_spacer = create_box(1, 1, vent_bottom_spacer_height)
    vent_bottom_spacer = align(vent_bottom_spacer, inner_reference, Alignment.BOTTOM)
    vent_vertical_reference = create_box(1, 1, vent_panel_height)
    vent_vertical_reference = align(
        vent_vertical_reference,
        vent_bottom_spacer,
        Alignment.STACK_TOP,
    )
    for y_alignment in [Alignment.FRONT, Alignment.BACK]:
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
        )
        side_vent_target = align(
            side_vent_target,
            inner_reference,
            Alignment.CENTER,
            axes=[0],
        )
        side_vent_target = align(
            side_vent_target,
            vent_vertical_reference,
            Alignment.CENTER,
            axes=[2],
        )
        side_vent_target = align(side_vent_target, housing_box, y_alignment)
        side_vent_cutters = align(side_vent_cutters, side_vent_target, Alignment.CENTER)
        vent_cutters = vent_cutters.fuse(side_vent_cutters)
    housing_box = housing_box.cut(vent_cutters)

    input_cable_hole = create_cylinder(
        cooleon_pair_housing_input_cable_hole_diameter / 2,
        wall_thickness + 4,
        direction=(1, 0, 0),
    )
    input_cable_hole = align(
        input_cable_hole,
        input_terminal_reference,
        Alignment.CENTER,
        axes=[1],
    )
    input_cable_hole = align(
        input_cable_hole,
        inner_reference,
        Alignment.CENTER,
        axes=[2],
    )
    input_cable_hole = align(input_cable_hole, housing_box, Alignment.RIGHT)
    housing_box = housing_box.cut(input_cable_hole)

    input_cable_clamp = input_cable_clamp.copy()
    input_cable_clamp = rotate(
        90,
        center=get_bounding_box_center(input_cable_clamp),
        axis=(0, 1, 0),
    )(input_cable_clamp)
    input_cable_clamp = input_cable_clamp.aligned_from_cutter(
        "cable_hole_cutter",
        input_cable_hole,
        Alignment.CENTER,
        axes=[1, 2],
    )
    input_cable_clamp = align(input_cable_clamp, inner_reference, Alignment.RIGHT)
    input_cable_clamp_clearance_pocket = input_cable_clamp.get_named_cutter(
        "clearance_cutter"
    )
    housing_box = housing_box.cut(input_cable_clamp_clearance_pocket)

    output_cable_holes = PartCollector()
    for output_terminal_part in output_terminal_parts:
        output_cable_hole = create_cylinder(
            cooleon_pair_housing_output_cable_hole_diameter / 2,
            wall_thickness + 4,
            direction=(1, 0, 0),
        )
        output_cable_hole = align(
            output_cable_hole,
            output_terminal_part,
            Alignment.CENTER,
            axes=[1, 2],
        )
        output_cable_hole = align(output_cable_hole, housing_box, Alignment.LEFT)
        output_cable_holes = output_cable_holes.fuse(output_cable_hole)
    housing_box = housing_box.cut(output_cable_holes)

    lid_length = get_bounding_box_size(lid_base_reference)[0]
    lid_width = get_bounding_box_size(lid_base_reference)[1]

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
    lid_base = align(lid_base, lid_base_reference, Alignment.CENTER)

    lid_drop_depth = (
        cooleon_pair_housing_lid_body_clearance + cooleon_pair_housing_lid_rim_depth
    )
    lid_rim_outer_length = (
        inner_reference_size[0] - 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_rim_outer_width = (
        inner_reference_size[1] - 2 * cooleon_pair_housing_lid_rim_clearance
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
    lid_rim = create_filleted_box(
        lid_rim_outer_length,
        lid_rim_outer_width,
        lid_drop_depth,
        fillet_radius=lid_ring_fillet,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    lid_rim = align(lid_rim, inner_reference, Alignment.CENTER, axes=[0, 1])
    lid_rim = align(lid_rim, lid_base_reference, Alignment.STACK_BOTTOM)
    lid_rim_inner_cutter = create_box(
        lid_rim_inner_length,
        lid_rim_inner_width,
        lid_drop_depth + 2,
    )
    lid_rim_inner_cutter = align(
        lid_rim_inner_cutter,
        lid_rim,
        Alignment.CENTER,
    )
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)

    lid_outer_lip_inner_length = (
        get_bounding_box_size(housing_box)[0]
        + 2 * cooleon_pair_housing_lid_rim_clearance
    )
    lid_outer_lip_inner_width = (
        get_bounding_box_size(housing_box)[1]
        + 2 * cooleon_pair_housing_lid_rim_clearance
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
    lid_outer_lip = align(lid_outer_lip, housing_box, Alignment.CENTER, axes=[0, 1])
    lid_outer_lip = align(lid_outer_lip, lid_base_reference, Alignment.STACK_BOTTOM)
    lid_outer_lip_inner_cutter = create_box(
        lid_outer_lip_inner_length,
        lid_outer_lip_inner_width,
        lid_drop_depth + 2,
    )
    lid_outer_lip_inner_cutter = align(
        lid_outer_lip_inner_cutter,
        lid_outer_lip,
        Alignment.CENTER,
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
        input_cable_clamp.leader,
        "cooleon_pair_housing_input_cable_clamp",
    )
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    housing.add_named_cutter(vent_cutters, "side_vent_diamond_cutters")
    housing.add_named_cutter(input_cable_hole, "input_cable_hole")
    housing.add_named_cutter(
        input_cable_clamp_clearance_pocket,
        "input_cable_clamp_clearance_pocket",
    )
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
        input_cable_clamp.get_named_non_production_part("tightening_screw"),
        "input_cable_clamp_screw",
    )

    return housing
