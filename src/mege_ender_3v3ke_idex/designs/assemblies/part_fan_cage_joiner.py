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
        flange_half_height,
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

    flange_stack = bottom_flange.fuse(top_flange)
    clearance_hole = create_cylinder(
        get_clearance_hole_diameter(screw_size, clearance_type) / 2,
        flange_half_height * 2 + 2,
    )
    clearance_hole = align(clearance_hole, flange_stack, Alignment.CENTER)
    clearance_hole = align(clearance_hole, tab_reference, Alignment.CENTER, axes=[0, 1])

    bottom_flange = bottom_flange.cut(clearance_hole)
    top_flange = top_flange.cut(clearance_hole)

    return bottom_flange, top_flange, clearance_hole


def join_part_fans_with_extruder_cage(
    *,
    part_fans,
    extruder_cage,
    belt_carriage=None,
    sprite_extruder=None,
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
    for anchor_name, extension_alignment in flange_specs:
        anchor_part = part_fans.get_named_non_production_part(anchor_name)
        consumed_part_fan_refs.append(
            part_fans.part_ref_for_named_non_production_part(anchor_name)
        )
        bottom_flange, top_flange, _ = _create_join_flange_halves(
            anchor_part=anchor_part,
            extension_alignment=extension_alignment,
            flange_extension=flange_extension,
            flange_half_height=flange_half_height,
            screw_size=screw_size,
            clearance_type=clearance_type,
        )
        bottom_flanges.append(bottom_flange)
        top_flanges.append(top_flange)

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
    for top_flange in top_flanges:
        joined_extruder_cage.leader = joined_extruder_cage.leader.fuse(top_flange)
    for consumed_part_fan_ref in consumed_part_fan_refs:
        _logger.info(f"Adding consumed part ref for {consumed_part_fan_ref}")
        joined_part_fans.add_consumed_part_ref(consumed_part_fan_ref)

    if belt_carriage is not None:
        mount_eye_width = 12.5
        mount_eye_depth = 5
        mount_eye_height = 20
        mount_eye_l_depth = 10
        mount_eye_l_thickness = 3

        belt_carriage_mount_eye = create_box(
            mount_eye_width, mount_eye_depth, mount_eye_height
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, belt_carriage, Alignment.CENTER
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, belt_carriage, Alignment.TOP
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, belt_carriage, Alignment.STACK_FRONT
        )
        belt_carriage_mount_eye = align(
            belt_carriage_mount_eye, sprite_extruder, Alignment.STACK_RIGHT, stack_gap=1
        )

        belt_carriage_mount_eye_l = create_box(
            mount_eye_width, mount_eye_l_depth, mount_eye_l_thickness
        )
        belt_carriage_mount_eye_l = align(
            belt_carriage_mount_eye_l, belt_carriage_mount_eye, Alignment.CENTER
        )
        belt_carriage_mount_eye_l = align(
            belt_carriage_mount_eye_l, belt_carriage_mount_eye, Alignment.STACK_FRONT
        )
        belt_carriage_mount_eye_l = align(
            belt_carriage_mount_eye_l, belt_carriage_mount_eye, Alignment.TOP
        )

        belt_carriage_mount_eye = belt_carriage_mount_eye.fuse(
            belt_carriage_mount_eye_l
        )

        right_clamp_hole_drill = belt_carriage.get_named_cutter(
            "right_clamp_hole_drill"
        )

        joined_extruder_cage = joined_extruder_cage.fuse(belt_carriage_mount_eye)
        joined_extruder_cage = joined_extruder_cage.cut(right_clamp_hole_drill)

        left_bridge_hole_drill = belt_carriage.get_named_cutter(
            "left_bridge_hole_drill"
        )

        left_bridge_mount_eye_width = 8
        left_bridge_mount_eye_depth = 3
        left_bridge_mount_eye_height = 30
        left_bridge_mount_eye = create_box(
            left_bridge_mount_eye_width,
            left_bridge_mount_eye_depth,
            left_bridge_mount_eye_height,
        )
        left_bridge_mount_eye = align(
            left_bridge_mount_eye, left_bridge_hole_drill, Alignment.CENTER
        )

        left_bridge_mount_eye = align(
            left_bridge_mount_eye, sprite_extruder, Alignment.STACK_BACK
        )
        left_bridge_mount_eye = align(
            left_bridge_mount_eye, joined_extruder_cage, Alignment.TOP
        )

        left_bridge_mount_eye = align(
            left_bridge_mount_eye, joined_extruder_cage, Alignment.LEFT
        )

        left_bridge_mount_eye = left_bridge_mount_eye.cut(left_bridge_hole_drill)
        joined_extruder_cage = joined_extruder_cage.fuse(left_bridge_mount_eye)

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

    bottom_flange, top_flange, _ = _create_join_flange_halves(
        anchor_part=lower_target,
        extension_alignment=Alignment.LEFT,
        flange_extension=8,
        flange_half_height=3,
        screw_size="M3",
        clearance_type="loose",
    )

    parts = PartList()
    parts.add(
        lower_target.fuse(bottom_flange),
        "lower_target_with_flange",
        flip=False,
    )
    parts.add(
        upper_target.fuse(top_flange),
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
