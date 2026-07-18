"""Simple cable-tie shield for the machined tool-head mount."""

from shellforgepy.simple import *

BIG_THING = 500
MOUNT_SCREW_LENGTH = 12


def create_tool_head_cable_attach_shield_assembly(
    *,
    tool_head_mount_machined,
    light_barrier_assembly=None,
    tool_head_cable_attach_shield_height,
    tool_head_cable_attach_shield_thickness,
    tool_head_cable_attach_shield_fillet_radius,
    tool_head_cable_attach_shield_plate_flange_overlap,
    tool_head_cable_attach_shield_flange_width,
    tool_head_cable_attach_shield_flange_depth,
    tool_head_cable_attach_shield_flange_thickness,
    tool_head_cable_attach_shield_hole_diameter,
    tool_head_cable_attach_shield_hole_columns,
    tool_head_cable_attach_shield_hole_rows,
    tool_head_cable_attach_shield_hole_x_margin,
    tool_head_cable_attach_shield_hole_z_margin,
):
    """Create a simple vertical cable-tie shield mounted to the front holes."""

    mount_width = get_bounding_box_size(tool_head_mount_machined)[0]
    plate = create_filleted_box(
        mount_width,
        tool_head_cable_attach_shield_thickness,
        tool_head_cable_attach_shield_height,
        fillet_radius=tool_head_cable_attach_shield_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    plate = align(plate, tool_head_mount_machined, Alignment.CENTER)
    plate = align(
        plate,
        tool_head_mount_machined,
        Alignment.STACK_FRONT,
        stack_gap=-tool_head_cable_attach_shield_plate_flange_overlap,
    )
    plate = align(plate, tool_head_mount_machined, Alignment.STACK_TOP)

    shield = plate
    cutters = {}
    mount_screws = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        flange = create_box(
            tool_head_cable_attach_shield_flange_width,
            tool_head_cable_attach_shield_flange_depth,
            tool_head_cable_attach_shield_flange_thickness,
        )
        front_hole = tool_head_mount_machined.get_named_cutter(
            f"hole_drill_{lr.name}_FRONT"
        )
        flange = align(flange, tool_head_mount_machined, lr)
        flange = align(flange, plate, Alignment.FRONT)
        flange = align(flange, tool_head_mount_machined, Alignment.STACK_TOP)
        shield = shield.fuse(flange)
        cutters[f"flange_mount_hole_{lr.name.lower()}"] = front_hole

        screw = create_cylinder_screw("M3", length=MOUNT_SCREW_LENGTH)
        screw = align(screw, front_hole, Alignment.CENTER, axes=[0, 1])
        screw = translate(
            0,
            0,
            get_bounding_box(flange)[1][2] - MOUNT_SCREW_LENGTH,
        )(screw)
        mount_screws[f"flange_mount_screw_{lr.name.lower()}"] = screw

    hole_radius = tool_head_cable_attach_shield_hole_diameter / 2
    columns = tool_head_cable_attach_shield_hole_columns
    rows = tool_head_cable_attach_shield_hole_rows
    x_margin = tool_head_cable_attach_shield_hole_x_margin
    z_margin = tool_head_cable_attach_shield_hole_z_margin
    x_step = (mount_width - 2 * x_margin) / (columns - 1)
    z_step = (tool_head_cable_attach_shield_height - 2 * z_margin) / (rows - 1)
    for column in range(columns):
        for row in range(rows):
            hole = create_cylinder(hole_radius, BIG_THING, direction=(0, 1, 0))
            hole = align(hole, plate, Alignment.CENTER)
            hole = translate(
                -mount_width / 2 + x_margin + column * x_step,
                0,
                -tool_head_cable_attach_shield_height / 2 + z_margin + row * z_step,
            )(hole)
            cutters[f"cable_tie_hole_{column}_{row}"] = hole

    for cutter in cutters.values():
        shield = shield.cut(cutter)

    if light_barrier_assembly is not None:
        light_barrier_cutter = materialize_bounding_box(
            light_barrier_assembly, x_enlargement=2, y_enlargement=1, z_enlargement=4
        )

        light_barrier_bbox_center = get_bounding_box_center(light_barrier_cutter)

        shield = shield.cut(light_barrier_cutter)

        flag_thickness = 2.25
        flag_depth = 8
        flag_height = 10
        flag_holder_size = 11

        tap_flag = create_box(flag_thickness, flag_depth, flag_height)
        tap_flag = align(tap_flag, light_barrier_assembly, Alignment.CENTER)
        tap_flag = align(tap_flag, plate, Alignment.STACK_BACK)

        tap_flag = align(tap_flag, light_barrier_assembly, Alignment.BOTTOM)
        top_flag_bbox = get_bounding_box(tap_flag)
        tap_flag = translate(
            0, 0, light_barrier_bbox_center[2] - top_flag_bbox[0][2] + 0.2
        )(tap_flag)

        shield = shield.fuse(tap_flag)

        tap_flag_holder = create_pyramid_stump(
            flag_holder_size,
            flag_thickness,
            flag_height / 2,
            flag_height / 2,
            flag_depth,
        )
        tap_flag_holder = rotate(-90, axis=[1, 0, 0])(tap_flag_holder)

        tap_flag_holder = align(tap_flag_holder, tap_flag, Alignment.CENTER)
        tap_flag_holder = align(tap_flag_holder, plate, Alignment.BOTTOM)
        tap_flag_holder = align(tap_flag_holder, plate, Alignment.STACK_BACK)

        shield = shield.fuse(tap_flag_holder)

    shield_part = LeaderFollowersCuttersPart(shield)
    for name, cutter in cutters.items():
        shield_part.add_named_cutter(cutter, name)
    for name, screw in mount_screws.items():
        shield_part.add_named_non_production_part(screw, name)
    return shield_part
