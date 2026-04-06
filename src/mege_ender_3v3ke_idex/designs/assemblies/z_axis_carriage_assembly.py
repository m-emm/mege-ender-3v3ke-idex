"""Declarative z-axis carriage assembly."""

import math

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_creality_threaded_rod_nut,
    create_igus_drylin_bearing,
)
from shellforgepy.simple import *


def _get_rod_part(rod):
    return rod.leader if hasattr(rod, "leader") else rod


def create_z_axis_carriage_assembly(
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

    carriage_front = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_front_depth,
        z_axis_carriage_front_height,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    carriage_front = align(carriage_front, guide_rod, Alignment.CENTER)
    carriage_front = align(carriage_front, guide_rod, Alignment.BOTTOM)

    bearing = create_igus_drylin_bearing(
        z_axis_igus_drylin_bearing_inner_diameter=z_axis_igus_drylin_bearing_inner_diameter,
        z_axis_igus_drylin_bearing_length=z_axis_igus_drylin_bearing_length,
        z_axis_igus_drylin_bearing_outer_diameter=z_axis_igus_drylin_bearing_outer_diameter,
        cutter_clearance=z_axis_igus_drylin_bearing_cutter_clearance,
        cutter_extra_length=z_axis_carriage_front_height,
    )
    bearing = align(bearing, carriage_front, Alignment.CENTER)
    bearing = align(bearing, guide_rod, Alignment.CENTER, axes=[0, 1])

    bearing_size = get_bounding_box_size(bearing)
    gap_bewteen_bearings = (
        z_axis_carriage_front_height
        - 2 * bearing_size[2]
        - z_axis_carriage_back_height
        - z_axis_carriage_x_axis_connector_thickness
    )

    carriage_front = bearing.use_as_cutter_on(carriage_front)

    top_bearing = align(bearing, carriage_front, Alignment.TOP)
    bottom_bearing = align(bearing, carriage_front, Alignment.BOTTOM)
    bottom_bearing = translate(0, 0, z_axis_carriage_back_height)(bottom_bearing)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_carriage_threaded_rod_clearance,
        z_axis_carriage_front_height + 10,
    )
    threaded_rod_cutter = align(
        threaded_rod_cutter,
        carriage_front,
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
    carriage_back = align(carriage_back, carriage_front, Alignment.CENTER)
    carriage_back = align(carriage_back, carriage_front, Alignment.TOP)
    carriage_back = align(
        carriage_back,
        carriage_front,
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
    carriage_front_center = get_bounding_box_center(carriage_front)
    carriage_cut_point = (
        carriage_front_center[0],
        guide_rod_center[1],
        carriage_front_center[2],
    )
    carriage_front, carriage_front_clamps = cut_in_two(
        carriage_front,
        cut_normal=(0, 1, 0),
        cut_thickness=z_axis_carriage_profile_clearance,
        cut_point=carriage_cut_point,
    )

    front_clamps_cutter = create_box(BIG_THING, BIG_THING, gap_bewteen_bearings)
    front_clamps_cutter = align(
        front_clamps_cutter,
        carriage_front_clamps,
        Alignment.CENTER,
    )
    front_clamps_cutter = align(
        front_clamps_cutter,
        top_bearing,
        Alignment.STACK_BOTTOM,
        stack_gap=z_axis_carriage_x_axis_connector_thickness,
    )
    carriage_front_clamps = carriage_front_clamps.cut(front_clamps_cutter)

    bearings_fused = top_bearing.fuse(bottom_bearing)
    bearings_fused_center = get_bounding_box_center(bearings_fused)
    carriage_front_clamps_center = get_bounding_box_center(carriage_front_clamps)
    clamps_cut_point = (
        carriage_front_clamps_center[0],
        carriage_front_clamps_center[1],
        bearings_fused_center[2],
    )
    carriage_top_clamp, carriage_bottom_clamp = cut_in_two(
        carriage_front_clamps,
        cut_normal=(0, 0, 1),
        cut_point=clamps_cut_point,
    )

    screw_assemblies = []
    for bt in [Alignment.BOTTOM, Alignment.TOP]:
        screw_representative_box = create_box(
            z_axis_carriage_width,
            z_axis_carriage_front_depth,
            bearing_size[2],
        )
        screw_representative_box = align(
            screw_representative_box,
            carriage_top_clamp,
            Alignment.CENTER,
        )

        if bt == Alignment.TOP:
            screw_representative_box = align(
                screw_representative_box,
                carriage_top_clamp,
                Alignment.BOTTOM,
            )
        else:
            screw_representative_box = align(
                screw_representative_box,
                carriage_bottom_clamp,
                Alignment.TOP,
            )

        screw_representative_box = align(
            screw_representative_box,
            carriage_top_clamp,
            Alignment.FRONT,
        )

        screw_assembly = create_four_screws_mount_assembly(
            screw_representative_box,
            z_axis_carriage_mount_screw_size,
            screw_length=z_axis_guide_rod_carriage_clamp_screw_length,
            screw_direction=Alignment.FRONT,
            flush_with_top=True,
            width_inset=z_axis_carriage_rod_clamp_screw_inset,
            length_inset=z_axis_carriage_rod_clamp_screw_inset,
            cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
            clearance_type=z_axis_default_clearance_hole_type,
            nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
        )
        screw_assembly = screw_assembly.prefixed_copy(
            f"carriage_clamp_{bt.name.lower()}_screw_assembly"
        )

        carriage_top_clamp = screw_assembly.use_as_cutter_on(carriage_top_clamp)
        carriage_bottom_clamp = screw_assembly.use_as_cutter_on(carriage_bottom_clamp)
        carriage_front = screw_assembly.use_as_cutter_on(carriage_front)
        screw_assemblies.append(screw_assembly)

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
        carriage_bottom_clamp,
        Alignment.CENTER,
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_bottom_clamp,
        Alignment.BOTTOM,
    )
    x_axis_mount_plate_bottom = align(
        x_axis_mount_plate_bottom,
        carriage_bottom_clamp,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_carriage_fillet_radius,
    )

    mount_screw_hole_drills = PartCollector()
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
    carriage_bottom_clamp = carriage_bottom_clamp.fuse(x_axis_mount_plate_bottom)

    x_axis_mount_plate_top = create_filleted_box(
        z_axis_carriage_width,
        z_axis_x_axis_to_carriage_gap + z_axis_carriage_fillet_radius,
        z_axis_carriage_x_axis_connector_thickness,
        z_axis_carriage_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.BACK],
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_top_clamp,
        Alignment.CENTER,
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_top_clamp,
        Alignment.TOP,
    )
    x_axis_mount_plate_top = align(
        x_axis_mount_plate_top,
        carriage_top_clamp,
        Alignment.STACK_FRONT,
        stack_gap=-z_axis_carriage_fillet_radius,
    )
    x_axis_mount_plate_top = x_axis_mount_plate_top.cut(mount_screw_hole_drills)
    carriage_top_clamp = carriage_top_clamp.fuse(x_axis_mount_plate_top)

    carriage_back_size = get_bounding_box_size(carriage_back)

    enhancement_length = math.sqrt(2) * carriage_back_size[1]

    enhancements = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        enhancement = create_box(
            z_axis_carriage_fillet_radius,
            enhancement_length,
            z_axis_carriage_fillet_radius,
        )
        enhancement = rotate(45, axis=(1, 0, 0))(enhancement)
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
    carriage_body = carriage_front.fuse(carriage_back)

    retval = LeaderFollowersCuttersPart(leader=carriage_body)
    retval.add_named_follower(carriage_top_clamp, "carriage_clamp_0")
    retval.add_named_follower(carriage_bottom_clamp, "carriage_clamp_1")
    retval.add_named_non_production_part(top_bearing.leader, "top_bearing")
    retval.add_named_non_production_part(nut.leader, "threaded_rod_nut")
    for screw_assembly in screw_assemblies:
        for name, part in screw_assembly.get_named_non_production_part_items():
            retval.add_named_non_production_part(part, name)
    retval.add_named_non_production_part(bottom_bearing.leader, "bottom_bearing")

    carriage_reference = retval.leaders_followers_fused()
    retval.add_named_non_production_part(
        translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(carriage_reference),
        "x_axis_alignment_reference",
    )

    return translate(0, 0, carriage_z_offset)(retval)
