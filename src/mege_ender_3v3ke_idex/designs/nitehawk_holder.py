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

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401; Keep the materials menu around, in case we want to switch back to other materials
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_3devops.process_data.mender3.process_data_utils import (
    augment_with_layer_height,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
# Keep layer-height derivation consistent with process_data helpers:
# 0.90 -> 0.28mm on 0.4mm nozzle.
PROCESS_DATA = augment_with_layer_height(PROCESS_DATA, layer_height_factor=0.9)

PROCESS_DATA["process_overrides"].update(
    {
        # Strength/interlayer-adhesion bias for PLAGFHT:
        # hotter, thicker layers, less cooling, lower speed/acceleration.
        "nozzle_temperature_initial_layer": "230",
        "nozzle_temperature": "230",
        "initial_layer_print_height": "0.28",
        "fan_min_speed": "25",
        "fan_max_speed": "45",
        "overhang_fan_speed": "60",
        "outer_wall_speed": "75",
        "top_surface_speed": "75",
        "inner_wall_speed": "130",
        "internal_solid_infill_speed": "130",
        "solid_infill_speed": "130",
        "sparse_infill_speed": "130",
        "outer_wall_acceleration": "2800",
        "top_surface_acceleration": "2800",
        "inner_wall_acceleration": "4500",
        "solid_infill_acceleration": "4500",
        "sparse_infill_acceleration": "4500",
        "wall_loops": "3",
        "brim_type": "no_brim",
        "sparse_infill_density": "60%",  # it is quite brittle, this plagfht
    }
)


BIG_THING = 500


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
    retval = LeaderFollowersCuttersPart(pcb)
    retval.add_named_follower(pcb, "pcb")

    retval = retval.fuse(plug)
    retval = retval.fuse(heater_connector)

    retval.add_named_cutter(hole_cutter_list[0], "hole_1")
    retval.add_named_cutter(hole_cutter_list[1], "hole_2")

    return retval


def create_nitehawk_holder():
    """Create the nitehawk_holder part."""

    mount_tower_1 = create_cone(
        nitehawk_holder_mount_tower_diameter / 2 + nitehawk_mount_tower_base_extension,
        nitehawk_holder_mount_tower_diameter / 2,
        nitehawk_holder_mount_tower_height + nitehawk_holder_thickness,
    )

    mount_tower_2 = translate(nitehawk_holes_center_distance, 0, 0)(mount_tower_1)

    mount_towers = LeaderFollowersCuttersPart(mount_tower_1.fuse(mount_tower_2))

    cable_attchment = create_filleted_box(
        nitehawk_holder_cable_attachment_width,
        nitehawk_holder_cable_attachment_length,
        nitehawk_holder_cable_attachment_thickness,
        fillet_radius=nitehawk_holder_cable_attachment_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.FRONT],
    )

    cable_attchment_hole_cutters = PartCollector()
    for i in range(nitehawk_holder_cable_attachment_num_holes):
        for lr in [Alignment.LEFT, Alignment.RIGHT]:
            hole_cutter = create_cylinder(
                nitehawk_holder_cable_attachment_holes_diameter / 2, BIG_THING
            )
            hole_cutter = align(hole_cutter, cable_attchment, Alignment.CENTER)
            hole_cutter = align(
                hole_cutter,
                cable_attchment,
                lr.stack_alignment,
                stack_gap=-1.5 * nitehawk_holder_cable_attachment_holes_diameter,
            )
            hole_cutter = translate(
                0,
                i
                * (
                    nitehawk_holder_cable_attachment_length
                    / (nitehawk_holder_cable_attachment_num_holes + 1)
                ),
                0,
            )(hole_cutter)

            cable_attchment_hole_cutters = cable_attchment_hole_cutters.fuse(
                hole_cutter
            )

    cable_attchment_hole_cutters = align(
        cable_attchment_hole_cutters, cable_attchment, Alignment.CENTER, axes=[0, 1]
    )

    cable_attchment = cable_attchment.cut(cable_attchment_hole_cutters)

    cable_attchment = align(cable_attchment, mount_towers, Alignment.CENTER)
    cable_attchment = align(cable_attchment, mount_towers, Alignment.BOTTOM)
    cable_attchment = align(cable_attchment, mount_towers, Alignment.FRONT)
    cable_attchment = translate(0, nitehawk_holder_cable_attachment_y_offset, 0)(
        cable_attchment
    )

    cable_attachment_bevel = create_right_triangle(
        nitehawk_holder_cable_attachment_thickness,
        nitehawk_holder_cable_attachment_thickness,
        nitehawk_holder_cable_attachment_width,
        extrusion_direction=(1, 0, 0),
        a_normal=(0, 0, -1),
        b_normal=(0, -1, 0),
    )
    cable_attachment_bevel = align(
        cable_attachment_bevel, cable_attchment, Alignment.CENTER
    )
    cable_attachment_bevel = align(
        cable_attachment_bevel, cable_attchment, Alignment.STACK_FRONT
    )
    cable_attachment_bevel = align(
        cable_attachment_bevel, cable_attchment, Alignment.TOP
    )

    cable_attchment = cable_attchment.fuse(cable_attachment_bevel)

    mount_towers.add_named_follower(cable_attchment, "cable_attachment")

    screw_hole_cutter_1 = create_cylinder(
        MScrew.from_size(nitehawk_holder_mount_screw_size).clearance_hole_normal / 2,
        BIG_THING,
    )
    screw_hole_cutter_1 = align(screw_hole_cutter_1, mount_tower_1, Alignment.CENTER)

    nut_cuttter = create_nut(
        nitehawk_holder_mount_screw_size, slack=nitehawk_nut_cutter_slack
    )
    nut_cuttter = align(nut_cuttter, screw_hole_cutter_1, Alignment.CENTER)
    nut_cuttter = align(nut_cuttter, mount_tower_1, Alignment.BOTTOM)
    screw_hole_cutter_1 = screw_hole_cutter_1.fuse(nut_cuttter)

    mount_towers.add_named_cutter(screw_hole_cutter_1, "screw_hole_cutter_1")

    screw_hole_cutter_2 = align(screw_hole_cutter_1, mount_tower_2, Alignment.CENTER)
    mount_towers.add_named_cutter(screw_hole_cutter_2, "screw_hole_cutter_2")

    mount_towers = rotate(nitehawk_board_angle)(mount_towers)

    holder = create_filleted_box(
        nitehawk_holder_width,
        nitehawk_holder_height,
        nitehawk_holder_thickness,
        fillet_radius=nitehawk_holder_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    holder_front_cutter = create_pyramid_stump(
        nitehawk_holder_width - 4 * nitehawk_holder_slit_height,
        nitehawk_holder_width - 8 * nitehawk_holder_slit_height,
        nitehawk_holder_thickness + 2,
        nitehawk_holder_thickness + 2,
        nitehawk_holder_slit_height,
    )
    holder_front_cutter = rotate(-90, axis=(1, 0, 0))(holder_front_cutter)
    holder_front_cutter = align(holder_front_cutter, holder, Alignment.CENTER)
    holder_front_cutter = align(holder_front_cutter, holder, Alignment.FRONT)
    holder = holder.cut(holder_front_cutter)

    mount_towers = align(mount_towers, holder, Alignment.CENTER)
    mount_towers = align(mount_towers, holder, Alignment.BOTTOM)

    mount_towers = translate(
        nitehawk_holder_mount_tower_x_offset, nitehawk_holder_mount_tower_y_offset, 0
    )(mount_towers)

    holder = holder.fuse(mount_towers.leader)

    holder = LeaderFollowersCuttersPart(holder)

    holder = mount_towers.use_as_cutter_on(holder)
    holder.add_named_follower(
        mount_towers.get_named_follower("cable_attachment"), "cable_attachment"
    )

    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_1"), "screw_hole_cutter_1"
    )
    holder.add_named_cutter(
        mount_towers.get_named_cutter("screw_hole_cutter_2"), "screw_hole_cutter_2"
    )

    holder = holder.fuse(holder.get_named_follower("cable_attachment"))

    holder_screw_hole_cutter_1 = holder.get_named_cutter("screw_hole_cutter_1")

    nitehawk_board = create_nitehawk_board()
    nitehawk_board = rotate(nitehawk_board_angle)(nitehawk_board)
    nitehawk_pcb = nitehawk_board.get_named_follower("pcb")
    board_alignment = align_translation(
        nitehawk_pcb, holder, Alignment.STACK_TOP, stack_gap=0.0
    )

    nitehawk_board = board_alignment(nitehawk_board)

    board_hole_1 = nitehawk_board.get_named_cutter("hole_1")

    align_board_translattion = align_translation(
        board_hole_1, holder_screw_hole_cutter_1, Alignment.CENTER, axes=[0, 1]
    )
    nitehawk_board = align_board_translattion(nitehawk_board)

    holder.add_named_non_production_part(nitehawk_board.leader, "nitehawk_board")

    nitehawk_pcb = nitehawk_board.get_named_follower("pcb")

    holder.add_named_non_production_part(nitehawk_pcb, "nitehawk_pcb")

    holder = rotate(-90, axis=(1, 0, 0))(holder)

    return holder


