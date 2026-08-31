"""Declarative monolithic z-axis carriage assembly."""

import math

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_creality_threaded_rod_nut,
)
from shellforgepy.simple import *

BRASS_ANGLE_THICKNESS = 1.5
BRASS_ANGLE_OUTER_SIZE = 30
BRASS_ANGLE_WIDTH = 14.2
BRASS_ANGLE_HOLE_DIAMETER = 4.8
BRASS_ANGLE_HOLE_WIDTH_INSET = 6
BRASS_ANGLE_HOLE_OUTER_INSET = 6.5
BRASS_ANGLE_HOLE_OUTER_INSET_2 = 21


def create_brass_angle():
    """Create one brass-angle reference with its two mounting-hole cutters."""

    base = create_box(
        BRASS_ANGLE_WIDTH,
        BRASS_ANGLE_OUTER_SIZE - 2 * BRASS_ANGLE_THICKNESS,
        BRASS_ANGLE_THICKNESS,
    )
    abs_center_offset = BRASS_ANGLE_WIDTH / 2 - BRASS_ANGLE_HOLE_WIDTH_INSET
    center = BRASS_ANGLE_WIDTH / 2

    drills = []
    for x, y in [
        (center - abs_center_offset, BRASS_ANGLE_HOLE_OUTER_INSET),
        (center + abs_center_offset, BRASS_ANGLE_HOLE_OUTER_INSET_2),
    ]:
        drill = create_cylinder(BRASS_ANGLE_HOLE_DIAMETER / 2, 50)
        drill = translate(x, y, -BRASS_ANGLE_THICKNESS / 2)(drill)
        base = base.cut(drill)
        drills.append(drill)

    base = LeaderFollowersCuttersPart(base)
    for index, drill in enumerate(drills):
        base.add_named_cutter(drill, f"brass_angle_hole_drill_{index}")

    back = rotate(90, axis=(1, 0, 0))(base)
    back = align(back, base, Alignment.STACK_BACK, stack_gap=BRASS_ANGLE_THICKNESS)
    back = align(back, base, Alignment.STACK_TOP, stack_gap=BRASS_ANGLE_THICKNESS)
    back = back.prefixed_copy("brass_angle_back")

    retval = base.fuse(back)
    bend = create_ring(
        2 * BRASS_ANGLE_THICKNESS,
        BRASS_ANGLE_THICKNESS,
        BRASS_ANGLE_WIDTH,
        angle=90,
    )
    bend = rotate(90, axis=(0, 1, 0))(bend)
    bend = align(bend, base, Alignment.BOTTOM)
    bend = align(bend, base, Alignment.STACK_BACK)

    return retval.fuse(bend)


def _get_part(part):
    return part.leader if hasattr(part, "leader") else part


