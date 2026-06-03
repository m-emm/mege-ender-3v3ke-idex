"""
Idler Cage

Usage:
    cd <project_root> && ./run.sh path/to/idler_cage.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/idler_cage.py
"""

import copy
import logging
import os

import numpy as np
from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_PETGCF_04_HS,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "0",
    }
)

BIG_THING = 500

axle_screw_size = "M3"
endcap_tensioner_cage_back_wall = 8
endcap_tensioner_length = 16
endcap_tensioner_screw_size = "M3"
idler_cage_back_wall = 4
idler_cage_clearance = 0.5
idler_cage_idler_tooth_count = 20
idler_cage_overlength = 6
idler_cage_top_bottom_thickness = 4
idler_cage_wall = 2
idler_mount_axle_clearance = 0.1
idler_screw_head_clearance = 0.3
inset_cutter_hole_slack = 0.05


def _create_threaded_inset_visual(screw_size):
    screw_spec = MScrew.from_size(screw_size)
    inset_outer_radius = m_screws_table[screw_size]["thread_inset_hole_diameter"] / 2
    inset_length = m_screws_table[screw_size]["thread_inset_length"]

    threaded_inset = create_cylinder(inset_outer_radius, inset_length)
    inset_hole = create_cylinder(screw_spec.core_hole / 2, inset_length + 0.2)
    inset_hole = align(inset_hole, threaded_inset, Alignment.CENTER)

    return threaded_inset.cut(inset_hole)


def _create_tensioner_nut_visual(screw_size):
    nut = create_nut(screw_size)
    nut = rotate(30)(nut)
    nut = rotate(90, axis=(0, 1, 0))(nut)
    nut = rotate(90, axis=(1, 0, 0))(nut)
    return nut


def _get_min_cage_height_for_threaded_inset(
    idler_height,
    screw_size=axle_screw_size,
    extra_length=0.0,
):
    return idler_height + 2 * (
        m_screws_table[screw_size]["thread_inset_length"] + extra_length
    )


