"""Declarative z-axis lower support assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    BIG_THING,
    z_axis_pillow_block_bearing_z_offset,
)
from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_axial_ball_bearing_8_x_19,
    create_axial_bearing_stopper,
    create_axial_rod_clamp,
    create_pillow_block_bearing,
    create_profile_mount_plate,
)
from shellforgepy.simple import *


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def _get_rods_parts(z_axis_rods):
    guide_rod = z_axis_rods.leader if hasattr(z_axis_rods, "leader") else z_axis_rods
    threaded_rod = z_axis_rods.get_named_non_production_part("threaded_rod")
    return guide_rod, threaded_rod


def create_z_axis_bottom_support_assembly(*, z_axis_profile, z_axis_rods, context=None):
    """Create the printable lower support stack for one z-axis side."""

    del context

    profile = _get_profile_part(z_axis_profile)
    guide_rod, threaded_rod = _get_rods_parts(z_axis_rods)

    clearance_stack = LeaderFollowersCuttersPart(guide_rod)
    clearance_stack.add_named_non_production_part(threaded_rod, "threaded_rod")

    pillow_block_bearing = create_pillow_block_bearing().prefixed_copy(
        "pillow_block_bearing"
    )
    pillow_block_bearing = rotate(-90, axis=(1, 0, 0))(pillow_block_bearing)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.CENTER)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.BOTTOM)
    pillow_block_bearing = translate(0, 0, z_axis_pillow_block_bearing_z_offset)(
        pillow_block_bearing
    )

    clearance_stack.add_named_non_production_part(
        pillow_block_bearing.leader,
        "pillow_block_bearing_body",
    )
    for name, part in pillow_block_bearing.get_named_non_production_part_items():
        clearance_stack.add_named_non_production_part(part, name)
    for name, cutter in pillow_block_bearing.get_named_cutter_items():
        clearance_stack.add_named_cutter(cutter, name)

    axial_bearing_stopper = create_axial_bearing_stopper()
    axial_bearing_stopper = align(axial_bearing_stopper, threaded_rod, Alignment.CENTER)
    axial_bearing_stopper = align(
        axial_bearing_stopper,
        pillow_block_bearing,
        Alignment.STACK_TOP,
    )
    clearance_stack.add_named_follower(axial_bearing_stopper, "axial_bearing_stopper")

    axial_bearing = create_axial_ball_bearing_8_x_19()
    axial_bearing = align(axial_bearing, threaded_rod, Alignment.CENTER)
    axial_bearing = align(axial_bearing, axial_bearing_stopper, Alignment.STACK_TOP)
    clearance_stack.add_named_non_production_part(axial_bearing, "axial_bearing")

    rod_clamp = create_axial_rod_clamp()
    rod_clamp = align(rod_clamp, threaded_rod, Alignment.CENTER)
    rod_clamp = align(rod_clamp, axial_bearing, Alignment.STACK_TOP)
    for name, part in rod_clamp.get_named_non_production_part_items():
        clearance_stack.add_named_non_production_part(part, name)
    for name, part in rod_clamp.get_named_follower_items():
        clearance_stack.add_named_follower(part, name)

    pillow_base = clearance_stack.get_named_non_production_part(
        "pillow_block_bearing_base"
    )
    pillow_base_size = get_bounding_box_size(pillow_base)

    pillow_bearing_mount_plate = create_box(
        pillow_base_size[0],
        BIG_THING,
        pillow_base_size[2],
    )
    pillow_bearing_mount_plate = align(
        pillow_bearing_mount_plate,
        pillow_base,
        Alignment.CENTER,
    )
    pillow_bearing_mount_plate = align(
        pillow_bearing_mount_plate,
        pillow_base,
        Alignment.STACK_BACK,
    )
    pillow_bearing_mount_plate = clearance_stack.use_as_cutter_on(
        pillow_bearing_mount_plate
    )

    profile_plane_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    profile_plane_cutter = align(
        profile_plane_cutter,
        pillow_bearing_mount_plate,
        Alignment.CENTER,
    )
    profile_plane_cutter = align(profile_plane_cutter, profile, Alignment.FRONT)
    pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(profile_plane_cutter)

    for cutter_index in range(2):
        cutter = clearance_stack.get_named_cutter(
            f"pillow_block_bearing_mount_hole_cutter_{cutter_index}"
        )
        nut_cutter = create_nut("M4", no_hole=True, slack=0.2)
        nut_cutter = rotate(90, axis=(1, 0, 0))(nut_cutter)
        nut_cutter = align(nut_cutter, cutter, Alignment.CENTER)
        nut_cutter = align(nut_cutter, pillow_bearing_mount_plate, Alignment.BACK)
        pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(nut_cutter)

    pillow_bearing_profile_mount_plate = create_profile_mount_plate()
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.CENTER,
    )
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.BACK,
    )
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.STACK_TOP,
    )
    pillow_bearing_mount_plate = pillow_bearing_mount_plate.fuse(
        pillow_bearing_profile_mount_plate
    )

    retval = LeaderFollowersCuttersPart(leader=pillow_bearing_mount_plate)

    retval.add_named_follower(axial_bearing_stopper, "axial_bearing_stopper")
    retval.add_named_follower(
        rod_clamp.get_named_follower("axial_clamp_part_0"),
        "axial_clamp_part_0",
    )
    retval.add_named_follower(
        rod_clamp.get_named_follower("axial_clamp_part_1"),
        "axial_clamp_part_1",
    )

    retval.add_named_non_production_part(
        pillow_block_bearing.leader,
        "pillow_block_bearing_body",
    )
    for name, part in pillow_block_bearing.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)
    retval.add_named_non_production_part(axial_bearing, "axial_bearing")
    for name, part in rod_clamp.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    return retval
