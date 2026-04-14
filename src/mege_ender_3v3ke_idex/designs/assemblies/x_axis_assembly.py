"""Declarative x-axis assembly."""

import copy

import numpy as np
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler
from mege_ender_3v3ke_idex.designs.idler_cage import create_idler_cage
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.simple import *


def _named_only(part):
    cleaned = LeaderFollowersCuttersPart(
        leader=part.leader,
        additional_data=dict(part.additional_data),
    )
    for name, follower in part.get_named_follower_items():
        cleaned.add_named_follower(follower, name)
    for name, cutter in part.get_named_cutter_items():
        cleaned.add_named_cutter(cutter, name)
    for name, non_production_part in part.get_named_non_production_part_items():
        cleaned.add_named_non_production_part(non_production_part, name)
    return cleaned


def _get_leader_part(part_like):
    return part_like.leader if hasattr(part_like, "leader") else part_like


def _create_idler_endcap(
    *,
    profile,
    with_tensioner,
    side,
    endcap_top_bottom,
    x_axis_profile_pitch,
    toolhead_path_width,
    toolhead_path_extended_width,
    toolhead_path_extended_gap,
    endcap_vertical_coupler_size,
    endcap_vertical_coupler_screw_size,
    endcap_vertical_coupler_screw_length,
    endcap_axle_screw_length,
    endcap_belt_clearance,
    endcap_belt_vertical_clearance,
    endcap_belt_width,
    endcap_clearance,
    endcap_idler_clearance,
    endcap_idler_tooth_count,
    endcap_mount_fillet_radius,
    endcap_mount_screw_size,
    endcap_outer_box_back_wall,
    endcap_profile_clearance,
    endcap_profile_groove_depth,
    endcap_profile_overlap,
    endcap_side_hole_boundary,
    endcap_side_hole_size,
    endcap_tensioner_cage_back_wall,
    endcap_tensioner_cage_clearance,
    endcap_tensioner_length,
    endcap_tensioner_outer_box_bottom_cage_clearance,
    endcap_tensioner_outer_box_bottom_thickness,
    endcap_tensioner_screw_size,
    endcap_tensioner_travel,
    endcap_top_bottom_wall,
    endcap_wall,
    idler_cage_back_wall,
    idler_cage_wall,
    big_thing,
):
    profile_size = get_bounding_box_size(profile)

    idler = create_gt2_idler(num_teeth=endcap_idler_tooth_count)
    idler_size = get_bounding_box_size(idler)

    target_cage_length = 1.3 * (idler_size[0] + 2 * endcap_clearance)
    if with_tensioner:
        target_cage_length += endcap_tensioner_length
    cage_overlength = target_cage_length - idler_size[0]

    cage_height = (
        profile_size[2]
        + 2 * endcap_top_bottom_wall
        - endcap_tensioner_outer_box_bottom_cage_clearance
        - endcap_tensioner_outer_box_bottom_thickness
    )
    outer_box_height = (
        cage_height
        + endcap_tensioner_outer_box_bottom_cage_clearance
        + endcap_tensioner_outer_box_bottom_thickness
    )

    if with_tensioner:
        cage_width_override = profile_size[1]
    else:
        cage_width_override = profile_size[1] + 2 * endcap_wall + 2 * endcap_clearance

    cage = create_idler_cage(
        cage_back_wall=(
            idler_cage_back_wall
            if not with_tensioner
            else endcap_tensioner_cage_back_wall
        ),
        cage_front_wall_thickness=endcap_wall
        + (endcap_profile_overlap if not with_tensioner else 0),
        cage_wall=idler_cage_wall,
        cage_height=cage_height,
        cage_overlength=cage_overlength,
        idler_tooth_count=endcap_idler_tooth_count,
        idler_clearance=endcap_idler_clearance,
        with_tensioner=with_tensioner,
        tensioner_screw_size=endcap_tensioner_screw_size,
        axle_screw_length=endcap_axle_screw_length,
        belt_clearance=endcap_belt_clearance,
        cage_width_override=cage_width_override,
    )

    if side != Alignment.LEFT:
        cage = rotate(180)(cage)

    cage = align(cage, profile, Alignment.CENTER)
    if with_tensioner:
        cage = align(
            cage,
            profile,
            side.stack_alignment,
            stack_gap=endcap_wall + endcap_tensioner_cage_clearance,
        )
    else:
        cage = align(
            cage,
            profile,
            side.stack_alignment,
            stack_gap=-endcap_profile_overlap,
        )

    profile_cutter = create_box(
        big_thing,
        profile_size[1] + endcap_profile_clearance,
        profile_size[2] + endcap_profile_clearance,
    )
    profile_cutter = align(profile_cutter, profile, Alignment.CENTER)
    profile_cutter = align(profile_cutter, profile, side)

    tool_head_path = create_box(profile_size[0], big_thing, toolhead_path_width)
    tool_head_path = align(tool_head_path, profile, Alignment.CENTER)
    tool_head_path = align(
        tool_head_path,
        profile,
        (
            Alignment.STACK_FRONT
            if endcap_top_bottom == Alignment.BOTTOM
            else Alignment.STACK_BACK
        ),
    )
    extended_toolhead_path = create_box(
        profile_size[0],
        big_thing,
        toolhead_path_extended_width,
    )
    extended_toolhead_path = align(extended_toolhead_path, profile, Alignment.CENTER)
    extended_toolhead_path = align(
        extended_toolhead_path,
        profile,
        (
            Alignment.STACK_FRONT
            if endcap_top_bottom == Alignment.BOTTOM
            else Alignment.STACK_BACK
        ),
        stack_gap=toolhead_path_extended_gap,
    )
    tool_head_path = tool_head_path.fuse(extended_toolhead_path)

    cage = cage.cut(profile_cutter)

    mount_eye = create_filleted_box(
        profile_size[1] * 0.6,
        profile_size[1],
        endcap_top_bottom_wall
        + endcap_profile_clearance
        + endcap_tensioner_outer_box_bottom_thickness
        + endcap_tensioner_outer_box_bottom_cage_clearance,
        fillet_radius=endcap_mount_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side],
    )
    mount_eye_screw_hole_cutter = create_cylinder(
        MScrew.from_size(endcap_mount_screw_size).clearance_hole_normal / 2,
        big_thing,
    )
    mount_eye_screw_hole_cutter = align(
        mount_eye_screw_hole_cutter,
        mount_eye,
        Alignment.CENTER,
    )
    mount_eye = mount_eye.cut(mount_eye_screw_hole_cutter)

    if with_tensioner:
        cage_size = get_bounding_box_size(cage)

        outer_box = create_box(
            cage_size[0]
            + endcap_profile_overlap
            + endcap_wall
            + endcap_outer_box_back_wall
            + 2 * endcap_tensioner_cage_clearance
            + endcap_tensioner_travel,
            cage_size[1] + 2 * endcap_wall,
            outer_box_height,
        )
        outer_box = align(outer_box, cage, Alignment.CENTER)
        outer_box = align(outer_box, cage, Alignment.TOP)
        outer_box = align(
            outer_box,
            profile,
            side.stack_alignment,
            stack_gap=-endcap_profile_overlap,
        )

        cage_cutter = create_box(
            cage_size[0]
            + 2 * endcap_tensioner_cage_clearance
            + endcap_tensioner_travel,
            cage_size[1] + 2 * endcap_tensioner_cage_clearance,
            big_thing,
        )
        cage_cutter = align(cage_cutter, cage, Alignment.CENTER)
        cage_cutter = align(cage_cutter, cage, side.opposite)
        cage_cutter = align(cage_cutter, outer_box, Alignment.BOTTOM)
        cage_cutter = translate(
            -side.sign * endcap_tensioner_cage_clearance,
            0,
            endcap_tensioner_outer_box_bottom_thickness,
        )(cage_cutter)
        outer_box = outer_box.cut(cage_cutter)

        profile_cutter = create_box(
            profile_size[0] + endcap_profile_clearance,
            profile_size[1] + 2 * endcap_profile_clearance,
            profile_size[2] + 2 * endcap_profile_clearance,
        )
        profile_cutter = align(profile_cutter, profile, Alignment.CENTER)
        outer_box = outer_box.cut(profile_cutter)

        side_hole_size_diagonal = np.sqrt(2) * endcap_side_hole_size
        side_hole_pitch = side_hole_size_diagonal * 1.5
        outer_bounding_box_size = get_bounding_box_size(outer_box)

        num_x_side_holes = int(
            (outer_bounding_box_size[0] - 2 * endcap_side_hole_boundary)
            / side_hole_pitch
        )
        num_z_side_holes = int(
            (outer_bounding_box_size[2] - 2 * endcap_side_hole_boundary)
            / side_hole_pitch
        )

        side_hole_drills = PartCollector()
        for ix in range(num_x_side_holes):
            for iz in range(num_z_side_holes):
                side_hole_drill = create_box(
                    endcap_side_hole_size,
                    big_thing,
                    endcap_side_hole_size,
                )
                side_hole_drill = rotate(45, axis=(0, 1, 0))(side_hole_drill)
                side_hole_drill = align(side_hole_drill, outer_box, Alignment.CENTER)
                side_hole_drill = translate(
                    ix * side_hole_pitch,
                    0,
                    iz * side_hole_pitch,
                )(side_hole_drill)
                side_hole_drills = side_hole_drills.fuse(side_hole_drill)

        side_hole_drills = align(side_hole_drills, outer_box, Alignment.CENTER)
        outer_box = outer_box.cut(side_hole_drills)

        belt_side_cutters = PartCollector()
        for fb in [Alignment.FRONT, Alignment.BACK]:
            belt_clearance_cutter = create_box(
                big_thing,
                endcap_profile_groove_depth,
                endcap_belt_width + 2 * endcap_belt_vertical_clearance,
            )
            belt_clearance_cutter = align(
                belt_clearance_cutter,
                profile,
                Alignment.CENTER,
            )
            belt_clearance_cutter = align(belt_clearance_cutter, profile, fb)
            belt_clearance_cutter = align(
                belt_clearance_cutter,
                cage,
                side.opposite.stack_alignment,
            )
            outer_box = outer_box.cut(belt_clearance_cutter)

            belt_side_clearance_cutter = create_pyramid_stump(
                endcap_profile_overlap,
                endcap_profile_overlap,
                endcap_belt_width * 2,
                endcap_belt_width,
                endcap_belt_width * 0.8,
            )
            belt_side_clearance_cutter = rotate(-90 * fb.sign, axis=(1, 0, 0))(
                belt_side_clearance_cutter
            )
            belt_side_clearance_cutter = align(
                belt_side_clearance_cutter,
                outer_box,
                Alignment.CENTER,
            )
            belt_side_clearance_cutter = align(
                belt_side_clearance_cutter,
                outer_box,
                side.opposite,
            )
            outer_box_size = get_bounding_box_size(outer_box)
            wall_at_profile = (
                outer_box_size[1] - profile_size[1]
            ) / 2 + endcap_profile_clearance
            belt_side_clearance_cutter = align(
                belt_side_clearance_cutter,
                outer_box,
                fb.stack_alignment,
                stack_gap=-wall_at_profile,
            )
            belt_side_cutters = belt_side_cutters.fuse(belt_side_clearance_cutter)

        outer_box = outer_box.cut(belt_side_cutters)

        tensioner_screw_part = cage.get_non_production_part_by_name("tensioner_screw")
        tensioner_screw_part = align(tensioner_screw_part, outer_box, side)
        tensioner_screw_part = translate(
            side.sign
            * MScrew.from_size(endcap_tensioner_screw_size).cylinder_head_height,
            0,
            0,
        )(tensioner_screw_part)

        tensioner_screw_hole_cutter = create_cylinder(
            MScrew.from_size(endcap_tensioner_screw_size).clearance_hole_normal / 2,
            big_thing,
        )
        tensioner_screw_hole_cutter = rotate(90, axis=(0, 1, 0))(
            tensioner_screw_hole_cutter
        )
        tensioner_screw_hole_cutter = align(
            tensioner_screw_hole_cutter,
            tensioner_screw_part,
            Alignment.CENTER,
        )
        tensioner_screw_hole_cutter = align(
            tensioner_screw_hole_cutter,
            outer_box,
            side.stack_alignment,
            stack_gap=-2 * endcap_wall,
        )
        outer_box = outer_box.cut(tensioner_screw_hole_cutter)

        mount_eye = align(mount_eye, outer_box, Alignment.CENTER)
        mount_eye = align(mount_eye, outer_box, Alignment.BOTTOM)
        mount_eye = align(
            mount_eye,
            outer_box,
            side.opposite.stack_alignment,
        )
        mount_eye = mount_eye.cut(profile_cutter)
        outer_box = outer_box.fuse(mount_eye)
        outer_box = outer_box.cut(tool_head_path)

        retval = LeaderFollowersCuttersPart(leader=outer_box)
        retval.add_named_follower(cage.leader, "endcap_idler_cage")
    else:
        mount_eye = align(mount_eye, cage, Alignment.CENTER)
        mount_eye = align(mount_eye, cage, Alignment.BOTTOM)
        mount_eye = align(
            mount_eye,
            cage,
            side.opposite.stack_alignment,
        )
        mount_eye = mount_eye.cut(profile_cutter)
        cage = cage.fuse(mount_eye)
        cage = cage.cut(tool_head_path)
        retval = LeaderFollowersCuttersPart(leader=cage.leader)
        retval.add_named_follower(cage.leader, "endcap_idler_cage")

    retval.add_named_follower(cage.get_non_production_part_by_name("idler"), "idler")
    retval.add_named_non_production_part(
        cage.get_non_production_part_by_name("axle"),
        "axle",
    )
    retval.add_named_non_production_part(
        cage.get_non_production_part_by_name("axle_threaded_inset"),
        "axle_threaded_inset",
    )
    if with_tensioner:
        retval.add_named_non_production_part(tensioner_screw_part, "tensioner_screw")
        retval.add_named_non_production_part(
            cage.get_non_production_part_by_name("tensioner_nut"),
            "tensioner_nut",
        )

    endcap_vertical_couplers = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        endcap_size = get_bounding_box_size(retval)
        profile_size = get_bounding_box_size(profile)

        endcap_vertical_coupler = create_box(
            endcap_vertical_coupler_size,
            endcap_vertical_coupler_size,
            endcap_size[2],
        )
        endcap_vertical_coupler = align(
            endcap_vertical_coupler,
            retval,
            Alignment.CENTER,
        )
        endcap_vertical_coupler = align(
            endcap_vertical_coupler,
            retval,
            fb.stack_alignment,
        )
        endcap_vertical_coupler = align(
            endcap_vertical_coupler,
            retval,
            Alignment.BOTTOM,
        )
        endcap_vertical_coupler = align(endcap_vertical_coupler, retval, side)

        endcap_vertical_coupler_connector = create_box(
            endcap_vertical_coupler_size,
            endcap_vertical_coupler_size,
            x_axis_profile_pitch / 2 - profile_size[2] / 2,
        )
        endcap_vertical_coupler_connector = align(
            endcap_vertical_coupler_connector,
            endcap_vertical_coupler,
            Alignment.CENTER,
        )
        endcap_vertical_coupler_connector = align(
            endcap_vertical_coupler_connector,
            profile,
            Alignment.STACK_TOP,
        )
        endcap_vertical_coupler = endcap_vertical_coupler.fuse(
            endcap_vertical_coupler_connector
        )

        endcap_vertical_coupler_bbox_size = get_bounding_box_size(
            endcap_vertical_coupler
        )
        endcap_vertical_coupler_total_representative = create_box(
            endcap_vertical_coupler_bbox_size[0],
            endcap_vertical_coupler_bbox_size[1],
            endcap_vertical_coupler_bbox_size[2] * 2,
        )
        endcap_vertical_coupler_total_representative = align(
            endcap_vertical_coupler_total_representative,
            endcap_vertical_coupler,
            Alignment.CENTER,
        )
        endcap_vertical_coupler_total_representative = align(
            endcap_vertical_coupler_total_representative,
            endcap_vertical_coupler,
            Alignment.BOTTOM,
        )

        screw_mount_assembly = create_screw_mount_assembly(
            endcap_vertical_coupler_total_representative,
            screw_size=endcap_vertical_coupler_screw_size,
            screw_length=endcap_vertical_coupler_screw_length,
            screw_direction=(
                Alignment.TOP
                if endcap_top_bottom == Alignment.BOTTOM
                else Alignment.BOTTOM
            ),
            flush_with_top=True,
        )
        endcap_vertical_coupler = screw_mount_assembly.use_as_cutter_on(
            endcap_vertical_coupler
        )

        if endcap_top_bottom == Alignment.TOP:
            npp_name = (
                f"endcap_vertical_coupler_top_{fb.name.lower()}_{side.name.lower()}"
            )
            for (
                screw_npp_name,
                npp,
            ) in screw_mount_assembly.get_named_non_production_part_items():
                retval.add_named_non_production_part(
                    npp,
                    f"{npp_name}_{screw_npp_name}",
                )

        endcap_vertical_couplers = endcap_vertical_couplers.fuse(
            endcap_vertical_coupler
        )

    retval = retval.fuse(endcap_vertical_couplers)

    if endcap_top_bottom == Alignment.TOP:
        center = get_bounding_box_center(cage)
        retval = rotate(180, axis=(1, 0, 0), center=center)(retval)
        retval.additional_data["endcap_is_rotated"] = True

    return retval


