"""Right/T1 extruder cage assembly fork for Tap integration."""

from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from shellforgepy.simple import *


def create_extruder_cage_right_assembly(
    *,
    sprite_extruder,
    nitehawk_board,
    tool_head_mount_machined,
    extruder_cage_mount_plate_thickness,
    extruder_cage_mount_plate_fillet_radius,
    extruder_cage_flange_thickness,
    extruder_cage_screw_size,
    extruder_cage_top_right_bridge_clearance,
    tool_head_mount_base_plate_height,
    tool_head_mount_sprite_mount_screw_length,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    duct_back_mount_plate_height,
    duct_back_mount_plate_height_border,
    duct_back_mount_plate_offset,
    duct_back_mount_plate_width_border,
    nitehawk_holder_mount_tower_diameter,
    nitehawk_holder_mount_tower_height,
    nitehawk_mount_tower_base_extension,
    nitehawk_holes_center_distance,
    nitehawk_nut_cutter_slack,
    BIG_THING,
):
    """Create the right/T1 cage around the injected Sprite extruder."""

    _ = tool_head_mount_machined


    tap_top_travel = 1.2

    extruder_size = get_bounding_box_size(sprite_extruder)
    screw_record = MScrew.from_size(extruder_cage_screw_size)
    sprite_extruder_size = get_bounding_box_size(sprite_extruder)
    sprite_extruder_bbox = get_bounding_box(sprite_extruder)
    sprite_extruder_body_size = get_bounding_box_size(sprite_extruder.leader)
    mount_hole_cutter = sprite_extruder.get_named_cutter("mount_hole_cutter")

    extruder_mount_base_plate_thickness = extruder_cage_mount_plate_thickness + 2
    tool_head_mount_machined_bbox = get_bounding_box(tool_head_mount_machined)
    tool_head_mount_machined_max_x = tool_head_mount_machined_bbox[1][0]
    tool_head_mount_machined_min_x = tool_head_mount_machined_bbox[0][0]
    sprite_extruder_min_x = sprite_extruder_bbox[0][0]

    sprite_extruder_max_x = sprite_extruder_bbox[1][0]
    sprite_mount_base_plate_width = (
        sprite_extruder_max_x
        - sprite_extruder_min_x
        + extruder_cage_flange_thickness
    )

    sprite_mount_base_plate = create_box(
        sprite_mount_base_plate_width,
        extruder_mount_base_plate_thickness,
        tool_head_mount_base_plate_height,
    )



    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        mount_hole_cutter,
        Alignment.CENTER,
    )
    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        tool_head_mount_machined,
        Alignment.STACK_BOTTOM,
    )
    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
    )

    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        sprite_extruder,
        Alignment.LEFT,
    )
    sprite_mount_base_plate = sprite_extruder.use_as_cutter_on(sprite_mount_base_plate)
    for name, cutter in tool_head_mount_machined.get_named_cutter_items():
        if "hole_drill_" in name:
            sprite_mount_base_plate = sprite_mount_base_plate.cut(cutter)
    sprite_mount_base_plate = sprite_mount_base_plate.cut(sprite_extruder.leader)

    mount_hole_cutter_bbox = get_bounding_box(mount_hole_cutter)
    mount_hole_cutter_size = get_bounding_box_size(mount_hole_cutter)
    mount_hole_cutter_center = get_bounding_box_center(mount_hole_cutter)
    mount_hole_diameter = mount_hole_cutter_size[0] - NemaSizes.NEMA17.hole_dist_mm
    if mount_hole_diameter <= 0:
        raise ValueError(
            "Sprite extruder mount hole cutter bbox does not match a NEMA17 pattern"
        )

    mount_hole_radius = mount_hole_diameter / 2
    top_mount_hole_center_z = mount_hole_cutter_bbox[1][2] - mount_hole_radius
    sprite_mount_screws = []
    for side_name, mount_hole_center_x in zip(
        ["left", "right"],
        [
            mount_hole_cutter_bbox[0][0] + mount_hole_radius,
            mount_hole_cutter_bbox[1][0] - mount_hole_radius,
        ],
    ):
        hole_guide = create_cylinder(
            mount_hole_radius,
            mount_hole_cutter_size[1],
            direction=(0, 1, 0),
        )
        hole_guide = align(hole_guide, mount_hole_cutter, Alignment.CENTER)
        hole_guide = translate(
            mount_hole_center_x - mount_hole_cutter_center[0],
            0,
            top_mount_hole_center_z - mount_hole_cutter_center[2],
        )(hole_guide)

        screw = create_cylinder_screw(
            extruder_cage_screw_size,
            tool_head_mount_sprite_mount_screw_length,
        )
        screw = rotate(-90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_guide, Alignment.CENTER)
        screw = align(screw, sprite_mount_base_plate, Alignment.BACK)
        screw = translate(0, screw_record.cylinder_head_height, 0)(screw)
        sprite_mount_screws.append((side_name, screw))

    duct_back_mount_plate_width = sprite_extruder_body_size[0]
    part_fan_back_mount_plate = create_filleted_box(
        duct_back_mount_plate_width,
        duct_back_mount_plate_height,
        extruder_cage_mount_plate_thickness,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    back_mount_plate_cutout = create_filleted_box(
        duct_back_mount_plate_width - 2 * duct_back_mount_plate_width_border,
        duct_back_mount_plate_height - 2 * duct_back_mount_plate_height_border,
        extruder_cage_mount_plate_thickness + 10,
        fillet_radius=(
            min(
                duct_back_mount_plate_width - 2 * duct_back_mount_plate_width_border,
                duct_back_mount_plate_height - 2 * duct_back_mount_plate_height_border,
            )
            / 4
        ),
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    back_mount_plate_cutout = align(
        back_mount_plate_cutout,
        part_fan_back_mount_plate,
        Alignment.CENTER,
    )
    part_fan_back_mount_plate = part_fan_back_mount_plate.cut(back_mount_plate_cutout)
    part_fan_back_mount_plate = rotate(90, axis=(1, 0, 0))(part_fan_back_mount_plate)
    part_fan_back_mount_plate = align(
        part_fan_back_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    part_fan_back_mount_plate = align(
        part_fan_back_mount_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
    )
    part_fan_back_mount_plate = align(
        part_fan_back_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    part_fan_back_mount_plate = translate(0, 0, duct_back_mount_plate_offset)(
        part_fan_back_mount_plate
    )
    part_fan_back_mount_plate = sprite_extruder.use_as_cutter_on(
        part_fan_back_mount_plate
    )

    nitehawk_pcb = nitehawk_board.get_named_follower("pcb")
    nitehawk_board_holes = sorted(
        [
            nitehawk_board.get_named_cutter("hole_1"),
            nitehawk_board.get_named_cutter("hole_2"),
        ],
        key=lambda hole: get_bounding_box_center(hole)[0],
    )
    tower_base_radius = (
        nitehawk_holder_mount_tower_diameter / 2 + nitehawk_mount_tower_base_extension
    )
    tower_tip_radius = nitehawk_holder_mount_tower_diameter / 2
    nitehawk_plate_width = nitehawk_holes_center_distance + 2 * (tower_base_radius)
    nitehawk_plate_depth = extruder_cage_mount_plate_thickness

    nitehawk_rear_mount_plate = create_filleted_box(
        nitehawk_plate_width,
        nitehawk_plate_depth,
        extruder_size[2],
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )

    nitehawk_mount_screws = []
    nitehawk_cutters = {}
    nitehawk_hole_cutters = []
    nitehawk_towers = PartCollector()

    sprite_extruder_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    sprite_extruder_cutter = align(
        sprite_extruder_cutter, sprite_extruder, Alignment.CENTER
    )
    sprite_extruder_cutter = align(
        sprite_extruder_cutter, sprite_extruder, Alignment.FRONT
    )

    for index, board_hole in enumerate(nitehawk_board_holes):
        tower = create_cone(
            tower_base_radius,
            tower_tip_radius,
            nitehawk_holder_mount_tower_height,
        )
        tower = rotate(90, axis=(1, 0, 0))(tower)
        tower = align(tower, board_hole, Alignment.CENTER, axes=[0, 2])
        tower = align(tower, nitehawk_pcb, Alignment.STACK_BACK)

        hole_cutter = create_cylinder(
            screw_record.clearance_hole_normal / 2,
            BIG_THING,
            direction=(0, 1, 0),
        )
        hole_cutter = align(hole_cutter, tower, Alignment.CENTER)

        hole_cutter = hole_cutter.cut(sprite_extruder_cutter)

        nitehawk_cutters[f"nitehawk_mount_hole_{index}"] = hole_cutter
        nitehawk_hole_cutters.append(hole_cutter)
        nitehawk_towers = nitehawk_towers.fuse(tower)

        screw = create_cylinder_screw(
            extruder_cage_screw_size,
            tool_head_mount_sprite_mount_screw_length,
        )
        screw = rotate(90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_cutter, Alignment.CENTER)
        screw = align(screw, nitehawk_board, Alignment.FRONT)
        screw = translate(0, -screw_record.cylinder_head_height, 0)(screw)
        nitehawk_mount_screws.append(screw)

    nitehawk_rear_mount_plate = align(
        nitehawk_rear_mount_plate,
        nitehawk_towers,
        Alignment.CENTER,
        axes=[0, 2],
    )
    nitehawk_rear_mount_plate = align(
        nitehawk_rear_mount_plate,
        nitehawk_towers,
        Alignment.STACK_BACK,
    )

    nitehawk_rear_mount_plate = align(
        nitehawk_rear_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
        axes=[2],
    )

    for index, hole_cutter in enumerate(nitehawk_hole_cutters):
        nut_pocket = create_nut(
            extruder_cage_screw_size,
            height=screw_record.nut_thickness + nitehawk_nut_cutter_slack,
            slack=nitehawk_nut_cutter_slack,
            no_hole=True,
        )
        nut_pocket = rotate(-90, axis=(1, 0, 0))(nut_pocket)
        nut_pocket = align(nut_pocket, hole_cutter, Alignment.CENTER)
        nut_pocket = align(nut_pocket, nitehawk_rear_mount_plate, Alignment.BACK)
        nitehawk_cutters[f"nitehawk_mount_nut_pocket_{index}"] = nut_pocket

    nitehawk_rear_mount_plate = nitehawk_rear_mount_plate.fuse(nitehawk_towers)
    for cutter in nitehawk_cutters.values():
        nitehawk_rear_mount_plate = nitehawk_rear_mount_plate.cut(cutter)
    nitehawk_rear_mount_plate = sprite_extruder.use_as_cutter_on(
        nitehawk_rear_mount_plate
    )

    left_mount_plate = create_filleted_box(
        extruder_cage_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        extruder_size[2],
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.TOP],
    )
    left_mount_plate = align(
        left_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    left_mount_plate = align(
        left_mount_plate,
        sprite_extruder,
        Alignment.FRONT,
    )
    left_mount_plate = align(
        left_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    left_mount_plate = align(
        left_mount_plate,
        sprite_extruder,
        Alignment.STACK_LEFT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )

    cutout_length = extruder_size[2] / 3
    cutout_depth = tool_head_additional_mount_plate_depth / 2

    left_mount_plate_cutout = create_pyramid_stump(
        bottom_width=cutout_length + cutout_depth,
        top_width=cutout_length,
        bottom_depth=BIG_THING,
        top_depth=BIG_THING,
        height=cutout_depth,
    )
    left_mount_plate_cutout = rotate(90)(left_mount_plate_cutout)

    left_mount_plate_cutout = rotate(90, axis=(1, 0, 0))(left_mount_plate_cutout)

    left_mount_plate_cutout = align(
        left_mount_plate_cutout,
        left_mount_plate,
        Alignment.CENTER,
    )
    left_mount_plate_cutout = align(
        left_mount_plate_cutout,
        left_mount_plate,
        Alignment.BACK,
    )
    left_mount_plate = left_mount_plate.cut(left_mount_plate_cutout)

    nitehawk_board_connectors = PartCollector()
    for tb in [Alignment.TOP, Alignment.BOTTOM]:

        nitehawk_board_connector = create_box(
            extruder_cage_mount_plate_thickness,
            BIG_THING,
            tool_head_additional_mount_plate_depth,
        )

        nitehawk_board_connector = align(
            nitehawk_board_connector,
            left_mount_plate,
            Alignment.CENTER,
        )
        nitehawk_board_connector = align(
            nitehawk_board_connector,
            left_mount_plate,
            Alignment.STACK_FRONT,
        )

        nitehawk_board_connector = align(
            nitehawk_board_connector, nitehawk_rear_mount_plate, tb
        )

        nitehawk_board_connector = fit_part_between(
            nitehawk_board_connector,
            cut_normal=(0, 1, 0),
            limiting_start_part=nitehawk_rear_mount_plate,
            limiting_end_part=sprite_extruder,
        )
        nitehawk_board_connectors = nitehawk_board_connectors.fuse(
            nitehawk_board_connector
        )

    left_mount_plate = left_mount_plate.fuse(nitehawk_board_connectors)

    left_mount_plate = sprite_extruder.use_as_cutter_on(left_mount_plate)

    right_mount_plate = create_box(
        extruder_cage_mount_plate_thickness,
        BIG_THING,
        tool_head_additional_mount_plate_depth,
    )
    right_mount_plate = align(
        right_mount_plate,
        sprite_mount_base_plate,
        Alignment.CENTER,
    )
    right_mount_plate = align(
        right_mount_plate,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )

    right_mount_plate = align(
        right_mount_plate,
        sprite_mount_base_plate,
        Alignment.STACK_FRONT,
    )
    right_mount_plate = align(
        right_mount_plate,
        sprite_mount_base_plate,
        Alignment.BOTTOM,
    )

    nitehawk_rear_mount_plate_shifted = translate(0, -nitehawk_plate_depth, 0)(
        nitehawk_rear_mount_plate
    )

    right_mount_plate = fit_part_between(
        right_mount_plate,
        cut_normal=(0, 1, 0),
        limiting_start_part=nitehawk_rear_mount_plate_shifted,
        limiting_end_part=sprite_mount_base_plate,
    )

    back_strips = PartCollector()
    back_strip_inset = 1.5
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        back_strip = create_box(
            tool_head_additional_mount_plate_depth / 2,
            extruder_cage_mount_plate_thickness,
            extruder_size[2],
        )
        back_strip = align(
            back_strip,
            sprite_extruder,
            Alignment.STACK_BACK,
        )

        back_strip = align(back_strip, sprite_extruder, Alignment.CENTER, axes=[2])
        back_strip = align(back_strip, sprite_extruder, lr)

        back_strip = fit_part_between(
            back_strip,
            cut_normal=(0, 0, 1),
            limiting_start_part=sprite_mount_base_plate,
            limiting_end_part=part_fan_back_mount_plate,
        )

        back_strip = translate(-lr.sign * back_strip_inset, 0, 0)(back_strip)
        back_strips = back_strips.fuse(back_strip)

    top_strip_size = get_bounding_box_size(right_mount_plate)

    top_strip_bbox_min_x = get_bounding_box(right_mount_plate)[0][0]

    left_flange_width = tool_head_mount_machined_max_x - top_strip_bbox_min_x

    right_flange = create_box(left_flange_width, top_strip_size[1], BIG_THING)
    right_flange = align(right_flange, right_mount_plate, Alignment.CENTER)
    right_flange = align(right_flange, right_mount_plate, Alignment.LEFT)

    right_flange = fit_part_between(
        right_flange,
        cut_normal=(0, 0, 1),
        limiting_start_part=tool_head_mount_machined,
        limiting_end_part=right_mount_plate,
    )
    right_flange = tool_head_mount_machined.use_as_cutter_on(right_flange)

    left_mount_plate_bbox = get_bounding_box(left_mount_plate)
    left_mount_plate_bbox_size = get_bounding_box_size(left_mount_plate)
    left_mount_plate_max_x = left_mount_plate_bbox[1][0]

    left_flange_width = left_mount_plate_max_x - tool_head_mount_machined_min_x

    left_flange = create_box(
        left_flange_width,
        left_mount_plate_bbox_size[1] + extruder_cage_mount_plate_thickness,
        BIG_THING,
    )
    left_flange = align(left_flange, left_mount_plate, Alignment.CENTER)
    left_flange = align(left_flange, left_mount_plate, Alignment.BACK)
    left_flange = align(left_flange, left_mount_plate, Alignment.RIGHT)

    left_flange = fit_part_between(
        left_flange,
        cut_normal=(0, 0, 1),
        limiting_start_part=right_mount_plate,
        limiting_end_part=tool_head_mount_machined,
    )

    left_flange = tool_head_mount_machined.use_as_cutter_on(left_flange)

    flange_size = get_bounding_box_size(left_flange)

    left_flange_min_x = get_bounding_box(left_flange)[0][0]
    right_flange_max_x = get_bounding_box(right_flange)[1][0]

    flange_connector_width = right_flange_max_x - left_flange_min_x

    flange_connector = create_box(
        flange_connector_width, extruder_cage_mount_plate_thickness, flange_size[2]
    )
    flange_connector = align(flange_connector, left_flange, Alignment.LEFT)

    flange_connector = align(flange_connector, left_flange, Alignment.FRONT)
    flange_connector = align(
        flange_connector, tool_head_mount_machined, Alignment.STACK_BOTTOM
    )

    extruder_fan = sprite_extruder.get_named_non_production_part("fan")
    extruder_fan_bbox = get_bounding_box(extruder_fan)
    extruder_fan_min_x = extruder_fan_bbox[0][0]

    back_left_flange_width = extruder_fan_min_x - tool_head_mount_machined_min_x - 1
    back_left_flange = create_box(
        back_left_flange_width,
        extruder_size[1] + extruder_mount_base_plate_thickness,
        flange_size[2] / 2,
    )

    back_left_flange = align(back_left_flange, sprite_extruder, Alignment.FRONT)
    back_left_flange = align(back_left_flange, left_flange, Alignment.LEFT)
    back_left_flange = align(back_left_flange, left_flange, Alignment.TOP)

    left_flange = left_flange.fuse(back_left_flange)
    left_flange = tool_head_mount_machined.use_as_cutter_on(left_flange)

    cage_leader = sprite_mount_base_plate
    cage_leader = cage_leader.fuse(left_mount_plate)
    cage_leader = cage_leader.fuse(part_fan_back_mount_plate)
    cage_leader = cage_leader.fuse(nitehawk_rear_mount_plate)
    cage_leader = cage_leader.fuse(right_mount_plate)
    cage_leader = cage_leader.fuse(back_strips)


    flange_part = flange_connector.fuse(left_flange).fuse(right_flange)


    flange_top_cutter = create_box(BIG_THING, BIG_THING,BIG_THING)
    flange_top_cutter = align(flange_top_cutter, sprite_extruder, Alignment.CENTER)
    flange_top_cutter = align(flange_top_cutter, sprite_extruder, Alignment.STACK_TOP, stack_gap=tap_top_travel)
    
    flange_part = flange_part.cut(flange_top_cutter)

    # cage_leader = cage_leader.fuse(flange_part)

    cage_leader = sprite_extruder.use_as_cutter_on(cage_leader)
    for cutter in nitehawk_cutters.values():
        cage_leader = cage_leader.cut(cutter)

    cage_leader = cage_leader.cut(flange_top_cutter)
    cage = LeaderFollowersCuttersPart(cage_leader)

    for side_name, screw in sprite_mount_screws:
        cage.add_named_non_production_part(
            screw,
            f"sprite_mount_screw_{side_name}",
        )

    for index, screw in enumerate(nitehawk_mount_screws):
        cage.add_named_non_production_part(
            screw,
            f"nitehawk_mount_screw_{index}",
        )

    cage.add_named_cutter(mount_hole_cutter, "mount_hole_cutter")
    for name, cutter in nitehawk_cutters.items():
        cage.add_named_cutter(cutter, name)

    return cage
