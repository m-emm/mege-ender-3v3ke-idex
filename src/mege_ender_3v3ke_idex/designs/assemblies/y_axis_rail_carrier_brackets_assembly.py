"""Rail carrier brackets assembled against the placed y-axis."""

from mege_ender_3v3ke_idex.designs.hollow_profiles import create_hollow_profile_ring
from shellforgepy.simple import *


def _create_bracket_for_corner(
    *,
    frame_front_back_profile,
    y_axis_profile,
    side_alignment,
    front_back_alignment,
    y_axis_rail_carrier_bracket_outer_diameter,
    y_axis_rail_carrier_bracket_height,
    y_axis_rail_carrier_bracket_profile_width,
    y_axis_rail_carrier_bracket_profile_wall,
    y_axis_rail_carrier_bracket_mount_plate_thickness,
    y_axis_rail_carrier_bracket_mount_plate_length,
    y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
    y_axis_rail_carrier_bracket_mount_screw_length,
    y_axis_rail_carrier_bracket_mount_screw_size,
    y_axis_rail_carrier_bracket_mount_screw_inset,
    context=None,
):

    BIG_THING = (context or {}).get("BIG_THING", 500)

    rotation_angle_map = {
        (Alignment.LEFT, Alignment.FRONT): 90,
        (Alignment.LEFT, Alignment.BACK): 0,
        (Alignment.RIGHT, Alignment.FRONT): 180,
        (Alignment.RIGHT, Alignment.BACK): -90,
    }

    rail_carrier_bracket_ring_profile = create_hollow_profile_ring(
        y_axis_rail_carrier_bracket_outer_diameter,
        profile_depth=y_axis_rail_carrier_bracket_profile_width,
        profile_height=y_axis_rail_carrier_bracket_height,
        wall_thickness=y_axis_rail_carrier_bracket_profile_wall,
        angle=90,
    )

    rail_carrier_bracket_ring_profile = rotate(
        rotation_angle_map[(side_alignment, front_back_alignment)] - 90
    )(rail_carrier_bracket_ring_profile)
    rail_carrier_bracket_ring_profile = align(
        rail_carrier_bracket_ring_profile,
        y_axis_profile,
        Alignment.CENTER,
        axes=[0],
    )
    rail_carrier_bracket_ring_profile = align(
        rail_carrier_bracket_ring_profile,
        frame_front_back_profile,
        Alignment.TOP,
    )
    rail_carrier_bracket_ring_profile = align(
        rail_carrier_bracket_ring_profile,
        y_axis_profile,
        (
            Alignment.STACK_LEFT
            if side_alignment == Alignment.RIGHT
            else Alignment.STACK_RIGHT
        ),
    )
    rail_carrier_bracket_ring_profile = align(
        rail_carrier_bracket_ring_profile,
        y_axis_profile,
        front_back_alignment,
    )
    rail_carrier_bracket_ring_profile = translate(
        -side_alignment.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
        -front_back_alignment.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
        y_axis_rail_carrier_bracket_mount_plate_thickness,
    )(rail_carrier_bracket_ring_profile)

    profile_size = get_bounding_box_size(y_axis_profile)

    rail_side_mount_plate = create_filleted_box(
        y_axis_rail_carrier_bracket_mount_plate_thickness,
        y_axis_rail_carrier_bracket_mount_plate_length,
        profile_size[2],
        y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, front_back_alignment],
    )
    rail_side_mount_plate = align(
        rail_side_mount_plate,
        y_axis_profile,
        Alignment.CENTER,
        axes=[0],
    )
    rail_side_mount_plate = align(
        rail_side_mount_plate,
        y_axis_profile,
        Alignment.TOP,
    )
    rail_side_mount_plate = align(
        rail_side_mount_plate,
        y_axis_profile,
        side_alignment.opposite.stack_alignment,
    )
    rail_side_mount_plate = align(
        rail_side_mount_plate,
        y_axis_profile,
        front_back_alignment,
    )

    frame_side_mount_plate = create_filleted_box(
        y_axis_rail_carrier_bracket_mount_plate_length,
        y_axis_rail_carrier_bracket_mount_plate_thickness,
        2 * profile_size[2],
        y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, side_alignment, Alignment.TOP],
    )
    frame_side_mount_plate = align(
        frame_side_mount_plate,
        y_axis_profile,
        Alignment.CENTER,
        axes=[0],
    )
    frame_side_mount_plate = align(
        frame_side_mount_plate,
        y_axis_profile,
        side_alignment.opposite.stack_alignment,
    )
    frame_side_mount_plate = align(
        frame_side_mount_plate,
        y_axis_profile,
        front_back_alignment,
    )
    frame_side_mount_plate = align(
        frame_side_mount_plate,
        frame_front_back_profile,
        Alignment.TOP,
    )

    frame_front_back_profile_size = get_bounding_box_size(frame_front_back_profile)
    top_mount_plate_depth = (
        frame_front_back_profile_size[1]
        + y_axis_rail_carrier_bracket_mount_plate_thickness
    )
    top_mount_plate_fillet_radius = (
        y_axis_rail_carrier_bracket_mount_plate_fillet_radius
    )

    top_mount_plate = create_filleted_box(
        y_axis_rail_carrier_bracket_mount_plate_length + profile_size[0],
        top_mount_plate_depth,
        y_axis_rail_carrier_bracket_mount_plate_thickness,
        top_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, front_back_alignment.opposite],
    )
    top_mount_plate = align(
        top_mount_plate, frame_side_mount_plate, side_alignment.opposite
    )
    top_mount_plate = align(
        top_mount_plate,
        frame_front_back_profile,
        front_back_alignment,
    )
    top_mount_plate = align(
        top_mount_plate,
        frame_front_back_profile,
        Alignment.STACK_TOP,
    )

    top_end_plate = create_cylinder(
        y_axis_rail_carrier_bracket_outer_diameter / 2,
        BIG_THING,
        angle=90,
    )

    top_end_plate = rotate(
        rotation_angle_map[(side_alignment, front_back_alignment)] - 90
    )(top_end_plate)

    top_end_plate = align(
        top_end_plate,
        y_axis_profile,
        Alignment.CENTER,
        axes=[0],
    )
    top_end_plate = align(
        top_end_plate,
        y_axis_profile,
        Alignment.STACK_TOP,
    )
    top_end_plate = align(
        top_end_plate,
        y_axis_profile,
        (
            Alignment.STACK_LEFT
            if side_alignment == Alignment.RIGHT
            else Alignment.STACK_RIGHT
        ),
    )
    top_end_plate = align(
        top_end_plate,
        y_axis_profile,
        front_back_alignment,
    )
    top_end_plate = translate(
        -side_alignment.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
        -front_back_alignment.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
        0,
    )(top_end_plate)

    top_end_plate_profile_cover = create_filleted_box(
        profile_size[0] + y_axis_rail_carrier_bracket_mount_plate_thickness,
        y_axis_rail_carrier_bracket_outer_diameter / 2
        + y_axis_rail_carrier_bracket_mount_plate_thickness,
        BIG_THING,
        fillet_radius=top_mount_plate_fillet_radius,
        no_fillets_at=[
            Alignment.BOTTOM,
            Alignment.TOP,
            front_back_alignment,
            side_alignment.opposite,
        ],
    )
    top_end_plate_profile_cover = align(
        top_end_plate_profile_cover,
        top_end_plate,
        Alignment.CENTER,
    )
    top_end_plate_profile_cover = align(
        top_end_plate_profile_cover,
        top_end_plate,
        front_back_alignment.opposite,
    )

    top_end_plate_profile_cover = align(
        top_end_plate_profile_cover,
        top_end_plate,
        side_alignment.stack_alignment,
    )
    top_end_plate_profile_cover = align(
        top_end_plate_profile_cover, top_end_plate, Alignment.BOTTOM
    )
    top_end_plate = top_end_plate.fuse(top_end_plate_profile_cover)

    top_end_plate_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    top_end_plate_cutter = align(
        top_end_plate_cutter,
        top_end_plate,
        Alignment.CENTER,
    )
    top_end_plate_cutter = align(
        top_end_plate_cutter,
        top_mount_plate,
        Alignment.STACK_TOP,
    )
    top_end_plate = top_end_plate.cut(top_end_plate_cutter)

    bracket = rail_carrier_bracket_ring_profile.fuse(rail_side_mount_plate)
    bracket = bracket.fuse(frame_side_mount_plate)
    bracket = bracket.fuse(top_mount_plate)
    bracket = bracket.fuse(top_end_plate)

    screw_alignments = [
        [
            (side_alignment.opposite.edge_alignment, bracket, None, 0),
            (Alignment.CENTER, frame_front_back_profile, [1], None),
        ],
        [
            (side_alignment.edge_alignment, top_end_plate, None, 0),
            (Alignment.CENTER, frame_front_back_profile, [1], None),
        ],
        [
            (side_alignment.edge_alignment, bracket, None, 0),
            (front_back_alignment.opposite.edge_alignment, top_end_plate, None, 1),
        ],
    ]
    top_bracket_screws = []
    for screw_alignment_list in screw_alignments:
        screw = create_cylinder_screw(
            y_axis_rail_carrier_bracket_mount_screw_size,
            y_axis_rail_carrier_bracket_mount_screw_length,
        )

        for (
            alignment_enum,
            target_part,
            target_axes,
            movement_axis,
        ) in screw_alignment_list:
            screw = align(
                screw,
                target_part,
                alignment_enum,
                target_axes,
            )
            if movement_axis is not None:
                screw = translate(
                    *[
                        (
                            -y_axis_rail_carrier_bracket_mount_screw_inset
                            * alignment_enum.sign
                            if axis_index == movement_axis
                            else 0
                        )
                        for axis_index in range(3)
                    ]
                )(screw)

        screw = align(screw, bracket, Alignment.TOP)
        screw = translate(
            0,
            0,
            MScrew.from_size(
                y_axis_rail_carrier_bracket_mount_screw_size
            ).cylinder_head_height,
        )(screw)

        top_bracket_screws.append(screw)

    for screw in top_bracket_screws:
        screw_cutter = create_cylinder(
            MScrew.from_size(
                y_axis_rail_carrier_bracket_mount_screw_size
            ).clearance_hole_loose
            / 2,
            BIG_THING,
        )
        screw_cutter = align(screw_cutter, screw, Alignment.CENTER)
        bracket = bracket.cut(screw_cutter)

    profile_screw = create_cylinder_screw(
        y_axis_rail_carrier_bracket_mount_screw_size,
        y_axis_rail_carrier_bracket_mount_screw_length,
    )
    profile_screw = rotate(-side_alignment.sign * 90, axis=(0, 1, 0))(profile_screw)
    profile_screw = align(profile_screw, rail_side_mount_plate, Alignment.CENTER)
    profile_screw = align(
        profile_screw,
        rail_side_mount_plate,
        front_back_alignment.opposite.edge_alignment,
    )
    profile_screw = align(profile_screw, rail_side_mount_plate, side_alignment.opposite)
    profile_screw = translate(
        -side_alignment.sign
        * MScrew.from_size(
            y_axis_rail_carrier_bracket_mount_screw_size
        ).cylinder_head_height,
        y_axis_rail_carrier_bracket_mount_screw_inset * front_back_alignment.sign,
        0,
    )(profile_screw)

    profile_screw_cutter = create_cylinder(
        MScrew.from_size(
            y_axis_rail_carrier_bracket_mount_screw_size
        ).clearance_hole_loose
        / 2,
        BIG_THING,
    )
    profile_screw_cutter = rotate(90, axis=(0, 1, 0))(profile_screw_cutter)
    profile_screw_cutter = align(profile_screw_cutter, profile_screw, Alignment.CENTER)
    bracket = bracket.cut(profile_screw_cutter)

    frame_screw = create_cylinder_screw(
        y_axis_rail_carrier_bracket_mount_screw_size,
        y_axis_rail_carrier_bracket_mount_screw_length,
    )
    frame_screw = rotate(front_back_alignment.sign * 90, axis=(1, 0, 0))(frame_screw)
    frame_screw = align(frame_screw, frame_side_mount_plate, Alignment.CENTER)
    frame_screw = align(
        frame_screw, frame_side_mount_plate, side_alignment.opposite.edge_alignment
    )
    frame_screw = align(
        frame_screw, frame_side_mount_plate, front_back_alignment.opposite
    )

    frame_screw = translate(
        side_alignment.sign* y_axis_rail_carrier_bracket_mount_screw_inset,
        -front_back_alignment.sign
        * MScrew.from_size(
            y_axis_rail_carrier_bracket_mount_screw_size
        ).cylinder_head_height,
        0,
    )(frame_screw)

    frame_screw_cutter = create_cylinder(
        MScrew.from_size(
            y_axis_rail_carrier_bracket_mount_screw_size
        ).clearance_hole_loose
        / 2,
        BIG_THING,
    )
    frame_screw_cutter = rotate(-front_back_alignment.sign * 90, axis=(1, 0, 0))(
        frame_screw_cutter
    )
    frame_screw_cutter = align(frame_screw_cutter, frame_screw, Alignment.CENTER)
    bracket = bracket.cut(frame_screw_cutter)

    return (
        bracket,
        rail_side_mount_plate,
        top_mount_plate,
        top_bracket_screws,
        profile_screw,
        frame_screw,
    )


