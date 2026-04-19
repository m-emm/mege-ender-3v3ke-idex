"""Standalone x-axis belt carriage assembly."""

import logging

from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _create_lower_side_plates(
    *,
    carriage_mount_plate,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_side_plate_depth,
    tool_head_mount_side_plate_height,
    tool_head_mount_carriage_mount_plate_fillet_radius,
):
    side_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_plate = create_filleted_box(
            tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth,
            tool_head_mount_side_plate_height,
            fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
            no_fillets_at=[Alignment.TOP, lr.opposite],
        )
        side_plate = align(side_plate, carriage_mount_plate, Alignment.STACK_BOTTOM)
        side_plate = align(side_plate, carriage_mount_plate, Alignment.FRONT)
        side_plate = align(side_plate, carriage_mount_plate, lr)
        side_plates = side_plates.fuse(side_plate)

    return side_plates


def _create_upper_side_plates(
    *,
    carriage_mount_plate,
    belt_profile,
    rotated_clamp,
    tool_head_mount_base_plate_height,
    tool_head_mount_carriage_mount_plate_thickness,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_side_plate_depth,
    tool_head_mount_carriage_mount_plate_fillet_radius,
):
    carriage_mount_plate_size = get_bounding_box_size(carriage_mount_plate)
    carriage_mount_plate_center = get_bounding_box_center(carriage_mount_plate)
    carriage_mount_plate_top_z = (
        carriage_mount_plate_center[2] + carriage_mount_plate_size[2] / 2
    )

    belt_profile_center_z = get_bounding_box_center(belt_profile)[2]
    rotated_clamp_size = get_bounding_box_size(rotated_clamp)
    clamp_top_z = belt_profile_center_z + rotated_clamp_size[2] / 2

    upper_side_plate_height = max(
        clamp_top_z - carriage_mount_plate_top_z + 2,
        tool_head_mount_base_plate_height
        + tool_head_mount_carriage_mount_plate_thickness,
    )

    upper_side_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        side_plate = create_filleted_box(
            tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth,
            upper_side_plate_height,
            fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
            no_fillets_at=[Alignment.BOTTOM, lr.opposite],
        )
        side_plate = align(side_plate, carriage_mount_plate, Alignment.STACK_TOP)
        side_plate = align(side_plate, carriage_mount_plate, Alignment.FRONT)
        side_plate = align(side_plate, carriage_mount_plate, lr)
        upper_side_plates = upper_side_plates.fuse(side_plate)

    return upper_side_plates


def _get_sprite_alignment_reference(sprite_extruder):
    sprite_alignment_reference = sprite_extruder.leader
    for (
        name,
        non_production_part,
    ) in sprite_extruder.get_named_non_production_part_items():
        if name == "fan":
            sprite_alignment_reference = sprite_alignment_reference.fuse(
                non_production_part
            )

    return sprite_alignment_reference


def _create_rotated_hollow_bridge(
    *,
    bridge_width,
    bridge_outer_size,
    bridge_wall_thickness,
    belt_deflectors,
    x_reference_part,
    axis_profile,
    sprite_alignment_reference,
    bridge_clearance_to_sprite,
):
    profile_bbox = get_bounding_box(axis_profile)
    sprite_bbox = get_bounding_box(sprite_alignment_reference)

    profile_front_y = profile_bbox[1][0]
    sprite_back_y = sprite_bbox[0][1]
    available_y_gap = sprite_back_y - profile_front_y

    _logger.info(f"Gap between profile and sprite: {available_y_gap}")

    minimum_outer_size = 2 * bridge_wall_thickness + 1.0
    usable_outer_size = min(
        bridge_outer_size,
        (available_y_gap - bridge_clearance_to_sprite) / (2**0.5),
    )
    usable_outer_size = max(usable_outer_size, minimum_outer_size)

    bridge = create_box(bridge_width, usable_outer_size, usable_outer_size)
    bridge_inner = create_box(
        bridge_width + 2,
        usable_outer_size - 2 * bridge_wall_thickness,
        usable_outer_size - 2 * bridge_wall_thickness,
    )
    bridge_inner = align(bridge_inner, bridge, Alignment.CENTER)
    bridge = bridge.cut(bridge_inner)
    bridge = rotate(45, axis=(1, 0, 0))(bridge)
    bridge = align(bridge, x_reference_part, Alignment.CENTER, axes=[0])
    bridge = align(bridge, belt_deflectors, Alignment.CENTER, axes=[2])
    bridge = align(bridge, belt_deflectors, Alignment.BACK)

    return bridge


