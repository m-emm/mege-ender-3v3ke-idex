"""
X Axis

Usage:
    cd <project_root> && ./run.sh path/to/x_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/x_axis.py
"""

import copy
import json
import logging
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_PETGCF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.endstop_holder import create_endstop_holder
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_carriage,
    create_mgn12h_rail,
    mgn_12h_carriage_length,
)
from mege_ender_3v3ke_idex.designs.motor_mount import create_motor_stack
from mege_ender_3v3ke_idex.designs.printer_frame import create_printer_frame
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (  # noqa: F401
    create_four_screws_mount_assembly,
    create_screw_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.tool_head_mount import create_tool_head_mount
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXTUDER_STEP_PATH = PROJECT_ROOT / "resources" / "creality_sprite.step.zip"

BIG_THING = 500


PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "enable_support": "1",
        "support_threshold_angle": "30",
        "brim_type": "no_brim",
        "support_on_build_plate_only": "1",
        "support_critical_regions_only": "1",
        "support_top_z_distance": "0.3",
        "support_interface_spacing": "0.8",
        "fan_min_speed": "10",
        "fan_max_speed": "25",
        "external_perimeter_speed": "75",
        "outer_wall_speed": "75",
        "sparse_infill_density": "85%",
        # "support_type": "tree(auto)",
        # "support_style": "tree_slim",
        # "wall_loops": "3",
        # "sparse_infill_density": "85%",  # PLAGFHT is very brittle and needs more strength
        # # Inter-layer adhesion / brittleness tuning
        # "nozzle_temperature": "235",
        # "fan_min_speed": "45",
        # "fan_max_speed": "65",
        # "overhang_fan_speed": "80",
        # "filament_max_volumetric_speed": "18",
        # "outer_wall_speed": "85",
        # "inner_wall_speed": "150",
        # "sparse_infill_speed": "150",
        # "internal_solid_infill_speed": "150",
        # "filament_flow_ratio": "1.01",
        # "infill_wall_overlap": "28%",
    }
)

endstop_holder_z_offset = 8
endstop_holder_inset_from_end = 15
endstop_holder_stack_gap = 1
endstop_holder_mount_plate_thickness = 4.5
endstop_holder_mount_plate_width = 8
endstop_holder_mount_plate_length = 20
endstop_holder_mount_screw_size = "M3"
endstop_holder_groove_holder_bottom_width = 6.3
endstop_holder_groove_holder_top_width = 6.0
endstop_holder_groove_holder_slit = 1.5
endstop_holder_groove_holder_height = 5

carriage_offset = x_axis_rail_length / 2 - mgn_12h_carriage_length / 2


endcap_vertical_coupler_size = 13
endcap_vertical_coupler_screw_size = "M5"
endcap_vertical_coupler_screw_length = 70


def create_rhomboid(length, width, thickness, angle, fillet_radius=None):
    """Create a rhomboid shape by shearing a box."""
    extra_length = width * np.tan(np.radians(angle))

    rotation_angle = -(90 - angle)
    box = create_box(length + extra_length, width, thickness)

    cutter = create_box(BIG_THING, BIG_THING, BIG_THING)

    cutter = translate(-BIG_THING, -BIG_THING / 2, 0)(cutter)
    cutter = rotate(rotation_angle)(cutter)

    rhomboid = box.cut(cutter)

    right_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    right_cutter = translate(0, -BIG_THING / 2, 0)(right_cutter)
    right_cutter = rotate(rotation_angle)(right_cutter)
    right_cutter = translate(length, 0, 0)(right_cutter)
    rhomboid = rhomboid.cut(right_cutter)

    if fillet_radius is not None:

        def edge_filter(bbox, v0_point, v1_point):
            v0_point = np.array(v0_point)
            v1_point = np.array(v1_point)
            edge_direction = v1_point - v0_point
            if np.allclose(edge_direction[0], 0) and np.allclose(edge_direction[1], 0):
                return True

            return False

        fillet_edges = filter_edges_by_function(rhomboid, edge_filter)
        rhomboid = apply_fillet_to_edges(rhomboid, fillet_radius, fillet_edges)

    return rhomboid


