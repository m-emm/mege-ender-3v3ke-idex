"""Standalone extruder cage assembly."""

from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from shellforgepy.simple import *


def _create_sprite_mount_hole_guides(*, mount_hole_cutter):
    mount_hole_cutter_bbox = get_bounding_box(mount_hole_cutter)
    mount_hole_cutter_size = get_bounding_box_size(mount_hole_cutter)
    mount_hole_cutter_center = get_bounding_box_center(mount_hole_cutter)

    mount_hole_diameter = mount_hole_cutter_size[0] - NemaSizes.NEMA17.hole_dist_mm
    if mount_hole_diameter <= 0:
        raise ValueError(
            "Sprite extruder mount hole cutter bbox does not match a NEMA17 pattern"
        )

    hole_radius = mount_hole_diameter / 2
    hole_length = mount_hole_cutter_size[1]
    top_hole_center_z = mount_hole_cutter_bbox[1][2] - hole_radius
    hole_centers_x = [
        mount_hole_cutter_bbox[0][0] + hole_radius,
        mount_hole_cutter_bbox[1][0] - hole_radius,
    ]

    hole_guides = []
    for side_name, hole_center_x in zip(["left", "right"], hole_centers_x):
        hole = create_cylinder(hole_radius, hole_length, direction=(0, 1, 0))
        hole = align(hole, mount_hole_cutter, Alignment.CENTER)
        hole = translate(
            hole_center_x - mount_hole_cutter_center[0],
            0,
            top_hole_center_z - mount_hole_cutter_center[2],
        )(hole)
        hole_guides.append((side_name, hole))

    return hole_guides


def _create_sprite_mount_screws(
    *,
    mount_hole_cutter,
    mount_base_plate,
    screw_size,
    screw_length,
):
    cylinder_head_height = MScrew.from_size(screw_size).cylinder_head_height
    screws = []

    for side_name, hole_guide in _create_sprite_mount_hole_guides(
        mount_hole_cutter=mount_hole_cutter,
    ):
        screw = create_cylinder_screw(screw_size, screw_length)
        screw = rotate(-90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_guide, Alignment.CENTER)
        screw = align(screw, mount_base_plate, Alignment.FRONT)
        screw = translate(0, -cylinder_head_height, 0)(screw)
        screws.append((side_name, screw))

    return screws


def _cut_with_sprite_mount_cutters(part, *, sprite_extruder):
    for _, cutter in sprite_extruder.get_named_cutter_items():
        part = part.cut(cutter)
    return part


