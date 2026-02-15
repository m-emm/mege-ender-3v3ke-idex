"""
Jury Rigged Z Carriage

Usage:
    cd <project_root> && ./run.sh path/to/jury_rigged_z_carriage.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/jury_rigged_z_carriage.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_precision import (  # noqa: F401
    PROCESS_DATA_PETG_04_HP,
    PROCESS_DATA_PLACF_04_HP,
)
from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.creality_wheel import (
    create_v_slot_wheel_608z_with_ball_bearing,
    v_slot_wheel_608z_outer_diameter,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETG_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        #   "wall_loops": "1",
        # "bottom_shell_layers": "1",
        # "top_shell_layers": "1",
        #        "sparse_infill_density": "25%",
        "brim_type": "no_brim",
        # "seam_position": "random",
    }
)


# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

BIG_THING = 500
wheel_distance = 36
wheel_front_y_offset = 6.5
wheels_vertical_gap = 8
wheels_plate_thickness = 8
wheels_plate_border = 8
wheels_plate_gap = 2
wheels_plate_preload_gap = 1.6
wheel_axle_diameter = 8
wheel_axle_length = 100
wheel_axle_clearance = 0.2
wheel_axle_screw_size = "M5"
wheel_axle_screw_length_with_head = 20
axle_screw_conical_head_height = m_screws_table[wheel_axle_screw_size][
    "conical_head_height"
]

wheel_axle_nut_screw_overlap = 3.5
axle_nut_cuter_slack = 0.2

axle_screw_offset_from_front = axle_screw_conical_head_height / 2

axle_base_diameter = 12


plate_connector_screw_size = "M3"

screw_connector_length = 25

cage_wall = 3
cage_height = 30

cage_front_gap = 2

cage_screw_size = "M3"

cage_screw_inset = 5
cage_screw_drill_depth = 5

cage_enhancer_width = 7
cage_enhancer_thickness = 7
hidden_nut_pocket_slack = 0.35


shortened_step_export_path = "/Users/mege/git/mege-ender-3v3ke-idex/resources/step_experiments/creality_z_axis_one_side_only_shortened.step"


def create_creality_z_axis():
    step_path = "/Users/mege/git/mege-ender-3v3ke-idex/resources/step_experiments/zaxis_only.step"

    _logger.info(f"Importing Z axis from STEP file: {step_path}")
    imported = import_solid_from_step(step_path)
    imported = rotate(90, axis=(1, 0, 0))(imported)  # Rotate to correct orientation
    _logger.info("Z axis imported successfully.")

    return imported


def create_creality_z_axis_one_side_only_shortened():
    step_path = "/Users/mege/git/mege-ender-3v3ke-idex/resources/step_experiments/zaxis_only.step"

    _logger.info(f"Importing Z axis from STEP file: {step_path}")
    imported = import_solid_from_step(step_path)

    _logger.info("Z axis imported successfully.")

    imported = rotate(90, axis=(1, 0, 0))(imported)  # Rotate to correct orientation
    retval, _ = cut_in_two(imported, cut_normal=(1, 0, 0))

    retval_bbox = get_bounding_box(retval)

    cut_point_z = retval_bbox[0][2] + 120
    _, retval = cut_in_two(retval, cut_normal=(0, 0, 1), cut_point=(0, 0, cut_point_z))

    export_solid_to_step(retval, shortened_step_export_path)
    _logger.info(
        f"Exported shortened Z axis to STEP for later re-use: {shortened_step_export_path}"
    )

    _logger.info("Z axis prepared successfully.")

    return retval


def create_creality_z_axis_one_side_only_shortened_from_step():

    _logger.info(
        f"Importing shortened Z axis from STEP file: {shortened_step_export_path}"
    )
    imported = import_solid_from_step(shortened_step_export_path)
    _logger.info("Shortened Z axis imported successfully.")

    return imported


def create_creality_profile_segment_only_from_step():

    step_path = "/Users/mege/git/mege-ender-3v3ke-idex/resources/step_experiments/creality_profile_segment_only.step"

    _logger.info(f"Importing Z axis profile from STEP file: {step_path}")
    imported = import_solid_from_step(step_path)

    imported = align(imported, None, Alignment.CENTER)

    imported_bbox = get_bounding_box(imported)

    imported = translate(0, 0, -imported_bbox[0][2])(imported)

    _logger.info("Z axis profile imported successfully.")

    return imported


def create_creality_profile_segment_only():

    z_axis = create_creality_z_axis()

    retval, _ = cut_in_two(z_axis, cut_normal=(1, 0, 0))

    retval, _ = cut_in_two(retval, cut_normal=(0, -1, 0))

    _logger.info("Exporting cut Z axis segment to STEP for verification.")
    export_solid_to_step(retval, "/tmp/creality_profile_segment_only.step")
    _logger.info(
        "Exported cut Z axis segment to /tmp/creality_profile_segment_only.step"
    )

    return retval


def create_screww_connector(screw_size, length):

    screw = MScrew.from_size(screw_size)
    screw_hole_diameter = screw.clearance_hole_normal

    connector_side = screw_hole_diameter * 2.5

    connector = create_box(length, connector_side, connector_side)

    nut_socked_cutter = create_hidden_nut_pocket_cutter(
        screw_size,
        bottom_cutter_length=connector_side / 2,
        slack=hidden_nut_pocket_slack,
    )
    nut_socked_cutter = rotate(90)(nut_socked_cutter)
    nut_socked_cutter = rotate(90, axis=(0, 1, 0))(nut_socked_cutter)
    nut_socked_cutter = align(nut_socked_cutter, connector, Alignment.CENTER)
    nut_socked_cutter = align(nut_socked_cutter, connector, Alignment.LEFT)

    nut_size = get_bounding_box_size(nut_socked_cutter)

    nut_socked_cutter = translate(nut_size[0], 0, 0)(nut_socked_cutter)

    connector = nut_socked_cutter.use_as_cutter_on(connector)

    return connector


def create_jury_rigged_z_carriage(z_axis_profile, threaded_rod):
    """Create the jury_rigged_z_carriage part."""

    wheels = LeaderFollowersCuttersPart(PartCollector())

    for lr in [Alignment.RIGHT, Alignment.LEFT]:
        wheel = create_v_slot_wheel_608z_with_ball_bearing()

        wheel = translate(lr.sign * wheel_distance / 2, 0, 0)(wheel)
        wheel = wheel.prefixed_copy(f"wheel_{lr.name.lower()}")

        if lr == Alignment.RIGHT:
            wheel_front = create_v_slot_wheel_608z_with_ball_bearing()
            wheel_front = translate(
                lr.sign * wheel_distance / 2, wheel_front_y_offset, 0
            )(wheel_front)
            wheel_front = wheel_front.prefixed_copy(f"wheel_{lr.name.lower()}_top")
            wheel_front = align(wheel_front, wheel, Alignment.CENTER)
            wheel_front = align(
                wheel_front, wheel, Alignment.STACK_FRONT, stack_gap=wheels_vertical_gap
            )
            wheels = wheels.fuse(wheel_front)

        else:
            wheel = translate(
                0, -wheel_front_y_offset / 2 - v_slot_wheel_608z_outer_diameter / 2, 0
            )(wheel)

        wheels = wheels.fuse(wheel)

    wheels = rotate(90, axis=(1, 0, 0))(wheels)
    wheels = align(wheels, z_axis_profile, Alignment.CENTER)
    wheels = align(wheels, z_axis_profile, Alignment.BOTTOM)
    wheels = align(wheels, z_axis_profile, Alignment.FRONT)

    wheels = translate(0, wheel_front_y_offset, 0)(wheels)

    wheels_size = get_bounding_box_size(wheels)

    wheels_plate = create_box(
        wheels_size[0] + 2 * wheels_plate_border,
        wheels_plate_thickness,
        wheels_size[2] + 2 * wheels_plate_border,
    )

    wheels_plate = align(wheels_plate, wheels, Alignment.CENTER)
    wheels_plate = align(
        wheels_plate, z_axis_profile, Alignment.STACK_BACK, stack_gap=wheels_plate_gap
    )
    wheels_plate_plain = wheels_plate

    wheels_plate_back_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    wheels_plate_back_cutter = align(
        wheels_plate_back_cutter, wheels_plate_plain, Alignment.CENTER
    )
    wheels_plate_back_cutter = align(
        wheels_plate_back_cutter, wheels_plate_plain, Alignment.STACK_BACK
    )

    wheel_axles = PartCollector()
    wheel_axle_screws_cutters = PartCollector()
    wheel_axle_screws = []
    for wheel_name in ["wheel_right", "wheel_left", "wheel_right_top"]:

        bearing_name = f"{wheel_name}_bearing"
        bearing = wheels.get_non_production_part_by_name(bearing_name)

        wheel_axle = create_cylinder(
            wheel_axle_diameter / 2 - wheel_axle_clearance, wheel_axle_length
        )
        wheel_axle = rotate(90, axis=(1, 0, 0))(wheel_axle)
        wheel_axle = align(wheel_axle, bearing, Alignment.CENTER)
        wheel_axle = align(wheel_axle, bearing, Alignment.FRONT)
        wheel_axle = translate(
            0, axle_screw_conical_head_height - axle_screw_offset_from_front, 0
        )(wheel_axle)

        wheel_axle_base = create_cylinder(axle_base_diameter / 2, BIG_THING)
        wheel_axle_base = rotate(90, axis=(1, 0, 0))(wheel_axle_base)
        wheel_axle_base = align(wheel_axle_base, bearing, Alignment.CENTER)
        wheel_axle_base = align(wheel_axle_base, bearing, Alignment.STACK_BACK)
        wheel_axle_base = wheel_axle_base.cut(wheels_plate_back_cutter)
        wheel_axle = wheel_axle.fuse(wheel_axle_base)

        wheel_axles = wheel_axles.fuse(wheel_axle)

        axle_screw_cutter = create_cylinder(
            MScrew.from_size(wheel_axle_screw_size).clearance_hole_close / 2, BIG_THING
        )
        axle_screw_cutter = rotate(90, axis=(1, 0, 0))(axle_screw_cutter)
        axle_screw_cutter = align(axle_screw_cutter, wheel_axle, Alignment.CENTER)
        wheel_axle_screws_cutters = wheel_axle_screws_cutters.fuse(axle_screw_cutter)

        wheel_axle_screw = create_conical_head_screw(
            wheel_axle_screw_size, wheel_axle_screw_length_with_head
        )
        wheel_axle_screw = rotate(90, axis=(1, 0, 0))(wheel_axle_screw)
        wheel_axle_screw = align(wheel_axle_screw, bearing, Alignment.CENTER)
        wheel_axle_screw = align(wheel_axle_screw, bearing, Alignment.FRONT)
        wheel_axle_screw = translate(0, -axle_screw_offset_from_front, 0)(
            wheel_axle_screw
        )

        wheel_axle_screws.append(wheel_axle_screw)

        wheel_axle_nut_cutter = create_nut(
            wheel_axle_screw_size,
            slack=axle_nut_cuter_slack,
            height=BIG_THING,
            no_hole=True,
        )
        wheel_axle_nut_cutter = rotate(90, axis=(1, 0, 0))(wheel_axle_nut_cutter)
        wheel_axle_nut_cutter = align(
            wheel_axle_nut_cutter, wheel_axle, Alignment.CENTER
        )
        wheel_axle_nut_cutter = align(
            wheel_axle_nut_cutter,
            wheel_axle_screw,
            Alignment.STACK_BACK,
            stack_gap=-wheel_axle_nut_screw_overlap,
        )
        wheel_axle_screws_cutters = wheel_axle_screws_cutters.fuse(
            wheel_axle_nut_cutter
        )

    axles_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    axles_cutter = align(axles_cutter, wheels_plate, Alignment.CENTER)
    axles_cutter = align(axles_cutter, wheels_plate, Alignment.STACK_BACK)
    wheel_axles = wheel_axles.cut(axles_cutter)

    wheels_plate = wheels_plate.fuse(wheel_axles)
    wheels_plate = wheels_plate.cut(wheel_axle_screws_cutters)

    retval = LeaderFollowersCuttersPart(wheels_plate)

    retval = retval.merge_except_leader(wheels)
    retval.add_named_non_production_part(wheels.leader, "wheels")
    for i in range(len(wheel_axle_screws)):
        retval.add_named_non_production_part(
            wheel_axle_screws[i], f"wheel_axle_screw_{i+1}"
        )

    screw_connectors = PartCollector()
    for tb in [Alignment.TOP, Alignment.BOTTOM]:
        connector = create_screww_connector(
            plate_connector_screw_size, screw_connector_length
        )
        if tb == Alignment.BOTTOM:
            connector = rotate(180, axis=(1, 0, 0))(connector)
        connector = align(connector, wheels_plate, Alignment.CENTER)
        connector = align(connector, wheels_plate, Alignment.BACK)
        connector = align(connector, wheels_plate, tb.stack_alignment)
        screw_connectors = screw_connectors.fuse(connector)

    retval = retval.fuse(screw_connectors)

    plate_size = get_bounding_box_size(wheels_plate)

    cage_front_wall = create_box(plate_size[0] + 2 * cage_wall, cage_wall, cage_height)
    cage_front_wall = align(cage_front_wall, wheels_plate, Alignment.CENTER)
    cage_front_wall = align(
        cage_front_wall, z_axis_profile, Alignment.STACK_FRONT, stack_gap=cage_front_gap
    )

    cage_side_walls = PartCollector()
    for lr in [Alignment.RIGHT, Alignment.LEFT]:
        cage_side_wall = create_box(cage_wall, BIG_THING, cage_height)
        cage_side_wall = align(cage_side_wall, cage_front_wall, Alignment.CENTER)
        cage_side_wall = align(cage_side_wall, cage_front_wall, lr)
        cage_side_wall = align(cage_side_wall, cage_front_wall, Alignment.STACK_BACK)

        cage_side_wall = cage_side_wall.cut(wheels_plate_back_cutter)

        side_wall_enhancers = PartCollector()
        for tb in [Alignment.TOP, Alignment.BOTTOM]:

            enhancer = create_box(
                cage_enhancer_width, BIG_THING, cage_enhancer_thickness
            )
            enhancer = align(enhancer, cage_side_wall, Alignment.CENTER)
            enhancer = align(enhancer, cage_side_wall, tb)
            enhancer = align(enhancer, cage_side_wall, lr.opposite.stack_alignment)
            enhancer = align(enhancer, cage_side_wall, Alignment.FRONT)
            enhancer = enhancer.cut(wheels_plate_back_cutter)

            nut_socked_cutter = create_hidden_nut_pocket_cutter(
                cage_screw_size, bottom_cutter_length=4, slack=hidden_nut_pocket_slack
            )
            nut_socked_cutter = rotate(-lr.sign * 90)(nut_socked_cutter)
            nut_socked_cutter = rotate(90, axis=(1, 0, 0))(nut_socked_cutter)

            nut_socked_cutter = align(nut_socked_cutter, enhancer, Alignment.CENTER)
            nut_socked_cutter = align(nut_socked_cutter, enhancer, Alignment.FRONT)
            nut_size = get_bounding_box_size(nut_socked_cutter)

            nut_socked_cutter = translate(0, 1.5 * nut_size[1], 0)(nut_socked_cutter)
            enhancer = nut_socked_cutter.use_as_cutter_on(enhancer)

            cage_front_wall = nut_socked_cutter.use_as_cutter_on(cage_front_wall)
            cage_side_wall = nut_socked_cutter.use_as_cutter_on(cage_side_wall)

            side_wall_enhancers = side_wall_enhancers.fuse(enhancer)

        cage_side_wall = cage_side_wall.fuse(side_wall_enhancers)

        cage_side_walls = cage_side_walls.fuse(cage_side_wall)

    cage = cage_front_wall

    retval = retval.fuse(cage_side_walls)

    left_plate, right_plate = cut_in_two(
        retval, cut_normal=(1, 0, 0), cut_thickness=wheels_plate_preload_gap
    )

    retval.add_named_follower(left_plate, "left_part")
    retval.add_named_follower(right_plate, "right_part")

    retval.add_named_follower(cage, "cage")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    z_axis_profile = create_creality_profile_segment_only_from_step()

    short_z_axis_one_side = create_creality_z_axis_one_side_only_shortened_from_step()


    short_z_axis_one_side = align(
        short_z_axis_one_side, z_axis_profile, Alignment.CENTER
    )
    short_z_axis_one_side = align(
        short_z_axis_one_side, z_axis_profile, Alignment.FRONT
    )
    short_z_axis_one_side = align(
        short_z_axis_one_side, z_axis_profile, Alignment.BOTTOM
    )
    parts.add(
        short_z_axis_one_side, "creality_z_axis", flip=False, skip_in_production=True
    )

    short_z_axis_bb = get_bounding_box(short_z_axis_one_side)

    threaded_rod, _ = cut_in_two(
        short_z_axis_one_side,
        cut_normal=(0, 1, 0),
        cut_point=(0, short_z_axis_bb[1][1] - 15, 0),
    )

    #threaded_rod = translate(0, 0, 150)(threaded_rod)
    #parts.add(threaded_rod, "threaded_rod", flip=False, skip_in_production=True)


    z_carriage = create_jury_rigged_z_carriage(z_axis_profile, threaded_rod)

    for name in ["left_part", "right_part"]:
        follower = z_carriage.get_follower_part_by_name(name)
        parts.add(
            follower,
            name,
            flip=False,
            prod_rotation_angle=-90,
            prod_rotation_axis=(1, 0, 0),
        )

    parts.add(
        z_carriage.get_named_follower("cage"),
        "cage",
        flip=False,
        prod_rotation_angle=90,
        prod_rotation_axis=(1, 0, 0),
    )

    for name, npp in z_carriage.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    sc = create_screww_connector("M3", 30)
    sc = translate(0, -50, 0)(sc)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=5,
        export_individual_parts=False,
    )

    _logger.info("jury_rigged_z_carriage created successfully!")


if __name__ == "__main__":
    main()
