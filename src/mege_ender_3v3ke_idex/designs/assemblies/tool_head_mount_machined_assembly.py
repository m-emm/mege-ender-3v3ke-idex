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
    tool_head_mount_machined_sprite_mount_hole_x_inset,
    tool_head_mount_machined_sprite_mount_hole_front_y_inset,
    tool_head_mount_machined_sprite_mount_hole_primary_y_pitch,
    tool_head_mount_machined_sprite_mount_hole_secondary_y_pitch,
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

    sprite_reference = create_box(
        tool_head_mount_machined_cutout_width,
        tool_head_mount_machined_sprite_mount_hole_primary_y_pitch
        + 2 * tool_head_mount_machined_sprite_mount_hole_front_y_inset,
        tool_head_mount_machined_plate_thickness,
    )
    sprite_reference = align(
        sprite_reference,
        carriage_mount_plate,
        Alignment.CENTER,
        axes=[0, 2],
    )
    sprite_reference = align(
        sprite_reference,
        carriage_mount_plate,
        Alignment.FRONT,
    )

    drill_radius = tool_head_mount_machined_sprite_mount_hole_diameter / 2
    back_extra_y_offset = (
        tool_head_mount_machined_sprite_mount_hole_secondary_y_pitch
        - tool_head_mount_machined_sprite_mount_hole_front_y_inset
        - drill_radius
    )

    for lr in [Alignment.RIGHT, Alignment.LEFT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            drill = create_cylinder(drill_radius, 50)
            drill = align(drill, carriage_mount_plate, Alignment.CENTER)
            drill = align(drill, carriage_mount_plate, lr.edge_alignment)
            drill = align(drill, sprite_reference, fb.edge_alignment)
            drill = translate(
                -lr.sign * tool_head_mount_machined_sprite_mount_hole_x_inset,
                -fb.sign * tool_head_mount_machined_sprite_mount_hole_front_y_inset,
                0,
            )(drill)
            carriage_mount_plate = carriage_mount_plate.cut(drill)
            cutters[f"hole_drill_{lr.name}_{fb.name}"] = drill

            if fb == Alignment.BACK:
                drill = create_cylinder(drill_radius, 100)
                drill = align(drill, carriage_mount_plate, Alignment.CENTER)
                drill = align(drill, carriage_mount_plate, lr.edge_alignment)
                drill = align(drill, sprite_reference, Alignment.STACK_BACK)
                drill = translate(
                    -lr.sign * tool_head_mount_machined_sprite_mount_hole_x_inset,
                    back_extra_y_offset,
                    0,
                )(drill)
                carriage_mount_plate = carriage_mount_plate.cut(drill)
                cutters[f"hole_drill_{lr.name}_{fb.name}_extra"] = drill

    carriage_mount_plate = LeaderFollowersCuttersPart(leader=carriage_mount_plate)
    for name, cutter in cutters.items():
        carriage_mount_plate.add_named_cutter(cutter, name)
    carriage_mount_plate.add_named_non_production_part(
        extruder_cutout_cutter,
        "extruder_cutout_reference",
    )
    carriage_mount_plate.set_hidden_by_default("extruder_cutout_reference")

    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.STACK_TOP,
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.BACK)

    for alignment in [Alignment.RIGHT, Alignment.LEFT]:
        carriage_mount_plate = align(carriage_mount_plate, carriage, alignment)
        carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)

    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.RIGHT if drive_position == Alignment.BOTTOM else Alignment.LEFT,
    )

    if record_metrics:
        record_weight_metric(
            TOOL_HEAD_MOUNT_MACHINED_METRICS_ID,
            Material.ALUMINUM,
            get_volume(carriage_mount_plate.leader),
            part_id="tool_head_mount_machined",
        )

    return carriage_mount_plate
