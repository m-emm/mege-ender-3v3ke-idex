"""Declarative monolithic z-axis carriage assembly."""

import copy
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


def _replacement_rail_carriage(z_axis_rail, name):
    """Extract one MGN12H block as a full replacement assembly."""

    metadata_by_name = z_axis_rail.additional_data.get("carriage_metadata_by_name", {})
    if name not in metadata_by_name:
        raise KeyError(
            f"Missing MGN12H metadata for {name!r}; available names: "
            f"{sorted(metadata_by_name)}"
        )

    carriage = LeaderFollowersCuttersPart(
        leader=z_axis_rail.get_follower_part_by_name(name).copy(),
        additional_data=copy.deepcopy(metadata_by_name[name]),
    )
    carriage.add_named_cutter(
        z_axis_rail.get_named_cutter(f"{name}_mounting_holes").copy(),
        "mounting_holes",
    )
    carriage.add_consumed_part_ref(z_axis_rail.part_ref_for_named_follower(name))
    return carriage


def join_z_axis_carriage_assembly(
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
    z_axis_rail_carriage_gap,
    z_axis_rail_carriage_offset_above_carriage,
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
    """Create the printable carriage and movable replacement MGN12H blocks."""

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
    # carriage_back = carriage_back.fuse(enhancements)

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

    for name, part in brass_angle_screw_references.items():
        mount_screw = create_complete_screw_assembly(
            "M4",
            25,
            clearance_type=z_axis_default_clearance_hole_type,
        )
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

        mount_nut = create_nut("M4")
        mount_nut = rotate(90, axis=(1, 0, 0))(mount_nut)
        mount_nut = align(
            mount_nut,
            mount_screw.get_named_non_production_part("complete_screw"),
            Alignment.CENTER,
            axes=[0, 2],
        )
        mount_nut = align(
            mount_nut,
            mount_screw.get_named_non_production_part("complete_screw"),
            Alignment.BACK,
        )
        retval.add_named_non_production_part(
            mount_nut,
            f"{name}_nut",
        )

    front_cutter = create_box(500, 500, 500)
    front_cutter = align(front_cutter, retval, Alignment.CENTER)
    front_cutter = align(front_cutter, bottom_brass_angle, Alignment.BACK)

    retval.leader = retval.leader.cut(front_cutter)

    top_nut_inset = 4
    hidden_nut_cutters = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hidden_nut_cutter = create_hidden_nut_pocket_cutter(
            "M3",
            bottom_cutter_length=8,
            top_cutter_length=100,
            slack=0.4,
            square_nut=True,
        )

        hidden_nut_cutter = rotate(-lr.sign * 90)(hidden_nut_cutter)
        hidden_nut_cutter = rotate(90, axis=(1, 0, 0))(hidden_nut_cutter)

        hidden_nut_cutter = align(hidden_nut_cutter, retval, Alignment.EDGE_TOP)
        hidden_nut_cutter = align(hidden_nut_cutter, retval, Alignment.BACK)
        hidden_nut_cutter = align(hidden_nut_cutter, retval, lr.edge_alignment)

        hidden_nut_cutter = translate(-lr.sign * top_nut_inset, -4, -top_nut_inset)(
            hidden_nut_cutter
        )

        hidden_nut_cutters[lr.name.lower()] = hidden_nut_cutter

    replacement_rail_carriages = {
        name: _replacement_rail_carriage(z_axis_rail, name)
        for name in ("bottom_carriage", "top_carriage")
    }
    replacement_rail_carriages["top_carriage"] = align(
        replacement_rail_carriages["top_carriage"],
        retval,
        Alignment.TOP,
    )
    replacement_rail_carriages["top_carriage"] = translate(
        0,
        0,
        z_axis_rail_carriage_offset_above_carriage,
    )(replacement_rail_carriages["top_carriage"])
    replacement_rail_carriages["bottom_carriage"] = align(
        replacement_rail_carriages["bottom_carriage"],
        replacement_rail_carriages["top_carriage"],
        Alignment.STACK_BOTTOM,
        stack_gap=z_axis_rail_carriage_gap,
    )

    rail_carriages_fused = replacement_rail_carriages["bottom_carriage"].leader.fuse(
        replacement_rail_carriages["top_carriage"].leader
    )

    current_bbox_size = get_bounding_box_size(retval)

    carriage_mount_plate = materialize_bounding_box(
        rail_carriages_fused, y_size=3, x_size=current_bbox_size[0]
    )
    carriage_mount_plate = align(carriage_mount_plate, retval, Alignment.BACK)
    for replacement_carriage in replacement_rail_carriages.values():
        carriage_mount_plate = replacement_carriage.use_as_cutter_on(
            carriage_mount_plate
        )

    side_plate_depth = 15

    side_mount_plate_thickness = 3.5
    connector_height = 14

    side_mount_plates = PartCollector()
    bottom_side_mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_mount_plate = materialize_bounding_box(
            carriage_mount_plate,
            y_size=side_plate_depth,
            x_size=side_mount_plate_thickness,
        )
        side_mount_plate = align(side_mount_plate, carriage_mount_plate, Alignment.TOP)
        side_mount_plate = align(side_mount_plate, carriage_mount_plate, lr)

        side_mount_plate = align(
            side_mount_plate, carriage_mount_plate, Alignment.STACK_FRONT
        )
        side_mount_plates = side_mount_plates.fuse(side_mount_plate)

        bottom_side_mount_plate = create_box(
            side_mount_plate_thickness, current_bbox_size[1], connector_height
        )

        bottom_side_mount_plate = align(
            bottom_side_mount_plate, retval, Alignment.CENTER
        )
        bottom_side_mount_plate = align(
            bottom_side_mount_plate, carriage_mount_plate, Alignment.BACK
        )
        bottom_side_mount_plate = align(
            bottom_side_mount_plate, carriage_mount_plate, lr
        )
        bottom_side_mount_plates = bottom_side_mount_plates.fuse(
            bottom_side_mount_plate
        )

        side_mount_plates = side_mount_plates.fuse(bottom_side_mount_plate)

    flange_thickness = 6
    bottom_flange = materialize_bounding_box(
        bottom_side_mount_plates, y_size=2 * flange_thickness
    )
    bottom_flange = align(bottom_flange, retval, Alignment.CENTER, axes=[1])

    bottom_flange_drill_off_center = 10
    bottom_flange_drills = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        bottom_flange_drill = create_cylinder(
            MScrew.from_size("M5").clearance_hole_loose / 2, 100
        )
        bottom_flange_drill = rotate(
            90,
            axis=(
                1,
                0,
                0,
            ),
        )(bottom_flange_drill)

        bottom_flange_drill = align(
            bottom_flange_drill, bottom_flange, Alignment.CENTER
        )

        bottom_flange_drill = translate(lr.sign * bottom_flange_drill_off_center, 0, 0)(
            bottom_flange_drill
        )

        bottom_flange_drills = bottom_flange_drills.fuse(bottom_flange_drill)

    bottom_flange = bottom_flange.cut(bottom_flange_drills)

    retval.leader = retval.leader.fuse(bottom_flange)

    retval.leader = retval.leader.fuse(side_mount_plates)
    retval.leader = retval.leader.fuse(carriage_mount_plate)

    for name, hidden_nut_cutter in hidden_nut_cutters.items():
        retval.leader = hidden_nut_cutter.use_as_cutter_on(retval.leader)

        retval.add_named_non_production_part(
            hidden_nut_cutter.leader, f"hidden_square_nut_{name}"
        )

    back_part, retval.leader = cut_in_two(retval.leader, cut_normal=(0, 1, 0))

    retval.leader = retval.leader.cut(bottom_flange_drills)

    retval.add_named_follower(back_part, "back_part")

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

    placement = translate(0, 0, carriage_z_offset)
    return {
        "carriage": placement(retval),
        "bottom_rail_carriage": placement(
            replacement_rail_carriages["bottom_carriage"]
        ),
        "top_rail_carriage": placement(replacement_rail_carriages["top_carriage"]),
    }
