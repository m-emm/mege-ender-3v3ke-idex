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
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


_logger = logging.getLogger(__name__)

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "0",
        "support_object_first_layer_gap": 0.8,
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


def create_profile_mount_plate(
    num_holes=2, screw_inset=5, profile_mount_width=z_axis_profile_mount_width
):

    plate = create_filleted_box(
        profile_mount_width,
        z_axis_profile_mount_plate_thickness,
        z_axis_profile_mount_plate_height,
        z_axis_profile_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.BOTTOM],
    )

    hole_drill_diameter = MScrew.from_size("M5").clearance_hole_loose

    hole_drills = PartCollector()
    hole_pitch = (
        (z_axis_profile_mount_plate_height - 2 * screw_inset - hole_drill_diameter)
        / (num_holes - 1)
        if num_holes > 1
        else 0
    )
    for i in range(num_holes):

        hole_drill = create_cylinder(hole_drill_diameter / 2, BIG_THING)
        hole_drill = rotate(90, axis=(1, 0, 0))(hole_drill)
        hole_drill = translate(0, 0, i * hole_pitch)(hole_drill)

        hole_drills = hole_drills.fuse(hole_drill)

    hole_drills = align(hole_drills, plate, Alignment.CENTER)
    plate = plate.cut(hole_drills)

    return plate


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

    axial_clamp_parts = cut_in_two(
        clamp, cut_normal=((0, 1, 0)), cut_thickness=axial_rod_clamp_gap
    )

    retval = LeaderFollowersCuttersPart(clamp)

    for i, axial_clamp_part in enumerate(axial_clamp_parts):
        retval.add_named_follower(axial_clamp_part, f"axial_clamp_part_{i}")

    for i, screw in enumerate(srews):
        retval.add_named_non_production_part(screw, f"axial_clamp_screw_{i}")

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


def create_pillow_block_bearing(screw_length=15):

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

    mount_screws = []
    mount_screw_size = "M4"

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

        mount_screw = create_cylinder_screw(size=mount_screw_size, length=screw_length)

        mount_screw = rotate(-90, axis=(1, 0, 0))(mount_screw)
        mount_screw = align(mount_screw, mount_hole_cutter, Alignment.CENTER)
        mount_screw = align(mount_screw, base, Alignment.BACK)
        mount_screw = translate(
            0, MScrew.from_size(mount_screw_size).cylinder_head_height, 0
        )(mount_screw)

        mount_screws.append(mount_screw)

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

    for i, mount_screw in enumerate(mount_screws):
        retval.add_named_non_production_part(mount_screw, f"mount_screw_{i}")

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


def create_creality_threaded_rod_nut(
    threaded_rod_guide_cutter_clearance=0.1, screw_hole_clearence_type="normal"
):
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
    ).get_clearance_hole_diameter(screw_hole_clearence_type)

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
        rod_guide_diameter / 2 + threaded_rod_guide_cutter_clearance, BIG_THING
    )
    rod_guide_cutter = align(rod_guide_cutter, rod_guide, Alignment.CENTER)
    retval.add_named_cutter(rod_guide_cutter, "rod_guide_cutter")

    return retval