def create_idler_cage(
    cage_back_wall,
    cage_wall,
    cage_height,
    cage_overlength,
    idler_tooth_count,
    idler_clearance,
    with_tensioner=False,
    tensioner_screw_size="M3",
    tensioner_screw_length=30,
    axle_screw_length=None,
    belt_clearance=1.0,
    cage_width_override=None,
    cage_front_wall_thickness=None,
    tensioner_screw_z_offset=0.0,
    idler_cone_clearance=0.5,
):
    """Create a printable idler cage with visual idler and axle screw."""

    idler = create_gt2_idler(num_teeth=idler_tooth_count)
    idler_size = get_bounding_box_size(idler)
    min_cage_height_for_threaded_inset = _get_min_cage_height_for_threaded_inset(
        idler_size[2],
        screw_size=axle_screw_size,
        extra_length=inset_cutter_hole_slack,
    )
    assert cage_height >= min_cage_height_for_threaded_inset, (
        f"Cage height {cage_height} too low for {axle_screw_size} threaded inset; "
        f"need at least {min_cage_height_for_threaded_inset:.2f}"
    )

    effective_front_wall_thickness = (
        cage_wall if cage_front_wall_thickness is None else cage_front_wall_thickness
    )

    base_length = (
        idler_size[0]
        + cage_overlength
        + effective_front_wall_thickness
        + cage_back_wall
        + 2 * idler_clearance
    )
    base_width = max(
        idler_size[1] + 2 * cage_wall + 2 * idler_clearance,
        cage_width_override or 0,
    )
    base_thickness = (cage_height - idler_size[2] - 2 * idler_clearance) / 2
    wall_height = cage_height - 2 * base_thickness

    # Offset so the idler hugs the thin wall and leaves room for tensioner travel.
    x_offset = (effective_front_wall_thickness - cage_back_wall - cage_overlength) / 2
    base_z_offset = -(idler_size[2] / 2 + idler_clearance + base_thickness / 2)
    top_z_offset = idler_size[2] / 2 + idler_clearance + base_thickness / 2

    base = create_box(base_length, base_width, base_thickness)
    _logger.info(
        f"Creating idler cage with base_length={base_length:.2f}, base_width={base_width:.2f}, base_thickness={base_thickness:.2f}"
    )
    base = align(base, idler, Alignment.CENTER)
    base = translate(x_offset, 0, base_z_offset)(base)

    back_wall = create_box(cage_back_wall, base_width, wall_height)
    back_wall = align(back_wall, base, Alignment.CENTER, axes=[1])
    back_wall = align(back_wall, base, Alignment.LEFT)
    back_wall = align(back_wall, base, Alignment.STACK_TOP)

    walls = PartCollector()
    side_wall_length = max(cage_overlength, 0)
    if side_wall_length > 0:
        side_wall = create_box(side_wall_length, cage_wall, wall_height)
        side_wall = align(side_wall, base, Alignment.STACK_TOP)
        side_wall = align(side_wall, back_wall, Alignment.STACK_RIGHT)
        side_wall = align(side_wall, base, Alignment.BACK)
        walls = walls.fuse(side_wall)

        side_wall_2 = align(side_wall, base, Alignment.FRONT)
        walls = walls.fuse(side_wall_2)

    front_wall_width = idler_size[1] - 2 * belt_clearance
    if front_wall_width > 0:
        front_wall = create_box(
            effective_front_wall_thickness,
            front_wall_width,
            wall_height,
        )
        front_wall = align(front_wall, base, Alignment.CENTER, axes=[1])
        front_wall = align(front_wall, base, Alignment.STACK_TOP)
        front_wall = align(front_wall, base, Alignment.RIGHT)
        walls = walls.fuse(front_wall)

    top_plate = create_box(base_length, base_width, base_thickness)
    top_plate = align(top_plate, idler, Alignment.CENTER)
    top_plate = translate(x_offset, 0, top_z_offset)(top_plate)

    cage = PartCollector()
    cage = cage.fuse(base)
    cage = cage.fuse(back_wall)
    cage = cage.fuse(walls)
    cage = cage.fuse(top_plate)

    axle_cutter_radius = (
        MScrew.from_size(axle_screw_size).clearance_hole_normal / 2
        + idler_mount_axle_clearance
    )
    axle_cutter = create_cylinder(axle_cutter_radius, BIG_THING)
    axle_cutter = align(axle_cutter, idler, Alignment.CENTER)
    cage = cage.cut(axle_cutter)

    head_cutter = create_cylinder(
        MScrew.from_size(axle_screw_size).cylinder_head_diameter / 2
        + idler_screw_head_clearance,
        MScrew.from_size(axle_screw_size).cylinder_head_height
        + 2 * idler_screw_head_clearance,
    )
    head_cutter = align(head_cutter, idler, Alignment.CENTER)
    head_cutter = align(head_cutter, cage, Alignment.TOP)
    cage = cage.cut(head_cutter)

    thread_inset_cutter = create_cylinder(
        m_screws_table[axle_screw_size]["thread_inset_hole_diameter"] / 2
        + inset_cutter_hole_slack,
        m_screws_table[axle_screw_size]["thread_inset_length"]
        + inset_cutter_hole_slack,
    )
    thread_inset_cutter = align(
        thread_inset_cutter,
        idler,
        Alignment.CENTER,
        axes=[0, 1],
    )
    thread_inset_cutter = align(thread_inset_cutter, cage, Alignment.BOTTOM)
    cage = cage.cut(thread_inset_cutter)

    axle_threaded_inset = _create_threaded_inset_visual(axle_screw_size)
    axle_threaded_inset = align(
        axle_threaded_inset,
        idler,
        Alignment.CENTER,
        axes=[0, 1],
    )
    axle_threaded_inset = align(axle_threaded_inset, cage, Alignment.BOTTOM)

    if axle_screw_length is None:
        axle_screw_length = (
            cage_height - MScrew.from_size(axle_screw_size).cylinder_head_height
        )
    axle = create_cylinder_screw(axle_screw_size, length=axle_screw_length)
    axle = align(axle, idler, Alignment.CENTER)
    axle = align(axle, cage, Alignment.TOP)

    idler_cone_height = 4
    idler_cone_extre_radius = 1
    for bt in [Alignment.BOTTOM, Alignment.TOP]:

        idler_cone = create_cone(
            radius1=axle_cutter_radius + idler_cone_height + idler_cone_extre_radius,
            radius2=axle_cutter_radius + idler_cone_extre_radius,
            height=idler_cone_height,
            direction=(0, 0, -bt.sign),
        )

        idler_cone = align(idler_cone, idler, Alignment.CENTER)
        idler_cone = align(
            idler_cone, idler, bt.stack_alignment, stack_gap=idler_cone_clearance
        )

        idler_cone = idler_cone.cut(axle_cutter)
        cage = cage.fuse(idler_cone)

    retval = LeaderFollowersCuttersPart(leader=cage)
    retval.add_named_non_production_part(idler, "idler")
    retval.add_named_non_production_part(axle, "axle")
    retval.add_named_non_production_part(axle_threaded_inset, "axle_threaded_inset")

    if with_tensioner:
        tensioner_clearance_radius = (
            MScrew.from_size(tensioner_screw_size).clearance_hole_normal / 2
        )

        clearance_cutter = create_cylinder(
            tensioner_clearance_radius,
            cage_back_wall + 0.2,
        )
        clearance_cutter = rotate(90, axis=(0, 1, 0))(clearance_cutter)
        clearance_cutter = align(
            clearance_cutter,
            idler,
            Alignment.CENTER,
            axes=[1, 2],
        )
        clearance_cutter = align(clearance_cutter, back_wall, Alignment.LEFT)
        clearance_cutter = translate(0, 0, tensioner_screw_z_offset)(clearance_cutter)
        cage = cage.cut(clearance_cutter)

        tensioner_screw = create_cylinder_screw(
            tensioner_screw_size,
            length=tensioner_screw_length,
        )
        tensioner_screw = rotate(90, axis=(0, 1, 0))(tensioner_screw)
        tensioner_screw = rotate(180)(tensioner_screw)
        tensioner_screw = align(
            tensioner_screw,
            clearance_cutter,
            Alignment.CENTER,
            axes=[1, 2],
        )
        tensioner_screw = align(
            tensioner_screw,
            idler,
            Alignment.STACK_LEFT,
            stack_gap=idler_clearance,
        )

        hidden_nut_cutter = create_hidden_nut_pocket_cutter(
            tensioner_screw_size,
            bottom_cutter_length=3,
            top_cutter_length=3,
            slack=0.3,
        )
        hidden_nut_cutter = rotate(90, axis=(0, 1, 0))(hidden_nut_cutter)
        hidden_nut_cutter = rotate(90, axis=(1, 0, 0))(hidden_nut_cutter)
        hidden_nut_cutter = align(
            hidden_nut_cutter,
            tensioner_screw,
            Alignment.CENTER,
        )
        hidden_nut_cutter = align(hidden_nut_cutter, cage, Alignment.LEFT)

        hidden_nut_cutter_size = get_bounding_box_size(hidden_nut_cutter)
        hidden_nut_cutter = translate(
            cage_back_wall / 2 - hidden_nut_cutter_size[0] / 2,
            0,
            0,
        )(hidden_nut_cutter)

        cage = hidden_nut_cutter.use_as_cutter_on(cage)
        retval.leader = cage
        retval.add_named_non_production_part(tensioner_screw, "tensioner_screw")

        tensioner_nut = _create_tensioner_nut_visual(tensioner_screw_size)
        tensioner_nut = align(
            tensioner_nut,
            hidden_nut_cutter.leader,
            Alignment.CENTER,
        )
        retval.add_named_non_production_part(tensioner_nut, "tensioner_nut")

    retval_bbox = get_bounding_box(retval)
    retval_bbox_size = get_bounding_box_size(retval)
    assert np.allclose(
        retval_bbox_size[2],
        cage_height,
    ), f"Expected cage height {cage_height}, got {retval_bbox_size[2]}"
    drop_to_bed = -retval_bbox[0][2]

    return translate(0, 0, drop_to_bed)(retval)