def create_z_axis():
    """Create the x_axis part."""

    # # resources/ender3top_only.step

    # step_file_path = PROJECT_ROOT / "resources" / "zaxis_only.step"

    # ender_part = import_solid_from_step(step_file_path)

    # ender_part = rotate(90, axis=(1, 0, 0))(ender_part)

    guide_width = 40
    guide_thickness = 2
    guide_length = 350

    guide1 = create_box(guide_width, guide_thickness, guide_length)
    guide2 = create_box(guide_width, guide_thickness, guide_length)
    guide2 = align(
        guide2, guide1, Alignment.STACK_RIGHT, stack_gap=z_axis_guide_distance
    )

    z_guides = guide1.fuse(guide2)

    # z_guides = align(z_guides, ender_part, Alignment.CENTER)

    # ender_part = ender_part.fuse(guides)

    return z_guides


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
):
    """Create a printable idler cage with visual idler and axle screw."""

    idler = create_gt2_idler(num_teeth=idler_tooth_count)
    idler_size = get_bounding_box_size(idler)

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
        idler_size[1] + 2 * cage_wall + 2 * idler_clearance, cage_width_override or 0
    )
    base_thickness = (cage_height - idler_size[2] - 2 * idler_clearance) / 2
    wall_height = cage_height - 2 * base_thickness

    # Offset so the idler hugs the thin wall (belt clearance) and leaves room for tensioner on the thick wall
    x_offset = (effective_front_wall_thickness - cage_back_wall - cage_overlength) / 2
    base_z_offset = -(idler_size[2] / 2 + idler_clearance + base_thickness / 2)
    top_z_offset = idler_size[2] / 2 + idler_clearance + base_thickness / 2

    base = create_box(base_length, base_width, base_thickness)
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
        thread_inset_cutter, idler, Alignment.CENTER, axes=[0, 1]
    )
    thread_inset_cutter = align(thread_inset_cutter, cage, Alignment.BOTTOM)
    cage = cage.cut(thread_inset_cutter)

    if axle_screw_length is None:
        axle_screw_length = (
            cage_height - MScrew.from_size(axle_screw_size).cylinder_head_height
        )
    axle = create_cylinder_screw(axle_screw_size, length=axle_screw_length)
    axle = align(axle, idler, Alignment.CENTER)
    axle = align(axle, cage, Alignment.TOP)

    retval = LeaderFollowersCuttersPart(
        leader=cage,
    )
    retval.add_named_non_production_part(idler, "idler")
    retval.add_named_non_production_part(axle, "axle")

    if with_tensioner:
        tensioner_clearance_radius = (
            MScrew.from_size(tensioner_screw_size).clearance_hole_normal / 2
        )

        clearance_cutter = create_cylinder(
            tensioner_clearance_radius,
            cage_back_wall + 0.2,
        )
        clearance_cutter = rotate(90, axis=(0, 1, 0))(clearance_cutter)
        clearance_cutter = align(clearance_cutter, idler, Alignment.CENTER, axes=[1, 2])
        clearance_cutter = align(clearance_cutter, back_wall, Alignment.LEFT)

        cage = cage.cut(clearance_cutter)

        tensioner_screw = create_cylinder_screw(
            tensioner_screw_size, length=tensioner_screw_length
        )
        tensioner_screw = rotate(90, axis=(0, 1, 0))(tensioner_screw)
        tensioner_screw = rotate(180)(tensioner_screw)

        tensioner_screw = align(
            tensioner_screw, clearance_cutter, Alignment.CENTER, axes=[1, 2]
        )
        tensioner_screw = align(
            tensioner_screw, idler, Alignment.STACK_LEFT, stack_gap=idler_clearance
        )

        hidden_nut_cutter = create_hidden_nut_pocket_cutter(
            tensioner_screw_size,
            bottom_cutter_length=3,
            top_cutter_length=3,
            slack=0.3,
        )

        hidden_nut_cutter = rotate(90, axis=(0, 1, 0))(hidden_nut_cutter)
        hidden_nut_cutter = rotate(90, axis=(1, 0, 0))(hidden_nut_cutter)

        hidden_nut_cutter = align(hidden_nut_cutter, tensioner_screw, Alignment.CENTER)

        hidden_nut_cutter = align(hidden_nut_cutter, cage, Alignment.LEFT)

        hidden_nut_cutter_size = get_bounding_box_size(hidden_nut_cutter)
        hidden_nut_cutter = translate(
            cage_back_wall / 2 - hidden_nut_cutter_size[0] / 2, 0, 0
        )(hidden_nut_cutter)

        cage = hidden_nut_cutter.use_as_cutter_on(cage)

        retval.leader = cage

        retval.add_named_non_production_part(tensioner_screw, "tensioner_screw")

    retval_bbox = get_bounding_box(retval)
    retval_bbox_size = get_bounding_box_size(retval)
    assert np.allclose(
        retval_bbox_size[2], cage_height
    ), f"Expected cage height {cage_height}, got {retval_bbox_size[2]}"
    drop_to_bed = -(retval_bbox[0][2])
    retval = translate(0, 0, drop_to_bed)(retval)

    return retval


