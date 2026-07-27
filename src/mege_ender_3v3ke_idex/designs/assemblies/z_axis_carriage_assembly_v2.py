"""Declarative z-axis carriage assembly."""

import math

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_creality_threaded_rod_nut,
)
from shellforgepy.simple import *

lm8luu_length = 44.9
lm8luu_outer_diameter = 15
lm8luu_inner_diameter = 8

lm8luu_outer_groove_width = 1.2
lm8luu_groove_offset = 6
lm8luu_groove_diameter = 14.25


brass_angle_thickness = 1.5
brass_angle_outer_size = 30
brass_angle_width = 14.2
brass_angle_hole_diameter = 4.8
brass_angle_hole_width_inset = 6
brass_angle_hole_outer_inset = 6.5
brass_angle_hole_outer_inset_2 = 21


def create_brass_angle():

    base = create_box(
        brass_angle_width,
        brass_angle_outer_size - 2 * brass_angle_thickness,
        brass_angle_thickness,
    )

    abs_center_offset = brass_angle_width / 2 - brass_angle_hole_width_inset
    center = brass_angle_width / 2

    drills = []
    for x, y in [
        (center - abs_center_offset, brass_angle_hole_outer_inset),
        (center + abs_center_offset, brass_angle_hole_outer_inset_2),
    ]:

        drill = create_cylinder(brass_angle_hole_diameter / 2, 50)
        drill = translate(x, y, -brass_angle_thickness / 2)(drill)

        base = base.cut(drill)
        drills.append(drill)

    base = LeaderFollowersCuttersPart(base)

    for i, drill in enumerate(drills):
        base.add_named_cutter(drill, f"brass_angle_hole_drill_{i}")

    back = rotate(90, axis=(1, 0, 0))(base)
    back = align(back, base, Alignment.STACK_BACK, stack_gap=brass_angle_thickness)
    back = align(back, base, Alignment.STACK_TOP, stack_gap=brass_angle_thickness)

    back = back.prefixed_copy("brass_angle_back")
    retval = base.fuse(back)

    bend = create_ring(
        2 * brass_angle_thickness,
        brass_angle_thickness,
        brass_angle_width,
        angle=90,
    )

    bend = rotate(90, axis=(0, 1, 0))(bend)

    bend = align(bend, base, Alignment.BOTTOM)
    bend = align(bend, base, Alignment.STACK_BACK)

    retval = retval.fuse(bend)

    return retval


def create_linear_bearing_LM8LUU(
    cutter_clearance,
    cutter_extra_length,
):

    bearing = create_ring(
        lm8luu_outer_diameter / 2, lm8luu_inner_diameter / 2, lm8luu_length
    )

    groove_cutters = PartCollector()
    for i in [-1, 1]:
        groove_cutter = create_ring(
            2 * lm8luu_outer_diameter,
            lm8luu_groove_diameter / 2,
            lm8luu_outer_groove_width,
        )
        groove_cutter = align(groove_cutter, bearing, Alignment.CENTER)

        groove_cutter = translate(0, 0, i * (lm8luu_length - lm8luu_groove_offset) / 2)(
            groove_cutter
        )

        groove_cutters = groove_cutters.fuse(groove_cutter)

    bearing = bearing.cut(groove_cutters)

    cutter = create_cylinder(
        (lm8luu_outer_diameter / 2) + cutter_clearance,
        lm8luu_length + cutter_extra_length,
    )
    cutter = align(cutter, bearing, Alignment.CENTER)

    return LeaderFollowersCuttersPart(bearing, cutters=[cutter])


def _get_rod_part(rod):
    return rod.leader if hasattr(rod, "leader") else rod


