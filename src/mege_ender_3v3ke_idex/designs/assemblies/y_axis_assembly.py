"""Declarative y-axis assembly."""

import logging

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.hollow_profiles import create_hollow_profile_ring
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    record_length_metric,
    record_weight_metric,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_rail_with_carriages
from mege_ender_3v3ke_idex.designs.print_bed import Y_AXIS_MOVING_MASS_ASSEMBLY_ID
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _record_y_axis_carriage_weight_metrics(y_axis):
    carriage_volume_mm3 = 0.0
    for name, part in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue
        carriage_volume_mm3 += get_volume(part)

    if carriage_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.STEEL,
            carriage_volume_mm3,
            part_id="mgn12ca_carriages",
        )


def _get_y_axis_carriages_fused(y_axis):
    y_axis_carriages = PartCollector()
    for name, follower in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue
        y_axis_carriages = y_axis_carriages.fuse(follower)
    return y_axis_carriages


def _align_y_axis_to_frame_and_undercarriage(y_axis, frame, print_bed_undercarriage):
    y_axis = align(y_axis, frame, Alignment.CENTER, axes=[0, 1])
    y_axis_profile_left = y_axis.get_non_production_part_by_name("profile_left")
    y_axis = align_translation(
        y_axis_profile_left,
        frame,
        Alignment.CENTER,
        axes=[2],
    )(y_axis)

    y_axis_carriages = _get_y_axis_carriages_fused(y_axis)
    undercarriage_bb = get_bounding_box(print_bed_undercarriage)
    y_axis_carriages_bb = get_bounding_box(y_axis_carriages)
    y_axis_drop_mm = y_axis_carriages_bb[1][2] - undercarriage_bb[0][2]

    _logger.info(
        "Dropping y_axis by %.3f mm so the print bed undercarriage seats on the Y carriages",
        y_axis_drop_mm,
    )
    return translate(0, 0, -y_axis_drop_mm)(y_axis)


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


def create_y_axis_assembly(
    *,
    frame,
    print_bed_undercarriage,
    y_axis_rail_spacing,
    y_axis_rail_length,
    y_axis_profile_length,
    y_axis_carriage_spacing,
    mgn_12ca_carriage_length,
    y_axis_rail_carrier_bracket_outer_diameter,
    y_axis_rail_carrier_bracket_height,
    y_axis_rail_carrier_bracket_profile_width,
    y_axis_rail_carrier_bracket_profile_wall,
    y_axis_rail_carrier_bracket_mount_plate_thickness,
    y_axis_rail_carrier_bracket_mount_plate_length,
    y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
    record_metrics=False,
    context=None,
):
    """Create the y-axis assembly aligned against the frame and undercarriage."""

    del context

    rails = []
    for side_sign in (-1, 1):
        rail_side_name = "left" if side_sign == -1 else "right"

        if record_metrics:
            record_length_metric(
                "extrusion_profile",
                ExtrusionProfileType.PROFILE_2020.value,
                f"y_axis_profile_{rail_side_name}",
                y_axis_profile_length,
            )

        profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020,
            length_mm=y_axis_profile_length,
        )
        profile = rotate(90, axis=(1, 0, 0))(profile)
        profile = align(profile, None, Alignment.CENTER)
        profile = translate(side_sign * y_axis_rail_spacing / 2, 0, 0)(profile)

        if record_metrics:
            record_length_metric(
                "linear_rail",
                "MGN12",
                f"y_axis_rail_{rail_side_name}",
                y_axis_rail_length,
            )

        rail = create_mgn12ca_rail_with_carriages(
            y_axis_rail_length,
            carriage_offsets=[
                -y_axis_rail_length / 2 + mgn_12ca_carriage_length / 2,
                -y_axis_rail_length / 2
                + y_axis_carriage_spacing
                + mgn_12ca_carriage_length / 2,
            ],
            carriage_names=["carriage_front", "carriage_back"],
        )
        rail = rotate(90)(rail)
        rail = rail.prefixed_copy(f"rail_{rail_side_name}")
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_front",
            f"carriage_front_carriage_{rail_side_name}",
        )
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_back",
            f"carriage_back_carriage_{rail_side_name}",
        )
        rail = align(rail, profile, Alignment.CENTER)
        rail = align(rail, profile, Alignment.STACK_TOP)
        rail.add_named_non_production_part(profile, f"profile_{rail_side_name}")

        lr = Alignment.LEFT if side_sign == -1 else Alignment.RIGHT
        for fb in [Alignment.FRONT, Alignment.BACK]:
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
            rail_carrier_bracket = rotate(rotation_angle_map[(lr, fb)] - 90)(
                rail_carrier_bracket
            )
            rail_carrier_bracket = align(
                rail_carrier_bracket,
                profile,
                Alignment.CENTER,
            )
            rail_carrier_bracket = align(
                rail_carrier_bracket,
                profile,
                Alignment.TOP,
            )
            rail_carrier_bracket = align(
                rail_carrier_bracket,
                profile,
                Alignment.STACK_LEFT if side_sign == 1 else Alignment.STACK_RIGHT,
            )
            rail_carrier_bracket = align(rail_carrier_bracket, profile, fb)
            rail_carrier_bracket = translate(
                -lr.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
                -fb.sign * y_axis_rail_carrier_bracket_mount_plate_thickness,
                y_axis_rail_carrier_bracket_mount_plate_thickness,
            )(rail_carrier_bracket)

            profile_size = get_bounding_box_size(profile)

            rail_side_mount_plate = create_filleted_box(
                y_axis_rail_carrier_bracket_mount_plate_thickness,
                y_axis_rail_carrier_bracket_mount_plate_length,
                profile_size[2],
                y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
                no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, fb],
            )
            rail_side_mount_plate = align(
                rail_side_mount_plate,
                profile,
                Alignment.CENTER,
            )
            rail_side_mount_plate = align(
                rail_side_mount_plate,
                profile,
                Alignment.TOP,
            )
            rail_side_mount_plate = align(
                rail_side_mount_plate,
                profile,
                lr.opposite.stack_alignment,
            )
            rail_side_mount_plate = align(rail_side_mount_plate, profile, fb)
            rail_carrier_bracket = rail_carrier_bracket.fuse(rail_side_mount_plate)

            frame_side_mount_plate = create_filleted_box(
                y_axis_rail_carrier_bracket_mount_plate_length,
                y_axis_rail_carrier_bracket_mount_plate_thickness,
                2 * profile_size[2],
                y_axis_rail_carrier_bracket_mount_plate_fillet_radius,
                no_fillets_at=[Alignment.FRONT, Alignment.BACK, lr],
            )
            frame_side_mount_plate = align(
                frame_side_mount_plate,
                profile,
                Alignment.CENTER,
            )
            frame_side_mount_plate = align(
                frame_side_mount_plate,
                profile,
                Alignment.TOP,
            )
            frame_side_mount_plate = align(
                frame_side_mount_plate,
                profile,
                lr.opposite.stack_alignment,
            )
            frame_side_mount_plate = align(frame_side_mount_plate, profile, fb)
            rail_carrier_bracket = rail_carrier_bracket.fuse(frame_side_mount_plate)

            rail.add_named_non_production_part(
                rail_carrier_bracket,
                f"rail_carrier_bracket_{rail_side_name}_{fb.name.lower()}",
            )

        rails.append(rail)

    y_axis = rails[0].fuse(rails[1])
    y_axis = _align_y_axis_to_frame_and_undercarriage(
        y_axis,
        frame,
        print_bed_undercarriage,
    )

    if record_metrics:
        _record_y_axis_carriage_weight_metrics(y_axis)

    return y_axis