def create_idler_endcap(profile, with_tensioner, side, endcap_top_bottom):
    """Create an idler endcap built around the idler cage (no tensioner version for now)."""

    profile_size = get_bounding_box_size(profile)

    idler = create_gt2_idler(num_teeth=endcap_idler_tooth_count)
    idler_size = get_bounding_box_size(idler)

    target_cage_length = 1.3 * (idler_size[0] + 2 * endcap_clearance)
    if with_tensioner:
        target_cage_length += endcap_tensioner_length
    cage_overlength = target_cage_length - idler_size[0]

    cage_height = (
        profile_size[2]
        + 2 * endcap_top_bottom_wall
        - endcap_tensioner_outer_box_bottom_cage_clearance
        - endcap_tensioner_outer_box_bottom_thickness
    )

    outer_box_height = (
        cage_height
        + endcap_tensioner_outer_box_bottom_cage_clearance
        + endcap_tensioner_outer_box_bottom_thickness
    )

    if with_tensioner:
        cage_width_override = profile_size[1]
    else:
        cage_width_override = profile_size[1] + 2 * endcap_wall + 2 * endcap_clearance

    cage = create_idler_cage(
        cage_back_wall=(
            idler_cage_back_wall
            if not with_tensioner
            else endcap_tensioner_cage_back_wall
        ),
        cage_front_wall_thickness=endcap_wall
        + (endcap_profile_overlap if not with_tensioner else 0),
        cage_wall=idler_cage_wall,
        cage_height=cage_height,
        cage_overlength=cage_overlength,
        idler_tooth_count=endcap_idler_tooth_count,
        idler_clearance=endcap_idler_clearance,
        with_tensioner=with_tensioner,
        tensioner_screw_size=endcap_tensioner_screw_size,
        axle_screw_length=endcap_axle_screw_length,
        belt_clearance=endcap_belt_clearance,
        cage_width_override=cage_width_override,
    )

    if side != Alignment.LEFT:
        cage = rotate(180)(cage)

    cage = align(cage, profile, Alignment.CENTER)

    if with_tensioner:
        cage = align(
            cage,
            profile,
            side.stack_alignment,
            stack_gap=endcap_wall + endcap_tensioner_cage_clearance,
        )
    else:
        cage = align(
            cage, profile, side.stack_alignment, stack_gap=-endcap_profile_overlap
        )

    profile_cutter = create_box(
        BIG_THING,
        profile_size[1] + endcap_profile_clearance,
        profile_size[2] + endcap_profile_clearance,
    )
    profile_cutter = align(profile_cutter, profile, Alignment.CENTER)
    profile_cutter = align(profile_cutter, profile, side)

    cage = cage.cut(profile_cutter)

    mount_eye = create_filleted_box(
        profile_size[1] * 0.6,
        profile_size[1],
        endcap_top_bottom_wall
        + endcap_profile_clearance
        + endcap_tensioner_outer_box_bottom_thickness
        + endcap_tensioner_outer_box_bottom_cage_clearance,
        fillet_radius=endcap_mount_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side],
    )
    mont_eye_screw_hole_cutter = create_cylinder(
        MScrew.from_size(endcap_mount_screw_size).clearance_hole_normal / 2,
        BIG_THING,
    )
    mont_eye_screw_hole_cutter = align(
        mont_eye_screw_hole_cutter, mount_eye, Alignment.CENTER
    )
    mount_eye = mount_eye.cut(mont_eye_screw_hole_cutter)

    if with_tensioner:

        cage_size = get_bounding_box_size(cage)

        outer_box = create_box(
            cage_size[0]
            + endcap_profile_overlap
            + endcap_wall
            + endcap_outer_box_back_wall
            + 2 * endcap_tensioner_cage_clearance
            + endcap_tensioner_travel,
            cage_size[1] + 2 * endcap_wall,
            outer_box_height,
        )

        outer_box = align(outer_box, cage, Alignment.CENTER)
        outer_box = align(outer_box, cage, Alignment.TOP)
        outer_box = align(
            outer_box, profile, side.stack_alignment, stack_gap=-endcap_profile_overlap
        )

        cage_cutter = create_box(
            cage_size[0]
            + 2 * endcap_tensioner_cage_clearance
            + endcap_tensioner_travel,
            cage_size[1] + 2 * endcap_tensioner_cage_clearance,
            BIG_THING,
        )
        cage_cutter = align(cage_cutter, cage, Alignment.CENTER)
        cage_cutter = align(cage_cutter, cage, side.opposite)
        cage_cutter = align(cage_cutter, outer_box, Alignment.BOTTOM)
        cage_cutter = translate(
            -side.sign * endcap_tensioner_cage_clearance,
            0,
            endcap_tensioner_outer_box_bottom_thickness,
        )(cage_cutter)

        outer_box = outer_box.cut(cage_cutter)

        profile_cutter = create_box(
            profile_size[0] + endcap_profile_clearance,
            profile_size[1] + 2 * endcap_profile_clearance,
            profile_size[2] + 2 * endcap_profile_clearance,
        )
        profile_cutter = align(profile_cutter, profile, Alignment.CENTER)
        outer_box = outer_box.cut(profile_cutter)

        side_hole_size_diagonal = np.sqrt(2) * endcap_side_hole_size
        side_hole_pitch = side_hole_size_diagonal * 1.5

        outer_bounding_box_size = get_bounding_box_size(outer_box)

        num_x_side_holes = int(
            (outer_bounding_box_size[0] - 2 * endcap_side_hole_boundary)
            / side_hole_pitch
        )

        num_z_side_holes = int(
            (outer_bounding_box_size[2] - 2 * endcap_side_hole_boundary)
            / side_hole_pitch
        )

        side_hole_drills = PartCollector()
        for ix in range(num_x_side_holes):
            for iz in range(num_z_side_holes):
                side_hole_drill = create_box(
                    endcap_side_hole_size, BIG_THING, endcap_side_hole_size
                )
                side_hole_drill = rotate(45, axis=(0, 1, 0))(side_hole_drill)
                side_hole_drill = align(side_hole_drill, outer_box, Alignment.CENTER)
                x_offset = ix * side_hole_pitch
                z_offset = iz * side_hole_pitch
                side_hole_drill = translate(x_offset, 0, z_offset)(side_hole_drill)
                side_hole_drills = side_hole_drills.fuse(side_hole_drill)

        side_hole_drills = align(side_hole_drills, outer_box, Alignment.CENTER)
        outer_box = outer_box.cut(side_hole_drills)

        obbcc = PartCollector()
        for fb in [Alignment.FRONT, Alignment.BACK]:
            belt_clearance_cutter = create_box(
                BIG_THING,
                endcap_profile_groove_depth,
                endcap_belt_width + 2 * endcap_belt_vertical_clearance,
            )
            belt_clearance_cutter = align(
                belt_clearance_cutter, profile, Alignment.CENTER
            )
            belt_clearance_cutter = align(belt_clearance_cutter, profile, fb)
            belt_clearance_cutter = align(
                belt_clearance_cutter, cage, side.opposite.stack_alignment
            )
            outer_box = outer_box.cut(belt_clearance_cutter)

            belt_side_clearance_cutter_length = endcap_profile_overlap
            belt_side_clearance_cutter = create_pyramid_stump(
                belt_side_clearance_cutter_length,
                belt_side_clearance_cutter_length,
                endcap_belt_width * 2,
                endcap_belt_width,
                endcap_belt_width * 0.8,
            )

            belt_side_clearance_cutter = rotate(-90 * fb.sign, axis=(1, 0, 0))(
                belt_side_clearance_cutter
            )
            belt_side_clearance_cutter = align(
                belt_side_clearance_cutter, outer_box, Alignment.CENTER
            )

            belt_side_clearance_cutter = align(
                belt_side_clearance_cutter, outer_box, side.opposite
            )
            outer_box_size = get_bounding_box_size(outer_box)
            wall_at_profile = (
                outer_box_size[1] - profile_size[1]
            ) / 2 + endcap_profile_clearance

            belt_side_clearance_cutter = align(
                belt_side_clearance_cutter,
                outer_box,
                fb.stack_alignment,
                stack_gap=-wall_at_profile,
            )

            obbcc = obbcc.fuse(belt_side_clearance_cutter)

        outer_box = outer_box.cut(obbcc)
        tensioner_screw_part = cage.get_non_production_part_by_name("tensioner_screw")
        tensioner_screw_part = align(tensioner_screw_part, outer_box, side)
        tensioner_screw_part = translate(
            side.sign
            * MScrew.from_size(endcap_tensioner_screw_size).cylinder_head_height,
            0,
            0,
        )(tensioner_screw_part)

        tensioner_screw_hole_cutter = create_cylinder(
            MScrew.from_size(endcap_tensioner_screw_size).clearance_hole_normal / 2,
            BIG_THING,
        )
        tensioner_screw_hole_cutter = rotate(90, axis=(0, 1, 0))(
            tensioner_screw_hole_cutter
        )
        tensioner_screw_hole_cutter = align(
            tensioner_screw_hole_cutter, tensioner_screw_part, Alignment.CENTER
        )

        tensioner_screw_hole_cutter = align(
            tensioner_screw_hole_cutter,
            outer_box,
            side.stack_alignment,
            stack_gap=-2 * endcap_wall,
        )
        outer_box = outer_box.cut(tensioner_screw_hole_cutter)

        mount_eye = align(
            mount_eye,
            outer_box,
            Alignment.CENTER,
        )
        mount_eye = align(mount_eye, outer_box, Alignment.BOTTOM)

        mount_eye = align(
            mount_eye,
            outer_box,
            side.opposite.stack_alignment,
        )
        mount_eye = mount_eye.cut(profile_cutter)
        outer_box = outer_box.fuse(mount_eye)

        retval = LeaderFollowersCuttersPart(leader=outer_box)
        retval.add_named_follower(cage.leader, "endcap_idler_cage")

    else:
        mount_eye = align(
            mount_eye,
            cage,
            Alignment.CENTER,
        )
        mount_eye = align(mount_eye, cage, Alignment.BOTTOM)

        mount_eye = align(
            mount_eye,
            cage,
            side.opposite.stack_alignment,
        )

        mount_eye = mount_eye.cut(profile_cutter)
        cage = cage.fuse(mount_eye)

        retval = LeaderFollowersCuttersPart(leader=cage.leader)
        retval.add_named_follower(cage.leader, "endcap_idler_cage")

    idler_part = cage.get_non_production_part_by_name("idler")
    retval.add_named_follower(idler_part, "idler")

    axle_part = cage.get_non_production_part_by_name("axle")
    retval.add_named_non_production_part(axle_part, "axle")

    if with_tensioner:

        retval.add_named_non_production_part(tensioner_screw_part, "tensioner_screw")

    endcap_vertical_couplers = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        endcap_size = get_bounding_box_size(retval)
        profile_size = get_bounding_box_size(profile)

        endcap_vertical_coupler = create_box(
            endcap_vertical_coupler_size, endcap_vertical_coupler_size, endcap_size[2]
        )
        endcap_vertical_coupler = align(
            endcap_vertical_coupler, retval, Alignment.CENTER
        )
        endcap_vertical_coupler = align(
            endcap_vertical_coupler, retval, fb.stack_alignment
        )
        endcap_vertical_coupler = align(
            endcap_vertical_coupler, retval, Alignment.BOTTOM
        )

        endcap_vertical_coupler = align(endcap_vertical_coupler, retval, side)

        endcap_vertical_coupler_connector = create_box(
            endcap_vertical_coupler_size,
            endcap_vertical_coupler_size,
            x_axis_profile_pitch / 2 - profile_size[2] / 2,
        )
        endcap_vertical_coupler_connector = align(
            endcap_vertical_coupler_connector, endcap_vertical_coupler, Alignment.CENTER
        )
        endcap_vertical_coupler_connector = align(
            endcap_vertical_coupler_connector,
            profile,
            Alignment.STACK_TOP,
        )

        endcap_vertical_coupler = endcap_vertical_coupler.fuse(
            endcap_vertical_coupler_connector
        )

        endcap_vertical_coupler_bbox_size = get_bounding_box_size(
            endcap_vertical_coupler
        )
        endcap_vertical_coupler_total_representative = create_box(
            endcap_vertical_coupler_bbox_size[0],
            endcap_vertical_coupler_bbox_size[1],
            endcap_vertical_coupler_bbox_size[2] * 2,
        )
        endcap_vertical_coupler_total_representative = align(
            endcap_vertical_coupler_total_representative,
            endcap_vertical_coupler,
            Alignment.CENTER,
        )
        endcap_vertical_coupler_total_representative = align(
            endcap_vertical_coupler_total_representative,
            endcap_vertical_coupler,
            Alignment.BOTTOM,
        )

        screw_mount_assembly = create_screw_mount_assembly(
            endcap_vertical_coupler_total_representative,
            screw_size=endcap_vertical_coupler_screw_size,
            screw_length=endcap_vertical_coupler_screw_length,
            screw_direction=(
                Alignment.TOP
                if endcap_top_bottom == Alignment.BOTTOM
                else Alignment.BOTTOM
            ),
            flush_with_top=True,
        )

        endcap_vertical_coupler = screw_mount_assembly.use_as_cutter_on(
            endcap_vertical_coupler
        )

        if endcap_top_bottom == Alignment.TOP:
            npp_name = (
                f"endcap_vertical_coupler_top_{fb.name.lower()}_{side.name.lower()}"
            )
            for (
                screw_npp_name,
                npp,
            ) in screw_mount_assembly.get_named_non_production_part_items():
                retval.add_named_non_production_part(
                    npp, f"{npp_name}_{screw_npp_name}"
                )

        endcap_vertical_couplers = endcap_vertical_couplers.fuse(
            endcap_vertical_coupler
        )

    retval = retval.fuse(endcap_vertical_couplers)

    if endcap_top_bottom == Alignment.TOP:
        center = get_bounding_box_center(cage)
        retval = rotate(180, axis=(1, 0, 0), center=center)(retval)

        retval.additional_data["endcap_is_rotated"] = True

    return retval