def create_top_mount(guide_rod, threaded_rod, profile):

    top_mount_plate = create_filleted_box(
        z_axis_top_mount_width,
        z_axis_top_mount_depth,
        z_axis_top_mount_thickness,
        z_axis_top_mount_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )

    top_mount_plate = align(top_mount_plate, guide_rod, Alignment.CENTER)

    top_mount_plate = align(
        top_mount_plate,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_motor_mount_plate_profile_distance,
    )

    rod_holder = create_filleted_box(
        z_axis_guide_rod_clamp_width,
        z_axis_top_mount_holder_depth,
        z_axis_top_mount_holder_height,
        z_axis_top_mount_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )

    rod_holder = align(rod_holder, top_mount_plate, Alignment.CENTER)
    rod_holder = align(rod_holder, top_mount_plate, Alignment.STACK_TOP)
    rod_holder = align(rod_holder, top_mount_plate, Alignment.FRONT)

    top_mount_plate = top_mount_plate.fuse(rod_holder)

    rod_holder_reinforcement = create_right_triangle(
        z_axis_top_mount_holder_height * z_axis_top_mount_reinforcement_factor,
        z_axis_top_mount_holder_height * z_axis_top_mount_reinforcement_factor,
        z_axis_top_mount_reinforcement_thickness,
        extrusion_direction=(1, 0, 0),
        a_normal=(0, 0, -1),
        b_normal=(0, 1, 0),
    )
    rod_holder_reinforcement = align(
        rod_holder_reinforcement, rod_holder, Alignment.CENTER
    )
    rod_holder_reinforcement = align(
        rod_holder_reinforcement, rod_holder, Alignment.BOTTOM
    )
    rod_holder_reinforcement = align(
        rod_holder_reinforcement, rod_holder, Alignment.STACK_BACK
    )

    top_mount_plate = top_mount_plate.fuse(rod_holder_reinforcement)

    guide_rod_top_aligner = align_translation(top_mount_plate, guide_rod, Alignment.TOP)

    top_mount_plate = guide_rod_top_aligner(top_mount_plate)
    rod_holder = guide_rod_top_aligner(rod_holder)

    top_mount_plate = top_mount_plate.cut(guide_rod)

    rod_holder_representation = create_box(
        z_axis_guide_rod_clamp_width,
        z_axis_top_mount_holder_depth,
        z_axis_top_mount_holder_height - z_axis_top_mount_thickness,
    )

    rod_holder_representation = align(
        rod_holder_representation, rod_holder, Alignment.CENTER
    )
    rod_holder_representation = align(
        rod_holder_representation, rod_holder, Alignment.TOP
    )

    screw_assembly = create_four_screws_mount_assembly(
        rod_holder_representation,
        screw_size=z_axis_top_mount_screw_size,
        screw_length=z_axis_top_mount_screw_length,
        screw_direction=Alignment.FRONT,
        flush_with_top=True,
        length_inset=z_axis_top_mount_screw_inset,
        width_inset=z_axis_top_mount_screw_inset,
        cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
        clearance_type=z_axis_default_clearance_hole_type,
        nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
    )

    top_mount_plate = screw_assembly.use_as_cutter_on(top_mount_plate)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_top_mount_threaded_rod_clearance,
        BIG_THING,
    )
    threaded_rod_cutter = align(threaded_rod_cutter, threaded_rod, Alignment.CENTER)
    threaded_rod_cutter = align(
        threaded_rod_cutter, top_mount_plate, Alignment.CENTER, axes=[2]
    )

    top_mount_plate = top_mount_plate.cut(threaded_rod_cutter)

    top_mount_profile_mount_plate = create_profile_mount_plate(
        profile_mount_width=z_axis_top_mount_profile_mount_width
    )

    top_mount_profile_mount_plate = align(
        top_mount_profile_mount_plate, top_mount_plate, Alignment.CENTER
    )
    top_mount_profile_mount_plate = align(
        top_mount_profile_mount_plate, top_mount_plate, Alignment.BACK
    )
    top_mount_profile_mount_plate = align(
        top_mount_profile_mount_plate, top_mount_plate, Alignment.BOTTOM
    )
    top_mount_profile_mount_plate = translate(0, 0, z_axis_top_mount_thickness)(
        top_mount_profile_mount_plate
    )

    top_mount_plate = top_mount_plate.fuse(top_mount_profile_mount_plate)

    top_mount_reinforcements = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        top_mount_reinforcement = create_right_triangle(
            z_axis_profile_mount_plate_height * z_axis_top_mount_reinforcement_factor,
            z_axis_profile_mount_plate_height * z_axis_top_mount_reinforcement_factor,
            z_axis_top_mount_reinforcement_thickness,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, 0, -1),
            b_normal=(0, -1, 0),
        )

        top_mount_reinforcement = align(
            top_mount_reinforcement, top_mount_profile_mount_plate, Alignment.CENTER
        )
        top_mount_reinforcement = align(
            top_mount_reinforcement, top_mount_profile_mount_plate, Alignment.BACK
        )
        top_mount_reinforcement = align(
            top_mount_reinforcement, top_mount_profile_mount_plate, Alignment.BOTTOM
        )
        top_mount_reinforcement = align(
            top_mount_reinforcement, top_mount_profile_mount_plate, lr
        )

        top_mount_reinforcements = top_mount_reinforcements.fuse(
            top_mount_reinforcement
        )

    top_mount_plate = top_mount_plate.fuse(top_mount_reinforcements)

    rod_center = get_bounding_box_center(guide_rod)
    rod_holder_center = get_bounding_box_center(rod_holder)
    cut_point = (rod_holder_center[0], rod_center[1], rod_holder_center[2])

    top_mount_back, top_mount_clamp = cut_in_two(
        top_mount_plate,
        cut_normal=(0, 1, 0),
        cut_point=cut_point,
        cut_thickness=z_axis_rod_clamp_gap,
    )

    retval = LeaderFollowersCuttersPart(top_mount_back)
    retval.add_named_follower(top_mount_clamp, "top_mount_clamp")
    for name, part in screw_assembly.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"top_mount_{name}")

    return retval