def create_z_axis_carriage_assembly_v2(
    *,
    z_axis_guide_rod,
    z_axis_threaded_rod,
    carriage_z_offset,
    BIG_THING,
    z_axis_carriage_back_depth,
    z_axis_carriage_back_height,
    z_axis_carriage_fillet_radius,
    z_axis_carriage_front_depth,
    z_axis_carriage_front_height,
    z_axis_carriage_mount_screw_size,
    z_axis_carriage_profile_clearance,
    z_axis_carriage_rod_clamp_screw_inset,
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
    z_axis_cylinder_head_clearance,
    z_axis_additional_screw_mount_clearance,
    z_axis_default_clearance_hole_type,
    z_axis_default_screw_nut_cutter_clearance,
    z_axis_guide_rod_carriage_clamp_screw_length,
    z_axis_igus_drylin_bearing_cutter_clearance,
    z_axis_igus_drylin_bearing_inner_diameter,
    z_axis_igus_drylin_bearing_length,
    z_axis_igus_drylin_bearing_outer_diameter,
    z_axis_nut_screw_hole_clearence_type,
    z_axis_threaded_rod_diameter,
    z_axis_x_axis_to_carriage_gap,
):
    """Create the printable carriage module for one z-axis side."""

    guide_rod = _get_rod_part(z_axis_guide_rod)
    threaded_rod = _get_rod_part(z_axis_threaded_rod)

    carriage_front_block = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_front_depth,
        z_axis_carriage_front_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    carriage_front_block = align(carriage_front_block, guide_rod, Alignment.CENTER)
    carriage_front_block = align(carriage_front_block, guide_rod, Alignment.BOTTOM)

    bearing = create_linear_bearing_LM8LUU(
        cutter_clearance=z_axis_igus_drylin_bearing_cutter_clearance,
        cutter_extra_length=z_axis_carriage_front_height,
    )
    bearing = align(bearing, carriage_front_block, Alignment.CENTER)
    bearing = align(bearing, guide_rod, Alignment.CENTER, axes=[0, 1])

    carriage_front_block = bearing.use_as_cutter_on(carriage_front_block)

    top_bearing = align(bearing, carriage_front_block, Alignment.TOP)

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

    carriage_back = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_back_depth + 2 * z_axis_carriage_fillet_radius,
        z_axis_carriage_back_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    carriage_back = align(carriage_back, carriage_front_block, Alignment.CENTER)
    carriage_back = align(carriage_back, carriage_front_block, Alignment.TOP)
    carriage_back = align(
        carriage_back,
        carriage_front_block,
        Alignment.STACK_BACK,
        stack_gap=-2 * z_axis_carriage_fillet_radius,
    )

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
    base_aligner = align_translation(
        nut_raw_base,
        carriage_back,
        Alignment.STACK_BOTTOM,
    )
    nut = base_aligner(nut)

    carriage_back = nut.use_as_cutter_on(carriage_back)
    carriage_back = carriage_back.cut(threaded_rod_cutter)

    guide_rod_center = get_bounding_box_center(guide_rod)
    carriage_front_block_center = get_bounding_box_center(carriage_front_block)
    carriage_cut_point = (
        carriage_front_block_center[0],
        guide_rod_center[1],
        carriage_front_block_center[2],
    )
    carriage_front_block_back_half, carriage_front_clamps = cut_in_two(
        carriage_front_block,
        cut_normal=(0, 1, 0),
        cut_thickness=z_axis_carriage_profile_clearance,
        cut_point=carriage_cut_point,
    )

    carriage_top_clamp = carriage_front_clamps

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
        carriage_top_clamp,
        Alignment.CENTER,
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_top_clamp,
        Alignment.BOTTOM,
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_top_clamp,
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

    mount_screw_hole_drills = PartCollector()
    mount_screw_hole_drills_directory = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        mount_screw_hole_drill = create_cylinder(
            x_axis_mount_screw_hole_diameter / 2,
            BIG_THING,
        )
        mount_screw_hole_drill = align(
            mount_screw_hole_drill,
            x_axis_mount_plate_bottom,
            Alignment.CENTER,
        )
        mount_screw_hole_drill = align(
            mount_screw_hole_drill,
            x_axis_mount_plate_bottom,
            Alignment.EDGE_FRONT,
        )
        mount_screw_hole_drill = translate(
            lr.sign * (z_axis_carriage_width / 3),
            ExtrusionProfileType.PROFILE_2020.size_mm[0] / 2,
            0,
        )(mount_screw_hole_drill)
        x_axis_mount_plate_bottom = x_axis_mount_plate_bottom.cut(
            mount_screw_hole_drill
        )
        mount_screw_hole_drills = mount_screw_hole_drills.fuse(mount_screw_hole_drill)

        mount_screw_hole_drills_directory[
            f"mount_screw_hole_drill_{lr.name.lower()}"
        ] = mount_screw_hole_drill

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
        enhancement = align(
            enhancement,
            carriage_back,
            Alignment.BACK,
        )
        enhancement = align(
            enhancement,
            carriage_back,
            Alignment.TOP,
        )
        enhancement = align(
            enhancement,
            carriage_back,
            lr,
        )
        enhancement = translate(-lr.sign * z_axis_carriage_fillet_radius, 0, 0)(
            enhancement
        )

        enhancements = enhancements.fuse(enhancement)
    carriage_back = carriage_back.fuse(enhancements)

    carriage_back = bearing.use_as_cutter_on(carriage_back)
    carriage_body = carriage_front_block_back_half.fuse(carriage_back)

    retval = LeaderFollowersCuttersPart(leader=carriage_body)

    brass_angle_screw_references = {}

    top_brass_angles_fused = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        brass_angle = create_brass_angle()

        brass_angle = rotate(90, axis=(1, 0, 0))(brass_angle)

        brass_angle = align(
            brass_angle,
            carriage_top_clamp,
            Alignment.CENTER,
        )

        brass_angle = align(
            brass_angle,
            carriage_top_clamp,
            Alignment.TOP,
        )

        brass_angle = align(
            brass_angle,
            carriage_top_clamp,
            Alignment.FRONT,
        )

        brass_angle = align(brass_angle, carriage_top_clamp, lr)

        x_axis_mount_screw_hole_drill = mount_screw_hole_drills_directory[
            f"mount_screw_hole_drill_{lr.name.lower()}"
        ]
        brass_angle = brass_angle.aligned_from_cutter(
            "brass_angle_back_brass_angle_hole_drill_1",
            x_axis_mount_screw_hole_drill,
            Alignment.CENTER,
            axes=[1],
        )

        brass_angle = translate(
            0, 0, -z_axis_carriage_x_axis_connector_thickness + brass_angle_thickness
        )(brass_angle)

        retval.add_named_non_production_part(
            brass_angle.leader, f"carriage_top_brass_angle_{lr.name.lower()}"
        )

        top_brass_angles_fused = top_brass_angles_fused.fuse(brass_angle.leader)

        for name, part in brass_angle.get_named_cutter_items():
            if name.startswith("brass_angle_hole_drill"):
                brass_angle_screw_references[
                    f"screw_reference_{lr.name.lower()}_{name}"
                ] = part

    top_brass_angles_cutter = materialize_bounding_box(
        top_brass_angles_fused, z_enlargement=100
    )
    top_brass_angles_cutter = align(
        top_brass_angles_cutter, top_brass_angles_fused, Alignment.TOP
    )

    linear_bearing_size = get_bounding_box_size(bearing)

    material_strength = 2.9
    linear_bearing_material_saver = create_cylinder(
        linear_bearing_size[0] / 2 + material_strength, 300
    )
    linear_bearing_material_saver = align(
        linear_bearing_material_saver, bearing, Alignment.CENTER
    )

    top_brass_angles_cutter = top_brass_angles_cutter.cut(linear_bearing_material_saver)

    carriage_top_clamp = carriage_top_clamp.cut(top_brass_angles_cutter)

    bottom_brass_angle = create_brass_angle()
    bottom_brass_angle = rotate(90, axis=(-1, 0, 0))(bottom_brass_angle)
    bottom_brass_angle = rotate(180)(bottom_brass_angle)

    bottom_brass_angle = align(
        bottom_brass_angle,
        carriage_top_clamp,
        Alignment.CENTER,
    )

    bottom_brass_angle = align(
        bottom_brass_angle,
        carriage_top_clamp,
        Alignment.BOTTOM,
    )
    x_axis_mount_screw_hole_drill = mount_screw_hole_drills_directory[
        f"mount_screw_hole_drill_left"
    ]

    bottom_brass_angle = bottom_brass_angle.aligned_from_cutter(
        "brass_angle_back_brass_angle_hole_drill_1",
        x_axis_mount_screw_hole_drill,
        Alignment.CENTER,
        axes=[1],
    )

    bottom_brass_angle = align(
        bottom_brass_angle,
        carriage_top_clamp,
        Alignment.LEFT,
    )

    bottom_brass_angle = translate(
        0, 0, z_axis_carriage_x_axis_connector_thickness - brass_angle_thickness
    )(bottom_brass_angle)

    for name, part in bottom_brass_angle.get_named_cutter_items():
        if name.startswith("brass_angle_hole_drill"):
            brass_angle_screw_references[f"screw_reference_bottom__{name}"] = part

    mount_screw_length = 25
    mount_screw_size = "M4"
    clamp_thread_inset_bosses = PartCollector()
    clamp_thread_inset_cutters = PartCollector()
    clamp_thread_insets = PartCollector()
    for name, part in brass_angle_screw_references.items():
        # retval.add_named_non_production_part(part, name)

        mount_screw = create_complete_screw_assembly(
            mount_screw_size, mount_screw_length
        )
        mount_screw = rotate(90, axis=(1, 0, 0))(mount_screw)
        mount_screw = align(mount_screw, part, Alignment.CENTER)
        mount_screw = align(
            mount_screw,
            top_brass_angles_fused,
            Alignment.STACK_BACK,
            stack_gap=-brass_angle_thickness,
        )
        carriage_top_clamp = mount_screw.use_as_cutter_on(carriage_top_clamp)
        retval.leader = mount_screw.use_as_cutter_on(retval.leader)

        retval.add_named_non_production_part(
            mount_screw.get_named_non_production_part("complete_screw"), f"{name}_screw"
        )

        threaded_insert = create_thread_inset_assembly(mount_screw_size, thickness=8.2)

        threaded_insert = rotate(90, axis=(1, 0, 0))(threaded_insert)
        threaded_insert = align(threaded_insert, part, Alignment.CENTER)
        threaded_insert = align(
            threaded_insert, carriage_front_block_back_half, Alignment.BACK
        )

        thread_inset_boss = threaded_insert.get_named_cutter("assembly_cutter")
        thread_inset_cutter = thread_inset_boss.cut(threaded_insert.leader)
        clamp_thread_inset_bosses = clamp_thread_inset_bosses.fuse(thread_inset_boss)
        clamp_thread_inset_cutters = clamp_thread_inset_cutters.fuse(
            thread_inset_cutter
        )
        clamp_thread_insets = clamp_thread_insets.fuse(
            threaded_insert.get_named_non_production_part("thread_inset")
        )

    retval.leader = retval.leader.fuse(clamp_thread_inset_bosses)
    retval.leader = retval.leader.cut(clamp_thread_inset_cutters)

    retval.add_named_non_production_part(clamp_thread_insets, "clamp_thread_insets")

    retval.add_named_non_production_part(
        bottom_brass_angle.leader, f"carriage_bottom_brass_angle"
    )

    bottom_gap_filler = materialize_bounding_box(
        carriage_top_clamp, y_size=z_axis_carriage_profile_clearance, z_size=4
    )
    bottom_gap_filler = align(bottom_gap_filler, carriage_top_clamp, Alignment.BOTTOM)
    bottom_gap_filler = align(
        bottom_gap_filler, carriage_top_clamp, Alignment.STACK_BACK
    )

    carriage_top_clamp = carriage_top_clamp.fuse(bottom_gap_filler)

    retval.add_named_follower(carriage_top_clamp, "carriage_clamp_0")
    retval.add_named_non_production_part(top_bearing.leader, "top_bearing")
    retval.add_named_non_production_part(nut.leader, "threaded_rod_nut")

    retval.add_named_non_production_part(
        carriage_reference,
        "x_axis_alignment_reference",
    )

    return translate(0, 0, carriage_z_offset)(retval)
