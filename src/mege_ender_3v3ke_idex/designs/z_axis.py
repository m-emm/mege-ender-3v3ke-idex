"""
Z Axis

Usage:
    cd <project_root> && ./run.sh path/to/z_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/z_axis.py
"""

import copy
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_carriage,
    create_mgn12h_rail,
)
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


_logger = logging.getLogger(__name__)

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "1",
        "external_perimeter_speed": "75",
        "fan_max_speed": "25",
        "fan_min_speed": "10",
        "outer_wall_speed": "75",
        "sparse_infill_density": "75%",
        "support_critical_regions_only": "1",
        "support_interface_spacing": "0.8",
        "support_on_build_plate_only": "1",
        "support_threshold_angle": "30",
        "support_top_z_distance": "0.3",
        "wall_loops": "3",
    }
)

z_axis_threaded_rod_diameter = 8
z_axis_threaded_rod_length = 500

z_axis_threaded_rod_profile_distance = 22
z_axis_thraded_rod_z_offset = 90


z_axis_pillow_block_bearing_z_offset = 15

z_axis_guide_rod_length = 600
z_axis_guide_rod_diameter = 8

z_axis_profile_length = 700

z_axis_guide_rod_threaded_rod_distance = 18
z_axis_guide_rod_profile_distance = 75

z_axis_carriage_height = 60
z_axis_carriage_width = 45
z_axis_carriage_front_depth = 22
z_axis_carriage_back_depth = 40
z_axis_carriage_back_height = 12
z_axis_carriage_fillet_radius = 4
z_axis_carriage_mount_screw_size = "M3"
z_axis_carriage_bearing_inset = 5
z_axis_carriage_threaded_rod_clearance = 0.3
z_axis_carriage_profile_clearance = 2

igus_drylin_bearing_inner_diameter = 8
igus_drylin_bearing_outer_diameter = 16
igus_drylin_bearing_length = 25

pillow_block_bearing_base_thickness = 5.1
pillow_block_bearing_base_width = 13.1
pillow_block_bearing_base_overall_length = 55

pillow_block_bearing_base_gap_length = 24.7
pillow_block_bottom_base_bridge_width = 3.5

pillow_block_bearing_mount_hole_diameter = 4.6
pillow_block_bearing_mount_hole_center_distance = 41.5
pillow_block_bearing_cage_diameter = 30
pillow_block_bearing_cage_thickness = 9.6
pillow_block_bearing_cage_rim = 2

pillow_block_bearing_rod_holder_outer_diameter = 12
pillow_block_bearing_rod_holder_inner_diameter = 8.03
pillow_block_bearing_rod_holder_length = 11


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


axial_ball_bearing_8_x_19_thickness = 7
axial_ball_bearing_8_x_19_outer_diameter = 19
axial_ball_bearing_8_x_19_inner_diameter = 8.2
axial_ball_bearing_8_x_19_disc_thickness = 2.15
axial_ball_bearing_8_x_19_ball_diameter = 3.17
axial_ball_bearing_8_x_19_ball_count = 6
axial_ball_bearing_8_x_19_ball_holder_disc_thickness = 1.9
axial_ball_bearing_8_x_19_ball_holder_disc_outer_diameter = 17.45
axial_ball_bearing_8_x_19_ball_holder_disc_inner_diameter = 9.6


axial_bearing_stopper_outer_diameter = 24
axial_bearing_stopper_inner_diameter = 16
axial_bearing_stopper_thickness = 4


axial_rod_clamp_outer_diameter = 32
axial_rod_clamp_inner_diameter = 8.2
axial_rod_clamp_thickness = 10
axial_rod_clamp_gap = 1.2
axial_rod_clamp_screw_size = "M3"
axial_rod_clamp_screw_length = 18
axial_rod_clamp_nut_clearance = 0.15
axial_rod_clamp_cylinder_head_cutter_clearance = 0.25
axial_rod_clamp_outer_diameter_cutting_depth = 9
axial_rod_clamp_screw_hole_distance_from_center = 10


