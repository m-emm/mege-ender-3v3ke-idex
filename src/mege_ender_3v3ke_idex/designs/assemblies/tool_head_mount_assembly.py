"""Declarative tool head mount assembly."""

import numpy as np
from mege_ender_3v3ke_idex.designs.nema_motors import NemaSizes
from shellforgepy.simple import *


def _create_sprite_mount_hole_guides(*, mount_hole_cutter):
    mount_hole_cutter_bbox = get_bounding_box(mount_hole_cutter)
    mount_hole_cutter_size = get_bounding_box_size(mount_hole_cutter)
    mount_hole_cutter_center = get_bounding_box_center(mount_hole_cutter)

    mount_hole_diameter = mount_hole_cutter_size[0] - NemaSizes.NEMA17.hole_dist_mm
    if mount_hole_diameter <= 0:
        raise ValueError(
            "Sprite extruder mount hole cutter bbox does not match a NEMA17 pattern"
        )

    hole_radius = mount_hole_diameter / 2
    hole_length = mount_hole_cutter_size[1]
    top_hole_center_z = mount_hole_cutter_bbox[1][2] - hole_radius
    hole_centers_x = [
        mount_hole_cutter_bbox[0][0] + hole_radius,
        mount_hole_cutter_bbox[1][0] - hole_radius,
    ]

    hole_guides = []
    for side_name, hole_center_x in zip(["left", "right"], hole_centers_x):
        hole = create_cylinder(hole_radius, hole_length, direction=(0, 1, 0))
        hole = align(hole, mount_hole_cutter, Alignment.CENTER)
        hole = translate(
            hole_center_x - mount_hole_cutter_center[0],
            0,
            top_hole_center_z - mount_hole_cutter_center[2],
        )(hole)
        hole_guides.append((side_name, hole))

    return hole_guides