def create_z_axis_carriage_assembly(
    *,
    z_axis_profile,
    z_axis_rail,
    z_axis_threaded_rod,
    carriage_z_offset,
    BIG_THING,
    z_axis_carriage_back_height,
    z_axis_carriage_fillet_radius,
    z_axis_carriage_front_depth,
    z_axis_carriage_front_height,
    z_axis_carriage_profile_center_distance,
    z_axis_carriage_threaded_rod_clearance,
    z_axis_carriage_width,
    z_axis_carriage_x_axis_connector_thickness,
    z_axis_creality_nut_base_cut_radius,
    z_axis_creality_nut_base_length,
    z_axis_creality_nut_base_thickness,
    z_axis_creality_nut_base_width,
    z_axis_creality_nut_mount_hole_center_center_distance,
    z_axis_creality_nut_mount_screw_size,
    z_axis_creality_nut_rod_guide_bottom_overstand,
    z_axis_creality_nut_rod_guide_diameter,
    z_axis_creality_nut_rod_guide_height,
    z_axis_creality_nut_threaded_rod_cuide_cutter_clearance,
    z_axis_default_clearance_hole_type,
    z_axis_nut_screw_hole_clearence_type,
    z_axis_threaded_rod_diameter,
    z_axis_x_axis_to_carriage_gap,
):
    """Create one monolithic carriage body around the retained Z hardware."""

    profile = _get_part(z_axis_profile)
    rail = _get_part(z_axis_rail)
    rail_carriages = [
        z_axis_rail.get_follower_part_by_name(name)
        for name in ("bottom_carriage", "top_carriage")
    ]
    threaded_rod = _get_part(z_axis_threaded_rod)

    carriage_front_block = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_front_depth,
        z_axis_carriage_front_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    carriage_front_block = align(
        carriage_front_block,
        rail,
        Alignment.CENTER,
        axes=[0],
    )
    carriage_front_block = align(carriage_front_block, rail, Alignment.BOTTOM)
    carriage_front_block = align(
        carriage_front_block,
        profile,
        Alignment.CENTER,
        axes=[1],
    )
    carriage_front_block = translate(
        0,
        -z_axis_carriage_profile_center_distance,
        0,
    )(carriage_front_block)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_carriage_threaded_rod_clearance,
        z_axis_carriage_front_height + 10,
    )
    threaded_rod_cutter = align(
        threaded_rod_cutter,
        carriage_front_block,
        Alignment.CENTER,
    )
    threaded_rod_cutter = align(
        threaded_rod_cutter,
        threaded_rod,
        Alignment.CENTER,
        axes=[0, 1],
    )

    front_block_center = get_bounding_box_center(carriage_front_block)
    front_block_size = get_bounding_box_size(carriage_front_block)
    bridge_front = (
        front_block_center[1]
        + front_block_size[1] / 2
        - 2 * z_axis_carriage_fillet_radius
    )
    rail_carriage_front_planes = [
        get_bounding_box_center(rail_carriage)[1]
        - get_bounding_box_size(rail_carriage)[1] / 2
        for rail_carriage in rail_carriages
    ]
    if max(rail_carriage_front_planes) - min(rail_carriage_front_planes) > 1e-6:
        raise ValueError("Z-axis MGN12H carriages must share a mounting plane")
    bridge_back = min(rail_carriage_front_planes)
    bridge_depth = bridge_back - bridge_front
    if bridge_depth <= 0:
        raise ValueError(
            "MGN12H carriage must be behind the Z-carriage interface plane"
        )

    carriage_back = create_filleted_box(
        z_axis_carriage_width,
        bridge_depth,
        z_axis_carriage_back_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    carriage_back = align(carriage_back, carriage_front_block, Alignment.CENTER)
    carriage_back = align(carriage_back, carriage_front_block, Alignment.TOP)
    carriage_back_center = get_bounding_box_center(carriage_back)
    carriage_back = translate(
        0,
        (bridge_front + bridge_back) / 2 - carriage_back_center[1],
        0,
    )(carriage_back)

    nut = create_creality_threaded_rod_nut(
        BIG_THING=BIG_THING,
        z_axis_threaded_rod_diameter=z_axis_threaded_rod_diameter,
        z_axis_creality_nut_base_cut_radius=z_axis_creality_nut_base_cut_radius,
        z_axis_creality_nut_base_length=z_axis_creality_nut_base_length,
        z_axis_creality_nut_base_thickness=z_axis_creality_nut_base_thickness,
        z_axis_creality_nut_base_width=z_axis_creality_nut_base_width,
        z_axis_creality_nut_mount_hole_center_center_distance=z_axis_creality_nut_mount_hole_center_center_distance,
        z_axis_creality_nut_mount_screw_size=z_axis_creality_nut_mount_screw_size,
        z_axis_creality_nut_rod_guide_bottom_overstand=z_axis_creality_nut_rod_guide_bottom_overstand,
        z_axis_creality_nut_rod_guide_diameter=z_axis_creality_nut_rod_guide_diameter,
        z_axis_creality_nut_rod_guide_height=z_axis_creality_nut_rod_guide_height,
        threaded_rod_guide_cutter_clearance=z_axis_creality_nut_threaded_rod_cuide_cutter_clearance,
        screw_hole_clearence_type=z_axis_nut_screw_hole_clearence_type,
    )
    nut = rotate(180, axis=(1, 0, 0))(nut)
    nut = align(nut, threaded_rod, Alignment.CENTER)
    nut_raw_base = nut.get_named_non_production_part("raw_base")
    nut_aligner = align_translation(
        nut_raw_base,
        carriage_back,
        Alignment.STACK_BOTTOM,
    )
    nut = nut_aligner(nut)
    carriage_back = nut.use_as_cutter_on(carriage_back)
    carriage_back = carriage_back.cut(threaded_rod_cutter)

    x_axis_mount_screw_size = ExtrusionProfileType.PROFILE_2020.nominal_hardware
    x_axis_mount_screw_hole_diameter = MScrew.from_size(
        x_axis_mount_screw_size
    ).get_clearance_hole_diameter(z_axis_default_clearance_hole_type)
    x_axis_mount_plate_bottom = create_filleted_box(
        z_axis_carriage_width,
        z_axis_x_axis_to_carriage_gap + z_axis_carriage_fillet_radius,
        z_axis_carriage_x_axis_connector_thickness,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_front_block,
        Alignment.CENTER,
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_front_block,
        Alignment.BOTTOM,
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_front_block,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_carriage_fillet_radius,
    )

    carriage_reference = create_filleted_box(
        z_axis_carriage_width,
        z_axis_x_axis_to_carriage_gap + z_axis_carriage_fillet_radius,
        0.01,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    carriage_reference = align(
        carriage_reference,
        x_axis_mount_plate_bottom,
        Alignment.CENTER,
    )
    carriage_reference = align(
        carriage_reference,
        x_axis_mount_plate_bottom,
        Alignment.STACK_TOP,
    )

    mount_screw_hole_drills = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(x_axis_mount_screw_hole_diameter / 2, BIG_THING)
        hole = align(hole, x_axis_mount_plate_bottom, Alignment.CENTER)
        hole = align(hole, x_axis_mount_plate_bottom, Alignment.EDGE_FRONT)
        hole = translate(
            lr.sign * (z_axis_carriage_width / 3),
            ExtrusionProfileType.PROFILE_2020.size_mm[0] / 2,
            0,
        )(hole)
        mount_screw_hole_drills[f"mount_screw_hole_drill_{lr.name.lower()}"] = hole
        x_axis_mount_plate_bottom = x_axis_mount_plate_bottom.cut(hole)

    x_axis_mount_plate_top = create_filleted_box(
        z_axis_carriage_width,
        z_axis_x_axis_to_carriage_gap + z_axis_carriage_fillet_radius,
        z_axis_carriage_x_axis_connector_thickness,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_front_block,
        Alignment.CENTER,
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_front_block,
        Alignment.TOP,
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_front_block,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_carriage_fillet_radius,
    )
    for hole in mount_screw_hole_drills.values():
        x_axis_mount_plate_top = x_axis_mount_plate_top.cut(hole)

    carriage_back_size = get_bounding_box_size(carriage_back)
    enhancement_angle = 48
    relevant_size = carriage_back_size[1] - 5
    enhancement_length = math.sqrt(
        relevant_size**2
        + (math.tan(math.radians(enhancement_angle)) * relevant_size) ** 2
    )
    enhancements = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        enhancement = create_filleted_box(
            1.5 * z_axis_carriage_fillet_radius,
            enhancement_length,
            1.5 * z_axis_carriage_fillet_radius,
            fillet_radius=z_axis_carriage_fillet_radius / 4,
            no_fillets_at=[Alignment.FRONT, Alignment.BACK],
        )
        enhancement = rotate(enhancement_angle, axis=(1, 0, 0))(enhancement)
        enhancement = align(enhancement, carriage_back, Alignment.BACK)
        enhancement = align(enhancement, carriage_back, Alignment.TOP)
        enhancement = align(enhancement, carriage_back, lr)
        enhancement = translate(
            -lr.sign * z_axis_carriage_fillet_radius,
            0,
            0,
        )(enhancement)
        enhancements = enhancements.fuse(enhancement)
    carriage_back = carriage_back.fuse(enhancements)

    carriage_body = carriage_front_block.fuse(carriage_back)
    carriage_body = carriage_body.fuse(x_axis_mount_plate_bottom)
    carriage_body = carriage_body.fuse(x_axis_mount_plate_top)
    retval = LeaderFollowersCuttersPart(leader=carriage_body)

    brass_angle_screw_references = {}
    top_brass_angles_fused = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        brass_angle = create_brass_angle()
        brass_angle = rotate(90, axis=(1, 0, 0))(brass_angle)
        brass_angle = align(brass_angle, carriage_front_block, Alignment.CENTER)
        brass_angle = align(brass_angle, carriage_front_block, Alignment.TOP)
        brass_angle = align(brass_angle, carriage_front_block, Alignment.FRONT)
        brass_angle = align(brass_angle, carriage_front_block, lr)
        hole = mount_screw_hole_drills[f"mount_screw_hole_drill_{lr.name.lower()}"]
        brass_angle = brass_angle.aligned_from_cutter(
            "brass_angle_back_brass_angle_hole_drill_1",
            hole,
            Alignment.CENTER,
            axes=[1],
        )
        brass_angle = translate(
            0,
            0,
            -z_axis_carriage_x_axis_connector_thickness + BRASS_ANGLE_THICKNESS,
        )(brass_angle)
        retval.add_named_non_production_part(
            brass_angle.leader,
            f"carriage_top_brass_angle_{lr.name.lower()}",
        )
        top_brass_angles_fused = top_brass_angles_fused.fuse(brass_angle.leader)
        for name, part in brass_angle.get_named_cutter_items():
            if name.startswith("brass_angle_hole_drill"):
                brass_angle_screw_references[
                    f"screw_reference_{lr.name.lower()}_{name}"
                ] = part

    bottom_brass_angle = create_brass_angle()
    bottom_brass_angle = rotate(90, axis=(-1, 0, 0))(bottom_brass_angle)
    bottom_brass_angle = rotate(180)(bottom_brass_angle)
    bottom_brass_angle = align(
        bottom_brass_angle,
        carriage_front_block,
        Alignment.CENTER,
    )
    bottom_brass_angle = align(
        bottom_brass_angle,
        carriage_front_block,
        Alignment.BOTTOM,
    )
    bottom_hole = mount_screw_hole_drills["mount_screw_hole_drill_left"]
    bottom_brass_angle = bottom_brass_angle.aligned_from_cutter(
        "brass_angle_back_brass_angle_hole_drill_1",
        bottom_hole,
        Alignment.CENTER,
        axes=[1],
    )
    bottom_brass_angle = align(
        bottom_brass_angle,
        carriage_front_block,
        Alignment.LEFT,
    )
    bottom_brass_angle = translate(
        0,
        0,
        z_axis_carriage_x_axis_connector_thickness - BRASS_ANGLE_THICKNESS,
    )(bottom_brass_angle)
    for name, part in bottom_brass_angle.get_named_cutter_items():
        if name.startswith("brass_angle_hole_drill"):
            brass_angle_screw_references[f"screw_reference_bottom__{name}"] = part

    brass_angle_thread_inset_bosses = PartCollector()
    brass_angle_thread_inset_cutters = PartCollector()
    brass_angle_thread_inserts = PartCollector()
    for name, part in brass_angle_screw_references.items():
        mount_screw = create_complete_screw_assembly("M4", 25)
        mount_screw = rotate(90, axis=(1, 0, 0))(mount_screw)
        mount_screw = align(mount_screw, part, Alignment.CENTER)
        mount_screw = align(
            mount_screw,
            top_brass_angles_fused,
            Alignment.STACK_BACK,
            stack_gap=-BRASS_ANGLE_THICKNESS,
        )
        retval.leader = mount_screw.use_as_cutter_on(retval.leader)
        retval.add_named_non_production_part(
            mount_screw.get_named_non_production_part("complete_screw"),
            f"{name}_screw",
        )

        threaded_insert = create_thread_inset_assembly("M4", thickness=8.2)
        threaded_insert = rotate(90, axis=(1, 0, 0))(threaded_insert)
        threaded_insert = align(threaded_insert, part, Alignment.CENTER)
        threaded_insert = align(
            threaded_insert,
            carriage_front_block,
            Alignment.BACK,
        )
        inset_boss = threaded_insert.get_named_cutter("assembly_cutter")
        inset_cutter = inset_boss.cut(threaded_insert.leader)
        brass_angle_thread_inset_bosses = brass_angle_thread_inset_bosses.fuse(
            inset_boss
        )
        brass_angle_thread_inset_cutters = brass_angle_thread_inset_cutters.fuse(
            inset_cutter
        )
        brass_angle_thread_inserts = brass_angle_thread_inserts.fuse(
            threaded_insert.get_named_non_production_part("thread_inset")
        )

    retval.leader = retval.leader.fuse(brass_angle_thread_inset_bosses)
    retval.leader = retval.leader.cut(brass_angle_thread_inset_cutters)

    front_cutter = create_box(500, 500, 500)
    front_cutter = align(front_cutter, retval, Alignment.CENTER)
    front_cutter = align(front_cutter, bottom_brass_angle, Alignment.BACK)

    retval.leader = retval.leader.cut(front_cutter)

    rail_carriages_fused = rail_carriages[0].fuse(rail_carriages[1])

    carriage_mount_plate = materialize_bounding_box(rail_carriages_fused, y_size=3)
    carriage_mount_plate = align(carriage_mount_plate, retval, Alignment.BACK)
    carriage_mount_plate = align(carriage_mount_plate, retval, Alignment.TOP)

    carriage_mount_plate = translate(0, 0, 30)(carriage_mount_plate)

    z_axis_rail_aligned = z_axis_rail.aligned_from_follower(
        "top_carriage", carriage_mount_plate, Alignment.TOP
    )

    carriage_mount_plate = z_axis_rail_aligned.use_as_cutter_on(carriage_mount_plate)

    side_mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_mount_plate = create_box(3, 30, 12)
        side_mount_plate = align(
            side_mount_plate, carriage_mount_plate, Alignment.CENTER
        )
        side_mount_plate = align(side_mount_plate, carriage_mount_plate, lr)
        side_mount_plate = align(
            side_mount_plate, carriage_mount_plate, Alignment.BOTTOM
        )
        side_mount_plate = align(
            side_mount_plate, carriage_mount_plate, Alignment.STACK_FRONT
        )
        side_mount_plate = translate(0, 0, 17)(side_mount_plate)
        side_mount_plates = side_mount_plates.fuse(side_mount_plate)

    retval.leader = retval.leader.fuse(side_mount_plates)
    retval.leader = retval.leader.fuse(carriage_mount_plate)

    retval.add_named_non_production_part(
        brass_angle_thread_inserts,
        "brass_angle_thread_inserts",
    )
    retval.add_named_non_production_part(
        bottom_brass_angle.leader,
        "carriage_bottom_brass_angle",
    )
    retval.add_named_non_production_part(nut.leader, "threaded_rod_nut")
    retval.add_named_non_production_part(
        carriage_reference,
        "x_axis_alignment_reference",
    )
    retval.set_hidden_by_default("x_axis_alignment_reference")

    return translate(0, 0, carriage_z_offset)(retval)
