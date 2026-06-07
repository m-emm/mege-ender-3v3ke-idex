"""Declarative machined tool head mount assembly."""

from shellforgepy.metrics import Material, record_weight_metric
from shellforgepy.simple import *

BIG_THING = 500

screw_hole_inset = 5
screw_size = "M3"
TOOL_HEAD_MOUNT_MACHINED_METRICS_ID = "tool_head_mount_machined"


def create_tool_head_mount_machined_assembly(
    *,
    carriage,
    sprite_extruder,
    x_axis_belt_carriage,
    tool_head_mount_machined_plate_fillet_radius,
    tool_head_mount_machined_plate_thickness,
    tool_head_mount_machined_plate_width,
    drive_position,
    record_metrics=False,
):
    """Create a machined tool head mount carriage plate."""

    _ = (x_axis_belt_carriage, tool_head_mount_machined_plate_fillet_radius)

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

    carriage_mount_plate = create_box(
        tool_head_mount_machined_plate_width,
        mount_plate_y_size,
        tool_head_mount_machined_plate_thickness,
        # fillet_radius=tool_head_mount_machined_plate_fillet_radius,
        # no_fillets_at=[Alignment.BOTTOM],
    )
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

    screw_hole_diameter = MScrew.from_size(screw_size).clearance_hole_loose

    for lr in [Alignment.RIGHT, Alignment.LEFT]:

        for fb in [Alignment.FRONT, Alignment.BACK]:
            drill = create_cylinder(screw_hole_diameter / 2, 50)

            drill = align(drill, carriage_mount_plate, Alignment.CENTER)
            drill = align(drill, carriage_mount_plate, lr.edge_alignment)
            drill = align(drill, sprite_extruder, fb.edge_alignment)

            drill = translate(
                -lr.sign * screw_hole_inset, -fb.sign * screw_hole_inset, 0
            )(drill)

            carriage_mount_plate = carriage_mount_plate.cut(drill)

            if fb == Alignment.BACK:
                drill = create_cylinder(screw_hole_diameter / 2, 100)

                drill = align(drill, carriage_mount_plate, Alignment.CENTER)
                drill = align(drill, carriage_mount_plate, lr.edge_alignment)
                drill = align(drill, sprite_extruder, Alignment.STACK_BACK)
                drill = translate(
                    -lr.sign * screw_hole_inset, fb.sign * screw_hole_inset, 0
                )(drill)

                carriage_mount_plate = carriage_mount_plate.cut(drill)

    if record_metrics:
        record_weight_metric(
            TOOL_HEAD_MOUNT_MACHINED_METRICS_ID,
            Material.ALUMINUM,
            get_volume(carriage_mount_plate),
            part_id="tool_head_mount_machined",
        )

    return LeaderFollowersCuttersPart(leader=carriage_mount_plate)