def _get_demo_cage_height(
    idler_tooth_count=idler_cage_idler_tooth_count,
    idler_clearance=idler_cage_clearance,
    threaded_inset_visual_gap=0.5,
):
    idler = create_gt2_idler(num_teeth=idler_tooth_count)
    idler_height = get_bounding_box_size(idler)[2]
    default_demo_height = (
        idler_height + 2 * idler_clearance + 2 * idler_cage_top_bottom_thickness
    )
    min_height_for_threaded_inset = _get_min_cage_height_for_threaded_inset(
        idler_height,
        screw_size=axle_screw_size,
        extra_length=threaded_inset_visual_gap,
    )

    return max(default_demo_height, min_height_for_threaded_inset)


def create_demo_idler_cage(with_tensioner=False, tensioner_screw_z_offset=0.0):
    demo_cage_height = _get_demo_cage_height()
    cage_kwargs = {
        "cage_back_wall": idler_cage_back_wall,
        "cage_wall": idler_cage_wall,
        "cage_height": demo_cage_height,
        "cage_overlength": idler_cage_overlength,
        "idler_tooth_count": idler_cage_idler_tooth_count,
        "idler_clearance": idler_cage_clearance,
        "axle_screw_length": (
            demo_cage_height - MScrew.from_size(axle_screw_size).cylinder_head_height
        ),
    }

    if with_tensioner:
        cage_kwargs.update(
            {
                "cage_back_wall": endcap_tensioner_cage_back_wall,
                "cage_overlength": endcap_tensioner_length,
                "with_tensioner": True,
                "tensioner_screw_size": endcap_tensioner_screw_size,
                "cage_front_wall_thickness": idler_cage_wall,
                "tensioner_screw_z_offset": tensioner_screw_z_offset,
            }
        )

    return create_idler_cage(**cage_kwargs)


