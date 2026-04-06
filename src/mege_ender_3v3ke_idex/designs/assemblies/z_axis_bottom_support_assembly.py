"""Declarative z-axis lower support assembly."""

from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_axial_ball_bearing_8_x_19,
    create_axial_bearing_stopper,
    create_axial_rod_clamp,
)
from shellforgepy.simple import *


def _get_rod_part(rod):
    return rod.leader if hasattr(rod, "leader") else rod


def _get_threaded_rod_coupler_reference(z_axis_threaded_rod):
    return z_axis_threaded_rod.get_named_non_production_part("coupler_reference")


def create_z_axis_bottom_support_assembly(
    *,
    z_axis_profile,
    z_axis_threaded_rod,
    z_axis_motor_mount,
    side,
    BIG_THING,
    z_axis_axial_ball_bearing_8_x_19_ball_count,
    z_axis_axial_ball_bearing_8_x_19_ball_diameter,
    z_axis_axial_ball_bearing_8_x_19_ball_holder_disc_inner_diameter,
    z_axis_axial_ball_bearing_8_x_19_ball_holder_disc_outer_diameter,
    z_axis_axial_ball_bearing_8_x_19_ball_holder_disc_thickness,
    z_axis_axial_ball_bearing_8_x_19_disc_thickness,
    z_axis_axial_ball_bearing_8_x_19_inner_diameter,
    z_axis_axial_ball_bearing_8_x_19_outer_diameter,
    z_axis_axial_ball_bearing_8_x_19_thickness,
    z_axis_axial_bearing_stopper_inner_diameter,
    z_axis_axial_bearing_stopper_outer_diameter,
    z_axis_axial_bearing_stopper_thickness,
    z_axis_axial_rod_clamp_cylinder_head_cutter_clearance,
    z_axis_axial_rod_clamp_gap,
    z_axis_axial_rod_clamp_inner_diameter,
    z_axis_axial_rod_clamp_nut_clearance,
    z_axis_axial_rod_clamp_outer_diameter,
    z_axis_axial_rod_clamp_outer_diameter_cutting_depth,
    z_axis_axial_rod_clamp_screw_head_backoff,
    z_axis_axial_rod_clamp_screw_hole_distance_from_center,
    z_axis_axial_rod_clamp_screw_length,
    z_axis_axial_rod_clamp_screw_size,
    z_axis_axial_rod_clamp_thickness,
):
    """Create the printable lower support stack for one z-axis side."""

    del z_axis_profile
    del side
    threaded_rod = _get_rod_part(z_axis_threaded_rod)
    pillow_block_bearing = z_axis_motor_mount.get_named_non_production_part(
        "pillow_block_bearing_body"
    )

    axial_bearing_stopper = create_axial_bearing_stopper(
        z_axis_axial_bearing_stopper_outer_diameter=z_axis_axial_bearing_stopper_outer_diameter,
        z_axis_axial_bearing_stopper_inner_diameter=z_axis_axial_bearing_stopper_inner_diameter,
        z_axis_axial_bearing_stopper_thickness=z_axis_axial_bearing_stopper_thickness,
    )
    axial_bearing_stopper = align(axial_bearing_stopper, threaded_rod, Alignment.CENTER)
    axial_bearing_stopper = align(
        axial_bearing_stopper,
        pillow_block_bearing,
        Alignment.STACK_TOP,
    )

    axial_bearing = create_axial_ball_bearing_8_x_19(
        axial_ball_bearing_8_x_19_ball_count=z_axis_axial_ball_bearing_8_x_19_ball_count,
        axial_ball_bearing_8_x_19_ball_diameter=z_axis_axial_ball_bearing_8_x_19_ball_diameter,
        axial_ball_bearing_8_x_19_ball_holder_disc_inner_diameter=z_axis_axial_ball_bearing_8_x_19_ball_holder_disc_inner_diameter,
        axial_ball_bearing_8_x_19_ball_holder_disc_outer_diameter=z_axis_axial_ball_bearing_8_x_19_ball_holder_disc_outer_diameter,
        axial_ball_bearing_8_x_19_ball_holder_disc_thickness=z_axis_axial_ball_bearing_8_x_19_ball_holder_disc_thickness,
        axial_ball_bearing_8_x_19_disc_thickness=z_axis_axial_ball_bearing_8_x_19_disc_thickness,
        axial_ball_bearing_8_x_19_inner_diameter=z_axis_axial_ball_bearing_8_x_19_inner_diameter,
        axial_ball_bearing_8_x_19_outer_diameter=z_axis_axial_ball_bearing_8_x_19_outer_diameter,
        axial_ball_bearing_8_x_19_thickness=z_axis_axial_ball_bearing_8_x_19_thickness,
    )
    axial_bearing = align(axial_bearing, threaded_rod, Alignment.CENTER)
    axial_bearing = align(axial_bearing, axial_bearing_stopper, Alignment.STACK_TOP)

    rod_clamp = create_axial_rod_clamp(
        BIG_THING=BIG_THING,
        z_axis_axial_rod_clamp_cylinder_head_cutter_clearance=z_axis_axial_rod_clamp_cylinder_head_cutter_clearance,
        z_axis_axial_rod_clamp_gap=z_axis_axial_rod_clamp_gap,
        z_axis_axial_rod_clamp_inner_diameter=z_axis_axial_rod_clamp_inner_diameter,
        z_axis_axial_rod_clamp_nut_clearance=z_axis_axial_rod_clamp_nut_clearance,
        z_axis_axial_rod_clamp_outer_diameter=z_axis_axial_rod_clamp_outer_diameter,
        z_axis_axial_rod_clamp_outer_diameter_cutting_depth=z_axis_axial_rod_clamp_outer_diameter_cutting_depth,
        z_axis_axial_rod_clamp_screw_head_backoff=z_axis_axial_rod_clamp_screw_head_backoff,
        z_axis_axial_rod_clamp_screw_hole_distance_from_center=z_axis_axial_rod_clamp_screw_hole_distance_from_center,
        z_axis_axial_rod_clamp_screw_length=z_axis_axial_rod_clamp_screw_length,
        z_axis_axial_rod_clamp_screw_size=z_axis_axial_rod_clamp_screw_size,
        z_axis_axial_rod_clamp_thickness=z_axis_axial_rod_clamp_thickness,
    )
    rod_clamp = align(rod_clamp, threaded_rod, Alignment.CENTER)
    rod_clamp = align(rod_clamp, axial_bearing, Alignment.STACK_TOP)
    retval = LeaderFollowersCuttersPart(leader=axial_bearing_stopper)
    retval.add_named_follower(
        rod_clamp.get_named_follower("axial_clamp_part_0"),
        "axial_clamp_part_0",
    )
    retval.add_named_follower(
        rod_clamp.get_named_follower("axial_clamp_part_1"),
        "axial_clamp_part_1",
    )

    retval.add_named_non_production_part(axial_bearing, "axial_bearing")
    for name, part in rod_clamp.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    return retval
