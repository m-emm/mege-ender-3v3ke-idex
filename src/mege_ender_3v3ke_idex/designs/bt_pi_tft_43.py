"""
Bt Pi Tft 43

Usage:
    cd <project_root> && ./run.sh path/to/bt_pi_tft_43.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/bt_pi_tft_43.py
"""

import copy
import logging
import math
import os

import numpy as np
from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.sil_dil import (
    create_dil,
    dil_pitch,
    top_pin_length,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_side,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLACF_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "wall_loops": "2",
        "bottom_shell_layers": "1",
        "top_shell_layers": "1",
        "sparse_infill_density": "25%",
    }
)

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

tft_screw_holders_center_to_center_distance_width = (
    tft_screw_holders_envelope_width - tft_screw_holder_diameter
)
tft_screw_holders_center_to_center_distance_height = (
    tft_screw_holders_envelope_height - tft_screw_holder_diameter
)

tft_cable_width = 16
tft_cable_clearance = 1

tft_screen_clearance = 0.5
tft_button_2_offset = 26
tft_button_1_offset = 13.7

raspi_width = 56
raspi_flight_height = 24
raspi_inward_offset = 10
raspi_connections_height = 17.2

raspi_board_length = 85
raspi_board_width = raspi_width
raspi_board_corner_radius = 3
raspi_board_thickness = 1.3
raspi_screw_hole_diameter = 2.75
raspi_screw_hole_distance = 58
raspi_screw_hole_x_inset = 3.5
raspi_screw_hole_y_inset = raspi_board_corner_radius
raspi_mount_cylinder_diameter = 6

raspi_network_dist = 10.25
raspi_network_width = 16
raspi_network_length = 21.3
raspi_network_height = 13.6

raspi_usb_1_dist = 29
raspi_usb_2_dist = 47
raspi_usb_width = 13.3
raspi_usb_length = 17.3
raspi_usb_height = 15.44

raspi_connectors_oversize = 1
raspi_connector_overstand = 1.6

raspi_micro_usb_dist = 10.6
raspi_micro_usb_width = 8.07
raspi_micro_usb_length = 5.75
raspi_micro_usb_height = 3.1
raspi_micro_usb_overstand = 1

raspi_hdmi_width = 15.1
raspi_hdmi_height = 7
raspi_hdmi_length = 12
raspi_hdmi_overstand = 1
raspi_hdmi_dist = 32

raspi_jack_diameter = 6
raspi_jack_dist = 53.5
raspi_jack_length_cylinder = 2.6
raspi_jack_length_cube = 12.7

raspi_gpio_dist_y = 3.5 + 49
raspi_gpio_dist_x = 3.5 + 29
raspi_gpio_num_pins_per_row = 20
raspi_gpio_inner_x_distance_in_pins = 1
raspi_gpio_pin_pitch = dil_pitch
raspi_gpio_pin_side = wire_wrap_pin_side
raspi_gpio_pin_length = 7
raspi_gpio_base_thickness = wire_wrap_pin_base_thickness
raspi_gpio_top_pin_length = top_pin_length

raspi_microsd_socket_width = 13.1
raspi_microsd_socket_height = 1.3
raspi_microsd_socket_length = 14.35
raspi_microsd_thickness = 1.05
raspi_microsd_width = 11.1
raspi_microsd_overstand = 2.8

tft_visual_color = (0.82, 0.88, 0.92)
tft_housing_visual_color = (0.9, 0.9, 0.86)
raspi_pcb_color = (0.52, 0.78, 0.56)
raspi_connector_color = (0.96, 0.97, 0.97)
raspi_tft_hover_gap = 23

tft_housing_wall_thickness = 2.4
tft_housing_border = 20
tft_housing_fillet_radius = 4

tft_housing_height = 60
tft_housing_cut_height = tft_housing_height

tft_housing_front_screen_thickness = 2.5
tft_housing_lip_size = 0.75
tft_housing_screw_plate_size = 9
tft_housing_screw_plate_thickness = 3.5

tft_housing_air_hole_size = 4
tft_housing_air_hole_spacing = 10
tft_air_hole_border = 5


