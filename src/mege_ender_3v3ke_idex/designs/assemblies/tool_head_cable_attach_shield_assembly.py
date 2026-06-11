"""Simple cable-tie shield for the machined tool-head mount."""

from shellforgepy.simple import *

BIG_THING = 500


def create_tool_head_cable_attach_shield_assembly(
    *,
    tool_head_mount_machined,
    **params,
):
    """Create a simple vertical cable-tie shield mounted to the front holes."""

    prefix = "tool_head_cable_attach_shield_"
    mount_width = get_bounding_box_size(tool_head_mount_machined)[0]
    height = params[prefix + "height"]
    plate = create_filleted_box(
        mount_width,
        params[prefix + "thickness"],
        height,
        fillet_radius=params[prefix + "fillet_radius"],
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    plate = align(plate, tool_head_mount_machined, Alignment.CENTER, axes=[0])
    plate = align(plate, tool_head_mount_machined, Alignment.FRONT)
    plate = align(plate, tool_head_mount_machined, Alignment.STACK_TOP)

    shield = plate
    cutters = {}
    for side in [Alignment.LEFT, Alignment.RIGHT]:
        flange = create_box(
            params[prefix + "flange_width"],
            params[prefix + "flange_depth"],
            params[prefix + "flange_thickness"],
        )
        front_hole = tool_head_mount_machined.get_named_cutter(
            f"hole_drill_{side.name}_FRONT"
        )
        flange = align(flange, front_hole, Alignment.CENTER, axes=[0])
        flange = align(flange, tool_head_mount_machined, Alignment.FRONT)
        flange = align(flange, tool_head_mount_machined, Alignment.STACK_TOP)
        shield = shield.fuse(flange)
        cutters[f"flange_mount_hole_{side.name.lower()}"] = front_hole

    hole_radius = params[prefix + "hole_diameter"] / 2
    columns, rows = params[prefix + "hole_columns"], params[prefix + "hole_rows"]
    x_margin = params[prefix + "hole_x_margin"]
    z_margin = params[prefix + "hole_z_margin"]
    x_step = (mount_width - 2 * x_margin) / (columns - 1)
    z_step = (height - 2 * z_margin) / (rows - 1)
    for column in range(columns):
        for row in range(rows):
            hole = create_cylinder(hole_radius, BIG_THING, direction=(0, 1, 0))
            hole = align(hole, plate, Alignment.CENTER)
            hole = translate(
                -mount_width / 2 + x_margin + column * x_step,
                0,
                -height / 2 + z_margin + row * z_step,
            )(hole)
            cutters[f"cable_tie_hole_{column}_{row}"] = hole

    for cutter in cutters.values():
        shield = shield.cut(cutter)

    shield_part = LeaderFollowersCuttersPart(shield)
    for name, cutter in cutters.items():
        shield_part.add_named_cutter(cutter, name)
    return shield_part
