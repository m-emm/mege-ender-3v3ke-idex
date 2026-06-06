"""Nitehawk toolhead board assembly."""

from shellforgepy.simple import *


def create_nitehawk_board_assembly(
    *,
    nitehawk_width,
    nitehawk_height,
    nitehawk_pcb_thickness,
    nitehawk_hole_diameter,
    nitehawk_holes_center_distance,
    nitehawk_holes_y_offset,
    nitehawk_top_width,
    nitehawk_plug_width,
    nitehawk_plug_length,
    nitehawk_plug_thickness,
    nitehawk_plug_overhang,
    nitehawk_umbilical_connector_height,
    nitehawk_umbilical_connector_gap,
    nitehawk_umbilical_connector_cable_connector_end_diameter,
    nitehawk_umbilical_connector_cable_connector_height,
    nitehawk_umbilical_cable_diameter,
    nitehawk_umbilical_cable_length,
    nitehawk_heater_connector_width,
    nitehawk_heater_connector_length,
    nitehawk_heater_connector_thickness,
    nitehawk_heater_connector_x_offset_from_right,
    nitehawk_heater_connector_y_offset_from_front,
    nitehawk_front_cutter_width,
    nitehawk_front_cutter_back_width,
    nitehawk_front_cutter_y_size,
    BIG_THING,
):
    """Create a visual/mechanical reference model of the Nitehawk toolhead board."""

    pcb = create_box(nitehawk_width, nitehawk_height, nitehawk_pcb_thickness)
    pcb = align(pcb, None, Alignment.CENTER)
    pcb_bbox = get_bounding_box(pcb)
    pcb = translate(0, -pcb_bbox[0][1], -pcb_bbox[0][2] / 2)(pcb)

    hole_cutters = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(nitehawk_hole_diameter / 2, nitehawk_pcb_thickness + 2)
        hole = align(hole, pcb, Alignment.CENTER)
        hole = align(hole, pcb, Alignment.FRONT)
        hole = translate(
            lr.sign * nitehawk_holes_center_distance / 2,
            nitehawk_holes_y_offset,
            0,
        )(hole)

        pcb = pcb.cut(hole)
        hole_cutters.append(hole)

        side_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
        side_cutter = align(side_cutter, None, Alignment.CENTER)
        side_cutter = translate(0, BIG_THING / 2, 0)(side_cutter)
        side_cutter = rotate(-lr.sign * 45)(side_cutter)
        side_cutter = translate(lr.sign * nitehawk_top_width / 2, nitehawk_height, 0)(
            side_cutter
        )
        pcb = pcb.cut(side_cutter)

    plug = create_box(
        nitehawk_plug_width,
        nitehawk_plug_length,
        nitehawk_plug_thickness,
    )
    plug = align(plug, pcb, Alignment.CENTER)
    plug = align(plug, pcb, Alignment.BACK)
    plug = align(plug, pcb, Alignment.STACK_TOP)
    plug = translate(0, nitehawk_plug_overhang, 0)(plug)

    umbilical_connector = create_box(
        nitehawk_plug_width,
        nitehawk_umbilical_connector_height,
        nitehawk_plug_thickness,
    )
    umbilical_connector = align(umbilical_connector, plug, Alignment.CENTER)
    umbilical_connector = align(
        umbilical_connector,
        plug,
        Alignment.STACK_BACK,
        stack_gap=nitehawk_umbilical_connector_gap,
    )
    umbilical_cable_connector = create_pyramid_stump(
        nitehawk_plug_width,
        nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_plug_thickness,
        nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_umbilical_connector_cable_connector_height,
    )
    umbilical_cable_connector = rotate(-90, axis=(1, 0, 0))(umbilical_cable_connector)
    umbilical_cable_connector = align(
        umbilical_cable_connector,
        umbilical_connector,
        Alignment.CENTER,
    )
    umbilical_cable_connector = align(
        umbilical_cable_connector,
        umbilical_connector,
        Alignment.STACK_BACK,
    )

    umbilical_cable = create_cylinder(
        nitehawk_umbilical_cable_diameter / 2,
        nitehawk_umbilical_cable_length,
        direction=(0, 1, 0),
    )
    umbilical_cable = align(
        umbilical_cable, umbilical_cable_connector, Alignment.CENTER
    )
    umbilical_cable = align(
        umbilical_cable,
        umbilical_cable_connector,
        Alignment.STACK_BACK,
    )

    heater_connector = create_box(
        nitehawk_heater_connector_width,
        nitehawk_heater_connector_length,
        nitehawk_heater_connector_thickness,
    )
    heater_connector = align(heater_connector, pcb, Alignment.RIGHT)
    heater_connector = align(heater_connector, pcb, Alignment.FRONT)
    heater_connector = align(heater_connector, pcb, Alignment.STACK_TOP)
    heater_connector = translate(
        -nitehawk_heater_connector_x_offset_from_right,
        nitehawk_heater_connector_y_offset_from_front,
        0,
    )(heater_connector)

    front_right_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    front_right_cutter = align(front_right_cutter, None, Alignment.CENTER)
    front_right_cutter = align(
        front_right_cutter,
        pcb,
        Alignment.STACK_RIGHT,
        stack_gap=-(nitehawk_front_cutter_width - nitehawk_front_cutter_back_width),
    )
    front_right_cutter = align(
        front_right_cutter,
        pcb,
        Alignment.STACK_FRONT,
        stack_gap=-nitehawk_front_cutter_y_size,
    )

    front_cutter = create_right_triangle(
        nitehawk_front_cutter_back_width,
        nitehawk_front_cutter_y_size,
        BIG_THING,
        extrusion_direction=(0, 0, 1),
        a_normal=(1, 0, 0),
        b_normal=(0, 1, 0),
    )
    front_cutter = align(front_cutter, pcb, Alignment.CENTER)
    front_cutter = align(front_cutter, pcb, Alignment.FRONT)
    front_cutter = align(front_cutter, front_right_cutter, Alignment.STACK_LEFT)
    front_cutter = front_cutter.fuse(front_right_cutter)

    pcb = pcb.cut(front_cutter)
    pcb = pcb.cut(mirror(normal=(1, 0, 0), point=(0, 0, 0))(front_cutter))

    board = LeaderFollowersCuttersPart(pcb)
    board.add_named_cutter(hole_cutters[0], "hole_1")
    board.add_named_cutter(hole_cutters[1], "hole_2")
    board.add_named_follower(pcb, "pcb")
    board.add_named_follower(plug, "plug")
    board.add_named_follower(umbilical_connector, "umbilical_connector")
    board.add_named_follower(
        umbilical_cable_connector,
        "umbilical_cable_connector",
    )
    board.add_named_follower(umbilical_cable, "umbilical_cable")
    board.add_named_follower(heater_connector, "heater_connector")

    return board
