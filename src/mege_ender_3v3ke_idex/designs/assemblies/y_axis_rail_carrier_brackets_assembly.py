"""Rail carrier brackets assembled against the placed y-axis."""

from mege_ender_3v3ke_idex.designs.hollow_profiles import create_hollow_profile_ring
from shellforgepy.simple import *


def _translation_delta(source_part, target_part):
    source_center = get_bounding_box_center(source_part)
    target_center = get_bounding_box_center(target_part)
    return tuple(
        target - source for source, target in zip(source_center, target_center)
    )


def _create_rail_carrier_bracket(
    *,
    y_axis_rail_carrier_bracket_outer_diameter,
    y_axis_rail_carrier_bracket_profile_width,
    y_axis_rail_carrier_bracket_height,
    y_axis_rail_carrier_bracket_profile_wall,
):
    return create_hollow_profile_ring(
        y_axis_rail_carrier_bracket_outer_diameter,
        profile_depth=y_axis_rail_carrier_bracket_profile_width,
        profile_height=y_axis_rail_carrier_bracket_height,
        wall_thickness=y_axis_rail_carrier_bracket_profile_wall,
        angle=90,
    )


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
):
    rotation_angle_map = {
        (Alignment.LEFT, Alignment.FRONT): 90,
        (Alignment.LEFT, Alignment.BACK): 0,
        (Alignment.RIGHT, Alignment.FRONT): 180,
        (Alignment.RIGHT, Alignment.BACK): -90,
    }

    rail_carrier_bracket = _create_rail_carrier_bracket(
        y_axis_rail_carrier_bracket_outer_diameter=y_axis_rail_carrier_bracket_outer_diameter,
        y_axis_rail_carrier_bracket_profile_width=y_axis_rail_carrier_bracket_profile_width,
        y_axis_rail_carrier_bracket_height=y_axis_rail_carrier_bracket_height,
        y_axis_rail_carrier_bracket_profile_wall=y_axis_rail_carrier_bracket_profile_wall,
    )
    rail_carrier_bracket = rotate(
        rotation_angle_map[(side_alignment, front_back_alignment)] - 90
    )(rail_carrier_bracket)
    rail_carrier_bracket = align(
        rail_carrier_bracket,
        y_axis_profile,
        Alignment.CENTER,
        axes=[0],
    )
    rail_carrier_bracket = align(
        rail_carrier_bracket,
        y_axis_profile,
        Alignment.TOP,
    )
    rail_carrier_bracket = align(
        rail_carrier_bracket,
        y_axis_profile,
        (
            Alignment.STACK_LEFT
            if side_alignment == Alignment.RIGHT
            else Alignment.STACK_RIGHT
        ),
    )
    rail_carrier_bracket = align(
        rail_carrier_bracket,
        y_axis_profile,
        front_back_alignment,
    )
    rail_carrier_bracket = translate(
        -side_alignment.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
        -front_back_alignment.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
        y_axis_rail_carrier_bracket_mount_plate_thickness,
    )(rail_carrier_bracket)

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

    target_rail_side_mount_plate = align(
        rail_side_mount_plate,
        y_axis_profile,
        Alignment.CENTER,
        axes=[2],
    )
    vertical_shift = _translation_delta(
        rail_side_mount_plate, target_rail_side_mount_plate
    )

    rail_carrier_bracket = translate(*vertical_shift)(rail_carrier_bracket)
    rail_side_mount_plate = translate(*vertical_shift)(rail_side_mount_plate)

    frame_side_mount_plate = create_filleted_box(
        y_axis_rail_carrier_bracket_mount_plate_length,
        y_axis_rail_carrier_bracket_mount_plate_thickness,
        2 * profile_size[2],
        y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.BACK, side_alignment],
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
        Alignment.TOP,
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
    frame_side_mount_plate = translate(*vertical_shift)(frame_side_mount_plate)

    frame_front_back_profile_size = get_bounding_box_size(frame_front_back_profile)
    top_mount_plate_depth = frame_front_back_profile_size[1]
    top_mount_plate_fillet_radius = min(
        y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
        min(
            y_axis_rail_carrier_bracket_mount_plate_thickness,
            top_mount_plate_depth,
        )
        / 2
        - 0.01,
    )

    top_mount_plate = create_filleted_box(
        y_axis_rail_carrier_bracket_mount_plate_length,
        top_mount_plate_depth,
        y_axis_rail_carrier_bracket_mount_plate_thickness,
        top_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    top_mount_plate = align(
        top_mount_plate,
        frame_side_mount_plate,
        Alignment.CENTER,
        axes=[0],
    )
    top_mount_plate = align(
        top_mount_plate,
        frame_front_back_profile,
        Alignment.CENTER,
        axes=[1],
    )
    top_mount_plate = align(
        top_mount_plate,
        frame_front_back_profile,
        Alignment.STACK_TOP,
    )

    bracket = rail_carrier_bracket.fuse(rail_side_mount_plate)
    bracket = bracket.fuse(frame_side_mount_plate)
    bracket = bracket.fuse(top_mount_plate)
    return bracket, rail_side_mount_plate, top_mount_plate


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
            bracket, rail_side_mount_plate, top_mount_plate = (
                _create_bracket_for_corner(
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
                )
            )
            leader = leader.fuse(bracket)
            followers.append(bracket)
            follower_names.append(
                f"rail_carrier_bracket_{side_name}_{front_back_alignment.name.lower()}"
            )
            non_production_parts.extend([rail_side_mount_plate, top_mount_plate])
            non_production_names.extend(
                [
                    f"profile_side_mount_plate_{side_name}_{front_back_alignment.name.lower()}",
                    f"top_mount_plate_{side_name}_{front_back_alignment.name.lower()}",
                ]
            )

    return LeaderFollowersCuttersPart(
        leader=leader,
        followers=followers,
        non_production_parts=non_production_parts,
        follower_names=follower_names,
        non_production_names=non_production_names,
    )