def align_holder_to_extruder(holder, extruder):

    nitehawk_board = holder.get_named_non_production_part("nitehawk_pcb")

    board_aligner = align_translation(nitehawk_board, extruder, Alignment.LEFT)

    holder = board_aligner(holder)

    holder = align(
        holder, extruder, Alignment.STACK_BACK, stack_gap=nitehawk_holder_extruder_gap
    )

    holder = align(holder, extruder, Alignment.BOTTOM)
    holder = translate(nitehawk_holder_width_offset, nitehawk_holder_height_offset, 0)(
        holder
    )

    return holder


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part

    sprite_extruder = create_sprite_extruder()

    parts.add(sprite_extruder, "sprite_extruder", flip=False, skip_in_production=True)

    for name, npp in sprite_extruder.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    holder = create_nitehawk_holder()
    holder = rotate(180, axis=(0, 1, 0))(holder)

    holder = align_holder_to_extruder(holder, sprite_extruder)

    parts.add(
        holder,
        "nitehawk_holder",
        flip=False,
        skip_in_production=False,
        color=(1.0, 0.0, 0.0),
    )
    for i, (name, npp) in enumerate(holder.get_named_non_production_part_items()):
        if i > 0:
            continue
        _logger.info(f"Adding non-production part: {name}")

        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            color=(
                0.0,
                0.0,
                0.7 + 0.3 * i / len(holder.get_named_non_production_part_items()),
            ),
        )

    # for name, follower in holder.get_named_follower_items():
    #     parts.add(follower, name, flip=False, skip_in_production=True)

    # holder_screw_hole_cutter_1 = holder.get_named_cutter("screw_hole_cutter_1")

    # nitehawk_board = create_nitehawk_board()
    # nitehawk_board = rotate(nitehawk_board_angle)(nitehawk_board)
    # nitehawk_pcb = nitehawk_board.get_named_follower("pcb")
    # board_alignment = align_translation(
    #     nitehawk_pcb, holder, Alignment.STACK_TOP, stack_gap=0.0
    # )

    # nitehawk_board = board_alignment(nitehawk_board)

    # board_hole_1 = nitehawk_board.get_named_cutter("hole_1")

    # align_board_translattion = align_translation(
    #     board_hole_1, holder_screw_hole_cutter_1, Alignment.CENTER, axes=[0, 1]
    # )
    # nitehawk_board = align_board_translattion(nitehawk_board)

    # parts.add(nitehawk_board, "nitehawk_board", flip=False, skip_in_production=True)

    # board_hole_1 = nitehawk_board.get_named_cutter("hole_1")

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
