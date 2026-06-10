"""Part fan assembly built from standalone injected fan artifacts."""

from shellforgepy.simple import *


def _create_side_mount_plate(
    *,
    sprite_extruder,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_thickness,
):
    side_mount_plate = create_box(
        tool_head_additional_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
    )
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.FRONT)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.STACK_BOTTOM)
    side_mount_plate = align(
        side_mount_plate,
        sprite_extruder,
        Alignment.STACK_LEFT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    side_mount_plate = translate(
        0,
        tool_head_additional_mount_plate_depth_offset,
        0,
    )(side_mount_plate)
    return side_mount_plate


def _create_duct_back_mount_plate_connector(
    *,
    sprite_extruder,
    tool_head_back_mount_plate_connector_height,
    tool_head_back_mount_plate_connector_thickness,
    tool_head_back_mount_plate_connector_width,
    duct_back_mount_plate_height,
    duct_back_mount_plate_height_border,
    duct_back_mount_plate_offset,
    duct_back_mount_plate_thickness,
    duct_back_mount_plate_width,
    duct_back_mount_plate_width_border,
):
    duct_back_mount_plate = create_box(
        duct_back_mount_plate_width,
        duct_back_mount_plate_height,
        duct_back_mount_plate_thickness,
    )
    cutout_width = duct_back_mount_plate_width - 2 * duct_back_mount_plate_width_border
    cutout_height = (
        duct_back_mount_plate_height - 2 * duct_back_mount_plate_height_border
    )
    cutout_fillet_radius = min(cutout_width, cutout_height) / 4

    duct_back_mount_plate_cutout = create_filleted_box(
        cutout_width,
        cutout_height,
        duct_back_mount_plate_thickness + 10,
        fillet_radius=cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    duct_back_mount_plate_cutout = align(
        duct_back_mount_plate_cutout,
        duct_back_mount_plate,
        Alignment.CENTER,
    )
    duct_back_mount_plate = duct_back_mount_plate.cut(duct_back_mount_plate_cutout)
    duct_back_mount_plate = rotate(90, axis=(1, 0, 0))(duct_back_mount_plate)
    duct_back_mount_plate = align(
        duct_back_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    duct_back_mount_plate = align(
        duct_back_mount_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
    )
    duct_back_mount_plate = align(
        duct_back_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    duct_back_mount_plate = translate(0, 0, duct_back_mount_plate_offset)(
        duct_back_mount_plate
    )

    duct_back_mount_plate_connector = create_box(
        tool_head_back_mount_plate_connector_width,
        tool_head_back_mount_plate_connector_thickness,
        tool_head_back_mount_plate_connector_height,
    )
    duct_back_mount_plate_connector = align(
        duct_back_mount_plate_connector,
        duct_back_mount_plate,
        Alignment.BACK,
    )
    duct_back_mount_plate_connector = align(
        duct_back_mount_plate_connector,
        duct_back_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    duct_back_mount_plate_connector = align(
        duct_back_mount_plate_connector,
        duct_back_mount_plate,
        Alignment.RIGHT,
    )
    return duct_back_mount_plate_connector


def _create_side_fan_mount_eye(
    *,
    side_fan_mount_plate,
    sprite_extruder,
    tool_head_additional_mount_plate_clearance,
):
    side_fan_mount_plate_size = get_bounding_box_size(side_fan_mount_plate)
    side_fan_mount_plate_height = side_fan_mount_plate_size[2]
    side_fan_mount_eye_height = side_fan_mount_plate_height / 4
    side_fan_mount_eye_fillet_radius = min(
        2,
        side_fan_mount_plate_size[0] / 4,
        7 / 4,
        side_fan_mount_eye_height / 2.5,
    )

    side_fan_mount_eye = create_filleted_box(
        side_fan_mount_plate_size[0],
        7,
        side_fan_mount_eye_height,
        fillet_radius=side_fan_mount_eye_fillet_radius,
        no_fillets_at=[Alignment.RIGHT, Alignment.LEFT, Alignment.FRONT],
    )
    side_fan_mount_eye = align(
        side_fan_mount_eye,
        side_fan_mount_plate,
        Alignment.CENTER,
    )
    side_fan_mount_eye = align(
        side_fan_mount_eye,
        side_fan_mount_plate,
        Alignment.STACK_BACK,
    )
    side_fan_mount_eye = align(
        side_fan_mount_eye,
        side_fan_mount_plate,
        Alignment.TOP,
    )
    side_fan_mount_eye = translate(0, 0, -3)(side_fan_mount_eye)
    side_fan_mount_eye = align(
        side_fan_mount_eye,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    if hasattr(sprite_extruder, "use_as_cutter_on"):
        side_fan_mount_eye = sprite_extruder.use_as_cutter_on(side_fan_mount_eye)
    return side_fan_mount_eye


def create_part_fan_assembly(
    *,
    sprite_extruder,
    front_part_fan,
    side_part_fan,
    blower_ring,
    duct_extension_width,
    part_fan_duct_extension_length,
    feeder_ring_height,
    feeder_ring_wall,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_thickness,
    tool_head_back_mount_plate_connector_height,
    tool_head_back_mount_plate_connector_thickness,
    tool_head_back_mount_plate_connector_width,
    duct_back_mount_plate_height,
    duct_back_mount_plate_height_border,
    duct_back_mount_plate_offset,
    duct_back_mount_plate_thickness,
    duct_back_mount_plate_width,
    duct_back_mount_plate_width_border,
):
    """Create fused part fan ducts from standalone part fans and blower ring."""

    front_mount_plate = front_part_fan.get_named_follower("mount_plate")
    front_outlet = front_part_fan.get_named_follower("outlet")
    side_fan_mount_plate = side_part_fan.get_named_follower("mount_plate")
    side_outlet = side_part_fan.get_named_follower("outlet")

    part_fans = front_mount_plate
    part_fans = part_fans.fuse(front_outlet)
    part_fans = part_fans.fuse(side_fan_mount_plate)
    part_fans = part_fans.fuse(side_outlet)

    duct_extension_body = create_box(
        duct_extension_width,
        part_fan_duct_extension_length,
        feeder_ring_height,
    )
    duct_extension = align(duct_extension_body, side_outlet, Alignment.CENTER)
    duct_extension = align(duct_extension, blower_ring, Alignment.TOP)
    duct_extension = align(duct_extension, side_outlet, Alignment.FRONT)

    side_fan_fused = side_part_fan.leader.fuse(side_outlet)
    side_fan_cutter = create_convex_hull(side_fan_fused)
    blower_ring_cutter = create_convex_hull(blower_ring.leader)

    duct_extension = duct_extension.cut(side_fan_cutter)
    duct_extension = duct_extension.cut(blower_ring_cutter)
    duct_extension_air_cutter = create_box(
        duct_extension_width - 2 * feeder_ring_wall,
        part_fan_duct_extension_length - 2 * feeder_ring_wall,
        feeder_ring_height - 2 * feeder_ring_wall,
    )
    duct_extension_air_cutter = align(
        duct_extension_air_cutter,
        duct_extension,
        Alignment.CENTER,
    )
    duct_extension = duct_extension.cut(duct_extension_air_cutter)

    front_part_fan_cutter = create_convex_hull(front_part_fan.leader, front_outlet)
    blower_ring_with_cut = blower_ring.leader.cut(front_part_fan_cutter)
    blower_ring_with_cut = blower_ring_with_cut.cut(duct_extension_air_cutter)

    side_mount_plate = _create_side_mount_plate(
        sprite_extruder=sprite_extruder,
        tool_head_additional_mount_plate_clearance=tool_head_additional_mount_plate_clearance,
        tool_head_additional_mount_plate_depth=tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_depth_offset=tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_height=tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_thickness=tool_head_additional_mount_plate_thickness,
    )
    duct_back_mount_plate_connector = _create_duct_back_mount_plate_connector(
        sprite_extruder=sprite_extruder,
        tool_head_back_mount_plate_connector_height=tool_head_back_mount_plate_connector_height,
        tool_head_back_mount_plate_connector_thickness=tool_head_back_mount_plate_connector_thickness,
        tool_head_back_mount_plate_connector_width=tool_head_back_mount_plate_connector_width,
        duct_back_mount_plate_height=duct_back_mount_plate_height,
        duct_back_mount_plate_height_border=duct_back_mount_plate_height_border,
        duct_back_mount_plate_offset=duct_back_mount_plate_offset,
        duct_back_mount_plate_thickness=duct_back_mount_plate_thickness,
        duct_back_mount_plate_width=duct_back_mount_plate_width,
        duct_back_mount_plate_width_border=duct_back_mount_plate_width_border,
    )
    side_fan_mount_eye = _create_side_fan_mount_eye(
        side_fan_mount_plate=side_fan_mount_plate,
        sprite_extruder=sprite_extruder,
        tool_head_additional_mount_plate_clearance=tool_head_additional_mount_plate_clearance,
    )

    part_fans = part_fans.fuse(blower_ring_with_cut)
    part_fans = part_fans.fuse(duct_extension)
    part_fans = part_fans.fuse(side_mount_plate)
    part_fans = part_fans.fuse(duct_back_mount_plate_connector)
    part_fans = part_fans.fuse(side_fan_mount_eye)

    retval = LeaderFollowersCuttersPart(part_fans)
    retval.add_named_non_production_part(side_mount_plate, "side_mount_plate")
    retval.add_named_non_production_part(
        duct_back_mount_plate_connector,
        "duct_back_mount_plate_connector",
    )
    retval.add_consumed_part_ref(
        front_part_fan.part_ref_for_named_follower("mount_plate")
    )
    retval.add_consumed_part_ref(front_part_fan.part_ref_for_named_follower("outlet"))
    retval.add_consumed_part_ref(
        side_part_fan.part_ref_for_named_follower("mount_plate")
    )
    retval.add_consumed_part_ref(side_part_fan.part_ref_for_named_follower("outlet"))
    retval.add_consumed_part_ref(blower_ring.part_ref_for_leader())

    return retval