def create_x_axis_assembly(
    *,
    x_axis_carriage_stopper_left,
    x_axis_carriage_stopper_right,
    x_axis_profile_pitch,
    x_axis_carriage_stopper_width,
    x_axis_carriage_stopper_thickness,
    x_axis_carriage_stopper_depth,
    x_axis_carriage_stopper_fillet_radius,
    x_axis_carriage_stopper_mount_screw_size,
    x_axis_carriage_stopper_mount_screw_length,
    mount_plate_connector_link_thickness,
    mount_plate_link_width,
    link_flange_depth,
    link_flange_thickness,
    link_screw_size,
    link_screw_length,
    toolhead_path_width,
    toolhead_path_extended_width,
    toolhead_path_extended_gap,
    endcap_vertical_coupler_size,
    endcap_vertical_coupler_screw_size,
    endcap_vertical_coupler_screw_length,
    endcap_axle_screw_length,
    endcap_belt_clearance,
    endcap_belt_vertical_clearance,
    endcap_belt_width,
    endcap_clearance,
    endcap_idler_clearance,
    endcap_idler_tooth_count,
    endcap_mount_fillet_radius,
    endcap_mount_screw_size,
    endcap_outer_box_back_wall,
    endcap_profile_clearance,
    endcap_profile_groove_depth,
    endcap_profile_overlap,
    endcap_side_hole_boundary,
    endcap_side_hole_size,
    endcap_tensioner_cage_back_wall,
    endcap_tensioner_cage_clearance,
    endcap_tensioner_length,
    endcap_tensioner_outer_box_bottom_cage_clearance,
    endcap_tensioner_outer_box_bottom_thickness,
    endcap_tensioner_screw_size,
    endcap_tensioner_travel,
    endcap_top_bottom_wall,
    endcap_wall,
    idler_cage_back_wall,
    idler_cage_wall,
    x_axis_lower_profile,
    x_axis_top_profile,
    x_axis_motor_mount_bottom,
    x_axis_motor_mount_top,
    x_axis_rail,
    x_axis_endstop_left,
    x_axis_endstop_right,
    BIG_THING,
    record_metrics=False,
):
    """Create the x-axis assembly in a canonical local coordinate system."""

    big_thing = BIG_THING
    del record_metrics

    lower_axis_profile = _get_leader_part(x_axis_lower_profile)
    top_axis_profile = _get_leader_part(x_axis_top_profile)
    axis_frame = lower_axis_profile.fuse(top_axis_profile)
    rail_with_carriages = x_axis_rail

    mount_plates = PartCollector()
    mount_plate_connectors = PartCollector()
    final_mount_plates_by_profile_position = {}
    axis_holding_counter_flanges_by_profile_position = {}
    motors_fused_by_profile_position = {}

    non_production_parts = [
        rail_with_carriages.get_follower_part_by_name("carriage_1"),
        rail_with_carriages.get_follower_part_by_name("carriage_2"),
        rail_with_carriages.leader,
        lower_axis_profile,
        top_axis_profile,
    ]
    non_production_names = [
        "carriage_1",
        "carriage_2",
        "rail",
        "lower_axis_profile",
        "top_axis_profile",
    ]
    motor_assemblies_by_profile_position = {
        Alignment.BOTTOM: x_axis_motor_mount_bottom,
        Alignment.TOP: x_axis_motor_mount_top,
    }

    for profile_position in (Alignment.BOTTOM, Alignment.TOP):
        profile_position_name = profile_position.name.lower()
        motor_assembly = motor_assemblies_by_profile_position[profile_position]

        motor_followers_fused = PartCollector()
        for follower in motor_assembly.followers:
            motor_followers_fused = motor_followers_fused.fuse(follower)
        motors_fused_by_profile_position[profile_position] = motor_followers_fused

        for (
            non_production_part_name,
            non_production_part,
        ) in motor_assembly.get_named_non_production_part_items():
            if (
                not non_production_part_name
                or non_production_part_name == "axis_holding_counter_flange"
            ):
                continue
            non_production_parts.append(non_production_part)
            non_production_names.append(
                f"{non_production_part_name}_{profile_position_name}"
            )

        mount_plate_connectors = mount_plate_connectors.fuse(
            motor_assembly.get_follower_part_by_name("mount_plate_connector")
        )

        mount_shield = motor_assembly.get_follower_part_by_name("mount_shield")
        axis_holding_counter_flange = motor_assembly.get_non_production_part_by_name(
            "axis_holding_counter_flange"
        )
        mount_plate = motor_assembly.get_follower_part_by_name("mount_plate")

        mount_plates = mount_plates.fuse(mount_plate)
        axis_holding_counter_flanges_by_profile_position[
            f"axis_holding_counter_flange_{profile_position_name}"
        ] = axis_holding_counter_flange

        final_mount_plates_by_profile_position[profile_position] = (
            motors_fused_by_profile_position[profile_position].fuse(mount_shield)
        )

        non_production_parts.append(
            motor_assembly.get_non_production_part_by_name("idlers")
        )
        non_production_names.append(f"idlers_{profile_position_name}")

    mount_plate_connectors_size = get_bounding_box_size(mount_plate_connectors)
    mount_plate_link = create_box(
        mount_plate_link_width,
        mount_plate_connector_link_thickness,
        mount_plate_connectors_size[2],
    )
    mount_plate_link = align(mount_plate_link, mount_plate_connectors, Alignment.CENTER)
    mount_plate_link = align(mount_plate_link, mount_plate_connectors, Alignment.BACK)

    bevel_size = (mount_plate_connectors_size[2] - 2 * 5) / 2
    mount_plate_link_bevels = PartCollector()
    for direction in (-1, 1):
        mount_plate_link_bevel = create_right_triangle(
            bevel_size,
            bevel_size,
            mount_plate_link_width,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, 0, direction),
            b_normal=(0, -1, 0),
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel,
            mount_plate_link,
            Alignment.CENTER,
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel,
            mount_plate_link,
            Alignment.STACK_FRONT,
        )
        mount_plate_link_bevel = align(
            mount_plate_link_bevel,
            mount_plate_link,
            Alignment.STACK_TOP if direction == 1 else Alignment.STACK_BOTTOM,
            stack_gap=-5 - bevel_size,
        )
        mount_plate_link_bevels = mount_plate_link_bevels.fuse(mount_plate_link_bevel)

    mount_plate_link = mount_plate_link.fuse(mount_plate_link_bevels)

    mount_plate_link_flange = create_filleted_box(
        mount_plate_link_width,
        link_flange_depth,
        2 * link_flange_thickness,
        fillet_radius=1,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, Alignment.FRONT],
    )
    mount_plate_link_flange = align(
        mount_plate_link_flange,
        mount_plate_link,
        Alignment.CENTER,
    )
    mount_plate_link_flange = align(
        mount_plate_link_flange,
        mount_plate_link,
        Alignment.STACK_BACK,
    )

    link_screw_hole_cutters = PartCollector()
    link_screws = []
    for index, side in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        del index
        link_screw = create_cylinder_screw(link_screw_size, length=link_screw_length)
        link_screw = align(link_screw, mount_plate_link_flange, Alignment.CENTER)
        link_screw = align(link_screw, mount_plate_link_flange, Alignment.TOP)
        link_screw = translate(
            side.sign * mount_plate_link_width / 4,
            0,
            MScrew.from_size(link_screw_size).cylinder_head_height,
        )(link_screw)
        link_screws.append(link_screw)

        link_screw_hole_cutter = create_cylinder(
            MScrew.from_size(link_screw_size).clearance_hole_normal / 2,
            big_thing,
        )
        link_screw_hole_cutter = align(
            link_screw_hole_cutter,
            link_screw,
            Alignment.CENTER,
        )
        link_screw_hole_cutters = link_screw_hole_cutters.fuse(link_screw_hole_cutter)

    mount_plate_link_flange = mount_plate_link_flange.cut(link_screw_hole_cutters)
    mount_plate_link = mount_plate_link.fuse(mount_plate_link_flange)

    mount_plate_link_cutter = create_box(big_thing, big_thing, big_thing)
    mount_plate_link_cutter = align(
        mount_plate_link_cutter,
        axis_frame,
        Alignment.CENTER,
    )
    mount_plate_link_cutters = cut_in_two(
        mount_plate_link_cutter,
        cut_point=get_bounding_box_center(mount_plate_link_cutter),
        cut_normal=(0, 0, 1),
    )

    # TODO: cut_in_two returns (top, bottom) here; mapping index order to BOTTOM/TOP is implicit.
    for index, profile_position in enumerate([Alignment.BOTTOM, Alignment.TOP]):
        current_mount_plate_link = mount_plate_link.cut(mount_plate_link_cutters[index])
        final_mount_plates_by_profile_position[profile_position] = (
            final_mount_plates_by_profile_position[profile_position].fuse(
                current_mount_plate_link
            )
        )

    mount_plates = mount_plates.fuse(mount_plate_link)

    retval = LeaderFollowersCuttersPart(
        leader=mount_plates,
        non_production_parts=non_production_parts,
        non_production_names=non_production_names,
    )

    for index, link_screw in enumerate(link_screws):
        retval.add_named_non_production_part(link_screw, f"link_screw_{index + 1}")

    for name, part in axis_holding_counter_flanges_by_profile_position.items():
        retval.add_named_follower(part, name)

    for profile_position in (Alignment.BOTTOM, Alignment.TOP):
        retval.add_named_follower(
            final_mount_plates_by_profile_position[profile_position],
            f"mount_plate_{profile_position.name.lower()}",
        )

    for profile_position in (Alignment.BOTTOM, Alignment.TOP):
        profile_to_align_to = (
            lower_axis_profile
            if profile_position == Alignment.BOTTOM
            else top_axis_profile
        )
        top_bottom_string = profile_position.name.lower()

        for endcap_side in (Alignment.LEFT, Alignment.RIGHT):
            with_tensioner = endcap_side == Alignment.RIGHT
            endcap_top_bottom = profile_position
            endcap_side_str = endcap_side.name.lower()

            endcap = _create_idler_endcap(
                profile=profile_to_align_to,
                with_tensioner=with_tensioner,
                side=endcap_side,
                endcap_top_bottom=endcap_top_bottom,
                x_axis_profile_pitch=x_axis_profile_pitch,
                toolhead_path_width=toolhead_path_width,
                toolhead_path_extended_width=toolhead_path_extended_width,
                toolhead_path_extended_gap=toolhead_path_extended_gap,
                endcap_vertical_coupler_size=endcap_vertical_coupler_size,
                endcap_vertical_coupler_screw_size=endcap_vertical_coupler_screw_size,
                endcap_vertical_coupler_screw_length=endcap_vertical_coupler_screw_length,
                endcap_axle_screw_length=endcap_axle_screw_length,
                endcap_belt_clearance=endcap_belt_clearance,
                endcap_belt_vertical_clearance=endcap_belt_vertical_clearance,
                endcap_belt_width=endcap_belt_width,
                endcap_clearance=endcap_clearance,
                endcap_idler_clearance=endcap_idler_clearance,
                endcap_idler_tooth_count=endcap_idler_tooth_count,
                endcap_mount_fillet_radius=endcap_mount_fillet_radius,
                endcap_mount_screw_size=endcap_mount_screw_size,
                endcap_outer_box_back_wall=endcap_outer_box_back_wall,
                endcap_profile_clearance=endcap_profile_clearance,
                endcap_profile_groove_depth=endcap_profile_groove_depth,
                endcap_profile_overlap=endcap_profile_overlap,
                endcap_side_hole_boundary=endcap_side_hole_boundary,
                endcap_side_hole_size=endcap_side_hole_size,
                endcap_tensioner_cage_back_wall=endcap_tensioner_cage_back_wall,
                endcap_tensioner_cage_clearance=endcap_tensioner_cage_clearance,
                endcap_tensioner_length=endcap_tensioner_length,
                endcap_tensioner_outer_box_bottom_cage_clearance=endcap_tensioner_outer_box_bottom_cage_clearance,
                endcap_tensioner_outer_box_bottom_thickness=endcap_tensioner_outer_box_bottom_thickness,
                endcap_tensioner_screw_size=endcap_tensioner_screw_size,
                endcap_tensioner_travel=endcap_tensioner_travel,
                endcap_top_bottom_wall=endcap_top_bottom_wall,
                endcap_wall=endcap_wall,
                idler_cage_back_wall=idler_cage_back_wall,
                idler_cage_wall=idler_cage_wall,
                big_thing=big_thing,
            )

            idler_name = (
                f"x_axis_idler_endcap_{top_bottom_string}_{endcap_side_str}_idler"
            )
            retval.add_named_non_production_part(
                endcap.get_follower_part_by_name("idler"),
                idler_name,
            )

            cage_name = None
            if with_tensioner:
                cage_name = (
                    f"x_axis_idler_endcap_{top_bottom_string}_{endcap_side_str}_cage"
                )
                retval.add_named_follower(
                    endcap.get_follower_part_by_name("endcap_idler_cage"),
                    cage_name,
                )

            endcap_name = f"x_axis_idler_endcap_{top_bottom_string}_{endcap_side_str}"
            retval.add_named_follower(endcap.leader, endcap_name)

            if endcap.additional_data.get("endcap_is_rotated", False):
                part_names = [idler_name, endcap_name]
                if cage_name is not None:
                    part_names.append(cage_name)
                for name in part_names:
                    retval.additional_data[name] = {"is_rotated": True}

            if cage_name is not None:
                current_additional_data = retval.additional_data.get(cage_name, {})
                current_additional_data.update(
                    {
                        "prod_rotation_angle": (
                            -90 * endcap_side.sign * profile_position.sign
                        ),
                        "prod_rotation_axis": (0, 1, 0),
                    }
                )
                retval.additional_data[cage_name] = current_additional_data

            for (
                npp_name_in_endcap,
                endcap_npp,
            ) in endcap.get_named_non_production_part_items():
                retval.add_named_non_production_part(
                    endcap_npp,
                    f"{endcap_name}_{npp_name_in_endcap}",
                )

    for side_name, side_alignment, endstop in (
        ("left", Alignment.LEFT, x_axis_endstop_left),
        ("right", Alignment.RIGHT, x_axis_endstop_right),
    ):
        stopper_template = (
            x_axis_carriage_stopper_left
            if side_alignment == Alignment.LEFT
            else x_axis_carriage_stopper_right
        )
        stopper = copy.deepcopy(stopper_template)
        stopper = align(stopper, rail_with_carriages, Alignment.CENTER, axes=[0, 1])
        stopper = align(stopper, rail_with_carriages, Alignment.BOTTOM)
        stopper = align(stopper, rail_with_carriages, side_alignment.stack_alignment)

        retval.add_named_follower(
            stopper.leader,
            f"rail_end_stopper_{side_name}",
        )
        retval.add_named_non_production_part(
            stopper.get_non_production_part_by_name("mount_screw"),
            f"rail_end_stopper_mount_screw_{side_name}",
        )
        retval.add_named_follower(
            _get_leader_part(endstop),
            f"x_axis_endstop_{side_name}",
        )
        retval.add_named_non_production_part(
            endstop.get_non_production_part_by_name("mount_screw"),
            f"endstop_mount_screw_{side_name}",
        )
        retval.add_named_non_production_part(
            endstop.get_non_production_part_by_name("board"),
            f"endstop_board_{side_name}",
        )

    return _named_only(retval)
