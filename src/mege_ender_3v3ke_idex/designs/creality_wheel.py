"""
Creality Wheel

Usage:
    cd <project_root> && ./run.sh path/to/creality_wheel.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/creality_wheel.py
"""

import copy
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_precision import (  # noqa: F401
    PROCESS_DATA_PETG_04_HP,
    PROCESS_DATA_PLACF_04_HP,
)
from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETG_04_HP)

PROCESS_DATA["process_overrides"].update(
    {
        #   "wall_loops": "1",
        # "bottom_shell_layers": "1",
        # "top_shell_layers": "1",
        #        "sparse_infill_density": "25%",
        "brim_type": "no_brim",
        "seam_position": "random",
    }
)

BIG_THING = 500


bb_608z_outer_diameter = 22
bb_608z_height = 7
v_slot_wheel_608z_bearing_radial_clearance = 0.0

v_slot_wheel_608z_ease_in_size = 0.7
v_slot_wheel_608z_singularity_cutter_thickness = 0.15

v_slot_wheel_608z_top_bottom_holder_size = 0.65
v_slot_wheel_608z_top_bottom_holder_axial_clearance = 0.05

v_slot_wheel_608z_width = 10.2
v_slot_wheel_608z_inner_width = 5
v_slot_wheel_608z_outer_diameter = 27.5


def create_608z_bearing(diameter_increase=0, height_increase=0):
    inner_diameter = 8
    height = bb_608z_height + height_increase
    outer_ring_width = 2
    inner_ring_width = 1.8
    bearing_height = height - 0.2

    outer_diameter = bb_608z_outer_diameter + diameter_increase
    bb_608_z = create_ring(
        outer_diameter / 2, outer_diameter / 2 - outer_ring_width, height
    )
    bb_608_z = bb_608_z.fuse(
        create_ring(inner_diameter / 2 + outer_ring_width, inner_diameter / 2, height)
    )
    bearing = bb_608_z.fuse(
        create_ring(
            outer_diameter / 2 - outer_ring_width,
            inner_diameter / 2 + inner_ring_width,
            bearing_height,
        )
    )
    bearing = translate(0, 0, (height - bearing_height) / 2)(bearing)

    bb_608_z = bb_608_z.fuse(bearing)

    return bb_608_z


def create_creality_wheel():
    """Create the creality_wheel part."""

    bearing_radial_clearance = 0.05
    bearing_axial_clearance = 0.1

    width = 10.2
    inner_width = 5
    outer_diameter = 24

    outer_radius_reduction = (width - inner_width) / 2

    roller_base = create_cylinder(outer_diameter / 2, width)

    roller_cutter_base = create_cylinder(outer_diameter / 2 + 1, width + 2)

    roller_cutter_base = align(roller_cutter_base, roller_base, Alignment.CENTER)

    for i in [Alignment.TOP, Alignment.BOTTOM]:

        roller_cutter = create_cone(
            radius1=outer_diameter / 2,
            radius2=outer_diameter / 2 - outer_radius_reduction,
            height=outer_radius_reduction,
        )
        if i == Alignment.BOTTOM:
            roller_cutter = rotate(180, axis=(0, 1, 0))(roller_cutter)

        roller_cutter = align(roller_cutter, roller_base, Alignment.CENTER)
        roller_cutter = align(
            roller_cutter,
            roller_base,
            i.stack_alignment,
            stack_gap=-outer_radius_reduction,
        )

        roller_cutter_base = roller_cutter_base.cut(roller_cutter)

    central_wheel = create_cylinder(outer_diameter / 2, inner_width)
    central_wheel = align(central_wheel, roller_base, Alignment.CENTER)
    roller_cutter_base = roller_cutter_base.cut(central_wheel)

    roller_base = roller_base.cut(roller_cutter_base)

    # bb_cutter = create_cylinder(outer_diameter_608z / 2, BIG_THING)
    # bb_cutter = align(bb_cutter, roller_base, Alignment.CENTER)
    # roller_base = roller_base.cut(bb_cutter)

    # bearing_cutter = create_608z_bearing(
    #     diameter_increase=bearing_radial_clearance,
    #     height_increase=bearing_axial_clearance,
    # )

    # bearing_cutter = align(bearing_cutter, roller_base, Alignment.CENTER)
    # roller_base = roller_base.cut(bearing_cutter)

    return roller_base


