"""High-voltage mains switchbox enclosure assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *


def create_hv_switchbox_assembly(
    *,
    fuse_holder,
    ssr,
    hv_switchbox_height,
    hv_switchbox_width,
    hv_switchbox_depth,
    hv_switchbox_wall_thickness,
    hv_switchbox_fuse_holder_top_y_offset,
    hv_switchbox_terminal_rail_width,
    hv_switchbox_terminal_rail_height,
    hv_switchbox_terminal_screw_size,
    hv_switchbox_terminal_screw_length,
    hv_switchbox_terminal_num_spots,
    hv_switchbox_terminal_rail_z_offset_from_bottom,
    hv_switchbox_terminal_nut_pocket_clearance,
    hv_switchbox_terminal_nut_pocket_sink_depth,
    hv_switchbox_ssr_mount_screw_size,
    hv_switchbox_ssr_mount_screw_length,
    hv_switchbox_ssr_mount_boss_depth,
    hv_switchbox_ssr_mount_boss_width,
    hv_switchbox_ssr_mount_boss_height,
    hv_switchbox_ssr_mount_nut_pocket_clearance,
    hv_switchbox_ssr_mount_nut_pocket_sink_depth,
    hv_switchbox_ssr_y_center,
    hv_switchbox_ssr_z_center,
    hv_switchbox_cable_cutout_width,
    hv_switchbox_cable_cutout_height_ratio,
    hv_switchbox_cable_cutout_fillet_radius,
    hv_switchbox_cable_cutout_cover_y_oversize,
    hv_switchbox_cable_cutout_cover_x_oversize,
    hv_switchbox_cable_cutout_cover_thickness,
    hv_switchbox_cable_cutout_cover_flange_thickness,
    hv_switchbox_cable_cutout_cover_clearance,
    hv_switchbox_cable_cutout_cover_mount_screw_size,
    hv_switchbox_cable_cutout_cover_mount_screw_length,
    hv_switchbox_cable_cutout_cover_mount_nut_clearance,
    hv_switchbox_cable_cutout_cover_mount_nut_pocket_sink_depth,
    hv_switchbox_mount_flange_screw_size,
    hv_switchbox_mount_flange_width,
    hv_switchbox_mount_flange_length,
    hv_switchbox_mount_flange_thickness,
    hv_switchbox_mount_flange_fillet_radius,
    hv_switchbox_corner_fillet_radius,
    hv_switchbox_lid_thickness,
    hv_switchbox_lid_body_clearance,
    hv_switchbox_lid_rim_depth,
    hv_switchbox_lid_rim_thickness,
    hv_switchbox_lid_rim_clearance,
    hv_switchbox_lid_screw_size,
    hv_switchbox_lid_screw_length,
    hv_switchbox_lid_screw_inset,
    hv_switchbox_lid_screw_mount_block_size,
):
    """Create a left-open mains switchbox with internal SSR and terminals."""

    switchbox_reference = create_box(
        hv_switchbox_width,
        hv_switchbox_depth,
        hv_switchbox_height,
    )

    switchbox_box = create_filleted_box(
        hv_switchbox_width,
        hv_switchbox_depth,
        hv_switchbox_height,
        fillet_radius=hv_switchbox_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.BOTTOM, Alignment.RIGHT],
    )

    inner_space_cutter = create_box(
        hv_switchbox_width - hv_switchbox_wall_thickness + 1,
        hv_switchbox_depth - 2 * hv_switchbox_wall_thickness,
        hv_switchbox_height - 2 * hv_switchbox_wall_thickness,
        origin=(
            -1,
            hv_switchbox_wall_thickness,
            hv_switchbox_wall_thickness,
        ),
    )
    switchbox_box = switchbox_box.cut(inner_space_cutter)

    top_panel_reference = create_box(
        hv_switchbox_width,
        hv_switchbox_depth,
        hv_switchbox_wall_thickness,
        origin=(0, 0, hv_switchbox_height - hv_switchbox_wall_thickness),
    )

    fuse_holder = rotate(-90, axis=(0, 1, 0))(fuse_holder)
    fuse_holder = fuse_holder.aligned_from_non_production_part(
        "mount_panel_reference",
        top_panel_reference,
        Alignment.CENTER,
    )
    fuse_holder = translate(0, hv_switchbox_fuse_holder_top_y_offset, 0)(fuse_holder)
    switchbox_box = switchbox_box.cut(fuse_holder.get_cutter_part_by_name("mount_hole"))

    inner_right_x = hv_switchbox_width - hv_switchbox_wall_thickness
    ssr_mount_boss_left_x = inner_right_x - hv_switchbox_ssr_mount_boss_depth
    ssr_mount_bosses = PartCollector()
    ssr_mount_holes = PartCollector()
    ssr_mount_nut_pocket_cutters = PartCollector()
    ssr_mount_screws = PartCollector()
    ssr_mount_nuts = PartCollector()
    ssr_mount_screws_list = []
    ssr_mount_nuts_list = []
    ssr_mount_holes_list = []
    ssr_mount_nut_pockets_list = []
    ssr_mount_hole_pattern = ssr.get_cutter_part_by_name("mounting_hole_pattern")
    ssr_mount_hole_pattern = rotate(90, axis=(0, 1, 0))(ssr_mount_hole_pattern)
    ssr_mount_translation = (
        ssr_mount_boss_left_x - get_bounding_box(ssr_mount_hole_pattern)[1][0],
        hv_switchbox_ssr_y_center - get_bounding_box_center(ssr_mount_hole_pattern)[1],
        hv_switchbox_ssr_z_center - get_bounding_box_center(ssr_mount_hole_pattern)[2],
    )
    ssr_mount_hole_pattern = translate(*ssr_mount_translation)(ssr_mount_hole_pattern)
    ssr_mount_hole_y_positions = []
    for mounting_hole_name in ["mounting_hole_1", "mounting_hole_2"]:
        ssr_mount_hole_reference = ssr.get_cutter_part_by_name(mounting_hole_name)
        ssr_mount_hole_reference = rotate(90, axis=(0, 1, 0))(ssr_mount_hole_reference)
        ssr_mount_hole_reference = translate(*ssr_mount_translation)(
            ssr_mount_hole_reference
        )
        ssr_mount_hole_y_positions.append(
            get_bounding_box_center(ssr_mount_hole_reference)[1]
        )

    ssr_visual = rotate(90, axis=(0, 1, 0))(ssr)
    ssr_visual = translate(
        ssr_mount_boss_left_x - get_bounding_box(ssr_visual)[1][0],
        hv_switchbox_ssr_y_center - get_bounding_box_center(ssr_visual)[1],
        hv_switchbox_ssr_z_center - get_bounding_box_center(ssr_visual)[2],
    )(ssr_visual)
    ssr_visual_bbox = get_bounding_box(ssr_visual)

    ssr_mount_screw_spec = MScrew.from_size(hv_switchbox_ssr_mount_screw_size)
    for ssr_mount_y in ssr_mount_hole_y_positions:
        ssr_mount_boss = create_filleted_box(
            hv_switchbox_ssr_mount_boss_depth,
            hv_switchbox_ssr_mount_boss_width,
            hv_switchbox_ssr_mount_boss_height,
            fillet_radius=min(
                hv_switchbox_corner_fillet_radius,
                hv_switchbox_ssr_mount_boss_width / 4,
                hv_switchbox_ssr_mount_boss_height / 4,
            ),
            no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
        )
        ssr_mount_boss = translate(
            ssr_mount_boss_left_x,
            ssr_mount_y - hv_switchbox_ssr_mount_boss_width / 2,
            hv_switchbox_ssr_z_center - hv_switchbox_ssr_mount_boss_height / 2,
        )(ssr_mount_boss)

        ssr_mount_hole = create_cylinder(
            ssr_mount_screw_spec.clearance_hole_normal / 2,
            hv_switchbox_ssr_mount_boss_depth - 0.8,
            origin=(
                ssr_mount_boss_left_x + 0.4,
                ssr_mount_y,
                hv_switchbox_ssr_z_center,
            ),
            direction=(1, 0, 0),
        )
        ssr_mount_boss = ssr_mount_boss.cut(ssr_mount_hole)
        ssr_mount_holes = ssr_mount_holes.fuse(ssr_mount_hole)
        ssr_mount_holes_list.append(ssr_mount_hole)

        ssr_mount_nut_pocket = create_hidden_nut_pocket_cutter(
            hv_switchbox_ssr_mount_screw_size,
            nut_height=hv_switchbox_ssr_mount_nut_pocket_sink_depth,
            bottom_cutter_length=hv_switchbox_ssr_mount_boss_depth,
            top_cutter_length=hv_switchbox_ssr_mount_boss_depth,
            slack=hv_switchbox_ssr_mount_nut_pocket_clearance,
        )
        ssr_mount_nut_pocket = rotate(-90, axis=(0, 1, 0))(ssr_mount_nut_pocket)
        ssr_mount_nut_pocket = rotate(90, axis=(1, 0, 0))(ssr_mount_nut_pocket)
        ssr_mount_nut_pocket = align(
            ssr_mount_nut_pocket, ssr_mount_boss, Alignment.CENTER
        )
        ssr_mount_boss = ssr_mount_nut_pocket.use_as_cutter_on(ssr_mount_boss)
        ssr_mount_nut_pocket_cutter = ssr_mount_nut_pocket.cutters[0]
        ssr_mount_nut_pocket_cutters = ssr_mount_nut_pocket_cutters.fuse(
            ssr_mount_nut_pocket_cutter
        )
        ssr_mount_nut_pockets_list.append(ssr_mount_nut_pocket_cutter)

        ssr_mount_screw_shaft = create_cylinder(
            float(hv_switchbox_ssr_mount_screw_size[1:]) / 2,
            inner_right_x - 0.8 - ssr_visual_bbox[0][0],
            origin=(
                ssr_visual_bbox[0][0],
                ssr_mount_y,
                hv_switchbox_ssr_z_center,
            ),
            direction=(1, 0, 0),
        )
        ssr_mount_screw_head = create_cylinder(
            ssr_mount_screw_spec.cylinder_head_diameter / 2,
            ssr_mount_screw_spec.cylinder_head_height,
            origin=(
                ssr_visual_bbox[0][0] - ssr_mount_screw_spec.cylinder_head_height,
                ssr_mount_y,
                hv_switchbox_ssr_z_center,
            ),
            direction=(1, 0, 0),
        )
        ssr_mount_screw = ssr_mount_screw_shaft.fuse(ssr_mount_screw_head)
        ssr_mount_screws = ssr_mount_screws.fuse(ssr_mount_screw)
        ssr_mount_screws_list.append(ssr_mount_screw)

        ssr_mount_nut = create_nut(hv_switchbox_ssr_mount_screw_size)
        ssr_mount_nut = rotate(-90, axis=(0, 1, 0))(ssr_mount_nut)
        ssr_mount_nut = rotate(90, axis=(1, 0, 0))(ssr_mount_nut)
        ssr_mount_nut = align(
            ssr_mount_nut, ssr_mount_nut_pocket.leader, Alignment.CENTER
        )
        ssr_mount_nuts = ssr_mount_nuts.fuse(ssr_mount_nut)
        ssr_mount_nuts_list.append(ssr_mount_nut)
        ssr_mount_bosses = ssr_mount_bosses.fuse(ssr_mount_boss)

    switchbox_box = switchbox_box.fuse(ssr_mount_bosses)

    terminal_rail = create_box(
        hv_switchbox_terminal_rail_height,
        hv_switchbox_depth - 2 * hv_switchbox_wall_thickness,
        hv_switchbox_terminal_rail_width,
    )
    terminal_rail = align(
        terminal_rail, switchbox_reference, Alignment.CENTER, axes=[1]
    )
    terminal_rail = align(terminal_rail, switchbox_reference, Alignment.RIGHT)
    terminal_rail = translate(-hv_switchbox_wall_thickness, 0, 0)(terminal_rail)
    terminal_rail = align(terminal_rail, switchbox_reference, Alignment.BOTTOM)
    terminal_rail = translate(0, 0, hv_switchbox_terminal_rail_z_offset_from_bottom)(
        terminal_rail
    )

    terminal_screw_spec = MScrew.from_size(hv_switchbox_terminal_screw_size)
    terminal_rail_pitch = get_bounding_box_size(terminal_rail)[1] / (
        hv_switchbox_terminal_num_spots + 1
    )
    terminal_rail_bbox = get_bounding_box(terminal_rail)
    terminal_rail_center_y = get_bounding_box_center(terminal_rail)[1]
    terminal_screws = PartCollector()
    terminal_nuts = PartCollector()
    terminal_holes = PartCollector()
    terminal_nut_pocket_cutters = PartCollector()
    terminal_screws_list = []
    terminal_nuts_list = []
    terminal_holes_list = []
    terminal_nut_pockets_list = []

    for terminal_index in range(hv_switchbox_terminal_num_spots):
        terminal_y = terminal_rail_bbox[0][1] + terminal_rail_pitch * (
            terminal_index + 1
        )

        terminal_hole = create_cylinder(
            terminal_screw_spec.clearance_hole_normal / 2,
            hv_switchbox_terminal_rail_height - 0.8,
            origin=(
                terminal_rail_bbox[0][0] + 0.4,
                terminal_y,
                get_bounding_box_center(terminal_rail)[2],
            ),
            direction=(1, 0, 0),
        )
        terminal_rail = terminal_rail.cut(terminal_hole)
        terminal_holes = terminal_holes.fuse(terminal_hole)
        terminal_holes_list.append(terminal_hole)

        terminal_nut_pocket = create_hidden_nut_pocket_cutter(
            hv_switchbox_terminal_screw_size,
            nut_height=hv_switchbox_terminal_nut_pocket_sink_depth,
            bottom_cutter_length=hv_switchbox_terminal_rail_width,
            top_cutter_length=hv_switchbox_terminal_rail_width,
            slack=hv_switchbox_terminal_nut_pocket_clearance,
        )
        terminal_nut_pocket = rotate(-90, axis=(0, 1, 0))(terminal_nut_pocket)
        terminal_nut_pocket = rotate(90, axis=(1, 0, 0))(terminal_nut_pocket)
        terminal_nut_pocket = align(
            terminal_nut_pocket, terminal_rail, Alignment.CENTER
        )
        terminal_nut_pocket = translate(
            0,
            terminal_y - terminal_rail_center_y,
            0,
        )(terminal_nut_pocket)
        terminal_rail = terminal_nut_pocket.use_as_cutter_on(terminal_rail)
        terminal_nut_pocket_cutter = terminal_nut_pocket.cutters[0]
        terminal_nut_pocket_cutters = terminal_nut_pocket_cutters.fuse(
            terminal_nut_pocket_cutter
        )
        terminal_nut_pockets_list.append(terminal_nut_pocket_cutter)

        terminal_screw_shaft = create_cylinder(
            float(hv_switchbox_terminal_screw_size[1:]) / 2,
            terminal_rail_bbox[1][0] - 0.8 - terminal_rail_bbox[0][0],
            origin=(
                terminal_rail_bbox[0][0],
                terminal_y,
                get_bounding_box_center(terminal_rail)[2],
            ),
            direction=(1, 0, 0),
        )
        terminal_screw_head = create_cylinder(
            terminal_screw_spec.cylinder_head_diameter / 2,
            terminal_screw_spec.cylinder_head_height,
            origin=(
                terminal_rail_bbox[0][0] - terminal_screw_spec.cylinder_head_height,
                terminal_y,
                get_bounding_box_center(terminal_rail)[2],
            ),
            direction=(1, 0, 0),
        )
        terminal_screw = terminal_screw_shaft.fuse(terminal_screw_head)
        terminal_screws = terminal_screws.fuse(terminal_screw)
        terminal_screws_list.append(terminal_screw)

        terminal_nut = create_nut(hv_switchbox_terminal_screw_size)
        terminal_nut = rotate(-90, axis=(0, 1, 0))(terminal_nut)
        terminal_nut = rotate(90, axis=(1, 0, 0))(terminal_nut)
        terminal_nut = align(terminal_nut, terminal_nut_pocket.leader, Alignment.CENTER)
        terminal_nuts = terminal_nuts.fuse(terminal_nut)
        terminal_nuts_list.append(terminal_nut)

    switchbox_box = switchbox_box.fuse(terminal_rail)

    cable_cutout_height = hv_switchbox_height * hv_switchbox_cable_cutout_height_ratio
    cable_cutout_fillet_radius = min(
        hv_switchbox_cable_cutout_fillet_radius,
        hv_switchbox_cable_cutout_width / 2 - 0.1,
        cable_cutout_height / 2 - 0.1,
    )
    cable_cutout_cutter = create_filleted_box(
        hv_switchbox_cable_cutout_width,
        hv_switchbox_wall_thickness + hv_switchbox_cable_cutout_cover_thickness + 10,
        cable_cutout_height,
        fillet_radius=cable_cutout_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    cable_cutout_cutter = align(
        cable_cutout_cutter, switchbox_reference, Alignment.CENTER, axes=[0, 2]
    )
    cable_cutout_cutter = align(
        cable_cutout_cutter, switchbox_reference, Alignment.BACK
    )
    switchbox_box = switchbox_box.cut(cable_cutout_cutter)

    cable_cutout_cover_width = (
        hv_switchbox_cable_cutout_width + hv_switchbox_cable_cutout_cover_x_oversize
    )
    cable_cutout_cover_height = (
        cable_cutout_height + hv_switchbox_cable_cutout_cover_y_oversize
    )
    cable_cutout_cover_flange_thickness = min(
        hv_switchbox_cable_cutout_cover_flange_thickness,
        hv_switchbox_cable_cutout_cover_thickness - 0.1,
    )
    cable_cutout_cover_plug_depth = (
        hv_switchbox_cable_cutout_cover_thickness - cable_cutout_cover_flange_thickness
    )
    cable_cutout_cover_fillet_radius = min(
        cable_cutout_fillet_radius,
        cable_cutout_cover_width / 2 - 0.1,
        cable_cutout_cover_height / 2 - 0.1,
    )
    cable_cutout_cover = create_filleted_box(
        cable_cutout_cover_width,
        cable_cutout_cover_flange_thickness,
        cable_cutout_cover_height,
        fillet_radius=cable_cutout_cover_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    cable_cutout_cover = align(
        cable_cutout_cover, switchbox_reference, Alignment.CENTER, axes=[0, 2]
    )
    cable_cutout_cover = align(
        cable_cutout_cover, switchbox_reference, Alignment.STACK_BACK
    )
    cable_cutout_cover_plug = create_filleted_box(
        hv_switchbox_cable_cutout_width - 2 * hv_switchbox_cable_cutout_cover_clearance,
        cable_cutout_cover_plug_depth,
        cable_cutout_height - 2 * hv_switchbox_cable_cutout_cover_clearance,
        fillet_radius=max(
            0.1,
            cable_cutout_fillet_radius - hv_switchbox_cable_cutout_cover_clearance,
        ),
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    cable_cutout_cover_plug = align(
        cable_cutout_cover_plug, cable_cutout_cover, Alignment.CENTER, axes=[0, 2]
    )
    cable_cutout_cover_plug = align(
        cable_cutout_cover_plug, cable_cutout_cover, Alignment.STACK_FRONT
    )
    cable_cutout_cover = cable_cutout_cover.fuse(cable_cutout_cover_plug)

    back_wall_reference = create_box(
        hv_switchbox_width,
        hv_switchbox_wall_thickness,
        hv_switchbox_height,
        origin=(0, hv_switchbox_depth - hv_switchbox_wall_thickness, 0),
    )
    cable_cover_screw_spec = MScrew.from_size(
        hv_switchbox_cable_cutout_cover_mount_screw_size
    )
    cable_cover_mount_screw_z_offset = (
        cable_cutout_height / 2 + (cable_cutout_cover_height - cable_cutout_height) / 4
    )
    cable_cover_mount_holes = PartCollector()
    cable_cover_mount_nut_pocket_cutters = PartCollector()
    cable_cover_mount_screws = PartCollector()
    cable_cover_mount_nuts = PartCollector()

    for tb in [Alignment.TOP, Alignment.BOTTOM]:
        cable_cover_screw_z_translation = tb.sign * cable_cover_mount_screw_z_offset

        cable_cover_mount_hole = create_cylinder(
            cable_cover_screw_spec.clearance_hole_normal / 2,
            hv_switchbox_wall_thickness + hv_switchbox_cable_cutout_cover_thickness + 4,
            direction=(0, 1, 0),
        )
        cable_cover_mount_hole = align(
            cable_cover_mount_hole, cable_cutout_cover, Alignment.CENTER
        )
        cable_cover_mount_hole = translate(0, 0, cable_cover_screw_z_translation)(
            cable_cover_mount_hole
        )
        cable_cover_mount_holes = cable_cover_mount_holes.fuse(cable_cover_mount_hole)

        cable_cover_mount_screw = create_cylinder_screw(
            hv_switchbox_cable_cutout_cover_mount_screw_size,
            hv_switchbox_cable_cutout_cover_mount_screw_length,
        )
        cable_cover_mount_screw = translate(
            0, 0, -hv_switchbox_cable_cutout_cover_mount_screw_length
        )(cable_cover_mount_screw)
        cable_cover_mount_screw = rotate(-90, axis=(1, 0, 0))(cable_cover_mount_screw)
        cable_cover_mount_screw = align(
            cable_cover_mount_screw, cable_cutout_cover, Alignment.CENTER, axes=[0, 2]
        )
        cable_cover_mount_screw = align(
            cable_cover_mount_screw, cable_cutout_cover, Alignment.BACK
        )
        cable_cover_mount_screw = translate(
            0,
            cable_cover_screw_spec.cylinder_head_height,
            cable_cover_screw_z_translation,
        )(cable_cover_mount_screw)
        cable_cover_mount_screws = cable_cover_mount_screws.fuse(
            cable_cover_mount_screw
        )

        cable_cover_mount_nut = create_nut(
            hv_switchbox_cable_cutout_cover_mount_screw_size
        )
        cable_cover_mount_nut = rotate(-90, axis=(1, 0, 0))(cable_cover_mount_nut)
        cable_cover_mount_nut = align(
            cable_cover_mount_nut, back_wall_reference, Alignment.CENTER, axes=[0, 2]
        )
        cable_cover_mount_nut = align(
            cable_cover_mount_nut, back_wall_reference, Alignment.STACK_FRONT
        )
        cable_cover_mount_nut = translate(0, 0, cable_cover_screw_z_translation)(
            cable_cover_mount_nut
        )
        cable_cover_mount_nuts = cable_cover_mount_nuts.fuse(cable_cover_mount_nut)

        cable_cover_mount_nut_pocket = create_nut(
            hv_switchbox_cable_cutout_cover_mount_screw_size,
            height=hv_switchbox_cable_cutout_cover_mount_nut_pocket_sink_depth,
            slack=hv_switchbox_cable_cutout_cover_mount_nut_clearance,
            no_hole=True,
        )
        cable_cover_mount_nut_pocket = rotate(-90, axis=(1, 0, 0))(
            cable_cover_mount_nut_pocket
        )
        cable_cover_mount_nut_pocket = align(
            cable_cover_mount_nut_pocket,
            back_wall_reference,
            Alignment.CENTER,
            axes=[0, 2],
        )
        cable_cover_mount_nut_pocket = align(
            cable_cover_mount_nut_pocket, back_wall_reference, Alignment.FRONT
        )
        cable_cover_mount_nut_pocket = translate(0, 0, cable_cover_screw_z_translation)(
            cable_cover_mount_nut_pocket
        )
        cable_cover_mount_nut_pocket_cutters = (
            cable_cover_mount_nut_pocket_cutters.fuse(cable_cover_mount_nut_pocket)
        )

    cable_cutout_cover = cable_cutout_cover.cut(cable_cover_mount_holes)
    switchbox_box = switchbox_box.cut(cable_cover_mount_holes)
    switchbox_box = switchbox_box.cut(cable_cover_mount_nut_pocket_cutters)

    lid = create_filleted_box(
        hv_switchbox_lid_thickness,
        hv_switchbox_depth,
        hv_switchbox_height,
        fillet_radius=hv_switchbox_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    lid = align(lid, switchbox_reference, Alignment.CENTER, axes=[1, 2])
    lid = align(
        lid,
        switchbox_reference,
        Alignment.STACK_LEFT,
        stack_gap=hv_switchbox_lid_body_clearance,
    )

    lid_rim_outer_width = (
        hv_switchbox_depth
        - 2 * hv_switchbox_wall_thickness
        - 2 * hv_switchbox_lid_rim_clearance
    )
    lid_rim_outer_height = (
        hv_switchbox_height
        - 2 * hv_switchbox_wall_thickness
        - 2 * hv_switchbox_lid_rim_clearance
    )
    lid_rim_inner_width = lid_rim_outer_width - 2 * hv_switchbox_lid_rim_thickness
    lid_rim_inner_height = lid_rim_outer_height - 2 * hv_switchbox_lid_rim_thickness
    lid_rim_fillet_radius = min(
        hv_switchbox_corner_fillet_radius,
        hv_switchbox_lid_rim_thickness / 2 - 0.1,
    )
    lid_rim = create_filleted_box(
        hv_switchbox_lid_body_clearance + hv_switchbox_lid_rim_depth,
        lid_rim_outer_width,
        lid_rim_outer_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_rim_inner_cutter = create_box(
        hv_switchbox_lid_body_clearance + hv_switchbox_lid_rim_depth + 2,
        lid_rim_inner_width,
        lid_rim_inner_height,
    )
    lid_rim_inner_cutter = align(lid_rim_inner_cutter, lid_rim, Alignment.CENTER)
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, switchbox_reference, Alignment.CENTER, axes=[1, 2])
    lid_rim = align(lid_rim, lid, Alignment.STACK_RIGHT)
    lid = lid.fuse(lid_rim)

    lid_screw_mount_blocks = PartCollector()
    lid_screw_mount_blocks_list = []
    for fb in [Alignment.FRONT, Alignment.BACK]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            screw_mount_block = create_filleted_box(
                hv_switchbox_width,
                hv_switchbox_lid_screw_mount_block_size,
                hv_switchbox_lid_screw_mount_block_size,
                fillet_radius=min(
                    hv_switchbox_corner_fillet_radius,
                    hv_switchbox_lid_screw_mount_block_size / 4,
                ),
                no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
            )
            screw_mount_block = align(
                screw_mount_block, switchbox_reference, Alignment.CENTER, axes=[1, 2]
            )
            screw_mount_block = align(screw_mount_block, switchbox_reference, fb)
            screw_mount_block = align(screw_mount_block, switchbox_reference, tb)
            lid_screw_mount_blocks = lid_screw_mount_blocks.fuse(screw_mount_block)
            lid_screw_mount_blocks_list.append(screw_mount_block)

    lid_screw_span_reference = lid.fuse(lid_screw_mount_blocks)
    lid_screw_mount = create_four_screws_mount_assembly(
        lid_screw_span_reference,
        hv_switchbox_lid_screw_size,
        hv_switchbox_lid_screw_length,
        screw_direction=Alignment.LEFT,
        with_nut_cutter=True,
        flush_with_top=True,
        width_inset=hv_switchbox_lid_screw_inset,
        length_inset=hv_switchbox_lid_screw_inset,
        clearance_type="loose",
    )

    lid = lid_screw_mount.use_as_cutter_on(lid)
    for lid_screw_mount_block in lid_screw_mount_blocks_list:
        lid_screw_mount_block_cutter = materialize_bounding_box(
            lid_screw_mount_block,
            x_enlargement=0.2,
            y_enlargement=0.2,
            z_enlargement=0.2,
        )
        lid = lid.cut(lid_screw_mount_block_cutter)

    lid_screw_mount_blocks = lid_screw_mount.use_as_cutter_on(lid_screw_mount_blocks)
    switchbox_box = switchbox_box.fuse(lid_screw_mount_blocks)
    switchbox_box = lid_screw_mount.use_as_cutter_on(switchbox_box)

    mount_flange_screw_hole_diameter = MScrew.from_size(
        hv_switchbox_mount_flange_screw_size
    ).clearance_hole_normal
    mount_flange_screw_holes = PartCollector()
    mount_flanges = PartCollector()
    for side in [Alignment.FRONT, Alignment.BACK]:
        mount_flange = create_filleted_box(
            hv_switchbox_mount_flange_width,
            hv_switchbox_mount_flange_length,
            hv_switchbox_mount_flange_thickness,
            fillet_radius=hv_switchbox_mount_flange_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
        )
        mount_flange = align(mount_flange, switchbox_box, Alignment.CENTER, axes=[0])
        mount_flange = align(mount_flange, switchbox_box, side.stack_alignment)
        mount_flange = align(mount_flange, switchbox_box, Alignment.BOTTOM)
        mount_flanges = mount_flanges.fuse(mount_flange)

        mount_flange_screw_hole = create_cylinder(
            mount_flange_screw_hole_diameter / 2,
            hv_switchbox_mount_flange_thickness + 2,
            origin=(
                get_bounding_box_center(mount_flange)[0],
                get_bounding_box_center(mount_flange)[1],
                -1,
            ),
        )
        mount_flange_screw_holes = mount_flange_screw_holes.fuse(
            mount_flange_screw_hole
        )

    switchbox_box = switchbox_box.fuse(mount_flanges)
    switchbox_box = switchbox_box.cut(mount_flange_screw_holes)

    switchbox = LeaderFollowersCuttersPart(leader=switchbox_box)
    switchbox.add_named_follower(lid, "hv_switchbox_lid")
    switchbox.add_named_follower(cable_cutout_cover, "hv_switchbox_cable_cutout_cover")
    switchbox.add_named_cutter(mount_flange_screw_holes, "mount_flange_screw_holes")
    switchbox.add_named_cutter(cable_cutout_cutter, "cable_cutout")
    switchbox.add_named_cutter(terminal_holes, "terminal_holes")
    switchbox.add_named_cutter(
        terminal_nut_pocket_cutters, "terminal_nut_pocket_cutters"
    )
    switchbox.add_named_cutter(ssr_mount_holes, "ssr_mount_holes")
    switchbox.add_named_cutter(
        ssr_mount_nut_pocket_cutters, "ssr_mount_nut_pocket_cutters"
    )
    switchbox.add_named_non_production_part(
        switchbox_reference, "hv_switchbox_body_reference"
    )
    switchbox.add_named_non_production_part(
        inner_space_cutter, "hv_switchbox_inner_space_reference"
    )
    switchbox.add_named_non_production_part(
        terminal_screws, "hv_switchbox_terminal_screws"
    )
    switchbox.add_named_non_production_part(terminal_nuts, "hv_switchbox_terminal_nuts")
    switchbox.add_named_non_production_part(ssr_mount_screws, "ssr_mount_screws")
    switchbox.add_named_non_production_part(ssr_mount_nuts, "ssr_mount_nuts")
    for ssr_mount_index, ssr_mount_screw in enumerate(ssr_mount_screws_list, start=1):
        switchbox.add_named_non_production_part(
            ssr_mount_screw, f"ssr_mount_screw_{ssr_mount_index}"
        )
    for ssr_mount_index, ssr_mount_nut in enumerate(ssr_mount_nuts_list, start=1):
        switchbox.add_named_non_production_part(
            ssr_mount_nut, f"ssr_mount_nut_{ssr_mount_index}"
        )
    for ssr_mount_index, ssr_mount_hole in enumerate(ssr_mount_holes_list, start=1):
        switchbox.add_named_cutter(ssr_mount_hole, f"ssr_mount_hole_{ssr_mount_index}")
    for ssr_mount_index, ssr_mount_nut_pocket in enumerate(
        ssr_mount_nut_pockets_list, start=1
    ):
        switchbox.add_named_cutter(
            ssr_mount_nut_pocket, f"ssr_mount_nut_pocket_{ssr_mount_index}"
        )
    for terminal_index, terminal_screw in enumerate(terminal_screws_list, start=1):
        switchbox.add_named_non_production_part(
            terminal_screw, f"terminal_screw_{terminal_index}"
        )
    for terminal_index, terminal_nut in enumerate(terminal_nuts_list, start=1):
        switchbox.add_named_non_production_part(
            terminal_nut, f"terminal_nut_{terminal_index}"
        )
    for terminal_index, terminal_hole in enumerate(terminal_holes_list, start=1):
        switchbox.add_named_cutter(terminal_hole, f"terminal_hole_{terminal_index}")
    for terminal_index, terminal_nut_pocket in enumerate(
        terminal_nut_pockets_list, start=1
    ):
        switchbox.add_named_cutter(
            terminal_nut_pocket, f"terminal_nut_pocket_{terminal_index}"
        )
    switchbox.add_named_non_production_part(
        cable_cover_mount_screws, "cable_cutout_cover_mount_screws"
    )
    switchbox.add_named_non_production_part(
        cable_cover_mount_nuts, "cable_cutout_cover_mount_nuts"
    )
    switchbox = switchbox.merge_except_leader(
        lid_screw_mount.prefixed_copy("lid_mount")
    )

    for name, part in fuse_holder.get_named_follower_items():
        switchbox.add_named_non_production_part(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_cutter_items():
        switchbox.add_named_cutter(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_non_production_part_items():
        switchbox.add_named_non_production_part(part, f"fuse_holder_{name}")

    for name, part in ssr_visual.get_named_follower_items():
        switchbox.add_named_non_production_part(part, f"ssr_{name}")

    for name, part in ssr_visual.get_named_cutter_items():
        switchbox.add_named_cutter(part, f"ssr_{name}")

    for name, part in ssr_visual.get_named_non_production_part_items():
        switchbox.add_named_non_production_part(part, f"ssr_{name}")

    return switchbox