def _create_sprite_mount_screws(
    *,
    mount_hole_cutter,
    mount_base_plate,
    screw_size,
    screw_length,
):
    cylinder_head_height = MScrew.from_size(screw_size).cylinder_head_height
    screws = []

    for side_name, hole_guide in _create_sprite_mount_hole_guides(
        mount_hole_cutter=mount_hole_cutter,
    ):
        screw = create_cylinder_screw(screw_size, screw_length)
        screw = rotate(-90, axis=(1, 0, 0))(screw)
        screw = align(screw, hole_guide, Alignment.CENTER)
        screw = align(screw, mount_base_plate, Alignment.BACK)
        screw = translate(0, cylinder_head_height, 0)(screw)
        screws.append((side_name, screw))

    return screws


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
    x_axis_belt_carriage,
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

    x_axis_belt_carriage_size = get_bounding_box_size(x_axis_belt_carriage)
    x_axis_belt_carriage_center = get_bounding_box_center(x_axis_belt_carriage)
    belt_carriage_top_z = (
        x_axis_belt_carriage_center[2] + x_axis_belt_carriage_size[2] / 2
    )

    upper_side_plate_height = max(
        belt_carriage_top_z - carriage_mount_plate_top_z + 2,
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


def create_tool_head_mount_assembly(
    *,
    carriage,
    sprite_extruder,
    x_axis_belt_carriage,
    extruder_mount_screw_size,
    tool_head_mount_base_plate_height,
    tool_head_mount_base_plate_thickness,
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
    tool_head_mount_extruder_cutout_carriage_gap,
    tool_head_mount_extruder_cutout_fillet_radius,
    tool_head_mount_extruder_cutout_width,
    tool_head_mount_plate_carriage_clearance,
    tool_head_mount_side_plate_depth,
    tool_head_mount_side_plate_height,
    tool_head_mount_side_plate_thickness,
    tool_head_mount_side_stiffener_thickness,
    tool_head_mount_sprite_mount_screw_length,
    tool_head_mount_tool_head_base_plate_clearance,
    tool_head_mount_tool_head_x_offset,
    tool_head_mount_tool_head_z_offset,
    tool_head_mount_x_offset,
    tool_head_mount_y_extension,
    drive_position,
    tool_head_mount_top_box_wall,
    tool_head_mount_top_box_height,
    BIG_THING,
):
    """Create a single tool head mount assembly."""

    big_thing = BIG_THING
    normalized_drive_position = str(drive_position).strip().lower()
    if normalized_drive_position == "bottom":
        drive_position = Alignment.BOTTOM
    elif normalized_drive_position == "top":
        drive_position = Alignment.TOP
    else:
        raise ValueError(f"Unsupported drive_position '{drive_position}'")

    carriage_size = get_bounding_box_size(carriage)

    base_plate_width = tool_head_mount_carriage_mount_plate_width
    if drive_position == Alignment.BOTTOM:
        base_plate_width -= 2 * tool_head_mount_side_plate_thickness
    else:
        base_plate_width += tool_head_mount_side_plate_thickness

    carriage_mount_plate = create_filleted_box(
        tool_head_mount_carriage_mount_plate_width,
        carriage_size[1] + tool_head_mount_y_extension,
        tool_head_mount_carriage_mount_plate_thickness,
        fillet_radius=tool_head_mount_carriage_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.CENTER)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.STACK_TOP,
    )
    carriage_mount_plate = align(carriage_mount_plate, carriage, Alignment.BACK)
    carriage_mount_plate = align(
        carriage_mount_plate,
        carriage,
        Alignment.RIGHT if drive_position == Alignment.BOTTOM else Alignment.LEFT,
    )

    carriage_mount_plate = carriage.use_as_cutter_on(carriage_mount_plate)

    mount_base_plate = create_box(
        base_plate_width,
        tool_head_mount_base_plate_thickness,
        tool_head_mount_base_plate_height,
    )
    mount_base_plate = align(mount_base_plate, carriage_mount_plate, Alignment.CENTER)
    mount_base_plate = align(
        mount_base_plate,
        carriage_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    mount_base_plate = align(
        mount_base_plate,
        sprite_extruder,
        Alignment.STACK_BACK,
    )

    if drive_position == Alignment.TOP:
        mount_base_plate = align(
            mount_base_plate,
            carriage_mount_plate,
            Alignment.RIGHT,
        )

    mount_hole_cutter = sprite_extruder.get_named_cutter("mount_hole_cutter")

    mount_base_plate = mount_base_plate.cut(mount_hole_cutter)
    mount_base_plate = mount_base_plate.cut(sprite_extruder.leader)
    sprite_mount_screws = _create_sprite_mount_screws(
        mount_hole_cutter=mount_hole_cutter,
        mount_base_plate=mount_base_plate,
        screw_size=extruder_mount_screw_size,
        screw_length=tool_head_mount_sprite_mount_screw_length,
    )

    extruder_cutout = create_filleted_box(
        tool_head_mount_extruder_cutout_width,
        big_thing,
        big_thing,
        fillet_radius=tool_head_mount_extruder_cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    extruder_cutout = align(extruder_cutout, carriage_mount_plate, Alignment.CENTER)
    extruder_cutout = align(extruder_cutout, sprite_extruder, Alignment.RIGHT)
    extruder_cutout = align(extruder_cutout, sprite_extruder, Alignment.BACK)

    carriage_mount_plate = carriage_mount_plate.cut(extruder_cutout)

    carriage_mount_plate_size = get_bounding_box_size(carriage_mount_plate)

    top_box_center_wall = create_box(
        carriage_mount_plate_size[0]
        - 2 * tool_head_mount_carriage_mount_plate_fillet_radius,
        tool_head_mount_top_box_wall,
        tool_head_mount_top_box_height,
    )

    top_box_center_wall = align(
        top_box_center_wall, carriage_mount_plate, Alignment.CENTER
    )

    top_box_center_wall = align(
        top_box_center_wall, carriage, Alignment.CENTER, axes=[1]
    )

    top_box_center_wall = align(
        top_box_center_wall, carriage_mount_plate, Alignment.STACK_TOP
    )

    top_box_side_walls = PartCollector()
    for top_box_side in [Alignment.LEFT, Alignment.RIGHT]:
        top_box_side_wall = create_box(
            tool_head_mount_top_box_wall,
            carriage_mount_plate_size[1]
            - 2 * tool_head_mount_carriage_mount_plate_fillet_radius,
            tool_head_mount_top_box_height,
        )
        top_box_side_wall = align(
            top_box_side_wall, carriage_mount_plate, Alignment.CENTER
        )
        top_box_side_wall = align(
            top_box_side_wall, carriage_mount_plate, Alignment.STACK_TOP
        )
        top_box_side_wall = align(top_box_side_wall, carriage_mount_plate, top_box_side)
        top_box_side_wall = translate(
            -top_box_side.sign * tool_head_mount_carriage_mount_plate_fillet_radius,
            0,
            0,
        )(top_box_side_wall)

        top_box_side_walls = top_box_side_walls.fuse(top_box_side_wall)

    hollow_top_side_box = create_box(
        carriage_mount_plate_size[0] / 2,
        carriage_size[1],
        tool_head_mount_top_box_height,
    )
    hollow_top_side_box_inside_cutter = create_box(
        carriage_mount_plate_size[0] / 2 - 2 * tool_head_mount_top_box_wall,
        carriage_size[1] - 2 * tool_head_mount_top_box_wall,
        tool_head_mount_top_box_height - 2 * tool_head_mount_top_box_wall,
    )
    hollow_top_side_box_inside_cutter = align(
        hollow_top_side_box_inside_cutter,
        hollow_top_side_box,
        Alignment.CENTER,
    )
    hollow_top_side_box = hollow_top_side_box.cut(hollow_top_side_box_inside_cutter)

    hollow_top_side_box = align(
        hollow_top_side_box,
        top_box_side_walls,
        Alignment.CENTER,
    )

    hollow_top_side_box = align(
        hollow_top_side_box,
        top_box_side_walls,
        Alignment.BACK,
    )

    hollow_top_side_box = align(
        hollow_top_side_box,
        top_box_side_walls,
        Alignment.LEFT if drive_position == Alignment.BOTTOM else Alignment.RIGHT,
    )

    carriage_mount_plate = carriage_mount_plate.fuse(hollow_top_side_box)

    carriage_mount_plate = carriage_mount_plate.fuse(top_box_side_walls)
    carriage_mount_plate = carriage_mount_plate.fuse(top_box_center_wall)

    end_of_extruder_helper = create_box(100, 1, 100)
    end_of_extruder_helper = align(
        end_of_extruder_helper, sprite_extruder, Alignment.CENTER
    )
    end_of_extruder_helper = align(
        end_of_extruder_helper, sprite_extruder, Alignment.STACK_FRONT
    )

    mount_block_size = 8

    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        mount_block = create_box(mount_block_size, mount_block_size, mount_block_size)
        mount_block = align(mount_block, sprite_extruder, Alignment.CENTER)
        mount_block = align(mount_block, sprite_extruder, lr.stack_alignment)
        mount_block = align(mount_block, sprite_extruder, Alignment.TOP)
        mount_block = align(mount_block, sprite_extruder, Alignment.FRONT)
        mount_block = translate(0, 0, -5)(mount_block)
        carriage_mount_plate = carriage_mount_plate.fuse(mount_block)

        marker = create_box(8, 7, 7)

        part_to_align_to = (
            mount_base_plate
            if drive_position == Alignment.BOTTOM
            else carriage_mount_plate
        )

        marker = align(marker, part_to_align_to, Alignment.CENTER)
        marker = align(marker, mount_base_plate, Alignment.STACK_TOP, stack_gap=1)
        marker = align(
            marker,
            part_to_align_to,
            lr.stack_alignment if drive_position == Alignment.BOTTOM else lr,
        )
        marker = align(marker, mount_base_plate, Alignment.FRONT)

        marker_bb_center = np.array(get_bounding_box_center(marker))
        mount_block_bb_center = np.array(get_bounding_box_center(mount_block))
        dist = np.linalg.norm(marker_bb_center - mount_block_bb_center)
        radius = dist / 2

        third_point = (
            (marker_bb_center[0] + mount_block_bb_center[0]) / 2,
            (marker_bb_center[1] + mount_block_bb_center[1]) / 2,
            mount_block_bb_center[2] - 20,
        )

        mount_segment_width = 25
        mount_segment_start = marker_bb_center + np.array(
            [0, 0, mount_segment_width / 4]
        )
        mount_segment_end = mount_block_bb_center + np.array(
            [0, -mount_segment_width / 4, mount_segment_width / 4]
        )

        mount_segment = create_ring_segment_between_points(
            mount_segment_start,
            mount_segment_end,
            third_point,
            inner_radius=radius,
            outer_radius=radius + mount_segment_width,
            height=8,
        )
        mount_segment = mount_segment.cut(sprite_extruder.leader)
        carriage_mount_plate = carriage_mount_plate.fuse(mount_segment)

    tool_head_mount = carriage_mount_plate
    tool_head_mount = tool_head_mount.fuse(mount_base_plate)

    belt_carriage_mount_screws = []
    belt_carriage_mount_screw_length = 50
    belt_carriage_mount_screw_size = "M3"
    belt_carriage_mount_screw_head_clearance = 1.5
    belt_carriage_mount_screw_tower_wall = 3.3

    belt_carriage_mount_screw_tower_size = (
        MScrew.from_size(belt_carriage_mount_screw_size).cylinder_head_diameter / 2
        + 2 * belt_carriage_mount_screw_head_clearance
        + 2 * belt_carriage_mount_screw_tower_wall
    )

    mount_towers = PartCollector()

    top_of_tool_head_mount = create_box(BIG_THING, BIG_THING, 1)
    top_of_tool_head_mount = align(
        top_of_tool_head_mount, tool_head_mount, Alignment.CENTER
    )
    top_of_tool_head_mount = align(
        top_of_tool_head_mount, tool_head_mount, Alignment.STACK_TOP
    )

    for name, part in x_axis_belt_carriage.get_named_cutter_items():
        mount_box = create_box(8, 8, 15)
        mount_box = align(mount_box, part, Alignment.CENTER)
        mount_box = align(
            mount_box,
            x_axis_belt_carriage,
            (
                Alignment.STACK_BOTTOM
                if drive_position == Alignment.TOP
                else Alignment.STACK_TOP
            ),
        )
        mount_box = mount_box.cut(sprite_extruder.leader)
        tool_head_mount = tool_head_mount.fuse(mount_box)

        belt_carriage_mount_screw_tower = create_cylinder(
            belt_carriage_mount_screw_tower_size / 2,
            BIG_THING,
        )

        belt_carriage_mount_screw_tower = align(
            belt_carriage_mount_screw_tower,
            part,
            Alignment.CENTER,
        )

        belt_carriage_mount_screw_tower = align(
            belt_carriage_mount_screw_tower,
            x_axis_belt_carriage,
            Alignment.STACK_TOP,
        )

        belt_carriage_mount_screw_tower = fit_part_between(
            belt_carriage_mount_screw_tower,
            cut_normal=(0, 0, 1),
            limiting_start_part=top_of_tool_head_mount,
            limiting_end_part=x_axis_belt_carriage,
        )

        belt_carriage_mount_screw = create_cylinder_screw(
            "M3", belt_carriage_mount_screw_length
        )

        belt_carriage_mount_screw = align(
            belt_carriage_mount_screw, part, Alignment.CENTER
        )
        belt_carriage_mount_screw = align(
            belt_carriage_mount_screw, carriage_mount_plate, Alignment.TOP
        )

        belt_carriage_mount_screw_head_cutter = create_cylinder(
            MScrew.from_size(belt_carriage_mount_screw_size).cylinder_head_diameter / 2
            + belt_carriage_mount_screw_head_clearance,
            BIG_THING,
        )
        belt_carriage_mount_screw_head_cutter = align(
            belt_carriage_mount_screw_head_cutter,
            belt_carriage_mount_screw,
            Alignment.CENTER,
        )
        belt_carriage_mount_screw_head_cutter = align(
            belt_carriage_mount_screw_head_cutter,
            x_axis_belt_carriage,
            Alignment.BOTTOM,
        )

        belt_carriage_mount_screw_head_cutter = translate(
            0, 0, belt_carriage_mount_screw_length - 3.5
        )(belt_carriage_mount_screw_head_cutter)

        tool_head_mount = tool_head_mount.cut(belt_carriage_mount_screw_head_cutter)

        belt_carriage_mount_screw = align(
            belt_carriage_mount_screw,
            belt_carriage_mount_screw_head_cutter,
            Alignment.STACK_BOTTOM,
        )
        belt_carriage_mount_screw = translate(
            0, 0, MScrew.from_size(belt_carriage_mount_screw_size).cylinder_head_height
        )(belt_carriage_mount_screw)

        if drive_position == Alignment.TOP:
            belt_carriage_mount_screw = align(
                belt_carriage_mount_screw,
                x_axis_belt_carriage,
                Alignment.TOP,
            )
            belt_carriage_mount_screw = translate(
                0,
                0,
                MScrew.from_size(belt_carriage_mount_screw_size).cylinder_head_height,
            )(belt_carriage_mount_screw)

        belt_carriage_mount_screws.append(belt_carriage_mount_screw)

        if drive_position == Alignment.BOTTOM:
            belt_carriage_mount_screw_tower = belt_carriage_mount_screw_tower.cut(
                belt_carriage_mount_screw_head_cutter
            )
            belt_carriage_mount_screw_tower = belt_carriage_mount_screw_tower.cut(part)
            mount_towers = mount_towers.fuse(belt_carriage_mount_screw_tower)

    if drive_position == Alignment.BOTTOM:
        tool_head_mount = mount_towers.fuse(tool_head_mount)

    tool_head_mount = x_axis_belt_carriage.use_as_cutter_on(tool_head_mount)

    x_axis_belt_carriage_cutter = materialize_bounding_box(
        x_axis_belt_carriage, x_enlargement=5, y_enlargement=0.2, z_enlargement=0.2
    )
    tool_head_mount = tool_head_mount.cut(x_axis_belt_carriage_cutter)

    for name, cutter in sprite_extruder.get_named_cutter_items():
        if "mount_hole" in name:
            tool_head_mount = tool_head_mount.cut(cutter)

    tool_head_mount = LeaderFollowersCuttersPart(leader=tool_head_mount)

    for side_name, screw in sprite_mount_screws:
        tool_head_mount.add_named_non_production_part(
            screw,
            f"sprite_mount_screw_{side_name}",
        )

    for i, screw in enumerate(belt_carriage_mount_screws):
        tool_head_mount.add_named_non_production_part(
            screw,
            f"belt_carriage_mount_screw_{i}",
        )
    tool_head_mount.add_named_cutter(mount_hole_cutter, "mount_hole_cutter")
    return tool_head_mount
