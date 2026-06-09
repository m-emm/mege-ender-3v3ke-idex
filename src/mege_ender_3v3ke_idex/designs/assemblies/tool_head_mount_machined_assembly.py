"""Declarative machined tool head mount assembly."""

from shellforgepy.metrics import Material, record_weight_metric
from shellforgepy.simple import *

BIG_THING = 500

TOOL_HEAD_MOUNT_MACHINED_METRICS_ID = "tool_head_mount_machined"


def _normalize_drive_position(drive_position):
    normalized_drive_position = str(drive_position).strip().lower()
    if normalized_drive_position == "bottom":
        return Alignment.BOTTOM
    if normalized_drive_position == "top":
        return Alignment.TOP
    raise ValueError(f"Unsupported drive_position '{drive_position}'")


def _create_vertical_hole(*, center_x, center_y, diameter):
    return translate(center_x, center_y, 0)(create_cylinder(diameter / 2, BIG_THING))


def _cut_hole_grid(part, *, x_positions, y_positions, diameter, name_prefix, cutters):
    for x_index, x_position in enumerate(x_positions):
        for y_index, y_position in enumerate(y_positions):
            hole = _create_vertical_hole(
                center_x=x_position,
                center_y=y_position,
                diameter=diameter,
            )
            part = part.cut(hole)
            cutters[f"{name_prefix}_{x_index}_{y_index}"] = hole
    return part


def create_tool_head_mount_machined_assembly(
    *,
    carriage,
    tool_head_mount_machined_plate_fillet_radius,
    tool_head_mount_machined_plate_thickness,
    tool_head_mount_machined_plate_width,
    tool_head_mount_machined_plate_depth,
    tool_head_mount_machined_cutout_width,
    tool_head_mount_machined_cutout_depth,
    tool_head_mount_machined_cutout_center_x,
    tool_head_mount_machined_cutout_center_y,
    tool_head_mount_machined_cutout_fillet_radius,
    tool_head_mount_machined_sprite_mount_hole_diameter,
    tool_head_mount_machined_sprite_mount_hole_x_0,
    tool_head_mount_machined_sprite_mount_hole_x_1,
    tool_head_mount_machined_sprite_mount_hole_y_0,
    tool_head_mount_machined_sprite_mount_hole_y_1,
    tool_head_mount_machined_sprite_mount_hole_y_2,
    tool_head_mount_machined_carriage_mount_hole_diameter,
    tool_head_mount_machined_carriage_mount_hole_x_0,
    tool_head_mount_machined_carriage_mount_hole_x_1,
    tool_head_mount_machined_carriage_mount_hole_x_2,
    tool_head_mount_machined_carriage_mount_hole_x_3,
    tool_head_mount_machined_carriage_mount_hole_y_0,
    tool_head_mount_machined_carriage_mount_hole_y_1,
    drive_position,
    record_metrics=False,
):
    """Create a machined tool head mount carriage plate."""

    _ = tool_head_mount_machined_plate_fillet_radius

    drive_position = _normalize_drive_position(drive_position)

    carriage_mount_plate = create_box(
        tool_head_mount_machined_plate_width,
        tool_head_mount_machined_plate_depth,
        tool_head_mount_machined_plate_thickness,
    )

    cutters = {}

    extruder_cutout_cutter = create_filleted_box(
        tool_head_mount_machined_cutout_width,
        tool_head_mount_machined_cutout_depth,
        BIG_THING,
        fillet_radius=tool_head_mount_machined_cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.FRONT],
    )
    cutout_center = get_bounding_box_center(extruder_cutout_cutter)
    extruder_cutout_cutter = translate(
        tool_head_mount_machined_cutout_center_x - cutout_center[0],
        tool_head_mount_machined_cutout_center_y - cutout_center[1],
        tool_head_mount_machined_plate_thickness / 2 - cutout_center[2],
    )(extruder_cutout_cutter)
    carriage_mount_plate = carriage_mount_plate.cut(extruder_cutout_cutter)
    cutters["extruder_cutout"] = extruder_cutout_cutter

    carriage_mount_plate = _cut_hole_grid(
        carriage_mount_plate,
        x_positions=[
            tool_head_mount_machined_sprite_mount_hole_x_0,
            tool_head_mount_machined_sprite_mount_hole_x_1,
        ],
        y_positions=[
            tool_head_mount_machined_sprite_mount_hole_y_0,
            tool_head_mount_machined_sprite_mount_hole_y_1,
            tool_head_mount_machined_sprite_mount_hole_y_2,
        ],
        diameter=tool_head_mount_machined_sprite_mount_hole_diameter,
        name_prefix="sprite_mount_hole",
        cutters=cutters,
    )

    carriage_mount_plate = _cut_hole_grid(
        carriage_mount_plate,
        x_positions=[
            tool_head_mount_machined_carriage_mount_hole_x_0,
            tool_head_mount_machined_carriage_mount_hole_x_1,
            tool_head_mount_machined_carriage_mount_hole_x_2,
            tool_head_mount_machined_carriage_mount_hole_x_3,
        ],
        y_positions=[
            tool_head_mount_machined_carriage_mount_hole_y_0,
            tool_head_mount_machined_carriage_mount_hole_y_1,
        ],
        diameter=tool_head_mount_machined_carriage_mount_hole_diameter,
        name_prefix="carriage_mount_hole",
        cutters=cutters,
    )

    retval = LeaderFollowersCuttersPart(leader=carriage_mount_plate)
    for name, cutter in cutters.items():
        retval.add_named_cutter(cutter, name)

    retval = align(retval, carriage, Alignment.CENTER)
    retval = align(
        retval,
        carriage,
        Alignment.STACK_TOP,
    )
    retval = align(retval, carriage, Alignment.BACK)
    retval = align(
        retval,
        carriage,
        Alignment.RIGHT if drive_position == Alignment.BOTTOM else Alignment.LEFT,
    )

    carriage_mount_plate = retval.leader

    if record_metrics:
        record_weight_metric(
            TOOL_HEAD_MOUNT_MACHINED_METRICS_ID,
            Material.ALUMINUM,
            get_volume(carriage_mount_plate),
            part_id="tool_head_mount_machined",
        )

    return retval
