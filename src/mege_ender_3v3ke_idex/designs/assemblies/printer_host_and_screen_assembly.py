"""Printer host and screen assembly."""

import logging
import math

import numpy as np
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

BIG_THING = 500

tft_height = 67.3
tft_width = 105.75
tft_with_board_thickness = 7.6
tft_screw_holder_height = 6.2
tft_screw_holder_diameter = 5.52
tft_screw_size = "M3"
tft_screw_cylinder_head_clearance = 0.5
tft_screw_holders_inset = 1.4075
tft_screw_holders_envelope_width = tft_width - 2 * tft_screw_holders_inset
tft_screw_holders_envelope_height = tft_height - 2 * tft_screw_holders_inset

tft_screen_clearance = 0.5

raspi_mount_cylinder_diameter = 6
raspi_tft_hover_gap = 23

tft_housing_wall_thickness = 2.4
tft_housing_border = 20
tft_housing_fillet_radius = 4

tft_housing_height = 60
tft_housing_cut_height = tft_housing_height

tft_housing_front_screen_thickness = 2.5
tft_housing_screw_plate_size = 9
tft_housing_screw_plate_thickness = 3.5

tft_housing_air_hole_size = 4
tft_housing_air_hole_spacing = 10
tft_air_hole_border = 5

tft_housing_join_screw_size = "M4"
tft_housing_join_screw_length = 12
tft_housing_join_screw_edge_inset = 11
tft_housing_join_boss_radius = 6.5
tft_housing_join_boss_height = 9
tft_housing_join_nut_slack = 0.25
tft_housing_join_countersink_clearance = 0.3


def iter_housing_join_positions(part):
    bbox = get_bounding_box(part)
    min_x, min_y, min_z = bbox[0]
    max_x, max_y, _ = bbox[1]

    for left_right in [Alignment.LEFT, Alignment.RIGHT]:
        x = (
            min_x + tft_housing_join_screw_edge_inset
            if left_right == Alignment.LEFT
            else max_x - tft_housing_join_screw_edge_inset
        )
        for front_back in [Alignment.FRONT, Alignment.BACK]:
            y = (
                min_y + tft_housing_join_screw_edge_inset
                if front_back == Alignment.FRONT
                else max_y - tft_housing_join_screw_edge_inset
            )
            name = f"{left_right.name.lower()}_{front_back.name.lower()}"
            yield name, left_right, front_back, np.array([x, y, min_z])


def create_housing_join_front_panel_cutter(front_panel):
    screw = MScrew.from_size(tft_housing_join_screw_size)
    cutter = PartCollector()

    for _, _, _, center in iter_housing_join_positions(front_panel):
        hole = create_cylinder(
            screw.clearance_hole_loose / 2,
            BIG_THING,
            origin=(center[0], center[1], center[2] - BIG_THING / 2),
        )
        cutter = cutter.fuse(hole)

        countersink = create_cone(
            radius1=screw.conical_head_diameter / 2
            + tft_housing_join_countersink_clearance,
            radius2=screw.clearance_hole_loose / 2,
            height=screw.conical_head_height + tft_housing_join_countersink_clearance,
            origin=(center[0], center[1], center[2] - 1e-3),
        )
        cutter = cutter.fuse(countersink)

    return cutter


def create_housing_join_hardware(front_panel, housing_body):
    screw = MScrew.from_size(tft_housing_join_screw_size)
    body_bbox = get_bounding_box(housing_body)
    body_bottom = body_bbox[0][2]
    boss_top = body_bottom + tft_housing_join_boss_height

    hardware = []
    for name, _, _, center in iter_housing_join_positions(front_panel):
        visual_screw = create_conical_head_screw(
            tft_housing_join_screw_size,
            tft_housing_join_screw_length,
        )
        visual_screw = rotate(180, axis=(1, 0, 0))(visual_screw)
        visual_screw = translate(
            center[0],
            center[1],
            center[2] + tft_housing_join_screw_length,
        )(visual_screw)
        hardware.append((f"housing_join_screw_{name}", visual_screw))

        nut = create_nut(tft_housing_join_screw_size)
        nut = rotate(30)(nut)
        nut = translate(
            center[0],
            center[1],
            boss_top - screw.nut_thickness - tft_housing_join_nut_slack,
        )(nut)
        hardware.append((f"housing_join_nut_{name}", nut))

    return hardware


