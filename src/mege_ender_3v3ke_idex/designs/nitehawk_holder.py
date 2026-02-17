"""
Nitehawk Holder

Usage:
    cd <project_root> && ./run.sh path/to/nitehawk_holder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/nitehawk_holder.py
"""

import logging
import os

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}

BIG_THING = 500

nitehawk_width = 51.3
nitehawk_height = 40.8
nitehawk_pcb_thickness = 1.6
nitehawk_top_width = 23
nitehawk_holes_y_offset = 16
nitehawk_holes_center_distance = 43
nitehawk_back_triangle_y_offset = 27.8
nitehawk_hole_diameter = 3.1
nitehawk_plug_width = 14
nitehawk_plug_thickness = 5.25
nitehawk_plug_length = 8.8
nitehawk_plug_overhang = 4
nitehawk_heater_connector_width = 7.7
nitehawk_heater_connector_length = 7.7
nitehawk_heater_connector_thickness = 8.8
nitehawk_heater_connector_x_offset_from_right = 10.3
nitehawk_heater_connector_y_offset_from_front = 5.1
nitehawk_front_cutter_width = 18.8
nitehawk_front_cutter_y_size = 7.0
nitehawk_front_cutter_back_width = 10.8
nitehawk_umbilical_connector_height = 13.2
nitehawk_umbilical_connector_gap = 0.15
nitehawk_umbilical_connector_cable_connector_height = 14.4
nitehawk_umbilical_connector_cable_connector_end_diameter = 9.4
nitehawk_umbilical_cable_diameter = 5.1
nitehawk_umbilical_cable_length = 30


def create_nitehawk_board():

    pcb = create_box(nitehawk_width, nitehawk_height, nitehawk_pcb_thickness)
    pcb = align(pcb, None, Alignment.CENTER)
    pcb_bbox = get_bounding_box(pcb)

    pcb = translate(0, -pcb_bbox[0][1], -pcb_bbox[0][2] / 2)(pcb)

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(nitehawk_hole_diameter / 2, nitehawk_pcb_thickness + 2)
        hole = align(hole, pcb, Alignment.CENTER)
        hole = align(hole, pcb, Alignment.FRONT)
        hole = translate(
            lr.sign * nitehawk_holes_center_distance / 2, nitehawk_holes_y_offset, 0
        )(hole)

        pcb = pcb.cut(hole)

        side_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
        side_cutter = align(side_cutter, None, Alignment.CENTER)

        side_cutter = translate(0, BIG_THING / 2, 0)(side_cutter)

        side_cutter = rotate(-lr.sign * 45)(side_cutter)
        side_cutter = translate(lr.sign * nitehawk_top_width / 2, nitehawk_height, 0)(
            side_cutter
        )

        pcb = pcb.cut(side_cutter)

    plug = create_box(
        nitehawk_plug_width, nitehawk_plug_length, nitehawk_plug_thickness
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
    plug = plug.fuse(umbilical_connector)

    umbilical_cable_connector_part = create_pyramid_stump(
        nitehawk_plug_width,
        nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_plug_thickness,
        nitehawk_umbilical_connector_cable_connector_end_diameter,
        nitehawk_umbilical_connector_cable_connector_height,
    )
    umbilical_cable_connector_part = rotate(-90, axis=(1, 0, 0))(
        umbilical_cable_connector_part
    )

    umbilical_cable_connector_part = align(
        umbilical_cable_connector_part, umbilical_connector, Alignment.CENTER
    )
    umbilical_cable_connector_part = align(
        umbilical_cable_connector_part, umbilical_connector, Alignment.STACK_BACK
    )

    plug = plug.fuse(umbilical_cable_connector_part)

    cable = create_cylinder(
        nitehawk_umbilical_cable_diameter / 2,
        nitehawk_umbilical_cable_length,
        direction=(0, 1, 0),
    )

    cable = align(cable, umbilical_cable_connector_part, Alignment.CENTER)
    cable = align(cable, umbilical_cable_connector_part, Alignment.STACK_BACK)
    plug = plug.fuse(cable)

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

    front_right_cutter = create_box(
        BIG_THING,
        BIG_THING,
        BIG_THING,
    )
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
    front_cutter_left = mirror(normal=(1, 0, 0), point=(0, 0, 0))(front_cutter)
    pcb = pcb.cut(front_cutter_left)

    pcb = pcb.cut(front_cutter)
    pcb = pcb.fuse(plug)

    pcb = pcb.fuse(heater_connector)

    return pcb


def create_nitehawk_holder():
    """Create the nitehawk_holder part."""
    # Example: simple box with a cylindrical hole
    width = 30
    depth = 20
    height = 10
    hole_radius = 4

    # Create base box
    part = create_box(width, depth, height)

    # Create a hole cutter
    hole = create_cylinder(hole_radius, height + 2)
    hole = align(hole, part, Alignment.CENTER)
    hole = translate(0, 0, -1)(hole)

    # Cut the hole
    part = part.cut(hole)

    return part


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_nitehawk_board()
    parts.add(part, "nitehawk_board", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("nitehawk_holder created successfully!")


if __name__ == "__main__":
    main()
