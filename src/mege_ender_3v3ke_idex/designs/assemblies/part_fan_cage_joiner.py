"""Join part fan and extruder cage assemblies with a shared flange.

Run the isolated flange demo with::

    ./run.sh src/mege_ender_3v3ke_idex/designs/assemblies/part_fan_cage_joiner.py
"""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _create_join_flange_halves(
    *,
    anchor_part=None,
    side_mount_plate=None,
    extension_alignment=Alignment.LEFT,
    flange_extension,
    flange_half_height,
    screw_size,
    clearance_type,
):
    if anchor_part is None:
        anchor_part = side_mount_plate

    clearance_hole_diameter = get_clearance_hole_diameter(screw_size, clearance_type)

    flange_size = list(get_bounding_box_size(anchor_part)[:2])
    tab_size = flange_size.copy()
    flange_size[extension_alignment.axis] += flange_extension
    tab_size[extension_alignment.axis] = flange_extension
    attachment_alignment = extension_alignment.opposite
    flange_width, flange_depth = flange_size
    tab_width, tab_depth = tab_size

    bottom_flange = create_box(
        flange_width,
        flange_depth,
        clearance_hole_diameter * 1.8,
    )
    bottom_flange = align(
        bottom_flange,
        anchor_part,
        Alignment.CENTER,
    )
    bottom_flange = align(bottom_flange, anchor_part, attachment_alignment)
    bottom_flange = align(bottom_flange, anchor_part, Alignment.TOP)

    top_flange = create_box(
        flange_width,
        flange_depth,
        flange_half_height,
    )
    top_flange = align(top_flange, bottom_flange, Alignment.CENTER)
    top_flange = align(top_flange, bottom_flange, Alignment.STACK_TOP)

    tab_reference = create_box(tab_width, tab_depth, flange_half_height)
    tab_reference = align(
        tab_reference,
        anchor_part,
        Alignment.CENTER,
    )
    tab_reference = align(
        tab_reference,
        anchor_part,
        extension_alignment.stack_alignment,
    )
    tab_reference = align(tab_reference, anchor_part, Alignment.TOP)

    clearance_hole = create_cylinder(
        get_clearance_hole_diameter(screw_size, clearance_type) / 2,
        flange_half_height * 2 + 50,
    )
    clearance_hole = rotate(
        90, axis=[1 if extension_alignment.axis != i else 0 for i in range(2)] + [0]
    )(clearance_hole)

    clearance_hole = align(clearance_hole, bottom_flange, Alignment.CENTER)

    bottom_flange = bottom_flange.cut(clearance_hole)
    top_flange = top_flange.cut(clearance_hole)

    bottom_flange_inner, bottom_flange_outer = cut_in_two(
        bottom_flange,
        cut_normal=[1 if extension_alignment.axis == i else 0 for i in range(3)],
    )

    if extension_alignment.sign == 1:
        bottom_flange_inner, bottom_flange_outer = (
            bottom_flange_outer,
            bottom_flange_inner,
        )

    bottom_flange = bottom_flange_inner
    top_flange = top_flange.fuse(bottom_flange_outer)

    return bottom_flange, top_flange, clearance_hole


def join_part_fans_with_extruder_cage(
    *,
    part_fans,
    extruder_cage,
    flange_extension=8.0,
    flange_half_height=3.0,
    screw_size="M3",
    clearance_type="loose",
):
    """Return joined output assemblies for a part fan and extruder cage pair."""

    flange_specs = [
        ("side_mount_plate", Alignment.LEFT),
        ("duct_back_mount_plate_connector", Alignment.BACK),
    ]

    bottom_flanges = []
    top_flanges = []
    consumed_part_fan_refs = []
    clearance_holes = []
    for anchor_name, extension_alignment in flange_specs:
        anchor_part = part_fans.get_named_non_production_part(anchor_name)
        consumed_part_fan_refs.append(
            part_fans.part_ref_for_named_non_production_part(anchor_name)
        )
        bottom_flange, top_flange, clearance_hole = _create_join_flange_halves(
            anchor_part=anchor_part,
            extension_alignment=extension_alignment,
            flange_extension=flange_extension,
            flange_half_height=flange_half_height,
            screw_size=screw_size,
            clearance_type=clearance_type,
        )
        bottom_flanges.append(bottom_flange)
        top_flanges.append(top_flange)
        clearance_holes.append(clearance_hole)

    joined_part_fans = LeaderFollowersCuttersPart(part_fans.leader.copy())
    for name, follower in part_fans.get_named_follower_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_part_fans.add_named_follower(follower.copy(), name)

    for name, nfp in part_fans.get_named_non_production_part_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_part_fans.add_named_non_production_part(nfp.copy(), name)

    for name, cutter in part_fans.get_named_cutter_items():
        joined_part_fans.add_named_cutter(cutter.copy(), name)

    joined_extruder_cage = LeaderFollowersCuttersPart(extruder_cage.leader.copy())
    for name, follower in extruder_cage.get_named_follower_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_extruder_cage.add_named_follower(follower.copy(), name)
    for name, nfp in extruder_cage.get_named_non_production_part_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_extruder_cage.add_named_non_production_part(nfp.copy(), name)
    for name, cutter in extruder_cage.get_named_cutter_items():
        if name in [anchor_name for anchor_name, _ in flange_specs]:
            continue
        joined_extruder_cage.add_named_cutter(cutter.copy(), name)

    for bottom_flange in bottom_flanges:
        joined_part_fans.leader = joined_part_fans.leader.fuse(bottom_flange)
        for clearance_hole in clearance_holes:
            joined_part_fans.leader = joined_part_fans.leader.cut(clearance_hole)
    for top_flange in top_flanges:
        joined_extruder_cage.leader = joined_extruder_cage.leader.fuse(top_flange)
        for clearance_hole in clearance_holes:
            joined_extruder_cage.leader = joined_extruder_cage.leader.cut(
                clearance_hole
            )
    for consumed_part_fan_ref in consumed_part_fan_refs:
        _logger.info(f"Adding consumed part ref for {consumed_part_fan_ref}")
        joined_part_fans.add_consumed_part_ref(consumed_part_fan_ref)

    return {
        "part_fans": joined_part_fans,
        "extruder_cage": joined_extruder_cage,
    }


def main():
    logging.basicConfig(level=logging.INFO)

    target_plate_thickness = 3
    target_plate_depth = 10
    target_plate_height = 10

    lower_target = create_box(
        target_plate_thickness,
        target_plate_depth,
        target_plate_height,
    )
    upper_target = create_box(
        target_plate_thickness,
        target_plate_depth,
        target_plate_height,
    )
    upper_target = align(upper_target, lower_target, Alignment.CENTER, axes=[0, 1])
    upper_target = align(upper_target, lower_target, Alignment.STACK_TOP)

    bottom_flange, top_flange, clearance_hole = _create_join_flange_halves(
        anchor_part=lower_target,
        extension_alignment=Alignment.LEFT,
        flange_extension=8,
        flange_half_height=3,
        screw_size="M3",
        clearance_type="loose",
    )

    lower_result = lower_target.fuse(bottom_flange)
    lower_result = lower_result.cut(clearance_hole)
    upper_result = upper_target.fuse(top_flange)
    upper_result = upper_result.cut(clearance_hole)

    parts = PartList()
    parts.add(
        lower_result,
        "lower_target_with_flange",
        flip=False,
    )
    parts.add(
        upper_result,
        "upper_target_with_flange",
        flip=False,
    )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=False,
    )

    _logger.info("Part fan cage join flange demo created successfully")


if __name__ == "__main__":
    main()
