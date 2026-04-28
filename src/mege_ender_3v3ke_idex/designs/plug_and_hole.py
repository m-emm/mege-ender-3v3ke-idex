"""
Plug And Hole

Usage:
    cd <project_root> && ./run.sh path/to/plug_and_hole.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/plug_and_hole.py
"""

import copy
import logging
import math
import os

import numpy as np
from mege_3devops.process_data.parametric import resolve_process_data_from_parameters
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

BIG_THING = 500
# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA_PETGCF = resolve_process_data_from_parameters(
    printer_id="megemaster",
    nozzle_hardened=True,
    nozzle_high_flow=True,
    nozzle_diameter_mm=0.6,
    material_name="petg_cf_generic",
    strength_factor=0.2,
    quality_factor=0.2,
)
PROCESS_DATA_TPU = resolve_process_data_from_parameters(
    printer_id="megemaster",
    nozzle_hardened=True,
    nozzle_high_flow=True,
    nozzle_diameter_mm=0.6,
    material_name="esun_tpu_95a",
    strength_factor=0.0,
    quality_factor=0.8,
)


WHAT_TO_PRINT = "plugs"  # "plugs" or "counter_plate"

if WHAT_TO_PRINT == "plugs":
    PROCESS_DATA = copy.deepcopy(PROCESS_DATA_TPU)
    PROCESS_DATA["process_overrides"]["brim_type"] = "no_brim"
else:
    PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF)
    PROCESS_DATA["process_overrides"]["brim_type"] = "no_brim"


def create_plug(
    plug_diameter,
    plug_angle_deg,
    plug_height,
    plug_wall_thickness,
    plug_base_thickness,
    plug_slit_width=None,
    fillet_radius=0.5,
    plug_lip_height=None,
    plug_lip_size=None,
    plug_lip_top_gap=None,
    no_inner_hole=False,
):

    plug_base = create_cylinder(plug_diameter / 2, plug_base_thickness)

    radius_1 = plug_diameter / 2
    radius_2 = radius_1 - plug_height * math.tan(math.radians(plug_angle_deg))
    cone = create_cone(
        radius1=radius_1,
        radius2=radius_2,
        height=plug_height,
    )
    cone = align(cone, plug_base, Alignment.CENTER)
    cone = align(cone, plug_base, Alignment.STACK_TOP)

    if (
        plug_lip_height is not None
        and plug_lip_size is not None
        and plug_lip_top_gap is not None
    ):

        lip_relative_height = (plug_height - plug_lip_top_gap) / plug_height

        lip_inner_radius_raw = radius_1 + (radius_2 - radius_1) * lip_relative_height
        lip_outer_radius = lip_inner_radius_raw + plug_lip_size
        lip = create_cylinder(
            lip_outer_radius,
            height=plug_lip_height,
        )

        lip = apply_fillet_by_alignment(
            lip,
            fillet_radius / 2,
            fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )
        lip = align(lip, cone, Alignment.CENTER)
        lip = align(lip, cone, Alignment.TOP)
        lip = translate(0, 0, -plug_lip_top_gap)(lip)

        cone = cone.fuse(lip)

    if not no_inner_hole:
        inner_cone = create_cone(
            radius1=radius_1 - plug_wall_thickness,
            radius2=radius_2 - plug_wall_thickness,
            height=plug_height + 1e-3,
        )
        inner_cone = align(inner_cone, plug_base, Alignment.CENTER)
        inner_cone = align(inner_cone, plug_base, Alignment.STACK_TOP)

        cone = cone.cut(inner_cone)
    plug = plug_base.fuse(cone)

    if plug_slit_width is not None and plug_slit_width > 0.0:
        slit_cutter = create_box(
            2 * plug_diameter,
            plug_slit_width,
            plug_height + 2.0,
        )
        slit_cutter = align(slit_cutter, plug, Alignment.CENTER)
        slit_cutter = align(slit_cutter, plug_base, Alignment.STACK_TOP)

        plug = plug.cut(slit_cutter)

    def edge_filter(bbox, v0_point, v1_point):
        v0_point = np.array(v0_point)
        if not np.allclose(v0_point[2], plug_base_thickness + plug_height):
            return False
        if not np.allclose(v1_point[2], plug_base_thickness + plug_height):
            return False
        return True

    fillet_edges = filter_edges_by_function(plug, edge_filter)
    plug = apply_fillet_to_edges(plug, fillet_radius, fillet_edges)

    return plug