def create_axial_bearing_stopper():
    stopper = create_ring(
        axial_bearing_stopper_outer_diameter / 2,
        axial_bearing_stopper_inner_diameter / 2,
        axial_bearing_stopper_thickness,
    )
    return stopper


def create_axial_rod_clamp():

    clamp = create_ring(
        axial_rod_clamp_outer_diameter / 2,
        axial_rod_clamp_inner_diameter / 2,
        axial_rod_clamp_thickness,
    )

    screw_cutter_diameter = MScrew.from_size(
        axial_rod_clamp_screw_size
    ).clearance_hole_normal
    screw_cutters = []
    nut_cutters = []
    cylinder_head_cutters = []
    for i in [-1, 1]:

        screw_cutter = create_cylinder(screw_cutter_diameter / 2, BIG_THING)
        screw_cutter = rotate(90, axis=(1, 0, 0))(screw_cutter)
        screw_cutter = align(screw_cutter, clamp, Alignment.CENTER)
        screw_cutter = translate(
            i * axial_rod_clamp_screw_hole_distance_from_center, 0, 0
        )(screw_cutter)

        screw_cutters.append(screw_cutter)

        nut_cutter = create_nut(
            axial_rod_clamp_screw_size,
            no_hole=True,
            height=axial_rod_clamp_outer_diameter / 2,
            slack=axial_rod_clamp_nut_clearance,
        )

        nut_cutter = rotate(90, axis=(1, 0, 0))(nut_cutter)

        nut_cutter = align(nut_cutter, screw_cutter, Alignment.CENTER)

        nut_cutters.append(nut_cutter)

        cylinder_head_cutter = create_cylinder(
            MScrew.from_size(axial_rod_clamp_screw_size).cylinder_head_diameter / 2
            + axial_rod_clamp_cylinder_head_cutter_clearance,
            axial_rod_clamp_outer_diameter / 2,
        )
        cylinder_head_cutter = rotate(90, axis=(1, 0, 0))(cylinder_head_cutter)
        cylinder_head_cutter = align(
            cylinder_head_cutter, screw_cutter, Alignment.CENTER
        )
        cylinder_head_cutters.append(cylinder_head_cutter)

    for screw_cutter in screw_cutters:
        clamp = clamp.cut(screw_cutter)

    for nut_cutter in nut_cutters:
        nut_cutter = align(
            nut_cutter,
            clamp,
            Alignment.STACK_BACK,
            stack_gap=-axial_rod_clamp_outer_diameter_cutting_depth,
        )
        clamp = clamp.cut(nut_cutter)

    srews = []

    for cylinder_head_cutter in cylinder_head_cutters:
        cylinder_head_cutter = align(
            cylinder_head_cutter,
            clamp,
            Alignment.STACK_FRONT,
            stack_gap=-axial_rod_clamp_outer_diameter_cutting_depth,
        )
        clamp = clamp.cut(cylinder_head_cutter)

        screw = create_cylinder_screw(
            size=axial_rod_clamp_screw_size, length=axial_rod_clamp_screw_length
        )
        screw = rotate(90, axis=(1, 0, 0))(screw)

        cylinder_head_height = MScrew.from_size(
            axial_rod_clamp_screw_size
        ).cylinder_head_height

        screw = align(screw, cylinder_head_cutter, Alignment.CENTER)
        screw = align(
            screw,
            cylinder_head_cutter,
            Alignment.STACK_BACK,
            stack_gap=-cylinder_head_height - 0.2,
        )
        srews.append(screw)

    clamp_parts = cut_in_two(
        clamp, cut_normal=((0, 1, 0)), cut_thickness=axial_rod_clamp_gap
    )

    retval = LeaderFollowersCuttersPart(clamp)

    for i, clamp_part in enumerate(clamp_parts):
        retval.add_named_follower(clamp_part, f"clamp_part_{i}")

    for i, screw in enumerate(srews):
        retval.add_named_non_production_part(screw, f"clamp_screw_{i}")

    return retval


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


