"""
Nitehawk Holder

Usage:
    cd <project_root> && ./run.sh path/to/nitehawk_holder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/nitehawk_holder.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401; Keep the materials menu around, in case we want to switch back to other materials
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_ender_3v3ke_idex.designs.nitehawk_holder import (
    create_nitehawk_board,
    create_nitehawk_holder,
    nitehawk_board_angle,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
BIG_THING = 500


def create_tool_head() -> LeaderFollowersCuttersPart:

    sprite_extruder = create_sprite_extruder()

    holder = create_nitehawk_holder(sprite_extruder)

    holder_screw_hole_cutter_1 = holder.get_named_cutter("screw_hole_cutter_1")

    nitehawk_board = create_nitehawk_board()
    nitehawk_board = rotate(nitehawk_board_angle)(nitehawk_board)
    nitehawk_pcb = nitehawk_board.get_named_follower("pcb")
    board_alignment = align_translation(
        nitehawk_pcb, holder, Alignment.STACK_TOP, stack_gap=0.0
    )

    nitehawk_board = board_alignment(nitehawk_board)

    board_hole_1 = nitehawk_board.get_named_cutter("hole_1")

    align_board_translattion = align_translation(
        board_hole_1, holder_screw_hole_cutter_1, Alignment.CENTER, axes=[0, 1]
    )
    nitehawk_board = align_board_translattion(nitehawk_board)

    retval = sprite_extruder

    retval = retval.merge_except_leader(holder)
    retval.add_named_non_production_part(holder.leader, "nitehawk_holder_leader")
    retval.add_named_non_production_part(nitehawk_board.leader, "nitehawk_board")
    retval = rotate(90, axis=(1, 0, 0))(retval)
    retval = rotate(180)(retval)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part

    toolhead = create_tool_head()

    parts.add(toolhead, "toolhead", flip=False, skip_in_production=True)

    for name, npp in toolhead.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("nitehawk_holder created successfully!")


if __name__ == "__main__":
    main()
