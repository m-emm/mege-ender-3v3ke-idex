"""Raspberry Pi board assembly."""

import numpy as np
from mege_ender_3v3ke_idex.designs.sil_dil import (
    create_dil,
    top_pin_length,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_side,
)
from shellforgepy.simple import *

BIG_THING = 500

raspi_width = 56
raspi_board_length = 85
raspi_board_width = raspi_width
raspi_board_corner_radius = 3
raspi_board_thickness = 1.3
raspi_screw_hole_diameter = 2.75
raspi_screw_hole_distance = 58
raspi_screw_hole_x_inset = 3.5
raspi_screw_hole_y_inset = raspi_board_corner_radius

raspi_network_dist = 10.25
raspi_network_width = 16
raspi_network_length = 21.3
raspi_network_height = 13.6

raspi_usb_1_dist = 29
raspi_usb_2_dist = 47
raspi_usb_width = 13.3
raspi_usb_length = 17.3
raspi_usb_height = 15.44

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


def create_raspberry_pi_gpio():
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


def create_raspberry_pi_assembly():
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

    raspi.add_named_follower(create_raspberry_pi_gpio(), "gpio")

    return raspi