def create_igus_drylin_bearing(cutter_clearance=0.1, cutter_extra_length=2):
    bearing = create_ring(
        igus_drylin_bearing_outer_diameter / 2,
        igus_drylin_bearing_inner_diameter / 2,
        igus_drylin_bearing_length,
    )
    cutter = create_cylinder(
        (igus_drylin_bearing_outer_diameter / 2) + cutter_clearance,
        igus_drylin_bearing_length + cutter_extra_length,
    )
    cutter = align(cutter, bearing, Alignment.CENTER)

    retval = LeaderFollowersCuttersPart(bearing, cutters=[cutter])

    return retval


def create_pillow_block_bearing():

    bearing = create_608z_bearing()

    cage = create_ring(
        pillow_block_bearing_cage_diameter / 2,
        (pillow_block_bearing_cage_diameter / 2) - pillow_block_bearing_cage_rim,
        pillow_block_bearing_cage_thickness,
    )

    cage = align(cage, bearing, Alignment.CENTER)

    cage_filler = create_ring(
        pillow_block_bearing_cage_diameter / 2 - pillow_block_bearing_cage_rim,
        bb_608z_outer_diameter / 2,
        bb_608z_height,
    )

    cage_filler = align(cage_filler, bearing, Alignment.CENTER)

    base = create_box(
        pillow_block_bearing_base_overall_length,
        pillow_block_bearing_base_thickness,
        pillow_block_bearing_base_width,
    )

    base_gap_cutter = create_box(
        pillow_block_bearing_base_gap_length, BIG_THING, BIG_THING
    )
    base_gap_cutter = align(base_gap_cutter, base, Alignment.CENTER)
    base = base.cut(base_gap_cutter)

    base_bridge = create_box(
        pillow_block_bearing_base_gap_length,
        pillow_block_bearing_base_thickness,
        pillow_block_bottom_base_bridge_width,
    )
    base_bridge = align(base_bridge, base, Alignment.CENTER)
    base_bridge = align(base_bridge, base, Alignment.FRONT)
    base = base.fuse(base_bridge)

    base = align(base, bearing, Alignment.CENTER)
    base = align(base, cage, Alignment.FRONT)

    base_sides = PartCollector()

    mount_hole_cutters = []

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        # base_side = create_box(
        #     pillow_block_bearing_cage_rim,
        #     pillow_block_bearing_cage_diameter / 2,
        #     pillow_block_bearing_cage_thickness,
        # )

        base_side = create_pyramid_stump(
            pillow_block_bearing_cage_rim,
            pillow_block_bearing_cage_rim,
            pillow_block_bearing_base_width,
            pillow_block_bearing_cage_thickness,
            pillow_block_bearing_cage_diameter / 2,
        )
        base_side = rotate(-90, axis=(1, 0, 0))(base_side)

        base_side = align(base_side, cage, Alignment.CENTER)
        base_side = align(base_side, base, Alignment.FRONT)
        base_side = align(base_side, cage, lr)
        base_sides = base_sides.fuse(base_side)

        mount_hole_cutter = create_cylinder(
            pillow_block_bearing_mount_hole_diameter / 2, BIG_THING
        )
        mount_hole_cutter = rotate(90, axis=(1, 0, 0))(mount_hole_cutter)

        mount_hole_cutter = align(mount_hole_cutter, base, Alignment.CENTER)
        mount_hole_cutter = translate(
            lr.sign * pillow_block_bearing_mount_hole_center_distance / 2, 0, 0
        )(mount_hole_cutter)
        mount_hole_cutters.append(mount_hole_cutter)

    for mount_hole_cutter in mount_hole_cutters:
        base = base.cut(mount_hole_cutter)

    base = base.fuse(base_sides)

    rod_holder = create_ring(
        pillow_block_bearing_rod_holder_outer_diameter / 2,
        pillow_block_bearing_rod_holder_inner_diameter / 2,
        pillow_block_bearing_rod_holder_length,
    )
    rod_holder = align(rod_holder, bearing, Alignment.CENTER)
    rod_holder = align(rod_holder, bearing, Alignment.BOTTOM)
    bearing = bearing.fuse(rod_holder)

    retval = LeaderFollowersCuttersPart(bearing)
    retval.add_named_non_production_part(cage, "cage")
    retval.add_named_non_production_part(cage_filler, "cage_filler")
    retval.add_named_non_production_part(base, "base")
    for i, mount_hole_cutter in enumerate(mount_hole_cutters):
        retval.add_named_cutter(mount_hole_cutter, f"mount_hole_cutter_{i}")

    retval = rotate(-90, axis=(1, 0, 0))(retval)

    return retval


