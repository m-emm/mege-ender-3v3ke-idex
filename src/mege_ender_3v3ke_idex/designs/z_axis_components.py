"""Shared z-axis geometry helpers extracted from the legacy z-axis script."""

import math

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.creality_wheel import create_608z_bearing
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from shellforgepy.metrics import record_length_metric
from shellforgepy.simple import *


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
    return create_ring(
        axial_bearing_stopper_outer_diameter / 2,
        axial_bearing_stopper_inner_diameter / 2,
        axial_bearing_stopper_thickness,
    )


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
            i * axial_rod_clamp_screw_hole_distance_from_center,
            0,
            0,
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
            cylinder_head_cutter,
            screw_cutter,
            Alignment.CENTER,
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

    screws = []
    for cylinder_head_cutter in cylinder_head_cutters:
        cylinder_head_cutter = align(
            cylinder_head_cutter,
            clamp,
            Alignment.STACK_FRONT,
            stack_gap=-axial_rod_clamp_outer_diameter_cutting_depth,
        )
        clamp = clamp.cut(cylinder_head_cutter)

        screw = create_cylinder_screw(
            size=axial_rod_clamp_screw_size,
            length=axial_rod_clamp_screw_length,
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
        screws.append(screw)

    axial_clamp_parts = cut_in_two(
        clamp,
        cut_normal=(0, 1, 0),
        cut_thickness=axial_rod_clamp_gap,
    )

    retval = LeaderFollowersCuttersPart(clamp)
    for i, axial_clamp_part in enumerate(axial_clamp_parts):
        retval.add_named_follower(axial_clamp_part, f"axial_clamp_part_{i}")
    for i, screw in enumerate(screws):
        retval.add_named_non_production_part(screw, f"axial_clamp_screw_{i}")

    return retval


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

    return LeaderFollowersCuttersPart(bearing, cutters=[cutter])


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
        pillow_block_bearing_base_gap_length,
        BIG_THING,
        BIG_THING,
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
            pillow_block_bearing_mount_hole_diameter / 2,
            BIG_THING,
        )
        mount_hole_cutter = rotate(90, axis=(1, 0, 0))(mount_hole_cutter)
        mount_hole_cutter = align(mount_hole_cutter, base, Alignment.CENTER)
        mount_hole_cutter = translate(
            lr.sign * pillow_block_bearing_mount_hole_center_distance / 2,
            0,
            0,
        )(mount_hole_cutter)
        mount_hole_cutters.append(mount_hole_cutter)

        mount_screw = create_cylinder_screw(size=mount_screw_size, length=screw_length)
        mount_screw = rotate(-90, axis=(1, 0, 0))(mount_screw)
        mount_screw = align(mount_screw, mount_hole_cutter, Alignment.CENTER)
        mount_screw = align(mount_screw, base, Alignment.BACK)
        mount_screw = translate(
            0,
            MScrew.from_size(mount_screw_size).cylinder_head_height,
            0,
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

    return rotate(-90, axis=(1, 0, 0))(retval)


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

    return bearing.fuse(ball_holder_disc)


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
            mount_hole_drill_diaameter / 2,
            2 * base_thickness,
        )
        mount_hole_drill_cutter = align(mount_hole_drill_cutter, base, Alignment.CENTER)
        mount_hole_drill_cutter = translate(
            lr.sign * mount_hole_center_center_distance / 2,
            0,
            0,
        )(mount_hole_drill_cutter)

        external_mount_hole_drill = create_cylinder(
            external_mount_hole_drill_diameter / 2,
            BIG_THING,
        )
        external_mount_hole_drill = align(
            external_mount_hole_drill,
            mount_hole_drill_cutter,
            Alignment.CENTER,
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
            external_mount_hole_drill,
            f"external_mount_hole_drill_{idx}",
        )

    rod_guide_cutter = create_cylinder(
        rod_guide_diameter / 2 + threaded_rod_guide_cutter_clearance,
        BIG_THING,
    )
    rod_guide_cutter = align(rod_guide_cutter, rod_guide, Alignment.CENTER)
    retval.add_named_cutter(rod_guide_cutter, "rod_guide_cutter")

    return retval


def create_top_bridge_profile(positioned_z_axes):
    z_axis_profiles = PartCollector()
    for z_axis in positioned_z_axes.values():
        z_axis_profiles = z_axis_profiles.fuse(getattr(z_axis, "leader", z_axis))

    bridge_length = get_bounding_box_size(z_axis_profiles)[0]
    record_length_metric(
        "extrusion_profile",
        ExtrusionProfileType.PROFILE_2020.value,
        "z_axis_top_bridge_profile",
        bridge_length,
    )
    bridge = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020,
        length_mm=bridge_length,
    )
    bridge = rotate(90, axis=(0, 1, 0))(bridge)
    bridge = align(bridge, z_axis_profiles, Alignment.CENTER, axes=[0])
    bridge = align(bridge, z_axis_profiles, Alignment.TOP)
    bridge = align(bridge, z_axis_profiles, Alignment.STACK_BACK)

    return bridge