def create_plug_and_hole():

    plug_diameter = 7
    plug_angle_deg = 5

    plug_lip_height = 0.8
    plug_lip_size = 0.5
    plug_lip_top_gap = 1.0
    plug_wall_thickness = 1.2
    plug_base_thickness = 0.8
    plug_height = 6

    plug_slack = 0.1

    base_thickness = 2
    counter_plate_thickness = 2.5

    base = create_box(2 * plug_diameter, 2 * plug_diameter, base_thickness)

    plug = create_plug(
        plug_diameter=plug_diameter,
        plug_angle_deg=plug_angle_deg,
        plug_height=plug_height,
        plug_wall_thickness=plug_wall_thickness,
        plug_base_thickness=plug_base_thickness,
        plug_slit_width=0.5,
        fillet_radius=0.5,
        plug_lip_height=plug_lip_height,
        plug_lip_size=plug_lip_size,
        plug_lip_top_gap=plug_lip_top_gap,
    )
    plug = align(plug, base, Alignment.CENTER)
    plug = align(plug, base, Alignment.STACK_TOP)

    retval = plug.fuse(base)

    counter_plate = create_box(
        2 * plug_diameter, 2 * plug_diameter, counter_plate_thickness
    )
    counter_plate = align(counter_plate, base, Alignment.CENTER)
    counter_plate = align(counter_plate, base, Alignment.STACK_TOP, stack_gap=0.5)

    hole_cutter = create_cylinder(plug_diameter / 2 + plug_slack, BIG_THING)

    hole_cutter = align(hole_cutter, plug, Alignment.CENTER)

    counter_plate = counter_plate.cut(hole_cutter)

    return retval, counter_plate


def create_plugged_plate(
    num_x_plugs=2,
    num_y_plugs=2,
    border=5,
    plate_width=50,
    plate_depth=40,
    plug_plate_thickness=1,
    counter_plate_thickness=2.5,
    plug_diameter=7,
    plug_slack=0.1,
    plug_angle_deg=5,
    plug_height=6,
    plug_wall_thickness=1.2,
    plug_base_thickness=0.8,
    plug_slit_width=0.5,
    fillet_radius=0.5,
    plug_lip_height=0.8,
    plug_lip_size=0.5,
    plug_lip_top_gap=1.0,
):

    base = create_box(plate_width, plate_depth, plug_plate_thickness)

    plug_x_pitch = (
        (plate_width - 2 * border - plug_diameter) / (num_x_plugs - 1)
        if num_x_plugs > 1
        else 0
    )
    plug_y_pitch = (
        (plate_depth - 2 * border - plug_diameter) / (num_y_plugs - 1)
        if num_y_plugs > 1
        else 0
    )

    counter_plate = create_box(plate_width, plate_depth, counter_plate_thickness)
    counter_plate = align(counter_plate, base, Alignment.CENTER)
    counter_plate = align(counter_plate, base, Alignment.STACK_TOP)

    plugs = PartCollector()
    hole_cutters = PartCollector()
    for i in range(num_x_plugs):
        for j in range(num_y_plugs):
            plug = create_plug(
                plug_diameter=plug_diameter,
                plug_angle_deg=plug_angle_deg,
                plug_height=plug_height,
                plug_wall_thickness=plug_wall_thickness,
                plug_base_thickness=plug_base_thickness,
                plug_slit_width=0.5,
                fillet_radius=0.5,
                plug_lip_height=plug_lip_height,
                plug_lip_size=plug_lip_size,
                plug_lip_top_gap=plug_lip_top_gap,
            )
            x_pos = -plate_width / 2 + border + i * plug_x_pitch
            y_pos = -plate_depth / 2 + border + j * plug_y_pitch
            plug = translate(x_pos, y_pos, 0)(plug)
            plugs = plugs.fuse(plug)

            hole_cutter = create_cylinder(plug_diameter / 2 + plug_slack, BIG_THING)
            hole_cutter = align(hole_cutter, plug, Alignment.CENTER)
            hole_cutters = hole_cutters.fuse(hole_cutter)

    plugs_and_holes = LeaderFollowersCuttersPart(plugs)
    plugs_and_holes.add_named_cutter(hole_cutters, "hole_cutters")
    plugs_and_holes = align(plugs_and_holes, base, Alignment.CENTER)
    plugs_and_holes = align(plugs_and_holes, base, Alignment.STACK_TOP)

    plugs_and_holes = plugs_and_holes.fuse(base)

    counter_plate = plugs_and_holes.use_as_cutter_on(counter_plate)

    plugs_and_holes.add_named_follower(counter_plate, "counter_plate")

    return plugs_and_holes


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    plug, counter_plate = create_plug_and_hole()
    parts.add(plug, "plug", flip=False, skip_in_production=True)
    parts.add(counter_plate, "counter_plate", flip=False, skip_in_production=True)

    plugs_plate = create_plugged_plate(
        num_x_plugs=2,
        num_y_plugs=2,
        border=5,
        plate_width=35,
        plate_depth=30,
        plug_plate_thickness=1,
        counter_plate_thickness=2.5,
        plug_diameter=7,
        plug_slack=0.1,
        plug_angle_deg=5,
        plug_height=4,
        plug_wall_thickness=1.2,
        plug_base_thickness=0.8,
        plug_slit_width=0.5,
        fillet_radius=0.5,
        plug_lip_height=0.8,
        plug_lip_size=0.5,
        plug_lip_top_gap=1.0,
    )
    plugs_plate = align(plugs_plate, plug, Alignment.STACK_RIGHT, stack_gap=10)
    parts.add(
        plugs_plate,
        "plugs_plate",
        flip=False,
        skip_in_production=WHAT_TO_PRINT != "plugs",
    )

    parts.add(
        plugs_plate.get_named_follower("counter_plate"),
        "plugs_plate_counter",
        flip=False,
        skip_in_production=WHAT_TO_PRINT != "counter_plate",
    )
    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("plug_and_hole created successfully!")


if __name__ == "__main__":
    main()