def create_axial_ball_bearing_8_x_19():

    bearing = PartCollector()
    for i in [0, 1]:
        disc = create_ring(
            axial_ball_bearing_8_x_19_outer_diameter / 2,
            axial_ball_bearing_8_x_19_inner_diameter / 2,
            axial_ball_bearing_8_x_19_disc_thickness,
        )
        disc = translate(
            0,
            0,
            i
            * (
                axial_ball_bearing_8_x_19_thickness
                - axial_ball_bearing_8_x_19_disc_thickness
            ),
        )(disc)
        bearing = bearing.fuse(disc)

    for i in range(axial_ball_bearing_8_x_19_ball_count):
        angle = (360 / axial_ball_bearing_8_x_19_ball_count) * i
        ball = create_sphere(axial_ball_bearing_8_x_19_ball_diameter / 2)
        ball_position_radius = (
            axial_ball_bearing_8_x_19_inner_diameter
            + axial_ball_bearing_8_x_19_outer_diameter
        ) / 4
        ball = translate(
            ball_position_radius * math.cos(math.radians(angle)),
            ball_position_radius * math.sin(math.radians(angle)),
            axial_ball_bearing_8_x_19_thickness / 2,
        )(ball)
        bearing = bearing.fuse(ball)

    ball_holder_disc = create_ring(
        axial_ball_bearing_8_x_19_ball_holder_disc_outer_diameter / 2,
        axial_ball_bearing_8_x_19_ball_holder_disc_inner_diameter / 2,
        axial_ball_bearing_8_x_19_ball_holder_disc_thickness,
    )
    ball_holder_disc = align(ball_holder_disc, bearing, Alignment.CENTER)

    bearing = bearing.fuse(ball_holder_disc)
    return bearing


def create_creality_threaded_rod_nut(guide_cutter_clearance=0.1):
    base_thickness = 3.5
    base_width = 12.5
    base_cut_radius = 15
    base_length = 23.8
    rod_guide_diameter = 9.97
    rod_guide_height = 10.55
    rod_guide_bottom_overstand = 2
    mount_hole_center_center_distance = 16.5
    mount_screw_size = "M3"

    base = create_box(base_length, base_width, base_thickness)

    mount_hole_drill_diaameter = MScrew.from_size(mount_screw_size).core_hole
    external_mount_hole_drill_diameter = MScrew.from_size(
        mount_screw_size
    ).clearance_hole_normal

    base_cutter = create_box(BIG_THING, BIG_THING, 2 * base_thickness)
    external_mount_hole_drills = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        cutter_reducer = create_cylinder(base_cut_radius, 2 * base_thickness)
        cutter_reducer = align(cutter_reducer, base_cutter, Alignment.CENTER)
        cutter_reducer = align(cutter_reducer, base_cutter, lr)

        current_cutter_lfc = LeaderFollowersCuttersPart(cutter_reducer)
        current_cutter = base_cutter.cut(cutter_reducer)
        current_cutter_lfc.add_named_cutter(current_cutter, "base_cutter")
        current_cutter_lfc = align(current_cutter_lfc, base, Alignment.CENTER)
        current_cutter_lfc = align(current_cutter_lfc, base, lr)

        base = current_cutter_lfc.use_as_cutter_on(base)

        mount_hole_drill_cutter = create_cylinder(
            mount_hole_drill_diaameter / 2, 2 * base_thickness
        )
        mount_hole_drill_cutter = align(mount_hole_drill_cutter, base, Alignment.CENTER)
        mount_hole_drill_cutter = translate(
            lr.sign * mount_hole_center_center_distance / 2, 0, 0
        )(mount_hole_drill_cutter)

        external_mount_hole_drill = create_cylinder(
            external_mount_hole_drill_diameter / 2, BIG_THING
        )
        external_mount_hole_drill = align(
            external_mount_hole_drill, mount_hole_drill_cutter, Alignment.CENTER
        )
        external_mount_hole_drill = external_mount_hole_drill.cut(base)
        external_mount_hole_drills.append(external_mount_hole_drill)

        base = base.cut(mount_hole_drill_cutter)

    rod_guide = create_cylinder(rod_guide_diameter / 2, rod_guide_height)

    rod_guide = align(rod_guide, base, Alignment.CENTER)
    rod_guide = align(rod_guide, base, Alignment.BOTTOM)
    rod_guide = translate(0, 0, -rod_guide_bottom_overstand)(rod_guide)

    whole_nut = base.fuse(rod_guide)
    rod_cutter = create_cylinder(z_axis_threaded_rod_diameter / 2, BIG_THING)
    rod_cutter = align(rod_cutter, rod_guide, Alignment.CENTER)
    whole_nut = whole_nut.cut(rod_cutter)

    retval = LeaderFollowersCuttersPart(whole_nut)
    retval.add_named_non_production_part(base, "raw_base")
    for idx, external_mount_hole_drill in enumerate(external_mount_hole_drills):
        retval.add_named_cutter(
            external_mount_hole_drill, f"external_mount_hole_drill_{idx}"
        )

    rod_guide_cutter = create_cylinder(
        rod_guide_diameter / 2 + guide_cutter_clearance, BIG_THING
    )
    rod_guide_cutter = align(rod_guide_cutter, rod_guide, Alignment.CENTER)
    retval.add_named_cutter(rod_guide_cutter, "rod_guide_cutter")

    return retval


