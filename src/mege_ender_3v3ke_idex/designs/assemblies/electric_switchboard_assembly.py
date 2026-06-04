"""24 V electric switchboard enclosure assembly."""

from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *


def create_electric_switchboard_assembly(
    *,
    emergency_button,
    fuse_holder,
    electric_switchboard_height,
    electric_switchboard_width,
    electric_switchboard_depth,
    electric_switchboard_wall_thickness,
    electric_switchboard_fuse_holder_top_y_offset,
    electric_switchboard_emergency_button_top_y_offset,
    electric_switchboard_rail_width,
    electric_switchboard_rail_height,
    electric_switchboard_rail_screw_size,
    electric_switchboard_rail_screw_length,
    electric_switchboard_rail_num_spots,
    electric_switchboard_rail_z_offset_from_bottom,
    electric_switchboard_rail_nut_pocket_clearance,
    electric_switchboard_cable_cutout_width,
    electric_switchboard_cable_cutout_height_ratio,
    electric_switchboard_cable_cutout_fillet_radius,
    electric_switchboard_cable_cutout_cover_y_oversize,
    electric_switchboard_cable_cutout_cover_x_oversize,
    electric_switchboard_cable_cutout_cover_thickness,
    electric_switchboard_cable_cutout_cover_clearance,
    electric_switchboard_cable_cutout_cover_mount_screw_size,
    electric_switchboard_cable_cutout_cover_mount_screw_length,
    electric_switchboard_cable_cutout_cover_mount_nut_clearance,
    electric_switchboard_cable_cutout_cover_mount_nut_pocket_sink_depth,
    electric_switchboard_mount_flange_screw_size,
    electric_switchboard_mount_flange_width,
    electric_switchboard_mount_flange_length,
    electric_switchboard_mount_flange_thickness,
    electric_switchboard_mount_flange_fillet_radius,
    electric_switchboard_corner_fillet_radius,
    electric_switchboard_lid_thickness,
    electric_switchboard_lid_body_clearance,
    electric_switchboard_lid_rim_depth,
    electric_switchboard_lid_rim_thickness,
    electric_switchboard_lid_rim_clearance,
    electric_switchboard_lid_screw_size,
    electric_switchboard_lid_screw_length,
    electric_switchboard_lid_screw_inset,
    electric_switchboard_lid_screw_mount_block_size,
    electric_switchboard_lid_screw_mount_depth,
):
    """Create a left-open switchboard box with a screw-on side lid."""

    switchboard_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_height,
    )

    switchboard_box = create_filleted_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_height,
        fillet_radius=electric_switchboard_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.BOTTOM, Alignment.RIGHT],
    )

    inner_space_cutter = create_box(
        electric_switchboard_width - electric_switchboard_wall_thickness + 1,
        electric_switchboard_depth - 2 * electric_switchboard_wall_thickness,
        electric_switchboard_height - 2 * electric_switchboard_wall_thickness,
        origin=(
            -1,
            electric_switchboard_wall_thickness,
            electric_switchboard_wall_thickness,
        ),
    )
    switchboard_box = switchboard_box.cut(inner_space_cutter)

    top_panel_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_wall_thickness,
        origin=(
            0,
            0,
            electric_switchboard_height - electric_switchboard_wall_thickness,
        ),
    )

    emergency_button = rotate(90)(emergency_button)

    emergency_button = emergency_button.aligned_from_non_production_part(
        "mount_panel_reference",
        top_panel_reference,
        Alignment.CENTER,
    )
    emergency_button = translate(
        0,
        electric_switchboard_emergency_button_top_y_offset,
        0,
    )(emergency_button)
    switchboard_box = switchboard_box.cut(
        emergency_button.get_cutter_part_by_name("neck_mount_hole")
    )

    fuse_holder = rotate(-90, axis=(0, 1, 0))(fuse_holder)
    fuse_holder = fuse_holder.aligned_from_non_production_part(
        "mount_panel_reference",
        top_panel_reference,
        Alignment.CENTER,
    )
    fuse_holder = translate(0, electric_switchboard_fuse_holder_top_y_offset, 0)(
        fuse_holder
    )
    switchboard_box = switchboard_box.cut(
        fuse_holder.get_cutter_part_by_name("mount_hole")
    )

    rail = create_box(
        electric_switchboard_rail_height,
        electric_switchboard_depth - 2 * electric_switchboard_wall_thickness,
        electric_switchboard_rail_width,
    )
    rail = align(rail, switchboard_reference, Alignment.CENTER, axes=[1])
    rail = align(rail, switchboard_reference, Alignment.RIGHT)
    rail = translate(-electric_switchboard_wall_thickness, 0, 0)(rail)
    rail = align(rail, switchboard_reference, Alignment.BOTTOM)
    rail = translate(0, 0, electric_switchboard_rail_z_offset_from_bottom)(rail)

    rail_screw_spec = MScrew.from_size(electric_switchboard_rail_screw_size)
    rail_pitch = get_bounding_box_size(rail)[1] / (
        electric_switchboard_rail_num_spots + 1
    )
    rail_bbox = get_bounding_box(rail)
    rail_center_y = get_bounding_box_center(rail)[1]
    rail_screws = PartCollector()

    for rail_spot_index in range(electric_switchboard_rail_num_spots):
        rail_screw_y = rail_bbox[0][1] + rail_pitch * (rail_spot_index + 1)
        rail_y_offset = rail_screw_y - rail_center_y

        rail_screw = create_cylinder_screw(
            electric_switchboard_rail_screw_size,
            electric_switchboard_rail_screw_length,
        )
        rail_screw = translate(0, 0, -electric_switchboard_rail_screw_length)(
            rail_screw
        )
        rail_screw = rotate(-90, axis=(0, 1, 0))(rail_screw)
        rail_screw = align(rail_screw, rail, Alignment.CENTER, axes=[1, 2])
        rail_screw = align(rail_screw, rail, Alignment.LEFT)
        rail_screw = translate(
            -rail_screw_spec.cylinder_head_height,
            rail_y_offset,
            0,
        )(rail_screw)
        rail_screws = rail_screws.fuse(rail_screw)

        rail_nut_pocket_cutter = create_hidden_nut_pocket_cutter(
            electric_switchboard_rail_screw_size,
            bottom_cutter_length=electric_switchboard_rail_width,
            top_cutter_length=electric_switchboard_rail_width,
            slack=electric_switchboard_rail_nut_pocket_clearance,
        )
        rail_nut_pocket_cutter = rotate(-90, axis=(0, 1, 0))(rail_nut_pocket_cutter)
        rail_nut_pocket_cutter = rotate(90, axis=(1, 0, 0))(rail_nut_pocket_cutter)
        rail_nut_pocket_cutter = align(rail_nut_pocket_cutter, rail, Alignment.CENTER)
        rail_nut_pocket_cutter = translate(0, rail_y_offset, 0)(rail_nut_pocket_cutter)
        rail = rail_nut_pocket_cutter.use_as_cutter_on(rail)

    switchboard_box = switchboard_box.fuse(rail)

    cable_cutout_height = (
        electric_switchboard_height * electric_switchboard_cable_cutout_height_ratio
    )
    cable_cutout_cutter_y_length = (
        electric_switchboard_wall_thickness
        + electric_switchboard_cable_cutout_cover_thickness
        + 10
    )
    cable_cutout_fillet_radius = min(
        electric_switchboard_cable_cutout_fillet_radius,
        electric_switchboard_cable_cutout_width / 2 - 0.1,
        cable_cutout_height / 2 - 0.1,
    )

    cable_cutout_cutter = PartCollector()
    cable_cutout_cutter = cable_cutout_cutter.fuse(
        create_box(
            electric_switchboard_cable_cutout_width - 2 * cable_cutout_fillet_radius,
            cable_cutout_cutter_y_length,
            cable_cutout_height,
            origin=(cable_cutout_fillet_radius, 0, 0),
        )
    )
    cable_cutout_cutter = cable_cutout_cutter.fuse(
        create_box(
            electric_switchboard_cable_cutout_width,
            cable_cutout_cutter_y_length,
            cable_cutout_height - 2 * cable_cutout_fillet_radius,
            origin=(0, 0, cable_cutout_fillet_radius),
        )
    )
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            cable_cutout_corner = create_cylinder(
                cable_cutout_fillet_radius,
                cable_cutout_cutter_y_length,
                origin=(
                    (
                        cable_cutout_fillet_radius
                        if lr == Alignment.LEFT
                        else electric_switchboard_cable_cutout_width
                        - cable_cutout_fillet_radius
                    ),
                    0,
                    (
                        cable_cutout_fillet_radius
                        if tb == Alignment.BOTTOM
                        else cable_cutout_height - cable_cutout_fillet_radius
                    ),
                ),
                direction=(0, 1, 0),
            )
            cable_cutout_cutter = cable_cutout_cutter.fuse(cable_cutout_corner)
    cable_cutout_cutter = align(
        cable_cutout_cutter, switchboard_reference, Alignment.CENTER, axes=[0, 2]
    )
    cable_cutout_cutter = align(
        cable_cutout_cutter, switchboard_reference, Alignment.BACK
    )
    switchboard_box = switchboard_box.cut(cable_cutout_cutter)

    cable_cutout_cover_width = (
        electric_switchboard_cable_cutout_width
        + electric_switchboard_cable_cutout_cover_x_oversize
    )
    cable_cutout_cover_height = (
        cable_cutout_height + electric_switchboard_cable_cutout_cover_y_oversize
    )
    cable_cutout_cover_plug_depth = min(
        electric_switchboard_wall_thickness,
        electric_switchboard_cable_cutout_cover_thickness,
    )
    cable_cutout_cover_flange_thickness = (
        electric_switchboard_cable_cutout_cover_thickness
        - cable_cutout_cover_plug_depth
    )
    cable_cutout_cover_plug_width = (
        electric_switchboard_cable_cutout_width
        - 2 * electric_switchboard_cable_cutout_cover_clearance
    )
    cable_cutout_cover_plug_height = (
        cable_cutout_height - 2 * electric_switchboard_cable_cutout_cover_clearance
    )
    cable_cutout_cover_fillet_radius = min(
        electric_switchboard_cable_cutout_fillet_radius,
        cable_cutout_cover_width / 2 - 0.1,
        cable_cutout_cover_height / 2 - 0.1,
    )
    cable_cutout_cover_plug_fillet_radius = min(
        cable_cutout_fillet_radius - electric_switchboard_cable_cutout_cover_clearance,
        cable_cutout_cover_plug_width / 2 - 0.1,
        cable_cutout_cover_plug_height / 2 - 0.1,
    )

    cable_cutout_cover_flange = PartCollector()
    cable_cutout_cover_flange = cable_cutout_cover_flange.fuse(
        create_box(
            cable_cutout_cover_width - 2 * cable_cutout_cover_fillet_radius,
            cable_cutout_cover_flange_thickness,
            cable_cutout_cover_height,
            origin=(cable_cutout_cover_fillet_radius, 0, 0),
        )
    )
    cable_cutout_cover_flange = cable_cutout_cover_flange.fuse(
        create_box(
            cable_cutout_cover_width,
            cable_cutout_cover_flange_thickness,
            cable_cutout_cover_height - 2 * cable_cutout_cover_fillet_radius,
            origin=(0, 0, cable_cutout_cover_fillet_radius),
        )
    )
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            cable_cutout_cover_corner = create_cylinder(
                cable_cutout_cover_fillet_radius,
                cable_cutout_cover_flange_thickness,
                origin=(
                    (
                        cable_cutout_cover_fillet_radius
                        if lr == Alignment.LEFT
                        else cable_cutout_cover_width - cable_cutout_cover_fillet_radius
                    ),
                    0,
                    (
                        cable_cutout_cover_fillet_radius
                        if tb == Alignment.BOTTOM
                        else cable_cutout_cover_height
                        - cable_cutout_cover_fillet_radius
                    ),
                ),
                direction=(0, 1, 0),
            )
            cable_cutout_cover_flange = cable_cutout_cover_flange.fuse(
                cable_cutout_cover_corner
            )
    cable_cutout_cover_flange = align(
        cable_cutout_cover_flange,
        switchboard_reference,
        Alignment.CENTER,
        axes=[0, 2],
    )
    cable_cutout_cover_flange = align(
        cable_cutout_cover_flange, switchboard_reference, Alignment.STACK_BACK
    )

    cable_cutout_cover_plug = PartCollector()
    cable_cutout_cover_plug = cable_cutout_cover_plug.fuse(
        create_box(
            cable_cutout_cover_plug_width - 2 * cable_cutout_cover_plug_fillet_radius,
            cable_cutout_cover_plug_depth,
            cable_cutout_cover_plug_height,
            origin=(cable_cutout_cover_plug_fillet_radius, 0, 0),
        )
    )
    cable_cutout_cover_plug = cable_cutout_cover_plug.fuse(
        create_box(
            cable_cutout_cover_plug_width,
            cable_cutout_cover_plug_depth,
            cable_cutout_cover_plug_height - 2 * cable_cutout_cover_plug_fillet_radius,
            origin=(0, 0, cable_cutout_cover_plug_fillet_radius),
        )
    )
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            cable_cutout_cover_plug_corner = create_cylinder(
                cable_cutout_cover_plug_fillet_radius,
                cable_cutout_cover_plug_depth,
                origin=(
                    (
                        cable_cutout_cover_plug_fillet_radius
                        if lr == Alignment.LEFT
                        else cable_cutout_cover_plug_width
                        - cable_cutout_cover_plug_fillet_radius
                    ),
                    0,
                    (
                        cable_cutout_cover_plug_fillet_radius
                        if tb == Alignment.BOTTOM
                        else cable_cutout_cover_plug_height
                        - cable_cutout_cover_plug_fillet_radius
                    ),
                ),
                direction=(0, 1, 0),
            )
            cable_cutout_cover_plug = cable_cutout_cover_plug.fuse(
                cable_cutout_cover_plug_corner
            )
    cable_cutout_cover_plug = align(
        cable_cutout_cover_plug,
        cable_cutout_cover_flange,
        Alignment.CENTER,
        axes=[0, 2],
    )
    cable_cutout_cover_plug = align(
        cable_cutout_cover_plug, cable_cutout_cover_flange, Alignment.STACK_FRONT
    )

    cable_cutout_cover = cable_cutout_cover_flange.fuse(cable_cutout_cover_plug)

    back_wall_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_wall_thickness,
        electric_switchboard_height,
        origin=(
            0,
            electric_switchboard_depth - electric_switchboard_wall_thickness,
            0,
        ),
    )
    cable_cutout_cover_mount_screw_spec = MScrew.from_size(
        electric_switchboard_cable_cutout_cover_mount_screw_size
    )
    cable_cutout_cover_mount_screw_z_offset = (
        cable_cutout_height / 2 + (cable_cutout_cover_height - cable_cutout_height) / 4
    )
    cable_cutout_cover_mount_holes = PartCollector()
    cable_cutout_cover_mount_nut_pocket_cutters = PartCollector()
    cable_cutout_cover_mount_screws = PartCollector()
    cable_cutout_cover_mount_nuts = PartCollector()

    for tb in [Alignment.TOP, Alignment.BOTTOM]:
        screw_z_translation = tb.sign * cable_cutout_cover_mount_screw_z_offset

        cable_cutout_cover_mount_hole = create_cylinder(
            cable_cutout_cover_mount_screw_spec.clearance_hole_normal / 2,
            electric_switchboard_wall_thickness
            + electric_switchboard_cable_cutout_cover_thickness
            + 4,
            direction=(0, 1, 0),
        )
        cable_cutout_cover_mount_hole = align(
            cable_cutout_cover_mount_hole, cable_cutout_cover, Alignment.CENTER
        )
        cable_cutout_cover_mount_hole = translate(0, 0, screw_z_translation)(
            cable_cutout_cover_mount_hole
        )
        cable_cutout_cover_mount_holes = cable_cutout_cover_mount_holes.fuse(
            cable_cutout_cover_mount_hole
        )

        cable_cutout_cover_mount_screw = create_cylinder_screw(
            electric_switchboard_cable_cutout_cover_mount_screw_size,
            electric_switchboard_cable_cutout_cover_mount_screw_length,
        )
        cable_cutout_cover_mount_screw = translate(
            0, 0, -electric_switchboard_cable_cutout_cover_mount_screw_length
        )(cable_cutout_cover_mount_screw)
        cable_cutout_cover_mount_screw = rotate(-90, axis=(1, 0, 0))(
            cable_cutout_cover_mount_screw
        )
        cable_cutout_cover_mount_screw = align(
            cable_cutout_cover_mount_screw,
            cable_cutout_cover,
            Alignment.CENTER,
            axes=[0, 2],
        )
        cable_cutout_cover_mount_screw = align(
            cable_cutout_cover_mount_screw,
            cable_cutout_cover,
            Alignment.BACK,
        )
        cable_cutout_cover_mount_screw = translate(
            0,
            cable_cutout_cover_mount_screw_spec.cylinder_head_height,
            screw_z_translation,
        )(cable_cutout_cover_mount_screw)
        cable_cutout_cover_mount_screws = cable_cutout_cover_mount_screws.fuse(
            cable_cutout_cover_mount_screw
        )

        cable_cutout_cover_mount_nut = create_nut(
            electric_switchboard_cable_cutout_cover_mount_screw_size
        )
        cable_cutout_cover_mount_nut = rotate(-90, axis=(1, 0, 0))(
            cable_cutout_cover_mount_nut
        )
        cable_cutout_cover_mount_nut = align(
            cable_cutout_cover_mount_nut,
            back_wall_reference,
            Alignment.CENTER,
            axes=[0, 2],
        )
        cable_cutout_cover_mount_nut = align(
            cable_cutout_cover_mount_nut,
            back_wall_reference,
            Alignment.STACK_FRONT,
        )
        cable_cutout_cover_mount_nut = translate(0, 0, screw_z_translation)(
            cable_cutout_cover_mount_nut
        )
        cable_cutout_cover_mount_nuts = cable_cutout_cover_mount_nuts.fuse(
            cable_cutout_cover_mount_nut
        )

        cable_cutout_cover_mount_nut_pocket = create_nut(
            electric_switchboard_cable_cutout_cover_mount_screw_size,
            height=electric_switchboard_cable_cutout_cover_mount_nut_pocket_sink_depth,
            slack=electric_switchboard_cable_cutout_cover_mount_nut_clearance,
            no_hole=True,
        )
        cable_cutout_cover_mount_nut_pocket = rotate(-90, axis=(1, 0, 0))(
            cable_cutout_cover_mount_nut_pocket
        )
        cable_cutout_cover_mount_nut_pocket = align(
            cable_cutout_cover_mount_nut_pocket,
            back_wall_reference,
            Alignment.CENTER,
            axes=[0, 2],
        )
        cable_cutout_cover_mount_nut_pocket = align(
            cable_cutout_cover_mount_nut_pocket,
            back_wall_reference,
            Alignment.FRONT,
        )
        cable_cutout_cover_mount_nut_pocket = translate(0, 0, screw_z_translation)(
            cable_cutout_cover_mount_nut_pocket
        )
        cable_cutout_cover_mount_nut_pocket_cutters = (
            cable_cutout_cover_mount_nut_pocket_cutters.fuse(
                cable_cutout_cover_mount_nut_pocket
            )
        )

    cable_cutout_cover = cable_cutout_cover.cut(cable_cutout_cover_mount_holes)
    switchboard_box = switchboard_box.cut(cable_cutout_cover_mount_holes)
    switchboard_box = switchboard_box.cut(cable_cutout_cover_mount_nut_pocket_cutters)

    lid = create_filleted_box(
        electric_switchboard_lid_thickness,
        electric_switchboard_depth,
        electric_switchboard_height,
        fillet_radius=electric_switchboard_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    lid = align(lid, switchboard_reference, Alignment.CENTER, axes=[1, 2])
    lid = align(
        lid,
        switchboard_reference,
        Alignment.STACK_LEFT,
        stack_gap=electric_switchboard_lid_body_clearance,
    )

    lid_rim_outer_width = (
        electric_switchboard_depth
        - 2 * electric_switchboard_wall_thickness
        - 2 * electric_switchboard_lid_rim_clearance
    )
    lid_rim_outer_height = (
        electric_switchboard_height
        - 2 * electric_switchboard_wall_thickness
        - 2 * electric_switchboard_lid_rim_clearance
    )
    lid_rim_inner_width = (
        lid_rim_outer_width - 2 * electric_switchboard_lid_rim_thickness
    )
    lid_rim_inner_height = (
        lid_rim_outer_height - 2 * electric_switchboard_lid_rim_thickness
    )
    lid_rim_fillet_radius = min(
        electric_switchboard_corner_fillet_radius,
        electric_switchboard_lid_rim_thickness / 2 - 0.1,
    )
    lid_rim = create_filleted_box(
        electric_switchboard_lid_body_clearance + electric_switchboard_lid_rim_depth,
        lid_rim_outer_width,
        lid_rim_outer_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_rim_inner_cutter = create_box(
        electric_switchboard_lid_body_clearance
        + electric_switchboard_lid_rim_depth
        + 2,
        lid_rim_inner_width,
        lid_rim_inner_height,
    )
    lid_rim_inner_cutter = align(lid_rim_inner_cutter, lid_rim, Alignment.CENTER)
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, switchboard_reference, Alignment.CENTER, axes=[1, 2])
    lid_rim = align(lid_rim, lid, Alignment.STACK_RIGHT)
    lid = lid.fuse(lid_rim)

    lid_screw_mount_blocks = PartCollector()

    for fb in [Alignment.FRONT, Alignment.BACK]:
        for tb in [Alignment.TOP, Alignment.BOTTOM]:
            screw_mount_block = create_filleted_box(
                electric_switchboard_width,
                electric_switchboard_lid_screw_mount_block_size,
                electric_switchboard_lid_screw_mount_block_size,
                fillet_radius=min(
                    electric_switchboard_corner_fillet_radius,
                    electric_switchboard_lid_screw_mount_block_size / 4,
                ),
                no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
            )

            screw_mount_block = align(
                screw_mount_block, switchboard_reference, Alignment.CENTER, axes=[1, 2]
            )
            screw_mount_block = align(screw_mount_block, switchboard_reference, fb)
            screw_mount_block = align(screw_mount_block, switchboard_reference, tb)

            lid_screw_mount_blocks = lid_screw_mount_blocks.fuse(screw_mount_block)

    lid_screw_span_reference = lid.fuse(lid_screw_mount_blocks)
    lid_screw_mount = create_four_screws_mount_assembly(
        lid_screw_span_reference,
        electric_switchboard_lid_screw_size,
        electric_switchboard_lid_screw_length,
        screw_direction=Alignment.LEFT,
        with_nut_cutter=True,
        flush_with_top=True,
        width_inset=electric_switchboard_lid_screw_inset,
        length_inset=electric_switchboard_lid_screw_inset,
        clearance_type="loose",
    )

    lid = lid_screw_mount.use_as_cutter_on(lid)
    lid_screw_mount_blocks = lid_screw_mount.use_as_cutter_on(lid_screw_mount_blocks)
    switchboard_box = switchboard_box.fuse(lid_screw_mount_blocks)
    switchboard_box = lid_screw_mount.use_as_cutter_on(switchboard_box)

    mount_flange_screw_hole_diameter = MScrew.from_size(
        electric_switchboard_mount_flange_screw_size
    ).clearance_hole_normal
    mount_flange_screw_holes = PartCollector()
    mount_flanges = PartCollector()
    for side in [Alignment.FRONT, Alignment.BACK]:
        mount_flange = create_filleted_box(
            electric_switchboard_mount_flange_width,
            electric_switchboard_mount_flange_length,
            electric_switchboard_mount_flange_thickness,
            fillet_radius=electric_switchboard_mount_flange_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
        )
        mount_flange = align(mount_flange, switchboard_box, Alignment.CENTER, axes=[0])
        mount_flange = align(mount_flange, switchboard_box, side.stack_alignment)
        mount_flange = align(mount_flange, switchboard_box, Alignment.BOTTOM)
        mount_flanges = mount_flanges.fuse(mount_flange)

        mount_flange_screw_hole = create_cylinder(
            mount_flange_screw_hole_diameter / 2,
            electric_switchboard_mount_flange_thickness + 2,
            origin=(
                get_bounding_box_center(mount_flange)[0],
                get_bounding_box_center(mount_flange)[1],
                -1,
            ),
        )
        mount_flange_screw_holes = mount_flange_screw_holes.fuse(
            mount_flange_screw_hole
        )

    switchboard_box = switchboard_box.fuse(mount_flanges)
    switchboard_box = switchboard_box.cut(mount_flange_screw_holes)

    switchboard = LeaderFollowersCuttersPart(leader=switchboard_box)
    switchboard.add_named_follower(lid, "electric_switchboard_lid")
    switchboard.add_named_follower(
        cable_cutout_cover, "electric_switchboard_cable_cutout_cover"
    )
    switchboard.add_named_cutter(mount_flange_screw_holes, "mount_flange_screw_holes")
    switchboard.add_named_non_production_part(
        rail_screws, "electric_switchboard_rail_screws"
    )
    switchboard.add_named_non_production_part(
        cable_cutout_cover_mount_screws, "cable_cutout_cover_mount_screws"
    )
    switchboard.add_named_non_production_part(
        cable_cutout_cover_mount_nuts, "cable_cutout_cover_mount_nuts"
    )
    switchboard = switchboard.merge_except_leader(
        lid_screw_mount.prefixed_copy("lid_mount")
    )

    for name, part in emergency_button.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in fuse_holder.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"fuse_holder_{name}")

    return switchboard
