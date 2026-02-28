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
from mege_ender_3v3ke_idex.designs.nitehawk_holder import (
    create_nitehawk_holder,
    align_holder_to_extruder,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
BIG_THING = 500

part_fan_size = 40.2
part_fan_fillet_radius = 2
part_fan_thickness = 10.5
part_fan_screw_size = "M2.5"
part_fan_screw_hole_inset = 2.5
part_fan_screw_mount_cutout_size = 5.3
part_fan_screw_mount_cutout_fillet_radius = 2
part_fan_screw_mount_base_thickness = 3.5
part_fan_window_width = 28
part_fan_window_height = 8.1
part_fan_hole_diameter = 31
part_fan_diameter = 30
part_fan_axis_from_left_offset = 17.2


part_fan_angle = 55
part_fans_separator_angle = 10
part_fan_x_offset = 50

part_fan_bed_clearance = 9


def create_part_fan():

    body = create_filleted_box(
        part_fan_size,
        part_fan_size,
        part_fan_thickness,
        part_fan_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    screw_hole_diameter = MScrew.from_size(part_fan_screw_size).clearance_hole_normal

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole = create_cylinder(screw_hole_diameter / 2, part_fan_thickness + 2)
            hole = align(hole, body, Alignment.CENTER)
            hole = align(hole, body, lr)
            hole = align(hole, body, fb)
            hole = translate(
                lr.sign * (screw_hole_diameter / 2 - part_fan_screw_hole_inset),
                fb.sign * (screw_hole_diameter / 2 - part_fan_screw_hole_inset),
                0,
            )(hole)
            body = body.cut(hole)

            mount_cutout = create_cylinder(
                part_fan_screw_mount_cutout_size / 2, BIG_THING
            )

            mount_cutout = align(mount_cutout, hole, Alignment.CENTER)
            mount_cutout = align(mount_cutout, body, Alignment.BOTTOM)

            mount_cutout = translate(
                0 * lr.sign * part_fan_screw_hole_inset,
                0 * fb.sign * part_fan_screw_hole_inset,
                part_fan_screw_mount_base_thickness,
            )(mount_cutout)
            body = body.cut(mount_cutout)

            additional_cutter = create_box(
                part_fan_screw_mount_cutout_size,
                part_fan_screw_mount_cutout_size,
                BIG_THING,
            )

            additional_cutter = align(additional_cutter, mount_cutout, Alignment.CENTER)
            additional_cutter = align(additional_cutter, mount_cutout, Alignment.BOTTOM)
            additional_cutter = align(additional_cutter, mount_cutout, lr.opposite)
            additional_cutter = align(additional_cutter, mount_cutout, fb.opposite)

            cutter_1 = translate(lr.sign * part_fan_screw_mount_cutout_size / 2, 0, 0)(
                additional_cutter
            )
            cutter_2 = translate(0, fb.sign * part_fan_screw_mount_cutout_size / 2, 0)(
                additional_cutter
            )
            body = body.cut(cutter_1)
            body = body.cut(cutter_2)

    fan_hole = create_cylinder(part_fan_hole_diameter / 2, BIG_THING)
    fan_hole = align(fan_hole, body, Alignment.CENTER)
    fan_hole = align(fan_hole, body, Alignment.BOTTOM)
    fan_hole = align(fan_hole, body, Alignment.RIGHT)
    fan_hole = translate(
        -part_fan_axis_from_left_offset + part_fan_hole_diameter / 2,
        0,
        (part_fan_thickness - part_fan_window_height) / 2,
    )(fan_hole)
    body = body.cut(fan_hole)

    window_cutter = create_box(part_fan_window_width, BIG_THING, part_fan_window_height)
    window_cutter = align(window_cutter, body, Alignment.CENTER)
    window_cutter = align(
        window_cutter, body, Alignment.STACK_FRONT, stack_gap=-part_fan_size / 2
    )

    body = body.cut(window_cutter)

    return body


def create_tool_head() -> LeaderFollowersCuttersPart:

    sprite_extruder = create_sprite_extruder()

    holder = create_nitehawk_holder()
    holder = rotate(180, axis=(0, 1, 0))(holder)

    holder = align_holder_to_extruder(holder, sprite_extruder)

    retval = sprite_extruder

    retval = retval.merge_except_leader(holder)
    retval.add_named_non_production_part(holder.leader, "nitehawk_holder_leader")

    sprite_extruder_fused = sprite_extruder.leaders_followers_fused()
    retval.add_named_non_production_part(sprite_extruder_fused, "sprite_extruder")

    hotend = sprite_extruder.get_named_non_production_part("hotend")

    fans = PartCollector()
    for i in [-1, 1]:
        fan = create_part_fan()
        fan = align(fan, None, Alignment.CENTER)
        if i == 1:
            fan = rotate(180)(fan)

        fan = rotate(90, axis=(1, 0, 0))(fan)

        fan = rotate(i * part_fan_angle, axis=(1, 0, 0))(fan)
        fan = translate(part_fan_x_offset, 0, 0)(fan)
        fan = rotate(i * part_fans_separator_angle, axis=(0, 1, 0))(fan)
        fans = fans.fuse(fan)

    fans = rotate(-90, axis=(0, 1, 0))(fans)
    fans = align(fans, hotend, Alignment.CENTER)
    fans = align(fans, hotend, Alignment.FRONT)
    fans = align(fans, hotend, Alignment.TOP)

    fans = translate(0, part_fan_bed_clearance, 0)(fans)

    retval.add_named_non_production_part(fans, f"part_fan_{i}")

    retval = rotate(90, axis=(1, 0, 0))(retval)
    retval = rotate(180)(retval)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part

    toolhead = create_tool_head()

    parts.add(toolhead, "toolhead", flip=False, skip_in_production=True)

    for name, npp in toolhead.get_named_non_production_part_items():
        if name in ["nitehawk_pcb"]:
            continue
        parts.add(npp, name, flip=False, skip_in_production=True)

    fan = create_part_fan()
    fan = translate(100, 0, 0)(fan)
    parts.add(fan, "part_fan", flip=False, skip_in_production=True)

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