def creaate_tft():

    tft_with_board = create_box(tft_width, tft_height, tft_with_board_thickness)

    screw_holders = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for tb in [Alignment.FRONT, Alignment.BACK]:
            screw_holder = create_cylinder(
                tft_screw_holder_diameter / 2, tft_screw_holder_height
            )
            screw_holder = align(screw_holder, tft_with_board, lr)
            screw_holder = align(screw_holder, tft_with_board, tb)
            screw_holder = align(screw_holder, tft_with_board, Alignment.STACK_TOP)

            screw_holder = translate(
                -lr.sign * tft_screw_holders_inset,
                -tb.sign * tft_screw_holders_inset,
                0,
            )(screw_holder)
            screw_holders.append(screw_holder)

    screw_holders_fused = PartCollector()
    for screw_holder in screw_holders:
        screw_holders_fused = screw_holders_fused.fuse(screw_holder)

    screw_holders_fused_size = get_bounding_box_size(screw_holders_fused)

    if not np.allclose(screw_holders_fused_size[0], tft_screw_holders_envelope_width):

        raise ValueError(
            f"Screw holders fused width {screw_holders_fused_size[0]} does not match expected envelope width {tft_screw_holders_envelope_width}"
        )

    if not np.allclose(screw_holders_fused_size[1], tft_screw_holders_envelope_height):

        raise ValueError(
            f"Screw holders fused height {screw_holders_fused_size[1]} does not match expected envelope height {tft_screw_holders_envelope_height}"
        )

    tft_with_board = tft_with_board.fuse(screw_holders_fused)
    retval = LeaderFollowersCuttersPart(
        tft_with_board, followers=screw_holders, cutters=[]
    )

    return retval


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
        tft_housing_height,
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

    housing_size = get_bounding_box_size(housing)

    num_air_holes_width = math.floor(
        (housing_size[0] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )
    num_air_holes_height = math.floor(
        (housing_size[1] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )

    num_air_holes_z = math.ceil(
        (housing_size[2] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )

    air_holes_width = PartCollector()
    for i in range(num_air_holes_width):
        for j in range(num_air_holes_z):
            air_hole_cutter = create_box(
                tft_housing_air_hole_size, BIG_THING, tft_housing_air_hole_size
            )

            air_hole_cutter = rotate(45, axis=(0, 1, 0))(air_hole_cutter)

            air_hole_cutter = translate(
                i * tft_housing_air_hole_spacing, 0, j * tft_housing_air_hole_spacing
            )(air_hole_cutter)
            air_holes_width = air_holes_width.fuse(air_hole_cutter)

    air_holes_width = align(air_holes_width, housing, Alignment.CENTER)

    housing = housing.cut(air_holes_width)

    air_holes_height = PartCollector()
    for i in range(num_air_holes_height):
        for j in range(num_air_holes_z):
            air_hole_cutter = create_box(
                BIG_THING,
                tft_housing_air_hole_size,
                tft_housing_air_hole_size,
            )

            air_hole_cutter = rotate(45, axis=(1, 0, 0))(air_hole_cutter)

            air_hole_cutter = translate(
                0, i * tft_housing_air_hole_spacing, j * tft_housing_air_hole_spacing
            )(air_hole_cutter)
            air_holes_height = air_holes_height.fuse(air_hole_cutter)

    air_holes_height = align(air_holes_height, housing, Alignment.CENTER)
    housing = housing.cut(air_holes_height)

    all_directions = [Alignment.LEFT, Alignment.RIGHT, Alignment.FRONT, Alignment.BACK]

    screw_plates = PartCollector()

    tft_center = np.array(get_bounding_box_center(tft))

    bridges = PartCollector()
    screw_drills = PartCollector()
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
            screw_cylinder_drill, screw_plate, Alignment.STACK_TOP
        )
        screw_drills = screw_drills.fuse(screw_cylinder_drill)

        screw_plates = screw_plates.fuse(screw_plate)

        screw_holder_center = np.array(get_bounding_box_center(screw_holder))

        direction_vector = screw_holder_center - tft_center
        direction_vector_signs = [int(math.copysign(1, v)) for v in direction_vector]

        _logger.info(
            f"Direction vector: {direction_vector}, signs: {direction_vector_signs}"
        )
        for direction in all_directions:
            if (
                direction_vector_signs[0] == direction.sign and direction.axis == 0
            ) or (direction_vector_signs[1] == direction.sign and direction.axis == 1):
                _logger.info(
                    f"Using direction {direction} for screw holder at {screw_holder_center}, direction signs  {direction_vector_signs} direction sign {direction.sign} and direction axis {direction.axis}"
                )
                bridge_length = (
                    tft_housing_border
                    + tft_screen_clearance
                    + tft_housing_wall_thickness * 0.25
                    + tft_screw_holders_inset
                    - tft_housing_wall_thickness / 2
                )
                bridge = create_box(
                    (
                        tft_housing_screw_plate_size
                        if direction.axis == 1
                        else bridge_length
                    ),
                    (
                        tft_housing_screw_plate_size
                        if direction.axis == 0
                        else bridge_length
                    ),
                    tft_housing_screw_plate_thickness,
                )
                bridge = align(bridge, screw_plate, Alignment.CENTER)
                bridge = align(bridge, screw_plate, direction.stack_alignment)
                bridges = bridges.fuse(bridge)

                print_helper = create_right_triangle(
                    bridge_length + tft_housing_screw_plate_size,
                    bridge_length + tft_housing_screw_plate_size,
                    tft_housing_screw_plate_size,
                    extrusion_direction=(
                        1 if direction.axis == 1 else 0,
                        1 if direction.axis == 0 else 0,
                        0,
                    ),
                    a_normal=(
                        direction.sign if direction.axis == 0 else 0,
                        direction.sign if direction.axis == 1 else 0,
                        0,
                    ),
                    b_normal=(0, 0, 1),
                )

                print_helper = align(print_helper, bridge, Alignment.CENTER)

                print_helper = align(print_helper, screw_plate, direction.opposite)
                print_helper = align(print_helper, bridge, Alignment.STACK_TOP)
                bridges = bridges.fuse(print_helper)

    housing_size = get_bounding_box_size(housing)
    housing_inner_length = (
        housing_size[0] - 2 * tft_housing_wall_thickness - 2 * tft_housing_fillet_radius
    )
    housing_inner_width = (
        housing_size[1] - 2 * tft_housing_wall_thickness - 2 * tft_housing_fillet_radius
    )

    border_print_helpers = []
    helper_size = (
        tft_housing_border + tft_screen_clearance + tft_housing_wall_thickness / 2
    )

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        _logger.info(
            f"Creating border print helper for {lr} with helper size {helper_size} and housing inner length {housing_inner_length}"
        )

        border_print_helper = create_right_triangle(
            helper_size,
            helper_size,
            housing_inner_width,
            extrusion_direction=(0, 1, 0),
            a_normal=(lr.sign, 0, 0),
            b_normal=(0, 0, 1),
        )
        border_print_helper = align(border_print_helper, housing, Alignment.CENTER)
        border_print_helper = align(border_print_helper, housing, Alignment.BOTTOM)
        border_print_helper = align(border_print_helper, housing, lr)

        border_print_helper = translate(
            0, 0, tft_housing_front_screen_thickness - 1e-1
        )(border_print_helper)

        border_print_helpers.append(border_print_helper)

    for fb in [Alignment.FRONT, Alignment.BACK]:
        _logger.info(
            f"Creating border print helper for {fb} with helper size {helper_size} and housing inner length {housing_inner_length}"
        )
        border_print_helper = create_right_triangle(
            helper_size,
            helper_size,
            housing_inner_length,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, fb.sign, 0),
            b_normal=(0, 0, 1),
        )
        border_print_helper = align(border_print_helper, housing, Alignment.CENTER)
        border_print_helper = align(border_print_helper, housing, Alignment.BOTTOM)

        border_print_helper = align(border_print_helper, housing, fb)
        border_print_helper = translate(
            0, 0, tft_housing_front_screen_thickness - 1e-1
        )(border_print_helper)

        border_print_helpers.append(border_print_helper)

    border_print_helpers_part_collector = PartCollector()
    for i, bph in enumerate(border_print_helpers):
        _logger.info(
            f"Adding border print helper to part collector: {i} / {len(border_print_helpers)}"
        )
        border_print_helpers_part_collector = border_print_helpers_part_collector.fuse(
            bph
        )

    border_print_helpers = translate(0, 0, 100)(border_print_helpers_part_collector)
    housing = housing.fuse(border_print_helpers_part_collector)

    bridges_and_screw_plates = bridges.fuse(screw_plates)
    bridges_and_screw_plates = bridges_and_screw_plates.cut(screw_drills)
    housing = housing.fuse(bridges_and_screw_plates)

    return housing


def create_raspi_board():

    raw_board = create_filleted_box(
        raspi_board_length,
        raspi_board_width,
        raspi_board_thickness,
        fillet_radius=raspi_board_corner_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    mount_hole_cutters = []
    mount_hole_cutter_names = []
    board_cutter = PartCollector()

    for left_right_name, hole_x in [
        ("left", raspi_screw_hole_x_inset),
        ("right", raspi_screw_hole_x_inset + raspi_screw_hole_distance),
    ]:
        for front_back_name, hole_y in [
            ("front", raspi_screw_hole_y_inset),
            ("back", raspi_board_width - raspi_screw_hole_y_inset),
        ]:
            hole = create_cylinder(raspi_screw_hole_diameter / 2, BIG_THING)
            hole = translate(hole_x, hole_y, -BIG_THING / 2)(hole)
            mount_hole_cutters.append(hole)
            board_cutter = board_cutter.fuse(hole)
            mount_hole_cutter_names.append(
                f"mount_hole_{left_right_name}_{front_back_name}"
            )

    board = raw_board.cut(board_cutter)

    raspi = LeaderFollowersCuttersPart(
        board,
        cutters=mount_hole_cutters,
        cutter_names=mount_hole_cutter_names,
    )

    network = create_box(
        raspi_network_length,
        raspi_network_width,
        raspi_network_height,
    )
    network = translate(
        raspi_board_length - raspi_network_length + raspi_connector_overstand,
        raspi_network_dist - raspi_network_width / 2,
        raspi_board_thickness,
    )(network)
    raspi.add_named_follower(network, "network")

    for usb_index, usb_dist in enumerate([raspi_usb_1_dist, raspi_usb_2_dist], start=1):
        usb = create_box(raspi_usb_length, raspi_usb_width, raspi_usb_height)
        usb = translate(
            raspi_board_length - raspi_usb_length + raspi_connector_overstand,
            usb_dist - raspi_usb_width / 2,
            raspi_board_thickness,
        )(usb)
        raspi.add_named_follower(usb, f"usb_{usb_index}")

    micro_usb = create_box(
        raspi_micro_usb_width,
        raspi_micro_usb_length,
        raspi_micro_usb_height,
    )
    micro_usb = translate(
        raspi_micro_usb_dist - raspi_micro_usb_width / 2,
        -raspi_micro_usb_overstand,
        raspi_board_thickness,
    )(micro_usb)
    raspi.add_named_follower(micro_usb, "micro_usb")

    hdmi = create_box(raspi_hdmi_width, raspi_hdmi_length, raspi_hdmi_height)
    hdmi = translate(
        raspi_hdmi_dist - raspi_hdmi_width / 2,
        -raspi_hdmi_overstand,
        raspi_board_thickness,
    )(hdmi)
    raspi.add_named_follower(hdmi, "hdmi")

    jack = create_box(
        raspi_jack_diameter,
        raspi_jack_length_cube,
        raspi_jack_diameter,
    )
    jack = translate(
        raspi_jack_dist - raspi_jack_diameter / 2,
        -raspi_jack_length_cylinder,
        raspi_board_thickness,
    )(jack)
    raspi.add_named_follower(jack, "jack")

    microsd_socket = create_box(
        raspi_microsd_socket_length,
        raspi_microsd_socket_width,
        raspi_microsd_socket_height,
    )
    microsd_socket = translate(
        0,
        raspi_board_width / 2 - raspi_microsd_socket_width / 2,
        -raspi_microsd_socket_height,
    )(microsd_socket)
    raspi.add_named_follower(microsd_socket, "microsd_socket")

    microsd_card = create_box(
        raspi_microsd_overstand,
        raspi_microsd_width,
        raspi_microsd_thickness,
    )
    microsd_card = translate(
        -raspi_microsd_overstand,
        raspi_board_width / 2 - raspi_microsd_width / 2,
        -(raspi_microsd_socket_height + raspi_microsd_thickness) / 2,
    )(microsd_card)
    raspi.add_named_follower(microsd_card, "microsd_card")

    raspi.add_named_follower(create_raspi_gpio(), "gpio")

    return raspi


def create_raspi_gpio():

    gpio = create_dil(
        raspi_gpio_inner_x_distance_in_pins,
        raspi_gpio_num_pins_per_row,
        pin_length=raspi_gpio_pin_length,
        pin_side=raspi_gpio_pin_side,
        top_pin_length=raspi_gpio_top_pin_length,
        base_thickness=raspi_gpio_base_thickness,
    )
    gpio = gpio.leaders_followers_fused()
    gpio = rotate(180, axis=(0, 1, 0))(gpio)
    gpio = rotate(-90, axis=(0, 0, 1))(gpio)

    gpio_center = np.array(get_bounding_box_center(gpio))
    gpio = translate(
        raspi_gpio_dist_x - gpio_center[0],
        raspi_gpio_dist_y - gpio_center[1],
        raspi_board_thickness,
    )(gpio)

    return gpio


def create_raspi_connectors(raspi):

    connectors = PartCollector()

    for _, connector_part in raspi.get_named_follower_items():
        connectors = connectors.fuse(connector_part)

    return connectors


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
            mount_cylinder,
            cutter_part,
            Alignment.CENTER,
            axes=[0, 1],
        )
        mount_cylinder = align(mount_cylinder, tft, Alignment.BOTTOM)
        mount_cylinder = translate(0, 0, tft_with_board_thickness)(mount_cylinder)
        mount_cylinders = mount_cylinders.fuse(mount_cylinder)

    return mount_cylinders


def create_printer_host_and_screen_assembly():
    tft = creaate_tft()

    housing = create_housing(tft)

    housing_real_height_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    housing_real_height_cutter = align(
        housing_real_height_cutter, housing, Alignment.CENTER
    )
    housing_real_height_cutter = align(
        housing_real_height_cutter,
        housing,
        Alignment.STACK_TOP,
        stack_gap=-(tft_housing_height - tft_housing_cut_height),
    )
    housing = housing.cut(housing_real_height_cutter)

    raspi = create_raspi_board()

    move_raspi_to_center = align_translation(
        raspi.leader,
        tft,
        Alignment.CENTER,
        axes=[0, 1],
    )
    raspi = move_raspi_to_center(raspi)

    raspi_mount_cylinders = create_raspi_mount_cylinders(raspi, tft)

    move_raspi_on_standoffs = align_translation(
        raspi.leader,
        raspi_mount_cylinders,
        Alignment.STACK_TOP,
    )
    raspi = move_raspi_on_standoffs(raspi)

    raspi_connectors = create_raspi_connectors(raspi)
    raspi_connectors = raspi_connectors.fuse(raspi_mount_cylinders)

    assembly = LeaderFollowersCuttersPart(housing)
    assembly.add_named_non_production_part(tft.leaders_followers_fused(), "tft_43")
    assembly.add_named_non_production_part(raspi.leader, "raspberry_pi_board")
    assembly.add_named_non_production_part(
        raspi_connectors,
        "raspberry_pi_connectors",
    )

    return assembly


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    assembly = create_printer_host_and_screen_assembly()
    parts.add(
        assembly.get_non_production_part_by_name("tft_43"),
        "bt_pi_tft_43",
        flip=False,
        skip_in_production=True,
        color=tft_visual_color,
    )

    parts.add(
        assembly.leader,
        "bt_pi_tft_43_housing",
        flip=True,
        color=tft_housing_visual_color,
    )

    parts.add(
        assembly.get_non_production_part_by_name("raspberry_pi_board"),
        "raspi_board",
        flip=False,
        skip_in_production=True,
        color=raspi_pcb_color,
    )
    parts.add(
        assembly.get_non_production_part_by_name("raspberry_pi_connectors"),
        "raspi_connectors",
        flip=False,
        skip_in_production=True,
        color=raspi_connector_color,
    )

    # parts.add(housing, "bt_pi_tft_43_housing", flip=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=8,
    )

    _logger.info("bt_pi_tft_43 created successfully!")


if __name__ == "__main__":
    main()
