"""Declarative tool head assembly composed from assembly dependencies."""

from shellforgepy.simple import *


def create_tool_head_assembly(
    *,
    sprite_extruder,
    nitehawk_holder,
    part_fans,
    holder_mount_plate_depth,
    holder_mount_plate_left_extension,
    holder_mount_plate_size,
    holder_mount_plate_spacer,
    holder_mount_plate_thickness,
    holder_mount_plate_top_offset,
    nitehawk_holder_extruder_gap,
    nitehawk_holder_height_offset,
    nitehawk_holder_width_offset,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_fillet_radius,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_thickness,
    tool_head_additional_mount_plate_z_offset,
    tool_head_front_mount_plate_connector_height,
    tool_head_front_mount_plate_connector_thickness,
    tool_head_front_mount_plate_connector_width,
    duct_front_mount_plate_height,
    duct_front_mount_plate_height_border,
    duct_front_mount_plate_offset,
    duct_front_mount_plate_thickness,
    duct_front_mount_plate_width,
    duct_front_mount_plate_width_border,
):
    """Create the tool head assembly from built subassemblies."""

    # The holder and fan assemblies are positioned relative to the injected
    # sprite extruder through global YAML placement steps before this assembly
    # is built, so the assembly generator only consumes their resolved poses.
    del nitehawk_holder_extruder_gap
    del nitehawk_holder_height_offset
    del nitehawk_holder_width_offset

    holder = nitehawk_holder

    holder_mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        extension = holder_mount_plate_left_extension if lr == Alignment.LEFT else 0
        holder_mount_plate = create_box(
            holder_mount_plate_thickness,
            holder_mount_plate_depth + extension,
            holder_mount_plate_size,
        )

        if lr == Alignment.RIGHT:
            mount_box = create_box(
                holder_mount_plate_spacer,
                holder_mount_plate_size,
                holder_mount_plate_size,
            )
            mount_box = align(mount_box, holder_mount_plate, Alignment.CENTER)
            mount_box = align(mount_box, holder_mount_plate, Alignment.BACK)
            mount_box = align(mount_box, holder_mount_plate, Alignment.STACK_RIGHT)
            holder_mount_plate = holder_mount_plate.fuse(mount_box)

        holder_mount_plate = align(holder_mount_plate, holder, Alignment.CENTER)
        holder_mount_plate = align(holder_mount_plate, sprite_extruder, Alignment.TOP)
        holder_mount_plate = align(
            holder_mount_plate,
            sprite_extruder,
            lr.stack_alignment,
        )
        holder_mount_plate = align(holder_mount_plate, holder, Alignment.FRONT)
        holder_mount_plate = translate(0, 0, -holder_mount_plate_top_offset)(
            holder_mount_plate
        )
        holder_mount_plates = holder_mount_plates.fuse(holder_mount_plate)

    holder = holder.fuse(holder_mount_plates)

    
    retval = holder

    fans = part_fans
    retval = retval.merge_except_leader(fans)
    retval.add_named_non_production_part(fans.leader, "part_fans")

    parts_to_print = holder.leader

    side_mount_plate = create_filleted_box(
        tool_head_additional_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.FRONT)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BOTTOM)
    side_mount_plate = align(
        side_mount_plate,
        sprite_extruder,
        Alignment.STACK_LEFT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    side_mount_plate = translate(
        0,
        tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_z_offset,
    )(side_mount_plate)

    blower_ducts = fans.get_named_follower("blower_ducts")
    blower_ducts = blower_ducts.fuse(side_mount_plate)

    duct_front_mount_plate = create_box(
        duct_front_mount_plate_width,
        duct_front_mount_plate_height,
        duct_front_mount_plate_thickness,
    )

    cutout_width = (
        duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border
    )
    cutout_height = (
        duct_front_mount_plate_height - 2 * duct_front_mount_plate_height_border
    )
    cutout_fillet_radius = min(cutout_width, cutout_height) / 4

    duct_front_mount_plate_cutout = create_filleted_box(
        cutout_width,
        cutout_height,
        duct_front_mount_plate_thickness + 10,
        fillet_radius=cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    duct_front_mount_plate_cutout = align(
        duct_front_mount_plate_cutout,
        duct_front_mount_plate,
        Alignment.CENTER,
    )
    duct_front_mount_plate = duct_front_mount_plate.cut(duct_front_mount_plate_cutout)
    duct_front_mount_plate = rotate(90, axis=(1, 0, 0))(duct_front_mount_plate)
    duct_front_mount_plate = align(
        duct_front_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate,
        sprite_extruder,
        Alignment.STACK_FRONT,
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    duct_front_mount_plate = translate(0, 0, duct_front_mount_plate_offset)(
        duct_front_mount_plate
    )
    blower_ducts = blower_ducts.fuse(duct_front_mount_plate)

    duct_front_mount_plate_connector = create_box(
        tool_head_front_mount_plate_connector_width,
        tool_head_front_mount_plate_connector_thickness,
        tool_head_front_mount_plate_connector_height,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector,
        duct_front_mount_plate,
        Alignment.BACK,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector,
        duct_front_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector,
        duct_front_mount_plate,
        Alignment.LEFT,
    )
    blower_ducts = blower_ducts.fuse(duct_front_mount_plate_connector)

    for _, cutter in sprite_extruder.get_named_cutter_items():
        parts_to_print = parts_to_print.cut(cutter)
        blower_ducts = blower_ducts.cut(cutter)

    retval.leader = parts_to_print
    return retval
