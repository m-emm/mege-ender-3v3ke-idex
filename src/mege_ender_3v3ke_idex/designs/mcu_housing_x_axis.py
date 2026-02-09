"""
Mcu Housing X Axis

Usage:
    cd <project_root> && ./run.sh path/to/mcu_housing_x_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/mcu_housing_x_axis.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.sil_dil import (
    dil_pitch,
    pcb_thickness,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_base_width,
    wire_wrap_pin_length,
    wire_wrap_pin_side,
)
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

BIG_THING = 500

PLATE_THICKNESS = 2.0
PLATE_BORDER = 6.0

PIN_LENGTH_BELOW_BOARD = wire_wrap_pin_length
PIN_SLOT_SLACK = 0.20
BOARD_CORNER_RADIUS = 0.25 * dil_pitch

PICO_BOARD_THICKNESS = pcb_thickness
TMC_BOARD_THICKNESS = 1.6

PICO_NUM_PINS_PER_ROW = 20
PICO_ROW_SPACING = 8 * dil_pitch
PICO_BOARD_WIDTH = 21.0
PICO_BOARD_LENGTH = 51.0

TMC_NUM_PINS_PER_ROW = 8
TMC_ROW_SPACING = 4 * dil_pitch
TMC_BOARD_WIDTH = 15.2
TMC_BOARD_LENGTH = 20.3

# Approximate board placement from klipper_setup/klipper_config/pico_w_btt_tmc2226.yaml:
# PICO origin [0,20], TMC1 origin [20,18], TMC2 origin [20,9]
PICO_TO_DRIVER_RIGHT_GAP = 3.5 * dil_pitch

HEADER_CUTTER_SLACK = 0.35


def _create_header_board_bundle(
    *,
    board_width: float,
    board_length: float,
    board_thickness: float,
    row_spacing: float,
    pins_per_row: int,
    pin_side: float = wire_wrap_pin_side,
    pin_length_below_board: float = PIN_LENGTH_BELOW_BOARD,
    pin_slot_slack: float = PIN_SLOT_SLACK,
    header_base_width: float = wire_wrap_pin_base_width,
    header_base_thickness: float = wire_wrap_pin_base_thickness,
    header_cutter_slack: float = HEADER_CUTTER_SLACK,
) -> LeaderFollowersCuttersPart:
    board_body = create_filleted_box(
        board_width,
        board_length,
        board_thickness,
        fillet_radius=BOARD_CORNER_RADIUS,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    pins = PartCollector()
    headers = PartCollector()
    pin_slots = PartCollector()
    header_slots = PartCollector()
    y_pitch_span = (pins_per_row - 1) * dil_pitch
    y_start = y_pitch_span / 2.0
    row_header_length = (pins_per_row - 1) * dil_pitch + header_base_width

    for row_sign in [-1, 1]:
        row_x_offset = row_sign * row_spacing / 2.0

        header_base = create_box(
            header_base_width,
            row_header_length,
            header_base_thickness,
        )
        header_base = align(header_base, board_body, Alignment.CENTER)
        header_base = align(header_base, board_body, Alignment.STACK_BOTTOM)
        header_base = translate(row_x_offset, 0, 0)(header_base)
        headers = headers.fuse(header_base)

        header_slot = create_box(
            header_base_width + 2 * header_cutter_slack,
            row_header_length + 2 * header_cutter_slack,
            BIG_THING,
        )
        header_slot = align(header_slot, header_base, Alignment.CENTER)
        header_slots = header_slots.fuse(header_slot)

        for i in range(pins_per_row):
            y_offset = y_start - i * dil_pitch
            x_offset = row_x_offset

            pin = create_box(pin_side, pin_side, pin_length_below_board)
            pin = align(pin, board_body, Alignment.CENTER)
            pin = align(pin, board_body, Alignment.STACK_BOTTOM)
            pin = translate(x_offset, y_offset, 0)(pin)
            pins = pins.fuse(pin)

            pin_slot = create_box(
                pin_side + 2 * pin_slot_slack,
                pin_side + 2 * pin_slot_slack,
                BIG_THING,
            )
            pin_slot = align(pin_slot, pin, Alignment.CENTER)
            pin_slots = pin_slots.fuse(pin_slot)

    visual = board_body.fuse(pins).fuse(headers)

    return LeaderFollowersCuttersPart(
        leader=board_body,
        followers=[pins, headers],
        cutters=[pin_slots, header_slots],
        non_production_parts=[visual],
        follower_names=["pins", "headers"],
        cutter_names=["pins_cutter", "headers_cutter"],
        non_production_names=["visual"],
    )


def _create_ground_plate_blank(
    boards_layout_reference,
):
    boards_bb_size = get_bounding_box_size(boards_layout_reference)

    plate = create_box(
        boards_bb_size[0] + 2 * PLATE_BORDER,
        boards_bb_size[1] + 2 * PLATE_BORDER,
        PLATE_THICKNESS,
    )
    plate = align(plate, boards_layout_reference, Alignment.CENTER, axes=[1, 2])
    plate = align(plate, boards_layout_reference, Alignment.LEFT)
    plate = translate(-PLATE_BORDER, 0, 0)(plate)
    return plate


def _create_board_layout() -> dict[str, LeaderFollowersCuttersPart]:
    pico = _create_header_board_bundle(
        board_width=PICO_BOARD_WIDTH,
        board_length=PICO_BOARD_LENGTH,
        board_thickness=PICO_BOARD_THICKNESS,
        row_spacing=PICO_ROW_SPACING,
        pins_per_row=PICO_NUM_PINS_PER_ROW,
    )
    tmc_1 = _create_header_board_bundle(
        board_width=TMC_BOARD_WIDTH,
        board_length=TMC_BOARD_LENGTH,
        board_thickness=TMC_BOARD_THICKNESS,
        row_spacing=TMC_ROW_SPACING,
        pins_per_row=TMC_NUM_PINS_PER_ROW,
    )
    tmc_2 = _create_header_board_bundle(
        board_width=TMC_BOARD_WIDTH,
        board_length=TMC_BOARD_LENGTH,
        board_thickness=TMC_BOARD_THICKNESS,
        row_spacing=TMC_ROW_SPACING,
        pins_per_row=TMC_NUM_PINS_PER_ROW,
    )

    tmc_1 = align(
        tmc_1,
        pico,
        Alignment.STACK_RIGHT,
        stack_gap=PICO_TO_DRIVER_RIGHT_GAP,
    )
    tmc_1 = align(tmc_1, pico, Alignment.BACK)

    tmc_2 = align(
        tmc_2,
        pico,
        Alignment.STACK_RIGHT,
        stack_gap=PICO_TO_DRIVER_RIGHT_GAP,
    )
    tmc_2 = align(tmc_2, pico, Alignment.FRONT)

    return {
        "pico": pico,
        "tmc1": tmc_1,
        "tmc2": tmc_2,
    }


def create_mcu_housing_x_axis() -> LeaderFollowersCuttersPart:
    """Create an X-axis electronics assembly with ground plate and pin slits."""
    boards_by_name = _create_board_layout()

    boards_layout_reference = PartCollector()
    for board in boards_by_name.values():
        boards_layout_reference = boards_layout_reference.fuse(
            board.get_non_production_part_by_name("visual")
        )

    ground_plate_blank = _create_ground_plate_blank(
        boards_layout_reference=boards_layout_reference
    )

    assembly = LeaderFollowersCuttersPart(leader=ground_plate_blank)
    assembly.add_named_follower(ground_plate_blank, "ground_plate_blank")

    for name, board in boards_by_name.items():
        assembly.add_named_follower(board.leader, f"{name}_board_body")
        assembly.add_named_follower(
            board.get_follower_part_by_name("pins"),
            f"{name}_pins",
        )
        assembly.add_named_follower(
            board.get_follower_part_by_name("headers"),
            f"{name}_headers",
        )
        assembly.add_named_cutter(
            board.get_cutter_part_by_name("pins_cutter"),
            f"{name}_pins_cutter",
        )
        assembly.add_named_cutter(
            board.get_cutter_part_by_name("headers_cutter"),
            f"{name}_headers_cutter",
        )
        assembly.add_named_non_production_part(
            board.get_non_production_part_by_name("visual"),
            f"{name}_visual",
        )

    assembly.leader = assembly.use_as_cutter_on(assembly.leader)
    return assembly


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    housing = create_mcu_housing_x_axis()

    parts.add(housing.leader, "mcu_housing_x_axis_ground_plate", flip=False)

    for name, part in housing.get_named_non_production_part_items():
        color = (0.20, 0.65, 0.20) if "pico" in name else (0.78, 0.35, 0.10)
        parts.add(
            part,
            f"mcu_housing_x_axis_{name}",
            flip=False,
            skip_in_production=True,
            color=color,
        )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("mcu_housing_x_axis created successfully!")


if __name__ == "__main__":
    main()