def create_tft():
    tft_with_board = create_box(tft_width, tft_height, tft_with_board_thickness)

    screw_holders = []
    for left_right in [Alignment.LEFT, Alignment.RIGHT]:
        for front_back in [Alignment.FRONT, Alignment.BACK]:
            screw_holder = create_cylinder(
                tft_screw_holder_diameter / 2,
                tft_screw_holder_height,
            )
            screw_holder = align(screw_holder, tft_with_board, left_right)
            screw_holder = align(screw_holder, tft_with_board, front_back)
            screw_holder = align(screw_holder, tft_with_board, Alignment.STACK_TOP)
            screw_holder = translate(
                -left_right.sign * tft_screw_holders_inset,
                -front_back.sign * tft_screw_holders_inset,
                0,
            )(screw_holder)
            screw_holders.append(screw_holder)

    screw_holders_fused = PartCollector()
    for screw_holder in screw_holders:
        screw_holders_fused = screw_holders_fused.fuse(screw_holder)

    screw_holders_fused_size = get_bounding_box_size(screw_holders_fused)
    if not np.allclose(screw_holders_fused_size[0], tft_screw_holders_envelope_width):
        raise ValueError(
            f"Screw holders fused width {screw_holders_fused_size[0]} does not "
            f"match expected envelope width {tft_screw_holders_envelope_width}"
        )
    if not np.allclose(screw_holders_fused_size[1], tft_screw_holders_envelope_height):
        raise ValueError(
            f"Screw holders fused height {screw_holders_fused_size[1]} does not "
            f"match expected envelope height {tft_screw_holders_envelope_height}"
        )

    tft_with_board = tft_with_board.fuse(screw_holders_fused)
    return LeaderFollowersCuttersPart(tft_with_board, followers=screw_holders)


