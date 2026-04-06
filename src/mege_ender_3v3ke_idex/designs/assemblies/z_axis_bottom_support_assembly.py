"""Declarative z-axis lower support assembly."""

from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_axial_ball_bearing_8_x_19,
    create_axial_rod_clamp,
)
from shellforgepy.simple import *


def _get_rod_part(rod):
    return rod.leader if hasattr(rod, "leader") else rod


def create_axial_bearing_stopper(
    *,
    z_axis_axial_bearing_stopper_outer_diameter,
    z_axis_axial_bearing_stopper_inner_diameter,
    z_axis_axial_bearing_stopper_thickness,
    z_axis_axial_bearing_stopper_inner_diameter_top,
    z_axis_axial_bearing_stopper_axial_bearing_sink,
    z_axis_axial_bearing_stopper_axial_bearing_clearance,
    z_axis_axial_bearing_stopper_axial_bearing_outer_diaameter,
):
    disk = create_cylinder(
        z_axis_axial_bearing_stopper_outer_diameter / 2,
        z_axis_axial_bearing_stopper_thickness,
    )

    # disk = apply_fillet_by_alignment(
    #     disk,
    #     fillet_radius=z_axis_axial_bearing_stopper_thickness / 4,
    #     fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    # )

    hole_cutter = create_cone(
        radius1=z_axis_axial_bearing_stopper_inner_diameter / 2,
        radius2=z_axis_axial_bearing_stopper_inner_diameter_top / 2,
        height=z_axis_axial_bearing_stopper_thickness,
    )

    hole_cutter = align(hole_cutter, disk, Alignment.CENTER)
    retval = disk.cut(hole_cutter)

    retval = apply_fillet_by_alignment(
        retval,
        fillet_radius=z_axis_axial_bearing_stopper_thickness / 8,
        fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    axia_bearing_cutter_disk = create_cylinder(
        z_axis_axial_bearing_stopper_axial_bearing_outer_diaameter / 2
        + z_axis_axial_bearing_stopper_axial_bearing_clearance,
        z_axis_axial_bearing_stopper_axial_bearing_sink,
    )
    axia_bearing_cutter_disk = align(axia_bearing_cutter_disk, retval, Alignment.CENTER)
    axia_bearing_cutter_disk = align(axia_bearing_cutter_disk, retval, Alignment.TOP)
    retval = retval.cut(axia_bearing_cutter_disk)

    return retval


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
    z_axis_axial_bearing_stopper_inner_diameter_top,
    z_axis_axial_bearing_stopper_outer_diameter,
    z_axis_axial_bearing_stopper_thickness,
    z_axis_axial_bearing_stopper_axial_bearing_sink,
    z_axis_axial_bearing_stopper_axial_bearing_clearance,
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
        z_axis_axial_bearing_stopper_inner_diameter_top=z_axis_axial_bearing_stopper_inner_diameter_top,
        z_axis_axial_bearing_stopper_axial_bearing_sink=z_axis_axial_bearing_stopper_axial_bearing_sink,
        z_axis_axial_bearing_stopper_axial_bearing_clearance=z_axis_axial_bearing_stopper_axial_bearing_clearance,
        z_axis_axial_bearing_stopper_axial_bearing_outer_diaameter=z_axis_axial_ball_bearing_8_x_19_outer_diameter,
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