def create_carriage(guide_rod, threaded_rod, profile):
    carriage_front = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_front_depth,
        z_axis_carriage_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )

    carriage_front = align(carriage_front, guide_rod, Alignment.CENTER)
    carriage_front = align(carriage_front, guide_rod, Alignment.BOTTOM)

    bearing = create_igus_drylin_bearing(
        cutter_clearance=0.1, cutter_extra_length=z_axis_carriage_height
    )
    bearing = align(bearing, carriage_front, Alignment.CENTER)
    bearing = align(bearing, guide_rod, Alignment.CENTER, axes=[0, 1])

    carriage_front = bearing.use_as_cutter_on(carriage_front)

    top_bearing = align(bearing, carriage_front, Alignment.TOP)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_carriage_threaded_rod_clearance,
        z_axis_carriage_height + 10,
    )

    threaded_rod_cutter = align(threaded_rod_cutter, carriage_front, Alignment.CENTER)
    threaded_rod_cutter = align(
        threaded_rod_cutter, threaded_rod, Alignment.CENTER, axes=[0, 1]
    )

    carriage_back = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_back_depth + 2 * z_axis_carriage_fillet_radius,
        z_axis_carriage_back_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )

    carriage_back = align(carriage_back, carriage_front, Alignment.CENTER)
    carriage_back = align(carriage_back, carriage_front, Alignment.BOTTOM)
    carriage_back = align(
        carriage_back,
        carriage_front,
        Alignment.STACK_BACK,
        stack_gap=-2 * z_axis_carriage_fillet_radius,
    )

    nut = create_creality_threaded_rod_nut()

    nut = align(nut, threaded_rod, Alignment.CENTER)

    nut_raw_base = nut.get_named_non_production_part("raw_base")
    base_aligner = align_translation(nut_raw_base, carriage_back, Alignment.STACK_TOP)
    nut = base_aligner(nut)




    carriage_back = nut.use_as_cutter_on(carriage_back)
    carriage_back = carriage_back.cut(threaded_rod_cutter)

    

    carriage_body = carriage_front.fuse(carriage_back)

    retval = LeaderFollowersCuttersPart(carriage_body)

    retval.add_named_non_production_part(top_bearing, "top_bearing")
    retval.add_named_non_production_part(nut, "threaded_rod_nut")

    bottom_bearing = align(bearing, carriage_front, Alignment.BOTTOM)
    retval.add_named_non_production_part(bottom_bearing, "bottom_bearing")

    return retval


