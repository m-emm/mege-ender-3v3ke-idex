"""Declarative x-axis assembly."""

import numpy as np
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.endstop_holder import create_endstop_holder
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler
from mege_ender_3v3ke_idex.designs.idler_cage import create_idler_cage
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_rail_with_carriages,
    mgn_12h_carriage_length,
)
from mege_ender_3v3ke_idex.designs.motor_mount import create_motor_stack
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_screw_mount_assembly,
)
from shellforgepy.metrics import record_length_metric
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


def _create_groove_holder(
    *,
    screw_size,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    big_thing,
):
    mount_screw_cutter = create_cylinder(
        MScrew.from_size(screw_size).clearance_hole_normal / 2,
        big_thing,
    )

    groove_holder = create_pyramid_stump(
        endstop_holder_mount_plate_width,
        endstop_holder_mount_plate_width,
        endstop_holder_groove_holder_bottom_width,
        endstop_holder_groove_holder_top_width,
        endstop_holder_groove_holder_height,
    )

    groove_holder_hole_cutter = create_cylinder(
        MScrew.from_size(screw_size).core_hole / 2 - 0.1,
        big_thing,
    )
    groove_holder_hole_cutter = align(
        groove_holder_hole_cutter,
        groove_holder,
        Alignment.CENTER,
    )
    groove_holder = groove_holder.cut(groove_holder_hole_cutter)

    mount_screw_cutter = align(
        mount_screw_cutter,
        groove_holder,
        Alignment.CENTER,
    )

    groove_holder_larger_hole_cutter = align(
        mount_screw_cutter,
        groove_holder,
        Alignment.STACK_TOP,
        stack_gap=endstop_holder_groove_holder_height / 3,
    )
    groove_holder = groove_holder.cut(groove_holder_larger_hole_cutter)

    slit_cutter = create_box(
        big_thing,
        endstop_holder_groove_holder_slit,
        big_thing,
    )
    slit_cutter = align(slit_cutter, groove_holder, Alignment.CENTER)
    groove_holder = groove_holder.cut(slit_cutter)

    retval = LeaderFollowersCuttersPart(leader=groove_holder)
    retval.add_named_cutter(mount_screw_cutter, "mount_screw_cutter")
    return retval