def create_ring_spike(outer_radius, height):

    inner_radius = outer_radius - height / 2

    base_ring = create_ring(outer_radius, inner_radius, height)
    spike_cutter = create_cone(
        radius1=outer_radius,
        radius2=inner_radius,
        height=height / 2,
    )
    spike_cutter = align(spike_cutter, base_ring, Alignment.CENTER)
    spike_cutter = align(
        spike_cutter,
        base_ring,
        Alignment.BOTTOM,
    )
    spike_top_cutter = rotate(180, axis=(0, 1, 0))(spike_cutter)
    spike_top_cutter = align(spike_top_cutter, base_ring, Alignment.CENTER)
    spike_top_cutter = align(
        spike_top_cutter,
        base_ring,
        Alignment.TOP,
    )

    spike = base_ring.cut(spike_cutter).cut(spike_top_cutter)

    return spike


def create_v_slot_wheel_608z():

    outer_radius_reduction = (
        v_slot_wheel_608z_width - v_slot_wheel_608z_inner_width
    ) / 2

    roller_base = create_cylinder(
        v_slot_wheel_608z_outer_diameter / 2, v_slot_wheel_608z_width
    )

    roller_cutter_base = create_cylinder(
        v_slot_wheel_608z_outer_diameter / 2 + 1, v_slot_wheel_608z_width + 2
    )

    roller_cutter_base = align(roller_cutter_base, roller_base, Alignment.CENTER)

    for i in [Alignment.TOP, Alignment.BOTTOM]:

        roller_cutter = create_cone(
            radius1=v_slot_wheel_608z_outer_diameter / 2,
            radius2=v_slot_wheel_608z_outer_diameter / 2 - outer_radius_reduction,
            height=outer_radius_reduction,
        )
        if i == Alignment.BOTTOM:
            roller_cutter = rotate(180, axis=(0, 1, 0))(roller_cutter)

        roller_cutter = align(roller_cutter, roller_base, Alignment.CENTER)
        roller_cutter = align(
            roller_cutter,
            roller_base,
            i.stack_alignment,
            stack_gap=-outer_radius_reduction,
        )

        roller_cutter_base = roller_cutter_base.cut(roller_cutter)

    central_wheel = create_cylinder(
        v_slot_wheel_608z_outer_diameter / 2, v_slot_wheel_608z_inner_width
    )
    central_wheel = align(central_wheel, roller_base, Alignment.CENTER)
    roller_cutter_base = roller_cutter_base.cut(central_wheel)

    roller_base = roller_base.cut(roller_cutter_base)

    inner_cutter_radius = (
        bb_608z_outer_diameter / 2 + v_slot_wheel_608z_bearing_radial_clearance
    )
    bb_sized_through_cutter = create_cylinder(inner_cutter_radius, BIG_THING)
    bb_sized_through_cutter = align(
        bb_sized_through_cutter, roller_base, Alignment.CENTER
    )
    roller_base = roller_base.cut(bb_sized_through_cutter)

    ease_in_cutters = PartCollector()
    top_bottom_holders = PartCollector()
    for tb in [Alignment.TOP, Alignment.BOTTOM]:
        ease_in_cutter = create_cone(
            inner_cutter_radius + v_slot_wheel_608z_ease_in_size,
            inner_cutter_radius,
            v_slot_wheel_608z_ease_in_size,
        )
        if tb == Alignment.TOP:
            ease_in_cutter = rotate(180, axis=(0, 1, 0))(ease_in_cutter)

        ease_in_cutter = align(ease_in_cutter, roller_base, Alignment.CENTER)
        ease_in_cutter = align(
            ease_in_cutter,
            roller_base,
            tb.stack_alignment,
            stack_gap=-v_slot_wheel_608z_ease_in_size,
        )
        ease_in_cutters = ease_in_cutters.fuse(ease_in_cutter)

        top_bottom_holder = create_ring_spike(
            inner_cutter_radius, v_slot_wheel_608z_top_bottom_holder_size
        )
        top_bottom_holder = align(top_bottom_holder, None, Alignment.CENTER, axes=[2])

        top_bottom_holder = translate(
            0,
            0,
            tb.sign
            * (
                bb_608z_height / 2
                + v_slot_wheel_608z_top_bottom_holder_axial_clearance
                + v_slot_wheel_608z_top_bottom_holder_size / 2
            ),
        )(top_bottom_holder)

        top_bottom_holders = top_bottom_holders.fuse(top_bottom_holder)

    top_bottom_holders = align(top_bottom_holders, roller_base, Alignment.CENTER)

    roller_base = roller_base.cut(ease_in_cutters)

    singularity_cutters = PartCollector()
    for i in [Alignment.TOP, Alignment.BOTTOM]:
        singularity_cutter = create_cylinder(BIG_THING, BIG_THING)
        singularity_cutter = align(singularity_cutter, roller_base, Alignment.CENTER)
        singularity_cutter = align(
            singularity_cutter,
            roller_base,
            i.stack_alignment,
            stack_gap=-v_slot_wheel_608z_singularity_cutter_thickness,
        )
        singularity_cutters = singularity_cutters.fuse(singularity_cutter)

    roller_base = roller_base.cut(singularity_cutters)
    roller_base = roller_base.fuse(top_bottom_holders)

    spacer_brim_thickness = 1.2
    spacer_brim_clearance = 0.8
    spacer_brim_width = 1.5
    spacer_brim_connector_width = 0.5
    spacer_brim_connector_thickness = 0.2
    num_spacer_brim_connectors = 8

    spacer_brim_radius = (
        inner_cutter_radius + v_slot_wheel_608z_ease_in_size - spacer_brim_clearance
    )
    spacer_brim = create_cone(
        radius1=spacer_brim_radius,
        radius2=spacer_brim_radius - spacer_brim_thickness,
        height=spacer_brim_thickness,
    )

    spacer_brim_cutter = create_cylinder(
        spacer_brim_radius - spacer_brim_width, BIG_THING
    )
    spacer_brim_cutter = align(spacer_brim_cutter, roller_base, Alignment.CENTER)
    spacer_brim = spacer_brim.cut(spacer_brim_cutter)

    spacer_brim = align(spacer_brim, roller_base, Alignment.CENTER)
    spacer_brim = align(spacer_brim, roller_base, Alignment.BOTTOM)

    roller_base = roller_base.fuse(spacer_brim)
    connectors = PartCollector()
    for i in range(num_spacer_brim_connectors):
        angle = i * (360 / num_spacer_brim_connectors)
        connector = create_box(
            spacer_brim_clearance,
            spacer_brim_connector_width,
            spacer_brim_connector_thickness,
        )

        connector = translate(spacer_brim_radius - spacer_brim_clearance / 2, 0, 0)(
            connector
        )
        connector = rotate(angle)(connector)

        connectors = connectors.fuse(connector)

    connectors = align(connectors, spacer_brim, Alignment.CENTER)
    connectors = align(connectors, spacer_brim, Alignment.BOTTOM)

    roller_base = roller_base.fuse(connectors)

    return roller_base