def create_z_axis():
    """Create the z_axis part."""

    z_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_4040, length_mm=z_axis_profile_length
    )

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)

    guide_rod = align(guide_rod, z_axis_profile, Alignment.CENTER)
    guide_rod = align(guide_rod, z_axis_profile, Alignment.BOTTOM)

    guide_rod = translate(0, -z_axis_guide_rod_profile_distance, 0)(guide_rod)

    threaded_rod = create_cylinder(
        z_axis_threaded_rod_diameter / 2, z_axis_threaded_rod_length
    )

    threaded_rod = align(threaded_rod, guide_rod, Alignment.CENTER)
    threaded_rod = align(threaded_rod, guide_rod, Alignment.BOTTOM)
    threaded_rod = align(
        threaded_rod,
        z_axis_profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_threaded_rod_profile_distance,
    )
    threaded_rod = translate(0, 0, z_axis_thraded_rod_z_offset)(threaded_rod)

    retval = LeaderFollowersCuttersPart(z_axis_profile)

    retval.add_named_non_production_part(guide_rod, "guide_rod")
    retval.add_named_non_production_part(threaded_rod, "threaded_rod")

    pillow_block_bearing = create_pillow_block_bearing()

    pillow_block_bearing = pillow_block_bearing.prefixed_copy("pillow_block_bearing")

    pillow_block_bearing = rotate(-90, axis=(1, 0, 0))(pillow_block_bearing)

    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.CENTER)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.BOTTOM)
    pillow_block_bearing = translate(0, 0, z_axis_pillow_block_bearing_z_offset)(
        pillow_block_bearing
    )

    retval.add_named_non_production_part(
        pillow_block_bearing.leader, "pillow_block_bearing_body"
    )

    for name, part in pillow_block_bearing.get_named_non_production_part_items():

        retval.add_named_non_production_part(part, name)

    axial_bearing_stopper = create_axial_bearing_stopper()

    axial_bearing_stopper = align(axial_bearing_stopper, threaded_rod, Alignment.CENTER)
    axial_bearing_stopper = align(
        axial_bearing_stopper, pillow_block_bearing, Alignment.STACK_TOP
    )

    retval.add_named_follower(axial_bearing_stopper, "axial_bearing_stopper")

    axial_bearing = create_axial_ball_bearing_8_x_19()

    axial_bearing = align(axial_bearing, threaded_rod, Alignment.CENTER)
    axial_bearing = align(axial_bearing, axial_bearing_stopper, Alignment.STACK_TOP)

    retval.add_named_follower(axial_bearing, "axial_bearing")

    rod_clamp = create_axial_rod_clamp()

    rod_clamp = align(rod_clamp, threaded_rod, Alignment.CENTER)
    rod_clamp = align(rod_clamp, axial_bearing, Alignment.STACK_TOP)

    for name, part in rod_clamp.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    for name, part in rod_clamp.get_named_follower_items():
        retval.add_named_follower(part, name)

    motor = create_nema_composite()

    motor = align(motor, threaded_rod, Alignment.CENTER)

    coupler = motor.get_named_follower("coupler")
    coupler_aligner = align_translation(coupler, threaded_rod, Alignment.STACK_BOTTOM)

    motor = coupler_aligner(motor)

    for name, part in motor.get_named_follower_items():
        retval.add_named_non_production_part(part, name)

    return retval


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import create_printer_frame

    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    z_axis = create_z_axis()

    parts.add(z_axis, "z_axis", flip=False, skip_in_production=True)

    for name, npp in z_axis.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    for name, folllower in z_axis.get_named_follower_items():
        parts.add(folllower, name, flip=False, skip_in_production=False)

    carriage = create_carriage(
        z_axis.get_named_non_production_part("guide_rod"),
        z_axis.get_named_non_production_part("threaded_rod"),
        z_axis,
    )

    carriage = translate(0, 0, 200)(carriage)

    parts.add(carriage, "z_axis_carriage", flip=False, skip_in_production=True)

    for name, npp in carriage.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    # printer_frame = create_printer_frame()

    # parts.add(printer_frame, "printer_frame", flip=False, skip_in_production=True)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("z_axis created successfully!")


if __name__ == "__main__":
    main()