def create_x_axis() -> LeaderFollowersCuttersPart:
    """Create the x_axis assembly as a composite part.

    Leader: printable mount-plate assembly (including shields/link/idler bases).
    Non-production parts: axis frame and both motor hardware stacks.
    """

    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020, length_mm=axis_profile_length
    )
    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    top_axis_profile = translate(0, 0, x_axis_profile_pitch)(lower_axis_profile)
    axis_frame = lower_axis_profile.fuse(top_axis_profile)

    rail = create_mgn12h_rail(length_mm=x_axis_rail_length)

    carriages = []
    for i in [-1, 1]:
        carriage = create_mgn12h_carriage()
        carriage = align(carriage, rail, Alignment.CENTER, axes=[0, 1])
        carriage = translate(i * carriage_offset, 0, 0)(carriage)
        carriages.append(carriage)

    for i, carriage in enumerate(carriages):
        rail.add_named_follower(carriage, f"carriage_{i+1}")
    rail_with_carriages = rail

    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.CENTER, axes=[0, 1]
    )
    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.STACK_TOP
    )

    mount_plates = PartCollector()
    mount_shields = PartCollector()
    mount_plate_connectors = PartCollector()

    non_production_parts = []
    non_production_names = []

    non_production_parts.append(
        rail_with_carriages.get_follower_part_by_name("carriage_1")
    )
    non_production_names.append("carriage_1")

    non_production_parts.append(
        rail_with_carriages.get_follower_part_by_name("carriage_2")
    )
    non_production_names.append("carriage_2")

    non_production_parts.append(rail_with_carriages.leader)
    non_production_names.append("rail")

    non_production_parts.append(lower_axis_profile)
    non_production_names.append("lower_axis_profile")
    non_production_parts.append(top_axis_profile)
    non_production_names.append("top_axis_profile")

    axis_holding_counter_flanges = {}

    final_mount_plates_by_side = defaultdict(PartCollector)
    counter_flange_screws_by_side = {}

    motors_fused_by_side = {}

    for side in (Alignment.LEFT, Alignment.RIGHT):

        motor_assembly = create_motor_stack(side, lower_axis_profile, top_axis_profile)

        motor_followers_fused = PartCollector()
        for follower in motor_assembly.followers:
            motor_followers_fused = motor_followers_fused.fuse(follower)

        motors_fused_by_side[side] = motor_followers_fused

        for (
            non_production_part_name,
            non_production_part,
        ) in motor_assembly.get_named_non_production_part_items():
            non_production_parts.append(non_production_part)
            non_production_names.append(
                non_production_part_name + f"_{side.name.lower()}"
            )

        mount_plate_connector = motor_assembly.get_follower_part_by_name(
            "mount_plate_connector"
        )
        mount_plate_connectors = mount_plate_connectors.fuse(mount_plate_connector)

        mount_shield = motor_assembly.get_follower_part_by_name("mount_shield")
        mount_shields = mount_shields.fuse(mount_shield)

        axis_holding_counter_flange = motor_assembly.get_non_production_part_by_name(
            "axis_holding_counter_flange"
        )
        axis_holding_counter_flange_screws = (
            motor_assembly.get_non_production_part_by_name(
                "axis_holding_counter_flange_screws"
            )
        )
        motor_idlers = motor_assembly.get_non_production_part_by_name("idlers")

        mount_plate = motor_assembly.get_follower_part_by_name("mount_plate")

        mount_plates = mount_plates.fuse(mount_plate)
        axis_holding_counter_flanges[
            f"axis_holding_counter_flange_{side.name.lower()}"
        ] = axis_holding_counter_flange

        final_mount_plates_by_side[side] = motors_fused_by_side[side]
        final_mount_plates_by_side[side] = final_mount_plates_by_side[side].fuse(
            mount_shield
        )
        counter_flange_screws_by_side[side] = axis_holding_counter_flange_screws

        non_production_parts.append(motor_idlers)
        non_production_names.append(f"idlers_{side.name.lower()}")

    mount_plate_connectors_size = get_bounding_box_size(mount_plate_connectors)

    mount_plate_link = create_box(
        mount_plate_link_width,
        mount_plate_connector_link_thickness,
        mount_plate_connectors_size[2],
    )

    mount_plate_link = align(mount_plate_link, mount_plate_connectors, Alignment.CENTER)

    mount_plate_link = align(mount_plate_link, mount_plate_connectors, Alignment.BACK)

    bevel_size = (mount_plate_connectors_size[2] - 2 * motor_mount_plate_thickness) / 2
    mount_plate_link_bevels = PartCollector()
    for m in [-1, 1]:

        mount_plate_link_bevel = create_right_triangle(
            bevel_size,
            bevel_size,
            mount_plate_link_width,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, 0, m),
            b_normal=(0, -1, 0),
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel, mount_plate_link, Alignment.CENTER
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel, mount_plate_link, Alignment.STACK_FRONT
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel,
            mount_plate_link,
            Alignment.STACK_TOP if m == 1 else Alignment.STACK_BOTTOM,
            stack_gap=-motor_mount_plate_thickness - bevel_size,
        )

        mount_plate_link_bevels = mount_plate_link_bevels.fuse(mount_plate_link_bevel)

    mount_plate_link = mount_plate_link.fuse(mount_plate_link_bevels)

    mount_plate_link_flange = create_filleted_box(
        mount_plate_link_width,
        link_flange_depth,
        2 * link_flange_thickness,
        fillet_radius=1,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.FRONT],
    )

    mount_plate_link_flange = align(
        mount_plate_link_flange, mount_plate_link, Alignment.CENTER
    )
    mount_plate_link_flange = align(
        mount_plate_link_flange, mount_plate_link, Alignment.STACK_BACK
    )

    link_screw_hole_cutters = PartCollector()
    link_scrws = []
    for i, side in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        link_screw = create_cylinder_screw(link_screw_size, length=link_screw_length)

        link_screw = align(link_screw, mount_plate_link_flange, Alignment.CENTER)
        link_screw = align(link_screw, mount_plate_link_flange, Alignment.TOP)
        link_screw = translate(
            side.sign * mount_plate_link_width / 4,
            0,
            MScrew.from_size(link_screw_size).cylinder_head_height,
        )(link_screw)

        link_scrws.append(link_screw)

        link_screw_hole_cutter = create_cylinder(
            MScrew.from_size(link_screw_size).clearance_hole_normal / 2,
            BIG_THING,
        )
        link_screw_hole_cutter = align(
            link_screw_hole_cutter, link_screw, Alignment.CENTER
        )
        link_screw_hole_cutters = link_screw_hole_cutters.fuse(link_screw_hole_cutter)

    mount_plate_link_flange = mount_plate_link_flange.cut(link_screw_hole_cutters)

    mount_plate_link = mount_plate_link.fuse(mount_plate_link_flange)

    mount_plate_link_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    mount_plate_link_cutter = align(
        mount_plate_link_cutter, axis_frame, Alignment.CENTER
    )

    mount_plate_link_cutter_center = get_bounding_box_center(mount_plate_link_cutter)
    mount_plate_link_cutters = cut_in_two(
        mount_plate_link_cutter,
        cut_point=mount_plate_link_cutter_center,
        cut_normal=(0, 0, 1),
    )

    for i, side in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        current_mount_plate_link = mount_plate_link.cut(mount_plate_link_cutters[i])
        final_mount_plates_by_side[side] = final_mount_plates_by_side[side].fuse(
            current_mount_plate_link
        )

    mount_plates = mount_plates.fuse(mount_plate_link)

    retval = LeaderFollowersCuttersPart(
        leader=mount_plates,
        non_production_parts=non_production_parts,
        non_production_names=non_production_names,
    )

    for i, link_screw in enumerate(link_scrws):
        retval.add_named_non_production_part(
            link_screw,
            f"link_screw_{i+1}",
        )

    _logger.info(f"counter_flange_screws_by_side: {counter_flange_screws_by_side}")
    for side in (Alignment.LEFT, Alignment.RIGHT):
        for i, screw in enumerate(counter_flange_screws_by_side[side]):
            retval.add_named_non_production_part(
                screw,
                f"axis_holding_counter_flange_screw_{i+1}_{side.name.lower()}",
            )

    for name, part in axis_holding_counter_flanges.items():
        retval.add_named_follower(part, name)

    for side in (Alignment.LEFT, Alignment.RIGHT):
        retval.add_named_follower(
            final_mount_plates_by_side[side],
            f"mount_plate_{side.name.lower()}",
        )

    for side in (Alignment.LEFT, Alignment.RIGHT):

        profile_to_align_to = (
            lower_axis_profile if side == Alignment.LEFT else top_axis_profile
        )

        top_bottom_string = "lower" if side == Alignment.LEFT else "top"

        endstop_holder = create_endstop_holder()

        endstop_holder = rotate(-90, axis=(0, 1, 0))(endstop_holder)

        endstop_holder = rotate(-side.sign * 90)(endstop_holder)

        endstop_holder = align(endstop_holder, profile_to_align_to, Alignment.CENTER)
        endstop_holder = align(endstop_holder, profile_to_align_to, side)

        if side == Alignment.RIGHT:
            endstop_board = endstop_holder.get_non_production_part_by_name("board")

            board_align_translation = align_translation(
                endstop_board,
                profile_to_align_to,
                Alignment.STACK_FRONT,
                stack_gap=endstop_holder_stack_gap,
            )
            endstop_holder = board_align_translation(endstop_holder)
            endstop_board = None  # this is no logner valid
        else:
            endstop_holder = align(
                endstop_holder,
                profile_to_align_to,
                Alignment.STACK_FRONT,
                stack_gap=endstop_holder_stack_gap,
            )

        tongue = endstop_holder.get_non_production_part_by_name("tongue")

        tongue_align_translation = align_translation(
            tongue,
            profile_to_align_to,
            Alignment.BOTTOM,
        )

        endstop_holder = tongue_align_translation(endstop_holder)

        endstop_holder = translate(
            -side.sign * endstop_holder_inset_from_end, 0, endstop_holder_z_offset
        )(endstop_holder)

        endstop_holder_mount_plate = create_box(
            endstop_holder_mount_plate_width,
            endstop_holder_mount_plate_length,
            endstop_holder_mount_plate_thickness,
        )

        endstop_holder_mount_plate = align(
            endstop_holder_mount_plate, endstop_holder, Alignment.CENTER
        )
        endstop_holder_mount_plate = align(
            endstop_holder_mount_plate, endstop_holder, Alignment.STACK_BACK
        )

        endstop_holder_mount_plate = align(
            endstop_holder_mount_plate, endstop_holder, side
        )

        endstop_holder_mount_plate = align(
            endstop_holder_mount_plate, profile_to_align_to, Alignment.STACK_TOP
        )

        endstop_holder_mount_screw_drill_diameter = MScrew.from_size(
            endstop_holder_mount_screw_size
        ).clearance_hole_normal

        endstop_holder_mount_screw_cutter = create_cylinder(
            endstop_holder_mount_screw_drill_diameter / 2, BIG_THING
        )
        endstop_holder_mount_screw_cutter = align(
            endstop_holder_mount_screw_cutter,
            endstop_holder_mount_plate,
            Alignment.CENTER,
        )
        endstop_holder_mount_screw_cutter = align(
            endstop_holder_mount_screw_cutter,
            profile_to_align_to,
            Alignment.CENTER,
            axes=[1],
        )

        endstop_holder_mount_plate = endstop_holder_mount_plate.cut(
            endstop_holder_mount_screw_cutter
        )

        endstop_holder_mount_plate_enhancer = create_right_triangle(
            endstop_holder_mount_plate_length / 3,
            endstop_holder_mount_plate_length / 3,
            endstop_holder_mount_plate_thickness / 4,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, -1, 0),
            b_normal=(0, 0, 1),
        )

        endstop_holder_mount_plate_enhancer = align(
            endstop_holder_mount_plate_enhancer,
            endstop_holder_mount_plate,
            Alignment.CENTER,
        )
        endstop_holder_mount_plate_enhancer = align(
            endstop_holder_mount_plate_enhancer,
            endstop_holder_mount_plate,
            Alignment.FRONT,
        )

        endstop_holder_mount_plate_enhancer = align(
            endstop_holder_mount_plate_enhancer, endstop_holder_mount_plate, side
        )
        endstop_holder_mount_plate_enhancer = align(
            endstop_holder_mount_plate_enhancer,
            endstop_holder_mount_plate,
            Alignment.STACK_TOP,
        )

        endstop_holder_mount_plate = endstop_holder_mount_plate.fuse(
            endstop_holder_mount_plate_enhancer
        )

        endstop_holder = endstop_holder.fuse(endstop_holder_mount_plate)

        retval.add_named_non_production_part(
            endstop_holder.get_non_production_part_by_name("board"),
            f"endstop_board_{side.name.lower()}",
        )

        groove_holder = create_pyramid_stump(
            endstop_holder_mount_plate_width,
            endstop_holder_mount_plate_width,
            endstop_holder_groove_holder_bottom_width,
            endstop_holder_groove_holder_top_width,
            endstop_holder_groove_holder_height,
        )

        groove_holder = align(
            groove_holder,
            endstop_holder_mount_screw_cutter,
            Alignment.CENTER,
        )
        groove_holder = align(
            groove_holder, endstop_holder_mount_plate, Alignment.STACK_BOTTOM
        )

        groove_holder_hole_cutter = create_cylinder(
            MScrew.from_size(endstop_holder_mount_screw_size).core_hole / 2 - 0.1,
            BIG_THING,
        )
        groove_holder_hole_cutter = align(
            groove_holder_hole_cutter,
            endstop_holder_mount_screw_cutter,
            Alignment.CENTER,
        )
        groove_holder = groove_holder.cut(groove_holder_hole_cutter)

        groove_holder_larger_hole_cutter = align(
            endstop_holder_mount_screw_cutter,
            groove_holder,
            Alignment.STACK_TOP,
            stack_gap=endstop_holder_groove_holder_height / 3,
        )
        groove_holder = groove_holder.cut(groove_holder_larger_hole_cutter)

        slit_cutter = create_box(
            BIG_THING, endstop_holder_groove_holder_slit, BIG_THING
        )
        slit_cutter = align(slit_cutter, groove_holder, Alignment.CENTER)
        groove_holder = groove_holder.cut(slit_cutter)

        endstop_holder = endstop_holder.fuse(groove_holder)

        retval.add_named_follower(
            endstop_holder.leader, f"endstop_holder_{side.name.lower()}"
        )

        for endcap_side in (Alignment.LEFT, Alignment.RIGHT):

            with_tensioner = endcap_side == Alignment.RIGHT

            endcap_top_bottom = (
                Alignment.BOTTOM if side == Alignment.LEFT else Alignment.TOP
            )

            endcap_side_str = endcap_side.name.lower()

            endcap = create_idler_endcap(
                profile_to_align_to,
                with_tensioner=with_tensioner,
                side=endcap_side,
                endcap_top_bottom=endcap_top_bottom,
            )

            idler_name = (
                f"x_axis_idler_endcap_{top_bottom_string}_{endcap_side_str}_idler"
            )
            retval.add_named_non_production_part(
                endcap.get_follower_part_by_name("idler"),
                idler_name,
            )

            if with_tensioner:
                cage_name = (
                    f"x_axis_idler_endcap_{top_bottom_string}_{endcap_side_str}_cage"
                )
                retval.add_named_follower(
                    endcap.get_follower_part_by_name("endcap_idler_cage"),
                    cage_name,
                )

            else:
                cage_name = None

            endcap_name = f"x_axis_idler_endcap_{top_bottom_string}_{endcap_side_str}"
            retval.add_named_follower(
                endcap.leader,
                endcap_name,
            )

            if endcap.additional_data.get("endcap_is_rotated", False):
                part_names = [idler_name, endcap_name]
                if cage_name is not None:
                    part_names.append(cage_name)

                for name in part_names:
                    retval.additional_data[name] = {"is_rotated": True}

            current_additional_data = retval.additional_data.get(cage_name, {})

            current_additional_data.update(
                {
                    "prod_rotation_angle": -90 * endcap_side.sign * side.sign,
                    "prod_rotation_axis": (0, 1, 0),
                }
            )
            retval.additional_data[cage_name] = current_additional_data

            for (
                npp_name_in_endcap,
                endcap_npp,
            ) in endcap.get_named_non_production_part_items():
                full_npp_name = f"{endcap_name}_{npp_name_in_endcap}"
                retval.add_named_non_production_part(endcap_npp, full_npp_name)

    return retval