def create_v_slot_wheel_608z_with_ball_bearing():

    wheel = create_v_slot_wheel_608z()

    bb = create_608z_bearing()

    bb = align(bb, wheel, Alignment.CENTER)

    retval = LeaderFollowersCuttersPart(wheel)
    retval.add_named_non_production_part(bb, "bearing")

    return retval


def create_bb_608z_holder(
    thickness,
    outer_diameter,
    preload_distance=0.1,
    holder_fin_length=1.2,
    holder_fin_thickness=1.0,
    num_holder_fins=12,
):

    fin_radius_delta = holder_fin_length / math.sqrt(2) - preload_distance
    inner_radius = bb_608z_outer_diameter / 2 - preload_distance + fin_radius_delta
    outer_ring = create_ring(outer_diameter / 2, inner_radius, thickness)

    fins = PartCollector()
    for i in range(num_holder_fins):
        angle = i * (360 / num_holder_fins)

        fin = create_pyramid_stump(
            thickness,
            thickness - 2 * fin_radius_delta,
            holder_fin_thickness,
            holder_fin_thickness,
            holder_fin_length,
        )

        fin = rotate(-90, axis=(0, 1, 0))(fin)
        fin = align(fin, outer_ring, Alignment.CENTER, axes=[2])
        fin_bbox = get_bounding_box(fin)
        fin = translate(-fin_bbox[0][0], 0, 0)(fin)
        fin = rotate(45)(fin)

        fin = translate(bb_608z_outer_diameter / 2 - preload_distance, 0, 0)(fin)

        fin = rotate(angle)(fin)

        fins = fins.fuse(fin)

    holder = outer_ring.fuse(fins)

    return holder


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    v_slot_wheel_608z = create_v_slot_wheel_608z()

    bb_2 = create_608z_bearing()

    bb_2 = align(bb_2, v_slot_wheel_608z, Alignment.CENTER)

    if not PROD:
        cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
        cutter = align(cutter, v_slot_wheel_608z, Alignment.CENTER)
        cutter, _ = cut_in_two(cutter, cut_normal=(1, 0, 0))

        v_slot_wheel_608z = v_slot_wheel_608z.cut(cutter)

    parts.add(bb_2, "608z_bearing_2", flip=False, skip_in_production=True)
    parts.add(
        v_slot_wheel_608z, "v_slot_wheel_608z", flip=False, skip_in_production=False
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("creality_wheel created successfully!")


if __name__ == "__main__":
    main()
