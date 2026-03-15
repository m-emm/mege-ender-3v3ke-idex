"""
Screw Mount Assembly

Usage:
    cd <project_root> && ./run.sh path/to/screw_mount_assembly.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/screw_mount_assembly.py
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


def create_single_screw_mount_for_top(
    part_thickness,
    screw_size,
    screw_length,
    with_nut_cutter=True,
    nut_cutter_clearance=0.15,
    flush_with_top=False,
    cylinder_head_cutter_clearance=0.1,
    clearance_type="normal",
    top_sink=0,
):

    screw = create_cylinder_screw(screw_size, screw_length)
    screw = translate(0, 0, -screw_length)(screw)

    m_screw_record = MScrew.from_size(screw_size)
    cylinder_head_height = m_screw_record.cylinder_head_height

    if flush_with_top:
        screw = translate(0, 0, -cylinder_head_height - top_sink)(screw)

    size_float = float(screw_size[1:])

    screw_body = create_cylinder(size_float / 2, screw_length)

    screw_body = align(screw_body, screw, Alignment.CENTER)
    screw_body = align(screw_body, screw, Alignment.BOTTOM)

    clearance_hole_diameter = m_screw_record.get_clearance_hole_diameter(
        clearance_type=clearance_type
    )

    hole_cutter = create_cylinder(clearance_hole_diameter / 2, part_thickness)

    hole_cutter = align(hole_cutter, screw_body, Alignment.CENTER)
    hole_cutter = align(hole_cutter, screw_body, Alignment.TOP)

    retval = LeaderFollowersCuttersPart(screw_body)
    retval.add_named_cutter(hole_cutter, "hole_cutter")

    if with_nut_cutter:
        nut_cutter = create_nut(
            screw_size,
            height=BIG_THING,
            slack=nut_cutter_clearance,
        )

        nut_cutter = align(nut_cutter, screw_body, Alignment.CENTER)
        nut_cutter = align(
            nut_cutter,
            screw_body,
            Alignment.STACK_BOTTOM,
            stack_gap=-m_screw_record.nut_thickness * 1.5 - nut_cutter_clearance,
        )

        retval.add_named_cutter(nut_cutter, "nut_cutter")

        nut = create_nut(screw_size)
        nut = align(nut, screw_body, Alignment.CENTER)
        nut = align(
            nut,
            screw_body,
            Alignment.BOTTOM,
        )
        nut = translate(0, 0, m_screw_record.nut_thickness / 2)(nut)
        retval.add_named_non_production_part(nut, "nut")

    if flush_with_top:

        cylinder_head_cutter = create_cylinder(
            m_screw_record.cylinder_head_diameter / 2 + cylinder_head_cutter_clearance,
            cylinder_head_height + cylinder_head_cutter_clearance + top_sink,
        )
        cylinder_head_cutter = align(cylinder_head_cutter, screw, Alignment.CENTER)
        cylinder_head_cutter = align(cylinder_head_cutter, screw, Alignment.TOP)
        cylinder_head_cutter = translate(0, 0, top_sink)(cylinder_head_cutter)
        retval.add_named_cutter(cylinder_head_cutter, "cylinder_head_cutter")

    retval.add_named_non_production_part(screw, "screw")

    return retval


def create_screw_mount_assembly(
    for_part,
    screw_size,
    screw_length,
    screw_direction=Alignment.TOP,
    with_nut_cutter=True,
    nut_cutter_clearance=0.15,
    flush_with_top=False,
    cylinder_head_cutter_clearance=0.1,
    clearance_type="normal",
    top_sink=0,
):

    part_bb_size = get_bounding_box_size(for_part)

    if screw_direction in [Alignment.TOP, Alignment.BOTTOM]:
        relevant_thickness = part_bb_size[2]
    elif screw_direction in [Alignment.FRONT, Alignment.BACK]:
        relevant_thickness = part_bb_size[1]
    elif screw_direction in [Alignment.LEFT, Alignment.RIGHT]:
        relevant_thickness = part_bb_size[0]
    else:
        raise ValueError("Invalid screw_direction")

    screw_mount_assembly = create_single_screw_mount_for_top(
        relevant_thickness,
        screw_size=screw_size,
        screw_length=screw_length,
        with_nut_cutter=with_nut_cutter,
        nut_cutter_clearance=nut_cutter_clearance,
        flush_with_top=flush_with_top,
        cylinder_head_cutter_clearance=cylinder_head_cutter_clearance,
        clearance_type=clearance_type,
        top_sink=top_sink,
    )

    if screw_direction == Alignment.FRONT:
        screw_mount_assembly = rotate(90, axis=(1, 0, 0))(screw_mount_assembly)

    elif screw_direction == Alignment.BACK:
        screw_mount_assembly = rotate(-90, axis=(1, 0, 0))(screw_mount_assembly)

    elif screw_direction == Alignment.LEFT:
        screw_mount_assembly = rotate(-90, axis=(0, 1, 0))(screw_mount_assembly)
    elif screw_direction == Alignment.RIGHT:
        screw_mount_assembly = rotate(90, axis=(0, 1, 0))(screw_mount_assembly)
    elif screw_direction == Alignment.BOTTOM:
        screw_mount_assembly = rotate(180, axis=(1, 0, 0))(screw_mount_assembly)
    elif screw_direction == Alignment.TOP:
        pass  # no rotation needed

    part_bbox = get_bounding_box(for_part)
    part_bbox_center = get_bounding_box_center(for_part)

    if screw_direction == Alignment.TOP:

        translation_vector = [part_bbox_center[0], part_bbox_center[1], part_bbox[1][2]]
    elif screw_direction == Alignment.BOTTOM:
        translation_vector = [part_bbox_center[0], part_bbox_center[1], part_bbox[0][2]]
    elif screw_direction == Alignment.FRONT:
        translation_vector = [part_bbox_center[0], part_bbox[0][1], part_bbox_center[2]]
    elif screw_direction == Alignment.BACK:
        translation_vector = [part_bbox_center[0], part_bbox[1][1], part_bbox_center[2]]
    elif screw_direction == Alignment.LEFT:
        translation_vector = [part_bbox[0][0], part_bbox_center[1], part_bbox_center[2]]
    elif screw_direction == Alignment.RIGHT:
        translation_vector = [part_bbox[1][0], part_bbox_center[1], part_bbox_center[2]]

    screw_mount_assembly = translate(*translation_vector)(screw_mount_assembly)

    return screw_mount_assembly


def create_four_screws_mount_assembly(
    for_part,
    screw_size,
    screw_length,
    screw_direction=Alignment.TOP,
    with_nut_cutter=True,
    nut_cutter_clearance=0.15,
    flush_with_top=False,
    cylinder_head_cutter_clearance=0.1,
    width_inset=5,
    length_inset=5,
    clearance_type="normal",
):

    part_bb_size = get_bounding_box_size(for_part)

    if screw_direction in [Alignment.TOP, Alignment.BOTTOM]:
        width_size = part_bb_size[0]
        length_size = part_bb_size[1]
        width_axis = 0
        length_axis = 1
    elif screw_direction in [Alignment.FRONT, Alignment.BACK]:
        width_size = part_bb_size[0]
        length_size = part_bb_size[2]
        width_axis = 0
        length_axis = 2
    elif screw_direction in [Alignment.LEFT, Alignment.RIGHT]:
        width_size = part_bb_size[1]
        length_size = part_bb_size[2]
        width_axis = 1
        length_axis = 2

    assemblies = []

    for i in [-1, 1]:
        for j in [-1, 1]:

            assembly = create_screw_mount_assembly(
                for_part,
                screw_size,
                screw_length,
                screw_direction,
                with_nut_cutter,
                nut_cutter_clearance,
                flush_with_top,
                cylinder_head_cutter_clearance,
                clearance_type=clearance_type,
            )

            translation_vector = [0, 0, 0]

            translation_vector[width_axis] = i * (width_size / 2 - width_inset)
            translation_vector[length_axis] = j * (length_size / 2 - length_inset)
            assembly = translate(*translation_vector)(assembly)

            assemblies.append(assembly)

    retval = None
    for k, assembly in enumerate(assemblies):
        current_asssembly = assembly.prefixed_copy(f"screw_{k}")
        if retval is None:
            retval = current_asssembly
        else:
            retval = retval.fuse(current_asssembly)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    test_thickness = 30
    base_plate = create_box(50, 50, test_thickness)
    base_plate = translate(0, 0, -test_thickness)(base_plate)

    single_screw_mount = create_single_screw_mount_for_top(
        test_thickness,
        "M3",
        25,
    )

    single_screw_mount = align(
        single_screw_mount, base_plate, Alignment.CENTER, axes=[0, 1]
    )  # leave z alignment alone, to test if the z is correctly aligned

    for name, npp in single_screw_mount.get_named_non_production_part_items():
        parts.add(npp, name, skip_in_production=True)

    base_plate = single_screw_mount.use_as_cutter_on(base_plate)

    single_screw_mount_2 = create_single_screw_mount_for_top(
        test_thickness,
        "M3",
        25,
        flush_with_top=True,
    )

    single_screw_mount_2 = align(
        single_screw_mount_2, base_plate, Alignment.CENTER, axes=[0, 1]
    )

    single_screw_mount_2 = translate(10, 0, 0)(single_screw_mount_2)

    for name, npp in single_screw_mount_2.get_named_non_production_part_items():
        parts.add(npp, name + "_2", skip_in_production=True)
    base_plate = single_screw_mount_2.use_as_cutter_on(base_plate)

    base_plate, _ = cut_in_two(base_plate, cut_normal=(0, 1, 0))

    parts.add(
        base_plate,
        "base_plate",
    )

    second_experiment = create_box(50, 50, test_thickness)

    second_experiment = translate(100, 0, -test_thickness)(second_experiment)

    screw_mount_assembly_test = create_screw_mount_assembly(
        second_experiment,
        screw_size="M3",
        screw_length=25,
        screw_direction=Alignment.FRONT,
        with_nut_cutter=True,
        flush_with_top=True,
    )

    for name, npp in screw_mount_assembly_test.get_named_non_production_part_items():
        parts.add(npp, name + "_front", skip_in_production=True)

    second_experiment = screw_mount_assembly_test.use_as_cutter_on(second_experiment)

    screw_mount_assembly_test_2 = create_screw_mount_assembly(
        second_experiment,
        screw_size="M3",
        screw_length=25,
        screw_direction=Alignment.BACK,
        with_nut_cutter=True,
        flush_with_top=True,
    )

    screw_mount_assembly_test_2 = translate(0, 0, 10)(screw_mount_assembly_test_2)

    for name, npp in screw_mount_assembly_test_2.get_named_non_production_part_items():
        parts.add(npp, name + "_back", skip_in_production=True)

    second_experiment = screw_mount_assembly_test_2.use_as_cutter_on(second_experiment)

    screw_mount_assembly_test_3 = create_screw_mount_assembly(
        second_experiment,
        screw_size="M3",
        screw_length=25,
        screw_direction=Alignment.RIGHT,
        with_nut_cutter=True,
        flush_with_top=True,
    )

    for name, npp in screw_mount_assembly_test_3.get_named_non_production_part_items():
        parts.add(npp, name + "_left", skip_in_production=True)

    screw_mount_assembly_test_4 = create_screw_mount_assembly(
        second_experiment,
        screw_size="M3",
        screw_length=25,
        screw_direction=Alignment.BOTTOM,
        with_nut_cutter=True,
        flush_with_top=True,
    )

    for name, npp in screw_mount_assembly_test_4.get_named_non_production_part_items():
        parts.add(npp, name + "_bottom", skip_in_production=True)

    second_experiment = screw_mount_assembly_test_4.use_as_cutter_on(second_experiment)

    second_experiment = screw_mount_assembly_test_3.use_as_cutter_on(second_experiment)

    second_experiment, _ = cut_in_two(second_experiment, cut_normal=(1, 0, 0))

    parts.add(
        second_experiment,
        "second_experiment",
    )

    third_experiment = create_box(50, 50, test_thickness)
    third_experiment = translate(200, 0, -test_thickness)(third_experiment)

    four_screws_mount_assembly = create_four_screws_mount_assembly(
        third_experiment,
        screw_size="M3",
        screw_length=25,
        screw_direction=Alignment.TOP,
        with_nut_cutter=True,
        flush_with_top=False,
    )

    for name, npp in four_screws_mount_assembly.get_named_non_production_part_items():
        parts.add(npp, name + "_four_screws", skip_in_production=True)

    third_experiment = four_screws_mount_assembly.use_as_cutter_on(third_experiment)

    parts.add(
        third_experiment,
        "third_experiment",
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("screw_mount_assembly created successfully!")


if __name__ == "__main__":
    main()
