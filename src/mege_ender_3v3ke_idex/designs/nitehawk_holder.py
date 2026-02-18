"""
Nitehawk Holder

Usage:
    cd <project_root> && ./run.sh path/to/nitehawk_holder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/nitehawk_holder.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETG_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        #   "wall_loops": "1",
        # "bottom_shell_layers": "1",
        # "top_shell_layers": "1",
        #        "sparse_infill_density": "25%",
        "wall_loops": "1",
        "brim_type": "no_brim",
        "seam_position": "random",
    }
)


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

nitehawk_board_angle = 30
nitehawk_holder_thickness = 1.5
nitehawk_holder_width_extesion = 10
nitehawk_holder_width = NemaSizes.NEMA17.size_mm + nitehawk_holder_width_extesion
nitehawk_holder_height = NemaSizes.NEMA17.size_mm
nitehawk_holder_mount_tower_diameter = 6.5
nitehawk_holder_mount_tower_height = 5
nitehawk_holder_mount_tower_x_offset = 3
nitehawk_holder_mount_tower_y_offset = 8
nitehawk_holder_mount_screw_size = "M3"
nitehawk_holder_mount_cut_radius = nitehawk_holder_height * 0.5
nut_cutter_slack = 0.22
mount_tower_base_extension = 2.0


def create_nitehawk_board():

    pcb = create_box(nitehawk_width, nitehawk_height, nitehawk_pcb_thickness)
    pcb = align(pcb, None, Alignment.CENTER)
    pcb_bbox = get_bounding_box(pcb)

    pcb = translate(0, -pcb_bbox[0][1], -pcb_bbox[0][2] / 2)(pcb)

    hole_cutter_list = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(nitehawk_hole_diameter / 2, nitehawk_pcb_thickness + 2)
        hole = align(hole, pcb, Alignment.CENTER)
        hole = align(hole, pcb, Alignment.FRONT)
        hole = translate(
            lr.sign * nitehawk_holes_center_distance / 2, nitehawk_holes_y_offset, 0
        )(hole)

        pcb = pcb.cut(hole)
        hole_cutter_list.append(hole)

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

    retval = LeaderFollowersCuttersPart(pcb)

    retval.add_named_cutter(hole_cutter_list[0], "hole_1")
    retval.add_named_cutter(hole_cutter_list[1], "hole_2")

    return retval


def create_nitehawk_holder(sprite_extruder):
    """Create the nitehawk_holder part."""

    holder = create_box(
        nitehawk_holder_width, nitehawk_holder_height, nitehawk_holder_thickness
    )

    mount_tower_1 = create_cone(
        nitehawk_holder_mount_tower_diameter / 2 + mount_tower_base_extension,
        nitehawk_holder_mount_tower_diameter / 2,
        nitehawk_holder_mount_tower_height + nitehawk_holder_thickness,
    )

    mount_tower_2 = translate(nitehawk_holes_center_distance, 0, 0)(mount_tower_1)

    mount_towers = LeaderFollowersCuttersPart(mount_tower_1.fuse(mount_tower_2))

    screw_hole_cutter_1 = create_cylinder(
        MScrew.from_size(nitehawk_holder_mount_screw_size).clearance_hole_normal / 2,
        BIG_THING,
    )
    screw_hole_cutter_1 = align(screw_hole_cutter_1, mount_tower_1, Alignment.CENTER)

    nut_cuttter = create_nut(nitehawk_holder_mount_screw_size, slack=nut_cutter_slack)
    nut_cuttter = align(nut_cuttter, screw_hole_cutter_1, Alignment.CENTER)
    nut_cuttter = align(nut_cuttter, mount_tower_1, Alignment.BOTTOM)
    screw_hole_cutter_1 = screw_hole_cutter_1.fuse(nut_cuttter)

    mount_towers.add_named_cutter(screw_hole_cutter_1, "screw_hole_cutter_1")

    screw_hole_cutter_2 = align(screw_hole_cutter_1, mount_tower_2, Alignment.CENTER)
    mount_towers.add_named_cutter(screw_hole_cutter_2, "screw_hole_cutter_2")

    mount_towers = rotate(nitehawk_board_angle)(mount_towers)

    mount_towers = align(mount_towers, holder, Alignment.CENTER)
    mount_towers = align(mount_towers, holder, Alignment.FRONT)
    mount_towers = align(mount_towers, holder, Alignment.LEFT)
    mount_towers = align(mount_towers, holder, Alignment.BOTTOM)

    mount_towers = translate(
        nitehawk_holder_mount_tower_x_offset, nitehawk_holder_mount_tower_y_offset, 0
    )(mount_towers)

    holder = holder.fuse(mount_towers.leader)
    holder = mount_towers.use_as_cutter_on(holder)

    holder = LeaderFollowersCuttersPart(holder)
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_1"), "screw_hole_cutter_1"
    )
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_2"), "screw_hole_cutter_2"
    )

    holder = align(holder, sprite_extruder, Alignment.CENTER)

    holder = align(holder, sprite_extruder, Alignment.BACK)
    holder = align(holder, sprite_extruder, Alignment.LEFT)
    holder = align(holder, sprite_extruder, Alignment.STACK_TOP)

    holder = sprite_extruder.use_as_cutter_on(holder)

    cut_cylinder = create_cylinder(nitehawk_holder_mount_cut_radius, BIG_THING)
    cut_cylinder = align(cut_cylinder, holder, Alignment.CENTER)
    cut_cylinder = align(
        cut_cylinder,
        holder,
        Alignment.STACK_FRONT,
        stack_gap=-nitehawk_holder_mount_cut_radius,
    )
    cut_cylinder = align(
        cut_cylinder,
        holder,
        Alignment.STACK_RIGHT,
        stack_gap=-nitehawk_holder_mount_cut_radius - nitehawk_holder_width_extesion,
    )

    holder = holder.cut(cut_cylinder)

    return holder


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part

    sprite_extruder = create_sprite_extruder()

    parts.add(sprite_extruder, "sprite_extruder", flip=False, skip_in_production=True)

    holder = create_nitehawk_holder(sprite_extruder)

    parts.add(
        holder,
        "nitehawk_holder",
        flip=False,
        skip_in_production=False,
        color=(1.0, 0.0, 0.0),
    )

    holder_screw_hole_cutter_1 = holder.get_named_cutter("screw_hole_cutter_1")

    nitehawk_board = create_nitehawk_board()
    nitehawk_board = rotate(nitehawk_board_angle)(nitehawk_board)
    nitehawk_board = align(nitehawk_board, holder, Alignment.STACK_TOP, stack_gap=0.0)

    board_hole_1 = nitehawk_board.get_named_cutter("hole_1")

    align_board_translattion = align_translation(
        board_hole_1, holder_screw_hole_cutter_1, Alignment.CENTER, axes=[0, 1]
    )
    nitehawk_board = align_board_translattion(nitehawk_board)

    parts.add(nitehawk_board, "nitehawk_board", flip=False, skip_in_production=True)

    board_hole_1 = nitehawk_board.get_named_cutter("hole_1")

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
