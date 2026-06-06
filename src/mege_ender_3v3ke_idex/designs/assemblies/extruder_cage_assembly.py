"""Standalone extruder cage assembly."""

from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from shellforgepy.simple import *


def create_extruder_cage_assembly(
    *,
    sprite_extruder,
    nitehawk_board,
    extruder_cage_mount_plate_thickness,
    extruder_cage_mount_plate_fillet_radius,
    extruder_cage_flange_thickness,
    extruder_cage_screw_size,
    tool_head_mount_base_plate_height,
    tool_head_mount_sprite_mount_screw_length,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_z_offset,
    duct_front_mount_plate_height,
    duct_front_mount_plate_height_border,
    duct_front_mount_plate_offset,
    duct_front_mount_plate_width_border,
    holder_mount_plate_depth,
    holder_mount_plate_size,
    nitehawk_holder_extruder_gap,
    nitehawk_holder_mount_tower_diameter,
    nitehawk_holder_mount_tower_height,
    nitehawk_mount_tower_base_extension,
    nitehawk_holes_center_distance,
    nitehawk_nut_cutter_slack,
    BIG_THING,
):
    """Create a standalone extruder cage around the injected sprite extruder."""

    screw_record = MScrew.from_size(extruder_cage_screw_size)
    sprite_extruder_size = get_bounding_box_size(sprite_extruder)
    sprite_extruder_body_size = get_bounding_box_size(sprite_extruder.leader)
    mount_hole_cutter = sprite_extruder.get_named_cutter("mount_hole_cutter")

    sprite_mount_base_plate = create_filleted_box(
        sprite_extruder_size[0] + 2 * extruder_cage_flange_thickness,
        extruder_cage_mount_plate_thickness,
        tool_head_mount_base_plate_height,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        mount_hole_cutter,
        Alignment.CENTER,
    )
    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        sprite_extruder,
        Alignment.TOP,
    )
    sprite_mount_base_plate = align(
        sprite_mount_base_plate,
        sprite_extruder,
        Alignment.STACK_FRONT,
    )
    sprite_mount_base_plate = sprite_extruder.use_as_cutter_on(sprite_mount_base_plate)
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
        screw = rotate(90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_guide, Alignment.CENTER)
        screw = align(screw, sprite_mount_base_plate, Alignment.FRONT)
        screw = translate(0, -screw_record.cylinder_head_height, 0)(screw)
        sprite_mount_screws.append((side_name, screw))

    part_fan_side_mount_plate = create_filleted_box(
        extruder_cage_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    part_fan_side_mount_plate = align(
        part_fan_side_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    part_fan_side_mount_plate = align(
        part_fan_side_mount_plate,
        sprite_extruder,
        Alignment.BACK,
    )
    part_fan_side_mount_plate = align(
        part_fan_side_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    part_fan_side_mount_plate = align(
        part_fan_side_mount_plate,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    part_fan_side_mount_plate = translate(
        0,
        tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_z_offset,
    )(part_fan_side_mount_plate)
    part_fan_side_mount_plate = sprite_extruder.use_as_cutter_on(
        part_fan_side_mount_plate
    )

    duct_front_mount_plate_width = sprite_extruder_body_size[0]
    part_fan_front_mount_plate = create_filleted_box(
        duct_front_mount_plate_width,
        duct_front_mount_plate_height,
        extruder_cage_mount_plate_thickness,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    front_mount_plate_cutout = create_filleted_box(
        duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border,
        duct_front_mount_plate_height - 2 * duct_front_mount_plate_height_border,
        extruder_cage_mount_plate_thickness + 10,
        fillet_radius=(
            min(
                duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border,
                duct_front_mount_plate_height
                - 2 * duct_front_mount_plate_height_border,
            )
            / 4
        ),
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    front_mount_plate_cutout = align(
        front_mount_plate_cutout,
        part_fan_front_mount_plate,
        Alignment.CENTER,
    )
    part_fan_front_mount_plate = part_fan_front_mount_plate.cut(
        front_mount_plate_cutout
    )
    part_fan_front_mount_plate = rotate(90, axis=(1, 0, 0))(part_fan_front_mount_plate)
    part_fan_front_mount_plate = align(
        part_fan_front_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    part_fan_front_mount_plate = align(
        part_fan_front_mount_plate,
        sprite_extruder,
        Alignment.STACK_FRONT,
    )
    part_fan_front_mount_plate = align(
        part_fan_front_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    part_fan_front_mount_plate = translate(0, 0, duct_front_mount_plate_offset)(
        part_fan_front_mount_plate
    )
    part_fan_front_mount_plate = sprite_extruder.use_as_cutter_on(
        part_fan_front_mount_plate
    )

    tower_base_radius = (
        nitehawk_holder_mount_tower_diameter / 2 + nitehawk_mount_tower_base_extension
    )
    tower_tip_radius = nitehawk_holder_mount_tower_diameter / 2
    nitehawk_plate_width = nitehawk_holes_center_distance + 2 * (
        tower_base_radius + holder_mount_plate_size
    )
    nitehawk_plate_depth = extruder_cage_mount_plate_thickness
    nitehawk_plate_height = max(
        holder_mount_plate_depth,
        2 * tower_base_radius + holder_mount_plate_size,
    )

    nitehawk_rear_mount_plate = create_filleted_box(
        nitehawk_plate_width,
        nitehawk_plate_depth,
        nitehawk_plate_height,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    nitehawk_rear_mount_plate = align(
        nitehawk_rear_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    nitehawk_rear_mount_plate = align(
        nitehawk_rear_mount_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
        stack_gap=nitehawk_holder_extruder_gap,
    )
    nitehawk_rear_mount_plate = align(
        nitehawk_rear_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )

    nitehawk_mount_screws = []
    nitehawk_cutters = {}
    nitehawk_towers = PartCollector()
    tower_spacing_reference = create_box(
        nitehawk_holes_center_distance + 2 * tower_base_radius,
        nitehawk_plate_depth,
        nitehawk_plate_height,
    )
    tower_spacing_reference = align(
        tower_spacing_reference,
        nitehawk_rear_mount_plate,
        Alignment.CENTER,
    )

    for index, lr in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        tower = create_cone(
            tower_base_radius,
            tower_tip_radius,
            nitehawk_holder_mount_tower_height,
        )
        tower = rotate(-90, axis=(1, 0, 0))(tower)
        tower = align(tower, nitehawk_rear_mount_plate, Alignment.CENTER)
        tower = align(tower, nitehawk_rear_mount_plate, Alignment.STACK_BACK)
        tower = align(tower, tower_spacing_reference, lr)

        hole_cutter = create_cylinder(
            screw_record.clearance_hole_normal / 2,
            BIG_THING,
            direction=(0, 1, 0),
        )
        hole_cutter = align(hole_cutter, tower, Alignment.CENTER)

        nut_pocket = create_nut(
            extruder_cage_screw_size,
            height=screw_record.nut_thickness + nitehawk_nut_cutter_slack,
            slack=nitehawk_nut_cutter_slack,
            no_hole=True,
        )
        nut_pocket = rotate(-90, axis=(1, 0, 0))(nut_pocket)
        nut_pocket = align(nut_pocket, hole_cutter, Alignment.CENTER)
        nut_pocket = align(nut_pocket, nitehawk_rear_mount_plate, Alignment.BACK)

        nitehawk_cutters[f"nitehawk_mount_hole_{index}"] = hole_cutter
        nitehawk_cutters[f"nitehawk_mount_nut_pocket_{index}"] = nut_pocket
        nitehawk_towers = nitehawk_towers.fuse(tower)

        screw = create_cylinder_screw(
            extruder_cage_screw_size,
            tool_head_mount_sprite_mount_screw_length,
        )
        screw = rotate(-90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_cutter, Alignment.CENTER)
        screw = align(screw, tower, Alignment.BACK)
        screw = translate(0, screw_record.cylinder_head_height, 0)(screw)
        nitehawk_mount_screws.append(screw)

    nitehawk_rear_mount_plate = nitehawk_rear_mount_plate.fuse(nitehawk_towers)
    for cutter in nitehawk_cutters.values():
        nitehawk_rear_mount_plate = nitehawk_rear_mount_plate.cut(cutter)
    nitehawk_rear_mount_plate = sprite_extruder.use_as_cutter_on(
        nitehawk_rear_mount_plate
    )

    cage_leader = sprite_mount_base_plate
    cage_leader = cage_leader.fuse(part_fan_side_mount_plate)
    cage_leader = cage_leader.fuse(part_fan_front_mount_plate)
    cage_leader = cage_leader.fuse(nitehawk_rear_mount_plate)
    cage_leader = sprite_extruder.use_as_cutter_on(cage_leader)
    for cutter in nitehawk_cutters.values():
        cage_leader = cage_leader.cut(cutter)

    cage = LeaderFollowersCuttersPart(cage_leader)
    cage.add_named_follower(sprite_mount_base_plate, "sprite_mount_base_plate")
    cage.add_named_follower(part_fan_side_mount_plate, "part_fan_side_mount_plate")
    cage.add_named_follower(part_fan_front_mount_plate, "part_fan_front_mount_plate")
    cage.add_named_follower(nitehawk_rear_mount_plate, "nitehawk_rear_mount_plate")

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
