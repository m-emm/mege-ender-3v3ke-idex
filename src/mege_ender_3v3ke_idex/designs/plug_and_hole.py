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

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_TPU)


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


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    plug, counter_plate = create_plug_and_hole()
    parts.add(plug, "plug", flip=False)
    parts.add(counter_plate, "counter_plate", flip=False)

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