def _create_mount_eyes(
    *,
    reference_part,
    drive_position,
    mount_eye_thickness,
    mount_eye_length,
    mount_eye_width,
    mount_eye_hole_diameter,
    mount_eye_fillet_radius,
    big_thing,
):
    mount_eyes = PartCollector()
    mount_eye_cutters = []
    z_alignment = Alignment.BOTTOM if drive_position == Alignment.TOP else Alignment.TOP

    for side_name, side_alignment in [
        ("left", Alignment.LEFT),
        ("right", Alignment.RIGHT),
    ]:
        mount_eye = create_filleted_box(
            mount_eye_width,
            mount_eye_length,
            mount_eye_thickness,
            mount_eye_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side_alignment.opposite],
        )
        mount_eye = align(mount_eye, reference_part, Alignment.CENTER, axes=[1])
        mount_eye = align(mount_eye, reference_part, z_alignment)
        mount_eye = align(mount_eye, reference_part, side_alignment.stack_alignment)

        mount_eye_hole = create_cylinder(mount_eye_hole_diameter / 2, big_thing)
        mount_eye_hole = align(mount_eye_hole, mount_eye, Alignment.CENTER)
        mount_eye = mount_eye.cut(mount_eye_hole)

        mount_eyes = mount_eyes.fuse(mount_eye)
        mount_eye_cutters.append((f"mount_eye_hole_{side_name}", mount_eye_hole))

    return mount_eyes, mount_eye_cutters