def create_carriage(guide_rod, threaded_rod, profile):
    carriage_front = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_front_depth,
        z_axis_carriage_front_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    carriage_front = align(carriage_front, guide_rod, Alignment.CENTER)
    carriage_front = align(carriage_front, guide_rod, Alignment.BOTTOM)

    bearing = create_igus_drylin_bearing(
        cutter_clearance=0.1, cutter_extra_length=z_axis_carriage_front_height
    )
    bearing = align(bearing, carriage_front, Alignment.CENTER)
    bearing = align(bearing, guide_rod, Alignment.CENTER, axes=[0, 1])

    bearing_size = get_bounding_box_size(bearing)
    gap_bewteen_bearings = (
        z_axis_carriage_front_height
        - 2 * bearing_size[2]
        - z_axis_carriage_back_height
        - z_axis_carriage_x_axis_connector_thickness
    )

    carriage_front = bearing.use_as_cutter_on(carriage_front)

    top_bearing = align(bearing, carriage_front, Alignment.TOP)
    bottom_bearing = align(bearing, carriage_front, Alignment.BOTTOM)
    bottom_bearing = translate(0, 0, z_axis_carriage_back_height)(bottom_bearing)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_carriage_threaded_rod_clearance,
        z_axis_carriage_front_height + 10,
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

    nut = create_creality_threaded_rod_nut(
        threaded_rod_guide_cutter_clearance=z_axis_creality_nut_threaded_rod_cuide_cutter_clearance,
        screw_hole_clearence_type=z_axis_nut_screw_hole_clearence_type,
    )

    nut = align(nut, threaded_rod, Alignment.CENTER)

    nut_raw_base = nut.get_named_non_production_part("raw_base")
    base_aligner = align_translation(
        nut_raw_base, carriage_back, Alignment.STACK_BOTTOM
    )
    nut = base_aligner(nut)

    carriage_back = nut.use_as_cutter_on(carriage_back)
    carriage_back = carriage_back.cut(threaded_rod_cutter)

    guide_rod_center = get_bounding_box_center(guide_rod)
    carriage_front_center = get_bounding_box_center(carriage_front)

    carriage_cut_point = (
        carriage_front_center[0],
        guide_rod_center[1],
        carriage_front_center[2],
    )

    carriage_front, carriage_front_clamps = cut_in_two(
        carriage_front,
        cut_normal=(0, 1, 0),
        cut_thickness=z_axis_carriage_profile_clearance,
        cut_point=carriage_cut_point,
    )

    front_clamps_cutter = create_box(BIG_THING, BIG_THING, gap_bewteen_bearings)

    front_clamps_cutter = align(
        front_clamps_cutter, carriage_front_clamps, Alignment.CENTER
    )
    front_clamps_cutter = align(
        front_clamps_cutter,
        top_bearing,
        Alignment.STACK_BOTTOM,
        stack_gap=z_axis_carriage_x_axis_connector_thickness,
    )

    carriage_front_clamps = carriage_front_clamps.cut(front_clamps_cutter)

    bearings_fused = top_bearing.fuse(bottom_bearing)
    bearings_fused_center = get_bounding_box_center(bearings_fused)

    carriage_front_clamps_center = get_bounding_box_center(carriage_front_clamps)
    clamps_cut_point = (
        carriage_front_clamps_center[0],
        carriage_front_clamps_center[1],
        bearings_fused_center[2],
    )

    carriage_top_clamp, carriage_bottom_clamp = cut_in_two(
        carriage_front_clamps, cut_normal=(0, 0, 1), cut_point=clamps_cut_point
    )

    screw_assemblies = []

    for bt in [Alignment.BOTTOM, Alignment.TOP]:
        screw_representative_box = create_box(
            z_axis_carriage_width, z_axis_carriage_front_depth, bearing_size[2]
        )

        screw_representative_box = align(
            screw_representative_box, carriage_top_clamp, Alignment.CENTER
        )

        if bt == Alignment.TOP:
            screw_representative_box = align(
                screw_representative_box, carriage_top_clamp, Alignment.BOTTOM
            )
        else:
            screw_representative_box = align(
                screw_representative_box, carriage_bottom_clamp, Alignment.TOP
            )

        screw_representative_box = align(
            screw_representative_box, carriage_top_clamp, Alignment.FRONT
        )

        screw_assembly = create_four_screws_mount_assembly(
            screw_representative_box,
            z_axis_carriage_mount_screw_size,
            screw_length=z_axis_guide_rod_carriage_clamp_screw_length,
            screw_direction=Alignment.FRONT,
            flush_with_top=True,
            width_inset=z_axis_carriage_rod_clamp_screw_inset,
            length_inset=z_axis_carriage_rod_clamp_screw_inset,
            cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
            clearance_type=z_axis_default_clearance_hole_type,
            nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
        )

        screw_assembly = screw_assembly.prefixed_copy(
            f"carriage_clamp_{bt.name.lower()}_screw_assembly"
        )

        carriage_top_clamp = screw_assembly.use_as_cutter_on(carriage_top_clamp)
        carriage_bottom_clamp = screw_assembly.use_as_cutter_on(carriage_bottom_clamp)
        carriage_front = screw_assembly.use_as_cutter_on(carriage_front)

        screw_assemblies.append(screw_assembly)

    x_axis_mount_plate_bottom = create_filleted_box(
        z_axis_carriage_width,
        z_axis_x_axis_to_carriage_gap + z_axis_carriage_fillet_radius,
        z_axis_carriage_x_axis_connector_thickness,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom, carriage_bottom_clamp, Alignment.CENTER
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom, carriage_bottom_clamp, Alignment.BOTTOM
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_bottom_clamp,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_carriage_fillet_radius,
    )

    carriage_bottom_clamp = carriage_bottom_clamp.fuse(x_axis_mount_plate_bottom)

    x_axis_mount_plate_top = create_filleted_box(
        z_axis_carriage_width,
        z_axis_x_axis_to_carriage_gap + z_axis_carriage_fillet_radius,
        z_axis_carriage_x_axis_connector_thickness,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top, carriage_top_clamp, Alignment.CENTER
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top, carriage_top_clamp, Alignment.TOP
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_top_clamp,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_carriage_fillet_radius,
    )

    carriage_top_clamp = carriage_top_clamp.fuse(x_axis_mount_plate_top)

    carriage_back = bearing.use_as_cutter_on(carriage_back)
    carriage_body = carriage_front.fuse(carriage_back)
    retval = LeaderFollowersCuttersPart(carriage_body)

    for k, clamp in enumerate([carriage_top_clamp, carriage_bottom_clamp]):
        retval.add_named_follower(clamp, f"carriage_clamp_{k}")

    retval.add_named_non_production_part(top_bearing, "top_bearing")
    retval.add_named_non_production_part(nut, "threaded_rod_nut")

    for screw_assembly in screw_assemblies:
        for name, part in screw_assembly.get_named_non_production_part_items():
            retval.add_named_non_production_part(part, name)

    retval.add_named_non_production_part(bottom_bearing, "bottom_bearing")

    return retval