def create_y_axis_rail_carrier_brackets_assembly(
    *,
    frame,
    y_axis,
    y_axis_rail_carrier_bracket_outer_diameter,
    y_axis_rail_carrier_bracket_height,
    y_axis_rail_carrier_bracket_profile_width,
    y_axis_rail_carrier_bracket_profile_wall,
    y_axis_rail_carrier_bracket_mount_plate_thickness,
    y_axis_rail_carrier_bracket_mount_plate_length,
    y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
    y_axis_rail_carrier_bracket_mount_screw_length,
    y_axis_rail_carrier_bracket_mount_screw_size,
    y_axis_rail_carrier_bracket_mount_screw_inset,
):
    """Create the rail carrier brackets against the already placed y-axis."""

    leader = PartCollector()
    follower_names = []
    followers = []
    non_production_parts = []
    non_production_names = []

    for side_name, side_alignment in (
        ("left", Alignment.LEFT),
        ("right", Alignment.RIGHT),
    ):
        y_axis_profile = y_axis.get_named_non_production_part(f"profile_{side_name}")

        for front_back_alignment in (Alignment.FRONT, Alignment.BACK):
            frame_front_back_profile = frame.get_named_non_production_part(
                f"frame_profile_{front_back_alignment.name.lower()}"
            )
            (
                bracket,
                rail_side_mount_plate,
                top_mount_plate,
                bracket_screws,
                profile_screw,
                frame_screw,
            ) = _create_bracket_for_corner(
                frame_front_back_profile=frame_front_back_profile,
                y_axis_profile=y_axis_profile,
                side_alignment=side_alignment,
                front_back_alignment=front_back_alignment,
                y_axis_rail_carrier_bracket_outer_diameter=y_axis_rail_carrier_bracket_outer_diameter,
                y_axis_rail_carrier_bracket_height=y_axis_rail_carrier_bracket_height,
                y_axis_rail_carrier_bracket_profile_width=y_axis_rail_carrier_bracket_profile_width,
                y_axis_rail_carrier_bracket_profile_wall=y_axis_rail_carrier_bracket_profile_wall,
                y_axis_rail_carrier_bracket_mount_plate_thickness=y_axis_rail_carrier_bracket_mount_plate_thickness,
                y_axis_rail_carrier_bracket_mount_plate_length=y_axis_rail_carrier_bracket_mount_plate_length,
                y_axis_rail_carrier_bracket_mount_plate_fillet_radius=y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
                y_axis_rail_carrier_bracket_mount_screw_length=y_axis_rail_carrier_bracket_mount_screw_length,
                y_axis_rail_carrier_bracket_mount_screw_size=y_axis_rail_carrier_bracket_mount_screw_size,
                y_axis_rail_carrier_bracket_mount_screw_inset=y_axis_rail_carrier_bracket_mount_screw_inset,
            )
            leader = leader.fuse(bracket)
            followers.append(bracket)
            follower_names.append(
                f"rail_carrier_bracket_{side_name}_{front_back_alignment.name.lower()}"
            )
            non_production_parts.append(rail_side_mount_plate)
            non_production_names.append(
                f"profile_side_mount_plate_{side_name}_{front_back_alignment.name.lower()}"
            )
            for screw_index, screw in enumerate(bracket_screws):
                non_production_parts.append(screw)
                non_production_names.append(
                    f"screw_{side_name}_{front_back_alignment.name.lower()}_{screw_index}"
                )

            non_production_parts.append(profile_screw)
            non_production_names.append(
                f"profile_screw_{side_name}_{front_back_alignment.name.lower()}"
            )
            non_production_parts.append(frame_screw)
            non_production_names.append(
                f"frame_screw_{side_name}_{front_back_alignment.name.lower()}"
            )

    return LeaderFollowersCuttersPart(
        leader=leader,
        followers=followers,
        non_production_parts=non_production_parts,
        follower_names=follower_names,
        non_production_names=non_production_names,
    )