def create_x_axis_belt_carriage_assembly(
    *,
    carriage,
    axis_profile,
    sprite_extruder,
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
    x_axis_belt_carriage_left_gap,
    x_axis_belt_carriage_right_gap,
    x_axis_belt_carriage_bridge_clearance_to_sprite,
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

    sprite_alignment_reference = _get_sprite_alignment_reference(sprite_extruder)
    carriage_size = get_bounding_box_size(carriage)
    clamp_seed = create_gt_belt_clamp(
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
    clamp_seed = rotate(90, axis=(1, 0, 0))(clamp_seed)
    clamp_seed = rotate(90)(clamp_seed)

    carriage_mount_plate = create_filleted_box(
        tool_head_mount_carriage_mount_plate_width,
        carriage_size[1] + tool_head_mount_y_extension,
        tool_head_mount_carriage_mount_plate_thickness,
        fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.STACK_TOP)
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.BACK)
    carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)

    if drive_alignment == Alignment.TOP:
        clamp_side_plates = _create_upper_side_plates(
            carriage_mount_plate=carriage_mount_plate,
            belt_profile=axis_profile,
            rotated_clamp=clamp_seed,
            tool_head_mount_base_plate_height=tool_head_mount_base_plate_height,
            tool_head_mount_carriage_mount_plate_thickness=tool_head_mount_carriage_mount_plate_thickness,
            tool_head_mount_side_plate_thickness=tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth=tool_head_mount_side_plate_depth,
            tool_head_mount_carriage_mount_plate_fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        )
    else:
        clamp_side_plates = _create_lower_side_plates(
            carriage_mount_plate=carriage_mount_plate,
            tool_head_mount_side_plate_thickness=tool_head_mount_side_plate_thickness,
            tool_head_mount_side_plate_depth=tool_head_mount_side_plate_depth,
            tool_head_mount_side_plate_height=tool_head_mount_side_plate_height,
            tool_head_mount_carriage_mount_plate_fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        )

    clamp_1 = align(
        clamp_seed,
        sprite_alignment_reference,
        Alignment.STACK_LEFT,
        stack_gap=x_axis_belt_carriage_left_gap,
    )
    clamp_1 = align(clamp_1, clamp_side_plates, Alignment.BACK)
    clamp_1 = align(clamp_1, axis_profile, Alignment.CENTER, axes=[2])
    clamp_1 = translate(0, -tool_head_mount_belt_clamp_y_offset, 0)(clamp_1)

    clamp_2 = rotate(180, axis=(0, 1, 0), center=get_bounding_box_center(clamp_seed))(
        clamp_seed
    )
    clamp_2 = align(
        clamp_2,
        sprite_alignment_reference,
        Alignment.STACK_RIGHT,
        stack_gap=x_axis_belt_carriage_right_gap,
    )
    clamp_2 = align(clamp_2, clamp_side_plates, Alignment.BACK)
    clamp_2 = align(clamp_2, axis_profile, Alignment.CENTER, axes=[2])
    clamp_2 = translate(0, -tool_head_mount_belt_clamp_y_offset, 0)(clamp_2)

    clamp = LeaderFollowersCuttersPart(leader=clamp_1.leader.fuse(clamp_2.leader))
    clamp.add_named_follower(clamp_1.get_follower_part_by_name("clamp"), "clamp_1")
    clamp.add_named_follower(clamp_2.get_follower_part_by_name("clamp"), "clamp_2")
    clamp.add_named_follower(clamp_1.leader, "belt_clamp_base_1")
    clamp.add_named_follower(clamp_2.leader, "belt_clamp_base_2")
    clamp.add_named_follower(
        clamp_1.get_follower_part_by_name("belt_path_cutter"),
        "belt_path_cutter_1",
    )
    clamp.add_named_follower(
        clamp_2.get_follower_part_by_name("belt_path_cutter"),
        "belt_path_cutter_2",
    )
    for name, non_production_part in clamp_1.get_named_non_production_part_items():
        clamp.add_named_non_production_part(non_production_part, f"clamp_1_{name}")
    for name, non_production_part in clamp_2.get_named_non_production_part_items():
        clamp.add_named_non_production_part(non_production_part, f"clamp_2_{name}")

    clamps_list = [
        clamp.get_follower_part_by_name("clamp_1"),
        clamp.get_follower_part_by_name("clamp_2"),
    ]
    bases_list = [
        clamp.get_follower_part_by_name("belt_clamp_base_1"),
        clamp.get_follower_part_by_name("belt_clamp_base_2"),
    ]
    belt_path_cutters_list = [
        clamp.get_follower_part_by_name("belt_path_cutter_1"),
        clamp.get_follower_part_by_name("belt_path_cutter_2"),
    ]

    clamp_cutter = PartCollector()
    bases_cutter = PartCollector()
    belt_path_cutter = PartCollector()
    belt_deflectors = PartCollector()

    for current_clamp, current_base, current_belt_path_cutter, clamp_side in zip(
        clamps_list,
        bases_list,
        belt_path_cutters_list,
        [Alignment.LEFT, Alignment.RIGHT],
    ):
        current_clamp_size = get_bounding_box_size(current_clamp)
        current_clamp_cutter = create_box(*current_clamp_size)
        current_clamp_cutter = align(
            current_clamp_cutter,
            current_clamp,
            Alignment.CENTER,
        )
        clamp_cutter = clamp_cutter.fuse(current_clamp_cutter)

        current_base_size = get_bounding_box_size(current_base)
        current_base_cutter = create_box(
            BIG_THING,
            current_base_size[1] + 2 * tool_head_mount_clamp_base_cutter_clearance,
            current_base_size[2],
        )
        current_base_cutter = align(current_base_cutter, current_base, Alignment.CENTER)
        current_base_cutter = align(current_base_cutter, current_base, Alignment.BACK)
        bases_cutter = bases_cutter.fuse(current_base_cutter)

        current_belt_path_cutter_size = get_bounding_box_size(current_belt_path_cutter)
        current_belt_path_cutter_enlarged = create_box(
            current_belt_path_cutter_size[0]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
            current_belt_path_cutter_size[1]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
            current_belt_path_cutter_size[2]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
        )
        current_belt_path_cutter_enlarged = align(
            current_belt_path_cutter_enlarged,
            current_belt_path_cutter,
            Alignment.CENTER,
        )
        belt_path_cutter = belt_path_cutter.fuse(current_belt_path_cutter_enlarged)

        belt_deflector = create_box(
            tool_head_mount_belt_deflector_thickness,
            BIG_THING,
            current_belt_path_cutter_size[2],
        )
        belt_deflector = align(
            belt_deflector,
            current_belt_path_cutter,
            Alignment.CENTER,
        )
        belt_deflector = align(
            belt_deflector,
            axis_profile,
            Alignment.STACK_FRONT,
            stack_gap=-tool_head_mount_belt_deflector_into_profile_distance,
        )

        belt_deflector_trimmer = create_box(
            BIG_THING + 10,
            BIG_THING + 10,
            BIG_THING + 10,
        )
        belt_deflector_trimmer = align(
            belt_deflector_trimmer,
            belt_deflector,
            Alignment.CENTER,
        )
        belt_deflector_trimmer = align(
            belt_deflector_trimmer,
            clamp_side_plates,
            Alignment.BACK,
        )
        belt_deflector = belt_deflector.cut(belt_deflector_trimmer)
        belt_deflector = align(
            belt_deflector,
            clamp_side_plates,
            clamp_side.stack_alignment,
            stack_gap=tool_head_mount_belt_deflector_belt_clearance,
        )

        bdc_x_size = (
            tool_head_mount_belt_deflector_belt_clearance
            + tool_head_mount_belt_deflector_thickness
            + tool_head_mount_belt_deflector_cage_thickness
        )
        bdc_y_size = 2 * tool_head_mount_belt_deflector_cage_thickness
        bdc_z_size = (
            current_belt_path_cutter_size[2]
            + 2 * tool_head_mount_belt_deflector_cage_thickness
        )

        belt_deflector_cage = create_box(bdc_x_size, bdc_y_size, bdc_z_size)
        bdc_cutter = create_box(
            bdc_x_size - tool_head_mount_belt_deflector_cage_thickness,
            bdc_y_size - tool_head_mount_belt_deflector_cage_thickness,
            bdc_z_size
            - 2 * tool_head_mount_belt_deflector_cage_thickness
            + 2 * tool_head_mount_belt_path_cutter_clearance,
        )
        bdc_cutter = align(bdc_cutter, belt_deflector_cage, Alignment.CENTER)
        bdc_cutter = align(bdc_cutter, belt_deflector_cage, Alignment.FRONT)
        bdc_cutter = align(bdc_cutter, belt_deflector_cage, clamp_side.opposite)
        belt_deflector_cage = belt_deflector_cage.cut(bdc_cutter)
        belt_deflector_cage = align(
            belt_deflector_cage,
            belt_deflector,
            Alignment.CENTER,
        )
        belt_deflector_cage = align(
            belt_deflector_cage,
            belt_deflector,
            Alignment.STACK_FRONT,
        )
        belt_deflector_cage = align(
            belt_deflector_cage,
            clamp_side_plates,
            clamp_side.stack_alignment,
        )

        bcd_belt_path_cutter = create_box(
            tool_head_mount_belt_deflector_belt_clearance,
            BIG_THING,
            current_belt_path_cutter_size[2]
            + 2 * tool_head_mount_belt_path_cutter_clearance,
        )
        bcd_belt_path_cutter = align(
            bcd_belt_path_cutter,
            belt_deflector,
            Alignment.CENTER,
        )
        bcd_belt_path_cutter = align(
            bcd_belt_path_cutter,
            belt_deflector,
            clamp_side.opposite.stack_alignment,
        )
        belt_deflector_cage = belt_deflector_cage.cut(bcd_belt_path_cutter)

        belt_deflectors = belt_deflectors.fuse(belt_deflector)
        belt_deflectors = belt_deflectors.fuse(belt_deflector_cage)

    clamp_side_plates = clamp_side_plates.cut(clamp_cutter)
    clamp_side_plates = clamp_side_plates.cut(bases_cutter)
    clamp_side_plates = clamp_side_plates.cut(belt_path_cutter)

    bridge = _create_rotated_hollow_bridge(
        bridge_width=get_bounding_box_size(clamp.leader)[0],
        bridge_outer_size=max(
            x_axis_belt_carriage_bridge_depth,
            x_axis_belt_carriage_bridge_web_height,
        ),
        bridge_wall_thickness=x_axis_belt_carriage_bridge_thickness,
        belt_deflectors=belt_deflectors,
        x_reference_part=clamp.leader,
        axis_profile=axis_profile,
        sprite_alignment_reference=sprite_alignment_reference,
        bridge_clearance_to_sprite=x_axis_belt_carriage_bridge_clearance_to_sprite,
    )
    mount_eyes, mount_eye_cutters = _create_mount_eyes(
        reference_part=bridge,
        drive_position=drive_alignment,
        mount_eye_thickness=x_axis_belt_carriage_mount_eye_thickness,
        mount_eye_length=x_axis_belt_carriage_mount_eye_length,
        mount_eye_width=x_axis_belt_carriage_mount_eye_width,
        mount_eye_hole_diameter=x_axis_belt_carriage_mount_eye_hole_diameter,
        mount_eye_fillet_radius=x_axis_belt_carriage_mount_eye_fillet_radius,
        big_thing=BIG_THING,
    )

    leader = clamp_side_plates.fuse(bridge)
    leader = leader.fuse(mount_eyes)
    leader = leader.fuse(clamp.leader)
    leader = leader.fuse(belt_deflectors)

    assembly = LeaderFollowersCuttersPart(leader=leader)
    assembly.add_named_follower(clamp.get_follower_part_by_name("clamp_1"), "clamp_1")
    assembly.add_named_follower(clamp.get_follower_part_by_name("clamp_2"), "clamp_2")

    for name, non_production_part in clamp.get_named_non_production_part_items():
        assembly.add_named_non_production_part(non_production_part, name)
    for cutter_name, cutter in mount_eye_cutters:
        assembly.add_named_cutter(cutter, cutter_name)

    assembly.additional_data["drive_position"] = normalized_drive_position
    return assembly