def create_z_axis():
    """Create the z_axis part."""

    z_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_4040, length_mm=z_axis_profile_length
    )

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)

    guide_rod = align(guide_rod, z_axis_profile, Alignment.CENTER)
    guide_rod = align(guide_rod, z_axis_profile, Alignment.STACK_FRONT)
    guide_rod = align(guide_rod, z_axis_profile, Alignment.BOTTOM)

    guide_rod = translate(0, -z_axis_guide_rod_profile_distance, 0)(guide_rod)

    guide_rod_cutter = create_cylinder(
        z_axis_guide_rod_diameter / 2 + 0.1, 2 * BIG_THING
    )
    guide_rod_cutter = align(guide_rod_cutter, guide_rod, Alignment.CENTER)

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

    rods_assembly = LeaderFollowersCuttersPart(guide_rod)

    rods_assembly.add_named_non_production_part(threaded_rod, "threaded_rod")

    pillow_block_bearing = create_pillow_block_bearing()

    pillow_block_bearing = pillow_block_bearing.prefixed_copy("pillow_block_bearing")

    pillow_block_bearing = rotate(-90, axis=(1, 0, 0))(pillow_block_bearing)

    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.CENTER)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.BOTTOM)
    pillow_block_bearing = translate(0, 0, z_axis_pillow_block_bearing_z_offset)(
        pillow_block_bearing
    )

    rods_assembly.add_named_non_production_part(
        pillow_block_bearing.leader, "pillow_block_bearing_body"
    )

    for name, part in pillow_block_bearing.get_named_non_production_part_items():

        rods_assembly.add_named_non_production_part(part, name)

    for name, cutter in pillow_block_bearing.get_named_cutter_items():
        rods_assembly.add_named_cutter(cutter, name)

    axial_bearing_stopper = create_axial_bearing_stopper()

    axial_bearing_stopper = align(axial_bearing_stopper, threaded_rod, Alignment.CENTER)
    axial_bearing_stopper = align(
        axial_bearing_stopper, pillow_block_bearing, Alignment.STACK_TOP
    )

    rods_assembly.add_named_follower(axial_bearing_stopper, "axial_bearing_stopper")

    axial_bearing = create_axial_ball_bearing_8_x_19()

    axial_bearing = align(axial_bearing, threaded_rod, Alignment.CENTER)
    axial_bearing = align(axial_bearing, axial_bearing_stopper, Alignment.STACK_TOP)

    rods_assembly.add_named_non_production_part(axial_bearing, "axial_bearing")

    rod_clamp = create_axial_rod_clamp()

    rod_clamp = align(rod_clamp, threaded_rod, Alignment.CENTER)
    rod_clamp = align(rod_clamp, axial_bearing, Alignment.STACK_TOP)

    for name, part in rod_clamp.get_named_non_production_part_items():
        rods_assembly.add_named_non_production_part(part, name)

    for name, part in rod_clamp.get_named_follower_items():
        rods_assembly.add_named_follower(part, name)

    motor = create_nema_composite(
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )

    motor = align(motor, threaded_rod, Alignment.CENTER)

    motor = align(motor, z_axis_profile, Alignment.BOTTOM)

    coupler = motor.get_named_follower("coupler")
    threaded_rod_part = rods_assembly.get_named_non_production_part("threaded_rod")
    coupler_aligner = align_translation(
        threaded_rod_part,
        coupler,
        Alignment.STACK_TOP,
        stack_gap=0,  # -z_axis_threaded_rod_coupler_overlap,
    )

    rods_assembly = coupler_aligner(rods_assembly)

    pillow_base = rods_assembly.get_named_non_production_part(
        "pillow_block_bearing_base"
    )
    pillow_base_size = get_bounding_box_size(pillow_base)

    pillow_bearing_mount_plate = create_box(
        pillow_base_size[0], BIG_THING, pillow_base_size[2]
    )

    pillow_bearing_mount_plate = align(
        pillow_bearing_mount_plate, pillow_base, Alignment.CENTER
    )
    pillow_bearing_mount_plate = align(
        pillow_bearing_mount_plate, pillow_base, Alignment.STACK_BACK
    )

    pillow_bearing_mount_plate = rods_assembly.use_as_cutter_on(
        pillow_bearing_mount_plate
    )

    profile_plane_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    profile_plane_cutter = align(
        profile_plane_cutter, pillow_bearing_mount_plate, Alignment.CENTER
    )
    profile_plane_cutter = align(profile_plane_cutter, z_axis_profile, Alignment.FRONT)

    pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(profile_plane_cutter)

    cutter_names = [f"pillow_block_bearing_mount_hole_cutter_{i}" for i in range(2)]

    for cutter_name in cutter_names:
        cutter = rods_assembly.get_named_cutter(cutter_name)

        nut_cutter = create_nut("M4", no_hole=True, slack=0.2)
        nut_cutter = rotate(90, axis=(1, 0, 0))(nut_cutter)
        nut_cutter = align(nut_cutter, cutter, Alignment.CENTER)
        nut_cutter = align(
            nut_cutter,
            pillow_bearing_mount_plate,
            Alignment.BACK,
        )
        pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(nut_cutter)

    pillow_bearing_profile_mount_plate = create_profile_mount_plate()
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate, pillow_bearing_mount_plate, Alignment.CENTER
    )
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate, pillow_bearing_mount_plate, Alignment.BACK
    )
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.STACK_TOP,
    )
    pillow_bearing_mount_plate = pillow_bearing_mount_plate.fuse(
        pillow_bearing_profile_mount_plate
    )

    retval.add_named_follower(pillow_bearing_mount_plate, "pillow_bearing_mount_plate")

    retval = retval.merge_except_leader(rods_assembly)

    retval.add_named_non_production_part(guide_rod, "guide_rod")

    for name, part in motor.get_named_follower_items():
        retval.add_named_non_production_part(part, name)

    motor_body = motor.get_named_follower("body")
    mount_plate = create_filleted_box(
        z_axis_motor_mount_plate_size,
        z_axis_motor_mount_plate_depth,
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    mount_plate = align(mount_plate, motor, Alignment.CENTER)
    mount_plate = align(mount_plate, motor_body, Alignment.STACK_TOP)

    mount_plate = align(
        mount_plate,
        z_axis_profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_motor_mount_plate_profile_distance,
    )

    profile_mount_plate = create_profile_mount_plate()
    profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.CENTER)
    profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.BACK)
    profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.STACK_TOP)

    mount_plate = motor.use_as_cutter_on(mount_plate)

    guide_rod_clamp = create_filleted_box(
        z_axis_guide_rod_clamp_width,
        z_axis_guide_rod_clamp_depth,
        z_axis_guide_rod_clamp_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.CENTER)
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.STACK_TOP)
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.FRONT)

    screws_mount_assembly = create_four_screws_mount_assembly(
        guide_rod_clamp,
        "M3",
        z_axis_guide_rod_clamp_screw_length,
        Alignment.FRONT,
        flush_with_top=True,
        cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
        clearance_type=z_axis_default_clearance_hole_type,
        nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
    )

    guide_rod_clamp = screws_mount_assembly.use_as_cutter_on(guide_rod_clamp)

    mount_plate = mount_plate.fuse(guide_rod_clamp)
    mount_plate = mount_plate.fuse(profile_mount_plate)
    mount_plate = mount_plate.cut(guide_rod_cutter)

    for name, part in screws_mount_assembly.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"guide_rod_clamp_{name}")

    guide_rod_center = get_bounding_box_center(guide_rod)
    guide_rod_clamp_center = get_bounding_box_center(guide_rod_clamp)

    cut_point = (
        guide_rod_clamp_center[0],
        guide_rod_center[1],
        guide_rod_clamp_center[2],
    )

    mount_plate_back, mount_plate_clamp_part = cut_in_two(
        mount_plate,
        cut_normal=(0, 1, 0),
        cut_thickness=z_axis_rod_clamp_gap,
        cut_point=cut_point,
    )

    retval.add_named_follower(mount_plate_clamp_part, "mount_plate_clamp_part")
    retval.add_named_follower(mount_plate_back, "mount_plate_back")

    top_mount = create_top_mount(guide_rod, threaded_rod, z_axis_profile)

    retval.add_named_follower(top_mount.leader, "top_mount")

    retval.add_named_follower(
        top_mount.get_named_follower("top_mount_clamp"), "top_mount_clamp"
    )
    for name, part in top_mount.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"top_mount_{name}")

    return retval


