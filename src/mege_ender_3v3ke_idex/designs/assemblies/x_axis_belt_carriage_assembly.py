"""Standalone x-axis belt carriage assembly."""

import logging

from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


top_mount_flange_thickness = 4


def create_x_axis_belt_carriage_assembly(
    *,
    carriage,
    axis_profile,
    sprite_extruder,
    tool_heead_mount_machined,
    tool_head_mount_base_plate_height,
    tool_head_mount_belt_clamp_base_thickness,
    tool_head_mount_belt_clamp_length,
    tool_head_mount_belt_clamp_thickness,
    tool_head_mount_belt_clamp_y_offset,
    tool_head_mount_belt_deflector_belt_clearance,
    tool_head_mount_belt_deflector_cage_thickness,
    tool_head_mount_belt_deflector_into_profile_distance,
    tool_head_mount_belt_deflector_thickness,
    tool_head_mount_belt_path_cutter_clearance,
    tool_head_mount_carriage_mount_plate_fillet_radius,
    tool_head_mount_carriage_mount_plate_thickness,
    tool_head_mount_carriage_mount_plate_width,
    tool_head_mount_clamp_base_cutter_clearance,
    tool_head_mount_plate_carriage_clearance,
    tool_head_mount_side_plate_depth,
    tool_head_mount_side_plate_height,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_y_extension,
    x_axis_belt_carriage_belt_clamp_clearance,
    x_axis_belt_carriage_fan_side_clamp_gap,
    x_axis_belt_carriage_bridge_mount_screw_size,
    x_axis_belt_carriage_bridge_depth,
    x_axis_belt_carriage_bridge_thickness,
    x_axis_belt_carriage_bridge_web_height,
    x_axis_belt_carriage_mount_eye_fillet_radius,
    x_axis_belt_carriage_mount_eye_hole_diameter,
    x_axis_belt_carriage_mount_eye_length,
    x_axis_belt_carriage_mount_eye_thickness,
    x_axis_belt_carriage_mount_eye_width,
    drive_position,
    BIG_THING,
):
    """Create a standalone x-axis belt carriage assembly."""

    normalized_drive_position = str(drive_position).strip().lower()
    if normalized_drive_position == "bottom":
        drive_alignment = Alignment.BOTTOM
    elif normalized_drive_position == "top":
        drive_alignment = Alignment.TOP
    else:
        raise ValueError(f"Unsupported drive_position '{drive_position}'")

    sprite_extruder_all_fused = sprite_extruder.leaders_followers_fused().fuse(
        sprite_extruder.get_non_production_parts_fused()
    )

    assembly = None

    clamps = []
    cages = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        clamp_lfc = create_gt_belt_clamp(
            base_thicknness=tool_head_mount_belt_clamp_base_thickness,
            clamp_thickness=tool_head_mount_belt_clamp_thickness,
            clamp_length=tool_head_mount_belt_clamp_length,
            screw_size="M3",
            screw_hole_border=1.9,
            teeth_clearance=0.1,
            single_screw=True,
            extra_scew_hole_clearance=0.2,
            use_threaded_inset=True,
        )
        clamp_lfc = rotate(90, axis=(1, 0, 0))(clamp_lfc)
        clamp_lfc = rotate(90)(clamp_lfc)

        if lr == Alignment.RIGHT:
            clamp_lfc = rotate(180)(clamp_lfc)

        clamp_lfc = align(clamp_lfc, sprite_extruder, Alignment.CENTER)
        clamp_lfc = align(
            clamp_lfc,
            axis_profile,
            Alignment.STACK_FRONT,
            stack_gap=tool_head_mount_belt_clamp_y_offset,
        )

        clamp_gap = 5
        if lr == Alignment.LEFT:
            clamp_gap = x_axis_belt_carriage_fan_side_clamp_gap

        if drive_alignment == Alignment.BOTTOM:

            if lr == Alignment.LEFT:
                clamp_gap = 0.3
                part_to_align_to = tool_heead_mount_machined
            else:
                part_to_align_to = sprite_extruder_all_fused

            clamp_lfc = clamp_lfc.aligned_from_follower(
                "clamp",
                part_to_align_to,
                lr.stack_alignment,
                stack_gap=clamp_gap,
            )

        else:

            clamp_lfc = clamp_lfc.aligned_from_follower(
                "clamp",
                tool_heead_mount_machined,
                lr.stack_alignment,
            )

        clamp_lfc = align(clamp_lfc, axis_profile, Alignment.CENTER, axes=[2])

        current_belt_path_cutter = clamp_lfc.get_named_follower("belt_path_cutter")
        current_belt_path_cutter_size = get_bounding_box_size(current_belt_path_cutter)

        belt_deflector_clearance = 0.5

        belt_deflector = create_box(
            tool_head_mount_belt_deflector_thickness,
            BIG_THING,
            current_belt_path_cutter_size[2] - 2 * belt_deflector_clearance,
        )
        belt_deflector = align(
            belt_deflector,
            current_belt_path_cutter,
            Alignment.CENTER,
        )

        clamp_part = clamp_lfc.get_named_follower("clamp")
        base_part = clamp_lfc.leader

        camp_and_base_fused = clamp_part.fuse(base_part)

        belt_deflector = fit_part_between(
            belt_deflector,
            cut_normal=(0, 1, 0),
            limiting_start_part=axis_profile,
            limiting_end_part=camp_and_base_fused,
            start_gap=-tool_head_mount_belt_deflector_into_profile_distance,
            end_gap=x_axis_belt_carriage_belt_clamp_clearance,
        )

        belt_deflector = align(
            belt_deflector,
            clamp_lfc.get_named_follower("belt_path_cutter"),
            lr.stack_alignment,
        )

        base_and_clamp_fused = base_part.fuse(clamp_part)
        all_clamp_size = get_bounding_box_size(base_and_clamp_fused)

        bdc_x_size = all_clamp_size[0]
        bdc_y_size = tool_head_mount_belt_deflector_cage_thickness
        bdc_z_size = all_clamp_size[2]

        belt_deflector_cage = create_box(bdc_x_size, bdc_y_size, bdc_z_size)
        belt_deflector_cage = align(
            belt_deflector_cage,
            base_and_clamp_fused,
            Alignment.CENTER,
        )
        belt_deflector_cage = align(
            belt_deflector_cage, belt_deflector, Alignment.FRONT
        )
        belt_deflector_cage = belt_deflector_cage.cut(current_belt_path_cutter)

        belt_deflector_connector = create_box(
            tool_head_mount_belt_clamp_thickness,
            x_axis_belt_carriage_belt_clamp_clearance,
            all_clamp_size[2],
        )

        belt_deflector_connector = align(
            belt_deflector_connector,
            clamp_part,
            Alignment.CENTER,
        )
        belt_deflector_connector = align(
            belt_deflector_connector, clamp_part, lr.opposite
        )
        belt_deflector_connector = align(
            belt_deflector_connector,
            clamp_part,
            Alignment.STACK_BACK,
        )

        clamps.append(clamp_part)

        cages = cages.fuse(belt_deflector_cage)
        clamp_part = clamp_part.fuse(belt_deflector)
        clamp_part = clamp_part.fuse(belt_deflector_cage)
        clamp_part = clamp_part.fuse(belt_deflector_connector)

        clamp_lfc_new = LeaderFollowersCuttersPart(clamp_part)

        clamp_lfc_new.add_named_follower(clamp_lfc.leader, "base")
        for name, npp in clamp_lfc.get_named_non_production_part_items():
            clamp_lfc_new.add_named_non_production_part(npp, name)

        clamp_lfc_new = clamp_lfc_new.prefixed_copy(f"belt_clamp_{lr.name.lower()}")

        if assembly is None:
            assembly = clamp_lfc_new
        else:
            assembly = assembly.fuse(clamp_lfc_new)

    clamps_fused = clamps[0].fuse(clamps[1])
    clamps_fused_size = get_bounding_box_size(clamps_fused)
    bridge_height = clamps_fused_size[2]

    bridge_thickness = x_axis_belt_carriage_bridge_thickness
    if drive_alignment == Alignment.BOTTOM:
        bridge_height -= 3
        bridge_thickness *= 0.75

    bridge = create_box(BIG_THING, bridge_thickness, bridge_height)

    bridge = align(bridge, clamps_fused, Alignment.CENTER)
    bridge = align(bridge, cages, Alignment.BACK)
    bridge = fit_part_between(
        bridge,
        cut_normal=(1, 0, 0),
        limiting_start_part=clamps[0],
        limiting_end_part=clamps[1],
    )
    bridge = align(bridge, clamps_fused, Alignment.BOTTOM)

    bridge_size = get_bounding_box_size(bridge)

    bridge_reinforcer = None
    if drive_alignment == Alignment.BOTTOM:

        bridge_reinforcer = create_box(
            bridge_size[0] - 8,
            bridge_thickness,
            4.5,
        )
        bridge_reinforcer = align(bridge_reinforcer, bridge, Alignment.RIGHT)
        bridge_reinforcer = align(
            bridge_reinforcer, belt_deflector, Alignment.CENTER, axes=[2]
        )

        bridge_reinforcer = align(bridge_reinforcer, bridge, Alignment.STACK_BACK)

    assembly = assembly.fuse(bridge)
    if bridge_reinforcer is not None:
        assembly = assembly.fuse(bridge_reinforcer)

    if drive_alignment == Alignment.TOP:
        mount_flange_width = 2.5 * x_axis_belt_carriage_bridge_thickness
        for lr in [Alignment.LEFT, Alignment.RIGHT]:
            mount_flange_back = create_box(
                mount_flange_width,
                x_axis_belt_carriage_bridge_thickness,
                bridge_height,
            )
            mount_flange_back = align(mount_flange_back, bridge, Alignment.BACK)
            mount_flange_back = align(
                mount_flange_back, tool_heead_mount_machined, Alignment.STACK_TOP
            )
            mount_flange_back = align(mount_flange_back, tool_heead_mount_machined, lr)

            # mount_flange_back = fit_part_between(
            #     mount_flange_back,
            #     cut_normal=(0, 0, 1),
            #     limiting_start_part=clamp_lfc_new,
            # )

            mount_flange_floor = create_box(
                mount_flange_width,
                20,
                top_mount_flange_thickness,
            )
            mount_flange_floor = align(
                mount_flange_floor, mount_flange_back, Alignment.CENTER
            )
            mount_flange_floor = align(
                mount_flange_floor, mount_flange_back, Alignment.BOTTOM
            )
            mount_flange_floor = align(
                mount_flange_floor, mount_flange_back, Alignment.BACK
            )

            mount_flange_floor = tool_heead_mount_machined.use_as_cutter_on(
                mount_flange_floor
            )

            assembly = assembly.fuse(mount_flange_back).fuse(mount_flange_floor)

    if drive_alignment == Alignment.BOTTOM:

        right_clamp = clamps[1]
        clamp_drill = create_cylinder(
            MScrew.from_size("M3").clearance_hole_loose / 2,
            BIG_THING,
            direction=(0, 1, 0),
        )
        clamp_drill = align(clamp_drill, right_clamp, Alignment.CENTER)

        threaded_inset_holder_radius = 3.5

        threaded_inset_holder = create_cylinder(
            threaded_inset_holder_radius, bridge_thickness, direction=(0, 1, 0)
        )
        threaded_inset_holder = align(
            threaded_inset_holder, clamp_drill, Alignment.CENTER
        )
        threaded_inset_holder = align(
            threaded_inset_holder, bridge, Alignment.STACK_BACK
        )
        assembly = assembly.fuse(threaded_inset_holder)

        assembly = assembly.cut(clamp_drill)
        assembly.add_named_cutter(clamp_drill, "right_clamp_hole_drill")

        thread_inset = create_thread_inset_assembly(
            size="M3",
            thickness=6,
            extra_radius=0.01,
            clearance_type="close",
        )
        thread_inset = rotate(-90, axis=(1, 0, 0))(thread_inset)

        thread_inset = align(thread_inset, clamp_drill, Alignment.CENTER)
        thread_inset = align(thread_inset, threaded_inset_holder, Alignment.BACK)

        assembly = thread_inset.use_as_cutter_on(assembly)
        thread_inset = thread_inset.prefixed_copy("right_clamp_thread_inset")
        assembly = assembly.merge_except_leader(thread_inset)

        left_bridge_drill = create_cylinder(
            MScrew.from_size("M3").clearance_hole_loose / 2,
            BIG_THING,
            direction=(0, 1, 0),
        )
        left_bridge_drill = align(left_bridge_drill, bridge, Alignment.CENTER)

        left_bridge_drill = align(left_bridge_drill, right_clamp, Alignment.CENTER,axes=[2])

        

        left_bridge_drill = align(
            left_bridge_drill, tool_heead_mount_machined, Alignment.LEFT
        )

        left_bridge_drill = translate(2, 0, 0)(left_bridge_drill)

        left_threaded_inset_holder = create_cylinder(
            threaded_inset_holder_radius, bridge_thickness, direction=(0, 1, 0)
        )
        left_threaded_inset_holder = align(
            left_threaded_inset_holder, left_bridge_drill, Alignment.CENTER
        )
        left_threaded_inset_holder = align(
            left_threaded_inset_holder, bridge, Alignment.STACK_BACK
        )
        assembly = assembly.fuse(left_threaded_inset_holder)

        assembly = assembly.cut(left_bridge_drill)
        assembly.add_named_cutter(left_bridge_drill, "left_bridge_hole_drill")

        left_thread_inset = create_thread_inset_assembly(
            size="M3",
            thickness=6,
            extra_radius=0.01,
            clearance_type="close",
        )
        left_thread_inset = rotate(-90, axis=(1, 0, 0))(left_thread_inset)

        left_thread_inset = align(
            left_thread_inset, left_bridge_drill, Alignment.CENTER
        )
        left_thread_inset = align(
            left_thread_inset, left_threaded_inset_holder, Alignment.BACK
        )

        assembly = left_thread_inset.use_as_cutter_on(assembly)
        left_thread_inset = left_thread_inset.prefixed_copy("left_bridge_thread_inset")
        assembly = assembly.merge_except_leader(left_thread_inset)

    return assembly
