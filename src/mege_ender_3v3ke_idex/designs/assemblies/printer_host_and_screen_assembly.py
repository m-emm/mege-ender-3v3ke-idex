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

    arc_reach = tft_housing_border

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

    return housing


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

    move_raspi_to_center = align_translation(
        raspberry_pi_assembly.leader,
        tft,
        Alignment.CENTER,
        axes=[0, 1],
    )
    raspi = move_raspi_to_center(raspberry_pi_assembly)

    raspi_mount_cylinders = create_raspi_mount_cylinders(raspi, tft)

    assembly = LeaderFollowersCuttersPart(housing)
    assembly.add_named_non_production_part(tft.leaders_followers_fused(), "tft_43")
    assembly.add_named_non_production_part(
        raspi_mount_cylinders,
        "raspberry_pi_standoffs",
    )

    return assembly
