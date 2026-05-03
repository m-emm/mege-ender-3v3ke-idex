"""
Trellis Plate

Usage:
    cd <project_root> && ./run.sh path/to/trellis_plate.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/trellis_plate.py
"""

import logging
import math
import os

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

BIG_THING = 500
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


def create_trellis_plate(
    length,
    width,
    thickness,
    x_border_width,
    y_border_width,
    band_width,
    band_pitch,
    hole_fillet_radius=None,
):

    base = create_box(length, width, thickness)

    cutter_template_size = band_pitch - 2 * band_width
    if hole_fillet_radius is not None:

        trellis_cutter_template = create_filleted_box(
            cutter_template_size,
            cutter_template_size,
            BIG_THING,
            fillet_radius=hole_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )
    else:
        trellis_cutter_template = create_box(
            cutter_template_size,
            cutter_template_size,
            BIG_THING,
        )

    trellis_cutter_template = rotate(45)(trellis_cutter_template)

    diagonal_spacing = band_pitch * math.sqrt(2)

    num_x_cutters = math.ceil((length - 2 * x_border_width) / diagonal_spacing)
    num_y_cutters = math.ceil((width - 2 * y_border_width) / diagonal_spacing)

    trellis_cutters = PartCollector()

    for x_int in range(num_x_cutters):
        for y_int in range(num_y_cutters):
            x_pos = x_border_width + band_pitch / 2 + x_int * diagonal_spacing
            y_pos = y_border_width + band_pitch / 2 + y_int * diagonal_spacing

            cutter = translate(x_pos, y_pos, 0)(trellis_cutter_template)
            trellis_cutters = trellis_cutters.fuse(cutter)

            cutter_offset = cutter = translate(
                x_pos + diagonal_spacing / 2, y_pos + diagonal_spacing / 2, 0
            )(trellis_cutter_template)
            trellis_cutters = trellis_cutters.fuse(cutter_offset)

    trellis_cutters = align(trellis_cutters, base, alignment=Alignment.CENTER)

    inner_cutter = create_box(
        length - 2 * x_border_width,
        width - 2 * y_border_width,
        BIG_THING,
    )
    inner_cutter = align(inner_cutter, base, alignment=Alignment.CENTER)
    border_cutter = create_box(
        length + 2 * BIG_THING,
        width + 2 * BIG_THING,
        BIG_THING,
    )
    border_cutter = align(border_cutter, base, alignment=Alignment.CENTER)
    border_cutter = border_cutter.cut(inner_cutter)

    trellis_cutters = trellis_cutters.cut(border_cutter)

    base = base.cut(trellis_cutters)

    return base


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_trellis_plate(
        length=400,
        width=50,
        thickness=5,
        x_border_width=5,
        y_border_width=5,
        band_width=5,
        band_pitch=30,
        hole_fillet_radius=2,
    )
    parts.add(part, "trellis_plate", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("trellis_plate created successfully!")


if __name__ == "__main__":
    main()