def _create_carriage_end_rail_stopper(
    *,
    carriage_end_rail_stopper_length,
    carriage_end_rail_stopper_depth,
    carriage_end_rail_stopper_thickness,
    carriage_end_rail_stopper_fillet_radius,
    endstop_holder_mount_screw_size,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    big_thing,
):
    stopper = create_filleted_box(
        carriage_end_rail_stopper_length,
        carriage_end_rail_stopper_depth,
        carriage_end_rail_stopper_thickness,
        fillet_radius=carriage_end_rail_stopper_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    groove_holder = _create_groove_holder(
        screw_size=endstop_holder_mount_screw_size,
        endstop_holder_mount_plate_width=endstop_holder_mount_plate_width,
        endstop_holder_groove_holder_bottom_width=endstop_holder_groove_holder_bottom_width,
        endstop_holder_groove_holder_top_width=endstop_holder_groove_holder_top_width,
        endstop_holder_groove_holder_height=endstop_holder_groove_holder_height,
        endstop_holder_groove_holder_slit=endstop_holder_groove_holder_slit,
        big_thing=big_thing,
    )
    groove_holder = align(groove_holder, stopper, Alignment.CENTER)
    groove_holder = align(groove_holder, stopper, Alignment.STACK_BOTTOM)

    stopper = groove_holder.use_as_cutter_on(stopper)

    retval = LeaderFollowersCuttersPart(stopper)
    retval.add_named_follower(groove_holder.leader, "groove_holder")
    retval.add_named_cutter(
        groove_holder.get_cutter_part_by_name("mount_screw_cutter"),
        "mount_screw_cutter",
    )
    return retval


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
    x_axis_profile_length,
    x_axis_profile_pitch,
    x_axis_rail_length,
    mount_plate_connector_link_thickness,
    mount_plate_link_width,
    link_flange_depth,
    link_flange_thickness,
    link_screw_size,
    link_screw_length,
    carriage_end_clearance,
    carriage_end_rail_stopper_length,
    carriage_end_rail_stopper_thickness,
    carriage_end_rail_stopper_depth,
    carriage_end_rail_stopper_fillet_radius,
    carriage_end_rail_connector_thickness,
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
    endstop_holder_mount_screw_size,
    endstop_holder_mount_plate_width,
    endstop_holder_groove_holder_bottom_width,
    endstop_holder_groove_holder_top_width,
    endstop_holder_groove_holder_height,
    endstop_holder_groove_holder_slit,
    endstop_holder_stack_gap,
    endstop_holder_y_offset,
    record_metrics=False,
    context=None,
):
    """Create the x-axis assembly in a canonical local coordinate system."""

    big_thing = (context or {}).get("BIG_THING", 500)
    carriage_offset = (
        x_axis_rail_length / 2 - mgn_12h_carriage_length / 2 - carriage_end_clearance
    )

    if record_metrics:
        record_length_metric(
            "extrusion_profile",
            ExtrusionProfileType.PROFILE_2020.value,
            "x_axis_lower_profile",
            x_axis_profile_length,
        )

    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020,
        length_mm=x_axis_profile_length,
    )
    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    if record_metrics:
        record_length_metric(
            "extrusion_profile",
            ExtrusionProfileType.PROFILE_2020.value,
            "x_axis_top_profile",
            x_axis_profile_length,
        )

    top_axis_profile = translate(0, 0, x_axis_profile_pitch)(lower_axis_profile)
    axis_frame = lower_axis_profile.fuse(top_axis_profile)

    if record_metrics:
        record_length_metric("linear_rail", "MGN12", "x_axis_rail", x_axis_rail_length)

    rail_with_carriages = create_mgn12h_rail_with_carriages(
        length_mm=x_axis_rail_length,
        carriage_offsets=[-carriage_offset, carriage_offset],
    )
    rail_with_carriages = align(
        rail_with_carriages,
        lower_axis_profile,
        Alignment.CENTER,
        axes=[0, 1],
    )
    rail_with_carriages = align(
        rail_with_carriages,
        lower_axis_profile,
        Alignment.STACK_TOP,
    )

    mount_plates = PartCollector()
    mount_plate_connectors = PartCollector()
    final_mount_plates_by_side = {}
    axis_holding_counter_flanges = {}
    counter_flange_screws_by_side = {}
    motors_fused_by_side = {}

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

    for side in (Alignment.LEFT, Alignment.RIGHT):
        motor_assembly = create_motor_stack(
            side,
            lower_axis_profile,
            top_axis_profile,
        )

        motor_followers_fused = PartCollector()
        for follower in motor_assembly.followers:
            motor_followers_fused = motor_followers_fused.fuse(follower)
        motors_fused_by_side[side] = motor_followers_fused

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
                f"{non_production_part_name}_{side.name.lower()}"
            )

        mount_plate_connectors = mount_plate_connectors.fuse(
            motor_assembly.get_follower_part_by_name("mount_plate_connector")
        )

        mount_shield = motor_assembly.get_follower_part_by_name("mount_shield")
        axis_holding_counter_flange = motor_assembly.get_non_production_part_by_name(
            "axis_holding_counter_flange"
        )
        axis_holding_counter_flange_screws = (
            motor_assembly.get_non_production_part_by_name(
                "axis_holding_counter_flange_screws"
            )
        )
        mount_plate = motor_assembly.get_follower_part_by_name("mount_plate")

        mount_plates = mount_plates.fuse(mount_plate)
        axis_holding_counter_flanges[
            f"axis_holding_counter_flange_{side.name.lower()}"
        ] = axis_holding_counter_flange

        final_mount_plates_by_side[side] = motors_fused_by_side[side].fuse(mount_shield)
        counter_flange_screws_by_side[side] = axis_holding_counter_flange_screws

        non_production_parts.append(
            motor_assembly.get_non_production_part_by_name("idlers")
        )
        non_production_names.append(f"idlers_{side.name.lower()}")

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

    for index, side in enumerate([Alignment.LEFT, Alignment.RIGHT]):
        current_mount_plate_link = mount_plate_link.cut(mount_plate_link_cutters[index])
        final_mount_plates_by_side[side] = final_mount_plates_by_side[side].fuse(
            current_mount_plate_link
        )

    mount_plates = mount_plates.fuse(mount_plate_link)

    retval = LeaderFollowersCuttersPart(
        leader=mount_plates,
        non_production_parts=non_production_parts,
        non_production_names=non_production_names,
    )

    for index, link_screw in enumerate(link_screws):
        retval.add_named_non_production_part(link_screw, f"link_screw_{index + 1}")

    for side in (Alignment.LEFT, Alignment.RIGHT):
        for index, screw in enumerate(counter_flange_screws_by_side[side]):
            retval.add_named_non_production_part(
                screw,
                f"axis_holding_counter_flange_screw_{index + 1}_{side.name.lower()}",
            )

    for name, part in axis_holding_counter_flanges.items():
        retval.add_named_follower(part, name)

    for side in (Alignment.LEFT, Alignment.RIGHT):
        retval.add_named_follower(
            final_mount_plates_by_side[side],
            f"mount_plate_{side.name.lower()}",
        )

    rail_end_stoppers = {}
    for side in (Alignment.LEFT, Alignment.RIGHT):
        profile_to_align_to = (
            lower_axis_profile if side == Alignment.LEFT else top_axis_profile
        )
        top_bottom_string = "lower" if side == Alignment.LEFT else "top"

        for endcap_side in (Alignment.LEFT, Alignment.RIGHT):
            with_tensioner = endcap_side == Alignment.RIGHT
            endcap_top_bottom = (
                Alignment.BOTTOM if side == Alignment.LEFT else Alignment.TOP
            )
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
                        "prod_rotation_angle": -90 * endcap_side.sign * side.sign,
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

            if side == Alignment.LEFT:
                rail_end_stopper = _create_carriage_end_rail_stopper(
                    carriage_end_rail_stopper_length=carriage_end_rail_stopper_length,
                    carriage_end_rail_stopper_depth=carriage_end_rail_stopper_depth,
                    carriage_end_rail_stopper_thickness=carriage_end_rail_stopper_thickness,
                    carriage_end_rail_stopper_fillet_radius=carriage_end_rail_stopper_fillet_radius,
                    endstop_holder_mount_screw_size=endstop_holder_mount_screw_size,
                    endstop_holder_mount_plate_width=endstop_holder_mount_plate_width,
                    endstop_holder_groove_holder_bottom_width=endstop_holder_groove_holder_bottom_width,
                    endstop_holder_groove_holder_top_width=endstop_holder_groove_holder_top_width,
                    endstop_holder_groove_holder_height=endstop_holder_groove_holder_height,
                    endstop_holder_groove_holder_slit=endstop_holder_groove_holder_slit,
                    big_thing=big_thing,
                )
                rail_end_stopper = align(
                    rail_end_stopper,
                    rail_with_carriages,
                    Alignment.CENTER,
                )
                rail_end_stopper = align(
                    rail_end_stopper,
                    rail_with_carriages,
                    Alignment.BOTTOM,
                )
                rail_end_stopper = align(
                    rail_end_stopper,
                    rail_with_carriages,
                    endcap_side.stack_alignment,
                )

                rail_end_stopper_fused = rail_end_stopper.leader.fuse(
                    rail_end_stopper.get_named_follower("groove_holder")
                )

                endstop_holder = create_endstop_holder()
                endstop_holder = rotate(-endcap_side.sign * 90)(endstop_holder)
                endstop_holder = align(
                    endstop_holder,
                    profile_to_align_to,
                    Alignment.CENTER,
                )
                endstop_holder = align(
                    endstop_holder,
                    rail_end_stopper_fused,
                    Alignment.STACK_TOP,
                )
                endstop_holder = translate(0, endstop_holder_y_offset, 0)(
                    endstop_holder
                )

                endstop_holder_board = endstop_holder.get_non_production_part_by_name(
                    "board"
                )
                endstop_holder_board_aligner = align_translation(
                    endstop_holder_board,
                    rail_with_carriages,
                    endcap_side.stack_alignment,
                    stack_gap=endstop_holder_stack_gap,
                )
                endstop_holder = endstop_holder_board_aligner(endstop_holder)
                retval.add_named_non_production_part(
                    endstop_holder.get_non_production_part_by_name("board"),
                    f"endstop_board_{endcap_side.name.lower()}",
                )

                fused = endstop_holder.leader.fuse(rail_end_stopper_fused)
                fused_size = get_bounding_box_size(fused)
                stopper_size = get_bounding_box_size(rail_end_stopper_fused)
                endstop_holder_size = get_bounding_box_size(endstop_holder)

                connector = create_box(
                    fused_size[0] - endstop_holder_size[0],
                    stopper_size[1],
                    carriage_end_rail_connector_thickness,
                )
                connector = align(connector, rail_end_stopper_fused, Alignment.CENTER)
                connector = align(
                    connector,
                    rail_end_stopper_fused,
                    endcap_side.opposite,
                )
                connector = align(
                    connector,
                    rail_end_stopper_fused,
                    Alignment.STACK_TOP,
                )
                connector = rail_end_stopper.use_as_cutter_on(connector)

                rail_end_stopper_fused = rail_end_stopper_fused.fuse(connector)
                rail_end_stopper_fused = rail_end_stopper_fused.fuse(
                    endstop_holder.leader
                )
                rail_end_stoppers[endcap_side] = rail_end_stopper_fused

    for alignment, rail_end_stopper in rail_end_stoppers.items():
        retval.add_named_follower(
            rail_end_stopper,
            f"rail_end_stopper_{alignment.name.lower()}",
        )

    return _named_only(retval)
