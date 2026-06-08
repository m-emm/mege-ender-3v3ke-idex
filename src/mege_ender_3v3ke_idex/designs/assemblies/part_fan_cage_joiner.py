"""Join part fan and extruder cage assemblies with a shared flange."""

from shellforgepy.simple import *


def _create_flange_block(width, depth, height, fillet_radius):
    if fillet_radius > 0:
        return create_filleted_box(
            width,
            depth,
            height,
            fillet_radius=fillet_radius,
            no_fillets_at=[Alignment.RIGHT, Alignment.TOP, Alignment.BOTTOM],
        )
    return create_box(width, depth, height)


def _create_join_flange_halves(
    *,
    side_mount_plate,
    flange_extension,
    flange_half_height,
    screw_size,
    clearance_type,
    fillet_radius,
):
    side_mount_plate_depth = get_bounding_box_size(side_mount_plate)[1]

    bottom_flange = _create_flange_block(
        flange_extension,
        side_mount_plate_depth,
        flange_half_height,
        fillet_radius,
    )
    bottom_flange = align(bottom_flange, side_mount_plate, Alignment.CENTER, axes=[1])
    bottom_flange = align(bottom_flange, side_mount_plate, Alignment.STACK_LEFT)
    bottom_flange = align(bottom_flange, side_mount_plate, Alignment.TOP)

    top_flange = _create_flange_block(
        flange_extension,
        side_mount_plate_depth,
        flange_half_height,
        fillet_radius,
    )
    top_flange = align(top_flange, bottom_flange, Alignment.CENTER, axes=[0, 1])
    top_flange = align(top_flange, bottom_flange, Alignment.STACK_TOP)

    flange_stack = bottom_flange.fuse(top_flange)
    clearance_hole = create_cylinder(
        get_clearance_hole_diameter(screw_size, clearance_type) / 2,
        flange_half_height * 2 + 2,
    )
    clearance_hole = align(clearance_hole, flange_stack, Alignment.CENTER)

    bottom_flange = bottom_flange.cut(clearance_hole)
    top_flange = top_flange.cut(clearance_hole)

    return bottom_flange, top_flange, clearance_hole


def join_part_fans_with_extruder_cage(
    *,
    part_fans,
    extruder_cage,
    flange_extension=8.0,
    flange_half_height=3.0,
    screw_size="M3",
    clearance_type="loose",
    fillet_radius=0.0,
):
    """Return joined output assemblies for a part fan and extruder cage pair."""

    side_mount_plate = part_fans.get_named_non_production_part("side_mount_plate")
    bottom_flange, top_flange, _ = _create_join_flange_halves(
        side_mount_plate=side_mount_plate,
        flange_extension=flange_extension,
        flange_half_height=flange_half_height,
        screw_size=screw_size,
        clearance_type=clearance_type,
        fillet_radius=fillet_radius,
    )

    joined_part_fans = part_fans.copy()
    joined_extruder_cage = extruder_cage.copy()

    joined_part_fans.leader = joined_part_fans.leader.fuse(bottom_flange)
    joined_extruder_cage.leader = joined_extruder_cage.leader.fuse(top_flange)

    return {
        "part_fans": joined_part_fans,
        "extruder_cage": joined_extruder_cage,
    }
