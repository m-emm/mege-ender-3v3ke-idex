"""Declarative machined tool head mount assembly."""

from shellforgepy.simple import *

BIG_THING = 500


def create_tool_head_mount_machined_assembly(
    *,
    carriage,
    sprite_extruder,
    x_axis_belt_carriage,
    tool_head_mount_carriage_mount_plate_fillet_radius,
    tool_head_mount_carriage_mount_plate_thickness,
    tool_head_mount_carriage_mount_plate_width,
    tool_head_mount_y_extension,
    drive_position,
):
    """Create a machined tool head mount carriage plate."""

    _ = (sprite_extruder, x_axis_belt_carriage)

    extruder_size = get_bounding_box_size(sprite_extruder)

    extruder_bbox = get_bounding_box(sprite_extruder)
    carriage_bbox = get_bounding_box(carriage)

    mount_plate_y_size = carriage_bbox[1][1] - extruder_bbox[0][1]

    normalized_drive_position = str(drive_position).strip().lower()
    if normalized_drive_position == "bottom":
        drive_position = Alignment.BOTTOM
    elif normalized_drive_position == "top":
        drive_position = Alignment.TOP
    else:
        raise ValueError(f"Unsupported drive_position '{drive_position}'")

    carriage_size = get_bounding_box_size(carriage)

    carriage_mount_plate = create_box(
        tool_head_mount_carriage_mount_plate_width,
        mount_plate_y_size,
        tool_head_mount_carriage_mount_plate_thickness,
        # fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        # no_fillets_at=[Alignment.BOTTOM],
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.STACK_TOP,
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.BACK)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.RIGHT if drive_position == Alignment.BOTTOM else Alignment.LEFT,
    )

    carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)

    extruder_cutout_cutter = create_filleted_box(
        extruder_size[0] + 4,
        extruder_size[1] + 4,
        BIG_THING,
        fillet_radius=3,
    )

    extruder_cutout_cutter = align(
        extruder_cutout_cutter, sprite_extruder, Alignment.CENTER
    )

    carriage_mount_plate = carriage_mount_plate.cut(extruder_cutout_cutter)

    return LeaderFollowersCuttersPart(leader=carriage_mount_plate)
