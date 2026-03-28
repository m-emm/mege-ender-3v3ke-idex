"""
Motor Mount

Usage:
    cd <project_root> && ./run.sh path/to/motor_mount.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/motor_mount.py
"""

import logging
import os
from functools import reduce

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler, create_gt2_pulley
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.metrics import record_mark_metric
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}


def create_idlers_for_motor(
    profile_to_align,
) -> LeaderFollowersCuttersPart:

    idlers = PartCollector()

    idler_axle_cutters = []
    idler_nut_cutters = []
    for idler_alignment in (Alignment.LEFT, Alignment.RIGHT):

        idler = create_gt2_idler(num_teeth=16)

        idler = align(
            idler,
            profile_to_align,
            Alignment.CENTER,
        )

        idler = translate(idler_alignment.sign * motor_idler_out_offset, 0, 0)(idler)
        idler = align(
            idler,
            profile_to_align,
            Alignment.STACK_BACK,
            stack_gap=motor_idler_profile_gap,
        )
        idlers = idlers.fuse(idler)

        idler_axle_cutter = create_cylinder(
            idler_mount_axle_diameter / 2 + idler_mount_axle_clearance, 100
        )
        idler_axle_cutter = align(idler_axle_cutter, idler, Alignment.CENTER)

        idler_screw_nut_cutter = create_nut(
            axle_screw_size,
            height=axle_screw_nut_hole_depth,
            slack=axle_screw_nut_slack,
        )
        idler_screw_nut_cutter = rotate(30)(idler_screw_nut_cutter)
        idler_screw_nut_cutter = align(idler_screw_nut_cutter, idler, Alignment.CENTER)
        idler_axle_cutters.append(idler_axle_cutter)
        idler_nut_cutters.append(idler_screw_nut_cutter)

    retval = LeaderFollowersCuttersPart(idlers)

    for i, idler_axle_cutter in enumerate(idler_axle_cutters):
        retval.add_named_cutter(idler_axle_cutter, f"idler_axle_cutter_{i}")
    for i, idler_nut_cutter in enumerate(idler_nut_cutters):
        retval.add_named_cutter(idler_nut_cutter, f"idler_nut_cutter_{i}")

    return retval


def _project_center_onto_profile_length_mm(profile_to_align, marker_part) -> float:
    profile_bbox = get_bounding_box(profile_to_align)
    profile_size = get_bounding_box_size(profile_to_align)
    profile_length_axis = max(range(3), key=lambda axis: profile_size[axis])
    marker_center = get_bounding_box_center(marker_part)

    return marker_center[profile_length_axis] - profile_bbox[0][profile_length_axis]