def _create_sprite_mount_base_plate(
    *,
    sprite_extruder,
    extruder_cage_flange_thickness,
    extruder_cage_mount_plate_fillet_radius,
    extruder_cage_mount_plate_thickness,
    extruder_cage_screw_size,
    tool_head_mount_base_plate_height,
    tool_head_mount_sprite_mount_screw_length,
):
    sprite_extruder_size = get_bounding_box_size(sprite_extruder)
    mount_hole_cutter = sprite_extruder.get_named_cutter("mount_hole_cutter")

    mount_base_plate = create_filleted_box(
        sprite_extruder_size[0] + 2 * extruder_cage_flange_thickness,
        extruder_cage_mount_plate_thickness,
        tool_head_mount_base_plate_height,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    mount_base_plate = align(mount_base_plate, mount_hole_cutter, Alignment.CENTER)
    mount_base_plate = align(mount_base_plate, mount_hole_cutter, Alignment.TOP)
    mount_base_plate = align(
        mount_base_plate,
        sprite_extruder,
        Alignment.STACK_FRONT,
    )
    mount_base_plate = mount_base_plate.cut(mount_hole_cutter)
    mount_base_plate = mount_base_plate.cut(sprite_extruder.leader)

    sprite_mount_screws = _create_sprite_mount_screws(
        mount_hole_cutter=mount_hole_cutter,
        mount_base_plate=mount_base_plate,
        screw_size=extruder_cage_screw_size,
        screw_length=tool_head_mount_sprite_mount_screw_length,
    )

    return mount_base_plate, sprite_mount_screws, mount_hole_cutter


def _create_part_fan_mount_plates(
    *,
    sprite_extruder,
    extruder_cage_mount_plate_fillet_radius,
    extruder_cage_mount_plate_thickness,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_z_offset,
    tool_head_front_mount_plate_connector_height,
    tool_head_front_mount_plate_connector_width,
    duct_front_mount_plate_height,
    duct_front_mount_plate_height_border,
    duct_front_mount_plate_offset,
    duct_front_mount_plate_width_border,
):
    sprite_extruder_size = get_bounding_box_size(sprite_extruder.leader)
    duct_front_mount_plate_width = sprite_extruder_size[0]

    side_mount_plate = create_filleted_box(
        extruder_cage_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BACK)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BOTTOM)
    side_mount_plate = align(
        side_mount_plate,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    side_mount_plate = translate(
        0,
        tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_z_offset,
    )(side_mount_plate)

    front_mount_plate = create_filleted_box(
        duct_front_mount_plate_width,
        duct_front_mount_plate_height,
        extruder_cage_mount_plate_thickness,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    cutout_width = (
        duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border
    )
    cutout_height = (
        duct_front_mount_plate_height - 2 * duct_front_mount_plate_height_border
    )
    cutout_fillet_radius = min(cutout_width, cutout_height) / 4

    front_mount_plate_cutout = create_filleted_box(
        cutout_width,
        cutout_height,
        extruder_cage_mount_plate_thickness + 10,
        fillet_radius=cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    front_mount_plate_cutout = align(
        front_mount_plate_cutout,
        front_mount_plate,
        Alignment.CENTER,
    )
    front_mount_plate = front_mount_plate.cut(front_mount_plate_cutout)
    front_mount_plate = rotate(90, axis=(1, 0, 0))(front_mount_plate)
    front_mount_plate = align(front_mount_plate, sprite_extruder, Alignment.CENTER)
    front_mount_plate = align(
        front_mount_plate,
        sprite_extruder,
        Alignment.STACK_FRONT,
    )
    front_mount_plate = align(front_mount_plate, sprite_extruder, Alignment.BOTTOM)
    front_mount_plate = translate(0, 0, duct_front_mount_plate_offset)(
        front_mount_plate
    )

    front_mount_plate_connector = create_box(
        tool_head_front_mount_plate_connector_width,
        extruder_cage_mount_plate_thickness,
        tool_head_front_mount_plate_connector_height,
    )
    front_mount_plate_connector = align(
        front_mount_plate_connector,
        front_mount_plate,
        Alignment.BACK,
    )
    front_mount_plate_connector = align(
        front_mount_plate_connector,
        front_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    front_mount_plate_connector = align(
        front_mount_plate_connector,
        front_mount_plate,
        Alignment.LEFT,
    )

    return side_mount_plate, front_mount_plate, front_mount_plate_connector


def _create_nitehawk_rear_mount_plate(
    *,
    sprite_extruder,
    extruder_cage_mount_plate_fillet_radius,
    extruder_cage_mount_plate_thickness,
    extruder_cage_screw_size,
    holder_mount_plate_depth,
    holder_mount_plate_size,
    holder_mount_plate_top_offset,
    nitehawk_holder_mount_tower_diameter,
    nitehawk_holder_mount_tower_height,
    nitehawk_mount_tower_base_extension,
    nitehawk_holes_center_distance,
    nitehawk_nut_cutter_slack,
    tool_head_additional_mount_plate_clearance,
    tool_head_mount_sprite_mount_screw_length,
    BIG_THING,
):
    screw_record = MScrew.from_size(extruder_cage_screw_size)
    tower_base_radius = (
        nitehawk_holder_mount_tower_diameter / 2 + nitehawk_mount_tower_base_extension
    )
    tower_tip_radius = nitehawk_holder_mount_tower_diameter / 2
    plate_width = nitehawk_holes_center_distance + 2 * (
        tower_base_radius + holder_mount_plate_size
    )
    plate_depth = extruder_cage_mount_plate_thickness
    plate_height = max(
        holder_mount_plate_depth,
        2 * tower_base_radius + holder_mount_plate_size,
    )

    rear_mount_plate = create_filleted_box(
        plate_width,
        plate_depth,
        plate_height,
        fillet_radius=extruder_cage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    rear_mount_plate = align(rear_mount_plate, sprite_extruder, Alignment.CENTER)
    rear_mount_plate = align(
        rear_mount_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    rear_mount_plate = align(rear_mount_plate, sprite_extruder, Alignment.TOP)
    rear_mount_plate = translate(0, 0, -holder_mount_plate_top_offset)(rear_mount_plate)

    screws = []
    cutters = {}
    towers = PartCollector()
    tower_spacing_reference = create_box(
        nitehawk_holes_center_distance + 2 * tower_base_radius,
        plate_depth,
        plate_height,
    )
    tower_spacing_reference = align(
        tower_spacing_reference,
        rear_mount_plate,
        Alignment.CENTER,
    )

    for index, lr in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        tower = create_cone(
            tower_base_radius,
            tower_tip_radius,
            nitehawk_holder_mount_tower_height,
        )
        tower = rotate(-90, axis=(1, 0, 0))(tower)
        tower = align(tower, rear_mount_plate, Alignment.CENTER)
        tower = align(tower, rear_mount_plate, Alignment.STACK_BACK)
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
        nut_pocket = align(nut_pocket, tower, Alignment.BACK)

        cutters[f"nitehawk_mount_hole_{index}"] = hole_cutter
        cutters[f"nitehawk_mount_nut_pocket_{index}"] = nut_pocket
        towers = towers.fuse(tower)

        screw = create_cylinder_screw(
            extruder_cage_screw_size,
            tool_head_mount_sprite_mount_screw_length,
        )
        screw = rotate(-90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_cutter, Alignment.CENTER)
        screw = align(screw, tower, Alignment.BACK)
        screw = translate(0, screw_record.cylinder_head_height, 0)(screw)
        screws.append(screw)

    rear_mount_plate = rear_mount_plate.fuse(towers)
    for cutter in cutters.values():
        rear_mount_plate = rear_mount_plate.cut(cutter)

    return rear_mount_plate, screws, cutters


def create_extruder_cage_assembly(
    *,
    sprite_extruder,
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
    tool_head_front_mount_plate_connector_height,
    tool_head_front_mount_plate_connector_width,
    duct_front_mount_plate_height,
    duct_front_mount_plate_height_border,
    duct_front_mount_plate_offset,
    duct_front_mount_plate_width_border,
    holder_mount_plate_depth,
    holder_mount_plate_size,
    holder_mount_plate_top_offset,
    nitehawk_holder_mount_tower_diameter,
    nitehawk_holder_mount_tower_height,
    nitehawk_mount_tower_base_extension,
    nitehawk_holes_center_distance,
    nitehawk_nut_cutter_slack,
    BIG_THING,
):
    """Create a standalone extruder cage around the injected sprite extruder."""

    mount_plate_fillet_radius = min(
        extruder_cage_mount_plate_fillet_radius,
        extruder_cage_mount_plate_thickness / 2 - 0.01,
    )

    sprite_mount_base_plate, sprite_mount_screws, mount_hole_cutter = (
        _create_sprite_mount_base_plate(
            sprite_extruder=sprite_extruder,
            extruder_cage_flange_thickness=extruder_cage_flange_thickness,
            extruder_cage_mount_plate_fillet_radius=mount_plate_fillet_radius,
            extruder_cage_mount_plate_thickness=(extruder_cage_mount_plate_thickness),
            extruder_cage_screw_size=extruder_cage_screw_size,
            tool_head_mount_base_plate_height=tool_head_mount_base_plate_height,
            tool_head_mount_sprite_mount_screw_length=(
                tool_head_mount_sprite_mount_screw_length
            ),
        )
    )
    (
        part_fan_side_mount_plate,
        part_fan_front_mount_plate,
        part_fan_front_mount_plate_connector,
    ) = _create_part_fan_mount_plates(
        sprite_extruder=sprite_extruder,
        extruder_cage_mount_plate_fillet_radius=mount_plate_fillet_radius,
        extruder_cage_mount_plate_thickness=extruder_cage_mount_plate_thickness,
        tool_head_additional_mount_plate_clearance=(
            tool_head_additional_mount_plate_clearance
        ),
        tool_head_additional_mount_plate_depth=tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_depth_offset=(
            tool_head_additional_mount_plate_depth_offset
        ),
        tool_head_additional_mount_plate_height=tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_z_offset=(
            tool_head_additional_mount_plate_z_offset
        ),
        tool_head_front_mount_plate_connector_height=(
            tool_head_front_mount_plate_connector_height
        ),
        tool_head_front_mount_plate_connector_width=(
            tool_head_front_mount_plate_connector_width
        ),
        duct_front_mount_plate_height=duct_front_mount_plate_height,
        duct_front_mount_plate_height_border=duct_front_mount_plate_height_border,
        duct_front_mount_plate_offset=duct_front_mount_plate_offset,
        duct_front_mount_plate_width_border=duct_front_mount_plate_width_border,
    )
    nitehawk_rear_mount_plate, nitehawk_mount_screws, nitehawk_cutters = (
        _create_nitehawk_rear_mount_plate(
            sprite_extruder=sprite_extruder,
            extruder_cage_mount_plate_fillet_radius=mount_plate_fillet_radius,
            extruder_cage_mount_plate_thickness=extruder_cage_mount_plate_thickness,
            extruder_cage_screw_size=extruder_cage_screw_size,
            holder_mount_plate_depth=holder_mount_plate_depth,
            holder_mount_plate_size=holder_mount_plate_size,
            holder_mount_plate_top_offset=holder_mount_plate_top_offset,
            nitehawk_holder_mount_tower_diameter=(nitehawk_holder_mount_tower_diameter),
            nitehawk_holder_mount_tower_height=nitehawk_holder_mount_tower_height,
            nitehawk_mount_tower_base_extension=nitehawk_mount_tower_base_extension,
            nitehawk_holes_center_distance=nitehawk_holes_center_distance,
            nitehawk_nut_cutter_slack=nitehawk_nut_cutter_slack,
            tool_head_additional_mount_plate_clearance=(
                tool_head_additional_mount_plate_clearance
            ),
            tool_head_mount_sprite_mount_screw_length=(
                tool_head_mount_sprite_mount_screw_length
            ),
            BIG_THING=BIG_THING,
        )
    )

    part_fan_side_mount_plate = _cut_with_sprite_mount_cutters(
        part_fan_side_mount_plate,
        sprite_extruder=sprite_extruder,
    )
    part_fan_front_mount_plate = _cut_with_sprite_mount_cutters(
        part_fan_front_mount_plate,
        sprite_extruder=sprite_extruder,
    )
    part_fan_front_mount_plate_connector = _cut_with_sprite_mount_cutters(
        part_fan_front_mount_plate_connector,
        sprite_extruder=sprite_extruder,
    )
    nitehawk_rear_mount_plate = _cut_with_sprite_mount_cutters(
        nitehawk_rear_mount_plate,
        sprite_extruder=sprite_extruder,
    )

    cage_leader = sprite_mount_base_plate
    cage_leader = cage_leader.fuse(part_fan_side_mount_plate)
    cage_leader = cage_leader.fuse(part_fan_front_mount_plate)
    cage_leader = cage_leader.fuse(part_fan_front_mount_plate_connector)
    cage_leader = cage_leader.fuse(nitehawk_rear_mount_plate)
    cage_leader = cage_leader.cut(mount_hole_cutter)
    for cutter in nitehawk_cutters.values():
        cage_leader = cage_leader.cut(cutter)

    cage = LeaderFollowersCuttersPart(cage_leader)
    cage.add_named_follower(sprite_mount_base_plate, "sprite_mount_base_plate")
    cage.add_named_follower(part_fan_side_mount_plate, "part_fan_side_mount_plate")
    cage.add_named_follower(part_fan_front_mount_plate, "part_fan_front_mount_plate")
    cage.add_named_follower(
        part_fan_front_mount_plate_connector,
        "part_fan_front_mount_plate_connector",
    )
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