def create_box_hole_cutter(box_width, box_length, box_height):

    box_to_leave_free = create_box(box_width, box_length, box_height)

    box_hole_cutter = PartCollector()
    for alignment in [
        Alignment.STACK_TOP,
        Alignment.STACK_BOTTOM,
        Alignment.STACK_FRONT,
        Alignment.STACK_BACK,
        Alignment.STACK_LEFT,
        Alignment.STACK_RIGHT,
    ]:

        cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
        cutter = align(cutter, box_to_leave_free, Alignment.CENTER)
        cutter = align(cutter, box_to_leave_free, alignment)
        box_hole_cutter = box_hole_cutter.fuse(cutter)

    return LeaderFollowersCuttersPart(box_to_leave_free, cutters=[box_hole_cutter])


def create_minimal_z_axis_reference():
    """Create only the Z-profile and rod geometry required to build/place a carriage."""

    z_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_4040, length_mm=z_axis_profile_length
    )

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)
    guide_rod = align(guide_rod, z_axis_profile, Alignment.CENTER)
    guide_rod = align(guide_rod, z_axis_profile, Alignment.STACK_FRONT)
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

    return retval


def align_x_axis_to_z_carriages(x_axis, z_axes_fused, carriages_fused):
    """Place the X axis relative to the Z carriages using production alignment rules.

    Source of truth:
    - X axis stays centered between the two Z axes in X/Y.
    - The lower X profile sits in front of the carriage set with the configured gap.
    - The lower X profile bottom is raised above the carriage bottom by the connector thickness.
    """

    x_axis = align(x_axis, z_axes_fused, Alignment.CENTER, axes=[0, 1])

    lower_axis_profile = x_axis.get_non_production_part_by_name("lower_axis_profile")
    axis_profile_aligner = align_translation(
        lower_axis_profile,
        carriages_fused,
        Alignment.FRONT,
    )
    x_axis = axis_profile_aligner(x_axis)

    lower_axis_profile = x_axis.get_non_production_part_by_name("lower_axis_profile")
    axis_profile_aligner = align_translation(
        lower_axis_profile,
        carriages_fused,
        Alignment.BOTTOM,
    )
    x_axis = axis_profile_aligner(x_axis)

    x_axis = translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(x_axis)

    return x_axis