def create_housing(tft):

    housing = create_filleted_box(
        tft_width
        + 2 * tft_housing_border
        + 2 * tft_screen_clearance
        + 2 * tft_housing_wall_thickness,
        tft_height
        + 2 * tft_housing_border
        + 2 * tft_screen_clearance
        + 2 * tft_housing_wall_thickness,
        tft_housing_front_screen_thickness,
        fillet_radius=tft_housing_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    housing_cutter = create_box(
        tft_width + 2 * tft_screen_clearance + 2 * tft_housing_border,
        tft_height + 2 * tft_screen_clearance + 2 * tft_housing_border,
        BIG_THING,
    )
    housing_cutter = align(housing_cutter, housing, Alignment.CENTER)
    housing_cutter = align(housing_cutter, housing, Alignment.BOTTOM)
    housing_cutter = translate(0, 0, tft_housing_front_screen_thickness)(housing_cutter)
    housing = housing.cut(housing_cutter)

    screen_cutter = create_box(
        tft_width + 2 * tft_screen_clearance,
        tft_height + 2 * tft_screen_clearance,
        BIG_THING,
    )
    screen_cutter = align(screen_cutter, housing, Alignment.CENTER)
    housing = housing.cut(screen_cutter)

    housing = align(housing, tft, Alignment.CENTER)
    housing = align(housing, tft, Alignment.BOTTOM)

    screw_plates = PartCollector()
    screw_drills = PartCollector()
    screw_plates_list = []
    for screw_holder in tft.followers:
        screw_plate = create_box(
            tft_housing_screw_plate_size,
            tft_housing_screw_plate_size,
            tft_housing_screw_plate_thickness,
        )
        screw_plate = align(screw_plate, screw_holder, Alignment.CENTER)
        screw_plate = align(screw_plate, screw_holder, Alignment.STACK_TOP)

        screw_hole_diameter = MScrew.from_size(tft_screw_size).clearance_hole_loose
        screw_hole = create_cylinder(screw_hole_diameter / 2, BIG_THING)
        screw_hole = align(screw_hole, screw_plate, Alignment.CENTER)
        screw_drills = screw_drills.fuse(screw_hole)

        screw_cylinder_drill = create_cylinder(
            MScrew.from_size(tft_screw_size).cylinder_head_diameter / 2
            + tft_screw_cylinder_head_clearance,
            BIG_THING,
        )
        screw_cylinder_drill = align(screw_cylinder_drill, screw_hole, Alignment.CENTER)
        screw_cylinder_drill = align(
            screw_cylinder_drill,
            screw_plate,
            Alignment.STACK_TOP,
        )
        screw_drills = screw_drills.fuse(screw_cylinder_drill)

        screw_plates = screw_plates.fuse(screw_plate)

        screw_plates_list.append(screw_plate)

    all_screw_plates_center = np.array(get_bounding_box_center(screw_plates))

    tft_bounding_box = get_bounding_box(tft)
    min_z = tft_bounding_box[0][2]

    arc_reach = tft_housing_border * 0.5

    screw_drills = PartCollector()

    for screw_plate in screw_plates_list:

        screw_hole_diameter = MScrew.from_size(tft_screw_size).clearance_hole_loose
        screw_hole = create_cylinder(screw_hole_diameter / 2, BIG_THING)
        screw_hole = align(screw_hole, screw_plate, Alignment.CENTER)
        screw_drills = screw_drills.fuse(screw_hole)

        screw_plate_center = np.array(get_bounding_box_center(screw_plate))
        p1 = np.array(screw_plate_center)
        direction = normalize(p1 - all_screw_plates_center)
        p1 += direction * (math.sqrt(2) * tft_housing_screw_plate_size / 2)

        p2 = p1 + direction * arc_reach

        p2[2] = min_z + tft_housing_front_screen_thickness / 2

        p3 = [p1[0], p1[1], min_z]

        screw_plate_support = create_ring_segment_between_points(
            p1,
            p2,
            p3,
            arc_reach * 4,
            arc_reach * 4 + tft_housing_screw_plate_thickness,
            tft_housing_screw_plate_size,
        )

        screw_plates = screw_plates.fuse(screw_plate_support)

        # screw_plate_support_extension = create_box(
        #     tft_housing_screw_plate_size,
        #     tft_housing_screw_plate_size,
        #     tft_housing_screw_plate_thickness,
        # )

        screw_plate_support_extension = create_cylinder(
            tft_housing_screw_plate_size / 2,
            tft_housing_screw_plate_thickness,
        )

        screw_plate_support_extension = rotate(45)(screw_plate_support_extension)
        screw_plate_support_extension = align(
            screw_plate_support_extension, screw_plate, Alignment.CENTER
        )

        extension_direction = normalize(np.sign(direction) * np.array([1, 1, 0]))
        (
            extension_rotation_axis,
            direction_to_extension_direction_angle,
        ) = shortest_arc_axis_angle(extension_direction, direction)
        screw_plate_support_extension = rotate(
            direction_to_extension_direction_angle,
            axis=tuple(extension_rotation_axis),
            center=tuple(screw_plate_center),
        )(screw_plate_support_extension)

        screw_plate_support_extension = translate(
            *(direction * tft_housing_screw_plate_size * math.sqrt(2) / 2)
        )(screw_plate_support_extension)
        screw_plate_extension_hull = create_convex_hull(
            screw_plate,
            screw_plate_support_extension,
        )
        screw_plates = screw_plates.fuse(screw_plate_extension_hull)

    screw_plates = screw_plates.cut(screw_drills)
    housing = housing.fuse(screw_plates)
    housing = housing.cut(create_housing_join_front_panel_cutter(housing))

    return housing


def create_housing_air_hole_cutter(housing_body):
    housing_size = get_bounding_box_size(housing_body)

    num_air_holes_width = math.floor(
        (housing_size[0] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )
    num_air_holes_height = math.floor(
        (housing_size[1] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )
    num_air_holes_z = math.floor(
        (housing_size[2] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )

    air_holes = PartCollector()
    air_holes_front_back = PartCollector()
    for i in range(num_air_holes_width):
        for j in range(num_air_holes_z):
            air_hole = create_box(
                tft_housing_air_hole_size,
                BIG_THING,
                tft_housing_air_hole_size,
            )
            air_hole = rotate(45, axis=(0, 1, 0))(air_hole)
            air_hole = translate(
                i * tft_housing_air_hole_spacing,
                0,
                j * tft_housing_air_hole_spacing,
            )(air_hole)
            air_holes_front_back = air_holes_front_back.fuse(air_hole)

    air_holes_front_back = align(air_holes_front_back, housing_body, Alignment.CENTER)
    air_holes = air_holes.fuse(air_holes_front_back)

    air_holes_left_right = PartCollector()
    for i in range(num_air_holes_height):
        for j in range(num_air_holes_z):
            air_hole = create_box(
                BIG_THING,
                tft_housing_air_hole_size,
                tft_housing_air_hole_size,
            )
            air_hole = rotate(45, axis=(1, 0, 0))(air_hole)
            air_hole = translate(
                0,
                i * tft_housing_air_hole_spacing,
                j * tft_housing_air_hole_spacing,
            )(air_hole)
            air_holes_left_right = air_holes_left_right.fuse(air_hole)

    air_holes_left_right = align(air_holes_left_right, housing_body, Alignment.CENTER)
    air_holes = air_holes.fuse(air_holes_left_right)

    return air_holes


def create_housing_join_receptacles(front_panel, housing_body):
    screw = MScrew.from_size(tft_housing_join_screw_size)
    body_bbox = get_bounding_box(housing_body)
    body_min = np.array(body_bbox[0])
    body_max = np.array(body_bbox[1])
    body_bottom = body_min[2]
    boss_top = body_bottom + tft_housing_join_boss_height
    bridge_width = tft_housing_join_boss_radius * 1.25

    receptacles = PartCollector()
    cutters = PartCollector()

    for _, left_right, front_back, center in iter_housing_join_positions(front_panel):
        boss = create_cylinder(
            tft_housing_join_boss_radius,
            tft_housing_join_boss_height,
            origin=(center[0], center[1], body_bottom),
        )
        receptacles = receptacles.fuse(boss)

        if left_right == Alignment.LEFT:
            bridge_x_min = body_min[0]
            bridge_x_max = center[0] + tft_housing_join_boss_radius
        else:
            bridge_x_min = center[0] - tft_housing_join_boss_radius
            bridge_x_max = body_max[0]
        x_bridge = create_box(
            bridge_x_max - bridge_x_min,
            bridge_width,
            tft_housing_join_boss_height,
            origin=(
                bridge_x_min,
                center[1] - bridge_width / 2,
                body_bottom,
            ),
        )
        receptacles = receptacles.fuse(x_bridge)

        if front_back == Alignment.FRONT:
            bridge_y_min = body_min[1]
            bridge_y_max = center[1] + tft_housing_join_boss_radius
        else:
            bridge_y_min = center[1] - tft_housing_join_boss_radius
            bridge_y_max = body_max[1]
        y_bridge = create_box(
            bridge_width,
            bridge_y_max - bridge_y_min,
            tft_housing_join_boss_height,
            origin=(
                center[0] - bridge_width / 2,
                bridge_y_min,
                body_bottom,
            ),
        )
        receptacles = receptacles.fuse(y_bridge)

        hole = create_cylinder(
            screw.clearance_hole_loose / 2,
            tft_housing_join_boss_height + 2,
            origin=(center[0], center[1], body_bottom - 1),
        )
        cutters = cutters.fuse(hole)

        nut_height = screw.nut_thickness + 2 * tft_housing_join_nut_slack
        nut_pocket = create_nut(
            tft_housing_join_screw_size,
            height=nut_height,
            slack=tft_housing_join_nut_slack,
            no_hole=True,
        )
        nut_pocket = rotate(30)(nut_pocket)
        nut_pocket = translate(
            center[0],
            center[1],
            boss_top - nut_height,
        )(nut_pocket)
        cutters = cutters.fuse(nut_pocket)

    return receptacles.cut(cutters)


def create_housing_body(tft, front_panel):
    body_height = tft_housing_cut_height - tft_housing_front_screen_thickness

    housing_body = create_filleted_box(
        tft_width
        + 2 * tft_housing_border
        + 2 * tft_screen_clearance
        + 2 * tft_housing_wall_thickness,
        tft_height
        + 2 * tft_housing_border
        + 2 * tft_screen_clearance
        + 2 * tft_housing_wall_thickness,
        body_height,
        fillet_radius=tft_housing_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    housing_cutter = create_box(
        tft_width + 2 * tft_screen_clearance + 2 * tft_housing_border,
        tft_height + 2 * tft_screen_clearance + 2 * tft_housing_border,
        BIG_THING,
    )
    housing_cutter = align(housing_cutter, housing_body, Alignment.CENTER)
    housing_cutter = align(housing_cutter, housing_body, Alignment.BOTTOM)
    housing_body = housing_body.cut(housing_cutter)

    housing_body = align(housing_body, front_panel, Alignment.CENTER, axes=[0, 1])
    front_panel_bbox = get_bounding_box(front_panel)
    housing_body_bbox = get_bounding_box(housing_body)
    housing_body = translate(
        0,
        0,
        front_panel_bbox[0][2]
        + tft_housing_front_screen_thickness
        - housing_body_bbox[0][2],
    )(housing_body)

    housing_body = housing_body.cut(create_housing_air_hole_cutter(housing_body))
    housing_body = housing_body.fuse(
        create_housing_join_receptacles(front_panel, housing_body)
    )

    return housing_body


def create_raspi_mount_cylinders(raspi, tft):
    mount_cylinders = PartCollector()

    for cutter_name, cutter_part in raspi.get_named_cutter_items():
        if not cutter_name.startswith("mount_hole_"):
            continue

        mount_cylinder = create_cylinder(
            raspi_mount_cylinder_diameter / 2,
            raspi_tft_hover_gap,
        )
        mount_cylinder = align(
            mount_cylinder, cutter_part, Alignment.CENTER, axes=[0, 1]
        )
        mount_cylinder = align(mount_cylinder, tft, Alignment.BOTTOM)
        mount_cylinder = translate(0, 0, tft_with_board_thickness)(mount_cylinder)
        mount_cylinders = mount_cylinders.fuse(mount_cylinder)

    return mount_cylinders


def create_printer_host_and_screen_assembly(*, raspberry_pi_assembly):
    tft = create_tft()
    housing = create_housing(tft)

    housing_real_height_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    housing_real_height_cutter = align(
        housing_real_height_cutter,
        housing,
        Alignment.CENTER,
    )
    housing_real_height_cutter = align(
        housing_real_height_cutter,
        housing,
        Alignment.STACK_TOP,
        stack_gap=-(tft_housing_height - tft_housing_cut_height),
    )
    housing = housing.cut(housing_real_height_cutter)
    housing_body = create_housing_body(tft, housing)

    move_raspi_to_center = align_translation(
        raspberry_pi_assembly.leader,
        tft,
        Alignment.CENTER,
        axes=[0, 1],
    )
    raspi = move_raspi_to_center(raspberry_pi_assembly)

    raspi_mount_cylinders = create_raspi_mount_cylinders(raspi, tft)

    assembly = LeaderFollowersCuttersPart(housing)
    assembly.add_named_follower(housing_body, "housing_body")
    assembly.add_named_non_production_part(tft.leaders_followers_fused(), "tft_43")
    assembly.add_named_non_production_part(
        raspi_mount_cylinders,
        "raspberry_pi_standoffs",
    )
    for name, part in create_housing_join_hardware(housing, housing_body):
        assembly.add_named_non_production_part(part, name)

    return assembly