def create_rail_drill_jig():

    rail = create_mgn12h_rail(length_mm=x_axis_rail_length)

    jig = create_box(axis_profile_length, jig_width / 2, jig_thickness)
    jig_ear = create_right_triangle(
        jig_thickness,
        jig_thickness,
        axis_profile_length,
        extrusion_direction=(1, 0, 0),
        a_normal=((0, -1, 0)),
        b_normal=(0, 0, 1),
    )
    jig_ear = align(jig_ear, jig, Alignment.CENTER)
    jig_ear = align(jig_ear, jig, Alignment.STACK_BACK)

    jig = jig.fuse(jig_ear)
    jig_cutter = create_box(axis_profile_length, BIG_THING, BIG_THING)
    jig_cutter = align(jig_cutter, jig, Alignment.CENTER)
    jig_cutter = align(jig_cutter, jig, Alignment.STACK_BACK, stack_gap=-2)
    jig = jig.cut(jig_cutter)

    jig_mirrored = mirror(normal=(0, 1, 0), point=(0, 0, 0))(jig)
    jig = jig.fuse(jig_mirrored)

    jig = align(jig, rail, Alignment.CENTER)
    jig = align(jig, rail, Alignment.BOTTOM)

    for cutter in rail.cutters:
        current_drill = create_cylinder(
            MScrew.from_size(rail_mount_screw_size).clearance_hole_close / 2,
            jig_thickness + 5,
        )
        current_drill = align(current_drill, cutter, Alignment.CENTER)
        current_drill = align(current_drill, jig, Alignment.CENTER, axes=[2])

        jig = jig.cut(current_drill)

    return jig

    # parts.add(clamp.leader, "belt_clamp_base", flip=False)
    # parts.add(clamp.get_follower_part_by_name("clamp"), "belt_clamp", flip=True)


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    frame = create_printer_frame()

    parts.add(
        frame,
        "printer_frame",
        flip=False,
        skip_in_production=True,
    )

    x_axis = create_x_axis()

    _logger.info(f"x_axis is: {x_axis}")

    x_axis = align(x_axis, frame, Alignment.CENTER)
    x_axis = align(x_axis, frame, Alignment.STACK_TOP, stack_gap=100)

    already_added_names = set()
    for name, npp in x_axis.get_named_non_production_part_items():        
        if name in already_added_names:
            _logger.warning(
                f"Duplicate non-production part name {name} in x_axis, skipping adding it to parts list"
            )
            continue
        already_added_names.add(name)
        parts.add(
            npp,
            f"x_axis_{name}",
            flip=False,
            skip_in_production=True,
        )


    for name, follower in x_axis.get_named_follower_items():

        if name in already_added_names:
            _logger.warning(
                f"Duplicate follower name {name} in x_axis, skipping adding it to parts list"
            )
            continue
        already_added_names.add(name)

        is_rotated = x_axis.additional_data.get(name, {}).get("is_rotated", False)

        prod_rotation_angle_from_data = x_axis.additional_data.get(name, {}).get(
            "prod_rotation_angle", None
        )
        prod_rotation_axis_from_data = x_axis.additional_data.get(name, {}).get(
            "prod_rotation_axis", None
        )

        parts.add(
            follower,
            f"x_axis_{name}",
            flip=is_rotated,  # flip if the part is rotated
            skip_in_production=False,
            prod_rotation_angle=prod_rotation_angle_from_data,
            prod_rotation_axis=prod_rotation_axis_from_data,
        )

    lower_axis_profile = x_axis.get_non_production_part_by_name("lower_axis_profile")

    tool_head_mount, _carriage, _tool_head = create_tool_head_mount(lower_axis_profile)

    carriage_1 = x_axis.get_non_production_part_by_name("carriage_1")

    tool_head_mount = align(
        tool_head_mount,
        carriage_1,
        Alignment.CENTER,
    )
    tool_head_mount = align(
        tool_head_mount,
        carriage_1,
        Alignment.BACK,
    )
    tool_head_mount = align(
        tool_head_mount,
        carriage_1,
        Alignment.TOP,
    )
    tool_head_mount = translate(0, 0, tool_head_mount_carriage_mount_plate_thickness)(
        tool_head_mount
    )

    parts.add(
        tool_head_mount,
        "x_axis_tool_head_mount",
        flip=False,
        skip_in_production=True,  # was False,
        prod_rotation_angle=180,
        prod_rotation_axis=(1, 0, 0),
        color=(0.7, 0.7, 0.2),
    )

    parts.add(
        tool_head_mount.get_follower_part_by_name("belt_clamp_base"),
        "x_axis_tool_head_mount_clamp",
        flip=False,
        skip_in_production=True,  # was False,
        prod_rotation_angle=90,
        prod_rotation_axis=(1, 0, 0),
        color=(0.7, 0.6, 0.5),
    )

    for name, npp in frame.get_named_non_production_part_items():
        parts.add(
            npp,
            f"printer_frame_{name}",
            flip=False,
            skip_in_production=True,
        )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=4,
        export_individual_parts=False,
    )

    _logger.info("x_axis created successfully!")


if __name__ == "__main__":
    main()