def create_positioned_x_z_axis_assembly(
    x_axis,
    z_axis_factory,
    *,
    frame=None,
    z_axis_base_z_offset,
    carriage_z_offset,
):
    """Build the aligned dual-Z and X-axis assembly from shared source-of-truth logic."""

    positioned_z_axes = {}
    positioned_carriages = {}
    z_axes_fused = PartCollector()
    carriages_fused = PartCollector()

    for side in [Alignment.LEFT, Alignment.RIGHT]:
        side_name = side.name.lower()

        z_axis = z_axis_factory()
        if frame is not None:
            z_axis = align(z_axis, frame, Alignment.CENTER)
            z_axis = align(z_axis, frame, Alignment.BOTTOM)

        z_axis = translate(
            side.sign * z_axis_x_offset_from_center,
            z_axis_y_offset,
            z_axis_base_z_offset,
        )(z_axis)

        positioned_z_axes[side_name] = z_axis
        z_axes_fused = z_axes_fused.fuse(z_axis.leader)

        carriage = create_carriage(
            z_axis.get_named_non_production_part("guide_rod"),
            z_axis.get_named_non_production_part("threaded_rod"),
            z_axis,
        )
        carriage = translate(0, 0, carriage_z_offset)(carriage)

        positioned_carriages[side_name] = carriage
        carriages_fused = carriages_fused.fuse(carriage.leaders_followers_fused())

    x_axis = align_x_axis_to_z_carriages(x_axis, z_axes_fused, carriages_fused)

    return positioned_z_axes, positioned_carriages, x_axis


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )
    from mege_ender_3v3ke_idex.designs.x_axis import create_x_axis  # noqa: F401

    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    z_animation = {"z_axis": (0, 0, 300)}
    bed_animation = {"bed_y": (0, 155, 0)}
    x_axis_carriage_animations = {
        "carriage_1": {**z_animation, "x_carriage_1": (300, 0, 0)},
        "carriage_2": {**z_animation, "x_carriage_2": (-300, 0, 0)},
    }

    frame = create_printer_frame()

    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    for name, npp in frame.get_named_non_production_part_items():
        animation = bed_animation if name == "print_bed" else None
        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    x_axis = create_x_axis()
    positioned_z_axes, positioned_carriages, x_axis = (
        create_positioned_x_z_axis_assembly(
            x_axis,
            create_z_axis,
            frame=frame,
            z_axis_base_z_offset=z_axis_base_z_offset,
            carriage_z_offset=z_axis_carriage_z_offset,
        )
    )

    for prefix, z_axis in positioned_z_axes.items():
        parts.add(z_axis, f"{prefix}_z_axis", flip=False, skip_in_production=True)

        for name, npp in z_axis.get_named_non_production_part_items():
            parts.add(npp, f"{prefix}_{name}", flip=False, skip_in_production=True)

        for name, follower in z_axis.get_named_follower_items():

            skip_in_production = False

            prod_rotation_angle = None
            prod_rotation_axis = None

            if "clamp" in name and "axial" not in name:
                prod_rotation_angle = 90
                prod_rotation_axis = (1, 0, 0)

            elif "pillow_bearing_mount_plate" in name:
                prod_rotation_angle = -90
                prod_rotation_axis = (1, 0, 0)

            parts.add(
                follower,
                f"{prefix}_{name}",
                flip=False,
                skip_in_production=skip_in_production,
                prod_rotation_angle=prod_rotation_angle,
                prod_rotation_axis=prod_rotation_axis,
            )
    for prefix, carriage in positioned_carriages.items():

        parts.add(
            carriage,
            f"{prefix}_z_axis_carriage",
            flip=False,
            skip_in_production=False,
            animation=z_animation,
        )

        for name, follower in carriage.get_named_follower_items():
            skip_in_production = False
            prod_rotation_angle = None
            prod_rotation_axis = None
            if "clamp" in name:
                prod_rotation_angle = 90
                prod_rotation_axis = (1, 0, 0)

            parts.add(
                follower,
                f"{prefix}_{name}",
                flip=False,
                skip_in_production=skip_in_production,
                prod_rotation_angle=prod_rotation_angle,
                prod_rotation_axis=prod_rotation_axis,
                animation=z_animation,
            )

        for name, npp in carriage.get_named_non_production_part_items():
            parts.add(
                npp,
                f"{prefix}_{name}",
                flip=False,
                skip_in_production=True,
                animation=z_animation,
            )

    parts.add(
        x_axis,
        "x_axis",
        flip=False,
        skip_in_production=True,
        animation=z_animation,
    )

    already_added_names = set()
    for name, npp in x_axis.get_named_non_production_part_items():
        current_naeme = f"x_axis_{name}"
        already_added_names.add(current_naeme)
        animation = x_axis_carriage_animations.get(name, z_animation)
        parts.add(
            npp,
            current_naeme,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    for name, follower in x_axis.get_named_follower_items():
        current_naeme = f"x_axis_{name}"
        if current_naeme in already_added_names:
            continue

        animation = x_axis_carriage_animations.get(name, z_animation)
        parts.add(
            follower,
            current_naeme,
            flip=False,
            skip_in_production=True,
            animation=animation,
        )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=4,
        export_individual_parts=False,
        export_stl=PROD,  # only export STL in production, for slicing; for obj export, not needed
    )

    _logger.info("z_axis created successfully!")


if __name__ == "__main__":
    main()