def create_motor_stack(
    side, lower_axis_profile, top_axis_profile
) -> LeaderFollowersCuttersPart:
    """Build one motor + mount assembly (idler bases, shield, connector) for a side."""

    vertical_aligment_map = {
        Alignment.LEFT: Alignment.BOTTOM,
        Alignment.RIGHT: Alignment.TOP,
    }

    vertical_alignment = vertical_aligment_map[side]

    profile_to_align = (
        lower_axis_profile if side == Alignment.LEFT else top_axis_profile
    )

    idlers_assembly = create_idlers_for_motor(
        profile_to_align=profile_to_align,
    )

    idlers_assembly = translate(side.sign * motor_x_offset, 0, 0)(idlers_assembly)

    idler_axle_cutters = [
        idlers_assembly.get_cutter_part_by_name(f"idler_axle_cutter_{i}")
        for i in range(2)
    ]
    idler_nut_cutters = [
        idlers_assembly.get_cutter_part_by_name(f"idler_nut_cutter_{i}")
        for i in range(2)
    ]

    pulley = create_gt2_pulley(num_teeth=20, belt_width=6)
    if side == Alignment.LEFT:
        pulley = rotate(180, axis=(0, 1, 0))(pulley)

    pulley = align(pulley, idlers_assembly, Alignment.CENTER)
    pulley = align(pulley, idlers_assembly, vertical_alignment)
    pulley = translate(0, motor_pulley_idlers_distance, 0)(pulley)

    motor = create_nema_composite(
        axle_length=x_axis_motor_axle_length,
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )

    if side == Alignment.LEFT:
        motor.rotate((0, 0, 0), (0, 1, 0), 180)

    motor = align(motor, idlers_assembly, Alignment.CENTER)
    motor = align(
        motor,
        pulley,
        vertical_alignment.opposite.stack_alignment,
        stack_gap=motor_pulley_gap,
    )

    motor = motor.aligned_from_follower(
        "axle",
        pulley,
        Alignment.CENTER,
        axes=[0, 1],
    )

    mount_plate_seed = create_box(1, 1, 1)
    mount_plate_seed = align(mount_plate_seed, motor, Alignment.CENTER)
    mount_plate_seed = align(mount_plate_seed, motor, Alignment.STACK_TOP)
    mount_plate_seed = align(mount_plate_seed, profile_to_align, Alignment.STACK_BACK)

    mount_plate_seed_fused = mount_plate_seed.fuse(motor.leader)

    mount_plate_seed_bounding_box_size = get_bounding_box_size(mount_plate_seed_fused)

    mount_plate = create_filleted_box(
        motor_mount_plate_size,
        mount_plate_seed_bounding_box_size[1],
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    mount_plate = align(mount_plate, motor, Alignment.CENTER)
    mount_plate = align(mount_plate, profile_to_align, Alignment.STACK_BACK)
    mount_plate = align(mount_plate, profile_to_align, vertical_alignment.opposite)

    mount_plate = motor.use_as_cutter_on(mount_plate)

    motor.add_named_non_production_part(pulley, "pulley")

    mount_plate_limit_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    mount_plate_limit_cutter = align(
        mount_plate_limit_cutter, mount_plate, Alignment.CENTER
    )
    mount_plate_limit_cutter = align(
        mount_plate_limit_cutter,
        mount_plate,
        vertical_alignment.opposite.stack_alignment,
    )

    mount_plate_opposite_limit_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    mount_plate_opposite_limit_cutter = align(
        mount_plate_opposite_limit_cutter, mount_plate, Alignment.CENTER
    )
    mount_plate_opposite_limit_cutter = align(
        mount_plate_opposite_limit_cutter,
        mount_plate,
        vertical_alignment.opposite,
    )

    motor_bbox_size = get_bounding_box_size(motor.leader)

    motor_bridge = create_filleted_box(
        motor_mount_plate_size,
        motor_bbox_size[1],
        BIG_THING / 2,
        fillet_radius=motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.FRONT],
    )
    motor_bridge = align(motor_bridge, motor, Alignment.CENTER)

    motor_body = motor.get_follower_part_by_name("body")

    motor_bridge = align(motor_bridge, motor_body, vertical_alignment.stack_alignment)

    motor_bridge = motor_bridge.cut(mount_plate_opposite_limit_cutter)

    motor_bridge = motor.use_as_cutter_on(motor_bridge)

    motor_bridge_bbox_size = get_bounding_box_size(motor_bridge)
    motor_bridge_front_bevel = create_right_triangle(
        motor_bridge_bbox_size[2],
        motor_bridge_bbox_size[2],
        thickness=motor_bridge_bbox_size[0],
        extrusion_direction=(1, 0, 0),
        a_normal=(0, 0, vertical_alignment.sign),
        b_normal=(0, -1, 0),
    )

    motor_bridge_front_bevel = align(
        motor_bridge_front_bevel, motor_bridge, Alignment.CENTER
    )
    motor_bridge_front_bevel = align(
        motor_bridge_front_bevel, motor_bridge, Alignment.STACK_FRONT
    )
    motor_bridge = motor_bridge.fuse(motor_bridge_front_bevel)

    for axle_cutter in idler_axle_cutters:
        mount_plate = mount_plate.cut(axle_cutter)
        motor_bridge = motor_bridge.cut(axle_cutter)

    for nut_cutter in idler_nut_cutters:
        nut_cutter_aligned = align(nut_cutter, mount_plate, vertical_alignment.opposite)
        mount_plate = mount_plate.cut(nut_cutter_aligned)
        nut_cutter_aligned = align(
            nut_cutter, motor_bridge, vertical_alignment.opposite
        )

        motor_bridge = motor_bridge.cut(nut_cutter_aligned)

    mount_shield = create_filleted_box(
        mount_shield_width,
        mount_shield_depth,
        BIG_THING,
        mount_shield_fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.TOP, Alignment.BOTTOM],
    )

    mount_shield = align(mount_shield, mount_plate, Alignment.CENTER)
    mount_shield = align(mount_shield, mount_plate, Alignment.FRONT)
    mount_shield = align(
        mount_shield,
        profile_to_align,
        vertical_alignment,
    )
    mount_shield = translate(0, 0, side.sign * mount_shield_oversize_z)(mount_shield)
    mount_shield = mount_shield.cut(mount_plate_limit_cutter)

    mount_shield_mount_screw_hole_cutter = create_cylinder(
        MScrew.from_size("M5").clearance_hole_normal / 2,
        BIG_THING,
        direction=(0, 1, 0),
    )
    mount_shield_mount_screw_hole_cutter = align(
        mount_shield_mount_screw_hole_cutter, mount_shield, Alignment.CENTER
    )
    mount_shield_mount_screw_hole_cutter = align(
        mount_shield_mount_screw_hole_cutter,
        profile_to_align,
        Alignment.CENTER,
        axes=[2],
    )
    mount_shield = mount_shield.cut(mount_shield_mount_screw_hole_cutter)

    motor.add_named_follower(mount_shield, "mount_shield")

    mount_screw = create_cylinder_screw(
        "M5", length=motor_mount_shield_mount_screw_length
    )
    mount_screw = rotate(-90, axis=(1, 0, 0))(mount_screw)
    mount_screw = align(
        mount_screw, mount_shield_mount_screw_hole_cutter, Alignment.CENTER
    )

    profile_part_name = (
        "x_axis_lower_profile" if side == Alignment.LEFT else "x_axis_top_profile"
    )
    record_mark_metric(
        stock_type=ExtrusionProfileType.PROFILE_2020.value,
        part_name=profile_part_name,
        stock_length_mm=x_axis_profile_length,
        mark_name=f"mount_shield_mount_screw_{side.name.lower()}",
        position_mm=_project_center_onto_profile_length_mm(
            profile_to_align,
            mount_shield_mount_screw_hole_cutter,
        ),
    )

    motor.add_named_non_production_part(mount_screw, "mount_screw")

    mount_plate_connector = create_filleted_box(
        mount_plate_connector_length,
        mount_plate_connector_depth,
        motor_mount_plate_thickness,
        fillet_radius=motor_mount_plate_fillet_radius,
        no_fillets_at=[
            Alignment.BOTTOM,
            Alignment.TOP,
            side,
        ],
    )

    mount_plate_connector = align(mount_plate_connector, mount_plate, Alignment.CENTER)
    mount_plate_connector = align(mount_plate_connector, mount_plate, Alignment.FRONT)
    mount_plate_connector = align(
        mount_plate_connector,
        mount_plate,
        side.opposite.stack_alignment,
    )
    mount_plate_connector = translate(
        side.sign * motor_mount_plate_fillet_radius, 0, 0
    )(mount_plate_connector)

    mount_plate_connector = mount_plate_connector.cut(mount_plate)

    motor.add_named_follower(mount_plate_connector, "mount_plate_connector")
    mount_flange = create_filleted_box(
        mount_plate_connector_length + motor_mount_plate_size,
        flange_depth,
        flange_thickness,
        fillet_radius=mount_shield_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, Alignment.FRONT],
    )

    mount_flange = align(mount_flange, mount_plate_connector, Alignment.CENTER)
    mount_flange = align(mount_flange, mount_plate, side)
    mount_flange = align(mount_flange, mount_plate_connector, Alignment.FRONT)
    mount_flange = align(mount_flange, profile_to_align, vertical_alignment)

    motor.add_named_non_production_part(idlers_assembly.leader, "idlers")

    nut_pocket_cutters = []
    for screw_hole_alignment in (Alignment.LEFT, Alignment.RIGHT):

        nut_cutter = create_hidden_nut_pocket_cutter(
            counter_flange_mount_screw_size,
            bottom_cutter_length=3,
            top_cutter_length=100,
            slack=0.3,
        )

        if vertical_alignment == Alignment.BOTTOM:
            nut_cutter = rotate(180, axis=(0, 1, 0))(nut_cutter)

        nut_cutter = align(nut_cutter, mount_flange, Alignment.CENTER)
        nut_cutter = align(nut_cutter, mount_plate_connector, screw_hole_alignment)
        nut_cutter = translate(
            -screw_hole_alignment.sign * mount_flange_screw_hole_inset,
            0,
            -side.sign * nut_cutter_offset_z,
        )(nut_cutter)

        nut_pocket_cutters.append(nut_cutter)
        mount_flange = nut_cutter.use_as_cutter_on(mount_flange)

    for idler_axle_cutter in idler_axle_cutters:
        mount_flange = mount_flange.cut(idler_axle_cutter)

        idler_screw_spec = MScrew.from_size(idler_screw_size)
        cylinder_head_cutter = create_cylinder(
            idler_screw_spec.cylinder_head_diameter / 2 + idler_screw_head_clearance,
            idler_screw_spec.cylinder_head_height + 2 * idler_screw_head_clearance,
        )
        cylinder_head_cutter = align(
            cylinder_head_cutter, idler_axle_cutter, Alignment.CENTER
        )
        cylinder_head_cutter = align(
            cylinder_head_cutter, mount_flange, vertical_alignment
        )
        mount_flange = mount_flange.cut(cylinder_head_cutter)

    mount_flange_bevel = create_right_triangle(
        bevel_depth + mount_flange_bevel_oversize,
        bevel_depth,
        thickness=mount_plate_connector_length - 2 * motor_mount_plate_fillet_radius,
        extrusion_direction=(side.sign, 0, 0),
        a_normal=(0, 0, vertical_alignment.sign),
        b_normal=(0, -1, 0),
    )

    mount_flange_bevel = align(
        mount_flange_bevel, mount_plate_connector, Alignment.CENTER
    )
    mount_flange_bevel = align(mount_flange_bevel, mount_flange, Alignment.BACK)

    mount_flange_bevel_flange_side = align(
        mount_flange_bevel, mount_flange, vertical_alignment.opposite.stack_alignment
    )

    for nut_cutter in nut_pocket_cutters:
        mount_flange_bevel_flange_side = nut_cutter.use_as_cutter_on(
            mount_flange_bevel_flange_side
        )

    mount_flange = mount_flange.fuse(mount_flange_bevel_flange_side)

    motor.add_named_follower(mount_flange, "mount_flange")

    motor_visual = motor.leader.copy()
    motor.add_named_non_production_part(motor_visual, "motor_visual")

    motor_name = f"motor_{side.name.lower()}"

    motor.additional_data["name"] = motor_name

    axis_holding_counter_flange = create_filleted_box(
        axis_holder_width,
        axis_holder_depth,
        axis_holder_thickness,
        axis_holder_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    axis_holding_counter_flange = align(
        axis_holding_counter_flange, mount_flange, side.opposite
    )
    axis_holding_counter_flange = align(
        axis_holding_counter_flange, mount_flange, vertical_alignment.stack_alignment
    )
    axis_holding_counter_flange = align(
        axis_holding_counter_flange, mount_flange, Alignment.BACK
    )

    axis_holding_counter_flange_screws = []

    for nut_cutter in nut_pocket_cutters:
        axis_holding_counter_flange = nut_cutter.use_as_cutter_on(
            axis_holding_counter_flange
        )

        profile_mount_screw_hole_cutter = create_cylinder(
            MScrew.from_size("M5").clearance_hole_normal / 2,
            BIG_THING,
        )
        profile_mount_screw_hole_cutter = align(
            profile_mount_screw_hole_cutter,
            axis_holding_counter_flange,
            Alignment.CENTER,
        )
        profile_mount_screw_hole_cutter = align(
            profile_mount_screw_hole_cutter, nut_cutter, Alignment.CENTER, axes=[0]
        )
        profile_mount_screw_hole_cutter = align(
            profile_mount_screw_hole_cutter,
            profile_to_align,
            Alignment.CENTER,
            axes=[1],
        )
        axis_holding_counter_flange = axis_holding_counter_flange.cut(
            profile_mount_screw_hole_cutter
        )

        axis_holding_counter_flange_screw = create_cylinder_screw(
            counter_flange_mount_screw_size, length=counter_flange_mount_screw_length
        )
        if side == Alignment.LEFT:
            axis_holding_counter_flange_screw = rotate(180, axis=(0, 1, 0))(
                axis_holding_counter_flange_screw
            )
        axis_holding_counter_flange_screw = align(
            axis_holding_counter_flange_screw, nut_cutter, Alignment.CENTER
        )
        axis_holding_counter_flange_screw = align(
            axis_holding_counter_flange_screw,
            axis_holding_counter_flange,
            vertical_alignment,
        )
        axis_holding_counter_flange_screw = translate(
            0,
            0,
            vertical_alignment.sign
            * MScrew.from_size(counter_flange_mount_screw_size).cylinder_head_height,
        )(axis_holding_counter_flange_screw)

        axis_holding_counter_flange_screws.append(axis_holding_counter_flange_screw)

    motor.add_named_follower(axis_holding_counter_flange, "axis_holding_counter_flange")

    axis_holding_counter_flange_screws_fused = reduce(
        lambda acc, screw: acc.fuse(screw),
        axis_holding_counter_flange_screws,
        PartCollector(),
    )
    motor.add_named_non_production_part(
        axis_holding_counter_flange_screws_fused, "axis_holding_counter_flange_screws"
    )

    motor.add_named_follower(motor_bridge, "motor_bridge")
    motor.add_named_follower(mount_plate, "mount_plate")

    retval = LeaderFollowersCuttersPart(motor.leader)

    for follower_name in [
        "mount_shield",
        "mount_plate",
        "mount_flange",
        "motor_bridge",
        "mount_plate_connector",
    ]:
        retval.add_named_follower(
            motor.get_follower_part_by_name(follower_name), follower_name
        )

    for cross_follower_name in [
        "axis_holding_counter_flange",
        "axle",
    ]:
        retval.add_named_non_production_part(
            motor.get_follower_part_by_name(cross_follower_name), cross_follower_name
        )

    for non_production_part_name in [
        "pulley",
        "idlers",
        "axis_holding_counter_flange_screws",
        "motor_visual",
        "mount_screw",
    ]:
        retval.add_named_non_production_part(
            motor.get_non_production_part_by_name(non_production_part_name),
            non_production_part_name,
        )

    return retval


def bboxes_overlap(bbox1, bbox2):
    x_overlap = max(0, min(bbox1[1][0], bbox2[1][0]) - max(bbox1[0][0], bbox2[0][0]))
    y_overlap = max(0, min(bbox1[1][1], bbox2[1][1]) - max(bbox1[0][1], bbox2[0][1]))
    z_overlap = max(0, min(bbox1[1][2], bbox2[1][2]) - max(bbox1[0][2], bbox2[0][2]))
    return x_overlap > 0 and y_overlap > 0 and z_overlap > 0


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020, length_mm=x_axis_profile_length
    )
    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    top_axis_profile = translate(0, 0, x_axis_profile_pitch)(lower_axis_profile)
    axis_frame = lower_axis_profile.fuse(top_axis_profile)

    parts.add(axis_frame, "axis_frame")

    # Create the part

    side = Alignment.RIGHT

    motor_assembly = create_motor_stack(side, lower_axis_profile, top_axis_profile)

    all_bboxes_by_name = {}

    for name, part in motor_assembly.get_named_follower_items():
        part_name = f"motor_stack_{side.name.lower()}_{name}"
        parts.add(part, part_name, skip_in_production=False)
        bbox = get_bounding_box(part)
        all_bboxes_by_name[part_name] = bbox

    # motor_followers_fused = PartCollector()
    # for follower in motor_assembly.followers:
    #     motor_followers_fused = motor_followers_fused.fuse(follower)

    # motor_followers_fused = translate(80, 100, 0)(motor_followers_fused)
    # parts.add(motor_followers_fused, f"motor_stack_{side.name.lower()}_followers_fused")

    for name, part in motor_assembly.get_named_non_production_part_items():
        part_name = f"motor_stack_{side.name.lower()}_{name}"

        parts.add(part, part_name, skip_in_production=False, color=(0.6, 0.6, 0.6))
        bbox = get_bounding_box(part)
        all_bboxes_by_name[part_name] = bbox

    all_bboxes_items = list(all_bboxes_by_name.items())

    for i in range(len(all_bboxes_items)):
        name_i, bbox_i = all_bboxes_items[i]
        for j in range(i + 1, len(all_bboxes_items)):
            name_j, bbox_j = all_bboxes_items[j]
            if bboxes_overlap(bbox_i, bbox_j):
                _logger.warning(f"Bounding boxes of {name_i} and {name_j} overlap")

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("motor_mount created successfully!")


if __name__ == "__main__":
    main()