def _create_front_cutaway_cutter(part):
    part_size = get_bounding_box_size(part)
    cutter = create_box(
        part_size[0] + 2 * idler_cage_clearance,
        part_size[1] / 2 + 2 * idler_cage_clearance,
        part_size[2] + 2 * idler_cage_clearance,
    )
    cutter = align(cutter, part, Alignment.CENTER, axes=[0, 2])
    cutter = align(cutter, part, Alignment.FRONT)
    return cutter


def create_demo_idler_cage_cutaway(tensioner_screw_z_offset=0.0):
    idler_cage = create_demo_idler_cage(
        with_tensioner=True,
        tensioner_screw_z_offset=tensioner_screw_z_offset,
    )
    cutaway_cutter = _create_front_cutaway_cutter(idler_cage.leader)

    cutaway_view = LeaderFollowersCuttersPart(idler_cage.leader.cut(cutaway_cutter))
    for name, part in idler_cage.get_named_non_production_part_items():
        cutaway_view.add_named_non_production_part(
            part.cut(cutaway_cutter),
            name,
        )

    return cutaway_view


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    basic_cage = create_demo_idler_cage().leader
    tensioner_cage = create_demo_idler_cage(with_tensioner=True).leader
    cutaway_view = create_demo_idler_cage_cutaway()
    cutaway_view_z_offset = create_demo_idler_cage_cutaway(tensioner_screw_z_offset=3.0)

    tensioner_cage = align(
        tensioner_cage,
        basic_cage,
        Alignment.STACK_RIGHT,
        stack_gap=20,
    )
    cutaway_view = align(
        cutaway_view,
        tensioner_cage,
        Alignment.STACK_RIGHT,
        stack_gap=20,
    )
    cutaway_view_z_offset = align(
        cutaway_view_z_offset,
        cutaway_view,
        Alignment.STACK_RIGHT,
        stack_gap=20,
    )

    parts.add(basic_cage, "idler_cage_basic", flip=False)
    parts.add(tensioner_cage, "idler_cage_tensioner", flip=False)
    parts.add(cutaway_view.leader, "idler_cage_tensioner_cutaway_body", flip=False)
    for name, part in cutaway_view.get_named_non_production_part_items():
        parts.add(part, f"idler_cage_tensioner_cutaway_{name}", flip=False)
    parts.add(
        cutaway_view_z_offset.leader,
        "idler_cage_tensioner_cutaway_z_offset_3_body",
        flip=False,
    )
    for name, part in cutaway_view_z_offset.get_named_non_production_part_items():
        parts.add(
            part,
            f"idler_cage_tensioner_cutaway_z_offset_3_{name}",
            flip=False,
        )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("idler_cage created successfully!")


if __name__ == "__main__":
    main()
